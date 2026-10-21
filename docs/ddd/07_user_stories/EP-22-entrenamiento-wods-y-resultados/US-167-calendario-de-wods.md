# US-167 · Como coach quiero ver el calendario de WODs por semana y buscar benchmarks para planear la programación

- **Épica:** EP-22 · Entrenamiento: movimientos, WODs y resultados
- **Bounded context:** Training (esquema `wods`, módulo `wods`)
- **Versión:** v0.5
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `WOD_Lista` (`/wods`)

## Historia

Como coach
quiero ver los WODs de una semana en calendario y buscar WODs por título o por benchmark
para planear la programación y repetir benchmarks en la fecha correcta

## Contexto de dominio

- **Aggregate / entidades:** `Wod` (lectura).
- **Reglas que aplica:** RN-15; regla de datos 6 (toda lista pagina y acepta búsqueda).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `wods.week_range(week_iso)` (devuelve lunes y domingo de la semana ISO)

## Alcance

- **Backend:** `wods.service.list(week | q, benchmark, limit, offset)`.
- **Front:** `WOD_Lista` con vista de semana (siete columnas, navegación anterior y siguiente) y vista de búsqueda con filtro "solo benchmarks"; cada tarjeta enlaza a `/wods/:id`.

## Criterios de aceptación

1. `GET /api/v1/wods?week=2026-W43` devuelve los WODs con `date` entre el lunes y el domingo de esa semana ISO, ordenados por fecha.
2. `GET /api/v1/wods?q=fran&benchmark=true` filtra por título (sin distinguir mayúsculas) y por `is_benchmark`, paginado con `limit` (1 a 200, por defecto 25) y `offset`, respuesta `{ items, total, limit, offset }`.
3. `week` mal formado devuelve 422 con `field = "week"`.
4. La semana se calcula sobre fechas civiles; "esta semana" en el front usa la fecha de Bogotá.
5. Solo admin y coach; `member` recibe 403 (el socio ve WODs por `/me` en EP-25).
6. Un día sin WOD se muestra vacío con acción "Crear WOD" que abre `/wods/nuevo?date=`.

## Escenarios BDD

```gherkin
# language: es
Característica: Calendario de WODs

  Escenario: Ver la semana actual
    Dado que hay WODs publicados el lunes, el miércoles y el viernes de esta semana
    Cuando abro el calendario de WODs
    Entonces veo los tres WODs en su día
    Y el martes aparece vacío con la opción de crear un WOD

  Escenario: Semana inválida
    Cuando pido los WODs de la semana "2026-43"
    Entonces el sistema responde que la semana no tiene el formato esperado
```

## Endpoints

- `GET /api/v1/wods` — rol(es): admin, coach — entrada: `week` o `q`, `benchmark`, `limit`, `offset` — salida: página de WODs (sin movimientos, con `movement_count`) — códigos: 200, 401, 403, 422

## Pantalla

- `WOD_Lista` en `/wods`: calendario semanal y búsqueda. Estados de carga, vacío y error.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `week_range("2026-W43")` devuelve 19 oct y 25 oct de 2026.
- **Pruebas:** service con base real (rango de semana, filtros), router, front.
- **Archivos principales:** `api/src/app/modules/wods/service.py`, `web/src/features/wods/pages/WodListPage.tsx`.

## Supuestos

- Supuesto: el parámetro `week` usa formato ISO 8601 `AAAA-Www`.

## Dependencias

- US-166 · Crear y editar WOD

## INVEST

- **Independiente:** solo lectura sobre WODs.
- **Negociable:** vista de mes posible después.
- **Valiosa:** el coach planea la semana de un vistazo.
- **Estimable:** una consulta y una pantalla.
- **Pequeña:** sin escrituras.
- **Testeable:** rangos y filtros verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
