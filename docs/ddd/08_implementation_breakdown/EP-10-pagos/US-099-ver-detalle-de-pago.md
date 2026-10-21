# US-099 · Ver detalle de pago — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-10-pagos/US-099-ver-detalle-de-pago.md`
- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context / módulo:** Payments (`api/src/app/modules/payments/`)
- **Versión:** v0.1
- **Puntos de la historia:** 1

## Estado de preparación

**READY**

Lectura simple de un pago con contrato, roles y códigos definidos. El enriquecimiento (socio, plan, nombres de quien registró y de quien anuló) reutiliza las mismas lecturas por lote de US-098, con la misma decisión de arquitectura.

## Resumen

Agrega `payments.service.get(id)` y `GET /payments/{id}` (admin y coach) con `PaymentDetail`, y el modal de detalle del front, sin acciones de edición ni borrado; la acción "Anular" (solo admin) la aporta US-097.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md.

## Validación contra el dominio

- Lectura del aggregate `Payment`. RN-01 (monto entero), RN-02 (el detalle no ofrece editar). Sin eventos ni funciones puras nuevas.

## Validación contra la arquitectura

- Módulo dueño: `payments`. El router llama a `payments.service.get`, que enriquece con `memberships.service.refs_for({membership_id})` y `auth.service.names_for({registered_by, voided_by})`, la misma composición de lectura acotada que se documenta en US-098 (no es brecha: sin escritura, por lote, vecinos publicados).
- Sin imports de `models` ajenos. Rol `require_role("admin", "coach")`. Sin datos cifrados en la respuesta.
- La ruta `/payments/{id}` se registra después de `/payments/summary` (US-100) para que `summary` no se interprete como id.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `async def get(session, payment_id: UUID) -> PaymentDetail` en `payments/service.py`: 404 `PaymentNotFound` si no existe; enriquecimiento por lote reutilizando el helper de US-098 (`_enrich(rows)`) — 1 h

### Schemas
- [ ] T2 · `PaymentDetail` = `PaymentRow` de US-098 más `voided_by`, `voided_by_name`, `voided_at`, `created_at` — 0,5 h

### Router
- [ ] T3 · `GET /payments/{id}` con `id: UUID` (422 si no es UUID), `Depends(require_role("admin", "coach"))`; códigos 200, 401, 403, 404, 422 — 0,5 h

### Tests unitarios puros
- No aplica (sin reglas puras nuevas).

### Tests de service con PostgreSQL
- [ ] T4 · `api/tests/payments/test_get.py`: pago vigente; pago anulado con `voided_by_name` resuelto; inexistente levanta 404 — 0,5 h

### Tests de router
- [ ] T5 · `api/tests/payments/test_router_get.py`: 200 coach y admin, 404, 422 con "no-es-uuid", 403 member, 401 sin token, `/payments/summary` no cae en esta ruta — 0,5 h

### Tests de arquitectura
- No aplica: siguen verdes `test_every_route_has_role.py` y `test_payments_dependencies.py` (US-098).

### Front
- [ ] T6 · `web/src/features/payments/api.ts`: `usePayment(id)`; `web/src/features/payments/components/PaymentDetailModal.tsx`: monto `$ 120.000`, medio con etiqueta, referencia, fecha en hora de Bogotá, socio, plan, registrado por; bloque de anulación (motivo, quién, cuándo) con `StatusTag` "Anulado" con texto; sin botones de editar ni borrar; carga y error; punto de montaje para la acción "Anular" de US-097 — 2 h
- [ ] T7 · `web/src/features/payments/components/PaymentDetailModal.test.tsx`: pago anulado muestra motivo y autor; no existe ningún botón de editar ni borrar — 0,5 h

### DevOps
- No aplica (el `openapi.json` se regenera con US-098 o US-100 en la misma iteración; si esta historia va sola, se regenera aquí sin costo adicional).

### Seguridad
- [ ] T8 · Revisión rápida: rol, UUID validado, ningún dato cifrado del socio en `PaymentDetail` — 0,5 h

## Orden de ejecución
1. T4 (service en rojo)
2. T1
3. T2
4. T5 (router en rojo)
5. T3
6. T6, T7
7. T8

## Dependencias técnicas
- US-098 · Listar y buscar pagos: helper de enriquecimiento y apertura del modal desde la fila.
- US-097 · Anular pago: acción "Anular" dentro del modal (solo admin).
- US-091 · `memberships.service.refs_for`; US-110 / US-041 · `auth.service.names_for`.

## Endpoints
- `GET /api/v1/payments/{id}` — roles: admin, coach

## Riesgos
- Orden de registro de rutas: `/payments/summary` capturado por `/payments/{id}` daría 422 — mitigación: prueba explícita en T5.
- Front condicionado a D1.

## Estimación
- Backend: 2 h (T1 a T3)
- Front: 2 h (T6)
- Pruebas: 1,5 h (T4, T5, T7)
- DevOps / seguridad: 0,5 h (T8)
- **Total: 6 h**
- Desvío leve sobre 1 punto (3 a 5 h) por el modal con bloque de anulación.

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/payments/test_get.py -q`
- [ ] `cd api && uv run pytest tests/payments/test_router_get.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/payments/components/PaymentDetailModal.test.tsx`
- [ ] `curl /api/v1/payments/no-es-uuid` devuelve 422 y `curl /api/v1/payments/<uuid-inexistente>` devuelve 404 con el envelope
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.payments --cov-fail-under=80`
