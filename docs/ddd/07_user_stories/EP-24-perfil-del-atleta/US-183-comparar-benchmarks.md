# US-183 · Como coach quiero ver todos los intentos de un socio en un mismo benchmark en orden cronológico para mostrarle cuánto ha mejorado

- **Épica:** EP-24 · Perfil del atleta
- **Bounded context:** Athletes (módulo `athletes`), lectura de Training por `results.service`
- **Versión:** v0.6
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Atleta_Perfil` (`/socios/:id/atleta`, subpestaña Benchmarks)

## Historia

Como coach
quiero elegir un benchmark y ver la lista y la gráfica de los intentos del socio
para mostrarle con datos su progreso entre un intento y otro

## Contexto de dominio

- **Aggregate / entidades:** `WodResult` (lectura vía `results.service`), `Wod` con `is_benchmark`, `PersonalRecord(kind = benchmark)`.
- **Reglas que aplica:** RN-15; solo resultados vigentes (`is_current = true`, Q18) y validados; el mejor lo decide `leaderboard_order` (Q20).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `athletes.benchmark_series(results, order_key) -> list[Attempt]` (marca cuál es el mejor y la diferencia con el anterior)

## Alcance

- **Backend:** `athletes.service.benchmarks(member_id, wod)` consulta `results.service.member_results(member_id, benchmark_title, only_current=True, status=validated)`; nunca lee `models` de results.
- **Front:** subpestaña Benchmarks con selector de benchmark, lista cronológica y gráfica de línea simple con tokens de color.

## Criterios de aceptación

1. `GET /api/v1/athletes/{member_id}/benchmarks?wod={wod_id}` con rol admin o coach devuelve los intentos del socio en ese benchmark (agrupado como en US-182) ordenados por fecha del WOD ascendente, cada uno con fecha, nivel, marca formateable y `is_best`.
2. Sin `wod`, devuelve la lista de benchmarks en los que el socio tiene al menos un intento, con el número de intentos y la mejor marca.
3. Solo se incluyen resultados `validated` con `is_current = true`; los `pending` y los reemplazados no aparecen.
4. Exactamente un intento por benchmark tiene `is_best = true`, según `leaderboard_order`.
5. Un `wod` que no es benchmark devuelve 422 con `field = wod`; inexistente, 404.
6. La lista de benchmarks (sin `wod`) pagina con `limit` (1 a 200, por defecto 25) y `offset`.
7. Rol `member` recibe 403 (su vista es `GET /me/benchmarks`, US-191); sin token, 401.
8. La respuesta no contiene campos cifrados del socio.

## Escenarios BDD

```gherkin
# language: es
Característica: Comparar benchmarks

  Escenario: Ver la evolución en Fran
    Dado que "Laura Gómez" tiene intentos validados en "Fran" de 4:40, 4:20 y 4:05
    Cuando el coach abre la subpestaña Benchmarks y elige "Fran"
    Entonces ve los tres intentos en orden cronológico
    Y el intento de 4:05 aparece marcado como mejor

  Escenario: WOD que no es benchmark
    Cuando se piden los benchmarks de "Laura Gómez" con un WOD que no es benchmark
    Entonces el sistema responde con error de validación en "wod"
```

## Endpoints

- `GET /api/v1/athletes/{member_id}/benchmarks?wod&limit&offset` — rol(es): admin, coach — salida: lista de benchmarks o serie de intentos — códigos: 200, 401, 403, 404, 422

## Pantalla

- `Atleta_Perfil`, subpestaña Benchmarks: selector, tabla y gráfica; el mejor se marca con texto "Mejor" además del color. Estados de carga, vacío ("Sin intentos en benchmarks") y error.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `benchmark_series` por tipo de score, con un solo intento y con empates.
- **Pruebas:** pura; service con base real; router; Vitest de la subpestaña.
- **Archivos principales:** `api/src/app/modules/athletes/service.py`, nueva consulta en `results/service.py`, `web/src/features/athletes/`.

## Supuestos

- Supuesto: la agrupación de benchmarks por título normalizado es la misma de US-182.

## Dependencias

- US-169 · Registrar resultados en tablet (resultados de benchmarks)
- US-180 · Registrar récords manuales (récords benchmark)

## INVEST

- **Independiente:** solo lectura.
- **Negociable:** forma de la gráfica.
- **Valiosa:** muestra progreso, motivo de renovación.
- **Estimable:** una consulta y una vista.
- **Pequeña:** pocos días.
- **Testeable:** orden y `is_best` exactos.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
