"""`0020_notifications_indexes` (S5-V8, S5-D255). # Rojo V8

Padre `0019_notifications`; es head. Tres índices, reversibles:
- `ix_notifications_membership_id` en `notifications.notifications (membership_id)`;
- `ix_members_created_at_id` en `members.members (created_at, id)`;
- `ix_payments_paid_at_id` en `payments.payments (paid_at, id)`.
El `downgrade` los borra y no toca datos.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.migrations._apoyo_notificaciones import consultar

REVISION = "0020_notifications_indexes"
PADRE = "0019_notifications"
INDICES: dict[str, tuple[str, str, str]] = {
    "ix_notifications_membership_id": ("notifications", "notifications", "(membership_id)"),
    "ix_members_created_at_id": ("members", "members", "(created_at, id)"),
    "ix_payments_paid_at_id": ("payments", "payments", "(paid_at, id)"),
}


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


def _indices(url: str) -> dict[str, str]:
    filas = consultar(
        url,
        "SELECT indexname, schemaname, tablename, indexdef FROM pg_indexes "
        "WHERE indexname = ANY($1::text[])",
        list(INDICES),
    )
    return {f["indexname"]: f"{f['schemaname']}.{f['tablename']} {f['indexdef']}" for f in filas}


def test_la_revision_cuelga_de_0019_y_es_head(alembic_config: Config) -> None:
    _revision_existe(alembic_config)
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    assert scripts.get_heads() == [REVISION]


def test_tras_upgrade_head_existen_los_tres_indices(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    reales = _indices(migrated_database)
    assert set(reales) == set(INDICES)
    for nombre, (esquema, tabla, columnas) in INDICES.items():
        assert reales[nombre].startswith(f"{esquema}.{tabla} "), nombre
        assert f"{columnas}" in reales[nombre], reales[nombre]
        assert "UNIQUE" not in reales[nombre]


def test_ciclo_downgrade_a_0019_borra_los_indices_y_vuelve_a_crearlos(
    alembic_config: Config, migrated_database: str
) -> None:
    _revision_existe(alembic_config)
    command.downgrade(alembic_config, PADRE)
    try:
        assert _indices(migrated_database) == {}
    finally:
        command.upgrade(alembic_config, "head")
    assert set(_indices(migrated_database)) == set(INDICES)
