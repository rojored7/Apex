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
