# Sprint 4 · Auditoría, tablero, worker y puesta en marcha (release v0.1)

- Versión: v0.1. Al cerrar este sprint se etiqueta `v0.1.0`.
- Épicas:
  - EP-11, salvo US-107;
  - EP-12;
  - EP-13;
  - US-094 de EP-09;
  - US-077 de EP-07;
  - US-080, US-081 y US-082 de EP-08;
  - US-030 de EP-02.
- Tamaño: 23 historias, 83 puntos y 389 h relativas.
- Rama: `feat/sprint-04-auditoria-operacion`.
- Historias del sprint: US-030, US-077, US-080, US-081, US-082, US-094, US-102, US-103, US-104, US-105, US-106, US-108, US-109, US-110, US-111, US-112, US-113, US-114, US-115, US-116, US-117, US-118, US-119.

## Objetivo

Dejar v0.1 lista para operar en el servidor del gimnasio:
- un worker recalcula los vencimientos cada mañana;
- la cadena de auditoría se consulta y se verifica desde pantalla y desde CLI;
- el tablero muestra el estado del negocio;
- hay datos de demostración e importación desde el Excel del box;
- el backup cifrado sale cada noche y su verificación aparece en `/health`;
- la KEK tiene un respaldo probado con una restauración real;
- la rotación de llaves funciona;
- despliegue y arranque son seguros y ordenados;
- los ADR documentan las decisiones que no se pueden deshacer.

## Demo al final del sprint

1. **Arranque en un servidor limpio.**
   - `docker compose -f infra/compose.yml up -d` levanta `db`, `api`, `worker`, `web` y `backup`, en el orden de US-118.
   - `/health` devuelve 200 solo con las migraciones en `0013_audit_verifications`, e incluye el campo informativo `backup`.
2. **Datos de demostración.** `docker compose run --rm tools uv run python -m app.cli seed --demo` crea planes, socios cifrados, membresías en todos los estados, pagos y anulaciones. Inicio muestra los KPI de membresías e ingresos del mes, y "Últimos movimientos" en frases sin entradas del sistema.
3. **Worker.** `docker compose run --rm worker uv run python -m app.worker.main --run-once expirations` con un `FrozenClock` adelantado pasa membresías a `expiring` y a `expired`. `worker.job_runs` registra la corrida, y una segunda corrida el mismo día no duplica nada.
4. **Auditoría.**
   - La pantalla filtra por tabla, usuario y fecha.
   - El detalle muestra antes y después, con "valor cifrado modificado" para los blobs.
   - "Verificar cadena" responde OK y queda en `audit.verifications`.
   - `cli verify-audit` da el mismo resultado.
   - La pestaña Historial de la ficha muestra los cambios del socio, de sus membresías y de sus pagos (N-31).
5. **Importación.** `cli import-members docs/plantillas/importar-socios.xlsx --as admin@...`:
   - importa con la cabecera exacta de Q17;
   - es idempotente por documento;
   - rechaza un archivo de más de 10 MB o de más de 5.000 filas.
6. **Backup y restauración.**
   - El backup de las 02:00 se corre a mano: sale un `pg_dump` más `uploads`, cifrado con `age`, y `latest.json`.
   - El job `backup_check` lo verifica con `verify_age_archive`.
   - `restore.sh` lo restaura en una base limpia con la KEK respaldada; un socio se lee y se revela.
7. **Rotación.** `cli rotate-key --data-class member.document --as admin@...`:
   - recifra por lotes y se puede reanudar;
   - deja la llave anterior en `retired` solo cuando no queda ningún dato cifrado con ella;
   - después de rotar, los socios siguen legibles.
8. **Planes.** Editar el precio de un plan no cambia las membresías vendidas (RN-04). No se puede dar de baja un plan que tenga membresías activas: responde 409.

## Dependencias de sprints anteriores

- **Sprint 3:**
  - US-083 y US-084 (`compute_status` y tabla);
  - US-089 (`_load_freezes_for`);
  - US-091 y US-092 (`refs_for`, `summary`, `count_active_by_plan`);
  - US-095 a US-100 (pagos, `summary(month)`);
  - US-073, US-074 y US-075 (ficha, `reveal`, edición);
  - US-086, US-090 y US-097 (para el seed de demostración).
- **Sprint 2:**
  - US-058 (`memberships_policy`);
  - US-069 y US-070 (`create`, `id_by_document`, `names_for`);
  - US-078 y US-079 (planes);
  - US-041 (`SYSTEM_USER_ID` y `active_admin_id_by_email`);
  - US-107 (eventos de seguridad).
- **Sprint 1:**
  - US-015 y US-016 (`record`, `verify_chain`, `subject_member_id`);
  - US-023 a US-029 (bus, `crypto_ops` y `export`);
  - US-033 (llaves);
  - US-039 (secretos).
- **Sprint 0:**
  - US-005 (Compose con `profiles: ["worker"]` y servicio `backup`);
  - US-020 (`register_health_check`).

Decisiones que aplica este sprint:
- G-05: historial por `subject_member_id`.
- G-06: `core/jobs.py`.
- G-07: `core/crypto/archive.py` y el binario `age`.
- G-08: `LogAlertSink` como único sink en v0.1.
- N-15: `--as` en todos los comandos.
- N-16: `backup` informativo en `/health`.
- N-21: propósitos `notify` y `auth_link`.
- N-22: baja de plan con 409.
- N-30: `audit.verifications`, `GET /audit/{seq}` y `GET /audit/verify/last`.
- N-31: historial de tres tablas.
- N-50: `job_runs`; backup a las 02:00 con 14 días de retención e `uploads`.
- Q10: últimos movimientos.
- Q17: plantilla de Excel.
- Refinamiento de US-030: una llave `retired` no descifra.
- Refinamiento de US-110: `display_name` y exclusión de `SYSTEM_USER_ID`.

## Historias en orden de ejecución

### Wave 0 · Infraestructura (`devops-wsl2-docker`)

- **Slice S4-W0-1 · Worker y arranque ordenado en Compose.** Son las tareas DevOps de US-113 y US-118.
  - Servicio `worker` sin `profiles`, con el mismo `api/Dockerfile` y otro comando.
  - Reintento de conexión.
  - `depends_on` con `service_healthy`.
  - Healthchecks de `db`, `api` y `web`.
  - Cierra el criterio diferido de US-005 del Sprint 0.
- **Slice S4-W0-2 · Contenedor de backup.** Son las tareas DevOps de US-114 y US-115.
  - `infra/backup/Dockerfile` y `run.sh`:
    - `pg_dump` más el volumen `uploads`;
    - cifrado con `age`;
    - subida con rclone a destino S3 compatible por `.env`, o local si no hay destino (P3);
    - `latest.json`.
  - Retención de 14 días.
  - Identidad `age` montada para verificar.
  - El binario `age` (BSD-3) entra en la imagen del api, para G-07.
- **Slice S4-W0-3 · Despliegue seguro.** Son las tareas DevOps de US-117 y de US-116.
  - `deploy.sh`, con un backup previo usando `--prefix`, `rollback-*.txt` y espera de salud.
  - `restore.sh`, que solo se nombra en el rollback y no se ejecuta en el deploy.
  - Volúmenes de respaldo de la KEK.
  - Gate de la Wave 0: `bash -n` de los scripts, smoke de Compose con los cinco servicios y una corrida manual del contenedor de backup en desarrollo.

### Wave 3a · Tests de backend en rojo (`backend-qa-executor`)

- **S4-B1:** `tests/worker`, que cubre registro de jobs, `claim_run`, `finish_run`, `--run-once` y `FrozenClock`.
- **S4-B2:**
  - `tests/worker/test_expirations.py`, incluida la marca `slow`;
  - `tests/cli/test_recompute_memberships.py`.
- **S4-B3:**
  - `tests/core/test_verify_chain.py`;
  - `tests/audit/test_verify.py`, `test_verify_concurrency.py`, `test_verify_performance.py` y `test_router_verify.py`;
  - `tests/cli/test_verify_audit.py`;
  - `tests/core/test_format_verify_message.py`.
- **S4-B4:**
  - `tests/audit/test_filters.py`, `test_list.py`, `test_list_coverage_v01.py`, `test_list_performance.py` y `test_router_list.py`;
  - `tests/audit/test_diff.py`, `test_get.py` y `test_router_get.py`.
- **S4-B5:**
  - `tests/audit/test_history_fields.py` y `test_member_history.py`;
  - `tests/members/test_router_member_audit.py`;
  - `tests/architecture/test_audit_subject.py`.
- **S4-B6:**
  - `tests/members/test_service_contact.py` y `test_validate_purpose.py`;
  - `tests/architecture/test_crypto_bus_importers.py`.
- **S4-B7:**
  - `tests/plans/test_merge_plan.py`, `test_service_update.py` y `test_router_update.py`;
  - `tests/integration/test_rn04_plan_price_change.py`;
  - `tests/plans/test_service_set_active.py` y `test_router_set_active.py`;
  - `tests/integration/test_plan_deactivation_with_memberships.py`;
  - `tests/plans/test_service_deactivate_or_fail.py` y `test_router_delete.py`.
- **S4-B8:**
  - `tests/dashboard`;
  - `tests/audit/test_recent.py`;
  - `tests/architecture/test_read_modules.py`.
- **S4-B9:**
  - `tests/cli/test_demo_dataset.py`, `test_seed_demo.py` y `test_seed_cli.py`;
  - `tests/cli/test_members_xlsx_parse.py`, `test_import_members.py` y `test_import_members_perf.py` (marca `slow`).
- **S4-B10:**
  - `tests/crypto/test_archive.py`;
  - `tests/worker/test_backup_check_evaluate.py` y `test_backup_check.py`;
  - `tests/core/test_health.py`, ampliada.
- **S4-B11:**
  - `tests/crypto/test_kek_backup.py`;
  - `tests/cli/test_export_kek.py`;
  - `tests/crypto/test_next_key_state.py`, `test_rotate.py`, `test_rotate_concurrency.py` y `test_rotate_index.py`;
  - `tests/test_cli_rotate_key.py`.
- **S4-B12:**
  - `tests/core/test_health_migrations.py`;
  - `tests/core/test_chain_hash_vector.py`;
  - `tests/architecture/test_adr_docs.py`.

### Wave 3b · Implementación de backend (`backend-implementor`)

- **Slice S4-B1 · Proceso worker programado.** Historia: US-113.
  - `core/jobs.py` (G-06), con `JobRun`, `claim_run`, `finish_run`, `last_run` y `run_job(name, fn)`.
  - **Migración `0012_worker_job_runs`:**
    - índice único `(job_name, run_date)`;
    - `details JSONB` con los intentos.
  - APScheduler a las 07:00 `America/Bogota`, con `--run-once`.
  - Un job puede abrir varias transacciones, una por lote.
  - Actor `SYSTEM_USER_ID`.
  - Gate: `slice-gate.sh worker && slice-gate.sh core/jobs`, más el ciclo de Alembic.
- **Slice S4-B2 · Job diario de vencimientos.** Historia: US-094.
  - `memberships.service.recompute_statuses(today)` en lotes.
  - `today` es `today_bogota()`.
  - Idempotente: una corrida por día.
  - Gate: `slice-gate.sh memberships && slice-gate.sh worker`.
- **Slice S4-B3 · Verificar la cadena desde API y CLI.** Historias: US-104 y US-105.
  - **Migración `0013_audit_verifications`:** append-only, con `started_at`, `finished_at`, `through_seq`, `ok`, `broken_at_seq`, `triggered_by`, `rows_checked` y `source`.
  - `run_verification` con lock asesor.
  - Un salto en `seq` cuenta como ruptura.
  - `POST /audit/verify` y `GET /audit/verify/last`.
  - `cli verify-audit --as`.
  - Gate: `slice-gate.sh audit`, más el ciclo de Alembic.
- **Slice S4-B4 · Consultar auditoría y ver el detalle.** Historias: US-102 y US-103.
  - Lista con filtros y `auth.service.names_for` e `ids_by_email`.
  - `GET /audit/{seq}`, registrado después de `/audit/verify/last`.
  - Diff de antes y después.
  - Gate: `slice-gate.sh audit`.
- **Slice S4-B5 · Historial del socio.** Historia: US-106.
  - `audit.service.list_for_subject(member_id)`: una sola consulta sobre `subject_member_id` (G-05). La columna ya existe desde `0002`.
  - `GET /members/{id}/audit`.
  - Gate: `slice-gate.sh audit && slice-gate.sh members`.
- **Slice S4-B6 · Contacto para avisos auditado.** Historia: US-077.
  - `contact_for_notification(member_id, fields, purpose)`, con propósitos `notify` y `auth_link`.
  - Escribe `crypto_ops` y la fila de auditoría con `SYSTEM_USER_ID`.
  - No tiene pantalla: lo consume EP-14 en el Sprint 5.
  - Gate: `slice-gate.sh members`.
- **Slice S4-B7 · Editar, activar y desactivar, y dar de baja un plan.** Historias: US-080, US-081 y US-082.
  - `PATCH /plans/{id}` sin afectar las vendidas (RN-04), con prueba de integración contra US-084.
  - `activate` y `deactivate`, con el rechazo `plan_inactive` en la venta.
  - `DELETE /plans/{id}`: borrado lógico, con 409 si hay membresías en `pending_payment`, `active`, `expiring` o `frozen`. Usa `count_active_by_plan` y el import perezoso plans→memberships de la lista blanca.
  - Gate: `slice-gate.sh plans`.
- **Slice S4-B8 · Tablero.** Historias: US-108 y US-110 (backend).
  - Contrato de `GET /dashboard` con los campos futuros en `null`: `notifications_today`, `attendance_week`, `sessions_today`, `wod_today` y `members_without_consent`.
  - KPI desde `memberships.summary()` y `payments.summary(month)`.
  - "Últimos movimientos" (Q10): 10 entradas de `members`, `memberships` y `payments`, excluido `SYSTEM_USER_ID`, con `display_name`.
  - Gate: `slice-gate.sh dashboard && slice-gate.sh audit`.
- **Slice S4-B9 · Datos de demostración e importación.** Historias: US-111 y US-112.
  - `cli seed --demo` idempotente. Llama a `sell` con `max_retroactive_days=None`.
  - `cli import-members`:
    - plantilla fija de Q17, validada por cabecera;
    - idempotente por documento;
    - límite de 10 MB y 5.000 filas;
    - cifrado por lotes con `bus.batch()`;
    - sin `defusedxml`.
  - Gate: `slice-gate.sh cli && slice-gate.sh members`.
- **Slice S4-B10 · Backup y su verificación.** Historias: US-114 y US-115 (backend).
  - `core/crypto/archive.py` (G-07), con `digest_file(path)` y `verify_age_archive(path, identity)` por subprocess.
  - `data_class` `backup.archive`.
  - Job `backup_check`.
  - Campo `backup` informativo en `/health`.
  - Gate: `slice-gate.sh crypto && slice-gate.sh worker`.
- **Slice S4-B11 · Respaldo de la KEK y rotación de llave.** Historias: US-116 y US-030.
  - `cli export-kek` y `cli verify-kek-backup`, con el verbo `export` en `crypto_ops`.
  - La prueba de restauración cierra con `reveal`.
  - `cli rotate-key`:
    - transiciones de estado que valida el trigger de `0003` (`next_key_state`), hasta `retired`;
    - recifrado por lotes que se puede reanudar;
    - un solo job por clase;
    - índice ciego solo con `--index`;
    - una llave `retired` no descifra;
    - `attachment.sensitive` responde 409 `rotation_not_supported` hasta el Sprint 6 (G-09).
  - Gate: `slice-gate.sh crypto`.
- **Slice S4-B12 · Despliegue, arranque y ADR.** Historias: US-117, US-118 y US-119 (backend y documentación).
  - `/health` responde 200 solo con las migraciones en `head`.
  - Docs de operación.
  - ADR-001 (monolito modular y regla G-03).
  - ADR-002 (criptografía: blob, N-02, firma y `digest`).
  - ADR de la cadena de auditoría (`canonical` y vector fijo).
  - Gate: `slice-gate.sh core/main`.

### Wave 5a · Tests de front en rojo (`frontend-qa-automation`)

- **S4-F1:**
  - `src/features/system/pages/AuditPage.test.tsx`;
  - `src/features/system/components/AuditDetailPanel.test.tsx` y `VerifyChainButton.test.tsx`;
  - `src/shared/lib/encryptedBlob.test.ts`.
- **S4-F2:**
  - `src/features/members/components/MemberHistoryTab.test.tsx`;
  - `src/features/members/lib/historyPhrase.test.ts`.
- **S4-F3:**
  - `src/features/dashboard`;
  - `tests/e2e/home.spec.ts`.
- **S4-F4:**
  - `src/features/plans/components/PlanForm.edit.test.tsx`;
  - `src/features/plans/pages/PlansPage.actions.test.tsx` y `PlansPage.delete.test.tsx`.

### Wave 5b · Implementación de front (`frontend-ux-engineer`)

- **Slice S4-F1 · Pantalla de auditoría.** Historias: US-102, US-103 y US-104 (front).
  - Lista con filtros.
  - Panel de antes y después.
  - Botón "Verificar cadena", con el enlace al `seq` roto.
  - Gate: `slice-gate.sh web/features/system`.
- **Slice S4-F2 · Historial de la ficha.** Historia: US-106 (front).
  - `HistoryAside` conectado; cierra el criterio diferido de US-066.
  - Frases por tabla.
  - Gate: `slice-gate.sh web/features/members`.
- **Slice S4-F3 · Inicio.** Historias: US-108, US-109 y US-110 (front).
  - `useDashboard`.
  - `KpiCard` con los estados de carga, error y `null`.
  - Enlaces a `/socios?membership_status=` y a `/pagos?from=&to=`.
  - Bloque "Últimos movimientos".
  - Gate: `slice-gate.sh web/features/dashboard`.
- **Slice S4-F4 · Acciones de planes.** Historias: US-080, US-081 y US-082 (front).
  - Editar.
  - Activar y desactivar.
  - Dar de baja, mostrando el 409.
  - Gate: `slice-gate.sh web/features/plans`.

### Validación del sprint

- Los cinco flujos críticos de E2E contra el stack completo:
  - login y guardas;
  - registrar socio;
  - vender con pago;
  - anular pago;
  - verificar la auditoría.
  Se corren `login.spec.ts`, `role-guards.spec.ts`, `sell-with-payment.spec.ts`, `home.spec.ts` y el resto de specs existentes.
- Worker con `--run-once` dos veces el mismo día, para probar la idempotencia.
- Ensayo completo en una base limpia: backup, `backup_check` y restauración.
- `rotate-key` interrumpido a mitad y luego reanudado.
- Prueba de rendimiento de la importación de 5.000 filas y de la verificación de la cadena.

## Migraciones que aplica

- `0012_worker_job_runs` (US-113).
- `0013_audit_verifications` (US-104 y US-105).

Ya no hacen falta: `0014_audit_subject_member` (G-05 va en `0002`), `0014_crypto_ops_purpose` y `0014_crypto_ops_export_verb`.

Condicional: `0014_payments_registered_by_idx`, solo si la prueba de rendimiento de US-098 la pide.

## Endpoints que expone

10 endpoints:
- `GET /api/v1/audit` (admin).
- `GET /api/v1/audit/verify/last` (admin), registrado antes que `/audit/{seq}`.
- `GET /api/v1/audit/{seq}` (admin).
- `POST /api/v1/audit/verify` (admin).
- `GET /api/v1/members/{id}/audit` (admin y coach).
- `GET /api/v1/dashboard` (admin y coach).
- `PATCH /api/v1/plans/{id}` (admin).
- `POST /api/v1/plans/{id}/activate` (admin).
- `POST /api/v1/plans/{id}/deactivate` (admin).
- `DELETE /api/v1/plans/{id}` (admin).

`GET /health` y `GET /api/v1/health` ganan el campo `backup` y el chequeo de migraciones en `head`.

## Tests de arquitectura que deben pasar

- Todos los de los Sprints 0 a 3.
- `tests/architecture/test_core_import_direction.py`, ampliada para `core/jobs.py`: solo la importan `app/worker/**` y el chequeo de salud (absorbe `test_core_jobs_imports.py`, US-113).
- `tests/architecture/test_service_import_graph.py`, ampliada con el par plans↔memberships (US-082).
- `tests/architecture/test_crypto_bus_importers.py` (US-077).
- `tests/architecture/test_audit_subject.py` (US-106).
- `tests/architecture/test_read_modules.py` (US-108 y US-110).
- `tests/architecture/test_no_cross_models.py`, ampliada (US-111, US-112 y US-119).
- `tests/architecture/test_banned_imports.py`, ampliada (US-115, US-116 y US-119).
- `tests/architecture/test_no_create_all.py`, ampliada (US-118).
- `tests/architecture/test_adr_docs.py` (US-119).

## Riesgos y mitigación

1. [HIGH] Operaciones irreversibles con llaves:
   - si se rota y la llave anterior pasa a `retired` con datos todavía cifrados con ella, esos datos se pierden;
   - un backup sin su KEK no sirve.
   - Mitigación:
     - US-116 va antes que US-030 en el mismo slice;
     - la restauración se ensaya en una base limpia antes del release;
     - la transición a `retired` se verifica con el conteo de pendientes;
     - ninguna de estas operaciones se ejecuta sobre datos reales sin confirmación humana (`CLAUDE.md`).
2. [HIGH] Es el sprint con más infraestructura nueva: worker, contenedor de backup, `age`, rclone y arranque ordenado. Un fallo de `depends_on` puede dejar el stack sin arrancar.
   - Mitigación: la Wave 0 completa con smoke antes de abrir la Wave 3a, y `deploy.sh` con espera de salud y rollback documentado.
3. [MEDIUM] Destino del backup sin definir (P3).
   - Mitigación: S3 compatible por `.env`, con destino local por defecto, y un aviso en el README de operación si queda local.
4. [MEDIUM] Rendimiento de la verificación de la cadena y de la importación.
   - Mitigación: pruebas `test_verify_performance.py` y `test_import_members_perf.py`, en un job aparte con la marca `slow`.
5. [MEDIUM] La release depende de cerrar todos los criterios diferidos de los Sprints 0 a 3.
   - Mitigación: una checklist de criterios diferidos en el reporte de `verify-delivery`:
     - de US-005, `tools` (Sprint 1) y `worker` (aquí);
     - de US-020, el campo `backup` (aquí);
     - de US-066, el historial (aquí).

## Definición de hecho del sprint

- Los 3 slices de Wave 0, los 12 de backend y los 4 de front confirmados con `checkpoint-commit.sh`.
- `scripts/workflow/run-gates.sh` en verde, con cobertura del 80 % en todo `src/app` y en el front.
- `cd api && uv run pytest tests/architecture -q` en verde.
- Ciclo de Alembic completo de `0001` a `0013`, más `downgrade -1` y `upgrade head`.
- `docs/openapi.json` y los tipos del front regenerados.
- E2E en verde contra el stack completo, con los cinco flujos críticos.
- Smoke del stack de producción (`infra/compose.yml` sin `compose.dev.yml`), con los cinco servicios `healthy` y `/health` con `db`, `version` y `backup`.
- Ensayo de restauración con evidencia:
  - archivo `age`;
  - `latest.json`;
  - salida de `backup_check`;
  - base restaurada con un socio legible.
- Rotación con evidencia: la llave anterior queda `retired` con cero pendientes, y `crypto_ops` muestra el `batch_id` de la rotación.
- Seguridad, revisada por `security-reviewer`:
  - el backup no contiene la KEK;
  - la identidad `age` está fuera de la imagen;
  - `export-kek` está auditado;
  - el worker no expone puertos;
  - `import-members` tiene límites y no usa parsers XML inseguros;
  - la auditoría no muestra material de llave;
  - `deploy.sh` no ejecuta `git push` ni `--force`.
- `verify-delivery` completo, con los dos pilares, sobre el stack de producción. Se etiqueta `v0.1.0`.
