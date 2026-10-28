# verify-delivery · Sprint 3 (plan contra lo entregado y prueba contra el sistema vivo)

- Rama: `feat/sprint-03-membresias-pagos`. HEAD al empezar: `0fa1270` (`docs(sprint-03): baja de cuentas de prueba heredadas (v12)`); mientras se hacía este paso otros agentes confirmaron `43793e4`, `221cc63` y `8ef1a91` (solo documentos), que esta matriz ya incorpora. Base del sprint: `d65056e` (cierre del Sprint 2 en `main`). El código (`api/`, `web/`, `infra/`) no cambia desde `6c98eb6`.
- Fecha: 2026-10-28.
- Alcance: paso V11 del plan (`docs/ddd/blueprints/sprint-03-plan.md`, sección 7). Pilar 1: matriz N/M de las 25 historias, los 22 endpoints más los dos filtros de `GET /members`, las 4 migraciones, las 10 condiciones para VERDE del impacto, la revisión de seguridad del diseño (H-1…H-3, M-1…M-10, L-1…L-13, D-1…D-5), la deuda heredada de §9.3 del Sprint 2, las 22 contradicciones de contrato (S3-C1…S3-C22), las desviaciones declaradas y las de la ejecución, y la validación V1–V12. Pilar 2: comprobación propia contra el stack vivo (sección 12).
- Método del Pilar 1: lectura de `SPRINT-03.md`, del plan (E1–E16, secciones 0–10), del impacto (`docs/ddd/impacto/sprint-03.md` §8), de `sprint-03-seguridad-diseno.md`, del bloque Sprint 3 de `DECISIONES.md` (S3-D41…S3-D105, secciones por slice, Fase 4 backend y front, V10, V1, V9), de los dos cuadernos, de `BRECHAS.md` §6 y §10 y de las 25 historias de `07_user_stories/`. Todo archivo citado se comprobó con `ls`/`grep` en `0fa1270`; el contrato se contó con un script contra `docs/openapi.json` y el de `d65056e`. Las cifras de pruebas que no corrí yo vienen de los cuadernos y se dicen como tales; la corrida propia de la suite del api está en la sección 12.
- Convención: **entregada** (todos los criterios vigentes con prueba), **parcial** (falta un criterio vigente o su prueba), **no**. "Criterio vigente" es el de la historia corregido por `DECISIONES.md` o por la nota de cabecera de su desglose (`08_implementation_breakdown/`, notas "> -" de S3-W0-1); cada corrección va en la columna de desviación. Las historias de `07_user_stories/` conservan el texto del gate (misma regla que el Sprint 2, S2-D2).

## 1. Historias (25)

Checkpoints de cada slice verificados con `git log --oneline d65056e..HEAD`. "Vivo" remite a la validación V2–V8 y a la validación final del stack (`docs/scratch/sprint-03.md`).

| Historia | Criterios vigentes (resumen) | Estado | Evidencia | Desviación declarada |
|---|---|---|---|---|
| US-056 Etiquetas de medios de pago | claves fijas `cash`/`nequi`/`breb` con `label` 1–30 y `hint` ≤ 120; clave ajena 422 `value.<x>`; `label` vacía 422; `payment_methods()` en orden; los pagos guardan el código; auditoría; coach 403 en `PATCH` y lectura por `GET /payments/methods`; front sin agregar ni quitar, con la nota | entregada | B3 `d5b37b9`, F4 `afe6526`; `api/tests/settings/test_payment_methods_{rules,service,router}.py`, `tests/payments/test_payment_methods_router.py`, `tests/architecture/test_payment_method_codes.py`; `web/src/features/system/components/PaymentMethodsForm.test.tsx` (nota "Para agregar un medio nuevo…"); vivo: V3 (`payment_methods` versión 1) | `GET /payments/methods` responde `{ items }` (S3-C7, D25); etiquetas `SafeText`, únicas sin mayúsculas y lectura tolerante a JSON ajeno (S3-D55, L-3) |
| US-071 Filtrar socios por membresía y plan | `membership_status` (incluidos `pending_payment` y `none`) y `plan_id` paginados; vigente gana a la futura; `plan_id` inexistente vacío, no UUID 422; estado fuera del enum 422; `members` sin joins a `memberships`; chips con texto y `aria-pressed`; chip y plan en la URL | entregada | B9b `7d78c05`, F2 `c6d9590`; `tests/members/test_chip_to_filter.py`, `test_service_list_membership_filters.py`, `test_router_list_filters.py`, `test_list_perf.py` (5.000 ids, `-m perf`); `tests/architecture/test_service_import_graph.py`, `test_no_cross_schema_sql.py`; `web/src/features/members/components/{MemberStatusChips,PlanFilter}.test.tsx`; vivo: V7.7 (chips con conteos, `plan_id` + "Al día" = 3 filas iguales al API) | Conjunto de ids por import perezoso de lista blanca y `any_`/`all_` (D22, G-03); `membership_status = "none"` explícito en filas, ficha y alta (B9b, PL4); los conteos de los chips son los globales del resumen, no por plan (observación de V7.7); criterio 8 sustituido por N-20 del Sprint 2 (`status=deleted` también para el coach); orden "Vencimiento más próximo" fuera de v0.1 (S3-D98) |
| US-072 Lista de socios en celular | tarjetas < 768 px sin desborde en 320 y 390; "Cargar más" con `offset + limit`; tarjeta enfocable de 44 px; búsqueda y chips iguales; sin datos sensibles; "Nuevo socio" con `members.create` | entregada | F2 `c6d9590`; `web/src/features/members/components/MemberCardList.test.tsx`; `web/tests/e2e/members-mobile.spec.ts` (preview, 390 y 320, axe) y `tests/e2e/stack/members-mobile.spec.ts`; vivo: V7.7 (0 tablas, 25 tarjetas y "Cargar más" → 50) | `useMembersInfinite` con `maxPages: 20` (S3-D52) y `gcTime: 0` (Fase 4 front L7) |
| US-073 Ver ficha del socio | 200 `MemberDetail` admin/coach; `member` 403; 404; 422; sensibles enmascarados en memoria; sin fila `reveal`; dado de baja con etiqueta y sin acciones; aviso sin autorización; "Dar de baja" solo admin; pestaña en la URL y futuras deshabilitadas; carga, 404 y error | entregada | B9b `7d78c05`, F1 `d139457`; `tests/members/test_service_get.py`, `test_router_get.py`; `tests/architecture/test_reveal_single_door.py`; `web/src/features/members/pages/MemberDetailPage.test.tsx`; `tests/e2e/stack/member-detail.spec.ts`; vivo: V6 (`decrypt | mask` con `record_id`, 0 `reveal` por abrir) y V7.6 | Criterio 3: la ficha deja filas `decrypt` con `purpose='mask'` en `crypto_ops` (D20); ninguna de auditoría. Criterio 4: el coach también ve la ficha de un dado de baja (N-20; `test_router_get.py::test_el_coach_ve_la_ficha_de_un_dado_de_baja`). Sin "notas" (S3-C18). Historial deshabilitado con "v0.1 · Sprint 4A" (US-106) |
| US-074 Mostrar dato sensible auditado | 200 `{field, value}`; `field` cerrado 422; `member` 403; 404; una fila `reveal` y una `decrypt` sin el valor; fallo de auditoría → sin valor; vacío → `null` y auditado; `no-store` y nada en logs; front re-enmascara al ocultar, al salir y a los 60 s | entregada | B10 `4b4ce60`, F1; `tests/members/test_service_reveal.py` (incluye `test_un_campo_vacio_devuelve_none_y_tambien_audita`), `test_router_reveal.py`; `tests/audit/test_reveal_entry.py` (ya con `make_member`); `tests/architecture/test_no_sensitive_in_logs.py` (sin `skip`), `test_reveal_single_door.py`; `tests/core/test_logging_redact.py` (reveal real, cierra T8 de US-018); `web/src/shared/ui/MaskedValue{,.reveal}.test.tsx`; vivo: V6 (`after = {"ip","field"}` sin el valor; `decrypt | reveal | 1`) y sección 12 de este archivo | `table_name = "members.members"` (S3-C4); `audit.record` directo sin `SensitiveFieldRevealed` (D19, S3-C16); `after` con `ip` (L-12); tres ventanas 30/min, 200/h, 600/día y aviso `reveal volume` (S3-D44, S3-D88) |
| US-075 Editar socio | `PATCH` admin/coach 200 enmascarado; solo cambian los enviados, recifra y reindexa; documento repetido 409 con `existing_id`; 422 de forma; dado de baja 409 `member_deactivated`; auditoría `update` con blobs; sin cambios → 200 sin fila ni evento; `MemberUpdated` con nombres; el formulario no revela; ficha y lista se invalidan | entregada | B10, F1; `tests/members/test_member_patch_rules.py`, `test_service_update.py`, `test_router_update.py`; `web/src/features/members/pages/MemberFormPage.edit.test.tsx`; `tests/e2e/stack/member-detail.spec.ts` (el `PATCH` lleva solo `phone`); vivo: V7.6 (coach cambia el teléfono; documento 403) | El documento y su tipo los cambia solo el admin, por presencia del campo: 403 `forbidden_field` aunque el valor sea igual (M-3, S3-D46); `MemberPatch` cerrado y `data_consent` solo `true` (422 `consent_cannot_be_withdrawn`); orden y recarga con candado (S3-D85…S3-D87) |
| US-076 Dar de baja socio | `DELETE` admin 204 con `deleted_at`; coach y `member` 403; ya de baja 409 `member_already_deactivated`; 404; fuera de listas y búsquedas salvo `status=deleted`; membresías y pagos intactos; `update` auditado y `MemberDeactivated`; documento reutilizable; sin `DELETE FROM`; front sin la acción para el coach | entregada | B10, F1; `tests/members/test_service_deactivate.py`, `test_router_deactivate.py`; `tests/architecture/test_no_physical_delete.py` (amplía a auditoría y llaves); `tests/e2e/stack/member-detail.spec.ts`; vivo: V7.6 y sección 12 | `deactivate`/`reactivate` toman `lock_member` (S3-D54, L-1); las dos rutas gastan `admin-write` y declaran 429 (S3-D97); `MemberReactivated` invalida el resumen (S3-D89). `POST /members/{id}/reactivate` es añadido de la historia (US-076 lo nombra el plan) |
| US-083 Reglas puras de fechas y estados | `compute_end_date`, orden de `compute_status` con `freezes`, `expiring_days` por parámetro, futura `active`, `classes_remaining = 0` → `expired`, `next_start_for_renewal`, `is_covered` sin anulados, todo puro, 100 % de ramas | entregada | B1 `5c9bb45`; `tests/memberships/test_rules.py`, `test_status_expr_parity.py`; corrida propia con cobertura de ramas sobre `0fa1270` (sección 12.6): `memberships/rules.py` 197 sentencias y 58 ramas, 0 sin cubrir, 100 % | `compute_status` con cuatro argumentos (S3-C12); `is_covered`/`paid_total` se conservan como oráculo y producción usa `covers` sobre la suma de SQL (Fase 4, PL2 c) |
| US-084 Vender membresía | 201 `pending_payment` con `MembershipOut`; fechas; precio copiado; clases por tipo; socio 404/422 `member_inactive`; plan 422; 409 `membership_conflict` con `existing_id` y enlace "Renovar"; 409 `membership_overlap`; venta tras vencida o anulada; una transacción con auditoría y `MembershipSold`; roles; sin `models` ajenos | entregada | B1, F3 `bf0626d`; `tests/memberships/test_sell_service.py`, `test_sell_router.py`, `test_lock_order.py`; `tests/migrations/test_0008_memberships.py`; `tests/architecture/test_no_cross_models.py`, `test_guarded_calls.py`; `web/src/features/memberships/pages/SellPage.test.tsx`; `tests/e2e/{,stack/}sell-with-payment.spec.ts`; vivo: V7.1, V7.4 (409 `membership_conflict`), V6 (`EXCLUDE` 23P01) y sección 12 | `sell(..., enforce_retroactive_limit=True)` y el service lee la política (S3-C13); `start_date <= hoy + 366` (422 `start_date_too_far`, S3-D47); con una vigente o futura gana `membership_conflict` a `membership_overlap` (D8; V7.4 lo anota); `lock_member` + `FOR SHARE` del plan (D3) |
| US-085 Vender con primer pago | membresía y pago en una transacción, 201 con `first_payment_id`; estado según cobertura; 422 con `first_payment.amount_cop` y `first_payment.method`; `paid_at` con zona; atomicidad ante un handler que falla; sobrepago con confirmación; pago y membresía auditados; roles | entregada | B4 `3d7702b`, F3; `tests/memberships/test_sell_with_payment_service.py`, `test_rules.py` (`prefix_field`, `reraise_with_prefix`); `web/src/features/memberships/components/FirstPaymentSection.test.tsx`; vivo: V7.1, V6 (`active | t`, auditoría 2869–2871) y sección 12 | El sobrepago lo confirma el servidor: 409 `payment_exceeds_balance` sin `confirm_overpayment` (S3-D41, H-1); el duplicado no aplica a la venta; la venta con pago gasta también `payments-write` (S3-D82); `role=None` conserva el tope retroactivo (S3-D81, S3-D96) |
| US-086 Activar por cobertura | dos pagos de 60.000 sobre 120.000 → `active` en la transacción del pago, `MembershipActivated` una vez; `expiring` si toca; pago parcial sin evento; ya activa sin cambio; anulados no suman; handler que falla revierte; auditoría `update`; activación solo por evento | entregada | B4; `tests/memberships/test_activation_service.py`, `test_lock_order.py` (`sell`/`register`); `tests/architecture/test_service_import_graph.py`, `test_gates_registered.py`, `test_handlers_no_new_locks.py`; vivo: V6 (`update memberships.memberships` en la auditoría) y V7.2 | Una pendiente ya vencida que se cubre queda `expired` y emite `MembershipActivated` con ese estado (D11). Criterio 8: `payments` no importa `memberships` a nivel de módulo; desde B8 tiene un import perezoso de lectura de presentación (`refs_for`) en la lista blanca de G-03 (D2) |
| US-087 Revertir activación al anular | anular el único pago → `pending_payment` y `MembershipActivationReverted` una vez; sigue cubierta sin cambio; `expiring` revierte; `frozen`/`expired`/`cancelled` sin cambio; handler que falla revierte; auditoría con quien anuló | entregada | B5 `47c5692`; `tests/memberships/test_revert_activation_service.py`; `tests/payments/test_void.py`; vivo: V6 (reversión con `end_date` intacto) y V7.3 | Estado EFECTIVO; `frozen` también revierte si deja de cubrir (`should_revert` en `{active, expiring, frozen}`, B5); la reversión conserva congelaciones y `end_date` (N-25). El criterio 4 ("frozen no cambia") lo corrige N-25 (nota del desglose de US-087); `expired` y `cancelled` siguen sin cambiar |
| US-088 Renovar membresía | `renew: true` empieza al día siguiente del fin; vencida o sin membresía → hoy; `start_date` ignorado; nace `pending_payment` o `active` con pago; futura existente 409 `future_membership_exists`; congelada usa el fin extendido; sin solapes; plan activo; roles; auditoría; chip con la vigente | entregada | B6 `3136ee6`, F3; `tests/memberships/test_renew_service.py`, `test_renew_router.py`; `web/src/features/memberships/pages/SellPage.test.tsx`; vivo: V7.4 (inicio 25 nov, futura creada) y V8 (201 y 409 `future_membership_exists`) | Vista previa `GET .../renewal-preview` sin candados ni cupo (añadido del plan, US-088); `start_date` del cuerpo descartado sin `validate_start_date` (B6) |
| US-089 Congelar membresía | `freeze` sobre `active`/`expiring` extiende el fin `N` días; estado por `compute_status`; fechas invertidas 422 `frozen_to`; retroactividad y vigencia 422; límites de veces y días; ya programada; solape con una futura; límites de settings; `apply_freeze` pura; roles; auditoría y `MembershipFrozen` | entregada | B2 `5d412bd`, F5 `5fdf793`; `tests/memberships/test_freeze_rules.py`, `test_freeze_service.py`, `test_freeze_router.py`, `test_freeze_revision.py`; `tests/migrations/test_0009_membership_freezes.py`; `web/src/features/memberships/components/FreezeModal.test.tsx`; `tests/e2e/stack/memberships-freeze-cancel.spec.ts`; vivo: V7.5 (fin 2026-11-24 → 2026-12-04; 409 `freeze_limit_reached`) | Códigos de D14: 409 (no 422) para `membership_not_freezable`, `freeze_limit_reached`, `freeze_days_exceeded`, `freeze_already_scheduled`; el solape es `overlaps_future_membership`; las ventanas viven en `membership_freezes` (append-only, S3-D48), sin columnas `frozen_*` ni `reason` (`// DESIGN-GAP:`); socio inactivo 422 (B2 M1) |
| US-090 Anular membresía | `cancel` con motivo 5–500 → `cancelled` con quién y cuándo; 422 `reason`; 409 ya anulada; desde cualquier estado; terminal; pagos intactos y pago nuevo 409 `membership_cancelled`; deja de contar para Q1; solo admin; auditoría y `MembershipCancelled` | entregada | B6, F5; `tests/memberships/test_cancel_service.py`, `test_cancel_router.py`; `tests/migrations/test_0008_endurecimiento.py` (terminal en la base); `web/src/features/memberships/components/CancelMembershipModal.test.tsx`; vivo: V7.5 (200 y pago 409 `membership_cancelled`), V6 (`memberships_identity` sobre una anulada) | `admin-write` y 429 (S3-D42); el evento lleva `reason_len`, nunca el motivo (S3-D70) |
| US-091 Listar membresías | página con `limit` 1–200; `status` múltiple; `ends_*` inclusivos e invertidos 422; `q` por la búsqueda del padrón sin descifrar; campos de la fila; orden `end_date`; detalle con congelaciones y anulación; roles; < 500 ms con 1.000 socios; chip de pendiente y precio en el front | entregada | B7 `9f5ae13`, F5; `tests/memberships/test_list_service.py`, `test_list_router.py`, `test_list_perf.py` (`-m perf`), `test_out_parity.py`; `web/src/features/memberships/pages/MembershipsPage.test.tsx`; vivo: V5 (`expiring` con 1.000 socios y 3.000 membresías 15,0 / 16,2 ms) | `status` con `max_length=100` (L-9); `ends_*` en `[2020-01-01, hoy + 5 años]` (S3-D47); cubeta `members-search` solo con `q` (S3-D45); estado efectivo en todas las salidas (S3-D91); `status` publicado como enum `MembershipStatus` (S3-D96) |
| US-092 Resumen y consultas de estado | `summary` con cinco enteros de socios vivos; prioridad de `resolve_member_status`; casos de vigente + futura; `status_for` sin N+1; `count_active_by_plan`; suma cuadra con el padrón; cuadra con la lista; roles; < 300 ms | entregada | B7; `tests/memberships/test_status_queries_service.py`, `test_summary_router.py`, `test_summary_cache.py`, `test_status_expr_parity.py`, `test_list_perf.py`; vivo: V5 (13,0–17,2 ms) y V7.7 (chips = resumen) | Resumen en SQL con `DISTINCT ON` y caché de 30 s invalidada tras el commit (S3-D53, E13, S3-D60, S3-D89, S3-D90); `count_active_by_plan` sin consumidor hasta US-082 (Sprint 4A). Un solo proceso del api (S3-D93) |
| US-093 Pestaña Membresías de la ficha | `GET /members/{id}/memberships` con anuladas, `start_date` desc; 404; dado de baja devuelve historia; roles; vigente arriba con `StatusTag`; "Renovar"/"Vender" según el caso; "Anular" solo admin y "Congelar" sobre `active`/`expiring`; carga, vacío y error | entregada | B11 `41e244e`, F7 `889f365` (+ `ce932d0`); `tests/memberships/test_member_memberships_service.py`, `test_member_memberships_router.py`; `web/src/features/memberships/components/MemberMembershipsTab.test.tsx`; `tests/e2e/{,stack/}member-tabs.spec.ts`; vivo: evidencia de B11 (`total 2`, `?q=Mensual`) | `q` por `plans.search_ids` (D28); ruta hija real `/socios/:id/membresias` (S3-D65, E3, E14); sin 429 (D28) |
| US-095 Registrar pago | 201 con `registered_by`; `amount_cop` entero 422; `method` 422; `reference` ≤ 64; `paid_at` con zona y no futuro; 404 y 409 `membership_cancelled`; `PaymentRegistered` en la transacción; `payments` no escribe `memberships`; auditado; roles; advertencia de Q5 en el front | entregada | B3 (service) y B4 (ruta, E9); `tests/payments/test_rules.py`, `test_register.py`, `test_router_register.py`, `test_can_void.py`; `tests/architecture/test_gates_registered.py`; `web/src/features/payments/components/RegisterPaymentPanel.test.tsx`; vivo: V7.2 (409 `payment_exceeds_balance`, 409 `payment_possible_duplicate`, 201 con `confirm_*`) y sección 12 | Sobrepago y duplicado confirmables en el servidor (S3-D41); tope de 60 no anulados (409 `payment_limit_reached`, S3-D42); `paid_at` desde 2020-01-01 y, para el coach, hasta `max_retroactive_days` atrás (S3-D47, S3-D51, desviación de N-27 por rol); `reference` con patrón de comprobante (S3-D50) |
| US-096 Inmutabilidad en la base | `DELETE` falla; `UPDATE` de columnas protegidas falla; la anulación completa pasa una vez; anulado inmutable; anulación incompleta falla; `true → false` falla; `can_void`; migración reversible; sin `delete(` en el service | entregada | B4; `api/migrations/versions/0011_payments_immutability.py`; `tests/migrations/test_0011_payments_immutability.py`, `test_triggers_siempre_activos.py`; `tests/payments/test_immutability.py`, `test_can_void.py`; `tests/architecture/test_payments_immutability_code.py`, `test_no_trigger_tampering.py`; vivo: V6 (`payments_immutable: column`, `already_voided`, `delete`, `truncate`; también con `session_replication_role = replica`) y sección 12 | Rama `truncate` propia y `incomplete_void` (B4); `ENABLE ALWAYS` (S3-D49); el rol dueño de la tabla aún podría apagar el trigger: separación de roles en S4B-W0-2 (residual aceptado, V10 I-2) |
| US-097 Anular pago | `void` con motivo 1–500 → 200 con `voided_by`/`voided_at`; 422 `reason`; 409 `payment_already_voided`; 404; no toca montos ni borra; `PaymentVoided` en la transacción; anular y registrar deja dos filas; auditoría `update`; solo admin | entregada | B5 `47c5692`, F4 y F6; `tests/payments/test_void_rules.py`, `test_void.py`, `test_router_void.py`; `web/src/features/payments/components/VoidPaymentModal.test.tsx`; `tests/e2e/stack/payment-void.spec.ts`; vivo: V7.3, V8 (200 y 409) y sección 12 | Tope de entrada de 2.000 caracteres antes de la regla de 500 (S3-D83); aviso en log al anular un pago de un mes anterior (S3-D51); `admin-write` (S3-D42) |
| US-098 Listar y buscar pagos | página `limit` 1–200; `from`/`to` con zona `[from, to)`; `method`; `registered_by`, `membership_id`, `member_id`; `voided`; `q` por referencia exacta o nombre; orden `paid_at` desc; sin cifrados; roles; < 500 ms con 10.000 | entregada | B8 `208117e`, F6 `8026ab1`; `tests/payments/test_list.py`, `test_list_filters.py`, `test_router_list.py`, `test_list_perf.py`, `test_enrich_guard.py`; `web/src/features/payments/pages/PaymentsPage.test.tsx`; vivo: V5 (12,9–13,7 ms con 10.000 pagos) | `backdated` en la fila y como filtro (S3-D51); correo parcial en `registered_by_name`/`voided_by_name` (S3-D57, L-2) hasta US-110; fechas acotadas (S3-D47); cubeta `members-search` con `q` |
| US-099 Ver detalle de pago | 200 con todos los campos; 404; 422; modal sin editar ni borrar; roles | entregada | B8, F6; `tests/payments/test_get.py`, `test_router_get.py`; `web/src/features/payments/components/PaymentDetailModal.test.tsx` | Nombres de usuario como correo parcial (S3-D57) |
| US-100 Resumen mensual de pagos | `{month, total_cop, by_method, voided_count, payments_count}` enteros; mes por defecto en Bogotá; 422 `month`; mes por hora de Bogotá; anulados aparte; `total_cop` = suma y cuadra con la lista; mes vacío en ceros; roles; `$ 0` en el front | entregada | B8, F6; `tests/payments/test_month_bounds.py`, `test_summary.py`, `test_router_summary.py`; `web/src/features/payments/components/MonthSummary.test.tsx`; vivo: V7.7 (`2026-10`: 7.682.000 en 86 pagos, cuadra con la lista paginada y con `/pagos`) y V5 (8,2–8,6 ms) | `parse_month` 2020–2100 con aritmética de `(año, mes)` (S3-D47, M-4); anulados de meses distintos probados (L-13) |
| US-101 Pestaña Pagos de la ficha | `GET /members/{id}/payments` de todas sus membresías, `paid_at` desc; anulados con motivo y `voided=false`; 404; dado de baja devuelve historia; montos y fechas; roles; sin editar ni borrar; "Anular" solo admin | entregada | B11, F7; `tests/payments/test_list_for_member.py`, `test_router_member_payments.py`; `web/src/features/payments/components/MemberPaymentsTab.test.tsx`; `tests/e2e/stack/member-tabs.spec.ts`; vivo: evidencia de B11 (`total 3`, `?voided=false` → 2) | `MemberPaymentsTab` vive en `features/payments` (S3-D65); `q` solo por referencia exacta (D28); sin 429 |

**Conteo: 25/25 entregadas, 0 parciales, 0 no entregadas.** Ninguna historia tiene un criterio vigente sin prueba. Las diferencias con el texto del gate están todas respaldadas por una decisión (columna derecha).

## 2. Endpoints (22) y filtros de `GET /members` (2)

Contados con un script sobre `docs/openapi.json` frente al de `d65056e`: 31 → 53 operaciones, **22 nuevas, 0 quitadas**; `GET /api/v1/members` gana `membership_status` y `plan_id`. Toda operación nueva declara `500` y `503` (`ErrorResponse`, S3-D67/E16). "Smoke" es una petición real contra el stack.

| # | Ruta | Rol | Límite (429) | Prueba de router | Smoke en vivo |
|---|---|---|---|---|---|
| 1 | `GET /members/{member_id}` | admin, coach | `members-detail` | `tests/members/test_router_get.py` | B9b; V7.6; sección 12 |
| 2 | `PATCH /members/{member_id}` | admin, coach | `members-write` | `tests/members/test_router_update.py` | V7.6 (coach `phone`, 403 documento) |
| 3 | `DELETE /members/{member_id}` | admin | `admin-write` (S3-D97) | `tests/members/test_router_deactivate.py` | V7.6; sección 12 |
| 4 | `POST /members/{member_id}/reactivate` | admin | `admin-write` (S3-D97) | `tests/members/test_router_deactivate.py` | V7.6; sección 12 |
| 5 | `POST /members/{member_id}/reveal` | admin, coach | `members-reveal` (3 ventanas) | `tests/members/test_router_reveal.py` | B10; V7.6; sección 12 |
| 6 | `GET /members/{member_id}/memberships` | admin, coach | sin límite (D28) | `tests/memberships/test_member_memberships_router.py` | B11 |
| 7 | `POST /members/{member_id}/memberships` | admin, coach | `memberships-write` (+ `payments-write` con pago) | `tests/memberships/test_sell_router.py`, `test_renew_router.py` | V7.1, V7.4; V8; sección 12 |
| 8 | `GET /members/{member_id}/memberships/renewal-preview` | admin, coach | sin límite | `tests/memberships/test_renew_router.py` | V7.4 (pantalla "Renovar") |
| 9 | `GET /members/{member_id}/payments` | admin, coach | sin límite (D28) | `tests/payments/test_router_member_payments.py` | B11; sección 12 (pestaña Pagos) |
| 10 | `GET /memberships` | admin, coach | `members-search` con `q` | `tests/memberships/test_list_router.py` | V7.5 (pantalla) |
| 11 | `GET /memberships/summary` | admin, coach | sin límite | `tests/memberships/test_summary_router.py` | V7.7 |
| 12 | `GET /memberships/{membership_id}` | admin, coach | sin límite | `tests/memberships/test_list_router.py` | B7 |
| 13 | `POST /memberships/{membership_id}/freeze` | admin, coach | `memberships-write` | `tests/memberships/test_freeze_router.py` | V7.5; V8 |
| 14 | `POST /memberships/{membership_id}/cancel` | admin | `admin-write` | `tests/memberships/test_cancel_router.py` | V7.5 |
| 15 | `POST /memberships/{membership_id}/payments` | admin, coach | `payments-write` | `tests/payments/test_router_register.py` | V7.2; sección 12 |
| 16 | `GET /payments` | admin, coach | `members-search` con `q` | `tests/payments/test_router_list.py` | V7.7 |
| 17 | `GET /payments/summary` | admin, coach | sin límite | `tests/payments/test_router_summary.py` | V7.7 |
| 18 | `GET /payments/methods` | admin, coach | sin límite | `tests/payments/test_payment_methods_router.py` | V7 (panel de pago) |
| 19 | `GET /payments/{payment_id}` | admin, coach | sin límite | `tests/payments/test_router_get.py` | V7.3 (detalle desde `/pagos`) |
| 20 | `POST /payments/{payment_id}/void` | admin | `admin-write` | `tests/payments/test_router_void.py` | V7.3; V8; sección 12 |
| 21 | `GET /settings/payment_methods` | admin | sin límite | `tests/settings/test_payment_methods_router.py` | V3 |
| 22 | `PATCH /settings/payment_methods` | admin | `admin-write` (S3-D100) | `tests/settings/test_payment_methods_router.py`, `test_admin_write_limit_router.py` | sin smoke propio (prueba de router y F4) |
| F1 | `GET /members?membership_status=` | admin, coach | `members-search` con `q` | `tests/members/test_router_list_filters.py` | V7.7 |
| F2 | `GET /members?plan_id=` | admin, coach | igual | `tests/members/test_router_list_filters.py` | V7.7 |

Transversales: `tests/architecture/test_every_route_has_role.py`, `test_error_codes_per_route.py` (`CON_LIMITE` exacto), `test_user_limits_catalog.py`, `test_writes_have_user_limit.py` (V10, toda escritura con tope o exenta con motivo), `test_error_responses_in_openapi.py` (503 en toda ruta con rol), `test_no_store_routes.py`, `test_session_scope.py`, `test_list_routes_use_page_params.py`.

**Conteo: 22/22 endpoints y 2/2 filtros con prueba de router; 21/22 con smoke en vivo (falta un `PATCH /settings/payment_methods` real contra el stack; lo cubren la prueba de router y la pantalla de F4 en `vitest`).**

## 3. Migraciones (4)

| Migración | `down_revision` | Prueba | Ciclo en `apex-db-1` | Volcado previo |
|---|---|---|---|---|
| `0008_memberships` | `0007_plans` | `tests/migrations/test_0008_memberships.py`, `test_0008_endurecimiento.py`, `test_triggers_siempre_activos.py` | B1 (dos veces, por la `0008` desechable) y V2 | `sprint-03-antes-0008_memberships.dump` (B1) |
| `0009_membership_freezes` | `0008_memberships` | `test_0009_membership_freezes.py` | B2 y V2 | B2 (P-MIG) |
| `0010_payments` | `0009_membership_freezes` | `test_0010_payments.py` | B3 y V2 | B3 (P-MIG) |
| `0011_payments_immutability` | `0010_payments` | `test_0011_payments_immutability.py` | B4 y V2 (`downgrade 0007_plans` → `upgrade head`, más el arranque desde `0010` por el engine de `env.py`) | `sprint-03-antes-0011.dump` (B4) y `sprint-03-antes-v2.dump` (V2) |

Una cabeza: `tests/core/test_migrations.py::test_single_head` y `alembic heads` en V2. Los volcados ya no están en `docs/scratch/` (comprobado con `ls` en `0fa1270`: solo quedan los `.md`), así que la higiene de V12 sobre volcados está hecha. B11.6 hizo el ciclo de cierre en `db_test` por los E2E de F1 (desviación autorizada) y V2 lo repitió en `apex-db-1`.

**Conteo: 4/4.**

## 4. Condiciones para VERDE del impacto (10)

| # | Condición (`docs/ddd/impacto/sprint-03.md` §8) | Estado | Dónde |
|---|---|---|---|
| 1 | Pruebas de arquitectura del Sprint 2 (`MODULES`, `ALLOWED_EDGES`, tablas auditadas, `env.py`) y par perezoso `members → memberships` en B9 | cumplida | B1, B3 (con S3-D80: aristas de `payments` repartidas entre B3 y B8), B9b; `tests/architecture/test_audit_module.py`, `test_service_import_graph.py`, `test_audited_tables.py` |
| 2 | Routers con `no_store`, `responses_for`, `SessionDep`, `current_clock()`, 429 solo con límite y en `CON_LIMITE` | cumplida | W0-2 `5e84bab` (`enforce_user_limit`, `StaffDep`/`AdminDep`, `test_user_limits_catalog`); cada slice B; V10 lo extiende a toda escritura de admin (`test_writes_have_user_limit.py`) |
| 3 | Contratos que chocaban: `{items}`, `q` en las anidadas, marcador `perf` | cumplida | B3 (S3-C7), B11 (`q` en las dos pestañas), W0-1/B7 (`perf`, S3-C14) |
| 4 | T-DOC de nombres en los desgloses y decisión de `active_ids` | cumplida | W0-1 `452453b` (notas de cabecera S3-C1…S3-C22 en los desgloses, `05_service_design.md`, `SPRINT-03.md`); `active_ids` en B7 (S3-D60) |
| 5 | Limpieza de `db_test`, doble del gate, fábricas, `test_no_physical_delete` solo `src/` | cumplida | B1 y B3 (`LIMPIAR_MEMBERSHIPS`/`LIMPIAR_PAYMENTS` con `ENABLE ALWAYS`, E1; `test_triggers_siempre_activos.py`); `tests/payments/conftest.py` (`gate_doble` opt-in); `api/tests/factories/{memberships,payments}.py`; B10 |
| 6 | `memberships` y `members` partidos con fachada | cumplida | B1/B3 nacen partidos; B9a `ee609f1` (`members`); Fase 4 S3-D90 (`summary.py`); `tests/architecture/test_file_and_function_size.py` |
| 7 | Pruebas ajenas del front y de settings | cumplida | B3 (`NO_HABILITADAS`), F4 (`ConfigPage.test.tsx`), F1/F3–F6 (`routes.test.ts`, `nav.test.ts`, `features.test.ts`) |
| 8 | Front sin cruces entre features | cumplida | S3-D65 (`shared/data/`, rutas hijas, `?pago=`); `web/tests/lint/boundaries.test.ts` en cada gate |
| 9 | P-API y P-MIG en cada slice; una cabeza; ciclo B1–B4 y V2; `pg_dump` antes de `0011` | cumplida | cuaderno por slice; sección 3 |
| 10 | `build web` antes de E2E; digests y `npm audit` de desarrollo decididos | cumplida | S3-D62/S3-D63 en W0-1; cada evidencia F; V2 y validación final |

**Conteo: 10/10.**

## 5. Revisión de seguridad del diseño (H-1…H-3, M-1…M-10, L-1…L-13, D-1…D-5)

| ID | Estado | Evidencia |
|---|---|---|
| H-1 sobrepago y duplicado en el servidor | cerrado | S3-D41; `payments/rules.py`, `register._check_under_lock`; `tests/payments/test_register.py`, `test_router_register.py`; `web/src/features/payments/components/RegisterPaymentPanel.test.tsx`; vivo V7.2 |
| H-2 topes de escritura y tope por membresía | cerrado | S3-D42, S3-D82, S3-D97, S3-D100; `core/ratelimit.py:316` (`USER_LIMITS`); `payments/rules.py:77` (`MAX_PAYMENTS_PER_MEMBERSHIP = 60`); `tests/architecture/test_user_limits_catalog.py`, `test_writes_have_user_limit.py`; vivo: 31 `POST /plans` → 30 × 201 y 429 (validación final §4) |
| H-3 tiempos de espera y 503 `busy` | cerrado | S3-D43, S3-D67, S3-D79; `core/db.py:177,183` (`BUSY_SQLSTATES`, `DatabaseBusy`); `tests/core/test_db_timeouts.py`, `test_errors_busy.py`; `tests/memberships/test_lock_order.py`; `tests/architecture/test_handlers_no_new_locks.py`; vivo V6 (503 en 10,03 s con `Retry-After: 1`, luego 201) |
| M-1 volcado con `reveal` | cerrado | S3-D44, S3-D88; `core/ratelimit.py:321` (`members-reveal-hour`) y ventanas de minuto y día; `tests/members/test_router_reveal.py` |
| M-2 `GET /members/{id}` y búsquedas | cerrado | S3-D45; `PII_SEARCH_BUCKET` (`core/ratelimit.py:330`); `members-detail` 120/min; pruebas de router de B7, B8 y B9b |
| M-3 `PATCH` por presencia | cerrado | S3-D46; `members/rules.py:324` (`ensure_can_change`); `tests/members/test_member_patch_rules.py`; vivo V7.6 (403 con el mismo documento) |
| M-4 fechas extremas | cerrado | S3-D47; `payments/rules.py:74` (`PAID_AT_FLOOR`), `start_date_too_far`, `parse_month`; `tests/payments/test_month_bounds.py`, `test_rules.py`, `tests/memberships/test_rules.py` |
| M-5 cancelada terminal y sin borrado | cerrado | S3-D48; `0008` y `0009` con triggers; `tests/migrations/test_0008_endurecimiento.py`, `test_0009_membership_freezes.py`; vivo V6 |
| M-6 trigger que la app puede apagar | cerrado con residual aceptado y dueño | S3-D49; `ENABLE ALWAYS` y prueba con `replica`; `tests/architecture/test_no_trigger_tampering.py`; separación de roles de base: S4B-W0-2 (V10 I-2, `SPRINT-04B.md`) |
| M-7 texto libre en la auditoría | cerrado con residual aceptado y dueño | S3-D50; patrón de `reference`; aviso `SENSITIVE_TEXT_WARNING` (`web/src/shared/data/schemas/payment.ts:25`); supresión: US-119 |
| M-8 `paid_at` retroactivo del coach | cerrado | S3-D51; `validate_paid_at` por rol; `backdated` (`payments/queries.py`); aviso de mes anterior en `void`; pruebas de B3, B5 y B8 |
| M-9 valor revelado en la caché del front | cerrado | S3-D52, S3-D104; `web/src/core/api/useSensitiveMutation.ts` y su prueba; `tests/lint/sensitive-mutations.test.ts`; `MaskedValue` re-enmascara al ocultar la pestaña (Fase 4 front L2) |
| M-10 resumen en memoria | cerrado | S3-D53, S3-D60, E13; `memberships/summary.py`; `tests/memberships/test_summary_cache.py`; vivo V5 |
| L-1 candado de socio en baja y reactivación | cerrado | S3-D54; `core/locks.py:48`; `tests/memberships/test_lock_order.py` (`sell`/`deactivate`) |
| L-2 correo de otros usuarios | cerrado (interino) | S3-D57; `payments/rules.py:204` (`partial_email`); nombre real con US-110 |
| L-3 etiquetas de medios | cerrado | S3-D55; `tests/settings/test_payment_methods_rules.py` |
| L-4 SQL crudo constante | cerrado | S3-D56, E6; `tests/architecture/test_sql_literals_constant.py` |
| L-5 quién registra el gate | cerrado | `memberships/service.py:88` (única llamada); `tests/architecture/test_guarded_calls.py`; anular sobre una cancelada en `test_void.py` |
| L-6 `enforce_retroactive_limit` | cerrado | `test_guarded_calls.py` |
| L-7 nombres de excepción y evento | cerrado | S3-D70; `MemberIsDeactivated` / `MemberDeactivated`; `tests/architecture/test_events_without_pii.py` |
| L-8 volcado previo | cerrado | S3-D58; `-n memberships -n payments`, `*.sql.gz` en `.gitignore`; volcados ya borrados (sección 3); RUNBOOK §10 (V10 L-C) |
| L-9 `status` sin tope | cerrado | `Query(max_length=100)`; `tests/memberships/test_list_router.py` |
| L-10 funciones de trigger | cerrado con desviación declarada | `SECURITY INVOKER` y `SET search_path = pg_catalog` en `0008`, `0009`, `0011` (comprobado por catálogo en `test_0008_memberships.py`); sin `CHECK voided_at >= created_at` (S3-D68) |
| L-11 aislamiento | cerrado | `test_guarded_calls.py` (sin `isolation_level`); caso de `sell` simultáneo en B1 |
| L-12 `reveal` con IP | cerrado | `after = {"field", "ip"}`; vivo V6 |
| L-13 resumen con anulados de otros meses | cerrado | `tests/payments/test_summary.py` |
| D-1 `enforce_user_limit` | cerrado | `core/ratelimit.py`; W0-2 |
| D-2 `StaffDep`/`AdminDep` | cerrado | `core/security.py:502,504` |
| D-3 `lock_membership` única | cerrado | `memberships/sell.py:343`; prueba AST en `test_guarded_calls.py` |
| D-4 `_decrypt_fields` única | cerrado | `members/detail.py:54`; `tests/architecture/test_reveal_single_door.py` |
| D-5 `ID_BATCH` y `chunked` | cerrado | `core/pagination.py:43`; `tests/core/test_pagination_chunks.py`; `any_uuids` (S3-D91) |

**Conteo: 31/31 cerrados (H 3/3, M 10/10, L 13/13, D 5/5). Dos con residual aceptado y dueño (M-6 → S4B-W0-2; M-7 → US-119) y uno con desviación declarada (L-10, S3-D68).**

## 6. Deuda heredada del Sprint 2 (`sprint-02-verify-delivery.md` §9.3)

| Ítem | Estado | Evidencia |
|---|---|---|
| Caso `reveal` de `test_no_sensitive_in_logs` y `test_reveal_entry` a la fábrica (S3-B10) | cerrado | sin `skip` en `test_no_sensitive_in_logs.py`; `test_reveal_entry.py:24,37` usa `make_member`; US-107 criterios 1 y 2 quedan cubiertos con `audit.record` directo (S3-C16) |
| Enlace del 409 a `/socios/{id}` (S3-B9/F1) | cerrado | `BRECHAS.md` §10.12; `tests/e2e/stack/members.spec.ts` ("Ver socio existente" con href `/socios/<uuid>`) |
| Imágenes base por digest (W0-1) | cerrado | `api/Dockerfile:7,26`, `web/Dockerfile:7,17`, `infra/compose.yml:15`, `compose.dev.yml:32`, `test_nginx_conf.sh:27` con `@sha256`; `scripts/ci/test_images_pinned.sh` (incluye `ci.yml` desde Fase 4 L2) |
| Dependencias de desarrollo del front con `npm audit` (W0-1) | cerrado | vitest 5.0.5 (S3-D63); el residual `braces` ya no aparece (V9.6); Zod 4 (S3-D105) deja `npm audit` en 0 en producción y desarrollo |
| `.env.seed` en disco (W0-1) | cerrado | `ls .env.seed` → no existe (S3-D64) |
| `payment_methods` (US-056) | cerrado | sección 1 |
| T8 de US-018 (`test_logging_redact` con `reveal` real) | cerrado | `tests/core/test_logging_redact.py:274` |
| Higiene de worktrees y volcados | cerrado | `git worktree list` solo el principal; sin `*.dump` en `docs/scratch/` |
| `remote_addr` real y p99 del login | diferido con dueño | S4B-W0-2 (sin cambio) |
| Índice de la búsqueda por nombre (`pg_trgm`) | diferido con dueño | Sprint 4A (sin cambio) |
| `omit` de `cli.py` y `worker/` en la cobertura | diferido con dueño | US-113, Sprint 4A |
| `display_name` (US-110) y tablero de Inicio (US-108) | diferido con dueño | Sprint 4A |
| Emisor de `forgot` (US-131) | diferido con dueño | Sprint 5 |
| Alerta por volumen de fallos de login | diferido con dueño | Sprint 4A (`core/alerts`) |
| Edición, activación y baja de planes (US-080…US-082) | diferido con dueño | Sprint 4A |
| `limit_req` con el portal | diferido con dueño | Sprint 10 |

**Conteo: 8/8 de lo que el plan asignó al Sprint 3, cerrado; 8 diferidos que ya tenían dueño en otro sprint, sin cambio.**

## 7. Contradicciones de contrato (S3-C1…S3-C22)

Las 22 se cerraron en W0-1 (`452453b`) como notas de cabecera en los desgloses afectados, en `05_service_design.md` y en `SPRINT-03.md` (cada `S3-Cn` aparece al menos en un documento corregido: `grep -rl "S3-Cn"` da 1 a 6 archivos por número). El código sigue la versión corregida:

| ID | Estado | Dónde se ve en el código o la prueba |
|---|---|---|
| C1 `get_ref` con `is_deleted` | cerrada | `memberships/sell.py` (`_sale_context`) |
| C2 `active_ids` | cerrada | `members.service.active_ids` (B7, `frozenset`) |
| C3 `types.reveal`, sin `bus.op_context` | cerrada | `members/detail.py:54`; `test_reveal_single_door.py` |
| C4 `members.members` | cerrada | `tests/audit/test_reveal_entry.py` |
| C5 `SessionDep`, `current_clock()`, `principal.user_id` | cerrada | `test_session_scope.py`, `test_no_direct_now.py` |
| C6 `PageParams`, `set[UUID]` | cerrada | `test_list_routes_use_page_params.py` |
| C7 `{ items }` | cerrada | `tests/payments/test_payment_methods_router.py` |
| C8 `members.document.update`, `members.delete` | cerrada | desglose US-075; `permissions.ts` |
| C9 prueba consolidada del grafo | cerrada | `tests/architecture/test_service_import_graph.py` |
| C10 `MemberNotFound` reutilizado | cerrada | `memberships/exceptions.py` sin duplicado |
| C11 `reveal` sin `commit()` | cerrada | `members/router.py` (`SessionDep`) |
| C12 `compute_status` con cuatro argumentos | cerrada | `tests/memberships/test_rules.py` |
| C13 `enforce_retroactive_limit` | cerrada | `test_guarded_calls.py` |
| C14 `perf` en lugar de `slow` | cerrada en el alcance del sprint | `test_list_perf.py` de `payments` y `memberships`; ver discrepancia 4 de la sección 13 |
| C15 `current_clock()` | cerrada | `test_no_direct_now.py` |
| C16 sin `SensitiveFieldRevealed` | cerrada | `members/detail.py`; `test_reveal_entry.py` |
| C17 `settings.service.payment_methods` | cerrada | `tests/settings/test_payment_methods_service.py` |
| C18 sin "notas" | cerrada | ficha sin notas (`MemberDetailPage.test.tsx`) |
| C19 grafo desde B1 | cerrada | gate de B1 (cuaderno) |
| C20 W0 con dos slices | cerrada | `452453b`, `5e84bab` |
| C21 `agreed_price_cop` en el gate | cerrada | `payments/service.py` (`MembershipPayability`) |
| C22 la pantalla reenvía con la confirmación | cerrada | V7.2; `RegisterPaymentPanel.test.tsx` |

**Conteo: 22/22.**

## 8. Revisiones posteriores (Fase 4 y V10)

- Revisión de seguridad por slice (`security-reviewer` en cada Verde de B1 a B11 y en F1, F2, F7): 0 CRITICAL y 0 HIGH en todas; MEDIUM corregidos con prueba (B1 M1, B2 M1, B4 MEDIUM-1 → S3-D82, B7 MEDIUM-1 y -2) o con dueño cerrado después (B1 M2 → B10); LOW corregidos o aceptados con motivo en `DECISIONES.md` por slice.
- Fase 4 backend (`code-reviewer` 0/1/4/3 y `python-reviewer` 0/0/5/7 sobre `c9720ea`): todos los HIGH y MEDIUM corregidos (S3-D89 a S3-D97); un MEDIUM aceptado con dueño (PM2 → S3-D92, US-160, Sprint 7) y dos LOW aceptados con motivo (PL3 `list`, PL7 b índice); checkpoint `6e8406f`.
- Fase 4 front (`typescript-reviewer`, 8 MEDIUM y 9 LOW sobre `d5f494d`, más los 4 pendientes de V1 y V10 L-D): 17/17 corregidos; revisión final 0/0/2/4, un LOW aceptado (regex de la prueba de lint, protegido por `config-protection`); checkpoint `b39d160`, fusión `fd2e8a3`.
- V10 (`security-reviewer` sobre `3c7db38`): M-A (S3-D100), L-A (S3-D101), L-B (S3-D102) corregidos; L-C documentado y ya ejecutado (volcados borrados); L-D corregido en el front; I-2 con dueño S4B-W0-2; I-3 informativo; I-4 con dueño US-106. Checkpoint `7962caa`.
- V9 (gates ligeros sobre `fd2e8a3`): todo verde salvo `npm audit --omit=dev` por Zod 3 (GHSA-mrhx-c7xc-m3w5), resuelto con la migración a Zod 4 (`6c98eb6`, S3-D105).

## 9. Validación V1–V12

| V | Estado | Evidencia |
|---|---|---|
| V1 Fusión | hecha | fusiones `80798f7`, `e2fcd08`, `87df3cc`, `c7f51e9`, `8241f8b`, `c9720ea`, `dfa9959`, `fd2e8a3`; `d5f494d` (fixture del enum); DESIGN-GAP en `BRECHAS.md` §10 (`035ce03`, `123abce`); `git worktree list` solo el principal |
| V2 Stack desde cero | hecha | cuaderno V2: buildx sin caché, `0011 (head)`, ciclo completo a `0007_plans` y vuelta, una cabeza, siete triggers en `A`, logs sin `ERROR` |
| V3 Datos reales | hecha | cuaderno V3: "Mensual V50137" creado porque "mensual" ya existía con otro precio; seis socios demo |
| V4 E2E contra el stack | hecha | cuaderno V4, validación final §5 y "Validación final del stack con Zod 4" (`221cc63`, imagen web `695f6e2f027d`): `e2e:stack` 35/35 dos veces seguidas en cada una de las tres rondas, 0 flaky, `retries: 0`; `preview` 144/144; CSP sin `unsafe-eval` con Zod 4. Tres defectos de prueba corregidos (`ece2f4e`, `5d2b4d1`, `958a070`) |
| V5 Rendimiento | hecha | 8/8 `perf` dos veces; todos los tiempos muy por debajo de los topes; no hace falta `0014` |
| V6 Smoke SQL | hecha | cuaderno V6: activación atómica, reversión, `EXCLUDE`, los siete rechazos de trigger, `reveal` sin valor, 0 `decrypt` sin propósito, `verify_chain` 2.914/2.914, 503 `busy`, logs limpios |
| V7 Demo | hecha | los siete puntos por la pantalla (capturas `v7-p*` en `web/test-results/captures/`) |
| V8 Repetición | hecha | `seed`, `init-keys`, `export-openapi`, anular dos veces, congelar dos veces, `renew` dos veces; `compose-smoke.sh` en una copia (Compose no construye en este equipo) |
| V9 Gates completos | hecha | V9.1 `run-gates.sh` completo sobre `aacd8b0` (mismo código que `0fa1270`), código 0: api 3.883 ok, 3 saltadas, cobertura 97 %; front 156 archivos y 2.788 pruebas, 98,87 % de líneas, lint, `tsc` y build; scripts en verde (cuaderno, bloque "V9.1", `8ef1a91`). V9.2–V9.7 y V9.9 sobre `fd2e8a3`; V9.8 en la validación final. Confirmado por la corrida propia de la sección 12.6 |
| V10 Revisión de seguridad posterior | hecha | sección 8 |
| V11 `verify-delivery` | este archivo | Pilar 1 (secciones 1 a 11) y Pilar 2 (sección 12) |
| V12 Cierre y paso humano | en parte | hecho: baja de 120 cuentas `coach-%@apex.test` (`0fa1270`), volcados borrados, worktree único, "Estado al cierre" de `SPRINT-03.md` y `DECISIONES.md` (`43793e4`), dueños de los cuatro puntos abiertos (`8ef1a91`). Pendiente: push de la rama (no está en `origin`: `git branch -r`), PR con los seis jobs de CI y merge, que hace una persona |

**Conteo: 11/12 hechas (V1–V11); V12 en parte (falta el paso humano).**

## 10. Desviaciones, añadidos y diferidos

### 10.1 Desviaciones declaradas en el plan (sección 7, V11)

| Desviación | Dónde quedó | Estado |
|---|---|---|
| Wave 0 con dos slices | S3-C20; `452453b`, `5e84bab` | aplicada |
| `core/db.py` y `core/errors.py` tocados | S3-D43, S3-D67; `core/db.py:177,183` | aplicada |
| 503 `busy` con `Retry-After: 1` | S3-D67, E16; V6 en vivo | aplicada |
| Confirmación de sobrepago y duplicado en el servidor | S3-D41; V7.2 | aplicada |
| `paid_at` por rol | S3-D51 (desvía N-27 en el rol) | aplicada |
| B9 en dos checkpoints | S3-D73; `ee609f1` (B9a) y `7d78c05` (B9b) | aplicada |
| Orden del front por disponibilidad | S3-D66: F3, F4, F5, F6, F2, F1, F7 (checkpoints en ese orden) | aplicada |
| `MemberPaymentsTab` en `features/payments` | S3-D65; `web/src/features/payments/components/MemberPaymentsTab.tsx` | aplicada |
| Sin `CHECK voided_at >= created_at` | S3-D68 | aplicada |
| Sin 10.000 socios | S3-D71 (5.000 ids en `any_`, 1.000 socios, 10.000 pagos) | aplicada |

### 10.2 Desviaciones de la ejecución (registradas en `DECISIONES.md` o en los cuadernos)

- Piso de 1.000 ms de los tiempos de espera con `ENV=production` (S3-D79, cierra el MEDIUM no aplicado de W0-2).
- Aristas `payments → members/auth` movidas de B3 a B8 (S3-D80).
- `role=None` en `sell` conserva el tope retroactivo (S3-D81; el centinela desaparece en S3-D96).
- La venta con primer pago gasta también `payments-write` (S3-D82).
- Tope de entrada de 2.000 caracteres del motivo de anulación (S3-D83).
- `id_by_document` en `members/changes.py`, orden de `update`, recarga con candado y traducción del índice único (S3-D84 a S3-D88).
- `test_events_without_pii.py` nace en B6, no en B10; `FreezeOut` gana `id` y `created_at`; 422/409 de congelar según D14 en lugar del texto de US-089.
- Ciclo de Alembic de B11.6 sobre `db_test` y en `apex-db-1` en V2 (autorizado).
- `memberships/queries.py` partido en `summary.py` (S3-D90); un constructor único de salidas y estado efectivo en todas (S3-D91).
- `status` publicado como enum `MembershipStatus` y `Role` tipado (S3-D96).
- `admin-write` y 429 en baja y reactivación de socios (S3-D97) y en diez rutas más de admin (S3-D100): 12 rutas en total fuera del alcance original de H-2; `lock`, `unlock` y `revoke-sessions` exentas con motivo.
- Topes de cuerpo por location en Nginx (64k, 128k para la política, S3-D101) y `DETAIL` de PostgreSQL fuera del log (S3-D102).
- `membership_status = "none"` explícito también en el alta (PL4).
- `get_payment_target` y `PaymentTarget` retirados como código muerto (PL2 a).
- Tiquetera agotada con fin futuro bloquea la compra siguiente hasta US-160 (S3-D92, aceptado con dueño).
- Orden "Vencimiento más próximo" fuera de v0.1 (S3-D98).
- El buscador del panel de pagos ofrece al socio inactivo (S3-D99; se aparta de la indicación del orquestador por lo que responde el api).
- A dónde lleva la venta al salir (S3-D103) y toda mutación por `useSensitiveMutation` (S3-D104).
- Migración del front a Zod 4.6.7 (S3-D105), con `jitless` por la CSP y `zod` en su propio chunk.
- En la venta solapada con una vigente el API responde `membership_conflict` y no `membership_overlap` (orden de D8; V7.4); el plan V7 decía `membership_overlap`.
- La pantalla dice "supera el saldo de la membresía" y no "supera el saldo pendiente" (V7.2, observación de texto).
- La segunda congelación sobre una membresía `frozen` responde `membership_not_freezable` antes que `freeze_already_scheduled` (orden de `rules.py`, V7.5).
- `crypto_ops` dio `decrypt | mask | 28` y no `5` en V6: el socio tenía 4 campos cifrados y la ficha se cargó 7 veces (aritmética del cuaderno).
- La demo usó "Mensual V50137" porque "mensual" ya existía con 320.000 (V3).
- `docker compose build` no funciona en este equipo (buildx 0.38.1 con `network: host`): imágenes con `docker buildx build` directo (RUNBOOK §7); `compose-smoke.sh` se corrió en una copia con ese cambio (V8).

### 10.3 Añadidos no pedidos (con prueba)

- `GET /members/{id}/memberships/renewal-preview` (vista previa de la renovación) y `POST /members/{id}/reactivate` (los dos están en los 22 del plan, no en el texto de las historias del gate).
- `tests/architecture/test_writes_have_user_limit.py` (V10) y las pruebas de router de topes de `plans`, `settings` y `auth`.
- `MemberReactivated` (S3-D89); `core.pagination.any_uuids`/`uuid_array` (S3-D91).
- Front: `shared/ui/MemberSearch`, `useSelectionFocus`, `shared/lib/{ids,routes,balance}.ts`, `statusMessage`/`toFormError`, `core/api/useSensitiveMutation.ts`, `core/zodSetup.ts`, `tests/lint/sensitive-mutations.test.ts`, `tests/unit/e2e-stack-guard.test.ts`, `exigirStackLocal`.

### 10.4 Diferidos con dueño

- US-094 (job de vencimientos) y sus eventos: Sprint 4A.
- "Socios con él" en `Planes.html`, `count_active_by_plan` visible y `plans.update` sin bloquear membresías: US-082 (Sprint 4A).
- Historial de la ficha y congelaciones sin `subject_member_id`: US-106 (Sprint 4A).
- `display_name` en lugar del correo parcial: US-110 (Sprint 4A).
- Separación de roles de base (rol del api sin superusuario ni dueño de `payments`, `memberships`, `audit`): S4B-W0-2 (S3-D49, V10 I-2, `SPRINT-04B.md`).
- `cli import-members` con una transacción por socio (S3-D95): Sprint 4B.
- Supresión de datos personales escritos en la auditoría (S3-D50): US-119.
- Recorte de `end_date` al agotarse una tiquetera (S3-D92): US-160 (Sprint 7).
- 413 de Nginx en HTML sin el envelope JSON: anotado para la llegada de adjuntos (v0.3; validación final §3).
- 429 `rate_limited` de S3-D100 en las pantallas (cuaderno V10, "Pendientes"): comprobado en el código, planes (`planErrors.ts:16,66`) y usuarios (`userActions.ts:49`, `NewUserPanel.tsx:56`) tienen texto propio; los formularios de configuración muestran el `message` del api ("Demasiados intentos. Espera un momento.", `useSectionForm.ts:95`). Cubierto; sin prueba E2E del 429 por pantalla.
- Cuatro puntos que el "Estado al cierre" dejó sin dueño (W0-2 MEDIUM-1 y MEDIUM-2 → S4B-W0-2; S3-D98 y pendientes de diseño de `BRECHAS.md` §10 → revisión de diseño previa al Sprint 4A): dueños asignados en `DECISIONES.md`, "Dueños asignados al cierre del Sprint 3" (`8ef1a91`).
- "Exportar" en las tres listas: EP-16 (US-139, v0.2).
- Los de la sección 6 que ya tenían dueño.

## 11. Veredicto del Pilar 1

| Bloque | N/M |
|---|---|
| Historias | 25/25 entregadas |
| Endpoints | 22/22 con prueba de router (21/22 con smoke en vivo) |
| Filtros de `GET /members` | 2/2 |
| Migraciones | 4/4 |
| Condiciones para VERDE | 10/10 |
| Revisión del diseño (H, M, L, D) | 31/31 (2 con residual aceptado y dueño, 1 con desviación declarada) |
| Deuda heredada del Sprint 2 asignada al Sprint 3 | 8/8 |
| Contradicciones de contrato | 22/22 |
| Desviaciones declaradas del plan | 10/10 aplicadas y trazables |
| Validación | 11/12 hechas; V12 en parte (paso humano) |

Lo que NO está entregado o no está probado en `8ef1a91`:

1. V12: push, PR con los seis jobs de CI en verde y merge (paso humano). Hasta entonces nada de este sprint corrió en GitHub Actions, incluido el job `e2e-stack` con las ocho `USER_*` ×100 (E15), que solo se puede ver allí.
2. `PATCH /settings/payment_methods` sin smoke en vivo (prueba de router, prueba de pantalla y la lectura de la sección en V3).

## 12. Pilar 2 · prueba propia contra el sistema vivo

Hecha por este agente el 2026-10-28 entre las 21:26 y las 21:45 UTC, después de que el otro agente terminara de reconstruir la imagen web y de correr `e2e:stack` (sus dos corridas de 35/35 están en `221cc63`). Árbol en `8ef1a91` (solo documentos desde `6c98eb6`). No se tocó código, `infra/`, `.env` ni la contraseña de `admin@ejemplo.local`. Salidas guardadas en el scratchpad de la sesión (`<scratchpad>/p2/`: `01-artefactos.txt` a `08-limpieza.txt`, `02-pantalla.log`) y las capturas en `web/test-results/captures/v11-*.png` (fuera de git).

### 12.1 Artefactos vigentes

- `apex-api:local` `sha256:7ebd75528265…` (creada 2026-10-28 20:39 UTC) y `apex-web:local` `sha256:695f6e2f027d…` (21:24 UTC). `docker inspect` de `apex-api-1` y `apex-web-1`: corren exactamente esas imágenes, `healthy`; `apex-db-1` en `postgres:16@sha256:9e2cf628…` (el digest de `infra/compose.yml`). Coinciden con lo anotado en el cuaderno ("Validación final del stack con Zod 4").
- La imagen del api es posterior al último commit que toca `api/` (`7962caa`, 20:32 UTC) y además el contenedor monta `api/src` y `api/migrations` por bind: corre el código del árbol. La de web es posterior al último commit que toca `web/` (`6c98eb6`, 21:07 UTC).
- `GET http://localhost:8180/api/v1/health` → **200** `{"status":"ok","db":"ok"}`; `alembic current` → `0011_payments_immutability (head)`.
- 8180 sirve `assets/main-6hstwnyo.js` y `assets/zod-DOov2Nxz.js`, los del cuaderno. Comprobación extra: un `vite build` del árbol actual a una carpeta del scratchpad (sin tocar `web/dist`) produce exactamente `main-6hstwnyo.js` y `zod-DOov2Nxz.js`: el bundle servido es el del código actual.

### 12.2 Escritura real por la pantalla (Playwright, Chromium, 1440 × 900, un solo trabajador)

Cuenta: admin desechable `admin-v11-<epoch>@apex.test` (`64509739-…`), creado con un access de `admin@ejemplo.local` firmado dentro de `apex-api-1` (script temporal en `/tmp`, borrado; `/tmp` vacío después) + `POST /users` 201 + `POST /auth/reset` 204 con el token de `activation_url` y una contraseña aleatoria (el mismo camino que usan `crearCoach` y la validación final; no hizo falta `tools issue-reset-link`).

| Paso | Resultado |
|---|---|
| Login por la pantalla `/login` | "Hola…" visible |
| Alta de socio por `/socios/nuevo` (documento y teléfono aleatorios, autorización marcada) | `POST /members` **201**, "Socio registrado: Valeria VerifS3mvsmunxp." (`1a18bb7a-73c4-4574-91fc-51f83a00ccc9`); captura `v11-1-alta.png` |
| Venta de "Mensual V50137" desde `/membresias/vender?socio=` | **no se pudo**: la pantalla no ofrece ese plan. Muestra "Se muestran 100 de 166 planes. Si falta el que buscas, avísale a un administrador." (los 100 primeros por nombre; 120 planes activos ordenan antes que "Mensual V50137"). Captura `v11-intento1-venta-sin-plan.png`. Ver hallazgo P2-1 |
| Venta por la pantalla con un plan equivalente que sí ofrece: "0 E2E 2wq5361c5" (120.000, 30 días), primer pago de $ 70.000 en efectivo | `POST /members/{id}/memberships` **201**, membresía `899a3e5c-6cf8-4d49-9766-cb4d5bfec3aa`, `pending_payment`, `paid_cop 70000`, `first_payment_id` presente; "Venta registrada" con Estado **"Pendiente de pago"**, saldo $ 50.000 (captura `v11-2-venta.png`) |
| Segundo pago por el panel ("Registrar saldo" en la pestaña Membresías de la ficha, precargado **$ 50.000**) | `POST /memberships/{id}/payments` **201** (`ef86ee60-…`), sin modal (otro valor, no es duplicado); la vigente pasa a **"Al día"** (captura `v11-3-segundo-pago.png`) |
| Anular ese segundo pago con motivo desde la pestaña Pagos | `POST /payments/{id}/void` **200**, `voided true`; la fila muestra el motivo y la vigente vuelve a **"Pendiente de pago"** (capturas `v11-4-anulado.png`, `v11-5-revertida.png`) |
| Revelar el documento en la ficha | la ficha muestra `CC •••• <4 últimos>`; "Mostrar" → `POST /members/{id}/reveal` **200** con `Cache-Control: no-store` y el valor igual al sembrado; "Ocultar" vuelve a la máscara y el documento no queda en el HTML (`page.content()` sin el valor). La captura `v11-6-ficha-enmascarada.png` es la del estado enmascarado; no se capturó el valor revelado |
| Dar de baja y reactivar por la pantalla | `DELETE /members/{id}` **204**, "Socio dado de baja", sin "Editar" (`v11-7-baja.png`); "Reactivar" → **200**, "Socio reactivado", "Editar" de vuelta (`v11-8-reactivado.png`) |

Ninguna respuesta 5xx ni error de página durante el recorrido. Escrituras que hizo el navegador, en orden: login 200, `POST /members` 201, venta 201, pago 201, anulación 200, `reveal` 200, baja 204, reactivación 200 (más los `refresh` 200 de cada recarga y el 401 inicial esperado sin cookie).

### 12.3 Cruce con la base (psql de solo lectura, `SET default_transaction_read_only = on`)

```
memberships.memberships  899a3e5c-…  pending_payment | 2026-10-28 | 2026-11-27 | 120000 | socio_ok t
payments.payments        8fe50593-…  70000 cash | member_id_copiado t | voided f | registro_el_desechable t
payments.payments        ef86ee60-…  50000 cash | member_id_copiado t | voided t | con_motivo t | anulo_el_desechable t
audit.audit_log (subject_member_id = socio, por seq; todas con el admin desechable como actor)
  4489 insert members.members           (claves: blobs, *_idx, sin valores en claro)
  4490 insert memberships.memberships
  4491 insert payments.payments          (primer pago)
  4492 insert payments.payments          (segundo pago)
  4493 update memberships.memberships   status pending_payment -> active   (activación por cobertura)
  4494 update payments.payments          voided, voided_at, voided_by, void_reason
  4495 update memberships.memberships   status active -> pending_payment   (reversión)
  4496 reveal members.members           after = {"ip": "172.30.0.128", "field": "document"}   (sin el valor)
  4497 update members.members           status active -> inactive, deleted_at   (baja)
  4498 update members.members           status inactive -> active, deleted_at   (reactivación)
crypto.crypto_ops (record_id = socio): decrypt|mask 16, decrypt|reveal 1, encrypt 2, index 2
crypto.crypto_ops con verb='decrypt' y purpose IS NULL en toda la tabla: 0
members.members: status active, vivo, document empieza por "apx1.", document_idx presente
```

Las cuatro filas pedidas están: `insert memberships`, `insert payments`, `update memberships` (activación y reversión), `reveal` con `after = {field, ip}` sin el valor, y `decrypt|reveal` exactamente 1. Los 16 `decrypt|mask` son 2 campos cifrados × 8 cargas de la ficha durante el recorrido (D20: una fila por campo no vacío y carga; el plan decía 5 para una carga de un socio con 5 campos).

### 12.4 Repetición e idempotencia

- La misma anulación por API, con el access del admin desechable (`04-repeticion.txt`): primer pago `8fe50593-…` → **200** `voided=true`; otra vez → **409** `{"error":{"code":"payment_already_voided","message":"El pago ya está anulado."}}` con `Cache-Control: no-store` y un solo `Pragma`; el segundo pago (ya anulado por la pantalla) por API → **409**. La membresía sigue `pending_payment` y tiene 2 de 2 pagos anulados: la doble anulación no tocó nada.
- `export-openapi` dos veces a archivos del scratchpad: sha256 `3559f3767c97…` en las dos, idéntico byte a byte entre sí y a `docs/openapi.json` (`cmp` sin diferencias); es el sha del cuaderno tras V10.
- Cadena de auditoría después de las escrituras: `verify_chain` sobre toda `audit.audit_log` en una conexión de solo lectura dentro de `apex-api-1` (script temporal borrado) → `VerifyResult(ok=True, rows_checked=4500, broken_at_seq=None)`.

### 12.5 Logs y limpieza

- `docker logs --since 20m apex-api-1` (133 líneas): 0 `ERROR`, 0 trazas, 0 `status` 5xx, 0 apariciones de `apx1.`, del correo del admin desechable y de los motivos escritos; un solo `WARNING` (`rate limit` de `login`, de la comprobación de seis logins fallidos del otro agente a las 21:30).
- Limpieza: el socio del primer intento (`b4bb8977-…`, sin membresías) se dio de baja por API (204, baja lógica); el admin desechable se borró con `DELETE /users/{id}` (204, `deleted_at`); quedan 5 usuarios vivos, los mismos de V12. Los archivos con access, contraseña y correo del desechable se borraron del scratchpad. Quedan como datos de prueba el socio `1a18bb7a-…` (activo, con su membresía `pending_payment` y dos pagos anulados), como los socios de la demo de V7.

### 12.6 Suite del api con cobertura sobre el árbol final

Corrida propia: `cd api && uv run pytest --cov=app -m "not perf"` con `TEST_DATABASE_URL` a `db_test` (`127.0.0.1:5443`), sobre `0fa1270` (el código no cambió después): **3.883 passed, 3 skipped (NTFS), 8 deselected (`perf`)** en 11 min 43 s; cobertura global de `app` **97 %** (6.835 sentencias, 166 sin cubrir; 1.252 ramas, 83 parciales). Coincide con el V9.1 del orquestador (3.883 ok, 97 %). `memberships/rules.py`: 100 % de sentencias y de ramas.

### 12.7 Hallazgos del Pilar 2

- **P2-1 (MINOR, riesgo de datos de prueba, no defecto del producto):** la venta pide los 100 primeros planes activos por nombre (`SELL_PLANS_LIMIT = 100`, `web/src/features/memberships/pages/useSellForm.ts:28`) y no tiene buscador de planes; con 166 planes activos en `apex-db-1` el plan de la demo ("Mensual V50137") ya no se puede elegir por la pantalla. La pantalla lo avisa ("Se muestran 100 de 166…"), como fijó la Fase 4 del front (L8). La causa es que cada corrida de `e2e:stack` crea planes `0 E2E …` y que no hay baja de planes hasta el Sprint 4A (30 planes `E2E-tope` más los de cada corrida: 136 en la validación final, 157 durante la última ronda de `e2e:stack`, 166 al hacer este recorrido). En un gimnasio real (decenas de planes) no aplica. Dueño propuesto: Sprint 4A, con `DELETE /plans/{id}` y la baja de planes (US-081), que las specs del stack reutilicen o den de baja su plan; y un buscador de planes en la venta si el catálogo supera 100. No está registrado todavía en `DECISIONES.md`.
- Ningún otro hallazgo: 0 respuestas 5xx, 0 errores de página, la activación, la reversión, la doble anulación, el `reveal` auditado sin valor, la baja y la reactivación se comportan como dicen las historias.

### 12.8 Checklist del Pilar 2

- [x] Artefactos desplegados vigentes (api por imagen y bind, web por imagen y hash del bundle reconstruido).
- [x] Interfaz real abierta y escrituras reales por la pantalla en el camino cambiado (alta, venta con primer pago, segundo pago, anulación, `reveal`, baja, reactivación), sin 5xx.
- [x] Base cruzada directamente (memberships, payments, audit_log, crypto_ops, members).
- [x] Repetición: la misma anulación dos veces (200 y 409); `export-openapi` dos veces.
- [x] Idempotencia: la doble anulación no cambia nada; el contrato exportado es estable.
- [x] Evidencia capturada (capturas, salida de psql, logs) sin datos sensibles.
- [ ] La venta del plan pedido ("Mensual V50137") por la pantalla: no se pudo por P2-1; se hizo con un plan equivalente (120.000, 30 días).

## 13. Discrepancias entre documentos y código

1. El cuaderno ("Validación final del stack tras Fase 4 y V10", §5) y `SPRINT-03.md` ("Estado al cierre", correcciones de validación) citan `59bf09d`, `43b4f09` y `561ae32`. Esos commits se reescribieron para el trailer (bloque "V9.1", `8ef1a91`) y en la rama son `ece2f4e`, `5d2b4d1` y `958a070`; los hashes viejos ya no están en `feat/sprint-03-membresias-pagos`.
2. `SPRINT-03.md`, "Estado al cierre" (`43793e4`): sigue con dos "[pendiente de cita]" (cobertura del api y `run-gates.sh`) que `8ef1a91` ya resolvió en el cuaderno (97 %, código 0), y con cuatro "Pendiente de dueño" que `8ef1a91` ya asignó en `DECISIONES.md`. "Pendiente humano" 5 (borrar volcados) también está hecho. El texto no se actualizó después.
3. El plan y el "Estado al cierre" dicen 20 slices, pero la lista que dan (W0-1, W0-2, B1–B8, B9a, B9b, B10, B11, F1–F7) suma 21 checkpoints; el 20 viene de contar B9 una vez.
4. S3-C14 (`-m slow` → `-m perf`) se corrigió en los documentos del Sprint 3, pero los desgloses de US-094 (`08_implementation_breakdown/EP-09-membresias/US-094-…md:128`) y US-112 (`…/US-112-…md:160`), de sprints futuros, todavía dicen `-m slow`.
5. `BRECHAS.md` §9 (fila "Socios · `MemberFormPage.tsx`", línea 236) sigue diciendo "Venta: Sprint 3 / S3-B1" para "Guardar y vender membresía", mientras §10.3 y §10.12 lo dan como pendiente de diseño (dueño: revisión de diseño previa al Sprint 4A).
6. Las historias de `07_user_stories/` conservan el texto del gate (por ejemplo US-089 con 422 donde D14 fija 409, US-073 criterio 3 sin `decrypt`, US-087 criterio 4 sobre `frozen`). Igual que en el Sprint 2, las correcciones viven en las notas de cabecera de los desgloses y en `DECISIONES.md`.

## 14. Veredicto

> **READY_WITH_WARNINGS**

Justificación:

- Pilar 1: 25/25 historias entregadas con prueba, 22/22 endpoints y 2/2 filtros, 4/4 migraciones, 10/10 condiciones para VERDE, 31/31 hallazgos del diseño, 8/8 de la deuda heredada asignada al sprint, 22/22 contradicciones de contrato, 11/12 pasos de validación. Todo HIGH y MEDIUM de las revisiones (por slice, Fase 4, V10, V9) quedó corregido o aceptado con decisión y dueño; 0 CRITICAL en todo el sprint. No hay deuda sin dueño: los cuatro puntos que quedaban se asignaron en `8ef1a91`, y P2-1 queda con dueño propuesto en este archivo.
- Pilar 2: imágenes vigentes y bundle igual al del código; escrituras reales por la pantalla sin un solo 5xx; la base muestra la activación atómica, la reversión, la anulación con motivo, el `reveal` auditado sin valor y la baja lógica; la doble anulación da 200 y 409 sin efectos; el contrato se exporta igual dos veces; la cadena de auditoría está íntegra; la suite del api da 3.883 ok y 97 %.
- Por qué no READY_FOR_RELEASE:
  1. V12 sin hacer: la rama no está en `origin`, así que la CI (seis jobs, incluido `e2e-stack` con las `USER_*` ×100 de E15) nunca corrió. Es el gate que falta y lo hace una persona.
  2. P2-1: el plan de la demo no se puede vender por la pantalla en la base de desarrollo por la acumulación de planes de E2E. No afecta a producción, pero rompe la demo tal como está escrita y crece con cada corrida.
  3. Residuales aceptados con dueño que tocan la seguridad de la caja: el rol del api sigue siendo dueño y superusuario y podría apagar los triggers de inmutabilidad (S3-D49, V10 I-2 → S4B-W0-2); el texto libre de referencias y motivos queda para siempre en la auditoría (S3-D50 → US-119).

Condiciones para el release:

- Push, PR y CI en verde en `api`, `web`, `images`, `scripts`, `secrets-scan` y `e2e-stack`; merge.
- Registrar P2-1 en `DECISIONES.md` con su dueño (Sprint 4A) o limpiar los planes de E2E cuando exista la baja de planes.
- Corregir en `SPRINT-03.md` los "[pendiente de cita]" y los "Pendiente de dueño" ya resueltos, y los tres hashes reescritos (discrepancias 1 y 2).
