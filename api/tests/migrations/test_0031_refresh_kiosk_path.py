"""`0031_refresh_kiosk_path` (S7-C4, S7-D41): `auth.refresh_tokens.kiosk_path` con su CHECK."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.migrations._apoyo_notificaciones import CHECK_VIOLATION, consultar, resultados

REVISION = "0031_refresh_kiosk_path"
PADRE = "0030_memberships_end_guard"
CHECK = "ck_refresh_tokens_kiosk_path_shape"
COLUMNA = (
    "SELECT data_type, is_nullable FROM information_schema.columns "
    "WHERE table_schema = 'auth' AND table_name = 'refresh_tokens' AND column_name = 'kiosk_path'"
)


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> Iterator[str]:
    yield migrated_database


def test_la_revision_cuelga_de_0030_tiene_id_corto_y_es_head(alembic_config: Config) -> None:
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    assert REVISION in {r.revision for r in scripts.iterate_revisions("head", "base")}


def test_la_columna_es_texto_y_admite_nulo(base: str) -> None:
    (fila,) = consultar(base, COLUMNA)
    assert fila["data_type"] == "text" and fila["is_nullable"] == "YES"


def test_el_check_acepta_el_checkin_y_nulo_y_rechaza_el_resto(base: str) -> None:
    usuario = "00000000-0000-0000-0000-000000000001"

    def alta(path: str | None) -> tuple[str, list[object]]:
        return (
            "INSERT INTO auth.refresh_tokens (id, created_by, user_id, token_hash, expires_at, "
            "kiosk_path) VALUES ($1, $2, $2, $3, now() + interval '1 day', $4)",
            [uuid4(), UUID(usuario), uuid4().hex, path],
        )

    buenas = [None, f"/clases/{uuid4()}/checkin"]
    malas = ["/panel", f"/clases/{str(uuid4()).upper()}/checkin", f"/clases/{uuid4()}/checkin/x"]
    for path in buenas:
        assert resultados(base, [[alta(path)]]) == [("", None)]
    for path in malas:
        assert resultados(base, [[alta(path)]]) == [(CHECK_VIOLATION, CHECK)]


def test_ciclo_head_base_head(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert consultar(base, COLUMNA) == []
    finally:
        command.upgrade(alembic_config, "head")
    assert len(consultar(base, COLUMNA)) == 1
