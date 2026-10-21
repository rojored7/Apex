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
- **Checkpoint:** `b7ade37`.

## S1-F2 · Permisos, encabezados y paneles (US-040, US-064, US-065)

- **Rojo** (stubs: `can` siempre falso, `useCan` siempre verdadero, componentes que devuelven `null`, `useFocusTrap` sin efecto): `src/core/auth/{permissions.test.ts,Can.test.tsx}`, `tests/unit/no-role-literals.test.ts`, `src/shared/hooks/useFocusTrap.test.tsx`, `src/shared/ui/{PageHeader,Tabs,KpiCard,SidePanel,ConfirmModal}.test.tsx`, `src/shared/ui/header-tabs-kpi.a11y.test.tsx`, `src/shared/ui/dialogs.a11y.test.tsx`, `src/shared/ui/css-tokens.test.ts`. Resultado: 76 fallaban y 25 pasaban (de 101). Las que pasaban: `no-role-literals` (la regla de roles ya entró en `restricted-config.ts` en S1-F1, antes de su prueba: desviación del orden TDD, anotada), los `axe` sobre stubs vacíos y `css-tokens` sobre los módulos del Sprint 0.
- **Verde:**
  - `src/core/auth/permissions.ts`: `ROLES`, `Role`, tabla `as const satisfies Record<string, readonly Role[]>`, `Action = keyof typeof TABLE` (una acción inexistente no compila), `ACTIONS` y `MATRIX` congelados, `can(role, action)` con `Object.hasOwn` y negación por defecto. Matriz del desglose con N-20 (`members.document.update`, `members.reactivate`), Q6/Q7/Q8, Q15/N-29 (`members.export`, `payments.export`) y Q25 (sin `today.view`).
  - `src/core/auth/useCan.ts` (`RoleContext`, `RoleProvider`, `useRole`, `useCan`), `Can.tsx` (`<Can action fallback?>`) e `index.ts`.
  - `src/shared/hooks/useFocusTrap.ts`: guarda el que abrió, enfoca el primer control (o `initialFocusRef`, o el contenedor), cicla Tab y Mayús+Tab, Escape llama a `onEscape`, bloquea el `overflow` del body con contador y devuelve el foco. Pila de trampas: con un `ConfirmModal` sobre un `SidePanel` solo la de arriba responde.
  - `PageHeader`: migas (`nav aria-label="Migas"`, `aria-current="page"`), un solo `h1` en `--text-screen-title`, total e insignia junto al título, hasta tres acciones (enlace con estilo de botón o `Button`) y el resto en "Más acciones" (`aria-haspopup="menu"`, `role="menu"`, flechas, Inicio, Fin, Escape, clic fuera).
  - `Tabs`: `tablist`/`tab`/`tabpanel` con tabindex móvil, flechas que saltan las no disponibles y dan la vuelta, Inicio y Fin; activa en `?tab=` (conserva los demás parámetros) o en el segmento (`urlMode="segment"`, `basePath`); una pestaña con `disabledUntil` lleva `aria-disabled` y el texto "Disponible en v0.x".
  - `KpiCard`: dinero con `formatCop`, conteo con `formatCount` (agregado a `format.ts` en S1-F1), `null` da "Disponible en v0.x" (o "Sin datos"), esqueleto con `aria-busy`, error "No se pudo cargar" con "Reintentar", con `href` un único `Link` con nombre "Etiqueta: valor" y descripción con la nota, `attention` con `--blue-tint` y borde `--apex-blue`.
  - `SidePanel`: portal, `role="dialog"`, `aria-modal`, `aria-labelledby`; ✕, Cancelar, Escape y clic en el velo pasan por `requestClose`, que con `isDirty` abre un `ConfirmModal` ("¿Descartar los cambios?" / "Descartar cambios" / "Volver"); ancho `calc(var(--sidebar) * 2)` y 100 % por debajo de 768 px; entrada con `transform`, sin animación con `prefers-reduced-motion`.
  - `ConfirmModal`: portal, título y consecuencia asociados (`aria-labelledby`, `aria-describedby`), motivo obligatorio u opcional (`showReason`) con `minReasonLength = 3` sobre el texto recortado, `confirmText` exacto, envío único con bandera en `useRef` y `aria-busy`, el motivo se envía tal cual, error del api con `field = "reason"` bajo el motivo y el resto en `role="alert"` (texto, nunca HTML), error no del api con "No se pudo completar la acción. Intenta de nuevo."; Escape y Volver no cierran mientras envía; cada apertura empieza limpia.
  - `src/shared/ui/index.ts` exporta los cinco componentes; `src/core/auth/index.test.ts` y `src/shared/ui/index.test.ts` cubren los barriles.
- **Gates:** `slice-gate.sh web/core` con `src/core/auth/{permissions.test.ts,Can.test.tsx,index.test.ts}` y `slice-gate.sh web/shared` con las demás pruebas del Rojo más `index.test.ts`, en verde (ver resultados abajo).
- **Cobertura** (suite completa con `--coverage`): `src/core/auth` 100 %; `src/shared/hooks` 100 % líneas y 97 % ramas; `src/shared/ui` 99 % líneas y 96 % ramas; global 99 %.
- **DESIGN-GAP:** `SidePanel.module.css` y `ConfirmModal.module.css`: no hay token para el velo de los diálogos (se usa `color-mix` de `--black` al 45 %) ni para el ancho del panel lateral (dos veces `--sidebar`).
- **Desviaciones:**
  - La regla de literales de rol (US-040 T2) no está en `web/eslint.config.js` sino en `tests/lint/restricted-config.ts` (ver la restricción transversal); es más estricta que el desglose: prohíbe comparar cualquier valor con `"admin"`, `"coach"` o `"member"`, no solo una variable llamada `role`.
  - `session.ts` no existe todavía (es de US-053); la excepción de la regla ya lo nombra.
  - US-040 T7 (alinear `member.reveal` y `member.create` en US-066 y US-072): `MaskedValue` de S1-F3 usa `members.reveal`; US-072 es de un sprint posterior y el tipo `Action` impedirá compilar el nombre viejo.
  - `PageHeader` recibe `total` como texto ya formateado (el diseño muestra "342 en total · 269 con membresía") en lugar de un número.
  - `Tabs` recibe el contenido como función `children(activeId)` y pinta un solo `tabpanel` (el de la pestaña activa).
