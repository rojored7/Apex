# US-009 · Esqueleto del front con tokens y fuentes locales — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-00-cimientos/US-009-esqueleto-del-front.md`
- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context / módulo:** ninguno de negocio, presentación (`web/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

El stack del front está fijado en `05_service_design.md` sección 5 y las licencias de fuentes e iconos quedan permitidas por DECISIONES N-49. Hay una tensión real entre el criterio 4 ("`tokens.css` idéntico a `docs/design/tokens.css`") y el criterio 5 ("ninguna petición a Google Fonts"): el archivo de diseño empieza con `@import url("https://fonts.googleapis.com/...")`. La resuelve `docs/design/DESIGN.md` (sección Tipografía: "descargar las dos familias a `public/fonts/` y cambiar el `@import` por `@font-face`"), así que no hace falta pregunta: la copia es idéntica salvo esa línea y la comparación de CI la excluye. El supuesto S1 (front en este repositorio) es pendiente del gate D1 y se trata como riesgo aceptado.

## Resumen

Proyecto Vite 6 + React 19 + TypeScript estricto en `web/` con ESLint (typescript-eslint), Stylelint, Vitest + Testing Library + jsdom y Playwright con un test de humo. `web/src/core/styles/tokens.css` es la copia de `docs/design/tokens.css` sin la línea `@import` de Google Fonts; las fuentes Michroma y Titillium Web (400, 600, 700) viven en `web/public/fonts/` en `woff2` con `@font-face` y `font-display: swap` en `web/src/core/styles/fonts.css`; los tres logos van a `web/public/brand/`. Una regla de lint falla ante colores hex, `rgb()`/`hsl()` o `font-family` literales fuera de los dos archivos de estilos base. `main.tsx` muestra una página mínima "APEX".

## Correcciones aplicadas por DECISIONES.md

- La historia acepta `0BSD` como supuesto y supone OFL 1.1 para las fuentes → `0BSD`, `ISC` y `OFL-1.1` quedan permitidas: corregido por DECISIONES N-49.
- Criterio 4 "idéntico" → idéntico salvo la línea `@import` de Google Fonts, reemplazada por `@font-face` locales en `fonts.css`: no es DECISIONES.md sino `docs/design/DESIGN.md` (Tipografía); se anota aquí porque cambia cómo se verifica el criterio.

## Validación contra el dominio

- No hay aggregates, entidades, value objects, invariantes RN-xx ni eventos.
- RN-01 (dinero entero) y el formato de fechas en Bogotá no se tocan aquí; son de US-060.

## Validación contra la arquitectura

- Estructura de `05_service_design.md` sección 5: `web/src/core/styles/tokens.css`, `web/src/core/api/` (vacío, lo llena US-059), `web/src/shared/ui/` (lo llena US-010), `web/src/features/`, `web/public/brand/`, `web/public/fonts/`, `web/tests/e2e/`.
- "Nada de colores literales": la regla de lint es el control automático; `tokens.css` y `fonts.css` son los únicos archivos exentos.
- Funciona sin internet en el local (`01_product_discovery.md` sección 6): fuentes locales y ninguna petición a CDN en el build.
- El cliente HTTP, los tipos generados desde `docs/openapi.json`, el router con el mapa de rutas y los temas son de EP-06 (US-059, US-067, US-068); aquí solo se instalan las dependencias.
- Sin backend, sin bus, sin roles, sin paginación ni auditoría: no aplica.

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
- [ ] T1 · `web/src/core/styles/tokens.test.ts`: lee con `node:fs` `docs/design/tokens.css` y `web/src/core/styles/tokens.css`, quita del original las líneas que empiezan por `@import` y exige igualdad exacta del resto (criterio 4); exige que la copia no contenga `fonts.googleapis.com` — 1 h
- [ ] T2 · `web/src/App.test.tsx`: renderiza `App` con Testing Library y encuentra el encabezado "APEX" (criterio 2, prueba mínima de Vitest) — 0,5 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T3 · `web/tests/lint/`: tres archivos de control (`bad-hex.module.css` con `color: #ff0000`, `bad-font.module.css` con `font-family: Arial`, `BadInline.tsx` con `style={{ color: "rgb(1,2,3)" }}`) y `web/tests/lint/lint-controls.test.ts` que corre Stylelint y ESLint por su API de Node sobre ellos y exige errores, y sobre un `good.module.css` con `color: var(--ink)` y exige cero errores (criterio 3). Los archivos de control quedan excluidos del `npm run lint` normal — 2 h

### Front
- [ ] T4 · Andamiaje: `web/package.json` con `"type": "module"`, scripts `dev`, `build` (`tsc --noEmit && vite build`), `preview`, `test` (`vitest`), `lint` (`eslint . && stylelint "src/**/*.css"`), `e2e` (`playwright test`); dependencias react 19, react-dom 19, react-router 7, @tanstack/react-query 5, react-hook-form 7, zod 3, lucide-react; desarrollo vite 6, @vitejs/plugin-react, typescript 5, vitest, jsdom, @testing-library/react, @testing-library/jest-dom, @testing-library/user-event, @vitest/coverage-v8, @playwright/test, eslint 9, typescript-eslint, eslint-plugin-react-hooks, stylelint, stylelint-config-standard; `package-lock.json` versionado; `.nvmrc` con 22 — 3,5 h
- [ ] T5 · `web/tsconfig.json` único (para que `npx tsc --noEmit` revise todo): `strict: true`, `noUncheckedIndexedAccess: true`, `exactOptionalPropertyTypes: true`, `jsx: react-jsx`, `moduleResolution: bundler`, `types: ["vite/client", "vitest/globals", "@testing-library/jest-dom"]`, `include: ["src", "tests", "vite.config.ts", "playwright.config.ts"]` — 1 h
- [ ] T6 · `web/vite.config.ts` con `@vitejs/plugin-react` y bloque `test` de Vitest (`environment: "jsdom"`, `setupFiles: ["src/test/setup.ts"]`, `css: { modules: { classNameStrategy: "non-scoped" } }`, cobertura v8 con umbral 80 % sobre `src/`); `web/src/test/setup.ts` con `@testing-library/jest-dom/vitest` — 1 h
- [ ] T7 · `web/src/core/styles/tokens.css`: copia exacta de `docs/design/tokens.css` sin la línea `@import` y sin ningún agregado (para que T1 compare igual); la nota "las fuentes se cargan localmente, ver DESIGN.md Tipografía" va en la cabecera de `fonts.css` — 0,5 h
- [ ] T8 · Fuentes locales: descargar `Michroma-Regular` y `TitilliumWeb-Regular`, `-SemiBold`, `-Bold` del repositorio oficial `google/fonts` (OFL), convertir o tomar `woff2` con subconjunto latin y latin-ext (tildes y ñ), guardar en `web/public/fonts/` con `OFL.txt` de cada familia; `web/src/core/styles/fonts.css` con cuatro `@font-face` (`font-display: swap`, `src: url("/fonts/...woff2") format("woff2")`) — 2,5 h
- [ ] T9 · Logos: copiar `docs/design/assets/logo/apex-logo-dark-bg.png`, `apex-logo-light-bg.png` y `apex-mark.png` a `web/public/brand/`; favicon desde `apex-mark.png` (S3) — 0,5 h
- [ ] T10 · `web/index.html` con `lang="es-CO"`, `<title>APEX</title>`, favicon de `/brand/apex-mark.png` y `<div id="root">`; `web/src/main.tsx` que importa `fonts.css` y `tokens.css` y monta `App`; `web/src/App.tsx` con un `<h1>` "APEX" que usa `var(--text-screen-title)`; carpetas vacías con `.gitkeep`: `src/core/api/`, `src/shared/ui/`, `src/features/`, `src/layouts/` — 1 h
- [ ] T11 · Lint de colores y fuentes: `web/.stylelintrc.json` que extiende `stylelint-config-standard` con `color-no-hex: true`, `color-named: "never"`, `function-disallowed-list: ["rgb", "rgba", "hsl", "hsla", "hwb", "lab", "lch", "oklch", "color"]`, `declaration-property-value-allowed-list: { "font-family": ["/^var\\(--/", "inherit"], "font": ["/var\\(--/", "inherit"] }` e `ignoreFiles: ["src/core/styles/tokens.css", "src/core/styles/fonts.css", "tests/lint/**"]`; `web/eslint.config.js` (flat) con typescript-eslint estricto, react-hooks y `no-restricted-syntax` que prohíbe en props `style` literales con `#hex`, `rgb(`, `hsl(` o `fontFamily` (criterio 3) — 2 h
- [ ] T12 · Playwright: `web/playwright.config.ts` con `webServer: { command: "npm run build && npm run preview -- --port 4173 --strictPort", port: 4173 }`, un solo proyecto Chromium; `web/tests/e2e/smoke.spec.ts` que abre `/`, ve "APEX", registra todas las peticiones y exige que ninguna salga de `localhost` (criterio 5), y comprueba `document.fonts.check("16px Michroma")` y `document.fonts.check("16px 'Titillium Web'")` después de `document.fonts.ready` (criterio 6) — 1,5 h

### DevOps
- [ ] T13 · CI: el job `web` de US-003 ya corre `npm ci`, lint, `tsc`, Vitest, build y Playwright; agregar `grep -r "fonts.googleapis\|fonts.gstatic" web/dist && exit 1 || true` como paso explícito tras el build, y la caché de navegadores de Playwright — 0,5 h

### Seguridad
- [ ] T14 · Revisión: `npm audit --omit=dev` sin vulnerabilidades altas; `license-checker --production` (US-004) en verde con N-49; `OFL.txt` presentes junto a las fuentes; ninguna dependencia de producción con script `postinstall` desconocido — 0,5 h

## Orden de ejecución
1. T4, T5, T6 (andamiaje, tipos y Vitest)
2. T1, T2 (pruebas en rojo)
3. T7, T8, T9, T10 (tokens, fuentes, logos y página mínima)
4. T3, T11 (lint de control en rojo y luego la regla)
5. T12 (Playwright de humo)
6. T13 (CI)
7. T14 (revisión)

## Dependencias técnicas
- US-001 · Repositorio git y estructura: carpeta `web/` y `.gitattributes` con `*.woff2 binary`.
- US-003 · Pipeline CI: job `web` donde corren lint, Vitest, build y Playwright.
- US-004 · Chequeo de licencias: paso `licencias-web` que valida estas dependencias.

## Endpoints
- Ninguno.

## Riesgos
- Front condicionado a D1: si el gate no aprueba S1, esta historia sale de este repositorio y las de front de todas las épicas también — mitigación: ninguna técnica; se decide en el gate.
- `docs/design/tokens.css` cambia en el futuro (el diseño se actualiza por Q3 y la paginación de D2): T1 falla hasta que se copie de nuevo — mitigación: es el comportamiento deseado; la falla nombra el archivo y el procedimiento es copiar y volver a quitar la línea `@import`.
- `declaration-property-value-allowed-list` de Stylelint con el atajo `font` puede rechazar usos válidos como `font: var(--text-body)` si el patrón está mal escrito — mitigación: casos de control positivos en T3.
- Fuentes de Google Fonts en `woff2` sin `latin-ext` pierden glifos del español en algunos pesos — mitigación: subconjunto latin y latin-ext en T8 y captura del texto "Año, Bogotá, ÑANDÚ" en el Playwright de humo.
- Versiones mayores nuevas (Vite 7, Zod 4) disponibles en el registro: la historia fija Vite 6 y Zod 3 — mitigación: se respeta la historia; un cambio de versión mayor es una historia aparte.

## Estimación
- Backend: 0 h
- Front: 13,5 h
- Pruebas: 3,5 h
- DevOps / seguridad: 1 h
- **Total: 18 h**

## Definición de hecho
- [ ] `cd web && npm ci && npm run build` termina con código 0 sin advertencias de tipos
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- --run src/core/styles/tokens.test.ts src/App.test.tsx tests/lint/lint-controls.test.ts`
- [ ] `cd web && npx playwright test tests/e2e/smoke.spec.ts` en verde
- [ ] `grep -rc "fonts.googleapis\|fonts.gstatic" web/dist | grep -v ":0$"` no devuelve nada
- [ ] `diff <(grep -v '^@import' docs/design/tokens.css) web/src/core/styles/tokens.css` sin diferencias
- [ ] `ls web/public/fonts/*.woff2 | wc -l` devuelve 4 y existen `web/public/fonts/OFL*.txt`
- [ ] `cd web && npm run licenses` en verde (US-004)
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npm test -- --run --coverage`
