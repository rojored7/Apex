# Cuaderno · Sprint 4A · Front (worktree)

Worktree `.claude/worktrees/sprint-04a-front`, rama `feat/sprint-04a-front`, creada desde `feat/sprint-04a-worker-auditoria-tablero` tras el checkpoint de S4A-B4 (S4A-D62). Orden: F1 (tras B4), F2 (tras B5), F4 (tras B7), F3 (tras B8); se fusiona en V1.

Reglas del worktree:
- `SLICE_BASE` fijado a la base del worktree; `git rebase feat/sprint-04a-worker-auditoria-tablero` antes de cada slice.
- El front no edita `docs/scratch/sprint-04a.md`, `docs/ddd/DECISIONES.md`, `CLAUDE.md`, `docs/BRECHAS.md`, `docs/openapi.json` ni `web/src/core/api/types.ts`; sí edita `docs/design/ROUTES.md` y este cuaderno.
- Cada slice deja su bloque Rojo (conteo y motivo de cada prueba en rojo) y Verde (conteo en verde y desviaciones).

## S4A-F1 · Pantalla de auditoría (US-102, US-103, US-104 front)

Worktree creado desde `2464030` (checkpoint de B4 más su evidencia); `SLICE_BASE=$(git merge-base HEAD main)` = `f5f2503`. `npm ci` limpio (444 paquetes; el worktree nace sin `node_modules`). No hizo falta rebase: la rama del sprint no avanzó desde la creación.

- **Línea base** (`2464030`): `npx tsc --noEmit` sin errores; `npx vitest run src/features/system src/config src/routes.test.ts src/layouts src/core/api/errorCodes.test.ts tests/lint`: 34 archivos y 481 pruebas en verde.
- **F1.1 · Códigos, features y stubs:**
  - `core/api/errorCodes.ts`: `verificationRunning` y `auditEntryNotFound` (sus literales ya existen en `api/src/app/modules/audit/exceptions.py`).
  - `config/features.ts`: `audit` en `ENABLED_FEATURES` (nueve); `config/routeTable.ts`: `load` de `/sistema/auditoria` (`features/system/pages/AuditPage`). `routes.reference.ts` no cambia (feature, acceso y layout iguales).
  - `features/system/schemas.ts`: `AUDIT_ACTIONS`, `auditRowSchema` y `auditDetailSchema` estrictos (una fila con `before` o `after` es respuesta inválida), `fieldChangeSchema`, `verifyResultSchema`, `verifyStartedSchema`, `lastVerificationSchema`.
  - `features/system/api.ts`: `useAudit(params)`, `useAuditEntry(seq)`, `useLastVerification({ polling, baseline })` y `useVerifyChain()` (por `useSensitiveMutation`), con `VERIFY_POLL_MS = 3.000`, `VERIFY_MAX_MS = 900.000` y `VERIFY_MAX_POLLS = 300`. Nacieron completos en F1.1 (son la tubería; el rojo es de comportamiento en los componentes y las funciones puras).
  - Stubs: `shared/lib/encryptedBlob.ts`, `features/system/{auditFilters,auditErrors}.ts`, `components/{AuditFilters,AuditDetailPanel,VerifyChainButton}.tsx`, `pages/AuditPage.tsx` (+ `.module.css`). Fixture `src/test/audit.tsx` (`auditRow`, `AUDIT_ROWS`, `auditDetail`, `encryptedMarker`, `verifyResult`, `verifyStarted`, `auditPageReply`, `queryOf`, `renderAuditPage`).
- **F1.2 · Rojo** (11 archivos de la línea de gate y del slice; `tsc` limpio): 74 fallaban y 150 pasaban (224).
  - `src/shared/lib/encryptedBlob.test.ts`: 8 de 28 fallaban (los positivos: marcador y blob válidos, nunca el texto cifrado, `isEncryptedValue`); los `null` y los negativos pasaban con el stub.
  - `src/features/system/auditFilters.test.ts`: 20 de 30 (todo `toApiParams`, `readAuditFilters` y los `parseSeq` válidos).
  - `src/features/system/pages/AuditPage.test.tsx`: 19 de 20 (pasaba solo el de acceso del coach, que depende de la tabla de rutas).
  - `src/features/system/components/AuditDetailPanel.test.tsx`: 14 de 20 (pasaban los seis de `?seq=` inválido o ausente: el stub no pide nada).
  - `src/features/system/components/VerifyChainButton.test.tsx`: 13 de 13.
  - Pasaban de entrada (la feature y la ruta se habilitan en F1.1, como en S3-F3): `config/features.test.ts`, `routes.test.ts` (lista con `load` y `/sistema/auditoria`), `layouts/nav.test.ts` (Auditoría entre Usuarios y roles y Configuración; el coach no la ve), `core/api/errorCodes.test.ts` (los dos códigos), `tests/lint/boundaries.test.ts` y `tests/lint/sensitive-mutations.test.ts` (`useVerifyChain` en la lista de las que usan `useSensitiveMutation`, sin tocar la lista blanca).
  - E2E: `tests/e2e/stack/audit.spec.ts` (S4A-D59) y `tests/e2e/audit.spec.ts` de preview. **Decisión E8:** la captura de preview se crea en este Rojo y la línea 4 del gate queda.
- **F1.3 · Verde** (S4A-D31, S4A-D58):
  - `encryptedBlob.ts`: `parseEncryptedBlob` (marcador con `key_id` UUID y `alg`, o blob `apx1.<uuid>.<alg>.<b64url>.<b64url>` exacto; nunca devuelve nonce ni cifrado) e `isEncryptedValue` (todo marcador `encrypted: true`, también con `key_id` nulo de S4A-D105, y todo texto que contenga `apx1.`, S4A-D107).
  - `auditFilters.ts`: `readAuditFilters`, `toApiParams` (URLSearchParams; UUID, tabla con el patrón del api y de la lista auditada, acción de la lista, fechas reales de Bogotá a UTC `[from, to)` con `core/i18n`, rango invertido fuera, `record_id` solo con `table`, `q` solo desde memoria, `offset` múltiplo de `limit` y tope 100.000), `parseSeq` (decimal, entero seguro ≥ 1), etiquetas de tablas y acciones, `auditUserLabel` ("Sistema (worker)", "Usuario sin cuenta").
  - `auditValues.ts` (nuevo): valor a texto; "Cifrado · llave <id>" o "Cifrado · sin llave identificable", "(recortado)" para `{"truncated": true}`, objetos aplanados `a.b: valor · c: valor` y corte a 2.000 con "…".
  - `auditErrors.ts`: lista (403, 422 de fechas, 429, genérico), detalle (404 `audit_entry_not_found`) y verificación (409 `verification_running`, 429, 403, genérico), con `statusMessage`, `toScreenError` y `connectionMessage`.
  - `AuditPage.tsx`: `PageHeader` con total ("Más de 100.000 entradas" si el api satura), `VerifyChainButton`, `AuditFilters` (FilterBar: Registro, Fecha, Usuario con `GET /users?limit=200` más "Sistema (worker)", Entidad, Acción), aviso de filtro por registro o socio con "Quitar", `DataTable` (carga, vacío con "Limpiar filtros", error con "Reintentar"), `Pagination` y `AuditDetailPanel` por `?seq=` (cerrar lo quita con `replace`).
  - `AuditDetailPanel.tsx`: `SidePanel` "Entrada #N"; metadatos, cambios antes → después en monoespaciada, hashes en `<code>`, enlace a la ficha del socio, carga, 404 sin reintento y error con reintento. Sin `dangerouslySetInnerHTML`.
  - `VerifyChainButton.tsx`: línea de la última verificación (hora de Bogotá), "Verificar ahora" (S4A-D35), 200 con resultado, 202 y 409 con sondeo de `last` hasta que cambia `finished_at` (el sondeo lo para `refetchInterval` en cuanto llega otra; tope por `setTimeout` de 900 s con "La verificación no terminó; vuelve a intentarlo."), cadena rota con enlace a `?seq=X` conservando los filtros, primera verificación con "Sin verificación anterior que comparar.". En el 202 la caché de `last` toma el `last` de la respuesta para que una copia vieja no se tome por el resultado.
  - Resultado: los 11 archivos, 224 de 224 en verde. `npm run lint` y `npx tsc --noEmit` limpios. Lectura amplia sin cambios de código: `src/features/system src/config src/layouts src/routes* src/core src/shared tests/lint tests/unit tests/kit-inventory.test.ts` 115 archivos y 1.862 pruebas en verde; `src/App.test.tsx src/pages src/dev src/features/{auth,dashboard,plans}` 15 y 257 en verde.
  - Preview (`npx playwright test --project=preview tests/e2e/audit.spec.ts`): 6 de 6 (flujo del admin con 202 y sondeo; axe en claro y oscuro a 390 y 1440 px sin desborde, con capturas; coach en "Sin permiso" sin pedir `/audit`). Un defecto de prueba corregido: "Cerrar" del panel chocaba con "Cerrar detalle" (`exact: true`).
- **DESIGN-GAP** (para `BRECHAS.md` §11, S4A-D36):
  - `AuditPage.tsx`: sin columna "Qué cambió (anterior → nuevo)" (la lista no trae antes ni después, RN-13 y S4A-D16; solo en el detalle); sin "Exportar rango" (v0.2); la columna "Ver/Detalle" se une al enlace de la primera columna; el total saturado se dice "Más de 100.000 entradas".
  - `AuditFilters.tsx`: sin búsqueda por nombre del socio (el api busca por correo del usuario o por id del registro con la entidad); el selector de usuario lista hasta 200 cuentas.
  - `auditFilters.ts`: sin entidades Resultado (v0.5) ni Llave (v0.2); se ofrecen las nueve tablas auditadas de hoy.
  - `AuditDetailPanel.tsx`: sin "Descifrar dato" ni "Mostrar" (US-103 lo prohíbe; solo "Cifrado" con la llave); sin IP de origen ni "hash ok · hash anterior ok" por fila (no están en `AuditDetail`; la integridad la da "Verificar ahora"); sin valores enmascarados (los cifrados nunca salen de la auditoría).
  - `VerifyChainButton.tsx`: sin "última firma nocturna (ML-DSA)" (v0.3, `sign-audit`); se muestra la última verificación de la cadena.
- **Desviaciones:**
  - `parseEncryptedBlob` sigue la firma del plan (`{ keyId, alg } | null`); para el marcador con `key_id` nulo (S4A-D105) se agregó `isEncryptedValue`, que pinta "Cifrado · sin llave identificable".
  - `useLastVerification` recibe además `baseline` (el `finished_at` de referencia): el `refetchInterval` para solo al llegar otra verificación; el tope de 900 s lo aplica el componente. Un 409 también espera el resultado (el texto dice que aparece aquí).
  - `toApiParams` exige además que `table` esté en la lista de tablas auditadas (el api da 422 si no, S4A-D106) y que `record_id` venga con `table`.
  - Nuevos fuera de la lista del plan: `features/system/auditValues.ts`, `components/AuditDetailPanel.module.css` y `components/VerifyChainButton.module.css`.
  - `tests/e2e/helpers/stack.ts` no gana `verificarCadena` en F1: la spec del stack verifica por la pantalla; el helper por API llega con F3 si lo necesita.
  - La spec del stack abre el detalle de una entrada que ella misma genera (el alta del coach desechable, `table=auth.users&record_id=<id>`), así no depende de la primera página (S4A-D59); `grep -rn "job_runs\|audit_log" web/tests` sigue vacío.
- **Gates 1 a 4 de F1.5** (desde la raíz del worktree, `SLICE_BASE=f5f2503`, con `ls` previo de cada archivo):
  1. `slice-gate.sh web/core src/core/api/errorCodes.test.ts src/test/setup.ts src/test/vitest-axe.d.ts`: verde, 1 archivo y 64 pruebas.
  2. `slice-gate.sh web/shared src/shared/lib/encryptedBlob.test.ts src/test/setup.ts src/test/vitest-axe.d.ts`: verde, 1 archivo y 28 pruebas.
  3. `slice-gate.sh web/app src/config/features.test.ts src/routes.test.ts src/layouts/nav.test.ts tests/lint/boundaries.test.ts tests/lint/sensitive-mutations.test.ts src/test/setup.ts src/test/vitest-axe.d.ts`: verde, 5 archivos y 49 pruebas.
  4. `npx playwright test --project=preview tests/e2e/audit.spec.ts`: 6 de 6.
  - Desviación de la línea de gate: el primer intento del gate 1 sin `src/test/setup.ts` y `src/test/vitest-axe.d.ts` falló en `tsc -p tsconfig.slice.json` (los tipos de `jest-dom` y `vitest-axe` no entran en el tsconfig del slice cuando la lista toca `AuditPage.test.tsx`); se agregan a la lista de cada gate (no son pruebas: solo entran al tsc). El gate 6 (sellante) debe llevarlos también. Los avisos de eslint son de archivos ignorados por configuración (`tests/lint/boundaries.test.ts`), no de código del slice.
  - Lectura sin sello: `npx vitest run src/features/system` 20 archivos y 369 pruebas en verde (el gate 6 estaría en verde); `npx vitest run tests/lint` 7 y 41; `npm run lint` y `npx tsc --noEmit` limpios; `grep -rn "job_runs\|audit_log" web/tests` vacío.
- **Pendiente para el cierre de F1:** informe de `security-reviewer` (paso 104.5) y sus correcciones; gate 6 sellante; F1.6 (buildx de `apex-web:local`, `up -d --no-build web` y `E2E_BASE_URL=http://localhost:8180 npx playwright test --project=stack tests/e2e/stack/audit.spec.ts`); F1.7 checkpoint con el trailer.

### F1 · Revisión de seguridad

`security-reviewer` (paso 104.5): 0 CRITICAL, 0 HIGH, 1 MEDIUM, 3 LOW. Los cuatro se corrigen en el slice, cada uno con prueba:
1. **MEDIUM** `features/system/api.ts`, `useLastVerification`: el sondeo cada 3 s no se frenaba con un error (429, 5xx) y `VERIFY_MAX_POLLS` no se usaba. Ahora `refetchInterval` devuelve `false` si `state.status === "error"` o `state.fetchFailureCount > 0`, y también si `state.dataUpdateCount` llega a `maxUpdates`. Esa es la opción nueva: las lecturas de cuando empieza la espera más `VERIFY_MAX_POLLS`, que calcula `lastVerificationPollLimit(queryClient)`. `VerifyChainButton` la guarda en la fase de espera y, si la consulta falla, dice "No pudimos consultar el resultado de la verificación; vuelve a intentarlo en un momento." y vuelve a habilitar el botón. Pruebas en `VerifyChainButton.test.tsx`: con un 429 en el sondeo no hay más peticiones; `useLastVerification` se detiene tras `maxUpdates` lecturas aunque `finished_at` no cambie. Las dos fallan sin la corrección (comprobado y restaurado).
2. **LOW** `auditValues.ts`, `flatten`: una clave que contiene `apx1.` se pinta "(clave cifrada)" (`auditKeyText`, con `isEncryptedValue`); el nombre del campo de un cambio usa la misma regla. Prueba en `AuditDetailPanel.test.tsx`.
3. **LOW** `schemas.ts`, `auditDetailSchema`: `before` y `after` se validan y se descartan con un `.transform`; la vista ya no los guarda (el api los sigue enviando; el `.strict()` sigue rechazando claves desconocidas). Prueba en `AuditDetailPanel.test.tsx`.
4. **LOW** `tests/e2e/stack/audit.spec.ts`: el contexto del coach se cierra en el `finally`.

### Evidencia de S4A-F1 (después del sello)

- Antes del sello: `npm run lint` y `npx tsc --noEmit` limpios; `npx vitest run tests/lint src/features/system` 27 archivos y 414 pruebas en verde; preview `audit.spec.ts` 6 de 6.
- **Gate 6 (sellante):** `slice-gate.sh web/system src/features/system/pages/AuditPage.test.tsx src/features/system/components/AuditDetailPanel.test.tsx src/features/system/components/VerifyChainButton.test.tsx src/features/system/auditFilters.test.ts src/test/setup.ts src/test/vitest-axe.d.ts`: verde, 4 archivos y 87 pruebas. Hubo un solo aviso de eslint, de un archivo ignorado por configuración.
- **F1.6, imagen:** `apex-web:local` pasó de `sha256:695f6e2f027d…` (2026-10-28T21:24Z) a `sha256:62458b7264fb…` (2026-10-29T06:40Z), con buildx desde la raíz del worktree. `up -d --no-build web` se lanzó desde el repo principal y `apex-web-1` quedó `healthy` con la imagen nueva.
- **E2E stack:** `E2E_BASE_URL=http://localhost:8180 npx playwright test --project=stack tests/e2e/stack/audit.spec.ts` con el admin desechable `admin-e2e-1793249495@apex.test` dio 1 de 1 (2,4 s).
  - La contraseña se fijó con `tools issue-reset-link --as admin@ejemplo.local` y `POST /auth/reset` (204). Solo vivió en variables de ese comando y no está escrita en ningún archivo. El admin real no se tocó.
  - Una segunda corrida, más de 65 s después, con una contraseña nueva y una configuración temporal del scratchpad que solo añade `screenshot: "on"`, dio 1 de 1 (2,6 s). Las dos corridas pasan, así que la spec se puede repetir.
  - La verificación salió por 200 con "Cadena íntegra: 4.576 filas verificadas (29 oct 2026, 1:47 a. m.)".
  - Captura: lista filtrada por `auth.users` y el registro del coach, con 3 entradas (alta del admin y dos cambios), aviso "Quitar el filtro de registro" y línea de la última verificación. Está en el scratchpad de la sesión (`f1-stack-results/.../test-finished-1.png`) y no entra al repo.
