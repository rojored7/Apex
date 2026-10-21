# US-077 · Contacto para avisos auditado — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-07-padron-de-socios/US-077-contacto-para-avisos-auditado.md`
- **Épica:** EP-07 · Padrón de socios
- **Bounded context / módulo:** Members, proveedor de Notifications (`api/src/app/modules/members/service.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

N-21 acepta el catálogo de propósitos y que el propósito vaya en `after` de la auditoría; N-15 fija el actor técnico del worker. Es un contrato interno sin HTTP y sin front, que se prueba sin el módulo de avisos.

## Resumen

- `members.service.contact_for_notification(member_id, purpose, by)` devuelve `Contact { first_name, phone, email }` en claro solo como valor de retorno; nunca se expone por HTTP.
- Admite los propósitos `notify` y `auth_link`; cualquier otro lanza `MemberError` antes de descifrar.
- Descifra teléfono y correo en un solo lote del bus (mismo `batch_id`), escribe una fila de auditoría `reveal` por campo descifrado con `after = {"field", "purpose"}` y emite `SensitiveFieldRevealed` con el propósito.
- Un socio dado de baja o inexistente lanza `MemberNotContactable` sin descifrar; un campo vacío vuelve `None` sin operación.
- Agrega una prueba de arquitectura que limita quién importa `core.crypto.bus`.

## Correcciones aplicadas por DECISIONES.md

- El criterio 3 dice que `user_id` es nulo cuando llama el worker → el actor del worker es `SYSTEM_USER_ID` (`00000000-0000-0000-0000-000000000001`), o el usuario de `--as <email>` si lo dispara una persona por CLI: corregido por DECISIONES N-15.
- El supuesto de propósitos `notify` y `auth_link` y del propósito guardado en `after` → aceptado; N-21 agrega `mask` al catálogo de propósitos de descifrado del módulo. `mask` lo usa solo la ficha (US-073) y nunca devuelve el valor fuera de `members`, por eso `contact_for_notification` lo rechaza igual que a un propósito desconocido: aceptado en DECISIONES N-21, coherente con N-01.
- Consecuencia de DECISIONES N-33 y N-34 (canales al socio y Telegram interno): no cambian este contrato; la elección de canal es de EP-14.

## Validación contra el dominio

- Aggregate `Member` (`Phone`, `Email`); RN-13 (descifrado auditado); RN-14 (un dado de baja no se contacta).
- Evento emitido: `SensitiveFieldRevealed(member_id, field, user_id, purpose)` por campo descifrado (el campo `purpose` lo declara US-074 como opcional).
- Función pura: `validate_purpose(purpose) -> None` (lanza `MemberError`).
- Sin discrepancias.

## Validación contra la arquitectura

- Contrato Customer/Supplier de `03_context_map.md` 2 (Notifications → Members con propósito `notify`) y sección 5 (ningún contexto descifra campos que no son suyos).
- Bus: descifrado por el tipo `Encrypted` dentro de `bus.batch("decrypt")` y `bus.op_context(user_id, record_id, purpose)`; ninguna primitiva fuera de `core/crypto`. Si la columna `purpose` de `crypto_ops` (brecha de US-073) se integra, la fila lleva `notify` o `auth_link`.
- Auditoría con `core.audit.record` en la misma transacción del llamador.
- Sin endpoint: no requiere rol HTTP; la prueba de rutas confirma que no está expuesta.
- Dataclass de salida, nunca el ORM; `repr=False` en los campos de contacto.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `validate_purpose(purpose: str) -> ContactPurpose` que acepta `notify` y `auth_link` y lanza `MemberError(code="invalid_purpose")` para cualquier otro, incluido `mask` — 0.5 h
- [ ] T2 · Caso de uso `async def contact_for_notification(session, member_id: UUID, purpose: str, by: Actor = SYSTEM_ACTOR) -> Contact`: valida el propósito antes de leer nada; carga el socio y lanza `MemberNotContactable` si no existe o tiene `deleted_at`; descifra solo los campos no nulos en un `bus.batch("decrypt")` con `op_context(user_id=by.id, record_id=member_id, purpose=purpose)`; por cada campo descifrado escribe `audit.record(action="reveal", table_name="members", record_id=member_id, after={"field": f, "purpose": purpose}, user_id=by.id)` y emite `SensitiveFieldRevealed(..., purpose=purpose)` — 3 h
- [ ] T3 · Dataclass congelada `Contact(first_name, phone, email)` con `field(repr=False)` en `phone` y `email`; excepción `MemberNotContactable` en `exceptions.py`; constante `SYSTEM_ACTOR` construida con la constante `SYSTEM_USER_ID` que exponga `core/` (se propone `core/security.py`; la fija EP-01/EP-03 por N-15) — 0.5 h

### Schemas
- No aplica (contrato interno sin HTTP).

### Router
- No aplica (no se expone por HTTP, criterio 1).

### Tests unitarios puros
- [ ] T4 · `api/tests/members/test_validate_purpose.py`: `notify` y `auth_link` válidos; `marketing`, `mask` y cadena vacía rechazados — 0.5 h

### Tests de service con PostgreSQL
- [ ] T5 · `api/tests/members/test_service_contact.py`: devuelve teléfono y correo sembrados; dos filas `reveal` con `after.purpose = "notify"` y `user_id = SYSTEM_USER_ID`; dos filas `decrypt` en `crypto_ops` con el mismo `batch_id`; propósito `marketing` no deja ninguna fila en `crypto_ops` ni en auditoría; socio dado de baja → `MemberNotContactable` sin descifrar; correo vacío → `None` y una sola fila de cada tipo; `--as` simulado con otro actor deja su `user_id`; `repr(contact)` no contiene el teléfono — 2 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T6 · `api/tests/architecture/test_crypto_bus_importers.py`: solo `app.core.*`, `app.modules.members`, `app.modules.athletes` y `app.modules.attachments` pueden importar `app.core.crypto.bus` (`03_context_map.md` sección 5); falla si `app.modules.notifications` (cuando exista) lo importa. Y en `test_every_route_has_role.py` (US-035) o en este archivo: ningún `router.py` referencia `contact_for_notification` — 1 h

### Front
- No aplica.

### DevOps
- No aplica.

### Seguridad
- [ ] T7 · Revisión: el `Contact` nunca se loguea (filtro de logs y `repr=False`); la auditoría no contiene valores; documentar en el docstring que el llamador es responsable de no persistir el contacto en claro (EP-14 guarda solo `rendered_body`) — 0.5 h

## Orden de ejecución

1. T4 (en rojo) y T1.
2. T3.
3. T5 (en rojo) y T2.
4. T6 y T7.

## Dependencias técnicas

- US-069 · Registrar socio: tabla y campos cifrados.
- US-074 · Mostrar dato sensible auditado: evento `SensitiveFieldRevealed` con `purpose` opcional.
- US-029 · Bitácora crypto_ops por lote: `bus.batch` con un `batch_id` por lote.
- US-015 · Tabla de auditoría: `core.audit.record`.
- US-041 · Tablas de auth: usuario técnico `SYSTEM_USER_ID` creado en `0004_auth` (N-15).
- Consumidor: EP-14 (US-124, US-126, US-131), en v0.2.

## Endpoints

- Ninguno.

## Riesgos

- El worker podría pedir el contacto para muchos socios en un bucle, una auditoría por campo y socio: crece `audit_log` — mitigación: es el rastro que exige la Ley 1581; el volumen (pocos cientos por día) es manejable.
- Un módulo futuro descifra por su cuenta saltándose este contrato — mitigación: T6 lo impide en CI.
- Sin la columna `purpose` en `crypto_ops` (brecha de US-073) el propósito solo queda en la auditoría — mitigación: la auditoría es la evidencia exigida; la columna es complemento.

## Estimación

- Backend: 4 h
- Front: 0 h
- Pruebas: 3.5 h
- DevOps / seguridad: 0.5 h
- **Total: 8 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/members/test_validate_purpose.py -q`
- [ ] `cd api && uv run pytest tests/members/test_service_contact.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `grep -rn "contact_for_notification" api/src/app/modules/*/router.py` no devuelve nada.
- [ ] Tras una llamada de prueba: `psql -c "SELECT after->>'purpose', user_id FROM audit.audit_log WHERE action='reveal' ORDER BY seq DESC LIMIT 2"` muestra `notify` y `00000000-0000-0000-0000-000000000001`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.members --cov-fail-under=80`
