# US-029 · Bitácora crypto_ops por lote — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-02-bus-de-criptografia/US-029-bitacora-crypto-ops-por-lote.md`
- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context / módulo:** Crypto (`api/src/app/core/crypto/oplog.py`, `api/src/app/core/crypto/bus.py`, tabla `crypto.crypto_ops`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**ARCHITECTURAL_GAP_DETECTED**

La bitácora necesita el actor de la operación, y hoy el único lugar previsto para él es el `contextvar` `current_actor` de `core/audit.py` (US-016). Si `core/crypto` lo importara de ahí, dependería de `core/audit`, que a su vez depende de `core/crypto` para el SHA-256 de la cadena (DECISIONES N-06): ciclo de imports. La estructura de `CLAUDE.md` no prevé un lugar neutral para el contexto de la petición. El resto de la historia está resuelto.

## Resumen

Cada operación del bus (`encrypt`, `decrypt`, `index`, `sign`, `verify`, `wrap`, `unwrap`, `rotate`, `export`) se acumula en un buffer de la unidad de trabajo y se inserta en `crypto_ops` en la misma transacción, justo antes del commit. Dentro de `with bus.batch(...)` las operaciones exitosas se agregan en una fila por (verbo, `data_class`, `key_id`, versión, propósito) con `batch_id` y `count`. Los errores siempre van en fila propia con su `record_id` y sobreviven al rollback del negocio porque se escriben en una conexión aparte. El actor sale de un `contextvar` neutral en `core/context.py`.

## Correcciones aplicadas por DECISIONES.md

- Criterio 4: "en CLI y worker `user_id` es `NULL`" → `user_id` es siempre un usuario: el de la petición, el de `--as <email>` en CLI o `SYSTEM_USER_ID` en worker, bootstrap y CLI sin `--as`; la columna es `NOT NULL` (US-024): corregido por DECISIONES N-15.
- El descifrado para enmascarar la ficha → fila `verb = decrypt`, `purpose = mask`: corregido por DECISIONES N-01. Los propósitos `notify` y `auth_link` (N-21), `reveal` (US-074) y `export` (US-138) usan la misma columna.
- Verbos → se suma `export` (`cli export-kek`, US-116); `count` en las filas de lote: confirmado por DECISIONES N-05.
- `digest` (N-06) no deja fila: no usa llave (ver US-027).
- La historia dice que el registro de errores va "en una transacción aparte o se reintenta" → se fija la transacción aparte (conexión propia del mismo engine en `after_soft_rollback`); supuesto de la historia aceptado sin cambio de DECISIONES.

## Validación contra el dominio

- `CryptoOp` append-only (02_domain_model 2.13; trigger de US-024): quién, verbo, `data_class`, `key_id`, versión, `record_id`, resultado y `batch_id`, más `count` y `purpose` por DECISIONES.
- RN-13: el descifrado deja evidencia; la fila nunca contiene material, texto en claro ni blob.
- Riesgo de EP-02 "costo por operación en listas grandes": las listas no descifran (N-01) y los lotes agregan.
- Función pura: `aggregate_ops(ops) -> list[OpRow]` (agrupa exitosas por la llave de agregación, conserva errores individuales).
- Sin eventos.

## Validación contra la arquitectura

- `core/crypto` no puede depender de `app.modules` ni de `core/audit`; hoy el actor vive en `core/audit.py` (US-016) y `core/audit` importa `core/crypto` (N-06). Ver la brecha.
- La escritura en la misma transacción usa eventos de sesión de SQLAlchemy registrados al importar `core/crypto/oplog.py` sobre `sqlalchemy.orm.Session`; `core/db.py` no importa `core/crypto`.
- Los módulos no escriben en `crypto_ops`: lo hace el bus. Pasan propósito y lote por argumentos con nombre opcionales (`decrypt(blob, aad, *, purpose=None)`, `blind_index(dc, value, *, record_id=None)`), compatibles con el contrato de `05_service_design.md`.
- Sin router (la consulta llega en US-144), sin rol, sin paginación.

## Preguntas abiertas

- Brecha: no existe en la estructura de `CLAUDE.md` un lugar neutral de `core/` para el contexto de la unidad de trabajo (actor, lote del comando). Si `current_actor` queda en `core/audit.py`, el grafo es `core/crypto/oplog` → `core/audit` → `core/crypto/digest`, y `core/audit` también arrastra `core/db`, con lo que `core/crypto/models` → `core/db` → `core/audit` → `core/crypto` cierra un ciclo.
- Propuesta:
  - Crear `api/src/app/core/context.py`, que solo importa la biblioteca estándar, con `SYSTEM_USER_ID: Final[UUID] = UUID("00000000-0000-0000-0000-000000000001")`, `current_actor: ContextVar[UUID | None]`, `current_batch: ContextVar[UUID | None]`, `get_actor() -> UUID` (lanza si falta), `actor_scope(user_id)` y `batch_scope(batch_id)` como administradores de contexto.
  - US-034 fija el actor con `core.context.actor_scope`; US-016 lee `core.context.get_actor()` en vez de definir su propio `contextvar`; CLI y worker abren `actor_scope(SYSTEM_USER_ID o el usuario de --as)` y `batch_scope(uuid4())` por comando.
  - `core/audit.py` importa `core.crypto.digest` (archivo hoja de US-027), no `core.crypto.bus`, para no arrastrar keyring ni modelos (precisa la letra de N-06, que dice `core.crypto.bus.digest`; `bus.digest` sigue existiendo como reexportación para los demás).
  - Prueba nueva `api/tests/architecture/test_core_import_graph.py` que construye el grafo de imports de `app.core` y falla si `core/crypto` importa `core/audit` o `app.modules`, si `core/context.py` importa algo de `app`, o si hay un ciclo entre paquetes de `core`.
  - Se actualiza la estructura de `CLAUDE.md` (sección "Estructura del repositorio") con `core/context.py` en el gate.

## Tareas

### Migración Alembic
- No aplica (columnas en `0003_crypto`, US-024).

### Models
- No aplica (usa `CryptoOp` de US-024).

### Service
- [ ] T1 · `api/src/app/core/context.py` según la propuesta de la brecha (`SYSTEM_USER_ID`, `current_actor`, `current_batch`, `get_actor`, `actor_scope`, `batch_scope`) — 1,5 h
- [ ] T2 · `api/src/app/core/crypto/oplog.py`: `OpEntry` (dataclass: `verb`, `data_class`, `key_id`, `key_version`, `record_id`, `purpose`, `result`); `record(...)` que añade al buffer del `contextvar` de la unidad de trabajo con `user_id = get_actor()` y `batch_id = current_batch` y deriva `record_id` del AAD cuando es un UUID canónico; valida `purpose` contra `OpPurpose` — 2 h
- [ ] T3 · Función pura `aggregate_ops(entries) -> list[OpRow]` en `oplog.py`: agrupa las `ok` por (`verb`, `data_class`, `key_id`, `key_version`, `purpose`) con `count` y `record_id = NULL`; cada `error` queda en fila propia con `count = 1` y su `record_id` — 1 h
- [ ] T4 · `bus.batch(verb, data_class) -> ContextManager[BatchHandle]`: genera `batch_id`, desvía las operaciones al lote y al cerrar empuja `aggregate_ops` al buffer; anidado dentro de `batch_scope` del comando reutiliza ese `batch_id` — 1,5 h
- [ ] T5 · Persistencia en la misma transacción: listener `before_commit` en `sqlalchemy.orm.Session` que vacía el buffer con un `INSERT ... VALUES` múltiple sobre `session.connection()`; si falla, el commit falla (la operación de negocio no queda sin rastro, coherente con US-074) — 2 h
- [ ] T6 · Persistencia tras rollback: listener `after_soft_rollback` que escribe en una conexión aparte (`session.get_bind().begin()`) las filas `error` y las `decrypt` del buffer (el dato estuvo en claro en memoria) y descarta `encrypt` e `index` (nunca llegaron a la base); `flush_standalone(engine)` asíncrono para operaciones sin sesión (arranque, CLI) — 3 h
- [ ] T7 · Cableado de verbos: `bus.encrypt`, `decrypt`, `blind_index`, `sign`, `verify` (US-025 a US-027), `keyring.load_all` (`unwrap` por llave, en un lote de arranque) y `bootstrap.ensure_keys` (`wrap`) llaman a `oplog.record`; `purpose` y `record_id` como argumentos con nombre opcionales — 1,5 h
- [ ] T8 · Cableado de la unidad de trabajo en la capa de aplicación (no en `core/db.py`): dependencia global en `api/src/app/main.py` que llama `keyring.refresh_if_stale` al abrir la sesión de la petición; `actor_scope` y `batch_scope` en el envoltorio común de comandos de `cli.py` y en el runner de jobs de `worker/main.py` — 1,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T9 · `api/tests/crypto/test_oplog_aggregate.py`: 500 `decrypt` `ok` de la misma llave dan una fila con `count = 500`; mezcla de dos `key_id` da dos filas; dos errores dan dos filas con su `record_id`; `purpose` distinto separa filas — 1 h

### Tests de service con PostgreSQL
- [ ] T10 · `api/tests/crypto/test_oplog.py`: cifrar un campo con actor fijado deja exactamente una fila `verb = encrypt` con `data_class`, `key_id`, `key_version`, `record_id`, `result = ok` y el `user_id` del actor; 500 descifrados en `bus.batch` dejan una fila con `batch_id` y `count = 500`; un `decrypt` con AAD equivocado seguido de rollback deja una fila `result = error` con el `record_id`; ninguna fila contiene el blob ni el texto (búsqueda en `row_to_json`); sin actor el commit falla con "falta el actor"; en un comando con `batch_scope` todas las filas comparten `batch_id`; `UPDATE` sobre `crypto_ops` falla (trigger de US-024) — 3,5 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T11 · `api/tests/architecture/test_core_import_graph.py` (propuesta de la brecha): grafo de imports de `app.core` por AST; falla si `core/crypto` importa `core/audit` o `app.modules`, si `core/context.py` importa algo de `app` o si hay ciclos — 1,5 h

### Front
- No aplica.

### DevOps
- No aplica.

### Seguridad
- [ ] T12 · Revisión: ninguna fila contiene material, blob ni valor; el mensaje de error no se persiste (solo `result`); la conexión aparte del rollback no reutiliza la transacción abortada; el actor no se puede falsear desde el cliente (lo fija `current_user`) — 1 h

## Orden de ejecución
1. Aprobar la propuesta de la brecha (`core/context.py`)
2. T1
3. T9 (prueba pura), luego T3
4. T10 escrita, luego T2, T4, T5 y T6
5. T7, T8
6. T11, T12

## Dependencias técnicas
- US-024 · Tablas crypto: `crypto_ops` con `count`, `purpose`, `user_id NOT NULL` y trigger append-only.
- US-025 · Cifrado AES-GCM: puntos de registro del bus y keyring.
- US-016 · Hook de auditoría (EP-01): debe leer el actor de `core/context.py` en vez de definir `current_actor` en `core/audit.py`.
- US-034 · current_user y require_role (EP-03): debe fijar el actor con `core.context.actor_scope`.
- US-015 · Cadena de hashes (EP-01): debe importar `core.crypto.digest`, no `core.crypto.bus`.

## Endpoints
- Ninguno.

## Riesgos
- Si EP-01 implementa `current_actor` en `core/audit.py` antes de aprobar la propuesta, habrá que moverlo — impacto: retrabajo en US-016 y US-034 — mitigación: la brecha se presenta en el gate antes del sprint de núcleo.
- Un fallo al insertar en `crypto_ops` tumba la operación de negocio — mitigación: es intencional (nada sale en claro sin rastro); `INSERT` múltiple por commit reduce la probabilidad.
- La conexión aparte en rollback consume una conexión extra del pool — mitigación: solo cuando hay errores o descifrados en una transacción revertida; pool con margen en `core/db.py`.

## Estimación
- Backend: 14 h
- Front: 0 h
- Pruebas: 6 h
- DevOps / seguridad: 1 h
- **Total: 21 h**

La suma supera el rango de 3 puntos (10-15 h) por el trabajo que agrega la brecha (`core/context.py`, cableado de la unidad de trabajo y la prueba del grafo de imports); sin la brecha serían unas 15 h.

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/crypto/test_oplog_aggregate.py tests/crypto/test_oplog.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Tras crear un registro de prueba con cinco campos cifrados: `SELECT verb, data_class, count FROM crypto.crypto_ops ORDER BY at DESC LIMIT 8` muestra cinco `encrypt` y tres `index`, todas con `user_id` no nulo
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.crypto --cov=app.core.context --cov-fail-under=80`
