# US-075 · Editar socio — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-07-padron-de-socios/US-075-editar-socio.md`
- **Épica:** EP-07 · Padrón de socios
- **Bounded context / módulo:** Members (`api/src/app/modules/members/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

N-20 resuelve el único supuesto que cambiaba el contrato (quién puede cambiar el documento) y N-01 elimina el recálculo de `*_hint`. El recifrado y el recálculo del índice ciego los da el tipo `Encrypted`/`BlindIndexed` (US-028). La respuesta enmascarada depende de la brecha de propósito de US-073, que se lista como dependencia y no cambia este contrato.

## Resumen

- `PATCH /api/v1/members/{id}` para admin y coach con semántica parcial: solo cambia lo enviado y `null` borra un campo opcional.
- Cada campo sensible enviado se recifra con la llave activa (nonce nuevo, mismo `aad = id`) y su índice ciego se recalcula en el mismo flush.
- Solo admin cambia el documento; un coach que lo envía recibe 403 con `field = "document"`.
- Cambiar a un documento ya usado por otro socio vivo responde 409 con `existing_id`; editar un dado de baja responde 409 `member_deactivated`.
- La auditoría `update` lleva solo los campos cambiados, con blobs; un PATCH sin cambios efectivos no audita ni emite `MemberUpdated`.
- La respuesta es `MemberDetail` enmascarado con `warnings: []`.
- Front: `MemberFormPage` en modo edición, sin mostrar nunca el valor actual en claro.

## Correcciones aplicadas por DECISIONES.md

- El supuesto "el coach puede cambiar el documento" → solo admin cambia el documento (es identidad); el coach edita el resto y recibe 403 si envía `document`: corregido por DECISIONES N-20.
- El supuesto "los `hint` de enmascarado se recalculan al cambiar el campo" → no existen `*_hint`; la respuesta enmascarada se calcula descifrando en memoria con propósito `mask`: corregido por DECISIONES N-01.
- La respuesta de editar no menciona `warnings` → lleva `warnings` (lista vacía o `data_consent_missing` si sigue sin autorización), igual que crear: corregido por DECISIONES N-19.
- El recálculo del índice usa la normalización de N-02 (en `core/crypto`, US-026): corregido por DECISIONES N-02.
- La historia menciona actualizar `updated_by`, que no es columna del mixin común (`CLAUDE.md`, regla de datos 3: `id`, `created_at`, `updated_at`, `created_by`) → el autor de cada cambio queda en `audit.audit_log.user_id`; no se agrega columna (alineado con `CLAUDE.md`, no es cambio de alcance).

## Validación contra el dominio

- Aggregate `Member`; invariantes: documento único entre vivos, nombres no vacíos, sexo válido, fecha de nacimiento no futura (`validate_member_input` de US-069), RN-14 (un dado de baja no se edita) y RN-13 (recifrado).
- Evento emitido: `MemberUpdated(member_id, changed_fields)` con nombres de campo, nunca valores.
- Funciones puras: `diff_fields(before, patch) -> frozenset[str]` y `ensure_can_change(fields, role)`.
- Sin discrepancias de dominio.

## Validación contra la arquitectura

- Módulo dueño: `members`; sin llamadas a otros módulos.
- Bus: recifrado e índice por los tipos de columna (US-028); para comparar y enmascarar, los valores actuales se descifran en un solo `bus.batch("decrypt")` con propósito `mask` (lectura interna que no sale del servidor, N-01); ninguna primitiva fuera de `core/crypto`.
- Auditoría: el hook de US-016 registra `update` con `before`/`after` solo de las columnas con historial real (incluye `*_idx`, que son HMAC); se verifica en pruebas.
- Rol: `require_role("admin", "coach")` en la ruta y regla de campo en el service (403 para coach con `document`).
- Concurrencia en el documento: índice único parcial de `0006_members` traducido a 409.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `diff_fields(before: MemberValues, patch: Mapping[str, object]) -> frozenset[str]`: compara solo las claves enviadas; para documento, teléfono y correo compara el valor normalizado con `normalize_for_index` (un cambio solo de formato no cuenta); `None` sobre un opcional con valor cuenta como cambio — 1.5 h
- [ ] T2 · Función pura `ensure_can_change(fields: frozenset[str], role: Role) -> None` que lanza `MemberFieldForbidden(field="document")` si el rol no es admin — 0.5 h
- [ ] T3 · Caso de uso `async def update(session, member_id: UUID, patch: MemberPatch, by: Actor) -> MemberDetailOut`: carga el socio (`MemberNotFound`); si `deleted_at` no es nulo lanza `MemberDeactivated`; descifra los valores actuales con propósito `mask`; valida el estado resultante con `validate_member_input`; calcula `diff_fields`; aplica `ensure_can_change`; si no hay cambios devuelve la ficha sin `flush`; si cambia el documento, pre-chequea `document_idx` contra otros vivos y traduce `IntegrityError` a `MemberDocumentDuplicated(existing_id)`; asigna solo los campos cambiados (el tipo recifra y reindexa); emite `MemberUpdated`; arma la respuesta enmascarada con `warnings` — 4.5 h
- [ ] T4 · `members/exceptions.py`: `MemberDeactivated` (409 `member_deactivated`) y `MemberFieldForbidden` (403 `forbidden_field` con `field`) — 0.5 h
- [ ] T5 · Evento `MemberUpdated(DomainEvent)` con `member_id` y `changed_fields: tuple[str, ...]` — 0.5 h

### Schemas
- [ ] T6 · `MemberPatch` con todos los campos de `MemberCreate` opcionales, `extra="forbid"`; uso de `model_fields_set` para distinguir "no enviado" de `null`; `null` en `first_name`, `last_name` o `document` responde 422 (N-19: documento obligatorio) — 1.5 h

### Router
- [ ] T7 · `PATCH /api/v1/members/{id}` con `Depends(require_role("admin", "coach"))`, `response_model=MemberDetailOut`; códigos 200, 401, 403, 404, 409, 422 — 1 h

### Tests unitarios puros
- [ ] T8 · `api/tests/members/test_member_patch_rules.py`: `diff_fields` (sin cambios, un cambio, cambio solo de formato `"300 123 4567"` frente a `"3001234567"`, `null` en opcional) y `ensure_can_change` (admin y coach con y sin `document`) — 1.5 h

### Tests de service con PostgreSQL
- [ ] T9 · `api/tests/members/test_service_update.py`: cambiar el teléfono cambia el blob (nonce distinto), descifra al nuevo valor, recalcula `phone_idx` y la búsqueda por el número viejo ya no encuentra; documento repetido → `MemberDocumentDuplicated` sin cambios parciales; dado de baja → `MemberDeactivated`; auditoría `update` solo con las columnas cambiadas y blobs en `before` y `after`; PATCH sin cambios → sin fila de auditoría ni evento; `MemberUpdated.changed_fields` sin valores; coach con `document` → `MemberFieldForbidden` — 3.5 h

### Tests de router
- [ ] T10 · `api/tests/members/test_router_update.py`: 200 admin y coach, 403 `member`, 403 coach con `document` y `field = "document"`, 401, 404, 409 (`member_document_duplicated` con `existing_id`, `member_deactivated`), 422 (`last_name` vacío, `sex` inválido, `birth_date` futura, `document: null`), `warnings` presente — 2 h

### Tests de arquitectura
- No aplica (siguen en verde `test_no_cross_models.py`, `test_every_route_has_role.py`, `test_banned_imports.py` y `test_members_encrypted_at_rest.py`).

### Front
- [ ] T11 · `MemberFormPage.tsx` en modo edición y `useUpdateMember(id)` en `api.ts`: campos no sensibles precargados; campos sensibles vacíos con su valor enmascarado como ayuda y botón "Cambiar" (el de documento solo con `useCan("member.document.change")`, admin); envía solo los campos modificados (`dirtyFields` de React Hook Form); al guardar invalida `useMember(id)` y las listas; `// DESIGN-GAP:` presentación de campos sensibles en edición — 4 h
- [ ] T12 · Vitest `web/src/features/members/pages/MemberFormPage.edit.test.tsx`: solo envía modificados, nunca muestra valor en claro, "Cambiar" del documento oculto al coach, error 409 con enlace — 2 h

### DevOps
- [ ] T13 · `docs/openapi.json` regenerado — 0.5 h

### Seguridad
- [ ] T14 · Revisión: los valores actuales descifrados para comparar no se loguean ni se devuelven; el 403 por campo no revela el documento actual; la carrera de dos ediciones con el mismo documento se resuelve por el índice único — 0.5 h

## Orden de ejecución

1. T8 (en rojo), luego T1 y T2.
2. T4, T5 y T6.
3. T9 (en rojo), luego T3.
4. T7 y T10.
5. T13 y T14.
6. T12 (en rojo), luego T11.

## Dependencias técnicas

- US-073 · Ver ficha del socio: ficha, `MemberDetailOut` y descifrado con propósito `mask` (con su brecha de EP-02).
- US-069 · Registrar socio: `validate_member_input`, `mask`, índice único parcial.
- US-028 · Tipos de columna Encrypted y BlindIndexed: recifrado y reindexado en el mismo flush.
- US-016 · Hook de auditoría after_flush: `update` solo con columnas cambiadas.
- US-040 · Matriz de permisos del front: permiso `member.document.change`.

## Endpoints

- `PATCH /api/v1/members/{id}` — roles: admin, coach

## Riesgos

- Si el hook de auditoría serializa la fila completa en lugar de solo lo cambiado, se incumple el criterio 6 — mitigación: T9 lo verifica y, si falla, se corrige en US-016.
- Comparar por valor normalizado hace que un cambio solo de formato no se guarde: el formato original del dato se conserva — mitigación: comportamiento esperado (el índice no cambia); documentado en el texto de ayuda del formulario.
- El descifrado interno para comparar depende del propósito `mask` de la brecha de US-073 — mitigación: mientras EP-02 lo integra, la operación queda en `crypto_ops` como `decrypt` sin propósito.
- Front condicionado a D1.

## Estimación

- Backend: 10 h
- Front: 6 h
- Pruebas: 7 h
- DevOps / seguridad: 1 h
- **Total: 24 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/members/test_member_patch_rules.py -q`
- [ ] `cd api && uv run pytest tests/members/test_service_update.py -q`
- [ ] `cd api && uv run pytest tests/members/test_router_update.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/members/pages/MemberFormPage.edit.test.tsx`
- [ ] `curl -X PATCH /api/v1/members/<id> -d '{"document":"55667788"}'` con token de coach responde 403 con `field = "document"`.
- [ ] Tras cambiar un teléfono: `psql -c "SELECT action, before ? 'phone', after ? 'phone', before ? 'first_name' FROM audit.audit_log WHERE record_id='<id>' ORDER BY seq DESC LIMIT 1"` muestra `update | t | t | f`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.members --cov-fail-under=80`
