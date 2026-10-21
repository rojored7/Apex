# US-087 · Revertir activación al anular un pago — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-09-membresias/US-087-revertir-activacion-al-anular-pago.md`
- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context / módulo:** Memberships (`api/src/app/modules/memberships/service.py`, handler del evento `PaymentVoided` de Payments)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

La pregunta abierta de la historia (si una `frozen` también vuelve a `pending_payment`) la resolvió DECISIONES N-25: sí, y conserva sus congelaciones. El resto es simétrico a US-086 y usa el mismo contrato `payments.service.sum_not_voided`. La dependencia hacia `payments.service` es la permitida por el cierre de la brecha de US-085.

## Resumen

Handler `memberships.service.on_payment_voided`, suscrito al importar el módulo: en la transacción de la anulación bloquea la membresía, recalcula el total no anulado y, si la membresía estaba `active`, `expiring` o `frozen` y ya no está cubierta, la pasa a `pending_payment` (sin tocar sus filas de `membership_freezes`), deja auditoría y emite `MembershipActivationReverted`. Sin endpoint ni front propios.

## Correcciones aplicadas por DECISIONES.md

- Criterio 4 y supuesto de la historia ("`frozen` no cambia al anular") → una membresía `frozen` que deja de estar cubierta pasa a `pending_payment` y conserva sus congelaciones; al volver a cubrirse, `compute_status` la devuelve a `frozen` si la ventana sigue conteniendo hoy: corregido por DECISIONES N-25.
- `expired` y `cancelled` siguen sin cambiar (la historia lo dice y N-25 solo corrige `frozen`).
- La cobertura se calcula con `payments.service.sum_not_voided` (contrato de consolidación), igual que en US-086.

## Validación contra el dominio

- `02_domain_model.md` 2.4: si al anular la cobertura cae por debajo del precio y la membresía estaba activa, vuelve a `pending_payment` y se emite `MembershipActivationReverted`. "Activa" incluye `expiring` (es un `active` cercano al fin) y, por N-25, `frozen`.
- RN-02: el pago no se borra; solo cambian sus columnas de anulación (US-097).
- RN-03: los pagos anulados no suman.
- Entidad interna `MembershipFreeze` (N-25): sus filas no se tocan; la extensión de `end_date` ya aplicada se conserva.
- Evento consumido: `PaymentVoided(membership_id, payment_id)`. Evento emitido: `MembershipActivationReverted(membership_id, member_id, previous_status)`.
- Sin discrepancias tras N-25.

## Validación contra la arquitectura

- Módulo dueño: `memberships`; Payments solo emite (mapa de contextos 5).
- Llamada de lectura `payments.service.sum_not_voided`; nunca `payments.models`.
- Suscripción `subscribe(PaymentVoided, on_payment_voided)`; corre en la misma transacción de `payments.service.void`: un fallo revierte la anulación (criterio 5).
- Auditoría por el hook con `current_actor` = el admin que anuló (criterio 6). El rol lo impone el endpoint de US-097 (solo admin).
- Sin bus de criptografía, sin paginación.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `async def on_payment_voided(event: PaymentVoided, session: AsyncSession) -> None`: `row = await session.get(Membership, event.membership_id, with_for_update=True)`; si no existe o `row.status not in {"active", "expiring", "frozen"}`, retorna; `paid = await payments_service.sum_not_voided(session, row.id)`; si `covers(row.agreed_price_cop, paid)`, retorna; guarda `previous = row.status`, asigna `row.status = "pending_payment"` y `emit(MembershipActivationReverted(row.id, row.member_id, previous), session)`; no toca `end_date` ni `membership_freezes` — 1.5 h
- [ ] T2 · Función pura `should_revert(status: MembershipStatus, agreed_price_cop: int, paid_cop: int) -> bool` (la usa T1), dataclass pública `MembershipActivationReverted` y `subscribe(PaymentVoided, on_payment_voided)` — 0.5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T3 · `api/tests/memberships/test_rules.py::test_should_revert` parametrizado: `active`, `expiring` y `frozen` sin cobertura → `True`; con cobertura → `False`; `pending_payment`, `expired`, `cancelled` → `False` — 0.5 h

### Tests de service con PostgreSQL
- [ ] T4 · `api/tests/memberships/test_revert_activation_service.py` por el bus real (anulando con `payments.service.void`): único pago de 120.000 anulado → `pending_payment` y un `MembershipActivationReverted`; pagos de 120.000 y 20.000, se anula el de 20.000 → sigue `active` sin eventos; `expiring` → `pending_payment`; `frozen` → `pending_payment` con su fila de `membership_freezes` y su `end_date` intactos, y un pago nuevo que cubre la devuelve a `frozen` (cuando exista US-089); `expired` y `cancelled` sin cambio; handler que lanza → el pago sigue sin anular; fila de auditoría `update` con el admin — 3 h

### Tests de router
- No aplica (el 200 de la anulación lo cubre US-097).

### Tests de arquitectura
- [ ] T5 · Confirmar verdes `test_payments_does_not_import_memberships.py` y `test_service_import_graph.py` — 0.25 h

### Front
- No aplica (US-097 invalida `["memberships"]` y `["members"]` al anular).

### DevOps
- No aplica.

### Seguridad
- [ ] T6 · Revisar que una anulación hecha por un coach es imposible por ruta (403 en US-097) y que el handler no permite reactivar una `cancelled` — 0.25 h

## Orden de ejecución
1. T3 (rojo), T2
2. T4 (rojo), T1 (verde)
3. T5
4. T6

## Dependencias técnicas
- US-086 · Activar por cobertura: patrón del handler, `snapshot`, `covers`.
- US-097 · Anular pago: emite `PaymentVoided` tras escribir las columnas de anulación y hacer `flush`.
- US-095 · `payments.service.sum_not_voided`.
- US-085 · Cierre de la brecha del ciclo de imports.
- US-089 · Congelaciones (para el caso `frozen` de T4).

## Endpoints
- Ninguno.

## Riesgos
- Una `frozen` revertida a `pending_payment` deja de verse "Congelada" en las listas aunque la ventana siga vigente (es la regla de N-25) — mitigación: la ficha (US-093) muestra las congelaciones de la membresía aunque el estado sea pendiente.
- Concurrencia entre una anulación y un pago nuevo sobre la misma membresía — mitigación: ambos handlers bloquean la fila con `FOR UPDATE`.

## Estimación
- Backend: 2 h
- Front: 0 h
- Pruebas: 3.75 h
- DevOps / seguridad: 0.25 h
- **Total: 6 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/memberships/test_rules.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_revert_activation_service.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Anular por `curl -X POST /api/v1/payments/<id>/void` el único pago de una membresía activa y comprobar `SELECT status FROM memberships.memberships WHERE id = '<id>'` = `pending_payment`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.memberships --cov-fail-under=80`
