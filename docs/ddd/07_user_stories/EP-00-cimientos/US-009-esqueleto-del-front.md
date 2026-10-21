# US-009 · Como equipo quiero el esqueleto de `web/` con Vite, React 19, TypeScript estricto, pruebas, tokens de diseño y fuentes locales para que cada pantalla nueva nazca con el diseño aprobado y sin colores inventados

- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context:** ninguno de negocio (`web/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (base de todas)

## Historia

Como equipo
quiero un proyecto Vite + React 19 + TypeScript estricto con ESLint, Vitest, Testing Library y Playwright, con `tokens.css`, fuentes Michroma y Titillium Web locales, logos y una regla que impida colores y fuentes literales
para que el front funcione sin internet en el local y se vea siempre igual al diseño

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** supuestos S1 (front en este repo, `web/`) y S3 (logos en `web/public/brand/`) de `DECISIONES.md`, pendientes del gate; `01_product_discovery.md` sección 6 (fuentes locales, internet intermitente); `05_service_design.md` sección 5 ("Nada de colores literales").
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** No aplica.
- **Front:** `web/package.json` con react 19, react-dom, react-router 7, @tanstack/react-query 5, react-hook-form 7, zod 3, lucide-react, vite 6, typescript, vitest, @testing-library/react, @testing-library/jest-dom, @playwright/test, eslint con typescript-eslint; `tsconfig.json` con `strict: true` y `noUncheckedIndexedAccess`; `web/src/core/styles/tokens.css` copiado de `docs/design/tokens.css` (fuente de verdad, sin editar); `web/public/fonts/` con Michroma y Titillium Web en `woff2` declaradas con `@font-face` y `font-display: swap`; `web/public/brand/` con los logos; regla de lint (stylelint `color-no-hex` + `declaration-property-value-disallowed-list`, o regla ESLint para estilos en línea) que falla si aparece un color hex, `rgb()` o `font-family` literal fuera de `tokens.css`; `main.tsx` con una página "APEX" mínima; scripts `dev`, `build`, `test`, `lint`, `e2e`; Playwright instalado con un test de humo que abre la página.

## Criterios de aceptación

1. `npm ci && npm run build` genera `web/dist` sin errores ni advertencias de tipos.
2. `npm test` corre Vitest en verde con al menos una prueba.
3. `npm run lint` falla si un componente usa un color literal (`#1a1a1a`, `rgb(…)`) o un `font-family` literal; pasa si usa `var(--…)` de `tokens.css`.
4. `web/src/core/styles/tokens.css` es idéntico a `docs/design/tokens.css` (prueba o paso de CI con `diff`).
5. Las fuentes se cargan desde `web/public/fonts/`; el build no hace ninguna petición a Google Fonts ni a otro CDN.
6. `npx playwright test` ejecuta el test de humo contra `vite preview` en verde.
7. TypeScript corre en modo estricto (`strict: true`).

## Escenarios BDD

```gherkin
# language: es
Característica: Esqueleto del front con diseño aprobado

  Escenario: Build y pruebas en verde
    Dado un clon limpio con Node instalado
    Cuando ejecuto "npm ci", "npm run build" y "npm test" en "web"
    Entonces los tres comandos terminan con código 0

  Escenario: Color literal rechazado
    Dado un componente con "color: #ff0000"
    Cuando ejecuto "npm run lint"
    Entonces el lint falla indicando usar un token de "tokens.css"

  Escenario: Sin dependencia de internet para fuentes
    Dado el build de producción
    Cuando abro la página sin conexión a internet en la LAN
    Entonces las fuentes Michroma y Titillium Web se muestran desde "/fonts"
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna propia; habilita todas.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** Vitest de humo, Playwright de humo, paso de CI de `diff` de tokens.
- **Archivos principales:** `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/src/main.tsx`, `web/src/core/styles/tokens.css`, `web/public/fonts/*`, `web/public/brand/*`, `web/.stylelintrc` o regla ESLint.

## Supuestos

- Supuesto: S1 se aprueba en el gate (el front se construye en `web/` dentro de este flujo, contra el párrafo "Alcance" de `CLAUDE.md`); si no se aprueba, esta historia y las de front quedan fuera de este repositorio.
- Supuesto: las licencias de Michroma y Titillium Web son OFL 1.1 (aceptadas por `01_product_discovery.md` sección 6).

## Dependencias

- US-001 · Repositorio git y estructura (carpeta `web/`).

## INVEST

- **Independiente:** no depende del backend.
- **Negociable:** herramienta exacta del lint de colores.
- **Valiosa:** fija la base visual y de calidad de todas las pantallas.
- **Estimable:** configuración estándar de Vite.
- **Pequeña:** tres a cuatro días.
- **Testeable:** comandos y lint de control.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto S1 declarado)

## Definición de terminado

- [ ] Build, lint, Vitest y Playwright en verde en CI
- [ ] Sin colores ni fuentes literales
- [ ] Revisión de PR aprobada
