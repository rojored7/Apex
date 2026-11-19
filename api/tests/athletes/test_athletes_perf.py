"""Rendimiento del módulo `athletes` con datos mezclados (S9-V6). Marcada `perf`: no es gate.

Corre aparte: `uv run pytest -m perf tests/athletes/test_athletes_perf.py -q -s`. Siembra en
`db_test` (dentro del savepoint de la prueba): 30 WODs de carga con 100 resultados cada uno
(unos 3.300 con las correcciones de `supersedes_id`; el handler de athletes deriva los RM al
sembrar), 500 récords manuales (RM y benchmark, algunos invalidados), 200 mediciones y un socio con
2.000 marcas (2.000 WODs de carga con el mismo movimiento principal). Hace `ANALYZE` y mide:

1. 15 registros de resultado seguidos (el camino de `PUT /results`: `results.service.record_result`
   y commit) con las suscripciones de athletes ACTIVAS y 15 SIN ellas, intercalados para que la
   deriva de la base no sesgue; la mediana con handler no sube más de 20 ms sobre la mediana sin él.
2. Una corrección (`supersedes_id`) de la marca que sostiene el RM del socio de 2.000 marcas
   (invalida y repone): termina bajo el `statement_timeout` configurado.
3. `EXPLAIN (ANALYZE, BUFFERS)` de las lecturas de `/rms`, `/records`, `member_marks`,
   `wod_ids_with_primary`, el puerto `RecordsProbe`, la lectura ORM de `_invalidate` y la lectura
   por `invalidated_by_result_id`: todas por índice, sin `Seq Scan` sobre `personal_records` ni
   `wod_results` ni `wod_movements`, sin tocar el planificador (S8-D50).
4. `/summary` (`athletes.reads.summary`) bajo 300 ms.
"""

from __future__ import annotations

import re
import statistics
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.config import Settings
from app.core.context import actor_scope
from app.core.pagination import PageParams
from app.modules.athletes import derive, reads
from app.modules.athletes import service as athletes_service
from app.modules.athletes.models import PersonalRecord
from app.modules.results import service as results_service
from app.modules.results.events import WodResultValidated
from app.modules.results.schemas import ResultIn
from app.modules.results.service import WodResultSuperseded, WodResultVoided
from app.modules.wods import service as wods_service
from tests.factories.athletes import make_metric, make_record
from tests.factories.explain import capturar_sql, imprimir_explain
from tests.factories.members import make_members
from tests.factories.results import make_result
from tests.factories.users import make_user
from tests.factories.wods import make_movement, make_wod

pytestmark = [pytest.mark.perf, pytest.mark.usefixtures("reloj", "bus_listo")]

TOPE_SUMMARY_MS = 300
TOPE_DIFERENCIA_MS = 20
WODS = 30
SOCIOS = 100
MOVIMIENTOS = 12
RECORDS_MANUALES = 500
MEDICIONES = 200
MARCAS_SOCIO_GRANDE = 2_000
PUNTO_MEDIO = MARCAS_SOCIO_GRANDE // 2
REGISTROS_MEDIDOS = 15
HOY = date(2026, 10, 20)
SEQ_SCAN = re.compile(r"Seq Scan on (personal_records|wod_results|wod_movements)")
EVENTOS = (WodResultValidated, WodResultSuperseded, WodResultVoided)


@dataclass
class Escena:
    coach: UUID
    socios: list[UUID]
    movimientos: list[UUID]
    wods: list[UUID]
    socio_clave: UUID


@contextmanager
def sin_handlers_de_athletes() -> Iterator[None]:
    """Quita del bus las suscripciones de athletes y las restaura en un `finally` (S9-D20)."""
    guardado = {tipo: list(events.subscribers_for(tipo)) for tipo in EVENTOS}
    propios = {derive.on_wod_result_validated, derive.on_wod_result_superseded}
    propios.add(derive.on_wod_result_voided)
    try:
        for tipo in EVENTOS:
            eventos_dict = events._subscribers
            eventos_dict[tipo] = [h for h in guardado[tipo] if h not in propios]
        yield
    finally:
        for tipo in EVENTOS:
            events._subscribers[tipo] = guardado[tipo]


def _fecha(dias_atras: int) -> str:
    return (HOY - timedelta(days=dias_atras)).isoformat()


async def _sembrar_resultados(session: AsyncSession) -> Escena:
    coach = (await make_user(session, role="coach")).id
    movs = [
        (await make_movement(session, coach, name=f"Mov perf {i}", unit="kg")).id
        for i in range(MOVIMIENTOS)
    ]
    socios = [m.id for m in await make_members(session, SOCIOS, data_consent_at=_consent())]
    wods: list[UUID] = []
    for w in range(WODS):
        wod = await make_wod(
            session,
            coach,
            [movs[w % MOVIMIENTOS], movs[(w + 1) % MOVIMIENTOS]],
            date=_fecha(WODS - w),
            title=f"WOD perf {w}",
            score_type="load",
            time_cap_s=None,
        )
        wods.append(wod.id)
        for k in range(100):
            socio = socios[(3 * w + k) % SOCIOS]
            carga = 60_000 + ((k * 7 + w * 3) % 60) * 1_000
            marca = await make_result(session, coach, wod.id, socio, load_g=carga, seconds=None)
            if k % 10 == 0:  # corrección: la anterior queda is_current = false
                await make_result(
                    session,
                    coach,
                    wod.id,
                    socio,
                    load_g=carga + 2_000,
                    seconds=None,
                    supersedes_id=marca.id,
                )
    return Escena(coach, socios, movs, wods, socios[50])


def _consent() -> Any:
    from datetime import UTC, datetime

    return datetime(2026, 10, 1, tzinfo=UTC)


async def _sembrar_records_y_medidas(session: AsyncSession, e: Escena) -> None:
    for i in range(RECORDS_MANUALES):
        socio = e.socios[i % SOCIOS]
        if i % 3:
            await make_record(
                session,
                socio,
                kind="rm",
                movement_id=e.movimientos[i % MOVIMIENTOS],
                value_g=50_000 + i * 100,
                invalidated=(i % 10 == 0),
            )
        else:
            await make_record(
                session,
                socio,
                kind="benchmark",
                benchmark_id=uuid4(),
                level="rx",
                seconds=200 + i,
                invalidated=(i % 10 == 0),
            )
    for i in range(MEDICIONES):
        await make_metric(session, e.socios[i % SOCIOS], measured_on=HOY - timedelta(days=i))


async def _sembrar_socio_grande(session: AsyncSession, e: Escena) -> tuple[UUID, UUID, UUID]:
    """2.000 marcas de carga del mismo movimiento principal; la mejor, a mitad. Devuelve
    `(socio, WOD de la mejor, resultado de la mejor)`."""
    socio = (await make_members(session, 1, data_consent_at=_consent()))[0].id
    mov = (await make_movement(session, e.coach, name="Mov perf grande", unit="kg")).id
    mejor_wod = mejor_resultado = None
    for i in range(MARCAS_SOCIO_GRANDE):
        wod = await make_wod(
            session,
            e.coach,
            [mov],
            date=_fecha(100 + i),
            title=f"WOD grande {i}",
            score_type="load",
            time_cap_s=None,
        )
        carga = 150_000 if i == PUNTO_MEDIO else 50_000 + (i * 37) % 60_000
        marca = await make_result(session, e.coach, wod.id, socio, load_g=carga, seconds=None)
        if i == PUNTO_MEDIO:
            mejor_wod, mejor_resultado = wod.id, marca.id
    assert mejor_wod is not None and mejor_resultado is not None
    return socio, mejor_wod, mejor_resultado


async def _registrar(session: AsyncSession, coach: UUID, datos: dict[str, Any]) -> float:
    """Un registro como `PUT /results`: `record_result` + commit del savepoint. Devuelve ms."""
    inicio = time.perf_counter()
    with actor_scope(coach):
        await results_service.record_result(
            session, ResultIn.model_validate(datos), by=coach, source="desk"
        )
        await session.commit()
    return (time.perf_counter() - inicio) * 1000


async def _medir_registros(session: AsyncSession, e: Escena) -> tuple[list[float], list[float]]:
    """15 registros con handler y 15 sin él, intercalados, con cargas crecientes por socio (cada
    registro es un RM nuevo: el camino más caro del handler)."""
    con_h = (await make_members(session, 1, data_consent_at=_consent()))[0].id
    sin_h = (await make_members(session, 1, data_consent_at=_consent()))[0].id
    mov_a = (await make_movement(session, e.coach, name="Mov medido A", unit="kg")).id
    mov_b = (await make_movement(session, e.coach, name="Mov medido B", unit="kg")).id
    wods_a, wods_b = [], []
    for i in range(REGISTROS_MEDIDOS + 1):  # el primero calienta
        for mov, lista, nombre in ((mov_a, wods_a, "A"), (mov_b, wods_b, "B")):
            wod = await make_wod(
                session,
                e.coach,
                [mov],
                date=_fecha(2_100 + 2 * i + (nombre == "B")),
                title=f"WOD medido {nombre}{i}",
                score_type="load",
                time_cap_s=None,
            )
            lista.append(wod.id)
    await session.execute(text("ANALYZE"))
    ms_con: list[float] = []
    ms_sin: list[float] = []
    for i in range(REGISTROS_MEDIDOS + 1):
        carga = 100_000 + i * 1_000
        ms = await _registrar(
            session,
            e.coach,
            {"wod_id": wods_a[i], "member_id": con_h, "level": "rx", "load_g": carga},
        )
        with sin_handlers_de_athletes():
            ms_b = await _registrar(
                session,
                e.coach,
                {"wod_id": wods_b[i], "member_id": sin_h, "level": "rx", "load_g": carga},
            )
        if i:
            ms_con.append(ms)
            ms_sin.append(ms_b)
    derivados = await session.scalar(
        select(text("count(*)"))
        .select_from(PersonalRecord)
        .where(PersonalRecord.member_id == con_h)
    )
    assert derivados == REGISTROS_MEDIDOS + 1, "el handler debía derivar un RM por registro"
    sin_derivar = await session.scalar(
        select(text("count(*)"))
        .select_from(PersonalRecord)
        .where(PersonalRecord.member_id == sin_h)
    )
    assert sin_derivar == 0, "sin handler no debe haber récords derivados"
    return ms_con, ms_sin


async def _plan(
    session: AsyncSession, titulo: str, tabla: str, lectura: Callable[[], Awaitable[Any]]
) -> tuple[float, list[str]]:
    """Calienta, mide el tiempo, captura el SQL que toca `tabla` y lo explica."""
    await lectura()
    inicio = time.perf_counter()
    await lectura()
    ms = (time.perf_counter() - inicio) * 1000
    with capturar_sql(session, tabla) as capturadas:
        await lectura()
    resumenes = await imprimir_explain(session, titulo, capturadas)
    conexion = await session.connection()
    planos = []
    for sql, parametros in capturadas:
        res = await conexion.exec_driver_sql("EXPLAIN " + sql, parametros)
        planos.append("\n".join(str(f[0]) for f in res.all()))
    print(f"{titulo}: {ms:.1f} ms")
    print("RESUMEN", "; ".join(resumenes))
    return ms, planos


async def test_rendimiento_athletes_con_datos_mezclados(
    session: AsyncSession, settings_prueba: Settings
) -> None:
    e = await _sembrar_resultados(session)
    await _sembrar_records_y_medidas(session, e)
    socio_grande, wod_mejor, mejor = await _sembrar_socio_grande(session, e)
    for tabla in ("athletes.personal_records", "athletes.body_metrics", "results.wod_results"):
        await session.execute(text(f"ANALYZE {tabla}"))
    await session.execute(text("ANALYZE wods.wod_movements"))
    total_resultados = await session.scalar(text("SELECT count(*) FROM results.wod_results"))
    total_records = await session.scalar(text("SELECT count(*) FROM athletes.personal_records"))
    print(f"\nSEMBRADO: resultados={total_resultados} records={total_records} (S9-V6)")

    # (1) registros con y sin handler
    ms_con, ms_sin = await _medir_registros(session, e)
    med_con, med_sin = statistics.median(ms_con), statistics.median(ms_sin)
    print(f"REGISTROS con handler (ms): {[round(x, 1) for x in ms_con]}")
    print(f"REGISTROS sin handler (ms): {[round(x, 1) for x in ms_sin]}")
    print(
        f"MEDIANAS: con={med_con:.1f} ms sin={med_sin:.1f} ms diferencia={med_con - med_sin:.1f} ms"
    )

    # (2) corrección del socio con 2.000 marcas
    marcas = await session.scalar(
        text("SELECT count(*) FROM results.wod_results WHERE member_id = :m AND is_current"),
        {"m": socio_grande},
    )
    assert marcas == MARCAS_SOCIO_GRANDE
    inicio = time.perf_counter()
    with actor_scope(e.coach):
        await results_service.record_result(
            session,
            ResultIn.model_validate(
                {
                    "wod_id": wod_mejor,
                    "member_id": socio_grande,
                    "level": "rx",
                    "load_g": 90_000,
                    "supersedes_id": mejor,
                }
            ),
            by=e.coach,
            source="desk",
        )
        await session.commit()
    ms_correccion = (time.perf_counter() - inicio) * 1000
    tope_ms = settings_prueba.DB_STATEMENT_TIMEOUT_MS
    print(f"CORRECCION socio con {marcas} marcas: {ms_correccion:.1f} ms (tope {tope_ms} ms)")

    # (3) EXPLAIN de las lecturas
    pagina = PageParams(limit=50)
    socio = e.socios[50]
    mov = e.movimientos[0]
    mov_con_records = e.movimientos[1]
    resultado_vivo = await session.scalar(
        select(PersonalRecord.result_id).where(
            PersonalRecord.member_id == socio,
            PersonalRecord.source == "derived",
            PersonalRecord.invalidated_at.is_(None),
        )
    )
    assert resultado_vivo is not None, "el socio clave debía tener un RM derivado vivo"
    todos: list[tuple[str, list[str]]] = []
    mov_selectivo = uuid4()
    for i in range(3):
        await make_record(
            session, e.socios[i], kind="rm", movement_id=mov_selectivo, value_g=80_000 + i
        )
    await session.execute(text("ANALYZE athletes.personal_records"))

    async def rms() -> Any:
        return await athletes_service.list_rms(session, socio, pagina)

    async def records() -> Any:
        return await athletes_service.list_records(session, socio, pagina)

    async def marcas_socio() -> Any:
        return await results_service.member_marks(session, socio, only_benchmarks=False)

    async def marcas_socio_grande() -> Any:
        return await results_service.member_marks(session, socio_grande, only_benchmarks=False)

    async def con_principal() -> Any:
        return await wods_service.wod_ids_with_primary(session, mov)

    async def sonda() -> Any:
        await athletes_service.records_probe.movement_has_records(session, mov_selectivo)
        await athletes_service.records_probe.benchmark_has_records(session, uuid4())

    async def sonda_movimiento_caliente() -> Any:
        await athletes_service.records_probe.movement_has_records(session, mov_con_records)

    async def lectura_de_invalidar() -> Any:
        # `_invalidate` escribe: dentro de un savepoint que se revierte (solo importa su SELECT).
        async with session.begin_nested() as sp:
            with actor_scope(e.coach):
                await derive._invalidate(
                    session,
                    member_id=socio,
                    result_id=resultado_vivo,
                    reason="voided",
                    by_result=None,
                )
            await sp.rollback()

    async def por_invalidante() -> Any:
        mark = await results_service.get_mark(session, resultado_vivo)
        assert mark is not None
        from dataclasses import replace

        marca = replace(mark, supersedes_id=resultado_vivo, result_id=uuid4())
        return await derive._superseded_targets(session, marca)

    casos: list[tuple[str, str, Callable[[], Awaitable[Any]]]] = [
        ("/rms", "athletes.personal_records", rms),
        ("/records", "athletes.personal_records", records),
        ("results.member_marks (socio con 30 marcas)", "results.wod_results", marcas_socio),
        ("wods.wod_ids_with_primary", "wods.wod_movements", con_principal),
        ("RecordsProbe (movimiento con 3 récords)", "athletes.personal_records", sonda),
        (
            "_invalidate (uq_personal_records_result_kind)",
            "athletes.personal_records",
            lectura_de_invalidar,
        ),
        ("por invalidated_by_result_id", "athletes.personal_records", por_invalidante),
    ]
    for titulo, tabla, lectura in casos:
        _ms, planos = await _plan(session, titulo, tabla, lectura)
        todos.append((titulo, planos))
    # Solo informativos: lecturas sobre una porción grande de una tabla de pocos miles de filas
    # (24 a 38 %), donde el Seq Scan es lo más barato para el planificador; no se afirman.
    informativos = [
        ("member_marks (socio con 2.000 marcas)", "results.wod_results", marcas_socio_grande),
        (
            "RecordsProbe (movimiento caliente)",
            "athletes.personal_records",
            sonda_movimiento_caliente,
        ),
    ]
    for titulo, tabla, lectura in informativos:
        await _plan(session, titulo + " [solo informativo]", tabla, lectura)

    # (4) /summary
    await reads.summary(session, socio)  # calentamiento
    inicio = time.perf_counter()
    await reads.summary(session, socio)
    ms_summary = (time.perf_counter() - inicio) * 1000
    print(f"/summary: {ms_summary:.1f} ms")
    print(
        f"RESUMEN V6: mediana con={med_con:.1f} sin={med_sin:.1f} dif={med_con - med_sin:.1f} ms; "
        f"correccion={ms_correccion:.1f} ms; summary={ms_summary:.1f} ms"
    )

    assert med_con - med_sin <= TOPE_DIFERENCIA_MS, (
        f"el handler suma {med_con - med_sin:.1f} ms a la mediana (tope {TOPE_DIFERENCIA_MS})"
    )
    assert ms_correccion < tope_ms, f"correccion {ms_correccion:.1f} ms >= statement_timeout"
    assert ms_summary < TOPE_SUMMARY_MS
    for titulo, planos in todos:
        for plano in planos:
            assert not SEQ_SCAN.search(plano), f"{titulo}: Seq Scan: {plano}"
