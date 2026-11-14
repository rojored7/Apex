# Sprint 7 (v0.4) · Análisis de impacto previo (Fase 0)

Anclado a HEAD `a2f38ad` (= main, árbol limpio, rama `feat/sprint-07-clases-horario-checkin`). Solo lectura.

Veredicto: AMARILLO

## 1. Blast radius (archivos de `api/src` + `api/tests` que importan `app.modules.X`)

- settings: 104 (secciones `hours` y `classes`; N-17, N-18 ya existen desde S2, US-154 cambia rangos y quita `allow_over_capacity`).
- members: 305 (filtro de última asistencia, `GET /members/{id}/attendance`, par members↔classes, pestaña Asistencia).
- memberships: 171 (US-160: `classes_remaining`, recorte de `end_date`, `original_end_date`; `rules.find_overlap`, `sell`, `expirations`).
- plans: 78 (solo lectura de `plans.service.get`; sin cambio previsto).
- auth: 167 (solo `names_for` e `is_active_staff`; sin cambio).
- dashboard: 18 (`schemas.py`: `attendance_week` y `sessions_today` hoy `null`; en el front `features/dashboard/{schemas,FutureKpis}` y `web/src/test/dashboard.tsx`).
- core/events: 42 (eventos nuevos de sesión cancelada y asistencia registrada/borrada; el tipo se define en `classes`, regla 3).
- core/locks: 27 (orden de candados: `lock_member` primero, luego sesión; el `FOR UPDATE` del cupo pasa por `core/locks.py`).
- core/ratelimit: 37 (cubetas nuevas de check-in, borrado y reportes; sube el conteo de 23 y su prueba).
- worker.registry: 26 (job nuevo de generación de sesiones; `registry`, `schedule`, pruebas de wave 0).
- El módulo `classes` NO existe: es código nuevo; `main.MODULES`, `test_service_import_graph.py` y `test_no_cross_*` lo recogen.
- Contrato: `docs/openapi.json` (16 411 líneas) y `web/src/core/api/types.ts` (11 005) se regeneran; el release sube la versión a `0.4.0` en 5 archivos (`check-release-version.sh`).
- Front: rutas y menú nuevos (Horario, Sesiones, CheckIn en `GymLayout`, que ya existe; "Hoy" = 3 enlaces existentes, Q25); fuente: `docs/design/ROUTES.md` y `screens/`.

## 2. Capa de datos

- Cadena actual lineal `0020 → 0024` (head `0024_crypto_rotation_from_api`). El plan nombra `0060-0064`: no hay `0025`-`0059`. Propuesta (registrar en DECISIONES): `0025` endurecimiento heredado, `0026_classes_slots`, `0027_class_sessions`, `0028_attendance`, `0029_memberships_classes_remaining_check`, `0030_memberships_exhausted_end_date`. Renumerar SPRINT-07.md y guías en el mismo cambio.
- `0025` (deuda S6-D130/D133, dueño Sprint 7): FK `fk_attachments_key_id` (`ON DELETE RESTRICT`, `NOT VALID` + `VALIDATE`); `guard_jobs_update` con `OLD.kind = 'rotate'` para `apex_api`; `CHECK ((purpose='sign') = (public_key IS NOT NULL))`; `CHECK (kind <> 'photo' OR NOT sensitive)`; `public_key` inmutable también para el propietario. Tablas con datos en desarrollo y ensayo: consultar antes las filas que violarían los CHECK.
- HALLAZGO en `memberships`: `classes_remaining >= 0`, `classes_pair` y `classes_remaining_le_total` YA existen desde `0008` (líneas 165-169). La migración de CHECK (`0063` en el plan) queda redundante: eliminarla o reducirla a prueba. Confirmar con US-160.
- `original_end_date`: columna nula nueva en tabla con datos; cumple los tres pasos sin backfill (NULL = no recortada) y sin NOT NULL. Requiere `GRANT UPDATE (original_end_date)` a `apex_api`: el grant por columna de `grants.sql:133` no la incluye. El trigger `memberships_identity` (`0008`) solo congela membresías anuladas.
- `EXCLUDE ex_memberships_member_dates` (gist, `0008`): no se edita. El recorte de `end_date` al agotar evita el choque; al devolver una clase, restaurar el fin original solo si no solapa, dentro de la transacción y bajo `lock_member`.
- Grants: 3 tablas nuevas (franjas, sesiones, asistencia) se clasifican en `infra/db/grants.sql` y `tests/migrations/test_db_grants.py` (`dbsetup` falla cerrado; hoy 22 tablas) más `GRANT USAGE ON SCHEMA classes`; `apex_worker` con SELECT/INSERT en sesiones y SELECT en franjas; asistencia sin DELETE para ningún rol y UPDATE por columna (`removed_*`, `flags`); trigger de auditoría `ALWAYS` y su entrada en `tests/migrations/test_0014*`.
- Índice único parcial (`session_id`, `member_id`) `WHERE removed_at IS NULL`; índice de última asistencia por socio (G-10, <500 ms con 1.000 socios).

## 3. Servicios Docker

- api: `COPY src`, `alembic.ini` y `migrations` en la imagen (Dockerfile 16-22): reconstruir. Hoy monta el volumen `keys:/run/apex/keys:ro` completo (compose.yml:139); la deuda heredada pide montar solo `custody/kek.bin` y `jwt/` (toca compose.yml, compose.openbao.yml, `deploy.sh`, `prod-smoke.sh`; se prueba en Linux).
- worker: misma imagen del api: reconstruir; la subruta `custody` ya está montada; sin volumen nuevo.
- web: build estático de Vite (`web/Dockerfile`): reconstruir tras rutas, tipos y pantallas.
- `migrate` corre `0025-0030`; `dbsetup` reaplica `grants.sql` en cada arranque.
- Sin infraestructura nueva (Wave 0 del plan).

## 4. Contratos API

- Nuevos: 18 rutas (settings hours y classes 4; class-slots 5 con cancel-future-sessions; class-sessions 4; attendance 4; `members/{id}/attendance` 1). Rol admin/coach en todas (`test_every_route_has_role`); `/attendance/summary` antes de `/{id}`; `DELETE` con motivo (verificar que cliente y proxy admitan cuerpo).
- Cambian: `GET /members` (filtro opcional y aditivo, sin ruptura) y `GET /dashboard` (`attendance_week` y `sessions_today` pasan de `null` a valor: cambia `types.ts`; `FutureKpis.tsx`, `schemas.ts` del dashboard y sus pruebas se actualizan en el mismo cambio).
- `settings/classes` pierde `allow_over_capacity` (N-38): revisar seed, `GET/PATCH` y el front.

## 5. Línea base de pruebas

- Cierre del Sprint 6 (S6-D141, sobre `af23e51`): api 9544 pasan y 100 saltadas; web 3930 de 3930 (2 hilos, 98,37 % de líneas).
- Hoy, `tests/architecture` en `a2f38ad`: 806 passed en 93,8 s (`db_test` respondió en 5443). Suite completa no corrida (poca memoria); mypy y web se toman del cierre de S6.

## 6. Riesgos por severidad

1. [ALTA] Numeración `0060-0064` frente a la cadena en `0024`: sin decisión se rompen `alembic heads` y `migrations_status`.
2. [ALTA] La deuda de S6 (`0025` y montaje mínimo de `keys`) tiene dueño este sprint y toca datos y seguridad; omitirla deja M1 abierto.
3. [MEDIA] Migración de CHECK duplicada con `0008` (nombres repetidos).
4. [MEDIA] `original_end_date` sin `GRANT UPDATE` falla solo en runtime con `apex_api`: exigir prueba de grants y E2E con rol real.
5. [MEDIA] Ciclo de imports members↔classes: ampliar la lista blanca G-03 antes de US-163.
6. [MEDIA] Cambio de `GET /dashboard` rompe `FutureKpis` y sus pruebas si no va junto.
7. [MEDIA] Carrera de cupo (aceptada) y rendimiento (<2 s check-in, <500 ms filtro): prueba `perf`.
8. [BAJA] Conversión local↔UTC, conteo de cubetas de rate limit y memoria en vitest (usar 2 hilos).

## Condiciones para VERDE

- C1: decidir y registrar la numeración (`0025`-`0030` propuesta) y actualizar SPRINT-07.md antes de crear migraciones.
- C2: `0025` de endurecimiento primero, con consulta previa de filas violantes y `downgrade` probado.
- C3: confirmar con US-160 que la migración de CHECK se elimina (ya están en `0008`).
- C4: `grants.sql`, `test_db_grants.py` y triggers de auditoría de las 3 tablas en el mismo slice que cada migración.
- C5: lista blanca G-03 members↔classes y su prueba antes de US-163; dashboard (api y web) en un solo cambio.
- C6: reconstruir api, worker y web tras cada wave con migraciones o contrato; regenerar `openapi.json` y `types.ts`.
