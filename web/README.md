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
npm run e2e                   # Playwright, proyecto preview (construye y sirve en el puerto 4173, api simulado)
npm run e2e:stack             # Playwright, proyecto stack, contra el stack real de Compose (ver abajo)
npm run gen:api               # regenera src/core/api/types.ts desde docs/openapi.json
npm run licenses              # licencias de producción permitidas (US-004)
```

## E2E contra el stack (`npm run e2e:stack`)

El proyecto `stack` de `playwright.config.ts` no arranca servidor: prueba el stack de Compose ya levantado (Nginx, api y db). Lo corre el job `e2e-stack` de la CI y la validación V4 de cada sprint.

- `E2E_BASE_URL`: la URL de Nginx, por ejemplo `http://localhost:8180` en local o `http://localhost:80` en CI. Con ella definida no se arranca `webServer`.
- `E2E_ADMIN_EMAIL` y `E2E_ADMIN_PASSWORD`: el admin del `seed` (los mismos valores de `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` del `.env.seed`). Sin ellas `datosDeBase()` (`tests/e2e/helpers/stack.ts`) lanza un error. Se exportan solo en la shell, nunca en un archivo versionado; la CI las saca del `.env.seed` efímero con `::add-mask::`.
- Perfil E2E del borde: Nginx limita `/api/v1/auth/` a 60 por minuto por IP y todo el tráfico del host llega con la misma IP, así que el stack se levanta apilando `infra/compose.e2e.yml` (zona de 6000r/m) y con los topes del api subidos en `.env` (bloque "Perfil E2E de límites" de `.env.example`). Se vuelve a producción con `up -d web api` sin ese archivo. Detalle en `docs/RUNBOOK.md`, sección 1.
- Cada prueba entra con su propio login (`loginComo`); no se usa `storageState` porque el refresh rota en cada uso (DECISIONES, S2-V).
- Si se acaba de correr `scripts/smoke/headers.sh`, esperar unos 60 segundos: su ráfaga agota el `limit_req` de la IP.

```
DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"
$DC -f infra/compose.e2e.yml up -d web          # desde la raíz
cd web && E2E_BASE_URL=http://localhost:8180 E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=... npm run e2e:stack
```

## Reglas

- Colores, tipografía y tamaños solo con variables de `src/core/styles/tokens.css`. El lint rechaza hex, `rgb()`/`hsl()` y `font-family` literales fuera de `tokens.css` y `fonts.css`.
- `src/core/styles/tokens.css` es `docs/design/tokens.css` sin la línea `@import` de Google Fonts; si el diseño cambia, se copia de nuevo y se quita esa línea (`tokens.test.ts` lo vigila).
- Las fuentes (Michroma, Titillium Web, OFL 1.1) se sirven desde `public/fonts/`; el build no hace ninguna petición a CDN.
- Componentes compartidos en `src/shared/ui/` (Button, Field, StatusTag, ...), con CSS Modules.
- `tests/lint/` guarda archivos de control que violan el lint a propósito; `npm run lint` los salta y `tests/lint/lint-controls.test.ts` los ejercita.
