# US-101 · Pestaña Pagos de la ficha — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-10-pagos/US-101-pestana-pagos-de-la-ficha.md`
- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context / módulo:** Payments (`api/src/app/modules/payments/`), consumido desde la ficha de Members (`web/src/features/members/`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Contrato, paginación, inclusión de anulados, roles y comportamiento con socios dados de baja están definidos (DECISIONES N-20 confirma que el socio dado de baja se ve en modo solo lectura). La consulta reutiliza `payments.service.list` de US-098 con el filtro `member_id`. Se fija dónde vive la ruta para no crear una dependencia de Members hacia Payments.

## Resumen

Expone `GET /members/{id}/payments` (admin y coach), que comprueba que el socio exista (también si está dado de baja) y devuelve `Page[PaymentRow]` filtrado por `member_id`, orden `paid_at` descendente, con anulados por defecto y `voided=false` para ocultarlos. En el front, la pestaña Pagos de `Socio_Ficha` con `DataTable` paginada y el botón "Registrar pago" que abre el panel de US-095 con el socio preseleccionado.

## Correcciones aplicadas por DECISIONES.md

- Socio dado de baja: la historia devuelve sus pagos (criterio 3), coherente con DECISIONES N-20 (admin y coach ven socios dados de baja en solo lectura). En la pestaña de un socio dado de baja el botón "Registrar pago" no se muestra, porque la ficha está en solo lectura por N-20; el backend no cambia (un pago se registra contra una membresía y lo valida US-095).
- Ubicación de la ruta (ajuste de implementación, no de alcance): la historia nombra `members/router.py`; la ruta se declara en `payments/router.py` con el mismo path `/members/{id}/payments`. Así `members` no importa `payments` (la dependencia ya existente va de Payments hacia Members por `search_ids`) y el router llama a un solo service.

## Validación contra el dominio

- Lectura del aggregate `Payment` filtrada por socio. RN-01, RN-02 (sin edición), regla de datos 6 (paginación).
- El filtro usa la columna `payments.member_id` (copia inmutable agregada en US-095), así que no hace falta pedir a Memberships la lista de membresías del socio.
- Eventos: ninguno. Funciones puras: ninguna nueva.

## Validación contra la arquitectura

- Módulo dueño: `payments`. `payments.service.list_for_member(session, member_id, voided, page)` llama a `members.service.ensure_exists(session, member_id, include_deleted=True)` (404 si no existe) y luego a `list(PaymentFilters(member_id=..., voided=...), page)` de US-098.
- `members.service.ensure_exists` es un contrato de lectura nuevo y mínimo de Members (equivale a `get` sin descifrar nada); se informa como contrato entre épicas. Si Members prefiere exponer solo `get`, se usa `get` y se descarta el resultado, a costa de descifrar el enmascarado (N-01) sin necesidad.
- Sin imports de `models` ajenos (US-022). Rol `require_role("admin", "coach")`. Paginación común de US-019.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (índice `(member_id, paid_at DESC)` en `0010_payments`).

### Models
- No aplica.

### Service
- [ ] T1 · `async def list_for_member(session, member_id: UUID, voided: bool | None, page: PageParams) -> Page[PaymentRow]` en `payments/service.py` sobre `list` de US-098 — 1 h

### Schemas
- [ ] T2 · Query `MemberPaymentsQuery { voided: bool | None }` más `PageParams`; respuesta `Page[PaymentRow]` (US-098) — 0,5 h

### Router
- [ ] T3 · `GET /members/{id}/payments` en `payments/router.py` (router con prefijo vacío y tag `payments`), `Depends(require_role("admin", "coach"))`; códigos 200, 401, 403, 404, 422 — 0,5 h

### Tests unitarios puros
- No aplica.

### Tests de service con PostgreSQL
- [ ] T4 · `api/tests/payments/test_list_for_member.py`: socia con 3 pagos en dos membresías (uno anulado) devuelve 3 en orden descendente; `voided=false` devuelve 2; socio dado de baja devuelve sus pagos; socio inexistente levanta 404 — 1,5 h

### Tests de router
- [ ] T5 · `api/tests/payments/test_router_member_payments.py`: 200 coach y admin, 404 socio inexistente, 422 con `limit=0` y `limit=201`, 403 member, 401 sin token — 1 h

### Tests de arquitectura
- [ ] T6 · `test_no_cross_models.py` (US-022) verde y verificación de que `app.modules.members` no importa nada de `app.modules.payments` (se agrega a `test_payments_dependencies.py` de US-098) — 0,5 h

### Front
- [ ] T7 · `web/src/features/payments/api.ts`: `useMemberPayments(memberId, { voided, limit, offset })`; `web/src/features/members/components/MemberPaymentsTab.tsx`: `DataTable` paginada (fecha en hora de Bogotá, plan, monto `$ 120.000`, medio, referencia, `StatusTag` "Anulado" con motivo), conmutador "Ocultar anulados", estados de carga, vacío "Este socio no tiene pagos" y error; botón "Registrar pago" que abre `RegisterPaymentPanel` con `memberId` (US-095), oculto si el socio está dado de baja; acción "Anular" solo admin (US-097); montada en la pestaña Pagos de la ficha (US-073) — 2 h
- [ ] T8 · `web/src/features/members/components/MemberPaymentsTab.test.tsx`: orden, etiqueta "Anulado", panel con socio preseleccionado, sin botón de registrar para socio dado de baja — 1 h

### DevOps
- [ ] T9 · Regenerar `docs/openapi.json` y tipos del front — 0,5 h

### Seguridad
- [ ] T10 · Revisión: rol, ninguna fila trae datos cifrados del socio, el 404 no revela si el id pertenece a otro tipo de registro — 0,5 h

## Orden de ejecución
1. T4 (service en rojo)
2. T1
3. T2
4. T5 (router en rojo)
5. T3
6. T6
7. T7, T8
8. T9
9. T10

## Dependencias técnicas
- US-098 · Listar y buscar pagos: `list`, `PaymentRow`, enriquecimiento.
- US-095 · Registrar pago: columna `member_id` y `RegisterPaymentPanel` con preselección.
- US-073 · Ver ficha del socio: contenedor de pestañas.
- US-069 · Registrar socio: `members.service.ensure_exists` (o `get`).
- US-097 · Anular pago: acción "Anular" en la fila.

## Endpoints
- `GET /api/v1/members/{id}/payments` — roles: admin, coach

## Riesgos
- Si el orquestador rechaza `payments.member_id`, el filtro debe pedir a `memberships.service` los ids de membresía del socio — mitigación: el cambio queda encapsulado en `list_for_member`; el contrato HTTP no cambia.
- Front condicionado a D1.

## Estimación
- Backend: 2 h (T1 a T3)
- Front: 2 h (T7)
- Pruebas: 4 h (T4 a T6 y T8)
- DevOps / seguridad: 1 h (T9, T10)
- **Total: 9 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/payments/test_list_for_member.py -q`
- [ ] `cd api && uv run pytest tests/payments/test_router_member_payments.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/members/components/MemberPaymentsTab.test.tsx`
- [ ] `curl "/api/v1/members/<id>/payments?voided=false"` devuelve solo pagos vigentes del socio; con un id inexistente devuelve 404
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.payments --cov-fail-under=80`
