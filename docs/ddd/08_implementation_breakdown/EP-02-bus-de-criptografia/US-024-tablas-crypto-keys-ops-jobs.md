# US-024 · Tablas crypto_keys, crypto_ops y crypto_jobs — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-02-bus-de-criptografia/US-024-tablas-crypto-keys-ops-jobs.md`
- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context / módulo:** Crypto (`api/src/app/core/crypto/models.py`, esquema `crypto`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**NEEDS_REFINEMENT**

Las tres tablas, sus enums, el índice de llave activa y los triggers están resueltos por la historia y DECISIONES N-05 y N-01. Queda una columna cuyo significado ningún documento define: `crypto_keys.rotate_by` puede ser el usuario que rotó (UUID) o la fecha límite de la próxima rotación (TIMESTAMPTZ). Cambia el tipo de la columna en una migración de la ruta crítica que después no se edita.

## Resumen

Migración `0003_crypto` con `crypto.crypto_keys` (inventario de llaves con material solo envuelto), `crypto.crypto_ops` (bitácora append-only con `count` para lotes y `purpose` para el propósito del descifrado) y `crypto.crypto_jobs` (progreso de rotaciones, recifrados, migraciones de proveedor y re-envolturas). Índice único parcial de una llave `active` por (`purpose`, `data_class`), índice único parcial de un job en curso por clase, CHECKs de enums y de coherencia propósito–algoritmo, y triggers que impiden borrar llaves, editar la bitácora y borrar jobs.

## Correcciones aplicadas por DECISIONES.md

- La historia supone la columna `crypto_ops.count` → se crea `count int NOT NULL DEFAULT 1 CHECK (count >= 1)`: confirmado por DECISIONES N-05.
- El enum de verbos del modelo (8 verbos) → se agrega `export` (para `cli export-kek`, US-116): corregido por DECISIONES N-05.
- `CryptoJob.kind` (`rotate`, `reencrypt`, `migrate_provider`) → se agrega `rewrap` (US-199): corregido por DECISIONES N-05.
- La historia no prevé dónde queda el propósito de un descifrado → se agrega `crypto_ops.purpose text NULL` (valores validados en código: `mask`, `reveal`, `notify`, `auth_link`, `export`), porque el descifrado del enmascarado "queda en `crypto_ops` (verbo `decrypt`, propósito `mask`)": corregido por DECISIONES N-01 (y N-21 para `notify`, `auth_link`).
- `crypto_ops.user_id` nulo en CLI y worker (US-029) → `user_id NOT NULL`; CLI y worker usan `SYSTEM_USER_ID` o el usuario de `--as`: corregido por DECISIONES N-15. Sin llave foránea a `auth.users` (core no depende de un módulo; además `0004_auth` corre después).
- Criterio 1 "la migración crea el esquema `crypto`" → el esquema lo crea `0001_core_schemas` (US-012); `0003_crypto` solo crea tablas, funciones e índices, y su `downgrade` no borra el esquema. Corregido por la numeración canónica de migraciones de la especificación del desglose.

## Validación contra el dominio

- Aggregates `CryptoKey`, `CryptoOp` y entidad `CryptoJob` (02_domain_model 2.13): todas las columnas del modelo están presentes, más `count`, `purpose` y `rewrap`/`export` por DECISIONES.
- Invariante "una sola llave `active` por (`purpose`, `data_class`)": índice único parcial en la base.
- Invariante "rotar deja la anterior en `decrypt_only` hasta que el job termine": el trigger de `crypto_keys` solo permite las transiciones `active → decrypt_only`, `decrypt_only → retired` y `active → retired` (esta última la usa la rotación de índice de US-030); nunca vuelve a `active`.
- RN-14 (llaves nunca se borran): trigger sin `DELETE` ni `TRUNCATE` en `crypto_keys`; `crypto_ops` append-only.
- "El material en claro nunca se persiste": `wrapped_material bytea` solo recibe la salida de `KeyProvider.wrap` (prueba de desigualdad con la DEK en US-025).
- Sin eventos ni funciones puras.

## Validación contra la arquitectura

- Modelos en `core/crypto/models.py`, previsto en el árbol de `05_service_design.md`; heredan `Base` y `CommonColumnsMixin` de `core/db.py`.
- Las tablas no son `__audited__`: su bitácora propia es `crypto_ops`. La prueba de tablas auditadas de US-107 las debe listar como exclusión explícita.
- Ningún módulo de negocio importa `core.crypto.models`; solo el bus, el keyring y `core/crypto/service.py`.
- Sin router (llega en EP-18), sin rol, sin paginación.
- Triggers PL/pgSQL como exige `04_architecture_decision.md` sección 7 para `crypto_ops`.

## Preguntas abiertas

- Pregunta: ¿`crypto_keys.rotate_by` es el usuario que ejecutó la rotación (`UUID`, se llena en la llave anterior al rotarla) o la fecha límite para rotar la llave (`TIMESTAMPTZ`, política de vida de la llave)?
- Alternativa propuesta por defecto: usuario que rotó, `rotate_by uuid NULL`, sin llave foránea, llenado junto con `rotated_at` en la llave que pasa a `decrypt_only` (es lo que describe US-030 criterio 1). Si se quiere una fecha límite, se agrega después como columna nueva `rotate_before` en el rango de EP-18 sin tocar esta migración.

## Tareas

### Migración Alembic
- [ ] T1 · `api/migrations/versions/0003_crypto.py` (`down_revision = "0002_audit_log"`): tabla `crypto.crypto_keys` con `id uuid PK`, `purpose text NOT NULL CHECK (purpose IN ('encrypt','index','sign'))`, `data_class text NOT NULL CHECK (data_class ~ '^[a-z_]+\.[a-z_]+$')`, `algorithm text NOT NULL CHECK (algorithm IN ('A256GCM','HMAC-SHA256','Ed25519','ML-DSA-65'))`, CHECK de coherencia (`encrypt`→`A256GCM`, `index`→`HMAC-SHA256`, `sign`→`Ed25519`|`ML-DSA-65`), `provider text NOT NULL CHECK (provider IN ('local','openbao'))`, `version int NOT NULL CHECK (version > 0)`, `state text NOT NULL CHECK (state IN ('active','decrypt_only','retired'))`, `wrapped_material bytea NOT NULL`, `rotated_at timestamptz NULL`, `rotate_by uuid NULL` (sujeto a la pregunta abierta), `created_at`, `updated_at` (`timestamptz NOT NULL DEFAULT now()`), `created_by uuid NOT NULL`; `UNIQUE (purpose, data_class, version)`; índice único parcial `uq_crypto_keys_active ON (purpose, data_class) WHERE state = 'active'` — 1,5 h
- [ ] T2 · En la misma migración, `crypto.crypto_ops`: `id uuid PK`, `at timestamptz NOT NULL DEFAULT now()`, `user_id uuid NOT NULL`, `verb text NOT NULL CHECK (verb IN ('encrypt','decrypt','index','sign','verify','wrap','unwrap','rotate','export'))`, `data_class text NULL`, `key_id uuid NULL`, `key_version int NULL`, `record_id uuid NULL`, `purpose text NULL`, `result text NOT NULL CHECK (result IN ('ok','error'))`, `batch_id uuid NULL`, `count int NOT NULL DEFAULT 1 CHECK (count >= 1)`, columnas comunes; índices `(at DESC)`, `(data_class, at DESC)`, `(key_id)`, `(batch_id) WHERE batch_id IS NOT NULL`, `(record_id) WHERE record_id IS NOT NULL` — 1 h
- [ ] T3 · En la misma migración, `crypto.crypto_jobs`: `id uuid PK`, `kind text NOT NULL CHECK (kind IN ('rotate','reencrypt','migrate_provider','rewrap'))`, `data_class text NULL`, `status text NOT NULL CHECK (status IN ('pending','running','done','failed'))`, `total int NOT NULL DEFAULT 0 CHECK (total >= 0)`, `done int NOT NULL DEFAULT 0 CHECK (done >= 0 AND done <= total)`, `started_at`, `finished_at timestamptz NULL`, `error text NULL`, columnas comunes; índice único parcial `uq_crypto_jobs_in_progress ON (coalesce(data_class, '*')) WHERE status IN ('pending','running')` (una rotación en curso por clase, requerido por US-030; los jobs globales usan `*`) — 1 h
- [ ] T4 · Funciones y triggers: `crypto.forbid_ops_mutation()` `BEFORE UPDATE OR DELETE` en `crypto_ops` y `BEFORE TRUNCATE` (statement); `crypto.guard_keys_update()` `BEFORE UPDATE OR DELETE` en `crypto_keys`: rechaza `DELETE`, rechaza cualquier cambio fuera de `state`, `rotated_at`, `rotate_by`, `updated_at` (comparando `OLD` y `NEW` columna por columna con `IS DISTINCT FROM`) y transiciones de `state` distintas de las tres permitidas; `BEFORE TRUNCATE` en `crypto_keys`; `crypto.guard_jobs_mutation()` rechaza `DELETE` y cambios fuera de `status`, `total`, `done`, `started_at`, `finished_at`, `error`, `updated_at`. Mensajes con `ERRCODE` `check_violation` y texto en español. `downgrade()` borra triggers, funciones y las tres tablas en orden inverso (no borra el esquema) — 2 h

### Models
- [ ] T5 · `api/src/app/core/crypto/models.py`: `CryptoKey`, `CryptoOp`, `CryptoJob` con `__table_args__ = {"schema": "crypto"}` más los `CheckConstraint`/`Index` reflejados para que `alembic check` no detecte diferencias; tipos `Literal` exportados (`KeyPurpose`, `KeyState`, `Algorithm`, `Provider`, `OpVerb`, `OpResult`, `OpPurpose`, `JobKind`, `JobStatus`); sin `__audited__`; `CryptoKey.__repr__` sin `wrapped_material` — 2 h

### Service
- No aplica (el uso de las tablas está en US-025, US-029 y US-030).

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- No aplica.

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/crypto/test_crypto_tables.py`: segunda llave `active` del mismo par falla (`IntegrityError`); `algorithm='DES'` falla; `purpose='encrypt'` con `algorithm='Ed25519'` falla; `UPDATE` y `DELETE` sobre `crypto_ops` fallan; `DELETE` sobre `crypto_keys` falla; `UPDATE` de `wrapped_material` falla; `UPDATE state` de `retired` a `active` falla; `UPDATE state` de `active` a `decrypt_only` con `rotated_at` pasa; `DELETE` sobre `crypto_jobs` falla; `UPDATE done` pasa; segundo job `running` de la misma clase falla; `count = 0` falla — 3 h
- [ ] T7 · `api/tests/migrations/test_0003_crypto.py`: `upgrade head`, `downgrade -1` (tablas y funciones desaparecen, el esquema `crypto` sigue) y `upgrade head` otra vez sobre base vacía — 1 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T8 · Registrar `crypto.crypto_keys`, `crypto.crypto_ops` y `crypto.crypto_jobs` como exclusiones explícitas (con comentario "bitácora propia") en la prueba de tablas auditadas de US-107 (`api/tests/architecture/test_audited_tables.py`); `test_no_cross_models.py` sigue verde — 0,5 h

### Front
- No aplica.

### DevOps
- No aplica.

### Seguridad
- [ ] T9 · Revisión: ninguna columna admite material en claro (solo `bytea` envuelto), `crypto_ops` no tiene columnas para valores ni blobs, triggers cubren también `TRUNCATE`, el rol de la aplicación no es dueño de las funciones de trigger (no puede desactivarlas con `ALTER TABLE ... DISABLE TRIGGER` si se separan roles en EP-13) — 1 h

## Orden de ejecución
1. Resolver la pregunta abierta (tipo de `rotate_by`)
2. T6 y T7 escritos primero (fallan sin migración)
3. T1, T2, T3, T4
4. T5
5. T8, T9

## Dependencias técnicas
- US-012 · Base de datos y Alembic multiesquema: `Base`, `CommonColumnsMixin`, esquema `crypto` en `0001_core_schemas`.
- US-015 · Tabla de auditoría (`0002_audit_log`): es el `down_revision` de `0003_crypto`.
- US-107 · Prueba de tablas auditadas: recibe las exclusiones de T8.

## Endpoints
- Ninguno.

## Riesgos
- El trigger de `crypto_keys` no deja cambiar `wrapped_material` ni `provider`, pero US-135 (migrar a OpenBao) y US-199 (re-envolver con ML-KEM) necesitan hacerlo: EP-15 y EP-26 quedarían bloqueadas — mitigación: EP-15 agrega en su rango (0030-0034) una migración que reemplaza `crypto.guard_keys_update()` permitiendo `wrapped_material` y `provider` solo junto con un job `migrate_provider` o `rewrap` en curso; nunca se edita `0003_crypto`.
- Tipo equivocado de `rotate_by`: corregirlo con datos exige migración en tres pasos — mitigación: la pregunta abierta se resuelve antes de aplicar la migración.
- `purpose` sin CHECK en la base: un valor mal escrito entra — mitigación: `OpPurpose` como `Literal` validado en el oplog (US-029) y prueba de que un propósito desconocido lanza error.
- Crecimiento de `crypto_ops`: una fila por operación individual — mitigación: agregación por lote (US-029) e índices por `at` para la consulta paginada de EP-18.

## Estimación
- Backend: 7,5 h
- Front: 0 h
- Pruebas: 4,5 h
- DevOps / seguridad: 1 h
- **Total: 13 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/crypto/test_crypto_tables.py tests/migrations/test_0003_crypto.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `psql -c "\d crypto.crypto_keys"` muestra `uq_crypto_keys_active` parcial y el trigger; `psql -c "DELETE FROM crypto.crypto_ops"` falla con el mensaje del trigger
- [ ] `cd api && uv run alembic check` sin diferencias entre modelos y migración
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.crypto --cov-fail-under=80`
