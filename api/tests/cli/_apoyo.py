"""Apoyo de las pruebas del CLI (plan del Sprint 4A, sección 2, bloque B1; S4A-D39, S4A-D48).

`correr(app, args, env, *, base, monkeypatch)`: invoca el Typer `app` con `CliRunner`. Si `env`
no es `None`, el comando ve `base.model_copy(update={"ENV": env})` como su `Settings`
(`monkeypatch` de `app.cli.get_settings` y `app.cli_base.get_settings`, S4B-D29): nunca se toca
`os.environ`
(`tests/architecture/test_no_os_environ.py`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import pytest
import typer
from click.testing import Result
from typer.testing import CliRunner

from app import cli, cli_base
from app.core.config import Settings

_runner = CliRunner()


def correr(
    app: typer.Typer,
    args: Sequence[str],
    env: Literal["dev", "production"] | None = None,
    *,
    base: Settings | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> Result:
    """Corre el comando; con `env`, `get_settings()` del CLI devuelve `base` con ese `ENV`."""
    if env is not None:
        if base is None or monkeypatch is None:
            raise ValueError("con env hacen falta base y monkeypatch")
        efectivo = base.model_copy(update={"ENV": env})
        monkeypatch.setattr(cli, "get_settings", lambda: efectivo)
        monkeypatch.setattr(
            cli_base, "get_settings", lambda: efectivo
        )  # no-op prudente hoy (S4B-D29): ningún comando lee cli_base.get_settings aún
    return _runner.invoke(app, list(args))
