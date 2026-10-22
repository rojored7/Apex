# Cómo contribuir

## Ramas

- `main` está protegida: nunca se hace push directo ni force push. Todo entra por pull request con la CI en verde.
- Ramas de trabajo: `feat/<tema>`, `fix/<tema>`, `chore/<tema>`. Cada sprint abre su rama desde `main` (por ejemplo `chore/sprint-00-cimientos`) después del merge del sprint anterior.
- El push de la rama y la apertura del PR los hace una persona. Los scripts del flujo (`scripts/workflow/`) nunca hacen push.

## Commits

Formato Conventional Commits: `<tipo>: <descripción>` o `<tipo>(<ámbito>): <descripción>`.

Tipos admitidos: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`.

Ejemplos:

```
feat(members): búsqueda por índice ciego del documento
test(core): pruebas de compute_status (rojo)
chore(checkpoint): S0-B1 core/config y core/clock
```

## Flujo por slice

1. Pruebas primero, en rojo, sobre stubs vacíos. Commit `test(<modulo>): ... (rojo)`.
2. Implementación hasta pasar `bash scripts/workflow/slice-gate.sh <modulo> [archivos de prueba...]`. Las pruebas de `api/tests/architecture` corren siempre.
3. `bash scripts/workflow/checkpoint-commit.sh "<slice>: <historias>"`. Solo funciona con el gate vigente y nunca sobre `main`.
4. Al cerrar una wave: `bash scripts/workflow/run-gates.sh` (api con cobertura global de `app` de al menos 80 % y `-m "not perf"`; scripts de infraestructura de `scripts/ci/`; front con lint, tsc, test con cobertura y build).

## Herramientas locales

```
cd api && uv sync
pre-commit install
```

`pre-commit` corre ruff (lint y formato), mypy y la detección de llaves privadas antes de cada commit.

## Dependencias y licencias

Solo se aceptan las licencias de la sección "Licencias" de `CLAUDE.md`. Toda dependencia nueva actualiza `NOTICE` con `bash scripts/ci/notice.sh` (la CI compara el archivo y falla si quedó desactualizado). Si la dependencia es MPL-2.0, se usa sin modificar y se agrega a `scripts/ci/licenses-exceptions.txt` con su justificación. La CI corre `bash scripts/ci/check-licenses-api.sh` sobre el runtime del api (lista blanca estricta: una licencia desconocida, `UNKNOWN` o `UNLICENSED`, también falla) y `npm run licenses` en `web/`.

## Secretos

Nunca se versiona un `.env`, un `.env.seed` (ni ningún `.env.*` salvo `.env.example` y `.env.seed.example`), una llave `.pem`, `.key` o `.kek`; `scripts/ci/check-key-files.sh` lo bloquea en pre-commit y en CI. `.env.seed` lleva solo `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` del primer seed, lo lee únicamente el servicio `tools` y se borra después del seed. Si un secreto llegó a un commit, se rota de inmediato y se avisa.
