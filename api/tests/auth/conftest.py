"""Fixtures de `tests/auth` (S2-B2)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.config import Settings
from tests.auth._sesion import EspiaArgon2
from tests.conftest import SleeperEspia


@pytest.fixture(autouse=True)
def _sin_piso_de_login(sleeper_nulo: SleeperEspia) -> SleeperEspia:
    """Ninguna prueba de auth duerme el piso de S2-D39; las que lo miden piden `sleeper_nulo`."""
    return sleeper_nulo


@pytest.fixture
def espia_argon2(seguridad: Settings) -> Iterator[EspiaArgon2]:
    """Cuenta verificaciones de argon2 (M-6); depende de `seguridad` para quitarse antes."""
    espia = EspiaArgon2()
    espia.instalar()
    try:
        yield espia
    finally:
        espia.quitar()
