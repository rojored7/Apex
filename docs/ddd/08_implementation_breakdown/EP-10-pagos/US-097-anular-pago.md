# US-097 · Anular pago — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-10-pagos/US-097-anular-pago.md`
- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context / módulo:** Payments (`api/src/app/modules/payments/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Endpoint, rol (solo admin), validación del motivo, evento `PaymentVoided` y transición permitida por el trigger de US-096 están definidos. La reversión de la membresía es de US-087 y reacciona al evento. El único supuesto (motivo de 500 caracteres como máximo) no cambia el esquema más allá del `CHECK` ya previsto en `0010_payments`.

## Resumen

Implementa `payments.service.void(id, reason, by)`: bloquea la fila con `SELECT ... FOR UPDATE`, verifica `can_void`, escribe las cuatro columnas de anulación en un solo `UPDATE` (la única transición que deja pasar el trigger) y emite `PaymentVoided(membership_id, payment_id)` en la misma transacción. Expone `POST /payments/{id}/void` solo para admin y agrega al front el `ConfirmModal` de anulación con motivo obligatorio, la etiqueta "Anulado" y la acción "Registrar pago nuevo" con datos precargados.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md. Se recuerda N-25: si el pago anulado cubría una membresía `frozen`, Memberships la pasa a `pending_payment` conservando sus congelaciones; eso lo resuelve US-087 en su handler (corrige el supuesto de US-087, no el de esta historia), y Payments no cambia nada por ello.

## Validación contra el dominio

- Aggregate `Payment`, columnas `voided`, `void_reason`, `voided_by`, `voided_at`.
- RN-02: se anula con motivo, una sola vez; la corrección es un pago nuevo (dos filas). RN-03: el pago anulado deja de sumar en `sum_not_voided`. RN-15: coach no anula.
- Función pura `can_void(payment)` (US-096) y nueva `normalize_void_reason(value) -> str` (recorta; vacío o más de 500 caracteres levanta `InvalidVoidReason`).
- Evento emitido: `PaymentVoided(membership_id, payment_id)` (declarado en US-095). Consumido por `memberships.service.on_payment_voided` (US-087). Eventos consumidos aquí: ninguno.

## Validación contra la arquitectura

- Módulo dueño: `payments`. Ninguna llamada de escritura a otro módulo: la reversión ocurre por evento (regla de módulos 3).
- Concurrencia: `SELECT ... FOR UPDATE` antes de `can_void`; si dos admins anulan a la vez, el segundo ve `voided = true` y recibe 409. Si aun así el trigger rechaza (por ejemplo, una escritura fuera del service), el service captura el error con prefijo `payments_immutable` y lo traduce a 409 `payment_already_voided`.
- Rol: `require_role("admin")`.
- Auditoría: el hook de US-016 deja la fila `update` con `before.voided = false` y `after.voided = true` y el usuario de la petición.
- Sin bus de criptografía ni primitivas.
- `voided_at` sale de `Clock.now()` (UTC).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (el `CHECK` de 500 caracteres y la coherencia de anulación están en `0010_payments`; el trigger en `0011_payments_immutability`).

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `normalize_void_reason(value: str) -> str` y constante `VOID_REASON_MAX = 500` en `payments/service.py`; excepciones `PaymentNotFound` (404), `PaymentAlreadyVoided` (409 `payment_already_voided`), `InvalidVoidReason` (422 `field="reason"`) en `payments/exceptions.py` — 1 h
- [ ] T2 · Caso de uso `async def void(session: AsyncSession, *, payment_id: UUID, reason: str, by: UUID) -> Payment`: `select(Payment).where(Payment.id == payment_id).with_for_update()`; 404 si no existe; `if not can_void(p): raise PaymentAlreadyVoided`; asigna las cuatro columnas (`voided=True`, `void_reason`, `voided_by=by`, `voided_at=clock.now()`); `flush`; captura `DBAPIError` con prefijo `payments_immutable` y la traduce a `PaymentAlreadyVoided`; `await events.emit(PaymentVoided(membership_id=p.membership_id, payment_id=p.id), session)`; devuelve el pago — 2 h

### Schemas
- [ ] T3 · `VoidPaymentIn { reason: str }` con validador que recorta y exige de 1 a 500 caracteres; la respuesta reutiliza `PaymentOut` de US-095 — 0,5 h

### Router
- [ ] T4 · `POST /payments/{id}/void` en `payments/router.py` con `Depends(require_role("admin"))`, 200 `PaymentOut`; códigos 200, 401, 403, 404, 409, 422 — 0,5 h

### Tests unitarios puros
- [ ] T5 · `api/tests/payments/test_void_rules.py`: `normalize_void_reason` con "  Monto mal digitado  ", "", "   ", 500 y 501 caracteres — 0,5 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/payments/test_void.py`: anulación feliz (cuatro columnas, monto, medio, referencia y `paid_at` intactos); doble anulación 409 sin cambios; pago inexistente; `PaymentVoided` emitido una vez con `membership_id` y `payment_id`; handler que falla revierte la anulación (la fila sigue `voided = false`); anular y registrar uno nuevo deja dos filas y `sum_not_voided` solo suma el nuevo; fila de auditoría `update` con `before.voided = false`, `after.voided = true` y el usuario; dos sesiones concurrentes que anulan el mismo pago: una 200 y otra 409 — 3 h

### Tests de router
- [ ] T7 · `api/tests/payments/test_router_void.py`: 200 admin; 403 coach; 403 member; 401 sin token; 422 `field="reason"` para ausente, vacío, espacios y 501 caracteres; 404; 409 con envelope — 1,5 h

### Tests de arquitectura
- [ ] T8 · `test_every_route_has_role.py` cubre la ruta nueva con rol admin; `test_no_cross_models.py` sigue verde (la anulación no toca `memberships`) — 0,5 h

### Front
- [ ] T9 · `web/src/features/payments/api.ts`: `useVoidPayment()` que invalida `payments`, `payments-summary`, `memberships` y `members`; `web/src/features/payments/schemas.ts`: Zod del motivo (1 a 500 tras recortar) — 1 h
- [ ] T10 · `web/src/features/payments/components/VoidPaymentModal.tsx`: `ConfirmModal` con `Field` de motivo obligatorio y el texto "El pago no se borra: queda anulado con este motivo"; manejo del 409 ("otra persona lo anuló antes") refrescando el pago; acción "Anular" en el detalle y en la fila visible solo con `useCan("payments.void")` (admin); tras anular, botón "Registrar pago nuevo" que abre `RegisterPaymentPanel` (US-095) con socio, membresía, monto y medio precargados — 2 h
- [ ] T11 · `web/src/features/payments/components/VoidPaymentModal.test.tsx`: botón oculto para coach, motivo obligatorio, 409 mostrado, precarga del pago nuevo — 1,5 h

### DevOps
- [ ] T12 · Regenerar `docs/openapi.json` y tipos del front — 0,5 h

### Seguridad
- [ ] T13 · Revisión: solo admin en servidor (el ocultamiento en front es cosmético), el motivo no se escribe en logs, IDOR no aplica (admin ve toda la caja), el error de la base no se filtra al cliente (solo el código `payment_already_voided`) — 0,5 h

## Orden de ejecución
1. T5 (pura en rojo)
2. T1
3. T6 (service en rojo)
4. T2
5. T3
6. T7 (router en rojo)
7. T4
8. T8
9. T9, T10, T11
10. T12
11. T13

## Dependencias técnicas
- US-096 · Inmutabilidad de pagos en la base: transición permitida y `can_void`.
- US-095 · Registrar pago: modelo, `PaymentOut`, `PaymentVoided` declarado, panel para el pago nuevo.
- US-087 · Revertir activación al anular pago: consume `PaymentVoided` (misma iteración; sin él la anulación funciona pero la membresía no se revierte).
- US-014 · Bus de eventos transaccional.
- US-034 · `require_role`.
- US-065 · Panel lateral y modal de confirmación (front).
- US-053 · Guardas de ruta por rol (`useCan` en el front).

## Endpoints
- `POST /api/v1/payments/{id}/void` — roles: admin

## Riesgos
- El `UPDATE` que arma SQLAlchemy incluye solo las columnas modificadas más `updated_at`; si el mixin tocara otra columna (por ejemplo `created_by`), el trigger rechazaría toda anulación — mitigación: la prueba feliz de T6 corre contra el trigger real de `0011`.
- Traducir errores de base por prefijo de mensaje es frágil — mitigación: constante compartida `IMMUTABLE_ERROR_PREFIX` y prueba específica en T6.
- Front condicionado a D1.

## Estimación
- Backend: 4 h (T1 a T4)
- Front: 3 h (T9, T10)
- Pruebas: 7 h (T5 a T8 y T11)
- DevOps / seguridad: 1 h (T12, T13)
- **Total: 15 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/payments/test_void_rules.py -q`
- [ ] `cd api && uv run pytest tests/payments/test_void.py -q`
- [ ] `cd api && uv run pytest tests/payments/test_router_void.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/payments/components/VoidPaymentModal.test.tsx`
- [ ] `curl -X POST /api/v1/payments/<id>/void -d '{"reason":"Se registró dos veces"}'` con token de coach devuelve 403 y con token de admin 200; una segunda llamada devuelve 409 `payment_already_voided`
- [ ] `SELECT voided, void_reason, voided_by, voided_at, amount_cop FROM payments.payments WHERE id = '<id>'` muestra la anulación y el monto original
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.payments --cov-fail-under=80`
