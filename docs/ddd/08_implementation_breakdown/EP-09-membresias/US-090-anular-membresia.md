# US-090 · Anular membresía — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-09-membresias/US-090-anular-membresia.md`
- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context / módulo:** Memberships (`api/src/app/modules/memberships/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Transición terminal con reglas cerradas por el dominio (`cancel(reason)` exige motivo, solo admin) y confirmadas por Q7. El CHECK que exige motivo y fecha en las canceladas ya entra en `0008_memberships` (US-084), así que no hay migración. Hay una diferencia de código HTTP con US-095 que se resuelve a favor de la historia dueña de esa regla (ver "Validación contra la arquitectura").

## Resumen

Caso de uso `memberships.service.cancel(id, reason, by)` y endpoint `POST /api/v1/memberships/{id}/cancel` (solo admin): deja la membresía `cancelled` con motivo, autor y hora UTC, no toca los pagos, la saca de Q1 (se puede volver a vender), deja auditoría y emite `MembershipCancelled`. En el front, acción "Anular" solo para admin con `ConfirmModal` y motivo obligatorio.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md (Q7: anular sigue siendo solo admin).

## Validación contra el dominio

- `02_domain_model.md` 2.3: `cancel(reason)` exige motivo no vacío; solo admin; `cancelled` es terminal (RN-06). El supuesto de la historia de un mínimo de 5 caracteres tras recortar se mantiene (es más estricto que "no vacío" y no contradice al dominio).
- Estados de origen permitidos: `pending_payment`, `active`, `expiring`, `frozen`, `expired`; desde `cancelled` → 409.
- RN-02 y RN-14: los pagos no se anulan ni se borran; las filas de `membership_freezes` tampoco.
- Q1: la `EXCLUDE` de `0008` ignora las canceladas (`WHERE status <> 'cancelled'`), así que una venta nueva en las mismas fechas es posible.
- Evento emitido: `MembershipCancelled(membership_id, member_id, reason)`.
- Sin discrepancias.

## Validación contra la arquitectura

- Módulo dueño: `memberships`. Sin llamadas a otros services.
- Efectos en otros módulos sin acoplarlos: el gate de US-085 (`membership_payability`) devuelve `cancelled = True` y Payments rechaza pagos nuevos; los handlers de US-086 y US-087 salen temprano por estado; el job de US-094 no selecciona `cancelled`.
- Diferencia entre historias: el criterio 6 de esta historia dice que un pago nuevo contra una cancelada devuelve 422; US-095 (criterio 6), que es la historia dueña de esa validación, dice 409 `membership_cancelled`. Se sigue US-095 y las pruebas de esta historia esperan 409.
- Rol: `require_role("admin")`; coach 403 (RN-15).
- Auditoría: `update` en `memberships` con `status` y `cancel_reason` antes y después (hook de US-016).
- Sin bus de criptografía, sin listas.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (el CHECK `status <> 'cancelled' OR (cancel_reason, cancelled_by, cancelled_at no nulos)` está en `0008_memberships`).

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `normalize_cancel_reason(reason: str | None) -> str` (recorta; lanza `CancelReasonInvalid` con `field = "reason"` si queda con menos de 5 caracteres) — 0.5 h
- [ ] T2 · `async def cancel(session, *, membership_id: UUID, reason: str, by: UUID, clock: Clock) -> MembershipView`: `FOR UPDATE`; 404 si no existe; `MembershipAlreadyCancelled` (409 `membership_already_cancelled`) si ya está cancelada; asigna `status = "cancelled"`, `cancel_reason`, `cancelled_by = by`, `cancelled_at = clock.now_utc()`; `emit(MembershipCancelled(...))`; dataclass pública `MembershipCancelled`; excepciones en `exceptions.py` — 2 h

### Schemas
- [ ] T3 · `CancelMembershipIn(reason: str)` con `extra="forbid"` (la regla de 5 caracteres vive en el service para que el error tenga el mismo envelope en API y CLI) — 0.5 h

### Router
- [ ] T4 · `POST /api/v1/memberships/{membership_id}/cancel` con `require_role("admin")`; 200 `MembershipOut`; 401, 403, 404, 409, 422 — 0.75 h

### Tests unitarios puros
- [ ] T5 · `test_rules.py::test_normalize_cancel_reason` (`None`, `""`, `"   "`, `"abcd"`, `"  Error de venta  "`) y `compute_status` de `cancelled` en cualquier fecha (ya en US-083, se reafirma) — 0.5 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/memberships/test_cancel_service.py`: anular desde cada estado de origen; pagos intactos (`SELECT` de `payments` sin cambios y sin auditoría de `payments`); segunda anulación → 409; motivo corto → 422 sin cambios; tras anular, `sell` al mismo socio con las mismas fechas → 201; registrar un pago contra la cancelada → 409 `membership_cancelled` (por el gate de US-085); un `PaymentVoided` posterior no la reactiva; auditoría `update` y `MembershipCancelled` una vez — 2.5 h

### Tests de router
- [ ] T7 · `api/tests/memberships/test_cancel_router.py`: 200 admin, 403 coach, 403 `member`, 401, 404, 409, 422 `field = "reason"` — 1 h

### Tests de arquitectura
- [ ] T8 · Confirmar `test_every_route_has_role.py` con la ruta nueva — 0.25 h

### Front
- [ ] T9 · `web/src/features/memberships/components/CancelModal.tsx` sobre `ConfirmModal`: campo de motivo obligatorio (Zod `cancelSchema`, mínimo 5 tras recortar), texto "Los pagos no se anulan automáticamente; anúlalos desde Pagos si corresponde"; acción "Anular" visible solo con `useCan("memberships.cancel")` (admin); `useCancelMembership` en `api.ts` que invalida `["memberships"]` y `["members", memberId]`; `StatusTag` "Cancelada" — 2.5 h
- [ ] T10 · Vitest `CancelModal.test.tsx`: botón oculto para coach, motivo vacío bloquea el envío, 409 muestra "Esta membresía ya estaba anulada" — 1 h

### DevOps
- [ ] T11 · Regenerar `docs/openapi.json` y `web/src/core/api/types.ts` — 0.25 h

### Seguridad
- [ ] T12 · Revisar: solo admin en la ruta (no basta con ocultar el botón); el motivo se guarda como texto sin interpretar y el front lo muestra escapado (sin `dangerouslySetInnerHTML`); el motivo no va al log — 0.25 h

## Orden de ejecución
1. T5 (rojo), T1
2. T6 (rojo), T2 (verde)
3. T3, T7 (rojo), T4 (verde)
4. T8, T11
5. T10 (rojo), T9 (verde)
6. T12

## Dependencias técnicas
- US-084 · Vender membresía: tabla, CHECK de cancelación y `MembershipOut`.
- US-085 · Gate `membership_payability` (pagos contra una cancelada).
- US-095 · Registrar pago: 409 `membership_cancelled`.
- US-065 · `ConfirmModal` (front). US-066 o equivalente · `useCan` (front).
- US-091 y US-093 · Alojan la acción "Anular".

## Endpoints
- `POST /api/v1/memberships/{id}/cancel` — roles: admin

## Riesgos
- Anular por error una membresía con pagos: no se puede deshacer (`cancelled` es terminal) — mitigación: el modal muestra plan, fechas y pagos antes de confirmar; la corrección es vender de nuevo.
- Diferencia de código (422 en esta historia, 409 en US-095) — mitigación: se sigue US-095; anotado para que el orquestador corrija el criterio 6 de esta historia.
- Front condicionado a D1.

## Estimación
- Backend: 3.75 h
- Front: 2.5 h
- Pruebas: 5.25 h
- DevOps / seguridad: 0.5 h
- **Total: 12 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/memberships/test_rules.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_cancel_service.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_cancel_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/memberships`
- [ ] Con token de coach, `curl -X POST /api/v1/memberships/<id>/cancel` responde 403; con token de admin responde 200 y `SELECT status, cancel_reason, cancelled_by FROM memberships.memberships WHERE id = '<id>'` trae `cancelled`, el motivo y el admin
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.memberships --cov-fail-under=80`
