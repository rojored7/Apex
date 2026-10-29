# Sprint 4A · Worker, auditoría verificable, tablero y planes restantes

> **Corregido en S4A-W0-1.** El plan de ejecución es `docs/ddd/blueprints/sprint-04a-plan.md` (enmiendas E1 a E10 de la crítica 1) y las decisiones están en `docs/ddd/DECISIONES.md`, sección "Sprint 4A" (S4A-D1 a S4A-D128). Donde este texto choque con ellos, mandan ellos. Correcciones de contrato de este archivo:
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

## Estado al cierre del sprint (documentación)

Fecha: 2026-10-29. Rama `feat/sprint-04a-worker-auditoria-tablero`, HEAD `39a4b31` antes de esta documentación. Sin push: el push y el PR los hace una persona (ver "Pendiente humano"). Las decisiones están en `docs/ddd/DECISIONES.md`, sección "Sprint 4A" (S4A-D1 a S4A-D128), con las subsecciones "Estado al cierre del Sprint 4A" y "Dueños asignados al cierre del Sprint 4A". El cuaderno de validación es `docs/scratch/sprint-04a.md`.

### Slices ejecutados

Los 14 slices del plan tienen su checkpoint (`chore(checkpoint)`; `git log --oneline` da los hashes):
- **Wave 0:** W0-1 (worker en Compose, solo preparación) y W0-2 (activación del worker).
- **Backend:** B1 (proceso worker, `core/jobs`, `core/alerts`, `0012`), B2 (job de vencimientos y `recompute-memberships`), B3 (verificación de la cadena, `0013`), B4 (consulta y detalle de la auditoría), B5 (historial del socio), B6 (contacto para avisos), B7 (editar, activar, desactivar y dar de baja planes) y B8 (tablero).
- **Front** (worktree `.claude/worktrees/sprint-04a-front`, S4A-D62; orden F1, F2, F4, F3): F1 (pantalla de auditoría), F2 (historial de la ficha), F4 (acciones de planes) y F3 (Inicio).
- **Correcciones y cierre:** V5 y V10 (`360d816`, S4A-D127), V11 (avisos del verify-delivery, S4A-D128, `89998b0`) y V9/V12 (`39a4b31` y la documentación de cierre).

### Conteos finales

- **API:** 4.995 pruebas en verde con `-m "not perf"`, 3 saltadas (NTFS) y 23 `perf` fuera del gate. Cobertura global de `app`: **97 %** sin `omit` (`run-gates.sh`, V9).
- **Arquitectura** (`tests/architecture`): 394 en verde, 0 saltadas.
- **Web:** 3.125 pruebas en verde; cobertura de **97,87 %** en sentencias y **98,82 %** en líneas; build y `npm run licenses` en verde (MIT 12, ISC 1).
- **Scripts:** `test_check_key_files`, `test_images_pinned`, `test_nginx_conf` y `test_compose_config` en verde (4 de 4); `scripts/workflow/tests/run.sh` 5 de 5; `pre-commit --all-files` en verde.
- **Dependencias y secretos:** `npm audit --omit=dev --audit-level=high` y `npm audit --audit-level=high` con 0 vulnerabilidades; `pip-audit` sin vulnerabilidades conocidas; gitleaks sobre 177 commits sin fugas.
- **E2E:** `e2e:stack` **40/40** en dos corridas seguidas (59,0 s y 57,6 s), 0 flaky; preview **161/161**.
- **Migraciones:** `0012_worker_job_runs` y `0013_audit_verifications`. Ciclo `0013 → 0011 → 0013` sobre `apex-db-1` con el worker parado; 244 pruebas de migraciones en `db_test`.
- **Contrato:** 10 endpoints y `active_members_count` en `GET /plans`; `docs/openapi.json` pasa de 53 a **63** operaciones.
- **Decisiones:** S4A-D1 a S4A-D128 (128).

### Tiempos `perf` (V5, tras S4A-D127)

- Vencimientos, 1.000 socios y 3.000 membresías: **31,5 s** (tope 60 s).
- Verificación de 100.000 filas: **2,20 a 2,26 s** en total; peor bloque síncrono **17,9 a 23,2 ms** (tope 100 ms).
- Lista de auditoría con `limit=25`: **13 a 16 ms** sin filtros y hasta 54 ms con tabla y usuario (tope 500 ms; los tiempos quedan por debajo de 60 ms).
- `recent`: unos **20 ms** (tope 50 ms).
- Tablero: unos **19 ms** (tope 300 ms).

### Validación V1 a V12

| Paso | Estado | Nota |
|---|---|---|
| V1 Fusión y documentos | hecha | Fusión de `feat/sprint-04a-front`; `BRECHAS.md` §11; `git worktree list` solo con el principal. |
| V2 Stack desde cero y ciclo | hecha | `apex-api:local` `329e3396b325`, `apex-web:local` `b8cd258b1cab`; 244 pruebas de migraciones; ciclo en `apex-db-1`. |
| V3 Datos reales | hecha con desviación | "Mensual" 120.000/30 no existe; se usó `Mensual mvjipju3`. La venta retroactiva nace `expired`, así que la base no tenía filas que corregir. |
| V4 E2E | hecha | `stack` 40/40 ×2; `preview` 161/161; topes de producción restaurados (429 a la cuarta verificación del minuto y `401 ×5, 429` en login). |
| V5 Rendimiento | hecha tras corrección | Falló por la pausa del GC (115 a 123 ms); corregido en S4A-D127 (17,9 a 23,2 ms). |
| V6 Smoke SQL | hecha | Triggers de `verifications` rechazan también con `session_replication_role = replica`; historial y tablero sin `@`, `apx1.` ni motivos; `verify_chain` por CLI (0) y API (200). |
| V7 Demo | hecha con desviaciones | V7.2 sin transiciones en `apex-db-1` (sí en `apex_sim`: +100); V7.6 "vender con el plan dado de baja" no concluyente antes de la limpieza P2-1. |
| V8 Repetición | hecha | `--run-once` ×2 con la misma fila; `verify-audit` ×2; `POST /audit/verify` ×4 (429 a la cuarta); `seed`, `init-keys` y `export-openapi` ×2 idénticos; smoke verde en 61 s. |
| V9 Gates completos | en verde en `89998b0`; falta repetir sobre la imagen final | `run-gates.sh`, `tests/architecture`, pre-commit, licencias, auditorías, gitleaks, `check-image-secrets` y `test_api_image` en verde con el código de V11. Queda reconstruir las imágenes con el HEAD final y repetir smoke y E2E (ver veredicto, aviso 2). |
| V10 Seguridad posterior | hecha | 0 CRITICAL, 0 HIGH, 0 MEDIUM, 4 LOW y 1 nota. L-1 a L-3 corregidos en `360d816`; L-4 (volcados) cerrado en V12. |
| V11 `verify-delivery` | hecha | Veredicto READY_WITH_WARNINGS; avisos 1, 5 y 6 tratados (ver veredicto). |
| V12 Cierre y paso humano | documentos y limpieza hechos | Limpieza P2-1 por API; borrado de los dos volcados y del admin desechable hechos por el agente de validación del stack, pendientes de verificación del orquestador antes del commit. Paso humano en "Pendiente humano". |

### Veredicto de V11 y matiz

El informe `docs/scratch/sprint-04a-verify-delivery.md` dio **READY_WITH_WARNINGS**, condicionado a que V9 quedara en verde. Con los avisos cerrados o con dueño, el veredicto pasa a **READY**, con este matiz:

1. **Aviso 1 (US-113 criterio 6, log del worker):** cerrado en código con prueba. `job finished` lleva `started_at`, `finished_at` y `duration_ms` (S4A-D128; `tests/worker/test_runner.py::test_el_log_job_finished_lleva_inicio_fin_y_duracion_de_la_fila`), en `89998b0`.
2. **Aviso 2 (P2-A, artefactos no vigentes con el HEAD):** condición pendiente. Las imágenes `apex-api:local` y `apex-web:local` deben reconstruirse con el HEAD final, recrear `api`, `worker` y `web`, y repetir el smoke y `e2e:stack`. El agente de validación del stack lo está ejecutando en paralelo. Si ese resultado no sale en verde, el veredicto vuelve a READY_WITH_WARNINGS.
3. **Aviso 3 (V9):** en verde en `89998b0`. Falta la repetición sobre la imagen final, incluida en el punto 2.
4. **Aviso 4 (V12):** la limpieza P2-1 está hecha. Los volcados y el admin desechable se marcan como hechos, pendientes de verificación del orquestador.
5. **Aviso 5 (R-3, pausa del GC en el api real):** no cerrado; tiene dueño en Sprint 4B. Impacto bajo: lectura de admin, 3 por minuto.
6. **Aviso 6 (cubetas en memoria, `sessionStorage`):** con dueño. Cubetas en v0.2; `sessionStorage` con regla de lint en 4B.
7. **Aviso 8 (MINOR):** `POST /plans/{id}/activate` no se ha llamado en vivo (P2-B), y la demo del job no hizo transiciones en la base viva (declarado en V3 y V7.2).

### Desviaciones declaradas

1. **`display_name` sin columna** (S4A-D19, D54, D108): el nombre visible es la parte local del correo; la columna llega en v0.2 (EP-04).
2. **`--date` solo con `--simulate`, `ENV=dev` y una base `*_sim` o `apex_test`**; nunca sobre `apex-db-1` (S4A-D48, D63, D75, E5).
3. **12 cubetas y 11 variables `USER_*`** frente a "`USER_LIMITS` no cambia" (contradicción 1; S4A-D26, D45, D47, D65).
4. **`VERIFY_BATCH_SIZE` = 500** (el contrato decía 5.000; B3 lo midió en 1.000) y **`SYNC_VERIFY_MAX_ROWS` = 100.000** (S4A-D91, D120).
5. **Marcador en lugar de blob** (S4A-D52, D105, D107).
6. **Worker sin volúmenes y endurecido**; `keys:ro` vuelve en el Sprint 5 (S4A-D49).
7. **429 en las cuatro lecturas** (`GET /audit`, `GET /audit/{seq}`, `GET /members/{id}/audit`, `GET /dashboard`) (S4A-D45, D27).
8. **`recent` por tabla** (S4A-D51, D115).
9. **`contact_for_notification(session, member_id, purpose)`** sin `fields` ni `by` (S4A-D21, D50).
10. **T8 de US-109 diferido a 4B** (con US-111; S4A-F3).
11. **Orden del front F1, F2, F4, F3** (S4A-D42, D62).
12. **Coach sin finanzas:** `income_month_cop` = `null` y frases sin monto (S4A-D118; ajusta S4A-D29).
13. **Enlace de ingresos en días civiles** (S4A-D121).
14. **Perf de la verificación con `gc.freeze()`** (S4A-D127; riesgo R-3 sin medir en el api real).
15. **US-113 criterio 6:** no se declaró en V11 como cumplido; se cumplió en S4A-D128 (aviso 1).
16. **Deuda a 4B** con índices, `0014_audit_log_triggers_always`, texto de `forbid_mutation()`, rol de base del worker (S4B-W0-2) y la pestaña Tabs a 1440 px.
17. **V3:** no existe el plan "Mensual" 120.000/30; se usó `Mensual mvjipju3`. La venta retroactiva nace `expired`.
18. **V7.2:** la base viva no tuvo transiciones del job; las transiciones se probaron en `apex_sim` (+100 `update` con `SYSTEM_USER_ID`) y en `tests/worker/test_expirations.py`.
19. **V7.6:** "vender con plan dado de baja" no concluyente antes de la limpieza P2-1 (100 de 178 planes). Tras la limpieza el total de activos cabe en una página.
20. **V4:** la captura de auditoría en preview cubre 390 y 1440 px (la spec fijada en F1), no 320, 768, 1024 y 1440; la de Inicio sí cubre los cuatro.
21. **`--status` desde la recuperación del arranque** no reejecuta un día cerrado (S4A-D79).
22. **Smoke de W0-1 y W0-2 sin reconstruir imágenes** (se usaron copias en el scratchpad); `chmod 600` sin efecto en NTFS.

### Deuda con dueño

| Ítem | Dueño | Destino | Referencia |
|---|---|---|---|
| `display_name` y parte local del correo como PII parcial | v0.2 (EP-04) | Columna de nombre visible; sustituye `user_names_for` y `user_refs_for` | S4A-D19, D54, D108 |
| Rol de base separado del worker, `.env` completo del worker y credencial compartida con el api | S4B-W0-2 | Mismo slice que el rol de base del api | S4A-D49, S4A-D85 (L-5) |
| `/health` con `worker.job_runs` | v0.2 | Hoy el aviso del worker es su latido | S4A-D8, S4A-D56 |
| `sign-audit` y firma externa del ancla `through_hash` | v0.3 | Residual: el ancla vive en la misma base | S4A-D43, S4A-D92 |
| `notifications.service` en `CONTACT_CALLERS` | Sprint 5 (EP-14) | Primer consumidor de `contact_for_notification` | S4A-D50 |
| T8 de US-109 (cuadre con datos de demostración) | Sprint 4B, con US-111 | Criterio diferido de S4A-F3 | `SPRINT-04A.md`, S4A-F3 |
| `0014_audit_log_triggers_always` (`ENABLE ALWAYS` de los dos triggers de `audit_log`) | Sprint 4B | Hoy `tgenabled = 'O'`; se confirmó en vivo en V10 | S4A-D98 |
| Texto de `audit.forbid_mutation()` que nombra `audit.audit_log` al rechazar `verifications` | Sprint 4B, con la fila anterior | La migración `0002` no se edita | V6, S4A-D98 |
| Índices `(record_id)`, `(action, seq DESC)` y `(table_name, action, seq DESC)` | Sprint 4B | Si el volumen lo exige | S4A-D106 c, S4A-D115, S4A-D119 b |
| R-3: pausa del GC de generación 2 en el api real durante la verificación síncrona | Sprint 4B | Medir con `gc.callbacks` bajo carga; `gc.freeze()` tras el arranque si hace falta | S4A-D127 |
| Cubetas por usuario en la memoria del único proceso (`audit-verify`, `audit-verify-hour`, `staff-read` y las anteriores) | v0.2 | Junto a OpenBao y el despliegue con varios procesos | S4A-D103 |
| `sessionStorage` en `web/src/pages/RouteError.tsx:41-43` | Front, Sprint 4B | Regla de lint con lista blanca de usos | V10 (nota), V11 aviso 6 |
| Barra `Tabs` de la ficha a 1440 px y contraste de "automático (aviso)" | Sprint 4B, pantalla de ficha | Desplazamiento de `Tabs` y contraste sin verificar en navegador | S4A-F2, `DECISIONES.md` "Deuda de front con dueño" |
| `payments.summary` sin caché | Aceptado | Constancia en `RUNBOOK.md` §11; se revisa si el volumen crece | S4A-D119 a |
| Revisión por diseño de `docs/BRECHAS.md` §11 | Backlog | `docs/design/` como fuente de verdad | V1, S4A-D36 |
| Precio vigente al vender (sin `expected_price_cop`) | Sprint 4B (S4B-W0, revisión de riesgos aceptados) | Riesgo aceptado con dueño | S4A-D60 |
| La lectura de la auditoría no se audita (el log de acceso es el único rastro) | Sprint 4B (S4B-W0, revisión de riesgos aceptados) | Riesgo aceptado con dueño | S4A-D61 |
| Pendientes de Sprint 3 que siguen: W0-2 MEDIUM-1 y -2, N-6 y N-7 | S4B-W0-2 | Mismo slice de endurecimiento de la base | `DECISIONES.md`, "Estado de los dueños del Sprint 3" |

### Datos de prueba que quedan en `apex-db-1`

- Socios de la demo `demo-s4a-expira` (`fc699bcd-e312-4c0f-bf72-f4bf4c091c1e`), `demo-s4a-historial` (`ffc1fee0-0247-4a36-aa3d-78e90efecc62`) y `demo-s4a-plan` (`fc91aba1-c237-4579-a7dd-b247cfd06b6c`), con sus membresías y pagos. Los pagos son inmutables y no se borran.
- Socio "Sofía DemoF4" de la demo de F4.
- Planes de demo dados de baja: `S4A-V3-corto-mvtcfyaf`, `S4A-V7-plan-mvtcfyaf` y `S4A-V8-plan-mvtcfyaf`.
- Coaches desechables dados de baja, incluido `coach-v6-mvtcfyaf@apex.test`.
- Tres coaches `@test.apex` del Sprint 3 (no se tocaron en V12).
- Planes vivos que no se tocaron: `mensual`, `Mensual V50137` y `Tiquetera 12`.
- Las 72 membresías activas de los planes desactivados en la limpieza P2-1 siguen activas, porque el procedimiento solo anula `pending_payment`.
- Admin desechable `admin-e2e-*@apex.test`: dado de baja (pendiente de verificación del orquestador).
- Filas de `audit.audit_log` de todo lo anterior: inmutables, con la cadena íntegra (`verify-audit` da 0).

### Pendiente humano

1. **Verificar antes del commit** el borrado de `docs/scratch/sprint-04a-antes-0012.dump` y `-0013.dump`, y la baja del admin desechable (ejecutados por el agente de validación del stack).
2. **Confirmar la reconstrucción de imágenes** con el HEAD final (P2-A): `apex-api:local` y `apex-web:local` con buildx, `up -d --no-build` (recrea api, worker y web), smoke y `e2e:stack`.
3. **Push** de `feat/sprint-04a-worker-auditoria-tablero`. Tras el merge por avance rápido (`git checkout main && git merge --ff-only feat/sprint-04a-worker-auditoria-tablero`), push de `main`. Ningún script hace push. Si el clasificador bloquea el push, reintentar en la siguiente sesión, como en los Sprints 2 y 3.
4. **CI en GitHub Actions**, con seis jobs: `api`, `web`, `images` (con el smoke del worker), `scripts`, `secrets-scan` y `e2e-stack` (con las 11 `USER_*` ×100 y el worker activo). Nada de este sprint ha corrido todavía en CI.
5. **PR:** `gh` no está instalado en este equipo; abrirlo a mano o instalar `gh`.
6. **Revisión por diseño de `docs/BRECHAS.md` §11** (Auditoría, Inicio, Planes y Rutas), con `docs/design/` como fuente de verdad.
7. **Verificar en vivo `POST /plans/{id}/activate`** (P2-B, MINOR) si la validación del stack no lo cubre.
