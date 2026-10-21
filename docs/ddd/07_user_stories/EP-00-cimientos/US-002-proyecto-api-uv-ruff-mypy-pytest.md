# US-002 · Como equipo quiero el proyecto `api` con uv, ruff con `banned-api`, mypy estricto, pytest y pre-commit para que el código defectuoso o que salta el bus de criptografía no pase del primer commit

- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context:** ninguno de negocio (`api/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `api/pyproject.toml` gestionado con `uv`, con ruff (lint y formato, `flake8-tidy-imports` banned-api), `mypy --strict`, `pytest` en modo asyncio y `pre-commit`
para que cada commit pase las mismas reglas y nadie importe primitivas criptográficas fuera de `core/crypto` y `core/security`

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** regla 8 del bus de criptografía de `CLAUDE.md` (prohibido importar `cryptography`, `oqs`, `hashlib`, `hmac`, `jwt`, `argon2` fuera de `core/crypto` y `core/security`); stack fijo de `CLAUDE.md` (Python 3.12); "Calidad y Git".
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `api/pyproject.toml` con Python 3.12, dependencias de runtime del stack fijo (FastAPI, SQLAlchemy 2 async, asyncpg, Alembic, Pydantic v2, pydantic-settings, Uvicorn, APScheduler, httpx, argon2-cffi, PyJWT, cryptography) y grupo de desarrollo (ruff, mypy, pytest, pytest-asyncio, pytest-cov, pre-commit); `uv.lock` versionado; configuración de ruff con `[tool.ruff.lint.flake8-tidy-imports.banned-api]` y excepción por `per-file-ignores` para `src/app/core/crypto/**` y `src/app/core/security.py`; `mypy --strict` sobre `src/`; `pytest` con `asyncio_mode = "auto"`; `src/app/__init__.py`, `tests/test_smoke.py` trivial; `.pre-commit-config.yaml` en la raíz con ruff (check y format) y mypy.
- **Front:** No aplica.

## Criterios de aceptación

1. En una máquina limpia, `cd api && uv sync` instala todo sin errores y genera o respeta `uv.lock`.
2. `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` y `uv run pytest` terminan con código 0.
3. Un archivo de prueba en `src/app/modules/x/service.py` con `import hashlib` hace fallar `ruff check` con la regla `TID251`; el mismo import en `src/app/core/crypto/bus.py` no falla.
4. Los seis módulos `cryptography`, `oqs`, `hashlib`, `hmac`, `jwt`, `argon2` están en la lista `banned-api`.
5. `mypy` corre con `strict = true` y rechaza una función sin anotaciones en `src/`.
6. `pre-commit run --all-files` ejecuta ruff y mypy y falla si alguno falla.
7. Las dependencias de runtime y de desarrollo están separadas (`[project.dependencies]` y `[dependency-groups] dev`).

## Escenarios BDD

```gherkin
# language: es
Característica: Calidad del backend desde el primer commit

  Escenario: Proyecto limpio en verde
    Dado un clon limpio con uv instalado
    Cuando ejecuto "uv sync" y luego ruff, mypy y pytest
    Entonces los cuatro comandos terminan con código 0

  Escenario: Import prohibido fuera del bus
    Dado un módulo "app/modules/members/service.py" que importa "hashlib"
    Cuando ejecuto "uv run ruff check ."
    Entonces ruff falla con la regla TID251
    Y el mensaje indica usar el bus de criptografía

  Escenario: Import permitido dentro del bus
    Dado el archivo "app/core/crypto/bus.py" que importa "hmac"
    Cuando ejecuto "uv run ruff check ."
    Entonces ruff no reporta TID251 para ese archivo

  Escenario: Función sin tipos rechazada
    Dado una función sin anotaciones en "src/app"
    Cuando ejecuto "uv run mypy src"
    Entonces mypy falla con error de función sin tipos
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** `tests/test_smoke.py`; prueba manual del caso prohibido documentada en el PR (la prueba de arquitectura definitiva es US-031).
- **Archivos principales:** `api/pyproject.toml`, `api/uv.lock`, `.pre-commit-config.yaml`, `api/tests/test_smoke.py`.

## Supuestos

- Ninguno.

## Dependencias

- US-001 · Repositorio git y estructura (carpeta `api/`).

## INVEST

- **Independiente:** solo necesita el repositorio.
- **Negociable:** versiones exactas y reglas adicionales de ruff.
- **Valiosa:** impide desde el día uno el error más caro del proyecto (cifrar fuera del bus).
- **Estimable:** configuración conocida.
- **Pequeña:** uno o dos días.
- **Testeable:** comandos con código de salida.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] `pytest` en verde
- [ ] `pre-commit` instalado y probado
- [ ] Revisión de PR aprobada
