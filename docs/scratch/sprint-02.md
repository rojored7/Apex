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

### S2-B6 · Rojo

- Línea base (HEAD `3597950`, árbol limpio): api 1283 ok y 4 saltadas (`-m 'not perf'`);
  `ruff check .` y `mypy src` (51 archivos) limpios.
- B6.1 stubs (`ruff` y `mypy src` limpios, 54 archivos):
  - `api/src/app/modules/audit/__init__.py` (sin `models.py`: la tabla vive en `core/audit.py`);
  - `router.py`: `router = APIRouter()` vacío (decisión 21);
  - `service.py`: `on_login_attempted`, `on_user_locked`, `on_sessions_revoked` y
    `on_password_changed(event, session) -> None` tipados con `NotImplementedError`, SIN
    suscribirse al bus. Importa de `auth.service` solo las cuatro clases de evento.
  - `MODULES` y `cli.py` no se tocan (son del Verde).
- B6.2 pruebas (41 casos nuevos):
  - `tests/audit/__init__.py`;
  - `tests/audit/test_security_events.py` (14): fila `login` ok y failed (la segunda sobrevive al
    rollback), correo inexistente sin filas, cinco fallidos con `account_limit=5` y el sexto 429
    sin fila, `lock` y `revoke_sessions` del admin, reuso de refresh y bloqueo automático con
    `SYSTEM_USER_ID`, `PasswordChanged` por `reset` (con `via_link_issued_by`) y por `change`,
    volcado sin contraseña, hash, refresh, su hash ni correo, `HandlerRoto` que revierte la fila
    `UserLocked` ya escrita y `verify_chain` íntegra;
  - `tests/auth/test_router_login_audit.py` (4): por HTTP desde `cliente_desde(IP_A)`, login ok y
    fallido con `ip` y `user_agent`, la fila del 401 sobrevive, sin el correo tecleado, cinco 401 y
    el sexto 429 (límite por IP) con cinco filas;
  - `tests/audit/test_reveal_entry.py` (1): `record(action="reveal", ...)` con `uuid4()`, sin
    `skip` (DECISIÓN 31);
  - `tests/architecture/test_audited_tables.py` (+10): `_cargar_modelos(modulos)` con `find_spec`,
    `REQUIRED_AUDITED_TABLES_V01`, `PENDING_AUDITED`, `_incumplidas()` y sus controles con clases
    falsas (pendiente presente sin `__audited__` falla; ausente o auditada no falla; requerida
    ausente o sin auditar falla);
  - `tests/architecture/test_audit_module.py` (9): `MODULES == ("auth","settings","audit")`, los
    cuatro handlers suscritos una vez tras `load_module_services()` (identidad de función),
    `router` vacío y sin `models.py`, `audit` sin imports prohibidos (`find_forbidden_imports`),
    `auth` sin ningún import de `audit` y el control del analizador;
  - `tests/cli/test_seed_cli.py` (+3): `seed`, `unlock-user` e `issue-reset-link` con éxito llaman
    a `load_module_services()` (espía sobre `app.main`, que delega en la real).
- Conteo: 1328 colectadas; 25 fallan, 1299 pasan, 4 saltadas. Las 25 son de B6 y todas por
  aserción de comportamiento (sin filas de evento, `MODULES` sin `audit`, handlers no suscritos,
  el CLI no carga los services); ninguna por `NotImplementedError`, import o fixture. Pasan ya
  16 nuevas: el correo inexistente sin filas, `reveal` (contrato de Sprint 1), las 10 de
  `test_audited_tables` y 4 de `test_audit_module` (router vacío, sin models, direcciones de
  import y control). Regresiones de la línea base: 0. `docs/openapi.json` sin cambios
  (`git diff --exit-code`). `db_test` queda sin usuarios, refresh, tokens, secciones ni filas de
  auditoría.
- Validación del Rojo: con una implementación provisional del Verde (handlers con `record`,
  `MODULES` con `audit` y `load_module_services()` perezoso en los tres comandos), luego
  revertida, la suite completa dio 1324 ok y 4 saltadas.
- Decisiones de prueba que el Verde debe respetar:
  - `on_login_attempted`: `record(action="login", table_name="auth.users",
    record_id=user_id, before=None, after={result, reason, ip, user_agent}, user_id=user_id)`;
    las claves de `after` son un subconjunto de esas cuatro (`reason` puede faltar o ser nula en
    el éxito); `user_agent` el del evento (ya truncado a 120). Nunca el correo.
  - `on_user_locked`: `action="update"`, `record_id=user_id`, `user_id=by`, `after ==
    {"event": "UserLocked", "reason": ...}` exacto. `on_sessions_revoked`: igual, `after ==
    {"event": "SessionsRevoked", "reason": ..., "revoked": n}` exacto.
  - `on_password_changed`: `action="update"`, `user_id=by`, `after.event = "PasswordChanged"`,
    `after.via` y `after.via_link_issued_by` (texto del UUID o `null`). L-13 manda sobre el
    blueprint 7.5 ("PasswordChanged sin suscriptores en v0.1").
  - Las filas de evento son `update` con `after.event`; el hook ORM sigue dejando su propio
    `update` (dos filas por bloqueo, a propósito). Ayuda nueva `es_update_del_hook(fila)` en
    `tests/auth/_cuentas.py`.
  - Los handlers se suscriben al importar `audit.service`; `load_module_services()` los deja una
    sola vez cada uno.
  - `cli.py`: `load_module_services()` por import perezoso de `app.main` dentro de los comandos
    (el espía se pone en el atributo de `app.main`).
- Pruebas existentes reparadas (por el contrato de B6, no por comportamiento): cuatro pruebas que
  contaban "todos los `update` de `auth.users`" esperando solo la fila del hook ahora filtran con
  `es_update_del_hook` (siguen exigiendo exactamente una): `test_change_password.py::
  test_la_auditoria_registra_el_update_con_el_hash_redactado`, `test_lock_unlock.py::
  test_lock_fija_locked_at_y_lo_audita_por_el_admin`, `test_reset_forgot.py::
  test_la_auditoria_deja_los_dos_updates_del_usuario_sin_el_token` y
  `test_update_delete_user.py::test_la_baja_es_logica_y_no_usa_session_delete`. Pasan igual en
  el Rojo; con el Verde provisional fallaban (2 o 3 `update` por las filas de evento).
- Desviaciones del encargo:
  - La prueba de `MODULES` y de suscripción vive en `tests/architecture/test_audit_module.py`
    (junto con las de dirección de imports), no en un `test_modules_loaded.py`.
  - El "sexto da 429" del service usa `account_limit=5` (el límite por cuenta corta antes de
    argon2); por HTTP es el límite por IP (`LOGIN_IP_LIMIT=5`).
  - La prueba de `HandlerRoto` falla en un handler de `SessionsRevoked` (posterior a
    `UserLocked`) y mira dentro de la transacción que la fila `UserLocked` ya existía: con el
    handler en `UserLocked` pasaría ya sobre los stubs (lo cubre `test_lock_unlock.py`).
  - `tests/audit/` no tiene `conftest.py`: el piso de login se anula con
    `pytestmark = usefixtures("sleeper_nulo")`.
  - `LIMPIEZA_DE_SESION` ya incluía `audit.audit_log` (verificado); la cadena se verifica entera
    dentro del savepoint de la prueba.

### S2-B6 · Verde

- Producto:
  - `api/src/app/modules/audit/service.py`: `on_login_attempted` (`login`, `after = {result,
    reason, ip, user_agent}`, `user_id` del propio usuario), `on_user_locked`,
    `on_sessions_revoked` y `on_password_changed` (`update` con `after.event`, `user_id = by`;
    `via_link_issued_by` como texto o `null`), con `core.audit.record` y suscritos con
    `events.subscribe` al final del módulo (idempotente).
  - `api/src/app/main.py`: `MODULES = ("auth", "settings", "audit")`.
  - `api/src/app/cli.py`: `_load_module_services()` (import perezoso de `app.main`) en `_seed`,
    `_issue_reset_link` y `_unlock_user`, tras instalar los listeners.
- Revisión (`security-reviewer`): sin CRITICAL ni HIGH; dos MEDIUM fijados con prueba
  (`tests/audit/test_security_events_review.py`, 2 casos: auditoría caída revierte el fallo
  entero; el último admin exento sigue cortado por IP) y nota en `docs/RUNBOOK.md`; cuatro LOW
  aceptados (DECISIONES S2-B6).
- Docs: `CLAUDE.md` (estructura de `audit/`), `docs/ddd/DECISIONES.md` (S2-B6),
  `docs/RUNBOOK.md` (sección S2-B6).
- Contrato: `export-openapi` y `git diff --exit-code docs/openapi.json` en verde; `types.ts` no
  se regenera.
- Suite (`-m 'not perf'`): 1330 colectadas, 1326 ok, 4 saltadas, 0 fallos; cobertura de `app`
  95 %; `ruff format`, `ruff check` y `mypy src` (54 archivos) limpios.

### S2-B7 · Rojo

- Línea base (HEAD `0fe9df3`, árbol limpio): api 1326 ok y 4 saltadas (`-m 'not perf'`);
  `ruff check .` y `mypy src` (54 archivos) limpios.
- B7.1 fábrica y limpieza:
  - `api/tests/factories/members.py`: `KNOWN` (`"7319582046"`, `"+57 300 765 4321"`,
    `"Lucia.Gomez@Correo.co"`, `date(1991, 7, 23)`, `{"name": "Rosa", "phone": "3115550199"}`),
    `KNOWN_NORMALIZED` (claro y normalizado como texto: lo que no puede aparecer en reposo),
    `make_member(session, **cambios)` (bajo `SYSTEM_USER_ID`, `Secret.from_plain`, `flush` y
    commit del savepoint; necesita `bus_listo`), `make_members(session, n)` con documentos únicos
    y `unique_document()`;
  - `FACTORIES["members.members"] = make_member`;
  - `tests/conftest.py`: `LIMPIAR_MEMBERS` (con `to_regclass`, inocuo sin la tabla) en
    `LIMPIEZA_DE_SESION` y en el `finally` de `dos_sesiones`;
  - `api/tests/members/{__init__,conftest,_apoyo}.py`: `bus_confirmado` (llaves con commit real
    para la carrera; al salir borra las llaves y las filas de `crypto_ops` desde su inicio),
    `cuerpo`, `entrada`, `crear`, `fila_socio`, `cuantos_socios`, `operaciones`,
    `CAMPOS_DETALLE` y `MASCARAS_KNOWN`.
- B7.2 stubs (`ruff` y `mypy src` limpios, 60 archivos), en `api/src/app/modules/members/`:
  - `models.py` completo: `Member(CommonColumnsMixin, SoftDeleteMixin, Base)`, esquema `members`,
    `__audited__`, `__audit_subject__ = "id"`, cinco `Encrypted`, tres `BlindIndexed`, CHECKs,
    único parcial e índices del blueprint; SIN `notes` y con `document_type` default `CC`;
  - `schemas.py` y `exceptions.py` completos (contrato): `MemberCreate` (`extra="forbid"`,
    `str_strip_whitespace`, `data_consent: bool = False`, sin `notes` ni `data_consent_at`),
    `EmergencyContactIn`, `MemberDetailOut`, `MemberRef`; `MemberError`,
    `MemberValidationError` (422), `MemberDocumentDuplicated` (409, `field="document"`,
    `existing_id`), `MemberNotFound` (404);
  - `service.py`: `MemberCreated(member_id)` y las firmas tipadas de `validate_member_input`,
    `compute_warnings`, `mask`, `create`, `get_ref`, `ensure_exists`, `id_by_document` y `count`
    con `NotImplementedError`;
  - `router.py`: `POST /members` con `require_role("admin", "coach")`, 201 y
    `response_model=MemberDetailOut`, que llama a `service.create`; las constantes del límite
    (`members-write`, 60, 60 s) quedan declaradas y el `enforce` lo pone el Verde (B7.5);
  - `MODULES`, `main.py`, `migrations/env.py` y la migración NO se tocan (Verde);
  - `tests/architecture/_imports.py`: `BANNED_MODULES`, `BannedImport`, `is_allowed(path)` y
    `find_banned_imports(source, path)` (`Import`, `ImportFrom` absoluto, `importlib.import_module`,
    `import_module` y `__import__` con literal, también dentro de funciones y de `TYPE_CHECKING`).
    Se escribió después de ver en rojo los casos de `test_import_analyzer.py`; queda verde.
- B7.3 pruebas (180 casos colectados nuevos o reemplazados):
  - `tests/members/test_member_rules.py` (72): `validate_member_input` (nombres, sexo, fecha; L-3
    con `"..."`, guiones tipográficos, `"+57"`, `"( ) -"` y correo en blanco), `compute_warnings`,
    `mask` (`CC •••• 0304`, `••• ••• 4567`, `l•••@•••.co`, `••/••/1991`, `"Registrado"`, `None`) y
    el contrato de `MemberCreate` (`extra_forbidden` para `notes`, `data_consent_at`,
    `data_consent_version`, `status` y `document_idx`);
  - `tests/members/test_service_create.py` (19): mismo índice con y sin puntos, 409 con
    `existing_id` sin crear nada, un dado de baja no bloquea, carrera con `dos_sesiones` y
    `bus_confirmado`, fila `insert` con blobs y `subject_member_id`, `MemberCreated`,
    `HandlerRoto` revierte, M-4 con el reloj movido 3 h, `warnings`, `crypto_ops` solo
    `encrypt`/`index` y ningún `decrypt`, 422 desde el service, `get_ref`, `ensure_exists`,
    `id_by_document` y `count`;
  - `tests/members/test_router_create.py` (21): 201 admin y coach, aviso sin autorización, cuerpo
    mínimo, 403 member, 401 sin token, 12 casos de 422 con `field` (incluidos `data_consent_at` y
    `notes`), 409, alta 61 que da 429 con `Retry-After` mientras otro usuario sigue, logs limpios;
  - arquitectura: `test_members_encrypted_at_rest.py` (4), `test_no_plaintext_at_rest.py` (6),
    `test_import_analyzer.py` (28), `test_banned_imports.py` reescrita sobre el analizador (4),
    `test_audited_tables.py` (`members.members` requerida, +1), `test_no_sensitive_in_logs.py`
    implementada (login real, alta, 409 y 422 con `capsys` y `caplog`; `reveal` aparte con
    `skip(reason="US-074, S3-B10")`) y `test_audit_module.py` (`MODULES` con `members`);
  - `tests/core/test_logging_redact.py` (+1): fila cruda, `repr`, extra e `IntegrityError` real;
  - `tests/migrations/test_0006_members.py` (27): columnas exactas, sin `notes` ni `*_hint`,
    defaults, CHECKs por SQLSTATE (incluido el claro en cada columna cifrada y los dos pares),
    nulos, único parcial con una baja que libera el documento, índices por `pg_indexes` y ciclo.
- Conteo: 1510 colectadas; 127 fallan (todas de B7), 1379 pasan, 4 saltadas. Motivos:
  `NotImplementedError` de los stubs (66: 52 reglas puras y 14 del service); ruta no montada,
  404 (22: router y centinela de logs); revisión `0006_members` inexistente (27);
  `members.members` inexistente, `UndefinedTable` (11: fábrica en service, arquitectura y log);
  aserción de contrato (1: `MODULES` sin `members`). Ninguna por import ni fixture; ninguna
  sesión queda colgada. Pasan ya 53 casos nuevos (contrato: schemas, analizador, descubrimiento
  de columnas, registro, banned imports, tablas auditadas). Regresiones de comportamiento: 0;
  `test_audit_module::test_modules_de_v01_incluye_audit_despues_de_auth` pasa a rojo a propósito
  (contrato B7). `docs/openapi.json` sin cambios.
- Validación del Rojo: con un Verde provisional (migración `0006` con el esquema de la prueba,
  service completo, `enforce` en el router, `MODULES` con `members` y el import en `env.py`),
  luego revertido (downgrade de `db_test` a `0005b` antes de borrar la revisión), la suite dio
  1505 ok, 4 saltadas y 1 fallo esperado (`test_docs_openapi_json_esta_al_dia`, P-API del Verde).
  `db_test` queda en `0005b_auth_security`, sin socios, usuarios, llaves ni secciones.
- Decisiones de prueba que el Verde debe respetar:
  - L-3: `"+57"` se normaliza a `"57"`, no a vacío (`normalize_for_index` solo quita el 57 con
    12 dígitos); `validate_member_input` necesita una regla de teléfono además del vacío (el
    provisional usó "menos de 7 dígitos"); `"(601) 555 0199"` y `"3007654321"` pasan.
  - `mask("document", ...)` usa los 4 últimos caracteres del valor normalizado (`"1.020.304"` da
    `CC •••• 0304`; `"AB-123456"` con `PA` da `PA •••• 3456`); teléfono: los 4 últimos dígitos;
    correo: primera letra, `•••@•••.` y la última etiqueta del dominio.
  - `validate_member_input` revisa también lo que el schema ya filtra (las pruebas usan
    `model_copy(update=...)`); por HTTP el `field` sale del schema (`first_name`, `sex`,
    `document_type`, `email`, `data_consent_at`, `notes`) o del service (`birth_date`, documento
    que se normaliza a vacío, `phone`).
  - `crypto_ops` del alta: solo `encrypt` (5 con todos los campos) e `index` (al menos 3) con el
    `record_id` del socio y `user_id` = actor; el pre-chequeo puede llevar o no `record_id`; cero
    `decrypt` nuevos.
  - `MemberCreated(member_id=...)` se emite con `events.emit` en la misma transacción; un handler
    que lanza deja el error y nada escrito tras el rollback.
  - El límite es `ratelimit.enforce("members-write", str(principal.user_id), limit=60,
    window_s=60)` antes del service; el 429 lleva `rate_limited` y `Retry-After`.
  - `test_no_sensitive_in_logs` reinstala `configure_logging` dentro de `capsys` y exige una
    línea `http_request` en el stdout capturado (si no, no probaría nada).
  - Agregar `from app.modules.members import models as _members` en `migrations/env.py`.
- Pruebas existentes reparadas (por el contrato de B7, no por comportamiento):
  - `tests/migrations/test_0005b_auth_security.py`: `..._y_es_head` pasa a
    `test_la_revision_existe_cuelga_de_0005_settings_y_esta_en_la_cadena_de_head`; con `0006`
    colgando de `0005b`, `get_heads() == ["0005b_auth_security"]` dejaría de valer. Ahora exige que
    esté en la cadena hasta head (la cabeza única sigue en `test_single_head`). Pasa en el Rojo y
    con el Verde provisional.
  - `test_audited_tables.py::test_una_pendiente_que_existe_auditada_no_falla` usa `plans.plans`
    como ejemplo (`members.members` ya es requerida).
- Desviaciones del encargo:
  - `no_store` no se exige en `POST /members`: el dependiente vive en `auth/cookies.py`, privado
    de `auth` (S2-D4, regla `private_helper`), y Nginx ya pone `Cache-Control: no-store` en
    `/api/` (`proxy-api.conf`). Si el Verde lo quiere, primero debe moverse a `core/`.
  - Topes de longitud que el blueprint no fija, elegidos para el contrato: nombres 100, teléfono
    30, parentesco 50 (documento de 3 a 30, como el blueprint).
  - `test_banned_imports.py` se reescribió sobre `find_banned_imports` (dos analizadores serían
    deriva); conserva sus casos (árbol real y `core/crypto`) y suma el control en `tmp_path` y la
    prueba de que el recorrido sí ve el bus.
  - `test_audited_tables::test_las_requeridas_de_v01_existen...` pasa en la suite completa del
    Rojo porque las pruebas importan `members.models` al recolectar; sola falla hasta que
    `MODULES` tenga `members` (lo exige `test_audit_module`).
  - `test_no_plaintext_at_rest` carga los `models.py` de todos los paquetes de `app.modules` (no
    solo `MODULES`) para descubrir columnas cifradas aunque el módulo aún no esté montado.

### S2-B7 · Verde

- Producto:
  - `api/migrations/versions/0006_members.py` (`down_revision = "0005b_auth_security"`): tabla
    `members.members` del blueprint sin `notes`, `document_type` default `'CC'`,
    `data_consent_at`/`data_consent_version` nulos, 12 CHECKs nombrados (`ck_members_*`), único
    parcial `uq_members_document_idx_alive` e índices `ix_members_phone_idx`,
    `ix_members_email_idx`, `ix_members_alive_last_name`; `downgrade` borra la tabla y deja el
    esquema (lo crea `0001`). `migrations/env.py` importa `app.modules.members.models`.
  - `members/service.py`: `validate_member_input` (L-3 con `normalize_for_index`; teléfono con al
    menos 7 dígitos), `compute_warnings`, `mask`, `create` (pre-chequeo por índice ciego,
    `Secret.from_plain`, `data_consent_at` del reloj, `begin_nested` + `flush`, traducción del
    `IntegrityError` del único, `refresh` de `created_at`/`updated_at`, `MemberCreated`,
    respuesta enmascarada desde la entrada) y `get_ref`, `ensure_exists`, `id_by_document`
    (`None` si el valor se normaliza a vacío), `count`.
  - `members/router.py`: `ratelimit.enforce("members-write", user_id, limit=60, window_s=60,
    kind="user")` antes del service (L-1). `main.py`: `MODULES` con `members`.
  - Revisión: `Member.__audit_redact__` con los tres índices ciegos (MEDIUM-1); máscara del
    documento sin cola con menos de 6 caracteres (LOW-2); `data_consent` estricto (LOW-5).
    Prueba nueva `tests/members/test_member_review.py` (10 casos, rojos antes del arreglo).
    LOW-3 y LOW-4 aceptados (DECISIONES S2-B7). `core/logging.py` no cambió.
- Migración por P-MIG: `docs/scratch/sprint-02-antes-0006_members.dump` (ignorado por `*.dump`);
  `stop api`; ciclo contra `db_test` (35 ok en `test_migrations`, `test_0006_members` y
  `test_0005b`); `alembic heads` = `0006_members (head)`; `start api` healthy;
  `alembic current` = `0006_members (head)`; ciclo `downgrade -1` (→ `0005b_auth_security`) y
  `upgrade head` en `apex-db-1`. Hallazgo al entrar: `apex-db-1` ya estaba en `0006_members` con
  la tabla del Verde provisional del QA (CHECKs con el nombre duplicado `ck_members_ck_members_*`,
  0 filas) y el api caído en el arranque por la revisión inexistente; el ciclo la recreó con la
  migración definitiva (`ck_members_*`).
- Contrato (P-API): `export-openapi` dos veces idénticas; `npm run gen:api` (+205 líneas en
  `types.ts`), `types.contract.test.ts` 5 ok y `tsc --noEmit` limpio.
- Suite (`-m 'not perf'`): 1520 colectadas, 1516 ok, 4 saltadas, 0 fallos; cobertura de `app`
  95 %; `ruff format`, `ruff check` y `mypy src` (60 archivos) limpios.
- Docker antes del gate (E1, como B3 a B5: el bloque nombra los socios de prueba), sin tocar el
  árbol; la recarga por bind recogió el código. Por Nginx `:8180` con `Origin` y un access
  firmado dentro del contenedor del api:
  - admin `POST /members` CC `1.020.304.417` → 201 con `CC •••• 4417` (los 4 últimos del
    normalizado `1020304417`), `••• ••• 0417`, `s•••@•••.apex`, `••/••/1990`, `Registrado`,
    `warnings: []` y `data_consent_at` del servidor;
  - el mismo alta → 409 `member_document_duplicated` con `existing_id`; `"1020304417"` sin
    puntos → 409 igual; sin token → 401 `unauthorized`; teléfono `"+57"` → 422 `field=phone`;
  - coach nuevo (`POST /users` → `POST /auth/reset` 204 con contraseña aleatoria descartada) →
    `POST /members` 201 con `warnings: ["data_consent_missing"]`;
  - 403 de `member`: no se probó en vivo (no hay cuentas `member` hasta el portal, L-2); lo
    cubren `test_router_create` y `test_every_route_has_role`;
  - psql: `document`, `phone`, `email` son blobs `apx1.<key_id>.A256GCM.`, `document_idx` HMAC
    hex; `row_to_json` de la tabla sin ninguno de los valores enviados (0 filas);
    `crypto.crypto_ops`: por socio 5 (o 3) `encrypt` y 3 `index` con su `record_id` y el actor
    (admin y coach), más el `index` del pre-chequeo sin `record_id`; ningún `decrypt`;
    `audit.audit_log`: un `insert` por socio con `subject_member_id`, `user_id` del actor, blob
    en `after.document` y `after.document_idx = ***`;
  - log del api: 0 coincidencias de documento, teléfono, correo, contacto, `apx1.` y correo del
    coach; `/api/v1/health` 200.
- Datos de prueba que quedan para B8 (listar): socios `2b5b6860-1db1-4699-a7ab-f25c85cc89d7`
  ("Prueba Smoke Uno", CC `1.020.304.417`, todos los campos, con autorización) y
  `8fbc42c3-eb59-4403-8e71-6bfba868800e` ("Prueba Smoke Dos", CC `52.000.418`, sin fecha ni
  contacto ni autorización); coach `coach-b7-smoke@test.apex`
  (`386a18f6-dff2-4490-b7ce-fb690fb085bd`, activo, contraseña descartada: para entrar,
  `tools issue-reset-link`).
- Desviaciones:
  - E1: el smoke de Docker corrió antes de los gates; tras los gates solo se repite `/health`.
  - El encargo esperaba `CC •••• 0417` para `1.020.304.417`; la regla que fijan las pruebas
    (4 últimos del normalizado) da `CC •••• 4417`. Manda la prueba.
  - El gate que sella lista también `tests/members/test_member_review.py` (nació en la revisión).

### S2-B8 · Rojo

- Línea base (HEAD `f85f24e`, árbol limpio): api 1516 ok y 4 saltadas (`-m 'not perf'`, 1520
  colectadas); `ruff check .` y `mypy src` (60 archivos) limpios.
- B8.1 marcador y stubs (`ruff format`, `ruff check` y `mypy src` limpios, 60 archivos):
  - `api/pyproject.toml`: marcador `perf` en `markers` (S2-D27). Con `--strict-markers`, sin él
    `test_list_perf.py` no colectaría. E8: el `up -d --build api` se hace una sola vez al cerrar
    B8 (no en el Rojo);
  - `members/schemas.py` completo: `MemberStatusFilter`, `MemberSort` (6 valores),
    `DEFAULT_MEMBER_SORT = "last_name"`, `MemberRowOut` (id, nombres, sexo, estado, `deleted_at`,
    `membership_status` y `plan_name` en `None`; nada sensible, N-01), `MemberListQuery`
    (`extra="forbid"`, congelado, `q` hasta `MAX_SEARCH_LENGTH`), `MemberName` (dataclass
    congelada con `sex`);
  - `members/service.py`: `QueryPlan(q, name_pattern, by_document, by_phone, by_email)`
    (dataclass congelada, completa), constantes `PHONE_DATA_CLASS`, `EMAIL_DATA_CLASS`,
    `LIKE_ESCAPE = "\\"`, y las firmas de `classify_query`, `list`, `search_ids` y `names_for`
    con `NotImplementedError`. `list` se llama como en el blueprint: dentro del módulo las
    anotaciones usan `builtins.list` (`compute_warnings`), si no mypy resuelve `list[...]` a la
    función;
  - `members/router.py`: `GET /members` con `require_role("admin", "coach")`,
    `Annotated[PageParams, Depends()]`, `q: SearchQuery`, `status` (alias de `member_status`),
    `sort`, `response_model=Page[MemberRowOut]`; `ratelimit.enforce("members-search",
    str(user_id), limit=60, window_s=60, kind="user")` solo si `q` no está vacío (L-1); arma
    `MemberListQuery` y llama a `service.list`.
- B8.2 pruebas (97 casos nuevos; 94 corren sin `perf`):
  - `tests/members/test_classify_query.py` (31): documento con puntos, guiones y espacios;
    pasaporte; teléfono con espacios, `+57` y paréntesis al mismo valor; 7 dígitos sí, 6 no;
    correo en mayúsculas; correo con dígitos no es documento; nombres (`góm`, `Góm`,
    `Laura Gómez`, `gom`) solo dan patrón; patrón recortado; `%`, `_`, `\` escapados; `...`,
    `+57`, `--`, `( )` sin índices; `None`/vacío/blanco dan el plan vacío; plan inmutable; los
    valores del plan dan el mismo índice ciego que el término (con `bus_listo`);
  - `tests/members/test_service_list.py` (34): documento con puntos, teléfono con y sin `+57`,
    correo en mayúsculas (Laura y la de `KNOWN`), sin coincidencias; nombre `góm`, `Góm`,
    `GÓMEZ`, `gom` y `laura gó`; varios por nombre; `%` y `_` no son comodines; sin `status`
    excluye bajas; `deleted`, `active`, `inactive`; una baja no aparece al buscarla salvo con
    `deleted`; cada `sort` (con `created_at` explícito) y el orden por defecto; paginación
    `limit`/`offset`/`total` sin repetir; filas con exactamente `CAMPOS_FILA` y sin claro,
    blob ni máscara; cero `decrypt`, de 1 a 3 `index` por búsqueda (una por clase, mismo
    `batch_id` no nulo, actor) y ninguno por nombre o sin `q`; `search_ids` en una sentencia
    (listener `before_cursor_execute` sin `SAVEPOINT`/`RELEASE`) y con o sin bajas;
    `names_for` en una sentencia, con bajas, sin el id inexistente, `[]` da `{}` e iterable;
  - `tests/members/test_router_list.py` (26): 200 admin y coach con el contrato y 25 por
    defecto; `status=deleted` para los dos (N-20); búsqueda por documento, teléfono, correo y
    nombre por HTTP; filas sin sensibles, `*_idx`, `*_hint`, claro ni máscara; 403 `member`
    (con y sin `q`); 401; 422 con `field` para `limit` 500/201/0/-1, `offset` -1, `sort`
    `foo`/`document`, `status` `foo` y `q` de 101; `limit=200` y `q` de 100 válidos; cada
    `sort` 200; 5 sin `q`, 60 con `q` y la 61 da 429 `rate_limited` con `Retry-After`, sin
    `q` y con `q=""` siguen en 200 y otro usuario sigue; el `q` (documento, teléfono, correo y
    un nombre) no aparece en stdout JSON (`capsys` con `configure_logging`) ni en `caplog`,
    tampoco tras un 422;
  - `tests/members/test_list_perf.py` (3, `pytestmark = pytest.mark.perf`): 999 socios con
    `make_members` más Laura, `ANALYZE`; tras un calentamiento `GET /members?q=1.020.304`
    < 500 ms; `EXPLAIN (FORMAT JSON)` de cada consulta con `document_idx` que el service envía
    (capturada con el listener y reenviada con `exec_driver_sql`) usa
    `uq_members_document_idx_alive`; L-11: 20 cuentas, 20 logins fallidos concurrentes, cada uno
    en su sesión de un motor con pool de 22 (`motor_amplio`), `rollback` como `get_session`,
    p95 < 2 s y cada cuenta con `failed_login_count = 1`; `dos_sesiones` siembra y limpia;
  - `tests/architecture/test_list_rows_without_sensitive_fields.py` (3): rutas efectivas
    (`effective_routes`) `GET` bajo `/api/v1/members` con respuesta `Page_...`; lee la fila en
    `app.openapi()` y falla con `document`, `phone`, `email`, `birth_date`,
    `emergency_contact`, `*_idx` o `*_hint`; exige ver `GET /api/v1/members`; control con
    `_FilaFalsa` (detecta 3), `_FilaLimpia`, un detalle y una lista fuera del prefijo.
- Conteo (`-m 'not perf'`): 1614 colectadas (1617 sin filtro, 3 deseleccionadas); 80 fallan,
  1530 pasan, 4 saltadas. Las 80: 79 nuevas por `NotImplementedError` de los stubs
  (`classify_query` 30, `list` 46, `names_for` 2, `search_ids` 1) y
  `test_openapi_export::test_docs_openapi_json_esta_al_dia` (la ruta nueva cambia el contrato;
  P-API en B8.4). Pasan ya 15 nuevas de contrato: 401, 403, los 9 casos de 422, `LIKE_ESCAPE`
  y las 3 de arquitectura. Ninguna por import ni fixture; ninguna sesión colgada.
  `-m 'not perf'` excluye `test_list_perf.py`; sin la variable se colecciona y da 2 fallos
  (`NotImplementedError` de `list`) y 1 pasa (L-11: mide B2, ya implementado).
- Validación del Rojo: con un Verde provisional del service (luego revertido desde la copia del
  stub) las 94 nuevas pasan, las 3 `perf` pasan (búsqueda 14,5 ms; L-11 p50 0,411 s, p95
  0,421 s por el piso de 400 ms) y la suite da 1609 ok, 4 saltadas y solo el fallo esperado de
  `docs/openapi.json`. `db_test` queda sin socios, usuarios `@test.apex`, llaves ni auditoría.
- Decisiones de prueba que el Verde debe respetar:
  - `QueryPlan` guarda VALORES NORMALIZADOS (no índices): `list` los pasa a
    `bus.blind_index(data_class, valor)`, que vuelve a normalizar (idempotente). Así
    `classify_query` sigue pura.
  - `name_pattern = "%" + escape(q.strip()) + "%"` con `LIKE_ESCAPE = "\\"` (escapar primero la
    barra). Las aserciones exactas usan términos en minúscula ASCII: el Verde puede plegar
    mayúsculas y tildes en SQL sobre columna y término.
  - `by_document` solo si el normalizado `generic` no queda vacío, tiene al menos un dígito y
    solo letras y dígitos ASCII (desviación 1).
  - Nombre sin tildes ni mayúsculas: `"gom"` y `"GÓMEZ"` encuentran a "Gómez" (`ILIKE` solo no
    basta: `'Gómez' ILIKE '%gom%'` es falso en `db_test`, `en_US.utf8`). El provisional usó
    `translate(lower(first_name || ' ' || last_name), 'áéíóúüñ', 'aeiouun')` a los dos lados,
    como US-079; sin migración.
  - La rama de documento debe llevar `deleted_at IS NULL` en la misma subconsulta para que el
    plan use el único parcial (lo exige el `EXPLAIN`).
  - `index` dentro de un único `bus.batch("index", None)` por llamada: una fila por clase con el
    mismo `batch_id`; una búsqueda por nombre o sin `q` no calcula ningún índice.
  - `status=deleted` = `deleted_at IS NOT NULL` (también inactivos); `active`/`inactive` = vivos
    con ese estado; sin `status` = vivos. Admin y coach por igual (N-20).
  - `search_ids(q)` con `q` en blanco da `set()`; `names_for([])` da `{}`; ambas una sola
    sentencia SQL cuando hay algo que buscar; `names_for` acepta cualquier iterable.
  - El límite cuenta solo con `q` no vacío; `q=""` no cuenta.
  - `MemberRowOut` tiene exactamente `id, first_name, last_name, sex, status, deleted_at,
    membership_status, plan_name`.
- Desviaciones del encargo:
  1. `by_document`: el blueprint dice "si `normalize_for_index(q, "generic")` no queda vacío";
     con eso `"góm"` (→ `gom`) y `"+57"` (el `+` se conserva) darían índice de documento, y el
     encargo pide que `"góm"` dé solo `name_pattern` y `"+57"` ningún índice. Se agregó "al menos
     un dígito y solo letras y dígitos" (los documentos CC, CE, TI y PA siempre los tienen). La
     búsqueda no cambia (un nombre nunca coincide con un índice de documento) y ahorra un HMAC
     por búsqueda de nombre. Debe anotarse en `DECISIONES.md` al cerrar B8.
  2. `"1.020.304"` también activa `by_phone` (tiene 7 dígitos): la caja es única y la regla de 7
     dígitos del blueprint lo implica; hay una prueba que lo fija.
  3. Nombre sin tildes (`"gom"`): el encargo dice "por `"góm"` sin tilde"; se toma como el término
     sin tilde (precedente US-079). Si no se quiere, quitar los casos `gom` de
     `test_service_list.py`.
  4. El `enforce` del límite ya queda en el router (no solo como stub), porque no depende del
     service; las pruebas del 429 fallan igual en el Rojo por `list`.
  5. L-11 pasa en el Rojo: mide el login de B2, ya implementado; se deja en el archivo `perf` como
     pide el plan.

### S2-B8 · Verde

- B8.3 `members/service.py`: `classify_query` (NFC, sin caracteres de control, recortado;
  `name_pattern` escapado; `by_document` solo letras y dígitos ASCII con al menos un dígito;
  `by_phone` con 7 o más dígitos; `by_email` si hay `@`), `_indices` (un único
  `bus.batch("index", None)`, solo si hay algún valor), `_ramas` (una subconsulta de ids por
  índice y una por nombre con `translate(lower(...))` a los dos lados y `ESCAPE '\'`, cada una
  con su condición de baja), `list` (`select(Member)` con `load_only` de las columnas en claro,
  filtro de estado, `id IN (UNION ...)`, orden de `sort` con desempate por el otro nombre y
  `paginate`), `search_ids` (una sentencia) y `names_for` (una sentencia; `[]` da `{}` sin
  consulta). Router y schemas sin cambios respecto del Rojo.
- B8.4 contrato: `export-openapi` dos veces idéntico; `docs/openapi.json` (+300 líneas: ruta y
  `Page_MemberRowOut_`) y `web/src/core/api/types.ts` regenerados;
  `types.contract.test.ts` 5 ok; `tsc --noEmit` limpio.
- Revisión (`security-reviewer`): 0 CRITICAL, 0 HIGH, 2 MEDIUM, 4 LOW. Corregidos con prueba
  MEDIUM-1 (`q` con NUL daba 500) y LOW-4 (NFC) en `tests/members/test_list_review.py`
  (11 casos, 8 rojos antes del arreglo, incluida la regresión del escape `\`, `100%` y `a_b`
  contra PostgreSQL). Aceptados MEDIUM-2, LOW-1, LOW-2 y LOW-3 (`DECISIONES.md`, S2-B8).
- Docs: `DECISIONES.md` sección "S2-B8" (las cuatro decisiones del orquestador, forma de la
  consulta, revisión); `docs/RUNBOOK.md` "Socios: buscar y listar (S2-B8)" (qué usa índice y
  qué no; `uv run pytest -m perf`).
- Números: `-m 'not perf'` 1621 ok, 4 saltadas, 3 deseleccionadas, 0 fallos; cobertura `app`
  96 % (`members/service.py` 97 %). `-m perf` 3 ok: búsqueda por documento con 1.000 socios
  13,5 ms; L-11 p50 0,407 s, p95 0,417 s. `ruff format`, `ruff check` y `mypy src` (60
  archivos) limpios.
- Deuda conocida (Sprint 4A): la rama de nombre no usa índice (`pg_trgm` o columna normalizada
  si la tabla crece). Pendiente fuera de alcance: el mismo NUL en `q` de `auth.list_users`
  (contrato común `SearchQuery`).

### S2-B9 · Rojo

- Línea base (HEAD `3e7ec24`, árbol limpio): api 1621 ok, 4 saltadas, 3 deseleccionadas
  (`-m 'not perf'`, 1625 colectadas); `ruff check .` y `mypy src` (60 archivos) limpios.
- B9.1 fábrica y limpieza:
  - `api/tests/factories/plans.py`: `make_plan(session, **cambios)` ("Mensual", 120.000, 30 días,
    `days`, activo; bajo `actor_scope(SYSTEM_USER_ID)`, `flush` y commit del savepoint; sin bus) y
    `make_plans(session, n)` (`Plan 000`, `Plan 001`, ...); `FACTORIES["plans.plans"]`;
  - `tests/conftest.py`: `LIMPIAR_PLANS` (con `to_regclass`, inocuo sin la tabla) en
    `LIMPIEZA_DE_SESION` y en el `finally` de `dos_sesiones`;
  - `api/tests/plans/{__init__,_apoyo}.py`: `PLANS`, `CAMPOS_PLAN`, `cuerpo`, `tiquetera`,
    `entrada`, `crear`, `fila_plan`, `cuantos_planes`.
- B9.2 stubs (`ruff` y `mypy src` limpios, 66 archivos), en `api/src/app/modules/plans/`:
  - `models.py` completo: `Plan(CommonColumnsMixin, SoftDeleteMixin, Base)`, esquema `plans`,
    `__audited__`, cinco CHECKs nombrados, `uq_plans_name_alive` sobre
    `lower(btrim(name)) WHERE deleted_at IS NULL` (`NAME_ALIVE_INDEX`) e `ix_plans_active_alive`;
  - `schemas.py` y `exceptions.py` completos (contrato): `PlanCreate` (`StrictInt` y topes de
    S2-D32 como constantes), `PlanOut`, `PlanSnapshot` (dataclass congelada), `PlanListQuery`;
    `PlanError`, `PlanValidationError` (422), `PlanNameDuplicated` (409, `field="name"`,
    `existing_id`), `PlanNotFound` (404), `PlanScopeForbidden` (403 `forbidden`);
  - `service.py`: `PlanCreated(plan_id)` y las firmas de `validate_plan`, `ensure_list_scope`,
    `ensure_read_scope`, `create`, `list`, `detail`, `get`, `get_including_deleted` y
    `names_for` con `NotImplementedError`;
  - `router.py`: `POST /plans` (`require_role("admin")`, 201), `GET /plans` y
    `GET /plans/{plan_id}` (`require_role("admin", "coach")`, `PageParams`, `q: SearchQuery`,
    `active`); llama al service;
  - NO se tocan `MODULES`, `main.py`, `migrations/env.py`, la migración ni `core/pagination.py`.
- B9.3 pruebas (222 colectadas nuevas en neto):
  - `tests/plans/test_validate_plan.py` (55): `validate_plan` (`days` con clases, también 0;
    `classes` sin clases, 0, negativo o 1.001; `duration_days` 0, negativo o 3.651; bordes
    válidos; mensaje sin el valor) y el contrato de `PlanCreate` (`StrictInt`: `120000.5`,
    `120000.0`, `"120000"`, `true`; topes; nombre recortado, blanco, 81; `kind`; `extra`);
  - `tests/plans/test_scope_rules.py` (16): admin todo; coach solo `active=True`; coach sobre
    inactivo; `member` nunca; `PlanScopeForbidden` es 403 `forbidden`;
  - `tests/plans/test_service_create.py` (15): "Mensual" y "Tiquetera 12", `created_at` y
    `updated_at` iguales a la fila (refresh), nombre recortado, fila `insert` de auditoría con
    `table_name='plans.plans'` y el actor, `PlanCreated`, `HandlerRoto` revierte (sin plan ni
    auditoría), 409 con `existing_id` para "Mensual", "mensual", "  MENSUAL  " y "MeNsUaL", un
    dado de baja libera el nombre, carrera con `dos_sesiones` ("Carrera" contra "carrera"), 422
    `class_count` desde el service;
  - `tests/plans/test_router_create.py` (25): 201 admin con `price_cop` entero; 403 coach y
    `member`; 401; 19 casos de 422 con `field` (precio decimal, negativo, cero, texto, booleano,
    1.000.000.001 y ausente; días 0, 3.651 y texto; clases 0 y 1.001; `days` con clases y
    `classes` sin clases; nombre blanco y de 81; `kind`; `is_active` y `created_by` extra); 409;
  - `tests/plans/test_service_list.py` (35): vivos en orden de nombre, `active` True/False, sin
    dados de baja, coach con y sin `active=True`, `q` (`TRIMES`, `promo`, `promocion` y
    `PROMOCIÓN` encuentran "Promoción", `ménsual` encuentra "Mensual", recortado, inactivo),
    `q` vacío, comodines `100%`, `a_b`, `\` y `%`, `q` con `active`, paginación sin repetir,
    `ORDER BY name ... id` (listener), `get` da `PlanSnapshot` (inactivo sí; baja o inexistente
    404), `get_including_deleted`, `for_share` con `FOR SHARE` en el SQL y candado real (un
    `UPDATE` de otra sesión con `lock_timeout` da 55P03), `names_for` en una sentencia con bajas
    y sin inexistentes, `[]` sin consultar, iterable con repetidos;
  - `tests/plans/test_router_list.py` (29): admin 200 con el contrato (activos e inactivos),
    `active=false`, coach `active=true` 200, coach sin parámetro, con `false` o solo `q` 403,
    búsqueda por HTTP, `member` 403 y 401 en las dos rutas, 422 con `field` (`limit` 500/201/0,
    `offset` -1, `active=talvez`, `q` de 101), `q` con `\x00`/`\x1f` 422 `field=q`, `limit=200`;
    detalle: activo 200 para los dos, inactivo 403 coach y 200 admin, baja o inexistente 404
    `plan_not_found`, id no UUID 422 `field=plan_id`;
  - `tests/migrations/test_0007_plans.py` (31): padre `0006_members` y head, columnas exactas,
    defaults, filas válidas (incluidos topes), 13 CHECKs por SQLSTATE, 6 obligatorias, único sin
    distinguir mayúsculas ni espacios (5 casos), la baja libera el nombre, índices por
    `pg_indexes`, ciclo;
  - arquitectura: `test_audited_tables.py` (`plans.plans` requerida y fuera de pendientes; nueva
    `test_plans_es_requerida_y_su_modulo_esta_en_modules`; el ejemplo de pendiente auditada pasa
    a `memberships.memberships`), `test_audit_module.py` (`MODULES` con `plans`),
    `test_service_import_graph.py` (`plans` sin aristas en ningún sentido),
    `test_list_routes_use_page_params.py` (exige `GET /users`, `/members` y `/plans`).
- Deuda de B8 que B9 cierra (NUL en `q`): `tests/core/test_pagination_router.py` (+11: `\x00`,
  `\x1f`, `\x01`, `\x07` dan 422 `field=q`; tilde, espacios, comodines, teléfono, correo y bordes
  siguen en 200), `tests/auth/test_users_list_router.py` (+3: `GET /users?q=a%00b`, `%00` y
  `a%1Fb` dan 422, hoy 500) y `tests/members/test_list_review.py` (la prueba que esperaba 200
  pasa a `test_un_q_con_caracteres_de_control_por_http_da_422_y_no_500`, 2 casos). `SearchQuery`
  queda como estaba para que fallen en rojo.
- Prueba reparada por contrato: `tests/migrations/test_0006_members.py::..._y_es_head` pasa a
  `test_la_revision_existe_cuelga_de_0005b_y_esta_en_la_cadena_de_head` (con `0007` colgando de
  `0006`, `get_heads() == ["0006_members"]` dejaría de valer; como en B7 con `0005b`).
- Conteo (`-m 'not perf'`): 1847 colectadas (1850 sin filtro, 3 deseleccionadas); 183 fallan,
  1660 pasan, 4 saltadas. Las 183: `tests/plans` 139 y `test_0007_plans.py` 31 (por
  `NotImplementedError` de los stubs, `relation "plans.plans" does not exist`, revisión
  `0007_plans` inexistente y rutas no montadas que dan 404), deuda del NUL 10 (5 de
  `SearchQuery`, 3 de `/users` con 500 y 2 de `/members` con 200) y arquitectura 3 (`MODULES`
  sin `plans`, `plans.plans` requerida sin módulo, `GET /plans` no recogida). Ninguna por import
  ni fixture. Pasan ya 43 nuevas: 35 de contrato de `PlanCreate`, 1 de `PlanScopeForbidden`, 6
  de `q` válido y 1 del grafo de services. Regresiones de comportamiento: 0.
- Validación del Rojo: con un Verde provisional (migración `0007_plans`, service completo,
  `MODULES` con `plans`, import en `env.py` y `SearchQuery` con `pattern=r"^[^\x00-\x1f]*$"`),
  revertido después (downgrade de `db_test` a `0006_members` antes de borrar la revisión), la
  suite dio 1841 ok, 4 saltadas y 2 fallos: `test_docs_openapi_json_esta_al_dia` (esperado,
  P-API de B9.6) y `test_los_checks_rechazan_por_sql_crudo[classes-sin-clases]`, que destapó un
  defecto del blueprint (abajo). `db_test` queda en `0006_members`, sin `plans.plans`, socios,
  usuarios `@test.apex`, llaves, auditoría ni secciones.
- Decisiones de prueba que el Verde debe respetar:
  - CHECK de clases: el del blueprint, `(kind = 'classes' AND class_count > 0) OR (kind = 'days'
    AND class_count IS NULL)`, ACEPTA `classes` con `class_count` nulo (`NULL > 0` es NULL,
    `TRUE AND NULL` es NULL y un CHECK con NULL pasa). La migración debe usar
    `(kind = 'classes' AND class_count IS NOT NULL AND class_count > 0) OR (kind = 'days' AND
    class_count IS NULL)`, como ya dice `models.py`. Anotar en `DECISIONES.md` (S2-B9).
  - NUL en `q` (deuda de S2-B8, MEDIUM-1): `core/pagination.SearchQuery` rechaza los caracteres
    de control C0 (`\x00` a `\x1f`) con 422 `field=q` en TODAS las listas (`/users`, `/members`,
    `/plans`), antes del service; el provisional usó `Query(pattern=r"^[^\x00-\x1f]*$")`. Cambia
    el OpenAPI de las tres listas (P-API). `classify_query` de `members` conserva su limpieza
    como defensa en profundidad para quien llame al service directo. Las pruebas no fijan
    `\x7f` ni el rango C1: si el Verde rechaza toda la categoría `Cc`, también cumple. Anotar en
    `DECISIONES.md` cerrando el pendiente de S2-B8.
  - `GET /plans/{plan_id}` necesita `PlanOut` (con `created_at`), que `PlanSnapshot` no trae: el
    stub agrega `service.detail(session, plan_id, *, role) -> PlanOut` (`get` + `ensure_read_scope`
    y la fila). Orden: baja o inexistente da 404 antes que el 403 del coach.
  - `ensure_list_scope` y `ensure_read_scope` cierran también para `member` (la ruta ya lo frena
    con `require_role`).
  - La búsqueda pliega mayúsculas y tildes en SQL a los dos lados (`translate(lower(...))`,
    US-079) y escapa `\`, `%` y `_`; `q` vacío o en blanco no filtra.
  - `create` recorta el nombre aunque llegue sin validar (`model_copy`); el pre-chequeo y el
    único comparan `lower(btrim(name))`; `PlanNameDuplicated.existing_id` puede ser `None` en la
    carrera; `refresh` de `created_at` y `updated_at`; `created_by` lo pone el actor.
  - `names_for([])` da `{}` sin tocar la base; con ids, una sola sentencia sobre `plans.plans`.
  - Agregar `from app.modules.plans import models as _plans` en `migrations/env.py`.
- Desviaciones del encargo:
  1. `service.detail` no está en el blueprint (ver arriba): sin él, el router tendría que leer el
     ORM o devolver el snapshot sin fechas.
  2. La prueba HTTP del NUL de socios vive en `tests/members/test_list_review.py` (ahí estaba la
     que esperaba 200), no en `test_router_list.py`.
  3. `GET /plans?q=<NUL>` se fija en 422 `field=q` (el encargo admitía "200 o 422"): es lo que da
     el contrato común una vez cerrada la deuda.
  4. `models.py` lleva el CHECK de clases corregido (no el literal del blueprint).

### S2-B9 · Verde

- B9.4 migración `0007_plans` (P-MIG): `pg_dump -Fc` a `docs/scratch/sprint-02-antes-0007_plans.dump`
  (ignorado por `*.dump`); `stop api`; `api/migrations/versions/0007_plans.py`
  (`down_revision = "0006_members"`, tabla `plans.plans` con los cinco CHECKs nombrados, el de
  clases con `class_count IS NOT NULL`, `uq_plans_name_alive` sobre `lower(btrim(name))` donde
  `deleted_at IS NULL` e `ix_plans_active_alive`; `downgrade` `drop_table`); import de
  `plans.models` en `migrations/env.py`; contra `db_test` `test_migrations.py` y
  `test_0007_plans.py` 34 ok; `alembic heads` = `0007_plans (head)`; `start api` healthy;
  `alembic current` = `0007_plans (head)`; ciclo `downgrade -1` (→ `0006_members`) y
  `upgrade head` en `apex-db-1`. Hallazgo al entrar: `apex-db-1` ya estaba en `0007_plans` con la
  tabla del Verde provisional del QA (CHECK de clases sin `IS NOT NULL`, 0 filas) y el api caído
  en el arranque ("Can't locate revision 0007_plans"); el ciclo la recreó con la definitiva
  (`ck_plans_class_count_by_kind` con `class_count IS NOT NULL`).
- B9.5 Verde: `plans/service.py` completo (`validate_plan`, `ensure_list_scope` y
  `ensure_read_scope` cerrando por defecto, también a `member`; `create` con NFC y recorte,
  pre-chequeo `lower(btrim(...))` en SQL a los dos lados, `begin_nested()` con traducción del
  `IntegrityError` de `uq_plans_name_alive`, `refresh` y `PlanCreated`; `list` con
  `translate(lower(...))` y `ESCAPE '\'`, orden `name, id`; `detail` en una sentencia, 404 antes
  que 403; `get` con `FOR SHARE` opcional; `get_including_deleted`; `names_for` en una
  sentencia). `MODULES = ("auth", "settings", "audit", "members", "plans")`.
  `core/pagination.SearchQuery` con `pattern=SEARCH_PATTERN` (`^[^\x00-\x1f\x7f-\x9f]*$`, toda
  la categoría `Cc`): cierra la deuda del NUL de S2-B8 en `/users`, `/members` y `/plans`.
  `members._limpio` solo cambia su docstring (defensa en profundidad).
- Revisión (`security-reviewer` sobre `git diff 3e7ec24 -- api/src api/migrations` y los nuevos):
  0 CRITICAL, 0 HIGH, 1 MEDIUM, 4 LOW. Corregidos con prueba MEDIUM-1 (`name` con NUL daba 500;
  U+200B pasaba el CHECK; NFC) y LOW-1 (`PlanListQuery.q` con `SEARCH_PATTERN`) en
  `tests/plans/test_plan_review.py` (14 casos, 10 rojos antes del arreglo). Aceptados LOW-2
  (403 frente a 404 del coach), LOW-3 (`existing_id` solo para el admin) y LOW-4 (búsqueda sin
  índice). Ver `DECISIONES.md`, S2-B9.
- B9.6 contrato (P-API): `export-openapi` dos veces idéntico; `docs/openapi.json` (+541 líneas:
  rutas de planes, `PlanCreate`, `PlanOut`, `Page_PlanOut_` y el `pattern` de `q` en las tres
  listas) y `web/src/core/api/types.ts` regenerados; `types.contract.test.ts` 5 ok;
  `tsc --noEmit` limpio. Con este slice el contrato queda definitivo para el front (F6 lo toma
  por rebase).
- Números: `-m 'not perf'` 1856 ok, 4 saltadas, 3 deseleccionadas, 0 fallos; cobertura `app`
  96 % (`plans/service.py` 94 %, `schemas.py` 97 %, `router.py` 100 %); `ruff format`,
  `ruff check` y `mypy src` (66 archivos) limpios.
- Docs: `DECISIONES.md` sección "S2-B9"; `sprint-02-blueprint.md` S2-B9 con el CHECK corregido y
  la nota; `docs/RUNBOOK.md` "Planes (S2-B9)". `CLAUDE.md` sin cambios (la carpeta `plans/` ya
  figura).
- Docker antes del gate (E1, como B7: el bloque nombra los planes que quedan), sin tocar el
  árbol; la recarga por bind recogió el código. Por Nginx `:8180` con `Origin` y accesos
  firmados dentro del contenedor del api (admin y `coach-b7-smoke@test.apex`):
  - admin `POST /plans` "Mensual" ($ 120.000, `days`, 30) → 201 con `"price_cop":120000`;
    "mensual" → 409 `plan_name_duplicated` con `field=name` y `existing_id` de "Mensual";
    "Tiquetera 12" (`classes`, 30 días, 12 clases, $ 150.000) → 201; `classes` sin
    `class_count` → 422 `field=class_count`; `GET /plans` → 200 con los dos (`total` 2);
  - coach `GET /plans?active=true` → 200 con los dos; `GET /plans` → 403 `forbidden`;
    `POST /plans` → 403;
  - admin `GET /users?q=a%00b` → 422 `field=q` (antes 500: deuda cerrada);
  - psql: `audit.audit_log` con dos `insert` de `plans.plans` con el admin como `user_id`;
    `\d plans.plans` con los cinco CHECKs `ck_plans_*` (el de clases con `IS NOT NULL`),
    `uq_plans_name_alive` UNIQUE sobre `lower(btrim(name)) WHERE deleted_at IS NULL` e
    `ix_plans_active_alive`; `/api/v1/health` 200.
- Datos de prueba que quedan (B9 del front y Sprint 3): planes
  `37aca240-de9b-4857-9dca-da75656309b1` ("Mensual", $ 120.000, `days`, 30 días) y
  `4ce6c6da-8fc6-4e92-bb56-2930f0e13186` ("Tiquetera 12", $ 150.000, `classes`, 30 días, 12
  clases), activos.
- Desviaciones:
  - E1: el smoke de Docker corrió antes de los gates (como B7 y B8); tras los gates solo se repite
    `/health`.
  - `SearchQuery` rechaza toda la categoría `Cc` (también U+007F a U+009F), no solo C0: lo admitían
    las decisiones del Rojo y coincide con la limpieza de `classify_query`.
  - El gate que sella lista también `tests/plans/test_plan_review.py` (nació en la revisión).
  - El script de firma quedó en `/tmp/firmar.py` del contenedor del api (sin secretos; el usuario
    del contenedor no puede borrar lo que copió `docker cp`); desaparece al recrear el contenedor.

## Validación del sprint (V2–V9)

Rama en `981836a` al entrar (B1–B9 y F1–F8 fusionados, árbol limpio). Alias
`DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"`. Informes
de Playwright, capturas y logs en el scratchpad de la sesión (fuera del repo). Sin credenciales
en este bloque: el admin del E2E sale de `.env.seed` solo en la shell.

### V2 · Stack desde cero de código
- `$DC build api web` (25 s) y `$DC up -d`: api y web recreados; `tools init-keys`: KEK, firma y
  par JWT "ya existe". api y web `healthy`.
- `alembic current` = `0007_plans (head)`; `downgrade -1` → `0006_members`; `upgrade head` →
  `0007_plans (head)`; `uv run alembic heads`: una sola cabeza (`0007_plans`).
- `curl` por 8180: `/api/v1/health` 200 `{"status":"ok","db":"ok","version":"dev"}`; `/` 200.
- Efecto anotado: el `downgrade` de `0007_plans` borra `plans.plans`, así que los planes de B9
  ("Mensual" `37aca240-…` y "Tiquetera 12" `4ce6c6da-…`) desaparecieron. "Tiquetera 12" se
  recreó por el api (`03cb58f6-13bb-4f66-84ec-81b5ade2e215`, $ 150.000, `classes`, 30 días, 12
  clases). Un spec de diagnóstico creó por error el plan "mensual" ($ 320.000, 90 días,
  `37f1e7d4-9952-4201-b2b8-0a2a4c733a0d`); no hay edición ni baja de planes en S2, así que queda
  y "Mensual" responde 409. La demo (V7) creó "Mensual <marca>" ($ 120.000, 30 días).

### V3 · Datos reales
- `auth.users` vivos: `admin@ejemplo.local` (admin), `coach-b3-smoke@test.apex` y
  `coach-b7-smoke@test.apex` (coach), `system@apex.local`; todos con `must_change_password = f`
  (las specs no necesitan cambiar la contraseña).
- `settings.settings_sections`: `gym` versión 2. `members.members`: 2. `plans.plans`: 0 (por el
  ciclo de V2).

### Smoke de producción previo a V4 (E5)
- `.env` local sin líneas de límites (rigen los defaults de `Settings`: `LOGIN_IP_LIMIT=5`…).
- Seis logins fallidos por 8180 con `Origin`: cinco 401 `invalid_credentials` y el sexto 429
  `rate_limited`.
- `scripts/ci/web-smoke.sh`: 5 ok, 0 fallas. `scripts/smoke/headers.sh`: 29 ok, 0 fallas (la
  ráfaga de 45 POST dio 45 respuestas 429: la zona ya estaba gastada por el smoke anterior).

### V4 · E2E contra el stack
- Perfil E2E en `.env` (bloque marcado, al final): `LOGIN_IP_LIMIT=1000`,
  `LOGIN_ACCOUNT_LIMIT=1000`, `LOGIN_ACCOUNT_GLOBAL_LIMIT=10000`, `LOGIN_LOCK_AFTER=1000`,
  `REFRESH_IP_LIMIT=1000`, `RESET_IP_LIMIT=1000`, `FORGOT_IP_LIMIT=1000`, `LOGOUT_IP_LIMIT=1000`;
  `$DC up -d api` y comprobado con `env` dentro del contenedor.
- Corridas antes de corregir (`--project=stack`, 25 pruebas):
  - 1 (8 workers): 5 ok, 17 fallos, 3 sin correr. 2 (8 workers, zona repuesta): 7 ok, 15 fallos.
    3 (`--workers=1`): 11 ok, 11 fallos, 3 sin correr.
  - Causas: (a) 429 del borde de Nginx (`limit_req` 60r/m, ráfaga 30) aun con el perfil del api:
    todo el host llega a Nginx con una IP (`172.30.0.128`, la puerta de enlace) y cada carga de
    la SPA hace `POST /auth/refresh` y `GET /auth/me`; en serie, 46 peticiones a
    `/api/v1/auth/` en 20 s (log de Nginx). Cada spec, sola, pasaba. (b) `captures.spec.ts`
    esperaba el `h1` "APEX" de la página estática de W0-1 (desde F3 `/` lleva a `/login`).
    (c) `plans.spec.ts`: axe `color-contrast` 4,22:1 en "Crear plan" medido a mitad de la
    transición de hover (120 ms); el estado final cumple (blanco sobre `#0077ad`).
- Correcciones (clasificación):
  - Entorno/prueba (a): zona `apex_auth` a `infra/nginx/snippets/auth-zone.conf` (60r/m, la de
    la imagen) e `infra/compose.e2e.yml`, que monta `infra/nginx/e2e/auth-zone.conf` (6000r/m)
    solo en V4 y en el job `e2e-stack`. Rojo primero: `test_nginx_conf.sh` 5 fallas y
    `test_compose_config.sh` 2 fallas; Verde: 0 y 0 (la ráfaga funcional sigue con 31 pasan y 14
    reciben 429). `$DC build web` y `$DC -f infra/compose.e2e.yml up -d web`.
  - Prueba (b): `captures.spec.ts` captura el login (siempre claro: `AccessLayout` fuerza el
    claro, así que solo cuatro capturas) y el Inicio con sesión en claro y oscuro (la elección
    del panel vive en `apex.theme`; `prefers-color-scheme` solo no lo oscurece). Asegura
    `data-theme` y que no haya desborde.
  - Prueba (c): `esperarTransiciones(page)` en `helpers/stack.ts` (espera `Animation.finished`)
    antes de cada axe en las seis specs que lo usan.
  - Producto: el saludo "Hola, admin@ejemplo.local" desbordaba 96 px a 320 px (texto sin puntos de
    corte; `scrollWidth` 416). `PageHeader.module.css` `.title` con `overflow-wrap: anywhere`;
    tras `$DC build web`, `scrollWidth` 320. Lo vigila `captures.spec.ts`.
  - CI: el job `e2e-stack` corría sin el perfil E2E del api (cinco logins por minuto) y sin
    `E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD` (`datosDeBase()` lanza). Ahora `sed` sube los topes en
    la copia del `.env`, `DC` apila `compose.e2e.yml` y el paso de Playwright exporta el admin del
    `.env.seed` efímero con `add-mask`.
  - No adoptado: `storageState` de E5 (el refresh rota y su reuso fuera de la gracia revoca todas
    las sesiones del usuario). Ver `DECISIONES.md`, S2-V.
- Resultado final, dos corridas seguidas (`E2E_BASE_URL=http://localhost:8180`, 8 workers):
  **29 ok, 0 fallos, 0 saltadas** en cada una (7,0 s y 6,7 s), 0 respuestas 429 en el log de
  Nginx. Pasaron en las dos: `captures` (cabeceras, 4 login, 8 Inicio), `login` (4),
  `logout-expired` (1), `members` (1), `plans` (2), `refresh-two-tabs` (1), `settings-gym` (5),
  `users-activation` (1), `users-manage` (1). 12 capturas: `login-light-{320,768,1024,1440}` e
  `inicio-{light,dark}-{320,768,1024,1440}`.
- `--project=preview` completo: **101 ok, 0 fallos** (24 s).
- Spec `role-guards` del stack: no existe (la de `vite preview` cubre la matriz con el api
  simulado; en el stack lo cubren `settings-gym`, `plans` y `users-activation` con coach real).
- Restauración: bloque del perfil borrado; `.env` idéntico byte a byte a la copia previa
  (`cmp`); `$DC up -d api web` (web sin `compose.e2e.yml`): 0 variables de límites en el api y
  `rate=60r/m` en `/etc/nginx/snippets/auth-zone.conf`. Sexto login fallido otra vez: cinco 401
  y 429 `rate_limited`.

### V5 · Rendimiento
- `uv run pytest -m perf tests/members/test_list_perf.py -q` (con `TEST_DATABASE_URL`): 3 ok en
  20 s (dos corridas). Búsqueda por documento con 1.000 socios: 12,1 ms; `EXPLAIN` con
  `uq_members_document_idx_alive` (aserción de la prueba); L-11, 20 logins fallidos
  concurrentes: p50 0,390 s, p95 0,399 s, máx. 0,401 s.

### V6 · Smoke con evidencia SQL
- `members.members`: `document` = `apx1.cfcd75b0-b1b6-4…` (blob de 106 caracteres),
  `document_idx` = `04504d1e3db9b0fa6f4d…` (HMAC).
- `audit.audit_log` de `auth.users`, últimas 10 por `seq`: `login` (695, 689, 688, 687, 683),
  `update` (694, 692, 686, 684) e `insert` (690); `password_hash` = `***` en las filas que lo
  traen y vacío en las demás. Totales: 54 `insert`, 282 `login`, 170 `update`; 0 filas con un
  `password_hash` distinto de `***` en toda la auditoría.
- `auth.one_time_tokens.token_hash` = `412d10e382ad18ac991b…` (64 hex: hash).
- `crypto.crypto_ops` por verbo: `encrypt` 30, `index` 52, `unwrap` 1288, **0 `decrypt`**.
- `core.audit.verify_chain` sobre `audit.audit_log` completa en orden de `seq` (script por stdin
  en el contenedor del api; no hay comando del CLI): `ok=True`, 695 de 695 filas, sin ruptura.

### V7 · Demo (8 puntos de `SPRINT-02.md`, por la API en 8180)
1. `GET /login` 200 con `#root` y CSP con nonce; capturas del login en los cuatro anchos (el
   login es siempre claro por diseño, así que "en tema oscuro" no aplica).
2. Admin `POST /users` (coach) 201 con `activation_url` `http://localhost:8180/restablecer/<token>`
   y vencimiento a 72 h; `POST /auth/reset` 204 sin abrir sesión; el mismo enlace otra vez 400
   `invalid_token`; login del coach 200.
3. Coach: `GET /settings/gym`, `/settings/privacy` y `/users` → 403 `forbidden` ("Sin permiso" en
   la pantalla lo prueba `settings-gym.spec.ts`).
4. Sexto intento fallido → 429 `rate_limited` (antes y después de V4). Refresh del coach 200;
   reuso del rotado dentro de la gracia → 401 `invalid_refresh` y la sesión sigue (refresh 200);
   reuso del rotado a los 11 s → 401 `invalid_refresh` y el refresh vigente queda revocado (401).
5. `PATCH /settings/gym` 200 (versión 14 → 15), `PATCH /settings/privacy` 200 con la versión
   nueva, `expiring_days=31` → 422 `field=value.expiring_days`, `expiring_days=7` → 200; el
   `GET /auth/me` del coach trae `gym_name` actualizado.
6. CC 1.020.304.417 ya existía (corrida anterior): `POST` → 409 `member_document_duplicated` con
   `existing_id`; búsqueda por documento → 1. Con un socio nuevo (201): búsqueda por documento,
   teléfono y apellido → 1 cada una. SQL del blob `apx1.` y el HMAC en V6.
7. "Mensual <marca>" ($ 120.000, 30 días) 201 con `price_cop=120000`; en mayúsculas, con espacios
   en los extremos y "Mensual" → 409 `plan_name_duplicated` con `existing_id`; coach
   `GET /plans?active=true` 200 (15, todos activos) y `GET /plans` 403.
8. Auditoría de `auth.users` con `login`, `insert` y `update` y `password_hash` `***` (V6).

### V8 · Repetición
- `tools seed` dos veces: "omitido: ya existe un admin activo" las dos.
- `tools init-keys` dos veces: las tres llaves "ya existe".
- `export-openapi` dos veces: idénticas entre sí e idénticas a `docs/openapi.json`.
- `SMOKE_KEEP=1 bash scripts/ci/compose-smoke.sh` (con el `.env.seed` local existente): verde en
  47 s; db, db_test, api y web healthy, seed omitido, api sin `ADMIN_*`, web en `172.30.0.10` =
  `TRUSTED_PROXIES`, `web-smoke` 0 fallas, `headers` 0 fallas.

### V9 · Gates completos
- `PYTEST_ADDOPTS="-m 'not perf'" bash scripts/workflow/run-gates.sh`: verde en 247 s. api: ruff,
  formato y mypy limpios; 1856 ok, 4 saltadas, 3 deseleccionadas; cobertura `app` 95,56 %. web:
  lint, tsc, 1676 pruebas en 105 archivos (cobertura 99,71 % de líneas) y build.
- `uv run pytest tests/architecture -q`: 142 ok, 1 saltada (US-074, S3-B10).
- `uvx pre-commit run --all-files`: la primera pasada falló en `end-of-file-fixer` (un archivo
  editado en V4 quedó sin salto final; el hook lo arregló); la segunda, verde.
- `bash scripts/workflow/tests/run.sh`: 5 de 5 archivos en verde.
- `bash scripts/ci/check-licenses-api.sh`: todas en la lista; `npm run licenses`: MIT 12, ISC 1.
- gitleaks sobre el historial: 68 commits, "no leaks found".
- `check-image-secrets.sh apex-api:local`: 0 fallas (incluye `gitleaks dir`);
  `test_api_image.sh apex-api:local`: 0 fallas.
- Además: `test_nginx_conf.sh` 0 fallas, `test_compose_config.sh` 0 fallas,
  `test_check_key_files.sh` 0 fallas, `bash -n` de `scripts/ci/*.sh` limpio.

### Commits de la validación
- `961e0d6` fix(infra): perfil E2E del borde (zona `limit_req` montable) y job `e2e-stack` con
  topes y admin del seed (`test_nginx_conf.sh`, `test_compose_config.sh`; docs `DECISIONES.md`
  S2-V, `RUNBOOK.md`, `CLAUDE.md`, `.env.example`).
- El siguiente checkpoint: `PageHeader` sin desborde y specs del stack reparadas, más este bloque.

### Estado al terminar
- `.env` de producción restaurado (idéntico a la copia previa). Stack `apex` arriba: db, db_test,
  api y web healthy en 8180/8181/5442/5443; web con la zona de producción (60r/m).
- Datos de prueba nuevos: coaches `coach-*@apex.test` de las specs y `coach-demo-*@test.apex` de
  la demo (este con sus sesiones revocadas), socios "Demo …" y los de las specs, planes
  "Trimestral <marca>", "Mensual <marca>", "mensual" y "Tiquetera 12", política `demo-<marca>`,
  `gym_name` "APEX CrossFit Demo <marca>".
