# EP-21 · Clases, horario y check-in

- **Versión del plan:** v0.4 (versión 0.4 completa; nombre `class_slots` en lugar de `schedule_templates`, `BRECHAS.md` sección 3).
- **Bounded context:** Classes (negocio, esquema `classes`). Reacciona en Memberships (descuento de clases) y alimenta Dashboard.
- **Estimación relativa:** L.

## Objetivo de negocio

Saber quién vino a qué clase, cuántos caben y quién está entrenando vencido, sin frenar la fila en la puerta. El check-in en la tablet nunca bloquea (RN-09): el socio vencido entra, pero queda marcado en rojo para que el coach o recepción le hable. Con eso el gimnasio recupera plata que hoy se escapa y ve la ocupación real de cada horario.

## Actores

- Administrador: configura el horario semanal.
- Administrador y coach: gestionan sesiones, hacen check-in y consultan asistencia.
- Tablet del piso del box (sesión de coach), en tema oscuro.
- Memberships: descuenta o devuelve clases por evento.

## Capacidades incluidas

### Backend
- Aggregate `ClassSlot` (franja semanal: día, hora de inicio, duración, cupo, coach por defecto, activa).
- Aggregate `ClassSession` (generada desde las franjas o extra; `starts_at` en UTC, cupo, coach, `wod_id` nulo hasta v0.5, estados `scheduled`, `cancelled`, `done`, motivo de cancelación).
- Entidad interna `Attendance`: socio, hora de check-in, quién lo hizo, `membership_status_at_checkin` y `flagged`.
- Función pura `classes.checkin_outcome(membership_status)` que siempre permite y decide la marca (RN-09); estado leído con `memberships.service.status_for`.
- Invariantes: una asistencia por sesión y socio (RN-10); no hay check-in en una sesión cancelada; el cupo es advertencia, no bloqueo.
- Generación de sesiones desde el horario para un rango de semanas, sin duplicar las ya generadas.
- Eventos `SessionGenerated`, `SessionCancelled`, `MemberCheckedIn`, `AttendanceRemoved`.
- En Memberships: handlers `on_member_checked_in` y `on_attendance_removed`, que bajan o devuelven `classes_remaining` en planes por clases y emiten `ClassConsumed` (RN-05); con cero clases la membresía pasa a `expired` (RN-06).
- Reportes de asistencia por socio y por semana.
- Filtro `last_attendance` en la lista de socios (EP-07).
- Campos "asistencia de la semana" y "sesiones de hoy" del tablero (EP-12).
- Secciones `hours` y `classes` de Settings (EP-05).
- Endpoints: `/class-slots` (admin), `/class-sessions` (lista por semana, sesión extra, cancelar), `GET /class-sessions/{id}`, `POST /attendance`, `DELETE /attendance/{id}`, `GET /attendance` con filtros de socio y fechas.

### Front
- Pantalla de sesiones de la semana con pestaña de asistencia.
- Pantalla de horario semanal (admin).
- Pantalla de check-in para tablet con búsqueda rápida de socio, marca roja para vencidos y sin plan, y advertencia de cupo lleno.
- Pestaña Asistencia de la ficha del socio y KPIs de asistencia en Inicio.

## Fuera de alcance

- Reservas de cupo por parte del socio.
- Check-in autónomo del socio (código QR o similar).
- Nómina o liquidación de coaches por clases (fuera de alcance del producto).

## Criterios de éxito medibles

- Un socio vencido o sin membresía hace check-in y queda `flagged = true`; ningún estado de membresía produce un error.
- Un segundo check-in del mismo socio en la misma sesión devuelve 409 (RN-10).
- Un check-in en un plan de 12 clases deja `classes_remaining = 11`; borrar esa asistencia lo devuelve a 12; con la última clase consumida la membresía queda `expired`.
- Generar las sesiones de la misma semana dos veces no duplica ninguna.
- El check-in se completa en menos de 3 toques y menos de 2 segundos de respuesta en la tablet.
- E2E de Playwright: check-in de un socio al día y de uno vencido en la misma sesión.

## Dependencias

- EP-09 Membresías (estado para el check-in y descuento de clases).
- EP-07 Padrón de socios (búsqueda rápida).
- EP-05 Configuración del gimnasio (horas, cupo por defecto).
- EP-12 Tablero de inicio (campos de asistencia).
- EP-06 Layout y componentes compartidos del front (`GymLayout`).

## Riesgos

- La tablet depende de la red local; con internet intermitente debe seguir funcionando en la LAN.
- Quién puede borrar una asistencia no está fijado (ver preguntas abiertas); un borrado devuelve una clase y tiene efecto en plata.
- Cambios de horario con sesiones ya generadas: no hay regla sobre si se regeneran o se conservan.

## Pantallas del diseño que habilita

- `Sesiones`, `Horario`, `CheckIn`, pestaña Asistencia de `Socio_Ficha`, KPIs de asistencia y sesiones de hoy en `Inicio`.
