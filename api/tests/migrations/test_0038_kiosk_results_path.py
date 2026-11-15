"""`0038_kiosk_results_path` (S8-B3, S8-D15, L-5): el CHECK de `kiosk_path` acepta `resultados`."""

from __future__ import annotations

import re
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.modules.auth.models import RefreshToken
from tests.migrations._apoyo_notificaciones import CHECK_VIOLATION, consultar, resultados

REVISION = "0038_kiosk_results_path"
PADRE = "0037_results_immutability"
CHECK = "ck_refresh_tokens_kiosk_path_shape"
SISTEMA = UUID("00000000-0000-0000-0000-000000000001")
DEFINICION = (
    "SELECT pg_get_constraintdef(c.oid) AS d FROM pg_constraint c "
    "WHERE c.conname = $1 AND c.conrelid = 'auth.refresh_tokens'::regclass"
)


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> Iterator[str]:
    yield migrated_database


def _alta(path: str | None) -> tuple[str, list[object]]:
    return (
        "INSERT INTO auth.refresh_tokens (id, created_by, user_id, token_hash, expires_at, "
        "kiosk_path) VALUES ($1, $2, $2, $3, now() + interval '1 day', $4)",
        [uuid4(), SISTEMA, uuid4().hex, path],
    )


def test_la_revision_cuelga_de_0037_tiene_id_corto_y_esta_en_la_cadena(
    alembic_config: Config,
) -> None:
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    assert REVISION in {r.revision for r in scripts.iterate_revisions("head", "base")}


def test_check_acepta_checkin_y_resultados(base: str) -> None:
    buenas = [None, f"/clases/{uuid4()}/checkin", f"/clases/{uuid4()}/resultados"]
    malas = [
        "/panel",
        f"/clases/{str(uuid4()).upper()}/resultados",
        f"/clases/{uuid4()}/resultados/x",
        f"/clases/{uuid4()}/otro",
        f"/clases/{uuid4()}/Resultados",
    ]
    for path in buenas:
        assert resultados(base, [[_alta(path)]]) == [("", None)], path
    for path in malas:
        assert resultados(base, [[_alta(path)]]) == [(CHECK_VIOLATION, CHECK)], path


def test_conserva_el_nombre_ck_refresh_tokens_kiosk_path_shape(base: str) -> None:
    filas = consultar(base, DEFINICION, CHECK)
    assert len(filas) == 1 and "resultados" in filas[0]["d"]
    otros = consultar(
        base,
        "SELECT conname FROM pg_constraint WHERE conrelid = 'auth.refresh_tokens'::regclass "
        "AND contype = 'c' AND conname LIKE '%kiosk%'",
    )
    assert [o["conname"] for o in otros] == [CHECK]


def test_modelo_y_migracion_dicen_lo_mismo(base: str) -> None:
    modelo = next(
        c
        for c in RefreshToken.__table__.constraints
        if str(getattr(c, "name", "")).endswith("kiosk_path_shape")
    )
    patron = re.search(r"~ '([^']+)'", str(modelo.sqltext))  # type: ignore[attr-defined]
    assert patron is not None
    en_base = re.search(r"~ '([^']+)'", consultar(base, DEFINICION, CHECK)[0]["d"])
    assert en_base is not None and en_base.group(1) == patron.group(1)


def test_downgrade_reescribe_resultados_a_checkin(alembic_config: Config, base: str) -> None:
    sesion = uuid4()
    token = uuid4().hex
    consultar(
        base,
        "INSERT INTO auth.refresh_tokens (id, created_by, user_id, token_hash, expires_at, "
        "kiosk_path) VALUES ($1, $2, $2, $3, now() + interval '1 day', $4) RETURNING id",
        uuid4(),
        SISTEMA,
        token,
        f"/clases/{sesion}/resultados",
    )
    try:
        command.downgrade(alembic_config, PADRE)
        (fila,) = consultar(
            base, "SELECT kiosk_path FROM auth.refresh_tokens WHERE token_hash = $1", token
        )
        assert fila["kiosk_path"] == f"/clases/{sesion}/checkin"
        assert "resultados" not in consultar(base, DEFINICION, CHECK)[0]["d"]
    finally:
        command.upgrade(alembic_config, "head")
        consultar(base, "DELETE FROM auth.refresh_tokens WHERE token_hash = $1 RETURNING id", token)


def test_ciclo_head_base_head(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert "resultados" not in consultar(base, DEFINICION, CHECK)[0]["d"]
    finally:
        command.upgrade(alembic_config, "head")
    assert "resultados" in consultar(base, DEFINICION, CHECK)[0]["d"]
