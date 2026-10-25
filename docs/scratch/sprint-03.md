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

### Evidencia de S3-W0-2 (después del sello; E8)

- Gates W0-2.6 con `PYTEST_ADDOPTS="-m 'not perf'"`, `ls` previo de los 21 archivos, seguidos y
  sin editar entre ellos, todos en verde al primer intento (cada uno con `tests/architecture`):
  1 `core/config` 241 ok; 2 `core/ratelimit` 212; 3 `core/security` 200; 4 `core/pagination`
  184; 5 `core/errors` 193; 6 `members` 216 y `plans` 224; 7 `cli` 189; 8 `architecture` 172;
  9 (sella) `core/db` 204. Una saltada en cada uno (`test_no_sensitive_in_logs`, US-074).
- Docker (sin tocar el árbol): la recarga por bind recogió el código; imagen del api
  reconstruida por `cli.py` (`docker buildx build --load --network host --allow network.host -t
  apex-api:local -f api/Dockerfile api`) y `$DC up -d --no-build api` → `healthy` en 6 s,
  `migraciones al día`, sin errores; `/api/v1/health` 200 por `:8180`; `alembic current` =
  `0007_plans (head)`. Un engine de `create_engine_from` dentro del contenedor responde
  `lock_timeout=10s`, `statement_timeout=30s`, `idle_in_transaction_session_timeout=1min`.
- Demostración de H-3 por Nginx `:8180`, con un access del admin firmado dentro del contenedor del
  api (no hay `.env.seed`, S3-D64):
  - psql en `apex-db-1`: `BEGIN; SELECT pg_advisory_xact_lock(4270002);` (`AUDIT_CHAIN_LOCK_KEY`
    de `core/audit.py`) a las 20:55:08.1 UTC, retenido 20 s con `pg_sleep(20)` y `ROLLBACK` a las
    20:55:28.2;
  - `POST /api/v1/members` a las 20:55:10.9 → **503** `{"error": {"code": "busy", "message":
    "La base de datos está ocupada; intenta de nuevo en un momento."}}` en **10,02 s**, con
    `Retry-After: 1` y `Cache-Control: no-store`; log del api: `WARNING` `app.db` `db busy` con
    `sqlstate: 55P03` y la línea `http_request` `status: 503`, `duration_ms: 10018.75`, ningún
    `ERROR` ni traza;
  - tras el `ROLLBACK`, el mismo `POST` a las 20:55:28.2 → **201** en 0,03 s (socio de prueba
    "Demo Hache Tres", CC terminado en 4599, `active`, queda en la base de desarrollo).
  - Observación previa al slice: por `:8180` toda respuesta del api lleva dos `Cache-Control:
    no-store` (el del api y el `add_header ... always` de `infra/nginx/snippets/proxy-api.conf`);
    pasa igual con `GET /plans`, no lo introduce W0-2 y es inocuo (mismo valor).
- `$DC run --rm tools --db-timeouts off export-openapi /tmp/o.json` → `openapi: escrito`, código
  0; `--db-timeouts quizas` → "Invalid value for --db-timeouts", código 2. `pg_stat_activity`
  sin sesiones `idle in transaction` al terminar.
- Checkpoint `5e84bab`; `git status` limpio después.

### S3-B1 · Rojo (B1.1 a B1.4 y la prueba de `0008`)

- Línea base: HEAD `d8c2810`, árbol limpio; `pytest -m "not perf"` con `TEST_DATABASE_URL`: 2.078 ok,
  4 saltadas, 3 deseleccionadas; `ruff check` y `mypy src` limpios.
- B1.1 verificado: tras fábrica, limpieza y apoyos, `pytest tests/members tests/plans` 422 ok.
- Rojo: 2.335 recolectadas; **198 fallan**, 2.130 ok (las 2.078 de la línea base más 52 nuevas que
  ya pasan sobre los stubs), 4 saltadas, 3 deseleccionadas. `ruff format`, `ruff check` y
  `mypy src` (84 archivos) limpios. `db_test` sin residuos: `alembic_version = 0007_plans`, sin
  `memberships.memberships`, 0 planes, 0 socios, 0 usuarios `@test.apex`, 0 sesiones
  `idle in transaction`.
  - Fallan por archivo: `tests/memberships/test_rules.py` 80 (`NotImplementedError` de las reglas;
    `ValueError` de fechas invertidas ausente); `tests/migrations/test_0008_memberships.py` 50 (no
    existe la revisión); `tests/memberships/test_sell_service.py` 25 y `test_sell_router.py` 15
    (`NotImplementedError` de `sell`/`compute_end_date` o `UndefinedTable`);
    `tests/core/test_config.py` 9 (S3-D79, piso de 1.000 ms en producción);
    `tests/core/test_locks.py` 5; `tests/memberships/test_refs_for.py` 4;
    `tests/architecture/test_service_import_graph.py` 3 (`memberships` aún no importa
    `members`/`plans`/`settings`: `test_cada_arista_permitida_existe`,
    `test_memberships_depende_de_members_plans_y_settings`,
    `test_plans_no_importa_services_y_solo_memberships_lo_importa`);
    `tests/architecture/test_guarded_calls.py` 2 (`lock_membership` sin `with_for_update` ni
    `populate_existing`); `tests/migrations/test_triggers_siempre_activos.py` 2;
    `tests/architecture/test_no_trigger_tampering.py` 1 (el docstring de `core/audit.py`, línea
    13, dice `` `TRUNCATE` ``: el Verde lo reescribe, por ejemplo "el vaciado de la tabla");
    `tests/memberships/test_lock_order.py` 1; `tests/core/test_openapi_export.py` 1
    (`docs/openapi.json` sin la ruta nueva: lo cierra P-API, B1.8).
  - Verdes sobre los stubs (52; el stub ya es el contrato): catálogos y constantes, inmutabilidad
    de los valores, 401, 422 de `member_id` en la ruta, OpenAPI de la ruta (201, 401, 403, 404,
    409, 422, 429, 500, 503), `NotImplementedError` de `renew` y `first_payment`, `CON_LIMITE` y
    `test_user_limits_catalog` con la ruta nueva, `test_sql_literals_constant` (todo el código
    actual cumple E6), `test_handlers_no_new_locks` (lista vacía), `test_banned_imports`
    ampliada, `test_no_cross_models` generalizada, `test_audited_tables`, `test_audit_module`,
    `test_0007_plans` "en la cadena" y los controles de cada analizador.
- Verde desechable (revertido; solo para validar el Rojo): migración `0008`, reglas, `sell`,
  `refs_for`, `lock_member`, el piso de S3-D79 y el docstring de `core/audit.py`. Suite: 2.324 ok y
  4 fallos: `test_docs_openapi_json_esta_al_dia` (esperado, P-API), `test_ninguna_funcion_supera_50_lineas`
  (el `sell` desechable de 70 líneas: el Verde debe partirlo, E11) y dos defectos de prueba del
  router (`MissingGreenlet` al leer `plan.id`/`previa.id` tras un 404/409: la sesión revierte y el
  ORM expira), ya corregidos capturando los ids antes. Con eso `pytest tests/memberships
  tests/migrations` en corrida conjunta (E1): 254 ok. Antes de borrar la revisión desechable se
  bajó `db_test` a `0007_plans`.
- Stubs: `core/locks.py` (`MEMBER_LOCK_NAMESPACE = 0` y `MEMBER_LOCK_SQL` definitivos;
  `lock_member` con `NotImplementedError`); `modules/memberships/`: `models.py` (completo, con
  `STATUSES`, `EXCLUDE_NAME`, `IDENTITY_CONSTRAINT`, `NO_DELETE_CONSTRAINT`), `exceptions.py`,
  `schemas.py`, `events.py` y `router.py` completos (contrato), `rules.py` (tipos definitivos sin
  validación de `__post_init__`; funciones con `NotImplementedError`), `sell.py` (`sell`,
  `lock_membership`, `get_payment_target`), `queries.py` (`refs_for`, `_load_freezes_for`),
  `lifecycle.py` (solo docstring), `service.py` fachada con `__all__` (`MembershipSold`,
  `get_payment_target`, `refs_for`, `sell`). `main.MODULES` suma `memberships`;
  `migrations/env.py` importa `memberships.models`; `PRIVATE_HELPERS["memberships"]`.
- Fixtures y apoyos: `tests/factories/memberships.py` (`make_membership`, `make_memberships`) y
  `FACTORIES["memberships.memberships"]`; `tests/conftest.py`: `TRIGGERS_DE_MEMBERSHIPS`,
  `LIMPIAR_MEMBERSHIPS` (en `LIMPIEZA_DE_SESION` antes de `LIMPIAR_MEMBERS`) y
  `limpiar_tras_dos_sesiones(engine, ultima_seq)` (el `finally` de `dos_sesiones`, extraído para
  que `test_triggers_siempre_activos` pruebe exactamente esa limpieza); `tests/memberships/`
  `__init__.py`, `_apoyo.py` y `conftest.py` (`bus_confirmado` copiado y `memberships_service`
  importado al nivel del módulo).
- Archivos de prueba nuevos: `tests/memberships/test_rules.py`, `test_sell_service.py`,
  `test_sell_router.py`, `test_refs_for.py`, `test_lock_order.py`; `tests/core/test_locks.py`;
  `tests/migrations/test_0008_memberships.py`, `test_triggers_siempre_activos.py`;
  `tests/architecture/test_no_trigger_tampering.py`, `test_sql_literals_constant.py`,
  `test_guarded_calls.py`, `test_handlers_no_new_locks.py`. Cambiados:
  `test_service_import_graph.py` (reescrita, D2), `test_audit_module.py`, `test_audited_tables.py`,
  `test_no_cross_models.py`, `test_error_codes_per_route.py`, `test_user_limits_catalog.py`,
  `test_banned_imports.py`, `tests/migrations/test_0007_plans.py`, `tests/core/test_config.py`.
- Importadores de lo tocado: `app.main.MODULES` lo leen `cli.py` (`_load_module_services`),
  `tests/conftest.py` (`load_module_services`), `test_audit_module.py`, `test_audited_tables.py` y
  `test_user_limits_catalog.py` (por `API_PREFIX`); `core/locks.py` es nuevo (lo usará
  `memberships/sell.py`; hoy lo importan `test_locks.py`, `test_sql_literals_constant.py` y
  `test_banned_imports.py` lo recorre); `tests/conftest.py` lo importan todas las pruebas
  (`LIMPIAR_MEMBERSHIPS` y `limpiar_tras_dos_sesiones` son nuevos, `dos_sesiones` conserva su
  comportamiento); `tests/architecture/_imports.PRIVATE_HELPERS` lo leen `find_forbidden_imports`
  (todas las pruebas de módulos) y `test_no_cross_models.py`; `FACTORIES` solo
  `test_no_plaintext_at_rest.py` (solo tablas cifradas).

#### Decisiones de prueba que el Verde debe respetar

1. **S3-D79 (decisión del orquestador en este Rojo).** Los tres `DB_*_TIMEOUT_MS` tienen piso de
   1.000 ms con `ENV=production` (validador en `Settings`, como `PASSWORD_MIN_LENGTH`; mensaje con
   el nombre de la variable, `ConfigError.invalid` la incluye); `0` sigue aceptado fuera de
   producción, y el CLI los desactiva con `model_copy` después de validar (no revalida). La prueba
   de W0-2 que aceptaba `0` con el `Settings` de producción se ajustó: no era un error de la prueba
   sino una decisión posterior (queda en su docstring). Va a `DECISIONES.md` en el Verde.
2. `pg_get_functiondef` nunca imprime `SECURITY INVOKER` (es el valor por defecto; solo imprime
   `SECURITY DEFINER`): la prueba de L-10 usa `pg_proc.prosecdef = false`, `lanname = plpgsql`,
   `proconfig == ['search_path=pg_catalog']` y "search_path" en la definición. Verificado contra
   PostgreSQL 16 de `db_test`.
3. `guard_identity` (S3-D48, "cualquier cambio sobre una `cancelled`"): sobre una cancelada se
   rechazan `status`, `cancel_reason`, `cancelled_by`, `cancelled_at` y también `end_date`; el
   desechable comparó además `classes_remaining`. Los cambios legítimos (`end_date`, `status`,
   `classes_remaining`, anular y un `UPDATE` sin cambios) pasan. Error: 23000 con
   `constraint_name = memberships_identity`; borrar y vaciar: 23000 con `memberships_no_delete`.
4. `validate_start_date(start, today, *, max_retroactive_days: int | None, max_ahead_days=366)`:
   `None` = sin tope retroactivo (lo pasa `sell` con `enforce_retroactive_limit=False`); compara
   con `today ± timedelta` y nunca suma días a `start` (sin `OverflowError` con `9999-12-31` ni
   `0001-01-01`). Los mensajes de `ValueError` de `__post_init__` nombran `start_date` y
   `frozen_from`; `compute_status` nombra `expiring_days`.
5. Excepciones con la firma de `DomainError` y `field` por defecto (`plan_id`, `start_date`), para
   `reraise_with_prefix` de B4. `MembershipOverlap` lleva `existing_id` cuando lo da
   `find_overlap` y no lo lleva cuando sale de la `EXCLUDE` (23P01).
6. `test_sell_service` reemplaza `sell._check_open_memberships` con un `monkeypatch` para probar la
   traducción de la `EXCLUDE`: el nombre (E11) y su llamada desde `sell` por atributo del módulo
   son contrato de prueba. Los handlers que fallan se prueban con una excepción propia, no
   `RuntimeError` (`NotImplementedError` lo es).
7. `refs_for` consulta `memberships.memberships` una vez por lote de `ID_BATCH` (450 ids = 3
   sentencias); `names_for` de socios y planes no se cuenta. Sin ids, cero sentencias.
8. `classify_open` ignora también las canceladas y las vencidas; una `pending_payment` es futura
   aunque haya empezado o vencido (D8). `is_covered` con lista vacía o todo anulado es falso.
9. `lock_member` traduce el 55P03 con `raise DatabaseBusy from error` (la prueba mira `__cause__`);
   la llave es `hashtextextended(str(member_id), 0)` (comprobada en `pg_locks`).
10. `test_service_import_graph` exige `ALLOWED_EDGES` exactamente igual al grafo de nivel de módulo
    (`test_cada_arista_permitida_existe`) y el comentario `# lazy: G-03` en todo import perezoso;
    los pares se importan en `python -I -c` en los dos órdenes.
11. `test_no_trigger_tampering` busca `TRUNCATE` en mayúsculas o `truncate [table] esquema.tabla`
    en cualquier caso (el helper `auth.rules.truncate` no cuenta); el docstring de `core/audit.py`
    sí cuenta y debe cambiar.

#### Desviaciones del Rojo

- `plan_renewal`, `resolve_member_status`, `apply_freeze`, `should_revert`, `parse_status_filter` y
  `prefix_field` no tienen stub ni prueba en B1: nacen con sus slices (B6, B7, B2, B5, B7, B4); el
  blueprint B1 los nombra en "Tipos puros" pero la matriz de pruebas de B1 no los incluye.
- `docs/openapi.json` sin tocar (el Rojo no corre P-API): `test_docs_openapi_json_esta_al_dia` en rojo.
- El caso `fin` en una cancelada y el de L-10 sin `SECURITY INVOKER` textual se explican arriba
  (decisiones 2 y 3).

### S3-B1 · Verde (B1.5 a B1.9)

- Línea base del Verde: HEAD `d8c2810` con el Rojo sin confirmar; `pytest -m "not perf"`: 198 fallan,
  2.130 ok, 4 saltadas, 3 deseleccionadas (igual que el Rojo).
- Hallazgo de entorno: `apex-db-1` estaba en `alembic_version = 0008_memberships` (el Verde desechable
  se aplicó también a la base de desarrollo al arrancar el api) sin la revisión en el árbol: el api no
  arrancaba ("Can't locate revision", `unhealthy`). La tabla estaba vacía (0 filas, 0 auditoría). Se
  resolvió dentro de P-MIG (DECISIONES, S3-B1).
- B1.5 P-MIG: volcado `docs/scratch/sprint-03-antes-0008_memberships.dump` con `$DC exec -T db
  pg_dump ... -n memberships -n payments` desde Bash (`chmod 600`, ignorado por git, `pg_restore -l`
  legible, 18 entradas); `$DC stop api`; `api/migrations/versions/0008_memberships.py`;
  `pytest tests/core/test_migrations.py tests/migrations/test_0008_memberships.py` 53 ok contra
  `db_test`; `alembic heads` = `0008_memberships (head)`; `$DC start api` → `healthy`, "migraciones al
  día"; ciclo `downgrade -1`/`upgrade head` en `apex-db-1` (reemplaza los objetos desechables).
- B1.6 Verde: `rules.py` (todas las puras y la validación de `__post_init__`), `sell.py` partido
  (`sell` en `begin_nested()`, `_sale_context`, `_check_open_memberships`, `_insert_membership`,
  `_sell_out`, `lock_membership`, `get_payment_target`; ninguna función pasa de 50 líneas),
  `queries.py` (`refs_for` por `chunked`, `_load_freezes_for` vacía hasta B2), `core/locks.py`
  (`lock_member`; 55P03 → `DatabaseBusy` con `from`), docstring de `core/audit.py` sin la palabra de
  vaciado, `Settings` con el piso de S3-D79 (`DB_TIMEOUT_FLOOR_MS`). `router.py`, `service.py`,
  `models.py`, `events.py` y `exceptions.py` del Rojo sin cambios de contrato.
- Revisión de seguridad (antes del gate): 0 CRITICAL, 0 HIGH, 2 MEDIUM, 5 LOW. Aplicados M1 (`renew=true`
  da 422 `field="renew"` hasta B6, validador en `SellMembershipIn`) y L1 (`guard_identity` vigila `id`,
  `created_at`, `created_by`; CHECK `cancel_fields_only_when_cancelled` en la migración y el modelo).
  M2 (dueño B10), L2 (S3-D49), L3, L4 y L5 (dueño B4) anotados en DECISIONES.
- Pruebas nuevas del Verde: `tests/memberships/test_payment_target.py` (4),
  `tests/memberships/test_sell_router_renew.py` (2) y `tests/migrations/test_0008_endurecimiento.py`
  (6). Ninguna prueba del Rojo cambió.
- Suite: 2.340 ok, 4 saltadas, 3 deseleccionadas, 0 fallos; cobertura de `app` 96 % (`memberships`
  98 %); `ruff format`, `ruff check` y `mypy src` (84 archivos) limpios.
- B1.7 Docs: RUNBOOK §6 (rollback de `0008`), §9 (piso de producción) y §10 (volcado, comprobación de la
  `EXCLUDE`, los triggers y las funciones con psql, y la venta); `.env.example` (comentario del piso);
  DECISIONES "S3-B1".
- B1.8 P-API: `export-openapi` dos veces idéntica (la ruta `POST /api/v1/members/{member_id}/memberships`
  y sus esquemas, solo adiciones: 323 líneas en `docs/openapi.json`, 202 en `web/src/core/api/types.ts`);
  repetida tras la revisión sin cambios; `npm run gen:api`, `types.contract.test.ts` 5 ok y
  `npx tsc --noEmit` limpio.
- Desviaciones: el plan "Mensual" de 120.000 en la base de desarrollo se llama "Mensual mvjipju3" (el
  llamado "mensual" vale 320.000): el smoke de B1.10 usa el id real del de 120.000. La evidencia de
  B1.10 va al commit `docs(sprint-03): evidencia de S3-B1` (E8).

### Evidencia de S3-B1 (B1.10, después del sello; E8)

- Gates B1.9 seguidos, sin editar entre ellos, `PYTEST_ADDOPTS="-m 'not perf'"`, `ls` previo de los 14
  archivos, todos verdes al primer intento: 1 `core/locks` 220 ok; 2 `architecture` 302 ok; 3 corrida
  conjunta `tests/memberships tests/migrations` 266 ok; 4 (sella) `memberships` 412 ok (con
  `test_payment_target`, `test_sell_router_renew` y `test_0008_endurecimiento`). Una saltada en cada
  gate (`test_no_sensitive_in_logs`, US-074). Checkpoint `5c9bb45`.
- P-MIG pasos 6 y 7 en `apex-db-1` (05:28 UTC): api `healthy`; `alembic current` = `0008_memberships
  (head)`; `downgrade -1` → `0007_plans` y `upgrade head` → `0008_memberships (head)` (instala la
  versión final con L1). Restricciones: diez `ck_memberships_*`, `ex_memberships_member_dates` y
  `pk_memberships`; triggers `memberships_forbid_delete`, `memberships_forbid_truncate` y
  `memberships_guard_identity` en `A`; funciones `forbid_delete` y `guard_identity` con
  `prosecdef = f` y `proconfig = {search_path=pg_catalog}`.
- Smoke por Nginx `:8180` con un access del admin firmado dentro del contenedor del api (no hay
  `.env.seed`): `GET /members?q=1020304417` da "Prueba Smoke Uno" (`2b5b6860-…`); `POST
  /members/2b5b6860-…/memberships` con el plan de 120.000 ("Mensual mvjipju3", `b6fab314-…`) → **201**
  en 0,03 s, `pending_payment`, `2026-10-25` a `2026-11-24`, `agreed_price_cop = 120000`, `paid_cop
  = 0`, `member_name` "Prueba Smoke Uno"; la segunda venta → **409** `membership_conflict` con
  `existing_id` de la primera (D8: una `pending_payment` es futura y la revisión de conflicto va antes
  que la de solape; `membership_overlap` sale con una no abierta que se cruza, cubierto por
  `test_sell_service`); `renew: true` → **422** `validation_error`, `field = renew` (M1);
  `/api/v1/health` 200.
- psql: `SELECT status, start_date, end_date, agreed_price_cop FROM memberships.memberships` → una fila
  `pending_payment | 2026-10-25 | 2026-11-24 | 120000`; `audit.audit_log` → una fila `insert` con
  `subject_member_id = 2b5b6860-…` y `user_id` del admin. Dentro de transacciones revertidas:
  `INSERT` crudo solapado (1 a 30 nov) → `23P01` `CONSTRAINT NAME: ex_memberships_member_dates`;
  `UPDATE … SET agreed_price_cop = 1` → `23000` `memberships_identity`; `DELETE` → `23000`
  `memberships_no_delete`; con `SET LOCAL session_replication_role = replica` el `UPDATE` sigue
  rechazado (`memberships_identity`). Queda una sola fila (la venta del smoke, en la base de
  desarrollo). Log del api sin `ERROR` en los últimos 5 minutos; 0 sesiones `idle in transaction`.

### S3-B2 · Rojo (B2.1 a B2.3 y la prueba de `0009`)

- Línea base: HEAD `b19adcd`, árbol limpio; `pytest -m "not perf"` con `TEST_DATABASE_URL`: 2.340 ok,
  4 saltadas, 3 deseleccionadas; `ruff check` y `mypy src` (84 archivos) limpios.
- Rojo: 2.457 recolectadas (113 más que la línea base; 3 deseleccionadas); **109 fallan**, 2.344 ok,
  4 saltadas. Cuenta: de las 2.340 verdes de la línea base, 3 pasan a rojo por B2 (los dos casos con
  base de `test_triggers_siempre_activos` y `test_docs_openapi_json_esta_al_dia`) y 1 desaparece (el
  parámetro `memberships.membership_freezes` de `PENDING_AUDITED`); se suman 8 nuevas que ya pasan
  sobre los stubs (lista abajo). `sell-sell` de `test_lock_order` se reparametrizó y sigue verde. `ruff format`, `ruff check` y `mypy src` (84 archivos) limpios.
  `db_test` sin residuos: `alembic_version = 0008_memberships`, sin `memberships.membership_freezes`,
  0 membresías, 0 planes, 0 socios, 0 usuarios `@test.apex`, 0 sesiones `idle in transaction`,
  los tres triggers de `memberships.memberships` en `A`. `apex-db-1` en `0008_memberships`, api
  `healthy`.
  - Fallan por archivo: `tests/memberships/test_freeze_rules.py` 32 (`NotImplementedError` de
    `apply_freeze`); `tests/migrations/test_0009_membership_freezes.py` 28 (no existe la revisión
    ni la tabla); `tests/memberships/test_freeze_service.py` 26 (`NotImplementedError` de `freeze`
    o `UndefinedTable` de `membership_freezes`; la de la `EXCLUDE` de membresías además por
    `AttributeError`: el stub de `lifecycle` aún no importa `find_overlap`, ver decisión 6);
    `tests/memberships/test_freeze_router.py` 19 (500 por el `NotImplementedError` o
    `UndefinedTable` al leer las congelaciones); `tests/migrations/test_triggers_siempre_activos.py`
    2 (faltan los dos triggers de `membership_freezes`); `tests/memberships/test_lock_order.py` 1
    (`freeze-sell`); `tests/core/test_openapi_export.py` 1 (`docs/openapi.json` sin la ruta nueva ni
    el `FreezeOut` nuevo: lo cierra P-API, B2.7).
  - Verdes sobre los stubs (el stub ya es el contrato): `FreezeError` con código, campo y estado;
    401 sin token; 422 de `membership_id` no UUID; OpenAPI de la ruta (200, 401, 403, 404, 409, 422,
    429, 500, 503; cuerpo `FreezeIn`, respuesta `MembershipOut`); esquemas `FreezeOut` y `FreezeIn`;
    `CON_LIMITE` y `test_user_limits_catalog` con la ruta nueva; `test_audited_tables` (requerida,
    sin sujeto); `test_handlers_no_new_locks` (lista vacía y `freeze` no cuenta como handler);
    `test_0008_memberships` "en la cadena" y con `TRUNCATE ... CASCADE`; la parte de texto de
    `test_triggers_siempre_activos`.
- Verde desechable (revertido; solo `db_test`, con `$DC stop api` antes de escribir la migración y
  `$DC start api` después de borrarla, regla de S3-B1): migración `0009` mínima, `apply_freeze`,
  `_load_freezes_for` real y `freeze`. Suite: 2.451 ok y 2 fallos esperados
  (`test_docs_openapi_json_esta_al_dia`, P-API; `test_ninguna_funcion_supera_50_lineas`, el
  `freeze` desechable de una pieza: el Verde lo parte). Encontró dos defectos de prueba en
  `test_0009`, ya corregidos (`_congelacion` con `membership_id` duplicado en el caso NOT NULL;
  PostgreSQL imprime `BEFORE DELETE OR UPDATE`, no `BEFORE UPDATE OR DELETE`). Corrida conjunta
  `tests/memberships tests/migrations tests/architecture` (E1): 590 ok y solo el de 50 líneas.
  Después: `alembic -x url=<db_test> downgrade 0008_memberships`, archivo borrado, `rules`,
  `lifecycle`, `queries` y `sell` restaurados desde copia; `apex-db-1` nunca dejó `0008`.
- Stubs (B2.2): `models.py` (`MembershipFreeze` completo con CHECKs `dates_ordered` y `days_match`,
  `ex_membership_freezes_dates`, `ix_membership_freezes_membership`, FK a `memberships.memberships`,
  `__audited__` sin `__audit_subject__` anotado para US-106; constantes `FREEZE_EXCLUDE_NAME` y
  `FREEZE_APPEND_ONLY_CONSTRAINT`); `rules.py` (`FreezeLimits`, `FreezeOutcome`, `FreezeError` y
  `apply_freeze` con `NotImplementedError`); `events.py` (`MembershipFrozen`); `exceptions.py`
  (`FreezeRejected`, `OverlapsFutureMembership`); `schemas.py` (`FreezeIn` con `extra="forbid"`;
  `FreezeOut` gana `id` y `created_at`, blueprint B2); `lifecycle.py` (`freeze` con
  `NotImplementedError` y los pasos en el docstring); `router.py` (`POST
  /memberships/{membership_id}/freeze`, 200 `MembershipOut`, `StaffDep`,
  `enforce_user_limit(request, "memberships-write", principal.user_id)`, `responses_for(404, 409,
  422, 429)`); `service.py` re-exporta `freeze` y `MembershipFrozen`; `queries._load_freezes_for`
  sigue vacía (solo el docstring).
- Fixtures (B2.1): `tests/factories/memberships.py: make_freeze(session, membership, frozen_from=None,
  frozen_to=None, **cambios)` (calcula `days`, no mueve el fin) y
  `FACTORIES["memberships.membership_freezes"]`; `tests/conftest.py`: `TRIGGERS_DE_CONGELACIONES` y
  `LIMPIAR_MEMBERSHIPS` con un bloque previo para `membership_freezes` (`to_regclass`, `DISABLE
  TRIGGER USER`, `DELETE`, `ENABLE ALWAYS TRIGGER` por nombre); `tests/memberships/_apoyo.py`:
  `ruta_congelar`, `cuerpo_congelacion`, `CAMPOS_FREEZE`, `congelar`, `congelaciones_de`.
- Archivos de prueba nuevos: `tests/memberships/test_freeze_rules.py` (33),
  `test_freeze_service.py` (26), `test_freeze_router.py` (23),
  `tests/migrations/test_0009_membership_freezes.py` (28). Cambiados: `test_lock_order.py`
  (`freeze-sell` y preparación por combinación, `gather(return_exceptions=True)`),
  `test_triggers_siempre_activos.py` (cinco triggers), `test_0008_memberships.py` (en la cadena,
  funciones de head como superconjunto y `TRUNCATE ... CASCADE`), `test_audited_tables.py`,
  `test_error_codes_per_route.py` (E2), `test_handlers_no_new_locks.py`.
- Importadores de lo tocado: `memberships.models` lo importan `queries.py`, `sell.py`,
  `migrations/env.py`, `tests/factories/memberships.py` y las pruebas de membresías;
  `memberships.rules`, `queries.py`, `sell.py`, `test_no_cross_models.py` y la fábrica;
  `memberships.schemas`, `lifecycle.py`, `queries.py`, `router.py`, `sell.py`, `_apoyo.py` y
  `test_service_import_graph.py`; `memberships.lifecycle` solo `service.py` (y la prueba de servicio
  para el `monkeypatch`); `memberships.service` lo importan `router.py`, `tests/memberships/conftest.py`
  y las pruebas (ningún otro módulo de `app` todavía); `LIMPIAR_MEMBERSHIPS` y `TRIGGERS_DE_*`:
  `tests/conftest.py` (`LIMPIEZA_DE_SESION`, `limpiar_tras_dos_sesiones`) y
  `test_triggers_siempre_activos.py`; `FACTORIES`: `test_no_plaintext_at_rest.py` (solo tablas
  cifradas). En `web/` nada usa `FreezeOut` fuera de `core/api/types.ts` (P-API lo regenera).

#### Decisiones de prueba que el Verde debe respetar

1. **`TRUNCATE memberships.memberships` en `test_0008` pasa a `CASCADE`.** Comprobado en `db_test`
   dentro de una transacción revertida: con una tabla que referencia a `memberships.memberships`,
   el `TRUNCATE` simple lo rechaza PostgreSQL con `0A000` antes de correr el trigger; con `CASCADE`
   el trigger de la tabla corre primero y da `23000 memberships_no_delete`. Sin el cambio, la FK de
   `0009` rompía `test_delete_y_truncate_se_rechazan_con_memberships_no_delete`. Por la misma razón
   `test_ciclo_de_0008` exige que las dos funciones de `0008` estén entre las de head (no igualdad).
2. **Códigos, campos y estados de `apply_freeze` (D14).** `FreezeError(code, *, field=None,
   status=409, message="")`: `membership_not_freezable` 409; `validation_error` 422
   `field="frozen_to"`; `freeze_too_retroactive` y `freeze_outside_validity` 422 con
   `field="frozen_from"` (el blueprint no fija el campo: se elige el que el front puede marcar);
   `freeze_already_scheduled`, `freeze_limit_reached` y `freeze_days_exceeded` 409 sin campo;
   `freeze_days_exceeded` lleva en `message` los días que quedan (el número aparece en el texto).
   `FreezeRejected` se construye con `code`, `message`, `field` y `status` del `FreezeError`.
3. **Orden de D14 fijado por pruebas**: estado efectivo, fechas invertidas, retroactividad,
   vigencia (`frozen_from` en `[start_date, end_date]`), ya programada (`frozen_to >= hoy` en alguna
   previa), veces, días. Una ventana que termina hoy contiene hoy: la membresía ya es `frozen` y el
   rechazo es `membership_not_freezable`, no `freeze_already_scheduled`.
4. **Sin `OverflowError`**: los días se cuentan restando fechas y se comparan con el tope antes de
   sumar al fin (`frozen_to = 9999-12-31` da `freeze_days_exceeded`).
5. **`freeze` corre dentro de `begin_nested()`** (regla transversal 5, como `sell`): un handler de
   `MembershipFrozen` que falla no deja congelación, ni fin corrido, ni fila `update` de auditoría.
   Lee la membresía sin candado, toma `lock_member` y después `lock_membership` (la espía de
   sentencias exige `pg_advisory_xact_lock` antes del `FOR UPDATE` sobre
   `memberships.memberships`).
6. **`lifecycle` importa `find_overlap` al nivel del módulo y la llama por ese nombre**: la prueba de
   traducción de `ex_memberships_member_dates` la reemplaza con `monkeypatch` (como
   `sell._check_open_memberships` en B1). `OverlapsFutureMembership` lleva `existing_id` cuando sale
   de `find_overlap` y no lo lleva cuando sale de la `EXCLUDE`. La revisión previa compara
   `[start_date, new_end_date]` con las otras no canceladas del socio (sin la propia).
7. **`MembershipOut` de `freeze`**: `paid_cop = 0` hasta B4; `freezes` con todas las congelaciones de
   la membresía en orden de `frozen_from` y `FreezeOut` con `id`, `frozen_from`, `frozen_to`, `days`
   y `created_at`; `member_name` y `plan_name` como en `sell`.
8. **Estado guardado tras congelar**: `status = compute_status(...)` con el fin corrido y la lista
   nueva: `frozen` si la ventana contiene hoy, `active` o `expiring` si es futura o ya terminó. La
   fila `update` de auditoría de `memberships.memberships` trae exactamente `{"end_date", "status"}`
   en `after`; la `insert` de `membership_freezes` va sin `subject_member_id`.
9. **Concurrencia**: dos `freeze` de la misma membresía desde hoy: la segunda espera el candado del
   socio, ve la fila ya `frozen` y responde `membership_not_freezable`. En `freeze-sell` la venta sin
   `renew` choca con la vigente (`membership_conflict`) en cualquier orden.
10. **Migración `0009`** (lo que la prueba exige): tabla con las ocho columnas `NOT NULL`, CHECKs con
    nombre `ck_membership_freezes_dates_ordered` y `ck_membership_freezes_days_match`, EXCLUDE sin
    `WHERE`, índice no único `ix_membership_freezes_membership`, una sola FK (a
    `memberships.memberships(id)`), función `memberships.forbid_freeze_mutation()` (`plpgsql`,
    `prosecdef = false`, `proconfig = ['search_path=pg_catalog']`, el texto con
    `membership_freezes_append_only`) usada por los dos triggers; `UPDATE` (también sin cambios),
    `DELETE` y `TRUNCATE` dan `23000` con `constraint_name = membership_freezes_append_only`, también
    con `session_replication_role = replica`; head es `0009_membership_freezes` y el `downgrade`
    deja las dos funciones de `0008`.

#### Desviaciones del Rojo

- El plan (B2.2) pone `_load_freezes_for` real en los stubs; por instrucción del orquestador sigue
  vacía y la hace real el Verde (las pruebas de `sell` y `refs_for` no cambian por eso).
- `FreezeOut` gana `id` y `created_at` (blueprint B2): cambia el contrato publicado en B1, P-API lo
  regenera en B2.7 (ningún consumidor en `web/` fuera de `types.ts`).
- `test_0008_memberships.py` cambia más que "es head" → "en la cadena": `TRUNCATE ... CASCADE` y las
  funciones de head como superconjunto (decisión 1).
- No se tocan `docs/openapi.json`, `web/`, `DECISIONES.md`, `CLAUDE.md` ni `RUNBOOK.md`.

### S3-B2 · Verde (B2.4 a B2.8)

- Línea base del Verde: HEAD `b19adcd` con el Rojo sin confirmar; 109 fallan, 2.344 ok, 4 saltadas
  (igual que el Rojo); `apex-db-1` en `0008_memberships`, api `healthy`.
- B2.4 P-MIG: volcado `docs/scratch/sprint-03-antes-0009_membership_freezes.dump` con `$DC exec -T db
  pg_dump ... -n memberships -n payments` desde Bash (`chmod 600`, ignorado por git, `pg_restore -l`
  legible); `$DC stop api`; `api/migrations/versions/0009_membership_freezes.py` (tabla, CHECKs
  `dates_ordered` y `days_match`, `EXCLUDE ex_membership_freezes_dates` sin `WHERE`, FK a
  `memberships.memberships`, índice `ix_membership_freezes_membership`, función
  `memberships.forbid_freeze_mutation()` `plpgsql`/`SECURITY INVOKER`/`search_path = pg_catalog`
  con 23000 `membership_freezes_append_only`, triggers `membership_freezes_append_only` y
  `membership_freezes_forbid_truncate` en `ENABLE ALWAYS`; `downgrade` simétrico);
  `pytest tests/core/test_migrations.py tests/migrations/test_0009_membership_freezes.py
  tests/migrations/test_0008_memberships.py` 81 ok contra `db_test`; `alembic heads` =
  `0009_membership_freezes (head)`; `$DC start api` → `healthy` (la imagen no cambia); `alembic
  current` = `0009_membership_freezes (head)`; ciclo `downgrade -1`/`upgrade head` en `apex-db-1`
  sin errores en el log.
- B2.5 Verde: `rules.apply_freeze` (orden D14, `_check_freeze_days` resta fechas antes de sumar);
  `queries._freeze_rows_for`, `_load_freezes_for` real (por lotes, orden `frozen_from`),
  `freeze_out` y `membership_out`; `lifecycle.freeze` partida (`_lock_for_freeze`, `_apply`,
  `_check_dates_of_member`, `_store_freeze`, `_translate_flush_error`), en `begin_nested()`, con
  `lock_member` antes de `lock_membership` y `find_overlap` importada al nivel del módulo.
  `router.py`, `service.py`, `models.py`, `events.py`, `exceptions.py` y `schemas.py` del Rojo sin
  cambios. Ninguna prueba del Rojo cambió.
- Revisión de seguridad (antes del gate): 0 CRITICAL, 0 HIGH, 1 MEDIUM, 4 LOW. Aplicados M1 (socio
  inactivo o dado de baja → 422 `member_inactive`) y L4 (`freezes` en orden de `frozen_from`); L1,
  L2 (US-106) y L3 (S3-D49) anotados en DECISIONES "S3-B2". Prueba nueva
  `tests/memberships/test_freeze_revision.py` (4: M1 con socio inactivo y dado de baja, L4 y la
  traducción de `ex_membership_freezes_dates` a `freeze_already_scheduled`), roja sin los cambios
  (3 fallan; la de la `EXCLUDE` ya pasaba) y verde con ellos.
- Suite: 2.457 ok, 4 saltadas, 3 deseleccionadas, 0 fallos; cobertura de `app` 96 % (`lifecycle`
  96 %, `rules` 100 %, `queries` 96 %); `ruff format`, `ruff check` y `mypy src` (84 archivos)
  limpios.
- B2.6 Docs: RUNBOOK §6 (rollback de `0009`) y §10 (vaciado de `memberships` con la FK,
  congelaciones append-only con psql, congelar); DECISIONES "S3-B2".
- B2.7 P-API: `export-openapi` dos veces idéntica (la ruta `POST
  /api/v1/memberships/{membership_id}/freeze`, `FreezeIn` y `FreezeOut` con `id` y `created_at`:
  286 líneas en `docs/openapi.json`, 202 en `web/src/core/api/types.ts`); `npm run gen:api`,
  `types.contract.test.ts` 5 ok y `npx tsc --noEmit` limpio.
- Desviaciones: `refs_for` no usa `_load_freezes_for` (no calcula estado); `ex_membership_freezes_dates`
  se traduce a `freeze_already_scheduled` (el blueprint no la traducía); el 200 en vivo queda para
  la demo tras B4 (no hay vía legítima de activar la membresía de B1 sin pagos). La evidencia de
  B2.9 va al commit `docs(sprint-03): evidencia de S3-B2` (E8).

### Evidencia de S3-B2 (B2.9, después del sello; E8)

- Gates B2.8 seguidos, sin editar entre ellos, `PYTEST_ADDOPTS="-m 'not perf'"`, `ls` previo de cada
  archivo, todos verdes al primer intento: 1 `architecture` (con `test_migrations`, `test_0009`,
  `test_0008`, `test_triggers_siempre_activos` y `test_audited_tables`) 301 ok; 2 corrida conjunta
  `tests/memberships tests/migrations` 382 ok; 3 (sella) `memberships` 336 ok (con
  `test_freeze_revision`, nacida en la revisión). Una saltada en los gates 1 y 3
  (`test_no_sensitive_in_logs`, US-074). Checkpoint `5d412bd`.
- P-MIG pasos 6 y 7 en `apex-db-1` (hechos en B2.4 y comprobados a las 06:18 UTC): api `healthy`;
  `alembic current` = `0009_membership_freezes (head)`. Catálogo: triggers
  `membership_freezes_append_only` y `membership_freezes_forbid_truncate` en `A`; funciones
  `forbid_delete`, `forbid_freeze_mutation` y `guard_identity` con `prosecdef = f` y
  `proconfig = {search_path=pg_catalog}`; restricciones `ck_membership_freezes_dates_ordered`,
  `ck_membership_freezes_days_match`, `ex_membership_freezes_dates`,
  `fk_membership_freezes_membership_id_memberships` y `pk_membership_freezes`.
- Smoke por Nginx `:8180` con un access del admin firmado dentro del contenedor del api (el script
  temporal se borró del contenedor): congelar 10 días (25 oct a 3 nov) la membresía de B1
  (`0338472b-…`, `pending_payment`) → **409** `membership_not_freezable` en 0,03 s (evidencia de
  D14: una pendiente de pago no se congela); id inexistente → **404** `membership_not_found`; sin
  token → **401** `unauthorized`; `/api/v1/health` 200. La membresía sigue `pending_payment |
  2026-11-24`, sin filas `update` de auditoría. El 200 en vivo queda para la demo tras B4
  (DECISIONES "S3-B2"); lo prueban `test_freeze_router` y `test_freeze_service` sobre `db_test`.
- psql en `apex-db-1`, dentro de una transacción revertida con una congelación insertada para la
  prueba: `UPDATE memberships.membership_freezes SET days = 1` → `23000` `CONSTRAINT NAME:
  membership_freezes_append_only`; `DELETE` → lo mismo; con `SET LOCAL session_replication_role =
  replica` un `UPDATE` sin cambios → lo mismo; el vaciado de la tabla → lo mismo. Después: 0
  congelaciones, 0 filas de auditoría de `membership_freezes`, 0 sesiones `idle in transaction`,
  log del api sin `ERROR` en los últimos 10 minutos.

### S3-B3 · Rojo (B3.1 a B3.3 y la prueba de `0010`)

- Línea base: HEAD `fdce0dd`, árbol limpio; `pytest -m "not perf"` con `TEST_DATABASE_URL`: 2.457 ok,
  4 saltadas, 3 deseleccionadas (salida 0); `ruff check` y `mypy src` (84 archivos) limpios.
- Rojo: 2.702 recolectadas (3 deseleccionadas); **140 fallan**, 2.558 ok, 4 saltadas. `ruff format`,
  `ruff check` y `mypy src` (93 archivos) limpios. De las verdes de la línea base solo
  `test_docs_openapi_json_esta_al_dia` pasa a rojo (P-API, B3.7); la parametrización de
  `NO_HABILITADAS` pierde `payment_methods` (4 casos) y `RUTAS` gana dos rutas (4 casos), y
  `PENDING_AUDITED` pierde `payments.payments` (1 caso). `db_test` sin residuos:
  `alembic_version = 0009_membership_freezes`, sin `payments.payments`, 0 membresías, 0 socios,
  0 planes, 0 usuarios `@test.apex`, 0 sesiones `idle in transaction`, los cinco triggers de
  `memberships` en `A`. `apex-db-1` en `0009_membership_freezes` (nunca migró), api `healthy`.
  - Fallan por archivo: `tests/payments/test_rules.py` 55 (`NotImplementedError` de las reglas; los
    422 de `reference` porque `PaymentIn` normaliza con `rules.normalize_reference`);
    `tests/payments/test_register.py` 36 (`NotImplementedError` de `register`, sumas y
    `UndefinedTable`); `tests/migrations/test_0010_payments.py` 28 (no existe la revisión);
    `tests/settings/test_payment_methods_service.py` 8 y `test_payment_methods_rules.py` 4
    (`decorate_methods` y `payment_methods`); `tests/payments/test_payment_methods_router.py` 4 (500
    por `methods`); `tests/architecture/test_service_import_graph.py` 2
    (`test_cada_arista_permitida_existe` y `test_payments_depende_de_members_auth_y_settings_y_no_de_memberships`:
    `payments` aún no importa `members`, `auth` ni `settings`);
    `tests/architecture/test_payment_method_codes.py` 1 (no existe `0010_payments.py`);
    `tests/memberships/test_lock_order.py` 1 (`sell-register`); `tests/core/test_openapi_export.py` 1.
  - Verdes sobre los stubs (el stub ya es el contrato): constantes de reglas y del modelo, patrón de
    comprobante, `PaymentIn` (montos, medios, `confirm_*` estrictos, extra, zona de `paid_at`),
    `PaymentOut`, catálogo de errores, eventos; esquema `PaymentMethodsSettings` (etiquetas, pistas,
    repetidas, extra, faltantes) por `validate_section`; las dos rutas tipadas de settings (son
    `get_section`/`update_section` reales) y la lectura y guardado por service; `GET
    /payments/methods` 401/403 y su OpenAPI (objeto `PaymentMethodsOut`, sin `429`, con `500` y
    `503`); `test_every_route_has_role` y `test_list_routes_use_page_params` con la ruta nueva;
    `test_audit_module` (tupla final), `test_audited_tables`, `test_no_cross_models`,
    `test_settings_no_secrets`, `test_banned_imports`, `test_triggers_siempre_activos` (texto de
    `LIMPIAR_PAYMENTS` y estado), `test_0009` "en la cadena"; los 12 subprocesos de importación
    limpia de los pares nuevos de `payments`.
- Verde desechable (revertido; solo `db_test`, con `$DC stop api` antes de escribir la migración y
  `$DC start api` después de borrarla; `apex-db-1` siguió en `0009`): migración `0010` mínima,
  reglas, consultas, `register`, `methods`, `decorate_methods` y `payment_methods`. Suite completa:
  2.693 ok y 5 fallos, todos del desechable o esperados (`test_docs_openapi_json_esta_al_dia`,
  P-API; `test_ninguna_funcion_supera_50_lineas`, el `register` de una pieza; y tres de
  `test_service_import_graph` por los imports dentro de funciones del desechable). Encontró un
  defecto de prueba (`test_el_tope_del_coach_sale_de_la_politica_guardada` llamaba a
  `update_section` sin `actor_scope`: corregido) y un defecto del blueprint (decisión 3).
  Después: `alembic -x url=<db_test> downgrade 0009_membership_freezes`, archivo borrado, `rules`,
  `queries`, `service` de `payments` y `settings/service.py` restaurados desde copia.
- Stubs (B3.2): `modules/payments/` completo salvo la lógica: `models.py` (`Payment` con los cinco
  CHECKs y los tres índices, `PAYMENT_METHODS`, `MAX_AMOUNT_COP`, `REFERENCE_MAX_LENGTH`,
  `VOID_REASON_MAX_LENGTH`; `__audited__` con sujeto `member_id`), `exceptions.py` (catálogo con
  `PaidAtInvalid` como base de `PaidAtInFuture`), `events.py`, `schemas.py` (`PaymentIn`,
  `PaymentOut`, `PaymentMethodOut`, `PaymentMethodsOut`), `router.py` (solo `GET /payments/methods`,
  `StaffDep`, `no_store`, `responses_for()`); `rules.py` (constantes definitivas,
  `PaymentFingerprint`, funciones con `NotImplementedError`), `queries.py` (`sum_not_voided`,
  `sums_not_voided`, `count_not_voided`, `_recent_fingerprints` con `NotImplementedError`),
  `service.py` (`MembershipPayability`, `MembershipGate`, `set_membership_gate` y `membership_gate`
  reales; `register` y `methods` con `NotImplementedError`; `__all__`). Settings:
  `PAYMENT_METHOD_CODES`, `MethodLabel`, `PaymentMethodsSettings` (validador de etiquetas únicas
  con `loc` `(<code>, "label")`), `PaymentMethodInfo`, `PaymentMethodsSectionOut`,
  `PaymentMethodsPatchIn`, registro en `ENABLED_SECTIONS`, `SECTION_REGISTRY`, `SECTION_VIEWS` (por
  el `**SECTION_REGISTRY`) y `SECTION_DEFAULTS`; `decorate_methods` y `payment_methods` con
  `NotImplementedError`; rutas tipadas `GET`/`PATCH /settings/payment_methods` antes de la genérica.
  `main.MODULES` final con `payments`; `migrations/env.py` importa `payments.models`;
  `PRIVATE_HELPERS["payments"] = {rules, events, queries}`.
- Fixtures (B3.1): `tests/factories/payments.py: make_payment(session, membership, *, amount=None,
  method="cash", paid_at=None, voided=False, void_reason=None, reference=None, registered_by=None,
  **cambios)` y `FACTORIES["payments.payments"]`; `tests/conftest.py`: `TRIGGERS_DE_PAGOS` y
  `LIMPIAR_PAYMENTS` (en `LIMPIEZA_DE_SESION` y en `limpiar_tras_dos_sesiones`, antes de
  `LIMPIAR_MEMBERSHIPS`); `tests/payments/{__init__,_apoyo,conftest}.py` (`GateDoble`,
  `gate_registrado`, `registrar`, `leer_pago`, `pagos_de`, `leer_auditoria_de_pagos`,
  `CAMPOS_PAYMENT`, `CAMPOS_METODO`; fixture `gate_doble`; `bus_confirmado` importado de
  `tests/memberships/conftest.py`); `tests/settings/_apoyo.py` (`NO_HABILITADAS` con cuatro,
  `RUTAS` con diez, `PAYMENT_METHODS_OK` y `PAYMENT_METHODS_DEFAULTS`).
- Archivos de prueba nuevos: `tests/payments/test_rules.py` (101), `test_register.py` (36),
  `test_payment_methods_router.py` (7); `tests/settings/test_payment_methods_rules.py` (20),
  `test_payment_methods_service.py` (10), `test_payment_methods_router.py` (11);
  `tests/architecture/test_payment_method_codes.py` (6); `tests/migrations/test_0010_payments.py`
  (28). Cambiados: `test_service_import_graph.py` (tres aristas y la prueba de `payments`),
  `test_audit_module.py`, `test_audited_tables.py`, `test_no_cross_models.py` (privados y models de
  `payments`), `test_settings_no_secrets.py`, `test_every_route_has_role.py`,
  `test_list_routes_use_page_params.py`, `test_banned_imports.py`,
  `tests/migrations/test_triggers_siempre_activos.py`, `test_0009_membership_freezes.py` (en la
  cadena), `tests/memberships/test_lock_order.py` (`sell-register`),
  `tests/settings/test_settings_router.py` y `test_settings_rules.py`.
- Importadores de lo tocado: `app.main.MODULES` lo leen `cli.py`, `tests/conftest.py`,
  `test_audit_module.py`, `test_audited_tables.py` y `test_user_limits_catalog.py`;
  `settings.schemas` lo importan `settings/{service,router}.py`, `memberships/sell.py`
  (`MembershipsPolicy`) y las pruebas de settings y de arquitectura; `settings.service` lo importan
  `settings/router.py`, `auth/users.py`, `memberships/sell.py` y `lifecycle.py` (ninguno usa lo
  nuevo); `settings.router` solo `main.py`; `migrations/env.py` lo usa Alembic; `payments/*` es
  nuevo (lo importan solo sus propios archivos, `migrations/env.py`, `main.py` por `MODULES` y las
  pruebas); `tests/conftest.py` lo importan todas las pruebas (`LIMPIAR_PAYMENTS` y
  `TRIGGERS_DE_PAGOS` son nuevos); `PRIVATE_HELPERS` lo leen `find_forbidden_imports` y
  `test_no_cross_models.py`; `FACTORIES` solo `test_no_plaintext_at_rest.py` (solo tablas cifradas).

#### Decisiones de prueba que el Verde debe respetar

1. **Aristas de `payments` (D2).** `ALLOWED_EDGES` gana `payments → members`, `payments → auth` y
   `payments → settings` como pide el plan, y `test_cada_arista_permitida_existe` exige que las
   tres existan a nivel de módulo: el Verde de B3 tiene que importar `members.service` y
   `auth.service` con un uso real. B3 no tiene uno evidente (`search_ids`, `ensure_exists` y
   `names_for` los usan las listas de B8): si el Verde no encuentra un uso legítimo, el orquestador
   decide mover esas dos aristas a B8 (cambia `ALLOWED_EDGES` y
   `test_payments_depende_de_members_auth_y_settings_y_no_de_memberships`). Ninguna arista hacia
   `memberships`, ni perezosa, en B3 (la perezosa de la lista blanca llega con B8).
2. **`void_coherent` con `void_reason IS NOT NULL` explícito (hallado por el Verde desechable).** Con
   el texto del blueprint, `btrim(NULL) <> ''` es NULL, el CHECK no es falso y un pago
   `voided = true` sin motivo entra. La migración y el modelo (ya corregido en el stub) escriben
   `voided = true AND void_reason IS NOT NULL AND btrim(void_reason) <> '' AND ...`
   (`test_0010_payments.py::...[anulado-sin-motivo]`).
3. **Errores de `paid_at`.** `PaidAtInvalid` (422 `validation_error`, `field="paid_at"`) para sin
   zona y antes del piso; `PaidAtInFuture` hereda de él (mismo código); `PaidAtTooRetroactive` es
   422 `paid_at_too_retroactive`. Orden de `validate_paid_at`: zona, piso, futuro, retroactividad
   (solo si `role != "admin"`). Compara sin convertir de zona (año 1 con +05:00 da 422, nunca
   `OverflowError`). Límites inclusivos: justo 7 días atrás pasa, 7 días y 1 s no; +4 min 59 s pasa
   y +5 min 1 s no (la frontera exacta de +5 min no la fija ninguna prueba).
4. **Ventana de duplicado solo con piso.** `is_possible_duplicate` cuenta los pagos no anulados con
   `registered_at >= now - DUPLICATE_WINDOW` (120 s exactos cuentan) e iguales en
   `registered_by`, `amount_cop`, `method` y `reference` (dos nulas son iguales). Un
   `registered_at` posterior a `now` cuenta: `registered_at` es `created_at` de la fila (reloj de la
   base, `now()` de la transacción) y en las pruebas va por delante del `reloj` congelado; así
   "dos registros seguidos" es duplicado. `_recent_fingerprints(session, membership_id, since)`
   filtra `created_at >= since`. La frontera de 119 s y 121 s se prueba también por el service con
   la fábrica (`created_at = T0 - 119 s` / `T0 - 121 s`).
5. **Orden dentro de `register` (lo exigen las pruebas):** gate (`MembershipGateNotRegistered` si
   falta, antes de tocar nada); 404; 409 cancelada; `validate_paid_at` con
   `memberships_policy(session).max_retroactive_days`; saldo con `agreed_price_cop` del gate;
   conteo; duplicado (salvo `confirm_duplicate`); insertar; `flush`; `emit`. Todo en
   `begin_nested()` (un handler que lanza no deja pago ni auditoría). `member_id` sale del gate (la
   prueba fuerza un `member_id` distinto con `GateDoble.forzados`). El gate se llama una vez por
   registro.
6. **`sums_not_voided`:** todo id pedido aparece (0 si no tiene pagos o todos anulados); sin ids, cero
   sentencias; 450 ids son 3 sentencias sobre `payments.payments` (`chunked`, `ID_BATCH`).
7. **`PaymentIn.reference` delega en `rules.normalize_reference`** (recorta, vacía a `None`, más de
   64 es `ValueError` sin el valor) y después aplica `SafeText` y `REFERENCE_PATTERN`.
8. **Settings:** `hint` vacío se acepta y con texto aplica `check_visible_text`; etiquetas únicas
   con `casefold`, error en el segundo código que repite (`value.nequi.label`,
   `value.breb.label`). `decorate_methods` devuelve `tuple[PaymentMethodInfo, ...]` en el orden de
   `codes`, con default por código faltante e ignorando ajenos; `payment_methods(session)` valida
   lo guardado con `PaymentMethodsSettings` y, si no valida, avisa en `app.settings` con solo la
   clave y responde los defaults. `GET /payments/methods` arma `PaymentMethodsOut` desde eso.
9. **`LIMPIAR_PAYMENTS`:** `to_regclass` y, por trigger, `IF EXISTS (SELECT 1 FROM pg_trigger WHERE
   tgrelid = 'payments.payments'::regclass AND tgname = ...)` antes de cada `ENABLE ALWAYS`; corre
   antes que `LIMPIAR_MEMBERSHIPS` en las dos limpiezas. `test_triggers_siempre_activos` acepta los
   de `payments` "solo si existen" hasta B4.
10. **`GateDoble`** bloquea la fila real con `SELECT ... FOR UPDATE` (SQL crudo, en `tests/`, no
    cuenta para `test_guarded_calls`) y arma la respuesta desde ella; `sell-register` de
    `test_lock_order` lo registra con `gate_registrado` alrededor del `gather`.
11. `test_list_routes_use_page_params` clasifica como lista solo las respuestas `Page_...` y rechaza
    los arreglos: el objeto `{items}` de D25 cumple sin cambiar la regla (condición 3 del impacto);
    la prueba nueva fija que la ruta responde `PaymentMethodsOut` y no entra en `listas`.

#### Desviaciones del Rojo

- `CAMPOS_ROW` y `CAMPOS_DETAIL` (sección 2 del plan) no se crean en `tests/payments/_apoyo.py`: sus
  campos los fija el blueprint de B8 (`PaymentRow`, `PaymentDetail`) y hoy no tienen consumidor.
- `bus_confirmado` no se copia: `tests/payments/conftest.py` lo importa de
  `tests/memberships/conftest.py` (una sola definición).
- `test_payment_method_codes.py` exige el texto de `0010_payments.py` (falla si no existe), no "solo
  si existe": en el Verde de B3 el archivo existe siempre.
- El modelo `Payment` ya lleva el CHECK `void_coherent` corregido (decisión 2).
- No se tocan `docs/openapi.json`, `web/`, `DECISIONES.md`, `CLAUDE.md` ni `RUNBOOK.md`.

### S3-B3 · Verde (B3.4 a B3.8)

- Línea base del Verde: HEAD `fdce0dd` con el Rojo sin confirmar; 140 fallan, 2.558 ok, 4 saltadas
  (igual que el Rojo); `apex-db-1` en `0009_membership_freezes`, api `healthy`.
- B3.4 P-MIG: volcado `docs/scratch/sprint-03-antes-0010_payments.dump` con `$DC exec -T db pg_dump
  ... -n memberships -n payments` desde Bash (`chmod 600`, ignorado por git, `pg_restore -l`
  legible); `$DC stop api`; `api/migrations/versions/0010_payments.py` (tabla con `member_id NOT
  NULL`, CHECKs `amount_range`, `method`, `reference_length`, `void_reason_length` y
  `void_coherent` con `void_reason IS NOT NULL`, índices `ix_payments_paid_at (paid_at DESC)`,
  `ix_payments_membership_id` e `ix_payments_member_paid (member_id, paid_at DESC)`, sin FK ni
  triggers, `downgrade` índices y tabla, SQL literal); `pytest tests/core/test_migrations.py
  tests/migrations/test_0010_payments.py tests/architecture/test_payment_method_codes.py` 37 ok
  contra `db_test`; `alembic heads` = `0010_payments (head)`; `$DC start api` → `healthy`;
  `alembic current` = `0010_payments (head)`; ciclo `downgrade -1`/`upgrade head` en `apex-db-1`
  sin errores en el log.
- B3.5 Verde: `payments/rules.py` (`validate_paid_at` con orden zona, piso, futuro y
  retroactividad; `normalize_reference`; `check_balance`; `is_possible_duplicate` con piso;
  `check_payment_count`), `queries.py` (`sum_not_voided`, `sums_not_voided` con `chunked` y ceros,
  `count_not_voided`, `_recent_fingerprints`), `service.py` (`register` partido en `_payable`,
  `_check_under_lock` e `_insert_payment`; `methods`), `settings/service.py` (`decorate_methods`
  pura y `payment_methods` tolerante). `models`, `schemas`, `router`, `events`, `exceptions` del
  Rojo sin cambios.
- Prueba cambiada por decisión (S3-D80, no por error): `test_service_import_graph.py` deja en
  `ALLOWED_EDGES` solo `("payments", "settings")` (las de `members` y `auth` llegan en B8) y la
  prueba de `payments` pasa a `test_payments_depende_de_settings_y_no_de_memberships`. La suite
  pierde 4 casos parametrizados (los subprocesos de importación limpia de las dos aristas, en los
  dos sentidos): 2.698 recolectadas.
- Revisión de seguridad (antes del gate): 0 CRITICAL, 0 HIGH, 0 MEDIUM, 3 LOW y 1 INFO, todos
  aceptados sin cambio y anotados en DECISIONES "S3-B3" (L1 ventana por `created_at` de la
  transacción, L2 homógrafos en etiquetas, L3 500 del `GET` de settings con fila inválida como las
  demás secciones, INFO inmutabilidad en `0011`). Sin prueba nueva.
- Suite: 2.694 ok, 4 saltadas, 3 deseleccionadas, 0 fallos; cobertura de `app` 96 % (`payments`:
  `rules` 100 %, `queries` 100 %, `service` 99 %); `ruff format`, `ruff check` y `mypy src` (93
  archivos) limpios.
- B3.6 Docs: RUNBOOK §10 (tabla `payments.payments` y rollback de `0010`, reglas del servidor de
  registrar pago, medios de pago); DECISIONES "S3-B3" (S3-D80, desviaciones del Rojo, revisión).
- B3.7 P-API: `export-openapi` dos veces idéntica (sha256 `0089e616…`; `GET /payments/methods`,
  `PaymentMethodsOut`, rutas tipadas `GET`/`PATCH /settings/payment_methods`: 368 líneas en
  `docs/openapi.json`, 281 en `web/src/core/api/types.ts`); `npm run gen:api`,
  `types.contract.test.ts` 5 ok y `npx tsc --noEmit` limpio.
- Desviaciones: aristas de `payments` según S3-D80; el volcado queda con modo `rw-r--r--` en NTFS
  (Windows no conserva `chmod 600`, como en B1 y B2). La evidencia de B3.9 va al commit
  `docs(sprint-03): evidencia de S3-B3` (E8).

### Evidencia de S3-B3 (B3.9, después del sello; E8)

- Gates B3.8 seguidos, sin editar entre ellos, `PYTEST_ADDOPTS="-m 'not perf'"`, `ls` previo de cada
  archivo, todos verdes al primer intento: 1 `settings` 344 ok; 2 `architecture` (con
  `test_migrations`, `test_0010`, `test_0009`, `test_triggers_siempre_activos`,
  `test_audited_tables`, `test_audit_module` y `test_banned_imports`) 298 ok; 3 `memberships` (con
  `test_lock_order`, `sell-register`) 235 ok; 4 corrida conjunta `tests/memberships tests/payments
  tests/migrations` 557 ok; 5 (sella) `payments` 404 ok. Una saltada en los gates 1, 2, 3 y 5
  (`test_no_sensitive_in_logs`, US-074). Checkpoint `d5b37b9`.
- P-MIG pasos 6 y 7 en `apex-db-1` (hechos en B3.4 y comprobados después del sello): api
  `healthy`; `alembic current` = `0010_payments (head)`; ciclo `downgrade -1`/`upgrade head` sin
  errores; log del api sin `ERROR` en los últimos 15 minutos; 0 sesiones `idle in transaction`.
- Smoke por Nginx `:8180` con accesos firmados dentro del contenedor del api (el script temporal se
  borró del contenedor y los tokens del disco):
  - `GET /api/v1/payments/methods` con el coach `coach-b7-smoke@test.apex` → **200**
    `{"items":[cash "Efectivo", nequi "Nequi", breb "Bre-B"]}` en orden, `Cache-Control:
    no-store`.
  - `GET /api/v1/settings/payment_methods` con el admin → 200 con los defaults en `version` 0;
    `PATCH` con `version` 0 y `breb` = "Bre-B (Bancolombia)" → **200** `version` 1 (auditoría
    `insert` de `settings.settings_sections`); `GET /payments/methods` del coach lo refleja.
  - `PATCH /settings/payment_methods` con el coach → 403; `GET /payments/methods` sin token → 401.
  - `POST /api/v1/memberships/{id}/payments` → **404** `not_found` (E9: la ruta nace en B4).
  - `/health` y `/api/v1/health` → 200. `payments.payments` sigue vacía.
- Observación sin cambio: Nginx y el api envían cada uno su `Cache-Control: no-store` (cabecera
  repetida, mismo valor); ya pasaba en rutas anteriores (`/members`), no es de B3.

### S3-B4 · Rojo (B4.1 volcado, B4.2 stubs, B4.3 Rojo y la prueba de `0011`)

- Línea base: HEAD `d8fc1df`, árbol limpio; `pytest -m "not perf"` con `TEST_DATABASE_URL`: 2.694 ok,
  4 saltadas, 3 deseleccionadas; `ruff check` y `mypy src` (93 archivos) limpios.
- B4.1 volcado (P-MIG paso 1, S3-D58, L-8), solo desde Bash: `$DC exec -T db pg_dump -U apex -Fc -n
  payments -n memberships apex > docs/scratch/sprint-03-antes-0011_payments_immutability.dump`,
  `chmod 600` (NTFS lo deja `rw-r--r--`, como en B1 a B3), 16.562 bytes, `pg_restore -l` legible,
  ignorado por git. El RUNBOOK lo escribe el Verde.
- Rojo: 2.842 recolectadas (3 deseleccionadas); **140 fallan**, 2.695 ok, 4 saltadas. `ruff format`,
  `ruff check` y `mypy src` (93 archivos) limpios. `db_test` sin residuos: `alembic_version =
  0010_payments`, 0 pagos, 0 membresías, 0 socios, sin `payments.forbid_mutation`, los cinco
  triggers de `memberships` en `A`. `apex-db-1` en `0010_payments` (nunca migró), api `healthy`.
  - Verdes de la línea base que pasan a rojo (32, todas por B4): `tests/payments/test_register.py`
    27 (el handler real `on_payment_registered` ya está suscrito y su stub lanza
    `NotImplementedError` en cada registro); `test_lock_order[sell-register]` (usa el gate real,
    stub); `test_0010_payments::test_sin_fk_y_los_unicos_triggers_son_los_de_0011` y los dos de
    `test_triggers_siempre_activos` que exigen los triggers de pagos (cambiados en este Rojo, E1);
    `test_docs_openapi_json_esta_al_dia` (P-API, B4.7).
  - Nuevas en rojo (108): `tests/payments/test_immutability.py` 38 (sin `0011`); `test_can_void.py`
    3; `test_router_register.py` 10 (gate y handler stub: 500); `tests/memberships/
    test_activation_service.py` 17; `test_sell_with_payment_service.py` 16; `test_rules.py` 12
    (`prefix_field`, `reraise_with_prefix`); `test_payment_target.py` 3 (`membership_payability`);
    `test_sell_router.py` 3 (venta con primer pago por HTTP); `test_lock_order[sell_con_pago-register]`;
    `tests/migrations/test_0011_payments_immutability.py` 4; `test_handlers_no_new_locks.py` 1
    (`on_payment_registered` aún no llama a `lock_membership`).
  - Verdes sobre los stubs (el stub ya es el contrato): `test_gates_registered.py` (5: el registro al
    importarse, en proceso limpio por `main` y por `cli`, y `register` sin gate falla cerrado y
    restaura), `test_payments_immutability_code.py` (5), `test_guarded_calls` (L-5),
    `test_service_import_graph` (arista `memberships → payments`, importación limpia en los dos
    órdenes), `test_error_codes_per_route` y `test_user_limits_catalog` (E2),
    `test_every_route_has_role` (la ruta nueva con rol), los 401/403/422 de forma y el OpenAPI de
    `test_router_register.py`, los 422 `first_payment.*` de `test_sell_router.py` y la
    suscripción del handler.
- Verde desechable (revertido; solo `db_test`, `$DC stop api` antes de escribir la migración y `$DC
  start api` después de borrarla; `apex-db-1` siguió en `0010`): `0011` mínima (función con ramas
  `truncate`, `delete`, `already_voided`, `column`, `incomplete_void`), `can_void`, `prefix_field`,
  `reraise_with_prefix`, `membership_payability`, `_register_first_payment`,
  `on_payment_registered`, `snapshot` y `paid_cop` real en `sell` y `membership_out`. Suite: 2.824
  ok y 11 fallos; los 10 que eran defectos de prueba se corrigieron y `tests/memberships
  tests/payments tests/migrations tests/architecture` dio 930 ok, 1 saltada. Solo queda
  `test_docs_openapi_json_esta_al_dia` (P-API). Después: `alembic -x url=<db_test> downgrade
  0010_payments`, archivo borrado y `sell`, `lifecycle`, `queries`, `rules` de `memberships` y
  `rules` de `payments` restaurados desde copia. Defectos de prueba que encontró: `cancel_reason =
  'x'` viola `ck_memberships_cancel_reason_length`; la auditoría "del socio" incluía el `insert` de
  `members.members` (ahora se excluye); el orden de eventos capturados (el capturador de
  `PaymentRegistered` corre después del handler real, que emite `MembershipActivated` antes): se
  compara por tipo.
- Stubs (B4.2): `payments/rules.can_void(payment)`; `payments/service.IMMUTABLE_CONSTRAINT =
  "payments_immutable"` (en `__all__`); `payments/router.py` publica `POST
  /memberships/{membership_id}/payments` real (`StaffDep`, `enforce_user_limit(request,
  "payments-write", principal.user_id)`, `role=principal.role`, `confirm_*` del cuerpo, 201
  `PaymentOut`, `responses_for(404, 409, 422, 429)`, `no_store` del router);
  `memberships/rules.prefix_field`; `memberships/schemas.SellMembershipIn.first_payment: PaymentIn |
  None = None` (el validador de `renew` sigue hasta B6); `memberships/sell.py`: `sell(...,
  first_payment: PaymentIn | None, ..., role: str | None = None)` (la rama con pago sigue en
  `NotImplementedError`), `membership_payability`, `_register_first_payment` y
  `reraise_with_prefix`; `memberships/events.MembershipActivated(membership_id, member_id, status)`;
  `memberships/lifecycle.snapshot` y `on_payment_registered`; `memberships/service.py` exporta los
  tres y al final registra `payments_service.set_membership_gate(membership_payability)` y
  `events.subscribe(PaymentRegistered, on_payment_registered)`; `memberships/router.py` pasa
  `role=principal.role` a `sell`.
- Archivos de prueba nuevos: `tests/payments/test_can_void.py` (3), `test_immutability.py` (41),
  `test_router_register.py` (23); `tests/memberships/test_sell_with_payment_service.py` (17),
  `test_activation_service.py` (18); `tests/architecture/test_payments_immutability_code.py` (5),
  `test_gates_registered.py` (5); `tests/migrations/test_0011_payments_immutability.py` (4).
  Cambiados: `tests/memberships/test_rules.py` (+12), `test_payment_target.py` (+3),
  `test_sell_router.py` (3 casos de 422 `first_payment.*` en lugar de "primer pago hasta B4" y 3
  pruebas nuevas), `test_sell_service.py` (`renew` solo), `test_lock_order.py` (gate real,
  combinación `sell_con_pago-register`, error esperado `None`);
  `tests/architecture/test_error_codes_per_route.py` y `test_user_limits_catalog.py` (E2),
  `test_service_import_graph.py`, `test_guarded_calls.py` (L-5), `test_handlers_no_new_locks.py`,
  `test_every_route_has_role.py`; `tests/migrations/test_triggers_siempre_activos.py` (E1) y
  `test_0010_payments.py` (en la cadena; triggers de `0011`).
- Importadores de lo tocado: `payments/rules.py` lo importan `payments/{queries,schemas,service}.py`
  y las pruebas; `payments/service.py` lo importan `payments/router.py`, `memberships/{sell,
  lifecycle,service}.py` (nuevos) y las pruebas; `payments/router.py` solo `main.py` (por
  `MODULES`); `memberships/schemas.py` lo importan `lifecycle`, `queries`, `router`, `sell` y
  pruebas (ahora importa `payments.schemas`, permitido por la regla 2); `memberships/sell.py`
  `lifecycle`, `service` y pruebas; `memberships/rules.py` `lifecycle`, `queries`, `sell`,
  `tests/factories/memberships.py` y pruebas; `memberships/events.py` `lifecycle`, `sell` y
  `service`; `memberships/service.py` `router`, `tests/memberships/{conftest,_apoyo}.py` y pruebas;
  `memberships/router.py` solo `main.py`. `tests/conftest.py` sin cambios.

#### Decisiones de prueba que el Verde debe respetar

1. **Motivos del trigger:** `payments_immutable: <motivo>` en el mensaje, con `ERRCODE =
   'integrity_constraint_violation'` y `CONSTRAINT = 'payments_immutable'`; `DELETE` da `delete` y
   el vaciado da `truncate` (B4.4 nombra las ramas `delete`/`truncate`; el blueprint decía `delete`
   para las dos: manda el plan). Orden: vaciado, borrado, `already_voided` (cualquier `UPDATE`
   sobre un anulado, también sin cambios o de `true` a `false`), `column` (las 10 con `IS DISTINCT
   FROM`, aunque la sentencia anule a la vez), `incomplete_void` (todo `UPDATE` de un vigente que no
   sea la anulación completa, también el que solo toca `updated_at` o pone `voided = false`). La
   definición nombra `NEW.<columna>` de las 10 y no lleva `EXCEPTION WHEN OTHERS`.
2. **`reraise_with_prefix`** construye `type(error)(error.code, error.message,
   field=prefix_field(...), existing_id=..., status=...)`, copia `headers` (dict nuevo) y no toca el
   original.
3. **`sell` con pago:** `confirm_duplicate=False` siempre; el `role` del llamador va a `register`; la
   respuesta lleva el `status` tras el handler, `paid_cop = sum_not_voided` y `first_payment_id`. La
   auditoría del socio (sin su propio `insert` de `members.members`) queda `insert` de la
   membresía, `insert` del pago y, si cubre, `update` con `before = {"status": "pending_payment"}`.
4. **`on_payment_registered`** llama a `lock_membership(session, event.membership_id)` una vez y a
   ningún otro candado; solo actúa sobre `pending_payment`; `hoy = to_bogota_date(event.occurred_at)`.
   Una pendiente vencida por fecha queda `expired` y **se emite** `MembershipActivated` con
   `status = "expired"` (D11 acepta el caso; el evento lleva el estado resultante).
5. **`paid_cop` real en `membership_out`** (la salida de `freeze`): B2 lo dejó en 0 "hasta B4";
   `test_congelar_una_pagada_devuelve_paid_cop_con_lo_no_anulado` lo exige.
6. **`membership_payability`** usa `lock_membership` (relee con `populate_existing`) y devuelve el
   `agreed_price_cop` de la fila, no el del plan.
7. **`test_lock_order` con el gate real:** la combinación nueva usa un socio con una `active` vencida
   (1 de septiembre al 1 de octubre); la venta con pago y el pago a la vencida terminan bien las dos.
8. **`payments-write` es cubeta propia:** el pago 31 da 429 y el mismo coach todavía vende
   (`memberships-write`).

#### Desviaciones del Rojo

- `sell(..., role: str | None = None)`: con `None` y un primer pago decide el Verde (el desechable
  pasó `""`, que la regla trata como rol limitado: falla cerrado). Las pruebas siempre pasan el rol.
- `snapshot(row)` convive con el `_snapshot_of` privado de B2; el Verde puede unificarlos.
- Las pruebas de `membership_payability` van en `tests/memberships/test_payment_target.py` (junto a
  `get_payment_target`), no en un archivo nuevo.
- Nota L5 de B1 (suscriptores de `MembershipSold`): sin cambio; `test_handlers_no_new_locks` sigue
  mirando solo `lifecycle.py`. Hoy no hay suscriptores de `MembershipSold`.
- No se tocan `docs/openapi.json`, `web/`, `DECISIONES.md`, `CLAUDE.md` ni `RUNBOOK.md`.

### S3-B4 · Verde (B4.4 a B4.8)

- Línea base del Verde: HEAD `d8fc1df` con el Rojo sin confirmar; 140 fallan, 2.695 ok, 4 saltadas
  (igual que el Rojo); `apex-db-1` en `0010_payments`, api `healthy`; `ruff` y `mypy` limpios.
- B4.4 P-MIG (el volcado de B4.1 ya existía: 16.562 bytes): `$DC stop api`;
  `api/migrations/versions/0011_payments_immutability.py` (función `payments.forbid_mutation()`
  `plpgsql`, `SECURITY INVOKER`, `SET search_path = pg_catalog`, sin `EXCEPTION WHEN OTHERS`;
  ramas `truncate` y `delete` por `TG_OP` antes de leer `OLD`, `already_voided`, `column` con `IS
  DISTINCT FROM` sobre las 10, `incomplete_void`; triggers `payments_forbid_mutation` y
  `payments_forbid_truncate` con `ENABLE ALWAYS`; `downgrade` triggers y función; SQL literal);
  `pytest tests/core/test_migrations.py tests/migrations/test_0011_payments_immutability.py
  tests/payments/test_immutability.py tests/migrations/test_triggers_siempre_activos.py
  tests/migrations/test_0010_payments.py` 83 ok contra `db_test`; `alembic heads` =
  `0011_payments_immutability (head)`; `$DC start api` → `healthy`, el log muestra `Running upgrade
  0010_payments -> 0011_payments_immutability` y `alembic current` = `0011_payments_immutability
  (head)`. El ciclo en `apex-db-1` (paso 7) va con la evidencia (B4.9).
- B4.5 Verde: `memberships/rules.prefix_field`; `payments/rules.can_void`; `memberships/sell.py`
  (`membership_payability` con `lock_membership` y el precio de la fila, `get_payment_target`
  derivado de él, `sell` con la rama de pago dentro del mismo `begin_nested()`,
  `_register_first_payment` con `confirm_duplicate=False`, `confirm_overpayment` del cuerpo y
  `role` del llamador o `LIMITED_ROLE = ""` con `None` (S3-D81), `reraise_with_prefix`, `_sell_out`
  con `paid_cop` de `sum_not_voided` y `first_payment_id`); `memberships/lifecycle.py` (`snapshot`
  público que reemplaza a `_snapshot_of`, `on_payment_registered` con un solo
  `lock_membership(session, event.membership_id)`, `sum_not_voided`, `covers`, `compute_status`
  sobre base `active` con congelaciones y `to_bogota_date(event.occurred_at)`, `flush` y
  `emit(MembershipActivated)`); `memberships/queries.membership_out` con `paid_cop` real.
  Resultado: 2.834 ok, 4 saltadas, 1 fallo (`test_docs_openapi_json_esta_al_dia`, P-API).
- Revisión de seguridad (`security-reviewer`, antes del gate): 0 CRITICAL, 0 HIGH, 1 MEDIUM, 2 LOW, 1
  INFO. MEDIUM-1 corregido con prueba en rojo primero (S3-D82: la venta con `first_payment` gasta
  también `payments-write`; `test_sell_router.py::
  test_la_venta_con_primer_pago_tambien_cuenta_en_payments_write`). LOW-1 cubierto con prueba
  nueva (`test_rules.py::test_reraise_with_prefix_sirve_para_toda_excepcion_de_pagos`, 10 casos).
  LOW-2 (dueño de la tabla) e INFO (socio dado de baja) aceptados en DECISIONES "S3-B4".
- Suite: 2.846 ok, 4 saltadas, 3 deseleccionadas, 0 fallos; cobertura de `app` 96 %; `ruff format`,
  `ruff check` y `mypy src` (93 archivos) limpios. Ninguna prueba del Rojo cambió; las dos nuevas
  salen de la revisión.
- B4.6 Docs: RUNBOOK §10 (inmutabilidad de los pagos con los cinco motivos, cómo probar el trigger
  con psql, rollback de `0011` que no toca filas y restauración `pg_restore --clean -n payments -n
  memberships` en orden: `downgrade 0010_payments`, `stop api`, restaurar, `start api`; venta con
  primer pago, ruta de registrar pago, cubeta `payments-write` y activación por cobertura;
  correcciones de las notas "hasta S3-B4"); DECISIONES "S3-B4" (mensajes del trigger, S3-D81
  `role=None`, `snapshot` unificado, desviaciones del Rojo, S3-D82 y la revisión).
- B4.7 P-API: `export-openapi` dos veces idéntica (sha256 `1f018068…`; `first_payment` en
  `SellMembershipIn` y `POST /memberships/{membership_id}/payments`: +306 líneas en
  `docs/openapi.json`, +193 en `web/src/core/api/types.ts`); `npm run gen:api`,
  `types.contract.test.ts` 5 ok, `npx tsc --noEmit` limpio y `npx vitest run` 110 archivos, 1.763
  ok.
- Desviaciones: S3-D81 (`role=None` como rol limitado) y S3-D82 (cubeta `payments-write` también
  en la venta con pago); el volcado queda `rw-r--r--` en NTFS como en B1 a B3. La evidencia de B4.9
  va al commit `docs(sprint-03): evidencia de S3-B4` (E8).
