# Sprint 0 · cuaderno de trabajo

Rama: `chore/sprint-00-cimientos` (desde `main` en `dc12c57`). Gate humano aprobado el 21 de octubre de 2026 con todas las decisiones de la sección A de `docs/ddd/DECISIONES.md` tal como se propusieron (D1, D2, D5, P5, P7, tres épicas de núcleo). El usuario fijó además que, ante contradicción, manda `/flow-new-project` y `CLAUDE.md` se corrige.

## S0-W0-0 · Línea base del entorno (21 de octubre de 2026)

- Windows 11 Pro 10.0.26300. Shell de trabajo: Git Bash 5.2.37 (msys) y PowerShell 5.1.
- WSL: distribución predeterminada Ubuntu, versión 2.
- Docker: cliente 29.2.1, Docker Compose v5.0.2. Docker Desktop estaba instalado pero apagado; se arrancó desde `C:\Program Files\Docker\Docker\Docker Desktop.exe` en esta sesión (ver abajo el estado del daemon).
- `uv`: no estaba instalado. Se instaló `uv 0.13.4` con el instalador oficial (`irm https://astral.sh/uv/install.ps1 | iex`) en `C:\Users\PC\.local\bin`. Las sesiones de shell abiertas antes de la instalación no lo tienen en `PATH`; en Bash se usa `export PATH="$HOME/.local/bin:$PATH"`.
- Python: el alias `python` de Windows apunta a la tienda (no hay intérprete). Vía `py`: 3.14.3 (predeterminado) y 3.12.10 (`py -3.12`). `uv` gestiona el 3.12 del proyecto.
- Node 24.14.0, npm 11.9.0, git 2.53.0.windows.1.
- Puertos: sin ningún proceso en `LISTENING` en 80, 8000, 5432, 5433 ni 5173. `WEB_PORT` queda en su valor por defecto (80). La primera búsqueda con `findstr :80` mostró conexiones salientes a puertos 80 remotos, no listeners; se repitió filtrando por `LISTENING`.

## T-DOC

- Pendiente de registrar al cerrar.
- Docker daemon: arriba tras arrancar Docker Desktop (`docker info` → servidor 29.2.1, `linux`). Línea base completa; ninguna herramienta falta.

## T-DOC (21 de octubre de 2026)

- Aplicadas las correcciones de `DECISIONES.md` C y E con scripts de reemplazo exacto (cada reemplazo exige una sola coincidencia): `CLAUDE.md` (14), `02_domain_model.md` (26), `05_service_design.md` (17), `03_context_map.md` (2), `docs/PLAN.md` (5), `docs/BRECHAS.md` (26), `DESIGN.md` (2), `ROUTES.md` (9 más 7 sustituciones de paginación).
- Historias (`07_user_stories`, 36 archivos) y `US-008` del desglose alineados por el agente `doc-updater`; dos restos cerrados a mano: `SEED_ADMIN_*` y `APEX_SEED_ADMIN_*` pasan a `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` en `08_implementation_breakdown` y `09_sprint_plan` (DECISIONES E), y US-043 criterio 2 adopta N-13 (reusar un refresh rotado revoca todas las sesiones).
- Decisión de interpretación del agente aceptada: en US-112 `--as` es opcional con `SYSTEM_USER_ID` por defecto (N-15 dice que todo comando del CLI lo acepta).
- Verificación por grep: `memberships/{id}/renew` sin endpoints vigentes; `SYSTEM_ACTOR_ID` sin resultados en historias; `CLAUDE.md` con `core/context.py`, `settings/` y `dashboard/`; sin `page`/`page_size` en el diseño.

## S0-W0-1 · Repositorio y proyecto api (US-001, US-002)

- Rojo: con `pyproject.toml` sin la sección de ruff, `uv run pytest` dio 4 fallos (`test_ruff_banned_api.py`) y 5 pasadas. Verde tras agregar `[tool.ruff]`: `ruff check`, `ruff format --check`, `mypy src` (strict) y 9 pruebas, cobertura 100 % (solo paquetes vacíos).
- `uv tree --no-dev --depth 1` no lista ruff, mypy, pytest ni pre-commit. Versiones resueltas: fastapi 0.157, sqlalchemy 2.1.5, pydantic 2.14, alembic 1.20, cryptography 50, ruff 0.15.12, mypy 1.20.2, pre-commit 4.7.0.
- Secretos: las 4 coincidencias de `BEGIN PRIVATE KEY` en `git log -p --all` son texto de los criterios de las historias, no llaves. Un `.env` de prueba no aparece en `git status`.
- **Diferido:** `pre-commit run --all-files` no pudo inicializar los hooks remotos porque `github.com:443` no responde desde esta máquina (PyPI sí). Se repite cuando haya conectividad; mientras tanto ruff, formato y mypy corren con `uv run`.
- **Paso humano (A-02):** protección de `main` en GitHub (US-001 T8); `gh` no está instalado y el push está pendiente de la persona.
- **Desviación del plan:** además del 80, están ocupados por otros proyectos en Docker el 8000 (`dian-api`), el 5432 y el 5433 (POSSI). Compose parametriza también `API_PORT`, `DB_PORT` y `DB_TEST_PORT` (por defecto 8000, 5432, 5433) y en esta máquina el `.env` usa `WEB_PORT=8180`, `API_PORT=8181`, `DB_PORT=5442`, `DB_TEST_PORT=5443`. Las tres variables nuevas entran en `NON_API_ENV_VARS` (US-011) y en `.env.example` (US-007).

## S0-W0-2 · Scripts de gate (US-008)

- Rojo: `bash scripts/workflow/tests/run.sh` con 0 de 5 archivos en verde (código 127, scripts ausentes). Verde: 5 de 5 (slice-gate 34 casos, checkpoint 12, run-gates 15, validate-impact 16, permisos 20).
- Gate real: `run-gates.sh 0` en verde (api; sin front todavía) y `slice-gate.sh architecture` como sello para el checkpoint `a322edc`.
- Desviación: pytest-cov no tiene `--cov-omit`; la exclusión de `cli.py` y `worker/*` (M-6) vive en `[tool.coverage.run] omit` de `api/pyproject.toml` y se quita en el Sprint 4A. `checkpoint-commit.sh` acepta `CHECKPOINT_TRAILER` para la línea de coautoría.

## S0-W0-3 · CI y licencias (US-003, US-004)

- Rojo: `tests/test_ci_database.py` falla (no se salta) sin `TEST_DATABASE_URL`; `scripts/ci/test_licenses.sh` sin el script de chequeo. Verde: `check-licenses-api.sh` acepta el runtime real (PSF-2.0 para `typing_extensions`, `certifi` por excepción MPL-2.0) y rechaza `fpdf2` (LGPL) y un paquete sin licencia; `NOTICE` generado dos veces idéntico.
- `.github/workflows/ci.yml` con jobs `api` (postgres:16 de servicio, `TEST_DATABASE_URL`, licencias, `NOTICE`), `web`, `images` y `scripts`, condicionados por existencia de archivos. Se valida cuando una persona empuje la rama (A-02); `github.com` no responde desde esta máquina.
- Checkpoint `a4275b6` con sello de `slice-gate.sh architecture`.

## S0-W0-4 · Imagen del api, Compose y entorno (US-005, US-007)

- Rojo: `tests/test_main_placeholder.py` sin `app.main`; `scripts/ci/test_api_image.sh` sin imagen. Verde: imagen `apex-api:ci` (328 MB, dos etapas, `uv` instalado desde PyPI, usuario `apex` 10001, `alembic.ini` y `migrations/` dentro, `alembic heads` con 0, sin pytest/ruff/mypy); `test_compose_config.sh` 14 de 14; `compose-smoke.sh` con `SMOKE_ALLOW_UNHEALTHY=1` (no hay `/health` hasta US-020) en 8 s; gate `slice-gate.sh main tests/test_main_placeholder.py tests/test_ci_database.py` con `db_test` arriba: 10 pruebas en verde, incluida la de PostgreSQL 16.
- Stack local arriba en `apex-db-1` (5442), `apex-db_test-1` (5443) y `apex-api-1` (8181); el marcador responde `/docs` con 200.
- **Entorno:** el bridge de Docker Desktop no tiene salida a internet en esta máquina (`Network is unreachable` dentro de los contenedores; `--network host` sí sale). No se reinicia Docker porque hay stacks ajenos corriendo. Mitigación: `compose.dev.yml` fija `build.network: host` para el api y `test_api_image.sh` acepta `DOCKER_BUILD_NETWORK=host`; `compose.yml` y la CI siguen estándar.
- **Desviación:** el servicio `backup` no se declara todavía (lo crea US-114 en el Sprint 4B); solo el volumen `backups`, como fija el desglose de US-005. `.env.example` incluye ya `ENV`, `TRUSTED_PROXIES`, `COOKIE_SECURE`, `FRONT_BASE_URL`, `TEST_DATABASE_URL` y los cuatro puertos; US-011 debe poner `TEST_DATABASE_URL`, `API_PORT`, `DB_PORT` y `DB_TEST_PORT` en `NON_API_ENV_VARS` junto con `WEB_PORT`.
- El barrido de archivos sensibles de la imagen excluye `site-packages`: `certifi/cacert.pem` y el parser de llaves de `cryptography` contienen `.pem` y la cadena `BEGIN PRIVATE KEY` de forma legítima (coincide con la nota de US-039).
- Diferidos (según el plan): healthcheck `healthy` real con US-020; `tools init-keys` en S1-B4; medición T6 de US-007 en la validación del Sprint 1; `profiles: ["worker"]` hasta US-113; protección de `main` y CI en verde cuando una persona empuje.

## S0-W0-5 · Nginx e imagen del front (US-006)

- Rojo: `test_nginx_conf.sh` sin `default.conf` y `web-smoke.sh` con 5 fallas sin `web`. Verde: `test_nginx_conf.sh` 10 de 10 (`nginx -t` por stdin, 5 MB, `server_tokens off`, `X-Forwarded-For` con `$remote_addr`, `X-Request-ID`, proxy sin URI, fallback del SPA, log sin query strings); `compose-smoke.sh` con `web` en 27 s y `web-smoke.sh` 5 de 5 (`/` y `/socios/123` con `#root`, `/api/v1/health` llega al api como 404 JSON hasta US-020, 413 con 5 MB + 1, `Server: nginx` sin versión).
- `web/Dockerfile` sirve `web/index.html` provisional mientras no exista `package.json` (rama condicional que US-009 retira). Contexto de build en la raíz con `web/Dockerfile.dockerignore`. En desarrollo el build de `web` también usa la red del host.
- Stack local: `apex-web-1` healthy en 8180, `apex-api-1` en 8181, `apex-db-1` en 5442, `apex-db_test-1` en 5443.
- Diferidos (plan): build real y `/api/v1/health` con 200 en la validación del sprint (US-009, US-020); cabeceras y CSP en el Sprint 1 (US-038).

## S0-B1 · Configuración y reloj (US-011, US-013)

- Rojo (`0ad46f6`): 13 fallos y 11 errores sobre stubs. Verde: 38 pruebas de `tests/core` y `tests/architecture`, mypy strict en 6 archivos.
- `Settings` con `extra="forbid"`; las claves ajenas (`POSTGRES_*`, `TEST_DATABASE_URL`, `ADMIN_EMAIL`, `ADMIN_INITIAL_PASSWORD`, `WEB_PORT`, `API_PORT`, `DB_PORT`, `DB_TEST_PORT`) se filtran del origen dotenv (`NON_API_ENV_VARS`); cualquier otra clave desconocida da `ConfigError` con su nombre. `ConfigError` se construye solo con `loc` y `type` y se lanza `from None`: ni el `ValidationError` ni su `input_value` llegan al mensaje (probado con un DSN inválido que lleva contraseña).
- Desviación documentada: `JWT_PRIVATE_KEY_PATH` es `Path`, no `FilePath`. Con `FilePath` ningún comando del host (`get_settings()`, exportar OpenAPI, pruebas) arrancaría porque `/run/apex/keys/...` solo existe en el contenedor; la existencia del archivo la valida quien carga la llave (US-033, US-023). Los campos de historias posteriores que ya pedía `.env.example` (`ENV`, `TRUSTED_PROXIES` como texto separado por comas con la propiedad `trusted_proxies`, `COOKIE_SECURE`, `FRONT_BASE_URL`) entran ya para que `test_env_example.py` pase.
- `core/clock.py`: `Clock`, `SystemClock`, `FrozenClock` (normaliza a UTC, `advance`, `set`), `to_bogota_date` pura, `current_clock`/`set_clock`/`reset_clock` sobre `ContextVar` (sin valor por defecto mutable, B039) y dependencia `get_clock`. `tzdata` agregado a las dependencias (T6); el smoke de la zona en la imagen se cierra en la validación del sprint al reconstruir.
- Comprobaciones de la definición de hecho: sin `DATABASE_URL`, `get_settings()` termina con `ConfigError` que la nombra sin valores; `print(get_settings())` muestra `SecretStr('**********')`.

## S0-B2 · Base de datos y Alembic multiesquema (US-012)

- Rojo (`4fccc4d`): `test_migrations` y `test_no_create_all` fallan por comportamiento; `test_db` y `test_session_dependency` fallaron en la recolección (el stub del mixin no declaraba clave primaria), observación: el rojo de esas dos no fue por comportamiento sino por configuración del mapper.
- Verde: 24 pruebas (db, migraciones, sesión, arquitectura) contra `db_test`; mypy strict en 7 archivos; ciclo `alembic -x url=... upgrade head / downgrade -1 / upgrade head` por CLI en verde (`env.py` acepta `-x url=` para el host, `sqlalchemy.url` para pruebas y `Settings` por defecto; también una conexión inyectada en `config.attributes["connection"]` para US-020).
- `CommonColumnsMixin` asigna el UUID en el evento `init` (US-028 cifra con `aad = id` antes del flush); `created_by` NOT NULL sin FK; `SoftDeleteMixin` aparte; `type_annotation_map` con `TIMESTAMPTZ` y UUID nativo; convención de nombres de restricciones. `get_session` hace commit al salir de la dependencia, antes de la respuesta (probado: una excepción tras insertar deja 0 filas; una respuesta normal deja 1).
- `conftest.py` compartido: `TEST_DATABASE_URL` obligatoria (falla, no se salta), `alembic upgrade head` una vez por corrida, savepoint por prueba con rollback de la transacción externa. `path_separator = os` en `alembic.ini` por el aviso de deprecación de Alembic 1.20.

## S0-B3 · Envelope de errores, logs JSON y contexto (US-017, US-018, G-01)

- Rojo (`4dea2a0`): 20 fallos, 10 errores y 1 saltada sobre stubs. Verde: 44 pruebas del slice (campo de validación, router de errores con 409/422/500/404/405 y la jerarquía 400/401/403/404/422, redacción por clave y por forma, SQL sin parámetros contra `db_test`, línea de acceso con `X-Request-ID`, `ErrorResponse` en todo 4xx y 5xx del OpenAPI sin `HTTPValidationError`).
- `core/context.py` nace solo con `request_id_var` (US-016 lo completa). `register_error_handlers` registra los cuatro handlers y reemplaza `app.openapi` para publicar `ErrorResponse`; `ERROR_RESPONSES` sirve a `FastAPI(responses=...)` y a `include_router`.
- Hallazgos: `fileConfig` de Alembic desactivaba los loggers ya creados (`app.access`): `migrations/env.py` pasa `disable_existing_loggers=False` y `configure_logging` reactiva el logger de acceso. `httpx` y `httpcore` registran la URL completa en INFO (query con `q=1020304`): `configure_logging` los deja en WARNING. `X-Request-ID` nunca reutiliza el valor del cliente.
- `tests/architecture/test_no_sensitive_in_logs.py` queda saltada con dueñas US-042, US-069 y US-074 (se activa sola cuando existan `auth.router` y `members.router`).

## S0-B4 · Bus de eventos y create_app (US-014, US-020)

- Rojo (`b84dd32`): 5 fallos y 16 errores sobre stubs. Verde: bus en memoria con despacho por tipo exacto, misma sesión, propagación de errores y corte en profundidad 5; probado sin base, con base (`begin_nested`: emisor y handler persisten juntos; si un handler falla no queda ni la fila del emisor) y por router con `get_session`.
- `create_app(settings, run_migrations_on_startup, migrations_script_location)`: logs, engine desde `Settings`, envelope, middleware de acceso, `load_module_services()`, routers bajo `/api/v1`, `/health` en raíz y bajo `/api/v1`, `/docs` y `/openapi.json` apagados con `ENV=production`; `app.main:app` perezosa (PEP 562). `lifespan`: `alembic upgrade head` en hilo aparte y relanza el error (probado con una revisión rota sobre 0001: el `lifespan` relanza y un `uvicorn --factory` real termina con código distinto de 0).
- Lock asesor `MIGRATION_LOCK_KEY` en `migrations/env.py` (transacción externa con commit explícito): dos `python -m alembic upgrade head` simultáneos terminan sin error y uno espera (`pg_locks` no concedido) mientras otra sesión tiene el lock. Se usan procesos, no hilos: `alembic.context` no es seguro entre hilos.
- `/health`: `SELECT 1` con `asyncio.timeout(2)`, base caída responde 503 `db=down` en menos de 3 s; comprobaciones registradas `critical=False` mantienen el 200 y `critical=True` dan 503 (N-16). `APP_VERSION` en `Settings` y `ARG GIT_SHA` en el Dockerfile. `connect_args={"timeout": 5}` en el engine.
- FastAPI 0.157 incluye routers de forma perezosa (`_IncludedRouter`), así que `test_routes_under_api_v1` lee las rutas del OpenAPI. `test_main_placeholder.py` retirada (la reemplazan `test_health.py` y `test_startup_failure.py`); `test_api_image.sh` verifica `create_app` importable.
- Diferidos (plan): `install_audit_listeners()` y `actor_scope(SYSTEM_USER_ID)` en S1-B2; campo `backup` (US-115) y arranque ordenado (US-118) en el Sprint 4B.
