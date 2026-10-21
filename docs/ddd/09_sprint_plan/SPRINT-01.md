# Sprint 1 · Núcleo de auditoría, bus de criptografía y seguridad de plataforma

- Versión: v0.1.
- Épicas:
  - EP-01: el resto;
  - EP-02: todo salvo US-030 y US-031;
  - EP-03: completa;
  - EP-04: solo US-041;
  - EP-06: el kit, sin pantallas.
- Tamaño: 28 historias, 83 puntos y 365 h relativas.
- Rama: `feat/sprint-01-nucleo-cripto-seguridad`, creada desde `main` cuando se fusiona el PR del Sprint 0.
- Historias del sprint: US-015, US-016, US-019, US-021, US-022, US-023, US-024, US-025, US-026, US-027, US-028, US-029, US-032, US-033, US-034, US-035, US-036, US-037, US-038, US-039, US-040, US-041, US-059, US-060, US-063, US-064, US-065, US-066.

## Objetivo

Dejar listas las tres piezas transversales que cualquier módulo de negocio usa sin pensar en ellas:
- **Auditoría:** la cadena es append-only y se escribe sola en `after_flush`.
- **Bus de criptografía:** cifra, indexa y firma sin que quien lo llama elija la llave ni el algoritmo.
- **Seguridad de plataforma:** argon2id, JWT Ed25519, `require_role` con `PrincipalLoader`, límite de intentos, CORS, CSP y manejo de secretos.

Al cerrar el sprint existen el usuario técnico y el admin inicial, y el front tiene su cliente tipado y el kit de componentes.

## Demo al final del sprint

`docker compose` abrevia `docker compose -f infra/compose.yml -f infra/compose.dev.yml`. Dentro de los contenedores los comandos van sin `uv run` (B-3).

1. **Llaves.** `docker compose run --rm tools init-keys` crea, en el volumen `keys` y con modo 600:
   - la KEK local;
   - la llave de firma del bus;
   - `jwt_ed25519.pem` y `jwt_ed25519.pub` (A-1).

   `init-keys` **no** crea las DEK.
2. **DEK al arrancar.** `docker compose up -d --build` arranca el api. En el `lifespan`, `ensure_keys` (US-025) crea las DEK por `data_class` que faltan, con `created_by = SYSTEM_USER_ID`. En `crypto.crypto_keys` quedan filas `active` con `wrapped_material` y sin material en claro. Con una KEK equivocada, el api no arranca.
3. **Cifrado.** Una prueba de service guarda un modelo de prueba con una columna `Encrypted`.
   - `SELECT` muestra `apx1.<key_id>.A256GCM.<nonce>.<ct>`.
   - `crypto.crypto_ops` tiene una fila `encrypt` por lote, con `count` y `user_id = SYSTEM_USER_ID`.
4. **Auditoría.**
   - `audit.audit_log` tiene `seq` consecutivo y `prev_hash` encadenado.
   - `UPDATE audit.audit_log SET action='x'` falla por el trigger.
   - El blob cifrado aparece en `after`, nunca el valor en claro.
5. **Usuarios.** `docker compose run --rm tools seed` crea el admin inicial con `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD`. Existe `system@apex.local`, con `is_active = false` y UUID `00000000-0000-0000-0000-000000000001`.
6. **Arquitectura.** `uv run pytest tests/architecture -q` pasa en el host. Una ruta de prueba sin `require_role` hace fallar `test_every_route_has_role.py`.
7. **Cabeceras.** `curl -I http://localhost:${WEB_PORT:-80}/` muestra:
   - CSP con nonce;
   - `X-Frame-Options: DENY`;
   - `nosniff`;
   - `Referrer-Policy`;
   - `Permissions-Policy`;
   - `index.html` con `no-store`.
8. **Front.** `cd web && npm test -- --run` pasa con el kit completo y los tipos generados desde `docs/openapi.json`.

## Dependencias de sprints anteriores

Del Sprint 0:
- US-002: `banned-api` y `test_banned_imports.py`.
- US-003: CI con PostgreSQL.
- US-005: volumen `keys`, servicio `tools` con `entrypoint` `app.cli`, y `migrations/` en la imagen.
- US-006: `default.conf`.
- US-008: gates con el ajuste A-01.
- US-009 y US-010: base del front.
- US-011, US-012, US-013, US-014, US-017, US-018 y US-020: núcleo mínimo del backend.

Decisiones que aplica:
- G-01, G-02 y G-05.
- N-01, N-02, N-04, N-05, N-06, N-08, N-10, N-13, N-15 y N-30.
- Refinamientos de US-024 (`rotated_by`) y de US-110 (`display_name` en `0004`).
- Códigos 401: `token_expired` y `unauthorized`.

Excepción documentada: `0004_auth` inserta la fila de `SYSTEM_USER_ID` en Alembic, aunque la regla de datos 8 de `CLAUDE.md` manda que los datos vayan por CLI. Se justifica porque es dato de referencia que necesitan las llaves foráneas, y está aprobado en N-15. T-DOC lo deja escrito en `CLAUDE.md`.

## Historias en orden de ejecución

El patrón de v0.1 es el del README: en cada slice, primero el **Rojo** (stubs vacíos y pruebas), después el **Verde** (implementación) y al final el **Gate**, que corre `slice-gate.sh <modulo> <archivos del Rojo>` y siempre agrega `tests/architecture`. Después del gate va el checkpoint.

### Wave 0 · Infraestructura (`devops-wsl2-docker`)

- **Slice S1-W0-1 · Cabeceras de seguridad y CSP.** Historia: US-038.
  - Rojo: `tests/unit/index-html.test.ts` y `tests/e2e/csp.spec.ts`.
  - Verde: Nginx con:
    - CSP con nonce `$request_id` (N-14);
    - `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` y `Permissions-Policy`;
    - `index.html` con `no-store`;
    - sin fuentes remotas.
  - Gate: `slice-gate.sh web/app tests/unit/index-html.test.ts` y el smoke de Nginx.
- **Preparación de S1-B4:** el volumen `keys` montado en `tools` con el usuario no root como dueño. Cierra la parte de infraestructura del criterio diferido de US-005.

### Waves 3a/3b · Backend, alternadas por slice

- **Slice S1-B1 · Tabla de auditoría y cadena de hashes.** Historia: US-015, con la tarea T1 de US-027 adelantada (`core/crypto/digest.py`, N-06).
  - Paso previo (bajas): `docker compose exec db pg_dump -U <usuario> -Fc apex > docs/scratch/sprint-01-antes-0002.dump`, antes de aplicar `0002`. Es la primera migración con trigger.
  - Rojo:
    - `tests/crypto/test_digest.py`;
    - `tests/core/test_audit_chain.py`;
    - `tests/core/test_audit_log_db.py`;
    - `tests/core/test_audit_concurrency.py`.
  - Verde:
    - en `core/audit.py`: `canonical`, `chain_hash`, `append_entry`, `record()` y `verify_chain`. `record()` asigna `seq` como el último más 1 bajo `pg_advisory_xact_lock`;
    - **migración `0002_audit_log`:**
      - `audit.audit_log`;
      - CHECK de `action`, que incluye `download`;
      - columna `subject_member_id` (G-05) dentro de la serialización canónica;
      - `audit.forbid_mutation()`;
      - índices `at`, `(table_name, record_id)`, `user_id`, `(table_name, seq DESC)` y `(subject_member_id, seq DESC)`.
  - Gate:
    - `slice-gate.sh core/audit` con sus tres archivos;
    - `slice-gate.sh crypto tests/crypto/test_digest.py`;
    - ciclo de Alembic.
- **Slice S1-B2 · Hook de auditoría.** Historia: US-016.
  - Rojo:
    - `tests/core/test_audit_serialize.py`;
    - `tests/core/test_audit_hook_db.py`;
    - `tests/core/test_audit_hook_perf.py`;
    - `tests/core/test_audit_actor_http.py`.
  - Verde:
    - `core/context.py` completo;
    - `install_audit_listeners()` conectado en `create_app`, lo que cierra el criterio diferido de US-020;
    - `created_by` en `before_flush`, lo que cierra el diferido de US-012;
    - `__audit_redact__`, `__audit_exclude__` y `__audit_subject__`;
    - en `update`, solo las columnas que cambian;
    - `PlaintextInAuditError`.
    - `SYSTEM_USER_ID` se usa sin FK hasta S1-B11.
  - Gate: `slice-gate.sh core/audit` con sus cuatro archivos.
- **Slice S1-B3 · Paginación, OpenAPI y fronteras.** Historias: US-019, US-021 y US-022.
  - Rojo:
    - `tests/core/test_pagination_db.py`;
    - `tests/core/test_pagination_router.py`;
    - `tests/core/test_openapi_export.py`;
    - `tests/architecture/test_list_routes_use_page_params.py`;
    - `tests/architecture/test_no_cross_models.py`;
    - `tests/architecture/test_find_forbidden_imports.py`.
  - Verde:
    - `PageParams`, `Page[T]` y `paginate`;
    - `docs/openapi.json` verificado en CI;
    - prueba de modelos cruzados (`schemas` y `exceptions` ajenos permitidos).
  - Gate:
    - `slice-gate.sh core/pagination` con sus archivos;
    - `slice-gate.sh main tests/core/test_openapi_export.py`.
- **Slice S1-B4 · KeyProvider, tablas crypto y llaves en el volumen.** Historias: US-023 y US-024.
  - Rojo:
    - `tests/crypto/test_local_provider.py`;
    - `tests/crypto/test_init_keys.py`. Cubre la KEK, la llave del bus y `jwt_ed25519.pem` y `jwt_ed25519.pub` con modo 600, y que la ejecución sea idempotente (A-1);
    - `tests/crypto/test_provider_startup.py`;
    - `tests/crypto/test_crypto_tables.py`;
    - `tests/migrations/test_0003_crypto.py`;
    - `tests/architecture/test_audited_tables.py`.
  - Verde:
    - `KeyProvider`, con `wrap`, `unwrap`, `sign`, `verify` y `rotate`;
    - `LocalFileProvider`;
    - `cli init-keys --data-class`, que además genera el par JWT Ed25519 si falta. Deja de valer la nota de "nadie genera la llave JWT" del README del desglose;
    - **migración `0003_crypto`**, con tres tablas:
      - `crypto_keys`: índice único parcial, CHECK propósito-algoritmo, trigger de transiciones de estado y columna `rotated_by`;
      - `crypto_ops`: columnas `count`, `purpose`, `user_id NOT NULL` y verbo `export`, en modo append-only;
      - `crypto_jobs`: tipo `rewrap` y un solo job en curso por `data_class`.
    - Cierra el criterio diferido de US-005 (`tools`).
  - Gate:
    - `slice-gate.sh crypto` con sus archivos;
    - `slice-gate.sh cli tests/crypto/test_init_keys.py`;
    - ciclo de Alembic.
- **Slice S1-B5 · Cifrado AES-256-GCM e índice ciego.** Historias: US-025 y US-026.
  - Rojo:
    - `tests/crypto/test_blob.py`;
    - `tests/crypto/test_registry.py`;
    - `tests/crypto/test_bus_encrypt.py`;
    - `tests/crypto/test_bootstrap.py`;
    - `tests/crypto/test_bus_no_leak.py`;
    - `tests/crypto/test_normalize.py`;
    - `tests/crypto/test_blind_index.py`.
  - Verde:
    - blob `apx1.` con `aad` igual al id;
    - `registry.py`;
    - keyring y `ensure_keys` en el `lifespan`: crea las DEK que faltan;
    - HMAC con la normalización N-02.
  - Gate: `slice-gate.sh crypto` con sus archivos.
- **Slice S1-B6 · Firma y bitácora por lote.** Historias: US-027 (el resto) y US-029.
  - Rojo:
    - `tests/crypto/test_signature_format.py`;
    - `tests/crypto/test_sign.py`;
    - `tests/crypto/test_oplog_aggregate.py`;
    - `tests/crypto/test_oplog.py`.
  - Verde:
    - `sign` y `verify` con el formato `apx1.<key_id>.<alg>.<sig_b64url>`;
    - `bus.batch()` y `oplog.record`, con el actor tomado de `core/context.py`.
  - Gate: `slice-gate.sh crypto` con sus archivos.
- **Slice S1-B7 · Tipos de columna.** Historia: US-028.
  - Rojo:
    - `tests/crypto/test_secret.py`;
    - `tests/crypto/test_types.py`;
    - `tests/crypto/test_types_key_check.py`;
    - `tests/core/test_audit_encrypted.py`;
    - `tests/core/test_audit_hook_encrypted.py`.
  - Verde:
    - `Encrypted(data_class)`, `BlindIndexed(data_class)` y `Secret`;
    - recifrado y reindexado en el mismo flush;
    - el hook guarda el blob.
  - Gate:
    - `slice-gate.sh crypto` con sus archivos;
    - `slice-gate.sh core/audit` con los dos archivos de `tests/core`.
- **Slice S1-B8 · Contraseñas y JWT.** Historias: US-032 y US-033.
  - Rojo: `tests/core/test_passwords.py` y `tests/core/test_jwt.py`.
  - Verde:
    - argon2id con parámetros en `Settings`;
    - JWT Ed25519 de 15 minutos con tolerancia de 30 s;
    - lectura de `jwt_ed25519.pem` desde `JWT_PRIVATE_KEY_PATH` en el volumen `keys`;
    - `new_opaque_token()` y `hash_opaque_token()`;
    - `TokenExpired` y `TokenInvalid`.
  - Gate: `slice-gate.sh core/security` con sus archivos.
- **Slice S1-B9 · `current_user`, `require_role` y prueba de rutas.** Historias: US-034 y US-035.
  - Rojo:
    - `tests/auth/test_principal_loader.py`;
    - `tests/core/test_require_role.py`;
    - `tests/core/test_docs_disabled.py`;
    - `tests/architecture/test_every_route_has_role.py`;
    - `tests/architecture/test_route_guard_unit.py`.
    - `tests/conftest.py` registra un `PrincipalLoader` **doble** desde este slice (M-2), porque el arranque falla si no hay cargador.
  - Verde:
    - `Principal`, `PrincipalLoader` y `register_principal_loader()` (G-02);
    - el rol se lee de la base;
    - `SYSTEM_USER_ID` se rechaza;
    - errores 401 `token_expired` y `unauthorized`;
    - `__apex_roles__`;
    - lista blanca: `/health`, `/auth/login`, `/auth/forgot`, `/auth/reset` y `/auth/refresh`.
  - Gate:
    - `slice-gate.sh core/security` con `tests/core/test_require_role.py` y `tests/core/test_docs_disabled.py`;
    - `slice-gate.sh auth tests/auth/test_principal_loader.py`. Queda incluido por lista de archivos (M-2).
- **Slice S1-B10 · Límite de intentos, CORS y secretos.** Historias: US-036, US-037 y US-039.
  - Rojo:
    - `tests/core/test_ratelimit.py`;
    - `tests/core/test_cors.py`;
    - `tests/core/test_config_secrets.py`.
  - Verde:
    - `core/ratelimit.py`, con 5 por minuto por IP y `TRUSTED_PROXIES`;
    - CORS cerrado;
    - validación al arrancar de los archivos de llave, incluido el par JWT;
    - gitleaks en CI;
    - inspección de la imagen.
  - Gate:
    - `slice-gate.sh core/ratelimit` con sus archivos;
    - `slice-gate.sh core/config` con sus archivos.
- **Slice S1-B11 · Cuentas de usuario y admin inicial.** Historia: US-041.
  - Rojo:
    - `tests/auth/test_pure_users.py`;
    - `tests/auth/test_seed.py`;
    - `tests/auth/test_auth_schema.py`;
    - `tests/cli/test_seed_cli.py`;
    - `tests/architecture/test_no_physical_delete_users.py`.
  - Verde:
    - **migración `0004_auth`:**
      - `users`, con índice único parcial sobre `email`, más `last_login_at` y `display_name`;
      - `refresh_tokens`, con `replaced_by_id`;
      - `one_time_tokens`;
      - `INSERT` de `SYSTEM_USER_ID`, que es la excepción documentada.
    - `auth.service.get_principal`, registrado como el cargador real. El doble de `conftest` queda solo para las pruebas que no tocan `auth`.
    - `names_for`, `ids_by_email` y `active_admin_id_by_email`.
    - `__audit_redact__`.
    - `cli seed --as`.
  - Gate:
    - `slice-gate.sh auth` con sus archivos;
    - `slice-gate.sh cli tests/cli/test_seed_cli.py`;
    - ciclo de Alembic.

### Waves 5a/5b · Front, alternadas por slice

- **Slice S1-F1 · Cliente API y formato.** Historias: US-059 y US-060.
  - Rojo:
    - stubs de `src/core/api/client.ts` y `src/core/i18n/format.ts`;
    - pruebas en `src/core/api`, `src/core/i18n` y `tests/lint`.
  - Verde:
    - `client.ts` con `credentials: "include"`, `ApiError` y `Page<T>`;
    - tipos generados desde `docs/openapi.json`;
    - `formatCop`, `formatDate`, `formatDateTime` y `formatMonth`.
  - Gate: `slice-gate.sh web/core <archivos de Rojo>`.
- **Slice S1-F2 · Permisos, encabezados y paneles.** Historias: US-040, US-064 y US-065.
  - Rojo:
    - pruebas en `src/core/auth`;
    - `tests/unit/no-role-literals.test.ts`;
    - `src/shared/ui/PageHeader`, `Tabs`, `KpiCard`, `SidePanel` y `ConfirmModal`;
    - `src/shared/hooks/useFocusTrap`.
  - Verde:
    - matriz única de permisos `members.*`;
    - `PageHeader`, `Tabs`, `KpiCard`, `SidePanel` y `ConfirmModal`, con trampa de foco.
  - Gate:
    - `slice-gate.sh web/core` con los archivos de `src/core/auth`;
    - `slice-gate.sh web/shared` con los demás.
- **Slice S1-F3 · Tabla y valor enmascarado.** Historias: US-063 y US-066.
  - Rojo:
    - `src/shared/ui/DataTable`, `Pagination`, `FilterBar` y `Chips`;
    - `src/shared/hooks` y `src/shared/lib`;
    - `src/shared/ui/MaskedValue` y `HistoryAside`;
    - `src/shared/lib/audit-labels`.
  - Verde:
    - el kit de listas sobre `{ items, total, limit, offset }`;
    - `MaskedValue` y `HistoryAside`, sin conectar todavía.
  - Gate: `slice-gate.sh web/shared <archivos de Rojo>`.
  - **Criterio diferido:** `onReveal` se conecta en el Sprint 3 (US-074) y el historial en el Sprint 4A (US-106).

### Validación del sprint

- `run-gates.sh` en verde y la suite de arquitectura completa.
- **Medición T6 de US-007**, que cierra su criterio diferido del Sprint 0 (A-6): medir el tiempo de arranque completo desde un clon limpio, sin `.env` previo ni volumen `keys`:
  1. `cp .env.example .env`;
  2. `docker compose run --rm tools init-keys`;
  3. `docker compose up -d --build`;
  4. `/health` en 200.

  El README de US-007 promete 5 minutos. El resultado queda en `docs/scratch/sprint-01.md`.
- Smoke:
  - el api arranca con las DEK que creó `ensure_keys` y lee la llave JWT;
  - con una KEK equivocada, el arranque falla.
- `npx playwright test tests/e2e/csp.spec.ts`.
- **Paso humano:** push de la rama y PR (A-02).

## Migraciones que aplica

- `0002_audit_log` (US-015). Lleva antes el volcado `pg_dump` de la base de desarrollo.
- `0003_crypto` (US-024).
- `0004_auth` (US-041), con la fila de `SYSTEM_USER_ID` como excepción documentada.

## Endpoints que expone

Ninguno de negocio. El sprint entrega lo que todos los endpoints van a usar: `require_role`, `rate_limit`, la paginación y el envelope de errores. Siguen `GET /health` y `GET /api/v1/health`.

## Tests de arquitectura que deben pasar

Todos corren en cada gate de slice (A-5).
- Los del Sprint 0.
- `test_core_import_direction.py`, consolidada en US-015. Absorbe `test_core_does_not_import_modules.py` (US-034) y `test_core_import_graph.py` (US-029).
- `test_list_routes_use_page_params.py` (US-019).
- `test_no_cross_models.py` y `test_find_forbidden_imports.py` (US-022).
- `test_banned_imports.py`, ampliada en US-023, US-032 y US-033.
- `test_audited_tables.py` (US-024).
- `test_every_route_has_role.py` y `test_route_guard_unit.py` (US-035).
- `test_no_physical_delete_users.py` (US-041).

## Riesgos y mitigación

1. [HIGH] Hay formatos que no se pueden cambiar después: la serialización canónica (US-015), el blob `apx1.` (US-025) y la normalización N-02 (US-026).
   - Mitigación:
     - vectores de prueba fijos;
     - ADR en el Sprint 4B;
     - ningún dato real antes del release.
2. [HIGH] Puede aparecer el ciclo de imports `core/crypto` → `core/db` → `core/audit` → `core/crypto`.
   - Mitigación: G-01, más `test_core_import_direction.py` corriendo en cada gate.
3. [MEDIUM] Sin llave JWT, el api no arranca.
   - Mitigación: `init-keys` la crea en S1-B4, y `test_init_keys.py` y US-039 lo verifican.
4. [MEDIUM] US-016 llega antes que US-041, y el arranque necesita un cargador de principal.
   - Mitigación: la constante `SYSTEM_USER_ID` funciona sin FK hasta B11, y el `PrincipalLoader` doble vive en `conftest` desde B9.
5. [MEDIUM] Es un sprint largo: 28 historias y 15 slices.
   - Mitigación:
     - `docs/scratch/sprint-01.md`;
     - un checkpoint por slice;
     - releer `CLAUDE.md` y este archivo después de cada compactación;
     - `git status` limpio antes de cada checkpoint, porque `checkpoint-commit.sh` hace `git add -A`.

## Definición de hecho del sprint

- Los 15 slices (W0, 11 de backend y 3 de front) quedan confirmados con `checkpoint-commit.sh`.
- `run-gates.sh` en verde, con:
  - cobertura global de `app` de al menos 80 %, con `--cov-omit` de `cli.py` y `worker/`;
  - front: lint, tsc, test y build.
- `cd api && uv run pytest tests/architecture -q` en verde.
- Ciclo de Alembic sobre `0004`.
- Volcado previo a `0002` guardado.
- `docs/openapi.json` al día.
- Smoke con evidencia SQL de la demo, y medición T6 de US-007 registrada.
- E2E: `tests/e2e/csp.spec.ts`.
- Seguridad (`security-reviewer`):
  - primitivas solo en `core/crypto` y `core/security`;
  - KEK y llave JWT con modo 600, fuera de la imagen;
  - sin material de llave en la auditoría ni en los logs;
  - JWT sin `alg` configurable;
  - límite de intentos detrás de `TRUSTED_PROXIES`;
  - gitleaks en verde.
- **Paso humano:** push, PR con CI en verde y merge.
- `verify-delivery`, que lista el criterio diferido de US-066.
