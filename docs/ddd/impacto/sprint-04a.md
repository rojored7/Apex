# Análisis de impacto previo · Sprint 4A (worker, auditoría verificable, tablero y planes restantes)

Fecha: 28 de octubre de 2026 (tarde; línea base tomada a las 17:00 hora local).
Alcance: `update` sobre un repositorio con código (`flow-update`, Fase 0).
Anclaje: rama `feat/sprint-04a-worker-auditoria-tablero`, HEAD `f5f2503` ("cierre del Sprint 3",
igual a `main`), `git status` limpio, un solo worktree. El nombre de la rama coincide con
`SPRINT-04A.md`.
Plan de referencia: `docs/ddd/09_sprint_plan/SPRINT-04A.md` (14 historias, 10 endpoints nuevos,
migraciones `0012_worker_job_runs` y `0013_audit_verifications`, dos slices de Wave 0, 8 de
backend S4A-B1 a S4A-B8 y 4 de front S4A-F1 a S4A-F4; `CRITICA-2.md` N-3 sobre el perfil
`worker`).

## Veredicto: AMARILLO

Se puede avanzar a la Fase 1 con `--allow-amber`. Nada es ROJO: los contratos del Sprint 3 que
este sprint consume existen (`record`, `verify_chain`, `subject_member_id` con su índice,
`refs_for`, `summary`, `count_active_by_plan`, `_load_freezes_for`, `names_for` de los cuatro
módulos, `FrozenClock`, `SYSTEM_USER_ID`, `resolve_actor` y `cli_runtime`), los esquemas `worker`
y `audit` existen desde `0001`, `apex-db-1` está en `0011_payments_immutability (head)`, el stack
está sano y `ruff`, `ruff format --check`, `mypy --strict` y `tsc --noEmit` pasan en HEAD. El
amarillo viene de cuatro cosas. Primera, **trece pruebas de arquitectura y de reglas que corren
en todos los gates fijan literalmente el estado del Sprint 3** (`MODULES`, `ALLOWED_EDGES`, las
aserciones `arriba["members"] == set()` y `perezosas["plans"] == set()`, el "router de `audit`
vacío", `EXCLUIDAS` de tablas auditadas, `CON_LIMITE`, la lista de rutas con `load`, las ocho
features habilitadas, las etiquetas del menú, las pestañas de la ficha) y fallan en cuanto el
primer slice toque su pieza. Segunda, **dos contratos del plan chocan con reglas vigentes del
código**: el `FOR UPDATE` por lotes de `recompute_statuses` (US-094) choca con
`test_guarded_calls.py` ("`with_for_update` sobre `Membership` solo en `sell.py::lock_membership`")
y con el orden de candados D3/S3-D95, y la frase "Ana P. registró…" (US-110) necesita
`auth.users.display_name`, que **no existe** (`auth/models.py:54-69`) y cuya migración no está en
la lista de `SPRINT-04A.md` (solo `0012` y `0013`). Tercera, **`core/jobs.py` y `core/alerts.py`
no existen** aunque `CLAUDE.md` los lista: `jobs.py` nace en S4A-B1; `alerts.py` (G-08,
`LogAlertSink`) no aparece en ningún slice y el plan lo da por aplicado. Cuarta, **nombres de
contrato en los desgloses que no son los del código** (`bus.op_context`, `SensitiveFieldRevealed`
que S3-C16 descartó, `auth.service.get_by_email`, `verify_chain(start_prev_hash, start_seq)`,
`Depends(Clock)`, marcador `slow`, `HomePage.tsx`). Todo se absorbe con las condiciones de la
sección 9; ninguna exige cambiar el alcance. El pendiente "revisión de diseño previa al Sprint
4A" (S3-D98 y BRECHAS §10) se resuelve en la sección 7: no bloquea y se absorbe como condición
documental.

## Cómo se verificó

- Lectura completa de `SPRINT-04A.md`, `CRITICA-2.md`, `CLAUDE.md`, `scripts/workflow/README.md`,
  `docs/ddd/impacto/sprint-03.md` (referencia de formato), las decisiones G-05, G-06, G-08, N-15,
  N-21, N-22, N-30, N-31, Q10, el refinamiento de US-110, el bloque "Estado al cierre del Sprint
  3", "Dueños asignados al cierre del Sprint 3" y P2-1 de `DECISIONES.md`, `docs/BRECHAS.md` §2,
  §6 y §10, `docs/design/ROUTES.md` y las pantallas `Auditoria.html`, `Inicio.html`, `Planes.html`
  y `Socio_Ficha.html`, el bloque "V9.1 · run-gates.sh completo" y los "Estado al terminar" de
  `docs/scratch/sprint-03.md`, `docs/RUNBOOK.md` §6 y §7, y los desgloses completos de US-077,
  US-080, US-081, US-082, US-094, US-102 a US-106, US-108 a US-110 y US-113 (más las secciones de
  contrato de sus historias).
- Lectura del código que el sprint toca (sección 1 y 2): `core/audit.py`, `core/clock.py`,
  `core/context.py`, `core/events.py`, `core/locks.py`, `core/health.py`, `core/db.py`,
  `core/ratelimit.py`, `core/errors.py`, `core/security.py`, `core/crypto/{types,bus,oplog,models}.py`,
  `main.py`, `cli.py`, `modules/audit/*`, `modules/plans/*`, `modules/memberships/{service,
  summary,queries,sell,lifecycle,rules}.py`, `modules/members/{service,detail,router}.py`,
  `modules/auth/users.py`, `migrations/env.py`, `0001`, `0002`, `0011`, `pyproject.toml`; las 43
  pruebas de `api/tests/architecture` (en especial `_imports.py`, `test_audit_module.py`,
  `test_audited_tables.py`, `test_service_import_graph.py`, `test_error_codes_per_route.py`,
  `test_user_limits_catalog.py`, `test_writes_have_user_limit.py`, `test_handlers_no_new_locks.py`,
  `test_guarded_calls.py`, `test_reveal_single_door.py`, `test_list_routes_use_page_params.py`,
  `test_list_rows_without_sensitive_fields.py`, `test_core_import_direction.py`,
  `test_no_physical_delete.py`, `test_events_without_pii.py`), `tests/conftest.py`,
  `tests/core/test_migrations.py`, `tests/migrations/test_triggers_siempre_activos.py`, `infra/*`,
  `scripts/ci/*.sh`, `.github/workflows/ci.yml`, `web/src/config/*`, `web/src/routes.test.ts`,
  `web/src/layouts/nav.test.ts`, `web/src/shared/ui/{HistoryAside,KpiCard}.tsx`,
  `web/src/shared/lib/audit-labels.ts`, `web/src/features/{dashboard,plans,system,members}`,
  `web/src/core/api/{errorCodes,types}.ts`, `web/tests/e2e/**`, `docs/openapi.json`, y `grep` de
  dependientes inversos sobre `api/src`, `api/tests`, `web/src`, `web/tests`, `infra` y `scripts`.
- Estado del stack con `docker compose ... ps`, `exec api alembic current` y consultas de solo
  lectura sobre `apex-db-1` (esquemas, tablas e índices de `audit` y `worker`, conteos).
- Gates baratos corridos en HEAD (sección 6): `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy src` en `api/` y `npx tsc --noEmit` en `web/`. No se corrió `pytest` ni `vitest`
  (instrucción de la Fase 0, memoria limitada). No se modificó ningún archivo fuera de este.

## 1. Inventario de contratos que el sprint consume

Cada uno marcado como: **existe** (con la firma esperada), **existe con otra firma o nombre**, o
**no existe** (lo crea el sprint o falta decidirlo).

### Auditoría (`core/audit.py`, `modules/audit`)

- `record(session, *, action, table_name, record_id, before, after, user_id=None,
  subject_member_id=None) -> AuditRow` (`core/audit.py:313`): **existe**. Toma el actor del
  contexto si no se pasa `user_id`; `AuditAction` (`:73`) ya incluye `verify` y `download`;
  `AUDIT_ACTIONS` (`:76`) es la fuente única del `CHECK`.
- `verify_chain(rows: Iterable[Mapping]) -> VerifyResult(ok, rows_checked, broken_at_seq)`
  (`:227`, `VerifyResult` en `:145`): **existe con otra firma**. Es pura, detecta salto de `seq`,
  `prev_hash` distinto, hash recalculado distinto y columnas espejo (`MIRROR_KEYS`, `:100`), pero
  **no acepta `start_prev_hash` ni `start_seq` ni devuelve `last_seq`/`last_hash`**, que US-104 T3
  necesita para verificar por lotes. Ampliarla con parámetros opcionales (compatibles con las 11
  pruebas de `tests/core/test_audit_chain.py` y las de `test_audit_log_db.py`,
  `test_audit_concurrency.py`, `test_security_events.py`, `test_reveal_entry.py` que la usan).
- `chain_hash`, `canonical`, `ZERO_HASH`, `AUDIT_CHAIN_LOCK_KEY = 4_270_002` (`:68`), `AuditEntry`
  (`:121`), `AuditRow` (`:152`): **existen**. La entrada `verify` que escriba la verificación
  toma el candado de la cadena por `record`; el candado de la verificación debe ser otra clave
  (`AUDIT_VERIFY_LOCK_KEY`, nueva; `test_sql_literals_constant.py` exige que el SQL sea constante
  de módulo con parámetros ligados y que `4_270_001` y `4_270_002` no cambien).
- `subject_member_id` (G-05): **existe completo**. Columna en `AuditEntry` (`:134`), entra al hash
  solo cuando no es nulo (`_hashed_keys`, `:214`), el hook la llena desde `__audit_subject__`
  (`_subject`, `:392`), `Member` declara `"id"`, `Membership` y `Payment` `"member_id"`
  (`test_audited_tables.py:169-183` lo exige), `reveal` la pasa (`members/detail.py:139`) y el
  índice `ix_audit_log_subject_member_seq` está aplicado en `apex-db-1`. La propuesta A de US-106
  (T1 a T3) **ya está hecha**; `0014_audit_subject_member` no hace falta, como dice el plan.
- `audit.service.recent(...)`, `list(...)`, `get(seq)`, `diff`, `member_history`,
  `history_fields`, `verify`, `last_verification`, `run_verification`, `format_verify_message`,
  `AuditVerification`: **no existen**; los crea el sprint. `modules/audit/service.py` tiene hoy
  111 líneas y solo los cuatro suscriptores de `auth`; `modules/audit/router.py` es un
  `APIRouter()` vacío (`router.py:11`).
- `modules/audit/schemas.py` y `exceptions.py`: **no existen** (regla de módulos 1: nacen con las
  rutas).

### Worker y jobs

- `core/jobs.py` (`JobRun`, `claim_run`, `finish_run`, `last_run`, `run_job`; G-06): **no
  existe**. Lo crea S4A-B1. `core/health.py` ofrece `register_health_check(name, fn, *,
  critical)` (`health.py:42`) para exponer el estado del último job en `/health` cuando US-115 lo
  pida; en este sprint no hay chequeo HTTP del worker.
- `app/worker/` (`main.py`, `jobs/`, y los `registry.py`, `schedule.py`, `runner.py` que propone
  US-113): **no existe**. `CLAUDE.md` solo lista `worker/main.py` y `worker/jobs/`: si nacen los
  otros tres, `CLAUDE.md` se corrige en el mismo cambio.
- `core/alerts.py` (`AlertSink`, `register_sink`, `alert`, `LogAlertSink`; G-08): **no existe**.
  `SPRINT-04A.md` lo cita entre las decisiones que "se aplican" y `CLAUDE.md` lo lista en `core/`,
  pero ningún slice lo nombra. Decidirlo (condición 1).
- `apscheduler>=3.10,<4` y `tzdata`: **ya instalados** (`pyproject.toml`, `uv.lock:56,67`,
  `NOTICE:8`): la imagen `apex-api:local` no necesita dependencias nuevas.
- Preámbulo de proceso sin HTTP: `cli.cli_runtime(settings, options)` (`cli.py:291-316`) instala
  `install_audit_listeners`, `install_oplog_listeners`, `install_crypto_type_listeners`, carga
  los services (`_load_module_services`, `:282`) y configura el engine; `cli.unit_of_work(actor)`
  (`:41`) fija `actor_scope` y `batch_scope`; `cli.resolve_actor(session, email)` (`:48`)
  resuelve `--as` exigiendo cuenta activa (sale con 2 si no). **Existen**: el worker debe repetir
  esos pasos (no importar `app.cli`) y los comandos nuevos (`recompute-memberships`,
  `verify-audit`) los reutilizan. El `_run` (`:348`) corre la corrutina en un hilo con copia del
  contexto cuando ya hay loop (las pruebas con `CliRunner` dependen de ello).
- `get_sessionmaker()` (`core/db.py:147`), `configure_engine`/`create_engine_from` (`:116,133`),
  `get_session`/`SessionDep` (`:223,246`): **existen**. Una transacción por lote del job se abre
  con `get_sessionmaker()()` y `session.begin()`, nunca con `get_session` (es dependencia HTTP).

### Membresías (`modules/memberships`)

- `service.refs_for(session, membership_ids) -> dict[UUID, MembershipRef]` (`queries.py:106`,
  reexportado en `service.py:52`): **existe**. `MembershipRef(member_id, member_first_name,
  member_last_name, plan_name, start_date, end_date)`; **US-110 lo describe como
  `MembershipRef(member_id, plan_id)`**: trae el nombre del plan y del socio ya resueltos (no el
  `plan_id`), lo que ahorra una llamada a `plans.names_for` para las frases de pagos.
- `service.summary(session, *, today=None) -> MembershipSummaryOut` (`summary.py:190`): **existe**,
  con caché de proceso (`SummaryCache`, TTL `SUMMARY_CACHE_TTL_S`, invalidada por eventos en el
  mismo proceso, S3-D53/S3-D93). Cuenta socios vivos por estado resuelto (`members.active_ids`,
  `members/service.py:294`).
- `service.count_active_by_plan(session, plan_id) -> int` (`queries.py:566`): **existe** con la
  definición de N-22 (estado efectivo distinto de `cancelled` y `expired`: cuenta
  `pending_payment`, `active`, `expiring` y `frozen`).
- `queries._load_freezes_for(session, membership_ids) -> dict[UUID, list[FreezeWindow]]`
  (`queries.py:166`): **existe**, privado (`PRIVATE_HELPERS["memberships"]` incluye `queries`):
  `recompute_statuses` debe vivir dentro de `memberships` (archivo privado nuevo, por ejemplo
  `expirations.py`, registrado en `_imports.PRIVATE_HELPERS`) y exportarse por `service.py`.
- `rules.compute_status(m, today, expiring_days, freezes) -> MembershipStatus` (`rules.py:240`),
  `rules.snapshot`, `rules.effective`, `queries.status_expr` (espejo SQL, `:282`): **existen**.
  Las listas ya derivan el estado efectivo en SQL (D5), así que el job solo corrige el `status`
  guardado y emite las transiciones.
- `sell.lock_membership(session, membership_id)` (`sell.py:343`, `FOR UPDATE` con
  `populate_existing=True`): **existe** y es la única puerta de `with_for_update` dentro de
  `memberships` (`test_guarded_calls.py:131-144`). `core.locks.lock_member(session, member_id)`
  (`locks.py:48`): **existe**.
- `MembershipExpiring`, `MembershipExpired`, `rules.transition_event`, `recompute_statuses`:
  **no existen**; los crea S4A-B2. Los nueve eventos actuales y sus suscriptores exactos están
  fijados en `test_handlers_no_new_locks.py:202-213` (`SUSCRIPTORES_ESPERADOS`).

### Socios (`modules/members`)

- `service.names_for(session, ids) -> dict[UUID, MemberName(id, first_name, last_name, sex)]`
  (`service.py:470`), incluidos dados de baja: **existe** (US-110 T4 pedía `include_deleted`: ya
  lo hace). `ensure_exists(session, member_id, *, include_deleted=False)` (`:275`), `get_ref`
  (`:258`), `active_ids` (`:294`), `search_ids` (`:461`): **existen**.
- Puerta de descifrado: `detail._decrypt_fields(socio, campos, purpose)` (`members/detail.py:54`)
  es el **único** sitio fuera de `core/` que puede llamar a `types.reveal`
  (`test_reveal_single_door.py:21`, `PUERTA`); `bus.batch(verb, data_class)` (`crypto/oplog.py:134`,
  reexportado por `bus`; `members/service.py:319` lo usa) agrupa las filas de `crypto_ops`;
  `OP_PURPOSES = ("mask", "reveal", "notify", "auth_link", "export")` (`crypto/models.py:65`):
  **existen**. **`bus.op_context(...)` (US-077 T2) no existe**; `contact_for_notification` debe
  pasar por `_decrypt_fields` con `purpose="notify"`/`"auth_link"` dentro de `bus.batch("decrypt",
  None)`.
- `SensitiveFieldRevealed` (US-077 T2 lo emite): **no existe y no se crea** (D19 y S3-C16:
  `reveal` audita con `audit.record` directo). US-077 debe hacer lo mismo: una fila `reveal` por
  campo con `after={"field", "purpose"}` y `subject_member_id`, sin evento.
- `SYSTEM_ACTOR` (US-077 T3): **no existe**; es `core.context.SYSTEM_USER_ID` (`context.py:37`) con
  `actor_scope`.
- `MemberError` (`members/exceptions.py`) y `MemberNotFound`: **existen**; `MemberNotContactable`
  e `invalid_purpose`: **no existen** (los crea S4A-B6).
- `members/router.py` (199 líneas): el 429 se declara por ruta (D27); `responses_for(401, 403)`
  en el router. `GET /members/{id}/audit` entra aquí (S4A-B5).

### Planes (`modules/plans`)

- `service.get(session, plan_id, *, for_share=False)` (`service.py:261`),
  `get_including_deleted` (`:272`), `names_for` (`:281`, incluye dados de baja), `validate_plan`
  (`:95`), `_id_por_nombre` (`:181`), `_insert` con `begin_nested` y traducción de
  `uq_plans_name_alive` (`:192`), `PlanSnapshot` (`schemas.py:63`), `PlanNameDuplicated(existing_id)`,
  `PlanNotFound` (`exceptions.py`): **existen**. `sell` ya lee el plan con `for_share=True`
  (riesgo 4 del Sprint 3 cerrado): la carrera baja-venta queda cubierta con `FOR UPDATE` en la baja.
- `update`, `set_active`, `deactivate_or_fail`, `merge_plan`, `PlanPatch`, `PlanUpdated`,
  `PlanDeactivated`, `PlanHasActiveMemberships`: **no existen** (S4A-B7). `plans/service.py` tiene
  314 líneas y `router.py` 60: hay sitio sin partir.
- `by: Actor` en las firmas de US-080/081/082: **no es el patrón**; el actor sale de
  `get_actor()`/`SessionDep` como en `create` (`service.py:220`).

### Auth (`modules/auth`)

- `service.names_for(session, user_ids: Sequence[UUID]) -> dict[UUID, str]` (`users.py:142`,
  reexportado en `service.py`): **existe con otra semántica**: devuelve el **correo**, no un nombre;
  no devuelve "Sistema" para `SYSTEM_USER_ID`. US-102 pide `UserRef(email, display_name)` y US-110
  pide el nombre corto.
- `auth.users.display_name` (refinamiento de US-110; `SPRINT-04A.md` lo atribuye a US-041): **no
  existe**. `auth/models.py:54-69` no tiene la columna, `0004_auth` no la crea (`grep display_name`
  en `api/src` da cero). Añadirla es una migración nueva (`0014`), fuera de la lista del plan, y
  toca `POST/PATCH /users`, `UserOut`, la pantalla Usuarios y el seed. Decidir (condición 9).
- `service.ids_by_email(session, emails) -> dict[str, UUID]` (`users.py:155`): **existe con otra
  semántica**: coincidencia exacta normalizada, no parcial. US-102 (`q` por correo parcial)
  necesita una búsqueda nueva en `auth` (`search_ids(q)` o similar); la arista `audit → auth` ya
  está en `ALLOWED_EDGES`.
- `auth.service.get_by_email` (US-105 T2): **no existe**; es `cli.resolve_actor` (que ya exige
  cuenta activa y sale con 2).

### Pagos, reloj, contexto, HTTP

- `payments.service.summary(session, month: str | None = None) -> PaymentsSummary(month,
  total_cop, by_method, voided_count, payments_count)` (`payments/queries.py:197`, `schemas.py:177`):
  **existe** para `income_month_cop`.
- `FrozenClock(instant)` con `advance(days, hours, minutes)` y `set` (`clock.py:53`),
  `current_clock()` (`:78`), `set_clock`/`reset_clock`, `to_bogota_date`, `BOGOTA` (`:25`):
  **existen**. La fixture `reloj` de `tests/conftest.py:441` congela `2026-10-21T15:00:00Z`.
  `get_clock` (`:90`) existe pero ninguna ruta lo inyecta: **US-108 T4 (`Depends` del `Clock`) debe
  usar `current_clock().today_bogota()` en el service**, patrón del repo.
- `SYSTEM_USER_ID`, `actor_scope`, `batch_scope`, `get_actor`, `MissingActorError`
  (`context.py`): **existen**.
- `responses_for(*codes)` (`errors.py:157`): **existe**, catálogo 400/401/403/404/409/422/429/500;
  **rechaza cualquier otro código** (`test_responses_for_rechaza_un_codigo_fuera_del_catalogo`):
  el 202 de `POST /audit/verify` se declara a mano en `responses={202: {"model": ...}}`, no con
  `responses_for`.
- `enforce_user_limit(request, bucket, user_id)` (`ratelimit.py:351`), `USER_LIMITS` con nueve
  cubetas (`:316`), `user_limits_from` atado a las `USER_*` de `Settings` (`:334`,
  `config.py:199-206`): **existen**. Una cubeta nueva exige campo en `Settings`, línea en
  `.env.example` (`test_env_example.py`) y ruta (`test_user_limits_catalog.py`). `admin-write`
  cubre "toda escritura de solo admin" (S3-D100): sirve para las cuatro de planes y para
  `POST /audit/verify` sin cubeta nueva.
- `PageParams`, `Page[T]`, `SearchQuery`, `paginate`, `to_page`, `chunked`, `any_uuids`
  (`core/pagination.py`), `no_store` (`core/http.py:21`), `AdminDep`/`StaffDep`
  (`security.py:502-504`), `PUBLIC_ROUTES` (ocho, `:508`): **existen**; ninguno cambia.

## 2. Blast radius por slice

### S4A-W0-1 y S4A-W0-2 · Worker en Compose

- Archivos: `infra/compose.yml` (servicio `worker`, líneas 47-60: imagen `apex-api:local`,
  `command: ["python", "-m", "app.worker.main"]`, `env_file`, `keys` ro, `uploads`, `depends_on:
  db healthy`, `profiles: ["worker"]`, `restart: unless-stopped`, **sin healthcheck**),
  `scripts/ci/test_compose_config.sh:58` (`check("worker" in prod["worker"].get("profiles", []),
  "worker queda tras un perfil hasta US-113")`), `scripts/ci/compose-smoke.sh` (no levanta `worker`),
  `.github/workflows/ci.yml` (`images` corre `test_compose_config.sh` y `compose-smoke.sh`;
  `e2e-stack` hace `up -d --build` sin perfiles: con el perfil quitado el worker arranca ahí y
  debe tolerar la espera de la base).
- Lo rompe: en W0-2, `test_compose_config.sh:58` falla al quitar el perfil (invertir la aserción
  en el mismo slice). En W0-1 nada falla si solo se agrega el healthcheck y se mantiene el perfil
  (N-3). El healthcheck "por `job_runs`" no tiene HTTP: o una consulta con `asyncpg` en un
  `python -c` (ya está en la imagen) sobre `worker.job_runs`, o un latido en archivo escrito por el
  scheduler; decidirlo en W0-1 porque `compose config` lo valida pero no lo ejecuta.
- `US-113 T13` escribe `command: ["uv", "run", ...]` y `depends_on: api: service_healthy`: la
  imagen no trae `uv` (CLAUDE.md) y Compose ya usa `python -m`; mantener lo que hay.

### S4A-B1 · `core/jobs.py`, `app/worker/`, `0012_worker_job_runs`

- Archivos nuevos: `core/jobs.py`, `worker/__init__.py`, `worker/main.py`, `worker/jobs/__init__.py`
  (y `registry.py`, `schedule.py`, `runner.py` si se siguen las tareas T4 a T7), `migrations/versions/
  0012_worker_job_runs.py`, `tests/worker/*`. Tocados: `pyproject.toml` (quitar `omit`,
  `:103-106`), `migrations/env.py` (importar `app.core.jobs` para que `target_metadata` conozca
  `worker.job_runs`; hoy importa solo los `models` de seis módulos, `env.py:30-35`), `CLAUDE.md`
  (estructura), `.env.example` y `Settings` solo si se crean `WORKER_TZ`/`WORKER_DAILY_HOUR`
  (`test_env_example.py:31-43` exige cada campo de `Settings` en `.env.example`); si se dejan
  como constantes (`America/Bogota`, 07:00 por Q28 y N-32) no hay cambio de configuración.
- Pruebas que fallan en silencio fuera del gate del slice:
  - `tests/architecture/test_audited_tables.py::test_toda_tabla_no_excluida_esta_auditada`
    recorre `Base.registry.mappers` cuyo módulo empieza por `app.`: `JobRun` en `app.core.jobs`
    entra en cuanto algo lo importe (lo hará `migrations/env.py`, `core/health.py` o
    `tests/conftest.py`) y **no declara `__audited__`** (US-113: bitácora operativa, no se audita)
    → agregar `"worker.job_runs"` a `EXCLUIDAS` (`:32`) con su motivo e importar `app.core.jobs` en
    `_cargar_modelos` (`:58`), para que `test_las_exclusiones_existen` lo encuentre siempre.
  - `test_core_import_direction.py`: `core/jobs.py` no puede importar `app.modules`
    (`test_core_no_importa_modulos`) ni cerrar ciclo con `core/health.py` si este lo importa
    (`test_sin_ciclos_entre_modulos_de_core`, solo imports de nivel de módulo). El plan amplía esta
    prueba con "solo `app.worker.*` y `app.main`/`core.health` importan `app.core.jobs`"
    (absorbe `test_core_jobs_imports.py`).
  - `test_sql_literals_constant.py` (`RAICES` incluye `core/`): el `INSERT ... ON CONFLICT
    (job_name, run_date) DO UPDATE ... RETURNING` de `claim_run` va en una constante de módulo
    con parámetros ligados, o se escribe con `postgresql.insert(...).on_conflict_do_update`.
  - `test_no_direct_now.py` recorre `src/app/**`: el worker toma "ahora" de `current_clock()`;
    `AsyncIOScheduler` usa su propio reloj internamente (no es código nuestro). `test_banned_imports.py`
    y `test_file_and_function_size.py` (50 líneas por función: el bucle principal con reintento,
    recuperación y `SIGTERM` se parte) también lo recorren.
  - `tests/core/test_migrations.py::test_downgrade_a_base_vacia_y_vuelta_a_head`: el `downgrade`
    de `0012` debe `DROP TABLE worker.job_runs` (el `DROP SCHEMA ... RESTRICT` de `0001` falla con
    una tabla olvidada). `test_single_head`.
  - `tests/conftest.py`: `LIMPIEZA_DE_SESION` (`:274`) y la limpieza de `dos_sesiones` (`:672`)
    no conocen `worker.job_runs`. Como `claim_run`/`finish_run` corren "en sesión corta y propia"
    con commit real (US-113 T3), las pruebas dejan filas y el índice único `(job_name, run_date)`
    choca entre pruebas: agregar `DELETE FROM worker.job_runs` (con `to_regclass`) en las dos
    limpiezas y limpiar por prueba (fixture) o usar `job_name` únicos.
  - `scripts/workflow/README.md` ("Cobertura (M-6)") y el comentario de `pyproject.toml`
    describen el `omit`: se actualizan al quitarlo.
- Dependientes inversos de lo que cambia: `pyproject.toml` lo leen `run-gates.sh`, `ci.yml` y
  `slice-gate.sh`; `migrations/env.py` lo usan `main.run_migrations`, `test_migrations.py` y
  `tests/conftest.py::migrated_database` (aplica `upgrade head` a `db_test` al empezar la sesión:
  `0012` y `0013` se aplican solas en las pruebas).

### S4A-B2 · `recompute_statuses`, job `expirations`, `cli recompute-memberships`

- Archivos: nuevo archivo privado en `modules/memberships/` (por ejemplo `expirations.py`) con
  `recompute_statuses`, `transition_event` en `rules.py`, dos eventos en `events.py` exportados por
  `service.py`; `worker/jobs/expirations.py`; `cli.py` (541 líneas, +~80); `tests/worker/
  test_expirations.py`, `tests/cli/test_recompute_memberships.py`, `tests/memberships/test_rules.py`.
- Pruebas que fallan en silencio:
  - `tests/architecture/_imports.py::PRIVATE_HELPERS["memberships"]` (`:34`): el archivo nuevo
    debe entrar en el conjunto, o cualquier módulo podría importarlo sin que la regla
    `private_helper` lo vea.
  - **`test_guarded_calls.py::test_lock_membership_es_la_unica_puerta_de_for_update_en_memberships`
    (`:131`)**: un `SELECT ... FOR UPDATE` por lotes en el archivo nuevo (US-094 T2) **falla la
    prueba**. Y aunque se exima, el orden de candados D3 (socio → plan → fila → cadena en el
    flush) y la advertencia S3-D95 de `core/locks.py:16-23` dicen que una transacción que bloquea
    filas de membresías de varios socios y después hace flush (candado de la cadena) puede
    interbloquearse con `freeze`/`cancel`/`sell`, que piden `lock_member` y después la fila. Opciones
    para el plan: un lote por **socio** con `lock_member` antes de la primera escritura (orden D3
    respetado; el job recorre `DISTINCT member_id`), o `lock_membership` por fila sin candado de
    socio aceptando el 40P01 ocasional (PostgreSQL corta el ciclo; `get_session` del api responde
    503 `busy`, el lote del job se revierte y se reintenta). Prueba con `dos_sesiones`
    (`tests/memberships/test_lock_order.py` es el molde).
  - `test_handlers_no_new_locks.py`: `HANDLERS_ESPERADOS` (`:29`) fija que `lifecycle.py` solo
    tiene `on_payment_registered` y `on_payment_voided`; `recompute_statuses` no es handler y no
    debe llamarse `on_*`. `SUSCRIPTORES_ESPERADOS` (`:202`) es exacto por evento: si
    `_mark_summary_dirty` se suscribe a `MembershipExpiring`/`MembershipExpired` (debe, porque el
    resumen cambia), se agregan las dos claves con `[MARCA]`.
  - `test_events_without_pii.py`: los dos eventos nuevos llevan solo `membership_id`, `member_id`,
    `end_date`, `on_date` (ninguna clave de `PROHIBIDOS`, `:36`).
  - `tests/architecture/test_no_cross_models.py` recorre solo `app/modules/*` (`:92-130`): **no**
    cubre `app/worker` ni `cli.py` como piden US-094 T10 y US-113 T12; si se quiere la garantía,
    la prueba nueva de `core/jobs` debe recorrer también `app/worker/**` con
    `find_forbidden_imports` (el worker no importa `models` de nadie).
  - Marcador: US-094 T8 dice `@pytest.mark.slow`; el registrado es `perf` (`pyproject.toml:98`,
    `--strict-markers`): usar `perf`.
  - `cli recompute-memberships --as`: `resolve_actor` exige cuenta activa (L-4); la prueba de
    "actor de auditoría = usuario indicado" sigue el patrón de `tests/cli/test_unlock_cli.py`
    (`CliRunner`, `:28-39`).
- Caché del resumen: `summary.py` invalida por eventos **del mismo proceso**; el job corre en el
  contenedor `worker`, así que el api sigue sirviendo el resumen cacheado hasta que venza
  `SUMMARY_CACHE_TTL_S` (riesgo 5, LOW; S3-D93 ya acepta un solo proceso de api).

### S4A-B3 · Verificación de la cadena (`0013`, API y CLI)

- Archivos: `core/audit.py` (502 líneas: `AuditVerification`, `verify_chain` ampliada,
  `run_verification`, `format_verify_message`, `VERIFY_BATCH_SIZE`, `AUDIT_VERIFY_LOCK_KEY` → cerca
  de 700; si pasa de 800 o alguna función de 50 líneas, partir en `core/audit_verify.py`, que
  `test_core_import_direction.py` acepta mientras no importe `core/crypto` fuera de `digest`),
  `modules/audit/{router,schemas,exceptions,service}.py`, `cli.py` (`verify-audit`),
  `migrations/versions/0013_audit_verifications.py`, `tests/core/test_verify_chain.py`,
  `tests/core/test_format_verify_message.py`, `tests/audit/test_verify*.py`,
  `tests/audit/test_router_verify.py`, `tests/cli/test_verify_audit.py`.
- Pruebas que fallan en silencio:
  - **`test_audit_module.py::test_audit_tiene_router_vacio_y_no_tiene_models` (`:69`)** afirma
    `list(router.routes) == []`: reescribirla como "tiene rutas, sigue sin `models.py`".
  - **`test_audited_tables.py`**: `AuditVerification` vive en `app.core.audit` (que `_cargar_modelos`
    importa siempre) y no se audita (US-104: su resultado ya entra a la cadena) → `"audit.verifications"`
    a `EXCLUIDAS`.
  - `test_no_physical_delete.py` (`MODELOS`/`TABLAS`, `:23-44`): agregar `AuditVerification` y
    `audit.verifications` para que un `DELETE` sobre la tabla falle en CI (append-only por N-30).
  - `tests/conftest.py`: `LIMPIEZA_DE_SESION` y `dos_sesiones` deben vaciar `audit.verifications`
    (con `DISABLE TRIGGER USER` / `DELETE` / `ENABLE ALWAYS TRIGGER <nombre>` por S3-D49, como
    `LIMPIAR_PAYMENTS`, `:263-271`) y hacerlo **antes** de borrar `audit.audit_log`; la limpieza de
    `dos_sesiones` borra `audit_log WHERE seq > :seq` (`:684`): una verificación confirmada ahí
    deja su fila y su entrada `verify`.
  - `tests/migrations/test_triggers_siempre_activos.py` fija listas exactas de triggers de
    membresías, congelaciones y pagos (`:46-56`): no cubre `verifications`; si el trigger nuevo se
    quiere en `'A'`, se agrega su tupla y se escribe el `ENABLE ALWAYS` en la limpieza.
  - `test_error_codes_per_route.py` y `test_writes_have_user_limit.py`: `POST /audit/verify` es
    una escritura autenticada no pública ni de emergencia → **debe** tener `enforce_user_limit`
    (`admin-write`), declarar 429 y entrar en `CON_LIMITE` (`:26`); `test_user_limits_catalog.py::
    test_las_rutas_con_enforce_user_limit_son_con_limite_menos_auth` exige igualdad exacta. Ambas
    rutas con `AdminDep` y 401/403; `GET /audit/verify/last` sin parámetros → sin 422; `POST
    /audit/verify` sin cuerpo → sin 422.
  - `test_no_store_routes.py`: el `APIRouter` de `audit` pasa a `dependencies=[Depends(no_store)]`.
  - `test_sql_literals_constant.py`: `pg_try_advisory_lock(:key)` como constante.
  - `tests/core/test_audit_chain.py` (11 pruebas) y las que llaman `verify_chain` con una sola
    posición: la firma ampliada mantiene los valores por defecto.
  - `tests/core/test_migrations.py`: `0013` baja trigger, índice y tabla (sin tocar
    `audit.forbid_mutation()` de `0002`, que `audit_log` sigue usando).
- Contratos: la entrada `verify` se escribe con `table_name="audit.verifications"` (el hook escribe
  siempre `esquema.tabla`, `_table_name`, `core/audit.py:386`; US-104 dice `"verifications"`), con
  `record_id = verifications.id` y `user_id = by`. El 202 se declara a mano (sección 1). La tarea
  en segundo plano necesita conexión propia (`db.get_engine().connect()`) y muere con el
  `--reload` del api de desarrollo (aceptado por N-30). En `apex-db-1` hay 4.504 filas: la
  verificación síncrona (umbral 100.000) responde en la demo. `cli verify-audit` usa `cli_runtime`
  + `resolve_actor`; el código 2 "base no disponible" se traduce desde `OSError`/`DBAPIError` al
  abrir la conexión; la prueba de rendimiento va con `perf`.

### S4A-B4 · Lista y detalle de auditoría

- Archivos: `modules/audit/{router,schemas,service}.py`, `modules/auth/users.py` y `service.py`
  (búsqueda parcial por correo nueva), `tests/audit/test_{filters,list,list_coverage_v01,
  list_performance,diff,get,router_list,router_get}.py`.
- Pruebas que fallan en silencio:
  - `test_list_routes_use_page_params.py`: `GET /audit` responde `Page_AuditRow` → exige
    `PageParams` (`Annotated[PageParams, Depends()]`), parámetro `q` y `limit` con máximo 200
    (`:81`). `test_las_listas_efectivas...` tiene un conjunto mínimo que no cambia.
  - `test_error_codes_per_route.py::test_422_solo_con_parametros_o_cuerpo`: `GET /audit/{seq}` con
    `seq: int` (`ge=1`) declara 422; `GET /audit` con filtros también.
  - `test_file_and_function_size.py`: `audit/service.py` crece con `list`, `get`, `diff`,
    `member_history`, `history_fields`, `recent`, `verify`, `last_verification`; si pasa de 800 o
    conviene, partir en `queries.py`/`verify.py` y registrar en `PRIVATE_HELPERS["audit"]`
    (`_imports.py:30`).
  - `test_audit_module.py::test_audit_no_importa_models_router_ni_helpers_de_otros_modulos`:
    `audit` solo importa `service`, `schemas` y `exceptions` ajenos; `AuditEntry` viene de
    `core.audit` (permitido).
- Contratos: `q` busca `record_id` exacto o correo del usuario (`auth`); el placeholder de
  `Auditoria.html` dice "Nombre del socio o id del registro": buscar por nombre de socio no está
  en US-102 (sería cruzar `audit` con `members`); `// DESIGN-GAP:` en F1. `AuditRow.user_email` es
  válido aquí (la regla de sufijo `_email` solo aplica bajo `/members`, sección B5).

### S4A-B5 · Historial del socio

- Archivos: `modules/members/{router,service}.py` (`history`), `modules/audit/{service,schemas}.py`
  (`member_history`, `MemberHistoryItem`, `history_fields`), `tests/architecture/test_audit_subject.py`,
  `tests/audit/test_{history_fields,member_history}.py`, `tests/members/test_router_member_audit.py`.
- Pruebas que fallan en silencio:
  - **`test_service_import_graph.py`**: `members.service.history` importando `audit.service` crea
    la arista de nivel de módulo `members → audit`, que no está en `ALLOWED_EDGES` (`:52`) y rompe
    `test_solo_existen_las_aristas_del_mapa_de_contextos` y la aserción `arriba["members"] ==
    set()` de `test_el_par_perezoso_members_memberships_existe_y_esta_permitido` (`:264`). El
    grafo queda acíclico (`audit → auth` solamente). Agregar la arista y reescribir la aserción en
    el Rojo. La alternativa (publicar `/members/{id}/audit` desde el router de `audit`, como hace
    `memberships` con `/members/{id}/memberships`) crearía `audit → members` y, con
    `members → memberships → members`, no cierra ciclo tampoco, pero el plan pone la ruta en
    `members` (`slice-gate.sh members` con `test_router_member_audit.py`): seguir el plan.
  - `test_list_routes_use_page_params.py`: la ruta responde `Page_MemberHistoryItem` → **necesita
    `q: SearchQuery`** (US-106 solo declara `limit` y `offset`), como pasó con las pestañas en S3.
  - **`test_list_rows_without_sensitive_fields.py`** recorre todo `GET` bajo `/api/v1/members` con
    `Page_*` y rechaza campos `document`, `phone`, `email`, `birth_date`, `emergency_contact` y
    cualquier sufijo `_idx`, `_hint` o **`_email`** (`:33-34`): `MemberHistoryItem` lleva
    `user_name` (como dice la historia) y **nunca `user_email`**; `fields` es una lista de nombres
    de campo, no de valores.
  - `test_error_codes_per_route.py`: la ruta es de lectura; sin `enforce_user_limit` no declara
    429 (igual que `GET /members/{id}/memberships`); con `{member_id}` declara 422; 404 por
    `MemberNotFound` (reutilizar `members.exceptions.MemberNotFound`, no duplicarlo en `audit`).
  - `test_audited_tables.py::test_membership_freezes_es_requerida_y_no_declara_sujeto_hasta_us_106`
    (`:186`) documenta que las congelaciones no llevan sujeto: US-106 decide que aparecen por la
    fila `update` de la membresía; la prueba se renombra o conserva con esa decisión anotada.
- Front: `shared/lib/audit-labels.ts` modela `AuditEntryView {id, at, actor_id, actor_name,
  entity, action, before, after}` (`:11-24`) con un `// DESIGN-GAP:` que espera el contrato real;
  el api entrega `{seq, at, user_id, user_name, action, table_name, record_id, fields}` sin
  `before`/`after`: `summarizeChange` (basado en `before`/`after`) debe aceptar `fields`
  (adaptador en `features/members` o cambio en `shared/lib`, slice `web/shared`). `HistoryAside`
  ya existe con su prueba (`kit-inventory`); `MemberDataTab.tsx:14` anota la caja "Historial
  reciente" como pendiente de US-106.

### S4A-B6 · Contacto para avisos

- Archivos: `modules/members/{detail,service,exceptions}.py` (o `contact.py` nuevo, registrado en
  `PRIVATE_HELPERS["members"]`, `_imports.py:38`), `tests/members/test_{service_contact,
  validate_purpose}.py`, `tests/architecture/test_crypto_bus_importers.py`.
- Pruebas que fallan en silencio: `test_reveal_single_door.py` (`PUERTA = ("modules/members/
  detail.py", "_decrypt_fields")`, `:21`; cualquier otra llamada a `types.reveal` o a
  `bus.decrypt` fuera de `core/` falla) → `contact_for_notification` llama a `_decrypt_fields`;
  `test_events_without_pii.py` no se toca si no hay evento (S3-C16). Importadores reales de
  `app.core.crypto.bus` hoy fuera de `core/`: `modules/members/service.py:73` y
  `modules/members/changes.py:50`; la lista blanca de `test_crypto_bus_importers.py` debe
  describirlos (`app.core.*`, `app.modules.members`; `athletes` y `attachments` cuando existan).
- Contrato: sin ruta (regla de `test_every_route_has_role.py` no aplica); `Contact` dataclass con
  `repr=False`; `MemberNotContactable` sin HTTP; `invalid_purpose` es `MemberError`. El propósito
  `mask` se rechaza (N-21). El consumidor (EP-14) llega en el Sprint 5: en este sprint nada lo
  llama en `src/`.

### S4A-B7 · Editar, activar/desactivar y dar de baja planes

- Archivos: `modules/plans/{service,schemas,exceptions,router}.py`, `tests/plans/test_{merge_plan,
  service_update,router_update,service_set_active,router_set_active,service_deactivate_or_fail,
  router_delete}.py`, `tests/integration/test_rn04_plan_price_change.py`, `tests/integration/
  test_plan_deactivation_with_memberships.py` (la carpeta `tests/integration/` no existe; el gate
  acepta cualquier archivo bajo `api/tests/`).
- Pruebas que fallan en silencio:
  - **`test_service_import_graph.py::test_plans_no_importa_services_y_solo_memberships_lo_importa`
    (`:281`)** afirma `perezosas["plans"] == set()`: el import perezoso de `memberships.service`
    en `deactivate_or_fail` la rompe. `("plans", "memberships")` ya está en `LAZY_IMPORT_WHITELIST`
    (`:65`) y la línea lleva `# lazy: G-03 (plans -> memberships)` (`LAZY_MARK`,
    `test_todo_import_perezoso_lleva_su_comentario`). Reescribir: `perezosas["plans"] ==
    {"memberships"}`; con B8, `importadores == {"memberships", "dashboard"}`.
  - **`test_writes_have_user_limit.py`**: `PATCH /plans/{id}`, `POST .../activate`,
    `POST .../deactivate` y `DELETE /plans/{id}` son escrituras no públicas → `enforce_user_limit(
    request, "admin-write", ...)`, 429 declarado y entrada en `CON_LIMITE`
    (`test_error_codes_per_route.py:26`) o la prueba falla en su Rojo.
  - `test_guarded_calls.py::test_fuera_de_memberships_nadie_nombra_membership` (`:163`): `plans`
    no puede nombrar `Membership`; solo usa `count_active_by_plan`. `with_for_update` sobre `Plan`
    en `plans/service.py` está permitido (la prueba restringe solo la carpeta `memberships`).
  - `test_events_without_pii.py`: `PlanUpdated(plan_id, changed_fields: tuple[str, ...])` lleva
    nombres de campo (como `MemberUpdated`), nunca el `name` nuevo; `PlanDeactivated(plan_id)`.
  - `test_no_physical_delete.py` ya cubre `plans.plans`; la baja es `update` con `deleted_at`.
  - `test_error_codes_per_route.py::test_422_solo_con_parametros_o_cuerpo`: las cuatro tienen
    `{plan_id}` → 422; `DELETE` responde 204 y 409 `plan_has_active_memberships`.
- Orden de candados: la baja toma `FOR UPDATE` del plan y después hace flush (cadena); `sell` toma
  socio → plan `FOR SHARE` → flush. Una baja nunca pide un socio: no hay inversión; `FOR SHARE`
  espera a `FOR UPDATE` y al revés, sin ciclo. Un plan con membresías `pending_payment` (los de
  `e2e:stack`) **no se puede dar de baja** hasta anular esas membresías (N-22): la limpieza de
  P2-1 necesita `POST /memberships/{id}/cancel` previo para esos casos (riesgo 9).
- Diseño `Planes.html`: trae la columna **"Socios con él"** (D37: "queda para US-082, Sprint 4A") y
  la acción "Editar". US-082 solo usa el conteo en el 409 de la baja. Mostrar la columna exige un
  campo nuevo en la fila de `GET /plans` (contrato) y un conteo por lote (`count_active_by_plan`
  es por un plan: con 166 planes vivos sería N+1). Decidir en el plan: contrato
  `counts_active_by_plans(ids)` en `memberships` + campo en `PlanOut` (B7 y F4), o `// DESIGN-GAP:`
  en F4 y la columna en 4B (condición 8).
- Front F4: `PlansPage.tsx` no tiene acciones por fila (`:16`, `// DESIGN-GAP:` lo anota),
  `PlanDetailPanel` es de solo lectura y `PlanForm` solo crea; `permissions.ts` ya tiene
  `plans.manage` (admin); `planErrors.ts` recibe `plan_has_active_memberships`;
  `web/tests/e2e/stack/plans.spec.ts` captura "Detalle del plan" y puede cambiar.

### S4A-B8 · Tablero

- Archivos nuevos: `modules/dashboard/{__init__,router,schemas,service}.py` (sin `models.py`),
  `modules/audit/service.py` (`recent`), `tests/dashboard/*`, `tests/audit/test_recent.py`,
  `tests/architecture/test_read_modules.py`. Tocados: `main.py` (`MODULES`, `:55`), `modules/auth`
  si "Sistema"/`display_name` se resuelve ahí.
- Pruebas que fallan en silencio:
  - **`test_audit_module.py::test_modules_de_v01_incluye_audit_despues_de_auth` (`:44`)** afirma la
    tupla literal de siete entradas: `dashboard` va al final (nadie lo importa; importa a todos).
  - **`test_service_import_graph.py`**: aristas nuevas de nivel de módulo `dashboard → memberships`,
    `dashboard → payments`, `dashboard → audit`, `dashboard → members`, `dashboard → plans` (si usa
    `plans.names_for`; con `refs_for` puede no hacer falta) y `dashboard → auth`; cada arista
    declarada debe existir de verdad (`test_cada_arista_permitida_existe`) y el par se importa en
    subproceso limpio en los dos órdenes (`PARES_EN_AMBOS_ORDENES`). `test_plans_no_importa_
    services_y_solo_memberships_lo_importa` cambia su conjunto de importadores.
  - `test_audited_tables.py::_cargar_modelos` tolera módulos sin `models` (`find_spec`); nada que
    hacer. `test_no_store_routes.py`, `test_session_scope.py`, `test_every_route_has_role.py`:
    router con `no_store`, `SessionDep`, `StaffDep`. `test_error_codes_per_route.py`:
    `GET /dashboard` sin parámetros ni cuerpo → **no** declara 422; `responses_for(401, 403)` basta.
  - `test_no_cross_schema_sql.py`: `dashboard` no escribe SQL literal con tablas ajenas (solo llama
    services).
  - `test_handlers_no_new_locks.py::SUSCRIPTORES_ESPERADOS`: `dashboard` no se suscribe a nada.
- Contratos: `last_movements` lee `after`/`before` de filas de `members`, `memberships` y
  `payments`. Las de `members` traen blobs `apx1.` en `document`, `phone`, `email`, `birth_date` y
  `emergency_contact` (el hook serializa todas las columnas no técnicas, `core/audit.py:351-371`):
  la vista reducida con lista blanca de llaves (US-110 T1) y la prueba que busca `apx1.` en la
  respuesta serializada no son opcionales. `auth.service.names_for` devuelve correos: "Sistema"
  para `SYSTEM_USER_ID` y el nombre corto dependen de la decisión de `display_name` (condición 9).
  `Inicio.html` saluda "Hola, Ana · martes 20 de octubre": hoy `InicioPage` saluda con el correo
  (`InicioPage.test.tsx:18`); con la opción (b) de la condición 9 el saludo usa la parte local del
  correo hasta que exista la columna.

### S4A-F1 a S4A-F4 · Front

- Reglas del front que fijan el estado del Sprint 3 y fallan en silencio:
  - `web/src/config/features.test.ts:10-13`: exactamente ocho features habilitadas
    (`ENABLED_FEATURES`, `features.ts:34`); F1 agrega `audit` → nueve.
  - `web/src/routes.test.ts:72-91`: lista literal de rutas con `load`; F1 agrega
    `/sistema/auditoria` (la fila existe sin `load`, `routeTable.ts:146`); F2 agrega la hija
    `/socios/:id/historial` y la aserción `:127` de los hijos de la ficha (`["index",
    "/socios/:id/membresias", "/socios/:id/pagos"]`) cambia. `routes.reference.ts` debe llevar la
    hija nueva (la prueba `:35` compara tabla y referencia): hoy no tiene ninguna ruta `historial`
    de la ficha.
  - `web/src/layouts/nav.test.ts:14`: etiquetas exactas del admin; con `audit` entra "Auditoría"
    entre "Usuarios y roles" y "Configuración" (orden del catálogo, `:25`).
  - `web/src/features/members/pages/MemberDetailPage.test.tsx:101-114`: Historial deshabilitada y
    última; `MemberDetailPage.tsx:57` tiene `disabledUntil: "v0.1 · Sprint 4A"`.
  - `web/src/features/dashboard/pages/InicioPage.test.tsx`: saludo con el correo, accesos del
    Sprint 2 y el texto "El tablero ... llega en la próxima versión" (`:40`): F3 lo reemplaza.
    US-109 nombra `HomePage.tsx`; la ruta carga `features/dashboard/pages/InicioPage`
    (`routeTable.ts:103`): conservar `InicioPage` o cambiar la tabla (la prueba de rutas no fija el
    nombre del archivo).
  - `web/tests/lint/boundaries.test.ts`: ninguna feature importa de otra. Los cruces previstos no
    aparecen (AuditPage, AuditDetailPanel y VerifyChainButton en `features/system`;
    `encryptedBlob.ts` en `shared/lib`; `MemberHistoryTab` en `features/members` sobre
    `shared/ui/HistoryAside`; `KpiGrid`/`LastMovements` en `features/dashboard` con enlaces a
    `/socios` y `/pagos` por `href`).
  - `web/tests/kit-inventory.test.ts`: `<Nombre>.test.tsx` por componente de `shared/ui`; nada
    nuevo en el kit salvo que se cree.
  - `web/src/core/api/errorCodes.test.ts`: cada código de `API_ERROR_CODES` debe existir literal
    en `api/src`; los nuevos (`plan_has_active_memberships`, `verification_running`, el 404 del
    detalle de auditoría, el 404 de la verificación) entran solo después de su slice de backend.
  - `web/src/core/api/types.ts` se regenera con `npm run gen:api` tras cada slice de backend que
    publica rutas (CI: "tipos del api al día").
  - `web/tests/unit/playwright-config.test.ts:33` fija los proyectos `preview` y `stack`; el
    proyecto `stack` corre `web/tests/e2e/stack/**` y `preview` el resto (`playwright.config.ts:
    20-26`). `home.spec.ts` (US-109 T8: login real y datos) va en `tests/e2e/stack/` si quiere
    datos reales, o en `tests/e2e/` con MSW. `web/tests/e2e/stack/plans.spec.ts`,
    `member-tabs.spec.ts` y `member-detail.spec.ts` capturan pantallas que F2 y F4 cambian.
  - `role-guards.spec.ts` (preview) comprueba que el coach no ve "Sistema" ni "Planes": la
    auditoría (admin) no cambia eso.
- Diseño: `Auditoria.html` llama al botón "Verificar ahora" (el plan dice "Verificar cadena"),
  filtra por Desde, Hasta, Usuario (incluye "sistema (worker)"), Entidad, Acción, Registro, y la
  tabla tiene la columna "Qué cambió (anterior → nuevo)" que la lista del api no trae (RN-13: el
  antes/después solo en el detalle, US-103) → `// DESIGN-GAP:` en F1. `Inicio.html`: "al día",
  "vencidas"/"Vencidos", "Ingresos de octubre", "Por avisar hoy", "Asistencia de la semana", "Hoy
  en el box", "WOD de hoy", "Últimos movimientos" — coincide con `KpiCard.availableIn`.
  `Socio_Ficha.html` solo tiene "Historial reciente" y el enlace "historial completo →".

### Archivos que el sprint no debe tocar

`core/crypto/*` (la puerta `_decrypt_fields` y `bus.batch` cubren US-077), `core/db.py`,
`core/context.py`, `core/events.py`, `core/pagination.py`, `core/errors.py` (los códigos nuevos son
subclases de `DomainError`; el 202 se declara en la ruta), `core/security.py` (`PUBLIC_ROUTES`
sigue en 8), `core/locks.py`, migraciones `0001` a `0011`, `tests/core/_principal_double.py`,
`infra/nginx/*` (no hay rutas nuevas con cabeceras distintas), `infra/compose.e2e.yml`,
`modules/payments/*` (solo se lee `summary`), `modules/settings/*`.

## 3. Capa de datos

### Lo que existe (aplicado en `apex-db-1`; `db_test` se migra desde cero en cada sesión)

- `exec api alembic current` = `0011_payments_immutability (head)`. Cadena lineal `0001 → … →
  0011`; `0011_payments_immutability.py:36` es la cabeza a la que se encadena `0012`.
- Esquemas `audit` y `worker` creados por `0001_core_schemas` (`SCHEMAS`, `:23-32`) y presentes en
  `pg_namespace`. En `worker` **no hay tablas**. En `audit` solo `audit.audit_log` con los índices
  `pk_audit_log`, `uq_audit_log_seq`, `ix_audit_log_at`, `ix_audit_log_table_record`,
  `ix_audit_log_user_id`, `ix_audit_log_table_seq` y `ix_audit_log_subject_member_seq`: los de
  US-102 (`at`, `(table_name, record_id)`, `user_id`), US-110 (`(table_name, seq DESC)`) y US-106
  (`(subject_member_id, seq DESC)`) ya existen; **no hacen falta `0014_audit_subject_member` ni
  índices nuevos**. Trigger `audit_log_forbid_mutation` y función `audit.forbid_mutation()`
  (`0002_audit_log.py:77-93`) listas para reutilizar en `0013`.
- Datos de desarrollo: 4.504 filas de auditoría, 228 socios, 138 membresías, 166 planes vivos
  (30 `E2E-tope-*` y los de las specs; P2-1).

### Lo que agrega el sprint

- `0012_worker_job_runs` (S4A-B1): `worker.job_runs` con columnas comunes, `job_name` (CHECK de
  forma), `run_date`, `started_at`, `finished_at`, `result` (CHECK con los estados del backup de
  US-115 incluidos), `error`, `details JSONB`; único `(job_name, run_date)`; índice
  `(job_name, started_at DESC)`; `downgrade` con `DROP TABLE`. `down_revision =
  "0011_payments_immutability"`. Sin `__audited__`. Reejecución del mismo día: la misma fila,
  intento agregado en `details.attempts` (US-113, corrección 2).
- `0013_audit_verifications` (S4A-B3): `audit.verifications` con `started_at`, `finished_at`,
  `through_seq`, `rows_checked`, `ok`, `broken_at_seq`, `triggered_by`, `source` (`api`/`cli`),
  columnas comunes, `CHECK` de coherencia `ok`/`broken_at_seq` y de fechas, índice
  `(finished_at DESC)`, trigger `BEFORE UPDATE OR DELETE` (y `TRUNCATE`) con
  `audit.forbid_mutation()` ya existente, preferiblemente `ENABLE ALWAYS` (S3-D49);
  `downgrade` quita trigger, índice y tabla y **no** la función (es de `0002`).
- Ninguna migración de datos. Si la condición 9 elige `display_name` en 4A, aparece una `0014`
  en tres pasos (columna nula, llenar con la parte local del correo, decidir si obligatoria):
  no está en el plan y debe anotarse en `SPRINT-04A.md` y `DECISIONES.md`.

### Riesgos de orden y de la suite

- Orden de slices igual a la cadena (B1 → B3); `alembic heads` en el gate de B1 y B3 si hay
  worktrees.
- El `api` de desarrollo monta `../api/migrations` por bind y corre `upgrade head` en cada
  reinicio de `--reload` (`compose.dev.yml:11-17`): un `0012_*.py` a medio escribir se aplica (o
  rompe el arranque) en `apex-db-1`. Misma mitigación del Sprint 3: redactar y probar contra
  `db_test` (`pytest tests/core/test_migrations.py`) antes de dejarlo en `migrations/versions`, o
  parar `api` mientras se escribe.
- `pg_dump -Fc` de `apex-db-1` antes de `0012` y de `0013` (P-MIG; `*.dump` está en `.gitignore`
  por N-5; se borra al cerrar, como en V12).
- Limpieza de `db_test`: `worker.job_runs` y `audit.verifications` entran en `LIMPIEZA_DE_SESION`
  y en `dos_sesiones` (sección 2).
- Rollback: `downgrade 0012` y `0013` bajan solos; `RUNBOOK.md` §6 gana sus dos entradas.

## 4. Servicios Docker y estrategia de rebuild

- Estado: `apex-db-1` healthy (`127.0.0.1:5442`), `apex-db_test-1` healthy (`127.0.0.1:5443`, 6
  días arriba), `apex-api-1` healthy (`127.0.0.1:8181`, bind de `src` y `migrations`, `--reload`),
  `apex-web-1` healthy (`0.0.0.0:8180`). Imágenes `apex-api:local` (2026-10-28 15:39) y
  `apex-web:local` (16:24); el último commit que toca `api/` es `7962caa` (15:32) y el último de
  `web/` `6c98eb6` (16:07): **las imágenes corresponden al código de HEAD**. `apex-api:ci` del
  2026-10-21 sigue en el host sin uso.
- Cómo corre cada servicio: `api` con bind de `src/` y `migrations/` (cambios sin rebuild);
  `worker` y `tools` **sin bind** (`compose.yml:47-79`; `compose.dev.yml` solo cubre `api`, `web`,
  `db`, `db_test`): ejecutan el código **de la imagen** (`Dockerfile:19-21` copia `src`,
  `alembic.ini` y `migrations`). Consecuencia: cada vez que B1 o B2 cambien el worker, o la demo
  use `tools verify-audit`/`tools recompute-memberships`, hace falta reconstruir `apex-api:local`.
  Opción de desarrollo: agregar a `compose.dev.yml` el mismo bind `../api/src:/app/src` al servicio
  `worker` (y a `tools`), de modo que `run --rm worker ... --run-once` use el código del árbol sin
  rebuild; la imagen de producción no cambia. `web` sin bind: F1 a F4 exigen rebuild para verse en
  `:8180` y para los E2E del proyecto `stack`.
- Quirk del equipo (RUNBOOK §7, `docs/scratch/sprint-03.md:14-16`): `docker compose build` y `up
  --build` fallan (Compose 5.6.1 + buildx 0.38.1 rechazan `build.network: host`). Se construye con
  `docker buildx build --load --network host --allow network.host -t apex-api:local -f
  api/Dockerfile api` y `... -t apex-web:local -f web/Dockerfile .` y se levanta con `up -d
  --no-build`. **No se reconstruyó nada en esta fase.** En la CI (Linux, sin `compose.dev.yml`) no
  aplica.
- N-3 (CRITICA-2): el servicio `worker` conserva `profiles: ["worker"]` hasta cerrar S4A-B1. En
  W0-1 solo `compose config`, `test_compose_config.sh` (que hoy **exige** el perfil) y el smoke sin
  el perfil. En W0-2: quitar el perfil, invertir la aserción de `test_compose_config.sh:58`,
  reconstruir `apex-api:local` con buildx, `up -d --no-build worker`, comprobar `ps worker`
  (en ejecución 30 s sin reinicios, healthy si se define healthcheck) y `run --rm worker python -m
  app.worker.main --run-once expirations` con código 0 y fila en `worker.job_runs`; ampliar
  `compose-smoke.sh` con ese paso para que el job `images` de CI lo cubra. El job `e2e-stack`
  (`up -d --build`) arrancará el worker sin perfil: debe esperar la base (reintento exponencial
  de US-113) y no entrar en bucle de reinicio.
- Nginx no cambia (`/api/` ya con `no-store` y `limit_req` solo en `/api/v1/auth/`): sin
  `test_nginx_conf.sh` ni `headers.sh` salvo al cerrar. Imágenes base por digest: ya renovadas el
  2026-10-22 (S3-D62); el plan decide si se renuevan al abrir el sprint (RUNBOOK §7) o en 4B.

## 5. Contratos API

### Estado de `docs/openapi.json` en HEAD

39 rutas y 53 operaciones (auth 7, users 9, settings 8, members 8, plans 3, memberships 6,
payments 5, health 1). No hay rutas `audit`, `dashboard` ni escrituras de `plans` más allá de
`POST /plans`. `web/src/core/api/types.ts` coincide (CI "tipos del api al día").

### Los 10 endpoints nuevos frente a las pruebas que vigilan el contrato

- `GET /api/v1/audit` (admin): `Page[AuditRow]` con `PageParams`, `q` y `limit ≤ 200`; filtros
  `from`/`to` (`AwareDatetime`, alias `from`), `user_id`, `table`, `record_id`, `action` en
  `AUDIT_ACTIONS`; 401/403/422. `user_email` permitido (no está bajo `/members`).
- `GET /api/v1/audit/verify/last` (admin): `VerifyResultOut | null`; sin parámetros → sin 422.
  Registrada **antes** de `GET /audit/{seq}`; con `seq: int` en el path la colisión real no
  existe (dos segmentos), pero el orden se mantiene por claridad (D-04 del plan).
- `GET /api/v1/audit/{seq}` (admin): `seq: int ≥ 1` (422 con `abc`), 404 por `seq` inexistente
  (código nuevo, por ejemplo `audit_entry_not_found`); `before`/`after` con blobs tal cual, nunca
  descifrados (`test_reveal_single_door.py` lo garantiza a nivel de código).
- `POST /api/v1/audit/verify` (admin): 200 `VerifyResultOut` o **202** `VerifyStartedOut`
  (declarado a mano), 409 `verification_running`, 429 (`admin-write`), 401/403; sin cuerpo → sin
  422. Entra en `CON_LIMITE` y en el conjunto exacto de `test_user_limits_catalog.py`.
- `GET /api/v1/members/{member_id}/audit` (admin y coach): `Page[MemberHistoryItem]` con
  `PageParams`, **`q: SearchQuery`**, `limit ≤ 200`, 404 `member_not_found`, 422; filas sin campos
  sensibles ni sufijo `_email`; sin 429.
- `GET /api/v1/dashboard` (admin y coach): `DashboardOut` con los cinco conteos, `income_month`,
  `income_month_cop`, `last_movements: list[MovementOut]` (≤10) y los campos futuros presentes en
  `null`; sin parámetros → sin 422; sin 429.
- `PATCH /api/v1/plans/{plan_id}` (admin): `PlanPatch` (`extra="forbid"`, `StrictInt`,
  `model_fields_set`), 200 `PlanOut`, 404, 409 `plan_name_duplicated`, 422, 429 (`admin-write`).
- `POST /api/v1/plans/{plan_id}/activate` y `/deactivate` (admin): 200 `PlanOut` idempotentes,
  404, 422, 429 (`admin-write`).
- `DELETE /api/v1/plans/{plan_id}` (admin): 204, 404, 409 `plan_has_active_memberships` (con el
  conteo en `message`), 422, 429 (`admin-write`).
- Roles frente a `web/src/core/auth/permissions.ts`: `audit.view` (ADMIN, `:33`), `dashboard.view`
  (STAFF, `:39`), `plans.view`/`plans.manage` (ADMIN, `:28-29`): coinciden. El historial de la
  ficha va con `members.view` (STAFF).
- Cubetas: ninguna nueva en `USER_LIMITS`; las cinco escrituras usan `admin-write` (30 por
  minuto, `USER_ADMIN_WRITE_LIMIT_PER_MIN`). Las lecturas nuevas no limitan (como `GET
  /memberships/summary` y las pestañas de la ficha).
- Códigos nuevos que `errorCodes.ts` (y `planErrors.ts`) deben conocer: `plan_has_active_memberships`,
  `verification_running`, el 404 del detalle de auditoría, el 404 de "sin verificaciones" si se
  decide 404 en vez de `null`; `invalid_purpose` y `member_not_contactable` no salen por HTTP.
- Cada slice de backend que publica rutas (B3, B4, B5, B7, B8) termina con `export-openapi` y
  `npm run gen:api`.

### Contradicciones entre desgloses y código que el plan cierra en T-DOC

- `verify_chain(rows, start_prev_hash, start_seq) -> VerifyResult(..., last_seq, last_hash)` →
  ampliar la firma actual (`core/audit.py:227`) con valores por defecto.
- `bus.op_context(...)`, `SensitiveFieldRevealed`, `SYSTEM_ACTOR` (US-077) → `detail._decrypt_fields`
  + `bus.batch`, `audit.record` directo (S3-C16), `SYSTEM_USER_ID`.
- `auth.service.get_by_email` (US-105) → `cli.resolve_actor`; `auth.service.ids_by_email(q)` parcial
  (US-102) → búsqueda nueva en `auth`.
- `auth.service.names_for -> UserRef(email, display_name)` (US-102/US-110) → hoy devuelve el
  correo; depende de la condición 9.
- `memberships.service.refs_for -> MembershipRef(member_id, plan_id)` (US-110) → trae
  `plan_name` y los nombres del socio.
- `Depends(Clock)` (US-108 T4) → `current_clock()` en el service.
- `table_name="verifications"` (US-104) → `"audit.verifications"`.
- `by: Actor` (US-080/081/082) → `get_actor()`.
- `@pytest.mark.slow` (US-094 T8, US-102 T8, US-104 T11, US-108 T8) → `perf`.
- `test_service_import_cycles.py` / `ALLOWED_LAZY` (US-082 T7) → `test_service_import_graph.py` /
  `LAZY_IMPORT_WHITELIST` (ya contiene el par).
- `command: ["uv", "run", ...]` y `depends_on: api` (US-113 T13) → lo que ya está en
  `compose.yml`.
- `HomePage.tsx` (US-109) → `InicioPage.tsx`; `0014_audit_subject_member` (US-106) → ya está en
  `0002`.
- `test_no_cross_models.py` "barre `app/worker` y `cli.py`" (US-094 T10, US-113 T12) → hoy solo
  recorre `app/modules`; la prueba nueva de `core/jobs` lo cubre si se quiere.

## 6. Línea base en HEAD `f5f2503`

- `git log --oneline -3`: `f5f2503 docs(sprint-03): cierre: hashes, citas, dueños, -m perf y p2-1
  (v12)`, `2e6748d docs(sprint-03): matriz verify-delivery (v11)`, `8ef1a91 docs(sprint-03): gates
  completos, higiene y dueños al cierre (v12)`. `git status` limpio; `git worktree list` solo el
  principal. Desde `6c98eb6` (zod 4) solo cambian documentos.
- Suites (no corridas aquí; cita de `docs/scratch/sprint-03.md`, "V9.1 · run-gates.sh completo",
  2026-10-28 sobre `aacd8b0`, mismo código que HEAD): api `pytest -m "not perf"` **3.883 ok, 3
  saltadas (NTFS), 8 `perf` deseleccionadas**, 11 min 04 s, cobertura global de `app` **97 %**
  (6.835 sentencias, 165 sin cubrir; con `cli.py` y `worker/*` todavía en `omit`); front **2.788
  pruebas en 156 archivos, 97,98 % de sentencias, 98,87 % de líneas**, lint, `tsc` y build en
  verde; scripts de infraestructura en verde.
- Corrido en esta fase (HEAD, árbol limpio):
  - `cd api && uv run ruff check .` → `All checks passed!` (código 0).
  - `cd api && uv run ruff format --check .` → `415 files already formatted` (código 0).
  - `cd api && uv run mypy src` → `Success: no issues found in 97 source files` (código 0).
  - `cd web && npx tsc --noEmit` → sin salida, código 0.
- Stack (`docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml ps`): los
  cuatro contenedores healthy; `exec api alembic current` = `0011_payments_immutability (head)`.
- `.env` local (solo nombres): `WEB_PORT=8180`, `API_PORT=8181`, `DB_PORT=5442`,
  `DB_TEST_PORT=5443`, `TEST_DATABASE_URL` hacia `127.0.0.1:5443/apex_test`. `.env` y `.env.seed`
  no están versionados (`.env.seed` se borró en S3-W0-1).

## 7. Bugs, desajustes de configuración y el pendiente de "revisión de diseño previa al Sprint 4A"

1. `CLAUDE.md` lista `core/jobs.py` y `core/alerts.py` que no existen. `jobs.py` nace en B1;
   `alerts.py` no está en ningún slice y `SPRINT-04A.md` cita G-08 como aplicado. No bloquea: el
   worker de v0.1 informa fallos por log (N-34); decidir si se crea un `core/alerts.py` mínimo
   (`AlertSink`, `register_sink`, `alert`, `LogAlertSink`) en B1 para cumplir la estructura, o se
   difiere a v0.2 con nota en `DECISIONES.md` y `CLAUDE.md` corregido.
2. `SPRINT-04A.md`, "Dependencias de sprints anteriores", atribuye `display_name` a US-041
   (Sprint 2). US-041 no la creó: `auth.users` no tiene `display_name` y el refinamiento de US-110
   ("se agrega `auth.users.display_name`, respaldo: parte local del correo") sigue abierto. El
   plan solo lista `0012` y `0013`. Contradicción que el plan debe cerrar (condición 9).
3. `scripts/ci/test_compose_config.sh:58` exige el perfil del worker: correcto hasta W0-2 y falla
   justo al quitarlo (invertir en el mismo slice).
4. US-104 T3 describe una `verify_chain` por lotes que no es la del código; US-104 T4 pone
   `run_verification` en `core/audit.py` (502 líneas): vigilar el tope de 800 y 50.
5. `test_no_cross_models.py` no recorre `app/worker` ni `cli.py` (US-094/US-113 lo dan por hecho).
6. `responses_for` no admite 202: el `POST /audit/verify` lo declara aparte.
7. `audit-labels.ts` espera `before`/`after` en el historial; el api de US-106 entrega `fields`.
8. `e2e-stack` en CI arranca el worker en cuanto se quite el perfil; `compose-smoke.sh` no lo
   prueba hasta que W0-2 lo agregue.
9. **Pendiente "revisión de diseño previa al Sprint 4A"** (`DECISIONES.md`, "Dueños asignados al
   cierre del Sprint 3"; `BRECHAS.md` §10.14). Son dos cosas y esta Fase 0 es su dueño:
   - **S3-D98** (orden "Vencimiento más próximo" en `GET /members`). Qué es: una ordenación que
     cruza `members` con `memberships` dentro de la consulta de socios; fuera de v0.1. Las dos
     salidas posibles (puerto de lectura en `members` o consulta de `memberships` que devuelva
     socios ordenados) no están en ninguna historia de 4A ni de 4B. Veredicto: **no bloquea y no
     se absorbe en 4A**; queda fuera de v0.1 con dueño "backlog v0.2, junto a EP-16 (exportar
     listas)", y el planner lo anota en `DECISIONES.md` (T-DOC de W0-1) para que deje de estar sin
     sprint.
   - **"Pendiente de diseño" de §10** ("Guardar y vender membresía", estilo de "Cancelada",
     "Ocultar anulados", selector de mes de pagos, tarjeta de la futura, "Nueva venta…" del
     selector, estado posterior del panel). `docs/design/` no cambió desde el cierre del Sprint 3
     (las pantallas que este sprint toca son `Auditoria`, `Inicio`, `Planes` y `Socio_Ficha`): no
     hay diseño nuevo que resolverlas. Veredicto: **no bloquean y no cambian código en 4A**;
     conservan su estado en §10 y el planner lo deja escrito. Lo que sí entra como brecha nueva de
     este sprint: "Socios con él" de `Planes.html` (sección 2, B7), la columna "Qué cambió" y la
     búsqueda por nombre de socio de `Auditoria.html`, y el saludo con nombre de `Inicio.html`;
     cada una con su `// DESIGN-GAP:` o su decisión en el slice que la toca.
10. P2-1 (166 planes vivos, la venta muestra 100): `DELETE /plans/{id}` (B7) permite retirar los
    `E2E-tope-*` sin membresías; los que tienen ventas `pending_payment` exigen anular esas
    membresías antes (N-22). Es limpieza de datos de desarrollo, no código; se hace tras B7 con
    un script o a mano y se anota en el cuaderno.
11. `.env.example` solo cambia si `Settings` gana variables (`WORKER_*`); `test_env_example.py` lo
    vigila. Ninguna cubeta nueva.

## 8. Riesgos del plan ampliados con lo visto en el código

1. [HIGH] Candados del recálculo diario (US-094) frente a `test_guarded_calls.py` y al orden D3
   /S3-D95: un `FOR UPDATE` por lotes falla la prueba y abre interbloqueos con `freeze`/`cancel`/
   `sell` a las 07:00 (o en `--run-once` durante el día). Mitigación: condición 3 (lote por socio
   con `lock_member`, o `lock_membership` por fila aceptando el 40P01 con reintento) y prueba con
   `dos_sesiones`.
2. [HIGH] `display_name` y "Sistema" (US-110/US-102): sin decisión, B4 y B8 no pueden fijar
   `AuditRow.user_name` ni las frases, y una migración `0014` fuera del plan rompería la regla de
   "una cabeza" si se improvisa. Mitigación: condición 9, decidida antes de B4.
3. [MEDIUM] Cobertura al quitar el `omit` (M-6): `worker/main.py` (scheduler, reintento, `SIGTERM`)
   y los comandos nuevos de `cli.py` entran al 80 % global; hoy 97 % con margen, pero el bucle
   principal es difícil de cubrir. Mitigación: `main.py` delgado (lógica en `schedule.py`/
   `runner.py` puras y probadas), `--run-once` cubierto por `CliRunner`/subproceso, y
   `run-gates.sh` tras B2 y tras B3.
4. [MEDIUM] Trece pruebas literales que fijan el estado del Sprint 3 (sección 2) rompen fuera del
   gate del slice si no se actualizan en el Rojo correspondiente; `tests/architecture` corre en
   todos los gates (A-5), así que se ven de inmediato, pero cada una cuesta un ciclo si no está
   prevista. Mitigación: condiciones 1 a 10.
5. [MEDIUM] Tamaño de archivos: `core/audit.py` (502 → ~700), `modules/audit/service.py` (111 →
   ~500), `cli.py` (541 → ~700), `members/service.py` (483 → ~560). Mitigación: partir desde el
   slice que los hace crecer (`core/audit_verify.py`, `audit/queries.py` en `PRIVATE_HELPERS`).
6. [MEDIUM] Verificación en segundo plano con conexión dedicada y `pg_try_advisory_lock`: el
   `--reload` del api de desarrollo mata la tarea; una excepción sin `finally` dejaría el candado
   tomado hasta que muera la conexión. Mitigación: `finally` que libera, prueba con el umbral bajado
   por monkeypatch y prueba de 409 con el candado tomado desde `dos_sesiones`.
7. [MEDIUM] Worker y `tools` sin bind: cada cambio exige rebuild con buildx (quirk del equipo).
   Mitigación: bind de `src` para `worker` y `tools` en `compose.dev.yml` (solo desarrollo) o
   aceptar el rebuild por slice y anotarlo en el cuaderno.
8. [MEDIUM] Fronteras de imports: tres aristas nuevas de nivel de módulo (`members → audit`,
   `dashboard → *`) y una perezosa (`plans → memberships`); `MODULES` gana `dashboard`. Mitigación:
   condiciones 6, 8 y 9; `test_service_import_graph.py` en cada gate.
9. [LOW] P2-1: planes con membresías `pending_payment` no se pueden dar de baja sin anular antes.
10. [LOW] Caché del resumen de membresías (`SUMMARY_CACHE_TTL_S`) no se invalida desde el proceso
    del worker: el tablero y los chips muestran el estado anterior hasta vencer el TTL después del
    ciclo de las 07:00. Aceptado por S3-D93; anotarlo en RUNBOOK §10.
11. [LOW] `last_movements`: las filas `insert`/`update` de `members` traen blobs `apx1.`; una vista
    reducida mal filtrada los expondría al coach. Mitigación: lista blanca de llaves y prueba que
    busca `apx1.` en la respuesta completa (US-110 T1, T8).
12. [LOW] `MembershipFreeze` sin `subject_member_id`: las congelaciones aparecen en el historial
    solo por la fila `update` de la membresía (aceptado en S3; US-106 lo confirma).
13. [LOW] `q` del historial y de la auditoría aceptado pero con semántica reducida (no busca por
    nombre de socio): `// DESIGN-GAP:` en F1 y F2.

## 9. Condiciones para VERDE

Se incorporan al plan de la Fase 1; el plan-critic las verifica.

1. S4A-B1 (Rojo) actualiza lo que `core/jobs.py` y `worker/` rompen: `tests/architecture/
   test_audited_tables.py` (`EXCLUIDAS` con `worker.job_runs` y `_cargar_modelos` importando
   `app.core.jobs`), `test_core_import_direction.py` ampliada (`core/jobs` no importa `modules`;
   solo `app/worker/**` y `core/health`/`main` lo importan; opcionalmente recorre `app/worker/**`
   con `find_forbidden_imports`), `tests/conftest.py` (`DELETE FROM worker.job_runs` con
   `to_regclass` en `LIMPIEZA_DE_SESION` y `dos_sesiones`, limpieza por prueba de `job_runs`),
   `migrations/env.py` (import de `app.core.jobs`), `pyproject.toml` (quitar `omit`) con
   `scripts/workflow/README.md` y `CLAUDE.md` (estructura real de `worker/`; `core/alerts.py`:
   crear el mínimo `LogAlertSink` o quitarlo de la estructura y anotar G-08 diferido a v0.2 en
   `DECISIONES.md`). Zona y hora del ciclo como constantes (`America/Bogota`, 07:00) salvo que el
   plan quiera `WORKER_*` en `Settings` (entonces `.env.example`).
2. S4A-W0-1 define el healthcheck del worker sin HTTP (consulta a `worker.job_runs` con `asyncpg`
   en `python -c`, o latido en archivo) y deja el perfil; S4A-W0-2 quita el perfil, invierte
   `scripts/ci/test_compose_config.sh:58`, agrega a `scripts/ci/compose-smoke.sh` el paso del
   worker (`ps` en ejecución 30 s y `run --rm worker python -m app.worker.main --run-once
   expirations` con código 0), reconstruye `apex-api:local` con buildx antes de `up -d --no-build`
   y decide si `compose.dev.yml` monta `../api/src` en `worker` y `tools` para no reconstruir en
   cada slice.
3. S4A-B2: `recompute_statuses` vive en un archivo privado nuevo de `memberships` (en
   `PRIVATE_HELPERS["memberships"]`) y se exporta por `service.py`; no usa `with_for_update` fuera
   de `sell.lock_membership` (`test_guarded_calls.py`): lote por socio con `lock_member` antes del
   primer flush (orden D3) o `lock_membership` por fila con reintento del lote ante 40P01, con
   prueba de interbloqueo sobre `dos_sesiones`; `MembershipExpiring`/`MembershipExpired` entran en
   `SUSCRIPTORES_ESPERADOS` de `test_handlers_no_new_locks.py` con `_mark_summary_dirty`;
   marcador `perf`; `cli recompute-memberships --date --as` con `cli_runtime` y `resolve_actor`.
4. S4A-B3: `test_audit_module.py` deja de exigir el router vacío; `EXCLUIDAS` gana
   `audit.verifications`; `test_no_physical_delete.py` gana `AuditVerification`/`audit.verifications`;
   `tests/conftest.py` vacía `audit.verifications` (`DISABLE TRIGGER USER`/`DELETE`/`ENABLE ALWAYS
   TRIGGER`) antes de `audit_log` en las dos limpiezas; `verify_chain` se amplía con parámetros
   opcionales sin romper `test_audit_chain.py`; `AUDIT_VERIFY_LOCK_KEY` nuevo y SQL constante; el
   202 se declara a mano; `POST /audit/verify` consume `admin-write`, declara 429 y entra en
   `CON_LIMITE`; la entrada `verify` usa `table_name="audit.verifications"`; `core/audit.py` se
   parte si supera 800 líneas o 50 por función; `cli verify-audit --as --wait-timeout` sale con 2
   por `--as` inválido o base caída.
5. S4A-B4: `GET /audit` con `Annotated[PageParams, Depends()]`, `q: SearchQuery` y `limit ≤ 200`;
   `auth` gana una búsqueda parcial por correo (la arista `audit → auth` ya existe);
   `GET /audit/{seq}` con `seq: int ≥ 1` registrada después de `/audit/verify/last`;
   `modules/audit/service.py` se parte en privados (`PRIVATE_HELPERS["audit"]`) si crece.
6. S4A-B5: la ruta `GET /members/{member_id}/audit` vive en `members/router.py` y
   `members.service.history` importa `audit.service` a nivel de módulo: `ALLOWED_EDGES` gana
   `("members", "audit")` y la aserción `arriba["members"] == set()` de
   `test_service_import_graph.py:264` pasa a `{"audit"}`; la ruta acepta `q: SearchQuery`;
   `MemberHistoryItem` no lleva `user_email` ni campos sensibles; reutiliza
   `members.exceptions.MemberNotFound`; `test_audit_subject.py` fija los tres modelos con
   `__audit_subject__`; `test_membership_freezes_es_requerida_y_no_declara_sujeto_hasta_us_106`
   se renombra con la decisión de US-106.
7. S4A-B6: `contact_for_notification` descifra por `detail._decrypt_fields` con `purpose`
   `notify`/`auth_link` dentro de `bus.batch("decrypt", None)`, audita con `audit.record` directo
   (sin `SensitiveFieldRevealed`, S3-C16) y usa `SYSTEM_USER_ID` de `core.context`;
   `test_crypto_bus_importers.py` parte de los importadores reales (`core/*`,
   `members/service.py`, `members/changes.py`); un `members/contact.py` nuevo entra en
   `PRIVATE_HELPERS["members"]`.
8. S4A-B7: las cuatro escrituras de planes consumen `admin-write`, declaran 429 y entran en
   `CON_LIMITE`; `test_plans_no_importa_services_y_solo_memberships_lo_importa` se reescribe
   (`perezosas["plans"] == {"memberships"}`; importadores `{"memberships", "dashboard"}` tras B8);
   el import perezoso lleva `# lazy: G-03 (plans -> memberships)`; `plans` no nombra `Membership`;
   `PlanUpdated.changed_fields` solo nombres; `plan_has_active_memberships` llega a `errorCodes.ts`
   y `planErrors.ts`; el plan decide "Socios con él" (`Planes.html`): contrato por lote
   `counts_active_by_plans(ids)` y campo en la fila de `GET /plans` en B7/F4, o `// DESIGN-GAP:`
   con dueño 4B.
9. S4A-B8 (y antes de B4): `MODULES` gana `"dashboard"` al final y `test_audit_module.py:47`
   cambia; `ALLOWED_EDGES` gana solo las aristas `dashboard → …` que de verdad se importen;
   router con `no_store`, `StaffDep`, `responses_for(401, 403)` y sin 422; `current_clock()` en el
   service; `test_read_modules.py`; vista reducida de `audit.service.recent` con lista blanca de
   llaves y prueba `apx1.`. **Decisión de `display_name` (pregunta 1 de US-110)**: (a) migración
   `0014_auth_display_name` en tres pasos más `UserOut`/`UserCreate`/`UserPatch`, seed y pantalla
   Usuarios, añadida a "Migraciones que aplica" de `SPRINT-04A.md`; o (b) sin columna en 4A:
   `auth.service.names_for` devuelve `UserRef(email, display_name=<parte local>)` y "Sistema" para
   `SYSTEM_USER_ID`, y la columna pasa a 4B con dueño. Se anota en `DECISIONES.md` y se corrige la
   mención a US-041 en `SPRINT-04A.md`.
10. Front: S4A-F1 actualiza `features.test.ts` (nueve features), `routes.test.ts` (lista con
    `/sistema/auditoria`), `nav.test.ts` ("Auditoría" entre "Usuarios y roles" y "Configuración"),
    `routeTable.ts:146` con `load`, y pone `// DESIGN-GAP:` en la columna "Qué cambió" y la búsqueda
    por nombre de `Auditoria.html` (botón con el texto del diseño, "Verificar ahora"); S4A-F2 agrega
    la hija `/socios/:id/historial` en `routeTable.ts` y `routes.reference.ts`, actualiza
    `routes.test.ts:127` y `MemberDetailPage.test.tsx:101-114`, y adapta `audit-labels.ts` a
    `fields` (slice `web/shared` con su prueba); S4A-F3 reemplaza `InicioPage.test.tsx`, conserva
    `InicioPage` (o cambia `routeTable.ts:103`) y ubica `home.spec.ts` en `tests/e2e/stack/` o en
    `tests/e2e/` según use datos reales o MSW; S4A-F4 agrega las acciones por fila y revisa
    `tests/e2e/stack/plans.spec.ts`. Cada slice de backend que publica rutas regenera
    `docs/openapi.json` y `types.ts`, y `errorCodes.ts` gana sus códigos.
11. Migraciones: `pg_dump -Fc` de `apex-db-1` a `docs/scratch/sprint-04a-antes-0012.dump` y
    `-0013.dump` antes de aplicar cada una (se borran al cerrar); cada migración se prueba contra
    `db_test` (`tests/core/test_migrations.py`, ciclo `upgrade head → downgrade -1 → upgrade head`)
    antes de dejarla en `migrations/versions` o con el `api` parado; `alembic heads` = 1 en los
    gates de B1 y B3; `RUNBOOK.md` §6 gana las entradas de `0012` y `0013`.
12. Cobertura (M-6): el `omit` se quita en S4A-B1 junto con `tests/worker` (y `tests/cli` del
    comando nuevo en B2); `run-gates.sh` se corre al cerrar B2 y de nuevo al cerrar B3 (CLI
    `verify-audit`), no solo al final.
13. T-DOC (W0-1): los desgloses corrigen los nombres de la sección 5 (`verify_chain`, `bus.op_context`,
    `SensitiveFieldRevealed`, `SYSTEM_ACTOR`, `get_by_email`, `ids_by_email` parcial, `refs_for`,
    `Depends(Clock)`, `table_name`, `by: Actor`, `slow`, `test_service_import_cycles.py`,
    `command: uv run`, `HomePage.tsx`, `0014_audit_subject_member`), y `DECISIONES.md` registra el
    cierre de la "revisión de diseño previa al Sprint 4A" (sección 7, punto 9): S3-D98 fuera de
    v0.1 con dueño de backlog, pendientes de diseño de §10 sin cambio, y las tres brechas nuevas
    de `Planes.html`, `Auditoria.html` e `Inicio.html` con su slice.

## Riesgos residuales (no bloquean)

- `--reload` con polling reinicia el api a mitad de un E2E del proyecto `stack` y mata una
  verificación en segundo plano; no editar `src/` durante la corrida.
- Las tres pruebas saltadas por NTFS se verifican en el job `api` de CI (Linux).
- El worker en `e2e-stack` corre el ciclo del día si el contenedor arranca después de las 07:00
  de Bogotá (recuperación de arranque tardío): con la base de CI vacía no cambia nada, pero deja
  una fila en `worker.job_runs` que `datosDeBase()` no espera; revisar `stack.ts` si alguna spec
  cuenta tablas.
- `apex-api:ci` del 2026-10-21 en el host es una imagen vieja sin uso local; no interfiere.
- El resumen cacheado del api tras el recálculo del worker (riesgo 10) es visible solo durante
  `SUMMARY_CACHE_TTL_S` después de las 07:00.
