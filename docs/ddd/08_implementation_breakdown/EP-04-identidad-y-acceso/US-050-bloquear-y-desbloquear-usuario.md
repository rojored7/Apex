# US-050 · Bloquear y desbloquear usuario — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-050-bloquear-y-desbloquear-usuario.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth (`api/src/app/modules/auth/`, `web/src/features/system/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Están definidos los dos endpoints, los cuatro códigos 409 (`last_admin`, `cannot_lock_self`, `already_locked` y `not_locked`), la revocación en la misma transacción y los dos eventos. Que el bloqueo surta efecto de inmediato depende de que `current_user` (US-034) consulte el estado en cada petición; eso ya está en los criterios de US-034. La auditoría de `UserLocked` y `SessionsRevoked` es de US-107: aquí solo se emiten los eventos.

## Resumen

`auth.service.lock(user_id, by)`:

- valida que el usuario exista y no esté borrado;
- valida que no sea el propio admin, que no esté ya bloqueado y que no sea el último admin activo;
- pone `locked_at`;
- revoca todos sus refresh tokens con `_revoke_all`;
- emite `UserLocked` y `SessionsRevoked(reason="lock")`, todo en una transacción.

`unlock` limpia `locked_at` sin restaurar sesiones. El front agrega las acciones "Bloquear" (con `ConfirmModal`) y "Desbloquear", y muestra el `StatusTag` "Bloqueado".

## Correcciones aplicadas por DECISIONES.md

- "Último admin activo" no cuenta al usuario técnico (`is_active = false`): corregido por DECISIONES N-15. El usuario técnico tampoco se puede bloquear ni desbloquear (404), igual que en US-049.
- La auditoría de `UserLocked` y `SessionsRevoked` (`update` sobre `users` con `after.event`) la escribe el handler de US-107. Esta historia no llama a `core.audit`. No es corrección de DECISIONES.md: es el reparto de la épica (US-107, EP-11).

## Validación contra el dominio

- Entidades: `User` y `RefreshToken`. Se cumplen las invariantes "bloquear impide login y revoca sesiones" y "no se puede bloquear al último admin activo".
- Funciones puras:
  - `would_remove_last_admin(..., deleting=True)` de US-049: bloquear equivale a quitar al admin del conjunto activo;
  - `lock_precondition(user, by_id, is_last_admin) -> None | AuthError`, que fija el orden de los errores: `cannot_lock_self`, luego `already_locked` y luego `last_admin`.
- Eventos que se emiten: `UserLocked(user_id, by)` y `SessionsRevoked(user_id, by, revoked=n, reason="lock")`. No consume eventos.
- Desbloquear no emite eventos de dominio. El cambio de `locked_at` lo registra el hook como `update`.

## Validación contra la arquitectura

- El módulo dueño es `modules/auth` y las rutas usan `require_role("admin")`.
- Efecto inmediato: `current_user` (US-034) carga el principal con `auth.service.get_principal` (US-041) y rechaza con 401 si hay `locked_at`. La dependencia de `core` hacia `auth` se resuelve registrando un loader, como se propone en US-041, y se reporta al orquestador.
- Concurrencia: igual que en US-049, `_lock_active_admins` con `FOR UPDATE`.
- Login y refresh de un usuario bloqueado: ya responden 401 genérico y 401 `invalid_refresh` (US-042 y US-043, por `can_login`). Los tokens de un solo uso de un bloqueado se rechazan (US-048).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `lock_precondition(user: User, by_id: UUID, *, is_last_admin: bool) -> None` en `auth/service.py`. Lanza `CannotLockSelf`, `AlreadyLocked` o `LastAdmin`, en ese orden. — 0.25 h
- [ ] T2 · `lock(session, user_id: UUID, *, by: UUID, clock) -> User`:
  1. `_get_alive_or_404`;
  2. `_lock_active_admins`;
  3. `lock_precondition`;
  4. `locked_at = now`;
  5. `n = _revoke_all(user_id)`;
  6. emitir `UserLocked` y `SessionsRevoked(reason="lock", revoked=n)`. — 1.25 h
- [ ] T3 · `unlock(session, user_id, *, by) -> User`: 404 si no existe o está borrado; `NotLocked` (409 `not_locked`) si no está bloqueado; `locked_at = None`. — 0.5 h
- [ ] T4 · Declarar el evento `UserLocked` y las excepciones `CannotLockSelf`, `AlreadyLocked` y `NotLocked` en `auth/exceptions.py`, con sus códigos de envelope. — 0.25 h

### Schemas
- No aplica (responde `UserOut` de US-046 y US-049).

### Router
- [ ] T5 · `POST /api/v1/users/{id}/lock` y `POST /api/v1/users/{id}/unlock`, los dos con `require_role("admin")`. Responden 200 con `UserOut`; los demás códigos son 401, 403, 404 y 409. — 0.75 h

### Tests unitarios puros
- [ ] T6 · `api/tests/auth/test_pure_lock.py`: `lock_precondition` con el propio usuario, un usuario ya bloqueado, el último admin y un caso válido; el orden de prioridad cuando aplican varios errores. — 0.25 h

### Tests de service con PostgreSQL
- [ ] T7 · `api/tests/auth/test_lock_unlock.py`:
  - bloquear pone `locked_at`, revoca las dos sesiones de Luis y emite `UserLocked` y `SessionsRevoked(revoked=2)` en la misma transacción. Si un handler falla (doble que lanza), no queda nada aplicado;
  - después del bloqueo, `login` lanza `InvalidCredentials` y `refresh` lanza `InvalidRefresh`;
  - desbloquear deja `locked_at` nulo, las sesiones siguen revocadas y el login vuelve a funcionar;
  - bloquear al único admin humano responde `LastAdmin`;
  - desbloquear a alguien no bloqueado responde `NotLocked`;
  - `SYSTEM_USER_ID` responde 404. — 1.5 h

### Tests de router
- [ ] T8 · `api/tests/auth/test_lock_router.py`:
  - el coach recibe 403;
  - un usuario inexistente o borrado da 404;
  - los cuatro 409 con su `code`;
  - el bloqueo es inmediato: con un access token de Luis emitido antes del bloqueo, `GET /auth/me` responde 401 en la siguiente petición. — 1.25 h

### Tests de arquitectura
- [ ] T9 · Mantener verde `test_every_route_has_role.py`. — 0.1 h

### Front
- [ ] T10 · Hooks `useLockUser()` y `useUnlockUser()` en `web/src/features/system/api.ts`, que invalidan `["users"]`. — 0.5 h
- [ ] T11 · En `web/src/features/system/pages/UsersPage.tsx`, acciones por fila:
  - "Bloquear", con un `ConfirmModal` que dice "Cierra todas sus sesiones y le impide entrar hasta que lo desbloquees";
  - "Desbloquear", solo en filas con estado `locked`;
  - el `StatusTag` "Bloqueado" usa el token de error y lleva texto;
  - los 409 muestran el mensaje del envelope. — 1.5 h
- [ ] T12 · Vitest `web/src/features/system/pages/UsersPage.lock.test.tsx`: confirmar llama a `lock` y refresca la fila; "Desbloquear" solo aparece en bloqueados; un 409 `cannot_lock_self` muestra su mensaje. — 1 h

### DevOps
- No aplica.

### Seguridad
- [ ] T13 · Revisión:
  - efecto inmediato sobre los access tokens vigentes;
  - revocación y bloqueo en una sola transacción;
  - nadie puede bloquearse a sí mismo;
  - el último admin está protegido con `FOR UPDATE`;
  - los eventos llegan a la auditoría (US-107). — 0.4 h

## Orden de ejecución
1. T6 (en rojo)
2. T1
3. T7 (en rojo)
4. T4
5. T2
6. T3
7. T8 (en rojo)
8. T5
9. T9
10. T12 (en rojo)
11. T10 y T11
12. T13

## Dependencias técnicas
- US-046 · Listar usuarios: la pantalla y `UserOut`.
- US-049 · `would_remove_last_admin`, `_lock_active_admins` y `_get_alive_or_404`.
- US-043 · `_revoke_all` y `SessionsRevoked`.
- US-034 · `current_user` comprueba `locked_at` en cada petición. Requiere el loader registrado de US-041 para no invertir la dependencia de `core` hacia `modules`.
- US-107 · Audita `UserLocked` y `SessionsRevoked`.
- US-065 · `ConfirmModal`.

## Endpoints
- `POST /api/v1/users/{id}/lock` — roles: admin
- `POST /api/v1/users/{id}/unlock` — roles: admin

## Riesgos
- Si US-034 cachea el principal o confía solo en el JWT, el bloqueo tardaría hasta 15 minutos en surtir efecto. Mitigación: T8 lo verifica de punta a punta y bloquea el cierre.
- `core/security` y `auth.service` quedarían con una dependencia en sentido prohibido si US-034 se implementa con un import directo. Mitigación: la propuesta de registrar el loader (US-041), reportada al orquestador.
- Front condicionado a D1.

## Estimación
- Backend: 3 h
- Front: 3 h
- Pruebas: 3.1 h
- DevOps / seguridad: 0.4 h
- **Total: 10 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/auth/test_pure_lock.py tests/auth/test_lock_unlock.py tests/auth/test_lock_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system/pages`
- [ ] Después de `curl -X POST -H 'Authorization: Bearer <admin>' http://localhost/api/v1/users/<luis>/lock`, `curl -H 'Authorization: Bearer <token previo de luis>' http://localhost/api/v1/auth/me` responde 401.
- [ ] `SELECT after->>'event' FROM audit.audit_log WHERE record_id = '<luis>' ORDER BY seq DESC LIMIT 2` devuelve `SessionsRevoked` y `UserLocked`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.auth --cov-fail-under=80`
