"""`--db-timeouts off` del CLI (S3-W0-2; S3-D43, E7 y E16; PL1 de la revisión de Fase 4 del
Sprint 3).

La opción es global (`@app.callback()` de Typer, va antes del comando) y deja las opciones de la
invocación en `ctx.obj` (`RuntimeOptions`), nunca en un estado de proceso: cada comando que abre
la base las pasa a `cli_runtime(settings, options)`. Con `off`, el engine del comando se
construye con los tres `DB_*_TIMEOUT_MS` en 0 (`rotate-key`, `sign-audit` y la importación de
US-112 sobre muchas filas); sin la opción, o con `on`, conservan el valor de `Settings`.

Se prueba con `create_engine_from` parcheado (corta antes de abrir ninguna conexión): directo
sobre `cli_runtime`, sobre el callback con un Typer de prueba que lee `ctx.obj`, y de punta a
punta con `unlock-user` e `issue-reset-link` (con `get_settings` cambiado por `export_settings`).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import typer
from sqlalchemy.ext.asyncio import AsyncEngine
from typer.testing import CliRunner

from app import cli
from app.cli import RuntimeOptions, app, export_settings
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


@pytest.fixture
def vistos(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Settings]]:
    """`create_engine_from` falso: guarda el `Settings` que recibe y corta el comando."""
    capturados: list[Settings] = []

    def falso(settings: Settings) -> AsyncEngine:
        capturados.append(settings)
        raise _EngineCapturado

    monkeypatch.setattr(db, "create_engine_from", falso)
    yield capturados


async def _settings_del_engine(base: Settings, options: RuntimeOptions | None) -> Settings:
    capturados: list[Settings] = []

    def falso(settings: Settings) -> AsyncEngine:
        capturados.append(settings)
        raise _EngineCapturado

    with pytest.MonkeyPatch.context() as parche:
        parche.setattr(db, "create_engine_from", falso)
        with pytest.raises(_EngineCapturado):
            async with cli.cli_runtime(base, options):
                pass  # pragma: no cover - el engine falso corta antes de ceder la sesión
    assert len(capturados) == 1
    return capturados[0]


def _tiempos(settings: Settings) -> dict[str, int]:
    return {nombre: getattr(settings, nombre) for nombre in DEFAULTS}


# `cli_runtime` con las opciones de la invocación -------------------------------------------------


async def test_db_timeouts_off_pone_los_tres_en_cero() -> None:
    base = export_settings()
    usado = await _settings_del_engine(base, RuntimeOptions(db_timeouts=False))
    assert _tiempos(usado) == CEROS
    assert usado.DATABASE_URL.get_secret_value() == base.DATABASE_URL.get_secret_value()
    assert _tiempos(base) == DEFAULTS, "el Settings recibido no se muta"


@pytest.mark.parametrize("options", [None, RuntimeOptions(), RuntimeOptions(db_timeouts=True)])
async def test_sin_off_conservan_el_valor_por_defecto(options: RuntimeOptions | None) -> None:
    usado = await _settings_del_engine(export_settings(), options)
    assert _tiempos(usado) == DEFAULTS


async def test_sin_off_respeta_los_tiempos_de_settings() -> None:
    """Sin `off`, el engine usa los tiempos que traiga `Settings` (no los del código)."""
    propios = export_settings().model_copy(update={"DB_LOCK_TIMEOUT_MS": 2500})
    usado = await _settings_del_engine(propios, RuntimeOptions())
    assert usado.DB_LOCK_TIMEOUT_MS == 2500


def test_las_opciones_son_inmutables() -> None:
    with pytest.raises(AttributeError):
        RuntimeOptions().db_timeouts = False  # type: ignore[misc]


# El callback deja las opciones en `ctx.obj` (PL1) ------------------------------------------------


def _con_sonda() -> tuple[typer.Typer, list[Any]]:
    """Un Typer con el callback real del CLI y un comando que guarda `ctx.obj`."""
    prueba = typer.Typer()
    prueba.callback()(cli.main)
    vistos: list[Any] = []

    @prueba.command()
    def sonda(ctx: typer.Context) -> None:
        vistos.append(ctx.obj)

    return prueba, vistos


@pytest.mark.parametrize(
    ("opciones", "esperado"),
    [
        (["--db-timeouts", "off"], RuntimeOptions(db_timeouts=False)),
        (["--db-timeouts", "on"], RuntimeOptions(db_timeouts=True)),
        ([], RuntimeOptions(db_timeouts=True)),
    ],
)
def test_el_callback_deja_las_opciones_en_ctx_obj(
    opciones: list[str], esperado: RuntimeOptions
) -> None:
    prueba, vistos = _con_sonda()
    resultado = runner.invoke(prueba, [*opciones, "sonda"])
    assert resultado.exit_code == 0, resultado.output
    assert vistos == [esperado]


def test_el_cli_no_guarda_estado_de_proceso() -> None:
    """PL1: ya no existe el global mutable `_runtime_options`."""
    assert not hasattr(cli, "_runtime_options")


# De punta a punta: los comandos que abren la base pasan `ctx.obj` --------------------------------


COMANDOS = [
    ["unlock-user", "alguien@apex.local", "--as", "admin@apex.local"],
    ["issue-reset-link", "alguien@apex.local", "--as", "admin@apex.local"],
]


@pytest.mark.parametrize("comando", COMANDOS, ids=lambda c: c[0])
def test_off_llega_al_engine_del_comando_y_no_se_arrastra(
    comando: list[str], vistos: list[Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "get_settings", export_settings)
    apagado = runner.invoke(app, ["--db-timeouts", "off", *comando])
    assert isinstance(apagado.exception, _EngineCapturado), apagado.output
    sin_opcion = runner.invoke(app, comando)
    assert isinstance(sin_opcion.exception, _EngineCapturado), sin_opcion.output
    assert [_tiempos(s) for s in vistos] == [CEROS, DEFAULTS]


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
