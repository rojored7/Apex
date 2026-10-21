# US-086 · Activar por cobertura de pagos — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-09-membresias/US-086-activar-por-cobertura-de-pagos.md`
- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context / módulo:** Memberships (`api/src/app/modules/memberships/service.py`, handler del evento `PaymentRegistered` de Payments)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

La regla (RN-03), el estado resultante (`compute_status` con `expiring_days` y congelaciones, Q11 y N-25) y el contrato de lectura (`payments.service.sum_not_voided`, agregado en consolidación) están resueltos. La dependencia `memberships.service` → `payments.service` que crea este handler es la dirección permitida por la propuesta de cierre de la brecha de US-085 (inyección del validador); el criterio 8 de esta historia es justamente lo que esa propuesta garantiza. Se lista como dependencia, no bloquea el diseño.

## Resumen

Handler `memberships.service.on_payment_registered`, suscrito al importar el módulo, que dentro de la transacción del pago bloquea la membresía, pide a Payments el total no anulado, y si una membresía `pending_payment` queda cubierta la pasa al estado que dé `compute_status` sobre una base activa, deja auditoría y emite `MembershipActivated`. Sin endpoint ni front propios.

## Correcciones aplicadas por DECISIONES.md

- La historia pide `payments.service.list_for_membership(membership_id)` (o `sum_not_voided`) → se usa `payments.service.sum_not_voided(session, membership_id) -> int`, el contrato fijado al consolidar (README, "Contratos entre services"); `is_covered` se evalúa con `covers(agreed_price_cop, paid_cop)` de US-083.
- `compute_status` recibe además la lista de congelaciones de la membresía: una membresía con congelación que contiene "hoy" queda `frozen` al cubrirse: corregido por DECISIONES N-25.
- "Hoy" del handler: `to_bogota_date(event.occurred_at)` (el `occurred_at` UTC lo pone el `Clock` al crear el evento, US-014), que es la fecha de Bogotá de Q28 sin que el handler lea el reloj por su cuenta.

## Validación contra el dominio

- RN-03: activa si la suma de pagos no anulados es `>=` `agreed_price_cop`; Q5: el excedente no cambia nada más.
- Reacción descrita en `02_domain_model.md` 2.4 y mapa de contextos 5: Payments nunca cambia el estado; Memberships reacciona al evento.
- Transición: solo desde `pending_payment`. Sobre `active`, `expiring` o `frozen` no hace nada (criterio 4); sobre `cancelled` tampoco (US-090, criterio 5); `expired` no es posible como origen porque `pending_payment` no cambia por fecha.
- Evento consumido: `PaymentRegistered(membership_id, amount_cop)`; evento emitido: `MembershipActivated(membership_id, member_id, status)` una sola vez por transición.
- Funciones puras: `covers`, `compute_status`.
- Sin discrepancias.

## Validación contra la arquitectura

- Módulo dueño del cambio: `memberships`. Payments solo emite.
- Llamadas service a service: `payments.service.sum_not_voided` (lectura) y `settings.service.memberships_policy()` (lectura). Nunca `payments.models` (US-022).
- Suscripción `core.events.subscribe(PaymentRegistered, on_payment_registered)` al importar `memberships/service.py`; el handler recibe `(event, session)` y corre en la misma transacción (US-014): un fallo revierte el pago (criterio 6).
- Grafo de imports: `memberships.service` importa `payments.service`; `payments` no importa nada de `memberships` (criterio 8; propuesta de US-085, verificada por `test_payments_does_not_import_memberships.py`).
- Auditoría: la actualización de `status` pasa por el hook `after_flush` (US-016) con `current_actor` = quien registró el pago.
- Sin bus de criptografía, sin rol propio (lo cubre el endpoint que registra el pago, US-095 y US-085), sin paginación.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `async def on_payment_registered(event: PaymentRegistered, session: AsyncSession) -> None`: `row = await session.get(Membership, event.membership_id, with_for_update=True)`; si no existe o `row.status != "pending_payment"`, retorna; `paid = await payments_service.sum_not_voided(session, row.id)`; si `not covers(row.agreed_price_cop, paid)`, retorna; lee `memberships_policy()` y las congelaciones propias (`_load_freezes(session, row.id)`, lista vacía hasta US-089); `new = compute_status(replace(snapshot(row), status=ACTIVE), to_bogota_date(event.occurred_at), policy.expiring_days, freezes)`; asigna `row.status = new`; `emit(MembershipActivated(...), session)` — 2.5 h
- [ ] T2 · Dataclass pública `MembershipActivated(membership_id, member_id, status)` en `memberships/service.py`, helper `snapshot(row) -> MembershipSnapshot` y registro `subscribe(PaymentRegistered, on_payment_registered)` al final del módulo — 0.5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T3 · `api/tests/memberships/test_rules.py`: `compute_status` sobre base activa con fecha cercana al fin (2026-10-27 con fin 2026-10-31 → `expiring`), con congelación que contiene hoy (→ `frozen`) y futura (`start_date > hoy` → `active`) — 0.5 h

### Tests de service con PostgreSQL
- [ ] T4 · `api/tests/memberships/test_activation_service.py` por el bus real (registrando el pago con `payments.service.register`): 60.000 + 60.000 sobre 120.000 → `active` y un solo `MembershipActivated`; mismo caso el 2026-10-27 → `expiring`; 20.000 → sigue `pending_payment` sin eventos; pago anulado no suma; pago sobre `active`, `expiring` y `frozen` no emite; pago sobre `cancelled` lo rechaza Payments antes; handler que lanza (doble de `settings.service.memberships_policy` que falla) → ni pago ni cambio de estado; fila de auditoría `update` con `before.status = pending_payment`, `after.status = active` y el `user_id` de quien registró — 3.5 h
- [ ] T5 · Prueba de concurrencia: dos transacciones registran 60.000 cada una sobre la misma membresía de 120.000; con el `FOR UPDATE` la segunda ve el pago de la primera y la membresía termina `active` — 2 h

### Tests de router
- No aplica (sin endpoint propio; el 201 con estado activo lo cubren US-085 y US-095).

### Tests de arquitectura
- [ ] T6 · Confirmar verdes `test_payments_does_not_import_memberships.py`, `test_service_import_graph.py` (de US-085) y `test_no_cross_models.py` (US-022) — 0.5 h

### Front
- No aplica (el front de US-095 y US-085 invalida `["memberships"]` y `["members"]` al registrar el pago).

### DevOps
- No aplica.

### Seguridad
- [ ] T7 · Revisar que el handler no confía en `event.amount_cop` para decidir (recalcula el total desde Payments) y que no escribe en `payments` — 0.5 h

## Orden de ejecución
1. T3 (rojo), T2
2. T4 (rojo), T1 (verde)
3. T5
4. T6
5. T7

## Dependencias técnicas
- US-083 · Reglas puras: `covers`, `compute_status`, `MembershipSnapshot`.
- US-084 · Vender membresía: tabla y modelo.
- US-085 · Cierre de la brecha del ciclo de imports (inyección del validador): sin él, este import de `payments.service` crea el ciclo.
- US-095 · Registrar pago: emite `PaymentRegistered` tras hacer `flush` del pago (para que `sum_not_voided` lo incluya) y expone `payments.service.sum_not_voided(session, membership_id) -> int`.
- US-014 · Bus de eventos: `subscribe`, `emit`, `occurred_at` del `Clock`.
- US-013 · `to_bogota_date`.
- US-058 · `memberships_policy()`.
- US-089 · Congelaciones (`_load_freezes` devuelve filas reales cuando exista la tabla; antes, lista vacía).

## Endpoints
- Ninguno.

## Riesgos
- Lecturas concurrentes de la cobertura en `READ COMMITTED` podrían dejar `pending_payment` una membresía ya cubierta — mitigación: `FOR UPDATE` sobre la membresía antes de sumar (T5 lo prueba).
- Si US-095 emite el evento antes del `flush`, el total no incluye el pago nuevo y no activa nunca — mitigación: prueba de T4 con el `register` real; anotado en la dependencia.
- Una `pending_payment` cuyo `end_date` ya pasó se cubre y queda `expired` directamente (y se emite `MembershipActivated` con `status = expired`) — mitigación: el campo `status` del evento permite a los suscriptores (avisos, v0.2) ignorarlo; comportamiento documentado aquí.

## Estimación
- Backend: 3 h
- Front: 0 h
- Pruebas: 6.5 h
- DevOps / seguridad: 0.5 h
- **Total: 10 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/memberships/test_rules.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_activation_service.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Registrar dos pagos parciales por `curl -X POST /api/v1/memberships/<id>/payments` y comprobar `SELECT status FROM memberships.memberships WHERE id = '<id>'` = `active` y una sola fila `update` en `audit.audit_log` para ese `record_id`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.memberships --cov-fail-under=80`
