"""Endurecimiento de `0008_memberships` tras la revisión de seguridad de S3-B1 (hallazgo L1).

- `guard_identity` también rechaza cambiar `id`, `created_at` y `created_by` (23000,
  `memberships_identity`): un `id` reescrito dejaría pagos huérfanos (`payments.membership_id`
  no tiene FK) y `created_*` son datos de la auditoría;
- `ck_memberships_cancel_fields_only_when_cancelled` (23514): motivo, quién y cuándo de anulación
  solo en una `cancelled`, por `INSERT` y por `UPDATE` (el CHECK `cancelled_has_reason` cubre el
  sentido contrario).
Usa las ayudas de `test_0008_memberships.py` (SQL crudo con asyncpg; cada escenario se revierte).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic.config import Config

from tests.migrations.test_0008_memberships import (
    CHECK_VIOLATION,
    IDENTIDAD,
    INTEGRITY_VIOLATION,
    SYSTEM_USER_ID,
    T_ANULADA,
    _fila,
    _insert,
    _resultado,
    _revision_existe,
    _update,
)


@pytest.mark.parametrize(
    ("asignacion", "valor"),
    [
        ("id = $2", uuid4()),
        ("created_by = $2", uuid4()),
        ("created_at = $2", datetime(2020, 1, 1, tzinfo=UTC)),
    ],
    ids=["id", "quien-creo", "cuando-se-creo"],
)
def test_guard_identity_rechaza_cambiar_id_y_datos_de_alta(
    alembic_config: Config, migrated_database: str, asignacion: str, valor: object
) -> None:
    _revision_existe(alembic_config)
    fila = _fila()
    assert _resultado(migrated_database, _insert(fila), _update(fila["id"], asignacion, valor)) == (
        INTEGRITY_VIOLATION,
        IDENTIDAD,
    )


@pytest.mark.parametrize(
    "cambios",
    [
        {"cancel_reason": "Se mudó de ciudad"},
        {"cancelled_by": SYSTEM_USER_ID},
        {"cancelled_at": T_ANULADA},
    ],
    ids=["motivo", "quien", "cuando"],
)
def test_datos_de_anulacion_solo_en_una_cancelada(
    alembic_config: Config, migrated_database: str, cambios: dict[str, object]
) -> None:
    _revision_existe(alembic_config)
    assert _resultado(migrated_database, _insert(_fila(**cambios)))[0] == CHECK_VIOLATION
    fila = _fila()
    columna, valor = next(iter(cambios.items()))
    actualizar = _update(fila["id"], f"{columna} = $2", valor)
    assert _resultado(migrated_database, _insert(fila), actualizar)[0] == CHECK_VIOLATION
