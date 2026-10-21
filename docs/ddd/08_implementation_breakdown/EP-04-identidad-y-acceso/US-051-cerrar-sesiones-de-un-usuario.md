# US-051 · Cerrar sesiones de un usuario — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-051-cerrar-sesiones-de-un-usuario.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth (`api/src/app/modules/auth/`, `web/src/features/system/`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

La historia ya define todo lo necesario:

- el endpoint con su conteo `{ revoked }`;
- que es idempotente cuando no hay sesiones;
- el caso de un admin que cierra sus propias sesiones;
- el campo nuevo `active_sessions` en la lista.

`active_sessions` es aditivo y la historia lo declara como agregado al contrato. Nada choca con DECISIONES.md.

## Resumen

`auth.service.revoke_sessions(user_id, by)` reutiliza `_revoke_all` (US-043) y devuelve cuántos refresh vigentes quedaron con `revoked_at`. También emite `SessionsRevoked(reason="admin", revoked=n)`, que audita US-107. El usuario no queda bloqueado. `list_users` (US-046) agrega `active_sessions` por usuario con una sola consulta agregada sobre `auth.refresh_tokens`. En el front, la acción "Cerrar sesiones" abre un `ConfirmModal` con el número de sesiones; si el admin la aplica sobre sí mismo, termina en `/login`.

## Correcciones aplicadas por DECISIONES.md

- El usuario técnico `SYSTEM_USER_ID` no es elegible y responde 404, igual que en US-046, US-049 y US-050. Nunca tiene sesiones, porque no puede iniciar sesión: coherente con DECISIONES N-15.
- La auditoría de `SessionsRevoked` la escribe US-107; aquí solo se emite el evento. Es el reparto de la épica y no una corrección de DECISIONES.md.

## Validación contra el dominio

- Entidades: `User` y `RefreshToken`. La invariante "revocar sesiones revoca todos los refresh tokens" se cumple con `_revoke_all` sin `except_id`.
- Evento que se emite: `SessionsRevoked(user_id, by, revoked=n, reason="admin")`. Se emite también con `n = 0`, porque la acción del admin queda auditada igual. No consume eventos.
- La historia no define funciones puras. El conteo de sesiones vigentes usa la misma condición que `is_refresh_usable` en SQL: `revoked_at IS NULL AND expires_at > now`.

## Validación contra la arquitectura

- El módulo dueño es `modules/auth` y la ruta usa `require_role("admin")`.
- `active_sessions` sale de una subconsulta agregada en el mismo esquema `auth` (`LEFT JOIN` de `count` agrupado por `user_id`), sin N+1 y sin cruzar esquemas.
- Un usuario dado de baja responde 404. Es coherente con US-049 y US-050, y en la práctica no tiene sesiones porque la baja las revoca.
- Sin datos sensibles. Los tokens nunca salen en la respuesta.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `revoke_sessions(session, user_id: UUID, *, by: UUID, clock) -> int` en `auth/service.py`: `_get_alive_or_404`, `n = _revoke_all(user_id)`, emite `SessionsRevoked(reason="admin", revoked=n)` y devuelve `n`. — 0.75 h
- [ ] T2 · Agregar `active_sessions: int` a `list_users` (US-046) mediante la subconsulta `SELECT user_id, count(*) FROM auth.refresh_tokens WHERE revoked_at IS NULL AND expires_at > :now GROUP BY user_id`, unida por `LEFT JOIN` con `coalesce(..., 0)`. — 1 h

### Schemas
- [ ] T3 · Agregar `RevokeSessionsOut` (`revoked: int`) y el campo `active_sessions: int` en `UserRow`. — 0.25 h

### Router
- [ ] T4 · `POST /api/v1/users/{id}/revoke-sessions` con `require_role("admin")`. Responde 200 con `RevokeSessionsOut`; los otros códigos son 401, 403 y 404. — 0.5 h

### Tests unitarios puros
- No aplica.

### Tests de service con PostgreSQL
- [ ] T5 · `api/tests/auth/test_revoke_sessions.py`:
  - Ana tiene 2 sesiones vigentes y 1 vencida; `revoke_sessions` devuelve 2 y emite `SessionsRevoked(revoked=2)`;
  - Ana sigue con `locked_at` nulo y puede volver a iniciar sesión;
  - una segunda llamada devuelve 0 y emite el evento con 0;
  - `list_users` reporta `active_sessions` correcto antes (2) y después (0);
  - `SYSTEM_USER_ID` responde 404. — 1.25 h

### Tests de router
- [ ] T6 · `api/tests/auth/test_revoke_sessions_router.py`:
  - 200 con `{ "revoked": 2 }`;
  - un id inexistente da 404;
  - el coach recibe 403;
  - cuando el admin cierra sus propias sesiones, su refresh actual también queda revocado y `refresh` responde 401. — 0.75 h

### Tests de arquitectura
- [ ] T7 · Mantener verde `test_every_route_has_role.py`. — 0.1 h

### Front
- [ ] T8 · Hook `useRevokeSessions()` en `web/src/features/system/api.ts` (invalida `["users"]`) y el campo `active_sessions` en el esquema Zod de la lista. — 0.25 h
- [ ] T9 · Acción "Cerrar sesiones" en `UsersPage` con un `ConfirmModal`: "Cerrar las {n} sesiones abiertas de {correo}. No lo bloquea; podrá ingresar de nuevo." Si el objetivo es el usuario conectado, al terminar se llama a `clearSession()` y se navega a `/login`. — 1.75 h
- [ ] T10 · Vitest `web/src/features/system/pages/UsersPage.sessions.test.tsx`: el modal muestra el número de sesiones, la confirmación llama al endpoint y, aplicada sobre uno mismo, se navega a `/login`. — 0.75 h

### DevOps
- No aplica.

### Seguridad
- [ ] T11 · Revisión: solo admin, sin tokens en la respuesta, auditoría del evento en US-107, y el conteo no expone el `user_agent` (la historia no lo pide). — 0.25 h

## Orden de ejecución
1. T5 (en rojo)
2. T1 y T2
3. T3
4. T6 (en rojo)
5. T4
6. T7
7. T10 (en rojo)
8. T8 y T9
9. T11

## Dependencias técnicas
- US-046 · Listar usuarios: `list_users` y `UserRow`, que esta historia amplía.
- US-043 · `_revoke_all` y el evento `SessionsRevoked`.
- US-049 · `_get_alive_or_404`.
- US-107 · Audita `SessionsRevoked`.
- US-065 · `ConfirmModal`.

## Endpoints
- `POST /api/v1/users/{id}/revoke-sessions` — roles: admin

## Riesgos
- Los access tokens ya emitidos siguen sirviendo hasta 15 minutos después de cerrar las sesiones, porque el usuario no queda bloqueado y `current_user` lo considera válido. Mitigación: es el comportamiento esperado de "cerrar sesiones" sin bloquear; para cortar el acceso de inmediato está "Bloquear" (US-050). Se aclara en el texto del modal y en el runbook.
- Front condicionado a D1.

## Estimación
- Backend: 2.5 h
- Front: 2.75 h
- Pruebas: 2.1 h
- DevOps / seguridad: 0.25 h
- **Total: 8 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/auth/test_revoke_sessions.py tests/auth/test_revoke_sessions_router.py tests/auth/test_list_users.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system/pages`
- [ ] `curl -X POST -H 'Authorization: Bearer <admin>' http://localhost/api/v1/users/<ana>/revoke-sessions` devuelve `{"revoked":2}`, y después `GET /api/v1/users?q=ana` muestra `active_sessions: 0`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.auth --cov-fail-under=80`
