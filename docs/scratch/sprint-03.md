# Cuaderno · Sprint 3

Rama `feat/sprint-03-membresias-pagos`. Plan: `docs/ddd/blueprints/sprint-03-plan.md` (20 slices,
enmiendas E1 a E16). Alias: `DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"`.
Las pruebas del api necesitan `TEST_DATABASE_URL` exportada desde `.env` (sin ella `run-gates.sh`
falla a propósito: 1.026 errores de "TEST_DATABASE_URL no está definida", no se saltan).

## Línea base (W0-1.1)

- HEAD `86d948e` (los documentos del plan sobre `eebfb0f` y `7b51d3c`), árbol limpio, `git worktree list`
  solo con el principal.
- Stack `apex` arriba y los cuatro servicios `healthy` (api, web, db, db_test); `alembic current` =
  `0007_plans (head)`. Puertos del host por nombre en `.env`: `WEB_PORT`, `API_PORT`, `DB_PORT`, `DB_TEST_PORT`.
- `$DC up -d --build` falla en este equipo desde Compose 5.6.1 y buildx 0.38.1: `bake` pide
  `--allow=network.host` por el `build.network: host` de `compose.dev.yml` y Compose no lo pasa. Las
  imágenes se construyeron con `docker buildx build --load --network host --allow network.host` y el
  stack se levantó con `$DC up -d --no-build` (RUNBOOK §7; DECISIONES, "S3-W0-1 · Infraestructura y
  dependencias").
- Imágenes de la línea base: `apex-api:local` `sha256:634ab1f05e355b5b4598e3e643578c858b3d6c3b51e0f6d5660a1e8dba8ae537`,
  `apex-web:local` `sha256:97a03e837d6239ab29f22eff07693e85882b4fe8ee1b46398c22e99af5210714`.
- `bash scripts/workflow/run-gates.sh` (con `TEST_DATABASE_URL`), todo en verde:
  - api: ruff, formato y mypy limpios; `pytest -m "not perf"` 1.987 ok, 4 saltadas (3 de NTFS y el
    caso `reveal` de US-074 para S3-B10), 3 deseleccionadas (`perf`); cobertura 95,71 % (umbral 80).
  - scripts: `test_check_key_files` 9 ok, `test_nginx_conf` 62 ok, `test_compose_config` 35 ok; 0 fallas.
  - web: lint y tsc limpios; 110 archivos, 1.763 pruebas; cobertura 99,68 % de líneas (vitest 3.2.7);
    build en verde (`main` 463,25 kB, 142,49 kB gzip).

### S3-W0-1 · Línea base, imágenes por digest, dependencias de desarrollo, `.env.seed` y documentación

- Documentación (W0-1.2, T-DOC):
  - `docs/ddd/DECISIONES.md`: sección "Sprint 3 · decisiones de implementación" con la sección 1 del
    plan copiada íntegra (D1 a D40, S3-D41 a S3-D78, S3-C1 a S3-C22); S3-D67 lleva la marca de E16;
    subsección con las enmiendas de la crítica 2 que fijan decisión (E16 el 503 solo con seguridad
    declarada, E13, E14, E15, E12) y subsección "S3-W0-1 · Infraestructura y dependencias".
  - `docs/ddd/09_sprint_plan/SPRINT-03.md`: nota del plan; Wave 0 con S3-W0-1 y S3-W0-2 (S3-C20);
    `compute_status` de cuatro argumentos y `sell(..., enforce_retroactive_limit=True)` en S3-B1;
    `test_service_import_graph.py` desde S3-B1 (S3-C19); `GET /payments/methods` como `{ items }`;
    `POST /memberships/{id}/payments` publicada en S3-B4 (E9); `-m perf` en S3-B7 y en la validación;
    `test_list_performance.py` → `tests/payments/test_list_perf.py` y `tests/memberships/test_list_perf.py`;
    E2E en `tests/e2e/stack/` y `tests/e2e/` (S3-D72); demo con el 409 `payment_exceeds_balance` y
    `payment_possible_duplicate` (S3-C22), `freeze_limit_reached`, `payments_immutable` y
    `payment_already_voided`; 503 `busy` en la definición de hecho; "Socios con él" fuera (US-082);
    `useMembershipSummary` en F4 (E10).
  - `docs/ddd/05_service_design.md`: `payment_methods` con `{ items }`; `reveal` con `types.reveal` y
    `audit.record` sin `commit()`; `sell` con la firma real (`enforce_retroactive_limit`, sin `by` ni
    `max_retroactive_days`, candados y `prefix_field`); `payability` con `agreed_price_cop`;
    `compute_status` de cuatro argumentos; `register(session, membership_id, data, role)` con `confirm_*`.
  - `docs/ddd/03_context_map.md`: aristas `memberships -> members/plans/settings`, `payments ->
    members/auth/settings`, `memberships -> payments` y la lista blanca `LAZY_IMPORT_WHITELIST`.
  - 15 desgloses de `docs/ddd/08_implementation_breakdown/` (US-056, US-071, US-073, US-074, US-075,
    US-076, US-083, US-084, US-085, US-091, US-092, US-093, US-095, US-096, US-098): un bloque
    "Corregido en S3-W0-1" bajo el título con las S3-C y decisiones que aplican, y 30 reemplazos en
    línea (`get_ref`, `test_service_import_graph.py`, `members.document.update`, `members.members`,
    `SessionDep`, `PageParams`, `set[UUID]`, `active_ids(session) -> frozenset[UUID]`,
    `now_utc`, `agreed_price_cop`, `perf`, `test_list_perf.py`, `{"items": [...]}`).
    `verificar.mjs` da el mismo resultado que antes (un único error previo: "SIN Total" de US-008).
  - `docs/BRECHAS.md`: sección 10 "Sprint 3" (diferencias de D37, "Socios con él" a US-082,
    confirmación de sobrepago y duplicado en el servidor, avisos de datos personales, rutas y
    contratos); la fila de `PlansPage.tsx` de la sección 9 pasa "Socios con él" al Sprint 4A.
  - `docs/RUNBOOK.md`: índice; sección 7 (imágenes por digest, renovación y la nota del build con
    `network: host`), sección 8 (primer admin sin `.env.seed`), esqueletos de las secciones 9 y 10;
    la sección 2 remite a la 8.
  - `scripts/workflow/README.md`: ejemplos `memberships`, `payments`, `web/memberships`,
    `web/payments` y la nota de "módulo inexistente" (S3-D61); `test_images_pinned.sh` en
    `run-gates.sh`; el paso informativo de `npm audit` (S3-D63). `scripts/ci/README.md`: entrada de
    `test_images_pinned.sh`.
  - `docs/ddd/blueprints/sprint-03-blueprint.md`: nota de "corregido por" al inicio.
  - `CLAUDE.md`: `core/locks.py` en la estructura, la línea del 503 `busy` en Seguridad y
    `web/src/shared/data/` en la regla 5 del front.
- Rojo (W0-1.3):
  - `scripts/ci/test_images_pinned.sh` (nuevo, grep puro, modo 100755): 10 fallas en los cinco
    archivos (`api/Dockerfile` 2 `FROM`, `web/Dockerfile` 2 `FROM`, `infra/compose.yml`,
    `infra/compose.dev.yml` y las 4 menciones de `nginx:stable-alpine` de `test_nginx_conf.sh`).
    Control negativo sobre una copia (comentario sin fecha y digest corto): 2 fallas, las esperadas.
  - `scripts/ci/test_compose_config.sh`: caso nuevo "postgres fijado por digest en los dos compose"
    en rojo (1 falla, `postgres:16 / postgres:16`).
  - `bash -n` de los dos scripts sin errores.
- Verde (W0-1.4, S3-D62):
  - Digests consultados el 22 de octubre con `docker buildx imagetools inspect <imagen:tag> --format '{{json .Manifest.Digest}}'`:
    `python:3.12-slim` `sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2`;
    `node:22-alpine` `sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914` (igual a L3);
    `postgres:16` `sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97` (igual a L3 y a `ci.yml`);
    `nginx:stable-alpine` `sha256:47928bf67eb62a1863cb08d9ecb52d3e704304ba614eaee17884204677702951`
    (distinto del de L3, `c59d1f8b…`: el tag se movió; se fija el vigente).
  - `api/Dockerfile` (dos `FROM`), `web/Dockerfile` (dos `FROM`), `infra/compose.yml` (`db`),
    `infra/compose.dev.yml` (`db_test`) y `scripts/ci/test_nginx_conf.sh` (variable `NGINX_IMAGE`,
    usada en sus cuatro `docker run`) por digest, con la fecha y el comando de renovación en el
    comentario de encima. `ci.yml`: el comentario del servicio `postgres:16` gana la fecha y el comando.
  - `scripts/workflow/run-gates.sh` corre `test_images_pinned` entre `test_check_key_files` y
    `test_nginx_conf`; `.github/workflows/ci.yml`, job `scripts`, gana el paso "imágenes base por
    digest (S3-D62)".
  - `test_images_pinned.sh`: 7 ok, 0 fallas. `test_compose_config.sh`: 36 ok, 0 fallas.
    `test_nginx_conf.sh`: 62 ok, 0 fallas. `scripts/workflow/tests/run.sh`: 5 de 5 archivos en verde.
- Dependencias de desarrollo del front (W0-1.5, S3-D63):
  - `npm audit --audit-level=high` de partida: 11 hallazgos (2 moderate, 7 high, 2 critical):
    `vitest` critical (directa), `tinypool` critical, `@vitest/mocker` moderate,
    `@vitest/coverage-v8` moderate (directa), `braces`, `micromatch`, `fast-glob`, `globby`,
    `stylelint` (directa), `stylelint-config-recommended` y `stylelint-config-standard` (directa) high.
  - `npm install -D vitest@latest @vitest/coverage-v8@latest stylelint@latest stylelint-config-standard@latest`:
    `vitest` y `@vitest/coverage-v8` 3.2.7 → 5.0.5 (mayor; Node `^22.12.0 || ^24.0.0`, aquí 24.14.0);
    `stylelint` 17.16.0 y `stylelint-config-standard` 40.0.0 ya eran las últimas estables.
    `npm audit fix` sin `--force`: sin cambios.
  - Después: 7 high, 0 critical, 0 moderate, todos de una sola causa sin arreglo publicado:
    `braces` (GHSA-vfj7-8cjw-p6xm, `<=3.0.3`; 3.0.3 es la última) por `micromatch`, `fast-glob` y
    `globby` de `stylelint`. Desviación del plan ("auditoría en cero"): no se adopta `stylelint`
    `18.0.0-next.0` (prerelease del mismo día) ni se baja a 7.7.0; residual con dueño en DECISIONES.
    `npm audit --omit=dev --audit-level=high`: 0 hallazgos.
  - Sin cambios de configuración: `vite.config.ts`, `src/test/setup.ts` y `tests/lint/*` siguen
    iguales. `npm run lint && npx tsc --noEmit && npm test -- --run --coverage && npm run build` en
    verde con vitest 5: 110 archivos, 1.763 pruebas; cobertura 97,83 % de sentencias, 95,45 % de
    ramas, 96,49 % de funciones y 98,81 % de líneas (el v8 de vitest 4+ remapea por AST y los
    números no son comparables uno a uno con los de 3.2.7; el umbral es 80); build en verde.
  - `npm run licenses`: MIT 12, ISC 1 (producción). `bash scripts/ci/notice.sh`: `NOTICE` sin cambios.
  - `ci.yml`, job `web`: paso "auditoría de dependencias de desarrollo (informativo, S3-D63)" con
    `npm audit --audit-level=high` y `continue-on-error: true`, después del de producción.
- Entorno local y repositorio (W0-1.6, S3-D58, S3-D64):
  - `.gitignore`: `*.dump` ya estaba; `*.sql.gz` agregado bajo "Volcados de base de datos"
    (`git check-ignore` lo confirma). `test_check_key_files.sh`: 9 ok.
  - `.env.seed`: antes de borrarlo, el admin del seed está activo, sin bloqueo, sin cambio de
    contraseña pendiente y su login por Nginx responde 200. `E2E_ADMIN_EMAIL` y
    `E2E_ADMIN_PASSWORD` se exportaron solo en la shell de la sesión (no se guardaron en ningún
    archivo) y se borró `.env.seed`. El admin vive en la base y en el gestor de contraseñas del
    operador; si la contraseña se pierde, `tools issue-reset-link <admin> --as <admin>` (RUNBOOK §8).
  - Prueba negativa de S3-D61: `bash scripts/workflow/slice-gate.sh memberships` →
    `slice-gate: módulo inexistente: api/src/app/modules/memberships`, salida 1, sin sello en `.git/apex/`.
- Docker (W0-1.7):
  - `$DC build api web` sigue fallando por el permiso `network.host` de `bake` (misma causa de la
    línea base); build con `docker buildx build --load --network host --allow network.host`: las
    etapas resuelven `python:3.12-slim@sha256:cb33f7f7…`, `node:22-alpine@sha256:fe4f6d74…` y
    `nginx:stable-alpine@sha256:47928bf6…`.
  - `$DC up -d --no-build`: `db` y `db_test` se recrean con `postgres:16@sha256:9e2cf628…` (misma
    imagen local, volumen `apex_pgdata` intacto); los cuatro servicios `healthy`;
    `alembic current` = `0007_plans (head)`.
  - `bash scripts/ci/web-smoke.sh`: 0 fallas. `bash scripts/smoke/headers.sh`: 0 fallas.
  - `docker image inspect`: `apex-api:local` `sha256:0c11e0eb5b4efa8622c5d334a9cecd0a0bba9020614b7329c6ea9ea547358cc5`
    (2026-10-22T20:09:29Z), `apex-web:local` `sha256:2195593533d06619b77645d9b4c6ab1ee54f867079f7f99936e14da329b80672`
    (2026-10-22T20:09:58Z).
- Gate (W0-1.8): `bash -n` de los 17 scripts de `scripts/ci`, `scripts/smoke` y `scripts/workflow`
  sin errores; `test_images_pinned.sh`, `test_compose_config.sh`, `test_nginx_conf.sh` y
  `test_check_key_files.sh` con 0 fallas; `scripts/workflow/tests/run.sh` 5 de 5; front completo en
  verde (arriba). Gate que sella: `slice-gate.sh web/app` con `tests/unit/playwright-config.test.ts`,
  `tests/unit/index-html.test.ts`, `tests/unit/no-role-literals.test.ts` y
  `tests/lint/boundaries.test.ts` (los cuatro verificados con `ls` antes; E4). Su resultado y el
  hash del checkpoint van en la evidencia posterior al sello (E8).
- Desviaciones: `npm audit` de desarrollo con 7 high residuales sin arreglo publicado (arriba);
  digest de `nginx:stable-alpine` distinto del anotado en L3; build local por buildx directo en
  lugar de `$DC build`.

### Evidencia de S3-W0-1 (posterior al sello, E8)

- Gate que sella: `slice-gate.sh web/app tests/unit/playwright-config.test.ts tests/unit/index-html.test.ts tests/unit/no-role-literals.test.ts tests/lint/boundaries.test.ts`
  en verde al primer intento: eslint 0 errores (1 aviso previo: `tests/lint/boundaries.test.ts` está en
  el patrón de ignorados de eslint), `tsc -p tsconfig.slice.json` limpio, vitest 4 archivos y 24 pruebas.
- Revisión de los scripts por `code-reviewer` antes del sello: sin hallazgos CRITICAL, HIGH ni MEDIUM.
  Nota menor: un `FROM --platform=...`, `FROM scratch` o un `FROM <etapa>` daría un rojo ruidoso en
  `test_images_pinned.sh` (hoy no existe ninguno).
- Checkpoint `452453b` (`chore(checkpoint): chore(sprint-03): S3-W0-1 ...`); `git status` limpio después.

### S3-W0-2 · Rojo (stubs W0-2.1 y pruebas W0-2.2)

- Línea base: HEAD `a072305`, árbol limpio; `pytest -m "not perf"` con `TEST_DATABASE_URL` en verde
  (1.987 ok, 4 saltadas, 3 deseleccionadas); `ruff check` y `mypy src` limpios.
- Rojo: 2.078 recolectadas; **47 fallan** (todas de W0-2 y por comportamiento: `NotImplementedError`
  de los stubs, `KeyError: 'cache-control'`, 500 en lugar de 503, `.env.example` sin las once
  variables, `members/router.py` con `ratelimit.enforce`), 2.027 ok (1.986 de la línea base, porque
  una previa de `test_env_example` pasa a rojo, y 41 nuevas que ya pasan sobre los stubs), 4
  saltadas. 87 pruebas nuevas en total (46 en rojo y 41 en verde). `ruff format`, `ruff check` y `mypy src` limpios.
  `db_test` sin residuos (planes, socios, usuarios `@test.apex` y sesiones `idle in transaction` en 0).
  - Fallan: `tests/core/test_db_timeouts.py` 18 de 24; `tests/core/test_ratelimit.py` 9 de las 10
    nuevas; `tests/core/test_pagination_chunks.py` 9 de 10; `tests/core/test_env_example.py` 3 (una es
    la previa `test_toda_variable_de_settings_esta_documentada`, porque `.env.example` no se tocó, E3
    del Sprint 2); `tests/architecture/test_user_limits_catalog.py` 3 de 6;
    `tests/core/test_errors_busy.py` 2 de 5; `tests/cli/test_db_timeouts_cli.py` 2 de 7;
    `tests/architecture/test_error_responses_in_openapi.py` 1 de las 2 nuevas.
  - Verdes sobre los stubs (41; el stub ya es el comportamiento: constantes y alias): las 12 nuevas
    de `test_config.py`, las 9 de `StaffDep` y `AdminDep` en `test_require_role.py`, 6 de
    `test_db_timeouts.py` (`BUSY_SQLSTATES`, `DatabaseBusy`, el control del engine sin tiempos, el AST
    de `env.py` y los dos `athrow` que no se traducen), 3 de `test_errors_busy.py`, el catálogo
    `USER_LIMITS`, 5 del CLI, "las operaciones sin rol no declaran 503", 3 de
    `test_user_limits_catalog.py` (dos son controles del analizador) e `ID_BATCH == 200`.
- Verde desechable (revertido; solo para validar el Rojo): con una implementación mínima de W0-2.3 la
  suite da 2.073 ok y 1 falla, `test_docs_openapi_json_esta_al_dia` (el `503` nuevo; lo cierra P-API,
  W0-2.5). Encontró la trampa de la decisión 4.
- Stubs: `core/config.py` (tres `DB_*_TIMEOUT_MS` con `ge=0` y ocho `USER_*_LIMIT_*` con `gt=0`,
  definitivos); `core/db.py` (`BUSY_SQLSTATES`, `BUSY_MESSAGE`, `BUSY_RETRY_AFTER_S` y `DatabaseBusy`
  definitivos; `server_settings_from`, `sqlstate_of` y `translate_busy` con `NotImplementedError`);
  `core/ratelimit.py` (`USER_LIMITS` y `PII_SEARCH_BUCKET` definitivos; `user_limits_from`,
  `enforce_user_limit` y `usage` con `NotImplementedError`); `core/security.py` (`StaffDep` y
  `AdminDep` definitivos); `core/pagination.py` (`ID_BATCH`; `chunked` con `NotImplementedError`);
  `cli.py` (`--db-timeouts` en `@app.callback()`, acepta cualquier texto y no hace nada;
  `DB_TIMEOUTS_CHOICES` y `_runtime_options` sin usar todavía). Sin cambio de comportamiento:
  `get_session`, `create_engine_from`, `_publicar_error_response`, `main.create_app`, `.env.example` y
  los routers quedan como estaban.
- Archivos de prueba: nuevos `tests/core/test_db_timeouts.py`, `tests/core/test_errors_busy.py`,
  `tests/core/test_pagination_chunks.py`, `tests/cli/test_db_timeouts_cli.py` y
  `tests/architecture/test_user_limits_catalog.py`; ampliados `tests/core/test_config.py`,
  `tests/core/test_env_example.py`, `tests/core/test_ratelimit.py`, `tests/core/test_require_role.py`
  (con dos rutas nuevas en `tests/core/_routes.py`) y
  `tests/architecture/test_error_responses_in_openapi.py`.
- Importadores de lo que se tocó (grep de `app.core.<m>`): `core/db` 37 archivos (entre ellos
  `migrations/env.py`, `cli.py`, `core/audit.py`, `core/security.py`, `core/health.py`, `main.py` y los
  `models`, `router` y `service` de auth, members, plans y settings); `core/config` 39;
  `core/ratelimit` 9 (`main.py`, `auth/links.py`, `auth/router.py`, `auth/sessions.py`,
  `auth/users.py`, `members/router.py` y 3 de pruebas); `core/security` 63; `core/pagination` 17;
  `app.cli` 16. `core/db.py` ahora importa `core/errors.DomainError` (sin ciclo: `errors` solo importa
  `core/context`; `test_core_import_direction` en verde).

#### Decisiones de prueba que el Verde debe respetar

1. `server_settings_from` da `"<n>ms"` y `"0"` exacto para cero; el engine de `create_engine_from`
   responde `SHOW` = `10s`, `30s` y `1min`. `sqlstate_of` lee `error.orig.sqlstate` y devuelve `None`
   para todo lo que no tenga `orig` o `sqlstate` (también un `ValueError`).
2. `get_session`: el `try/except DBAPIError` abarca todo el `async with` (E7) y re-lanza
   `DatabaseBusy` con `raise ... from error` (la prueba mira `__cause__`); un `IntegrityError` o un
   `DomainError` salen intactos (la misma instancia). El caso "al confirmar" deja un `UPDATE` ORM
   pendiente que sale en el flush del commit.
3. El 503 lleva `Cache-Control: no-store` aunque la respuesta la arme `_handler_dominio` (las cabeceras
   de la dependencia `no_store` no llegan a una respuesta de error); por ejemplo
   `DatabaseBusy.headers = {"Retry-After": "1", "Cache-Control": "no-store"}`. Las pruebas de
   `translate_busy` solo exigen `headers["Retry-After"] == "1"`. Sin traza `ERROR` en el log.
4. OpenAPI: el `503` NO entra en `_DESCRIPCIONES` ni en `ERROR_RESPONSES` (si entra, el `503` de
   `/health` pasa a `ErrorResponse` y fallan `test_health_no_declara_errores_*` y la prueba nueva). Hoy
   ninguna operación del contrato declara `security`, así que "seguridad declarada" se decide sobre las
   rutas: dependencia con la marca `__apex_roles__` (como `route_has_role_dependency`). `errors.py` no
   puede importar `security.py` a nivel de módulo (ciclo `security -> db -> errors`): marca por duck
   typing o import perezoso. Las públicas (login, refresh, logout, forgot, reset) no declaran `503`.
5. `user_limits_from` sigue E15 (`USER_WRITE` a `memberships-write` y `payments-write`;
   `USER_ADMIN_WRITE` a `admin-write`; `USER_MEMBERS_WRITE` a `members-write`; `USER_SEARCH` a
   `members-search`; `USER_DETAIL` a `members-detail`; las tres `USER_REVEAL_*` a las tres
   `members-reveal*`) y conserva las ventanas del catálogo. `enforce_user_limit` usa `kind="user"`, la
   clave `str(user_id)`, el tope de `request.app.state.user_limits`, `KeyError` para un bucket fuera de
   `USER_LIMITS`, y no escribe el usuario en el log. `usage` no crea la clave al consultar.
6. `chunked` devuelve un iterador, conserva el orden y da `ValueError` (mensaje con `size`) para un
   tamaño `<= 0` (decisión de prueba: sin ella `size=0` sería un bucle infinito).
7. CLI (E7): `--db-timeouts` acepta solo `on` u `off` (otro valor sale con 2); el callback fija el
   estado en cada invocación (un `off` no se arrastra a la siguiente); `cli_runtime` construye el engine
   con una copia (`model_copy`) del `Settings` recibido con los tres en 0, sin mutar el original. La
   prueba parchea `app.core.db.create_engine_from` solo alrededor de `cli_runtime` (`export-openapi`
   también construye un engine dentro de `create_app`).
8. `test_user_limits_catalog` acepta como bucket un literal del catálogo o el nombre
   `PII_SEARCH_BUCKET` (Name o Attribute). `CLAVES_SIN_RUTA_TODAVIA` lista los siete buckets cuya ruta
   no existe; cada slice que publica la ruta de uno lo saca en su Rojo (E2): B1 y B2
   `memberships-write`, B4 `payments-write`, B5 `admin-write`, B9b `members-detail`, B10 los tres de
   `members-reveal`.
9. `app.state.user_limits` lo fija `create_app`; como `app_http` usa `create_app`, no hace falta tocar
   `tests/conftest.py`.

#### Desviaciones del Rojo

- `app_rota` (`tests/core/_app_rota.py`) no se usa: es la fábrica de arranque fallido de US-020 y no
  sirve para el handler de 503. El 503 se prueba con la app real (`api_prueba`, cliente con
  `raise_app_exceptions=False`) y con una app mínima con el `get_session` real (E16).
- `.env.example` sin tocar (E3 del Sprint 2): por eso también falla la prueba previa
  `test_toda_variable_de_settings_esta_documentada`; la cierran las once líneas del Verde.
- `test_user_limits_catalog` agrega en forma progresiva la regla de S3-D69 "toda clave tiene al menos
  una ruta" (`CLAVES_SIN_RUTA_TODAVIA`), porque W0-2 solo cablea `members-write` y `members-search`.

### S3-W0-2 · Verde (W0-2.3 a W0-2.6)

- Verde: `core/db.py` (`server_settings_from`, `sqlstate_of`, `translate_busy`; `create_engine_from`
  con `server_settings`; `get_session` con el `try` sobre todo el `async with`, commit incluido, y
  `raise DatabaseBusy from error`; `DatabaseBusy.headers` con `Retry-After: 1` y
  `Cache-Control: no-store`); `core/errors.py` (`503` `ErrorResponse` con `MENSAJE_503` en toda
  operación con `__apex_roles__`, import perezoso de `security`); `core/ratelimit.py`
  (`user_limits_from` con la correspondencia de E15, `enforce_user_limit`, `usage` y
  `SlidingWindowStore.count`, que no crea la clave); `core/pagination.chunked`;
  `main.create_app` fija `app.state.user_limits`; `cli.py` (`--db-timeouts` solo `on`/`off`,
  `typer.BadParameter` y exit 2 en otro valor, estado fijado en cada invocación, `cli_runtime` con
  `model_copy` de los tres en 0); `members/router.py` con `enforce_user_limit(request,
  "members-write", ...)`, `enforce_user_limit(request, PII_SEARCH_BUCKET, ...)` y `StaffDep`;
  `plans/router.py` con `StaffDep` y `AdminDep`; `.env.example` con las once líneas activas.
  `migrations/env.py`, `tests/conftest.py` y las pruebas del Rojo sin cambios.
- Revisión de seguridad (`security-reviewer`, sobre `git diff a072305 -- api/src .env.example`):
  sin CRITICAL ni HIGH. Aplicados con prueba: LOW-1 (`WARNING` `db busy` con solo `sqlstate`,
  `test_get_session_deja_un_warning_con_solo_el_sqlstate`) y el techo `le=2147483647` de los
  `DB_*_TIMEOUT_MS` (`test_los_tiempos_de_espera_tienen_el_techo_de_postgresql`, 3 casos). No
  aplicados, con motivo y dueño en `DECISIONES.md` "S3-W0-2": piso de `DB_*` en producción
  (MEDIUM; el plan y el Rojo fijan `ge=0`; decide el orquestador en V), techo de `USER_*` (V4 los
  sube ×100 con `ENV=production`), `25P03` como 503 (MEDIUM-1; S3-D67 fija el conjunto) y el
  `crypto_ops` del rollback (MEDIUM-2; no se silencia una fila de la bitácora).
  Comprobado por el revisor: `current_user` usa `SessionDep` (se traduce), los listeners de
  auditoría hacen rollback completo, `pg_advisory_xact_lock(4270002)` respeta `lock_timeout`,
  `--db-timeouts off` no es alcanzable desde el api (nadie importa `app.cli`).
- Suite (`-m 'not perf'`): 2.082 recolectadas, **2.078 ok, 0 fallos, 4 saltadas**, 3
  deseleccionadas (las 47 del Rojo en verde, más 4 nuevas de la revisión); cobertura de `app`
  96 %; `ruff format`, `ruff check` y `mypy src` (72 archivos) limpios.
  `scripts/ci/test_compose_config.sh`: 0 fallas con el `.env.example` nuevo.
- Contrato (P-API): `export-openapi` dos veces con el mismo SHA-256 (`e2b7db2d…`), +240 líneas en
  `docs/openapi.json` (el `503` en las 24 operaciones con rol; login, refresh, logout, forgot y
  reset sin `503`; `/health` y `/api/v1/health` con su `503` `HealthOut`); `npm run gen:api`
  (+216 líneas en `types.ts`), `types.contract.test.ts` 5 ok, `tsc --noEmit` y `npm run lint`
  limpios.
- Docs: `docs/RUNBOOK.md` §9 completa; `DECISIONES.md` sección "S3-W0-2".
- Desviaciones: ninguna prueba del Rojo cambió; se agregaron 4 casos por la revisión. La
  evidencia de los gates, Docker y H-3 va en el commit `docs(sprint-03): evidencia de S3-W0-2`
  (E8).
