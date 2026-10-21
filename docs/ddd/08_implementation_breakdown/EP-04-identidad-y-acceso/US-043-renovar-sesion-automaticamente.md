# US-043 · Renovar sesión automáticamente — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-043-renovar-sesion-automaticamente.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth (`api/src/app/modules/auth/`) y `web/src/core/api/`, `web/src/core/auth/`
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

La rotación del refresh, los 401 por causa y la coordinación entre pestañas están definidos. DECISIONES N-13 corrige el único supuesto abierto: si alguien reusa un refresh ya rotado, se revocan todas las sesiones del usuario. La columna `replaced_by_id`, que hace falta para detectarlo, ya está en `0004_auth` (US-041).

## Resumen

`auth.service.refresh` toma la cookie, busca el token por su hash con `SELECT ... FOR UPDATE`, valida que se pueda usar, lo revoca y crea uno nuevo enlazado con `replaced_by_id`. Devuelve un access token nuevo. Si el token presentado ya había sido reemplazado (reuso), revoca todos los refresh del usuario, emite `SessionsRevoked(reason="refresh_reuse")` y responde 401 `invalid_refresh`. Del lado del front, `client.ts` resuelve el `token_expired` con un único refresh compartido entre peticiones y entre pestañas (Web Locks más `BroadcastChannel`), reintenta una vez y, si no puede renovar, manda a `/login?next=`.

## Correcciones aplicadas por DECISIONES.md

- Criterio 2 y supuesto "reusar un refresh rotado solo se rechaza; no se revocan las demás sesiones" → reusar un refresh ya rotado responde 401 `invalid_refresh` **y revoca todas las sesiones del usuario** (es señal de robo); se emite `SessionsRevoked` con `reason = "refresh_reuse"`: corregido por DECISIONES N-13.
- Refresh en cookie `HttpOnly` y access en memoria: aceptado por DECISIONES N-13.
- Criterio 5: el access vencido responde 401 `token_expired`, "distinto de `invalid_token`". Como `invalid_token` es el código 400 de los tokens de un solo uso (N-11), cualquier otro 401 de `current_user` usa `unauthorized`, como define US-034: ajuste de coherencia con DECISIONES N-11.

## Validación contra el dominio

- Las entidades son `User` y `RefreshToken`. La invariante "un refresh ya usado no sirve una segunda vez" se cumple con `revoked_at` y `replaced_by_id`.
- Función pura: `is_refresh_usable(token, user, now) -> bool`. Pide que el token no esté revocado, que no esté vencido y que `can_login(user)` sea verdadero. Se agrega la función pura `is_reuse(token) -> bool`, verdadera cuando `revoked_at` y `replaced_by_id` no son nulos.
- Evento emitido solo en el reuso: `SessionsRevoked(user_id, by=SYSTEM_USER_ID, revoked=n, reason="refresh_reuse")`. Lo audita US-107. No consume eventos.
- Bloquear impide usar las sesiones: `can_login` rechaza a los usuarios bloqueados, y US-050 además revoca sus tokens.

## Validación contra la arquitectura

- El módulo dueño es `modules/auth`. `POST /auth/refresh` está en la lista blanca y se autentica con la cookie.
- Primitivas: `core.security.hash_opaque_token`, `new_opaque_token` y `create_access_token`. Nada de `hashlib` ni `jwt` en el módulo.
- Concurrencia: `SELECT ... FOR UPDATE` sobre la fila del refresh presentado. Una segunda petición simultánea con el mismo token espera y después ve `replaced_by_id`, así que se trata como reuso. Por eso la coordinación del front es obligatoria (ver riesgos).
- Actor: en el reuso, `current_actor = SYSTEM_USER_ID` (N-15), porque no hay usuario autenticado; en la rotación normal, `current_actor = user.id`, para el `created_by` del token nuevo.
- `refresh_tokens` no está auditada. La revocación masiva queda registrada por el evento.
- `token_expired`: hace falta que `current_user` de US-034 distinga `TokenExpired` de `TokenInvalid` (US-033 ya lanza las dos excepciones) y responda `401 token_expired` o `401 unauthorized`.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (usa `refresh_tokens.replaced_by_id` de `0004_auth`, US-041).

### Models
- No aplica.

### Service
- [ ] T1 · Funciones puras `is_refresh_usable(token: RefreshToken, user: User, now: datetime) -> bool` e `is_reuse(token: RefreshToken) -> bool` en `auth/service.py`. — 0.5 h
- [ ] T2 · Función interna compartida `_revoke_all(session, user_id: UUID, *, now, except_id: UUID | None = None) -> int`. Hace un `UPDATE refresh_tokens SET revoked_at = now WHERE user_id = :u AND revoked_at IS NULL AND expires_at > now [AND id <> :except]` y devuelve cuántas filas cambió. La reutilizan US-045, US-048, US-049, US-050 y US-051. — 0.5 h
- [ ] T3 · Caso de uso `refresh(session, refresh_token: str | None, *, user_agent, clock) -> RefreshResult`:
  - sin token, o con un hash inexistente, lanza `InvalidRefresh`;
  - si `is_reuse`, revoca todo con `_revoke_all`, emite `SessionsRevoked(reason="refresh_reuse")`, hace commit y lanza `InvalidRefresh`;
  - si no `is_refresh_usable`, lanza `InvalidRefresh`;
  - en el caso normal, crea el token nuevo, pone `revoked_at` y `replaced_by_id` en el anterior y emite el access. — 2 h
- [ ] T4 · Declarar el evento `SessionsRevoked(user_id, by, revoked: int, reason: Literal["admin","lock","delete","refresh_reuse"])` y la excepción `InvalidRefresh`, que se mapea a 401 `invalid_refresh`. — 0.25 h

### Schemas
- [ ] T5 · `RefreshOut` con `access_token`, `token_type` y `expires_in`, en `auth/schemas.py`. — 0.25 h

### Router
- [ ] T6 · `POST /api/v1/auth/refresh`, público y en la lista blanca:
  - lee la cookie `apex_refresh` e ignora el cuerpo;
  - en 200 llama a `set_refresh_cookie`;
  - en 401 llama a `clear_refresh_cookie`. — 0.75 h

### Tests unitarios puros
- [ ] T7 · `api/tests/auth/test_pure_refresh.py`: `is_refresh_usable` con un token vigente, vencido, revocado y de un usuario bloqueado o borrado; `is_reuse` con un token rotado y con uno revocado por logout (este último no es reuso). — 0.5 h

### Tests de service con PostgreSQL
- [ ] T8 · `api/tests/auth/test_refresh_service.py`:
  - la rotación deja el token anterior con `revoked_at` y `replaced_by_id` en la misma transacción;
  - el nuevo vence a los 7 días;
  - reusar el token viejo revoca los tres refresh vigentes del usuario, emite un `SessionsRevoked(revoked=3, reason="refresh_reuse")` y ese efecto queda tras el 401;
  - un token vencido o de un usuario bloqueado se rechaza;
  - dos `refresh` concurrentes con el mismo token (dos sesiones y `asyncio.gather`) terminan en una rotación y un reuso. — 2.5 h

### Tests de router
- [ ] T9 · `api/tests/auth/test_refresh_router.py`:
  - sin cookie, 401 `invalid_refresh`;
  - el cuerpo se ignora;
  - en el 200 la cookie nueva es distinta de la anterior;
  - una ruta protegida con un access vencido (`FrozenClock` adelantado 16 min) responde 401 `token_expired`;
  - un token con firma inválida responde 401 `unauthorized`. — 1.25 h

### Tests de arquitectura
- [ ] T10 · Que `test_every_route_has_role.py` siga verde con `/auth/refresh` en la lista blanca. — 0.25 h

### Front
- [ ] T11 · `web/src/core/api/client.ts`:
  - interceptor de 401 con `error.code === "token_expired"`;
  - una sola promesa de refresh en curso (single-flight) dentro de la pestaña;
  - entre pestañas, `navigator.locks.request("apex-refresh", ...)`: antes de llamar, la pestaña que obtiene el candado revisa si llegó un token nuevo por `BroadcastChannel("apex-auth")` en los últimos segundos;
  - reintenta cada petición original una sola vez;
  - si el refresh falla, llama a `clearSession()`, publica `logout` en el canal y navega a `/login?next=<ruta>`. — 3 h
- [ ] T12 · `web/src/core/auth/session.ts`: escuchar el canal `apex-auth`, con los mensajes `token` (aplica el access nuevo) y `logout` (limpia la sesión). Nunca se envía el refresh por el canal, porque vive en la cookie. — 0.75 h
- [ ] T13 · Vitest `web/src/core/api/client.test.ts`:
  - tres peticiones concurrentes con `token_expired` hacen un solo refresh y tres reintentos;
  - un refresh 401 lleva a `/login?next=/socios`;
  - un `BroadcastChannel` y `navigator.locks` simulados en dos "pestañas" hacen un solo refresh;
  - nunca se llama a `console.*` con el token. — 2 h

### DevOps
- No aplica.

### Seguridad
- [ ] T14 · Revisión:
  - la detección de reuso revoca todo y queda auditada;
  - el refresh nunca aparece en logs ni en el canal entre pestañas;
  - la cookie se borra en 401;
  - riesgo P7 (HTTP en LAN) anotado. — 0.5 h

## Orden de ejecución
1. T7 (en rojo)
2. T1
3. T8 (en rojo)
4. T2 y T4
5. T3
6. T5
7. T9 (en rojo)
8. T6
9. T10
10. T13 (en rojo)
11. T12 y T11
12. T14

## Dependencias técnicas
- US-042 · Iniciar sesión: emite el primer refresh, la cookie y `session.ts`.
- US-041 · Cuentas de usuario: la columna `replaced_by_id`.
- US-034 · current_user: debe responder `401 token_expired` cuando el JWT está vencido y `401 unauthorized` en cualquier otro caso.
- US-033 · JWT Ed25519: `TokenExpired` frente a `TokenInvalid`, y los helpers de token opaco.
- US-107 · Auditoría de eventos de seguridad: registra `SessionsRevoked`.
- US-059 · Cliente API: `client.ts` existente.

## Endpoints
- `POST /api/v1/auth/refresh` — roles: público (lista blanca)

## Riesgos
- Con N-13, dos pestañas que renuevan a la vez con la misma cookie se ven como reuso y cierran todas las sesiones del usuario. Mitigación: Web Locks más `BroadcastChannel` en T11 y una prueba que lo simula. Los navegadores sin Web Locks caen a un candado en `localStorage` con marca de tiempo, que guarda solo un flag y nunca el token.
- P7: la cookie viaja sin TLS en v0.1. Alguien que la capture en la LAN puede renovar hasta que el dueño use el reuso o el bloqueo. Mitigación: TLS en v0.3 y `COOKIE_SECURE` en cuanto haya dominio.
- Si US-034 no distingue `token_expired`, el front no sabría cuándo renovar. Mitigación: se agrega a la dependencia y lo cubre T9.
- Front condicionado a D1.

## Estimación
- Backend: 4.25 h
- Front: 5.75 h
- Pruebas: 4.5 h
- DevOps / seguridad: 0.5 h
- **Total: 15 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/auth/test_pure_refresh.py -q`
- [ ] `cd api && uv run pytest tests/auth/test_refresh_service.py -q`
- [ ] `cd api && uv run pytest tests/auth/test_refresh_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/core/api src/core/auth`
- [ ] `curl -b 'apex_refresh=<viejo>' -X POST http://localhost/api/v1/auth/refresh` con un refresh ya rotado responde 401 `invalid_refresh`, y después `SELECT count(*) FROM auth.refresh_tokens WHERE user_id = '<u>' AND revoked_at IS NULL` devuelve 0.
- [ ] `SELECT after->>'event' FROM audit.audit_log WHERE record_id = '<u>' ORDER BY seq DESC LIMIT 1` devuelve `SessionsRevoked`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.auth --cov-fail-under=80`
