"""`auth.rules.would_remove_last_admin` (S2-B5; US-049, US-050; blueprint S2-B5).

Pura: recibe el conjunto de admins activos que devuelve `tokens.lock_active_admins` (rol admin,
activos, sin bloqueo ni baja, con hash, sin el técnico) y dice si dar de baja al objetivo, o
cambiarle el rol a uno que no es `admin`, deja ese conjunto vacío. Un objetivo fuera del
conjunto (coach, admin pendiente, bloqueado o el técnico) nunca es el último admin.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.core.context import SYSTEM_USER_ID
from app.modules.auth.rules import would_remove_last_admin

UNO = UUID("00000000-0000-0000-0000-0000000000a1")
DOS = UUID("00000000-0000-0000-0000-0000000000a2")


@pytest.mark.parametrize(
    ("new_role", "deleting"),
    [(None, True), ("coach", False), ("member", False), ("coach", True)],
)
def test_un_solo_admin_dado_de_baja_o_degradado_es_el_ultimo(
    new_role: str | None, deleting: bool
) -> None:
    assert (
        would_remove_last_admin(
            frozenset({UNO}),
            UNO,
            new_role=new_role,  # type: ignore[arg-type]
            deleting=deleting,
        )
        is True
    )


@pytest.mark.parametrize(
    ("new_role", "deleting"),
    [(None, True), ("coach", False), ("member", False)],
)
def test_con_dos_admins_ninguno_es_el_ultimo(new_role: str | None, deleting: bool) -> None:
    for objetivo in (UNO, DOS):
        assert (
            would_remove_last_admin(
                frozenset({UNO, DOS}),
                objetivo,
                new_role=new_role,  # type: ignore[arg-type]
                deleting=deleting,
            )
            is False
        )


@pytest.mark.parametrize("objetivo", [DOS, SYSTEM_USER_ID, uuid4()])
def test_un_objetivo_que_no_es_admin_activo_nunca_es_el_ultimo(objetivo: UUID) -> None:
    assert (
        would_remove_last_admin(frozenset({UNO}), objetivo, new_role=None, deleting=True) is False
    )
    assert (
        would_remove_last_admin(frozenset({UNO}), objetivo, new_role="coach", deleting=False)
        is False
    )


def test_sin_admins_activos_no_hay_ultimo_que_quitar() -> None:
    assert would_remove_last_admin(frozenset(), UNO, new_role=None, deleting=True) is False


def test_cambiar_a_admin_no_quita_al_ultimo() -> None:
    assert would_remove_last_admin(frozenset({UNO}), UNO, new_role="admin", deleting=False) is False


def test_sin_baja_ni_cambio_de_rol_no_quita_a_nadie() -> None:
    assert would_remove_last_admin(frozenset({UNO}), UNO, new_role=None, deleting=False) is False
