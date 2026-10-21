# US-068 · Temas, accesibilidad y capturas — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-06-layout-y-componentes-front/US-068-temas-accesibilidad-y-capturas.md`
- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context / módulo:** presentación (`web/src/core/theme/`, `web/src/dev/`, `web/tests/e2e/`, CI)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

Los tokens y los dos temas ya existen en `docs/design/tokens.css`: el oscuro solo redefine variables, como pide el criterio 2. Los umbrales de accesibilidad y los anchos de captura están fijados. La herramienta (Playwright con `@axe-core/playwright`, stylelint) está dentro del stack; la licencia MPL-2.0 de `axe` es una confirmación del gate anotada como riesgo, no una duda de contrato. El tema por defecto de cada zona lo define `DESIGN.md` y no contradice la historia: la preferencia guardada manda, y sin ella se usa el defecto de la zona.

## Resumen

Agrega el mecanismo de tema (`data-theme` en `<html>`, preferencia guardada en `localStorage` dentro de `try/catch`, y respaldo en la preferencia del sistema o en el defecto de la zona), la regla de estilos que rechaza hex, `rgb()`, `hsl()` y familias de fuente fuera de `tokens.css`, y una página de catálogo con los 16 componentes del kit en sus estados, que no se enruta en producción. También agrega una suite de Playwright con `axe` sobre el catálogo y los cuatro layouts en los dos temas, capturas en 320, 768, 1024 y 1440 px con prueba de desborde horizontal, el umbral de cobertura del 80 % en `shared/ui/` y el job de CI que lo corre todo y publica las capturas como artefacto.

## Correcciones aplicadas por DECISIONES.md

- `StatusTag` del catálogo (criterio 7: siempre lleva texto) → el catálogo incluye el estado "Pendiente de pago", con borde y texto `--warning` como "Por vencer", además de Al día, Por vencer, Vencido, Sin plan, Congelado, Cancelado e Inactivo; `axe` y la captura lo cubren en los dos temas: corregido por DECISIONES Q3.

## Validación contra el dominio

- No hay aggregates. Aplica las restricciones no funcionales de accesibilidad (`01_product_discovery.md` 6): 44 px, 56 px en tablet, foco visible, contraste de 4,5:1 y nunca solo color.
- Ningún componente porta significado solo con color (criterio 7, `DESIGN.md` regla 10).
- No tiene funciones puras de dominio. La única función pura es de presentación: `resolveTheme(stored, zoneDefault, prefersDark) -> "light" | "dark"`.

## Validación contra la arquitectura

- Capas de backend: no aplica.
- Temas por zona, según `DESIGN.md` ("Temas"): panel en claro por defecto con un conmutador que guarda la preferencia; portal según `prefers-color-scheme`; gimnasio y TV forzados en oscuro (lo hace `useForcedTheme` de US-062). El catálogo sigue la preferencia del sistema, como pide el primer escenario BDD. Así se reconcilian la historia y el diseño sin cambiar el alcance.
- `web/src/core/styles/tokens.css` es una copia de `docs/design/tokens.css` (lo deja US-009). Su `@import` de Google Fonts se reemplaza por `@font-face` locales en `public/fonts/` (US-009, internet intermitente en el box). La regla de estilos solo permite literales de color y `font-family` en ese archivo.
- `localStorage` se usa solo para la preferencia de tema, que es una comodidad por visitante: si falla, el tema funciona en la sesión sin errores (criterio 3).
- Licencias: `@axe-core/playwright` (MPL-2.0, usado sin modificar y solo en desarrollo), `stylelint` (MIT) y `vitest-axe` (MIT). Hay que confirmar MPL-2.0 en la lista de `CLAUDE.md`, porque hoy está aceptada solo para OpenBao y pywebpush sin modificar. Como el paquete no se distribuye en la imagen, se anota como riesgo.

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
- [ ] T1 · `web/src/core/theme/theme.test.ts`: `resolveTheme` (guardada `dark` gana sobre el defecto `light` de la zona; sin preferencia guardada en el panel da `light`; sin preferencia en el portal sigue al sistema); `readStoredTheme` con un `localStorage` que lanza devuelve `null` sin error; `writeStoredTheme` con un `localStorage` que lanza no rompe y deja el tema aplicado en memoria (criterio 3) — 1 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T2 · `web/.stylelintrc.cjs` con `color-no-hex`, `function-disallowed-list: ["rgb","rgba","hsl","hsla"]` y `font-family-no-missing-generic-family-keyword`, más una regla propia (o `declaration-property-value-disallowed-list`) que rechaza `font-family` fuera de `src/core/styles/tokens.css`, con override para ese archivo; regla de ESLint `no-restricted-syntax` para literales de color en `style={{…}}` de TSX; fixture `web/tests/lint/fixtures/bad-color.css` con `#ff0000` que debe fallar indicando archivo y línea (`web/tests/lint/stylelint.test.ts`) — 2 h

### Front
- [ ] T3 · `web/src/core/theme/theme.ts`: `resolveTheme`, `readStoredTheme` y `writeStoredTheme` (clave `apex.theme`, con `try/catch`), `applyTheme(theme)` sobre `document.documentElement.dataset.theme`, y un store mínimo con `useSyncExternalStore` (`useTheme()`, `toggleTheme()`) que también escucha cambios de `prefers-color-scheme`; el defecto por zona se declara en cada layout (`PanelLayout` da `light`, `PortalLayout` da `system`) — 2 h
- [ ] T4 · `web/src/core/theme/ThemeToggle.tsx`: botón de 44 px con texto accesible ("Cambiar a tema oscuro"), que se coloca en la `TopBar` de US-061 — 0.5 h
- [ ] T5 · `web/src/dev/Catalog.tsx` y `web/catalog.html` (entrada separada de Vite, `vite build --mode catalog`): los 16 componentes (`Button`, `Field`, `StatusTag`, `TopBar`, `SideNav`, `PageHeader`, `FilterBar`, `DataTable`, `Pagination`, `Chips`, `Tabs`, `KpiCard`, `SidePanel`, `ConfirmModal`, `MaskedValue` y `HistoryAside`) en sus estados (carga, vacío, error, deshabilitado, foco y abierto) y los cuatro layouts con contenido de ejemplo (`LayoutsPreview` de US-062); el build de producción no incluye esta entrada — 3 h

### DevOps
- [ ] T6 · Playwright `web/tests/e2e/kit.spec.ts`: para cada tema (forzando `data-theme`) y cada ancho (320, 768, 1024 y 1440 px), abre el catálogo y los layouts, corre `AxeBuilder` con las etiquetas `wcag2a`, `wcag2aa` y `wcag21aa` (cero violaciones de contraste, nombre accesible, rol y foco), compara `document.documentElement.scrollWidth <= clientWidth` y guarda la captura en `test-results/captures/<tema>-<ancho>.png` — 3 h
- [ ] T7 · `web/vitest.config.ts`: `coverage.thresholds` con 80 % para `src/shared/ui/**` y `web/tests/kit-inventory.test.ts`, que falla si alguno de los 16 componentes no tiene su `*.test.tsx` (criterio 6) — 1.5 h
- [ ] T8 · `.github/workflows/ci.yml`: job `web-e2e` (`npm ci`, `npx playwright install --with-deps chromium`, `npm run build:catalog`, `vite preview` en segundo plano y `npx playwright test tests/e2e`) que sube `test-results/captures/` como artefacto; paso `npx stylelint "src/**/*.css"` en el job de lint; el job es obligatorio para mezclar — 2.5 h

### Seguridad
- [ ] T9 · Revisión: `localStorage` solo guarda `apex.theme`; el catálogo no está en el build de producción ni en la imagen de Nginx; sin fuentes remotas en producción (CSP de US-036 sin `fonts.googleapis.com`) — 0.5 h

## Orden de ejecución
1. T1 (en rojo)
2. T3
3. T4
4. T2
5. T7
6. T5
7. T6
8. T8
9. T9

## Dependencias técnicas
- US-009 · Esqueleto del front: tokens copiados, fuentes locales y Vitest.
- US-010 · Componentes base Button, Field y StatusTag.
- US-061, US-062, US-063, US-064, US-065 y US-066: los componentes y layouts del catálogo (la historia cierra después de todas ellas; T1 a T4 y T2 se adelantan).
- US-036 · Cabeceras y CSP de Nginx: no debe permitir fuentes remotas.

## Endpoints
- Ninguno.

## Riesgos
- Front condicionado a D1.
- `@axe-core/playwright` es MPL-2.0 y `CLAUDE.md` acepta MPL-2.0 solo para OpenBao y pywebpush — mitigación: es una dependencia de desarrollo que no se distribuye; confirmarlo en el gate junto con N-49. `axe-core` también es MPL-2.0 y no hay un motor de reglas WCAG equivalente con licencia MIT o Apache, así que la confirmación en el gate es necesaria (sin ella, el criterio 4 se verifica solo con revisión manual).
- Las capturas varían por fuentes y antialiasing entre máquinas — mitigación: en v0.1 las capturas son artefacto de revisión visual, no comparación de píxeles; la prueba automática es la de desborde.
- `tokens.css` del diseño importa Google Fonts y el box tiene internet intermitente — mitigación: US-009 lo reemplaza por `@font-face` locales; T9 verifica que la CSP no permite el dominio remoto.
- Un componente nuevo fuera del catálogo escapa de `axe` — mitigación: T7 exige prueba por componente, y la revisión de PR exige agregarlo al catálogo.

## Estimación
- Backend: 0 h
- Front: 5.5 h
- Pruebas: 3 h
- DevOps / seguridad: 7.5 h
- **Total: 16 h**

## Definición de hecho
- [ ] Backend: no aplica (la historia no toca `api/`)
- [ ] `cd web && npm run lint && npx stylelint "src/**/*.css" && npx tsc --noEmit && npm test -- src/core/theme tests/lint tests/kit-inventory.test.ts`
- [ ] `cd web && npm run build:catalog && npx playwright test tests/e2e/kit.spec.ts` en verde, con 16 capturas (4 anchos × 2 temas × catálogo y layouts) publicadas como artefacto de CI
- [ ] Agregar `color: #ff0000` a `src/shared/ui/Button.css` hace fallar stylelint con archivo y línea (verificación manual en el PR)
- [ ] `grep -rnE "#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(" web/src --include=*.css --include=*.tsx | grep -v core/styles/tokens.css` no devuelve nada
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npx vitest run --coverage` con umbral 80 en `src/shared/ui/**` y `src/core/theme/**`
