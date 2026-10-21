# web

Front de APEX: React 19 + TypeScript + Vite 6. Fuente de verdad del diseño: `docs/design/` (leer `DESIGN.md` antes de tocar una pantalla).

## Requisitos

- Node 22 (`.nvmrc`) y npm. Todo se corre desde `web/`.

## Comandos

```
npm ci                        # dependencias exactas del package-lock.json
npm run dev                   # servidor de desarrollo de Vite
npm run build                 # tsc --noEmit y vite build a dist/
npm run preview               # sirve dist/ en local
npm run lint                  # ESLint (TS y React) y Stylelint (CSS)
npx tsc --noEmit              # revisa tipos de src, tests y configs
npm test -- --run             # Vitest una vez
npm test -- --run --coverage  # Vitest con cobertura (umbral 80 % sobre src/)
npx playwright install chromium   # una vez, navegador de las pruebas de humo
npm run e2e                   # Playwright (construye y sirve en el puerto 4173)
npm run licenses              # licencias de producción permitidas (US-004)
```

## Reglas

- Colores, tipografía y tamaños solo con variables de `src/core/styles/tokens.css`. El lint rechaza hex, `rgb()`/`hsl()` y `font-family` literales fuera de `tokens.css` y `fonts.css`.
- `src/core/styles/tokens.css` es `docs/design/tokens.css` sin la línea `@import` de Google Fonts; si el diseño cambia, se copia de nuevo y se quita esa línea (`tokens.test.ts` lo vigila).
- Las fuentes (Michroma, Titillium Web, OFL 1.1) se sirven desde `public/fonts/`; el build no hace ninguna petición a CDN.
- Componentes compartidos en `src/shared/ui/` (Button, Field, StatusTag, ...), con CSS Modules.
- `tests/lint/` guarda archivos de control que violan el lint a propósito; `npm run lint` los salta y `tests/lint/lint-controls.test.ts` los ejercita.
