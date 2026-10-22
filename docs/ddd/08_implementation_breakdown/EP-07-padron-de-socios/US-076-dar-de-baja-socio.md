# US-076 · Dar de baja socio — desglose técnico

> **Corregido en S3-W0-1** (`docs/ddd/blueprints/sprint-03-plan.md`, sección 1; registro en `docs/ddd/DECISIONES.md`, "Sprint 3"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - Acción de permiso: `members.delete`, no `member.deactivate` (S3-C8).
> - `deactivate` y `reactivate` toman `core/locks.lock_member` (S3-D54); el evento se llama `MemberDeactivated` (S3-D70).
> - `test_no_physical_delete.py` reemplaza a `test_no_physical_delete_users.py` (D21).

- **Historia:** `docs/ddd/07_user_stories/EP-07-padron-de-socios/US-076-dar-de-baja-socio.md`
- **Épica:** EP-07 · Padrón de socios
- **Bounded context / módulo:** Members (`api/src/app/modules/members/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

N-20 cierra los dos supuestos de la historia: la baja no anula membresías y sí existe `POST /members/{id}/reactivate` (admin) desde v0.1. La baja lógica, el rol y la liberación del documento ya estaban definidos. No queda nada que cambie contrato o esquema.

## Resumen

- `DELETE /api/v1/members/{id}` (solo admin) fija `deleted_at` (UTC) y `status = "inactive"`; la fila se conserva; responde 204.
- `POST /api/v1/members/{id}/reactivate` (solo admin) limpia `deleted_at` y vuelve a `status = "active"`; si el documento ya lo tomó otro socio vivo, responde 409 con `existing_id`.
- Las membresías, los pagos y la auditoría del socio no se tocan.
- Tras la baja, el documento queda libre para un socio nuevo (índice único parcial).
- Front: acción "Dar de baja" con `ConfirmModal` (solo admin) y acción "Reactivar" en la ficha de solo lectura (solo admin).

## Correcciones aplicadas por DECISIONES.md

- El supuesto "no hay acción de reactivar en v0.1; se registra de nuevo" → existe `POST /api/v1/members/{id}/reactivate`, solo admin, desde v0.1: corregido por DECISIONES N-20.
- El supuesto "la baja no cancela las membresías vigentes" → confirmado tal cual (la baja no anula membresías; si hace falta, el admin cancela aparte con US-090): aceptado en DECISIONES N-20.
- El criterio 4 dice que el dado de baja "aparece con `status=deleted` para admin" → aparece para admin y coach, y su ficha se ve en solo lectura (US-070, US-073): corregido por DECISIONES N-20.

## Validación contra el dominio

- Aggregate `Member`; RN-14 (borrado lógico, nunca físico); RN-15 (solo admin borra); RN-02 (los pagos no cambian).
- Invariante de documento único entre vivos: al dar de baja se libera; al reactivar se vuelve a exigir.
- Eventos: `MemberDeactivated(member_id)` al dar de baja (catálogo de eventos). Reactivar no tiene evento propio en el catálogo; se emite `MemberUpdated(member_id, changed_fields=("deleted_at", "status"))` para no inventar un evento nuevo.
- Sin funciones puras nuevas. Sin discrepancias.

## Validación contra la arquitectura

- Módulo dueño: `members`. No llama a `memberships` ni a `payments` (la baja no los afecta).
- Auditoría: el hook de US-016 registra la baja lógica como `update` con `deleted_at` y `status` antes y después; igual la reactivación.
- Rol: `require_role("admin")` en las dos rutas.
- Nunca `DELETE FROM members.members` ni `session.delete(member)`: prueba de arquitectura nueva para las tablas con borrado lógico.
- `deleted_at` se toma del `Clock` de `core/clock.py` (UTC), para poder congelarlo en pruebas.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (`deleted_at` y el índice único parcial existen desde `0006_members`).

### Models
- No aplica.

### Service
- [ ] T1 · Caso de uso `async def deactivate(session, member_id: UUID, by: Actor) -> None`: `MemberNotFound` si no existe; `MemberAlreadyDeactivated` (409 `member_already_deactivated`) si ya tiene `deleted_at`; fija `deleted_at = clock.now()` y `status = "inactive"`; emite `MemberDeactivated` — 1.5 h
- [ ] T2 · Caso de uso `async def reactivate(session, member_id: UUID, by: Actor) -> MemberDetailOut`: `MemberNotFound`; `MemberNotDeactivated` (409 `member_not_deactivated`) si está vivo; pre-chequea `document_idx` entre vivos y traduce también la `IntegrityError` del índice único a `MemberDocumentDuplicated(existing_id)`; limpia `deleted_at`, `status = "active"`; emite `MemberUpdated`; devuelve la ficha (US-073) — 2 h
- [ ] T3 · Excepciones `MemberAlreadyDeactivated` y `MemberNotDeactivated` en `exceptions.py`; evento `MemberDeactivated(DomainEvent)` con `member_id` en `service.py` — 0.5 h

### Schemas
- No aplica (la baja no tiene cuerpo y la reactivación devuelve `MemberDetailOut` de US-069).

### Router
- [ ] T4 · `DELETE /api/v1/members/{id}` con `Depends(require_role("admin"))`, `status_code=204` (códigos 204, 401, 403, 404, 409) y `POST /api/v1/members/{id}/reactivate` con `Depends(require_role("admin"))` (códigos 200, 401, 403, 404, 409) — 1 h

### Tests unitarios puros
- No aplica (sin funciones puras nuevas).

### Tests de service con PostgreSQL
- [ ] T5 · `api/tests/members/test_service_deactivate.py` con `FrozenClock`: la fila sigue existiendo con `deleted_at` en UTC y `status = 'inactive'`; fila `update` en auditoría con `deleted_at` antes y después; `MemberDeactivated` emitido; el socio sale de `list` por defecto y de la búsqueda por documento, teléfono, correo y nombre; un socio nuevo con el mismo documento se crea; las filas de `memberships.memberships` y `payments.payments` del socio no cambian (comparación por SQL crudo antes y después, cuando existan US-084 y US-095); baja repetida → `MemberAlreadyDeactivated`; reactivar vuelve a `active`, reactivar con el documento tomado → `MemberDocumentDuplicated` con `existing_id`, reactivar un vivo → `MemberNotDeactivated` — 3 h

### Tests de router
- [ ] T6 · `api/tests/members/test_router_deactivate.py`: 204 admin; 403 coach y `member` sin cambios; 401 sin token; 404 inexistente; 409 baja repetida; `reactivate` 200 admin, 403 coach, 409 `member_not_deactivated` y `member_document_duplicated` — 1.5 h

### Tests de arquitectura
- [ ] T7 · `api/tests/architecture/test_no_physical_delete.py`: analiza con `ast` el código de `app/modules/members`, `plans` y `auth` y falla si encuentra `session.delete(...)`, `delete(Member)`, `delete(Plan)`, `delete(User)` o SQL `DELETE FROM` sobre esas tablas; US-082 lo reutiliza para planes — 1 h

### Front
- [ ] T8 · `web/src/features/members/components/DeactivateMemberModal.tsx` con `ConfirmModal` del kit: texto "El socio deja de aparecer en la lista; sus membresías, pagos e historial se conservan"; visible solo con `useCan("member.deactivate")`; al confirmar llama a `useDeactivateMember`, vuelve a `/socios` con mensaje; muestra el error del API si falla — 2 h
- [ ] T9 · Acción "Reactivar" en la ficha de solo lectura (US-073) con `ConfirmModal`, solo admin; ante 409 de documento muestra el enlace al socio existente; `useReactivateMember` en `api.ts` invalida la ficha y las listas — 1.5 h
- [ ] T10 · Vitest `web/src/features/members/components/DeactivateMemberModal.test.tsx` y prueba de "Reactivar" en `MemberDetailPage.test.tsx`: acciones ocultas al coach, modal, errores — 1 h

### DevOps
- [ ] T11 · `docs/openapi.json` regenerado con `DELETE /members/{id}` y `POST /members/{id}/reactivate` — 0.5 h

### Seguridad
- [ ] T12 · Revisión: el coach no puede dar de baja ni reactivar por el API (no solo por el front); el 409 de reactivación solo expone `existing_id` a admin; la baja no borra datos personales (borrado definitivo por retención es tema de `privacy.retention_years`, fuera de alcance) — 0.5 h

## Orden de ejecución

1. T3.
2. T5 (en rojo), luego T1 y T2.
3. T4, T6 y T7.
4. T11 y T12.
5. T10 (en rojo), luego T8 y T9.

## Dependencias técnicas

- US-073 · Ver ficha del socio: ficha de solo lectura donde viven las acciones.
- US-069 · Registrar socio: índice único parcial que libera y vuelve a exigir el documento.
- US-070 · Buscar y listar socios: exclusión por defecto de dados de baja.
- US-016 · Hook de auditoría after_flush: baja lógica como `update`.
- US-013 · Reloj y fecha de Bogotá: `Clock` para `deleted_at`.
- US-065 · Panel lateral y modal de confirmación.
- US-084 y US-095 (solo para la prueba de que membresías y pagos no cambian).

## Endpoints

- `DELETE /api/v1/members/{id}` — roles: admin
- `POST /api/v1/members/{id}/reactivate` — roles: admin

## Riesgos

- Un socio dado de baja conserva membresías vigentes: el worker de vencimientos y el tablero siguen contándolo hasta que venzan — mitigación: comportamiento decidido por N-20; el resumen de US-092 cuenta solo socios no dados de baja.
- Reactivar después de que otro socio tomó el documento: dos fichas para la misma persona — mitigación: el 409 con `existing_id` obliga a resolverlo a mano.
- Front condicionado a D1.

## Estimación

- Backend: 5 h
- Front: 4.5 h
- Pruebas: 5.5 h
- DevOps / seguridad: 1 h
- **Total: 16 h**

Supera en 1 h la referencia de 3 puntos por la reactivación que agrega N-20.

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/members/test_service_deactivate.py -q`
- [ ] `cd api && uv run pytest tests/members/test_router_deactivate.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/members`
- [ ] Tras `curl -X DELETE /api/v1/members/<id>` (admin): `psql -c "SELECT deleted_at IS NOT NULL, status FROM members.members WHERE id='<id>'"` devuelve `t | inactive`.
- [ ] `grep -rn "DELETE FROM members" api/src` no devuelve nada.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.members --cov-fail-under=80`
