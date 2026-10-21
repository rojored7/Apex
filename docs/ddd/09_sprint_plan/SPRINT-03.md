# Sprint 3 · Núcleo comercial: membresías, pagos y ficha del socio

- Versión: v0.1.
- Épicas:
  - EP-09 completa, salvo US-094;
  - EP-10 completa;
  - US-056 de EP-05;
  - el resto de EP-07, salvo US-077.
- Tamaño: 25 historias, 78 puntos y 389 h relativas.
- Rama: `feat/sprint-03-membresias-pagos`.
- Historias del sprint: US-056, US-071, US-072, US-073, US-074, US-075, US-076, US-083, US-084, US-085, US-086, US-087, US-088, US-089, US-090, US-091, US-092, US-093, US-095, US-096, US-097, US-098, US-099, US-100, US-101.

## Objetivo

Cerrar el ciclo comercial del box en una sola iteración, porque membresías y pagos son una pareja inseparable (S5, RN-03): vender un plan, cobrarlo de forma atómica, activar por cobertura, renovar antes de vencer, congelar, anular y corregir pagos sin editarlos nunca.

La ficha del socio muestra sus datos enmascarados, sus membresías y sus pagos. Revelar un dato queda auditado.

## Demo al final del sprint

1. **Vender con primer pago.** Desde la ficha del socio, vender "Mensual" con un primer pago de $ 120.000 en efectivo. La membresía queda `active` en la misma transacción. En la base hay una fila en `memberships.memberships`, otra en `payments.payments` con `member_id` copiado, y las dos entradas de auditoría.
2. **Pago parcial y cobertura.**
   - Vender a otro socio con un pago de $ 60.000: la membresía queda en "Pendiente de pago", con el chip nuevo (Q3).
   - Registrar otros $ 60.000: pasa a `active`.
   - Pagar de más: el front advierte "este pago supera el saldo pendiente en $ X" y pide confirmación (Q5).
3. **Anular un pago.** El admin anula el segundo pago con un motivo: la membresía vuelve a `pending_payment` (US-087).
   - `UPDATE payments.payments SET amount_cop = 1` falla por el trigger.
   - Una segunda anulación del mismo pago falla.
4. **Renovar antes de vencer.** La nueva membresía empieza el día siguiente al `end_date` de la vigente (Q1). Una tercera membresía que se solape responde 409, y a mano la rechaza el `EXCLUDE USING gist`.
5. **Congelar y anular.**
   - Congelar 10 días extiende el fin.
   - La tercera congelación responde 409 por `max_freezes_per_membership = 2` (Q9).
   - Anular una membresía (solo admin) y luego intentar pagarla responde 409 `membership_cancelled`.
6. **Ficha del socio.**
   - Muestra `CC •••• 4417`, calculado en memoria con propósito `mask` (N-01).
   - "Mostrar" lo revela, con una fila `reveal` en la auditoría y otra `decrypt` en `crypto_ops`.
   - El coach edita el teléfono y no puede cambiar el documento (N-20).
   - Dar de baja deja la ficha en modo solo lectura, con el chip "Dados de baja".
7. **Listas y resumen.**
   - La lista de socios filtra por estado de membresía y por plan.
   - En un ancho de 390 px, la lista se ve como tarjetas.
   - `GET /payments/summary` muestra el total del mes, que cuadra con la lista de pagos del mes.

## Dependencias de sprints anteriores

- **Sprint 2:**
  - US-058 (`memberships_policy()`: `expiring_days`, límites de Q9 y `max_retroactive_days`);
  - US-069 y US-070 (`members.service.ref`, `ensure_exists`, `search_ids` y `names_for`);
  - US-078 y US-079 (`plans.service.get(for_share=True)` y `names_for`);
  - US-054 y US-055 (registro de secciones y hooks de Settings);
  - US-041 (`auth.service.names_for` con `display_name`);
  - el shell del front (US-061, US-067 y US-053).
- **Sprint 1:**
  - US-014 (bus transaccional);
  - US-016 (hook con `__audit_subject__`);
  - US-028 y US-029 (tipos cifrados y bitácora con `purpose`);
  - el kit `DataTable`, `Chips`, `SidePanel`, `ConfirmModal`, `Tabs` y `MaskedValue`.
- **Sprint 0:** `btree_gist`, que ya está en `0001`.

Decisiones que aplica este sprint:
- Q1: una vigente y una futura; `EXCLUDE`.
- Q2: renovar con `renew: true`.
- Q3: chip "Pendiente de pago".
- Q5: pago por encima del precio, con advertencia.
- Q6: `reveal` para admin y coach.
- Q7: congelar admin y coach; anular solo admin.
- Q9: límites de congelación.
- Q11 y Q28: `compute_status` con `expiring_days` y la fecha de Bogotá.
- N-01: enmascarado en memoria.
- N-20: bajas visibles, documento solo admin, `reactivate`.
- N-23: fin inclusivo.
- N-24: `start_date` hasta `max_retroactive_days` atrás; renovación con vista previa.
- N-25: `membership_freezes`.
- N-26: conteo por estado resuelto.
- N-27: `paid_at` sin futuro, con 5 minutos de tolerancia.
- N-28: se aceptan pagos sobre `expired` y `frozen`.
- G-03: puerto `set_membership_gate` e imports perezosos en lista blanca.
- G-04: lecturas a profundidad 2.
- Refinamiento de US-056: `GET /payments/methods`.

## Historias en orden de ejecución

### Wave 0 · Infraestructura (`devops-wsl2-docker`)

Este sprint no trae infraestructura nueva. La Wave 0 solo verifica la línea base:
- `docker compose -f infra/compose.yml -f infra/compose.dev.yml up -d`;
- `alembic current` en `0007_plans`;
- `run-gates.sh` en verde sobre `main`.

Si algo falla, se corrige antes de abrir la Wave 3a.

### Wave 3a · Tests de backend en rojo (`backend-qa-executor`)

- **S3-B1:**
  - `tests/memberships/test_rules.py`, con las reglas puras de fechas, estados y cobertura;
  - `tests/memberships/test_sell_service.py`;
  - `tests/memberships/test_sell_router.py`.
- **S3-B2:**
  - `tests/memberships/test_freeze_rules.py`;
  - `tests/memberships/test_freeze_service.py`;
  - `tests/memberships/test_freeze_router.py`.
- **S3-B3:**
  - `tests/payments/test_rules.py`, `test_register.py` y `test_router_register.py`;
  - `tests/settings/test_payment_methods_rules.py`, `test_payment_methods_service.py` y `test_payment_methods_router.py`;
  - `tests/payments/test_payment_methods_router.py`;
  - `tests/architecture/test_payment_method_codes.py`.
- **S3-B4:**
  - `tests/payments/test_can_void.py` y `tests/payments/test_immutability.py`;
  - `tests/memberships/test_sell_with_payment_service.py`;
  - `tests/memberships/test_activation_service.py`;
  - `tests/architecture/test_payments_immutability_code.py`;
  - `tests/architecture/test_gates_registered.py`;
  - `tests/architecture/test_service_import_graph.py`.
- **S3-B5:**
  - `tests/payments/test_void_rules.py`, `test_void.py` y `test_router_void.py`;
  - `tests/memberships/test_revert_activation_service.py`.
- **S3-B6:**
  - `tests/memberships/test_renew_service.py` y `test_renew_router.py`;
  - `tests/memberships/test_cancel_service.py` y `test_cancel_router.py`.
- **S3-B7:**
  - `tests/memberships/test_list_service.py`, incluida la marca `slow`;
  - `tests/memberships/test_list_router.py`;
  - `tests/memberships/test_status_queries_service.py`;
  - `tests/memberships/test_summary_router.py`;
  - `tests/architecture/test_no_cross_schema_sql.py`.
- **S3-B8:**
  - `tests/payments/test_list.py`, `test_list_filters.py`, `test_list_performance.py` y `test_router_list.py`;
  - `tests/payments/test_get.py` y `test_router_get.py`;
  - `tests/payments/test_month_bounds.py`, `test_summary.py` y `test_router_summary.py`.
- **S3-B9:**
  - `tests/members/test_chip_to_filter.py`;
  - `tests/members/test_service_list_membership_filters.py` y `test_router_list_filters.py`;
  - `tests/members/test_service_get.py` y `test_router_get.py`.
- **S3-B10:**
  - `tests/members/test_service_reveal.py` y `test_router_reveal.py`;
  - `tests/members/test_member_patch_rules.py`, `test_service_update.py` y `test_router_update.py`;
  - `tests/members/test_service_deactivate.py` y `test_router_deactivate.py`;
  - `tests/architecture/test_no_physical_delete.py`.
- **S3-B11:**
  - `tests/memberships/test_member_memberships_service.py` y `test_member_memberships_router.py`;
  - `tests/payments/test_list_for_member.py` y `test_router_member_payments.py`.

### Wave 3b · Implementación de backend (`backend-implementor`)

El orden de los slices respeta las migraciones (`0008` → `0009` → `0010` → `0011`) y la ruta crítica US-084 → US-095 → US-096 → US-085 → US-086 → US-092.

- **Slice S3-B1 · Reglas puras y vender.** Historias: US-083 y US-084.
  - Funciones puras:
    - `compute_end_date`;
    - `compute_status(membership, today, expiring_days)` con la lista de congelaciones;
    - `covers`;
    - `next_start_for_renewal`;
    - `classify_open`.
  - **Migración `0008_memberships`:**
    - `EXCLUDE USING gist (member_id WITH =, daterange(start_date, end_date, '[]') WITH &&) WHERE (status <> 'cancelled')`;
    - CHECK de fechas, de clases y de cancelación;
    - índices `(status, end_date)` y `(member_id, status, start_date)`;
    - sin las columnas `frozen_*`.
  - `sell(..., max_retroactive_days)`: el router pasa el valor de Settings.
  - `get_payment_target` y `refs_for`.
  - Q4: `classes_remaining` existe, pero en v0.1 nada lo descuenta.
  - Gate: `slice-gate.sh memberships`, más el ciclo de Alembic.
- **Slice S3-B2 · Congelar.** Historia: US-089.
  - **Migración `0009_membership_freezes`:** una fila por congelación, CHECK `frozen_from <= frozen_to` y `EXCLUDE` por `membership_id`.
  - `apply_freeze` pura, que recibe los límites.
  - 409 `overlaps_future_membership`.
  - Gate: `slice-gate.sh memberships`, más el ciclo de Alembic.
- **Slice S3-B3 · Registrar pago y medios de pago.** Historias: US-095 y US-056.
  - **Migración `0010_payments`:**
    - `amount_cop` con CHECK mayor que 0;
    - `method` con CHECK `cash`, `nequi` o `breb`;
    - las cuatro columnas de anulación, con su CHECK;
    - `member_id NOT NULL`;
    - índices `paid_at`, `membership_id` y `(member_id, paid_at DESC)`.
  - `payments.service.register`:
    - hace `flush` antes de emitir `PaymentRegistered`;
    - expone `sum_not_voided`;
    - define el puerto `MembershipGate` (G-03).
  - Sección `payment_methods` en Settings y `GET /payments/methods`.
  - Gate: `slice-gate.sh payments && slice-gate.sh settings`, más el ciclo de Alembic.
- **Slice S3-B4 · Inmutabilidad, venta con primer pago y activación.** Historias: US-096, US-085 y US-086.
  - **Migración `0011_payments_immutability`:**
    - función `payments.forbid_mutation()`;
    - trigger `BEFORE UPDATE OR DELETE` que deja pasar solo la anulación, una vez y solo sobre las columnas de anulación;
    - trigger contra `TRUNCATE`.
  - `can_void`.
  - Memberships registra `membership_payability` en `set_membership_gate`.
  - `sell` con `first_payment` en la misma sesión.
  - Handler de `PaymentRegistered` que activa por cobertura (RN-03).
  - Gate: `slice-gate.sh payments && slice-gate.sh memberships`, más el ciclo de Alembic.
- **Slice S3-B5 · Anular pago y revertir la activación.** Historias: US-097 y US-087.
  - `void`, que traduce el error del trigger a 409.
  - `PaymentVoided` después del `flush`.
  - Handler que revierte a `pending_payment` y conserva las congelaciones (N-25).
  - Gate: `slice-gate.sh payments && slice-gate.sh memberships`.
- **Slice S3-B6 · Renovar y anular membresía.** Historias: US-088 y US-090.
  - `renew: true` ignora `start_date`.
  - `GET /members/{id}/memberships/renewal-preview`.
  - `cancel`, solo para admin, con motivo.
  - Gate: `slice-gate.sh memberships`.
- **Slice S3-B7 · Listar membresías y consultas de estado.** Historias: US-091 y US-092.
  - Lista paginada, y `GET /memberships/{id}` con `paid_cop` (lo usa la advertencia de Q5).
  - `summary()` por socio y estado resuelto.
  - `status_for(member_ids)`, `member_ids_by_status` y `count_active_by_plan` (G-04).
  - Gate: `slice-gate.sh memberships`.
- **Slice S3-B8 · Listas, detalle y resumen de pagos.** Historias: US-098, US-099 y US-100.
  - Lista con filtros y enriquecimiento por lote (`refs_for`, `names_for`).
  - Detalle.
  - `summary(month)` con los límites de mes de Bogotá.
  - Gate: `slice-gate.sh payments`.
- **Slice S3-B9 · Filtros de socios y ficha.** Historias: US-071 y US-073.
  - Filtro `membership_status` y `plan_id` por conjuntos de ids, sin JOIN (G-04).
  - Import perezoso members→memberships en la lista blanca (G-03).
  - La ficha descifra con propósito `mask` y no guarda nada en claro.
  - Gate: `slice-gate.sh members`.
- **Slice S3-B10 · Revelar, editar, dar de baja y reactivar.** Historias: US-074, US-075 y US-076.
  - `reveal`:
    - escribe la fila `reveal` con `audit.record` en la misma transacción (ciclo con US-107 resuelto);
    - llena `subject_member_id`;
    - deja la fila `decrypt` en `crypto_ops`.
  - Editar recifra y reindexa en el mismo flush. Solo el admin cambia el documento.
  - Baja lógica y `POST /members/{id}/reactivate`. La baja no anula membresías (N-20).
  - Gate: `slice-gate.sh members`.
- **Slice S3-B11 · Pestañas de la ficha.** Historias: US-093 y US-101 (backend).
  - `GET /members/{id}/memberships`.
  - `GET /members/{id}/payments`.
  - Gate: `slice-gate.sh memberships && slice-gate.sh payments`.

### Wave 5a · Tests de front en rojo (`frontend-qa-automation`)

- **S3-F1:**
  - `src/features/members/pages/MemberDetailPage.test.tsx`;
  - `src/shared/ui/MaskedValue.reveal.test.tsx`;
  - `src/features/members/pages/MemberFormPage.edit.test.tsx`;
  - `src/features/members`, para la baja.
- **S3-F2:**
  - `src/features/members/components`;
  - `src/features/members/components/MemberCardList.test.tsx`;
  - `tests/e2e/members-mobile.spec.ts`.
- **S3-F3:**
  - `src/features/memberships`, con la venta, el primer pago y la renovación;
  - `tests/e2e/sell-with-payment.spec.ts`.
- **S3-F4:**
  - `src/features/payments`;
  - `src/features/payments/components/VoidPaymentModal.test.tsx`;
  - `src/features/system`, para la pestaña de medios de pago.
- **S3-F5:** `src/features/memberships`, con la lista, congelar, anular y el resumen.
- **S3-F6:**
  - `src/features/payments/pages/PaymentsPage.test.tsx`;
  - `src/features/payments/components/PaymentDetailModal.test.tsx`;
  - `src/features/payments/components/MonthSummary.test.tsx`.
- **S3-F7:**
  - `src/features/memberships`, con la pestaña de la ficha;
  - `src/features/members/components/MemberPaymentsTab.test.tsx`.

### Wave 5b · Implementación de front (`frontend-ux-engineer`)

- **Slice S3-F1 · Ficha del socio.** Historias: US-073, US-074, US-075 y US-076 (front).
  - `Socio_Ficha` con pestañas y `MaskedValue` conectado a `reveal`.
  - Edición, en la que el documento es solo para admin.
  - Baja y reactivar, con el modo de solo lectura.
  - Gate: `slice-gate.sh web/features/members`.
- **Slice S3-F2 · Filtros de la lista y vista móvil.** Historias: US-071 y US-072.
  - Chips por estado, incluido "Pendiente de pago", anotado como `DESIGN-GAP`.
  - Selector de plan activo.
  - `Socios_Movil` en tarjetas.
  - Gate: `slice-gate.sh web/features/members`.
- **Slice S3-F3 · Vender, primer pago y renovar.** Historias: US-084, US-085 y US-088 (front).
  - `Membresia_Vender`, en `/membresias/vender?socio=:id&renovar=1`.
  - Resumen con `$ 120.000` y la fecha de fin.
  - El 409 enlaza a "Renovar".
  - Gate: `slice-gate.sh web/features/memberships`.
- **Slice S3-F4 · Registrar y anular pagos.** Historias: US-056, US-095 y US-097 (front).
  - Pestaña "Medios de pago" en `Config`.
  - `RegisterPaymentPanel`, con la advertencia de Q5.
  - `VoidPaymentModal`, solo para admin.
  - Gate: `slice-gate.sh web/features/payments && slice-gate.sh web/features/system`.
- **Slice S3-F5 · Pantalla de membresías.** Historias: US-089, US-090, US-091 y US-092 (front).
  - Lista `Membresias`, con los modales de congelar y anular.
  - `useMembershipSummary`.
  - Gate: `slice-gate.sh web/features/memberships`.
- **Slice S3-F6 · Pantalla de pagos.** Historias: US-098, US-099 y US-100 (front).
  - Lista `Pagos` con filtros.
  - Modal de detalle con el bloque de anulación.
  - Resumen del mes.
  - Gate: `slice-gate.sh web/features/payments`.
- **Slice S3-F7 · Pestañas Membresías y Pagos de la ficha.** Historias: US-093 y US-101 (front).
  - Botones Renovar, Congelar y Anular.
  - `RegisterPaymentPanel` con el socio preseleccionado.
  - Gate: `slice-gate.sh web/features/memberships && slice-gate.sh web/features/members`.

### Validación del sprint

- E2E contra el stack:
  - `tests/e2e/sell-with-payment.spec.ts`;
  - `tests/e2e/members-mobile.spec.ts`.
- Pruebas de rendimiento de las listas de pagos y de membresías (`-m slow`).
- Prueba manual en la base dev de la demo, con evidencia:
  - `EXCLUDE` rechazando un solapamiento;
  - trigger rechazando el `UPDATE`;
  - auditoría `insert`, `update` y `reveal`.

## Migraciones que aplica

- `0008_memberships` (US-084).
- `0009_membership_freezes` (US-089).
- `0010_payments` (US-095).
- `0011_payments_immutability` (US-096).

## Endpoints que expone

22 endpoints:

- **Members:**
  - admin y coach:
    - `GET /api/v1/members/{id}` y `PATCH /api/v1/members/{id}`;
    - `POST /api/v1/members/{id}/reveal`;
    - `GET /api/v1/members/{id}/memberships` y `POST /api/v1/members/{id}/memberships`, para vender, vender con primer pago y renovar;
    - `GET /api/v1/members/{id}/memberships/renewal-preview`;
    - `GET /api/v1/members/{id}/payments`;
  - solo admin: `DELETE /api/v1/members/{id}` y `POST /api/v1/members/{id}/reactivate`.
- **Memberships:**
  - admin y coach:
    - `GET /api/v1/memberships`, `GET /api/v1/memberships/summary` y `GET /api/v1/memberships/{id}`;
    - `POST /api/v1/memberships/{id}/freeze`;
    - `POST /api/v1/memberships/{id}/payments`;
  - solo admin: `POST /api/v1/memberships/{id}/cancel`.
- **Payments:**
  - admin y coach: `GET /api/v1/payments`, `GET /api/v1/payments/summary`, `GET /api/v1/payments/methods` y `GET /api/v1/payments/{id}`;
  - solo admin: `POST /api/v1/payments/{id}/void`.
- **Settings (admin):** `GET` y `PATCH /api/v1/settings/payment_methods`.

`GET /api/v1/members` ya existía. Este sprint le agrega los filtros `membership_status` y `plan_id`.

Las rutas fijas se registran antes que las de parámetro: `/payments/summary` y `/payments/methods` antes de `/payments/{id}`, y `/memberships/summary` antes de `/memberships/{id}`.

## Tests de arquitectura que deben pasar

- Los de los Sprints 0 a 2.
- `tests/architecture/test_banned_imports.py`, ampliada (US-083).
- `tests/architecture/test_no_cross_models.py`, ampliada (US-084).
- `tests/architecture/test_service_import_graph.py` (US-085). Es la consolidada: absorbe `test_service_import_cycles.py` (US-071 y US-073), `test_payments_does_not_import_memberships.py` (US-085 y US-095) y `test_payments_dependencies.py` (US-098). Comprueba tres cosas:
  - el grafo es acíclico a nivel de módulo;
  - los imports perezosos solo aparecen en la lista blanca de G-03;
  - cada service se importa en un subproceso limpio.
- `tests/architecture/test_gates_registered.py` (US-085).
- `tests/architecture/test_payment_method_codes.py` (US-056).
- `tests/architecture/test_payments_immutability_code.py` (US-096).
- `tests/architecture/test_no_cross_schema_sql.py` (US-091).
- `tests/architecture/test_no_physical_delete.py` (US-076).

## Riesgos y mitigación

1. [HIGH] Es el nudo de dependencias más denso de v0.1: el bus transaccional, el puerto G-03, el handler de cobertura y el trigger, en la misma iteración. Un error se propaga a renovar, congelar, al resumen, al tablero y al job de vencimientos.
   - Mitigación:
     - slices de 1 a 3 historias en orden estricto;
     - `test_service_import_graph.py` entra en S3-B4 y bloquea desde ahí;
     - después de cada slice se corre la suite completa de `memberships` y `payments`, no solo la del slice.
2. [HIGH] Un trigger de `0011` mal escrito bloquea anulaciones legítimas, o deja editar la caja. Corregirlo con pagos reales es migrar una regla que protege plata.
   - Mitigación: `tests/payments/test_immutability.py`, con una prueba por cada columna permitida, por cada columna prohibida, por la doble anulación, por `DELETE` y por `TRUNCATE`.
3. [HIGH] El `EXCLUDE USING gist` y la invariante de Q1 con la renovación anticipada.
   - Mitigación: pruebas de service con membresía vigente más futura, con congelada y extendida, y con cancelada (que no cuenta); inserción manual a modo de evidencia.
4. [MEDIUM] Carrera entre vender y dar de baja un plan.
   - Mitigación: `plans.service.get(for_share=True)` en `sell` desde S3-B1. US-082 cierra la otra mitad en el Sprint 4.
5. [MEDIUM] Es el sprint con más pantallas nuevas (7 slices de front).
   - Mitigación: la ficha (S3-F1) va antes que sus pestañas (S3-F7), y el E2E de venta con pago valida el camino completo.

## Definición de hecho del sprint

- Los 11 slices de backend y los 7 de front confirmados con `checkpoint-commit.sh`.
- `scripts/workflow/run-gates.sh` en verde, con cobertura del 80 % en `memberships`, `payments`, `members` y `settings`.
- `cd api && uv run pytest tests/architecture -q` en verde.
- Ciclo de Alembic sobre `0011`.
- `docs/openapi.json` y los tipos del front regenerados.
- E2E en verde: `tests/e2e/sell-with-payment.spec.ts` y `tests/e2e/members-mobile.spec.ts`.
- Smoke con evidencia SQL de la demo:
  - activación atómica;
  - reversión al anular;
  - `EXCLUDE`;
  - trigger;
  - filas `reveal` y `decrypt`.
- Seguridad, revisada por `security-reviewer`:
  - pagos sin `UPDATE` ni `DELETE` posibles por la API ni por SQL;
  - anular y cancelar solo para admin;
  - `reveal` siempre auditado, con usuario y campo;
  - ninguna lista devuelve campos cifrados ni enmascarados;
  - la ficha no guarda el valor descifrado;
  - montos en `int` COP sin decimales.
- `verify-delivery`, con una venta y una anulación reales hechas por la pantalla y verificadas en la base.
