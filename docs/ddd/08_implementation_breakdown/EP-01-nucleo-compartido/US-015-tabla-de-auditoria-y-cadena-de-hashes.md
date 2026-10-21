# US-015 · Tabla de auditoría append-only y cadena de hashes — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-01-nucleo-compartido/US-015-tabla-de-auditoria-y-cadena-de-hashes.md`
- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context / módulo:** Audit, escritura (`api/src/app/core/audit.py`, esquema `audit`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

DECISIONES resuelve los tres puntos abiertos de la historia:
- N-06: el SHA-256 sale de `core.crypto.bus.digest`;
- N-08: la acción `download`;
- N-30: un salto en `seq` es ruptura.

Quedan dos decisiones técnicas, tomadas y justificadas aquí, que no cambian el alcance:
- el bloqueo concreto, que es `pg_advisory_xact_lock`;
- asignar `seq` bajo ese bloqueo en lugar de un `bigserial`, porque una secuencia deja huecos al revertir y N-30 los contaría como ruptura.

La tabla lleva además las columnas comunes que exige la regla de datos 3. La serialización canónica queda fijada en este desglose porque es irreversible.

## Resumen

Esta historia entrega:
- la migración `0002_audit_log`: tabla `audit.audit_log`, función `audit.forbid_mutation()` y triggers que rechazan UPDATE, DELETE y TRUNCATE;
- el modelo `AuditEntry` en `core/audit.py`;
- las funciones puras `canonical`, `chain_hash` y `verify_chain`;
- `append_entry` (síncrona, para el hook de US-016) y `record` (async, para las llamadas explícitas de US-074 y US-107), las dos con `pg_advisory_xact_lock`, que serializa la lectura del `prev_hash`;
- `digest(data) -> str` en `core/crypto`, para que `core/audit.py` no importe `hashlib`.

## Correcciones aplicadas por DECISIONES.md

- La historia propone `crypto.sha256(data)`. Se usa `core.crypto.bus.digest(data: bytes) -> str` (SHA-256 en hexadecimal minúscula). `core/audit.py` no importa `hashlib` y la excepción de `banned-api` no se amplía. Corregido por DECISIONES N-06.
- La historia lista las acciones `insert | update | delete | reveal | export | login | verify`. El CHECK agrega `download`. Corregido por DECISIONES N-08.
- La historia define `seq` como `bigserial`. Se usa `seq BIGINT NOT NULL UNIQUE`, asignado como `último + 1` bajo el lock asesor. Con una secuencia, una transacción revertida consumiría un número y dejaría un hueco, y por DECISIONES N-30 un salto en `seq` es ruptura de la cadena.
- La historia dice que la tabla no lleva `updated_at`. Lleva `id` UUID, `created_at`, `updated_at` y `created_by`, por la regla de datos 3 de `CLAUDE.md` (restricción dura). Para que no haya dos verdades, un CHECK obliga `created_at = at`, `updated_at = at` y `created_by = user_id`, y el trigger impide cambiarlas. No lleva `deleted_at` (RN-14: la auditoría nunca se borra).
- `user_id` es siempre un usuario real o `SYSTEM_USER_ID` (`00000000-0000-0000-0000-000000000001`), nunca nulo. Corregido por DECISIONES N-15.
- Índices de la migración: se agrega `(table_name, seq DESC)` a los de la historia, para que US-102 y US-110 no necesiten migración (numeración canónica).

## Validación contra el dominio

- Aggregate `AuditEntry` (append-only), de `02_domain_model.md` 2.12, con la acción `download` (N-08).
- RN-16: `hash = SHA-256(prev_hash || canonical(row))`, y una fila alterada rompe la cadena.
- RN-14: nunca se borra. El trigger rechaza UPDATE, DELETE y TRUNCATE.
- Funciones puras: `canonical(row) -> bytes`, `chain_hash(prev_hash, row) -> str` y `verify_chain(rows) -> VerifyResult`. `chain_hash` llama a `digest`, que es determinista y sin llave, así que sigue siendo probable sin base.
- `VerifyResult(ok: bool, rows_checked: int, broken_at_seq: int | None)`. Se usa `broken_at_seq`, igual que en la columna de `0013_audit_verifications`. US-104 lo llama `broken_seq` (ver Riesgos).
- Sin eventos.

## Validación contra la arquitectura

- `core/audit.py` es el dueño del modelo de auditoría (`05_service_design.md`: "models viven en core/audit.py").
- Dirección de imports:
  - `core/audit.py` importa `core/db.py`, `core/clock.py` y `core.crypto.bus` (solo `digest`);
  - `core/crypto/**` nunca importa `core/audit`;
  - `core/**` nunca importa `app.modules`.
  
  Lo verifica una prueba de arquitectura nueva (T11).
- Sin ciclo con la bitácora cripto: `digest` no usa llave, no escribe en `crypto_ops` y vive en `core/crypto/digest.py`, que solo importa `hashlib`. `bus.py` lo reexporta. Si `bus.py` registrara en `crypto_ops` cada `digest`, el hook de auditoría escribiría durante un flush, y eso abriría recursión. Por eso queda prohibido por contrato.
- Lint `banned-api`: `hashlib` queda en `core/crypto/digest.py`, que está permitido. `test_banned_imports.py` (US-002) sigue verde.
- La tabla no hereda `CommonColumnsMixin`, porque `created_at` debe ser igual a `at`, que se fija en Python con `current_clock()` antes de calcular el hash. Declara sus columnas comunes de forma explícita.
- Rol, paginación y router: no aplican (la consulta es EP-11).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- [ ] T1 · `0002_audit_log` (`api/migrations/versions/0002_audit_log.py`). Tabla `audit.audit_log`, con estas columnas:
  - `id UUID PRIMARY KEY`;
  - `seq BIGINT NOT NULL UNIQUE` sin `DEFAULT`, con `CHECK (seq >= 1)`;
  - `at TIMESTAMPTZ NOT NULL`;
  - `user_id UUID NOT NULL`, sin FK, porque `auth.users` llega en `0004_auth`;
  - `action TEXT NOT NULL CHECK (action IN ('insert','update','delete','reveal','export','download','login','verify'))`;
  - `table_name TEXT NOT NULL`;
  - `record_id UUID NULL`, porque `verify` no tiene registro;
  - `before JSONB NULL` y `after JSONB NULL`;
  - `prev_hash CHAR(64) NOT NULL CHECK (prev_hash ~ '^[0-9a-f]{64}$')` y `hash CHAR(64) NOT NULL CHECK (hash ~ '^[0-9a-f]{64}$')`;
  - `created_at TIMESTAMPTZ NOT NULL`, `updated_at TIMESTAMPTZ NOT NULL` y `created_by UUID NOT NULL`, con `CHECK (created_at = at AND updated_at = at AND created_by = user_id)`.
  
  Índices: `ix_audit_log_at (at)`, `ix_audit_log_table_record (table_name, record_id)`, `ix_audit_log_user_id (user_id)` e `ix_audit_log_table_seq (table_name, seq DESC)`.
  
  Función PL/pgSQL `audit.forbid_mutation()` con `RAISE EXCEPTION 'audit.audit_log es append-only' USING ERRCODE = 'P0001'` y dos triggers:
  - `audit_log_forbid_mutation BEFORE UPDATE OR DELETE ... FOR EACH ROW`;
  - `audit_log_forbid_truncate BEFORE TRUNCATE ... FOR EACH STATEMENT`.
  
  El downgrade borra los triggers, la función y la tabla.
  
  — 2 h

### Models
- [ ] T2 · `class AuditEntry(Base)` en `core/audit.py` con `__tablename__ = "audit_log"` y `__table_args__ = {"schema": "audit"}`. Declara de forma explícita las columnas de T1. No hereda el mixin y no lleva `__audited__`. Se inserta siempre con `insert()` de Core (T7), nunca con `session.add` — 1 h

### Service
- [ ] T3 · `core/crypto/digest.py` con `sha256_hex(data: bytes) -> str`, que usa `hashlib`, devuelve 64 caracteres hexadecimales en minúscula y solo importa `hashlib`. `core/crypto/bus.py` expone `digest = sha256_hex`; si `bus.py` aún no existe porque US-025 llega después, se crea con solo esa función y US-025 lo extiende. Contrato: `digest` no usa llave ni escribe en `crypto_ops` — 1 h
- [ ] T4 · Función pura `canonical(row: Mapping[str, object]) -> bytes`. Es la especificación irreversible, y su docstring la copia textual para el ADR de US-119:
  - `json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")`;
  - `datetime`: exige un valor aware, lo pasa a UTC y lo formatea como `YYYY-MM-DDTHH:MM:SS.ffffffZ`, siempre con 6 decimales;
  - `date`: `YYYY-MM-DD`;
  - `UUID`: texto en minúscula con guiones;
  - `None`: `null`;
  - `bool`, `int` y `str` quedan tal cual, sin normalizar Unicode;
  - `Enum`: su `.value`;
  - `dict` y `list` se recorren de forma recursiva;
  - `float`, `Decimal`, `bytes` y cualquier otro tipo lanzan `CanonicalError`.
  
  Las claves de la fila que entran al hash son `id`, `seq`, `at`, `user_id`, `action`, `table_name`, `record_id`, `before` y `after`. Las columnas espejo quedan fuera porque las fija el CHECK, y `verify_chain` las compara aparte.
  
  — 1,5 h
- [ ] T5 · `ZERO_HASH = "0" * 64` y la función `chain_hash(prev_hash: str, row: Mapping[str, object]) -> str = digest(prev_hash.encode("ascii") + canonical(row))` — 0,5 h
- [ ] T6 · Función pura `verify_chain(rows: Iterable[Mapping[str, object]]) -> VerifyResult`. Recorre en orden de `seq` y marca ruptura en la primera fila donde ocurra cualquiera de estas cosas:
  - `seq` distinto del anterior más 1, con el primero en 1 (N-30);
  - `prev_hash` distinto del `hash` anterior (o de `ZERO_HASH` en la primera fila);
  - el `hash` recalculado no coincide;
  - las columnas espejo difieren de `at` o `user_id`.
  
  Una cadena vacía da `ok = True` y `rows_checked = 0` — 1,5 h
- [ ] T7 · Escritura:
  - `AUDIT_CHAIN_LOCK_KEY: Final[int]` (bigint fijo, distinto del lock de migraciones de US-020);
  - `append_entry(conn: Connection, *, action: AuditAction, table_name: str, record_id: UUID | None, before: Mapping | None, after: Mapping | None, user_id: UUID) -> AuditRow`, síncrona, que:
    1. ejecuta `SELECT pg_advisory_xact_lock(:key)`;
    2. lee `SELECT seq, hash FROM audit.audit_log ORDER BY seq DESC LIMIT 1` (o usa `0` y `ZERO_HASH` si no hay filas);
    3. arma la fila con `id = uuid4()`, `seq = último + 1` y `at = current_clock().now_utc()`;
    4. calcula `hash = chain_hash(prev_hash, fila)`;
    5. inserta con `insert(AuditEntry)`, con las columnas espejo iguales.
  - `async def record(session: AsyncSession, **kwargs) -> AuditRow`, que delega con `await session.run_sync(lambda s: append_entry(s.connection(), **kwargs))`.
  
  El lock se libera solo al terminar la transacción. Se descarta `SELECT ... FOR UPDATE` sobre la última fila porque con la tabla vacía no hay fila que bloquear y dos primeras inserciones tomarían `ZERO_HASH` a la vez.
  
  — 2,5 h

### Schemas
- No aplica (los schemas HTTP de auditoría son de EP-11).

### Router
- No aplica.

### Tests unitarios puros
- [ ] T8 · `tests/core/test_audit_chain.py`:
  - `canonical`: orden de claves distinto da los mismos bytes (criterio 2); fechas aware en otra zona salen en UTC con `Z` y 6 decimales; un datetime ingenuo, un `float` o un `Decimal` lanzan `CanonicalError`; UUID en minúscula; `None`; acentos y `ñ` en UTF-8 sin escapar;
  - `chain_hash` es determinista;
  - `verify_chain`: cadena vacía, una fila, rota al inicio, al medio y al final, salto de `seq`, `prev_hash` cambiado y columna espejo alterada.
  
  — 2 h

### Tests de service con PostgreSQL
- [ ] T9 · `tests/core/test_audit_log_db.py`:
  - tres llamadas a `record` dejan `seq` 1, 2 y 3 encadenados, con `ZERO_HASH` en la primera fila (criterio 1);
  - `UPDATE`, `DELETE` y `TRUNCATE` sobre `audit.audit_log` fallan como dueño de la tabla (criterio 3);
  - con `ALTER TABLE audit.audit_log DISABLE TRIGGER audit_log_forbid_mutation` dentro de la transacción de prueba, alterar el `after` de `seq = 2` hace que `verify_chain` devuelva `ok = False` y `broken_at_seq = 2` (criterio 4);
  - `at` es `timestamp with time zone`, en UTC (criterio 7).
  
  — 2,5 h
- [ ] T10 · `tests/core/test_audit_concurrency.py`: dos conexiones independientes, fuera del savepoint del fixture, auditan a la vez con `asyncio.gather` y luego confirman. Resultado: `seq` 1 y 2, `prev_hash` distintos y `verify_chain` correcta (criterio 5). La limpieza del fixture usa `DISABLE TRIGGER USER`, `TRUNCATE` y `ENABLE`, solo en pruebas — 1,5 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T11 · `api/tests/architecture/test_core_import_direction.py` (`ast`), que falla nombrando archivo y línea si:
  - un archivo de `src/app/core/**` importa `app.modules`;
  - un archivo de `src/app/core/crypto/**` importa `app.core.audit`;
  - `core/audit.py` importa de `app.core.crypto` algo distinto de `bus.digest`.
  
  `test_banned_imports.py` (US-002) debe seguir verde, sin `hashlib` en `core/audit.py` — 1 h

### Front
- No aplica.

### DevOps
- [ ] T12 · Docstring de `canonical` con la especificación completa y la marca "decisión irreversible; ver ADR (US-119)"; nota en el `PR` para que US-119 la copie en `docs/adr/` — 0,5 h

### Seguridad
- [ ] T13 · Revisión:
  - ningún camino de escritura usa `session.add(AuditEntry)` ni el ORM `update`;
  - el trigger cubre también TRUNCATE;
  - el lock asesor es por transacción (`xact`) y no queda colgado;
  - `before` y `after` nunca reciben valores en claro de campos cifrados (lo garantiza US-016);
  - `digest` no se registra en `crypto_ops`.
  
  — 0,5 h

## Orden de ejecución
1. T8 y T11 (en rojo)
2. T3
3. T4
4. T5
5. T6
6. T1
7. T2
8. T7
9. T9
10. T10
11. T12
12. T13

## Dependencias técnicas
- US-012 · Base de datos y Alembic multiesquema: esquema `audit` (`0001_core_schemas`), `Base` y fixture.
- US-013 · Reloj de Bogotá: `current_clock()` para `at`.
- US-002 · Proyecto api: regla `banned-api` y `test_banned_imports.py`.
- US-025 · Cifrado AES-GCM (EP-02): extiende `core/crypto/bus.py` sin romper `digest`; si llega antes, T3 solo agrega la función.
- US-016 · Hook after_flush: consumidor principal de `append_entry`.
- US-119 · ADR: copia la especificación de `canonical`.

## Endpoints
- Ninguno.

## Riesgos
- La serialización canónica es irreversible: cambiarla con datos existentes rompe toda la cadena — mitigación: especificación cerrada en T4, pruebas de cada tipo y ADR (US-119). Cualquier tipo no previsto falla en lugar de serializarse "a ojo".
- El lock asesor serializa toda escritura auditada del sistema; una importación larga (US-112) bloquea a recepción — mitigación: la carga de v0.1 es menor de 10 usuarios, y US-112 confirma por lotes. La prueba de 500 inserciones en menos de 5 s de US-016 mide el impacto.
- Discrepancia de nombres con US-104 (`broken_seq` frente a `broken_at_seq`) — mitigación: se adopta `broken_at_seq`, que coincide con `0013_audit_verifications`; EP-11 debe alinear su schema HTTP.
- Las pruebas no pueden limpiar la tabla porque el trigger lo impide — mitigación: un fixture de limpieza con `DISABLE TRIGGER USER` solo en `db_test`, y la mayoría de pruebas dentro del savepoint con rollback.
- `CHAR(64)` frente a `TEXT`: el relleno con espacios no aplica porque la longitud es fija y la valida el CHECK.

## Estimación
- Backend: 10 h
- Front: 0 h
- Pruebas: 7 h
- DevOps / seguridad: 1 h
- **Total: 18 h**

Supera la referencia de 3 puntos (10 a 15 h) porque la especificación canónica es irreversible y la prueba de concurrencia con conexiones reales necesita su propio fixture.

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_audit_chain.py tests/core/test_audit_log_db.py tests/core/test_audit_concurrency.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `psql "$DATABASE_URL" -c "UPDATE audit.audit_log SET action='insert'"` es rechazado con "audit.audit_log es append-only" (con al menos una fila)
- [ ] `psql "$DATABASE_URL" -c "TRUNCATE audit.audit_log"` es rechazado
- [ ] `grep -rn "hashlib" api/src/app/core/audit.py` no devuelve nada
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.audit --cov=app.core.crypto.digest --cov-fail-under=80`
