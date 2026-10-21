# US-159 · Como coach quiero hacer check-in de los socios en la tablet sin que nunca se bloquee por su membresía para no frenar la fila y saber quién entrena vencido

- **Épica:** EP-21 · Clases, horario y check-in
- **Bounded context:** Classes (esquema `classes`), lee estado de Memberships
- **Versión:** v0.4
- **Actor:** administrador, coach
- **Tamaño:** 8
- **Prioridad:** P0 ruta crítica de la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `CheckIn` (`/clases/:id/checkin`, tablet 1024x768, tema oscuro)

## Historia

Como coach en el piso del box
quiero buscar al socio y registrarle la asistencia a la clase en dos o tres toques
para que entre sin esperar y, si está vencido o sin plan, quede marcado en rojo para hablarle después

## Contexto de dominio

- **Aggregate / entidades:** `ClassSession` con su entidad interna `Attendance` (`member_id`, `checked_in_at`, `checked_in_by`, `membership_status_at_checkin`, `flagged`).
- **Reglas que aplica:** RN-09 (el check-in nunca bloquea por estado de membresía: registra y marca); RN-10 (una asistencia por sesión y socio); no hay check-in en sesión `cancelled`; el cupo es advertencia, no bloqueo (el coach decide); Q11 (`checkin_window_min`, `allow_over_capacity`); RN-15.
- **Eventos que emite:** `MemberCheckedIn(member_id, session_id, flagged)`
- **Eventos que consume:** ninguno
- **Funciones puras:** `classes.checkin_outcome(membership_status) -> (allowed = True, flagged: bool)`, `classes.within_checkin_window(starts_at, now, window_min) -> bool`, `classes.capacity_outcome(count, capacity, allow_over_capacity) -> CapacityOutcome`

## Alcance

- **Backend:** migración `classes.attendance`; `POST /api/v1/attendance` `{ session_id, member_id }`; estado leído con `memberships.service.status_for([member_id])`; búsqueda rápida con `GET /api/v1/members?q=` (US-070); `GET /api/v1/class-sessions/{id}` con asistentes.
- **Front:** pantalla `CheckIn` en `GymLayout`: búsqueda con resultados grandes (56 px), toque para registrar, lista de asistentes con marca roja y texto "Vencido" o "Sin plan", contador de cupo y aviso de cupo lleno.

## Criterios de aceptación

1. `POST /attendance` exige rol `admin` o `coach`; socio recibe 403.
2. `checkin_outcome` devuelve `allowed = True` para todos los estados (`active`, `expiring`, `expired`, `frozen`, `none`, `pending_payment`) y `flagged = True` para `expired`, `none`, `frozen` y `pending_payment`, `False` para `active` y `expiring`; prueba pura con cada estado.
3. Un socio vencido o sin membresía queda registrado con 201, `flagged = true` y `membership_status_at_checkin` con su estado; ningún estado de membresía produce un error.
4. Un segundo check-in del mismo socio en la misma sesión devuelve 409 `already_checked_in` (índice único `(session_id, member_id)`), RN-10.
5. Check-in en una sesión `cancelled` devuelve 409 `session_cancelled`.
6. Con `allow_over_capacity = true`, el check-in que supera el cupo se registra con 201 y la respuesta trae `over_capacity: true`; la pantalla muestra "Cupo lleno" como advertencia.
7. Con `allow_over_capacity = false` se aplica el supuesto declarado abajo.
8. Fuera de la ventana `checkin_window_min` respecto de `starts_at` se aplica el supuesto declarado abajo.
9. Un socio dado de baja (`deleted_at` no nulo) no aparece en la búsqueda; si se envía su id, 404.
10. Cada check-in emite `MemberCheckedIn` en la misma transacción, queda auditado (`attendance` con `__audited__ = True`) y guarda `checked_in_at` en UTC y `checked_in_by`.
11. La respuesta de la API llega en menos de 2 segundos en la LAN con 1.000 socios y el flujo buscar-tocar-confirmar toma 3 toques o menos.
12. La pantalla nunca muestra campos cifrados del socio (solo nombre, apellido y estado).

## Escenarios BDD

```gherkin
# language: es
Característica: Check-in en la tablet

  Antecedentes:
    Dado que inicié sesión como coach en la tablet
    Y la sesión de hoy a las 18:00 está programada con cupo 15

  Escenario: Check-in de un socio al día y de uno vencido
    Cuando registro a "Juan Rojas", que está al día
    Y registro a "Pedro Díaz", que está vencido
    Entonces ambos quedan en la lista de asistentes
    Y "Pedro Díaz" aparece marcado en rojo con el texto "Vencido"
    Y "Juan Rojas" aparece sin marca

  Escenario: Check-in repetido
    Dado que "Juan Rojas" ya hizo check-in en esta sesión
    Cuando intento registrarlo otra vez
    Entonces veo "Ya registró asistencia en esta clase"
    Y la API responde 409

  Escenario: Clase llena con sobrecupo permitido
    Dado que la sesión ya tiene 15 asistentes y se permite superar el cupo
    Cuando registro a "Laura Gómez"
    Entonces queda registrada
    Y veo la advertencia "Cupo lleno"
```

## Endpoints

- `POST /api/v1/attendance` — rol(es): admin, coach — entrada: `{ session_id, member_id, override_capacity?: bool }` — salida: `{ id, flagged, membership_status_at_checkin, over_capacity, attendance_count, capacity }` — códigos: 201, 401, 403, 404, 409, 422
- `GET /api/v1/class-sessions/{id}` — rol(es): admin, coach — códigos: 200, 401, 403, 404
- `GET /api/v1/members?q=` — rol(es): admin, coach (búsqueda rápida, US-070)

## Pantalla

- `CheckIn` en `/clases/:id/checkin` con `GymLayout` (oscuro, 56 px). Estados: buscando, sin resultados, registrado, ya registrado, cupo lleno, sesión cancelada, error de red. La marca roja siempre va con texto.

## Notas técnicas

- **Migración:** sí; tabla `classes.attendance` con columnas comunes, FK a `class_sessions`, `member_id` UUID sin FK cruzada de esquema (regla de módulos), índice único `(session_id, member_id)`.
- **Trigger / restricciones:** `CHECK membership_status_at_checkin IN (...)`.
- **Funciones puras a probar:** `checkin_outcome` (todos los estados), `within_checkin_window` (bordes exactos de la ventana), `capacity_outcome` (cupo justo, cupo superado con y sin permiso).
- **Pruebas:** puras, service con base real (409, evento, auditoría), router, front (flujo de 3 toques), E2E Playwright: check-in de un socio al día y uno vencido en la misma sesión.
- **Archivos principales:** `api/src/app/modules/classes/{models,service,router}.py`, `web/src/features/classes/pages/CheckInPage.tsx`.

## Supuestos

- Supuesto: con `allow_over_capacity = false`, el check-in que supera el cupo devuelve 409 `session_full` y se puede repetir con `override_capacity: true` (el coach decide). Así el cupo sigue siendo decisión del coach y no un bloqueo duro; contradice en parte la invariante "el cupo es advertencia, no bloqueo", por eso va al gate.
- Supuesto: fuera de la ventana `checkin_window_min` (antes de `starts_at - window` o después de `starts_at + window`) el check-in devuelve 422 `outside_checkin_window`. RN-09 solo prohíbe bloquear por estado de membresía, no por hora; si el gate prefiere que la ventana solo advierta, se cambia a 201 con `outside_window: true`.
- Supuesto: `pending_payment` y `frozen` se marcan `flagged` (el modelo solo nombra vencido y sin plan como ejemplos de marca roja).

## Dependencias

- US-157 · Sesiones de la semana (sesión y detalle)
- US-092 · Resumen y consultas de estado (`status_for`)
- US-070 · Buscar y listar socios (búsqueda rápida)
- US-062 · Layouts portal, gym y TV (`GymLayout`)

## INVEST

- **Independiente:** el descuento de clases va aparte (US-160).
- **Negociable:** reglas de ventana y sobrecupo (supuestos).
- **Valiosa:** recupera plata de socios vencidos sin frenar la fila.
- **Estimable:** modelo, endpoint, tres funciones puras y una pantalla táctil.
- **Pequeña:** 8 puntos, en el límite; si crece, se separa la pantalla.
- **Testeable:** RN-09 y RN-10 son binarias.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] E2E de check-in en verde
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `attendance`
- [ ] Revisión de PR aprobada
