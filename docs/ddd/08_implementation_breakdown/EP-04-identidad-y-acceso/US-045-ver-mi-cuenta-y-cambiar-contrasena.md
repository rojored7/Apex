# US-045 · Ver mi cuenta y cambiar contraseña — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-045-ver-mi-cuenta-y-cambiar-contrasena.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth (`api/src/app/modules/auth/`, `web/src/features/auth/`, `web/src/shared/ui/TopBar.tsx`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Los dos endpoints, sus códigos y la revocación de las demás sesiones están definidos. DECISIONES N-10 (política de contraseña) y N-13 (cambiar la contraseña revoca las demás sesiones) confirman los supuestos de la historia. El enmascarado de `password_hash` en auditoría depende de `__audit_redact__`, que ya se exige en US-041.

## Resumen

`GET /auth/me` devuelve el principal autenticado (`id`, `email`, `role`, `member_id`). `POST /auth/me/password` verifica la contraseña actual, valida la nueva con `validate_password_policy` (12 caracteres o más, que no esté en la lista común y que sea distinta de la actual), guarda el hash argon2id y revoca todos los refresh del usuario salvo el de la cookie de la sesión actual. También emite `PasswordChanged`. El front muestra el correo y el rol en el `TopBar` y abre el `SidePanel` "Cambiar contraseña", validado con Zod. `change_password` queda como el contrato que reutiliza el portal (US-192).

## Correcciones aplicadas por DECISIONES.md

- La política es de 12 caracteres o más y distinta de la actual. Además se rechaza si está en la lista corta de contraseñas comunes: corregido por DECISIONES N-10.
- Cambiar la contraseña revoca las demás sesiones y conserva la actual: aceptado por DECISIONES N-13.

## Validación contra el dominio

- Las entidades son `User` y `RefreshToken`.
- Evento emitido: `PasswordChanged(user_id, by, via: Literal["change","activate","reset"])`, aquí con `via = "change"` y `by` igual al propio usuario.
- No consume eventos.
- Función pura: `validate_password_policy(password, current_hash=...)`, que se crea en US-041 y aquí agrega su prueba del caso "igual a la actual".
- No hay discrepancias con `02_domain_model.md` 2.11.

## Validación contra la arquitectura

- El módulo dueño es `modules/auth`. Las dos rutas usan `require_role("admin", "coach", "member")`.
- El principal sale de `current_user` (US-034), y el router no carga models.
- Sesión actual: la cookie `apex_refresh` llega porque su `Path=/api/v1/auth` cubre `/auth/me/password`. El service calcula el hash con `core.security.hash_opaque_token` y excluye ese id de `_revoke_all`. Sin cookie se revoca todo.
- Primitivas: `core.security.verify_password` y `hash_password`.
- Auditoría: el hook registra un `update` sobre `users` con `password_hash` como `"***"` en `before` y `after`. `PasswordChanged` no requiere auditoría adicional.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `me(principal: Principal) -> MeOut` en `auth/service.py`. Arma la respuesta sin volver a consultar la base, porque `current_user` ya cargó al usuario. — 0.25 h
- [ ] T2 · `change_password(session, user_id: UUID, current_password: str, new_password: str, *, current_refresh: str | None, clock) -> None`:
  - si `verify_password` falla con la actual, lanza `FieldError("current_password")`;
  - `validate_password_policy(new, current_hash=...)` lanza `FieldError("new_password")`;
  - si pasa, aplica `hash_password`, llama a `_revoke_all(user_id, except_id=<id de la sesión actual>)` y emite `PasswordChanged(via="change")`. — 1.5 h

### Schemas
- [ ] T3 · `MeOut` (`id`, `email`, `role`, `member_id`) y `ChangePasswordIn` (`current_password: SecretStr` y `new_password: SecretStr` con `max_length` 1024). — 0.5 h

### Router
- [ ] T4 · `GET /api/v1/auth/me` (200 o 401) y `POST /api/v1/auth/me/password` (204, 401 o 422 con `field`), los dos con `require_role("admin", "coach", "member")`. — 0.75 h

### Tests unitarios puros
- [ ] T5 · `api/tests/auth/test_pure_password_policy.py`: una contraseña nueva igual a la actual se rechaza; el resto de los casos ya están en US-041. — 0.25 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/auth/test_change_password.py`:
  - con dos sesiones, después del cambio la de la cookie sigue vigente y la otra queda con `revoked_at`;
  - se emite `PasswordChanged`;
  - la auditoría `update` sobre `users` tiene `"***"` en `before` y `after`;
  - con la actual errada, el hash no cambia;
  - con una nueva de 11 caracteres, nada cambia. — 1.25 h

### Tests de router
- [ ] T7 · `api/tests/auth/test_me_router.py`: `/auth/me` sin token responde 401, y con token no trae `password_hash`; `/auth/me/password` responde 422 con `field` `current_password` o `new_password`, y 204. — 0.75 h

### Tests de arquitectura
- [ ] T8 · Que `test_every_route_has_role.py` y `test_banned_imports.py` sigan verdes. — 0.1 h

### Front
- [ ] T9 · Hooks `useMe()` (`useQuery` sobre `GET /auth/me`) y `useChangePassword()` (`useMutation`) en `web/src/features/auth/api.ts`, y esquema Zod `changePasswordSchema` (mínimo 12 y `refine` de confirmación) en `web/src/features/auth/schemas.ts`. — 0.75 h
- [ ] T10 · `web/src/features/auth/components/ChangePasswordPanel.tsx`, un `SidePanel` con tres `Field`. Estados: guardando, error por `field` y éxito, que cierra el panel y muestra "Contraseña actualizada". El `TopBar` muestra el correo y el rol (etiqueta en español) e incluye la opción "Cambiar contraseña". — 2 h
- [ ] T11 · Vitest `web/src/features/auth/components/ChangePasswordPanel.test.tsx`: una confirmación distinta bloquea el envío; un 422 con `field: "current_password"` se muestra bajo ese campo; el éxito cierra el panel. — 1 h

### DevOps
- No aplica.

### Seguridad
- [ ] T12 · Revisión: sin contraseñas en logs, revocación de las otras sesiones, sin `password_hash` en la respuesta de `/auth/me`, y la contraseña actual siempre se exige. — 0.25 h

## Orden de ejecución
1. T5 y T6 (en rojo)
2. T1 y T2
3. T3
4. T7 (en rojo)
5. T4
6. T8
7. T11 (en rojo)
8. T9 y T10
9. T12

## Dependencias técnicas
- US-042 · Iniciar sesión: la sesión y la cookie.
- US-043 · Renovar sesión: `_revoke_all`.
- US-041 · `validate_password_policy` y `__audit_redact__` (US-016).
- US-034 · current_user (`Principal`).
- US-061 · TopBar y US-065 · SidePanel.
- US-192 (v1.0) reutiliza `auth.service.change_password`. El contrato queda fijado aquí.

## Endpoints
- `GET /api/v1/auth/me` — roles: admin, coach, member
- `POST /api/v1/auth/me/password` — roles: admin, coach, member

## Riesgos
- Si `__audit_redact__` no existe en US-016, el hash entraría en la cadena inmutable. Mitigación: T6 lo verifica y bloquea el cierre.
- La lista de contraseñas comunes es corta y no reemplaza a un servicio tipo HIBP. Es aceptable para v0.1 (N-10).
- Front condicionado a D1.

## Estimación
- Backend: 3 h
- Front: 3.75 h
- Pruebas: 2.35 h
- DevOps / seguridad: 0.25 h
- **Total: 9 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/auth/test_pure_password_policy.py tests/auth/test_change_password.py tests/auth/test_me_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/auth/components`
- [ ] Después del cambio, `SELECT count(*) FROM auth.refresh_tokens WHERE user_id = '<u>' AND revoked_at IS NULL` devuelve 1 (la sesión actual), y `SELECT before->>'password_hash', after->>'password_hash' FROM audit.audit_log WHERE table_name = 'users' ORDER BY seq DESC LIMIT 1` devuelve `*** | ***`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.auth --cov-fail-under=80`
