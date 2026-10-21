# US-180 · Como coach quiero registrar récords personales manuales de un socio para conservar las marcas logradas fuera del registro de resultados

- **Épica:** EP-24 · Perfil del atleta
- **Bounded context:** Athletes (esquema `athletes`)
- **Versión:** v0.6
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Atleta_Perfil` (`/socios/:id/atleta`, subpestañas RMs y Récords)

## Historia

Como coach
quiero registrar un RM de un movimiento o una marca de benchmark que el socio logró
para que su historial de récords esté completo aunque la marca no venga de un WOD registrado

## Contexto de dominio

- **Aggregate / entidades:** `PersonalRecord` (`member_id`, `kind` `rm` | `benchmark`, `movement_id` si `rm`, `wod_id` si `benchmark`, `value`, `achieved_at`, `source` `manual` | `derived`, `result_id`).
- **Reglas que aplica:** RN-12 (los manuales los registra coach o admin), RN-14 (los récords nunca se borran), RN-15; el vigente de un movimiento es el de mayor valor (criterio de éxito de EP-24).
- **Eventos que emite:** `PersonalRecordSet` cuando el récord manual queda como vigente
- **Eventos que consume:** ninguno
- **Funciones puras:** `athletes.current_record(records, kind, target) -> PersonalRecord | None`

## Alcance

- **Backend:** modelo `PersonalRecord`; `athletes.service.add_manual_record(member_id, data, by)`, `list_records(member_id, kind, limit, offset)`; valida movimiento activo por `wods.service.get_movement` y WOD benchmark por `wods.service.get`.
- **Front:** subpestañas RMs (lista por movimiento con el vigente destacado) y Récords (benchmarks) con formulario en `SidePanel`.

## Criterios de aceptación

1. `POST /api/v1/athletes/{member_id}/records` con rol admin o coach y `{ kind: "rm", movement_id, value, achieved_at }` crea un récord con `source = manual` y responde 201.
2. `kind = rm` exige `movement_id` de un movimiento existente con `unit = kg` y `value` en kg mayor que 0; sin `movement_id`, con movimiento inexistente o con unidad distinta de kg devuelve 422 con `field`.
3. `kind = benchmark` exige `wod_id` de un WOD con `is_benchmark = true` y un `value` que cumple `results.validate_score` del `score_type` del WOD; si no, 422.
4. `achieved_at` en ISO 8601 UTC; no se acepta una fecha futura (422).
5. `GET /api/v1/athletes/{member_id}/records?kind=rm|benchmark&limit&offset` pagina (`limit` 1 a 200, por defecto 25) y responde `{ items, total, limit, offset }`; cada ítem indica `is_current`.
6. El vigente por movimiento (o por WOD) es el récord de mayor valor según `current_record`; un manual y un derivado del mismo movimiento conviven y gana el de mayor valor.
7. Registrar un manual que supera al vigente emite `PersonalRecordSet`; uno menor o igual se guarda como histórico y no emite el evento.
8. No existe endpoint de borrado ni de edición; `personal_records` está auditada (`__audited__ = True`).
9. Rol `member` recibe 403; sin token, 401; socio inexistente o dado de baja, 404.

## Escenarios BDD

```gherkin
# language: es
Característica: Registrar récords manuales

  Antecedentes:
    Dado que el socio "Juan Ríos" tiene un RM vigente de 95 kg en "Back squat"

  Escenario: Récord manual que supera al vigente
    Cuando el coach registra para "Juan Ríos" un RM de 100 kg en "Back squat"
    Entonces el RM vigente de "Back squat" es 100 kg con origen manual
    Y el RM de 95 kg sigue en el historial
    Y se emite el evento de récord personal

  Escenario: RM sin movimiento
    Cuando el coach registra un RM de 100 kg sin indicar movimiento
    Entonces el sistema rechaza el registro con error en "movement_id"
```

## Endpoints

- `POST /api/v1/athletes/{member_id}/records` — rol(es): admin, coach — entrada: `{ kind, movement_id?, wod_id?, value, achieved_at }` — salida: `PersonalRecordOut` — códigos: 201, 401, 403, 404, 422
- `GET /api/v1/athletes/{member_id}/records?kind&limit&offset` — rol(es): admin, coach — salida: página — códigos: 200, 401, 403, 404, 422

## Pantalla

- `Atleta_Perfil`, subpestañas RMs y Récords: listas con el vigente marcado con texto "Vigente" (no solo color), botón "Registrar récord" en `SidePanel`. Estados de carga, vacío y error.

## Notas técnicas

- **Migración:** sí; tabla `athletes.personal_records` con `value_kg` (numérico) y columnas de score para benchmark (`seconds`, `rounds`, `reps`, `load_kg`), índice por (`member_id`, `kind`, `movement_id`) y (`member_id`, `kind`, `wod_id`); CHECK de coherencia `kind`/`movement_id`/`wod_id`.
- **Trigger / restricciones:** prohibido el `DELETE` desde la aplicación (RN-14).
- **Funciones puras a probar:** `current_record` con manual y derivado, empate (gana el más antiguo), lista vacía.
- **Pruebas:** pura; service con base real; router; Vitest de las subpestañas.
- **Archivos principales:** `api/src/app/modules/athletes/`, `web/src/features/athletes/`.

## Supuestos

- Supuesto: los RM se expresan en kg y solo se registran sobre movimientos con `unit = kg`.
- Supuesto: se permite registrar un RM manual menor o igual al vigente; queda como histórico y no cambia el vigente.
- Supuesto: en empate de valor, el vigente es el logrado primero (`achieved_at` más antiguo).

## Dependencias

- US-165 · Catálogo de movimientos (movimiento del RM)
- US-166 · Crear y editar WOD (WOD benchmark)
- US-073 · Ver ficha del socio (contenedor)

## INVEST

- **Independiente:** no depende de la derivación automática.
- **Negociable:** reglas de empate y unidades.
- **Valiosa:** historial completo del atleta.
- **Estimable:** un modelo, dos endpoints, dos subpestañas.
- **Pequeña:** cabe en un sprint.
- **Testeable:** vigente por mayor valor, 422 por coherencia.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada
