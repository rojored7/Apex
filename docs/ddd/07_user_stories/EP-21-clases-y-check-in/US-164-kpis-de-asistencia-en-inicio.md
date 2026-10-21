# US-164 · Como administrador quiero ver en Inicio la asistencia de la semana y las sesiones de hoy para saber de un vistazo cómo va la ocupación del box

- **Épica:** EP-21 · Clases, horario y check-in
- **Bounded context:** Dashboard (lectura) sobre Classes
- **Versión:** v0.4
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Inicio` (`/`, tarjetas Asistencia de la semana y Sesiones de hoy)

## Historia

Como administrador o coach
quiero ver en Inicio cuántas asistencias van esta semana y qué sesiones hay hoy con su ocupación
para decidir en segundos si hay que reforzar un horario o avisar de una clase llena

## Contexto de dominio

- **Aggregate / entidades:** `ClassSession`, `Attendance` (lectura).
- **Reglas que aplica:** el contrato de `/dashboard` se fija en v0.1 con estos campos en `null`; aquí solo se llenan sin cambiar el contrato (EP-12); Q28 (semana y "hoy" en Bogotá); Q25 (el grupo "Hoy" enlaza a `Sesiones` filtrada a hoy).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna nueva

## Alcance

- **Backend:** `classes.service.today(today)` y `classes.service.week_attendance(today)`; `dashboard.service.summary` llena `attendance_week` y `sessions_today`.
- **Front:** las dos `KpiCard` dejan de mostrarse vacías; "Sesiones de hoy" enlaza a `/clases?dia=hoy`.

## Criterios de aceptación

1. `GET /api/v1/dashboard` devuelve `attendance_week: { count, flagged_count }` con las asistencias de lunes a hoy de la semana en curso en Bogotá.
2. `sessions_today` es una lista con `id`, `starts_at` (UTC), `coach_name`, `capacity`, `attendance_count` y `status` de las sesiones de hoy en Bogotá, ordenada por hora.
3. El resto de los campos del contrato no cambia (prueba de contrato contra el `openapi.json` anterior: solo dejan de ser `null` estos dos).
4. Sin sesiones hoy, `sessions_today` es `[]` (no `null`) y la tarjeta muestra "No hay clases hoy".
5. `GET /dashboard` sigue exigiendo admin o coach y responde en menos de 300 ms con 1.000 socios.
6. El módulo `dashboard` obtiene los datos por `classes.service`, sin importar `models` ajenos.

## Escenarios BDD

```gherkin
# language: es
Característica: KPIs de asistencia en Inicio

  Escenario: Martes con tres clases
    Dado que hoy es martes y hay sesiones a las 06:00, 12:00 y 18:00
    Y esta semana hubo 41 asistencias, 3 marcadas
    Cuando el coach abre Inicio
    Entonces la tarjeta de asistencia muestra 41 y 3 marcadas
    Y la tarjeta de sesiones de hoy muestra las tres clases con su ocupación

  Escenario: Día sin clases
    Dado que hoy no hay sesiones programadas
    Cuando el administrador abre Inicio
    Entonces la tarjeta de sesiones de hoy dice "No hay clases hoy"
```

## Endpoints

- `GET /api/v1/dashboard` — rol(es): admin, coach — salida: llena `attendance_week` y `sessions_today` — códigos: 200, 401, 403

## Pantalla

- `Inicio`, tarjetas de asistencia y sesiones de hoy. Estados de carga y error.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** reutiliza `week_range` (US-157).
- **Pruebas:** service con base real, prueba de contrato del dashboard, arquitectura (sin models ajenos), front.
- **Archivos principales:** `api/src/app/modules/dashboard/service.py`, `api/src/app/modules/classes/service.py`, `web/src/features/dashboard/pages/HomePage.tsx`.

## Supuestos

- Supuesto: la forma exacta de `attendance_week` y `sessions_today` se fija aquí si US-108 solo los dejó como `null` sin tipo; si US-108 ya fijó el tipo, manda US-108.

## Dependencias

- US-159 · Check-in en tablet
- US-108 · Contrato del tablero

## INVEST

- **Independiente:** llena dos campos existentes.
- **Negociable:** métricas mostradas.
- **Valiosa:** frase guía del producto (10 segundos).
- **Estimable:** pequeño.
- **Pequeña:** sí.
- **Testeable:** conteos y contrato estable.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: pruebas de las tarjetas; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
