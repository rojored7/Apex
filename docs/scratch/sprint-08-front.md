# Sprint 8 · cuaderno del front (rama feat/sprint-08-front)

## S8-F1 · Movimientos y Benchmarks (US-165, US-166, S8-D5, S8-D6)

Base 6893c3f (sin rebase: la rama del sprint estaba en el mismo commit). `npm ci` una vez. `tsc` base: 0 errores.

Rojo (antes del código): `MovementPanel.test.tsx`, `BenchmarkPanel.test.tsx` y `MovementsPage.test.tsx` no resolvían el import
(3 archivos fallidos, 0 pruebas ejecutadas); `features.test.ts` (13 features) y `routes.test.ts` (lista con `/movimientos`): 2 failed.

Verde:
- `features/wods/`: `schemas.ts` (Zod de respuesta y de formularios, PATCH solo con lo cambiado), `api.ts` (listas y escrituras con
  `useSensitiveMutation`), `wodErrors.ts` (409 `movement_exists` y `benchmark_exists` bajo «Nombre», 422 `score_type_locked` bajo
  «Tipo de marca», 403/404/429/5xx), `components/{MovementPanel,BenchmarkPanel,MovementsList,BenchmarksList}.tsx`, `pages/MovementsPage.tsx`
  (pestañas `?tab=`).
- `config/features.ts` habilita `wods`; `routeTable.ts` carga `/movimientos`; `errorCodes.ts` suma cinco códigos.
- `nav.ts` no cambió: «WOD de hoy», «WODs» y «Movimientos» ya dependían de `wods` desde S7-F1. «WODs» y «WOD de hoy» llevan a 404 hasta F2.
- E2E `web/tests/e2e/stack/movements.spec.ts`.

DESIGN-GAP anotados en código: alias, «lb» y «Tipos de récord» (S8-D5); pestaña Benchmarks (S8-D6); el 409 no enlaza al existente
(no hay ficha de movimiento).

Tropiezo del entorno: un heredoc de Git Bash con comillas falló en bloque; los archivos se escribieron con Write.

Cierre F1: corrida completa lint 0, tsc 0, vitest 238 archivos / 4327 pruebas verdes, build 0; gate `web/wods` verde (53 pruebas).
E2E `movements.spec.ts` ESCRITO, sin correr (stack de desarrollo roto; instrucción del usuario: no `up`, ni E2E, ni banderas).

## S8-F2 · Lista y formulario de WOD (US-166, US-167, S8-D7, S8-D8)

Merge de `feat/sprint-08-wods-resultados-tv` (c007e3e) sin conflictos (6d00629). `types.ts` ya traía WodOut, ResultIn, TvBoard.
Rojo: `score.test.ts` (import sin resolver), `Segmented.test.tsx` (import sin resolver), `WodListPage.test.tsx` y `WodFormPage.test.tsx` (import sin resolver, 0 pruebas), `routes.test.ts` (1 failed: faltaban las tres rutas con `load`).
Verde: `shared/data/score.ts` (gramos <-> kg, `formatScore`), `shared/data/weeks.ts` (movido desde classes para que dos features lo usen), `shared/ui/Segmented`, `features/wods/{wodSchemas,wodsApi,wodFormErrors}.ts`,
`components/{WeekCalendar,MovementPicker,WodPreview}`, `pages/{WodListPage,WodFormPage}`, rutas `/wods`, `/wods/nuevo`, `/wods/:id/editar` con `load`.
Corrida completa: lint 0, tsc 0, vitest 242 archivos / 4372 pruebas, build 0. E2E `wods.spec.ts` ESCRITO, sin correr.
DESIGN-GAP: «AMRAP/For time», plantillas, «2 sesiones faltan» (S8-D7). Heredocs de Git Bash con ciertos caracteres fallan: archivos con Write.

F2 checkpoint c96f937. Rama al día con el backend (merge 6d00629).

## Pendiente (F3 a F6) y notas para quien siga
- F3 (`/wods/:id`): `shared/data/results.ts` (hooks de GET /wods/{id}/leaderboard?level&sex&limit&offset y GET /wods/{id}/results?include_superseded), `features/wods/components/{Leaderboard,WodSessions}.tsx`, `pages/WodDetailPage.tsx`, Historial con `HistoryAside` sobre GET /audit?table=wods.wods&record_id= solo con `audit.view` (E5). `formatScore` ya existe en `shared/data/score.ts` con prueba; falta la de empates 1-2-2-4.
  Hueco del contrato: no hay PATCH de resultados; «asignar a otra sesión» solo puede hacerse como corrección `PUT /results` con `supersedes_id` y `session_id` nuevo. Las sesiones del día salen de `/class-sessions` (clases): una feature no importa de otra, así que el hook va a `shared/data/`. Enlazar el formulario de WOD (`navigate("/wods/:id")`) ya apunta a esta ruta.
- F4: `/clases/:id/resultados` (GymLayout, `routeTable` ya trae la ruta sin `load`), `layouts/tabletMode.ts` (`TABLET_PATH` con las dos rutas), `ZoneShells.tsx`, `CheckInPage` («Registrar resultados» con POST /auth/kiosk y ruta `/resultados`), `ResultsEntryPage`, `ScoreForm` (kg a gramos con `kgInputToGrams`; `capped` solo con `time`; Zod 0..1.000 kg), `ScaledChips` (`scaled_movement_ids`), `AddWalkIn`; E2E de 15 resultados con tiempo medido (S8-D40).
- F5: pestaña `/socios/:id/resultados` (quitar `disabledUntil`), `WodTodayCard` (`wod_today` ya llega en GET /dashboard como objeto), `TvSettingsForm` en `?tab=tv` (`gcTime: 0`, sin persistir la respuesta de regenerate-token).
- F6: `/tv` con `TvLayout`, `fetch` propio con `credentials: "omit"` y solo `X-Device-Token`; token del fragmento `#token=` limpiado con `replaceState` antes de la primera petición; `POST /auth/logout` al montar; claves `_g` del contrato (`load_rx_m_g`, `load_rx_f_g`, `score.load_g`); soak `web/tests/soak/tv.soak.spec.ts` y `.github/workflows/nightly.yml`.
- Los E2E de stack de F1 y F2 (`movements.spec.ts`, `wods.spec.ts`) siguen sin correr: stack roto, sin banderas, por indicación del usuario.

## S8-F3 · Detalle de WOD (US-171, US-172, S8-D13, E5)

Desviación de TDD (honesta): el código de F3 se escribió antes que sus pruebas, así que no hay rojo medido de F3; las pruebas se
escribieron después y pasan a la primera. Para F4 sí hay rojo medido.
Verde: `shared/data/{results,resultErrors}.ts` (hooks de leaderboard, resultados, sesiones del WOD y anular), `features/wods/{historyApi.ts,
components/{Leaderboard,AllResults,WodSessions,WodSummary,WodHistory}.tsx, pages/WodDetailPage.tsx}`, ruta `/wods/:id` con `load`,
permiso `results.void` (solo admin), etiqueta «WOD» en `audit-labels`, siete códigos de error de resultados en `errorCodes.ts`.
Contrato: no hay PATCH de resultados ni «mover a otra sesión» (M-3 de B1d): un resultado equivocado lo anula el admin con motivo
(`POST /results/{id}/void`, `Can action="results.void"`), y «Todos los resultados» tiene «Incluir corregidos y anulados».
Historial: `GET /audit?table=wods.wods&record_id=` solo con `audit.view` (admin); el coach no ve la pestaña.
DESIGN-GAP en código: «vs. su anterior», «PR», «Buscar atleta» (el endpoint no recibe `q`), «Por validar» (EP-25), «Ver en TV» (F6),
«Veces hecho en el box» y «Escalado sugerido». E2E `web/tests/e2e/stack/wod-detail.spec.ts` ESCRITO, sin correr.
Gates: `slice-gate web/wods` verde (185 pruebas con permisos y rutas); lint 0, tsc 0, build 0; vitest completo 4396 verdes antes de mi
edición de F4 (la única falla de esa corrida fue `features.test.ts` editado a mitad de corrida para F4).

## S8-F4 · Registro de resultados en la tablet (US-169, US-170, S8-D15, S8-D27, S8-D31, S8-D40, L-2)

Rojo medido (antes del código): 6 archivos fallidos. Tres sin resolver el import (0 pruebas): `ScaledChips.test`, `ScoreForm.test`,
`ResultsEntryPage.test`. Doce pruebas rojas: `features.test` (1, falta `results`), `tabletMode.test` (9, no existía `TABLET_PATH`),
`ZoneShells.test` (2, `GymShell` no confinaba `/resultados`); `CheckInPage.test`: 2 rojas («Registrar resultados»).
Verde:
- `layouts/tabletMode.ts` (`TABLET_PATH` con las dos rutas; reemplaza `CHECKIN_PATH`), `ZoneShells.tsx` la usa, `GymLayout` rotula el contador
  con su propio `label` («Registrados 2 de 4»; antes decía siempre «Llegaron»).
- `features/results/{schemas,api,resultErrors}.ts`, `components/{AttendeeResults,ScoreForm,ScaledChips,AddWalkIn}.tsx`,
  `pages/ResultsEntryPage.tsx`; `CheckInPage` suma «Registrar resultados» por `switchSession` (cambio de clase S7-D42, sin contraseña;
  un `Link` habría abierto el diálogo de salida).
- `config/features.ts` habilita `results`; `routeTable.ts` carga `/clases/:id/resultados`; `routes.test.ts` la suma.
- Corrección: `PUT /results` con `supersedes_id` y el MISMO `session_id`; no hay «mover a otra sesión» (S8-B1d M-3); lo equivocado lo anula el
  admin desde el detalle del WOD (F3). 403 `kiosk_mode` al corregir un resultado de escritorio se explica; 409 relee la lista.
- «+ Alguien que no hizo check-in»: búsqueda por nombre (3 letras) y `POST /attendance`; hook propio en `features/results/api.ts` (no se importa de `classes`).
- Tres pruebas viejas de `shells.test.tsx` usaban `/clases/1/resultados` como «otra pantalla» del quiosco; ahora usan `/clases/1/otra`.
DESIGN-GAP en código: «anterior en <WOD>», récord automático (EP-24), «Nota (opcional)», «+ otro» de los chips (el contrato solo admite movimientos del WOD).
E2E `web/tests/e2e/stack/results.spec.ts` ESCRITO, SIN CORRER (stack roto): 15 resultados con pausas de tecleo de 120 ms, uno «No terminó»,
una corrección, tiempo total medido y anotado como `tiempo-15-resultados` (tope 5 min), leaderboard del WOD en un contexto de admin aparte,
ninguna petición a `/reveal` ni a `/members/{id}`. El valor medido queda pendiente de la primera corrida real.
Cierre F4: vitest completo 249 archivos / 4451 pruebas (una falla: `errorCodes.test` prohíbe `code: "..."` suelto; el `"custom"` de Zod pasó a la constante
`ISSUE_CODE`, verde después); lint 0, tsc 0, build 0; `slice-gate web/layouts` y `web/results` verdes (239 pruebas con las vecinas).

## S8-F5a · Limpieza de F4: una sola copia de POST /attendance
`useCheckIn` (con `checkinSchema`) pasó a `shared/data/attendance.ts`; `classes/api.ts` ya no lo define, `CheckInPage` y `AddWalkIn` (results) usan
la misma copia y `useAddAttendance` desapareció de `results/api.ts`. Invalida `class-session`, `class-sessions`, `attendance` y `session-results`
(literales: shared no importa de features). Las «semanas» ya estaban compartidas desde F2 (`shared/data/weeks.ts`; classes y wods lo importan de ahí).
Rojo: `attendance.test.ts` sin resolver el import (1 archivo fallido, 0 pruebas). Verde: 2 pruebas; 339 pruebas de shared/classes/results verdes.
Gate `web/shared` verde; checkpoint 1430a81.

## S8-F5 · Ficha, Inicio y Configuración (US-173, US-174, US-175, S8-D30, S8-D32, L-4)
Rojo medido (antes del código): 7 archivos fallidos: `MemberResultsTab.test`, `WodTodayCard.test` y `TvSettingsForm.test` sin resolver el import
(0 pruebas) y 8 pruebas rojas en `MemberDetailPage.test` (pestaña Resultados habilitada), `InicioPage.test` (región «WOD de hoy»), `ConfigPage.test`
(2: pestañas y `?tab=tv`) y `routes.test` (4: hija `/socios/:id/resultados`).
Verde:
- `features/results/tabs/MemberResultsTab.tsx` (+ `useMemberResults`, `memberResultRowSchema`, `memberResultsError`), ruta hija `/socios/:id/resultados`
  (feature `results`, acceso `results.record`: no hay permiso `results.view`; el api abre la lectura a admin y coach) en `routeTable.ts` y
  `routes.reference.ts`; la ficha quita `disabledUntil` y la suma a `CHILD_TABS`.
- `features/dashboard/components/WodTodayCard.tsx` reemplaza a `FutureKpis` (borrado con su prueba; su CSS se queda para NotificationKpis).
  «Registrar resultados» va a la próxima sesión viva de hoy (`nextCheckInSession`); `shared/lib/routes.resultsPath` y `shared/data/score.SCORE_TYPE_LABELS`.
- `features/system/components/TvSettingsForm.tsx`: la sección `tv` entra al hook genérico (`SettingsKey`), más `useRegenerateTvToken` y `useRevokeTvToken`
  (`useSensitiveMutation`, gcTime 0; la respuesta de regenerate-token NO se escribe en la caché: se relee la vista). El enlace con `#token=` vive solo
  en el estado del componente y se borra con «Listo». Prueba `no_persiste_el_token_en_la_cache` (consultas, mutaciones, localStorage y sessionStorage).
- Desviación: «Abrir pantalla TV» del menú (`nav.ts`) NO se agregó: sin token no hay a dónde abrir y el token no se puede volver a ver; el «Abrir la TV»
  vive en el enlace recién generado. «WOD de hoy» ya estaba en el menú desde F1.
- Docs: `ROUTES.md` y `docs/operacion/wods.md`.
- E2E ESCRITOS, sin correr (stack roto): `member-results.spec.ts`, `settings-tv.spec.ts` y una prueba nueva en `stack/home.spec.ts`.
Cierre F5: lint 0, tsc 0, vitest completo 252 archivos / 4482 pruebas (2 fallas de lint arquitectónico corregidas: una constante `HTTP_*` fuera de
core/api y un orden de propiedades CSS), build 0. Gates verdes: `web/dashboard` (8), `web/system` (15), sello `web/results` (47, con MemberDetailPage).

## S8-F6 · Pantalla de TV (US-177, S8-D19, S8-D20, S8-D32, L-4)
Rojo medido (antes del código): 5 archivos fallidos: `TvWod.test`, `TvLeaderboard.test` y `TvPage.test` sin resolver el import (0 pruebas) y 2 pruebas
rojas: `features.test` (falta `tv`) y `routes.test` (falta `/tv` con `load`).
Verde:
- `core/api/tvClient.ts` (`fetchTvToday`): el ÚNICO `fetch` fuera del cliente del api que existe, dentro de `core/api` porque el lint solo permite `fetch`
  ahí (sin tocar la configuración protegida). Solo `X-Device-Token`, `credentials: "omit"`, `cache: "no-store"`, sin `Authorization`, sin token en la URL;
  401 = «token inválido»; red, 429, 5xx, tiempo (15 s) o JSON malo = «no disponible».
- `features/tv/`: `schemas.ts` (TvBoard en gramos, Zod), `api.ts` (`useTvBoard`: clave `["tv","today"]` sin token, intervalo `refresh_seconds`, 5 min con
  401, sin reintentos propios), `tvToken.ts` (`consumeTvToken`), `components/{TvWod,TvLeaderboard}.tsx`, `pages/TvPage.tsx` (+ CSS con tokens; letras de 28 px
  o más). `/tv` carga con `load` en `routeTable.ts`, `tv` entra a `ENABLED_FEATURES`.
- DECISIÓN del token (pedida por el encargo): el lint solo prohíbe `sessionStorage` (S4B-D51); `localStorage` no está prohibido y S8-D32 pide guardarlo en
  `apex.tv.token`. Se guarda en localStorage del navegador de la TV (una TV sin teclado no puede volver a pegar el enlace tras un corte de luz). Si el
  almacenamiento falla, queda en memoria y el enlace se vuelve a abrir. `tv.md` decía «en memoria»: se corrigió. No se guarda ninguna respuesta.
- `POST /auth/logout` al montar con `logout()` de core/auth: cierra también las demás pestañas del mismo navegador; el aviso va en `TV_HANDOFF` y en `tv.md`.
- Soak: `web/tests/soak/tv.soak.spec.ts` + `web/playwright.soak.config.ts` (`npm run soak`, puerto 4174, `vite preview`; `page.clock` acelera 12 h en cuatro
  tramos de 3 h, `page.route` con 20 filas, heap por CDP tras GC en cada cuarto; pasa si el último ≤ 1,2 × el primero) y job `tv-soak` real en `nightly.yml`
  (`test_nightly_workflow.sh`: 0 fallas). ESCRITO, SIN CORRER (regla de no correr E2E en esta ronda).
- E2E de stack ESCRITO, sin correr: `web/tests/e2e/stack/tv.spec.ts`.
Cierre F6: lint 0, tsc 0, vitest completo 255 passed (255) ; 4511 passed (4511), build 0; sello web/tv con TvPage.
