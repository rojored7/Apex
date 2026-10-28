# Sprint 3 · Núcleo comercial: membresías, pagos y ficha del socio

- Versión: v0.1.
- Épicas:
  - EP-09 completa, salvo US-094;
  - EP-10 completa;
  - US-056 de EP-05;
  - el resto de EP-07, salvo US-077.
- Tamaño: 25 historias, 78 puntos, 389 h relativas.
- Rama: `feat/sprint-03-membresias-pagos`.
- Historias del sprint: US-056, US-071, US-072, US-073, US-074, US-075, US-076, US-083, US-084, US-085, US-086, US-087, US-088, US-089, US-090, US-091, US-092, US-093, US-095, US-096, US-097, US-098, US-099, US-100, US-101.

Plan de ejecución: `docs/ddd/blueprints/sprint-03-plan.md` (20 slices, enmiendas E1 a E16). Este documento se corrigió en S3-W0-1 con sus contradicciones de contrato (S3-C1 a S3-C22, `docs/ddd/DECISIONES.md`, "Sprint 3"); donde todavía choquen, manda el plan.

## Objetivo

Cerrar el ciclo comercial del box en una sola iteración. Membresías y pagos van juntos porque no funcionan uno sin el otro (S5, RN-03). Al terminar, el box puede:
- vender un plan;
- cobrarlo de forma atómica;
- activar la membresía cuando los pagos la cubren;
- renovar antes de que venza;
- congelar y anular;
- corregir pagos sin editarlos nunca.

La ficha del socio muestra sus datos enmascarados, sus membresías y sus pagos. Revelar un dato queda auditado.

## Demo al final del sprint

Antes de empezar: `docker compose up -d --build` y entrar como admin.

1. **Vender con primer pago.** Desde la ficha, vender "Mensual" con un primer pago de $ 120.000 en efectivo. La membresía queda `active` en la misma transacción. En la base aparecen la fila de `memberships`, la fila de `payments` con `member_id` copiado y las dos entradas de auditoría.
2. **Pago parcial y cobertura.**
   - Con un pago de $ 60.000, la membresía queda en "Pendiente de pago" (Q3).
   - Al registrar otros $ 60.000, pasa a `active`.
   - Si el pago supera el saldo, el API responde 409 `payment_exceeds_balance` sin `confirm_overpayment`; la pantalla muestra la advertencia y reenvía con la confirmación (Q5, S3-D41, S3-C22). Un pago igual en los últimos 120 s responde 409 `payment_possible_duplicate` hasta confirmarlo.
3. **Anular un pago.** El admin anula el segundo pago con motivo, y la membresía vuelve a `pending_payment`.
   - `UPDATE payments.payments SET amount_cop = 1` falla por el trigger (`payments_immutable`).
   - Anular dos veces el mismo pago responde 409 `payment_already_voided`.
4. **Renovar antes de vencer.** La nueva membresía empieza el día siguiente al fin de la vigente (Q1). Si se intenta crear una que se solape, la API responde 409 y el `EXCLUDE USING gist` la rechaza también en la base.
5. **Congelar y anular.**
   - Congelar 10 días extiende el fin.
   - La tercera congelación responde 409 `freeze_limit_reached` (Q9, D14).
   - Pagar una membresía anulada responde 409 `membership_cancelled`.
6. **Ficha del socio.**
   - El documento aparece como `CC •••• 4417`, enmascarado en memoria (N-01).
   - "Mostrar" deja una fila `reveal` en la auditoría y una `decrypt` en `crypto_ops`.
   - El coach edita el teléfono, pero no puede cambiar el documento (N-20).
   - Al dar de baja al socio, la ficha queda en solo lectura con el chip "Dados de baja".
7. **Listas y resumen.**
   - La lista de socios filtra por estado y por plan.
   - A 390 px de ancho, la lista se muestra en tarjetas.
   - `GET /payments/summary` cuadra con la lista de pagos del mes.

## Dependencias de sprints anteriores

- **Sprint 2:**
  - US-058: `memberships_policy()`.
  - US-069 y US-070: `ref`, `ensure_exists`, `search_ids` y `names_for`.
  - US-078 y US-079: `plans.service.get(for_share=True)` y `names_for`.
  - US-054 y US-055: registro de secciones y hooks.
  - US-041: `auth.service.names_for`.
  - US-074 reutiliza `tests/audit/test_reveal_entry.py`, de US-107.
  - El shell del front.
- **Sprint 1:**
  - US-014, US-016, US-028 y US-029.
  - El kit.
- **Sprint 0:** `btree_gist` en `0001`.

Decisiones que se aplican: Q1, Q2, Q3, Q5, Q6, Q7, Q9, Q11, Q28; N-01, N-20, N-23, N-24, N-25, N-26, N-27, N-28; G-03, G-04; y el refinamiento de US-056.

## Historias en orden de ejecución

Patrón de v0.1: en cada slice van primero el Rojo (stubs y pruebas) y después el Verde. El gate se corre con los archivos del slice más `tests/architecture`, y después se hace el checkpoint.

El orden respeta las migraciones (`0008` → `0009` → `0010` → `0011`) y la ruta crítica US-084 → US-095 → US-096 → US-085 → US-086 → US-092.

### Wave 0 · Infraestructura (`devops-wsl2-docker`)

Corregido por `docs/ddd/blueprints/sprint-03-plan.md` (S3-C20): la Wave 0 tiene dos slices.
- **Slice S3-W0-1 · Línea base, imágenes por digest, dependencias de desarrollo, `.env.seed` y documentación.**
  - Línea base: `docker compose up -d --build`; `docker compose exec api alembic current` en `0007_plans`; `run-gates.sh` en verde sobre la rama.
  - Imágenes base por digest en los `Dockerfile`, los dos Compose y `test_nginx_conf.sh`, vigiladas por `scripts/ci/test_images_pinned.sh` (S3-D62).
  - `vitest` y `stylelint` actualizados hacia `npm audit --audit-level=high` en cero (S3-D63); queda un residual sin arreglo publicado (`braces`, vía `stylelint`), registrado en `DECISIONES.md`, "S3-W0-1 · Infraestructura y dependencias".
  - `.env.seed` local borrado (S3-D64); `*.sql.gz` en `.gitignore` (S3-D58).
  - Decisiones del sprint en `DECISIONES.md` y correcciones de contrato en los documentos (condiciones 3, 4 y 10).
- **Slice S3-W0-2 · Tiempos de espera de la base, 503 `busy` y helpers comunes de `core`.** `lock_timeout`, `statement_timeout` e `idle_in_transaction_session_timeout` por `Settings` (S3-D43), 503 `busy` con `Retry-After: 1` (S3-D67), `enforce_user_limit` con topes configurables (S3-D59, S3-D76), `StaffDep` y `AdminDep`, `ID_BATCH` y `chunked()`.

### Waves 3a/3b · Backend, alternadas por slice

- **Slice S3-B1 · Reglas puras y vender.** Historias: US-083 y US-084.
  - Rojo:
    - `tests/memberships/test_rules.py`;
    - `tests/memberships/test_sell_service.py`;
    - `tests/memberships/test_sell_router.py`.
  - Verde:
    - funciones puras: `compute_end_date`, `compute_status(snapshot, today, expiring_days, freezes)` (cuatro argumentos, `freezes` obligatorio; S3-C12), `covers`, `next_start_for_renewal` y `classify_open`;
    - **migración `0008_memberships`**, con `EXCLUDE USING gist` (Q1) y sin las columnas `frozen_*`;
    - `sell(..., enforce_retroactive_limit=True)` (el service lee `memberships_policy`; sin `by` ni `max_retroactive_days` desde el router; S3-C13), `get_payment_target` y `refs_for`;
    - Q4: `classes_remaining` todavía no se descuenta.
    - `tests/architecture/test_service_import_graph.py` cambia aquí (S3-C19): desde S3-B1 bloquea todos los checkpoints.
  - Gate: `slice-gate.sh memberships <archivos de Rojo>` más el ciclo de Alembic.
- **Slice S3-B2 · Congelar.** Historia: US-089.
  - Rojo:
    - `tests/memberships/test_freeze_rules.py`;
    - `tests/memberships/test_freeze_service.py`;
    - `tests/memberships/test_freeze_router.py`.
  - Verde:
    - **migración `0009_membership_freezes`**;
    - `apply_freeze` pura, que recibe los límites;
    - 409 `overlaps_future_membership`.
  - Gate: `slice-gate.sh memberships <archivos de Rojo>` más el ciclo de Alembic.
- **Slice S3-B3 · Registrar pago y medios de pago.** Historias: US-095 y US-056.
  - Rojo:
    - `tests/payments/test_rules.py`;
    - `tests/payments/test_register.py`;
    - `tests/settings/test_payment_methods_rules.py`, `test_payment_methods_service.py` y `test_payment_methods_router.py`;
    - `tests/payments/test_payment_methods_router.py`;
    - `tests/architecture/test_payment_method_codes.py`.
    - Doble en `conftest` (M-1): `tests/payments/conftest.py` registra un doble de `membership_payability` en `set_membership_gate`. Las pruebas de service de este slice no dependen así de que memberships haya registrado el puerto.
  - Verde:
    - **migración `0010_payments`**, con `member_id NOT NULL`;
    - `register`, que hace flush antes de emitir `PaymentRegistered`;
    - `sum_not_voided`;
    - puerto `MembershipGate` (G-03);
    - sección `payment_methods` y `GET /payments/methods`, que responde el objeto `PaymentMethodsOut { items }` (S3-C7, D25).
  - Gate: `slice-gate.sh payments` y `slice-gate.sh settings`, cada uno con sus archivos, más el ciclo de Alembic.
  - `POST /memberships/{id}/payments` no se publica en este slice (E9, S3-D77): `register` queda como service probado con `gate_doble`; la ruta, su límite y su prueba de router (`tests/payments/test_router_register.py`) nacen en S3-B4, porque necesitan el gate real (M-1).
- **Slice S3-B4 · Inmutabilidad, venta con primer pago y activación.** Historias: US-096, US-085 y US-086.
  - Paso previo: volcado `docker compose exec db pg_dump -U <usuario> -Fc apex > docs/scratch/sprint-03-antes-0011.dump` antes de aplicar `0011`, que trae el trigger de pagos.
  - Rojo:
    - `tests/payments/test_can_void.py`;
    - `tests/payments/test_immutability.py`;
    - `tests/payments/test_router_register.py`, contra el gate real (M-1);
    - `tests/memberships/test_sell_with_payment_service.py`;
    - `tests/memberships/test_activation_service.py`;
    - `tests/architecture/test_payments_immutability_code.py`;
    - `tests/architecture/test_gates_registered.py`;
    - `tests/architecture/test_service_import_graph.py`.
  - Verde:
    - **migración `0011_payments_immutability`**: solo deja pasar la anulación, una vez y sobre sus columnas, y bloquea `TRUNCATE`;
    - `can_void`;
    - memberships registra `membership_payability` en `set_membership_gate`;
    - `sell` con `first_payment`;
    - handler de `PaymentRegistered` que activa por cobertura (RN-03);
    - se publica `POST /memberships/{id}/payments` (E9, S3-D77).
  - Gate: `slice-gate.sh payments` y `slice-gate.sh memberships`, cada uno con sus archivos, más el ciclo de Alembic.
    - `test_service_import_graph.py` bloquea todos los checkpoints desde S3-B1 (S3-C19); aquí gana la arista `memberships -> payments` y desde aquí también bloquea el gate real.
- **Slice S3-B5 · Anular pago y revertir la activación.** Historias: US-097 y US-087.
  - Rojo:
    - `tests/payments/test_void_rules.py`, `test_void.py` y `test_router_void.py`;
    - `tests/memberships/test_revert_activation_service.py`.
  - Verde:
    - `void`, que traduce el error del trigger a 409;
    - `PaymentVoided` emitido después del flush;
    - la reversión conserva las congelaciones (N-25).
  - Gate: `slice-gate.sh payments` y `slice-gate.sh memberships`, cada uno con sus archivos.
- **Slice S3-B6 · Renovar y anular membresía.** Historias: US-088 y US-090.
  - Rojo:
    - `tests/memberships/test_renew_service.py` y `test_renew_router.py`;
    - `tests/memberships/test_cancel_service.py` y `test_cancel_router.py`.
  - Verde:
    - `renew: true` ignora `start_date`;
    - `renewal-preview`;
    - `cancel` solo para admin, con motivo.
  - Gate: `slice-gate.sh memberships <archivos de Rojo>`.
- **Slice S3-B7 · Listar membresías y consultas de estado.** Historias: US-091 y US-092.
  - Rojo:
    - `tests/memberships/test_list_service.py`; la parte de rendimiento va en `tests/memberships/test_list_perf.py`, con el marcador `-m perf` (S3-C14, D29);
    - `tests/memberships/test_list_router.py`;
    - `tests/memberships/test_status_queries_service.py`;
    - `tests/memberships/test_summary_router.py`;
    - `tests/architecture/test_no_cross_schema_sql.py`.
  - Verde:
    - lista, y `GET /memberships/{id}` con `paid_cop`;
    - `summary()`;
    - `status_for`, `member_ids_by_status` y `count_active_by_plan` (G-04).
  - Gate: `slice-gate.sh memberships <archivos de Rojo>`.
- **Slice S3-B8 · Listas, detalle y resumen de pagos.** Historias: US-098, US-099 y US-100.
  - Rojo:
    - `tests/payments/test_list.py`, `test_list_filters.py`, `test_list_perf.py` (marcador `perf`) y `test_router_list.py`;
    - `tests/payments/test_get.py` y `test_router_get.py`;
    - `tests/payments/test_month_bounds.py`, `test_summary.py` y `test_router_summary.py`.
  - Verde:
    - enriquecimiento por lote;
    - detalle;
    - `summary(month)` en hora de Bogotá.
  - Gate: `slice-gate.sh payments <archivos de Rojo>`.
- **Slice S3-B9 · Filtros de socios y ficha.** Historias: US-071 y US-073.
  - Rojo:
    - `tests/members/test_chip_to_filter.py`;
    - `tests/members/test_service_list_membership_filters.py` y `test_router_list_filters.py`;
    - `tests/members/test_service_get.py` y `test_router_get.py`.
  - Verde:
    - filtros por conjuntos de ids, sin JOIN (G-04);
    - import perezoso en lista blanca (G-03);
    - descifrado con propósito `mask`.
  - Gate: `slice-gate.sh members <archivos de Rojo>`.
- **Slice S3-B10 · Revelar, editar, dar de baja y reactivar.** Historias: US-074, US-075 y US-076.
  - Rojo:
    - `tests/members/test_service_reveal.py` y `test_router_reveal.py`;
    - `tests/audit/test_reveal_entry.py`, con el socio real;
    - `tests/members/test_member_patch_rules.py`, `test_service_update.py` y `test_router_update.py`;
    - `tests/members/test_service_deactivate.py` y `test_router_deactivate.py`;
    - `tests/architecture/test_no_physical_delete.py`;
    - extensión de `tests/core/test_logging_redact.py` con un `reveal` real, que cierra la tarea T8 de US-018 (A-6).
  - Verde:
    - `reveal` con `audit.record` en la misma transacción, `subject_member_id` y una fila `decrypt`;
    - editar recifra y reindexa, y solo el admin puede cambiar el documento;
    - baja lógica y `reactivate`.
  - Gate: `slice-gate.sh members`, `slice-gate.sh audit tests/audit/test_reveal_entry.py` y `slice-gate.sh core/logging tests/core/test_logging_redact.py`.
- **Slice S3-B11 · Pestañas de la ficha.** Historias: US-093 y US-101 (backend).
  - Rojo:
    - `tests/memberships/test_member_memberships_service.py` y `test_member_memberships_router.py`;
    - `tests/payments/test_list_for_member.py` y `test_router_member_payments.py`.
  - Verde: `GET /members/{id}/memberships` y `GET /members/{id}/payments`.
  - Gate: `slice-gate.sh memberships` y `slice-gate.sh payments`, cada uno con sus archivos.

### Waves 5a/5b · Front, alternadas por slice

- **Slice S3-F1 · Ficha del socio.** Historias: US-073, US-074, US-075 y US-076 (front).
  - Rojo:
    - `src/features/members/pages/MemberDetailPage.test.tsx`;
    - `src/shared/ui/MaskedValue.reveal.test.tsx`;
    - `src/features/members/pages/MemberFormPage.edit.test.tsx`;
    - pruebas de baja.
  - Verde:
    - `Socio_Ficha`, con `MaskedValue` conectado (cierra el criterio diferido de US-066 sobre `onReveal`);
    - edición;
    - baja y reactivar.
  - Gate: `slice-gate.sh web/members` y `slice-gate.sh web/shared`, cada uno con sus archivos.
- **Slice S3-F2 · Filtros de la lista y vista móvil.** Historias: US-071 y US-072.
  - Rojo:
    - `src/features/members/components`;
    - `MemberCardList.test.tsx`;
    - `tests/e2e/members-mobile.spec.ts` (proyecto `preview`) y `tests/e2e/stack/members-mobile.spec.ts` (proyecto `stack`; S3-D72).
  - Verde:
    - chips, incluido "Pendiente de pago" (`DESIGN-GAP`);
    - selector de plan;
    - `Socios_Movil`.
  - Gate: `slice-gate.sh web/members <archivos de Rojo>`.
- **Slice S3-F3 · Vender, primer pago y renovar.** Historias: US-084, US-085 y US-088 (front).
  - Rojo:
    - pruebas de venta en `src/features/memberships`;
    - `tests/e2e/sell-with-payment.spec.ts` (proyecto `preview`); la gemela `tests/e2e/stack/sell-with-payment.spec.ts` se corre en la validación V4 (S3-D78).
  - Verde: `Membresia_Vender` en `/membresias/vender?socio=:id&renovar=1`.
  - Gate: `slice-gate.sh web/memberships <archivos de Rojo>`.
- **Slice S3-F4 · Registrar y anular pagos.** Historias: US-056, US-095 y US-097 (front).
  - Rojo:
    - pruebas de `src/features/payments`;
    - `VoidPaymentModal.test.tsx`;
    - la pestaña de medios de pago en `src/features/system`.
  - Verde:
    - pestaña "Medios de pago";
    - `RegisterPaymentPanel`, con la advertencia de Q5;
    - `VoidPaymentModal`.
  - Gate: `slice-gate.sh web/payments` y `slice-gate.sh web/system`, cada uno con sus archivos.
- **Slice S3-F5 · Pantalla de membresías.** Historias: US-089, US-090, US-091 y US-092 (front).
  - Rojo: pruebas de la lista, de congelar, de anular y del resumen.
  - Verde:
    - `Membresias`, con sus modales;
    - consume `useMembershipSummary`, que nace en S3-F4 en `web/src/shared/data/memberships.ts` (E10, S3-D78).
  - Gate: `slice-gate.sh web/memberships <archivos de Rojo>`.
- **Slice S3-F6 · Pantalla de pagos.** Historias: US-098, US-099 y US-100 (front).
  - Rojo:
    - `PaymentsPage.test.tsx`;
    - `PaymentDetailModal.test.tsx`;
    - `MonthSummary.test.tsx`.
  - Verde: `Pagos`, con filtros, modal de detalle y resumen del mes.
  - Gate: `slice-gate.sh web/payments <archivos de Rojo>`.
- **Slice S3-F7 · Pestañas Membresías y Pagos de la ficha.** Historias: US-093 y US-101 (front).
  - Rojo:
    - pruebas de la pestaña en `src/features/memberships`;
    - `MemberPaymentsTab.test.tsx`.
  - Verde: botones Renovar, Congelar y Anular, y el panel de pago con el socio preseleccionado.
  - Gate: `slice-gate.sh web/memberships` y `slice-gate.sh web/members`, cada uno con sus archivos.

### Validación del sprint

- E2E (S3-D72):
  - proyecto `stack` (`web/tests/e2e/stack/`): `sell-with-payment.spec.ts`, `payment-void.spec.ts`, `member-detail.spec.ts` y `members-mobile.spec.ts`;
  - proyecto `preview` (`web/tests/e2e/`): `sell-with-payment.spec.ts` y `members-mobile.spec.ts`.
- Pruebas de rendimiento `-m perf` de pagos y membresías (`tests/payments/test_list_perf.py`, `tests/memberships/test_list_perf.py`; S3-C14). No son gate (S2-D27).
- Evidencia manual en la base de desarrollo:
  - el `EXCLUDE` rechaza un solapamiento;
  - el trigger rechaza un `UPDATE`;
  - la auditoría tiene filas `insert`, `update` y `reveal`.
- Paso humano: push de la rama y PR.

## Migraciones que aplica

- `0008_memberships` (US-084).
- `0009_membership_freezes` (US-089).
- `0010_payments` (US-095).
- `0011_payments_immutability` (US-096), con volcado `pg_dump` previo.

## Endpoints que expone

22 endpoints.

- **Members:**
  - Admin y coach:
    - `GET /api/v1/members/{id}`;
    - `PATCH /api/v1/members/{id}`;
    - `POST /api/v1/members/{id}/reveal`;
    - `GET /api/v1/members/{id}/memberships`;
    - `POST /api/v1/members/{id}/memberships`;
    - `GET /api/v1/members/{id}/memberships/renewal-preview`;
    - `GET /api/v1/members/{id}/payments`.
  - Solo admin:
    - `DELETE /api/v1/members/{id}`;
    - `POST /api/v1/members/{id}/reactivate`.
- **Memberships:**
  - Admin y coach:
    - `GET /api/v1/memberships`;
    - `GET /api/v1/memberships/summary`;
    - `GET /api/v1/memberships/{id}`;
    - `POST /api/v1/memberships/{id}/freeze`;
    - `POST /api/v1/memberships/{id}/payments`.
  - Solo admin: `POST /api/v1/memberships/{id}/cancel`.
- **Payments:**
  - Admin y coach:
    - `GET /api/v1/payments`;
    - `GET /api/v1/payments/summary`;
    - `GET /api/v1/payments/methods`;
    - `GET /api/v1/payments/{id}`.
  - Solo admin: `POST /api/v1/payments/{id}/void`.
  - `GET /api/v1/payments/methods` responde un objeto `{ items }`, no un arreglo (S3-C7).
- **Settings (solo admin):** `GET` y `PATCH /api/v1/settings/payment_methods`.

"Socios con él" de `Planes.html` no entra en este sprint: queda para US-082 (Sprint 4A; D37).

Además, `GET /api/v1/members` gana los filtros `membership_status` y `plan_id`. Las rutas fijas se registran antes que las que llevan parámetro.

## Tests de arquitectura que deben pasar

Corren en cada gate de slice (A-5).

- Los de los Sprints 0 a 2.
- `test_banned_imports.py` (US-083) y `test_no_cross_models.py` (US-084), ampliadas.
- `test_service_import_graph.py` (US-085). Es la consolidada: absorbe `test_service_import_cycles.py`, `test_payments_does_not_import_memberships.py` y `test_payments_dependencies.py`.
- `test_gates_registered.py` (US-085).
- `test_payment_method_codes.py` (US-056).
- `test_payments_immutability_code.py` (US-096).
- `test_no_cross_schema_sql.py` (US-091).
- `test_no_physical_delete.py` (US-076).

## Riesgos y mitigación

1. [HIGH] Este sprint concentra el nudo de dependencias más denso de v0.1: el bus transaccional, el puerto G-03, el handler de cobertura y el trigger.
   - Mitigación:
     - slices pequeños, en orden estricto;
     - `test_service_import_graph.py` corre en cada gate desde S3-B1 (S3-C19);
     - al cerrar cada slice se corre la suite completa de `memberships` y `payments` con `run-gates.sh`.
2. [HIGH] Si el trigger de `0011` queda mal escrito, puede bloquear anulaciones legítimas o dejar editar la caja.
   - Mitigación:
     - una prueba por cada columna permitida y por cada columna prohibida, más doble anulación, `DELETE` y `TRUNCATE`;
     - volcado de la base antes de aplicar la migración.
3. [HIGH] El `EXCLUDE` y Q1 pueden chocar con la renovación anticipada.
   - Mitigación: pruebas con una membresía vigente más una futura, con una congelada y extendida, y con una cancelada.
4. [MEDIUM] Hay una carrera entre vender y dar de baja un plan.
   - Mitigación: `get(for_share=True)` desde S3-B1. US-082 cierra el caso en el Sprint 4A.
5. [MEDIUM] El doble de `membership_payability` puede ocultar un error del gate real.
   - Mitigación: la prueba de router real y `test_gates_registered.py` entran en S3-B4. El doble queda solo en `tests/payments/conftest.py`.

## Definición de hecho del sprint

- Los 11 slices de backend y los 7 de front confirmados con `checkpoint-commit.sh`.
- `run-gates.sh` en verde: cobertura global de `app` en 80 % o más, y front completo.
- `cd api && uv run pytest tests/architecture -q` en verde.
- Ciclo de Alembic sobre `0011` y volcado previo guardado.
- `docs/openapi.json` y los tipos del front regenerados.
- E2E en verde: los cuatro del proyecto `stack` y los dos del proyecto `preview` de la validación.
- Smoke con evidencia SQL de:
  - la activación atómica;
  - la reversión;
  - el `EXCLUDE`;
  - el trigger;
  - las filas `reveal` y `decrypt`.
- Seguridad (`security-reviewer`):
  - los pagos no se pueden modificar ni por API ni por SQL;
  - anular y cancelar son solo para admin;
  - todo `reveal` queda auditado;
  - las listas no devuelven datos cifrados;
  - los montos van en `int` COP;
  - cuando la base agota `lock_timeout` o `statement_timeout`, o detecta un interbloqueo, el API responde 503 `busy` con `Retry-After: 1` y nunca 500 (S3-D43, S3-D67).
- Paso humano: push, PR con CI en verde y merge.
- `verify-delivery`, con una venta y una anulación reales hechas por la pantalla.

## Estado al cierre del sprint (documentación)

Fecha: 2026-10-28. Rama `feat/sprint-03-membresias-pagos`. HEAD antes de esta documentación: `0fa1270`. Sin push: la rama está en local y el push y el PR los hace una persona (ver "Pendiente humano").

### Slices ejecutados

Cada slice tiene su checkpoint (`chore(checkpoint)`). Los 20 slices del plan están confirmados en 21 checkpoints (B9 se confirmó en dos, B9a y B9b): W0-1 y W0-2, B1 a B11 y F1 a F7.

- **Wave 0:** W0-1 `452453b` (línea base, imágenes por digest, dependencias de desarrollo y decisiones); W0-2 `5e84bab` (tiempos de espera de la base, 503 `busy` y helpers de límite por usuario). Son dos slices, no uno (S3-C20).
- **Backend:**
  - B1 `5c9bb45` (reglas puras, venta atómica, migración 0008);
  - B2 `5d412bd` (congelar, migración 0009);
  - B3 `d5b37b9` (registrar pago, medios de pago, migración 0010);
  - B4 `3d7702b` (inmutabilidad, venta con primer pago, activación, migración 0011);
  - B5 `47c5692` (anular pago y reversión);
  - B6 `3136ee6` (renovar y anular membresía);
  - B7 `9f5ae13` (lista de membresías, resumen y consultas de estado);
  - B8 `208117e` (lista, detalle y resumen de pagos);
  - B9 en dos checkpoints (S3-D73): B9a `ee609f1` (partición de `members/service.py` sin cambio de comportamiento) y B9b `7d78c05` (filtros de socios y ficha enmascarada);
  - B10 `4b4ce60` (revelar, editar, dar de baja y reactivar);
  - B11 `41e244e` (pestañas de membresías y pagos de la ficha, cierre del backend).
- **Front** (orden de ejecución según S3-D66: F3, F4, F5, F6, F2, F1, F7):
  - F3 `bf0626d` (vender, primer pago y renovar);
  - F4 `afe6526` (registrar y anular pagos, panel por URL, medios de pago);
  - F5 `5fdf793` (membresías con congelar y anular);
  - F6 `8026ab1` (pagos con detalle y resumen del mes);
  - F2 `c6d9590` (filtros de socios, chips y vista móvil);
  - F1 `d139457` (ficha del socio con revelado auditado, edición, baja y reactivación);
  - F7 `889f365` (pestañas de la ficha; `ce932d0` estabiliza los E2E del stack).
- **Revisiones y correcciones posteriores:**
  - Fase 4 backend `6e8406f`;
  - Fase 4 front `b39d160`;
  - V10 (seguridad posterior, backend e infra) `7962caa`;
  - migración del front a Zod 4 (GHSA-mrhx-c7xc-m3w5) `6c98eb6`.
- **Correcciones de validación:** `3c7db38` (evidencia V2 a V8), `7bb4e55` y `dab1cc4` (E2E del preview), `ece2f4e`, `5d2b4d1` y `958a070` (E2E del stack; en el cuaderno aparecen con sus hashes previos a la reescritura del trailer: `59bf09d`, `43b4f09`, `561ae32`). Los merges de los worktrees de los agentes del front van en el `git log`, no aquí.

### Conteos finales

- **API** (sin cambios en `api/` desde `7962caa`): **3.883 pruebas en verde** (1.517 y 2.366, en las dos mitades de la suite con `-m "not perf"`), **3 saltadas** por NTFS, **8 `perf`** fuera de los gates. Fuente: "Fase 4 · Backend" y "V10 · Corrección" del cuaderno. Cobertura global de `app`: **97 %** (6.835 sentencias, 165 sin cubrir; fuente: bloque "V9.1 · `run-gates.sh` completo y V12 · higiene" del cuaderno).
- **Front** (sin cambios en `web/` desde `6c98eb6`, tras la migración a Zod 4): **156 archivos y 2.788 pruebas en verde**. Cobertura: 97,98 % de sentencias, 94,56 % de ramas, 97,09 % de funciones y 98,87 % de líneas. Build: `main` 418,30 kB y el chunk `zod` 92,05 kB. Fuente: "V9 · Migración a Zod 4" del cuaderno del front.
- **`run-gates.sh` en verde el 2026-10-28:** corrida por el orquestador sobre `aacd8b0` (mismo código que el HEAD final): api 3.883 ok con 97 % de cobertura, front 2.788 ok, lint, tsc, build y scripts de infraestructura en verde, salida `run-gates: todos los gates en verde`. Fuente: bloque "V9.1 · `run-gates.sh` completo y V12 · higiene" del cuaderno.

### Validación V2 a V8, V9 y final

- **Migraciones:** `0008_memberships`, `0009_membership_freezes`, `0010_payments` y `0011_payments_immutability`. El ciclo `downgrade 0007_plans` y `upgrade head` se ejecutó en V2 sobre `apex-db-1` (el diferimiento de B11.6 a V2 queda cerrado), con volcado previo `docs/scratch/sprint-03-antes-v2.dump` (ver "Pendiente humano").
- **Tiempos `perf` (V5, dos corridas):** búsqueda por documento con 1.000 socios, 34,6 y 30,9 ms; login fallido ×20, p95 0,411 y 0,412 s; `membership_status=active` con 5.000 ids, 43,1 y 42,6 ms; `membership_status=none` con 5.000 ids, 138,8 y 161,4 ms; lista `expiring` con 1.000 socios y 3.000 membresías, 15,0 y 16,2 ms; resumen sin caché, 17,2 y 13,0 ms; lista de pagos con 10.000 pagos, 13,7 y 12,9 ms; resumen del mes con 10.000 pagos, 8,2 y 8,6 ms. Todo está por debajo de los topes (500 y 300 ms).
- **Smoke con evidencia SQL (V6):** activación atómica (membresía `active` con el pago en `payments`, auditoría `insert`, `insert`, `update`); reversión (`pending_payment`, fechas intactas, pago con `voided = t`); `EXCLUDE` (`ex_memberships_member_dates` rechaza el solapamiento, SQLSTATE 23P01); triggers (`payments_immutable`, `memberships_identity`, `memberships_no_delete`, `membership_freezes_append_only`, también con `session_replication_role = replica`); filas `reveal` y `decrypt` en `audit.audit_log` y `crypto_ops`, sin valores en claro en los logs; `verify_chain` sobre 2.914 filas, sin ruptura; 503 `busy` medido (10,03 s, `Retry-After: 1`).
- **E2E:**
  - `e2e:stack` con 35 de 35 en dos corridas seguidas después de V10 (V4 ya había dado 35 de 35 dos veces);
  - Playwright del proyecto `preview`: 144 de 144 (V4, dos veces, y de nuevo en la migración a Zod 4, tras corregir la CSP con `jitless`).
  - La corrida final del stack con Zod 4 la añade otro agente al cuaderno: ver `docs/scratch/sprint-03.md`, bloque "Validación final del stack con Zod 4". En el momento de escribir este estado, ese bloque todavía no aparece en el cuaderno.
- **Demo por pantalla (V7):** venta con cobro completo (`Al día`), venta parcial (`Pendiente de pago`), saldo con confirmaciones de sobrepago y duplicado, anulación de pago desde la ficha con reversión, renovación con inicio al día siguiente, congelación con la ventana y el límite de congelaciones, anulación, ficha con revelado, baja y reactivación, filtros de socios y resumen de pagos del mes.

### Contrato

- `docs/openapi.json`: **53 operaciones** (31 en `d65056e`, **22 nuevas**, 0 quitadas). Exportación idéntica en dos corridas; sha256 `3559f376…` después de V10.
- `GET /members` gana `membership_status` y `plan_id`, con las rutas fijas antes que las que llevan parámetro.
- Componente nuevo `MembershipStatus` (seis valores); `status` de `MembershipOut`, `MembershipRow` y `SellMembershipOut` lo referencia.
- Respuestas `429` nuevas: 10 en escrituras de solo admin (V10, S3-D100) y 2 en la baja y la reactivación de socios (Fase 4, S3-D97).
- `GET /payments/methods` responde `{ items }` (S3-C7).
- `web/src/core/api/types.ts` regenerado con `npm run gen:api` sin deriva.

### Revisiones de seguridad y de código

- **Por slice (`security-reviewer`):** ninguna revisión registrada dio CRITICAL ni HIGH. Los MEDIUM de B1, B2, B4 y B7 se corrigieron con prueba; el de B1 sobre `lock_member` en `sell` se cerró en B10.
- **Fase 4 backend (`code-reviewer` y `python-reviewer`):** `code-reviewer` dio 0 CRITICAL, 1 HIGH, 4 MEDIUM y 3 LOW; `python-reviewer` dio 0 CRITICAL, 0 HIGH, 5 MEDIUM y 7 LOW, con solapamientos (M1 es PM1, y M2 es PL5). Estado: todo corregido, salvo PM2 (MEDIUM de `python-reviewer`, `classes_remaining = 0`), **aceptado con decisión y dueño** (S3-D92, Sprint 7, US-160), y algunos LOW aceptados con justificación (L3, `list` sombrea al builtin, PL2 (c) y PL7 (b)).
- **Fase 4 front (`typescript-reviewer`):** 8 MEDIUM y 9 LOW en la primera revisión, todos corregidos salvo el LOW 5 (`enclosingFunction` por expresión regular), aceptado con justificación. La revisión final dio 0 CRITICAL, 0 HIGH, 2 MEDIUM y 4 LOW: el MEDIUM 2 es un cambio de texto intencional (M7), el LOW 5 queda aceptado y el resto está corregido.
- **V10 (`security-reviewer`):** M-A (MEDIUM) corregido; L-A y L-B corregidos; L-D corregido en el front; L-C documentado (borrado de volcados pendiente, ver "Pendiente humano"); I-2 con dueño S4B-W0-2; I-4 con dueño US-106; I-3 informativo.
- **V9 ligero:** `npm audit --omit=dev` bloqueaba por `zod` 3.25.76 (GHSA-mrhx-c7xc-m3w5). Resuelto con Zod 4.6.7 (S3-D105): `npm audit` da 0 en producción y en desarrollo.
- **Revisión W0-2 (dos MEDIUM no aplicados):** ver "Hallazgos abiertos".

### Desviaciones del plan (consolidado)

1. Wave 0 en dos slices, W0-1 y W0-2 (S3-C20).
2. S3-D43: los tiempos de espera tienen piso de 1.000 ms en producción (S3-D79) y las opciones del CLI viajan en `ctx.obj` (PL1 de la Fase 4).
3. 503 `busy`: `Retry-After: 1` y traducción en `get_session` (S3-D67). La descripción `503` va solo en las operaciones con seguridad declarada, no en las públicas (E16).
4. Confirmaciones en el servidor: el API responde 409 `payment_exceeds_balance` o `payment_possible_duplicate` y la pantalla reenvía con `confirm_overpayment` o `confirm_duplicate` (H-1, S3-D41; S3-C22).
5. `paid_at` por rol: el coach solo registra dentro de `max_retroactive_days` (422 `paid_at_too_retroactive`); el admin, sin ese límite (S3-D51).
6. B9 en dos checkpoints, `B9a` y `B9b` (S3-D73).
7. Orden del front: F3, F4, F5, F6, F2, F1, F7 (S3-D66).
8. `MemberPaymentsTab` vive en `web/src/features/payments/components/` (no en `memberships`), igual que su prueba.
9. Sin `CHECK` de fechas de anulación (`voided_at >= created_at` se descarta, S3-D68).
10. Sin siembra de 10.000 socios: el volumen es de 1.000 socios; los 10.000 se usan para pagos (S3-D71).
11. Ciclo de Alembic de B11.6 diferido a V2, donde se ejecutó sobre `apex-db-1`.
12. Nació `memberships/summary.py` (S3-D90), que no estaba en el plan.
13. `status` tipado como enum `MembershipStatus` en el contrato (S3-D96).
14. `admin-write` ampliado: a la baja y reactivación de socios (S3-D97) y a todas las escrituras de solo admin (S3-D100).
15. Migración del front a Zod 4 (S3-D105), que no estaba en el plan.
16. `membership_conflict` frente a `membership_overlap`: `sell` responde `membership_conflict` cuando hay una membresía vigente o futura, y `membership_overlap` solo contra una no cancelada que ya no es vigente (D8 en el código). El texto del plan no coincide con ese orden; no es un defecto (V7).
17. Texto de sobrepago: la pantalla dice "supera el saldo de la membresía" y el plan decía "saldo pendiente" (V7).
18. Regla de clases agotadas diferida a v0.4 (S3-D92).
19. Ventanas de topes por proceso: el api corre con un solo proceso (S3-D93).
20. Proyecto `stack` con 15 specs y 35 pruebas, más que las cuatro del plan (S3-D72).
21. El buscador del panel de pagos ofrece al socio inactivo (S3-D99). Se desvía de la indicación de deshabilitarlo porque el API lo acepta.
22. Ordenación "Vencimiento más próximo" fuera de v0.1 (S3-D98).

### Hallazgos que quedaron sin dueño al redactar este documento (resueltos en `8ef1a91`)

- **W0-2 MEDIUM-1:** `25P03` y los cortes del servidor quedan como 500 en lugar de 503. Aceptado con dueño **S4B-W0-2** (DECISIONES, "Dueños asignados al cierre del Sprint 3").
- **W0-2 MEDIUM-2:** un fallo al escribir `crypto_ops` durante el rollback tras un 55P03 da 500 en lugar de 503. Aceptado con dueño **S4B-W0-2** (misma sección de DECISIONES).
- **S3-D98 (ordenación por vencimiento):** no entra en v0.1; dueño: **revisión de diseño previa al Sprint 4A** (análisis de impacto del Sprint 4A).
- **Pendientes de diseño de BRECHAS §10** (por ejemplo "Guardar y vender membresía", estilo de "Cancelada", "Ocultar anulados" y el selector de mes de pagos): figuran como "Pendiente de diseño"; dueño: **revisión de diseño previa al Sprint 4A** con `docs/design/` como fuente de verdad.
- **Observación de V9:** el 413 de Nginx sale en HTML y no con el envelope JSON. El front lo trata como error genérico. Se anotó para cuando lleguen los adjuntos (v0.3).

### Deuda con dueño

- Clases agotadas (S3-D92, PM2): módulo `classes`, Sprint 7 (v0.4), US-160 (`SPRINT-07.md`).
- Rol del api no superusuario ni dueño de `payments`, `memberships` y `audit` (S3-D49, I-2 y L2 de B1): slice S4B-W0-2 (`SPRINT-04B.md`).
- `subject_member_id` en las congelaciones (L2 de B2): US-106, Sprint 4A.
- Orden de candados del comando `import-members` (S3-D95, PL6): una transacción por socio, en SPRINT-04B.
- Historial del socio, pestaña y caja de la ficha: US-106, Sprint 4A (S4A-F2).
- Nombre de usuario en lugar del correo parcial (S3-D57): US-110, Sprint 4A.
- Tablero de Inicio (KPIs): US-108, Sprint 4A (S4A-B8).
- "Socios con él" en Planes (D37): US-082, Sprint 4A.
- `DELETE /api/v1/plans/{id}` para los datos de prueba: Sprint 4A (`SPRINT-04A.md`, línea de `DELETE /api/v1/plans/{id}`).
- Dependencias de versión de BRECHAS §10: "Exportar" (v0.2, EP-16, US-139), foto y adjuntos (v0.3), asistencia (v0.4), último WOD (v0.5) y portal (v1.0); el 413 de Nginx con envelope JSON (v0.3).
- Límite `USER_*` en producción: lo decide quien administra el `.env` (W0-2, operador).
- N-6 (dueño S4B-W0-2) y N-7 (remedir el p99 en S4B-W0-2): heredadas del Sprint 2.

### Datos de prueba que quedan en `apex-db-1`

- 30 planes `E2E-tope-d78ef5-1` a `-30`, creados en la validación final del stack (topes `admin-write`). Quedan hasta el `DELETE /plans` del Sprint 4A.
- Plan "Mensual V50137" (120.000, 30 días), usado por la demo, y el plan 320.000/90 creado por error en el Sprint 2.
- Socios de la demo "… V50137" (Venta, Parcial, Renovar, Congelar, Ficha, CongelarLimite y Busy), con sus membresías y pagos.
- Planes, socios y ventas de las specs E2E.
- Tres coaches `@test.apex` (`coach-b3-smoke`, `coach-b7-smoke`, `coach-demo-mvjipju3`): fuera del patrón de V12, quedan para decidir aparte.
- Cuentas vivas tras V12: `admin@ejemplo.local` (no tocada), `system@apex.local` (inactiva, `is_active = false`) y las tres de arriba. Las 120 cuentas `coach-*@apex.test` se dieron de baja en V12 (204 cada una, auditadas).

### Pendiente humano

1. Push de la rama `feat/sprint-03-membresias-pagos`.
2. PR con la CI en verde en sus seis jobs: `api`, `web`, `images`, `scripts`, `secrets-scan` y `e2e-stack`. El job `e2e-stack` con las ocho `USER_*` ×100 solo se verifica en GitHub Actions. El paso `npm audit` del job `web` es informativo.
3. Merge.
4. Restablecer la contraseña del admin: `.env.seed` se borró en W0-1 (S3-D64). Se usa `tools issue-reset-link <admin> --as <admin>` (RUNBOOK §2).
5. Borrar los volcados `docs/scratch/sprint-03-antes-*.dump` (L-C de V10, RUNBOOK §10). **No se encuentran en `docs/scratch/` al cerrar**; hay que confirmar que no quedan copias en la máquina.
6. Cierre de `verify-delivery`: lo hace otro agente en `docs/scratch/sprint-03-verify-delivery.md`, y no forma parte de este commit.
