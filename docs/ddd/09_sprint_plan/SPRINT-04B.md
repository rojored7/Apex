# Sprint 4B · Continuidad operativa y release v0.1

> **Corregido en S4B-W0-1.** El plan de ejecución es `docs/ddd/blueprints/sprint-04b-plan.md` (sección 1, decisiones S4B-D1 a S4B-D103, y sección 4 en adelante) y las decisiones están en `docs/ddd/DECISIONES.md`, sección "Sprint 4B". Donde este texto choque con ellos, mandan ellos. Correcciones de contrato de este archivo:
> - Migraciones: el sprint aplica `0014_audit_log_triggers_always` (`ENABLE ALWAYS` de los triggers de `audit_log` y `verifications`, y el texto de `forbid_mutation`); el ciclo de Alembic es `0001` a `0014` (S4B-D4).
> - Los slices son W0-1, W0-2 (`0014`) y W0-3 en Wave 0; B0 (partir el CLI sin comportamiento nuevo), B1, B2, B3a (respaldo de la KEK), B3b (rotación y `retire-key`) y B4 en backend; y F1 (deuda de front) en un worktree.
> - El respaldo produce dos archivos (`db` y `uploads`) y un manifiesto firmado con `minisign`; la verificación corre en el contenedor `backup`. No existe `verify_age_archive` (G-07 enmendada), `backup.archive` ni `BACKUP_AGE_VERIFY_IDENTITY_PATH` en el worker.
> - `/health` colapsa el estado en `backup` ∈ {`ok`, `attention`, `unknown`} y `migrations` ∈ {`ok`, `mismatch`, `unknown`}.
> - `rotate-key member.document --reason ... --as ...` (argumento posicional, no `--data-class`) deja la llave anterior en `decrypt_only`; `retire-key` es un comando aparte que exige el conteo confirmado de pendientes, incluidos los blobs de `audit_log`.
> - El respaldo de la KEK usa `age -p` (sin `pyrage` ni `--passphrase-file`); `restore.sh` se ejecuta en B3a y en la CI, no solo se nombra.
> - `deploy.sh --ref <rama o SHA> --expect-sha <sha>`: sin `docker compose pull` ni `IMAGE_TAG`, sin firma de etiquetas (v0.2).
> - La configuración se parte en `.env` y `.env.ops`; `api` y `worker` no ven las contraseñas del propietario.
> - Las pruebas de rendimiento usan el marcador `perf` (`-m perf`), no `slow`, y no son gate. Los scripts se comprueban con `bash -n` y pruebas en Bash puro (sin `bats` ni `shellcheck`). Dentro de los contenedores no hay `uv`: se usa `docker compose run --rm tools ...`.
> - `import-members` usa `defusedxml`, una transacción por socio y no `bus.batch()`; el tope es de 5.000 filas.
> - Las condiciones de los índices de `audit_log` (S4B-D5): `0015_audit_log_indexes` solo si `max(seq) > 500.000` o una prueba `perf` de `tests/audit` supera su tope; se mide en V5.

- **Versión:** v0.1. Al cerrar este sprint se etiqueta `v0.1.0`.
- **Épicas:** EP-13 (todo menos US-113) y US-030 de EP-02.
- **Tamaño:** 9 historias, 39 puntos, 174 h relativas.
- **Rama:** `feat/sprint-04b-continuidad-release`.
- **Historias del sprint:** US-030, US-111, US-112, US-114, US-115, US-116, US-117, US-118, US-119.

## Objetivo

Dejar v0.1 lista para operar en el servidor del gimnasio:
- datos de demostración;
- importación desde el Excel del box;
- backup nocturno cifrado, con su verificación visible en `/health`;
- respaldo de la KEK probado con una restauración real;
- rotación de llaves que se puede reanudar;
- despliegue y arranque ordenados y seguros;
- ADR que documentan las decisiones que no se pueden deshacer.

## Demo al final del sprint

Esta demo corre sobre el stack de producción: `docker compose -f infra/compose.yml up -d --build`, sin `compose.dev.yml`.

1. **Arranque.**
   - `migrate` y `dbsetup` terminan y `db`, `api`, `worker`, `web` y `backup` arrancan en el orden de US-118.
   - `/health` responde 200 solo cuando `migrations` es `ok` (colapsado: `ok`, `mismatch` o `unknown`), y trae el campo informativo `backup` (`ok`, `attention` o `unknown`).
2. **Datos de demostración.**
   - `docker compose run --rm tools seed --demo` crea planes, socios cifrados, membresías en todos los estados, pagos y anulaciones.
   - Inicio cuadra con esos datos. Así se cierra el criterio diferido de US-109.
3. **Importación.**
   - `docker compose run --rm -v "$PWD/docs/plantillas:/plantillas:ro" tools import-members /plantillas/importar-socios.xlsx --as admin@...` importa con la cabecera de Q17.
   - Es idempotente por documento.
   - Rechaza archivos de más de 10 MB o de más de 5.000 filas.
4. **Backup y restauración.**
   - Una corrida manual del contenedor `backup` produce:
     - un `pg_dump` y el volumen `uploads`, cada uno en su archivo cifrado con `age`;
     - `latest.json`, el manifiesto, con su firma `minisign`.
   - `docker compose run --rm worker python -m app.worker.main --run-once backup_check` evalúa el manifiesto (la verificación con identidad corre en el contenedor `backup`).
   - `restore.sh` restaura en una base limpia con la KEK respaldada (`restore-kek`); un socio se lee y se revela.
5. **Rotación de llave.**
   - `docker compose run --rm tools rotate-key member.document --reason "..." --as admin@...` recifra por lotes y deja la llave anterior en `decrypt_only`.
   - Si se interrumpe, se reanuda.
   - `docker compose run --rm tools retire-key ...` la deja `retired` solo con cero datos pendientes y el conteo confirmado (incluidos los blobs de `audit_log`).
   - Los socios siguen legibles.
6. **Despliegue.**
   - `deploy.sh --ref <rama o SHA> --expect-sha <sha>` saca un backup previo con `--prefix`, sin `docker compose pull`.
   - Espera la salud del stack.
   - Deja `rollback-*.txt`.

## Dependencias de sprints anteriores

- **Sprint 4A:**
  - US-113: worker y `core/jobs.py`;
  - US-094: `recompute_statuses`;
  - US-104 y US-105: verificación de la cadena;
  - US-108 y US-109: el tablero que cuadra con la demo.
- **Sprint 3:**
  - US-084, US-086, US-089, US-090, US-095 y US-097, que el seed usa;
  - US-074: el `reveal` de la prueba de restauración.
- **Sprint 2:**
  - US-069 y US-070: `create` e `id_by_document`;
  - US-078;
  - US-041: `active_admin_id_by_email`.
- **Sprint 1:**
  - US-023 a US-029: bus, `crypto_ops` y `export`;
  - US-039: secretos.
- **Sprint 0:**
  - US-005: servicio `backup`;
  - US-020: `register_health_check`.

Decisiones que aplica: G-07, N-05, N-15, N-16, N-50, Q17, el refinamiento de US-030 y P3 (destino del backup: S3 compatible por `.env` o, si no se define, local).

## Historias en orden de ejecución

Patrón de v0.1 en cada slice:
1. Rojo: stubs y pruebas.
2. Verde: la implementación.
3. Gate con los archivos del slice más `tests/architecture`.
4. Checkpoint.

### Wave 0 · Infraestructura (`devops-wsl2-docker`)

Se sella con `scripts/workflow/wave0-gate.sh <slice> [archivos de prueba...]`: `bash -n` de todo `.sh` bajo `infra/`, `scripts/ci/` y `scripts/workflow/`, las pruebas de infraestructura y, al final, `slice-gate.sh architecture`.

- **Slice S4B-W0-1 · T-DOC, `age`, imagen y servicio `backup`, `wave0-gate.sh` y decisiones del sprint.** Son las tareas DevOps de US-114 y US-115 (T11).
  - `infra/backup/Dockerfile` y `run.sh` (imagen `apex-backup:local` con `age`, `rclone`, `minisign`, `pg_dump` y `supercronic`):
    - `pg_dump` más `uploads`, cada uno en su archivo cifrado con `age`;
    - rclone a S3 compatible, o copia local;
    - `latest.json` firmado con `minisign`.
  - Retención de 14 días.
  - Identidad `age` de verificación montada solo en `backup` (`infra/compose.verify.yml`).
  - El binario `age` (BSD-3) entra también en la imagen del api, para `archive.py`.
  - `.env.ops.example`, dependencias y documentación de contrato (T-DOC) en los desgloses y este archivo.
- **Slice S4B-W0-2 · Migración `0014_audit_log_triggers_always` y re-armado de triggers.** Deuda S4A-D98: `ENABLE ALWAYS` de los triggers de `audit_log` y `verifications`, y el texto de `forbid_mutation`. Con la condición de los índices de `audit_log` escrita (S4B-D5).
- **Slice S4B-W0-3 · Roles de base, migraciones fuera del api, entorno por servicio y endurecimiento.** Son las tareas DevOps de US-118, US-117 y US-116.
  - **Hecho en S4B-W0-3:** `infra/db/` (roles, permisos por tabla y columna, `revoke.sql`, `apply.sh`), servicios `migrate` y `dbsetup`, `MIGRATE_ON_STARTUP`, `.env`/`.env.ops` por servicio, red parametrizada, endurecimiento (L-7), zona `apex_health` de Nginx, `25P03` y el rollback de `crypto_ops`. Ver el bloque S4B-W0-3 de `docs/ddd/DECISIONES.md`.
  - Servicios `migrate` y `dbsetup`; `depends_on` con `service_healthy`.
  - Healthchecks de `db`, `api`, `web` y `backup`.
  - Rol de base del api separado (S3-D49, reforzado por I-2 de la revisión V10 del Sprint 3): el api y el worker se conectan con roles que no son superusuario ni dueños de los esquemas; las migraciones corren con el rol dueño. Así el api no puede apagar ni borrar los triggers de inmutabilidad con SQL propio.
  - `.env` y `.env.ops`: cada servicio recibe solo sus variables (H-1).
  - MEDIUM-1 y MEDIUM-2 del Sprint 3.
  - Volúmenes del respaldo de la KEK; el worker monta `backups` como `:ro`.
- **Gate de la Wave 0:**
  - `wave0-gate.sh` (`bash -n` sobre los scripts, pruebas de infraestructura, `docker compose config` en las combinaciones);
  - smoke de Compose con los cinco servicios;
  - corrida manual del contenedor `backup` con `docker compose run --rm backup ...`, sin binarios del host.

### Waves 3a/3b · Backend, alternadas por slice

- **Slice S4B-B0 · Partir el CLI sin comportamiento nuevo.** Sin historias: `cli.py` (760 líneas) se divide en `cli_base.py` y `cli_ops/`, con el mapeo `cli` del gate.
- **Slice S4B-B1 · Datos de demostración e importación.** Historias: US-111 y US-112.
  - Rojo:
    - `tests/cli/test_demo_dataset.py`, `test_seed_demo.py` y `test_seed_cli.py`;
    - `tests/cli/test_members_xlsx_parse.py`, `test_import_members.py` y `test_import_members_perf.py` (`-m perf`).
  - Verde:
    - `cli seed --demo`, idempotente por reanudación, que llama a `sell(..., enforce_retroactive_limit=False, role="admin")`, en dos transacciones por socio; `--allow-production` y el nombre de la base para bases que no son de prueba;
    - `cli import-members`:
      - plantilla Q17;
      - idempotente;
      - límites de 10 MB y 5.000 filas;
      - con `defusedxml`, dentro de `IMPORT_DIR`, registro en `members.import_runs`;
      - sin `bus.batch()`;
      - una transacción por socio (deuda de PL6 de la revisión de Fase 4 del Sprint 3, S3-D95): alta, venta y primer pago de un socio confirman juntos y el siguiente socio abre otra transacción, así ninguna pide `lock_member` después del primer flush auditado de otro socio (orden de candados de D3, docstring de `core/locks.py`).
  - Gate: `slice-gate.sh cli` con sus archivos (`slice-gate.sh members` no aplica).
- **Slice S4B-B2 · Backup y su verificación.** Historias: US-114 (backend) y US-115.
  - Rojo:
    - `tests/crypto/test_archive.py`;
    - `tests/worker/test_backup_check_evaluate.py` y `test_backup_check.py`;
    - `tests/core/test_health.py`, ampliada.
  - Verde:
    - `core/crypto/archive.py`, con `digest_file` (sin `verify_age_archive`);
    - job `backup_check` con `run(ctx) -> JobResult(status=...)`, que evalúa el manifiesto sin descifrar;
    - campo `backup` de `/health` (`ok`, `attention`, `unknown`), registrado con `critical=False`. Con esto se cierra el criterio diferido de US-020.
  - Gate: `slice-gate.sh crypto`, `slice-gate.sh worker` y `slice-gate.sh main`, cada uno con sus archivos.
- **Slice S4B-B3a · Respaldo de la KEK y prueba de restauración.** Historia: US-116.
  - Rojo:
    - `tests/crypto/test_kek_backup.py`;
    - `tests/cli/test_export_kek.py`.
  - Verde:
    - `cli export-kek`, `cli verify-kek-backup` y `cli restore-kek`, con `age -p` y los verbos `export` y `verify` en `crypto_ops` (`kek.backup`);
    - `restore.sh` ejecutado en el slice y en la CI.
  - Gate: `slice-gate.sh crypto` y `slice-gate.sh cli`, cada uno con sus archivos.
- **Slice S4B-B3b · Rotación de llave reanudable y `retire-key`.** Historia: US-030 (va después de US-116 y de su checkpoint).
  - Rojo:
    - `tests/crypto/test_next_key_state.py`, `test_rotate.py`, `test_rotate_concurrency.py` y `test_rotate_index.py`;
    - `tests/cli/test_rotate_key_cli.py`.
  - Verde:
    - `cli rotate-key <data_class> --reason ... --as ...`:
      - recifrado por lotes que se puede reanudar;
      - un solo job a la vez por clase;
      - índice solo con `--index`;
      - cierra en `decrypt_only` y deja `rotated_by`;
      - `attachment.sensitive` responde 409 `rotation_not_supported` hasta el Sprint 6 (G-09);
    - `cli retire-key`: `retired` solo con cero pendientes y el conteo confirmado (blobs de `audit_log` incluidos); una llave `retired` no descifra.
  - Gate: `slice-gate.sh crypto` y `slice-gate.sh cli`, cada uno con sus archivos.
- **Slice S4B-B4 · Despliegue, arranque y ADR.** Historias: US-117, US-118 y US-119.
  - Rojo:
    - `tests/core/test_health_migrations.py`;
    - `tests/core/test_chain_hash_vector.py`;
    - `tests/architecture/test_adr_docs.py`.
  - Verde:
    - `/health` responde 200 solo con `migrations == "ok"` (`ok`, `mismatch`, `unknown`);
    - `deploy.sh --ref --expect-sha`, documentación de operación;
    - ADR-001 (monolito modular y G-03), ADR-002 (criptografía, con `age -p`), ADR-003 (pagos inmutables) y ADR-004 (serialización canónica de la cadena de auditoría, con vector fijo).
  - Gate: `slice-gate.sh main` con sus archivos.
- **Slice S4B-F1 · Deuda de front con dueño 4B** (worktree `sprint-04b-front`, tras el checkpoint de B4): `sessionStorage` con regla de lint, barra `Tabs` a 1440 px, contraste de "automático (aviso)", T8 de US-109 (corre en V4) y `table_name` desconocido.

Este sprint no tiene Waves 5a/5b: ninguna historia trae pantallas; F1 solo salda deuda de front de los Sprints 3 y 4A.

### Validación del sprint

Detalle de cada paso en `docs/ddd/blueprints/sprint-04b-plan.md`, sección 7:
- V1 · Fusión del worktree del front y documentos al día (sin referencias a `verify_age_archive`, `pyrage`, `IMAGE_TAG`, `bats`, `slow` ni `uv run` dentro de contenedores).
- V2 · Stack desde cero de código, proyecto de producción aparte (`apex-ensayo`) y ciclo de Alembic hasta `0014`.
- V3 · Datos reales antes de navegar (desarrollo, `apex-db-1` solo lectura).
- V4 · E2E (preview y stack dos veces) y T8 de US-109 contra el ensayo; `import-members` sobre el ensayo.
- V5 · Rendimiento (`-m perf`: importación de 5.000 filas, GC del arranque) y línea base de la condición de los índices (S4B-D5).
- V6 · Smoke con evidencia SQL (triggers, roles, worker, backup, `verify-audit`).
- V7 · Demo (los 6 puntos de arriba con el texto corregido).
- V8 · Repetición e idempotencia (`seed --demo`, `import-members`, `run.sh`, `backup_check`, `deploy.sh`, `dbsetup`, `rotate-key`, `retire-key`).
- V9 · Gates completos (`run-gates.sh`, `tests/architecture` sin saltadas, licencias, auditoría de dependencias, gitleaks, imágenes).
- V10 · Revisión de seguridad posterior (`security-reviewer` sobre el código fusionado).
- V11 · `verify-delivery`: matriz de las 9 historias y checklist de criterios diferidos de v0.1 (US-004 a US-007, US-012, US-018, US-020, US-066 y US-109), con las desviaciones declaradas.
- V12 · Cierre documental, limpieza, merge por avance rápido, etiqueta `v0.1.0` local y paso humano (push, PR, merge; la etiqueta se empuja solo con la CI en verde).

## Migraciones que aplica

`0014_audit_log_triggers_always` (`down_revision = "0013_audit_verifications"`), en el slice W0-2: `ENABLE ALWAYS` de los ocho triggers que estaban en `O` (dos de `audit_log` y seis de `crypto.*`; con los dos de `verifications` quedan diez en `A`) y `CREATE OR REPLACE` de `audit.forbid_mutation()` con `TG_TABLE_SCHEMA`/`TG_TABLE_NAME`. El esquema de v0.1 se cierra en `0014`. Los roles y permisos de base los aplica `dbsetup`, no Alembic.

Los índices de `audit_log` solo entran (`0015_audit_log_indexes`, con `CONCURRENTLY` fuera de transacción) si `max(seq) > 500.000` o una prueba `perf` de `tests/audit` supera su tope (S4B-D5); V5 deja la línea base.

## Endpoints que expone

Ninguno nuevo. `GET /health` y `GET /api/v1/health` agregan `backup` (`ok`, `attention`, `unknown`) y `migrations` (`ok`, `mismatch`, `unknown`); el estado 200 exige `migrations == "ok"`.

## Tests de arquitectura que deben pasar

Todos corren en cada gate de slice (A-5).
- Todos los de los Sprints 0 a 4A.
- `test_no_cross_models.py`, ampliada en US-111, US-112 y US-119.
- `test_ruff_banned_api.py` (sin cambio) y `test_third_party_confinement.py` (nueva), que reemplazan a `test_banned_imports.py` en US-115, US-116 y US-119.
- `test_no_create_all.py`, ampliada en US-118.
- `test_adr_docs.py` (US-119).

## Riesgos y mitigación

1. **[HIGH] Operaciones irreversibles con llaves.** Una rotación que deja `retired` una llave que todavía tiene datos los pierde, y un backup sin su KEK no sirve.
   - Mitigación:
     - US-116 va antes que US-030 dentro del mismo slice;
     - la restauración se ensaya en una base limpia;
     - `rotate-key` cierra en `decrypt_only` y el conteo de pendientes tiene que ser cero y estar confirmado antes de `retire-key`;
     - nada de esto se corre sobre datos reales sin confirmación humana.
2. **[HIGH] Infraestructura nueva: backup, `age`, rclone y arranque ordenado.**
   - Mitigación:
     - la Wave 0 se sella con `wave0-gate.sh` y smoke antes de la Wave 3a;
     - `deploy.sh` tiene rollback documentado.
3. **[MEDIUM] El destino del backup no está definido (P3).**
   - Mitigación: destino local por defecto, con un aviso en el README de operación.
4. **[MEDIUM] La release depende de cerrar todos los criterios diferidos.**
   - Mitigación: la checklist de la validación.
5. **[MEDIUM] Rendimiento de la importación.**
   - Mitigación: `test_import_members_perf.py` con el marcador `perf` (corre aparte, no es gate).

## Definición de hecho del sprint

- Slices:
  - los 3 de Wave 0 (W0-1, W0-2 y W0-3) quedan sellados con `wave0-gate.sh` y verificados con smoke;
  - los 6 de backend (B0, B1, B2, B3a, B3b y B4) quedan confirmados con `checkpoint-commit.sh`;
  - F1 (front) fusionado en V1.
- Pruebas:
  - `run-gates.sh` en verde, con cobertura global de `app` en 80 % o más, incluidos `cli.py` y `worker/`;
  - `tests/architecture` en verde.
- Migraciones: ciclo completo de Alembic de `0001` a `0014`, con `downgrade -1` y `upgrade head`.
- Smoke del stack de producción: los cinco servicios `healthy` (con `migrate` y `dbsetup` terminados) y `/health` con `db`, `version`, `backup` y `migrations`.
- Evidencia:
  - de la restauración: archivo `age`, `latest.json`, salida de `backup_check` y una base restaurada con un socio legible;
  - de la rotación: la llave anterior en `decrypt_only` tras `rotate-key`, `retired` con cero pendientes tras `retire-key`, y el `batch_id` en `crypto_ops`.
- Seguridad (`security-reviewer`):
  - el backup no contiene la KEK;
  - la identidad `age` de verificación y la llave de firma están fuera de las imágenes y solo `backup` las monta;
  - `export-kek` queda auditado;
  - `import-members` tiene límites;
  - `deploy.sh` no hace `push`, `--force`, `down -v` ni `pull`.
- Paso humano: push, PR con CI en verde, merge y etiqueta `v0.1.0`.
- `verify-delivery` completo sobre el stack de producción.

## Deuda con dueño

| Ítem | Dueño | Destino | Referencia |
|---|---|---|---|
| Caddy y TLS (`compose.caddy.yml`) | v0.2 (EP-20 adelantado) | Fuera de v0.1 | S4B-D2 |
| Firma de etiquetas con `allowed_signers` | v0.2 (titular) | `deploy.sh --ref --expect-sha` no verifica firma | S4B-D2 |
| `audit.append()` `SECURITY DEFINER` | v0.2 | Hoy `apex_api` conserva `INSERT` en `audit_log` | V10 |
| Compromiso de KEK y `rewrap` | v0.2 (OpenBao) | Hoy una KEK comprometida no se re-envuelve | V10 |
| Verificación de la firma del manifiesto en el worker por el bus | v0.2 | Hoy la firma se verifica en `backup`; el worker evalúa el manifiesto | S4B-D2 |
| `0015_audit_log_indexes` | Condición de S4B-D5 | `max(seq) > 500.000` o una `perf` de `tests/audit` fuera de tope | S4B-D5 |
| `display_name` | v0.2 (EP-04) | Sustituye la parte local del correo | S4A-D19 |
| `sign-audit` y ancla firmada | v0.3 | Residual: el ancla vive en la misma base | S4A-D43 |
| `notifications.service` en `CONTACT_CALLERS` y regla de la Ley 1581 | Sprint 5 | Primer consumidor de `contact_for_notification` | S4A-D50 |
| S4A-D60 (precio vigente al vender) y S4A-D61 (lectura de auditoría sin auditar) | Revisados en W0-1.8: se mantienen aceptados (D60 con condición de v0.2, D61 con dueño v0.3) | Constancia en `DECISIONES.md` | S4B-D50 |
| N-6 y N-7 | Operador | `instalar-en-servidor.md`; no bloquean la etiqueta | B4 |
