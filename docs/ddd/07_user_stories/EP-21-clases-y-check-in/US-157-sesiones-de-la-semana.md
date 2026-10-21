# US-157 · Como coach quiero ver las sesiones de la semana, crear una sesión extra y cancelar una sesión con motivo para organizar las clases reales del box

- **Épica:** EP-21 · Clases, horario y check-in
- **Bounded context:** Classes (esquema `classes`)
- **Versión:** v0.4
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica de la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Sesiones` (`/clases`)

## Historia

Como coach o administrador
quiero ver las sesiones de la semana con su ocupación, agregar una sesión extra y cancelar una sesión con motivo
para tener al día el calendario real de clases

## Contexto de dominio

- **Aggregate / entidades:** `ClassSession`.
- **Reglas que aplica:** no se hace check-in en una sesión `cancelled`; fechas en UTC en API; RN-15; Q25 (el grupo "Hoy" del menú enlaza a `Sesiones` filtrada a hoy).
- **Eventos que emite:** `SessionCancelled(session_id, reason)`
- **Eventos que consume:** ninguno
- **Funciones puras:** `classes.week_range(week, tz = "America/Bogota") -> (from_utc, to_utc)`

## Alcance

- **Backend:** `GET /api/v1/class-sessions?week=AAAA-Www` (o `from`/`to`), `POST /api/v1/class-sessions` (sesión extra, `slot_id` nulo), `GET /api/v1/class-sessions/{id}` (con asistentes y conteo), `POST /api/v1/class-sessions/{id}/cancel` con motivo.
- **Front:** pantalla `Sesiones` con vista semanal, ocupación "asistentes / cupo", botón de sesión extra (`SidePanel`) y modal de cancelar con motivo; enlace "Hoy" filtra al día actual.

## Criterios de aceptación

1. Todos los endpoints exigen rol `admin` o `coach`; socio recibe 403.
2. `GET /class-sessions?week=2026-W43` devuelve las sesiones cuyo `starts_at` cae en esa semana ISO de lunes a domingo en hora de Bogotá, con `attendance_count` y `capacity`; pagina con `limit`/`offset` (máximo 200) y responde `{ items, total, limit, offset }`.
3. Un `week` mal formado devuelve 422 con `field: "week"`.
4. `POST /class-sessions` crea una sesión `scheduled` con `slot_id` nulo; exige `starts_at` en ISO 8601 con zona, `duration_min` de 15 a 240, `coach_id` válido; `capacity` por defecto `settings.classes.default_capacity`; queda auditada.
5. `POST /class-sessions/{id}/cancel` exige `reason` no vacío (422 si falta); cancelar una sesión ya `cancelled` devuelve 409; emite `SessionCancelled` y queda auditada.
6. Cancelar una sesión con asistencias registradas no borra esas asistencias.
7. `GET /class-sessions/{id}` devuelve la sesión con la lista de asistentes (nombre y apellido, marca `flagged`), sin campos cifrados.
8. Las horas se muestran en Bogotá; el estado "Cancelada" se muestra con texto.

## Escenarios BDD

```gherkin
# language: es
Característica: Sesiones de la semana

  Escenario: El coach cancela la clase de las 19:00 por lluvia
    Dado que inicié sesión como coach
    Y existe la sesión del jueves a las 19:00
    Cuando la cancelo con el motivo "corte de luz en el sector"
    Entonces la sesión aparece como "Cancelada" en la semana
    Y queda auditada con el motivo

  Escenario: Cancelar sin motivo
    Dado que inicié sesión como coach
    Cuando intento cancelar una sesión sin motivo
    Entonces recibo 422 con field "reason"
```

## Endpoints

- `GET /api/v1/class-sessions` — rol(es): admin, coach — entrada: `week` o `from`/`to`, `status?`, `limit`, `offset` — salida: `{ items: SessionOut[], total, limit, offset }` — códigos: 200, 401, 403, 422
- `POST /api/v1/class-sessions` — rol(es): admin, coach — entrada: `{ starts_at, duration_min, capacity?, coach_id }` — códigos: 201, 401, 403, 422
- `GET /api/v1/class-sessions/{id}` — rol(es): admin, coach — códigos: 200, 401, 403, 404
- `POST /api/v1/class-sessions/{id}/cancel` — rol(es): admin, coach — entrada: `{ reason }` — códigos: 200, 401, 403, 404, 409, 422

## Pantalla

- `Sesiones` en `/clases`: vista semanal, sesión extra en `SidePanel`, cancelar con `ConfirmModal` con motivo. Estados de carga, vacío y error.

## Notas técnicas

- **Migración:** no (tabla de US-156).
- **Trigger / restricciones:** ninguna nueva.
- **Funciones puras a probar:** `week_range` (semana que cruza fin de año, conversión a UTC).
- **Pruebas:** puras, service con base real, router (rol, 422, 409), front.
- **Archivos principales:** `api/src/app/modules/classes/{service,router}.py`, `web/src/features/classes/pages/SessionsPage.tsx`.

## Supuestos

- Supuesto: el coach puede cancelar sesiones y crear sesiones extra (`ROUTES.md` le da acceso a Clases y solo marca Horario como solo admin).
- Supuesto: una sesión pasa a `done` cuando su hora de fin ya pasó, calculado al leer (no se persiste por job); el estado persistido solo distingue `scheduled` y `cancelled` en v0.4.

## Dependencias

- US-156 · Generar sesiones desde el horario
- US-063 · DataTable y paginación

## INVEST

- **Independiente:** gestión de sesiones sin check-in.
- **Negociable:** vista semanal o de lista.
- **Valiosa:** calendario real para el equipo.
- **Estimable:** cuatro endpoints y una pantalla.
- **Pequeña:** cabe en un sprint.
- **Testeable:** semana, cancelación y 409 verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `class_sessions`
- [ ] Revisión de PR aprobada
