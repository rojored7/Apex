# Crítica 1 del plan del Sprint 3 (plan-critic) · Veredicto: RECHAZADO

Sobre `docs/ddd/blueprints/sprint-03-plan.md` en `eebfb0f`. Seis bloqueantes y once enmiendas.

## Bloqueantes

1. **`ENABLE ALWAYS` (S3-D49) se pierde con la limpieza de `db_test` (sección 0, D30).** `api/tests/conftest.py:172-222` y `:597-607` usan `DISABLE TRIGGER USER` / `DELETE` / `ENABLE TRIGGER USER`; `ENABLE TRIGGER USER` deja `tgenabled='O'` y pisa el `'A'` de `0008`, `0009` y `0011`. `migrated_database` y cada `dos_sesiones` repiten la limpieza. `test_0008` (replica), `test_0009` y `test_0011` (`tgenabled='A'`) pasan aisladas y fallan en la corrida completa; los gates por archivo no lo ven hasta `run-gates.sh` (B11.6 o V9). Corrección: la limpieza termina con `ALTER TABLE … ENABLE ALWAYS TRIGGER <nombre>` por trigger, más una prueba que afirme `tgenabled='A'` tras la limpieza y tras `dos_sesiones`.
2. **`CON_LIMITE` y `test_user_limits_catalog` se actualizan tarde: el gate de B1 falla.** `test_error_codes_per_route.py:26-35,85-87` exige igualdad exacta entre "429 declarado" y `CON_LIMITE`; B1 añade `POST /members/{id}/memberships`, B2 `freeze`, B3 `payments` sin tocarla; B5.2 asume que B1–B4 lo hicieron. Corrección: cada slice que introduce una ruta con límite (B1, B2, B3, B5, B6, B7, B8, B9b, B10) actualiza `CON_LIMITE` en su Rojo; reescribir B5.2; `test_user_limits_catalog` usa el mismo conjunto.
3. **S3-D65 punto 2 (pestañas como rutas hijas con `<Outlet>`) no es implementable con el router actual.** `web/src/routes.tsx:34-44,60-63` genera rutas planas; `RouteDef` (`routeTable.ts:19-27`) no tiene `children` ni `parent`; F1.1/F7.1 no tocan `routes.tsx`, `routeAccess.ts`, `routes.reference.ts` ni `nav.ts`. Corrección: paso explícito en F3.1 (primer slice que toca `routeTable`): `parent`/`children` en `RouteDef`, anidamiento en `buildRoutes`, `routeAccess`, oráculo y `nav` (excluir hijas con `:id`), pruebas de anidamiento en `routes.test.ts` y `routes.render.test.tsx`.
4. **El gate de W0-1 referencia un archivo que no existe.** W0-1.8 paso 5 pasa `tests/unit/dev-proxy.test.ts`; `web/tests/unit/` solo tiene `index-html`, `no-role-literals` y `playwright-config`; `slice-gate.sh` aborta con "archivo inexistente". Corrección: quitarlo o crearlo con propósito; verificar con `ls` cada archivo de cada línea de gate.
5. **`prefix_field(...)` (D4, B4.5) no existe.** Ningún stub lo crea ni se dice dónde vive; re-lanzar `PaymentError` con `field` prefijado exige un contrato. Corrección: stub y prueba en B3 o B4 (dueño, firma, caso `first_payment.amount_cop`); si va en `core/errors.py`, justificarlo como S3-D43.
6. **`test_sql_literals_constant` (S3-D56 / B1.3) falla contra código existente.** Exige `ast.Constant` en `text(`, `literal_column(` y `execute(`; hay 25 `execute(` con ORM (`members/service.py:295`). Corrección: regla "ningún argumento de cadena construido dinámicamente (`JoinedStr`, `BinOp`, `.format`) en `text`/`literal_column`/`exec_driver_sql`", sin tocar `execute(<statement ORM>)`, con control de fuente falsa.

## Observaciones

- **W0-2 y `get_session`**: el commit ocurre en el `__aexit__` de `session.begin()`; el `try/except DBAPIError` debe abarcar todo el `async with`, con prueba de 55P03 al confirmar. `migrations/env.py:84` crea su propio engine sin `server_settings`: el `SET LOCAL … = 0` es redundante y `test_las_migraciones_anulan_los_tiempos_de_espera` es una prueba vacía. `create_engine_from` lo usan `cli.py:261` y `main.py:172`: `rotate-key`, `sign-audit` y los jobs heredan los timeouts; documentar y revisar. `test_error_responses_in_openapi.py` usa una app de juguete sin roles; "toda operación con rol declara 503" necesita `create_app()`.
- **Orden gate/evidencia (E1 del Sprint 2)**: la evidencia Docker/psql se obtiene tras el sello; editar el cuaderno entonces cambia la huella. Definir dónde se anota (bloque del slice siguiente o commit `docs` aparte).
- **B3 deja viva `POST /memberships/{id}/payments` sin gate** → `MembershipGateNotRegistered` da 500. Mover a B4 o traducir a error de dominio.
- **`PanelLayout` es presentacional** (`layouts.a11y.test.tsx:23-39` sin `QueryClientProvider`): el host del panel de pagos encaja en `PanelShell`.
- **F3 vs B7**: F3 crea `useMembershipSummary()` pero `GET /memberships/summary` nace en B7. Mover a F4/F5 o F3 tras B7. El E2E `stack` de F3 ("Al día" en `/socios`) necesita B9b: diferir explícito.
- **Caché del resumen (S3-D53)** se invalida en el `emit`, antes del commit: ventana de 30 s con datos viejos. Invalidar tras commit o documentar.
- **`PYTEST_ADDOPTS` en B9a**: `slice-gate.sh members` sin lista incluye `test_list_perf.py`; B9a sí lleva `-m 'not perf'`.
- **`USER_LIMITS` constantes**: V4 corre 13 specs con el mismo admin (30/min `memberships-write`, 60/min `members-search`, 30/min `members-reveal`); sin perfil E2E → flaky 429. Hacerlos configurables por `Settings` con default (perfil E2E) o serializar specs.
- **`pg_dump` desde la shell** con `exec -T` y solo desde Bash.
- **Límite de 50 líneas**: `sell` y `summary` en riesgo; anticipar partición.
- **SPRINT-03 vs plan**: falta paso de ampliación de `test_banned_imports.py` (US-083, `core/locks.py` sin `hashlib`); `test_list_performance.py` vs `test_list_perf.py` (corregir SPRINT-03.md en W0-1.2); HEAD de partida es `eebfb0f`.
- **Alcance de W0-1** amplio (digests, vitest/stylelint, 15 documentos, `.env.seed`): aceptable con la regla de gate fallido.
- **`CLAUDE.md` por adelantado** (`core/locks.py`, 503 `busy`) antes de que exista el código: ventana de contradicción aceptable.

## Enmiendas a incorporar (E1…E11)

- **E1** Limpieza que preserva `ENABLE ALWAYS` (sección 0, 2, B1, B2, B3): `LIMPIAR_PAYMENTS`/`LIMPIAR_MEMBERSHIPS` cierran con `ENABLE ALWAYS TRIGGER <nombre>`; prueba de `tgenabled='A'` tras limpieza y `dos_sesiones`; `test_0008/0009/0011` en corrida completa; corrida conjunta `tests/memberships` + `tests/migrations` en B1.
- **E2** `CON_LIMITE` por slice (B1, B2, B3, B5, B6, B7, B8, B9b, B10); reescribir B5.2; `test_user_limits_catalog` con el mismo conjunto.
- **E3** Rutas hijas reales (F3.1, F7.1): `RouteDef.parent`/`children`, `buildRoutes` anida, `routeAccess`, `routes.reference.ts`, `nav.ts`; pruebas de `<Outlet>`.
- **E4** W0-1.8 paso 5: quitar `tests/unit/dev-proxy.test.ts` o crearlo; `ls` de cada archivo de gate.
- **E5** `prefix_field`: stub y prueba en B3/B4 con dueño y firma; si `core`, justificar.
- **E6** `test_sql_literals_constant`: regla de cadena dinámica, sin tocar `execute(ORM)`, con control.
- **E7** `get_session` con `try` sobre todo el `async with`; `env.py` sin prueba vacía; impacto de timeouts en `cli.py` y worker documentado en RUNBOOK §9; `test_error_responses_in_openapi` con `create_app()`.
- **E8** Evidencia Docker tras el sello: dónde y cuándo se anota.
- **E9** `POST /memberships/{id}/payments` nace en B4 (o error de dominio explícito en B3).
- **E10** Front: `useMembershipSummary` a F4/F5 o F3 tras B7; host del panel en `PanelShell` o `layouts.a11y.test` en verde; `USER_LIMITS` configurables por `Settings` con perfil E2E.
- **E11** `exec -T` en `pg_dump`; `PYTEST_ADDOPTS` en B9a; partición anticipada de `sell`/`summary`; invalidación de caché tras commit; paso de `test_banned_imports.py`; `test_list_performance.py` en SPRINT-03.md; HEAD `eebfb0f`.
