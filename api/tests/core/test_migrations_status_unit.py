"""Ramas de `core/migrations_status.py` que la base real no alcanza (S4B-B4, Verde).

Sin base: se sustituye la lectura de `alembic_version` y se comprueba el colapso a los tres valores
públicos y lo que dice el log (la revisión sí, la URL nunca).
"""

from __future__ import annotations

import pytest

from app.core import migrations_status as ms


@pytest.fixture(autouse=True)
def _restaurar() -> object:
    antes = (ms._head, ms._known)
    yield None
    ms._head, ms._known = antes


def _leer(filas: list[str]) -> object:
    async def leer() -> list[str]:
        return filas

    return leer


async def test_sin_configurar_es_unknown() -> None:
    ms._head = None
    assert await ms.migrations_health() == "unknown"


@pytest.mark.parametrize("filas", [[], ["a", "b"]])
async def test_cero_o_dos_filas_son_unknown(
    monkeypatch: pytest.MonkeyPatch, filas: list[str]
) -> None:
    ms.configure_migrations("h", frozenset({"h"}))
    monkeypatch.setattr(ms, "_leer_filas", _leer(filas))
    assert await ms.migrations_health() == "unknown"


async def test_la_lectura_que_falla_es_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    ms.configure_migrations("h", frozenset({"h"}))

    async def falla() -> list[str]:
        raise OSError("sin conexión")

    monkeypatch.setattr(ms, "_leer_filas", falla)
    assert await ms.migrations_health() == "unknown"


@pytest.mark.parametrize(
    ("actual", "motivo"), [("viejo", "behind"), ("desconocida", "unknown_revision")]
)
async def test_mismatch_nombra_el_motivo_y_la_revision_en_el_log(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    actual: str,
    motivo: str,
) -> None:
    ms.configure_migrations("nuevo", frozenset({"nuevo", "viejo"}))
    monkeypatch.setattr(ms, "_leer_filas", _leer([actual]))
    with caplog.at_level("WARNING", logger="app.migrations_status"):
        assert await ms.migrations_health() == "mismatch"
    assert motivo in caplog.text and actual in caplog.text
    assert "postgresql" not in caplog.text


async def test_la_revision_del_log_se_recorta_y_no_lleva_caracteres_de_control() -> None:
    assert ms._para_log("a\nb" + "x" * 200) == "a?b" + "x" * (ms._MAX_REVISION_LOG - 3)
