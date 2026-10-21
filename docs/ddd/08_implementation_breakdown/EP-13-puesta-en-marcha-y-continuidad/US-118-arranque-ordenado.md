# US-118 · Arranque ordenado — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-13-puesta-en-marcha-y-continuidad/US-118-arranque-ordenado.md`
- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context / módulo:** ninguno; operación (`infra/compose.yml`) y arranque del api (`api/src/app/main.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

La historia ajusta healthchecks y `depends_on`, y agrega al `/health` de US-020 una comprobación de que la revisión de Alembic es `head`. El contrato de `/health` está decidido por N-16 (raíz y `/api/v1/health`, backup informativo). El arranque con migraciones antes de aceptar tráfico ya es la decisión de `04_architecture_decision.md`. No hay supuestos abiertos.

## Resumen

Se completa el orden de arranque en `infra/compose.yml`:

- `db` tiene healthcheck con `pg_isready`;
- `api` depende de `db` sano;
- `web` y `worker` dependen de `api` sano;
- `backup` depende de `db` sano;
- todos tienen `restart: unless-stopped`.

El healthcheck del `api` llama a `/health` con Python de la propia imagen (sin `curl`). Al `/health` de US-020 se agrega la comprobación `migrations`, que compara la revisión de la base con el `head` del directorio de migraciones; si no coinciden, responde 503. Se confirma que Uvicorn no abre el puerto hasta que termina el `lifespan` (migraciones y apertura de DEK), y que una migración fallida termina el proceso con código distinto de 0 y nombra la revisión. Una prueba de arquitectura prohíbe `create_all` fuera de `tests/`.

## Correcciones aplicadas por DECISIONES.md

- `/health` → responde en la raíz y en `/api/v1/health`; el campo `backup` (US-115) es informativo y nunca vuelve 503 la respuesta, así que el healthcheck de Compose no reinicia el api por un backup viejo: DECISIONES N-16.
- Orden de `worker` → depende de `api` sano y no migra (la migración la hace solo el api con `pg_advisory_lock`, US-020); el worker reintenta la conexión según US-113: coherente con DECISIONES N-50 (worker con `job_runs`).
- Ninguna otra; la historia ya es coherente con DECISIONES.md.

## Validación contra el dominio

- Sin aggregates ni reglas de negocio.
- Regla de datos 7: nunca `create_all` en producción; se hace cumplir con prueba (criterio 6).
- `04_architecture_decision.md` sección 8: el reinicio automático de Compose compensa que todo corra en un solo proceso.
- Confirmado: sin discrepancias.

## Validación contra la arquitectura

- `main.py` (`create_app`, US-020) es el único que migra al arrancar.
- La comprobación `migrations` se registra con `register_health_check("migrations", fn)` y **no** es informativa: si falla, `/health` responde 503 con `status: "degraded"`.
- `fn` usa `alembic.script.ScriptDirectory` y `MigrationContext` sobre la conexión. Alembic no es primitiva criptográfica, así que no aplica `banned-api`.
- Uvicorn ejecuta el `lifespan` antes de enlazar el socket: mientras migra, la conexión se rechaza (criterio 2). Una excepción en el `lifespan` termina el proceso con código 3 de Uvicorn, distinto de 0, y Compose lo reintenta.
- Healthchecks:
  - `api`: `python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"`, sin binarios extra en la imagen;
  - `web`: `wget -q --spider http://127.0.0.1/` (Nginx Alpine);
  - `db`: `pg_isready -U $POSTGRES_USER`.
- Sin rol nuevo: `/health` ya está en la lista blanca (US-035).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `app/core/health.py` (o `main.py`, según US-020): chequeo `migrations` que devuelve `"head"` si la revisión actual de la base es igual a `ScriptDirectory.get_current_head()`, y `"behind"` si no; registrado no informativo — 1 h
- [ ] T2 · `app/main.py`: en el `lifespan`, envolver `alembic upgrade head` para registrar en el log JSON la revisión que falló (`revision`, `error` sin datos de conexión) y relanzar, para que el proceso salga con código distinto de 0 — 0,5 h

### Schemas
- [ ] T3 · Salida de `/health` (US-020): campo `migrations: Literal["head", "behind"]`; `docs/openapi.json` regenerado — 0,5 h

### Router
- No aplica (la ruta es de US-020).

### Tests unitarios puros
- No aplica.

### Tests de service con PostgreSQL
- [ ] T4 · `api/tests/core/test_health_migrations.py`: base en `head` → 200 con `migrations: "head"`; base con `alembic downgrade -1` → 503 con `migrations: "behind"`; `lifespan` con una migración de prueba que lanza error → el arranque falla y el log nombra la revisión — 1,5 h

### Tests de router
- [ ] T5 · `api/tests/core/test_health.py`: `/health` y `/api/v1/health` iguales; el campo `backup` informativo no cambia el 200 cuando `migrations` es `head` y `db` es `ok` — 0,5 h

### Tests de arquitectura
- [ ] T6 · `api/tests/architecture/test_no_create_all.py`: recorre `api/src/` y falla si encuentra `create_all(` o `metadata.create_all`; `tests/` queda permitido — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T7 · `infra/compose.yml`: healthchecks de `db`, `api` y `web` con `interval`, `timeout`, `retries` y `start_period` (el del api cubre migraciones largas: 60 s); `depends_on` con `condition: service_healthy` (`api` de `db`; `web` y `worker` de `api`; `backup` de `db`); `restart: unless-stopped` en todos — 1 h
- [ ] T8 · `infra/tests/startup_smoke.sh` en CI: `docker compose up -d` desde cero; `docker compose ps --format json` muestra que `worker` y `web` arrancan después de que `api` está `healthy` (comparando `State.StartedAt` con el momento en que `api` pasó a `healthy`); con una imagen de prueba que trae una migración rota, `api` sale con código distinto de 0 y `web` no arranca; `docker compose restart` vuelve todo a `healthy` sin intervención — 2,5 h

### Seguridad
- [ ] T9 · Revisión: el log de una migración fallida no imprime `DATABASE_URL` ni la contraseña; `/health` no expone la revisión de Alembic exacta (solo `head` o `behind`) — 0,5 h

## Orden de ejecución

1. T6 (en rojo si hubiera `create_all`).
2. T4 (en rojo), luego T1, T2 y T3.
3. T5.
4. T7.
5. T8.
6. T9.

## Dependencias técnicas

- US-020 · `create_app`, migraciones al arrancar con `pg_advisory_lock`, `/health` y `register_health_check`.
- US-005 · Dockerfile del api y Compose.
- US-006 · Imagen de Nginx (healthcheck de `web`).
- US-113 · Worker con reintento de conexión.
- US-114 · Servicio `backup` (su `depends_on`).
- US-115 · Campo `backup` informativo de `/health`.
- US-025 · Apertura de DEK en el `lifespan` (parte del "listo para tráfico").

## Endpoints

- `GET /health` — roles: público (lista blanca)
- `GET /api/v1/health` — roles: público (lista blanca)

## Riesgos

- `start_period` corto con una migración larga: Compose marca `api` como `unhealthy` y lo reinicia a mitad de una migración — mitigación: `start_period` de 60 s, la migración corre con `pg_advisory_lock` y Alembic usa una transacción por migración.
- `depends_on` con `service_healthy` solo aplica al arranque: si `api` se cae después, `worker` sigue — mitigación: el worker reintenta la conexión (US-113) y no depende del api en tiempo de ejecución.
- Reinicio del host con Docker sin arranque automático — mitigación: `docs/operacion/actualizar.md` (US-117) incluye `systemctl enable docker` como requisito del servidor.

## Estimación

- Backend: 2 h
- Front: 0 h
- Pruebas: 5 h
- DevOps / seguridad: 2 h
- **Total: 9 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_health_migrations.py tests/core/test_health.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `bash infra/tests/startup_smoke.sh` en CI (arranque en frío, migración rota y reinicio)
- [ ] `docker compose -f infra/compose.yml up -d && docker compose ps` muestra `db`, `api`, `web`, `worker` y `backup` como `healthy` o `running`
- [ ] `curl -s http://localhost/api/v1/health | jq -r .migrations` devuelve `head`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.health --cov-fail-under=80`
