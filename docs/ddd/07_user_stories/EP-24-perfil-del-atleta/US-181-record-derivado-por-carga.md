# US-181 · Como coach quiero que un resultado validado con más carga que el RM vigente cree el récord automáticamente para no tener que registrarlo a mano

- **Épica:** EP-24 · Perfil del atleta
- **Bounded context:** Athletes (esquema `athletes`), consume eventos de Training
- **Versión:** v0.6
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front; el efecto se ve en `Atleta_Perfil`, subpestaña RMs)

## Historia

Como coach
quiero que cuando valide un resultado de carga que supera el RM del socio en el movimiento principal se cree su récord
para que el atleta vea sus récords actualizados el mismo día sin trabajo extra

## Contexto de dominio

- **Aggregate / entidades:** `PersonalRecord` (derivado), lee `WodResult`, `Wod` y `WodMovement`.
- **Reglas que aplica:** RN-12 (resultado validado con `load_kg` mayor al RM vigente del movimiento crea récord derivado), Q19 (solo el movimiento con `is_primary` y solo si `score_type = load`; WOD sin principal no deriva), RN-14 (nunca se borra).
- **Eventos que emite:** `PersonalRecordSet`
- **Eventos que consume:** `WodResultValidated`
- **Funciones puras:** `athletes.derive_record(result, current_rm) -> PersonalRecord | None`

## Alcance

- **Backend:** handler `on_wod_result_validated` registrado en `athletes/service.py`; obtiene el movimiento principal por `wods.service.primary_movement(wod_id)`; corre en la misma transacción del evento (si falla, se revierte la validación).
- **Front:** No aplica (la subpestaña RMs de US-184 muestra el origen "Derivado").

## Criterios de aceptación

1. Un `WodResultValidated` de un WOD `score_type = load` con movimiento principal y `load_kg = 100` sobre un RM vigente de 95 kg crea un `PersonalRecord(kind = rm, source = derived, result_id, value = 100, achieved_at = fecha del WOD)`.
2. Con `load_kg = 90` sobre 95 kg no se crea nada; con `load_kg = 95` (igual) tampoco.
3. Si el socio no tiene RM en ese movimiento, el primer resultado validado con carga mayor que 0 crea el récord derivado.
4. Un WOD sin movimiento principal o con `score_type` distinto de `load` no deriva récord de carga.
5. Un resultado con nivel `scaled` no deriva RM.
6. El handler es idempotente: un mismo `result_id` nunca genera dos récords (restricción única sobre `result_id` donde no es nulo).
7. Cuando se crea el récord se emite `PersonalRecordSet(member_id, record_id, kind)`.
8. Un error en el handler revierte la validación completa (misma transacción, `02_domain_model.md` sección 3).
9. El récord derivado queda auditado como `insert` con el usuario que validó.

## Escenarios BDD

```gherkin
# language: es
Característica: Récord derivado por carga

  Antecedentes:
    Dado que el WOD del día es de tipo carga con "Deadlift" como movimiento principal
    Y que "Juan Ríos" tiene un RM vigente de 95 kg en "Deadlift"

  Escenario: Resultado validado que supera el RM
    Cuando el coach valida un resultado RX de "Juan Ríos" con 100 kg
    Entonces "Juan Ríos" tiene un RM vigente de 100 kg en "Deadlift" con origen derivado
    Y el récord apunta al resultado validado

  Escenario: Resultado validado por debajo del RM
    Cuando el coach valida un resultado RX de "Juan Ríos" con 90 kg
    Entonces el RM vigente de "Juan Ríos" sigue siendo 95 kg
    Y no se crea ningún récord nuevo
```

## Endpoints

- Ninguno (handler de evento).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** sí; índice único parcial `personal_records(result_id) WHERE result_id IS NOT NULL`.
- **Trigger / restricciones:** sin `DELETE`.
- **Funciones puras a probar:** `derive_record` con mayor, igual, menor, sin RM previo, `scaled`, WOD sin principal, `score_type` distinto de `load`.
- **Pruebas:** pura; service con base real emitiendo el evento; prueba de reversión si el handler falla; prueba de idempotencia.
- **Archivos principales:** `api/src/app/modules/athletes/service.py`; consulta nueva `wods.service.primary_movement`.

## Supuestos

- Supuesto: los resultados que nacen `validated` al registrarlos coach o admin (US-169) también emiten `WodResultValidated`; si no, solo derivarían los validados desde el portal.
- Supuesto: un resultado `scaled` no deriva RM porque la carga no es la RX del movimiento.
- Supuesto: corregir un resultado (US-170) que ya derivó récord no elimina el récord (RN-14); el nuevo resultado puede derivar otro.

## Dependencias

- US-180 · Registrar récords manuales (tabla y vigente)
- US-169 · Registrar resultados en tablet (emisión de `WodResultValidated`)

## INVEST

- **Independiente:** handler aislado sobre un evento existente.
- **Negociable:** si `scaled` deriva o no.
- **Valiosa:** récords sin trabajo manual.
- **Estimable:** un handler y una función pura.
- **Pequeña:** cabe en un sprint.
- **Testeable:** casos numéricos exactos de RN-12.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada

## Correcciones del Sprint 9 (T-DOC, 2026-11-15)

- Evento nuevo (S9-D7): `results` emite `WodResultSuperseded(old_result_id, new_result_id, member_id, wod_id)` al corregir, antes de `WodResultRecorded` y `WodResultValidated`. Ningún evento lleva la marca: el handler la lee con `results.service.get_mark`.
- Tres handlers (S9-D7): validar, corregir y anular un resultado; todos corren en la transacción del emisor y sin candados propios (el emisor ya tiene `lock_member`).
- CA8 corregido (S9-D30, S9-D42): invalidar falla cerrado (si falla, se revierte la corrección o la anulación); derivar y reponer fallan en blando dentro de un savepoint (se omite, se alerta sin ids y `derive-records` lo repara); «base ocupada» sale como 503 `busy` y el resultado no se confirma.
- Invalidación auditada (S9-D42): `_invalidate` escribe por ORM (cuatro columnas) para que cada fila deje su `update` en `audit_log` con el actor del contexto.
- Reponer el mejor (S9-D11, S9-D30): tras invalidar se repone el mejor que quede, solo si se invalidó algo, con filtro en SQL y tope `RESTORE_MAX_MARKS = 200` (si se alcanza: alerta `athletes_restore_capped` con el conteo y no repone).
- Idempotencia (S9-D8): índice único parcial `(result_id, kind)`; un 23505 es un no-op, nunca un 500. La anulación de un resultado también invalida.
- Resultados anteriores a v0.6 (S9-D21): comando `derive-records [--as <email>] [--dry-run]`, idempotente, auditado, paso de despliegue de v0.6.
