# Sprint 1 · Front (Waves 5a/5b) — cuaderno de evidencia

Agente: `frontend-ux-engineer`, en un worktree aislado sobre `feat/sprint-01-nucleo-cripto-seguridad`. Solo toca `web/` y este archivo. No edita `docs/scratch/sprint-01.md` (lo lleva otra sesión).

Línea base antes de tocar nada (`web/`, `npm ci` limpio): `npx tsc --noEmit` sin errores, `npx vitest run` 10 archivos y 80 pruebas en verde, `npm run lint` en verde.

## Restricción transversal: `web/eslint.config.js` protegido

Los desgloses de US-059 (T8), US-060 (T4) y US-040 (T2) piden reglas nuevas en `web/eslint.config.js`. Ese archivo está protegido por el hook `config-protection` y no se rodea. Solución que no toca la config:

- Las reglas viven en `web/tests/lint/restricted-config.ts` (ESLint programático con `overrideConfigFile: true`, parser de `typescript-eslint`).
- `web/tests/lint/no-direct-fetch.test.ts` las aplica a todo `web/src/**/*.{ts,tsx}` real y falla si hay un hallazgo, así que `npm test` (y la CI) hace cumplir la frontera aunque `npm run lint` no la vea.
- Reglas: `fetch` (global y `window`/`globalThis`/`self.fetch`) solo en `src/core/api`; `no-console` en todo `src/`; `Intl` y `toLocale*` solo en `src/core/i18n`; comparación del rol con `"admin"`, `"coach"` o `"member"` (y `switch (role)`, `case "admin":`) solo en `src/core/auth/permissions.ts` y `session.ts`.
- **Pendiente para el usuario:** mover ese bloque a `web/eslint.config.js` cuando autorice editarlo. `tests/lint/*` queda fuera de `eslint .` por la exclusión del Sprint 0, así que los archivos nuevos de `tests/lint/` no se lintan con la config del repo (sí pasan `tsc`).

## S1-F1 · Cliente API y formato (US-059, US-060)

- **Rojo** (sobre stubs que lanzan "sin implementar"): `src/core/api/{errors,query,client,types.contract}.test.ts`, `src/core/i18n/format.test.ts`, `tests/lint/no-direct-fetch.test.ts`, `tests/lint/no-intl-outside-i18n.test.ts`. Resultado: 125 fallaban y 7 pasaban (de 132).
- **Verde:**
  - `src/core/api/errors.ts`: `ApiError` (`status`, `code`, `message`, `field`, `existingId`), `parseApiError(status, body)` con Zod sobre el envelope; sin envelope (HTML de Nginx, vacío, JSON ajeno) da `network_error` con "No pudimos conectar con el servidor. Intenta de nuevo."; 503 `crypto_unavailable` se respeta (N-16).
  - `src/core/api/query.ts`: `toQueryString` (omite `undefined`/`null`, repite arreglos), `listParams` (limit 500 → 200, 0 o ausente → 25, offset nunca negativo), `clampLimit` (para la URL, US-063: fuera de 1..200 → 25), `MAX_LIMIT = 200`, `DEFAULT_LIMIT = 25`.
  - `src/core/api/page.ts`: `Page<T>` y `pageSchema(item)` (Zod) para validar respuestas de lista.
  - `src/core/api/client.ts`: `api.get/post/put/patch/delete<T>(path, { query, body, signal })`, base `/api/v1`, `Authorization: Bearer` desde `setAccessTokenGetter` (token solo en memoria, N-13), timeout de 15 s (`code: "timeout"`), cancelación del que llama propagada como `AbortError`, 204 y cuerpo vacío dan `undefined`, `registerOnUnauthorized` invocado como máximo una vez por petición con un reintento si responde `"retry"`. Sin `console`.
  - `src/core/api/types.ts` generado con `openapi-typescript` 7.13.0 (MIT, versión exacta, dependencia de desarrollo) por `npm run gen:api` (alias `npm run generate:api`).
  - `src/config/locale.ts` (`LOCALE = "es-CO"`, `TZ_DISPLAY = "America/Bogota"`) y `src/core/i18n/format.ts`: `formatCop`, `formatCount`, `parseCop`, `formatDate`, `formatDateTime`, `formatTime`, `formatMonth`, `todayBogota`, `MONEY_INVALID`. El texto se arma con tablas propias de meses y "a. m."/"p. m." a partir de las partes numéricas de `Intl.DateTimeFormat` en Bogotá, para no depender de la versión de ICU.
- **Gate:** `SLICE_BASE=HEAD bash scripts/workflow/slice-gate.sh web/core <7 archivos de Rojo>` en verde: eslint de los archivos tocados, `tsc` del slice, 7 archivos y 129 pruebas.
- **Cobertura** (`vitest --coverage` sobre el slice): `src/core/api` 100 % líneas y 99 % ramas; `src/core/i18n` 100 % líneas y 86 % ramas; `src/config` 100 %.
- **Desviaciones:**
  - `credentials: "same-origin"`, no `"include"`: lo fijan el desglose de US-059 (T6, T11: "`credentials` nunca es `include`") y N-13; el plan aprobado manda sobre el encargo.
  - Sin MSW: `fetch` se simula con `vi.stubGlobal`; no hacía falta otra dependencia.
  - `types.contract.test.ts` (no `.test-d.ts`): Vitest no tiene el modo `typecheck` configurado; las aserciones `expectTypeOf` y el `@ts-expect-error` sobre `ErrorBody.cedula` los verifica `tsc --noEmit`. El esquema de prueba es `ErrorBody` porque el contrato aún no tiene `MemberRow` ni ninguna lista. La misma prueba regenera `types.ts` en un directorio temporal y lo compara con el versionado (criterio 5 sin depender de `git diff`).
  - `Page<T>` se declara a mano con un `DESIGN-GAP` en `page.ts`: `docs/openapi.json` todavía no publica un esquema de lista.
  - `test:tz` con `cross-env` (US-060 T6) no se agrega: la prueba cambia `process.env.TZ` en caliente (UTC, Asia/Tokyo y America/New_York) dentro de Vitest, sin dependencia nueva.
  - `listParams` limita a 200 y `clampLimit` vuelve a 25: son dos reglas distintas de dos historias (US-059 criterio 7 y US-063 criterio 2), no una sola función compartida como sugería el desglose de US-063.
  - Job de CI `web-contract` (US-059 T10): no se toca `.github/` en este encargo; la prueba de contrato corre dentro de `npm test`, que la CI ya ejecuta.
