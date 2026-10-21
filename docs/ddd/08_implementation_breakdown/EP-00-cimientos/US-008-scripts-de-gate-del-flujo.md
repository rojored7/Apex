# US-008 · Scripts de gate del flujo en `scripts/workflow/` — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-00-cimientos/US-008-scripts-de-gate-del-flujo.md`
- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context / módulo:** ninguno de negocio, terreno (`scripts/workflow/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Tres de los cuatro scripts están completamente definidos. `validate-impact-analysis.sh` no: la historia supone que el veredicto tiene la forma del plan-critic (`Veredicto: APROBADO` o `APROBADO CON OBSERVACIONES`), pero el único análisis de impacto real del proyecto, `docs/ddd/00b_impact_analysis.md`, usa la escala de semáforo (`## Veredicto: AMARILLO`) y su texto dice que se avanza "con `--allow-amber`". Con el patrón de la historia, el script rechazaría el análisis de impacto que ya existe. DECISIONES.md no fija el formato. Resuelto en DECISIONES E (refinamiento US-008); ver "Preguntas abiertas".

## Resumen

Cuatro scripts POSIX en Bash (`#!/usr/bin/env bash`, `set -euo pipefail`) con ayuda por `-h`, permiso de ejecución en git y códigos de salida distintos de 0 al fallar: `slice-gate.sh <modulo> [archivos de prueba...]` (ruff, formato, mypy y pytest del módulo, más `tests/architecture`; ver Ajuste A-01), `checkpoint-commit.sh "<mensaje>"` (solo si el gate del slice pasó sobre el estado actual, nunca en `main`, nunca push), `run-gates.sh` (suite completa del api con cobertura 80 % y del front si existe) y `validate-impact-analysis.sh <archivo>` (existe y tiene un veredicto aprobado). Pruebas de los scripts en `scripts/workflow/tests/` con repositorios temporales y herramientas simuladas, ejecutadas en CI y válidas en Git Bash y Linux.

## Correcciones aplicadas por DECISIONES.md

- Refinamiento E (US-008): `validate-impact-analysis.sh` acepta `VERDE`, `APROBADO` y `APROBADO CON OBSERVACIONES`; `AMARILLO` solo con `--allow-amber`; `ROJO`, `RECHAZADO`, cualquier otro valor o la ausencia de la línea fallan (ver "Preguntas abiertas"). Ajuste A-01 del plan de sprints: ver su sección.
- Precisión de diseño (no cambia el alcance): "verifica que `slice-gate` pasó" se implementa con un sello: `slice-gate.sh` escribe al terminar en verde `.git/apex/slice-gate.ok` con el módulo y una huella del árbol de trabajo (`git stash create` o `git diff HEAD` más la lista de archivos sin seguimiento, resumidos con `git hash-object --stdin`); `checkpoint-commit.sh` recalcula la huella y se niega si no coincide o si no hay sello. Así la firma del script sigue siendo `checkpoint-commit.sh "<mensaje>"`.

## Validación contra el dominio

- No hay aggregates, entidades, value objects, invariantes RN-xx ni eventos.

## Validación contra la arquitectura

- `05_service_design.md` sección 7 nombra los cuatro scripts; `00b_impact_analysis.md` ("Gate verificado manualmente") describe qué hacía cada uno a mano. Coinciden con el alcance de la historia.
- Mapeo de módulo a rutas: `members` → `src/app/modules/members` y `tests/members`; `core/<x>` → `src/app/core/<x>` (o `<x>.py`) y `tests/core`; `crypto` → `src/app/core/crypto` y `tests/crypto` (coincide con el árbol de `tests/` de `05_service_design.md` sección 2). El mapeo completo de A-01 (api y front) prevalece sobre esta lista.
- Umbral de cobertura 80 % de `CLAUDE.md` y reglas globales, aplicado en `run-gates.sh`.
- No se usa ShellCheck (GPL-3.0) en CI: sintaxis con `bash -n` y pruebas de comportamiento (ver US-004).
- Sin módulos de negocio, sin bus, sin roles, sin paginación ni auditoría: no aplica.

## Preguntas abiertas

- Pregunta: ¿qué veredictos acepta `validate-impact-analysis.sh`? El plan-critic devuelve `APROBADO`, `APROBADO CON OBSERVACIONES` o `RECHAZADO`; el análisis de impacto de la Fase 0 devuelve `VERDE`, `AMARILLO` o `ROJO` (`docs/ddd/00b_impact_analysis.md` tiene `## Veredicto: AMARILLO`). Alternativa por defecto propuesta: el script busca la primera línea que coincida con `^(#+ *)?Veredicto: *` (con o sin encabezado Markdown) y acepta `APROBADO`, `APROBADO CON OBSERVACIONES` y `VERDE`; `AMARILLO` pasa solo con la opción `--allow-amber`; `RECHAZADO`, `ROJO`, cualquier otro valor o la ausencia de la línea fallan. Con esa regla, `validate-impact-analysis.sh --allow-amber docs/ddd/00b_impact_analysis.md` termina en 0.
- Resuelta (DECISIONES E, refinamiento US-008): `validate-impact-analysis.sh` acepta `VERDE`, `APROBADO` y `APROBADO CON OBSERVACIONES`; `AMARILLO` solo con `--allow-amber`; `ROJO`, `RECHAZADO`, cualquier otro valor o la ausencia de la línea fallan. La alternativa propuesta queda como regla fija.

## Ajuste A-01 del plan de sprints

Fuente: `docs/ddd/09_sprint_plan/README.md`, sección "A-01 · `slice-gate.sh` ampliado" (contenido íntegro). Las tareas T2, T4, T8, T10 y T14 lo aplican.

**Firma:** `scripts/workflow/slice-gate.sh <modulo> [archivos de prueba...]`.
- Con lista de archivos, corre solo esos archivos más `tests/architecture`.
- Sin lista, corre la carpeta de pruebas del módulo más `tests/architecture`.
- **`tests/architecture` corre siempre (A-5).** Así, las mitigaciones que dependen de pruebas de arquitectura, por ejemplo `test_members_encrypted_at_rest.py` o `test_service_import_graph.py`, bloquean de verdad cada checkpoint.

**Qué corre:**
- api: `uv run ruff check`, `uv run ruff format --check` y `uv run mypy` sobre la ruta de código del módulo, y después `uv run pytest` sobre la lista de archivos más `tests/architecture`;
- front: `npx eslint` solo sobre los archivos que el slice toca (`git diff --name-only` contra la base del slice, más la lista de archivos); `npx tsc --noEmit -p tsconfig.slice.json`, donde el script genera `tsconfig.slice.json` temporal que extiende `tsconfig.json` con `include` = archivos del slice (pasar archivos sueltos a `tsc` ignora `tsconfig.json`; CRITICA-2 O-1); y después `npx vitest run` sobre la lista de archivos.

**Mapeo de módulos** (se escribe como lista para respetar la regla de formato: sin tablas fuera del índice):
- api:
  - `core/<x>`: código en `api/src/app/core/<x>.py` o en `api/src/app/core/<x>/`; pruebas en `api/tests/core`.
  - `crypto`: código en `api/src/app/core/crypto/`; pruebas en `api/tests/crypto`.
  - `<modulo>` (`auth`, `settings`, `members`, `plans`, `memberships`, `payments`, `audit` y, desde v0.2, los demás): código en `api/src/app/modules/<modulo>/`; pruebas en `api/tests/<modulo>`.
  - `dashboard`: código en `api/src/app/modules/dashboard/`; pruebas en `api/tests/dashboard`.
  - `main`: código en `api/src/app/main.py`; pruebas en `api/tests/core`, en los archivos de arranque y salud. Reemplaza al antiguo `core/main`.
  - `worker`: código en `api/src/app/worker/`; pruebas en `api/tests/worker`.
  - `cli`: código en `api/src/app/cli.py`; pruebas en `api/tests/cli`.
  - `architecture`: sin ruta de código propia, solo `api/tests/architecture`. Con lista de archivos, sirve para pruebas que viven en la raíz de `api/tests/`, como `test_ci_database.py`.
  - Pruebas fuera de la carpeta del módulo (`tests/migrations`, `tests/integration`): se pasan por la lista de archivos.
- front:
  - `web/<feature>`: `web/src/features/<feature>`. Por ejemplo, `web/auth`, `web/system`, `web/members`, `web/plans`, `web/memberships`, `web/payments` y `web/dashboard`.
  - `web/shared`: `web/src/shared`.
  - `web/core`: `web/src/core`.
  - `web/layouts`: `web/src/layouts`.
  - `web/app`: `web/src/App.tsx`, `web/src/routes*`, `web/src/config`, `web/src/styles` e `index.html`, más `web/tests/unit` y `web/tests/lint`.

**Validación del nombre** (reemplaza la de T14 de US-008): `^(web/)?[a-z][a-z0-9_-]*(/[a-z][a-z0-9_-]*)*$`. Acepta guiones y varios niveles. Cada archivo de la lista debe existir dentro de `api/tests/` o de `web/`.

**Notación única en todos los sprints:** `web/<feature>`, no `web/features/<x>`, y `main`, no `core/main`.

**Cobertura:**
- `run-gates.sh` aplica `--cov=app --cov-fail-under=80`.
- Desde el Sprint 0 y hasta el Sprint 3, usa `--cov-omit=src/app/cli.py,src/app/worker/*`.
- El ajuste se documenta en `scripts/workflow/README.md` y en US-008.

**Costo estimado:** entre 3 y 4 h dentro de US-008. No cambia otras historias.

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
- [ ] T1 · `scripts/workflow/tests/lib.sh`: utilidades de prueba sin dependencias externas: `mk_repo` (repositorio git temporal en `scripts/workflow/tests/tmp/` con rama `feat/x` y un commit), `stub_tool <nombre> <código>` (crea en un directorio de `PATH` un `uv` o `npm` falso que registra los argumentos y sale con el código pedido), `assert_exit <esperado> <comando...>`, `assert_no_new_commit` — 1,5 h
- [ ] T2 · `scripts/workflow/tests/test_slice_gate.sh`: con `uv` simulado en verde termina en 0 y escribe el sello; con `uv` que falla en `mypy` termina distinto de 0 y no escribe sello; sin argumento muestra ayuda y sale con 2; `-h` muestra ayuda y sale con 0; módulo inexistente falla con mensaje (criterio 2); casos de lista de archivos (con lista corre solo esos archivos más `tests/architecture`; sin lista, la carpeta del módulo más `tests/architecture`; `tests/architecture` corre siempre); mapeo de A-01 (`main` a `api/tests/core`, `web/<feature>` a `web/src/features/<feature>`); regex `^(web/)?[a-z][a-z0-9_-]*(/[a-z][a-z0-9_-]*)*$` con guiones, varios niveles y rama `web/`; archivo de prueba inexistente falla — 1,5 h
- [ ] T3 · `scripts/workflow/tests/test_checkpoint_commit.sh`: en `main` falla y no crea commit; sin sello falla; con sello de otro estado del árbol falla; con sello vigente crea un commit `chore(checkpoint): <mensaje>` y no ejecuta `git push` (un `git` envoltorio en `PATH` registra los subcomandos y la prueba exige que `push` no aparezca) (criterio 3) — 1,5 h
- [ ] T4 · `scripts/workflow/tests/test_run_gates.sh`: con `uv` simulado que falla en `pytest --cov-fail-under=80` termina distinto de 0; sin `web/package.json` no invoca `npm`; con `web/package.json` invoca `npm run lint`, `npx tsc --noEmit -p tsconfig.json`, `npm test` y `npm run build` (criterio 4); `pytest` lleva `--cov-omit=src/app/cli.py,src/app/worker/*` hasta el Sprint 3 y no lo lleva desde el Sprint 4A — 1,5 h
- [ ] T5 · `scripts/workflow/tests/test_validate_impact.sh`: archivo inexistente falla; sin línea de veredicto falla; `Veredicto: APROBADO` y `Veredicto: APROBADO CON OBSERVACIONES` pasan; `Veredicto: RECHAZADO` falla; casos de semáforo según la respuesta a la pregunta abierta (por defecto: `VERDE` pasa, `AMARILLO` falla sin `--allow-amber` y pasa con ella, `ROJO` falla); el archivo real `docs/ddd/00b_impact_analysis.md` como caso de regresión (criterio 5) — 1 h
- [ ] T6 · `scripts/workflow/tests/run.sh`: ejecuta todas las pruebas `test_*.sh`, imprime resumen y sale distinto de 0 si alguna falla; limpia `tests/tmp/` — 0,5 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T7 · `scripts/workflow/tests/test_permisos.sh`: `git ls-files -s scripts/workflow/*.sh` muestra modo `100755` para los cuatro; `bash -n` sin errores en cada script; ninguno contiene `git push` (criterio 1 y regla de "sin push") — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T8 · `scripts/workflow/slice-gate.sh <modulo> [archivos de prueba...]`: valida el nombre con la regex de A-01 y que cada archivo exista bajo `api/tests/` o `web/`; resuelve rutas de código y pruebas según el mapeo de A-01; corre desde `api/` `uv run ruff check <ruta>`, `uv run ruff format --check <ruta>` y `uv run mypy <ruta>` acotados a la ruta del módulo, y `uv run pytest <archivos o carpeta del módulo> tests/architecture -q` (`tests/architecture` siempre); el front sigue A-01 (eslint, `tsc -p tsconfig.slice.json`, vitest); en verde escribe el sello `.git/apex/slice-gate.ok`; `-h` con uso y ejemplos — 3 h
- [ ] T9 · `scripts/workflow/checkpoint-commit.sh "<mensaje>"`: rechaza si `git rev-parse --abbrev-ref HEAD` es `main`; recalcula la huella y la compara con el sello; `git add -A`; `git commit -m "chore(checkpoint): <mensaje>"`; borra el sello; nunca push; `-h` — 1 h
- [ ] T10 · `scripts/workflow/run-gates.sh`: api completo (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest --cov=app --cov-fail-under=80 --cov-omit=src/app/cli.py,src/app/worker/*` (`--cov-omit` solo hasta el Sprint 3 incluido)) y, si existe `web/package.json`, `npm run lint`, `npx tsc --noEmit -p tsconfig.json` (proyecto completo), `npm test -- --run --coverage`, `npm run build`; imprime qué gate falló; `-h` — 1,5 h
- [ ] T11 · `scripts/workflow/validate-impact-analysis.sh [--allow-amber] <archivo>`: implementa la regla de la pregunta abierta (por defecto, la alternativa propuesta); mensaje claro con el veredicto encontrado; `-h` — 0,5 h
- [ ] T12 · Permisos y fin de línea: `git update-index --chmod=+x scripts/workflow/*.sh` (en Windows `chmod` no llega a git) y confirmación de que `.gitattributes` de US-001 fuerza `eol=lf` en `*.sh`; `scripts/workflow/README.md` con uso de los cuatro — 0,5 h
- [ ] T13 · Paso en CI: job `scripts` en `.github/workflows/ci.yml` (Ubuntu) que corre `bash scripts/workflow/tests/run.sh`; verificación manual en Git Bash de Windows anotada en el PR (criterio 6) — 1 h

### Seguridad
- [ ] T14 · Revisión: ningún script ejecuta `git push`, `--force`, `--no-verify` ni `reset --hard`; los argumentos se citan (`"$1"`) para evitar inyección por nombres de módulo; el nombre del módulo se valida con `^(web/)?[a-z][a-z0-9_-]*(/[a-z][a-z0-9_-]*)*$` (guiones y varios niveles) y cada archivo de prueba debe existir bajo `api/tests/` o `web/` antes de construir rutas — 1 h

## Orden de ejecución
1. T1 (utilidades de prueba)
2. T2, T3, T4, T5, T7 (pruebas en rojo)
3. T8, T9, T10, T11 (scripts)
4. T12 (permisos y fin de línea)
5. T6 (runner)
6. T13 (CI y verificación en Git Bash)
7. T14 (revisión)

## Dependencias técnicas
- US-002 · Proyecto api con uv, ruff, mypy y pytest: las herramientas que invocan los scripts.
- US-001 · Repositorio git y estructura: `.gitattributes` con `eol=lf` y la carpeta `scripts/workflow/`.
- US-003 · Pipeline CI: workflow donde se agrega el job `scripts`.
- US-009 · Esqueleto del front: rama de `run-gates.sh` para `web/` (solo se activa si existe `web/package.json`).

## Endpoints
- Ninguno.

## Riesgos
- Pregunta abierta sobre el formato del veredicto: si se implementa solo el patrón del plan-critic, el análisis de impacto real del proyecto falla el gate — mitigación: T11 implementa la alternativa propuesta por defecto y T5 incluye el archivo real como regresión; si el gate elige otra cosa, cambia una expresión regular y sus casos de prueba.
- La huella del sello con `git stash create` no incluye archivos sin seguimiento: un archivo nuevo agregado después del gate pasaría sin verificar — mitigación: la huella suma `git ls-files --others --exclude-standard` con el contenido de cada archivo.
- Diferencias de Git Bash: `mktemp`, `sed -i` y rutas con espacios se comportan distinto — mitigación: utilidades propias en `lib.sh`, sin `sed -i`, y prueba manual en Git Bash (T13).
- `uv run` dentro de los scripts usa el Python del entorno de `api/`: si alguien corre el script desde otra carpeta falla — mitigación: los scripts calculan la raíz con `git rev-parse --show-toplevel` y hacen `cd` explícito.

## Estimación
- Backend: 0 h
- Front: 0 h
- Pruebas: 8 h
- DevOps / seguridad: 8,5 h
- **Total: 16,5 h**

## Definición de hecho
- [ ] `bash scripts/workflow/tests/run.sh` termina con código 0
- [ ] `git ls-files -s scripts/workflow/slice-gate.sh scripts/workflow/checkpoint-commit.sh scripts/workflow/run-gates.sh scripts/workflow/validate-impact-analysis.sh` muestra `100755` en las cuatro líneas
- [ ] `bash scripts/workflow/slice-gate.sh -h && bash scripts/workflow/checkpoint-commit.sh -h && bash scripts/workflow/run-gates.sh -h && bash scripts/workflow/validate-impact-analysis.sh -h` terminan con código 0
- [ ] `git switch main && bash scripts/workflow/checkpoint-commit.sh "control"; echo $?` imprime un código distinto de 0 y `git log -1` no cambia
- [ ] `bash scripts/workflow/validate-impact-analysis.sh --allow-amber docs/ddd/00b_impact_analysis.md` termina con código 0 (según la respuesta a la pregunta abierta)
- [ ] `bash scripts/workflow/run-gates.sh` termina con código 0 sobre `main` actualizado
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Prueba en Git Bash de Windows anotada en el PR
