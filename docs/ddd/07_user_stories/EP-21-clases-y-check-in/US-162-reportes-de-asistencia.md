# US-162 · Como administrador quiero consultar la asistencia por socio y por semana para ver la ocupación real de cada horario y la constancia de cada socio

- **Épica:** EP-21 · Clases, horario y check-in
- **Bounded context:** Classes (esquema `classes`)
- **Versión:** v0.4
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Sesiones` (`/clases/asistencia`, pestaña Asistencia) y `Socio_Ficha` (`/socios/:id`, pestaña Asistencia)

## Historia

Como administrador o coach
quiero ver la asistencia filtrada por socio y por rango de fechas, y el resumen por semana
para saber qué horarios se llenan y qué socios dejaron de venir

## Contexto de dominio

- **Aggregate / entidades:** `Attendance`, `ClassSession`.
- **Reglas que aplica:** paginación (regla de datos 6); fechas en UTC en API; RN-15; Training y Classes nunca leen campos cifrados del socio.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `classes.weekly_summary(rows) -> list[WeekBucket]`

## Alcance

- **Backend:** `GET /api/v1/attendance?member_id&from&to&session_id&flagged` paginado; `GET /api/v1/attendance/summary?from&to` con conteo por semana y por franja; `GET /api/v1/members/{id}/attendance` para la pestaña de la ficha.
- **Front:** pestaña Asistencia de `Sesiones` (tabla y resumen semanal) y pestaña Asistencia de `Socio_Ficha` (lista de clases asistidas con marca `flagged`).

## Criterios de aceptación

1. Todos los endpoints exigen rol `admin` o `coach`; socio recibe 403.
2. `GET /attendance` filtra por `member_id`, `session_id`, `flagged`, `from` y `to` (ISO 8601 UTC, sobre `checked_in_at`), pagina con `limit` (1 a 200, por defecto 25) y `offset`, y responde `{ items, total, limit, offset }`.
3. Cada fila trae nombre y apellido del socio, fecha y hora de la sesión, `flagged` y `membership_status_at_checkin`; nunca campos cifrados.
4. `GET /attendance/summary` devuelve, por semana ISO (lunes a domingo en Bogotá), el total de asistencias, asistencias marcadas y ocupación promedio (asistentes / cupo) por franja; un rango mayor a 26 semanas devuelve 422.
5. `from` mayor que `to` devuelve 422.
6. La pestaña de la ficha muestra la última asistencia y el total de los últimos 30 días.

## Escenarios BDD

```gherkin
# language: es
Característica: Reportes de asistencia

  Escenario: Asistencia de un socio en el mes
    Dado que "Juan Rojas" asistió a 9 clases en octubre, 2 de ellas marcado como vencido
    Cuando el administrador abre la pestaña Asistencia de su ficha
    Entonces ve las 9 clases con fecha y hora de Bogotá
    Y 2 aparecen con la marca "Vencido"

  Escenario: Rango de fechas invertido
    Cuando pido GET /api/v1/attendance?from=2026-10-31&to=2026-10-01
    Entonces recibo 422 con field "from"
```

## Endpoints

- `GET /api/v1/attendance` — rol(es): admin, coach — códigos: 200, 401, 403, 422
- `GET /api/v1/attendance/summary` — rol(es): admin, coach — entrada: `from`, `to` — salida: `{ weeks: [...] }` — códigos: 200, 401, 403, 422
- `GET /api/v1/members/{id}/attendance` — rol(es): admin, coach — paginado — códigos: 200, 401, 403, 404

## Pantalla

- `Sesiones` (pestaña Asistencia en `/clases/asistencia`) y pestaña Asistencia de `Socio_Ficha`. Estados de carga, vacío y error.

## Notas técnicas

- **Migración:** no; índice `attendance(member_id, checked_in_at)` si falta.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `weekly_summary` (semanas sin asistencias, cupo 0 no divide).
- **Pruebas:** puras, service con base real, router, front.
- **Archivos principales:** `api/src/app/modules/classes/service.py`, `web/src/features/classes/components/AttendanceTab.tsx`.

## Supuestos

- Supuesto: el resumen semanal es `GET /attendance/summary`; ningún documento nombra el endpoint del reporte por semana.
- Supuesto: límite de 26 semanas por consulta de resumen.

## Dependencias

- US-159 · Check-in en tablet
- US-073 · Ver ficha del socio

## INVEST

- **Independiente:** solo lectura.
- **Negociable:** métricas del resumen.
- **Valiosa:** ocupación real y retención.
- **Estimable:** tres lecturas y dos pestañas.
- **Pequeña:** sí.
- **Testeable:** filtros y conteos verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
