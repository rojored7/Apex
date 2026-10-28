# Sprint 4A · Worker, auditoría verificable, tablero y planes restantes

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

1. `docker compose up -d --build` levanta también el servicio `worker` (ya sin `profiles`).
   - `docker compose exec api alembic current` muestra `0013_audit_verifications`.
2. Con los socios y las membresías de la demo del Sprint 3:
   - `docker compose run --rm worker python -m app.worker.main --run-once expirations`, con `FrozenClock` adelantado, pasa membresías a `expiring` y a `expired`;
   - `worker.job_runs` registra la corrida;
   - una segunda corrida el mismo día no duplica nada.
3. Auditoría:
   - la pantalla filtra por tabla, usuario y fecha;
   - el detalle muestra antes y después, con "valor cifrado modificado";
   - "Verificar cadena" responde OK y queda en `audit.verifications`;
   - `docker compose run --rm tools verify-audit --as admin@...` da el mismo resultado.
4. La pestaña Historial de la ficha muestra los cambios del socio, de sus membresías y de sus pagos (N-31).
5. Inicio muestra:
   - los KPI de membresías e ingresos del mes;
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
  - US-041 (`display_name`);
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

Desde este sprint, `src/app/cli.py` y `src/app/worker/` entran en la cobertura: se quita el `--cov-omit` (M-6).

### Wave 0 · Infraestructura (`devops-wsl2-docker`)

- **Slice S4A-W0-1 · Worker en Compose (solo preparación).** Son las tareas DevOps de US-113 que no necesitan código del worker.
  - Se define el servicio `worker` con la misma imagen y el comando `python -m app.worker.main`, reintento de conexión a la base y healthcheck por `job_runs`, **pero se conserva `profiles: ["worker"]`**: todavía no existe `app/worker/main.py` y el contenedor entraría en bucle de reinicios (CRITICA-2 N-3).
  - Gate: `docker compose config` valida el archivo; smoke de Compose **sin** el perfil `worker`.
- **Slice S4A-W0-2 · Activar el worker.** Se ejecuta **después de cerrar S4A-B1**.
  - Se quita `profiles: ["worker"]`.
  - Cierra el criterio diferido de US-005.
  - Gate: smoke de Compose con `worker` en marcha y `healthy`, y `docker compose run --rm worker python -m app.worker.main --run-once expirations` con código 0.

### Waves 3a/3b · Backend, alternadas por slice

- **Slice S4A-B1 · Proceso worker programado.** Historia: US-113.
  - **Rojo:** `tests/worker` (registro de jobs, `claim_run`, `finish_run`, `--run-once`, `FrozenClock`), con stubs de `core/jobs.py` y `worker/main.py`.
  - **Verde:**
    - `core/jobs.py` (G-06);
    - migración `0012_worker_job_runs`;
    - APScheduler a las 07:00 `America/Bogota`;
    - una transacción por lote;
    - actor `SYSTEM_USER_ID`.
  - **Gate:** `slice-gate.sh worker` y `slice-gate.sh core/jobs`, cada uno con sus archivos, más el ciclo de Alembic.
- **Slice S4A-B2 · Job diario de vencimientos.** Historia: US-094.
  - **Rojo:**
    - `tests/worker/test_expirations.py`, también con `-m perf`;
    - `tests/cli/test_recompute_memberships.py`.
  - **Verde:**
    - `recompute_statuses(today)` por lotes, con `today_bogota()`;
    - idempotente: una sola corrida por día.
  - **Gate:** `slice-gate.sh memberships`, `slice-gate.sh worker` y `slice-gate.sh cli`, con los archivos de cada uno.
- **Slice S4A-B3 · Verificar la cadena desde la API y desde la CLI.** Historias: US-104 y US-105.
  - **Rojo:**
    - `tests/core/test_verify_chain.py`;
    - `tests/audit/test_verify.py`, `test_verify_concurrency.py`, `test_verify_performance.py` y `test_router_verify.py`;
    - `tests/cli/test_verify_audit.py`;
    - `tests/core/test_format_verify_message.py`.
  - **Verde:**
    - migración `0013_audit_verifications`;
    - `run_verification` con lock asesor; un salto en `seq` cuenta como ruptura;
    - `POST /audit/verify` y `GET /audit/verify/last`;
    - `cli verify-audit --as`.
  - **Gate:** `slice-gate.sh audit`, `slice-gate.sh core/audit` y `slice-gate.sh cli`, con los archivos de cada uno, más el ciclo de Alembic.
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
    - `list_for_subject(member_id)` sobre `subject_member_id` (G-05);
    - `GET /members/{id}/audit`.
  - **Gate:** `slice-gate.sh audit` y `slice-gate.sh members`, con los archivos de cada uno.
- **Slice S4A-B6 · Contacto para avisos auditado.** Historia: US-077.
  - **Rojo:**
    - `tests/members/test_service_contact.py` y `test_validate_purpose.py`;
    - `tests/architecture/test_crypto_bus_importers.py`.
  - **Verde:**
    - `contact_for_notification(member_id, fields, purpose)`, con propósitos `notify` y `auth_link`;
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
    - `DELETE` lógico, con 409 si hay membresías activas; usa `count_active_by_plan` mediante un import perezoso de la lista blanca.
  - **Gate:** `slice-gate.sh plans` con sus archivos, más los dos archivos de `tests/integration`.
- **Slice S4A-B8 · Tablero.** Historias: US-108 y US-110 (backend).
  - **Rojo:**
    - `tests/dashboard`;
    - `tests/audit/test_recent.py`;
    - `tests/architecture/test_read_modules.py`.
  - **Verde:**
    - contrato de `GET /dashboard` con los campos futuros en `null`;
    - KPI;
    - "Últimos movimientos" (Q10), sin `SYSTEM_USER_ID` y con `display_name`.
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

- E2E de `home.spec.ts` y de todos los specs anteriores.
- `--run-once expirations` dos veces el mismo día.
- Prueba de rendimiento de la verificación de la cadena (`-m perf`).
- Paso humano: push y PR.

## Migraciones que aplica

- `0012_worker_job_runs` (US-113).
- `0013_audit_verifications` (US-104 y US-105).

Ya no hacen falta `0014_audit_subject_member`, `0014_crypto_ops_purpose` ni `0014_crypto_ops_export_verb`. Queda como condicional `0014_payments_registered_by_idx`.

## Endpoints que expone

10 endpoints:
- `GET /api/v1/audit` (admin).
- `GET /api/v1/audit/verify/last` (admin), registrado antes de `/audit/{seq}`.
- `GET /api/v1/audit/{seq}` (admin).
- `POST /api/v1/audit/verify` (admin).
- `GET /api/v1/members/{id}/audit` (admin y coach).
- `GET /api/v1/dashboard` (admin y coach).
- `PATCH /api/v1/plans/{id}` (admin).
- `POST /api/v1/plans/{id}/activate` (admin).
- `POST /api/v1/plans/{id}/deactivate` (admin).
- `DELETE /api/v1/plans/{id}` (admin).

## Tests de arquitectura que deben pasar

Corren en cada gate de slice (A-5).
- Todos los de los Sprints 0 a 3.
- `test_core_import_direction.py`, ampliada para `core/jobs.py` (absorbe `test_core_jobs_imports.py`).
- `test_service_import_graph.py`, ampliada con el par plans↔memberships (US-082).
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
4. **[MEDIUM]** Al quitar el `--cov-omit` puede bajar la cobertura global.
   - Mitigación: las pruebas de `tests/worker` y `tests/cli` entran en este mismo sprint, y `run-gates.sh` se corre después de B2.
5. **[LOW]** Sin datos de demostración, el tablero se prueba con factories.
   - Mitigación: el criterio diferido de US-109 queda declarado y se cierra en 4B.

## Definición de hecho del sprint

- El slice de Wave 0, los 8 de backend y los 4 de front, confirmados con `checkpoint-commit.sh`.
- `run-gates.sh` en verde, con cobertura global de `app` de al menos 80 %, ya sin `--cov-omit`.
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
