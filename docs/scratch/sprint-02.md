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
