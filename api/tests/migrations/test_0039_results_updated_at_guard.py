"""`0039_results_updated_guard` (S8-B1d, L-9): `updated_at` de un resultado no retrocede.

Padre `0038_kiosk_results_path`. La guarda de `0037` dejaba `updated_at` libre; ahora exige
`NEW.updated_at >= OLD.updated_at` (el resto de la guarda no cambia).
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_WOD_RESULTS
from tests.migrations._apoyo_notificaciones import consultar, existe, resultados
from tests.migrations.test_0023_attachments import _ejecutar
from tests.migrations.test_0036_results_wod_results import TABLA, fila
from tests.migrations.test_0037_results_immutability import GUARDA, _upd

REVISION = "0039_results_updated_guard"
PADRE = "0038_kiosk_results_path"


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> Iterator[str]:
    scripts = ScriptDirectory.from_config(alembic_config)
    if scripts.get_revision(REVISION) is None:
        pytest.fail(f"no existe la revisión {REVISION}")
    try:
        yield migrated_database
    finally:
        if existe(migrated_database, TABLA):
            _ejecutar(migrated_database, LIMPIAR_WOD_RESULTS)


def test_cuelga_de_0038_y_tiene_id_corto(alembic_config: Config) -> None:
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_updated_at_no_retrocede(base: str) -> None:
    rid = uuid4()
    salidas = resultados(
        base,
        [
            [fila(id=rid), _upd(rid, "updated_at = now() - interval '1 day'")],
            [fila(id=rid), _upd(rid, "is_current = false, updated_at = now() - interval '1 day'")],
            [fila(id=rid), _upd(rid, "updated_at = now() + interval '1 day'")],
            [fila(id=rid), _upd(rid, "updated_at = updated_at")],
        ],
    )
    assert salidas[0] == (GUARDA, None)
    assert salidas[1] == (GUARDA, None)
    assert salidas[2] == ("", None)
    assert salidas[3] == ("", None)


def test_la_guarda_sigue_siempre_activa(base: str) -> None:
    (fila_trigger,) = consultar(
        base, "SELECT tgenabled FROM pg_trigger WHERE tgname = 'wod_results_guard_update'"
    )
    assert fila_trigger["tgenabled"] in {"A", b"A"}


def test_ciclo_downgrade_upgrade(alembic_config: Config, base: str) -> None:
    rid = uuid4()
    try:
        command.downgrade(alembic_config, PADRE)
        antes = resultados(
            base, [[fila(id=rid), _upd(rid, "updated_at = now() - interval '1 day'")]]
        )
        assert antes == [("", None)]  # sin 0039, `updated_at` volvía a ser libre
    finally:
        command.upgrade(alembic_config, "head")
    despues = resultados(base, [[fila(id=rid), _upd(rid, "updated_at = now() - interval '1 day'")]])
    assert despues == [(GUARDA, None)]
