# Cuaderno · Sprint 4B

Rama `feat/sprint-04b-continuidad-release`. Plan: `docs/ddd/blueprints/sprint-04b-plan.md` (W0-1, W0-2, W0-3, B0, B1, B2, B3a, B3b, B4, F1 y V1 a V12; enmiendas de `sprint-04b-critica-1.md` y `sprint-04b-critica-2.md`, que mandan). Alias: `DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"`. Las pruebas del api necesitan `TEST_DATABASE_URL=postgresql+asyncpg://apex:apex-test@127.0.0.1:5443/apex_test`; `uv` en `~/.local/bin`; `python` no está en el `PATH` del host. El front escribe en `docs/scratch/sprint-04b-front.md`.

## Línea base (W0-1.1)

- HEAD `483297c` (planificación del sprint sobre `280addd`, cierre del Sprint 4A), árbol limpio, `git worktree list` solo con el principal.
- Stack `apex` arriba: `api`, `db`, `db_test`, `web`, `worker` `healthy`; `alembic current` = `0013_audit_verifications (head)`. Puertos del host por nombre en `.env`: `WEB_PORT`, `API_PORT`, `DB_PORT`, `DB_TEST_PORT`.
- Imágenes de partida: `apex-api:local` `sha256:83a82fc3caff5174c81323e7bed5b6b8b2f29639d4cfac867bebce9498abe87d` (2026-10-29T11:20:58Z) y `apex-web:local` `sha256:6745c50bf90a83164972531333213beed5cac7265de1945b566eacc93f214fdb` (2026-10-29T11:21:19Z).
- Estado de `apex-db-1` (solo lectura): 265 socios, `max(seq)` de `audit.audit_log` 5612, `crypto.crypto_keys` 8 filas con `max(version)` 1, los 8 triggers no internos en `tgenabled = 'O'`, un solo rol `apex%` (`apex`).
- Gates baratos sobre HEAD: `ruff check .` limpio, `ruff format --check .` 510 archivos sin cambios, `mypy src` 119 archivos sin errores; `test_check_key_files`, `test_images_pinned`, `test_nginx_conf`, `test_compose_config` con 0 fallas; `scripts/workflow/tests/run.sh` 5 de 5. (`tsc` del front no se repite: W0-1 no toca `web/`.) La suite completa no se repite: V9 del Sprint 4A sobre el mismo código (api 4.995 ok, 3 saltadas, 97 %; web 3.125 ok).
- Alpine y `postgres:16-alpine` (2026-10-29): digest del índice `sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab`, Alpine 3.24.3, `bash 5.3.9`. `apk policy` ofrece: `age 1.3.2-r1`, `minisign 0.12-r2`, `rclone 1.74.1-r3`, `supercronic 0.2.49-r1` (el plan citaba las de Alpine 3.23; se fijan las nuevas, ver DECISIONES). La imagen local `postgres:16-alpine` sin digest de otro proyecto no se usa.
- Puertos 8280 y 8380 libres (`netstat -ano` vacío); ninguna red `172.31.x`; `docker stats --no-stream` de línea base: `apex-db_test-1` 1,17 GiB, `apex-api-1` 116 MiB, `apex-worker-1` 78 MiB, `apex-db-1` 31 MiB, `apex-web-1` 7 MiB, y otros proyectos arriba (`dian-*`, `vi-*`, `possi-*`, `ventasonline-*`, `motor-flujos-*`); memoria total de Docker 11,68 GiB.
- `git check-ignore -v docs/scratch/ensayo/x`: vacío en HEAD (la regla llega en W0-1.6; al sellar da `.gitignore:57:docs/scratch/ensayo/`); `git check-ignore -v docs/scratch/sprint-04b-antes-0014.dump` → `.gitignore:46:*.dump`; `git ls-files docs/scratch/sprint-04b.md`: vacío hasta este checkpoint (el cuaderno se crea ahora y entra en el sello).

## S4B-W0-1 · Imagen y servicio `backup`, `age`, `.env.ops.example`, `wave0-gate.sh`, T-DOC y decisiones

- **Rojo (W0-1.2)**, conteos contra HEAD:
  - `infra/backup/tests/run.sh`: 0 de 3 archivos (`lib.sh`, `manifest.schema.json`, `run.sh`, `entrypoint.sh` y `healthcheck.sh` no existían).
  - `scripts/ci/test_compose_config.sh`: 19 fallas (servicio `backup` en producción, healthcheck, volúmenes, `compose.verify.yml`, `.env.ops.example`, `git` ignora/versiona).
  - `test_images_pinned.sh`: 1 falla (no existe `infra/backup/Dockerfile`). `test_check_key_files.sh`: 6 fallas (`.env.ops.example`, `backup-sign.key`, `backup-verify-identity.txt`, `age-identity.txt`, `rclone.conf`, `*.age`).
  - `pytest tests/core/test_env_example.py tests/core/test_config.py`: 7 fallan, 89 pasan (6 de `test_env_example`, porque `.env.ops.example` no existe, y 1 de `test_config` por `NON_API_ENV_VARS`).
  - `scripts/workflow/tests/test_wave0_gate.sh`: 1 falla (`wave0-gate.sh` no existe). `test_api_image.sh` se escribió contra la imagen: con la `apex-api:local` de HEAD faltaban `age`, `/data/backups`, `/data/imports` y la etiqueta (4 fallas esperadas; la corrida real fue contra la imagen nueva).
- **Verde (W0-1.3 a W0-1.7):**
  - `uv add openpyxl defusedxml` (`openpyxl 3.1.5`, `defusedxml 0.7.1`, `et-xmlfile 2.0.0`); `check-licenses-api.sh` y `test_licenses.sh` verdes; `notice.sh` regenera `NOTICE` (110 líneas) con el bloque de binarios de contenedor.
  - `api/Dockerfile`: `age`, `/data/backups` y `/data/imports` con dueño `apex`, `LABEL org.opencontainers.image.revision`.
  - `infra/backup/`: `Dockerfile`, `lib.sh`, `run.sh`, `entrypoint.sh`, `healthcheck.sh`, `manifest.schema.json`, `.dockerignore` y `tests/` (arnés propio, `validate_manifest.py`). `infra/compose.yml` (servicio `backup`), `infra/compose.verify.yml`, `.env.ops.example`, `NON_API_ENV_VARS` (+20 nombres), `.gitignore`, `check-key-files.sh`, `compose-smoke.sh` (bloque `backup`), `ci.yml` (`age` fijado `1.1.1-1ubuntu0.24.04.3`, build de `apex-backup:ci`, `check-image-secrets`, `test_infra_scripts`), `run-gates.sh` (+`test_infra_scripts`), `wave0-gate.sh` y su prueba.
  - Resultados: `infra/backup/tests/run.sh` 3 de 3 (lib 48, manifest 13, static 40; dentro de `apex-backup:local` el de manifiesto se salta por falta de Python y corre en el host y en la CI); `test_compose_config` 0 fallas; `test_images_pinned` 0; `test_check_key_files` 0; `test_wave0_gate` 23 ok; `test_run_gates` 22 ok; `pytest test_env_example + test_config` 96 ok.
- **Docker (W0-1.10):**
  - Imágenes: `apex-backup:local` `sha256:898011430a8565b57d0981275c0acd27efde0ce4cd3ac4fd0b9d842e6f3e30f6` (índice de buildx; reconstruida tras la revisión de seguridad) y `apex-api:local` `sha256:da6d45f986021af520b80b801451ef84dfdbcabcf93710b53b51a474d0e1f4e6`. `$DC up -d --no-build` recreó `db` (cambió su `env_file`; el volumen persiste), `api`, `worker` y arrancó `backup` (`healthy`, log `ERROR backup deshabilitado: falta BACKUP_AGE_RECIPIENT`). `alembic current` sigue en `0013`; 265 socios y `max(seq)` 5612 intactos.
  - M2: se añadieron al `.env` de este equipo (no versionado) las 20 claves de `.env.ops.example` con sus valores por defecto, sin secretos (`APEX_*_DB_PASSWORD=cambiar-esto`): `BACKUP_KEEP_DAYS`, `BACKUP_CRON`, `BACKUP_AGE_RECIPIENT`, `BACKUP_AGE_VERIFY_RECIPIENT`, `BACKUP_RCLONE_REMOTE`, `RCLONE_CONFIG_APEX_{TYPE,PROVIDER,ENDPOINT,ACCESS_KEY_ID,SECRET_ACCESS_KEY}`, `BACKUP_SIGN_PUBKEY`, `BACKUP_SIGN_KEY_FILE`, `BACKUP_VERIFY_IDENTITY_FILE`, `DEPLOY_HEALTH_TIMEOUT`, `APEX_{API,WORKER,BACKUP}_DB_PASSWORD`, `APEX_SUBNET`, `APEX_IP_RANGE`, `APEX_WEB_IP`. `cmp` contra `.env.example` no aplica: se amplía a propósito. Los destinatarios `age` quedan vacíos.
  - `test_api_image.sh apex-api:local` 0 fallas (con `MSYS_NO_PATHCONV=1` en la prueba de `stat`); `check-image-secrets.sh` limpio en api y backup (hubo que excluir los binarios de rclone, que llevan la cabecera PEM como constante).
  - Bind de `${BACKUP_SIGN_KEY_FILE:-/dev/null}` en Docker Desktop: el contenedor arranca, `/run/apex/backup/sign.key` es un dispositivo de tamaño 0 y `run.sh` lo trata como ausente: **se mantiene `/dev/null`, no hace falta `compose.sign.yml`.**
  - Corrida real sobre `apex-db-1` (solo lectura) con claves age y minisign de prueba generadas en el scratchpad (borradas): primera corrida `verify=skipped` y `upload=skipped`, `latest.json` y `.minisig` válidos (`minisign -V` ok, esquema ok), segunda con `compose.verify.yml` `verify=ok`; volcado de 1,5 MB cifrado que `pg_restore --list` lee; uploads 1,8 KB; 1 s por corrida; `pre-deploy` y `pre-restore` escriben `<prefijo>-<ts>.json` sin tocar `latest.json`; con el remoto `local` de rclone `upload=ok`. El volumen `backups` se vació al terminar.
  - Smoke de Compose (copia del scratchpad: buildx previo y `--no-build`), `SMOKE_KEEP=1`, **verde en 72 s** con el bloque `backup` (inerte y visible, corrida real, firma, cabeceras age, descifrado de db y uploads) y todo lo anterior (worker, seed, web, headers 0 fallas).
- **Revisión de seguridad (`security-reviewer`, W0-1.11.1):** 0 CRITICAL, 0 HIGH, 4 MEDIUM, 7 LOW. Aplicados o con dueño en S4B-D104 (DECISIONES): entorno por herramienta sin `env` en el argv, `10#` en `KEEP_DAYS`, manifiesto y firma al remoto, `verify=failed` no reemplaza `latest.json`, `-f` en las llaves, nombre del juego validado, limpieza del `.age` huérfano, `--immutable`, validación del destinatario en el entrypoint. Diferido con dueño B3a: manifiesto por juego y autoverificación de la firma.
- **T-DOC (W0-1.8):** `DECISIONES.md` (sección "Sprint 4B" íntegra del plan, enmiendas, constancia de S4A-D60 y S4A-D61 con dueños EP-09 y v0.3, S4B-D104), `CLAUDE.md`, `RUNBOOK.md` (índice, §6 esqueleto de `0014`, §7 `apex-backup`, regla S4B-D98 con la antigua tachada, §12 nueva), `BRECHAS.md` §12, `scripts/workflow/README.md`, nota del blueprint; desgloses de US-030, 111, 112, 114 a 119 y `SPRINT-04B.md`.
- **Desviaciones del plan:** versiones de Alpine nuevas; época del ejemplo de `backup_name` corregida (`1792566005`); el aserto "compose.yml sin POSTGRES_PASSWORD" pasó a "sin valor literal"; `check-image-secrets.sh` y `test_api_image.sh` ajustados; `ci.yml` fija `age` con la versión de noble-updates de Launchpad (`packages.ubuntu.com` no respondió); `git check-ignore -v .env.ops.example` imprime la regla de negación `!.env.ops.example` y sale con 1, equivalente al "vacío" del plan sin `-v`.

### Evidencia de S4B-W0-1

- Gates que sellaron: `slice-gate.sh core/config tests/core/test_config.py tests/core/test_env_example.py` (ruff, format y mypy limpios; 490 ok con `tests/architecture`) y `wave0-gate.sh W0-1 tests/core/test_env_example.py tests/core/test_config.py` (`bash -n`, `test_check_key_files`, `test_images_pinned`, `test_nginx_conf`, `test_compose_config`, `test_infra_scripts` 48+13+40, `test_api_image` sobre `apex-api:local`, cuatro `docker compose config --quiet`, y el sello por `slice-gate.sh architecture`: 490 ok). Los dos con `PYTEST_ADDOPTS="-m 'not perf'"`.
- Checkpoint `f35ff39` (`chore(checkpoint): S4B-W0-1 imagen y servicio backup, age, .env.ops.example, wave0-gate y decisiones del sprint`), con el trailer `Co-Authored-By: Claude Fable 5.1`. `git check-ignore -q .env.ops.example` sale con 1 (no ignorado) y estaba en `git status` como no rastreado antes del sello. Los `.sh` nuevos entraron con modo 100755.
- Agente de documentación: 9 desgloses con bloque "Corregido en S4B-W0-1" (54 viñetas) y `SPRINT-04B.md` reescrito; `verificar.mjs` (en `08_implementation_breakdown/`) da solo el error previo de US-008. Dos puntos a revisar por el orquestador: la redacción de varias viñetas combina palabras clave del plan, y el nombre de la prueba de `rotate-key` usa `tests/cli/test_rotate_key_cli.py` (viñeta de W0-1.8) frente a `test_cli_rotate_key.py` de S4B-D2.
- Estado final del stack: `apex` con `api`, `db`, `db_test`, `web`, `worker` y `backup` `healthy`; `alembic current` `0013`; volumen `backups` vacío.

## S4B-W0-2 · Migración `0014_audit_log_triggers_always` y re-armado de triggers

### Evidencia de S4B-W0-1

- Checkpoint `f35ff39` y commit de evidencia `b33e38b` (ver bloque anterior).

- **W0-2.1 (P-MIG 1 y 2):** volcado `docs/scratch/sprint-04b-antes-0014.dump` de `apex-db-1` con `pg_dump -Fc` desde Bash (`-T`): 1.515.249 bytes; `chmod 600` sin efecto en NTFS (`-rw-r--r--`); `git check-ignore -v` → `.gitignore:47:*.dump`. `$DC stop api` hecho antes de crear ningún archivo en `migrations/versions/` (último: `0013`); el worker y `backup` siguen `healthy`. El api queda parado hasta W0-2.7.
- **Rojo (W0-2.2):**
  - `tests/factories/triggers.py` nuevo (`AUDIT_LOG_TRIGGERS`, `VERIFICATIONS_TRIGGERS`, `CRYPTO_TRIGGERS`, `ALWAYS_TRIGGERS` por tabla con los diez, `disable_user_sql`, `rearm_always_sql` = un bloque `DO` por tabla).
  - Las 4 sentencias `ENABLE TRIGGER USER` de `tests/conftest.py` (y los `DISABLE`) y los 14 archivos restantes de la lista de S4B-D6 usan el ayudante (15 archivos en total); `tests/factories/audit_chain.py` deriva `APAGAR`/`ENCENDER` del ayudante. `test_no_trigger_tampering.py` intacto.
  - `test_0014_audit_log_triggers_always.py` (nuevo): 44 pruebas, todas en rojo hoy (1 FAILED + 43 ERROR del fixture `base`, motivo: "no existe la revisión 0014_audit_log_triggers_always"); 0 verdes.
  - `test_0013`: "es head" pasó a "está en la cadena hasta head" (verde hoy y con `0014`).
  - `test_triggers_siempre_activos.py`: +9 casos (`audit_log` 2 en `A`, `crypto.*` 6 en `A`, TRUNCATE bajo `replica` ×5 tablas con rollback, ayudante, y `test_tras_la_limpieza_de_sesion_los_diez_triggers_siguen_en_always`). En rojo hoy: 5 (`seis_triggers_de_crypto`, 3 TRUNCATE de `crypto.*`, el de los diez). Los de `audit_log`/`verifications` pasan hoy porque las limpiezas con el ayudante ya dejan `audit_log` en `A` (efecto buscado, válido antes y después de `0014`).
  - Corrida `pytest tests/migrations tests/core/test_migrations.py tests/architecture -m "not perf"`: 642 ok, 6 FAILED, 43 ERROR (rojo 49 = 44 de `test_0014` + 5 de `test_triggers_siempre_activos`).
  - Limpiezas: `tests/audit tests/core/test_audit_log_db.py tests/crypto`: 533 ok, 2 saltadas (NTFS sin modo POSIX), 0 fallas.
  - `ruff check`, `ruff format --check` y `mypy src` limpios.

### S4B-W0-2 · Verde (W0-2.3 a W0-2.5)

- **Migración** `api/migrations/versions/0014_audit_log_triggers_always.py` (`down_revision = "0013_audit_verifications"`): `CREATE OR REPLACE FUNCTION audit.forbid_mutation()` con `TG_TABLE_SCHEMA`/`TG_TABLE_NAME`, `SECURITY INVOKER`, `search_path = pg_catalog`, `P0001`; ocho `ENABLE ALWAYS TRIGGER` literales; `downgrade` simétrico con el cuerpo de `0002`. `uv run alembic heads` = `0014_audit_log_triggers_always (head)`. Api parado; Alembic solo contra `db_test` por pytest.
- **Correcciones a las pruebas del Rojo (no a la función):** (1) `crypto.*` rechaza con `ERRCODE check_violation` (`23514`), no `P0001` (`Tabla.sqlstate`, `CHECK_VIOLATION`); (2) `data_class` de la fila de `crypto_keys` pasó de `prueba.cero14` a `prueba.cero_cat` (el CHECK no admite dígitos). Los mensajes de `crypto_keys`/`crypto_jobs` coinciden con `0003`.
- **Pruebas de migraciones** (`tests/core/test_migrations.py`, `test_0014_*`, `test_0013_*`, `test_triggers_siempre_activos.py`): 88 passed.
- **Docs:** RUNBOOK §6 (`0014` completa, con la nota de que todo `downgrade` deja los triggers en `O` y la función antigua), DECISIONES (S4A-D98 y V6 cerrados; S4B-D4/D5/D6 en forma final), SPRINT-04B "Migraciones".
- **W0-2.5 (suite en dos mitades, sin `--cov`):** mitad 1 (`architecture core crypto auth settings migrations cli worker`): 2442 passed, 3 skipped (NTFS sin modo POSIX), 1 deselected; mitad 2 (`members plans memberships payments audit dashboard integration`): 2607 passed, 22 deselected. 0 fallas. `ruff check`, `ruff format --check` y `mypy src` limpios.

### S4B-W0-2 · Revisiones

- `database-reviewer`: APROBAR, sin bloqueantes. (1) BAJA: RUNBOOK §6 y DECISIONES (junto a S4B-D4) dicen ahora que `0014` se aplica con el api y el worker parados (`ShareRowExclusiveLock` sobre `audit_log` y `crypto.*` hasta el commit; `env.py` comparte una transacción para todas las pendientes) y que `pg_restore --disable-triggers` (modo `replica`) ya no omite estas tablas. (2) INFO: nada que cambiar.

### Evidencia de S4B-W0-2

- Checkpoint `f508b73`. Gate `wave0-gate.sh W0-2` sellado: 482 passed (4 archivos de migraciones + `tests/architecture`); ruff/format/mypy limpios.
- W0-2.7 en `apex-db-1`: `$DC stop worker` antes de arrancar el api (decisión del revisor); `$DC start api` aplicó `0014` ("Running upgrade 0013_audit_verifications -> 0014_audit_log_triggers_always"), `alembic current` = `0014_audit_log_triggers_always (head)`. Ciclo `downgrade -1` (ocho en `O`, `verifications` en `A`) → `upgrade head` → `current` 0014.
- `tgenabled`: los diez inmutables en `A` (`audit_log` 2, `verifications` 2, `crypto_ops` 2, `crypto_keys` 2, `crypto_jobs` 2) y los siete de `memberships`/`payments` también en `A` (17 filas).
- Bajo `replica` y dentro de `BEGIN; ... ROLLBACK;`: "audit.audit_log es append-only", "audit.verifications es append-only", "crypto.crypto_ops es append-only".
- Stack: api `healthy` en `0014`, worker `healthy` (RestartCount 0), `/health` y `/api/v1/health` 200. Evidencia también en el scratchpad (`w02-evidencia.md`).

- Commits de S4B-W0-2: checkpoint `f508b73` y evidencia `79b31a8` (`docs(sprint-04b): evidencia de S4B-W0-2`).

## S4B-W0-3 · Roles de base, migraciones fuera del api, entorno por servicio, endurecimiento y MEDIUM-1/2

### S4B-W0-3 · Rojo

**W0-3.1 · Inventario para `grants.sql`** (greps al scratchpad; psql de solo lectura sobre `apex-db-1`, `alembic_version` = `0014_audit_log_triggers_always`)
- Catálogo real: 9 esquemas de aplicación (`audit auth crypto members memberships payments plans settings worker`) más `public`; 16 tablas: `audit.{audit_log,verifications}`, `auth.{one_time_tokens,refresh_tokens,users}`, `crypto.{crypto_jobs,crypto_keys,crypto_ops}`, `members.members`, `memberships.{membership_freezes,memberships}`, `payments.payments`, `plans.plans`, `settings.settings_sections`, `worker.job_runs`, `public.alembic_version`. Cero secuencias (`audit_log.seq` lo asigna el código bajo candado), cero identidades; `public` solo trae las funciones de `btree_gist` (usadas por los dos `EXCLUDE USING gist` de `memberships`: la prueba inserta una membresía con `apex_api` para probar que el `REVOKE` no las rompe).
- Triggers (17, todos en `A`): `forbid_mutation` en audit y payments, `crypto.*` con guardas propias, `memberships.guard_identity` (identidad y estado `cancelled`), `forbid_delete`, `forbid_freeze_mutation`. Funciones de aplicación sin `SECURITY DEFINER`.
- Greps (92 líneas de `delete(|update(|with_for_update|begin_nested|FOR SHARE/UPDATE`, 23 de `text(` en `core`): `DELETE` real solo en `auth/tokens.py:91` (`delete(RefreshToken)`, purga de sesiones vencidas); `UPDATE` explícito en `auth/tokens.py` (refresh, usuarios: contadores y `tokens_valid_after`) y `core/jobs.py` (`worker.job_runs`, `on_conflict_do_update` y `update(JobRun)`); el resto de escrituras es ORM por `flush`. `FOR UPDATE`: `auth` (usuario y token), `memberships.sell.lock_membership`, `payments` (pago y membresía), `plans`, `settings`; `FOR SHARE`: plan (`plans.service.get`) y `crypto_keys` (`core/crypto/types.py:152`). `lock_member` es `pg_advisory_xact_lock` (no `FOR UPDATE` de `members`): el `UPDATE (updated_at)` del worker en `members.members` es el plan, y la prueba lo ejercita igual.
- Matriz resultante (tabla -> api / worker; `backup` = `SELECT` por `pg_read_all_data`, nada más): `audit_log` S,I / S,I; `verifications` S,I / -; `one_time_tokens` S,I,U / -; `refresh_tokens` S,I,U,D / -; `users` S,I,U / S; `crypto_jobs` S / S; `crypto_keys` S,I,U(updated_at) / -; `crypto_ops` S,I / S,I; `members` S,I,U / S,U(updated_at); `membership_freezes` S,I / S; `memberships` S,I,U(end_date, classes_remaining, status, cancel_reason, cancelled_by, cancelled_at, updated_at) / S,U(status, updated_at); `payments` S,I,U(voided, void_reason, voided_by, voided_at, updated_at) / -; `plans` S,I,U / S; `settings_sections` S,I,U / S; `job_runs` S / S,I,U; `alembic_version` S / -. Nunca `TRUNCATE`, `TRIGGER`, `REFERENCES`; `DELETE` solo `apex_api` en `auth.refresh_tokens`. La matriz vive en `tests/migrations/test_db_grants.py::PRIVILEGIOS` y el encabezado de `grants.sql` debe listar `-- clasificada: esquema.tabla` por tabla.

**W0-3.2 · Rojo de infraestructura** (todo con `bash -n` limpio)
- `scripts/ci/test_compose_config.sh`: el render usa `--env-file .env.example --env-file .env.ops.example` más un archivo temporal de contraseñas centinela distintas por rol (fugas por nombre y por valor; `environment` leído sin resolver los `env_file`, porque el `.env` de esta máquina es la suma de los dos ejemplos). Antes (HEAD): 82 ok / 0 fallas. Ahora: 118 ok / 50 fallas; los 50 son todos de lo nuevo (migrate, dbsetup, db sin env_file, api/worker/web/backup/tools por servicio, recorte de `.env.example`, red parametrizada, perfil `prod-init`, RUNBOOK `--no-deps`, `!override` en desarrollo, E2E con la cadena completa). Pasan hoy por ser invariantes ya ciertos: backup en desarrollo sin `dbsetup` y con `${POSTGRES_USER}`, `config --quiet`, `TRUSTED_PROXIES`. La aserción vieja "worker sin volúmenes" se reemplazó (S4B-D11: solo `backups:ro`).
- `scripts/ci/test_nginx_conf.sh`: 75 ok / 11 fallas (zona `apex_health` 30r/m, `location = /api/v1/health` con `burst=10 nodelay`, `error_page 429 = @rate_limited`, `proxy-api.conf`, `client_max_body_size 64k`, una sola declaración de la zona en `snippets/`, y la ráfaga funcional de 45 GET: hoy 45 pasan, 0 con 429).
- `scripts/ci/test_db_roles.sh` (nuevo): contra `apex-db-1` (solo intentos de login y `BEGIN; ... ROLLBACK;`): 44 fallas, 0 ok (rol inexistente). Verifiqué el mecanismo `PGPASSWORD=... docker compose exec -T -e PGPASSWORD` con un `select 'ok'` del propietario.
- `test_images_pinned.sh` (0 fallas) y `test_check_key_files.sh` (0 fallas) sin cambios: la imagen de `dbsetup` entra bajo la misma regla de digest y comentario con fecha.

**W0-3.3 · Rojo del api** (`ruff check`, `ruff format` y `mypy src` limpios; no hizo falta ningún stub en `src`)
- `tests/migrations/conftest.py` (fixture `apex_roles`, S4B-D101), `tests/migrations/test_db_grants.py` (131 casos con `test_db_apply.py`), `tests/migrations/test_db_apply.py` (entrypoint de `dbsetup` sobre `db_test` por `docker cp`/`exec`), `tests/architecture/test_db_roles_confined.py` (5, verdes: nada en `src` toca los roles, ningún `docker exec` apunta a `apex-db-1`, la fixture solo borra `apex_roles` y arranca con `revoke.sql`).
- Verde desechable: con un `roles.sql`/`grants.sql`/`revoke.sql`/`apply.sh` mínimos generados desde la matriz, los 131 casos pasaron (sha256 de los desechables en el scratchpad); borrados, `infra/db/` no existe y `db_test` quedó sin roles ni la base `apex_roles`. Hallazgo para el Verde: con `NOINHERIT` en `apex_backup`, `GRANT pg_read_all_data TO apex_backup` no sirve; hace falta `WITH INHERIT TRUE` (PG16), y la prueba lo exige.
- Conteos rojo/verde: `test_db_grants.py` 3 fallas + 120 errores de fixture ("no existe infra/db/..."); `test_db_apply.py` 1 falla + 7 errores; `test_oplog_rollback_failure.py` 3 rojas (el `IntegrityError` del rollback enmascara el error de negocio) / 1 verde de control; `test_errors_busy.py` 2 rojas (`25P03`) / 8 verdes (incluidos 57P01/2/3 en 500); `test_startup_failure.py` 6 rojas (`MIGRATE_ON_STARTUP` desconocida) / 2 verdes; `test_env_example.py` 5 rojas / 17; `test_config.py` 6 rojas / 81; `test_db_timeouts.py` 1 roja (`BUSY_SQLSTATES` con `25P03`) / 24; `test_health.py` 5 verdes (+1 guarda de `APP_VERSION`); `tests/architecture` 399 verdes.
- Reparaciones de pruebas viejas por el recorte E7: `test_config.py::test_non_api_env_vars_contiene_...` (excluye los campos de `Settings`; `DATABASE_URL` no puede ser variable ajena), `test_env_example.py` (`test_toda_variable_de_settings...`, `test_sin_secretos_reales` y `..._claves_de_operacion_...` miran también el ejemplo de operación), `test_db_timeouts.py::test_busy_sqlstates`.
- Desviación declarada: la caché y el `Lock` de `/health`, los estados colapsados y `migrations ok|mismatch|unknown` NO se probaron aquí; el plan los asigna a B2.3 y B4 (S4B-D60: "W0-3 (Nginx), B2 (caché, backup), B4 (migrations)") y exigirían `core/health.py` de B2. En W0-3 solo entra la zona de Nginx y la guarda `/health.version == APP_VERSION`.

### S4B-W0-3 · Verde (W0-3.4 a W0-3.9; sin ensayo, sin P-ROL, sin checkpoint)

**W0-3.4 · `infra/db/`** (pendiente de `database-reviewer` antes del sello): `roles.sql` (`\getenv`, `\gexec`, `format('%L')`, `SET log_min_error_statement = panic` y `log_statement = 'none'` al inicio, atributos `NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS NOREPLICATION LOGIN`, `CONNECTION LIMIT` 20/5/2, `ALTER ROLE ... SET` de los dos tiempos de espera con los valores de `Settings`), `grants.sql` (una transacción; `REVOKE ... FROM PUBLIC` de base, `public` y objetos; `GRANT CONNECT`/`USAGE`; matriz por tabla y columna; `pg_read_all_data` con `WITH INHERIT TRUE`; lista `-- clasificada:` de 16 tablas y bloque final `RAISE EXCEPTION 'tabla sin clasificar: %'`), `revoke.sql` (`DROP OWNED BY` + `DROP ROLE IF EXISTS`, idempotente) y `apply.sh` (`/bin/sh`, `set -eu`: dash no tiene `pipefail`; valida vacío, `cambiar-esto`, < 24 y repetidas sin imprimir valores). `test_db_grants.py` + `test_db_apply.py` sobre `apex_roles`: **131 verdes** (Rojo: 3 fallas + 120 errores de fixture + 1 + 7).
- Hallazgo cerrado: el `SELECT ... FOR SHARE` de `crypto_keys` con `apex_api` funciona **con** `UPDATE (updated_at)` (la prueba existe); el `GRANT` no sobra.
- `test_db_roles.sh` contra una base `apex_roles` de `db_test` migrada con `DATABASE_URL` en el entorno y con `apply.sh` copiado a `/opt/db` (shim de `DC` en el scratchpad que traduce `exec -T -e PGPASSWORD db` a `docker exec` sobre `apex-db_test-1`): **44 ok, 0 fallas**; después `revoke.sql`, `DROP DATABASE apex_roles` y `/opt/db` borrado: 0 roles `apex_%` en `db_test`. Nada tocó `apex-db-1`.

**W0-3.5 · Compose, Nginx, `.env`, red.** `infra/compose.yml` (migrate, dbsetup, entorno por servicio, red parametrizada, endurecimiento, `GIT_SHA`), `infra/compose.dev.yml` (propietario, `MIGRATE_ON_STARTUP=true`, `depends_on: !override`, perfil `prod-init`, `backup` con el propietario), `infra/nginx/default.conf` + `snippets/health-zone.conf`, `.env.example` (sin POSTGRES_/DATABASE_URL/puertos; `MIGRATE_ON_STARTUP=true`; cabecera nueva), `.env.ops.example` (+ POSTGRES_*, DATABASE_URL, TEST_DATABASE_URL, cuatro puertos), `web/Dockerfile` (`ARG GIT_SHA` y etiqueta), `infra/README.md`. `test_compose_config.sh`: **0 fallas** (Rojo 118 ok / 50 fallas; la regex de secretos en línea se restauró, ver DECISIONES); `test_nginx_conf.sh`: **0 fallas** (Rojo 75 ok / 11 fallas; incluye 45 GET reales: pasan las ráfagas y el resto 429 con envelope).

**W0-3.6 · api.** `core/config.py` (`MIGRATE_ON_STARTUP: bool = True`), `main.py` (`create_app(run_migrations_on_startup: bool | None = None)`, `_should_migrate`, `_make_lifespan`, `run_migrations` etiqueta la excepción con `apex_revision` y el `logger.exception` lleva `extra={"revision": ...}`), `migrations/env.py` (URL de `DATABASE_URL` del entorno antes de `get_settings()`; anota `ultima_revision`), `core/db.py` (`25P03`), `core/crypto/oplog.py` (blindaje de `_after_soft_rollback`), `cli.py` (`export_settings` con `MIGRATE_ON_STARTUP`). Prueba nueva: `tests/core/test_migrations.py::test_alembic_con_solo_database_url_en_el_entorno`. Un tope de 50 líneas de `create_app` obligó a extraer `_should_migrate` y `_make_lifespan` (`test_file_and_function_size`).

**W0-3.7 · CI y smoke.** `ci.yml` (job `api`: contenedor de la base de prueba; `images`: `.env.ops`; `e2e-stack`: `.env.ops` con contraseñas aleatorias enmascaradas, `DC` con dos `--env-file`, espera de `migrate` y `dbsetup`, `test_db_roles.sh` antes de los E2E), `compose-smoke.sh` (dos `--env-file`, `migrate` y `dbsetup` ausentes sin perfil), `wave0-gate.sh` (dos `--env-file` y combinación `prod-init`). `bash -n` de todo limpio; YAML válido.

**W0-3.8 · Docs.** RUNBOOK §12 (sección nueva de roles, `.env`/`.env.ops`, `migrate`, `run --rm --no-deps dbsetup`, rollback con `revoke.sql`, ensayo), §9 (`25P03`), §1 (N-6 y N-7 con comando y umbral), §7 ya traía la regla S4B-D98 con la antigua tachada (W0-1); `CLAUDE.md`, `README.md`, `infra/README.md`, `DECISIONES.md` (bloque W0-3), `SPRINT-04B.md`.

**W0-3.9 · Gates** (`PYTEST_ADDOPTS="-m 'not perf'"`, `ls` previo de cada archivo):
- `slice-gate.sh core/config tests/core/test_config.py tests/core/test_env_example.py`: verde, 508 passed (tras las revisiones: 512).
- `slice-gate.sh core/db tests/core/test_db_timeouts.py tests/core/test_errors_busy.py`: verde, 434 passed (tras las revisiones: 437).
- `slice-gate.sh main tests/core/test_startup_failure.py tests/core/test_health.py tests/core/test_migrations.py`: verde, 416 passed (tras las revisiones: 417).
- `slice-gate.sh crypto tests/crypto/test_oplog_rollback_failure.py`: verde, 403 passed (tras las revisiones: 405).
- `slice-gate.sh architecture tests/architecture/test_db_roles_confined.py tests/migrations/test_db_grants.py tests/migrations/test_db_apply.py`: verde, 530 passed (399 de arquitectura + 131 de roles); tras las revisiones: 539.
- `test_compose_config.sh` 0 fallas, `test_nginx_conf.sh` 0 fallas, `test_images_pinned.sh` 0 fallas, `test_check_key_files.sh` 0 fallas, `scripts/workflow/tests/run.sh` 6 de 6 (23 ok en `test_wave0_gate`), `test_db_roles.sh` 44 ok contra `db_test`.
- `ruff check`, `ruff format --check`, `mypy src` limpios.

**Dudas del Rojo resueltas:** (1) `WITH INHERIT TRUE`; (2) `env.py` toma `DATABASE_URL` del entorno + prueba en `test_migrations.py`; (3) zona en `snippets/health-zone.conf`, se conserva `client_max_body_size 64k` (la prueba lo exige y evita el tope de 5 MB del server); (4) `BACKUP_DIR`/`BACKUP_AGE_VERIFY_IDENTITY_PATH` quedan para B2 (el worker ya recibe `BACKUP_DIR` por `environment`); (5) `GIT_SHA` solo por `build.args` y `APP_VERSION`; (6)-(7) aceptadas; (8) `wave0-gate.sh`, `ci.yml` y `compose-smoke.sh` con dos `--env-file`; el job `api` descubre el contenedor del servicio postgres para `test_db_grants.py` (`docker exec`, sin cliente en el runner); (9) `run --rm --no-deps dbsetup` en RUNBOOK §12; (10) caché y `Lock` de `/health` a B2 (precisión de S4B-D60 en DECISIONES).

**Pendiente para el cierre:** `database-reviewer` sobre `infra/db/` y `security-reviewer` de W0-3; reconstrucción de `apex-api:local` y `apex-web:local` (S4B-D98) y ensayo `apex-ensayo` (W0-3.10; ahí se prueba que el api y el worker de dev arrancan con `read_only` y que Nginx arranca con raíz de solo lectura); P-ROL sobre `apex-db-1` (W0-3.11); `wave0-gate.sh W0-3 ...` que sella; checkpoint y evidencia.

### S4B-W0-3 · Revisiones

`database-reviewer`: APROBAR CON CAMBIOS (1 MEDIA, 5 BAJAS). `security-reviewer`: 0 CRITICAL, 0 HIGH, 3 MEDIUM, 4 LOW. Todo corregido con prueba; las constancias no llevan código.

1. **MEDIA (DB-1)** `grants.sql`: el fallo cerrado recorre todo esquema que no sea del sistema y los `relkind` r, p, v, m, S y f, con excepción de objetos de extensión (`pg_depend` `deptype = 'e'`). Pruebas: tabla en un esquema nuevo, vista en `members` y secuencia en `public` hacen fallar `grants.sql` (y se reaplica limpio); los objetos de `btree_gist` no lo hacen.
2. **MEDIA (DB-2) y LOW (L1)** `apply.sh`: alfabeto `[A-Za-z0-9._~-]` (las contraseñas van en una URL); `.env.ops.example`, RUNBOOK §12 y `ci.yml` usan `openssl rand -hex 24`. Pruebas en `test_db_apply.py` (`@`, `/`, espacio y comilla se rechazan sin imprimir el valor).
3. **MEDIUM (M1, H-1)** prueba viva de `/proc/1/environ`: `scripts/ci/test_env_isolation.sh` (api, worker y backup; por nombre y por valor; solo imprime nombres). Corre en `e2e-stack` antes de `test_db_roles.sh` y la ejecuta el ensayo W0-3.10. `prod-smoke.sh` aún no existe: lo incorpora B4.
4. **MEDIUM (M2)** `Settings` con `ENV=production` falla (`ConfigError`, solo nombres) si el entorno trae `POSTGRES_PASSWORD`, `APEX_*_DB_PASSWORD`, `RCLONE_*`, `BACKUP_SIGN_*` o `BACKUP_VERIFY_*`; desarrollo los ignora. Pruebas en `test_config.py`. El chequeo de `deploy.sh` queda para B4.
5. **MEDIUM (M3)** `MIGRATE_ON_STARTUP` por defecto `False`; `compose.dev.yml` y la fixture `settings_prueba` lo ponen en `true`; `.env.example` trae `false` con el comentario. Prueba: sin la variable, `create_app()` no migra.
6. **BAJA (DB-3)** `apex_worker` pierde `UPDATE (updated_at)` sobre `members.members` (y con él `FOR UPDATE` en esa tabla): `grants.sql`, `PRIVILEGIOS`, `test_db_roles.sh` y la matriz (la del Rojo decía `S,U(updated_at)`; la vigente es `S`).
7. **BAJA (DB-4, L3)** `revoke.sql` documenta que no restaura los `REVOKE ... FROM PUBLIC` (inocuo con propietario superusuario); no se otorga nada a `PUBLIC` (la prueba estática lo prohíbe).
8. **BAJA (DB-5, L4)** `_after_soft_rollback`: el `try` cubre `get_bind()` y se llama `alert("crypto_ops_lost", error_type=..., sqlstate=...)` además del `logger.error`; `sqlstate` entra en `ALERT_CONTEXT_KEYS`. Prueba en `test_oplog_rollback_failure.py`. La prueba del Rojo que contaba un único `ERROR` ahora mira solo el logger `app.crypto.oplog` (el sink de alertas escribe otro).
9. **BAJA (DB-6)** el `WARNING` `db busy` con el SQLSTATE ya valía para todos los `BUSY_SQLSTATES`; la prueba se parametriza sobre todos.
10. **LOW (L2)** `roles.sql`: `SET log_min_duration_statement = -1` y `SET log_duration = off` junto a los otros dos `SET`.

**Constancias.** `GIT_SHA` es público en `/health.version`; `tools` sin `read_only` (perfil de operador); `TRUSTED_PROXIES` manual en los ensayos.

### Evidencia de S4B-W0-3

Checkpoint `bcc1c65` (sello `wave0-gate.sh W0-3`, 568 passed).
Commit de evidencia posterior al sello: `d5f3890` (`docs(sprint-04b): evidencia de S4B-W0-3`, solo este cuaderno).

Checkpoint: bcc1c65. Sello: wave0-gate.sh W0-3 (568 passed con tests/architecture).

### Imágenes (reconstruidas con buildx, S4B-D98)
- apex-api:local  sha256:84f04df0428016bbec526172b10b103b971ff9642f7eb01926c9250ae8966d99 (antes da6d45f9...)
- apex-web:local  sha256:1f4f49377584194cf69ebf4bd0b54b228bb03cc788250433883a0083d1aaf312 (antes 6745c50b...)

### Ensayo apex-ensayo (subred 172.31.0.0/24, WEB_PORT 8280, POSTGRES_DB apex_ensayo, ENV=production)
- migrate: 15 revisiones, la última `0013_audit_verifications -> 0014_audit_log_triggers_always`, código 0; dbsetup código 0 ("roles aplicados; 16 tablas clasificadas").
- api, worker, backup, web, db: healthy; StartedAt de worker y web posterior al healthy del api; worker RestartCount 0.
- test_db_roles.sh contra el ensayo: 0 fallas (44 comprobaciones). test_env_isolation.sh: 0 fallas (api, worker, backup).
- Primer intento: test_env_isolation.sh detectó que env_file ../.env leía el .env de desarrollo; corregido con APEX_ENV_DIR y resellado.
- /api/v1/health 200 {"status":"ok","db":"ok","version":"dev"}; 45 GET seguidos: 11 con 200 y 34 con 429; el log del api no contiene "alembic".
- pg_stat_activity (apex_ensayo): apex (psql), apex_api, apex_worker.
- Tráfico real como apex_api: login, cambio de contraseña, GET /members 200, POST /plans 201/200 (fila creada), GET /dashboard 200; "permission denied" en el log del api: 0. Admin desechable admin-ensayo@apex.test solo en apex_ensayo (se borra con el volumen en V12).
- Ensayo detenido con `stop` (sin -v).

### P-ROL sobre apex-db-1
- `alembic current` = 0014_audit_log_triggers_always (head) antes; `dbsetup` con --no-deps: código 0, "roles aplicados; 16 tablas clasificadas"; no existe contenedor migrate del proyecto apex.
- pg_roles: apex_api, apex_backup, apex_worker: rolsuper/createrole/createdb/bypassrls = f; rolconnlimit 20, 2, 5.
- test_db_roles.sh contra apex-db-1: 0 fallas.
- .env: solo cambiaron APEX_API_DB_PASSWORD, APEX_WORKER_DB_PASSWORD y APEX_BACKUP_DB_PASSWORD (sha256 antes 5ab9b973..., después 812bbba4...). .env.ops creado desde el ejemplo con los valores de .env; ambos ignorados por git.
- Desarrollo: api, worker y backup se recrearon (force-recreate) y quedan healthy, pero usan al PROPIETARIO por diseño (compose.dev.yml, S4B-D11): pg_stat_activity de apex-db-1 muestra apex x3. Los roles se ejercitan con tráfico real en el ensayo.

## S4B-B0 · Partir el CLI sin comportamiento nuevo

### S4B-B0 · Línea base y B0.1 (extracción pura)

- Línea base en HEAD `d5f3890`: `pytest tests/cli tests/architecture tests/worker -q -m "not perf"` = 612 passed (1 perf deseleccionada); `/health` 200.
- B0.1: `cli_base.py` (unit_of_work, resolve_actor, DB_TIMEOUTS_CHOICES, RuntimeOptions, runtime_options, _sin_tiempos_de_espera, _load_module_services, cli_runtime, _run, _reject, production_guard_error, get_settings) y, para llegar a `cli.py` en 323 líneas, `cli_ops/{keys,openapi,accounts,recompute,verify_audit}.py` con el código de implementación de los siete comandos movido sin cambiar firmas ni mensajes; `cli_ops/__init__.py` con `register_ops(app)` vacío. `cli.py` reexporta por `__all__`.
- Única prueba tocada en B0.1: `test_crypto_bus_importers.py` (`IMPORTADORES_REALES`, `ARRANQUE` y un control: `cli.py` -> `cli_base.py`).
- Mapeo del gate: `slice-gate.sh` `cli` lintea, formatea y tipa `cli.py` + lo que exista de `cli_base.py`, `cli_ops`, `seed`, `imports`; caso nuevo en `scripts/workflow/tests/test_slice_gate.sh` (45 ok, 0 fallas); README actualizado.
- B0.1 verde por sí solo: `tests/cli tests/architecture tests/worker` = 612 passed (misma cuenta que HEAD); `slice-gate.sh cli` sin lista = 476 passed.

### S4B-B0 · Rojo

- Stubs en `cli_base.py`: `resolve_admin_actor` y `crypto_runtime` con `NotImplementedError`.
- `tests/cli/test_cli_base.py` (28 pruebas): 12 en rojo por `NotImplementedError` (8 de `resolve_admin_actor` y 4 de `crypto_runtime`: keyring y engine liberado, engine liberado si falla el cuerpo, KEK ausente, DEK que no se desenvuelve) y 16 en verde desde el Rojo (reexportación, `get_settings`, tamaños).
- Arquitectura: `test_app_layer_importers.py` (nueva, 14 pruebas) y `test_worker_boundaries.py` (+2) quedan en VERDE desde el Rojo, porque la extracción de B0.1 ya existe: el plan preveía rojo por archivos ausentes, pero tras B0.1 no hay ausentes. Rojo real de arquitectura: 0. Dos fallos de las propias pruebas nuevas se corrigieron en el acto (`cli_ops/openapi.py` importa `app.main` perezosamente como antes; `models` agrupaba `Member` como submódulo).
- Total del Rojo: 12 failed, 39 passed en los tres archivos.

### S4B-B0 · Verde

- `resolve_admin_actor` (`auth.service.active_admin_id_by_email`) y `crypto_runtime` (`configure_provider(get_key_provider(settings))`; en `cli_runtime`, bajo `actor_scope(SYSTEM_USER_ID)` y su transacción, desenvuelve cada DEK `active` no `sign` y recién entonces `ensure_keys`). Ningún comando los usa todavía.
- `_apoyo.correr` y `test_db_timeouts_cli.py` fijan `cli.get_settings` y `cli_base.get_settings`.
- `tests/cli tests/architecture tests/worker` = 656 passed (612 + 44 nuevas).
- Tamaños: `cli.py` 323, `cli_base.py` 200, `cli_ops/__init__` 15, `keys` 95, `openapi` 64, `accounts` 122, `recompute` 110, `verify_audit` 52. Ruff check, ruff format --check y mypy src (126 archivos) limpios.
- `test_guarded_calls`: `enforce_retroactive_limit` ya no aparece en ningún archivo (lo trae B1); la regla `archivo != "cli.py"` no cambia.

### S4B-B0 · Gates no sellantes (B0.5)

- `slice-gate.sh architecture` con las cinco pruebas del plan: 415 passed, verde (sello de `architecture`; el sellante será `slice-gate.sh cli ...` al cierre).
- `pytest tests/cli tests/worker -q -m "not perf"`: 241 passed.
- `scripts/workflow/tests/*.sh`: checkpoint 16, permisos 24, run_gates 22, slice_gate 45, validate_impact 16, wave0_gate 23, todos sin fallas.
- Nota: durante B0.1 se corrió `slice-gate.sh cli` (476 passed) y dejó un sello que ya está invalidado por los cambios posteriores.

### S4B-B0 · Revisión Python

`python-reviewer`: APROBAR, 0 bloqueantes. Aplicado: LOW 3 (`reject` público con `comando` obligatorio; `cli.py`, `recompute.py`, `verify_audit.py` y `test_cli_base.py` actualizados) y LOW 4 (comentarios de no-op en `_apoyo.py` y `test_db_timeouts_cli.py`). Constancias en DECISIONES: MEDIUM 1 (sin llamador hasta B1/B3), LOW 2 (duplicación con `_admin_actor_and_target`, a unificar en B1) y el tope de 200 líneas de `cli_base.py`.

### Evidencia de S4B-B0

Checkpoint `cf7a53f` (trailer verificado con `git log -1 --format=%B`). Sellante: `slice-gate.sh cli tests/cli/test_cli_base.py tests/cli/test_db_timeouts_cli.py tests/cli/test_seed_cli.py tests/cli/test_verify_audit.py` = 479 passed; antes `slice-gate.sh architecture` con las 5 pruebas del plan = 415 passed. `ruff check`, `ruff format --check` y `mypy src` limpios. `/health` 200. Contenedor `tools` (bind de desarrollo, sin datos): `--help` lista los comandos, `export-openapi /tmp/o.json` escribe, `import app.cli_base, app.cli_ops.keys` ok y `/app/src/app/cli_base.py` y `cli_ops/` presentes.

## S4B-B1 · Datos de demostración e importación de socios

### S4B-B1 · Rojo

- Línea base en HEAD `1344ac1` (árbol limpio; "Evidencia de S4B-B0" ya registrada arriba con `cf7a53f`/`1344ac1`): `/health` 200.
- B1.1 stubs: `seed/{__init__,dataset,apply}.py` (`dataset` solo tipos: `DemoPlan`, `DemoPayment`, `DemoFreeze`, `DemoSale`, `DemoMember`, `DemoSpec`; `demo_dataset` y `apply_demo`/`_sell_back_dated`/`_ensure_plans`/`_ensure_member`/`_sell_and_pay`/`_finish` con `NotImplementedError`), `imports/{__init__,members_xlsx,report}.py` (constantes de límites, `HeaderError`, `LimitError`, `RowError`, `RowResult`, `ImportResult`, `validate_header`, `parse_member_row`, `mask_document`, `check_limits`, `resolve_input`, `read_rows`, `import_members`, `report_path`, `write_report` con `NotImplementedError`), `cli_ops/seed_demo.py` (`run_seed_demo`, `CURRENT_DATABASE_SQL`, `SAFE_DATABASE_SUFFIXES`), `cli_ops/import_members.py` (`register(app)`), `register_ops` registra `import-members`, `cli.py` (`seed --demo --force-demo-on-non-empty --allow-production`; el cuerpo del seed del admin pasó a `_seed_admin` para no pasar de 50 líneas), `Settings.IMPORT_DIR` y `.env.example`, `scripts/plantillas/generar_importar_socios.py` (stub).
- Fixtures: `tests/factories/xlsx.py`, `tests/cli/conftest.py` (`import_dir`, `settings_importacion`, `settings_importacion_produccion`, `limpiar_demo`), `tests/cli/_apoyo.py` (`conteos_de_tablas`), `tests/cli/_apoyo_demo.py`.
- Rojo (suite acotada `tests/architecture tests/core/test_config.py tests/core/test_env_example.py tests/cli -m "not perf"`: 676 passed, 146 rojas = 135 failed + 11 errors, 2 saltadas):
  - `test_demo_dataset.py` 15 rojas (`NotImplementedError: demo_dataset`), 0 verdes.
  - `test_members_xlsx_parse.py` 58 rojas (`NotImplementedError`), 1 verde (la cabecera exportada es la de Q17).
  - `test_seed_demo.py` 26 rojas (salida 1 por `NotImplementedError` en lugar de 0/2), 0 verdes.
  - `test_seed_cli.py` +5 rojas (`--demo`), 13 verdes previas intactas.
  - `test_import_members.py` 38 rojas, 1 verde (`openpyxl.xml.DEFUSEDXML` y sin lxml), 2 saltadas (enlaces simbólicos sin privilegios en Windows; corren en CI/Linux).
  - `test_import_members_perf.py` 2 `perf` rojas (deseleccionadas del gate).
  - Arquitectura: 4 rojas (`test_guarded_calls` x2: una sola llamada de `enforce_retroactive_limit` en `_sell_back_dated` de `seed/apply.py`; `test_app_layer_importers` x1: `cli_ops/seed_demo.py` e `import_members.py` importan su paquete; `test_third_party_confinement` x1: `members_xlsx.py` importa `openpyxl`); el resto de `tests/architecture` en verde (493 con las pruebas de B0).
  - `test_config.py` (+3) y `test_env_example.py` (+1) para `IMPORT_DIR`: verdes desde el Rojo (el campo y la línea ya son parte de B1.1).
- `ruff check`, `ruff format --check` y `mypy src` (134 archivos) limpios. `/health` 200 al final.

### S4B-B1 · Verde

- Pasos B1.4 a B1.7 hechos; B1.8 sin el sello (`slice-gate.sh cli ...`), sin `run-gates.sh`, sin B1.9 ni checkpoint (esperan los hallazgos de `security-reviewer`).
- Archivos nuevos: `seed/{dataset,apply}.py`, `imports/{members_xlsx,limits,parse,persist,report,results}.py`, `cli_ops/{seed_demo,import_members}.py`, `cli_keyring.py`, `cli_session.py`, `tests/cli/test_seed_demo_fechas.py`, `scripts/plantillas/generar_importar_socios.py` (real), `docs/plantillas/importar-socios.xlsx`, `docs/operacion/{importar-socios,demo}.md`. Tocados: `cli_base.py` (176 líneas: `_load_keyring` salió a `cli_keyring.py`; `crypto_runtime(..., persist_keys=)`), RUNBOOK §12, CLAUDE.md, DECISIONES (bloque «S4B-B1», D105 a D108), SPRINT-04B.
- Conteos: `tests/architecture` + `test_config` + `test_env_example` + `tests/cli` (`-m "not perf"`) = 823 passed, 2 skipped (enlaces simbólicos sin privilegios en Windows; corren en CI), 2 perf deseleccionadas. Los 146 rojos y las 4 de arquitectura pasaron a verde sin cambiar una aserción. `slice-gate.sh architecture` (las cinco pruebas del plan) y `slice-gate.sh core/config` en verde. `ruff check`, `ruff format --check` y `mypy src` (140 archivos) limpios; `/health` 200.
- Perf (`uv run pytest -m perf tests/cli/test_import_members_perf.py`): 1.000 filas en 19,2 s (techo 120) y 5.000 en 95,4 s (techo 600). Una primera corrida dio salida 2 a los 0,23 s en la de 1.000 con un proceso de pytest en segundo plano colgado en la misma base de pruebas; no se reprodujo en dos corridas limpias.
- Desviaciones: D105 (firmas de `check_limits`/`read_rows` sobre bytes, `members_xlsx` como fachada), D106 (`cli_keyring.py`, `cli_session.py`, `persist_keys`: necesarios para que la segunda corrida y `--dry-run` no dejen `crypto_ops`, que el Rojo exige y el comportamiento de B0 contradecía), D107 (sin reporte por omisión, manda S4B-D34), nombre del contacto de emergencia también contra fórmulas.
- Dudas 1 a 12: resueltas como indicó el orquestador (ver DECISIONES, «Dudas del Rojo resueltas»); la 12 no exigió ajustar el catálogo.
- Falta para el cierre: `security-reviewer` de B1 (confinamiento de rutas, XXE, zip, celdas, reporte `O_EXCL`, PII, guarda de producción, orden de candados), `slice-gate.sh cli ...` sellante, `run-gates.sh`, B1.9 (demos 2 y 3 sobre `apex_demo`), checkpoint y «Evidencia de S4B-B1».

### S4B-B1 · Revisiones

`security-reviewer`: 0 CRITICAL, 0 HIGH, 2 MEDIUM, 4 LOW. Corregidos con prueba (detalle y decisión en DECISIONES, «S4B-B1 · Revisión de seguridad»):
- MEDIUM resumen y reporte parciales ante un fallo a mitad: S4B-D109.
- MEDIUM guarda de la base antes de las llaves: S4B-D110.
- LOW fórmulas en todo campo de texto: S4B-D111.
- LOW `IMPORT_DIR` aparte de `UPLOADS_DIR` y de la KEK: S4B-D112.
- LOW correos de demostración `@ejemplo.invalid`: S4B-D113.
- LOW constancia (sin cambio de código): las filas `unwrap` de `crypto_ops` de cada corrida del CLI se pierden por el rollback (S4B-D106); coste aceptado.
- Pendiente de B4 (dueño B4): `tools` no monta `IMPORT_DIR`; se anotó en DECISIONES y en `SPRINT-04B.md`.

### Evidencia de S4B-B1

Checkpoint `fa04fec` (trailer verificado con `git log -1 --format=%B`). Gates: `slice-gate.sh architecture` (5 pruebas del plan) 456 passed; `slice-gate.sh core/config` 581 passed; `run-gates.sh` en primer plano: api 5505 passed, 5 skipped, cobertura 96,68 % (`cli.py` 97 %, `cli_base.py` 100 %, `cli_keyring.py` 100 %, `cli_session.py` 100 %, `seed/` e `imports/` de 85 a 100 %), scripts de infraestructura y web (172 archivos, 3125 pruebas, lint, tsc, build) en verde; sellante `slice-gate.sh cli` con las 6 pruebas del plan 663 passed, 2 skipped (enlaces simbólicos en Windows), como último comando que tocó el árbol. `ruff check`, `ruff format --check` y `mypy src` limpios.

B1.9 sobre `apex_demo` (`apex-db_test-1`; `apex-db-1` no se tocó; evidencia completa en el scratchpad `b1-evidencia.md`): `alembic upgrade head` 0; `seed --demo --as` 0 con `planes=3 socios=30 membresias=31 pagos=33` y la segunda vez 0 `ya aplicado`; `verify-audit --as` 0 «Cadena íntegra: 132 registros»; psql: los seis estados (12/5/6/2/4/2), 30 socios con `document`, `phone` y `email` en `apx1.`; `import-members` por bind temporal: `--dry-run` 0, real 0 (`created=3 rejected=1`), repetida 0 (`skipped_existing=3`), CSV del dry-run y de la real idénticos, 5.001 filas 2, reporte existente 2, fuera de `IMPORT_DIR` 2, reportes sin cifras de 7 o más dígitos y logs de `api` y `worker` sin datos de la demo. `apex_demo` se conserva hasta V12 (S4B-D92). La demostración de `GET /dashboard` (T8 de US-109) es de V4 (S4B-D88).

## S4B-B2 · Backup: verificación del manifiesto en el worker y salud

### Evidencia de S4B-B1 (nota de hashes)

Los hashes `fa04fec`/`4e01e39` citados arriba se reescribieron al añadir el trailer: el checkpoint de B1 es `b8f80dd` y la evidencia `8023d56`.

### S4B-B2 · Rojo

- Línea base: HEAD `8023d56`, árbol limpio. Docker Desktop estaba apagado al empezar (el worker `apex-worker-1` se reinició solo al levantarlo y se volvió a detener; `db_test` arrancado con `docker start apex-db_test-1`). Worker parado al terminar.
- B2.1 stubs: `core/crypto/archive.py` (constantes y `digest_file` con `NotImplementedError`), `core/backup_status.py` (`HEALTH_JOB`, `MAX_RUN_AGE` 36 h, `BACKUP_STATES`, `PUBLIC_BACKUP`, `backup_health`), `worker/jobs/backup_check.py` (`NAME`, `MAX_BACKUP_BYTES`, `BackupStatus` Literal, `Manifest`, `ManifestFile`, `parse_manifest`, `evaluate`, `run`, `get_settings` importado para la fixture), `core/jobs.py` (`DETAIL_KEYS` +4, `last_results`), `worker/runner.py` (`JobResult.status`, `InvalidJobStatus`), `worker/jobs/__init__.py` (`backup_check` a las 07:00 con `timeout_s` 600), `core/health.py` (`HEALTH_CACHE_TTL_S`, `clear_health_cache`, `register_health_check(..., allowed, healthy)` guardados pero no aplicados), `main.py` (registro del check `backup`), `core/config.py` (`BACKUP_DIR`), `.env.ops.example` (BACKUP_DIR; `BACKUP_*` es de operación, no de `.env.example`).
- Fixtures: `tests/factories/backup.py`, `tests/worker/conftest.py::backup_dir`, `tests/core/conftest.py::health_cache_limpia` (autouse en todo `tests/core`).
- Pruebas existentes reparadas (cambio de contrato, no debilitadas): `test_health.py::test_comprobacion_informativa...` (el check informativo ya no se llama `backup`, nombre reservado y registrado por `create_app`), `test_jobs_core.py::test_detail_keys_es_el_conjunto_cerrado_del_plan` (+4 claves), `test_schedule.py` (`JOBS` por tupla con `backup_check`).
- Rojo (suite acotada: `tests/worker`, `tests/architecture`, `tests/core/{test_health,test_backup_status,test_config,test_env_example,test_openapi_export}`, `tests/crypto/test_archive`): 167 rojas, el resto verde:
  - `test_backup_check_evaluate.py` 69 rojas (`NotImplementedError`), 0 verdes.
  - `test_backup_check.py` 32 rojas, 1 saltada (enlace simbólico sin privilegios en Windows).
  - `test_runner.py` +8 rojas (`status` ignorado), `test_jobs_core.py` +3 (`last_results`), `test_main.py` +9 (`EXIT_BY_RESULT`, estados y corridas reales).
  - `test_health.py` 13 rojas (`allowed`, `healthy`, caché, `Lock`, `HealthOut.backup`), `test_backup_status.py` 15 rojas, `test_archive.py` 13 rojas (1 saltada).
  - Arquitectura 5 rojas: `test_archive_importers` x1, `test_backup_status_imports` x2, `test_core_import_direction` x1, `test_worker_boundaries` x1; 471 verdes.
  - Verdes desde el Rojo (datos ya presentes en los stubs, como `IMPORT_DIR` en B1): `test_config.py` +3 y `test_env_example.py` +1 (`BACKUP_DIR`).
- `ruff check`, `ruff format --check` y `mypy src` (143 archivos) limpios. `/health` 200.
- Sin Verde desechable en este slice: no se validó que cada prueba pueda pasar con una implementación de referencia.

### S4B-B2 · Verde

- Código: `core/crypto/archive.py` (`digest_file`), `core/jobs.py` (`last_results`), `core/backup_status.py`, `core/health.py` (caché con TTL y `Lock`, `allowed`/`healthy`, checks en paralelo, `HealthOut.backup`), `main.py` (ya registraba `backup`), `worker/jobs/backup_check.py`, `worker/runner.py` (`_resultado_de`, `BACKUP_BAD_STATES`, aviso `backup_unhealthy`), `worker/main.py` (`EXIT_BY_RESULT`).
- Resolución de las 10 notas: (1) `HealthOut.backup` + contrato regenerado; (2) check `backup` en `create_app`, caché con `current_clock()` y `get_engine` resuelto en `health`; (3) `MAX_RUN_AGE` 36 h = S4B-D114; (4)-(5) semántica del Rojo; (6) `main.py` importa `backup_status`, `health.py` no importa `core.jobs`; (7) `getattr(os, "O_NOFOLLOW", 0)`; (8) sin `per-file-ignores` (ruff no los exige aún); (9) pruebas de caché y log validadas en verde; (10) ok.
- P-API: `export-openapi` x2 idénticas (cmp), `docs/openapi.json` +10 líneas, `gen:api` -> `types.ts` +6, `tsc` limpio, `src/core/api` 173 pruebas verdes.
- Desviación: `health_status` corre las comprobaciones en paralelo (S4B-D115).
- Docs: RUNBOOK §12, CLAUDE.md, DECISIONES «S4B-B2», SPRINT-04B.
- Pendiente: `security-reviewer`, gate sellante `slice-gate.sh worker ...`, B2.9 (Docker, demo), checkpoint.

### S4B-B2 · Revisiones

security-reviewer: 0 CRITICAL, 0 HIGH, 2 MEDIUM, 3 LOW; 5/5 corregidos (TDD, S4B-D116 a D120 en DECISIONES):
1. MEDIUM FIFO: `O_NONBLOCK` + `fstat` regular en `digest_file` y `_leer_manifiesto`. Corregido.
2. MEDIUM `files` sin tope ni unicidad: `MAX_FILES = 8`, nombres únicos con prefijo del juego -> `corrupt`. Corregido.
3. LOW `digest_file` hasta EOF: `max_bytes` con el tamaño declarado. Corregido.
4. LOW `BACKUP_DIR` sin validar: validador `_anidadas`. Corregido.
5. LOW registradores de `/health` sin prueba de arquitectura: `test_health_check_registrars.py`. Corregido.

### S4B-B2 · Evidencia

Checkpoint `2c6b194`. Gates en verde tras las correcciones: `crypto` (503 passed, 2 skipped), `core/config` (621), `core/health` (506), `architecture` con las 6 pruebas (480) y el sellante `slice-gate.sh worker` con las 6 pruebas del plan (732 passed, 3 skipped: enlace simbólico y dos FIFO, que no existen en Windows). `ruff check`, `ruff format --check` y `mypy src` (143 archivos) limpios.

Imágenes (buildx, S4B-D98): `apex-api:local` sha256:a6cd7f599d52b9f709d002e2eeefb24549c5aac8ecc35f9e347940de4bb896d1 (antes 84f04df04280); `apex-web:local` sin cambios (1f4f49377584); `apex-backup:local` sin cambios (c9510caf189d).

Desarrollo (`apex-db-1`; `api` y `worker` recreados con `--no-build --force-recreate`, ambos healthy; `web` reiniciado porque Nginx conservaba la IP anterior del api): volumen `apex_backups` vacío -> `--run-once backup_check` sale 1 con `result: missing`, `details {"archivos": 0}`, log `WARNING backup_check finished` sin ruta y alerta `backup_unhealthy` (result missing); `--status backup_check` muestra `missing`; `/health` directo (8181) `{"status":"ok","db":"ok","version":"dev","backup":"attention"}` y por Nginx (8180) igual: 200 con `attention`.

Ensayo `apex-ensayo` (WEB_PORT 8280; par age y llave minisign de prueba generados en el scratchpad con `apex-backup:local`, nunca en el repositorio; api, worker y backup recreados con la imagen nueva, todos healthy):
- `run.sh` sin identidad: `verify: skipped`; `--run-once backup_check` sale 0 con `ok_unverified` (`archivos 1, edad_horas 0, tamano_bytes 79940, verificado 0`); `/health` 8280 pasó de `attention` (corrida de recuperación del arranque, con el volumen vacío, cacheada 30 s) a `"backup":"ok"` tras la caché.
- Con `-f infra/compose.verify.yml` y la identidad de verificación: `run.sh` "verificación de descifrado: ok", `verify: ok`; `--run-once backup_check` sale 0 con `ok` (`archivos 2, verificado 1`), la fila del día se reutilizó (`attempts` 3: missing de la recuperación, ok_unverified, ok); `/health` `"backup":"ok"`.
- `grep -c /data/backups` sobre la salida de las corridas y sobre `logs --tail 80 worker`: 0.
- No se pudo hacer la última parte del plan (borrar los archivos de prueba del volumen y repetir con el volumen vacío): el sistema bloqueó el `rm` dentro del contenedor (comprobación de seguridad); el caso `missing` con volumen vacío queda demostrado en desarrollo arriba. Los archivos de prueba quedan en el volumen `apex-ensayo_backups` (se van con el volumen en V12).
- Ensayo detenido con `stop` (sin `-v`).

Linux: `digest_file` sobre un FIFO dentro de `apex-api:local` lanza `OSError` en 0,0 s ("no es un archivo regular"); las pruebas de FIFO de pytest se omiten en Windows y corren en CI.

## S4B-B3a · Respaldo de la KEK con `age -p`, `restore.sh` y prueba de restauración

### S4B-B3a · Rojo

- Línea base: HEAD `701ba45`, árbol limpio. `tests/crypto tests/architecture tests/cli/test_cli_base.py`: 670 passed, 4 skipped. Tras el Rojo, la misma suite más `test_export_kek.py` y `test_kek_real_age.py`: 690 passed, 34 failed, 42 skipped (0 regresiones: las 34 rojas son todas de archivos nuevos o ampliados).
- B3a.1 stubs: `core/crypto/archive.py` (`VerifyKekResult` con `ok` derivado, `NoTty`, `AgeError`/`AgeMissing`/`AgeTimeout`, `KekLengthInvalid`, `KekPathRejected`, `KEK_LEN`, `export_kek_file`/`restore_kek_file`/`verify_kek_backup` con `NotImplementedError`, `get_settings` importado para que las pruebas lo reemplacen), `core/crypto/kek_backup.py` (`WrappedDek`, `verify_wrapped`, `load_wrapped`), `core/crypto/registry.py` (`kek.backup` sin llave: ya verde desde el Rojo, como `IMPORT_DIR` en B1), `cli_ops/kek.py` (tres comandos que salen 2 con "no implementado") y su registro en `cli_ops/__init__.py`, `infra/backup/restore.sh` (exit 99), `infra/tests/restore_e2e.sh` (exit 99, Rojo documental).
- Fixtures: `tests/factories/fake_age.py` (`fake_age`, `configurar`, `llamadas`, `latido`, `envolver_falso`/`desenvolver_falso`), `tests/factories/pty_run.py` (`correr_con_pty`, solo Linux), `tests/cli/_apoyo.correr_con_pty`, `tests/crypto/conftest.py` (`kek_tmp`, `wrapped_de_prueba`, `age_falso`, `entorno_visto`), `tests/cli/conftest.py` (`kek_de_prueba`, `settings_kek`, `ajustes_kek`, `entorno_kek`, `llaves_en_base`).
- Rojo por archivo (ejecución normal en este equipo / con `APEX_FAKE_AGE_FORZAR=1`, que fuerza el age falso en Windows solo para ver el Rojo):
  - `tests/crypto/test_kek_backup.py`: 10 rojas (`NotImplementedError` de `verify_wrapped`/`load_wrapped`, y `restore` ausente de `OP_PURPOSES`), 1 verde (no hay lector público de la KEK).
  - `tests/crypto/test_archive_kek.py`: 10 rojas y 20 saltadas / 29 rojas y 1 saltada (`NotImplementedError` de las tres funciones). Saltadas: las 20 que lanzan el age falso (Windows, ver desviación 1) y el enlace simbólico sin privilegios.
  - `tests/cli/test_export_kek.py`: 9 rojas y 13 saltadas / 22 rojas (salida 2 "no implementado" donde se esperaba 0, o el texto de contrato ausente), 1 verde (`--passphrase*` no existe).
  - `tests/architecture/test_kek_path_single_door.py`: 1 roja (`archive.py` aún no abre la KEK), 6 verdes. `test_archive_importers.py`: 2 rojas (`cli_ops/kek.py` aún no importa `archive`), 5 verdes. `test_third_party_confinement.py`: 2 rojas (`archive.py` sin `subprocess` ni `Popen`), 23 verdes. `test_core_import_direction.py` y `test_worker_boundaries.py`: 3 pruebas nuevas verdes de nacimiento (guardas sobre archivos que ya existen como stubs).
  - `test_registry.py` (+2) y `test_bootstrap.py` (+1): verdes desde el Rojo porque el stub ya registra `kek.backup`; `test_las_cinco_clases_de_v01` se reparó (`ESPERADAS | SIN_LLAVE`).
  - `tests/crypto/test_fake_age.py`: 5 verdes (autoprueba del falso). `test_archive_real_age.py` (3) y `test_kek_real_age.py` (2): 5 saltadas (Windows sin `pty` ni `age`); corren en CI y contenedor Linux, y la CI las exige sin saltos (S4B-D103).
  - `infra/backup/tests/test_restore_guard.sh`: 29 fallas y 30 verdes (la mayoría de los verdes son negativas que se cumplen al no tocar nada el stub); `run.sh` de tests: 3 de 4 archivos en verde. `restore_e2e.sh`: Rojo documental, "corre en B3a.4 dentro de apex-ensayo y en CI".
- `ruff check`, `ruff format` y `mypy src` (145 archivos) limpios. `bash -n` limpio en los tres scripts. Todas las rojas fallan por `NotImplementedError`, "no implementado" o aserción real; ninguna por `ImportError` ni fixture rota.
- Sin Verde desechable en este slice.

### S4B-B3a · Dudas y desviaciones del Rojo (para el Verde)

1. El age falso no corre en Windows: `Popen(env={})` sobre un `.cmd` falla (cmd.exe no arranca con entorno vacío; verificado). Las pruebas que lo lanzan se saltan en Windows con motivo (`age_falso`) y corren en Linux/CI o en el contenedor; `APEX_FAKE_AGE_FORZAR=1` las fuerza. El Verde debe validarlas en Linux (contenedor) antes de sellar.
2. Control del falso por archivo (`control.json`), no por `FAKE_AGE_NO_TTY`: con `env={}` el hijo no ve variables.
3. `AGE_BINARY` sigue siendo `/usr/bin/age` (`test_archive.py` lo fija desde B2); `age_falso` parchea la constante y los `age_binary=` por defecto (`__kwdefaults__`) para conservar la firma exacta del plan.
4. `OP_PURPOSES` no incluye `restore`: `oplog.record(purpose="restore")` lanzaría `CryptoError`. El plan dice "migración: ninguna", y `crypto_ops.purpose` no tiene CHECK, así que basta añadirlo a la tupla; `test_el_proposito_restore_existe_en_la_bitacora` lo exige.
5. `archive` lee `BACKUP_DIR` y `dirname(CRYPTO_LOCAL_KEK_PATH)` por `get_settings()` (las pruebas lo reemplazan por un objeto con solo esos dos atributos); no hay otros parámetros en la firma del plan.
6. Excepciones nuevas fijadas por las pruebas: `KekPathRejected` (ruta bajo `BACKUP_DIR`/KEK viva/enlace; sin la ruta en el mensaje), `KekLengthInvalid(AgeError)` (31/33/0/64 bytes), `AgeError` ante archivo ajeno o frase mala (sin texto del hijo), `NoTty` (el Verde detecta el aviso de age en stderr sin reproducirlo). Una KEK de tamaño incorrecto o ausente lanza `CryptoError` (`kek_invalid`/`kek_missing`, de `check_key_file`).
7. `test_kek_path_single_door.py`: el plan decía "solo local_provider y archive referencian `CRYPTO_LOCAL_KEK_PATH`"; es falso hoy (config, provider, `cli_ops/keys.py`, `openapi.py`). Se fijó "solo ellos ABREN la KEK" y una lista cerrada de archivos que la NOMBRAN, que incluye `cli_ops/kek.py` (pasa la ruta a `archive`).
8. Contrato de textos del CLI (todos en `test_export_kek.py`): `--as es obligatorio`; `no existe un admin activo`; `la ruta de salida no es válida`; `el archivo de salida ya existe`; `solo con CRYPTO_PROVIDER=local`; `la KEK no está disponible`; `se requiere una terminal interactiva`; `sin bitácora`; `verify-kek-backup: total=N failed=M` (10 = cinco DEK + cinco llaves de índice de v0.1; la verificación cuenta todas las `active`/`decrypt_only`); `no se pudo abrir el respaldo`.
9. Contrato de `restore.sh` (cabecera de `test_restore_guard.sh`): `APEX_RESTORE_DATA_ROOT` y `APEX_RESTORE_TMP` como raíces configurables, `run.sh` junto al propio script, firma en `<manifiesto>.minisig`, la inspección del `tar` y la verificación de sha256 ocurren ANTES de la guarda de filas y de `pg_restore`, y las negativas salen con 2 (fallo de `run.sh` sale con 1).
10. `kek_tmp` vive en `tmp_path/keys/kek.bin` (no en la raíz de `tmp_path`) para que "el directorio de la KEK viva" no abarque las salidas de la prueba.
11. `restore_e2e.sh` se registró en `infra/tests/` (carpeta nueva); `test_infra_scripts.sh` solo gana una comprobación explícita porque `infra/backup/tests/run.sh` ya recorre `test_*.sh`.

### S4B-B3a · Verde

- Código: `core/crypto/archive.py` (368 líneas; `Popen` por lista con `env={}` y sin shell, KEK por `stdin`/`PIPE`, salida `O_EXCL|O_NOFOLLOW` 0o600, plazo y `kill`, errores tipados sin texto del hijo), `core/crypto/kek_backup.py`, `core/crypto/models.py` (`restore` en `OP_PURPOSES` y `OpPurpose`), `cli_ops/kek.py` (292 líneas, `cli_runtime`, `resolve_admin_actor(required=True)` en export y restore, `audit.record` + `oplog.record`, restore tolera la base caída). `infra/backup/restore.sh`, `lib.sh` (+`valid_tar_listing`), `Dockerfile` (copia `restore.sh`), `infra/tests/restore_e2e.sh`, `.github/workflows/ci.yml` (job `api`: `-rs --junitxml` y paso que exige 0 saltadas en los dos archivos de age real; job `images`: smoke con `SMOKE_KEEP=1`, guardas, e2e y `down -v` con `always()`). Docs: `docs/operacion/respaldo-y-restauracion.md`, RUNBOOK §12, `CLAUDE.md`, DECISIONES (S4B-D121 a D129).
- Conteos en verde, Windows (host): `tests/crypto` + `tests/architecture` (gate `crypto`): 545 passed, 25 skipped; gate `architecture`: 495 passed; `tests/cli/test_export_kek.py + test_kek_real_age.py + test_cli_base.py`: 38 passed, 15 skipped; `infra/backup/tests`: 4 de 4 archivos (`test_restore_guard.sh` 59 ok, `test_lib.sh` 57 ok); `ruff check`, `ruff format --check` y `mypy src` (145 archivos) limpios.
- Saltadas en Windows (motivo): 20 de `test_archive_kek.py` y 3 de `test_export_kek.py` (+ las de `test_sin_terminal`) por el `age` falso (cmd.exe no arranca con `env={}`), 1 por enlaces simbólicos sin privilegios, 3 de `test_archive_real_age.py` y 2 de `test_kek_real_age.py` (sin `pty` ni `age`), y las de FIFO/enlaces de `test_archive.py`. Todas corrieron en Linux (siguiente punto); nada saltado se da por verde en Windows.
- Linux (contenedor `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`, `age` 1.1.1 de Debian, `UV_PROJECT_ENVIRONMENT=/tmp/venv`, base de prueba por `host.docker.internal:5443`): `test_archive_kek + test_fake_age + test_kek_backup + test_archive_real_age + test_export_kek + test_kek_real_age`: **74 passed, 0 skipped** (incluye las 5 con `age` real y `pty`); ampliado con `test_archive + test_registry + test_bootstrap + test_cli_base`: **133 passed, 0 skipped**. Cobertura en Linux de esos 6 archivos: `archive.py` 82 %, `kek_backup.py` 97 %, `cli_ops/kek.py` 90 %. En Windows la cobertura por archivo no se mide (el `age` falso se salta).
- Scripts: `test_restore_guard.sh` 59 ok / 0 fallas (Git Bash); `restore.sh` real contra PostgreSQL 16, `age`, `minisign` y `tar` de BusyBox reales (contenedores desechables, borrados): restaura 2 filas y el ancla, rechaza una base con datos (salida 2), acepta `--i-know-this-overwrites`, y `run.sh --prefix pre-restore` corre antes de `pg_restore`. `bash -n` limpio en `restore.sh`, `restore_e2e.sh` y `lib.sh`. `restore_e2e.sh` NO se ejecutó de punta a punta en este equipo (necesita el stack del smoke o `apex-ensayo`); su primera corrida es la CI o B3a.7.
- Imagen `apex-backup:local` reconstruida con buildx: id `7dfddddf3c88` (verificado dentro de la imagen: `bash -n /opt/backup/restore.sh`, `age --version` = 1.3.2, `minisign -v` = 0.12). `apex-api:local` NO se reconstruyó (B3a.7).

#### Desviaciones del Verde respecto al Rojo y al plan (también en DECISIONES)

1. `total=10` -> `total=8` en `test_kek_backup.py`, `test_export_kek.py` y `test_kek_real_age.py`: hay 5 DEK y 3 llaves de índice, no 5 (S4B-D123).
2. `tests/factories/fake_age.py` no anota `LC_CTYPE` (lo añade el intérprete de Python 3.12 al entorno vacío; PEP 538) (S4B-D122).
3. `tests/factories/pty_run.py` gana `cwd` (el Rojo lo llamaba desde `_apoyo.correr_con_pty` sin que existiera) (S4B-D126).
4. `tests/cli/test_cli_base.py`: `TOPE_CLI_OPS = {"kek.py": 400}` (S4B-D121).
5. `restore-kek` no escribe bajo el volumen `keys` (regla del propio Rojo): la guía restaura a una carpeta y mueve con `install` (S4B-D125).
6. `verify-kek-backup` sale 1 con `total=0` y registra auditoría `verify` (S4B-D127).
7. `restore_e2e.sh` quedó como script completo pero sin corrida local de punta a punta.

#### Pendiente

`security-reviewer` de B3a, sello `slice-gate.sh cli`, B3a.7 (Docker y evidencia sobre `apex-ensayo`, con `apex-api:local` reconstruida) y checkpoint. Abierto para el ensayo: `pg_restore` sin `--single-transaction`.

### S4B-B3a · Revisiones

- **security-reviewer:** 0 CRITICAL, 0 HIGH, 4 MEDIUM, 6 LOW. Estado 10/10: 9 corregidos con prueba y 1 aceptado con dueño (L2, v0.2 con OpenBao). Decisiones S4B-D130 a D137 en DECISIONES.
  - M1 TOCTOU de `restore.sh` (D131), M2 `valid_tar_listing` con enlaces de BusyBox/GNU y topes (D132), M3 `pg_restore` todo o nada y `dbsetup` tras restaurar (D133), M4 la KEK en claro solo en `/dev/shm` (D135): corregidos.
  - L1 solo errores de conexión degradan `restore-kek`, con línea JSON (D130), L3 la guarda de filas mira seis tablas (D133), L4 secretos fuera de argv y lista de proyectos en `restore_e2e.sh` (D136), L5 dueño y permisos de los uploads restaurados (D133), L6 `digest_file` en `digest.py` y detección por AST de aperturas con alias (D134): corregidos.
  - L2 copias inmutables de la KEK por `AESGCM(bytes(kek))` (D137): aceptado; `archive.py` ya escribe a `stdin` desde un `memoryview` del `bytearray`.
- **Conteos tras las correcciones.** Windows: gate `architecture` 497 passed; gate `crypto` 547 passed, 25 skipped; `test_restore_guard.sh` 73 ok, `test_lib.sh` 64 ok (en Linux la guarda da 74 ok: suma la comprobación de permisos 600/700 que NTFS no puede hacer); `tests/worker/test_backup_check*.py` + `tests/core/test_backup_status.py` 127 passed, 3 skipped; `ruff`, `ruff format --check` y `mypy src` limpios. Linux (contenedor uv, `age` 1.1.1): `test_archive_kek`, `test_fake_age`, `test_kek_backup`, `test_archive_real_age`, `test_export_kek` y `test_kek_real_age`: 78 passed, 0 skipped (4 pruebas nuevas de `restore-kek`).
- **Imágenes reconstruidas con buildx:** `apex-backup:local` id `bf10096a5068`; `apex-api:local` id `5289c8fce66d`.

### S4B-B3a · Evidencia

- Checkpoint `5e4ad47`. Sello `slice-gate.sh cli` (536 passed, 18 skipped en Windows) escrito tras las últimas correcciones, incluidas las dos del propio `restore_e2e.sh` (S4B-D138).
- Imágenes (buildx): `apex-backup:local` `bf10096a5068`, `apex-api:local` `5289c8fce66d`. Desarrollo: `up -d --no-build --force-recreate api worker` (el worker estuvo parado durante el cambio en `worker/jobs/backup_check.py` y volvió a `healthy`); `apex-db-1` no se tocó.
- Ensayo (`apex-ensayo`, `ENV=production`, base `apex_ensayo`): `up -d --no-build --force-recreate api worker backup` con api, worker, backup y db `healthy`. Claves de respaldo efímeras (par `age` y par `minisign`) generadas fuera del repositorio y borradas al terminar; el recipiente y la llave de firma entraron solo por variables de la invocación.
- `run.sh` con `compose.verify.yml`: db 78.702 bytes y uploads 1.736 bytes cifrados, `verify: ok`, manifiesto firmado, `upload: skipped`, 0,9 s.
- `restore_e2e.sh` sobre el ensayo (`E2E_DC` del ensayo, base `apex_restore` creada y borrada dentro de su `db`): 23 comprobaciones, 0 fallas, 31 s en total. Socio con documento cifrado; `export-kek` y `verify-kek-backup` con `age` real bajo `pty` (frase aleatoria solo en memoria, no escrita en ningún archivo); `run.sh`; casos negativos que salen 2 sin tocar la base ni tomar `pre-restore` (manifiesto sin firma, firma inválida, sin `-P`, `--confirm-database` distinto, `tar` con enlace simbólico en un juego firmado de verdad); `restore.sh` sale 0 con `--single-transaction`; el ancla impresa (`through_seq` y `through_hash`) coincide con `audit.verifications` de origen y de la base restaurada; los 17 triggers de origen quedan igual (17 en `A`); `pre-restore` presente; `dbsetup` sobre la base restaurada y `apex_api` lee `members.members`; el adjunto restaurado es de 10001:10001 con modo 600 y la imagen del api lo lee; `restore-kek` a `/dev/shm`; con la KEK restaurada `reveal` devuelve el documento; con otra KEK el arranque falla con `unwrap_failed` y no aparece el documento ni material.
- Para no perder los juegos anteriores del ensayo (el script limpia `apex-*` del volumen `backups` de ese proyecto), se copiaron a un volumen temporal y se devolvieron al terminar (8 archivos). `$DCE stop` al final (nunca `down -v`); quedan solo `apex_ensayo` y su volumen.
- Pendiente: `pg_restore` en la CI (la primera corrida del job `images` con `restore_e2e.sh` sobre el stack del smoke) y el borrado de los artefactos del ensayo en V12.


## S4B-B3b · Rojo

### Línea base

- Árbol limpio en `82caed7`. `tests/crypto tests/architecture tests/cli/test_cli_base.py tests/cli/test_export_kek.py` (`-m "not perf"`): 726 passed, 43 skipped, 1 failed. El fallo es previo al slice: `tests/crypto/test_digest.py::test_solo_importa_hashlib` (`digest.py` importa `os`, `pathlib`, `stat` y `typing` desde que B3a le añadió `digest_file`, S4B-D134; el test sigue exigiendo solo `hashlib`). No es de B3b; lo arregla quien toque `digest.py` o el test (propuesta: el test debe admitir esa lista cerrada de la biblioteca estándar).

### Archivos del Rojo

- Stubs (`NotImplementedError` o salida 2 `no implementado`): `core/crypto/discovery.py` (`ColumnRef` completo, `encrypted_columns` stub), `core/crypto/service.py` (constantes, excepciones, `next_key_state`, `validate_reason`, `start_rotation`, `reencrypt_batch`, `finish_rotation`, `fail_job`, `rotate_index`, `count_rows_by_key`, `count_audit_blobs`, `retire_key`, `recent_kek_verify`), `cli_ops/rotate_key.py`, `cli_ops/retire_key.py`, registrados en `cli_ops/__init__.py`.
- Apoyo: `tests/crypto/_rotacion.py` (`rotacion_lista`, `filas_rotacion`, `candado_rotacion_tomado`, `manifiesto_reciente`, `escribir_manifiesto`, `verify_reciente`, ayudas de lectura) y `tests/crypto/_rotacion_flujo.py` (`rotar`, `iniciar`, `un_lote`, `cerrar`, `recargar`, `registrar_blob`); `tests/crypto/conftest.py` y `tests/cli/conftest.py` reexportan las fixtures.
- Arquitectura (se añadieron al final de cada archivo): `test_guarded_calls.py`, `test_sql_literals_constant.py`, `test_no_direct_now.py`, `test_file_and_function_size.py`, `test_core_import_direction.py`, `test_worker_boundaries.py`, `test_third_party_confinement.py`.
- Crypto: `test_next_key_state.py`, `test_discovery.py`, `test_rotate.py`, `test_rotate_concurrency.py`, `test_rotate_index.py`, `test_retire_key.py`. CLI: `test_rotate_key_cli.py`, `test_retire_key_cli.py`.

### Conteo en rojo

- Arquitectura (4 rojas, el resto son controles y reglas que ya se cumplen con los stubs): `test_service_toma_for_update_en_las_cuatro_funciones_de_rotacion` (el `service.py` stub no llama `with_for_update`), `test_service_ejecuta_las_dos_sentencias_con_text_y_la_constante`, `test_rotated_at_de_service_sale_de_current_clock`, `test_las_cuatro_funciones_de_rotacion_estan_implementadas_y_miden_menos_de_50` (detecta stubs). Verdes por diseño: tipado de las constantes, importaciones de `service`/`discovery`/CLI, `pyrage` ausente y los controles con fuentes falsas.
- `tests/crypto`: `test_next_key_state` 8 rojas de 9 (la verde comprueba que `InvalidTransition` no es `ValueError`); `test_discovery` 9/9; `test_rotate` 32/32; `test_rotate_concurrency` 5/5; `test_rotate_index` 11 de 12 (la verde fija `MAX_INDEX_ROWS == 50_000`); `test_retire_key` 21/21. Total 86 rojas, 2 verdes. Causa: `NotImplementedError` del stub, salvo `test_una_escritura_con_for_share_hace_esperar_a_start_rotation`, que cae en una aserción real (el stub termina al instante).
- `tests/cli`: `test_rotate_key_cli` 22/22 rojas (aserción sobre `no implementado`, salida 2 en lugar de 0/1, o `NotImplementedError`); `test_retire_key_cli` 1 roja y 22 en error de preparación, todas por `NotImplementedError: service.start_rotation` en la fixture `rotada` (necesita una rotación real para tener una `decrypt_only`). Al llegar el Verde de `core/crypto` esas 22 pasan a ejecutar su aserción.
- Ninguna falla por `ImportError`, sintaxis o fixture rota. `ruff check .`, `ruff format --check .` (587 archivos) y `mypy src` (149 archivos) limpios.
- Regresión: el resto de lo corrido en la línea base sigue igual (747 passed contando las verdes nuevas, 43 skipped; el único fallo previo es `test_digest`).

### S4B-B3b · Dudas y desviaciones del Rojo (para el Verde)

1. `next_key_state(current, event, purpose)` con `event: Literal["rotate", "retire"]`: el plan decía `job_status`, que no puede expresar "decrypt_only → retired solo por retiro". `InvalidTransition` no hereda de `ValueError`.
2. Errores que fijan las pruebas: `ValueError` para `reason` inválido (también vacío o en blanco), para un conteo `confirmed_audit_blobs` distinto, para filas de negocio pendientes, para una llave inexistente y para `rotate_index` sobre `MAX_INDEX_ROWS`; `InvalidTransition` si la llave no está `decrypt_only`; `DatabaseBusy` (de `core.db`) si el `FOR UPDATE` vence por `lock_timeout`; `RotationInProgress` si otra conexión tiene `pg_try_advisory_lock(hashtext('apex:rotate:<clase>'))`; `ValueError` en `discovery` si falta tabla/columna o no es `Encrypted` de esa clase; `CryptoError(unknown_data_class)` para una clase fuera del registro.
3. El "tope de 50.000 filas" se baja con `monkeypatch.setattr(service, "MAX_INDEX_ROWS", 10)`: el Verde debe leer la constante del módulo en cada llamada (no copiarla a un default).
4. La falla inyectada de `test_rotate.py` parchea `bus.decrypt` (atributo de módulo): el servicio debe llamar `bus.decrypt` y `bus.encrypt` por `from app.core.crypto import bus`. `reencrypt_batch` devuelve las filas migradas en ese lote (0 cuando no queda ninguna); `fail_job(job_id, error_code)` corre en su propia transacción y deja `error == error_code`.
5. `start_rotation` no recarga el keyring del proceso: lo hace quien rota (`Keyring.load_all`), como en `_rotacion_flujo.iniciar`. El candado de sesión: las pruebas solo fijan que, con otra conexión sosteniéndolo, `start_rotation` lanza `RotationInProgress` sin crear llave ni job. Quién retiene el candado entre lotes (conexión dedicada del comando) lo decide el Verde; atención a no dejarlo tomado en una conexión del pool (las fixtures no pueden soltarlo).
6. `recent_kek_verify(session, within)` compara contra `current_clock()`, no contra `now()` del servidor (`T0` de `reloj` ≠ fecha real): `verify_reciente` inserta `crypto_ops.at = reloj - edad`. Cuenta solo `verb = 'verify'`, `data_class = 'kek.backup'`, `result = 'ok'` y `user_id != SYSTEM_USER_ID`.
7. `retire_key` registra una fila `crypto_ops` `rotate` (+1 sobre las existentes; la prueba no fija con qué `key_id`). La auditoría `audit.record(... "retire" ...)` y la del motivo de `rotate-key` las escribe el CLI (el servicio no importa `core/audit`); por eso "auditoría con el motivo" se prueba en `tests/cli/test_rotate_key_cli.py` y no en `test_rotate.py`.
8. Contrato de textos del CLI (todos en los dos archivos de `tests/cli`): `rotate-key: total=N`, `rotate-key: hecho=X/N` por lote, última línea `rotate-key: llave anterior en decrypt_only; retirar con retire-key`; `--reason` en el texto de cada rechazo de motivo (sin repetir el motivo recibido); `esa clase no admite rotación hasta EP-18 (G-09)`; `rotación en curso` (salida 1); `la base está ocupada` (salida 1) tras un intento y tres reintentos de 1 s con `asyncio.sleep(1)` y `service.start_rotation` llamado por módulo (4 llamadas); `repita el comando` tras una falla de lote (salida 1, sin el texto de la excepción). `retire-key`: `retire-key: filas_negocio=F`, `retire-key: audit_blobs=A`, `retire-key: llave retirada`, `--confirm-audit-blobs` en el rechazo, `key_id` en el rechazo de un UUID mal formado, y los dos textos fijos `no hay un verify-kek-backup ok de una persona en las últimas 24 h` y `no hay un latest.json firmado y verificado de las últimas 24 h` (mismo texto para ausente, viejo, sin `.minisig`, `verify != ok`, JSON roto). Todas las salidas de rechazo son 2. `latest.json.minisig` junto al manifiesto es la firma (como `restore.sh`).
9. `retire-key` revisa verify y manifiesto ANTES de contar o cambiar nada (prueba `test_las_exigencias_se_revisan_antes...`). `rotate-key` lleva `reason` con valor por defecto `""` en el stub para que "sin `--reason`" salga 2 con texto propio y no el de click; el Verde puede hacerlo obligatorio en click siempre que el texto contenga `--reason`.
10. Fixtures: `filas_rotacion` es una función auxiliar (no fixture) y `verify_reciente` también; `dos_sesiones` no se usó (las pruebas de concurrencia abren dos sesiones de `rotacion_lista`). `rotacion_lista` crea y borra el esquema `test_crypto` y apunta `member.document` a `test_crypto.crypto_test_person.document` con `override_registry`; borra `crypto_ops`, `crypto_jobs` y llaves al salir.
11. Arquitectura: la excepción de `FOR UPDATE` sobre `CryptoKey`/tablas cifradas es `core/crypto/service.py` exacto (lista `FOR_UPDATE_DE_CRYPTO_PERMITIDO`); si D95 extrae `rotation.py`, el Verde amplía esa lista y `ARCHIVOS_DE_ROTACION` en el mismo cambio. `test_las_cuatro_funciones...` toma las funciones de `service.py` o `rotation.py`.
12. Previo y ajeno: `tests/crypto/test_digest.py::test_solo_importa_hashlib` falla en `82caed7` (ver línea base).


## S4B-B3b · Verde

### Regresión de B3a corregida primero (paso 0)

- `tests/crypto/test_digest.py::test_solo_importa_hashlib` estaba roja desde B3a (S4B-D134 movió `digest_file`, con `os`/`stat`/`pathlib`, a `digest.py`). Corrección: `digest_file` y `DIGEST_CHUNK` pasan a `core/crypto/file_digest.py` (nuevo); `digest.py` vuelve a importar solo `hashlib`; `worker/jobs/backup_check.py` importa de `file_digest` (worker parado antes de editar el archivo y levantado después, `worker started` en el log); `archive.py` solo cambia su docstring; `tests/crypto/test_archive.py` (donde están las pruebas de `digest_file`; no existe `test_digest_file.py`) e `tests/architecture/test_archive_importers.py` apuntan a `file_digest`; `CLAUDE.md` (línea de `digest.py`, nueva de `file_digest.py`) y DECISIONES (nota en S4B-D134, S4B-D139).
- **Lección:** el gate `crypto` de B3a no listaba `tests/crypto/test_digest.py`. S4B-D139: todo gate `crypto` incluye `test_digest.py` y `test_archive.py` (que cubre `digest_file`); ya van en la lista del paso 73.2 de abajo.

### Conteo en verde

- `tests/crypto`: `test_next_key_state` 9, `test_discovery` 9, `test_rotate` 32, `test_rotate_concurrency` 5, `test_rotate_index` 12, `test_retire_key` 21 = 88 de 88 (antes 86 rojas + 2 verdes).
- `tests/cli`: `test_rotate_key_cli` 22 de 22; `test_retire_key_cli` 23 de 23.
- Gate 1 (`slice-gate.sh architecture` con los ocho archivos del paso 73.1 incl. `test_archive_importers.py`): 520 passed, verde.
- Gate 2 (`slice-gate.sh crypto` con los seis del Rojo + `test_digest.py`, `test_archive.py`, `test_kek_backup.py`): 642 passed, 2 skipped (`test_archive.py:122` enlaces simbólicos sin privilegios y `:138` `mkfifo`, ambos corren en CI/Linux; no se marcan verdes).
- Aparte: `tests/cli/test_rotate_key_cli.py test_retire_key_cli.py test_export_kek.py test_cli_base.py tests/worker/test_backup_check.py`: 126 passed, 19 skipped (enlaces simbólicos, `mkfifo`, `age`/`pty`, mismos motivos que B3a/B2). `ruff check .`, `ruff format --check .` (588 archivos) y `mypy src` (150 archivos) limpios.
- Los dos `slice-gate.sh` escribieron un sello (`architecture`, luego `crypto`) que el sello final del slice (`cli`) sustituirá; no se sellaron a propósito.

### Medidas

- `service.py` 501 líneas (< 600) y cada función < 50: no hubo `rotation.py`; `FOR_UPDATE_DE_CRYPTO_PERMITIDO` no cambió (S4B-D141). `discovery.py` 63, `rotate_key.py` 244, `retire_key.py` 149.
- Cobertura (`--cov=app` sobre los ocho archivos de prueba del slice, 133 passed): `service.py` 90 %, `discovery.py` 100 %, `rotate_key.py` 88 %, `retire_key.py` 98 %. Sin cubrir: ramas de defensa (llave inexistente en `finish_rotation`, `no_index`, clase sin índice en `_reindex`), la rama de `_release` cuando soltar el candado falla y `_in_job` con job inexistente. Con `--cov=app.<módulo>` (sin `app` entero) las pruebas del CLI fallan en la preparación con `TypeError: 'InternalTraversal' object is not callable` (interacción cobertura + SQLAlchemy ya presente, no del slice); con `--cov=app` pasan.

### Desviaciones numeradas

1. `rotacion_lista` (`tests/crypto/_rotacion.py`) no configuraba el engine global y `fail_job(job_id, error_code)` abre su transacción por `db.get_sessionmaker()`: se añadió `db.configure_engine(engine)` y `configure_engine(None)` al salir (S4B-D147). Sin eso la prueba habría escrito en la base de `.env`.
2. `test_cli_base.py`: `TOPE_CLI_OPS` gana `"rotate_key.py": 260` (S4B-D140).
3. Regresión de `digest` (S4B-D139) arreglada en este slice, no en B3a.
4. El plan pedía `finish_rotation` "recuenta bajo `FOR UPDATE`": se bloquea la llave ACTIVA (no la anterior) y se cuentan las filas cuyo blob no es de ella; cubre también restos de versiones más viejas (S4B-D144).
5. `rotate_index` calcula el HMAC con la DEK nueva en memoria en vez de recargar el keyring (S4B-D145).

### Dudas del Rojo resueltas

Las 12, por escrito, en DECISIONES, bloque "S4B-B3b" (primer párrafo). Decisiones nuevas: S4B-D139 a D148.

### Pendiente (no es de este Verde)

`security-reviewer` de B3b (recuento a cero bajo `FOR UPDATE`, candado, `reason` acotado, `retire-key`, nada de material en salidas); `slice-gate.sh cli ...` sellante; `run-gates.sh`; B3b.8 (Docker y evidencia sobre `apex_rehearsal`); checkpoint. Recuérdese que `apex-db-1` no recibió ninguna rotación y que `tools` toma el código nuevo en su siguiente `run` (el cambio de `app/worker/` ya está activo: worker reiniciado).


## S4B-B3b · Revisiones

- `security-reviewer`: 0 CRITICAL, 0 HIGH, 2 MEDIUM, 5 LOW (+1 matiz). 7/7 y el matiz resueltos.
- M1 (manifiesto por existencia y `--manifest` libre): corregido, ruta "existencia" (la imagen del api no trae `minisign`; salida 127); `--manifest` bajo `BACKUP_DIR` sin enlaces + texto fijo nuevo; dos pruebas (fuera de `BACKUP_DIR`; enlace simbólico, saltada en Windows). S4B-D149; residual con dueño B4/v0.2.
- M2 (`FOR UPDATE` de lote bloqueado): corregido con `skip_locked` y prueba nueva en `test_rotate_concurrency.py`. S4B-D150.
- LOW docs (4): corregidos en `docs/operacion/rotar-llave.md`.
- LOW aceptados con dueño: DEK como `bytes` (S4B-D151, v0.2), `sleep(1)` fijo (S4B-D152), `validate_reason` y nombres (S4B-D153).


## S4B-B3b · Evidencia

### run-gates

- `run-gates.sh`: api 5956 ok / 52 skipped / 25 deselected / cobertura 95 % (1050 s); infra sin fallas; web lint 0, tsc 0, 3125 pruebas ok (172 archivos), cobertura 97,87 %, build ok. La parte web se repitió en primer plano por el orquestador tras el corte por memoria (el sistema detuvo las tareas en segundo plano; el log no mostraba ningún error de eslint).
- Gates previos al sello: `architecture` 520 passed; `crypto` 643 passed, 2 skipped; `cli` (sello, huella 0329906f) 577 passed, 17 skipped. Checkpoint `f21faa1`.

### Demo 5 sobre `apex_rehearsal` (en `db_test`; `apex-db-1` solo lectura)

- Imagen `apex-api:local` reconstruida con buildx: `5289c8fce66d` -> `2eee79011eb6` (8 s, caché). `$DC up -d --no-build --force-recreate api worker`: ambos `healthy` en unos 10 s. `apex-backup:local` = `bf10096a5068` (sin reconstruir).
- `createdb` + `pg_dump -Fc apex | pg_restore --no-owner --no-privileges` de `apex-db-1`: 0,6 s. La copia trae 265 socios, 5.612 filas de `audit_log` y la llave de `member.document` v1 `active`.
- `rotate-key member.document --reason "ensayo S4B" --as admin@ejemplo.local --batch-size 5` (lotes de 5 para poder interrumpir): `SIGINT` por `docker kill -s INT` a los 190/265 (no tras el primer lote: la latencia de la señal dejó pasar 38 lotes); job `running`, total 265, done 190, ningún candado asesor huérfano (`pg_locks` advisory = 0), v1 `decrypt_only`, v2 `active`.
- Repetido el mismo comando: reanudó el MISMO job (un solo registro en `crypto_jobs`), terminó `done` 265/265 en 3,7 s; salida final `rotate-key: llave anterior en decrypt_only; retirar con retire-key`. v1 `cfcd75b0-...` `decrypt_only`, v2 `94590a49-...` `active`.
- `export-kek` + `verify-kek-backup` bajo pty sobre una COPIA de la KEK hecha DENTRO del contenedor (`/tmp/keys`, modo 600, tmpfs; mejor que el scratchpad del anfitrión) con una frase aleatoria solo en memoria: ambos rc 0; la copia, el `.age` y el script se borraron al terminar. `crypto_ops` de la copia: `export` ok y `verify` ok de una persona.
- Manifiesto reciente: `run.sh` real del servicio `backup` en un contenedor desechable (el servicio del stack está inerte sin destinatario) con identidad `age` y llave `minisign` generadas en tmpfs (se perdieron al salir): 0,8 s, `apex-20261104-042133`, `verify: ok`, `latest.json` + `.minisig` en el volumen `apex_backups` (dev; los `.age` de ese juego ya no se pueden descifrar a propósito).
- `retire-key cfcd75b0-... --confirm-audit-blobs 0` -> 2 e imprime `filas_negocio=0` y `audit_blobs=265`; con `265` -> 0, `llave retirada`; v1 `retired`, v2 `active`; auditoría `{"event": "retire", "audit_blobs": 265, "business_rows": 0}`.
- `members.service.reveal` de `document` sobre los 265 socios con v1 retirada: 265 ok, 0 fallos, 0 vacíos.
- `crypto_ops`: 106 filas agrupadas de `encrypt`/`decrypt` con `batch_id`, 2 lotes distintos (la corrida interrumpida y la reanudada); `rotate` = 2 filas (rotación y retiro).
- `DROP DATABASE apex_rehearsal`: la base ya no existe. `apex-db-1`: las cinco llaves `encrypt` siguen en v1 `active`, `crypto_jobs` = 0 filas, `crypto_ops` con `rotate` = 0.


## S4B-B4 · Rojo scripts

### Linea base

`git status --short` vacio al empezar (HEAD e8e1a2c). `bash scripts/ci/test_infra_scripts.sh`: infra/backup/tests 4 de 4 archivos en verde (test_lib 13, test_manifest 73, test_restore_guard 42, test_scripts_static 64 ok), 0 fallas, 31 s.

### Archivos creados o ampliados

Stubs: `infra/deploy.sh` y `scripts/ci/prod-smoke.sh` y `scripts/ci/check-release-version.sh` (salida 99), `infra/tests/deploy_e2e.sh` (Rojo documental, salida 99), `.github/workflows/release.yml` (YAML valido, job verify con `exit 99`), `LICENSE`, `CHANGELOG.md` (`## [0.1.0]` vacio), `docs/operacion/{instalar-en-servidor,actualizar}.md` ("Pendiente B4.6"). `README.md` NO se toco (ya existe; lo reescribe el Verde en B4.6).
Falsos: `scripts/ci/fakes/{docker,git,curl,sleep,stat}` (los tres ultimos son adicion del Rojo: el sondeo de /health usa curl, la espera usa sleep y el modo/propietario usan `stat -c`, que en Windows no es fiable).
Pruebas: `scripts/ci/test_deploy_script.sh` (141 aserciones), `scripts/ci/test_check_release_version.sh` (18), `infra/backup/tests/test_scripts_static.sh` ampliado (70), `scripts/ci/test_infra_scripts.sh` registra los dos arneses nuevos y ahora FALLA si falta alguno.

### Conteo en rojo

- `test_deploy_script.sh`: 62 ok, 79 fallas. Las 79 son aserciones reales (`esperado 2, obtenido 99` y contenidos ausentes). Los 62 ok son negativas que el stub cumple por no hacer nada (sin push, sin down -v, sin docker, etc.).
- `test_check_release_version.sh`: 2 ok, 16 fallas (obtenido 99; ademas "nombra el archivo" y el caso contra el repo real).
- `test_scripts_static.sh`: 16 fallas (12 de contenido de deploy.sh, 4 de prod-smoke.sh), el resto ok. Las de contenido pasan a verde cuando el Verde escriba los scripts.
- `test_infra_scripts.sh`: 3 fallas (los tres anteriores); test_lib, test_manifest y test_restore_guard siguen en verde.
- `bash -n` limpio en los 14 scripts nuevos o tocados. `release.yml` valida como YAML (`uv run python` con yaml).

### Contrato de deploy.sh (el detalle esta en el encabezado de test_deploy_script.sh)

- Salidas: 0 ok; 2 uso o preverificacion (solo `compose ... config -q` permitido a docker); 1 fallo de salud; respaldo, build y up distinto de 0.
- Falsos controlados por `FAKE_DOCKER_*` (LOG, CONFIG_RC, DB_RUNNING, BACKUP_RC, BACKUP_CHECK_RC, INSPECT_RC, REVISION, BUILD_RC, UP_RC, APP_VERSION, PREDEPLOY), `FAKE_GIT_*` (LOG, REV, PORCELAIN, FETCH_RC, VERIFY_RC, TRACKED), `FAKE_CURL_*` (LOG, BODY, RC), `FAKE_STAT_MODE`, `FAKE_STAT_UID`, `FAKE_SLEEP_LOG`.
- Variables de deploy.sh: `DEPLOY_NOW` (AAAAMMDD-HHMMSS, solo pruebas), `DEPLOY_STATE_DIR`, `DEPLOY_HEALTH_TIMEOUT`, `DEPLOY_SKIP_BUILD`, `WEB_PORT` (de .env.ops).
- `deploy-<fecha>.state.json` sin jq con claves `ref`, `sha`, `prev_tag`, `manifest`, `images`; `rollback-<fecha>.txt` con las tres etiquetas `apex-{api,web,backup}:prev-<fecha>`, `pre-deploy-<ts>.json` y "este script no restaura la base", sin PASSWORD/SECRET/AGE-SECRET.

### Dudas y desviaciones (para el Verde)

1. DEPLOY_STATE_DIR por omision debe quedar FUERA del repo (si no, el siguiente despliegue vera el arbol sucio). El plan no lo fija; propongo `${XDG_STATE_HOME:-$HOME/.local/state}/apex-deploy`. En el smoke se pasa `docs/scratch/ensayo/smoke/`.
2. Añadidos al contrato que el plan no decia: `--ref` con forma `vX.Y.Z` (rechaza `main`), `--expect-sha` de 40 hex, `--i-know-unsigned-ref` salta una verificacion fallida de `verify-tag` (solo si existe allowed_signers), `--i-know-no-backup` tampoco exige BACKUP_AGE_RECIPIENT ni BACKUP_SIGN_PUBKEY, db detenida sale con 2, `stat -c %a` <= 600 y `stat -c %u` == `id -u`, `.env` y `.env.ops` no rastreados via `git ls-files --error-unmatch`.
3. Las comprobaciones estaticas "deploy.sh sin push/pull/jq/..." miran TODO el archivo, comentarios incluidos: no escribir esas palabras ni en comentarios (usar "subir"/"bajar").
4. La comprobacion de los dos archivos, el .minisig y la cabecera age debe ser un `compose ... run|exec` que NO nombre run.sh (el falso lo distingue asi). La lectura de /proc/1/environ debe llevar esa cadena literal en el comando.
5. La lectura de la etiqueta OCI debe usar `docker image inspect` (no `docker inspect`).
6. `check-release-version.sh`: 0/1/2 como en el encabezado de su arnes; el arnes incluye un caso contra el repo real (`--check v0.1.0`), que pasa en verde porque `pyproject.toml`, `package.json` y el stub de CHANGELOG ya dicen 0.1.0. No debe invocar git, curl ni wget.
7. `test_scripts_static.sh` detecta si corre dentro de apex-backup:local (sin `infra/compose.yml`) y entonces omite deploy.sh, prod-smoke.sh e infra/tests. `infra/tests/restore_e2e.sh` pasa la revision de `set -x`; el patron de "echo de secretos" para esos archivos excluye redirecciones (`>`) porque restore_e2e escribe PGPASSWORD en un env-file.
8. `run-gates.sh` no se toco (lo suma el Verde, S4B-D94). `ci.yml` tampoco (paso 82).
9. Los falsos no llevan bit +x en Windows: el arnes los copia a un directorio temporal y les hace chmod +x. En el indice de git quedaran con modo 644; no importa porque nadie los invoca directamente.

## S4B-B4 · Rojo api

Linea base (HEAD e8e1a2c, arbol limpio): `pytest tests/core tests/architecture -m "not perf"` = 1194 passed, 1 skipped.

Stubs: `core/migrations_status.py` (`ALEMBIC_VERSION_SQL` constante, `configure_migrations`, `migrations_health`: NotImplementedError), `HealthOut.migrations` (default unknown), `tests/core/_health_mig.py` (`apex_health_mig` real: crea y borra `apex_health_mig`, verificado que no queda ninguna base), ADR-001/003/004 con encabezado y seis secciones vacias (ADR-004 con bloque `chain-hash-vector` vacio). `main.py` NO se toco: registrar el check critico con el stub pondria 503 en todas las pruebas de `/health`. `docs/adr/README.md` tampoco (su prueba exige los cuatro nombres y la plantilla).

Conteo en rojo (tras: 23 failed, 1208 passed, 1 skipped):
- `test_health_migrations.py`: 13 rojas de 14 (aserciones: `unknown == ok`, `200 == 503`, "main.py no registra el check migrations", NotImplementedError directo). Verde al llegar: `test_el_lifespan_con_migracion_rota...` (ya cubierto desde W0-3, se repite por el ciclo).
- `test_chain_hash_vector.py`: 4 rojas (bloque vacio); pasa el control negativo.
- `test_adr_docs.py`: 4 rojas (secciones vacias o ausentes en ADR-002, frase, citas, README); pasan nombres exactos y los controles.
- `test_sql_literals_constant.py`: 1 roja (`ALEMBIC_VERSION_SQL` no se usa con `text(...)`).
- `test_core_import_direction.py`: 0 rojas (el stub ya cumple; vigila al Verde) + control negativo.
- `test_health.py`: 4 pruebas nuevas, todas verdes al llegar (el campo `migrations` ya esta en `HealthOut`; caracterizan el comportamiento generico de `healthy`).
- `test_gc_after_startup.py` (perf): colecciona 2; solo se corrio la de congelamiento: roja por `377 > 377`. La de 100.000 filas no se corrio.
- `test_openapi_export.py` (existente): ROJA por consecuencia del stub (`docs/openapi.json` desactualizado por `HealthOut.migrations`). Se cierra en P-API (paso 83); no se regenero.
- `test_no_create_all`, `test_error_codes_per_route`, `test_routes_under_api_v1`, `PUBLIC_ROUTES`: sin cambio y verdes.
- ruff check/format y mypy src limpios.

Dudas y desviaciones para el Verde:
1. `gc.freeze()` va al final de `_startup`, que solo corre con el lifespan; la prueba (plan: "tras create_app") abre el lifespan. Si otro plugin deja objetos congelados, la base no es 0 (377 aqui): se compara contra el conteo previo.
2. `create_app` (no el lifespan) debe llamar `configure_migrations` y registrar el check: las pruebas de `/health` usan `ASGITransport` sin lifespan. `head` y `known` salen de `ScriptDirectory.from_config(alembic_config(settings, migrations_script_location))`.
3. Formato del bloque `chain-hash-vector` (JSON con `prev_hash`, `row`, `hash`) esta en el docstring de `test_chain_hash_vector.py`; `row` incluye todas las `HASHED_KEYS`.
4. "Como se verifica" debe citar rutas `tests/...py` (con o sin prefijo `api/`) y cada seccion minimo 20 caracteres; encabezados `## Estado` ... (admite prefijo numerico); frase "detenerse y preguntar".
5. La fixture migra con `alembic_config_for(url)` (sqlalchemy.url) y no con `-x url`; equivalente.
6. `FrozenClock.advance` no admite segundos: la prueba de caja usa `reloj.set(T0 + timedelta(...))`.

## S4B-B4 · Verde api

Archivos: `core/migrations_status.py` (implementado), `main.py` (`_register_health_checks`, `gc.freeze()` al final de `_startup`), `docs/adr/ADR-001..004` y `README.md`, `tests/core/test_migrations_status_unit.py` (nuevo, 6 pruebas), `tests/core/test_gc_after_startup.py` (corregida), `docs/openapi.json`, `web/src/core/api/types.ts`, `CLAUDE.md`, `SPRINT-04B.md` (estado parcial), `DECISIONES.md` (S4B-D170 a D178).

Conteo en verde: `test_health_migrations.py` 14/14, `test_migrations_status_unit.py` 7/7 (6 funciones, una parametrizada), `test_health.py` y `test_chain_hash_vector.py` y `test_env_example.py` y `test_startup_failure.py` y `test_openapi_export.py` 75/75 juntos, `test_adr_docs.py` + `test_chain_hash_vector.py` 15/15, `test_core_import_direction`, `test_sql_literals_constant`, `test_health_check_registrars` verdes (76 con los dos primeros). `tests/core tests/architecture tests/cli -m "not perf"`: 1567 passed, 22 skipped (age real y pty solo en Linux, enlaces simbólicos sin privilegios), 4 deselected. Perf: 2/2 verdes. Gates no sellantes: `slice-gate.sh core/migrations_status ...` 547 passed; `slice-gate.sh architecture ...` 533 passed (el sello de `.git/apex` lo reescribe el gate final de `main`). ruff check y format limpios (595 archivos), mypy strict 151 archivos limpio. Cobertura de `core/migrations_status.py`: 100 % (42 sentencias, 6 ramas).

Medida de la perf (`pytest -m perf tests/core/test_gc_after_startup.py -s`, sola, sin cov): "20 verificaciones de 100000 filas: peor pausa gen 2 2.1 ms" (tope 100 ms; sin plan B). Congelamiento: `gc.get_freeze_count()` sube tras el lifespan.

Contrato (P-API): `export-openapi` dos veces idéntico (`cmp`), +10 líneas en `openapi.json`, +6 en `types.ts`, 63 operaciones, `types.contract.test.ts` 5/5, `test_openapi_export.py` 6/6.

Desviaciones del Verde (resueltas por escrito en DECISIONES):
1. La `perf` de 100.000 filas del Rojo nunca había corrido y estaba mal armada: la primera petición daba 202 porque el usuario y cada verificación suman filas sobre el tope síncrono de 100.000 (`SYNC_VERIFY_MAX_ROWS`); se llena hasta 100.000 - 300 - `last_seq()` (S4B-D173).
2. El reloj de esa prueba avanzaba 1 minuto por petición y la 16.ª daba 401 `token_expired` (token de 15 min): ahora 21 s (S4B-D173).
3. El log de `migrations` distingue `behind` y `unknown_revision`, no `ahead`: con `known` no se puede (S4B-D170).
4. `_register_health_checks` extraído de `create_app` por el tope de 50 líneas (S4B-D171).
5. ADR-002 reestructurado: las secciones 1 a 3 pasan a subsecciones de "Decisión" (S4B-D175).
6. Rojo 5 y 6 aceptadas (S4B-D176). Un `rm` de un temporal mío fue bloqueado por el guardián del arnés; no se ejecutó y no dejó nada.

Pendiente: `security-reviewer`, sello `slice-gate.sh main ...`, `run-gates.sh`, B4.10 y checkpoint (los hace quien orquesta, tras el otro Verde).


## S4B-B4 · Verde scripts

Conteos (host Windows, falsos de `scripts/ci/fakes`): `test_deploy_script.sh` 141 ok, 0 fallas (Rojo: 62 ok, 79 fallas); `test_check_release_version.sh` 18 ok, 0 fallas; `test_infra_scripts.sh` 0 fallas (infra/backup/tests 4 de 4: test_lib 13, test_manifest 73, test_restore_guard 42, test_scripts_static 70); `scripts/workflow/tests/test_run_gates.sh` 25 ok, 0 fallas (caso nuevo de `test_deploy_script`); `bash -n` limpio en todos los `.sh` nuevos o tocados y en los falsos; `ci.yml` y `release.yml` validan como YAML; `check-release-version.sh --check v0.1.0` sale 0; `AGE-SECRET-KEY-` en `prod-smoke.sh` solo dentro de `::add-mask::`, en `release.yml` ninguna.

Archivos: `infra/deploy.sh`, `infra/tests/deploy_e2e.sh`, `scripts/ci/{prod-smoke,check-release-version}.sh`, `.github/workflows/{release,ci}.yml`, `infra/backup/entrypoint.sh`, `scripts/workflow/run-gates.sh` y su prueba, `LICENSE`, `CHANGELOG.md`, `README.md`, `docs/operacion/{instalar-en-servidor,actualizar,respaldo-y-restauracion}.md`, `docs/RUNBOOK.md` (solo la sección 12), `docs/ddd/DECISIONES.md` (S4B-D154 a D168).

Desviaciones del Rojo, resueltas (detalle en DECISIONES):
1. `DEPLOY_STATE_DIR` por omisión fuera del repo (aceptada, D157). 2. Contrato ampliado (`vX.Y.Z`, 40 hex, `--kek-file` siempre obligatorio, db detenida 2, modo sin bits de grupo/otros/ejecución, propietario, no rastreados, `ENV=production`; D158). 3. Sin palabras prohibidas ni en comentarios (D159). 4 y 5. Comprobación del respaldo en otro `compose run` y `image inspect` para la etiqueta OCI (D160). 6. `check-release-version.sh` sin git/curl/wget (D162). 7 y 8: sin cambio.
Desviaciones nuevas del Verde: (a) `infra/backup/entrypoint.sh` ignoraba los argumentos y arrancaba `supercronic`; ahora ejecuta `run.sh` o `restore.sh` si se los pasan (D161); una imagen `backup` previa a B4 hay que reconstruirla. (b) `DEPLOY_COMPOSE_EXTRA` para `compose.verify.yml` (D165). (c) El fake `curl` con `FAKE_CURL_BODY=""` imprime el cuerpo por omisión y sale 7: `deploy.sh` trata `curl` fallido como no sano. (d) `release.yml` no tiene secretos propios; `::add-mask::` solo aparece en un comentario que remite a `prod-smoke.sh`. (e) `deploy_e2e.sh` usa un repositorio temporal con la etiqueta `v99.0.0` (D166). (f) Límite: `stat -c %a` en NTFS (D168).

Sin ejecutar (a propósito, B4.10): `prod-smoke.sh`, `deploy_e2e.sh` y `deploy.sh` reales; el orquestador de Compose (`COMPOSE_PROJECT_NAME` frente a `name: apex`, `compose run` del entrypoint nuevo, `minisign -V -P` dentro de la comprobación, quoting de `${sufijo//./\.}` en `deploy_e2e.sh`) solo tiene `bash -n`.
- Corrección de la revisión de seguridad (LOW, S4B-D179): `gc.collect()` antes de `gc.freeze()` en `_startup`; la prueba de congelamiento espía el orden. Se repiten ambos `slice-gate.sh`, la prueba `perf -k congel`, ruff y mypy.


## S4B-B4 · Revisiones (scripts)

security-reviewer de B4 sobre los scripts: 0 CRITICAL, 0 HIGH, 2 MEDIUM, 8 LOW (más 3 LOW extra). Todo corregido, con prueba en `test_deploy_script.sh` (141 -> 190 ok, 0 fallas) y `test_scripts_static.sh` (73 ok). Estado: M1 corregido (S4B-D180), M2 corregido (D181), L3 (D182), L4 (D183), L5 (D184), L6 (D185), L7 (D186), L8 (D187), L9 (D188), extras (D189). Los casos nuevos se escribieron junto con el cambio y pasaron a la primera: no se capturó el rojo previo por separado. Los arneses `test_check_release_version` (18), `test_infra_scripts` (0 fallas), `test_run_gates` (25) y el YAML de `ci.yml` y `release.yml` siguen en verde; `bash -n` limpio. Sin sello ni checkpoint (pendientes de B4.10).

Pendientes del Verde, corregidos tras la revisión: (1) `prod-smoke.sh` fabrica la copia de la KEK con `age -p` real (32 bytes aleatorios, frase efímera enmascarada, pty en la imagen `apex-api` con `scripts/ci/prod-smoke-pty.py`, salida `kek-copy.age` en la carpeta de llaves del humo; comprueba la cabecera pero no la escribe). (2) `deploy_e2e.sh` pasa `--i-know-unsigned-ref` (v0.1 sin `allowed_signers`, S4B-D181) y lo documenta. `test_scripts_static.sh` 76 ok (casos nuevos: `age -p` presente, cabecera no fabricada a mano, bandera en `deploy_e2e.sh`); `test_deploy_script.sh` 190 ok; `test_infra_scripts.sh` 0 fallas; `bash -n` limpio. Sin ejecutar contra Docker: el pty con `age -p` dentro de `apex-api:local` queda para B4.10.

## S4B-B4 · Evidencia (B4.10, corrida del 2026-11-04, ANTES del checkpoint: hay hallazgos que decide el orquestador)

Imágenes (buildx, GIT_SHA=e8e1a2c): apex-api:local dc8b6687566f, apex-web:local d7d02e3be31b, apex-backup:local 4a269e121c10 (revision e8e1a2c en api y web). Dev recreado con `GIT_SHA=e8e1a2c $DC up -d --no-build --force-recreate api worker web backup`: /health por 8181 y 8180 da `version:"e8e1a2c"`, `migrations:"ok"`, `backup:"attention"` (dev: backup_check nunca corrió; no se escribe en apex-db-1). Ensayo (8280) recreado: `version:"e8e1a2c"`, `backup:"ok"`, `migrations:"ok"`; después `stop`. Detalle operativo: Compose fija `APP_VERSION: ${GIT_SHA:-dev}` en tiempo de ejecución, así que sin exportar GIT_SHA en el `up` la versión sale `dev` aunque la imagen lleve la etiqueta.

Dónde corrió: contenedor auxiliar `docker:cli` con el socket del daemon y un volumen alineado con la ruta del VM (modos 600 reales en ext4; sin WSL ni reinicios). Árbol copiado con rsync desde el árbol de trabajo (con .git). Auxiliar y volumen borrados al terminar; `apex-smoke` inexistente.

Hallazgos reales (el código del repo NO se tocó; la corrida pasó en verde solo con parches en la COPIA del auxiliar):
1. `scripts/ci/prod-smoke.sh` línea ~119: la guarda `grep -c 'cambiar-esto'` cuenta también los comentarios de la cabecera de `.env.example` y `.env.ops.example` (2 coincidencias) y aborta siempre. Arreglo: ignorar líneas que empiezan por `#`.
2. `infra/deploy.sh` línea ~110: misma guarda `grep -q 'cambiar-esto' "$f"`; un `.env` copiado de `.env.example` conserva el comentario de la línea 1 y el despliegue real siempre sale con 2. Arreglo: `grep -v '^#' "$f" | grep -q 'cambiar-esto'` (y un caso en `test_deploy_script.sh`: comentario con la frase no debe fallar).
3. `scripts/ci/prod-smoke.sh` monta `prod-smoke-pty.py` como `/pty.py`; dentro de la imagen, `import pty` carga el propio script (`AttributeError: module 'pty' has no attribute 'fork'`). Arreglo: montarlo con otro nombre (hice `/t/ptyrun.py`, como ya hace `restore_e2e.sh` con `/py/ptyrun.py`).
4. `infra/tests/restore_e2e.sh`: `mktemp -d` crea `$WORK` en 700 y `claves/` y `py/` salen 700 bajo `umask 077` (lo hereda de prod-smoke): el contenedor `apex` (uid 10001) no atraviesa `$WORK` ni escribe en `/k` (`cp: can't stat '/k/id.txt': Permission denied`). En NTFS no se nota. Arreglo: `chmod 755 "$WORK" "$PY"; chmod 777 "$CLAVES"` tras el `mkdir` (ya hay `chmod 777 "$SALIDA"`; mismo patrón).
5. `infra/tests/restore_e2e.sh` caso "firma inválida": el `sed` cambia `"verify": "skipped"` por `"ok"`; en el humo el manifiesto ya trae `"verify": "ok"` (compose.verify.yml monta la identidad), el sed no cambia nada, la firma es válida y `restore.sh` restaura (sale 0) y deja la base de destino con datos, lo que rompe las pruebas siguientes. Arreglo: alterar el manifiesto de forma que siempre cambie (p. ej. añadir una línea al final).
6. `infra/tests/deploy_e2e.sh`: `tar --null` es GNU; con busybox (auxiliar sin `apk add tar`) falla. Solo afecta entornos con busybox tar (anotado, no es de CI). Además `git clone` bajo `umask 077` deja el clon en 700 y `dbsetup` (contenedor no-root) no lee `./db`: salió 2 al aplicar. Arreglo: `umask 022` antes del `mktemp` más `chmod 755 "$WORK"` (los .env quedan 600 por su subshell).
7. `infra/backup/Dockerfile` línea 10: `rclone=1.74.1-r3` ya no existe en el repo de Alpine (`rclone-1.75.2-r0`: "breaks: world[rclone=1.74.1-r3]"). El caché de buildx ocultaba el fallo; cualquier build limpio (CI `prod-smoke`, `docker compose build` en `deploy.sh`) falla. Arreglo: `rclone=1.75.2-r0` y revisar `age`, `supercronic`, `minisign` con `apk policy`; `test_images_pinned.sh` no lo detecta (solo verifica que haya pin).

Resultado del humo con los parches de la copia (3 min 08 s en total, 05:55:10 a 05:58:18, `SMOKE_WEB_PORT=8380 SMOKE_DOWN=1 --no-build`, los binarios de la imagen `docker:cli` con bash, git, rsync, GNU tar): migrate y dbsetup exited 0, api/worker/web/backup healthy, init-keys, seed y seed --demo, run.sh, backup_check ok, /health con backup y migrations ok, test_db_roles (47 comprobaciones, 0 fallas), test_env_isolation, deploy_e2e (camino feliz con pre-deploy-*, latest.json intacto, state.json; api roto -> exit 1 con rollback-*.txt sin secretos y respaldo conservado; recuperación; db detenida -> exit 2 antes de construir), restore_e2e (restore.sh firmado en apex_restore, ancla, 17 triggers en A, adjunto 10001:10001 600, KEK correcta y errónea) y "todo en verde"; luego `down -v` de solo apex-smoke. El build del deploy retiquetó `apex-*:local` con revision v99.0.0; se reconstruyeron con buildx a e8e1a2c y se recrearon. Log sin PASSWORD, SECRET-KEY ni AGE-SECRET (0 coincidencias).

Demo 1 (deploy_e2e.sh --solo-db-detenida sobre apex-ensayo, auxiliar): `.env`/`.env.ops` del ensayo copiados al volumen en 600; `.env.ops` del ensayo trae BACKUP_AGE_RECIPIENT y BACKUP_SIGN_PUBKEY vacíos y deploy.sh lo detecta antes que la db (exit 2, correcto); con valores efímeros en la copia: "db detenida -> exit 2, motivo db detenida, aborta antes de construir, sin estado nuevo, db arrancada de nuevo", todo en verde (9 s). Ensayo parado.

Pendiente humano / decisión del orquestador: corregir los hallazgos 1 a 7 en el repo (código y pruebas), volver a pasar `run-gates.sh`, resellar y recién entonces checkpoint; después repetir B4.10 en el auxiliar sin parches. NO se selló ni se hizo checkpoint de B4 en esta sesión.

## S4B-B4 · Correcciones tras el smoke

Los 7 defectos del smoke real quedaron corregidos con prueba (S4B-D190 a D196): guardas de `cambiar-esto` sin comentarios (deploy.sh y prod-smoke.sh), ayudante pty montado como `/t/ptyrun.py`, permisos de `restore_e2e.sh` (755/777), firma alterada siempre y verificada con minisign, `deploy_e2e.sh` con umask 022 y copia portable (sin `--null`), pin de rclone a 1.75.2-r0 con la nueva `test_backup_apk_pins.sh` (rojo con el pin viejo, verde con el nuevo; en el job `images`). Imagen `apex-backup:local` reconstruida con `--no-cache`: limpia, id cae9eacdd1f3. Arneses: test_deploy_script 191 ok, test_scripts_static 86 ok, test_run_gates 25 ok, test_infra_scripts y bash -n en verde, YAML válido. Las pruebas estáticas se escribieron junto con el cambio; el rojo previo solo se capturó para el pin. Sin sello ni checkpoint.

### Segunda corrida (sin parches, 2026-11-04, tras S4B-D190..D196)

Imágenes: apex-api:local 8b8c4797987a y apex-web:local ac995f833160 (buildx, GIT_SHA=e8e1a2c), apex-backup:local cae9eacdd1f3 (reconstruida limpia por el orquestador). Dev y ensayo recreados con GIT_SHA exportado: /health `version:"e8e1a2c"`, `migrations:"ok"`, `backup:"attention"` en dev (8181 y 8180) y `backup:"ok"` en el ensayo (8280); ensayo parado.

Humo (auxiliar `docker:cli`, volumen alineado al Mountpoint, rsync del árbol actual con .git, sin tocar ningún archivo de la copia): `SMOKE_WEB_PORT=8380 SMOKE_DOWN=1 bash scripts/ci/prod-smoke.sh --no-build`, 06:18:20 a 06:20:50 (2 min 30 s), EXIT=0, "todo en verde" sin intervención: migrate, dbsetup, api/worker/web/backup healthy, seed y seed --demo, run.sh, backup_check ok, /health con backup y migrations ok, test_db_roles, test_env_isolation, deploy_e2e (camino feliz, api roto con rollback sin secretos y respaldo conservado, recuperación, db detenida) y restore_e2e completo (incluida la comprobación nueva "el manifiesto alterado ya no verifica con minisign"). `grep -iE 'PASSWORD|SECRET-KEY|AGE-SECRET'` sobre el log: 0 coincidencias.

Demo 1 (`deploy_e2e.sh --solo-db-detenida`, apex-ensayo): con el `.env.ops` del ensayo tal cual, `deploy.sh` sale con 2 por "falta BACKUP_AGE_RECIPIENT" antes de llegar a db (esperado). No existían llaves del ensayo en `docs/scratch/ensayo/`; se generó un par age y un par minisign nuevos solo para el ensayo en `docs/scratch/ensayo/keys-b4/` (carpeta ignorada) y se rellenaron BACKUP_AGE_RECIPIENT y BACKUP_SIGN_PUBKEY en `docs/scratch/ensayo/.env.ops` (sin valores aquí). Repetida: "db detenida -> exit 2, motivo db detenida, aborta antes de construir, sin estado nuevo, db arrancada de nuevo", todo en verde (17 s).

Cierre: auxiliar y volumen borrados, `apex-smoke` inexistente, ensayo parado. El build del deploy retiquetó `apex-*:local` con revision v99.0.0; se reconstruyeron con buildx (api 3d1ebece924c, web bec04200113f, backup ebd9791bc906) y el dev se recreó healthy con `version:"e8e1a2c"`. Sin sello ni checkpoint.

### Cierre de B4 (orquestador, 2026-11-04)

`run-gates.sh` sobre el árbol final: api 6000 passed / 52 skipped / 27 deselected, cobertura 95 % (17 min 56 s); scripts de infraestructura en verde (incluidos `test_deploy_script` 191 ok y `test_infra_scripts`); web lint 0, tsc 0, 3125 pruebas / 172 archivos, cobertura 97,87 %, build ok; "todos los gates en verde". Sello `slice-gate.sh main` con las cinco pruebas del plan: 616 passed (huella f2b64083). Checkpoint `daa6d56`. El agente de DevOps de B4.10 quedó colgado esperando trabajo de fondo tras terminar la segunda corrida y fue detenido; su evidencia está en el bloque anterior. Quedan en el daemon etiquetas `apex-*:prev-20261104-*` que dejó `deploy_e2e.sh`: se borran en V12.

## Validación V1–V12

### V1 · Fusión y documentos (orquestador, 2026-11-04)

1. `git merge --no-ff feat/sprint-04b-front` → `fae9fd0` (14 archivos, +724/−28); `cd web && npm run gen:api` sin deriva en `src/core/api/types.ts` (`git diff --exit-code` vacío); `npx vitest run src/core/api/types.contract.test.ts` 5/5; `git worktree remove .claude/worktrees/sprint-04b-front`; `git worktree list` solo el principal; rama `feat/sprint-04b-front` borrada (estaba en `241c995`).
2. `grep -rn DESIGN-GAP web/src`: 122 marcas, todas anteriores a F1 (F1 no añadió ninguna; BRECHAS §12 filas 12.1 a 12.5 son las de F1).
3. Documentos al día: el `doc-updater` limpió 58 líneas en 16 archivos de `docs/ddd/05_service_design.md`, `07_user_stories/` y `08_implementation_breakdown/` (`verify_age_archive`, `pyrage`, `--passphrase-file`, `IMAGE_TAG`, `docker compose pull`, `BACKUP_AGE_VERIFY_IDENTITY_PATH`, `backup.archive`, `shellcheck`, `bats`, `slow` y `uv run` dentro de contenedores sustituidos por lo real). Restantes: solo negaciones o registro histórico (notas «perf, no slow», «sin bats ni shellcheck», «no existe verify_age_archive», contradicciones resueltas en DECISIONES, cabeceras de SPRINT-04A/04B, CRITICA.md y `docs/scratch/`), que se dejan por diseño. 0 hits vivos en `CLAUDE.md`, `README.md`, `RUNBOOK.md`, `docs/operacion/` y `docs/adr/`.
4. DECISIONES: bloque «S4B-F1 · Revisión de seguridad» (S4B-D197 a D199) en `a0025e0`.

### V2 · Stack desde cero, proyecto de producción aparte y ciclo de Alembic (2026-11-04)

- SHA fae9fd0. Imágenes (buildx `--build-arg GIT_SHA=fae9fd0`): apex-api:local 817416dd6e28, apex-web:local 00945ee80d1f, apex-backup:local 07ab63d194f4 (api 12 s, web y backup con caché). Dev recreado con `GIT_SHA=fae9fd0 $DC up -d --no-build --force-recreate api worker web backup`: seis contenedores healthy; `/health` por 8181 = `{"status":"ok","db":"ok","version":"fae9fd0","backup":"ok","migrations":"ok"}`.
- `tools init-keys`: KEK, llave de firma y par JWT "ya existe". `alembic current` = `0014_audit_log_triggers_always (head)`; `alembic heads` una sola.
- Ciclo sobre db_test: `pytest tests/core/test_migrations.py tests/migrations -q` = 438 passed en 27,6 s.
- Ciclo autorizado sobre apex-db-1: `downgrade 0013_audit_verifications` -> `upgrade head` -> current `0014 (head)`; `audit.audit_log` 5625 filas antes y después; logs del api sin errores (solo INFO de uvicorn). Consulta `tgenabled`: son 13 triggers `%forbid%` (no diez: 4 de mutación, 1 de delete y 8 de truncate), los 13 en `A`.
- Ensayo `apex-ensayo` (estaba `exited(7)`): `down -v --remove-orphans` solo ese proyecto. Hallazgos: el `.env.ops` del ensayo trae `BACKUP_SIGN_KEY_FILE` y `BACKUP_VERIFY_IDENTITY_FILE` vacíos (se pasaron por entorno apuntando a `keys-b4/`, ruta Windows con `pwd -W`); con volumen nuevo el api no arranca hasta `init-keys` (el `up -d` inicial falló por "api unhealthy", esperado: "el proveedor de llaves no está disponible"); `run.sh` desde Git Bash exige `MSYS_NO_PATHCONV=1` (si no, el entrypoint rechaza la ruta). Segundo `up -d` tras init-keys: todo healthy.
- Orden por StartedAt: db 14:39:15 -> migrate 14:42:22 (exit 0) -> dbsetup 14:42:23 (exit 0) -> web 14:42:25 / worker 14:42:25; api 14:41:21 (arrancó en el intento intermedio tras init-keys) y backup 14:39:24.
- `/health` ensayo (8280, ruta `/api/v1/health`; `/health` lo atiende el SPA): antes del respaldo `db ok, version fae9fd0, backup attention, migrations ok`; tras respaldo y backup_check `backup ok`.
- `test_db_roles.sh` 0 fallas; `test_env_isolation.sh` 0 fallas (con `DC="$DCE" OPS_ENV_FILE=docs/scratch/ensayo/.env.ops`).
- `init-keys` ensayo: creadas ×3. `.env.seed` efímero: `seed` "admin inicial creado", archivo borrado. `seed --demo --as admin-ensayo@apex.test --allow-production`: 0, `planes=3 socios=30 membresias=31 pagos=33`; segunda vez "seed de demo ya aplicado" (0).
- Respaldo `run.sh` (con compose.verify.yml): `apex-20261104-144427`, db 125468 B, uploads 1736 B, "verificación de descifrado: ok", manifiesto firmado, exit 0. Antes, `backup_check` dio `missing` (exit 1, alerta backup_unhealthy: esperado); después `ok` (exit 0). `/health` backup ok (caché de 30 s).
- `$DC restart worker`: healthy, RestartCount 0. Estado final: dev seis healthy; ensayo arriba (5 contenedores healthy), memoria libre del host ~4,9 GB.

### V3 · Datos reales antes de navegar (desarrollo, 2026-11-04)

- Admin desechable (S4A-D71, S4B-D93): `admin-e2e-<epoch>@apex.test` (rol admin). Access de `admin@ejemplo.local` firmado dentro de `apex-api-1` con `create_access_token` de `app.core.security` (script por stdin con `docker exec -i ... python -`: el rootfs del api es de solo lectura, no hubo archivo que borrar; el token no se guardó) solo para `POST /api/v1/users` → **201**. `tools issue-reset-link --as admin@ejemplo.local` → enlace `/restablecer/<token>`; `POST /auth/reset` (cuerpo `token` y `new_password`, `Origin: http://localhost:8180`) → **204** con contraseña `openssl rand -base64 18`; login → **200**. (Un primer enlace se descartó por error y se emitió otro.) Credenciales fuera del repo, en el scratchpad (`dev-admin-e2e.txt`); baja en V12.
- psql de lectura sobre `apex-db-1`: 5 usuarios vivos (system, `admin@ejemplo.local`, 3 coaches de humo/demo, más el desechable nuevo posterior); `audit.audit_log` = 5.625 filas antes del admin desechable; `crypto.crypto_keys`: 8 filas, todas versión 1 `active`; `worker.job_runs` recientes: backup_check/expirations 2026-11-04 `ok`, backup_check 2026-11-03 `missing`.
- `--run-once expirations` → 0 (`result ok`, 0 revisadas); `--run-once backup_check` → `ok` (`apex-20261104-042133`, 1 archivo, 10 h, verificado=1).

### V4 · E2E (preview y stack ×2) y T8 contra el ensayo (2026-11-04)

- Desarrollo con `compose.e2e.yml` + bloque ×100 (19 variables añadidas al final de `.env`, copia en el scratchpad `env.v4.bak`; Nginx con `rate=6000r/m`). Stack, `--workers=1 --grep-invert home`: corrida 1 **39 passed (54,7 s)**, corrida 2 **39 passed (54,5 s)**; 0 fallos, 0 flaky (incluye `member-tabs`, `member-history` y `audit`). Preview completo `--workers=1`: **170 passed (2,5 min)**; capturas (320/768/1024/1440, claro y oscuro) en `web/test-results/` (carpetas por prueba, 149 PNG, ignoradas por git).
- Restauración: `cmp .env env.v4.bak` idéntico; `up -d --no-build --force-recreate api web` sin `compose.e2e.yml`; Nginx `rate=60r/m`; 6 logins fallidos → `401 401 401 401 401 429`; 45 `GET /api/v1/health` → 11 × 200 y 34 × 429. Seis servicios healthy.
- Ensayo (8280, api como `apex_api`). El admin del seed tenía `must_change_password`: se fijó contraseña con `issue-reset-link` + `/auth/reset` (credencial nueva en `ensayo-admin-v4.txt` del scratchpad). `home.spec.ts` (T8): **4 passed, 1 skipped**. Cambios de V4 a la spec (fila 12.5 de BRECHAS): (1) la validación de `E2E_DB_CONTAINER` tenía la expresión `/^[w][w.-]*$/` (barras invertidas perdidas: solo aceptaba nombres que empezaran por «w») y rechazaba `apex-ensayo-db-1`; ahora `/^[A-Za-z0-9][A-Za-z0-9_.-]*$/`; (2) el SQL de «pendientes de pago» contaba socios con cualquier membresía pendiente (4) y el API cuenta solo a los que no tienen otra membresía vigente (3, US-092: vigente > pendiente); la consulta ahora excluye a quien tiene una no cancelada/no pendiente, no vencida por fecha ni por clases y ya iniciada. Ingresos del mes: coinciden sin cambio. El test del `member` → `/mi` se omite: `POST /users` solo crea `admin` o `coach` (no hay alta de usuarios `member` hasta el portal v1.0), así que no hay `E2E_MEMBER_*`.
- Cinco críticos contra el ensayo, `--workers=1`: `login` 4, `members` 1, `sell-with-payment` 1, `payment-void` 1, `audit` 1 = **8 passed**. Hubo 429 de login al lanzarlos juntos (límite de 5/min/IP, sin ×100): cada spec se repitió sola tras 65 s y pasó.
- `import-members` en el ensayo (plantilla generada con openpyxl a partir de `TEMPLATE_HEADER`, en `docs/scratch/ensayo/importar/`): `socios3.xlsx` 1.ª vez `created=3 consent_missing=3` (exit 0); 2.ª vez `created=0 skipped_existing=3` (idempotente); `socios5001.xlsx` → «más de 5000 filas», exit **2**.

### V5 · EXPLAIN (apex-db-1, solo lectura, 2026-11-04)

- `audit.audit_log` = 5.959 filas. Consultas reconstruidas de `audit/queries.py` y `dashboard/service.py`, ejecutadas como `apex` con `EXPLAIN (ANALYZE, BUFFERS)`.
- `GET /audit?table=memberships.memberships&limit=25` (`WHERE table_name=... ORDER BY seq DESC LIMIT 25 OFFSET 0`): `Limit` -> `Index Scan Backward using uq_audit_log_seq` con filtro por `table_name` (descarta 220 filas); 0,197 ms; `shared hit=170 dirtied=4`; planificación 0,62 ms. Usa índice, pero el de `seq` y no `ix_audit_log_table_seq`: con pocas filas por tabla el planificador prefiere recorrer `seq` hacia atrás.
- Conteo de la misma página (`count(*)` sobre subconsulta con `LIMIT`; el real usa 100.001, aquí 10.001): `Index Only Scan using ix_audit_log_table_record`, 537 filas, 0,279 ms, `hit=120` (147 heap fetches).
- `recent` del tablero (3 sentencias, una por tabla, `action IN (insert,update,delete)`, sin `SYSTEM_USER_ID`, `LIMIT 10`): todas `Index Scan Backward using uq_audit_log_seq` con filtro; `members.members` 0,028 ms hit=64 (descarta 84); `memberships.memberships` 0,024 ms hit=60 (76); `payments.payments` 0,030 ms hit=79 (105). Suma ~0,08 ms.
- Línea base de S4B-D5: todo bajo 1 ms a 5,9 mil filas. Riesgo a vigilar con volumen: ambas consultas dependen de recorrer `seq` con filtro; si una tabla es rara en el log, el recorrido crece (el planificador debería pasar a `ix_audit_log_table_seq` por estadísticas, no está forzado).

### V6 · Smoke con evidencia SQL (2026-11-04)

- Triggers `%forbid%` en `apex-db-1` y `apex_ensayo`: 13 y 13, todos `tgenabled='A'` (4 de mutación/borrado, 8+1 de truncate; nombres iguales en ambas bases).
- Dentro de `BEGIN; ... ROLLBACK;` en ambas bases: `UPDATE`, `DELETE`, `TRUNCATE` y `SET LOCAL session_replication_role = replica; UPDATE` sobre `audit.audit_log` -> `ERROR:  audit.audit_log es append-only` (el propietario `apex` es superusuario, así que `replica` se aceptó y el trigger `ALWAYS` aun así disparó; sin "permission denied"). `UPDATE` y `DELETE` sobre `audit.verifications` -> `audit.verifications es append-only`. `UPDATE crypto.crypto_ops` -> `crypto.crypto_ops es append-only`. (Primer intento de `verifications` falló por columna `result` inexistente: la columna es `ok`; repetido bien.)
- Roles (`pg_roles LIKE 'apex%'`, idénticos en las dos bases): `apex` super/createrole/createdb/login = t/t/t/t (propietario bootstrap de `POSTGRES_USER`, solo lo usan db, migrate, dbsetup, tools); `apex_api`, `apex_worker`, `apex_backup` = f/f/f/t.
- `scripts/ci/test_db_roles.sh`: dev (`DC` de dev, `OPS_ENV_FILE=.env.ops`, existe) **0 fallas** y ensayo **0 fallas**.
- `worker.job_runs`: dev `backup_check` 11-04 ok (2 intentos), `expirations` 11-04 ok (2), `backup_check` 11-03 missing (3), `expirations` 11-03 ok (1), `expirations` 10-29 ok (13); ensayo `backup_check` 11-04 ok (3), `expirations` 11-04 ok (1). `job_name LIKE '%_sim'` = 0 en dev y en ensayo.
- Backup (ensayo): `latest.json` `verify: ok`, `upload: skipped`, `database: apex_ensayo`; `minisign -V -P $BACKUP_SIGN_PUBKEY` -> "Signature and comment signature verified" (exit 0); `head -c 20` de los dos `.age` = `age-encryption.org/v`; el directorio solo tiene el juego `apex-20261104-144427` (2 .age + manifiesto + .minisig), nada borrado. `/api/v1/health` (8280): `{"status":"ok","db":"ok","version":"fae9fd0","backup":"ok","migrations":"ok"}`.
- `verify-audit`: dev (admin desechable) exit 0 "Cadena íntegra: 5959 registros verificados hasta el seq 5959"; ensayo exit 0 "Cadena íntegra: 208 registros verificados hasta el seq 208". Cada corrida añade una fila a `audit.verifications` (por diseño).
- Logs `api worker backup` (dev 297 líneas, ensayo 638): `AGE-SECRET-KEY|/keys/|kek.bin|BEGIN|passphrase` = 0 y 0; correos (`[a-z0-9._-]+@...`) = 0 y 0; `document|phone|email|telefono` = 0 y 0; 7-10 dígitos: 38 y 178 coincidencias, todas dentro de cadenas hexadecimales (request ids y hashes), 0 números sueltos. Sin hallazgos.
- `SELECT max(at) <= now() FROM audit.audit_log` = t (dev y ensayo).

### V5 · Rendimiento (orquestador, 2026-11-04; dos corridas, en primer plano por lotes porque el segundo plano murió por memoria; `VACUUM (ANALYZE, PARALLEL 0) audit.audit_log` en `db_test` tras cada corrida)

Corrida 1 / corrida 2 (todas `passed`; 29 pruebas `perf` en total: 22 + 3 + 2 + 2):
- `audit/test_list_performance`: lista sin filtros 17,0 / 18,7 ms; por tabla 25,1 / 30,3; por usuario 20,2 / 18,0; tabla y usuario 26,4 / 38,4; `count(*)` sin filtros 23,6 / 11,1; con tabla 29,9 / 66,0 ms.
- `members/test_list_perf`: búsqueda por documento con 1.000 socios 33,2 / 31,8 ms; `membership_status=active` con 5.000 ids 44,0 / 37,0 ms; `none` 37,3 / 35,8 ms. L-11 login fallido ×20: p50 0,404 / 0,388 s, p95 0,413 / 0,397 s (≥ `LOGIN_MIN_DURATION_MS`).
- `memberships/test_list_perf`: lista expiring con 1.000 socios y 3.000 membresías 18,9 / 19,1 ms; resumen sin caché 16,6 / 15,7 ms.
- `payments/test_list_perf`: lista con 10.000 pagos 20,1 / 13,7 ms; resumen del mes 9,2 / 8,2 ms.
- `worker/test_expirations` (perf): 1.000 revisados, 2.256 cambiadas, 0 `busy_omitidos`, 0 errores en las dos corridas.
- `audit/test_verify_performance`: verificación de 100.000 filas 2,62 / 2,55 s; peor bloque 26,6 / 30,0 ms (tope 100 ms).
- `core/test_gc_after_startup` (S4B-D48): 20 verificaciones de 100.000 filas, peor pausa de generación 2 3,1 / 4,6 ms (tope 100 ms; sin plan B).
- `cli/test_import_members_perf`: 1.000 filas 17,9 s (tope 120 s); 5.000 filas 88,6 s (medida; tope 600 s). Dos corridas `passed` (108 s y 112 s en total).
- `EXPLAIN (ANALYZE, BUFFERS)` sobre `apex-db-1`: ver "V5 · EXPLAIN" arriba (todo < 1 ms, con índice).
- Comprobación del gate corregido (S4B-D200): `slice-gate.sh web/shared src/shared/ui/Tabs.test.tsx src/shared/lib/audit-labels.test.ts src/shared/ui/HistoryAside.test.tsx` SIN extras: tsc en verde y 82 pruebas.

### V9 · Gates completos (orquestador, 2026-11-04; parcial: faltan `run-gates.sh` final, `check-image-secrets.sh`, `test_api_image.sh` y `pre-commit` final tras el último cambio de código)

2. `uv run pytest tests/architecture -q`: 533 passed, 0 skipped (incluidas `test_third_party_confinement`, `test_archive_importers`, `test_app_layer_importers`, `test_backup_status_imports`, `test_kek_path_single_door`, `test_adr_docs`).
3. Saltadas de la suite del api en este equipo (`-rs` sobre `tests/` menos los módulos de negocio sin saltos: 2.572 passed, 52 skipped, 5 deselected): `test_archive_kek.py` 16 y `test_export_kek.py` 14 (el `age` falso no arranca con `env={}` bajo cmd.exe; corrieron en el contenedor Linux de B3a: 78 passed, 0 skipped), `test_archive_real_age.py` 3 y `test_kek_real_age.py` 2 (`age` real y `pty` solo en Linux; corrieron en el contenedor Linux de B3a con `age` 1.1.1 y la CI exige 0 saltos, S4B-D103), `test_backup_check.py` 2 y `test_archive.py` 1 (`mkfifo`; la prueba manual de B2 en `apex-api:local` y la CI), enlaces simbólicos sin privilegios 6 (`test_backup_check` 1, `test_archive_kek` 1, `test_archive` 1, `test_import_members` 2, `test_retire_key_cli` 1; CI), NTFS sin modo POSIX 3 (`test_provider_startup`, `test_init_keys`, `test_jwt`; CI). Total 52 = las 52 de `run-gates.sh`.
4. `uvx pre-commit run --all-files`: todo en verde salvo `end-of-file-fixer`, que normalizó el final de `docs/scratch/sprint-04b.md` y `docs/ddd/DECISIONES.md`; se repite al final.
5. `bash scripts/workflow/tests/run.sh`: 6 de 6 archivos en verde (incluida la prueba nueva de S4B-D200).
6. `check-licenses-api.sh` ok, `test_licenses.sh` 0 fallas, `cd web && npm run licenses` ok; `notice.sh` sin cambios en `NOTICE`.
7. `npm audit --omit=dev --audit-level=high`: 0 vulnerabilidades; `npm audit --audit-level=high` completo: 0 high/critical; `pip-audit --strict --disable-pip --require-hashes` sobre el export de producción: sin vulnerabilidades conocidas.
8. gitleaks sobre el historial (`--log-opts=--all`, 206 commits): 14 hallazgos, todos falsos positivos (contraseñas centinela de `tests/migrations` y `test_compose_config.sh`, `clave-inventada-1234` de la guía, texto de salida `retire-key: filas_negocio=`); lista blanca por valor exacto con `regexTarget = "match"` en `c236ef4`; segundo escaneo: "no leaks found".
10. `cd web && npm run gen:api && git diff --exit-code src/core/api/types.ts`: sin deriva; `grep -rn "job_runs\|audit_log" web/tests`: 0.
11. `check-release-version.sh --check v0.1.0`: 0 (pyproject, package.json y CHANGELOG en 0.1.0). `test_images_pinned.sh`: 0 fallas.


### V7 · Demo (ensayo `apex-ensayo`, 2026-11-04, HEAD 78be9fb; los seis puntos de `SPRINT-04B.md`)

Preparación: ensayo parado con `stop` -> `$DCE up -d --no-build` (con `compose.verify.yml` y las dos variables de llaves, `GIT_SHA=78be9fb`, `MSYS_NO_PATHCONV=1`): db, api, backup, worker y web `healthy` en 15 s. Memoria libre del host entre 2,0 y 1,77 GB durante toda la sesión (nunca bajó de 1,5 GB; no se paró ningún servicio de desarrollo). Las imágenes locales de api y web no cambian de código desde `fae9fd0` (`git diff fae9fd0..HEAD -- api/src web/src infra` vacío), así que se reconstruyen solo para llevar la etiqueta del HEAD.

1. Arranque de producción: ya demostrado en V2 (orden db -> migrate -> dbsetup -> web/worker, `migrations: ok`, `backup` en `/health`). Aquí se repitió el arranque del ensayo: `/api/v1/health` = `{"status":"ok","db":"ok","version":"78be9fb","backup":"ok","migrations":"ok"}`.
2. `seed --demo` e Inicio contra el ensayo: V2 y V4 (T8, `home.spec.ts`).
3. `import-members`: V4 (idempotente; > 5.000 filas sale 2).

**4. Respaldo y restauración (B3a.7 sobre el árbol final)**
- `run.sh` manual (con `compose.verify.yml`): `apex-20261104-153744`, db 145.062 B, uploads 1.736 B, `verificación de descifrado: ok`, manifiesto firmado; 4,1 s. `minisign -V -P` sobre `latest.json`: "Signature and comment signature verified". `latest.json` lleva `verify: ok`, `upload: skipped`, `database: apex_ensayo`.
- `--run-once backup_check` con el manifiesto verificado: `result ok`, `verificado 1`, 5,7 s. Con `run.sh` SIN `compose.verify.yml` (`apex-20261104-153839`, sin línea de verificación) y luego `backup_check`: `result ok_unverified`, `verificado 0`. (Un primer intento sin exportar `BACKUP_SIGN_KEY_FILE` salió con "falta la llave de firma", esperado: `compose.yml` la monta siempre.)
- `restore_e2e.sh` sobre el ensayo, en el anfitrión (no hizo falta el auxiliar: tras S4B-D190..D196 los modos ya no estorban en NTFS), con `E2E_DC` del ensayo, `E2E_ENV_DIR=docs/scratch/ensayo`, `E2E_ADMIN_EMAIL=admin-ensayo@apex.test`: 23 comprobaciones, 0 fallas, 36,5 s. Cubre: socio con documento cifrado, `export-kek` y `verify-kek-backup` con `age -p` bajo pty (`total=... failed=0`), `run.sh` firmado, negativas con salida 2 (sin firma, firma inválida comprobada con minisign, sin `-P`, `--confirm-database` distinto, `tar` con enlace simbólico firmado) sin tocar la base ni tomar `pre-restore`, `restore.sh` sale 0 en `apex_restore` (base creada y borrada dentro del `db` del ensayo; el script usa ese nombre fijo, no `apex_ensayo_restore`), ancla de auditoría igual a la de origen, 17 triggers en `A`, `pre-restore` presente, `dbsetup` y lectura de `apex_api`, adjunto 10001:10001 modo 600 legible por la imagen del api, `restore-kek` a `/dev/shm`, `reveal` devuelve el documento con la KEK restaurada y con otra KEK aparece `unwrap_failed` sin documento ni material.
- Efecto lateral conocido: el `limpiar` del script borra `apex-*`, `latest.json` y `latest.json.minisig` del volumen `backups` del proyecto (esta vez no se copiaron aparte); se generó un juego nuevo antes de la rotación. El ensayo suma un socio "Restore E2E" (37 socios en total).

**5. Rotación interrumpida y reanudada, retiro**
- Estado previo: 37 socios con documento cifrado; `member.document` con dos llaves v1 `active` (cifrado `8bdc1c76-...` e índice ciego), `crypto_jobs` vacía.
- Con 37 filas una pasada de 500 no se puede interrumpir a mano, así que el envoltorio `rot_int.py` (scratchpad, montado en `tools`) lanza `rotate-key member.document --reason "demo v0.1.0" --as admin-ensayo@apex.test --batch-size 5` y le manda SIGINT en cuanto `crypto_jobs.done >= 5`: `rotate-key: total=37`, `hecho=5/37`, SIGINT a 1,65 s, salida 130, job `running` 5/37, 0 candados asesores. Total 2,8 s.
- Reanudación (mismo comando sin envoltorio, tamaño de lote por omisión): `reanudando desde hecho=5/37` -> `hecho=37/37`, sale 0, 2,5 s; un solo registro en `crypto_jobs` (`done` 37/37); versión 1 de cifrado en `decrypt_only`, versión 2 `active`.
- `export-kek` + `verify-kek-backup` sobre la KEK del ensayo (frase aleatoria solo en memoria, `PTY_FRASE` nunca escrita; archivo `docs/scratch/ensayo/kekbak/kek.age`, 214 B, ignorado por git, se borra en V12): `verify-kek-backup: total=9 failed=0`. `run.sh` reciente: `apex-20261104-154142`.
- `retire-key 8bdc1c76-... --as admin-ensayo@apex.test`: sin `--confirm-audit-blobs` sale 2 ("es obligatorio"); con `0` sale 2 e imprime `filas_negocio=0` `audit_blobs=37`; con `37` sale 0 `llave retirada`.
- `reveal` de `document` de los 37 socios con la versión 1 retirada (`reveal_all.py`): `total=37 ok=37 vacios=0 fallos=0`, 2,5 s.
- `crypto_ops` de `member.document`: `encrypt` versión 2 en dos lotes con `batch_id` (5 filas y 32 filas = 37; el lote de 5 comparte `batch_id` con su fila `rotate`), `rotate` de rotación y de retiro con `batch_id` propio; cada `decrypt` de los 39 reveals trae su `batch_id`.

**6. `deploy.sh` sobre el ensayo (auxiliar Linux)**
- Vía: contenedor `docker:cli` (socket, `--network host`, bash/git/rsync/curl/GNU tar con `apk`) y volumen `apex-b4-work` montado en su propio Mountpoint (`/var/lib/docker/volumes/apex-b4-work/_data`), `TMPDIR` dentro del volumen, copia del árbol con rsync (con `.git`, más `docs/scratch/ensayo` con `.env`, `.env.ops`, `keys-b4/`, `kekbak/kek.age`). Se ejecutó `infra/tests/deploy_e2e.sh` de esa copia con `E2E_PROJECT=apex-ensayo`, `E2E_ENV_DIR`, `E2E_KEK_FILE` (la copia `age -p` del ensayo) y las dos variables de llaves apuntando al volumen. Parches SOLO en la copia (script `aux-deploy.sh` del scratchpad; el repositorio no se tocó): (a) la guarda que en `apex-ensayo` solo admite `--solo-db-detenida` pasa a admitir el camino completo; (b) `REF=v99.0.1` en vez de `v99.0.0`; (c) un bloque "1b" con una segunda corrida consecutiva para V8. `deploy_e2e.sh` crea el repositorio temporal con la etiqueta `v99.0.1` (SHA de la copia `51a57559...`), lo clona y corre ahí el `deploy.sh` real con `--ref v99.0.1 --expect-sha <sha> --kek-file <kek.age> --i-know-unsigned-ref` y `DEPLOY_COMPOSE_EXTRA=infra/compose.verify.yml`. No se usó `DEPLOY_SKIP_BUILD=1` en la primera corrida: `deploy.sh` construye con `GIT_SHA=v99.0.1` (caché de buildx) y eso deja la etiqueta OCI coincidente; las siguientes corridas sí van con `DEPLOY_SKIP_BUILD=1`. `DEPLOY_STATE_DIR` en `docs/scratch/ensayo/state` dentro del volumen.
- Corrida 1 (15:43 a 15:45, 1 min 38 s; el bloque 1b se insertó por error dentro de la cabecera de comentarios y no corrió como debía: no hizo daño, las funciones aún no existían): camino feliz, api roto y db detenida, todo en verde. Corrida 2 (15:46:54 a 15:48:10, 1 min 17 s, parche corregido): **todo en verde**:
  - camino feliz: `deploy.sh` sale 0; quedan `pre-deploy-<ts>-db.dump.age`, `-uploads.tar.age`, `.json` y `.json.minisig`; `latest.json` no cambió; `/health` 200 con `migrations: ok`; `deploy-<fecha>.state.json`.
  - 1b segunda corrida consecutiva (`DEPLOY_SKIP_BUILD=1`): sale 0; pre-deploy 4 -> 5 juegos; etiquetas `prev-*` 33 -> 36 (tres nuevas); dos `deploy-*.state.json` (V8).
  - api roto (`CRYPTO_LOCAL_KEK_PATH=/nonexistent` en el `.env` del clon, no en el del ensayo): `deploy.sh` sale 1 (`docker compose up -d terminó con error`), escribe `rollback-20261104-154731.txt` (1.077 B): motivo, las tres imágenes `prev-<fecha>`, respaldo previo, código anterior, comandos de vuelta atrás y la advertencia "este script no restaura la base"; `grep -ciE 'PASSWORD|SECRET'` = 0; el respaldo pre-deploy se conservó y el nuevo también. Con el `.env` bueno el stack se recupera (sale 0).
  - `db` detenida: sale 2, motivo "el servicio db no está en marcha", sin "construcción de las imágenes", sin estado nuevo; la db se vuelve a arrancar.
- Resultado en el volumen `backups` del ensayo: siete juegos `pre-deploy-*` (tres de la corrida 1: camino feliz, api roto, recuperación; cuatro de la 2: camino feliz, 1b, api roto, recuperación), todos con cabecera age, manifiesto y firma; `latest.json` sigue en el juego `apex-20261104-154142`. El daemon queda con 42 etiquetas `apex-*:prev-*` (V12).
- Cierre: auxiliar (`--rm`) y volumen `apex-b4-work` borrados. Las imágenes quedaron con etiqueta `v99.0.1` (api `48d723e84bd6`, web `287643ebf660`, backup `c13780244403`); se reconstruyeron con buildx (`--build-arg GIT_SHA=78be9fb`, 15 s por caché): `apex-api:local` **5c40e21c1b38**, `apex-web:local` **c1abdde010fb**, `apex-backup:local` **efe44b7ac28e** (la imagen backup no lleva etiqueta de revisión). Recreados api, worker, web y backup con `--no-build --force-recreate`: `/api/v1/health` = `{"status":"ok","db":"ok","version":"78be9fb","backup":"ok","migrations":"ok"}`, etiqueta OCI `78be9fb` en api y web.

### V8 · preparación (ensayo `apex-ensayo`, 2026-11-04)

- `database-reviewer`: volcado de `role_table_grants` y `role_column_grants` (`WHERE grantee LIKE 'apex_%'`, mismas consultas del plan) en `C:\Users\PC\AppData\Local\Temp\claude\C--Users-PC-Proyectos-Apex\1118b396-2b0c-4b0b-9f7c-f9f6b9a1a3a4\scratchpad\v8-grants-ensayo.txt` (688 líneas; 51 filas de tabla y 632 de columna; 16 tablas clasificadas por `dbsetup`). Roles: `apex` super/createrole/createdb/login; `apex_api`, `apex_worker`, `apex_backup` sin superusuario, con `connlimit` 20, 5 y 2.
- `dbsetup` ×2 (`$DCE --profile prod-init run --rm --no-deps dbsetup`): ambos sales 0 con "roles aplicados; 16 tablas clasificadas" (aviso NOTICE de `pg_read_all_data` ya concedido); `pg_roles`, `role_table_grants` y `role_column_grants` idénticos byte a byte antes, después de la 1.ª y después de la 2.ª (`cmp`).
- `run.sh` ×2 (con `compose.verify.yml`): `apex-20261104-155011` y `apex-20261104-155017`, ambos `verificación de descifrado: ok`; el volumen pasó de 32 a 36 entradas (+4 archivos, dos juegos), ningún archivo borrado (retención de 14 días); `latest.json` -> `apex-20261104-155017` con firma válida.
- `--run-once backup_check` ×2 el mismo día: ambos `result=ok` sobre `apex-20261104-155017`; en `worker.job_runs` sigue UNA fila para `(backup_check, 2026-11-04)` con el mismo `id` (`15a67641-...`): el segundo intento actualiza la fila (antes `ok_unverified`, ahora `ok`); la tabla no tiene contador de intentos y el índice `uq_job_runs_name_date` lo impone.
- `init-keys` ×2: las dos veces "KEK/llave de firma/par JWT: ya existe", sale 0; `crypto_keys` sigue igual (9 filas tras la rotación).
- `verify-audit` ×2: "Cadena íntegra: 257 registros ... seq 257" y "258 ... seq 258" (la primera añade su fila a `audit.verifications`), ambas 0; `audit.verifications` = 6 filas, `max(through_seq)` 258.
- `export-kek` ×2: la 1.ª sale 0; la 2.ª sale 2 "el archivo de salida ya existe" (`O_EXCL`) y NO escribe fila en `crypto_ops`. `verify-kek-backup` ×2: `total=9 failed=0` las dos; `crypto_ops` con tres `export` ok y tres `verify` ok en 40 min (uno de cada uno de `restore_e2e.sh`, uno de `export` y dos de `verify` de esta tanda).
- `retire-key` repetida sobre la llave ya retirada: sale 2 con `la llave encrypt en retired no admite el evento retire` (el mensaje real no dice "ya retirada"; el plan esperaba ese texto).
- `rotate-key member.document` tras `done`: sin `--reason` sale 2 `--reason no es válido: el motivo es obligatorio`; con `--reason` inicia una NUEVA rotación (no hay "nada que rotar"): 37/37, sale 0, versión 2 -> `decrypt_only`, versión 3 `active`, dos filas `done` en `crypto_jobs`. El ensayo queda con `member.document` v1 retirada, v2 `decrypt_only`, v3 `active`.
- `deploy.sh` ×2 seguidos: ver V7.6 (1b): dos `pre-deploy`, código 0 las dos, tres `prev-*` nuevas por corrida.
- Estado final: ensayo arriba y `healthy` (db, api, worker, web, backup) con las imágenes de HEAD; `apex-db-1` (dev) sin tocar: 8 llaves, las 8 versión 1 `active` (SELECT al final); stack de desarrollo `healthy` (imágenes `fae9fd0` sin recrear); sin escrituras ni rotaciones en dev.

### V8 · Revisión de base de datos

- `database-reviewer`: 0 CRITICAL, 0 HIGH, 0 MEDIUM, 5 LOW, 1 INFO. Decisiones S4B-D201 a D206 en `docs/ddd/DECISIONES.md`.
- Corregido: D201 (conteo de `apply.sh` desde el ARRAY + prueba de las tres listas) y D205 (RUNBOOK §12: `revoke.sql` en cada base).
- Aceptado con dueño: D202 (INSERT completo en pagos, el ORM nombra `voided`), D203 (UPDATE completo en users/members), D204 (SELECT del worker), D206 (propietario superusuario, Sprint 5 / v0.2).
- Sin cambios en privilegios: no se reaplica `dbsetup` en ningún stack.

### V10 · Revisión de seguridad posterior

- Conteos: 0 CRITICAL, 0 HIGH, 0 MEDIUM, 2 LOW.
- L-N1 (`restore-kek` sin rastro con la base arriba) -> slice B3a -> S4B-D207, sale 1 + aviso fijo; prueba en `tests/cli/test_export_kek.py` (age falso: solo CI/Linux).
- L-N2 (`.github/allowed_signers` ausente) -> slice B4 (despliegue) -> S4B-D208 aceptado por S4B-D181 (falla cerrado), dueño v0.2 y el titular.
- Nota: las 8 llaves de `crypto_keys` son 5 DEK más 3 llaves de índice ciego (`*.index`), todas versión 1 `active`.

Nota del orquestador (V10, S4B-D207): la prueba nueva de `restore-kek` con la bitácora rota y las demás de la KEK corrieron en el contenedor Linux (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim` + `age` de Debian): `test_export_kek.py`, `test_kek_real_age.py`, `test_archive_kek.py` y `test_archive_real_age.py` → 62 passed, 0 skipped. El agente había pegado las aserciones de D207 en la prueba del `OperationalError` (D124); se restauró su contrato (salida 0 y línea JSON) y el caso de D207 vive en `test_restore_kek_con_la_base_arriba_y_la_bitacora_rota_sale_1_y_deja_el_archivo`.
