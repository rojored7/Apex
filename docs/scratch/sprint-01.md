# Cuaderno · Sprint 1 · Núcleo de auditoría, bus de criptografía y seguridad

Rama `feat/sprint-01-nucleo-cripto-seguridad`, creada desde `main` el 2026-10-21 tras el
merge local (fast-forward) de `chore/sprint-00-cimientos` (`ca8415f`). El push a GitHub
lo bloquea el clasificador de permisos de la sesión: queda como paso humano.

## Línea base (2026-10-21)

- `git status` limpio en `main` = `ca8415f`.
- api: 106 pruebas en verde, 1 saltada; cobertura 93 % (cierre del Sprint 0).
- web: 75 pruebas en verde; cobertura 100 %.
- Stack de desarrollo arriba: `apex-db-1`, `apex-db_test-1`, `apex-api-1`, `apex-web-1`
  en los puertos 8180/8181/5442/5443 (`.env` local).

## Slices

### S1-W0-1 · Cabeceras de seguridad y CSP con nonce (US-038)

- Rojo: `web/tests/unit/index-html.test.ts` (2 de 5 fallaban: sin `nonce` en `<script>` y `<link>`),
  `web/tests/e2e/csp.spec.ts`, `scripts/smoke/headers.sh`.
- Verde: `vite.config.ts` (`html.cspNonce`, `modulePreload.polyfill=false`),
  `infra/nginx/snippets/{security-headers,proxy-api}.conf`, `default.conf` con CSP exacta,
  `sub_filter` de `__CSP_NONCE__` → `$request_id`, `no-store`, `location /api/v1/tv/` (N-44),
  `web/Dockerfile` copia los snippets; `test_nginx_conf.sh` ampliado (26 comprobaciones);
  `compose-smoke.sh` llama a `headers.sh`.
- Evidencia: `headers.sh` contra Nginx real en 8180: 19 ok, 0 fallas (nonces distintos entre
  peticiones, 413 con 6 MB). Playwright `csp.spec.ts`: 2 ok sobre `vite preview` (interceptando
  como Nginx) y 1 ok + 1 saltada con `CSP_BASE_URL=http://localhost:8180/`. `web-smoke.sh` 5/5.
  `slice-gate.sh web/app tests/unit/index-html.test.ts` verde.
- Desviaciones: no hay script de tema inicial, así que T3 (`theme-init.js`) no aplica. El smoke de
  cabeceras corre dentro del job `images` (vía `compose-smoke.sh`), no en un job `smoke-headers`
  aparte: los nombres de los checks obligatorios no cambian. La prueba del HTML construido corre en
  entorno node y construye con la API de Vite a un directorio temporal.

### S1-B1 · Tabla de auditoría y cadena de hashes (US-015 + T1 de US-027)

- Paso previo: `pg_dump -Fc` de la base de desarrollo antes de `0002` en
  `docs/scratch/sprint-01-antes-0002.dump` (3,6 KB; ignorado por git por `*.dump`).
- Rojo: `tests/crypto/test_digest.py`, `tests/core/test_audit_chain.py`, `test_audit_log_db.py`,
  `test_audit_concurrency.py` sobre stubs con `NotImplementedError`: 20 fallos + 10 errores (la
  tabla no existía). `test_core_import_direction.py` (T11) ya existía desde US-014.
- Verde: `core/crypto/digest.py` (`sha256_hex`, solo `hashlib`), `core/audit.py` (`canonical`
  con la especificación irreversible en el docstring, `chain_hash`, `verify_chain`, `AuditEntry`,
  `append_entry` con `pg_advisory_xact_lock(4_270_002)` y `seq = último + 1`, `record`),
  migración `0002_audit_log` (CHECKs de acción con `download`, hex de 64, espejo; 4 índices;
  `audit.forbid_mutation()` con triggers de fila y de TRUNCATE).
- Evidencia: `slice-gate.sh core/audit` (46 ok, 1 saltada), `slice-gate.sh crypto` (23 ok);
  cobertura 100 % de `audit.py` y `digest.py`; ciclo de Alembic en la base de desarrollo
  (`upgrade head` → `downgrade -1` → `upgrade head`, `current` = `0002_audit_log (head)`);
  `TRUNCATE audit.audit_log` en psql rechazado por `audit.forbid_mutation()`; 10 transacciones
  concurrentes dejan `seq` 1..10 y cadena válida; `grep hashlib audit.py` vacío.
- Ajustes: `test_migrations.py` ahora compara con el head del `ScriptDirectory` y baja hasta
  `base` (antes asumía `0001`). `rows_checked` cuenta hasta la primera ruptura inclusive.
- Seguridad (T13): escritura solo con `insert()` de Core; trigger cubre TRUNCATE; lock `xact`;
  `digest` no toca `crypto_ops`. Los valores en claro de campos cifrados los evita US-016.

### S1-B2 · Hook de auditoría (US-016)

- Rojo: `tests/core/test_audit_serialize.py`, `test_audit_hook_db.py`, `test_audit_hook_perf.py`,
  `test_audit_actor_http.py` sobre stubs: 15 fallos + 12 errores.
- Verde: `core/context.py` completo (`SYSTEM_USER_ID`, `current_actor`, `get_actor`,
  `actor_scope`, `MissingActorError` con el mensaje de los criterios 7 y 8); en `core/audit.py`
  `serialize_value`, `serialize_row` (sin técnicas, `"***"` para `__audit_redact__` como pide
  US-041, guarda `PlaintextInAuditError`), `diff_row`, listeners `before_flush` (`created_by`)
  y `after_flush` (insert/update/delete, `__audit_exclude__`, `__audit_subject__`, columnas
  cifradas por `is_encrypted`), `install_audit_listeners()` idempotente sobre `Session`;
  `record`/`append_entry` toman el actor del contexto si no se les pasa y aceptan
  `subject_member_id`. `create_app` instala los listeners y corre los pasos de arranque bajo
  `actor_scope(SYSTEM_USER_ID)`; `tests/conftest.py` los instala una vez.
- `0002_audit_log` corregida antes de cualquier push: columna `subject_member_id` e índice
  `ix_audit_log_subject_member_seq` (G-05; el plan del sprint los pone en `0002`). Solo estaba
  aplicada en las bases locales de desarrollo y prueba, que se bajaron a `base` y volvieron a
  `head`. `subject_member_id` entra al hash solo cuando no es nulo (US-106 T8).
- Evidencia: 55 casos de auditoría en verde; 500 inserciones auditadas en una transacción muy
  por debajo de 5 s; cadena válida tras varios flushes; el actor de una dependencia async llega
  al commit del teardown de `get_session`; suite completa 165 ok + 1 saltada, cobertura 95 %.
- Hallazgo de entorno: `localhost` resuelve a `::1` primero y `db_test` solo escucha en IPv4;
  en Windows el rechazo tarda 2 s, así que `/health` (límite 2 s) devolvía 503 y la suite tardaba
  117 s. `TEST_DATABASE_URL` pasa a `127.0.0.1` en `.env` y `.env.example` (con nota); la suite
  baja a 9 s. `test_migrations.py`, `test_migration_lock.py` y `test_startup_failure.py` dejan
  de asumir `0001` como head.
- Diferido por plan: `tests/core/test_audit_hook_encrypted.py` con el `Encrypted` real llega en
  S1-B7; la guarda ya se prueba aquí con un tipo falso que expone `is_encrypted`.

### S1-B3 · Paginación, OpenAPI y fronteras (US-019, US-021, US-022)

- Rojo: `tests/core/test_pagination_db.py`, `test_pagination_router.py`, `test_openapi_export.py`,
  `tests/architecture/test_list_routes_use_page_params.py`, `test_no_cross_models.py`,
  `test_find_forbidden_imports.py` sobre stubs: 25 fallos, 7 ok (las validaciones de FastAPI
  ya funcionaban solas).
- Verde: `core/pagination.py` (`PageParams` como dataclass con `Annotated[int, Query(...)]`,
  `Page[T]` con `extra="forbid"`, `SearchQuery` de 100, `paginate` que cuenta sobre la
  subconsulta y agrega la clave primaria al `ORDER BY`, `to_page`); `cli.py` con Typer (MIT;
  trae `rich` MIT, `shellingham` ISC y `click` BSD-3: licencias en verde, `NOTICE`
  regenerado) y `export-openapi` sobre `Settings.model_construct` con marcadores;
  `tests/architecture/_imports.py` con `find_forbidden_imports` (relativos, dentro de funciones,
  `TYPE_CHECKING`, alias, `importlib.import_module` literal; `ALLOW_FOREIGN_SCHEMAS = True`
  por la decisión del gate); `docs/openapi.json` versionado (309 líneas, `info.version` =
  `0.1.0` del paquete, no `APP_VERSION`); `.gitattributes` con `docs/openapi.json text eol=lf`;
  CI con los pasos "fronteras entre módulos" y "openapi al día" (falla con `::error::` y el
  comando a correr).
- Evidencia: 51 ok + 1 saltada entre los seis archivos y toda `tests/architecture`; dos
  exportaciones idénticas byte a byte; exportación sin variables del api ni `.env`;
  `test_docs_openapi_json_esta_al_dia` compara el archivo versionado con la exportación.
- Observación: con un solo comando Typer exige un `@app.callback()` para mantener el modo de
  subcomandos (`export-openapi` como argumento). `Page[X]` de Pydantic es una subclase
  parametrizada, no un alias de `typing`: la prueba de arquitectura usa `issubclass`.

### S1-B4 · KeyProvider, tablas crypto y llaves en el volumen (US-023, US-024)

- Rojo: `tests/crypto/test_local_provider.py`, `test_init_keys.py`, `test_provider_startup.py`,
  `test_crypto_tables.py`, `tests/migrations/test_0003_crypto.py`,
  `tests/architecture/test_audited_tables.py` sobre stubs: 22 fallos + 8 errores, 3 ok (las de
  tablas auditadas pasan con solo los modelos), 2 saltadas (modo POSIX, solo fuera de Windows).
- Verde: `core/crypto/errors.py` (`CryptoError` con `code`, sin bytes), `provider.py`
  (`KeyInfo`, `KeyProvider` async, `get_key_provider`, `configure_provider`/`current_provider`),
  `local_provider.py` (`apxw1 || nonce || AES-256-GCM(kek, dek, aad)`, Ed25519 con semilla
  cruda, `parse_wrapped` puro, `check_key_file` sin leer contenido; permisos solo fuera de
  `nt`), `core/crypto/models.py` (`CryptoKey`, `CryptoOp`, `CryptoJob` con CHECKs e índices
  parciales), `core/security.py` mínimo (par JWT Ed25519 en PEM; US-032/033 lo extienden),
  `cli init-keys [--dir] [--as] [--data-class]` idempotente (A-1: nunca sobrescribe, completa lo
  que falta; `--data-class` responde 2 hasta US-140), migración `0003_crypto` (tres tablas,
  `forbid_ops_mutation`, `guard_keys_update` con transiciones, `guard_jobs_mutation`, TRUNCATE
  cubierto), `Settings.CRYPTO_LOCAL_SIGNING_KEY_PATH`, gancho en el `lifespan` (el proveedor se
  abre antes de los pasos de arranque; sin KEK el proceso termina con log sin material),
  `conftest` con llaves reales por sesión (`claves_prueba`), `compose-smoke.sh` corre
  `tools init-keys` antes de arrancar el api, `.gitignore`/`.dockerignore` con `jwt_ed25519.pub`.
- Evidencia: 37 ok + 2 saltadas en los seis archivos; suite completa 230 ok + 3 saltadas; ruff y
  mypy limpios. En el stack de desarrollo (Linux): `tools init-keys` creó `kek.bin` (32 B),
  `sign-ed25519.key` (32 B), `jwt_ed25519.pem` y `.pub` con `-rw-------` y dueño `apex` (10001);
  el api arrancó con "proveedor de llaves listo: local" y `/health` 200. Ciclo de `0003`
  (`downgrade 0002_audit_log` deja el esquema `crypto` sin tablas ni funciones; `upgrade head`).
- Desviaciones: `init-keys` es idempotente con código 0 (A-1 del plan del sprint) en vez del
  código 1 del desglose T8 de US-023. Las comprobaciones de modo 600/700 se saltan en Windows
  (NTFS no tiene modo POSIX) y se verificaron en el contenedor; el directorio del volumen ya
  existía con 755 (lo crea Docker), así que `mkdir 700` no aplica ahí. `migrations/helpers.py`
  no es importable desde los archivos de versión (Alembic los carga por ruta): `0003` declara
  las columnas comunes en el propio archivo. `.claude/worktrees/` queda ignorado: el agente de
  front trabaja en un worktree dentro del repo y `checkpoint-commit.sh` hace `git add -A`.
- Seguridad (T16, T9): la KEK no tiene accesor público ni aparece en `repr` ni en excepciones;
  `init-keys` no acepta material por argumento; `crypto_ops` no tiene columnas de valores;
  triggers cubren TRUNCATE. Pendiente de EP-13: separar el rol de la aplicación del dueño de los
  triggers.

### S1-B5 · Cifrado AES-256-GCM e índice ciego (US-025, US-026)

- Rojo: `tests/crypto/{test_blob,test_registry,test_normalize,test_bus_encrypt,test_bootstrap,
  test_bus_no_leak,test_blind_index}.py` sobre stubs: 37 fallos + 15 errores; fixtures nuevas en
  `tests/crypto/conftest.py` (`proveedor_local`, `sin_llaves`, `bus_listo`).
- Verde: `registry.py` (cinco clases de v0.1 con `index_kind` y `value_type`, `override_registry`
  solo para pruebas), `blob.py` (`apx1` de cinco partes, base64url sin relleno, errores sin el
  blob), `aead.py` (único `AESGCM` fuera del proveedor; un solo mensaje para AAD y alteración),
  `mac.py` (`hmac` solo aquí), `normalize.py` (N-02: `generic`, `phone` con el `57` solo a 12
  dígitos, `email`), `keyring.py` (`LoadedKey` con `bytearray` sin `repr`, `active_for`, `get`,
  `load_all`, `refresh_if_stale`, `ensure_loaded`, keyring del proceso), `bootstrap.py`
  (`ensure_keys` con `INSERT ... ON CONFLICT (purpose, data_class) WHERE state = 'active' DO
  NOTHING`, DEK y llaves `index`, `created_by = SYSTEM_USER_ID`), `bus.py` (`encrypt`, `decrypt`,
  `blind_index`, `aad_for`, `digest`), `docs/adr/ADR-002-criptografia.md` en borrador (envoltura,
  blob y AAD, normalización), `create_app` corre `ensure_keys` bajo `actor_scope(SYSTEM_USER_ID)`
  antes de los pasos de arranque y retira el keyring al apagar.
- Evidencia: 90 ok + 2 saltadas en `tests/crypto`; suite completa 287 ok + 3 saltadas; ruff y
  mypy limpios. Stack de desarrollo: al reiniciar el api, "llaves del bus cargadas:
  Keyring(llaves=8, activas=8)"; en `crypto.crypto_keys` hay 5 llaves `encrypt` (A256GCM) y 3
  `index` (HMAC-SHA256), todas `active`, `version` 1, `created_by` = `SYSTEM_USER_ID`,
  `wrapped_material` de 65 bytes con prefijo `apxw1` y sin material en claro; `/health` 200.
  Dos `ensure_keys` concurrentes en dos sesiones reales dejan una sola llave por clase.
- Observaciones: el predicado del índice parcial en `ON CONFLICT` debe ir literal (con un
  parámetro ligado PostgreSQL no reconoce el índice). La marca de frescura del keyring usa
  conteo, `max(updated_at)` y la firma `id:state` (dentro de una misma transacción dos cambios
  de estado comparten `now()`). "Con una KEK equivocada el api no arranca" se demuestra con
  `test_otra_kek_no_abre_la_envuelta` (unwrap falla) y no contra el volumen de desarrollo, porque
  reemplazar la KEK destruiría las DEK reales. `oplog.record` y `refresh_if_stale` por unidad de
  trabajo llegan en S1-B6 (US-029).

### S1-B6 · Firma y bitácora por lote (US-027, US-029)

- Rojo: `tests/crypto/{test_signature_format,test_sign,test_oplog_aggregate,test_oplog}.py` y la
  ampliación de `tests/architecture/test_core_import_direction.py` (absorbe el grafo de US-029:
  `context.py` solo biblioteca estándar, `db.py` sin `audit`/`crypto`, sin ciclos entre módulos
  de `core` a nivel de módulo): 17 fallos + 12 errores.
- Verde: `signature.py` (`apx1.<key_id>.<alg>.<sig_b64url>`), `bus.sign`/`bus.verify` async vía
  `KeyProvider` (la privada nunca sale; `verify` acepta `active`, `decrypt_only` y `retired`,
  Q27; una firma de otra clase lanza `key_missing`), llaves `sign` como referencia
  `local:sign-ed25519` en `crypto_keys` (`ensure_keys` las crea para clases con `sign=True`;
  ninguna de negocio en v0.1), `oplog.py` (buffer por unidad de trabajo en `ContextVar`,
  `record`, `aggregate_ops`, `batch`, `before_commit` que inserta en la misma transacción,
  `after_soft_rollback` que conserva `error` y `decrypt` por conexión aparte,
  `flush_standalone`), verbos cableados en `encrypt`/`decrypt`/`blind_index`/`sign`/`verify`,
  `unwrap` en el keyring y `wrap` en `ensure_keys`; `purpose` y `record_id` como argumentos con
  nombre; `batch_scope` en `context.py`; `refresh_keyring` como dependencia de los routers de
  módulos (no de `/health`); `unit_of_work(actor)` en `cli.py`; listeners instalados en
  `create_app` y `conftest`.
- Evidencia: 35 ok en los cinco archivos; suite completa 316 ok + 3 saltadas; ruff y mypy
  limpios. Transacciones reales: cifrar deja una fila `encrypt` con `record_id` y el actor; 500
  descifrados en `bus.batch` dejan una fila `count = 500` con `batch_id` y `purpose = mask`; un
  descifrado con AAD ajeno seguido de rollback deja una fila `error` con su `record_id`; ninguna
  fila contiene blob ni texto (`row_to_json`); sin actor el commit falla con "falta el actor".
  Stack de desarrollo: al arrancar, `crypto_ops` recibe 8 filas `unwrap` con `SYSTEM_USER_ID`.
- Decisiones de implementación: fuera de `bus.batch` cada operación es una fila (conserva su
  `record_id`), también bajo `batch_scope`, que solo fija el `batch_id`; `verify` inválido se
  registra con `result = error` sin lanzar. La resolución de `--as <email>` a un usuario llega
  con `auth.service` (US-041/US-111): `unit_of_work` usa `SYSTEM_USER_ID` por ahora.

### S1-B7 · Tipos de columna (US-028)

- Rojo: `tests/crypto/{test_secret,test_types,test_types_key_check}.py`,
  `tests/core/{test_audit_encrypted,test_audit_hook_encrypted}.py` y el modelo de prueba
  `tests/crypto/models_fixture.py` (cinco `Encrypted`, tres `BlindIndexed`, esquema
  `test_crypto` creado dentro del savepoint): rojo en la recolección (los stubs levantan al
  definir el modelo).
- Verde: `secret.py` (`Secret` pendiente/sellado; `repr`/`str` = `Secret(•••)`; `json`,
  `pickle` y Pydantic fallan; igualdad solo entre blobs; `canonical_json`), `types.py`
  (`Encrypted` con `is_encrypted`, solo deja pasar blobs `apx1` válidos también por `INSERT` de
  Core; `BlindIndexed(data_class, source=...)`; `before_flush` que asigna `id`, rechaza cambios
  de `id` (`id_immutable`), cifra con `aad = id` según `value_type`, llena el `_idx` en el mismo
  flush, deja `NULL` en ambas con `None`, rechaza `_idx` a mano (`index_manual`) y comprueba la
  llave vigente con `SELECT ... FOR SHARE` (`crypto_key_changed`); `reveal(obj, campo,
  proposito)`), auditoría pasando las columnas `is_encrypted` por `process_bind_param` (sin
  importar `core.crypto`), listener registrado en `create_app` y `conftest`.
- Evidencia: 20 ok en el slice; suite completa 336 ok + 3 saltadas; ruff y mypy limpios. En
  `db_test`: `row_to_json` de la fila no contiene ningún valor en claro y sí cinco blobs
  `apx1.`; `document_idx` coincide con `blind_index("member.document", "1020304")`; cambiar el
  teléfono recifra y reindexa en el mismo flush; `date` y `dict` vuelven con su tipo; un blob
  copiado a otro registro no se abre (`decrypt_failed`); una rotación simulada desde otra
  sesión hace fallar el flush con `crypto_key_changed`; la auditoría guarda el blob en
  `before`/`after` y nunca el claro ni `Secret(`; el `SELECT` por índice ciego encuentra al socio.
- Observación: SQLAlchemy envuelve el error del `TypeDecorator` en `StatementError` con el
  `CryptoError` original en `orig` (así lo prueba el caso de Core). El tipo falso de
  `test_audit_hook_db.py` implementa ahora `process_bind_param`, como exige el contrato.

### S1-B8 · Contraseñas y JWT (US-032, US-033)

- Rojo: `tests/core/test_passwords.py` y `tests/core/test_jwt.py` sobre stubs: 4 fallos + 23
  errores.
- Verde: `Settings` con `ARGON2_TIME_COST`, `ARGON2_MEMORY_COST_KIB`, `ARGON2_PARALLELISM`,
  `PASSWORD_MIN_LENGTH`, `ACCESS_TOKEN_TTL_S`, `REFRESH_TOKEN_TTL_DAYS`, `JWT_LEEWAY_S` (en
  producción argon2 no baja de los valores por defecto); `core/security.py` con argon2id
  (`hash_password`, `verify_password`, `needs_rehash`, `dummy_verify`, política N-10 con
  `common_passwords.txt` de 303 entradas en el paquete), JWT `EdDSA` (`load_jwt_keys` con
  `StartupError` sin contenido y comprobación de `JWT_PUBLIC_KEY_PATH`, `access_claims` pura,
  `create_access_token`, `decode_access_token` con `exp`/`iat` comparados contra `core/clock`
  y tolerancia de 30 s, `TokenExpired`/`TokenInvalid`), refresh opaco (`new_opaque_token`,
  `hash_opaque_token`, `new_refresh_token`), `configure_security(settings)` llamado en el
  lifespan antes del proveedor de llaves.
- Evidencia: 27 ok en los dos archivos; suite completa 363 ok + 3 saltadas; ruff y mypy
  limpios. Vencido a los 16 min, válido a los 15 min 20 s; otra llave Ed25519, `alg: none`,
  HS256 con la pública como secreto (forjado a mano porque PyJWT se niega a emitirlo), claims
  faltantes, `role` ajeno y `sub` no UUID → `TokenInvalid`; llave RSA, archivo vacío o
  inexistente y pública que no coincide → `StartupError` con el nombre de la variable y sin
  PEM; ni contraseñas, hashes, tokens ni la privada en `caplog`. El api de desarrollo arranca
  con la llave JWT del volumen (`/health` 200).
- Decisión: `exp` e `iat` se validan en el api contra el reloj de `core/clock` (PyJWT solo
  valida firma y claims obligatorios), así las pruebas usan `FrozenClock` y el api tiene un
  solo reloj. `jwt`, `cryptography`, `hashlib` y `hmac` entran en `tests/core/test_jwt.py` con
  `noqa: TID251` solo para forjar tokens de ataque; `src/app` sigue limpio.

### S1-B9 · `current_user`, `require_role` y prueba de rutas (US-034, US-035)

- Rojo: `tests/core/test_require_role.py`, `tests/core/test_docs_disabled.py`,
  `tests/architecture/test_every_route_has_role.py`, `tests/architecture/test_route_guard_unit.py`,
  más `tests/core/_routes.py` (router de prueba) y `tests/core/_principal_double.py` (doble del
  puerto, M-2): rojo en la recolección (el registro del doble en `conftest` era un stub).
- Verde: en `core/security.py` `Principal`, puerto `PrincipalLoader` con `register_principal_loader`
  / `get_principal_loader` (G-02), `role_allowed`, `current_user` (Bearer exacto, `token_expired`
  solo para vencido con firma válida, `SYSTEM_USER_ID` rechazado antes de ir a la base, rol vigente
  de la base y no del claim, fija `current_actor` sin resetearlo), `require_role(*roles)` con
  `__apex_roles__` y validación al definir, `PUBLIC_ROUTES` (7 entradas comentadas),
  `effective_routes` (recorre `effective_route_contexts()` de los routers perezosos de FastAPI
  0.157), `route_has_role_dependency` y `unprotected_routes` (también reporta `Route`/`Mount` y la
  TV sin `__apex_device_token__`, N-44); toda 401 lleva `WWW-Authenticate: Bearer`
  (`core/errors.py`); `RequestLogMiddleware` limpia el actor al terminar la petición (después del
  commit de `get_session`); el lifespan exige un cargador registrado (cerrado por defecto).
- Evidencia: 21 ok en los cuatro archivos; suite completa 384 ok + 3 saltadas; ruff y mypy
  limpios. Admin 200 / coach 403 / member 403 en `staff`; sin cabecera, `Basic`, Bearer vacío y
  dos tokens → 401 `unauthorized`; vencido → 401 `token_expired`; otra llave, `SYSTEM_USER_ID`,
  inexistente y dado de baja → 401 con cuerpos idénticos; el claim `admin` de un coach no sirve;
  el actor es visible en el handler y el `contextvar` queda vacío después; 10 peticiones
  concurrentes no mezclan actores. El api de desarrollo deja de arrancar ("Application startup
  failed") hasta que `auth` registre el cargador real en S1-B11: es la conducta cerrada por
  defecto que pide US-034.
- Desviaciones: `tests/auth/test_principal_loader.py` y `slice-gate.sh auth` pasan a S1-B11 (no
  existe `auth.users` hasta `0004_auth`). `ENV` sigue siendo `dev | production` (decisión del
  Sprint 0) en vez de `dev | test | prod`. La base de prueba se limpia de llaves, bitácoras y
  auditoría al empezar cada sesión de pytest (`migrated_database`), porque las llaves se envuelven
  con la KEK temporal de la sesión. Observación: `UUID(int=1)` es `SYSTEM_USER_ID`; los usuarios
  de prueba empiezan en 101.


### Front S1-F1 a S1-F3 · fusionados desde el worktree del agente

- Merge `6511f47` de la rama `worktree-agent-a970a230434bd76be` (cuatro checkpoints: `b7ade37`,
  `dd66f5f`, `628114a`, `cfdabb4`; 79 archivos, solo `web/` y `docs/scratch/sprint-01-front.md`).
- Verificado en la rama fusionada: `npm ci`, lint, `tsc`, 593 pruebas en 43 archivos, cobertura
  99,63 % de líneas (96,25 % ramas), build de Vite y licencias (12 MIT, 1 ISC) en verde.
- El agente no rodeó el hook `config-protection`: las reglas de ESLint de US-059/060/040 viven en
  `web/tests/lint/restricted-config.ts` y las aplica Vitest sobre `src/`. Pendiente de la persona:
  moverlas a `web/eslint.config.js` si lo autoriza. Usó `credentials: "same-origin"` (US-059,
  N-13). Dependencia nueva: `openapi-typescript` 7.13.0 (MIT, desarrollo). Seis `DESIGN-GAP`
  (velo y ancho del panel sin token, chip "Pendiente de pago", plegado de filtros del portal,
  esquemas de lista y de auditoría aún fuera de `docs/openapi.json`). Detalle en
  `docs/scratch/sprint-01-front.md`.

### S1-B10 · Límite de intentos, CORS y secretos (US-036, US-037, US-039)

- Rojo: `tests/core/test_ratelimit.py`, `test_cors.py`, `test_config_secrets.py` y ampliaciones de
  `test_env_example.py` (sin PEM ni valores base64 largos, `CORS_ORIGINS` vacío) y de
  `test_every_route_has_role.py` (login y forgot con `__apex_rate_limit__` cuando existan):
  29 fallos + 4 errores.
- Verde: `core/ratelimit.py` (`allow` pura con ventana deslizante y `Retry-After`, `client_ip`
  que solo cree en `X-Forwarded-For` desde una red de `TRUSTED_PROXIES`, `SlidingWindowStore`
  con tope de claves y `asyncio.Lock`, dependencia `rate_limit(bucket)` con marca
  `__apex_rate_limit__`), `TooManyRequestsError` 429 `rate_limited` con `Retry-After` (el
  handler de dominio aplica `headers`), `parse_origins` y `CORS_ORIGINS` sin decodificar (lista
  por comas o JSON; `*` y `null` fallan al arrancar con el nombre de la variable),
  `CORSMiddleware` solo con orígenes y sin credenciales, `Settings.trusted_proxies` como redes,
  `RATE_LIMIT_MAX_KEYS`, `missing_secrets`/`check_secrets_or_exit` (solo nombres de variable)
  antes de cargar llaves en el lifespan, `scripts/ci/check-image-secrets.sh` (export de la
  imagen, `.env`, llaves por contenido, `.pem`/`.key`/`.kek` bajo `/app`, `gitleaks dir`),
  `.gitleaks.toml`, job `secrets-scan` (gitleaks sobre todo el historial) y paso de imagen en
  CI, `gitleaks` en `NOTICE`, `.env.example` con `TRUSTED_PROXIES=172.16.0.0/12` documentado.
- Evidencia: 47 ok en el slice; suite completa 424 ok + 3 saltadas; ruff y mypy limpios.
  Sexto intento 429 e intento liberado 61 s después; buckets e IPs independientes; cliente no
  confiable no rota con `X-Forwarded-For`; 429 idéntico para cualquier correo. Preflight solo
  para el origen exacto; con `CORS_ORIGINS` vacío ningún preflight recibe la cabecera.
  `repr`/`dump` de `Settings` muestran `**********`; el arranque sin KEK falla con
  "Faltan secretos: CRYPTO_LOCAL_KEK_PATH" y el log no lleva valores. `check-image-secrets.sh`
  contra `apex-api:local`: 4 de 4 ok (excluye el parser PEM de `cryptography`, que contiene la
  cabecera como constante, y los certificados de CA). `gitleaks git` sobre los 41 commits: sin
  hallazgos. `docs/openapi.json` regenerado (entra el 429).
- Decisiones: la dependencia de `rate_limit` se declara en `auth.router` cuando existan login
  y forgot (US-042, US-048); `X-Forwarded-For` en Nginx sigue siendo `$remote_addr` (decisión de
  seguridad del Sprint 0: Nginx es el primer salto); uvicorn corre con un solo worker por
  defecto. `ENV` se mantiene `dev | production`.

### S1-B11 · Cuentas de usuario y admin inicial (US-041; cierra US-034 T5/T9)

- Rojo: `tests/auth/{test_pure_users,test_seed,test_auth_schema,test_principal_loader}.py`,
  `tests/cli/test_seed_cli.py`, `tests/architecture/test_no_physical_delete_users.py` sobre
  stubs: 11 fallos + 3 errores.
- Verde: migración `0004_auth` (`users` con CHECKs de rol, `member_id` para `member` y correo
  normalizado, índice único parcial `uq_users_email_alive`; `refresh_tokens` con
  `replaced_by_id`; `one_time_tokens`; INSERT del usuario técnico `system@apex.local`
  `00000000-0000-0000-0000-000000000001` inactivo y sin contraseña, N-15), `modules/auth`
  (`models.py` con `__audited__`, `__audit_redact__ = {password_hash}` y `__audit_exclude__ =
  {last_login_at}`; `exceptions.py`; `schemas.py`; `router.py` vacío; `service.py` con las puras,
  `seed_admin` que emite `UserCreated`, `load_active_principal` registrado al importarse como
  cargador real del puerto, `names_for`, `ids_by_email`, `active_admin_id_by_email`),
  `MODULES = ("auth",)`, `ADMIN_EMAIL`/`ADMIN_INITIAL_PASSWORD` (`SecretStr`) como campos de
  `Settings`, `cli seed [--as]` (sale con 2 sin correo, sin contraseña o débil; nunca la imprime;
  `--as` resuelve el correo a un usuario vivo; el actor envuelve el commit).
- Evidencia: 30 ok en el slice; suite completa 441 ok + 3 saltadas; ruff y mypy limpios. En
  `db_test`: la base rechaza `member` sin `member_id`, correo con mayúsculas y rol ajeno; el
  correo se repite solo tras la baja; `seed_admin` deja una fila `insert` con
  `after.password_hash = "***"` y `user_id = SYSTEM_USER_ID`, emite `UserCreated` y el segundo
  seed devuelve `skipped`; el usuario técnico no cuenta como admin activo; el cargador devuelve
  `None` para inactivo, bloqueado, dado de baja, sin contraseña, inexistente y `SYSTEM_USER_ID`.
  Stack de desarrollo: el api vuelve a arrancar (`alembic current` = `0004_auth (head)`, `/health`
  200); `tools seed` rechazó el marcador `cambiar-esto` del `.env` ("no cumple la política:
  too_common"); con una contraseña real (solo en el `.env` local) creó `admin@ejemplo.local`
  con hash `$argon2id$`, la segunda corrida "omitido: ya existe un admin activo", y
  `audit.audit_log` muestra `insert auth.users` con `***` en vez del hash.
- Desviaciones: `validate_password_policy` de auth delega en `core.security` (una sola lista de
  comunes). `test_require_role` vuelve a registrar el doble después de `create_app`, porque
  `auth.service` registra el cargador real al importarse. El `cli seed` corre su corrutina en
  un hilo propio cuando ya hay un loop activo (pruebas async con `CliRunner`).
