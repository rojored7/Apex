# US-063 · Tabla, paginación, filtros y chips — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-06-layout-y-componentes-front/US-063-tabla-paginacion-filtros-y-chips.md`
- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context / módulo:** presentación (`web/src/shared/ui/`, `web/src/shared/hooks/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

La paginación por `limit` y `offset` (D2, aceptada como supuesto del gate), la forma `Page<T>` y el estado en la URL están definidos. Los cuatro componentes son genéricos y no dependen de reglas de negocio. El formato del parámetro `sort` no lo fija ningún contrato común, así que el hook recibe el serializador por configuración y no cambia ningún contrato.

## Resumen

Construye el kit de listas:

- `DataTable`: columnas tipadas, primera columna como enlace a la ficha, encabezados ordenables con `aria-sort`, estados de esqueleto, vacío y error con "Reintentar", y vista de tarjetas por debajo de 768 px.
- `Pagination`: 25, 50 o 100 por página, "Mostrando 26–50 de 312", anterior y siguiente.
- `FilterBar`: búsqueda `q` con espera de 300 ms, selects, rango de fechas y "Limpiar".
- `Chips`: selección única o múltiple, con conteo y `aria-pressed`.

Todo se apoya en el hook `useListParams`, que sincroniza `q`, filtros, `limit`, `offset` y `sort` con la URL, corrige `limit` fuera de rango y vuelve `offset` a 0 cuando cambia un filtro. Las funciones puras `pageToOffset`, `offsetToPage` y `totalPages` hacen la traducción de páginas.

## Correcciones aplicadas por DECISIONES.md

- `DESIGN.md` y `ROUTES.md` paginan con `page` y `page_size` → el front envía siempre `limit` y `offset` y nunca `page` ni `page_size`: supuesto del gate D2 / S2, tratado como aceptado.
- Estado `pending_payment` → los conjuntos de chips de estado de membresía que arman las features (US-071 en `Socios_Lista`, US-092 en `Membresias`) incluyen "Pendiente de pago", con borde y texto `--warning`. Por eso `Chips` debe admitir siete u ocho opciones con conteo sin desbordar en 320 px (se hace desplazable dentro de su caja) y su catálogo de pruebas incluye esa opción: corregido por DECISIONES Q3.

## Validación contra el dominio

- No hay aggregates; consume `Page<T>` (regla de datos 6).
- Límites: `limit` de 1 a 200 con 25 por defecto (regla de datos 6). `Pagination` solo ofrece 25, 50 y 100, y la URL corrige cualquier valor fuera de [1, 200] a 25 (criterio 2).
- Funciones puras: `pageToOffset(page, limit) -> number`, `offsetToPage(offset, limit) -> number` y `totalPages(total, limit) -> number`; además, `clampLimit(value) -> number` y `rangeLabel(offset, limit, total) -> string`.
- N-01: las listas nunca muestran datos cifrados ni enmascarados. `DataTable` no tiene un tipo de columna "enmascarada", y `MaskedValue` (US-066) es solo para fichas.

## Validación contra la arquitectura

- Capas de backend: no aplica.
- Estructura: `web/src/shared/ui/DataTable.tsx`, `Pagination.tsx`, `FilterBar.tsx` y `Chips.tsx`, más `web/src/shared/hooks/useListParams.ts` y `web/src/shared/lib/pagination.ts` (puras). Las features combinan `useListParams` con su hook de TanStack Query (`queryKey` con los parámetros; `signal` del query para cancelar la petición anterior, criterio 6).
- `listParams` de US-059 limita `limit` al enviar; `useListParams` lo corrige al leer la URL. Son dos defensas, y no se duplica la lógica: los dos usan `clampLimit`.
- Reglas de `DESIGN.md`: la tabla va dentro de una caja con `overflow-x: auto`, sin botones de editar o borrar en las filas, y la primera columna enlaza a la ficha.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- No aplica.

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T1 · `web/src/shared/lib/pagination.test.ts`: `pageToOffset(1,25) = 0`, `pageToOffset(3,50) = 100`; `offsetToPage(100,50) = 3`; `totalPages` con total 0 (1 página, vacía), un múltiplo exacto (300/50 = 6) y la última parcial (312/50 = 7); `clampLimit` con 500, 0, −1, "abc" y 50; `rangeLabel(100,50,312) = "Mostrando 101–150 de 312"`, con total 0 da "Sin resultados" — 1 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- No aplica (cubren estos archivos la regla de colores literales de US-068 y la de `fetch` de US-059).

### Front
- [ ] T2 · `web/src/shared/lib/pagination.ts`: las cinco funciones puras y las constantes `PAGE_SIZES = [25, 50, 100]` y `DEFAULT_LIMIT` (reutiliza la de `core/api/query.ts`) — 0.5 h
- [ ] T3 · `web/src/shared/hooks/useListParams.ts`: lee y escribe `q`, filtros declarados, `limit`, `offset` y `sort` en `useSearchParams` de React Router 7; `setFilter` y `setQuery` vuelven `offset` a 0; `limit` pasa por `clampLimit`; `q` se escribe con 300 ms de espera (`useDebouncedValue`); `serializeSort` y `parseSort` configurables (por defecto `campo` o `-campo`); devuelve `params` estables para `queryKey` — 2.5 h
- [ ] T4 · `web/src/shared/ui/DataTable.tsx`: `columns: Column<T>[]` con `key`, `header`, `render`, `sortable` y `align`; la primera columna como `<a href>` a `rowHref(row)`; encabezados ordenables como `<button>` dentro de `<th aria-sort>`; esqueleto con un número de filas igual a `limit` (máximo 10); vacío con `emptyMessage` y `emptyAction`; error con el `message` del `ApiError` como texto y botón "Reintentar" (`onRetry`); por debajo de 768 px, una lista de tarjetas por fila (patrón `Socios_Movil`); cifras con `tabular-nums` — 4 h
- [ ] T5 · `web/src/shared/ui/Pagination.tsx`: select de tamaño (25, 50, 100), `rangeLabel`, botones "Anterior" y "Siguiente" de 44 px, deshabilitados en los extremos; `aria-label="Paginación"` — 1.5 h
- [ ] T6 · `web/src/shared/ui/FilterBar.tsx`: buscador (`type="search"`, `label` visible u oculto accesible) más selects y rango de fechas (`from` y `to` como `AAAA-MM-DD` civiles) más ordenar, más "Limpiar" (que borra todo y vuelve `offset` a 0); en celular se apila — 2 h
- [ ] T7 · `web/src/shared/ui/Chips.tsx`: `mode: "single" | "multiple"`, opciones `{ value, label, count?, tone? }`; cada chip es un `<button aria-pressed>` con texto y conteo; el activo lleva fondo `--black` y un icono de verificación (no solo color); el contenedor se desplaza en horizontal dentro de su caja cuando no cabe — 2 h
- [ ] T8 · Testing Library: `DataTable.test.tsx` (esqueleto, vacío con `total = 0`, error "Error interno" con Reintentar que llama a `onRetry`, `aria-sort` al pulsar el encabezado, teclado), `Pagination.test.tsx` (página 3 con 50 por página produce `limit=50&offset=100` y el texto correcto), `FilterBar.test.tsx` (con temporizadores falsos, escribir "pérez" produce una sola petición a los 300 ms con `offset=0`), `Chips.test.tsx` (`aria-pressed`, múltiple, ocho opciones que incluyen "Pendiente de pago") — 3.5 h
- [ ] T9 · `web/src/shared/hooks/useListParams.test.tsx` con `MemoryRouter`: `limit=500` en la URL pide `limit=25`; cambiar un filtro desde la página 4 vuelve a `offset=0`; atrás restaura la vista anterior; recargar conserva `q`, filtros, `limit`, `offset` y `sort` — 1.5 h
- [ ] T10 · `axe` sobre `DataTable` (con datos, vacía y con error), `Pagination`, `FilterBar` y `Chips` en `web/src/shared/ui/list.a11y.test.tsx` — 1 h

### DevOps
- No aplica (los jobs de lint, test y capturas ya existen en US-009 y US-068).

### Seguridad
- [ ] T11 · Revisión: el `message` del error se muestra como texto (sin HTML); los parámetros de la URL se validan con un esquema Zod antes de enviarlos (no se pasan claves desconocidas al API) — 0.5 h

## Orden de ejecución
1. T1 (en rojo)
2. T2
3. T9 (en rojo)
4. T3
5. T8 (en rojo)
6. T4
7. T5
8. T6
9. T7
10. T10
11. T11

## Dependencias técnicas
- US-010 · Componentes base Button, Field y StatusTag.
- US-019 · Contrato de paginación del API: la forma `{ items, total, limit, offset }`.
- US-059 · Cliente API: `Page<T>`, `ApiError` y `listParams`.
- US-060 · Formato: `formatCop` y `formatDate` en las celdas que lo necesiten (lo usan las features).

## Endpoints
- Ninguno.

## Riesgos
- Front condicionado a D1. D2 sigue pendiente del gate: si se rechaza, `useListParams` cambiaría la serialización (T3 está aislado para eso).
- La convención de `sort` no está escrita en un contrato común (US-070 dice "asc o desc" sin formato) — mitigación: `serializeSort` es configurable por lista; se reporta para que el desglose de US-019 fije `campo` y `-campo`.
- Que una feature intente mostrar el teléfono enmascarado en la lista, como dice US-070 en su `MemberRow` — mitigación: `DataTable` no tiene un tipo de columna enmascarada; la contradicción con N-01 se reporta para el desglose de EP-07.
- La vista de tarjetas en celular puede duplicar el contenido para los lectores de pantalla — mitigación: se renderiza una sola de las dos vistas según `matchMedia`, nunca las dos ocultas con CSS.

## Estimación
- Backend: 0 h
- Front: 12.5 h
- Pruebas: 7 h
- DevOps / seguridad: 0.5 h
- **Total: 20 h**

## Definición de hecho
- [ ] Backend: no aplica (la historia no toca `api/`)
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/shared/ui/DataTable src/shared/ui/Pagination src/shared/ui/FilterBar src/shared/ui/Chips src/shared/hooks src/shared/lib`
- [ ] En la página de catálogo (US-068), una petición interceptada al ir a la página 3 con 50 por página lleva `limit=50&offset=100` y ningún `page` ni `page_size`
- [ ] Capturas del catálogo de listas en 320, 768, 1024 y 1440 px, en claro y oscuro, sin desborde horizontal de la página
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npx vitest run --coverage src/shared/ui src/shared/hooks src/shared/lib` con umbral 80 en los cuatro componentes
