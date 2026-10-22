# Exploración Sprint 2 (Fase 1 de /flow-update)

Rama `feat/sprint-02-identidad-config-socios-planes`, HEAD `482295f`, árbol limpio. Solo lectura: no se corrió pytest ni vitest (línea base del cierre del Sprint 1 en `docs/scratch/sprint-01.md`). Rutas relativas a la raíz; `core/` = `api/src/app/core/`.

## 0. Resumen ejecutivo

El Sprint 1 dejó casi todo el material. Falta construir: routers (el de auth está vacío), `modules/settings|members|plans`, `session.ts`, router del front, layouts y fixtures de pruebas autenticadas.

Riesgos y bloqueantes que cambian el diseño (detalle en secciones 5 y 6):

1. **Escrituras en rutas que responden 401 se pierden.** `get_session` (`core/db.py:145-152`) hace rollback si el handler lanza `DomainError`. Afecta: reuso de refresh que revoca todo (N-13, US-043), login fallido (auditoría, bloqueo por cuenta M-2) y `LoginAttempted`. Hay que responder con `JSONResponse` (retorno normal, commit) o usar sesión propia (`db.get_sessionmaker()()`).
2. **Rutas públicas sin actor.** `login`, `refresh`, `reset`, `forgot` no pasan por `current_user`; `RefreshToken`, `OneTimeToken` y `User.last_login_at` fallan con `MissingActorError`. `actor_scope` como `with` se cierra antes del commit del teardown: hacer `await session.flush()` dentro del scope o `current_actor.set(...)` directo (lo limpia `RequestLogMiddleware`, `core/logging.py:161,175`).
3. **`--strict-markers` y `-m perf`.** `api/pyproject.toml:77-80` solo registra `db`. `tests/members/test_list_perf.py` (S2-B8) falla en la colección.
4. **`tests/architecture/test_no_sensitive_in_logs.py`** se activa cuando existen `auth.router` Y `members.router`. Al crear `members/router.py` (S2-B7) deja de saltarse y su cuerpo es un `raise AssertionError` de relleno. `tests/architecture` corre en cada gate (A-5): bloquea el checkpoint de B7 si no se implementa ahí.
5. **`clear_subscribers()` global** (autouse en `tests/core/test_events.py:43` y `test_events_db.py:30`) vacía el bus para el resto de la corrida; los suscriptores se registran una sola vez al importar `service.py`. Los tests de `members`, `plans`, `settings` corren después de `core` y no verán los handlers. Hace falta un fixture que guarde y restaure `events._subscribers`.
6. **Rate limit global entre pruebas** (`core/ratelimit.py:108-120`): más de 5 logins en 60 s (con `FrozenClock` la ventana no avanza; la IP de `ASGITransport` es fija) dan 429. Fixture autouse con `reset_store()`.
7. **Entorno local:** `.env` tiene `FRONT_BASE_URL=http://localhost` pero `WEB_PORT` distinto de 80 (el stack está en `:8180`). El enlace de activación apuntaría al puerto 80.
8. **Contradicciones de contrato/diseño** (6.9): `Usuarios.html` pide "Nombre" y `auth.users` no tiene `display_name`; `/auth/me/password` vs `/me/password`; `plans.view` solo admin en la matriz del front vs `GET /plans` para coach; `activate` no existe como endpoint.

## 1. Backend: puntos de integración del Sprint 1

### 1.1 `core/security.py` (548 líneas)

| Símbolo | Línea | Uso en el Sprint 2 |
|---|---|---|
| `Principal(user_id, role, member_id)` | 381 | Dataclass congelada que devuelve `current_user`. |
| `PrincipalLoader` / `register_principal_loader` / `get_principal_loader` | 388/395/400 | Puerto; `auth.service.load_active_principal` se registra al importarse (`modules/auth/service.py:164`). |
| `current_user` | 423 | Lee `Authorization: Bearer`, decodifica, rechaza `SYSTEM_USER_ID` (434), pide el principal a la base (manda el rol de la base, no el claim), `current_actor.set(...)` sin resetear (439). Depende de `get_session`. |
| `require_role(*roles)` | 443 | Dependencia por ruta, marca `__apex_roles__`: `Annotated[Principal, Depends(require_role("admin"))]`. |
| `PUBLIC_ROUTES` | 461 | Health x2, `POST /api/v1/auth/{login,refresh,forgot,reset}`, `GET /api/v1/tv/today`. No hay `activate`. |
| `create_access_token(user_id, role, member_id, clock)` | 204 | Usa TTL y llaves de `configure_security`; claims `sub, role, member_id, iat, exp, jti`. |
| `decode_access_token(token, clock)` | 210 | `TokenExpired` solo con firma válida y vencido (leeway 30 s); lo demás `TokenInvalid`. |
| `new_refresh_token()` -> `(token, hash)` | 264 | 32 bytes base64url; solo se persiste el SHA-256. |
| `new_opaque_token()` / `hash_opaque_token()` | 251/256 | Para `OneTimeToken`. Texto no ASCII lanza `TokenInvalid`. |
| `hash_password(plain)` | 303 | Valida política N-10 (`WeakPasswordError`); cuesta CPU: `anyio.to_thread.run_sync` (ejemplo `auth/service.py:124`). |
| `verify_password(hash, plain)` / `needs_rehash` | 308/315 | `verify_password` nunca lanza. |
| `dummy_verify(plain)` | 333 | Iguala tiempo con correo inexistente; también `to_thread`. |
| `configure_security(settings)` | 341 | Lo llama el lifespan; en pruebas sin lifespan hay que llamarlo (llaves JWT globales). |

`unprotected_routes()` (533) alimenta `test_every_route_has_role`.

### 1.2 `core/ratelimit.py`
`rate_limit(bucket, limit=5, window_s=60)` (123) devuelve una dependencia con `__apex_rate_limit__`. Uso: `@router.post("/login", dependencies=[Depends(rate_limit("login"))])`; `test_login_y_forgot_llevan_limite_de_intentos` lo exige en `/auth/login` y `/auth/forgot`. La IP real sale de `X-Forwarded-For` solo si el socket está en `TRUSTED_PROXIES`; Nginx sobrescribe la cabecera con `$remote_addr` (`infra/nginx/snippets/proxy-api.conf`). Estado en `app.state.trusted_proxies` y `rate_limit_max_keys` (`main.py:180-181`). Almacén en memoria, un proceso. `reset_store()` (118). Orden: las dependencias del router (`refresh_keyring` -> `get_session`) corren ANTES de `rate_limit`, así que un 429 abre una conexión.

### 1.3 `core/events.py`
`DomainEvent` (`@dataclass(frozen=True, slots=True, kw_only=True)`, `occurred_at` del reloj). Los eventos se declaran en el `service.py` del emisor (ya existe `UserCreated`, `auth/service.py:46`). `subscribe(Tipo, handler)` es idempotente; `emit(event, session)` corre los handlers en orden con la misma sesión, propaga excepciones, límite de 5 niveles; nada corre después del commit (N-37); tipo exacto, sin herencia. El sprint agrega `LoginAttempted`, `UserLocked`, `SessionsRevoked` y los suscriptores de US-107.

### 1.4 `core/audit.py`
- Hook (`install_audit_listeners`, 497): `before_flush` pone `created_by = get_actor()` en objetos nuevos con `CommonColumnsMixin`; `after_flush` audita `__audited__ = True` (insert con `after`; update solo con columnas cambiadas y `before`/`after`; delete). El borrado lógico es un update.
- Atributos: `__audit_redact__` (el valor escrito es `***`, línea 70; la demo dice `<redacted>`: la prueba debe esperar `***`), `__audit_exclude__`, `__audit_subject__` (atributo con el socio; `"id"` en members).
- `record(session, *, action, table_name, record_id, before, after, user_id=None, subject_member_id=None)` (312). Acciones: `insert|update|delete|reveal|export|download|login|verify`. Con `user_id` explícito no necesita actor. `audit_log.user_id` es NOT NULL: sin persona usar `SYSTEM_USER_ID`. N-31: login con correo inexistente no se audita.
- Un `Encrypted` sin prefijo `apx1.` aborta el flush (`PlaintextInAuditError`); `float`, `Decimal` y `bytes` lanzan `CanonicalError`: COP en `int`, fechas con zona.
- Ya listos: `User.last_login_at` en `__audit_exclude__`; `User.password_hash` y `OneTimeToken.token_hash` en `__audit_redact__`.
- Modelos auditados sin columnas `deferred`; sesión con `expire_on_commit=False` (así la crea `get_sessionmaker`).

### 1.5 `core/context.py`
`SYSTEM_USER_ID` (36), `current_actor`, `get_actor()` (lanza `MissingActorError`), `actor_scope(user_id)` (60), `batch_scope`. Ver riesgo 2.

### 1.6 `core/pagination.py`
`PageParams` (dataclass con `Depends()`; limit 1..200, 25 por defecto; offset >= 0), `Page[T]` (`extra="forbid"`), `SearchQuery` (q <= 100), `paginate(session, select, params)` -> `(items, total)` con orden estable por PK, `to_page(items, total, params)`. `test_list_routes_use_page_params` recorre `router.routes` de `MODULES` y exige `PageParams` en todo GET con `response_model=Page[...]`; un GET de lista con otro tipo de respuesta elude la prueba sin avisar.

### 1.7 `core/errors.py`
Envelope `{"error": {code, message, field?, existing_id?}}`. Clases: `DomainError` (400 por defecto, `field`, `existing_id`), `UnauthorizedError` 401 (agrega `WWW-Authenticate: Bearer`), `ForbiddenError` 403, `NotFoundError` 404, `ConflictError` 409, `ValidationFailed` 422, `TooManyRequestsError(retry_after_s)` 429 con `Retry-After`. El 422 de Pydantic arma `field` desde `loc`. Los códigos del sprint (`invalid_token` 400, `version_conflict` 409, `section_not_available` 404, `email_taken` y `member_duplicate` 409 con `existing_id`, `invalid_refresh` 401) se crean subclasando `DomainError` en cada `exceptions.py` (hoy solo `AuthError` 422). `ERROR_RESPONSES` ya publica 400/401/403/404/409/422/429/500 en el OpenAPI.

### 1.8 `core/crypto`
- `types.py`: `Encrypted(data_class)` y `BlindIndexed(data_class, source=...)` son `TypeDecorator`. Se asigna `Secret.from_plain(valor)`; el `before_flush` (209) cifra con `aad = id` y llena el `_idx`. Un `_idx` cambiado a mano sin cambiar la fuente falla (`index_manual`); `id` inmutable en registros cifrados; valor `None` deja ambas columnas en NULL.
- `reveal(obj, campo, proposito)` (224): única lectura en claro; deja rastro en `crypto_ops`. Sirve a `test_reveal_entry` (S2-B6) y al enmascarado de Sprint 3.
- `Secret` no se serializa (Pydantic y JSON lanzan `TypeError`): los schemas de lista nunca incluyen columnas `Encrypted` (`test_list_rows_without_sensitive_fields`).
- `bus.blind_index(data_class, value)` (109): síncrona, requiere keyring cargado, normaliza por `index_kind` (`generic`, `phone`, `email`) y deja una fila `index` en `crypto_ops` por llamada. La búsqueda de S2-B8 debe usarla desde `members.service` (nunca `hmac`).
- `registry.py` ya trae las 5 clases `member.document|phone|email|birth_date|emergency_contact` con columnas `members.members.<campo>`; `birth_date` y `emergency_contact` sin índice; `emergency_contact` es `json` (se pasa un dict). Los nombres de columna del modelo deben coincidir con el registro.

### 1.9 `main.py`
- `MODULES = ("auth",)` (51). Cada módulo nuevo se agrega ahí; `test_audited_tables`, `test_list_routes_use_page_params` y `test_no_cross_models` iteran `MODULES` e importan `app.modules.<m>.models` y `.router`: cada módulo necesita ambos archivos.
- `load_module_services()` (73) importa `service.py` (donde se suscriben handlers).
- `include_module_routers()` (92) monta `mod.router` con `dependencies=[Depends(refresh_keyring)]` (95). `refresh_keyring` (79) depende de `get_session`: abre conexión y consulta `crypto_keys` antes de validar el token y antes del rate limit, también en login/refresh/forgot/reset (deuda M-3 "solo tras validar el token"). FastAPI cachea la dependencia, así que hay una sola sesión por petición. Opciones: dejarlo (una consulta por petición) o moverlo a las rutas autenticadas tras `current_user`.
- Un segundo `APIRouter(prefix="/users")` en `auth` NO se monta solo: `include_module_routers` importa solo `mod.router`; hay que hacer `router.include_router(users_router)` dentro de `auth/router.py`.
- `lifespan` (126): migraciones -> `check_secrets_or_exit` -> `configure_security` -> `configure_provider` -> exige `PrincipalLoader` -> `ensure_keys` (bajo `actor_scope(SYSTEM_USER_ID)`) -> pasos de `register_startup_step`. CORS cerrado y `allow_credentials=False` (irrelevante: mismo origen vía Nginx).

### 1.10 `modules/auth/*` (estado actual)
- `models.py`: `User` (auditado, soft delete, CHECKs, único parcial `uq_users_email_alive`), `RefreshToken` (no auditado, excluido en `test_audited_tables.EXCLUIDAS`), `OneTimeToken` (auditado; `purpose` activate|reset). No existen `display_name`, contador de intentos ni `must_change_password`.
- `service.py`: puras `validate_user_role`, `normalize_login_email`, `user_status` (`deleted > locked > inactive > active`), `is_active_admin`, `validate_password_policy(password, current_hash=...)`; casos `seed_admin`, `load_active_principal`; lecturas `names_for`, `ids_by_email`, `active_admin_id_by_email`; evento `UserCreated`.
- `router.py`: `APIRouter(prefix="/auth", tags=["auth"])` vacío. `schemas.py`: `Role`, `UserStatus`, `UserOut`. `exceptions.py`: `AuthError` (422).
- `0004_auth` ya está aplicada: no editarla; toda columna nueva exige migración nueva.

### 1.11 `cli.py`
`unit_of_work(actor_id)` (34), `resolve_actor(session, email)` (42), `seed` (272) con `_seed` (223): instala los tres listeners, configura argon2, `db.configure_engine` y ejecuta `seed_admin` dentro de `unit_of_work(actor)`. Es el patrón para comandos nuevos. `cli.py` y `worker/` están fuera de cobertura (`api/pyproject.toml:87`, hasta US-113).

### 1.12 `core/logging.py`
`SENSITIVE_KEYS` cubre `password, password_hash, token, refresh_token, access_token, authorization, cookie, document, phone, email, birth_date, emergency_contact`. No cubre `activation_url`, `new_password`, `current_password` ni `q`: si un `extra=` los usa quedan en claro (por forma solo se redactan blobs `apx1.` y JWT). `RequestLogMiddleware` (146) loguea método, `path_format` (`/users/{id}`), status y duración; no query, cuerpo ni cabeceras.

## 2. Cómo se prueban hoy

### 2.1 Fixtures
`api/tests/conftest.py`:
- Instala los tres listeners al importarse (41-43) y registra `principal_double` (46).
- `test_database_url` (session; falla si falta `TEST_DATABASE_URL`), `claves_prueba` (session; `init_keys_files` en tmp), `settings_prueba(tmp_path, migrated_database, claves_prueba)` (escribe un `.env` temporal con `ENV=dev` y CORS de localhost; `COOKIE_SECURE` y `FRONT_BASE_URL` quedan en el default), `alembic_config`, `migrated_database` (session: `upgrade head` y limpia `crypto_keys`, `crypto_ops` y `audit_log` con triggers apagados; NO limpia `auth.users`), `engine` (por prueba), `session` (conexión + transacción externa + savepoint; se revierte todo).
- `tests/crypto/conftest.py`: `proveedor_local`, `sin_llaves` (vacía `crypto_keys` en el savepoint y `configure_keyring(None)`), `bus_listo` (`ensure_keys` bajo `actor_scope(SYSTEM_USER_ID)`, devuelve el keyring, limpia al final). Viven en `tests/crypto/`: NO se ven desde `tests/members`; hay que subirlos a `tests/conftest.py` o crear `tests/members/conftest.py`.
- `tests/core/_principal_double.py`: `principal_double.usuarios[UUID] = Principal(...)`, `llamadas`, `reset()`.
- Trampa de registro: `create_app` importa `auth.service`, que registra el cargador real solo la PRIMERA vez que se importa. En una corrida completa `tests/auth/test_principal_loader.py` ya lo importó y el real pisó al doble; `test_require_role.py:148` re-registra el doble por eso. Los tests de routers de auth deben registrar `load_active_principal` explícitamente y restaurar el doble al terminar.

### 2.2 Patrones de prueba de router
- `tests/core/test_require_role.py`: `create_app(settings_prueba, run_migrations_on_startup=False)`, router extra con `app.include_router(router, prefix=API_PREFIX)` (`tests/core/_routes.py`), `set_clock(FrozenClock(T0))`, lifespan con `app.router.lifespan_context(app)` (crea llaves con commit real y usa el engine real, no el savepoint), `AsyncClient` con `ASGITransport(app=app)`, token con `create_access_token(user_id, role, member_id, FrozenClock(...))`.
- `tests/core/test_pagination_router.py`: `FastAPI()` mínima + `register_error_handlers`, sin base.
- `tests/core/test_audit_actor_http.py`: `configure_sessionmaker(async_sessionmaker(engine, ...))` y dependencias dobles; crea y borra tablas de prueba en el esquema `worker`.
- `tests/core/test_ratelimit.py` (84-115): `reset_store()` al inicio y al final; `ASGITransport(app=app, client=(ip, 1234))`.

### 2.3 Fixtures que faltan para routers autenticados de verdad
No existe ninguna con token real y usuario real en `auth.users`. Propuesta (en `api/tests/conftest.py` o un `api/tests/api_fixtures.py` importado desde ahí; fábrica de usuarios en `api/tests/factories/users.py`, junto a la de socios que ya pide el sprint):
1. `restore_bus` (autouse): guarda una copia de `events._subscribers` y la restaura después de cada prueba (riesgo 5).
2. `fresh_rate_limit` (autouse): `reset_store()` antes y después (riesgo 6).
3. `real_loader`: `register_principal_loader(load_active_principal)` y al terminar `register_principal_loader(principal_double)`.
4. `make_user` (fábrica async): recibe `role`, `email` (por defecto un uuid corto con dominio `@test.apex`), `password` y `member_id`; crea `User` con `password_hash` de `hash_password(...)` (requiere `configure_security(settings_prueba)`), `created_by=SYSTEM_USER_ID`, bajo `actor_scope(SYSTEM_USER_ID)`, y hace `flush()`. Devuelve un dataclass `TestUser(id, email, password, role, member_id)`.
5. `auth_headers(user)`: cabecera `Authorization: Bearer <create_access_token(user.id, user.role, user.member_id, get_clock())>`.
6. Dos clientes:
   - **`api_client` (rápido, preferido):** `create_app(settings_prueba, run_migrations_on_startup=False)` SIN lifespan; `app.dependency_overrides[get_session]` devuelve la fixture `session` (savepoint); `bus_listo` aporta el keyring; `configure_security(settings_prueba)` aporta JWT y argon2; `set_clock(FrozenClock(T0))`. `refresh_keyring` también usa `get_session`, así que el override lo cubre. Todo se revierte solo. Límite: no hay commit real, así que no cubre el commit del teardown, `crypto_ops` (se escribe en `before_commit`) ni concurrencia entre peticiones.
   - **`live_client` (commit real):** como `test_require_role` (lifespan y engine reales). Para refresh con rotación concurrente, rollback ante 401, cadena de auditoría y `crypto_ops`. Correos únicos por prueba y limpieza con `DELETE` de `auth.one_time_tokens`, `auth.refresh_tokens` y `auth.users` del dominio `@test.apex` (los triggers protegen `audit_log`, no estas tablas; `test_no_physical_delete_users` solo vigila `src/`).
7. Cookies: `httpx.AsyncClient` conserva cookies; con `COOKIE_SECURE=false` y base_url http la cookie `apex_refresh` (`Path=/api/v1/auth`) se reenvía en `POST /api/v1/auth/refresh`. Los atributos se verifican leyendo la cabecera `set-cookie` de la respuesta.
8. Las pruebas `test_pure_*` no necesitan nada de esto.

## 3. Front

### 3.1 Estado
`web/src` solo tiene el kit (US-040, US-059 a US-066) y un `App.tsx` mínimo (h1 "APEX"). No existen `routes.tsx`, `session.ts`, `layouts/` (solo `.gitkeep`), `features/` (solo `.gitkeep`), `TopBar`, `SideNav`, `QueryClientProvider`, `RouterProvider` ni tema. `main.tsx` monta `<StrictMode><App/></StrictMode>` e importa `fonts.css` y `tokens.css`.
Pruebas que se rompen al reemplazar `App.tsx`: `src/App.test.tsx` (espera h1 "APEX") y `tests/e2e/smoke.spec.ts` (h1 "APEX" y el texto "Año, Bogotá, ÑANDÚ").

### 3.2 `web/src/core/api/client.ts`
- `API_BASE = "/api/v1"`, `REQUEST_TIMEOUT_MS = 15000`. `api.get|post|put|patch|delete<T>(path, options)` con `RequestOptions { query?, body?, signal?, skipAuthRetry? }`.
- Los ganchos se llaman `setAccessTokenGetter(getter | null)` (línea 36) y `registerOnUnauthorized(handler | null)` (41); el handler es `UnauthorizedHandler = (error: ApiError) => Promise<"retry" | "fail">`. No existe un símbolo `onUnauthorized`.
- `credentials: "same-origin"` (109): basta para la cookie del refresh (`Path=/api/v1/auth`, mismo origen vía Nginx). No usar `"include"`.
- El 401 invoca el gancho solo si `!retried && !skipAuthRetry` y repite una vez si responde `"retry"`. `login`, `refresh` y `logout` deben pasar `skipAuthRetry: true`. El gancho debe decidir por `error.code === "token_expired"` (el `unauthorized` genérico no dispara refresh).
- Un 204 devuelve `undefined`; un cuerpo no JSON en éxito se vuelve `network_error`.
- `errors.ts`: `ApiError { status, code, message, field, existingId }`, `parseApiError` (valida el envelope con Zod y degrada a `network_error`, p. ej. ante un 502 de Nginx), `isApiError`, `GENERIC_MESSAGES`.
- `page.ts`: `Page<T>` y `pageSchema(item)` a mano (DESIGN-GAP: `docs/openapi.json` aún no tiene esquemas de lista; al regenerar `types.ts` con las listas del sprint, comparar y retirar el gap). `query.ts`: `toQueryString`, `listParams({limit, offset, ...filtros})`, `clampLimit`, `MAX_LIMIT`, `DEFAULT_LIMIT`.

### 3.3 `web/src/core/auth/`
- `permissions.ts`: `ROLES`, `Role`, `can(role, action)` (niega por defecto), `MATRIX`, `ACTIONS`. Acciones del sprint: `users.manage` y `settings.manage` (admin); `plans.view` y `plans.manage` (admin, ver 6.9); `members.view|create|update|reveal` (STAFF); `account.manage` (STAFF, aunque `/auth/me/password` lo permite a los 3 roles); `dashboard.view`. Este archivo y `session.ts` son los únicos donde un rol se compara con un literal.
- `useCan.ts`: `RoleContext`, `RoleProvider` (= `RoleContext.Provider`), `useRole()`, `useCan(action)`. El comentario dice que US-053 lo conecta a `session.ts` sin cambiar la firma: el `RoleProvider` debe montarse en `main.tsx` o `App.tsx` con el rol de `GET /auth/me`.
- `Can.tsx`: `<Can action fallback>{children}</Can>`. `index.ts` re-exporta todo.
- Falta: `session.ts` (token en memoria, `BroadcastChannel("apex-auth")`, Web Locks para un refresh compartido), `RequireRole`, `homeFor(role)`, `isRouteEnabled`.

### 3.4 `web/src/shared/ui` (todo exportado por `shared/ui/index.ts`) y `shared/hooks`
| Componente | Props clave |
|---|---|
| `Button` | `variant: primary / secondary / danger / ghost`, `size: md / lg`, `loading`, atributos de `<button>` |
| `Field` (forwardRef) | `label`, `name`, `hint`, `error`, `errorAction {href, text}` (para el 409 con enlace al socio existente), `required`, `size`, `children(control)` para select o textarea; atributos de `<input>` |
| `StatusTag` | `status: MembershipStatusView` (active, expiring, expired, frozen, cancelled, pending_payment, none) |
| `PageHeader` | `title`, `total`, `badge`, `description`, `breadcrumbs[]`, `actions[]` (`id,label,href,onClick,variant,tone,disabled`) |
| `Tabs` | `label`, `tabs[] {id,label,disabledUntil}`, `urlMode: query / segment`, `param`, `basePath`, `children(activeId)` |
| `KpiCard` | `label,value,kind: money / count,availableIn,note,delta,href,attention,isLoading,error,onRetry` |
| `SidePanel` | `open,title,isDirty,onClose,footer,cancelLabel,children` |
| `ConfirmModal` | `open,title,consequence,confirmLabel,tone,cancelLabel,reasonRequired,showReason,reasonLabel,minReasonLength,confirmText,onConfirm(reason),onClose` |
| `DataTable<T>` | `caption,columns[] {key,header,render,sortable,align},rows,total,limit,rowKey,rowHref,isLoading,error,onRetry,emptyMessage,emptyAction,sort,onSortChange` (la primera columna enlaza; `rowHref` es obligatorio) |
| `Pagination` | `total,limit,offset,onPageChange(page),onLimitChange` (25/50/100) |
| `FilterBar` | `query,onQueryChange,onClear,searchLabel,searchPlaceholder,selects[],onSelectChange,dateRange,sort` (debounce de 300 ms interno) |
| `Chips` | `label,mode,options[] {value,label,count,tone},value,onChange` |
| `MaskedValue` | `label,masked,onReveal(),revealAction="members.reveal",kind,documentType` |
| `HistoryAside` | `entries,total,onLoadMore,isLoading,error,onRetry,title` |

Hooks: `useDebouncedValue(value, ms)`, `useFocusTrap(active, options)`, `useListParams({filters, sorts})` (q, limit, offset, sort y filtros en la URL con `useSearchParams` de `react-router`), `useMediaQuery(query)` y `MOBILE_QUERY`. Libs: `lib/pagination.ts`, `lib/audit-labels.ts`.
Faltan `TopBar`, `SideNav` (S2-F1), el conmutador de tema y `LinkModal`. Los tests de inventario del kit (`shared/ui/index.test.ts`, `tests/kit-inventory.test.ts` de S2-F8) deben incluir los nuevos.
Dependencias instaladas: `react-router` 7 (importar de `react-router`, no de `react-router-dom`), `@tanstack/react-query` 5, `react-hook-form`, `zod` 3, `lucide-react`, `vitest-axe`. No hay `@axe-core/playwright`: "axe sobre todo el kit" se cubre con `vitest-axe` (ya en `setup.ts`) o agregando el paquete (licencia MPL-2.0, aceptada sin modificar según CLAUDE.md).

### 3.5 `web/src/core/i18n/format.ts`
`formatCop`, `formatCount`, `parseCop`, `formatDate`, `formatDateTime`, `formatTime`, `formatMonth`, `todayBogota`, `EMPTY_VALUE`. Es el único lugar permitido para `Intl` y `toLocale*`. El TopBar usa `formatDateTime` o `formatTime` para la hora de Bogotá. `config/locale.ts`: `LOCALE="es-CO"`, `TZ_DISPLAY`.

### 3.6 Reglas que Vitest aplica a `src/` (`web/tests/lint/restricted-config.ts`)
`no-console`; `fetch` solo en `src/core/api/**`; `Intl` y `toLocale*` solo en `src/core/i18n/**`; ningún literal de rol (`=== "admin"`, `switch(role)`, `case "coach"`) fuera de `core/auth/permissions.ts` y `core/auth/session.ts`. Además `eslint.config.js` (strictTypeChecked) prohíbe hex, rgb, hsl y `fontFamily` en `style=`; `stylelint` sobre `src/**/*.css`. `tsconfig`: `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes` (los props opcionales no admiten `undefined` explícito). Cobertura mínima de 80 %, con umbral propio para `src/shared/ui/**`.
Consecuencia: `RequireRole` y `homeFor` no pueden hacer `if (role === "member")` fuera de `session.ts` y `permissions.ts`; usar `can(role, "me.home.view")` o una función exportada desde `permissions.ts`.

### 3.7 Vite, Playwright, Nginx y CSP
- `web/vite.config.ts` NO tiene `server.proxy`. `npm run dev` y `vite preview` (puerto 4173, el de Playwright) no reenvían `/api`. Para dev, agregar `server.proxy` de `/api` hacia `http://127.0.0.1:<API_PORT>` (8181 en esta máquina). Para los E2E contra el stack (S2-W0-1), `playwright.config.ts` fija `baseURL` en `http://localhost:4173` y levanta su propio `webServer`: parametrizarlo con una variable tipo `E2E_BASE_URL`, omitiendo `webServer` cuando exista (precedente: `CSP_BASE_URL` en `tests/e2e/csp.spec.ts`). Aquí el stack está en `http://localhost:8180`.
- `html.cspNonce = "__CSP_NONCE__"` y `modulePreload.polyfill = false`. La CSP de `/index.html` es: default-src self; script-src self + nonce por petición; style-src self; img-src self y data; font-src self; connect-src self. Implicaciones: no hay script en línea para fijar el tema antes de pintar (hacerlo con un import temprano en `main.tsx` que ponga `document.documentElement.dataset.theme`); no hay `<style>` en línea.
- Tema: `tokens.css` ya define el modo oscuro por `prefers-color-scheme` (salvo `data-theme="light"`) y por `:root[data-theme="dark"]`. Panel: claro por defecto con preferencia guardada (localStorage); check-in, resultados y TV fijan `data-theme="dark"` en su ruta; el portal sigue al sistema.

### 3.8 Pantallas del Sprint 2 (`docs/design/screens/<Clave>.html` y `<Clave>.dark.html`, salvo TV)
| Zona y ruta | Archivo | Rol | Endpoints |
|---|---|---|---|
| Login `/login`, `/recuperar`, `/restablecer/:token` (3 tarjetas en un archivo) | `Login.html` | sin sesión | POST `/auth/login`, `/auth/forgot`, `/auth/reset` |
| Layout del panel (TopBar + SideNav de 232 px; en celular, cajón) | `Inicio.html` como referencia de layout (la pantalla Inicio llega en Sprint 3) | admin, coach | GET `/auth/me` (gym_name) |
| Layout del portal (columna de 600 px, menú inferior de 5 pestañas) | `Portal_Inicio.html` (390x844; también `Portal_*`) | member | solo layout |
| Layout gym (oscuro, tablet 1024x768) | `CheckIn.html`, `Resultados_Registro.html` | staff | solo layout |
| Layout TV (oscuro, 1920x1080) | `TV.html` (sin variante dark) | token | solo layout |
| `/sistema/usuarios` | `Usuarios.html` | admin | GET y POST `/users`; PATCH y DELETE `/users/{id}`; lock, unlock, resend-link, revoke-sessions |
| `/sistema/configuracion` | `Config.html` (8 secciones en el diseño; 3 en el sprint: Gimnasio, Membresías, Datos personales) | admin | GET y PATCH `/settings/{section}` |
| `/socios` | `Socios_Lista.html` (celular: `Socios_Movil.html`) | staff | GET `/members?q&limit&offset` |
| `/socios/nuevo` | `Socio_Form.html` (sin foto ni adjuntos en v0.1) | staff | POST `/members` |
| `/planes` | `Planes.html` | admin | GET y POST `/plans` |
| Patrones | `P_Lista.html`, `P_Formulario.html`, `P_Ficha.html` | | |

Observaciones de diseño frente al sprint:
- `Login.html` muestra "[NOMBRE DEL GIMNASIO]", pero `gym_name` solo llega por `GET /auth/me` (autenticado): en el login usar "APEX" y marcar `// DESIGN-GAP:`.
- `Usuarios.html` tiene "Nombre *" y la lista muestra nombres; `auth.users` no tiene nombre (6.9).
- `Socio_Form.html` incluye sexo, tipo de documento (CC, CE, TI, Pasaporte), unidad de carga, contacto de emergencia con parentesco, observaciones de salud, autorización Ley 1581 y acceso al portal. El sprint solo especifica documento, teléfono y correo cifrados; qué campos entran a `0006_members` debe salir de `docs/ddd/08_implementation_breakdown/EP-07-padron-de-socios/` (no se leyó aquí).
- `Planes.html` tiene tipo de duración "por clases" o "por días" y casilla "Activo".
- `Config.html` muestra 8 secciones; las otras 5 deben quedar como "Próximamente" (`Tabs.disabledUntil`) con `// DESIGN-GAP:`.
- Reglas de `DESIGN.md` que más pesan: tokens solo de `tokens.css`; controles de 44 px; listas paginadas en el servidor; dinero `$ 120.000`; fechas `20 oct 2026` en hora de Bogotá; el duplicado se muestra en `Field` con `errorAction` hacia el socio existente; "Sistema" solo para admin; logos `web/public/brand/apex-logo-dark-bg.png` y `apex-logo-light-bg.png` según tema.

## 4. Entorno de ejecución

### 4.1 Servicios (`infra/compose.yml` + `infra/compose.dev.yml`)
Comando base: `docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml <cmd>`.

| Servicio | Cómo llega el código | Qué hacer al cambiar |
|---|---|---|
| `api` (imagen `apex-api:local`; en dev `uvicorn --reload --reload-dir /app/src`, polling, puerto `127.0.0.1:${API_PORT}`) | **Bind mount** de `../api/src` -> `/app/src` y `../api/migrations` -> `/app/migrations`. El resto (`pyproject.toml`, `uv.lock`, `alembic.ini`, `Dockerfile`) es COPY. | Cambios en `src/`: recarga sola. **Una migración nueva NO dispara recarga** (`migrations/` no está en `--reload-dir`): `restart api` o tocar un `.py` de `src`; el lifespan corre `alembic upgrade head`. Cambios en `pyproject.toml`, `uv.lock`, `alembic.ini` o `Dockerfile`: `up -d --build api`. |
| `tools` (profile `tools`, entrypoint `python -m app.cli`, único con escritura sobre el volumen `keys`) | **COPY** de la imagen (la capa dev solo monta `src` en `api`) | Si cambia `cli.py` o código que usa el comando: `build api` y luego `run --rm tools <cmd>`. |
| `worker` (profile `worker`) | COPY; `app/worker/main.py` no existe aún | no se levanta |
| `web` (build con contexto en la raíz: `npm ci`, `npm run build`, Nginx) | **COPY** del build estático y de `infra/nginx/*` | **Todo cambio de front o de Nginx exige** `up -d --build web` (la capa `npm ci` se cachea mientras no cambie `package*.json`). Para iterar, `npm run dev` con proxy (3.7). |
| `db` (`postgres:16`, volumen `pgdata`) | | dev publica `127.0.0.1:${DB_PORT}` |
| `db_test` (solo dev, **tmpfs**: los datos se pierden al reiniciar el contenedor) | | `migrated_database` re-aplica `upgrade head` en cada corrida de pytest |

Volúmenes: `pgdata`, `uploads`, `keys` (el api lo monta de solo lectura), `backups`. El servicio `api` carga todo `.env` con `env_file`, incluido `ADMIN_INITIAL_PASSWORD` (deuda M-8).
Nginx (`infra/nginx/default.conf`): sirve el build; `/api/` va a `api:8000` con `snippets/proxy-api.conf` (`X-Forwarded-For $remote_addr`, `X-Request-ID`, `proxy_read_timeout 60s`); CSP con nonce solo en `/index.html`; cabeceras de seguridad en cada location. El `log_format apex` registra `$uri`, no la query; tras el `try_files ... /index.html` de una ruta SPA el `$uri` ya es `/index.html`, así que el token de `/restablecer/<token>` NO queda en el access log. La tarea de S2-W0-1 "dejar de registrar query strings de `/restablecer/` y de `q`" ya se cumple de hecho por el formato; falta una prueba que lo demuestre (extender `scripts/ci/test_nginx_conf.sh`). Pendientes reales: (a) `Referrer-Policy: strict-origin-when-cross-origin` envía la URL completa con el token como `Referer` en las peticiones del mismo origen desde la página de activación: limpiar la URL con `history.replaceState` al montar o usar `no-referrer` en esa ruta; (b) falta `Cache-Control: no-store` en `/api/` (deuda L-1) y las respuestas de login y refresh llevan el access token.

### 4.2 Estado actual (consultado sin modificar nada)
`ps` (2026-10-22 UTC):
- `apex-api-1`: Up 46 min, healthy, `127.0.0.1:8181->8000`.
- `apex-db-1`: Up 51 min, healthy, `127.0.0.1:5442->5432`.
- `apex-db_test-1`: Up 11 h, healthy, `127.0.0.1:5443->5432`.
- `apex-web-1`: Up 46 min, healthy, `0.0.0.0:8180->80`.

`logs --tail=20 api`: solo `http_request` de `GET /health` 200 cada 10 s (1,6 a 3 ms), sin errores ni avisos.
Los puertos del `.env` local difieren del `.env.example` (8180, 8181, 5442, 5443); el stack real está en `http://localhost:8180`. `TEST_DATABASE_URL` del `.env` apunta al puerto 5443 (coincide con `DB_TEST_PORT`).

## 5. Bugs de configuración que afectan al sprint

| # | Archivo | Hallazgo | Acción |
|---|---|---|---|
| C1 | `api/pyproject.toml:77-80` | Solo existe el marcador `db`; `addopts` lleva `--strict-markers`. `-m perf` (S2-B8) falla al coleccionar. | Registrar `perf` y decidir si el gate normal lo excluye (`-m "not perf"`). |
| C2 | `.env` local (variables `FRONT_BASE_URL`, `WEB_PORT`) | `FRONT_BASE_URL=http://localhost` con `WEB_PORT` distinto de 80: el `activation_url` de US-047 apunta al puerto equivocado (afecta la demo y `users-activation.spec.ts`). | Alinear `FRONT_BASE_URL` con `WEB_PORT` en el `.env` local; documentar la relación en `.env.example`. |
| C3 | `.env.example` (bloque CORS) | `CORS_ORIGINS` tiene dos comentarios contradictorios ("lista JSON" y "separados por coma"). `Settings` lo declara `NoDecode` (formato coma). | Dejar un solo comentario coherente con `core/config.py:126` y con `tests/core/test_env_example.py`. |
| C4 | `.env` local | Faltan `APP_VERSION`, `ARGON2_*`, `PASSWORD_MIN_LENGTH`, `ACCESS_TOKEN_TTL_S`, `REFRESH_TOKEN_TTL_DAYS`, `JWT_LEEWAY_S` (están en `.env.example`). | Informativo: tienen default en `Settings`. Ojo: el default de `ENV` es `production`. |
| C5 | `.env.example`, `compose.yml` | `ADMIN_*` entra al `api` por `env_file` (M-8). | Moverlo al `environment` de `tools` o borrarlo del `.env` tras el seed; decide el dueño de M-8 (este sprint). |
| C6 | `.env`, `.env.example` | `TRUSTED_PROXIES=172.16.0.0/12`: cualquier contenedor de la red de Docker puede falsear la IP, y el límite de login depende de ella (M-1 resto). | Subred fija e IP del proxy en `compose.yml`; `TRUSTED_PROXIES` solo esa IP. |
| C7 | `api/pyproject.toml:87` | `omit = ["*/app/cli.py", "*/app/worker/*"]` hasta el Sprint 3. | Correcto para el sprint; no tocar. La DoD pide el `--cov-omit` documentado: ya lo está. |
| C8 | `web/vite.config.ts`, `web/playwright.config.ts` | Sin proxy `/api` y `baseURL` fijo en 4173. | Ver 3.7. |
| C9 | `web/package.json` | Sin script de E2E contra el stack ni `@axe-core/playwright`; `gen:api` y `generate:api` ya existen. | Agregar script (p. ej. `e2e:stack`); decidir axe (3.4). |
| C10 | `.github/workflows/ci.yml:142-150` | El Playwright de CI corre `npm run e2e` contra `vite preview`. | S2-W0-1 define el job contra `infra/compose.yml --build`. |
| C11 | `api/migrations/versions/0004_auth.py` | Ids con prefijo numérico y slug; redefine `common_columns` localmente (no usa `migrations/helpers.py`). | `0005_settings`, `0006_members`, `0007_plans` con `down_revision` encadenado (`"0004_auth"`, ...); el esquema lo crea 0001 (`APP_SCHEMAS` ya incluye `settings`, `members`, `plans`). Respetar el lock de `migrations/env.py`. |

## 6. Riesgos de integración concretos

### 6.1 Cookie del refresh y `credentials`
Contrato (US-042 T6): cookie `apex_refresh`, `HttpOnly`, `SameSite=Strict`, `Path=/api/v1/auth`, `Max-Age=604800`, `Secure` si `COOKIE_SECURE`. El cliente ya usa `same-origin`. Riesgos:
- `Path=/api/v1/auth` hace que solo `login`, `refresh`, `logout` y `reset` vean la cookie; `/auth/me` no la necesita (usa Bearer). Correcto.
- Con `npm run dev` y el proxy de Vite el origen del navegador es el de Vite y el proxy conserva la cookie; sin proxy la cookie no llega al api.
- Con otro origen para el front, `allow_credentials=False` lo impediría: fuera de alcance en v0.1.
- Borrar la cookie exige los mismos `Path` y atributos (`clear_refresh_cookie`).
- En pruebas: `Secure` solo con `COOKIE_SECURE=true`; con base_url http el cliente no la reenviaría.
- Las respuestas con tokens necesitan `Cache-Control: no-store` (L-1).

### 6.2 `refresh_keyring` en todos los routers (M-3)
Ver 1.9. Efecto: login, refresh, forgot y reset abren sesión y consultan la base antes del rate limit y antes de validar nada; un 429 cuesta una conexión del pool; con la base caída esas rutas dan 500 (`/health` no, por diseño). Decisión pendiente del dueño de M-3 en este sprint, antes de abrir el login.

### 6.3 `principal_double` frente al cargador real
Ver 2.1. Los tests de `tests/core` que usan el doble siguen válidos. Para routers de auth hay que usar el real y restaurar el doble al terminar. El doble ignora `locked_at` e `is_active`, así que las pruebas de bloqueo (US-050: bloquear implica 401 inmediato) y de baja DEBEN usar el cargador real. `load_active_principal` ya filtra `locked_at`, `is_active`, `deleted_at` y `password_hash` nulo: no necesita cambios.

### 6.4 `PUBLIC_ROUTES` y `test_every_route_has_role`
`test_la_lista_blanca_es_la_esperada` fija el conjunto exacto de 7 rutas. Una ruta pública nueva (p. ej. un `/auth/activate`) exige cambiar `PUBLIC_ROUTES` y esa prueba a la vez; con el diseño actual (activar = `/auth/reset`) no cambia. Cada ruta nueva de `settings`, `members`, `plans`, `users` y `/auth/{logout,me,me/password}` debe llevar `require_role(...)` en la firma o en `dependencies=[...]` (también sirve a nivel de router: la prueba recorre el árbol de dependencias). `test_login_y_forgot_llevan_limite_de_intentos` exige `rate_limit` en `POST /auth/login` y `/auth/forgot` (conviene ponerlo también en `reset`).

### 6.5 `test_audited_tables`
Toda tabla nueva (`settings.*`, `members.members`, `plans.plans` y las que agregue `0005`) debe declarar `__audited__ = True` o entrar a `EXCLUIDAS` con motivo. El sprint amplía el test (US-107). `RefreshToken` ya está excluida. `settings` debe auditarse ("cada sección se guarda por separado y queda en auditoría"). `members.members` lleva `__audit_subject__ = "id"`.

### 6.6 `test_no_cross_models`
Prohíbe importar `models` y `router` de otro módulo (también `members` <-> `plans`). `settings` expone `memberships_policy()` y `current_privacy_version()`: otros módulos las llaman vía `settings.service`. El import perezoso solo vale para la lista blanca de `tests/architecture/test_service_import_graph.py`, que NO existe aún en el repo (CLAUDE.md lo cita). Los pares `members` <-> `memberships` y `plans` <-> `memberships` llegan en Sprint 3.

### 6.7 `test_list_routes_use_page_params`
Aplica a `GET /users`, `GET /members` y `GET /plans`: declarar `response_model=Page[...]` y `params: Annotated[PageParams, Depends()]`. `GET /plans` del coach (solo `active=true`) también la necesita.

### 6.8 `docs/openapi.json` y `web/src/core/api/types.ts`
`docs/openapi.json` (8 KB) hoy solo tiene `/health`. La CI falla si `git diff --exit-code docs/openapi.json` tras el export (`.github/workflows/ci.yml:64-68`), y `web/src/core/api/types.contract.test.ts` falla si `types.ts` no coincide con `openapi-typescript` sobre el JSON. Orden en cada slice backend que cambie rutas: (1) `cd api && uv run python -m app.cli export-openapi ../docs/openapi.json`; (2) `cd web && npm run gen:api`; (3) `npx vitest run src/core/api/types.contract.test.ts`. El export usa `export_settings()` (sin `.env`), es determinista y no corre migraciones: los routers nuevos solo necesitan estar en `MODULES`. Al regenerar, comparar `Page<T>` manual con el esquema generado.

### 6.9 Contradicciones y decisiones abiertas
1. **Nombre del usuario.** `Usuarios.html` pide "Nombre *" y la lista muestra nombres. `docs/ddd/DECISIONES.md:174` dice "se agrega `auth.users.display_name`" (US-110), pero `0004_auth` no lo tiene y US-047 solo recibe `email`, `role`, `member_id`. Opciones: (a) migración propia de auth (no editar 0004; SPRINT-02 solo lista 0005 a 0007, habría que renumerar o añadir 0008); (b) mostrar el correo y marcar `// DESIGN-GAP:`.
2. **Ruta de cambio de contraseña.** SPRINT-02: `POST /api/v1/auth/me/password`; `docs/design/ROUTES.md` (portal): `POST /me/password` y `GET/PATCH /me`. Fijar `/auth/me/password` para v0.1 y anotarlo en `docs/BRECHAS.md` o `DECISIONES.md`.
3. **Planes para el coach.** `ROUTES.md`: "Coach no ve Planes"; matriz del front: `plans.view` solo admin; SPRINT-02: `GET /plans` y `GET /plans/{id}` para admin y coach con `active=true`. El Sprint 3 (vender) necesita que el coach liste planes: alinear la matriz con una acción para STAFF.
4. **`activate`.** SPRINT-02 B4 habla de "forgot, reset y activate" pero lista 4 endpoints públicos; el diseño usa una pantalla para ambos. Un solo `POST /auth/reset`; el token lleva su `purpose`.
5. **Rama.** SPRINT-02 dice `feat/sprint-02-identidad-socios-planes`; la real es `feat/sprint-02-identidad-config-socios-planes`. Sin impacto técnico.
6. **Revocación de sesiones.** `RefreshToken` no se audita; la huella de "cambiar contraseña revoca las demás" y "cerrar sesiones" la deja el evento `SessionsRevoked` (S2-B6) vía `audit.record`.
7. **Bloqueo por cuenta (M-2).** `locked_at` existe; no hay contador de intentos por cuenta. Implementarlo exige almacenamiento (memoria como el rate limit, o columna con migración) y que el 401 no pierda la escritura (riesgo 1).
8. **`last_login_at`** está en `__audit_exclude__` (no genera `update`); la demo pide filas `login`: `audit.record(action="login", user_id=user.id)`.
9. **`test_no_sensitive_in_logs`**: ver riesgo 4.

### 6.10 Orden y enganches para el blueprint
- Orden del sprint: W0-1, luego B1 a B9, luego F1 a F8. Dependencias duras: B7 antes de B8; F1 y F2 antes de cualquier página; F3 (sesión) antes de F4a.
- Antes de B2: fixtures de 2.3, marcador `perf` (C1) y decisión de M-3.
- Antes de B7: decidir `test_no_sensitive_in_logs` (riesgo 4) y subir `bus_listo` a un conftest visible para `tests/members`.
- El módulo `audit` (S2-B6, suscriptores) no tiene `models.py` y no está en `MODULES`: `load_module_services()` solo importa los de `MODULES`. Para que `audit.service` se importe hay que agregar `"audit"` a `MODULES`; entonces `test_audited_tables` buscará `app.modules.audit.models` e `include_module_routers` importará `audit.router`. O se crean ambos archivos (vacíos), o se ajustan `load_module_services` y las pruebas. Decisión de diseño a cerrar en el blueprint (CLAUDE.md dice que los models de audit viven en `core/audit.py`).
- Cada slice backend con rutas nuevas: `export-openapi` + `gen:api` + `types.contract.test.ts` en el mismo slice.
- Cada slice de front: `up -d --build web` antes de cualquier E2E contra el stack.
- `up -d --build api` si cambia `pyproject.toml` o `uv.lock` (nuevas dependencias); migraciones nuevas: `restart api`.
