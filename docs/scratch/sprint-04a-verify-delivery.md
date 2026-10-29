# verify-delivery · Sprint 4A (plan contra lo entregado y prueba contra el sistema vivo)

- Rama: `feat/sprint-04a-worker-auditoria-tablero`. HEAD al empezar y al terminar: `fa0787d` (`docs(sprint-04a): evidencia de V2–V8, correcciones finales y V10`). Base del sprint: `f5f2503` (cierre del Sprint 3 en `main`); planificación `8e17c3d`. Último commit que toca código: `360d816` (2026-10-29 10:31:45Z; `api/src/app/core/audit.py`, `core/audit_verify.py`, `modules/audit/diff.py`, `worker/main.py`, `web/src/shared/data/plans.ts`).
- Fecha: 2026-10-29 (10:30–10:45Z).
- Alcance: paso V11 del plan (`docs/ddd/blueprints/sprint-04a-plan.md`, sección 7). Pilar 1: matriz N/M de las 14 historias, los 10 endpoints más `active_members_count`, las 2 migraciones, las 13 condiciones para VERDE del impacto, la revisión de seguridad del diseño (H-1, H-2, M-1…M-7, L-1…L-10), las decisiones S4A-D1…S4A-D127, las enmiendas E1…E10, la deuda heredada del Sprint 3 con dueño 4A, las 12 contradicciones resueltas del plan, los hallazgos de las revisiones por slice y de V10, las desviaciones declaradas y la validación V1–V12. Pilar 2: lo que V2–V8 dejó en el cuaderno más una comprobación propia de solo lectura contra el stack (sección 13).
- Método: lectura completa de `SPRINT-04A.md`, del plan (secciones 7 y 10), de `docs/ddd/impacto/sprint-04a.md` §9, de `sprint-04a-seguridad-diseno.md`, de `sprint-04a-critica-1.md`, del bloque "Sprint 4A" de `DECISIONES.md` (líneas 1101–1306), de los dos cuadernos (`docs/scratch/sprint-04a.md`, 827 líneas; `docs/scratch/sprint-04a-front.md`, 271 líneas) y de los criterios de las 14 historias de `07_user_stories/` con las notas "Corregido en S4A-W0-1" de sus desgloses. Los archivos de prueba citados se comprobaron con `ls`/`grep` en `fa0787d`; el contrato se contó con un script contra `docs/openapi.json` y el de `f5f2503`. **No se corrió ninguna suite** (V9 `run-gates.sh` está en marcha en segundo plano); las cifras de pruebas vienen de los cuadernos y se dicen como tales.
- Convención (la del Sprint 3): **entregada** (todos los criterios vigentes con prueba), **parcial** (falta un criterio vigente o su prueba; se dice si está declarado), **no**. "Criterio vigente" es el de la historia corregido por `DECISIONES.md` o por la nota de cabecera de su desglose; las historias de `07_user_stories/` conservan el texto del gate (S2-D2).

## 1. Historias (14)

Checkpoints verificados con `git log --oneline 8e17c3d..HEAD` (35 commits; 20 checkpoints o fusiones).

| Historia | Criterios vigentes (resumen) | Estado | Evidencia | Desviación declarada |
|---|---|---|---|---|
| US-077 Contacto para avisos auditado | sin ruta HTTP; propósito solo `notify`/`auth_link` (si no, `InvalidPurpose` sin leer); `reveal` por campo con `purpose` y actor, `decrypt` en `crypto_ops` con `purpose` y `record_id`, sin valores; baja o inexistente → `MemberNotContactable` sin descifrar; vacío → `None` sin descifrar; nadie fuera de `members` la llama | entregada | B6 `fb5f357`; `api/tests/members/test_validate_purpose.py`, `test_service_contact.py` (`test_un_campo_vacio_da_none_y_una_sola_fila_de_cada_tipo`, `test_sin_telefono_ni_correo_no_deja_filas`, `test_contact_no_se_serializa`); `tests/architecture/test_contact_callers.py` (`CONTACT_CALLERS = frozenset()`), `test_crypto_bus_importers.py`; cuaderno líneas 407–449 | Firma `contact_for_notification(session, member_id, purpose)` sin `fields` ni `by` (S4A-D21, S4A-D50); sin `bus.batch`; importadores reales del bus con `ARRANQUE` (S4A-D113). Sin demo: la consume el Sprint 5 (plan §10) |
| US-080 Editar plan sin afectar vendidas | `PATCH` subconjunto → 200; validación sobre el plan resultante (`class_count`); RN-01; RN-04 (vendida conserva `agreed_price_cop`, `end_date`, clases); `is_active` 422; 404 inexistente o de baja; admin, 403, 401; auditoría `update` con solo lo cambiado; `PlanUpdated` | entregada | B7 `d702727`, F4 `ba85c63`; `tests/plans/test_merge_plan.py`, `test_service_update.py`, `test_router_update.py`; `tests/integration/test_rn04_plan_price_change.py::test_subir_el_plan_no_cambia_lo_vendido_y_la_venta_nueva_cobra_el_precio_vigente`; `web/src/features/plans/components/PlanForm.edit.test.tsx`; vivo B7.9, F4 demo 6, V7.6 (psql `agreed_price_cop` 120.000 con el plan a 135.000) y V8 (`PATCH` ×2 → 2.ª sin auditoría) | `admin-write` y 429 (S4A-D26); `null` explícito en obligatorios 422 (S4A-D114); sin `version`, precio vigente al vender (S4A-D60, riesgo aceptado) |
| US-081 Activar y desactivar plan | `POST .../deactivate` y `.../activate` 200 idempotentes; desactivar siempre permitido, membresías intactas; inactivo fuera de `?active=true` y venta 422 `plan_inactive`; 404; admin; auditoría `is_active` | entregada | B7, F4; `tests/plans/test_service_set_active.py` (`test_activar_un_activo_no_agrega_auditoria_ni_evento`, `test_desactivar_dos_veces_no_agrega_auditoria_ni_evento`), `test_router_set_active.py`; `tests/integration/test_plan_deactivation_with_memberships.py` (las tres); `PlansPage.actions.test.tsx`; vivo V7.6 (deactivate 200 y venta 422 `plan_inactive`), V8 (deactivate ×2 sin auditoría nueva) | Rutas `POST` aparte, no `PATCH active` (S4A-D23; casilla Activo como DESIGN-GAP, `BRECHAS.md` §11.3). `activate` sin smoke en vivo propio (ver sección 2) |
| US-082 Dar de baja plan sin membresías activas | `DELETE` 204 lógico con `deleted_at` e `is_active=false`; 409 `plan_has_active_memberships` con conteo; cuentan `pending_payment`/`active`/`expiring`/`frozen` por estado efectivo; de baja → 404 y la vendida conserva el nombre; repetir → 404; admin; auditoría `update`; sin `memberships.models` | entregada | B7, F4; `tests/plans/test_service_deactivate_or_fail.py` (incluye `test_get_including_deleted_conserva_el_nombre_y_get_no_lo_ve` y las dos carreras), `test_router_delete.py`; `tests/memberships/test_counts_active_by_plans.py`; `tests/architecture/test_service_import_graph.py` (perezosa `# lazy: G-03 (plans -> memberships)`, `plans/service.py:344,428`); `PlansPage.delete.test.tsx`; vivo V7.6 (409 con "1 membresía activa", 204 tras anular) y V8 (204 y 404) | Solo conteo en el 409 (S4A-D24, S4A-D60); "Socios con él" por `active_members_count` (S4A-D25) |
| US-094 Job diario de vencimientos | candidatas `active`/`expiring`/`frozen` por socio con `lock_member`; el 24 → `expiring` con un evento, el 1 → `expired`; idempotente; apagado tres días → solo `MembershipExpired`; congelación que empieza hoy/termina ayer; `pending_payment` y `cancelled` intactas; `today_bogota()`; auditoría con `SYSTEM_USER_ID`; fallo de un socio no tumba el resto; resumen de conteos; 1.000 socios < 60 s | entregada | B2 `7f4756f`; `tests/worker/test_expirations.py` (14 casos nombrados, p. ej. `test_el_24_una_active_que_vence_el_31_pasa_a_expiring_con_un_evento`, `test_dos_corridas_el_mismo_dia_dan_un_evento_y_una_fila_update`, `test_a_las_2_utc_del_1_de_noviembre_sigue_siendo_31_en_bogota`, `test_la_auditoria_va_con_el_usuario_del_sistema_y_el_socio`), `tests/memberships/test_recompute_lock_order.py`, `test_rules.py` (`transition_event`), `tests/cli/test_recompute_memberships.py`, `tests/architecture/test_expirations_lock_order.py`; perf 31,5 s (V5); vivo B2.9 y V7.2 sobre `apex_sim` (+100 `update` con `SYSTEM_USER_ID`, repetida → 0) | Lote por socio en páginas de 200 y una transacción por socio, no `FOR UPDATE ... LIMIT 500` (S4A-D2, S4A-D57); `RecomputeSummary` con siete enteros (`revisados`, no `revisadas`); eventos sin suscriptores (S4A-D1); `--date` solo con `--simulate` (S4A-D48, S4A-D63). La base viva no tenía filas desalineadas: 0 transiciones en `apex-db-1` (V3, V7.2, V6 parte 2) |
| US-102 Consultar auditoría | `{items,total,limit,offset}`, `limit` 1–200; filtros `from`/`to` acotados, `user_id`, `table` (`esquema.tabla` auditable), `record_id` (con `table`), `subject_member_id`, `action` cerrado; `q` por UUID o correo parcial; `seq` desc; sin `before`/`after`; cobertura de las tablas de v0.1; solo admin; solo lectura; < 500 ms con 100.000 | entregada | B4 `2044bf8`, F1 `7ad022a`; `tests/audit/test_filters.py`, `test_list.py`, `test_list_coverage_v01.py` (`test_cada_insert_aparece_con_usuario_y_fecha`), `test_router_list.py`, `test_list_performance.py` (`perf`); `tests/core/test_validators.py`; `tests/auth/test_user_refs.py`; `web/src/features/system/pages/AuditPage.test.tsx`, `auditFilters.test.ts`; `tests/e2e/stack/audit.spec.ts`; vivo B4.9 y V7.3 (filtros por entidad, "Sistema (worker)" = psql 2, fecha, `record_id`) ; V5 lista 7,9–53,9 ms | Filtros reales y nombres `esquema.tabla` (S4A-D16, S4A-D46); `staff-read` y 429 (S4A-D45); `record_id` exige `table` y `total` saturado en 100.001 (S4A-D106 a/b); `q` UUID vs `record_id` (S4A-D104); la lectura no se audita (S4A-D61) |
| US-103 Ver detalle antes y después | `GET /audit/{seq}` con `changes`; 404 `audit_entry_not_found`, 422; ningún valor en claro; el servidor nunca entrega el blob (marcador `{encrypted,key_id,alg}`); el front pinta "Cifrado" sin descifrar; `diff` puro; solo admin | entregada | B4, F1; `tests/audit/test_diff.py`, `test_get.py` (`test_la_respuesta_serializada_no_lleva_blobs_ni_datos_en_claro`, `test_el_servicio_no_descifra_nunca`, `test_un_idx_con_hmac_de_una_fila_antigua_llega_como_asteriscos`), `test_router_get.py`; `web/src/shared/lib/encryptedBlob.test.ts`, `AuditDetailPanel.test.tsx`; vivo B4.9 y V6 (`GET /audit/4772`: marcador `A256GCM`, 0 `apx1.`), V7.3 (pantalla "Cifrado" ×2 con `key_id`, sin "Mostrar") | El criterio 3 del gate ("aparecen como blob `apx1.`") lo corrige S4A-D52: marcador en lugar de blob; mal formados también tapados (S4A-D105, S4A-D107); `*_idx` como `***` también en filas antiguas (V10 L-3, `360d816`) |
| US-104 Verificar la cadena desde la pantalla | `POST /audit/verify` ≤ 100.000 → 200 `{ok, rows_checked, broken_at_seq, finished_at}`; fila alterada → `broken_at_seq` exacto; > umbral → 202 con `last`; en curso → 409 `verification_running`; cada verificación deja su `verify` en la cadena; 100.000 < 60 s; nunca escribe filas existentes; solo admin | entregada | B3 `014f455`, F1; `tests/audit/test_verify.py` (`test_fila_1234_alterada_rompe_en_1234`, `test_h1_cola_borrada_tras_una_verificacion_ok_da_rota`, `test_la_verificacion_no_cambia_ninguna_fila_existente`), `test_verify_concurrency.py`, `test_router_verify.py` (`test_por_encima_del_umbral_responde_202_con_la_ultima`, `test_con_otra_verificacion_en_curso_responde_409`), `test_verify_performance.py` (`perf`), `tests/core/test_verify_chain.py`; `web/.../VerifyChainButton.test.tsx`; `tests/migrations/test_0013_audit_verifications.py`; vivo B3.14, V6 (200 `ok`, 5.139 filas), V7.3 ("Cadena íntegra: 5.146 filas"), V8 (200 ×3 y 429) | Ancla `through_hash` (S4A-D43, S4A-D99); `AUTOCOMMIT` + `invalidate` (S4A-D44); cubetas `audit-verify`/`audit-verify-hour` (S4A-D47); lote 500 por rango acotado (S4A-D120); `SYNC_VERIFY_MAX_ROWS` 100.000 (S4A-D91); plazo síncrono 45 s con paso a 202 (S4A-D100) |
| US-105 Verificar la cadena por CLI | íntegra → 0 con el mensaje; rota → 1 con el `seq`; base caída → 2; entrada `verify` a nombre de `SYSTEM_USER_ID` o de `--as`, `source = cli`; recorre todo por lotes; no imprime `before`/`after` | entregada | B3; `tests/cli/test_verify_audit.py` (nueve casos: `test_cadena_integra_sale_0_y_va_a_nombre_del_usuario_tecnico`, `test_fila_42_alterada_sale_1_con_el_seq`, `test_base_caida_sale_2_sin_la_url_ni_la_contrasena`, `test_en_produccion_sin_as_sale_2`, `test_la_conexion_del_candado_es_autocommit_e_invalidada`), `tests/core/test_format_verify_message.py`; vivo B3.14 (código 0, 4.517), V6, V7.3 y V8 (0 y 0) | Mensaje "Cadena íntegra: N registros verificados hasta el seq N." (no "N filas verificadas"); `--as` obligatorio y `--db-timeouts off` rechazado con `ENV=production` (S4A-D53, S4A-D95); `--wait-timeout` |
| US-106 Historial del socio | `GET /members/{id}/audit` por `subject_member_id` (ficha, membresías, pagos; incluye `reveal`); ítems con `fields` sin valores ni `before`/`after`; ningún valor cifrado; 404 / dado de baja con su historial; admin y coach con el mismo cuerpo, `member` 403; abrir la ficha no agrega entradas; `q` por parte local | entregada | B5 `8cf8ed9`, F2 `1ee7804`; `tests/audit/test_history_fields.py`, `test_member_history.py` (`test_total_se_satura_en_max_audit_offset_mas_uno`, `test_q_con_arroba_da_pagina_vacia_sin_buscar_usuarios`), `tests/members/test_router_member_audit.py` (`test_coach_y_admin_reciben_el_mismo_cuerpo`, `test_un_socio_dado_de_baja_devuelve_su_historial`, `test_leer_el_historial_no_agrega_entradas`), `tests/architecture/test_audit_subject.py`; `MemberHistoryTab.test.tsx`, `historyPhrase.test.ts`, `MemberDataTab.test.tsx`; `tests/e2e/stack/member-history.spec.ts`; vivo B5.8, V6 (coach = admin, 0 `@`/`apx1.`/`void_reason`), V7.4 (5 frases iguales para admin y coach) | Criterio 1 ampliado por N-31/G-05 (`subject_member_id`, no solo `table_name = members`); `void_reason`/`reference` ocultos también como nombre (S4A-D109); 404 antes que 422 (S4A-D111); `staff-read` (S4A-D45). Cierra el criterio diferido de US-066 |
| US-108 Contrato del tablero | `GET /dashboard` con `today`, cinco conteos, `income_month_cop`, `income_month`, `last_movements` y los cinco futuros presentes en `null`; conteos = `GET /memberships/summary`, ingresos = `GET /payments/summary`; mes de Bogotá; admin y coach, `member` 403; < 300 ms; `dashboard` sin `models` | entregada | B8 `8339138`; `tests/dashboard/test_service.py` (`test_los_conteos_son_los_del_resumen_de_membresias`, `test_borde_de_mes_cuenta_el_pago_de_la_noche_del_31_en_octubre`, `test_el_coach_recibe_los_mismos_conteos_sin_ingresos_y_sin_consultar_pagos`), `test_router.py`, `test_pure.py`, `test_perf.py` (`perf`, mediana 16,4–19,0 ms); `tests/architecture/test_read_modules.py`; vivo B8.10 y V7.5 (KPI = resumen, ingresos 14.152.000 = `/payments/summary`) | `income_month_cop` `null` para el coach (S4A-D118, ajusta S4A-D29); `staff-read` y 429 (S4A-D27, S4A-D45); el cuadre usa fábricas, no `seed --demo` (S4A-D29; T8 de US-109 a 4B) |
| US-109 KPI de membresías e ingresos | cuatro tarjetas con los valores y formato; `null` → estado vacío, nunca 0; enlaces a `/socios?membership_status=…` y `/pagos` del mes; pendientes de pago; carga y error con reintentar; coach y admin; `member` a `/mi`; **usable < 10 s con datos de demo (T8)** | **parcial (declarada)** | F3 `452d39e`; `web/src/features/dashboard/components/KpiGrid.test.tsx`, `FutureKpis.test.tsx`, `links.test.ts`, `pages/InicioPage.test.tsx`, `schemas.test.ts`; `tests/e2e/home.spec.ts` (preview, 11/11) y `tests/e2e/stack/home.spec.ts` (2/2 en F3.6, 40/40 ×2 en V4); vivo V7.5 | T8 (medición < 10 s y cuadre con datos de demostración, US-111) diferido al Sprint 4B (`SPRINT-04A.md` S4A-F3; desglose de US-109 línea 86). El coach ve "Solo administración" en ingresos, no la misma tarjeta (S4A-D118, S4A-D125); enlace de ingresos en días civiles (S4A-D121) |
| US-110 Últimos movimientos | ≤ 10 de `members`, `memberships` y `payments` por `seq` desc, sin `reveal`/`login`/`export`/`verify` ni el sistema; catálogo de frases; nombre + inicial; sin datos sensibles; monto en el servidor; vacío; < 300 ms con 100.000; solo por `audit.service.recent` | entregada | B8, F3; `tests/dashboard/test_movement_phrase.py` (24 casos, incluidos `test_actor_inexistente_se_nombra_alguien` y los de `with_amount=False`), `test_last_movements.py`, `tests/audit/test_recent.py` (perf con `EXPLAIN` por tabla), `tests/audit/test_diff.py` (`REDUCED_FIELDS`); `tests/architecture/test_read_modules.py`, `test_user_refs_scope.py`; `LastMovements.test.tsx`; vivo B8.10 y V7.5 (10 frases, 0 "Sistema", 0 `apx1.`) | Catálogo de S4A-D28 (la anulación de pago va sin monto; "vendió X a Y" en vez de "Se vendió…"); una consulta por tabla (S4A-D51); sin `SYSTEM_USER_ID` y límite tras excluir; plan de `members.members` por `uq_audit_log_seq` con muchas lecturas (S4A-D115, índice a 4B) |
| US-113 Proceso worker programado | `worker` arranca con `up` y la misma imagen; 07:00 Bogotá; `today_bogota()`; un job que lanza no detiene a los demás; `--run-once` 0/≠0; **logs JSON con `job`, `started_at`, `finished_at` (UTC), `duration_ms` y `result`**; recuperación de arranque tardío una sola vez; reintento de base con tope de 60 s | **parcial (no declarada)** | W0-1 `9cf519a`, B1 `dbc352e`, W0-2 `1df9c08`; `tests/worker/test_schedule.py`, `test_runner.py` (`test_el_segundo_job_corre_aunque_el_primero_lance`, `test_reinicio_a_las_nueve_sin_ciclo_corre_una_sola_vez`, `test_ni_el_log_ni_stdout_llevan_el_documento`), `test_main.py` (`test_wait_for_database_reintenta_1_2_4_con_tope_de_60`), `test_jobs_core.py`; `tests/migrations/test_0012_worker_job_runs.py`; `scripts/ci/test_compose_config.sh` (52 ok) y `compose-smoke.sh`; vivo W0-2.3/2.4, smoke V8, `apex-worker-1` healthy | **Criterio 6 sin cumplir y sin decisión:** el log `job finished` (`api/src/app/worker/runner.py:171-178`) lleva `job`, `run_date`, `result` y `error_type`; no lleva `started_at`, `finished_at` ni `duration_ms` (esos instantes quedan en `worker.job_runs` y en `--status`, no en el log). El desglose (T6, línea 91) los pedía; ninguna nota "Corregido en S4A-W0-1", decisión ni prueba lo cambia. Resto: latido en archivo (S4A-D8, S4A-D56), sin volúmenes y endurecido (S4A-D49), horario como constantes (S4A-D5) |

**Conteo: 12/14 entregadas, 2 parciales (US-109 con T8 diferido y declarado a 4B; US-113 con el criterio 6 de logs sin cumplir ni declarar), 0 no entregadas.**

## 2. Endpoints (10) y `active_members_count`

Contados con un script sobre `docs/openapi.json` frente al de `f5f2503`: **53 → 63 operaciones, 10 nuevas, 0 quitadas**. Toda operación nueva declara 500 y 503; todas salvo `GET /audit/verify/last` declaran 429. `PlanOut.active_members_count` es `integer` obligatorio.

| # | Ruta | Rol | Cubeta (429) | Respuestas en OpenAPI | Prueba de router | Smoke en vivo |
|---|---|---|---|---|---|---|
| 1 | `GET /audit` | admin | `staff-read` | 200, 401, 403, 422, 429, 500, 503 | `tests/audit/test_router_list.py` | B4.9; V7.3 |
| 2 | `GET /audit/verify/last` | admin | sin límite | 200, 401, 403, 500, 503 | `tests/audit/test_router_verify.py` (`test_last_sin_verificaciones_es_null_y_despues_la_ultima_sin_429`) | B3.14 |
| 3 | `GET /audit/{seq}` | admin | `staff-read` | 200, 401, 403, 404, 422, 429, 500, 503 | `tests/audit/test_router_get.py` | B4.9; V6 (`/audit/4772`); V7.3 |
| 4 | `POST /audit/verify` | admin | `audit-verify` + `audit-verify-hour` | 200, 202, 401, 403, 409, 429, 500, 503 | `tests/audit/test_router_verify.py` | B3.14; V4 y V8 (200 ×3, 429); V6; V7.3 |
| 5 | `GET /members/{member_id}/audit` | admin, coach | `staff-read` | 200, 401, 403, 404, 422, 429, 500, 503 | `tests/members/test_router_member_audit.py` | B5.8; V6; V7.4 |
| 6 | `GET /dashboard` | admin, coach | `staff-read` | 200, 401, 403, 429, 500, 503 | `tests/dashboard/test_router.py` | B8.10 (incluye 429 a la 121.ª); V6; V7.5 |
| 7 | `PATCH /plans/{plan_id}` | admin | `admin-write` | 200, 401, 403, 404, 409, 422, 429, 500, 503 | `tests/plans/test_router_update.py` | B7.9; V7.6 (pantalla); V8 (×2) |
| 8 | `POST /plans/{plan_id}/activate` | admin | `admin-write` | 200, 401, 403, 404, 422, 429, 500, 503 | `tests/plans/test_router_set_active.py` | **sin smoke propio** (ninguna spec `stack` ni demo llamó a `activate`; lo cubren la prueba de router y `PlansPage.actions.test.tsx`) |
| 9 | `POST /plans/{plan_id}/deactivate` | admin | `admin-write` | 200, 401, 403, 404, 422, 429, 500, 503 | `tests/plans/test_router_set_active.py` | B7.9; V7.6; V8 (×2) |
| 10 | `DELETE /plans/{plan_id}` | admin | `admin-write` | 204, 401, 403, 404, 409, 422, 429, 500, 503 | `tests/plans/test_router_delete.py` | B7.9; V7.6 (409 y 204); V8 (204, 404) |
| + | `active_members_count` en `GET /plans` y `GET /plans/{plan_id}` | admin, coach | — | `PlanOut` obligatorio | `tests/plans/test_service_list.py`, `test_router_list.py`, `tests/memberships/test_counts_active_by_plans.py` | B7.9 (`?limit=200`, toda fila entera); F4 demo ("Socios con él" = 1) |

Transversales: `tests/architecture/test_error_codes_per_route.py` (`CON_LIMITE`, `PLANES_B7`), `test_user_limits_catalog.py` (12 cubetas; `CLAVES_SIN_RUTA_TODAVIA` vacía), `test_writes_have_user_limit.py`, `test_every_route_has_role.py`, `test_no_store_routes.py`, `test_session_scope.py`, `test_audit_module.py` (orden `verify/last` antes de `{seq}`); `tests/core/test_openapi_export.py` 6/6 (B8.7).

**Conteo: 10/10 endpoints y 1/1 campo con prueba de router y fila en el contrato; 9/10 endpoints con smoke en vivo (falta `POST /plans/{id}/activate`).**

## 3. Migraciones (2)

| Migración | `down_revision` | Prueba | Ciclo en `apex-db-1` | Volcado previo |
|---|---|---|---|---|
| `0012_worker_job_runs` | `0011_payments_immutability` | `tests/migrations/test_0012_worker_job_runs.py` (25), `tests/core/test_migrations.py` | B1.10 (`downgrade -1` → `upgrade head`) y V2.5 (`downgrade 0011` → `upgrade head`, con `$DC stop worker` antes, E4) | `docs/scratch/sprint-04a-antes-0012.dump` (W0-1.2) |
| `0013_audit_verifications` | `0012_worker_job_runs` | `tests/migrations/test_0013_audit_verifications.py` (22), `test_triggers_siempre_activos.py` (+3) | B3.14 (sin parar el worker, E4) y V2.5 | `docs/scratch/sprint-04a-antes-0013.dump` (B3.1) |

V2.4: `pytest tests/core/test_migrations.py tests/migrations` → 244 ok (incluye `test_downgrade_a_base_vacia_y_vuelta_a_head`, `test_single_head`). `alembic heads` una sola. Comprobado por mí: `alembic current` en `apex-api-1` = `0013_audit_verifications (head)`; `audit.verifications` con sus dos triggers en `A` y `audit.audit_log` con los suyos en `O` (S4A-D98). Los dos volcados **siguen en disco** (comprobado con `ls`), ignorados por `.gitignore:46`: se borran en V12 (V10 L-4).

**Conteo: 2/2.**

## 4. Condiciones para VERDE del impacto (C1–C13, `docs/ddd/impacto/sprint-04a.md` §9) y su paso (plan §10)

| # | Condición | Estado | Dónde |
|---|---|---|---|
| C1 | B1: `test_audited_tables`, `test_core_import_direction`, `conftest` (`LIMPIAR_JOB_RUNS`), `env.py`, `omit` fuera, `core/alerts.py` mínimo, horario como constantes | cumplida | pasos 11–17; cuaderno 45–76; `test_worker_boundaries.py` (S4A-D73); `api/pyproject.toml` sin `omit`; `worker/schedule.py:26` |
| C2 | W0-1 healthcheck sin HTTP con perfil; W0-2 sin perfil, aserción invertida, smoke con `--run-once`, buildx, binds de desarrollo | cumplida | pasos 3–5, 22–27; `test_compose_config.sh` 52 ok; `compose-smoke.sh` (S4A-D86, S4A-D87); cuaderno 107–132 |
| C3 | B2: privado en `PRIVATE_HELPERS`, sin `with_for_update`, lote por socio, `dos_sesiones`, eventos en `SUSCRIPTORES_ESPERADOS`, `perf`, CLI con `--date --simulate` y `--as` | cumplida | pasos 29–33; `test_guarded_calls.py::test_expirations_no_llama_with_for_update`, `test_handlers_no_new_locks.py`, `test_recompute_lock_order.py`; cuaderno 134–175 |
| C4 | B3: `test_audit_module`, `EXCLUIDAS`, `test_no_physical_delete`, limpieza de `verifications`, `verify_chain` ampliada, candado y SQL constante, 202 a mano, 429 y `CON_LIMITE`, `table_name="audit.verifications"`, CLI con salidas 0/1/2 | cumplida con desviación declarada | pasos 40–50; la condición pedía `admin-write`: manda S4A-D47 (`audit-verify`, contradicción 1) |
| C5 | B4: `PageParams`, `q: SearchQuery`, búsqueda parcial por correo en `auth`, `{seq}` tras `verify/last`, privados de `audit` | cumplida | pasos 54–58; `auth.service.search_user_ids`; `test_audit_module.py` |
| C6 | B5: ruta en `members/router.py`, arista `members → audit`, `q`, sin `user_email`, `test_audit_subject.py`, renombre de la prueba de congelaciones | cumplida | pasos 64–67; `test_service_import_graph.py`, `test_audited_tables.py::..._por_decision_s4a_d20` |
| C7 | B6: `detail._decrypt_fields` con propósito, `audit.record` directo, `test_crypto_bus_importers.py`, `contact.py` privado | cumplida con matiz | pasos 73–75; sin `bus.batch` (S4A-D21) e importadores reales con `ARRANQUE` (S4A-D113) |
| C8 | B7: `admin-write`, 429 y `CON_LIMITE`; perezosa con marca; sin `Membership`; `changed_fields` solo nombres; código del 409 en el front; "Socios con él" | cumplida | pasos 79–83; `counts_active_by_plans` (S4A-D25); `errorCodes.ts` `planHasActiveMemberships` (F4.1) |
| C9 | B8: `MODULES` + `dashboard`, aristas reales, router con `no_store`/`StaffDep`, `test_read_modules.py`, vista reducida; decisión de `display_name` | cumplida | pasos 54, 57, 89, 90, 93; opción (b) sin columna (S4A-D19, S4A-D54, S4A-D108) |
| C10 | Front: features, rutas, menú, DESIGN-GAP, hija `/socios/:id/historial`, `audit-labels.ts`, `InicioPage`, acciones de planes, P-API por slice | cumplida | pasos 100–122; cuaderno del front F1.1–F3.5; `BRECHAS.md` §11 (V1, `79e5204`) |
| C11 | Volcados antes de cada migración y borrado al cierre; ciclo en `db_test` y `apex-db-1`; una cabeza; RUNBOOK §6 | **cumplida salvo el borrado de los volcados (V12)** | pasos 2, 14, 20, 39, 44, 52, V2; los dos `.dump` siguen en `docs/scratch/` |
| C12 | `omit` fuera en B1; `run-gates.sh` al cerrar B2 y B3 | cumplida | B2.8 (4.121 ok, 96,54 %), B3 C12 (4.241 ok, 97 %), B8.9.1 (4.992 ok, 96,79 %); V9 en curso |
| C13 | T-DOC y cierre de la revisión de diseño previa | cumplida | W0-1.6 (113 notas en 14 desgloses); `DECISIONES.md` §"Resueltos en S4A-W0-1"; `BRECHAS.md` §10.14 y §11 |

**Conteo: 12/13 cumplidas y 1 en parte (C11: falta borrar los volcados, que es paso de V12).**

## 5. Revisión de seguridad del diseño (`sprint-04a-seguridad-diseno.md`)

| ID | Slice | Estado | Prueba o evidencia que lo cierra |
|---|---|---|---|
| H-1 cola perdida sin detección | B3 | cerrado | S4A-D43, S4A-D99; `core/audit_verify.py` (`_check_anchor`, `_verified_through_hash`); `tests/audit/test_verify.py` (`test_h1_cola_borrada_tras_una_verificacion_ok_da_rota`, `test_h1_cola_reemplazada_por_una_cadena_valida_pero_distinta_da_rota`, `test_una_verificacion_rota_no_mueve_el_ancla`); vivo V6 (`through_hash` en `audit.verifications` y en el log `audit anchor`) |
| H-2 candado de sesión en conexión transaccional | B3 | cerrado | S4A-D44, S4A-D100, S4A-D101; `modules/audit/verify.py` (`AUTOCOMMIT`, `invalidate`, `_TASK_LOCKS`); `tests/audit/test_verify_concurrency.py` (13), `tests/cli/test_verify_audit.py::test_la_conexion_del_candado_es_autocommit_e_invalidada`; `test_guarded_calls.py` (`AUTOCOMMIT_PERMITIDO` por ruta, E10) |
| M-1 lecturas sin cubeta | B3, B4, B5, B8 | cerrado | S4A-D45; `core/ratelimit.py:327`; pruebas de 429 en `test_router_list.py`, `test_router_member_audit.py::test_la_121_del_minuto_da_429_y_otro_usuario_pasa`, `tests/dashboard/test_router.py`; vivo B8.10 |
| M-2 filtros sin acotar | B4 | cerrado | S4A-D46, S4A-D66; `core/validators.py:117` (`check_instant_range`), `MAX_SEQ`, `TABLE_PATTERN`; `tests/core/test_validators.py`, `tests/audit/test_filters.py`; vivo B4.9 (cuatro 422) |
| M-3 `verify` repetida y cubeta compartida | B3 | cerrado | S4A-D47, S4A-D120, S4A-D127; `test_router_verify.py` (`test_la_cuarta_peticion_del_minuto_da_429`, `test_la_peticion_21_de_la_hora_da_429`); vivo V4 y V8 (429 a la 4.ª). Residual: ver riesgo R-3 (pausa del GC en el proceso del api) |
| M-4 `--date` sobre la base real | B1, B2, W0-1 | cerrado | S4A-D48, S4A-D63, S4A-D75, E5; `tests/worker/test_main.py` (`test_guarda_dura_de_date`, `test_date_con_simulate_contra_la_base_viva_da_2`); vivo V7.2 (dos rechazos con salida 2 sobre `apex`); comprobado por mí: 0 filas `*_sim` en `apex-db-1` y `max(at) <= now()` |
| M-5 worker con más de lo que necesita | W0-1, W0-2 | cerrado con residual y dueño | S4A-D49; `infra/compose.yml` (sin `ports`, sin `volumes`, `read_only`, `cap_drop`, `no-new-privileges`); `test_compose_config.sh`; residual: el worker recibe todo `.env` y usa la credencial del api (B1 L-5) → S4B-W0-2 |
| M-6 `contact_for_notification` sin cerco | B6, B5 | cerrado | S4A-D50; `test_contact_callers.py` (más el endurecimiento de B6 LOW 1); `MemberHistoryItem.purpose` |
| M-7 `recent` sin índice | B8 | cerrado con residual y dueño | S4A-D51, S4A-D115, S4A-D119 b; `tests/audit/test_recent.py` (perf, `EXPLAIN` sin `Seq Scan`, < 50 ms); índice `(table_name, action, seq DESC)` a 4B |
| L-1 blobs al navegador | B4, F1 | cerrado | S4A-D52, S4A-D105, S4A-D107; `test_get.py`, `encryptedBlob.test.ts` |
| L-2 `--as` y `--db-timeouts off` | B2, B3 | cerrado | S4A-D53, S4A-D95; `test_verify_audit.py` (`test_en_produccion_sin_as_sale_2`, `..._con_db_timeouts_off_sale_2`), `test_recompute_memberships.py` |
| L-3 parte local del correo | B4, B5, B8 | cerrado con regresión consciente y dueño | S4A-D54, S4A-D108; `tests/architecture/test_user_refs_scope.py`; columna de nombre en v0.2 (EP-04) |
| L-4 `core/jobs` (actor, `stale_after`, `shield`, `details`) | B1 | cerrado | S4A-D55, S4A-D77; `test_jobs_core.py`, `test_runner.py::test_el_job_escribe_como_usuario_del_sistema_con_lote`, `test_schedule.py::test_running_de_hace_31_minutos_esta_muerto_y_corre` |
| L-5 latido sin base | B1 | cerrado | S4A-D56; `test_main.py::test_touch_heartbeat_con_la_base_caida_no_escribe_ni_propaga` |
| L-6 fase 1 abierta y esperas dentro de la transacción | B2 | cerrado | S4A-D57; `tests/architecture/test_expirations_lock_order.py` (7) |
| L-7 front de auditoría | F1 | cerrado | S4A-D58, S4A-D122; `auditFilters.test.ts`, `AuditDetailPanel.test.tsx`, `VerifyChainButton.test.tsx` |
| L-8 `datosDeBase()` y specs | W0-2, F1, F3 | cerrado | S4A-D59; `grep -rn "job_runs\|audit_log" web/tests` vacío (W0-2.1, F1, F3.6) |
| L-9 planes (precio vigente, 409 con conteo, limpieza P2-1 por API) | B7, V12 | **cerrado en código; la limpieza P2-1 está en ejecución (V12)** | S4A-D60; `test_rn04_plan_price_change.py`; RUNBOOK §11 "Limpieza P2-1". Comprobado por mí: a las 10:35Z otra sesión estaba dando de baja planes por la API (`audit.audit_log` seq 5226 en adelante, `update plans.plans` cada ~4 s); quedaban 171 planes activos |
| L-10 reglas hacia adelante | B4, B8 | cerrado | S4A-D61; `test_settings_no_secrets.py` (+2), `test_audited_tables.py` (+5, `AUDITABLE_TABLES` / `RECENT_TABLES_ALLOWED`) |

**Conteo: 19/19 cerrados en código (H 2/2, M 7/7, L 10/10); 3 con residual aceptado y dueño (M-5, M-7, L-3); L-9 con su parte operativa (P2-1) en curso dentro de V12.**

## 6. Decisiones S4A-D1…S4A-D127 (`DECISIONES.md`, líneas 1101–1306)

Una fila por decisión. "Código" lleva archivo y prueba; "documental" es una decisión de proceso o de documento; "aceptada" es un riesgo con dueño. Las líneas de código de S4A-D75…S4A-D120 coinciden con las que V10 comprobó una a una (cuaderno 782–792).

| Decisión | Tipo | Evidencia |
|---|---|---|
| D1 `status` espejo, lecturas derivadas, eventos sin suscriptores | código | `memberships/events.py`; `test_expirations.py::test_los_eventos_de_transicion_no_tienen_suscriptores`, `test_el_resumen_de_membresias_no_cambia_con_el_job` |
| D2 dos fases, transacción por socio | código | `memberships/expirations.py` (`RECOMPUTE_PAGE = 200`, `MAX_BUSY_RETRIES = 2`); `test_recompute_lock_order.py` |
| D3 `claim_run`/`finish_run`, idempotencia `(job_name, run_date)` | código | `core/jobs.py:180,255`; `uq_job_runs_name_date` (`0012`); `test_jobs_core.py` |
| D4 `--date` (reemplazada por D48) | código | códigos 0/1/2/3 en `test_main.py` (`test_run_once_con_una_corrida_vigente_da_3`) |
| D5 horario como constantes | código | `worker/schedule.py:26`; `test_schedule.py::test_constantes_del_horario` |
| D6 estructura y arranque | código | `worker/{schedule,registry,runner,runtime,main}.py`; `test_main.py::test_en_un_proceso_limpio_run_once_carga_los_services` |
| D7 `core/alerts.py` mínimo | código | `core/alerts.py:23` (`ALERT_CONTEXT_KEYS`); `tests/core/test_alerts.py` (15) |
| D8 latido en archivo | código | `worker/runtime.py` (`HEARTBEAT_PATH`); healthcheck de `infra/compose.yml`; vivo `apex-worker-1` healthy |
| D9 compose, perfil, binds, smoke, CI | código | `infra/compose.yml`, `compose.dev.yml:21-32`; `test_compose_config.sh`; perfil quitado en W0-2 |
| D10 fronteras del worker | código | `tests/architecture/test_worker_boundaries.py` (7) |
| D11 `verify_chain` con continuación | código | `core/audit.py:234`; `tests/core/test_verify_chain.py` |
| D12 `core/audit_verify.py` | código | `core/audit_verify.py`; `test_core_import_direction.py` |
| D13 candado y topes (corregida por D44/D47/D91/D120) | código | `audit_verify.py:47,50,52`; `verify.py:49` |
| D14 contrato HTTP 200/202/409 | código | `test_router_verify.py` (OpenAPI con 202, 409, 429) |
| D15 CLI `verify-audit` y `recompute-memberships`; `cli_ops.py` > 760 | código | `cli.py:542,601,692`; `cli.py` mide 760 líneas (comprobado): no se extrajo `cli_ops.py` |
| D16 un contrato de filtros | código | `audit/schemas.py` (`AuditListQuery`); `test_filters.py` |
| D17 detalle sin descifrar (corregida por D52) | código | `test_get.py::test_el_servicio_no_descifra_nunca` |
| D18 `audit` partido | código | `PRIVATE_HELPERS["audit"] = {verify, queries, diff}`; `test_no_cross_models.py` |
| D19 `display_name` sin columna | código | `auth/users.py` (`SYSTEM_DISPLAY_NAME`); `tests/auth/test_user_refs.py`; columna a v0.2 |
| D20 historial del socio | código | `audit/queries.py::member_history`; `test_member_history.py` |
| D21 firma de `contact_for_notification` | código | `members/contact.py`; `test_service_contact.py` |
| D22 `PATCH /plans` | código | `plans/service.py::update`; `test_service_update.py` |
| D23 activar/desactivar por `POST` | código | `plans/router.py`; `test_router_set_active.py` |
| D24 `DELETE` y `pending_payment` | código | `test_service_deactivate_or_fail.py::test_una_membresia_activa_por_estado_efectivo_bloquea_la_baja` |
| D25 "Socios con él" | código | `memberships/queries.py:588`; `test_counts_active_by_plans.py`; columna en `PlansPage.test.tsx` |
| D26 cubetas (corregida por la contradicción 1) | código | `core/ratelimit.py:316-330` (12 cubetas) |
| D27 contrato de `/dashboard` | código | `dashboard/schemas.py`; `test_router.py::test_el_cuerpo_tiene_las_claves_del_contrato_y_los_futuros_en_null` |
| D28 últimos movimientos (con D51, D61) | código | `dashboard/service.py`; `test_movement_phrase.py` |
| D29 roles y KPI (ajustada por D118) | código | `test_router.py::test_admin_y_coach_reciben_200_con_el_mismo_cuerpo_salvo_las_finanzas` |
| D30 features, rutas y menú | código | `config/features.test.ts`, `routes.test.ts`, `layouts/nav.test.ts` (F1.2) |
| D31 pantalla de auditoría | código | `AuditPage.test.tsx` y compañía (F1) |
| D32 historial unificado | código | `audit-labels.test.ts`, `HistoryAside.test.tsx`, `MemberHistoryTab.test.tsx` (F2) |
| D33 Inicio | código | `KpiGrid.test.tsx`, `FutureKpis.test.tsx`, `LastMovements.test.tsx` (F3) |
| D34 planes en el front | código | `PlanForm.edit.test.tsx`, `PlansPage.actions.test.tsx`, `PlansPage.delete.test.tsx` (F4) |
| D35 mutaciones, códigos y contrato | código | `tests/lint/sensitive-mutations.test.ts` (sin tocar la lista blanca); `errorCodes.test.ts`; `types.contract.test.ts` |
| D36 DESIGN-GAP y `BRECHAS.md` §11 | documental | `BRECHAS.md` §11.1–11.4 (V1, `79e5204`) |
| D37 pruebas de arquitectura por Rojo | documental | Rojo de cada slice en el cuaderno (B1.2, B2.2, B3.4, B4.2, B5.2, B6.2, B7.2, B8.2) |
| D38 migraciones | código | sección 3 |
| D39 cobertura y `run-gates.sh` | código | `omit` fuera (B1.7); `run-gates.sh` en B2.8, B3, B8.9.1; V9 en curso |
| D40 `slice-gate.sh` sin cambios | documental | verificado en el plan; gates sellados en cada slice |
| D41 correcciones T-DOC | documental | 113 notas en 14 desgloses (W0-1.6) |
| D42 orden de slices y reconstrucción | documental | checkpoints en el orden de §3 del plan; fusiones `f0d274f`, `a54a0be`, `c8f8abd`, `e36fff6` |
| D43 ancla `through_hash` | código | H-1; residual sin firma externa hasta v0.3 (D92, aceptada) |
| D44 `AUTOCOMMIT` + `invalidate` | código | H-2 |
| D45 `staff-read` y `MAX_AUDIT_OFFSET` | código | M-1 |
| D46 rangos acotados | código | M-2 |
| D47 cubetas de verificación y lote | código | M-3 |
| D48 guarda de `--date` | código | M-4 |
| D49 worker sin volúmenes, endurecido | código + aceptada | M-5; residual de credencial → S4B-W0-2 |
| D50 cerco de `contact_for_notification` | código | M-6 |
| D51 `recent` por tabla | código | M-7 |
| D52 marcador en el detalle | código | L-1 |
| D53 `--as` en producción | código | L-2 |
| D54 `user_names_for` / `user_refs_for` | código | L-3; `test_user_refs_scope.py` (6) |
| D55 actor antes del reclamo, `shield` | código | L-4 |
| D56 latido condicionado | código | L-5 |
| D57 fase 1 cerrada, esperas fuera | código | L-6 |
| D58 front de auditoría | código | L-7 |
| D59 specs sin `job_runs`/`audit_log` | código | L-8 |
| D60 precio vigente; 409 con conteo; P2-1 por API | código + aceptada | L-9; P2-1 en V12 |
| D61 sin secretos en settings; tablas auditables únicas; lectura no auditada | código + aceptada | L-10 |
| D62 front en worktree | documental | cuaderno del front; `git worktree list` solo el principal (comprobado) |
| D63 demo con fecha sobre `apex_sim` | código + proceso | B2.9 y V7.2 (`apex_sim` creada y borrada; 0 en `pg_database`, comprobado) |
| D64 job marcador en B1 | código | B1.10 y W0-2.4 (`{"placeholder_ok": 1}`); reemplazado en B2 |
| D65 las tres cubetas nacen en B3 | código | `.env.example`, `config.py`, `ci.yml` (11 variables, V4) |
| D66 `check_instant_range` | código | `core/validators.py:117`; `test_validators.py` (`PAID_AT_FLOOR == INSTANT_FLOOR`) |
| D67 `tests/integration/` | código | `api/tests/integration/{__init__,conftest}.py` |
| D68 corridas `perf` | proceso | cinco archivos `perf` corridos en su slice y en V5 (cuaderno 653–662) |
| D69 fábrica de cadena | código | `tests/factories/audit_chain.py` |
| D70 limpieza de `db_test` | código | `LIMPIAR_JOB_RUNS`, `LIMPIAR_VERIFICATIONS` en `tests/conftest.py` |
| D71 admin desechable | proceso | `admin-e2e-1793249495@apex.test` (sigue activo; 1 fila viva comprobada); se borra en V12 |
| D72 tamaños y particiones | código | `cli.py` 760, `plans/service.py` 506; `test_file_and_function_size.py` |
| D73 regla de importadores de `core.jobs` | código | `test_worker_boundaries.py` |
| D74 `audit.verifications` en `test_no_physical_delete` | código | `test_no_physical_delete.py` (B3.4) |
| D75 `--simulate` de hoy también con guarda | código | `worker/runtime.py:217`; `test_main.py::test_simulate_con_la_fecha_de_hoy_tambien_exige_dev_y_base_de_simulacion` |
| D76 `check_details` pública | código | `core/jobs.py:235`; `test_runner.py:330` |
| D77 cierre condicionado (`lost_claim`) | código | `core/jobs.py:259-292`; `test_jobs_core.py:276` |
| D78 rastro `stale` y cierre en una sentencia | código | `core/jobs.py:75,87,172`; `test_attempts_path_recorta_a_max_attempts` |
| D79 el ciclo no repite un día cerrado | código | `core/jobs.py:187,206`; `test_main.py::test_recuperacion_y_disparo_concurrentes_no_se_solapan_y_corren_una_vez`; vivo W0-2.4 y B2.9 paso 2 |
| D80 `finished_at = greatest(...)` | código | `core/jobs.py:259-292` |
| D81 reclamo ocupado | código | `core/db.py:177` (`BUSY_SQLSTATES`); pruebas 55P03/08006 |
| D82 `alert()` valida valores | código | `core/alerts.py:44-61`; `test_alerts.py:113,154` |
| D83 `--run-once` con la base caída | código | `worker/main.py:137`; `test_main.py::test_run_once_con_la_base_caida_al_cerrar_sale_1_sin_traza` |
| D84 fallos del ciclo solo con el tipo | código | `worker/runtime.py:176`, `worker/main.py:187`; dos pruebas en `test_main.py` |
| D85 `type: ignore` de apscheduler; `CycleTasks` en `runtime.py` | código | `worker/runtime.py` |
| D86 smoke comprueba `config --services` | código | `compose-smoke.sh:73` |
| D87 forma del smoke; excepción de los `print` | código + documental | `compose-smoke.sh:79,94`; comentarios en `worker/main.py` (`360d816`) |
| D88 la CI no cambia | documental | `ci.yml` `e2e-stack` con `up -d --build` |
| D89 `--simulate` por el runner; `--simulate` con `--as` rechazado | código | `cli.py`; `test_recompute_memberships.py::test_simulate_con_as_sale_2_sin_tocar_nada` |
| D90 medida de `cli.py`; log fuera del `except`; fixture de handlers | código | `tests/cli/conftest.py::sin_handlers_sobre_flujos_cerrados` |
| D91 `SYNC_VERIFY_MAX_ROWS` 100.000 | código | `modules/audit/verify.py:49` |
| D92 residual del ancla hasta v0.3 | aceptada con dueño | RUNBOOK §11 (copiar la línea `audit anchor` junto al respaldo); dueño v0.3 `sign-audit` |
| D93 `last_seq`/`last_hash` fuera de la igualdad | código | `core/audit.py:155-156`; `test_audit_chain.py` sin cambio |
| D94 sentencias compiladas | código | `audit_verify.py:56-57`; `test_sql_literals_constant.py` |
| D95 guarda de producción compartida | código | `cli.py:601` |
| D96 fallos fuera del `except` | código | `verify.py:98-126`; `test_verify_concurrency.py` |
| D97 CHECKs de `0013` | código | `0013_audit_verifications.py:54`; `test_0013_audit_verifications.py` |
| D98 triggers de `audit_log` en `O` | aceptada con dueño | Sprint 4B `0014_audit_log_triggers_always`; confirmado en vivo por mí (`tgenabled = 'O'`) |
| D99 `through_hash` del recorrido; lote vacío = ruptura | código | `audit_verify.py:186-192,232`; `test_verify.py` |
| D100 plazo síncrono 45 s | código | `verify.py:55`; `test_si_la_rama_sincrona_vence_sigue_en_segundo_plano_con_el_candado` |
| D101 candado de tarea cancelada | código | `verify.py:61,205`; `test_una_tarea_cancelada_antes_de_empezar_suelta_e_invalida_el_candado` |
| D102 auditoría una sola vez al final | código | `core/audit.py:68`; `test_run_verification_escribe_auditoria_una_sola_vez_y_al_final` |
| D103 cubetas en memoria del proceso | **aceptada sin sprint dueño** | RUNBOOK §11; "sin dueño de código hasta que el api pase a varios procesos" (`SPRINT-04A.md:303`) |
| D104 `q` UUID frente a `record_id` | código | `test_filters.py` |
| D105 `apx1.` mal formado tapado | código | `diff.py`; `test_filters.py` |
| D106 conteo con índice y acotado | código + aceptada | (a)(b) `queries.py::build_audit_filters`, `core/pagination.py:101-108`, `test_list_performance.py` (`EXPLAIN`); (c) índices → Sprint 4B |
| D107 endurecimiento del marcador y `MAX_DEPTH` | código | `diff.py`; pruebas de 40 niveles |
| D108 parte local = PII parcial | aceptada con dueño | v0.2, EP-04 |
| D109 `void_reason`/`reference` ocultos como nombre | código | `diff.py` (`HIDDEN_HISTORY_FIELDS`); `test_history_fields.py` |
| D110 `total` del historial saturado | código | `test_member_history.py::test_total_se_satura_en_max_audit_offset_mas_uno` |
| D111 404 antes que 422 | código | `test_router_member_audit.py::test_socio_inexistente_con_offset_fuera_de_rango_da_404` |
| D112 `q` con `@` no busca | código | `queries.py:95,244`; `test_q_con_arroba_da_pagina_vacia_sin_buscar_usuarios` |
| D113 importadores reales del bus | código | `test_crypto_bus_importers.py` (8) |
| D114 `null` explícito en `PATCH` | código | `test_merge_plan.py` (4 casos) |
| D115 plan de `recent` en `members.members` | código + aceptada | `test_recent.py::test_cada_consulta_por_tabla_va_por_indice_sin_seq_scan`; índice → Sprint 4B |
| D116 actor inexistente y pago sin monto | código | `test_movement_phrase.py::test_actor_inexistente_se_nombra_alguien`, `test_insert_de_pago_sin_monto_entero_usa_la_frase_generica` |
| D117 forma interna de frases y `recent` | código | `dashboard/service.py`, `audit/queries.py::recent`; `test_recent.py` |
| D118 coach sin finanzas | código | `dashboard/service.py:75,231` (`FINANCE_ROLES`); `test_service.py`, `test_router.py`; vivo B8.10, V6 |
| D119 notas de B8 (sin caché de pagos; `recent` con escrituras del sistema) | aceptada + código | RUNBOOK §11; `test_recent_con_5_mil_escrituras_recientes_del_sistema_sin_seq_scan_y_bajo_50_ms` |
| D120 lote 500 por rango acotado | código | `audit_verify.py:47,201-243`; `test_hueco_que_cubre_un_lote_entero_rompe_en_la_fila_siguiente` |
| D121 enlace de ingresos en días civiles | código | `web/src/features/dashboard/links.ts`; `links.test.ts` |
| D122 marcador y sondeo en el front | código | `encryptedBlob.ts`, `useLastVerification`; `VerifyChainButton.test.tsx` (sondeo detenido con 429) |
| D123 historial en el front | código | `MemberHistoryTab.test.tsx`, `MemberDataTab.test.tsx` |
| D124 acciones de planes en el front | código | `PlansPage.actions.test.tsx` (doble clic: una petición) |
| D125 tablero en el front | código | `KpiGrid.test.tsx` ("Solo administración"), `schemas.test.ts` (`.strict()`) |
| D126 `setup` y tipos de axe en los gates | proceso | líneas de gate del cuaderno del front (F1.5–F3.5) |
| D127 perf con `gc.freeze()` | código | `tests/audit/test_verify_performance.py` (`360d816`); 17,9–23,2 ms de peor bloque |

**Conteo: 127/127 con evidencia** (S4A-D31…S4A-D35 no tienen línea propia en `DECISIONES.md`: van agrupadas en "S4A-D30 a S4A-D36"; su contenido está en el blueprint y en el front). Ocho aceptadas con dueño (D43/D92, D49, D60, D98, D106 c, D108, D115, D119) y **una aceptada sin sprint dueño (D103)**.

## 7. Enmiendas de la crítica 1 (E1…E10)

| Enmienda | Estado | Evidencia |
|---|---|---|
| E1 una sola forma del marcador | aplicada | B1.1 (`jobs/expirations.py` real), W0-1.6; `DECISIONES.md` contradicción 12 |
| E2 claves de `RecomputeSummary` ⊆ `DETAIL_KEYS` | aplicada | `test_expirations.py` (forma de `RecomputeSummary`, B2.3) |
| E3 orden de evidencia de B2.9 | aplicada | cuaderno 183–198 (psql antes, `start worker`, `--status`, corrida) |
| E4 parar el worker antes de un `downgrade` | aplicada | B3.14 (no hizo falta, anotado) y V2.5 (`$DC stop worker` / `start`, `RestartCount` 0) |
| E5 guarda dura de `--date` | aplicada | `test_main.py::test_guarda_dura_de_date`; V7.2 (salida 2 ×2 sobre `apex`) |
| E6 primera invocación 0 o 3 | aplicada | `compose-smoke.sh` (S4A-D87); smoke de W0-2 y V8 |
| E7 `--run-once` en el contenedor endurecido | aplicada | B1.10 paso 6 |
| E8 `MemberDataTab.test.tsx` y `audit.spec.ts` de preview | aplicada | F1.2 (decisión E8), F2.2 (7/7 rojos) |
| E9 `grep -cE` de la CI a 11 | aplicada | B3.8; V4 (`ci.yml:294-295` espera 11) |
| E10 `AUTOCOMMIT` y excepción por ruta | aplicada | `test_guarded_calls.py` (`AUTOCOMMIT_PERMITIDO`, controles negativos) |

**Conteo: 10/10.**

## 8. Deuda heredada del Sprint 3 con dueño 4A y contradicciones de contrato

### 8.1 Deuda heredada ("Dueños asignados al cierre del Sprint 3" y plan §10)

| Ítem | Estado | Evidencia |
|---|---|---|
| `display_name` (US-110) | diferido con dueño, decisión tomada | S4A-D19/D54/D108: parte local del correo en 4A; columna en v0.2 con EP-04 |
| "Socios con él" y `count_active_by_plan` visible | cerrado | B7/F4; `active_members_count` |
| `plans.update` sin bloquear `memberships` | cerrado | `FOR UPDATE` solo del plan; `test_service_update.py` |
| Job de vencimientos y eventos (US-094) | cerrado | B2 |
| Historial de la ficha y congelaciones sin `subject_member_id` (US-106) | cerrado | B5 (por el `update` de la membresía, S4A-D20); F2 |
| `omit` de `cli.py` y `worker/` en la cobertura | cerrado | B1.7; `run-gates.sh` sin `omit` 96,54–97 % |
| P2-1 (`DELETE /plans/{id}` y limpieza) | código cerrado; **limpieza en curso (V12)** | B7; 171 planes activos a las 10:36Z mientras otra sesión daba de baja |
| Borrado de volcados | **pendiente (V12)** | dos `.dump` en `docs/scratch/` |
| S3-D98 y "Pendientes de diseño" de §10 (revisión de diseño previa al 4A) | cerrado | `BRECHAS.md` §10.14 y §11; S3-D98 a backlog v0.2 con EP-16 |
| W0-2 MEDIUM-1/-2 del Sprint 3 | sin cambio, dueño S4B-W0-2 | `DECISIONES.md:1093-1094` |

### 8.2 Contradicciones resueltas del plan (sección 1, 12) y de contrato

Las 12 contradicciones del plan quedaron en `DECISIONES.md:1105-1118` y el código sigue la versión ganadora: (1) tres cubetas nuevas, `ratelimit.py:327-329`; (2) `--date` con `--simulate`, E5; (3) ancla, `AUTOCOMMIT`, lote 500, umbral 100.000; (4) worker sin volúmenes; (5) `user_names_for`/`user_refs_for`; (6) `recent` por tabla; (7) `test_contact_callers.py` y `purpose`; (8) actor antes del reclamo; (9) `grep` de `web/tests`; (10) marcador; (11) rangos en `core/validators.py`; (12) marcador del job en B1. Las de T-DOC (S4A-D41 y las de este plan, `DECISIONES.md:1192`) se cerraron como notas en los 14 desgloses (W0-1.6) y en `SPRINT-04A.md` (cabecera). **Conteo: 12/12 resueltas; T-DOC aplicado.**

## 9. Hallazgos de las revisiones por slice y de V10

| Revisión | Resultado | Cierre |
|---|---|---|
| B1 `database-reviewer` (2 M, 2 L) y `security-reviewer` (1 M, 5 L) | corregidos 8 de 9 | S4A-D77…S4A-D84; L-5 (worker con todo `.env`) aceptado con dueño S4B-W0-2 |
| B2 `security-reviewer` (3 L) | corregidos | `--simulate --as` rechazado; fixture de handlers; RUNBOOK §11 (caché del resumen) |
| B3 `database-reviewer` y `security-reviewer` (1 M + 1 MEDIA, 4 L) | corregidos 6; 2 aceptados | S4A-D99…S4A-D102; D98 con dueño 4B; **D103 restricción conocida sin sprint dueño** |
| B4 `security-reviewer` (1 M, 3 L) | corregidos | S4A-D106 (a, b; c a 4B), S4A-D107, S4A-D108 |
| B5 `security-reviewer` (2 L) | corregidos | S4A-D112; constancia en S4A-D54 |
| B6 `security-reviewer` (3 L) | corregidos | `test_contact_callers.py`, `test_crypto_bus_importers.py`, `Contact.__reduce__` |
| B7 `security-reviewer` (2 L) | aceptados con constancia | S4A-D22 (`existing_id`), pruebas existentes de idempotencia |
| B8 `security-reviewer` (1 M, 2 L) | M corregido; L aceptados | S4A-D118; S4A-D119 a/b |
| F1 (1 M, 3 L) | corregidos | `VerifyChainButton.test.tsx`, `AuditDetailPanel.test.tsx` |
| F2 (2 L) | corregidos | `MemberHistoryTab.test.tsx`, `audit-labels.test.ts` |
| F4 (3 L) | corregidos | `PlansPage.test.tsx`, `PlansPage.actions.test.tsx`, `PlansPage.delete.test.tsx` |
| F3 (2 M, 3 L) | corregidos | `schemas.test.ts`, `LastMovements.test.tsx`, `format.test.ts` |
| V10 (0 C, 0 H, 0 M, 4 L + 1 nota) | L-1, L-2, L-3 corregidos en `360d816`; L-4 en V12 | L-4: volcados todavía en disco; **la nota informativa (`sessionStorage` en `RouteError.tsx`, "permitirlo explícitamente en el lint") no tiene dueño ni decisión** |
| V6 (texto de `forbid_mutation`) | aceptado con dueño | Sprint 4B junto a `0014_audit_log_triggers_always` |
| Observación de F2 (Tabs a 1440 px, contraste de "automático (aviso)") | con dueño | Sprint 4B, `DECISIONES.md:1304-1306` |

0 CRITICAL y 0 HIGH en todo el sprint. **Sin cierre o sin dueño concreto: D103 (cubetas en memoria) y la nota de `sessionStorage`; los dos son WARNING explícitos.**

## 10. Validación V1–V12

| V | Estado | Evidencia |
|---|---|---|
| V1 Fusión y documentos | hecha | fusiones `f0d274f`, `a54a0be`, `c8f8abd`, `e36fff6`; `79e5204` (`BRECHAS.md` §11, S4A-D121…D126); `git worktree list` solo el principal (comprobado) |
| V2 Stack desde cero y ciclo | hecha | api `329e3396b325`, web `b8cd258b1cab`; 244 ok de migraciones; ciclo `0013 → 0011 → 0013` en `apex-db-1` con el worker parado |
| V3 Datos reales | hecha con desviación | "Mensual" 120.000/30 no existe: se usó `Mensual mvjipju3`; la venta retroactiva nace `expired` (no hay fila desalineada para el job) |
| V4 E2E | hecha | `stack` 40/40 ×2 (59,0 s y 57,6 s), 0 flaky; `preview` 161/161; topes de producción restaurados (429 a la 4.ª verificación, `401 ×5, 429` en login) |
| V5 Rendimiento | hecha tras corrección | falló (115–123 ms) por GC; corregido en `360d816` (S4A-D127): 17,9–23,2 ms; resto en verde |
| V6 Smoke SQL | hecha | triggers de `verifications` rechazan aun con `replica`; historial y tablero sin `@`/`apx1.`/`void_reason`; `verify_chain` por CLI (0) y API (200) |
| V7 Demo | hecha con desviaciones | V7.2 sin transiciones en `apex-db-1` (sí en `apex_sim`: +100); V7.6 "el plan no aparece en vender" no concluyente (100 de 178 planes, P2-1) |
| V8 Repetición | hecha | `--run-once` ×2 (misma fila, 7 intentos en total), `verify-audit` ×2, `POST /audit/verify` ×4 (429), `seed`/`init-keys`/`export-openapi` ×2 idénticos, `PATCH`/`deactivate` ×2 sin auditoría nueva, `DELETE` 204/404, smoke verde en 61 s |
| V9 Gates completos | **en curso** (lo corre el orquestador; no repetido aquí) | — |
| V10 Seguridad posterior | hecha | 0/0/0/4 + nota; L-1…L-3 en `360d816` |
| V11 `verify-delivery` | este archivo | — |
| V12 Cierre y paso humano | **en curso / pendiente** | limpieza P2-1 empezada por otra sesión (10:35Z); faltan volcados, admin desechable, "Estado al cierre" en `SPRINT-04A.md` y `DECISIONES.md`, reconstrucción de imágenes tras `360d816`, push, CI y merge |

**Conteo: 9/12 hechas (V1–V8, V10); V9 y V12 en curso; V11 este archivo.**

## 11. Desviaciones declaradas

| Desviación | Dónde quedó | Estado |
|---|---|---|
| `display_name` sin columna | S4A-D19, S4A-D54, S4A-D108; `BRECHAS.md` §9 cerrada | aplicada; columna a v0.2 (EP-04) |
| `--date` solo con `--simulate`, `ENV=dev` y base `*_sim`/`apex_test`; nunca sobre `apex-db-1` | S4A-D48, S4A-D63, S4A-D75, E5 | aplicada; 0 filas `*_sim` y `max(at) <= now()` en `apex-db-1` (comprobado) |
| Tres cubetas nuevas frente a "`USER_LIMITS` no cambia" | contradicción 1, S4A-D26, S4A-D45, S4A-D47, S4A-D65 | aplicada; 12 cubetas y 11 variables (`ci.yml` espera 11) |
| `VERIFY_BATCH_SIZE` 500 (el plan decía 1.000) y `SYNC_VERIFY_MAX_ROWS` 100.000 | S4A-D91, S4A-D120 | aplicada |
| Marcador en lugar de blob | S4A-D52, S4A-D105, S4A-D107 | aplicada |
| Worker sin volúmenes y endurecido | S4A-D49 | aplicada; `keys:ro` vuelve en el Sprint 5 |
| 429 en las cuatro lecturas (`/audit`, `/audit/{seq}`, `/members/{id}/audit`, `/dashboard`) | S4A-D45, S4A-D27 | aplicada |
| `recent` por tabla | S4A-D51, S4A-D115 | aplicada |
| `contact_for_notification(session, member_id, purpose)` | S4A-D21, S4A-D50 | aplicada |
| T8 de US-109 a 4B | `SPRINT-04A.md` S4A-F3; desglose US-109 T8 | aplicada (criterio pendiente) |
| Orden del front F1, F2, F4, F3 | S4A-D42, S4A-D62 | aplicada (checkpoints `7ad022a`, `1ee7804`, `ba85c63`, `452d39e`) |
| Coach sin finanzas | S4A-D118 (ajusta S4A-D29) | aplicada; "Solo administración" (S4A-D125) |
| Enlace de ingresos en días civiles | S4A-D121 | aplicada |
| Perf de la verificación medida con `gc.freeze` | S4A-D127 | aplicada (ver riesgo R-3) |
| Deuda a 4B: índices (S4A-D106 c, S4A-D115), `0014_audit_log_triggers_always` (S4A-D98), texto de `forbid_mutation` (V6), rol de base y entorno del worker (S4B-W0-2), Tabs a 1440 px | `SPRINT-04A.md` "Deuda con dueño"; `DECISIONES.md:1304` | registrada con dueño |
| Base viva sin transiciones del job (desviación de la demo, no del producto) | cuaderno V3, V7.2, V6 parte 2 | declarada; comprobado por mí: 0 `update` de `memberships.memberships` con `SYSTEM_USER_ID` en `apex-db-1`; las transiciones se probaron en `apex_sim` (+100) y en `tests/worker/test_expirations.py` |

Desviaciones de ejecución menores (cuaderno): smoke de W0-1 y W0-2 sin reconstruir imágenes (copias en el scratchpad); `chmod 600` sin efecto en NTFS; "RUNBOOK §7 Worker" vive en §9; `audit.spec.ts` de preview capturaba solo 390 y 1440 (corregido en `360d816`); `--status` desde la recuperación del arranque no reejecuta un día cerrado (S4A-D79).

**No declarada: el criterio 6 de US-113 (campos del log del worker), sección 1.**

## 12. Veredicto del Pilar 1

| Bloque | N/M |
|---|---|
| Historias | 12/14 entregadas; 2 parciales (US-109 declarada; US-113 no declarada) |
| Endpoints | 10/10 + `active_members_count` con prueba de router y contrato; 9/10 con smoke en vivo |
| Migraciones | 2/2 |
| Condiciones para VERDE | 12/13 (C11 espera el borrado de volcados de V12) |
| Seguridad del diseño (H, M, L) | 19/19 (3 con residual y dueño) |
| Decisiones S4A-D1…D127 | 127/127 con evidencia (1 aceptada sin sprint dueño: D103) |
| Enmiendas E1…E10 | 10/10 |
| Deuda heredada con dueño 4A | 7/9 cerrada; 2 en V12 (limpieza P2-1 en curso, volcados) |
| Contradicciones del plan | 12/12 |
| Revisiones por slice y V10 | 0 CRITICAL/HIGH; todo MEDIUM corregido; 2 sin dueño concreto (D103, nota de `sessionStorage`) |
| Validación | 9/12 hechas; V9 y V12 en curso |

## 13. Pilar 2 · contra el sistema real

### 13.1 Lo que V2–V8 dejó probado (cuaderno, líneas 625–722)

- Imágenes reconstruidas en V2: `apex-api:local` `sha256:329e3396b325…` (09:26:40Z) y `apex-web:local` `sha256:b8cd258b1cab…` (09:16:37Z); cinco servicios `healthy`.
- Corrida real del worker sobre `apex-db-1`: `--run-once expirations` en V3, V7.2 ×2, V8 ×2 y el smoke ×2: una sola fila `expirations|2026-10-29|ok` con 7 intentos; `audit_log` sin filas nuevas. Fecha adelantada solo en `apex_sim` (+100 transiciones, repetida 0), base borrada.
- Verificación real por API (200 ×3 y 429) y por CLI (código 0, "Cadena íntegra: 5202 / 5203 …") en V6, V7.3 y V8; `audit.verifications` con 16 filas `ok` y `through_seq` creciente.
- Edición y baja de plan reales por la pantalla (V7.6): editar a 135.000 con la vendida en 120.000 (psql), 409 con "Desactivar", desactivar 200, venta 422 `plan_inactive` por API, 204 tras anular.
- Specs `stack` 40/40 dos veces; `preview` 161/161.
- SQL de V6: triggers de `verifications` rechazan aun con `replica`; logs de api y worker (705 líneas) sin documentos, teléfonos, correos, `apx1.` ni motivos.

### 13.2 Comprobación propia (2026-10-29 10:35–10:40Z, solo lectura)

- `docker inspect apex-worker-1`: `RestartCount 0`, `healthy`, `StartedAt 2026-10-29T09:28:59Z`; a las 10:35:40Z lleva **1 h 06 min** sin reiniciar. api, web, db y db_test `healthy`, `RestartCount 0`.
- `GET http://127.0.0.1:8180/api/v1/health` → **200** `{"status":"ok","db":"ok"}`; `alembic current` = `0013_audit_verifications (head)`.
- psql con `default_transaction_read_only=on` sobre `apex-db-1`: `worker.job_runs` una fila `expirations|2026-10-29|ok|7`; 0 filas `*_sim`; `audit.verifications` 16 filas, todas `ok`, `max(through_seq)` 5.216; `audit.audit_log` 5.238 filas, `max(at) <= now()` = `t`; 0 `update` de `memberships.memberships` con `SYSTEM_USER_ID`; triggers `audit_log_forbid_*` en `O` y `verifications_forbid_*` en `A`; 0 bases `*sim*`; 0 coaches `coach-%@apex.test` activos; 1 admin `admin-e2e-%@apex.test` activo.
- Logs de la última hora: 0 `ERROR`/`CRITICAL`/`Traceback` en api y en worker; 0 `apx1.` y 0 `@apex.test` en el worker.
- `git status` limpio; `git worktree list` solo el principal.

### 13.3 Hallazgos del Pilar 2

- **P2-A (MAJOR para el cierre, no para el producto): artefactos desplegados no vigentes respecto a `360d816`.** Las dos imágenes son anteriores al último commit de código (10:31:45Z). El api corre el código del árbol por el bind de `api/src` con `--reload`; el worker monta `api/src` en solo lectura **sin** recarga y su proceso arrancó a las 09:28:59Z, antes de `360d816` (cambios de `core/audit.py`, `core/audit_verify.py` y comentarios de `worker/main.py`: sin cambio de comportamiento del job, pero el proceso no es el del árbol). La imagen web `b8cd258b1cab` (09:16Z) **no trae** `planRowSchema.strict()` (V10 L-1): ninguna spec `stack` corrió con ese bundle. Comprobé que las claves de `planRowSchema` coinciden con `PlanOut` del contrato (10 de 10), así que el riesgo de rotura es bajo, pero no está probado en vivo. V12 debe reconstruir `apex-api:local` y `apex-web:local` con buildx, `up -d --no-build` (recrea api, worker y web), repetir el smoke (`compose-smoke.sh` en copia) y una corrida de `e2e:stack`.
- **P2-B (MINOR): `POST /plans/{id}/activate` sin una llamada real contra el stack.**
- **P2-C (MINOR, demo): la base viva no tuvo transiciones del job**; la evidencia de transición es `apex_sim` y las pruebas. No es defecto: la base no tenía filas desalineadas.
- **P2-D (en curso):** durante este paso otra sesión ejecutaba la limpieza P2-1 por la API (seq 5226+ desde 10:35:29Z: login, `update plans.plans` cada ~4 s, un `update memberships.memberships`); el conteo de planes activos (171) y de filas de auditoría cambia mientras tanto. No toqué nada.

### 13.4 Checklist del Pilar 2

- [x] Interfaz real abierta y escrituras reales por la pantalla en los caminos cambiados (V7.3–V7.6, F4 demo 6, specs `stack` ×2).
- [x] Base cruzada directamente (V6 y la comprobación propia).
- [x] Caminos repetidos ejecutados más de una vez (`--run-once`, `verify-audit`, `POST /audit/verify`, `PATCH`/`deactivate`/`DELETE`, `seed`, `init-keys`, `export-openapi`).
- [x] Idempotencia probada (misma fila de `job_runs`, sin auditoría nueva en las repeticiones).
- [x] `apex-worker-1` healthy más de una hora sin reinicios.
- [ ] **Artefactos vigentes con HEAD: no** (P2-A). Falta reconstruir y repetir el smoke final en V12.
- [ ] `POST /plans/{id}/activate` en vivo (P2-B).

## 14. Discrepancias entre documentos y código

1. `SPRINT-04A.md` (cabecera) dice "S4A-D1 a S4A-D121"; el bloque llega a S4A-D127.
2. El plan (§7 V11) pide la matriz de "S4A-D1 a S4A-D74" y "`VERIFY_BATCH_SIZE` 1.000"; el valor final es 500 (S4A-D120) y las decisiones llegan a S4A-D127.
3. `DECISIONES.md` no tiene línea propia para S4A-D31…S4A-D35 (agrupadas en "S4A-D30 a S4A-D36").
4. El desglose de US-113 (T6, línea 91) y el criterio 6 de la historia piden `started_at`, `finished_at` y `duration_ms` en el log del worker; el código no los escribe y ningún documento lo corrige.
5. Las historias de `07_user_stories/` conservan el texto del gate (por ejemplo US-103 criterio 3 con blobs, US-105 criterio 1 con "N filas verificadas", US-110 con "Se vendió…"); las correcciones viven en las notas de los desgloses y en `DECISIONES.md` (regla S2-D2).
6. V3 esperaba un plan "Mensual" 120.000/30 que no existe en `apex-db-1`.

## 15. Pendientes humanos

1. Push de la rama y de `main` tras el merge, y ver en GitHub Actions los seis jobs (`api`, `web`, `images` con el smoke del worker, `scripts`, `secrets-scan`, `e2e-stack` con las 11 `USER_*` ×100 y el worker activo). Nada de este sprint ha corrido en CI.
2. Revisión de `docs/BRECHAS.md` §11 (Auditoría, Inicio, Planes, Rutas) por diseño, con `docs/design/` como fuente de verdad.
3. Datos de prueba de V12: socios `demo-s4a-expira` (`fc699bcd-…`), `demo-s4a-historial` (`ffc1fee0-…`), `demo-s4a-plan` (`fc91aba1-…`) con sus membresías y pagos; planes `S4A-V3-corto-mvtcfyaf` (activo), `S4A-V7-plan-…` y `S4A-V8-plan-…` (de baja); el admin desechable `admin-e2e-1793249495@apex.test` (`8378cdeb-…`, activo) se borra con `DELETE /users/{id}`; los planes `0 E2E …`/`E2E-tope-*` en la limpieza P2-1 (en curso).

## 16. Veredicto

> **READY_WITH_WARNINGS** (condicionado a que V9 termine en verde; si V9 falla, pasa a NOT_READY_FOR_RELEASE)

Justificación:

- Pilar 1: 12/14 historias entregadas con prueba y 2 parciales sin impacto en la caja ni en los datos; 10/10 endpoints y el campo nuevo en el contrato (53 → 63) con prueba de router; 2/2 migraciones con ciclo en `db_test` y en `apex-db-1`; 19/19 hallazgos del diseño cerrados; 127/127 decisiones con evidencia; 10/10 enmiendas; 0 CRITICAL y 0 HIGH en todas las revisiones; todo MEDIUM corregido.
- Pilar 2: worker real `healthy` más de una hora sin reinicios, corrida diaria idempotente (una fila, 7 intentos, sin auditoría duplicada), verificación de la cadena íntegra por API y CLI con ancla, planes editados y dados de baja por la pantalla con RN-04 comprobado en la base, specs `stack` 40/40 dos veces, 0 errores en logs, 0 datos sensibles en logs y respuestas.

Warnings (motivo):

1. **US-113 criterio 6 no cumplido ni declarado** (MINOR): el log del worker no lleva `started_at`, `finished_at` ni `duration_ms`. Hay que registrarlo como desviación con dueño (propuesta: Sprint 4B) o agregarlo con prueba.
2. **Artefactos no vigentes con `360d816`** (P2-A): web sin `.strict()` desplegado; worker con un proceso anterior al último commit. V12 debe reconstruir las dos imágenes, recrear api, worker y web y repetir el smoke final y `e2e:stack`.
3. **V9 sin resultado** en el momento de este informe.
4. **V12 abierto:** limpieza P2-1 en curso (171 planes activos; la venta sigue mostrando "100 de N"), dos volcados de la base viva en disco (V10 L-4, C11), admin desechable activo, "Estado al cierre" de `SPRINT-04A.md` y `DECISIONES.md` sin escribir.
5. **Riesgo de producción R-3 (S4A-D127):** la corrección del perf aísla el GC en la prueba; la pausa de generación 2 del proceso del api durante una verificación síncrona no se midió y puede superar los 100 ms de bloque (el propio cuaderno lo advierte, línea 660). Impacto bajo (lectura de admin, 3 por minuto), pero sin dueño.
6. **Deuda sin sprint dueño:** S4A-D103 (cubetas en memoria del único proceso) y la nota informativa de V10 (`sessionStorage` en `RouteError.tsx`).
7. **Residuales aceptados con dueño que tocan la integridad de la auditoría:** triggers de `audit.audit_log` en `O` (S4A-D98, confirmado en vivo; `0014_audit_log_triggers_always` en 4B), ancla sin firma externa hasta v0.3 (S4A-D92), worker con la credencial y todo `.env` del api (S4B-W0-2), índices de auditoría (S4A-D106 c, S4A-D115).
8. US-109 T8 diferido a 4B (declarado); `POST /plans/{id}/activate` sin smoke en vivo; la demo del job sin transiciones en la base viva (declarado).

Condiciones para el release (cierre del sprint):

- V9 en verde (cobertura de `app` ≥ 80 % sin `omit`, `tests/architecture` sin saltadas, pre-commit, licencias, auditorías, gitleaks, `test_api_image.sh`, sin deriva de `types.ts`).
- V12 completo: reconstrucción de las dos imágenes y smoke final más `e2e:stack` sobre el árbol de HEAD; limpieza P2-1 terminada (`GET /plans?limit=1&active=true` ≤ 100) y `verify-audit` en 0 después; borrar los dos `.dump`, el admin desechable y cualquier copia; "Estado al cierre" y "Dueños asignados al cierre del Sprint 4A".
- Registrar en `DECISIONES.md` la desviación del criterio 6 de US-113 con dueño (o implementarla), un dueño para S4A-D103 y para la nota de `sessionStorage`, y el riesgo R-3.
- Paso humano: push, CI con los seis jobs en verde y merge.
