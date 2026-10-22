"""Fachada del service de auth (revisión Python H1: el antiguo `service.py` de 1257 líneas se
partió en archivos privados del módulo).

Otros módulos (`audit`, el CLI) y las rutas solo importan este archivo (regla de módulos 2):
reexporta lo público de
- `events.py`: `UserCreated`, `LoginAttempted`, `SessionsRevoked`, `UserLocked`,
  `PasswordChanged` (los escucha `audit.service`);
- `sessions.py`: `login`, `refresh`, `logout`, `load_active_principal`, `configure_sleeper`,
  `LoginResult`, `RefreshResult` y los buckets del límite por cuenta;
- `users.py`: seed, lecturas para otros módulos, "Mi cuenta" y el ciclo de vida del usuario;
- `links.py`: `reset`, `forgot`, `issue_link` y `resend_link`;
- `rules.py`: `normalize_login_email`, `is_active_admin` y `user_status`.

Al importarse registra `load_active_principal` como el `PrincipalLoader` de `core.security`
(US-034): es el único punto de registro y `main.load_module_services` lo importa al arrancar.
"""

from __future__ import annotations

from app.core.security import register_principal_loader
from app.modules.auth.events import (
    LoginAttempted,
    PasswordChanged,
    SessionsRevoked,
    UserCreated,
    UserLocked,
)
from app.modules.auth.links import (
    FORGOT_ACCOUNT_BUCKET,
    FORGOT_ACCOUNT_LIMIT,
    FORGOT_ACCOUNT_WINDOW_S,
    forgot,
    issue_link,
    resend_link,
    reset,
)
from app.modules.auth.rules import is_active_admin, normalize_login_email, user_status
from app.modules.auth.sessions import (
    ACCOUNT_BUCKET,
    ACCOUNT_GLOBAL_BUCKET,
    LoginResult,
    RefreshResult,
    configure_sleeper,
    load_active_principal,
    login,
    logout,
    refresh,
)
from app.modules.auth.users import (
    CHANGE_PASSWORD_USER_LIMIT,
    SeedResult,
    active_admin_id_by_email,
    active_user_id_by_email,
    change_password,
    create_user,
    delete_user,
    get_user,
    ids_by_email,
    list_users,
    lock,
    me,
    names_for,
    revoke_sessions,
    seed_admin,
    unlock,
    update_user,
    validate_password_policy,
    validate_user_role,
)

register_principal_loader(load_active_principal)

__all__ = [
    "ACCOUNT_BUCKET",
    "ACCOUNT_GLOBAL_BUCKET",
    "CHANGE_PASSWORD_USER_LIMIT",
    "FORGOT_ACCOUNT_BUCKET",
    "FORGOT_ACCOUNT_LIMIT",
    "FORGOT_ACCOUNT_WINDOW_S",
    "LoginAttempted",
    "LoginResult",
    "PasswordChanged",
    "RefreshResult",
    "SeedResult",
    "SessionsRevoked",
    "UserCreated",
    "UserLocked",
    "active_admin_id_by_email",
    "active_user_id_by_email",
    "change_password",
    "configure_sleeper",
    "create_user",
    "delete_user",
    "forgot",
    "get_user",
    "ids_by_email",
    "is_active_admin",
    "issue_link",
    "list_users",
    "load_active_principal",
    "lock",
    "login",
    "logout",
    "me",
    "names_for",
    "normalize_login_email",
    "refresh",
    "resend_link",
    "reset",
    "revoke_sessions",
    "seed_admin",
    "unlock",
    "update_user",
    "user_status",
    "validate_password_policy",
    "validate_user_role",
]
