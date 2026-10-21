# US-028 · Tipos de columna Encrypted y BlindIndexed — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-02-bus-de-criptografia/US-028-tipos-de-columna-encrypted-y-blindindexed.md`
- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context / módulo:** Crypto (`api/src/app/core/crypto/types.py`, `api/src/app/core/crypto/secret.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

Los tipos, el AAD igual al id, el JSON del contacto, la fecha ISO y la prohibición de cambiar el id están definidos en la historia y en `04_architecture_decision.md` sección 7. El patrón de lectura explícita que la historia deja "para decidir al implementar" se fija aquí sin cambiar el alcance (`Secret` opaco y `reveal` explícito). DECISIONES N-01 confirma que nada se guarda en claro ni en fragmentos.

## Resumen

Un modelo declara `document: Mapped[Secret | None] = mapped_column(Encrypted("member.document"))` y `document_idx: Mapped[str | None] = mapped_column(BlindIndexed("member.document", source="document"))`. El valor del atributo es un `Secret` opaco: se crea con `Secret.from_plain(...)` y nunca muestra su contenido en `repr`, `str` ni JSON. Un listener `before_flush` cifra los `Secret` pendientes con `aad = id`, recalcula el `_idx` en el mismo flush, asigna el `id` si falta y rechaza cambios de `id`. El `TypeDecorator` solo deja llegar a la base blobs `apx1` válidos, así que un texto en claro nunca se escribe ni siquiera por un `INSERT` de Core. Leer en claro exige `reveal(obj, campo, purpose)`.

## Correcciones aplicadas por DECISIONES.md

- La historia deja abierto el patrón de lectura en claro → `reveal(obj, field, purpose) -> str | date | dict` en `core/crypto/types.py`, con `purpose` obligatorio (`mask`, `reveal`, `notify`, `auth_link`, `export`) que va a `crypto_ops.purpose`: corregido por DECISIONES N-01 (el enmascarado de la ficha es un descifrado con propósito `mask`) y N-21 (propósitos `notify` y `auth_link`). No hay columnas `*_hint` (N-01).
- `created_by` del registro de prueba y actor de las operaciones → `SYSTEM_USER_ID` en pruebas sin petición: corregido por DECISIONES N-15.

## Validación contra el dominio

- Value objects cifrados de `Member` (`Document`, `Phone`, `Email`, `BirthDate`, `EmergencyContact`, 02_domain_model 2.1): el tipo de columna es su implementación; `EmergencyContact` como JSON `{"name","phone"}` y `BirthDate` como `date`.
- RN-13: ningún valor sensible llega a la base en claro; mostrar en claro pasa por `reveal`, que deja rastro en `crypto_ops` (la auditoría `reveal` la escribe `members.service`, US-074).
- Invariante "documento único por índice ciego": `BlindIndexed` llena `document_idx` en el mismo flush, de modo que el índice único parcial de `0006_members` se evalúa en la misma sentencia `INSERT`.
- Sin eventos. Función pura: `canonical_json(value) -> str` (llaves ordenadas, separadores compactos, `ensure_ascii=False`).

## Validación contra la arquitectura

- Tipos en `core/crypto/types.py`, como fija `04_architecture_decision.md` sección 7; `models` → `core.crypto.types` es una dependencia permitida (`05_service_design.md` sección 1).
- El listener se registra al importar `core/crypto/types.py` sobre `sqlalchemy.orm.Session` (clase síncrona que usa `AsyncSession` por debajo), así `core/db.py` no importa `core/crypto` y no hay ciclo.
- Un `TypeDecorator` no conoce el id de la fila, por eso el cifrado ocurre en `before_flush` (donde está el objeto) y el `TypeDecorator` solo valida y envuelve. Es un detalle interno de `core/crypto`.
- Los módulos nunca llaman `bus.encrypt` para estos campos: basta asignar `Secret.from_plain`.
- La auditoría (US-016) debe serializar columnas con `TypeDecorator` pasando por `column.type.process_bind_param`, así guarda el blob sin importar `core/crypto` (contrato hacia EP-01).
- Sin router, sin rol, sin paginación.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (la tabla de prueba se crea con `create_all` solo en tests).

### Models
- [ ] T1 · Modelo de prueba `api/tests/crypto/models_fixture.py::CryptoTestPerson` en el esquema `test_crypto` con los cinco campos `Encrypted` de v0.1 y los tres `BlindIndexed`, heredando `CommonColumnsMixin` — 1 h

### Service
- [ ] T2 · `api/src/app/core/crypto/secret.py`: `Secret` inmutable con dos estados (`from_plain(value)` pendiente, `from_blob(blob)` sellado); `__repr__`/`__str__` devuelven `Secret(•••)`; `__eq__` solo entre blobs; `__reduce__`, `__json__` y la serialización de Pydantic lanzan `TypeError` (evita filtrar a respuestas o logs); `blob` solo disponible en estado sellado — 2 h
- [ ] T3 · `api/src/app/core/crypto/types.py::Encrypted(TypeDecorator[Secret])` con `impl = Text`, `cache_ok = True`, atributo `data_class` validado contra el registro; `process_bind_param` acepta `None`, `Secret` sellado o `str` que pase `parse_blob`, y rechaza todo lo demás (incluido `Secret` pendiente y texto en claro) con `CryptoError("valor en claro hacia la base")`; `process_result_value` devuelve `Secret.from_blob` — 2,5 h
- [ ] T4 · `types.py::BlindIndexed(TypeDecorator[str])` con `impl = Text`, `data_class` (debe tener `index_kind`) y `source` (nombre del atributo `Encrypted`); el índice de la columna lo declara el modelo — 1 h
- [ ] T5 · Listener `before_flush` en `types.py`: recorre `session.new` y `session.dirty` con columnas `Encrypted`; asigna `id = uuid4()` si falta; si el `id` de un objeto persistente cambió (`inspect(obj).attrs.id.history.has_changes()`) lanza `CryptoError("no se puede cambiar el id de un registro cifrado")`; por cada `Secret` pendiente serializa según `value_type` (`str`, `date.isoformat()`, `canonical_json`), llama `bus.encrypt(data_class, bytes, aad_for(obj.id))`, reemplaza por el `Secret` sellado y llena el `BlindIndexed` asociado con `bus.blind_index`; `None` deja ambas columnas en `NULL`; un cambio directo a un `_idx` sin cambio de su fuente lanza error — 4 h
- [ ] T6 · Verificación de llave vigente en el mismo listener (requerida por US-030): antes de cifrar, una vez por flush y por clase, `SELECT id FROM crypto.crypto_keys WHERE purpose = :p AND data_class = :dc AND state = 'active' FOR SHARE` sobre `session.connection()`; si no coincide con la llave `active` del keyring lanza `CryptoError("crypto_key_changed")` (el error HTTP lo traduce a 503 reintentable). El `FOR SHARE` hace que la transacción de rotación espere a las escrituras en curso con la llave anterior — 2 h
- [ ] T7 · `types.reveal(obj, field, purpose) -> str | date | dict`: descifra con `aad_for(obj.id)`, convierte por `value_type`, registra la operación con `purpose` (US-029); `purpose` fuera del `Literal` `OpPurpose` lanza error — 1,5 h
- [ ] T8 · Función pura `canonical_json(value: Mapping[str, object]) -> str` en `secret.py` — 0,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T9 · `api/tests/crypto/test_secret.py`: `repr`, `str`, `json.dumps` y `model_dump` de Pydantic no muestran el valor; `canonical_json` ordena llaves y es estable — 1 h

### Tests de service con PostgreSQL
- [ ] T10 · `api/tests/crypto/test_types.py` con `CryptoTestPerson`: `document` guardado empieza por `apx1.`; `SELECT row_to_json(t)::text FROM test_crypto.crypto_test_person t` no contiene `"1020304"` ni `"1.020.304"`; `document_idx` = `blind_index("member.document", "1020304")`; cambiar el teléfono recifra (blob distinto) y recalcula `phone_idx` en el mismo flush; `None` deja `NULL` en ambas; contacto JSON vuelve como el mismo `dict`; `birth_date` vuelve como `date`; cambiar el `id` lanza error y no hay commit; asignar `"1020304"` como `str` lanza `CryptoError`; un `INSERT` de Core con texto en claro falla; las cinco clases de v0.1 probadas — 4 h
- [ ] T11 · `api/tests/crypto/test_types_key_check.py`: con una llave `active` cambiada por otra sesión (simulación de rotación), el flush lanza `crypto_key_changed`; con la llave vigente pasa — 1 h
- [ ] T12 · `api/tests/core/test_audit_encrypted.py` (en coordinación con US-016): un modelo de prueba auditado con un campo `Encrypted` deja `before` y `after` con el blob, nunca el valor — 1 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T13 · `test_banned_imports.py` y `test_no_plaintext_at_rest.py` (US-031) siguen verdes con el modelo de prueba — 0,5 h

### Front
- No aplica.

### DevOps
- No aplica.

### Seguridad
- [ ] T14 · Revisión: `Secret` no se filtra por `repr`, logs, JSON ni excepciones; el `TypeDecorator` bloquea texto en claro en ORM y en Core; el descifrado solo ocurre con `reveal` y propósito; el `id` es inmutable en registros cifrados — 1 h

## Orden de ejecución
1. T9 (prueba pura), luego T8 y T2
2. T1, T10 escrita, luego T3, T4 y T5
3. T11, luego T6
4. T7
5. T12, T13, T14

## Dependencias técnicas
- US-025 · Cifrado AES-GCM y formato de blob: `bus.encrypt`, `parse_blob`, `aad_for`, registro con `value_type`.
- US-026 · Índice ciego HMAC: `bus.blind_index`.
- US-012 · Base de datos y Alembic (EP-01): `CommonColumnsMixin` con `id` asignado en Python antes del flush.
- US-016 · Hook de auditoría (EP-01): debe serializar columnas `TypeDecorator` por `process_bind_param` para guardar el blob.
- US-029 · Bitácora crypto_ops: registro de `encrypt`, `index` y `decrypt` con `purpose`.

## Endpoints
- Ninguno.

## Riesgos
- El orden de los listeners: si la auditoría serializara en `before_flush` antes del cifrado, vería un `Secret` pendiente — mitigación: la auditoría usa `after_flush` (US-016) y `Secret` pendiente no es serializable (falla ruidosamente, nunca en claro).
- `FOR SHARE` en cada flush con campos cifrados añade una consulta por clase — impacto mínimo con menos de 10 usuarios concurrentes — mitigación: una vez por flush y por clase, sobre índice único.
- La importación masiva (US-112) cifra 1.000 filas: el listener debe ser rápido — mitigación: prueba de rendimiento junto con la de US-016 (500 inserciones en menos de 5 s).

## Estimación
- Backend: 14,5 h
- Front: 0 h
- Pruebas: 7,5 h
- DevOps / seguridad: 1 h
- **Total: 23 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/crypto/test_secret.py tests/crypto/test_types.py tests/crypto/test_types_key_check.py tests/core/test_audit_encrypted.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] En la base de prueba, `SELECT document FROM test_crypto.crypto_test_person` devuelve solo valores que empiezan por `apx1.`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.crypto --cov-fail-under=80`
