"""Consultas de estado y resumen de membresías (S3-B7, US-092; D5, M-10, N-22, N-26, S3-D53,
S3-D60).

Hoy es 2026-10-21 (`reloj`), `expiring_days` 7. Escenario del BDD de US-092 (`gimnasio`), un
socio por membresía salvo Laura; planes "Mensual" (30 días) y "Trimestral" (90 días):
- 10 `active` (Mensual, del 2026-10-01 al 2026-10-31: faltan 10 días);
- 3 por vencer: 2 Mensual y 1 Trimestral `active` guardadas que terminan el 2026-10-26 (faltan 5);
- Laura Gómez: Mensual por vencer (del 2026-09-26 al 2026-10-26) y renovación Trimestral
  `pending_payment` del 2026-10-27 al 2027-01-24 → cuenta `expiring` y su plan es el Mensual;
- 4 vencidas (Mensual, del 2026-08-01 al 2026-08-31): 2 guardadas `active` (vencidas por fecha,
  sin job: D5) y 2 guardadas `expired`;
- 1 congelada: `active` del 2026-10-01 al 2026-11-15 con congelación del 20 al 23 de octubre;
- 2 `pending_payment` (Mensual, del 2026-10-21 al 2026-11-20);
- 1 socio sin membresías y 1 con solo una anulada (los dos `none`);
- 1 socio dado de baja con una `active` vigente: no entra al resumen.
Resumen esperado: 10, 4, 4, 1, 2; más 2 `none` = 23 socios vivos (US-092 criterio 7).

`count_active_by_plan` (N-22 sobre el estado efectivo): plan "Clases" con 2 `active`, 1
`pending_payment`, 5 vencidas (3 guardadas `expired` y 2 `active` guardadas cuyo fin pasó) y 1
anulada → 3; una congelada del mismo plan suma 1.

`members.service.active_ids` (S3-D60): `frozenset` de los no dados de baja (también los
`inactive`). `summary` con 2.500 socios vivos (sembrados con SQL) emite tres sentencias a
`memberships.memberships` (lotes de `SUMMARY_ID_BATCH` = 1.000) y suma lo mismo que con un solo
lote.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.core.crypto.keyring import Keyring
from app.modules.members import service as members_service
from app.modules.memberships import service
from app.modules.memberships import summary as cache_del_resumen
from app.modules.memberships.schemas import MemberMembership, MembershipSummaryOut
from tests.conftest import T0, ContadorDeConsultas
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import TABLA_MEMBRESIAS

HOY = date(2026, 10, 21)
POR_VENCER_FIN = date(2026, 10, 26)


async def _socio(session: AsyncSession, nombre: str, **cambios: Any) -> Any:
    datos: dict[str, Any] = {
        "first_name": nombre,
        "last_name": "Estado",
        "document": unique_document(),
        "phone": None,
        "email": None,
        **cambios,
    }
    return await make_member(session, **datos)


@dataclass(frozen=True)
class Gimnasio:
    mensual: UUID
    trimestral: UUID
    vivos: frozenset[UUID]
    por_estado: dict[str, set[UUID]]
    laura: UUID
    sin_membresias: UUID
    solo_anulada: UUID
    dado_de_baja: UUID


async def _varios(
    session: AsyncSession, n: int, plan: Any, etiqueta: str, **membresia: Any
) -> set[UUID]:
    ids: set[UUID] = set()
    for i in range(n):
        socio = await _socio(session, f"{etiqueta} {i}")
        await make_membership(session, socio, plan, **membresia)
        ids.add(socio.id)
    return ids


@pytest.fixture
async def gimnasio(session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock) -> Gimnasio:
    mensual = await make_plan(session, name="Mensual")
    trimestral = await make_plan(session, name="Trimestral", price_cop=300_000, duration_days=90)
    vigente = {"status": "active", "start": date(2026, 10, 1), "end": date(2026, 10, 31)}
    por_vencer = {"status": "active", "start": date(2026, 9, 26), "end": POR_VENCER_FIN}
    agosto = {"start": date(2026, 8, 1), "end": date(2026, 8, 31)}
    pendiente = {"status": "pending_payment", "start": HOY, "end": date(2026, 11, 20)}
    activos = await _varios(session, 10, mensual, "Activo", **vigente)
    vencer = await _varios(session, 2, mensual, "Vence", **por_vencer)
    vencer |= await _varios(
        session,
        1,
        trimestral,
        "VenceTri",
        status="active",
        start=date(2026, 7, 28),
        end=POR_VENCER_FIN,
    )
    laura = await make_member(session, first_name="Laura", last_name="Gómez")
    await make_membership(session, laura, mensual, **por_vencer)
    await make_membership(
        session,
        laura,
        trimestral,
        status="pending_payment",
        start=date(2026, 10, 27),
        end=date(2027, 1, 24),
    )
    vencidas = await _varios(session, 2, mensual, "VencidaActiva", status="active", **agosto)
    vencidas |= await _varios(session, 2, mensual, "VencidaGuardada", status="expired", **agosto)
    congelado = await _socio(session, "Congelado")
    hielo = await make_membership(
        session,
        congelado,
        mensual,
        status="active",
        start=date(2026, 10, 1),
        end=date(2026, 11, 15),
    )
    await make_freeze(session, hielo, date(2026, 10, 20), date(2026, 10, 23))
    pendientes = await _varios(session, 2, mensual, "Pendiente", **pendiente)
    sin_membresias = await _socio(session, "Nadie")
    solo_anulada = await _socio(session, "Anulada")
    await make_membership(session, solo_anulada, mensual, status="cancelled")
    baja = await _socio(session, "Baja", deleted_at=T0 - timedelta(days=1))
    await make_membership(session, baja, mensual, **vigente)
    por_estado = {
        "active": activos,
        "expiring": vencer | {laura.id},
        "expired": vencidas,
        "frozen": {congelado.id},
        "pending_payment": pendientes,
    }
    vivos = frozenset(set().union(*por_estado.values()) | {sin_membresias.id, solo_anulada.id})
    return Gimnasio(
        mensual=mensual.id,
        trimestral=trimestral.id,
        vivos=vivos,
        por_estado=por_estado,
        laura=laura.id,
        sin_membresias=sin_membresias.id,
        solo_anulada=solo_anulada.id,
        dado_de_baja=baja.id,
    )


# summary (US-092 criterios 1, 3, 4, 7; D5) --------------------------------------------------------


async def test_el_resumen_cuenta_socios_por_estado_resuelto(
    session: AsyncSession, gimnasio: Gimnasio
) -> None:
    resumen = await service.summary(session)
    assert resumen == MembershipSummaryOut(
        active=10, expiring=4, expired=4, frozen=1, pending_payment=2
    )


async def test_la_suma_del_resumen_mas_los_none_es_el_total_de_socios_vivos(
    session: AsyncSession, gimnasio: Gimnasio
) -> None:
    resumen = await service.summary(session)
    sin_estado = 2  # el socio sin membresías y el de solo una anulada
    assert sum(resumen.model_dump().values()) + sin_estado == len(gimnasio.vivos) == 23


async def test_el_resumen_usa_hoy_de_bogota_o_el_dia_pedido(
    session: AsyncSession, gimnasio: Gimnasio, reloj: FrozenClock
) -> None:
    """El 2026-10-27 (pasado como argumento o por el reloj): a las 10 vigentes les faltan 4 días
    (`expiring`); las 3 por vencer del 26 ya vencieron (`expired`, 4 + 3 = 7); Laura tiene su
    Mensual vencida y la renovación `pending_payment` (gana la pendiente: 2 + 1 = 3); la
    congelación del congelado terminó el 23 y le faltan 19 días (`active`)."""
    resumen = await service.summary(session, today=date(2026, 10, 27))
    assert resumen == MembershipSummaryOut(
        active=1, expiring=10, expired=7, frozen=0, pending_payment=3
    )
    reloj.set(T0 + timedelta(days=6))  # 2026-10-27 en Bogotá
    assert await service.summary(session) == resumen


async def test_un_socio_dado_de_baja_no_entra_al_resumen(
    session: AsyncSession, gimnasio: Gimnasio
) -> None:
    resumen = await service.summary(session)
    assert resumen.active == 10  # la vigente del dado de baja no suma
    assert gimnasio.dado_de_baja not in await members_service.active_ids(session)


async def test_una_active_guardada_vencida_cuenta_expired_sin_job(
    session: AsyncSession, gimnasio: Gimnasio
) -> None:
    filas = await session.execute(
        text(
            "SELECT status, count(*) FROM memberships.memberships "
            "WHERE end_date = :fin GROUP BY status"
        ),
        {"fin": date(2026, 8, 31)},
    )
    assert dict(filas.all()) == {"active": 2, "expired": 2}  # nadie cambió lo guardado
    assert (await service.summary(session)).expired == 4


# status_for (US-092 criterio 5) -------------------------------------------------------------------


async def test_status_for_da_estado_y_membresia_que_decide_y_omite_a_los_sin_membresias(
    session: AsyncSession, gimnasio: Gimnasio
) -> None:
    activo = next(iter(gimnasio.por_estado["active"]))
    estados = await service.status_for(
        session, [activo, gimnasio.laura, gimnasio.sin_membresias, gimnasio.solo_anulada]
    )
    assert set(estados) == {activo, gimnasio.laura}
    assert estados[gimnasio.laura] == MemberMembership(
        status="expiring", plan_id=gimnasio.mensual, plan_name="Mensual", end_date=POR_VENCER_FIN
    )
    assert estados[activo] == MemberMembership(
        status="active", plan_id=gimnasio.mensual, plan_name="Mensual", end_date=date(2026, 10, 31)
    )


async def test_status_for_sin_ids_no_consulta(
    session: AsyncSession, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        assert await service.status_for(session, []) == {}
    assert contador_de_consultas.sentencias == []


async def test_status_for_de_200_ids_emite_una_sola_consulta_de_membresias(
    session: AsyncSession, gimnasio: Gimnasio, contador_de_consultas: ContadorDeConsultas
) -> None:
    ids = list(gimnasio.vivos) + [uuid4() for _ in range(200 - len(gimnasio.vivos))]
    assert len(ids) == 200
    with contador_de_consultas.midiendo():
        estados = await service.status_for(session, ids)
    assert set(estados) == gimnasio.vivos - {gimnasio.sin_membresias, gimnasio.solo_anulada}
    assert contador_de_consultas.de(TABLA_MEMBRESIAS) == 1
    assert contador_de_consultas.de("plans.plans") <= 1


async def test_status_for_de_201_ids_parte_en_dos_lotes(
    session: AsyncSession, gimnasio: Gimnasio, contador_de_consultas: ContadorDeConsultas
) -> None:
    ids = list(gimnasio.vivos) + [uuid4() for _ in range(201 - len(gimnasio.vivos))]
    with contador_de_consultas.midiendo():
        await service.status_for(session, ids)
    assert contador_de_consultas.de(TABLA_MEMBRESIAS) == 2


# member_ids_by_status (contrato de US-071) --------------------------------------------------------


async def test_member_ids_by_status_por_estado_y_plan_de_la_membresia_que_decide(
    session: AsyncSession, gimnasio: Gimnasio
) -> None:
    vencer = gimnasio.por_estado["expiring"]
    assert await service.member_ids_by_status(session, {"expiring"}) == vencer
    mensual = await service.member_ids_by_status(session, {"expiring"}, gimnasio.mensual)
    assert len(mensual) == 3 and gimnasio.laura in mensual
    trimestral = await service.member_ids_by_status(session, {"expiring"}, gimnasio.trimestral)
    assert len(trimestral) == 1 and gimnasio.laura not in trimestral
    # La renovación Trimestral de Laura no decide su estado: no cuenta como pendiente.
    pendientes = await service.member_ids_by_status(
        session, {"pending_payment"}, gimnasio.trimestral
    )
    assert pendientes == set()


async def test_member_ids_by_status_con_varios_estados(
    session: AsyncSession, gimnasio: Gimnasio
) -> None:
    obtenidos = await service.member_ids_by_status(session, {"frozen", "pending_payment"})
    assert obtenidos == gimnasio.por_estado["frozen"] | gimnasio.por_estado["pending_payment"]
    assert await service.member_ids_by_status(session, set()) == set()


# count_active_by_plan (N-22 sobre D5) -------------------------------------------------------------


async def test_count_active_by_plan_cuenta_pendientes_y_vigentes_por_estado_efectivo(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    clases = await make_plan(session, name="Clases", kind="classes", class_count=12)
    otro = await make_plan(session, name="Otro")
    agosto = {"start": date(2026, 8, 1), "end": date(2026, 8, 31)}
    await _varios(session, 2, clases, "Act", status="active")
    await _varios(session, 1, clases, "Pend", status="pending_payment")
    await _varios(session, 3, clases, "Venc", status="expired", **agosto)
    await _varios(session, 2, clases, "VencAct", status="active", **agosto)
    await _varios(session, 1, clases, "Anul", status="cancelled")
    await _varios(session, 4, otro, "Otro", status="active")
    assert await service.count_active_by_plan(session, clases.id) == 3
    congelado = await _socio(session, "Hielo")
    hielo = await make_membership(
        session, congelado, clases, status="active", start=date(2026, 10, 1), end=date(2026, 11, 15)
    )
    await make_freeze(session, hielo, date(2026, 10, 20), date(2026, 10, 23))
    assert await service.count_active_by_plan(session, clases.id) == 4
    assert await service.count_active_by_plan(session, uuid4()) == 0


# members.service.active_ids (S3-D60) -------------------------------------------------------------


async def test_active_ids_da_un_frozenset_de_los_no_dados_de_baja(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    vivo = await _socio(session, "Vivo")
    inactivo = await _socio(session, "Inactivo", status="inactive")
    baja = await _socio(session, "Baja", deleted_at=T0 - timedelta(days=1))
    ids = await members_service.active_ids(session)
    assert isinstance(ids, frozenset)
    assert ids == {vivo.id, inactivo.id}
    assert baja.id not in ids


async def test_active_ids_emite_una_sola_consulta_y_no_descifra(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    await _socio(session, "Uno")
    await _socio(session, "Dos")
    with contador_de_consultas.midiendo():
        assert len(await members_service.active_ids(session)) == 2
    assert len(contador_de_consultas.sentencias) == 1
    decrypts = await session.scalar(
        text("SELECT count(*) FROM crypto.crypto_ops WHERE verb = 'decrypt'")
    )
    assert decrypts == 0


# Resumen por lotes (S3-D60) ---------------------------------------------------------------------

_SOCIOS_EN_LOTE = text(
    "INSERT INTO members.members (id, first_name, last_name, status, document_type, document, "
    "document_idx, created_by) "
    "SELECT gen_random_uuid(), 'Carga', :apellido, 'active', 'CC', 'apx1.prueba.A256GCM.x.x', "
    "'carga-' || :apellido || '-' || i, :actor FROM generate_series(1, :n) AS i"
)
_MEMBRESIAS_EN_LOTE = text(
    "INSERT INTO memberships.memberships (id, member_id, plan_id, agreed_price_cop, start_date, "
    "end_date, status, created_by) "
    "SELECT gen_random_uuid(), m.id, :plan, 120000, :inicio, :fin, :estado, :actor "
    "FROM members.members m WHERE m.last_name = :apellido"
)


async def _sembrar_lote(
    session: AsyncSession, plan: UUID, apellido: str, n: int, estado: str | None
) -> None:
    """`n` socios vivos con SQL (sin cifrar de verdad: el resumen nunca lee los blobs) y, si hay
    `estado`, una membresía de cada uno del 2026-10-01 al 2026-10-31."""
    await session.execute(_SOCIOS_EN_LOTE, {"apellido": apellido, "n": n, "actor": SYSTEM_USER_ID})
    if estado is not None:
        await session.execute(
            _MEMBRESIAS_EN_LOTE,
            {
                "plan": plan,
                "inicio": date(2026, 10, 1),
                "fin": date(2026, 10, 31),
                "estado": estado,
                "actor": SYSTEM_USER_ID,
                "apellido": apellido,
            },
        )


async def test_el_resumen_de_2500_socios_va_en_tres_lotes_y_suma_igual_que_uno(
    session: AsyncSession,
    reloj: FrozenClock,
    contador_de_consultas: ContadorDeConsultas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = await make_plan(session, name="Lotes")
    await _sembrar_lote(session, plan.id, "Lote A", 1500, "active")
    await _sembrar_lote(session, plan.id, "Lote B", 700, "pending_payment")
    await _sembrar_lote(session, plan.id, "Lote C", 300, None)
    assert cache_del_resumen.SUMMARY_ID_BATCH == 1000
    esperado = MembershipSummaryOut(
        active=1500, expiring=0, expired=0, frozen=0, pending_payment=700
    )
    with contador_de_consultas.midiendo():
        en_lotes = await service.summary(session)
    assert en_lotes == esperado
    assert contador_de_consultas.de(TABLA_MEMBRESIAS) == 3
    assert contador_de_consultas.de("members.members") == 1  # `active_ids`, una vez
    monkeypatch.setattr(cache_del_resumen, "SUMMARY_ID_BATCH", 10_000)
    with contador_de_consultas.midiendo():
        de_una_vez = await service.summary(session)
    assert de_una_vez == en_lotes
    assert contador_de_consultas.de(TABLA_MEMBRESIAS) == 1


async def test_sin_socios_el_resumen_es_cero_sin_consultar_membresias(
    session: AsyncSession, reloj: FrozenClock, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        resumen = await service.summary(session)
    assert resumen == MembershipSummaryOut(
        active=0, expiring=0, expired=0, frozen=0, pending_payment=0
    )
    assert contador_de_consultas.de(TABLA_MEMBRESIAS) == 0
