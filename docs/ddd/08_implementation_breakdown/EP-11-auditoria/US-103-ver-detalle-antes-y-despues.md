# US-103 · Ver detalle antes y después — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-11-auditoria/US-103-ver-detalle-antes-y-despues.md`
- **Épica:** EP-11 · Auditoría y trazabilidad
- **Bounded context / módulo:** Audit (`api/src/app/modules/audit/`; modelo en `api/src/app/core/audit.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

La ruta `GET /audit/{seq}` está aceptada por DECISIONES N-30. La función pura `diff`, la salida y la regla de no mostrar valores en claro están definidas. Los campos cifrados ya llegan como blob `apx1.` desde el hook de US-016, así que esta historia no descifra nada.

## Resumen

Agrega `audit.service.get(seq)`, la función pura `audit.diff(before, after) -> list[FieldChange]` y `GET /audit/{seq}` (solo admin) con `before`, `after`, `prev_hash`, `hash` y `changes`. En el front, el `SidePanel` de detalle de la pantalla `Auditoria`, que muestra los blobs como "Cifrado" con su `key_id` y nunca ofrece descifrar.

## Correcciones aplicadas por DECISIONES.md

- Supuesto de la historia "el detalle se pide por `seq` en `GET /audit/{seq}`, ruta nueva en el contrato" → aceptado por DECISIONES N-30; se agrega a `docs/openapi.json`.
- Las entradas `download` (recibos y adjuntos desde v0.2/v0.3) se muestran con el mismo detalle: DECISIONES N-08.
- Ninguna otra corrección.

## Validación contra el dominio

- Aggregate `AuditEntry`. RN-13: los campos cifrados se guardan y muestran como blob; RN-16: se muestran `prev_hash` y `hash`; RN-15: solo admin.
- Función pura `diff(before: dict | None, after: dict | None) -> list[FieldChange]` con `FieldChange(field, kind: "added" | "removed" | "changed", before, after)`: en `insert` todos los campos son `added`, en `delete` todos `removed`, en `update` solo los que difieren; para `reveal`, `login`, `verify` y `download` se aplica igual sobre el `after` (sin `before`).
- Eventos: ninguno.

## Validación contra la arquitectura

- Módulo dueño: `modules/audit`; lee `core.audit.AuditEntry`. Nombre del usuario por `auth.service.names_for` (mismo contrato que US-102).
- El reconocimiento de blobs (`apx1.<key_id>.<alg>...`) en el front es lectura de un prefijo de texto, no criptografía; no se toca el bus. El backend no intenta descifrar ni llamar a `core.crypto.bus.decrypt`, y una prueba lo asegura.
- Rol `require_role("admin")`.
- Orden de rutas: `GET /audit/verify/last` (US-104) se registra antes de `GET /audit/{seq}`; `{seq}` se declara `int` (422 si no es numérico).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `diff(before, after) -> list[FieldChange]` en `modules/audit/service.py` con orden estable por nombre de campo — 1 h
- [ ] T2 · `async def get(session, seq: int) -> AuditDetail`: `AuditNotFound` (404) si no existe; nombre del usuario por `auth.service.names_for`; `changes = diff(entry.before, entry.after)` — 1 h

### Schemas
- [ ] T3 · `AuditDetail { seq, at, user_id, user_email, user_name, action, table_name, record_id, before: dict | None, after: dict | None, prev_hash, hash, changes: list[FieldChange] }` — 0,5 h

### Router
- [ ] T4 · `GET /audit/{seq}` con `seq: int` (mínimo 1), `Depends(require_role("admin"))`, registrado después de `/audit/verify/last`; códigos 200, 401, 403, 404, 422 — 0,5 h

### Tests unitarios puros
- [ ] T5 · `api/tests/audit/test_diff.py`: insert, update sin cambios (lista vacía), update con dos campos, delete, campo que pasa a `null`, `reveal` con `after.field` — 1 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/audit/test_get.py`: socio creado y editado (teléfono y notas) por el service real de Members; la entrada `update` tiene `changes` con `phone` y `notes`; `before.phone` y `after.phone` empiezan por `apx1.` y la respuesta serializada no contiene el teléfono en claro (búsqueda del texto en el JSON completo); el service no llama a `bus.decrypt` (espía sobre el bus); `seq` inexistente levanta 404 — 1,5 h

### Tests de router
- [ ] T7 · `api/tests/audit/test_router_get.py`: 200 admin, 404, 422 con `abc`, 403 coach, 401 sin token, `/audit/verify/last` no cae en `{seq}` — 0,5 h

### Tests de arquitectura
- No aplica: siguen verdes `test_every_route_has_role.py` y `test_no_cross_models.py`.

### Front
- [ ] T8 · `web/src/features/system/api.ts`: `useAuditEntry(seq)`; `web/src/shared/lib/encryptedBlob.ts`: `parseEncryptedBlob(value) -> { keyId } | null` (prefijo `apx1.`); `web/src/features/system/components/AuditDetailPanel.tsx`: `SidePanel` con metadatos, lista de cambios (antes → después), valores cifrados como "Cifrado" con `key_id` y sin botón para descifrar, `prev_hash` y `hash` en fuente monoespaciada, carga y error — 1,5 h
- [ ] T9 · `web/src/features/system/components/AuditDetailPanel.test.tsx` y `web/src/shared/lib/encryptedBlob.test.ts`: render de "Cifrado" con `key_id`, ausencia de cualquier acción de descifrar — 0,5 h

### DevOps
- [ ] T10 · Regenerar `docs/openapi.json` y tipos del front — 0,5 h

### Seguridad
- [ ] T11 · Revisión: ningún camino de código del módulo audit importa o llama a `core.crypto.bus.decrypt`; solo admin; los hashes no son secretos — 0,5 h

## Orden de ejecución
1. T5 (pura en rojo)
2. T1
3. T6 (service en rojo)
4. T2
5. T3
6. T7 (router en rojo)
7. T4
8. T8, T9
9. T10
10. T11

## Dependencias técnicas
- US-102 · Consultar auditoría: pantalla, router y contrato `auth.service.names_for`.
- US-016 · Hook de auditoría: campos cifrados guardados como blob.
- US-028 · Tipo `Encrypted` (para la prueba con un socio real).
- US-069 / US-075 · Registrar y editar socio (datos de la prueba T6).
- US-104 · Verificar cadena: ruta `/audit/verify/last` registrada antes.

## Endpoints
- `GET /api/v1/audit/{seq}` — roles: admin

## Riesgos
- Si un módulo futuro audita un campo sensible sin el tipo `Encrypted`, quedaría en claro en `before`/`after` y esta pantalla lo mostraría — mitigación: la prueba de arquitectura de US-028/US-107 sobre columnas sensibles; aquí solo se muestra lo que hay.
- Front condicionado a D1.

## Estimación
- Backend: 3 h (T1 a T4)
- Front: 1,5 h (T8)
- Pruebas: 3,5 h (T5 a T7 y T9)
- DevOps / seguridad: 1 h (T10, T11)
- **Total: 9 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/audit/test_diff.py -q`
- [ ] `cd api && uv run pytest tests/audit/test_get.py -q`
- [ ] `cd api && uv run pytest tests/audit/test_router_get.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system/components/AuditDetailPanel.test.tsx src/shared/lib/encryptedBlob.test.ts`
- [ ] `curl /api/v1/audit/<seq-de-un-update-de-socio>` con token de admin devuelve `changes` y ningún valor sin prefijo `apx1.` en `phone`, `document`, `email`, `birth_date` ni `emergency_contact`; `curl /api/v1/audit/abc` devuelve 422
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.audit --cov-fail-under=80`
