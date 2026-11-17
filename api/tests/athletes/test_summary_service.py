"""`athletes.service.summary` con PostgreSQL real (S9-C2, US-184 CA1 y CA3; S9-D16, S9-D27). Rojo.

- Fecha de la última medición y número de mediciones VIGENTES (las anuladas no cuentan, tampoco
  para la fecha).
- `current_rms` = movimientos con RM vigente (igual al `total` de `list_rms`); `recent_records`:
  los tres vigentes más recientes con `is_current` y nombres del catálogo.
- `benchmarks_with_attempts`: benchmarks con intentos vigentes y validados (igual al `total` de
  `list_benchmarks`); un resultado anulado no cuenta.
- NO descifra: sin filas nuevas en `crypto_ops`, sin `reveal` ni auditoría, y funciona con el
  keyring sin cargar (custodio sellado).
- A lo sumo seis consultas en el caso completo; socio dado de baja se lee; 404 si no existe.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.crypto import types
from app.core.crypto.keyring import configure_keyring
from app.core.pagination import PageParams
from app.modules.athletes import reads, service
from app.modules.members.exceptions import MemberNotFound
from app.modules.results.schemas import VoidIn
from app.modules.results.service import void_result
from tests.athletes._apoyo_derivar import AlertasCapturadas
from tests.factories.athletes import make_metric, make_record
from tests.factories.members import make_members
from tests.factories.triggers import disable_user_sql
from tests.factories.wods import make_benchmark, make_movement, make_wod
from tests.results._apoyo import Escena, escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

SEIS = 6
CAMPOS_RECIENTE = {
    "id",
    "kind",
    "movement_id",
    "movement_name",
    "benchmark_id",
    "benchmark_name",
    "score_type",
    "value_g",
    "level",
    "seconds",
    "rounds",
    "reps",
    "load_g",
    "capped",
    "achieved_on",
    "source",
    "wod_id",
}


async def _intentos(session: AsyncSession, e: Escena, benchmark_id: UUID, *dias: str) -> list[UUID]:
    ids: list[UUID] = []
    for dia in dias:
        wod = (
            await make_wod(
                session,
                e.coach,
                list(e.movimientos),
                date=dia,
                title=f"B {dia} {uuid4().hex[:6]}",
                score_type="time",
                time_cap_s=900,
                benchmark_id=str(benchmark_id),
            )
        ).id
        ids.append((await registrar(session, dataclasses.replace(e, wod_id=wod), seconds=300)).id)
    return ids


async def test_socio_sin_datos_da_ceros_y_lista_vacia(session: AsyncSession) -> None:
    miembro = (await make_members(session, 1))[0]

    resumen = await service.summary(session, miembro.id)

    assert resumen.model_dump() == {
        "last_metric_on": None,
        "metrics_count": 0,
        "current_rms": 0,
        "benchmarks_with_attempts": 0,
        "recent_records": [],
        "truncated": False,
    }


async def test_la_ultima_medicion_y_el_conteo_excluyen_las_anuladas(
    session: AsyncSession,
) -> None:
    miembro = (await make_members(session, 1))[0]
    await make_metric(session, miembro.id, measured_on=date(2026, 9, 1))
    await make_metric(session, miembro.id, measured_on=date(2026, 9, 20))
    await make_metric(session, miembro.id, measured_on=date(2026, 10, 5), voided=True)
    otro = (await make_members(session, 1))[0]
    await make_metric(session, otro.id, measured_on=date(2026, 10, 10))

    resumen = await service.summary(session, miembro.id)

    assert (resumen.last_metric_on, resumen.metrics_count) == (date(2026, 9, 20), 2)


async def test_solo_mediciones_anuladas_es_como_no_tener(session: AsyncSession) -> None:
    miembro = (await make_members(session, 1))[0]
    await make_metric(session, miembro.id, voided=True)

    resumen = await service.summary(session, miembro.id)

    assert (resumen.last_metric_on, resumen.metrics_count) == (None, 0)


async def test_current_rms_cuenta_movimientos_y_coincide_con_la_lista(
    session: AsyncSession,
) -> None:
    miembro = (await make_members(session, 1))[0]
    e = await escena(session, con_clase=False)
    mov_a, mov_b = e.movimientos
    await make_record(session, miembro.id, movement_id=mov_a, value_g=100_000)
    await make_record(session, miembro.id, movement_id=mov_a, value_g=120_000)
    await make_record(session, miembro.id, movement_id=mov_b, value_g=50_000)
    await make_record(session, miembro.id, movement_id=uuid4(), value_g=70_000, invalidated=True)
    fran = (await make_benchmark(session, e.coach, "Fran", "time")).id
    await make_record(session, miembro.id, kind="benchmark", benchmark_id=fran)

    resumen = await service.summary(session, miembro.id)
    rms = await service.list_rms(session, miembro.id, PageParams())

    assert resumen.current_rms == 2 == rms.total


async def test_recent_records_son_los_tres_vigentes_mas_recientes_con_nombres(
    session: AsyncSession,
) -> None:
    miembro = (await make_members(session, 1))[0]
    coach = (await escena(session, con_clase=False)).coach
    movs = [(await make_movement(session, coach, f"Mov {n}", "kg")).id for n in range(4)]
    fran = (await make_benchmark(session, coach, "Fran", "time")).id
    superado = await make_record(
        session, miembro.id, movement_id=movs[0], value_g=80_000, achieved_on=date(2026, 9, 28)
    )
    for n, dia in enumerate((1, 5, 7), start=0):
        await make_record(
            session,
            miembro.id,
            movement_id=movs[n],
            value_g=100_000,
            achieved_on=date(2026, 9, dia),
        )
    bench = await make_record(
        session, miembro.id, kind="benchmark", benchmark_id=fran, achieved_on=date(2026, 9, 6)
    )
    await make_record(
        session, miembro.id, movement_id=movs[3], value_g=60_000, achieved_on=date(2026, 9, 2)
    )

    resumen = await service.summary(session, miembro.id)

    recientes = resumen.recent_records
    assert len(recientes) == 3
    forma = [(r.kind, r.achieved_on.day) for r in recientes]
    assert forma == [("rm", 7), ("benchmark", 6), ("rm", 5)]
    assert resumen.truncated is False
    assert all(set(r.model_dump()) == CAMPOS_RECIENTE for r in recientes)
    assert superado.id not in {r.id for r in recientes}
    assert recientes[1].id == bench.id
    assert (recientes[1].benchmark_name, recientes[1].score_type) == ("Fran", "time")
    assert recientes[0].movement_name == "Mov 2"


async def test_benchmarks_con_intentos_cuenta_vigentes_y_validados_como_la_lista(
    session: AsyncSession,
) -> None:
    e = await escena(session, score_type="time", fecha="2026-08-20", con_clase=False)
    fran = (await make_benchmark(session, e.coach, "Fran", "time")).id
    grace = (await make_benchmark(session, e.coach, "Grace", "time")).id
    helen = (await make_benchmark(session, e.coach, "Helen", "time")).id
    await _intentos(session, e, fran, "2026-09-01", "2026-09-08")
    await _intentos(session, e, grace, "2026-09-10")
    (anulado,) = await _intentos(session, e, helen, "2026-09-15")
    with actor_scope(e.coach):
        await void_result(session, anulado, VoidIn(reason="Socio equivocado"), by=e.coach)

    resumen = await service.summary(session, e.socio_id)
    lista = await service.list_benchmarks(session, e.socio_id, PageParams())

    assert resumen.benchmarks_with_attempts == 2 == lista.total


async def test_no_descifra_ni_deja_filas_de_cifrado_o_de_auditoria(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    miembro = (await make_members(session, 1))[0]
    await make_metric(session, miembro.id)
    await make_record(session, miembro.id, movement_id=uuid4())

    def prohibido(*_a: Any, **_k: Any) -> None:
        raise AssertionError("el resumen no debe descifrar")

    monkeypatch.setattr(types, "reveal", prohibido)
    ops = await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops"))
    audit = await session.scalar(text("SELECT count(*) FROM audit.audit_log"))

    await service.summary(session, miembro.id)

    assert await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops")) == ops
    assert await session.scalar(text("SELECT count(*) FROM audit.audit_log")) == audit
    revelaciones = await session.scalar(
        text("SELECT count(*) FROM audit.audit_log WHERE action = 'reveal'")
    )
    assert revelaciones == 0


async def test_funciona_con_el_custodio_sellado(session: AsyncSession) -> None:
    miembro = (await make_members(session, 1))[0]
    await make_metric(session, miembro.id, measured_on=date(2026, 9, 20))
    await make_record(session, miembro.id, movement_id=uuid4(), value_g=90_000)
    configure_keyring(None)  # el custodio se selló: no hay llaves en memoria

    resumen = await service.summary(session, miembro.id)
    rms = await service.list_rms(session, miembro.id, PageParams())

    assert (resumen.last_metric_on, resumen.metrics_count, resumen.current_rms) == (
        date(2026, 9, 20),
        1,
        1,
    )
    assert rms.total == 1


async def test_a_lo_sumo_seis_consultas_en_el_caso_completo(session: AsyncSession) -> None:
    e = await escena(session, score_type="time", fecha="2026-08-20", con_clase=False)
    fran = (await make_benchmark(session, e.coach, "Fran", "time")).id
    await _intentos(session, e, fran, "2026-09-01", "2026-09-08")
    await make_metric(session, e.socio_id, measured_on=date(2026, 9, 1))
    await make_metric(session, e.socio_id, measured_on=date(2026, 9, 2), voided=True)
    for mov in e.movimientos:
        await make_record(session, e.socio_id, movement_id=mov, value_g=100_000)
    await make_record(session, e.socio_id, kind="benchmark", benchmark_id=fran)
    session.expunge_all()

    sentencias: list[str] = []
    destino = session.sync_session.get_bind()

    def anotar(_c: Any, _cur: Any, sql: str, *_a: Any) -> None:
        if sql.lstrip().upper().startswith(("SELECT", "WITH")):
            sentencias.append(sql)

    event.listen(destino, "before_cursor_execute", anotar)
    try:
        resumen = await service.summary(session, e.socio_id)
    finally:
        event.remove(destino, "before_cursor_execute", anotar)

    assert resumen.current_rms == 2 and resumen.benchmarks_with_attempts == 1
    assert len(sentencias) <= SEIS, [s[:80] for s in sentencias]


async def test_un_socio_dado_de_baja_tambien_se_lee(session: AsyncSession) -> None:
    miembro = (await make_members(session, 1))[0]
    await make_record(session, miembro.id, movement_id=uuid4())
    await session.execute(
        text("UPDATE members.members SET deleted_at = now() WHERE id = :i"), {"i": miembro.id}
    )

    resumen = await service.summary(session, miembro.id)

    assert resumen.current_rms == 1


async def test_socio_inexistente_da_404_member_not_found(session: AsyncSession) -> None:
    with pytest.raises(MemberNotFound):
        await service.summary(session, uuid4())


async def test_el_tope_de_records_vivos_marca_truncated_y_no_muestra_historicos_como_vigentes(
    session: AsyncSession,
    alertas: AlertasCapturadas,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coach = (await escena(session, con_clase=False)).coach
    miembro = (await make_members(session, 1))[0]
    fran = (await make_benchmark(session, coach, "Fran", "time")).id
    movs = [(await make_movement(session, coach, f"Mov {n}", "kg")).id for n in range(2)]
    for n, seg in enumerate((200, 300, 400)):  # el mejor (200) es el más antiguo
        await make_record(
            session,
            miembro.id,
            kind="benchmark",
            benchmark_id=fran,
            seconds=seg,
            achieved_on=date(2026, 9, 1 + n),
        )
    for mov in movs:
        await make_record(session, miembro.id, movement_id=mov, achieved_on=date(2026, 8, 1))
    monkeypatch.setattr(reads, "LIVE_RECORDS_MAX", 2)

    with caplog.at_level(logging.WARNING, logger="app.athletes"):
        resumen = await service.summary(session, miembro.id)

    assert resumen.truncated is True
    assert resumen.current_rms == 2, "los RM salen de SQL, sin tope"
    assert [r.kind for r in resumen.recent_records] == ["rm", "rm"]
    assert all(r.benchmark_id is None for r in resumen.recent_records)
    assert alertas.de("athletes_summary_capped") == [{"marcas": 2}]
    assert alertas.de("athletes_restore_capped") == []
    assert str(miembro.id) not in str(alertas.recibidas)
    avisos = [r for r in caplog.records if r.name == "app.athletes"]
    assert avisos and "resumen" in avisos[0].getMessage()


async def test_sin_tope_los_benchmarks_vigentes_salen_y_truncated_es_falso(
    session: AsyncSession, alertas: AlertasCapturadas
) -> None:
    coach = (await escena(session, con_clase=False)).coach
    miembro = (await make_members(session, 1))[0]
    fran = (await make_benchmark(session, coach, "Fran", "time")).id
    for n, seg in enumerate((200, 300, 400)):
        await make_record(
            session,
            miembro.id,
            kind="benchmark",
            benchmark_id=fran,
            seconds=seg,
            achieved_on=date(2026, 9, 1 + n),
        )

    resumen = await service.summary(session, miembro.id)

    assert resumen.truncated is False
    assert [(r.kind, r.seconds) for r in resumen.recent_records] == [("benchmark", 200)]
    assert alertas.recibidas == []


async def test_el_tope_de_marcas_de_benchmarks_marca_truncated_y_alerta(
    session: AsyncSession,
    alertas: AlertasCapturadas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e = await escena(session, score_type="time", fecha="2026-08-20", con_clase=False)
    fran = (await make_benchmark(session, e.coach, "Fran", "time")).id
    await _intentos(session, e, fran, "2026-09-01", "2026-09-08")
    monkeypatch.setattr(reads, "MEMBER_MARKS_MAX", 2)

    resumen = await service.summary(session, e.socio_id)

    assert resumen.truncated is True and resumen.benchmarks_with_attempts == 1
    assert alertas.de("athletes_summary_capped") == [{"marcas": 2}]
    assert str(e.socio_id) not in str(alertas.recibidas)


async def test_un_rm_sin_valor_se_omite_y_se_avisa(
    session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    miembro = (await make_members(session, 1))[0]
    bueno, malo = uuid4(), uuid4()
    await make_record(session, miembro.id, movement_id=bueno, value_g=90_000)
    await session.execute(
        text(
            "DO $$ DECLARE c text; BEGIN SELECT conname INTO c FROM pg_constraint "
            "WHERE conrelid = 'athletes.personal_records'::regclass AND conname LIKE '%rm_shape'; "
            "EXECUTE 'ALTER TABLE athletes.personal_records DROP CONSTRAINT ' || quote_ident(c); "
            "END $$"
        )
    )
    roto = await make_record(session, miembro.id, movement_id=malo, value_g=1)
    await session.execute(text(disable_user_sql("athletes.personal_records")))
    await session.execute(
        text("UPDATE athletes.personal_records SET value_g = NULL WHERE id = :i"), {"i": roto.id}
    )
    session.expunge_all()  # sin la entidad vieja del mapa de identidad

    with caplog.at_level(logging.WARNING, logger="app.athletes"):
        resumen = await service.summary(session, miembro.id)
        rms = await service.list_rms(session, miembro.id, PageParams())

    assert resumen.current_rms == 1 and [r.value_g for r in resumen.recent_records] == [90_000]
    assert [i.value_g for i in rms.items] == [90_000]
    assert any("sin valor" in r.getMessage() for r in caplog.records)
