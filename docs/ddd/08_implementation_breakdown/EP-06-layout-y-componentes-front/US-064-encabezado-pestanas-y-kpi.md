# US-064 · Encabezado, pestañas y KPI — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-06-layout-y-componentes-front/US-064-encabezado-pestanas-y-kpi.md`
- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context / módulo:** presentación (`web/src/shared/ui/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Son tres componentes de presentación con criterios exactos: patrón WAI-ARIA de pestañas, KPI con `null` que muestra "Disponible en v0.x" y un único `h1`. No tienen supuestos ni dependencias de contrato salvo `formatCop` (US-060). Encajan con `DESIGN.md` (título en Michroma con el total a la derecha, migas en fichas y formularios, Historial como última pestaña de las fichas).

## Resumen

Construye:

- `PageHeader`: migas opcionales, `h1` en `--font-display`, total opcional junto al título, y una zona de hasta tres acciones más el menú "Más acciones".
- `Tabs`: `tablist`, `tab` y `tabpanel`, con flechas, Inicio y Fin; la pestaña activa vive en la URL (`?tab=` o segmento) y las pestañas no disponibles anuncian su versión.
- `KpiCard`: etiqueta, valor, variación y enlace opcionales; estados de carga, valor, `null` ("Disponible en v0.x", sin cero engañoso) y error; variante "pide atención" con `--blue-tint`.

## Correcciones aplicadas por DECISIONES.md

Ninguna; la historia ya es coherente con DECISIONES.md. El contrato del tablero con campos futuros en `null` (EP-12, US-109) es el que consume `KpiCard`.

## Validación contra el dominio

- No hay aggregates.
- RN-01: un `KpiCard` de dinero formatea con `formatCop`; uno de conteo usa el separador de miles de `format.ts` (`formatCount`, que se agrega a US-060 si falta, como función pura).
- EP-12: los campos del tablero que llegan `null` antes de su versión (por avisar en v0.2, asistencia en v0.4, sesiones de hoy en v0.4) se muestran como "Disponible en v0.x" y nunca como 0.

## Validación contra la arquitectura

- Capas de backend: no aplica.
- `web/src/shared/ui/PageHeader.tsx`, `Tabs.tsx` y `KpiCard.tsx`. Los usan `Socio_Ficha` (US-073), `Config` (US-055) e `Inicio` (US-109).
- `Tabs` usa `useSearchParams` o un parámetro de ruta (prop `urlMode: "query" | "segment"`), sin estado propio duplicado (las reglas web dicen que la URL es el estado).
- Tokens: `--text-screen-title`, `--text-kpi`, `--blue-tint`, `--apex-blue` (línea de la pestaña activa) y `--muted`.

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
- No aplica (la historia no declara funciones puras; `formatCount`, si se agrega, se prueba en `format.test.ts` de US-060).

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- No aplica (la regla de colores literales de US-068 cubre estos archivos).

### Front
- [ ] T1 · `web/src/shared/ui/PageHeader.tsx`: `breadcrumbs?` (`<nav aria-label="Migas">` con `<ol>`), `title` en un único `<h1>` con `--text-screen-title` y mayúsculas, `total?` con `tabular-nums`, `actions` (máximo tres `Button`; si llegan más, las sobrantes pasan al menú "Más acciones" accesible); las acciones van después del título en el orden de tabulación — 1.5 h
- [ ] T2 · `web/src/shared/ui/Tabs.tsx`: `tabs: { id, label, disabledUntil?: "v0.x" }[]`; `role="tablist"`, `role="tab"` con `aria-selected`, `aria-controls` y `tabIndex` móvil, y `role="tabpanel"` con `aria-labelledby`; flechas izquierda y derecha (saltan las deshabilitadas), Inicio y Fin; pestaña activa en `?tab=` o en el segmento según `urlMode`; una pestaña deshabilitada lleva `aria-disabled="true"` y el texto visible "Disponible en v0.x", y no se activa; línea inferior `--apex-blue` en la activa — 2.5 h
- [ ] T3 · `web/src/shared/ui/KpiCard.tsx`: props `label`, `value: number | null | undefined`, `kind: "money" | "count"`, `availableIn?`, `note?`, `delta?`, `href?`, `attention?`, `isLoading?`, `error?`; con `isLoading` muestra un esqueleto; con `null` muestra "Disponible en {availableIn}" sin número; con error muestra "No se pudo cargar" y un reintento opcional; con `href`, toda la tarjeta es un único `<a>` cuyo nombre accesible combina etiqueta y valor ("Por vencer: 12"); `attention` usa fondo `--blue-tint` y borde `--apex-blue` — 2 h
- [ ] T4 · Testing Library: `Tabs.test.tsx` (flecha derecha desde Membresías activa Pagos y la URL lo refleja; recargar conserva la pestaña; una pestaña no disponible no cambia la activa; Inicio y Fin), `KpiCard.test.tsx` (con `null` y "v0.2" muestra "Disponible en v0.2" y no muestra "0"; dinero `$ 120.000`; conteo `1.250`; nombre accesible del enlace) y `PageHeader.test.tsx` (un solo `h1`; cuatro acciones dejan tres visibles más el menú; orden de tabulación) — 3.5 h
- [ ] T5 · `axe` sobre los tres componentes en sus estados, en `web/src/shared/ui/header-tabs-kpi.a11y.test.tsx` — 0.5 h

### DevOps
- No aplica (las capturas del catálogo las genera el job de US-068).

### Seguridad
- No aplica (componentes de presentación sin datos sensibles).

## Orden de ejecución
1. T4 (en rojo)
2. T2
3. T3
4. T1
5. T5

## Dependencias técnicas
- US-010 · Componentes base: `Button` dentro de `PageHeader`.
- US-060 · Formato de dinero y fechas: `formatCop` y el separador de miles.

## Endpoints
- Ninguno.

## Riesgos
- Front condicionado a D1.
- `Config` (US-055) usa pestañas aunque el diseño muestra secciones en una sola página — mitigación: `Tabs` sirve igual; la decisión visual se anota como `DESIGN-GAP` en US-055.
- Pestañas en el segmento de la ruta y en la query a la vez producen dos fuentes de verdad — mitigación: cada uso elige un solo `urlMode`.

## Estimación
- Backend: 0 h
- Front: 6 h
- Pruebas: 4 h
- DevOps / seguridad: 0 h
- **Total: 10 h**

## Definición de hecho
- [ ] Backend: no aplica (la historia no toca `api/`)
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/shared/ui/PageHeader src/shared/ui/Tabs src/shared/ui/KpiCard`
- [ ] En el catálogo (US-068), un `KpiCard` con `null` se ve "Disponible en v0.2" en claro y oscuro, en las capturas de los cuatro anchos
- [ ] `axe` sin violaciones de rol, nombre accesible ni foco en los tres componentes
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npx vitest run --coverage src/shared/ui`
