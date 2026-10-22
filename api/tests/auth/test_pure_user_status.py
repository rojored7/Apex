"""Salidas puras de la lista y del alta de usuarios (S2-B3; US-045, US-047; S2-D1).

- `rules.user_row(user, active_sessions=n)`: la fila de `GET /users` con `status` calculado
  por `user_status` (precedencia `deleted > locked > inactive > pending_activation > active`);
  nunca trae `password_hash` ni tokens.
- `rules.user_out(user)`: `UserOut` con `status` y `must_change_password`.
- `core.search.escape_like(q)` (antes `rules.escape_like`; revisión Python H3): escapa la barra
  invertida, `%` y `_` (el `q` de la lista va con
  `ILIKE ... ESCAPE '\\'`).
La matriz SQL contra Python de `status_filter` vive en `test_auth_filter_matrix.py`.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.core.context import SYSTEM_USER_ID
from app.core.search import escape_like
from app.modules.auth.models import User
from app.modules.auth.rules import user_out, user_row
from app.modules.auth.schemas import UserOut, UserRow
from tests.auth._cuentas import CAMPOS_USER_OUT, CAMPOS_USER_ROW
from tests.conftest import T0


def _user(**cambios: object) -> User:
    valores: dict[str, object] = {
        "id": uuid4(),
        "email": "ana@test.apex",
        "password_hash": "$argon2id$x",
        "role": "coach",
        "member_id": None,
        "is_active": True,
        "must_change_password": False,
        "created_at": T0,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    return User(**valores)


ESTADOS = [
    ("active", {}),
    ("inactive", {"is_active": False}),
    ("locked", {"locked_at": T0}),
    ("pending_activation", {"password_hash": None}),
    ("deleted", {"deleted_at": T0}),
    ("deleted", {"deleted_at": T0, "locked_at": T0, "is_active": False}),
    ("locked", {"locked_at": T0, "is_active": False, "password_hash": None}),
    ("inactive", {"is_active": False, "password_hash": None}),
]


@pytest.mark.parametrize(("esperado", "cambios"), ESTADOS)
def test_user_row_calcula_el_estado_con_la_precedencia(
    esperado: str, cambios: dict[str, object]
) -> None:
    fila = user_row(_user(**cambios), active_sessions=0)
    assert isinstance(fila, UserRow)
    assert fila.status == esperado


def test_user_row_trae_exactamente_los_campos_del_contrato() -> None:
    usuario = _user(last_login_at=T0 - timedelta(hours=2), role="admin")
    fila = user_row(usuario, active_sessions=3)
    datos = fila.model_dump()
    assert set(datos) == CAMPOS_USER_ROW
    assert datos == {
        "id": usuario.id,
        "email": "ana@test.apex",
        "role": "admin",
        "status": "active",
        "member_id": None,
        "last_login_at": T0 - timedelta(hours=2),
        "created_at": T0,
        "active_sessions": 3,
    }
    assert "$argon2id" not in fila.model_dump_json()


def test_user_row_de_un_socio_lleva_su_ficha() -> None:
    ficha = uuid4()
    fila = user_row(_user(role="member", member_id=ficha), active_sessions=0)
    assert fila.role == "member" and fila.member_id == ficha


def test_user_out_lleva_estado_y_must_change_password() -> None:
    usuario = _user(password_hash=None, must_change_password=True)
    salida = user_out(usuario)
    assert isinstance(salida, UserOut)
    assert set(salida.model_dump()) == CAMPOS_USER_OUT
    assert salida.status == "pending_activation"
    assert salida.must_change_password is True
    assert salida.id == usuario.id and salida.email == usuario.email


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("ana", "ana"),
        ("50%", "50\\%"),
        ("a_b", "a\\_b"),
        ("c\\d", "c\\\\d"),
        ("%_\\", "\\%\\_\\\\"),
        ("", ""),
    ],
    ids=["sin-comodines", "porcentaje", "guion-bajo", "barra", "los-tres", "vacio"],
)
def test_escape_like_escapa_la_barra_el_porcentaje_y_el_guion_bajo(
    entrada: str, esperado: str
) -> None:
    assert escape_like(entrada) == esperado
