# US-106 · Historial del socio — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-11-auditoria/US-106-historial-del-socio.md`
- **Épica:** EP-11 · Auditoría y trazabilidad
- **Bounded context / módulo:** Audit (`api/src/app/modules/audit/`, `api/src/app/core/audit.py`), consumido desde Members (`api/src/app/modules/members/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**ARCHITECTURAL_GAP_DETECTED**

DECISIONES N-31 amplía el historial de la ficha a las entradas de `members`, `memberships` y `payments` del socio (por `record_id` de sus membresías y pagos). Reunir esos ids obligaría a que un módulo de negocio (Members) encadene los services de Memberships, Payments y Audit, y además Members dependería de Payments, que ya depende de Members (ciclo). `core/audit.py` tampoco puede consultarlos porque `core` no depende de módulos. Falta en la arquitectura un "sujeto" de la entrada de auditoría que permita filtrar por socio sin componer; se propone abajo.

## Resumen

Expone `GET /members/{id}/audit` (admin y coach) con la línea de tiempo del socio: altas, ediciones, bajas, consultas en claro (`reveal`), y desde N-31 también ventas, cambios de estado y anulaciones de sus membresías y el registro y anulación de sus pagos. Cada ítem trae acción, usuario, fecha, tabla y los nombres de los campos cambiados (o el campo revelado), nunca valores. En el front, la pestaña Historial de `Socio_Ficha` con `HistoryAside` y frases del tipo "Ana P. editó teléfono y notas". El desglose de tareas asume aprobada la propuesta A de "Preguntas abiertas".

## Correcciones aplicadas por DECISIONES.md

- Supuesto de la historia "en v0.1 el historial incluye solo las entradas de la tabla `members`" → incluye `members`, `memberships` y `payments` del socio: corregido por DECISIONES N-31. Consecuencia: cada ítem lleva `table_name` para que el front arme la frase correcta (agregado mínimo al `MemberHistoryItem` de la historia).
- Supuesto "los `reveal` se registran con `table_name = "members"`, `record_id = id del socio` y `after.field`" → se mantiene; la fila la escribe US-074 (ajuste de consolidación del README de historias) y, con la propuesta A, además lleva `subject_member_id`.
- Las entradas hechas por procesos sin usuario aparecen como "Sistema": DECISIONES N-15.
- La acción `download` (recibos desde v0.2, adjuntos desde v0.3) entra en el historial cuando exista: DECISIONES N-08.

## Validación contra el dominio

- Lectura del aggregate `AuditEntry` filtrada por socio. RN-13 (los `reveal` aparecen; ningún valor cifrado se muestra), RN-16 (no se altera la cadena), regla de datos 6 (paginación).
- El socio de una membresía es `Membership.member_id`; el socio de un pago es la copia inmutable `Payment.member_id` que agrega US-095. Ninguno cambia después de crear, así que el sujeto de una entrada nunca queda desactualizado.
- Función pura nueva `history_fields(entry) -> list[str]`: en `update` los campos de `diff` (US-103), en `reveal` `[after.field]`, en `insert` y `delete` lista vacía (la frase es "creó" o "dio de baja").
- Eventos: ninguno.

## Validación contra la arquitectura

- Qué falla hoy:
  - Componer en `members.service` exige `memberships.service.ids_for_member`, `payments.service.ids_for_member` y `audit.service.list(record_ids=...)`: tres services de otros módulos desde un módulo de negocio que no es de lectura (`dashboard`, `portal`, `tv`), contra la regla de no encadenar tres services.
  - `members` importando `payments.service` cierra un ciclo con `payments.service` → `members.service.search_ids` (US-098).
  - Resolverlo en `core/audit.py` exigiría que `core` dependa de módulos, prohibido por `CLAUDE.md` (regla de módulos 4) y por el mapa de contextos (Audit no depende de nadie).
  - No existe en la estructura de `CLAUDE.md` un módulo de lectura de "historial" donde poner la composición.
- Con la propuesta A: `members.router` → `members.service.history(member_id, page)` → `members.service.ensure_exists` (incluye dados de baja, N-20) y `audit.service.member_history(subject_member_id, page)`. El router llama a un service; Members depende de Audit (lectura, Published Language) y Audit de Auth para nombres (como US-102). Sin imports de `models` ajenos.
- Rol `require_role("admin", "coach")`. Paginación común. Sin bus de cifrado: la respuesta no lleva `before`/`after`.

## Preguntas abiertas

- **Brecha:** la entrada de auditoría no tiene un sujeto de negocio; filtrar "todo lo del socio X" sobre tres tablas exige componer ids entre módulos que no pueden componerse.
- **Propuesta A (recomendada): columna `subject_member_id` en `audit.audit_log` poblada por el hook.**
  - Columna `subject_member_id UUID NULL` en `audit.audit_log`, incluida en `canonical(row)` (entra al hash, así que no se puede alterar sin romper la cadena), con índice `ix_audit_subject_member_seq (subject_member_id, seq DESC)`.
  - Atributo de clase opcional `__audit_subject__: str` en los modelos auditados, con el nombre del atributo que da el socio: `Member` → `"id"`, `Membership` → `"member_id"`, `Payment` → `"member_id"`. `MembershipFreeze` (si se audita) queda sin sujeto porque no tiene `member_id` y el hook no puede resolverlo por su membresía; está fuera de lo que nombra N-31 (ver Riesgos).
  - El hook de US-016 lee `getattr(obj, obj.__audit_subject__)` si existe; `core.audit.record(...)` recibe `subject_member_id` opcional (US-074 lo pasa en el `reveal`). `core` sigue sin conocer ningún módulo: solo lee un atributo declarado por el modelo.
  - Requiere `payments.member_id` (ya incluido en `0010_payments` por US-095).
  - Migración: como `0002_audit_log` aún no tiene datos, lo correcto es incluir la columna y el índice en `0002_audit_log` y la regla en `canonical` de US-015 antes del primer dato (la serialización canónica es irreversible). Si `0002` ya estuviera aplicada en algún entorno con datos, se usa `0014_audit_subject_member` (columna nula, sin relleno, porque las filas antiguas quedan con `null` y su hash no cambia si `canonical` omite la clave cuando es nula).
  - Alternativa por defecto si no se responde: A, dentro de `0002_audit_log`.
- **Propuesta B (descartada salvo que el orquestador la prefiera):** módulo de solo lectura nuevo `modules/history` (como `dashboard`, sin esquema) que compone `members`, `memberships`, `payments` y `audit`. Funciona sin tocar la cadena, pero crea un módulo que `CLAUDE.md` no prevé y hace consultas `record_id = ANY(:ids)` con listas que crecen con la antigüedad del socio.
- **Pregunta cerrada para el orquestador:** ¿se aprueba la propuesta A (columna `subject_member_id` en `0002_audit_log`, atributo `__audit_subject__` en `Member`, `Membership` y `Payment`, y `payments.member_id` en `0010_payments`)? Por defecto: sí.

## Tareas

### Migración Alembic
- [ ] T1 · Con la propuesta A: agregar a `0002_audit_log` (US-015) la columna `subject_member_id UUID NULL` y el índice `ix_audit_subject_member_seq (subject_member_id, seq DESC)`; si `0002` ya tiene datos en algún entorno, crear `0014_audit_subject_member` con lo mismo y `downgrade` que elimina índice y columna — 1 h

### Models
- [ ] T2 · `core/audit.py`: columna `subject_member_id` en `AuditEntry` e inclusión en `canonical(row)` (omitida si es nula); declarar `__audit_subject__ = "id"` en `members/models.py` (`Member`), `"member_id"` en `memberships/models.py` (`Membership`) y `"member_id"` en `payments/models.py` (`Payment`) — 1,5 h

### Service
- [ ] T3 · `core/audit.py`: el hook `after_flush` de US-016 toma `subject_member_id` de `__audit_subject__` cuando el modelo lo declara; `record(...)` acepta `subject_member_id: UUID | None = None` (US-074 lo pasa en el `reveal`) — 1,5 h
- [ ] T4 · `modules/audit/service.py`: función pura `history_fields(entry) -> list[str]` y `async def member_history(session, subject_member_id: UUID, page: PageParams) -> Page[MemberHistoryItem]` (consulta por `subject_member_id ORDER BY seq DESC` sin cargar valores; nombres por `auth.service.names_for`) — 1,5 h
- [ ] T5 · `modules/members/service.py`: `async def history(session, member_id: UUID, page) -> Page[MemberHistoryItem]` que llama a `ensure_exists(member_id, include_deleted=True)` (404) y a `audit.service.member_history` — 0,5 h

### Schemas
- [ ] T6 · `modules/audit/schemas.py`: `MemberHistoryItem { seq, at, user_id, user_name, action, table_name, record_id, fields: list[str] }` — 0,5 h

### Router
- [ ] T7 · `modules/members/router.py`: `GET /members/{id}/audit` con `Depends(require_role("admin", "coach"))`; códigos 200, 401, 403, 404, 422 — 0,5 h

### Tests unitarios puros
- [ ] T8 · `api/tests/audit/test_history_fields.py`: `insert`, `update` con teléfono y notas, `reveal` con `document`, `delete`; `canonical` con y sin `subject_member_id` (sin la clave cuando es nula, el hash es el mismo de US-015) — 1 h

### Tests de service con PostgreSQL
- [ ] T9 · `api/tests/audit/test_member_history.py`: socia creada por "Ana Pérez", editada y revelada por "Juan Ruiz", con una membresía vendida y un pago registrado y anulado; el historial trae las entradas de `members`, `memberships` y `payments` en orden `seq` descendente con `subject_member_id` correcto; ninguna entrada de otro socio; ningún valor cifrado en la respuesta (búsqueda del texto en el JSON); abrir la ficha (`members.service.get`) no agrega entradas; socio dado de baja devuelve su historial incluida la baja; la cadena sigue íntegra con `verify_chain` — 2,5 h

### Tests de router
- [ ] T10 · `api/tests/members/test_router_member_audit.py`: 200 coach y admin, 404 socio inexistente, 422 `limit=0`, 403 member, 401 sin token — 1 h

### Tests de arquitectura
- [ ] T11 · `api/tests/architecture/test_audit_subject.py`: `Member`, `Membership` y `Payment` declaran `__audit_subject__` y el atributo existe en el modelo; `modules/members` no importa `memberships.service` ni `payments.service` para esta ruta; `test_no_cross_models.py` sigue verde — 1 h

### Front
- [ ] T12 · `web/src/features/members/api.ts`: `useMemberHistory(memberId, page)`; `web/src/features/members/lib/historyPhrase.ts`: frase por `action` y `table_name` ("Ana P. creó el socio", "Juan R. editó teléfono y notas", "Juan R. mostró el documento", "Ana P. vendió una membresía", "Ana P. registró un pago", "Ana P. anuló un pago"), con nombre e inicial del apellido; `web/src/features/members/components/MemberHistoryTab.tsx` sobre `HistoryAside` (US-066): orden descendente, paginado, carga, vacío y error — 2,5 h
- [ ] T13 · `web/src/features/members/components/MemberHistoryTab.test.tsx` y `historyPhrase.test.ts`: frases por acción y tabla, orden, ausencia de valores — 1 h

### DevOps
- [ ] T14 · Regenerar `docs/openapi.json` y tipos del front; anotar en el ADR de la serialización canónica (US-119) la clave `subject_member_id` — 0,5 h

### Seguridad
- [ ] T15 · Revisión: coach ve el historial del socio (permitido por la épica) pero nunca `before`/`after`; sin IDOR adicional (admin y coach ven todos los socios); `subject_member_id` no es dato sensible — 0,5 h

## Orden de ejecución
1. Aprobación de la propuesta A por el orquestador
2. T8 (puras en rojo)
3. T1
4. T2
5. T3
6. T9 (service en rojo)
7. T4, T5
8. T6
9. T10 (router en rojo)
10. T7
11. T11
12. T12, T13
13. T14
14. T15

## Dependencias técnicas
- US-015 · Tabla de auditoría y cadena de hashes: recibe la columna y la regla de `canonical` (propuesta A).
- US-016 · Hook de auditoría: lee `__audit_subject__`.
- US-074 · Mostrar dato sensible auditado: pasa `subject_member_id` al `record` del `reveal`.
- US-095 · Registrar pago: columna `payments.member_id`.
- US-084 · Vender membresía: `Membership.__audit_subject__`.
- US-102 / US-103 · Consultar y detallar auditoría: `diff`, `auth.service.names_for`.
- US-073 · Ver ficha del socio y US-066 · `HistoryAside` (front).
- US-069 · `members.service.ensure_exists`.

## Endpoints
- `GET /api/v1/members/{id}/audit` — roles: admin, coach

## Riesgos
- Si la propuesta A llega después de que `0002_audit_log` tenga datos, la columna entra por `0014` y las filas viejas no tienen sujeto — mitigación: decidir antes de implementar US-015 (está en la ruta crítica).
- Un modelo auditado nuevo con relación a un socio que olvide `__audit_subject__` no aparecería en el historial — mitigación: T11 mantiene la lista de modelos que deben declararlo.
- `MembershipFreeze` (US-089) no tiene `member_id`; sus congelaciones aparecen en el historial solo por la entrada `update` de la membresía que extiende `end_date` — mitigación: aceptable para N-31 (que nombra `members`, `memberships` y `payments`); si se quiere la fila de congelación, `0009_membership_freezes` agrega `member_id`.
- Front condicionado a D1.

## Estimación
- Backend: 7 h (T1 a T7)
- Front: 2,5 h (T12)
- Pruebas: 6,5 h (T8 a T11 y T13)
- DevOps / seguridad: 1 h (T14, T15)
- **Total: 17 h**
- Desvío sobre la referencia de 3 puntos (10 a 15 h): la ampliación de N-31 y la propuesta A (columna, hook y tres modelos) agregan trabajo que la historia no contemplaba.

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/audit/test_history_fields.py -q`
- [ ] `cd api && uv run pytest tests/audit/test_member_history.py -q`
- [ ] `cd api && uv run pytest tests/members/test_router_member_audit.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` (si la columna entra por `0014_audit_subject_member`)
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/members/components/MemberHistoryTab.test.tsx src/features/members/lib/historyPhrase.test.ts`
- [ ] `SELECT table_name, action FROM audit.audit_log WHERE subject_member_id = '<id>' ORDER BY seq DESC` devuelve filas de `members`, `memberships` y `payments` del socio, y `curl /api/v1/members/<id>/audit` con token de coach devuelve las mismas sin `before`/`after`
- [ ] `cd api && uv run python -m app.cli verify-audit` sigue devolviendo 0 después de generar el historial
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.audit --cov=app.modules.members --cov-fail-under=80`
