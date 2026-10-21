# US-115 · Verificación de backup — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-13-puesta-en-marcha-y-continuidad/US-115-verificacion-de-backup.md`
- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context / módulo:** ninguno de negocio; job `api/src/app/worker/jobs/backup_check.py`, registro en `api/src/app/core/jobs.py` (propuesto en US-113), campo `backup` de `/health` en `api/src/app/main.py`, y una ampliación de `api/src/app/core/crypto/`
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**ARCHITECTURAL_GAP_DETECTED**

El job tiene que hacer dos operaciones criptográficas fuera de `core/crypto`: calcular el sha256 de un archivo de cientos de MB en streaming y descifrar un archivo `age` con una identidad X25519. El bus hoy solo ofrece `encrypt`, `decrypt` (blobs `apx1.`), `blind_index`, `sign`, `verify` y `digest(data: bytes)` (N-06). Ninguna sirve para un archivo `age` ni para un hash en streaming. Sin una ampliación del bus, el job tendría que importar `hashlib` (prohibido por `banned-api`) o invocar `age` desde el worker, fuera de la única puerta criptográfica. Se propone la ampliación concreta.

## Resumen

El job `backup_check` corre en el ciclo de las 07:00 del worker (US-113). Lee `latest.json` del volumen `backups` (montado en solo lectura en el worker) y comprueba:

1. que el archivo existe;
2. que su `created_at` tiene menos de 24 horas según el reloj UTC;
3. que su sha256 coincide, con `core.crypto.bus.digest_file`;
4. si hay identidad de verificación (`BACKUP_AGE_VERIFY_IDENTITY_PATH`, N-50), que se puede descifrar en streaming sin escribir nada en claro, con `core.crypto.bus.verify_age_archive`.

La función pura `evaluate(...)` decide el estado: `ok`, `ok_unverified`, `stale`, `missing`, `corrupt` o `undecryptable`. El resultado queda en `worker.job_runs.result` y en `details`. `/health` expone `backup` como campo informativo, sin cambiar el código 200, mediante `register_health_check(..., informative=True)` de US-020.

## Correcciones aplicadas por DECISIONES.md

- Supuesto de la historia "el estado del backup se expone en `/health` sin cambiar el código 200" → aceptado; además `/health` responde en la raíz y en `/api/v1/health`: DECISIONES N-16.
- Supuesto "la identidad `age` de verificación se monta solo si el operador la provee" → aceptado; se monta en solo lectura en el worker: DECISIONES N-50.
- La historia condiciona `details` ("si no existe en US-113, se agrega aquí con su migración") → no hay migración aquí; `details` JSONB ya está en `0012_worker_job_runs`: numeración canónica (DECISIONES N-50).
- Criterio 9 ("dos registros de verificación el mismo día") → el índice canónico es único por `(job_name, run_date)`. La segunda corrida actualiza la fila del día y agrega la verificación a `details.attempts`; `/health` expone la última: corregido por la numeración canónica de `0012` (DECISIONES N-50), con la propuesta registrada en US-113.
- Avisar del fallo → en v0.1 solo log de nivel `error` y `/health`; la alerta por Telegram al equipo es de v0.2 (`core/alerts.py`): DECISIONES N-34.
- Hash SHA-256 → por el bus, nunca con `hashlib` fuera de `core/crypto`: DECISIONES N-06.
- Firma del backup → no se verifica firma antes de v1.0: DECISIONES N-48.

## Validación contra el dominio

- Sin aggregates. Regla de EP-13: "`backup_check` marca error si el último backup tiene más de 24 horas"; el borde exacto de 24 h 0 s es `stale`.
- Q28: el `run_date` del registro es `today_bogota()`; la edad se mide con `clock.now()` en UTC.
- Función pura: `evaluate(manifest: Manifest | None, now_utc: datetime, file_exists: bool, sha256_ok: bool | None, decrypt_ok: bool | None) -> BackupStatus`, con prioridad `missing` > `corrupt` > `undecryptable` > `stale` > `ok_unverified` > `ok`. Sin identidad de verificación (`decrypt_ok is None`), el estado máximo es `ok_unverified`.
- Sin eventos. Confirmado: sin discrepancias con el dominio.

## Validación contra la arquitectura

- Brecha: el bus no tiene operaciones de archivo (ver "Preguntas abiertas").
- El job es capa de aplicación (worker). No importa `models` de módulos y usa `app.core.jobs` según la regla de importación propuesta en US-113.
- `/health`: `register_health_check(name, fn, informative=True)` de US-020. Un chequeo informativo nunca cambia el código HTTP. Hay que acordar con US-020 que el registro acepte ese parámetro. La función lee `core.jobs.last_run(session, "backup_check")` y devuelve solo el estado (`"unknown"` si no hay ejecución).
- Volúmenes: `backups` en solo lectura en el worker; la identidad de verificación en solo lectura y solo en el worker, nunca en el api ni en `backup`.
- Lint banned-api: el job no importa `hashlib` ni `subprocess` para cifrado. Todo pasa por `core.crypto.bus`.
- Seguridad de `/health`: público (lista blanca). Solo expone el estado, nunca el nombre del archivo, la ruta ni el error.

## Preguntas abiertas

- Brecha 1 · Operaciones criptográficas sobre archivos de backup fuera del bus. Propuesta:
  - Se agrega `api/src/app/core/crypto/archive.py`, y el bus lo reexpone con dos funciones:
    - `bus.digest_file(path: Path, chunk_size: int = 1 << 20) -> str`: SHA-256 en streaming, con la misma implementación que `digest`.
    - `bus.verify_age_archive(path: Path, identity_path: Path) -> bool`: invoca el binario `age` (BSD-3-Clause, misma versión fijada que la imagen `backup`) con `subprocess` desde `core/crypto`, con `age -d -i <identidad> <archivo>`. La salida va a un sumidero que solo cuenta bytes (nunca a disco). Hay timeout de 10 minutos y devuelve `False` ante cualquier error, sin propagar la salida de error con contenido.
  - `verify_age_archive` deja una fila en `crypto_ops` con verbo `verify` y `data_class = "backup.archive"`, registrada en `core/crypto/registry.py` (N-04), sin `key_id` porque la llave no está en `crypto_keys`. `digest_file` no registra nada, igual que `digest` (N-06): un hash no usa llave. El verbo `digest` no existe en el CHECK de `crypto_ops` y no se agrega.
  - La imagen del api (que también usa el worker) agrega el binario `age` y su licencia en `NOTICE`.
  - El test de arquitectura `test_banned_imports.py` (US-031) se amplía para que `subprocess` con `age` solo aparezca en `core/crypto/archive.py`.
  - Alternativa: `pyrage`, enlaces de Python a `rage`, en `core/crypto`. Se descarta para esta historia porque no descifra en streaming, contra el criterio 7.
  - `CLAUDE.md` (bus, regla 1) agrega `digest_file` y `verify_age_archive` a la lista de la única puerta al aprobar el gate.
- Pregunta asociada (no bloquea si se acepta la propuesta de US-113): cada reejecución del mismo día se guarda en `details.attempts` de la misma fila y no en filas nuevas.

## Tareas

### Migración Alembic
- No aplica (usa `0012_worker_job_runs`: `result` con los estados de backup y `details` JSONB).

### Models
- No aplica (usa `JobRun` de `core/jobs.py`, US-113).

### Service
- [ ] T1 · `core/crypto/archive.py`: `digest_file` (streaming, sin cargar el archivo en memoria) y `verify_age_archive` (subprocess con lista de argumentos, sin `shell=True`, `stdout` a un lector que descarta y cuenta bytes, `stderr` descartado, timeout); registro en `crypto_ops` solo para `verify_age_archive`; reexportados en `core/crypto/bus.py`; `data_class` `backup.archive` en `core/crypto/registry.py` — 3 h
- [ ] T2 · `worker/jobs/backup_check.py`: función pura `evaluate(...)` y dataclass `Manifest` que se parsea desde `latest.json` con validación del esquema `infra/backup/manifest.schema.json` (US-114); un manifiesto ilegible cuenta como `missing` — 1,5 h
- [ ] T3 · `worker/jobs/backup_check.py`: `async def run(session, today, clock) -> JobOutcome` que lee `BACKUP_DIR` y `BACKUP_AGE_VERIFY_IDENTITY_PATH` de `Settings`, comprueba existencia, edad, `bus.digest_file` y, si hay identidad, `bus.verify_age_archive`; devuelve el estado y `details` (`status`, `backup_name`, `backup_created_at`, `checked_at`, `verified: bool`); log JSON de nivel `error` si el estado no es `ok`; se registra como `backup_check` en `worker/jobs/__init__.py` después de `expirations` — 2 h
- [ ] T4 · `app/main.py` (o `core/health.py` de US-020): chequeo `backup` registrado con `informative=True` que lee `core.jobs.last_run(session, "backup_check")` y devuelve `ok`, `ok_unverified`, `stale`, `missing`, `corrupt`, `undecryptable` o `unknown`; acordar con US-020 el parámetro `informative` del registro — 1 h

### Schemas
- [ ] T5 · Esquema de salida de `/health` (US-020): campo `backup: Literal["ok", "ok_unverified", "stale", "missing", "corrupt", "undecryptable", "unknown"]`; `docs/openapi.json` regenerado — 0,5 h

### Router
- No aplica (el endpoint `/health` es de US-020; solo se agrega el campo).

### Tests unitarios puros
- [ ] T6 · `api/tests/worker/test_backup_check_evaluate.py`: los seis estados; borde de 24 h exactas (`2026-10-20T12:00:00Z` contra `2026-10-21T12:00:00Z` es `stale`); 23 h 59 min 59 s es válido; sin identidad, el máximo es `ok_unverified`; prioridad cuando falla más de una comprobación — 1,5 h

### Tests de service con PostgreSQL
- [ ] T7 · `api/tests/worker/test_backup_check.py`: con `FrozenClock` en `2026-10-21T12:00:00Z` y archivos de prueba en un directorio temporal (generados con `age` y una identidad de prueba): backup de las 07:00 del mismo día es `ok`; del día anterior, `stale`; directorio vacío, `missing`; sha256 alterado, `corrupt`; identidad equivocada, `undecryptable`; `job_runs` guarda el estado y, en una segunda corrida del mismo día, `details.attempts` tiene dos entradas — 2 h
- [ ] T8 · `api/tests/crypto/test_archive.py`: `digest_file` coincide con `digest(bytes)` para un archivo de 5 MB; `verify_age_archive` es verdadero con la identidad correcta y falso con otra o con archivo truncado; durante la verificación no aparece ningún archivo nuevo en el directorio temporal; quedan filas en `crypto_ops` sin material de llave — 1,5 h

### Tests de router
- [ ] T9 · `api/tests/core/test_health.py`: sin ejecución, `backup: "unknown"`; con una ejecución `stale`, `/health` y `/api/v1/health` responden 200 con `backup: "stale"`; el cuerpo no tiene nombre de archivo ni error — 1 h

### Tests de arquitectura
- [ ] T10 · `api/tests/architecture/test_banned_imports.py` (US-031): `subprocess` que invoca `age` solo en `app/core/crypto/archive.py`; `app/worker/jobs/backup_check.py` no importa `hashlib`, `subprocess` ni `cryptography` — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T11 · Imagen del api (US-005): binario `age` con versión fijada y checksum; `infra/compose.yml`: en `worker`, volumen `backups:/data/backups:ro` y, comentado como opcional, el montaje de la identidad de verificación en solo lectura; `BACKUP_DIR` y `BACKUP_AGE_VERIFY_IDENTITY_PATH` en `Settings` y `.env.example`; `NOTICE` con `age` en la imagen del api — 1,5 h

### Seguridad
- [ ] T12 · Revisión: la identidad de verificación es una llave privada; documentar en `docs/operacion/respaldo-y-restauracion.md` (US-116) que su presencia en el servidor permite descifrar los backups locales, y que por eso es opcional y distinta de la identidad maestra si el operador lo prefiere (otro destinatario `age` en `BACKUP_AGE_RECIPIENT`); permisos 400 del archivo montado; `/health` público sin detalles — 1 h

## Orden de ejecución

1. Cerrar la brecha 1 en el gate (ampliación del bus) y la de US-113 (`core/jobs.py`).
2. T8 (en rojo), luego T1.
3. T10.
4. T6 (en rojo), luego T2.
5. T7 (en rojo), luego T3.
6. T9 (en rojo), luego T5 y T4.
7. T11 y T12.

## Dependencias técnicas

- US-113 · Proceso worker programado: registro de jobs, `core/jobs.py` y `0012_worker_job_runs` con `details`.
- US-114 · Backup nocturno cifrado: `latest.json`, su esquema y el volumen `backups`.
- US-020 · `create_app` y `/health`: `register_health_check` con `informative=True` (acordado en consolidación).
- US-025 / US-027 / US-029 · Bus de criptografía: `bus.py`, `registry.py` y `crypto_ops`; `digest` de N-06 (US-015).
- US-031 · Pruebas de arquitectura criptográfica.
- US-013 · `Clock` y `FrozenClock`.
- US-005 · Imagen del api (binario `age`).

## Endpoints

- `GET /health` — roles: público (lista blanca)
- `GET /api/v1/health` — roles: público (lista blanca)

## Riesgos

- Identidad de verificación en el servidor: quien robe el servidor puede abrir los backups locales — mitigación: es opcional (sin ella, `ok_unverified`); se documenta usar un segundo destinatario `age` solo para verificar y rotarlo.
- Archivos grandes en v0.3 (`uploads`): la verificación tarda — mitigación: streaming y timeout de 10 minutos; si se excede, el estado es `undecryptable` con `details.reason = "timeout"`.
- Que US-020 no acepte chequeos informativos: `/health` respondería 503 por un backup viejo y Compose reiniciaría el api — mitigación: T4 acuerda `informative=True` y T9 lo prueba.
- Que la brecha se resuelva con `pyrage`: se pierde el streaming del criterio 7 — mitigación: la propuesta usa el binario `age`.
- Estimación por encima del rango de 3 puntos (10 a 15 h): la suma da 17 h por la ampliación del bus que cierra la brecha (T1, T8 y T10) — mitigación: si el gate aprueba la ampliación tal cual, no hay más trabajo oculto.

## Estimación

- Backend: 8 h
- Front: 0 h
- Pruebas: 6 h
- DevOps / seguridad: 3 h
- **Total: 17 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/worker/test_backup_check_evaluate.py tests/worker/test_backup_check.py -q`
- [ ] `cd api && uv run pytest tests/crypto/test_archive.py -q`
- [ ] `cd api && uv run pytest tests/core/test_health.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `docker compose run --rm worker uv run python -m app.worker.main --run-once backup_check` termina con 0 y `curl -s http://localhost/api/v1/health | jq -r .backup` devuelve el estado registrado
- [ ] Con un backup de más de 24 horas, `curl -s -o /dev/null -w "%{http_code}" http://localhost/api/v1/health` sigue en `200` y `.backup` es `stale`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.worker.jobs.backup_check --cov=app.core.crypto.archive --cov-fail-under=80`
