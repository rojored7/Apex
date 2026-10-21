# Sprint 0 · Terreno, gates y esqueleto ejecutable

- Versión: v0.1.
- Épicas: EP-00 completa y lo mínimo de EP-01.
- Tamaño: 17 historias, 48 puntos, 203 h relativas (EP-00: 124 h; EP-01 mínimo: 79 h).
- Rama: `chore/sprint-00-cimientos`, creada desde el `main` actual (ajuste A-02 del README).
- Historias del sprint: US-001, US-002, US-003, US-004, US-005, US-006, US-007, US-008, US-009, US-010, US-011, US-012, US-013, US-014, US-017, US-018, US-020.

## Objetivo

Que cualquier agente o persona clone el repositorio y, con un solo comando, levante el stack con `/health` en verde y un PostgreSQL 16 de prueba. Al cerrar el sprint:
- las pruebas corren;
- CI rechaza lint, tipos, licencias prohibidas e imports de criptografía fuera del bus;
- los cuatro scripts de gate, con el mapeo de A-01, quedan disponibles para todos los sprints siguientes.

## Demo al final del sprint

Todos los comandos se corren desde la raíz del repositorio. `docker compose` abrevia `docker compose -f infra/compose.yml -f infra/compose.dev.yml` (convención del README).

1. `docker compose up -d --build` deja `db`, `db_test`, `api` y `web` en estado `healthy`.
2. `curl -s http://localhost:${WEB_PORT:-80}/health` y `curl -s http://localhost:${WEB_PORT:-80}/api/v1/health` responden 200 por Nginx, con `db` y `version`.
3. `docker compose exec api alembic current` muestra `0001_core_schemas`. En la base existen los nueve esquemas y la extensión `btree_gist`.
4. En el host, `cd api && uv run pytest` pasa contra `db_test` con `TEST_DATABASE_URL`, y la suite de arquitectura queda en verde.
5. `import hashlib` en `src/app/modules/x/service.py` hace fallar `uv run ruff check .` con `TID251`.
6. Un PR de la rama muestra en CI los jobs `api`, `web`, `images`, `scripts` y licencias en verde. El push y el PR los hace una persona (A-02).
7. `http://localhost:${WEB_PORT:-80}` sirve el build del front, con tokens, fuentes locales, `Button`, `Field` y `StatusTag`.
8. `scripts/workflow/slice-gate.sh core/config tests/core/test_config.py` ejecuta el archivo y `tests/architecture`, y escribe el sello. `scripts/workflow/checkpoint-commit.sh` rechaza `main`.

## Dependencias de sprints anteriores

Ninguna: es el primer sprint.

Bloqueos previos a la primera wave:
- **Gate humano de `DECISIONES.md` sección A.** Sin la aprobación de D1/S1 no se puede reescribir el "Alcance" de `CLAUDE.md`, y `CLAUDE.md` exige preguntar cuando el plan lo contradice. Se confirman también:
  - D2 (`limit`/`offset`);
  - D5 (vender y renovar con `sell`);
  - P5 (correo de login en claro);
  - P7 (solo LAN en v0.1);
  - la estructura de tres épicas de núcleo.
- **Ajuste A-02:** rama desde `main` y `git status` limpio.

## Historias en orden de ejecución

Patrón de v0.1 (README, "Cómo se cierra un sprint"): en cada slice se escriben primero sus pruebas en rojo, sobre stubs vacíos; después se implementa y se pasa el gate con la lista de archivos del slice, que incluye siempre `tests/architecture`; al final va el checkpoint. Las waves 3a/3b y 5a/5b se alternan por slice. No se deja en rojo la wave completa.

### Tarea documental previa (T-DOC, bloqueante)

Aplica las correcciones de `DECISIONES.md` secciones C y E. La ejecuta el orquestador, o `doc-updater`, en la rama del sprint y antes de la Wave 0, porque los agentes de las waves leen `CLAUDE.md` como regla. Se cierra con un commit normal (todavía no hay gates): `docs: aplica correcciones de DECISIONES C y E`.

1. **`CLAUDE.md`:**
   - **Alcance:** el front se construye y se mantiene en `web/` dentro de este flujo (D1).
   - **Estructura:**
     - `core/context.py` (G-01);
     - `core/clock.py`;
     - `core/jobs.py` (G-06);
     - `core/alerts.py` (G-08);
     - `core/crypto/registry.py`, `core/crypto/digest.py` y `core/crypto/archive.py` (G-07);
     - en `modules/`: `settings/`, `dashboard/`, `attachments/` (v0.3), `tv/` (v0.5) y `portal/` (v1.0), que faltan en el árbol actual (M-5).
   - **Reglas de módulos:**
     - regla 2 bis de dependencias mutuas entre services (G-03), con la lista blanca de v0.1 (memberships↔payments, members↔memberships, plans↔memberships) y la de v0.4 (members↔classes);
     - un módulo puede importar `schemas.py` y `exceptions.py` de otro (refinamiento de US-022).
   - **Reglas de datos:** excepción documentada a la regla 8: la fila de `SYSTEM_USER_ID` la inserta `0004_auth`, porque es dato de referencia para llaves foráneas (N-15).
   - **Bus, regla 5:** normalización del índice ciego de N-02.
   - **Licencias:**
     - se agregan `PSF-2.0`, `0BSD`, `ISC` y `OFL-1.1` (N-49 y US-004);
     - MPL-2.0 sin modificar también para `certifi` y `axe-core`.
   - **Seguridad:** Telegram es solo canal interno del equipo (N-34).
2. **`docs/ddd/02_domain_model.md`:**
   - Q1;
   - `compute_status` con `expiring_days` y fecha de Bogotá (Q11, Q28);
   - `apply_freeze` con límites (Q9) y `MembershipFreeze` (N-25);
   - `is_current` e `is_primary` (Q18, Q19);
   - récord de benchmark (Q20);
   - web push en v1.0 (Q14).
3. **`docs/ddd/05_service_design.md`:**
   - quitar `renew` como endpoint (Q2);
   - `reveal` también para coach (Q6);
   - secciones de Settings (Q11);
   - puerto `PrincipalLoader` (G-02).
4. **`docs/ddd/03_context_map.md`, sección 5:** lecturas a profundidad 2 (G-04).
5. **`docs/PLAN.md`:**
   - Tarea 6 (renovar);
   - v0.2: sale el push;
   - v0.3: entra el CBOM;
   - v1.0: sale el CBOM.
6. **`docs/BRECHAS.md`:** marcar como resueltas D3, D4 y las de la sección 3 que cierran estas decisiones.
7. **`docs/design/`:**
   - chip "Pendiente de pago" (Q3);
   - `limit`/`offset` en `DESIGN.md` y `ROUTES.md` (D2).
8. **`docs/ddd/07_user_stories/`:** se alinea con las contradicciones que resuelve el README del desglose:
   - `SYSTEM_USER_ID`;
   - variables de entorno, más `WEB_PORT` (A-4);
   - permisos `members.*`;
   - `broken_at_seq`;
   - `notifications_today`;
   - 409 `membership_cancelled`;
   - rangos de N-18;
   - Telegram interno.
9. **`docs/ddd/08_implementation_breakdown/EP-00-cimientos/US-008-scripts-de-gate-del-flujo.md`:** se amplía con el ajuste A-01 completo del README (firma con lista de archivos, mapeo, regex, `tests/architecture` siempre, lint y tsc acotados, `--cov-omit`).
10. **Verificación por grep:**
    - `grep -n "memberships/{id}/renew" docs/ddd/05_service_design.md docs/PLAN.md` no devuelve ningún endpoint vigente;
    - `grep -rn "SYSTEM_ACTOR_ID" docs/ddd/07_user_stories` no devuelve nada;
    - `grep -n "core/context.py\|settings/\|dashboard/" CLAUDE.md` devuelve las líneas nuevas.

### Wave 0 · Infraestructura (`devops-wsl2-docker`)

Hasta que exista US-008 (S0-W0-2), cada slice se verifica a mano con los comandos de su "Definición de hecho" y se confirma con un commit normal. Desde S0-W0-3, todos los slices usan los gates.

- **Slice S0-W0-0 · Línea base del entorno.** Solo verifica; no escribe código.
  - Comandos:
    - `docker version` y `docker compose version`;
    - `wsl --status` (WSL2 activo y Docker Desktop con su backend);
    - `uv --version`;
    - `uv python find 3.12` o `python --version` (3.12);
    - Git Bash disponible (`bash --version` en Windows);
    - puertos libres: 80, 8000, 5432 y 5433 (`netstat -ano | findstr :80` y equivalentes).
  - El resultado se escribe en `docs/scratch/sprint-00.md`.
  - Si el puerto 80 está ocupado, se define `WEB_PORT` en `.env`:
    - Compose publica `web` en `${WEB_PORT:-80}`;
    - US-007 la documenta en `.env.example`;
    - US-011 la agrega a `NON_API_ENV_VARS`, para que `extra="forbid"` no rompa el arranque.
  - Si falta una herramienta, el sprint se detiene con el diagnóstico.
- **Slice S0-W0-1 · Repositorio y proyecto api.** Historias: US-001 y US-002.
  - **Rojo:**
    - stubs de `api/src/app/__init__.py`;
    - `api/tests/test_smoke.py`;
    - `api/tests/architecture/test_ruff_banned_api.py`;
    - `api/tests/architecture/test_banned_imports.py`.
  - **Verde, US-001:**
    - estructura de carpetas;
    - `.gitattributes` ya existe con `eol=lf` y `*.woff2 binary`: solo se verifica;
    - protección de `main` documentada (A-02).
  - **Verde, US-002:**
    - `api/pyproject.toml` con uv;
    - ruff con `flake8-tidy-imports` y `banned-api` (`cryptography`, `oqs`, `hashlib`, `hmac`, `jwt`, `argon2`);
    - `mypy --strict`;
    - pytest con `asyncio_mode=auto`;
    - `.pre-commit-config.yaml`.
  - **Verificación manual:** `cd api && uv sync && uv run ruff check . && uv run mypy src && uv run pytest`.
- **Slice S0-W0-2 · Scripts de gate.** Historia: US-008, con el ajuste A-01 completo.
  - **Rojo:** `scripts/workflow/tests/lib.sh` y las pruebas de los scripts:
    - `test_slice_gate.sh`: lista de archivos, `tests/architecture` siempre, mapeo, regex de varios niveles con guiones, rama `web/`;
    - `test_checkpoint_commit.sh`;
    - `test_run_gates.sh`, con `--cov-omit`;
    - `test_validate_impact.sh`;
    - `test_permisos.sh`.
  - **Verde:**
    - `slice-gate.sh <modulo> [archivos de prueba...]`, con la tabla de mapeo de A-01;
    - `checkpoint-commit.sh`;
    - `run-gates.sh`, con cobertura global de `app` al 80 % y `--cov-omit` de `src/app/cli.py` y `src/app/worker/*` hasta el Sprint 4A (M-6);
    - `validate-impact-analysis.sh`: VERDE, APROBADO y APROBADO CON OBSERVACIONES pasan; AMARILLO solo con `--allow-amber`;
    - `scripts/workflow/README.md`.
  - **Gate:** `bash scripts/workflow/tests/run.sh`. Es el primer checkpoint del proyecto.
- **Slice S0-W0-3 · CI y licencias.** Historias: US-003 y US-004.
  - **Rojo:**
    - `api/tests/test_ci_database.py`: usa `TEST_DATABASE_URL` y **falla, no se salta**, si no está definida;
    - prueba de la lista de licencias.
  - **Verde:**
    - `.github/workflows/ci.yml` con los jobs `api` (PostgreSQL 16 de servicio y `TEST_DATABASE_URL`), `images`, `web` y `scripts`;
    - `pip-licenses --allow-only` con la lista ampliada (refinamiento de US-004);
    - `NOTICE`.
  - **Gate:** `slice-gate.sh architecture tests/test_ci_database.py`.
  - CI se valida cuando una persona empuja la rama y abre el PR (A-02).
  - **Criterio diferido, se cierra en la validación de este sprint:** el paso `licencias-web` necesita `web/package.json` (US-009).
- **Slice S0-W0-4 · Imagen del api, Compose y entorno.** Historias: US-005 y US-007.
  - **Rojo:**
    - `api/tests/test_main_placeholder.py`;
    - `scripts/ci/test_api_image.sh`, que verifica:
      - usuario no root;
      - `tzdata`;
      - que `alembic.ini` y `migrations/` existen en la imagen;
      - que `docker run --rm <imagen> alembic heads` termina con 0.
  - **Verde, `api/Dockerfile` multi-stage con uv:**
    - etapas `builder` y `runtime`;
    - en las dos: `COPY alembic.ini migrations ./`, además de `pyproject.toml`, `uv.lock` y `src` (B-3);
    - el runtime no tiene `uv`, y su `PATH` apunta a `/app/.venv/bin`;
    - por eso, dentro de los contenedores, los comandos van sin `uv run`.
  - **Verde, `infra/compose.yml`:**
    - servicios `web` (publicado en `${WEB_PORT:-80}`), `api`, `db`, `worker` (con `profiles: ["worker"]`), `backup` y `tools`;
    - `tools` usa `entrypoint: ["python", "-m", "app.cli"]`.
  - **Verde, `infra/compose.dev.yml`:**
    - puertos;
    - hot reload;
    - `db_test`;
    - bind mounts de `../api/src` y `../api/migrations` (B-3).
  - **Verde, resto:**
    - `scripts/ci/compose-smoke.sh`;
    - `.env.example` con los nombres de US-011, más `WEB_PORT`;
    - README de arranque.
  - **Gate:** `slice-gate.sh main tests/test_main_placeholder.py` y `bash scripts/ci/test_api_image.sh`.
    - `tests/core/test_env_example.py` **no** forma parte de este gate (A-3): compara contra `Settings` y entra en S0-B1.
  - **Criterios diferidos:**
    - el healthcheck `healthy` con la app real se cierra en este sprint con US-020;
    - el servicio `tools` con `init-keys` se cierra en el Sprint 1, S1-B4;
    - la medición T6 de US-007 se cierra en la validación del Sprint 1;
    - quitar `profiles: ["worker"]` se cierra en el Sprint 4A con US-113.
- **Slice S0-W0-5 · Nginx e imagen del front.** Historia: US-006.
  - **Rojo:** smoke de Nginx en `scripts/ci/compose-smoke.sh` (proxy y límite de 5 MB).
  - **Verde:** `infra/nginx/default.conf` con:
    - proxy de `/api/` a `api:8000`;
    - `client_max_body_size 5m`;
    - `X-Forwarded-For` sobrescrito con `$remote_addr`;
    - `try_files`.
    - La imagen se construye con un `web/index.html` provisional.
  - **Gate:** `bash scripts/ci/compose-smoke.sh`.
  - **Criterio diferido, se cierra en la validación de este sprint:** servir el build real (US-009) y el 200 real de `/api/v1/health` (US-020).
  - **Criterio diferido, se cierra en el Sprint 1:** cabeceras y CSP (US-038).

### Waves 3a/3b · Backend, alternadas por slice (`backend-qa-executor` y luego `backend-implementor`)

- **Slice S0-B1 · Configuración y reloj.** Historias: US-011 y US-013.
  - **Rojo:**
    - stubs de `core/config.py` y `core/clock.py`;
    - `tests/core/test_config.py`;
    - `tests/core/test_config_error_message.py`;
    - `tests/core/test_env_example.py`;
    - `tests/core/test_clock.py`;
    - `tests/architecture/test_no_os_environ.py`;
    - `tests/architecture/test_no_direct_now.py`.
  - **Verde:**
    - `Settings`:
      - `extra="forbid"`;
      - `NON_API_ENV_VARS`, que incluye `WEB_PORT`;
      - `DATABASE_URL` como `SecretStr`;
      - `CORS_ORIGINS` como `list[str]`.
    - `Clock`, `SystemClock`, `FrozenClock` y `today_bogota()` (Q28).
  - **Gate:** `slice-gate.sh core/config` y `slice-gate.sh core/clock`, cada uno con sus archivos de Rojo.
- **Slice S0-B2 · Base de datos y Alembic multiesquema.** Historia: US-012.
  - **Rojo:**
    - stub de `core/db.py`;
    - `tests/core/test_db.py`;
    - `tests/core/test_migrations.py`;
    - `tests/core/test_session_dependency.py`;
    - `tests/architecture/test_no_create_all.py`.
  - **Verde:**
    - engine async con `hide_parameters=True`;
    - `Base` y `CommonColumnsMixin`, con el UUID asignado en Python;
    - `migrations/env.py` multiesquema;
    - **migración `0001_core_schemas`:** los esquemas `audit`, `crypto`, `auth`, `settings`, `members`, `plans`, `memberships`, `payments` y `worker`, y `CREATE EXTENSION btree_gist`.
  - **Gate:** `slice-gate.sh core/db <archivos de Rojo>` y el ciclo `alembic upgrade head && downgrade -1 && upgrade head`.
  - **Criterio diferido, se cierra en el Sprint 1:** `created_by` automático lo da US-016, en S1-B2.
- **Slice S0-B3 · Envelope de errores y logs JSON.** Historias: US-017 y US-018.
  - **Rojo:**
    - stubs de `core/errors.py`, `core/logging.py` y `core/context.py`;
    - `tests/core/test_errors_field.py`;
    - `tests/core/test_errors_router.py`;
    - `tests/core/test_logging_redact.py`;
    - `tests/core/test_logging_sql.py`;
    - `tests/core/test_logging_access.py`;
    - `tests/architecture/test_error_responses_in_openapi.py`;
    - `tests/architecture/test_no_sensitive_in_logs.py`.
  - **Verde:**
    - envelope `{ error: { code, message, field?, existing_id? } }` y `ERROR_RESPONSES`;
    - JSON a stdout con redacción y `RequestLogMiddleware`;
    - `core/context.py` solo con `request_id_var`. US-016 lo completa (G-01).
  - **Gate:** `slice-gate.sh core/errors` y `slice-gate.sh core/logging`, con sus archivos.
  - **Criterio diferido:** la tarea T8 de US-018 (redacción con datos reales) se cierra en S2-B7, al llegar `members`, y en S3-B10, con `reveal` (A-6).
- **Slice S0-B4 · Bus de eventos y `create_app`.** Historias: US-014 y US-020.
  - **Rojo:**
    - stubs de `core/events.py` y `main.py`;
    - `tests/core/test_events.py`;
    - `tests/core/test_events_db.py`;
    - `tests/core/test_events_router.py`;
    - `tests/core/test_health.py`;
    - `tests/core/test_migration_lock.py`;
    - `tests/core/test_startup_failure.py`;
    - `tests/architecture/test_routes_under_api_v1.py`;
    - `tests/architecture/test_core_import_direction.py`, primera versión: `core` no importa `app.modules`.
  - **Verde:**
    - `subscribe` y `emit` en la misma sesión;
    - `create_app()`:
      - `alembic upgrade head` al arrancar, con `pg_advisory_lock` (necesita `migrations/` en la imagen, B-3);
      - `load_module_services()`;
      - `register_error_handlers`;
      - `register_health_check`;
    - `GET /health` y `GET /api/v1/health`;
    - `/docs` apagado en producción.
  - **Gate:** `slice-gate.sh core/events` y `slice-gate.sh main`, con sus archivos.
  - **Criterio diferido, se cierra en S1-B2:** `install_audit_listeners()` y `actor_scope(SYSTEM_USER_ID)`.
  - **Criterio diferido, se cierra en el Sprint 4B:** el campo `backup` (US-115) y el arranque ordenado (US-118).

### Waves 5a/5b · Front, alternadas por slice (`frontend-qa-automation` y luego `frontend-ux-engineer`)

- **Slice S0-F1 · Esqueleto del front.** Historia: US-009.
  - **Rojo:**
    - `src/core/styles/tokens.test.ts`;
    - `src/App.test.tsx`, sobre un `App` vacío;
    - `tests/lint/lint-controls.test.ts`;
    - `tests/e2e/smoke.spec.ts`.
  - **Verde:**
    - Vite, React 19 y TypeScript estricto;
    - `tokens.css` y `fonts.css` locales;
    - lint de colores;
    - Vitest con jsdom;
    - Playwright base;
    - proxy de Vite.
  - **Gate:** `slice-gate.sh web/app <archivos de Rojo>`.
- **Slice S0-F2 · Componentes base.** Historia: US-010.
  - **Rojo:** stubs y pruebas en `src/shared/ui` de `Button`, `Field` y `StatusTag`, con axe.
  - **Verde:** los tres componentes, accesibles.
  - **Gate:** `slice-gate.sh web/shared <archivos de Rojo>`.

### Validación del sprint

- Se cierran los criterios diferidos dentro del sprint:
  - `licencias-web` (US-004);
  - el build real servido por Nginx y el proxy a `/api/v1/health` (US-006);
  - el healthcheck `healthy` (US-005).
- `run-gates.sh` en verde.
- `docker compose -f infra/compose.yml up -d --build` y `scripts/ci/compose-smoke.sh`.
- `npx playwright test tests/e2e/smoke.spec.ts` contra el stack.
- **Paso humano:** push de la rama y apertura del PR; CI en verde (A-02).

## Migraciones que aplica

- `0001_core_schemas` (US-012).

## Endpoints que expone

- `GET /health` (lista blanca; US-020).
- `GET /api/v1/health` (lista blanca; US-020).

## Tests de arquitectura que deben pasar

Todos se ejecutan en cada gate de slice (A-5).
- `test_ruff_banned_api.py` y `test_banned_imports.py`, primera versión (US-002).
- `test_no_os_environ.py` (US-011).
- `test_no_create_all.py` (US-012).
- `test_no_direct_now.py` (US-013).
- `test_core_import_direction.py`, primera versión (US-014).
- `test_error_responses_in_openapi.py` (US-017).
- `test_no_sensitive_in_logs.py` (US-018).
- `test_routes_under_api_v1.py` (US-020).
- La suite de los scripts: `scripts/workflow/tests/test_permisos.sh` (US-008).

## Riesgos y mitigación

1. [HIGH] El gate humano no aprueba D1, o cambia otra decisión de la sección A.
   - Mitigación: T-DOC va primero y bloquea.
   - Si D1 no pasa, US-009 y US-010 salen del alcance de agentes y se re-planean las Waves 5.
2. [MEDIUM] Arranque en frío: los gates no existen hasta S0-W0-2.
   - Mitigación: S0-W0-0 y S0-W0-1 se verifican a mano y la evidencia queda en `docs/scratch/sprint-00.md`.
3. [MEDIUM] Docker Desktop sobre WSL2: rendimiento de volúmenes, fin de línea y puerto 80 ocupado.
   - Mitigación: S0-W0-0, `WEB_PORT`, `.gitattributes` con LF y `git update-index --chmod=+x`.
4. [MEDIUM] Los criterios diferidos de US-005, US-006, US-007, US-018 y US-020 pueden dar una falsa sensación de "hecho".
   - Mitigación: cada uno está nombrado aquí con el slice o el sprint que lo cierra, y se revisa en `verify-delivery`.
5. [LOW] `pip-licenses` falla en la primera corrida por `typing_extensions` (PSF-2.0).
   - Mitigación: la lista ampliada entra con T-DOC.

## Definición de hecho del sprint

- T-DOC confirmado y verificación por grep limpia.
- `docs/scratch/sprint-00.md` con la línea base del entorno.
- Cada slice desde S0-W0-2 tiene su `checkpoint-commit.sh`. S0-W0-0 y S0-W0-1 tienen evidencia manual.
- `scripts/workflow/run-gates.sh` en verde: cobertura global de `app` de al menos 80 %, con `--cov-omit` de `cli.py` y `worker/` documentado; y front con lint, tsc, test y build.
- `bash scripts/workflow/tests/run.sh` y `cd api && uv run pytest tests/architecture -q` en verde.
- Ciclo de Alembic sobre `0001`.
- Licencias en verde en api y front. `NOTICE` presente.
- Smoke:
  - `docker compose -f infra/compose.yml up -d --build`;
  - `scripts/ci/compose-smoke.sh`;
  - `bash scripts/ci/test_api_image.sh` (`alembic heads`);
  - `curl` a los dos `/health` con 200.
- E2E: `npx playwright test tests/e2e/smoke.spec.ts`.
- Seguridad (`security-reviewer`):
  - usuario no root;
  - sin `.env` ni llaves en la imagen;
  - `.dockerignore`;
  - `banned-api` activo;
  - ningún script hace `git push`, `--force` ni `--no-verify`;
  - `/docs` apagado con `ENV=production`.
- **Paso humano:** push de la rama, PR con CI en verde y merge.
- `verify-delivery` con la evidencia de la demo.
