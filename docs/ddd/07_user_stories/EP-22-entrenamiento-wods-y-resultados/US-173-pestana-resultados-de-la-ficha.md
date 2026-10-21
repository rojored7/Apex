# US-173 · Como coach quiero ver los resultados de un socio en su ficha para conversar con él sobre su progreso

- **Épica:** EP-22 · Entrenamiento: movimientos, WODs y resultados
- **Bounded context:** Training (módulo `results`)
- **Versión:** v0.5
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Socio_Ficha` (`/socios/:id`, pestaña Resultados)

## Historia

Como coach
quiero ver en la ficha del socio todos sus resultados vigentes, del más reciente al más antiguo
para mostrarle su historial y su evolución en los benchmarks

## Contexto de dominio

- **Aggregate / entidades:** `WodResult` (lectura), `Wod` (título, fecha, tipo de marca).
- **Reglas que aplica:** Q18 (solo vigentes), RN-15.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `results.service.list_by_member(member_id, benchmark?, limit, offset)`; `GET /members/{id}/results`.
- **Front:** pestaña Resultados de `Socio_Ficha` con `DataTable` (fecha del WOD, título, nivel, marca, estado) y filtro "solo benchmarks".

## Criterios de aceptación

1. `GET /api/v1/members/{id}/results` devuelve los resultados `is_current` del socio ordenados por fecha del WOD descendente, paginados con `limit` (1 a 200, por defecto 25) y `offset`, respuesta `{ items, total, limit, offset }`.
2. `benchmark=true` filtra a WODs `is_benchmark`.
3. Un socio dado de baja (`deleted_at`) conserva sus resultados visibles para admin.
4. Un socio inexistente devuelve 404.
5. Solo admin y coach; `member` recibe 403 (el socio ve los suyos por `/me/results`).
6. Los resultados `pending` (enviados por el socio, desde EP-25) aparecen marcados "por validar".

## Escenarios BDD

```gherkin
# language: es
Característica: Resultados en la ficha del socio

  Escenario: Ver el historial del socio
    Dado que Ana Pérez tiene 8 resultados vigentes y 1 reemplazado
    Cuando abro la pestaña Resultados de su ficha
    Entonces veo 8 resultados ordenados del más reciente al más antiguo

  Escenario: Socio inexistente
    Cuando pido los resultados de un socio que no existe
    Entonces el sistema responde que el socio no fue encontrado
```

## Endpoints

- `GET /api/v1/members/{id}/results` — rol(es): admin, coach — entrada: `benchmark?`, `limit`, `offset` — salida: página de resultados — códigos: 200, 401, 403, 404, 422

## Pantalla

- `Socio_Ficha`, pestaña Resultados: tabla con estados de carga, vacío ("Todavía no tiene resultados") y error.

## Notas técnicas

- **Migración:** no; índice `results.wod_results (member_id) WHERE is_current`.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service con base real, router, front.
- **Archivos principales:** `api/src/app/modules/results/router.py`, `web/src/features/members/components/ResultsTab.tsx`.

## Supuestos

- Supuesto: la ruta vive en el router de `results` aunque cuelgue de `/members/{id}`, para no hacer que Members dependa de Training.

## Dependencias

- US-169 · Registrar resultados en tablet
- US-073 · Ver ficha del socio

## INVEST

- **Independiente:** lectura sobre datos existentes.
- **Negociable:** columnas y filtro.
- **Valiosa:** conversación de progreso con el socio.
- **Estimable:** un endpoint y una pestaña.
- **Pequeña:** 2 puntos.
- **Testeable:** orden y filtros verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
