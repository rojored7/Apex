# Análisis de impacto previo · Sprint 4B (continuidad operativa y release v0.1)

Fecha: 29 de octubre de 2026 (línea base tomada entre las 12:30 y las 13:30 hora local).
Alcance: `update` sobre un repositorio con código (`flow-update`, Fase 0).
Anclaje: rama `feat/sprint-04b-continuidad-release`, HEAD `280addd` ("docs(sprint-04a): v12: estado
al cierre", igual a `main`), `git status` limpio, un solo worktree. El nombre de la rama coincide
con `SPRINT-04B.md`.
Plan de referencia: `docs/ddd/09_sprint_plan/SPRINT-04B.md` (9 historias: US-030, US-111, US-112,
US-114, US-115, US-116, US-117, US-118, US-119; dos slices de Wave 0 `S4B-W0-1` y `S4B-W0-2`, cuatro
de backend `S4B-B1` a `S4B-B4`, sin front; "Migraciones que aplica: ninguna"; "Endpoints: ninguno
nuevo, `/health` gana `backup` y la comprobación de migraciones"; release `v0.1.0`).

## Veredicto: AMARILLO

Se puede avanzar a la Fase 1 con `--allow-amber`. Nada es ROJO: todo lo que el sprint consume del
Sprint 4A y anteriores existe y con la firma que el código fija (`core/jobs.py` con `last_run`,
`RESULTS` que ya admite los seis estados del backup, `DETAIL_KEYS`, `JobSpec`/`JobResult`/
`JobContext`, `register_health_check(name, fn, *, critical)`, `HealthOut` con `extra="allow"`,
`bus.digest`/`bus.batch`, `KeyProvider.unwrap`, `LocalFileProvider`, `Keyring`, `ensure_keys`, el
verbo `export` y `rotate` en el CHECK de `crypto_ops` y el trigger de transiciones de `crypto_keys`
de `0003`, `cli_runtime`/`resolve_actor`/`unit_of_work`/`production_guard_error`, `sell` con
`enforce_retroactive_limit`, `members.service.create`/`id_by_document`/`count`,
`recompute_statuses`, `auth.service.active_admin_id_by_email`), `apex-db-1` está en
`0013_audit_verifications (head)`, el stack (cinco contenedores) está sano y `ruff`, `ruff format
--check`, `mypy --strict` y `tsc --noEmit` pasan en HEAD. El amarillo viene de seis cosas.
Primera, **el plan dice "ninguna migración" pero el cierre del Sprint 4A asignó a este sprint
`0014_audit_log_triggers_always` y el texto de `audit.forbid_mutation()`** (S4A-D98, V6; `SPRINT-04A.md`
"Deuda con dueño"; los dos triggers de `audit_log` siguen con `tgenabled = 'O'` en `apex-db-1`): hay
que decidirlo antes de W0-2, porque toca `tests/conftest.py`, `test_triggers_siempre_activos.py`,
RUNBOOK §6 y la definición de hecho ("ciclo `0001` a `0013`"). Segunda, **cinco contratos de los
desgloses chocan con reglas vigentes del código**: (a) `core/health.py` y `main.py` no pueden
importar `app.core.jobs` (`test_worker_boundaries.py:240`, `test_core_import_direction.py:114`) y
US-115 T4 lee `core.jobs.last_run` desde `/health`; (b) `CheckResult` es `Literal["ok", "down",
"unknown"]` (`core/health.py:25`) y los estados `stale`/`missing`/`corrupt`/`undecryptable`/
`ok_unverified` y `head`/`behind` no caben sin ampliar el tipo (mypy `--strict`); (c) el runner solo
escribe `result` `ok` o `error` (`worker/runner.py:155`) y `check_details` rechaza todo valor que no
sea entero (`core/jobs.py:235`, S4A-D55 d, S4A-D76): el job `backup_check` no puede guardar
`stale` en `result` ni `backup_name`/`backup_created_at`/`checked_at` en `details` como pide US-115
T3; (d) `test_guarded_calls.py:116` solo admite `enforce_retroactive_limit` desde `cli.py`, y
`sell` no tiene `max_retroactive_days` (US-111 T2/T4); (e) `test_crypto_bus_importers.py:35` fija
por igualdad exacta quién importa el bus fuera de `core/`: `app/imports/members_xlsx.py` (US-112
T4, `bus.blind_index`/`bus.batch`/`bus.digest`) y `worker/jobs/backup_check.py` (US-115,
`bus.digest_file`) rompen la prueba hasta que se decida la lista blanca o la vía por `members.service`.
Tercera, **`cli.py` mide exactamente 760 líneas**, el tope que S4A-D72/S4A-D95 fijaron para
extraer `cli_ops.py` ("el próximo comando que crezca lo extrae"): los cinco comandos nuevos
(`seed --demo`, `import-members`, `export-kek`, `verify-kek-backup`, `rotate-key`) exigen partirlo
en el Rojo de B1. Cuarta, **`infra/backup/` no existe, la imagen del api no trae `age`, el worker
no monta volúmenes** (`compose.yml:47-79`, `test_compose_config.sh:171` lo exige) **y `.env.example`
no conoce ninguna `BACKUP_*`**: como `api`, `worker` y `tools` reciben todo `.env` por `env_file` y
`Settings` usa `extra="forbid"`, cada variable nueva de operación debe entrar en `NON_API_ENV_VARS`
(`core/config.py:45`) o el api deja de arrancar. Quinta, **`openpyxl` y `pyrage` no están en
`pyproject.toml` ni en `uv.lock`**, `pyrage` no está verificada contra `pip-licenses`, y la lista
`banned-api` vive en tres sitios literales (`pyproject.toml:53-59`, `_imports.py:155`,
`test_ruff_banned_api.py:18`). Sexta, **la deuda del 4A sin slice en el plan**: R-3 (pausa del GC),
la regla de lint de `sessionStorage`, la barra `Tabs` a 1440 px y el contraste de "automático
(aviso)" (que son front, y este sprint "no tiene Waves 5a/5b"), los índices de `audit.audit_log` y
la revisión de S4A-D60/S4A-D61 tienen dueño "Sprint 4B" en `DECISIONES.md` pero ningún slice de
`SPRINT-04B.md` los nombra. Todo se absorbe con las condiciones de la sección 9; ninguna exige
cambiar el alcance de las nueve historias.

## Cómo se verificó

- Lectura completa de `SPRINT-04B.md`, `CRITICA.md` (M-8), `CRITICA-2.md` (M-8 recalculado, N-3,
  N-4, N-5), `README.md` del plan (sección "Sprint 4B" y "Cómo se cierra un sprint"), `CLAUDE.md`,
  `scripts/workflow/README.md`, `docs/ddd/impacto/sprint-04a.md` (referencia de formato), el bloque
  "Sprint 4A · decisiones de implementación" completo de `DECISIONES.md` (S4A-D1 a S4A-D128, las
  enmiendas E1 a E10, "Estado al cierre del Sprint 4A", "Dueños asignados al cierre del Sprint 4A" y
  "Estado de los dueños del Sprint 3 al cierre del Sprint 4A"), las decisiones G-07, G-09, N-05,
  N-07, N-15, N-16, N-24, N-48, N-50, Q17 y P3, `docs/BRECHAS.md` §11 (11.1 a 11.6),
  `docs/design/ROUTES.md` (el sprint no toca pantallas; se confirmó que no existe pantalla de
  respaldo ni de importación en `docs/design/screens/`), `docs/RUNBOOK.md` (índice, §6, §7, §9 y
  §11), `docs/scratch/sprint-04a.md` (V9 "Gates completos" y V12 "Stack final"), y los desgloses
  completos de US-030, US-111, US-112, US-114, US-115, US-116, US-117, US-118 y US-119 (más la
  historia de US-030 y la cabecera Q17 de US-112).
- Lectura del código que el sprint toca o consume (secciones 1 y 2): `main.py`, `cli.py`,
  `core/{health,jobs,alerts,config,clock,context,db,audit}.py`, `core/crypto/{bus,registry,digest,
  models,provider,local_provider,keyring,bootstrap,oplog,types,secret}.py`, `worker/{main,registry,
  runner,runtime,schedule}.py`, `worker/jobs/{__init__,expirations}.py`, los `service.py` de
  `members`, `memberships` (y `sell.py`, `lifecycle.py`, `expirations.py`), `payments`, `plans`,
  `auth` (y `users.py`), `settings` (y `schemas.py`), `modules/audit/queries.py`,
  `migrations/env.py`, `0002`, `0003`, `0012`, `0013`, `pyproject.toml`, `uv.lock` (grep),
  `api/Dockerfile`, `infra/compose.yml`, `compose.dev.yml`, `compose.e2e.yml`, `infra/README.md`,
  `infra/nginx/default.conf`, `.env.example`, `.gitignore`, `.github/workflows/ci.yml`,
  `scripts/ci/{test_compose_config,compose-smoke,test_api_image,check-licenses-api,notice,
  test_images_pinned}.sh`, `scripts/ci/licenses-exceptions.txt`, `NOTICE`, `scripts/workflow/
  slice-gate.sh` (mapeo de módulos), las 48 pruebas de `api/tests/architecture` (en especial
  `_imports.py`, `test_banned_imports.py`, `test_worker_boundaries.py`,
  `test_crypto_bus_importers.py`, `test_no_create_all.py`, `test_contact_callers.py`,
  `test_no_cross_models.py`, `test_core_import_direction.py`, `test_guarded_calls.py`,
  `test_sql_literals_constant.py`, `test_no_trigger_tampering.py`, `test_ruff_banned_api.py`,
  `test_audited_tables.py`, `test_no_physical_delete.py`, `test_file_and_function_size.py`,
  `test_no_direct_now.py`, `test_no_os_environ.py`, `test_settings_no_secrets.py`),
  `tests/conftest.py`, `tests/cli/{conftest,test_seed_cli}.py`, `tests/core/{test_health,
  test_migrations,test_startup_failure,test_env_example}.py`, `tests/migrations/
  test_triggers_siempre_activos.py`, `tests/factories/audit_chain.py`, `tests/crypto/
  test_crypto_tables.py`, `docs/adr/*`, `docs/openapi.json` (`HealthOut`), `web/src/core/api/
  types.ts`, `web/src/pages/RouteError.tsx`, `web/eslint.config.js`, `web/src/config/features.ts` y
  `web/src/features/system/*`.
- Estado del stack con `docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml
  ps`, `exec api alembic current`, `docker images`, `docker compose version`, `docker buildx
  version` y consultas de solo lectura sobre `apex-db-1` (triggers y su `tgenabled`, llaves,
  conteos, `pg_roles`, dueños de esquema). Disponibilidad de paquetes en las imágenes base con
  contenedores desechables (`apt-cache policy age` sobre `python:3.12-slim` por digest; `apk search`
  sobre `postgres:16-alpine`). **No se reconstruyó ninguna imagen ni se tocó el stack.**
- Gates baratos corridos en HEAD (sección 6): `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy src` en `api/` y `npx tsc --noEmit` en `web/`. No se corrió `pytest` ni `vitest`
  (instrucción de la Fase 0). No se modificó ningún archivo fuera de este.

## 1. Inventario de contratos que el sprint consume

Cada uno marcado como: **existe** (con la firma esperada), **existe con otra firma o nombre**, o
**no existe** (lo crea el sprint o falta decidirlo).

### Worker, jobs y salud (`core/jobs.py`, `core/health.py`, `main.py`, `worker/`)

- `last_run(session, job_name) -> JobRunView | None` (`core/jobs.py:297`): **existe**; devuelve el
  último intento por `started_at DESC` del nombre exacto. `JobRunView(id, job_name, run_date,
  started_at, finished_at, result, error, details)` (`:111`).
- `RESULTS = {"running", "ok", "error", "ok_unverified", "stale", "missing", "corrupt",
  "undecryptable"}` (`core/jobs.py:81`; CHECK `ck_job_runs_result` en `0012:47-50`): **existe**,
  ya incluye los seis estados del backup de US-115. `finish_run` acepta cualquiera de ellos
  (`_validar_resultado`, `:250`).
- **Pero** `JobResult(ok: bool, details)` (`worker/runner.py:77`) no lleva estado, y `_ejecutar`
  (`:155`) escribe `result = "ok" if respuesta.ok else "error"`: **existe con otra firma**; un job
  no puede devolver `stale`. Hace falta un campo opcional (`JobResult.result: str | None`) que el
  runner pase a `_cerrar` cuando esté en `RESULTS`.
- `DETAIL_KEYS` (`core/jobs.py:58-70`: `revisados`, `cambiadas`, `por_vencer`, `vencidas`,
  `otras`, `busy_omitidos`, `errores`, `placeholder_ok`) y `check_details` (`:235`; solo enteros,
  más `clock_override` booleano; S4A-D55 d, S4A-D76): **existen** y **contradicen US-115 T3**
  (`details` con `status`, `backup_name`, `backup_created_at`, `checked_at`, `verified: bool`).
  Ninguna cadena ni fecha entra en `details`: el estado va en `result`, los enteros (por ejemplo
  `verified`, `age_hours`, `size_mb`) en claves nuevas de `DETAIL_KEYS`, y el nombre del archivo y
  las fechas al log JSON (sin PII, como ya hace `job finished`, S4A-D128).
- `JobSpec(name, run, hour, minute, timeout_s=900)` (`worker/registry.py:21`), `JOBS` (`worker/
  jobs/__init__.py:9-11`, una tupla con `expirations`), `JobContext(session_factory, today, clock,
  simulated)` (`runner.py:67`), `run_job` (`:205`), `run_cycle` (`:251`), `DAILY_HOUR`/
  `DAILY_MINUTE` (`schedule.py`): **existen**. `backup_check` se agrega a `JOBS` después de
  `expirations`; `test_worker_boundaries.py:213` fija los ocho archivos mínimos del worker con `<=`
  (sumar `jobs/backup_check.py` no la rompe; agregarlo al conjunto la mantiene útil).
- `register_health_check(name, fn, *, critical: bool)` (`core/health.py:42`): **existe con otro
  nombre**. US-115 T4 y US-118 T1 piden `informative=True`; el código lo expresa con
  `critical=False` (informativa, mantiene el 200) y `critical=True` (503 `degraded`), y
  `tests/core/test_health.py:65-78` ya prueba una comprobación `backup` informativa.
- `CheckResult = Literal["ok", "down", "unknown"]` y `CheckFn = Callable[[], Awaitable[CheckResult]]`
  (`core/health.py:25-26`), `extras: dict[str, CheckResult]` (`:81`): **existen con otra forma**.
  Ni `stale`/`missing`/`corrupt`/`undecryptable`/`ok_unverified` ni `head`/`behind` caben: hay que
  ampliar el tipo (una unión por comprobación, o `str` validado por `HealthOut`). `HealthOut`
  (`:51-56`) tiene `extra="allow"` y `docs/openapi.json` publica `additionalProperties: true`
  (`:963`): los campos nuevos `backup` y `migrations` deben declararse explícitos para que el
  contrato y `web/src/core/api/types.ts:1205` los tipen (CI "openapi al día" y "tipos del api al
  día").
- `core/health.py` y `main.py` **no pueden importar `app.core.jobs`** ni siquiera de forma perezosa
  (`test_worker_boundaries.py:240`, `test_core_import_direction.py:114-135`, S4A-D73): US-115 T4
  (`core.jobs.last_run` desde el chequeo `backup`) **choca**. Dos salidas: (a) ampliar las dos
  pruebas para admitir solo `core/health.py` importando `last_run` y anotar la excepción en
  `DECISIONES.md`; (b) `core/backup_status.py` con la consulta `SELECT result FROM worker.job_runs
  WHERE job_name = :job ORDER BY started_at DESC LIMIT 1` como constante de módulo con parámetro
  ligado (`test_sql_literals_constant.py` acepta constantes en `core/`), registrado desde `main.py`
  sin tocar las reglas. Condición 6.
- `run_migrations(settings, script_location)` (`main.py:110`), `alembic_config(settings)` (`:101`),
  `_startup` (`:115-152`, `logger.exception("las migraciones fallaron...")` y relanza; `:126`),
  `register_startup_step` (`:76`): **existen**. US-118 T2 ("registrar la revisión que falló") es
  una precisión del `except` de `:125-127`; `tests/core/test_startup_failure.py:51,60` ya cubren el
  relanzamiento y la salida distinta de 0 de Uvicorn. El `head` del directorio se lee una vez
  (`ScriptDirectory.from_config(alembic_config(settings)).get_current_head()`) tras migrar; la
  revisión de la base en cada llamada con `MigrationContext` sobre una conexión con el mismo límite
  de 2 s de `check_db` (`DB_TIMEOUT_S`, `:27`): el healthcheck de Compose llama `/health` cada 10 s.
- Worker en Compose (`infra/compose.yml:47-79`): `read_only: true`, `tmpfs /tmp`, `cap_drop ALL`,
  `no-new-privileges`, **sin `volumes`** (S4A-D49) y `test_compose_config.sh:171` lo exige
  (`check(not worker.get("volumes"))`): **choca con US-115 T11** (`backups:/data/backups:ro` y la
  identidad opcional). La aserción pasa a "solo `backups` en solo lectura (más la identidad si se
  monta), nunca `keys` ni `uploads`" (`:63` sigue).
- `core/alerts.py` (`alert(code, **context)`, `ALERT_CONTEXT_KEYS = {job, result, error_type,
  attempts, run_date}`, `:23`): **existe**; un backup `stale` se informa por log de nivel `error` y
  `/health` (N-34); `alert("job_failed", ...)` solo si el job falla.

### Bus de criptografía (`core/crypto/`)

- `bus.digest = sha256_hex(data: bytes) -> str` (`bus.py:38`, `digest.py:14`), `bus.batch =
  oplog.batch(verb, data_class)` (`bus.py:39`, `oplog.py:134`), `bus.blind_index(data_class, value,
  *, record_id=None)` (`:109`), `bus.decrypt` que rechaza llaves `retired` con `CryptoError
  ("key_retired")` (`:82-83`): **existen**.
- `bus.digest_file(path, chunk_size)`, `bus.verify_age_archive(path, identity_path)`,
  `core/crypto/archive.py` (G-07): **no existen**; los crea S4B-B2. `digest.py` es el único módulo
  que importa `hashlib` hoy; `archive.py` puede importarlo (`is_allowed`, `_imports.py:176`,
  `pyproject.toml:62`). Ningún archivo de `src/app` importa `subprocess` hoy: la regla nueva de
  US-115 T10 ("`subprocess` solo en `core/crypto/archive.py`") nace sin excepciones previas.
- `registry.py`: `DataClassSpec(name, encrypt, index_kind, sign, value_type: Literal["str","date",
  "json"], columns)` (`:22`), `_V01` con las cinco clases `member.*` (`:32-45`), `get_spec` que
  lanza `unknown_data_class` (`:52-56`): **existe**. `backup.archive` y `attachment.sensitive`
  **no existen**: `backup.archive` entra en B2 (`encrypt=False`, `index_kind=None`, `sign=False`,
  columnas vacías); `attachment.sensitive` no entra en v0.1, así que `rotate-key
  attachment.sensitive` hoy daría `unknown_data_class`, no `rotation_not_supported` (G-09): el
  CLI decide su salida (condición 8).
- `oplog.record(verb, *, data_class: str | None, key_id: UUID | None, key_version: int | None,
  record_id=None, purpose=None, result="ok")` (`oplog.py:75`) y `crypto_ops.key_id`/`key_version`/
  `data_class` **nulos admitidos** (`models.py:139-141`, `0003:99-100`): **existe**; la fila
  `verify` de `backup.archive` sin llave y la fila `export` del respaldo de la KEK caben sin
  migración. `OP_VERBS` incluye `rotate` y `export` (`models.py:53-63`; CHECK `verb` en
  `0003:107-122`), `OP_PURPOSES` incluye `export` (`:65`): **existen**. **No hace falta
  `0014_crypto_ops_export_verb`** (US-116, paso 1 del orden de ejecución).
- `KEY_STATES = (active, decrypt_only, retired)` (`models.py:50`) y el trigger
  `crypto.guard_keys_update()` (`0003:203-238`): solo cambian `state`, `rotated_at`, `rotated_by`
  y `updated_at`; transiciones `active → decrypt_only | retired` y `decrypt_only → retired`;
  `retired → *` prohibido: **existe**, coincide con `next_key_state` de US-030 T1. Índice parcial
  de una `active` por par (`0003:89`) y un job en curso por clase (`tests/crypto/
  test_crypto_tables.py:125`): **existen**. `crypto.crypto_jobs` tiene 0 filas en `apex-db-1`.
- `KeyProvider` (`provider.py:30`: `wrap`, `unwrap`, `sign`, `verify`, `rotate`, `key_info`),
  `LocalFileProvider(kek_path, signing_key_path)` (`local_provider.py:69-72`), `parse_wrapped`
  (`:39`), `check_key_file(path, *, size, name)` (`:49`), `get_key_provider(settings)` (`provider.py:44`),
  `configure_provider`/`current_provider`: **existen**. **No hay método que devuelva la KEK en
  claro**: `export_kek` (US-116 T1) debe leer el archivo `CRYPTO_LOCAL_KEK_PATH` con
  `check_key_file` dentro de `core/crypto/kek_backup.py`, no por el proveedor. La DEK nueva de la
  rotación se genera como en `bootstrap._create_missing` (`os.urandom(DEK_LEN)` + `provider.wrap`,
  `bootstrap.py:54`).
- `Keyring` (`keyring.py:44`: `get`, `active_for`, `load_all`, `refresh_if_stale`, `ensure_loaded`),
  `configure_keyring`/`current_keyring`/`refresh_current`, `ensure_keys(session, provider) ->
  Keyring` (`bootstrap.py:81`): **existen**. Tras rotar, el proceso que rota recarga con `load_all`;
  el api recarga por `refresh_if_stale` en `current_user` (S2-D11).
- `types.py`: `Encrypted(data_class)` (`:40`), `BlindIndexed(data_class, *, source)` (`:71`),
  `_encrypted_props`/`_index_props` (`:122`, `:131`), `_check_key_current` (`:140`, el `FOR SHARE`
  del listener de US-028), `reveal(obj, field, purpose)` (`:227`): **existen**. `discovery.
  encrypted_columns(metadata, data_class)` (US-030 T2) **no existe**; puede derivar de
  `registry.columns` (`esquema.tabla.columna` en texto) y `Base.metadata.tables`, sin importar
  `models` de ningún módulo.
- `core/crypto/service.py`, `discovery.py`, `kek_backup.py`: **no existen**; los crea S4B-B3.
  `test_core_import_direction.py:59` prohíbe que `core/crypto` importe `core/audit`: las entradas
  de auditoría de la rotación y del respaldo se escriben desde `cli.py` con `core.audit.record`
  (`core/audit.py:341`; `AUDIT_ACTIONS` ya trae `update`, `export` y `verify`, `:76-85`), como
  dicen US-030 T10 y US-116 T2.
- `pyrage`: **no está** en `pyproject.toml:8-23` ni en `uv.lock`. Su licencia (MIT) y las ruedas
  `cp312` manylinux no se verificaron aquí (sin red): se confirman con `uv add` y
  `check-licenses-api.sh` en W0-1 (condición 2); la alternativa `apx-kek1` (scrypt + AES-256-GCM
  con `cryptography`, ya instalada) queda documentada en US-116.

### CLI (`cli.py`) y services que usan el seed y la importación

- `cli.py` **mide 760 líneas** (S4A-D95: "no pasa de 760; el próximo comando que crezca lo
  extrae"; tope duro 800 en `test_file_and_function_size.py:15`). Comandos: `export-openapi`
  (`:168`), `init-keys` (`:256`), `seed` (`:365`, con `--no-force-change` y `--as`; `tests/cli/
  test_seed_cli.py:203` invoca `["seed", "--no-force-change"]`), `issue-reset-link` (`:418`),
  `unlock-user` (`:491`), `recompute-memberships` (`:541`), `verify-audit` (`:691`). Ayudas:
  `unit_of_work(actor_id)` (`:42`), `resolve_actor(session, email)` (`:49`; exige cuenta **activa**
  con `active_user_id_by_email`, no exige admin), `RuntimeOptions`/`--db-timeouts` (`:86`),
  `cli_runtime(settings, options)` (`:292`), `_load_module_services` (`:282`), `_run` (`:348`),
  `production_guard_error(settings, opciones, actor)` (`:601`, S4A-D53/D95). **Existen**.
  `resolve_cli_actor` (US-030 T9) **no existe**: es `resolve_actor`. `seed --demo`,
  `import-members`, `export-kek`, `verify-kek-backup`, `rotate-key`: **no existen**.
- `auth.service.active_admin_id_by_email(session, email) -> UUID | None` (`users.py:231`,
  exportado en `service.py`), `active_user_id_by_email` (`:224`), `ids_by_email` (`:153`),
  `seed_admin` (`:243`): **existen**. Decidir si los comandos nuevos exigen admin (historias) o
  cuenta activa (patrón actual de `resolve_actor`): condición 4.
- `members.service.create(session, data: MemberCreate) -> MemberDetailOut` (`service.py:265`;
  actor de `get_actor()`, **sin `by=`**), `id_by_document(session, document) -> UUID | None`
  (`changes.py:105`, exportado en `service.py:98,170`), `count(session, *, include_deleted=False)`
  (`:310`), `MemberDocumentDuplicated(existing_id)` (`exceptions.py:30`; US-112 T7 lo llama
  `DuplicateDocument`): **existen**. `MemberCreate` (`schemas.py:78-93`): `first_name`,
  `last_name`, `document_type`, `document`, `phone`, `email`, `birth_date`, `sex`,
  `emergency_contact: EmergencyContactIn`, `data_consent: bool` (estricto): **no tiene `notes` ni
  `data_consent_at`**: la columna `notas` de Q17 no tiene destino (decidir: se ignora con aviso o
  se rechaza la fila) y la autorización queda `false` (Q16).
- `memberships.service.sell(session, *, member_id, plan_id, start_date=None, renew=False,
  first_payment=None, enforce_retroactive_limit=True, role=None)` (`sell.py:128-137`): **existe
  con otra firma** (US-111 pide `max_retroactive_days: int | None`). Además `test_guarded_calls.py:
  116` exige que `enforce_retroactive_limit` se nombre **solo en `cli.py`**: un `app/seed/demo.py`
  que lo pase falla la prueba (condición 4). Con `role=None` el primer pago conserva el tope
  retroactivo de `paid_at` (S3-D81): el seed pasa `role="admin"`.
- `payments.service.register(session, *, membership_id, amount_cop, method, reference=None,
  paid_at=None, confirm_overpayment=False, confirm_duplicate=False, role)` (`service.py:140-151`;
  `role` es obligatorio por nombre) y `void(session, *, payment_id, reason)` (`:249`): **existen**.
- `memberships.service.freeze(session, *, membership_id, frozen_from, frozen_to)`
  (`lifecycle.py:135`), `cancel(session, *, membership_id, reason)` (`:303`), `recompute_statuses
  (session_factory, *, today, page_size=RECOMPUTE_PAGE) -> RecomputeSummary` (`expirations.py:89`):
  **existen**; `recompute_statuses` recibe una **fábrica de sesiones** y abre una transacción por
  socio (S4A-D2): no puede correr "dentro de la misma transacción" del seed (US-111 T2): corre
  después del commit, igual que `cli recompute-memberships` (`cli.py:647`).
- `plans.service.create(session, data: PlanCreate)` (`service.py:261`), `settings.service.
  memberships_policy(session) -> MembershipsPolicy` (`service.py:201`; `expiring_days` 7,
  `max_freeze_days_per_membership` 30, `max_freezes_per_membership` 2, `max_retroactive_days` 7,
  `schemas.py:137-140`): **existen**.
- `core.audit.record(session, *, action, table_name, record_id, before, after, user_id=None,
  subject_member_id=None)` (`core/audit.py:341`): **existe** para la entrada resumen de la
  importación. `0002` no impone forma a `table_name`, pero `GET /audit?table=` exige
  `^[a-z_]{1,63}\.[a-z_]{1,63}$` y pertenencia a `AUDITABLE_TABLES` (`modules/audit/queries.py:
  68-80`, S4A-D46/D106): `table_name="members_import"` (US-112) se escribe pero nunca se filtra.
  Decidir el nombre (condición 4).
- `openpyxl` y `et_xmlfile`: **no están** en `pyproject.toml` ni `uv.lock`. `check-licenses-api.sh:18`
  permite `MIT;BSD;Apache;PostgreSQL;ISC;0BSD;PSF;Python Software Foundation` (la PSF **sí** está en
  la lista de `CLAUDE.md`; el motivo de US-112 para excluir `defusedxml` es viejo, pero
  `SPRINT-04B.md` ya decide "sin `defusedxml`" y los límites de 10 MB y 5.000 filas). `notice.sh`
  regenera el bloque de dependencias directas solo (CI "NOTICE al día").

### Infraestructura (`infra/`, Dockerfile, CI, scripts)

- `infra/backup/` (Dockerfile, `run.sh`, `lib.sh`, `restore.sh`, `manifest.schema.json`, pruebas):
  **no existe**. `infra/README.md:3` lo nombra como pendiente. El volumen `backups` está declarado
  (`compose.yml:134`) y sin uso; `test_compose_config.sh:69-70` ya lo espera declarado.
- Imágenes base: `postgres:16-alpine` (Alpine 3.23.4) trae en `apk` `age-1.2.1-r15`,
  `rclone-1.72.1-r4` y `supercronic-0.2.39-r6`; `python:3.12-slim` por digest (Debian 13.7) trae
  `age 1.2.1-1+b5` en `apt`. **La misma versión 1.2.1 de `age` en las dos imágenes** cumple
  "misma versión fijada que la imagen `backup`" (US-115) sin descargar binarios con checksum
  (US-114 T9 puede usar `apk add age=1.2.1-r15 rclone=1.72.1-r4 supercronic=0.2.39-r6`). Hay una
  `postgres:16-alpine` local sin digest (`4e6e670bb069`, 2026-04-21): el `FROM` debe ir por digest
  con fecha (`test_images_pinned.sh`, S3-D62), y ese script **solo revisa `api/Dockerfile`,
  `web/Dockerfile`, los dos compose, `test_nginx_conf.sh` y `ci.yml`** (`:9-14`): hay que sumarle
  `infra/backup/Dockerfile`.
- `api/Dockerfile`: `apt-get install tzdata` (`:30-36`), usuario `apex` 10001, sin `age`: **no
  existe** el binario que G-07 necesita; `test_api_image.sh` no lo comprueba.
- `infra/compose.yml`: `db` con healthcheck `pg_isready` (`:19-23`), `api` con healthcheck por
  Python y `start_period: 30s` (`:38-44`; US-118 pide 60 s), `web` con healthcheck `wget`
  (`:114-118`) y `depends_on: api: condition: service_started` (`:111-113`; US-118 pide
  `service_healthy`), `worker` endurecido, `tools` con `keys` en escritura y `uploads` (`:92-94`) y
  **sin bind al host** (el `export-kek --out` y el `import-members /plantillas/...` de la demo
  necesitan `-v` en el `run`), sin servicio `backup`, sin `IMAGE_TAG`: las imágenes son
  `apex-api:local`/`apex-web:local` construidas en el host, no hay registro. **`docker compose
  pull` de US-117 T3 no aplica a imágenes locales**: `deploy.sh` debe construir (con el quirk de
  buildx de este equipo, RUNBOOK §7) o el plan decide publicar en un registro (fuera de alcance).
- `.env.example`: sin `BACKUP_*`, `RCLONE_*`, `IMAGE_TAG`, `DEPLOY_HEALTH_TIMEOUT`,
  `BACKUP_DIR`, `BACKUP_AGE_VERIFY_IDENTITY_PATH`. `Settings` (`core/config.py:111`, `extra=
  "forbid"`, `:117`) con origen dotenv propio que **rechaza toda clave desconocida salvo
  `NON_API_ENV_VARS`** (`:45`, `:95-110`); `tests/core/test_env_example.py:31,37` exige que cada
  campo de `Settings` esté en `.env.example` y que toda clave ajena esté en `NON_API_ENV_VARS`.
  `RCLONE_CONFIG_*` es un prefijo variable: `NON_API_ENV_VARS` es un `frozenset` de nombres
  exactos, así que o se fijan los nombres (`RCLONE_CONFIG_APEX_TYPE`, `..._PROVIDER`,
  `..._ACCESS_KEY_ID`, `..._SECRET_ACCESS_KEY`, `..._ENDPOINT`) o `config.py` gana una regla de
  prefijo (`core/` compartido: tocarlo en un solo slice).
- `.github/workflows/ci.yml`: sin `shellcheck` (ShellCheck es GPL: `CLAUDE.md` manda `bash -n`;
  US-114 T8, US-117 T9 y US-116 lo piden: se sustituye), sin `bats` (MIT, no está instalado en el
  host; `which bats` vacío), sin job de release ni de etiquetas, sin build de la imagen de backup
  (`images` solo construye `apex-api:ci` y `apex-web:ci`, `:213-240`); `e2e-stack` levanta con
  `$DC up -d --build` sin lista de servicios (`:315`): el servicio `backup` arrancará ahí
  (supercronic en espera) y `down -v` lo limpia (`:355`).
- `scripts/ci/compose-smoke.sh`: construye `api` (`:52`), levanta `db`, `db_test`, `api`, `worker`
  (`:76-113`), `tools seed` (`:123`) y `web` (`:129-142`); nada de `backup`. Fuera de CI no borra
  volúmenes (`:30-31`).
- `scripts/workflow/slice-gate.sh:97-110`: mapeo `core/<x>`, `crypto`, `main`, `worker`, `cli`
  (→ `src/app/cli.py`), `architecture` y `<modulo>` → `src/app/modules/<modulo>`. **`app/seed/` y
  `app/imports/` (US-111, US-112) no tienen mapeo**: `slice-gate.sh seed` falla con "módulo
  inexistente: api/src/app/modules/seed" y `slice-gate.sh cli` solo pasa `ruff`/`mypy` sobre
  `cli.py`. Condición 4.
- Host: `age`, `bats` y `shellcheck` no instalados; `uv` en `~/.local/bin`; `python` no está en
  `PATH` (se usa `uv run`). Compose v5.6.1 y buildx v0.38.1 (quirk de `build.network: host`,
  RUNBOOK §7, sigue vigente).

### Pruebas de arquitectura y fixtures que fijan el estado del Sprint 4A

- `test_crypto_bus_importers.py`: `IMPORTADORES_REALES` **exacto** (`:35-45`: `cli.py`, `main.py`,
  `worker/runtime.py`, `members/{changes,detail,models,service}.py`), `ARRANQUE` (`:46`) solo con
  `install_crypto_type_listeners`, `PREFIJOS_PERMITIDOS` (`:47-52`: `core/`, `modules/members/`,
  `modules/athletes/`, `modules/attachments/`). `VIGILADOS` son solo `bus` y `types` (`:32`):
  importar `app.core.crypto.archive` o `app.core.crypto.service` directamente **no** se vigila,
  pero contradice la única puerta (`CLAUDE.md`, bus 1) y G-07 ("el bus lo reexpone").
- `test_worker_boundaries.py`: `_archivos_de_aplicacion()` = `worker/**` + `cli.py` (`:151`);
  `esperados` de ocho archivos (`:213-222`); `test_solo_el_worker_importa_core_jobs` (`:240`); el
  worker no escribe SQL (`text`/`exec_driver_sql`, `:231`). `app/seed/` y `app/imports/` quedan
  fuera de todo recorrido (`test_no_cross_models.py` solo barre `app/modules/*`, `:103`): US-111
  T10 y US-112 T13 se implementan aquí, no en `test_no_cross_models.py`.
- `test_guarded_calls.py`: `enforce_retroactive_limit` solo en `cli.py` (`:116-124`);
  `AUTOCOMMIT_PERMITIDO` (`:127`); `with_for_update` sobre `Membership` solo en
  `sell.lock_membership` (`:178`); nadie fuera de `memberships` nombra `Membership` (`:224`). La
  rotación (`core/crypto/service.py`) puede usar `with_for_update` sobre `CryptoKey` y sobre
  `Table` de Core (la restricción es por carpeta y por nombre), nunca `isolation_level`.
- `test_sql_literals_constant.py` (`RAICES` = `modules` y `core`, `:28`): el SQL de la rotación
  (`split_part(<col>, '.', 2) <> :active_id ... FOR UPDATE`, US-030 T4) se construye con Core
  (`select(t.c.id, t.c[nombre]).where(func.split_part(...) != ...).with_for_update()`), no con
  `text()` armado por tabla.
- `test_core_import_direction.py`: `core/crypto` no importa `core/audit` (`:59`); sin ciclos en
  `core/` (`:84`); `jobs`/`alerts` sin `modules` ni `audit`, y `audit.py`/`health.py` sin `jobs`
  (`:114-135`).
- `test_banned_imports.py` + `_imports.BANNED_MODULES` (`:155-157`) + `pyproject.toml:53-59` +
  `test_ruff_banned_api.py:18,38` ("lista los seis módulos"): **cuatro sitios literales** para
  agregar `pyrage` (US-116 T7). `subprocess` no está prohibido hoy; la regla nueva (solo
  `core/crypto/archive.py`) se agrega como caso aparte en `test_banned_imports.py`.
- `test_no_direct_now.py` (`PERMITIDO = core/clock.py`, `:13`), `test_no_os_environ.py`
  (`core/config.py`, `:13`), `test_no_trigger_tampering.py` (`PATRONES` `DISABLE TRIGGER`,
  `session_replication_role`, `ALTER TABLE ... TRIGGER`, `TRUNCATE`; **solo barre `app/`**,
  `:7-8`): la migración `0014` y `restore.sh` quedan fuera; `archive.py`, `backup_check.py`,
  `kek_backup.py` y `service.py` toman el tiempo de `current_clock()`/`ctx.clock`.
- `test_audited_tables.py`: `EXCLUIDAS` (`:45-52`) ya contiene las tres tablas `crypto.*`,
  `worker.job_runs` y `audit.verifications`; `_cargar_modelos` (`:73-77`) importa `core.jobs` y
  `core.audit_verify`. Nada que hacer.
- `test_no_physical_delete.py` (`MODELOS` con `CryptoKey`, `CryptoOp`, `AuditVerification`,
  `:24-35`): la rotación nunca borra llaves (RN-14) ni filas de `crypto_ops`.
- `test_contact_callers.py` (`CONTACT_CALLERS = frozenset()`, `:317`): sin impacto.
- `test_triggers_siempre_activos.py`: listas exactas de pagos (`:61`), congelaciones, membresías y
  verificaciones (`:141`); **no cubre `audit_log`** (hoy `'O'`). `tests/conftest.py:310-312` apaga,
  borra y vuelve a encender `audit.audit_log` con `ENABLE TRIGGER USER` (deja `'O'`); si `0014` los
  pasa a `ENABLE ALWAYS`, esa línea los degrada en cada sesión de pruebas (la lección E1 del Sprint
  3): hay que encenderlos **por nombre** con `ENABLE ALWAYS` en `LIMPIEZA_DE_SESION`, en el
  `finally` de `dos_sesiones` y en `limpiar_tras_dos_sesiones`, como ya hace `tests/factories/
  audit_chain.py:44-47`.
- `tests/core/test_health.py:65-78`: una comprobación `backup` con `critical=False` que devuelve
  `"down"` mantiene el 200: el Rojo de B2 la reescribe con los estados reales.
- `tests/core/test_migrations.py:51,60,76`: `test_downgrade_a_base_vacia_y_vuelta_a_head` y
  `test_single_head` recorren toda la cadena; `tests/core/test_health_migrations.py` (US-118 T4)
  hace `downgrade -1` sobre `db_test`, que `migrated_database` (`conftest.py:324`, sesión) deja en
  `head`: restaurar `head` en el `finally` o correr en un subproceso con una base propia.

## 2. Blast radius por slice

### S4B-W0-1 · Contenedor de backup y `age`

- Archivos nuevos: `infra/backup/{Dockerfile,run.sh,lib.sh,manifest.schema.json}`,
  `infra/backup/tests/*`, `docs/operacion/` (carpeta nueva, no está en la estructura de
  `CLAUDE.md`). Tocados: `infra/compose.yml` (servicio `backup`: `backups` rw, `uploads:ro`,
  `env_file ../.env`, `depends_on db healthy`, sin `ports`, `restart`), `api/Dockerfile` (`age`
  por `apt` con versión fijada, `test_api_image.sh` con `age --version`), `.env.example` y
  `core/config.py` (`NON_API_ENV_VARS` con `BACKUP_AGE_RECIPIENT`, `BACKUP_RCLONE_REMOTE`,
  `BACKUP_KEEP_DAYS`, `BACKUP_CRON`, los `RCLONE_CONFIG_*` con nombre fijo, `IMAGE_TAG` si se
  decide, `DEPLOY_HEALTH_TIMEOUT`), `scripts/ci/test_images_pinned.sh` (sumar
  `infra/backup/Dockerfile`), `scripts/ci/test_compose_config.sh` (servicio `backup`, volúmenes,
  `backups` en uso), `scripts/ci/compose-smoke.sh` (`up -d backup`, `run --rm backup run.sh`,
  `latest.json` válido), `.github/workflows/ci.yml` (`images`: build `apex-backup:ci`,
  `check-image-secrets.sh` sobre ella, `bash -n infra/backup/*.sh`, pruebas de `lib.sh`), `NOTICE`
  (bloque fijo "recursos que no son paquetes": `age`, `rclone`, `supercronic`, imagen `postgres`;
  `notice.sh:40-55` solo escribe un bloque literal), `CLAUDE.md` (estructura: `infra/backup/`,
  `docs/operacion/`, `docs/plantillas/`; bus regla 1 dice "desde v0.2, `digest_file`…" y el sprint
  lo hace en v0.1), `RUNBOOK.md` (sección nueva de respaldo).
- Lo rompe fuera del gate: `tests/core/test_env_example.py:37` (`test_toda_clave_ajena_al_api_esta_
  en_non_api_env_vars`) en cuanto `.env.example` gane una `BACKUP_*` que no esté en
  `NON_API_ENV_VARS`; peor, **el api, el worker y `tools` dejan de arrancar** con un `.env` que
  traiga esas claves (`extra="forbid"`). `test_images_pinned.sh` no falla (no mira el Dockerfile
  nuevo) hasta que se le agregue, y entonces exige digest y fecha. `test_compose_config.sh:69`
  ("volúmenes pgdata, uploads y keys en uso") sigue verde; sumar `backups` a esa aserción.
- `bats` no está en el host ni en la CI: las funciones puras de `lib.sh` (`backup_name`,
  `retention_to_delete`) se prueban con el patrón ya existente de `scripts/workflow/tests/run.sh`
  (Bash puro) o se instala `bats-core` (MIT) solo en el job `images`; decidirlo en W0-1.
- Quirk de buildx: la imagen de backup y la del api (con `age`) se construyen con `docker buildx
  build --load --network host --allow network.host` y se levantan con `up -d --no-build` (RUNBOOK
  §7). El `tar` y el `sh` de Alpine son parte de la imagen base (GPL en el SO, no dependencias):
  se anota en `NOTICE` como dice US-114.

### S4B-W0-2 · Arranque ordenado, despliegue y rol de base separado

- Archivos: `infra/compose.yml` (`web.depends_on.api: service_healthy`, `api.healthcheck.
  start_period: 60s`, `worker` con `backups:/data/backups:ro`, `backup` con `depends_on db`),
  `infra/deploy.sh`, `infra/backup/restore.sh`, `infra/tests/*` (nuevos; `bash -n` en CI),
  `docs/operacion/actualizar.md`, `docs/operacion/respaldo-y-restauracion.md`, `RUNBOOK.md` §6
  (`0014`), `migrations/versions/0014_audit_log_triggers_always.py` **si se decide aquí**
  (condición 1), `tests/migrations/test_0014_*.py`, `tests/migrations/
  test_triggers_siempre_activos.py` (la pareja `audit_log_forbid_mutation`/`_truncate` en `'A'`),
  `tests/conftest.py:310-312` y las dos limpiezas de `dos_sesiones` (`ENABLE ALWAYS TRIGGER` por
  nombre), `infra/db/init/*.sql` o RUNBOOK (creación del rol del api), `core/config.py` y
  `.env.example` (`MIGRATIONS_DATABASE_URL` o equivalente), `main.py:101-112` (`alembic_config`
  con la URL del dueño), `migrations/env.py:57` (`get_settings`), `scripts/ci/
  test_compose_config.sh` (aserciones nuevas: `web` tras `api` healthy, `worker` con solo
  `backups` ro, `backup` sin `ports`, `env_file` de cada servicio).
- Lo rompe fuera del gate: `test_compose_config.sh:171` (`worker sin volumenes`) al montar
  `backups`; `:111-120` (`env_file` por servicio) si el worker pasa a un `.env` propio (S4A-D85
  L-5: ".env completo del worker" es la deuda; decidir si se parte `.env` o solo se cambia la
  credencial); `tests/conftest.py` y `tests/factories/audit_chain.py` dependen de que el rol de
  pruebas sea dueño (`DISABLE TRIGGER USER` exige dueño): **las pruebas siguen con el superusuario
  `apex` de `db_test`** (`compose.dev.yml:43-59`), el rol separado es solo de `apex-db-1` y del
  stack de producción.
- **Contradicción interna del rol separado (S3-D49, I-2):** `main.py:122-128` corre `alembic
  upgrade head` al arrancar con `DATABASE_URL`; si el api se conecta con un rol que no es dueño de
  `payments`, `memberships` y `audit`, **`0014` (y cualquier migración futura) falla al arrancar**
  (`ALTER TABLE` exige dueño). Opciones: (a) `MIGRATIONS_DATABASE_URL` en `Settings` (dueño) que
  usan solo `run_migrations`, `migrations/env.py` y `cli_runtime`, y `DATABASE_URL` (rol del api)
  para todo lo demás; (b) el api es dueño pero no superusuario (cierra `session_replication_role`,
  que exige superusuario, pero no `DISABLE TRIGGER`). Hoy `apex-db-1` tiene **un solo rol `apex`,
  superusuario y dueño de los nueve esquemas** (consulta a `pg_roles` y `pg_namespace`), y el
  contenedor `db` solo ejecuta `initdb` en un volumen vacío: el rol nuevo se crea por script en
  `/docker-entrypoint-initdb.d` (solo stacks nuevos, como el `e2e-stack` de CI) **y** por un
  procedimiento manual en RUNBOOK para `apex-db-1` y el servidor. Condición 3.
- Despliegue: no hay registro de imágenes ni `IMAGE_TAG`; `apex-api:local` se construye en el
  host. `deploy.sh` reemplaza `docker compose pull` por la construcción (con el quirk) o el plan
  decide un registro (`ghcr.io`) y el push humano. El rollback de imagen es volver a etiquetar el
  id anterior (`docker tag <id> apex-api:local`), que `deploy-<fecha>.state.json` guarda. La
  espera de salud consulta `http://127.0.0.1:${WEB_PORT}/api/v1/health` (Nginx pasa `/api/`,
  `default.conf:61`; `WEB_PORT=8180` aquí, 80 en el servidor); `jq` no está garantizado en el
  host: la lectura de `db`/`migrations` se hace con `python -c` o `grep`.
- `restore.sh` corre en la imagen `backup` (tiene `pg_restore` 16 y `age`) pero ese servicio monta
  `uploads` en solo lectura: la restauración de `uploads/` necesita `run --rm -v apex_uploads:
  /data/uploads backup restore.sh ...` o un servicio `restore` con perfil. Se niega si hay filas en
  `members.members`, `payments.payments` o `audit.audit_log` salvo `--i-know-this-overwrites`.
- Sprint 3 pendiente con dueño S4B-W0-2 (`DECISIONES.md`, "Estado de los dueños del Sprint 3"):
  W0-2 MEDIUM-1 (`25P03` y cortes del servidor como 503 `busy`, no 500), MEDIUM-2 (fallo de
  `crypto_ops` durante el rollback), N-6 y N-7 (remedir el p99 del login). Ninguno está en
  `SPRINT-04B.md`: el plan los confirma o los reasigna con dueño (condición 1).

### S4B-B1 · Datos de demostración e importación (US-111, US-112)

- Archivos nuevos: `app/seed/{__init__,demo}.py`, `app/imports/{__init__,members_xlsx,report}.py`,
  `docs/plantillas/importar-socios.xlsx` y `scripts/plantillas/generar_importar_socios.py`,
  `docs/operacion/importar-socios.md`, `tests/cli/{test_demo_dataset,test_seed_demo,
  test_members_xlsx_parse,test_import_members,test_import_members_perf}.py`, `tests/fixtures/
  socios-3.xlsx` (o generados en la prueba). Tocados: `cli.py` (**partir antes**: `cli_ops.py` o
  un módulo por comando, registrado desde `cli.py` con `app.command`), `pyproject.toml`
  (`openpyxl`), `uv.lock`, `NOTICE`, `scripts/workflow/slice-gate.sh` y su README (mapeos `seed` y
  `imports`), `tests/architecture/test_worker_boundaries.py` (`_archivos_de_aplicacion` con
  `seed/**` e `imports/**`), `test_guarded_calls.py:116` (si el seed nombra
  `enforce_retroactive_limit`), `test_crypto_bus_importers.py` (si `imports/` importa el bus),
  `tests/cli/test_seed_cli.py` (el `seed` existente gana `--demo` sin cambiar `--no-force-change`
  ni `--as`), `CLAUDE.md` (estructura).
- Pruebas que fallan en silencio fuera del gate:
  - `test_guarded_calls.py::test_enforce_retroactive_limit_solo_desde_el_cli` si
    `app/seed/demo.py` llama `sell(..., enforce_retroactive_limit=False)`. Salidas: el seed recibe
    de `cli.py` una función de venta ya configurada (el argumento se nombra solo en `cli.py`), o la
    prueba admite `seed/demo.py` con una decisión anotada.
  - `test_crypto_bus_importers.py::test_los_importadores_fuera_de_core_son_exactamente_los_fijados`
    y `test_todo_importador_esta_en_la_lista_blanca` si `app/imports/members_xlsx.py` importa
    `bus.blind_index`, `bus.batch` o `bus.digest`. Recomendado: la importación no toca el bus;
    `members.service` le da lo que necesita (`id_by_document` ya existe y calcula el índice por
    dentro; un `document_index(document)`/`import_batch()` nuevos en la fachada de `members` para
    los repetidos del archivo y el lote de `crypto_ops`), y el hash del archivo lo da `bus.digest`
    desde `cli.py`… que tampoco puede (`ARRANQUE`): por `members.service` o se amplía la lista
    blanca con `imports/members_xlsx.py` y nombres exactos. Decidir en el Rojo.
  - `test_file_and_function_size.py`: `cli.py` en 760 (tope 800): cinco comandos más lo superan.
  - `test_worker_boundaries.py` no barre `seed/` ni `imports/` hasta que se amplíe
    `_archivos_de_aplicacion()` (US-111 T10).
  - `tests/cli/test_seed_cli.py:203,237`: la opción `--demo` se suma al comando `seed` existente;
    `--as` con cuenta inactiva/bloqueada/técnica sigue saliendo con 2.
- Contratos: `sell(..., enforce_retroactive_limit=False, role="admin")`; `payments.register(...,
  paid_at=<pasado>, role="admin")`; `members.service.create(session, data)` con el actor en
  `unit_of_work(actor)`; `recompute_statuses(db.get_sessionmaker(), today=today)` **después** del
  commit del seed; una transacción **por socio** (plan B1, PL6/S3-D95; manda sobre US-111 T2 "todo
  en una sola transacción": un bucle de `lock_member` de 30 socios en una transacción con flushes
  auditados entre medio invierte el orden D3); idempotencia por `id_by_document` de los documentos
  `999…`; `--force-demo-on-non-empty` necesario sobre `apex-db-1` (265 socios, 67 vivos); el
  cuadre de Inicio (T8 de US-109) se mide contra `GET /dashboard` con esos datos sumados a los que
  haya. `MemberCreate` no tiene `notes`: la columna `notas` de Q17 se lee y se descarta con aviso
  en el reporte, o se rechaza; `sex` acepta `f`/`m`/`x` (`Sex`); `emergency_contact` es
  `EmergencyContactIn(name, phone)`. El reporte CSV con `;` y BOM (N-29) se escribe junto al
  archivo, que en `tools` es un bind del operador (`-v "$PWD/docs/plantillas:/plantillas:ro"`
  de la demo es solo lectura: **el reporte no se puede escribir ahí**; `--report <ruta>` o un
  bind con escritura). `--dry-run`: `crypto_ops` se registra en la sesión del llamador (`oplog.
  _before_commit`, `oplog.py:199`): el `ROLLBACK` no deja rastro (US-112 T11 lo prueba).
- Perf: marcador `perf` (`pyproject.toml:78-81`, `--strict-markers`), no `slow`; `SPRINT-04B.md`
  pide 5.000 filas y US-112 T12 1.000: fijar 5.000 (el límite) con el tiempo medido en el
  cuaderno. La cadena de auditoría toma `pg_advisory_xact_lock(4_270_002)` en cada flush: un
  flush por lote de 500 reduce las esperas (US-112, riesgos).

### S4B-B2 · Backup y su verificación (US-114 backend, US-115)

- Archivos nuevos: `core/crypto/archive.py`, `worker/jobs/backup_check.py`, `tests/crypto/
  test_archive.py`, `tests/worker/{test_backup_check_evaluate,test_backup_check}.py`. Tocados:
  `core/crypto/bus.py` (reexporta `digest_file`, `verify_age_archive`), `core/crypto/registry.py`
  (`backup.archive`), `core/jobs.py` (`DETAIL_KEYS` con enteros nuevos), `worker/runner.py`
  (`JobResult.result` opcional y `_ejecutar:155`), `worker/jobs/__init__.py` (`JOBS`),
  `core/health.py` (tipos y campo `backup`), `main.py` (registro de la comprobación o
  `core/backup_status.py`), `core/config.py` y `.env.example` (`BACKUP_DIR`,
  `BACKUP_AGE_VERIFY_IDENTITY_PATH`), `infra/compose.yml` (worker con `backups:ro`; la identidad
  opcional comentada), `tests/architecture/test_banned_imports.py` (regla de `subprocess`),
  `test_crypto_bus_importers.py` (lista blanca para `worker/jobs/backup_check.py` con los dos
  nombres), `test_worker_boundaries.py:213` (`jobs/backup_check.py`), `tests/core/test_health.py`,
  `tests/worker/test_jobs_core.py` (si cambia `DETAIL_KEYS`), `docs/openapi.json` y
  `web/src/core/api/types.ts` (regenerados), `api/Dockerfile` ya con `age` (W0-1).
- Pruebas que fallan en silencio fuera del gate:
  - `test_worker_boundaries.py::test_solo_el_worker_importa_core_jobs` y
    `test_core_import_direction.py::test_jobs_y_alerts_no_importan_modulos_ni_audit` si
    `core/health.py` o `main.py` importan `core.jobs` (condición 6).
  - `test_crypto_bus_importers.py` si `backup_check.py` importa `bus` (condición 6).
  - `test_no_direct_now.py` si `backup_check.py` o `archive.py` llaman `datetime.now`: la edad del
    backup se mide con `ctx.clock.now_utc()`.
  - `tests/worker/test_runner.py` y `test_jobs_core.py` fijan `DETAIL_KEYS` y el mapeo
    `ok`/`error`: cambian en el Rojo.
  - `test_compose_config.sh:171` (worker sin volúmenes) al montar `backups`.
  - `mypy --strict` sobre `core/health.py` con los estados nuevos (`CheckResult`).
  - `test_env_example.py:31` por `BACKUP_DIR` y `BACKUP_AGE_VERIFY_IDENTITY_PATH` en `Settings`.
- Contratos: `verify_age_archive` invoca `age -d -i <identidad> <archivo>` con lista de argumentos,
  `stdout` a un lector que cuenta y descarta, `stderr` descartado, `timeout` de 600 s, devuelve
  `False` ante cualquier fallo y registra `oplog.record("verify", data_class="backup.archive",
  key_id=None, key_version=None, result=...)` (nulos admitidos); `digest_file` no registra (N-06).
  El worker solo necesita el binario `age` (G-07), **no la identidad maestra**: la identidad de
  verificación es opcional y distinta (N-50, US-115 T12). `evaluate(manifest, now_utc,
  file_exists, sha256_ok, decrypt_ok)` pura, con la prioridad de US-115. El `details` del job:
  solo enteros (`verified: 0|1`, `age_hours`, `size_mb`); el estado en `result`.
- Salud: `backup` informativo con `critical=False` (nunca 503, N-16); `HealthOut.backup:
  Literal["ok","ok_unverified","stale","missing","corrupt","undecryptable","unknown"] = "unknown"`
  explícito; `/health` no expone nombre, ruta ni error. Se regenera `docs/openapi.json`
  (`export-openapi`) y `types.ts` (`npm run gen:api`): ningún archivo del front lo consume, pero la
  CI compara los dos.

### S4B-B3 · Respaldo de la KEK y rotación de llave (US-116, US-030)

- Archivos nuevos: `core/crypto/{kek_backup,service,discovery}.py`, `infra/backup/restore.sh` (si
  no quedó en W0-2), `infra/tests/{restore_e2e.sh,restore_guard.*}`, `docs/operacion/
  rotar-llave.md`, `tests/crypto/{test_kek_backup,test_next_key_state,test_rotate,
  test_rotate_concurrency,test_rotate_index}.py`, `tests/cli/{test_export_kek,
  test_cli_rotate_key}.py` (US-030 T15 lo pone en `tests/test_cli_rotate_key.py`: el gate acepta
  cualquier archivo bajo `api/tests/`, pero la convención es `tests/cli/`). Tocados: `cli.py` (ya
  partido en B1), `pyproject.toml` (`pyrage`), `uv.lock`, `NOTICE`, `pyproject.toml:53-59`,
  `_imports.py:155`, `test_ruff_banned_api.py:18,38` (`pyrage` prohibido fuera del bus),
  `tests/crypto/test_crypto_tables.py` (nada: las transiciones ya se prueban), `RUNBOOK.md`
  (§9 "comandos largos" ya nombra `rotate-key` con `--db-timeouts off`).
- Pruebas que fallan en silencio fuera del gate:
  - `test_ruff_banned_api.py::test_banned_api_lista_los_seis_modulos` al sumar `pyrage` (pasa a
    siete en los tres sitios).
  - `test_crypto_bus_importers.py::test_el_arranque_solo_importa_el_instalador_de_types`: `cli.py`
    no puede importar `bus` ni `types`; toda la criptografía de los comandos vive en
    `core/crypto/service.py` y `kek_backup.py` (importarlos desde `cli.py` no se vigila).
  - `test_core_import_direction.py:59`: `core/crypto/service.py` no importa `core/audit`.
  - `test_sql_literals_constant.py`: el `SELECT ... FOR UPDATE` por tabla y columna va en Core.
  - `test_guarded_calls.py:224`: `discovery.py` no nombra `Membership` (recorre `Base.metadata`
    por `registry.columns`).
  - `test_no_direct_now.py`: `rotated_at`/`finished_at` con `current_clock()`.
  - `test_file_and_function_size.py`: `start_rotation`, `reencrypt_batch`, `rotate_index` se
    diseñan por debajo de 50 líneas.
- Contratos: `export_kek(provider, passphrase)` lee la KEK del archivo (`check_key_file`), cifra
  con `pyrage.passphrase.encrypt` (o `apx-kek1` si `pyrage` no pasa licencias/ruedas), nunca por
  argumento, rechaza rutas bajo `BACKUP_DIR` y dentro del volumen `backups`; `verify_kek_backup`
  descifra en memoria y prueba `unwrap` de cada DEK `active`/`decrypt_only` con un
  `LocalFileProvider` en memoria (hoy exige dos rutas de archivo, `local_provider.py:72`: se
  construye con un archivo temporal 600 en `tmpfs` o se extrae `unwrap_with(kek_bytes)`). El
  `tools` sin bind al host: `export-kek --out /out/kek.age` con `-v "$PWD/out:/out"` en la demo.
  Rotación: candado `pg_try_advisory_lock(hashtext('apex:rotate:' || :data_class))` como constante
  con parámetro ligado en una conexión dedicada (patrón `core/audit_verify.py:56-57`); el reclamo
  de la llave `active` con `FOR UPDATE` espera a los `FOR SHARE` de `_check_key_current`;
  `attachment.sensitive` no existe en el registro: `rotate-key` responde con salida 2 y mensaje
  fijo "clase sin rotación hasta EP-18" (G-09; el 409 `rotation_not_supported` es del endpoint de
  US-145); la pregunta abierta de US-030 (blobs de `audit_log` frente a `retired`) se cierra en
  W0-1 T-DOC con la alternativa por defecto (no cuentan: el detalle de auditoría ya muestra
  marcadores y nunca descifra, S4A-D52, y `bus.decrypt` lanza `key_retired`).
- Orden: US-116 antes que US-030 dentro del slice (riesgo 1 del plan); `pg_dump` y `export-kek`
  antes de la primera rotación real sobre `apex-db-1` (las ocho llaves están en versión 1).

### S4B-B4 · Despliegue, arranque y ADR (US-117, US-118, US-119)

- Archivos nuevos: `tests/core/{test_health_migrations,test_chain_hash_vector}.py`,
  `tests/architecture/test_adr_docs.py`, `docs/adr/{ADR-001-monolito-modular,
  ADR-003-pagos-inmutables,ADR-004-serializacion-canonica-de-auditoria}.md`. Tocados:
  `core/health.py` (`migrations` crítico), `main.py` (`head` leído tras migrar; log con la
  revisión que falló), `docs/adr/ADR-002-criptografia.md` (**ya existe**, 37 líneas, 4 secciones y
  "Pendiente para US-119"; US-119 lo llama `ADR-002-bus-de-criptografia.md` con 6 secciones:
  conservar el nombre que `CLAUDE.md` lista y completarlo), `docs/adr/README.md` (3 líneas),
  `README.md` (enlaces a `docs/adr` y `docs/operacion`), `docs/openapi.json` y `types.ts`
  (`migrations`), `infra/compose.yml` (si no quedó en W0-2).
- Pruebas que fallan en silencio: `tests/core/test_health.py` (el cuerpo gana `migrations`);
  `test_migrations.py` si `test_health_migrations.py` deja `db_test` en `downgrade -1`;
  `test_no_create_all.py` ya existe (US-118 T6 "ampliada": no hay nada que ampliar; se verifica que
  siga verde); `test_adr_docs.py` exige que cada ruta citada en "Cómo se verifica" exista
  (`tests/payments/test_immutability_trigger.py` de US-096: comprobar el nombre real antes de
  citarlo).
- Contratos: `/health` responde 503 `degraded` con `migrations: "behind"`; Compose marca el api
  `unhealthy` y `worker`/`web` no arrancan (`depends_on` healthy): es el comportamiento deseado
  tras un rollback de imagen con esquema más nuevo (riesgo de US-117). En desarrollo, un
  `0014_*.py` a medio escribir bajo `--reload` (`compose.dev.yml:11-17`, bind de `migrations`)
  rompe el arranque como en 4A: escribir y probar contra `db_test` o parar `api`.

### Deuda asignada por el Sprint 4A: qué entra y qué queda con condición

- **Entra en 4B (tiene slice natural):** rol de base separado del worker y del api con su `.env`
  (S4A-D49, S4A-D85 L-5, S3-D49, I-2) → W0-2. T8 de US-109 (cuadre del tablero con los datos de
  demostración) → B1 (validación V7). Revisión de los riesgos aceptados S4A-D60 (precio vigente
  al vender) y S4A-D61 (la lectura de la auditoría no se audita) → W0-1 T-DOC, decisión anotada.
  Pendientes de Sprint 3 W0-2 MEDIUM-1/-2 y N-6/N-7 → W0-2 (o reasignación explícita).
- **Entra en 4B solo si el plan lo decide (hoy contradice "ninguna migración"):**
  `0014_audit_log_triggers_always` y el texto de `audit.forbid_mutation()` (S4A-D98, V6).
  Evidencia: `audit_log_forbid_mutation` y `audit_log_forbid_truncate` con `tgenabled = 'O'` en
  `apex-db-1`; `verifications_*` en `'A'`. Recomendación: W0-2 (es endurecimiento de la base y el
  rol dueño lo aplica), con `CREATE OR REPLACE FUNCTION audit.forbid_mutation()` que use
  `TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME` en el mensaje, `downgrade` que vuelva a `ENABLE
  TRIGGER` y al texto original, P-MIG (volcado previo) y RUNBOOK §6. Los triggers `crypto_*` de
  `0003` también están en `'O'`: queda anotado como residual del mismo tipo, sin dueño nuevo.
- **Deuda explícita con condición (no entra salvo que la condición se cumpla):** índices
  `(record_id)`, `(action, seq DESC)` y `(table_name, action, seq DESC)` de `audit.audit_log`
  (S4A-D106 c, S4A-D115, S4A-D119 b): `audit.audit_log` tiene 5.612 filas; se crean en una
  `0015_audit_log_indexes` solo si `test_list_performance.py`/`test_recent.py` (`-m perf`)
  dejan de cumplir sus topes o el conteo real supera el umbral que el plan fije (por ejemplo
  500.000 filas). R-3 (pausa del GC en el api real, S4A-D127): se mide en la validación del sprint
  (V5) con `gc.callbacks` en el proceso del api bajo `POST /audit/verify` síncrono; `gc.freeze()`
  tras el arranque solo si el peor bloque pasa de 100 ms. Ambas se anotan en `SPRINT-04B.md` y
  `DECISIONES.md` con esa condición.
- **Front sin slice en 4B ("ninguna historia trae pantallas"):** la regla de lint de
  `sessionStorage` (lista blanca con `web/src/pages/RouteError.tsx:41-43`; `eslint.config.js:29`
  ya usa `no-restricted-syntax` y admite una entrada `MemberExpression[object.name=
  'sessionStorage']` con `files` que excluya ese archivo) cabe como tarea de higiene de `web/app`
  en B4 sin tocar pantallas; la barra `Tabs` a 1440 px y el contraste de "automático (aviso)"
  (`S4A-F2`) **sí** tocan la ficha: o se abre un mini-slice `web/members` en 4B con su prueba
  visual, o se reasignan con dueño (Sprint 5, que sí tiene front) y se anota. Decidirlo en W0-1.

### Archivos que el sprint no debe tocar

`core/audit.py` (solo se llama `record`), `core/audit_verify.py`, `core/db.py`, `core/context.py`,
`core/events.py`, `core/locks.py`, `core/pagination.py`, `core/errors.py`, `core/security.py`
(`PUBLIC_ROUTES` sigue en 8: `/health` ya es pública), `core/ratelimit.py`, migraciones `0001` a
`0013`, `modules/*/router.py` y `schemas.py`, `modules/{memberships,payments,plans,settings,
dashboard,audit}/service.py` (solo se consumen; `members/service.py` solo si gana el puerto de la
importación), `infra/nginx/*`, `infra/compose.e2e.yml`, `web/src/features/**` y `web/src/shared/**`
(salvo el mini-slice de la ficha si se decide), `web/src/core/api/types.ts` solo por regeneración.

## 3. Capa de datos

### Lo que existe (aplicado en `apex-db-1`; `db_test` se migra desde cero en cada sesión)

- `exec api alembic current` = `0013_audit_verifications (head)`. Cadena lineal `0001 → … → 0013`
  (`0005b` entre `0005` y `0006`); una sola cabeza.
- Triggers: `audit_log_forbid_mutation` y `audit_log_forbid_truncate` en `'O'` (S4A-D98);
  `verifications_forbid_mutation` y `verifications_forbid_truncate` en `'A'`; los seis de
  `crypto.*` (`0003`) en `'O'`. La función `audit.forbid_mutation()` dice "audit.audit_log es
  append-only" para las dos tablas (`0002:79-82`).
- `crypto.crypto_keys`: ocho llaves, todas `version = 1` y `active` (cinco `encrypt`, tres `index`
  de `member.document`, `member.email`, `member.phone`); `crypto.crypto_ops` 7.961 filas;
  `crypto.crypto_jobs` 0 filas. El CHECK `verb` admite `rotate` y `export`.
- Datos: `members.members` 265 filas (67 sin `deleted_at`), membresías `active` 79, `cancelled`
  56, `expired` 1, `frozen` 25, `pending_payment` 2; `payments.payments` 219; `audit.audit_log`
  5.612 filas (`max(seq)` 5.612); `plans.plans` 79 vivos; `worker.job_runs` con `expirations ok`
  de hoy; `audit.verifications` con verificaciones del 4A.
- Roles: un solo rol `apex`, superusuario, dueño de los nueve esquemas (`audit`, `crypto`, `auth`,
  `settings`, `members`, `plans`, `memberships`, `payments`, `worker`). **No existe el rol separado
  del api ni del worker.**

### Lo que agrega el sprint

- Según `SPRINT-04B.md`: ninguna migración. Según los dueños del 4A: `0014_audit_log_triggers_
  always` (condición 1). Si entra: `revision = "0014_audit_log_triggers_always"`, `down_revision =
  "0013_audit_verifications"`; `upgrade`: `ALTER TABLE audit.audit_log ENABLE ALWAYS TRIGGER
  audit_log_forbid_mutation` y `..._truncate`, `CREATE OR REPLACE FUNCTION audit.forbid_mutation()`
  con el nombre de la tabla en el mensaje; `downgrade`: `ENABLE TRIGGER` simple y la función con el
  texto de `0002`. Sin filas tocadas; sin `__audited__`; `migrations/env.py` no cambia (no hay
  modelo nuevo). Debe correrla el rol dueño (W0-2).
- Ninguna migración de datos. El seed de demostración, la importación, el respaldo de la KEK y la
  rotación son comandos del CLI (regla de datos 8), idempotentes y auditados.
- `0015_audit_log_indexes`: solo bajo la condición de volumen (sección 2).

### Riesgos de orden y de la suite

- Si `0014` entra, va en W0-2 antes de B1: el seed y la importación corren con los triggers ya
  en `'A'` y la cadena no cambia de forma.
- `tests/conftest.py:310-312`, `dos_sesiones` y `limpiar_tras_dos_sesiones`: `ENABLE ALWAYS
  TRIGGER` por nombre (nunca `ENABLE TRIGGER USER`), como `LIMPIAR_PAYMENTS` y
  `LIMPIAR_VERIFICATIONS`; `test_triggers_siempre_activos.py` gana la pareja de `audit_log`;
  `tests/factories/audit_chain.py:44-47` ya está bien.
- `pg_dump -Fc` de `apex-db-1` antes de `0014` (P-MIG; `*.dump` ignorado) y antes de la primera
  `rotate-key` real (S4B-B3, riesgo 1 del plan). `restore.sh` se ensaya en una base **limpia**
  (`createdb` en `apex-db_test-1`, como `apex_sim` en 4A), nunca sobre `apex-db-1`.
- El `api` de desarrollo monta `migrations/` por bind y migra al reiniciar (`compose.dev.yml:11-17`):
  misma mitigación del 4A (probar contra `db_test` o parar `api` mientras se escribe `0014`).
- Rollback: `downgrade 0014` deja los triggers en `'O'` sin tocar filas; RUNBOOK §6 gana su
  entrada. `tests/core/test_health_migrations.py` deja `db_test` en `head` al terminar.
- Con el rol separado, `tests/` sigue usando el superusuario de `db_test`; el rol del api solo se
  prueba por el smoke y por el E2E de CI (stack nuevo con el `initdb` script).

## 4. Servicios Docker y estrategia de rebuild

- Estado: `apex-db-1` healthy (`127.0.0.1:5442`), `apex-db_test-1` healthy (`127.0.0.1:5443`, 15
  horas arriba), `apex-api-1` healthy (`127.0.0.1:8181`, bind de `src` y `migrations`, `--reload`),
  `apex-worker-1` healthy, `apex-web-1` healthy (`0.0.0.0:8180`). Imágenes `apex-api:local`
  `83a82fc3caff` (2026-10-29 06:20:58 -05) y `apex-web:local` `6745c50bf90a` (06:21:19 -05): el
  último commit que toca `api/` es `89998b0` (06:15:36 -05) y `280addd` (06:29) solo cambia
  documentos: **las imágenes corresponden al código de HEAD** (lo confirma V12 del cuaderno).
  `apex-api:ci` del 2026-10-21 sigue sin uso. `postgres:16-alpine` (`4e6e670bb069`, sin digest)
  y `prodrigestivill/postgres-backup-local` pertenecen a otro proyecto/pruebas previas: no se usan.
- Cómo corre cada servicio: `api` con bind de `src/` y `migrations/` (cambios sin rebuild);
  `worker` y `tools` **con bind de `src/` y `migrations/` en solo lectura en desarrollo**
  (`compose.dev.yml:21-33`, S4A-D9): los comandos nuevos del CLI (`seed --demo`,
  `import-members`, `export-kek`, `rotate-key`) y el job `backup_check` corren desde el árbol con
  `run --rm tools ...`/`run --rm worker ...` sin reconstruir; el `worker` residente exige
  `restart worker` tras tocar `app/worker/` (RUNBOOK §7). La imagen de producción sí cambia dos
  veces: W0-1 (`age`) y al cerrar (release). `web` no cambia en este sprint (sin front) salvo el
  mini-slice de la ficha si se decide.
- Imagen nueva `apex-backup:local` (W0-1): se construye con buildx (quirk) y se levanta con `up -d
  --no-build backup`. La corrida manual del gate de Wave 0 es `run --rm backup run.sh` sobre
  `apex-db-1` (produce `apex-*.sql.age` y `latest.json` en el volumen `backups`; sin
  `BACKUP_RCLONE_REMOTE`, `upload: "skipped"`); el volumen se inspecciona con `run --rm backup ls
  /data/backups` y nunca se borra.
- Quirk del equipo (RUNBOOK §7): `docker compose build` y `up --build` fallan con Compose 5.6.1 +
  buildx 0.38.1 (`build.network: host`). Se construye con `docker buildx build --load --network
  host --allow network.host -t apex-api:local -f api/Dockerfile api` (y lo mismo para
  `apex-backup:local` con `-f infra/backup/Dockerfile infra/backup`) y se levanta con `up -d
  --no-build`. **No se reconstruyó nada en esta fase.** La demo del sprint dice `docker compose -f
  infra/compose.yml up -d --build`: en este equipo es `buildx` + `up -d --no-build`; en el servidor
  Linux (sin `compose.dev.yml`) `--build` funciona. `deploy.sh` debe contemplar las dos formas o
  solo la del servidor con una nota.
- Red y volúmenes: subred `172.30.0.0/24`, `web` en `.10` (`TRUSTED_PROXIES`); el servicio
  `backup` no publica puertos y se conecta a `db` por la red interna con `PGPASSWORD` de `.env`
  (`POSTGRES_PASSWORD`). Volúmenes `pgdata`, `uploads`, `keys`, `backups` (declarado desde US-005).
  `.gitignore` ya ignora `backups/` y `*.dump`.
- Nginx no cambia (`/api/` ya pasa `/api/v1/health`); `web` pasa a depender de `api` healthy.
  Imágenes base por digest del 2026-10-22 (S3-D62): se renuevan o no al abrir el sprint (RUNBOOK
  §7); la de `postgres:16-alpine` se fija nueva en W0-1 con `docker buildx imagetools inspect`.

## 5. Contratos API y front

### Estado de `docs/openapi.json` en HEAD

63 operaciones (53 del Sprint 3 más las 10 del 4A). `HealthOut` (`:962-994`) publica `db`
(`ok|down|unknown`), `status` (`ok|degraded`), `version` y `additionalProperties: true`.
`web/src/core/api/types.ts:1205` coincide. Ningún archivo de `web/src` llama `/health`.

### Lo que cambia

- `GET /health` y `GET /api/v1/health`: campos nuevos `backup` (informativo, siete valores,
  `unknown` sin corrida) y `migrations` (`head|behind`, crítico: `behind` → 503 `degraded`). Se
  declaran explícitos en `HealthOut` (no por `extra`), se regenera `docs/openapi.json` en B2 y B4
  (`export-openapi`) y `types.ts` (`npm run gen:api`); la CI falla en "openapi al día" y "tipos del
  api al día" si se olvida. Sin rol (ya en `PUBLIC_ROUTES`), sin 422, sin 429.
- Ningún endpoint nuevo, ninguna cubeta nueva, ningún código de error HTTP nuevo
  (`rotation_not_supported` es del endpoint de US-145, v0.2+; en v0.1 es una salida del CLI).
- Front: sin pantallas. `features.ts` (`ENABLED_FEATURES`), `routeTable.ts`, `nav` y
  `permissions.ts` no cambian. Solo la regla de lint de `sessionStorage` (si se decide) y, si se
  abre el mini-slice de la ficha, `web/src/shared/ui/Tabs.tsx` y el CSS del historial.
- CLI (contrato de operación): `seed --demo [--force-demo-on-non-empty] [--as]`, `import-members
  <xlsx> [--as] [--dry-run] [--report]`, `export-kek --out [--passphrase-file] [--as]`,
  `verify-kek-backup <archivo> [--passphrase-file] [--as]`, `rotate-key <data_class> --reason
  [--index] [--as] [--batch-size]`; códigos 0/1/2 como los comandos existentes (`--as` inválido o
  base caída → 2; `production_guard_error` en producción). `worker --run-once backup_check`.

### Contradicciones entre desgloses y código que el plan cierra en T-DOC (W0-1)

- `register_health_check(..., informative=True)` (US-115 T4, US-118) → `critical=False`/`True`.
- `details` con cadenas y fechas (US-115 T3) → solo enteros de `DETAIL_KEYS`; estado en `result`.
- `JobOutcome` como retorno del job (US-115 T3) → `JobResult`.
- `sell(..., max_retroactive_days=None)` (US-111) → `sell(..., enforce_retroactive_limit=False,
  role="admin")`, solo nombrado desde `cli.py` o con excepción anotada.
- `members.service.create(data, by=actor_id)` (US-112 T4) → `create(session, data)` con
  `unit_of_work(actor)`.
- `DuplicateDocument` (US-112 T7) → `MemberDocumentDuplicated`.
- `recompute_statuses(today)` dentro de la transacción (US-111 T2) → `recompute_statuses
  (session_factory, today=)` tras el commit; una transacción por socio (plan B1).
- `resolve_cli_actor` (US-030 T9) → `resolve_actor`; admin obligatorio o cuenta activa: decidir.
- `0014_crypto_ops_export_verb` (US-116) → no hace falta (`0003` ya trae `export`).
- `@pytest.mark.slow` / "job `slow`" (US-112 T12, riesgo 5 del plan) → `perf`.
- `shellcheck` (US-114 T8, US-116, US-117 T9) → `bash -n` (ShellCheck es GPL, `CLAUDE.md`).
- `bats` (US-114 T5-T7, US-116 T9, US-117 T5) → harness Bash propio o `bats-core` solo en CI.
- `docker compose pull` e `IMAGE_TAG` (US-117 T3, T7) → imágenes locales sin registro: construir.
- `docker compose run --rm api uv run python -m app.cli seed --demo` (US-111 T11) y `docker
  compose run --rm worker uv run python -m app.worker.main` (US-115) → `tools seed --demo` y
  `worker python -m app.worker.main` (la imagen no trae `uv`, CRITICA B-3).
- `ADR-002-bus-de-criptografia.md` (US-119) → `docs/adr/ADR-002-criptografia.md` (existe, se
  completa).
- `table_name="members_import"` (US-112) → un nombre `esquema.tabla` filtrable, por ejemplo
  `members.import_runs`, sin entrar en `AUDITABLE_TABLES` (no es un modelo) o con decisión de que
  no se filtra.
- "`core.crypto.bus.digest_file` desde el job" (US-115) → lista blanca de
  `test_crypto_bus_importers.py` o import de `archive` por decisión.
- `CLAUDE.md` bus regla 1 "desde v0.2, `digest_file`…" → v0.1 (este sprint).

## 6. Línea base en HEAD `280addd`

- `git log --oneline -3`: `280addd docs(sprint-04a): v12: estado al cierre, dueños asignados, stack
  final y limpieza`, `39a4b31 chore(sprint-04a): v9: lista blanca de gitleaks...`, `89998b0
  chore(checkpoint): S4A-V11 log del worker con tiempos...`. `git status` limpio; `git worktree
  list` solo el principal.
- Suites (no corridas aquí; cita de `docs/scratch/sprint-04a.md`, V9 sobre `89998b0` y V12 sobre
  `39a4b31`, mismo código que HEAD): api `pytest -m "not perf"` **4.995 ok, 3 saltadas (NTFS), 23
  `perf` deseleccionadas**, 14 min 40 s, cobertura global de `app` **97 %** sin `omit`; front
  **3.125 pruebas en 172 archivos, 97,87 % de sentencias y 98,82 % de líneas**, lint, `tsc`,
  build y licencias en verde; scripts de infraestructura 4 de 4 en verde.
- Corrido en esta fase (HEAD, árbol limpio):
  - `cd api && uv run ruff check .` → `All checks passed!` (código 0).
  - `cd api && uv run ruff format --check .` → `510 files already formatted` (código 0).
  - `cd api && uv run mypy src` → `Success: no issues found in 119 source files` (código 0).
  - `cd web && npx tsc --noEmit` → sin salida, código 0.
- Stack (`docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml ps`): los
  cinco contenedores healthy; `exec api alembic current` = `0013_audit_verifications (head)`.
- `.env` local (solo nombres): `WEB_PORT=8180`, `API_PORT=8181`, `DB_PORT=5442`,
  `DB_TEST_PORT=5443`, `TEST_DATABASE_URL=postgresql+asyncpg://apex:apex-test@127.0.0.1:5443/
  apex_test`. Los puertos 80, 8000, 5432 y 5433 son de otro proyecto. `.env` y `.env.seed` no
  están versionados. `gh` no está instalado (el push, el PR y la etiqueta son humanos).

## 7. Bugs, desajustes de configuración y contradicciones documentales

1. `SPRINT-04B.md` ("Migraciones que aplica: ninguna"; DoD "ciclo `0001` a `0013`") contradice los
   dueños del cierre del 4A (`0014_audit_log_triggers_always`, texto de `forbid_mutation`,
   índices "si el volumen lo exige"). Se decide en W0-1 (condición 1).
2. `CLAUDE.md` describe `core/crypto/archive.py` como "desde v0.2"; `SPRINT-04B.md` lo construye
   en v0.1. `CLAUDE.md` no lista `app/seed/`, `app/imports/`, `core/crypto/{kek_backup,service,
   discovery}.py`, `infra/backup/`, `infra/deploy.sh`, `docs/operacion/` ni `docs/plantillas/`.
3. `scripts/workflow/slice-gate.sh` no mapea `seed` ni `imports`; `SPRINT-04B.md` da como gate de
   B1 `slice-gate.sh cli` y `slice-gate.sh members`, que no lintan ni tipan `app/seed/` ni
   `app/imports/` (sí lo hace `run-gates.sh`, que es global).
4. `cli.py` en 760 líneas, el tope de S4A-D72/S4A-D95: cualquier comando nuevo lo supera.
5. `worker/runner.py:155` solo escribe `ok`/`error`; `core/jobs.RESULTS` admite los estados del
   backup desde `0012` pero ningún camino los escribe.
6. `core/health.py:25` tipa las comprobaciones con tres valores; el plan agrega nueve.
7. `core/health.py` y `main.py` no pueden importar `core.jobs` (dos pruebas); US-115 T4 lo pide.
8. `test_compose_config.sh:171` exige el worker sin volúmenes; US-115 T11 monta `backups`.
9. `.env.example`/`Settings`: toda variable de operación nueva debe entrar en `NON_API_ENV_VARS` o
   el api no arranca; `RCLONE_CONFIG_*` no tiene nombres fijos.
10. `api/Dockerfile` sin `age`; `test_images_pinned.sh` no cubre `infra/backup/Dockerfile`; CI sin
    build de la imagen de backup, sin `bash -n` de `infra/`, sin `shellcheck` (GPL) ni `bats`.
11. `infra/compose.yml`: `web` depende de `api` `service_started` (US-118 pide healthy); `api`
    `start_period` 30 s (US-118 pide 60); no hay `backup`; no hay registro ni `IMAGE_TAG` para
    `docker compose pull` de `deploy.sh`.
12. `test_guarded_calls.py:116` y `sell` sin `max_retroactive_days`: el seed no puede vivir fuera
    de `cli.py` tal como lo describe US-111 sin tocar la prueba.
13. `test_crypto_bus_importers.py` exacto: `imports/` y `worker/jobs/backup_check.py` no pueden
    importar el bus sin lista blanca.
14. `apex-db-1` tiene un solo rol superusuario dueño de todo; `main.py` migra al arrancar con
    `DATABASE_URL`: el rol separado exige una URL de migraciones o un api dueño no superusuario.
15. `docs/adr/ADR-002-criptografia.md` existe con otro nombre y 4 secciones; `docs/adr/README.md`
    tiene 3 líneas; `docs/operacion/` y `docs/plantillas/` no existen.
16. `MemberCreate` no tiene `notes`: la columna `notas` de Q17 no tiene destino.
17. US-030 sigue `NEEDS_REFINEMENT` por la pregunta de los blobs de `audit_log`; US-115 sigue
    `ARCHITECTURAL_GAP_DETECTED` hasta que el gate acepte G-07 (ya aceptada en `DECISIONES.md`):
    ambos estados se actualizan en T-DOC.
18. `attachment.sensitive` no existe en `registry.py`: `rotate-key attachment.sensitive` da
    `unknown_data_class`, no `rotation_not_supported` (G-09).
19. Deuda de front con dueño "Sprint 4B" (`sessionStorage`, `Tabs` 1440, contraste) y el sprint
    "no tiene Waves 5a/5b".
20. `tools` no monta el host: la demo de importación ya pone `-v .../docs/plantillas:/plantillas:ro`
    (solo lectura: el reporte CSV no cabe ahí) y `export-kek --out` necesita su propio `-v`.

## 8. Riesgos del plan ampliados con lo visto en el código

1. [HIGH] Operaciones irreversibles con llaves (riesgo 1 del plan): las ocho llaves de `apex-db-1`
   están en versión 1; una rotación mal cerrada deja `decrypt_only` (recuperable) y solo el
   recuento a cero bajo `FOR UPDATE` permite `retired` (el trigger de `0003` impide volver atrás).
   Mitigación: US-116 antes que US-030, `pg_dump` + `export-kek` antes de la primera rotación
   real, prueba de interrupción y reanudación con `dos_sesiones`, y ninguna rotación real sin
   confirmación humana (el plan ya lo dice).
2. [HIGH] Rol de base separado frente a las migraciones al arrancar (sección 2, W0-2): sin
   decisión, o el api no migra o el rol no separa nada. Mitigación: condición 3.
3. [HIGH] Variables de operación nuevas y `extra="forbid"`: un `.env` con `BACKUP_*` sin
   `NON_API_ENV_VARS` tumba el api, el worker y `tools` en el próximo `up -d`. Mitigación:
   condición 2 (nombres fijos, `test_env_example.py`, smoke).
4. [MEDIUM] Contratos del job y de la salud (`JobResult`, `DETAIL_KEYS`, `CheckResult`, importadores
   de `core.jobs`): sin decidirlos en el Rojo de B2, el slice reescribe el runner a mitad del Verde.
   Mitigación: condiciones 5 y 6.
5. [MEDIUM] `cli.py` en el tope y cuatro listas literales de módulos prohibidos: cada comando
   nuevo rompe una prueba distinta si no se parte primero. Mitigación: condición 4 (partir en el
   Rojo de B1) y 8 (`pyrage` en los tres sitios más `_imports`).
6. [MEDIUM] Infraestructura nueva sin herramientas en el host (`age`, `bats`, `shellcheck`) y con
   el quirk de buildx: la Wave 0 se verifica con contenedores (`run --rm backup`) y con la CI;
   `bash -n` sustituye a ShellCheck. Mitigación: condición 2.
7. [MEDIUM] `pyrage` y `openpyxl` no verificados contra `pip-licenses` ni contra las ruedas de
   `cp312`; la alternativa `apx-kek1` existe pero cambia el formato que el operador abre con `age`.
   Mitigación: `uv add` + `check-licenses-api.sh` en W0-1, antes de B1/B3.
8. [MEDIUM] Importación en `tools` sin escritura al host: el reporte CSV y el `latest.json` de la
   demo necesitan binds explícitos; una ruta mal puesta deja datos personales en el contenedor.
   Mitigación: `--report`, documento de operación con el `-v` exacto y borrado al terminar.
9. [MEDIUM] `0014` y la limpieza de `db_test`: `ENABLE TRIGGER USER` en `conftest.py:312` degrada
   los triggers a `'O'` en cada sesión y `test_triggers_siempre_activos.py` no lo vería hasta
   sumar la pareja. Mitigación: condición 7.
10. [MEDIUM] P3 sin destino (riesgo 3 del plan): sin `BACKUP_RCLONE_REMOTE` el backup es local y
    vive en el mismo disco que `pgdata`; el README de operación lo dice y `latest.json` lo marca
    `skipped`. Aceptado por el plan.
11. [LOW] El seed de demostración sobre `apex-db-1` (265 socios) exige `--force-demo-on-non-empty`
    y suma 30 socios `999…` a los datos de prueba del 4A; el cuadre de Inicio se mide con todo.
12. [LOW] `test_health_migrations.py` con `downgrade -1` sobre `db_test` puede dejar la sesión de
    pruebas fuera de `head` si falla a mitad: `finally` que vuelva a `upgrade head`.
13. [LOW] `e2e-stack` de CI arranca el servicio `backup` (`up -d --build`): supercronic en espera
    hasta las 02:00 de Bogotá; no interfiere con las specs; `down -v` lo limpia.
14. [LOW] Triggers `crypto_*` de `0003` también en `'O'`: mismo residual que S4A-D98, sin dueño.

## 9. Condiciones para VERDE

Se incorporan al plan de la Fase 1; el plan-critic las verifica.

1. **W0-1 (T-DOC, antes de tocar código):** `SPRINT-04B.md` y `DECISIONES.md` cierran la deuda del
   4A con un destino cada una: `0014_audit_log_triggers_always` + texto de `forbid_mutation` →
   **S4B-W0-2** (sección "Migraciones que aplica" pasa a `0014`, DoD "ciclo `0001` a `0014`",
   RUNBOOK §6); índices de `audit.audit_log` → deuda con condición de volumen escrita (filas o
   topes `perf`); R-3 → medición en V5 con `gc.callbacks`; `sessionStorage` → regla de lint en B4
   (`web/app`, sin pantallas); `Tabs` 1440 y contraste → mini-slice `web/members` en 4B o dueño
   Sprint 5 anotado; S4A-D60 y S4A-D61 → decisión de revisión anotada; pendientes de Sprint 3
   (W0-2 MEDIUM-1/-2, N-6/N-7) → tareas concretas de W0-2 o reasignación. Los desgloses corrigen
   los nombres de la sección 5 (`critical=`, `details` enteros, `enforce_retroactive_limit`,
   `create(session, data)`, `MemberDocumentDuplicated`, `recompute_statuses(session_factory)`,
   `resolve_actor`, sin `0014_crypto_ops_export_verb`, `perf`, `bash -n`, sin `uv run`, sin
   `compose pull`, `ADR-002-criptografia.md`, `members.import_runs`), US-030 pasa a READY con la
   alternativa por defecto de los blobs de `audit_log`, US-115 pasa a READY con G-07 aceptada, y
   `CLAUDE.md` gana la estructura nueva y corrige "desde v0.2" en la regla 1 del bus.
2. **W0-1 (infra):** `infra/backup/Dockerfile` con `FROM postgres:16-alpine@sha256:<digest>` y el
   comentario con fecha y comando (S3-D62), `age`, `rclone` y `supercronic` por `apk` con versión
   fijada (1.2.1-r15, 1.72.1-r4, 0.2.39-r6), usuario no root; `scripts/ci/test_images_pinned.sh`
   suma ese Dockerfile; `api/Dockerfile` instala `age` 1.2.1 por `apt` y `test_api_image.sh`
   comprueba `age --version`; `.env.example` gana `BACKUP_AGE_RECIPIENT`, `BACKUP_RCLONE_REMOTE`,
   `BACKUP_KEEP_DAYS=14`, `BACKUP_CRON`, los `RCLONE_CONFIG_APEX_*` con nombre fijo y
   `DEPLOY_HEALTH_TIMEOUT`, y **todos** entran en `NON_API_ENV_VARS` (`core/config.py:45`) con
   `test_env_example.py` en verde; `infra/compose.yml` gana `backup` (`backups` rw, `uploads:ro`,
   `depends_on db healthy`, sin `ports`, `restart`); `test_compose_config.sh` lo asegura y suma
   `backups` a los volúmenes en uso; `compose-smoke.sh` corre `run --rm backup run.sh` y valida
   `latest.json`; `ci.yml` construye `apex-backup:ci`, le pasa `check-image-secrets.sh`, corre
   `bash -n infra/backup/*.sh infra/*.sh` y las pruebas de `lib.sh` (harness Bash como
   `scripts/workflow/tests/run.sh`, o `bats-core` instalado solo en CI); `NOTICE` gana el bloque
   fijo de `age`, `rclone`, `supercronic` e imagen `postgres`; `uv add openpyxl` y `uv add pyrage`
   (o la decisión `apx-kek1`) pasan `check-licenses-api.sh` y `notice.sh` en este slice, antes de
   B1 y B3. `apex-api:local` y `apex-backup:local` se reconstruyen con buildx y se levantan con
   `up -d --no-build`.
3. **W0-2 (rol de base y arranque):** decisión escrita entre (a) `MIGRATIONS_DATABASE_URL` (rol
   dueño) en `Settings` + `.env.example`, usada por `main.run_migrations`, `migrations/env.py` y
   `cli_runtime`, con `DATABASE_URL` del rol del api sin `SUPERUSER` ni propiedad de los esquemas,
   y (b) api dueño no superusuario; en ambos casos el worker con su propio rol/credencial y la
   decisión sobre su `.env` (S4A-D85 L-5); creación del rol por `infra/db/init/*.sql` montado en
   `db` (`/docker-entrypoint-initdb.d`, stacks nuevos y `e2e-stack`) y procedimiento manual en
   RUNBOOK para `apex-db-1` y el servidor; `test_compose_config.sh` con las aserciones de
   `env_file` por servicio; `tests/` siguen con el superusuario de `db_test`; prueba de que el rol
   del api no puede `ALTER TABLE ... DISABLE TRIGGER` ni `SET session_replication_role` (smoke con
   `psql` como ese rol). `web.depends_on.api: service_healthy`, `api.healthcheck.start_period:
   60s`, `worker` con `backups:/data/backups:ro` y `test_compose_config.sh:171` reescrita ("solo
   `backups` en ro; nunca `keys` ni `uploads`"). `deploy.sh` sin `pull`: construye (buildx o
   `compose build` según el host), guarda ids de imagen en `deploy-<fecha>.state.json`, espera
   `/api/v1/health` con `db == "ok"` y `migrations == "head"`, escribe `rollback-<fecha>.txt` con
   `docker tag <id anterior> apex-api:local` y nunca `down -v`, `volume rm`, `set -x`, `push` ni
   `--force`; `restore.sh` con `run --rm -v apex_uploads:/data/uploads backup restore.sh` (o
   servicio `restore` con perfil) y la guarda de base vacía. `0014_audit_log_triggers_always`
   (condición 7) se aplica aquí con el rol dueño.
4. **B1 (Rojo):** `cli.py` se parte antes de agregar comandos (`cli_ops.py` o un módulo por
   comando registrado desde `cli.py`; `cli.py` queda como fachada por debajo de 760 y
   `test_worker_boundaries.CLI`, `ARRANQUE`, `test_guarded_calls` y `test_gates_registered`
   siguen apuntando a `cli.py`); `slice-gate.sh` y su README ganan los mapeos `seed` →
   `src/app/seed` y `imports` → `src/app/imports` (con prueba en `scripts/workflow/tests/`), y el
   gate de B1 es `slice-gate.sh cli`, `slice-gate.sh seed` y `slice-gate.sh imports` con sus
   archivos; `test_worker_boundaries._archivos_de_aplicacion()` barre `seed/**` e `imports/**`
   (US-111 T10, US-112 T13); `enforce_retroactive_limit` se nombra solo en `cli.py` (el seed recibe
   la venta configurada) o `test_guarded_calls.py:116` admite `seed/demo.py` con decisión anotada;
   la importación no importa el bus (repetidos del archivo por `members.service.id_by_document` o
   un puerto nuevo `document_index`/`import_batch` en la fachada de `members`; hash del archivo
   por ese mismo puerto) o `test_crypto_bus_importers.py` gana `imports/members_xlsx.py` con
   nombres exactos; `seed --demo` es una opción del `seed` existente que conserva `--no-force-change`
   y `--as`; `--as` resuelve con `resolve_actor` (cuenta activa) o con `active_admin_id_by_email`
   (admin) por decisión única para los cinco comandos; una transacción por socio con
   `recompute_statuses(db.get_sessionmaker(), today=)` tras el último commit; `sell(...,
   role="admin")` y `payments.register(..., role="admin")` para fechas pasadas; `notas` de Q17 se
   descarta con aviso en el reporte; la entrada resumen usa un `table_name` `esquema.tabla`;
   `--report <ruta>` para el CSV (el bind de la demo es `:ro`); `test_import_members_perf.py` con
   `perf` y 5.000 filas; `run-gates.sh` al cerrar B1 (cobertura de `cli.py`, `seed/`, `imports/`).
5. **B2 (Rojo, worker):** `JobResult` gana `result: str | None = None` y `_ejecutar` lo escribe
   cuando está en `RESULTS` (si no, `ok`/`error` como hoy); `DETAIL_KEYS` gana solo claves
   enteras del backup (`verified`, `age_hours`, `size_mb` o las que fije el plan) y
   `tests/worker/test_runner.py`/`test_jobs_core.py` se actualizan; `evaluate(...)` pura; el log
   `error` lleva el estado y el nombre del archivo, `details` no; `JOBS` suma `backup_check` tras
   `expirations` y `test_worker_boundaries.py:213` gana `jobs/backup_check.py`; `backup_check.py`
   toma el tiempo de `ctx.clock.now_utc()`; `Settings` gana `BACKUP_DIR` y
   `BACKUP_AGE_VERIFY_IDENTITY_PATH` (y `.env.example`).
6. **B2 (Rojo, bus y salud):** `core/crypto/archive.py` con `digest_file` (streaming, `hashlib`
   dentro del bus) y `verify_age_archive` (`subprocess` con lista de argumentos, sin `shell`,
   `stdout` a sumidero que cuenta, `stderr` descartado, `timeout` 600 s, `oplog.record("verify",
   data_class="backup.archive", key_id=None, key_version=None)`), reexportados por `bus.py`;
   `registry.py` gana `backup.archive`; `test_banned_imports.py` gana el caso "`subprocess` solo
   en `core/crypto/archive.py`"; `test_crypto_bus_importers.py` gana `worker/jobs/backup_check.py`
   con exactamente `{digest_file, verify_age_archive}` (patrón `ARRANQUE`). `core/health.py`
   amplía el tipo de resultado (unión de literales o `str` validado en `HealthOut`) y declara
   `backup` (informativo, `critical=False`, `unknown` por defecto) y `migrations` (crítico);
   quién lee `worker.job_runs` desde el api se decide entre (a) excepción única para
   `core/health.py` en `test_worker_boundaries.py:240` y `test_core_import_direction.py:114` con
   S4A-D73 enmendado, o (b) `core/backup_status.py` con SQL constante y parámetro ligado,
   registrado desde `main.py`; `tests/core/test_health.py` fija los estados reales;
   `docs/openapi.json` y `types.ts` se regeneran en el mismo slice.
7. **Migración `0014` (W0-2):** `ENABLE ALWAYS` de `audit_log_forbid_mutation` y
   `audit_log_forbid_truncate`, `CREATE OR REPLACE FUNCTION audit.forbid_mutation()` con
   `TG_TABLE_SCHEMA`/`TG_TABLE_NAME` en el mensaje, `downgrade` exacto; `tests/migrations/
   test_0014_*.py` y `test_triggers_siempre_activos.py` con la pareja en `'A'`;
   `tests/conftest.py:310-312`, el `finally` de `dos_sesiones` y `limpiar_tras_dos_sesiones`
   encienden por nombre con `ENABLE ALWAYS TRIGGER`; `pg_dump -Fc` de `apex-db-1` antes de
   aplicarla (`docs/scratch/sprint-04b-antes-0014.dump`, se borra al cerrar); `alembic heads` = 1;
   RUNBOOK §6 con su entrada; `0015_audit_log_indexes` solo si se cumple la condición de volumen
   escrita en la condición 1.
8. **B3 (Rojo):** `pyrage` en `pyproject.toml:53-59`, `_imports.BANNED_MODULES`,
   `test_ruff_banned_api.BANNED` (y el nombre de la prueba "seis" → "siete"); `core/crypto/
   kek_backup.py`, `service.py` y `discovery.py` sin importar `core/audit` ni `app.modules`;
   `cli.py` sin `bus`/`types`; auditoría (`update`/`export`/`verify`) desde `cli.py` con
   `core.audit.record`; el SQL de la rotación en Core sobre `Table` (sin `text()` dinámico);
   candado `pg_try_advisory_lock(hashtext(:clave))` constante con parámetro ligado en conexión
   dedicada (sin `isolation_level`); `discovery` por `registry.columns` y `Base.metadata`, sin
   nombrar `Membership`; `rotate-key attachment.sensitive` sale con 2 y mensaje fijo (G-09);
   `export-kek` rechaza rutas bajo `BACKUP_DIR` y exige `--passphrase-file` o prompt sin eco;
   `verify_kek_backup` construye el proveedor en memoria (archivo temporal 600 en `tmpfs` o
   `unwrap_with`); `tests/cli/test_cli_rotate_key.py` (no en la raíz de `tests/`); prueba de
   interrupción y reanudación y de "rotación en curso" con `dos_sesiones`; `pg_dump` +
   `export-kek` antes de la primera rotación real sobre `apex-db-1`; `run-gates.sh` al cerrar B3.
9. **B4:** `migrations` en `/health` con el `head` leído una vez tras migrar y la revisión de la
   base por llamada con el límite de 2 s; `tests/core/test_health_migrations.py` deja `db_test` en
   `head` en su `finally`; `main._startup` registra la revisión que falló sin la URL; ADR-001,
   ADR-003 y ADR-004 nuevos y `ADR-002-criptografia.md` completado a seis secciones con el nombre
   actual; `docs/adr/README.md` con índice y plantilla; `test_adr_docs.py` y
   `test_chain_hash_vector.py` (vector leído del ADR-004 con regex sobre un bloque marcado);
   `README.md` enlaza `docs/adr` y `docs/operacion`; regla de lint de `sessionStorage` en
   `web/eslint.config.js` con lista blanca `web/src/pages/RouteError.tsx` y su prueba en
   `web/tests/lint/`; `docs/openapi.json` y `types.ts` regenerados.
10. **Validación y release:** los cinco E2E críticos contra el stack de producción (`infra/
    compose.yml` solo, `--env-file .env`, `WEB_PORT=8180` en este equipo), ensayo completo en una
    base limpia (`createdb` en `apex-db_test-1`: backup, `backup_check`, `restore.sh`, arranque con
    la KEK respaldada y `reveal`), `rotate-key` interrumpida y reanudada, perf de 5.000 filas, R-3
    medido, checklist de criterios diferidos (US-004 a US-007, US-012, US-018, US-020 `backup` y
    `migrations`, US-066, US-109 T8), `run-gates.sh` final con cobertura ≥ 80 % incluidos
    `cli.py`, `seed/`, `imports/` y `worker/`, `security-reviewer` sobre los cinco puntos de la
    DoD, limpieza de datos de demostración si se sembraron en `apex-db-1` (o constancia de que
    quedan), y el paso humano: push, PR con CI en verde, merge y `git tag -a v0.1.0`.

## Riesgos residuales (no bloquean)

- `--reload` con polling reinicia el api a mitad de un E2E del proyecto `stack`; no editar `src/`
  durante la corrida.
- Las tres pruebas saltadas por NTFS se verifican en el job `api` de CI (Linux).
- `supercronic` en el contenedor `backup` corre a las 02:00 de Bogotá: en el stack de desarrollo
  produce un backup diario en el volumen `backups` (retención 14 días) mientras el stack esté
  arriba; es el comportamiento esperado y el espacio es acotado (`pg_dump` de 1,2 MB hoy).
- `apex-api:ci` del 2026-10-21 y `postgres:16-alpine` sin digest en el host son imágenes viejas sin
  uso; no interfieren.
- Los triggers `crypto_*` de `0003` siguen en `'O'`; el rol separado de W0-2 cierra el vector de
  `session_replication_role` para todas las tablas, y el `ENABLE ALWAYS` de `crypto` queda como
  residual anotado sin dueño nuevo.
- `GET /health` responde 503 mientras una migración futura esté a medias: Compose reinicia el api
  solo tras `retries` × `interval` (50 s) más el `start_period` de 60 s; una migración más larga
  que eso en el servidor exige subir `start_period` (riesgo documentado en US-118).
