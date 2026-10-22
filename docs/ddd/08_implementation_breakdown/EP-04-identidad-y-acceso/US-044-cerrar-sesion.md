# US-044 · Cerrar sesión — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-044-cerrar-sesion.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth (`api/src/app/modules/auth/`, `web/src/shared/ui/TopBar.tsx`, `web/src/core/auth/`)
- **Versión:** v0.1
- **Puntos de la historia:** 1

## Estado de preparación

**READY**

Es un endpoint pequeño con contrato completo: 204, idempotente sin cookie, y revoca solo la sesión actual. No choca con DECISIONES.md, y se apoya en el canal entre pestañas que crea US-043.

## Resumen

`auth.service.logout(user, refresh_token)` revoca únicamente el refresh de la cookie, si pertenece al usuario autenticado. El router borra la cookie y responde 204 siempre que haya un access token válido. En el front, el ítem "Cerrar sesión" del menú de usuario del `TopBar` llama al endpoint, limpia la sesión en memoria y avisa a las demás pestañas por `BroadcastChannel`, aunque la petición falle por red. Después navega a `/login`.

## Correcciones aplicadas por DECISIONES.md

Ninguna; la historia ya es coherente con DECISIONES.md.

## Validación contra el dominio

- Las entidades son `User` y `RefreshToken`. Se revoca un solo token, y el resto de las sesiones sigue vigente (criterio 2). Coincide con "revocar sesiones revoca todos los refresh" porque aquí no se revocan sesiones en bloque.
- No emite eventos de dominio y no consume eventos. Un logout no se audita como `SessionsRevoked`: la historia no lo pide y `refresh_tokens` no es tabla auditada.
- No tiene funciones puras.

## Validación contra la arquitectura

- El módulo dueño es `modules/auth`. La ruta declara `require_role("admin", "coach", "member")` y no está en la lista blanca.
- IDOR: el service filtra `user_id = current_user.id` al buscar el token, así que un refresh ajeno no se revoca y la respuesta sigue siendo 204.
- Primitivas: el hash de la cookie se calcula con `core.security.hash_opaque_token`.
- Sin paginación ni auditoría.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `logout(session, user_id: UUID, refresh_token: str | None, *, clock) -> None` en `auth/service.py`: sin token, no hace nada; con token, aplica `UPDATE refresh_tokens SET revoked_at = now WHERE token_hash = :h AND user_id = :u AND revoked_at IS NULL`. — 0.5 h

### Schemas
- No aplica.

### Router
- [ ] T2 · `POST /api/v1/auth/logout` con `require_role("admin", "coach", "member")`. Lee la cookie `apex_refresh`, llama a `logout` y a `clear_refresh_cookie`, y responde 204. Sin access token responde 401 `unauthorized` (lo resuelve US-034). — 0.5 h

### Tests unitarios puros
- No aplica.

### Tests de service con PostgreSQL
- [ ] T3 · `api/tests/auth/test_logout_service.py`:
  - con dos sesiones del mismo usuario, el logout revoca solo la actual;
  - después, `refresh` con ese token lanza `InvalidRefresh` (no es reuso porque no tiene `replaced_by_id`);
  - un token de otro usuario no se revoca. — 0.75 h

### Tests de router
- [ ] T4 · `api/tests/auth/test_logout_router.py`: 204 con `Set-Cookie` que vence la cookie; sin cookie, 204 igual; sin access token, 401. — 0.5 h

### Tests de arquitectura
- [ ] T5 · Que `test_every_route_has_role.py` siga verde: `/auth/logout` declara rol. — 0.1 h

### Front
- [ ] T6 · En `web/src/core/auth/session.ts`, función `logout()`: llama a `POST /auth/logout` con `credentials: "same-origin"` y, en `finally`, ejecuta `clearSession()`, publica `logout` en `BroadcastChannel("apex-auth")` y navega a `/login`. Ítem "Cerrar sesión" en el menú de usuario de `web/src/shared/ui/TopBar.tsx`, deshabilitado durante la petición. — 1 h (corregido en Sprint 2, ver DECISIONES S2-D44)
- [ ] T7 · Vitest `web/src/shared/ui/TopBar.logout.test.tsx`: después del 204 y después de un error de red, la sesión queda limpia, se publica el mensaje y se navega a `/login`. — 0.5 h

### DevOps
- No aplica.

### Seguridad
- [ ] T8 · Revisión: no se puede revocar un token ajeno (IDOR), la cookie se borra con el mismo `Path` y en el cliente no queda el access token. — 0.15 h

## Orden de ejecución
1. T3 (en rojo)
2. T1
3. T4 (en rojo)
4. T2
5. T5
6. T7 (en rojo)
7. T6
8. T8

## Dependencias técnicas
- US-042 · Iniciar sesión: la cookie, `clear_refresh_cookie` y `session.ts`.
- US-043 · Renovar sesión: el canal `apex-auth` y el comportamiento de `InvalidRefresh`.
- US-034 · current_user y require_role.
- US-061 · TopBar con menú de usuario.

## Endpoints
- `POST /api/v1/auth/logout` — roles: admin, coach, member

## Riesgos
- Si el access token venció justo antes del logout, el 401 `token_expired` dispara un refresh y un reintento, que agregan una rotación inútil. Mitigación: aceptable. El front limpia la sesión igual en `finally`.
- Front condicionado a D1.

## Estimación
- Backend: 1 h
- Front: 1.5 h
- Pruebas: 1.35 h
- DevOps / seguridad: 0.15 h
- **Total: 4 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/auth/test_logout_service.py tests/auth/test_logout_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/shared/ui/TopBar.logout.test.tsx`
- [ ] Después de `curl -X POST -H 'Authorization: Bearer <a>' -b 'apex_refresh=<r>' http://localhost/api/v1/auth/logout` (204), `curl -b 'apex_refresh=<r>' -X POST http://localhost/api/v1/auth/refresh` responde 401 `invalid_refresh`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.auth --cov-fail-under=80`
