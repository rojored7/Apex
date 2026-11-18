# Sprint 9 · front (cuaderno)

## S9-F1 · Pestaña Atleta, Resumen y Medidas

Rama `sprint-09-front` (worktree). US-178, US-179, US-184; H-1, L-7, E7. Dueño del Rojo: `frontend-qa-automation`.

### Rojo

**Stubs** (compilan, no hacen nada; los hooks y funciones lanzan `Error("S9-F1: no implementado")`, los componentes devuelven `null`):
- `web/src/features/athletes/{api.ts,schemas.ts,athleteErrors.ts}`, `tabs/AthleteTab.tsx` y `components/{SummaryCards,MetricsTab,MetricPanel,MetricField}.tsx`.
- `web/src/shared/data/athletes.ts` (`invalidateAthleteViews`), `formatWeightKg` en `shared/data/score.ts`, prop `variant?: "underline" | "pills"` en `shared/ui/Tabs.tsx` (sin efecto), `data_consent_at?: string | null` en `MemberTabMember` (`shared/data/members.ts`, H-1).
- Sin tocar (la prueba pide el cambio): `config/features.ts`, `config/routeTable.ts`, `core/auth/permissions.ts`, `MemberDetailPage.tsx`.

**Apoyo de pruebas**: `src/test/athletes.tsx` (fixtures `metric`, `summary`, `revealReply`, `renderAthlete`, `cacheText`), `src/test/memberTabs.tsx` (segmento `atleta`), `src/test/memberDetail.tsx` (hija `/socios/:id/atleta` en el router de prueba), `src/config/routes.reference.ts` (oráculo: Atleta pasa de ruta suelta a hija de `/socios/:id`).

**Spec E2E** (no ejecutada, la corre el orquestador): `web/tests/e2e/stack/athlete-profile.spec.ts` (2 casos: abrir ficha, pestaña Atleta, registrar peso 61,2, revelar y verlo; `?tab=medidas` sobrevive a recargar y ningún `/reveal` al abrir). Usa `crearSocio` (socio ficticio con autorización de datos) y `darDeBajaSocio` en `afterEach`; no crea coach, así que el guardián no exige `borrarUsuario`.

**Rojo medido** (`npx vitest run --pool=forks --maxWorkers=2`):

| Archivo | failed / passed | Motivo |
|---|---|---|
| `features/athletes/components/MetricField.test.tsx` (nuevo) | 25 / 0 | el stub devuelve `null`: no hay «•••», «—» ni botón «Mostrar …» |
| `features/athletes/components/MetricPanel.test.tsx` (nuevo) | 42 / 0 | sin diálogo «Registrar medidas» ni campos ni «Guardar medidas» |
| `features/athletes/components/MetricsTab.test.tsx` (nuevo) | 22 / 0 | sin tabla ni petición a `GET /athletes/{id}/metrics` |
| `features/athletes/components/SummaryCards.test.tsx` (nuevo) | 18 / 0 | sin tarjetas ni petición a `GET /athletes/{id}/summary` |
| `features/athletes/tabs/AthleteTab.test.tsx` (nuevo) | 19 / 0 | sin tablist «Secciones del atleta» ni «Registrar medidas» |
| `shared/ui/Tabs.test.tsx` (ampliado) | 2 / 26 | falta `data-variant` y la clase `.pills`; teclado y roles pasan porque no cambian |
| `shared/data/athletes.test.ts` (nuevo) | 2 / 0 | `invalidateAthleteViews` es stub; `invalidateResultViews` aún no la llama |
| `shared/data/score.test.ts` (ampliado) | 2 / 8 | `formatWeightKg` es stub |
| `config/features.test.ts` | 3 / 4 | `athletes` aún no está en `ENABLED_FEATURES` y la ruta no es hija |
| `core/auth/permissions.test.ts` | 1 / 147 | faltan `athletes.write` y `athletes.reveal` en la matriz |
| `core/auth/routeAccess.test.ts` | 1 / 173 | `/socios/42/atleta` aún no abre página |
| `layouts/nav.test.ts` | 2 / 14 | `athletes` no habilitada; la ruta no es hija de la ficha |
| `routes.test.ts` | 5 / 17 | la ruta de Atleta es suelta, sin `load`, y no es la última hija |
| `features/members/pages/MemberDetailPage.test.tsx` | 4 / 37 | la pestaña Atleta sigue «Disponible en v0.6» |

Total de los archivos de F1: 148 fallan (126 en archivos nuevos, 22 en casos nuevos o cambiados de archivos existentes), todos por el stub o por la funcionalidad ausente (ninguno por importación ni sintaxis). Suite completa del front: 4 704 pruebas en la corrida, 4 555 pasan; todas las que fallan son de la lista de arriba, salvo una corregida después (`tests/lint/no-direct-fetch.test.ts`, que vio `sessionStorage` en el apoyo `src/test/athletes.tsx`; se movió la ayuda a las pruebas y quedó en verde: 5/5).

**Comprobaciones**: `npx tsc --noEmit` exit 0; `npm run lint` (eslint + stylelint) exit 0; `tests/unit/e2e-stack-guard.test.ts` 16/16; `tests/lint/*` 8 archivos en verde.

### Contrato que fijan las pruebas (el Verde lo implementa)

- Textos del diseño: subpestañas «Resumen», «Medidas corporales», «RMs por movimiento», «Récords», «Benchmarks» (`<Tabs variant="pills" label="Secciones del atleta">`, `?tab=`, `resumen` por defecto); columnas «Fecha, Peso, Altura, % grasa, Notas, Registró»; tarjetas `<section>` con `<h2>`.
- `MetricField`: «•••» / «—», botón «Mostrar peso|altura|% grasa|notas» y «Ocultar …»; UN `POST .../reveal` con `{field}`; 60 s, `visibilitychange` a `hidden`, `pagehide`, desmontar; `gcTime: 0` y `reset()`.
- `MetricPanel`: fecha de hoy en Bogotá, «Peso (kg)» con un decimal (coma o punto) enviado en gramos, «Altura (cm)», «% grasa», «Notas»; exige al menos una medida numérica (como `validate_metric` del api); `422` bajo su campo; `409 consent_required` con mensaje y enlace «Ir a la ficha del socio» (`/socios/{id}`); `consentMissing` deshabilita «Guardar medidas».
- `MetricsTab`: «Anular medición del {fecha}» abre `ConfirmModal` sin motivo; `POST .../void` sin cuerpo; con el socio dado de baja no hay «Anular».
- Los mensajes exactos están en las pruebas (se pueden revisar con `grep -n "findByText\|toHaveTextContent" web/src/features/athletes -r`).

### Puntos que no cuadran con el código o el contrato

1. **H-1 sí se puede cumplir**: la ficha (`MemberDetailView`) trae `data_consent_at`; solo faltaba que `MemberTabMember` lo declarara (se agregó opcional en el Rojo) y que `MemberDetailPage` lo pase por el contexto (ya lo hace al entregar la ficha completa). Sin el dato (pestaña montada sola) decide el 409 del api.
2. **Notas sin medida**: el api (`validate_metric`) rechaza un registro que solo traiga notas («Registra al menos una medida: peso, estatura o grasa»); la prueba lo exige también en el cliente.
3. **«Altura» y «% grasa»** son los rótulos del diseño; US-178 dice «estatura». Se siguió el diseño.
4. La ruta `/socios/:id/atleta` estaba como ruta suelta sin `load` en `routeTable.ts`; F1 debe convertirla en `childRoute(MEMBER_DETAIL, …)` con `load` (las pruebas de `routes.test.ts`, `features.test.ts` y `nav.test.ts` lo exigen). El oráculo `routes.reference.ts` ya quedó así.
5. RMs, Récords y Benchmarks: F1 solo exige que las tres subpestañas existan; su contenido es de F2 y F3.

### Verde

**Archivos nuevos** (web/src): `features/athletes/{api.ts,schemas.ts,athleteErrors.ts,recordFormat.ts}`, `features/athletes/tabs/{AthleteTab.tsx,AthleteTab.module.css}`, `features/athletes/components/{SummaryCards,MetricsTab,MetricPanel,MetricField}.tsx` y sus `.module.css`; `shared/data/athletes.ts` (`invalidateAthleteViews`, `ATHLETE_VIEW_KEYS`).
**Modificados**: `config/routeTable.ts` (Atleta pasa a `childRoute(MEMBER_DETAIL, ...)` con `load` diferido, feature `athletes`, acceso `athletes.view`, última hija tras Resultados), `config/features.ts` (`athletes` habilitada), `core/auth/permissions.ts` (`athletes.write` y `athletes.reveal` para admin y coach), `core/api/errorCodes.ts` (`metric_voided`, `metric_already_voided`; existen en `api/src/.../athletes/exceptions.py`), `features/members/pages/MemberDetailPage.tsx` (sin `disabledUntil`, `atleta` en `CHILD_TABS`), `shared/ui/Tabs.tsx` y `Tabs.module.css` (`variant="pills"`, `data-variant`, clase `.pills` solo con tokens), `dev/Catalog.tsx`, `docs/design/DESIGN.md` (E7), `shared/data/score.ts` (`formatWeightKg`), `shared/data/results.ts` (`invalidateResultViews` llama a `invalidateAthleteViews`).

**Decisiones**: MetricField no reutiliza MaskedValue (su botón se llama «Mostrar», las pruebas piden «Mostrar peso»); copia su lógica (60 s, visibilitychange, pagehide, respuesta con pestaña oculta) con `REVEAL_TTL_MS` compartido, y el claro vive solo en el estado local ya formateado. El reveal usa `useSensitiveMutation` (gcTime 0 y reset). El formulario del panel solo existe mientras el panel está abierto (se desmonta al cerrar o guardar): nada queda para la próxima apertura. El `reveal` del coach con socio de baja: el api da 403 (S9-D34) y la pantalla lo explica; en el front `athletes.reveal` sigue siendo de admin y coach.

**Errores evidentes de las pruebas corregidos** (sin tocar su intención):
1. `MetricsTab.test.tsx` y `SummaryCards.test.tsx`: esperaban «1 sep 2026» y «4 sep 2026»; el formateador del front (`MONTHS_SHORT`, usado por toda la app) dice «sept». Se cambiaron a «sept».
2. `src/test/athletes.tsx`: el marcador de URL `where` era un `<output>` (rol implícito «status») y chocaba con `getByRole("status")` de «Cargando el resumen…»; ahora es un `<span>`.
3. «mientras guarda, el botón no permite un segundo envío» vuelve a buscar «Guardar medidas» durante el envío: el botón conserva su rótulo y solo marca `aria-busy` (sin «Guardando…»). `ConfirmModal` de Anular usa `cancelLabel="Cancelar"` (la prueba lo busca así).

**Resultado** (desde `web/`): suite completa `npx vitest run --pool=forks --maxWorkers=2`: 267 archivos, 4 712 pruebas (la corrida anterior al Verde: 4 704 con 148 en rojo; ahora 0 en rojo); `npx tsc --noEmit` exit 0; `npm run lint` exit 0; `npm run build` exit 0; `tests/unit/e2e-stack-guard.test.ts` verde (la spec no crea coach). Gates no sellantes (raíz del worktree): `slice-gate.sh web/shared src/shared/ui/Tabs.test.tsx` exit 0; `web/members src/features/members/pages/MemberDetailPage.test.tsx` exit 0; `web/app` exit 0. Sin correr: el gate sellante `web/athletes`, checkpoint, Docker y Playwright (los hace el orquestador).

**DESIGN-GAP** (comentados en código): valores en claro en la tabla (S9-D16: solo «•••» y «Mostrar»), gráfica de peso y selector de serie, columna y campo «Cintura», medidas configurables, «Exportar progreso», «Laura (portal)», «Registrar RM» (F2). RMs, Récords y Benchmarks son solo subpestañas con el texto «Esta sección llega en la siguiente entrega del perfil del atleta.» (contenido en F2 y F3).

**Desviaciones del plan**: ninguna de alcance. `athleteErrors.ts` trae además `summaryError`, `metricsListError`, `fieldErrorOf`, `isConsentRequired`, `revealMetricError` y `voidMetricError`; `recordFormat.ts` queda listo para F2.

### Revisiones

Rojo medido de la tanda (antes de corregir): 9 pruebas nuevas fallaban en el front (Tabs 1, AthleteTab 1, MetricField 6, MetricsTab 1) y `useTimedReveal.test.tsx` no cargaba (el hook no existía); luego todo en verde.

| Hallazgo | Rojo medido | Arreglo |
|---|---|---|
| M1 404 de «Anular» dice «Actualizamos la lista» | MetricsTab: 404 no releía la lista (falló); 429 pasó (solo fija el mensaje) | `useVoidMetric` invalida también con 404 |
| M2 aria-live del valor | MetricField: sin `aria-live` (falló) | el span del valor lleva `aria-live="polite"` |
| M3 aviso al guardar | AthleteTab: no había «Medidas guardadas.» (falló) | `role="status"` sin ningún valor; se borra al abrir el panel otra vez |
| L4 chip «Anulada» y rama voided | sin prueba (código inalcanzable) | quitados chip, rama y la clase `.voided` (con su `2px` literal) |
| L5 `?tab=` arrastrado a otras hijas | Tabs: falló | modo segment borra `param` además de `offset`; el resto de la query se conserva |
| L6+L7+seg. L1/L2 hook compartido | `useTimedReveal.test.tsx` (9 pruebas: plazo, hidden, pagehide síncrono con flushSync, pageshow persistido, vencido al volver por visibilitychange, pageshow o focus) | `shared/hooks/useTimedReveal.ts` con `expiresAt`; lo usan MaskedValue (sus pruebas siguen verdes, sin cambio visible) y MetricField; `REVEAL_TTL_MS` vive en el hook y MaskedValue lo reexporta |
| L8 kg | sin cambio de conducta (pruebas del panel ya cubrían) | `weightInputToGrams` usa `kgInputToGrams`; valida aparte un decimal y 20 a 400 kg |
| L9 `as` y 2px | prueba nueva de `isScoreKind` | `SCORE_KINDS` e `isScoreKind` en `shared/data/score.ts`; sin `as` en recordFormat |
| Hueco: reveal en vuelo al desmontar | MetricField: la señal no existía (falló) | ver seg. L3 |
| Hueco: cambio de socio con la pestaña abierta | pasó sin cambios (las filas llevan key por id) | se deja la prueba y `key={memberId}` en AthleteTab, que descarta claros, panel y aviso |
| Seg. L3 cancelar POST al desmontar | MetricField falló (`signal.aborted` false) | `useRevealMetric` recibe `signal` (api.post ya lo aceptaba); MetricField aborta al desmontar |
| Seg. L4 validar respuesta del reveal | 4 pruebas fallaron (campo distinto, peso texto, peso no entero, notas número) | `isRevealValueFor` + `reply.field === field`; si no, `invalidResponseError()` |
| Seg. L5 consentMissing en save() | pasó sin cambios (el botón deshabilitado ya frena el Enter) | guardia `if (consentMissing === true) return;` como defensa en profundidad; la prueba queda |
| Menor: `darDeBajaSocio` | sin prueba (E2E) | comprueba `response.ok()` y lanza; `tsc` compila las demás specs. Riesgo: una spec que ya dio de baja al socio ahora lanzaría en el afterEach (404) |

**No corregido, para decisión**: L6 (subir la mutación del reveal a MetricsTab y pasar `onReveal` a MetricField). Las pruebas del Rojo montan `<MetricField memberId metricId field has />` sin `onReveal` y esperan el POST, así que el componente debe seguir trayendo su propio hook; subirlo exigiría cambiar esas pruebas. El costo real es un observador de mutación por celda con valor (hasta 400 con limit=100), sin llamadas ni estado extra mientras nadie pulsa «Mostrar»; `useRevealMetric` ya está aislado, así que el cambio es pequeño si se decide.

**Verificación**: suite completa 268 archivos, 4 734 pruebas; en una corrida bajo carga falló una vez `system/api.test.tsx` (la misma que ya falló aislada en una corrida anterior del Verde, ajena a este slice) y pasa al correrla sola; `tsc`, `lint` y `build` exit 0; `e2e-stack-guard` verde; gates no sellantes `web/shared`, `web/members` y `web/app` exit 0.

### E2E (orquestador)

**Rojo E2E (orquestador, P-E2E con `pe2e.sh`, stack en `61807fc` con la pestaña Atleta deshabilitada):** `athlete-profile.spec.ts` 2 failed, exit 1. Caso 1: timeout de 30 s esperando la pestaña Atleta habilitada. Caso 2: `getByRole('tab', { name: 'Medidas corporales' })` no existe. Motivo correcto: la ruta y la pestaña aún no existen en la imagen. `.env` restaurado (cmp OK), api y web recreados sin el overlay.
**Verde E2E (orquestador):** P-REBUILD 3 desde el worktree (`apex-web:local` con `GIT_SHA=61807fc-f1`, build exit 0). P-E2E, `athlete-profile.spec.ts`: corrida 1, 2 passed (3,2 s); corrida 2, 2 passed (3,8 s); exit 0 las dos. `.env` restaurado (cmp OK), api y web recreados sin el overlay.
- `darDeBajaSocio` más estricto: ninguna de las 10 specs que lo usan da de baja al socio antes de su limpieza (un `DELETE` repetido daría 409 `member_already_deactivated`).
- `src/features/system/api.test.tsx` falló una vez en una corrida completa con carga; solo pasa 3 de 3 y el slice no toca `features/system`. Se vigila en P-GATES.
- L6 aceptado: S9-D67.

### Sello y evidencia

- Gate sellante `slice-gate.sh web/athletes` (5 archivos): 137 passed, exit 0. No sellantes del Verde (`web/shared`, `web/members`, `web/app`): exit 0.
- E2E final tras las revisiones: P-REBUILD 3 desde el worktree (build exit 0) y P-E2E de `athlete-profile.spec.ts`: corrida 1, 2 passed (3,1 s); corrida 2, 2 passed (3,6 s); `.env` restaurado.
- Checkpoint `3474ab4`.

## S9-F2 · RMs y Récords

Rama `sprint-09-front` (worktree). US-180, US-181, US-182; L-4, E8. Dueño del Rojo: `frontend-qa-automation`.

### Rojo

**Stubs** (compilan; hooks y funciones lanzan `Error("S9-F2: no implementado")`, componentes devuelven `null`):
- `web/src/features/athletes/components/{RmsTab,RecordsTab,RecordPanel}.tsx`; `useRms`, `useRecords`, `useAddRecord`, `useInvalidateRecord` en `features/athletes/api.ts`; tipos `RmView`, `RecordView`, `RecordCreate` en `schemas.ts`.
- `web/src/shared/data/catalog.ts` (`useMovements`, `useBenchmarks`, `useKgMovementOptions`, `useBenchmarkOptions`; las dos claves `MOVEMENTS_QUERY_KEY` y `BENCHMARKS_QUERY_KEY` ya valen); `formatScoreDelta` en `shared/data/score.ts`.
- Sin tocar (la prueba pide el cambio): `features/wods/*`, `AthleteTab.tsx` (subpestañas RMs y Récords, «+ Registrar récord»).

**Apoyo de pruebas**: `src/test/athletes.tsx` (fixtures `rm`, `record`, `derivedRm`, `derivedBenchmark`, catálogo `CATALOG_MOVEMENTS`/`CATALOG_BENCHMARKS` y sus handlers, rutas).

**Spec E2E** (no ejecutada): `web/tests/e2e/stack/athlete-records.spec.ts`; solo admin (sin coach: no hay `borrarUsuario`), socio con `darDeBajaSocio`. Clase de hoy + WOD por carga + `PUT /results` de 100 kg; ve el RM en RMs y Récords; corrige a 90 kg con `supersedes_id` y ve el de 100 kg invalidado («Resultado corregido»).

### Contrato que fijan las pruebas (el Verde lo implementa)

- Subpestañas: tablas «RMs por movimiento del socio» (Movimiento, 1RM, Último cambio, Origen) y «Récords del socio» (Fecha, Récord, Valor, Origen, Estado, Acciones); `h2` «RMs por movimiento» y «Récords».
- Origen: «Manual · {quien}», «Automático del WOD», «Automático (tablet)» (solo `RecordOut.result_source === "kiosk"`; `RmOut` no lo trae).
- Récords: chips grupo «Tipo de récord» (`RMs`, `Benchmarks`; URL `kind=rm|benchmark`) y grupo «Estado del récord» (`Ver invalidados`; URL `invalidated=1`; pide `include_invalidated=true`). Estado: «Vigente», «Histórico», «Invalidado» + «Error de digitación» / «Resultado corregido» / «Resultado anulado».
- Derivado: enlace «Ver el WOD de {título}» a `/wods/{wod_id}` y «Se corrige corrigiendo el resultado que lo originó.»; «Invalidar {título} del {fecha}» solo en manual vivo (sin baja del socio); ConfirmModal «¿Invalidar este récord?» / «Invalidar récord» / «Cancelar», sin motivo, POST sin cuerpo.
- `AthleteTab`: «+ Registrar récord» (athletes.write, socio vivo, sin exigir autorización de datos) abre `RecordPanel` («Registrar récord», «Guardar récord»); aviso `role=status` «Récord guardado.»; Benchmarks sigue con el aviso de F3.
- `RecordPanel`: `Segmented` «Tipo de récord» (RM, Benchmark), select «Movimiento» (activos en kg), «Carga (kg)» (0,01 a 1.000, gramos enteros), «Fecha del récord»; Benchmark: select «Benchmark», `Segmented` «Nivel» (RX por omisión) y el campo del `score_type` (Tiempo mm:ss, Rondas + Repeticiones, Repeticiones, Carga); sin «No terminó»; 422 bajo su campo; 409 `record_duplicate`.
- `catalog.ts`: `useKgMovementOptions` pide `limit=200&offset=0&active=true` y deja unit kg activos como `{value,label}`; `useBenchmarkOptions` pide `limit=200&offset=0` y da `{value,label,scoreType}`.
- `formatScoreDelta(tipo, actual, previa)`: «−0:28», «+1:05», «+5 reps», «+2,5 kg», «Sin cambio», `null` para rondas+reps, DNF o datos que faltan.

### Puntos que no cuadran con el plan o el contrato

1. `RmOut` no trae `result_source`: «Automático (tablet)» solo se puede decir en Récords; la prueba de RmsTab fija que no se escribe ahí.
2. `parseClock`/`formatClock` viven en `features/results/schemas.ts`: el panel (feature `athletes`) necesita una copia en `shared/data/score.ts`.
3. El plan no dice dónde está «Registrar récord»; se puso en `AthleteTab` junto a «Registrar medidas» (como el diseño).
4. La prueba de `features/wods` usa `vi.mock` del módulo compartido (WodFormPage.catalog.test.tsx): fija que la página lee de `shared/data/catalog`, sin mirar su implementación.

### Verde

**Archivos**: nuevos `features/athletes/recordErrors.ts`, `components/RecordsTab.module.css`; implementados `components/{RmsTab,RecordsTab,RecordPanel}.tsx`, `shared/data/catalog.ts`; modificados `features/athletes/{api,schemas}.ts` (useRms, useRecords, useAddRecord, useInvalidateRecord; rmSchema, recordSchema, recordFormSchema, parseRecordForm; `RecordView` pasa a `z.infer` porque `result_source` opcional choca con exactOptionalPropertyTypes), `tabs/AthleteTab.tsx` («+ Registrar récord», aviso «Récord guardado.», subpestañas RMs y Récords), `shared/data/score.ts` (`formatScoreDelta`; `parseClock` y `formatClock` movidos aquí), `features/results/schemas.ts` (importa de shared), `features/wods/{api.ts,components/BenchmarksList.tsx,components/MovementsList.tsx,pages/WodFormPage.tsx}` (lecturas y claves salen de `shared/data/catalog`; wods conserva solo escrituras y tipos de filtros).

**Decisiones**: «Automático del WOD» en RMs y «Automático (tablet)» solo en Récords (`RecordOut.result_source === "kiosk"`). Cargas en gramos con `kgInputToGrams` y tope > 0 (`recordLoadToGrams`). El formulario guarda el `score_type` del benchmark elegido en un valor del formulario para un solo esquema Zod. Las claves de las opciones cuelgan de `["movements"]` y `["benchmarks"]`.

**DESIGN-GAP** (comentados en código): 3RM, 5RM, «máx. reps», unidad preferida, «editar» un récord, «Exportar progreso», «Laura (portal)».

**Arreglo visual (LOW de la preview 5a)**: en `MetricsTab` las celdas de texto (Fecha, Registró) ocupan ahora la misma franja de alto que las de `MetricField` (`.cell`: flex, `align-items: center`, `min-height: var(--control)`), así el «•••» del peso queda alineado con la fecha. Solo CSS con tokens. Sin prueba (jsdom no calcula layout ni los módulos CSS dan estilos); queda para la preview del orquestador.

**Errores de pruebas corregidos**: ninguno.

**Resultado** (desde `web/`): suite completa `npx vitest run --pool=forks --maxWorkers=2`: 273 archivos, 4 878 pruebas, 0 en rojo (antes del Verde 142 en rojo); `npm run lint` exit 0; `npx tsc --noEmit` exit 0; `npm run build` exit 0; `tests/unit/e2e-stack-guard.test.ts` 16 verdes. Gates no sellantes (raíz del worktree): `web/shared src/shared/data/catalog.test.ts src/shared/data/score.test.ts`, `web/wods` y `web/results` exit 0. Sin correr: gate sellante `web/athletes`, checkpoint, Docker y Playwright.

### Revisiones

Rojo medido antes de corregir: 18 pruebas nuevas en rojo (7 archivos); las de 429 de Récords y la carrera de chips pasaron sin cambios (cubren comportamiento ya correcto, se dejan).

| Hallazgo | Rojo medido | Arreglo |
|---|---|---|
| M1 esquemas duplicados | `catalog.test.ts` (wods y catalog no compartían esquema) | `catalog.ts` exporta `movementSchema`, `benchmarkSchema` y las constantes; `wods/schemas.ts` las reexporta y `wods/api.ts` usa `MovementsParams = CatalogMovementsParams` (idem benchmarks) |
| M2 opciones de una sola página | 3 pruebas (450 en 3 páginas, 1.500 corta en 5 con aviso, `refetch`) | `collectPages` pide de a 200 hasta `total` con tope `OPTIONS_MAX_PAGES = 5`; las opciones devuelven `CatalogOptions` con `truncated` y `refetch`; el panel avisa con texto visible |
| M3 «Reintentar» del catálogo | 2 pruebas del panel | `CatalogNotice` con «Reintentar» (`refetch()`) en RM y en Benchmark |
| M4 `?? 0` y score_type desconocido | 6 pruebas (`schemas.record.test.ts`) | `benchmarkMark` (time, rounds_reps, reps, load); desconocido da «Elige el benchmark otra vez.» bajo `benchmark_id`; `parseRecordForm` lanza con `validated()` en lugar de fabricar un 0 |
| M5 foco tras invalidar | 1 prueba | el encabezado «Récords» (`tabIndex=-1`) recibe el foco al cerrar el modal con éxito (ref + efecto sobre `invalidating`) |
| L6 `moviesFailed` | n/a (nombre) | `movementsFailed` |
| L7 handlers del chip | n/a (estructura) | `changeKind` y `changeInvalidated` |
| L8 CSS del panel | n/a | `AthletePanel.module.css` (antes `MetricPanel.module.css`) lo usan los dos paneles |
| L9 `score_type` | 1 prueba | `recordSchema.score_type` es `z.enum(SCORE_KINDS).nullable()`; el api declara `str` pero solo emite time, rounds_reps, reps y load (derivados de `benchmarks.score_type` y de WOD con marca); un valor ajeno ahora da `invalid_response` |
| seg. L3 member null | 1 prueba | `memberDeleted = member === null \|\| deleted_at !== null` (sin acciones) |
| seg. L4 invalidación acotada | 2 pruebas (`invalidateRecordViews` y RecordsTab) | `invalidateRecordViews(queryClient, memberId)` (resumen, RMs, récords y benchmarks del socio); `useAddRecord` y `useInvalidateRecord` la usan; medidas y otros socios no se releen |
| seg. L5 `kind`/`invalidated` arrastrados | 1 prueba (Tabs) | `Tabs` acepta `ownParams` (parámetros propios de la subpestaña que se borran al cambiar, en modo query y segmento); AthleteTab pasa `kind`, `invalidated` y `benchmark` |
| 13 `RecordPanelForm` largo | n/a | partido en `RmFields`, `BenchmarkFields`, `MarkFields` y `CatalogNotice` |

**Pruebas añadidas sin cambio de comportamiento**: 429 de la lista de Récords y la carrera al cambiar de chip con la respuesta anterior en vuelo (pasaron de inmediato).

**E2E** (`athlete-records.spec.ts`, conserva la clase a +10 min con corte 23:49 del orquestador): la limpieza cancela la clase (`POST /class-sessions/{id}/cancel`, tolerante); crea un movimiento kg ficticio si no hay uno activo; segundo caso: registrar un récord manual por el panel y luego invalidarlo con el ConfirmModal, comprobando «Invalidado» con «Ver invalidados». No ejecutada (la corre el orquestador); `tsc` y el guardián en verde.

**No corregido**: nada.

**Verificación de las revisiones** (desde `web/`): suite completa 274 archivos, 4 905 pruebas, 0 en rojo; `npm run lint`, `npx tsc --noEmit` y `npm run build` exit 0; guardián `e2e-stack-guard` 16 verdes; gates no sellantes `web/shared` (catalog y score), `web/wods` y `web/results` exit 0.

### E2E (orquestador)

**Ajuste del orquestador a la spec:** la clase de hoy pasaba a +2 h y la prueba se omitía después de las 21:00 de Bogotá (se omitió a las 22:16, 0 casos). El check-in no bloquea por hora (N-38, solo banderas), así que la clase empieza a +10 min y el corte pasa a las 23:49.
**Rojo E2E (orquestador, P-E2E, imagen web con F1 sin F2):** `athlete-records.spec.ts` 1 failed, exit 1: no existe la tabla «RMs por movimiento del socio» (motivo correcto). `.env` restaurado. Dejó viva una clase «Récords E2E …» de hoy (la spec no la cancelaba; hallazgo L-2 de seguridad). Tiene resultado, así que no se puede cancelar (409 `locked_by_results`, por diseño): termina sola.
**Verde E2E:** P-REBUILD 3 desde el worktree (build exit 0). Primera corrida doble: corrida 1, 2 passed; corrida 2, el caso del derivado falló en `POST /class-sessions` (409 `session_duplicate`). Causa: la clase de la corrida 1 tiene resultados, no se puede cancelar (409 `locked_by_results`, por diseño) y sigue «programada» en el mismo minuto. Arreglo del orquestador en la spec: `crearClaseDeHoy` prueba el minuto siguiente ante `session_duplicate` (hasta 5), y cualquier otro error falla. Después, corrida 1: 2 passed (4,4 s); corrida 2: 2 passed (4,5 s); exit 0 las dos.
**Regresión sobre la imagen de F2:** `athlete-profile.spec.ts` y `kiosk-idle.spec.ts`: 4 passed. `.env` restaurado en cada corrida.
**Datos que quedan en desarrollo (ficticios):** clases «Récords E2E …» de hoy con su resultado (no se cancelan por diseño; terminan solas), WODs de 2033, socios ficticios dados de baja, y el récord manual invalidado del caso 2.

### Sello y evidencia

- Gate sellante `slice-gate.sh web/athletes` (RmsTab, RecordsTab, RecordPanel): 119 passed, exit 0. No sellantes del Verde (`web/shared`, `web/wods`, `web/results`): exit 0.
- Checkpoint `2a1c1f0`.

## S9-F3 · Benchmarks

US-183. Subpestaña «Benchmarks» de Atleta con la serie del socio y `TrendChart` compartido. Dueño del Rojo: `frontend-qa-automation`.

### Rojo

**Stubs** (compilan): `features/athletes/components/BenchmarksTab.tsx` y `shared/ui/TrendChart.tsx` devuelven `null` (este último exportado en `shared/ui/index.ts` con `TrendPoint` y `TrendChartProps`); hooks `useAthleteBenchmarks(memberId, {limit, offset})` y `useBenchmarkSeries(memberId, benchmarkId)` en `features/athletes/api.ts` lanzan `Error("S9-F3: no implementado ...")`; tipos `BenchmarkRowView`, `BenchmarkSeriesView`, `AttemptView` en `schemas.ts`. Sin tocar (lo pide la prueba): `AthleteTab.tsx`, `dev/Catalog.tsx` (`KIT_COMPONENTS`), CSS de `TrendChart`.

**Contrato que fijan las pruebas (decisiones del Rojo para el Verde)**
- Lista: `GET /athletes/{id}/benchmarks?limit=200&offset=0` (el api pagina; la pantalla pide el máximo, avisa «Se muestran los primeros 200 benchmarks.» si `total > 200` y no pinta paginación). Chips en el grupo «Benchmark», `?benchmark=<benchmark_id>`; sin valor o con uno que no está en la lista vale el primero (sin escribir la URL). Claves de consulta `["athlete-benchmarks", id, ...]` (las relee `invalidateRecordViews`).
- Serie: `GET /athletes/{id}/benchmarks/{benchmark_id}`; tabla «Intentos del socio en <nombre>» con Fecha, Marca, Nivel y Diferencia (orden del api, ascendente). «Mejor» en texto en la marca del `is_best`. Diferencia: «Primera vez» (el primero), «Cambió de nivel» si `level_changed` (sin número), `formatScoreDelta` en los demás, «—» si no se puede (rondas + repeticiones, DNF). Notas: «Solo se compara entre intentos del mismo nivel.» y, con `truncated`, «Se muestran los 200 intentos más recientes.». DESIGN-GAP: columna «Escaló».
- Vacíos: «Sin intentos en benchmarks» (lista) y «Este socio todavía no tiene intentos validados en <nombre>.» (serie).
- Errores (textos nuevos): lista 403 «No tienes permiso para ver los benchmarks de este socio.», 404 y 429 con los textos de `RECORD_ERROR_MESSAGES` (`memberGone`, `tooManyReads`), 5xx «No pudimos cargar los benchmarks. Intenta de nuevo en un momento.»; serie 404 `benchmark_not_found` «Este benchmark ya no está en el catálogo. Elige otro.», 403 igual que la lista, 5xx «No pudimos cargar la serie de este benchmark. Intenta de nuevo en un momento.»; los 5xx con Reintentar.
- `TrendChart({title, points: {id,label,value,text,isBest?}[], emptyMessage?})`: `<svg role="img">` con `aria-label` «<título>: N puntos. <label>: <texto>; ... (mejor)» («1 punto»), un `circle` por punto, el mejor con `data-best="true"` y radio mayor, `polyline` si hay 2 o más, sin puntos `<p>` «Sin datos para graficar.»; `TrendChart.module.css` solo con `var(--…)`. Catálogo de 17 a 18 componentes, con sección «TrendChart» (gráfica y vacío).

**Apoyo de pruebas**: `src/test/athletes.tsx` (`BENCHMARKS_PATH`, `seriesPath`, `benchmarkRow`, `attempt`, `seriesOf`, `FRAN_ROW`, `FRAN_ATTEMPTS`, `FRAN_SERIES`, `HELEN_ROW`, `HELEN_SERIES`).

**E2E** (no ejecutada): `athlete-profile.spec.ts` suma un caso: WOD «Fran» (`benchmark_id` de Fran, por tiempo) en un día libre de 2033, clase de hoy a +10 min (corte 23:49, tolerante a `session_duplicate`), asistencia y `PUT /results` de 245 s; `?tab=benchmarks` muestra chip «Fran» activo, tabla con 4:05 «Mejor» RX y la gráfica «Fran: 1 punto»; limpieza: baja del socio y cancelar la clase (tolerante, con resultados no se puede, S9-D68). Requiere `seed-benchmarks` aplicado.

**Rojo medido** (`npx vitest run --pool=forks --maxWorkers=2`):

| Archivo | failed / passed | Motivo |
|---|---|---|
| `features/athletes/components/BenchmarksTab.test.tsx` (nuevo) | 37 / 0 | el stub devuelve `null`: sin chips, tabla ni peticiones |
| `shared/ui/TrendChart.test.tsx` (nuevo) | 8 / 1 | stub `null`: sin SVG ni mensaje; falta `TrendChart.module.css`. Pasa «el componente no tiene colores literales» (trivial con el stub) |
| `dev/Catalog.test.tsx` (ampliado) | 2 / 7 | `KIT_COMPONENTS` sigue en 17 y no hay región «TrendChart» |
| `features/athletes/tabs/AthleteTab.test.tsx` (caso cambiado) | 1 / resto verde | la subpestaña Benchmarks aún muestra «llega en la siguiente entrega» |

Total 48 en rojo, 0 por importación ni sintaxis. Suite completa: 276 archivos, 4 953 pruebas, 4 905 pasan; los únicos 48 que fallan son los de arriba.
**Comprobaciones**: `npx tsc --noEmit` exit 0; `npm run lint` exit 0; `tests/unit/e2e-stack-guard.test.ts` en verde.

### Verde

**Archivos**: `shared/ui/TrendChart.tsx` y `.module.css` (SVG, `role="img"`, mejor punto con radio mayor y `data-best`, `polyline` desde 2 puntos, solo `var(--…)`); `features/athletes/components/BenchmarksTab.tsx` y `.module.css`; `api.ts` (`useAthleteBenchmarks` pide páginas de 200 hasta 5 como `shared/data/catalog.ts`, sin repetir benchmarks; `useBenchmarkSeries`; claves `["athlete-benchmarks", id, "list"|"series", ...]`); `schemas.ts` (esquemas Zod de fila, intento y serie); `recordErrors.ts` (`benchmarksListError`, `benchmarkSeriesError`: 404 `member_not_found` distinto de `benchmark_not_found`); `AthleteTab.tsx` (Benchmarks pinta `BenchmarksTab`; se quitó `COMING_SOON` y su CSS `.soon`); `dev/Catalog.tsx` (18 componentes, sección TrendChart); `docs/design/DESIGN.md` (entrada TrendChart).

**Decisiones**: la tabla va del más reciente al más antiguo (como el HTML del diseño), la gráfica en orden cronológico y la «Diferencia» contra el intento anterior en el tiempo (se ordena por `wod_date` antes de calcular). Mientras carga la serie, la tabla de esqueleto se llama «Cargando los intentos del socio en X» para que nunca se confunda con la tabla con datos. Sin `placeholderData`: al cambiar de chip no se mezclan series. Solo lectura (no hay acciones, vale igual con socio nulo o de baja). Los errores usan textos fijos. La gráfica omite intentos sin marca graficable; rondas + repeticiones se dibuja como rondas×1000 + reps.

**Errores de pruebas corregidos (con motivo)**
- `BenchmarksTab.test.tsx` «lista los cinco intentos…»: fijaba orden ascendente en la tabla; decisión del orquestador (el diseño manda): ahora descendente.
- «más de 200 benchmarks»: por la coherencia con F2 (M2) se piden más páginas hasta 1.000; el aviso pasa a «Se muestran los primeros 1.000 benchmarks.» con total 1230. Prueba nueva: con 230 se pide `offset=200` y no hay aviso.

**DESIGN-GAP** (comentados en código): columna «Escaló» y «solo se compara entre el mismo nivel» (va como nota); selector `<select>` del diseño frente a chips del plan.

**Resultado** (desde `web/`): suite completa `npx vitest run --pool=forks --maxWorkers=2`: 276 archivos, 4 955 pruebas, 0 en rojo (antes del Verde 48 en rojo; +2 pruebas netas por la segunda página y el tope de la lista); `npm run lint` exit 0; `npx tsc --noEmit` exit 0; `npm run build` exit 0; `tests/unit/e2e-stack-guard.test.ts` 16 verdes. Sin correr: gate sellante `web/athletes`, checkpoint, Docker y Playwright.

### Revisiones

Rojo medido antes de corregir (`npx vitest run` de `features/athletes`, `shared/ui` y `dev`): 25 en rojo en 4 archivos. Pasaron de inmediato, y se dejan como caracterización, las de misma fecha, orden no ascendente, empate, `rx_plus`, `score_type` desconocido, 429, 404 `member_not_found`, la comparación del cambio de socio y las de sentido «mayor es mejor» por omisión. Una prueba mía del sentido vertical estaba al revés (índices) y se corrigió antes del Verde.

| Hallazgo | Rojo medido | Arreglo |
|---|---|---|
| M1 «Primera vez» con serie truncada | 1 prueba | `deltaText`/`chronology` reciben `truncated`; el más antiguo mostrado dice «—» |
| M2 sentido vertical | 2 pruebas (con `lowerIsBetter` y comentario falso) | `TrendChart` acepta `lowerIsBetter` y calcula mínimo y máximo con `reduce`; `BenchmarksTab` lo pasa para `time` (el mejor punto queda arriba en tiempo y en carga) |
| M3 etiquetas y radio | 2 pruebas (sin `svg text`, `vector-effect`) | las fechas de los extremos van en HTML bajo el SVG (`.ticks`); `vector-effect: non-scaling-stroke` en eje, línea y puntos; viewBox 360x140 para que el radio se lea en 320 y 375 px |
| M4 `aria-label` largo | 1 prueba | más de 12 puntos: cantidad, primero, último y mejor |
| M5 negación y cabecera de la prueba | n/a | `/Se muestran los primeros/`; cabecera con 1.000 y orden descendente |
| L6 valores no finitos | 2 pruebas (NaN, Infinity, 1 y 1e12; todo inválido) | `Number.isFinite` antes de dibujar; sin `Math.min(...)`. No hay prueba de 150 000 puntos: pintarlos en jsdom cuesta más que lo que prueba; el `reduce` no depende del tamaño de la pila |
| L7 decisión del orquestador | 4 pruebas | la gráfica omite `capped` y grafica solo el nivel del intento más reciente, con la leyenda «Gráfica de intentos en {nivel}»; la prueba que esperaba 5 puntos pasó a 4 |
| L8 `level_changed \|\|` | n/a | quitado; la comparación es la local entre niveles |
| L9 reps de rondas + reps | 1 prueba (5 rondas + 5000 reps) | `Math.min(reps, 999)` con comentario |
| L10 gráfica y notas con error | 1 prueba (relectura fallida con datos viejos) | si `series.error` solo se pinta el aviso |
| L11 error tipado | 1 prueba (`role=alert` sin tabla) | `ErrorNotice` propio con `ApiError`, ya no se usa `DataTable` para el error |
| L12 píldora «Mejor» | 2 pruebas (BenchmarksTab y StatusTag) | `StatusTag mark="best"` (`data-mark`), entrada en `dev/Catalog.tsx` y `DESIGN.md` |
| L13 pruebas que faltaban | 20 en `BenchmarksTab.test.tsx` | misma fecha, orden no ascendente, empate «Sin cambio», `rx_plus`, `score_type` desconocido, 429, 404 `member_not_found`, rondas×1000 y omisión sin marca, cambio de `memberId` |
| L14 pruebas de `TrendChart` | 9 | sentido vertical, reparto horizontal, etiquetas, un punto, valores extremos |
| L15 E2E | n/a (no se corre) | `getByRole("button", { name: "Fran", exact: true })`; afirma «Primera vez»; la cancelación solo tolera 2xx o 409 |
| S1 tope de intentos | 1 prueba | `attempts` con `.max(200)` (`SERIES_MAX_ATTEMPTS`) |
| S2 serie de otro benchmark | 1 prueba | `queryFn` lanza `invalidResponseError` si `benchmark_id` no es el pedido |
| S3 marcas negativas | 4 pruebas | `.nonnegative()` en segundos, rondas, repeticiones y carga |
| S4 limpieza E2E | n/a | `afterEach` de las dos specs: la baja del socio y la cancelación de clases se intentan siempre; el primer fallo se relanza al final |

**Conservado**: el movimiento que el orquestador puso en el WOD de Fran de la spec.
**Datos que quedan en desarrollo (ficticios)**: un WOD de 2033 por corrida de `athlete-profile.spec.ts` (no hay borrado de WODs por diseño) y la clase con resultado (no se cancela, 409).
**No corregido**: nada.

**Verificación de las revisiones** (desde `web/`): suite completa 277 archivos, 4 994 pruebas, 0 en rojo; `npm run lint`, `npx tsc --noEmit` y `npm run build` exit 0; guardián `e2e-stack-guard` 16 verdes (ver abajo); gate no sellante `web/shared src/shared/ui/TrendChart.test.tsx` exit 0. Sin correr: gate sellante `web/athletes`, checkpoint, Docker y Playwright.

### E2E (orquestador)

**Rojo E2E (orquestador, P-E2E, imagen web con F2 sin F3):** primer intento, el caso nuevo falló en `POST /wods` (311 ms): la spec mandaba `movements: []` y el api exige de 1 a 30 movimientos (`validate_wod`). No es un rojo válido. Arreglo del orquestador en la spec: un movimiento activo cualquiera, sin carga, `21-15-9`. Segundo intento: 1 failed, exit 1. No existe el chip «Fran» de la subpestaña Benchmarks (motivo correcto); los datos ya se crean bien. Los dos casos de F1 siguen pasando (2 passed en el primer intento). `.env` restaurado.
**Verde E2E:** P-REBUILD 3 desde el worktree (build exit 0). P-E2E de `athlete-profile.spec.ts` (3 casos, con el de Benchmarks) y `athlete-records.spec.ts` (2 casos): corrida 1, 5 passed (11,7 s); corrida 2, 5 passed (12,0 s); exit 0. `.env` restaurado.
**E2E tras las revisiones** (P-REBUILD 3 desde el worktree, build exit 0): `athlete-profile.spec.ts` y `athlete-records.spec.ts`, 5 passed (9,8 s); `kiosk-idle.spec.ts` 2 skipped (su corte de las 23:19 de Bogotá; corrió a las 23:43). La segunda corrida va después de medianoche, en el bloque de evidencia.

## Cierre de la Wave 5a (S9-F1, 2026-11-17)

**P-GATES** (worktree limpio `.claude/worktrees/gates` en `29d8932`, la rama del sprint con F1 integrado por `merge --ff-only`): api lint, formato y mypy en verde; pytest 12.304 passed, 103 skipped, 47 deselected (1 h 20 min, con un agente de front en paralelo), cobertura 96 %; scripts y Caddy en verde; web lint, tsc, Vitest 268 archivos y 4.734 pruebas (cobertura 95,86 % de líneas) y build: `run-gates: todos los gates en verde (wave 5a)`, exit 0. `src/features/system/api.test.tsx` no falló.
**P-REBUILD 3** (árbol principal, `GIT_SHA=29d8932`): build exit 0, `up -d --no-build --force-recreate web`, web `healthy`, `/socios` 200.
**Preview 8180** (guion Playwright local que lee la clave del archivo, admin, socio ficticio dado de baja con una medición del E2E; tema forzado con `apex.theme` en localStorage, porque el tema no sigue a `prefers-color-scheme`): Resumen y Medidas en claro y oscuro a 1440 px. Píldoras de las cinco subpestañas, tarjetas del resumen, tabla con «•••» y «Mostrar», «—» sin dato, aviso de solo lectura por la baja; los dos temas con sus tokens. Hallazgo visual LOW: en la tabla de Medidas la celda del peso («••• Mostrar») queda unos píxeles más abajo que las demás celdas de la fila; se corrige en S9-F2 (misma feature).
El hallazgo visual se corrigió en S9-F2 (`MetricsTab`: celdas con la misma franja de alto).

### Sello y evidencia (S9-F3)

- Gate sellante `slice-gate.sh web/athletes src/features/athletes/components/BenchmarksTab.test.tsx`: 58 passed, exit 0. No sellante `web/shared` (TrendChart): exit 0.
- Checkpoint `dc06f8c`.
- Segunda corrida E2E después de medianoche (imagen con F3 y sus revisiones): `athlete-profile`, `athlete-records` y `kiosk-idle`, 7 passed (9,0 s), exit 0; `.env` restaurado.

## Arreglos visuales del cierre de la Wave 5b

| Hallazgo (LOW) | Arreglo | Prueba |
|---|---|---|
| Medidas: los «—» de Altura, % grasa y Notas quedaban más arriba que «•••» y «Mostrar» | `MetricField.module.css` `.empty` y `MetricsTab.module.css` `.notes`: flex, `align-items: center`, `min-height: var(--control)`, la misma franja que el resto de celdas | sin prueba (jsdom no calcula layout); queda para la preview del orquestador |
| TrendChart con un punto: caja grande con una línea corta y suelta abajo (el `max-height` de 200 px dejaba el SVG angosto dentro de un contenedor ancho y el eje parecía corto) | sin `max-height`; el contenedor `.wrap` topa en `max-width: 560px`; alto del viewBox 140 a 120; el eje solo existe con 2 o más puntos y cubre de la primera a la última posición de punto | `TrendChart.test.tsx`: con un punto no hay `line` ni `polyline` (rojo antes); con 2 o más el eje va de `min(cx)` a `max(cx)`; el CSS no tiene `max-height` y sí `max-width` (rojo antes) |
| Récords: «Se corrige corrigiendo el resultado que lo originó.» redundante | «Para cambiarlo, corrige el resultado que lo originó.» en `RecordsTab.tsx`; corrección de pruebas por decisión del orquestador: `RecordsTab.test.tsx` (afirmación y negación) y la spec E2E `athlete-records.spec.ts` | `RecordsTab.test.tsx` (rojo antes con el texto nuevo) |

## Cierre de la Wave 5b (S9-F2 y S9-F3, 2026-11-18)

**P-REBUILD 3 y 4** (árbol principal, `GIT_SHA=4725fcd`): imágenes `apex-api:local` y `apex-web:local` reconstruidas (exit 0), `up -d --no-build --force-recreate api worker web`; `/health` 8181: `status ok`, `db ok`, `migrations ok`, `crypto ok`, `version 4725fcd` (`backup: attention`, como antes); api, worker y web `healthy`.
**Smoke 8181 de solo lectura** (`w5b_smoke.py`, socio ficticio con un intento de Fran): admin y coach, `GET /athletes/{id}/summary`, `/metrics`, `/rms`, `/records`, `/benchmarks` y `/benchmarks/{benchmark_id}`: 200 en las 12 peticiones.
**Capturas** (guion Playwright local, admin, un login por tema; tema por `apex.theme`): las cinco subpestañas en 768, 1024 y 1440, claro y oscuro: 30 capturas, ningún desborde horizontal de la página. El primer intento del oscuro se cortó en el login (cuarto login en un minuto: el límite de intentos de Nginx); el guion pasó a un solo login por tema.
Hallazgos visuales (LOW), corregidos antes de cerrar: (1) en Medidas los «—» de Altura, % grasa y Notas quedaban más arriba que la fecha y el «•••»; (2) `TrendChart` con un solo intento pintaba una línea corta suelta abajo; (3) el texto «Se corrige corrigiendo el resultado que lo originó.» era redundante.
Arreglos en el checkpoint `0a20569` (sello `web/athletes` con RecordsTab, MetricsTab, MetricField y BenchmarksTab: 156 passed). Imagen web reconstruida desde el worktree: P-E2E de `athlete-profile` y `athlete-records`, 5 passed. Capturas repetidas en claro (15): la fila de Medidas queda alineada, la gráfica de un punto ya no tiene la línea suelta y el texto de Récords dice «Para cambiarlo, corrige el resultado que lo originó.».
