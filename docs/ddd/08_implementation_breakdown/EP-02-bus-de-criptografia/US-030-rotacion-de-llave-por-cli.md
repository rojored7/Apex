# US-030 · Rotación de llave por CLI — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-02-bus-de-criptografia/US-030-rotacion-de-llave-por-cli.md`
- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context / módulo:** Crypto (`api/src/app/core/crypto/service.py`, `api/src/app/core/crypto/discovery.py`, `api/src/app/cli.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 8

## Estado de preparación

**NEEDS_REFINEMENT**

El flujo de rotación, el lote de 500, la reanudación, la exclusión de rotaciones concurrentes y la rotación de índice con `--index` (DECISIONES N-07) están resueltos. Queda un supuesto que cambia el comportamiento y que ningún documento decide: `audit.audit_log` guarda en `before` y `after` los blobs de los campos cifrados (US-016, US-028) y es inmutable, así que nunca se pueden recifrar. Si esos blobs cuentan como "dato cifrado con la llave", la llave anterior no podría pasar nunca a `retired`; si no cuentan, ese historial queda ilegible al retirarla.

## Resumen

`cli rotate-key <data_class> --reason "<motivo>" [--index] [--as <email>]` crea una DEK nueva `active` (versión + 1), pasa la anterior a `decrypt_only` en la misma transacción, crea un `CryptoJob(kind = rotate)` y recifra por lotes de 500 filas, cada lote en su transacción, todas las columnas `Encrypted` de esa clase descubiertas desde los metadatos de SQLAlchemy. El job es reanudable (procesa filas cuyo blob no lleva el `key_id` activo) y excluyente por un candado consultivo de PostgreSQL. Solo cuando un último conteo bajo candado da cero filas con la llave anterior, esta pasa a `retired`. Con `--index` se rota también la llave del índice ciego y se recalculan todos los `_idx` en una sola transacción. El CLI escribe la auditoría con el motivo.

## Correcciones aplicadas por DECISIONES.md

- Supuesto de la historia: la llave `index` solo se rota con `--index` explícito → confirmado por DECISIONES N-07.
- Actor de la rotación → el usuario de `--as <email>` o, sin él, `SYSTEM_USER_ID`; ese usuario va a `crypto_ops.user_id`, a `crypto_keys.rotate_by` (si la pregunta de US-024 se resuelve como usuario) y a la auditoría: corregido por DECISIONES N-15.
- `CryptoJob.kind`: la historia nombra `rotate` y `reencrypt` → un comando `rotate-key` crea un único job `kind = rotate` que cubre el recifrado; `reencrypt` queda para recifrar sin rotar (EP-18) y `rewrap` para US-199: coherente con DECISIONES N-05.
- Criterio 10 "acción registrada en `audit_log` sobre `crypto_keys`" choca con US-024 criterio 9 (las tablas crypto no son `__audited__`) → la entrada la escribe el CLI con `audit.record` explícito (acción `update`, tabla `crypto.crypto_keys`, `record_id` de la llave nueva, motivo en `after`), no el hook. Así `core/crypto` no depende de `core/audit` (brecha de US-029, DECISIONES N-06 fija la dirección `core/audit` → `core/crypto`).

## Validación contra el dominio

- `CryptoKey`: una sola `active` por (`purpose`, `data_class`) (índice parcial de US-024); la anterior queda `decrypt_only` hasta que el job termina; nunca se borra (RN-14); material en claro nunca persistido.
- `CryptoJob`: progreso `total`/`done`, estados `pending`, `running`, `done`, `failed`.
- `CryptoOp`: lotes con `batch_id` y `count`, más una fila `rotate`.
- Regla de datos 8: la migración de datos es un comando de `cli.py`, idempotente (reanudable sin doble recifrado) y auditado.
- Función pura `next_key_state(current_state, job_status) -> state`: `active` → `decrypt_only` al iniciar, `decrypt_only` → `retired` con job `done`, `active` → `retired` solo para llaves `index` en `--index`; `retired` → cualquier otro estado prohibido. Coincide con 2.13.
- Discrepancia que origina la pregunta: el modelo dice "la anterior queda `decrypt_only` hasta que el job termine y la retire", sin considerar las copias inmutables del blob en `audit_log`.

## Validación contra la arquitectura

- El servicio vive en `core/crypto/service.py` (previsto en `05_service_design.md`: "rotate, reencrypt por lotes"). No importa `app.modules`: descubre tablas y columnas recorriendo `Base.metadata` en busca de columnas `Encrypted(data_class)` y las cruza con `registry.columns` (US-025). El CLI importa la aplicación para poblar los metadatos.
- El recifrado usa SQL de Core sobre el objeto `Table` (`SELECT ... FOR UPDATE` y `UPDATE` de la columna), así no dispara el hook de auditoría por fila ni importa modelos de otro módulo; conserva `updated_at` (`updated_at = updated_at`) porque no es un cambio de negocio.
- La auditoría y la resolución de `--as` (vía `auth.service`) ocurren en `cli.py`, capa de aplicación; `core/crypto` no llama a `core/audit` ni a módulos.
- Concurrencia con el API: el listener de US-028 toma `FOR SHARE` sobre la llave activa antes de cifrar; la transacción que pasa la llave a `decrypt_only` espera a esas escrituras, así ninguna fila nueva queda con la llave anterior después de rotar. El API carga la llave nueva con `refresh_if_stale` (US-025, US-029).
- Sin router (la pantalla es US-145), sin rol HTTP, sin paginación.

## Preguntas abiertas

- Pregunta: los blobs de campos cifrados que guarda `audit.audit_log` en `before` y `after` (inmutables, nunca se recifran), ¿cuentan como "dato cifrado con la llave anterior" para decidir si esa llave puede pasar a `retired`?
- Alternativa propuesta por defecto: no cuentan. La condición de retiro es "cero filas con la llave anterior en las columnas `Encrypted` de las tablas de negocio" (el esquema `audit` se excluye). La llave `retired` conserva su `wrapped_material` (RN-14) pero el bus no la carga ni descifra con ella; el historial de la ficha (US-106) muestra "valor cifrado modificado" sin descifrar. Es lo que se espera tras una sospecha de filtración. La alternativa contraria (que la llave nunca se retire mientras haya auditoría que la use) deja `decrypt_only` como estado final y vuelve inútil `retired`.

## Tareas

### Migración Alembic
- No aplica (usa `0003_crypto`; el índice parcial de un job en curso por clase lo crea US-024).

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `next_key_state(current: KeyState, job_status: JobStatus | None, purpose: KeyPurpose) -> KeyState` en `api/src/app/core/crypto/service.py`, con `InvalidTransition` para `retired` → cualquiera y `decrypt_only` → `active` — 1,5 h
- [ ] T2 · `api/src/app/core/crypto/discovery.py`: `encrypted_columns(metadata, data_class) -> list[ColumnRef]` (tabla, columna, `BlindIndexed` asociado) recorriendo `Base.metadata.tables`; falla si una columna esperada por `registry.columns` no existe o no es `Encrypted` de esa clase; excluye el esquema `audit` — 2 h
- [ ] T3 · `service.start_rotation(session, data_class, reason, actor) -> CryptoJob`: si hay job `rotate` `pending`, `running` o `failed` de la clase, lo devuelve para reanudar (sin llave nueva); si no, en una transacción: `SELECT ... FOR UPDATE` de la llave `active` (espera a los `FOR SHARE` del API), la pasa a `decrypt_only` con `rotated_at = now()` y `rotate_by`, genera y envuelve la DEK nueva con `version + 1` en `active`, crea el job con `total` = filas pendientes, registra `rotate` en `crypto_ops`; recarga el keyring. `reason` vacío lanza `ValueError` — 4 h
- [ ] T4 · `service.reencrypt_batch(session, job, batch_size=500) -> int`: por cada `ColumnRef`, `SELECT id, <col> FROM <tabla> WHERE <col> IS NOT NULL AND split_part(<col>, '.', 2) <> :active_id ORDER BY id LIMIT :n FOR UPDATE`; descifra con su `key_id` y `aad_for(id)`, cifra con la activa, `UPDATE` de Core por id; todo dentro de `bus.batch("decrypt")` y `bus.batch("encrypt")`; suma a `job.done` (ajusta `total` si aparecen filas nuevas); devuelve las filas procesadas. Cada llamada es una transacción — 5 h
- [ ] T5 · `service.finish_rotation(session, job) -> bool`: bajo `FOR UPDATE` de las llaves `decrypt_only` de la clase, recuenta filas con `key_id` distinto del activo en todas las columnas descubiertas; si es cero, cada llave `decrypt_only` sin filas pasa a `retired` (con `next_key_state`) y el job a `done` con `finished_at`; si no, devuelve `False` y el bucle sigue — 2 h
- [ ] T6 · `service.fail_job(job_id, error_code)` en transacción aparte: job `failed`, `error` con un código sin datos (`db_error`, `decrypt_failed`, `interrupted`), llave anterior intacta en `decrypt_only` — 1 h
- [ ] T7 · `service.rotate_index(session, data_class, reason, actor) -> int` para `--index`: en una sola transacción crea la llave `index` nueva `active`, pasa la anterior directo a `retired`, recalcula todos los `_idx` de la clase descifrando con la DEK vigente y `bus.blind_index` con la llave nueva (lote `index` en `crypto_ops`); se niega si la clase supera 50.000 filas (protección; el gimnasio tiene hasta 1.000 socios) — 4 h
- [ ] T8 · Exclusión entre procesos: `pg_try_advisory_lock(hashtext('apex:rotate:' || :data_class))` en una conexión dedicada que el comando mantiene abierta; si no se obtiene, "rotación en curso" y código 1. Un job `running` sin candado (proceso caído) se reanuda — 1,5 h
- [ ] T9 · Comando en `api/src/app/cli.py`: `rotate-key <data_class> --reason TEXT [--index] [--as EMAIL] [--batch-size 500]`; `--reason` obligatorio y no vacío tras `strip` (si falta, código 2 sin tocar llaves); carga la aplicación para poblar los metadatos, arranca el keyring, abre `actor_scope` y `batch_scope`, informa el total de filas antes de empezar, recorre `reencrypt_batch` imprimiendo `done/total` por lote, llama `finish_rotation` y sale con 0; ante excepción llama `fail_job` y sale con 1. `--as` se resuelve con `auth.service` (usuario existente, rol admin, no dado de baja); sin `--as`, `SYSTEM_USER_ID` (N-15). Si EP-13 ya creó el helper común `resolve_cli_actor`, se reutiliza — 3 h
- [ ] T10 · Auditoría desde el CLI: `audit.record(session, action="update", table_name="crypto.crypto_keys", record_id=<llave nueva>, before={"key_id": <anterior>, "state": "active"}, after={"event": "rotate", "reason": ..., "new_version": n, "index": bool})` en la misma transacción de `start_rotation`, y otra entrada `{"event": "retire"}` en la de `finish_rotation` — 1,5 h

### Schemas
- No aplica.

### Router
- No aplica (la historia es solo CLI; el endpoint llega en US-145).

### Tests unitarios puros
- [ ] T11 · `api/tests/crypto/test_next_key_state.py`: transiciones permitidas y prohibidas (`retired` → `active`, `decrypt_only` → `active`, `active` → `retired` para `encrypt`) — 1 h

### Tests de service con PostgreSQL
- [ ] T12 · `api/tests/crypto/test_rotate.py` con 1.200 filas del modelo de prueba de US-028: rotación completa (versión 2 `active`, 3 lotes, `done = 1200`, versión 1 `retired`, todos se leen, ninguna fila con el `key_id` anterior); lectura durante el recifrado tras el primer lote; interrupción simulada tras el lote 1 y nueva ejecución que continúa sin crear versión 3 ni recifrar de nuevo (se compara el blob de las filas ya migradas); falla inyectada en el lote 2 deja `failed`, versión 1 en `decrypt_only` y datos legibles; `crypto_ops` con una fila `rotate` y filas de lote con `count`; entradas de auditoría con el motivo — 6 h
- [ ] T13 · `api/tests/crypto/test_rotate_concurrency.py`: dos sesiones; con el candado tomado, la segunda falla con "rotación en curso" y no crea llave; una escritura del API con `FOR SHARE` en curso hace esperar la transacción de rotación y su fila queda con la llave nueva o es recifrada antes del retiro — 2,5 h
- [ ] T14 · `api/tests/crypto/test_rotate_index.py`: `--index` cambia todos los `document_idx`, la búsqueda por el valor normalizado encuentra el registro con la llave nueva, la llave `index` anterior queda `retired`, `--index` sin datos funciona — 1,5 h
- [ ] T15 · `api/tests/test_cli_rotate_key.py`: sin `--reason` sale con código distinto de 0 y no cambia llaves; `--as` de un usuario inexistente falla; salida informa el total antes de empezar — 1 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T16 · `test_core_import_graph.py` (US-029) y `test_banned_imports.py` (US-031) siguen verdes: `core/crypto/service.py` no importa `core/audit` ni `app.modules` — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T17 · `docs/operacion/rotar-llave.md`: cuándo rotar, comando exacto con `docker compose run --rm api python -m app.cli rotate-key ...`, aviso de CPU en horario de atención, cómo reanudar, qué hacer si queda `failed`, respaldo previo obligatorio (`pg_dump` y `cli export-kek`, US-116) — 2 h

### Seguridad
- [ ] T18 · Revisión: ninguna transición deja una llave `retired` con datos de negocio; el código de error del job no contiene datos; el material nuevo solo se persiste envuelto; el candado no se puede saltar con dos contenedores (es de la base, no del proceso); el motivo no admite datos personales (se advierte en la ayuda del comando) — 1 h

## Orden de ejecución
1. Resolver la pregunta abierta (blobs de `audit_log` frente a `retired`)
2. T11 (prueba pura), luego T1
3. T2
4. T12, T13 y T14 escritas, luego T3, T4, T5, T6, T7 y T8
5. T15 escrita, luego T9 y T10
6. T16, T17, T18

## Dependencias técnicas
- US-028 · Tipos Encrypted y BlindIndexed: columnas a descubrir, `FOR SHARE` del listener y `Secret`.
- US-029 · Bitácora crypto_ops por lote: `bus.batch`, `actor_scope`, `batch_scope` y la brecha de `core/context.py`.
- US-024 · Tablas crypto: índice de una `active`, índice de un job en curso por clase, trigger de transiciones.
- US-025 y US-026 · Keyring, bootstrap e índice ciego.
- US-016 · Hook de auditoría (EP-01) y US-015 · `audit.record`: entrada de auditoría escrita por el CLI.
- US-041 · Usuarios (EP-04): resolución de `--as` por `auth.service` y fila de `SYSTEM_USER_ID`.
- US-116 · Respaldo de la KEK (EP-13): respaldo previo recomendado en el runbook.

## Endpoints
- Ninguno.

## Riesgos
- Retirar una llave mientras queda un dato de negocio cifrado con ella pierde ese dato para siempre — impacto: irreversible sobre RN-13 — mitigación: retiro solo tras recuento a cero bajo `FOR UPDATE`, `FOR SHARE` en las escrituras del API, trigger que impide volver de `retired` y prueba de lectura total tras retirar.
- Historial de auditoría ilegible tras retirar (pregunta abierta) — impacto: la ficha no puede mostrar valores viejos — mitigación: se decide en el gate; por defecto se muestra "valor cifrado modificado".
- Recifrar en horario de atención consume CPU — mitigación: el comando informa el total y el runbook recomienda fuera de horario; 1.000 socios se recifran en segundos.
- Un proceso API con keyring viejo intenta cifrar con la llave anterior — mitigación: `crypto_key_changed` (503 reintentable) en US-028 y `refresh_if_stale` al inicio de cada petición.
- `--index` deja sin resultados las búsquedas de un proceso que no recargó — mitigación: `refresh_if_stale` al inicio de la petición; la ventana es de una petición.

## Estimación
- Backend: 25,5 h
- Front: 0 h
- Pruebas: 12,5 h
- DevOps / seguridad: 3 h
- **Total: 41 h**

La suma queda en el borde alto del rango de 8 puntos (28-42 h) por la rotación de índice en una sola transacción, el candado entre procesos y las pruebas de concurrencia; la historia no se parte (rotar sin recifrar deja el proceso incompleto).

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/crypto/test_next_key_state.py tests/crypto/test_rotate.py tests/crypto/test_rotate_concurrency.py tests/crypto/test_rotate_index.py tests/test_cli_rotate_key.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Tras `uv run python -m app.cli rotate-key member.document --reason "prueba"` en una base con datos: `SELECT version, state FROM crypto.crypto_keys WHERE purpose = 'encrypt' AND data_class = 'member.document' ORDER BY version` muestra `1 retired` y `2 active`; `SELECT status, done, total FROM crypto.crypto_jobs ORDER BY created_at DESC LIMIT 1` muestra `done` con `done = total`
- [ ] `SELECT count(*) FROM members.members WHERE split_part(document, '.', 2) = '<key_id versión 1>'` devuelve 0 (cuando exista `members`, US-069)
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.crypto --cov-fail-under=80`
