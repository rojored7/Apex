# US-169 · Como coach quiero registrar en la tablet las marcas de los socios que asistieron a la clase para sacar los resultados de la pizarra

- **Épica:** EP-22 · Entrenamiento: movimientos, WODs y resultados
- **Bounded context:** Training (esquema `results`, módulo `results`)
- **Versión:** v0.5
- **Actor:** administrador, coach
- **Tamaño:** 8
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Resultados_Registro` (`/clases/:id/resultados`)

## Historia

Como coach
quiero registrar al final de la clase, desde la lista de asistentes, el nivel y la marca de cada socio en el WOD de la sesión
para que cada atleta tenga historial y el box tenga leaderboard sin depender de la pizarra

## Contexto de dominio

- **Aggregate / entidades:** `WodResult` (raíz): `wod_id`, `member_id`, `session_id`, `level` (`rx` | `rx_plus` | `scaled`), `seconds`, `rounds`, `reps`, `load_kg`, `scaled_notes`, `status` (`validated` | `pending`), `recorded_by`, `validated_by`, `validated_at`, `supersedes_id`, `is_current`. Value object `Score`.
- **Reglas que aplica:** RN-11 (un resultado por WOD y socio; nace `validated` si lo registra coach o admin); RN-14 (los resultados nunca se borran); Q18 (`is_current` e índice único parcial `(wod_id, member_id) WHERE is_current`); `results.validate_score` según `score_type`; trigger de inmutabilidad que solo permite `UPDATE` de columnas de validación e `is_current`.
- **Eventos que emite:** `WodResultRecorded(member_id, wod_id, load_kg, movements)`, `WodResultValidated(result_id, member_id, wod_id)`
- **Eventos que consume:** ninguno
- **Funciones puras:** `results.validate_score(score_type, seconds, rounds, reps, load_kg) -> None | ScoreError`

## Alcance

- **Backend:** modelo `WodResult` auditado; `results.service.record(...)`; `GET /class-sessions/{id}/attendance` (lista de asistentes con nombre y si ya tienen resultado, sin campos cifrados); `PUT /results` registra si no existe resultado vigente del socio en ese WOD.
- **Front:** `Resultados_Registro` en `GymLayout` (oscuro, controles de 56 px): lista de asistentes de la sesión, por cada uno selector de nivel y los campos que pide el `score_type` del WOD efectivo; guardado por fila.

## Criterios de aceptación

1. `GET /api/v1/class-sessions/{id}/attendance` devuelve los asistentes de la sesión con `member_id`, `first_name`, `last_name` y `has_result`, sin ningún campo cifrado, paginado con `limit` (máximo 200) y `offset`.
2. `PUT /api/v1/results` con `{ wod_id, member_id, session_id?, level, seconds?, rounds?, reps?, load_kg?, scaled_notes? }` válido crea el resultado con `status = validated`, `is_current = true`, `recorded_by` y `validated_by` igual al usuario, `validated_at` en UTC, y responde 201.
3. `validate_score`: `time` sin `seconds`, `rounds_reps` sin `rounds` o sin `reps`, `reps` sin `reps`, `load` sin `load_kg` devuelven 422 con `field`; valores negativos devuelven 422.
4. Si ya existe un resultado `is_current` del mismo socio en el mismo WOD y la petición no trae `supersedes_id`, responde 409 con `existing_id` (RN-11); la corrección la cubre US-170.
5. El índice único parcial `(wod_id, member_id) WHERE is_current` impide en la base dos resultados vigentes aunque se salte el service.
6. Se emiten en la misma transacción `WodResultRecorded` y `WodResultValidated`; si un suscriptor falla, no queda el resultado.
7. El trigger de `results.wod_results` rechaza todo `DELETE` y todo `UPDATE` de columnas distintas de `status`, `validated_by`, `validated_at` e `is_current`.
8. Solo admin y coach (`require_role("admin", "coach")`); `member` recibe 403 (el socio envía por `/me/results`, EP-25).
9. Cada resultado deja auditoría (`__audited__ = True`).
10. En la tablet, registrar el resultado de un socio toma un toque para nivel y un campo numérico por dato del `score_type`; 15 socios se registran en menos de 5 minutos (prueba de uso con el coach).

## Escenarios BDD

```gherkin
# language: es
Característica: Registro de resultados en la tablet

  Antecedentes:
    Dado que inicié sesión como coach en la tablet
    Y la sesión de las 18:00 de hoy tiene el WOD "Fran" de tipo de marca "time"
    Y Ana Pérez y Juan Rojas hicieron check-in en esa sesión

  Escenario: Registrar la marca de un asistente
    Cuando registro para Ana Pérez nivel "rx" con 245 segundos
    Entonces Ana Pérez queda con resultado validado en "Fran"
    Y su fila muestra que ya tiene resultado
    Y se emiten los eventos WodResultRecorded y WodResultValidated

  Escenario: Falta el tiempo en un WOD por tiempo
    Cuando registro para Juan Rojas nivel "scaled" sin segundos
    Entonces el sistema rechaza el registro indicando que el tiempo es obligatorio
    Y Juan Rojas sigue sin resultado
```

## Endpoints

- `GET /api/v1/class-sessions/{id}/attendance` — rol(es): admin, coach — entrada: `limit`, `offset` — salida: página de asistentes — códigos: 200, 401, 403, 404
- `PUT /api/v1/results` — rol(es): admin, coach — entrada: ver criterio 2 — salida: resultado — códigos: 201, 401, 403, 404, 409, 422

## Pantalla

- `Resultados_Registro` en `/clases/:id/resultados` (tablet 1024 × 768, tema oscuro): lista de asistentes con formulario por fila, estado "registrado", mensajes de error por campo y estado "sin WOD publicado" cuando la sesión no tiene WOD efectivo.

## Notas técnicas

- **Migración:** sí; esquema `results` y tabla `results.wod_results` con columnas comunes, `supersedes_id` (FK a sí misma), `is_current` (bool, por defecto true), índice único parcial, CHECK de `level` y `status`.
- **Trigger / restricciones:** trigger `BEFORE UPDATE OR DELETE` que solo permite cambiar `status`, `validated_by`, `validated_at`, `is_current` (Q18).
- **Funciones puras a probar:** `validate_score` con los cuatro `score_type`, valores faltantes, ceros y negativos.
- **Pruebas:** puras, service con base real (unicidad, trigger, eventos en la transacción), router (403 member, 409, 422), arquitectura (la consulta de asistentes no lee columnas cifradas), front, E2E de registro de una clase.
- **Archivos principales:** `api/src/app/modules/results/*`, `api/src/app/modules/classes/service.py` (asistentes), `web/src/features/results/pages/ResultsEntryPage.tsx`.

## Supuestos

- Supuesto: un resultado registrado por coach o admin nace `validated` y, además de `WodResultRecorded`, emite `WodResultValidated` en la misma transacción, para que RN-12 (récord derivado, EP-24) aplique también a los resultados registrados en la tablet y no solo a los validados desde el portal.
- Supuesto: `PUT /results` registra solo socios con asistencia en la sesión cuando trae `session_id`; sin `session_id` (resultado fuera de clase) se permite a coach y admin.

## Dependencias

- US-168 · WOD del día y asignación a sesiones (WOD efectivo de la sesión)
- US-159 · Check-in en tablet (asistentes)
- US-062 · GymLayout

## INVEST

- **Independiente:** se apoya en sesiones y WODs ya existentes; la corrección va aparte (US-170).
- **Negociable:** orden de campos y atajos de la tablet ajustables.
- **Valiosa:** es el corazón del historial del atleta.
- **Estimable:** una tabla, un trigger, dos endpoints y una pantalla de tablet.
- **Pequeña:** 8 puntos, en el límite; la corrección y el leaderboard están fuera.
- **Testeable:** validación del Score, unicidad y trigger verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `results.wod_results`
- [ ] Revisión de PR aprobada
