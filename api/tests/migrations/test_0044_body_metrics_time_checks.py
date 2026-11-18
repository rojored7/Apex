"""`0044_body_metrics_time_checks` (S9-V7b, L1). Padre `0043_athletes_personal_records`.

Dos CHECK de orden temporal en `athletes.body_metrics`: `voided_at >= created_at` (o NULL) y
`updated_at >= created_at`. Cada escenario corre en una transacción que se revierte; `23514` es el
error de un CHECK. El `downgrade` los quita y el `upgrade` los repone.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.migrations._apoyo_notificaciones import SYSTEM_USER_ID, Paso, consultar, resultados
from tests.migrations.test_0042_athletes_body_metrics import (
    TABLA,
    actualizar,
    insertar,
    llaves,
    medida,
)

REVISION = "0044_body_metrics_time_checks"
PADRE = "0043_athletes_personal_records"
CHECK = "23514"
OK = ("", None)
NOMBRES = ("ck_body_metrics_voided_after_created", "ck_body_metrics_updated_after_created")


def _escenario(*pasos: Paso) -> list[Paso]:
    return [*llaves(), *pasos]


def _correr(url: str, *escenarios: Sequence[Paso]) -> list[tuple[str, str | None]]:
    return resultados(url, [list(e) for e in escenarios])


def _checks(url: str) -> list[str]:
    filas = consultar(
        url,
        "SELECT conname FROM pg_constraint WHERE conrelid = to_regclass($1) AND contype = 'c' "
        "AND conname = ANY($2::text[]) ORDER BY conname",
        TABLA,
        list(NOMBRES),
    )
    return [f["conname"] for f in filas]


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> str:
    return migrated_database


def test_cuelga_de_0043_y_esta_en_la_cadena_de_head(alembic_config: Config) -> None:
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_crea_los_dos_check(base: str) -> None:
    assert _checks(base) == sorted(NOMBRES)


def test_una_anulacion_anterior_a_la_creacion_viola_el_check(base: str) -> None:
    id_ = uuid4()
    atrasada = _escenario(
        insertar(medida(id=id_)),
        actualizar(
            id_, "voided_at = created_at - interval '1 second', voided_by = $2", SYSTEM_USER_ID
        ),
    )
    a_tiempo = _escenario(
        insertar(medida(id=id_)),
        actualizar(id_, "voided_at = created_at, voided_by = $2", SYSTEM_USER_ID),
    )

    salidas = _correr(base, atrasada, a_tiempo)

    assert salidas == [(CHECK, NOMBRES[0]), OK]


def test_updated_at_anterior_a_created_at_viola_el_check(base: str) -> None:
    fila = medida(
        created_at=datetime(2026, 10, 21, 10, tzinfo=UTC),
        updated_at=datetime(2026, 10, 21, 9, tzinfo=UTC),
    )

    (salida,) = _correr(base, _escenario(insertar(fila)))

    assert salida == (CHECK, NOMBRES[1])


def test_downgrade_quita_los_check_y_el_upgrade_los_repone(
    alembic_config: Config, base: str
) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert _checks(base) == []
    finally:
        command.upgrade(alembic_config, "head")
    assert _checks(base) == sorted(NOMBRES)
