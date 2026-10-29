"""Entrada del worker `python -m app.worker.main` (US-113; S4A-D4, S4A-D6, S4A-D8, S4A-D48,
S4A-D56, S4A-D64; enmiendas E1 y E5).

`main(argv)` directo (no hay Typer): `load_settings` de `app.worker.main` devuelve
`settings_prueba` (base `apex_test`, `ENV=dev`) o una copia con `model_copy`; nunca se toca
`os.environ`. El reloj es `reloj_worker` (`2026-10-21T15:00Z`, hoy `2026-10-21` en Bogotá): `main`
corre en un hilo con copia del contexto si ya hay un loop (como `cli._run`), así que lo ve.
- `--run-once expirations` sobre la base vacía da 0 y deja una fila `ok` con
  `details["revisados"] == 0` (el recálculo real de S4A-B2 reemplazó el marcador de S4A-D64);
  dos veces el mismo día reutiliza la fila;
- un job de prueba que falla da 1; un job inexistente da 2 y lista los registrados; con una corrida
  `running` vigente da 3;
- `--date` (S4A-D48, E5): fecha distinta de hoy sin `--simulate` da 2; con `--simulate`, `ENV=dev` y
  base `apex_test` instala `FrozenClock` a las 12:00 de Bogotá (17:00Z) de esa fecha, reclama
  `expirations_sim`, imprime `RELOJ SIMULADO: <fecha>` en la primera línea y deja
  `logger.warning("clock override")`; con `ENV=production` o con una base `.../apex` da 2; `--date`
  igual a hoy sin `--simulate` da 0;
- `--status <job>`: el último intento en JSON (una línea, sin `attempts`) y 0, o 2 sin corridas;
  `--status expirations_sim` muestra la simulada;
- `runtime.clock_override_error` (la guarda pura de E5), `wait_for_database` (esperas 1, 2, 4, ...
  con tope de 60 s por espera), `touch_heartbeat_if_db_ok` (S4A-D56) y `serve` con la parada ya
  disparada (latido escrito, salida 0);
- en un proceso limpio, `--run-once expirations` deja registrado el gate de pagos
  (`load_module_services`, `test_gates_registered.py`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.jobs import JobRun
from app.worker import main as worker_main
from app.worker import runner, runtime
from app.worker.registry import JobSpec
from app.worker.runner import JobContext, JobResult
from app.worker.runtime import clock_override_error, touch_heartbeat_if_db_ok, wait_for_database
from tests.factories.job_runs import make_job_run
from tests.worker.conftest import SpecObservado

Fabrica = async_sessionmaker[AsyncSession]
HOY = date(2026, 10, 21)
FUTURA = date(2026, 11, 1)
MEDIODIA_FUTURA_UTC = datetime(2026, 11, 1, 17, 0, tzinfo=UTC)  # 12:00 de Bogotá
CAMPOS_STATUS = {
    "id",
    "job_name",
    "run_date",
    "started_at",
    "finished_at",
    "result",
    "error",
    "details",
}


def _con_base(settings: Settings, nombre: str) -> Settings:
    partes = urlsplit(settings.DATABASE_URL.get_secret_value())
    url = urlunsplit(partes._replace(path=f"/{nombre}"))
    return settings.model_copy(update={"DATABASE_URL": SecretStr(url)})


@pytest.fixture(autouse=True)
def logging_restaurado() -> Iterator[None]:
    """`worker_runtime` llama a `configure_logging`: se restauran los handlers y el nivel raíz."""
    raiz = logging.getLogger()
    handlers, nivel = list(raiz.handlers), raiz.level
    try:
        yield
    finally:
        raiz.handlers[:] = handlers
        raiz.setLevel(nivel)


@pytest.fixture
def usar_settings(monkeypatch: pytest.MonkeyPatch) -> Any:
    def usar(settings: Settings) -> Settings:
        monkeypatch.setattr(worker_main, "load_settings", lambda *a, **k: settings)
        return settings

    return usar


@pytest.fixture
def con_prueba(usar_settings: Any, settings_prueba: Settings) -> Settings:
    return usar_settings(settings_prueba)  # type: ignore[no-any-return]


async def _corridas(fabrica: Fabrica) -> list[JobRun]:
    async with fabrica() as sesion:
        return list((await sesion.scalars(select(JobRun).order_by(JobRun.job_name))).all())


def _json_de_status(salida: str) -> dict[str, Any]:
    for linea in reversed(salida.strip().splitlines()):
        try:
            datos = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if isinstance(datos, dict) and {"job_name", "run_date"} <= set(datos):
            return datos
    raise AssertionError(f"--status no imprimió el intento en una línea JSON: {salida!r}")


# --run-once ---------------------------------------------------------------------------------------


async def test_run_once_expirations_sobre_base_vacia_da_0_con_revisados_0(
    con_prueba: Settings, session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    assert worker_main.main(["--run-once", "expirations"]) == 0

    corridas = await _corridas(session_factory)
    assert [(c.job_name, c.run_date, c.result) for c in corridas] == [("expirations", HOY, "ok")]
    assert corridas[0].details["revisados"] == 0
    assert "placeholder_ok" not in corridas[0].details
    assert "clock_override" not in corridas[0].details


async def test_run_once_dos_veces_el_mismo_dia_reutiliza_la_fila(
    con_prueba: Settings, session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    assert worker_main.main(["--run-once", "expirations"]) == 0
    assert worker_main.main(["--run-once", "expirations"]) == 0

    corridas = await _corridas(session_factory)
    assert len(corridas) == 1
    assert len(corridas[0].details["attempts"]) == 2


async def test_run_once_de_un_job_que_falla_da_1(
    con_prueba: Settings,
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    spec_que_lanza: SpecObservado,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_main, "get_registry", lambda: (spec_que_lanza.spec,))

    assert worker_main.main(["--run-once", "prueba_lanza"]) == 1

    corridas = await _corridas(session_factory)
    assert [(c.job_name, c.result, c.error) for c in corridas] == [
        ("prueba_lanza", "error", "RuntimeError")
    ]


async def test_run_once_de_un_job_inexistente_da_2_y_lista_los_registrados(
    con_prueba: Settings,
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert worker_main.main(["--run-once", "no_existe"]) == 2

    salida = capsys.readouterr()
    assert "expirations" in salida.out + salida.err
    assert await _corridas(session_factory) == []


async def test_run_once_con_una_corrida_vigente_da_3(
    con_prueba: Settings, session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    async with session_factory() as sesion:
        vigente = await make_job_run(
            sesion,
            "expirations",
            HOY,
            result="running",
            started_at=reloj_worker.now_utc() - timedelta(minutes=5),
        )

    assert worker_main.main(["--run-once", "expirations"]) == 3

    corridas = await _corridas(session_factory)
    assert [(c.id, c.result, c.started_at) for c in corridas] == [
        (vigente.id, "running", vigente.started_at)
    ]


# --date y --simulate (S4A-D48, E5) ----------------------------------------------------------------


async def test_date_distinta_de_hoy_sin_simulate_da_2(
    con_prueba: Settings,
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert worker_main.main(["--run-once", "expirations", "--date", FUTURA.isoformat()]) == 2

    salida = capsys.readouterr()
    assert "--simulate" in salida.out + salida.err
    assert await _corridas(session_factory) == []


async def test_date_con_simulate_en_dev_y_apex_test_simula_el_dia(
    con_prueba: Settings,
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    argv = ["--run-once", "expirations", "--date", FUTURA.isoformat(), "--simulate"]

    assert worker_main.main(argv) == 0

    primera_linea = capsys.readouterr().out.splitlines()[0]
    assert primera_linea == f"RELOJ SIMULADO: {FUTURA.isoformat()}"
    assert any(
        r.levelno == logging.WARNING and r.getMessage() == "clock override" for r in caplog.records
    )
    corridas = await _corridas(session_factory)
    assert [(c.job_name, c.run_date, c.result) for c in corridas] == [
        ("expirations_sim", FUTURA, "ok")
    ]
    assert corridas[0].started_at == MEDIODIA_FUTURA_UTC
    assert corridas[0].details["clock_override"] is True
    assert corridas[0].details["revisados"] == 0


async def test_date_con_simulate_y_env_production_da_2(
    usar_settings: Any,
    settings_prueba: Settings,
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
) -> None:
    usar_settings(settings_prueba.model_copy(update={"ENV": "production"}))
    argv = ["--run-once", "expirations", "--date", FUTURA.isoformat(), "--simulate"]

    assert worker_main.main(argv) == 2
    assert await _corridas(session_factory) == []


async def test_date_con_simulate_contra_la_base_viva_da_2(
    usar_settings: Any,
    settings_prueba: Settings,
    reloj_worker: FrozenClock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    usar_settings(_con_base(settings_prueba, "apex"))
    argv = ["--run-once", "expirations", "--date", FUTURA.isoformat(), "--simulate"]

    assert worker_main.main(argv) == 2
    salida = capsys.readouterr()
    assert "RELOJ SIMULADO" not in salida.out


async def test_date_igual_a_hoy_sin_simulate_corre_normal(
    con_prueba: Settings, session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    assert worker_main.main(["--run-once", "expirations", "--date", HOY.isoformat()]) == 0

    corridas = await _corridas(session_factory)
    assert [(c.job_name, c.run_date) for c in corridas] == [("expirations", HOY)]
    assert "clock_override" not in corridas[0].details


async def test_date_invalida_da_2(con_prueba: Settings, reloj_worker: FrozenClock) -> None:
    assert worker_main.main(["--run-once", "expirations", "--date", "2026-13-40"]) == 2


@pytest.mark.parametrize(
    ("objetivo", "simulate", "env", "base", "aceptada"),
    [
        (HOY, False, "dev", "apex", True),
        (HOY, False, "production", "apex", True),
        (FUTURA, False, "dev", "apex_test", False),
        (FUTURA, True, "production", "apex_sim", False),
        (FUTURA, True, "dev", "apex", False),
        (FUTURA, True, "dev", "apex_simx", False),
        (FUTURA, True, "dev", "apex_test_copia", False),
        (FUTURA, True, "dev", "apex_sim", True),
        (FUTURA, True, "dev", "apex_test", True),
        (HOY - timedelta(days=1), True, "dev", "apex_sim", True),
    ],
    ids=[
        "hoy_dev",
        "hoy_produccion",
        "sin_simulate",
        "produccion",
        "base_viva",
        "sufijo_falso",
        "test_con_sufijo",
        "copia_sim",
        "apex_test",
        "ayer_en_copia",
    ],
)
def test_guarda_dura_de_date(
    settings_prueba: Settings,
    objetivo: date,
    simulate: bool,
    env: str,
    base: str,
    aceptada: bool,
) -> None:
    settings = _con_base(settings_prueba, base).model_copy(update={"ENV": env})

    error = clock_override_error(objetivo, HOY, simulate=simulate, settings=settings)

    assert (error is None) is aceptada, error
    if not aceptada:
        assert isinstance(error, str) and error


@pytest.mark.parametrize(
    "argv",
    [["--date", "2026-11-01"], ["--simulate"], ["--status", "expirations", "--simulate"]],
    ids=["date_suelta", "simulate_suelto", "status_con_simulate"],
)
def test_date_y_simulate_sin_run_once_dan_2(con_prueba: Settings, argv: list[str]) -> None:
    assert worker_main.main(argv) == 2


def test_run_once_y_status_juntos_dan_2(con_prueba: Settings) -> None:
    assert worker_main.main(["--run-once", "expirations", "--status", "expirations"]) == 2


async def test_simulate_con_la_fecha_de_hoy_tambien_exige_dev_y_base_de_simulacion(
    usar_settings: Any,
    settings_prueba: Settings,
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
) -> None:
    usar_settings(_con_base(settings_prueba, "apex"))

    assert worker_main.main(["--run-once", "expirations", "--simulate"]) == 2
    assert await _corridas(session_factory) == []


# --status -----------------------------------------------------------------------------------------


async def test_status_imprime_el_ultimo_intento_sin_attempts(
    con_prueba: Settings,
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    intento = {"started_at": "x", "finished_at": "x", "result": "ok", "error": None}
    async with session_factory() as sesion:
        fila = await make_job_run(
            sesion, "expirations", HOY, details={"placeholder_ok": 1, "attempts": [intento]}
        )

    assert worker_main.main(["--status", "expirations"]) == 0

    datos = _json_de_status(capsys.readouterr().out)
    assert set(datos) == CAMPOS_STATUS
    assert datos["id"] == str(fila.id)
    assert (datos["job_name"], datos["run_date"], datos["result"]) == (
        "expirations",
        HOY.isoformat(),
        "ok",
    )
    assert datos["details"] == {"placeholder_ok": 1}


async def test_status_sin_corridas_da_2(
    con_prueba: Settings, session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    assert worker_main.main(["--status", "expirations"]) == 2


async def test_status_de_la_simulada(
    con_prueba: Settings,
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with session_factory() as sesion:
        await make_job_run(sesion, "expirations", HOY)
        simulada = await make_job_run(
            sesion, "expirations_sim", FUTURA, details={"clock_override": True}
        )

    assert worker_main.main(["--status", "expirations_sim"]) == 0

    datos = _json_de_status(capsys.readouterr().out)
    assert datos["id"] == str(simulada.id)
    assert datos["details"] == {"clock_override": True}


# wait_for_database, latido y serve ---------------------------------------------------------------


class _Corte(Exception):
    """El `sleep` falso corta la espera infinita tras unas cuantas vueltas."""


def _sleep_espia(esperas: list[float], *, cortar_tras: int) -> Any:
    async def dormir(segundos: float) -> None:
        esperas.append(segundos)
        if len(esperas) >= cortar_tras:
            raise _Corte

    return dormir


async def test_wait_for_database_con_la_base_lista_no_espera(settings_prueba: Settings) -> None:
    esperas: list[float] = []

    await wait_for_database(settings_prueba, sleep=_sleep_espia(esperas, cortar_tras=1))

    assert esperas == []


async def test_wait_for_database_reintenta_1_2_4_con_tope_de_60(settings_prueba: Settings) -> None:
    esperas: list[float] = []
    sin_base = _con_base(settings_prueba, "apex_no_existe")

    with pytest.raises(_Corte):
        await wait_for_database(sin_base, sleep=_sleep_espia(esperas, cortar_tras=9))

    assert esperas == [1, 2, 4, 8, 16, 32, 60, 60, 60]


async def test_touch_heartbeat_con_la_base_lista_escribe_el_latido(
    session_factory: Fabrica, latido_tmp: Path
) -> None:
    assert await touch_heartbeat_if_db_ok(session_factory, latido_tmp) is True
    assert latido_tmp.exists()  # noqa: ASYNC240


async def test_touch_heartbeat_con_la_base_caida_no_escribe_ni_propaga(
    settings_prueba: Settings, latido_tmp: Path
) -> None:
    url = _con_base(settings_prueba, "apex_no_existe").DATABASE_URL.get_secret_value()
    motor = create_async_engine(url)
    try:
        rota = async_sessionmaker(motor, expire_on_commit=False)
        assert await touch_heartbeat_if_db_ok(rota, latido_tmp) is False
    finally:
        await motor.dispose()
    assert not latido_tmp.exists()  # noqa: ASYNC240


async def test_serve_con_la_parada_disparada_escribe_el_latido_y_sale_0(
    settings_prueba: Settings,
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    latido_tmp: Path,
) -> None:
    reloj_worker.set(
        datetime(2026, 10, 21, 11, 0, tzinfo=UTC)
    )  # 06:00 de Bogotá: nada que recuperar
    parada = asyncio.Event()
    parada.set()

    assert await worker_main.serve(settings_prueba, stop=parada) == 0

    assert latido_tmp.exists()  # noqa: ASYNC240
    assert runtime.HEARTBEAT_PATH == latido_tmp
    assert await _corridas(session_factory) == []


# Proceso limpio: gate de pagos registrado (load_module_services) --------------------------------

_PROGRAMA = (
    "import sys\n"
    "from app.worker import main as m\n"
    "codigo = m.main(['--run-once', 'expirations'])\n"
    "from app.modules.payments import service as p\n"
    "from app.modules.memberships import service as ms\n"
    "assert p.membership_gate() is ms.membership_payability, 'gate sin registrar'\n"
    "sys.exit(codigo)\n"
)


async def test_en_un_proceso_limpio_run_once_carga_los_services(
    settings_prueba: Settings, session_factory: Fabrica, tmp_path: Path
) -> None:
    assert (tmp_path / ".env").is_file()  # lo escribe `settings_prueba`

    resultado = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-I", "-c", _PROGRAMA],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr[-2000:]
    corridas = await _corridas(session_factory)
    assert [(c.job_name, c.result) for c in corridas] == [("expirations", "ok")]


# Revisiones de B1 (S4A-D79, S4A-D83, S4A-D84) ---------------------------------------------------


async def test_recuperacion_y_disparo_concurrentes_no_se_solapan_y_corren_una_vez(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    activos: list[int] = []
    maximo = 0
    corridas = 0

    async def lento(ctx: JobContext) -> JobResult:
        nonlocal maximo, corridas
        corridas += 1
        activos.append(1)
        maximo = max(maximo, len(activos))
        await asyncio.sleep(0.2)
        activos.pop()
        return JobResult(ok=True, details={"revisados": 0})

    spec = JobSpec(name="prueba_lenta_ciclo", run=lento, hour=7, minute=0)
    ciclos = runtime.CycleTasks(session_factory, lambda: (spec,))

    await asyncio.gather(ciclos.cycle(), ciclos.cycle())

    assert (corridas, maximo) == (1, 1)
    filas = await _corridas(session_factory)
    assert [(f.job_name, f.result, len(f.details["attempts"])) for f in filas] == [
        ("prueba_lenta_ciclo", "ok", 1)
    ]


async def test_un_fallo_inesperado_del_ciclo_queda_en_el_log_solo_con_el_tipo(
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def roto(*args: object, **kwargs: object) -> list[object]:
        raise RuntimeError("documento 1020304417")

    monkeypatch.setattr(runtime, "run_cycle", roto)
    caplog.set_level(logging.DEBUG)

    await runtime.CycleTasks(session_factory, lambda: ()).cycle()

    errores = [r for r in caplog.records if r.getMessage() == "worker cycle failed"]
    assert len(errores) == 1 and errores[0].__dict__["error_type"] == "RuntimeError"
    assert all("1020304417" not in str(vars(r)) for r in caplog.records)


async def test_serve_registra_el_fallo_de_la_recuperacion_y_sale_0(
    settings_prueba: Settings,
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    latido_tmp: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def recuperacion_rota(self: object) -> None:
        raise RuntimeError("documento 1020304417")

    monkeypatch.setattr(runtime.CycleTasks, "cycle", recuperacion_rota)
    caplog.set_level(logging.DEBUG)
    parada = asyncio.Event()
    parada.set()

    assert await worker_main.serve(settings_prueba, stop=parada) == 0

    errores = [r for r in caplog.records if r.getMessage() == "worker recovery failed"]
    assert len(errores) == 1 and errores[0].__dict__["error_type"] == "RuntimeError"
    assert all("1020304417" not in str(vars(r)) for r in caplog.records)


async def test_run_once_con_la_base_caida_al_cerrar_sale_1_sin_traza(
    con_prueba: Settings,
    session_factory: Fabrica,
    reloj_worker: FrozenClock,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def cierre_roto(*args: object, **kwargs: object) -> None:
        raise ConnectionError("documento 1020304417")

    monkeypatch.setattr(runner, "finish_run", cierre_roto)
    caplog.set_level(logging.DEBUG)

    assert worker_main.main(["--run-once", "expirations"]) == 1

    salida = capsys.readouterr()
    assert "1020304417" not in salida.out + salida.err
    assert "Traceback" not in salida.out + salida.err
    fallos = [r for r in caplog.records if r.getMessage() == "job run failed"]
    assert len(fallos) == 1 and fallos[0].__dict__["error_type"] == "ConnectionError"
    assert all(r.exc_info is None for r in caplog.records)
    assert all("1020304417" not in str(vars(r)) for r in caplog.records)
