"""`audit.service.recent` (S4A-B8, US-110; S4A-D28, S4A-D51, S4A-D61 b).

Cadena de la prueba (vaciada por `audit_chain_factory`, reloj en T0): las once filas de
`sembrar_actividad` (ver `test_member_history.py`) más seis que agrega `extras`:

  seq accion    tabla                       quien
   1  insert    auth.users                  Sistema (alta de ana)
   2  insert    auth.users                  Sistema (alta de juan)
   3  insert    plans.plans                 ana
   4  insert    members.members             ana   (socia Lucía)
   5  update    members.members             juan  (teléfono y correo)
   6  reveal    members.members             juan
   7  insert    memberships.memberships     ana   (venta)
   8  insert    payments.payments           juan  (pago 120.000)
   9  update    memberships.memberships     juan  (activa por cobertura)
  10  update    payments.payments           ana   (anula)
  11  update    memberships.memberships     ana   (revierte)
  12  login     auth.users                  ana
  13  reveal    members.members             ana
  14  verify    audit.verifications         ana
  15  export    members.members             ana
  16  download  members.members             ana
  17  insert    members.members             Sistema (`make_member`)

`recent(session, tables, limit, *, actions=("insert", "update", "delete"), exclude_user_ids=())`
devuelve `AuditEntryView` en `seq` descendente: una consulta por tabla (S4A-D51), unidas en
memoria y recortadas a `limit`; `tables` dentro de `RECENT_TABLES_ALLOWED` y `limit` de 1 a 50
(si no, `ValueError`); `before`/`after` reducidos a `diff.REDUCED_FIELDS`.

Los dos casos `perf` (100.000 lecturas más recientes que las escrituras: `recent` por debajo de
50 ms de mediana y `EXPLAIN` de la consulta por tabla por índice, sin `Seq Scan`; S4A-D115)
se corren aparte: `uv run pytest -m perf tests/audit/test_recent.py -q`.
"""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Mapping, Sequence
from dataclasses import fields
from typing import Any, Final
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.core.crypto.keyring import Keyring
from app.modules.audit.diff import REDUCED_FIELDS
from app.modules.audit.schemas import AuditEntryView
from tests.audit._apoyo import (
    CORREO_NUEVO,
    MOTIVO_ANULACION,
    TELEFONO_NUEVO,
    Actividad,
    sembrar_actividad,
)
from tests.audit.conftest import audit_service
from tests.conftest import ContadorDeConsultas, UsuarioPrueba
from tests.factories.members import KNOWN_NORMALIZED, make_member

SOCIOS: Final = "members.members"
MEMBRESIAS: Final = "memberships.memberships"
PAGOS: Final = "payments.payments"
NEGOCIO: Final = (SOCIOS, MEMBRESIAS, PAGOS)
SEIS: Final = (*NEGOCIO, "plans.plans", "auth.users", "settings.settings_sections")


@pytest.fixture
async def actividad(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
) -> Actividad:
    return await sembrar_actividad(session, ana=ana, juan=juan)


@pytest.fixture
async def extras(session: AsyncSession, actividad: Actividad, ana: UsuarioPrueba) -> Actividad:
    """Filas 12 a 17: cinco lecturas de ana por `audit.record` y un alta del sistema."""
    socia = actividad.member_id
    lecturas: Sequence[tuple[Any, str, UUID | None, dict[str, Any]]] = (
        ("login", "auth.users", ana.id, {"result": "ok"}),
        ("reveal", SOCIOS, socia, {"field": "document"}),
        ("verify", "audit.verifications", None, {"ok": True}),
        ("export", SOCIOS, None, {"rows": 1}),
        ("download", SOCIOS, socia, {"file": "x"}),
    )
    for accion, tabla, registro, after in lecturas:
        await record(
            session,
            action=accion,
            table_name=tabla,
            record_id=registro,
            before=None,
            after=after,
            user_id=ana.id,
            subject_member_id=socia if tabla == SOCIOS and registro == socia else None,
        )
    await session.commit()
    await make_member(session, document="9100000017", phone=None, email=None)
    return actividad


async def _seqs(
    session: AsyncSession, tablas: Sequence[str], limit: int = 50, **kw: Any
) -> list[int]:
    vistas = await audit_service.recent(session, tablas, limit, **kw)
    return [v.seq for v in vistas]


# Filtros: tablas, acciones y usuarios excluidos ----------------------------------------------


async def test_las_tres_tablas_de_negocio_solo_escrituras(
    session: AsyncSession, extras: Actividad
) -> None:
    """`reveal`, `login`, `export`, `verify` y `download` no salen; `plans` y `users` tampoco si
    no se piden."""
    assert await _seqs(session, NEGOCIO) == [17, 11, 10, 9, 8, 7, 5, 4]


async def test_plans_y_users_solo_si_se_piden(session: AsyncSession, extras: Actividad) -> None:
    assert await _seqs(session, (*NEGOCIO, "plans.plans")) == [17, 11, 10, 9, 8, 7, 5, 4, 3]
    assert await _seqs(session, ("auth.users",)) == [2, 1]
    assert await _seqs(session, SEIS) == [17, 11, 10, 9, 8, 7, 5, 4, 3, 2, 1]


async def test_excluye_al_sistema_antes_del_limite(
    session: AsyncSession, extras: Actividad
) -> None:
    assert await _seqs(session, NEGOCIO, exclude_user_ids=(SYSTEM_USER_ID,)) == [
        11,
        10,
        9,
        8,
        7,
        5,
        4,
    ]
    assert await _seqs(session, NEGOCIO, 3, exclude_user_ids=(SYSTEM_USER_ID,)) == [11, 10, 9]
    assert await _seqs(session, SEIS, 50, exclude_user_ids=(SYSTEM_USER_ID,)) == [
        11,
        10,
        9,
        8,
        7,
        5,
        4,
        3,
    ]


async def test_excluye_a_varios_usuarios(
    session: AsyncSession, extras: Actividad, ana: UsuarioPrueba
) -> None:
    assert await _seqs(session, NEGOCIO, exclude_user_ids=(SYSTEM_USER_ID, ana.id)) == [9, 8, 5]


async def test_filtra_por_acciones(session: AsyncSession, extras: Actividad) -> None:
    assert await _seqs(session, NEGOCIO, actions=("insert",)) == [17, 8, 7, 4]
    assert await _seqs(session, NEGOCIO, actions=("update",)) == [11, 10, 9, 5]
    assert await _seqs(session, NEGOCIO, actions=("delete",)) == []


async def test_respeta_limit_y_el_orden_global_por_seq(
    session: AsyncSession, extras: Actividad
) -> None:
    assert await _seqs(session, NEGOCIO, 1) == [17]
    assert await _seqs(session, NEGOCIO, 4) == [17, 11, 10, 9]
    assert await _seqs(session, (PAGOS, SOCIOS, MEMBRESIAS), 5) == [17, 11, 10, 9, 8]
    todas = await _seqs(session, SEIS)
    assert todas == sorted(todas, reverse=True)
    assert len(set(todas)) == len(todas)


async def test_cadena_vacia_da_lista_vacia(
    session: AsyncSession, audit_chain_factory: object
) -> None:
    assert await audit_service.recent(session, NEGOCIO, 10) == []


# Validación -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tablas",
    [
        ("crypto.crypto_keys",),
        ("crypto.crypto_ops",),
        ("audit.verifications",),
        ("audit.audit_log",),
        ("memberships.membership_freezes",),
        ("auth.one_time_tokens",),
        ("members",),
        (SOCIOS, "crypto.crypto_jobs"),
    ],
    ids=lambda t: "+".join(t),
)
async def test_rechaza_tablas_fuera_de_la_lista_blanca(
    session: AsyncSession, tablas: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError):
        await audit_service.recent(session, tablas, 10)


@pytest.mark.parametrize("limite", [0, -1, 51, 1000])
async def test_rechaza_limit_fuera_de_1_a_50(session: AsyncSession, limite: int) -> None:
    with pytest.raises(ValueError):
        await audit_service.recent(session, NEGOCIO, limite)


@pytest.mark.parametrize("limite", [1, 50])
async def test_acepta_los_bordes_de_limit(
    session: AsyncSession, audit_chain_factory: object, limite: int
) -> None:
    assert await audit_service.recent(session, NEGOCIO, limite) == []


def test_las_constantes_de_recent() -> None:
    assert audit_service.MAX_RECENT_LIMIT == 50
    assert frozenset(SEIS) == audit_service.RECENT_TABLES_ALLOWED


# Vista reducida -------------------------------------------------------------------------------


def _json(vistas: Sequence[AuditEntryView]) -> str:
    def plano(valor: object) -> object:
        if isinstance(valor, Mapping):
            return dict(valor)
        return str(valor)

    return json.dumps(
        [{f.name: getattr(v, f.name) for f in fields(v)} for v in vistas],
        default=plano,
        ensure_ascii=False,
    )


async def test_la_vista_reducida_no_lleva_blobs_reference_ni_void_reason(
    session: AsyncSession, extras: Actividad
) -> None:
    vistas = await audit_service.recent(session, SEIS, 50)
    assert vistas and all(isinstance(v, AuditEntryView) for v in vistas)
    for vista in vistas:
        assert set(vista.before or {}) <= REDUCED_FIELDS, vista.seq
        assert set(vista.after or {}) <= REDUCED_FIELDS, vista.seq
    texto = _json(vistas)
    for prohibido in (
        "apx1.",
        "reference",
        "void_reason",
        MOTIVO_ANULACION,
        TELEFONO_NUEVO,
        CORREO_NUEVO,
        "_idx",
        "password",
        *KNOWN_NORMALIZED,
    ):
        assert prohibido not in texto, prohibido


async def test_cada_vista_trae_la_cabecera_de_su_fila(
    session: AsyncSession, extras: Actividad, ana: UsuarioPrueba, juan: UsuarioPrueba
) -> None:
    vistas = {v.seq: v for v in await audit_service.recent(session, NEGOCIO, 50)}
    pago = vistas[8]
    assert (pago.action, pago.table_name, pago.user_id) == ("insert", PAGOS, juan.id)
    assert (pago.record_id, pago.subject_member_id) == (extras.payment_id, extras.member_id)
    assert dict(pago.after or {})["amount_cop"] == 120_000
    anula = vistas[10]
    assert (dict(anula.before or {}), dict(anula.after or {})) == (
        {"voided": False},
        {"voided": True},
    )
    activa = vistas[9]
    assert (dict(activa.before or {}), dict(activa.after or {})) == (
        {"status": "pending_payment"},
        {"status": "active"},
    )
    assert activa.record_id == extras.membership_id
    venta = vistas[7]
    assert (venta.user_id, venta.before) == (ana.id, None)
    assert dict(venta.after or {})["plan_id"] == str(extras.plan_id)
    edicion = vistas[5]
    assert (dict(edicion.before or {}), dict(edicion.after or {})) == ({}, {})


# Una consulta por tabla (S4A-D51) -------------------------------------------------------------


@pytest.mark.parametrize("tablas", [NEGOCIO, (SOCIOS,), SEIS], ids=["tres", "una", "seis"])
async def test_una_consulta_por_tabla(
    session: AsyncSession,
    extras: Actividad,
    contador_de_consultas: ContadorDeConsultas,
    tablas: tuple[str, ...],
) -> None:
    with contador_de_consultas.midiendo() as contador:
        await audit_service.recent(session, tablas, 10, exclude_user_ids=(SYSTEM_USER_ID,))
    assert len(contador.sentencias) == len(tablas), contador.sentencias
    assert contador.de("audit.audit_log") == len(tablas)


async def test_la_validacion_falla_antes_de_consultar(
    session: AsyncSession, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo() as contador:
        with pytest.raises(ValueError):
            await audit_service.recent(session, (SOCIOS, "crypto.crypto_keys"), 10)
        with pytest.raises(ValueError):
            await audit_service.recent(session, NEGOCIO, 51)
    assert contador.sentencias == []


# Rendimiento (S4A-D51, M-7): `perf`, fuera de los gates ---------------------------------------

NEGOCIO_POR_TABLA: Final = 1_000
LECTURAS: Final = 50_000
TOPE_MS: Final = 50
CONSULTA_POR_TABLA: Final = (
    "SELECT * FROM audit.audit_log WHERE table_name = :t AND action = ANY(:acciones) "
    "AND user_id <> ALL(:excluidos) ORDER BY seq DESC LIMIT :n"
)


@pytest.fixture
async def cien_mil_lecturas(
    audit_chain_factory: Any, reloj: FrozenClock, ana: UsuarioPrueba
) -> Any:
    """1.000 inserts por tabla de negocio y, DESPUÉS (más recientes), 50.000 `login` de
    `auth.users` y 50.000 `reveal` de `members.members`, todos de ana."""
    for tabla in NEGOCIO:
        await audit_chain_factory.make(NEGOCIO_POR_TABLA, table_name=tabla, user_id=ana.id)
    await audit_chain_factory.make(
        LECTURAS, table_name="auth.users", user_id=ana.id, action="login"
    )
    await audit_chain_factory.make(LECTURAS, table_name=SOCIOS, user_id=ana.id, action="reveal")
    await audit_chain_factory.session.execute(text("ANALYZE audit.audit_log"))
    return audit_chain_factory


@pytest.mark.perf
async def test_recent_baja_de_50_ms_con_100_mil_lecturas_recientes(
    session: AsyncSession, cien_mil_lecturas: Any
) -> None:
    excluidos = (SYSTEM_USER_ID,)
    await audit_service.recent(session, NEGOCIO, 10, exclude_user_ids=excluidos)  # calentamiento
    tiempos: list[float] = []
    for _ in range(5):
        inicio = time.perf_counter()
        vistas = await audit_service.recent(session, NEGOCIO, 10, exclude_user_ids=excluidos)
        tiempos.append((time.perf_counter() - inicio) * 1000)
    assert len(vistas) == 10
    assert all(v.action == "insert" for v in vistas)
    assert statistics.median(tiempos) < TOPE_MS, tiempos


@pytest.mark.perf
@pytest.mark.parametrize("tabla", NEGOCIO)
async def test_cada_consulta_por_tabla_va_por_indice_sin_seq_scan(
    session: AsyncSession, cien_mil_lecturas: Any, tabla: str
) -> None:
    """La forma de S4A-D51 (una tabla, `action = ANY`, `user_id <> ALL`, `seq DESC LIMIT`) va por
    índice y no barre la tabla.

    S4A-D115: con 50.000 `reveal` de `members.members` más recientes el planificador prefiere
    `uq_audit_log_seq` hacia atrás con filtro en vez de `ix_audit_log_table_seq` (el índice
    `(table_name, seq DESC)` no salta las lecturas de la misma tabla); el tiempo sigue por debajo
    de 50 ms. Se acepta cualquiera de los dos índices, nunca `Seq Scan`; el índice
    `(table_name, action, seq DESC)` queda como deuda del Sprint 4B junto a S4A-D106 c."""
    filas = await session.execute(
        text("EXPLAIN " + CONSULTA_POR_TABLA),
        {
            "t": tabla,
            "acciones": ["insert", "update", "delete"],
            "excluidos": [SYSTEM_USER_ID],
            "n": 10,
        },
    )
    plan = "\n".join(filas.scalars().all())
    assert "ix_audit_log_table_seq" in plan or "uq_audit_log_seq" in plan, plan
    assert "Seq Scan" not in plan, plan


SISTEMA_RECIENTE: Final = 5_000


@pytest.fixture
async def cinco_mil_del_sistema(
    audit_chain_factory: Any, reloj: FrozenClock, ana: UsuarioPrueba
) -> Any:
    """1.000 inserts de ana por tabla de negocio y, DESPUÉS, 5.000 escrituras del sistema en
    `memberships.memberships` (revisión de B8, LOW 3: `user_id <> ALL` descarta las filas más
    recientes de esa tabla antes de juntar 10)."""
    for tabla in NEGOCIO:
        await audit_chain_factory.make(NEGOCIO_POR_TABLA, table_name=tabla, user_id=ana.id)
    await audit_chain_factory.make(
        SISTEMA_RECIENTE, table_name=MEMBRESIAS, user_id=SYSTEM_USER_ID, action="update"
    )
    await audit_chain_factory.session.execute(text("ANALYZE audit.audit_log"))
    return audit_chain_factory


@pytest.mark.perf
async def test_recent_con_5_mil_escrituras_recientes_del_sistema_sin_seq_scan_y_bajo_50_ms(
    session: AsyncSession, cinco_mil_del_sistema: Any, ana: UsuarioPrueba
) -> None:
    """S4A-D115 (revisión de B8, LOW 3): el plan de `memberships.memberships` sigue por índice y
    `recent` de las tres tablas sigue por debajo de 50 ms aunque las 5.000 filas más recientes
    de esa tabla sean del sistema."""
    excluidos = (SYSTEM_USER_ID,)
    filas = await session.execute(
        text("EXPLAIN " + CONSULTA_POR_TABLA),
        {
            "t": MEMBRESIAS,
            "acciones": ["insert", "update", "delete"],
            "excluidos": [SYSTEM_USER_ID],
            "n": 10,
        },
    )
    plan = "\n".join(filas.scalars().all())
    assert "ix_audit_log_table_seq" in plan or "uq_audit_log_seq" in plan, plan
    assert "Seq Scan" not in plan, plan
    await audit_service.recent(session, NEGOCIO, 10, exclude_user_ids=excluidos)  # calentamiento
    tiempos: list[float] = []
    for _ in range(5):
        inicio = time.perf_counter()
        vistas = await audit_service.recent(session, NEGOCIO, 10, exclude_user_ids=excluidos)
        tiempos.append((time.perf_counter() - inicio) * 1000)
    assert len(vistas) == 10
    assert all(v.user_id == ana.id for v in vistas)
    assert statistics.median(tiempos) < TOPE_MS, tiempos
