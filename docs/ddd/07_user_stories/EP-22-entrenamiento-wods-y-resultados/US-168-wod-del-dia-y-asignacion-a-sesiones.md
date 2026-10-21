# US-168 · Como coach quiero que las sesiones del día hereden el WOD del día y poder asignar otro a una sesión para registrar los resultados contra el entrenamiento correcto

- **Épica:** EP-22 · Entrenamiento: movimientos, WODs y resultados
- **Bounded context:** Training (módulo `wods`), Conformist de Classes (`ClassSession.wod_id`)
- **Versión:** v0.5
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `WOD_Detalle` (`/wods/:id`) y `Sesiones` (`/clases`)

## Historia

Como coach
quiero consultar el WOD de hoy y que cada sesión del día lo herede, con la opción de asignar otro WOD a una sesión concreta
para que la tablet de resultados sepa contra qué WOD registrar las marcas

## Contexto de dominio

- **Aggregate / entidades:** `Wod` (lectura), `ClassSession.wod_id` (dueño Classes).
- **Reglas que aplica:** "un WOD principal por fecha; las sesiones de ese día lo heredan; se puede asignar otro a una sesión concreta" (`02_domain_model.md` 2.7); Q28: "hoy" es `today_bogota()`.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `wods.effective_wod_id(session_wod_id, day_wod_id)` devuelve el asignado o, si es nulo, el del día.

## Alcance

- **Backend:** `wods.service.today()` y `wods.service.for_date(date)`; `GET /wods/today`; asignación por `classes.service.assign_wod(session_id, wod_id, by)` (Training llama al service de Classes, nunca a sus models); `GET /class-sessions/{id}` devuelve `effective_wod_id`.
- **Front:** en `Sesiones`, selector "WOD de esta sesión" (por defecto "WOD del día"); en `WOD_Detalle`, encabezado con las sesiones que lo usan.

## Criterios de aceptación

1. `GET /api/v1/wods/today` devuelve el WOD cuya `date` es `today_bogota()`; si no hay, responde 200 con `null` (no 404) para que Inicio y la tablet muestren "sin WOD publicado".
2. Una sesión con `wod_id` nulo usa el WOD del día de su `starts_at` convertido a fecha de Bogotá.
3. `PATCH /api/v1/class-sessions/{id}` con `{ wod_id }` asigna otro WOD existente; `wod_id: null` vuelve a heredar.
4. Asignar un `wod_id` inexistente devuelve 422 con `field = "wod_id"`; asignar a una sesión `cancelled` devuelve 409.
5. El cambio de `wod_id` queda en auditoría de `classes.class_sessions`.
6. Solo admin y coach; `member` recibe 403 en la asignación. `GET /wods/today` para `member` se habilita en EP-25.
7. No hay joins entre esquemas `wods` y `classes`: la composición se hace en los services.

## Escenarios BDD

```gherkin
# language: es
Característica: WOD del día y asignación a sesiones

  Escenario: Las sesiones heredan el WOD del día
    Dado que hoy, en hora de Bogotá, es 21 oct 2026 y el WOD del día es "Fran"
    Y hay sesiones a las 6:00 y a las 18:00 sin WOD asignado
    Cuando abro el registro de resultados de la sesión de las 18:00
    Entonces el WOD de la sesión es "Fran"

  Escenario: Asignar un WOD inexistente
    Dado una sesión programada de hoy
    Cuando le asigno un WOD que no existe
    Entonces el sistema rechaza la asignación indicando el campo WOD
```

## Endpoints

- `GET /api/v1/wods/today` — rol(es): admin, coach — salida: WOD con movimientos o `null` — códigos: 200, 401, 403
- `PATCH /api/v1/class-sessions/{id}` — rol(es): admin, coach — entrada: `{ wod_id: uuid | null }` — salida: sesión con `effective_wod_id` — códigos: 200, 401, 403, 404, 409, 422

## Pantalla

- `Sesiones` (`/clases`): selector de WOD por sesión. `WOD_Detalle` (`/wods/:id`): sesiones que lo usan. `// DESIGN-GAP:` si el diseño no muestra el selector.

## Notas técnicas

- **Migración:** no (la columna `classes.class_sessions.wod_id` nace en US-156; solo se agrega la FK lógica, sin FK entre esquemas).
- **Trigger / restricciones:** ninguna FK cruzada; validación en service.
- **Funciones puras a probar:** `effective_wod_id(None, X) == X`; `effective_wod_id(Y, X) == Y`; conversión de `starts_at` 23:30 UTC a fecha de Bogotá del mismo día anterior.
- **Pruebas:** service con base real, router, prueba de arquitectura (sin imports de `classes.models` en `wods`).
- **Archivos principales:** `api/src/app/modules/wods/service.py`, `api/src/app/modules/classes/service.py`.

## Supuestos

- Supuesto: la asignación se expone como `PATCH /class-sessions/{id}` con `wod_id`; el contrato de EP-21 no la nombra explícitamente.

## Dependencias

- US-166 · Crear y editar WOD
- US-157 · Sesiones de la semana

## INVEST

- **Independiente:** pequeña extensión sobre sesiones y WODs existentes.
- **Negociable:** el selector puede vivir en Sesiones o en el detalle.
- **Valiosa:** sin ella los resultados no saben su WOD.
- **Estimable:** una consulta y un PATCH.
- **Pequeña:** sin tablas nuevas.
- **Testeable:** herencia y zona horaria verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `classes.class_sessions`
- [ ] Revisión de PR aprobada
