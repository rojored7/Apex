# Análisis de impacto previo · Sprint 5 (v0.2: OpenBao, avisos de vencimiento, recibos y exportaciones)

Fecha: 4 de noviembre de 2026 (línea base tomada entre las 11:20 y las 11:55 hora local).
Alcance: `update` sobre un repositorio con código (`flow-update`, Fase 0).
Anclaje: rama `feat/sprint-05-openbao-avisos-recibos`, HEAD `a1ad4cb` ("docs(sprint-04b): V12
limpieza y cierre del Sprint 4B", igual a `main`), `git status` limpio, un solo worktree
(`git worktree list` solo muestra `C:/Users/PC/Proyectos/Apex a1ad4cb`).
Plan de referencia: `docs/ddd/09_sprint_plan/SPRINT-05.md` (20 historias: US-120 a US-132 de EP-14,
US-133 a US-136 de EP-15 y US-137 a US-139 de EP-16; 78 puntos y 323 h; "bloques en orden de
ejecución, sin slices: el sprint se refina al llegar"; Wave 0 `openbao`, Waves 3a y 3b con los
bloques A (OpenBao), B (avisos) y C (recibos y exportaciones), Waves 5a y 5b de front; migraciones
"en los rangos reservados" EP-15 0030-0034, EP-14 0020-0029, EP-16 0035-0039; 22 endpoints nuevos y
4 cambiados; `/health` gana `crypto`).

## Veredicto: AMARILLO

Se puede avanzar a la Fase 1 con `--allow-amber`. Nada es ROJO: todo lo que el sprint consume del
Sprint 4B y anteriores existe (`KeyProvider`, `LocalFileProvider`, `Keyring`, `ensure_keys`,
`crypto_keys.provider` con CHECK `local|openbao`, `crypto_jobs.kind` con `migrate_provider` y su
índice de un solo job en curso, `register_health_check(name, fn, *, critical, allowed, healthy)`,
`HealthOut` con `backup` y `migrations`, `core/alerts.py` con `AlertSink`/`register_sink`/`alert`,
`core/events.py`, el worker con `JobSpec`/`JobResult(status)`/`run_job`, `contact_for_notification`,
`recompute_statuses`, `MembershipExpiring`/`MembershipExpired`, `AUDIT_ACTIONS` con `download` y
`export`, `OP_PURPOSES` con `notify`/`auth_link`/`export`, `members.service.names_for`,
`memberships.service.refs_for`/`status_for`/`member_ids_by_status`, `auth.service.names_for`,
`settings.service.get_section`/`payment_methods`, `payments.service.summary`, `age` en la imagen del
api), `apex-db-1` está en `0014_audit_log_triggers_always (head)`, el stack (seis contenedores) está
sano, las imágenes `apex-api:local` y `apex-web:local` llevan la etiqueta de revisión `a1ad4cb` (=
HEAD) y `ruff`, `ruff format --check`, `mypy --strict` (151 archivos) y `tsc --noEmit` pasan en HEAD.
El amarillo viene de ocho cosas que el plan debe fijar antes de tocar código.

Primera, **el puerto `KeyProvider` ya es `async` y `wrap(dek)`/`unwrap(wrapped)` no llevan
`key_ref`** (`core/crypto/provider.py:30-42`): el desglose de EP-15 supone un puerto síncrono con
`httpx.Client` y `anyio.to_thread`, y SPRINT-05 fija `wrap(key_ref, dek)`; además `bootstrap._create_missing`
escribe `provider="local"` literal (`bootstrap.py:63`), `Keyring.load_all` desenvuelve todas las filas
con un único proveedor (`keyring.py:96-101`), `get_key_provider` responde `unknown_provider` ante
`openbao` (`provider.py:54-57`) y `missing_secrets` solo comprueba archivos del proveedor local
(`config.py:548-553`). Segunda, **el trigger `crypto.guard_keys_update()` de `0003` prohíbe cambiar
`provider` y `wrapped_material`** (`0003_crypto.py:213-215`): `migrate-provider` exige una migración
nueva que extienda la guarda (el plan lo dice), pero `0030_crypto_jobs_single_running` y
`0031_crypto_provider_openbao` **no hacen falta** (el índice `uq_crypto_jobs_in_progress` sobre
`coalesce(data_class, '*')` y el CHECK `provider IN ('local', 'openbao')` ya están en `0003`), y la
cadena real es lineal `0001` → `0014`: la siguiente es `0015`, no `0030`. Tercera, **el estado
degradado no existe y choca con el arranque y con Compose**: `main._startup` relanza cualquier fallo
de `ensure_keys` (el api no acepta tráfico, `main.py:132-157`), `CryptoError` no tiene handler en
`core/errors.py` (hoy sería 500 `internal_error`), no existen `CryptoState`, `load_deks`,
`ensure_available` ni `health_state`, `HealthOut` no declara `crypto`, el 503 del OpenAPI lleva el
texto fijo "Base de datos ocupada" (`MENSAJE_503`, `errors.py:43`), y **en `infra/compose.yml` `web`
y `worker` dependen de `api` `service_healthy` con un healthcheck que exige HTTP 200**
(`compose.yml:118-124,140-146,232-234`): con OpenBao sellado al reiniciar el servidor, `web` y
`worker` nunca arrancan, lo contrario de la mitigación del riesgo 2 del plan ("Nginx no depende de la
salud del api"); `infra/deploy.sh:289-301` usa `curl -f` y falla con cualquier 503. Cuarta, **el worker
no puede hoy ni descifrar ni omitir por sellado**: `worker/runtime.py` no carga el keyring, el
servicio `worker` no monta `keys` ni token (`compose.yml:131-134`, `test_compose_config.sh:86` lo
exige "hasta el Sprint 5"), `apex_worker` no tiene `SELECT` ni `UPDATE (updated_at)` sobre
`crypto.crypto_keys` (`infra/db/grants.sql`), `JobSpec` no tiene `needs_crypto`, y `RESULTS` y el
CHECK `ck_job_runs_result` de `0012` no admiten `skipped`. Quinta, **doce pruebas de arquitectura
fijan por igualdad exacta cosas que el sprint cambia**: `CONTACT_CALLERS == frozenset()`
(`test_contact_callers.py:27,106`), `ALLOWED_EDGES` y `LAZY_IMPORT_WHITELIST`
(`test_service_import_graph.py:54-77`), los privados de `members` (`{rules, detail, changes, contact}`,
`test_no_cross_models.py:167-170`), `len(PUBLIC_ROUTES) == 8`, `ENABLED_SECTIONS`/`SECTION_REGISTRY`
("exactamente las cuatro"), `ALERT_CONTEXT_KEYS` (seis claves, valores `str|int`), `DETAIL_KEYS`
(solo enteros), `IMPORTADORES_REALES` del bus, el conjunto de archivos del worker, la matriz
`PRIVILEGIOS` de `test_db_grants.py` y el `ARRAY` `clasificadas` de `grants.sql` (fail-closed:
`dbsetup` detiene todo ante una tabla sin clasificar), `ENABLED_FEATURES.size == 9` del front
(`features.test.ts:11-12`). Sexta, **contratos de los desgloses con otro nombre o firma en el
código**: `memberships.service.labels_for`/`current_for`/`notification_candidates`/
`has_current_or_future` no existen (`refs_for` y `status_for` cubren los dos primeros),
`members.service.exists` es `ensure_exists(session, id, *, include_deleted)`,
`contact_for_notification(session, member_id, purpose)` no tiene `fields`, `settings.channels` responde
404 `section_not_available`, `auth.forgot` no lee la base por decisión H-2/S2-D36 (US-131 la cambia),
`test_core_no_modules.py` ya existe consolidado como `test_core_import_direction::test_core_no_importa_modulos`.
Séptima, **dependencias y licencias sin verificar**: `reportlab`, `aiosmtplib`, `pypdf` no están en
`pyproject.toml` ni `uv.lock`; `reportlab` arrastra `pillow` (licencia HPND / "MIT-CMU", que
`check-licenses-api.sh` acepta solo si `pip-licenses` la reporta con la palabra `MIT`) y
`charset-normalizer`; las imágenes de OpenBao (MPL-2.0 sin modificar) y Mailpit (MIT) no están en el
host y `test_images_pinned.sh` exige digest con fecha en los dos compose; `notice.sh` solo escribe un
bloque literal. Octava, **la deuda con dueño "v0.2 / Sprint 5" del cierre del 4B no tiene slice en
`SPRINT-05.md`**: Caddy y TLS (D45, D66), `apex_owner` NOSUPERUSER (D206), `audit.append()` y los
residuales de `INSERT` (D61), `rewrap` y compromiso de la KEK (D137, D148, D151), verificación
criptográfica del manifiesto en el worker y en `retire-key` (D57, D80, D149), `UPDATE` por columna en
`auth.users` y `SELECT` acotado del worker (D203, D204), `INSERT` de pagos sin columnas de anulación
(D202), `display_name`, índices de `audit_log` con condición (D5), firma de etiquetas (D181, D208).
Todo se absorbe con las condiciones de la sección 9; ninguna exige cambiar el alcance de las veinte
historias, pero C1 (T-DOC) y C3 (Compose y salud) deben cerrarse antes de la Wave 0.

## Cómo se verificó

- Lectura completa de `SPRINT-05.md`, `README.md` del plan (índice, "Cómo se cierra un sprint",
  riesgos del Sprint 5), los tres `BREAKDOWN.md` de EP-14, EP-15 y EP-16 y el README del desglose,
  las tres épicas, las cuatro historias de EP-15 completas y las secciones de alcance, criterios y
  notas técnicas de US-122, US-123, US-124, US-126, US-127, US-131, US-137 y US-138 (las demás por
  búsqueda de contratos), `docs/ddd/impacto/sprint-04b.md` (referencia de formato), los bloques
  "Estado al cierre del Sprint 4B" y "Dueños asignados al cierre del Sprint 4B" de `DECISIONES.md`
  (más S4B-D206), `02_domain_model.md` §2.10 y §2.13, `03_context_map.md` (§1, §2 "Avisos", §5 G-04),
  `04_architecture_decision.md` §4 y §5, `05_service_design.md` (puertos `NotificationChannel` y
  `AlertSink`, contratos de `notifications`, `export`, `receipt_pdf`, `today_count`),
  `docs/BRECHAS.md` §2 ("Avisos", "Recibo en PDF", "Exportar listas", "Recuperación y activación"),
  §7 y §12, `docs/design/ROUTES.md` completo y los textos de `PorAvisarHoy.html`, `Notif_Reglas.html`,
  `Notif_Historial.html`, `Pagos.html`, `Socios_Lista.html`, `Config.html`, `Inicio.html`,
  `Login.html` y `Socio_Ficha.html` (claro y oscuro existen para los tres de avisos), `CLAUDE.md`,
  `docs/RUNBOOK.md` (índice y §11-§12), `docs/adr/ADR-002-criptografia.md`, `infra/README.md`.
- Lectura del código que el sprint toca o consume (secciones 1 y 2): `main.py`, `cli.py`,
  `cli_base.py`, `cli_ops/__init__.py`, `core/{health,alerts,events,errors,audit,config,context,
  http,jobs,ratelimit,security,db,backup_status,migrations_status}.py`, `core/crypto/{provider,
  local_provider,bus,keyring,bootstrap,registry,errors,models,oplog,service,archive,kek_backup,
  discovery}.py`, `worker/{main,registry,runner,runtime}.py`, `worker/jobs/__init__.py`, los
  `service.py` de `members` (y `contact.py`, `detail.py`), `memberships` (y `queries.py`,
  `expirations.py`, `events.py`), `payments` (y `router.py`), `dashboard` (y `schemas.py`), `settings`
  (y `schemas.py`), `auth` (y `links.py`, `users.py`, `schemas.py`), `migrations/env.py`, `0003`,
  `0012`, `0014`, `infra/compose.yml`, `compose.dev.yml`, `infra/db/grants.sql`, `infra/deploy.sh`,
  `infra/nginx/default.conf`, `.env.example`, `.env.ops.example`, `api/pyproject.toml`, `uv.lock`
  (grep), `api/Dockerfile`, `NOTICE`, `web/package.json`, `.github/workflows/ci.yml`,
  `scripts/ci/{check-licenses-api,test_compose_config,test_images_pinned,compose-smoke}.sh`,
  `scripts/ci/licenses-exceptions.txt`, `scripts/workflow/slice-gate.sh`, las 55 pruebas de
  `api/tests/architecture` (en especial `test_contact_callers`, `test_crypto_bus_importers`,
  `test_service_import_graph`, `test_third_party_confinement`, `_imports`, `test_banned_imports`,
  `test_worker_boundaries`, `test_core_import_direction`, `test_health_check_registrars`,
  `test_app_layer_importers`, `test_no_store_routes`, `test_writes_have_user_limit`,
  `test_user_limits_catalog`, `test_settings_no_secrets`, `test_file_and_function_size`,
  `test_read_modules`, `test_events_without_pii`, `test_error_codes_per_route`,
  `test_audited_tables`, `test_audit_subject`, `test_no_cross_models`, `test_every_route_has_role`,
  `test_list_routes_use_page_params`, `test_list_rows_without_sensitive_fields`,
  `test_kek_path_single_door`, `test_gates_registered`), `tests/migrations/test_db_grants.py`,
  `tests/conftest.py` (limpieza), `tests/core/{test_migrations,test_env_example}.py`,
  `docs/openapi.json` (63 operaciones, 47 rutas; `HealthOut`, `DashboardOut`),
  `web/src/config/{features,features.test,routeTable,routes.reference}.ts`,
  `web/src/core/auth/permissions.ts`, `web/src/layouts/nav.ts`, `web/src/core/api/types.ts`,
  `web/src/features/{dashboard,auth,system}/` y `web/src/shared/{ui,lib,data}/`.
- Estado del stack con `docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml
  ps`, `exec api alembic current`, `docker image ls`, `docker image inspect` (etiqueta
  `org.opencontainers.image.revision`), `docker compose version`, `netstat` de los puertos 80, 8000,
  5432, 5433 y 8200, y `which age bao openbao gh jq`. **No se reconstruyó ninguna imagen ni se tocó el
  stack.**
- Gates baratos corridos en HEAD (sección 6): `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy src` en `api/` y `npx tsc --noEmit` en `web/`. No se corrió `pytest` ni `vitest`
  (instrucción de la Fase 0). No se modificó ningún archivo fuera de este.

## 1. Inventario de contratos que el sprint consume

Cada uno marcado como: **existe** (con la firma esperada), **existe con otra firma o nombre**, o
**no existe** (lo crea el sprint o falta decidirlo).

### Bus de criptografía y proveedor (`core/crypto/`, EP-15)

- `KeyProvider` (`provider.py:30-42`): `async wrap(dek: bytes) -> bytes`, `async unwrap(wrapped:
  bytes) -> bytes`, `async sign(key_ref, data)`, `async verify(key_ref, data, signature)`, `async
  rotate(key_ref) -> KeyInfo`, `async key_info(key_ref) -> KeyInfo`: **existe con otra firma**. El
  docstring ya dice "los métodos son `async` porque OpenBao se habla con `httpx.AsyncClient`"
  (US-023 T2): el desglose de EP-15 ("el puerto sigue siendo síncrono y `OpenBaoProvider` usa
  `httpx.Client`; el bus las ejecuta con `anyio.to_thread.run_sync`") contradice el código y a la
  propia US-134 (`httpx.AsyncClient`). `wrap`/`unwrap` **no llevan `key_ref`**: SPRINT-05 fija
  `wrap(key_ref, dek)` y `unwrap(key_ref, wrapped)` (US-134); `LocalFileProvider` ignora el
  argumento y `bus.sign`/`bus.verify` ya pasan `_key_ref(llave)` (`bus.py:125-157`). Llamadores de
  `wrap`/`unwrap` que cambian con la firma: `bootstrap._create_missing` (`:66`), `keyring._load_rows`
  (`:96`), `core/crypto/service.py` (`_swap_key`, rotación, `:223`) y `kek_backup.verify_wrapped`
  (que abre con `AESGCM` directo, no por el puerto). Decidir en C2.
- `LocalFileProvider(kek_path, signing_key_path)` (`local_provider.py:69`), `check_key_file`,
  `parse_wrapped`, `WRAP_PREFIX = b"apxw1"`, `SIGNING_KEY_REF = "local:sign-ed25519"`,
  `PROVIDER_NAME = "local"`: **existen**. La envoltura `apxw1` queda en las filas `local`; con
  OpenBao `wrapped_material` guarda el texto `vault:v<n>:...` (N-03; `LargeBinary`, cabe).
- `get_key_provider(settings)` (`provider.py:44-57`): **existe con otra forma**: con
  `CRYPTO_PROVIDER == "openbao"` lanza `CryptoError("unknown_provider", "proveedor de llaves no
  disponible en esta versión")`. El desglose pide "registro de proveedores `providers: dict[str,
  KeyProvider]`" y "proveedor por fila": hoy hay un solo `_provider` de proceso
  (`configure_provider`/`current_provider`). `Settings.CRYPTO_PROVIDER: Literal["local",
  "openbao"]` (`config.py:175`) **existe**; `OPENBAO_ADDR`, `OPENBAO_TOKEN_PATH`,
  `OPENBAO_TIMEOUT_S`, `CRYPTO_RECOVERY_POLL_S` **no existen** (ni en `.env.example`, que dice
  "openbao desde v0.2"; `test_env_example.py:32` exige que cada campo nuevo de `Settings` esté ahí).
- `Keyring` (`keyring.py:44`): `load_all(session, provider)`, `refresh_if_stale`, `ensure_loaded`,
  `provider` (atributo), `_load_rows` que desenvuelve `active`/`decrypt_only` con **el único
  proveedor recibido**: **existe con otra forma**; la desenvoltura "por fila según
  `crypto_keys.provider`" (criterio 4 de US-135) exige que `_load_rows` elija el proveedor por
  `fila.provider`. `current_keyring()` sin keyring lanza `CryptoError("crypto_unavailable")`
  (`:149-152`): es la semilla natural del estado sellado.
- `bootstrap.ensure_keys(session, provider) -> Keyring` y `_create_missing` (`bootstrap.py:50-87`):
  **existen con otra forma**: `provider="local"` literal en el `INSERT` (`:63`) y `SIGNING_KEY_REF`
  del proveedor local para las llaves `sign`. Con `CRYPTO_PROVIDER=openbao`, una llave nueva (por
  ejemplo tras `rotate-key`) debe nacer `openbao` con su `key_ref` de Transit. Hoy ninguna clase
  tiene `sign=True` (`registry._V01`), así que no hay fila `sign` en `apex-db-1` (8 llaves: 5
  `encrypt`, 3 `index`); `apex-sign-audit` de US-133 se crea en Transit pero EP-17 la usa.
- `bus.py`: `encrypt`, `decrypt`, `blind_index`, `sign`, `verify`, `digest`, `batch`: **existen**;
  síncronas salvo `sign`/`verify`. `CryptoState`, `load_deks()`, `ensure_available()`,
  `health_state(provider_status, deks_loaded)`: **no existen**. `encrypt`/`decrypt`/`blind_index`
  ya fallan con `crypto_unavailable` sin keyring (vía `current_keyring()`); `digest` no (SHA-256 sin
  llave: el desglose pide que también lance; no hace falta, N-06).
- `CryptoError` (`errors.py`): `CryptoCode` ya incluye `crypto_unavailable`, `unknown_provider`,
  `key_missing`, `unwrap_failed`: **existe**. `CryptoSealed`, `CryptoUnreachable`, `CryptoForbidden`
  y `map_error(status, body)` **no existen**; caben como códigos nuevos de `CryptoCode` (`sealed`,
  `unreachable`, `forbidden`) sin clases nuevas. **No hay handler de `CryptoError` en
  `core/errors.py`** (`register_error_handlers`, `:229-235`): fuera de `members/changes.py:110`
  (`empty_value` → `None`) ningún módulo la captura; en una ruta hoy acaba en `_handler_inesperado`
  → 500 `internal_error`. US-136 exige 503 `crypto_unavailable`: handler nuevo en `core/errors.py`
  (sin importar `core/crypto`: `core/errors` puede importar `core/crypto/errors` si
  `test_sin_ciclos_entre_modulos_de_core` lo permite; `core/crypto/errors.py` no importa nada de
  `core`).
- `crypto_keys` (`models.py:72`, `0003`): `provider` con CHECK `('local', 'openbao')`, `KEY_STATES`,
  `uq_crypto_keys_active`, trigger `crypto.guard_keys_update()` que **prohíbe cambiar `provider` y
  `wrapped_material`** (`0003:213-215`, "solo cambia state y rotated_*"): **existe y bloquea
  `migrate-provider`**. SPRINT-05 ya lo prevé ("la función de guarda se extiende con una migración
  nueva, no se reemplaza; DECISIONES E"). La migración debe `CREATE OR REPLACE FUNCTION` admitiendo
  el par (`provider`, `wrapped_material`) cuando cambian juntos y `provider` va `local → openbao`
  (nunca al revés, nunca solo uno de los dos), con `downgrade` al texto de `0003`. Los triggers
  `crypto_*` siguen en `tgenabled = 'O'` (residual anotado en 4B).
- `crypto_jobs` (`models.py:142`): `JOB_KINDS` con `migrate_provider` y `rewrap`, índice único
  `uq_crypto_jobs_in_progress` sobre `coalesce(data_class, '*') WHERE status IN ('pending',
  'running')`: **existe**. Un `migrate_provider` con `data_class = NULL` ocupa la clave `'*'`: **no
  hace falta `0030_crypto_jobs_single_running`** (el desglose lo dice: "si `0003` ya lo incluyó, no
  se crea"). Tampoco `0031_crypto_provider_openbao`.
- `crypto_ops` (`models.py:112`): `OP_VERBS` con `wrap` y `unwrap`, `batch_id`, `count`,
  `OP_PURPOSES` con `notify`, `auth_link`, `export`: **existen**. `oplog.record(verb, *, data_class,
  key_id, key_version, record_id=None, purpose=None, result="ok")`: **existe**; las filas
  `unwrap`/`wrap` de la migración caben con `batch_scope(uuid4())` (`core/context.py:72`).
- `core/crypto/service.py` (503 líneas; tope 800): `start_rotation`, `reencrypt_batch`,
  `finish_rotation`, `rotate_index`, `retire_key`, `recent_kek_verify`, `_rotation_lock`,
  `_swap_key`: **existen**. `migrate_provider(from_, to, by, dry_run)` y
  `plan_provider_migration(keys)` **no existen**: entran en `service.py` (quedaría cerca de 600) o
  en un `core/crypto/migrate_provider.py` nuevo; `test_core_import_direction.py:209` exige que
  `service.py` y `discovery.py` no importen `core/audit` ni `app.modules`: la auditoría la escribe
  `cli_ops/migrate_provider.py`, como `rotate_key.py`.
- `cli_base.crypto_runtime(settings, options, *, persist_keys)` (`cli_base.py:158`) y
  `cli_keyring.load_keyring`: **existen**; `migrate-provider` necesita **dos** proveedores vivos a
  la vez (`local` para `unwrap`, `openbao` para `wrap`): `configure_provider` admite uno solo.
  `cli_ops/` admite un archivo por familia (`test_app_layer_importers.py`: nunca se importan entre
  sí); `cli.py` mide 336 líneas (tope 700, S4B).
- `archive.py`/`kek_backup.py` (`export-kek`, `verify-kek-backup`, `restore-kek`): **existen y no
  cambian**; US-116 se exige antes de migrar (riesgo 1). `verify_wrapped` abre con la KEK local:
  tras migrar, un `verify-kek-backup` sobre llaves `openbao` no aplica (decidir el mensaje, C2).
- `ADR-002-criptografia.md` §1 dice "con OpenBao (v0.2) la envoltura es lo que devuelva Transit":
  **existe**; se completa con `vault:v<n>:` y el proveedor por fila.

### Salud, arranque, errores y Compose (US-136)

- `register_health_check(name, fn, *, critical, allowed=DEFAULT_ALLOWED, healthy=DEFAULT_HEALTHY)`
  (`health.py:51-67`), `HealthOut(status, db, version, backup, migrations)` con `extra="allow"`
  (`:94-103`), caché por comprobación `HEALTH_CACHE_TTL_S` (`db` 2 s, `backup` 30 s, `migrations`
  30 s): **existen**. El check `crypto` se registra con `critical=True, allowed={"ok", "sealed",
  "unreachable", "unknown"}, healthy={"ok"}` desde `main.py` (`test_health_check_registrars.py`:
  solo `main.py` y `core/`); `HealthOut.crypto: Literal["ok", "sealed", "unreachable", "unknown"] =
  "unknown"` explícito para que `docs/openapi.json` y `types.ts:1206` lo tipen; `HEALTH_CACHE_TTL_S`
  gana `crypto` (≤ 30 s para que el criterio 4 de US-136 "en máximo 30 s" se cumpla con el sondeo).
- `main._startup` (`main.py:115-157`): `configure_provider(get_key_provider(settings))` y
  `ensure_keys` dentro de `try` que **relanza y el api no acepta tráfico**: **existe con otra
  forma**. US-136 exige arrancar sin DEK y sondear cada `CRYPTO_RECOVERY_POLL_S`; `gc.freeze()` al
  final del arranque (S4B-D48/D179) debe correr también en el arranque degradado. El sondeo es una
  tarea `asyncio` del lifespan que el `finally` cancela (patrón de
  `_cancel_background_verifications`).
- `core/errors.py`: `MENSAJE_503 = "Base de datos ocupada"` para el 503 que `_publicar_error_response`
  agrega a toda operación con rol (`:252-297`): **existe con otro texto**. Con `crypto_unavailable`
  compartiendo el 503, la descripción del OpenAPI pasa a "Base de datos ocupada o custodio de llaves
  no disponible" (ningún test fija el texto; `test_error_codes_per_route.py` solo exige que el 503
  apunte a `ErrorResponse` y que `/health` conserve `HealthOut`). `ErrorBody(code, message,
  field?, existing_id?)` cabe para `{code: "crypto_unavailable", message: "El custodio de llaves
  no está disponible. Avise al administrador para desellarlo."}`.
- `infra/compose.yml`: `api.healthcheck` exige `status == 200` (`:118-124`), `worker.depends_on.api:
  service_healthy` (`:140-146`), `web.depends_on.api: service_healthy` (`:232-234`),
  `backup.depends_on.dbsetup` (`:214`): **existe y contradice US-136 y el riesgo 2 del plan**. Con
  OpenBao sellado en el arranque del servidor (el escenario del riesgo), el api queda `unhealthy`
  (503) y Compose no arranca `web` ni `worker`: el operador no ve ni el front ni el mensaje. Salidas:
  (a) el healthcheck de Compose llama a `/health` y acepta 503 cuando el cuerpo trae `"db": "ok"` y
  `"migrations": "ok"` (lo que `deploy.sh` ya busca), con un `python -c` que parsee el JSON, y
  `/health` sigue respondiendo 503 para quien lo consulte; (b) `web.depends_on.api` baja a
  `service_started` (deshace S4B-D11 para `web`) y `worker` sondea por su cuenta. Recomendación: (a),
  anotada en DECISIONES (C3). `infra/deploy.sh:289-301` usa `curl -fsS` (falla con 503) y
  `fallo_despliegue("/health no llegó a db ok y migrations ok")`: el plan pide el mensaje "api en
  estado sellado: desellar OpenBao", así que el sondeo debe aceptar el 503 con `crypto: sealed` y
  decirlo.
- `test_compose_config.sh`: `{"pgdata", "uploads", "keys"} <= volumes` y la cadena literal
  `"pgdata, uploads, keys, backups"` (`:92-93`), `worker` sin `keys` ni `uploads` "hasta el Sprint
  5" (`:86`), `db` sin `ports`, secretos solo por interpolación (`:98`): los volúmenes
  `openbao-data` y `openbao-token`, el montaje del token en `api` y `worker` y el servicio `openbao`
  sin `ports` entran en sus aserciones (C3). `test_images_pinned.sh` revisa cada `image:` de los dos
  compose: `openbao/openbao:<ver>@sha256:...` con fecha y comando, igual Mailpit en
  `compose.dev.yml`.
- `.github/workflows/ci.yml`: `e2e-stack` hace `cp .env.example .env` (`CRYPTO_PROVIDER=local`) y
  `$DC up -d --build` sin lista de servicios (`:398`): `openbao` arrancará ahí; el smoke de la DoD
  ("migrar proveedor, sellar, ver el 503, desellar") necesita pasos nuevos (modo dev o `bootstrap.sh`
  con llaves efímeras, `bao operator seal`/`unseal`). `compose-smoke.sh` no conoce `openbao`.
- Puertos del host: 80, 8000, 5432 y 5433 están ocupados por otro proyecto (PID 12672; el stack de
  APEX usa `WEB_PORT=8180`, `API_PORT=8181`, `DB_PORT=5442`, `DB_TEST_PORT=5443`); 8200 libre y
  **no debe publicarse** (criterio 1 de US-133). `which age bao openbao gh jq`: ninguno en el host;
  `bao` solo existe dentro del contenedor (`docker compose exec openbao bao ...`). Compose v5.6.1.

### Worker, jobs y alertas (US-124 a US-126, US-136)

- `JobSpec(name, run, hour, minute, timeout_s=900)` (`registry.py:21`), `JOBS = (expirations,
  backup_check)` (`jobs/__init__.py:9-18`), `JobContext(session_factory, today, clock, simulated)`,
  `JobResult(ok, details, status=None)` (`runner.py:87`, S4B-D23), `run_job`, `run_cycle`,
  `EXIT_BY_RESULT` (`main.py:51`): **existen**. `needs_crypto` en `JobSpec` **no existe**; `notify`
  se agrega a `JOBS` después de `backup_check` (o entre `expirations` y `backup_check`: el orden de
  la tupla es el orden del ciclo, y el plan pide `notify` "después de `expirations`").
  `test_worker_boundaries.py:104-115` fija el conjunto de archivos con `<=`: sumar
  `jobs/notify.py` al conjunto.
- `RESULTS = {running, ok, error, ok_unverified, stale, missing, corrupt, undecryptable}`
  (`core/jobs.py:86`) y el CHECK `ck_job_runs_result` de `0012:48`: **sin `skipped`**. El desglose
  de EP-15 pide `result = skipped` con `details = {"reason": "crypto_sealed"}`; además `details`
  solo admite enteros de `DETAIL_KEYS` (`check_details`, `:241-248`). Dos salidas: (a) migración
  `job_runs_result_skipped` (CHECK ampliado, `RESULTS` y `EXIT_BY_RESULT` con `skipped` → 0); (b)
  sin migración: `result = ok` con `details = {"omitido_sellado": 1}` y un log `warning`.
  Recomendación: (b) para `notify` (que igual corre `generate` y `summary` sin descifrar: solo la
  fase `send` necesita el bus) y dejar `skipped` para cuando un job entero se omita (EP-17
  `sign_audit`). Decidir en C4.
- `DETAIL_KEYS` (`core/jobs.py:58-70`; enteros): gana las claves del job `notify` (`generados`,
  `omitidos_preferencia`, `omitidos_canal`, `enviados`, `fallidos`, `resumen_enviado`, `omitido_sellado`
  o las que fije el plan); `tests/worker/test_jobs_core.py` las fija.
- `worker/runtime.py` (`worker_runtime`, `load_module_services`, latido): **no carga proveedor ni
  keyring** (S4A-D49: "en 4A no cifra ni descifra; el Sprint 5 vuelve a montar `keys:ro`"). La fase
  `send` descifra el correo por `contact_for_notification` → `types.reveal` → `bus.decrypt` →
  `current_keyring()`: el worker necesita `configure_provider` + `ensure_keys` (o solo
  `Keyring.load_all` sin crear llaves) y, en Compose, el token de OpenBao (`openbao-token:ro`) o
  `keys:ro` si el proveedor sigue `local`. Decisión del plan: el worker carga llaves con el mismo
  proveedor que el api (`CRYPTO_PROVIDER` de `.env`), y en modo sellado omite solo la fase `send`.
- `infra/db/grants.sql` y `tests/migrations/test_db_grants.py:58-139`: `apex_worker` tiene `SELECT`
  en `crypto.crypto_jobs` y `SELECT, INSERT` en `crypto.crypto_ops`, pero **nada sobre
  `crypto.crypto_keys`**; `_check_key_current` hace `SELECT ... FOR SHARE` (`types.py:140`), que en
  PostgreSQL exige `UPDATE` sobre alguna columna: `apex_worker` necesita `SELECT` y `UPDATE
  (updated_at)` como `apex_api` (residual D61 ampliado). Tablas nuevas: `notifications.notification_templates`
  (api S I U; worker S), `notifications.notification_rules` (api S I U; worker S),
  `notifications.notifications` (api S I U; worker S I U), `members.member_channel_preferences`
  (api S I U; worker S) deben entrar en la matriz, en el `ARRAY` `clasificadas` (bloque 7,
  fail-closed) y en `PRIVILEGIOS`; `apex_backup` lee por `pg_read_all_data`. `apex_worker` ya tiene
  `SELECT, INSERT` en `audit.audit_log` (las filas `reveal` del `send`) y `SELECT` en
  `members.members`, `memberships.memberships`, `settings.settings_sections`.
- `core/alerts.py`: `AlertSink.send(code, context)` **síncrono**, `register_sink(sink)`,
  `alert(code, **context)` con `ALERT_CONTEXT_KEYS = {job, result, error_type, attempts, run_date,
  sqlstate}` y valores `str | int` (`:23-25,52-63`): **existe con otra forma** respecto a
  `alert(kind, text)` del desglose y de `05_service_design.md`. El resumen diario (conteos por estado
  y el enlace a `/avisos/hoy`, sin nombres) exige claves nuevas (`pending`, `failed`, `sent`,
  `skipped`, `url`) o un `code = "daily_summary"` con su propio conjunto; `TelegramAlertSink`
  compone el texto en español a partir de `code` y `context` (el texto nunca viaja como contexto
  libre: S4A-D82). Como `send` es síncrono, el sink usa `httpx.Client` con `timeout` explícito
  (10 s) y nunca propaga (`alert` ya captura y loguea solo el tipo). Se registra desde `main.py` y
  `worker/main.py` (raíz de composición; `test_core_no_importa_modulos` ya vigila que
  `core/alerts.py` no importe `app.modules`: el `test_core_no_modules.py` del desglose está
  consolidado). El `chat_id` del equipo: el desglose lo pone en `settings.channels` y US-126 "en
  `.env` (supuesto)"; con Q12 (`settings.channels` sin secretos) el `chat_id` no es secreto, pero el
  sink se construye al arrancar sin sesión: va en `.env` (`TELEGRAM_CHAT_ID`) o el sink lo lee de
  `settings` por sesión propia. Decidir en C5.
- `alert("crypto_sealed", ...)` desde la transición a `sealed` (N-34, 1 h): cabe con `code` nuevo y
  contexto `{result: "sealed"}`.

### Avisos: módulo `notifications` y lo que pide a otros (EP-14)

- `modules/notifications/` **no existe**. `main.MODULES` (`main.py:51-60`) es la única lista:
  `notifications` entra antes de `dashboard` (que lo consumirá); `cli_base._load_module_services`
  y `worker/runtime.py:79` la reutilizan. `migrations/env.py:35-40` importa los `models` de cada
  módulo: sumar `from app.modules.notifications import models`. `scripts/workflow/slice-gate.sh`
  mapea `<modulo>` → `src/app/modules/<modulo>` y `tests/<modulo>` sin lista cerrada: `slice-gate.sh
  notifications` funciona sin tocar el script.
- `members.service.contact_for_notification(session, member_id, purpose) -> Contact` (`contact.py:69`):
  **existe con otra firma** (el desglose pide `fields={"phone"}`/`{"email"}` para descifrar solo el
  campo del canal; hoy descifra `phone` y `email` y audita una fila `reveal` por campo no nulo).
  `Contact(first_name, phone, email)` no se serializa (`__reduce__` lanza). Regla de composición
  S4A-D50: una unidad por socio, confirmar antes de enviar. `validate_purpose` solo admite `notify`
  y `auth_link`. `CONTACT_CALLERS = frozenset()` y `test_contact_callers.py:106` lo fija por
  igualdad (`assert frozenset() == CONTACT_CALLERS`): la prueba cambia a
  `{"modules/notifications/service.py"}` (su docstring ya lo anuncia); `cli.py` y `worker/` siguen
  sin poder nombrarla (el job llama a `notifications.service`).
- `members.service`: `names_for(session, ids) -> dict[UUID, MemberName(id, first_name, last_name,
  sex)]`, `ensure_exists(session, member_id, *, include_deleted=False)`, `get_ref`, `active_ids`,
  `list(session, query: MemberListQuery, ...)`, `search_ids`: **existen**; `exists`,
  `channels_for`, `get_channels`, `set_channels`, `effective_channels`, `export` **no existen**.
  `MemberUpdated` existe (nombres de campo, sin valores: `test_events_without_pii`). Los privados de
  `members` son exactamente `{rules, detail, changes, contact}` (`test_no_cross_models.py:167-170`):
  las preferencias de canal van en archivos existentes (`models.py`, `changes.py`, `service.py`) o
  la prueba gana `channels` con decisión anotada (`members/service.py` mide hoy unas 560 líneas).
- `memberships.service` (`__all__`, `service.py:73-100`): `refs_for(session, membership_ids) ->
  dict[UUID, MembershipRef]` (socio, plan y fechas por id de membresía) **cubre `labels_for`**;
  `status_for(session, member_ids, *, today) -> dict[UUID, MemberMembership(status, plan_id,
  plan_name, end_date)]` **cubre `current_for`**; `member_ids_by_status(session, statuses, plan_id,
  *, today)`, `list_for_member`, `summary`: **existen**. `notification_candidates(on_dates)` y
  `has_current_or_future(member_ids, today)` **no existen**: entran en `memberships/queries.py` (la
  fachada los reexporta) con `status_expr`/`_deciding` ya existentes; `MembershipExpiring`/
  `MembershipExpired` existen pero el generador no los consume (decisión del desglose a favor de la
  arquitectura; coherente con `04_architecture_decision.md` §5).
- `settings`: `ENABLED_SECTIONS = {gym, privacy, memberships, payment_methods}` (`schemas.py:63`),
  `SECTION_REGISTRY`/`SECTION_VIEWS`/`SECTION_DEFAULTS` (`:200-230`), `SectionKey.channels` ya
  declarado (`:55`), `get_section(session, key)` que responde `SectionNotAvailable` (404) fuera de
  `ENABLED_SECTIONS`: **existe con otra forma**. `test_settings_no_secrets.py` recorre
  `SECTION_REGISTRY` (que "debe tener exactamente las secciones habilitadas") y rechaza campos cuyo
  nombre contenga `token`, `secret` o `password` o termine en `_key`: el esquema de `channels`
  (`email.enabled`, `email.from_name`, `email.reply_to`, `whatsapp_link.enabled`,
  `whatsapp_link.country_code`) y la vista con `credentials_present` cumplen; `channels_credentials_present(config)`
  en `settings.service` lee `core.config.Settings` (nunca el valor). El front `ConfigPage.tsx:27-32`
  tiene cuatro pestañas (`gimnasio`, `privacidad`, `membresias`, `medios`): quinta `canales`
  (`Config.html` la numera "4 · Canales de aviso").
- `auth`: `forgot(email, *, policy)` (`links.py:154-171`) **no lee ni escribe la base** (H-2,
  S2-D36: "sin emisor no hay nada que hacer; no leerla quita de raíz cualquier diferencia de
  tiempo"); `create_user(session, *, email, role, by, front_base_url) -> CreateUserOut`
  (`users.py:465`) y `resend_link` → `IssuedLinkOut(url, purpose, expires_at)` con `extra="forbid"`
  (`schemas.py:162`); `auth.service.names_for` y `user_names_for`: **existen**. US-131 revierte H-2:
  `forgot` pasa a buscar la cuenta, emitir el token y enviar en `BackgroundTasks` tras el 204, con
  la prueba de tiempos comparables (`wait_floor` ya existe). `email_sent: bool` entra en
  `CreateUserOut` e `IssuedLinkOut` (regenerar `openapi.json` y `types.ts`; `web/src/features/system`
  usa `IssuedLinkOut`). Arista nueva `auth → notifications` en `ALLOWED_EDGES` (sin ciclo:
  `notifications` no importa `auth`).
- `dashboard`: `DashboardOut.notifications_today: int | None = None` (`schemas.py:60`,
  `extra="forbid"`) y `summary(session, *, with_finances)` (`service.py:234`): **existen**; el
  `KpiCard` del front ya lee `notifications_today` (`FutureKpis.tsx:27`, "Disponible en v0.2").
  `test_read_modules.py` prohíbe a `dashboard` importar `models`, `core.audit` o ejecutar SQL:
  `notifications.service.today_count(session, today)` cumple; arista `dashboard → notifications`.
- `core/events.py`: `DomainEvent`, `subscribe`, `emit` (misma sesión, sin "después del commit"):
  **existe**. Los cuatro eventos de `notifications` (`NotificationQueued`, `NotificationSent`,
  `NotificationFailed`, `NotificationSkipped`) se declaran en `notifications/service.py`
  (`test_events_without_pii`: solo ids, conteos y códigos; `reason` prohibido como texto libre:
  el `skip_reason` no viaja en el evento).
- `core/audit.py`: `__audited__ = True` y `__audit_subject__` por modelo (`audit.py:411-422`;
  `test_audited_tables.py` exige que toda tabla no excluida esté auditada; `test_audit_subject.py`
  que los modelos con socio declaren su sujeto): `notifications.notifications` con
  `__audit_subject__ = "member_id"`, `member_channel_preferences` igual; plantillas y reglas sin
  sujeto. `record(session, *, action, table_name, record_id: UUID | None, before, after, user_id=None,
  subject_member_id=None)` (`:341`) y `record_id` nulo admitido (`:133`): **existen** para
  `export` con `record_id=None` y `after={filters, rows}`.
- `core/ratelimit.py`: `USER_LIMITS` con 12 cubetas (`:316-329`), `test_user_limits_catalog.py`
  (`CLAVES_SIN_RUTA_TODAVIA = frozenset()`: toda cubeta tiene ruta) y
  `test_writes_have_user_limit.py` (todo `POST`/`PATCH`/`DELETE` con cubeta o motivo en `EXENTAS`,
  que solo admite públicas): las escrituras nuevas (`POST`/`PATCH` de plantillas y reglas →
  `admin-write`; `POST /notifications/{id}/skip`, `PATCH /members/{id}/channels` →
  `memberships-write` o una cubeta `notifications-write` nueva con su `USER_*` en `Settings` y
  `.env.example`; `PATCH /settings/channels` → `admin-write`) deben nombrar `enforce_user_limit`.
  `GET /notifications/{id}/wa-link` (descifra) y `GET /members/export` (descifra en masa) son `GET`
  y la prueba no las obliga: por seguridad consumen `members-reveal` (o `staff-read`) y lo anota el
  plan. `rate_limit("forgot")` por IP (5/min) y `FORGOT_ACCOUNT_BUCKET` existen (criterio 6 de
  US-131).
- `core/security.py`: `PUBLIC_ROUTES` con 8 entradas y `test_every_route_has_role.py:62-76` lo fija
  (`len == 8`): ninguna ruta nueva es pública. `StaffDep`/`AdminDep` **existen**. `core/http.no_store`
  en el `APIRouter` (`test_no_store_routes.py`): el router de `notifications` lo declara a nivel de
  router como `payments`.
- `core/pagination.py` (`Page`, `PageParams`, `SearchQuery`) y `test_list_routes_use_page_params.py`
  (toda ruta con `response_model=Page[...]` usa `PageParams` y acepta `q`): las tres listas de
  avisos y la de `/members/{id}/notifications` pasan por ahí (`q` opcional; el desglose no lo
  nombra: decidir si `GET /notifications` admite `q` o se excluye con motivo).
- `tests/conftest.py` `LIMPIEZA_DE_SESION` (`:304-320`): gana `DELETE FROM notifications.notifications`,
  `notification_rules`, `notification_templates` (en ese orden, por la FK) y
  `members.member_channel_preferences` antes de `LIMPIAR_MEMBERS`.
- Dependencias: `aiosmtplib` (MIT) y la imagen Mailpit (MIT) para SMTP de prueba **no están**;
  `httpx` 0.28.1 (BSD) sí, con `anyio` y `certifi` (MPL-2.0 sin modificar, en
  `licenses-exceptions.txt`). Brevo y Telegram por `httpx` directo con `httpx.MockTransport` en
  pruebas. `python-telegram-bot` (LGPL) prohibido: `check-licenses-api.sh` ya lo rechaza por
  omisión (solo acepta `MIT;BSD;Apache;PostgreSQL;ISC;0BSD;PSF`).

### Recibos y exportaciones (EP-16)

- `AUDIT_ACTIONS` con `download` y `export` (`core/audit.py:76-85`; CHECK de `0002`): **existen**;
  **no hace falta `0035_audit_action_download`**. US-137 (historia) dice `export`; el desglose ya lo
  corrige a `download` (N-08).
- `payments.service`: `register`, `void`, `methods`, `summary` (lo usa `dashboard`), `list`,
  `get`, `list_for_member` (`PaymentListQuery`, `schemas.py:122`): **existen**; `receipt_pdf(id,
  by)`, `export(filters, by)`, `receipt_context`, `format_cop` (existe en `dashboard.service:103`,
  pura: moverla a un sitio compartido o duplicar con prueba), `format_bogota`, `csv_row`,
  `payments/receipt.py` **no existen**. `payments/router.py` ya declara `no_store` a nivel de
  router (`:70`) y registra `/payments/summary` y `/payments/methods` antes de `/payments/{id}`:
  `/payments/export` y `/payments/{id}/receipt.pdf` siguen ese orden (`receipt.pdf` no choca con
  `{payment_id}` porque FastAPI prueba la más específica primero solo si se registra antes).
  `payments` no importa `memberships` arriba (D1: puerto `MembershipGate`); `refs_for` para el
  recibo entra como import perezoso con `# lazy: G-03 (payments -> memberships)`, ya en
  `LAZY_IMPORT_WHITELIST` (`test_service_import_graph.py:75-77`) y con uso real desde S3-B8.
- `members.service.list` con `MemberListQuery(q, status, membership_status, plan_id, sort, limit,
  offset)` (`schemas.py:145`), `_filtro_de_estado`, `_por_membresia` (lazy `members → memberships`,
  ya en la lista blanca), `bus.batch("decrypt", data_class)` y `types.reveal(socio, campo,
  "export")` (`OP_PURPOSES` tiene `export`): **existen** para `export(filters, by)`. El descifrado
  en lotes de 500 con `batch_id` por lote y clase sale de `oplog.batch` (`_materialize` agrega por
  lote). `members/router.py` registra `/members/export` antes de `/members/{member_id}`.
  `test_list_rows_without_sensitive_fields.py` solo barre filas de `Page[...]`: un `StreamingResponse`
  no entra, pero el router no debe declarar un `response_model` con esos campos.
- `core/export.py` (`csv_stream`, `escape_formula`) **no existe**; `core/` compartido, sin
  importar módulos (`test_core_no_importa_modulos`).
- `reportlab` (BSD-3), `pypdf` (BSD, solo dev): **no están** en `pyproject.toml:8-24` ni `uv.lock`.
  `reportlab` 4.x depende de `pillow` (licencia HPND, que Pillow publica como `MIT-CMU`/"CMU License
  (MIT-CMU)" desde 10.x) y de `charset-normalizer` (MIT): `check-licenses-api.sh` acepta por
  coincidencia parcial `MIT`, así que pasa solo si `pip-licenses` lee ese texto; si lee "Historical
  Permission Notice and Disclaimer (HPND)" falla y hay que decidir (excepción justificada en
  `licenses-exceptions.txt` solo si la licencia es permisiva, o `pillow` fuera con `reportlab` sin
  imágenes raster: el logo PNG lo exige). Se verifica en W0 con `uv add reportlab` +
  `check-licenses-api.sh` (C8). El logo `apex-logo-light-bg.png` existe en `docs/design/assets/logo/`
  y `web/public/brand/`; copiado a `api/src/app/modules/payments/assets/` entra en la imagen por
  `COPY src ./src` (`Dockerfile:19`) y en la rueda por `packages = ["src/app"]` (hatch incluye los
  datos del paquete); `test_api_image.sh` puede comprobar su presencia.
- `test_third_party_confinement.py` (`SOLO_BAJO_IMPORTS = (openpyxl, defusedxml)`, `subprocess`
  solo en `archive.py`, `NUNCA = (pyrage,)`): patrón para reglas nuevas opcionales (`reportlab`
  solo en `payments/receipt.py`, `aiosmtplib` solo en `notifications/channels/email.py`).
- `infra/nginx/default.conf`: `location /api/` con `client_max_body_size 64k` (`:72-73`), sin
  `proxy_read_timeout` propio: un CSV de 1.000 socios en menos de 10 s cabe en el valor por defecto
  (60 s); el PDF sale en una sola respuesta. Nada que cambiar salvo que la exportación supere el
  minuto.

### Front (Waves 5a y 5b)

- `web/src/config/features.ts`: `notifications` está en `FEATURES` y **no** en `ENABLED_FEATURES`;
  `features.test.ts:11-12` fija las nueve habilitadas y `size == 9` → pasa a diez. `routeTable.ts:147-149`
  ya trae `/avisos/hoy`, `/avisos/reglas`, `/avisos/historial` (feature `notifications`, acceso
  `notifications.view`, layout `panel`) y `routes.reference.ts:66-68` coincide; `permissions.ts` ya
  tiene `members.export` (admin), `payments.export` (admin), `notifications.rules.edit` (admin) y
  `notifications.view`; `layouts/nav.ts:72,80-81` ya tiene "Por avisar hoy" en Hoy y "Reglas y
  plantillas"/"Historial de envíos" en Avisos: **existen**; se habilitan al entrar la feature.
- `features/dashboard/components/FutureKpis.tsx:27` muestra "Por avisar hoy · Disponible en v0.2"
  con `notifications_today`; pasa a `KpiCard` real con enlace a `/avisos/hoy` y "Nadie por avisar"
  en 0 (`FutureKpis.test.tsx:21,43,72` cambian).
- `features/auth/pages/ForgotPage.tsx:4,18`: `DESIGN-GAP` "Pídele al administrador tu enlace de
  recuperación." (H-2); US-131 lo cambia por "Si el correo está registrado, te enviamos un enlace"
  (`Login.html`) y cierra el `DESIGN-GAP`. `ResetPage.tsx:10` ("Guardar y entrar" no abre sesión)
  queda.
- `features/system/pages/ConfigPage.tsx`: quinta pestaña "Canales" (`?tab=canales`) con
  `ChannelsSettingsForm` (patrón `PaymentMethodsForm`), insignia "Credenciales listas"/"Faltan
  credenciales en .env". `features/system/api.ts` y `schemas.ts` ganan la sección.
- `features/members`: pestaña `avisos` de la ficha hoy deshabilitada ("Disponible en v0.2",
  `isPageAvailable`); hija nueva `NotificationsTab.tsx` de la feature `notifications` (una feature
  nunca importa de otra: la pestaña se registra como hija de otra feature igual que `membresias` y
  `pagos`, S3-D65) con `ChannelPreferences`; `ExportButton` en `MembersListPage` (`useCan("members.export")`
  + `ConfirmModal`). `features/payments`: `ReceiptButton` en `PaymentDetailModal` y en
  `MemberPaymentsTab`, `ExportButton` en `PaymentsPage` (`Pagos.html` trae "Exportar" y "Recibo";
  `Socios_Lista.html` "Exportar").
- `features/notifications/` **no existe** (api, schemas, `TodayPage`, `RulesPage`, `HistoryPage`,
  `SkipModal`). Pantallas `PorAvisarHoy.html` (acciones "Omitir", "Regenerar lista"; abrir WhatsApp),
  `Notif_Reglas.html` ("Editar regla · Vencido", "Pestaña Plantillas · editor"),
  `Notif_Historial.html` (paginación): existen con su `.dark.html`. "Regenerar lista" no tiene
  endpoint en el plan (`generate_for` es del job y `cli notify --generate-only`): `// DESIGN-GAP:`.
- `shared/ui/index.ts` no tiene `downloadBlob`; el desglose lo pone en `shared/ui/` pero
  `CLAUDE.md` reserva `shared/ui` para los componentes de `DESIGN.md`: va en `shared/lib/download.ts`
  (junto a `paymentPanel.ts`, `routes.ts`). `shared/data/` gana los hooks que compartan dos features
  (`useChannels` si la ficha y Config lo usan).
- `web/src/core/api/types.ts` se regenera con `npm run gen:api` tras `export-openapi` (CI "tipos
  del api al día"). E2E: `web/tests/e2e/avisos.spec.ts` (preview) y `tests/e2e/stack/` (contra el
  stack); `home.spec.ts` del stack ya existe y gana el KPI.

## 2. Blast radius por bloque

### Wave 0 · Servicio `openbao`, token y procedimiento

- Archivos nuevos: `infra/openbao/{config.hcl,bootstrap.sh}`, `infra/openbao/tests/*` (Bash puro,
  `bash -n`), `docs/operacion/openbao.md` (desellado 3 de 5, rekey, dónde guardar las llaves,
  verificación con `/health`). Tocados: `infra/compose.yml` (servicio `openbao` por digest con fecha
  y comando, sin `ports`, `cap_add IPC_LOCK` o `disable_mlock`, healthcheck con `bao status` que
  devuelve 2 cuando está sellado: `healthcheck` debe aceptar "sellado pero vivo" o `api`/`worker`
  no pueden depender de `openbao` `service_healthy`; volúmenes `openbao-data` y `openbao-token`;
  `api` y `worker` con `openbao-token:/run/secrets/openbao:ro`), `infra/compose.dev.yml` (`openbao`
  en modo dev con `BAO_DEV_ROOT_TOKEN_ID`, y Mailpit por digest), `.env.example` (`OPENBAO_ADDR`,
  `OPENBAO_TOKEN_PATH`, `OPENBAO_TIMEOUT_S`, `CRYPTO_RECOVERY_POLL_S`; `CRYPTO_PROVIDER` sigue
  `local` hasta migrar), `core/config.py` (campos nuevos de `Settings` con validador "si
  `CRYPTO_PROVIDER=openbao`, `OPENBAO_ADDR` obligatoria"; `missing_secrets` comprueba
  `OPENBAO_TOKEN_PATH`), `scripts/ci/test_compose_config.sh` (servicio sin `ports`, volúmenes, token
  `:ro`, worker con solo `backups` y el token), `scripts/ci/test_images_pinned.sh` (pasa solo: ya
  revisa los dos compose), `scripts/ci/compose-smoke.sh` y `.github/workflows/ci.yml` (`openbao` en
  modo dev en `e2e-stack` y en el smoke; `bash -n infra/openbao/*.sh`), `NOTICE` (bloque fijo
  "OpenBao · MPL-2.0 sin modificar · imagen `openbao/openbao`"; `notice.sh` escribe un bloque
  literal: editar el script, no el archivo), `CLAUDE.md` (estructura: `infra/openbao/` ya listado
  "desde v0.2"), `RUNBOOK.md` §13.
- Lo rompe fuera del gate: `test_env_example.py:32,38` en cuanto `Settings` gane campos sin línea
  en `.env.example` o `.env.example` gane claves ajenas sin `NON_API_ENV_VARS` (`extra="forbid"`:
  **el api, el worker y `tools` dejan de arrancar**); `test_images_pinned.sh` con una imagen sin
  digest; `test_compose_config.sh:92-93` con la cadena literal de volúmenes; `test_kek_path_single_door.py`
  si `OPENBAO_TOKEN_PATH` se lee fuera de `core/crypto` (la lista `NOMBRAN_LA_RUTA` es de la KEK:
  conviene un gemelo para el token, `ABREN` = `core/crypto/openbao_provider.py`).
- Quirk de buildx (RUNBOOK §7): la imagen del api no cambia en W0 (solo `.env` y Compose); `openbao`
  es una imagen pública: `up -d --no-build openbao` basta. El token periódico se escribe en el
  volumen `openbao-token` con modo 600 y `uid 10001` (el api corre como `apex` 10001 con
  `read_only: true`): `bootstrap.sh` corre dentro del contenedor `openbao` (`docker compose exec
  openbao sh /opt/openbao/bootstrap.sh`) o como `run --rm` con el volumen montado.

### Bloque A · OpenBao (US-133 a US-136)

- Archivos nuevos: `core/crypto/openbao_provider.py` (`httpx.AsyncClient`, `key_name(purpose,
  data_class)`, `map_error`, token leído de archivo, renovación `auth/token/renew-self`, timeout,
  TLS si `https`), `core/crypto/migrate_provider.py` (o dentro de `service.py`), `core/crypto/
  health.py` (`health_state`, estado del proceso, sondeo), `cli_ops/migrate_provider.py`,
  `migrations/versions/0015_crypto_keys_guard_provider.py`, `tests/crypto/{test_provider_contract,
  test_openbao_provider,test_migrate_provider,test_health_state}.py`, `tests/core/test_health_crypto.py`,
  `tests/members/test_router_crypto_unavailable.py`, `tests/worker/test_skip_when_sealed.py`,
  `tests/cli/test_migrate_provider.py`, `tests/migrations/test_0015_*.py`. Tocados:
  `core/crypto/provider.py` (firma de `wrap`/`unwrap`, registro por nombre, `get_key_provider` con
  `openbao`), `local_provider.py` (ignora `key_ref`), `keyring.py` (proveedor por fila),
  `bootstrap.py` (`provider` real y `key_ref` de Transit), `bus.py` (si se agrega `ensure_available`),
  `errors.py` (códigos `sealed`, `unreachable`, `forbidden`), `service.py` (`_swap_key` con la firma
  nueva), `kek_backup.py` (mensaje para llaves `openbao`), `core/errors.py` (handler de
  `CryptoError` → 503 `crypto_unavailable` solo para `crypto_unavailable`/`sealed`/`unreachable`;
  el resto sigue como hoy; `MENSAJE_503`), `core/health.py` (`HealthOut.crypto`,
  `HEALTH_CACHE_TTL_S["crypto"]`), `main.py` (arranque degradado, sondeo, check `crypto`),
  `worker/main.py` y `worker/runtime.py` (proveedor y keyring, sondeo, `needs_crypto`),
  `worker/registry.py` (`JobSpec.needs_crypto`), `worker/runner.py` (omisión y resultado),
  `core/jobs.py` (`DETAIL_KEYS`/`RESULTS` según C4), `core/config.py`, `infra/compose.yml`
  (healthcheck del api y `depends_on`, C3), `infra/deploy.sh` (sondeo que distingue `sealed`),
  `tests/core/test_health.py`, `tests/core/test_startup_failure.py` (hoy exige que el api **no**
  arranque sin proveedor: cambia a "arranca degradado con `openbao` sellado, no arranca sin KEK
  local"), `docs/openapi.json` y `types.ts`, `docs/adr/ADR-002-criptografia.md` §1 (`vault:v<n>:`),
  `RUNBOOK.md` §6 (`0015`), `docs/operacion/openbao.md`.
- Pruebas que fallan en silencio fuera del gate: `test_crypto_bus_importers.py` si alguien fuera de
  `core/`, `members/` o `ARRANQUE` importa `bus`/`types` (el worker importa solo
  `install_crypto_type_listeners` por `runtime.py`: cargar el keyring desde `runtime.py` con
  `ensure_keys` es un import de `bootstrap`, no vigilado, pero `cli_base.py` es el patrón);
  `test_core_import_direction::test_sin_ciclos_entre_modulos_de_core` si `core/errors.py` importa
  `core/crypto/errors.py` y algo de `core/crypto` importa `core/errors` (hoy no); `test_health_check_registrars`
  si el check `crypto` se registra desde `core/crypto` (permitido: `core/`) o desde un módulo (no);
  `test_kek_path_single_door`; `test_no_direct_now` (el sondeo usa `current_clock()`);
  `test_file_and_function_size` (`service.py` 503 + migración ≈ 100 → cerca de 600, por debajo de
  800; funciones de ≤ 50 líneas); `test_db_grants.py`/`grants.sql` (`apex_worker` sobre
  `crypto_keys`); `test_triggers_siempre_activos.py` no cubre `crypto_*` (siguen `'O'`);
  `tests/core/test_migrations.py` recorre `0001` → head y vuelta: `0015` con `downgrade` exacto.
- Contratos: `migrate-provider --from local --to openbao [--as] [--dry-run]` con confirmación
  `MIGRAR`, una transacción por llave (`unwrap` local → `wrap` openbao → `unwrap` openbao →
  comparación en tiempo constante → `UPDATE provider, wrapped_material`), `crypto_ops` con el
  mismo `batch_id`, `CryptoJob(kind="migrate_provider", data_class=None)`, auditoría `update` en
  `crypto_keys` con `record_id = job_id` desde el CLI, salida 0 "nada que migrar" si no queda
  `local`; `production_guard_error` exige `--as` con `ENV=production` (S4A-D53). Antes de la
  primera migración real sobre `apex-db-1`: `pg_dump -Fc` y `export-kek` (US-116) con
  `verify-kek-backup` reciente (`recent_kek_verify` ya existe para `retire-key`: reutilizar la
  misma exigencia). Blobs de `members.members` byte a byte iguales (no se recifra nada).
- Salud: `/health` → `{status: "degraded", db: "ok", crypto: "sealed", backup, migrations}` con
  503; `GET /members/{id}` → 503 `crypto_unavailable`; `GET /plans` → 200 (no toca el bus;
  `current_user` llama `refresh_current` que **no hace nada sin keyring**, `keyring.py:156-166`:
  bien). Nginx responde 503 del api tal cual (`proxy_intercept_errors off`).

### Bloque B · Avisos (US-120 a US-132)

- Archivos nuevos: `modules/notifications/{__init__,router,schemas,models,service,exceptions}.py`,
  `modules/notifications/channels/{__init__,base,email,whatsapp_link,telegram}.py` (privados: solo
  los importa `notifications`; la regla `private_helper` los vigila si se registran en
  `PRIVATE_HELPERS`), `worker/jobs/notify.py`, `cli_ops/notify.py` (`notify
  [--generate-only|--send-only] [--as]`, `seed-notifications [--as]`), migraciones `0016_notifications_templates`,
  `0017_notification_rules`, `0018_notifications`, `0019_member_channel_preferences` (números según
  C1), `core/export.py` no (es de C), `tests/notifications/*`, `tests/worker/test_notify.py`,
  `tests/cli/test_notify.py`, `tests/migrations/test_001[6-9]_*.py`, `tests/architecture/
  test_notifications_no_bus.py`. Tocados: `main.MODULES`, `migrations/env.py`, `members/{models,
  service,schemas,router,changes}.py` (preferencias: `get_channels`, `set_channels`, `channels_for`,
  `effective_channels`, `MemberChannelPreference` con `__audited__`), `members/contact.py` (`fields`
  opcional), `memberships/{queries,service}.py` (`notification_candidates`, `has_current_or_future`),
  `settings/{schemas,service,router}.py` (`channels` habilitada, `ChannelsSettings`, `ChannelsView`
  con `credentials_present`, `channels_credentials_present`), `auth/{links,users,schemas,router}.py`
  (`forgot` con cuenta y `BackgroundTasks`, `email_sent`), `dashboard/service.py` (`today_count`),
  `core/alerts.py` (claves de contexto), `core/jobs.py` (`DETAIL_KEYS`), `core/ratelimit.py`
  (cubeta nueva si se decide) y `core/config.py` + `.env.example` (`EMAIL_PROVIDER`, `SMTP_HOST`,
  `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `BREVO_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
  `NOTIFY_MAX_ATTEMPTS=3`, `NOTIFY_HTTP_TIMEOUT_S=10`, todos `SecretStr` los secretos), `worker/jobs/
  __init__.py` (`JOBS`), `worker/main.py` (`register_sink(TelegramAlertSink(...))`), `main.py`
  (ídem), `infra/db/grants.sql`, `tests/migrations/test_db_grants.py`, `tests/conftest.py`
  (limpieza), `tests/architecture/{test_contact_callers,test_service_import_graph,
  test_no_cross_models,test_worker_boundaries,test_user_limits_catalog}.py`, `tests/core/
  test_env_example.py` (prueba de "van activas con sus valores" para las nuevas), `tests/worker/
  test_jobs_core.py`, `tests/auth/*` de `forgot` (hoy prueban que **no** lee la base),
  `infra/compose.dev.yml` (Mailpit), `docs/openapi.json`, `types.ts`, `CLAUDE.md` (`notifications/`
  y `core/export.py`), `RUNBOOK.md` §13, `docs/operacion/avisos.md`.
- Pruebas que fallan en silencio fuera del gate: `test_contact_callers.py:106` (igualdad con
  `frozenset()`); `test_service_import_graph.py` (aristas no declaradas: `notifications →
  members/memberships/settings`, `auth → notifications`, `dashboard → notifications`; además
  importa cada par en subproceso limpio en los dos órdenes: `auth → notifications → members →
  audit → auth` **sería un ciclo** si `notifications` importara `auth`; no debe); `test_no_cross_models.py:167`
  (privados de `members`); `test_audited_tables.py` (tabla nueva sin `__audited__`);
  `test_audit_subject.py` (modelo con `member_id` sin `__audit_subject__`);
  `test_writes_have_user_limit.py` (escritura sin cubeta); `test_no_store_routes.py`;
  `test_every_route_has_role.py`; `test_routes_under_api_v1.py`; `test_list_routes_use_page_params.py`
  (lista sin `PageParams`/`q`); `test_events_without_pii.py` (`skip_reason` en un evento);
  `test_settings_no_secrets.py` (campo con `token`/`secret`/`password`); `test_env_example.py`;
  `test_db_grants.py` y el bloque 7 de `grants.sql` (**`dbsetup` falla cerrado** con las cuatro
  tablas nuevas sin clasificar: en desarrollo no corre `dbsetup`, en CI `e2e-stack` y en producción
  sí); `test_worker_boundaries.py` (el worker no escribe SQL ni importa `models`/`router`: el job
  llama `notifications.service`); `test_core_import_direction` (`core/alerts.py` sin `app.modules`);
  `tests/auth` de H-2; `tests/dashboard` que fijan `notifications_today is None`; `test_error_codes_per_route`
  (`responses_for` solo admite códigos del catálogo: 409 `template_name_taken`, `duplicate_active_rule`,
  `notification_closed`; 422 `member_without_phone`, `field=channel`).
- Contratos: `generate_for(session_factory o session, today, by=SYSTEM_USER_ID)` con
  `INSERT ... ON CONFLICT (rule_id, membership_id, target_date) DO NOTHING RETURNING id`;
  `send_pending` con una transacción por aviso y `contact_for_notification` **dentro** de esa
  transacción, confirmada antes de enviar (S4A-D50; el envío ocurre tras el commit y el resultado se
  escribe en una segunda transacción corta); `wa_link(session, id, by)` idempotente; `skip`;
  `today_list`/`today_count` con `today_bogota()` (Q28); `send_transactional_email(to, subject,
  body) -> bool` directo (N-36) con `aiosmtplib` o Brevo y `NOTIFY_HTTP_TIMEOUT_S`;
  `daily_team_summary(today)` → `alert("daily_summary", pending=, failed=, sent=, skipped=,
  run_date=)`; `TelegramAlertSink(token, chat_id, timeout)` con `httpx.Client` síncrono y
  `build_payload` puro. Roles: admin escribe plantillas y reglas; admin y coach gestionan avisos;
  `member` 403. Un dado de baja: `GET /members/{id}/channels` 200 y `PATCH` 409 `member_deleted`
  (N-20; US-123 dice 404: corregido por el desglose). N-33 (refinamiento aceptado en SPRINT-05): el
  correo exige fila `email active = true` **y** `data_consent_at`; sin filas, solo `whatsapp_link`.
- El job `notify` corre a `DAILY_HOUR:DAILY_MINUTE` después de `expirations` (orden de `JOBS`); en
  desarrollo el `worker` residente exige `restart worker` tras tocar `app/worker/` o un service que
  use un job (RUNBOOK §7); `run --rm worker python -m app.worker.main --run-once notify` dos veces el
  mismo día sin duplicar (DoD).

### Bloque C · Recibos y exportaciones (US-137 a US-139)

- Archivos nuevos: `core/export.py`, `modules/payments/receipt.py`, `modules/payments/assets/
  apex-logo-light-bg.png`, `tests/payments/{test_receipt_pure,test_receipt_service,test_export}.py`,
  `tests/members/test_export.py` (con un caso `perf` de 1.000 socios), `tests/core/test_export.py`,
  `web/src/features/payments/components/{ReceiptButton,ExportButton}.tsx`,
  `web/src/features/members/components/ExportButton.tsx`, `web/src/shared/lib/download.ts`.
  Tocados: `payments/{service,router,schemas}.py`, `members/{service,router}.py`, `pyproject.toml`
  (`reportlab`; `pypdf` en `dev`), `uv.lock`, `NOTICE`, `scripts/ci/check-licenses-api.sh` (caso de
  control que rechaza `fpdf2`, LGPL: ya lo hace por omisión; agregar la prueba), `tests/architecture/
  test_third_party_confinement.py` (opcional), `docs/openapi.json`, `types.ts`, `CLAUDE.md`.
- Pruebas que fallan en silencio fuera del gate: `test_no_cross_models.py` (`payments` no importa
  `memberships.models`; `refs_for` por lazy G-03); `test_service_import_graph.py` (`payments →
  memberships` solo perezoso con la marca; `members → memberships` ídem); `test_read_modules.py`
  no aplica; `test_list_rows_without_sensitive_fields.py` si el router declara `response_model`
  con campos sensibles; `test_writes_have_user_limit` no aplica (son `GET`); `test_banned_imports`
  (`reportlab` no es primitiva; `hashlib` sigue prohibido: ningún digest del PDF fuera del bus);
  `test_file_and_function_size.py` (`members/service.py` ≈ 560 + `export` → mantener bajo 800 o
  extraer `members/export.py` como privado y sumarlo al conjunto exacto de `test_no_cross_models`);
  licencias (`check-licenses-api.sh`, `notice.sh`, CI "NOTICE al día").
- Contratos: `GET /payments/{id}/receipt.pdf` (admin y coach; `application/pdf`,
  `Content-Disposition: attachment; filename="recibo-<8>.pdf"`, auditoría `download` sobre
  `payments` con `record_id` y `subject_member_id`), `GET /members/export` y `GET /payments/export`
  (solo admin; `text/csv; charset=utf-8`, BOM, `;`, `\r\n`, `escape_formula` en toda celda,
  columnas exactas de N-29, `StreamingResponse`, auditoría `export` con `after={filters, rows}`
  escrita **antes** de transmitir; `no-store`); el CSV de pagos del mes cuadra con
  `GET /payments/summary`. Fechas en hora de Bogotá (`TZ_DISPLAY`) solo en PDF y CSV.

### Deuda con dueño "v0.2 / Sprint 5" del cierre del 4B: qué entra y qué queda con condición

- **Entra con slice natural:** `notifications` y la regla hacia adelante de la Ley 1581 → Bloque B
  (US-123 con N-33). `rewrap` y compromiso de la KEK (D137, D148, D151): el desglose de EP-15 dice
  que `migrate_provider` no usa `rewrap` (N-05); el escenario "cambiar la KEK y re-envolver todo"
  (`rotar-llave.md:70`, "corresponde a la versión con OpenBao") es exactamente `migrate-provider`
  hacia una llave nueva de Transit o `rotate` de la llave de Transit: el plan debe decir si
  `rewrap` (re-envolver con la versión nueva de la llave Transit tras `transit/keys/<n>/rotate`)
  entra en US-135 o queda en EP-18 (`Llaves`, v0.3). `SELECT` acotado del worker (D204) → la matriz
  de `grants.sql` cambia en B de todos modos: resolverlo ahí.
- **Entra solo si el plan lo decide (hoy sin slice):** `apex_owner` NOSUPERUSER (D206, "Sprint 5 /
  v0.2 infra, antes de operar con datos reales") → Wave 0 o un slice `S5-W0-2` de infra (toca
  `infra/db/roles.sql`, `apply.sh`, `compose.yml` `db`/`migrate`/`dbsetup`/`tools`, RUNBOOK §12,
  `test_db_grants.py`); Caddy y TLS (D45, D66, "v0.2"; `caddy:2-alpine` ya está en el host sin uso;
  `COOKIE_SECURE`, `ALLOW_INSECURE_COOKIE`, P7): `compose.caddy.yml` y `Caddyfile.example` o
  reasignación explícita a EP-20 (v0.3) anotada; `audit.append()` y residuales de `INSERT` (D61);
  verificación criptográfica del manifiesto en el worker y en `retire-key` (D57, D80, D149);
  `UPDATE` por columna en `auth.users` (D203) e `INSERT` de pagos sin columnas de anulación (D202);
  `display_name` (v0.2); firma de etiquetas y `.github/allowed_signers` (D181, D208, titular del
  repositorio); índices de `audit_log` con condición (D5: solo si la línea base de V5 lo pide).
  Cada una recibe en T-DOC un slice del Sprint 5 o un dueño nuevo con versión (C1).
- **Pendientes del plan mismo sin dueño en código:** la alerta `crypto_sealed` por Telegram (N-34,
  1 h, "cuando exista `core.alerts`": existe desde 4A) → Bloque A o B; `IMPORT_DIR` fijo en `tools`
  (D211: solo si la operación lo pide); `validate_reason` sin detección de nombres (D153:
  operación).

### Archivos que el sprint no debe tocar

`core/audit.py` (solo `record`; `AUDIT_ACTIONS` ya trae `download` y `export`), `core/audit_verify.py`,
`core/db.py`, `core/context.py`, `core/locks.py`, `core/pagination.py`, `core/search.py`,
`core/backup_status.py`, `core/migrations_status.py`, `core/crypto/{archive,file_digest,digest,aead,
blob,mac,normalize,secret,signature,types,discovery,registry}.py` (`registry` solo si el plan decide
una clase `sign` para `apex-sign-audit`, que es de EP-17), migraciones `0001` a `0014`,
`modules/{plans,audit}/*` (solo se consumen), `modules/memberships/{sell,lifecycle,expirations,
summary,rules}.py`, `infra/backup/*`, `infra/db/roles.sql` (salvo `apex_owner` si entra),
`infra/nginx/*`, `infra/compose.e2e.yml`, `infra/compose.verify.yml`, `web/src/features/plans/**`,
`web/src/core/api/types.ts` solo por regeneración, `web/src/config/routeTable.ts` y
`routes.reference.ts` (las rutas de avisos ya están; solo cambian si el plan agrega una ruta).

## 3. Capa de datos

### Lo que existe (aplicado en `apex-db-1`; `db_test` se migra desde cero en cada sesión)

- `exec api alembic current` = `0014_audit_log_triggers_always (head)`. Cadena lineal `0001 → … →
  0014` (`0005b` entre `0005` y `0006`); una sola cabeza. Convención de nombres: `00NN_<tema>`
  secuencial (`tests/core/test_migrations.py` solo exige una cabeza y el ciclo completo; ningún
  regex fija el prefijo, pero RUNBOOK §6 y la DoD "ciclo `0001` a `00NN`" cuentan en secuencia).
- Esquemas: `audit`, `auth`, `crypto`, `members`, `memberships`, `payments`, `plans`, `settings`,
  `worker` (nueve; `APP_SCHEMAS` en `core/db.py`): `notifications` **no existe**. `0001_core_schemas`
  creó los esquemas base; `migrations/env.py` usa `APP_SCHEMAS` para el `include_schemas`: sumar
  `notifications` a `APP_SCHEMAS` (en `core/db.py`, compartido) y `grants.sql` (`USAGE ON SCHEMA`,
  `REVOKE ... IN SCHEMA` enumeran los nueve esquemas literalmente: el décimo entra en las cuatro
  sentencias).
- `crypto.crypto_keys`: ocho llaves, todas `version = 1`, `active`, `provider = 'local'` (5
  `encrypt`, 3 `index`; ninguna `sign`); trigger `crypto_keys_guard` que prohíbe cambiar `provider`
  y `wrapped_material`; `crypto.crypto_jobs` sin filas en curso; `crypto.crypto_ops` con filas de
  4B. Roles: `apex` (propietario, superusuario: D206), `apex_api`, `apex_worker`, `apex_backup`
  con la matriz de `grants.sql`.
- `worker.job_runs` con CHECK `ck_job_runs_result` de ocho valores (sin `skipped`); `members.members`
  con `data_consent_at` (nula admitida) y `deleted_at`; `settings.settings_sections` con cuatro
  claves posibles (sin fila `channels`: la sección nace con sus defaults en el primer `GET`, patrón
  de US-054, sin migración); `audit.audit_log` con triggers `ENABLE ALWAYS` desde `0014`.

### Lo que agrega el sprint

- Según `SPRINT-05.md`: `crypto_jobs_single_running` y `crypto_provider_openbao` (EP-15, rango
  0030-0034), `notifications_templates`, `notification_rules`, `notifications` (`membership_id NOT
  NULL`, N-37), `member_channel_preferences` (EP-14, 0020-0029), ninguna de EP-16, y "la función de
  guarda de `crypto_keys` de `0003` se extiende con una migración nueva". Según el código: las dos
  primeras **no hacen falta** (sección 1) y la de la guarda **sí**. Propuesta de numeración
  secuencial, en orden de aplicación (EP-15 primero): `0015_crypto_keys_guard_provider`
  (`CREATE OR REPLACE FUNCTION crypto.guard_keys_update()` que admite `provider` `local → openbao`
  con `wrapped_material` nuevo en la misma fila y nada más; `downgrade` al texto de `0003`),
  `0016_notifications_schema_templates` (`CREATE SCHEMA notifications` + `notification_templates`,
  único en `name`, sin `deleted_at`), `0017_notification_rules` (FK a plantillas, CHECK de
  `trigger`, de `channel IN ('email', 'whatsapp_link')`, del signo de `offset_days`, único parcial
  `(trigger, offset_days, channel) WHERE is_active`), `0018_notifications` (`member_id` y
  `membership_id` UUID sin FK entre esquemas, `membership_id NOT NULL`, único `(rule_id,
  membership_id, target_date)`, CHECK de `status`, de `attempts >= 0` y `status <> 'skipped' OR
  skip_reason IS NOT NULL`, índices `(status, target_date)`, `(member_id, target_date DESC)`),
  `0019_member_channel_preferences` (FK a `members.members`, CHECK `channel`, único `(member_id,
  channel)`), y `0020_job_runs_result_skipped` solo si C4 lo decide. Los rangos "reservados" del
  README del desglose se abandonan en favor de la secuencia real (C1). `test_db_grants.py` y
  `grants.sql` clasifican las cuatro tablas; `tests/migrations/test_001N_*.py` con `upgrade`,
  `downgrade -1`, `upgrade` y las restricciones.
- Migraciones de datos: `migrate-provider` (llaves) y `seed-notifications` (plantillas y reglas por
  defecto) son comandos del CLI, idempotentes y auditados (regla de datos 8); ninguna va en
  Alembic. `migrate-provider` corre como `tools` (propietario): el trigger de `0015` lo deja pasar y
  `apex_api` sigue sin poder cambiar `provider` (solo `UPDATE (updated_at)`).

### Riesgos de orden y de la suite

- `0015` va en el Bloque A antes de `migrate-provider`; `0016` a `0019` en el Bloque B antes del
  primer `seed-notifications`. El `api` de desarrollo monta `migrations/` por bind y migra al
  reiniciar (`compose.dev.yml:11-17`): una migración a medio escribir bajo `--reload` rompe el
  arranque (mitigación de 4A: escribir y probar contra `db_test` o parar `api`).
- `pg_dump -Fc` de `apex-db-1` antes de `0015` (P-MIG; `*.dump` ignorado) y antes de la primera
  `migrate-provider` real, más `export-kek` con `verify-kek-backup` (riesgo 1 del plan).
- `tests/conftest.py` `LIMPIEZA_DE_SESION` y `dos_sesiones`: las tablas nuevas entran antes de
  `members` (FK de `member_channel_preferences`) y `notifications` antes de `notification_rules` y
  `notification_templates` (FK). `tests/migrations/test_db_grants.py` corre sobre `db_test` con
  `apply.sh`: la matriz nueva se prueba ahí, no en `apex-db-1` (en desarrollo los roles se aplican
  a mano, RUNBOOK §12).
- Rollback: `downgrade 0015` solo cambia la función (sin filas); `downgrade 0016-0019` borra tablas
  y el esquema (datos de avisos perdidos: aceptable en v0.2 solo antes de operar; RUNBOOK §6 gana
  las entradas). Tras `migrate-provider`, **no hay rollback de datos** sin la KEK local: el
  archivo `kek.bin` se conserva hasta verificar la migración (criterio 2 de US-135 se demuestra en
  el ensayo, no en producción).
- Con OpenBao sellado, `migrate`/`dbsetup` corren igual (no usan el bus); el api arranca degradado;
  `worker` carga el keyring en el sondeo.

## 4. Servicios Docker y estrategia de rebuild

- Estado (`docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml ps`): seis
  contenedores healthy: `apex-api-1` (`127.0.0.1:8181`, bind de `src` y `migrations`, `--reload`),
  `apex-backup-1` (`apex-backup:local`), `apex-db-1` (`127.0.0.1:5442`, 16 h arriba),
  `apex-db_test-1` (`127.0.0.1:5443`), `apex-web-1` (`0.0.0.0:8180`), `apex-worker-1`. Imágenes
  `apex-api:local` (`20a30740af53`, creada 2026-11-04 16:41 UTC, etiqueta de revisión `a1ad4cb`),
  `apex-web:local` (`7362c951e9e3`, 14:30 UTC, `a1ad4cb`) y `apex-backup:local` (`34874b888a0a`):
  el último commit que toca `api/` e `infra/` es `6cc9b8e` y `web/` es `cbbe6bc`, anteriores a
  `a1ad4cb` (solo documentos): **las imágenes corresponden al código de HEAD**. `apex-api:ci` del
  2026-10-21 sigue sin uso. `caddy:2-alpine` está en el host (otro uso; relevante solo si Caddy
  entra). **No hay imagen de OpenBao ni de Mailpit en el host**: la primera `up -d openbao` las
  descarga (red necesaria; el quirk de buildx no aplica a imágenes públicas).
- Cómo corre cada servicio: `api` con bind de `src/` y `migrations/` (cambios sin rebuild);
  `worker` y `tools` con bind de `src/` y `migrations/` en solo lectura (`compose.dev.yml:34-50`):
  `migrate-provider`, `notify`, `seed-notifications` corren con `run --rm tools ...`/`run --rm
  worker ...` sin reconstruir; el `worker` residente exige `restart worker` tras tocar `app/worker/`
  o un service que use un job (`notify`, `memberships`, `members`, `notifications`). La imagen de
  producción `apex-api:local` **cambia tres veces**: Bloque A (`openbao_provider.py`, `0015`,
  dependencias nuevas no; `httpx` ya está), Bloque B (`aiosmtplib`, `uv.lock`) y Bloque C
  (`reportlab`, `pillow`, `charset-normalizer`, el logo en `assets/`), más el cierre. `web` cambia
  en 5a/5b. `migrate` y `dbsetup` (perfil `prod-init`) usan `apex-api:local` y `postgres:16`:
  tras `0015`-`0019` y los grants nuevos, el stack de producción exige reconstruir el api antes de
  `migrate` (S4B-D98: sin bind de código).
- Servicio nuevo `openbao` (`infra/compose.yml`): imagen `openbao/openbao:<2.x>@sha256:<digest>`
  con fecha y comando de renovación (S3-D62; `test_images_pinned.sh`), `command: server -config
  /openbao/config/config.hcl`, sin `ports`, `cap_add: [IPC_LOCK]` o `disable_mlock = true` en
  `config.hcl` (en Docker Desktop/WSL2 `mlock` suele fallar: `disable_mlock` es lo seguro de
  documentar), volúmenes `openbao-data:/openbao/file` y `openbao-token:/openbao/token`, healthcheck
  `bao status` (sale 0 desellado, 2 sellado, 1 error: el healthcheck debe tratar 2 como "vivo"
  —`CMD-SHELL "bao status; rc=$?; [ $rc -eq 0 ] || [ $rc -eq 2 ]"`— o el `api` no puede depender de
  él), `depends_on` ninguno; `api.depends_on.openbao: service_healthy`,
  `worker.depends_on.openbao: service_healthy`; `api` y `worker` con `openbao-token:/run/secrets/
  openbao:ro`; red por defecto (subred fija `172.30.0.0/24`, sin IP fija para `openbao`;
  `OPENBAO_ADDR=http://openbao:8200`). En `compose.dev.yml`: `openbao` con `command: server -dev
  -dev-root-token-id=<token de desarrollo>` y `BAO_DEV_LISTEN_ADDRESS=0.0.0.0:8200`, sin puerto
  publicado al host (o `127.0.0.1:8200` solo si el plan lo pide para `bao` desde el host: no hay
  `bao` en el host, así que `docker compose exec openbao bao ...`), y el servidor `mailpit`
  (`axllent/mailpit:<ver>@sha256:...`, SMTP 1025 interno, UI opcional en `127.0.0.1:8025`).
- Desellado: en producción, tras cada reinicio del contenedor `openbao`, el operador corre tres veces
  `docker compose --env-file .env --env-file .env.ops -f infra/compose.yml exec openbao bao operator
  unseal` (una llave por vez) siguiendo `docs/operacion/openbao.md`; `/health` pasa de `sealed` a
  `ok` en ≤ `CRYPTO_RECOVERY_POLL_S`. En desarrollo el modo dev arranca desellado y el escenario de
  US-136 se ensaya con `bao operator seal` y `unseal` con la llave que imprime el modo dev (o con un
  `openbao` de pruebas inicializado por `bootstrap.sh` con 5/3 y llaves efímeras en CI). El token
  periódico del api: `bootstrap.sh` lo escribe en `openbao-token/token` con modo 600 y `uid 10001`
  (el volumen es del contenedor `openbao`, que corre como `openbao` uid 100: `chown` dentro del
  script o `user:` en el servicio; decidir en W0).
- `deploy.sh` (S4B-B4): construye con `GIT_SHA`, `up -d` y sondea `/api/v1/health` con `curl -f`
  hasta `db ok` y `migrations ok`: con `crypto: sealed` el 503 hace fallar la espera. Cambio: aceptar
  `503` cuando el cuerpo trae `db ok`, `migrations ok` y `crypto: sealed`, y terminar con el mensaje
  del plan ("api en estado sellado: desellar OpenBao") y código distinto de 0 **sin** `rollback`
  automático (`test_deploy_script.sh` fija hoy el comportamiento: cambia con prueba).
- Quirk del equipo (RUNBOOK §7): `docker compose build` y `up --build` fallan con Compose 5.6.1 +
  buildx 0.38.1 (`build.network: host`): se construye con `docker buildx build --load --network
  host --allow network.host -t apex-api:local -f api/Dockerfile api` y se levanta con `up -d
  --no-build`. **No se reconstruyó nada en esta fase.** La demo del sprint dice `docker compose up
  -d --build`: en este equipo es `buildx` + `up -d --no-build`.
- Red y volúmenes: subred `172.30.0.0/24`, `web` en `.10`; volúmenes `pgdata`, `uploads`, `keys`,
  `backups` + `openbao-data`, `openbao-token`. `test_compose_config.sh:92-93` fija la lista en dos
  aserciones. `.gitignore` no necesita cambios (el token nunca sale del volumen).

## 5. Contratos API y front

### Estado de `docs/openapi.json` en HEAD

63 operaciones en 47 rutas. `HealthOut` publica `status`, `db`, `version`, `backup`
(`ok|attention|unknown`), `migrations` (`ok|mismatch|unknown`) y `additionalProperties: true`;
`DashboardOut.notifications_today` es `integer | null`; `IssuedLinkOut` `{url, purpose,
expires_at}`; `ErrorResponse` con `503` "Base de datos ocupada" en toda operación con rol.
`web/src/core/api/types.ts:1206` coincide.

### Lo que cambia

- `GET /health` y `GET /api/v1/health`: campo `crypto` (`ok|sealed|unreachable|unknown`, crítico:
  distinto de `ok` → 503 `degraded`). Explícito en `HealthOut`; regenerar `openapi.json` y
  `types.ts` en el Bloque A.
- Endpoints nuevos (22, todos con rol, bajo `/api/v1`, con `no_store`): plantillas (5: `GET`, `POST`,
  `GET /{id}`, `PATCH /{id}`, `POST /preview`), reglas (4), avisos (5: `GET`, `GET /today`, `GET
  /{id}`, `GET /{id}/wa-link`, `POST /{id}/skip`), `GET|PATCH /settings/channels` (2), `GET|PATCH
  /members/{id}/channels` (2), `GET /members/{id}/notifications` (1; vive en el router de
  `notifications`), `GET /payments/{id}/receipt.pdf`, `GET /members/export`, `GET /payments/export`
  (3). Códigos nuevos del catálogo: 409 `template_name_taken`, `duplicate_active_rule`,
  `notification_closed` (o el nombre que fije el plan para "ya `sent`/`skipped`"), 422
  `member_without_phone`, 422 `field=channel`; 503 `crypto_unavailable` compartiendo el 503 con
  `busy`. Rutas con efecto en `GET`: `wa-link` (documentado en OpenAPI, `no-store`).
- Endpoints cambiados: `POST /auth/forgot` (sin cambio de contrato; envío real), `POST /users` y
  `POST /users/{id}/resend-link` (`email_sent: bool` en `CreateUserOut` e `IssuedLinkOut`),
  `GET /dashboard` (`notifications_today` deja de ser `null`), `GET|PATCH /settings/{section}` con
  `channels` habilitada.
- Cubetas: escrituras nuevas en `admin-write` (plantillas, reglas, `settings/channels`) y
  `memberships-write` o una `notifications-write` nueva (skip, canales del socio): si nace una
  cubeta, entra en `USER_LIMITS`, `user_limits_from`, `Settings.USER_NOTIFICATIONS_WRITE_LIMIT_PER_MIN`,
  `.env.example` (y el comentario "Catálogo: 12 cubetas y 11 variables" que
  `test_env_example.py:166` cita por conteo) y `test_user_limits_catalog`.
- CLI (contrato de operación): `migrate-provider --from local --to openbao [--as] [--dry-run]`,
  `notify [--generate-only|--send-only] [--as]`, `seed-notifications [--as]`; códigos 0/1/2 como los
  existentes; `worker --run-once notify`.
- Front: `ENABLED_FEATURES` gana `notifications` (10); páginas `TodayPage`, `RulesPage`,
  `HistoryPage` (rutas ya en `routeTable.ts`), pestaña `avisos` de la ficha (hija de la feature
  `notifications`), pestaña "Canales" de Config, `ReceiptButton`, dos `ExportButton`, KPI "Por
  avisar" real, mensajes reales de `ForgotPage`; `shared/lib/download.ts`. Sin cambios en `nav.ts`,
  `permissions.ts` ni `routeTable.ts` salvo que el plan agregue una ruta.

### Contradicciones entre desgloses y código que el plan cierra en T-DOC (Wave 0)

- `KeyProvider` síncrono + `httpx.Client` + `anyio.to_thread` (desglose EP-15) → el puerto **ya es
  `async`**; `OpenBaoProvider` con `httpx.AsyncClient` (como dice US-134).
- `wrap(key_ref, dek)` / `unwrap(key_ref, wrapped)` (SPRINT-05, US-134) → hoy `wrap(dek)` /
  `unwrap(wrapped)`: decidir si se agrega `key_ref` (LocalFileProvider lo ignora) o si el
  `OpenBaoProvider` deriva la llave Transit de `data_class`/`purpose` por otro camino.
- `0030_crypto_jobs_single_running` y `0031_crypto_provider_openbao` → **no hacen falta**
  (`0003`); sí hace falta `0015_crypto_keys_guard_provider` (el plan la nombra sin número).
- Rangos `0020-0039` → secuencia real `0015` en adelante.
- `result = skipped` + `details = {"reason": "crypto_sealed"}` (desglose EP-15) → `RESULTS`/CHECK sin
  `skipped` y `details` solo enteros: C4.
- `register_health_check("crypto", fn)` → `register_health_check("crypto", fn, critical=True,
  allowed=..., healthy={"ok"})`.
- `/health` → `{status, db, crypto, backup, version}` (US-136) → también `migrations` (4B).
- "Nginx no depende de la salud del api" (riesgo 2 del plan) → `web.depends_on.api:
  service_healthy` desde S4B-W0-3: C3.
- `alert(kind, text)` (desglose EP-14, `05_service_design.md`) → `alert(code, **context)` con
  claves cerradas y valores `str|int`; `AlertSink.send(code, context)` síncrono.
- `test_core_no_modules.py` nuevo → ya existe `test_core_import_direction::test_core_no_importa_modulos`.
- `members.service.exists` → `ensure_exists`; `labels_for` → `refs_for`; `current_for` →
  `status_for`; `contact_for_notification(member_id, "notify", fields=...)` → sin `fields` (se
  agrega, compatible).
- US-123 criterio 3 (404 para dado de baja) → N-20: `GET` 200 y `PATCH` 409 `member_deleted`
  (desglose ya corregido). US-123 criterio 1 ("sin filas, todos `active = true`") → N-33
  refinado: sin filas solo `whatsapp_link`.
- US-137 "auditoría `export`" → `download` (N-08; desglose corregido).
- US-138 columnas de 12 → las 9 de N-29 (desglose corregido).
- `uv run python -m app.cli migrate-provider` (US-135) → `docker compose run --rm tools
  migrate-provider` (la imagen no trae `uv`).
- `chat_id` en `settings.channels` (desglose) frente a `.env` (US-126): C5.
- `downloadBlob` en `shared/ui/` → `shared/lib/`.
- `RUNBOOK.md:311` ("rotación llega en v0.2 con OpenBao, `cli rotate-key`") → `rotate-key` existe
  desde 4B (S4B-B3b): texto desactualizado.
- `CLAUDE.md`: "`worker/jobs/`: `notify.py`, `sign_audit.py` (v0.2 en adelante)" → `sign_audit` es
  EP-17 (v0.3, dueño "sign-audit: v0.3" en 4B); `cli.py` "rotate-key, sign-audit llegan en 4B/Sprint
  5" → `rotate-key` ya llegó; `.env.example` "openbao desde v0.2" se vuelve verdad.
- `04_architecture_decision.md` §4 lista `sign_audit` en el worker y "firma ML-DSA (v1.0)" del
  backup: fuera de este sprint.

## 6. Línea base en HEAD `a1ad4cb`

- `git log --oneline -3`: `a1ad4cb docs(sprint-04b): V12 limpieza y cierre del Sprint 4B`,
  `b8a7e97 docs(sprint-04b): V9 final, V11 verify-delivery, estado al cierre y dueños
  (S4B-D209..D211)`, `6cc9b8e fix(cli,db): restore-kek sale 1 si no puede registrar la bitácora
  (S4B-D207); apply.sh cuenta el ARRAY validado (S4B-D201); decisiones V8 y V10`. `git status`
  limpio; `git worktree list` solo el principal.
- Suites (no corridas aquí; cita de `DECISIONES.md`, "Estado al cierre del Sprint 4B", V9 sobre
  `6cc9b8e`, mismo código que HEAD): api `pytest -m "not perf"` **6.002 passed, 52 skipped, 27
  deselected, cobertura 95,03 %** (umbral 80 %); `tests/architecture` **533 sin saltos**; scripts
  de infraestructura 6 de 6 en verde; front **3.149 pruebas en 173 archivos, cobertura 97,86 %**,
  lint 0, `tsc` 0, build; `pre-commit --all-files` en verde; licencias api y web, `NOTICE`,
  `npm audit` y `pip-audit` sin hallazgos. Las 52 saltadas son del `age` falso y real en Windows
  (corren en el contenedor Linux y en CI, que exige 0 saltos; S4B-D103).
- Corrido en esta fase (HEAD, árbol limpio):
  - `cd api && uv run ruff check .` → `All checks passed!` (código 0).
  - `cd api && uv run ruff format --check .` → `595 files already formatted` (código 0).
  - `cd api && uv run mypy src` → `Success: no issues found in 151 source files` (código 0).
  - `cd web && npx tsc --noEmit` → sin salida, código 0.
- Stack: seis contenedores healthy (sección 4); `exec api alembic current` =
  `0014_audit_log_triggers_always (head)`; imágenes con revisión `a1ad4cb`.
- `.env` local (solo nombres): `WEB_PORT=8180`, `API_PORT=8181`, `DB_PORT=5442`, `DB_TEST_PORT=5443`,
  `TEST_DATABASE_URL=postgresql+asyncpg://apex:apex-test@127.0.0.1:5443/apex_test`,
  `CRYPTO_PROVIDER=local`. Los puertos 80, 8000, 5432 y 5433 los escucha otro proyecto (PID 12672);
  8200 libre y no se publica. `.env`, `.env.ops` y `.env.seed` no están versionados. `age`, `bao`,
  `gh` y `jq` no están en el host; `uv` en `~/.local/bin`; Compose v5.6.1.

## 7. Bugs, desajustes de configuración y contradicciones documentales

1. `provider.py` ya es `async` y sin `key_ref` en `wrap`/`unwrap`; el desglose de EP-15 lo describe
   síncrono y SPRINT-05 pide `key_ref`.
2. `bootstrap._create_missing` escribe `provider="local"` literal y `SIGNING_KEY_REF` local; con
   `CRYPTO_PROVIDER=openbao` crearía filas incoherentes.
3. `Keyring._load_rows` desenvuelve con un solo proveedor; `configure_provider` admite uno solo:
   la migración interrumpida (llaves en dos proveedores) y `migrate-provider` necesitan dos vivos.
4. `get_key_provider("openbao")` → `unknown_provider`; `missing_secrets` no conoce el token.
5. Trigger `crypto_keys_guard` de `0003` prohíbe `provider` y `wrapped_material`: migración
   `0015` obligatoria; `0030`/`0031` innecesarias; numeración `0015+`.
6. `main._startup` relanza sin DEK; sin handler de `CryptoError` (500); `MENSAJE_503` fijo;
   `HealthOut` sin `crypto`.
7. `compose.yml`: `web` y `worker` dependen de `api` healthy con healthcheck de 200; `deploy.sh`
   con `curl -f`: el estado sellado deja el stack sin front y el despliegue en fallo.
8. `RESULTS`/CHECK `0012` sin `skipped`; `details` solo enteros; `JobSpec` sin `needs_crypto`;
   `worker/runtime.py` sin proveedor ni keyring; `worker` sin `keys`/token en Compose
   (`test_compose_config.sh:86` lo fija "hasta el Sprint 5").
9. `apex_worker` sin privilegios sobre `crypto.crypto_keys` (`FOR SHARE` exige `UPDATE`); cuatro
   tablas nuevas y el esquema `notifications` fuera de `grants.sql` (fail-closed), `test_db_grants`,
   `APP_SCHEMAS`.
10. `CONTACT_CALLERS` vacío y fijado por igualdad; `contact_for_notification` sin `fields`.
11. `ALLOWED_EDGES`/`LAZY_IMPORT_WHITELIST`, privados de `members`, `ENABLED_FEATURES.size == 9`,
    `len(PUBLIC_ROUTES) == 8`, `SECTION_REGISTRY` "exactamente las habilitadas",
    `ALERT_CONTEXT_KEYS`, `DETAIL_KEYS`, archivos del worker, `MODULES`: listas cerradas que
    cambian en el Rojo de cada bloque.
12. `ENABLED_SECTIONS` sin `channels` (404); `ConfigPage` con cuatro pestañas.
13. `auth.forgot` no lee la base (H-2, S2-D36); US-131 lo cambia: la decisión se enmienda y las
    pruebas de `tests/auth` que fijan "no consulta" se reescriben.
14. `memberships.service` sin `notification_candidates`/`has_current_or_future`; `labels_for`/
    `current_for` existen como `refs_for`/`status_for`; `members.service.exists` es `ensure_exists`.
15. `reportlab`, `aiosmtplib`, `pypdf`, Mailpit y OpenBao no están en el repo ni en el host;
    `pillow` (HPND/MIT-CMU) sin verificar contra `check-licenses-api.sh`; `notice.sh` con bloque
    literal.
16. `test_env_example.py` y `extra="forbid"`: cada variable nueva de `Settings` debe ir en
    `.env.example` y toda clave ajena en `NON_API_ENV_VARS` (un `.env` con claves desconocidas
    tumba api, worker y `tools`).
17. CI `e2e-stack` y `compose-smoke.sh` no conocen `openbao` ni Mailpit; el smoke de la DoD
    (sellar/desellar) no tiene paso.
18. `FutureKpis.tsx`, `ForgotPage.tsx` (DESIGN-GAP H-2), pestaña `avisos` deshabilitada,
    `shared/ui` sin `downloadBlob`: cambios de front previstos; "Regenerar lista" de
    `PorAvisarHoy.html` sin endpoint.
19. Deuda con dueño "v0.2 / Sprint 5" sin slice en `SPRINT-05.md` (sección 2, última parte).
20. Textos desactualizados: `RUNBOOK.md:311`, `CLAUDE.md` (`sign_audit` en v0.2, `rotate-key`
    "llega"), `04_architecture_decision.md` §4 (`sign_audit`, firma ML-DSA del backup),
    US-133 ("token o AppRole": el desglose fija token periódico), US-134 ("si es enum de base sin
    ese valor, migración": es CHECK y ya lo tiene).

## 8. Riesgos del plan ampliados con lo visto en el código

1. [HIGH] Pérdida de las llaves de desellado (riesgo 1 del plan): además, **tras `migrate-provider`
   el respaldo de la KEK local (`export-kek`) deja de cubrir las DEK**; la continuidad pasa a
   depender del respaldo del volumen `openbao-data` (que `infra/backup/run.sh` **no** incluye hoy:
   solo `pg_dump` y `uploads`) y de las 5 llaves Shamir. Mitigación: conservar `kek.bin` y su
   respaldo hasta verificar; sumar `openbao-data` al respaldo cifrado (o documentar que sin él la
   base restaurada es ilegible) y ensayar restauración completa (base + OpenBao) en una base limpia.
2. [HIGH] OpenBao sellado tras reiniciar (riesgo 2 del plan) con Compose tal como está: `web` y
   `worker` no arrancan, `deploy.sh` falla y el api queda `unhealthy` sin reinicio (Compose no
   reinicia por salud). Mitigación: C3.
3. [HIGH] `migrate-provider` sobre `apex-db-1` (8 llaves) y el trigger `0015`: una fila con
   `provider = openbao` y `wrapped_material` local (o al revés) deja esa clase ilegible.
   Mitigación: verificación del envoltorio nuevo antes del `UPDATE`, una transacción por llave,
   `pg_dump` + `export-kek` previos, ensayo en `db_test` y en una base `*_sim`, y nunca sobre datos
   reales sin confirmación humana (`MIGRAR`).
4. [MEDIUM] Variables nuevas y `extra="forbid"` (riesgo 3 del 4B repetido): `OPENBAO_*`, `SMTP_*`,
   `BREVO_API_KEY`, `TELEGRAM_*`, `NOTIFY_*`, `EMAIL_PROVIDER`, `CRYPTO_RECOVERY_POLL_S`. Mitigación:
   todas en `Settings` + `.env.example` en el mismo slice (`test_env_example`), smoke de arranque.
5. [MEDIUM] Canales externos (riesgo 3 del plan): `AlertSink.send` síncrono con `httpx.Client` dentro
   del loop del worker bloquea el latido hasta el timeout (10 s < 120 s del healthcheck: tolerable);
   `send_pending` con `aiosmtplib` async. Mitigación: timeouts explícitos, una transacción por
   aviso, `failed` visible.
6. [MEDIUM] `forgot` con cuenta real (H-2 revertida): diferencia de tiempo entre correo existente e
   inexistente. Mitigación del plan (`BackgroundTasks` tras el 204 + `wait_floor`) con prueba de
   tiempos; el `OneTimeToken` se emite en una transacción corta antes de responder o en la tarea.
7. [MEDIUM] Licencia de `pillow` (dependencia de `reportlab`) y verificación de ruedas `cp312`
   sin red en esta fase. Mitigación: `uv add reportlab` + `check-licenses-api.sh` en W0 (C8);
   alternativa: `reportlab` sin `pillow` no sirve para el PNG del logo (habría que incrustar el logo
   como vector o aceptar la excepción si la licencia es permisiva, que lo es).
8. [MEDIUM] Memoria del equipo: la suite completa del api ya corre "en tres partes con
   `--cov-append` por memoria" (4B); el Sprint 5 suma un módulo, un proveedor con `httpx` y un
   OpenBao real en pruebas de integración. Mitigación: pruebas de contrato contra OpenBao solo
   marcadas (`openbao`) y con el servicio de `compose.dev.yml`; `run-gates.sh` por partes.
9. [MEDIUM] `grants.sql` fail-closed: una tabla nueva sin clasificar detiene `dbsetup` en CI y en
   producción, no en desarrollo (donde no corre). Mitigación: `test_db_grants.py` en el Rojo de cada
   migración (corre sobre `db_test` con `apply.sh`).
10. [MEDIUM] CSV con datos en claro (riesgo 5 del plan): además, `GET /members/export` sin cubeta
    permitiría descargar en bucle. Mitigación: cubeta `members-reveal` (30/min, 200/h, 600/día) o
    propia, confirmación en el front, auditoría previa al stream.
11. [LOW] `wa-link` como `GET` con efecto: `no-store`, idempotente, solo al pulsar; un prefetch no
    lo ejecuta porque exige `Authorization`.
12. [LOW] `e2e-stack` de CI arranca `openbao` (modo dev) y Mailpit: tiempo de arranque mayor;
    `down -v` lo limpia.
13. [LOW] `caddy:2-alpine` y `apex-api:ci` en el host sin uso; no interfieren.
14. [LOW] Los triggers `crypto_*` de `0003` siguen en `'O'` (residual de 4B); `0015` los conserva
    tal cual.

## 9. Condiciones para VERDE

Se incorporan al plan de la Fase 1; el plan-critic las verifica.

1. **T-DOC (Wave 0, antes de tocar código):** `SPRINT-05.md`, los tres `BREAKDOWN.md` y
   `DECISIONES.md` cierran: (a) la numeración real de migraciones (`0015_crypto_keys_guard_provider`,
   `0016`-`0019` de avisos, `0020_job_runs_result_skipped` solo si C4; sin `0030`/`0031`/`0035`) y la
   DoD "ciclo `0001` a `00NN`"; (b) el puerto `KeyProvider` `async` (sin `anyio`, `httpx.AsyncClient`)
   y la decisión sobre `key_ref`; (c) los nombres de la sección 5 (`refs_for`, `status_for`,
   `ensure_exists`, `alert(code, **context)`, `register_health_check(..., critical=True, allowed=,
   healthy=)`, `download`, columnas N-29, `tools` sin `uv run`, N-20 en US-123, N-33 refinado);
   (d) el destino de cada deuda con dueño "v0.2 / Sprint 5" (sección 2): `apex_owner` (D206),
   Caddy/TLS (D45, D66), `audit.append()` (D61), `rewrap` (D137, D148, D151), manifiesto en worker
   y `retire-key` (D57, D80, D149), `UPDATE` por columna y `SELECT` acotado (D202-D204),
   `display_name`, índices (D5), firma de etiquetas (D181, D208), alerta `crypto_sealed`: un slice
   del Sprint 5 o un dueño nuevo con versión, anotado; (e) `CLAUDE.md` (estructura con
   `notifications/`, `core/export.py`, `core/crypto/openbao_provider.py`, `infra/openbao/`,
   `worker/jobs/notify.py`; `sign_audit` a v0.3; `rotate-key` existente), `RUNBOOK.md:311`,
   `04_architecture_decision.md` §4 y US-133/US-134 corregidos; (f) US-123 pasa de
   `NEEDS_REFINEMENT` a READY con N-33 y US-126 de `ARCHITECTURAL_GAP_DETECTED` a READY (G-08 ya
   está en el código).
2. **Bloque A (Rojo, bus):** `provider.py` con el registro por nombre (`local`, `openbao`) y
   `get_key_provider` que construye el que pide `CRYPTO_PROVIDER` **y** mantiene el `local` vivo
   mientras existan filas `provider = 'local'` (o `migrate-provider` recibe los dos por
   argumento); `Keyring._load_rows` elige el proveedor por `fila.provider`; `_create_missing` escribe
   el `provider` real y, con `openbao`, el `key_ref` de Transit; `missing_secrets` exige
   `OPENBAO_TOKEN_PATH` legible con `openbao`; `OpenBaoProvider` con `httpx.AsyncClient`, timeout,
   token leído del archivo (nunca en `repr`, logs ni `crypto_ops`), `renew-self`, `map_error` puro y
   códigos `sealed`/`unreachable`/`forbidden` en `CryptoCode`; suite de contrato
   `test_provider_contract.py` parametrizada (`local` siempre; `openbao` con marcador y el servicio
   de `compose.dev.yml`); `0015` con `CREATE OR REPLACE` de la guarda (solo `local → openbao` con
   `wrapped_material` nuevo en la misma fila) y `downgrade` exacto; `migrate-provider` en
   `cli_ops/migrate_provider.py` (una transacción por llave, verificación antes del `UPDATE`,
   `batch_scope`, `CryptoJob`, auditoría desde el CLI, `MIGRAR`, `--dry-run`, "nada que migrar",
   `production_guard_error`), con prueba de interrupción y reanudación con `dos_sesiones`;
   `kek_backup`/`verify-kek-backup` con mensaje claro para llaves `openbao`; `pg_dump` +
   `export-kek` + `verify-kek-backup` antes de la primera migración real; blobs byte a byte.
3. **Bloque A (Rojo, salud y Compose):** `main._startup` arranca degradado solo con `openbao`
   `sealed`/`unreachable` (sin KEK local sigue sin arrancar: `test_startup_failure.py` se
   reescribe así), sondeo cada `CRYPTO_RECOVERY_POLL_S` con `current_clock()` y log por transición;
   `core/crypto/health.py` (`health_state` puro + estado del proceso) registrado desde `main.py`
   como `crypto` crítico; `HealthOut.crypto` explícito y `HEALTH_CACHE_TTL_S["crypto"] <= 30`;
   handler de `CryptoError` en `core/errors.py` → 503 `crypto_unavailable` (solo para
   `crypto_unavailable`/`sealed`/`unreachable`; `MENSAJE_503` ampliado; el resto de códigos no
   cambia); `worker/runtime.py` carga proveedor y keyring (sin crear llaves) y sondea; `JobSpec.needs_crypto`
   y la omisión según C4; `infra/compose.yml`: healthcheck del `api` que acepta 503 con `db ok` y
   `migrations ok` (JSON parseado con `python -c`), `api`/`worker` con `openbao-token:ro` y
   `depends_on.openbao` con un healthcheck de OpenBao que trata "sellado" como vivo; `deploy.sh`
   que distingue `crypto: sealed` ("api en estado sellado: desellar OpenBao") con su prueba en
   `test_deploy_script.sh`; `test_compose_config.sh` con las aserciones nuevas (`openbao` sin
   `ports`, volúmenes, token `:ro`, worker sin `keys`/`uploads` pero con el token); `openapi.json`
   y `types.ts` regenerados; evidencia de `/health` en los tres estados en el cuaderno.
4. **Bloque A/B (worker):** decisión escrita entre `0020_job_runs_result_skipped` (`RESULTS`,
   `EXIT_BY_RESULT`, CHECK) y `result = ok` con `omitido_sellado: 1` en `DETAIL_KEYS`;
   `DETAIL_KEYS` gana las claves enteras de `notify`; `JOBS` suma `notify` tras `expirations` y
   `test_worker_boundaries.py` gana `jobs/notify.py`; `grants.sql` y `test_db_grants.py` dan a
   `apex_worker` `SELECT` y `UPDATE (updated_at)` sobre `crypto.crypto_keys` (anotado como
   ampliación de D61) y lo necesario sobre las tablas de avisos; `run --rm worker --run-once notify`
   dos veces sin duplicar.
5. **Bloque B (Rojo, módulo y contratos):** `main.MODULES` gana `notifications` antes de
   `dashboard`; `migrations/env.py` importa sus `models`; `APP_SCHEMAS` gana `notifications`;
   `grants.sql` (cuatro sentencias de esquemas, matriz y `ARRAY` `clasificadas`) y
   `test_db_grants.PRIVILEGIOS` clasifican las cuatro tablas; `tests/conftest.py` las limpia en
   orden; `test_contact_callers.CONTACT_CALLERS = {"modules/notifications/service.py"}`;
   `ALLOWED_EDGES` gana `notifications → {members, memberships, settings}`, `auth → notifications`,
   `dashboard → notifications` (sin ciclo: `notifications` nunca importa `auth` ni `dashboard`);
   `contact_for_notification` gana `fields` opcional compatible; `memberships` gana
   `notification_candidates` y `has_current_or_future` en `queries.py`; preferencias de canal en
   archivos existentes de `members` o con `channels` sumado al conjunto exacto de
   `test_no_cross_models`; `settings.channels` habilitada (`ENABLED_SECTIONS`, `SECTION_REGISTRY`,
   `SECTION_VIEWS`, `SECTION_DEFAULTS`) con `credentials_present` desde `core.config` y
   `test_settings_no_secrets` en verde; `ALERT_CONTEXT_KEYS` gana las claves del resumen (o un
   `code` con conjunto propio) y `TelegramAlertSink` (`httpx.Client`, timeout 10 s, `build_payload`
   puro, token y `chat_id` de `.env` o `settings` por decisión) se registra en `main.py` y
   `worker/main.py`; los cuatro eventos sin texto libre; `__audited__` + `__audit_subject__` en los
   modelos con socio; cada escritura con cubeta (`admin-write` / `memberships-write` /
   `notifications-write` nueva con `USER_*`, `.env.example` y el conteo del comentario de cubetas) y
   `wa-link` con `members-reveal`; `no_store` a nivel de router; listas con `PageParams` (y `q` o
   motivo); `forgot` con cuenta, token y `BackgroundTasks` + prueba de tiempos (S2-D36 enmendada en
   DECISIONES); `email_sent` en `CreateUserOut` e `IssuedLinkOut`; `Settings` + `.env.example` con
   `EMAIL_PROVIDER`, `SMTP_*`, `BREVO_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
   `NOTIFY_MAX_ATTEMPTS`, `NOTIFY_HTTP_TIMEOUT_S` (secretos `SecretStr`); `uv add aiosmtplib` +
   `check-licenses-api.sh` + `notice.sh`; Mailpit por digest en `compose.dev.yml`; `openapi.json` y
   `types.ts` regenerados; `run-gates.sh` al cerrar el bloque.
6. **Bloque B (seed y job):** `seed-notifications` idempotente y auditado (dos plantillas y cinco
   reglas por `whatsapp_link`), `notify [--generate-only|--send-only]`, `generate_for` con `ON
   CONFLICT DO NOTHING ... RETURNING`, recuperación de 15 días, supresión por renovación (N-35),
   `skipped` con motivo por preferencia o canal deshabilitado, una transacción por aviso en `send`
   con `contact_for_notification` confirmada antes de enviar (S4A-D50), `daily_team_summary` sin
   nombres, `today_count` en el tablero; `FrozenClock` en las pruebas (17, 20, 21, 27 de octubre y 4
   de noviembre).
7. **Bloque C (Rojo):** `uv add reportlab` (y `pypdf` en `dev`) con `check-licenses-api.sh` en verde
   (decisión escrita sobre `pillow` si `pip-licenses` no lo reporta como `MIT-CMU`), `NOTICE`;
   `core/export.py` (`csv_stream`, `escape_formula`) sin importar módulos; `payments/receipt.py`
   con el logo en `payments/assets/` y `test_api_image.sh` comprobando que la imagen lo trae;
   `receipt_pdf` con `refs_for` por lazy G-03, `names_for`, `gym` y `payment_methods`; auditoría
   `download` con `subject_member_id`; `members.service.export` con `MemberListQuery`, lotes de
   500 con `bus.batch` y `purpose="export"`, auditoría `export` antes del stream, cubeta
   `members-reveal`; `payments.service.export` que cuadra con `summary(month)`; rutas `/export` y
   `receipt.pdf` registradas antes de `/{id}`; `members/service.py` bajo 800 (o `members/export.py`
   privado sumado al conjunto exacto); caso de control de `fpdf2` en el script de licencias;
   `perf` de 1.000 socios < 10 s.
8. **Wave 0 (infra OpenBao):** `infra/openbao/config.hcl` (`storage "file"`, listener
   `0.0.0.0:8200` sin TLS en la red interna, `ui = false`, `disable_mlock` documentado),
   `bootstrap.sh` idempotente (init 5/3 solo si no está inicializado, mostrar llaves y token raíz
   una vez y nunca a archivo, `transit` habilitado, cinco `apex-kek-<data_class>` `aes256-gcm96`
   no exportables + `apex-sign-audit` `ed25519`, política `apex-api` con `read` de `transit/keys/
   apex-*` y `update` de `renew-self`, token periódico escrito con 600 y uid 10001 en
   `openbao-token`), `bash -n` y pruebas Bash puras; servicio `openbao` por digest con fecha y
   comando (`test_images_pinned.sh`), sin `ports`; `compose.dev.yml` con modo dev; CI `e2e-stack`
   y `compose-smoke.sh` con `openbao` (modo dev) y el smoke sellar/desellar; `NOTICE` con el bloque
   fijo MPL-2.0 sin modificar (editando `notice.sh`); `docs/operacion/openbao.md` (desellado 3 de
   5, rekey, dos lugares fuera del servidor, `/health`, qué ve el usuario); `.env.example` con
   `OPENBAO_ADDR`, `OPENBAO_TOKEN_PATH`, `OPENBAO_TIMEOUT_S`, `CRYPTO_RECOVERY_POLL_S` y `Settings`
   con sus campos y validadores (`test_env_example` en verde); decisión sobre `apex_owner` (D206) y
   Caddy/TLS (D45, D66) escrita en T-DOC (C1); `infra/backup/run.sh` incluye `openbao-data` o el
   documento de operación dice por qué no.
9. **Waves 5a y 5b (front):** `ENABLED_FEATURES` con `notifications` (`features.test.ts` a 10);
   `features/notifications/{api,schemas,pages/{TodayPage,RulesPage,HistoryPage},components/SkipModal}`
   con `PorAvisarHoy.html`, `Notif_Reglas.html`, `Notif_Historial.html` (claro y oscuro) y
   `// DESIGN-GAP:` en "Regenerar lista"; pestaña `avisos` de la ficha como hija de la feature
   `notifications` con `ChannelPreferences`; pestaña "Canales" en `ConfigPage` (`?tab=canales`);
   `ReceiptButton` y `ExportButton` ×2 con `ConfirmModal` y `useCan`; `shared/lib/download.ts`;
   KPI "Por avisar" real (`FutureKpis` pierde la fila); `ForgotPage` con "Si el correo está
   registrado, te enviamos un enlace" y el `DESIGN-GAP` cerrado; tokens sin colores literales;
   Vitest por página; `tests/e2e/avisos.spec.ts` y su gemelo en `tests/e2e/stack/`; `BRECHAS.md`
   §13 con las filas del sprint; `npm run lint && npx tsc --noEmit && npm test && npm run build`.
10. **Validación y cierre:** smoke con OpenBao (migrar, sellar, 503, desellar, `/health` en cada
    estado, evidencia), `migrate-provider` interrumpido y reanudado en `db_test`, `notify` ×2 sin
    duplicar, los tres E2E de la DoD contra el stack de producción (`infra/compose.yml` solo,
    `WEB_PORT=8180`), `run-gates.sh` final con cobertura ≥ 80 % incluidos `notifications/`,
    `openbao_provider.py`, `worker/jobs/notify.py` y `cli_ops/{migrate_provider,notify}.py`,
    `security-reviewer` sobre los seis puntos de la DoD (token de OpenBao fuera de logs y
    `crypto_ops`, `last_error` sin secretos, Telegram sin datos personales, `wa-link` `no-store`,
    CSV con escape de fórmulas, correo solo con opt-in y consentimiento), `verify-delivery` con los
    dos pilares sobre el stack con OpenBao, ensayo de restauración completa (base + `openbao-data`)
    en una base limpia, y el paso humano: push, PR con CI en verde, merge y `git tag -a v0.2.0`.

## Riesgos residuales (no bloquean)

- `--reload` con polling reinicia el api a mitad de un E2E del proyecto `stack`; no editar `src/`
  durante la corrida.
- Las pruebas de `age` saltadas en Windows (52) siguen corriendo en el contenedor Linux y en CI; las
  de OpenBao real se suman a ese grupo si el servicio no está arriba en el host.
- `bao` no existe en el host: toda operación de OpenBao es `docker compose exec openbao bao ...`;
  el procedimiento de operación debe escribirse así.
- Los triggers `crypto_*` de `0003` siguen en `'O'`; `0015` no los toca (residual anotado desde 4B).
- `GET /health` responde 503 mientras OpenBao esté sellado: cualquier monitor externo que mida solo
  el código HTTP verá el api caído aunque `db` y `migrations` estén bien; `docs/operacion/openbao.md`
  lo explica y `deploy.sh` lo distingue (C3).
- El resumen diario por Telegram sale aunque no haya avisos ("Nadie por avisar"): decidir si se
  omite con cero (US-126 no lo fija).
