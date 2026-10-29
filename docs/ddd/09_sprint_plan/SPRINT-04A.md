# Sprint 4A · Worker, auditoría verificable, tablero y planes restantes

> **Corregido en S4A-W0-1.** El plan de ejecución es `docs/ddd/blueprints/sprint-04a-plan.md` (enmiendas E1 a E10 de la crítica 1) y las decisiones están en `docs/ddd/DECISIONES.md`, sección "Sprint 4A" (S4A-D1 a S4A-D121). Donde este texto choque con ellos, mandan ellos. Correcciones de contrato de este archivo:
> - Las pruebas de rendimiento usan el marcador `perf` (`-m perf`), no `slow`; nunca entran al gate (`-m "not perf"`).
> - `0014` no se crea: `audit.audit_log.subject_member_id` ya viene de `0002`; el sprint aplica solo `0012_worker_job_runs` y `0013_audit_verifications` (S4A-D19, S4A-D38). `0014_payments_registered_by_idx` tampoco entra.
> - `GET /audit` filtra por `from`, `to`, `user_id`, `table` (`esquema.tabla`), `record_id`, `subject_member_id`, `action`, `q`, `limit` y `offset` (hasta 100.000), con rangos acotados (S4A-D16, S4A-D45, S4A-D46).
> - `contact_for_notification(session, member_id, purpose)`, no `(member_id, fields, purpose)` (S4A-D21, S4A-D50).
> - US-041 no creó `display_name`: en 4A el nombre visible es la parte local del correo y "Sistema" para `SYSTEM_USER_ID`; la columna llega en v0.2 con EP-04 (S4A-D19).
> - `/health` no lee `worker.job_runs` en 4A (pasa a v0.2): el worker tiene healthcheck por latido (S4A-D8, S4A-D56).
> - La auditoría se verifica con "Verificar ahora" (`POST /audit/verify`) con las cubetas `audit-verify` (3 por minuto) y `audit-verify-hour` (20 por hora), no con `admin-write` (S4A-D14, S4A-D47).
> - `GET /members/{id}/audit` y `GET /dashboard` (y `GET /audit`, `GET /audit/{seq}`) consumen la cubeta `staff-read` y declaran 429 (S4A-D45, S4A-D27).
> - `--date` solo con `--simulate`, `ENV=dev` y una base `*_sim` o `apex_test` (S4A-D48, enmienda E5); la demo con fecha corre contra `apex_sim` en `apex-db_test-1`, nunca contra `apex-db-1` (S4A-D63).
> - `datosDeBase()` vive en `web/tests/e2e/helpers/stack.ts` y devuelve credenciales, no cuenta tablas: la verificación es `grep -rn "job_runs\|audit_log" web/tests` vacío (S4A-D59).
> - `list_for_subject(member_id)` es `member_history(session, member_id, page, q)` (S4A-D20).
> - `VERIFY_BATCH_SIZE` = 500, con lectura por rango acotado de `seq` (S4A-D120), y `SYNC_VERIFY_MAX_ROWS` = 100.000 (valor final, S4A-D91); ajustan S4A-D47 y S4A-D13.
> - El coach no ve ingresos: `income_month_cop` llega `null` y las frases de pagos no llevan monto (S4A-D118).
> - El enlace de ingresos del tablero es `/pagos?from=AAAA-MM-DD&to=AAAA-MM-DD` con días civiles, no un instante UTC (S4A-D121).

- **Versión:** v0.1. Es la primera mitad del cierre; la release la hace el Sprint 4B.
- **Épicas:**
  - EP-11, salvo US-107;
  - EP-12;
  - US-113 de EP-13;
  - US-094 de EP-09;
  - US-077 de EP-07;
  - US-080, US-081 y US-082 de EP-08.
- **Tamaño:** 14 historias, 44 puntos, 215 h relativas.
- **Rama:** `feat/sprint-04a-worker-auditoria-tablero`.
- **Historias del sprint:** US-077, US-080, US-081, US-082, US-094, US-102, US-103, US-104, US-105, US-106, US-108, US-109, US-110, US-113.

## Objetivo

Que el sistema haga solo lo que pasa todos los días y que se pueda demostrar lo que pasó:
- **Worker:** recalcula los vencimientos cada mañana.
- **Auditoría:** se consulta, se detalla y se verifica, tanto desde la pantalla como por CLI.
- **Ficha del socio:** muestra su historial.
- **Tablero:** muestra los KPI y los últimos movimientos.
- **Planes:** se pueden editar, activar o desactivar y dar de baja sin romper lo que ya se vendió.

## Demo al final del sprint

`docker compose` abrevia `docker compose -f infra/compose.yml -f infra/compose.dev.yml`. Dentro de los contenedores, los comandos van sin `uv run`.

1. `docker compose up -d --build` levanta también el servicio `worker` (ya sin `profiles`). En este equipo: imágenes con `docker buildx build --load --network host --allow network.host` y `up -d --no-build` (RUNBOOK §7).
   - `docker compose exec api alembic current` muestra `0013_audit_verifications`.
2. Con los socios y las membresías de la demo del Sprint 3:
   - `docker compose run --rm worker python -m app.worker.main --run-once expirations` sobre la base viva, sin fecha, pasa a `expiring` y `expired` lo que el calendario real exige; la fecha adelantada se demuestra con `--date 2026-11-01 --simulate` contra la copia `apex_sim` (S4A-D48, S4A-D63), nunca contra `apex-db-1`;
   - `worker.job_runs` registra la corrida;
   - una segunda corrida el mismo día no duplica nada.
3. Auditoría:
   - la pantalla filtra por tabla, usuario y fecha;
   - el detalle muestra antes y después; los valores cifrados salen como "Cifrado" con su `key_id` (el servidor nunca entrega el blob, S4A-D52);
   - "Verificar ahora" responde OK y queda en `audit.verifications` con el ancla `through_hash` (S4A-D43);
   - `docker compose run --rm tools verify-audit --as admin@...` da el mismo resultado.
4. La pestaña Historial de la ficha muestra los cambios del socio, de sus membresías y de sus pagos (N-31).
5. Inicio muestra:
   - los KPI de membresías y, en el admin, los ingresos del mes (el coach ve «Solo administración», S4A-D118);
   - "Últimos movimientos" en frases, sin entradas del sistema.
6. Planes:
   - editar el precio no cambia las membresías vendidas (RN-04);
   - desactivar un plan impide venderlo;
   - dar de baja un plan con membresías activas responde 409.

## Dependencias de sprints anteriores

- **Sprint 3:**
  - US-083 y US-084;
  - US-089 (`_load_freezes_for`);
  - US-091 y US-092 (`refs_for`, `summary`, `count_active_by_plan`);
  - US-095 a US-100;
  - US-073 a US-075.
- **Sprint 2:**
  - US-058;
  - US-069 y US-070;
  - US-078 y US-079;
  - US-041 (sin `display_name`: no lo creó; S4A-D19);
  - US-107.
- **Sprint 1:**
  - US-015 y US-016 (`record`, `verify_chain`, `subject_member_id`);
  - US-029;
  - el kit (`HistoryAside`).
- **Sprint 0:** US-005 (`worker` con `profiles`).

Decisiones que se aplican:
- G-05, G-06 y G-08 (`LogAlertSink`);
- N-15, N-21, N-22, N-30 y N-31;
- Q10;
- el refinamiento de US-110.

## Historias en orden de ejecución

Patrón de v0.1: en cada slice van primero el Rojo (stubs y pruebas) y después el Verde. El gate usa los archivos del slice más `tests/architecture`, y después va el checkpoint.

Desde este sprint, `src/app/cli.py` y `src/app/worker/` entran en la cobertura: el Verde de S4A-B1 quita el `omit` de `[tool.coverage.run]` en `api/pyproject.toml` (M-6, S4A-D39; no existe `--cov-omit`).

### Wave 0 · Infraestructura (`devops-wsl2-docker`)

- **Slice S4A-W0-1 · Worker en Compose (solo preparación).** Son las tareas DevOps de US-113 que no necesitan código del worker.
  - Se define el servicio `worker` con la misma imagen y el comando `python -m app.worker.main`, `depends_on` de `db` y `api` `healthy`, sin volúmenes, endurecido (`read_only`, `tmpfs /tmp`, `cap_drop ALL`, `no-new-privileges`; S4A-D49) y healthcheck por latido (S4A-D8; no por `job_runs`), **pero se conserva `profiles: ["worker"]`**: todavía no existe `app/worker/main.py` y el contenedor entraría en bucle de reinicios (CRITICA-2 N-3). `worker` y `tools` montan `api/src` y `api/migrations` en solo lectura en `compose.dev.yml`.
  - Gate: `docker compose config` valida el archivo; `test_compose_config.sh` en verde; smoke de Compose **sin** el perfil `worker`; `slice-gate.sh architecture` que sella.
- **Slice S4A-W0-2 · Activar el worker.** Se ejecuta **después de cerrar S4A-B1**.
  - Se quita `profiles: ["worker"]`.
  - Cierra el criterio diferido de US-005.
  - Gate: smoke de Compose con `worker` en marcha, `healthy` y sin reinicios, y `docker compose run --rm worker python -m app.worker.main --run-once expirations` dos veces: la primera acepta 0 o 3 y la segunda exige 0 (enmienda E6); `--status expirations` con `result: ok`. `grep -rn "job_runs\|audit_log" web/tests` vacío (S4A-D59).
  - **Cumplido** (checkpoint de S4A-W0-2): perfil fuera de `infra/compose.yml`, `apex-api:local` reconstruida con buildx, `worker` `healthy` con 0 reinicios, `--run-once expirations` ×2 con salida 0 sobre la misma fila y `--status` con `result: ok`; `compose-smoke.sh` gana esos pasos. Criterio diferido de US-005 cerrado. Evidencia en `docs/scratch/sprint-04a.md`.

### Waves 3a/3b · Backend, alternadas por slice

- **Slice S4A-B1 · Proceso worker programado.** Historia: US-113.
  - **Rojo:** `tests/worker` (registro de jobs, `claim_run`, `finish_run`, `--run-once`, `--date --simulate`, `FrozenClock`), `tests/core/test_alerts.py`, `tests/cli/test_export_openapi_cli.py` y `test_init_keys_cli.py`, con stubs de `core/jobs.py`, `core/alerts.py` y `worker/`. El job `expirations` nace como marcador verde (`details={"placeholder_ok": 1}`, S4A-D64).
  - **Verde:**
    - `core/jobs.py` (G-06);
    - migración `0012_worker_job_runs`;
    - APScheduler a las 07:00 `America/Bogota`;
    - actor `SYSTEM_USER_ID` fijado antes del reclamo (S4A-D55);
    - latido condicionado a `SELECT 1` (S4A-D56).
  - **Gate:** `slice-gate.sh worker` y `slice-gate.sh core/jobs`, cada uno con sus archivos, más el ciclo de Alembic.
- **Slice S4A-B2 · Job diario de vencimientos.** Historia: US-094.
  - **Rojo:**
    - `tests/worker/test_expirations.py`, también con `-m perf`;
    - `tests/cli/test_recompute_memberships.py`.
  - **Verde:**
    - `recompute_statuses(session_factory, *, today)` en `memberships/expirations.py`: lectura de candidatas y una transacción por socio con `lock_member` (S4A-D2, S4A-D57), con `today_bogota()`;
    - idempotente: una sola fila de `job_runs` por día;
    - `recompute-memberships [--date --simulate] [--as]` (S4A-D48, S4A-D53).
  - **Gate:** `slice-gate.sh memberships`, `slice-gate.sh worker` y `slice-gate.sh cli`, con los archivos de cada uno.
- **Slice S4A-B3 · Verificar la cadena desde la API y desde la CLI.** Historias: US-104 y US-105.
  - **Rojo:**
    - `tests/core/test_verify_chain.py`;
    - `tests/audit/test_verify.py`, `test_verify_concurrency.py`, `test_verify_performance.py` y `test_router_verify.py`;
    - `tests/cli/test_verify_audit.py`;
    - `tests/core/test_format_verify_message.py`.
  - **Verde:**
    - migración `0013_audit_verifications`;
    - `run_verification` con lock asesor en conexión `AUTOCOMMIT`, lotes de 500 por rango acotado de `seq` (S4A-D120) y ancla `through_hash` (S4A-D43, S4A-D44, S4A-D47); un salto en `seq` cuenta como ruptura (`broken_at_seq`);
    - `POST /audit/verify` y `GET /audit/verify/last`;
    - `cli verify-audit --as`.
    - Hecho en el Verde: `audit.verifications` guarda `through_hash char(64)` (el `hash` de la fila `through_seq`, o `ZERO_HASH` con la cadena vacía) y la siguiente verificación lo exige como ancla; tres cubetas nuevas en el catálogo (12 cubetas y 11 variables `USER_*`): `staff-read` (`USER_READ_LIMIT_PER_MIN`, 120 por minuto; la consumen B4, B5 y B8), `audit-verify` (`USER_AUDIT_VERIFY_LIMIT_PER_MIN`, 3 por minuto) y `audit-verify-hour` (`USER_AUDIT_VERIFY_LIMIT_PER_HOUR`, 20 por hora); el job `e2e-stack` de la CI las sube ×100 (E9). `SYNC_VERIFY_MAX_ROWS` calibrado en 100.000 (S4A-D91).
  - **Gate:** `slice-gate.sh audit`, `slice-gate.sh core/audit`, `slice-gate.sh core/audit_verify` y `slice-gate.sh cli`, con los archivos de cada uno, más el ciclo de Alembic.
- **Slice S4A-B4 · Consultar la auditoría y ver el detalle.** Historias: US-102 y US-103.
  - **Rojo:**
    - `tests/audit/test_filters.py`, `test_list.py`, `test_list_coverage_v01.py`, `test_list_performance.py` y `test_router_list.py`;
    - `tests/audit/test_diff.py`, `test_get.py` y `test_router_get.py`.
  - **Verde:**
    - lista con filtros;
    - `GET /audit/{seq}`, registrado después de `/audit/verify/last`;
    - diff de antes y después.
  - **Gate:** `slice-gate.sh audit <archivos de Rojo>`.
- **Slice S4A-B5 · Historial del socio.** Historia: US-106.
  - **Rojo:**
    - `tests/audit/test_history_fields.py` y `test_member_history.py`;
    - `tests/members/test_router_member_audit.py`;
    - `tests/architecture/test_audit_subject.py`.
  - **Verde:**
    - `member_history(session, member_id, page, q)` sobre `subject_member_id` (G-05, S4A-D20);
    - `GET /members/{id}/audit`.
  - **Gate:** `slice-gate.sh audit` y `slice-gate.sh members`, con los archivos de cada uno.
- **Slice S4A-B6 · Contacto para avisos auditado.** Historia: US-077.
  - **Rojo:**
    - `tests/members/test_service_contact.py` y `test_validate_purpose.py`;
    - `tests/architecture/test_crypto_bus_importers.py`.
  - **Verde:**
    - `contact_for_notification(session, member_id, purpose)`, con propósitos `notify` y `auth_link` (S4A-D21);
    - escribe en `crypto_ops` y en la auditoría.
    - Lo consume EP-14 en el Sprint 5.
  - **Gate:** `slice-gate.sh members <archivos de Rojo>`.
- **Slice S4A-B7 · Editar, activar o desactivar y dar de baja un plan.** Historias: US-080, US-081 y US-082.
  - **Rojo:**
    - `tests/plans/test_merge_plan.py`, `test_service_update.py` y `test_router_update.py`;
    - `tests/integration/test_rn04_plan_price_change.py`;
    - `tests/plans/test_service_set_active.py` y `test_router_set_active.py`;
    - `tests/integration/test_plan_deactivation_with_memberships.py`;
    - `tests/plans/test_service_deactivate_or_fail.py` y `test_router_delete.py`.
  - **Verde:**
    - `PATCH` sin efecto sobre las membresías vendidas;
    - `activate` y `deactivate`, con `plan_inactive` en la venta;
    - `DELETE` lógico, con 409 `plan_has_active_memberships` si hay membresías activas (solo el conteo); usa `count_active_by_plan` mediante un import perezoso de la lista blanca;
    - columna "Socios con él" por `active_members_count` (`counts_active_by_plans`, S4A-D25).
  - **Gate:** `slice-gate.sh plans` con sus archivos, más los dos archivos de `tests/integration`.
- **Slice S4A-B8 · Tablero.** Historias: US-108 y US-110 (backend).
  - **Rojo:**
    - `tests/dashboard`;
    - `tests/audit/test_recent.py`;
    - `tests/architecture/test_read_modules.py`.
  - **Verde:**
    - contrato de `GET /dashboard` con los campos futuros en `null`;
    - KPI;
    - "Últimos movimientos" (Q10), sin `SYSTEM_USER_ID` y con el nombre de `user_names_for` (parte local del correo; S4A-D19, S4A-D54); una consulta por tabla (S4A-D51).
    - Por ahora, las pruebas de cuadre usan factories en lugar de US-111.
  - **Gate:** `slice-gate.sh dashboard` y `slice-gate.sh audit`, con los archivos de cada uno.

### Waves 5a/5b · Front, alternadas por slice

- **Slice S4A-F1 · Pantalla de auditoría.** Historias: US-102, US-103 y US-104 (front).
  - **Rojo:**
    - `AuditPage.test.tsx`, `AuditDetailPanel.test.tsx` y `VerifyChainButton.test.tsx`;
    - `src/shared/lib/encryptedBlob.test.ts`.
  - **Verde:**
    - lista;
    - panel de antes y después;
    - verificar, con enlace al `seq` roto.
  - **Gate:** `slice-gate.sh web/system` y `slice-gate.sh web/shared`, con los archivos de cada uno.
- **Slice S4A-F2 · Historial de la ficha.** Historia: US-106 (front).
  - **Rojo:** `MemberHistoryTab.test.tsx` y `historyPhrase.test.ts`.
  - **Verde:** `HistoryAside` conectado. Cierra el criterio diferido de US-066.
  - **Gate:** `slice-gate.sh web/members <archivos de Rojo>`.
- **Slice S4A-F3 · Inicio.** Historias: US-108, US-109 y US-110 (front).
  - **Rojo:** pruebas en `src/features/dashboard` y `tests/e2e/home.spec.ts`.
  - **Verde:**
    - `useDashboard`;
    - `KpiCard` con estados de carga, error y `null`;
    - enlaces a `/socios` y `/pagos`;
    - "Últimos movimientos".
  - **Gate:** `slice-gate.sh web/dashboard <archivos de Rojo>`.
  - **Criterio diferido:** T8 de US-109 (cuadre con los datos de demostración) se cierra en el Sprint 4B, con US-111.
- **Slice S4A-F4 · Acciones de planes.** Historias: US-080, US-081 y US-082 (front).
  - **Rojo:** `PlanForm.edit.test.tsx`, `PlansPage.actions.test.tsx` y `PlansPage.delete.test.tsx`.
  - **Verde:** editar, activar o desactivar y dar de baja, mostrando el 409.
  - **Gate:** `slice-gate.sh web/plans <archivos de Rojo>`.

### Validación del sprint

Detalle de cada paso en `docs/ddd/blueprints/sprint-04a-plan.md`, sección 7:
- V1 · Fusión del worktree del front y documentos.
- V2 · Stack desde cero de código y ciclo de Alembic (con `$DC stop worker` antes de un `downgrade` que borre `worker.job_runs`, enmienda E4).
- V3 · Datos reales antes de navegar.
- V4 · E2E contra el stack (preview y stack dos veces), con `home.spec.ts` y todos los specs anteriores.
- V5 · Rendimiento (`-m perf`: vencimientos, verificación, lista, `recent` y tablero).
- V6 · Smoke con evidencia SQL y `verify_chain`.
- V7 · Demo (los 6 puntos de arriba).
- V8 · Repetición e idempotencia (`--run-once expirations` dos veces el mismo día).
- V9 · Gates completos (`run-gates.sh`).
- V10 · Revisión de seguridad posterior.
- V11 · `verify-delivery`.
- V12 · Cierre documental y paso humano (push y PR).

## Migraciones que aplica

- `0012_worker_job_runs` (US-113).
- `0013_audit_verifications` (US-104 y US-105).

Ya no hacen falta `0014_audit_subject_member`, `0014_crypto_ops_purpose` ni `0014_crypto_ops_export_verb`. Queda como condicional `0014_payments_registered_by_idx`.

## Endpoints que expone

10 endpoints:
- `GET /api/v1/audit` (admin).
- `GET /api/v1/audit/verify/last` (admin), registrado antes de `/audit/{seq}`.
- `GET /api/v1/audit/{seq}` (admin).
- `POST /api/v1/audit/verify` (admin; cubetas `audit-verify` y `audit-verify-hour`, S4A-D47).
- `GET /api/v1/members/{id}/audit` (admin y coach; cubeta `staff-read`, S4A-D45).
- `GET /api/v1/dashboard` (admin y coach; cubeta `staff-read`; el coach recibe `income_month_cop` `null`, S4A-D118).
- `PATCH /api/v1/plans/{id}` (admin).
- `POST /api/v1/plans/{id}/activate` (admin).
- `POST /api/v1/plans/{id}/deactivate` (admin).
- `DELETE /api/v1/plans/{id}` (admin).

## Tests de arquitectura que deben pasar

Corren en cada gate de slice (A-5).
- Todos los de los Sprints 0 a 3.
- `test_core_import_direction.py`, ampliada para `core/jobs.py` y `core/alerts.py` (absorbe `test_core_jobs_imports.py`).
- `test_worker_boundaries.py` (S4A-D10, S4A-D73), `test_contact_callers.py` (S4A-D50), `test_expirations_lock_order.py` (S4A-D57) y `test_user_refs_scope.py` (S4A-D54).
- `test_service_import_graph.py` y `LAZY_IMPORT_WHITELIST`, ampliadas con el par plans↔memberships (US-082; no `test_service_import_cycles.py`).
- `test_crypto_bus_importers.py` (US-077).
- `test_audit_subject.py` (US-106).
- `test_read_modules.py` (US-108 y US-110).

## Riesgos y mitigación

1. **[MEDIUM]** El orden fijo de las migraciones (`0012` antes que `0013`) obliga a que el worker vaya antes que la verificación de la cadena.
   - Mitigación: S4A-B1 va primero y bloquea.
2. **[MEDIUM]** El worker podría duplicar el recálculo si corre dos veces.
   - Mitigación: índice único `(job_name, run_date)` y prueba de doble corrida.
3. **[MEDIUM]** La verificación de la cadena puede ser lenta con muchas filas.
   - Mitigación: `test_verify_performance.py` y lock asesor.
4. **[MEDIUM]** Al quitar el `omit` de coverage puede bajar la cobertura global.
   - Mitigación: las pruebas de `tests/worker` y `tests/cli` entran en este mismo sprint, y `run-gates.sh` se corre después de B2.
5. **[LOW]** Sin datos de demostración, el tablero se prueba con factories.
   - Mitigación: el criterio diferido de US-109 queda declarado y se cierra en 4B.

## Definición de hecho del sprint

- El slice de Wave 0, los 8 de backend y los 4 de front, confirmados con `checkpoint-commit.sh`.
- `run-gates.sh` en verde, con cobertura global de `app` de al menos 80 %, ya sin el `omit` de coverage.
- `cd api && uv run pytest tests/architecture -q` en verde.
- Ciclo de Alembic sobre `0013`.
- `docs/openapi.json` y tipos del front regenerados.
- E2E en verde.
- Smoke con `worker`, con evidencia de `job_runs` y de `audit.verifications`.
- Seguridad (`security-reviewer`):
  - la auditoría no muestra material de llave;
  - el historial respeta el rol;
  - `verify-audit` queda atribuido con `--as`;
  - el worker no expone puertos.
- Paso humano: push, PR con CI en verde y merge.
- `verify-delivery`.

## Deuda con dueño (registrada durante el sprint)

- S4A-D98 (revisión de S4A-B3): los triggers `audit_log_forbid_mutation` y `audit_log_forbid_truncate` de `0002` tienen `tgenabled = 'O'` y no disparan bajo `session_replication_role = replica`; la cadena y el ancla lo detectan. Dueño: Sprint 4B, migración `0014_audit_log_triggers_always` (nunca se edita `0002`).
- V6 (LOW aceptado; DECISIONES, "V5/V10 · Correcciones finales"): `audit.forbid_mutation()` de `0002` dice "audit.audit_log es append-only" también al rechazar un cambio de `audit.verifications` (sus triggers de `0013` la reutilizan); el rechazo es correcto, solo el texto nombra la otra tabla. Texto fijo de una migración aplicada: no se edita. Dueño: Sprint 4B, junto a `0014_audit_log_triggers_always` (S4A-D98).
- S4A-D103 (revisión de S4A-B3): las cubetas por usuario (`audit-verify`, `audit-verify-hour`, `staff-read` y las anteriores) viven en la memoria del único proceso de Uvicorn; restricción conocida junto a S3-D93, sin dueño de código hasta que el api pase a varios procesos.
- S4A-D106 c (revisión de S4A-B4, `security-reviewer` MEDIUM): `GET /audit` con `action` solo, o con `at` más otro filtro, cuenta sin índice líder (el conteo ya está acotado a 100.001 filas y `record_id` exige `table`). Si el crecimiento de `audit.audit_log` lo exige, índices `(action, seq DESC)` y `(record_id)` en `0014_audit_log_indexes` (o en la migración de auditoría del Sprint 4B que venga primero, junto a S4A-D98). Dueño: Sprint 4B.
- S4A-D115 (Verde de S4A-B8, M-7): con muchas lecturas (`reveal`) recientes de `members.members`, la consulta por tabla de `audit.service.recent` usa `uq_audit_log_seq` hacia atrás con filtro en vez de `ix_audit_log_table_seq` (20,9 ms con 50.000 lecturas; tope 50 ms; la prueba `perf` acepta los dos índices y nunca `Seq Scan`). Si el crecimiento lo exige, índice `(table_name, action, seq DESC)` (o parcial sobre `insert`, `update` y `delete`) en la misma migración de índices de la auditoría que S4A-D106 c. Dueño: Sprint 4B. El mismo índice cubre el caso de muchas escrituras recientes del sistema (S4A-D119 b: hoy 0,8 ms con 5.000).
- S4A-D118 (revisión de S4A-B8, MEDIUM): el coach recibe `GET /dashboard` sin `income_month_cop` (`null`) ni montos en las frases; ajusta S4A-D29. Dueño del front: S4A-F3 (KPI de ingresos "Solo administración" cuando llega `null`).
- S4A-V1 (observación del cuaderno de F2, no es una marca `DESIGN-GAP`): en la barra `Tabs` de la ficha, con nueve pestañas, a 1440 px "Membresías" queda recortada cuando la activa es Historial; y la etiqueta "automático (aviso)" del historial no tiene contraste verificado en navegador. Dueño: Sprint 4B, pantalla de ficha (S4A-V1, `DECISIONES.md`, "Deuda de front con dueño").
