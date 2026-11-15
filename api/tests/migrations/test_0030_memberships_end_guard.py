"""`0030_memberships_end_guard` (S7-C2b, revisión de C2, L2 y L3). Rojo C2b.

Padre `0029_memberships_orig_end_date`. Dos cambios:
- CHECK `ck_memberships_original_end_date_after_end` (`original_end_date IS NULL OR
  original_end_date > end_date`): un recorte siempre deja el fin ANTES del original (L2). El CHECK
  de `0029` (`needs_classes`) sigue. Con una consulta previa que aborta con el conteo.
- `memberships.guard_identity()` congela también `original_end_date` en las filas anuladas (L3).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.conftest import LIMPIAR_MEMBERSHIPS
from tests.migrations._apoyo_notificaciones import CHECK_VIOLATION, consultar, resultados
from tests.migrations.test_0023_attachments import _ejecutar

REVISION = "0030_memberships_end_guard"
PADRE = "0029_memberships_orig_end_date"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
CHECK = "ck_memberships_original_end_date_after_end"
INTEGRITY = "23000"
EXISTE_CHECK = (
    "SELECT 1 FROM pg_constraint WHERE conname = 'ck_memberships_original_end_date_after_end'"
)

Paso = tuple[str, list[Any]]

ALTA_PLAN = (
    "INSERT INTO plans.plans (id, created_by, name, price_cop, kind, duration_days, class_count, "
    "is_active) VALUES ($1, $2, $3, 100000, 'classes', 60, 12, true)"
)
ALTA_MEMBRESIA = (
    "INSERT INTO memberships.memberships (id, created_by, member_id, plan_id, agreed_price_cop, "
    "start_date, end_date, classes_total, classes_remaining, status, original_end_date) "
    "VALUES ($1, $2, $3, $4, 100000, '2026-10-01', '2026-11-30', 12, 3, 'active', $5)"
)


def _revision_existe(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> Iterator[str]:
    _revision_existe(alembic_config)
    yield migrated_database


def _plan() -> tuple[UUID, Paso]:
    plan = uuid4()
    return plan, (ALTA_PLAN, [plan, SYSTEM_USER_ID, f"Prueba 0030 {plan}"])


def _membresia(plan: UUID, socio: UUID, original: date | None) -> tuple[UUID, Paso]:
    ident = uuid4()
    return ident, (ALTA_MEMBRESIA, [ident, SYSTEM_USER_ID, socio, plan, original])


def test_la_revision_cuelga_de_0029_tiene_id_corto_y_esta_en_la_cadena(
    alembic_config: Config,
) -> None:
    _revision_existe(alembic_config)
    assert len(REVISION) <= 32
    scripts = ScriptDirectory.from_config(alembic_config)
    revision = scripts.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE
    (head,) = scripts.get_heads()
    assert REVISION in {r.revision for r in scripts.iterate_revisions(head, "base")}


def test_el_original_debe_ser_posterior_al_fin(base: str) -> None:
    """L2: `original_end_date` igual o anterior a `end_date` viola el CHECK; posterior pasa."""
    socio = uuid4()
    plan, alta_plan = _plan()
    escenarios = [
        [alta_plan, _membresia(plan, socio, date(2026, 11, 30))[1]],  # igual al fin
        [alta_plan, _membresia(plan, socio, date(2026, 11, 1))[1]],  # anterior
        [alta_plan, _membresia(plan, socio, date(2026, 12, 15))[1]],  # posterior
        [alta_plan, _membresia(plan, socio, None)[1]],  # no recortada
    ]
    assert resultados(base, escenarios) == [
        (CHECK_VIOLATION, CHECK),
        (CHECK_VIOLATION, CHECK),
        ("", None),
        ("", None),
    ]


def test_el_check_de_0029_sigue(base: str) -> None:
    nombres = {
        f["conname"]
        for f in consultar(
            base,
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'memberships.memberships'::regclass AND contype = 'c'",
        )
    }
    assert {"ck_memberships_original_end_date_needs_classes", CHECK} <= nombres


def test_una_anulada_no_cambia_su_original_end_date(base: str) -> None:
    """L3: el guard de identidad congela `original_end_date` en una fila `cancelled`; en una viva
    sí se puede mover."""
    socio = uuid4()
    plan, alta_plan = _plan()
    ident, alta = _membresia(plan, socio, date(2026, 12, 15))
    anular: Paso = (
        "UPDATE memberships.memberships SET status = 'cancelled', cancel_reason = 'Motivo largo', "
        "cancelled_by = $2, cancelled_at = now() WHERE id = $1",
        [ident, SYSTEM_USER_ID],
    )
    mover_viva: Paso = (
        "UPDATE memberships.memberships SET original_end_date = '2027-01-10' WHERE id = $1",
        [ident],
    )
    mover_anulada: Paso = (
        "UPDATE memberships.memberships SET original_end_date = '2027-01-10' WHERE id = $1",
        [ident],
    )
    borrar_original: Paso = (
        "UPDATE memberships.memberships SET original_end_date = NULL WHERE id = $1",
        [ident],
    )
    salidas = resultados(
        base,
        [
            [alta_plan, alta, mover_viva],
            [alta_plan, alta, anular, mover_anulada],
            [alta_plan, alta, anular, borrar_original],
        ],
    )
    assert salidas == [
        ("", None),
        (INTEGRITY, "memberships_identity"),
        (INTEGRITY, "memberships_identity"),
    ]


def test_downgrade_a_0029_quita_el_check_y_restaura_el_guard(
    alembic_config: Config, base: str
) -> None:
    socio = uuid4()
    plan, alta_plan = _plan()
    ident, alta = _membresia(plan, socio, date(2026, 12, 15))
    anular: Paso = (
        "UPDATE memberships.memberships SET status = 'cancelled', cancel_reason = 'Motivo largo', "
        "cancelled_by = $2, cancelled_at = now() WHERE id = $1",
        [ident, SYSTEM_USER_ID],
    )
    mover: Paso = (
        "UPDATE memberships.memberships SET original_end_date = '2027-01-10' WHERE id = $1",
        [ident],
    )
    try:
        command.downgrade(alembic_config, PADRE)
        assert not consultar(base, EXISTE_CHECK)
        assert resultados(base, [[alta_plan, alta, anular, mover]]) == [("", None)]
    finally:
        command.upgrade(alembic_config, "head")


def test_upgrade_aborta_con_el_conteo_si_hay_originales_malos(
    alembic_config: Config, base: str
) -> None:
    """Con una fila que viola L2, `0030` aborta nombrando el conteo y no crea el CHECK."""
    socio = uuid4()
    plan, alta_plan = _plan()
    _, mala = _membresia(plan, socio, date(2026, 11, 30))
    try:
        command.downgrade(alembic_config, PADRE)
        _ejecutar_pasos(base, [alta_plan, mala])
        with pytest.raises(RuntimeError, match=r"1 membres"):
            command.upgrade(alembic_config, REVISION)
        assert not consultar(base, EXISTE_CHECK)
    finally:
        _ejecutar(base, LIMPIAR_MEMBERSHIPS)
        _ejecutar_pasos(base, [("DELETE FROM plans.plans WHERE id = $1", [plan])])
        command.upgrade(alembic_config, "head")


def test_ciclo_head_base_head(alembic_config: Config, base: str) -> None:
    try:
        command.downgrade(alembic_config, "base")
    finally:
        command.upgrade(alembic_config, "head")
    assert consultar(base, EXISTE_CHECK)


def _ejecutar_pasos(url: str, pasos: list[Paso]) -> None:
    """Corre los pasos con commit (a diferencia de `resultados`, que revierte)."""

    async def correr() -> None:
        conexion = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://", 1))
        try:
            for sql, args in pasos:
                await conexion.execute(sql, *args)
        finally:
            await conexion.close()

    asyncio.run(correr())


FUNCION = "SELECT pg_get_functiondef('memberships.guard_identity()'::regprocedure) AS definicion"


def test_downgrade_restaura_la_funcion_exacta_de_0029(alembic_config: Config, base: str) -> None:
    """S7-C3b: la definición tras bajar es la que dejó `0029` (antes de `0030`), carácter a
    carácter; no solo «deja mover `original_end_date` en una anulada»."""
    try:
        command.downgrade(alembic_config, "0028_attendance")
        command.upgrade(alembic_config, PADRE)
        de_0029 = consultar(base, FUNCION)[0]["definicion"]
        command.upgrade(alembic_config, "head")
        de_0030 = consultar(base, FUNCION)[0]["definicion"]
        command.downgrade(alembic_config, PADRE)
        tras_bajar = consultar(base, FUNCION)[0]["definicion"]
    finally:
        command.upgrade(alembic_config, "head")
    assert de_0030 != de_0029
    assert tras_bajar == de_0029
