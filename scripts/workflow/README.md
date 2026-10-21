# scripts/workflow

Gates del flujo (`/flow-new-project`, `/flow-update`). Cuatro scripts en Bash POSIX (`#!/usr/bin/env bash`, `set -euo pipefail`), con `-h`, modo `100755` en git y fin de línea LF. Ninguno hace push, `--force`, `--no-verify` ni `reset --hard`. Todos calculan la raíz con `git rev-parse --show-toplevel`, así que se pueden invocar desde cualquier carpeta del repositorio.

## slice-gate.sh `<modulo> [archivos de prueba...]`

Gate de un slice. Con lista de archivos corre solo esos archivos más `tests/architecture`; sin lista, la carpeta de pruebas del módulo más `tests/architecture`. `tests/architecture` corre siempre (A-5).

- api: `uv run ruff check`, `uv run ruff format --check` y `uv run mypy` sobre la ruta de código del módulo, y `uv run pytest` sobre la lista más `tests/architecture`.
- front: `npx eslint` solo sobre los archivos que toca el slice (`git diff --name-only` contra la base del slice, más los archivos sin seguimiento y la lista recibida); `npx tsc --noEmit -p tsconfig.slice.json`, donde `tsconfig.slice.json` es un archivo temporal que extiende `tsconfig.json` con `include` = carpetas del módulo más los archivos del slice (pasar archivos sueltos a `tsc` ignora `tsconfig.json`); y `npx vitest run` sobre los archivos de prueba de la lista (o las carpetas del módulo si no hay lista). La base del slice es `SLICE_BASE` si está definida, o `git merge-base HEAD main`.

Mapeo de módulos (A-01):
- `core/<x>`: `api/src/app/core/<x>.py` o `api/src/app/core/<x>/`; pruebas en `api/tests/core`.
- `crypto`: `api/src/app/core/crypto/`; pruebas en `api/tests/crypto`.
- `main`: `api/src/app/main.py`; pruebas en `api/tests/core`.
- `worker`: `api/src/app/worker/`; pruebas en `api/tests/worker`.
- `cli`: `api/src/app/cli.py`; pruebas en `api/tests/cli`.
- `architecture`: sin código; `api/tests/architecture`. Con lista, sirve para pruebas en la raíz de `api/tests/`, como `test_ci_database.py`.
- `<modulo>` (`auth`, `settings`, `members`, ...): `api/src/app/modules/<modulo>/`; pruebas en `api/tests/<modulo>`.
- `web/<feature>`: `web/src/features/<feature>`. `web/shared`: `web/src/shared`. `web/core`: `web/src/core`. `web/layouts`: `web/src/layouts`. `web/app`: `web/src/App.tsx`, `web/src/routes*`, `web/src/config`, `web/src/styles`, `index.html`, `web/tests/unit`, `web/tests/lint`.

Nombre válido: `^(web/)?[a-z][a-z0-9_-]*(/[a-z][a-z0-9_-]*)*$`. Cada archivo de la lista debe existir bajo `api/tests/` o bajo `web/`.

En verde escribe `.git/apex/slice-gate.ok` con el módulo y una huella del árbol de trabajo (`git diff HEAD` más los archivos sin seguimiento con su `hash-object`, resumidos con `git hash-object --stdin`).

## checkpoint-commit.sh `"<mensaje>"`

Crea `chore(checkpoint): <mensaje>` con `git add -A` solo si la rama no es `main`, existe el sello y la huella actual coincide con la del sello. Borra el sello al terminar. Antes de correrlo, `git status` debe mostrar solo cambios del slice.

## run-gates.sh `[wave]`

Suite completa: en `api/`, `ruff check .`, `ruff format --check .`, `mypy src` y `pytest --cov=app --cov-fail-under=80`; si existe `web/package.json`, en `web/`, `npm run lint`, `npx tsc --noEmit`, `npm test -- --run --coverage` y `npm run build`. Imprime qué gate falló.

Cobertura (M-6): el umbral es global sobre `app`. Hasta el Sprint 3, `[tool.coverage.run] omit` en `api/pyproject.toml` excluye `src/app/cli.py` y `src/app/worker/*`; esa exclusión se quita en el Sprint 4A (US-113), cuando entran a la cobertura. No existe una opción `--cov-omit` en pytest-cov: la exclusión vive en la configuración de coverage.

## validate-impact-analysis.sh `[--allow-amber] <archivo>`

Busca la primera línea `Veredicto: <valor>` (admite `## Veredicto:` y `**Veredicto:`). Acepta `VERDE`, `APROBADO` y `APROBADO CON OBSERVACIONES`; `AMARILLO` solo con `--allow-amber`; `ROJO`, `RECHAZADO`, otro valor o la ausencia de la línea fallan.

## Pruebas

`bash scripts/workflow/tests/run.sh` corre `tests/test_*.sh` con repositorios temporales en `tests/tmp/` y herramientas simuladas (`uv`, `npm`, `npx`, envoltorio de `git`). `test_permisos.sh` verifica el modo `100755`, `bash -n` y la ausencia de push. La CI corre la misma suite en el job `scripts` (US-003). En Windows, los permisos se fijan con `git update-index --chmod=+x scripts/workflow/*.sh`.
