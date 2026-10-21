# US-063 · Como equipo quiero la tabla, la paginación por offset, la barra de filtros y los chips compartidos para que todas las listas paginen y filtren igual contra el API

- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context:** presentación (`web/src/shared/ui/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Patrón `P_Lista` (referencia; lo usan `Socios_Lista`, `Membresias`, `Pagos`, `Usuarios`, `Auditoria`)

## Historia

Como equipo
quiero `DataTable`, `Pagination`, `FilterBar` y `Chips`
para que cada lista del sistema muestre carga, vacío y error de la misma forma y traduzca páginas a `limit` y `offset` sin errores

## Contexto de dominio

- **Aggregate / entidades:** ninguno; consume `Page<T>` del contrato.
- **Reglas que aplica:** regla de datos 6 y S2 (`limit` de 1 a 200, por defecto 25, y `offset`; respuesta `{ items, total, limit, offset }`); `BRECHAS.md` D2 (el front traduce páginas a offset); estado de filtros en la URL (reglas web).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `pageToOffset(page, limit) -> number`, `offsetToPage(offset, limit) -> number`, `totalPages(total, limit) -> number`

## Alcance

- **Backend:** No aplica.
- **Front:** `DataTable` (columnas tipadas, orden por columna con `sort`, estados de carga con esqueleto, vacío con mensaje y acción opcional, error con reintento, fila clicable accesible); `Pagination` (tamaños 25, 50 y 100; anterior y siguiente; "Mostrando 26–50 de 312"); `FilterBar` (búsqueda `q` con espera de 300 ms, filtros por select y rango de fechas, botón limpiar); `Chips` (selección única o múltiple con conteo opcional); sincronización de `q`, filtros, `limit`, `offset` y `sort` con la URL.

## Criterios de aceptación

1. `pageToOffset(1, 25)` es 0 y `pageToOffset(3, 50)` es 100; `Pagination` envía siempre `limit` y `offset`, nunca `page` ni `page_size`.
2. `Pagination` solo ofrece tamaños 25, 50 y 100; un `limit` en la URL mayor que 200 o menor que 1 se corrige a 25 antes de pedir.
3. Cambiar un filtro o la búsqueda vuelve `offset` a 0.
4. `q`, filtros, `limit`, `offset` y `sort` viven en la URL; recargar la página conserva la vista y el botón atrás restaura la anterior.
5. `DataTable` muestra esqueleto durante la carga, mensaje de vacío cuando `total = 0` y mensaje de error con botón "Reintentar" cuando la petición falla; el error muestra el `message` del envelope.
6. La búsqueda espera 300 ms sin teclear antes de pedir y cancela la petición anterior.
7. `Chips` comunica el estado seleccionado con `aria-pressed` y texto, no solo con color.
8. Los encabezados ordenables son botones con `aria-sort`; la tabla es navegable con teclado.
9. Cobertura de 80 % o más en los cuatro componentes.

## Escenarios BDD

```gherkin
# language: es
Característica: Listas paginadas por offset

  Escenario: Ir a la página 3 con 50 por página
    Dado una lista con 312 elementos
    Y un tamaño de página de 50
    Cuando el usuario va a la página 3
    Entonces la petición lleva limit 50 y offset 100
    Y se muestra "Mostrando 101–150 de 312"

  Escenario: Cambiar la búsqueda reinicia el offset
    Dado que el usuario está en la página 4
    Cuando escribe "pérez" en la búsqueda
    Entonces la petición lleva q "pérez" y offset 0

  Escenario: Tamaño de página fuera de rango en la URL
    Dado una URL con limit 500
    Cuando se abre la lista
    Entonces la petición lleva limit 25

  Escenario: Error del API
    Dado que el API responde 500 con el mensaje "Error interno"
    Cuando se carga la lista
    Entonces la tabla muestra "Error interno" y un botón Reintentar

  Escenario: Lista vacía
    Dado que el API responde total 0
    Cuando se carga la lista
    Entonces la tabla muestra el mensaje de vacío configurado
```

## Endpoints

- Ninguno propio; consumen cualquier `GET` de lista con `limit` y `offset`.

## Pantalla

- Patrón `P_Lista` y `Socios_Movil` como referencia (en celular la tabla se convierte en tarjetas por fila). `// DESIGN-GAP:` si falta el estado de error en el diseño.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** `pageToOffset`, `offsetToPage`, `totalPages` con total 0, total exacto múltiplo del límite y última página parcial.
- **Pruebas:** Testing Library para estados, teclado y URL (con `MemoryRouter`); `axe`.
- **Archivos principales:** `web/src/shared/ui/DataTable.tsx`, `Pagination.tsx`, `FilterBar.tsx`, `Chips.tsx`, `web/src/shared/hooks/useListParams.ts`.

## Supuestos

- Ninguno.

## Dependencias

- US-010 · Componentes base Button, Field, StatusTag.
- US-019 · Contrato de paginación (forma de la respuesta).

## INVEST

- **Independiente:** se prueba con datos simulados.
- **Negociable:** el tiempo de espera de la búsqueda y la vista de tarjetas en celular.
- **Valiosa:** todas las listas del sistema la usan.
- **Estimable:** cuatro componentes y un hook.
- **Pequeña:** 4 a 5 días.
- **Testeable:** cálculo de offset y estados verificables.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales (si aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado (si cambia el contrato)
- [ ] Auditoría verificada para las tablas tocadas (si aplica)
- [ ] Revisión de PR aprobada
