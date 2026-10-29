# US-109 · KPIs de membresías e ingresos — desglose técnico

> **Corregido en S4A-W0-1** (`docs/ddd/blueprints/sprint-04a-plan.md`, sección 1 y enmiendas E1 a E10; registro en `docs/ddd/DECISIONES.md`, "Sprint 4A"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - La página es `web/src/features/dashboard/pages/InicioPage.tsx` (con `InicioPage.test.tsx`), que ya existe y deja de ser mínima en S4A-F3; no existe `HomePage.tsx` (S4A-D41).
> - El cuadre con datos de demostración (US-111) se difiere al Sprint 4B; las pruebas de 4A usan fábricas (S4A-D29).
> - `home.spec.ts` (stack) usa el admin del seed (`E2E_ADMIN_*`), `crearCoach`, `exigirStackLocal` y `borrarUsuario` de `web/tests/e2e/helpers/stack.ts`, sin depender del orden de `recent` (S4A-D59).
> - `GET /dashboard` puede responder 429 (`staff-read`): la página lo trata como error con "Reintentar" (S4A-D45).

- **Historia:** `docs/ddd/07_user_stories/EP-12-tablero-de-inicio/US-109-kpis-de-membresias-e-ingresos.md`
- **Épica:** EP-12 · Tablero de inicio
- **Bounded context / módulo:** Dashboard, presentación (`web/src/features/dashboard/`); sin cambios en `api/src/app/modules/dashboard/`
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Es una historia solo de front sobre el contrato `DashboardOut` de US-108. Los destinos de los enlaces existen en US-071 (`membership_status`) y US-098 (`from`/`to`), y el estado `pending_payment` es visible por Q3. Nada cambia contrato ni esquema.

## Resumen

Se construye la página `Inicio` (`/`) dentro de `PanelLayout`: una grilla con cuatro `KpiCard` de v0.1 (Al día, Por vencer, Vencidos, Ingresos del mes), una línea secundaria "N pendientes de pago" bajo "Al día" y cuatro tarjetas de versiones futuras en estado vacío cuando su campo viene `null`. Cada KPI enlaza a la lista filtrada. La página tiene estados de carga, error con "Reintentar" y vacío, y se mide el tiempo desde el login hasta que la página es usable.

## Correcciones aplicadas por DECISIONES.md

- La historia supone mostrar `pending_payment` como línea secundaria → se mantiene; el chip y la etiqueta usan el token `--warning` como "por vencer": corregido por DECISIONES Q3 (estilo de la etiqueta).
- La historia supone el umbral de "por vencer" de 7 días → el número lo calcula el API con `expiring_days` de Settings; el front no escribe "7 días" en ningún texto: corregido por DECISIONES Q11.
- El mes de ingresos y el rango de `/pagos` → mes y límites de Bogotá: aceptado por DECISIONES N-27 y Q28.

## Validación contra el dominio

- No hay aggregate; la página presenta `DashboardOut`.
- RN-01: el ingreso se formatea con `formatCop` de `core/i18n/format.ts` (US-060) como `$ 1.250.000`; el valor llega entero.
- RN-06 con Q11: los conteos vienen resueltos del API (N-26); el front no calcula estados.
- Q3: `members_pending_payment` visible con texto, no solo color.
- Sin eventos ni funciones puras de dominio. Confirmado: sin discrepancias.

## Validación contra la arquitectura

- No toca el backend; consume `GET /dashboard` por `useDashboard()` (US-108).
- Rol: el API exige admin o coach; en el front, la guarda de ruta de US-053 redirige al `member` a `/mi`. La matriz de permisos de US-040 decide qué ve cada rol; admin y coach ven lo mismo.
- Estructura `web/src/features/dashboard/{api.ts,schemas.ts,pages/,components/}` y kit de `web/src/shared/ui/` (`KpiCard`, `PageHeader`). Nada de colores literales: solo tokens de `tokens.css`.
- Estado en la URL: los enlaces llevan los filtros como parámetros de consulta (`membership_status`, `from`, `to`), según `web/patterns.md`.
- Datos sensibles: ninguno en la página.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- No aplica (sin backend nuevo).

### Schemas
- No aplica (usa `dashboardSchema` de US-108).

### Router
- No aplica.

### Tests unitarios puros
- [ ] T1 · `web/src/features/dashboard/links.test.ts`: `kpiLinks(today)` devuelve `/socios?membership_status=active`, `expiring`, `expired`, `pending_payment` y `/pagos?from=2026-10-01T05:00:00Z&to=2026-11-01T05:00:00Z` para `today = 2026-10-20` (límites del mes de Bogotá en UTC, iguales a `month_bounds_utc` de US-100) — 1 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T2 · Debe seguir verde el chequeo de colores literales y de accesibilidad de US-068 sobre `features/dashboard` (sin hex, rgb ni nombres de color en `.tsx` ni `.css`) — 0,5 h

### Front
- [ ] T3 · `web/src/features/dashboard/links.ts`: función pura `kpiLinks(today: string)` con los destinos del criterio 3 y 4 y conversión del mes de Bogotá a `from`/`to` en UTC con `core/i18n/format.ts` — 1 h
- [ ] T4 · `web/src/features/dashboard/components/KpiGrid.tsx`: cuatro `KpiCard` de v0.1 con valor, etiqueta y enlace (`<Link>` de React Router 7), línea secundaria "N pendientes de pago" enlazada bajo "Al día", ingreso con `formatCop` y mes con `formatMonth` ("octubre 2026"); foco visible y área de clic de 44 px — 3 h
- [ ] T5 · `web/src/features/dashboard/components/FutureKpis.tsx`: tarjetas "Por avisar", "Asistencia de la semana", "Sesiones de hoy" y "WOD de hoy" que, con el campo `null`, muestran "Disponible en una próxima versión" y nunca `0`; con valor, lo muestran (así EP-14, EP-21 y EP-22 solo cambian datos) — 1,5 h
- [ ] T6 · `web/src/features/dashboard/pages/InicioPage.tsx`: página en `PanelLayout` con `PageHeader` ("Inicio" y fecha de hoy en Bogotá), `KpiGrid`, `FutureKpis` y el hueco del bloque de US-110; estados de carga (esqueleto de `KpiCard`) y error con "Reintentar" (`refetch`); ruta `/` registrada en `routes.tsx` con la guarda de admin y coach; comentario `// DESIGN-GAP:` en la línea de pendientes de pago — 2 h
- [ ] T7 · `web/src/features/dashboard/pages/InicioPage.test.tsx` (Vitest y Testing Library con MSW): valores del escenario (120, 14, 9, `$ 3.250.000`), tarjetas futuras vacías, enlaces correctos, error con reintento que vuelve a pedir, y que ninguna tarjeta depende solo del color (cada una tiene texto) — 2,5 h
- [ ] T8 · `web/tests/e2e/home.spec.ts` (Playwright): login como coach con datos de demo, clic en "Por vencer" llega a la lista filtrada; medición del tiempo desde el envío del login hasta que la grilla es visible (menos de 10 s); `member` redirigido a `/mi` — 2 h
- [ ] T9 · Capturas de `InicioPage` en 320, 768, 1024 y 1440, en claro y oscuro (flujo de US-068), revisadas sin desbordes — 1 h

### DevOps
- No aplica (el build del front ya está en la imagen de Nginx de US-006).

### Seguridad
- [ ] T10 · Revisión: la página no muestra datos personales; los enlaces no llevan datos sensibles en la URL; la guarda de ruta y el 403 del API coinciden — 0,5 h

## Orden de ejecución

1. T1 (en rojo) y T3.
2. T7 (en rojo), luego T4, T5 y T6.
3. T8 y T9.
4. T2 y T10.

## Dependencias técnicas

- US-108 · Contrato del tablero: `useDashboard()` y `dashboardSchema`.
- US-064 · Encabezado, pestañas y KPI: `KpiCard` con estados de carga, error y `null`.
- US-060 · Formato de dinero y fechas: `formatCop`, `formatMonth` y límites de mes de Bogotá.
- US-061 · Layout del panel; US-053 · Guardas de ruta por rol; US-067 · Mapa de rutas.
- US-071 · Filtrar socios por estado (destino `/socios?membership_status=`) y US-098 · Listar pagos (destino `/pagos?from=&to=`), dependencias suaves.
- US-068 · Temas, accesibilidad y capturas.
- US-111 · Datos de demostración (para T8).

## Endpoints

- `GET /api/v1/dashboard` — roles: admin, coach

## Riesgos

- Que US-071 o US-098 usen otros nombres de parámetro: los enlaces llevarían a listas sin filtrar — mitigación: T1 fija los nombres y la prueba E2E T8 recorre un enlace real.
- Diferencia de límites de mes entre front y API: el total de `/pagos` no cuadraría con la tarjeta — mitigación: T1 usa los mismos valores de prueba que `month_bounds_utc` de US-100.
- `DESIGN-GAP` de "pendientes de pago": el diseño puede pedir una quinta tarjeta después — mitigación: la línea es un componente aislado dentro de `KpiGrid`.
- Front condicionado a D1: si el gate no aprueba S1, la historia completa sale del alcance.

## Estimación

- Backend: 0 h
- Front: 8 h
- Pruebas: 6 h
- DevOps / seguridad: 1 h
- **Total: 15 h**

## Definición de hecho

- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/dashboard`
- [ ] `cd web && npx playwright test tests/e2e/home.spec.ts`
- [ ] Capturas de US-068 en cuatro anchos y dos temas revisadas
- [ ] Con datos de demo, los cuatro números de Inicio coinciden con `GET /api/v1/memberships/summary` y `GET /api/v1/payments/summary` (revisión manual con `curl`)
- [ ] `grep -rEn "#[0-9a-fA-F]{3,6}\b|rgb\(" web/src/features/dashboard` no devuelve nada
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npm test -- src/features/dashboard --coverage`
