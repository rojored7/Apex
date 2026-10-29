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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from app import cli, cli_base
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.crypto.models import CryptoOp
from app.modules.members.models import Member

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


async def conteos_de_tablas(session: AsyncSession) -> dict[str, int]:
    """Filas de `members`, `audit_log` y `crypto_ops` (S4B-B1): "no escribió nada" / "no cambió"."""
    return {
        "members": int(await session.scalar(select(func.count()).select_from(Member)) or 0),
        "audit_log": int(await session.scalar(select(func.count()).select_from(AuditEntry)) or 0),
        "crypto_ops": int(await session.scalar(select(func.count()).select_from(CryptoOp)) or 0),
    }
