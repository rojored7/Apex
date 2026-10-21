# US-182 · Como coach quiero que una mejor marca validada en un benchmark cree el récord del socio para seguir su progreso en los WODs de referencia

- **Épica:** EP-24 · Perfil del atleta
- **Bounded context:** Athletes (esquema `athletes`)
- **Versión:** v0.6
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (efecto visible en `Atleta_Perfil`, subpestaña Récords)

## Historia

Como coach
quiero que un resultado validado en un WOD benchmark que mejora la marca anterior del socio cree su récord
para que el atleta vea cuándo mejoró en Fran, Grace o Murph sin registrarlo a mano

## Contexto de dominio

- **Aggregate / entidades:** `PersonalRecord(kind = benchmark)`, lee `WodResult` y `Wod`.
- **Reglas que aplica:** Q20 (resultado validado en WOD `is_benchmark` que mejora la marca anterior crea récord derivado; "mejor" lo decide `leaderboard_order(score_type)`), RN-14.
- **Eventos que emite:** `PersonalRecordSet`
- **Eventos que consume:** `WodResultValidated`
- **Funciones puras:** `athletes.derive_benchmark_record(result, current_best, order_key) -> PersonalRecord | None`; usa `results.leaderboard_order(score_type)`

## Alcance

- **Backend:** ampliar `on_wod_result_validated` para WODs con `is_benchmark = true`; compara con el mejor récord benchmark vigente del socio para el mismo `wod_id`.
- **Front:** No aplica.

## Criterios de aceptación

1. En un benchmark `score_type = time`, un resultado validado de 245 s sobre un récord vigente de 260 s crea `PersonalRecord(kind = benchmark, source = derived, wod_id, result_id)`; uno de 270 s no crea nada.
2. En `rounds_reps`, `reps` y `load` gana el mayor según `leaderboard_order`; empate exacto no crea récord.
3. Un resultado `scaled` nunca supera a uno `rx` o `rx_plus` (el orden de `leaderboard_order` pone `scaled` después); si el vigente es `scaled` y el nuevo es `rx`, el nuevo es mejor.
4. Sin marca previa del socio en ese benchmark, el primer resultado validado crea el récord.
5. Idempotente por `result_id` (misma restricción única de US-181).
6. Se emite `PersonalRecordSet` cuando se crea el récord.
7. La comparación agrupa los WODs con `is_benchmark = true` por título normalizado (minúsculas, sin espacios ni puntos): "Fran" del 3 de marzo y "FRAN" del 10 de mayo son el mismo benchmark; el récord guarda el `wod_id` del intento que lo logró.

## Escenarios BDD

```gherkin
# language: es
Característica: Récord derivado de benchmark

  Escenario: Mejor tiempo en un benchmark
    Dado que "Laura Gómez" tiene un récord de 4:20 en el benchmark "Fran"
    Cuando el coach valida un resultado RX de "Laura Gómez" en "Fran" con 4:05
    Entonces el récord vigente de "Laura Gómez" en "Fran" es 4:05 con origen derivado

  Escenario: Tiempo peor que el récord
    Dado que "Laura Gómez" tiene un récord de 4:20 en el benchmark "Fran"
    Cuando el coach valida un resultado RX de "Laura Gómez" en "Fran" con 4:40
    Entonces el récord vigente sigue siendo 4:20
```

## Endpoints

- Ninguno (handler de evento).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no (reutiliza `personal_records` de US-180).
- **Trigger / restricciones:** ninguna nueva.
- **Funciones puras a probar:** `derive_benchmark_record` para cada `score_type`, empates, `scaled` contra `rx`.
- **Pruebas:** pura; service con base real con el evento.
- **Archivos principales:** `api/src/app/modules/athletes/service.py`.

## Supuestos

- Supuesto: un benchmark repetido en otra fecha es un `Wod` nuevo con otro `wod_id` (un WOD tiene `date`). El dominio no define una identidad de benchmark independiente del WOD; se compara por título normalizado de los WODs con `is_benchmark = true`, porque comparar solo por `wod_id` impediría ver progreso. Si el gate prefiere un catálogo de benchmarks, cambia el criterio 7 y US-183.

## Dependencias

- US-181 · Récord derivado por carga (handler y restricción de idempotencia)

## INVEST

- **Independiente:** extiende un handler existente.
- **Negociable:** identidad del benchmark.
- **Valiosa:** progreso en WODs de referencia.
- **Estimable:** una función pura y una rama del handler.
- **Pequeña:** cabe en pocos días.
- **Testeable:** casos por tipo de score.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada
