# Sprint 1 · Núcleo de auditoría, bus de criptografía y seguridad de plataforma

- Versión: v0.1.
- Épicas:
  - EP-01, el resto;
  - EP-02, salvo US-030 y US-031;
  - EP-03 completa;
  - EP-04, solo US-041;
  - EP-06, el kit sin pantallas.
- Tamaño: 28 historias, 83 puntos y 365 h relativas.
- Rama: `feat/sprint-01-nucleo-cripto-seguridad`.
- Historias del sprint: US-015, US-016, US-019, US-021, US-022, US-023, US-024, US-025, US-026, US-027, US-028, US-029, US-032, US-033, US-034, US-035, US-036, US-037, US-038, US-039, US-040, US-041, US-059, US-060, US-063, US-064, US-065, US-066.

## Objetivo

Dejar listas las tres piezas transversales que todo módulo de negocio usa sin pensar en ellas:
- la cadena de auditoría append-only, escrita sola en `after_flush`;
- el bus de criptografía, que cifra, indexa y firma sin que el llamador elija llave ni algoritmo;
- la seguridad de plataforma: argon2id, JWT Ed25519, `require_role` con `PrincipalLoader`, rate limit, CORS, CSP y secretos.

Al cerrar el sprint existen el usuario técnico y el admin inicial, y el front tiene su cliente tipado y el kit de componentes.

## Demo al final del sprint

1. `docker compose run --rm tools uv run python -m app.cli init-keys` crea la KEK local con permisos 600 en el volumen `keys`, y las DEK por `data_class`. En `crypto.crypto_keys` hay filas `active` con `wrapped_material` y sin material en claro.
2. Una prueba de service guarda un modelo de prueba con una columna `Encrypted`:
   - `SELECT` muestra un valor `apx1.<key_id>.A256GCM.<nonce>.<ct>`;
   - `crypto.crypto_ops` tiene una fila `encrypt` por lote con `count` y `user_id = SYSTEM_USER_ID`.
3. `audit.audit_log`:
   - tiene filas con `seq` consecutivo y `prev_hash` encadenado;
   - `UPDATE audit.audit_log SET action='x'` falla por el trigger `audit.forbid_mutation()`;
   - el blob cifrado aparece en `after`, nunca el texto en claro.
4. `docker compose run --rm tools uv run python -m app.cli seed` crea el admin inicial con `SEED_ADMIN_EMAIL` y `SEED_ADMIN_PASSWORD`. Existe `system@apex.local` con `is_active = false` y UUID `00000000-0000-0000-0000-000000000001`.
5. `uv run pytest tests/architecture -q` en verde. Una ruta de prueba sin `require_role` hace fallar `test_every_route_has_role.py`.
6. `curl -I http://localhost/` muestra:
   - `Content-Security-Policy` con nonce;
   - `X-Frame-Options: DENY`;
   - `X-Content-Type-Options`, `Referrer-Policy` y `Permissions-Policy`;
   - `index.html` con `no-store`.
7. `cd web && npm test -- --run` pasa los componentes del kit: `DataTable`, `Pagination`, `FilterBar`, `Chips`, `PageHeader`, `Tabs`, `KpiCard`, `SidePanel`, `ConfirmModal`, `MaskedValue` y `HistoryAside`, más los tipos generados desde `docs/openapi.json`.

## Dependencias de sprints anteriores

Todo viene del Sprint 0:
- US-002: `banned-api`, mypy estricto y `test_banned_imports.py`.
- US-003: CI con PostgreSQL de servicio.
- US-005: volumen `keys` y servicio `tools`.
- US-006: `default.conf` base.
- US-009: proyecto Vite.
- US-010: `Button`, `Field` y `StatusTag`.
- US-011: `Settings`.
- US-012: `CommonColumnsMixin` con id en Python y `0001`.
- US-013: `Clock`.
- US-014: bus de eventos.
- US-017: envelope de errores.
- US-018: logging.
- US-020: `create_app()` y `register_health_check`.

Decisiones que aplica este sprint:
- G-01: `core/context.py` con actor y lote.
- G-02: `PrincipalLoader`.
- G-05: `subject_member_id` en `0002`.
- N-01: sin columnas `*_hint`.
- N-02: normalización del índice ciego.
- N-04: formato de firma `apx1.<key_id>.<alg>.<sig>`.
- N-05: `count`, `export` y `rewrap` en las tablas crypto.
- N-06: `digest` en `core/crypto`.
- N-08: `download` en el CHECK de acción.
- N-10: contraseña mínima de 12 caracteres.
- N-13: `replaced_by_id`.
- N-15: `SYSTEM_USER_ID`.
- N-30: `seq` bajo lock.
- Refinamiento de US-024: `rotated_by`.
- Refinamiento de US-110: `display_name` en `0004`.
- Códigos 401: `token_expired` y `unauthorized`.

## Historias en orden de ejecución

### Wave 0 · Infraestructura (`devops-wsl2-docker`)

- **Slice S1-W0-1 · Cabeceras de seguridad y CSP.** Historia: US-038.
  - Nginx con CSP y nonce desde `$request_id` (N-14).
  - `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` y `Permissions-Policy`.
  - `index.html` con `no-store`.
  - Sin fuentes remotas.
  - Pruebas: `tests/unit/index-html.test.ts` y `tests/e2e/csp.spec.ts`.
  - Gate: `slice-gate.sh web/app` y el smoke de Nginx.
- **Preparación de S1-B4:** se habilita el servicio `tools` de Compose con el volumen `keys` montado y usuario no root. Es el criterio diferido de US-005, que se cierra en S1-B4.

### Wave 3a · Tests de backend en rojo (`backend-qa-executor`)

- **S1-B1:**
  - `tests/crypto/test_digest.py`;
  - `tests/core/test_audit_chain.py`;
  - `tests/core/test_audit_log_db.py`;
  - `tests/core/test_audit_concurrency.py`.
- **S1-B2:**
  - `tests/core/test_audit_serialize.py`;
  - `tests/core/test_audit_hook_db.py`;
  - `tests/core/test_audit_hook_perf.py`;
  - `tests/core/test_audit_actor_http.py`.
  - `tests/core/test_audit_hook_encrypted.py` se activa en S1-B7.
- **S1-B3:**
  - `tests/core/test_pagination_db.py`;
  - `tests/core/test_pagination_router.py`;
  - `tests/core/test_openapi_export.py`;
  - `tests/architecture/test_list_routes_use_page_params.py`;
  - `tests/architecture/test_no_cross_models.py`;
  - `tests/architecture/test_find_forbidden_imports.py`.
- **S1-B4:**
  - `tests/crypto/test_local_provider.py`;
  - `tests/crypto/test_init_keys.py`;
  - `tests/crypto/test_provider_startup.py`;
  - `tests/crypto/test_crypto_tables.py`;
  - `tests/migrations/test_0003_crypto.py`;
  - `tests/architecture/test_audited_tables.py`.
- **S1-B5:**
  - `tests/crypto/test_blob.py`;
  - `tests/crypto/test_registry.py`;
  - `tests/crypto/test_bus_encrypt.py`;
  - `tests/crypto/test_bootstrap.py`;
  - `tests/crypto/test_bus_no_leak.py`;
  - `tests/crypto/test_normalize.py`;
  - `tests/crypto/test_blind_index.py`.
- **S1-B6:**
  - `tests/crypto/test_signature_format.py`;
  - `tests/crypto/test_sign.py`;
  - `tests/crypto/test_oplog_aggregate.py`;
  - `tests/crypto/test_oplog.py`.
- **S1-B7:**
  - `tests/crypto/test_secret.py`;
  - `tests/crypto/test_types.py`;
  - `tests/crypto/test_types_key_check.py`;
  - `tests/core/test_audit_encrypted.py`.
- **S1-B8:**
  - `tests/core/test_passwords.py`;
  - `tests/core/test_jwt.py`.
- **S1-B9:**
  - `tests/auth/test_principal_loader.py`;
  - `tests/core/test_require_role.py`;
  - `tests/core/test_docs_disabled.py`;
  - `tests/architecture/test_every_route_has_role.py`;
  - `tests/architecture/test_route_guard_unit.py`.
- **S1-B10:**
  - `tests/core/test_ratelimit.py`;
  - `tests/core/test_cors.py`;
  - `tests/core/test_config_secrets.py`.
- **S1-B11:**
  - `tests/auth/test_pure_users.py`;
  - `tests/auth/test_seed.py`;
  - `tests/auth/test_auth_schema.py`;
  - `tests/cli/test_seed_cli.py`;
  - `tests/architecture/test_no_physical_delete_users.py`.

### Wave 3b · Implementación de backend (`backend-implementor`)

- **Slice S1-B1 · Tabla de auditoría y cadena de hashes.** Historia: US-015, con la tarea T1 de US-027 adelantada (`core/crypto/digest.py`, que exige N-06).
  - `core/audit.py`:
    - `canonical`, `chain_hash` y `append_entry`;
    - `record()`, que asigna `seq` como el último más 1 bajo `pg_advisory_xact_lock`. No usa `bigserial`, porque un hueco cuenta como ruptura (N-30);
    - `verify_chain`.
  - **Migración `0002_audit_log`:**
    - `audit.audit_log`;
    - CHECK de `action` que incluye `download` (N-08);
    - `subject_member_id UUID NULL` dentro de la serialización canónica (G-05);
    - función y trigger `audit.forbid_mutation()`;
    - los índices `at`, `(table_name, record_id)`, `user_id`, `(table_name, seq DESC)` y `(subject_member_id, seq DESC)`.
  - Gate: `slice-gate.sh core/audit && slice-gate.sh crypto`, más el ciclo de Alembic.
- **Slice S1-B2 · Hook de auditoría en `after_flush`.** Historia: US-016.
  - `core/context.py` completo (G-01): `SYSTEM_USER_ID`, `current_actor`, `current_batch`, `actor_scope()` y `batch_scope()`.
  - `install_audit_listeners()`, que llama `create_app`. Cierra el criterio diferido de US-020.
  - El hook:
    - llena `created_by` en el `before_flush` (cierra el criterio diferido de US-012);
    - soporta `__audit_redact__` (`"<redacted>"`), `__audit_exclude__` y `__audit_subject__`;
    - en `update` audita solo las columnas que cambiaron;
    - lanza `PlaintextInAuditError`.
  - `SYSTEM_USER_ID` se usa sin llave foránea hasta S1-B11.
  - Gate: `slice-gate.sh core/audit`.
- **Slice S1-B3 · Paginación, OpenAPI y fronteras.** Historias: US-019, US-021 y US-022.
  - `PageParams`, `Page[T]` y `paginate`, con `limit` de 1 a 200 (25 por defecto) y `offset`.
  - `docs/openapi.json`, regenerado y verificado en CI.
  - Prueba de `models` cruzados. Se permiten `schemas.py` y `exceptions.py` ajenos (refinamiento de US-022).
  - Gate: `slice-gate.sh core/pagination && slice-gate.sh core/main`.
- **Slice S1-B4 · KeyProvider y tablas crypto.** Historias: US-023 y US-024.
  - `KeyProvider` con `wrap`, `unwrap`, `sign`, `verify` y `rotate`.
  - `LocalFileProvider`, con la KEK en un archivo 600.
  - `cli init-keys --data-class`, que pide US-140.
  - **Migración `0003_crypto`:**
    - `crypto_keys`, con índice único parcial de una sola llave `active` por (`purpose`, `data_class`), CHECK entre propósito y algoritmo, trigger de transiciones de `state` que impide editar `wrapped_material`, y `rotated_by`;
    - `crypto_ops`, con `count`, `purpose`, `user_id NOT NULL`, el verbo `export` y triggers append-only;
    - `crypto_jobs`, con `kind` que incluye `rewrap` y un solo job en curso por clase.
  - Cierra el criterio diferido de US-005 (servicio `tools`).
  - Gate: `slice-gate.sh crypto`, más el ciclo de Alembic.
- **Slice S1-B5 · Cifrado AES-256-GCM e índice ciego.** Historias: US-025 y US-026.
  - Blob `apx1.<key_id>.A256GCM.<nonce>.<ct>` con `aad` igual al id del registro.
  - `core/crypto/registry.py` con las `data_class` (N-04).
  - Keyring que abre las DEK al arrancar.
  - HMAC-SHA-256 sobre el valor normalizado según N-02: NFKD sin diacríticos, minúsculas, sin espacios, puntos ni guiones; teléfono sin prefijo `57`.
  - Gate: `slice-gate.sh crypto`.
- **Slice S1-B6 · Firma y bitácora por lote.** Historias: US-027 (el resto) y US-029.
  - `sign` y `verify` con el formato `apx1.<key_id>.<alg>.<sig_b64url>`.
  - `bus.batch()` y `oplog.record`, agregado por lote con `count` y `purpose`, leyendo el actor de `core/context.py` (G-01).
  - Gate: `slice-gate.sh crypto`.
- **Slice S1-B7 · Tipos de columna.** Historia: US-028.
  - `Encrypted(data_class)` y `BlindIndexed(data_class)`.
  - `Secret`.
  - Recifrado y reindexado en el mismo flush.
  - El hook guarda el blob por `process_bind_param`.
  - Activa `tests/core/test_audit_hook_encrypted.py`.
  - Gate: `slice-gate.sh crypto && slice-gate.sh core/audit`.
- **Slice S1-B8 · Contraseñas y JWT.** Historias: US-032 y US-033.
  - argon2id con los parámetros en `Settings`.
  - JWT Ed25519 de 15 minutos con tolerancia de 30 s (N-14).
  - `new_opaque_token()` y `hash_opaque_token()`.
  - `TokenExpired` y `TokenInvalid`.
  - Gate: `slice-gate.sh core/security`.
- **Slice S1-B9 · `current_user`, `require_role` y prueba de rutas.** Historias: US-034 y US-035.
  - `Principal`, `PrincipalLoader` y `register_principal_loader()` (G-02).
  - El arranque falla si no hay cargador.
  - El rol se lee de la base y `SYSTEM_USER_ID` se rechaza.
  - 401 `token_expired` y 401 `unauthorized`.
  - Marca `__apex_roles__`, y lista blanca con `/health`, `/auth/login`, `/auth/forgot`, `/auth/reset` y `/auth/refresh`.
  - Gate: `slice-gate.sh core/security`.
- **Slice S1-B10 · Rate limit, CORS y secretos.** Historias: US-036, US-037 y US-039.
  - `core/ratelimit.py`, con 5 por minuto por IP y `TRUSTED_PROXIES`.
  - CORS cerrado a `CORS_ORIGINS`.
  - Validación de los archivos de llave al arrancar.
  - gitleaks en CI.
  - Inspección de la imagen: llaves privadas por contenido y ningún `.pem` ni `.key` bajo `/app`.
  - Gate: `slice-gate.sh core/ratelimit && slice-gate.sh core/config`.
- **Slice S1-B11 · Cuentas de usuario y admin inicial.** Historia: US-041.
  - **Migración `0004_auth`:**
    - `users`, con índice único parcial sobre `email WHERE deleted_at IS NULL`, `last_login_at` y `display_name`;
    - `refresh_tokens`, con `replaced_by_id`;
    - `one_time_tokens`;
    - `INSERT` de `SYSTEM_USER_ID`.
  - `auth.service`: `get_principal`, registrado como cargador real; `names_for`, `ids_by_email` y `active_admin_id_by_email`.
  - `__audit_redact__ = ("password_hash",)` en `users`.
  - `cli seed` con `--as`.
  - Gate: `slice-gate.sh auth`, más el ciclo de Alembic.

### Wave 5a · Tests de front en rojo (`frontend-qa-automation`)

- **S1-F1:** `src/core/api`, `src/core/i18n` y `tests/lint`.
- **S1-F2:**
  - `src/core/auth`;
  - `tests/unit/no-role-literals.test.ts`;
  - `src/shared/ui/PageHeader`, `Tabs` y `KpiCard`;
  - `src/shared/ui/SidePanel` y `ConfirmModal`;
  - `src/shared/hooks/useFocusTrap`.
- **S1-F3:**
  - `src/shared/ui/DataTable`, `Pagination`, `FilterBar` y `Chips`;
  - `src/shared/hooks` y `src/shared/lib`;
  - `src/shared/ui/MaskedValue` y `HistoryAside`;
  - `src/shared/lib/audit-labels`.

### Wave 5b · Implementación de front (`frontend-ux-engineer`)

- **Slice S1-F1 · Cliente API y formato.** Historias: US-059 y US-060.
  - `client.ts` con `credentials: "include"`, `ApiError` y `Page<T>`.
  - Tipos generados desde `docs/openapi.json`.
  - `formatCop`, `formatDate`, `formatDateTime` y `formatMonth` con la hora de Bogotá.
  - Gate: `slice-gate.sh web/core`.
- **Slice S1-F2 · Permisos, encabezados y paneles.** Historias: US-040, US-064 y US-065.
  - Matriz única de permisos (`can`, `useCan`, `Action`) con nombres `members.*`.
  - `PageHeader`, `Tabs` y `KpiCard`.
  - `SidePanel` y `ConfirmModal` con trampa de foco.
  - Gate: `slice-gate.sh web/shared && slice-gate.sh web/core`.
- **Slice S1-F3 · Tabla y valor enmascarado.** Historias: US-063 y US-066.
  - `DataTable`, `Pagination`, `FilterBar` y `Chips` sobre `{ items, total, limit, offset }`.
  - `MaskedValue` y `HistoryAside`, todavía sin conectar.
  - Gate: `slice-gate.sh web/shared`.
  - Criterio diferido: `onReveal` y el historial se conectan con US-074 (Sprint 3) y US-106 (Sprint 4). Así lo prevé el desglose ("no bloquean el componente").

### Validación del sprint

- `run-gates.sh` en verde y la suite de arquitectura completa.
- Smoke del stack:
  - `init-keys` y `seed` dentro de Compose;
  - el api arranca con las DEK abiertas;
  - arrancar con una KEK equivocada falla al iniciar (US-025 y US-116 lo vuelven a probar en el Sprint 4).
- `npx playwright test tests/e2e/csp.spec.ts` contra Nginx.

## Migraciones que aplica

- `0002_audit_log` (US-015, con `subject_member_id` de G-05).
- `0003_crypto` (US-024).
- `0004_auth` (US-041, con `display_name`, `last_login_at`, `replaced_by_id` y la fila de `SYSTEM_USER_ID`).

## Endpoints que expone

Ninguno nuevo de negocio. Este sprint entrega las dependencias que todos los endpoints usan: `require_role`, `rate_limit`, paginación y envelope de errores. Siguen expuestos `GET /health` y `GET /api/v1/health`.

## Tests de arquitectura que deben pasar

- Los del Sprint 0.
- `tests/architecture/test_core_import_direction.py`, consolidada (US-015). Absorbe `test_core_does_not_import_modules.py` (US-034) y `test_core_import_graph.py` (US-029), y comprueba tres cosas:
  - `core` no importa `app.modules`;
  - `core/crypto` no importa `core/audit`;
  - `core/audit` solo toma `core/crypto/digest`.
- `tests/architecture/test_list_routes_use_page_params.py` (US-019).
- `tests/architecture/test_no_cross_models.py` y `tests/architecture/test_find_forbidden_imports.py` (US-022).
- `tests/architecture/test_banned_imports.py`, ampliada (US-023, US-032 y US-033).
- `tests/architecture/test_audited_tables.py` (US-024).
- `tests/architecture/test_every_route_has_role.py` y `tests/architecture/test_route_guard_unit.py` (US-035).
- `tests/architecture/test_no_physical_delete_users.py` (US-041).

## Riesgos y mitigación

1. [HIGH] Tres formatos son irreversibles desde el primer dato: la serialización canónica de la cadena (US-015), el blob `apx1.` (US-025) y la normalización N-02 (US-026).
   - Mitigación:
     - vectores de prueba fijos (`test_chain_hash_vector.py` en US-119);
     - la revisión de seguridad revisa los tres explícitamente;
     - no entran datos reales hasta el release v0.1.
2. [HIGH] Ciclo de imports `core/crypto` → `core/db` → `core/audit` → `core/crypto`.
   - Mitigación: G-01 (`core/context.py`, solo biblioteca estándar) y `test_core_import_direction.py` desde S1-B1.
3. [MEDIUM] Concurrencia del `seq` y del `prev_hash`.
   - Mitigación: `tests/core/test_audit_concurrency.py` con dos sesiones.
4. [MEDIUM] US-016 llega antes que US-041.
   - Mitigación: la constante `SYSTEM_USER_ID` se usa sin llave foránea hasta S1-B11, como prevé el desglose de US-025. La suite completa se vuelve a correr después de `0004`.
5. [MEDIUM] Sprint largo: 28 historias, 11 slices de backend y 3 de front.
   - Mitigación:
     - notas de estado en `docs/scratch/sprint-01.md`;
     - un checkpoint por slice;
     - releer `CLAUDE.md` y este archivo después de cada compactación.

## Definición de hecho del sprint

- Los 14 slices confirmados con `checkpoint-commit.sh`: 11 de backend y 3 de front.
- `scripts/workflow/run-gates.sh` en verde: api con cobertura del 80 % en `src/app/core` y `src/app/modules/auth`, y front con lint, tsc, test y build.
- `cd api && uv run pytest tests/architecture -q` en verde.
- `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` sobre `0004`.
- `docs/openapi.json` al día, por el paso de CI de US-021.
- Smoke en Compose, con evidencia SQL de la demo: blob `apx1.`, fila de `crypto_ops`, cadena de auditoría y `UPDATE` rechazado.
- E2E: `npx playwright test tests/e2e/csp.spec.ts`.
- Seguridad, revisada por `security-reviewer`:
  - primitivas solo en `core/crypto` y `core/security`;
  - KEK con permisos 600 y fuera de la imagen;
  - ningún material de llave en `audit_log` ni en los logs;
  - argon2id con parámetros por `Settings`;
  - JWT sin `alg` configurable;
  - rate limit detrás de `TRUSTED_PROXIES`;
  - gitleaks en verde.
- `verify-delivery` completo, que lista el criterio diferido de US-066.
