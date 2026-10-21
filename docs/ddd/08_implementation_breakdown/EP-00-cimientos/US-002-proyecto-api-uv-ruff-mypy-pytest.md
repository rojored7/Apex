# US-002 · Proyecto api con uv, ruff, mypy, pytest y pre-commit — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-00-cimientos/US-002-proyecto-api-uv-ruff-mypy-pytest.md`
- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context / módulo:** ninguno de negocio, terreno (`api/pyproject.toml`, `api/src/app/`, `api/tests/`, `.pre-commit-config.yaml`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

La historia fija herramientas y reglas que ya están decididas en `CLAUDE.md` (stack fijo, regla 8 del bus, "Calidad y Git") y en `05_service_design.md` sección 2. DECISIONES N-06 confirma que `core/audit.py` no necesita excepción de `banned-api` porque usa `core.crypto.bus.digest`. No queda ningún supuesto que cambie contrato ni comportamiento.

## Resumen

Crear el proyecto Python del api gestionado con `uv`: `pyproject.toml` con Python 3.12, dependencias de runtime del stack fijo y grupo `dev` separado, `uv.lock` versionado, ruff (lint y formato) con `flake8-tidy-imports.banned-api` para `cryptography`, `oqs`, `hashlib`, `hmac`, `jwt`, `argon2` y excepción solo en `src/app/core/crypto/**` y `src/app/core/security.py`, `mypy --strict` sobre `src/`, `pytest` con `asyncio_mode = "auto"`, una prueba de humo y `pre-commit` en la raíz con ruff y mypy. Además, una prueba de arquitectura liviana que impide que alguien afloje la configuración de `banned-api` sin que falle la suite.

## Correcciones aplicadas por DECISIONES.md

- La historia lista la excepción de `banned-api` para `core/crypto/**` y `core/security.py` → se mantiene exactamente así y se deja explícito que `core/audit.py` no tiene excepción (usa `core.crypto.bus.digest` para el SHA-256 de la cadena): corregido por DECISIONES N-06 (aclaración, no cambio).
- Ninguna otra; la historia ya es coherente con DECISIONES.md.

## Validación contra el dominio

- No hay aggregates, entidades, value objects, invariantes RN-xx ni eventos.
- Indirectamente protege RN-13 (datos sensibles cifrados por el bus): la regla `banned-api` es la barrera estática que obliga a cifrar por `core.crypto.bus`.

## Validación contra la arquitectura

- Estructura `api/src/app/` y `api/tests/` según `05_service_design.md` sección 2. El paquete se llama `app` (imports `from app.core...`).
- Regla 8 del bus de `CLAUDE.md`: los seis módulos van en `banned-api`; la excepción vive solo en `per-file-ignores` de `src/app/core/crypto/**` y `src/app/core/security.py`. Si `core/security` crece a paquete, la excepción se amplía a `src/app/core/security/**` en la historia que lo haga (EP-03), nunca a otra ruta.
- `liboqs-python` no se instala en v0.1 (riesgo 5 de `00b_impact_analysis.md`); `oqs` igual queda prohibido en `banned-api` desde ya.
- Sin módulos de negocio, sin rol, sin paginación, sin auditoría: no aplica.
- `asyncpg` como driver de PostgreSQL (Apache 2.0); `aiosqlite` no entra: ninguna prueba usa SQLite (US-003 criterio 2).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- No aplica.

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T1 · `api/tests/test_smoke.py`: `test_app_package_importa()` que importa `app` y verifica `app.__name__ == "app"` (prueba trivial del criterio de salida de la Tarea 0) — 0,5 h

### Tests de service con PostgreSQL
- No aplica (la sesión de prueba y `conftest.py` con PostgreSQL los crea US-012).

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T2 · `api/tests/architecture/test_ruff_banned_api.py`: lee `api/pyproject.toml` con `tomllib` y verifica que (a) `cryptography`, `oqs`, `hashlib`, `hmac`, `jwt`, `argon2` están en `tool.ruff.lint.flake8-tidy-imports.banned-api`; (b) `TID` está en `select`; (c) las únicas entradas de `per-file-ignores` que contienen `TID251` son `src/app/core/crypto/**` y `src/app/core/security.py`. No sustituye a US-031 (que revisa los imports reales); evita que alguien desactive la regla en silencio — 1,5 h
- [ ] T3 · `api/tests/architecture/test_ruff_banned_api.py::test_import_prohibido_falla`: escribe en `tmp_path` un árbol `src/app/modules/x/service.py` con `import hashlib` y `from cryptography.hazmat.primitives.ciphers.aead import AESGCM`, corre `ruff check --config <pyproject> <tmp>` con `subprocess` y exige código distinto de 0 con `TID251` para ambas líneas; el mismo contenido en `src/app/core/crypto/bus.py` da código 0 (cubre los criterios 3 y el escenario "Import permitido dentro del bus") — 1,5 h

### Front
- No aplica.

### DevOps
- [ ] T4 · `api/pyproject.toml` sección `[project]`: `name = "apex-api"`, `requires-python = ">=3.12,<3.13"`, `[project.dependencies]` con fastapi, uvicorn[standard], sqlalchemy[asyncio] 2.x, asyncpg, alembic, pydantic 2.x, pydantic-settings, apscheduler 3.x, httpx, argon2-cffi, pyjwt, cryptography (versiones con cota inferior y `~=` en las de API inestable); `[build-system]` con hatchling y `[tool.hatch.build.targets.wheel] packages = ["src/app"]`; `api/.python-version` con `3.12` — 2 h
- [ ] T5 · `[dependency-groups] dev`: ruff, mypy, pytest, pytest-asyncio, pytest-cov, pre-commit, pip-licenses (lo usa US-004); generar y versionar `api/uv.lock` con `uv lock` — 0,5 h
- [ ] T6 · `[tool.ruff]`: `target-version = "py312"`, `line-length = 100`, `src = ["src", "tests"]`; `[tool.ruff.lint] select = ["E", "F", "W", "I", "UP", "B", "S", "TID", "ASYNC", "RUF"]`; `[tool.ruff.lint.flake8-tidy-imports.banned-api]` con las seis entradas y mensaje en español ("Prohibido fuera de core/crypto y core/security: usa core.crypto.bus o core.security"); `[tool.ruff.lint.per-file-ignores]` con `"src/app/core/crypto/**" = ["TID251"]`, `"src/app/core/security.py" = ["TID251"]` y `"tests/**" = ["S101"]` (solo `assert`, nunca `TID251`) — 2 h
- [ ] T7 · `[tool.mypy]`: `strict = true`, `python_version = "3.12"`, `files = ["src"]`, `plugins = ["pydantic.mypy"]`, `warn_unreachable = true` — 0,5 h
- [ ] T8 · `[tool.pytest.ini_options]`: `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`, `testpaths = ["tests"]`, `addopts = "-ra --strict-markers"`; `[tool.coverage.run] source = ["app"]`, `branch = true` — 0,5 h
- [ ] T9 · Paquete mínimo: `api/src/app/__init__.py`, `api/src/app/py.typed`, `api/src/app/core/__init__.py`, `api/src/app/modules/__init__.py`, `api/tests/__init__.py`, `api/tests/architecture/__init__.py` — 0,5 h
- [ ] T10 · `.pre-commit-config.yaml` en la raíz: hook `astral-sh/ruff-pre-commit` (`ruff` con `--fix` y `ruff-format`) limitado a `^api/`; hook local `mypy` con `language: system`, `entry: uv run --directory api mypy src`, `pass_filenames: false` (usa las dependencias del proyecto, no un entorno aislado sin stubs); hook `detect-private-key` de `pre-commit/pre-commit-hooks` (refuerza el criterio 6 de US-001); `pre-commit install` documentado en `CONTRIBUTING.md` — 2 h

### Seguridad
- [ ] T11 · Revisión: confirmar con `uv run ruff check .` que ningún archivo de `tests/` queda exento de `TID251`; confirmar que `uv.lock` no trae `python-telegram-bot`, `fpdf2` ni otro paquete LGPL/GPL (el chequeo automático llega con US-004) — 0,5 h

## Orden de ejecución
1. T4, T5 (proyecto y lock: sin esto no hay herramientas)
2. T9 (paquete mínimo para que mypy y pytest tengan qué revisar)
3. T6, T7, T8 (configuración de las herramientas)
4. T1, T2, T3 (pruebas; T2 y T3 primero en rojo con una configuración incompleta, luego en verde)
5. T10 (pre-commit sobre una base ya verde)
6. T11 (revisión final)

## Dependencias técnicas
- US-001 · Repositorio git y estructura: la carpeta `api/` y el `.gitignore` de `.venv/`.

## Endpoints
- Ninguno.

## Riesgos
- Coincidencia de submódulos en `banned-api`: si ruff no trata `cryptography.hazmat...` como cubierto por la entrada `cryptography`, un import profundo pasaría el lint — mitigación: T3 prueba explícitamente un import de submódulo; si falla, se agregan entradas por submódulo (`cryptography.hazmat`) en T6.
- Pruebas de criptografía en `tests/crypto/` (EP-02) que quieran vectores de referencia con `cryptography` directo chocarán con `TID251`: no hay excepción para `tests/` — mitigación: las pruebas del bus verifican por la API pública del bus; si EP-02 necesita una excepción para `tests/crypto/**`, la pide como cambio explícito de esta configuración y actualiza T2.
- mypy en pre-commit con entorno aislado (`mirrors-mypy`) no ve las dependencias y da falsos errores — mitigación: hook local con `uv run` (T10).
- Versiones de Python: el servidor y la imagen usan 3.12; una máquina con 3.13 como predeterminada puede crear el entorno con la versión equivocada — mitigación: `requires-python` con cota superior y `.python-version` con `3.12` en `api/`.

## Estimación
- Backend: 0,5 h
- Front: 0 h
- Pruebas: 3,5 h
- DevOps / seguridad: 8 h
- **Total: 12 h**

## Definición de hecho
- [ ] `cd api && uv sync` termina con código 0 en una máquina limpia y `git diff --exit-code uv.lock` no muestra cambios
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/test_smoke.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `pre-commit run --all-files` termina con código 0; con una función sin anotaciones en `api/src/app/x.py` termina con código distinto de 0 (se borra el archivo de control)
- [ ] `cd api && uv tree --no-dev --depth 1` no lista ruff, mypy, pytest ni pre-commit (criterio 7)
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app --cov-fail-under=80`
