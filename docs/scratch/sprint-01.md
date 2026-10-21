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
