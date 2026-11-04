# Cuaderno del front · Sprint 4B

Rama del worktree de F1 (S4B-F1), que arranca tras el checkpoint de S4B-B4 (plan, sección 3). Este archivo es el único cuaderno que escribe el worktree del front; el backend y el orquestador escriben en `docs/scratch/sprint-04b.md`. Regla: el worktree hace rebase sobre la rama del sprint antes de F1 y no toca `docs/openapi.json` ni `web/src/core/api/types.ts` (solo el backend los regenera).

Worktree `.claude/worktrees/sprint-04b-front`, rama `feat/sprint-04b-front` desde `45b4050`.

Reglas del worktree:
- `export SLICE_BASE=$(git merge-base HEAD main)` en cada comando de gate (no persiste entre llamadas).
- El front no edita `docs/scratch/sprint-04b.md`, `DECISIONES.md`, `CLAUDE.md`, `docs/openapi.json` ni `web/src/core/api/types.ts`; F1 sí edita `docs/BRECHAS.md` §12 (Verde/Documentación) y este cuaderno.
- Memoria escasa: vitest solo sobre los archivos del slice; Playwright `preview` con `--workers=1`; nunca `stack`.

## S4B-F1 · Deuda de front con dueño 4B

### Rojo (paso 87 y 88)

- `npm ci` limpio. **Línea base** (`45b4050`): `npx vitest run tests/lint src/shared/ui/Tabs.test.tsx src/shared/lib/audit-labels.test.ts src/shared/ui/HistoryAside.test.tsx src/features/system/pages/AuditPage.test.tsx`: 11 archivos, 132 pruebas en verde; `npx tsc --noEmit` 0.
- **Stubs:** ninguno hizo falta. `Tabs.tsx`, `Tabs.module.css`, `HistoryAside.module.css` y `audit-labels.ts` no cambian en el Rojo (las pruebas compilan contra las firmas actuales; `entityLabel` no cambia de firma).
- **Pruebas nuevas** (después: 11 archivos, 140 pruebas; 8 en rojo, todas por aserción real, ninguna por compilación o fixture):
  - `web/tests/lint/no-session-storage.test.ts` (nuevo, 9 pruebas): **6 en rojo**, porque `restricted-config.ts` todavía no tiene la regla (`expected [] to include 'no-restricted-globals'` / `'no-restricted-properties'`): `sessionStorage` a secas en un archivo nuevo, `window.sessionStorage`, `globalThis.sessionStorage`, dentro de `src/core`, en archivos de nombre parecido al de la lista blanca (`RouteError2.tsx`, `features/x/pages/RouteError.tsx`) y la fuente real de `RouteError.tsx` copiada a `src/pages/Copia.tsx`. Pasan 3 que son guardas contra una regla mal escrita: `RouteError.tsx` en su ruta exacta da `[]` (con las tres formas), los `*.test.*` de `src` quedan fuera y `fetch` sigue prohibido en el mismo archivo.
  - `web/src/shared/ui/Tabs.test.tsx` (+8 pruebas, 22 en total): **2 en rojo** (`scrollIntoView` se llama 0 veces; esperado 1 con `{ inline: "nearest", block: "nearest" }` sobre la pestaña Historial): "si la activa no cabe la lleva a la vista" y "End a Historial en una barra corta". Pasan 6 (nueve pestañas con Historial activa y cinco deshabilitadas; si caben las nueve no se llama; Datos activa y cabe no se llama; sin `scrollIntoView` en el entorno no lanza; CSS sin px/rem/em/vw/ch/% literales en ancho, relleno, gap y tamaño de letra; toda `var(--x)` de `Tabs.module.css` existe en `tokens.css`).
  - `web/src/shared/lib/audit-labels.test.ts` (+3): `members.import_runs` y `crypto.crypto_keys` se devuelven crudos. Pasan hoy (no hay etiqueta para ellas): son guardas contra que alguien agregue una etiqueta equivocada o una excepción.
  - `web/src/features/system/pages/AuditPage.test.tsx` (+2): fila con `members.import_runs` / `crypto.crypto_keys` en la lista y detalle por `?seq=` de la segunda. Pasan hoy (`tableLabel` ya devuelve el nombre).
  - `web/tests/e2e/member-history.spec.ts` (preview, nuevo, 2 pruebas): entrada `reveal` con `purpose: "notify"` por `page.route`; axe `color-contrast` en claro y oscuro exige que la etiqueta "automático (aviso)" esté en `passes` (no en `incomplete`) y axe general sin violaciones. **Pasan 2 de 2: el contraste ya es suficiente en ambos temas**, así que `HistoryAside.module.css` no necesita cambio (el 4A no lo vio porque ninguna ruta produce la entrada, no porque falle).
  - `web/tests/e2e/member-tabs.spec.ts` (preview, +2 por tema): **2 en rojo**: a 1440 px con Historial activa, `Adjuntos Disponible en v0.3` termina en x=1466,5 y la barra acaba en 1416,5 (la última pestaña queda 50 px fuera; el recorte es real, no de jsdom).
  - `web/tests/e2e/home.spec.ts` (preview, +1): admin con KPI, "Por vencer" a `/socios?membership_status=expiring`, tabla visible en menos de 10 s. Pasa 1 de 1 (el comportamiento ya existe; es la versión simulada de la ampliación del stack).
  - `web/tests/e2e/stack/home.spec.ts` (+3, no corren en F1): KPI contra `GET /dashboard` y `psql` (se omite sin `E2E_DB_CONTAINER`), Por vencer más grilla en menos de 10 s, `member` → `/mi` (se omite sin `E2E_MEMBER_EMAIL`/`E2E_MEMBER_PASSWORD`). Corren en V4 (S4B-D88) con `E2E_BASE_URL=http://localhost:8280`.
  - `web/tests/e2e/stack/member-tabs.spec.ts` (+1, no corre en F1): mismas nueve cajas dentro de la barra a 1440 px en claro y oscuro, con `capture`.
  - `web/tests/e2e/stack/member-history.spec.ts`: sin cambios; ya tenía el axe general de la pestaña Historial con datos reales (claro y oscuro) desde el 4A.
- **Verificación del Rojo:** `npx tsc --noEmit` 0; `npx eslint` sobre los archivos del slice 0 errores (`tests/lint/*` está en `ignores` de ESLint, igual que las pruebas de lint anteriores); `npx playwright test --project=preview --workers=1 tests/e2e/member-tabs.spec.ts tests/e2e/member-history.spec.ts tests/e2e/home.spec.ts`: 22 pruebas, 20 en verde y 2 en rojo (las de barra).

### Dudas para el Verde

1. **Regla de lint:** `restricted-config.ts` agrupa `no-restricted-globals` y `no-restricted-properties` por bloques de `files`; en flat config el último bloque que coincide gana, así que la regla nueva debe sumarse a las listas existentes (FETCH_GLOBAL, INTL_GLOBAL) de cada bloque o ir en un solo bloque que las incluya. Debe ignorar `src/pages/RouteError.tsx` y `**/*.test.{ts,tsx}`. Los ids que esperan las pruebas son `no-restricted-globals` (a secas) y `no-restricted-properties` (`window`/`globalThis`/`self`).
2. **Tabs, causa del recorte:** a 1440 px las nueve caben solo si se reduce el ancho de las deshabilitadas (el texto "Disponible en v0.x" va en la misma línea). Opciones: apilar la nota bajo el rótulo (`flex-direction: column`) con `--space-*`, o relleno menor. La prueba de CSS prohíbe medidas literales en ancho, relleno, gap y letra. Si ni así caben (viewport menor), queda `scrollIntoView`.
3. **Tabs, efecto:** `scrollIntoView` debe llamarse en un efecto sobre `activeId` solo si la caja de la pestaña activa (`getBoundingClientRect`) no está dentro de la de la lista, con `?.` por si el entorno no la define (jsdom). No debe llamarse al montar si cabe.
4. **Contraste:** pasa hoy; confirmar con el `axe` del stack (V4/F1.6) y dejar la fila en BRECHAS §12 como "verificado, sin cambio".
5. **`table_name` desconocido:** las pruebas pasan sin cambio de código. Si el Verde quiere algo más que "crudo" (por ejemplo una etiqueta para `members.import_runs`), cambia el contrato de las pruebas.
6. **psql de `stack/home.spec.ts`:** las definiciones de pendientes (socios distintos con membresía `pending_payment`) e ingresos (pagos no anulados desde el 1 del mes de Bogotá) son mi lectura de `queries.py`/dashboard; V4 debe calibrarlas contra el ensayo antes de sellar.

### Verde (pasos 89 a 91, puntos 1-3)

- **Regla de `sessionStorage`** (`web/tests/lint/restricted-config.ts`): `SESSION_GLOBAL` y `SESSION_PROPERTIES` (`window`/`globalThis`/`self`). Los tres bloques de globales y propiedades se generan con `scopedRules({ withSession })`: primero con la regla nueva y `ignores` = lista blanca (`src/pages/RouteError.tsx`, `src/**/*.test.{ts,tsx}`); después un segundo juego acotado a la lista blanca con las listas viejas, para que `fetch`/`Intl` sigan prohibidos en `RouteError.tsx` y en las pruebas (un `ignores` simple los habría liberado: lo detectó la prueba "no sustituye las demás reglas"). `eslint.config.js` no se toca. `src/` entero no usa `sessionStorage` fuera de `RouteError.tsx` (solo un comentario en `MemberFormPage.tsx`, que la regla no ve): sin hallazgos.
- **Tabs** (`Tabs.module.css`): `.disabled` pasa a `flex-direction: column; justify-content: center; gap: var(--space-1)`; la nota "Disponible en v0.x" queda bajo el rótulo con el mismo texto y `--text-caption`. Altura 22 + 4 + 16 px = 42, dentro de `--control` (44). Sin medidas literales. `Tabs.tsx`: `listRef` en la lista y un `useEffect` sobre `activeId` que compara `getBoundingClientRect` de la pestaña con el de la barra y solo si no cabe llama `scrollIntoView?.({ inline: "nearest", block: "nearest" })` (con el cast a propiedad opcional por `no-unnecessary-condition`).
- **Sin cambio:** `HistoryAside.module.css`, `audit-labels.ts`, `RouteError.tsx`.
- **Conteos:** `tests/lint` 8 archivos, 50 pruebas (`no-session-storage` 9/9); `Tabs.test.tsx` 22/22; gate 2: 3 archivos, 82 pruebas; `tsc --noEmit` 0; `npx eslint src` 0; Playwright `preview` (`member-tabs`, `home`, `member-history`, `--workers=1`): 22/22.
- **Capturas** (`web/test-results/captures/`, ignoradas por git): `ficha-tabs-historial-{light,dark}-1440.png`, `ficha-historial-aviso-{light,dark}-1440.png`.
- **Resolución de las dudas:** (1) regla sumada a las listas de cada bloque (ver arriba); (2) apilar la nota, sin tocar relleno; (3) efecto con `?.`, sin llamada al montar si cabe; (4) contraste verificado en `preview`, fila 12.2, falta el axe del stack en F1.6; (5) `table_name` crudo, sin contrato nuevo, fila 12.3; (6) `stack/home.spec.ts` se calibra en V4, fila 12.5.
- **Desviaciones:** (D1) el gate `web/app` y `web/shared` falla en `tsc` (`toBeInTheDocument`/`toHaveAttribute`... "no existe") en cualquier prueba con jest-dom porque `tsconfig.slice.json` no incluye `src/test/setup.ts` ni `src/test/vitest-axe.d.ts` (comprobado con `TopBar.test.tsx`, que no toqué). Se corrieron los dos gates pasando esos dos archivos como extra en la lista; no se edita `slice-gate.sh`. Para el sello `web/members` hará falta lo mismo, o corregir el script. (D2) Los gates 1 y 2 escribieron su sello en `.git/apex/slice-gate.ok`; el sello de `web/members` lo reemplaza.
- **Pendiente:** security-reviewer, sello `web/members`, Docker y stack (F1.6), checkpoint.

### Verde · cierre tras el security-reviewer

- **HIGH-1 (aceptado, dueño: el usuario):** la regla de `sessionStorage` (y las de `fetch`/`Intl`) la aplica `npm test` vía `lintSourceTree` (gates `slice-gate`, `run-gates` y job `web` de CI), no `npm run lint`, porque `eslint.config.js` no importa `restricted-config.ts` y está protegido por `config-protection`. DECISIONES lo anota el orquestador.
- **LOW-1:** `no-restricted-syntax` con `MemberExpression[computed=true][object.name=/^(window|globalThis|self)$/]` en tres bloques disjuntos (rol + calculado; solo calculado en `permissions.ts`/`session.ts`; solo rol en la lista blanca). `no-session-storage.test.ts` 11/11: `window[k]` falla; el alias `const w = window` queda documentado como límite aceptado. `tests/lint` 8 archivos, 52 pruebas.
- **LOW-2:** `stack/home.spec.ts` valida `E2E_DB_CONTAINER` con `/^[w][w.-]*$/` antes de `execFileSync`.

### F1.6 · Docker

- Imagen `apex-web:local` construida desde el worktree con buildx (`--network host`): id `sha256:caf5b14b269fb9e633aeb619979214086eef2e7fc83344b1e2b352d66376bf7d`. `web` recreado con `--no-build --force-recreate` en el stack principal: `apex-web-1` healthy en el puerto 8180 (HTTP 200).
- Specs `stack` (`member-tabs`, `member-history`): **pendientes para V3/V4**. Motivo: la consulta de solo lectura `SELECT ... FROM auth.users WHERE email LIKE 'e2e-%' AND deleted_at IS NULL` devolvió 0 filas (no hay admin desechable vivo) y no hay otra vía válida para crearlo sin la sesión del admin real (no se resetea ni se toca `admin@ejemplo.local`). Las specs se corren en V3/V4 con el admin desechable que crea el operador. El resto de la verificación de F1 se hizo en `preview`.
