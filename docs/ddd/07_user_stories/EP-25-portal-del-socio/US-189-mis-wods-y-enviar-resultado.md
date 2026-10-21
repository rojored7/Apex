# US-189 · Como socio quiero ver mis resultados y enviar mi marca del WOD de hoy desde el celular para tener mi historial sin depender del coach

- **Épica:** EP-25 · Portal del socio
- **Bounded context:** Portal (módulo `portal`), Training (módulo `results`)
- **Versión:** v1.0
- **Actor:** socio
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Portal_WODs` (`/mi/wods`)

## Historia

Como socio
quiero ver el WOD de hoy, mi historial de resultados y enviar mi marca
para registrar mi entrenamiento aunque el coach no alcance a anotarlo en la tablet

## Contexto de dominio

- **Aggregate / entidades:** `WodResult`, `Wod`.
- **Reglas que aplica:** RN-11 (uno por WOD y socio; el enviado por el socio nace `pending`), Q18 (`is_current`, índice único parcial), Score por `score_type` (`validate_score`), RN-14 (nunca se borra), RN-15.
- **Eventos que emite:** `WodResultRecorded`
- **Eventos que consume:** ninguno
- **Funciones puras:** `results.validate_score(score_type, seconds, rounds, reps, load_kg)`

## Alcance

- **Backend:** `GET /me/results`, `GET /wods/today` habilitado para rol member, `POST /me/results` que llama a `results.service.submit(member_id, wod_id, score, level)` con `status = pending`, `recorded_by` = usuario socio.
- **Front:** `Portal_WODs` con el WOD de hoy, formulario según `score_type` y lista de mis resultados con estado "Por validar" o "Validado".

## Criterios de aceptación

1. `GET /api/v1/wods/today` responde 200 a admin, coach y member con el WOD del día (fecha de Bogotá) y sus movimientos, sin datos de otros socios; `null` si no hay WOD.
2. `POST /api/v1/me/results` con `{ wod_id, level, seconds?, rounds?, reps?, load_kg?, scaled_notes? }` crea un `WodResult` con `status = pending`, `is_current = true` y responde 201.
3. Los campos obligatorios dependen del `score_type` (`time` exige `seconds`, `rounds_reps` exige `rounds` y `reps`, `reps` exige `reps`, `load` exige `load_kg`); faltantes o negativos devuelven 422 con `field`.
4. Solo se puede enviar resultado del WOD de hoy o de los últimos 7 días; fuera de ese rango, 422 con `field = wod_id`.
5. Si el socio ya tiene un resultado vigente (`is_current`) en ese WOD, devuelve 409 (RN-11).
6. Un resultado `pending` no aparece en el leaderboard ni en la TV hasta ser validado (US-190).
7. `GET /api/v1/me/results?limit&offset` devuelve solo los resultados vigentes del socio, con WOD, fecha, marca, nivel y estado; paginado (`limit` 1 a 200, por defecto 25).
8. Ninguna ruta `/me/results` acepta `member_id`; anti IDOR probado (US-186).
9. Admin y coach reciben 403 en `/me/results`; sin token, 401.
10. `wod_results` sigue bajo el trigger de inmutabilidad; el socio no puede editar ni borrar su envío.

## Escenarios BDD

```gherkin
# language: es
Característica: Enviar resultado desde el portal

  Escenario: El socio envía su tiempo del WOD de hoy
    Dado que el WOD de hoy es "Fran" por tiempo
    Cuando "Laura" envía un tiempo de 4:30 en nivel RX
    Entonces su resultado aparece como "Por validar" en "Mis WODs"
    Y no aparece en el leaderboard del día

  Escenario: Resultado por tiempo sin segundos
    Cuando "Laura" envía un resultado de "Fran" sin tiempo
    Entonces el sistema rechaza el envío con error en "seconds"
```

## Endpoints

- `GET /api/v1/wods/today` — rol(es): admin, coach, member — códigos: 200, 401
- `GET /api/v1/me/results?limit&offset` — rol(es): member — códigos: 200, 401, 403, 422
- `POST /api/v1/me/results` — rol(es): member — entrada: score — salida: `WodResultOut` — códigos: 201, 401, 403, 404, 409, 422

## Pantalla

- `Portal_WODs`: tarjeta del WOD de hoy, formulario adaptado al tipo de score con controles de 44 px, lista de mis resultados; estados de carga, vacío y error.

## Notas técnicas

- **Migración:** no (tabla de US-169).
- **Trigger / restricciones:** índice único parcial (`wod_id`, `member_id`) `WHERE is_current` (Q18).
- **Funciones puras a probar:** `validate_score` (ya probada en US-169), regla de ventana de 7 días como función pura `results.can_submit(wod_date, today)`.
- **Pruebas:** pura; service; router con anti IDOR; Vitest del formulario por tipo; parte del E2E de EP-25.
- **Archivos principales:** `api/src/app/modules/results/service.py`, `portal/router.py`, `web/src/features/portal/pages/PortalWods.tsx`.

## Supuestos

- Supuesto: el socio puede enviar resultados del WOD de hoy y de los 7 días anteriores; el dominio no fija la ventana.
- Supuesto: el socio no necesita asistencia registrada en una sesión para enviar resultado (`session_id` opcional).

## Dependencias

- US-186 · Autorización propia en rutas me
- US-169 · Registrar resultados en tablet (modelo, trigger, validación)
- US-168 · GET /wods/today (agregado en consolidación)

## INVEST

- **Independiente:** agrega un origen nuevo de resultados.
- **Negociable:** ventana de envío.
- **Valiosa:** historial del atleta sin trabajo del coach.
- **Estimable:** tres rutas y una pantalla.
- **Pequeña:** cabe en un sprint.
- **Testeable:** pending, 409, 422 por score.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, anti IDOR, validación y envelope de error
- [ ] Front: pruebas de página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
