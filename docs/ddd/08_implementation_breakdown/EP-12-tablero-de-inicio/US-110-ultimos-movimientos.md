# US-110 · Últimos movimientos — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-12-tablero-de-inicio/US-110-ultimos-movimientos.md`
- **Épica:** EP-12 · Tablero de inicio
- **Bounded context / módulo:** Dashboard (`api/src/app/modules/dashboard/`), con lectura de Audit (`api/src/app/modules/audit/service.py`), Members, Plans, Memberships y Auth por sus services
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**NEEDS_REFINEMENT**

Q10 fija la fuente (últimas 10 entradas de auditoría de `members`, `memberships` y `payments`) y la forma de armarlo. Pero quedan dos supuestos que cambian contrato y comportamiento y que DECISIONES.md no resuelve. Primero, las frases empiezan con el nombre de quien actuó ("Ana P."), y `auth.users` no tiene nombre (solo `email`, US-041). Segundo, el job diario de vencimientos (US-094) escribe una entrada `update` por cada membresía que cambia de estado, y cada mañana llenaría los 10 puestos con transiciones automáticas en vez de lo que pasó en recepción.

## Resumen

Se agrega `audit.service.recent(tables, limit, exclude_user_ids)` (lectura por el índice `(table_name, seq DESC)` de la migración `0002_audit_log`) y la función pura `dashboard.movement_phrase(entry, names) -> str`. `dashboard.service.summary` llena `last_movements` con `{ seq, at, phrase, table_name, record_id, member_id }`: pide las entradas a `audit.service`, junta los ids y resuelve nombres en lote con `members.service.names_for`, `plans.service.names_for`, `auth.service.names_for` y `memberships.service.refs_for`. Ninguna frase usa un campo cifrado. En el front, el componente `LastMovements` muestra la frase, la hora relativa de Bogotá y el enlace a la ficha del socio.

## Correcciones aplicadas por DECISIONES.md

- La historia supone un catálogo de frases propio (Q10 solo da dos ejemplos) → se acepta el catálogo del criterio 2 como contrato de `movement_phrase`: aceptado por DECISIONES Q10 (amplía los ejemplos sin cambiar la fuente).
- La historia menciona el índice `(table_name, seq DESC)` "en migración propia si la medición lo pide" → no hay migración propia; el índice ya está en `0002_audit_log` (US-015) según la numeración canónica.
- Supuesto de la historia de que el socio de un pago se obtiene vía `memberships.service` → se hace con `memberships.service.refs_for(membership_ids)`, en lote y en solo lectura, permitido para Dashboard por el mapa de contextos.
- La acción `download` (N-08) también queda excluida del bloque, igual que `reveal`, `login`, `export` y `verify`: corregido por DECISIONES N-08 (la acción existe desde v0.1 en el CHECK de `audit_log`).

## Validación contra el dominio

- `AuditEntry` (2.12) se lee, nunca se escribe. El filtro por acción deja pasar solo `insert`, `update` y `delete`.
- RN-13: las frases usan solo `first_name` y la inicial de `last_name` (en claro por diseño), nombres de plan y `amount_cop`. Los blobs `apx1.` de `before` y `after` nunca salen del service: `movement_phrase` recibe una vista reducida de la entrada (`action`, `table_name`, campos permitidos de `after` y `before`), no el JSON completo.
- RN-01: el monto sale de `after.amount_cop` (entero) y se formatea `$ 120.000` en el servidor con una función pura `format_cop(int) -> str` del módulo.
- Las frases de membresía usan `member_id` y `plan_id` del `after`. Las de pago usan `after.membership_id` y `memberships.service.refs_for`. La anulación de pago es un `update` con `before.voided = false` y `after.voided = true`. La baja de socio es un `update` que pone `deleted_at`.
- Función pura: `movement_phrase(entry: MovementSource, names: NameBook) -> str`. Nombre corto: `short_name("Laura", "Gómez Restrepo") -> "Laura G."`.
- Discrepancia señalada: el aggregate `User` no tiene nombre visible (2.11). La frase "Ana P. registró..." lo necesita (pregunta 1).

## Validación contra la arquitectura

- Módulo dueño: `dashboard`, solo lectura y sin `models.py`. Componer los services de audit, members, plans, memberships y auth es una composición de lectura de Dashboard, permitida por el mapa de contextos (contexto 14 y "Dashboard → todos los de negocio").
- `audit.service.recent` vive en `modules/audit/service.py`, que es el dueño de la lectura de `core/audit.py` (05, sección 2: "models viven en core/audit.py"). `dashboard` nunca importa `core.audit` ni ningún `models`; lo verifica T15.
- Contratos que se piden a otros módulos (sin leer sus tablas):
  - `members.service.names_for(ids) -> dict[UUID, PersonName]`, que incluye socios dados de baja para poder escribir "dio de baja a Laura G." (US-069/US-070).
  - `plans.service.names_for(ids) -> dict[UUID, str]`, que incluye planes dados de baja (US-078).
  - `auth.service.names_for(user_ids) -> dict[UUID, str]`, que devuelve "Sistema" para `SYSTEM_USER_ID` (N-15) (US-041).
  - `memberships.service.refs_for(membership_ids) -> dict[UUID, MembershipRef(member_id, plan_id)]`, contrato nuevo que se pide a EP-09.
- Bus de criptografía: no se usa ni se descifra nada.
- Lint banned-api: sin cambios.
- Rol: el campo viaja en `GET /dashboard` con `require_role("admin", "coach")`. El coach no tiene acceso a `GET /audit` (solo admin, US-102). Ve aquí solo frases sin datos personales, que es lo que Q10 autoriza para el tablero.
- Paginación: no aplica; `limit` fijo de 10 dentro del service (máximo permitido en `recent`: 50).
- Auditoría: la lectura no se audita.

## Preguntas abiertas

- Pregunta 1 (contrato de `auth` y migración `0004_auth`). ¿Se agrega a `auth.users` una columna `display_name` (texto de 1 a 80 caracteres, obligatoria al crear usuarios desde US-047, con migración en tres pasos si ya hay usuarios) para escribir "Ana P." en las frases? Alternativa por defecto que se propone: sí, `display_name` en `0004_auth` antes de que tenga datos, con el valor "Sistema" para `SYSTEM_USER_ID`. Si se rechaza, se usa la parte local del correo ("ana.perez registró un pago..."), sin cambio de esquema.
- Pregunta 2 (comportamiento de `audit.service.recent`). ¿Se excluyen del bloque las entradas cuyo `user_id` es `SYSTEM_USER_ID` (job de vencimientos, seed e importación sin `--as`), para que las transiciones automáticas de cada mañana no tapen lo que pasó en recepción? Alternativa por defecto que se propone: sí, `recent` recibe `exclude_user_ids=[SYSTEM_USER_ID]`. La activación por cobertura (un `update` de `status` hecho en la misma transacción del pago, con el usuario de recepción) se muestra como "La membresía Plan Mensual de Laura G. quedó al día" en lugar de la frase genérica.

## Tareas

### Migración Alembic
- No aplica (usa el índice `(table_name, seq DESC)` de `0002_audit_log`). Si la pregunta 1 se aprueba, la columna `display_name` va en `0004_auth` (US-041), no aquí.

### Models
- No aplica.

### Service
- [ ] T1 · `modules/audit/service.py`: `async def recent(session, tables: Sequence[str], limit: int, *, actions=("insert", "update", "delete"), exclude_user_ids: Sequence[UUID] = ()) -> list[AuditEntryView]`, con `limit` de 1 a 50, una consulta `WHERE table_name = ANY(:tables) AND action = ANY(:actions) AND user_id <> ALL(:excl) ORDER BY seq DESC LIMIT :limit`; devuelve una vista inmutable (dataclass congelada) con `seq`, `at`, `user_id`, `action`, `table_name`, `record_id` y solo las llaves permitidas de `before`/`after` (`member_id`, `plan_id`, `membership_id`, `amount_cop`, `voided`, `deleted_at`, `status`) — 2 h
- [ ] T2 · `modules/dashboard/service.py`: funciones puras `short_name(first: str, last: str) -> str`, `format_cop(amount: int) -> str` y `movement_phrase(entry: AuditEntryView, names: NameBook) -> str` con el catálogo del criterio 2 (alta, edición, baja de socio; venta y anulación de membresía; pago y anulación de pago; activación por cobertura si se aprueba la pregunta 2; frase genérica "X modificó <entidad> de Laura G.") — 2 h
- [ ] T3 · `modules/dashboard/service.py`: `async def last_movements(session) -> list[MovementOut]` que llama a `audit.service.recent(["members", "memberships", "payments"], 10, exclude_user_ids=...)`, junta ids, llama una sola vez a cada `names_for` y a `memberships.service.refs_for`, arma `NameBook` y aplica `movement_phrase`; si un nombre falta usa "un socio" o "un plan" sin fallar; `summary` (US-108) lo incluye en `last_movements` — 1,5 h
- [ ] T4 · Contratos pedidos a otros módulos, coordinados con sus dueños: `memberships.service.refs_for` (EP-09, consulta única por `id = ANY(...)`) y `auth.service.names_for` con "Sistema" para `SYSTEM_USER_ID`; si EP-07 y EP-08 no traen `names_for` con dados de baja incluidos, se agrega el parámetro `include_deleted=True` en esos services — 1,5 h

### Schemas
- [ ] T5 · `modules/dashboard/schemas.py`: `MovementOut` con `seq: int`, `at: datetime` (UTC), `phrase: str`, `table_name: Literal["members", "memberships", "payments"]`, `record_id: UUID` y `member_id: UUID | None` (para el enlace a la ficha); `DashboardOut.last_movements: list[MovementOut]` con máximo 10 elementos — 0,5 h

### Router
- No aplica (el campo viaja en `GET /dashboard` de US-108).

### Tests unitarios puros
- [ ] T6 · `api/tests/dashboard/test_movement_phrase.py`: una prueba por cada frase del criterio 2 y por la genérica; `short_name` con apellido compuesto ("Gómez Restrepo" → "G.") y con tildes ("Ángela Ñúñez" → "Ángela Ñ."); `format_cop(120000) == "$ 120.000"`; una entrada cuyo `after` trae un blob `apx1.` en `document` no lo incluye en la frase (la vista reducida lo descarta) — 2 h

### Tests de service con PostgreSQL
- [ ] T7 · `api/tests/audit/test_recent.py`: filtra por tablas y acciones (las entradas `reveal`, `login`, `export`, `verify` y `download` y las de `plans` o `users` no aparecen), respeta `limit` y el orden por `seq` descendente, excluye `SYSTEM_USER_ID` cuando se pide, y con 100.000 entradas responde en menos de 50 ms con `EXPLAIN` que usa el índice `(table_name, seq DESC)` (marcado `slow`) — 2 h
- [ ] T8 · `api/tests/dashboard/test_last_movements.py`: escenario del BDD (venta de Plan Mensual a Laura Gómez y pago de 120.000 de Juan Ruiz por Ana Pérez) produce las frases esperadas, el más reciente primero; con 3 entradas devuelve 3; sin entradas, lista vacía; un `reveal` del documento no aparece; la respuesta serializada completa no contiene ningún valor de documento, teléfono, correo, fecha de nacimiento ni contacto de emergencia de los socios creados ni ninguna cadena `apx1.` — 2 h

### Tests de router
- [ ] T9 · `api/tests/dashboard/test_router.py`: `last_movements` presente con admin y coach; 403 para `member` (se reutiliza la prueba de rol de US-108 y se agrega la verificación del campo) — 0,5 h

### Tests de arquitectura
- [ ] T10 · `api/tests/architecture/test_read_modules.py` (de US-108): se agrega que `app.modules.dashboard` no importa `app.core.audit`; deben seguir verdes `test_no_cross_models.py` y `test_banned_imports.py` — 0,5 h

### Front
- [ ] T11 · `web/src/features/dashboard/components/LastMovements.tsx`: lista con la frase, la hora relativa en Bogotá ("hace 5 min", con la hora exacta en `title` y en texto accesible) y enlace a `/socios/:id` cuando `member_id` existe; estados de carga, vacío ("Todavía no hay movimientos") y error; se integra en `HomePage` de US-109; sin colores literales — 2 h
- [ ] T12 · `web/src/features/dashboard/components/LastMovements.test.tsx`: lista con 10 elementos en orden, vacío, enlace a la ficha y hora relativa con reloj falso — 1 h

### DevOps
- [ ] T13 · Regenerar `docs/openapi.json` con `MovementOut` — 0,5 h

### Seguridad
- [ ] T14 · Revisión de exposición: el coach ve frases de acciones de otros usuarios sin datos personales; ningún campo de la vista reducida de T1 puede traer un blob; el log no imprime frases — 0,5 h
- [ ] T15 · Revisión de que `audit.service.recent` no acepta tablas fuera de una lista blanca (`members`, `memberships`, `payments`, `plans`, `users`, `settings_sections`) para que un uso futuro no exponga `crypto_*` — 0,5 h

## Orden de ejecución

1. Cerrar las preguntas 1 y 2 en el gate (cambian `auth.service.names_for` y la firma de `recent`).
2. T6 (en rojo), luego T2.
3. T7 (en rojo), luego T1 y T15.
4. T4 (contratos con EP-07, EP-08, EP-09 y EP-04).
5. T5, T8 (en rojo), luego T3.
6. T9 y T10.
7. T13, T12 (en rojo), luego T11.
8. T14.

## Dependencias técnicas

- US-108 · Contrato del tablero: campo `last_movements` y `dashboard.service.summary`.
- US-102 · Consultar auditoría: `modules/audit/service.py` existe y es dueño de la lectura de `core/audit.py`.
- US-015 · Tabla de auditoría: índice `(table_name, seq DESC)` en `0002_audit_log` y CHECK de `action` con `download`.
- US-016 · Hook de auditoría: `after` guarda las columnas de la fila (incluidas `member_id`, `plan_id`, `membership_id`, `amount_cop`, `voided`, `deleted_at`).
- US-069 / US-070 · `members.service.names_for(ids)` (con dados de baja).
- US-078 · `plans.service.names_for(ids)`.
- US-041 · `auth.service.names_for(user_ids)` y, si se aprueba la pregunta 1, la columna `display_name` en `0004_auth`.
- US-091 o US-092 · `memberships.service.refs_for(membership_ids)` (contrato nuevo pedido a EP-09).
- US-094 · Job de vencimientos: escribe con `SYSTEM_USER_ID` (N-15), base de la pregunta 2.
- US-109 · Página `HomePage` donde se monta el bloque.

## Endpoints

- `GET /api/v1/dashboard` — roles: admin, coach

## Riesgos

- Ruido de transiciones automáticas: sin la exclusión de la pregunta 2, cada mañana el bloque muestra solo cambios del worker — mitigación: la alternativa por defecto excluye `SYSTEM_USER_ID`.
- Fuga de datos cifrados por la frase genérica: un `after` de `members` trae blobs — mitigación: la vista reducida de T1 solo deja pasar llaves de una lista blanca y T8 busca `apx1.` en la respuesta.
- Nombres actuales y no históricos: si un socio cambia de nombre, frases viejas muestran el nombre nuevo — mitigación: se acepta; el tablero muestra los últimos 10 movimientos, no un historial.
- Contratos `names_for` y `refs_for` definidos en otras épicas con otra firma — mitigación: T4 coordina las firmas y se listan como contradicción a revisar en el resumen de la épica.
- Front condicionado a D1.
- Estimación por encima del rango de 3 puntos (10 a 15 h): la suma de tareas da 20 h porque la historia coordina contratos en cuatro módulos (members, plans, memberships, auth) y agrega una consulta nueva en audit — mitigación: si los `names_for` llegan listos de EP-04, EP-07 y EP-08, T4 baja a 0,5 h.

## Estimación

- Backend: 8 h
- Front: 2 h
- Pruebas: 8 h
- DevOps / seguridad: 2 h
- **Total: 20 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/dashboard -q`
- [ ] `cd api && uv run pytest tests/audit/test_recent.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/dashboard`
- [ ] Con datos de demo: `curl -s -H "Authorization: Bearer <token coach>" http://localhost/api/v1/dashboard | jq '.last_movements | length'` devuelve un número entre 0 y 10, y `... | grep -c "apx1\."` devuelve 0
- [ ] `EXPLAIN` de la consulta de `recent` usa el índice `(table_name, seq DESC)`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.dashboard --cov=app.modules.audit --cov-fail-under=80`
