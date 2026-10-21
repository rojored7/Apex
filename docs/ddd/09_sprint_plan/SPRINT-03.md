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
   - Si el pago supera el saldo, la pantalla muestra una advertencia y pide confirmación (Q5).
3. **Anular un pago.** El admin anula el segundo pago con motivo, y la membresía vuelve a `pending_payment`.
   - `UPDATE payments.payments SET amount_cop = 1` falla por el trigger.
   - Anular dos veces el mismo pago también falla.
4. **Renovar antes de vencer.** La nueva membresía empieza el día siguiente al fin de la vigente (Q1). Si se intenta crear una que se solape, la API responde 409 y el `EXCLUDE USING gist` la rechaza también en la base.
5. **Congelar y anular.**
   - Congelar 10 días extiende el fin.
   - La tercera congelación responde 409 (Q9).
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

No hay infraestructura nueva. Solo se verifica la línea base:
- `docker compose up -d --build`;
- `docker compose exec api alembic current` en `0007_plans`;
- `run-gates.sh` en verde sobre `main`.

### Waves 3a/3b · Backend, alternadas por slice

- **Slice S3-B1 · Reglas puras y vender.** Historias: US-083 y US-084.
  - Rojo:
    - `tests/memberships/test_rules.py`;
    - `tests/memberships/test_sell_service.py`;
    - `tests/memberships/test_sell_router.py`.
  - Verde:
    - funciones puras: `compute_end_date`, `compute_status(membership, today, expiring_days)`, `covers`, `next_start_for_renewal` y `classify_open`;
    - **migración `0008_memberships`**, con `EXCLUDE USING gist` (Q1) y sin las columnas `frozen_*`;
    - `sell(..., max_retroactive_days)`, `get_payment_target` y `refs_for`;
    - Q4: `classes_remaining` todavía no se descuenta.
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
    - sección `payment_methods` y `GET /payments/methods`.
  - Gate: `slice-gate.sh payments` y `slice-gate.sh settings`, cada uno con sus archivos, más el ciclo de Alembic.
  - La prueba de router de `POST /memberships/{id}/payments` (`tests/payments/test_router_register.py`) pasa a S3-B4, porque necesita el gate real (M-1).
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
    - handler de `PaymentRegistered` que activa por cobertura (RN-03).
  - Gate: `slice-gate.sh payments` y `slice-gate.sh memberships`, cada uno con sus archivos, más el ciclo de Alembic.
    - Desde aquí `test_service_import_graph.py` bloquea todos los checkpoints, porque `tests/architecture` corre en cada gate.
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
    - `tests/memberships/test_list_service.py`, incluida la parte `-m slow`;
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
    - `tests/payments/test_list.py`, `test_list_filters.py`, `test_list_performance.py` y `test_router_list.py`;
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
    - `tests/e2e/members-mobile.spec.ts`.
  - Verde:
    - chips, incluido "Pendiente de pago" (`DESIGN-GAP`);
    - selector de plan;
    - `Socios_Movil`.
  - Gate: `slice-gate.sh web/members <archivos de Rojo>`.
- **Slice S3-F3 · Vender, primer pago y renovar.** Historias: US-084, US-085 y US-088 (front).
  - Rojo:
    - pruebas de venta en `src/features/memberships`;
    - `tests/e2e/sell-with-payment.spec.ts`.
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
    - `useMembershipSummary`.
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

- E2E:
  - `sell-with-payment.spec.ts`;
  - `members-mobile.spec.ts`.
- Pruebas de rendimiento `-m slow` de pagos y membresías.
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
- **Settings (solo admin):** `GET` y `PATCH /api/v1/settings/payment_methods`.

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
     - `test_service_import_graph.py` corre en cada gate desde S3-B4;
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
- E2E en verde: `sell-with-payment.spec.ts` y `members-mobile.spec.ts`.
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
  - los montos van en `int` COP.
- Paso humano: push, PR con CI en verde y merge.
- `verify-delivery`, con una venta y una anulación reales hechas por la pantalla.
