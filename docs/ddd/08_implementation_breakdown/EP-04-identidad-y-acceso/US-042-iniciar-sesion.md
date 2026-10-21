# US-042 · Iniciar sesión — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-042-iniciar-sesion.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth (`api/src/app/modules/auth/`, `web/src/features/auth/`, `web/src/core/auth/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

El contrato de `POST /auth/login` está completo: entrada, salida, cookie, códigos y error genérico. DECISIONES fija dónde vive cada token (N-13), qué hacer con los correos inexistentes (N-31) y el usuario técnico (N-15). La fila de auditoría `login` la escribe US-107 con un evento que emite esta historia; aquí no se escribe auditoría a mano.

## Resumen

`auth.service.login` normaliza el correo y verifica la contraseña con `core.security`. Si el usuario no existe, verifica contra un hash ficticio para no filtrar por tiempo. Emite un access token JWT Ed25519 de 15 minutos y un refresh opaco de 7 días, que se guarda solo como hash en `auth.refresh_tokens`. El refresh se entrega en una cookie `HttpOnly`. Si el usuario existe, el intento emite `LoginAttempted` con el resultado. El front crea la tarjeta "Ingresar", guarda la sesión solo en memoria y redirige según el rol.

## Correcciones aplicadas por DECISIONES.md

- Criterio 6: "cada intento deja auditoría, con `user_id` nulo si el correo no existe" → un login fallido con un correo que no existe solo genera log y cuenta para el rate limit; no deja auditoría ni evento: corregido por DECISIONES N-31.
- Criterio 6: la fila de auditoría `login` la escribe el handler de US-107 a partir del evento `LoginAttempted(user_id, result)`. `auth.service` no llama a `core.audit.record`. Esto sigue la instrucción de la épica de que la auditoría de login es de US-107; el texto de US-107 dice lo contrario y se reporta como contradicción.
- El supuesto "refresh en cookie `HttpOnly` y access solo en memoria" queda confirmado: aceptado por DECISIONES N-13.
- El usuario técnico `system@apex.local` (`is_active = false`, sin contraseña) siempre recibe el 401 genérico: corregido por DECISIONES N-15.

## Validación contra el dominio

- Las entidades son `User` y `RefreshToken`. La invariante "bloquear impide login" se cumple con la función pura `can_login(user)`: `is_active`, sin `locked_at`, sin `deleted_at` y con `password_hash`.
- RN-15: login está en la lista blanca pública.
- Evento emitido: `LoginAttempted(user_id: UUID, result: Literal["ok", "failed"])`, una dataclass congelada en `auth/service.py`. Solo se emite cuando el correo corresponde a un usuario existente. No consume eventos.
- `last_login_at` se actualiza en el login correcto, dentro de la misma transacción. Lo usa US-046.
- No hay discrepancias con `02_domain_model.md`.

## Validación contra la arquitectura

- El módulo dueño es `modules/auth`. El router solo valida, aplica el rate limit, llama a `auth.service.login` y escribe la cookie.
- Primitivas, todas en `core.security`:
  - `verify_password`, `needs_rehash` y `hash_password` (US-032);
  - `create_access_token(sub, role)` (US-033);
  - `new_opaque_token() -> (token, token_hash)` y `hash_opaque_token(token)`, que son la generalización de `new_refresh_token()` de US-033.

  Ni `hashlib` ni `jwt` entran a `modules/auth`.
- La transacción no es la habitual. En un fallo, el service emite el evento, hace `commit` y después lanza `InvalidCredentials`, porque `get_session` revierte ante cualquier excepción (US-012) y la auditoría del intento fallido se perdería. Hay una prueba específica.
- Actor de auditoría y `created_by`: el service fija `current_actor = user.id` antes del flush, porque la ruta es pública y no pasa por `current_user`.
- `User.__audit_exclude__ = {"last_login_at"}` evita una fila `update` por cada login. La fila útil la deja US-107.
- El rate limit es la dependencia `rate_limit("login")` de US-036 y corre antes de leer el cuerpo.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (usa `0004_auth` de US-041, que ya incluye `last_login_at`).

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `can_login(user: User) -> bool` en `auth/service.py`. — 0.5 h
- [ ] T2 · Caso de uso `login(session, email: str, password: str, *, ip: str, user_agent: str | None, clock: Clock) -> LoginResult`. Devuelve `access_token`, `expires_in = 900`, `refresh_token` en claro (solo para la cookie) y un resumen `user`. Pasos:
  - normaliza el correo con `normalize_login_email`;
  - busca el usuario no borrado; si no existe, llama a `verify_password(DUMMY_HASH, password)` y lanza `InvalidCredentials` sin emitir nada;
  - si existe y la verificación o `can_login` falla, emite `LoginAttempted(result="failed")`, hace commit y lanza `InvalidCredentials`;
  - si todo pasa, rehace el hash si `needs_rehash`, actualiza `last_login_at`, inserta `RefreshToken` (`token_hash`, `expires_at = now + 7 d`, `user_agent[:255]`) y emite `LoginAttempted(result="ok")`. — 3 h
- [ ] T3 · Declarar el evento `LoginAttempted` y la excepción `InvalidCredentials` en `auth/exceptions.py`, que se mapea a 401 `invalid_credentials` con el mensaje "Correo o contraseña incorrectos". `DUMMY_HASH` se calcula una vez al importar, con `core.security.hash_password` y una constante de 32 caracteres. — 0.5 h

### Schemas
- [ ] T4 · En `auth/schemas.py`:
  - `LoginIn`: `email: EmailStr` y `password: SecretStr` con `min_length = 1` y `max_length = 1024`, para no hacer argon2 sobre cuerpos enormes;
  - `LoginOut`: `access_token`, `token_type: Literal["bearer"]`, `expires_in: int` y `user: UserSummary` (`id`, `email`, `role`). — 0.5 h

### Router
- [ ] T5 · `POST /api/v1/auth/login` en `auth/router.py`, público y en la lista blanca de US-035, con la dependencia `rate_limit("login")`. Responde 200 con `LoginOut` y llama a `set_refresh_cookie(response, token)`. Códigos: 200, 401, 422 y 429. — 1 h
- [ ] T6 · Helper `set_refresh_cookie` y `clear_refresh_cookie` en `auth/router.py`:
  - cookie `apex_refresh` con `HttpOnly`, `SameSite=Strict`, `Path=/api/v1/auth` y `Max-Age=604800`;
  - `Secure` según `Settings.COOKIE_SECURE`, que vale false solo en v0.1 en LAN (P7). — 0.5 h

### Tests unitarios puros
- [ ] T7 · `api/tests/auth/test_pure_login.py`: `can_login` con un usuario activo (true), bloqueado, `is_active = false`, borrado, sin `password_hash` y el usuario técnico. — 0.5 h

### Tests de service con PostgreSQL
- [ ] T8 · `api/tests/auth/test_login_service.py`, con `FrozenClock`:
  - en un login correcto queda una fila en `refresh_tokens` con `token_hash` distinto del token y `expires_at` igual a ahora más 7 días;
  - `last_login_at` queda en ahora;
  - se emite un solo `LoginAttempted("ok")`;
  - una contraseña incorrecta emite `LoginAttempted("failed")` y el evento sobrevive al 401 (la prueba verifica el commit);
  - un correo inexistente no emite eventos y llama al verificador con `DUMMY_HASH` (espía);
  - un usuario bloqueado, inactivo, borrado o técnico recibe `InvalidCredentials`;
  - un hash con parámetros viejos se rehace. — 2.5 h

### Tests de router
- [ ] T9 · `api/tests/auth/test_login_router.py`:
  - las cinco causas de rechazo devuelven exactamente el mismo cuerpo y el mismo código 401;
  - `email` mal formado o ausente responde 422 con `field`;
  - el sexto intento por IP en 60 s responde 429 sin llamar al service;
  - la cookie de la respuesta tiene los atributos de T6;
  - el cuerpo de la respuesta no contiene el refresh;
  - `" Coach@Apex.co "` inicia sesión. — 2 h

### Tests de arquitectura
- [ ] T10 · Que `test_every_route_has_role.py` (US-035) siga verde con `/auth/login` en la lista blanca, y que `test_banned_imports.py` siga verde sin `jwt`, `argon2` ni `hashlib` en `modules/auth`. — 0.25 h

### Front
- [ ] T11 · `web/src/core/auth/session.ts`:
  - store en memoria con `accessToken`, `user` y `expiresAt`, más `setSession`, `clearSession`, `getAccessToken` y `subscribe`;
  - prohibido usar `localStorage` y `sessionStorage`, lo que se verifica con una prueba de búsqueda en `web/src/core/auth`;
  - `homeFor(role)` en `web/src/core/auth/home.ts`, que US-053 reutiliza. — 1.5 h
- [ ] T12 · Esquema Zod `loginSchema` en `web/src/features/auth/schemas.ts` y hook `useLogin()` con TanStack Query (`useMutation`) en `web/src/features/auth/api.ts`, que llama a `POST /auth/login` con `credentials: "include"` desde `core/api/client.ts`. — 1 h
- [ ] T13 · `web/src/features/auth/pages/LoginPage.tsx` y `components/LoginCard.tsx` con `Field`, `Button` y `react-hook-form`:
  - estados inicial, cargando (botón deshabilitado) y error genérico sobre la tarjeta;
  - ante un error conserva el correo y limpia la contraseña;
  - al terminar, `setSession` y `navigate(next ?? homeFor(role))`;
  - solo tokens, nada de colores literales, controles de 44 px y foco visible. — 3 h
- [ ] T14 · Vitest `web/src/features/auth/pages/LoginPage.test.tsx`: éxito con redirección por rol, error 401 con el mensaje que conserva el correo, 422 y botón deshabilitado durante la petición. — 1.5 h
- [ ] T15 · Playwright `web/tests/e2e/login.spec.ts`, "login de admin": entra con el admin de seed y ve `/`. — 1.5 h

### DevOps
- [ ] T16 · Agregar `COOKIE_SECURE` (bool, por defecto true) a `core/config.py` y a `.env.example`, con una nota de que en v0.1 en LAN sin TLS se pone en false (P7). — 0.25 h

### Seguridad
- [ ] T17 · Revisión:
  - respuesta 401 idéntica en cuerpo y en tiempo aproximado (verificación ficticia);
  - rate limit antes de argon2;
  - ningún log con `password` ni con el token (filtro `redact` de US-018);
  - cookie `HttpOnly` y `Strict`;
  - access token fuera del almacenamiento persistente;
  - `user_agent` truncado. — 0.75 h

## Orden de ejecución
1. T7 (en rojo)
2. T1
3. T8 (en rojo)
4. T3 y T2
5. T4
6. T9 (en rojo)
7. T6 y T5
8. T10
9. T16
10. T11
11. T12
12. T14 (en rojo)
13. T13
14. T15
15. T17

## Dependencias técnicas
- US-041 · Cuentas de usuario y admin inicial: tablas, `normalize_login_email` y el usuario técnico.
- US-032 · argon2id: `verify_password` y `needs_rehash`.
- US-033 · JWT Ed25519: `create_access_token`. Además, `new_opaque_token()` y `hash_opaque_token()` tienen que exponerse en `core.security`; hoy US-033 solo define `new_refresh_token()`.
- US-036 · Rate limit en login y forgot: la dependencia `rate_limit("login")`.
- US-016 · Hook de auditoría: `__audit_exclude__` para `last_login_at`.
- US-107 · Auditoría de eventos de seguridad: se suscribe a `LoginAttempted` y escribe la acción `login`.
- US-059 · Cliente API y tipos generados: `client.ts` con `credentials: "include"`.
- US-060 y US-062 · Componentes `Field` y `Button` del kit.

## Endpoints
- `POST /api/v1/auth/login` — roles: público (lista blanca)

## Riesgos
- P7: en v0.1 los tokens y la contraseña viajan por HTTP en la LAN, y la cookie no puede llevar `Secure`. Mitigación: `COOKIE_SECURE` configurable y TLS con Caddy en v0.3 (EP-20). Anotado en el runbook.
- El commit explícito en el camino de fallo rompe el patrón de "una transacción por petición". Mitigación: se limita a `login` y lo cubre T8.
- El texto de US-107 dice que `auth.service` llama a `core.audit.record`. Si US-107 se implementa así, la acción `login` quedaría duplicada. Mitigación: se reporta al orquestador; el contrato es el evento `LoginAttempted`.
- P5, correo en claro: si cambia en el gate, cambia la búsqueda del usuario.
- Front condicionado a D1.

## Estimación
- Backend: 6 h
- Front: 8.5 h
- Pruebas: 5.25 h
- DevOps / seguridad: 1 h
- **Total: 21 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/auth/test_pure_login.py -q`
- [ ] `cd api && uv run pytest tests/auth/test_login_service.py -q`
- [ ] `cd api && uv run pytest tests/auth/test_login_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/auth src/core/auth`
- [ ] `cd web && npx playwright test tests/e2e/login.spec.ts`
- [ ] `curl -i -X POST http://localhost/api/v1/auth/login -H 'Content-Type: application/json' -d '{"email":"dueno@apex.co","password":"<clave>"}'` devuelve 200, `Set-Cookie: apex_refresh=...; HttpOnly; SameSite=Strict; Path=/api/v1/auth`, y `SELECT count(*) FROM auth.refresh_tokens WHERE token_hash = '<valor de la cookie>'` devuelve 0, porque solo se guarda el hash.
- [ ] Seis `curl` seguidos con una contraseña errada: el sexto responde 429 `rate_limited`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.auth --cov-fail-under=80`
