"""Job diario de vencimientos y recálculo de la columna `status` (S4A-B2, US-094; S4A-D1, S4A-D2,
S4A-D48, S4A-D57; enmienda E2).

Base real con commit (`session_factory` del worker: una transacción por socio), bus de cifrado
confirmado (`bus_confirmado`, para crear socios), caché del resumen apagada
(`sin_cache_de_resumen`) y `reloj_worker` (`2026-10-21T15:00Z`, hoy 21 de octubre en Bogotá). El
recálculo corre bajo `actor_scope(SYSTEM_USER_ID)` como lo pone el runner; los casos del job
pasan por `runner.run_job` con el `JobSpec` real de `JOBS`.

Reglas (`rules.compute_status`, `expiring_days` 7 por defecto): `expiring` si
`end_date - hoy <= expiring_days`; `expired` si `hoy > end_date`; `frozen` si una congelación
contiene hoy. Una membresía `active` del 1 al 31 de octubre está `active` el 23 (faltan 8),
`expiring` el 24 (faltan 7) y `expired` el 1 de noviembre.
"""

from __future__ import annotations

import logging
import time
from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import events
from app.core.audit import AuditEntry
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.jobs import DETAIL_KEYS, JobRun
from app.core.locks import lock_member
from app.modules.memberships import service as memberships_service
from app.modules.memberships.models import Membership, MembershipFreeze
from app.modules.memberships.rules import FreezeWindow, compute_status, snapshot
from app.modules.memberships.service import (
    MembershipExpired,
    MembershipExpiring,
    RecomputeSummary,
)
from app.worker import runner
from app.worker.jobs import JOBS
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import (
    make_freeze,
    make_membership,
    make_memberships_para_recalculo,
)
from tests.factories.plans import make_plan
from tests.memberships._apoyo import guardar_politica
from tests.memberships.conftest import bus_confirmado, sin_cache_de_resumen  # noqa: F401

Fabrica = async_sessionmaker[AsyncSession]
HOY = date(2026, 10, 21)
OCT_1 = date(2026, 10, 1)
OCT_24 = date(2026, 10, 24)
OCT_31 = date(2026, 10, 31)
NOV_1 = date(2026, 11, 1)
NOV_30 = date(2026, 11, 30)
CANDIDATOS = frozenset({"active", "expiring", "frozen"})

pytestmark = pytest.mark.usefixtures("bus_confirmado", "reloj_worker")


# Apoyo ----


async def _membresia(
    fabrica: Fabrica, *, status: str, start: date = OCT_1, end: date = OCT_31, **socio: Any
) -> Membership:
    """Un socio nuevo con una membresía guardada con `status` (`start`, `end`)."""
    async with fabrica() as sesion:
        miembro = await make_member(sesion, **{"document": unique_document(), **socio})
        plan = await make_plan(sesion, name=f"Plan {miembro.id}")
        return await make_membership(sesion, miembro, plan, status=status, start=start, end=end)


async def _recalcular(fabrica: Fabrica, hoy: date, **opciones: Any) -> RecomputeSummary:
    with actor_scope(SYSTEM_USER_ID):
        return await memberships_service.recompute_statuses(fabrica, today=hoy, **opciones)


async def _estado(fabrica: Fabrica, membership_id: UUID) -> str:
    async with fabrica() as sesion:
        estado = await sesion.scalar(
            select(Membership.status).where(Membership.id == membership_id)
        )
    assert estado is not None
    return estado


async def _updates(fabrica: Fabrica, membership_id: UUID) -> list[AuditEntry]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(
            select(AuditEntry)
            .where(
                AuditEntry.table_name == "memberships.memberships",
                AuditEntry.action == "update",
                AuditEntry.record_id == membership_id,
            )
            .order_by(AuditEntry.seq)
        )
        return list(filas)


async def _corridas(fabrica: Fabrica) -> list[JobRun]:
    async with fabrica() as sesion:
        return list((await sesion.scalars(select(JobRun).order_by(JobRun.job_name))).all())


def _resumen(**conteos: int) -> dict[str, int]:
    return asdict(RecomputeSummary(**conteos))


# Transiciones con su evento ----


async def test_el_24_una_active_que_vence_el_31_pasa_a_expiring_con_un_evento(
    session_factory: Fabrica, capturar_eventos: Any
) -> None:
    recibidos = capturar_eventos(MembershipExpiring, MembershipExpired)
    membresia = await _membresia(session_factory, status="active")

    resumen = await _recalcular(session_factory, OCT_24)

    assert await _estado(session_factory, membresia.id) == "expiring"
    assert asdict(resumen) == _resumen(revisados=1, cambiadas=1, por_vencer=1)
    assert recibidos == [
        MembershipExpiring(
            membership_id=membresia.id,
            member_id=membresia.member_id,
            end_date=OCT_31,
            on_date=OCT_24,
            occurred_at=recibidos[0].occurred_at,
        )
    ]


async def test_el_23_la_misma_membresia_sigue_active_y_no_es_candidata(
    session_factory: Fabrica, capturar_eventos: Any
) -> None:
    recibidos = capturar_eventos(MembershipExpiring, MembershipExpired)
    membresia = await _membresia(session_factory, status="active")

    resumen = await _recalcular(session_factory, date(2026, 10, 23))

    assert await _estado(session_factory, membresia.id) == "active"
    assert asdict(resumen) == _resumen()
    assert recibidos == []


async def test_el_1_de_noviembre_una_expiring_pasa_a_expired_con_un_evento(
    session_factory: Fabrica, capturar_eventos: Any
) -> None:
    recibidos = capturar_eventos(MembershipExpiring, MembershipExpired)
    membresia = await _membresia(session_factory, status="expiring")

    resumen = await _recalcular(session_factory, NOV_1)

    assert await _estado(session_factory, membresia.id) == "expired"
    assert asdict(resumen) == _resumen(revisados=1, cambiadas=1, vencidas=1)
    assert [type(e) for e in recibidos] == [MembershipExpired]
    assert (recibidos[0].membership_id, recibidos[0].member_id) == (
        membresia.id,
        membresia.member_id,
    )
    assert (recibidos[0].end_date, recibidos[0].on_date) == (OCT_31, NOV_1)


async def test_dos_corridas_el_mismo_dia_dan_un_evento_y_una_fila_update(
    session_factory: Fabrica, capturar_eventos: Any
) -> None:
    recibidos = capturar_eventos(MembershipExpiring, MembershipExpired)
    membresia = await _membresia(session_factory, status="active")

    primera = await _recalcular(session_factory, OCT_24)
    segunda = await _recalcular(session_factory, OCT_24)

    assert primera.cambiadas == 1
    assert asdict(segunda) == _resumen()
    assert len(recibidos) == 1
    assert len(await _updates(session_factory, membresia.id)) == 1


async def test_una_active_vencida_hace_tres_dias_emite_solo_expired(
    session_factory: Fabrica, capturar_eventos: Any
) -> None:
    recibidos = capturar_eventos(MembershipExpiring, MembershipExpired)
    membresia = await _membresia(session_factory, status="active")

    resumen = await _recalcular(session_factory, date(2026, 11, 3))

    assert await _estado(session_factory, membresia.id) == "expired"
    assert [type(e) for e in recibidos] == [MembershipExpired]
    assert (resumen.por_vencer, resumen.vencidas, resumen.cambiadas) == (0, 1, 1)


# Congelaciones ----


async def test_una_congelacion_que_empieza_hoy_deja_frozen_sin_evento(
    session_factory: Fabrica, capturar_eventos: Any
) -> None:
    recibidos = capturar_eventos(MembershipExpiring, MembershipExpired)
    membresia = await _membresia(session_factory, status="active", end=NOV_30)
    async with session_factory() as sesion:
        await make_freeze(sesion, membresia, OCT_24, date(2026, 10, 28))

    resumen = await _recalcular(session_factory, OCT_24)

    assert await _estado(session_factory, membresia.id) == "frozen"
    assert asdict(resumen) == _resumen(revisados=1, cambiadas=1, otras=1)
    assert recibidos == []


@pytest.mark.parametrize(
    ("fin", "esperado", "eventos"),
    [(NOV_30, "active", []), (date(2026, 10, 29), "expiring", [MembershipExpiring])],
)
async def test_una_congelacion_que_termino_ayer_vuelve_a_active_o_expiring_segun_el_fin(
    session_factory: Fabrica,
    capturar_eventos: Any,
    fin: date,
    esperado: str,
    eventos: list[type[Any]],
) -> None:
    recibidos = capturar_eventos(MembershipExpiring, MembershipExpired)
    membresia = await _membresia(session_factory, status="frozen", end=fin)
    async with session_factory() as sesion:
        await make_freeze(sesion, membresia, date(2026, 10, 20), date(2026, 10, 23))

    resumen = await _recalcular(session_factory, OCT_24)

    assert await _estado(session_factory, membresia.id) == esperado
    assert [type(e) for e in recibidos] == eventos
    assert resumen.cambiadas == 1


# Lo que el recálculo nunca toca ----


@pytest.mark.parametrize(
    ("guardado", "fin"),
    [
        ("pending_payment", date(2026, 10, 10)),
        ("cancelled", date(2026, 10, 10)),
        ("expired", NOV_30),
    ],
)
async def test_pending_payment_cancelled_y_expired_guardados_quedan_intactos(
    session_factory: Fabrica, capturar_eventos: Any, guardado: str, fin: date
) -> None:
    recibidos = capturar_eventos(MembershipExpiring, MembershipExpired)
    membresia = await _membresia(session_factory, status=guardado, end=fin)

    resumen = await _recalcular(session_factory, OCT_24)

    assert await _estado(session_factory, membresia.id) == guardado
    assert asdict(resumen) == _resumen()
    assert recibidos == []
    assert await _updates(session_factory, membresia.id) == []


# El día de Bogotá, la auditoría y la política ----


async def test_a_las_2_utc_del_1_de_noviembre_sigue_siendo_31_en_bogota(
    session_factory: Fabrica, capturar_eventos: Any
) -> None:
    """`2026-11-01T02:00Z` son las 21:00 del 31 de octubre en Bogotá: el job corre con hoy 31, la
    membresía que vence el 31 queda `expiring` (no `expired`)."""
    recibidos = capturar_eventos(MembershipExpiring, MembershipExpired)
    membresia = await _membresia(session_factory, status="active")
    reloj = FrozenClock(datetime(2026, 11, 1, 2, 0, tzinfo=UTC))

    salida = await runner.run_job(JOBS[0], clock=reloj, session_factory=session_factory)

    assert (salida.run_date, salida.result) == (OCT_31, "ok")
    assert await _estado(session_factory, membresia.id) == "expiring"
    assert [(type(e), e.on_date) for e in recibidos] == [(MembershipExpiring, OCT_31)]


async def test_la_auditoria_va_con_el_usuario_del_sistema_y_el_socio(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    membresia = await _membresia(session_factory, status="active", end=date(2026, 10, 25))

    salida = await runner.run_job(JOBS[0], clock=reloj_worker, session_factory=session_factory)

    assert (salida.run_date, salida.result) == (HOY, "ok")
    [fila] = await _updates(session_factory, membresia.id)
    assert fila.user_id == SYSTEM_USER_ID
    assert fila.subject_member_id == membresia.member_id
    assert await _estado(session_factory, membresia.id) == "expiring"


async def test_expiring_days_sale_de_settings(session_factory: Fabrica) -> None:
    async with session_factory() as sesion:
        await guardar_politica(sesion, expiring_days=3)
    membresia = await _membresia(session_factory, status="active")

    antes = await _recalcular(session_factory, OCT_24)  # faltan 7 > 3: sigue active
    assert asdict(antes) == _resumen()
    assert await _estado(session_factory, membresia.id) == "active"

    despues = await _recalcular(session_factory, date(2026, 10, 28))  # faltan 3
    assert despues.por_vencer == 1
    assert await _estado(session_factory, membresia.id) == "expiring"


# Paridad, resumen y suscriptores ----


async def _ventanas(fabrica: Fabrica) -> dict[UUID, list[FreezeWindow]]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(select(MembershipFreeze))
        salida: dict[UUID, list[FreezeWindow]] = {}
        for fila in filas:
            salida.setdefault(fila.membership_id, []).append(
                FreezeWindow(fila.frozen_from, fila.frozen_to)
            )
        return salida


async def test_tras_el_job_el_estado_guardado_es_el_efectivo_en_toda_candidata(
    session_factory: Fabrica,
) -> None:
    async with session_factory() as sesion:
        await make_memberships_para_recalculo(sesion, n_socios=6, por_socio=3, hoy=HOY)
    congelada = await _membresia(session_factory, status="active", end=NOV_30)
    async with session_factory() as sesion:
        await make_freeze(sesion, congelada, date(2026, 10, 20), date(2026, 10, 22))

    resumen = await _recalcular(session_factory, HOY)

    # 6 socios con 2 vencidas cada uno (las vigentes faltan 25 a 30 días) y la congelada.
    assert asdict(resumen) == _resumen(revisados=7, cambiadas=13, vencidas=12, otras=1)
    ventanas = await _ventanas(session_factory)
    async with session_factory() as sesion:
        filas = list(await sesion.scalars(select(Membership)))
    assert len(filas) == 19
    for fila in filas:
        assert fila.status in CANDIDATOS | {"expired"}
        efectivo = compute_status(snapshot(fila), HOY, 7, ventanas.get(fila.id, []))
        assert fila.status == efectivo.value, (fila.start_date, fila.end_date, fila.status)


async def test_el_resumen_de_membresias_no_cambia_con_el_job(session_factory: Fabrica) -> None:
    async with session_factory() as sesion:
        await make_memberships_para_recalculo(sesion, n_socios=4, por_socio=2, hoy=HOY)
    await _membresia(session_factory, status="active", end=date(2026, 10, 25))
    async with session_factory() as sesion:
        antes = await memberships_service.summary(sesion, today=HOY)

    resumen = await _recalcular(session_factory, HOY)

    assert resumen.cambiadas > 0
    async with session_factory() as sesion:
        despues = await memberships_service.summary(sesion, today=HOY)
    assert despues == antes


def test_los_eventos_de_transicion_no_tienen_suscriptores() -> None:
    """S4A-D1: ni Notifications (Sprint 5) ni `_mark_summary_dirty`."""
    assert events.subscribers_for(MembershipExpiring) == ()
    assert events.subscribers_for(MembershipExpired) == ()


# Error de un socio y ocupación ----


def _texto(registro: logging.LogRecord) -> str:
    return f"{registro.getMessage()} {registro.__dict__}"


async def test_un_socio_que_falla_no_detiene_a_los_demas_y_el_log_no_trae_datos(
    session_factory: Fabrica, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    documento = unique_document()
    membresias = [await _membresia(session_factory, status="active") for _ in range(2)]
    fallida = await _membresia(
        session_factory, status="active", document=documento, first_name="Hermenegilda"
    )

    async def lanza(evento: MembershipExpiring, sesion: AsyncSession) -> None:
        if evento.member_id == fallida.member_id:
            raise RuntimeError(f"documento {documento} de Hermenegilda")

    events.subscribe(MembershipExpiring, lanza)  # `restaurar_bus` lo quita al salir

    resumen = await _recalcular(session_factory, OCT_24, page_size=2)

    assert asdict(resumen) == _resumen(revisados=3, cambiadas=2, por_vencer=2, errores=1)
    assert await _estado(session_factory, fallida.id) == "active"
    for membresia in membresias:
        assert await _estado(session_factory, membresia.id) == "expiring"
    textos = [_texto(r) for r in caplog.records]
    assert any("RuntimeError" in t for t in textos), "el error se registra con su tipo"
    for prohibido in (documento, "Hermenegilda", str(fallida.member_id), str(fallida.id)):
        assert not [t for t in textos if prohibido in t], prohibido


async def test_un_socio_ocupado_se_omite_tras_los_reintentos_y_el_ciclo_sigue(
    session_factory: Fabrica, migrated_database: str
) -> None:
    ocupada = await _membresia(session_factory, status="active")
    libre = await _membresia(session_factory, status="active")
    motor = create_async_engine(
        migrated_database,
        hide_parameters=True,
        connect_args={"server_settings": {"lock_timeout": "200ms"}},
    )
    impaciente = async_sessionmaker(motor, expire_on_commit=False)
    try:
        async with session_factory() as sostiene, sostiene.begin():
            await lock_member(sostiene, ocupada.member_id)
            inicio = time.monotonic()
            resumen = await _recalcular(impaciente, OCT_24)
            transcurrido = time.monotonic() - inicio
    finally:
        await motor.dispose()

    assert asdict(resumen) == _resumen(revisados=2, cambiadas=1, por_vencer=1, busy_omitidos=1)
    assert transcurrido >= 1.5, "dos reintentos con esperas de 0,5 s y 1 s"
    assert await _estado(session_factory, ocupada.id) == "active"
    assert await _estado(session_factory, libre.id) == "expiring"
    segunda = await _recalcular(
        session_factory, OCT_24
    )  # liberado: la corrida siguiente lo arregla
    assert asdict(segunda) == _resumen(revisados=1, cambiadas=1, por_vencer=1)


# Forma del resumen (E2) y el job ----


def test_recompute_summary_es_congelado_de_enteros_con_claves_de_detail_keys() -> None:
    resumen = RecomputeSummary(revisados=3, cambiadas=2, por_vencer=1, vencidas=1, errores=1)
    datos = asdict(resumen)
    assert set(datos) == {
        "revisados",
        "cambiadas",
        "por_vencer",
        "vencidas",
        "otras",
        "busy_omitidos",
        "errores",
    }
    assert set(datos) <= DETAIL_KEYS
    assert all(type(valor) is int for valor in datos.values())
    with pytest.raises(FrozenInstanceError):
        resumen.revisados = 9  # type: ignore[misc]


async def test_el_resumen_real_solo_trae_enteros(session_factory: Fabrica) -> None:
    await _membresia(session_factory, status="active")
    resumen = await _recalcular(session_factory, OCT_24)
    datos = asdict(resumen)
    assert set(datos) <= DETAIL_KEYS
    assert all(type(valor) is int for valor in datos.values())


async def test_el_job_devuelve_ok_con_los_conteos_en_details(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    await _membresia(session_factory, status="active", end=date(2026, 10, 25))

    salida = await runner.run_job(JOBS[0], clock=reloj_worker, session_factory=session_factory)

    assert salida.result == "ok"
    assert salida.details == _resumen(revisados=1, cambiadas=1, por_vencer=1)
    [corrida] = await _corridas(session_factory)
    assert (corrida.job_name, corrida.run_date, corrida.result) == ("expirations", HOY, "ok")
    assert corrida.details["revisados"] == 1
    assert "placeholder_ok" not in corrida.details


async def test_el_job_con_un_error_de_socio_termina_en_error_con_los_conteos(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    membresia = await _membresia(session_factory, status="active", end=date(2026, 10, 25))

    async def lanza(evento: MembershipExpiring, sesion: AsyncSession) -> None:
        raise RuntimeError("falla de prueba")

    events.subscribe(MembershipExpiring, lanza)

    salida = await runner.run_job(JOBS[0], clock=reloj_worker, session_factory=session_factory)

    assert salida.result == "error"
    assert salida.details["errores"] == 1
    assert await _estado(session_factory, membresia.id) == "active"


async def test_simulado_reclama_expirations_sim_y_no_la_fila_real(session_factory: Fabrica) -> None:
    membresia = await _membresia(session_factory, status="active")
    reloj = FrozenClock(datetime(2026, 11, 1, 17, 0, tzinfo=UTC))  # 12:00 de Bogotá

    salida = await runner.run_job(
        JOBS[0], clock=reloj, session_factory=session_factory, simulated=True
    )

    assert (salida.job_name, salida.run_date, salida.result) == ("expirations_sim", NOV_1, "ok")
    corridas = await _corridas(session_factory)
    assert [(c.job_name, c.run_date) for c in corridas] == [("expirations_sim", NOV_1)]
    assert corridas[0].details["vencidas"] == 1
    assert await _estado(session_factory, membresia.id) == "expired"


# Rendimiento (no es gate; S2-D27) ----


@pytest.mark.perf
async def test_mil_socios_y_tres_mil_membresias_en_menos_de_60_segundos(
    session_factory: Fabrica,
) -> None:
    async with session_factory() as sesion:
        await make_memberships_para_recalculo(sesion, n_socios=1000, por_socio=3, hoy=HOY)

    inicio = time.monotonic()
    resumen = await _recalcular(session_factory, HOY)
    transcurrido = time.monotonic() - inicio

    assert resumen.revisados == 1000
    assert resumen.vencidas == 2000
    assert resumen.busy_omitidos == resumen.errores == 0
    assert transcurrido < 60, transcurrido
