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
