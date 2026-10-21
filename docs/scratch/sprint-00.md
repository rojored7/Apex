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
