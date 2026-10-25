"""Anular un pago por el service (S3-B5, US-097; blueprint B5 y flujo 6.3; D13, M-8, L-5, S3-D51).

`payments.service.void(session, *, payment_id, reason) -> PaymentOut` con el gate REAL
(`memberships.service.membership_payability`, registrado al importar `memberships.service`) y el
handler real de `PaymentVoided` (`memberships.on_payment_voided`, US-087). Orden de D13: leer el
pago sin candado (404 `payment_not_found`), gate sobre su `membership_id` (`FOR UPDATE` de la
membresía), `FOR UPDATE` del pago con `populate_existing`, `rules.can_void` (409
`payment_already_voided`), las cuatro columnas de anulación (`voided_by = get_actor()`,
`voided_at = current_clock().now_utc()`), `flush` (el rechazo del trigger de `0011` con
`IMMUTABLE_CONSTRAINT` también sale como 409) y `emit(PaymentVoided)`. Todo en un savepoint: un
handler que falla deja el pago sin anular.

"Ahora" es `T0` = 2026-10-21T15:00:00Z (10:00 en Bogotá; `reloj`). El aviso de mes anterior
(M-8 punto 3) compara meses civiles de Bogotá: un pago del 15 de septiembre o del
2026-10-01T04:59Z (30 de septiembre en Bogotá) avisa; uno del 2026-10-01T05:00Z o de hoy no.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.db import violated_constraint
from app.core.errors import DomainError
from app.modules.memberships import service as memberships_service
from app.modules.payments import rules
from app.modules.payments import service as payments_service
from app.modules.payments.exceptions import (
    InvalidVoidReason,
    MembershipGateNotRegistered,
    PaymentAlreadyVoided,
    PaymentNotFound,
)
from app.modules.payments.models import Payment
from app.modules.payments.service import IMMUTABLE_CONSTRAINT, PaymentVoided
from tests.conftest import T0, CapturarEventos
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.memberships._apoyo import leer_membresia
from tests.payments._apoyo import (
    DE_ANULACION,
    GateDoble,
    anular,
    gate_registrado,
    leer_pago,
    pagos_de,
    registrar,
    updates_de,
)

ADMIN = UUID("0000000a-0000-4000-8000-00000000b510")
PAGADOR = UUID("0000000a-0000-4000-8000-00000000b511")
MOTIVO = "Monto mal digitado"
TABLA_PAGOS = "payments.payments"
TABLA_MEMBRESIAS = "memberships.memberships"
INTACTAS = (
    "id",
    "membership_id",
    "member_id",
    "amount_cop",
    "method",
    "reference",
    "paid_at",
    "registered_by",
    "created_at",
    "created_by",
)
AVISO = "void of previous month"


async def _pago(
    session: AsyncSession, *, estado: str = "pending_payment", **cambios: Any
) -> Payment:
    """Un pago de 60.000 (fábrica, sin eventos) de una membresía nueva de 120.000."""
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan, status=estado)
    cambios.setdefault("amount", 60_000)
    return await make_payment(session, membresia, **cambios)


def _intactas(fila: dict[str, Any]) -> dict[str, Any]:
    return {columna: fila[columna] for columna in INTACTAS}


# Anulación feliz ----------------------------------------------------------------------------------


async def test_anular_llena_las_cuatro_columnas_y_no_toca_lo_demas(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    pago = await _pago(
        session, method="nequi", reference="NEQ-00123", paid_at=T0 - timedelta(days=1)
    )
    antes = await leer_pago(session, pago.id)
    assert antes is not None
    salida = await anular(session, ADMIN, payment_id=pago.id, reason=f"  {MOTIVO}  ")
    despues = await leer_pago(session, pago.id)
    assert despues is not None
    assert _intactas(despues) == _intactas(antes)
    assert despues["voided"] is True
    assert despues["void_reason"] == MOTIVO
    assert despues["voided_by"] == ADMIN
    assert despues["voided_at"] == T0
    assert (salida.id, salida.voided, salida.void_reason) == (pago.id, True, MOTIVO)
    assert (salida.voided_by, salida.voided_at) == (ADMIN, T0)
    assert (salida.amount_cop, salida.method, salida.reference) == (60_000, "nequi", "NEQ-00123")
    assert salida.paid_at == T0 - timedelta(days=1)


async def test_anular_deja_un_update_de_auditoria_del_admin_con_el_socio(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    pago = await _pago(session)
    pago_id, socio_id = pago.id, pago.member_id
    await anular(session, ADMIN, payment_id=pago_id, reason=MOTIVO)
    cambios = await updates_de(session, TABLA_PAGOS, pago_id)
    assert [(c["user_id"], c["subject_member_id"]) for c in cambios] == [(ADMIN, socio_id)]
    antes, despues = cambios[0]["before"], cambios[0]["after"]
    assert set(antes) == set(despues) == DE_ANULACION
    assert antes == {"voided": False, "void_reason": None, "voided_by": None, "voided_at": None}
    assert (despues["voided"], despues["void_reason"]) == (True, MOTIVO)
    assert despues["voided_by"] == str(ADMIN)
    assert str(despues["voided_at"]).startswith("2026-10-21T15:00:00")


async def test_anular_emite_payment_voided_una_vez_con_los_ids(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    anulados = capturar_eventos(PaymentVoided)
    pago = await _pago(session)
    await anular(session, ADMIN, payment_id=pago.id, reason=MOTIVO)
    assert [(e.membership_id, e.payment_id) for e in anulados] == [(pago.membership_id, pago.id)]


async def test_anular_usa_el_gate_sobre_la_membresia_del_pago(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """D13: el candado de la membresía se pide por el gate (el mismo puerto de `register`)."""
    pago = await _pago(session)
    with gate_registrado(GateDoble()) as doble:
        await anular(session, ADMIN, payment_id=pago.id, reason=MOTIVO)
    assert doble.llamadas == [pago.membership_id]


# Errores ------------------------------------------------------------------------------------------


async def test_la_segunda_anulacion_da_409_y_no_cambia_nada(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    pago = await _pago(session)
    pago_id = pago.id
    await anular(session, ADMIN, payment_id=pago_id, reason=MOTIVO)
    primera = await leer_pago(session, pago_id)
    reloj.advance(minutes=5)
    with pytest.raises(PaymentAlreadyVoided) as capturado, actor_scope(PAGADOR):
        await payments_service.void(session, payment_id=pago_id, reason="Otro motivo")
    assert (capturado.value.status, capturado.value.code) == (409, "payment_already_voided")
    assert await leer_pago(session, pago_id) == primera
    assert len(await updates_de(session, TABLA_PAGOS, pago_id)) == 1


async def test_un_pago_inexistente_da_404_payment_not_found(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    with pytest.raises(PaymentNotFound) as capturado, actor_scope(ADMIN):
        await payments_service.void(session, payment_id=uuid4(), reason=MOTIVO)
    assert (capturado.value.status, capturado.value.code) == (404, "payment_not_found")


@pytest.mark.parametrize(
    "motivo", ["x" * 501, "Monto\x00mal", "   "], ids=["501", "nul", "espacios"]
)
async def test_un_motivo_invalido_da_422_en_reason_y_no_anula(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, motivo: str
) -> None:
    """El service valida el motivo aunque no llegue por HTTP (un NUL llegaría a PostgreSQL)."""
    pago = await _pago(session)
    pago_id = pago.id
    with pytest.raises(InvalidVoidReason) as capturado, actor_scope(ADMIN):
        await payments_service.void(session, payment_id=pago_id, reason=motivo)
    assert capturado.value.field == "reason"
    fila = await leer_pago(session, pago_id)
    assert fila is not None and fila["voided"] is False
    assert await updates_de(session, TABLA_PAGOS, pago_id) == []


async def test_sin_gate_falla_cerrado_y_no_anula(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    pago = await _pago(session)
    pago_id = pago.id
    anterior = payments_service.membership_gate()
    payments_service.set_membership_gate(None)
    try:
        with pytest.raises(MembershipGateNotRegistered), actor_scope(ADMIN):
            await payments_service.void(session, payment_id=pago_id, reason=MOTIVO)
    finally:
        payments_service.set_membership_gate(anterior)
    fila = await leer_pago(session, pago_id)
    assert fila is not None and fila["voided"] is False


class _HandlerRoto(Exception):
    """No es `RuntimeError`: `NotImplementedError` del stub lo es y daría un verde falso."""


async def test_un_handler_de_payment_voided_que_falla_deja_el_pago_sin_anular(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    pago = await _pago(session)
    pago_id = pago.id

    async def roto(evento: PaymentVoided, sesion: AsyncSession) -> None:
        raise _HandlerRoto

    events.subscribe(PaymentVoided, roto)  # `restaurar_bus` lo quita al salir
    with pytest.raises(_HandlerRoto), actor_scope(ADMIN):
        await payments_service.void(session, payment_id=pago_id, reason=MOTIVO)
    fila = await leer_pago(session, pago_id)
    assert fila is not None
    assert {columna: fila[columna] for columna in DE_ANULACION} == {
        "voided": False,
        "void_reason": None,
        "voided_by": None,
        "voided_at": None,
    }
    assert await updates_de(session, TABLA_PAGOS, pago_id) == []


# Anular y registrar el correcto -------------------------------------------------------------------


async def test_anular_y_registrar_otro_deja_dos_filas_y_solo_suma_el_nuevo(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    pago = await _pago(session, reference="REC-1")
    membresia_id = pago.membership_id
    await anular(session, ADMIN, payment_id=pago.id, reason=MOTIVO)
    nuevo = await registrar(
        session,
        PAGADOR,
        membership_id=membresia_id,
        amount_cop=50_000,
        method="cash",
        reference="REC-2",
    )
    filas = await pagos_de(session, membresia_id)
    # `created_at` es el `now()` de la transacción de la prueba: igual en las dos filas.
    assert {f["id"]: f["voided"] for f in filas} == {pago.id: True, nuevo.id: False}
    assert await payments_service.sum_not_voided(session, membresia_id) == 50_000


# Lo que ya estaba anulado fuera del service -------------------------------------------------------

_ANULAR_POR_SQL = text(
    "UPDATE payments.payments SET voided = true, void_reason = 'Anulado por SQL', "
    "voided_by = :u, voided_at = now() WHERE id = :id"
)


async def test_un_pago_anulado_antes_por_sql_crudo_da_409(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    pago = await _pago(session)
    pago_id = pago.id
    await session.execute(_ANULAR_POR_SQL, {"u": PAGADOR, "id": pago_id})
    await session.commit()
    with pytest.raises(PaymentAlreadyVoided), actor_scope(ADMIN):
        await payments_service.void(session, payment_id=pago_id, reason=MOTIVO)
    fila = await leer_pago(session, pago_id)
    assert fila is not None
    assert (fila["void_reason"], fila["voided_by"]) == ("Anulado por SQL", PAGADOR)


async def test_el_rechazo_del_trigger_se_traduce_a_payment_already_voided(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si `rules.can_void` no viera la anulación previa, el `flush` choca con la rama
    `already_voided` del trigger de `0011`; `void` la traduce por `IMMUTABLE_CONSTRAINT` (nunca
    buscando texto) a 409, con el `IntegrityError` como causa. `void` llama a `rules.can_void`
    por el módulo, así que este reemplazo lo alcanza."""
    pago = await _pago(session)
    pago_id = pago.id
    await session.execute(_ANULAR_POR_SQL, {"u": PAGADOR, "id": pago_id})
    await session.commit()
    monkeypatch.setattr(rules, "can_void", lambda _pago: True)
    with pytest.raises(PaymentAlreadyVoided) as capturado, actor_scope(ADMIN):
        await payments_service.void(session, payment_id=pago_id, reason=MOTIVO)
    causa = capturado.value.__cause__
    assert isinstance(causa, IntegrityError)
    assert violated_constraint(causa) == IMMUTABLE_CONSTRAINT
    fila = await leer_pago(session, pago_id)
    assert fila is not None and fila["void_reason"] == "Anulado por SQL"


# L-5: el pago de una membresía anulada se puede anular y no la reactiva --------------------------


async def test_anular_el_pago_de_una_cancelada_da_200_y_no_la_reactiva(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    revertidas = capturar_eventos(memberships_service.MembershipActivationReverted)
    pago = await _pago(session, estado="cancelled")
    membresia_id = pago.membership_id
    salida = await anular(session, ADMIN, payment_id=pago.id, reason=MOTIVO)
    assert salida.voided is True
    fila = await leer_membresia(session, membresia_id)
    assert fila is not None and fila["status"] == "cancelled"
    assert revertidas == []
    assert await updates_de(session, TABLA_MEMBRESIAS, membresia_id) == []


# M-8 punto 3 (S3-D51): aviso con solo ids al anular un pago de un mes anterior --------------------

_ATRIBUTOS_DE_REGISTRO = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


@pytest.mark.parametrize(
    ("paid_at", "avisa"),
    [
        (datetime(2026, 9, 15, 15, 0, tzinfo=UTC), True),
        (datetime(2026, 10, 1, 4, 59, tzinfo=UTC), True),
        (datetime(2026, 10, 1, 5, 0, tzinfo=UTC), False),
        (T0, False),
    ],
    ids=["15-sep", "30-sep-en-bogota", "01-oct-en-bogota", "hoy"],
)
async def test_anular_un_pago_de_un_mes_anterior_deja_un_aviso_con_solo_ids(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    caplog: pytest.LogCaptureFixture,
    paid_at: datetime,
    avisa: bool,
) -> None:
    pago = await _pago(session, paid_at=paid_at, reference="NEQ-77", amount=61_234)
    pago_id, membresia_id = pago.id, pago.membership_id
    caplog.set_level(logging.WARNING)
    await anular(session, ADMIN, payment_id=pago_id, reason=MOTIVO)
    avisos = [r for r in caplog.records if r.getMessage() == AVISO]
    if not avisos:
        assert not avisa
        return
    assert avisa and len(avisos) == 1
    registro = avisos[0]
    assert registro.levelno == logging.WARNING
    assert registro.name.startswith("app.")
    extra = set(registro.__dict__) - _ATRIBUTOS_DE_REGISTRO
    assert extra == {"payment_id", "membership_id"}
    assert str(registro.__dict__["payment_id"]) == str(pago_id)
    assert str(registro.__dict__["membership_id"]) == str(membresia_id)
    texto = str(registro.__dict__)
    assert MOTIVO not in texto and "NEQ-77" not in texto and "61234" not in texto


# Orden de candados (D13, L-4: se prueba con una espía de sentencias) -----------------------------


@pytest.fixture
def sentencias(session: AsyncSession) -> Iterator[list[str]]:
    """Las sentencias que la conexión de `session` envía, en orden."""
    conexion = session.bind.sync_connection  # type: ignore[union-attr]
    vistas: list[str] = []

    def espiar(_c: object, _cur: object, sql: str, *_args: object) -> None:
        vistas.append(sql)

    event.listen(conexion, "before_cursor_execute", espiar)
    try:
        yield vistas
    finally:
        event.remove(conexion, "before_cursor_execute", espiar)


async def test_lee_el_pago_sin_candado_bloquea_la_membresia_y_despues_el_pago(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, sentencias: list[str]
) -> None:
    pago = await _pago(session)
    sentencias.clear()
    await anular(session, ADMIN, payment_id=pago.id, reason=MOTIVO)

    def primera(condicion: Any) -> int:
        return next(i for i, s in enumerate(sentencias) if condicion(s))

    lectura = primera(
        lambda s: "payments.payments" in s and s.lstrip().upper().startswith("SELECT")
    )
    membresia = primera(lambda s: "FOR UPDATE" in s and "memberships.memberships" in s)
    fila_pago = primera(lambda s: "FOR UPDATE" in s and "payments.payments" in s)
    escritura = primera(lambda s: s.lstrip().upper().startswith("UPDATE payments.payments".upper()))
    assert "FOR UPDATE" not in sentencias[lectura]
    assert lectura < membresia < fila_pago < escritura, sentencias


# Concurrencia (D13, con commit real) --------------------------------------------------------------


async def _intentar(sesion: AsyncSession, payment_id: UUID) -> object:
    with actor_scope(ADMIN):
        try:
            salida = await payments_service.void(sesion, payment_id=payment_id, reason=MOTIVO)
            await sesion.commit()
        except DomainError as error:
            await sesion.rollback()
            return error
    return salida


async def test_dos_anulaciones_simultaneas_una_da_200_y_la_otra_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
) -> None:
    primera, segunda = dos_sesiones
    pago = await _pago(primera)
    pago_id = pago.id
    resultados = await asyncio.gather(
        _intentar(primera, pago_id),
        _intentar(segunda, pago_id),
        return_exceptions=True,  # las dos terminan antes de que `dos_sesiones` limpie
    )
    errores = [r for r in resultados if isinstance(r, BaseException)]
    assert len(errores) == 1 and isinstance(errores[0], PaymentAlreadyVoided), resultados
    fabrica = async_sessionmaker(primera.bind, expire_on_commit=False)
    async with fabrica() as lectora:
        fila = await leer_pago(lectora, pago_id)
        assert fila is not None and fila["voided"] is True
        assert len(await updates_de(lectora, TABLA_PAGOS, pago_id)) == 1
