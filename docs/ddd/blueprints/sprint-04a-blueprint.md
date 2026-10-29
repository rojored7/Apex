# Blueprint de implementación · Sprint 4A · Worker, auditoría verificable, tablero y planes restantes

> **Nota de cabecera (V1):** corregido por `sprint-04a-plan.md` y por las decisiones de ejecución S4A-D75 a S4A-D121 (`docs/ddd/DECISIONES.md`, "Sprint 4A"). Donde este documento choque con ellos, mandan ellos.
>
> **Corregido por `sprint-04a-plan.md`** (sección 1 y enmiendas E1 a E10; registro en `docs/ddd/DECISIONES.md`, "Sprint 4A", desde S4A-W0-1): D3, D4, D6, D9, D12, D13, D14, D16, D17, D19, D20, D21, D26, D27, D28 y S4A-D62 a S4A-D74. Donde este plano choque con el plan o con `DECISIONES.md`, mandan ellos.

> Fase 1 de `/flow-update`. Resuelve los 11 hallazgos y las 16 preguntas abiertas de `sprint-04a-exploracion.md` y las 13 "Condiciones para VERDE" de `docs/ddd/impacto/sprint-04a.md` (sección 9; se citan como **C1 a C13**). Donde este plano y un desglose chocan, manda este plano; las decisiones se copian a `docs/ddd/DECISIONES.md` (sección "Sprint 4A") en el primer checkpoint (S4A-W0-1), igual que hicieron los Sprints 2 y 3.

- Rama: `feat/sprint-04a-worker-auditoria-tablero`, desde `f5f2503` (= `main`, cierre del Sprint 3). Última migración aplicada: `0011_payments_immutability`. Este sprint aplica `0012_worker_job_runs` y `0013_audit_verifications` y **ninguna más** (S4A-D19, S4A-D38).
- Entradas: `CLAUDE.md`, `SPRINT-04A.md`, `CRITICA-2.md` (N-3), `sprint-04a-exploracion.md`, `docs/ddd/impacto/sprint-04a.md`, el blueprint y el plan del Sprint 3, `02_domain_model.md`, `03_context_map.md` (G-04), `05_service_design.md`, `DECISIONES.md` (G-03, G-04, G-05, G-06, G-08, N-15, N-21, N-22, N-30, N-31, Q10, refinamiento de US-110, S3-D41 a S3-D105, "Estado al cierre del Sprint 3", "Dueños asignados al cierre del Sprint 3", P2-1), `BRECHAS.md` (§10 y `:244`), `docs/design/` (`DESIGN.md`, `ROUTES.md`, `Auditoria`, `Inicio`, `Planes`, `Socio_Ficha`), `RUNBOOK.md` §7, `scripts/workflow/README.md` y `slice-gate.sh`, los desgloses de US-077, 080, 081, 082, 094, 102 a 106, 108 a 110 y 113, y el código real de `api/src/app`, `api/tests`, `infra`, `scripts` y `web/src` (cada firma citada se verificó en HEAD).
- Este archivo es solo un plano: no cambia código. Cada DECISIÓN lleva el motivo; las que contradicen un desglose lo dicen.

## 0. Cómo leerlo

1. Sección 1: decisiones **S4A-D1 a S4A-D42** (no reutilizan números del Sprint 3, que llegan a S3-D105). Leerlas antes de escribir un Rojo.
2. Sección 2: reglas transversales y estructura de archivos por módulo.
3. Sección 3: orden de ejecución y dependencias entre slices.
4. Sección 4: backend slice por slice (W0-1, W0-2 y S4A-B1 a S4A-B8).
5. Sección 5: front slice por slice (S4A-F1 a S4A-F4).
6. Sección 6: flujos de datos.
7. Sección 7: mapa de las pruebas que rompen fuera del gate, asignadas al Rojo exacto.
8. Sección 8: fábricas y fixtures.
9. Sección 9: mapa endpoint a front.
10. Sección 10: trazabilidad (hallazgos, preguntas y condiciones C1 a C13), riesgos, tabla final de slices y lista para el planner.

Convención de cada slice (la de los Sprints 2 y 3): Rojo (stubs que lanzan `NotImplementedError` y pruebas que fallan), Verde (implementación) y Gate (`bash scripts/workflow/slice-gate.sh <modulo> <archivos de Rojo>`, que añade `tests/architecture`). Todo slice backend que publica rutas o cambia esquemas regenera `docs/openapi.json` (`cd api && uv run python -m app.cli export-openapi ../docs/openapi.json`) y, en el mismo checkpoint, `cd web && npm run gen:api` (`types.contract.test.ts` falla si `types.ts` no coincide). Los parámetros de ruta se llaman `{seq}`, `{member_id}` y `{plan_id}`. El marcador de rendimiento es `perf`, nunca `slow` (`--strict-markers`).

## 1. DECISIONES

### Estado de membresías, worker y Compose

**S4A-D1 · US-094 frente a D5: la columna `status` es un espejo persistido del estado efectivo; las lecturas siguen derivadas (hallazgo 1, pregunta 2; C3).**
- Las lecturas no cambian: `rules.compute_status` y `queries.status_expr` siguen mandando en `list`, `get`, `status_for`, `summary`, `count_active_by_plan` y `classify_open` (D5, S3-D96). El job **no** cambia ningún resultado visible en pantalla.
- `recompute_statuses(session_factory, *, today, ...)` mantiene la columna alineada con el estado efectivo de `today` para las filas que el tiempo movió, y es la **fuente de los eventos de transición** `MembershipExpiring` y `MembershipExpired` que consumirá Notifications (Sprint 5). Sin el job la columna quedaría en `active` para siempre y no habría eventos.
- Invariantes: (1) el job solo toca filas con `status` guardado en `active`, `expiring` o `frozen`; `pending_payment`, `cancelled` y `expired` guardados nunca entran (criterio 6 de US-094 y D5); (2) tras el job, para toda fila candidata, `status` guardado `== compute_status(...)` de `today` (prueba de paridad en B2); (3) nadie lee la columna cruda salvo `lifecycle.py:264` (exige `pending_payment`) y `sell` (`open_memberships` aplica `effective(...)`), así que el desfase de un día entre medianoche y las 07:00 no tiene efecto visible (aceptado en US-094 "Riesgos").
- Sin índices nuevos: la consulta de candidatas usa `ix_memberships_status_end_date (status, end_date)` más `status_expr(...) <> status`.
- Eventos nuevos en `memberships/events.py` (`@dataclass(frozen=True, slots=True, kw_only=True)`, heredan `DomainEvent`, sin PII; pasan `test_events_without_pii.py`): `MembershipExpiring(membership_id, member_id, end_date, on_date)` y `MembershipExpired(membership_id, member_id, end_date, on_date)`, re-exportados desde `service.py`. Pura `rules.transition_event(old, new) -> Literal["expiring","expired"] | None`: a `expiring` desde `active` o `frozen` -> `"expiring"`; a `expired` desde cualquier estado -> `"expired"`; `active <-> frozen` y lo demás -> `None`. Un `active` guardado que ya venció hace tres días emite solo `MembershipExpired` (criterio 4).
- **Sin suscriptores, y NO se suscribe `_mark_summary_dirty` a los dos eventos nuevos** (matiza C3, que lo pedía): el resumen se calcula con `status_expr`, no con la columna, así que el job no lo cambia; marcarlo sucio invalidaría la caché sin motivo y el job corre en otro proceso (S3-D93). `SUSCRIPTORES_ESPERADOS` de `test_handlers_no_new_locks.py` gana las dos claves con lista vacía, que fija "ningún suscriptor" hasta el Sprint 5.
- Primera corrida sobre la base viva: 69 `active` y 22 `frozen` guardadas, varias ya vencidas por fecha, generan decenas de filas `update` de auditoría con `SYSTEM_USER_ID`. Aceptado y anotado en RUNBOOK (S4A-D39): es el rastro correcto del cambio de la columna.
- Corrección documental: la frase de US-094 "las lecturas devuelven el estado guardado" se reemplaza por esta decisión (C13).

**S4A-D2 · Orden de candados y forma del lote: una transacción por socio (hallazgo 2, pregunta 3; C3).**
- `test_guarded_calls.py` solo admite `with_for_update` sobre `Membership` dentro de `sell.lock_membership`, y S3-D95 / `core/locks.py` exigen `lock_member` **antes** del primer flush auditado. El `FOR UPDATE ... LIMIT 500` por lote del desglose se descarta.
- `memberships/expirations.py` (privado, entra a `PRIVATE_HELPERS["memberships"]`) hace dos fases. **Fase 1, lectura sin candados:** páginas de `RECOMPUTE_PAGE = 200` ids de socio (los distintos `member_id` con `status` guardado en active, expiring o frozen, `status_expr(today, expiring_days)` distinto del guardado y `member_id > :last`, orden por `member_id`, `LIMIT 200`; paginación por llave). **Fase 2, una transacción por socio** (`async with session_factory() as s, s.begin()`): (1) `lock_member(s, member_id)`; (2) por cada membresía candidata de ese socio, `sell.lock_membership(s, id)` (la única puerta de `FOR UPDATE`; relee con `populate_existing`, así una anulación o un pago concurrente se ve); (3) si el estado guardado ya no es candidato o ya coincide con el efectivo, se salta (idempotencia por comparación); (4) congelaciones con `queries._load_freezes_for(s, ids)` (privado de `memberships`, legal porque el archivo es del mismo módulo); (5) `compute_status(snapshot, today, expiring_days, ventanas)`; (6) asignar `m.status`, **un solo `flush` al final** (primer toque a la cadena) y `events.emit(...)` según `transition_event`; (7) commit. Orden resultante: socio -> fila -> cadena, el de D3 (el mismo de `freeze`).
- `expiring_days` se lee una vez por corrida con `settings_service.memberships_policy` (la arista `memberships -> settings` ya existe).
- Ante `DBAPIError` con SQLSTATE en `BUSY_SQLSTATES` (55P03, 57014, 40P01) el socio se reintenta hasta `MAX_BUSY_RETRIES = 2` con esperas de 0,5 s y 1 s; si sigue ocupado se cuenta en `busy_omitidos` y el job sigue con el siguiente socio (no aborta el ciclo; se corrige en la siguiente corrida o con `--run-once`). Cualquier otra excepción de un socio se cuenta en `errores` (se registra solo el tipo, nunca ids ni nombres) y el ciclo continúa.
- `RecomputeSummary(revisados, cambiadas, por_vencer, vencidas, otras, busy_omitidos, errores)` (dataclass congelada, solo conteos). El job devuelve `ok` si `busy_omitidos + errores == 0`; si no, `error` con los conteos (re-ejecutable el mismo día: es idempotente).
- Nada se llama `on_*` en el archivo. Prueba AST nueva del orden de candados (B2) y prueba de interbloqueo con `dos_sesiones` (`freeze`/`cancel`/`sell`/`register` simultáneos con el job; molde `tests/memberships/test_lock_order.py`).

**S4A-D3 · `core/jobs.py`: reclamo, cierre e idempotencia por `(job_name, run_date)` (C1).**
- Modelo `JobRun(CommonColumnsMixin, Base)` en el esquema `worker`, **sin** `__audited__` (bitácora operativa). Vista `JobRunView` (dataclass congelada: `id, job_name, run_date, started_at, finished_at, result, error, details`).
- `async claim_run(session, job_name, run_date, *, now, stale_after=timedelta(hours=6)) -> JobRunView | None`: un `postgresql.insert(JobRun).on_conflict_do_update` sobre `(job_name, run_date)` que fija result en running, started_at en `now`, finished_at y error en nulo, solo si el result previo no es running o su started_at es anterior a `now - stale_after`, con `returning`; `None` si otra corrida running sigue vigente. Se escribe con Core (no `text()`), así `test_sql_literals_constant.py` no se involucra; `now` sale de `current_clock().now_utc()` (no `now()` de la base: `FrozenClock` lo controla). `created_by = get_actor()`.
- `async finish_run(session, run_id, *, result, error, details)`: relee la fila (el reclamo la dejó running), agrega el intento a `details["attempts"]` (lista de `{started_at, finished_at, result, error}`, máximo 20) y fija `finished_at` y `result`. `error` guarda solo el tipo de la excepción y conteos.
- `async last_run(session, job_name) -> JobRunView | None` (`started_at DESC`).
- Cada llamada corre en una sesión corta y propia, distinta de la del job (un fallo del job no borra el registro del error). Una reejecución del mismo día vuelve a reclamar la misma fila: se permite tras ok y error, se bloquea con un running de menos de 6 horas.
- Importación (absorbe `test_core_jobs_imports.py`): solo `app.worker.*` importa `app.core.jobs`; `core/jobs.py` no importa `app.modules`; ni `core/audit.py` ni `core/health.py` lo importan. `migrations/env.py` y `tests/` sí.

**S4A-D4 · Adelantar el día: `--date` en el worker y en la CLI (hallazgo 6, pregunta 4).**
- `python -m app.worker.main --run-once <job> [--date AAAA-MM-DD]` y `python -m app.cli recompute-memberships [--date AAAA-MM-DD] [--as <correo>]`. Con `--date`, el proceso construye `FrozenClock` a las 12:00 de Bogotá de esa fecha y lo instala con `set_clock` antes de abrir el runtime; `today_bogota()` da exactamente la fecha, `run_date` es esa fecha y la auditoría lleva `at` de ese día. Es la única forma de "adelantar el reloj" entre procesos (el `FrozenClock` vive en el `ContextVar` del proceso).
- Guarda: con `Settings.ENV == "production"` un `--date` distinto de hoy sale con código 2 ("--date solo se acepta con ENV=dev"). Sin leer el entorno fuera de `core/config.py` (`test_no_os_environ.py`). RUNBOOK documenta que una auditoría con fecha adelantada solo se produce en desarrollo (la cadena no exige `at` monótono).
- Códigos de `--run-once`: 0 ok, 1 el job falló, 2 el job no existe (imprime los registrados) o argumento inválido, 3 ya hay una corrida running vigente. `--status <job>` (solo lectura) imprime el último `JobRunView` en JSON (sin `attempts`) y sale 0, o 2 si no hay corridas; el smoke lo usa para comprobar `job_runs` sin `psql`.

**S4A-D5 · Horario y zona como constantes, no en `Settings` (pregunta 6; C1).** `worker/schedule.py`: `WORKER_TIMEZONE = "America/Bogota"`, `DAILY_HOUR = 7`, `DAILY_MINUTE = 0` (Q28, N-32). Sin `WORKER_TZ` ni `WORKER_DAILY_HOUR`: `Settings` es `extra="forbid"` y exigiría `.env.example`, `NON_API_ENV_VARS` y `test_env_example.py` para un valor que no es caso de uso de v0.1. `.env.example` y `core/config.py` no cambian. La imagen fija `TZ=UTC`; el worker usa `zoneinfo` explícito (`tzdata` y `apscheduler 3.11.3` ya están en `pyproject.toml`, `uv.lock` y la imagen: sin cambios de dependencias ni de `NOTICE`).

**S4A-D6 · Estructura y arranque del worker (pregunta 7; C1).**
- `worker/schedule.py` (puras: `next_run(now_utc, tz, hour, minute)`, `should_run(job_name, run_date, now_local, scheduled_at, previous)`), `worker/registry.py` (`JobSpec(name, run, hour, minute, timeout_s=900)` y `get_registry()` sobre una tupla inmutable), `worker/jobs/__init__.py` (declara `JOBS`) y `worker/jobs/expirations.py` (`async run(ctx: JobContext) -> JobResult`), `worker/runner.py` (`run_job`, `run_cycle`), `worker/runtime.py` (`worker_runtime`, `wait_for_database`) y `worker/main.py` (delgado: argparse, `serve`, `run_once`, `main`).
- `worker_runtime(settings)` (async context manager) **no se extrae de `cli.py`**: repite a propósito las líneas de `cli_runtime` (listeners de auditoría, `oplog` y cifrado, `main.load_module_services()`, `configure_logging`, `db.configure_engine(create_engine_from(settings))`, `dispose_engine`) para que `worker` no importe `cli`. Sin keyring ni JWT (`expirations` no cifra); el Sprint 5 agrega `ensure_keys` aquí. `load_module_services()` es obligatorio (`test_gates_registered.py`).
- `wait_for_database(settings, *, sleep=asyncio.sleep)`: reintento exponencial 1, 2, 4, ... tope 60 s; el sondeo es `SELECT 1 FROM worker.job_runs LIMIT 0`, de modo que un worker que arranca antes de que el api termine `0012` reintenta en lugar de caer en bucle de reinicios.
- `run_job`: `today = current_clock().today_bogota()`, `claim_run`, `actor_scope(SYSTEM_USER_ID)` y `batch_scope(uuid4())`, el job bajo `asyncio.wait_for(..., spec.timeout_s)`, `finish_run`; captura la excepción de cada job sin detener a los demás y llama `alerts.alert(...)` si falló. `serve`: `AsyncIOScheduler(timezone=WORKER_TIMEZONE)` con `CronTrigger(hour=7, minute=0)`, `coalesce=True`, `max_instances=1`, más el trabajo de latido (S4A-D8); al arrancar recupera el ciclo del día si `should_run`; `SIGTERM` termina el job en curso (espera acotada a 30 s). `max_instances=1` más `claim_run` impiden dos corridas aunque haya dos réplicas.
- La lógica vive en `schedule.py`, `runner.py` y `runtime.py` (puras o con inyección de `sleep`, reloj y fábrica de sesión) para que `main.py` sea fino y la cobertura no dependa del bucle del scheduler. Ninguna función pasa de 50 líneas.

**S4A-D7 · `core/alerts.py` mínimo en B1 (C1; G-08).** `CLAUDE.md` lo lista y ningún slice lo creaba. Se crea el mínimo de v0.1 (~40 líneas): `AlertSink` (Protocol), `register_sink(sink)`, `alert(code, **context)` (llama a todos los sinks; un sink que falla no propaga), `LogAlertSink` (`logger.error` con `code` y contexto sin datos personales) registrado por defecto. Telegram (v0.2, N-34) agrega su sink sin tocar a los llamadores. El runner llama `alert("job_failed", job=..., result=...)`. Prueba `tests/core/test_alerts.py`; `core` no importa módulos.

**S4A-D8 · Healthcheck del worker: latido en archivo (hallazgo 5c, pregunta 5; C2).**
- Un job diario no da latidos: el healthcheck por `job_runs` del plan se interpreta como vivo = el scheduler sigue girando (latido); qué corrió se lee de `job_runs` con `--status`. El scheduler agrega un trabajo `IntervalTrigger(seconds=30)` que hace `Path(HEARTBEAT_PATH).touch()` (`HEARTBEAT_PATH = Path("/tmp/apex-worker-heartbeat")`, constante de `worker/runtime.py`; `touch` no usa `datetime.now`, `test_no_direct_now.py` no se involucra). Se escribe solo después de conectar a la base.
- Compose: `healthcheck.test` es `["CMD", "python", "-c", <programa>]`, donde el programa sale con 0 si existe el archivo de latido y su `mtime` tiene menos de 120 s (usa `os.path.getmtime` y `time.time`); `interval: 30s`, `timeout: 5s`, `retries: 3`, `start_period: 90s`. No depende del módulo `app.worker`, así que W0-1 puede declararlo antes de que exista el código.
- `/health` del api **no** lee `job_runs` en 4A (US-115 es v0.2); `CLAUDE.md` se corrige (C13).

**S4A-D9 · Compose, perfil, binds de desarrollo, smoke y CI (hallazgos 5 y 8; C2; N-3).**
- **W0-1** (con `profiles: ["worker"]` conservado): añade `healthcheck` (S4A-D8) y `depends_on: api: condition: service_healthy` junto a `db` (las migraciones las corre el api al arrancar), conserva `command: ["python", "-m", "app.worker.main"]` (la imagen no trae `uv`; US-113 T13 se corrige), `restart: unless-stopped`, `env_file ../.env`, `keys` en solo lectura y `uploads`; **sin `ports`** ni `.env.seed`. Se actualiza el comentario de `compose.yml:48-50`. `scripts/ci/test_compose_config.sh` gana aserciones de healthcheck, de `depends_on` del api y de ausencia de `ports` en `worker` (`:110` ya cubre `ADMIN_*` y `.env.seed`), y **mantiene** la aserción del perfil. Gate: `docker compose config` y el smoke sin el perfil.
- **W0-2** (después de cerrar B1): quita `profiles` e invierte la aserción de `:58` (worker no tiene perfil); `compose-smoke.sh` agrega `up -d --no-build worker`, `esperar_healthy worker 120`, `RestartCount == 0` tras 30 s, `run --rm worker python -m app.worker.main --run-once expirations` con código 0 **dos veces** y `--status expirations` con dos intentos. Reconstruir `apex-api:local` con buildx antes (RUNBOOK §7).
- **`compose.dev.yml`** agrega a `worker` y a `tools` los binds de `api` (`../api/src:/app/src:ro` y `../api/migrations:/app/migrations:ro`): la demo y el smoke locales ejecutan el código del árbol sin reconstruir la imagen en cada slice (hallazgo 8). La imagen de producción no cambia. Un cambio en `app/worker/` exige reiniciar el contenedor `worker` (no hay `--reload`).
- **CI**: el job `images` corre el smoke ampliado; `e2e-stack` hace `up -d --build` sin perfiles y el worker arranca solo (espera la base; si arranca después de las 07:00 de Bogotá corre el ciclo del día, que con la base vacía no cambia nada pero deja una fila en `worker.job_runs`): W0-2 verifica con `grep` que `datosDeBase()` de `web/tests/e2e/stack/helpers/stack.ts` no cuenta esa tabla. No se agregan variables `USER_*`.

**S4A-D10 · Fronteras del worker y de los jobs (C1, C3).** El worker es capa de aplicación como `cli.py`: importa `app.core.*` y, de los módulos, solo `service`, `schemas` y `exceptions`; nunca `models`, `router` ni privados, y no escribe SQL (todo el SQL del worker vive en `core/jobs.py` o llega por services; `test_sql_literals_constant.py` no recorre `app/worker/`). Lo vigila una prueba nueva `tests/architecture/test_worker_boundaries.py` (por `ast` con `find_forbidden_imports`, recorre `app/worker/**` y `app/cli.py`, que `test_no_cross_models.py` no cubre) que además absorbe la regla de importadores de `core.jobs`.

### Auditoría verificable

**S4A-D11 · `verify_chain` ampliada con continuación y semántica del salto (hallazgo 4, pregunta 9; C4).**
- Firma: `verify_chain(rows, *, start_prev_hash: str = ZERO_HASH, start_seq: int = 1) -> VerifyResult`. `VerifyResult` gana `last_seq: int | None = None` y `last_hash: str | None = None` **al final y con valor por defecto**, así las construcciones posicionales de `tests/core/test_audit_chain.py` (11 pruebas) siguen verdes. `last_seq` y `last_hash` son los de la última fila verificada (o `None` si no hubo filas).
- Semántica del salto, sin cambio: `broken_at_seq` es el `seq` de la **primera fila que no encaja** (si falta la 1234, es la 1235). Se mantiene (las pruebas existentes lo fijan y el enlace de la pantalla apunta a una fila que existe). Excepción, la **cola perdida**: si el recorrido termina sin ruptura pero `last_seq < through_seq` (alguien borró las últimas filas), `run_verification` marca `broken_at_seq = last_seq + 1` (ese seq puede no existir: el detalle responde 404 y el front lo dice).
- Las columnas espejo (`created_at`, `updated_at`, `created_by`) hay que leerlas para que `MIRROR_KEYS` las compare: el lote lee todas las columnas de la fila.

**S4A-D12 · Dónde vive la verificación: `core/audit_verify.py` (hallazgo 8; C4).** `core/audit.py` (502 líneas) conserva solo `verify_chain` ampliada; el resto nace en un archivo nuevo para no pasar de 800 líneas ni de 50 por función: `AuditVerification(CommonColumnsMixin, Base)` (esquema `audit`, sin `__audited__`), `VERIFY_BATCH_SIZE = 5000`, `AUDIT_VERIFY_LOCK_KEY: Final[int] = 4_270_003` (distinta de `MIGRATION_LOCK_KEY = 4_270_001` y `AUDIT_CHAIN_LOCK_KEY = 4_270_002`; `test_sql_literals_constant.py:100` suma la tercera), las sentencias SQL como constantes de módulo (`pg_try_advisory_lock`, `pg_advisory_unlock`), `async run_verification(session, *, source, by) -> AuditVerification`, `format_verify_message(result) -> tuple[str, int]` y los auxiliares `_scan_chain` y `_persist`. Importa de `core/audit` y de nadie más (`test_core_import_direction.py`). `test_audited_tables._cargar_modelos`, `migrations/env.py` y `test_no_physical_delete.py` lo conocen.
- `run_verification(session, *, source, by)`: (1) `started_at = current_clock().now_utc()`; (2) `through_seq = max(seq)` (0 si vacía); (3) lotes de 5.000 filas (`seq` mayor que el último, orden por `seq`, todas las columnas) con `verify_chain(lote, start_prev_hash=last_hash, start_seq=last_seq + 1)`, deteniéndose en la primera ruptura; (4) comprobación de cola perdida; (5) inserta `AuditVerification` (`created_by = by`) y escribe la fila `verify` con `audit.record(action="verify", table_name="audit.verifications", record_id=v.id, before=None, after={ok, rows_checked, broken_at_seq, through_seq, started_at, finished_at, source}, user_id=by)` (el hook usa siempre `esquema.tabla`; US-104 escribía `verifications`, se corrige). Las lecturas no toman el candado de la cadena; `record` lo toma al final y la clave `4_270_003` vive en otra conexión: sin ciclo posible.
- Nunca escribe ni modifica filas existentes de `audit_log` (prueba por hash de la tabla antes y después).

**S4A-D13 · Candado de la verificación y topes de tiempo (hallazgo 7, pregunta 9).**
- Exclusión mutua con `pg_try_advisory_lock(4_270_003)` de **sesión** en una conexión dedicada (`db.get_engine().connect()`), liberada en `finally` con `pg_advisory_unlock` (y por la base si el proceso muere): funciona con varios procesos y no deja estado en memoria. Si no se obtiene: 409 `verification_running` (API) o espera (CLI, S4A-D15). La conexión del candado es distinta de la sesión que escribe el resultado.
- Tiempos: Nginx `/api/` sin `proxy_read_timeout` explícito = 60 s; `statement_timeout` de 30 s por sentencia (cada lote de 5.000 filas cabe); `lock_timeout` de 10 s al escribir la fila `verify` (el hook toma el candado de la cadena). **Umbral síncrono `SYNC_VERIFY_MAX_ROWS = 50_000`** (no los 100.000 de N-30: deja margen bajo los 60 s de Nginx; lo calibra `test_verify_performance.py` con `-m perf` sobre 100.000 filas: si el recorrido de 100.000 cabe en 20 s la constante sube a 100.000 y se anota). Hasta ese `max(seq)`: 200 con el resultado. Por encima: tarea `asyncio` con su propia sesión y la conexión del candado ya tomada (se toma **antes** de responder, así el 409 es determinista), guardada en un conjunto de módulo para que no la recoja el recolector, con `finally` que libera el candado y registra el error (solo el tipo); responde **202** `VerifyStartedOut`. No sobrevive a un reinicio (aceptado por N-30; el resultado terminado sí persiste; el `--reload` del api de desarrollo la mata y no se edita `src/` durante un E2E).
- No hay continuación ni paginación de la verificación: `GET /audit/verify/last` más el sondeo del front cubren el caso largo. Nginx no se toca.

**S4A-D14 · Contrato HTTP de la verificación (C4).**
- `POST /api/v1/audit/verify` (admin; `enforce_user_limit(request, "admin-write", principal.user_id)`, 429 declarado, entra a `CON_LIMITE`): 200 `VerifyResultOut`, 202 `VerifyStartedOut`, 409 `verification_running`. El 202 se declara a mano en `responses=` (`responses_for` no admite 202 y no se amplía: `core/errors.py` no se toca); la ruta devuelve `VerifyResultOut` o `JSONResponse(status_code=202)`. Sin cuerpo: sin 422.
- `GET /api/v1/audit/verify/last` (admin): `VerifyResultOut | null` (200 con `null` si no hay verificaciones; nunca 404). Sin parámetros: sin 422. Registrada **antes** de `GET /audit/{seq}`.
- `VerifyResultOut {ok, rows_checked, through_seq, broken_at_seq, started_at, finished_at, triggered_by, source}`. Un solo nombre, `broken_at_seq`, en la columna y en el API (US-104 usaba `broken_seq`; se corrige en el desglose). La respuesta no lleva `before` ni `after`. `VerifyStartedOut {status: "running", last: VerifyResultOut | null}`.
- Código nuevo `verification_running` (409); `errorCodes.ts` lo recibe en el mismo checkpoint que su literal en `api/src`.

**S4A-D15 · `verify-audit` y `recompute-memberships` en la CLI (C3, C4).**
- Ambos usan `cli_runtime(settings, runtime_options(ctx))` y `resolve_actor(session, email)` (reemplaza a `auth.service.get_by_email` del desglose, que no existe). `--as` es opcional (sin él, `SYSTEM_USER_ID`, N-15, como `seed`); con él la acción queda atribuida a esa persona (criterio de seguridad del sprint). La demo lo usa.
- `verify-audit [--as correo] [--wait-timeout 300]`: toma el candado de sesión con `pg_try_advisory_lock` en un bucle de espera de 2 s hasta `--wait-timeout` (no `pg_advisory_lock` bloqueante: el `lock_timeout` de 10 s lo cortaría), llama `run_verification(session, source="cli", by=actor)` con el actor fijado por `unit_of_work(actor)` durante el commit (como `_seed`), imprime `format_verify_message` y sale 0 (íntegra), 1 (rota) o 2 (`--as` inválido, base caída con `OSError` o `DBAPIError` al abrir y mensaje genérico sin URL ni contraseña, o `--wait-timeout` agotado). Nunca imprime `before` ni `after`.
- `recompute-memberships [--date] [--as]`: S4A-D4 para `--date`; usa `db.get_sessionmaker()` como fábrica; llama `memberships.service.recompute_statuses(...)` dentro de `unit_of_work(actor)`; imprime el resumen (solo conteos); sale 0, o 1 si `busy_omitidos + errores > 0`.
- Tamaño: `cli.py` (541) crece unas 120 líneas (~660, bajo el tope de 800); si pasara de 760, los dos comandos pasan a `app/cli_ops.py` registrado desde `cli.py`.

**S4A-D16 · Consulta de auditoría: un solo contrato de filtros (preguntas 10 y 15; US-102; C5).**
- `GET /api/v1/audit` (admin): `Page[AuditRow]` con `Annotated[PageParams, Depends()]`, `q: SearchQuery` y los filtros `from` y `to` (`AwareDatetime`, alias, rango `[from, to)`), `user_id` (UUID, igualdad), `table` (patrón de dos segmentos en minúscula y guion bajo separados por un punto, igualdad con el `table_name` real `esquema.tabla`: `members.members`, `memberships.memberships`, `memberships.membership_freezes`, `payments.payments`, `plans.plans`, `auth.users`, `settings.settings_sections`, `audit.verifications`), `record_id` (UUID), `subject_member_id` (UUID) y `action` (`Literal` de `AUDIT_ACTIONS`, fuente única con el CHECK de `0002`). `ROUTES.md:89` (`from&to&user&entity&action&q`) se corrige al contrato real (C13); el cliente usa los mismos nombres.
- `q` (obligatoria en toda lista `Page_`, `test_list_routes_use_page_params`): si es un UUID exacto filtra `record_id`; si no, es un fragmento del **correo** de quien actuó (coincidencia parcial, sin distinguir mayúsculas ni tildes) resuelto en `auth` con la función nueva `auth.service.search_user_ids(session, term, *, local_part_only=False, limit=200) -> set[UUID]` (`ILIKE` con `core.search.clean_query` y `contains_pattern`, valor ligado y escape, nunca `text()` dinámico; `ids_by_email` exacta no se toca porque la usa `resolve_actor`). Buscar por nombre de socio no entra (cruzaría `audit` con `members`): `// DESIGN-GAP:` en F1.
- Orden `seq DESC`. `total` con el mismo filtro (`count(*)`); si `test_list_performance.py` (100.000 filas, `limit=25`, menos de 500 ms con y sin filtros) fallara por el `count`, sin filtros se usa `max(seq)` (la cadena no tiene huecos, N-30). Los índices necesarios ya existen (`ix_audit_log_at`, `ix_audit_log_table_record`, `ix_audit_log_user_id`, `ix_audit_log_table_seq`, `ix_audit_log_subject_member_seq`): **no hay migración `0014_audit_indexes`**.
- `AuditRow {seq, at, user_id, user_email, user_name, action, table_name, record_id, subject_member_id}` nunca lleva `before` ni `after`. `user_email` es válido aquí (la prueba de sufijo `_email` solo barre `/api/v1/members...`) y solo lo ve el admin. La consulta no modifica `audit_log` (prueba por conteo y hash de la última fila).
- La pantalla filtra por usuario con un selector (usuarios de `GET /users?limit=200` más la opción fija Sistema (worker) = `SYSTEM_USER_ID`) que envía `user_id`.

**S4A-D17 · Detalle y diff sin descifrar nunca (US-103).**
- `GET /api/v1/audit/{seq}` (admin): `seq: int` con `ge=1` (422 si no es entero), 404 `audit_entry_not_found` (código nuevo). Devuelve `AuditDetail {seq, at, user_id, user_email, user_name, action, table_name, record_id, subject_member_id, before, after, prev_hash, hash, changes}`. `before` y `after` salen **tal cual se guardaron**: los campos cifrados son blobs `apx1.<key_id>.<alg>...` (texto cifrado, no material de llave) y los `_idx` de `members` son `***`; el servicio **no importa el bus** ni llama a `decrypt` (`test_reveal_single_door.py` ya lo vigila; el repaso de seguridad lo repite). Los `reference` y `void_reason` de pagos van en claro en la cadena (ya lo son): el detalle admin los ve; el historial del socio y el tablero no (S4A-D20, S4A-D28).
- `changes: list[FieldChange {field, kind: added | removed | changed, before, after, encrypted: bool}]` por la función pura `diff(before, after)` (orden estable por nombre de campo; `insert` todo added, `delete` todo removed, `update` solo los distintos; para `reveal`, `login`, `verify` y `download` se aplica sobre `after`). `encrypted` es verdadero si el valor (antes o después) empieza por `apx1.`. La marca "valor cifrado modificado" es solo presentación del front (`encryptedBlob.ts` más la etiqueta Cifrado con `key_id`); no hay botón de descifrar (`// DESIGN-GAP:` frente a `Auditoria.html`, que ofrece Descifrar dato).

**S4A-D18 · `audit` nace partido (hallazgo 8; C5).** `audit/service.py` (111 líneas, hoy con los cuatro suscriptores de `auth`) queda como **fachada** con esos handlers y re-exporta; el resto va en privados registrados en `PRIVATE_HELPERS["audit"]` (`tests/architecture/_imports.py:30`; comparaciones exactas de `test_no_cross_models.py:137,145,152`): `queries.py` (`list`, `get`, `recent`, `member_history`), `diff.py` (puras: `diff`, `history_fields`, `reduce_entry`) y `verify.py` (`verify`, `last_verification`, tarea en segundo plano). El conjunto crece por slice: B3 `{verify}`, B4 `{verify, queries, diff}`. `audit` sigue sin `models.py` (el modelo vive en `core/audit.py`) y de otros módulos solo importa `service`, `schemas` y `exceptions`.

**S4A-D19 · `display_name`: sin columna en 4A; respaldo con la parte local del correo (hallazgo 3, pregunta 1; C9).**
- No hay migración `0014`. `auth.users` no tiene `display_name` ni `0004_auth` lo creó; añadirlo toca `User` (auditada), `UserOut`, `UserCreate`, `UserPatch`, `seed_admin`, la fábrica, la pantalla Usuarios, el flujo de alta y la regla de tres pasos con datos, y empuja el `0014` condicional de pagos a `0015`. Nada del sprint lo exige para su valor de negocio. Se difiere a v0.2 (junto a EP-04) con dueño anotado en `DECISIONES.md` y `BRECHAS.md`; el contrato de lectura queda estable para absorberlo.
- Contrato nuevo en `auth` (nace en B4): `UserRef` (dataclass congelada en `auth/schemas.py`: `id, email, display_name`) y `async user_refs_for(session, user_ids) -> dict[UUID, UserRef]`, re-exportado en `service.py`. `display_name` es la parte local del correo (`ana.perez` de `ana.perez@x.co`) y `Sistema` para `SYSTEM_USER_ID`. Cuando exista la columna solo cambia esta función. **`auth.service.names_for` e `ids_by_email` no cambian** (`payments` usa `names_for` -> correo para `registered_by_name` con `partial_email`, S3-D57; `resolve_actor` usa `ids_by_email`).
- Efectos: `AuditRow.user_name`, `MemberHistoryItem.user_name` y las frases del tablero usan `display_name`; el saludo de Inicio usa la parte local del correo (`// DESIGN-GAP:` frente a Hola, Ana). Se corrige la mención "US-041 (`display_name`)" de `SPRINT-04A.md` y se cierra la contradicción abierta de `BRECHAS.md:244` (manda: no en 4A).

**S4A-D20 · Historial del socio (US-106, G-05; C6).**
- `GET /api/v1/members/{member_id}/audit` (admin y coach, `StaffDep`) vive en `members/router.py`. `members.service.history(session, member_id, page, q)` hace `ensure_exists(member_id, include_deleted=True)` (reutiliza `MemberNotFound`, 404) y delega en `audit.service.member_history(session, member_id, page, q)`. **Arista de nivel de módulo nueva `members -> audit`** (import arriba de `members/service.py`): `ALLOWED_EDGES` la suma y la aserción de `arriba` para `members` en `test_service_import_graph.py:264` pasa de conjunto vacío a `{"audit"}`, con `perezosas` de `members` igual a `{"memberships"}` intacto. El grafo sigue acíclico (`audit -> auth` solamente). No se publica la ruta desde `audit` (crearía `audit -> members`).
- Consulta: `subject_member_id = :id` por `seq DESC` sobre `ix_audit_log_subject_member_seq`, con `PageParams` y `q`. `q` es real: fragmento del nombre de quien actuó (parte local del correo; `search_user_ids(..., local_part_only=True)`, sin exponer dominios al coach).
- `MemberHistoryItem {seq, at, user_id, user_name, action, table_name, record_id, fields: list[str]}`: **sin** `user_email` (la prueba de sufijo `_email` barre todo `GET` bajo `/members` con respuesta `Page_`), sin `before` ni `after`, sin valores. Mismos campos para admin y coach. `fields` por la pura `history_fields(entry)`: `update` -> nombres de columna cambiados, **sin** `*_idx` ni columnas técnicas; `reveal` -> el campo de `after.field` (nunca `ip`); `insert` y `delete` -> lista vacía. Las filas de `payments.payments` aportan nombres de campo, jamás `reference` ni `void_reason`.
- Abrir la ficha (`members.get`) no agrega entradas; la cadena sigue íntegra con `verify_chain`.
- **Congelaciones (deuda L2 de B2 / I-4 de V10):** `MembershipFreeze` no declara `__audit_subject__` y no se agrega: necesitaría `member_id`, columna nueva en una tabla append-only con trigger (backfill imposible con `UPDATE` bloqueado). Decisión: la congelación aparece en el historial por el `update` de la membresía (`end_date`, `status`). `test_audited_tables.py::test_membership_freezes_es_requerida_y_no_declara_sujeto_hasta_us_106` se renombra `..._por_decision_s4a_d20`. `test_audit_subject.py` fija los tres modelos con sujeto (`Member` por `id`; `Membership` y `Payment` por `member_id`) y que `members` no importa `memberships.service` ni `payments.service` para esta ruta.

**S4A-D21 · `contact_for_notification`: firma única y rastro (pregunta 13, hallazgo 10; C7).**
- Firma: `async def contact_for_notification(session, member_id: UUID, purpose: str) -> Contact`. Sin `fields` (el contacto es teléfono y correo, fijos), sin `by` (el actor sale de `get_actor()`: `SYSTEM_USER_ID` en el worker, el de `--as` en la CLI) y sin `SensitiveFieldRevealed`, `bus.op_context` ni `SYSTEM_ACTOR` (no existen; S3-C16). Vive en `members/contact.py` (privado nuevo, a `PRIVATE_HELPERS["members"]`; `service.py` re-exporta `contact_for_notification`, `Contact`, `MemberNotContactable` y `validate_purpose`).
- Orden: (1) `validate_purpose(purpose)` **antes** de leer nada: solo `notify` y `auth_link`; `mask`, `reveal`, `export` y cualquier otro lanzan `InvalidPurpose` (`MemberError`, código `invalid_purpose`, no sale por HTTP; `OP_PURPOSES` ya contiene `notify` y `auth_link`, así que no hay migración ni `0014_crypto_ops_*`); (2) cargar el socio y lanzar `MemberNotContactable` si no existe o tiene `deleted_at`, sin descifrar; (3) descifrar teléfono y correo con `detail._decrypt_fields` pasando el propósito (única puerta de `types.reveal`, `test_reveal_single_door.py`); (4) por cada campo descifrado no nulo, `audit.record` con action reveal, tabla `members.members`, `record_id` y `subject_member_id` del socio y un `after` con las claves field y purpose (el `reveal` interactivo conserva `ip` y no lleva purpose: no se toca). Un campo vacío devuelve `None`, no se descifra y no audita.
- `crypto_ops`: una fila decrypt por campo con purpose y `record_id` del socio. **No se usa `bus.batch`** (matiza C7): `aggregate_ops` pierde el `record_id`. El `batch_id` común lo da el `batch_scope` del llamador (worker y CLI), que es lo que pide el criterio de mismo lote.
- Sin `lock_member`: no escribe filas de `members`, solo audita. `Contact(first_name, phone, email)` con `field(repr=False)` en teléfono y correo. Sin ruta; nada en `src/` lo llama hasta el Sprint 5. Requiere el keyring cargado (`bus_listo` en pruebas; el worker de 4A no lo abre).
- `tests/architecture/test_crypto_bus_importers.py` parte de los importadores reales de `app.core.crypto.bus` y `types` fuera de `core/`: `modules/members/service.py`, `changes.py` y `detail.py`; lista blanca: `app.core.*`, `app.modules.members.*`, y `athletes` y `attachments` cuando existan; falla si `notifications` lo importa.

### Planes

**S4A-D22 · `PATCH /plans/{plan_id}` (US-080; RN-04).** `PlanPatch` (`extra="forbid"`, `str_strip_whitespace`, `name: SafeText` de 1 a 80, `price_cop`, `duration_days` y `class_count` como `StrictInt` con los topes de `PlanCreate`, `kind`), todos opcionales; `model_fields_set` distingue no enviado de `null`. `is_active` y `deleted_at` en el cuerpo dan 422 por `extra="forbid"`. Pura `merge_plan(current: PlanSnapshot, patch) -> PlanState`: cambiar a `days` exige `class_count: null` explícito si el plan tenía clases (si no, `PlanValidationError` con field `class_count`); luego `validate_plan` sobre el resultado. `update(session, plan_id, patch)`: `SELECT ... FOR UPDATE` del plan vivo (serializa dos PATCH; `sell` toma `FOR SHARE`, sin ciclo y sin socio), `PlanNotFound` si no existe o está dado de baja, renombrar respeta `uq_plans_name_alive` (pre-chequeo y traducción de la carrera a `PlanNameDuplicated`, 409 con `existing_id`), sin cambios efectivos no hay `flush`, auditoría ni evento (200 igual), y con cambios `flush` más `PlanUpdated(plan_id, changed_fields)` (nombres de campo, nunca valores; `test_events_without_pii.py`). El precio vendido no se toca: `memberships` copia precio, fechas y `classes_total` al vender y el trigger `guard_identity` impide cambiarlos (prueba de integración RN-04). Sin `version` ni bloqueo optimista: gana la última escritura, como `PATCH /members` (D21 de S3).

**S4A-D23 · Activar y desactivar son `POST` aparte; `ROUTES.md` se corrige (hallazgo 12; brecha nueva).** `POST /plans/{plan_id}/activate` y `/deactivate` (admin, idempotentes): `set_active(session, plan_id, active)`; sin cambio no hay `flush`, auditoría ni evento; desactivar emite `PlanDeactivated(plan_id)`, activar emite `PlanUpdated(plan_id, ("is_active",))` (el catálogo no tiene `PlanActivated`). Desactivar se permite con membresías activas (RN-08) y no consulta a `memberships`. `sell` ya traduce `plan_inactive` (422): US-081 solo agrega la prueba de integración. `ROUTES.md:39` (activar y desactivar por PATCH `active`) se corrige a las dos rutas POST, y la casilla Activo de la edición de `Planes.html` queda como `// DESIGN-GAP:` (hay acciones en la fila). Se anota en BRECHAS §11.

**S4A-D24 · `DELETE /plans/{plan_id}` y la regla frente a `pending_payment` (hallazgo 12, P2-1; C8).**
- `deactivate_or_fail(session, plan_id)`: `FOR UPDATE` del plan vivo (`PlanNotFound` si no), import **perezoso** de `memberships.service` dentro de la función con el comentario `# lazy: G-03 (plans -> memberships)` (par ya en `LAZY_IMPORT_WHITELIST`), `count_active_by_plan(session, plan_id)`; si es mayor que 0, `PlanHasActiveMemberships(count)` (409 `plan_has_active_memberships`, mensaje: este plan tiene N membresías activas, desactívalo en su lugar; N es un conteo, no PII); si es 0, `deleted_at = now` e `is_active = False` en **un solo flush** (una fila `update`), `PlanDeactivated` solo si estaba activo, y 204. El nombre queda libre (`uq_plans_name_alive`). `plans` no nombra `Membership` (`test_fuera_de_memberships_nadie_nombra_membership`).
- **Regla de `pending_payment`:** cuenta como activa (N-22: `pending_payment`, `active`, `expiring` y `frozen` por estado efectivo). Un plan con una venta sin pagar **no se puede dar de baja** hasta anular esa membresía (`POST /memberships/{id}/cancel`, admin). Es la respuesta a P2-1: los 166 planes de datos de prueba (30 `E2E-tope-*` y los de las specs) se retiran con un procedimiento de limpieza en desarrollo (anular las `pending_payment` de esos planes y luego `DELETE`), documentado en RUNBOOK y ejecutado como paso manual de `verify-delivery`; **no** es código de producción ni un endpoint nuevo.
- Carreras: `sell` toma socio, luego `FOR SHARE` del plan, luego la fila; la baja toma `FOR UPDATE` del plan y cuenta sin pedir socio. Una venta en vuelo hace esperar la baja (503 `busy` si pasan 10 s) y una baja confirmada hace que `sell` reciba `PlanNotFound` convertido en `PlanInvalid`. Sin ciclo.

**S4A-D25 · Socios con él entra en B7 y F4 (hallazgo 13, pregunta 12; C8).** Contrato por lote en `memberships`: `async counts_active_by_plans(session, plan_ids) -> dict[UUID, int]` (un `GROUP BY plan_id` con el mismo `status_expr` y la misma exclusión de `cancelled` y `expired` que `count_active_by_plan`, por trozos de `ID_BATCH`; `queries.py`, re-exportado en `service.py`). `PlanOut` gana `active_members_count: int`; `plans.service` lo llena con un helper `_out_with_counts(session, planes)` que llama `counts_active_by_plans` por **import perezoso** (mismo par G-03) en `list`, `detail`, `update` y `set_active`; `create` devuelve 0 sin consulta. El total partido de activos e inactivos no necesita backend: el front lee `total` de dos llamadas `GET /plans?limit=1` con `active=true` y con `active=false`. `planRowSchema` del front no es estricto: el campo nuevo no invalida la lista. Descripción y Días para usarlas de `Planes.html` no tienen columna: `// DESIGN-GAP:`.

**S4A-D26 · Las cuatro escrituras de planes y la de verificación usan `admin-write` (C4, C8).** Las cinco llaman `await enforce_user_limit(request, "admin-write", principal.user_id)` después del rol, declaran 429 por ruta (nunca en el `APIRouter`, D27 de S3) y entran a `CON_LIMITE` de `test_error_codes_per_route.py` (`PATCH /api/v1/plans/{plan_id}`, `POST .../activate`, `POST .../deactivate`, `DELETE /api/v1/plans/{plan_id}`, `POST /api/v1/audit/verify`). `USER_LIMITS` no cambia (9 cubetas, 8 variables `USER_*`, sin variables nuevas en CI). Las lecturas nuevas no limitan. `test_writes_have_user_limit.py` y `test_user_limits_catalog.py` exigen que estén todas; sus Rojos las incluyen.

### Tablero

**S4A-D27 · Contrato de `GET /dashboard` (US-108).** Módulo de lectura `dashboard` (`router.py`, `schemas.py`, `service.py`, `__init__.py`; **sin `models.py`**), `"dashboard"` al final de `MODULES` (nadie lo importa; importa a los demás). `GET /api/v1/dashboard` con `StaffDep`, `dependencies=[Depends(no_store)]`, `SessionDep`, `responses_for(401, 403)` y sin 422 (sin parámetros). `DashboardOut` lleva `today: date`, los cinco conteos `members_active`, `members_expiring`, `members_expired`, `members_frozen` y `members_pending_payment`, `income_month` (AAAA-MM), `income_month_cop: int`, `last_movements: list[MovementOut]` (máximo 10) y los cinco campos futuros `notifications_today`, `members_without_consent`, `attendance_week`, `sessions_today` y `wod_today`, **presentes y `null`** (sin `exclude_none`; el front los pinta Disponible en v0.x). `today = current_clock().today_bogota()` (no `Depends(Clock)`). KPI de membresías desde `memberships.service.summary(session, today=today)` (caché propia de 30 s; el job no la invalida, S4A-D1); ingresos desde `payments.service.summary(session, month_of(today))` (`total_cop`; el mes de Bogotá). `month_of(today)` devuelve AAAA-MM y es pura. `dashboard` no recalcula estados ni suma pagos. Sin caché propia. Aristas de nivel de módulo nuevas, solo las que se importan de verdad: `dashboard -> audit`, `-> auth`, `-> members`, `-> memberships`, `-> payments` (**no** `-> plans`: el nombre del plan sale de `memberships.refs_for`, así `plans` sigue importado solo por `memberships`).

**S4A-D28 · Últimos movimientos (Q10, US-110; hallazgos 11 y 14).**
- `audit.service.recent(session, tables, limit, *, actions, exclude_user_ids) -> list[AuditEntryView]`: `actions` por defecto insert, update y delete; `limit` de 1 a 50 (`ValueError` fuera de rango); `tables` debe estar en la lista blanca `RECENT_TABLES_ALLOWED` = `members.members`, `memberships.memberships`, `payments.payments`, `plans.plans`, `auth.users`, `settings.settings_sections`, con los nombres **reales** `esquema.tabla` (`crypto.*` rechazadas; US-110 escribía `members`, `memberships` y `payments`, que no existen en la cadena); una consulta filtrada por tabla, acción y usuario excluido, ordenada por `seq` descendente con `LIMIT`, por `ix_audit_log_table_seq`. Devuelve una **vista reducida inmutable** (`AuditEntryView`: `seq, at, user_id, action, table_name, record_id, subject_member_id` y `before` y `after` filtrados por la lista blanca de llaves `member_id, plan_id, membership_id, amount_cop, voided, deleted_at, status`). Ningún blob `apx1.`, ni `reference`, ni `void_reason` sale del service (`reduce_entry`; prueba que busca `apx1.` en la respuesta serializada completa).
- `dashboard` llama `recent` con las tres tablas de negocio, límite 10 y `exclude_user_ids=(SYSTEM_USER_ID,)`: el límite de 10 se aplica **después** de excluir al sistema (el job de vencimientos y el seed no tapan lo de recepción; Q10 y la pregunta 2 de US-110). `Inicio.html` muestra Sistema marcó 3 membresías como vencidas: gana US-110, `// DESIGN-GAP:` en F3.
- Nombres por lote, sin importar `plans`: socio por `subject_member_id` con `members.names_for` (incluye bajas); plan y fechas por `memberships.refs_for` de los `record_id` de filas de membresía; actor por `auth.user_refs_for`. Si falta un nombre se usa un socio o un plan genérico (nunca falla). `short_name("Laura", "Gómez Restrepo")` da `Laura G.`; `format_cop(120000)` da `$ 120.000`.
- `MovementOut` lleva `seq, at, phrase, table_name` (Literal de las tres tablas reales), `record_id` y `member_id`.
- `test_read_modules.py`: `dashboard` no tiene `models.py`, no importa `app.modules.*.models` ni `app.core.audit` ni `app.core.audit_verify`, y no abre `session.execute` (solo compone services).

**S4A-D29 · Roles y KPI.** Admin y coach ven el mismo tablero (el coach solo ve frases sin datos personales; no tiene `GET /audit`). `members_pending_payment` es visible (Q3); `// DESIGN-GAP:` en F3 por la línea de pendientes de pago que el diseño no dibuja. El cuadre con datos de demostración (T8 de US-109) se difiere a 4B (US-111); las pruebas de 4A usan fábricas.

`movement_phrase(entry, names) -> str` es pura, vive en `dashboard/service.py` y arma la frase con el actor como `display_name`. Catálogo (S4A-D28):
- socio insert: registró a {Socio}; update con `deleted_at` fijado: dio de baja a {Socio}; con `deleted_at` limpiado: reactivó a {Socio}; otro update: actualizó los datos de {Socio};
- membresía insert: vendió {Plan} a {Socio}; update con status cancelled: anuló la membresía {Plan} de {Socio}; update de pending_payment a otro estado (activación por cobertura): la membresía {Plan} de {Socio} quedó al día; otro update: actualizó la membresía {Plan} de {Socio};
- pago insert: registró un pago de {monto} de {Socio} (monto de `after.amount_cop`); update con `voided` fijado: anuló un pago de {Socio}, **sin monto** (un update de pago anulado no trae `amount_cop` y no se lee `payments` aparte; pregunta 14);
- cualquier otro caso: modificó {entidad} de {Socio}.

### Front

**S4A-D30 · Features, rutas y menú (C10).** `ENABLED_FEATURES` suma `audit` (nueve; `features.test.ts:10-13`) en F1, con `load` de `/sistema/auditoria` (`routeTable.ts:146`), `routes.test.ts` (lista de rutas con `load`), `nav.test.ts` (Auditoría entre Usuarios y roles y Configuración) y la guarda `audit.view` (admin). La pestaña Historial es la hija `/socios/:id/historial` (`childRoute(MEMBER_DETAIL, ...)` con `CHILD_TABS`, acceso `members.history.view`, **feature `members`** y no `audit`, porque el coach la ve; `load` de `features/members/components/MemberHistoryTab`); `src/config/routes.reference.ts` y `ROUTES.md` se mueven juntos (`routes.test.ts:35` los compara; `:127` fija los hijos de la ficha y pasa a incluir historial). `MemberDetailPage.tsx:57` pierde `disabledUntil` y `MemberDetailPage.test.tsx:101-114` cambia. `permissions.ts` no se toca (`audit.view`, `members.history.view`, `plans.manage` y `dashboard.view` ya existen).

**S4A-D31 · Pantalla de auditoría (F1; US-102, US-103, US-104).** En `features/system/` (la feature Sistema ya existe): `pages/AuditPage.tsx` (más css), `components/AuditFilters.tsx`, `AuditDetailPanel.tsx`, `VerifyChainButton.tsx`, `auditFilters.ts` (URL a API: `from` y `to` de Bogotá a UTC con `core/i18n`, `table`, `user_id`, `action`, `record_id`, `q` en memoria como en S2-D41, `seq` del detalle en la URL), `auditErrors.ts`; hooks `useAudit`, `useAuditEntry`, `useLastVerification` (con `refetchInterval` mientras el estado es running) y `useVerifyChain` (con `useSensitiveMutation`) en `api.ts`; Zod en `schemas.ts`. `shared/lib/encryptedBlob.ts`: `parseEncryptedBlob(value: unknown)` devuelve el `keyId` y el `alg` o `null`, por el prefijo `apx1.` (nunca devuelve ni guarda el texto cifrado). El botón lleva el texto del diseño, **Verificar ahora** (C10; el plan decía Verificar cadena); resultado "Cadena íntegra: N filas verificadas" o "Cadena rota en el registro seq X" con enlace a `?seq=X`; 409 con mensaje; fecha de la última verificación en Bogotá; 404 del detalle ("ese registro ya no existe"). `// DESIGN-GAP:` en: columna Qué cambió (anterior a nuevo; RN-13: el antes y después solo en el detalle), búsqueda por nombre de socio, Descifrar dato o Mostrar (US-103 lo prohíbe), Exportar rango (v0.2), última firma ML-DSA (v0.3), entidades Resultado y Llave (versiones futuras) y valores enmascarados. Sin ítem de menú para el coach (la ruta ya es admin).

**S4A-D32 · Historial de la ficha: se unifican las tres formas (hallazgo 14, pregunta 11; C10).** Se **adapta** `audit-labels.ts` (slice `web/shared`) y se mapea en la feature, sin duplicar `HistoryAside`: `AuditEntryView` gana `fields?: readonly string[]` y `phrase?: string`; `summarizeChange` acepta `fields` (línea Cambió: Teléfono, Notas con `FIELD_LABELS`, sin valores) cuando no hay `before` ni `after`; `ENTITY_LABELS` gana las claves reales `members.members`, `memberships.memberships` y `payments.payments` (las viejas se conservan); `HistoryAside` pinta `entry.phrase` como línea fuerte cuando existe. `features/members/lib/historyEntries.ts` convierte `MemberHistoryItem` a `AuditEntryView` y `historyPhrase.ts` arma la frase (editó teléfono y notas, vendió una membresía, registró un pago, anuló un pago, mostró el documento). `MemberHistoryTab` usa `useMemberHistory` (`useInfiniteQuery`, `maxPages: 20`, `limit` 25) sobre `HistoryAside`; la caja Historial reciente de `MemberDataTab.tsx:14` se conecta a las 5 últimas con el enlace historial completo. Cierra el criterio diferido de US-066.

**S4A-D33 · Inicio (F3; US-109, US-110).** Se conserva `InicioPage.tsx` (`routeTable.ts:103`; US-109 decía `HomePage.tsx`). Nuevos en `features/dashboard/`: `api.ts` (`useDashboard`, clave `["dashboard"]`, `staleTime` 60 s), `schemas.ts` (Zod; futuros `nullable()`, no `optional()`), `links.ts` (`kpiLinks(today)`: `/socios?membership_status=` con active, expiring, expired y pending_payment, y `/pagos?from&to` con el mes de Bogotá en UTC, desfase fijo de 5 horas), `components/KpiGrid.tsx` (cuatro `KpiCard` de v0.1 más la línea de pendientes de pago), `FutureKpis.tsx` (tarjetas con `null` dicen Disponible en v0.x, nunca 0), `LastMovements.tsx` (frase, hora relativa de Bogotá, enlace a `/socios/:id`; carga, vacío y error). `KpiCard` y `HistoryAside` ya cubren carga, error, `null` y `href`; el kit no cambia. `InicioPage.test.tsx` se reemplaza; el saludo usa la parte local del correo (S4A-D19). `home.spec.ts`: uno en `web/tests/e2e/stack/` (login real, KPI igual a `GET /dashboard`, clic en Por vencer) y uno en `web/tests/e2e/` (preview, API simulada, coach). Capturas a 320, 768, 1024 y 1440 en claro y oscuro.

**S4A-D34 · Planes en el front (F4; US-080, US-081, US-082).** `PlansPage` gana una columna de acción por fila (menú: Editar, Activar o Desactivar según `is_active`, Dar de baja) tras `<Can action="plans.manage">`, la columna Socios con él (`active_members_count`) y el total de activos e inactivos (dos lecturas con `limit=1`). `PlanForm` gana modo edición (precarga, aviso fijo "Cambiar el precio no modifica las membresías ya vendidas", envío solo de campos modificados, error de campo del 422 o 409). Desactivar usa `ConfirmModal` ("Las membresías vigentes con este plan siguen igual; el plan deja de aparecer al vender"); dar de baja usa `ConfirmModal` y ante `plan_has_active_memberships` muestra el mensaje del API y el botón Desactivar. Hooks `useUpdatePlan`, `useSetPlanActive` y `useDeletePlan` en `features/plans/api.ts`, todos con `useSensitiveMutation`; invalidan `PLANS_QUERY_KEY`. `planErrors.ts` traduce el código nuevo. `web/tests/e2e/stack/plans.spec.ts` se revisa. La venta (P2-1: 100 de 166 planes) se resuelve limpiando datos (S4A-D24), no con un buscador.

**S4A-D35 · Mutaciones, códigos y contrato (C10).** `useVerifyChain`, `useUpdatePlan`, `useSetPlanActive` y `useDeletePlan` pasan por `useSensitiveMutation` (S3-D104); **no** se agregan a la lista blanca de `tests/lint/sensitive-mutations.test.ts`. `errorCodes.ts` gana `plan_has_active_memberships`, `verification_running` y `audit_entry_not_found` solo después de que su literal exista en `api/src` (`errorCodes.test.ts`); `invalid_purpose` y `member_not_contactable` no salen por HTTP y no se agregan. `core/api/types.ts` se regenera con `npm run gen:api` en cada slice que publica rutas (B3, B4, B5, B7, B8). `tests/lint/boundaries.test.ts` no cambia: nada cruza features (la auditoría y el historial comparten solo `shared/`).

**S4A-D36 · DESIGN-GAPs y `BRECHAS.md` §11 (hallazgo 10; C13).** Cada desvío entre diseño e historias lleva `// DESIGN-GAP:` en el código y una fila en una sección nueva `docs/BRECHAS.md` §11 (Sprint 4A) con su dueño: `Auditoria.html` (Qué cambió, búsqueda por nombre de socio, Descifrar dato o Mostrar, Exportar rango v0.2, firma ML-DSA v0.3, entidades Resultado y Llave, valores enmascarados), `Inicio.html` (Sistema marcó..., saludo con nombre, Hoy en el box, Por avisar hoy, Asistencia, WOD de hoy: versiones futuras; pendientes de pago), `Planes.html` (Descripción, Días para usarlas, casilla Activo en la edición) y `ROUTES.md` (PATCH `active`; `GET /audit` con otros nombres). La revisión de diseño previa al 4A queda **cerrada**: S3-D98 (orden por vencimiento) fuera de v0.1 con dueño de backlog v0.2 (junto a EP-16), los pendientes de diseño de §10 sin cambio y sin código, y las brechas nuevas con su slice (C13).

### Pruebas, migraciones, cobertura y gates

**S4A-D37 · Qué pruebas de arquitectura se amplían y en qué Rojo.** La tabla completa está en la sección 7. Regla: la prueba que un slice rompe se corrige en el **Rojo de ese mismo slice**, porque `tests/architecture` corre en todos los gates (A-5) y la que no se prevé cuesta un ciclo.

**S4A-D38 · Migraciones (C11).**
- `0012_worker_job_runs` (`down_revision = "0011_payments_immutability"`): tabla `worker.job_runs` con `id uuid PK`, `job_name text NOT NULL` (CHECK de forma: minúscula inicial, minúsculas, dígitos y guion bajo, de 2 a 63 caracteres), `run_date date NOT NULL` (fecha de Bogotá), `started_at timestamptz NOT NULL`, `finished_at timestamptz NULL`, `result text NOT NULL` (CHECK en running, ok, error y los estados de backup de US-115 ok_unverified, stale, missing, corrupt, undecryptable, para no editar una migración aplicada en v0.2), `error text NULL`, `details jsonb NOT NULL` con valor por defecto un objeto vacío, `created_at`, `updated_at`, `created_by uuid NOT NULL`, CHECK `finished_at IS NULL OR finished_at >= started_at`; índice único `uq_job_runs_name_date (job_name, run_date)` e índice `ix_job_runs_name_started (job_name, started_at DESC)`. Sin triggers (se actualiza al cerrar el intento), sin `__audited__`. `downgrade`: índices y tabla (el esquema `worker` es de `0001`, cuyo `DROP SCHEMA ... RESTRICT` falla si queda algo).
- `0013_audit_verifications` (`down_revision = "0012_worker_job_runs"`): tabla `audit.verifications` con `id`, `started_at` y `finished_at` (`timestamptz NOT NULL`), `through_seq bigint NOT NULL` (CHECK mayor o igual a 0), `rows_checked bigint NOT NULL` (CHECK mayor o igual a 0), `ok boolean NOT NULL`, `broken_at_seq bigint NULL`, `triggered_by uuid NOT NULL`, `source text NOT NULL` (CHECK en api o cli), `created_at`, `updated_at`, `created_by`; CHECKs de coherencia (ok sin `broken_at_seq`, no ok con `broken_at_seq`) y `started_at <= finished_at`; índice `ix_verifications_finished_at (finished_at DESC)`; triggers `verifications_forbid_mutation` (antes de UPDATE o DELETE, por fila) y `verifications_forbid_truncate` (antes de TRUNCATE, por sentencia) sobre la función **existente** `audit.forbid_mutation()` de `0002` (no se redefine), ambos habilitados con ENABLE ALWAYS (S3-D49). `downgrade`: triggers, índice y tabla; nunca la función.
- Pruebas: `tests/migrations/test_0012_worker_job_runs.py` (columnas y nulabilidad, cada CHECK con SQL crudo 23514, índice único 23505, la revisión cuelga de `0011_payments_immutability`, `downgrade`) y `test_0013_audit_verifications.py` (lo mismo, más `UPDATE`, `DELETE` y `TRUNCATE` rechazados, triggers con `tgenabled` en A, función usada igual a `audit.forbid_mutation`, y que siguen disparando bajo `session_replication_role = replica`). `tests/migrations/test_0011_payments_immutability.py:112-117` pasa de `0011` es la cabeza única a está en la cadena de head (como `test_0010_payments.py:194`) en el Rojo de **B1**; `test_0012...` hace lo mismo en el Rojo de B3. `tests/core/test_migrations.py` (ciclo y cabeza única) y `test_triggers_siempre_activos.py` (tupla de `verifications`) cubren el resto.
- Operación: `pg_dump -Fc` de `apex-db-1` a `docs/scratch/sprint-04a-antes-0012.dump` y `-0013.dump` antes de aplicar cada una (`*.dump` ya está en `.gitignore`; se borran al cerrar). Cada archivo de migración se prueba contra `db_test` antes de dejarlo en `migrations/versions` o con el api parado: el api de desarrollo monta `../api/migrations` y corre `upgrade head` en cada reinicio de `--reload`. Después de cada migración, `restart api` (o `alembic upgrade head` explícito). `alembic heads` devuelve una sola cabeza en los gates de B1 y B3. Ciclo `upgrade head`, `downgrade -1`, `upgrade head` en B1 y B3. `RUNBOOK.md` §6 gana las dos entradas.

**S4A-D39 · Cobertura (M-6), tamaños y momento de `run-gates.sh` (hallazgo 15, pregunta 16; C12).**
- El `omit` de `pyproject.toml` (`*/app/cli.py` y `*/app/worker/*`) se quita en el **Verde de B1**, junto con las pruebas de `tests/worker`. Se añaden `tests/cli/test_export_openapi_cli.py` y `test_init_keys_cli.py` (por `CliRunner`) en el Rojo de B1 para que `cli.py` no baje la cobertura al entrar (hoy esas dos rutas solo las cubren `tests/crypto/test_init_keys.py` y `tests/core/test_openapi_export.py`). `scripts/workflow/README.md` (Cobertura M-6) y el comentario de `pyproject.toml` se actualizan.
- `run-gates.sh` (cobertura sin `omit`, pruebas de migraciones y arquitectura) se corre **al cerrar B2 y al cerrar B3** (CLI `verify-audit`), y al cerrar el sprint. Es el único gate que atrapa `test_0011...:117` y las pruebas de `tests/migrations`.
- Tamaños (800 por archivo, 50 por función): `core/audit.py` ~530 (solo `verify_chain`), `core/audit_verify.py` ~250, `audit/` partido (S4A-D18), `cli.py` ~660, `members/service.py` (483) recibe solo re-exportaciones (historial y contacto van en privados), `plans/service.py` (314) ~480 con cuatro casos de uso y helpers (si pasa de 600 se parte `plans/changes.py`, privado). Funciones largas probables (`recompute_statuses`, `run_verification`, `movement_phrase`, `verify`) se parten desde el diseño.

**S4A-D40 · `slice-gate.sh`, marcador y fábrica.** Los nombres `worker`, `cli`, `core/jobs`, `core/audit`, `core/audit_verify`, `audit`, `members`, `memberships`, `plans`, `dashboard`, `web/system`, `web/dashboard`, `web/members`, `web/plans` y `web/shared` resuelven todos por el mapeo genérico (S3-D61: el script no cambia) **una vez que existen** los directorios o archivos: el Rojo de B1 crea `api/src/app/worker/__init__.py`, `core/jobs.py` y `tests/worker/__init__.py`; B3 crea `core/audit_verify.py`; B8 crea `modules/dashboard/__init__.py` y `tests/dashboard/__init__.py`; `web/src/features/dashboard/` ya existe. El gate de un módulo no corre `tests/migrations`, el ciclo de Alembic ni `-m perf`: se pasan por lista o aparte (cada slice lo dice). `audit_chain_factory` no existía y nace en B3 (sección 8).

**S4A-D41 · Correcciones documentales de los desgloses (T-DOC, C13).** En el primer checkpoint (S4A-W0-1) se corrigen: `verify_chain(start_prev_hash, start_seq)` por la firma real ampliada (S4A-D11); `bus.op_context`, `SensitiveFieldRevealed` y `SYSTEM_ACTOR` (US-077) por `detail._decrypt_fields` más `audit.record` más `SYSTEM_USER_ID`; `auth.service.get_by_email` (US-105) por `cli.resolve_actor`; `ids_by_email(q)` parcial por `search_user_ids`; `names_for -> UserRef` por `user_refs_for`; `refs_for -> MembershipRef(member_id, plan_id)` (US-110) por el real, con nombres y fechas y sin `plan_id`; `Depends(Clock)` por `current_clock()`; `table_name="verifications"` por `audit.verifications`; tablas `members`, `memberships` y `payments` por los nombres `esquema.tabla`; `by: Actor` (US-080, US-081, US-082) por `get_actor()`; `broken_seq` por `broken_at_seq`; `slow` por `perf`; `test_service_import_cycles.py` y `ALLOWED_LAZY` (US-082) por `test_service_import_graph.py` y `LAZY_IMPORT_WHITELIST`; `command: uv run` y `depends_on: api` (US-113) por el `compose.yml` real; `HomePage.tsx` por `InicioPage.tsx`; `0014_audit_subject_member` (US-106) por ya existe en `0002`; la frase de US-094 de lecturas del estado guardado por S4A-D1; el healthcheck por `job_runs` por S4A-D8; US-041 como dueña de `display_name` por S4A-D19; `WORKER_TZ` y `WORKER_DAILY_HOUR` (US-113) por constantes (S4A-D5). `CLAUDE.md` se corrige en el mismo cambio: estructura real de `core/` (`jobs.py`, `alerts.py`, `audit_verify.py`), de `worker/` (`schedule`, `registry`, `runner`, `runtime`, `main`, `jobs/`), `modules/audit` partido, comandos `verify-audit` y `recompute-memberships`, y `/health` lee `job_runs` pasa a v0.2. `SPRINT-04A.md` añade: `0014` no se crea; `-m perf`; `GET /audit` con sus filtros reales.

**S4A-D42 · Orden de slices y reconstrucción.** Orden sin cambio respecto a `SPRINT-04A.md`: W0-1, B1, W0-2, B2, B3, B4, B5, B6, B7, B8, F1, F2, F3, F4, con tres precisiones: (a) `user_refs_for` nace en B4 y lo usan B5 y B8; (b) F1 necesita B3 y B4, F2 necesita B5, F3 necesita B8 y F4 necesita B7; el front se ejecuta por disponibilidad del backend (como S3-D66); (c) reconstruir `apex-api:local` y `apex-web:local` con buildx solo en W0-2, al cerrar el backend (antes de los E2E del stack) y en `verify-delivery`; entre tanto `worker` y `tools` ven el código por bind (S4A-D9). `web` no tiene bind: F1 a F4 exigen reconstruir para verse en `:8180` y para el proyecto `stack`.

## 2. Reglas transversales

### Backend
1. Routers: validan, declaran rol con `AdminDep` o `StaffDep`, llaman a **un** service y devuelven; cero `select` en routers. Todo con `SessionDep`, `dependencies=[Depends(no_store)]` y `responses_for(...)` por ruta; el 429 se declara por ruta (nunca en el `APIRouter`). Listas con `Annotated[PageParams, Depends()]`, `q: SearchQuery = None` y `Page[T]`; ninguna lista devuelve un arreglo suelto.
2. Un módulo solo llama a otro por su `service.py` (más `schemas.py` y `exceptions.py`); nunca `models`, `router` ni privados. Aristas nuevas: `members -> audit` (B5), `dashboard -> audit, auth, members, memberships, payments` (B8) y la perezosa `plans -> memberships` (B7, ya en la lista blanca de G-03). `audit -> auth` y `memberships -> settings` ya existen.
3. Eventos: dataclasses congeladas con `kw_only` que heredan `DomainEvent`, declaradas en el privado `events.py` del emisor y re-exportadas por su `service.py` (L7); sin PII ni texto libre. Nuevos: `MembershipExpiring`, `MembershipExpired` (sin suscriptores), `PlanUpdated(plan_id, changed_fields)` y `PlanDeactivated(plan_id)`.
4. Todo caso de uso async recibe `session` primero; actor con `get_actor()`; hora con `current_clock()`; hoy con `current_clock().today_bogota()`. El worker y la CLI fijan el actor con `actor_scope` y `batch_scope` (`unit_of_work` en la CLI).
5. Orden único de candados (D3, S3-D95): socio, `FOR SHARE` del plan, fila de la membresía (`sell.lock_membership`), fila del pago, cadena de auditoría (la toma el hook al hacer flush). Un proceso por lotes confirma una transacción por socio. Candado de verificación `4_270_003` aparte (S4A-D12).
6. Las tablas auditadas se escriben por ORM (el hook las ve). `worker.job_runs` y `audit.verifications` no son auditadas y se escriben con Core o ORM sin hook; la segunda ya queda en la cadena como fila `verify`.
7. Cada migración tiene su `tests/migrations/test_<revision>.py` y entra al ciclo de Alembic; cada `downgrade` es simétrico y nunca toca el esquema ni una función de otra migración.
8. Ningún `message` ni log lleva documento, teléfono, correo, referencia de pago ni motivo. El worker y la CLI registran solo conteos y tipos de error. La auditoría no muestra material de llave (los blobs `apx1.` con `key_id` no lo son).
9. Dinero siempre `int` COP. Fechas: `date` para vigencias, `timestamptz` para instantes, hoy de Bogotá.

### Front
1. TanStack Query para todo dato del servidor; React Hook Form y Zod 4 (jitless, `core/zodSetup.ts`) para todo formulario; listas paginadas en el servidor con `limit` y `offset`. El texto `q` vive en memoria, nunca en la URL (S2-D41).
2. Por feature: `api.ts`, `schemas.ts`, `*Errors.ts`, `*Links.ts`, `components/`, `pages/`; los tipos salen de `core/api/types.ts` generado. Nada cruza entre features (`boundaries.test.ts`): lo compartido vive en `shared/`.
3. Mutaciones por `useSensitiveMutation`; sin rol comparado con literal fuera de `permissions.ts` (`useCan`, `<Can>`); sin `console`, `fetch` ni `Intl` fuera de `core/api` y `core/i18n`; solo variables de `tokens.css`.
4. Todo faltante del diseño lleva `// DESIGN-GAP:` y su fila en `BRECHAS.md` §11 (S4A-D36).

### Pruebas
1. TDD por slice: Rojo con stubs que lanzan `NotImplementedError`, Verde y gate. Puras sin base; de service con `session`; de router con `app_http`, `usuario_real` y `cabeceras`; concurrencia con `dos_sesiones`.
2. Importar los services al nivel del archivo de prueba o en `conftest`: `restaurar_bus` (autouse) restaura el bus al terminar cada prueba. Aplica a `tests/worker` y `tests/cli`.
3. El reloj de las pruebas es `reloj` (2026-10-21T15:00Z); los casos de vencimiento usan `reloj.advance(days=)` hasta 2026-10-24, 2026-11-01 y 2026-11-03.
4. Rendimiento con `@pytest.mark.perf`.

### Estructura de archivos nueva o tocada

```
api/src/app/
  core/
    jobs.py            B1  JobRun, JobRunView, claim_run, finish_run, last_run
    alerts.py          B1  AlertSink, register_sink, alert, LogAlertSink
    audit.py           B3  verify_chain ampliada, VerifyResult con last_seq y last_hash
    audit_verify.py    B3  AuditVerification, run_verification, format_verify_message, claves y constantes
  worker/
    __init__.py  main.py  registry.py  schedule.py  runner.py  runtime.py      B1
    jobs/__init__.py                                                          B1
    jobs/expirations.py                                                       B2
  cli.py               B2 recompute-memberships, B3 verify-audit
  modules/
    memberships/  expirations.py (privado), events.py, rules.py, queries.py, service.py   B2, B7
    audit/        router.py schemas.py exceptions.py service.py (fachada)
                  verify.py (B3)  queries.py diff.py (B4)
    auth/         users.py schemas.py service.py          B4: user_refs_for, search_user_ids, UserRef
    members/      contact.py (B6), router.py service.py   B5: history y GET /members/{member_id}/audit
    plans/        schemas.py exceptions.py service.py router.py   B7
    dashboard/    __init__.py router.py schemas.py service.py     B8
api/migrations/versions/  0012_worker_job_runs.py  0013_audit_verifications.py
api/tests/
  worker/          test_schedule.py test_runner.py test_main.py test_jobs_core.py test_expirations.py
  dashboard/       test_pure.py test_service.py test_last_movements.py test_router.py test_perf.py
  audit/           test_verify*.py test_filters.py test_list*.py test_diff.py test_get.py
                   test_router_*.py test_history_fields.py test_member_history.py test_recent.py
  integration/     test_rn04_plan_price_change.py test_plan_deactivation_with_memberships.py
  factories/       audit_chain.py (fábrica de cadenas)
  architecture/    test_worker_boundaries.py test_crypto_bus_importers.py test_audit_subject.py
                   test_read_modules.py test_expirations_lock_order.py
infra/             compose.yml (worker), compose.dev.yml (binds de worker y tools)
scripts/ci/        test_compose_config.sh, compose-smoke.sh
web/src/features/  system/ (auditoría), members/ (historial), dashboard/ (inicio), plans/ (acciones)
web/src/shared/    lib/encryptedBlob.ts, lib/audit-labels.ts, ui/HistoryAside.tsx
```

## 3. Orden de ejecución y dependencias

Orden: W0-1, B1, W0-2, B2, B3, B4, B5, B6, B7, B8, F1 a F4 (el front por disponibilidad del backend). Un checkpoint por slice (`scripts/workflow/checkpoint-commit.sh`); `run-gates.sh` al cerrar B2, B3 y el sprint.

Dependencias duras:
- B1 antes de W0-2 (N-3: el perfil `worker` se quita solo cuando existe `app/worker/main.py`) y antes de B2 y B3 (`core/jobs.py` y `0012`; `0013` cuelga de `0012`).
- B2 necesita B1 (el job corre sobre el runner). B3 necesita solo `0012` aplicada; el ciclo de Alembic de B3 prueba ambas.
- B4 necesita B3 (`PRIVATE_HELPERS["audit"]`, router, `audit_chain_factory`) y crea `user_refs_for` y `search_user_ids` en `auth`. B5 necesita B4 (`diff` e `history_fields`). B6 es independiente (solo `members`). B7 necesita `count_active_by_plan` y crea `counts_active_by_plans`. B8 necesita B4 (`recent`, `user_refs_for`), `memberships.summary`, `payments.summary` y `refs_for`.
- Front: F1 necesita B3 y B4; F2 necesita B5; F3 necesita B8; F4 necesita B7.
- Archivos compartidos que más de un slice toca: `tests/conftest.py` (limpiezas: B1 y B3), `test_audited_tables.py` (B1, B3, B5), `test_service_import_graph.py` (B5, B7, B8), `test_error_codes_per_route.py` (B3, B7), `test_audit_module.py` (B3, B4, B8), `tests/architecture/_imports.py` (B2, B3, B4, B6), `main.py` (`MODULES`: B8), `cli.py` (B2, B3), `routeTable.ts`, `routes.reference.ts` y `routes.test.ts` (F1, F2), `audit-labels.ts` (F2), `docs/openapi.json` y `types.ts` (B3, B4, B5, B7, B8).

## 4. Backend, slice por slice

### S4A-W0-1 · Worker en Compose, solo preparación (C2, C13)

- Línea base: los cuatro servicios sanos, `alembic current` en `0011_payments_immutability`, `run-gates.sh` en verde sobre `main`; se anota en `docs/scratch/sprint-04a.md` (cuaderno del sprint, guardarraíl 5). `pg_dump -Fc` previo a `0012` (S4A-D38).
- `infra/compose.yml`: servicio `worker` con healthcheck (S4A-D8), `depends_on` de `db` y `api` healthy, sin `ports`, **con** `profiles: ["worker"]`; comentario de `:48-50` actualizado.
- `infra/compose.dev.yml`: binds de `src` y `migrations` (solo lectura) en `worker` y en `tools` (S4A-D9).
- `scripts/ci/test_compose_config.sh`: aserciones nuevas del worker (healthcheck, `depends_on` del api, sin `ports`) manteniendo la del perfil.
- T-DOC (S4A-D41): correcciones de los desgloses, `CLAUDE.md`, `SPRINT-04A.md`, `ROUTES.md` y `BRECHAS.md` (§11 inicial con S3-D98 cerrada); copiar S4A-D1 a S4A-D42 a `DECISIONES.md` (sección Sprint 4A) con el cierre de la revisión de diseño previa.
- Gate: `docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml config` válido; `bash scripts/ci/test_compose_config.sh`; `bash scripts/ci/compose-smoke.sh` **sin** el perfil (no levanta el worker).

### S4A-B1 · Proceso worker programado, `core/jobs.py` y `0012` (US-113; C1, C11, C12)

Crear:
- `api/migrations/versions/0012_worker_job_runs.py` (S4A-D38).
- `core/jobs.py`: `JobRun`, `JobRunView`, `claim_run`, `finish_run`, `last_run` (S4A-D3). `core/alerts.py` (S4A-D7).
- `worker/schedule.py`: `WORKER_TIMEZONE`, `DAILY_HOUR`, `DAILY_MINUTE`, `next_run(now_utc, tz, hour, minute) -> datetime` y `should_run(job_name, run_date, now_local, scheduled_at, previous) -> bool` (verdadero solo si ya pasó la hora del día y no hay fila, o la fila está running desde hace más de 6 horas; un error no se reintenta solo).
- `worker/registry.py`: `JobSpec` (dataclass congelada), `register(registry, spec)` pura que devuelve un registro nuevo, y `get_registry()`. `worker/jobs/__init__.py`: `JOBS` con `expirations` (en B1 apunta a un stub que lanza `NotImplementedError`; B2 pone el real).
- `worker/runner.py`: `JobContext(session_factory, today, clock)`, `JobResult(ok, details)`, `JobOutcome`, `async run_job(spec, *, clock, session_factory) -> JobOutcome`, `async run_cycle(registry, ...) -> list[JobOutcome]`.
- `worker/runtime.py`: `HEARTBEAT_PATH`, `async worker_runtime(settings)` (context manager), `async wait_for_database(settings, *, sleep, max_wait_s=60)`.
- `worker/main.py`: `build_parser()`, `async run_once(job, date, ...) -> int`, `async serve(...)`, `main(argv=None) -> int` (S4A-D4 y D6).
- `tests/worker/__init__.py`, `test_schedule.py`, `test_runner.py`, `test_jobs_core.py`, `test_main.py`; `tests/core/test_alerts.py`; `tests/migrations/test_0012_worker_job_runs.py`; `tests/architecture/test_worker_boundaries.py`; `tests/cli/test_export_openapi_cli.py` y `test_init_keys_cli.py`.

Modificar:
- `migrations/env.py`: importar `app.core.jobs` para `target_metadata`.
- `pyproject.toml`: quitar `omit`; `scripts/workflow/README.md` y el comentario.
- `tests/conftest.py`: `LIMPIAR_JOB_RUNS` (borrado de `worker.job_runs`, con `to_regclass`) en `LIMPIEZA_DE_SESION`, en el `finally` de `dos_sesiones` y en `limpiar_tras_dos_sesiones`.
- Pruebas de arquitectura (C1): `test_audited_tables.py` (entrada `worker.job_runs` en `EXCLUIDAS` con motivo bitácora operativa sin auditoría, e importar `app.core.jobs` en `_cargar_modelos`), `test_core_import_direction.py` (nuevas: `core/jobs` y `core/alerts` no importan `app.modules`; solo `app.worker.*` importa `app.core.jobs`; `core/audit.py` no lo importa; sin ciclo con `core/health.py`) y `tests/migrations/test_0011_payments_immutability.py:112-117` (está en la cadena de head).

Rojo (casos clave):
- `test_schedule.py`: `next_run` desde 2026-10-21T11:59Z da 12:00Z del mismo día (07:00 Bogotá) y desde 12:00:01Z da el día siguiente; `today_bogota` a 2026-10-22T01:00Z da 2026-10-21; `should_run` sin fila, con ok del día, con error del día (no reintenta), con running viejo (sí) y antes de la hora (no).
- `test_jobs_core.py` (base real, `dos_sesiones` donde hay commit): `claim_run` crea la fila running; el segundo reclamo con running vigente da `None`; tras `finish_run` ok, un nuevo reclamo del mismo día reutiliza la fila y `details.attempts` tiene 2; un running de más de 6 horas se reclama; dos reclamos concurrentes dejan una sola ejecución; `finish_run` con error guarda el tipo y no datos; `last_run`; `created_by` es el actor.
- `test_runner.py` (`FrozenClock`, dos jobs de prueba, uno que lanza): el segundo corre, la escritura del que falla se revierte, `job_runs` queda con error y ok, `alert` se llama con el código job_failed, el log no contiene datos personales; `timeout_s` bajo marca error; el actor de las escrituras del job es `SYSTEM_USER_ID`; reinicio a las 09:00 de Bogotá con el ciclo hecho no ejecuta nada y sin ciclo hecho ejecuta una sola vez.
- `test_main.py`: `--run-once` con un job de prueba da 0, con fallo 1, con job inexistente 2 y lista los registrados, con corrida vigente 3; `--date` instala un `FrozenClock` (`run_date` es esa fecha) y con `ENV=production` y fecha distinta de hoy da 2; `--status` imprime el último intento; `wait_for_database` con un `sleep` falso respeta 1, 2, 4 y el tope de 60 s; `serve` con la parada ya disparada arranca el scheduler, escribe el latido y sale 0; `load_module_services` queda cargado (el gate de pagos está registrado, como en `test_gates_registered.py`).
- `test_worker_boundaries.py`: ningún archivo de `app/worker/**` ni `cli.py` importa `models`, `router` ni privados de un módulo, ni escribe `text(`; control con fuente falsa que debe fallar.
- `test_0012_worker_job_runs.py` (S4A-D38) y el ciclo de Alembic.

Gate: `bash scripts/workflow/slice-gate.sh worker tests/worker/test_schedule.py tests/worker/test_runner.py tests/worker/test_main.py`, `bash scripts/workflow/slice-gate.sh core/jobs tests/worker/test_jobs_core.py tests/core/test_alerts.py tests/migrations/test_0012_worker_job_runs.py`, `bash scripts/workflow/slice-gate.sh cli tests/cli/test_export_openapi_cli.py tests/cli/test_init_keys_cli.py`, más el ciclo de Alembic y `alembic heads` con una sola cabeza.

### S4A-W0-2 · Activar el worker (US-005 criterio diferido; C2)

- `infra/compose.yml`: quitar `profiles: ["worker"]` y su comentario.
- `scripts/ci/test_compose_config.sh`: invertir `:58` (worker no tiene perfil); la bandera `--profile worker` de los comandos queda inofensiva.
- `scripts/ci/compose-smoke.sh`: paso del worker (S4A-D9). Reconstruir `apex-api:local` con buildx (RUNBOOK §7) antes de `up -d --no-build worker`.
- Verificar con `grep` que `web/tests/e2e/stack/helpers/stack.ts` no cuenta `worker.job_runs`; documentar en RUNBOOK §7 el worker (comando, `--run-once`, `--status`, `--date`, latido) y las dos filas nuevas de §6.
- Gate: `docker compose ... config`; `bash scripts/ci/test_compose_config.sh`; `bash scripts/ci/compose-smoke.sh` con el worker en marcha, healthy y sin reinicios; `docker compose ... run --rm worker python -m app.worker.main --run-once expirations` con código 0 y fila en `worker.job_runs`.

### S4A-B2 · Job diario de vencimientos y `recompute-memberships` (US-094; C3, C12)

Crear:
- `memberships/expirations.py` (privado; a `PRIVATE_HELPERS["memberships"]`): constantes `RECOMPUTE_PAGE = 200` y `MAX_BUSY_RETRIES = 2`, `RecomputeSummary`, `async recompute_statuses(session_factory, *, today: date, page_size: int = RECOMPUTE_PAGE) -> RecomputeSummary` y los auxiliares `_candidate_member_ids(session, today, expiring_days, after)` y `_recompute_member(session_factory, member_id, today, expiring_days)` (S4A-D2). Cada función de menos de 50 líneas.
- `memberships/events.py`: `MembershipExpiring` y `MembershipExpired`. `memberships/rules.py`: `transition_event(old, new)`. `memberships/service.py`: re-exporta `recompute_statuses`, `RecomputeSummary` y los dos eventos (a `__all__`); **no** suscribe nada a ellos.
- `worker/jobs/expirations.py`: `async run(ctx)` llama `memberships.service.recompute_statuses(ctx.session_factory, today=ctx.today)` y devuelve los conteos en `details` (ok si `busy_omitidos + errores == 0`); `JOBS` apunta a él.
- `cli.py`: comando `recompute-memberships` (S4A-D4 y D15).
- `tests/worker/test_expirations.py`, `tests/cli/test_recompute_memberships.py`, `tests/memberships/test_recompute_lock_order.py`, `tests/architecture/test_expirations_lock_order.py`.

Modificar:
- `tests/architecture/_imports.py`: `PRIVATE_HELPERS["memberships"]` suma `expirations`; `test_no_cross_models.py:137` compara el conjunto exacto.
- `test_handlers_no_new_locks.py`: `SUSCRIPTORES_ESPERADOS` suma `MembershipExpiring` y `MembershipExpired` con lista vacía (S4A-D1). `HANDLERS_ESPERADOS` no cambia.
- `tests/memberships/test_rules.py`: `test_transition_event`.

Rojo (casos clave):
- `test_rules.py::test_transition_event`: active a expiring, active a expired, expiring a expired, frozen a expiring, frozen a active, active a frozen y sin cambio.
- `test_expirations.py` (`FrozenClock`, base real, `actor_scope(SYSTEM_USER_ID)`): 2026-10-24 active a expiring con un `MembershipExpiring`; 2026-11-01 expiring a expired con un `MembershipExpired`; **dos corridas el mismo día**: un solo evento y una sola fila update de auditoría; 2026-11-03 sobre active con fin 2026-10-31 da expired y solo `MembershipExpired`; una congelación que empieza hoy da frozen y una que terminó ayer da active o expiring según el fin; `pending_payment`, `cancelled` y `expired` guardados intactos; 2026-11-01 02:00Z sigue en el día 31 de Bogotá y la membresía sigue expiring; auditoría con `user_id = SYSTEM_USER_ID` y `subject_member_id`; `expiring_days = 3` desde settings; **paridad**: tras el job, el `status` guardado es igual a `compute_status` para toda candidata; el resumen (`memberships.summary`) es el mismo antes y después del job; ningún evento se suscribe a `_mark_summary_dirty`.
- Error por socio: con `page_size = 2` y un handler de `MembershipExpiring` que lanza solo para un socio, los demás quedan actualizados, ese no, `errores = 1` y el log no contiene nombres ni documentos. Ocupación: una sesión que sostiene `lock_member` del socio con `lock_timeout` bajo da `busy_omitidos = 1` tras los reintentos y el ciclo sigue.
- `test_recompute_lock_order.py` (`dos_sesiones`): el job frente a `freeze`, `cancel`, `sell` y `register` del mismo socio, simultáneos, sin interbloqueo sin resolver (a lo sumo un 503 busy en el api y un reintento en el job); el resultado final es coherente (la anulación gana sobre el recálculo: una `cancelled` no vuelve a otro estado).
- `test_expirations_lock_order.py` (por AST): en `expirations.py` no hay `with_for_update` ni funciones con prefijo on_; dentro de `_recompute_member` la primera llamada a `lock_member` ocurre antes de `lock_membership` y esta antes del primer `flush`.
- Con el marcador perf en `test_expirations.py`: 1.000 socios y 3.000 membresías en menos de 60 s.
- `test_recompute_memberships.py` (CliRunner): `--date` y `--as` (actor de auditoría = el usuario indicado), código 0 sin errores y 1 con errores, `--as` inexistente da 2, `--date` con `ENV=production` y fecha distinta de hoy da 2, la salida solo trae conteos.

Gate: `bash scripts/workflow/slice-gate.sh memberships tests/memberships/test_rules.py tests/memberships/test_recompute_lock_order.py`, `bash scripts/workflow/slice-gate.sh worker tests/worker/test_expirations.py`, `bash scripts/workflow/slice-gate.sh cli tests/cli/test_recompute_memberships.py`, más `cd api && uv run pytest -m perf tests/worker/test_expirations.py -q`. **Al cerrar B2: `bash scripts/workflow/run-gates.sh`** (cobertura sin `omit`, C12). Demo: `docker compose ... run --rm worker python -m app.worker.main --run-once expirations --date 2026-11-01` y de nuevo (sin filas nuevas de auditoría en la segunda).

### S4A-B3 · Verificar la cadena desde la API y desde la CLI (US-104, US-105; C4, C11, C12)

Crear:
- `api/migrations/versions/0013_audit_verifications.py` (S4A-D38).
- `core/audit_verify.py` (S4A-D12): `AuditVerification`, `VERIFY_BATCH_SIZE`, `AUDIT_VERIFY_LOCK_KEY`, `run_verification`, `format_verify_message`; sentencias del candado como constantes de módulo.
- `audit/verify.py` (privado): `SYNC_VERIFY_MAX_ROWS = 50_000`, `acquire_verify_lock()` que devuelve la conexión con el candado o `None`, `verify(session, *, by)` que devuelve `Finished(result)` o `Started(last)`, `last_verification(session)` y la tarea en segundo plano con su conjunto de referencias.
- `audit/schemas.py`: `VerifyResultOut`, `VerifyStartedOut`. `audit/exceptions.py`: `AuditError` base y `VerificationRunning` (409 `verification_running`). `audit/router.py`: `GET /audit/verify/last` y `POST /audit/verify`, con `dependencies=[Depends(no_store)]` y `AdminDep`. `audit/service.py`: re-exporta `verify` y `last_verification`.
- `cli.py`: comando `verify-audit` (S4A-D15).
- Pruebas: `tests/factories/audit_chain.py`, `tests/core/test_verify_chain.py`, `tests/core/test_format_verify_message.py`, `tests/audit/test_verify.py`, `test_verify_concurrency.py`, `test_verify_performance.py`, `test_router_verify.py`, `tests/cli/test_verify_audit.py`, `tests/migrations/test_0013_audit_verifications.py`.

Modificar:
- `core/audit.py`: `verify_chain` con `start_prev_hash` y `start_seq` y `VerifyResult` con `last_seq` y `last_hash` (S4A-D11).
- `migrations/env.py` (importar `app.core.audit_verify`).
- `tests/architecture/_imports.py`: `PRIVATE_HELPERS["audit"]` es el conjunto con `verify`; `test_no_cross_models.py:137,145,152` comparan el conjunto exacto.
- `test_audit_module.py`: la prueba del router vacío (`:69-72`) pasa a: audit tiene exactamente las rutas `POST /audit/verify` y `GET /audit/verify/last` y sigue sin `models.py`; el router de `audit` lleva `no_store`.
- `test_audited_tables.py`: `EXCLUIDAS` suma `audit.verifications` (motivo: su resultado ya entra a la cadena como fila verify) e importa `app.core.audit_verify`.
- `test_no_physical_delete.py`: `MODELOS` y `TABLAS` suman `AuditVerification` y `audit.verifications`.
- `test_sql_literals_constant.py`: fija también `AUDIT_VERIFY_LOCK_KEY == 4_270_003`.
- `test_error_codes_per_route.py`: `CON_LIMITE` suma `POST /api/v1/audit/verify`; `test_user_limits_catalog.py` y `test_writes_have_user_limit.py` lo exigen.
- `tests/migrations/test_0012_worker_job_runs.py`: de cabeza única a está en la cadena; `test_triggers_siempre_activos.py`: tupla de `verifications`.
- `tests/conftest.py`: `LIMPIAR_VERIFICATIONS` (deshabilitar triggers de usuario, borrar, volver a habilitar con ENABLE ALWAYS por nombre, como `LIMPIAR_PAYMENTS`) **antes** de limpiar `audit.audit_log` en `LIMPIEZA_DE_SESION`, en el `finally` de `dos_sesiones` y en `limpiar_tras_dos_sesiones`.
- `docs/RUNBOOK.md`: `0012` y `0013`, el comando `verify-audit`, el candado y los códigos de salida.

Rojo (casos clave):
- `test_verify_chain.py` (puras): cadena vacía, una fila, íntegra de 50, fila 1 alterada, del medio, última, fila borrada (el `seq` siguiente es el reportado), `prev_hash` manipulado, columna espejo distinta, y verificación en dos lotes con `start_prev_hash` y `start_seq` igual a la de una vez; los valores por defecto conservan `test_audit_chain.py`.
- `test_format_verify_message.py`: íntegra (texto y código 0) y rota en el seq 42 (texto y código 1).
- `test_verify.py` (base real, `audit_chain_factory`): cadena de 5.000 filas da ok y `rows_checked = 5000`; la fila 1234 alterada (con `DISABLE TRIGGER USER` dentro de la transacción de prueba) da `broken_at_seq = 1235`; cola borrada da `broken_at_seq = last_seq + 1`; cada verificación deja una fila en `audit.verifications` y una entrada verify con `table_name = audit.verifications` que entra a la cadena (una segunda verificación sigue íntegra); una transacción auditada revertida no deja huecos; la verificación no cambia ninguna fila de `audit_log` (hash de la tabla antes y después); `UPDATE` sobre `audit.verifications` rechazado.
- `test_verify_concurrency.py` (`dos_sesiones`): con el candado tomado por otra conexión, `verify` lanza 409; con `SYNC_VERIFY_MAX_ROWS` bajado por monkeypatch devuelve Started, la tarea termina dejando la fila y libera el candado en `finally` (también si falla); mientras corre, otra petición responde.
- `test_verify_performance.py` (perf): 100.000 filas, verificación completa en menos de 60 s (y la medida que decide el umbral de S4A-D13).
- `test_router_verify.py`: 200 admin con resultado, 202 running, 409 `verification_running`, 429 a la petición 31 del minuto, `GET /audit/verify/last` con y sin verificaciones, 403 coach, 401 sin token; el 202 aparece en el OpenAPI.
- `test_verify_audit.py` (CliRunner): íntegra da 0 y el texto; fila 42 alterada da 1; la entrada verify lleva `user_id = SYSTEM_USER_ID` y `after.source = cli`; con `--as` la entrada y `triggered_by` llevan ese usuario; `--as` inexistente da 2; base caída (puerto cerrado) da 2 sin la URL en la salida; `--wait-timeout` corto con el candado tomado da 2; la salida no contiene ningún valor de before o after; ninguna lectura de más de `VERIFY_BATCH_SIZE` filas.
- `test_0013_audit_verifications.py` (S4A-D38) y el ciclo de Alembic.

Gate: `bash scripts/workflow/slice-gate.sh audit tests/audit/test_verify.py tests/audit/test_verify_concurrency.py tests/audit/test_router_verify.py tests/migrations/test_0013_audit_verifications.py`, `bash scripts/workflow/slice-gate.sh core/audit_verify tests/core/test_verify_chain.py tests/core/test_format_verify_message.py`, `bash scripts/workflow/slice-gate.sh core/audit tests/core/test_audit_chain.py`, `bash scripts/workflow/slice-gate.sh cli tests/cli/test_verify_audit.py`, más `pytest -m perf tests/audit/test_verify_performance.py`, el ciclo de Alembic y `alembic heads` con una sola cabeza. `export-openapi` y `gen:api`. Primera prueba con datos reales: `verify-audit` contra `apex-db-1` (4.500 filas): si da rota, **parar**: es un hallazgo real de la cadena. **Al cerrar B3: `bash scripts/workflow/run-gates.sh`** (C12).

### S4A-B4 · Consultar la auditoría y ver el detalle (US-102, US-103; C5, C9)

Crear:
- `audit/queries.py` (privado): `list(session, filters, page)`, `get(session, seq)`; `audit/diff.py` (puras): `diff(before, after)`, `FieldChange`; `audit/schemas.py`: `AuditRow`, `AuditDetail`, `FieldChange`; `audit/exceptions.py`: `AuditEntryNotFound` (404 `audit_entry_not_found`); `audit/router.py`: `GET /audit` y `GET /audit/{seq}` (después de `/audit/verify/last`).
- `auth/schemas.py`: `UserRef`; `auth/users.py` y `auth/service.py`: `user_refs_for` y `search_user_ids` (S4A-D16 y D19).
- Pruebas: `tests/audit/test_filters.py`, `test_list.py`, `test_list_coverage_v01.py`, `test_list_performance.py`, `test_router_list.py`, `test_diff.py`, `test_get.py`, `test_router_get.py`; `tests/auth/test_user_refs.py`.

Modificar:
- `PRIVATE_HELPERS["audit"]` pasa a `verify`, `queries` y `diff` (y `test_no_cross_models.py`).
- `test_audit_module.py`: las rutas esperadas de `audit` pasan a las cuatro.
- `test_error_codes_per_route.py`: el 422 de `GET /audit/{seq}` y de `GET /audit` se declara; sin 429.
- `docs/design/ROUTES.md:89`: el contrato real de `GET /audit` (C13).

Rojo (casos clave):
- `test_filters.py` (puras): `build_audit_filters` por cada filtro, `q` UUID y `q` texto, rango `[from, to)`, acción fuera de la lista rechazada.
- `test_list.py`: cada filtro (incluidos `table` con el nombre `esquema.tabla`, `subject_member_id` y `user_id`); orden `seq` descendente; paginación y `total`; `q` por `record_id` y por correo parcial sin distinguir mayúsculas; filas sin `before` ni `after`; la consulta no modifica `audit_log` (conteo y hash de la última fila iguales).
- `test_list_coverage_v01.py`: una fila en members, plans, memberships, payments, users y settings por sus services y cada insert aparece con usuario y fecha.
- `test_list_performance.py` (perf): 100.000 filas, `limit = 25`, menos de 500 ms con y sin filtros de tabla y usuario.
- `test_diff.py`: insert, update sin cambios (lista vacía), update con dos campos, delete, campo que pasa a null, reveal con `after.field`, y `encrypted` verdadero para valores con prefijo `apx1.`.
- `test_get.py`: socio creado y editado (teléfono y notas) por el service real; la entrada update trae `changes` con phone y notes; `before.phone` y `after.phone` empiezan por `apx1.` y la respuesta serializada no contiene el teléfono en claro; el service no llama al bus (espía); `seq` inexistente da `AuditEntryNotFound`.
- `test_router_list.py` y `test_router_get.py`: 200 admin, 403 coach y member, 401, 422 (`action` desconocida, `limit` 201, `seq` no numérico o cero), 404, y `/audit/verify/last` no cae en `{seq}`.
- `test_user_refs.py`: `user_refs_for` da la parte local del correo y Sistema para `SYSTEM_USER_ID`; `search_user_ids` es parcial, sin distinguir mayúsculas ni tildes, escapa comodines y con `local_part_only` no coincide con el dominio; `names_for` e `ids_by_email` no cambian.

Gate: `bash scripts/workflow/slice-gate.sh audit tests/audit/test_filters.py tests/audit/test_list.py tests/audit/test_list_coverage_v01.py tests/audit/test_diff.py tests/audit/test_get.py tests/audit/test_router_list.py tests/audit/test_router_get.py`, `bash scripts/workflow/slice-gate.sh auth tests/auth/test_user_refs.py`, más `pytest -m perf tests/audit/test_list_performance.py`. `export-openapi` y `gen:api`.

### S4A-B5 · Historial del socio (US-106; C6)

Crear:
- `audit/queries.py`: `member_history(session, member_id, page, q)`; `audit/diff.py`: `history_fields(entry)`; `audit/schemas.py`: `MemberHistoryItem`.
- `members/service.py`: `history(session, member_id, page, q)` (importa `audit.service` arriba); `members/router.py`: `GET /members/{member_id}/audit` con `StaffDep`, `PageParams`, `q: SearchQuery`, `responses_for(404)` y sin 429.
- Pruebas: `tests/audit/test_history_fields.py`, `tests/audit/test_member_history.py`, `tests/members/test_router_member_audit.py`, `tests/architecture/test_audit_subject.py`.

Modificar (todas en el Rojo de B5; C6):
- `test_service_import_graph.py`: `ALLOWED_EDGES` suma `("members", "audit")`; la aserción de `:264` (conjunto vacío de `arriba` para members) pasa a `{"audit"}`; `test_cada_arista_permitida_existe` y el subproceso limpio en los dos órdenes cubren el par nuevo.
- `test_audited_tables.py:186`: la prueba de las congelaciones se renombra y conserva (S4A-D20).
- `test_list_rows_without_sensitive_fields.py` no cambia de código: barre la ruta nueva y exige que `MemberHistoryItem` no tenga `user_email`.
- `test_list_routes_use_page_params.py`: sin cambio (el conjunto se compara con menor o igual); la ruta cumple `PageParams`, `q` y `limit` máximo 200.

Rojo (casos clave):
- `test_history_fields.py`: insert y delete dan lista vacía; update con teléfono y notas da sus nombres sin los `_idx`; reveal con `document` da el campo; nunca `ip`; `canonical` con y sin `subject_member_id` (sin la clave cuando es nula el hash es el de US-015).
- `test_member_history.py`: socia creada por Ana, editada y revelada por Juan, con una membresía vendida y un pago registrado y anulado: el historial trae las entradas de `members.members`, `memberships.memberships` y `payments.payments` en orden descendente con el `subject_member_id` correcto; ninguna entrada de otro socio; ningún valor cifrado ni `reference` ni `void_reason` en la respuesta serializada (se busca el texto en el JSON); una congelación aparece por el update de la membresía; abrir la ficha no agrega entradas; un socio dado de baja devuelve su historial; `q` filtra por el nombre de quien actuó y no por el dominio; la cadena sigue íntegra.
- `test_router_member_audit.py`: 200 coach y admin con el mismo cuerpo, 404 socio inexistente, 422 `limit=0` o 201, 403 member, 401, y el OpenAPI no declara 429.
- `test_audit_subject.py`: `Member`, `Membership` y `Payment` declaran `__audit_subject__` y el atributo existe; `MembershipFreeze` no; `modules/members` no importa `memberships.service` ni `payments.service` en el camino de esta ruta.

Gate: `bash scripts/workflow/slice-gate.sh audit tests/audit/test_history_fields.py tests/audit/test_member_history.py`, `bash scripts/workflow/slice-gate.sh members tests/members/test_router_member_audit.py tests/architecture/test_audit_subject.py`. `export-openapi` y `gen:api`.

### S4A-B6 · Contacto para avisos auditado (US-077; C7)

Crear:
- `members/contact.py` (privado): `Contact`, `InvalidPurpose`, `MemberNotContactable`, `validate_purpose`, `contact_for_notification` (S4A-D21); `members/exceptions.py`: las dos excepciones; `members/service.py`: re-exporta.
- Pruebas: `tests/members/test_validate_purpose.py`, `tests/members/test_service_contact.py`, `tests/architecture/test_crypto_bus_importers.py`.

Modificar:
- `tests/architecture/_imports.py`: `PRIVATE_HELPERS["members"]` suma `contact`; `test_no_cross_models.py` compara el conjunto exacto.
- `test_events_without_pii.py`: sin cambio (no hay evento).

Rojo (casos clave):
- `test_validate_purpose.py`: notify y auth_link válidos; marketing, mask, reveal, export y vacío rechazados.
- `test_service_contact.py` (`bus_listo`, `batch_scope`): devuelve teléfono y correo sembrados; dos filas reveal en la auditoría con `after.purpose = notify`, `subject_member_id` y `user_id = SYSTEM_USER_ID`; dos filas decrypt en `crypto_ops` con `purpose = notify`, el `record_id` del socio y el mismo `batch_id`; propósito inválido no deja filas en `crypto_ops` ni en la auditoría; socio dado de baja o inexistente da `MemberNotContactable` sin descifrar; correo vacío da `None` y una sola fila de cada tipo; con otro actor la fila lleva su `user_id`; `repr(contact)` no contiene el teléfono ni el correo.
- `test_crypto_bus_importers.py`: los importadores reales de `app.core.crypto.bus` y `types` fuera de `core/` son solo los archivos de `members`; falla si `notifications` (cuando exista) lo importa; ningún `router.py` referencia `contact_for_notification`; `test_reveal_single_door.py` sigue verde (la llamada a `types.reveal` es solo la de `_decrypt_fields`).

Gate: `bash scripts/workflow/slice-gate.sh members tests/members/test_validate_purpose.py tests/members/test_service_contact.py tests/architecture/test_crypto_bus_importers.py`.

### S4A-B7 · Editar, activar o desactivar y dar de baja un plan (US-080, US-081, US-082; C8)

Crear / modificar en `plans/`:
- `schemas.py`: `PlanPatch`, `PlanState`, `PlanOut.active_members_count` (S4A-D22 y D25). `exceptions.py`: `PlanHasActiveMemberships(count)` (409 `plan_has_active_memberships`). `service.py`: `merge_plan`, `update`, `set_active`, `deactivate_or_fail`, `_out_with_counts`, eventos `PlanUpdated` y `PlanDeactivated` (con `slots=True`, `kw_only=True`, sin texto libre) y las firmas en `__all__`. `router.py`: `PATCH /plans/{plan_id}` (200, `responses_for(404, 409, 429)`), `POST /plans/{plan_id}/activate` y `/deactivate` (200, `responses_for(404, 429)`), `DELETE /plans/{plan_id}` (204, `responses_for(404, 409, 429)`); las cuatro con `AdminDep` y `enforce_user_limit(request, "admin-write", principal.user_id)`.
- `memberships/queries.py` y `service.py`: `counts_active_by_plans(session, plan_ids)`.
- Pruebas: `tests/plans/test_merge_plan.py`, `test_service_update.py`, `test_router_update.py`, `test_service_set_active.py`, `test_router_set_active.py`, `test_service_deactivate_or_fail.py`, `test_router_delete.py`; `tests/memberships/test_counts_active_by_plans.py`; `tests/integration/__init__.py`, `test_rn04_plan_price_change.py`, `test_plan_deactivation_with_memberships.py`.

Modificar (en el Rojo de B7; C8):
- `test_service_import_graph.py:281-286`: la prueba de plans pasa a `perezosas` de plans igual a `{"memberships"}` y arriba vacío; los importadores de `plans.service` siguen siendo `{"memberships"}` (dashboard no importa plans); nueva prueba de que la perezosa vive en `service.py`, lleva `# lazy: G-03` y `plans` no nombra `Membership`.
- `test_error_codes_per_route.py`: `CON_LIMITE` suma las cuatro rutas de planes; el 422 por `{plan_id}` se declara; `DELETE` responde 204 y 409.
- `docs/design/ROUTES.md:39` y `docs/BRECHAS.md` §11 (S4A-D23).

Rojo (casos clave):
- `test_merge_plan.py`: solo precio; a classes sin `class_count` (error); a classes con 12; a days sin `class_count: null` (error) y con null (válido); precio negativo (error).
- `test_service_update.py`: cambio de precio con una fila update en auditoría con `price_cop` antes y después; `PlanUpdated` con nombres de campo; PATCH sin cambios sin auditoría ni evento; plan dado de baja da `PlanNotFound`; nombre repetido da `PlanNameDuplicated`; la carrera de dos renombres a la vez termina en 409 con `dos_sesiones`.
- `test_rn04_plan_price_change.py`: vende Mensual a 120.000 con `memberships.service.sell`, sube el plan a 135.000 y `agreed_price_cop`, `end_date` y `classes_total` siguen iguales; un intento SQL de cambiar el precio pactado lo rechaza el trigger.
- `test_service_set_active.py`: desactivar deja is_active falso, una fila update y `PlanDeactivated`; repetir no agrega auditoría ni evento; activar emite `PlanUpdated`; dado de baja da `PlanNotFound`; el plan desactivado no sale en la lista activa. `test_plan_deactivation_with_memberships.py`: con cuatro membresías activas, desactivar no cambia su estado, precio ni fechas, y vender con el plan inactivo da 422 `plan_inactive`.
- `test_service_deactivate_or_fail.py`: solo expired y cancelled da baja con `deleted_at` e `is_active` falso, una fila update y `PlanDeactivated`; con 12 active da `PlanHasActiveMemberships(12)` y el plan intacto; con una `pending_payment` bloquea (regla de S4A-D24); con una frozen bloquea; baja repetida da `PlanNotFound`; el nombre queda libre para un plan nuevo; `get_including_deleted` conserva el nombre; carrera con una venta en vuelo (`dos_sesiones`).
- `test_counts_active_by_plans.py`: conteo por lote igual al de `count_active_by_plan` plan por plan; plan sin ventas da 0; sin ids no consulta.
- Routers: 200, 204, 403 coach (plan intacto), 401, 404, 409, 422 (`is_active` en el cuerpo, `class_count`, `price_cop` negativo o decimal), 429 a la petición 31 del minuto.

Gate: `bash scripts/workflow/slice-gate.sh plans tests/plans/test_merge_plan.py tests/plans/test_service_update.py tests/plans/test_router_update.py tests/plans/test_service_set_active.py tests/plans/test_router_set_active.py tests/plans/test_service_deactivate_or_fail.py tests/plans/test_router_delete.py tests/integration/test_rn04_plan_price_change.py tests/integration/test_plan_deactivation_with_memberships.py`, `bash scripts/workflow/slice-gate.sh memberships tests/memberships/test_counts_active_by_plans.py`. `export-openapi` y `gen:api`.

### S4A-B8 · Tablero (US-108, US-110 backend; C9)

Crear:
- `dashboard/__init__.py`, `router.py`, `schemas.py` (`DashboardOut`, `MovementOut`), `service.py` (`month_of`, `short_name`, `format_cop`, `movement_phrase`, `last_movements`, `summary`) (S4A-D27 y D28).
- `audit/queries.py`: `recent`; `audit/diff.py`: `reduce_entry`; `audit/schemas.py`: `AuditEntryView`; `audit/service.py` re-exporta `recent`.
- Pruebas: `tests/dashboard/__init__.py`, `test_pure.py`, `test_movement_phrase.py`, `test_service.py`, `test_last_movements.py`, `test_router.py`, `test_perf.py`; `tests/audit/test_recent.py`; `tests/architecture/test_read_modules.py`.

Modificar (en el Rojo de B8; C9):
- `main.py`: `MODULES` suma `dashboard` al final; `test_audit_module.py:44-47` (tupla exacta, ahora de ocho) y su docstring.
- `test_service_import_graph.py`: `ALLOWED_EDGES` suma las cinco aristas de `dashboard` hacia audit, auth, members, memberships y payments; cada una debe existir de verdad (`test_cada_arista_permitida_existe`) y el par se importa limpio en los dos órdenes.
- `test_no_store_routes.py`, `test_session_scope.py` y `test_every_route_has_role.py` cubren el router nuevo (`no_store`, `SessionDep`, `StaffDep`); `GET /dashboard` no declara 422 ni 429.

Rojo (casos clave):
- `test_movement_phrase.py` (puras): una prueba por frase del catálogo (S4A-D28) y por el fallback; `short_name` con apellido compuesto y con tildes; `format_cop`; una entrada con blobs `apx1.` en `document` no los incluye (la vista reducida los descarta).
- `test_recent.py`: filtra por tablas y acciones (reveal, login, export, verify y download no aparecen; plans y users solo si se piden); respeta `limit` y el orden; excluye `SYSTEM_USER_ID`; rechaza tablas fuera de la lista blanca (`crypto.*`); con 100.000 entradas responde en menos de 50 ms con `EXPLAIN` por `ix_audit_log_table_seq` (perf).
- `test_service.py` y `test_pure.py`: con factories y `FrozenClock` en 2026-10-20, los conteos son idénticos a `memberships.service.summary()` y `income_month_cop` a `payments.service.summary` de 2026-10; borde de mes con el reloj en 2026-11-01T01:00Z (20:00 del 31 de octubre en Bogotá): `income_month` es 2026-10 y un pago con `paid_at` 2026-11-01T03:00Z cuenta en octubre; `month_of` en fin de mes y de año.
- `test_last_movements.py`: el escenario de venta de Plan Mensual a Laura Gómez y pago de 120.000 por Ana produce las frases esperadas, la más reciente primero; con 3 entradas devuelve 3; sin entradas, lista vacía; un reveal no aparece; el trabajo de `SYSTEM_USER_ID` no aparece y el límite de 10 se llena con lo demás; **la respuesta serializada completa no contiene** ningún valor de documento, teléfono, correo, nacimiento ni contacto de emergencia, ninguna cadena `apx1.`, ni `reference` ni `void_reason`; un socio dado de baja conserva su nombre.
- `test_router.py`: 200 con admin y coach, 403 member, 401; todas las llaves del contrato presentes y las cinco futuras en `null`, no ausentes; `last_movements` con 10 como máximo.
- `test_read_modules.py` (S4A-D28).
- `test_perf.py` (perf): 1.000 socios y 12 meses de pagos, `summary` en menos de 300 ms (mediana de 5).

Gate: `bash scripts/workflow/slice-gate.sh dashboard tests/dashboard/test_pure.py tests/dashboard/test_movement_phrase.py tests/dashboard/test_service.py tests/dashboard/test_last_movements.py tests/dashboard/test_router.py tests/architecture/test_read_modules.py`, `bash scripts/workflow/slice-gate.sh audit tests/audit/test_recent.py`, más `pytest -m perf tests/dashboard/test_perf.py`. `export-openapi` y `gen:api`. **Al cerrar B8: `run-gates.sh`, reconstruir imágenes con buildx y probar con el stack real.**

## 5. Front, slice por slice

Gate del front: `bash scripts/workflow/slice-gate.sh web/<feature> <archivos de Rojo>` (corre `eslint`, `tsc -p tsconfig.slice.json` y `vitest run` sobre lo del slice) y, al cerrar cada slice, `cd web && npm run lint && npx tsc --noEmit && npm test`. Antes de cada slice: `npm run gen:api` del slice de backend correspondiente ya hecho.

### S4A-F1 · Pantalla de auditoría (US-102, US-103, US-104 front; C10)

Crear:
- `web/src/shared/lib/encryptedBlob.ts` y `encryptedBlob.test.ts`.
- `web/src/features/system/pages/AuditPage.tsx` (más `.module.css`) y `AuditPage.test.tsx`; `components/AuditFilters.tsx`, `AuditDetailPanel.tsx` y `AuditDetailPanel.test.tsx`, `VerifyChainButton.tsx` y `VerifyChainButton.test.tsx`; `auditFilters.ts` (más prueba); `auditErrors.ts` (más prueba).
- En `features/system/api.ts` y `schemas.ts`: `useAudit`, `useAuditEntry`, `useLastVerification`, `useVerifyChain` y los esquemas Zod de `AuditRow`, `AuditDetail`, `VerifyResult`.
- `web/tests/e2e/stack/audit.spec.ts` (admin: filtra por entidad, abre el detalle, verifica y ve íntegra) y la captura en preview.

Modificar (en el Rojo de F1; C10):
- `web/src/config/features.ts` y `features.test.ts:10-13` (nueve features, con `audit`).
- `web/src/config/routeTable.ts:146` (`load` de `/sistema/auditoria`), `routes.test.ts:72-91` (lista con `load`) y `routes.reference.ts` si cambia algo de la fila.
- `web/src/layouts/nav.test.ts:14` (Auditoría entre Usuarios y roles y Configuración).
- `web/src/core/api/errorCodes.ts` y `errorCodes.test.ts` (`verification_running`, `audit_entry_not_found`), solo con B3 y B4 ya cerrados.
- `web/src/core/api/types.ts` (generado). `// DESIGN-GAP:` de S4A-D31.

Rojo (casos clave):
- `encryptedBlob.test.ts`: un blob válido da `keyId` y `alg`; texto sin prefijo, vacío, no texto y un blob mal formado dan `null`; nunca devuelve el texto cifrado.
- `AuditPage.test.tsx`: filtros en la URL con los nombres del api (`from`, `to`, `table`, `user_id`, `action`, `record_id`), Bogotá a UTC en las fechas, paginación por `offset`, carga, vacío y error con reintento, el coach no ve el ítem de menú ni la ruta.
- `AuditDetailPanel.test.tsx`: metadatos, lista de cambios antes a después, valores cifrados como Cifrado con el `key_id`, ausencia de cualquier acción de descifrar, `prev_hash` y `hash` en fuente monoespaciada, 404 con mensaje, carga y error.
- `VerifyChainButton.test.tsx`: estados 200 (Cadena íntegra con N filas), 202 con sondeo de `last`, 409 con mensaje, cadena rota con enlace a `?seq=X`, fecha de la última verificación en Bogotá y texto Verificar ahora.

Gate: `bash scripts/workflow/slice-gate.sh web/system src/features/system/pages/AuditPage.test.tsx src/features/system/components/AuditDetailPanel.test.tsx src/features/system/components/VerifyChainButton.test.tsx` y `bash scripts/workflow/slice-gate.sh web/shared src/shared/lib/encryptedBlob.test.ts`.

### S4A-F2 · Historial de la ficha (US-106 front; C10)

Crear:
- `features/members/components/MemberHistoryTab.tsx` y `.test.tsx`; `features/members/lib/historyEntries.ts` y `historyPhrase.ts` con `historyPhrase.test.ts`; `useMemberHistory` en `features/members/api.ts`; el esquema Zod de `MemberHistoryItem` en `features/members/schemas.ts`.

Modificar (en el Rojo de F2; C10):
- `web/src/shared/lib/audit-labels.ts` y `audit-labels.test.ts` (campos `fields` y `phrase`, `ENTITY_LABELS` con los nombres reales) y `web/src/shared/ui/HistoryAside.tsx` y su prueba (línea `phrase`): gate `web/shared`.
- `web/src/config/routeTable.ts` (hija `/socios/:id/historial` con `members.history.view`, `CHILD_TABS`), `routes.reference.ts`, `routes.test.ts:127` (hijos de la ficha) y `docs/design/ROUTES.md` (se mueven juntos).
- `web/src/features/members/pages/MemberDetailPage.tsx:57` (sin `disabledUntil`) y `MemberDetailPage.test.tsx:101-114`; `MemberDataTab.tsx:14` (caja Historial reciente con las 5 últimas y el enlace).
- `web/tests/e2e/stack/member-tabs.spec.ts` y `member-detail.spec.ts` si capturan la pestaña.

Rojo: `historyPhrase.test.ts` (frase por acción y tabla, con el nombre de quien actuó y sin valores), `historyEntries` (mapeo de `table_name` completo y de `fields`), `MemberHistoryTab.test.tsx` (orden descendente, Cargar más acumulativo, vacío, error con reintento, el coach lo ve, ningún valor mostrado), `audit-labels.test.ts` (resumen con `fields`).

Gate: `bash scripts/workflow/slice-gate.sh web/members src/features/members/components/MemberHistoryTab.test.tsx src/features/members/lib/historyPhrase.test.ts` y `bash scripts/workflow/slice-gate.sh web/shared src/shared/lib/audit-labels.test.ts src/shared/ui/HistoryAside.test.tsx`.

### S4A-F3 · Inicio (US-108, US-109, US-110 front; C10)

Crear: `features/dashboard/api.ts`, `schemas.ts`, `links.ts` (con `links.test.ts`), `components/KpiGrid.tsx`, `FutureKpis.tsx`, `LastMovements.tsx` (cada uno con su prueba) y la actualización de `pages/InicioPage.tsx`; `web/tests/e2e/stack/home.spec.ts` y `web/tests/e2e/home.spec.ts`.

Modificar: `InicioPage.test.tsx` (reemplazo completo del saludo y los atajos del Sprint 2); `docs/design/ROUTES.md:18` (ya no es mínima); `errorCodes` sin cambios.

Rojo: `links.test.ts` (`kpiLinks("2026-10-20")` da los cuatro destinos de `/socios` y el de `/pagos` con los límites del mes de Bogotá en UTC, 2026-10-01T05:00Z a 2026-11-01T05:00Z), `KpiGrid` (valores 120, 14, 9 y `$ 3.250.000`, línea de pendientes, enlaces, carga y error con Reintentar que vuelve a pedir), `FutureKpis` (null dice Disponible en v0.x y nunca 0; con valor lo muestra), `LastMovements` (diez en orden, vacío, enlace a la ficha, hora relativa con reloj falso), `InicioPage.test.tsx` y los dos `home.spec.ts` (clic en Por vencer llega a `/socios?membership_status=expiring`; el member va a `/mi`; ninguna tarjeta depende solo del color). Capturas en 320, 768, 1024 y 1440, en claro y oscuro.

Gate: `bash scripts/workflow/slice-gate.sh web/dashboard src/features/dashboard/links.test.ts src/features/dashboard/components/KpiGrid.test.tsx src/features/dashboard/components/FutureKpis.test.tsx src/features/dashboard/components/LastMovements.test.tsx src/features/dashboard/pages/InicioPage.test.tsx`. **Criterio diferido:** T8 de US-109 (cuadre con datos de demostración) se cierra en el Sprint 4B con US-111.

### S4A-F4 · Acciones de planes (US-080, US-081, US-082 front; C10)

Crear: `useUpdatePlan`, `useSetPlanActive` y `useDeletePlan` en `features/plans/api.ts`; el modo edición de `components/PlanForm.tsx`; la columna de acción, Socios con él y el total de activos e inactivos en `pages/PlansPage.tsx`; `planErrors.ts` con `plan_has_active_memberships`; `PlanForm.edit.test.tsx`, `PlansPage.actions.test.tsx` y `PlansPage.delete.test.tsx`.

Modificar: `web/src/core/api/errorCodes.ts` y su prueba (`plan_has_active_memberships`, con B7 cerrado); `shared/data/schemas` si `planRowSchema` necesita `active_members_count` con valor por defecto 0; `web/tests/e2e/stack/plans.spec.ts`; `docs/design/ROUTES.md:39`.

Rojo: `PlanForm.edit.test.tsx` (precarga, aviso fijo, envía solo lo modificado, error de campo del 422 y del 409 de nombre), `PlansPage.actions.test.tsx` (Desactivar con `ConfirmModal`, el cambio de la etiqueta de estado, Activar, acciones ocultas al coach, columna Socios con él, total partido), `PlansPage.delete.test.tsx` (baja exitosa quita la fila; el 409 muestra el mensaje y el botón Desactivar que llama a `useSetPlanActive`; acción oculta al coach).

Gate: `bash scripts/workflow/slice-gate.sh web/plans src/features/plans/components/PlanForm.edit.test.tsx src/features/plans/pages/PlansPage.actions.test.tsx src/features/plans/pages/PlansPage.delete.test.tsx`.

## 6. Flujos de datos

### 6.1 El ciclo diario del worker (demo 2)
1. `python -m app.worker.main` (o `--run-once expirations --date 2026-11-01`): `worker_runtime` instala los listeners, carga los services (gate de pagos registrado), configura el engine y espera la base (`wait_for_database`).
2. `serve` arma el scheduler con el cron de las 07:00 de Bogotá y el latido cada 30 s; al arrancar, si ya pasó la hora y no hay fila del día, recupera el ciclo.
3. `run_job`: `today` del reloj, `claim_run` (sesión corta propia; la fila queda running), `actor_scope(SYSTEM_USER_ID)` y `batch_scope`, y el job llama `memberships.service.recompute_statuses(session_factory, today=...)`.
4. `recompute_statuses`: lee `expiring_days`; páginas de ids de socios con candidatas (sin candados); por socio una transacción: `lock_member`, `lock_membership` por fila, `compute_status` con las congelaciones, asignación, un flush (el hook escribe una fila update por membresía con `SYSTEM_USER_ID` y `subject_member_id`) y `emit` de `MembershipExpiring` o `MembershipExpired`; commit. Un socio ocupado se reintenta y, si sigue, se omite y se cuenta.
5. `finish_run` (otra sesión) fija ok o error, agrega el intento a `details.attempts` y, si falló, llama `alert` con el código job_failed. Una segunda corrida el mismo día vuelve a reclamar la fila, no encuentra candidatas y no escribe auditoría ni eventos.

### 6.2 Verificar la cadena (demo 3)
1. Pantalla: Verificar ahora llama `POST /audit/verify`; CLI: `verify-audit --as admin@...`. Ambas toman el candado de sesión `4_270_003` en una conexión dedicada (la API responde 409 si no lo obtiene; la CLI espera hasta `--wait-timeout`).
2. `run_verification`: `through_seq` y lotes de 5.000 con `verify_chain` por continuación; en la primera ruptura se detiene; después, comprobación de cola perdida.
3. Se inserta `audit.verifications` y se escribe la fila verify (`record` toma el candado de la cadena al final). Hasta 50.000 filas la API responde 200 con el resultado; por encima, 202 y una tarea con su propia sesión que libera el candado en `finally`; el front sondea `GET /audit/verify/last`.
4. El front muestra Cadena íntegra o Cadena rota en el registro seq X con enlace al detalle (`GET /audit/{seq}`, 404 si el seq ya no existe).

### 6.3 Historial del socio (demo 4)
`GET /members/{member_id}/audit` (staff): `members.service.history` comprueba que el socio exista (también dados de baja) y llama a `audit.service.member_history`, que lee por `subject_member_id` y `seq` descendente, resuelve nombres con `auth.user_refs_for` y devuelve `fields` sin valores. El front mapea cada ítem a `AuditEntryView` con su frase y lo pinta con `HistoryAside` (pestaña completa y caja de la ficha).

### 6.4 Tablero (demo 5)
`GET /dashboard` (staff): `today` del reloj; `memberships.summary` y `payments.summary` del mes AAAA-MM; `audit.recent` de las tres tablas de negocio sin `SYSTEM_USER_ID`; nombres por lote (`members.names_for`, `memberships.refs_for`, `auth.user_refs_for`); `movement_phrase` por entrada; los cinco campos futuros en `null`. Nunca un blob ni `reference` ni `void_reason`.

### 6.5 Planes (demo 6)
`PATCH` cambia el precio sin tocar membresías vendidas; `deactivate` impide vender (`plan_inactive` en `sell`); `DELETE` toma `FOR UPDATE` del plan, cuenta con `count_active_by_plan` (perezoso) y responde 204 o 409 `plan_has_active_memberships`; con una venta `pending_payment` el 409 obliga a anular antes.

### 6.6 Contacto para avisos (Sprint 5 lo consume)
Un job de Notifications llama `contact_for_notification` con el socio y el propósito notify dentro de `actor_scope` y `batch_scope`: valida el propósito, descifra teléfono y correo por `_decrypt_fields`, deja dos filas reveal con purpose en la auditoría y dos decrypt en `crypto_ops`, y devuelve un `Contact` que el llamador no persiste en claro.

## 7. Pruebas de arquitectura y de reglas que rompen fuera del gate: dónde se arreglan

Las trece del impacto (C1 a C10) más las que este blueprint agrega. Todas se corrigen en el **Rojo** del slice indicado.

- B1: `test_audited_tables.py` (`EXCLUIDAS` con `worker.job_runs` e importar `app.core.jobs`); `test_core_import_direction.py` (importadores de `core.jobs`, `core/jobs` y `core/alerts` sin módulos); `tests/migrations/test_0011_payments_immutability.py:112-117` (está en la cadena); `tests/conftest.py` (limpieza de `worker.job_runs` en las tres limpiezas); `migrations/env.py`; `pyproject.toml` (`omit`); nueva `test_worker_boundaries.py`.
- B2: `_imports.py` y `test_no_cross_models.py` (`expirations` en `PRIVATE_HELPERS["memberships"]`); `test_handlers_no_new_locks.py` (`SUSCRIPTORES_ESPERADOS` con los dos eventos nuevos y lista vacía); `test_events_without_pii.py` (los eventos nuevos pasan); nueva `test_expirations_lock_order.py`; `test_guarded_calls.py` sin cambio (el recálculo usa `lock_membership`).
- B3: `test_audit_module.py:69-72` (router con dos rutas, sin models); `test_audited_tables.py` (`audit.verifications` en `EXCLUIDAS`, `app.core.audit_verify` importado); `test_no_physical_delete.py` (`AuditVerification`); `test_sql_literals_constant.py` (tercera llave); `test_error_codes_per_route.py` (`CON_LIMITE` con `POST /audit/verify`), `test_user_limits_catalog.py` y `test_writes_have_user_limit.py`; `_imports.py` (`audit`); `test_no_store_routes.py` (router de audit); `test_triggers_siempre_activos.py`; `tests/conftest.py` (`audit.verifications` antes de `audit_log`); `test_0012` (cadena); `test_audit_chain.py` (firma ampliada con valores por defecto).
- B4: `_imports.py` (`audit` con `queries` y `diff`); `test_audit_module.py` (cuatro rutas); `test_list_routes_use_page_params.py` y `test_error_codes_per_route.py` (422 de las rutas nuevas) sin cambio de conjuntos; `test_no_cross_models.py` (audit no importa `auth.models`).
- B5: `test_service_import_graph.py` (`("members", "audit")` y la aserción de `arriba`); `test_audited_tables.py:186` (renombre); `test_list_rows_without_sensitive_fields.py` (barre la ruta nueva).
- B6: `_imports.py` (`members` con `contact`); `test_reveal_single_door.py` sin cambio; nueva `test_crypto_bus_importers.py`.
- B7: `test_service_import_graph.py:281-286` (perezosa de plans); `test_error_codes_per_route.py` (`CON_LIMITE` con cuatro rutas); `test_writes_have_user_limit.py`; `test_guarded_calls.py` (`plans` no nombra `Membership`).
- B8: `test_audit_module.py:44-47` (ocho módulos); `test_service_import_graph.py` (cinco aristas de dashboard; los importadores de plans siguen siendo memberships); nueva `test_read_modules.py`; `test_no_store_routes.py`, `test_session_scope.py` y `test_every_route_has_role.py` cubren el router nuevo.
- F1: `features.test.ts` (nueve), `routes.test.ts` (lista con load), `nav.test.ts` (Auditoría), `errorCodes.test.ts`. F2: `routes.test.ts:127` y `:35`, `MemberDetailPage.test.tsx:101-114`, `routes.reference.ts`. F3: `InicioPage.test.tsx`. F4: `errorCodes.test.ts`, `plans.spec.ts`.

## 8. Fábricas y fixtures

- `tests/factories/audit_chain.py` (nace en B3): `make_audit_chain(session, n, table_name)` agrega `n` filas a continuación de la última con `chain_hash` real, `at` creciente a partir del reloj y inserción por lotes con Core (los 100.000 de las pruebas perf no pasan por `record()`); `tamper_row(session, seq, column)` altera una fila con `ALTER TABLE ... DISABLE TRIGGER USER` dentro de la transacción de la prueba (se revierte con ella) y `drop_rows(session, seqs)`.
- `tests/factories/job_runs.py`: `make_job_run(session, job_name, run_date, result, ...)`.
- `tests/worker/conftest.py`: fábrica de sesión sobre la base de prueba, `FrozenClock` con `set_clock`, un `JobSpec` de prueba que escribe y uno que lanza, y la limpieza de `worker.job_runs` por prueba.
- `tests/conftest.py`: `LIMPIAR_JOB_RUNS` y `LIMPIAR_VERIFICATIONS` (S4A-D38) en las tres limpiezas.
- Reutiliza `make_member`, `make_membership`, `make_freeze`, `make_payment` y `make_plan`; `bus_listo` para `contact_for_notification`; `dos_sesiones` para candados; `capturar_eventos` para `MembershipExpiring` y `MembershipExpired`.
- Front: MSW de `core/api` con las respuestas de `AuditRow`, `AuditDetail`, `VerifyResult`, `MemberHistoryItem`, `DashboardOut` y `PlanOut` con `active_members_count`; `mockSession` para el proyecto preview.

## 9. Mapa endpoint a front

Roles: A = admin, C = coach. Slice de backend entre paréntesis.
- `GET /audit` (B4; A): `AuditPage` y `useAudit` (F1).
- `GET /audit/{seq}` (B4; A): `AuditDetailPanel` y `useAuditEntry` (F1).
- `GET /audit/verify/last` (B3; A): `VerifyChainButton` y `useLastVerification` (F1).
- `POST /audit/verify` (B3; A): `VerifyChainButton` y `useVerifyChain` (F1).
- `GET /members/{member_id}/audit` (B5; A, C): `MemberHistoryTab`, la caja de `MemberDataTab` y `useMemberHistory` (F2).
- `GET /dashboard` (B8; A, C): `InicioPage` y `useDashboard` (F3).
- `PATCH /plans/{plan_id}` (B7; A): `PlanForm` en edición y `useUpdatePlan` (F4).
- `POST /plans/{plan_id}/activate` y `/deactivate` (B7; A): acciones de fila y `useSetPlanActive` (F4).
- `DELETE /plans/{plan_id}` (B7; A): Dar de baja y `useDeletePlan` (F4).
- Cambios de contrato en rutas existentes: `GET /plans` y `GET /plans/{plan_id}` ganan `active_members_count` (B7, F4).
Son 10 endpoints nuevos; ninguno devuelve un arreglo suelto.

## 10. Trazabilidad, riesgos, tabla de slices y lista para el planner

### 10.1 Preguntas abiertas de la exploración y su decisión

1. `display_name`: S4A-D19 (sin columna en 4A; respaldo de la parte local del correo; sin `0014`).
2. Columna `status` como espejo: S4A-D1 (sí; lecturas derivadas; eventos desde el job; sin suscribir la caché).
3. Forma del lote: S4A-D2 (una transacción por socio, `lock_member` y `lock_membership`, reintento y omisión ante busy).
4. Adelantar el día: S4A-D4 (`--date` en el worker y en la CLI; guarda de producción).
5. Healthcheck del worker: S4A-D8 (latido en archivo; `/health` no lee `job_runs` en 4A).
6. `WORKER_*` en `Settings`: S4A-D5 (constantes).
7. Preámbulo compartido: S4A-D6 (`worker_runtime` propio; `cli_runtime` no se toca).
8. Nombres de los privados: S4A-D18 (`audit`: `queries`, `diff`, `verify`), S4A-D2 (`memberships/expirations.py`), S4A-D21 (`members/contact.py`).
9. Contrato de verificación: S4A-D11 a D14 (candado de sesión 4_270_003, umbral síncrono 50.000, `audit.verifications`, `verify_chain` con continuación).
10. Contrato de `auth` para la lista: S4A-D16 y D19 (`search_user_ids`, `user_refs_for`; `names_for` e `ids_by_email` intactos).
11. Historial en el front: S4A-D32 (se adapta `audit-labels.ts` y `HistoryAside`; hija `/socios/:id/historial` con la feature members).
12. Socios con él y totales: S4A-D25 (`counts_active_by_plans`, `active_members_count`, totales con `limit=1`).
13. Contacto para avisos: S4A-D21 (firma única sin `fields` ni `by`; `purpose` en el `after`; sin `bus.batch`).
14. Movimientos del tablero: S4A-D28 (anulación sin monto; activación por cobertura con su frase; el sistema excluido).
15. Revisión de diseño previa: S4A-D36 y S4A-D41 (cerrada; S3-D98 a backlog v0.2).
16. Cobertura de `cli.py`: S4A-D39 (pruebas de `export-openapi` e `init-keys` en el Rojo de B1).

### 10.2 Hallazgos de la exploración (1 a 11) y dónde se resuelven

1. US-094 frente a D5: S4A-D1. 2. Orden de candados: S4A-D2. 3. `display_name`: S4A-D19. 4. Contratos distintos del código: S4A-D11, D15, D19, D21 y D41. 5. Pruebas que fallan: sección 7. 6. Entorno (worker y tools sin bind, `test_compose_config.sh:58`, smoke): S4A-D9. 7. Tamaños: S4A-D12, D18 y D39. 8. Diseño frente a decisiones: S4A-D17, D23, D28 y D36. 9. Historial y lista (congelaciones sin sujeto, mezcla de entradas de `auth.users`): S4A-D16 y D20. 10. `contact_for_notification`: S4A-D21. 11. Verificación de la cadena: S4A-D11 a D15.

### 10.3 Condiciones para VERDE del impacto (C1 a C13)

- C1 (B1: pruebas de `core/jobs` y `worker/`, conftest, `env.py`, `omit`, `core/alerts.py`, constantes de horario): S4A-D3, D5, D6, D7, D10, D39 y sección 7 (B1).
- C2 (W0-1 con healthcheck y perfil; W0-2 sin perfil, test invertido, smoke, buildx, binds de desarrollo): S4A-D8 y D9.
- C3 (B2: privado en `PRIVATE_HELPERS`, sin `with_for_update` fuera de `lock_membership`, lote por socio, prueba `dos_sesiones`, eventos en `SUSCRIPTORES_ESPERADOS`, `perf`, CLI con `--date` y `--as`): S4A-D1, D2 y D15. Matiz: los eventos entran con lista vacía en vez de suscribir `_mark_summary_dirty` (S4A-D1).
- C4 (B3): S4A-D11 a D15 y D26; sección 7 (B3).
- C5 (B4): S4A-D16, D17 y D18.
- C6 (B5): S4A-D20 y sección 7 (B5).
- C7 (B6): S4A-D21. Matiz: sin `bus.batch` para conservar el `record_id`.
- C8 (B7): S4A-D22 a D26.
- C9 (B8, `display_name`): S4A-D19, D27 y D28.
- C10 (front): S4A-D30 a D35.
- C11 (migraciones, volcados, ciclo, `alembic heads`): S4A-D38.
- C12 (cobertura y `run-gates.sh` en B2 y B3): S4A-D39.
- C13 (T-DOC y cierre de la revisión de diseño): S4A-D36 y D41.

Puntos adicionales de la coordinación: (1) `test_guarded_calls.py` y el recálculo por socio con `dos_sesiones`, y `_load_freezes_for` privado dentro de `memberships`: S4A-D2; (2) `display_name`: S4A-D19; (3) las trece pruebas literales asignadas a su Rojo: sección 7; (4) nombres de contrato corregidos (`bus.op_context`, `SensitiveFieldRevealed`, `get_by_email`, `verify_chain`, `Depends(Clock)`, `slow`, 202 en `responses_for`, `MemberHistoryItem` sin `user_email`, `q` en el historial): S4A-D14, D15, D20, D21 y D41; (5) `core/alerts.py`, binds de `worker` y `tools`, `test_compose_config.sh:58`, smoke y `e2e-stack`: S4A-D7 y D9; (6) 166 planes y la regla de `DELETE` frente a `pending_payment`: S4A-D24.

### 10.4 Riesgos

1. [HIGH] Interbloqueo entre el recálculo y `freeze`, `cancel`, `sell` o `register`. Mitigación: S4A-D2 (orden D3, una transacción por socio, reintento y omisión), prueba AST y prueba `dos_sesiones`.
2. [HIGH] Hash de la cadena no reproducible al releer JSONB (la verificación da rota en datos reales). Mitigación: la primera prueba de B3 contra `apex-db-1` (4.500 filas); si da rota se detiene el sprint, porque sería un hallazgo de la cadena y no del código nuevo; `canonical` no cambia.
3. [MEDIUM] Verificación larga contra Nginx de 60 s. Mitigación: umbral síncrono de 50.000, 202 con tarea, sondeo del front; calibración con la prueba perf.
4. [MEDIUM] Cobertura al quitar el `omit`. Mitigación: `main.py` delgado, pruebas de CLI nuevas en B1 y `run-gates.sh` tras B2 y B3.
5. [MEDIUM] La primera corrida del job escribe decenas de filas de auditoría de golpe bajo el candado de la cadena. Mitigación: una transacción por socio (candado corto) y documentación en RUNBOOK.
6. [MEDIUM] Fuga de blobs o de `reference` en el tablero y el historial. Mitigación: vista reducida con lista blanca de llaves, `fields` sin valores y pruebas que buscan `apx1.` en la respuesta serializada completa.
7. [MEDIUM] Worker y `tools` con código viejo. Mitigación: binds de desarrollo (solo lectura) y buildx en W0-2, al cerrar el backend y en `verify-delivery`.
8. [MEDIUM] `--date` adelanta la fecha de la auditoría. Mitigación: rechazado con ENV de producción; documentado en RUNBOOK.
9. [LOW] El resumen cacheado del api no se invalida por el job (otro proceso): no hace falta, el resumen es derivado (S4A-D1, S3-D93).
10. [LOW] La tarea de verificación en segundo plano muere con el reinicio del api (aceptado por N-30; el `--reload` de desarrollo también): no editar `src/` durante un E2E.
11. [LOW] `e2e-stack` arranca el worker y puede dejar una fila de `job_runs`: `datosDeBase()` no la cuenta (verificado en W0-2).
12. [LOW] La limpieza P2-1 de planes de prueba exige anular antes las ventas `pending_payment` (S4A-D24); es un paso manual de `verify-delivery`.

### 10.5 Tabla de slices final

| Orden | Slice | Historias | Archivos principales | Rojo (pruebas) | Gate |
|---|---|---|---|---|---|
| 1 | S4A-W0-1 | US-113 (preparación) | `infra/compose.yml`, `compose.dev.yml`, `test_compose_config.sh`, T-DOC | aserciones de `test_compose_config.sh` | `compose config`, `test_compose_config.sh`, smoke sin perfil |
| 2 | S4A-B1 | US-113 | `core/jobs.py`, `core/alerts.py`, `worker/*`, `0012` | `tests/worker/*`, `test_alerts`, `test_0012`, `test_worker_boundaries`, tests de CLI | `worker`, `core/jobs`, `cli` + ciclo Alembic |
| 3 | S4A-W0-2 | US-113 (cierra US-005) | `compose.yml`, `test_compose_config.sh`, `compose-smoke.sh` | smoke del worker | smoke con worker healthy y `--run-once` 0 |
| 4 | S4A-B2 | US-094 | `memberships/expirations.py`, eventos, `worker/jobs/expirations.py`, `cli.py` | `test_expirations`, `test_recompute_memberships`, `test_recompute_lock_order`, `test_transition_event`, orden de candados | `memberships`, `worker`, `cli`, perf, `run-gates.sh` |
| 5 | S4A-B3 | US-104, US-105 | `core/audit_verify.py`, `core/audit.py`, `0013`, `audit/verify.py`, router, `cli.py` | `test_verify_chain`, `test_format_verify_message`, `test_verify*`, `test_router_verify`, `test_verify_audit`, `test_0013` | `audit`, `core/audit_verify`, `core/audit`, `cli` + Alembic, perf, `run-gates.sh` |
| 6 | S4A-B4 | US-102, US-103 | `audit/queries.py`, `diff.py`, `auth` (`user_refs_for`, `search_user_ids`) | `test_filters`, `test_list*`, `test_diff`, `test_get`, routers, `test_user_refs` | `audit`, `auth`, perf |
| 7 | S4A-B5 | US-106 | `members/service.py` y `router.py`, `audit` (`member_history`) | `test_history_fields`, `test_member_history`, `test_router_member_audit`, `test_audit_subject` | `audit`, `members` |
| 8 | S4A-B6 | US-077 | `members/contact.py` | `test_validate_purpose`, `test_service_contact`, `test_crypto_bus_importers` | `members` |
| 9 | S4A-B7 | US-080, US-081, US-082 | `plans/*`, `memberships` (`counts_active_by_plans`) | `test_merge_plan`, `test_service_update`, `test_router_*`, `test_service_deactivate_or_fail`, integración RN-04 y desactivación | `plans` + `memberships` |
| 10 | S4A-B8 | US-108, US-110 | `dashboard/*`, `audit` (`recent`), `main.py` | `tests/dashboard/*`, `test_recent`, `test_read_modules` | `dashboard`, `audit`, perf, `run-gates.sh`, buildx |
| 11 | S4A-F1 | US-102, US-103, US-104 | `features/system/*`, `shared/lib/encryptedBlob.ts` | `AuditPage`, `AuditDetailPanel`, `VerifyChainButton`, `encryptedBlob` | `web/system`, `web/shared` |
| 12 | S4A-F2 | US-106 | `features/members/*`, `audit-labels.ts`, `HistoryAside.tsx` | `MemberHistoryTab`, `historyPhrase`, `audit-labels` | `web/members`, `web/shared` |
| 13 | S4A-F3 | US-108, US-109, US-110 | `features/dashboard/*` | `links`, `KpiGrid`, `FutureKpis`, `LastMovements`, `InicioPage`, `home.spec` | `web/dashboard` |
| 14 | S4A-F4 | US-080, US-081, US-082 | `features/plans/*` | `PlanForm.edit`, `PlansPage.actions`, `PlansPage.delete` | `web/plans` |

Validación del sprint: E2E completo (preview y stack, con `home.spec.ts` y `audit.spec.ts`), `--run-once expirations` dos veces el mismo día, perf de la verificación y de la lista de auditoría, `security-reviewer` (la auditoría no muestra material de llave, el historial respeta el rol, `verify-audit` atribuido con `--as`, el worker sin puertos), limpieza de planes de prueba (P2-1) y `verify-delivery` contra el stack reconstruido. Paso humano: push, PR con CI en verde y merge.

### 10.6 Lo que el planner debe convertir en pasos

1. Un paso por slice de la tabla anterior, en ese orden, cada uno con sus tres tiempos: Rojo (stubs y pruebas, incluidos los ajustes de la sección 7 de ese slice), Verde y Gate con la lista exacta de archivos de este documento.
2. En W0-1: volcado `pg_dump -Fc` previo a `0012`, healthcheck del worker con el perfil conservado, binds de desarrollo, aserciones de `test_compose_config.sh`, T-DOC completo (S4A-D41), copia de S4A-D1 a D42 a `DECISIONES.md` y creación de `BRECHAS.md` §11 con las brechas de S4A-D36.
3. En B1: crear primero los stubs que `slice-gate.sh` exige (`worker/__init__.py`, `core/jobs.py`, `tests/worker/__init__.py`), luego las pruebas; quitar el `omit` en el Verde, no antes; migración probada contra `db_test` antes de dejarla en `migrations/versions`; `restart api` tras aplicarla.
4. En B2: ningún `with_for_update` nuevo; el recálculo por socio con `lock_member` y `lock_membership`; los eventos sin suscriptores; `run-gates.sh` al cerrar.
5. En B3: `AUDIT_VERIFY_LOCK_KEY = 4_270_003`; `verify_chain` ampliada sin romper `test_audit_chain.py`; fila verify con `table_name = audit.verifications`; limpieza de `audit.verifications` antes de `audit_log`; primera verificación contra `apex-db-1` y parar si da rota; `run-gates.sh` al cerrar.
6. En B4: `user_refs_for` y `search_user_ids` en `auth` sin tocar `names_for` ni `ids_by_email`; `GET /audit/{seq}` después de `/audit/verify/last`.
7. En B5: arista `members -> audit` y su ajuste en `test_service_import_graph.py` en el mismo Rojo; `MemberHistoryItem` sin `user_email`; `q` real.
8. En B6: `contact_for_notification` solo por `_decrypt_fields`; sin `bus.batch`; `test_crypto_bus_importers.py` con los importadores reales.
9. En B7: cuatro rutas con `admin-write` y 429 declarado; import perezoso con `# lazy: G-03`; `counts_active_by_plans` y `active_members_count`; regla de `pending_payment`; corregir `ROUTES.md:39`.
10. En B8: `dashboard` al final de `MODULES`; cinco aristas declaradas y existentes; vista reducida con lista blanca; prueba de `apx1.` en la respuesta completa; reconstruir imágenes y probar en el stack real.
11. En F1 a F4: regenerar `types.ts` antes; los cambios de `features.test.ts`, `routes.test.ts`, `nav.test.ts`, `MemberDetailPage.test.tsx`, `InicioPage.test.tsx` y `errorCodes.test.ts` van en el Rojo del slice; `useSensitiveMutation` en toda mutación nueva; `// DESIGN-GAP:` y fila de `BRECHAS.md` §11 por cada desvío.
12. Cierre: `run-gates.sh` en verde con cobertura de `app` de al menos 80 % sin `omit`; `pytest tests/architecture -q`; ciclo de Alembic sobre `0013`; `docs/openapi.json` y tipos regenerados; E2E; smoke con worker, `job_runs` y `audit.verifications`; limpieza P2-1; borrado de los volcados; `verify-delivery`; documentos: `RUNBOOK.md` (§6 y §7, primera corrida del job, `--date`, cache del resumen), `CLAUDE.md`, `DECISIONES.md` (estado al cierre del Sprint 4A) y `SPRINT-04A.md`.
