# EP-21 · Clases, horario y check-in — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-21-clases-y-check-in.md`
- **Versión:** v0.4
- **Historias:** US-154 a US-164 (11 historias, 39 puntos)

## Resumen

La épica crea el módulo `classes` (esquema `classes`) con tres tablas: `class_slots` (plantilla semanal), `class_sessions` (instancias generadas o extra) y `attendance` (check-in). El trabajo va en este orden:

- Configurar las secciones `hours` y `classes` de Settings (US-154).
- Definir el horario (US-155).
- Generar las sesiones a 14 días con un job diario (US-156).
- Gestionar la semana: sesión extra, cancelar (US-157) y cancelar las futuras de una franja (US-158).
- Check-in en la tablet que nunca bloquea (US-159) y su borrado lógico (US-161).
- Descontar y devolver clases en Memberships por eventos (US-160).
- Reportes de asistencia (US-162), filtro de última asistencia en la lista de socios (US-163) y KPIs del tablero (US-164).

Classes lee el estado de membresía con `memberships.service.status_for(member_ids)`, los nombres de socios con `members.service.names_for(member_ids)` y los nombres y roles de coaches con `auth.service`. Nunca lee campos cifrados. Memberships descuenta y devuelve clases solo por los eventos `MemberCheckedIn` y `AttendanceRemoved`, declarados en `core/events.py`.

El check-in solo responde error por dos cosas: asistencia duplicada (RN-10) y sesión cancelada. Nunca falla por cupo, hora ni membresía: siempre registra y devuelve `flags`.

## Correcciones aplicadas por DECISIONES.md

- US-154 y US-159 usan `allow_over_capacity` (409 `session_full` con `override_capacity` para forzar) → `allow_over_capacity` se elimina de `settings.classes` y `override_capacity` se elimina del contrato de `POST /attendance`. Superar el cupo registra siempre con 201 y agrega `over_capacity` a `flags`: corregido por DECISIONES N-38.
- US-159 responde 422 `outside_checkin_window` fuera de la ventana → registra con 201 y agrega `out_of_window` a `flags`; `checkin_window_min` es solo umbral de advertencia: corregido por DECISIONES N-39.
- US-159 devuelve `flagged` y `over_capacity` sueltos → la respuesta lleva `flags: ["expired" | "no_membership" | "frozen" | "over_capacity" | "out_of_window"]` y `flagged = len(flags) > 0`; `attendance.flags` se persiste. El estado `pending_payment` produce `no_membership`, porque según el lenguaje ubicuo "sin plan" es no tener membresía vigente y `pending_payment` no es vigente (Q1). `expiring` y `active` no marcan: corregido por DECISIONES N-38 y N-39 (la correspondencia de `pending_payment` es una precisión y se anota como riesgo).
- US-154 fija `default_capacity` de 1 a 200 y `hours` como `{ closed, opens_at, closes_at }` por día → `default_capacity` de 1 a 100, `checkin_window_min` de 0 a 240, y `hours` por día de la semana como lista de rangos `{ open, close }` en hora local (lista vacía = cerrado): corregido por DECISIONES N-18. El 422 de un rango incoherente lleva `field` del tipo `hours.monday[0]`.
- US-161 hace borrado físico con `before` en la auditoría → borrado lógico con `removed_at`, `removed_by` y `removed_reason`; la unicidad es un índice parcial `(session_id, member_id) WHERE removed_at IS NULL`. La auditoría registra `update` con antes y después, no `delete`: corregido por DECISIONES N-40.
- US-155 guarda `start_time` como hora local (`TIME` sin zona) → aceptado; la conversión a `starts_at` UTC ocurre al generar: aceptado por DECISIONES N-40.
- US-160 reactiva una tiquetera `expired` al devolver una clase si su fecha no pasó → aceptado: aceptado por DECISIONES N-40 (ver la pregunta abierta de US-160 sobre el choque con la renovación).
- US-161 deja abierto quién borra → admin y coach, auditado, emite `AttendanceRemoved` que devuelve la clase si el plan es por clases: corregido por DECISIONES Q8.
- US-155 y US-156: editar o desactivar una franja afecta solo a las sesiones no generadas. La generación es a 14 días por el job diario y la cancelación masiva es la acción "cancelar sesiones futuras de esta franja" (US-158): corregido por DECISIONES Q23.
- US-160: hasta v0.4 un plan por clases solo vencía por fecha; desde aquí lo descuenta `MemberCheckedIn`: aplicado por DECISIONES Q4.
- US-154 y US-159: los valores de `classes` vienen de Settings (`default_capacity`, `checkin_window_min`), sin `allow_over_capacity`: aplicado por DECISIONES Q11 con la corrección de N-38.
- US-156 supone un "usuario técnico de sistema" sin definir → `created_by = SYSTEM_USER_ID`; `cli generate-sessions` acepta `--as <email>`: corregido por DECISIONES N-15.
- US-157 y US-164: el grupo "Hoy" del menú es un enlace a `Sesiones` filtrada a hoy (`/clases?dia=hoy`), no una ruta nueva: aplicado por DECISIONES Q25.
- "Hoy", la semana ISO y los cortes de "hace N días" se calculan con `today_bogota()`; el API devuelve UTC: aplicado por DECISIONES Q28.
- `PATCH /class-sessions/{id}` entra al contrato, pero su historia es US-168 (EP-22, asignar WOD). Esta épica deja `class_sessions.wod_id` nulo y sin FK entre esquemas, listo para esa ruta, y no la implementa: anotado por DECISIONES N-41.

## Validación contra el dominio y la arquitectura

- **Dominio:**
  - `ClassSlot` y `ClassSession` son raíces y `Attendance` es entidad interna de `ClassSession` (`02_domain_model.md` 2.5).
  - Invariantes:
    - RN-10, una asistencia vigente por sesión y socio (índice parcial);
    - RN-09, el check-in nunca bloquea por membresía (N-38 y N-39 lo extienden a cupo y hora);
    - no hay check-in en una sesión `cancelled` (409 `session_cancelled`);
    - el cupo es advertencia.
  - `membership_status_at_checkin` admite `active`, `expiring`, `expired`, `frozen`, `pending_payment` y `none` (el dominio no lista `pending_payment`; se agrega porque `status_for` lo devuelve, Q3).
  - Eventos: `SessionGenerated`, `SessionCancelled`, `MemberCheckedIn` y `AttendanceRemoved`. Los dos últimos se amplían con `attendance_id`, `checked_in_at` y `membership_status_at_checkin`, para que Memberships ubique la membresía que descontó sin leer tablas de Classes.
  - RN-05 y RN-06 (descuento y `expired` con 0 clases) viven en `memberships`.
- **Funciones puras (classes):**
  - `checkin_flags(membership_status, attendance_count, capacity, starts_at, now, window_min) -> list[str]`, que compone las otras tres;
  - `checkin_outcome(membership_status) -> (allowed=True, flags_membresia)`;
  - `within_checkin_window(starts_at, now, window_min) -> bool`;
  - `capacity_outcome(count, capacity) -> bool`, sin el parámetro `allow_over_capacity`, eliminado por N-38;
  - `validate_slot(weekday, start_time, duration_min, capacity)`;
  - `planned_sessions(slots, from_date, to_date, tz) -> list[PlannedSession]`;
  - `week_range(week, tz) -> (from_utc, to_utc)`;
  - `session_display_status(status, starts_at, duration_min, now)` (`done` calculado al leer, supuesto de US-157);
  - `weekly_summary(rows) -> list[WeekBucket]`;
  - `absence_cutoff(code, today) -> date | None` (`7d`, `14d`, `30d`, `60d`, `never`).
- **Funciones puras (memberships):** `consume_class(membership) -> Membership` (nunca negativo), `return_class(membership) -> Membership` (tope `classes_total`), y `compute_status(membership, today, expiring_days, freezes)` reutilizada (Q11, N-25).
- **Arquitectura:**
  - Classes → `memberships.service.status_for` (lectura), → `members.service.names_for` y `members.service.exists_active` (lectura), → `auth.service.names_for` y `auth.service.is_active_staff` (validar coach), → `settings.service.classes()` y `settings.service.get_section("hours")`.
  - Memberships ← Classes solo por eventos.
  - Dashboard → `classes.service.today` y `week_attendance` (lectura compuesta permitida).
  - Members → `classes.service.member_ids_with_attendance_since` y `last_attendance_for` (US-163): esa última dirección forma un ciclo `members.service` ↔ `classes.service` (ver la brecha de US-163).
  - Ningún import de `models` ajenos; `attendance.member_id` y `class_sessions.coach_id` son UUID sin FK entre esquemas.
- **Eventos en `core/events.py`:** las dataclasses congeladas de los cuatro eventos se declaran ahí (patrón de `CLAUDE.md`, regla de módulos 3), así Memberships no importa nada de `modules.classes`.
- **Rol:** `/class-slots*` solo admin; `/class-sessions*`, `/attendance*`, `GET /members/{id}/attendance`, `GET /members` y `GET /dashboard` admin y coach; `/settings/{hours,classes}` solo admin; socio 403.
- **Paginación:** todas las listas con `limit` 1 a 200 y `{items, total, limit, offset}`; el resumen semanal limita el rango a 26 semanas.
- **Auditoría:** `class_slots`, `class_sessions` y `attendance` con `__audited__ = True`; los cambios de `classes_remaining` quedan en la auditoría de `memberships`.
- **Bus y lint:** ninguna tarea usa primitivas ni campos cifrados.

## Tablas y migraciones

- `0060_classes_slots` (US-155): `CREATE SCHEMA classes`; tabla `classes.class_slots`:
  - `id` UUID;
  - `weekday` smallint con CHECK 0 a 6;
  - `start_time` TIME (hora local de Bogotá, N-40);
  - `duration_min` smallint con CHECK 15 a 240;
  - `capacity` smallint con CHECK `>= 1`;
  - `default_coach_id` UUID NOT NULL;
  - `is_active` bool NOT NULL default true;
  - columnas comunes.
  
  Índice único parcial `(weekday, start_time) WHERE is_active`. Downgrade: borra tabla y esquema.
- `0061_class_sessions` (US-156): tabla `classes.class_sessions`:
  - `id` UUID;
  - `slot_id` UUID nulo con FK a `class_slots` (mismo esquema);
  - `starts_at` TIMESTAMPTZ NOT NULL;
  - `duration_min` y `capacity` con los mismos CHECK;
  - `coach_id` UUID NOT NULL;
  - `wod_id` UUID nulo, sin FK (lo usa EP-22);
  - `status` text con CHECK (`scheduled`, `cancelled`, `done`), default `scheduled`;
  - `cancel_reason` text nulo, con CHECK `status <> 'cancelled' OR length(trim(cancel_reason)) > 0`;
  - columnas comunes.
  
  Índice único parcial `(slot_id, starts_at) WHERE slot_id IS NOT NULL` e índice `starts_at`. Downgrade: borra la tabla.
- `0062_attendance` (US-159, con las columnas de N-40 desde el inicio para no migrar con datos): tabla `classes.attendance`:
  - `id` UUID;
  - `session_id` UUID NOT NULL con FK a `class_sessions`;
  - `member_id` UUID NOT NULL;
  - `checked_in_at` TIMESTAMPTZ NOT NULL;
  - `checked_in_by` UUID NOT NULL;
  - `membership_status_at_checkin` text con CHECK (`active`, `expiring`, `expired`, `frozen`, `pending_payment`, `none`);
  - `flags` text[] NOT NULL default `{}`, con CHECK `flags <@ ARRAY['expired','no_membership','frozen','over_capacity','out_of_window']`;
  - `flagged` bool NOT NULL, con CHECK `flagged = (cardinality(flags) > 0)`;
  - `removed_at` TIMESTAMPTZ nulo, `removed_by` UUID nulo y `removed_reason` text nulo, con CHECK `(removed_at IS NULL) = (removed_by IS NULL)`;
  - columnas comunes.
  
  Índice único parcial `(session_id, member_id) WHERE removed_at IS NULL` (RN-10) e índices `(member_id, checked_in_at DESC)` y `(checked_in_at)`. Downgrade: borra la tabla.
- `0063_memberships_classes_remaining_check` (US-160): `ALTER TABLE memberships.memberships ADD CONSTRAINT ... CHECK (classes_remaining IS NULL OR (classes_remaining >= 0 AND classes_remaining <= classes_total))`, solo si `0008_memberships` no lo creó (verificar). Si hay filas que lo violen, la migración falla con un mensaje claro y no corrige datos (eso sería un comando de `cli.py`).
- Condicionada a la respuesta de US-160: `0064_memberships_exhausted_end_date` (columna nula `original_end_date` date en `memberships.memberships`) si se aprueba la propuesta por defecto.
- Sin migración para `settings`: `hours` y `classes` viven en `settings.settings_sections` y sus valores por defecto están en el esquema Pydantic (US-154).

## Services y eventos

- `modules/settings/schemas.py` y `service.py`: `HoursSection` (lunes a domingo, lista de `{open, close}` HH:MM local, `open < close`, sin rangos solapados) y `ClassesSection` (`default_capacity` 1 a 100, por defecto 15; `checkin_window_min` 0 a 240, por defecto 30). `settings.service.classes() -> ClassesSection` devuelve el valor por defecto si no hay fila. `validate_section` pura por sección.
- `modules/classes/service.py`, casos de uso:
  - `list_slots`, `create_slot(data, by)` (capacidad por defecto de Settings; coach validado con `auth.service.is_active_staff`; 409 `slot_duplicated`), `update_slot(id, data, by)` (sin tocar sesiones generadas, Q23);
  - `cancel_future_sessions(slot_id, reason, by) -> int`: una transacción, solo `scheduled` con `starts_at > now`; emite `SessionCancelled` por sesión;
  - `generate_sessions(today, days=14, by=SYSTEM_USER_ID) -> int`: `INSERT ... ON CONFLICT DO NOTHING` sobre el índice parcial; no regenera `cancelled`; emite `SessionGenerated` solo por las creadas;
  - `list_sessions(week | from/to, status, limit, offset)`, con `attendance_count` en una consulta agrupada, nombres de coach en lote y `done` calculado;
  - `create_extra_session(data, by)`, `cancel_session(id, reason, by)` (409 `session_already_cancelled`), `get_session(id)` (asistentes no removidos con nombre, apellido, `flags` y `flagged`, sin campos cifrados);
  - `check_in(session_id, member_id, by) -> CheckInOut`:
    - 404 si la sesión no existe, o si el socio no existe o está dado de baja (`members.service.exists_active`);
    - 409 `session_cancelled`;
    - lee `status_for([member_id])`, cuenta los asistentes vigentes y calcula `checkin_flags`;
    - inserta y responde 409 `already_checked_in` si el índice parcial salta;
    - emite `MemberCheckedIn` en la misma transacción.
  - `remove_attendance(id, reason, by)`: 404 si no existe o ya fue removida; borrado lógico; emite `AttendanceRemoved`; se permite en sesiones `cancelled`.
  - `list_attendance(member_id, session_id, flagged, from_, to, limit, offset)`, `attendance_summary(from_, to)` (máximo 26 semanas, por franja; las sesiones extra van al grupo `extra`), `member_attendance(member_id, limit, offset)` (con `last_attendance_at` y `count_30d`).
  - `last_attendance_for(member_ids) -> dict[UUID, datetime | None]` y `member_ids_with_attendance_since(cutoff_utc) -> set[UUID]` (US-163).
  - `today(today) -> list[SessionToday]` y `week_attendance(today) -> {count, flagged_count}` (US-164).
  - Todas las consultas de asistencia excluyen `removed_at IS NOT NULL`.
- `modules/memberships/service.py`, handlers suscritos con `core.events.subscribe`:
  - `on_member_checked_in(event)`: si `membership_status_at_checkin` es `active` o `expiring`, busca la membresía no cancelada del socio cuyo rango contiene la fecha de Bogotá de `checked_in_at` y cuyo plan es por clases (`plans.service.get`), aplica `consume_class` y recalcula `compute_status`. Emite `ClassConsumed(membership_id, classes_remaining)` y, si llega a 0, `MembershipExpired`. En cualquier otro caso no cambia nada.
  - `on_attendance_removed(event)`: misma ubicación por fecha y misma condición sobre `membership_status_at_checkin`; aplica `return_class` con tope `classes_total` y recalcula el estado (reactiva una `expired` si su fecha no pasó, N-40).
  - Si un handler falla, la transacción del check-in o del borrado se revierte completa.
- Eventos emitidos: `SessionGenerated(session_id, slot_id, starts_at)`, `SessionCancelled(session_id, reason)`, `MemberCheckedIn(attendance_id, member_id, session_id, checked_in_at, membership_status_at_checkin, flagged)`, `AttendanceRemoved(attendance_id, member_id, session_id, checked_in_at, membership_status_at_checkin)`, `ClassConsumed` y `MembershipExpired` (desde memberships). Consumidos: `MemberCheckedIn` y `AttendanceRemoved` (memberships).
- `modules/members/service.py`: parámetro `last_attendance` en `list` (`member_ids_with_attendance_since` y exclusión con `id NOT IN`, sin JOIN; `never` usa todos los ids con asistencia) y `last_attendance_at` por fila con `last_attendance_for` (US-163).
- `modules/dashboard/service.py`: llena `attendance_week` y `sessions_today` sin cambiar el resto del contrato de US-108.

## Endpoints

- `GET /api/v1/settings/hours` — roles: admin
- `PATCH /api/v1/settings/hours` — roles: admin
- `GET /api/v1/settings/classes` — roles: admin
- `PATCH /api/v1/settings/classes` — roles: admin
- `GET /api/v1/class-slots` — roles: admin
- `POST /api/v1/class-slots` — roles: admin
- `PATCH /api/v1/class-slots/{id}` — roles: admin
- `POST /api/v1/class-slots/{id}/cancel-future-sessions` — roles: admin
- `GET /api/v1/class-sessions` — roles: admin, coach
- `POST /api/v1/class-sessions` — roles: admin, coach
- `GET /api/v1/class-sessions/{id}` — roles: admin, coach
- `POST /api/v1/class-sessions/{id}/cancel` — roles: admin, coach
- `POST /api/v1/attendance` — roles: admin, coach
- `DELETE /api/v1/attendance/{id}` — roles: admin, coach
- `GET /api/v1/attendance` — roles: admin, coach
- `GET /api/v1/attendance/summary` — roles: admin, coach
- `GET /api/v1/members/{id}/attendance` — roles: admin, coach
- `GET /api/v1/members` — roles: admin, coach
- `GET /api/v1/dashboard` — roles: admin, coach

Notas de contrato:
- Check-in: entrada `{ session_id, member_id }`. Salida `{ id, flags, flagged, membership_status_at_checkin, attendance_count, capacity }`. Códigos 201, 401, 403, 404, 409 (`already_checked_in`, `session_cancelled`), 422 (solo por cuerpo mal formado).
- Borrado de asistencia: `reason?` en el cuerpo. Responde 204 o 404.
- `GET /api/v1/members/{id}/attendance` está en el router de `members`, que delega en `classes.service.member_attendance`.

## Componentes de front

- `web/src/features/system/components/HoursSettings.tsx` y `ClassesSettings.tsx` en `Config` (pestañas Horas y Clases; sin el campo de sobrecupo, N-38).
- `web/src/features/classes/pages/SchedulePage.tsx` (`/clases/horario`, solo admin): grilla semanal, `SlotPanel.tsx` en `SidePanel` para crear, editar, activar y desactivar. La acción "Cancelar sesiones futuras" abre un `ConfirmModal` con el conteo y el motivo, y avisa que no desactiva la franja.
- `web/src/features/classes/pages/SessionsPage.tsx` (`/clases`, con `?dia=hoy` del grupo "Hoy", Q25): vista semanal con "asistentes / cupo", sesión extra en `SidePanel`, cancelar con motivo y estado "Cancelada" con texto. Pestaña Asistencia (`/clases/asistencia`) con `AttendanceTab.tsx` (tabla y resumen semanal).
- `web/src/features/classes/pages/CheckInPage.tsx` (`/clases/:id/checkin`, `GymLayout` oscuro, controles de 56 px):
  - búsqueda con `GET /members?q=`;
  - toque para registrar;
  - `AttendeeList.tsx` con la marca roja siempre acompañada de texto ("Vencido", "Sin plan", "Congelado", "Cupo lleno", "Fuera de horario") a partir de `flags`;
  - contador de cupo;
  - acción "Quitar" con `ConfirmModal`;
  - estados de búsqueda, sin resultados, ya registrado, sesión cancelada y error de red.
- `web/src/features/members/components/MemberAttendanceTab.tsx` (pestaña Asistencia de `Socio_Ficha`: última asistencia y total de los últimos 30 días) y el filtro "Última asistencia" con su columna en `MembersFilterBar.tsx` (`// DESIGN-GAP:` si la columna no está en el diseño).
- `web/src/features/dashboard/components/AttendanceKpis.tsx`: tarjetas "Asistencia de la semana" y "Sesiones de hoy" ("No hay clases hoy" si la lista viene vacía).
- `api.ts` y `schemas.ts` por feature (TanStack Query 5 y Zod). Pruebas Vitest por componente y página. E2E Playwright `web/tests/e2e/checkin.spec.ts`: check-in de un socio al día y de uno vencido en la misma sesión. Sin colores literales.

## Worker, CLI e infraestructura

- Job `generate_sessions` en `worker/jobs/generate_sessions.py`, registrado a las 07:00 America/Bogota con `worker.job_runs` (US-113). Registra en el log JSON cuántas sesiones creó.
- `cli generate-sessions --days 14 [--as <email>]`, idempotente.
- Sin cambios de Compose ni de Nginx. La tablet usa la LAN; ningún flujo de check-in depende de internet.

## Dependencias

- EP-05: US-054 (secciones validadas y `version`, N-17), US-055 o la historia que fija `hours` (N-18).
- EP-09: US-083 (`compute_status` con 0 clases), US-086 (patrón de handlers), US-088 (renovación; ver la pregunta de US-160), US-092 (`status_for`, `member_ids_by_status`).
- EP-07: US-070 (búsqueda rápida y `names_for`), US-071 (patrón de filtros por ids sin JOIN), US-073 (pestañas de la ficha), US-076 (bajas y N-20).
- EP-08: `plans.service.get` (tipo del plan) para los handlers.
- EP-04: `auth.service.names_for` e `is_active_staff` (coach válido y nombre del coach).
- EP-01: US-013 (`today_bogota`, `FrozenClock`), US-014 (bus transaccional), US-016 (auditoría), US-019 (paginación), US-022 (test de models cruzados).
- EP-12: US-108 (contrato con `attendance_week` y `sessions_today` en `null`).
- EP-13: US-113 (worker y `job_runs`).
- EP-06: US-062 (`GymLayout`), US-063 (`DataTable`), `SidePanel`, `ConfirmModal`, `KpiCard`, `StatusTag`.
- EP-22 depende de esta épica: `class_sessions.wod_id`, `PATCH /class-sessions/{id}` (US-168, N-41) y `GET /class-sessions/{id}/attendance` (US-169) se construyen dentro del módulo `classes`.

## Riesgos

- Ciclo de imports `members.service` ↔ `classes.service` introducido por US-163 (ver la brecha). Mitigación: la regla propuesta y un test de arquitectura antes de implementar US-163.
- Renovación tras agotar las clases: el `EXCLUDE` de Q1 rechaza una renovación que empieza hoy si la tiquetera agotada conserva un `end_date` futuro. Mitigación: la pregunta abierta de US-160, que hay que responder antes de implementarla.
- Correspondencia de `pending_payment` con el flag `no_membership`: es una precisión sobre N-38. Mitigación: confirmar en el gate; cambiarla es solo tocar `checkin_outcome`.
- Concurrencia en el cupo: dos check-ins simultáneos pueden registrar el asistente 16 y el 17 sin marcar `over_capacity` en uno de ellos. Es aceptable porque el cupo solo advierte. Mitigación: contar dentro de la misma transacción con `SELECT ... FOR UPDATE` sobre la sesión.
- Rendimiento del check-in (menos de 2 s) y del filtro de última asistencia (menos de 500 ms con 1.000 socios). Mitigación: índices de `0062`, consultas en lote y prueba de rendimiento con 1.000 socios.
- Conversión de hora local a UTC: Colombia no tiene horario de verano, pero se usa `zoneinfo("America/Bogota")` y no un desfase fijo. Mitigación: pruebas puras que cruzan cambio de mes y de año.
- La ubicación de la membresía por fecha en los handlers depende de la invariante de Q1 (sin solapes entre membresías no canceladas del mismo socio). Mitigación: prueba con membresía vigente por días y futura por clases (no se descuenta nada).
- Front condicionado a D1.

## Estado y estimación por historia

- US-154 · Configurar horas y clases — **READY** — 9 h — Secciones `hours` (lista de rangos) y `classes` sin `allow_over_capacity`, con los rangos de N-18 y N-38.
- US-155 · Horario semanal de franjas — **READY** — 20 h — Migración `0060`, `validate_slot` pura, coach validado por `auth.service`, `start_time` local (N-40) y Q23 sin tocar sesiones generadas.
- US-156 · Generar sesiones desde el horario — **READY** — 18 h — Migración `0061`, `planned_sessions` pura, generación idempotente a 14 días por job diario (Q23) con `SYSTEM_USER_ID` (N-15).
- US-157 · Sesiones de la semana — **READY** — 22 h — Lista semanal con `week_range` pura, sesión extra, cancelar con motivo y `done` calculado al leer.
- US-158 · Cancelar sesiones futuras de una franja — **READY** — 7 h — Cancelación atómica de las `scheduled` futuras de la franja con motivo y un evento por sesión (Q23).
- US-159 · Check-in en tablet — **READY** — 36 h — Migración `0062` con `flags`, `removed_at` e índice parcial; nunca 409 ni 422 por cupo, hora ni membresía (N-38, N-39); solo 409 por duplicado o sesión cancelada; incluye E2E.
- US-160 · Descontar y devolver clases — **NEEDS_REFINEMENT** — 13 h — Pregunta: cuando una tiquetera llega a `classes_remaining = 0` con `end_date` futuro, la renovación (`next_start_for_renewal` = hoy, porque ya venció) choca con el `EXCLUDE` de Q1 sobre el rango de fechas, y devolver la clase (N-40) puede dejar dos membresías vigentes. ¿Al consumir la última clase se recorta `end_date` a la fecha del consumo y la renovación de una tiquetera agotada empieza al día siguiente? Propuesta por defecto: sí. El fin original se guarda en `original_end_date` (migración `0064`). Al devolver la clase se restaura el fin original solo si no se solapa con otra membresía no cancelada; si se solapa, la clase vuelve al saldo y la membresía sigue `expired`.
- US-161 · Borrar asistencia — **READY** — 8 h — Borrado lógico con `removed_at`, `removed_by` y `removed_reason` (N-40), admin y coach (Q8), auditoría `update` y `AttendanceRemoved` en la misma transacción.
- US-162 · Reportes de asistencia — **READY** — 14 h — Lista paginada, resumen semanal por franja con `weekly_summary` pura (máximo 26 semanas) y pestaña de la ficha.
- US-163 · Filtro de última asistencia — **ARCHITECTURAL_GAP_DETECTED** — 9 h — Brecha: `members.service.list` llama a `classes.service.last_attendance_for` y `member_ids_with_attendance_since`, mientras `classes.service` ya llama a `members.service.names_for` y `exists_active`. Es un ciclo de imports entre services sin solución documentada (el mismo patrón que `members` ↔ `memberships` en v0.1). Propuesta: fijar en `CLAUDE.md` y en `tests/architecture/test_service_cycles.py` la regla "entre services con dependencia mutua documentada se importa el módulo (`from app.modules.classes import service as classes_service`) y se llama en tiempo de ejecución; prohibido `from app.modules.x.service import funcion`". El test admite solo los pares declarados en una lista blanca (`members`↔`memberships`, `members`↔`classes`) y falla ante cualquier otro ciclo.
- US-164 · KPIs de asistencia en Inicio — **READY** — 8 h — `classes.service.today` y `week_attendance` compuestos por `dashboard` (lectura permitida), sin cambiar el resto del contrato de US-108.

## Total de la épica

- **Total: 164 h**
