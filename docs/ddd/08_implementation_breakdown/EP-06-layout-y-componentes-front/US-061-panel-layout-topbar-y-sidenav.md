# US-061 · Panel layout, TopBar y SideNav — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-06-layout-y-componentes-front/US-061-panel-layout-topbar-y-sidenav.md`
- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context / módulo:** presentación (`web/src/layouts/`, `web/src/shared/ui/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**NEEDS_REFINEMENT**

El layout, el menú filtrado por rol, el grupo "Hoy" (Q25) y la accesibilidad están resueltos. La historia (y `DESIGN.md`) pone el nombre del gimnasio en la `TopBar`, que también ve el coach. Ese dato vive en `settings.gym`, cuyo `GET` es solo para admin (US-054), y `GET /auth/me` (US-045) solo devuelve `{ id, email, role, member_id }`. No hay un contrato para que el coach lea el nombre, y definirlo cambia un contrato del API.

## Resumen

Construye `PanelLayout` (grid con `TopBar`, `SideNav` y `<main>`, más el enlace "Saltar al contenido"), `TopBar` (logo según el tema, nombre del gimnasio, fecha y hora de Bogotá, correo y rol del usuario, menú con "Mi cuenta" y "Cerrar sesión", conmutador de tema) y `SideNav`, con los grupos de `DESIGN.md` y las entradas filtradas por `buildNavItems(role, enabledFeatures)`. El menú se pliega en tablet y pasa a cajón por debajo de 768 px, con Escape y devolución del foco. El grupo "Hoy" queda modelado como tres enlaces a pantallas existentes y oculto en v0.1.

## Correcciones aplicadas por DECISIONES.md

- Grupo "Hoy" → no es una pantalla ni una ruta; son tres enlaces (`Sesiones` filtrada a hoy, `WOD_Detalle` del día y `PorAvisarHoy`) que aparecen cuando sus épicas están habilitadas; en v0.1 no se muestra: aceptado por DECISIONES Q25 (la historia ya lo dice; se confirma).
- Permisos del menú → se toman de `can(role, action)` de US-040 (`plans.view`, `settings.manage`, `users.manage`, `audit.view`, `crypto.manage`), sin una lista de roles propia en `nav.ts`. Es coherente con RN-15 y Q6/Q7; no hay corrección.

## Validación contra el dominio

- No hay aggregates. Usa `User.role` (`admin`, `coach`, `member`) de la sesión. `buildNavItems("member", …)` devuelve una lista vacía, porque el socio usa `PortalLayout` (US-062).
- RN-15: el front oculta y el API verifica. Ocultar una entrada no reemplaza el 403 del API.
- Función pura `buildNavItems(role, enabledFeatures) -> NavItem[]`.

## Validación contra la arquitectura

- Capas de backend: no aplica en esta historia. La alternativa por defecto de la pregunta abierta agrega un campo a `GET /auth/me`, y ese cambio de backend lo hace US-045 (EP-04): `auth.service.me` llama a `settings.service.get(SectionKey.gym)`, de service a service, sin models cruzados.
- Estructura: `web/src/layouts/PanelLayout.tsx`, `web/src/layouts/nav.ts`, `web/src/shared/ui/TopBar.tsx` y `SideNav.tsx`. Usa `useCan` (US-040) y `formatDateTime` (US-060).
- Grupos de `DESIGN.md`: Inicio · Hoy · Gestión (Socios, Planes, Membresías, Pagos) · Entrenamiento (Clases, Movimientos, WODs) · Avisos · Sistema (Usuarios, Auditoría, Llaves, Configuración). Las "entradas" de la historia se acomodan dentro de esos grupos. Es una precisión, no un cambio de alcance.
- Tokens: `--sidebar` (232 px), `--control` (44 px), `--black` para la barra superior. Cero literales.

## Preguntas abiertas

- ¿De dónde lee la `TopBar` el nombre del gimnasio para el admin y el coach? Alternativa por defecto propuesta: `GET /api/v1/auth/me` agrega `gym_name: string` (roles admin, coach y member; valor de `settings.gym.name`, o "APEX" si la sección nunca se guardó), implementado en US-045. La `TopBar` lo recibe como prop `gymName` y, mientras US-045 no lo tenga, muestra "APEX". Alternativa descartable: un endpoint nuevo `GET /api/v1/settings/gym/public`.

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
- [ ] T1 · `web/src/layouts/nav.test.ts`: `buildNavItems` para `admin` con `enabledFeatures` de v0.1 (Inicio, Socios, Planes, Membresías, Pagos, Usuarios, Auditoría y Configuración); para `coach` (sin Planes ni ningún ítem de Sistema); para `member` (lista vacía); con `classes` habilitada aparece Clases; con `classes`, `wods` y `notifications` aparece el grupo Hoy con tres enlaces y ninguna ruta `/hoy`; grupos vacíos se omiten — 1 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- No aplica (la regla de colores literales de US-068 cubre estos archivos).

### Front
- [ ] T2 · `web/src/layouts/nav.ts`: tipos `NavGroup` y `NavItem` (`label`, `to`, `feature`, `action?` para `can`, `group`), catálogo `NAV_CATALOG` con los grupos de `DESIGN.md` y `buildNavItems(role, enabledFeatures)` pura, que filtra por `isRouteEnabled` (US-067) y `can` (US-040) — 1.5 h
- [ ] T3 · `web/src/layouts/PanelLayout.tsx`: grid de CSS con `TopBar` fija, `SideNav` de `var(--sidebar)` y `<main id="contenido" tabIndex={-1}>` con relleno `var(--space-6)`; enlace "Saltar al contenido" visible al enfocarlo; orden de tabulación TopBar, SideNav, contenido; tres modos según el ancho (escritorio ≥ 1024, tablet 768 a 1023 con menú plegado a iconos y texto accesible, celular < 768 con cajón) — 2.5 h
- [ ] T4 · `web/src/shared/ui/TopBar.tsx`: fondo `--black`, logo `apex-logo-dark-bg.png` desde `public/brand/`, nombre del gimnasio (prop `gymName`, por defecto "APEX"), fecha y hora de Bogotá con `formatDateTime` actualizada cada minuto, correo y rol de `GET /auth/me` (US-045), menú de usuario accesible (botón con `aria-haspopup` y `aria-expanded`, entradas "Mi cuenta" y "Cerrar sesión" como ranuras que conectan US-045 y US-044), botón de 44 px del conmutador de tema (usa el store de tema de US-068) y botón ☰ de 44 px solo en celular — 3 h
- [ ] T5 · `web/src/shared/ui/SideNav.tsx`: lista por grupos con títulos `--text-section-title`; el ítem activo lleva `aria-current="page"` y un indicador no cromático (barra lateral de 4 px más peso 700), además del fondo `--black`; modo cajón con `role="dialog"`, foco atrapado, cierre con Escape y clic fuera, y devolución del foco al botón ☰; ítems de 44 px — 3.5 h
- [ ] T6 · `web/src/layouts/PanelLayout.test.tsx`, `TopBar.test.tsx` y `SideNav.test.tsx` (Testing Library): el admin ve Planes y Sistema; el coach no ve Planes ni Usuarios, Auditoría, Llaves ni Configuración; `aria-current` en la ruta actual; orden de tabulación; "Saltar al contenido" lleva el foco a `<main>`; con 390 px, el ☰ abre el cajón, Escape lo cierra y el foco vuelve al ☰; `axe` sin violaciones — 3 h
- [ ] T7 · Playwright `web/tests/e2e/panel-layout.spec.ts`: capturas de una página de muestra dentro de `PanelLayout` en 320, 768, 1024 y 1440 px, en claro y oscuro, con aserción `scrollWidth <= clientWidth` — 1.5 h

### DevOps
- [ ] T8 · Publicar las capturas de T7 como artefacto del job `web-e2e` (el job lo crea US-068; aquí solo se agrega la spec) — 0.5 h

### Seguridad
- [ ] T9 · Revisión: el menú depende solo de `can` (sin roles en el código de cada pantalla); ocultar no reemplaza el 403 del API; la `TopBar` no muestra datos personales distintos del correo del propio usuario — 0.5 h

## Orden de ejecución
1. Resolver la pregunta abierta (y, si se acepta la alternativa por defecto, avisar a US-045)
2. T1 (en rojo)
3. T2
4. T6 (en rojo)
5. T3
6. T5
7. T4
8. T7
9. T8
10. T9

## Dependencias técnicas
- US-010 · Componentes base Button, Field y StatusTag.
- US-040 · Matriz de permisos del front (`can`, `useCan`).
- US-060 · Formato de dinero y fechas (`formatDateTime` en la `TopBar`).
- US-067 · Mapa de rutas (`isRouteEnabled`, `config/features.ts`); se puede desarrollar en paralelo con un stub.
- US-068 · Temas (store del tema que usa el conmutador); se puede desarrollar en paralelo.
- US-045 · Ver mi cuenta: correo y rol en la `TopBar` y, con la alternativa por defecto, `gym_name`.

## Endpoints
- Ninguno.

## Riesgos
- Front condicionado a D1.
- Si se elige el endpoint público alternativo, otra historia de EP-05 tiene que absorberlo — mitigación: la `TopBar` recibe `gymName` por prop, así que el origen del dato no cambia el componente.
- `DESIGN.md` no dibuja el cajón en celular ni el modo plegado de tablet — mitigación: `// DESIGN-GAP:` en `SideNav.tsx` y revisión visual con las capturas de T7.
- El reloj de la `TopBar` vuelve a renderizar todo el layout cada minuto — mitigación: el reloj va en un subcomponente aislado con su propio temporizador.

## Estimación
- Backend: 0 h
- Front: 10.5 h
- Pruebas: 5.5 h
- DevOps / seguridad: 1 h
- **Total: 17 h**

## Definición de hecho
- [ ] Backend: no aplica en esta historia (el campo `gym_name`, si se aprueba, se verifica en US-045)
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/layouts src/shared/ui/TopBar src/shared/ui/SideNav`
- [ ] `cd web && npx playwright test tests/e2e/panel-layout.spec.ts` con capturas en 320, 768, 1024 y 1440 px, en claro y oscuro, sin desborde horizontal
- [ ] Con sesión de coach, el DOM del menú no contiene "Planes", "Usuarios", "Auditoría", "Llaves" ni "Configuración" (aserción de la spec)
- [ ] `axe` sin violaciones de contraste, nombre accesible ni foco en el layout
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npx vitest run --coverage src/layouts src/shared/ui`
