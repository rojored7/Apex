"""`core/backup_status.py`: el estado de los respaldos para `/health` (S4B-B2; S4B-D26, D60, D71).

Base real (`worker.job_runs` sembrada con `make_job_run`), reloj `FrozenClock` en
`2026-10-21T12:00:00Z`. `backup_health()` lee la última corrida de `backup_check` y la colapsa:
- sin corrida -> `unknown`; `ok` y `ok_unverified` -> `ok`; `stale`, `missing`, `corrupt` y
  `undecryptable` -> `attention`; `running` y `error` -> `unknown`;
- una corrida más vieja que `MAX_RUN_AGE` (el worker dejó de comprobar) -> `attention`, sea cual
  sea su resultado de forma; 40 h es más viejo, 12 h no;
- solo cuenta el `job_name` exacto `backup_check` (ni `_sim` ni otros jobs);
- con la base caída -> `unknown` en menos de 3 s, sin lanzar;
- el valor devuelto es siempre uno de `PUBLIC_BACKUP`: ningún nombre ni ruta.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import db
from app.core.backup_status import (
    BACKUP_STATES,
    HEALTH_JOB,
    MAX_RUN_AGE,
    PUBLIC_BACKUP,
    backup_health,
)
from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.config import Settings
from tests.conftest import LIMPIAR_JOB_RUNS
from tests.factories.job_runs import make_job_run

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)
HOY = date(2026, 10, 21)
Fabrica = async_sessionmaker[AsyncSession]


@pytest.fixture
def reloj() -> Iterator[FrozenClock]:
    reloj = FrozenClock(NOW)
    token = set_clock(reloj)
    try:
        yield reloj
    finally:
        reset_clock(token)


@pytest.fixture
async def base_global(settings_prueba: Settings, engine: AsyncEngine) -> AsyncIterator[Fabrica]:
    """El engine del proceso apunta a `db_test` (como lo deja `create_app`); limpia `job_runs`."""
    db.configure_engine(db.create_engine_from(settings_prueba))
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield fabrica
    finally:
        await db.dispose_engine()
        async with engine.begin() as conexion:
            await conexion.execute(text(LIMPIAR_JOB_RUNS))


async def _sembrar(
    fabrica: Fabrica,
    resultado: str,
    *,
    hace: timedelta = timedelta(hours=2),
    job: str = HEALTH_JOB,
    dia: date = HOY,
) -> None:
    async with fabrica() as sesion:
        await make_job_run(sesion, job, dia, result=resultado, started_at=NOW - hace)


def test_las_constantes_son_las_del_plan() -> None:
    assert HEALTH_JOB == "backup_check"
    assert (
        frozenset({"ok", "ok_unverified", "stale", "missing", "corrupt", "undecryptable"})
        == BACKUP_STATES
    )
    assert frozenset({"ok", "attention", "unknown"}) == PUBLIC_BACKUP
    assert timedelta(hours=24) < MAX_RUN_AGE < timedelta(hours=40)


async def test_sin_corrida_es_unknown(reloj: FrozenClock, base_global: object) -> None:
    assert await backup_health() == "unknown"


@pytest.mark.parametrize(
    ("resultado", "esperado"),
    [
        ("ok", "ok"),
        ("ok_unverified", "ok"),
        ("stale", "attention"),
        ("missing", "attention"),
        ("corrupt", "attention"),
        ("undecryptable", "attention"),
        ("running", "unknown"),
        ("error", "unknown"),
    ],
)
async def test_cada_resultado_se_colapsa_al_valor_publico(
    resultado: str, esperado: str, reloj: FrozenClock, base_global: Fabrica
) -> None:
    await _sembrar(base_global, resultado)

    valor = await backup_health()

    assert valor == esperado
    assert valor in PUBLIC_BACKUP


async def test_una_corrida_ok_de_hace_40_horas_es_attention(
    reloj: FrozenClock, base_global: Fabrica
) -> None:
    await _sembrar(base_global, "ok", hace=timedelta(hours=40), dia=HOY - timedelta(days=2))

    assert await backup_health() == "attention"


async def test_una_corrida_ok_de_hace_12_horas_sigue_siendo_ok(
    reloj: FrozenClock, base_global: Fabrica
) -> None:
    await _sembrar(base_global, "ok", hace=timedelta(hours=12))

    assert await backup_health() == "ok"


async def test_una_corrida_ok_unverified_vieja_tambien_es_attention(
    reloj: FrozenClock, base_global: Fabrica
) -> None:
    await _sembrar(base_global, "ok_unverified", hace=timedelta(hours=40), dia=HOY - timedelta(2))

    assert await backup_health() == "attention"


async def test_solo_cuenta_la_corrida_mas_reciente(
    reloj: FrozenClock, base_global: Fabrica
) -> None:
    await _sembrar(base_global, "corrupt", hace=timedelta(hours=26), dia=HOY - timedelta(days=1))
    await _sembrar(base_global, "ok", hace=timedelta(hours=2))

    assert await backup_health() == "ok"


async def test_otros_jobs_y_la_simulada_no_cuentan(
    reloj: FrozenClock, base_global: Fabrica
) -> None:
    await _sembrar(base_global, "ok", hace=timedelta(hours=3))
    await _sembrar(base_global, "error", hace=timedelta(hours=1), job="expirations")
    await _sembrar(base_global, "corrupt", hace=timedelta(hours=1), job="backup_check_sim")

    assert await backup_health() == "ok"


async def test_con_la_base_caida_es_unknown_en_menos_de_3_segundos(
    settings_prueba: Settings, reloj: FrozenClock
) -> None:
    partes = urlsplit(settings_prueba.DATABASE_URL.get_secret_value())
    url = urlunsplit(partes._replace(netloc=f"{partes.username}:x@127.0.0.1:1"))
    caida = settings_prueba.model_copy(update={"DATABASE_URL": SecretStr(url)})
    db.configure_engine(db.create_engine_from(caida))
    try:
        inicio = time.perf_counter()
        valor = await backup_health()
        transcurrido = time.perf_counter() - inicio
    finally:
        await db.dispose_engine()

    assert valor == "unknown"
    assert transcurrido < 3
