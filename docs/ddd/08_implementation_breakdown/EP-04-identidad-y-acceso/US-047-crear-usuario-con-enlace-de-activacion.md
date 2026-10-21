# US-047 · Crear usuario con enlace de activación — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-047-crear-usuario-con-enlace-de-activacion.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth (`api/src/app/modules/auth/`, `web/src/features/system/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

DECISIONES N-11 cierra los supuestos de la historia: 72 h para la activación y la URL base `FRONT_BASE_URL`. DECISIONES N-36 confirma que en v0.1 el enlace solo lo entrega el endpoint de admin, porque no hay correo. El contrato de entrada y salida y los códigos 201, 409 y 422 están completos.

## Resumen

`auth.service.create_user` valida el rol y el `member_id`, normaliza y comprueba que el correo no esté repetido entre los no borrados, y crea el `User` sin contraseña (`password_hash` nulo, estado `pending_activation`). Después emite un `OneTimeToken(activate)` de 72 h, guardado solo como hash, y devuelve `activation_url = <FRONT_BASE_URL>/restablecer/<token>` una sola vez. Emite `UserCreated`. El helper `_issue_one_time_token` lo reutilizan `forgot` (US-048) y `resend_link` (US-052). El front agrega el `SidePanel` "Nuevo usuario" con el enlace de solo lectura, el botón "Copiar" y la advertencia de entregarlo por un medio seguro.

## Correcciones aplicadas por DECISIONES.md

- Vencimiento de 72 h para `activate` y URL desde `FRONT_BASE_URL`: aceptado por DECISIONES N-11 (eran supuestos).
- En v0.1 el enlace lo devuelve el endpoint de admin y no se envía correo; en v0.2, US-131 lo enviará con texto fijo y de forma directa, no por la cola: aceptado por DECISIONES N-36. `create_user` deja un punto de extensión, el parámetro `notify: bool = False`, que no se usa en v0.1.
- El `created_by` de la fila es el admin autenticado. No existe un actor `seed` ni `SYSTEM_ACTOR_ID`: coherente con DECISIONES N-15.

## Validación contra el dominio

- Las entidades son `User` y `OneTimeToken(activate)`. La invariante "un token de un solo uso se consume una vez" la garantiza US-048. Aquí se garantiza que el token se guarde solo como hash.
- S7: `role = member` exige `member_id` (422 con `field: "member_id"`), y `admin` o `coach` con `member_id` también responde 422 (v0.1). La pantalla solo ofrece `admin` y `coach`.
- Evento emitido: `UserCreated(user_id, role, by)`.
- Funciones puras: `validate_user_role` (US-041) y `activation_url(base_url: str, token: str) -> str`.
- No consume eventos.

## Validación contra la arquitectura

- El módulo dueño es `modules/auth` y el rol es `require_role("admin")`.
- No se llama a `members.service` para validar `member_id`. La historia no lo pide y, en v0.1, la pantalla no crea socios usuarios; la validación de existencia llega con US-185 (Members llama a Auth). Así no se crea una dependencia de auth hacia members.
- Primitivas: el token sale de `core.security.new_opaque_token()` (32 bytes en base64url y su hash SHA-256). Nada de `secrets` ni `hashlib` en el módulo.
- Auditoría: el hook registra `insert` sobre `users` (con `password_hash` nulo, redactado como `"***"`) e `insert` sobre `one_time_tokens` con `token_hash` y no el token.
- Error 409 `email_taken` con `field: "email"` y `existing_id`, según el envelope de US-017. Una carrera contra el índice único parcial se traduce en el mismo 409.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Constantes `ACTIVATE_TTL = timedelta(hours=72)` y `RESET_TTL = timedelta(hours=1)` (N-11), y función pura `activation_url(base_url, token)`, que quita la `/` final y agrega `/restablecer/<token>`. — 0.25 h
- [ ] T2 · Helper `_issue_one_time_token(session, user_id: UUID, purpose: Purpose, *, clock) -> tuple[str, OneTimeToken]`:
  - pone `used_at = now` en los tokens del mismo propósito y usuario que siguen con `used_at IS NULL`;
  - crea el token nuevo con `expires_at = now + TTL`;
  - devuelve el token en claro, que nunca se guarda ni se loguea. — 1 h
- [ ] T3 · Caso de uso `create_user(session, *, email: str, role: Role, member_id: UUID | None, by: UUID, clock, notify: bool = False) -> CreatedUser`, que devuelve `user` y `activation_url`. Pasos: `validate_user_role`, `normalize_login_email`, búsqueda de un usuario no borrado con ese correo (si existe, `EmailTaken(existing_id)`), `User(password_hash=None)`, `_issue_one_time_token("activate")` y `UserCreated`. Un `IntegrityError` del índice único se traduce a `EmailTaken`. — 1.5 h

### Schemas
- [ ] T4 · `CreateUserIn` (`email: EmailStr`, `role: Role`, `member_id: UUID | None = None`) y `CreateUserOut` (`user: UserOut` con `status`, y `activation_url: str`). — 0.5 h

### Router
- [ ] T5 · `POST /api/v1/users` con `require_role("admin")`. Responde 201 con `CreateUserOut`; los demás códigos son 401, 403, 409 (`email_taken`, `field`, `existing_id`) y 422 (`field: "member_id"` o `"role"`). — 0.75 h

### Tests unitarios puros
- [ ] T6 · `api/tests/auth/test_pure_links.py`: `activation_url` con y sin `/` final; las TTL valen 72 h y 1 h. — 0.25 h

### Tests de service con PostgreSQL
- [ ] T7 · `api/tests/auth/test_create_user.py`, con `FrozenClock`:
  - el usuario se crea con `password_hash` nulo y `user_status == "pending_activation"`;
  - un token `activate` con `expires_at` igual a ahora más 72 h y `token_hash` distinto del token de la URL;
  - `created_by` es el admin;
  - hay dos filas `insert` en `audit.audit_log` (`users` y `one_time_tokens`) sin el token en claro;
  - se emite `UserCreated`;
  - un correo repetido entre no borrados lanza `EmailTaken` con el id, y si el anterior está borrado se puede crear;
  - el usuario recién creado no puede iniciar sesión (US-042). — 1.5 h

### Tests de router
- [ ] T8 · `api/tests/auth/test_create_user_router.py`:
  - 201 con una `activation_url` que contiene `/restablecer/`;
  - 409 con `field` y `existing_id`;
  - 422 para `member` sin `member_id` y para un rol inválido;
  - 403 para coach;
  - el log capturado no contiene el token. — 1 h

### Tests de arquitectura
- [ ] T9 · Que `test_banned_imports.py` siga verde (sin `secrets.token_*` ni `hashlib` en `modules/auth` si la regla los incluye) y también `test_every_route_has_role.py`. — 0.1 h

### Front
- [ ] T10 · Hook `useCreateUser()` (`useMutation`, invalida `["users"]`) en `web/src/features/system/api.ts`, y Zod `createUserSchema` (`email`, `role` en `admin` o `coach`) en `web/src/features/system/schemas.ts`. — 0.5 h
- [ ] T11 · `web/src/features/system/components/NewUserPanel.tsx`, un `SidePanel` con `Field` de correo y selector de rol:
  - después del 201 muestra el enlace en un campo de solo lectura, el botón "Copiar" (`navigator.clipboard.writeText`, con aviso de confirmación) y la advertencia "Entrega este enlace por un medio seguro; vence en 72 horas";
  - al cerrar se descarta el enlace del estado;
  - un 409 se muestra bajo el correo, con un enlace al usuario existente;
  - lo abre el botón "Nuevo usuario" de `UsersPage`. — 2.5 h
- [ ] T12 · Vitest `web/src/features/system/components/NewUserPanel.test.tsx`: crear, mostrar y copiar; al cerrar, el enlace no se ve; error 409 por campo. — 1 h

### DevOps
- [ ] T13 · Comprobar que `FRONT_BASE_URL` (US-041, T13) está en `.env.example` con el valor de la LAN, por ejemplo `http://apex.local`. — 0.1 h

### Seguridad
- [ ] T14 · Revisión:
  - el token tiene al menos 256 bits de entropía y solo se guarda su hash;
  - el enlace solo aparece en la respuesta 201;
  - no se loguea;
  - el front no lo guarda en almacenamiento persistente;
  - riesgo de entrega manual (EP-04) anotado. — 0.4 h

## Orden de ejecución
1. T6 (en rojo)
2. T1
3. T7 (en rojo)
4. T2 y T3
5. T4
6. T8 (en rojo)
7. T5
8. T9
9. T13
10. T12 (en rojo)
11. T10 y T11
12. T14

## Dependencias técnicas
- US-046 · Listar usuarios: la pantalla y la consulta `["users"]`.
- US-041 · Cuentas de usuario: las tablas, `validate_user_role`, `normalize_login_email` y `FRONT_BASE_URL`.
- US-033 · `core.security.new_opaque_token()`.
- US-016 · Hook de auditoría con `__audit_redact__`.
- US-017 · Envelope de error con `existing_id`.
- US-065 · Panel lateral y modal de confirmación.
- US-131 (v0.2) y US-185 (v1.0) reutilizan `create_user`. Su firma queda fijada aquí.

## Endpoints
- `POST /api/v1/users` — roles: admin

## Riesgos
- Sin correo en v0.1, el admin entrega el enlace a mano y puede compartirlo por un medio inseguro. Mitigación: la advertencia en pantalla, el vencimiento de 72 h, el uso único y `resend-link` para invalidarlo (US-052).
- Un `member_id` que no existe en el padrón se acepta en el API hasta US-185. Mitigación: la pantalla de v0.1 no ofrece el rol `member`. Se anota para EP-25.
- Front condicionado a D1.

## Estimación
- Backend: 4 h
- Front: 4 h
- Pruebas: 2.85 h
- DevOps / seguridad: 0.5 h
- **Total: 11 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/auth/test_pure_links.py tests/auth/test_create_user.py tests/auth/test_create_user_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system/components/NewUserPanel.test.tsx`
- [ ] `curl -X POST -H 'Authorization: Bearer <admin>' -d '{"email":"ana@apex.co","role":"coach"}' http://localhost/api/v1/users` responde 201 con `activation_url`, y `SELECT purpose, expires_at - created_at FROM auth.one_time_tokens WHERE user_id = '<id>'` devuelve `activate | 72:00:00`.
- [ ] `SELECT count(*) FROM audit.audit_log WHERE after::text LIKE '%<token de la URL>%'` devuelve 0.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.auth --cov-fail-under=80`
