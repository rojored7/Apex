# US-003 · Pipeline de CI con PostgreSQL 16 y build de imágenes — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-00-cimientos/US-003-pipeline-ci.md`
- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context / módulo:** ninguno de negocio, terreno (`.github/workflows/ci.yml`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El contenido del pipeline está fijado por "Calidad y Git" de `CLAUDE.md` y por `05_service_design.md` sección 7. Los jobs `web` e `images` se activan cuando existan sus archivos, así que la historia no espera a US-005, US-006 ni US-009. El chequeo de licencias queda explícitamente en US-004.

## Resumen

Un workflow `ci` que corre en cada `pull_request` y en cada `push` a `main` con tres jobs: `api` (uv con caché, ruff, formato, mypy, pytest con cobertura contra un servicio `postgres:16`), `web` (npm ci, lint, typecheck, Vitest, build y Playwright de humo, activo cuando exista `web/package.json`) e `images` (build sin push de `api/Dockerfile` y `web/Dockerfile`, activo cuando existan). Al cerrar, los tres jobs quedan como checks obligatorios en la protección de `main` de US-001.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md.
- Nota de coordinación: el job `web` incluye `npx tsc --noEmit` y el Playwright de humo porque la Definición de terminado de US-009 los exige "en CI"; no amplía el alcance de esta historia, solo deja el lugar donde US-009 los engancha.

## Validación contra el dominio

- No hay aggregates, entidades, value objects, invariantes RN-xx ni eventos.

## Validación contra la arquitectura

- Pruebas contra PostgreSQL 16 real, nunca SQLite: coincide con `CLAUDE.md` ("pytest con PostgreSQL de prueba") y `05_service_design.md` sección 6.
- Umbral de cobertura 80 % sobre `src/`: coincide con `CLAUDE.md` y las reglas globales; hoy aplica sobre el paquete mínimo de US-002.
- Sin secretos reales: las variables de prueba viven en el `env` del workflow; nada en `secrets` hasta EP-13 (si el despliegue lo necesita).
- La prueba de `docs/openapi.json` (US-021) y las de arquitectura (US-022, US-031, US-035) se suman a este job `api` cuando existan; no se crean aquí.

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
- No aplica.

### Tests de service con PostgreSQL
- [ ] T1 · `api/tests/test_ci_database.py::test_database_url_apunta_a_postgres16`: marcada `@pytest.mark.db`, se salta si no hay `DATABASE_URL`; con `asyncpg.connect` (sin pasar por `core/db.py`, que aún no existe) ejecuta `SHOW server_version` y exige que empiece por `16.` y que el esquema de la URL sea `postgresql`; cubre el criterio 2 y el escenario "Pruebas contra PostgreSQL real". US-012 la reemplaza por la fixture de sesión de `conftest.py` — 1 h

### Tests de router
- No aplica.

### Tests de arquitectura
- No aplica (el job `api` ya corre `tests/architecture` de US-002; las nuevas se agregan solas al estar bajo `tests/`).

### Front
- No aplica (solo el job de CI del front, en DevOps).

### DevOps
- [ ] T2 · `.github/workflows/ci.yml` base: `on: pull_request` (rama `main`) y `push` (rama `main`); `concurrency` por rama con `cancel-in-progress: true`; `permissions: contents: read`; `defaults.run.shell: bash` — 1 h
- [ ] T3 · Job `api`: `runs-on: ubuntu-24.04`; `services.postgres` con `image: postgres:16`, `POSTGRES_USER=apex`, `POSTGRES_PASSWORD=apex-ci`, `POSTGRES_DB=apex_test`, `options: --health-cmd "pg_isready -U apex" --health-interval 5s --health-retries 10`, puerto `5432:5432`; `env.DATABASE_URL=postgresql+asyncpg://apex:apex-ci@localhost:5432/apex_test`; pasos `actions/checkout`, `astral-sh/setup-uv` con `enable-cache: true` y `cache-dependency-glob: api/uv.lock`, `uv sync --frozen`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest --cov=app --cov-report=xml --cov-report=term --cov-fail-under=80` con `working-directory: api` — 2,5 h
- [ ] T4 · Publicación de cobertura del job `api`: `actions/upload-artifact` con `api/coverage.xml` y resumen en `$GITHUB_STEP_SUMMARY` (criterio 4) — 0,5 h
- [ ] T5 · Job `web`: `if: hashFiles('web/package.json') != ''`; `actions/setup-node` con Node 22 y caché `npm` sobre `web/package-lock.json`; `npm ci`, `npm run lint`, `npx tsc --noEmit`, `npm test -- --run`, `npm run build`, `npx playwright install --with-deps chromium`, `npm run e2e` con `working-directory: web` (un job saltado por `if` cuenta como exitoso para los checks obligatorios) — 2 h
- [ ] T6 · Job `images`: `needs: [api]`; `docker/setup-buildx-action`; `docker/build-push-action` con `push: false`, `context: api`, `file: api/Dockerfile`, caché `type=gha`, condicionado a `hashFiles('api/Dockerfile') != ''`; segundo paso igual para `web/Dockerfile` con `context: .` (la imagen del front necesita `infra/nginx/default.conf`, ver US-006), condicionado a `hashFiles('web/Dockerfile') != ''` — 1,5 h
- [ ] T7 · Gancho para el smoke de Compose en el job `images` (lo llenan US-005 y US-006): paso `scripts/ci/compose-smoke.sh` condicionado a que exista el archivo, con `cp .env.example .env` previo; aquí solo se deja el paso y su condición — 0,5 h
- [ ] T8 · Actualizar `infra/github/main-protection.json` de US-001 con `required_status_checks.contexts = ["api", "web", "images"]` y `strict = true`; aplicar con `gh api -X PUT repos/rojored7/Apex/branches/main/protection --input infra/github/main-protection.json` — 0,5 h
- [ ] T9 · PR de control: rama `chore/ci-control` con una prueba que falla (`assert False`) y otra con un error de ruff; verificar que el PR queda en rojo y que el botón de fusionar está bloqueado; capturas o enlaces en la descripción del PR; cerrar sin fusionar — 1 h
- [ ] T10 · Medir el tiempo del pipeline en un PR trivial (objetivo menor de 10 minutos, criterio 7) y anotarlo en el PR; si pasa de 10, revisar cachés de uv, npm, Playwright y buildx — 0,5 h

### Seguridad
- [ ] T11 · Revisión del workflow: `permissions` mínimos, acciones de terceros fijadas a versión mayor de los publicadores oficiales (`actions/*`, `astral-sh/*`, `docker/*`), sin `pull_request_target`, ningún valor de `secrets.*`, la contraseña de PostgreSQL de CI es un marcador sin valor fuera de CI — 1 h

## Orden de ejecución
1. T1 (prueba que exige PostgreSQL 16; en local se salta sin `DATABASE_URL`)
2. T2, T3, T4 (job `api`, el único con contenido real hoy)
3. T5, T6, T7 (jobs condicionados; quedan en verde o saltados)
4. T11 (revisión antes de exigir los checks)
5. T8 (checks obligatorios en `main`)
6. T9, T10 (PR de control y medición)

## Dependencias técnicas
- US-002 · Proyecto api con uv, ruff, mypy y pytest: lo que corre el job `api`.
- US-001 · Repositorio git y estructura: la protección de `main` donde se registran los checks.
- US-005 · Dockerfile del api y Compose, US-006 · Nginx e imagen del front, US-009 · Esqueleto del front: activan los jobs `images` y `web` cuando llegan (no bloquean esta historia).

## Endpoints
- Ninguno.

## Riesgos
- Checks obligatorios con nombre distinto al del job: GitHub registra el check por el `name` del job; si se renombra, `main` queda bloqueada para siempre — mitigación: nombres fijos `api`, `web`, `images` y T8 después de la primera corrida en verde.
- La protección de `main` depende del plan de GitHub (ver riesgo de US-001) — mitigación: la misma que en US-001; sin protección, el workflow igual corre pero no bloquea.
- Tiempo del job `web` con Playwright (descarga de navegadores) puede empujar el total sobre 10 minutos — mitigación: solo Chromium y caché de `~/.cache/ms-playwright` por versión de `@playwright/test`.
- El umbral de 80 % con un solo archivo trivial da una cifra engañosa — mitigación: se acepta en este sprint (criterio 4); el umbral se vuelve real desde EP-01.

## Estimación
- Backend: 0 h
- Front: 0 h
- Pruebas: 2 h
- DevOps / seguridad: 10 h
- **Total: 12 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && DATABASE_URL=postgresql+asyncpg://apex:apex-ci@localhost:5432/apex_test uv run pytest tests/test_ci_database.py -q` contra un `postgres:16` local en verde
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `gh workflow view ci` muestra el workflow y `gh run list --workflow ci --limit 1` muestra la última corrida en `success`
- [ ] El PR de control (`chore/ci-control`) queda en rojo y `gh pr view <n> --json mergeStateStatus` devuelve `BLOCKED`
- [ ] `gh api repos/rojored7/Apex/branches/main/protection/required_status_checks` lista `api`, `web` e `images`
- [ ] Tiempo total del pipeline en el PR trivial anotado en el PR y menor de 10 minutos
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app --cov-fail-under=80`
