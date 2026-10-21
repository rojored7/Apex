# US-062 · Layouts de portal, gimnasio y TV — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-06-layout-y-componentes-front/US-062-layouts-portal-gym-y-tv.md`
- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context / módulo:** presentación (`web/src/layouts/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**NEEDS_REFINEMENT**

`GymLayout` y `TvLayout` están resueltos. `PortalLayout` choca con la fuente de verdad del front. La historia pide un menú inferior de seis destinos (Inicio, Pagos, WODs, Progreso, Datos y Avisos) con ancho pensado para 390 px. `DESIGN.md` ("Estructura de la app") y `Portal_Inicio.html` dibujan cinco pestañas (Inicio, Pagos, WODs, Progreso y Yo) y una columna de máximo 600 px centrada en escritorio. DECISIONES.md no lo resuelve, y la decisión cambia el comportamiento visible del portal.

## Resumen

Construye los tres marcos que faltan:

- `PortalLayout`: una columna, menú inferior fijo y relleno inferior igual a su alto; sigue el tema del teléfono.
- `GymLayout`: fuerza el tema oscuro con `data-theme="dark"`, controles de 56 px, tipografía ampliada y una barra mínima con el nombre de la sesión y "Salir"; no tiene `SideNav`.
- `TvLayout`: 1920 × 1080, tema oscuro, sin cursor, sin elementos enfocables y sin barras de desplazamiento.

Ningún layout hace peticiones. Se prueban con contenido de ejemplo en Vitest y en una página de muestra que no está enrutada en producción.

## Correcciones aplicadas por DECISIONES.md

Ninguna; la historia ya es coherente con DECISIONES.md. La TV recibe el token por cabecera `X-Device-Token` (N-44), pero eso es de US-176, porque `TvLayout` no hace peticiones (criterio 7).

## Validación contra el dominio

- No hay aggregates. Aplica las restricciones no funcionales de `01_product_discovery.md` 6: 44 px, 56 px en tablet, foco visible, contraste de 4,5:1 y nunca solo color.
- RN-09 (el check-in nunca bloquea) no es de este marco, pero `GymLayout` deja el espacio para la lista "ya llegaron" siempre visible (`DESIGN.md`, "Las pantallas de gimnasio").
- No tiene funciones puras.

## Validación contra la arquitectura

- Capas de backend: no aplica.
- `web/src/layouts/PortalLayout.tsx`, `GymLayout.tsx` y `TvLayout.tsx`. Los usa `routes.tsx` (US-067). Tokens `--control-gym`, `--text-button-gym` y `--text-tv-title`.
- Temas según `DESIGN.md`: el portal sigue `prefers-color-scheme` (sin conmutador); el gimnasio y la TV fuerzan el oscuro con `data-theme="dark"` en `<html>` mientras están montados, y al desmontar devuelven el valor anterior.

## Preguntas abiertas

- ¿El menú inferior del portal sigue a `DESIGN.md` y `Portal_Inicio.html` (cinco pestañas: Inicio `/mi`, Pagos `/mi/pagos`, WODs `/mi/wods`, Progreso `/mi/progreso` y Yo `/mi/datos`, desde donde se entra a `/mi/avisos`; columna de máximo 600 px centrada) en lugar de los seis destinos de la historia? Alternativa por defecto propuesta: sí, cinco pestañas como el diseño, y `PortalLayout` recibe la lista de destinos por configuración (`PORTAL_TABS`), para que pasar a seis sea un cambio de datos y no del componente.

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
- No aplica (la historia no tiene funciones puras).

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T1 · `web/src/layouts/layouts.no-fetch.test.ts`: ningún archivo de `src/layouts/` importa `core/api` ni `@tanstack/react-query` (criterio 7); análisis estático con `import.meta.glob` — 0.5 h

### Front
- [ ] T2 · `web/src/layouts/PortalLayout.tsx` y `web/src/layouts/portalTabs.ts`: `<main>` en una columna con `max-width` según la alternativa por defecto, `<nav aria-label="Menú del portal">` fijo abajo con `PORTAL_TABS` (icono Lucide de 20 px más texto, 44 px de alto como mínimo, `aria-current="page"`), relleno inferior igual a la altura del menú más `env(safe-area-inset-bottom)`; sigue el tema del sistema — 3 h
- [ ] T3 · `web/src/layouts/GymLayout.tsx`: `useForcedTheme("dark")` (efecto que fija `document.documentElement.dataset.theme` y lo restaura al desmontar), barra superior mínima con ranura `title` (nombre de la sesión) y botón "Salir" de 56 px, contenido con la variable `--control` sobrescrita a `var(--control-gym)` en el contenedor, para que `Button` y `Field` midan 56 px sin variantes nuevas; sin `SideNav` — 2.5 h
- [ ] T4 · `web/src/layouts/TvLayout.tsx`: contenedor de 1920 × 1080 con `overflow: hidden` y `cursor: none`, atributo `inert` en la raíz del contenido, tema oscuro forzado con `useForcedTheme`, y un escalado con `transform: scale()` para pantallas que no son exactamente 1080p — 2 h
- [ ] T5 · `web/src/dev/LayoutsPreview.tsx`: página de muestra con contenido de ejemplo para los tres layouts, enrutada solo cuando `import.meta.env.DEV` o en el build del catálogo de US-068 — 1 h
- [ ] T6 · Testing Library: `PortalLayout.test.tsx` (destinos visibles con texto, `aria-current`, el último elemento del contenido no queda bajo el menú porque el relleno es igual al alto), `GymLayout.test.tsx` (con `matchMedia` claro, `data-theme` queda en `dark`; al desmontar se restaura; los botones tienen `min-height` igual a `--control-gym`) y `TvLayout.test.tsx` (con `tabbable`, cero elementos enfocables; `cursor: none`) — 3 h
- [ ] T7 · `axe` en los tres layouts con contenido de ejemplo, en `web/src/layouts/layouts.a11y.test.tsx` (con `vitest-axe`) — 1 h
- [ ] T8 · Playwright `web/tests/e2e/layouts.spec.ts`: capturas de `PortalLayout` en 320 y 390 × 844, de `GymLayout` en 1024 × 768 y de `TvLayout` en 1920 × 1080, sin desborde horizontal ni barras de desplazamiento — 1.5 h

### DevOps
- [ ] T9 · Agregar `layouts.spec.ts` al job `web-e2e` y a los artefactos de capturas (job de US-068) — 0.5 h

### Seguridad
- No aplica (marcos sin datos ni peticiones).

## Orden de ejecución
1. Resolver la pregunta abierta
2. T1
3. T6 (en rojo)
4. T3
5. T4
6. T2
7. T5
8. T7
9. T8
10. T9

## Dependencias técnicas
- US-061 · Panel layout, TopBar y SideNav: patrón de layout, tokens y "Saltar al contenido".
- US-010 · Componentes base: `Button` y `Field` respetan `--control`.
- US-068 · Temas: comparte el mecanismo de `data-theme` y el job de capturas (se integra al cerrar las dos).

## Endpoints
- Ninguno.

## Riesgos
- Front condicionado a D1.
- Forzar `data-theme` en `<html>` desde un layout puede dejar el panel en oscuro si el desmontaje falla (por ejemplo, por un error de render) — mitigación: `useForcedTheme` restaura en la limpieza del efecto; T6 lo prueba, y el panel vuelve a fijar su tema al montar (US-068).
- `inert` no está en navegadores antiguos — mitigación: la TV es un navegador controlado por el gimnasio; además, `TvLayout` no recibe hijos interactivos y T6 verifica con `tabbable`.
- Si se elige la alternativa de seis destinos, el menú en 320 px queda apretado (53 px por destino) — mitigación: `PORTAL_TABS` es configurable y T8 mide en 320 px.

## Estimación
- Backend: 0 h
- Front: 8.5 h
- Pruebas: 6 h
- DevOps / seguridad: 0.5 h
- **Total: 15 h**

Queda por debajo de la referencia de 5 puntos (16 a 26 h) porque los tres marcos no tienen datos ni estado y reutilizan los tokens y el patrón de US-061.

## Definición de hecho
- [ ] Backend: no aplica (la historia no toca `api/`)
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/layouts`
- [ ] `cd web && npx playwright test tests/e2e/layouts.spec.ts` con capturas en 320, 390 × 844, 1024 × 768 y 1920 × 1080
- [ ] Con preferencia del sistema en claro, `document.documentElement.dataset.theme === "dark"` dentro de `GymLayout` y `TvLayout`
- [ ] Recorrido con Tab en `TvLayout` sin ningún elemento enfocado
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npx vitest run --coverage src/layouts`
