# Sprint 0 · Terreno, gates y esqueleto ejecutable

- Versión: v0.1.
- Épicas: EP-00 completa y lo mínimo de EP-01.
- Tamaño: 17 historias, 48 puntos y 203 h relativas (EP-00, 124 h; EP-01 mínimo, 79 h).
- Rama: `chore/sprint-00-cimientos`, creada después del commit inicial (ajuste A-02 del README).
- Historias del sprint: US-001, US-002, US-003, US-004, US-005, US-006, US-007, US-008, US-009, US-010, US-011, US-012, US-013, US-014, US-017, US-018, US-020.

## Objetivo

Que cualquier agente o persona clone el repositorio y, con un solo comando, levante el stack con `/health` en verde y una base PostgreSQL 16 de prueba. En ese estado:
- las pruebas corren;
- la CI rechaza lint, tipos, licencias prohibidas e imports de criptografía fuera del bus;
- los cuatro scripts de gate quedan disponibles para todos los sprints siguientes.

## Demo al final del sprint

1. `docker compose -f infra/compose.yml -f infra/compose.dev.yml up -d --build` deja `db`, `db_test`, `api` y `web` en estado `healthy`.
2. `curl -s http://localhost/health` y `curl -s http://localhost/api/v1/health` (por Nginx) responden 200 con `db` y `version`.
3. `docker compose exec api uv run alembic current` muestra `0001_core_schemas`. En la base existen los nueve esquemas y la extensión `btree_gist`.
4. `cd api && uv run pytest` pasa contra `db_test`, con la suite de arquitectura en verde.
5. Escribir `import hashlib` en `src/app/modules/x/service.py` hace fallar `uv run ruff check .` con `TID251`.
6. Un PR de prueba corre en la CI los jobs `api`, `web`, `images`, `scripts` y licencias, todos en verde.
7. `http://localhost` sirve el build del front: tokens de diseño, fuentes locales y los componentes `Button`, `Field` y `StatusTag`.
8. `scripts/workflow/slice-gate.sh core/config` escribe el sello, y `scripts/workflow/checkpoint-commit.sh` rechaza la rama `main`.

## Dependencias de sprints anteriores

Ninguna: es el primer sprint.

Bloqueos previos, que deben quedar resueltos antes de la primera wave:
- **Gate humano de `DECISIONES.md` sección A.** Sin la aprobación de D1/S1 no se puede reescribir el "Alcance" de `CLAUDE.md`, y `CLAUDE.md` manda pedir confirmación cuando el plan lo contradice. Quedan confirmados así:
  - D1: front en `web/`;
  - D2: paginación con `limit` y `offset`;
  - D5: vender y renovar por `sell`;
  - P5: correo de login en claro;
  - P7: solo LAN en v0.1;
  - la estructura de tres épicas de núcleo.
- **Ajuste A-02:** commit inicial en `main` y creación de la rama del sprint.

## Historias en orden de ejecución

### Tarea documental previa (T-DOC, bloqueante)

Correcciones que imponen `DECISIONES.md` secciones C y E. La ejecuta el orquestador, o el agente `doc-updater`, antes de la Wave 0, porque los agentes de las waves leen `CLAUDE.md` como regla. No usa `slice-gate.sh` (todavía no existe); se cierra con un commit `docs: aplica correcciones de DECISIONES C y E`.

1. **`CLAUDE.md`:**
   - "Alcance": el front se construye y se mantiene en `web/` dentro de este flujo (D1).
   - Estructura: agregar `core/context.py` (G-01), `core/clock.py`, `core/jobs.py` (G-06), `core/alerts.py` (G-08), `core/crypto/registry.py`, `core/crypto/digest.py` y `core/crypto/archive.py` (G-07).
   - Reglas de módulos: agregar la regla 2 bis de dependencias mutuas entre services (G-03), con la lista blanca de v0.1 (memberships↔payments, members↔memberships, plans↔memberships) y la de v0.4 (members↔classes).
   - Reglas de módulos: dejar dicho que un módulo puede importar `schemas.py` y `exceptions.py` de otro (refinamiento de US-022).
   - Bus de criptografía, regla 5: la normalización del índice ciego de N-02.
   - Licencias: agregar `PSF-2.0`, `0BSD`, `ISC` y `OFL-1.1` (N-49 y US-004). MPL-2.0 sin modificar se acepta también para `certifi` y `axe-core`.
   - Seguridad: Telegram es solo canal interno del equipo (N-34).
2. **`docs/ddd/02_domain_model.md`:**
   - invariante de una membresía vigente y una futura (Q1);
   - `compute_status` con `expiring_days` y la fecha de Bogotá (Q11, Q28);
   - `apply_freeze` con límites (Q9) y `MembershipFreeze` (N-25);
   - `is_current` e `is_primary` (Q18, Q19);
   - récord de benchmark (Q20);
   - web push en v1.0 (Q14).
3. **`docs/ddd/05_service_design.md`:**
   - quitar `renew` como endpoint (Q2);
   - `reveal` también para coach (Q6);
   - secciones de Settings (Q11);
   - puerto `PrincipalLoader` en la tabla de puertos (G-02).
4. **`docs/ddd/03_context_map.md` sección 5:** lecturas a profundidad 2, por lote y sin escrituras (G-04).
5. **`docs/PLAN.md`:**
   - Tarea 6 (renovar);
   - v0.2: el push sale;
   - v0.3: el CBOM entra;
   - v1.0: el CBOM sale.
6. **`docs/BRECHAS.md`:** marcar como resueltas D3, D4 y las de la sección 3 que cierran estas decisiones.
7. **`docs/design/`:**
   - chip "Pendiente de pago" (Q3);
   - paginación `limit`/`offset` en `DESIGN.md` y `ROUTES.md` (D2).
8. **Historias de `07_user_stories/`:** alinearlas con las contradicciones que resuelve el README del desglose:
   - `SYSTEM_ACTOR_ID` pasa a `SYSTEM_USER_ID` (N-15);
   - nombres de variables de entorno;
   - permisos `members.*`;
   - `broken_at_seq`;
   - `notifications_today`;
   - 409 `membership_cancelled`;
   - rangos de N-18;
   - Telegram como canal interno.
9. **Verificación por grep:**
   - `grep -n "memberships/{id}/renew" docs/ddd/05_service_design.md docs/PLAN.md` no devuelve endpoints vigentes;
   - `grep -n "SYSTEM_ACTOR_ID" -r docs/ddd/07_user_stories` no devuelve nada;
   - `grep -n "core/context.py" CLAUDE.md` devuelve la línea nueva.

### Wave 0 · Infraestructura (`devops-wsl2-docker`)

Hasta que exista US-008, cada slice se verifica a mano con los comandos de su "Definición de hecho" y se confirma con un commit normal. Desde S0-W0-2, todos los slices usan los gates.

- **Slice S0-W0-1 · Repositorio y proyecto api.** Historias: US-001 y US-002.
  - US-001:
    - estructura del repositorio;
    - `.gitattributes` con `eol=lf` en `*.sh` y `*.woff2 binary`;
    - protección de `main`, documentada para GitHub.
  - US-002:
    - `api/pyproject.toml` con uv;
    - ruff con `flake8-tidy-imports` y `banned-api` (`cryptography`, `oqs`, `hashlib`, `hmac`, `jwt`, `argon2`);
    - `mypy --strict`;
    - pytest con `asyncio_mode=auto`;
    - `.pre-commit-config.yaml`;
    - `api/tests/test_smoke.py`.
  - Verificación manual: `cd api && uv sync && uv run ruff check . && uv run mypy src && uv run pytest`.
- **Slice S0-W0-2 · Scripts de gate.** Historia: US-008, con el ajuste A-01 (`web/<feature>`).
  - Crea `slice-gate.sh`, `checkpoint-commit.sh`, `run-gates.sh` y `validate-impact-analysis.sh`.
  - Las pruebas de los scripts van en `scripts/workflow/tests/`.
  - `validate-impact-analysis.sh`:
    - acepta VERDE, APROBADO y APROBADO CON OBSERVACIONES;
    - acepta AMARILLO solo con `--allow-amber`;
    - rechaza ROJO y RECHAZADO (refinamiento de US-008, aceptado).
  - Gate: `bash scripts/workflow/tests/run.sh`. Es el primer `checkpoint-commit.sh` del proyecto.
- **Slice S0-W0-3 · CI y licencias.** Historias: US-003 y US-004.
  - `.github/workflows/ci.yml` con los jobs `api` (PostgreSQL 16 de servicio y `TEST_DATABASE_URL`), `images`, `web` y `scripts`.
  - `pip-licenses --allow-only` con la lista ampliada (refinamiento de US-004) y `NOTICE`.
  - Gate: `slice-gate.sh core` sobre `tests/test_ci_database.py` y `tests/architecture`. La CI se valida en un PR de prueba.
  - Criterio diferido, cerrado en la fase de validación de este sprint: el paso `licencias-web` necesita `web/package.json` (US-009).
- **Slice S0-W0-4 · Imagen del api, Compose y entorno.** Historias: US-005 y US-007.
  - `api/Dockerfile`: multi-stage con uv, usuario no root y `tzdata`.
  - `infra/compose.yml` con `web`, `api`, `db`, `worker` (detrás de `profiles: ["worker"]`), `backup` y `tools`.
  - `infra/compose.dev.yml` con puertos, hot reload y `db_test`.
  - `scripts/ci/compose-smoke.sh`.
  - `.env.example` completo, con los nombres de US-011: `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`, `ENV`, `TRUSTED_PROXIES`, `COOKIE_SECURE` y `FRONT_BASE_URL`.
  - README de arranque.
  - Gate: `slice-gate.sh core` sobre `tests/test_main_placeholder.py` y `tests/core/test_env_example.py`.
  - Criterios diferidos:
    - el healthcheck `healthy` del api con la app real se cierra en este sprint con US-020;
    - el servicio `tools` con `cli init-keys` y la medición completa del arranque (T6 de US-007) se cierran en el Sprint 1 con US-023;
    - quitar `profiles: ["worker"]` se cierra en el Sprint 4 con US-113.
- **Slice S0-W0-5 · Nginx e imagen del front.** Historia: US-006.
  - `infra/nginx/default.conf`:
    - proxy de `/api/` a `api:8000`;
    - `client_max_body_size 5m`;
    - `X-Forwarded-For` sobrescrito con `$remote_addr`;
    - `try_files`.
  - La imagen se construye con un `web/index.html` provisional.
  - Criterio diferido, cerrado en la fase de validación de este sprint: servir el build real (US-009) y que el proxy devuelva el 200 real de `/api/v1/health` (US-020).
  - Criterio diferido al Sprint 1: el endurecimiento con cabeceras y CSP lo hace US-038.

### Wave 3a · Tests de backend en rojo (`backend-qa-executor`)

Pruebas que se escriben antes de cada slice de la Wave 3b:
- **S0-B1:**
  - `tests/core/test_config.py`;
  - `tests/core/test_config_error_message.py`;
  - `tests/core/test_env_example.py`;
  - `tests/core/test_clock.py`;
  - `tests/architecture/test_no_os_environ.py`;
  - `tests/architecture/test_no_direct_now.py`.
- **S0-B2:**
  - `tests/core/test_db.py`;
  - `tests/core/test_migrations.py`;
  - `tests/core/test_session_dependency.py`;
  - `tests/architecture/test_no_create_all.py`.
- **S0-B3:**
  - `tests/core/test_errors_field.py`;
  - `tests/core/test_errors_router.py`;
  - `tests/core/test_logging_redact.py`;
  - `tests/core/test_logging_sql.py`;
  - `tests/core/test_logging_access.py`;
  - `tests/architecture/test_error_responses_in_openapi.py`;
  - `tests/architecture/test_no_sensitive_in_logs.py`.
- **S0-B4:**
  - `tests/core/test_events.py`;
  - `tests/core/test_events_db.py`;
  - `tests/core/test_events_router.py`;
  - `tests/core/test_health.py`;
  - `tests/core/test_migration_lock.py`;
  - `tests/core/test_startup_failure.py`;
  - `tests/architecture/test_routes_under_api_v1.py`;
  - `tests/architecture/test_core_import_direction.py`, en su primera versión: `core` no importa `app.modules`.

### Wave 3b · Implementación de backend (`backend-implementor`)

- **Slice S0-B1 · Configuración y reloj.** Historias: US-011 y US-013.
  - `core/config.py`:
    - `Settings` con pydantic-settings y `extra="forbid"`;
    - lista `NON_API_ENV_VARS`;
    - `DATABASE_URL` como `SecretStr`;
    - `CORS_ORIGINS` como `list[str]`.
  - `core/clock.py`:
    - `Clock`, `SystemClock` y `FrozenClock`;
    - `today_bogota()` (Q28).
  - Gate: `slice-gate.sh core/config && slice-gate.sh core/clock`.
- **Slice S0-B2 · Base de datos y Alembic multiesquema.** Historia: US-012.
  - Engine async con `hide_parameters=True`.
  - `Base` y `CommonColumnsMixin`, con el UUID asignado en Python antes del flush.
  - `migrations/env.py` multiesquema.
  - **Migración `0001_core_schemas`:** los esquemas `audit`, `crypto`, `auth`, `settings`, `members`, `plans`, `memberships`, `payments` y `worker`, más `CREATE EXTENSION btree_gist`.
  - Gate: `slice-gate.sh core/db`, más el ciclo `alembic upgrade head && downgrade -1 && upgrade head`.
  - Criterio diferido al Sprint 1: `created_by` lo llena el `before_flush` de US-016; hasta entonces las pruebas lo asignan a mano.
- **Slice S0-B3 · Envelope de errores y logs JSON.** Historias: US-017 y US-018.
  - `core/errors.py`, con `{ error: { code, message, field?, existing_id? } }` y `ERROR_RESPONSES`.
  - `core/logging.py`, con JSON a stdout, redacción y `RequestLogMiddleware`.
  - `core/context.py` se crea solo con `request_id_var`, como prevén las dos historias. US-016 lo completa (G-01).
  - Gate: `slice-gate.sh core/errors && slice-gate.sh core/logging`.
  - Criterio diferido: la prueba T8 de US-018 (redacción con datos reales) se activa cuando llegan US-042 (Sprint 2), US-069 (Sprint 2) y US-074 (Sprint 3), como prevé el desglose.
- **Slice S0-B4 · Bus de eventos y `create_app`.** Historias: US-014 y US-020.
  - `core/events.py`, con `subscribe` y `emit` en la misma sesión.
  - `create_app()`:
    - `alembic upgrade head` al arrancar, con `pg_advisory_lock`;
    - `load_module_services()`;
    - `register_error_handlers`;
    - punto de extensión `register_health_check`.
  - `GET /health` y `GET /api/v1/health`.
  - `/docs` apagado en producción (N-14).
  - Gate: `slice-gate.sh core/events && slice-gate.sh core/main`.
  - Criterio diferido al Sprint 1: la llamada a `install_audit_listeners()` y `actor_scope(SYSTEM_USER_ID)` las conecta US-016, que es dueña de esas funciones.
  - Criterios diferidos al Sprint 4: los campos `backup` de `/health` y el arranque ordenado se agregan con US-115 y US-118.

### Wave 5a · Tests de front en rojo (`frontend-qa-automation`)

- **S0-F1:**
  - `src/core/styles/tokens.test.ts`;
  - `src/App.test.tsx`;
  - `tests/lint/lint-controls.test.ts`;
  - `tests/e2e/smoke.spec.ts`.
- **S0-F2:** pruebas de `src/shared/ui` para `Button`, `Field` y `StatusTag`, con axe.

### Wave 5b · Implementación de front (`frontend-ux-engineer`)

- **Slice S0-F1 · Esqueleto del front.** Historia: US-009.
  - Vite, React 19 y TypeScript estricto.
  - `tokens.css` copiado del diseño y fuentes locales (`fonts.css`).
  - Lint que prohíbe colores fuera de los tokens.
  - Vitest con jsdom y Playwright base.
  - Proxy de Vite a `/api` en desarrollo.
  - Gate: `slice-gate.sh web/app` (A-01), o `run-gates.sh`.
- **Slice S0-F2 · Componentes base.** Historia: US-010.
  - `Button`, `Field` y `StatusTag` accesibles.
  - `axe-core` como MPL-2.0 sin modificar.
  - Gate: `slice-gate.sh web/shared`.

### Validación del sprint

- Se cierran los criterios diferidos dentro del sprint:
  - el paso `licencias-web` de US-004;
  - el build real servido por Nginx y el proxy a `/api/v1/health` de US-006;
  - el healthcheck `healthy` de US-005.
- `run-gates.sh` en verde.
- `docker compose -f infra/compose.yml up -d --build` y `scripts/ci/compose-smoke.sh`.
- `npx playwright test tests/e2e/smoke.spec.ts` contra el stack.
- La CI completa en un PR de la rama del sprint.

## Migraciones que aplica

- `0001_core_schemas` (US-012).

## Endpoints que expone

- `GET /health` (lista blanca; US-020).
- `GET /api/v1/health` (lista blanca; US-020).

## Tests de arquitectura que deben pasar

- `tests/architecture/test_ruff_banned_api.py` (US-002).
- `tests/architecture/test_banned_imports.py`, primera versión (US-002, según la dependencia de US-011). Se amplía en los Sprints 1, 2 y 4.
- `tests/architecture/test_no_os_environ.py` (US-011).
- `tests/architecture/test_no_create_all.py` (US-012).
- `tests/architecture/test_no_direct_now.py` (US-013).
- `tests/architecture/test_core_import_direction.py`, primera versión (US-014): `core` no importa `app.modules`.
- `tests/architecture/test_error_responses_in_openapi.py` (US-017).
- `tests/architecture/test_no_sensitive_in_logs.py` (US-018).
- `tests/architecture/test_routes_under_api_v1.py` (US-020).
- La suite de los scripts de gate, `scripts/workflow/tests/test_permisos.sh` (US-008): modo `100755`, `bash -n` y ningún `git push`.

## Riesgos y mitigación

1. [HIGH] El gate humano no aprueba D1, o cambia otra decisión de la sección A.
   - Mitigación: T-DOC es la primera tarea y bloquea.
   - Si D1 no pasa, salen US-009 y US-010 del alcance de agentes, el Sprint 0 cierra solo con backend e infraestructura, y se re-planean las Waves 5.
2. [MEDIUM] Arranque en frío: los gates no existen hasta S0-W0-2.
   - Mitigación: los dos primeros slices se verifican a mano con los comandos exactos de su "Definición de hecho", y la evidencia queda en el reporte.
3. [MEDIUM] Los criterios diferidos de US-005, US-006, US-007 y US-020 pueden dar una falsa sensación de "hecho".
   - Mitigación: cada uno está nombrado en este archivo y en el reporte de cierre, con el sprint que lo cierra.
4. [MEDIUM] Docker Desktop sobre WSL2: rendimiento de volúmenes y fines de línea en los `*.sh`.
   - Mitigación: `.gitattributes` con `eol=lf` (US-001), `git update-index --chmod=+x` (US-008) y verificación de los scripts en Git Bash anotada en el PR.
5. [LOW] `pip-licenses` falla desde la primera corrida por `typing_extensions` (PSF-2.0).
   - Mitigación: la lista ampliada de US-004 ya entra en T-DOC.

## Definición de hecho del sprint

- T-DOC confirmado. La verificación por grep de T-DOC no devuelve resultados inesperados.
- Cada slice tiene su `checkpoint-commit.sh`, salvo S0-W0-1, que se confirma con un commit normal y evidencia manual.
- `scripts/workflow/run-gates.sh` en verde: api con cobertura del 80 % sobre `src/app/core`, y front con lint, tsc, test y build.
- `bash scripts/workflow/tests/run.sh` en verde.
- `cd api && uv run pytest tests/architecture -q` en verde.
- `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`.
- Licencias en verde para el api y para el front. `NOTICE` presente.
- Smoke: `docker compose -f infra/compose.yml up -d --build`, `scripts/ci/compose-smoke.sh`, y `curl` a `/health` y `/api/v1/health` por Nginx con 200.
- E2E: `npx playwright test tests/e2e/smoke.spec.ts`.
- Seguridad, revisada por `security-reviewer`:
  - imagen del api con usuario no root;
  - sin `.env` ni llaves en la imagen;
  - `.dockerignore` completo;
  - `banned-api` activo;
  - ningún script ejecuta `git push`, `--force` ni `--no-verify`;
  - `/docs` apagado con `ENV=production`.
- `verify-delivery` con evidencia de la demo, incluida la salida de `alembic current` y la lista de esquemas en la base.
