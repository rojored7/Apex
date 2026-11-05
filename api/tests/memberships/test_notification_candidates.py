"""`memberships.service.notification_candidates` y `has_current_or_future` (S5-B7, US-124;
S5-D26, N-35, E7; G-04). # Rojo B7

`notification_candidates(session, on_dates) -> list[NotificationCandidate]`:
- cada membresía NO anulada ni pendiente de pago cuyo `end_date` está en `on_dates`, con
  `member_id` (aunque el socio esté dado de baja: `generate` lo filtra), `membership_id`,
  `end_date` y `plan_name`; ni el nombre del socio ni sus datos de contacto;
- las `active`, `expiring`, `frozen` y `expired` guardadas entran (la vencida es el caso de uso);
- orden `end_date, id`; sin fechas devuelve `[]` sin enviar ninguna sentencia;
- una sola sentencia sobre `memberships.memberships` para todas las fechas, sin JOIN a otro
  esquema (el nombre del plan sale de `plans.service.names_for`).

`has_current_or_future(session, member_ids, today) -> set[UUID]` (N-35: no se avisa como vencido a
quien renovó): los ids con una membresía no anulada cuyo estado EFECTIVO a `today` no es
`expired`, es decir vigente (`active`, `expiring`, `frozen`), futura o pendiente de pago (una venta
registrada cuenta como renovación). Una consulta por trozo de `ID_BATCH`; sin ids no consulta.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.core.pagination import ID_BATCH
from app.modules.memberships import service
from app.modules.memberships.schemas import NotificationCandidate
from tests.conftest import ContadorDeConsultas
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import TABLA_MEMBRESIAS

HOY = date(2026, 10, 21)
OTROS_ESQUEMAS = re.compile(r"\b(members|payments|plans|auth|settings)\.\w+")


async def _socio(session: AsyncSession, **cambios: object):  # type: ignore[no-untyped-def]
    return await make_member(session, document=unique_document(), phone=None, email=None, **cambios)


# notification_candidates -----------------------------------------------------------------------


async def test_devuelve_la_membresia_cuyo_fin_cae_en_la_fecha(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session, name="Trimestral")
    socio = await _socio(session)
    fin = HOY + timedelta(days=3)
    membresia = await make_membership(
        session, socio, plan, status="active", start=fin - timedelta(days=29), end=fin
    )

    candidatos = await service.notification_candidates(session, {fin})

    assert candidatos == [
        NotificationCandidate(
            member_id=socio.id, membership_id=membresia.id, end_date=fin, plan_name="Trimestral"
        )
    ]


async def test_solo_trae_las_fechas_pedidas_y_ordena_por_fin_e_id(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    d1, d2, d3 = HOY - timedelta(days=1), HOY, HOY + timedelta(days=3)
    esperadas = []
    for fin in (d3, d1, d2, d1):
        socio = await _socio(session)
        m = await make_membership(
            session, socio, plan, status="active", start=fin - timedelta(days=29), end=fin
        )
        esperadas.append((fin, m.id))
    otro = await _socio(session)
    await make_membership(
        session,
        otro,
        plan,
        status="active",
        start=HOY - timedelta(days=29),
        end=HOY + timedelta(days=9),
    )

    candidatos = await service.notification_candidates(session, [d1, d2])

    fines = [c.end_date for c in candidatos]
    assert fines == sorted(fines) and len(candidatos) == 3
    assert {c.membership_id for c in candidatos} == {i for f, i in esperadas if f in (d1, d2)}
    iguales = [c for c in candidatos if c.end_date == d1]
    assert [c.membership_id for c in iguales] == sorted(c.membership_id for c in iguales)


@pytest.mark.parametrize("estado", ["active", "expiring", "expired", "frozen"])
async def test_entran_las_membresias_vigentes_vencidas_o_congeladas(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring, estado: str
) -> None:
    plan = await make_plan(session)
    socio = await _socio(session)
    fin = HOY - timedelta(days=2)
    m = await make_membership(
        session, socio, plan, status=estado, start=fin - timedelta(days=29), end=fin
    )
    candidatos = await service.notification_candidates(session, {fin})
    assert [c.membership_id for c in candidatos] == [m.id]


@pytest.mark.parametrize("estado", ["cancelled", "pending_payment"])
async def test_no_entran_las_anuladas_ni_las_pendientes_de_pago(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring, estado: str
) -> None:
    plan = await make_plan(session)
    socio = await _socio(session)
    fin = HOY + timedelta(days=3)
    await make_membership(
        session, socio, plan, status=estado, start=fin - timedelta(days=29), end=fin
    )
    assert await service.notification_candidates(session, {fin}) == []


async def test_un_socio_dado_de_baja_sigue_siendo_candidato(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    """La baja no anula membresías (N-20): el filtro por `deleted_at` es de `generate`."""
    plan = await make_plan(session)
    socio = await _socio(session, deleted_at=reloj.now_utc())
    fin = HOY
    m = await make_membership(
        session, socio, plan, status="active", start=fin - timedelta(days=29), end=fin
    )
    assert [c.membership_id for c in await service.notification_candidates(session, {fin})] == [
        m.id
    ]


async def test_sin_fechas_o_sin_coincidencias_devuelve_lista_vacia(
    session: AsyncSession,
    reloj: FrozenClock,
    bus_listo: Keyring,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    plan = await make_plan(session)
    socio = await _socio(session)
    await make_membership(session, socio, plan, status="active", start=HOY, end=HOY)
    with contador_de_consultas.midiendo():
        assert await service.notification_candidates(session, set()) == []
        assert contador_de_consultas.sentencias == []
    assert await service.notification_candidates(session, {HOY + timedelta(days=100)}) == []


async def test_una_sola_sentencia_sobre_memberships_y_ningun_join_entre_esquemas(
    session: AsyncSession,
    reloj: FrozenClock,
    bus_listo: Keyring,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    plan = await make_plan(session)
    fechas = [HOY - timedelta(days=n) for n in (1, 7, 15)]
    for fin in fechas:
        socio = await _socio(session)
        await make_membership(
            session, socio, plan, status="active", start=fin - timedelta(days=29), end=fin
        )

    with contador_de_consultas.midiendo():
        candidatos = await service.notification_candidates(session, fechas)

    assert len(candidatos) == 3
    de_membresias = [sql for sql in contador_de_consultas.sentencias if TABLA_MEMBRESIAS in sql]
    assert len(de_membresias) == 1, contador_de_consultas.sentencias
    assert OTROS_ESQUEMAS.search(de_membresias[0]) is None, de_membresias[0]
    assert len(contador_de_consultas.sentencias) <= 2  # memberships + nombres de plan


async def test_acepta_cualquier_coleccion_de_fechas(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    socio = await _socio(session)
    m = await make_membership(session, socio, plan, status="active", start=HOY, end=HOY)
    for coleccion in ({HOY}, frozenset({HOY}), [HOY], (HOY,), [HOY, HOY]):
        candidatos = await service.notification_candidates(session, coleccion)
        assert [c.membership_id for c in candidatos] == [m.id]


# has_current_or_future -------------------------------------------------------------------------


async def test_quien_tiene_una_vigente_o_una_futura_ya_renovo(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    vigente = await _socio(session)
    await make_membership(
        session,
        vigente,
        plan,
        status="active",
        start=HOY - timedelta(days=5),
        end=HOY + timedelta(days=24),
    )
    vence_hoy = await _socio(session)
    await make_membership(
        session, vence_hoy, plan, status="expiring", start=HOY - timedelta(days=29), end=HOY
    )
    futura = await _socio(session)
    await make_membership(
        session,
        futura,
        plan,
        status="active",
        start=HOY + timedelta(days=5),
        end=HOY + timedelta(days=34),
    )

    ids = {vigente.id, vence_hoy.id, futura.id}
    assert await service.has_current_or_future(session, ids, HOY) == ids


async def test_quien_solo_tiene_vencidas_o_anuladas_no_renovo(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    vencida = await _socio(session)
    await make_membership(
        session,
        vencida,
        plan,
        status="expired",
        start=HOY - timedelta(days=40),
        end=HOY - timedelta(days=10),
    )
    anulada = await _socio(session)
    await make_membership(
        session,
        anulada,
        plan,
        status="cancelled",
        start=HOY - timedelta(days=5),
        end=HOY + timedelta(days=24),
    )
    sin_nada = await _socio(session)

    ids = {vencida.id, anulada.id, sin_nada.id}
    assert await service.has_current_or_future(session, ids, HOY) == set()


async def test_una_vieja_vencida_y_una_nueva_vigente_cuentan_como_renovado(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    socio = await _socio(session)
    await make_membership(
        session,
        socio,
        plan,
        status="expired",
        start=HOY - timedelta(days=40),
        end=HOY - timedelta(days=11),
    )
    await make_membership(
        session,
        socio,
        plan,
        status="active",
        start=HOY - timedelta(days=10),
        end=HOY + timedelta(days=19),
    )
    assert await service.has_current_or_future(session, [socio.id], HOY) == {socio.id}


async def test_una_venta_pendiente_de_pago_cuenta_como_renovacion(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    socio = await _socio(session)
    await make_membership(
        session,
        socio,
        plan,
        status="expired",
        start=HOY - timedelta(days=40),
        end=HOY - timedelta(days=11),
    )
    await make_membership(
        session, socio, plan, status="pending_payment", start=HOY - timedelta(days=10)
    )
    assert await service.has_current_or_future(session, {socio.id}, HOY) == {socio.id}


async def test_una_congelada_hoy_cuenta_como_vigente(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    socio = await _socio(session)
    m = await make_membership(
        session,
        socio,
        plan,
        status="active",
        start=HOY - timedelta(days=20),
        end=HOY + timedelta(days=15),
    )
    await make_freeze(session, m, HOY - timedelta(days=1), HOY + timedelta(days=5))
    assert await service.has_current_or_future(session, {socio.id}, HOY) == {socio.id}


async def test_el_estado_depende_de_la_fecha_pedida(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    """Estado por fecha (E7): la misma membresía es vigente el 21 y vencida el 15 de noviembre."""
    plan = await make_plan(session)
    socio = await _socio(session)
    await make_membership(
        session,
        socio,
        plan,
        status="active",
        start=HOY - timedelta(days=5),
        end=HOY + timedelta(days=24),
    )
    assert await service.has_current_or_future(session, {socio.id}, HOY) == {socio.id}
    assert (
        await service.has_current_or_future(session, {socio.id}, HOY + timedelta(days=30)) == set()
    )


async def test_ignora_ids_ajenos_y_sin_ids_no_consulta(
    session: AsyncSession,
    reloj: FrozenClock,
    bus_listo: Keyring,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    plan = await make_plan(session)
    socio = await _socio(session)
    otro = await _socio(session)
    await make_membership(
        session, otro, plan, status="active", start=HOY, end=HOY + timedelta(days=29)
    )
    with contador_de_consultas.midiendo():
        assert await service.has_current_or_future(session, set(), HOY) == set()
        assert contador_de_consultas.sentencias == []
    assert await service.has_current_or_future(session, {socio.id, uuid4()}, HOY) == set()


async def test_450_ids_van_en_lotes_de_id_batch(
    session: AsyncSession,
    reloj: FrozenClock,
    bus_listo: Keyring,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    ids = [uuid4() for _ in range(450)]
    with contador_de_consultas.midiendo():
        assert await service.has_current_or_future(session, ids, HOY) == set()
    assert contador_de_consultas.de(TABLA_MEMBRESIAS) == math.ceil(450 / ID_BATCH) == 3
    assert not any(OTROS_ESQUEMAS.search(s) for s in contador_de_consultas.sentencias)


def test_notification_candidate_es_inmutable_y_solo_lleva_ids_fechas_y_plan() -> None:
    campos = set(NotificationCandidate.__dataclass_fields__)
    assert campos == {"member_id", "membership_id", "end_date", "plan_name"}
    assert NotificationCandidate.__dataclass_params__.frozen  # type: ignore[attr-defined]
