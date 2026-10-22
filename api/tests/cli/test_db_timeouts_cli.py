"""`--db-timeouts off` del CLI (S3-W0-2; S3-D43, E7 y E16).

La opción es global (`@app.callback()` de Typer, va antes del comando) y deja un estado de
proceso que `cli_runtime` consulta: con `off`, el engine del comando se construye con los tres
`DB_*_TIMEOUT_MS` en 0 (`rotate-key`, `sign-audit` y la importación de US-112 sobre muchas
filas); sin la opción, o con `on`, conservan el valor de `Settings`. Se prueba con
`export-openapi` (no toca la base) y con `create_engine_from` parcheado: `cli_runtime` no llega a
abrir ninguna conexión.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from typer.testing import CliRunner

from app import cli
from app.cli import app, export_settings
from app.core import db
from app.core.config import Settings

runner = CliRunner()
DEFAULTS = {
    "DB_LOCK_TIMEOUT_MS": 10000,
    "DB_STATEMENT_TIMEOUT_MS": 30000,
    "DB_IDLE_IN_TX_TIMEOUT_MS": 60000,
}
CEROS = dict.fromkeys(DEFAULTS, 0)


class _EngineCapturado(Exception):
    """Corta `cli_runtime` justo al pedir el engine, sin conexión."""


class Capturador:
    """Parchea `create_engine_from` solo alrededor de `cli_runtime` (`create_app`, que corre en
    `export-openapi`, también construye un engine): guarda el `Settings` que recibe y corta el
    comando sin abrir conexión."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch

    async def settings_del_engine(self, base: Settings) -> Settings:
        vistos: list[Settings] = []

        def falso(settings: Settings) -> AsyncEngine:
            vistos.append(settings)
            raise _EngineCapturado

        with self._monkeypatch.context() as parche:
            parche.setattr(db, "create_engine_from", falso)
            with pytest.raises(_EngineCapturado):
                async with cli.cli_runtime(base):
                    pass  # pragma: no cover - el engine falso corta antes de ceder la sesión
        assert len(vistos) == 1
        return vistos[0]


@pytest.fixture
def capturados(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Capturador]:
    """Al salir, una invocación sin la opción devuelve el estado del proceso a su defecto."""
    try:
        yield Capturador(monkeypatch)
    finally:
        runner.invoke(app, ["export-openapi", str(tmp_path / "restaurar.json")])


def _invocar(tmp_path: Path, *opciones: str) -> None:
    resultado = runner.invoke(app, [*opciones, "export-openapi", str(tmp_path / "o.json")])
    assert resultado.exit_code == 0, resultado.output
    assert (tmp_path / "o.json").is_file()


def _tiempos(settings: Settings) -> dict[str, int]:
    return {nombre: getattr(settings, nombre) for nombre in DEFAULTS}


async def test_db_timeouts_off_pone_los_tres_en_cero(
    capturados: Capturador, tmp_path: Path
) -> None:
    base = export_settings()
    _invocar(tmp_path, "--db-timeouts", "off")
    usado = await capturados.settings_del_engine(base)
    assert _tiempos(usado) == CEROS
    assert usado.DATABASE_URL.get_secret_value() == base.DATABASE_URL.get_secret_value()
    assert _tiempos(base) == DEFAULTS, "el Settings recibido no se muta"


async def test_sin_la_opcion_conservan_el_valor_por_defecto(
    capturados: Capturador, tmp_path: Path
) -> None:
    _invocar(tmp_path)
    usado = await capturados.settings_del_engine(export_settings())
    assert _tiempos(usado) == DEFAULTS


async def test_off_y_despues_sin_la_opcion_vuelve_al_valor_por_defecto(
    capturados: Capturador, tmp_path: Path
) -> None:
    """El estado es del proceso: cada invocación lo fija de nuevo (no se arrastra un `off`)."""
    _invocar(tmp_path, "--db-timeouts", "off")
    _invocar(tmp_path)
    usado = await capturados.settings_del_engine(export_settings())
    assert _tiempos(usado) == DEFAULTS


async def test_db_timeouts_on_es_el_valor_por_defecto(
    capturados: Capturador, tmp_path: Path
) -> None:
    _invocar(tmp_path, "--db-timeouts", "on")
    usado = await capturados.settings_del_engine(export_settings())
    assert _tiempos(usado) == DEFAULTS


async def test_sin_la_opcion_respeta_los_tiempos_de_settings(
    capturados: Capturador, tmp_path: Path
) -> None:
    """Sin la opción, el engine usa los tiempos que traiga `Settings` (no los del código)."""
    _invocar(tmp_path)
    propios = export_settings().model_copy(update={"DB_LOCK_TIMEOUT_MS": 2500})
    usado = await capturados.settings_del_engine(propios)
    assert usado.DB_LOCK_TIMEOUT_MS == 2500


def test_un_valor_desconocido_sale_con_2(tmp_path: Path) -> None:
    resultado = runner.invoke(
        app, ["--db-timeouts", "quizas", "export-openapi", str(tmp_path / "o.json")]
    )
    assert resultado.exit_code == 2
    assert not (tmp_path / "o.json").exists()


def test_la_opcion_aparece_en_la_ayuda() -> None:
    resultado = runner.invoke(app, ["--help"])
    assert resultado.exit_code == 0
    assert "--db-timeouts" in resultado.output
