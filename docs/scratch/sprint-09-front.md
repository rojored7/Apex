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
