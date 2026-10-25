"""Anular una membresía (S3-B6, US-090; blueprint B6 y flujo 6.5; D3, D8, D17, M-5, M-7, S3-D48).

`cancel(session, *, membership_id, reason) -> MembershipOut`, dentro de `begin_nested()`:
`rules.normalize_cancel_reason` (NFC, recorte, `SafeText` y de 5 a 500 caracteres tras recortar;
`CancelReasonInvalid`, 422 `validation_error` con `field="reason"`, sin el valor en el mensaje);
`sell.lock_membership` (`FOR UPDATE` con `populate_existing`, el único candado: ni el del socio);
404 `membership_not_found`; 409 `membership_already_cancelled`; `status = "cancelled"`,
`cancel_reason`, `cancelled_by = get_actor()`, `cancelled_at = current_clock().now_utc()`; `flush`
(auditoría `update` con el socio como sujeto); `emit(MembershipCancelled(membership_id, member_id,
reason_len))`, sin el texto del motivo. No toca pagos ni congelaciones. Después, la `EXCLUDE`
deja de contarla (se puede vender con las mismas fechas), el gate real de pagos responde
`cancelled` (409 `membership_cancelled`) y `guard_identity` impide revivirla (S3-D48).

"Hoy" es 2026-10-21 y "ahora" `T0` = 2026-10-21T15:00:00Z (`reloj`). El plan "Mensual" (120.000,
30 días) vendido hoy va del 2026-10-21 al 2026-11-20 (N-23). Estados de origen (guardados):
`pending_payment` de hoy; `active` de hoy; `expiring` del 2026-09-28 al 2026-10-28; `expired` del
2026-09-01 al 2026-10-01; `frozen` del 2026-10-15 al 2026-11-14 con su congelación del 2026-10-20
al 2026-10-25 (la fábrica no corre el fin).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import MissingActorError, actor_scope
from app.core.crypto.keyring import Keyring
from app.core.db import sqlstate_of, violated_constraint
from app.modules.memberships import service
from app.modules.memberships.exceptions import (
    CancelReasonInvalid,
    MembershipAlreadyCancelled,
    MembershipNotFound,
)
from app.modules.memberships.models import IDENTITY_CONSTRAINT, Membership
from app.modules.memberships.rules import (
    CANCEL_REASON_MAX,
    CANCEL_REASON_MIN,
    normalize_cancel_reason,
)
from app.modules.memberships.schemas import CancelMembershipIn
from app.modules.memberships.service import MembershipActivationReverted, MembershipCancelled
from app.modules.payments.exceptions import MembershipCancelled as PaymentToCancelledMembership
from tests.conftest import T0, CapturarEventos
from tests.factories.members import make_member
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.memberships._apoyo import (
    cancelar,
    congelaciones_de,
    leer_membresia,
    membresias_del_socio,
    vender,
)
from tests.payments._apoyo import (
    anular,
    leer_auditoria_de_pagos,
    leer_pago,
    pagos_de,
    registrar,
    updates_de,
)

ADMIN = UUID("0000000a-0000-4000-8000-00000000b630")
PAGADOR = UUID("0000000a-0000-4000-8000-00000000b631")
HOY = date(2026, 10, 21)
TABLA = "memberships.memberships"
MOTIVO = "Cambio de ciudad"
DE_ANULACION = frozenset({"status", "cancel_reason", "cancelled_by", "cancelled_at"})


# Regla pura: normalize_cancel_reason (D17, M-7) ---------------------------------------------------


def test_los_topes_del_motivo_son_los_del_check_de_la_tabla() -> None:
    assert (CANCEL_REASON_MIN, CANCEL_REASON_MAX) == (5, 500)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        (f"  {MOTIVO}  ", MOTIVO),
        ("abcde", "abcde"),
        ("  abcde  ", "abcde"),
        ("x" * 500, "x" * 500),
        ("Café cerrado", "Café cerrado"),
    ],
    ids=["recorta", "cinco", "cinco-con-espacios", "quinientos", "nfc"],
)
def test_normalize_cancel_reason_acepta_y_normaliza(entrada: str, esperado: str) -> None:
    assert normalize_cancel_reason(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["", "   ", "abcd", "  abcd  ", "x" * 501, "Motivo\x00largo", "​" * 6, "Motivo​largo"],
    ids=["vacio", "espacios", "cuatro", "cuatro-con-espacios", "501", "nul", "invisibles", "u200b"],
)
def test_normalize_cancel_reason_rechaza_con_422_en_reason_sin_el_valor(entrada: str) -> None:
    with pytest.raises(CancelReasonInvalid) as error:
        normalize_cancel_reason(entrada)
    assert (error.value.status, error.value.code, error.value.field) == (
        422,
        "validation_error",
        "reason",
    )
    if entrada.strip():
        assert entrada.strip() not in error.value.message


def test_el_esquema_corta_lo_enorme_y_rechaza_lo_invisible_antes_del_service() -> None:
    from pydantic import ValidationError

    assert CancelMembershipIn(reason=f"  {MOTIVO}  ").reason == MOTIVO
    assert CancelMembershipIn(reason="x" * 1999).reason == "x" * 1999  # lo decide el service
    for malo in ["y" * 2001, "", "   ", "a\x00bcdef", "​"]:
        with pytest.raises(ValidationError):
            CancelMembershipIn(reason=malo)
    with pytest.raises(ValidationError):
        CancelMembershipIn.model_validate({"reason": MOTIVO, "cancelled_by": str(uuid4())})


# Escenarios ------------------------------------------------------------------------------------


async def _membresia(session: AsyncSession, estado: str = "pending_payment") -> Membership:
    socio = await make_member(session)
    plan = await make_plan(session)
    if estado == "expiring":
        return await make_membership(session, socio, plan, status=estado, start=date(2026, 9, 28))
    if estado == "expired":
        return await make_membership(session, socio, plan, status=estado, start=date(2026, 9, 1))
    if estado == "frozen":
        membresia = await make_membership(
            session, socio, plan, status=estado, start=date(2026, 10, 15)
        )
        await make_freeze(session, membresia, date(2026, 10, 20), date(2026, 10, 25))
        return membresia
    return await make_membership(session, socio, plan, status=estado)


ESTADOS = ["pending_payment", "active", "expiring", "expired", "frozen"]


# Anular -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("estado", ESTADOS)
async def test_anular_desde_cada_estado_deja_cancelled_con_motivo_autor_y_fecha(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, estado: str
) -> None:
    membresia = await _membresia(session, estado)
    membresia_id = membresia.id
    antes = await leer_membresia(session, membresia_id)
    assert antes is not None
    salida = await cancelar(session, ADMIN, membership_id=membresia_id, reason=f"  {MOTIVO}  ")
    assert (salida.id, salida.status, salida.cancel_reason) == (membresia_id, "cancelled", MOTIVO)
    assert salida.cancelled_at == T0
    assert (salida.start_date, salida.end_date) == (antes["start_date"], antes["end_date"])
    assert len(salida.freezes) == (1 if estado == "frozen" else 0)
    fila = await leer_membresia(session, membresia_id)
    assert fila is not None
    assert (fila["status"], fila["cancel_reason"]) == ("cancelled", MOTIVO)
    assert (fila["cancelled_by"], fila["cancelled_at"]) == (ADMIN, T0)
    cambios = {k for k in fila if fila[k] != antes[k]}
    assert cambios == DE_ANULACION


async def test_anular_no_toca_los_pagos_ni_deja_auditoria_de_pagos(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session, "active")
    vigente = await make_payment(session, membresia, amount=60_000, reference="NEQ-1")
    anulado = await make_payment(
        session, membresia, amount=10_000, voided=True, void_reason="Error de digitación"
    )
    membresia_id, ids = membresia.id, (vigente.id, anulado.id)
    pagos_antes = [await leer_pago(session, i) for i in ids]
    auditoria_antes = await leer_auditoria_de_pagos(session)
    await cancelar(session, ADMIN, membership_id=membresia_id, reason=MOTIVO)
    assert [await leer_pago(session, i) for i in ids] == pagos_antes
    assert await leer_auditoria_de_pagos(session) == auditoria_antes
    assert len(await pagos_de(session, membresia_id)) == 2


async def test_anular_dos_veces_da_409_y_no_cambia_la_fila(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    membresia_id = membresia.id
    await cancelar(session, ADMIN, membership_id=membresia_id, reason=MOTIVO)
    anulada = await leer_membresia(session, membresia_id)
    with pytest.raises(MembershipAlreadyCancelled) as error:
        await cancelar(session, ADMIN, membership_id=membresia_id, reason="Otro motivo distinto")
    assert (error.value.status, error.value.code) == (409, "membership_already_cancelled")
    assert await leer_membresia(session, membresia_id) == anulada
    assert len(await updates_de(session, TABLA, membresia_id)) == 1


async def test_una_membresia_inexistente_da_404(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    with pytest.raises(MembershipNotFound) as error:
        await cancelar(session, ADMIN, membership_id=uuid4(), reason=MOTIVO)
    assert (error.value.status, error.value.code) == (404, "membership_not_found")


async def test_sin_actor_falla_cerrado_y_no_cambia_nada(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """Revisión de seguridad del Verde de B6, LOW-2: un llamador interno sin actor no deja una
    anulación sin autor (`cancelled_by`); `get_actor()` lanza y el savepoint revierte."""
    membresia = await _membresia(session)
    membresia_id = membresia.id
    antes = await leer_membresia(session, membresia_id)
    with pytest.raises(MissingActorError):
        await service.cancel(session, membership_id=membresia_id, reason=MOTIVO)
    assert await leer_membresia(session, membresia_id) == antes
    assert await updates_de(session, TABLA, membresia_id) == []


@pytest.mark.parametrize(
    "motivo",
    ["abcd", "  abc  ", "x" * 501, "Motivo\x00largo", "​" * 6],
    ids=["cuatro", "tres-con-espacios", "501", "nul", "invisibles"],
)
async def test_un_motivo_invalido_da_422_y_no_cambia_nada(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, motivo: str
) -> None:
    membresia = await _membresia(session)
    membresia_id = membresia.id
    antes = await leer_membresia(session, membresia_id)
    with pytest.raises(CancelReasonInvalid) as error:
        await cancelar(session, ADMIN, membership_id=membresia_id, reason=motivo)
    assert (error.value.status, error.value.field) == (422, "reason")
    assert await leer_membresia(session, membresia_id) == antes
    assert await updates_de(session, TABLA, membresia_id) == []


async def test_tras_anular_se_vende_al_mismo_socio_con_las_mismas_fechas(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    membresia_id, socio_id, plan_id = membresia.id, membresia.member_id, membresia.plan_id
    await cancelar(session, ADMIN, membership_id=membresia_id, reason=MOTIVO)
    nueva = await vender(session, ADMIN, member_id=socio_id, plan_id=plan_id)
    assert (nueva.start_date, nueva.end_date) == (HOY, date(2026, 11, 20))
    assert nueva.status == "pending_payment" and nueva.id != membresia_id
    estados = sorted(f["status"] for f in await membresias_del_socio(session, socio_id))
    assert estados == ["cancelled", "pending_payment"]


async def test_registrar_un_pago_contra_la_anulada_da_409_por_el_gate_real(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    membresia_id = membresia.id
    await cancelar(session, ADMIN, membership_id=membresia_id, reason=MOTIVO)
    with pytest.raises(PaymentToCancelledMembership) as error:
        await registrar(
            session, PAGADOR, membership_id=membresia_id, amount_cop=60_000, method="cash"
        )
    assert (error.value.status, error.value.code) == (409, "membership_cancelled")
    assert await pagos_de(session, membresia_id) == []


async def test_un_payment_voided_posterior_no_la_reactiva(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    membresia = await _membresia(session)
    membresia_id = membresia.id
    pago = await registrar(
        session, PAGADOR, membership_id=membresia_id, amount_cop=120_000, method="cash"
    )
    activa = await leer_membresia(session, membresia_id)
    assert activa is not None and activa["status"] == "active"
    await cancelar(session, ADMIN, membership_id=membresia_id, reason=MOTIVO)
    revertidas = capturar_eventos(MembershipActivationReverted)
    anulado = await anular(session, ADMIN, payment_id=pago.id, reason="Monto mal digitado")
    assert anulado.voided is True
    fila = await leer_membresia(session, membresia_id)
    assert fila is not None and (fila["status"], fila["cancel_reason"]) == ("cancelled", MOTIVO)
    assert revertidas == []


async def test_la_auditoria_es_un_update_del_admin_con_el_socio_como_sujeto(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    membresia_id, socio_id = membresia.id, membresia.member_id
    await cancelar(session, ADMIN, membership_id=membresia_id, reason=MOTIVO)
    filas = await updates_de(session, TABLA, membresia_id)
    assert len(filas) == 1
    fila = filas[0]
    assert (fila["user_id"], fila["subject_member_id"]) == (ADMIN, socio_id)
    assert set(fila["before"]) == DE_ANULACION and set(fila["after"]) == DE_ANULACION
    assert fila["before"]["status"] == "pending_payment"
    assert (fila["after"]["status"], fila["after"]["cancel_reason"]) == ("cancelled", MOTIVO)


async def test_emite_membership_cancelled_una_vez_con_el_largo_y_sin_el_texto(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    membresia = await _membresia(session)
    membresia_id, socio_id = membresia.id, membresia.member_id
    recibidos = capturar_eventos(MembershipCancelled)
    await cancelar(session, ADMIN, membership_id=membresia_id, reason=f"  {MOTIVO}  ")
    assert len(recibidos) == 1
    evento = recibidos[0]
    assert (evento.membership_id, evento.member_id) == (membresia_id, socio_id)
    assert evento.reason_len == len(MOTIVO) == 16
    assert MOTIVO not in repr(evento)


class _HandlerRoto(Exception):
    """Excepción propia (no `RuntimeError`: `NotImplementedError` lo es)."""


async def test_un_handler_que_falla_deja_la_membresia_como_estaba(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session, "active")
    membresia_id = membresia.id
    antes = await leer_membresia(session, membresia_id)

    async def roto(evento: MembershipCancelled, sesion: AsyncSession) -> None:
        raise _HandlerRoto

    events.subscribe(MembershipCancelled, roto)  # `restaurar_bus` lo quita al salir
    with pytest.raises(_HandlerRoto), actor_scope(ADMIN):
        await service.cancel(session, membership_id=membresia_id, reason=MOTIVO)
    assert await leer_membresia(session, membresia_id) == antes
    assert await updates_de(session, TABLA, membresia_id) == []


async def test_anular_una_congelada_conserva_su_congelacion_y_su_fin(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session, "frozen")
    membresia_id = membresia.id
    congelaciones = await congelaciones_de(session, membresia_id)
    assert len(congelaciones) == 1
    salida = await cancelar(session, ADMIN, membership_id=membresia_id, reason=MOTIVO)
    assert await congelaciones_de(session, membresia_id) == congelaciones
    assert salida.end_date == date(2026, 11, 14)
    assert [(f.frozen_from, f.frozen_to) for f in salida.freezes] == [
        (date(2026, 10, 20), date(2026, 10, 25))
    ]


@pytest.mark.parametrize(
    "cambio",
    ["status = 'active'", "cancel_reason = 'Otro motivo'", "cancelled_at = now()"],
    ids=["revivir", "motivo", "fecha"],
)
async def test_guard_identity_impide_tocar_la_anulada_por_sql_crudo(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, cambio: str
) -> None:
    membresia = await _membresia(session)
    membresia_id = membresia.id
    await cancelar(session, ADMIN, membership_id=membresia_id, reason=MOTIVO)
    sentencia = text(f"UPDATE memberships.memberships SET {cambio} WHERE id = :id")  # noqa: S608
    with pytest.raises(IntegrityError) as error:
        async with session.begin_nested():
            await session.execute(sentencia, {"id": membresia_id})
    assert sqlstate_of(error.value) == "23000"
    assert violated_constraint(error.value) == IDENTITY_CONSTRAINT
    fila = await leer_membresia(session, membresia_id)
    assert fila is not None and (fila["status"], fila["cancel_reason"]) == ("cancelled", MOTIVO)


# Candados (D3, H-3; L-4: se prueba con una espía de sentencias) ---------------------------------


@pytest.fixture
def sentencias(session: AsyncSession) -> Iterator[list[str]]:
    """Las sentencias que la conexión de `session` envía, en orden."""
    conexion = session.bind.sync_connection  # type: ignore[union-attr]
    vistas: list[str] = []

    def espiar(_c: object, _cur: object, sql: str, *_args: Any) -> None:
        vistas.append(sql)

    event.listen(conexion, "before_cursor_execute", espiar)
    try:
        yield vistas
    finally:
        event.remove(conexion, "before_cursor_execute", espiar)


async def test_cancel_solo_bloquea_la_fila_de_la_membresia_antes_de_escribir(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, sentencias: list[str]
) -> None:
    membresia = await _membresia(session)
    membresia_id = membresia.id
    sentencias.clear()
    await cancelar(session, ADMIN, membership_id=membresia_id, reason=MOTIVO)
    bloqueos = [i for i, s in enumerate(sentencias) if "FOR UPDATE" in s.upper()]
    escritura = next(
        i
        for i, s in enumerate(sentencias)
        if s.lstrip().upper().startswith("UPDATE MEMBERSHIPS.MEMBERSHIPS")
    )
    assert len(bloqueos) == 1, sentencias
    assert "memberships.memberships" in sentencias[bloqueos[0]]
    assert bloqueos[0] < escritura
    # el candado del socio (`lock_member`) es el asesor con `hashtextextended`; el de la cadena
    # de auditoría (`after_flush`) sí aparece y no cuenta
    assert not [s for s in sentencias if "HASHTEXTEXTENDED" in s.upper()], sentencias
