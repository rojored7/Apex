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

## S4A-F2 · Historial de la ficha (US-106 front)

- **F2.1 · Rebase y stubs:** `git rebase feat/sprint-04a-worker-auditoria-tablero` trae B5 (`82d4e7e`: contrato `GET /members/{member_id}/audit` y `MemberHistoryItem` en `docs/openapi.json` y `types.ts`, sin regenerar); F1 queda en `7ad022a` (checkpoint) y `dc3d31e` (evidencia, HEAD). `package-lock.json` sin cambios: sin `npm ci`. `SLICE_BASE` sigue en `f5f2503`.
  - `shared/lib/audit-labels.ts`: `AuditEntryView` gana `fields`, `phrase` y `purpose`; `actorLabel` acepta solo `actor_id` y `actor_name`; `PURPOSE_LABEL` (stub vacío).
  - `shared/ui/HistoryAside.tsx`: props `moreLabel` y `footer` (sin pintar todavía).
  - Tubería real (como en F1.1): `features/members/schemas.ts` (`HISTORY_ACTIONS`, `HISTORY_PURPOSES`, `memberHistoryItemSchema` estricto, `memberHistoryPageSchema`); `api.ts` (`useMemberHistory` con `useInfiniteQuery`, `limit` 25, `maxPages: 20`, `gcTime: 0`, sin releer al enfocar; `useMemberHistoryPreview` con `limit` 5; claves bajo `["members"]`); `memberLinks.ts` (`memberHistoryHref`); `routeTable.ts` (hija `/socios/:id/historial`, `members.history.view`, feature `members`, `load` de `MemberHistoryTab`) y `routes.reference.ts`.
  - Stubs: `memberErrors.ts` (`HISTORY_MESSAGES` y `historyError` que siempre da el genérico), `lib/historyPhrase.ts` (devuelve la acción), `lib/historyEntries.ts` (sin `fields` ni `phrase`), `components/MemberHistoryTab.tsx` (`null`). Fixture `src/test/history.tsx` (`historyItem`, `historyItems`, `manyHistoryItems`, `historyReply`, `historyCalls`, `renderMemberHistoryTab`, `PHONE_VALUE`, `DOCUMENT_VALUE`); `src/test/memberDetail.tsx` monta la hija Historial y responde `GET /members/{id}/audit` vacío por defecto.
- **F2.2 · Rojo** (`tsc` limpio): 59 fallaban de 149 en los 7 archivos.
  - `src/shared/lib/audit-labels.test.ts`: 7 de 33 (ENTITY_LABELS reales, `summarizeChange` con `fields`, `PURPOSE_LABEL`).
  - `src/shared/ui/HistoryAside.test.tsx`: 5 de 14 (frase fuerte, etiqueta de `purpose`, `moreLabel`, `footer`; el de HTML literal ya pasaba porque React escapa).
  - `src/features/members/lib/historyPhrase.test.ts`: 22 de 23 (todas las frases por acción y tabla y el mapeo de `historyEntries`; pasaba "ninguna frase contiene un valor").
  - `src/features/members/components/MemberHistoryTab.test.tsx`: 15 de 15.
  - `src/features/members/components/MemberDataTab.test.tsx` (E8: nace en este Rojo): 7 de 7.
  - `src/features/members/pages/MemberDetailPage.test.tsx`: 3 de 35 (pestañas con Historial habilitada y última; navegar a la hija; el coach la ve).
  - `src/routes.test.ts`: 0 de 22. La hija se registra en F2.1, como en F1. Se ajustaron cuatro aserciones: la lista con `load`, los hijos de la ficha (`:127`), las hijas con su acceso y la hija cuya feature no está habilitada. El oráculo `routes.reference.ts` se movió en el mismo paso.
  - E2E: `tests/e2e/stack/member-history.spec.ts` nuevo (alta por api con teléfono, PATCH del teléfono por api, caja de Datos con "editó teléfono" y su enlace, pestaña con "editó teléfono" antes de "creó el socio", sin ninguno de los dos números, axe en claro y oscuro, capturas). `member-tabs.spec.ts` (stack): al final, Historial es la última pestaña y cuenta la venta, los pagos y la anulación sin el motivo. `member-detail.spec.ts` (stack): tras editar, la caja muestra "editó teléfono" y "mostró el documento" sin el número; el coach abre Historial. `tests/e2e/member-tabs.spec.ts` (preview) simula `GET /members/{id}/audit` vacío.
- **F2.3 · Verde** (S4A-D32):
  - `audit-labels.ts`: `ENTITY_LABELS` con `members.members`, `memberships.memberships` y `payments.payments` (las viejas siguen); `FIELD_LABELS` con las columnas reales que salen en `fields` (`voided_at`, `voided_by`, `cancelled_at`, `cancelled_by`, `agreed_price_cop`, `registered_by`, `data_consent_at`...); `fieldNameLabel` (un nombre con `apx1.` se dice "campo cifrado"); `summarizeChange` sin `before` ni `after` y con `fields` da "Cambió: Teléfono, Correo" o, en un reveal, "Campo: Documento".
  - `HistoryAside.tsx`: con `phrase`, la frase es la línea fuerte y debajo va "entidad · hora" (la frase ya dice quién y qué; no se repite el resumen); con `purpose`, etiqueta "automático (aviso)"; `moreLabel` y `footer`. Todo texto de React.
  - `historyPhrase.ts`: "<quien> editó teléfono y correo", "creó el socio", "eliminó al socio", "mostró el documento" (y los otros cuatro campos con su artículo), "vendió una membresía", "anuló una membresía", "registró un pago", "anuló un pago", "modificó una membresía: vence y estado"; genérico "<quien> <acción> (<entidad>)". "Sistema" por `SYSTEM_USER_ID`; sin nombre, "Usuario".
  - `historyEntries.ts`: `toAuditEntryView` (`id` = `seq`, tabla completa, copia de `fields`, `purpose`, `phrase`) y `uniqueHistoryEntries` (sin `seq` repetidos al correrse el offset).
  - `MemberHistoryTab.tsx` (+ `.module.css`): HistoryAside "Historial" a todo el ancho; "Cargar más" hasta 20 páginas y aviso del tope ("Se muestran las 500 entradas más recientes. Las anteriores están en Auditoría (solo administradores)."); error inicial con "Reintentar"; fallo al cargar más con aviso, sin perder lo cargado.
  - `MemberDataTab.tsx` (+ css): cuadrícula flexible con la caja "Historial reciente" a la derecha (al final en el celular), 5 entradas, sin "Ver más", enlace "Ver historial completo →" (`--ink` con subrayado); su error no tumba la ficha.
  - `MemberDetailPage.tsx`: Historial sin `disabledUntil` y en `CHILD_TABS` (deshabilitada solo si la ruta no abre página para el rol).
  - `memberErrors.ts`: `historyError` (429 "Demasiadas consultas; espera un momento", 404, 403, 5xx, red y respuesta inválida).
  - Resultado: los 7 archivos, 149 de 149. Lectura amplia: `npx vitest run src/features/members src/shared/lib/audit-labels.test.ts src/shared/ui src/routes.test.ts tests/lint` 62 archivos y 1.068 pruebas; `src/features/{memberships,payments} src/core src/config src/layouts tests/unit tests/kit-inventory.test.ts src/dev src/App.test.tsx` 59 y 1.302. `npm run lint` y `npx tsc --noEmit` limpios. Preview `tests/e2e/member-tabs.spec.ts` 6 de 6.
- **F2.4 · Documentación:** `docs/design/ROUTES.md` con la hija `/socios/:id/historial` y la caja de Datos; la frase de pestañas deja de decir que Historial está deshabilitada.
- **DESIGN-GAP** (para `BRECHAS.md` §11):
  - `MemberHistoryTab.tsx`: `Socio_Ficha.html` no dibuja la pestaña Historial abierta (su enlace va a `Auditoria.html`, pantalla del admin); se usa HistoryAside a todo el ancho, sin filtros ni búsqueda (el api acepta `q` por usuario y la pantalla no la ofrece).
  - `MemberDataTab.tsx`: el diseño muestra "antes → después" enmascarado ("Cambió teléfono · 310 ••• 221 → 310 ••• 221"); el api no manda valores (S4A-D20), solo la frase. "Check-in" (v0.4) no existe todavía.
- **Desviaciones:**
  - La frase del job de vencimientos dice "Sistema marcó la membresía como vencida o por vencer" y no solo "como vencida": el historial no trae el valor nuevo y el recálculo (S4A-B2) también pasa a "por vencer". Contiene la frase del plan.
  - `childRoute` recibe la ruta completa `/socios/:id/historial` (convención de S3-F7) y no el segmento `historial` que escribe el paso 107.
  - La caja "Historial reciente" usa `useMemberHistoryPreview` (`useQuery`, `limit` 5) en vez de una página de `useMemberHistory`: la caja nunca carga más.
  - HistoryAside gana `moreLabel` y `footer` (no los listaba el plan) para "Cargar más" y el enlace de la caja; con `phrase` no repite el resumen "Cambió:" y la línea de abajo lleva la entidad en vez de quien actuó (ya está en la frase).
  - El enlace de la caja dice "Ver historial completo →" como `Socio_Ficha.html` (el plan escribe "historial completo →").
  - `historyPhrase.test.ts` cubre también `historyEntries` (el gate sellante solo lista ese archivo).
  - Nuevos fuera de la lista del plan: `MemberHistoryTab.module.css` y la ampliación de `tests/e2e/member-tabs.spec.ts` (preview).
- **Gates 1 y 2 de F2.5** (desde la raíz del worktree, `SLICE_BASE=f5f2503`, `ls` previo de cada archivo, con `src/test/setup.ts` y `src/test/vitest-axe.d.ts` en cada lista):
  1. `slice-gate.sh web/shared src/shared/lib/audit-labels.test.ts src/shared/ui/HistoryAside.test.tsx src/test/setup.ts src/test/vitest-axe.d.ts`: verde a la primera, 2 archivos y 47 pruebas.
  2. `slice-gate.sh web/app src/routes.test.ts tests/lint/boundaries.test.ts src/test/setup.ts src/test/vitest-axe.d.ts`: verde a la primera, 2 archivos y 27 pruebas.
  - El único aviso de eslint es de un archivo ignorado por configuración (`tests/lint/sensitive-mutations.test.ts`).
  - Lectura sin sello: `npx vitest run src/features/members tests/lint` 31 archivos y 662 pruebas. Los cuatro archivos del gate 3 suman 80 pruebas en verde. `npm run lint` y `npx tsc --noEmit` limpios.
- **Pendiente para el cierre de F2:** revisión de `security-reviewer` y sus correcciones; gate 3 sellante (`slice-gate.sh web/members src/features/members/components/MemberHistoryTab.test.tsx src/features/members/lib/historyPhrase.test.ts src/features/members/pages/MemberDetailPage.test.tsx src/features/members/components/MemberDataTab.test.tsx src/test/setup.ts src/test/vitest-axe.d.ts`); F2.6 (buildx de `apex-web:local`, `up -d --no-build web` y las tres specs del stack); F2.7, el checkpoint con el trailer.

### F2 · Revisión de seguridad

`security-reviewer`: 0 CRITICAL, 0 HIGH, 0 MEDIUM, 2 LOW. Los dos se corrigen en el slice, cada uno con prueba:
1. **LOW** `features/members/components/MemberHistoryTab.tsx`: con un `:id` sin forma de UUID la consulta queda deshabilitada (`enabled: isMemberId(id)`) y la pestaña mostraba "Cargando historial" sin fin. Ahora pinta `HISTORY_MESSAGES.notFound` sin petición ni "Reintentar" (`historyNotFoundError` en `memberErrors.ts`). Prueba en `MemberHistoryTab.test.tsx` ("un :id sin forma de UUID no pide nada…"; `renderMemberHistoryTab` acepta `entry`). Falla sin la corrección (comprobado y restaurado, sha256 idéntico).
2. **LOW** `shared/lib/audit-labels.ts`, `fieldNameLabel`: un nombre de campo desconocido se pintaba tal cual. Ahora: etiqueta de `FIELD_LABELS`; "campo cifrado" si contiene `apx1.`; el nombre si cumple `/^[a-z_]{1,40}$/`; si no, "campo". `summarizeChange` y `historyPhrase` usan la misma regla. Pruebas en `audit-labels.test.ts` (HTML, mayúsculas y tildes, punto y coma, 41 caracteres, vacío, dígitos y correo dan "campo"; el resumen con `fields` también); 8 fallaban antes de la corrección.
- Tras las correcciones: `npm run lint` y `npx tsc --noEmit` limpios; `npx vitest run tests/lint src/features/members src/shared` 81 archivos y 1.313 pruebas en verde. Gate 1 (`web/shared`) reejecutado: verde, 2 archivos y 57 pruebas. El gate 3 sellante va después de este bloque; su resultado, F2.6 y el checkpoint quedan en "Evidencia de S4A-F2".
- F2.6, primera corrida contra el stack (antes del sello definitivo): `member-history` 1 de 1, `member-detail` 1 de 1, `member-tabs` 0 de 1 por un defecto de la prueba. Cambiar de pestaña conserva la URL salvo `offset`, así que `?voided=false` de Pagos llega a `/socios/:id/historial?voided=false` y la expresión exigía `historial$`. Ahora admite la consulta (`historial(\?.*)?$`). Pagos no cambia y la pestaña Historial ignora ese parámetro. Por ese cambio el gate 3 se vuelve a correr como último comando que toca el árbol.

### Evidencia de S4A-F2 (después del sello)

- **Gate 3 (sellante):** `slice-gate.sh web/members src/features/members/components/MemberHistoryTab.test.tsx src/features/members/lib/historyPhrase.test.ts src/features/members/pages/MemberDetailPage.test.tsx src/features/members/components/MemberDataTab.test.tsx src/test/setup.ts src/test/vitest-axe.d.ts`: verde, 4 archivos y 81 pruebas.
  - Corrió dos veces. La primera quedó invalidada por la corrección de `member-tabs.spec.ts` (bloque anterior). La segunda fue el último comando que tocó el árbol antes del checkpoint.
  - El único aviso de eslint es de un archivo ignorado por configuración.
- **F2.6, imagen:** `apex-web:local` pasó de `sha256:62458b7264fb…` (2026-10-29T06:40Z) a `sha256:0dd855b6db9c…` (2026-10-29T07:10Z). Se construyó con buildx desde la raíz del worktree.
  - `up -d --no-build web` se lanzó desde el repo principal. `apex-web-1` quedó `healthy` con la imagen nueva; api, worker, db y db_test, `healthy`.
  - No hizo falta reconstruir tras la corrección de la spec: solo tocó una prueba.
- **E2E stack** con el admin desechable `admin-e2e-1793249495@apex.test`:
  - La contraseña se fijó con `tools issue-reset-link --as admin@ejemplo.local` y `POST /auth/reset` con `Origin: http://localhost:8180` (204, dos veces). Solo vivió en variables del comando y no está escrita en ningún archivo. El admin real no se tocó.
  - Las specs corrieron con `--workers=1` y una pausa de 65 s entre lotes, por el límite de login.
  - `member-history.spec.ts`: 1 de 1 en las dos corridas (1,7 s y 1,6 s). La caja de Datos muestra "… editó teléfono" con su enlace. La pestaña muestra "editó teléfono" antes de "creó el socio". Ninguno de los dos números ni `apx1.` aparece en el HTML. axe sin violaciones en claro y en oscuro.
  - `member-tabs.spec.ts`: 0 de 1 en la primera corrida (defecto de la prueba, corregido) y 1 de 1 tras el sello (4,4 s). La pestaña Historial es la última y muestra "vendió una membresía", dos "registró un pago", "anuló un pago" y "modificó una membresía: estado" sin el motivo de la anulación. axe sin violaciones.
  - `member-detail.spec.ts`: 1 de 1 (3,3 s). La caja de Datos muestra "editó teléfono" y "mostró el documento" sin el número. El coach desechable abre Historial sin ver el documento.
- **Contraste:** el axe de Playwright (wcag2a, wcag2aa y wcag21aa, con contraste) no dio violaciones en las frases, la etiqueta "automático (aviso)" (no apareció en estas corridas), la entidad y la hora en `--muted`, ni el enlace "Ver historial completo →". Probado en claro y oscuro a 1440 px, más una captura del celular a 390 px.
- **Capturas:** `ficha-historial-stack-light-1440`, `ficha-historial-socio-stack-{light,dark}-1440` y `ficha-historial-socio-stack-movil-light-390`. Quedan en `web/test-results/captures/`, que no entra al repo.
- **Observaciones:**
  - En una membresía vendida con abono y luego saldada, la pestaña muestra dos "modificó una membresía: estado" del admin. Son los cambios de estado que el api registra al pagar; el job del sistema no participó.
  - En la barra de pestañas a 1440 px, "Membresías" queda recortada a la izquierda cuando la activa es Historial. Es el desplazamiento horizontal del `Tabs` existente con nueve pestañas, no algo nuevo de F2.
- **Checkpoint:** `1ee7804` con el trailer `Co-Authored-By: Claude Fable 5.1`.
