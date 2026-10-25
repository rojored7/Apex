"""Fábricas de datos de prueba por tabla (plan del Sprint 2, sección 2).

`FACTORIES` mapea `esquema.tabla` a su fábrica. Cada fábrica termina con
`await session.commit()`: con la `session` de savepoint libera el savepoint, así los datos
quedan fuera de lo que una petición fallida revierte. B7 agrega `members.members` (necesita el
bus listo) y B9 `plans.plans` (sin columnas cifradas); S3-B1 `memberships.memberships` (pide
el socio y el plan); S3-B2 `memberships.membership_freezes` (pide la membresía).
`test_no_plaintext_at_rest.py` exige una fábrica por cada tabla con columnas cifradas.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from tests.factories.members import make_member
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.plans import make_plan
from tests.factories.users import make_one_time_token, make_user

FACTORIES: dict[str, Callable[..., Awaitable[Any]]] = {
    "auth.users": make_user,
    "auth.one_time_tokens": make_one_time_token,
    "members.members": make_member,
    "memberships.memberships": make_membership,
    "memberships.membership_freezes": make_freeze,
    "plans.plans": make_plan,
}
