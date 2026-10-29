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
