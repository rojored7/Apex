# US-005 · Imagen del api y Compose de producción y desarrollo — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-00-cimientos/US-005-dockerfile-api-y-compose.md`
- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context / módulo:** ninguno de negocio, terreno (`api/Dockerfile`, `api/.dockerignore`, `infra/compose.yml`, `infra/compose.dev.yml`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

La topología está fijada en `04_architecture_decision.md` sección 4 y el riesgo 4 de `00b_impact_analysis.md` decide la KEK en volumen nombrado. El único supuesto de la historia (healthcheck en `/health` sin prefijo) lo confirma DECISIONES N-16. Lo que falta para que `api` y `worker` corran de verdad (US-020 y US-113) se cubre con un marcador mínimo y un perfil de Compose, sin cambiar el alcance.

## Resumen

Imagen del api en dos etapas con `uv` (builder con `uv sync --frozen --no-dev`, runtime `python:3.12-slim` con usuario `apex` UID 10001, sin compiladores ni grupo `dev`), una sola imagen para `api` y `worker` con comandos distintos. `infra/compose.yml` con `db` (PostgreSQL 16, volumen `pgdata`, `pg_isready`), `api` (healthcheck HTTP a `/health`), `worker` y `web` (lo completa US-006), volúmenes nombrados `pgdata`, `uploads`, `keys` y `backups`, `restart: unless-stopped` y sin publicar el puerto de PostgreSQL. `infra/compose.dev.yml` con recarga en caliente, puertos 8000 y 5432 abiertos y `db_test` efímero para pytest.

## Correcciones aplicadas por DECISIONES.md

- Supuesto de la historia: healthcheck de `api` en `/health` sin prefijo → se confirma: `/health` existe en la raíz y en `/api/v1/health`; el healthcheck del contenedor usa `/health` y Nginx (US-006) usa `/api/v1/health`: corregido por DECISIONES N-16 (confirmación).
- Ninguna otra; la historia ya es coherente con DECISIONES.md.

## Validación contra el dominio

- No hay aggregates, entidades, value objects, invariantes RN-xx ni eventos.
- RN-13 (datos cifrados) depende de que la KEK no viaje en la imagen: se cumple con el volumen `keys` montado en solo lectura y `.dockerignore` que excluye `.env`, `keys/` y `*.key`.

## Validación contra la arquitectura

- Vista de despliegue de `04_architecture_decision.md` sección 4: `nginx` (servicio `web`), `api`, `worker` (misma imagen, comando worker), `db`; `backup` es de EP-13 (US-114) y `openbao` de EP-15. Aquí solo se declara el volumen `backups`.
- "Seguridad" de `CLAUDE.md` y sección 6 de `04_architecture_decision.md`: secretos por `.env` y volumen, nunca por imagen. `env_file` apunta a `../.env` (relativo a `infra/`).
- Usuario no root con UID fijo para que el archivo de KEK con modo 600 (lo crea `cli init-keys`, US-023) tenga dueño estable.
- Las migraciones al arrancar son de US-020 (`create_app()`); el arranque ordenado y `depends_on` estrictos son de US-118. Aquí `api` espera a `db` `healthy` y nada más.
- Sin módulos, sin bus, sin roles, sin paginación ni auditoría: no aplica.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Marcador `api/src/app/main.py` con `app = FastAPI(title="APEX")` y comentario `# Reemplazado por create_app() en US-020`, para que `uvicorn app.main:app` arranque antes de US-020 (criterio 3: "antes, el contenedor arranca"); tipado estricto para mypy — 0,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T2 · `api/tests/test_main_placeholder.py::test_app_es_fastapi`: importa `app.main.app` y verifica que es instancia de `FastAPI`; US-020 la reemplaza por las pruebas de `create_app()` — 0,5 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T3 · `scripts/ci/tests/test_compose_config.sh`: corre `docker compose -f infra/compose.yml config --format json` y con `jq` verifica que `db` no tiene `ports`, que `keys` está montado con `read_only: true` en `api` y `worker`, que `api` y `worker` usan la misma `image`, que los volúmenes `pgdata`, `uploads`, `keys` y `backups` están declarados, y que `db_test` no existe en `compose.yml`; con `-f infra/compose.dev.yml` verifica que `db_test` no tiene volúmenes (criterios 4 a 8) — 2 h
- [ ] T4 · `scripts/ci/tests/test_api_image.sh`: construye `api/Dockerfile`, exige `docker run --rm apex-api:ci id -u` distinto de 0, que `docker run --rm apex-api:ci sh -c 'find / -xdev \( -name ".env" -o -name "*.key" -o -name "*.pem" \) 2>/dev/null'` no devuelva nada y que `docker run --rm apex-api:ci python -c "import importlib.util,sys; sys.exit(any(importlib.util.find_spec(m) for m in ['pytest','ruff','mypy']))"` termine en 0 (criterios 1 y 2) — 1,5 h

### Front
- No aplica.

### DevOps
- [ ] T5 · `api/Dockerfile` etapa `builder`: `FROM python:3.12-slim AS builder`, `COPY --from=ghcr.io/astral-sh/uv:<versión fija> /uv /bin/uv`, `ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never`, `WORKDIR /app`, `COPY pyproject.toml uv.lock ./`, `uv sync --frozen --no-dev --no-install-project` (capa de dependencias cacheable), `COPY src ./src`, `uv sync --frozen --no-dev` — 2,5 h
- [ ] T6 · `api/Dockerfile` etapa `runtime`: `FROM python:3.12-slim`, usuario `apex` con UID y GID 10001, `mkdir -p /run/apex/keys /data/uploads && chown apex:apex` (Docker copia la propiedad del punto de montaje a un volumen nombrado vacío), `COPY --from=builder --chown=apex:apex /app /app`, `ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1`, `USER apex`, `EXPOSE 8000`, `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]` (la lista de proxies confiables la ajusta US-036 con `FORWARDED_ALLOW_IPS`, N-14) — 1,5 h
- [ ] T7 · `api/.dockerignore`: `.venv`, `.env`, `.env.*`, `keys/`, `*.key`, `*.pem`, `tests/`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.coverage`, `coverage.xml`, `__pycache__` — 0,5 h
- [ ] T8 · `infra/compose.yml` servicio `db`: `image: postgres:16`, `env_file: ../.env` (usa `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`), volumen `pgdata:/var/lib/postgresql/data`, `healthcheck: pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}` cada 5 s, sin `ports`, `restart: unless-stopped` — 1 h
- [ ] T9 · `infra/compose.yml` servicio `api`: `build: { context: ../api, dockerfile: Dockerfile }`, `image: apex-api:local`, `env_file: ../.env`, volúmenes `keys:/run/apex/keys:ro` y `uploads:/data/uploads`, `depends_on: db: condition: service_healthy`, `healthcheck` con `python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"` (la imagen slim no trae curl), `start_period: 30s`, `restart: unless-stopped` — 2 h
- [ ] T10 · `infra/compose.yml` servicio `worker`: `image: apex-api:local`, `command: ["python", "-m", "app.worker.main"]`, mismo `env_file` y volúmenes que `api` (keys en `ro`), `depends_on: db: condition: service_healthy`, `profiles: ["worker"]` hasta que exista `app/worker/main.py` (US-113 quita el perfil en su PR), `restart: unless-stopped` — 1 h
- [ ] T11 · `infra/compose.yml` servicio `tools` para comandos de CLI que escriben llaves (`cli init-keys` de US-023): misma imagen, `profiles: ["tools"]`, `keys:/run/apex/keys` en lectura y escritura, `entrypoint: ["python", "-m", "app.cli"]`; es la única vía de escritura del volumen `keys` — 0,5 h
- [ ] T12 · `infra/compose.yml` cabecera y volúmenes: `name: apex`; volúmenes nombrados `pgdata`, `uploads`, `keys`, `backups` (este último lo usa US-114); servicio `web` declarado como esqueleto (`image: apex-web:local`, puerto `80:80`, `depends_on: api: condition: service_started`) para que US-006 complete `build` y configuración — 0,5 h
- [ ] T13 · `infra/compose.dev.yml`: `api` con `command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/src`, bind mount `../api/src:/app/src`, `WATCHFILES_FORCE_POLLING=true` (los eventos de archivos no cruzan de NTFS a WSL2), `ports: ["8000:8000"]`; `db` con `ports: ["5432:5432"]`; servicio `db_test` (`postgres:16`, `tmpfs: /var/lib/postgresql/data`, `POSTGRES_DB=apex_test`, `ports: ["5433:5432"]`, healthcheck `pg_isready`) — 2 h
- [ ] T14 · Smoke de Compose en CI: `scripts/ci/compose-smoke.sh` (gancho dejado por US-003 T7) que hace `cp .env.example .env` si falta, `docker compose -f infra/compose.yml -f infra/compose.dev.yml up -d --build db api`, espera `db` `healthy` (máximo 120 s), verifica que `api` está `running` con `docker compose ps --format json`, y si la imagen ya tiene `/health` (US-020) espera `api` `healthy`; al final `docker compose down -v` — 2 h
- [ ] T15 · Verificación manual en Linux y en Windows con WSL2: arranque desde un clon limpio, tiempo medido hasta `db` `healthy` y `api` en ejecución, anotado en el PR (Definición de terminado de la historia) — 1 h

### Seguridad
- [ ] T16 · Revisión: el volumen `keys` solo es escribible por `tools`; `db` sin puertos en producción; `.dockerignore` probado por T4; `restart: unless-stopped` en todos los servicios de larga vida; ninguna variable con secreto en `compose.yml` (todo por `env_file`) — 1 h

## Orden de ejecución
1. T2 (prueba del marcador, en rojo)
2. T1 (marcador de `app.main`)
3. T7, T5, T6 (imagen)
4. T4 (prueba de la imagen)
5. T8, T9, T10, T11, T12 (Compose de producción)
6. T13 (Compose de desarrollo)
7. T3 (prueba de la configuración de Compose)
8. T14 (smoke en CI)
9. T16, T15 (revisión y verificación en Linux y WSL2)

## Dependencias técnicas
- US-002 · Proyecto api con uv, ruff, mypy y pytest: `pyproject.toml`, `uv.lock` y el paquete `app` que se empaquetan.
- US-003 · Pipeline CI: el job `images` donde corren T3, T4 y T14.
- US-007 · `.env.example` y README: las variables que leen `env_file` y el smoke (se pueden trabajar en paralelo; T14 necesita el archivo).
- US-020 · `create_app()`, migraciones y `/health`: reemplaza el marcador de T1 y vuelve `healthy` el healthcheck de `api`.
- US-023 · KeyProvider y proveedor local: `cli init-keys` que escribe en el volumen `keys` por el servicio `tools`.
- US-113 · Proceso worker: crea `app/worker/main.py` y quita `profiles: ["worker"]`.

## Endpoints
- Ninguno.

## Riesgos
- `env_file` y la interpolación de Compose: Compose busca `.env` para interpolar `${...}` en el directorio del proyecto (`infra/`), no en la raíz — mitigación: ningún `${VAR}` en los archivos de Compose (salvo `$$` para el shell del healthcheck); todo entra por `env_file: ../.env` y el README (US-007) indica correr los comandos desde la raíz.
- Volumen nombrado `keys` con dueño root si se crea antes de que exista el punto de montaje en la imagen: el archivo de KEK quedaría ilegible para `apex` — mitigación: T6 crea y da dueño a `/run/apex/keys` en la imagen; T15 lo verifica con `docker compose run --rm tools ...` y `stat`.
- Recarga en caliente en WSL2 con el código en NTFS: sin polling no detecta cambios — mitigación: `WATCHFILES_FORCE_POLLING=true` en `compose.dev.yml`; recomendar clonar dentro del sistema de archivos de WSL2.
- `worker` en bucle de reinicios si se quita el perfil antes de US-113 — mitigación: el perfil lo quita el PR de US-113, no otro.
- El healthcheck de `api` queda `unhealthy` hasta US-020 (el marcador no tiene `/health`): `web` no debe esperar `service_healthy` todavía — mitigación: `condition: service_started` en T12; US-118 lo endurece.

## Estimación
- Backend: 0,5 h
- Front: 0 h
- Pruebas: 4 h
- DevOps / seguridad: 15,5 h
- **Total: 20 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/test_main_placeholder.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `docker compose -f infra/compose.yml -f infra/compose.dev.yml config` termina con código 0
- [ ] `docker compose -f infra/compose.yml config --format json | jq '.services.db.ports'` devuelve `null`
- [ ] `docker build -t apex-api:ci -f api/Dockerfile api && docker run --rm apex-api:ci id -u` devuelve `10001`
- [ ] `bash scripts/ci/tests/test_compose_config.sh && bash scripts/ci/tests/test_api_image.sh` terminan con código 0
- [ ] `docker compose -f infra/compose.yml -f infra/compose.dev.yml up -d db api && docker compose -f infra/compose.yml -f infra/compose.dev.yml ps` muestra `db` en `healthy` y `api` en `running` en menos de 5 minutos desde un clon limpio (tiempo anotado en el PR, en Linux y en WSL2)
- [ ] `bash scripts/ci/compose-smoke.sh` termina con código 0
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app --cov-fail-under=80`
