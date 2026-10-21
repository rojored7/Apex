# US-016 · Hook de auditoría en `after_flush` — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-01-nucleo-compartido/US-016-hook-de-auditoria-after-flush.md`
- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context / módulo:** Audit, hook (`api/src/app/core/audit.py`, `api/src/app/core/context.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

El único supuesto de la historia, el actor técnico de worker y CLI, lo cierra DECISIONES N-15: un solo `SYSTEM_USER_ID` y `--as <email>` en el CLI. Este desglose fija dos decisiones técnicas que no cambian el alcance:
- el `ContextVar` del actor vive en un archivo neutro, `core/context.py`, para que `core/crypto` (US-029) también lo lea sin importar `core/audit`, porque eso cerraría un ciclo con N-06;
- los listeners los instala `core/audit.py` sobre la clase de sesión, de modo que `core/db.py` no importe auditoría.

## Resumen

Esta historia entrega:
- `core/context.py`, con `SYSTEM_USER_ID`, el `ContextVar` del actor, `get_actor()`, `actor_scope()` y `request_id_var`;
- en `core/audit.py`, un listener `before_flush` que llena `created_by` y un listener `after_flush` que, por cada objeto de un modelo con `__audited__ = True`, escribe `insert`, `update` o `delete` con `before` y `after` en la misma transacción, usando `append_entry` de US-015;
- las funciones puras `serialize_value`, `serialize_row` y `diff_row`;
- una guarda que rechaza el flush si una columna cifrada lleva un valor sin el prefijo `apx1.`;
- pruebas de cada caso con base real y una prueba de rendimiento con 500 inserciones.

## Correcciones aplicadas por DECISIONES.md

- La historia propone un `SYSTEM_ACTOR_ID` configurable, un actor `system` para el worker y el admin que ejecuta el CLI. Se usa un único `SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")`, constante en `core/context.py` y no variable de entorno. El worker, el seed, la importación y la migración de proveedor fijan ese actor. Todo comando del CLI acepta `--as <email>` y fija el `id` de esa persona; resolver el correo es tarea del CLI (US-111) a través de `auth.service`. Corregido por DECISIONES N-15.
- El criterio 7 dice que solo falla el flush de un modelo auditado sin actor. Como `created_by` es `NOT NULL` (US-012, N-15), falla cualquier inserción de un modelo con `CommonColumnsMixin` sin actor ni `created_by` explícito. Es un superconjunto del criterio 7, con el mismo `MissingActorError`.

## Validación contra el dominio

- `AuditEntry`. Tablas auditadas de v0.1: `members`, `plans`, `memberships`, `payments`, `users` y `settings_sections`. Cada módulo declara `__audited__ = True` en su historia; la lista la vigila la prueba de US-107.
- RN-16: cada fila pasa por `append_entry`, que encadena el hash.
- RN-13: los campos cifrados entran a la auditoría como blob `apx1.…`, nunca en claro. Hay una guarda activa (T5).
- RN-14: un borrado lógico (`deleted_at` de nulo a fecha) se audita como `update`. Un borrado físico se audita como `delete` con `before` completo.
- Funciones puras:
  - `diff_row(before: Mapping, after: Mapping) -> tuple[dict, dict]`;
  - `serialize_value(value) -> JsonValue`;
  - `serialize_row(values: Mapping[str, object], *, encrypted: frozenset[str], redacted: frozenset[str]) -> dict`.
- Sin eventos.

## Validación contra la arquitectura

- Audit ← todos, como Published Language por hook (`03_context_map.md`). Ningún módulo llama a la auditoría para sus cambios normales.
- Dirección de imports:
  - `core/audit.py` importa `core/context.py`, `core/db.py`, `core/clock.py` y `core.crypto.bus.digest`;
  - `core/context.py` solo importa la biblioteca estándar;
  - `core/crypto` (US-029) y `core/security` (US-034) importan `core/context.py`, nunca `core/audit.py`;
  - `core/db.py` no importa `core/audit.py`; `install_audit_listeners()` se llama desde `create_app()`, `worker/main.py`, `cli.py` y `tests/conftest.py`.
- La auditoría no importa `core.crypto.types`. Las columnas cifradas se reconocen por el atributo `is_encrypted = True` que expone el tipo de US-028, así que no hay dependencia de import.
- Cómo se propaga el actor por HTTP: `current_user` (US-034) es una dependencia `async def` que llama a `current_actor.set(user.id)` y no lo resetea en un teardown. Cada petición corre en su propia tarea con su propio contexto, y el commit de `get_session` ocurre en el teardown de esa dependencia. Como `current_user` depende de `get_session`, su teardown corre antes, y si reseteara el actor ahí el commit se quedaría sin actor.
- Las rutas sin token que escriben en tablas auditadas fijan el actor de forma explícita con `actor_scope`: login con bloqueo, `reset` de contraseña y activación (EP-04). Ver Riesgos.
- Lint `banned-api`: sin primitivas criptográficas. Models cruzados, rol y paginación: no aplican.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (usa `audit.audit_log` de `0002_audit_log`, US-015).

### Models
- No aplica. Los modelos de cada módulo declaran `__audited__ = True` y, si hace falta, `__audit_redact__: ClassVar[frozenset[str]]` (por ejemplo `{"password_hash"}` en `users`, US-041).

### Service
- [ ] T1 · `core/context.py`:
  - `SYSTEM_USER_ID: Final[UUID]`;
  - `current_actor: ContextVar[UUID | None]`, con `None` por defecto;
  - `get_actor() -> UUID`, que lanza `MissingActorError` si no hay actor;
  - `@contextmanager actor_scope(user_id: UUID) -> Iterator[None]`, que fija el actor y lo restaura al salir;
  - `request_id_var: ContextVar[str | None]`, que usan US-017 y US-018;
  - docstring con las reglas de propagación descritas en la validación de arquitectura.
  
  — 1,5 h
- [ ] T2 · Funciones puras en `core/audit.py`:
  - `serialize_value(value: object) -> JsonValue`: UUID en minúscula; `datetime` aware en ISO UTC con `Z`; `date` en ISO; `Enum` como su `.value`; `bool`, `int`, `str` y `None` tal cual; `dict` y `list` de JSONB de forma recursiva; `Decimal`, `float` y `bytes` lanzan `AuditSerializationError`;
  - `serialize_row(values, *, encrypted, redacted) -> dict`: excluye `created_at` y `updated_at` (son técnicos y la fila de auditoría ya tiene `at`); reemplaza las columnas de `redacted` por `"[redacted]"`; si una columna de `encrypted` trae un valor no nulo que no empieza por `apx1.`, lanza `PlaintextInAuditError`.
  
  — 1,5 h
- [ ] T3 · Función pura `diff_row(before: Mapping, after: Mapping) -> tuple[dict, dict]`: devuelve solo las claves cuyo valor cambió, incluido el cambio a `None` — 0,5 h
- [ ] T4 · Listener `before_flush(session, flush_context, instances)`: para cada objeto de `session.new` que hereda `CommonColumnsMixin` y tiene `created_by is None`, asigna `get_actor()`. Si no hay actor, se propaga `MissingActorError` con el mensaje "falta el actor: fije actor_scope(SYSTEM_USER_ID) o --as <email>" (criterios 7 y 8) — 1 h
- [ ] T5 · Listener `after_flush(session, flush_context)`:
  1. recorre `session.new`, `session.dirty` y `session.deleted`, filtrando los modelos con `__audited__ = True`;
  2. en una inserción, escribe `insert` con `after = serialize_row(todas las columnas)` (criterio 1);
  3. en un objeto modificado, toma el valor anterior de `inspect(obj).attrs[col].history.deleted` y el nuevo de `history.added`, aplica `diff_row` y, si no quedan cambios, no escribe nada (criterios 2 y 3);
  4. en un borrado, escribe `delete` con `before` completo;
  5. llama a `append_entry(session.connection(), action=..., table_name=obj.__tablename__, record_id=obj.id, before=..., after=..., user_id=get_actor())`.
  
  La escritura es Core, sobre la misma conexión y la misma transacción (criterio 6). Las columnas cifradas se detectan con `getattr(column.type, "is_encrypted", False)` y se pasan a `serialize_row` (criterio 5).
  
  — 3,5 h
- [ ] T6 · `install_audit_listeners() -> None`, idempotente: registra T4 y T5 con `event.listen(Session, ...)` sobre la clase `Session` síncrona que usa `AsyncSession`. Además, `record()` de US-015 pasa a tomar `user_id` de `get_actor()` cuando no se le pasa — 1 h
- [ ] T7 · Contratos documentados en el docstring de `core/audit.py`:
  - para US-028: el atributo mapeado de una columna `Encrypted` contiene siempre el blob `apx1.…`; el valor en claro va en un accesor aparte, y el tipo expone `is_encrypted = True`;
  - para US-034: `current_user` fija el actor sin resetearlo;
  - para worker y CLI: `actor_scope(SYSTEM_USER_ID)` o el actor de `--as`.
  
  — 0,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T8 · `tests/core/test_audit_serialize.py`:
  - `diff_row`: sin cambios, un cambio, cambio a nulo y dos columnas;
  - `serialize_value`: UUID, `datetime` aware y uno ingenuo (este falla), `date`, `Enum`, y `Decimal` o `float` prohibidos;
  - `serialize_row`: excluye `created_at` y `updated_at`, redacta `password_hash` y lanza `PlaintextInAuditError` ante `"1020304"` en una columna cifrada;
  - `get_actor()` sin actor da `MissingActorError`, y `actor_scope` restaura el valor anterior.
  
  — 2 h

### Tests de service con PostgreSQL
- [ ] T9 · `tests/core/test_audit_hook_db.py`, con un modelo de prueba auditado y otro no auditado:
  - una inserción da `insert` con `after` y `user_id` igual al actor (criterio 1);
  - modificar dos columnas da `before` y `after` solo de esas dos (criterio 2);
  - asignar el mismo valor no deja fila de auditoría (criterio 3);
  - el modelo no auditado no deja filas (criterio 4);
  - el borrado lógico es `update` de `deleted_at`;
  - el borrado físico es `delete` con `before`;
  - con rollback no queda ninguna fila de auditoría (criterio 6);
  - sin actor, el flush falla con `MissingActorError` (criterio 7, BDD 3);
  - `created_by` se llena solo (criterio 8);
  - dos flushes en la misma transacción mantienen la cadena válida (`verify_chain`).
  
  — 4 h
- [ ] T10 · `tests/core/test_audit_hook_encrypted.py`:
  - con un tipo de prueba que expone `is_encrypted = True`, el `after` contiene `apx1.…` y no contiene `1020304`;
  - asignar texto en claro a esa columna hace fallar el flush (criterio 5, BDD 2);
  - una segunda prueba con el `Encrypted` real, marcada `skipif` hasta que exista US-028, verifica el mismo resultado de punta a punta.
  
  — 1 h
- [ ] T11 · `tests/core/test_audit_hook_perf.py`: 500 inserciones auditadas en una transacción en menos de 5 s contra `db_test` (insumo de US-112) — 1 h

### Tests de router
- [ ] T12 · `tests/core/test_audit_actor_http.py`: en una app mínima, una dependencia `async` de prueba imita a `current_user` y fija el actor, y un endpoint modifica un modelo auditado. La fila de auditoría tiene `user_id` igual al actor. Esto demuestra que el actor sigue visible durante el commit del teardown de `get_session` — 1,5 h

### Tests de arquitectura
- No aplica nueva. Deben seguir verdes `test_core_import_direction.py` (US-015: `core/audit.py` no importa `core.crypto.types`, y `core/crypto` no importa `core/audit`) y `test_banned_imports.py` (US-002).

### Front
- No aplica.

### DevOps
- No aplica.

### Seguridad
- [ ] T13 · Revisión:
  - ningún valor descifrado llega a `before` o `after` (guarda T2 y prueba T10);
  - `__audit_redact__` en `users.password_hash` (coordinar con US-041);
  - sin actor no hay auditoría silenciosa con `user_id` vacío;
  - `SYSTEM_USER_ID` es una constante, no se puede inyectar por entorno;
  - las rutas públicas que escriben tablas auditadas usan `actor_scope` de forma explícita (lista entregada a EP-04).
  
  — 1 h

## Orden de ejecución
1. T8 (en rojo)
2. T1
3. T2
4. T3
5. T9 (en rojo)
6. T4
7. T5
8. T6
9. T10
10. T11
11. T12
12. T7
13. T13

## Dependencias técnicas
- US-015 · Tabla de auditoría y cadena de hashes: `append_entry`, `record`, `verify_chain` y `0002_audit_log`.
- US-012 · Base de datos: `CommonColumnsMixin` con `created_by NOT NULL` e id asignado al construir.
- US-034 · current_user (dependencia suave): fija `current_actor`; hasta que exista, las pruebas usan una dependencia doble.
- US-028 · Tipos Encrypted y BlindIndexed: debe cumplir el contrato de T7 (el atributo guarda el blob y el tipo expone `is_encrypted`). Activa la segunda prueba de T10.
- US-041 · Cuentas de usuario: crea la fila de `SYSTEM_USER_ID` en `0004_auth` y declara `__audit_redact__`.
- US-020 · create_app: llama a `install_audit_listeners()`; también lo hacen el worker y el CLI.

## Endpoints
- Ninguno.

## Riesgos
- Si US-028 implementa `Encrypted` como `TypeDecorator`, que cifra en `process_bind_param` y deja el valor en claro en el atributo, el hook vería texto en claro: el criterio 5 fallaría o el flush se rechazaría — mitigación: contrato explícito (T7), guarda `PlaintextInAuditError` y prueba de punta a punta en T10, que se activa con US-028.
- Rutas sin JWT que escriben tablas auditadas (bloqueo por intentos en login, `reset` y activación de contraseña) fallarían con `MissingActorError` — mitigación: EP-04 fija `actor_scope(user.id)` (el dueño de la cuenta) o `SYSTEM_USER_ID` antes del flush. Se avisa como contrato entre épicas.
- Columnas diferidas o expiradas: `history.deleted` viene vacío y `before` quedaría incompleto — mitigación: los modelos auditados no usan `deferred` y la sesión usa `expire_on_commit=False` (US-012). Se anota en el docstring.
- Resetear el actor en el teardown de `current_user` borra el actor antes del commit — mitigación: regla documentada y prueba T12.
- Rendimiento en lotes grandes (importación, recifrado): una lectura de la cola por entrada, bajo el lock — mitigación: medido en T11. Si hace falta, US-112 confirma por lotes.

## Estimación
- Backend: 9,5 h
- Front: 0 h
- Pruebas: 9,5 h
- DevOps / seguridad: 1 h
- **Total: 20 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_audit_serialize.py tests/core/test_audit_hook_db.py tests/core/test_audit_hook_encrypted.py tests/core/test_audit_hook_perf.py tests/core/test_audit_actor_http.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Tras la prueba de T9, `SELECT action, before, after, user_id FROM audit.audit_log ORDER BY seq` muestra `insert`, `update` (solo las columnas cambiadas) y `delete`, con el actor correcto
- [ ] `verify_chain` sobre las filas generadas por T9 y T11 devuelve `ok = True`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.audit --cov=app.core.context --cov-fail-under=80`
