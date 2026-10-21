# US-067 · Mapa de rutas — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-06-layout-y-componentes-front/US-067-mapa-de-rutas.md`
- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context / módulo:** presentación (`web/src/routes.tsx`, `web/src/config/`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Las rutas vienen de `ROUTES.md`. Lo que cambia está decidido: no hay `/hoy` (Q25), renovar es `/membresias/vender?socio=:id&renovar=1` (Q2) y la TV entra por `/tv?token=…` (N-44). El supuesto de la historia (`enabledFeatures` como lista versionada en código) solo afecta al front y no cambia ningún contrato. La guarda por rol la conecta US-053; aquí cada ruta solo declara sus `roles`.

## Resumen

Crea `web/src/routes.tsx` con React Router 7 y cuatro grupos:

- Acceso: `/login`, `/recuperar`, `/restablecer/:token` y `/tv` con `TvLayout`.
- Panel, con `PanelLayout`.
- Portal: `/mi/*` con `PortalLayout`.
- Tablet: `/clases/:id/checkin` y `/clases/:id/resultados` con `GymLayout`.

Cada ruta declara `feature`, `roles` y carga diferida (`lazy`). `web/src/config/features.ts` tiene la lista `enabledFeatures` de v0.1, y `isRouteEnabled` es una función pura. Una ruta cuya `feature` no está habilitada responde con la página 404 propia sin descargar su código. Una prueba de inventario compara las rutas declaradas contra un archivo de referencia derivado de `ROUTES.md`.

## Correcciones aplicadas por DECISIONES.md

- Grupo "Hoy" → no existe la ruta `/hoy`; navegar a ella da 404: aceptado por DECISIONES Q25 (la historia ya lo dice).
- Renovar → no hay ruta `/membresias/:id/renovar`; se usa `/membresias/vender?socio=:id&renovar=1`, y el API es `POST /members/{id}/memberships` con `renew: true`: corregido por DECISIONES Q2 (la historia ya usa la ruta correcta; el archivo de referencia no incluye ninguna variante con `renew`).
- TV → `/tv` recibe `?token=` una sola vez; la página de US-176 lo guarda en `localStorage` y limpia la query. La ruta no exige `token` como parámetro obligatorio y no lo registra: corregido por DECISIONES N-44 (la lógica es de US-176; aquí solo se declara la ruta sin parámetro obligatorio).

## Validación contra el dominio

- No hay aggregates. S4: cada pantalla entra cuando existe su API; `enabledFeatures` es la bandera.
- Permisos de `ROUTES.md`: el admin ve todo; el coach no ve Sistema ni Planes; el socio solo `/mi/*`. Cada ruta declara `roles`, y la guarda de US-053 los aplica.
- Función pura `isRouteEnabled(route, enabledFeatures) -> boolean`; una ruta sin `feature` (por ejemplo, `/login` o la 404) siempre está habilitada.

## Validación contra la arquitectura

- Capas de backend: no aplica.
- Estructura: `web/src/routes.tsx`, `web/src/config/features.ts`, `web/src/config/routes.reference.ts` y `web/src/pages/NotFound.tsx`.
- Layouts de US-061 y US-062. Las páginas viven en `features/<feature>/pages/` y se importan con `lazy(() => import(...))`, de modo que el bundle inicial solo contiene el shell, los layouts y Acceso (criterio 3).
- `enabledFeatures` de v0.1: `auth`, `dashboard`, `members`, `plans`, `memberships`, `payments`, `users`, `audit` y `settings`. Las de v0.2 en adelante (`notifications`, `crypto`, `classes`, `wods`, `results`, `athletes`, `tv` y `portal`) se declaran como rutas, pero quedan deshabilitadas.

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
- [ ] T1 · `web/src/config/features.test.ts`: `isRouteEnabled` con una ruta habilitada, una deshabilitada (`classes`) y una sin `feature` — 0.5 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T2 · `web/src/routes.inventory.test.ts`: la lista aplanada de rutas de `routes.tsx` (`path`, `feature`, `roles` y layout) coincide exactamente con `routes.reference.ts` (derivado a mano de `ROUTES.md`, con sus nombres de parámetro); no existe ninguna ruta `/hoy`; cada ruta de `/mi/*` usa `PortalLayout`, las de tablet `GymLayout`, `/tv` usa `TvLayout` y el resto del panel `PanelLayout` (criterios 1, 4 y 5) — 1 h

### Front
- [ ] T3 · `web/src/config/features.ts`: tipo `Feature` (unión de 17 features: las de `05_service_design.md` 5, con `system` partido en `users`, `audit`, `settings` y `crypto`, que se habilitan en versiones distintas), `ENABLED_FEATURES_V01` y `isRouteEnabled`. `web/src/config/routes.reference.ts`: la referencia de T2 con un comentario que apunta a `ROUTES.md` — 0.5 h
- [ ] T4 · `web/src/routes.tsx`: `createBrowserRouter` con los cuatro grupos; cada ruta tiene `handle: { feature, roles }` y `lazy`; un `loader` mínimo, o un elemento envoltorio, que da la 404 si `!isRouteEnabled` antes de resolver el `lazy` (así no se descarga el código); ranura `RequireRole` (la implementa US-053; aquí es un paso de control documentado); parámetros con los nombres de `ROUTES.md` (`/socios/:id`, `/socios/:id/editar`, `/socios/:id/atleta`, `/clases/:id/checkin`, `/restablecer/:token`) — 2 h
- [ ] T5 · `web/src/pages/NotFound.tsx`: "No encontrada", con enlace a `/` (o a `/mi` para el rol socio) y `h1` único — 0.5 h
- [ ] T6 · `web/src/routes.test.tsx` (`createMemoryRouter`): `/socios` carga la lista dentro de `PanelLayout`; `/clases` muestra "No encontrada" y el `import` de la página de sesiones no se ejecuta (espía sobre el módulo `lazy`); `/hoy` da 404 — 1 h

### DevOps
- [ ] T7 · `web/scripts/check-initial-bundle.mjs`: después de `vite build`, lee el manifest y falla si el chunk de entrada incluye módulos de `src/features/` (salvo `auth`); se agrega al job de build de CI — 1 h

### Seguridad
- [ ] T8 · Revisión: ocultar rutas no reemplaza el rol del API; `/tv` no registra la query en ningún log del front; `/restablecer/:token` no envía el token a terceros (sin `Referer`: `<meta name="referrer" content="no-referrer">` en esa ruta) — 0.5 h

## Orden de ejecución
1. T1 (en rojo)
2. T3
3. T2 (en rojo)
4. T6 (en rojo)
5. T4
6. T5
7. T7
8. T8

## Dependencias técnicas
- US-061 · Panel layout, TopBar y SideNav: `PanelLayout`, y `buildNavItems` usa `isRouteEnabled`.
- US-062 · Layouts de portal, gimnasio y TV: `PortalLayout`, `GymLayout` y `TvLayout`.
- US-053 · Guardas de ruta por rol: conecta `RequireRole` con `handle.roles`; no bloquea esta historia.

## Endpoints
- Ninguno.

## Riesgos
- Front condicionado a D1.
- `ROUTES.md` todavía usa `POST /memberships`, `POST /payments` y `page`/`page_size` en la descripción de los datos — mitigación: el inventario solo compara rutas del front, no rutas del API; los contratos del API salen de `types.ts` (US-059).
- La referencia manual puede desincronizarse de `ROUTES.md` — mitigación: T2 obliga a tocar los dos archivos juntos, y la revisión de PR compara contra `ROUTES.md`.
- `enabledFeatures` en código obliga a desplegar para habilitar una pantalla — mitigación: es lo que pide S4 (la pantalla entra con su API, en el mismo despliegue).

## Estimación
- Backend: 0 h
- Front: 3 h
- Pruebas: 2.5 h
- DevOps / seguridad: 1.5 h
- **Total: 7 h**

## Definición de hecho
- [ ] Backend: no aplica (la historia no toca `api/`)
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/routes src/config`
- [ ] `cd web && npm run build && node scripts/check-initial-bundle.mjs` en verde
- [ ] En el navegador, `/hoy` y `/clases` muestran "No encontrada" y la pestaña de red no descarga el chunk de sesiones
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npx vitest run --coverage src/config src/routes.tsx`
