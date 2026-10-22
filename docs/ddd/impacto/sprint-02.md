# Análisis de impacto previo · Sprint 2 (identidad, configuración, shell del front, socios y planes)

Fecha: 21 de octubre de 2026 (noche; línea base corrida el 22 a las 22:07 hora local).
Alcance: `update` sobre un repositorio con código (`flow-update`, Fase 0).
Anclaje: rama `feat/sprint-02-identidad-config-socios-planes`, HEAD `482295f`
("cierre del Sprint 1"). `git status` limpio. El nombre de la rama difiere del que escribe
`SPRINT-02.md` (`feat/sprint-02-identidad-socios-planes`): es solo nomenclatura, no bloquea.
Plan de referencia: `docs/ddd/09_sprint_plan/SPRINT-02.md` (26 historias, 29 endpoints,
migraciones `0005_settings`, `0006_members` y `0007_plans`, 9 slices de backend y 9 de front).

## Veredicto: AMARILLO

Se puede avanzar a la Fase 1 con `--allow-amber`. Nada es ROJO: no hay datos reales, las
migraciones `0001` a `0004` solo están aplicadas en bases locales, la suite completa está en
verde y el stack de desarrollo está arriba. El amarillo viene de ocho condiciones concretas
(sección 8) que, si no se absorben en el plan, rompen un gate a mitad del sprint o dejan la
demo sin cumplir: una prueba de arquitectura que pasa de "saltada" a "roja" en cuanto exista
`members/router.py`, dos pruebas de arquitectura que exigen `models.py` y `router.py` en cada
módulo de `MODULES` (el módulo `audit` del Sprint 2 no trae ninguno de los dos), `FRONT_BASE_URL`
sin puerto en el `.env` local (los enlaces de activación apuntarían a otro proyecto), tres
tareas DevOps de los desgloses que nombran pasos o jobs de CI que no existen, y la deuda
M-1 a M-8 del Sprint 1 que tiene que entrar antes de abrir el login.

## Cómo se verificó

- Lectura completa de `SPRINT-02.md`, `CLAUDE.md`, `00b_impact_analysis.md`,
  `docs/scratch/sprint-01.md` y los desgloses de US-031, US-042 a US-055, US-057, US-058,
  US-061, US-062, US-067 a US-070, US-078, US-079 y US-107.
- Lectura del código que el sprint modifica (sección 1) y `grep` de dependientes inversos
  sobre `api/src`, `api/tests`, `api/migrations`, `web/src`, `web/tests`, `infra` y `scripts`.
- Línea base ejecutada (sección 5). No se modificó ningún archivo fuera de este.

## 1. Blast radius: archivos existentes que el sprint modifica

Por cada archivo: qué cambia, quién lo importa hoy (dependientes inversos reales, sin
`__pycache__`) y qué pruebas lo cubren. Si un dependiente se rompe, se arregla en el mismo
slice (regla "cambio atómico y en cascada").

### `api/src/app/core/security.py`

- Cambios previstos: ninguno obligatorio en `PUBLIC_ROUTES` (ya contiene `login`, `refresh`,
  `forgot`, `reset`, `tv/today` y los dos `health`). Cambios de deuda: M-3 (que
  `refresh_keyring` no abra sesión antes de validar el token; ver `main.py`), L-5 (tope de
  longitud de contraseña en `validate_password_policy`/`hash_password`) y, si se decide,
  helpers de cookie (no: van en `auth/router.py`, porque `core` no puede importar módulos).
- Lo importan: `main.py`, `cli.py`, `core/config.py` (import perezoso de `StartupError`),
  `modules/auth/service.py`, `tests/conftest.py`, `tests/core/_principal_double.py`,
  `tests/core/_routes.py`, `tests/architecture/test_every_route_has_role.py`,
  `tests/architecture/test_route_guard_unit.py`, `tests/auth/test_principal_loader.py`,
  `tests/auth/test_seed.py`, `tests/cli/test_seed_cli.py`, `tests/core/test_config_secrets.py`,
  `tests/core/test_jwt.py`, `tests/core/test_passwords.py`, `tests/core/test_require_role.py`,
  `tests/crypto/test_provider_startup.py`.
- Pruebas que lo cubren: `test_jwt.py` (27 casos con `FrozenClock`), `test_passwords.py`,
  `test_require_role.py` (21 casos admin/coach/member, 401 por causa),
  `test_route_guard_unit.py`, `test_every_route_has_role.py`. Esta última tiene dos
  aserciones que condicionan el sprint: `test_la_lista_blanca_es_la_esperada` fija
  `PUBLIC_ROUTES` como un `frozenset` literal (cualquier ruta pública nueva exige cambiar la
  prueba, y el sprint no añade ninguna), y `test_login_y_forgot_llevan_limite_de_intentos`,
  que hoy no encuentra las rutas y pasa vacía, se activa sola cuando existan
  `POST /auth/login` y `POST /auth/forgot`: exige `rate_limit(...)` en las dos.
- Regla: `test_banned_imports.py` y `test_ruff_banned_api.py` prohíben `jwt`, `argon2`,
  `hashlib`, `hmac`, `cryptography` fuera de aquí y de `core/crypto`. `modules/auth` usa
  `hash_opaque_token`, `new_opaque_token`, `create_access_token`, `verify_password`,
  `needs_rehash`, `dummy_verify` ya existentes: no hay que ampliar `security.py` para
  US-042/043/047/048.

### `api/src/app/core/ratelimit.py`

- Cambios previstos: M-2 (clave por cuenta además de por IP, con el correo normalizado y
  nunca en el log; IPv6 agregada por /64 en `client_ip`). Hoy la clave es `(bucket, ip)`
  y la IPv6 cuenta por dirección completa.
- Lo importa: solo `tests/core/test_ratelimit.py` (la dependencia `rate_limit("login")` se
  declara por primera vez en `auth/router.py` en S2-B2). Lee `app.state.trusted_proxies`
  y `app.state.rate_limit_max_keys`, que fija `main.py`.
- Pruebas: `test_ratelimit.py` (ventana deslizante, `Retry-After`, `X-Forwarded-For` solo
  desde red de confianza, tope de claves, marca `__apex_rate_limit__`). Un cambio de la
  firma de `hit`/`allow` rompe esa prueba; ampliar con casos nuevos, no reescribir.

### `api/src/app/core/audit.py`

- Cambios previstos: ninguno en el código. US-107 usa `record(session, *, action="login",
  table_name="users", record_id, before=None, after={...}, user_id=...)`; la firma ya es
  keyword-only y `AUDIT_ACTIONS` ya incluye `login`. `AuditEntry` sigue en `core`.
- Lo importan: `main.py`, `cli.py`, `tests/conftest.py`, `tests/architecture/test_audited_tables.py`,
  `tests/architecture/test_core_import_direction.py`, `tests/auth/test_seed.py` y nueve
  archivos `tests/core/test_audit_*.py` (55 casos).
- Riesgo: `test_core_import_direction.py` exige que `core/audit` no importe `core/crypto`
  salvo `digest`. El módulo `audit` de Sprint 2 (`modules/audit/service.py`) vive fuera de
  `core`, así que la suscripción a `LoginAttempted`, `UserLocked` y `SessionsRevoked` no toca
  esta regla.

### `api/src/app/core/events.py`

- Cambios previstos: ninguno. Los eventos nuevos (`LoginAttempted`, `SessionsRevoked`,
  `UserLocked`, `PasswordChanged`, `MemberCreated`, `PlanCreated` si lo hubiera) se declaran
  en el `service.py` del módulo emisor, como `UserCreated` hoy.
- Lo importan: `modules/auth/service.py`, `tests/auth/test_seed.py`, `tests/core/test_events.py`,
  `test_events_db.py`, `test_events_router.py`.
- Contrato que condiciona a US-042/043: `emit` corre los handlers en la misma sesión y
  propaga excepciones; "nada después del commit". Los desgloses de US-042 y US-043 piden
  hacer `commit` en el camino de fallo y luego lanzar el 401 para que el evento sobreviva al
  rollback de `get_session`. Eso rompe el patrón "una transacción por petición" y
  `test_session_dependency.py` lo documenta; cubrirlo con una prueba propia en S2-B2.

### `api/src/app/core/config.py`

- Cambios previstos: ninguno obligatorio para las historias (ya existen `COOKIE_SECURE`,
  `FRONT_BASE_URL`, `ACCESS_TOKEN_TTL_S`, `REFRESH_TOKEN_TTL_DAYS`, `PASSWORD_MIN_LENGTH`,
  `TRUSTED_PROXIES`, `ADMIN_EMAIL`, `ADMIN_INITIAL_PASSWORD`). Cambios de deuda: M-8 (sacar
  `ADMIN_*` del `.env` compartido) y L-8/L-5 si se decide validar `COOKIE_SECURE` en
  producción o un `PASSWORD_MAX_LENGTH`.
- Lo importan: `migrations/env.py`, `cli.py`, `main.py`, `core/db.py`, `core/logging.py`,
  `core/security.py`, `core/crypto/provider.py`, `tests/conftest.py` y 18 archivos de
  pruebas (`test_config*.py`, `test_env_example.py`, `test_cors.py`, `test_jwt.py`, etc.).
- Pruebas que vigilan cualquier variable nueva: `test_env_example.py`
  (`test_toda_variable_de_settings_esta_documentada`,
  `test_toda_clave_ajena_al_api_esta_en_non_api_env_vars`, `test_sin_secretos_reales`): una
  variable nueva exige línea en `.env.example` y, si no es del api, entrada en
  `NON_API_ENV_VARS`. `extra="forbid"` hace que una clave desconocida en `.env` tumbe el
  arranque del api.

### `api/src/app/main.py` (`MODULES`)

- Cambios previstos: `MODULES` pasa de `("auth",)` a incluir `settings`, `audit`, `members`
  y `plans`, en ese orden de carga (el `service` de `audit` debe importarse después de
  `auth` para suscribirse a eventos que `auth.service` declara; `settings` antes de `auth`
  porque `GET /auth/me` lee `gym_name` por `settings.service`). M-3: `refresh_keyring` hoy
  se inyecta con `include_router(..., dependencies=[Depends(refresh_keyring)])`, es decir,
  abre sesión y consulta `crypto_keys` antes de `current_user`, también en rutas públicas;
  hay que moverlo detrás de la validación del token (por ejemplo, dentro de `require_role`
  o como dependencia que reciba `Principal`).
- Lo importan: `cli.py`, `tests/architecture/test_audited_tables.py`,
  `test_every_route_has_role.py`, `test_list_routes_use_page_params.py`,
  `test_routes_under_api_v1.py`, `tests/core/_app_rota.py`, `test_config_secrets.py`,
  `test_cors.py`, `test_docs_disabled.py`, `test_health.py`, `test_migration_lock.py`,
  `test_openapi_export.py`, `test_require_role.py`, `test_startup_failure.py`,
  `tests/crypto/test_provider_startup.py`.
- Dos pruebas de arquitectura recorren `MODULES` e importan por nombre:
  `test_audited_tables.py` hace `importlib.import_module(f"app.modules.{m}.models")` y
  `test_list_routes_use_page_params.py` hace `import_module(f"app.modules.{m}.router")`;
  además `include_module_routers` importa `router` de cada módulo. **El módulo `audit` del
  Sprint 2 solo trae `service.py`** (su router llega con US-108 y sus models viven en
  `core/audit.py`): sin un `audit/models.py` y un `audit/router.py` mínimos (o una lista
  separada para "módulos con router"), las dos pruebas y el arranque fallan en S2-B6.
- `cli.py` no llama a `load_module_services()`: `_seed` importa solo `auth.service`. US-107
  T3 exige que api, CLI y worker importen `audit.service` para que los handlers existan en
  todos los procesos. Cambio pequeño en `cli.py`, cubierto por `tests/cli/test_seed_cli.py`.

### `api/src/app/modules/auth/*`

- `router.py` pasa de vacío a 16 rutas (`/auth/*` y `/users/*`); `schemas.py` agrega
  `LoginIn/Out`, `RefreshOut`, `MeOut` (con `gym_name`), `UserCreateIn`, `CreateUserOut`,
  `IssuedLinkOut`, `RevokeSessionsOut`, `UserRow`; `service.py` agrega `can_login`, `login`,
  `refresh`, `logout`, `change_password`, `list_users`, `create_user`, `activate`, `forgot`,
  `reset`, `update_user`, `delete_user`, `lock`, `unlock`, `revoke_sessions`, `resend_link`,
  `_revoke_all`, `_issue_one_time_token`, y los eventos; `exceptions.py` agrega
  `InvalidCredentials` (401), `InvalidRefresh` (401), `InvalidToken` (400), `EmailTaken`
  (409), `LastAdmin` (409); `models.py` no cambia (`0004` ya trae `last_login_at`,
  `locked_at`, `replaced_by_id`, `one_time_tokens`). M-8 agregaría `must_change_password`.
- Lo importan: `cli.py` (`active_admin_id_by_email`, `seed_admin`),
  `tests/architecture/test_no_sensitive_in_logs.py`, `tests/auth/test_auth_schema.py`,
  `test_principal_loader.py`, `test_pure_users.py`, `test_seed.py`, `tests/cli/test_seed_cli.py`.
- Contrato que no se puede romper: `auth.service` registra `load_active_principal` al
  importarse (`register_principal_loader`), y `tests/core/test_require_role.py` vuelve a
  registrar el doble después de `create_app`. Cualquier prueba nueva de router que necesite
  un usuario real debe crearlo en la base (no hay todavía fixture `admin_token`/`login_as`;
  hace falta crearla en S2-B2 y reutilizarla en B3 a B9 y en `tests/members`, `tests/plans`).
- `test_no_physical_delete_users.py` escanea `src/` con regex: `DELETE /users/{id}` (US-049)
  tiene que ser `deleted_at`, nunca `session.delete(user)`.

### `api/src/app/cli.py`

- Cambios: `load_module_services()` en `_seed` (US-107 T3), L-4 (`resolve_actor` hoy acepta
  "cualquier rol, no dada de baja": debe exigir usuario activo y no bloqueado), M-8 (origen
  de `ADMIN_*`). Cobertura: `cli.py` está en `omit` de coverage; lo cubren
  `tests/cli/test_seed_cli.py`, `tests/crypto/test_init_keys.py`, `test_openapi_export.py`.
- Lo importan: `tests/conftest.py` (`init_keys_files`, `key_paths_in`), `tests/crypto/conftest.py`,
  `tests/architecture/test_every_route_has_role.py`, `tests/core/test_config_secrets.py`,
  `test_cors.py`, `test_docs_disabled.py`, `test_jwt.py`, `test_openapi_export.py`,
  `tests/crypto/test_init_keys.py`, `test_local_provider.py`, `test_provider_startup.py`;
  `infra/compose.yml` (servicio `tools`, `entrypoint python -m app.cli`).

### `api/tests/conftest.py` y `api/tests/core/_principal_double.py`

- Cambios: fixtures nuevas (cliente HTTP autenticado por rol, fábricas en
  `api/tests/factories/` que pide US-031 T2 y US-069) y, si se agrega `settings`/`members`/
  `plans` a `LIMPIEZA_DE_SESION`, el `DELETE` de esas tablas al empezar la sesión (los
  socios cifrados de una sesión anterior no se abren con la KEK temporal de la nueva).
- `_principal_double.py` no cambia; lo usan `conftest.py` y `test_require_role.py`.
- Riesgo: `migrated_database` corre `upgrade head` una vez por sesión; con `0005` a `0007`
  nuevas, `test_downgrade_a_base_vacia_y_vuelta_a_head` baja hasta `base` y vuelve, así que
  cada migración nueva necesita `downgrade` correcto desde el primer gate.

### `web/src/core/api/client.ts`

- Cambios: interceptor del 401 `token_expired` con refresh single-flight, Web Locks y
  `BroadcastChannel("apex-auth")` (US-043 T11); manejo del 403 sin limpiar sesión (US-053 T6).
  Ya existen `setAccessTokenGetter`, `registerOnUnauthorized`, `skipAuthRetry`.
- Lo importan: `src/core/api/client.test.ts`, `tests/lint/no-direct-fetch.test.ts` (ningún
  `fetch` fuera de `client.ts`). Las features nuevas (`features/auth`, `system`, `members`,
  `plans`) lo importarán.
- Contradicción a resolver antes de S2-F3: los desgloses de US-042 T12 y US-044 T6 dicen
  `credentials: "include"`; el cliente usa `"same-origin"` y `client.test.ts` lo afirma
  (decisión del Sprint 1 por N-13 y P7: un solo origen). Se mantiene `same-origin`; los
  desgloses se corrigen en T-DOC.

### `web/src/core/auth/*`

- Cambios: nuevos `session.ts`, `home.ts`, `routeAccess.ts`, `RequireRole.tsx`,
  `RequireAuth.tsx`; `useCan.ts` se conecta a `session.ts` sin cambiar firma (US-053);
  `index.ts` reexporta.
- Lo importan: `src/shared/ui/MaskedValue.tsx` (y sus dos pruebas), `tests/lint/restricted-config.ts`,
  `tests/unit/no-role-literals.test.ts`.
- Regla que condiciona el diseño: la regla ESLint (aplicada por Vitest en
  `tests/lint/restricted-config.ts`) solo permite comparar un rol con un literal en
  `src/core/auth/permissions.ts` y `src/core/auth/session.ts`. `homeFor(role)` (US-042 T11
  lo pone en `home.ts`) y `routeAccess.ts` comparan roles: o viven en `session.ts`, o se
  amplía el `ignores` de la regla y su prueba en el mismo slice (S2-F2/F3).

### `web/src/shared/ui/*`

- Cambios: nuevos `TopBar`, `SideNav` (US-061), `ThemeToggle` (en `core/theme`), y
  `index.ts` los exporta. `tests/kit-inventory.test.ts` (US-068 T7) exigirá un `*.test.tsx`
  por componente.
- Lo importan desde fuera de la carpeta: `tests/lint/no-direct-fetch.test.ts`,
  `no-intl-outside-i18n.test.ts`, `no-reveal-cache.test.ts` (reglas, no componentes).
  Cobertura actual 99,6 %; `vite.config.ts` ya tiene `coverage.thresholds`.

### `web/src/App.tsx`

- Cambios: deja de ser la página de prueba de fuentes y pasa a `RouterProvider` con
  `routes.tsx`, `QueryClientProvider` y `RoleProvider` conectado a `session.ts`.
- Lo importan: `src/App.test.tsx` (hay que reescribirla en S2-F2) y `src/main.tsx`.
  `tests/unit/index-html.test.ts` construye con Vite y verifica el nonce: no depende del
  contenido de `App`.

### `infra/nginx/default.conf` y `snippets/`

- Cambios: `location ~ ^/restablecer/ { access_log off; }` (US-048 T15), `log_format` sin
  `q` para `/api/v1/members` (US-070 T14; el formato `apex` ya registra solo `$uri`, sin
  query, así que basta con confirmarlo en la prueba), `limit_req` en `/api/v1/auth/login` y
  `/forgot` (M-3), `Cache-Control: no-store` en `proxy-api.conf` (L-1). La CSP no cambia.
- Lo usan: `web/Dockerfile` (COPY de `default.conf` y `snippets/`), `scripts/ci/test_nginx_conf.sh`
  (26 comprobaciones), `scripts/smoke/headers.sh` (19 ok), `compose-smoke.sh`,
  `web/tests/e2e/csp.spec.ts`. Cualquier cambio exige `docker compose build web`.

### `.github/workflows/ci.yml`

- Cambios: job nuevo `web-e2e` contra el stack de Compose con capturas en 320/768/1024/1440
  (S2-W0-1, US-068 T8, US-061 T8, US-062 T9); paso `check-initial-bundle.mjs` (US-067 T7).
  Los nombres `api`, `web`, `images`, `scripts`, `secrets-scan` son checks protegidos: no se
  renombran, solo se agregan.
- Gaps detectados: US-069 T19 y US-078 T14 piden "incluir la migración en el paso de CI
  `upgrade head → downgrade -1 → upgrade head`" y ese paso no existe en `ci.yml`. Lo que sí
  existe es `tests/core/test_migrations.py::test_downgrade_a_base_vacia_y_vuelta_a_head`,
  que corre dentro de `pytest` y cubre el ciclo completo. Decidir en el plan: o se agrega el
  paso, o los desgloses se corrigen para apuntar a esa prueba. El paso `openapi al día` falla
  si `docs/openapi.json` no se regenera tras cada slice de backend.

### Archivos que el sprint no debe tocar

`core/crypto/*`, `core/db.py`, `core/context.py`, `core/errors.py` (los códigos nuevos son
subclases de `DomainError` en cada `exceptions.py`), `core/pagination.py`, migraciones
`0001` a `0004`, `tests/core/_principal_double.py`.

## 2. Capa de datos

### Lo que existe (aplicado solo en bases locales)

- `0001_core_schemas`: los nueve esquemas de `APP_SCHEMAS` (`audit`, `crypto`, `auth`,
  `settings`, `members`, `plans`, `memberships`, `payments`, `worker`) y `btree_gist`. Los
  esquemas `settings`, `members` y `plans` ya existen: `0005` a `0007` solo crean tablas.
- `0002_audit_log` (con `subject_member_id`, corregida antes de cualquier push),
  `0003_crypto` (`crypto_keys`, `crypto_ops`, `crypto_jobs` con triggers),
  `0004_auth` (`users`, `refresh_tokens`, `one_time_tokens`, INSERT del usuario técnico N-15).
- Cadena lineal: `0001 → 0002 → 0003 → 0004` (head). `alembic current` en `apex-db-1` es
  `0004_auth (head)` según el cuaderno del Sprint 1.

### Lo que agrega el sprint

- `0005_settings` (S2-B1, US-054): `settings.settings_sections` con `key` bajo `CHECK` de
  ocho claves, `value JSONB`, `version >= 0`, `updated_by`, índice único por `key`, sin FK
  entre esquemas y sin filas sembradas. `down_revision = 0004_auth`.
- `0006_members` (S2-B7, US-069): `members.members` con cinco blobs `apx1.` (`document`,
  `phone`, `email`, `birth_date`, `emergency_contact`), tres `*_idx`, `CHECK (document LIKE
  'apx1.%')` y pares `(phone IS NULL) = (phone_idx IS NULL)`, índice único parcial
  `uq_members_document_idx_alive`, sin `*_hint` (N-01). `down_revision = 0005_settings`.
  Las ocho llaves del bus (`member.*`, 5 `encrypt` + 3 `index`) ya existen en
  `crypto.crypto_keys` desde S1-B5; no hay que crear clases nuevas en el registro.
- `0007_plans` (S2-B9, US-078): `plans.plans` con `price_cop > 0`, `kind IN ('days','classes')`,
  índice único parcial `uq_plans_name_alive` (N-22) e `ix_plans_active_alive`.
  `down_revision = 0006_members`.

### Riesgos de orden y reglas

- Orden de los slices igual al de la cadena (B1 → B7 → B9), así que no hay riesgo de dos
  heads si el backend se trabaja en serie. Si algún slice se desarrolla en un worktree
  paralelo (como hizo el front en el Sprint 1), `alembic heads` puede devolver dos: agregar
  `uv run alembic heads` (debe devolver uno) al ciclo de Alembic de cada gate.
- `migrations/env.py` dice "los `models` de cada módulo se importan aquí; cada historia
  agrega su línea" y hoy solo tiene el comentario de ejemplo. Agregar `settings`, `members`
  y `plans` en su slice; si no, `target_metadata` no los conoce y `alembic revision
  --autogenerate` daría una migración vacía (el `upgrade` escrito a mano sí funciona).
- Recarga en caliente aplica migraciones a medio escribir: el `api` de desarrollo monta
  `../api/migrations` por bind y corre `alembic upgrade head` en el `lifespan` en cada
  reinicio de `--reload`. Guardar un archivo `0005_*.py` incompleto en esa carpeta lo aplica
  (o rompe el arranque) en `apex-db-1`. Mitigación: escribir y probar la migración contra
  `db_test` con `pytest tests/core/test_migrations.py` antes de dejarla en
  `migrations/versions`, o detener `api` mientras se redacta.
- Regla "nunca editar una migración aplicada": `0001` a `0004` están aplicadas únicamente en
  `apex-db-1` (volumen `pgdata`) y `apex-db_test-1` (tmpfs), sin datos reales y sin push. El
  Sprint 1 corrigió `0002` bajando a `base` por esa razón. Para el Sprint 2 la regla se
  aplica tal cual: `must_change_password` (M-8) o cualquier columna que falte en `auth.users`
  va en una migración nueva (`0008_...`), no en `0004`.
- Limpieza de `db_test` por sesión: `LIMPIEZA_DE_SESION` borra llaves, bitácora y auditoría.
  Con `members.members` cifrada bajo la KEK temporal de cada sesión de pytest, las filas
  de una sesión anterior quedan ilegibles: agregar `DELETE FROM members.members`,
  `plans.plans`, `settings.settings_sections`, `auth.refresh_tokens`, `auth.one_time_tokens`
  (y los `users` distintos del técnico) a la limpieza en S2-B7, respetando triggers.
- `test_migrations.py` compara con el head del `ScriptDirectory` y baja hasta `base`: cada
  `downgrade` nuevo se prueba automáticamente desde el primer gate.

## 3. Contratos

### Estado de `docs/openapi.json` en HEAD

329 líneas; rutas `GET /health` y `GET /api/v1/health`; esquemas `ErrorBody`, `ErrorResponse`
y `HealthOut`; el 429 ya aparece (S1-B10). `web/src/core/api/types.ts` está generado desde
ese archivo (`npm run gen:api`) y `types.contract.test.ts` lo compara.

### Los 29 endpoints nuevos

- Auth (7): `POST /auth/login` y `POST /auth/forgot` públicos con `rate_limit` (5/min por IP);
  `POST /auth/refresh` y `POST /auth/reset` públicos; `POST /auth/logout`, `GET /auth/me`,
  `POST /auth/me/password` con `require_role("admin","coach","member")`.
- Users (9, admin): `GET`/`POST /users`; `GET`/`PATCH`/`DELETE /users/{id}`;
  `POST /users/{id}/lock`, `/unlock`, `/resend-link`, `/revoke-sessions`.
- Settings (8, admin): `GET`/`PATCH /settings/{section}` y las tres secciones
  `gym`, `privacy`, `memberships` (el plan cuenta las seis rutas concretas aparte de la
  genérica; en código es un solo par de rutas con `{section}` validado por enum).
- Members (2, admin y coach): `POST` y `GET /members`.
- Plans (3): `POST /plans` (admin); `GET /plans` y `GET /plans/{id}` (admin y coach).

Consecuencia operativa: ocho de los nueve slices de backend cambian el contrato. Cada uno
termina con `uv run python -m app.cli export-openapi ../docs/openapi.json` y
`cd web && npm run gen:api`, o el paso `openapi al día` de CI y `types.contract.test.ts`
fallan. El tipo `UserRow` cambia dentro del sprint (US-051 agrega `active_sessions`): es
aditivo.

### `PUBLIC_ROUTES` y las pruebas que vigilan las rutas

- `PUBLIC_ROUTES` ya lista las cuatro rutas públicas de auth: no cambia. La prueba
  `test_la_lista_blanca_es_la_esperada` lo fija literalmente.
- `test_every_route_has_role.py`: las 25 rutas no públicas tienen que llevar `require_role`
  en su árbol de dependencias (la marca `__apex_roles__`); `login` y `forgot` tienen que
  llevar `__apex_rate_limit__`. Corre con `ENV=production` (sin `/docs`).
- `test_list_routes_use_page_params.py`: `GET /users`, `GET /members`, `GET /plans` deben
  declarar `PageParams` y responder `Page[...]`.
- `test_routes_under_api_v1.py` y `test_error_responses_in_openapi.py`: todo bajo `/api/v1`,
  todo 4xx/5xx con `ErrorResponse` (lo da `responses=ERROR_RESPONSES` de la app).
- `test_no_cross_models.py` (`_imports.py`): `audit.service` puede importar
  `auth.service` (eventos) y `auth.schemas`; nunca `auth.models`. `auth.service` lee
  `settings.service.get(...)` para `gym_name`. `members`, `plans` y `settings` no se
  importan entre sí en este sprint.
- `test_audited_tables.py`: `settings.settings_sections`, `members.members` y `plans.plans`
  deben declarar `__audited__ = True`; US-107 T8 agrega la lista `REQUIRED_AUDITED_TABLES_V01`.
- `test_banned_imports.py` y `test_ruff_banned_api.py`: `members/service.py` solo usa
  `core.crypto.bus` y los tipos `Encrypted`/`BlindIndexed`; `auth` solo `core.security`.
- `test_no_sensitive_in_logs.py`: hoy está **saltada** con la condición
  `_existe("app.modules.auth.router") and _existe("app.modules.members.router")`. Su cuerpo
  es `raise AssertionError("implementar al activar: ...")`. En cuanto S2-B7 cree
  `members/router.py`, la prueba deja de saltarse y **falla en todos los gates** (A-5:
  `tests/architecture` corre siempre). Tiene que implementarse dentro de S2-B7 (login +
  crear socio con captura de stdout; el caso `reveal` queda para US-074).
- Pruebas de arquitectura nuevas del sprint: `test_settings_no_secrets.py`,
  `test_auth_routes.py`, `test_members_encrypted_at_rest.py`, `test_no_plaintext_at_rest.py`,
  `test_import_analyzer.py`, `test_list_rows_without_sensitive_fields.py`, y ampliaciones de
  `test_audited_tables.py`, `test_no_cross_models.py`, `test_banned_imports.py`.
  `test_no_plaintext_at_rest.py` (US-031 T4) exige una fábrica por tabla con columnas
  `Encrypted` en `api/tests/factories/`; sin ella falla "agregue una fábrica para <tabla>".

### Contradicciones entre desgloses que el plan debe cerrar

- US-107 T1 dice que `auth.service.login` llama a `core.audit.record` directamente; US-042 y
  `SPRINT-02.md` dicen que `login` emite `LoginAttempted` y US-107 se suscribe. Manda el plan
  del sprint: evento.
- US-057/US-058 ofrecen `current_privacy_version()` y `memberships_policy()`; US-149 y US-089
  (sprints posteriores) hablan de `get_section(...)`. Se fijan los dos primeros como
  canónicos ya en S2-B1.
- US-042/US-044 `credentials: "include"` frente a `same-origin` del cliente real (ver §1).
- US-042 T16 dice `COOKIE_SECURE` "por defecto true"; `Settings` y `.env.example` lo tienen en
  `false`. Mantener `false` en v0.1 (P7) y, como L-8, fallar cerrado en `ENV=production` sin
  `COOKIE_SECURE=true` salvo override explícito; decidirlo en el plan.

## 4. Servicios Docker y estrategia de rebuild

### Cómo corre cada servicio hoy

- `db` (`postgres:16`, volumen `pgdata`, puerto `127.0.0.1:${DB_PORT}` solo en desarrollo).
  Healthcheck `pg_isready`. No se reconstruye nunca.
- `db_test` (solo `compose.dev.yml`, `tmpfs`, puerto `127.0.0.1:${DB_TEST_PORT}`). Pytest del
  host apunta aquí con `TEST_DATABASE_URL`. Si se recrea el contenedor se pierde todo y
  `migrated_database` vuelve a migrar desde cero: inofensivo.
- `api` (imagen `apex-api:local`, `api/Dockerfile` en dos etapas con `uv sync --frozen`).
  En desarrollo `compose.dev.yml` monta `../api/src:/app/src` y `../api/migrations:/app/migrations`
  por bind y arranca `uvicorn --reload --reload-dir /app/src` con `WATCHFILES_FORCE_POLLING`.
  Consecuencias: cambios en `src/` y `migrations/` se ven sin rebuild; cambios en
  `pyproject.toml`/`uv.lock` (dependencia nueva) y en `alembic.ini` exigen
  `docker compose ... build api && up -d api`. El `lifespan` corre `alembic upgrade head`
  en cada reinicio. Nota: el comando de desarrollo no lleva `--proxy-headers` (el `CMD`
  de producción sí); como Nginx no es `127.0.0.1`, uvicorn no reescribe `client.host` en
  ningún caso y la IP real la resuelve solo `core/ratelimit.client_ip` con `TRUSTED_PROXIES`.
- `tools` (misma imagen, `entrypoint python -m app.cli`, perfil `tools`, volumen `keys` con
  escritura, **sin bind de `src`**). Cualquier cambio en `cli.py`, `auth/service.py` o en
  una migración que el CLI deba conocer exige `build api` (la imagen es la misma) antes de
  `docker compose run --rm tools seed|init-keys`. Es la única vía de escritura al volumen
  `keys` y el único lugar donde `ADMIN_*` debería estar presente (M-8).
- `worker` (misma imagen, perfil `worker`, sin `app/worker/main.py` todavía): fuera del
  sprint.
- `web` (imagen `apex-web:local`, `web/Dockerfile` con contexto en la raíz: `npm ci`,
  `npm run build`, Nginx con `COPY` de `dist`, `infra/nginx/default.conf` y `snippets/`).
  **No hay bind de `web/`**: cada slice de front (F1 a F8) y cada cambio de Nginx (W0-1,
  US-048, US-070, M-3, L-1) exige `docker compose ... build web && up -d web`. El servicio
  `web` depende de `api` con `condition: service_started` (no `healthy`): los E2E contra el
  stack deben esperar `api` healthy por su cuenta, como hace `compose-smoke.sh`.

### Estrategia de rebuild por slice (propuesta para el plan)

- S2-W0-1 (Nginx, CI): `build web`, `up -d web`, `bash scripts/ci/test_nginx_conf.sh`,
  `bash scripts/smoke/headers.sh`; si cambia `compose*.yml` (M-1), `up -d` del proyecto
  completo (crea la red con subred fija; recrea los cuatro contenedores sin tocar volúmenes).
- S2-B1 a S2-B9 (api): sin rebuild salvo dependencia nueva; verificar que `--reload` recogió
  el cambio (`docker compose logs --tail 20 api`) y `alembic current` dentro del contenedor
  tras B1, B7 y B9. Si la demo necesita `tools seed` con el `cli.py` nuevo: `build api`.
- S2-F1 a S2-F8 (web): `build web` al cerrar cada slice que se quiera ver en `8180`; los
  Vitest y el `vite preview` de Playwright no lo necesitan. Antes de la validación del
  sprint y de `kit.spec.ts`/`login.spec.ts` contra el stack: `build web` obligatorio.
- Evidencia de que hace falta: la imagen `apex-web:local` en ejecución se construyó el
  2026-10-21 21:12 UTC y HEAD `482295f` es del 2026-10-22 02:28 UTC; la imagen `apex-api:local`
  es de las 02:16 UTC (el api se salva por el bind de `src`).

## 5. Línea base en HEAD `482295f`

- api: `cd api && uv run pytest -q -p no:cacheprovider` con
  `TEST_DATABASE_URL=postgresql+asyncpg://apex:apex-test@127.0.0.1:5443/apex_test`:
  **443 pasan, 4 saltadas, 0 fallan** en 28,84 s. Saltadas: `test_no_sensitive_in_logs.py`
  ("se activa con US-042, US-069 y US-074") y tres comprobaciones de modo POSIX que NTFS no
  conserva (`test_jwt.py:196`, `test_init_keys.py:46`, `test_provider_startup.py:51`).
  Herramientas: `uv 0.13.4`, Python 3.12.10. Cobertura de referencia del cierre del Sprint 1:
  94 % global de `app` (`cli.py` y `worker/` en `omit`).
- web: `cd web && npm test -- --run`: **593 pasan en 43 archivos, 0 fallan** en 12,05 s.
  Node v24.14.0 (CI usa Node 22). Cobertura de referencia: 99,6 %.
- Docker (`docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml ps`):
  `apex-db-1` healthy (`127.0.0.1:5442`), `apex-db_test-1` healthy (`127.0.0.1:5443`, 11 h
  arriba), `apex-api-1` healthy (`127.0.0.1:8181`), `apex-web-1` healthy (`0.0.0.0:8180`).
  No se bajó nada; 80/8000/5432/5433 pertenecen a otros proyectos y no se tocan.
- `.env` local (solo nombres y puertos): `WEB_PORT=8180`, `API_PORT=8181`, `DB_PORT=5442`,
  `DB_TEST_PORT=5443`, `ENV=dev`, `CORS_ORIGINS=` vacío, `TRUSTED_PROXIES=172.16.0.0/12`,
  `COOKIE_SECURE=false`, `FRONT_BASE_URL=http://localhost`, `ADMIN_EMAIL` y
  `ADMIN_INITIAL_PASSWORD` presentes. `.env` no está versionado (`git ls-files` vacío).
- Type check y lint: en verde al cierre del Sprint 1 (`run-gates.sh`, `pre-commit
  --all-files`); no se repitieron aquí porque no hubo cambios desde ese commit.

## 6. Bugs y desajustes de configuración visibles

1. `FRONT_BASE_URL=http://localhost` con `WEB_PORT=8180` en el `.env` local. Los enlaces de
   activación y restablecimiento de US-047/048/052 se construyen con `FRONT_BASE_URL`, así
   que apuntarían al puerto 80 de otro proyecto. En `.env.example` la pareja `localhost`/`80`
   es coherente, pero el comentario no dice que el puerto debe acompañar a `WEB_PORT`.
   Corregir el `.env` local antes de S2-B3 y el comentario de `.env.example` en S2-W0-1.
2. `.env.example`, `CORS_ORIGINS`: dos comentarios contradictorios ("lista JSON" y "separados
   por coma"; el código acepta ambas). `TRUSTED_PROXIES`: el primer comentario ("IPs de
   proxies confiables... vacío: ninguno") quedó obsoleto bajo el segundo. Cosmético; se limpia
   con M-1.
3. `TRUSTED_PROXIES=172.16.0.0/12` cubre toda la red de Docker (deuda M-1 ya anotada). Con
   Nginx enviando `X-Forwarded-For $remote_addr` (un solo salto) el riesgo es acotado, pero
   cualquier contenedor de la LAN de Docker podría falsificar la IP del limitador.
4. `compose.dev.yml` arranca uvicorn sin `--proxy-headers` y producción con él: divergencia
   inofensiva hoy (ver §4) pero conviene igualarla o documentarla.
5. `compose.yml`: `web` depende de `api` en `service_started`; `tools` depende solo de `db`.
   `tools seed` antes de que `api` haya migrado falla con tabla inexistente: el orden del
   smoke (`init-keys` → `api` healthy → `seed`) debe repetirse en la demo y en el job
   `web-e2e`.
6. `ADMIN_EMAIL`/`ADMIN_INITIAL_PASSWORD` viajan a `api`, `worker` y `tools` por el mismo
   `env_file` (deuda M-8). `Settings` los admite como opcionales; `.env.example` pide borrarlos
   tras el seed, pero nada lo verifica.
7. `ci.yml`: el job `web` corre Playwright sobre `vite preview` sin api; no existe `web-e2e`
   ni el paso de ciclo de Alembic que nombran US-069/078. `images` corre `compose-smoke.sh`
   con `.env.example` copiado (puertos 80/8000/5432/5433: correcto en CI, nunca en esta
   máquina).
8. `alembic.ini`: `script_location = migrations` y `prepend_sys_path = src` son relativos a
   `api/`; `main.py` y `conftest.py` fijan rutas absolutas, y `tools` corre en `/app`. Sin bug;
   solo recordar que `alembic` a mano se ejecuta desde `api/`.
9. `Settings.ENV` por defecto `production` y `.env.example` `ENV=dev`: `compose-smoke` en CI
   publica `/docs`. Aceptable en smoke; la imagen de producción lo apaga por `.env`.

## 7. Deuda del Sprint 1 que este sprint absorbe

Fuente: `docs/scratch/sprint-01.md`, "Revisión de seguridad". L-2 y L-6 ya cerrados; H-1,
M-4, M-5, M-6 cerrados en el mismo cierre; M-7, L-3 y L-7 quedan fuera (EP-13/EP-17/EP-20).

- M-1 (resto): red de Compose con subred fija e IP fija del contenedor `web`
  (`networks.apex.ipam` y `ipv4_address`), `TRUSTED_PROXIES=<ip del proxy>/32` en
  `.env.example` y en el `.env` local, comprobación nueva en `scripts/ci/test_compose_config.sh`.
  Slice: **S2-W0-1** (infra) y se verifica al cablear `rate_limit("login")` en **S2-B2**
  (`test_ratelimit.py` + prueba de router del sexto intento). Requiere `up -d` del proyecto.
- M-2: límite por cuenta (clave `(bucket, correo normalizado)` además de `(bucket, ip)`,
  sin registrar el correo), IPv6 agregada por /64 en `client_ip`. Slice: **S2-B2**, en
  `core/ratelimit.py` y `auth/router.py`; pruebas en `test_ratelimit.py` y
  `test_login_router.py`. El "bloqueo por `locked_at`" automático no se recomienda (permite
  bloquear a un admin desde fuera); el bloqueo sigue siendo manual (US-050).
- M-3: `limit_req_zone`/`limit_req` en Nginx para `/api/v1/auth/login` y `/forgot`
  (**S2-W0-1**, `test_nginx_conf.sh`, `build web`); `refresh_keyring` solo después de validar
  el token (**S2-B2**, `main.py` + `security.py`; cubren `test_require_role.py`,
  `tests/crypto/test_provider_startup.py` y las pruebas de `refresh_if_stale`). Es
  prerrequisito de abrir el login: hoy toda petición pública abre sesión y consulta
  `crypto_keys` antes de autenticar.
- M-8: `ADMIN_*` solo en `tools` (por ejemplo un `.env.seed` ignorado por git que solo
  `tools` lee con `env_file: [../.env, ../.env.seed]`, o `environment` en `tools`; ampliar
  `check-key-files.sh` y `.gitignore`; `test_env_example.py` y `test_config*.py` siguen en
  verde porque los campos de `Settings` quedan opcionales). `must_change_password` para el
  admin sembrado: columna nueva en `auth.users` por migración `0008` (nunca editando `0004`)
  y exigencia en `GET /auth/me`/`POST /auth/me/password`. Slice: **S2-B3** (US-045) para la
  columna y el flujo; **S2-W0-1** para el `env_file`. Si el plan no quiere una cuarta
  migración en el sprint, `must_change_password` se difiere con nota en `DECISIONES.md`.
- L-1: `Cache-Control: no-store` (y `Pragma: no-cache`) en `snippets/proxy-api.conf` para
  todo `/api/`. Slice: **S2-W0-1**; `test_nginx_conf.sh` y `headers.sh`.
- L-2: cerrado (token opaco no ASCII → `TokenInvalid`).
- L-4: `cli.resolve_actor`/`active_admin_id_by_email` aceptan cualquier usuario no dado de
  baja; deben exigir activo y no bloqueado. Slice: **S2-B5** (cuando existan bloqueo y baja
  lógica reales), en `auth/service.py` y `cli.py`; pruebas `tests/cli/test_seed_cli.py` y
  `tests/auth/test_lock_unlock.py`.
- L-5: tope de longitud de contraseña (1024 en `LoginIn` según US-042 T4; aplicar el mismo
  tope en `core.security.validate_password_policy` para `reset`, `activate` y `me/password`).
  Slice: **S2-B2** (login) y **S2-B3** (`test_pure_password_policy.py`).
- L-8: cookie `apex_refresh` con `HttpOnly`, `SameSite=Strict`, `Path=/api/v1/auth`,
  `Secure` según `COOKIE_SECURE`. Slice: **S2-B2** (US-042 T6, `test_login_router.py`). La
  parte "con TLS" sigue en EP-20; decidir si `ENV=production` exige `COOKIE_SECURE=true`.

## 8. Condiciones para VERDE

Se incorporan al plan de la Fase 1; el plan-critic las verifica.

1. S2-B7 implementa `tests/architecture/test_no_sensitive_in_logs.py` (login + crear socio
   con captura de stdout) en el mismo slice que crea `members/router.py`; hoy el cuerpo
   lanza `AssertionError` y se activa solo.
2. S2-B6 entrega `modules/audit/models.py` y `modules/audit/router.py` mínimos (o separa
   "módulos con router" de "módulos con service" en `main.py`), porque
   `test_audited_tables.py`, `test_list_routes_use_page_params.py` e
   `include_module_routers` importan `models` y `router` de cada entrada de `MODULES`.
   `cli._seed` llama a `load_module_services()`.
3. S2-W0-1 cierra M-1, M-3 (Nginx), L-1 y el `env_file` de M-8, con `build web`, `up -d` del
   proyecto, `test_compose_config.sh` y `test_nginx_conf.sh` ampliados; S2-B2 cierra M-2,
   M-3 (`refresh_keyring`), L-5 y L-8 antes de exponer `POST /auth/login`.
4. `FRONT_BASE_URL` del `.env` local pasa a `http://localhost:8180` antes de S2-B3, y
   `.env.example` documenta que el puerto acompaña a `WEB_PORT`.
5. Cada slice de backend que publica rutas regenera `docs/openapi.json` y
   `web/src/core/api/types.ts`; cada migración nueva se prueba primero contra `db_test`
   (`test_migrations.py`) y después se deja en `migrations/versions` (bind con `--reload`);
   el gate de B1, B7 y B9 incluye `alembic heads` con un solo head y el ciclo
   `upgrade head → downgrade -1 → upgrade head` en `apex-db-1`. El plan decide si ese ciclo
   entra también como paso de CI o si los desgloses de US-069/078 se corrigen para apuntar a
   `test_migrations.py`.
6. Las contradicciones de contrato se resuelven en T-DOC antes de codificar:
   `LoginAttempted` por evento (no `audit.record` en `auth.service`), `credentials:
   "same-origin"`, `current_privacy_version()`/`memberships_policy()` canónicos,
   `COOKIE_SECURE=false` en v0.1, y dónde viven `homeFor`/`routeAccess` respecto a la regla
   de literales de rol (`session.ts` o `ignores` ampliado con su prueba).
7. S2-B2 crea la fixture de cliente autenticado por rol (usuarios reales en `db_test`,
   `login` real) que reutilizan B3 a B9; S2-B7 crea `api/tests/factories/` (US-031 T2) y
   amplía `LIMPIEZA_DE_SESION` con las tablas nuevas.
8. `build web` antes de cualquier E2E o demo contra `8180` (la imagen en ejecución es
   anterior al HEAD), y `build api` antes de `tools seed` si `cli.py` cambió.

## Riesgos residuales (no bloquean)

- `--reload` con polling y migraciones automáticas en desarrollo puede reiniciar el api a
  mitad de una prueba E2E; para `login.spec.ts` y `kit.spec.ts` contra el stack, no editar
  `src/` durante la corrida.
- Node local v24 frente a Node 22 en CI y en `web/Dockerfile`: `package-lock.json` manda;
  si una dependencia nueva (por ejemplo para Web Locks o axe en Playwright) solo instala en
  24, CI falla.
- Las cuatro pruebas saltadas por NTFS se verifican dentro del contenedor (Linux), como en
  el Sprint 1.
- `uq_members_document_idx_alive` y el formato del blob quedan fijados con datos reales por
  primera vez (riesgo HIGH del plan): `test_members_encrypted_at_rest.py` corre en todos los
  gates desde S2-B7 y no se cargan socios reales antes del release.
