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
