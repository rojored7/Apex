"""Kit de pruebas de `tests/core` (S4B-B2).

- `health_cache_limpia` (autouse): `clear_health_cache()` antes y después de cada prueba, para que
  la caché de `/health` (S4B-D60) no pase de una prueba a otra.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.health import clear_health_cache


@pytest.fixture(autouse=True)
def health_cache_limpia() -> Iterator[None]:
    clear_health_cache()
    try:
        yield
    finally:
        clear_health_cache()
