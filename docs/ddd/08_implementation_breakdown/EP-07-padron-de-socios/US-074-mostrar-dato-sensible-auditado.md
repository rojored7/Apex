# US-074 · Mostrar dato sensible auditado — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-07-padron-de-socios/US-074-mostrar-dato-sensible-auditado.md`
- **Épica:** EP-07 · Padrón de socios
- **Bounded context / módulo:** Members, con Crypto (bus) y Audit (`api/src/app/modules/members/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Q6 fija los roles (admin y coach, siempre auditado), N-01 confirma que `reveal` es la única forma de ver el valor completo, y la consolidación de historias decidió que esta historia escribe la fila `reveal` con `audit.record` en la misma transacción. Los criterios se cumplen con la bitácora `crypto_ops` tal como la define US-029; el propósito `reveal` en `crypto_ops` es una mejora que llega con la brecha de US-073 y no bloquea.

## Resumen

- `POST /api/v1/members/{id}/reveal` con `{ "field": ... }` para admin y coach: descifra un solo campo con el bus y responde `{ field, value }` con `Cache-Control: no-store`.
- En la misma transacción: una fila `crypto_ops` (`decrypt`), una fila de auditoría `reveal` escrita con `core.audit.record` (`after = {"field": ...}`) y el evento `SensitiveFieldRevealed`.
- Si algo del rastro falla, la respuesta es 500 y el valor no sale: el router confirma la transacción antes de construir la respuesta.
- Front: `MaskedValue.onReveal` llama a una mutación sin caché y vuelve a enmascarar al ocultar, al salir de la ficha o a los 60 segundos.

## Correcciones aplicadas por DECISIONES.md

- Ninguna corrección de contenido: la historia ya sigue Q6 (admin y coach) y N-01 (`reveal` es la única vía al valor completo, auditada).
- Consecuencia de DECISIONES N-20: un socio dado de baja se ve en la ficha en solo lectura, así que `reveal` sobre un dado de baja también se permite a admin y coach, con la misma auditoría; solo un id inexistente responde 404.
- Consecuencia de DECISIONES N-21: el detalle de la consulta va en `after` de la auditoría (`{"field": "phone"}`), porque `AuditEntry` no tiene columnas extra.

## Validación contra el dominio

- Aggregate `Member` y sus value objects cifrados; RN-13 (mostrar en claro se audita).
- Evento emitido: `SensitiveFieldRevealed(member_id, field, user_id)` (catálogo de `02_domain_model.md` sección 3).
- Discrepancia menor con el catálogo de eventos: el catálogo pone a `audit` como suscriptor de `SensitiveFieldRevealed`; por la consolidación de historias (ciclo US-074/US-107) la fila la escribe esta historia directamente y no debe existir un suscriptor que la duplique. Se cubre con una prueba (exactamente una fila).
- Sin funciones puras nuevas (el campo se valida con el enum del esquema).

## Validación contra la arquitectura

- Módulo dueño: `members`. Llama a `core.audit.record` (core, permitido) y a `core.events.emit`; no llama a otros módulos.
- Bus: el valor sale de `core.crypto.bus.decrypt(blob, aad = id)` a través del tipo `Encrypted`; ninguna primitiva fuera de `core/crypto`.
- Transaccionalidad: el use case hace `flush` de la auditoría y del registro de `crypto_ops`; el router hace `commit` explícito antes de devolver para que una falla de confirmación no deje salir el valor (no se confía en el cierre de la dependencia de sesión, que puede correr después de enviar la respuesta).
- Rol: `require_role("admin", "coach")`. Ruta incluida en `test_every_route_has_role.py`.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Caso de uso `async def reveal(session, member_id: UUID, field: SensitiveField, by: Actor) -> RevealedValue`: carga el socio (incluye dados de baja; `MemberNotFound` si no existe); si el blob es `NULL`, `value = None` sin descifrar; si no, descifra solo ese campo dentro de `bus.op_context(user_id=by.id, record_id=member_id, purpose="reveal")` (el propósito se registra cuando EP-02 integre la columna de la brecha de US-073); escribe `audit.record(session, action="reveal", table_name="members", record_id=member_id, before=None, after={"field": field}, user_id=by.id)`; emite `SensitiveFieldRevealed`; hace `flush` — 3 h
- [ ] T2 · Evento `SensitiveFieldRevealed(DomainEvent)` con `member_id`, `field`, `user_id` y `purpose: str | None = None` (US-077 lo usa con `notify` y `auth_link`), declarado en `members/service.py` — 0.5 h

### Schemas
- [ ] T3 · `RevealIn { field: Literal["document","phone","email","birth_date","emergency_contact"] }` con `extra="forbid"`; `RevealOut { field, value: str | EmergencyContactOut | None }` (`birth_date` como `AAAA-MM-DD`) — 0.5 h

### Router
- [ ] T4 · `POST /api/v1/members/{id}/reveal` con `Depends(require_role("admin", "coach"))`; llama al service, hace `await session.commit()` explícito y solo entonces arma la respuesta con `Cache-Control: no-store`; códigos 200, 401, 403, 404, 422, 500 — 1 h

### Tests unitarios puros
- No aplica (sin funciones puras nuevas; el enum lo valida Pydantic y se prueba en T6).

### Tests de service con PostgreSQL
- [ ] T5 · `api/tests/members/test_service_reveal.py`: el valor descifrado coincide con el sembrado para los cinco campos; exactamente una fila `reveal` en `audit.audit_log` con `user_id`, `record_id` y `after.field`, sin el valor; una fila `decrypt` en `crypto_ops` con `data_class` y `record_id`; si `audit.record` lanza error (monkeypatch), la transacción se revierte y no hay valor; campo vacío devuelve `None` y también se audita; `SensitiveFieldRevealed` emitido una vez y ningún suscriptor agrega otra fila `reveal`; funciona sobre un dado de baja — 2.5 h

### Tests de router
- [ ] T6 · `api/tests/members/test_router_reveal.py`: 200 admin y coach con `{ field, value }`; 422 con `field = "field"` para `"first_name"`; 403 `member` sin fila `reveal`; 401 sin token; 404 inexistente; cabecera `Cache-Control: no-store`; falla simulada del `commit` responde 500 y el cuerpo no contiene el valor; `caplog` sin el valor — 2.5 h

### Tests de arquitectura
- No aplica (siguen en verde `test_every_route_has_role.py`, `test_banned_imports.py` y `test_service_import_cycles.py`).

### Front
- [ ] T7 · `web/src/features/members/api.ts`: `useRevealField(memberId)` como `useMutation` sin escribir en la caché de consultas (`gcTime: 0`, sin `setQueryData`); conexión de `MaskedValue.onReveal` en `MemberDetailPage`; el valor vive en estado local del componente y se limpia al ocultar, al desmontar y a los 60 segundos — 2.5 h
- [ ] T8 · Vitest `web/src/shared/ui/MaskedValue.reveal.test.tsx` con temporizadores falsos: una sola llamada por clic, re-enmascarado a los 60 s, al ocultar y al desmontar; error del API muestra mensaje sin valor — 1.5 h

### DevOps
- [ ] T9 · `docs/openapi.json` regenerado — 0.5 h

### Seguridad
- [ ] T10 · Revisión: el valor no aparece en logs del API ni en el `repr` de excepciones; `no-store` también en Nginx para la ruta; `RevealOut` no se reutiliza en otra respuesta; anotar como mejora futura un umbral de `reveal` por usuario y hora para detectar extracción masiva (no está en el alcance) — 0.5 h

## Orden de ejecución

1. T2 y T3.
2. T5 (en rojo), luego T1.
3. T6 (en rojo), luego T4.
4. T9 y T10.
5. T8 (en rojo), luego T7.

## Dependencias técnicas

- US-073 · Ver ficha del socio: ficha y `MaskedValue` montados.
- US-015 · Tabla de auditoría y cadena de hashes: `core.audit.record` con acción `reveal`.
- US-029 · Bitácora crypto_ops por lote: fila `decrypt` en la misma transacción.
- US-014 · Bus de eventos transaccional.
- US-066 · Valor enmascarado e historial (componente `MaskedValue`).
- US-107 · Auditoría de eventos de seguridad: queda sin la fila `reveal` (ciclo resuelto en consolidación).

## Endpoints

- `POST /api/v1/members/{id}/reveal` — roles: admin, coach

## Riesgos

- Si el `commit` ocurre al cerrar la dependencia de sesión, una falla podría llegar después de enviar el valor — mitigación: `commit` explícito en el router antes de responder y prueba de falla en T6.
- Un suscriptor futuro de `SensitiveFieldRevealed` en `audit` duplicaría la fila — mitigación: prueba de "exactamente una fila" en T5.
- Extracción masiva de datos por un usuario legítimo: queda auditada pero no se frena — mitigación: el rastro existe; el umbral se propone como mejora fuera de alcance.
- Front condicionado a D1.

## Estimación

- Backend: 5 h
- Front: 4 h
- Pruebas: 5 h
- DevOps / seguridad: 1 h
- **Total: 15 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/members/test_service_reveal.py -q`
- [ ] `cd api && uv run pytest tests/members/test_router_reveal.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/shared/ui/MaskedValue.reveal.test.tsx`
- [ ] `curl -i -X POST /api/v1/members/<id>/reveal -d '{"field":"phone"}'` con token de coach muestra `Cache-Control: no-store` y el teléfono.
- [ ] `psql -c "SELECT action, after FROM audit.audit_log WHERE record_id='<id>' ORDER BY seq DESC LIMIT 1"` muestra `reveal | {"field": "phone"}` y no contiene el número.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.members --cov-fail-under=80`
