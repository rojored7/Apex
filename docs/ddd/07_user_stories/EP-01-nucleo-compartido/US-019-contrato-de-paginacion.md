# US-019 · Como equipo quiero un contrato común de listas con `limit` y `offset` para que toda lista del API pagine igual y ninguna consulta devuelva miles de filas sin límite

- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context:** `core/` (`core/pagination.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero una dependencia `PageParams` (`limit` 1 a 200, por defecto 25, `offset` mayor o igual a 0) y un esquema genérico `Page[T]` con `{ items, total, limit, offset }`
para que todas las listas cumplan la regla de datos 6 con el mismo código y el front pagine con un solo componente

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** regla de datos 6 de `CLAUDE.md` (toda lista pagina, máximo 200, y acepta búsqueda); S2 / D2 de `DECISIONES.md` (`limit`/`offset`, no `page`/`page_size`); `05_service_design.md` sección 4.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `PageParams` como dependencia de FastAPI con `limit: int = Query(25, ge=1, le=200)` y `offset: int = Query(0, ge=0)`; `Page[T]` genérico de Pydantic v2; helper `paginate(session, select_stmt, params) -> Page` que ejecuta `count(*)` sobre la subconsulta y aplica `limit`/`offset` con orden estable (exige `ORDER BY`; si no viene, agrega `id`); parámetro común `q: str | None` (máximo 100 caracteres) documentado.
- **Front:** No aplica (lo consume US-063).

## Criterios de aceptación

1. Una lista sin parámetros devuelve `limit = 25` y `offset = 0`.
2. `limit=201` o `limit=0` devuelve 422 con `field = "limit"`; `offset=-1` devuelve 422 con `field = "offset"`.
3. La respuesta tiene exactamente las claves `items`, `total`, `limit`, `offset`; `total` es el número de filas que cumplen el filtro, no el de la página.
4. Dos páginas consecutivas sobre los mismos datos no repiten ni omiten filas (orden estable).
5. Una prueba de arquitectura recorre las rutas `GET` que devuelven listas y falla si alguna no usa `PageParams` (rutas con `response_model` `Page[...]`).
6. `q` con más de 100 caracteres devuelve 422.

## Escenarios BDD

```gherkin
# language: es
Característica: Listas paginadas con limit y offset

  Escenario: Valores por defecto
    Dado 30 registros en una lista de prueba
    Cuando pido la lista sin parámetros
    Entonces recibo 25 items
    Y "total" es 30, "limit" es 25 y "offset" es 0

  Escenario: Límite fuera de rango
    Dado una lista de prueba
    Cuando pido la lista con "limit=500"
    Entonces el código HTTP es 422
    Y "error.field" es "limit"

  Escenario: Segunda página sin repetidos
    Dado 30 registros
    Cuando pido "limit=25&offset=0" y luego "limit=25&offset=25"
    Entonces entre ambas páginas recibo los 30 registros sin repetir ninguno
```

## Endpoints

- Ninguno propio; aplica a todos los `GET` de listas.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** ninguna (helper probado con base real).
- **Pruebas:** service con base real (conteo y orden), router (422), arquitectura (rutas de lista con `PageParams`).
- **Archivos principales:** `api/src/app/core/pagination.py`.

## Supuestos

- Supuesto: `core/pagination.py` es un archivo nuevo de `core/` no listado en la estructura de `05_service_design.md`; si se prefiere, vive dentro de `core/db.py`.

## Dependencias

- US-017 · Envelope de errores (formato del 422).

## INVEST

- **Independiente:** no depende de módulos de negocio.
- **Negociable:** ubicación del helper.
- **Valiosa:** una sola regla de paginación para todo el sistema.
- **Estimable:** acotada.
- **Pequeña:** un día.
- **Testeable:** límites y conteo verificables.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas en verde
- [ ] Revisión de PR aprobada
