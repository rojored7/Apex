# US-048 · Activar cuenta y restablecer contraseña — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-048-activar-cuenta-y-restablecer-contrasena.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth (`api/src/app/modules/auth/`, `web/src/features/auth/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

DECISIONES N-10, N-11, N-12, N-13 y N-36 resuelven todo lo que la historia dejaba como supuesto o mencionaba de más:

- la política de contraseña;
- las duraciones de los tokens y el error 400 `invalid_token`;
- que la ruta `GET /users/{id}/activation-link` no existe;
- la revocación de sesiones;
- que en v0.1 no hay correo.

El contrato de `POST /auth/reset` y `POST /auth/forgot` queda completo.

## Resumen

`auth.service.reset(token, new_password)` busca el token por su hash y comprueba que sigue vigente, que no se usó y que el usuario no está bloqueado ni borrado. Valida la política y consume el token de forma atómica (`UPDATE ... WHERE used_at IS NULL RETURNING`). Guarda el hash argon2id y emite `PasswordChanged`. Si el propósito era `reset`, revoca todos los refresh del usuario; si era `activate`, el estado pasa de `pending_activation` a `active` porque ahora hay `password_hash`. `forgot(email)` responde siempre 204, con el rate limit de 5 por minuto por IP. Si el usuario está activo, emite un `OneTimeToken(reset)` de 1 h e invalida los anteriores. El front agrega las tarjetas `/restablecer/:token` y `/recuperar`, y el E2E del flujo completo de la épica.

## Correcciones aplicadas por DECISIONES.md

- Contexto de dominio: "en v0.1 el enlace de recuperación solo se ve desde `GET /users/{id}/activation-link`" → esa ruta **no existe**. En v0.1 el admin entrega el enlace con `POST /users/{id}/resend-link` (US-052), que emite un token nuevo de propósito `reset` e invalida el que haya creado `forgot`: corregido por DECISIONES N-12. Esto también corrige la descripción de `forgot` en `05_service_design.md` sección 3.
- Vencimiento de 72 h para `activate` y de 1 h para `reset`, y 400 `invalid_token`: aceptado por DECISIONES N-11 (eran supuestos).
- Contraseña de 12 caracteres o más, validada contra la lista de contraseñas comunes: corregido por DECISIONES N-10 (la historia solo exigía la longitud).
- `reset` revoca todas las sesiones: coherente con DECISIONES N-13.
- En v0.1 `forgot` crea el token pero no lo envía por ningún canal; el envío por correo con texto fijo y directo llega con US-131: aceptado por DECISIONES N-36.

## Validación contra el dominio

- Las entidades son `User`, `OneTimeToken` (`activate` y `reset`) y `RefreshToken`.
- La invariante "un token de un solo uso se consume una vez" se cumple con un `UPDATE` condicional que debe afectar exactamente una fila.
- Funciones puras:
  - `is_one_time_token_usable(token, user, now) -> bool`: `used_at` nulo, `expires_at > now`, y un usuario no bloqueado, no borrado y con `is_active`;
  - `validate_password_policy` (US-041).
- Evento emitido: `PasswordChanged(user_id, by=user_id, via="activate" | "reset")`. No consume eventos.
- `forgot` solo emite el token para usuarios con `user_status == "active"`. Un usuario pendiente de activación usa `resend-link` (US-052).

## Validación contra la arquitectura

- El módulo dueño es `modules/auth`. Las dos rutas son públicas, están en la lista blanca (`/auth/reset`, `/auth/forgot`) y no exigen access token.
- Rate limit: la dependencia `rate_limit("forgot")` de US-036, con un contador independiente del de login.
- Primitivas: `core.security.hash_opaque_token` y `hash_password`. Nada de `hashlib` ni `argon2` en el módulo.
- Actor de auditoría: `current_actor = token.user_id`, porque el propio usuario actúa sobre su cuenta. En `forgot` es `SYSTEM_USER_ID`, ya que la petición es anónima (N-15).
- Auditoría: `update` sobre `users` con `password_hash` como `"***"`; `update` sobre `one_time_tokens` (`used_at`) con `token_hash` y nunca el token.
- Orden de validación, para no filtrar información:
  1. buscar el token y comprobar que se puede usar (si no, 400);
  2. aplicar la política (si falla, 422 y el token sigue sin usar);
  3. consumirlo de forma atómica (si otra petición ganó, 400).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `is_one_time_token_usable(token: OneTimeToken, user: User, now: datetime) -> bool` en `auth/service.py`. — 0.25 h
- [ ] T2 · Caso de uso `reset(session, token: str, new_password: str, *, clock) -> None`:
  - si `hash_opaque_token` no encuentra el token, o `is_one_time_token_usable` es falso, lanza `InvalidToken` (400 `invalid_token`);
  - `validate_password_policy` lanza `FieldError("new_password")`;
  - `UPDATE one_time_tokens SET used_at = now WHERE id = :id AND used_at IS NULL RETURNING id`; con 0 filas, lanza `InvalidToken`;
  - aplica `hash_password` y, si el propósito es `reset`, llama a `_revoke_all(user_id)`;
  - emite `PasswordChanged(via=purpose)`. — 2.5 h
- [ ] T3 · Caso de uso `forgot(session, email: str, *, clock) -> None`: normaliza el correo y busca el usuario; si su `user_status == "active"`, llama a `_issue_one_time_token(user_id, "reset")` (US-047), que invalida los `reset` anteriores. El token en claro se descarta en v0.1, porque no hay canal (US-131 lo enviará). Nunca lanza un error por un correo inexistente. — 1 h

### Schemas
- [ ] T4 · `ResetIn` (`token: str` de 20 a 200 caracteres, `new_password: SecretStr` con un máximo de 1024) y `ForgotIn` (`email: EmailStr`). — 0.5 h

### Router
- [ ] T5 · `POST /api/v1/auth/reset` (públicos: 204, 400 `invalid_token`, 422 `field: "new_password"`) y `POST /api/v1/auth/forgot` (`rate_limit("forgot")`: 204, 422 `field: "email"`, 429). Las dos rutas se agregan a la lista blanca de US-035. — 1 h

### Tests unitarios puros
- [ ] T6 · `api/tests/auth/test_pure_one_time_token.py`: `is_one_time_token_usable` con un token vigente, usado, vencido (en el límite exacto de `expires_at`), de un usuario bloqueado y de uno borrado. — 0.5 h

### Tests de service con PostgreSQL
- [ ] T7 · `api/tests/auth/test_reset_forgot.py`, con `FrozenClock`:
  - activar deja el estado en `active` y `used_at` puesto, y después el login funciona;
  - un segundo uso lanza `InvalidToken` y el hash no cambia;
  - una contraseña corta lanza `FieldError` y el token sigue sin usar;
  - un `reset` con dos sesiones abiertas las revoca a las dos;
  - un token vencido (más de 1 h) se rechaza;
  - dos `reset` concurrentes con el mismo token (`asyncio.gather`) producen exactamente un éxito;
  - `forgot` con un correo inexistente no crea filas;
  - `forgot` repetido deja un solo `reset` abierto;
  - `forgot` de un usuario bloqueado o pendiente no crea nada;
  - la auditoría no contiene el token. — 2.5 h

### Tests de router
- [ ] T8 · `api/tests/auth/test_reset_forgot_router.py`:
  - `reset` responde 204, 400 `invalid_token` y 422 con `field`;
  - `forgot` responde 204 con un correo existente y también con uno inexistente, con cuerpos idénticos;
  - el sexto `forgot` por IP responde 429;
  - los dos endpoints funcionan sin `Authorization`. — 1.25 h

### Tests de arquitectura
- [ ] T9 · Que `test_every_route_has_role.py` siga verde con `/auth/reset` y `/auth/forgot` en la lista blanca. — 0.1 h

### Front
- [ ] T10 · Hooks `useResetPassword()` y `useForgotPassword()` en `web/src/features/auth/api.ts`; Zod `resetSchema` (mínimo 12 y confirmación) y `forgotSchema` en `web/src/features/auth/schemas.ts`. — 0.75 h
- [ ] T11 · `web/src/features/auth/pages/ResetPage.tsx` en `/restablecer/:token`:
  - lee el token y llama a `history.replaceState` para sacarlo de la barra de direcciones;
  - tarjeta "Nueva contraseña / Activar cuenta" con dos `Field`;
  - ante un 400 muestra "El enlace ya no es válido. Pide uno nuevo al administrador.";
  - ante un 422, el error queda bajo el campo;
  - ante un 204, lleva a `/login` con un aviso de éxito. — 2 h
- [ ] T12 · `web/src/features/auth/pages/ForgotPage.tsx` en `/recuperar`: tarjeta "Olvidé mi contraseña" que envía `forgot` y muestra siempre "Pídele al administrador tu enlace de recuperación" (`// DESIGN-GAP:` el texto de v0.1 no está en el diseño). Las rutas son públicas en `routes.tsx`. — 1 h
- [ ] T13 · Vitest `web/src/features/auth/pages/ResetPage.test.tsx` y `ForgotPage.test.tsx`: confirmación distinta, 400, 422, 204 con navegación, y el mismo mensaje con un correo existente y con uno inexistente. — 1.5 h
- [ ] T14 · Playwright `web/tests/e2e/users-activation.spec.ts`, el criterio de éxito de EP-04: login del admin, crear el coach (US-047), copiar el enlace, abrirlo, definir la contraseña y entrar como coach a `/`. — 2 h

### DevOps
- [ ] T15 · `infra/nginx/default.conf`: `location ~ ^/restablecer/ { access_log off; try_files $uri /index.html; }`, para que el token del enlace no quede en el log de acceso de Nginx. Prueba manual documentada en el PR. — 0.5 h

### Seguridad
- [ ] T16 · Revisión:
  - `forgot` no permite enumerar cuentas (mismo cuerpo, sin diferencia observable de código);
  - el token no aparece en logs, ni en auditoría, ni en la barra de direcciones después de cargar;
  - `Referrer-Policy` de US-038 vigente;
  - consumo atómico del token;
  - rate limit de `forgot`. — 0.5 h

## Orden de ejecución
1. T6 (en rojo)
2. T1
3. T7 (en rojo)
4. T2 y T3
5. T4
6. T8 (en rojo)
7. T5
8. T9
9. T13 (en rojo)
10. T10, T11 y T12
11. T15
12. T14
13. T16

## Dependencias técnicas
- US-047 · Crear usuario con enlace de activación: genera el token `activate` y el helper `_issue_one_time_token`.
- US-036 · Rate limit en login y forgot: `rate_limit("forgot")`.
- US-043 · Renovar sesión: `_revoke_all`.
- US-041 · `validate_password_policy` y `__audit_redact__` (US-016).
- US-038 · Cabeceras de seguridad (`Referrer-Policy`) y la configuración de Nginx.
- US-052 · Reenviar enlace: es la única forma de entregar un enlace `reset` en v0.1 (N-12).
- US-131 (v0.2): enviará por correo el token de `forgot`, con texto fijo (N-36).

## Endpoints
- `POST /api/v1/auth/reset` — roles: público (lista blanca)
- `POST /api/v1/auth/forgot` — roles: público (lista blanca)

## Riesgos
- En v0.1, `forgot` crea un token que nadie puede ver. El usuario depende del admin, que emite otro con `resend-link`. Mitigación: el texto fijo de la tarjeta lo explica y el runbook lo documenta.
- El token del enlace viaja en la ruta (`/restablecer/<token>`), que se puede registrar en logs o en el historial. Mitigación: T15 (sin log en Nginx), T11 (`replaceState`), uso único y TTL corta.
- P7: en v0.1 la contraseña nueva viaja sin TLS en la LAN. Mitigación: EP-20 en v0.3.
- Front condicionado a D1.

## Estimación
- Backend: 5.25 h
- Front: 7.25 h
- Pruebas: 4.35 h
- DevOps / seguridad: 1 h
- **Total: 18 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/auth/test_pure_one_time_token.py tests/auth/test_reset_forgot.py tests/auth/test_reset_forgot_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/auth/pages`
- [ ] `cd web && npx playwright test tests/e2e/users-activation.spec.ts`
- [ ] `curl -X POST -d '{"token":"<t>","new_password":"Kettlebell2026!"}' http://localhost/api/v1/auth/reset` responde 204 la primera vez y 400 `invalid_token` la segunda.
- [ ] `curl -X POST -d '{"email":"nadie@apex.co"}' http://localhost/api/v1/auth/forgot` responde 204 sin crear filas en `auth.one_time_tokens`.
- [ ] `docker compose logs web | grep restablecer` no muestra tokens.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.auth --cov-fail-under=80`
