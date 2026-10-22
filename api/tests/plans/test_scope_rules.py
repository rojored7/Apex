"""Reglas de alcance de los planes por rol (S2-B9; US-079; S2-D26). Puras, sin base.

- `ensure_list_scope(role, active)`: el admin lista con `active` en `None`, `True` o `False`; el
  coach solo con `active=True` (sin parámetro o con `False` da `PlanScopeForbidden`, 403
  `forbidden`). `member` nunca lista (la ruta ya lo frena con `require_role`; la regla pura
  también cierra).
- `ensure_read_scope(role, plan)`: el admin lee activos e inactivos; el coach solo activos; un
  plan inactivo da `PlanScopeForbidden` al coach. `member` nunca lee.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.errors import DomainError
from app.core.security import Role
from app.modules.plans.exceptions import PlanError, PlanScopeForbidden
from app.modules.plans.schemas import PlanSnapshot
from app.modules.plans.service import ensure_list_scope, ensure_read_scope


def _plan(*, activo: bool) -> PlanSnapshot:
    return PlanSnapshot(
        id=uuid4(),
        name="Mensual",
        price_cop=120_000,
        kind="days",
        duration_days=30,
        class_count=None,
        is_active=activo,
        deleted_at=None,
    )


def test_plan_scope_forbidden_es_un_403_forbidden_de_dominio() -> None:
    error = PlanScopeForbidden()
    assert isinstance(error, PlanError) and isinstance(error, DomainError)
    assert error.status == 403 and error.code == "forbidden"
    assert error.field is None and error.existing_id is None


# Lista ------------------------------------------------------------------------------------


@pytest.mark.parametrize("active", [None, True, False], ids=["sin", "activos", "inactivos"])
def test_el_admin_lista_con_cualquier_filtro(active: bool | None) -> None:
    ensure_list_scope("admin", active)


def test_el_coach_lista_solo_los_activos() -> None:
    ensure_list_scope("coach", True)


@pytest.mark.parametrize("active", [None, False], ids=["sin-parametro", "inactivos"])
def test_el_coach_sin_active_true_recibe_plan_scope_forbidden(active: bool | None) -> None:
    with pytest.raises(PlanScopeForbidden) as error:
        ensure_list_scope("coach", active)
    assert error.value.status == 403 and error.value.code == "forbidden"


@pytest.mark.parametrize("active", [None, True, False], ids=["sin", "activos", "inactivos"])
def test_member_nunca_lista(active: bool | None) -> None:
    with pytest.raises(PlanScopeForbidden):
        ensure_list_scope("member", active)


# Lectura de uno ---------------------------------------------------------------------------


@pytest.mark.parametrize("activo", [True, False], ids=["activo", "inactivo"])
def test_el_admin_lee_activos_e_inactivos(activo: bool) -> None:
    ensure_read_scope("admin", _plan(activo=activo))


def test_el_coach_lee_un_plan_activo() -> None:
    ensure_read_scope("coach", _plan(activo=True))


def test_el_coach_sobre_un_plan_inactivo_recibe_plan_scope_forbidden() -> None:
    with pytest.raises(PlanScopeForbidden) as error:
        ensure_read_scope("coach", _plan(activo=False))
    assert error.value.status == 403


@pytest.mark.parametrize("activo", [True, False], ids=["activo", "inactivo"])
def test_member_nunca_lee(activo: bool) -> None:
    rol: Role = "member"
    with pytest.raises(PlanScopeForbidden):
        ensure_read_scope(rol, _plan(activo=activo))
