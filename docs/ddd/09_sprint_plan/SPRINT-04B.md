# Sprint 4B · Continuidad operativa y release v0.1

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
   - `db`, `api`, `worker`, `web` y `backup` arrancan en el orden de US-118.
   - `/health` responde 200 solo cuando las migraciones están en `head`, y trae el campo informativo `backup`.
2. **Datos de demostración.**
   - `docker compose run --rm tools seed --demo` crea planes, socios cifrados, membresías en todos los estados, pagos y anulaciones.
   - Inicio cuadra con esos datos. Así se cierra el criterio diferido de US-109.
3. **Importación.**
   - `docker compose run --rm -v "$PWD/docs/plantillas:/plantillas:ro" tools import-members /plantillas/importar-socios.xlsx --as admin@...` importa con la cabecera de Q17.
   - Es idempotente por documento.
   - Rechaza archivos de más de 10 MB o de más de 5.000 filas.
4. **Backup y restauración.**
   - Una corrida manual del contenedor `backup` produce:
     - un `pg_dump`;
     - el volumen `uploads`, cifrado con `age`;
     - `latest.json`.
   - `docker compose run --rm worker python -m app.worker.main --run-once backup_check` lo verifica con `verify_age_archive`.
   - `restore.sh` restaura en una base limpia con la KEK respaldada; un socio se lee y se revela.
5. **Rotación de llave.**
   - `docker compose run --rm tools rotate-key --data-class member.document --as admin@...` recifra por lotes.
   - Si se interrumpe, se reanuda.
   - La llave anterior queda `retired` solo con cero datos pendientes.
   - Los socios siguen legibles.
6. **Despliegue.**
   - `deploy.sh` saca un backup previo con `--prefix`.
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

- **Slice S4B-W0-1 · Contenedor de backup y `age`.** Son las tareas DevOps de US-114 y US-115.
  - `infra/backup/Dockerfile` y `run.sh`:
    - `pg_dump` más `uploads`;
    - cifrado con `age`;
    - rclone a S3 compatible, o copia local;
    - `latest.json`.
  - Retención de 14 días.
  - Identidad `age` montada para verificar.
  - El binario `age` (BSD-3) entra en la imagen del api, que lo necesita para G-07.
- **Slice S4B-W0-2 · Arranque ordenado y despliegue.** Son las tareas DevOps de US-118, US-117 y US-116.
  - `depends_on` con `service_healthy`.
  - Healthchecks de `db`, `api`, `web` y `backup`.
  - `deploy.sh`, con backup previo, espera de salud y `rollback-*.txt`.
  - `restore.sh`, que se nombra en el rollback pero no se ejecuta.
  - Volúmenes del respaldo de la KEK.
- **Gate de la Wave 0:**
  - `bash -n` sobre los scripts;
  - smoke de Compose con los cinco servicios;
  - corrida manual del contenedor `backup` en desarrollo.

### Waves 3a/3b · Backend, alternadas por slice

- **Slice S4B-B1 · Datos de demostración e importación.** Historias: US-111 y US-112.
  - Rojo:
    - `tests/cli/test_demo_dataset.py`, `test_seed_demo.py` y `test_seed_cli.py`;
    - `tests/cli/test_members_xlsx_parse.py`, `test_import_members.py` y `test_import_members_perf.py` (`-m slow`).
  - Verde:
    - `cli seed --demo`, idempotente, que llama a `sell` con `max_retroactive_days=None`;
    - `cli import-members`:
      - plantilla Q17;
      - idempotente;
      - límites de 10 MB y 5.000 filas;
      - `bus.batch()`;
      - sin `defusedxml`;
      - una transacción por socio (deuda de PL6 de la revisión de Fase 4 del Sprint 3, S3-D95): alta, venta y primer pago de un socio confirman juntos y el siguiente socio abre otra transacción, así ninguna pide `lock_member` después del primer flush auditado de otro socio (orden de candados de D3, docstring de `core/locks.py`).
  - Gate: `slice-gate.sh cli` y `slice-gate.sh members`, cada uno con sus archivos.
- **Slice S4B-B2 · Backup y su verificación.** Historias: US-114 y US-115 (backend).
  - Rojo:
    - `tests/crypto/test_archive.py`;
    - `tests/worker/test_backup_check_evaluate.py` y `test_backup_check.py`;
    - `tests/core/test_health.py`, ampliada.
  - Verde:
    - `core/crypto/archive.py`, con `digest_file` y `verify_age_archive` (G-07);
    - `data_class` `backup.archive`;
    - job `backup_check`;
    - campo `backup` de `/health`. Con esto se cierra el criterio diferido de US-020.
  - Gate: `slice-gate.sh crypto`, `slice-gate.sh worker` y `slice-gate.sh main`, cada uno con sus archivos.
- **Slice S4B-B3 · Respaldo de la KEK y rotación de llave.** Historias: US-116 y US-030.
  - Rojo:
    - `tests/crypto/test_kek_backup.py`;
    - `tests/cli/test_export_kek.py`;
    - `tests/crypto/test_next_key_state.py`, `test_rotate.py`, `test_rotate_concurrency.py` y `test_rotate_index.py`;
    - `tests/test_cli_rotate_key.py`.
  - Verde:
    - `cli export-kek` y `cli verify-kek-backup`, con el verbo `export` en `crypto_ops`;
    - `cli rotate-key`:
      - transiciones de estado según el trigger de `0003`, hasta `retired`;
      - recifrado por lotes que se puede reanudar;
      - un solo job a la vez por clase;
      - índice solo con `--index`;
      - una llave `retired` no descifra;
      - `attachment.sensitive` responde 409 `rotation_not_supported` hasta el Sprint 6 (G-09).
  - Gate: `slice-gate.sh crypto` y `slice-gate.sh cli`, cada uno con sus archivos.
- **Slice S4B-B4 · Despliegue, arranque y ADR.** Historias: US-117, US-118 y US-119.
  - Rojo:
    - `tests/core/test_health_migrations.py`;
    - `tests/core/test_chain_hash_vector.py`;
    - `tests/architecture/test_adr_docs.py`.
  - Verde:
    - `/health` responde 200 solo con las migraciones en `head`;
    - documentación de operación;
    - ADR-001 (monolito modular y G-03);
    - ADR-002 (criptografía);
    - ADR de la cadena de auditoría, con vector fijo.
  - Gate: `slice-gate.sh main` con sus archivos.

Este sprint no tiene Waves 5a/5b: ninguna historia trae pantallas.

### Validación del sprint y release

- Los cinco flujos E2E críticos contra el stack de producción:
  - login y guardas;
  - registrar socio;
  - vender con pago;
  - anular pago;
  - verificar la auditoría.
- Ensayo completo en una base limpia: backup, `backup_check` y restauración.
- `rotate-key`: se interrumpe a mitad de camino y se reanuda.
- Prueba de rendimiento de la importación de 5.000 filas.
- Checklist de criterios diferidos de v0.1, todos cerrados. Se revisan en `verify-delivery`:
  - US-004, US-005, US-006 y US-007;
  - US-012 y US-018;
  - US-020 (los campos `backup` y migraciones);
  - US-066 y US-109.
- Paso humano: push, PR, merge y etiqueta `v0.1.0`.

## Migraciones que aplica

Ninguna. El esquema de v0.1 se cierra en `0013`.

## Endpoints que expone

Ninguno nuevo. `GET /health` y `GET /api/v1/health` agregan el campo `backup` y la comprobación de que las migraciones están en `head`.

## Tests de arquitectura que deben pasar

Todos corren en cada gate de slice (A-5).
- Todos los de los Sprints 0 a 4A.
- `test_no_cross_models.py`, ampliada en US-111, US-112 y US-119.
- `test_banned_imports.py`, ampliada en US-115, US-116 y US-119.
- `test_no_create_all.py`, ampliada en US-118.
- `test_adr_docs.py` (US-119).

## Riesgos y mitigación

1. **[HIGH] Operaciones irreversibles con llaves.** Una rotación que deja `retired` una llave que todavía tiene datos los pierde, y un backup sin su KEK no sirve.
   - Mitigación:
     - US-116 va antes que US-030 dentro del mismo slice;
     - la restauración se ensaya en una base limpia;
     - el conteo de pendientes tiene que ser cero antes de pasar a `retired`;
     - nada de esto se corre sobre datos reales sin confirmación humana.
2. **[HIGH] Infraestructura nueva: backup, `age`, rclone y arranque ordenado.**
   - Mitigación:
     - la Wave 0 se completa con smoke antes de la Wave 3a;
     - `deploy.sh` tiene rollback documentado.
3. **[MEDIUM] El destino del backup no está definido (P3).**
   - Mitigación: destino local por defecto, con un aviso en el README de operación.
4. **[MEDIUM] La release depende de cerrar todos los criterios diferidos.**
   - Mitigación: la checklist de la validación.
5. **[MEDIUM] Rendimiento de la importación.**
   - Mitigación: `test_import_members_perf.py` en un job `slow`.

## Definición de hecho del sprint

- Slices:
  - los 2 de Wave 0 quedan verificados con smoke;
  - los 4 de backend quedan confirmados con `checkpoint-commit.sh`.
- Pruebas:
  - `run-gates.sh` en verde, con cobertura global de `app` en 80 % o más, incluidos `cli.py` y `worker/`;
  - `tests/architecture` en verde.
- Migraciones: ciclo completo de Alembic de `0001` a `0013`, con `downgrade -1` y `upgrade head`.
- Smoke del stack de producción: los cinco servicios `healthy` y `/health` con `db`, `version` y `backup`.
- Evidencia:
  - de la restauración: archivo `age`, `latest.json`, salida de `backup_check` y una base restaurada con un socio legible;
  - de la rotación: la llave anterior `retired` con cero pendientes, y el `batch_id` en `crypto_ops`.
- Seguridad (`security-reviewer`):
  - el backup no contiene la KEK;
  - la identidad `age` está fuera de la imagen;
  - `export-kek` queda auditado;
  - `import-members` tiene límites;
  - `deploy.sh` no hace `push` ni usa `--force`.
- Paso humano: push, PR con CI en verde, merge y etiqueta `v0.1.0`.
- `verify-delivery` completo sobre el stack de producción.
