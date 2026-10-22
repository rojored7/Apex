# Cuaderno · Sprint 2

Rama `feat/sprint-02-identidad-config-socios-planes`. Línea base en `7cadb62`: api 443 ok y 4
saltadas; web 593 ok en 43 archivos; stack `apex` en 8180/8181/5442/5443, los cuatro healthy.

### S2-W0-1 · Red fija y proxy de confianza, `.env.seed` solo para tools, Nginx endurecido y job e2e-stack

- Rojo (todas corridas y fallando antes del Verde):
  - `scripts/ci/test_nginx_conf.sh`: 29 fallas. Referrer-Policy fuera del snippet común y
    repartida por location (`no-referrer` en `= /index.html` y `/`; `strict-origin-when-cross-origin`
    en `/assets/`, `/fonts/`, `/brand/`, `@rate_limited` y `proxy-api.conf`), CSP con
    `form-action 'self'` (index) y `'none'` (api), `no-store` y `Pragma` en `proxy-api.conf`,
    `limit_req_zone` 60r/m, `limit_req burst=30 nodelay`, 16k, `error_page 429`,
    `limit_req_status`, `limit_req_log_level`, `@rate_limited` con envelope y `Retry-After 60`,
    y una prueba funcional con Nginx real en un contenedor desechable (token de `/restablecer/`
    y `q` fuera del log, `no-referrer` en `/restablecer/<token>`, ráfaga de 45 POST con 429,
    20 KB a auth con 413). La funcional destapó un hallazgo real: con `error_log ... error`,
    un 502 escribía `request: "GET /api/v1/members?q=..."` en el log (falla "el parámetro q
    aparece en el log" ya en la configuración de HEAD).
  - `scripts/ci/test_compose_config.sh`: 11 fallas (subred, IP de `web`, `ip_range`,
    `TRUSTED_PROXIES` = IP/32, `tools` con `.env.seed` `required: false`, api/worker/db sin
    `ADMIN_*` con valor, `.env.example` con `ADMIN_*` vacías, `.env.seed.example` vacío,
    `!.env.seed.example`).
  - `scripts/smoke/headers.sh` contra 8180: 9 fallas (aserciones de Referrer-Policy de `/`
    reemplazadas por `no-referrer` según E4/E9; `/api/v1/health` sigue con
    `strict-origin-when-cross-origin`; `form-action`, `no-store`, `Pragma`, `/restablecer/`,
    ráfaga 429 con envelope y `Retry-After`). Las tres del log pasaban ya (`$uri`).
  - `scripts/ci/test_check_key_files.sh` (nuevo): 1 falla (`.env.seed.example` bloqueado).
  - `web/tests/unit/playwright-config.test.ts` (nuevo, sobre un stub de `tests/e2e/helpers/stack.ts`):
    6 de 6 fallaban por aserción.
- Verde:
  - `infra/compose.yml`: `networks.default.ipam` con `172.30.0.0/24` e `ip_range: 172.30.0.128/25`
    (las IP dinámicas nunca toman la de Nginx), `web.networks.default.ipv4_address: 172.30.0.10`,
    `tools.env_file: [../.env, {path: ../.env.seed, required: false}]`.
  - `infra/nginx/default.conf`: `limit_req_zone $binary_remote_addr zone=apex_auth:10m rate=60r/m`,
    `location /api/v1/auth/` (limit_req burst 30 nodelay, 16k, `error_page 429 = @rate_limited`),
    `location @rate_limited` con el envelope `rate_limited`, `Retry-After 60`, `no-store` y CSP
    `'none'`; `error_log crit` y `limit_req_log_level warn`; Referrer-Policy por location; CSP del
    index con `form-action 'self'`. Sin location de `/restablecer/` (M-3).
  - `snippets/security-headers.conf` sin Referrer-Policy; `snippets/proxy-api.conf` con
    Referrer-Policy, CSP `form-action 'none'`, `Cache-Control no-store` y `Pragma no-cache`.
  - `.env.example`: `TRUSTED_PROXIES=172.30.0.10/32`, `ADMIN_*` vacías (Settings aún las declara;
    `SeedSettings` llega en B2), un solo comentario de `CORS_ORIGINS`, nota de `FRONT_BASE_URL` y
    `WEB_PORT`, bloque comentado del perfil E2E de límites (E5). `.env.seed.example` nuevo, vacío
    (L-9). `.gitignore` con `!.env.seed.example`; `check-key-files.sh` lo permite.
  - `scripts/ci/compose-smoke.sh`: `tools seed` con `.env.seed` (efímero con contraseña aleatoria
    si no existe, borrado al salir), comprobación de que el api no ve `ADMIN_*` y de que la IP de
    `web` es la de `TRUSTED_PROXIES`.
  - `web/playwright.config.ts`: proyectos `preview` (ignora `stack/**` y `helpers/**`) y `stack`
    (`stack/**/*.spec.ts`, `baseURL` de `E2E_BASE_URL`); sin `webServer` cuando existe
    `E2E_BASE_URL`. `web/package.json`: `e2e` = `--project=preview`, `e2e:stack` = `--project=stack`.
    `tests/e2e/helpers/stack.ts` (`VIEWPORTS`, `THEMES`, `captureName`, `capture`) y
    `tests/e2e/stack/captures.spec.ts` (cabeceras reales y 8 capturas). `csp.spec.ts` imita la
    CSP nueva.
  - `.github/workflows/ci.yml`: job `e2e-stack` (`needs: images`): `.env` desde el ejemplo,
    `.env.seed` efímero, build, `init-keys`, `up -d --build`, espera de api y web healthy, seed
    (con `--no-force-change` solo si `seed --help` lo lista), Playwright `--project=stack` con
    `E2E_BASE_URL=http://localhost:80` y artefacto `e2e-stack-captures`. `secrets-scan` corre
    también `test_check_key_files.sh`. Ningún job existente cambia de nombre.
  - `CLAUDE.md`: `.env.seed.example` en la estructura y la regla de `ADMIN_*`/`TRUSTED_PROXIES`.
  - Entorno local (no versionado, W0-1.4): `ADMIN_*` movidas de `.env` a `.env.seed` (ignorado),
    `TRUSTED_PROXIES=172.30.0.10/32`; `FRONT_BASE_URL` ya era `http://localhost:8180`.
- Evidencia:
  - Subred: `docker network inspect` de las 11 redes del host; usadas 172.17 a 172.25 /16, ninguna
    en 172.30.0.0/24. `docker compose version`: v5.0.2 (>= 2.24, `required: false` vale).
  - `bash -n` de `scripts/ci/*.sh`, `scripts/smoke/*.sh` y `scripts/workflow/*.sh`: sin errores.
  - `test_nginx_conf.sh`: 56 ok, 0 fallas (ráfaga funcional: 31 pasan y 14 reciben 429).
  - `test_compose_config.sh`: 31 ok, 0 fallas. `test_check_key_files.sh`: 9 ok, 0 fallas;
    `check-key-files.sh` sobre `git ls-files`: limpio.
  - `$DC down` (sin `-v`; volúmenes `apex_pgdata`, `apex_keys`, `apex_uploads` intactos) y
    `SMOKE_KEEP=1 bash scripts/ci/compose-smoke.sh`: verde en 72 s. db, db_test, api y web
    healthy; `seed: omitido: ya existe un admin activo` (tools leyó `ADMIN_*` de `.env.seed`:
    `.env` ya no las tiene); "api sin ADMIN_*"; "web en 172.30.0.10 = TRUSTED_PROXIES";
    `web-smoke.sh` 5 ok; `headers.sh` 29 ok, 0 fallas (12 respuestas 429 en la ráfaga, envelope
    y `Retry-After 60`; el log de Nginx sin el token ni `q`).
  - `docker network inspect apex_default`: `172.30.0.0/24`, rango `172.30.0.128/25`; web
    `172.30.0.10`, db `.130`, api `.131`, db_test `.129`. `alembic current`: `0004_auth (head)`.
  - Playwright `E2E_BASE_URL=http://localhost:8180 npm run e2e:stack`: 9 ok; 8 capturas en
    `web/test-results/captures/inicio-{light,dark}-{320,768,1024,1440}.png` (revisada la
    oscura a 320 px). `npm run e2e` (preview): 3 ok. `CSP_BASE_URL=http://localhost:8180/`
    `csp.spec.ts`: 1 ok y 1 saltada (la de control solo corre sobre preview).
  - `vitest run tests/unit/playwright-config.test.ts`: 6 ok; `tsc --noEmit` y `eslint` limpios.
  - api completo (`.env.example` cambió): 443 ok y 4 saltadas, igual que la línea base.
- Desviaciones:
  - Alcance acotado por el orquestador: W0-1.1 (correcciones de desgloses, `SPRINT-02.md`,
    `BRECHAS.md`, `docs/RUNBOOK.md`, nota del blueprint) y el `server.proxy` de `vite.config.ts`
    (W0-1.5, C8) quedan fuera de este slice; `DECISIONES.md` recibe solo las decisiones de W0-1.
    `loginComo` y `crearCoach` del helper llegan con el login real (B2/F3).
  - `TRUSTED_PROXIES` va como `172.30.0.10/32` (no la IP suelta del plan): mismo efecto en
    `Settings.trusted_proxies` y la prueba compara contra la IP de `web` más `/32`.
  - `ADMIN_*` siguen como líneas vacías en `.env.example` hasta B2 (`test_env_example` exige
    documentar todo campo de `Settings`); el api no las recibe con valor.
  - `error_log` baja de `error` a `crit` (hallazgo de la prueba funcional): se pierde el detalle
    de los fallos de conexión al upstream en el log de Nginx; el 502 sigue en el access log y el
    api registra lo suyo.
  - `limit_req` con valor fijo (no `NGINX_AUTH_RATE` por `envsubst`): ver decisión en
    `DECISIONES.md`.
  - Las specs `login`, `users-activation`, `role-guards`, `settings-gym` y `refresh-two-tabs` del
    proyecto `stack` se crean en sus slices; el proyecto toma todo `tests/e2e/stack/**`.
  - El gate de cierre incluye además `web/tests/unit/playwright-config.test.ts`.

### S2-B1 · Configuración del gimnasio (US-054, US-055 back, US-057, US-058)

- Rojo (Wave 3a; corrido sobre stubs, sin la migración `0005_settings`):
  - B1.1 kit de fixtures en `api/tests/conftest.py`: `proveedor_local`, `sin_llaves` y
    `bus_listo` movidas desde `tests/crypto/conftest.py` (que conserva solo
    `limpiar_llaves_con_commit`; `tests/core/test_audit_encrypted.py` y
    `test_audit_hook_encrypted.py` dejan de importarlas), `reloj` (`FrozenClock`
    `2026-10-21T15:00:00Z`), `argon2_rapido`, `seguridad` (`configure_security` y argon2 en
    mínimos), `cargador_real`, `app_http` (sin lifespan; `get_session` sustituido por la
    `session` de la prueba con commit o rollback), `usuario_real` (fábrica sobre
    `tests/factories/users.py::make_user`, usuario real con `hash_password` y token real),
    `cabeceras(usuario)` (`Bearer` y `Origin` de `FRONT_BASE_URL`) y `dos_sesiones` (E6: dos
    sesiones con commit real; al salir borra `settings.settings_sections` y la cola de
    auditoría que agregaron). `LIMPIEZA_DE_SESION` incluye `settings.settings_sections` con
    un `DO $$ ... to_regclass(...)` para no romper la suite mientras la tabla no exista.
    `tests/factories/__init__.py` con `FACTORIES = {"auth.users": make_user}`.
  - B1.2 stubs `api/src/app/modules/settings/{__init__,models,schemas,exceptions,service,router}.py`:
    modelo `SettingsSection` completo (auditado, `CHECK key_valid`, `version_non_negative`,
    `uq_settings_sections_key`), excepciones completas, `SectionKey`, `ENABLED_SECTIONS`,
    `MembershipsPolicy` y las entradas y salidas del API fijas; esquemas de valor vacíos,
    `SECTION_REGISTRY = {}` y `SECTION_DEFAULTS = {}`; service con `NotImplementedError`;
    router plano con las 8 rutas y `require_role("admin")`, aún fuera de `MODULES`.
    `test_single_head` en `tests/core/test_migrations.py`.
  - B1.3 pruebas: `tests/settings/` (`_apoyo.py` y los 11 archivos del plan),
    `tests/architecture/test_settings_no_secrets.py`, `tests/migrations/test_0005_settings.py`
    y el caso `test_nadie_fuera_de_settings_importa_settings_models` en
    `test_no_cross_models.py`.
  - Conteo: `pytest tests/settings tests/architecture/test_settings_no_secrets.py`: 190
    fallas y 1 ok (el control del detector de secretos, que prueba la propia prueba). Motivos:
    `NotImplementedError` de las puras y casos de uso (validate_section 79, update_section
    12, ensure_enabled 11, get_section 8, defaults_for 6, check_version 5, memberships_policy
    2, get, gym_name, current_privacy_version), 404 `not_found` del router no montado (52),
    `SECTION_REGISTRY` vacío (6). `test_0005_settings.py`: 4 fallas (la tabla no existe).
    Ningún error de import ni de fixture. Suite completa: 194 fallas, 446 ok, 4 saltadas; sin
    contar el Rojo, 445 ok (443 de la línea base, `test_single_head` y el caso nuevo de
    `test_no_cross_models`). `ruff check .`, `ruff format --check .` y `mypy src` limpios.
  - Control del kit (prueba desechable, borrada): con `MODULES` parchado a `("auth","settings")`,
    coach 403, sin token 401 y admin llega al service (el `NotImplementedError` sube como
    excepción porque `ASGITransport` relanza los errores de la app).
- Supuestos que el Verde debe respetar:
  - El coach recibe 403 también en `GET /settings/gym` (plan B1.3: "el coach recibe 403 en
    las 8 rutas"; S2-D14: el coach ve el nombre del gimnasio por `GET /auth/me`).
  - `field` del 422 en forma `value.<campo>`, tanto desde `validate_section` como desde la
    validación del cuerpo en las rutas tipadas; el `message` nunca repite el valor.
  - `SECTION_DEFAULTS`: `gym` = `name "APEX"` y los otros seis en `None`; `privacy` =
    `policy_version`, `policy_text` y `consent_required_from` en `None`, `retention_years 5`;
    `memberships` = 7, 30, 2, 7. `defaults_for` devuelve una copia.
  - `gym.email` se normaliza a minúsculas sin espacios (D5); NIT hasta 15 con
    `^\d+(-\d)?$`; `retention_years` y los cuatro de memberships son enteros estrictos
    (rechazan `"7"`, `7.5`, `7.0` y `True`).
  - `get_section` de una sección nunca guardada: `version 0`, `updated_at` y `updated_by`
    nulos; `update_section` deja `created_by` y `updated_by` = actor; auditoría `insert` con
    `before` nulo y `after` con `key`, `value` y `version`; `update` con `before`/`after` de
    `value` y `version`; `subject_member_id` nulo; `table_name = 'settings.settings_sections'`.
  - Primer guardado con `version != 0` y versión vieja: 409 `version_conflict` con el mensaje
    "Otra persona cambió esta sección. Recarga para ver los cambios." y sin `field`.
  - Restricciones de la migración con los nombres de `NAMING_CONVENTION`:
    `pk_settings_sections`, `ck_settings_sections_key_valid`,
    `ck_settings_sections_version_non_negative` e índice `uq_settings_sections_key`; sin FK.
  - El Verde agrega `settings` a `MODULES`, el import de `settings.models` en
    `migrations/env.py` y regenera `docs/openapi.json` (P-API).
- Verde (Wave 3b):
  - `api/src/app/core/validators.py` (nuevo): `EmailAddress` (D5) sin `email-validator`, con
    `check_email_shape` pura; pruebas en `api/tests/core/test_validators.py` (16 casos).
  - `modules/settings/schemas.py`: esquemas de `gym`, `privacy` (`PrivacySettings` y
    `PrivacyView`) y `memberships` (cuatro `StrictInt`), `SECTION_REGISTRY` con las tres
    habilitadas, `SECTION_VIEWS` (lectura: `privacy` con `PrivacyView`) y `SECTION_DEFAULTS`.
  - `modules/settings/service.py`: puras (`validate_section` con `field = "value.<loc>"` y
    mensaje "El campo value.<x> no es válido.", `check_version`, `defaults_for` con
    `deepcopy`, `ensure_enabled`), `get_section`, `update_section` (`FOR UPDATE` con
    `populate_existing`; primer guardado en `begin_nested()` con el `IntegrityError` de
    `uq_settings_sections_key` traducido a 409; `refresh` de `updated_at` tras el flush; log
    solo con `settings_key` y `settings_version`), `get`, `memberships_policy`,
    `current_privacy_version` y `gym_name` (respaldo "APEX").
  - `router.py`: solo el docstring (las 8 rutas del stub ya cumplían el contrato).
  - `api/migrations/versions/0005_settings.py`; import de `settings.models` en
    `migrations/env.py`; `MODULES = ("auth", "settings")` en `main.py`.
  - Contrato: `docs/openapi.json` (dos exportaciones idénticas) y `web/src/core/api/types.ts`
    regenerados; `types.contract.test.ts` 5/5 y `npx tsc --noEmit` limpio.
- Evidencia:
  - `pytest tests/settings tests/migrations tests/architecture tests/core/test_validators.py`:
    262 ok, 1 saltada (`test_no_sensitive_in_logs`, dueño B7). Suite completa: 656 ok,
    4 saltadas, 0 fallas. Cobertura global de `app` 95 % (`settings/service.py` 96 %,
    `schemas.py` 100 %, `router.py` 100 %, `core/validators.py` 100 %).
  - `ruff format .`, `ruff check .` y `mypy src` (48 archivos) limpios.
  - Alembic contra `db_test`: `upgrade head` → `downgrade 0004_auth` → `upgrade head`;
    `alembic heads` = `0005_settings (head)` (uno solo).
  - Stack (P-MIG): `pg_dump -Fc` en `docs/scratch/sprint-02-antes-0005_settings.dump`
    (ignorado), `stop api` mientras se escribía la migración, `start api` → `healthy`, el log
    muestra `Running upgrade 0004_auth -> 0005_settings` y `migraciones al día`;
    `alembic current` = `0005_settings (head)`; ciclo `downgrade -1` → `upgrade head` en
    `apex-db-1`; `\d settings.settings_sections` con `pk_settings_sections`,
    `uq_settings_sections_key`, `ck_settings_sections_key_valid` y
    `ck_settings_sections_version_non_negative`, sin FK y sin filas; `/health` 200
    `{"status":"ok","db":"ok"}`.
  - Escritura real por Nginx (`:8180`) con un token de acceso del admin de desarrollo
    (firmado dentro del contenedor del api; el login real llega en B2): `GET /settings/gym`
    defaults en versión 0; `PATCH` versión 0 → 1; `PATCH` con versión 0 otra vez → 409
    `version_conflict` con el mensaje exacto; `PATCH` versión 1 → 2; `GET /settings/tv` → 404
    `section_not_available`; `"7"` en `expiring_days` → 422 `value.expiring_days`; sin token
    → 401. En psql: una fila `gym` en versión 2 con `updated_by` del admin y dos filas de
    auditoría (`insert` con `after.version = 1` y `update` con `after.version = 2`) con el
    `user_id` del admin. La fila queda en la base de desarrollo como configuración real.
- Desviaciones:
  - `tests/migrations/test_0005_settings.py`: la consulta de `pg_constraint` pasa a
    `contype::text AS contype`. La prueba estaba objetivamente mal: asyncpg devuelve el tipo
    `"char"` como `bytes` (`b'p'`) y la comparación con `'p'` nunca podía pasar. No cambia lo
    que se verifica.
  - `SECTION_VIEWS` (no estaba en el blueprint): necesario para leer `privacy` sin publicar
    con `get`; anotado en `DECISIONES.md`.
  - El PATCH con un valor idéntico al guardado igual sube la versión (cada guardado es una
    versión); la auditoría `update` lleva solo `version` en ese caso porque el hook registra
    las columnas que cambian.

### S2-B2 · Rojo

- Línea base (HEAD `e0ad2d9`, árbol limpio): api 656 ok y 4 saltadas; `ruff check .` y
  `mypy src` (48 archivos) limpios.
- B2.1 fixtures (`api/tests/conftest.py`, E7 y E9): `load_module_services()` corre al importarse
  ANTES del import de `principal_double` y de `register_principal_loader(principal_double)`;
  autouse `restaurar_bus` (foto `{tipo: list(handlers)}` y restauración) y `reset_rate_limit`;
  `capturar_eventos(*tipos)` (quita solo su capturador), `sleeper_nulo` (`SleeperEspia` sobre
  `auth.service.configure_sleeper`), `api_prueba` (la app de `app_http`, con
  `app.state.settings` reemplazable) y `cliente_desde(ip)` (otra IP de socket, para IPv6);
  `usuario_real` gana `password=None` (pendiente), `borrado` y `debe_cambiar` (solo envía
  `must_change_password` si es verdadero); `LIMPIAR_AUTH` (refresh, tokens de un solo uso y
  usuarios `@test.apex`, nunca `SYSTEM_USER_ID`) en `LIMPIEZA_DE_SESION` y en el `finally` de
  `dos_sesiones`. Migrados a `restaurar_bus` todos los usuarios de `clear_subscribers()`:
  `test_events.py` (fixture `_bus_vacio` que vacía el bus dentro de la prueba),
  `test_events_db.py`, `test_events_router.py` (sin el `clear` final) y `tests/auth/test_seed.py`
  (usa `capturar_eventos`). `pytest tests/core tests/auth tests/settings`: sin regresiones.
- E3: `COOKIE_SECURE=true` en todo `Settings` de producción de las pruebas (`test_config.BASE`,
  `test_health` en dos sitios, `test_every_route_has_role._produccion`, `test_docs_disabled`,
  `test_logging_access`, `test_logging_sql`; las dos últimas no fijan `ENV` y caen en producción).
- B2.2 stubs (firmas tipadas, cuerpos `NotImplementedError`): `core/config.py` (las variables
  enteras nuevas con default y `gt=0`, incluidas `LOGIN_ACCOUNT_GLOBAL_*` de S2-D10;
  `AUTH_ALLOWED_ORIGINS`, `LOGIN_MIN_DURATION_MS=400` provisional, `ALLOW_INSECURE_COOKIE`;
  `validate_cookie_security`, `SeedSettings` declarada y `load_seed_settings` stub);
  `core/security.py` (`PASSWORD_MAX_LENGTH`, `too_long` en `WeakReason`, `Principal` con
  defaults, `PUBLIC_ROUTES` con logout: 8); `core/crypto/keyring.refresh_current`;
  `core/ratelimit.py` (`KeyKind`, `ip_bucket_key(ip, ipv4_prefix=24)`, `enforce`, `record`,
  `forget`, `configure_store_limits`, `store_for`, `rate_limits_from`; `peek`, `add` y `forget`
  del almacén); `auth/rules.py`, `auth/tokens.py` y `auth/cookies.py` nuevos; `auth/service.py`
  (eventos, `LoginResult`, `RefreshResult`, `configure_sleeper` real, `login`, `refresh`,
  `logout`, `active_user_id_by_email`, `seed_admin(force_change=True)`); `exceptions.py`,
  `schemas.py` y `router.py` plano con las tres rutas y sus dependencias declaradas.
- B2.3 y B2.4: regla `private_helper` en `tests/architecture/_imports.py` (escrita después de ver
  en rojo sus 5 casos de `test_find_forbidden_imports.py`; queda verde) y el caso de
  `test_no_cross_models.py`; `test_every_route_has_role.py` (8 públicas, las tres rutas de sesión
  registradas sin rol, bucket propio de límite en login, refresh, logout, forgot y reset);
  pruebas nuevas o ampliadas en `tests/core/{test_passwords,test_ratelimit,test_require_role,
  test_config,test_env_example}.py`, `tests/crypto/test_refresh_current.py`,
  `tests/migrations/test_0005b_auth_security.py`, `tests/auth/{test_pure_login,test_pure_refresh,
  test_auth_filter_matrix,test_login_service,test_login_router,test_refresh_service,
  test_refresh_router,test_logout_service,test_logout_router}.py`, `tests/auth/test_seed.py` y
  `tests/cli/test_seed_cli.py`; ayudas en `tests/auth/_sesion.py` y `tests/auth/conftest.py`.
- Conteo: 854 colectadas; 165 fallan, 685 pasan, 4 saltadas. Motivos de las 165:
  `NotImplementedError` de los stubs (117); `TypeError` porque `family_started_at` aún no es
  columna (19, `test_pure_refresh`); `ProgrammingError` por columna de `0005b` inexistente (4);
  revisión `0005b_auth_security` inexistente (5); aserciones de comportamiento (20:
  `.env.example` sin variables nuevas y con `ADMIN_*`, M-9 sin validador, `too_long`, IPv6 /64,
  topes de `app.state`, `iat` contra `tokens_valid_after`, keyring tras un token válido,
  `SeedSettings` y `--no-force-change` en el CLI, `--as` con cuentas no activas,
  `docs/openapi.json` desactualizado). Ningún error de import ni de fixture. Pasan ya sobre los
  stubs 16 casos nuevos (contrato declarado: rutas registradas, defaults de `Settings`,
  `private_helper`, `Principal`, 128 caracteres, firma inválida; y `cambiar-esto`, que ya está en
  `common_passwords.txt` desde el Sprint 1). Regresiones de la línea base: 2, ambas por cambio
  de contrato que cierra el Verde (`test_toda_variable_de_settings_esta_documentada` y
  `test_docs_openapi_json_esta_al_dia`). `test_la_lista_blanca_es_la_esperada` se actualizó
  (7 → 8, H-1).
- Decisiones de prueba que el Verde debe respetar:
  - Una petición, una transacción: los helpers de servicio confirman tras cada éxito; un 401 de
    login confirma antes de lanzar (S2-D8) y la prueba hace `rollback` después.
  - `family_started_at` del primer refresh sale del reloj de la app (`T0`), no de `now()` de SQL,
    y la rotación lo hereda; la familia muere cuando `family_started_at + 30 d <= ahora`.
  - `is_reuse`: rotado (`replaced_by_id` no nulo) y `ahora - revoked_at >= 10 s`; a los 9,999 s
    es gracia. Logout no deja `replaced_by_id`, no es reuso y no fija `tokens_valid_after`.
  - `tokens_valid_after = ahora truncado a segundos`; un `iat` igual pasa, uno anterior da 401
    `unauthorized`.
  - Límite por cuenta con clave `"{correo}|{ip_bucket_key(ip)}"` (/24, /64): se comprueba con
    `enforce(count=False)` antes de argon2 y se suma con `record` al fallar; tope global por
    correo (`account-global`); el último admin activo queda fuera de ambos y del bloqueo, pero
    su `failed_login_count` sí sube. `rate_limit` por IP mantiene la IPv4 exacta
    (`ipv4_prefix=32`) y agrupa IPv6 por /64; sus topes salen de `app.state.rate_limits`
    (`rate_limits_from(settings)`).
  - M-6: exactamente una verificación de argon2 por rama (espía sobre `security._hasher`); el
    pendiente usa `dummy_verify`; el piso pide al sleeper `0 < espera <= min_duration_ms / 1000`
    en todo 401 y nada en el éxito.
  - `LoginAttempted.user_agent` truncado a 120 y la fila de refresh a 255; el evento nunca trae
    el correo. `SessionsRevoked(by=SYSTEM_USER_ID)` en `lock` y en `refresh_reuse`.
  - Borrado de la cookie: `apex_refresh` vacía con `Max-Age=0`, `Path=/api/v1/auth`, `HttpOnly`
    y `SameSite=Strict`; el 403 de origen no emite `Set-Cookie`.
  - Las rutas leen `Settings` de `request.app.state.settings` (cookie `Secure`, orígenes).
  - `seed --no-force-change` fuera de dev sale con 2 y el mensaje menciona `ENV=dev`; `--as` con
    una cuenta no activa sale con 2 y el mensaje menciona `--as`.
- Desviaciones del encargo:
  - Las columnas de S2-D9 (`must_change_password`, `failed_login_count`, `tokens_valid_after`,
    `refresh_tokens.family_started_at`) NO se declaran en los modelos en el Rojo: sin la
    migración, todo `SELECT` de `User` o `RefreshToken` fallaría con `UndefinedColumn` y rompería
    unas 200 pruebas ajenas a B2 (settings, CLI, seguridad). Las declara el Verde junto con
    `0005b`. Sí entra ya `__audit_exclude__` con `failed_login_count` y `tokens_valid_after`
    (inocuo). `last_login_at` y `locked_at` ya existían desde `0004`.
  - `ADMIN_*` siguen en `Settings` y fuera de `NON_API_ENV_VARS` en el Rojo porque `cli seed`
    todavía las lee de ahí (mypy); las pruebas fijan el contrato y el Verde las mueve.
  - `tests/core/test_validators.py` ya existe y pasa desde B1 (16 casos); no se rehízo.
  - `main.py` (quitar `refresh_keyring`) y `.env.example` quedan para el Verde (B2.6); sus
    pruebas están en rojo.
  - `test_pure_login.py` cubre estado, `account_may_authenticate`, `should_auto_lock` e
    `is_active_admin`; `is_refresh_usable`, `is_reuse`, el tope de 30 días y `policy_from` van en
    `test_pure_refresh.py` (sin duplicar).
  - Casos del blueprint superados por H-1: "logout sin access da 401" y "un token de otro usuario
    no se revoca" ya no aplican (logout por cookie, sin Bearer).

### S2-B2 · Verde

- Producto: migración `0005b_auth_security` (cuatro columnas de S2-D9 y
  `ck_users_failed_login_count_non_negative`; `env.py` importa `auth.models`); columnas en
  `auth/models.py`; `rules.py`, `tokens.py`, `cookies.py`, `service.py` (login con H-4 y M-6,
  refresh con gracia y tope absoluto, logout por cookie, `seed_admin(force_change)`,
  `active_user_id_by_email`, cargador con `AUTH_FILTER`) y `router.py` plano; `core/security.py`
  (`too_long`, corte `tokens_valid_after`, `refresh_current` tras el token), `keyring.refresh_current`,
  `core/ratelimit.py` (almacenes por tipo con `OrderedDict`, `ip_bucket_key`, `enforce`/`record`/
  `forget`, `rate_limits_from`), `core/config.py` (`ADMIN_*` a `NON_API_ENV_VARS`, `SeedSettings`,
  M-9, `AUTH_ALLOWED_ORIGINS`), `main.py` (sin `refresh_keyring`; `app.state.rate_limits` y topes
  de almacén), `cli.py` (`SeedSettings`, `--no-force-change` solo en dev, `--as` solo activo),
  `.env.example` (sin `ADMIN_*`, variables nuevas activas, P7 junto a `ALLOW_INSECURE_COOKIE`),
  `scripts/ci/test_compose_config.sh` (ADMIN_* ausentes). `.env` local con
  `AUTH_ALLOWED_ORIGINS=http://localhost:8180,http://localhost:5173` y `up -d api` (E8).
- `LOGIN_MIN_DURATION_MS`: medido dentro de `apex-api-1` (argon2 3/65536/4 + commit, 30 muestras
  por corrida): medianas 47,8, 46,6 y 58,8 ms → 1,5 × ~48 = 72 → default 75 (`docs/RUNBOOK.md`).
- Revisión de seguridad (agente, sin CRITICAL ni HIGH): MEDIUM-1 (un rotado dentro de la gracia
  borraba la cookie nueva) corregido con `InvalidRefresh.clear_cookie` y prueba nueva en
  `test_refresh_router.py`; LOW-3 (IPv4 mapeada en IPv6) corregido en `ip_bucket_key` con prueba
  nueva en `test_ratelimit.py`; LOW-1 (ventana < 1 s del corte) y LOW-2 (último admin exento
  distinguible) quedan como riesgos aceptados en `DECISIONES.md`.
- Suite: 852 pasan, 4 saltadas, 0 fallos; cobertura de `app` 95 %; `ruff check .`, `ruff format`
  y `mypy src` (51 archivos) limpios. Contrato: `export-openapi` dos veces idéntico, `gen:api`,
  `types.contract.test.ts` 5/5 y `tsc --noEmit` limpio.
- Docker (previo al gate, repetido tras él sin tocar el árbol): dump
  `docs/scratch/sprint-02-antes-0005b_auth_security.dump`; `stop api` al escribir; `up -d api`
  aplicó `0005_settings -> 0005b_auth_security`; ciclo `downgrade -1`/`upgrade head` en `apex-db-1`
  y `alembic current` = `0005b_auth_security (head)`; `build api`; `tools seed` dos veces: "omitido"
  (el admin del Sprint 1 ya existe); en una base desechable `apex_seedcheck` (creada y borrada en
  `apex-db-1`): "admin inicial creado", luego "omitido", y el admin con `must_change_password = t`.
  Smoke por Nginx `:8180`: login 200 con `apex_refresh; HttpOnly; Max-Age=604800;
  Path=/api/v1/auth; SameSite=strict` y `Cache-Control: no-store`; refresh con `Origin` ajeno 403
  sin `Set-Cookie`; refresh 200 con cookie rotada; logout 204 con `Max-Age=0`; refresh tras logout
  401; login con `Origin` ajeno 403 sin `Set-Cookie`; seis fallos seguidos: 401 ×5 y 429
  (`Retry-After: 60`); psql: `token_hash` de 64 hex y `family_started_at` lleno en ambas filas;
  `/health` y `/api/v1/health` 200.
- Desviaciones (detalle en `DECISIONES.md` S2-B2): `tests/core/test_startup_failure.py` gana
  `COOKIE_SECURE=true` (llamador de E3 que el Rojo no listó: construye `Settings` de producción);
  dos pruebas nuevas de la revisión; el `logger.warning` del lifespan del blueprint lo reemplaza
  el validador M-9; `active_admin_id_by_email` se reemplaza por `active_user_id_by_email`.

### S2-B3 · Rojo

- Línea base (HEAD `ba984b7`, árbol limpio): api 852 ok y 4 saltadas (`-m 'not perf'`);
  `ruff check .` y `mypy src` (51 archivos) limpios. `FRONT_BASE_URL=http://localhost:8180` en el
  `.env` local (B3.1, solo verificado).
- B3.1 fábrica: `make_one_time_token(session, user, purpose, *, expires_in, used_at=None,
  created_by=SYSTEM_USER_ID)` en `tests/factories/users.py` (`expires_at` = reloj de la app +
  `expires_in`; guarda solo `hash_opaque_token`; devuelve `(claro, fila)`; commit como
  `make_user`) y `FACTORIES["auth.one_time_tokens"]`.
- B3.1 stubs (firmas tipadas, `NotImplementedError`; `ruff` y `mypy src` limpios):
  - `core/security.require_role(*roles, allow_pending_password=False)`: parámetro aceptado, sin
    cambiar el comportamiento (la marca `__apex_roles__` no cambia).
  - `auth/rules.py`: `ACTIVATE_TTL = 72 h`, `RESET_TTL = 1 h` y `RESET_PATH` (constantes reales);
    stubs `validate_password_policy(password, *, current_hash=None, field="password")`,
    `activation_url(base_url, token)`, `escape_like(value)`, `user_row(user, *, active_sessions)`
    y `user_out(user)`.
  - `auth/tokens.issue_one_time_token(session, user_id, purpose, *, now) -> (claro, OneTimeToken)`
    y el alias `OneTimePurpose`.
  - `auth/exceptions.py`: `EmailTaken` (409 `email_taken`) e `InvalidCurrentPassword` (422
    `invalid_current_password`), completas (son contrato).
  - `auth/schemas.py` completos: `StaffRole = Literal["admin","coach"]`, `UserOut` +
    `must_change_password`, `MeOut`, `ChangePasswordIn` (ambos `SecretStr` de 1 a 128),
    `AccessTokenOut`, `UserRow` (con `active_sessions`), `CreateUserIn(email, role: StaffRole)`
    sin `member_id` (`extra="forbid"`, L-2) y `CreateUserOut(user, activation_url, expires_at)`.
  - `auth/service.py`: evento `PasswordChanged(user_id, by, via, via_link_issued_by=None)` y
    stubs `me(session, principal) -> MeOut`, `change_password(session, user_id, current, new, *,
    current_refresh, policy) -> AccessTokenOut`, `list_users(session, *, q, role, status, page)
    -> Page[UserRow]` y `create_user(session, *, email, role, by, front_base_url) ->
    CreateUserOut`.
  - `auth/router.py` plano: `GET /auth/me` y `POST /auth/me/password` (tres roles con
    `allow_pending_password=True`, `no_store`; el segundo responde 200 `AccessTokenOut` y pasa la
    cookie `apex_refresh` como `current_refresh`), `GET /users` (admin, `PageParams`, `q`,
    `role`, `status` por alias, `no_store`) y `POST /users` (admin, 201, `no_store`, pasa
    `FRONT_BASE_URL` de `app.state.settings`). `core/logging.py` sin cambios.
- B3.2 pruebas: los 9 archivos de `tests/auth/` (`test_pure_password_policy`, `test_pure_links`,
  `test_pure_user_status`, `test_change_password`, `test_me_router`, `test_list_users`,
  `test_users_list_router`, `test_create_user`, `test_create_user_router`) con la ayuda
  `tests/auth/_cuentas.py`; `tests/core/test_require_role.py` (403 `password_change_required` con
  el doble, `allow_pending_password` sobre la ruta nueva `/_t/pendiente` de
  `tests/core/_routes.py`, y el recorrido de TODAS las rutas efectivas con rol, con usuarios
  reales `debe_cambiar` del rol que la ruta admite); `tests/core/test_logging_redact.py` (8 casos);
  `tests/architecture/test_list_routes_use_page_params.py` reescrita sobre `effective_routes` y
  `app.openapi()`; `tests/architecture/test_service_import_graph.py` nueva.
- Conteo: 992 colectadas; 103 fallan, 885 pasan, 4 saltadas. Las 102 del Rojo de B3: 94 por
  `NotImplementedError` de los stubs (rules, tokens, service; incluye el recorrido de
  `test_require_role`, que se corta en `GET /auth/me`) y 8 por aserción de comportamiento
  (7 de redacción en `test_logging_redact` y el 403 `password_change_required` con el doble).
  Ningún error de import ni de fixture. La 103 es la regresión por cambio de contrato que cierra
  el Verde con P-API: `test_docs_openapi_json_esta_al_dia` (rutas nuevas; `docs/openapi.json` no
  se toca en el Rojo). Pasan ya sobre los stubs 34 casos nuevos de contrato declarado: 401 sin
  token, 403 de coach y socio en `/users`, 422 con `field` de `PageParams`, `q`, `role`,
  `status`, `role=member` (L-2), `member_id` de más, correo inválido, 129 caracteres y campo de
  más en `me/password`, los TTL, la marca de roles, el grafo de services y la lista paginada.
  `db_test` queda sin usuarios `@test.apex`, sin refresh y sin tokens de un solo uso.
- Decisiones de prueba que el Verde debe respetar:
  - `require_role`: con `must_change_password` y sin `allow_pending_password`, 403
    `{"code": "password_change_required", "message": "Debes cambiar tu contraseña para
    continuar."}`, sin `field`, antes de validar el cuerpo (el recorrido manda `{}` a los POST y
    PATCH y espera 403; `POST /auth/me/password` con `{}` llega a la validación: 422).
  - `rules.validate_password_policy`: `AuthError` 422 `weak_password` con el `field` pedido
    (por defecto `password`), mensaje sin la clave; la longitud se revisa antes que la igualdad
    con `current_hash`. `service.validate_password_policy` (B2, `field="password"` fijo) sigue
    vigente para `seed_admin` y `test_pure_users.py`.
  - `change_password`: primero la actual (`InvalidCurrentPassword`, `field="current_password"`),
    luego la política con `field="new_password"`; un solo `update` auditado de `auth.users`
    (`password_hash = "***"` en `before` y `after`, `must_change_password` de true a false);
    `failed_login_count = 0`; `tokens_valid_after = ahora truncado` también sin otras sesiones;
    eventos en este orden: `PasswordChanged(user_id, by=user_id, via="change",
    via_link_issued_by=None)` y, solo si revocó alguna, `SessionsRevoked(by=user_id,
    reason="password_changed")`; devuelve `AccessTokenOut` con `iat = ahora` y `expires_in` de la
    política (900). La ruta no emite `Set-Cookie`.
  - `GET /auth/me`: `{id, email, role, member_id, gym_name, must_change_password}` con
    `gym_name` de `settings.service.gym_name` (respaldo `"APEX"`).
  - `list_users`: sin `SYSTEM_USER_ID`; sin `status` excluye borrados; `status_filter` por estado;
    `q` con `ILIKE` sobre el correo, `%` a cada lado de `escape_like(q)` y `ESCAPE` con la barra
    invertida; orden `email ASC`; `active_sessions` = refresh con `revoked_at IS NULL AND
    expires_at > ahora` (reloj de la app; `expires_at == ahora` no cuenta). `escape_like`
    antepone la barra invertida a la barra invertida, `%` y `_`.
  - `user_row` y `user_out`: exactamente los campos del contrato (`CAMPOS_USER_ROW` y
    `CAMPOS_USER_OUT` de `_cuentas.py`).
  - `create_user`: correo normalizado; `password_hash` nulo, `is_active` true,
    `must_change_password = False`, `created_by = by`; un token `activate` con
    `expires_at = ahora + 72 h` y `created_by = by`; dos `insert` de auditoría atribuidos al actor
    (la prueba de servicio abre `actor_scope(admin)`, como haría `current_user`), sin el token ni
    su hash; `UserCreated(role, by)`; `EmailTaken` con `existing_id` y mensaje sin el correo; una
    cuenta borrada libera el correo; en la carrera con `dos_sesiones` una alta gana y la otra da
    `EmailTaken` (su `existing_id` puede ser nulo o el de la ganadora). Ni el token ni la URL en
    ningún registro de log.
  - `activation_url`: quita las barras finales de la base, conserva su ruta y agrega
    `/restablecer/<token>` sin escapar.
  - `issue_one_time_token`: cierra por ORM los abiertos del mismo propósito con `used_at = now`
    (un `update` auditado por token cerrado), nunca los del otro propósito.
  - Redacción: `redact_text` cambia el token de `/restablecer/<token>` por
    `/restablecer/[redacted]` (con o sin esquema, query o fragmento) y el valor de
    `apex_refresh=<v>` por `apex_refresh=[redacted]` conservando los atributos; `SENSITIVE_KEYS`
    suma `activation_url`, `url` y `set-cookie`; `/restablecer` sin token no cambia.
  - Grafo de services: aristas permitidas `audit → auth` y `auth → settings`; el import de
    `settings.service` en `auth.service` va a nivel de módulo (un import perezoso fallaría: la
    lista blanca está vacía).
- Desviaciones del encargo:
  - `effective_route_contexts()` no existe en `tests/core/_routes.py` (ese archivo es el router
    de prueba `/_t/...`); el recorrido usa `app.core.security.effective_routes`, que ya recorre
    `effective_route_contexts` de FastAPI.
  - Helpers puros nuevos que no estaban en la lista: `rules.escape_like`, `rules.user_row` y
    `rules.user_out` (cubren "`q="_"` escapado" y "sin `password_hash`" en puro); constante
    `RESET_PATH`.
  - `create_user` recibe `front_base_url` (la URL se arma en el service con
    `rules.activation_url`) y no `member_id` (L-2 manda sobre el blueprint). `change_password`
    recibe `policy` para el `expires_in` del access nuevo.
  - Los casos de `issue_one_time_token` viven en `test_create_user.py` (no hay archivo propio en
    la lista del plan).
  - `test_every_route_has_role.py` y los conteos no cambian: ninguna prueba existente contaba
    rutas; `PUBLIC_ROUTES` sigue en 8.

### S2-B3 · Verde

- Producto (B3.3):
  - `core/security.require_role`: tras el rol, 403 `password_change_required` ("Debes cambiar tu contraseña para continuar.", sin `field`) si `must_change_password` y la ruta no pide `allow_pending_password`; constante `PASSWORD_CHANGE_REQUIRED_MESSAGE`.
  - `core/logging`: `_RESET_LINK` (`/restablecer/<token>` y `%2Frestablecer%2F<token>`), `_REFRESH_COOKIE` (`apex_refresh=<v>`) y claves `activation_url`, `url`, `set-cookie`.
  - `core/pagination.paginate`: firma `Select[T]` (SQLAlchemy 2.1).
  - `auth/rules`: `validate_password_policy(field=...)`, `activation_url`, `LIKE_ESCAPE`, `escape_like`, `user_row` y `user_out`.
  - `auth/tokens.issue_one_time_token`: cierra los abiertos del mismo propósito con `FOR UPDATE` y por ORM, con `update` auditado. Crea el nuevo con el TTL del propósito, guarda solo el hash y pone `created_by = get_actor()`.
  - `auth/service`:
    - `me` con `settings_service.gym_name`; el import va a nivel de módulo, arista `auth → settings`.
    - `change_password` con `FOR UPDATE`, tope por usuario y `revoke_all(except_id=<refresh propio de la cookie>)`.
    - `list_users` con `paginate` más `active_sessions` agregado por página.
    - `create_user` con `begin_nested` y `EmailTaken`.
    - `service.validate_password_policy` delega en `rules`.
  - `auth/router`: `POST /auth/me/password` con `rate_limit("change-password", 10)`.
- Revisión de seguridad (antes del gate que sella): sin CRITICAL. HIGH-1 corregido (límites de `me/password`), MEDIUM-2 en parte (`FOR UPDATE`), LOW-5 corregido. MEDIUM-3, LOW-4 y el resto de MEDIUM-2 quedan aceptados en `DECISIONES.md` (S2-B3). Pruebas nuevas: `tests/auth/test_change_password_limits.py` (3 casos) y un caso de enlace codificado en `tests/core/test_logging_redact.py`.
- Suite con `-m 'not perf'`: 996 colectadas; 992 pasan y 4 saltadas (las 3 de NTFS y `test_no_sensitive_in_logs`). Cobertura de `app` 95 %. `ruff format`, `ruff check` y `mypy src` (51 archivos) limpios.
- Contrato (P-API): `export-openapi` dos veces idéntico; `npm run gen:api`, `types.contract.test.ts` (5) y `tsc --noEmit` en verde. El límite nuevo no cambió el OpenAPI.
- Docs: `05_service_design.md` (`Principal` con `must_change_password` y `tokens_valid_after`, `me` con `gym_name`, `change_password`, `list_users`, `create_user` sin `member_id`, rutas tipadas de settings, `me/password` 200) y `DECISIONES.md` (S2-B3). `CLAUDE.md` sin cambios: no hay cambio estructural.
- Docker antes del gate, sin tocar el árbol (la recarga por bind recogió `service.py`, `router.py` y `logging.py`; no hay migración). Smoke por Nginx `:8180` con `Origin`:
  - login del admin 200;
  - `GET /auth/me` 200 con `gym_name = "APEX"` y `must_change_password = false`;
  - `GET /users?limit=25&offset=0` 200 con el admin `active` y `active_sessions = 1`;
  - `POST /users` (coach) 201 con `activation_url` que empieza por `http://localhost:8180/restablecer/` (token de 43), `pending_activation` y `expires_at` a 72 h;
  - el `POST /users` repetido da 409 `email_taken` con `field` y `existing_id`;
  - en psql, la fila `activate` guarda solo un hash de 64 hex y ninguna fila tiene el token en claro;
  - el log del api no contiene el token (0 coincidencias; el service nunca escribe la URL);
  - `/api/v1/health` 200.
- Coach de prueba que queda para B4 (activación): `coach-b3-smoke@test.apex`, rol `coach`, `pending_activation`, con un token `activate` abierto hasta 72 h después del smoke. B4 lo activa con `resend-link` (el token en claro ya se descartó).
- Desviaciones:
  - E1: el smoke de Docker corrió antes de los gates, porque este bloque debe nombrar al coach de prueba y el árbol no se puede tocar después del gate. Tras los gates solo se repite `/health`, sin escribir.
  - El gate que sella lista también `tests/auth/test_change_password_limits.py` (nació en la revisión).
  - `paginate` cambia de firma en `core/` (tipado, sin cambio de comportamiento).

### S2-B4 · Rojo

- Línea base (HEAD `07465fc`, árbol limpio): api 992 ok y 4 saltadas (`-m 'not perf'`);
  `ruff check .` y `mypy src` (51 archivos) limpios.
- B4.1 stubs (firmas tipadas, `NotImplementedError`; `ruff` y `mypy src` limpios):
  - `auth/exceptions.py` completas (contrato): `InvalidToken` (400 `invalid_token`, constante
    `INVALID_TOKEN_MESSAGE` = "El enlace ya no es válido. Pide uno nuevo al administrador."),
    `UserNotEligible` (409 `user_not_eligible`) y `UserNotFound` (404 `user_not_found`).
  - `auth/schemas.py` completos: `ResetIn(token 20–200, new_password SecretStr 1–128)`,
    `ForgotIn(email: EmailAddress)` (ya trae el tope de 254), `IssuedLinkOut(url, purpose:
    Literal["activate","reset"], expires_at)`, todos `extra="forbid"`.
  - `auth/rules.py`: stubs `is_one_time_token_usable(token, user, now)` y `link_purpose_for(user)`.
  - `auth/tokens.py`: stub `get_alive_or_404(session, user_id, *, include_deleted=False) -> User`.
  - `auth/service.py`: constantes reales `FORGOT_ACCOUNT_BUCKET = "forgot-account"`,
    `FORGOT_ACCOUNT_LIMIT = 5`, `FORGOT_ACCOUNT_WINDOW_S = 3600`; stubs `reset(session, token,
    new_password) -> None`, `forgot(session, email, *, ip, policy) -> None`,
    `resend_link(session, user_id, *, by, front_base_url) -> IssuedLinkOut` e
    `issue_link(session, user_id, *, by, front_base_url) -> IssuedLinkOut` (sin L-13, para el CLI).
  - `auth/router.py` cableado completo: `POST /auth/forgot` (`rate_limit("forgot")`, 204 vacío),
    `POST /auth/reset` (`rate_limit("reset")`, 204 vacío) y `POST /users/{user_id}/resend-link`
    (admin, `no_store`, 200 `IssuedLinkOut`, `FRONT_BASE_URL` de `app.state.settings`).
  - `cli.py`: comando `issue-reset-link <correo> --as <correo>` stub que no imprime nada.
  - `core/security.PUBLIC_ROUTES` ya tenía forgot y reset (8 rutas): verificado, sin cambios.
- B4.2 pruebas (129 casos nuevos): `tests/auth/test_pure_one_time_token.py` (26),
  `test_reset_forgot.py` (35), `test_reset_forgot_router.py` (25), `test_resend_link.py` (17),
  `test_resend_link_router.py` (9), `tests/architecture/test_auth_routes.py` (7) y
  `tests/cli/test_issue_reset_link_cli.py` (10).
- Conteo: 1125 colectadas; 109 fallan, 1012 pasan, 4 saltadas. Las 108 de B4: 98 por
  `NotImplementedError` de los stubs y 10 por aserción de comportamiento (el CLI stub sale con 0
  y no imprime la URL). Ningún error de import ni de fixture. La 109 es la regresión por contrato
  que cierra el Verde con P-API: `test_docs_openapi_json_esta_al_dia` (rutas nuevas;
  `docs/openapi.json` no se toca en el Rojo). Pasan ya sobre los stubs 21 casos de contrato
  declarado: los 7 de `test_auth_routes`, los 422 de `ForgotIn` y `ResetIn` (10) y 401, 403 de
  coach y socio y 422 de id mal formado en `resend-link` (4). `db_test` queda sin usuarios
  `@test.apex`, sin refresh y sin tokens de un solo uso.
- Contradicción resuelta: el blueprint (S2-B4) dice que las públicas de auth son "login,
  refresh, forgot y reset"; manda la revisión de seguridad (H-1, S2-D35, S2-D47):
  `test_auth_routes.py` espera exactamente login, refresh, logout, forgot y reset, las cinco con
  `__apex_rate_limit__` de su propio bucket.
- Decisiones de prueba que el Verde debe respetar:
  - `is_one_time_token_usable`: `used_at is None`, `now < expires_at` (igual a `now` ya no
    sirve; `now + 1 s` sí) y `account_may_authenticate(user)`, salvo que con `activate` no se
    exige hash. Consecuencia probada: un pendiente solo es usable con `activate`; un activo con
    hash también puede usar un `activate` vigente; bloqueado, borrado, inactivo y técnico nunca.
    `link_purpose_for` mira solo el hash (bloqueado o borrado no cambian el propósito).
  - `get_alive_or_404`: lee fresco; técnico e inexistente `UserNotFound` también con
    `include_deleted=True`; un borrado solo vuelve con `include_deleted=True`.
  - `reset`: el orden del blueprint. Todo fallo del token (inexistente, usado, vencido,
    bloqueado, borrado, inactivo, o `reset` sobre un pendiente) es `InvalidToken` con el mismo
    mensaje y sin `field`; la política va con `field="new_password"` y deja el token sin usar
    (la prueba hace rollback y luego lo usa con éxito). Éxito: `used_at = ahora`, hash nuevo,
    `must_change_password = False`, `failed_login_count = 0`. Con `reset`: `revoke_all` siempre
    (`tokens_valid_after = ahora truncado`, también sin sesiones) y `SessionsRevoked(user_id,
    by=user_id, revoked=n, reason="password_reset")` solo si n > 0. `PasswordChanged(user_id,
    by=user_id, via=<propósito>, via_link_issued_by=<created_by del token>)`. Devuelve `None`
    y no crea refresh (no inicia sesión). Auditoría: un solo `update` de `auth.users` del propio
    usuario (`password_hash = "***"` en `before` y `after`) y un `update` del token con
    `before.used_at = null`, `after.used_at` lleno y `token_hash = "***"`. Concurrencia: dos
    `reset` con `dos_sesiones` dan un éxito y un `InvalidToken` (`FOR UPDATE`).
  - `forgot(session, email, *, ip, policy)`: firma coherente con `login` (desviación: el
    encargo decía `sleeper`; la espera usa el sleeper de `configure_sleeper`, que ya anula
    `sleeper_nulo`, y el piso sale de `policy.min_duration_ms`). No escribe nada: ni filas, ni
    cierre del `reset` abierto, ni auditoría, ni cambios en `auth.users`, para ninguna cuenta
    (activa, bloqueada, pendiente, inactiva, borrada o inexistente). Exactamente una llamada al
    sleeper con `0 < espera <= min_duration_ms / 1000` exista o no el correo. Tope por cuenta:
    `ratelimit.enforce(FORGOT_ACCOUNT_BUCKET, <correo normalizado>, limit=5, window_s=3600)`
    con `count=True` (todo intento cuenta, exista o no la cuenta y desde cualquier IP); el sexto
    lanza `TooManyRequestsError` con `Retry-After`; otro correo no se frena; la ventana se
    libera a los 3600 s. Deja al menos un registro de log y ninguno lleva el correo ni su parte
    local.
  - `resend_link`: técnico o inexistente `UserNotFound`; bloqueado o borrado `UserNotEligible`
    sin crear tokens; L-13: `user_id == by` y otro admin activo con hash dan `UserNotEligible`
    sin cerrar su `reset` abierto; un admin pendiente sí recibe `activate`. Emite con
    `issue_one_time_token` (cierra el abierto del mismo propósito, aunque esté vencido, con
    `used_at = ahora`); `url` = `rules.activation_url(front_base_url, token)` (quita las barras
    finales); `expires_at` 72 h o 1 h. Auditoría: `insert` del token nuevo y `update` del
    cerrado atribuidos al admin, sin el token, su hash ni la URL; el log tampoco los lleva.
  - Ruta `resend-link`: el parámetro se llama `user_id` (`{id}` sombrearía el builtin, A002);
    200 con `Cache-Control: no-store` y sin `Set-Cookie`; 404 `user_not_found`, 409
    `user_not_eligible`, 422 con id mal formado; dos reenvíos seguidos dejan inválido el primero.
  - Rutas `forgot` y `reset`: 204 con cuerpo vacío y sin `Set-Cookie`; sin `Authorization` ni
    `Origin` (no usan cookie: NO llevan `require_same_origin`; S2-D38 solo cubre login, refresh y
    logout; anotado). Las cabeceras de `forgot` (salvo `date`) son idénticas exista o no la
    cuenta. `FORGOT_IP_LIMIT = 5`: el sexto por IP da 429. `RESET_IP_LIMIT = 10` (E5, manda
    sobre el "sexto" del encargo): el undécimo por IP da 429. El límite por cuenta de forgot se
    ve también por HTTP desde seis IP distintas.
  - CLI `issue-reset-link <correo> --as <correo>`: `FRONT_BASE_URL` de `Settings` (la prueba la
    pone con barra final); imprime una sola URL `<base sin barra>/restablecer/<token>` y el
    token una sola vez, sin el hash; propósito de `link_purpose_for` (el propio admin y otro
    admin activo: `reset` a 1 h; un pendiente: `activate`); `created_by` y actor de la
    auditoría = el admin de `--as`; sin `--as`, con un coach, un admin bloqueado o un correo
    inexistente en `--as`: sale con 2, el mensaje menciona `--as` y no hay filas; un correo
    objetivo inexistente sale con 2 con el MISMO mensaje que una cuenta borrada, sin repetir el
    correo y sin filas; dos invocaciones dejan un solo token abierto. El CLI no puede importar
    `rules` ni `tokens` (`private_helper`): usa `service.issue_link`.
- Desviaciones del encargo:
  - `forgot` recibe `policy` en vez de `sleeper` (ver arriba).
  - `service.issue_link` nuevo (no estaba en la lista): el CLI necesita emitir sin L-13 y solo
    puede llamar al `service.py`.
  - El "sexto por IP" de `reset` es el undécimo: E5 fija `RESET_IP_LIMIT=10`.
  - `FORGOT_ACCOUNT_WINDOW_S = 3600` (el encargo no fijaba la ventana).
  - Ninguna prueba existente cambió: `test_every_route_has_role.py` ya esperaba 8 públicas y su
    caso de límites ya listaba forgot y reset.

### S2-B4 · Verde

- Producto (B4.3):
  - `auth/rules`: `is_one_time_token_usable` (sin usar, `now < expires_at`; `reset` exige
    `account_may_authenticate`, `activate` admite `active` o `pending_activation` fuera del
    técnico) y `link_purpose_for` (solo el hash).
  - `auth/tokens`: `get_alive_or_404(include_deleted, for_update)` y
    `close_open_one_time_tokens` (revisión, MEDIUM-1). Orden de candados usuario → token.
  - `auth/service`: `reset` (token resuelto sin candado, `FOR UPDATE` del usuario y luego del
    token, `InvalidToken` único, política con `field="new_password"`, hash, `used_at`, cierre de
    los demás enlaces, `revoke_all` + `SessionsRevoked` solo con `reset`, `PasswordChanged` con
    `via_link_issued_by`); `forgot` sin leer ni escribir la base (tope `forgot-account`, piso,
    log sin correo); `issue_link` y `resend_link` (elegibles `active`/`pending_activation`, L-13
    en `resend_link`, `actor_scope(by)` para `created_by` y auditoría); `active_admin_id_by_email`
    para el CLI; `change_password` ahora también cierra los enlaces abiertos.
  - `cli issue-reset-link`: `--as` obligatorio de un admin activo, objetivo por `ids_by_email`,
    mismo mensaje y exit 2 para inexistente, borrado o no elegible; imprime la URL una vez.
- Pruebas del Rojo corregidas por error objetivo (no por comportamiento):
  - `test_reset_forgot.py::test_la_auditoria_deja_los_dos_updates_del_usuario_sin_el_token`
    esperaba `after.token_hash` en un `update`; `core/audit.diff_row` audita solo columnas
    cambiadas y `token_hash` no cambia. Ahora: si aparece, va `"***"` (el volcado sigue sin el
    token ni su hash).
  - `test_reset_forgot_router.py::_sin_fecha` también descarta `x-request-id`, que es distinto
    en cada petición (las demás cabeceras siguen idénticas exista o no la cuenta).
- Revisión de seguridad (antes del gate que sella): sin CRITICAL ni HIGH. MEDIUM-1 y LOW-1
  corregidos con pruebas nuevas en `tests/auth/test_one_time_token_closure.py` (3 casos); LOW-2,
  LOW-3, LOW-4 e INFO aceptados en `DECISIONES.md` (S2-B4).
- Suite con `-m 'not perf'`: 1128 colectadas; 1124 pasan y 4 saltadas. Cobertura de `app` 95 %.
  `ruff format`, `ruff check` y `mypy src` (51 archivos) limpios.
- Contrato (P-API): `export-openapi` dos veces idéntico; `npm run gen:api`,
  `types.contract.test.ts` (5) y `tsc --noEmit` en verde. Rutas nuevas: `POST /auth/forgot`,
  `POST /auth/reset` y `POST /users/{user_id}/resend-link`.
- Docs: `docs/RUNBOOK.md` (recuperar a un admin con `tools issue-reset-link`, `forgot` sin envío
  hasta US-131 y sus límites) y `DECISIONES.md` (S2-B4). `CLAUDE.md` sin cambios.
- Docker antes del gate (E1, como en B3: el bloque lleva la evidencia), sin tocar el árbol:
  `$DC build api` (cambió `cli.py`); la recarga por bind recogió el service. Por Nginx `:8180`:
  - `tools issue-reset-link coach-b3-smoke@test.apex --as <admin>`: exit 0, una URL
    `http://localhost:8180/restablecer/<token de 43>`, propósito `activate` (el coach seguía
    pendiente);
  - `GET` de esa URL: 200 con `Referrer-Policy: no-referrer`;
  - `POST /auth/reset`: 204; segundo uso: 400 `invalid_token`;
  - login del coach con la contraseña nueva: 200; psql: hash presente, activo, sin bloqueo,
    `must_change_password = f` (el coach queda `active`);
  - `POST /auth/forgot` del coach: 204 y psql sin token `reset` nuevo (0 antes, 0 después);
    del segundo al sexto: 204 ×4 y 429; tras liberar la ventana por IP (62 s), el mismo correo
    sigue en 429 y otro correo da 204 (tope por cuenta, no por IP);
  - `POST /users/{id}/resend-link` con el access del admin: sobre el coach 200
    `purpose=reset`; sobre el propio admin 409 `user_not_eligible`;
  - psql: todas las filas de `one_time_tokens` con `token_hash` de 64 hex, 0 filas con el token
    en claro, 0 filas de auditoría con el token; log del api: 0 coincidencias del token y 0 del
    correo del coach; `/api/v1/health` 200.
- Desviaciones:
  - E1: el smoke de Docker corrió antes de los gates (el bloque debe llevar la evidencia y el
    árbol no se toca tras el gate). Tras los gates solo se repite `/health`, sin escribir.
  - El gate que sella lista también `tests/auth/test_one_time_token_closure.py` (nació en la
    revisión).
  - `change_password` (B3) cambia: cierra los enlaces abiertos (MEDIUM-1).

### S2-B5 · Rojo

- Línea base (HEAD `6240359`, árbol limpio): api 1124 ok y 4 saltadas (`-m 'not perf'`);
  `ruff check .` y `mypy src` (51 archivos) limpios.
- B5.1 stubs (firmas tipadas, `NotImplementedError`; `ruff` y `mypy src` limpios):
  - `auth/exceptions.py` completas (contrato): `LastAdmin` (409 `last_admin`), `CannotLockSelf`
    (409 `cannot_lock_self`), `AlreadyLocked` (409 `already_locked`) y `NotLocked` (409
    `not_locked`), con mensaje en español y sin datos de la cuenta.
  - `auth/schemas.py` completos: `UpdateUserIn(email: EmailAddress | None = None, role: Role |
    None = None)` con `extra="forbid"` y `RevokeSessionsOut(revoked: int)`.
  - `auth/rules.py`: stubs `would_remove_last_admin(active_admin_ids, target_id, *, new_role,
    deleting)` y `lock_precondition(user, by_id, *, is_last_admin)`.
  - `auth/tokens.py`: stub `lock_active_admins(session) -> frozenset[UUID]`.
  - `auth/service.py`: stubs `get_user`, `update_user(session, user_id, *, email, role, by)`,
    `delete_user(session, user_id, *, by)`, `lock`, `unlock` y `revoke_sessions(...) -> int`
    (en `__all__`). `UserLocked` y `SessionsRevoked` ya existían desde B2.
  - `auth/router.py` cableado completo, todas con `Admin` y `no_store`: `GET /users/{user_id}`
    y `PATCH` (200 `UserOut` por `rules.user_out`), `DELETE` (204 sin `Response` propia, para que
    FastAPI conserve el `Cache-Control` de `no_store`), `POST /users/{user_id}/lock` y `/unlock`
    (200 `UserOut`) y `/revoke-sessions` (200 `RevokeSessionsOut`).
  - `cli.py`: comando `unlock-user <correo> [--as <correo>]` stub (`NotImplementedError`).
- B5.2 pruebas (156 casos nuevos): `tests/auth/test_pure_last_admin.py` (13),
  `test_update_delete_user.py` (29), `test_user_detail_router.py` (31), `test_pure_lock.py` (13),
  `test_lock_unlock.py` (19), `test_lock_router.py` (20), `test_revoke_sessions.py` (10),
  `test_revoke_sessions_router.py` (11), `tests/cli/test_unlock_cli.py` (8) y
  `tests/architecture/test_auth_routes.py` (+2: lista exacta `RUTAS_USERS` y `no_store` en todas;
  "toda ruta bajo /users es admin" ahora exige las nueve). Ayuda nueva `tests/auth/_ciclo.py`
  (`ruta`, `como`, `entrar`, `sesiones_vivas`, `EVENTOS_DE_CUENTA`).
- Conteo: 1284 colectadas; 130 fallan, 1150 pasan, 4 saltadas. Las 129 de B5: 121 por
  `NotImplementedError` de los stubs (incluidas las tres carreras con `dos_sesiones`, que usan
  `return_exceptions=True` y fallan por aserción con el `NotImplementedError` dentro) y 8 del CLI
  por comportamiento (el stub sale con 1). Ningún error de import ni de fixture. La 130 es la
  regresión por contrato que cierra el Verde con P-API: `test_docs_openapi_json_esta_al_dia`.
  Pasan ya sobre los stubs 27 casos de contrato declarado: 401 sin token, 403 de coach y socio,
  422 de id mal formado y de cuerpo (`extra="forbid"`, rol o correo inválidos), los cuatro
  errores 409 y los dos casos nuevos de `test_auth_routes`. El recorrido de `test_require_role`
  (403 `password_change_required`) ya cubre las seis rutas y pasa. `db_test` queda sin usuarios
  `@test.apex`, sin refresh, sin tokens de un solo uso y sin secciones de settings.
- Decisiones de prueba que el Verde debe respetar:
  - `would_remove_last_admin`: verdadero solo si `target_id` está en el conjunto, el conjunto es
    de uno y hay baja o `new_role` distinto de `admin`. `new_role=None` sin baja,
    `new_role="admin"` o un objetivo fuera del conjunto (coach, pendiente, bloqueado, técnico)
    dan falso.
  - `lock_active_admins`: rol admin, `is_active`, sin `locked_at` ni `deleted_at`, con hash, sin
    el técnico (que en `db_test` es `admin` inactivo). `FOR UPDATE` probado con `SET LOCAL
    lock_timeout` en la segunda sesión (espera `DBAPIError`).
  - `get_user`: incluye borradas; técnico e inexistente `UserNotFound`.
  - `update_user`: técnico, inexistente o borrada `UserNotFound`; correo normalizado; el propio
    correo con otra caja no choca; el de una borrada se puede tomar; `EmailTaken(field="email",
    existing_id=<la otra>)` sin el correo en el mensaje; carrera de dos cuentas al mismo correo:
    una gana y la otra `EmailTaken` (`existing_id` nulo o el ganador). Rol: `validate_user_role`
    con el `member_id` actual (coach a member `member_id_required`; member a coach
    `member_id_not_allowed`); degradar al último admin activo da `LastAdmin` (un admin pendiente
    o bloqueado no lo releva). Cuerpo vacío (`{}`): 200 sin cambios y sin fila de auditoría. Un
    `update` auditado por el actor con `before`/`after` de lo que cambió. El cargador ve el rol
    nuevo: un admin degradado recibe 403 en `GET /users` con su token anterior.
  - `delete_user`: técnico, inexistente o borrada `UserNotFound` (la segunda baja da 404: DELETE
    no es idempotente); baja lógica `deleted_at = ahora` sin `session.delete` (espía) y sin fila
    `delete` en la auditoría, con un `update` del actor; `LastAdmin` para el último admin activo
    (el técnico no cuenta); `revoke_all` en la misma transacción (`revoked_at = ahora`,
    `tokens_valid_after = ahora truncado`); `SessionsRevoked(user_id, by, revoked=n,
    reason="delete")` siempre, también con n = 0; si un handler de `SessionsRevoked` lanza, no
    queda `deleted_at`, ni corte, ni revocación; el correo queda libre para `create_user`; la
    cuenta deja de autenticar (401 en `/auth/me`). Dos bajas concurrentes de los dos únicos
    admins: exactamente una.
  - `lock`: borrada, técnico, inexistente `UserNotFound`; orden de errores `CannotLockSelf`,
    `AlreadyLocked`, `LastAdmin`. `LastAdmin` solo se alcanza por el service (con `by` del
    técnico o de un coach): por HTTP quien bloquea ya es otro admin activo. Éxito: `locked_at =
    ahora` por el ORM (un `update` auditado por el admin), `revoke_all`, y los eventos en este
    orden: `UserLocked(user_id, by, reason="admin")` y `SessionsRevoked(user_id, by, revoked=n,
    reason="lock")`, también con n = 0. Si un handler de `UserLocked` lanza, no queda nada.
  - `unlock`: borrada, técnico, inexistente `UserNotFound`; `NotLocked` sin fila de auditoría;
    `locked_at = None` (un `update` auditado por el admin; `failed_login_count` fuera del diff) y
    `failed_login_count = 0`; `ratelimit.forget(ACCOUNT_BUCKET, <correo>)` (borra todas las
    subclaves `correo|red`) y `ratelimit.forget(ACCOUNT_GLOBAL_BUCKET, <correo>,
    kind="account-global")`, sin tocar las de otra cuenta (verificado con `enforce(limit=1,
    count=False)`); cierra los enlaces abiertos (`used_at = ahora`, `update` auditado por el
    admin; decisión S2-B4 MEDIUM-1); las sesiones siguen revocadas y `tokens_valid_after` no
    cambia; ningún evento de dominio. Tras desbloquear, el access viejo sigue en 401 y uno nuevo
    entra.
  - `revoke_sessions`: borrada, técnico, inexistente `UserNotFound`; revoca solo los refresh vivos
    de ese usuario y devuelve cuántos; `tokens_valid_after` = ahora truncado (probado con
    `T0 + 1,75 s`, que da `T0 + 1 s`) también sin sesiones; `SessionsRevoked(..., reason="admin")`
    con n = 0 y con n = 2; no bloquea ni toca `failed_login_count`; el admin que se revoca a sí
    mismo pierde su refresh (`refresh` da `InvalidRefresh`) y su access. Ruta: 200
    `{"revoked": n}` sin `Set-Cookie`; un access con `iat` igual al corte pasa y uno anterior da
    401.
  - Orden de candados usuario → token: seis rondas de `revoke_sessions` y `refresh` concurrentes
    (alternando cuál arranca primero) con `dos_sesiones`; al final de cada ronda, cero refresh
    vivos. El Verde debe hacer que `refresh` bloquee el usuario antes que el token (como `reset`:
    `user_id` del token sin candado, `FOR UPDATE` del usuario y luego del token con
    `populate_existing`), o un sucesor creado durante la revocación sobrevive (riesgo de B3
    MEDIUM-2 diferido a B5).
  - Rutas: 200 y 204 con `Cache-Control: no-store` (no se mira en los 4xx); 404 `user_not_found`;
    409 con su código; 422 `validation_error` con id mal formado.
  - CLI `unlock-user <correo> [--as <correo>]`: normaliza el correo; éxito exit 0 con una línea
    no vacía; `locked_at` nulo y `failed_login_count = 0`; el `update` auditado lleva
    `SYSTEM_USER_ID` sin `--as` y la persona de `--as` con él; `--as` inexistente o bloqueado sale
    con 2 con `--as` en el mensaje (`resolve_actor`) y sin cambios; una cuenta no bloqueada, una
    inexistente y una borrada salen con 2 y el mismo mensaje, sin repetir el correo y sin
    auditoría; una segunda invocación sobre la misma cuenta sale con 2. El CLI no puede importar
    `rules` ni `tokens` (`private_helper`): usa `service.ids_by_email` y `service.unlock`.
- Desviaciones del encargo:
  - Ayuda nueva `tests/auth/_ciclo.py` (no estaba en la lista; evita repetir rutas y logins).
  - `test_auth_routes.py` gana dos casos (lista exacta y `no_store`) además de ampliar la lista.
  - "DELETE 204 y segundo 404 o idempotente": se eligió 404, coherente con `update_user`, que da
    404 sobre una borrada.
  - `SessionsRevoked` de `delete` y `lock` se emite también con 0 (el plan solo lo exigía para
    `revoke_sessions`): así toda revocación administrativa queda auditada (S2-D49), igual que el
    bloqueo automático de B2.
  - `unlock` cierra los enlaces abiertos: lo pide `DECISIONES.md` S2-B4 (MEDIUM-1), no la lista
    del blueprint.
  - "Inexistente exit 2 mismo mensaje" del CLI se leyó como un solo mensaje para no bloqueada,
    inexistente y borrada (no revela si la cuenta existe), igual que `issue-reset-link`.
  - Las pruebas de "un handler falla" usan una excepción propia (`HandlerRoto`): con
    `RuntimeError` pasaban sobre los stubs, porque `NotImplementedError` hereda de él.

### S2-B5 · Verde

- B5.3 Verde:
  - `rules.would_remove_last_admin` (verdadero solo si el objetivo es el único del conjunto y hay
    baja o un rol distinto de `admin`) y `rules.lock_precondition` (`CannotLockSelf`,
    `AlreadyLocked`, `LastAdmin`).
  - `tokens.lock_active_admins`: `SELECT id` de admins activos con hash, sin bloqueo, baja ni el
    técnico, `ORDER BY id FOR UPDATE`.
  - `service.get_user` (`get_alive_or_404(include_deleted=True)`), `update_user`, `delete_user`,
    `lock`, `unlock` y `revoke_sessions`. Candados: admins activos → cuenta → tokens. `unlock`
    olvida `login-account` (todas las redes) y `login-account-global` al final y cierra los
    enlaces abiertos.
  - `refresh` bloquea el usuario antes que el token (`_locked_refresh_and_owner`, el orden de
    `reset`): cierra el riesgo diferido de B3 MEDIUM-2. `logout` sigue con `_locked_refresh_row`.
  - `cli unlock-user <correo> [--as]` con `service.ids_by_email` y `service.unlock`; un solo
    mensaje (exit 2) para no bloqueada, inexistente y borrada, sin el correo.
- Revisión `security-reviewer` sobre `git diff 6240359 -- api/src` (sin CRITICAL ni HIGH):
  MEDIUM-1 corregido (el bloqueo automático por fallos toma `lock_active_admins` antes de
  `increment_failures`; prueba nueva `tests/auth/test_auto_lock_last_admin.py`, roja antes del
  arreglo), LOW-3 corregido (cambiar el correo cierra los enlaces abiertos; prueba nueva
  `tests/auth/test_update_user_email_links.py`), LOW-1, LOW-2 y LOW-4 aceptados
  (`DECISIONES.md` S2-B5).
- Prueba corregida por error objetivo: `test_revocar_y_refrescar_a_la_vez...` pedía
  `argon2_rapido` en vez de `seguridad` y, corrida sola, fallaba por llaves JWT sin configurar.
- Suite: 1287 colectadas; 1283 pasan, 4 saltadas, 0 fallan (`-m 'not perf'`); cobertura de
  `app` 95 % (`auth/service.py` 96 %, `rules.py` y `tokens.py` 100 %); `ruff format --check`,
  `ruff check .` y `mypy src` (51 archivos) limpios. Cada archivo de B5 pasa también corrido
  solo.
- B5.4 contrato (P-API): `export-openapi` dos veces idéntico; `npm run gen:api`;
  `types.contract.test.ts` 5 ok; `tsc --noEmit` limpio.
- Docs: `docs/RUNBOOK.md` (sección "Ciclo de vida de las cuentas": `tools unlock-user <correo>
  --as <correo>`, qué limpia y qué no, contadores en memoria, baja lógica y último admin; el
  cambio de correo cierra enlaces) y `DECISIONES.md` (S2-B5).
- Docker antes del gate (E1, como en B3 y B4: el bloque lleva la evidencia), sin tocar el árbol:
  `$DC build api` (cambió `cli.py`); la recarga por bind recogió el service. psql: un solo admin
  real vivo (más el técnico). Por Nginx `:8180` con `Origin` y un access del admin firmado dentro
  del contenedor del api:
  - preparación: `tools issue-reset-link coach-b3-smoke@test.apex --as <admin>` y
    `POST /auth/reset` 204 con una contraseña aleatoria que no se guardó; login del coach 200;
  - `GET /users/{coach}` 200 `active`; `PATCH {"role":"admin"}` 200 y de vuelta a coach 200;
  - `POST .../lock` 200 `locked` con `Cache-Control: no-store`; psql: `locked_at` y
    `tokens_valid_after` llenos, 0 refresh vivos de 2; login del coach 401
    `invalid_credentials` (el mismo mensaje);
  - `POST .../unlock` 200 `active`; psql `locked_at` nulo y `failed_login_count = 0`;
  - `tools unlock-user coach-b3-smoke@test.apex --as <admin>` sobre la cuenta ya desbloqueada:
    exit 2, "no hay una cuenta bloqueada con ese correo";
  - login del coach 200; `POST .../revoke-sessions` 200 `{"revoked":1}`;
  - `POST /users/{admin}/lock` 409 `cannot_lock_self`;
  - `DELETE` 204 con `Cache-Control: no-store`; segundo 404 `user_not_found`; `GET` 200
    `deleted`; `POST /users` con el mismo correo 201 (correo liberado);
  - auditoría: 6 `update` de `auth.users` para el coach (reset, dos `PATCH`, lock, unlock y
    baja); log del api: 0 coincidencias del correo; `/api/v1/health` 200.
- Coach de prueba que queda para los slices siguientes: `coach-b3-smoke@test.apex`, cuenta NUEVA
  (id `2d04a278-7af7-403b-8daa-9838b31076ac`), rol `coach`, `pending_activation`, con un token
  `activate` abierto 72 h (el token en claro se descartó). La cuenta anterior
  (`5b123624-...`) queda dada de baja.
- Observación sin cambio (previa a B5): las respuestas por Nginx llevan `Cache-Control:
  no-store` dos veces (la pone el api y la repite `infra/nginx/snippets/proxy-api.conf`); mismo
  valor, sin efecto.
- Desviaciones:
  - E1: el smoke de Docker corrió antes de los gates; tras los gates solo se repite `/health`.
  - El gate que sella lista también `tests/auth/test_auto_lock_last_admin.py` y
    `tests/auth/test_update_user_email_links.py` (nacieron en la revisión) y los dos de refresh
    (regresión por el candado usuario → token).
  - `login` (B2, `_register_failure`) y `update_user` cambian por la revisión (MEDIUM-1, LOW-3).
