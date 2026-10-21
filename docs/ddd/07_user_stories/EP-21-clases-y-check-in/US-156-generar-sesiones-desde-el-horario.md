# US-156 · Como administrador quiero que las sesiones de las próximas dos semanas se generen solas desde el horario para no crear cada clase a mano

- **Épica:** EP-21 · Clases, horario y check-in
- **Bounded context:** Classes (esquema `classes`), worker
- **Versión:** v0.4
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica de la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front; el resultado se ve en `Sesiones`)

## Historia

Como administrador
quiero que un job diario genere las sesiones de los próximos 14 días a partir de las franjas activas
para que el coach siempre tenga las clases listas para el check-in sin que nadie las cree a mano

## Contexto de dominio

- **Aggregate / entidades:** `ClassSession` (`slot_id`, `starts_at` TIMESTAMPTZ, `duration_min`, `capacity`, `coach_id`, `wod_id` nulo, `status`, `cancel_reason`), `ClassSlot`.
- **Reglas que aplica:** Q23 (las sesiones se generan con 14 días de antelación por el job diario; cambiar una franja solo afecta a las no generadas); Q28 (fechas civiles de Bogotá, `today_bogota()`); fechas en UTC en base.
- **Eventos que emite:** `SessionGenerated(session_id, slot_id, starts_at)`
- **Eventos que consume:** ninguno
- **Funciones puras:** `classes.planned_sessions(slots, from_date, to_date) -> list[PlannedSession]`

## Alcance

- **Backend:** modelo y migración `classes.class_sessions` (auditada); `classes.service.generate_sessions(today, days = 14)`; job `worker/jobs/generate_sessions.py` registrado en el worker a las 07:00 America/Bogota; comando `cli generate-sessions --days 14` para correrlo a demanda.
- **Front:** No aplica.

## Criterios de aceptación

1. Para cada franja activa y cada fecha entre `today_bogota()` y `today_bogota() + 13` cuyo día de la semana coincide, existe una `ClassSession` `scheduled` con `starts_at` = fecha + `start_time` en Bogotá convertido a UTC, y con `duration_min`, `capacity` y `coach_id` copiados de la franja.
2. Correr el job dos veces el mismo día (o dos días seguidos) no duplica ninguna sesión: restricción única `(slot_id, starts_at)`.
3. Una sesión ya generada no cambia si después se edita o desactiva su franja (Q23).
4. Una franja desactivada no genera sesiones nuevas.
5. No se regenera una sesión `cancelled` existente para la misma franja y hora.
6. Cada sesión creada emite `SessionGenerated` y queda auditada con `created_by` = `SYSTEM_USER_ID` (N-15).
7. `planned_sessions` es pura y se prueba con `FrozenClock` cruzando un cambio de mes.
8. El job registra en el log JSON cuántas sesiones creó, sin datos personales.

## Escenarios BDD

```gherkin
# language: es
Característica: Generación de sesiones desde el horario

  Escenario: El job genera dos semanas de clases
    Dado una franja activa los lunes a las 06:00 de 60 minutos y cupo 15
    Y hoy es miércoles 21 de octubre de 2026 en Bogotá
    Cuando corre el job de generación de sesiones
    Entonces existen sesiones el lunes 26 de octubre y el lunes 2 de noviembre a las 11:00 UTC
    Y cada una tiene cupo 15

  Escenario: El job corre dos veces el mismo día
    Dado que el job ya generó las sesiones de hoy
    Cuando el job corre otra vez
    Entonces el número de sesiones no cambia
```

## Endpoints

- Ninguno. Job `generate_sessions` y comando `cli generate-sessions`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** sí; tabla `class_sessions` con columnas comunes, FK a `class_slots`, índice único `(slot_id, starts_at)` donde `slot_id` no es nulo, índice por `starts_at`.
- **Trigger / restricciones:** `CHECK status IN ('scheduled','cancelled','done')`.
- **Funciones puras a probar:** `planned_sessions` (rango, días de la semana, conversión Bogotá a UTC, cambio de mes).
- **Pruebas:** pura con `FrozenClock`, service con base real (idempotencia), job del worker.
- **Archivos principales:** `api/src/app/modules/classes/service.py`, `api/src/app/worker/jobs/generate_sessions.py`, `api/src/app/cli.py`.

## Supuestos

- Supuesto: el worker usa `SYSTEM_USER_ID` para `created_by` (N-15).
- Supuesto: el paso de `scheduled` a `done` no se modela aquí; ver US-157.

## Dependencias

- US-155 · Horario semanal de franjas
- US-113 · Proceso worker programado

## INVEST

- **Independiente:** solo crea sesiones desde las franjas.
- **Negociable:** días de antelación y hora del job.
- **Valiosa:** elimina trabajo manual diario.
- **Estimable:** función pura, servicio y job.
- **Pequeña:** cabe en un sprint.
- **Testeable:** fechas e idempotencia verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras, de service con PostgreSQL real y del job en verde; cobertura de 80 % o más en lo tocado
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] Auditoría verificada para `class_sessions`
- [ ] Revisión de PR aprobada
