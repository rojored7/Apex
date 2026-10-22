# Crítica 2 del plan del Sprint 3 (plan-critic) · Veredicto: APROBADO CON OBSERVACIONES

Sobre `docs/ddd/blueprints/sprint-03-plan.md` en `7b51d3c`. Los seis bloqueantes de la crítica 1 están resueltos en el cuerpo del plan (1 limpieza con `ENABLE ALWAYS TRIGGER`; 2 `CON_LIMITE` por slice; 3 rutas hijas especificadas en F3.1, con el defecto nuevo E14; 4 W0-1.8 con archivos reales; 5 `prefix_field` con dueño en `memberships`; 6 `test_sql_literals_constant` compatible con todos los `text(`/`literal_column(`/`exec_driver_sql(` existentes). Quedan cinco enmiendas obligatorias, E12–E16, que se aplican antes del slice afectado y no cambian el alcance ni el conteo de 165 pasos.

## Hallazgos nuevos

**Alta**
- **E13 · `after_commit` se dispara también al liberar un SAVEPOINT** (`sqlalchemy/orm/session.py:1332-1340`: `if self._parent is None or self.nested`). `sell` va en `begin_nested()`; la marca `apex.summary_dirty` se consume al liberar el SAVEPOINT y el commit externo ya no invalida: ventana (hasta 10 s por el candado de auditoría) en que otra petición recalcula con datos viejos y los guarda 30 s. `test_summary_cache.py` fallaría en B7 si usa `sell`.
- **E12 · Gate de F3 con archivo inexistente**: F3.6 paso 2 pasa `src/shared/data/memberships.test.ts`, que nace en F4 (F4.5).

**Media**
- **E14 · La ruta hija índice duplica el `path`**: F1.1 agrega `route("/socios/:id", "Datos", …, {parent: "/socios/:id"})`; `routes.test.ts:33-35` exige paths únicos y `:25-30` compara el oráculo con `strip` sin `parent`; F1.2 dice "`routes.reference.ts` sin cambios" y F1.1 lo contradice; `nav.ts` es un catálogo estático (`NAV_CATALOG`), no se deriva de `ROUTE_TABLE`: la frase "ya excluye rutas con parent o ':'" es falsa.
- **E15 · El job `e2e-stack` no recibe los topes `USER_*`**: `ci.yml:268-275` solo sube `LOGIN_*`, `REFRESH_*`, `RESET_*`, `FORGOT_*`, `LOGOUT_*`; con los defaults las 13 specs con un admin darán 429. Ocho variables alimentan nueve cubetas (`memberships-write` y `payments-write` comparten `USER_WRITE_LIMIT_PER_MIN`): correspondencia no escrita en W0-2.1.
- **E16 · Contradicción sobre el 503 de `/health`**: E7 pide que `/health` y las públicas no declaren `503`; `test_error_codes_per_route.py:63-70` exige que `/health` declare `503` con `HealthOut`. S3-D67 dice "toda operación con sesión" y W0-2.3 "con seguridad declarada".

**Baja**
- Línea 908 del plan aún dice host del panel en `layouts/PanelLayout.tsx` (E10 manda `PanelShell`).
- `--db-timeouts off`: `cli_runtime(settings)` no es opción de typer; hace falta `@app.callback()` con estado de módulo; la prueba con `export-openapi` no observa nada: probar con `create_engine_from` parcheado.
- Listener de caché: limpiar la marca también en `after_soft_rollback`; `test_errors_busy` usa un service que lanza `DatabaseBusy` directo: falta un caso con `get_session` real y 55P03 al confirmar.
- `test_triggers_siempre_activos` corre `LIMPIEZA_DE_SESION` completa en mitad de la suite: mejor solo `LIMPIAR_MEMBERSHIPS` y `LIMPIAR_PAYMENTS`.
- `test_no_trigger_tampering` prohíbe `TRUNCATE` y `DISABLE TRIGGER` en cualquier cadena de `app/`, docstrings incluidos.
- Línea base de W0-1.1: HEAD es `7b51d3c` (solo documentos sobre `eebfb0f`).

## Supuestos verificados
Conteo 165 y 20 slices; `env.py` con engine propio; `api` toma el `.env` completo (`USER_*` llegan al contenedor); archivos de gate de W0-2 existen; `routes.render.test.tsx`, `nav.test.ts`, `features.test.ts`, `routeAccess.test.ts`, `ConfigPage.test.tsx`, `layouts.a11y.test.tsx` existen; `begin_nested` + `after_commit` → FALSO (E13); `nav.ts` excluye hijas → FALSO (E14).
