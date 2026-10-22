"""Fábricas de datos de prueba por tabla (plan del Sprint 2, sección 2).

`FACTORIES` mapea `esquema.tabla` a su fábrica. Cada fábrica termina con
`await session.commit()`: con la `session` de savepoint libera el savepoint, así los datos
quedan fuera de lo que una petición fallida revierte. Socios (B7) y planes (B9) se agregan
en su slice.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from tests.factories.users import make_one_time_token, make_user

FACTORIES: dict[str, Callable[..., Awaitable[Any]]] = {
    "auth.users": make_user,
    "auth.one_time_tokens": make_one_time_token,
}
