# Sprint 7 · v0.4: clases, horario y check-in

- Versión: v0.4.
- Épica: EP-21 (clases, horario y check-in).
- Tamaño: 11 historias, 39 puntos y 164 h relativas.
- Nivel de detalle: bloques en orden de ejecución; los slices (W0-1 a W0-4, A1 a B3, C1 a R3, F1 a F6 y V1 a V9) están en `docs/ddd/blueprints/sprint-07-plan.md`, sección 3.
- Historias del sprint: US-154, US-155, US-156, US-157, US-158, US-159, US-160, US-161, US-162, US-163, US-164.

## Objetivo

Que el box publique su horario semanal y que el sistema genere las sesiones con 14 días de antelación (Q23). El coach registra la asistencia desde una tablet en segundos.

El check-in nunca bloquea (RN-09, N-38, N-39): siempre registra y advierte en rojo cuando la membresía está vencida o congelada, cuando no hay membresía, cuando se pasó el cupo, cuando se está fuera de la ventana o cuando la sesión no es de hoy ni de ayer (`other_day`): siete banderas contando `pending_payment`. Las tiqueteras por clases descuentan y devuelven clases (Q4). Inicio muestra la asistencia.

## Demo al final del sprint

1. **Horario.** En Configuración, fijar el horario de apertura y `default_capacity = 15`. En Horario, crear la franja "Lunes 6:00 CrossFit" con su coach.
2. **Sesiones.** El job diario genera las sesiones de los próximos 14 días y es idempotente. La pantalla Sesiones muestra la semana. Se puede cancelar una sesión con motivo, o cancelar todas las sesiones futuras de la franja (Q23).
3. **Check-in en la tablet (`GymLayout`).**
   - Registrar a un socio al día.
   - Registrar a un socio vencido: queda registrado con `flags: ["expired"]` en rojo y sin 409.
   - Una sesión que no es de hoy ni de ayer registra con `other_day`, también sin 409.
   - El asistente 16 queda con `over_capacity`.
4. **Tiqueteras.**
   - Una tiquetera de 10 clases baja a 9.
   - Borrar la asistencia, que es borrado lógico con motivo (N-40), devuelve la clase.
   - Al agotar la tiquetera, `end_date` se recorta a la fecha de consumo y se guarda `original_end_date` (refinamiento de US-160).
5. **Reportes y filtros.**
   - Reportes de asistencia por semana y franja.
   - Pestaña Asistencia en la ficha del socio.
   - Filtro "sin asistir desde" en la lista de socios.
   - Inicio llena `attendance_week` y `sessions_today`.

## Dependencias de sprints anteriores

Solo depende de v0.1. Por eso este sprint se puede ejecutar antes que los Sprints 5 y 6 si el negocio lo prioriza.

- **Sprint 4A:**
  - US-108 (contrato del tablero con `attendance_week` y `sessions_today` en `null`);
  - US-113 (worker y `job_runs`).
- **Sprint 3:**
  - US-083 (`compute_status` con 0 clases);
  - US-086 (patrón de handlers);
  - US-088 (renovación);
  - US-092 (`status_for` y `member_ids_by_status`);
  - US-071 (filtros por ids sin JOIN);
  - US-073 (pestañas de la ficha);
  - US-076 (bajas, N-20).
- **Sprint 2:**
  - US-054 y US-055 (secciones `hours` y `classes`, N-17 y N-18);
  - US-070 (búsqueda rápida y `names_for`);
  - `plans.service.get`;
  - `auth.service.names_for` e `is_active_staff`;
  - US-062 (`GymLayout`).

## Historias en orden de ejecución (por bloques)

1. **Bloque A · Configuración y horario.**
   - US-154 · Configurar horas y clases: sin `allow_over_capacity` (N-38); rangos de N-18.
   - US-155 · Horario semanal de franjas: `start_time` en hora local (N-40) y `validate_slot` pura.
2. **Bloque B · Sesiones.**
   - US-156 · Generar sesiones: `planned_sessions` pura y job diario con `SYSTEM_USER_ID`.
   - US-157 · Sesiones de la semana: `week_range` pura, sesión extra y cancelación con motivo.
   - US-158 · Cancelar las sesiones futuras de una franja: atómica, con un evento por sesión.
3. **Bloque C · Asistencia.**
   - US-159 · Check-in en tablet:
     - `flags` en lugar de errores;
     - solo responde 409 por duplicado o por sesión cancelada;
     - siete banderas: `expired`, `no_membership`, `frozen`, `pending_payment`, `over_capacity`, `out_of_window` y `other_day` (S7-D12, S7-D27);
     - incluye el E2E.
   - US-160 · Descontar y devolver clases: `classes_remaining`, recorte de `end_date` y `original_end_date`.
     - Deuda heredada del Sprint 3 (PM2 de la revisión de Fase 4, S3-D92): al gastar la última clase, el descuento recorta `end_date` a `min(end_date, max(start_date, hoy))` (S7-D29); así ni `rules.find_overlap` ni la `EXCLUDE` `ex_memberships_member_dates` bloquean la compra siguiente. Hoy una tiquetera con `classes_remaining = 0` y `end_date` futuro da `MembershipOverlap` al vender: `tests/memberships/test_sell_service.py::test_una_tiquetera_agotada_con_fin_futuro_hoy_bloquea_la_compra` fija ese comportamiento y esta historia la invierte.
   - US-161 · Borrar asistencia: borrado lógico, para admin y coach (Q8); emite `AttendanceRemoved`. El coach solo quita asistencias de sesiones de hoy o de ayer (Bogotá); fuera de eso, 403 `attendance_locked`; el admin, cualquiera (S7-D27).
4. **Bloque D · Lecturas.**
   - US-162 · Reportes de asistencia: `weekly_summary` pura, con un máximo de 26 semanas.
   - US-163 · Filtro de última asistencia (G-10). Antes de esta historia, la lista blanca de G-03 se amplía con el par members↔classes.
   - US-164 · KPI de asistencia en Inicio.

Waves:
- **Wave 0** (W0-1 a W0-4): documentos y decisiones; `0025`; volumen `keys` con `sign/` y api sin la llave de firma; línea base, cubetas `classes-write` y `attendance-write` (25 y 24) y gates de vitest con 2 hilos.
- **Wave 3a** (A1, A2, B1, B2, B3): configuración, franjas y sesiones. **Wave 3b** (C1, C2, C3, R1, R2, R3): asistencia, tiqueteras y lecturas.
- **Waves 5a (F1 a F3) y 5b (F4 a F6); validación V1 a V9:**
  - pantallas Horario, Sesiones y CheckIn (en `GymLayout`);
  - pestaña Asistencia de la ficha;
  - tarjetas de Inicio.
  - El enlace "Hoy" del menú no es una pantalla nueva: son tres enlaces a pantallas que ya existen (Q25).

## Migraciones que aplica

En orden ascendente (S7-D2; la cabeza actual es `0024_crypto_rotation_from_api` y todos los ids caben en `varchar(32)`):
- `0025_s6_hardening` (deuda del Sprint 6: FK de `attachments.key_id`, `sign_iff_public_key`, `photo_not_sensitive`, `public_key` inmutable, `guard_jobs_update` solo para `rotate`; S7-D3).
- `0026_class_slots` (US-155). Crea el esquema `classes` y `classes.class_slots`.
- `0027_class_sessions` (US-156). Incluye la columna nula `wod_id`, que usa EP-22 en el Sprint 8.
- `0028_attendance` (US-159), con `flags` (siete banderas, incluida `other_day`), `removed_at`, `removed_by` y `removed_reason`, el trigger `guard_attendance` y el índice único parcial sobre (`session_id`, `member_id`) `WHERE removed_at IS NULL`.
- `0029_memberships_orig_end_date` (US-160), con `original_end_date` nula. No hay migración de CHECK de `classes_remaining`: ya existen desde `0008`. La numeración `0060` a `0064` del plan original no se usa.

## Endpoints que expone

- **Settings:** `GET` y `PATCH /api/v1/settings/hours`; `GET` y `PATCH /api/v1/settings/classes`.
- **Class slots:**
  - `GET /api/v1/class-slots` y `POST /api/v1/class-slots`;
  - `PATCH /api/v1/class-slots/{id}`;
  - `POST /api/v1/class-slots/{id}/cancel-future-sessions`.
- **Class sessions:**
  - `GET /api/v1/class-sessions` y `POST /api/v1/class-sessions`;
  - `GET /api/v1/class-sessions/{id}`;
  - `POST /api/v1/class-sessions/{id}/cancel`.
- **Attendance:**
  - `POST /api/v1/attendance` y `GET /api/v1/attendance`;
  - `GET /api/v1/attendance/summary`;
  - `DELETE /api/v1/attendance/{id}`, que es borrado lógico.
- **Members:** `GET /api/v1/members/{id}/attendance`.
- **Cambios en endpoints de v0.1:**
  - `GET /api/v1/members` recibe el filtro de última asistencia;
  - `GET /api/v1/dashboard` llena `attendance_week` y `sessions_today`.

## Tests de arquitectura que deben pasar

- Toda la suite anterior.
- `test_service_import_graph.py`, ampliada con el par members↔classes (G-10). Falla ante cualquier otro ciclo.
- `test_no_cross_models.py` y `test_no_cross_schema_sql.py` sobre `classes`.
- `test_every_route_has_role.py` sobre las rutas nuevas.

## Riesgos y mitigación

1. [MEDIUM] Ciclo de imports members↔classes.
   - Mitigación: la regla de G-03 y su prueba van antes de US-163.
2. [MEDIUM] Al renovar una tiquetera agotada, el `EXCLUDE` de Q1 choca con un `end_date` futuro.
   - Mitigación: el refinamiento de US-160 aceptado (recorte de `end_date`, S7-D29).
   - Al devolver una clase, el fin original se restaura solo si no se solapa con otra membresía.
3. [MEDIUM] Dos check-ins simultáneos pueden registrar al asistente 16 y al 17 sin marcar `over_capacity` en uno de ellos.
   - Mitigación: contar dentro de la misma transacción con `SELECT ... FOR UPDATE`. Es aceptable, porque el cupo solo advierte.
4. [MEDIUM] Rendimiento: el check-in debe tardar menos de 2 s, y el filtro de última asistencia menos de 500 ms con 1.000 socios.
   - Mitigación: índices de `0028` y una prueba de rendimiento.
5. [LOW] Conversión de hora local a UTC.
   - Mitigación: `zoneinfo("America/Bogota")` y pruebas que cruzan cambio de mes y de año.

## Definición de hecho del sprint

- Definición de hecho común del README.
- E2E del check-in en la tablet con las cinco banderas.
- El job de generación de sesiones con `--run-once`, dos veces el mismo día y sin duplicar.
- Seguridad, revisada por `security-reviewer`:
  - el check-in no expone datos cifrados en la tablet (modo tablet, S7-D24);
  - borrar una asistencia queda auditado;
  - roles admin y coach en todas las rutas (franjas y cancelar futuras solo admin);
  - el api no ve la llave de firma (S7-D4, S7-D23).
- `verify-delivery`, con un check-in real y su descuento verificado en la base.
