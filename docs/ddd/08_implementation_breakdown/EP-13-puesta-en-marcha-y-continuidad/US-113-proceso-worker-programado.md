# US-113 · Proceso worker programado — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-13-puesta-en-marcha-y-continuidad/US-113-proceso-worker-programado.md`
- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context / módulo:** ninguno de negocio; proceso `worker` (`api/src/app/worker/`) y registro de ejecuciones propuesto en `api/src/app/core/jobs.py`
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**ARCHITECTURAL_GAP_DETECTED**

La historia necesita la tabla `worker.job_runs`. N-50 la acepta y la migración canónica `0012_worker_job_runs` la crea. Pero la estructura de `CLAUDE.md` no tiene un lugar para su modelo SQLAlchemy: `worker/` solo tiene `main.py` y `jobs/`, y no existe un módulo `worker` en `modules/`. Además, el modelo lo leen dos procesos: el worker, que escribe, y el api, que en `/health` expone el resultado de `backup_check` (US-115). Se propone una ubicación concreta y su regla de importación.

## Resumen

Se construye `worker/main.py` con APScheduler 3.10 (MIT), `AsyncIOScheduler` en zona `America/Bogota` y un ciclo diario a las 07:00 que ejecuta en orden los jobs del registro `worker/jobs/__init__.py`. Cada job corre en su propia sesión y transacción. Su ejecución queda en `worker.job_runs` (único por `job_name` y `run_date` de Bogotá), en una transacción aparte para que un fallo del job no borre el registro del error. Se agrega:

- un log JSON por ejecución;
- recuperación al arrancar si el ciclo del día no corrió;
- reintento de conexión con espera exponencial hasta 60 s;
- el comando `python -m app.worker.main --run-once <job>`.

El servicio `worker` entra en `infra/compose.yml` con la misma imagen que el api.

## Correcciones aplicadas por DECISIONES.md

- La historia propone `worker.job_runs` como supuesto propio → la tabla queda aceptada, con columna `details` JSONB desde el inicio para US-115: corregido por DECISIONES N-50 y la numeración canónica `0012_worker_job_runs`.
- La historia propone dos índices (único total y único parcial `WHERE result = 'ok'`) → un solo índice único total `(job_name, run_date)`. Una reejecución del mismo día (fallo reintentado o `--run-once`) actualiza la misma fila y agrega el intento a `details.attempts`: corregido por la numeración canónica de `0012` (DECISIONES N-50).
- Actor de las escrituras del worker → `created_by` de `job_runs` y `user_id` de toda auditoría que produzcan los jobs es `SYSTEM_USER_ID`: corregido por DECISIONES N-15 (no existe `SYSTEM_ACTOR_ID` por variable).
- "Hoy" de los jobs → `today_bogota()` de `core/clock.py`: aceptado por DECISIONES Q28.
- La firma de auditoría (v0.3) corre en el mismo ciclo de las 07:00: aceptado por DECISIONES N-32 (solo se reserva el lugar en el registro).
- Las alertas por Telegram de un job fallido son de v0.2 (`core/alerts.py`, N-34). En v0.1 el fallo se ve en el log y, para el backup, en `/health`: DECISIONES N-34 y N-16.

## Validación contra el dominio

- No hay aggregate propio. El worker invoca casos de uso de otros módulos: `memberships.service.recompute_statuses(today)` (US-094) y `backup_check` (US-115); en v0.2 `notify` y en v0.3 `sign_audit`.
- `04_architecture_decision.md` sección 5: el worker no recibe eventos; consulta tablas. Los eventos que emiten los jobs (por ejemplo `MembershipExpired`) corren dentro de la transacción del job.
- Sección 8: el efecto obligatorio "el ciclo del día corrió" queda persistido en `job_runs`, no en memoria.
- Funciones puras: `next_run(now_utc: datetime, tz: str = "America/Bogota", hour: int = 7, minute: int = 0) -> datetime` y `should_run(job_name: str, run_date: date, now_local: time, scheduled_at: time, previous: JobRunView | None) -> bool`. `should_run` es verdadero solo si ya pasó la hora programada del día y no hay fila, o si la fila quedó `running` desde hace más de 6 horas (proceso caído). Un `error` no se reintenta solo: se reintenta con `--run-once`, para evitar bucles de fallo.
- `registry.register(job_name, func, hour=7, minute=0, order=n)` es una función pura sobre un registro inmutable (devuelve un registro nuevo).

## Validación contra la arquitectura

- Brecha: `CLAUDE.md` no prevé dónde vive el modelo de `worker.job_runs` (ver "Preguntas abiertas").
- El worker es capa de aplicación (como `cli.py`): llama a `service.py` de los módulos y nunca a sus `models`. La prueba de arquitectura de US-022 se amplía a `app/worker/`.
- Lint banned-api: sin primitivas. La verificación de backup de US-115 pasa por el bus.
- Rol: no hay HTTP.
- Auditoría: `job_runs` **no** lleva `__audited__`, porque es bitácora operativa y no dato de negocio; auditarla llenaría la cadena con ruido diario. Las escrituras de negocio de los jobs sí se auditan por el hook normal, con `SYSTEM_USER_ID`.
- Columnas comunes: `id` UUID asignado en Python, `created_at`, `updated_at` y `created_by` (`CommonColumnsMixin`). Sin `deleted_at` (no es una tabla con borrado lógico) y sin borrado físico por la aplicación.
- Configuración: `WORKER_TZ` (por defecto `America/Bogota`) y `WORKER_DAILY_HOUR` (por defecto 7) en `Settings` (US-011) y en `.env.example`; `tzdata` (Apache-2.0) en la imagen para `zoneinfo`.

## Preguntas abiertas

- Brecha 1 · Ubicación del modelo `JobRun`. Ni `worker/` ni `modules/` tienen hoy un `models.py` para el esquema `worker`, y la tabla la usan el worker y el api.
  - Propuesta: crear `api/src/app/core/jobs.py`, siguiendo el precedente de `core/audit.py` (modelo de `audit_log` en `core`) y de `core/crypto/models.py`. El archivo contiene el modelo `JobRun` (esquema `worker`) y las únicas funciones que lo tocan: `claim_run(session, job_name, run_date) -> JobRunView | None`, `finish_run(session, run_id, result, error, details)` y `last_run(session, job_name) -> JobRunView | None`.
  - Regla de importación: solo `app/worker/**` y el chequeo de salud de `app/main.py` (o `core/health`) importan `app.core.jobs`. Ningún módulo de `app/modules/` lo importa.
  - `core/jobs.py` no importa nada de `modules/`, así que `core` no depende de ningún módulo.
  - La regla se hace cumplir con `api/tests/architecture/test_core_jobs_imports.py`, y `CLAUDE.md` agrega la línea `jobs.py  # registro de ejecuciones del worker (worker.job_runs)` en la sección `core/` al aprobar el gate.
  - Alternativa descartada: `app/worker/models.py`, porque obligaría al api a importar el paquete del worker (APScheduler incluido) para su `/health`.
- Pregunta asociada (no bloquea si se acepta la propuesta de la corrección 2): la historia de US-115 pide "dos registros" cuando `backup_check` corre dos veces el mismo día, pero el índice canónico es único por `(job_name, run_date)`. Se propone por defecto que cada reejecución actualice la fila y agregue el intento a `details.attempts` (lista con `started_at`, `finished_at`, `result`, `error`), sin cambiar el índice de `0012`.

## Tareas

### Migración Alembic
- [ ] T1 · `0012_worker_job_runs`: tabla `worker.job_runs` con `id UUID PK`, `job_name TEXT NOT NULL` (CHECK `job_name ~ '^[a-z][a-z0-9_]{1,62}$'`), `run_date DATE NOT NULL` (fecha de Bogotá), `started_at TIMESTAMPTZ NOT NULL`, `finished_at TIMESTAMPTZ NULL`, `result TEXT NOT NULL` con CHECK en `running`, `ok`, `error` y los estados de backup (`ok_unverified`, `stale`, `missing`, `corrupt`, `undecryptable`), `error TEXT NULL` (sin datos personales), `details JSONB NOT NULL DEFAULT '{}'`, `created_at`, `updated_at`, `created_by UUID NOT NULL`; índice único `(job_name, run_date)` e índice `(job_name, started_at DESC)`; downgrade con `DROP TABLE`. El esquema `worker` ya existe por `0001_core_schemas` — 2 h

### Models
- [ ] T2 · `api/src/app/core/jobs.py`: modelo `JobRun(CommonColumnsMixin, Base)` con `__table_args__ = {"schema": "worker"}` y la vista inmutable `JobRunView` (dataclass congelada) que devuelven las funciones — 1 h

### Service
- [ ] T3 · `app/core/jobs.py`: `claim_run` (`INSERT ... ON CONFLICT (job_name, run_date) DO UPDATE SET result='running', started_at=now() WHERE job_runs.result <> 'running' OR job_runs.started_at < now() - interval '6 hours' RETURNING *`), `finish_run` y `last_run`; cada llamada en una sesión corta y propia, distinta de la del job — 1,5 h
- [ ] T4 · `app/worker/registry.py`: `JobSpec(name, func, hour, minute, order)`, `register(...)` y `get_registry()`; `app/worker/jobs/__init__.py` importa los jobs de cada épica (`expirations` de US-094 y `backup_check` de US-115) y declara el orden — 1 h
- [ ] T5 · `app/worker/schedule.py`: funciones puras `next_run` y `should_run` — 1 h
- [ ] T6 · `app/worker/runner.py`: `async def run_job(spec, clock) -> JobOutcome` (calcula `today = today_bogota(clock)`, `claim_run`, abre sesión y transacción del job con el contexto de actor `SYSTEM_USER_ID` de US-016, ejecuta `spec.func(session, today, clock)`, hace commit o rollback, `finish_run` y log JSON con `job`, `started_at`, `finished_at`, `duration_ms` y `result`); `async def run_cycle(clock)` que ejecuta en orden y atrapa la excepción de cada job sin detener a los demás — 2 h
- [ ] T7 · `app/worker/main.py`: `AsyncIOScheduler(timezone="America/Bogota")` con `CronTrigger(hour=7, minute=0)`, `coalesce=True` y `max_instances=1`; al arrancar espera la base con reintento exponencial (1, 2, 4, … hasta 60 s); recuperación de arranque tardío con `should_run`; `--run-once <job>` (código 0 si `ok`, 1 si falló, 2 si el job no existe, listando los registrados); manejo de `SIGTERM` para terminar el job en curso — 2 h

### Schemas
- No aplica (sin HTTP; `JobRunView` y `JobOutcome` son dataclasses internas).

### Router
- No aplica.

### Tests unitarios puros
- [ ] T8 · `api/tests/worker/test_schedule.py`: `next_run` desde `2026-10-21T11:59:00Z` da `2026-10-21T12:00:00Z`; desde `2026-10-21T12:00:01Z` da `2026-10-22T12:00:00Z`; `today_bogota` a `2026-10-22T01:00:00Z` da `2026-10-21`; `should_run` en los casos sin fila, `ok` del día, `error` del día (no reintenta), `running` viejo (sí) y antes de la hora (no) — 1,5 h

### Tests de service con PostgreSQL
- [ ] T9 · `api/tests/worker/test_runner.py`: con `FrozenClock` y dos jobs de prueba, uno que lanza excepción: el segundo corre, la transacción del que falla se revierte (su escritura de prueba no queda), `job_runs` tiene `error` y `ok`, y el log JSON del error tiene el nombre del job y no tiene datos personales — 2 h
- [ ] T10 · `api/tests/worker/test_runner.py`: reinicio a las 09:00 de Bogotá con el ciclo ya hecho no ejecuta nada; sin ciclo hecho, ejecuta una sola vez; `claim_run` concurrente desde dos tareas deja una sola ejecución; una segunda corrida con `--run-once` agrega el intento a `details.attempts` — 1,5 h
- [ ] T11 · `api/tests/worker/test_main.py`: `--run-once expirations` con un job de prueba devuelve 0; con fallo, 1; `--run-once no-existe` devuelve 2 y lista los jobs; el reintento de conexión respeta el tope de 60 s (reloj falso) — 1 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T12 · `api/tests/architecture/test_core_jobs_imports.py`: solo `app.worker.*` y `app.main` (o `app.core.health`) importan `app.core.jobs`, y `app.core.jobs` no importa `app.modules`; `test_no_cross_models.py` revisa también `app/worker/` — 1 h

### Front
- No aplica.

### DevOps
- [ ] T13 · `infra/compose.yml`: servicio `worker` con la imagen del api, `command: ["uv", "run", "python", "-m", "app.worker.main"]`, `restart: unless-stopped`, `depends_on: api: condition: service_healthy` (US-118), mismas variables de base y KEK, sin puertos; `WORKER_TZ` y `WORKER_DAILY_HOUR` en `Settings` y `.env.example`; `apscheduler` y `tzdata` en `pyproject.toml` y en `NOTICE` — 1,5 h
- [ ] T14 · Smoke de Compose en CI: el contenedor `worker` queda en ejecución 30 s sin reiniciarse y `--run-once` con un job de prueba devuelve 0 — 1 h

### Seguridad
- [ ] T15 · Revisión: el log del worker pasa por el filtro de campos sensibles de US-018; `error` guarda el tipo y el mensaje de la excepción, nunca argumentos con datos de socios; la imagen no trae secretos — 0,5 h

## Orden de ejecución

1. Cerrar la brecha 1 en el gate (ubicación `core/jobs.py`).
2. T1, luego T2.
3. T8 (en rojo), luego T5.
4. T9 y T10 (en rojo), luego T3, T4 y T6.
5. T11 (en rojo), luego T7.
6. T12.
7. T13 y T14.
8. T15.

## Dependencias técnicas

- US-012 · Base de datos y Alembic multiesquema: `CommonColumnsMixin` y el esquema `worker` de `0001_core_schemas`.
- US-013 · Reloj y fecha de Bogotá: `Clock`, `today_bogota()`, `FrozenClock`.
- US-011 · Configuración desde `.env`: `WORKER_TZ` y `WORKER_DAILY_HOUR`.
- US-016 · Hook de auditoría: contexto de actor `SYSTEM_USER_ID` para procesos sin HTTP.
- US-018 · Logging JSON sin datos sensibles.
- US-041 · `SYSTEM_USER_ID` creado por `0004_auth`.
- US-005 · Dockerfile del api y Compose.
- US-118 · Arranque ordenado (`depends_on` del worker).
- US-094 · Job diario de vencimientos y US-115 · Verificación de backup: los primeros jobs que se registran (US-094 no se cierra sin esta historia).

## Endpoints

- Ninguno.

## Riesgos

- Un job que se cuelga bloquea el ciclo: los siguientes no corren — mitigación: `timeout` por job (`asyncio.wait_for`, 15 minutos por defecto en `JobSpec`) y `running` vencido a las 6 horas.
- Dos réplicas del worker por error de Compose ejecutan el ciclo dos veces — mitigación: `claim_run` con `ON CONFLICT` deja ganar a una sola.
- Cambio de hora: Colombia no tiene horario de verano, pero `zoneinfo` sin `tzdata` en la imagen slim falla — mitigación: `tzdata` como dependencia explícita.
- Si la brecha se resuelve distinto (por ejemplo, un módulo `modules/worker`), cambian las rutas de T2, T3 y T12, pero no la migración.
- Estimación por encima del rango de 3 puntos (10 a 15 h): la suma da 21 h porque la historia incluye la migración `0012`, el registro persistente con reclamo concurrente y la recuperación tras reinicio, que la historia trata como "mínimos" — mitigación: se puede partir en dos entregas (scheduler con `--run-once`, y después `job_runs` con recuperación) sin cambiar el alcance.

## Estimación

- Backend: 11 h
- Front: 0 h
- Pruebas: 7 h
- DevOps / seguridad: 3 h
- **Total: 21 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/worker -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `docker compose -f infra/compose.yml -f infra/compose.dev.yml up -d worker` y `docker compose ps worker` muestra el servicio en ejecución sin reinicios
- [ ] `docker compose run --rm worker uv run python -m app.worker.main --run-once no-existe; echo $?` imprime la lista de jobs y `2`
- [ ] `psql -c "SELECT job_name, run_date, result FROM worker.job_runs ORDER BY started_at DESC LIMIT 5"` muestra la ejecución del día
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.worker --cov=app.core.jobs --cov-fail-under=80`
