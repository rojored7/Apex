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

### Evidencia de S3-B4 (B4.9, después del sello; E8)

- Gates B4.8 seguidos, sin editar entre ellos, `PYTEST_ADDOPTS="-m 'not perf'"`, `ls` previo de cada
  archivo, todos verdes al primer intento: 1 `architecture` (con `test_migrations`, `test_0011`,
  `test_0010`, `test_triggers_siempre_activos`, `test_gates_registered` y
  `test_payments_immutability_code`) 288 ok; 2 `payments` (con `test_can_void`, `test_immutability`,
  `test_router_register` y `test_register`) 349 ok; 3 corrida conjunta `tests/memberships
  tests/payments tests/migrations` 695 ok; 4 (sella) `memberships` (con `test_rules`,
  `test_sell_with_payment_service`, `test_activation_service`, `test_sell_service`,
  `test_lock_order`, `test_0011` y, por la revisión, `test_sell_router`) 444 ok. Una saltada en los
  gates 1, 2 y 4 (`test_no_sensitive_in_logs`, US-074). Checkpoint `3d7702b`.
- P-MIG pasos 6 y 7 en `apex-db-1`: `alembic current` = `0011_payments_immutability (head)`; ciclo
  `downgrade -1` (a `0010_payments`) y `upgrade head` sin errores; después, `payments_forbid_mutation`
  y `payments_forbid_truncate` en `A`, `forbid_mutation` con `prosecdef = f` y
  `{search_path=pg_catalog}`; api `healthy`; log del api sin `ERROR` en 20 minutos; 0 sesiones
  `idle in transaction`.
- Demo 1 por Nginx `:8180` con un access del admin firmado dentro del contenedor del api (el archivo
  del token se borró del scratchpad): socio nuevo "Demo B4Uno" (documento único) y venta del plan
  "Mensual" de 120.000 con `first_payment` de 120.000 en `cash` → **201** `status = active`,
  `paid_cop = 120000`, `first_payment_id` lleno, del 2026-10-25 al 2026-11-24. psql: una fila en
  `memberships.memberships` (`active`, 120.000); una en `payments.payments` con `member_id` copiado
  del socio y `registered_by` del admin; `audit.audit_log` del socio (sin `members.members`): `insert`
  de la membresía (seq 869), `insert` del pago (870) y `update` de la membresía (871, `before =
  {"status": "pending_payment"}`, `after = {"status": "active"}`), los tres del admin y con el mismo
  `subject_member_id`.
- Demo 2: socio nuevo "Demo B4Dos"; venta con 60.000 → 201 `pending_payment`, `paid_cop = 60000`;
  `POST /memberships/{id}/payments` de 60.000 (`DEMO-2`) → **201** y la membresía queda `active`
  (auditoría `update` `pending_payment` → `active`); tercer pago de 1.000 sin `confirm_overpayment` →
  **409** `payment_exceeds_balance` (`field = amount_cop`); con `confirm_overpayment: true` → **201**;
  el mismo pago repetido en menos de 2 minutos → **409** `payment_possible_duplicate`. Todas con
  `Cache-Control: no-store`.
- psql en transacciones revertidas sobre el pago de la demo 1 (`\set VERBOSITY verbose`): `UPDATE
  payments.payments SET amount_cop = 1` → `ERROR 23000: payments_immutable: column`; `DELETE` →
  `payments_immutable: delete`; `SET LOCAL session_replication_role = replica; UPDATE ...` →
  `payments_immutable: column` (rechazado); vaciado de la tabla → `payments_immutable: truncate`;
  todas con `CONSTRAINT NAME: payments_immutable`. Después: el pago sigue en 120.000 y la tabla
  tiene 4 pagos (los de las demos).
- `/health` y `/api/v1/health` → 200.

### S3-B5 · Rojo (B5.1 stubs y B5.2 Rojo; sin migración)

- Línea base: HEAD `b09d89d`, árbol limpio; `pytest -m "not perf"` con `TEST_DATABASE_URL`: 2.846 ok,
  4 saltadas, 3 deseleccionadas; `ruff check` y `mypy src` (93 archivos) limpios. (Una primera
  corrida de la línea base se contaminó porque los stubs se escribieron mientras corría y
  `test_openapi_export` exporta en un subproceso; se repitió con los cambios en `git stash`.)
- Rojo: 2.942 recolectadas (3 deseleccionadas); **69 fallan**, 2.869 ok, 4 saltadas. `ruff format`,
  `ruff check` y `mypy src` (93 archivos) limpios. `db_test` sin residuos: `alembic_version =
  0011_payments_immutability`, 0 pagos, 0 membresías, 0 congelaciones, 0 socios, 0 planes, 0
  usuarios `@test.apex`, 0 sesiones `idle in transaction`, los siete triggers de `memberships` y
  `payments` en `A`. `apex-db-1` no se tocó (sin migración); api `healthy`, log sin `ERROR`.
  - Verdes de la línea base que pasan a rojo: solo `test_docs_openapi_json_esta_al_dia` (P-API,
    B5.4). Suscribir el stub de `on_payment_voided` no rompe nada previo: nadie anulaba por el
    service antes de B5 (la fábrica inserta pagos anulados sin eventos).
  - Nuevas en rojo (68): `tests/payments/test_void_rules.py` 20 (`NotImplementedError` de
    `normalize_void_reason` e `is_previous_month`); `test_void.py` 21 (todas); `test_router_void.py`
    5 (200, 404, 409, 429 y el 422 de 501 caracteres, que decide el service: 500 por el stub);
    `tests/memberships/test_revert_activation_service.py` 19; `test_lock_order[register-void]`;
    `tests/architecture/test_handlers_no_new_locks.py::test_on_payment_voided_solo_bloquea_la_fila_del_evento`;
    `test_payments_immutability_code.py::test_void_vive_en_service_y_asigna_exactamente_las_cuatro_de_anulacion`.
  - Verdes sobre los stubs (el stub ya es el contrato): `VOID_REASON_MAX`, `VoidPaymentIn` (recorte,
    ausente, vacío, espacios, NUL, U+200B, campo desconocido, no texto), catálogo de
    `PaymentAlreadyVoided` e `InvalidVoidReason`, el evento `MembershipActivationReverted`, la
    suscripción del handler, `test_router_void` 401, 403 (coach y `member`), 422 de forma
    (ausente, vacío, espacios, campo desconocido, `payment_id` no UUID) y su OpenAPI;
    `test_error_codes_per_route` y `test_user_limits_catalog` (E2), `test_every_route_has_role`,
    `test_reraise_with_prefix_sirve_para_toda_excepcion_de_pagos` con las dos clases nuevas, y
    `test_ningun_handler_pide_candados_nuevos` / `test_los_handlers_de_lifecycle_son_exactamente_los_del_slice`
    con la lista nueva.
- Verde desechable (revertido; sin migración, solo `db_test`): `normalize_void_reason` con
  `check_visible_text` y el tope, `is_previous_month` por `(año, mes)` de `to_bogota_date`, `void`
  en el orden de D13 con `begin_nested`, `should_revert`, `on_payment_voided`. Suite: 2.937 ok, 4
  saltadas y 1 fallo (`test_docs_openapi_json_esta_al_dia`, P-API). Encontró dos defectos de prueba,
  corregidos: (1) `test_void.py::test_anular_y_registrar_otro...` comparaba el orden de
  `pagos_de` (`created_at` es el `now()` de la transacción de la prueba, igual en las dos filas):
  ahora compara por id; (2) `test_router_void.py` exigía `no-store` en el 409: los errores salen por
  el handler global, que no conserva la cabecera de la dependencia del router (ya pasaba en B4;
  `test_router_register` tampoco lo exige en errores). Después, `rules` y `service` de `payments` y
  `rules` y `lifecycle` de `memberships` restaurados desde copia.
- Stubs (B5.1): `payments/rules.py` (`VOID_REASON_MAX = VOID_REASON_MAX_LENGTH` = 500,
  `normalize_void_reason` e `is_previous_month` con `NotImplementedError`); `payments/exceptions.py`
  (`PaymentAlreadyVoided` 409 `payment_already_voided`; `InvalidVoidReason` 422 `validation_error`
  con `field="reason"` por defecto y la firma de `DomainError`); `payments/schemas.py`
  (`VoidPaymentIn(reason: SafeText)`, `extra="forbid"`); `payments/service.py` (`void(session, *,
  payment_id, reason) -> PaymentOut` con `NotImplementedError`, en `__all__`, y el orden de D13 en
  el docstring); `payments/router.py` (`POST /payments/{payment_id}/void`, 200 `PaymentOut`,
  `AdminDep`, `enforce_user_limit(request, "admin-write", principal.user_id)`,
  `responses_for(404, 409, 422, 429)`, `no_store` del router); `memberships/rules.should_revert`;
  `memberships/events.MembershipActivationReverted(membership_id, member_id, previous_status)`;
  `memberships/lifecycle.on_payment_voided`; `memberships/service.py` exporta los dos y suscribe
  `PaymentVoided → on_payment_voided`.
- Archivos de prueba nuevos: `tests/payments/test_void_rules.py` (32), `test_void.py` (21),
  `test_router_void.py` (14); `tests/memberships/test_revert_activation_service.py` (20).
  Cambiados: `tests/payments/_apoyo.py` (`anular`, `updates_de`, `DE_ANULACION`),
  `tests/memberships/test_lock_order.py` (`Escenario.payment_id`, `_con_activa_y_un_pago`,
  `_anular_pago`, combinación `register-void`), `tests/architecture/test_error_codes_per_route.py`
  (E2: `CON_LIMITE` gana solo `("post", "/api/v1/payments/{payment_id}/void")`),
  `test_user_limits_catalog.py` (`CLAVES_SIN_RUTA_TODAVIA` pierde `admin-write`),
  `test_handlers_no_new_locks.py` (lista exacta con `on_payment_voided` y su prueba de candado),
  `test_payments_immutability_code.py` (`void` existe y asigna exactamente las cuatro).
- Importadores de lo tocado: `payments/rules.py` lo importan `payments/{queries,schemas,service}.py`
  y pruebas; `payments/exceptions.py` `payments/{rules,service}.py` y pruebas;
  `payments/schemas.py` `memberships/{schemas,sell}.py`, `payments/{router,service}.py`, pruebas y
  `tests/payments/_apoyo.py`; `payments/service.py` `memberships/{lifecycle,queries,sell,service}.py`,
  `payments/router.py` y pruebas; `payments/router.py` solo `main.py` (por `MODULES`);
  `memberships/rules.py` `memberships/{lifecycle,queries,sell}.py`, `tests/factories/memberships.py`
  y pruebas; `memberships/events.py` `memberships/{lifecycle,sell,service}.py`;
  `memberships/lifecycle.py` `memberships/service.py` y pruebas; `memberships/service.py`
  `memberships/router.py`, `tests/memberships/{conftest,_apoyo}.py` y pruebas;
  `tests/payments/_apoyo.py` lo importan las pruebas de `tests/payments` y tres de
  `tests/memberships`. Ningún archivo de `src` cambia de firma: todo lo nuevo es agregado.

#### Decisiones de prueba que el Verde debe respetar

1. **`normalize_void_reason`** aplica la regla de `SafeText` (NFC, recorte, sin `Cc`/`Cf`, algo
   visible) más el tope de 500 tras recortar; todo rechazo es `InvalidVoidReason` (422
   `validation_error`, `field="reason"`) sin el valor en el mensaje. `void` la llama siempre (un
   llamador interno con NUL no llega a PostgreSQL). El 501 por HTTP lo decide el service, con el
   mismo código que los 422 del esquema.
2. **`is_previous_month(paid_at, today)`** compara `(año, mes)` de la fecha civil de Bogotá de
   `paid_at` con los de `today`; un mes posterior no es "anterior".
3. **Orden de `void` (D13), fijado con una espía de sentencias:** primero un `SELECT` de
   `payments.payments` sin `FOR UPDATE`, después `FOR UPDATE` de `memberships.memberships` (por el
   gate, una llamada con el `membership_id` del pago: `GateDoble.llamadas`), después `FOR UPDATE`
   de `payments.payments` y al final el `UPDATE`. Sin gate, `MembershipGateNotRegistered` y nada
   escrito. Inexistente 404 `payment_not_found`.
4. **`rules.can_void` se llama por el módulo** (`rules.can_void(...)`, no importado por nombre): la
   prueba del trigger lo reemplaza con `monkeypatch` para forzar el rechazo `already_voided` en el
   `flush`, que debe salir como `PaymentAlreadyVoided` con el `IntegrityError` como `__cause__`
   (`violated_constraint == IMMUTABLE_CONSTRAINT`).
5. **Las cuatro columnas se asignan dentro de `void`** en `service.py` (no en una ayuda): la prueba
   AST exige que `void` asigne exactamente `voided`, `void_reason`, `voided_by` y `voided_at`.
   `voided_at` es `current_clock().now_utc()` (igual a `T0` en las pruebas) y `voided_by` el actor.
6. **Aviso de mes anterior:** `logger.warning("void of previous month", extra={"payment_id": ...,
   "membership_id": ...})` de un logger `app.*`; el registro no lleva más atributos propios que
   esos dos (ni motivo, ni monto, ni referencia). Uno de octubre en Bogotá no avisa.
7. **`on_payment_voided`** llama a `lock_membership(session, event.membership_id)` una vez y a
   ningún otro candado; usa el estado EFECTIVO con `hoy = to_bogota_date(event.occurred_at)` y las
   congelaciones; `MembershipActivationReverted.previous_status` es ese estado efectivo
   (`active`, `expiring` o `frozen`). Revertir solo cambia `status` (auditoría `update` con
   `before = {"status": <guardado>}` y `after = {"status": "pending_payment"}` del admin); `end_date`
   y `membership_freezes` intactos. `expired` efectivo (`active` guardada vencida), `cancelled` y
   `pending_payment` no cambian ni emiten.
8. **Atomicidad:** un handler de `PaymentVoided` o de `MembershipActivationReverted` que lanza deja
   el pago sin anular, la membresía como estaba y sin auditoría nueva (`begin_nested`).
9. **Auditoría del pago:** un solo `update` con `user_id` del admin, `subject_member_id` del socio y
   `before`/`after` exactamente con las cuatro columnas de anulación.
10. **Concurrencia:** dos `void` del mismo pago con `dos_sesiones`: uno devuelve `PaymentOut` y el
    otro `PaymentAlreadyVoided` (sin 55P03); `register` frente a `void` sobre la misma membresía
    terminan los dos bien (`test_lock_order[register-void]`).

#### Desviaciones del Rojo

- `InvalidVoidReason` usa el código `validation_error` (el plan solo fija 422 y `field="reason"`):
  así los cuatro 422 de `reason` del router dan el mismo código, venga del esquema o del service.
- `normalize_void_reason` también rechaza NUL y U+200B (el plan los pone como rechazos de
  `SafeText`): `VoidPaymentIn` los rechaza en el esquema y la regla del service los rechaza para
  llamadores internos (decisión 1).
- `test_void.py` agrega casos fuera de la lista del plan: motivo inválido por el service, sin gate,
  uso del gate, orden de sentencias y la traducción del trigger con `can_void` reemplazado (el
  plan pedía "un `UPDATE` por SQL crudo antes acaba en 409 por `IMMUTABLE_CONSTRAINT`": con
  `populate_existing` ese caso sale por `can_void`, así que se prueban los dos caminos por
  separado).
- `test_revert_activation_service.py` incluye la tabla de `should_revert` (regla pura) y el caso
  `pending_payment` sin cambio.
- El 409 por HTTP no exige `no-store` (decisión del Verde desechable, defecto 2).
- No se tocan `docs/openapi.json`, `web/`, `DECISIONES.md`, `CLAUDE.md` ni `RUNBOOK.md`.

### S3-B5 · Verde (B5.3 a B5.5; sin migración)

- Línea base del Verde: HEAD `b09d89d` con el Rojo sin confirmar; 69 fallan, 2.869 ok, 4 saltadas
  (igual que el Rojo); `ruff` y `mypy` limpios. `apex-db-1` no se toca (sin migración).
- B5.3 Verde: `payments/rules.py` (`normalize_void_reason` con `check_visible_text` y el tope de
  500 tras recortar, todo rechazo `InvalidVoidReason()` sin valor; `is_previous_month` por `(año,
  mes)` de `to_bogota_date(paid_at)`); `payments/service.py` (`void` en el orden de D13 con
  `begin_nested()`, las cuatro columnas asignadas en `void`; ayudas `_lock_for_void`,
  `_flush_void` con `IMMUTABLE_CONSTRAINT` → `PaymentAlreadyVoided` `from` el error y
  `_warn_if_previous_month` con el logger `app.payments`, `PREVIOUS_MONTH_WARNING`);
  `memberships/rules.should_revert` (efectivo en `_VIGENTES` y no `covers`);
  `memberships/lifecycle.on_payment_voided` (un `lock_membership`, estado efectivo con
  congelaciones y `to_bogota_date(event.occurred_at)`, solo `status`, `flush`,
  `emit(MembershipActivationReverted)`). Resultado: 2.937 ok, 4 saltadas, 1 fallo
  (`test_docs_openapi_json_esta_al_dia`, P-API), igual que el Verde desechable del QA.
- Revisión de seguridad (`security-reviewer` sobre `git diff b09d89d -- api/src`, antes del gate
  que sella): 0 CRITICAL, 0 HIGH, 0 MEDIUM, 3 LOW. LOW-2 corregido con prueba en rojo primero
  (S3-D83: `VoidPaymentIn.reason` con `max_length = VOID_REASON_INPUT_MAX = 2000` antes de
  `check_visible_text`; `test_void_rules.py::test_el_esquema_tiene_un_tope_holgado_de_entrada_antes_de_la_regla_de_500`
  en rojo por `ImportError`, y `test_router_void.py::test_un_motivo_enorme_se_corta_en_el_esquema_con_422_en_reason`,
  que ya pasaba por el service y fija el comportamiento). LOW-1 (motivo en claro en la auditoría) y
  LOW-3 (`expired` efectivo no cambia el guardado) aceptados en DECISIONES "S3-B5".
- Suite: 2.940 ok, 4 saltadas, 3 deseleccionadas, 0 fallos; cobertura de `app` 96 %; `ruff format
  --check` (365 archivos), `ruff check` y `mypy src` (93 archivos) limpios. Ninguna prueba del Rojo
  cambió; las dos nuevas salen de la revisión.
- Docs: RUNBOOK §10 "Anular un pago y revertir la activación (S3-B5)" (solo admin, `admin-write`,
  motivo, 409 por `can_void` y por el trigger `already_voided`, aviso de mes anterior, reversión que
  conserva fin y congelaciones, atomicidad, orden de candados, comprobación por psql); DECISIONES
  "S3-B5" (orden de `void`, aviso, `on_payment_voided`, desviaciones del Rojo, S3-D83 y la revisión).
- B5.4 P-API: `export-openapi` dos veces idéntica (sha256 `7c1e29f4…`; `POST
  /payments/{payment_id}/void` y `VoidPaymentIn` con `maxLength: 2000`: +139 líneas en
  `docs/openapi.json`, +123 en `web/src/core/api/types.ts`); `npm run gen:api`,
  `types.contract.test.ts` 5 ok, `npx tsc --noEmit` limpio y `npx vitest run` 110 archivos, 1.763 ok.
- B5.5 gates, seguidos y sin editar entre ellos, `PYTEST_ADDOPTS="-m 'not perf'"`, `ls` previo:
  (1) `memberships` con `test_revert_activation_service` y `test_lock_order`; (2) el que sella,
  `payments` con `test_void_rules`, `test_void`, `test_router_void` y `test_immutability`. Una
  primera pasada verde de los dos (273 y 358 ok) se repitió después de escribir este bloque, para que
  el sello cubra el árbol con la documentación.

### Evidencia de S3-B5 (B5.6, después del sello; E8)

- Gates B5.5 al primer intento (repetidos una vez tras escribir el bloque del Verde, antes del
  checkpoint): 1 `memberships` (con `test_revert_activation_service`, `test_lock_order` y
  `tests/architecture`) 273 ok; 2 (sella) `payments` (con `test_void_rules`, `test_void`,
  `test_router_void`, `test_immutability` y `tests/architecture`) 358 ok. Una saltada en los dos
  (`test_no_sensitive_in_logs`, US-074). Checkpoint `47c5692`.
- api `healthy`, recargado por el bind (`WatchFiles detected changes ... Reloading`, `Application
  startup complete`; el contenedor ve `_lock_for_void` y `VOID_REASON_INPUT_MAX`); log del api sin
  `ERROR` en los 10 minutos de la demo; 0 sesiones `idle in transaction`. Sin migración:
  `apex-db-1` sigue en `0011_payments_immutability`.
- Demo 3 por Nginx `:8180` con access del admin y de un coach firmados dentro del contenedor del api
  (solo en variables de la shell; ningún archivo con token). Socio "Demo B4Dos" de la demo 2 de B4,
  membresía `b21e25b5…` (120.000, `active`, pagos 60.000 + 60.000 `DEMO-2` + 1.000 `DEMO-3`):
  - coach → `POST /api/v1/payments/34c5effc…/void` **403** `forbidden`, sin cambios;
  - admin con `{"reason": "Monto mal digitado"}` sobre el pago `DEMO-2` (el de 60.000 que completó
    la cobertura) → **200** con `voided = true`, `void_reason`, `voided_by` = admin, `voided_at`
    lleno; monto, medio, comprobante y `paid_at` intactos; `Cache-Control: no-store`;
  - psql: la membresía vuelve a `pending_payment` con `end_date` 2026-11-24 intacto; lo pagado no
    anulado es 61.000; `audit.audit_log`: `update` del pago (seq 877, `before` con las cuatro
    columnas en vacío/falso, `after` con la anulación) y `update` de la membresía (seq 878,
    `before = {"status": "active"}`, `after = {"status": "pending_payment"}`), los dos del admin y
    con el socio como sujeto (el `update` de B4, seq 875, era la activación);
  - admin otra vez → **409** `payment_already_voided`, sin cambios;
  - psql en transacción revertida (`\set VERBOSITY verbose`): `UPDATE payments.payments SET
    amount_cop = 1 WHERE id = <anulado>` → `ERROR 23000: payments_immutable: already_voided`,
    `CONSTRAINT NAME: payments_immutable`; después el pago sigue en 60.000 y anulado.
- `/health` y `/api/v1/health` → 200.

### S3-B6 · Rojo (B6.1 stubs y B6.2 Rojo; sin migración)

- Línea base: HEAD `f2aab11`, árbol limpio; `pytest -m "not perf"` con `TEST_DATABASE_URL`: 2.940 ok,
  4 saltadas, 3 deseleccionadas; `ruff check` y `mypy src` (93 archivos) limpios. Corrida completa
  antes de tocar `src` (lección de B5: `test_openapi_export` exporta en un subproceso).
- Rojo: 3.060 recolectadas (3 deseleccionadas); **93 fallan**, 2.960 ok, 4 saltadas. `ruff format`,
  `ruff check` y `mypy src` (93 archivos) limpios. `db_test` sin residuos: `alembic_version =
  0011_payments_immutability`, 0 pagos, 0 membresías, 0 congelaciones, 0 socios, 0 planes, 0
  usuarios `@test.apex`, 0 sesiones `idle in transaction`, los siete triggers de `memberships` y
  `payments` en `A`. `apex-db-1` no se tocó (sin migración).
  - Verdes de la línea base que pasan a rojo: solo `test_docs_openapi_json_esta_al_dia` (P-API,
    B6.4). Salen de la línea base 3 pruebas retiradas (abajo): 2.940 − 3 − 1 = 2.936 siguen
    verdes.
  - Nuevas en rojo (92): `tests/memberships/test_renew_service.py` 37 (`NotImplementedError` de
    `plan_renewal`, de la rama `renew=True` de `sell` y de `renewal_preview`);
    `test_renew_router.py` 11 (201, 409, 429, vista previa 200/404/409/422 `plan_inactive` y
    "sin límite": 500 por el stub); `test_cancel_service.py` 37 (`normalize_cancel_reason` y
    `cancel`); `test_cancel_router.py` 6 (200, 404, 409, 429 y los 422 de 4 y de 501
    caracteres, que decide el service); `test_lock_order[sell-cancel]`.
  - Nuevas verdes sobre los stubs (24; el stub ya es el contrato): `test_renew_router.py` 7
    (`renew: false` explícito, 403 `member`, 401, 422 de `plan_id` ausente y no UUID, 403/401 de la
    vista previa, OpenAPI de la vista previa); `test_cancel_router.py` 10 (403 coach y `member`,
    401, 422 de forma: ausente, vacío, NUL y 100.000 caracteres, campo desconocido, `membership_id`
    no UUID, OpenAPI con `maxLength` 2000); `test_cancel_service.py` 2 (topes 5 y 500, esquema
    `CancelMembershipIn`); `test_lock_order[freeze-register]` 1; `test_events_without_pii.py` 4.
    Cambiadas y verdes: `test_error_codes_per_route` y `test_user_limits_catalog` (E2).
- Verde desechable (revertido; sin migración, solo `db_test`): `plan_renewal` y
  `normalize_cancel_reason`, la rama `renew` de `sell` (contexto con candados, `classify_open`
  sobre el estado efectivo, `FutureMembershipExists`, `plan_renewal`, `renewal=renew`),
  `renewal_preview` sin candados (`plans.get` sin `for_share`) y `cancel` (normaliza, un
  `lock_membership`, 404, 409, las cuatro columnas, `flush`, `emit`). `tests/memberships
  tests/payments tests/migrations tests/architecture`: 1.148 ok, 1 saltada; suite completa: 3.052
  ok, 4 saltadas, 1 fallo (`test_docs_openapi_json_esta_al_dia`, P-API). Sin defectos de prueba.
  Después, `rules`, `sell` y `lifecycle` restaurados desde copia (`ruff format` sin cambios).
- Stubs (B6.1): `memberships/exceptions.py` (`FutureMembershipExists` 409
  `future_membership_exists`; `MembershipAlreadyCancelled` 409 `membership_already_cancelled`;
  `CancelReasonInvalid` 422 `validation_error` con `field="reason"` por defecto y la firma de
  `DomainError`); `memberships/events.py` (`MembershipCancelled(membership_id, member_id,
  reason_len)`); `memberships/rules.py` (`CANCEL_REASON_MIN = 5`, `CANCEL_REASON_MAX = 500`,
  `RenewalPlan(start_date, end_date, agreed_price_cop)` definitivo, `plan_renewal(current, plan,
  price_cop, today)` y `normalize_cancel_reason(reason)` con `NotImplementedError`);
  `memberships/schemas.py` (`SellMembershipIn` **sin** el validador provisional de `renew` de B1
  M1; `CANCEL_REASON_INPUT_MAX = 4 * CANCEL_REASON_MAX = 2000`; `CancelMembershipIn(reason)` con
  `StringConstraints(max_length=2000)` y `check_visible_text`, `extra="forbid"`;
  `RenewalPreviewOut(start_date, end_date, agreed_price_cop, current_end_date: date | None)`);
  `memberships/sell.py` (la rama `renew=True` sigue en `NotImplementedError`, ahora alcanzable por
  HTTP: 500 hasta el Verde; `renewal_preview(session, *, member_id, plan_id)` stub; docstring con
  el diseño); `memberships/lifecycle.py` (`cancel(session, *, membership_id, reason)` stub y
  docstring); `memberships/service.py` re-exporta `MembershipCancelled`, `cancel` y
  `renewal_preview`; `memberships/router.py`: `GET /members/{member_id}/memberships/renewal-preview`
  (`plan_id` de query obligatorio, `StaffDep`, `responses_for(404, 409, 422)`, sin límite, `no_store`
  del router) y `POST /memberships/{membership_id}/cancel` (200 `MembershipOut`, `AdminDep`,
  `enforce_user_limit(request, "admin-write", principal.user_id)`, `responses_for(404, 409, 422,
  429)`).
- Archivos de prueba nuevos: `tests/memberships/test_renew_service.py` (37),
  `test_renew_router.py` (18), `test_cancel_service.py` (39), `test_cancel_router.py` (16);
  `tests/architecture/test_events_without_pii.py` (4). Cambiados: `tests/memberships/_apoyo.py`
  (`ruta_cancelar`, `cuerpo_cancelacion`, `cancelar`), `test_lock_order.py` (`_anular_membresia`,
  `sell-cancel` y `freeze-register`), `test_sell_service.py` (sale
  `test_renovar_sigue_sin_implementar_hasta_b6` y el docstring apunta a `test_renew_service.py`),
  `tests/architecture/test_error_codes_per_route.py` (E2: `CON_LIMITE` gana solo `("post",
  "/api/v1/memberships/{membership_id}/cancel")`). Retirado: `tests/memberships/
  test_sell_router_renew.py` (S3-B1 M1; sus dos casos quedan invertidos en `test_renew_router.py`:
  `test_renew_true_ya_no_es_un_422_de_forma` y `test_renew_false_explicito_sigue_vendiendo`). Sin
  cambio: `test_user_limits_catalog.py` (`admin-write` ya tenía ruta desde B5) y
  `test_handlers_no_new_locks.py` (la lista exacta sigue con los dos handlers: `cancel` no es
  `on_*`).
- Importadores de lo tocado: `memberships/exceptions.py` lo importan `memberships/{lifecycle,rules,
  sell}.py` y pruebas; `memberships/events.py` `memberships/{lifecycle,sell,service}.py`;
  `memberships/rules.py` `memberships/{lifecycle,queries,sell,schemas}.py` (`schemas` es nuevo:
  lee `CANCEL_REASON_MAX`; `rules` no importa `schemas`, sin ciclo), `tests/factories/
  memberships.py` y pruebas; `memberships/schemas.py` `memberships/{lifecycle,queries,router,
  sell}.py`, `tests/memberships/_apoyo.py`, `test_service_import_graph.py`,
  `test_find_forbidden_imports.py` y pruebas; `memberships/sell.py` `memberships/{lifecycle,
  service}.py` y pruebas; `memberships/lifecycle.py` `memberships/service.py`,
  `test_handlers_no_new_locks.py` y pruebas; `memberships/service.py` `memberships/router.py`,
  `tests/memberships/{conftest,_apoyo}.py` y pruebas; `memberships/router.py` solo `main.py` (por
  `MODULES`). Ningún archivo de `src` cambia de firma: todo es agregado salvo el validador
  retirado de `SellMembershipIn` (el contrato publicado de `renew` sigue siendo booleano).

#### Decisiones de prueba que el Verde debe respetar

1. **Renovar (Q1, D8).** Con `renew=True` el `start_date` recibido se ignora (también uno
   retroactivo de 30 días: no hay `start_date_too_retroactive`) y no corre `validate_start_date`
   (una renovación que empieza el 2027-11-26 pasa). Bajo el candado del socio y con el estado
   EFECTIVO de las no canceladas: una futura de D8 (`pending_payment` de cualquier fecha, incluida
   una de hoy sin vigente, o `active`/`expiring` con inicio posterior a hoy) da
   `FutureMembershipExists` con su `existing_id`; si no, `plan_renewal(classify_open(...).current,
   términos del plan, plan.price_cop, hoy)`. La vigente congelada renueva desde su fin ya
   extendido. Las canceladas no cuentan. `MembershipSold(renewal=True)` una vez. La vigente no
   cambia ni gana auditoría; la renovación deja una sola fila `insert` con el socio como sujeto.
2. **Primer pago de la renovación:** el mismo camino de B4: con pago completo la futura queda
   `active` (`start_date > hoy`); un monto mayor al precio sin `confirm_overpayment` da 409
   `payment_exceeds_balance` con `field="first_payment.amount_cop"` y no deja ni membresía ni pago.
3. **Carrera:** dos renovaciones a la vez (`dos_sesiones`): una gana y la otra recibe
   `FutureMembershipExists` con el id de la ganadora (la ve como futura tras el candado del socio).
4. **`renewal_preview`:** mismas validaciones y errores que la renovación (`MemberNotFound`,
   `MemberInactive`, `PlanInvalid`, `PlanInactive`, `FutureMembershipExists` con `existing_id`) y
   el mismo resultado que crea después `sell(..., renew=True)`; `current_end_date` es el fin de la
   vigente o `None`. Sin escribir y **sin candados**: la espía exige que ninguna sentencia tenga
   `FOR UPDATE`, `FOR SHARE` (el plan se lee con `plans.get` sin `for_share`) ni `pg_advisory`, y
   ningún `INSERT`/`UPDATE`/`DELETE`.
5. **Rutas.** Renovar usa `memberships-write` (la 31 da 429 aunque las 30 primeras sean 404: el
   límite va antes del service). La vista previa es `GET` con `plan_id` de query obligatorio (422
   `validation_error` con `field="plan_id"` si falta o no es UUID), sin 429 en el OpenAPI y sin
   consumir cupo: 40 seguidas del mismo coach dan 200 y ese coach sigue vendiendo.
6. **`normalize_cancel_reason`:** NFC y recorte con `check_visible_text`, luego largo de 5 a 500;
   todo rechazo es `CancelReasonInvalid()` (422 `validation_error`, `field="reason"`) sin el valor
   en el mensaje. `CANCEL_REASON_MIN`/`CANCEL_REASON_MAX` en `rules.py` y el esquema con tope
   holgado de 2000 (S3-D83): por HTTP, 4 y 501 caracteres los decide el service; vacío, NUL y
   100.000 el esquema; todos con el mismo código y campo. `cancel` lo aplica también para
   llamadores internos (un NUL nunca llega a PostgreSQL).
7. **`cancel`:** un único `FOR UPDATE` (sobre `memberships.memberships`, por `lock_membership`)
   antes del `UPDATE`, y nunca el candado del socio (ninguna sentencia con `hashtextextended`; el
   asesor de la cadena de auditoría sí aparece y no cuenta). 404 `membership_not_found`; 409
   `membership_already_cancelled` sin cambios (una sola auditoría `update`). Cambian exactamente
   `status`, `cancel_reason` (recortado), `cancelled_by` (el actor) y `cancelled_at`
   (`current_clock().now_utc()`, igual a `T0`); fechas, pagos (filas y auditoría de `payments`) y
   congelaciones intactos. Auditoría: un `update` del admin con el socio como sujeto y `before`/
   `after` con exactamente esas cuatro claves. La salida es `MembershipOut` con sus congelaciones.
   Un handler de `MembershipCancelled` que lanza deja todo como estaba (`begin_nested`).
8. **Después de anular:** `sell` con las mismas fechas da `pending_payment`; `register` da 409
   `membership_cancelled` por el gate real y no crea pago; anular un pago suyo da 200 y no la
   reactiva (sin `MembershipActivationReverted`); `UPDATE` crudo de `status`, `cancel_reason` o
   `cancelled_at` da 23000 `memberships_identity`.
9. **`MembershipCancelled`** tiene exactamente `occurred_at`, `membership_id`, `member_id` y
   `reason_len` (`int`, el largo del motivo normalizado: 16 para "Cambio de ciudad"); su `repr` no
   contiene el texto.
10. **Orden de candados:** `sell-cancel` (socio con una `active` vencida del 1 de septiembre al 1
    de octubre; se anula mientras se vende otra desde hoy) termina sin error de dominio, sin 55P03
    ni 40P01, en cualquier orden.

#### Desviaciones del Rojo

- `test_events_without_pii.py` nace aquí (B5 no lo creó; S3-D70 lo ponía en B10 y el plan de B6 lo
  adelanta). Los eventos de `auth` (`LoginAttempted`, `SessionsRevoked`, `UserLocked`) tienen un
  campo `reason` que es un `Literal` cerrado (códigos, no texto): la regla acepta un nombre
  prohibido solo si su tipo es `Literal` o `Literal | None`. Sin esa excepción la prueba fallaría
  por `auth`, no por B6. La lista prohibida suma `note`, `notes`, `birth_date`,
  `emergency_contact`, `address`, `cancel_reason` y `void_reason` a la de S3-D70.
- `test_lock_order` suma `freeze-register` (S3-D43, asignada a B6 en el docstring de la prueba y
  ausente hasta hoy); pasa sobre el código actual.
- Las pruebas puras de `plan_renewal` y `normalize_cancel_reason` viven en `test_renew_service.py`
  y `test_cancel_service.py` (en la línea de gate de B6.5), no en `test_rules.py` (como
  `should_revert` en B5).
- La vista previa tampoco toma `FOR SHARE` del plan (lectura estricta de "no toma candado"; el
  blueprint solo nombraba el del socio).
- `test_sell_router_renew.py` se retira (S3-B1 M1) y `test_renovar_sigue_sin_implementar_hasta_b6`
  sale de `test_sell_service.py`; sus casos quedan cubiertos al revés en `test_renew_router.py` y
  `test_renew_service.py`.
- No se tocan `docs/openapi.json`, `web/`, `DECISIONES.md`, `CLAUDE.md` ni `RUNBOOK.md`.

### S3-B6 · Verde (B6.3 a B6.5; sin migración)

- B6.3: `rules.plan_renewal` y `normalize_cancel_reason`; `sell.py` con `_sale_context(lock=...)`,
  `_open_memberships`, `_renewal_for` (futura → `FutureMembershipExists`, `plan_renewal`, solape),
  rama `renew` y `renewal_preview` sin candados; `lifecycle.cancel`. `ruff format`, `ruff check` y
  `mypy src` (93 archivos) limpios. `tests/memberships tests/payments tests/architecture
  tests/migrations`: 1.148 ok, 1 saltada (igual que el Verde desechable del QA).
- Revisión de seguridad: 0 CRITICAL/HIGH/MEDIUM, 3 LOW (DECISIONES "S3-B6"); LOW-2 fijado con
  `test_cancel_service.py::test_sin_actor_falla_cerrado_y_no_cambia_nada` (pasa).
- B6.4 P-API: `export-openapi` dos veces idéntica (sha256 `43421887…`, +291 líneas en
  `docs/openapi.json`, +247 en `web/src/core/api/types.ts`); `types.contract.test.ts` 5 ok y
  `tsc --noEmit` limpio. **F3 puede arrancar con este contrato.**
- Docs: RUNBOOK §10 "Renovar una membresía" y "Anular una membresía"; DECISIONES "S3-B6".
- Suite completa: una primera corrida con `--cov` la detuvo el sistema por falta de memoria (sin
  resultado). Se repitió en dos mitades, de una en una, `-m "not perf"`: (1) `core crypto auth
  settings cli audit` 1.476 ok, 3 saltadas; (2) `members plans memberships payments migrations
  architecture` más `test_ci_database.py` y `test_smoke.py` 1.578 ok, 1 saltada, 3
  deseleccionadas. Total 3.054 ok, 4 saltadas, 0 fallos (el Rojo tenía 3.060 con 93 fallos; +1
  prueba de la revisión). Después `npx vitest run` en `web/`: 110 archivos, 1.763 ok. Cobertura
  global no se midió (la corrida con `--cov` de toda la suite es la que agotó la memoria); la del
  módulo `app.modules.memberships` con `tests/memberships` es 99 % (735 sentencias, 5 sin cubrir;
  426 ok). `slice-gate.sh` no mide cobertura.
- B6.5 gate que sella: `memberships` con `test_renew_service`, `test_renew_router`,
  `test_cancel_service`, `test_cancel_router`, `test_lock_order`, `test_sell_service` y
  `tests/architecture/test_events_without_pii.py`.

### Evidencia de S3-B6 (B6.6, después del sello; E8)

- Gate B6.5 (sella) `memberships` con los siete archivos y `tests/architecture`: 395 ok, 1 saltada
  (`test_no_sensitive_in_logs`, US-074), al primer intento y repetido tras corregir el bloque del
  Verde. Checkpoint `3136ee6`.
- api `healthy` y recargado por el bind (la vista previa ya respondía 200 antes de la demo); log del
  api sin `ERROR` en los 15 minutos de la demo; 0 sesiones `idle in transaction`. Sin migración:
  `apex-db-1` sigue en `0011_payments_immutability`.
- Demo 4 por Nginx `:8180` con accesos del admin y de un coach firmados dentro del contenedor del
  api (solo en variables de la shell; ningún archivo con token). Socio "Demo B4Uno" de la demo 1 de
  B4 (`active` del 2026-10-25 al 2026-11-24), plan "Mensual mvjipju3" de 120.000:
  - `GET /members/9786ef0a…/memberships/renewal-preview?plan_id=b6fab314…` → **200**
    `{start_date 2026-11-25, end_date 2026-12-25, agreed_price_cop 120000, current_end_date
    2026-11-24}`: inicio = fin + 1;
  - `POST /members/9786ef0a…/memberships` con `renew: true` y `start_date` 2026-01-01 (descartado) →
    **201** `pending_payment` del 2026-11-25 al 2026-12-25 (`6086de3c…`); auditoría `insert` (seq
    879) del admin con el socio como sujeto; la vigente sin auditoría nueva;
  - la vista previa otra vez → **409** `future_membership_exists` con `existing_id` = `6086de3c…`;
  - venta sin `renew` con `start_date` 2026-11-01 (dentro de la vigente) → **409**
    `membership_conflict` con `existing_id` de la vigente (`927a3723…`): por D8 la revisión de
    conflicto (hay vigente y futura) va antes que la de solape, así que `membership_overlap` no
    llega a evaluarse;
  - psql en transacción revertida (`\set VERBOSITY verbose`): `INSERT` crudo del 2026-11-01 al
    2026-12-01 para el mismo socio → `ERROR 23P01` en `ex_memberships_member_dates`; después el socio
    sigue con 2 membresías.
- Demo 5: membresía `pending_payment` de B1 (`0338472b…`, "Prueba Smoke Uno"):
  - coach → `POST /memberships/0338472b…/cancel` **403** `forbidden`, sin cambios;
  - admin con `{"reason": "  Cambio de ciudad  "}` → **200** `status = cancelled`, `cancel_reason`
    "Cambio de ciudad" (recortado), `cancelled_at` lleno, fechas intactas, `Cache-Control:
    no-store`; psql: `cancelled_by` = admin; auditoría `update` (seq 880) del admin con el socio como
    sujeto y `before`/`after` con exactamente `status`, `cancel_reason`, `cancelled_by` y
    `cancelled_at`; 0 pagos de esa membresía (sin cambios);
  - admin otra vez → **409** `membership_already_cancelled`;
  - `POST /memberships/0338472b…/payments` (120.000 `cash`) → **409** `membership_cancelled`, sin
    pago;
  - psql en transacción revertida: `UPDATE memberships.memberships SET status = 'active' WHERE id =
    <anulada> AND status = 'cancelled'` → `ERROR 23000: memberships_identity: una membresía anulada
    no cambia`, `CONSTRAINT NAME: memberships_identity`; después sigue `cancelled`.
- `/health` y `/api/v1/health` → 200.
- Observación sin cambio: el 200 de `cancel` por Nginx trae `Cache-Control: no-store` dos veces
  (una en minúsculas); no es de B6 (mismo `no_store` del router de B1 a B5).

### S3-B7 · Rojo (B7.1 fixtures, B7.2 stubs y B7.3 Rojo; sin migración)

- Línea base: HEAD `c457922`, árbol limpio; suite en dos mitades con `-m "not perf"` y
  `TEST_DATABASE_URL`: (1) `core crypto auth settings cli audit` + `test_ci_database.py` y
  `test_smoke.py` 1.483 ok, 3 saltadas; (2) `members plans memberships payments migrations
  architecture` 1.571 ok, 1 saltada, 3 deseleccionadas. Total 3.054 ok, 4 saltadas. `ruff check` y
  `mypy src` (93 archivos) limpios.
- Rojo: 3.215 recolectadas; con `-m "not perf"`: **123 fallan**, 3.083 ok, 4 saltadas, 5
  deseleccionadas. Mitad 1: 1 falla (`test_docs_openapi_json_esta_al_dia`, P-API de B7.5), 1.482
  ok, 3 saltadas. Mitad 2: 122 fallan (todas de B7), 1.601 ok, 1 saltada, 5 deseleccionadas.
  `tests/memberships/test_list_perf.py` aparte: 2 fallan (rojo esperado). Las 122 + 2 son
  `NotImplementedError` de los stubs, salvo `test_el_handler_solo_marca_la_sesion` (`KeyError
  'apex.summary_dirty'`: el stub del handler no marca). `ruff format`, `ruff check` y `mypy src`
  (93 archivos) limpios. `db_test` sin residuos: `alembic_version = 0011_payments_immutability`,
  0 pagos, 0 membresías, 0 congelaciones, 0 socios, 0 planes, 0 usuarios `@test.apex`, 0 sesiones
  `idle in transaction`, los siete triggers de `memberships` y `payments` en `A` (también tras las
  dos pruebas `perf`, que siembran dentro de la transacción de `session`). `apex-db-1` no se tocó.
  - Verdes de la línea base que pasan a rojo: solo `test_docs_openapi_json_esta_al_dia` (P-API).
  - Nuevas: 154 (152 sin `perf`). En rojo 122 + 2 `perf`; verdes sobre los stubs 30 (el stub ya es
    el contrato): `test_list_router.py` 9 (403 `member`/401 de lista y detalle; 422 de forma de
    `limit` 0 y 201, `offset` -1, `status` de 101, fecha mal formada, `plan_id` y `member_id` no
    UUID; detalle con id no UUID), `test_list_service.py` 2 (esquema de filtros),
    `test_summary_router.py` 3 (403/401, orden de rutas, OpenAPI), `test_summary_cache.py` 7
    (suscripción a los siete eventos), `test_rules.py` 1 (`MEMBER_STATUS_PRIORITY`),
    `tests/architecture/test_no_cross_schema_sql.py` 4 y `test_handlers_no_new_locks.py` 4 nuevas.
    Cambiadas y verdes: `test_error_codes_per_route.py` y `test_list_routes_use_page_params.py`.
- Verde desechable (revertido; sin migración, solo `db_test`): `active_ids`, `parse_status_filter`,
  `resolve_member_membership`/`resolve_member_status`, `status_expr` (`case` con `literal(today,
  Date)` y `exists()` sobre `membership_freezes`), `member_status_rank_expr`, `list` (validación,
  filtros, `paginate`, enriquecimiento por lote), `get`, `summary` (caché, `active_ids`, lotes con
  `DISTINCT ON` por `postgresql.distinct_on` y `count(*) FILTER`), `status_for`,
  `member_ids_by_status`, `count_active_by_plan`, el handler y los dos listeners de `Session`. Las
  ocho líneas del gate de B7 más `tests/architecture`: 509 ok, 1 saltada; solo fallaron
  `test_ninguna_funcion_supera_50_lineas` (el `list` desechable, no el Rojo) y un `ERROR` de
  `caplog` por correr con `-p no:logging`. `test_list_perf.py`: 2 ok (lista `expiring` 16,5 ms;
  resumen sin caché 18,1 ms). Pruebas de mutación de E13 sobre el desechable: sin `if
  session.in_nested_transaction(): return` fallan 3 de `test_summary_cache.py` (SAVEPOINT de
  `sell`, de `register` y el rollback); sin la guarda de SAVEPOINT en `after_soft_rollback` falla
  `test_el_rollback_de_un_savepoint_no_pierde_la_marca_de_la_transaccion`. Sin defectos de prueba.
  Después, `memberships/queries.py`, `memberships/rules.py` y `members/service.py` restaurados
  desde copia (sha256 iguales a los del stub).
- Fixtures (B7.1): `tests/conftest.py` gana `ContadorDeConsultas` y la fixture
  `contador_de_consultas` (`before_cursor_execute` sobre `engine.sync_engine`, toda la prueba;
  ignora `SAVEPOINT`, `RELEASE` y `ROLLBACK TO`; `midiendo()` vacía lo anotado; `de(tabla)` cuenta
  las sentencias que nombran `esquema.tabla` como palabra completa, así `memberships.memberships`
  no cuenta `memberships.membership_freezes`; `solo_de(tabla, *sin)`). `tests/memberships/
  conftest.py` gana `sin_cache_de_resumen` (autouse: `configure_summary_cache(0)` y
  `reset_summary_cache()` antes; al salir vacía y vuelve a `SUMMARY_CACHE_TTL_S`).
  `tests/memberships/_apoyo.py` gana `RESUMEN`, `ruta_detalle`, `CAMPOS_ROW`, `CAMPOS_RESUMEN`,
  `TABLA_MEMBRESIAS`, `TABLA_CONGELACIONES` y `guardar_politica(session, version=0, **cambios)`.
- Stubs (B7.2): `members/service.py: active_ids(session) -> frozenset[UUID]`;
  `memberships/exceptions.py`: `StatusFilterInvalid` y `DateRangeInvalid` (422
  `validation_error`, `field` por defecto `status` y `ends_to`); `memberships/rules.py`:
  `ResolvedStatus`, `RESOLVED_NONE`, `MEMBER_STATUS_PRIORITY = ("current", "pending_payment",
  "expired", "future")`, `parse_status_filter`, `resolve_member_membership`,
  `resolve_member_status` (con `NotImplementedError`); `memberships/schemas.py`:
  `STATUS_FILTER_MAX_LENGTH = 100`, `MembershipListQuery`, `MembershipRow`,
  `MembershipSummaryOut`, `MemberMembership`; `memberships/queries.py`: `ENDS_FLOOR`,
  `ENDS_CEILING_YEARS`, `SUMMARY_ID_BATCH = 1000`, `SUMMARY_CACHE_TTL_S = 30`,
  `SUMMARY_DIRTY_KEY = "apex.summary_dirty"`, `SummaryCache` (real), `reset_summary_cache` y
  `configure_summary_cache` (reales, ver decisiones), `_mark_summary_dirty` (no hace nada),
  `status_expr`, `member_status_rank_expr`, `list`, `get`, `summary`, `status_for`,
  `member_ids_by_status`, `count_active_by_plan` (con `NotImplementedError`); `queries.py` usa
  `builtins.list` en las anotaciones y llamadas existentes (`list` lo sombrea);
  `memberships/service.py`: re-exporta los siete y `MemberMembership`, `__all__:
  builtins.list[str]`, y al final suscribe `queries._mark_summary_dirty` a `MembershipSold`,
  `MembershipActivated`, `MembershipActivationReverted`, `MembershipFrozen`, `MembershipCancelled`,
  `PaymentRegistered` y `PaymentVoided` (después de los handlers de negocio);
  `memberships/router.py`: `GET /memberships/summary` (sin parámetros), `GET /memberships`
  (`StaffDep`, `PageParams`, `q`, `status` con alias y `max_length=100`, `plan_id`, `member_id`,
  `ends_from`, `ends_to`; `enforce_user_limit(request, PII_SEARCH_BUCKET, principal.user_id)`
  solo con `q`; `responses_for(422, 429)`) y `GET /memberships/{membership_id}`
  (`responses_for(404)`), en ese orden y al final del router; `no_store` del router.
- Archivos de prueba nuevos: `tests/memberships/test_status_expr_parity.py` (7),
  `test_list_service.py` (32), `test_list_perf.py` (2, `perf`), `test_list_router.py` (25),
  `test_status_queries_service.py` (16), `test_summary_cache.py` (18), `test_summary_router.py`
  (6); `tests/architecture/test_no_cross_schema_sql.py` (4). Cambiados: `tests/memberships/
  test_rules.py` (+40), `tests/architecture/test_handlers_no_new_locks.py` (+4: lista exacta de
  handlers `_mark_*` de `queries.py`, solo `session.info`, sin `await` ni candados, lista exacta
  de suscriptores de los siete eventos y control con fuente falsa), `test_error_codes_per_route.py`
  (E2: `CON_LIMITE` gana `("get", "/api/v1/memberships")`), `test_list_routes_use_page_params.py`
  (gana `GET /api/v1/memberships`). Sin cambio: `test_user_limits_catalog.py` (`members-search` ya
  tenía ruta; el conjunto de rutas sale de `CON_LIMITE`).
- Importadores de lo tocado: `members/service.py` lo importan `members/router.py`,
  `memberships/{lifecycle,queries,sell}.py` y pruebas; `memberships/exceptions.py`
  `memberships/{lifecycle,rules,sell}.py` y pruebas; `memberships/rules.py`
  `memberships/{lifecycle,queries,schemas,sell}.py`, `tests/factories/memberships.py` y pruebas
  (`schemas` lee ahora también `ResolvedStatus`; `rules` no importa `schemas`: sin ciclo);
  `memberships/schemas.py` `memberships/{lifecycle,queries,router,sell}.py`,
  `tests/memberships/_apoyo.py` y pruebas (importa ahora `core.pagination.MAX_SEARCH_LENGTH`);
  `memberships/queries.py` `memberships/{lifecycle,sell,service}.py` (importa ahora
  `core.clock`, `core.events.DomainEvent` y `core.pagination.Page/PageParams`; ninguna arista
  nueva entre módulos); `memberships/service.py` `memberships/router.py`,
  `tests/memberships/{conftest,_apoyo}.py` y pruebas; `memberships/router.py` solo `main.py`
  (por `MODULES`); `tests/conftest.py` toda la suite. Ninguna firma existente cambia: todo es
  agregado.

#### Decisiones de prueba que el Verde debe respetar

1. **`active_ids`:** `frozenset[UUID]` de los socios con `deleted_at IS NULL` (también los
   `inactive`), en una sentencia y sin descifrar.
2. **`parse_status_filter`:** separa por comas, recorta cada parte y funde repetidos; `None`, `""`
   o solo espacios es `None`; un estado desconocido, en mayúsculas, `none` o una parte vacía
   (`"active,"`, `",active"`, `"active,,expiring"`) es `StatusFilterInvalid` (422
   `validation_error`, `field="status"`, sin el valor en el mensaje). `cancelled` es válido.
3. **Estado del socio (US-092):** sobre snapshots con estado EFECTIVO; las `cancelled` no cuentan.
   Categorías en orden `MEMBER_STATUS_PRIORITY`: `current` (no `pending_payment` ni `expired`,
   inicio <= hoy), `pending_payment`, `expired`, `future` (inicio > hoy). Decide la de mejor
   categoría; en empate, la de fin más tardío (dos vencidas: la última). El estado es el
   efectivo de la que decide (una futura de plan corto que ya está `expiring` cuenta
   `expiring`). `resolve_member_membership` devuelve `(estado, snapshot | None)`: `("none",
   None)` sin membresías o solo anuladas. Indiferente al orden de entrada.
4. **`status_expr(today, expiring_days)`** coincide con `compute_status` en toda la malla
   (`today` del 22 de octubre al 2 de noviembre con fin 31 de octubre, `expiring_days` 0, 3 y
   7, lo guardado `active`/`expired`/`frozen` no manda, congelación que contiene hoy o que cruza
   el fin, `classes_remaining` 0 y 5, `pending_payment`, `cancelled`, futura). El SQL solo nombra
   tablas de `memberships`. **`member_status_rank_expr(today, expiring_days)`** es la posición en
   `MEMBER_STATUS_PRIORITY` de la categoría de cada fila no anulada. La prueba arma el `DISTINCT
   ON` con `sqlalchemy.dialects.postgresql.distinct_on` (en SQLAlchemy 2.1 `select().distinct(col)`
   está deprecado) ordenado por `member_id, rango, end_date DESC`.
5. **`list(session, filters: MembershipListQuery, page: PageParams) -> Page[MembershipRow]`**
   (como `members.list`; el blueprint lo daba con argumentos sueltos). Valida en el service, con
   el "hoy" del reloj: `parse_status_filter`; cada `ends_*` entre `ENDS_FLOOR` (2020-01-01,
   incluido) y hoy más 5 años (la prueba fija que 2031-10-20 pasa y 2032-10-21 falla, sin fijar
   el día exacto del techo), `DateRangeInvalid(field=<el que falla>)`, y después invertidas en
   `ends_to`; años 1 y 9999 dan 422, nunca 500. Sin `status` excluye `cancelled`; con `status`,
   el estado efectivo. `ends_*` incluyen los extremos. Orden `end_date, id`. `q` con
   `members.search_ids(include_deleted=True)` (un dado de baja aparece); sin coincidencias,
   página vacía sin consultar `plans` ni `payments`. Con 8 filas en la página: exactamente una
   sentencia a `members.members`, una a `plans.plans`, una a `payments.payments` y como mucho
   una de congelaciones aparte. `paid_cop` ignora los anulados. Cero `decrypt` (también con `q`
   por documento). Un `status` de 101 caracteres falla en el esquema (`loc == ("status",)`).
6. **`get`:** `MembershipOut` (las mismas claves que `membership_out`, con congelaciones y
   `paid_cop`); 404 `membership_not_found`; una anulada se ve con su motivo.
7. **`summary(session, *, today=None)`:** cuenta socios vivos por estado resuelto (10/4/4/1/2 en
   el escenario; suma más `none` = vivos). Lee `members.service.active_ids` una vez y consulta
   `memberships.memberships` una vez por lote de `SUMMARY_ID_BATCH`, **leído al llamar** (la
   prueba lo cambia con `monkeypatch.setattr(queries, "SUMMARY_ID_BATCH", 10_000)`): 2.500 socios
   dan 3 sentencias y la misma suma que con 1; sin socios vivos, ninguna. `today=None` es "hoy"
   de Bogotá del reloj.
8. **`status_for`:** `dict[UUID, MemberMembership(status, plan_id, plan_name, end_date)]` de la
   membresía que decide; los ids sin membresías no anuladas no aparecen (blueprint; el llamador
   usa `none`); lotes de `ID_BATCH` (200 ids: 1 sentencia a `memberships.memberships`; 201: 2);
   sin ids no envía ninguna sentencia (ni la de settings).
9. **`member_ids_by_status(statuses, plan_id=None)`:** por el plan de la membresía que DECIDE
   (la renovación Trimestral pendiente de Laura no la pone en `pending_payment` del Trimestral);
   con `statuses` vacío, `set()`.
10. **`count_active_by_plan`:** estado efectivo distinto de `cancelled` y `expired` (una `active`
    guardada vencida no cuenta; una congelada sí).
11. **Caché (S3-D53, E11, E13):** clave `(hoy, expiring_days)` (volver al `expiring_days` previo
    sirve la entrada vieja); una entrada sirve mientras su edad medida con `current_clock()` sea
    menor que el TTL (29 s sirve, 31 s no); TTL 0 nunca sirve. `_mark_summary_dirty(event,
    session)` solo hace `session.info["apex.summary_dirty"] = True` (sin `await`, sin candados).
    La invalidación es un listener de `Session`: `after_commit` que retorna si
    `session.in_nested_transaction()` (confirmado con prueba de mutación: `after_commit` se
    despacha antes de cerrar el SAVEPOINT) y, si la marca estaba, vacía la caché y la borra;
    `after_soft_rollback` borra la marca solo si la transacción revertida NO es un SAVEPOINT
    (`previous_transaction.nested`): el rollback de un SAVEPOINT dentro de una transacción ya
    marcada no la pierde (si no, el commit siguiente conservaría datos viejos, contra S3-D53).
    Tras el commit real la marca queda borrada; tras el rollback real también.
12. **Rutas:** `/memberships/summary` antes de `/memberships/{membership_id}` (prueba
    estructural sobre `effective_routes`); el resumen no declara parámetros, 404, 422 ni 429. La
    lista con `q` gasta `PII_SEARCH_BUCKET` (40 aquí + 20 en `/members?q=` pasan, la 21 en
    socios y la siguiente aquí dan 429); sin `q` no gasta (61 seguidas dan 200). Los 422 de la
    lista llevan `validation_error` con `field` (también los que decide el service).

#### Desviaciones del Rojo

- `members/service.py` no tiene `__all__` (el plan dice que `active_ids` "va en `__all__`"): no
  se crea uno para un solo nombre, que además ocultaría el resto en un `import *`. La partición de
  B9a decide la fachada.
- `reset_summary_cache` y `configure_summary_cache` no lanzan `NotImplementedError`: los usa la
  fixture autouse `sin_cache_de_resumen` en cada prueba de `tests/memberships` y un stub que
  lanzara rompería las ~1.000 pruebas ya verdes. Son dos líneas sobre la clase `SummaryCache`,
  que el plan ya excluía de los stubs.
- `after_soft_rollback` con guarda de SAVEPOINT y su prueba amplían E13 (el texto de E13 solo
  decía "limpia la marca"); motivo en la decisión 11.
- `FrozenClock.advance` no tiene `seconds` (el plan escribe `reloj.advance(seconds=31)`): la prueba
  usa `reloj.set(T0 + timedelta(seconds=31))`; `core/clock.py` no se toca.
- Los 2.500 socios del caso de lotes se siembran con SQL crudo (blobs `apx1.prueba...` y
  `document_idx` falsos: el resumen nunca los lee), no con `make_members` (2.500 altas cifradas
  y auditadas harían lenta una prueba que no es `perf`). La prueba `perf` sí usa `make_members` y
  `make_memberships`, como pide el plan.
- `test_no_cross_schema_sql.py` es una guardia: verde sobre los stubs y sobre el código actual.
- No se tocan `docs/openapi.json`, `web/`, `DECISIONES.md`, `CLAUDE.md` ni `RUNBOOK.md`.

### S3-B7 · Verde (B7.4 a B7.6; sin migración)

- B7.4: `members.active_ids` (`frozenset`, una sentencia); `rules.parse_status_filter`,
  `member_status_category`, `resolve_member_membership` (mejor categoría, luego fin y después
  inicio más tardío) y `resolve_member_status`; `queries.py`: `status_expr` (`case` con
  `literal(today, Date)` y `EXISTS` correlacionado sobre `membership_freezes`),
  `member_status_rank_expr`, `_deciding` (`DISTINCT ON` con `postgresql.distinct_on`), `list`
  (validación, `q` con `search_ids(include_deleted=True)` y `= ANY(:ids uuid[])`, `paginate`,
  `_rows_for` con una sentencia por vecino y estado efectivo con `compute_status`), `get` (estado
  efectivo), `summary` partida (`_summary_compute`, `_summary_counts` con `count(*) FILTER`,
  `_summary_cache_get/put`), `_mark_summary_dirty`, listeners `after_commit` (guarda de
  SAVEPOINT) y `after_soft_rollback` (solo transacción real) registrados una vez, `status_for`,
  `member_ids_by_status`, `count_active_by_plan`. Sin partir `queries.py` (688 líneas; el handler
  y `SUMMARY_ID_BATCH` deben quedar en `queries.py` por las pruebas). `ruff format`, `ruff check`
  y `mypy src` (93 archivos) limpios.
- Revisión de seguridad: 0 CRITICAL/HIGH, 2 MEDIUM corregidos (marca de sesión sin caché;
  generación de la caché y candado de un solo cálculo), LOW-2 y LOW-3 corregidos, LOW-1 y LOW-4
  aceptados (DECISIONES "S3-B7"). Cinco pruebas nuevas en `test_summary_cache.py` (23 en total).
- B7.5 P-API: `export-openapi` dos veces idéntica (sha256 `f908cbee…`, +520 líneas en
  `docs/openapi.json`, +339 en `web/src/core/api/types.ts`); `types.contract.test.ts` 5 ok y
  `tsc --noEmit` limpio. **F4 y F5 pueden arrancar sobre este contrato** (`GET
  /memberships/summary`, `GET /memberships`, `GET /memberships/{membership_id}`).
- Docs: RUNBOOK §10 "Estado de las membresías, lista y resumen" (estado derivado sin job, lista,
  detalle, resumen, caché de 30 s, `expiring_days` y la consulta psql para cuadrar el resumen);
  DECISIONES "S3-B7".
- Suite en dos mitades, de una en una, `-m "not perf"`: (1) `core crypto auth settings cli
  audit` + `test_ci_database.py` y `test_smoke.py` 1.483 ok, 3 saltadas; (2) `members plans
  memberships payments migrations architecture` 1.728 ok, 1 saltada, 5 deseleccionadas. Total
  3.211 ok, 4 saltadas, 0 fallos (el Rojo: 3.215 con 123 fallos; +5 de la revisión).
  `tests/memberships/test_list_perf.py` aparte: 2 ok. `db_test` sin residuos (0 socios,
  membresías y pagos; 0 `idle in transaction`; los siete triggers en `A`).
- B7.6 gates (abajo, en "Evidencia de S3-B7").

### Evidencia de S3-B7 (B7.7, después del sello; E8)

- Gates B7.6 al primer intento, seguidos y sin editar entre ellos (`ls` previo de los once
  archivos): (1) `PYTEST_ADDOPTS="-m 'not perf'"` `members` con `test_service_list.py`,
  `test_router_list.py` y `tests/architecture` 320 ok; (2) el que sella, sin `PYTEST_ADDOPTS`,
  `memberships` con las nueve líneas y `tests/architecture` 518 ok (incluye las dos `perf`). Una
  saltada en los dos (`test_no_sensitive_in_logs`, US-074). Checkpoint `9f5ae13`.
- api `healthy`, recargado por el bind (`WatchFiles detected changes ... Reloading`,
  `Application startup complete`; el contenedor ve `_summary_flight_lock`); log del api sin
  `ERROR` en los 15 minutos de la demo; 0 sesiones `idle in transaction`. Sin migración:
  `apex-db-1` sigue en `0011_payments_immutability`.
- Demo por Nginx `:8180` con accesos del admin y de un coach firmados dentro del contenedor del
  api (solo en variables de la shell; el script temporal se borró del contenedor y del
  scratchpad):
  - `GET /api/v1/memberships?status=active,pending_payment` (admin) → **200** `total 3`, orden
    por fin: "Demo B4Uno" `927a3723…` `active` (`paid_cop` 120.000), "Demo B4Dos" `b21e25b5…`
    `pending_payment` (`paid_cop` 61.000: el pago anulado de B5 no suma) y la renovación de B6
    `6086de3c…` `pending_payment` (`paid_cop` 0, del 2026-11-25 al 2026-12-25);
  - `GET /api/v1/memberships/summary` → **200** `{"active": 1, "expiring": 0, "expired": 0,
    "frozen": 0, "pending_payment": 1}` con `Cache-Control: no-store`. Cuadre en psql con la
    consulta de RUNBOOK §10 ("Cuadrar el resumen en psql", `expiring_days` 7 de
    `settings.settings_sections`): `active 1`, `pending_payment 1`; 19 socios vivos, así que 17
    `none` (Demo B4Uno decide por su vigente aunque tenga la renovación pendiente; la de B1 está
    anulada);
  - `GET /api/v1/memberships/b21e25b5…` (socio de la demo 3 de B5) → **200** `status
    pending_payment`, `paid_cop` 61.000, `freezes []`: **cierra la evidencia pendiente de B5.6**;
  - `GET /api/v1/memberships?q=Demo` → **200**; coach → **200** en la lista y en el resumen; sin
    token → **401** `unauthorized` en los dos; coach con `status=vigente` → **422**
    `validation_error`, `field = "status"`, mensaje sin el valor;
  - `/health` y `/api/v1/health` → 200.
- Rol `member`: no hay ningún usuario `member` en la base de desarrollo, y el api toma el rol del
  usuario en la base (`PrincipalLoader`), no del claim del token: un access firmado con
  `role=member` para el id del admin responde 200 como admin (no es un escalamiento: firmar
  exige la llave privada del api). El 403 de `member` lo fijan `test_list_router.py` y
  `test_summary_router.py` con usuarios reales; no se demuestra en vivo.

### S3-B8 · Rojo (B8.1 stubs y B8.2 Rojo; sin migración)

- Línea base: HEAD `7eac10a`, árbol limpio; suite en dos mitades con `-m "not perf"` y
  `TEST_DATABASE_URL`: (1) `core crypto auth settings cli audit` + `test_ci_database.py` y
  `test_smoke.py` 1.483 ok, 3 saltadas; (2) `members plans memberships payments migrations
  architecture` 1.728 ok, 1 saltada, 5 deseleccionadas. Total 3.211 ok, 4 saltadas. `ruff check` y
  `mypy src` (93 archivos) limpios.
- Rojo: 3.422 recolectadas; con `-m "not perf"`: **162 fallan**, 3.249 ok, 4 saltadas, 7
  deseleccionadas. Mitad 1: 1 falla (`test_docs_openapi_json_esta_al_dia`, P-API de B8.4), 1.482
  ok, 3 saltadas. Mitad 2: 161 fallan (todas de B8), 1.767 ok, 1 saltada, 7 deseleccionadas.
  `tests/payments/test_list_perf.py` aparte: 2 fallan (rojo esperado: 500 por el stub). De las
  161: 158 son `NotImplementedError` de los stubs (`payments.list` 42, `month_bounds_utc` 21,
  `parse_month` 20, `payments.summary` 19, `build_filters` 18, `check_date_range` 12,
  `payments.get` 9, `partial_email` 8, `is_backdated` 7, `date_ceiling` 2; las de router llegan
  como 500) y 3 son del grafo de services: `test_cada_arista_permitida_existe` (`payments → auth` y
  `payments → members` declaradas sin import), `test_payments_depende_de_members_auth_y_settings_
  y_no_de_memberships` y `test_el_par_perezoso_payments_memberships_existe_y_esta_permitido`
  (`perezosas["payments"]` vacío). `ruff format`, `ruff check` y `mypy src` (93 archivos) limpios.
  `db_test` sin residuos: `alembic_version = 0011_payments_immutability`, 0 pagos, 0 membresías,
  0 congelaciones, 0 socios, 0 planes, 0 usuarios `@test.apex`, 0 sesiones `idle in
  transaction`, los siete triggers de `memberships` y `payments` en `A` (también tras las dos
  `perf`, que siembran 10.000 pagos dentro de la transacción de `session`). `apex-db-1` no se
  tocó.
  - Verdes de la línea base que pasan a rojo: `test_docs_openapi_json_esta_al_dia` (P-API) y
    `test_cada_arista_permitida_existe` (S3-D80: las dos aristas entran en B8 con su uso).
  - Nuevas: 203 (202 netas: una del grafo se renombra; 201 sin `perf`). En rojo 160 + 2 `perf`;
    verdes sobre los stubs 41
    (el stub ya es el contrato): `test_list_filters.py` 11 (estructura de `PaymentFilters`,
    `DATE_FLOOR`, el alias `from` y 8 rechazos del esquema `PaymentListQuery`),
    `test_month_bounds.py` 2 (`MONTH_MIN`/`MONTH_MAX`; `InvalidMonth` no es `ValueError`),
    `test_router_list.py` 13 (403/401 y 12 422 de forma: `limit` 0 y 201, `offset`, `method`,
    `from` mal formada y sin zona, `voided`, `backdated`, tres ids y `q` de 101),
    `test_router_get.py` 3 (422 por UUID, 403/401, orden de los `GET`), `test_router_summary.py`
    3 (403/401, `month` de 10 caracteres, OpenAPI), `tests/architecture` 7
    (`test_list_rows_without_sensitive_fields.py` 3: filas de membresías y pagos, correo parcial
    sin campos `*email*`; los subprocesos de import de las dos aristas nuevas en los dos
    órdenes, 4) y `tests/memberships/test_rules.py` 2
    (la prueba parametrizada por las subclases de `PaymentError` gana `InvalidMonth` e
    `InvalidDateRange`).
- Verde desechable (revertido; sin migración, solo `db_test`): `parse_month` (`[0-9]{4}-[0-9]{2}`
  con `fullmatch`), `month_bounds_utc` (aritmética de `(año, mes)` con `ZoneInfo`),
  `date_ceiling`, `check_date_range`, `partial_email` (`rpartition("@")`), `is_backdated`,
  `build_filters`, `list` (validación, `search_ids(include_deleted=True)` solo con `q`, total y
  página `paid_at DESC, id DESC`), `get`, `summary` (`SUM`/`COUNT ... FILTER` en una sentencia) y
  `_enrich` (`refs_for` perezoso con `# lazy: G-03 (payments -> memberships)`, `auth.names_for`
  una vez con quien registró y quien anuló, `partial_email`), con `members.service` y
  `auth.service` importados a nivel de módulo en `queries.py`. Resultado: `tests/payments` y
  `tests/architecture` 737 ok y 1 falla de prueba (abajo); corregida, la mitad 2 completa 1.928
  ok, 1 saltada, 7 deseleccionadas (incluye `test_ninguna_funcion_supera_50_lineas`, el grafo con
  sus subprocesos y `test_no_cross_schema_sql`). `test_list_perf.py`: 2 ok (lista 14,8 ms;
  resumen 12,2 ms con 10.000 pagos): la migración condicional `0014_payments_registered_by_idx`
  no hace falta con este plan. Después, `payments/rules.py` y `payments/queries.py` restaurados
  desde copia (sha256 iguales a los del stub, los nueve archivos de `payments/`).
  - Defecto de prueba encontrado y corregido: `test_sin_q_no_hay_operaciones_de_cripto_y_con_q_
    solo_indices` no veía las filas `index` de la búsqueda por documento porque la bitácora
    `crypto_ops` se vacía en `before_commit`; `listar` (y `detalle` en `test_get.py`) ahora
    confirma como una petición (`await session.commit()`), igual que `tests/members`.
- Stubs (B8.1): `payments/exceptions.py`: `InvalidMonth` (422 `validation_error`, `field`
  `month`) e `InvalidDateRange` (422 `validation_error`, `field` por defecto `to`);
  `payments/rules.py`: `DATE_FLOOR = PAID_AT_FLOOR`, `DATE_CEILING_YEARS = 5`, `MONTH_MIN = 2020`,
  `MONTH_MAX = 2100`, `MONTH_LENGTH = 7`, `BACKDATED_AFTER = 24 h`, `PaymentFilters` (real) y
  `build_filters`, `date_ceiling`, `check_date_range`, `parse_month`, `month_bounds_utc`,
  `partial_email`, `is_backdated` (con `NotImplementedError`); `payments/schemas.py`:
  `PaymentListQuery` (`extra="forbid"`, `populate_by_name`, alias `from`), `PaymentRow`,
  `PaymentDetail`, `PaymentsByMethod`, `PaymentsSummary`; `payments/queries.py`: `list`, `get`,
  `summary` y `_enrich` (con `NotImplementedError`), y `builtins.list` en lo existente (`list`
  sombrea al de Python); `payments/service.py`: re-exporta `list`, `get` y `summary` y
  `__all__: builtins.list[str]`; `payments/router.py`: `GET /payments/summary` (`month` con
  `max_length=MONTH_LENGTH`, `responses_for(422)`), `GET /payments/methods` (ya existía),
  `GET /payments` (`PageParams`, `q`, `from` por alias, `to`, `method`, `registered_by`,
  `voided`, `backdated`, `member_id`, `membership_id`; `enforce_user_limit(request,
  PII_SEARCH_BUCKET, principal.user_id)` solo con `q`; `responses_for(422, 429)`) y
  `GET /payments/{payment_id}` (`responses_for(404)`), en ese orden de `GET`; `no_store` del
  router. Ningún stub importa `members.service` ni `auth.service`: un import sin uso lo rechaza
  `ruff` (F401) y S3-D80 pide las aristas con uso real; entran en el Verde.
- Archivos de prueba nuevos (`tests/payments`): `test_month_bounds.py` (43),
  `test_list_filters.py` (58), `test_list.py` (29), `test_router_list.py` (26), `test_get.py` (5),
  `test_router_get.py` (8), `test_summary.py` (11), `test_router_summary.py` (10) y
  `test_list_perf.py` (2, `perf`). Cambiados: `tests/payments/_apoyo.py` (`RESUMEN`,
  `TABLA_PAGOS`, `CAMPOS_ROW`, `CAMPOS_DETAIL`, `CAMPOS_RESUMEN`, `CAMPOS_POR_MEDIO`,
  `ruta_pago`), `tests/architecture/test_service_import_graph.py` (`ALLOWED_EDGES` gana
  `("payments", "auth")` y `("payments", "members")`, S3-D80; `test_payments_depende_de_settings_
  y_no_de_memberships` pasa a `..._de_members_auth_y_settings_y_no_de_memberships`; nueva
  `test_el_par_perezoso_payments_memberships_existe_y_esta_permitido`),
  `test_error_codes_per_route.py` (E2: `CON_LIMITE` gana `("get", "/api/v1/payments")`),
  `test_list_routes_use_page_params.py` (gana `GET /api/v1/payments`) y
  `test_list_rows_without_sensitive_fields.py` (recorre también `/api/v1/memberships` y
  `/api/v1/payments`; sufijo sensible `_email`; `registered_by_name` sí, ningún campo con
  `email`). Sin cambio: `test_user_limits_catalog.py` (la cubeta ya tenía ruta; el conjunto sale
  de `CON_LIMITE`).
- Importadores de lo tocado: `payments/rules.py` lo importan `payments/{queries,schemas,service}.py`
  y pruebas (importa ahora `sqlalchemy.ColumnElement`); `payments/exceptions.py`
  `payments/{rules,service}.py`, `tests/architecture/test_gates_registered.py` y pruebas de
  `memberships` y `payments`; `payments/schemas.py` `memberships/{schemas,sell}.py`,
  `payments/{models,router,service}.py`, `settings/schemas.py` y pruebas (importa ahora
  `core.pagination.MAX_SEARCH_LENGTH`; no importa `queries`: sin ciclo);
  `payments/queries.py` solo `payments/service.py` (importa ahora `payments.schemas` y
  `core.pagination.Page/PageParams`); `payments/service.py` `core/events.py`,
  `memberships/{lifecycle,queries,sell,service}.py`, `payments/{events,router}.py` y pruebas;
  `payments/router.py` solo `main.py` (por `MODULES`). Ninguna firma existente cambia: todo es
  agregado.

#### Decisiones de prueba que el Verde debe respetar

1. **`PaymentFilters`** (dataclass congelada; nueve campos, todos `None` por defecto) y
   **`build_filters(filters, member_ids_from_q=())`**: sin filtros, `[]`. Rango `[from_, to)`
   (incluye `from`, excluye `to`; `from == to` da vacío); `method`, `registered_by`,
   `member_id`, `membership_id` por igualdad; `voided` y `backdated` tri-estado; `q` es
   `lower(reference) = lower(q)` (exacta, no parcial) o `member_id` en `member_ids_from_q`; sin
   `q` los ids no filtran. Se prueba ejecutando las condiciones contra pagos reales.
2. **Rango (M-4, S3-D47):** `check_date_range(from_, to, today)` (nombre nuevo, el plan no lo
   fijaba) con `InvalidDateRange` (en `exceptions.py`, 422 `validation_error`, `field` `from` o
   `to`; invertidas en `to`); `DATE_FLOOR == PAID_AT_FLOOR` (2020-01-01T00:00Z);
   `date_ceiling(today)` con zona entre hoy + 5 años − 1 día y hoy + 6 años (2031-10-20 pasa,
   2032-10-21 falla; un 29 de febrero no falla); años 1 y 9999 dan 422 sin `OverflowError`.
   `list` valida con el "hoy" de Bogotá del reloj antes de consultar.
3. **Mes (D23, M-4):** `parse_month` acepta solo `AAAA-MM` con dígitos ASCII completo (sin
   espacios, sin salto de línea final, sin dígitos de ancho completo, sin signo), mes 01–12, año
   2020–2100; `month_bounds_utc(month: str)` valida igual y devuelve `[inicio, fin)` con zona
   UTC (octubre: 05:00Z del 1 al 05:00Z del 1 de noviembre; diciembre cruza de año; `2100-12`
   termina en 2101-01-01T05:00Z). `InvalidMonth` vive en `exceptions.py` (422
   `validation_error`, `field="month"`, sin el valor en el mensaje) y no hereda de `ValueError`.
4. **`partial_email`:** primera letra de la parte local, `•••`, `@` y el dominio tras la ÚLTIMA
   `@`; sin `@`, primera letra y `•••`; vacío, `•••`; sin cambiar mayúsculas.
5. **`backdated` (M-8, S3-D51):** `created_at - paid_at > 24 h` estricto (24 h exactas no; 24 h
   y 1 s sí; un `paid_at` posterior a `created_at` no). El filtro SQL usa la misma regla.
6. **`list(session, filters: PaymentListQuery, page: PageParams) -> Page[PaymentRow]`** (como
   `members.list` y `memberships.list`). Orden `paid_at DESC, id DESC`. `q` con
   `members.service.search_ids(include_deleted=True)` solo cuando hay `q` (un socio dado de baja
   aparece). Con 25 filas: exactamente una sentencia a `memberships.memberships`,
   `members.members`, `plans.plans` y `auth.users`, y como mucho dos a `payments.payments`; con
   `q` de apellido, dos a `members.members` (búsqueda y nombres); con `q` sin coincidencias,
   ninguna a `memberships`, `plans` ni `auth`.
7. **Cifrado:** ningún `decrypt` nunca (ni con `q`); sin `q` ninguna fila nueva en `crypto_ops`;
   con `q` por documento, solo filas `index` de la búsqueda de socios. Así se lee "decrypt solo
   con q" del plan (el blueprint dice "ningún `decrypt` salvo el de `q`" y B7 fijó cero
   `decrypt` con `q`: la búsqueda va por índice ciego). Las ayudas de prueba confirman como una
   petición (`before_commit` vacía la bitácora).
8. **Filas:** `PaymentRow` tiene exactamente 17 claves (`CAMPOS_ROW`); `registered_by_name` es
   `str | None` (correo parcial; `None` solo si el usuario no existiera); nombre, apellido,
   plan y fechas de la membresía no nulos (de `refs_for`). `PaymentDetail` suma `voided_by`,
   `voided_by_name` (parcial), `voided_at` y `created_at`. Ningún correo completo en la salida.
9. **`get`:** `PaymentNotFound` (404 `payment_not_found`); una sentencia a `auth.users` para
   quien registró y quien anuló.
10. **`summary(session, month: str | None = None) -> PaymentsSummary`:** `month` de la salida es
    `AAAA-MM`; `by_method` es un objeto con `cash`, `nequi` y `breb` siempre; `total_cop` y
    `by_method` solo vigentes; `payments_count` vigentes y `voided_count` anulados del mes por
    `paid_at` (anular en octubre un pago de septiembre baja septiembre y no toca octubre, L-13);
    sin `month`, el mes de `current_clock().today_bogota()`; `total_cop` cuadra con la suma de
    `list(from, to, voided=false)` del mismo mes.
11. **Rutas:** orden de los `GET` bajo `/api/v1/payments`: `summary`, `methods`, lista,
    `{payment_id}` (prueba estructural). `month` con `max_length=7` (un valor más largo es 422 de
    forma en `month`). Los 422 de la lista llevan `validation_error` con `field` (`from` por su
    alias), también los que decide el service. La cubeta `PII_SEARCH_BUCKET` solo con `q`: 60
    aquí dan 200 y la 61 429; 30 en socios y 30 aquí, la 61 aquí da 429; 40 aquí y 20 en socios,
    la 21 en socios y la siguiente aquí dan 429.
12. **`perf`:** se mide por HTTP (más estricto que "en el service" del blueprint) con siembra
    cruda; `GET /payments?limit=25` < 500 ms y `GET /payments/summary?month=2026-10` < 300 ms con
    10.000 pagos.

#### Desviaciones del Rojo

- `InvalidMonth` e `InvalidDateRange` viven en `payments/exceptions.py` (convención del módulo;
  el plan los listaba en `rules.py`, que los lanza). `check_date_range`, `MONTH_LENGTH`,
  `DATE_CEILING_YEARS`, `BACKDATED_AFTER` y `PaymentsByMethod` son agregados que el plan no
  nombraba (contrato necesario para las pruebas).
- "decrypt solo con q" se fija como "ningún `decrypt`; con `q`, solo `index`" (decisión 7).
- `members.service.ensure_exists` (S3-D80) no lo exige ninguna prueba: la arista
  `payments → members` la justifica `search_ids`.
- `test_list_rows_without_sensitive_fields.py` gana el sufijo sensible `_email` y los prefijos de
  membresías y pagos (el plan pedía ampliarla si solo recorría `members`).
- No se tocan `docs/openapi.json`, `web/`, `DECISIONES.md`, `CLAUDE.md` ni `RUNBOOK.md`.

### S3-B8 · Verde (B8.3 a B8.7)

- Verde: `payments/rules.py` (`build_filters`, `_q_condition`, `date_ceiling`, `_outside`, `check_date_range`, `parse_month`, `month_bounds_utc`, `partial_email`, `is_backdated`, `EMAIL_MASK`, `_MONTH_RE`) y `payments/queries.py` (`list`, `_as_filters`, `_as_row`, `get`, `summary`, `_enrich`, `_partial_name`, `_detail`, `logger`). Router, schemas, service y exceptions quedan como en el Rojo. Ninguna prueba del Rojo cambió.
- Suite sin `perf`, en dos mitades: (1) 1.483 ok, 3 saltadas; (2) 1.929 ok, 1 saltada, 7 deseleccionadas. Total 3.412 ok, 4 saltadas, 0 fallos (3.423 recolectadas: las 3.422 del Rojo más `test_enrich_guard.py`). `test_list_perf.py`: 2 ok (lista 13,7 ms y resumen 10,2 ms con 10.000 pagos). `0014` no hace falta.
- Contrato (P-API): `export-openapi` dos veces, idéntico byte a byte; `npm run gen:api`, `types.contract.test.ts` 5 ok y `tsc --noEmit` limpio en el árbol principal (solo cambia `web/src/core/api/types.ts`).
- Revisión de seguridad: 0 CRITICAL, HIGH o MEDIUM; LOW-1 corregido con prueba (`test_enrich_guard.py`), LOW-2 y LOW-3 aceptados (ver `DECISIONES.md`, "S3-B8").
- Docs: `RUNBOOK.md` §10 "Pagos: lista, detalle y resumen del mes"; `DECISIONES.md` "S3-B8".
- **F6 puede arrancar:** `GET /payments`, `GET /payments/{id}` y `GET /payments/summary` están en `docs/openapi.json` y en `web/src/core/api/types.ts`.

### Evidencia de S3-B8 (B8.6, después del sello; demo 7)

- Antes de los gates: `ruff format --check` (387 archivos), `ruff check` y `mypy src` (93 archivos) limpios; `test_list_perf.py` 2 ok. Gates B8.5 seguidos, sin editar entre ellos, sin `PYTEST_ADDOPTS` y con `ls` previo: (1) `members` con `tests/members/test_router_list.py` y `tests/architecture`: 294 ok, 1 saltada. El primer intento dio 67 errores de setup porque la shell no tenía `TEST_DATABASE_URL`; no se tocó nada y el segundo pasó. (2) El que sella: `payments` con las diez líneas (las nueve del plan más `test_enrich_guard.py`, nacida en la revisión) y `tests/architecture`: 461 ok, 1 saltada (`test_no_sensitive_in_logs`, US-074), sin deseleccionadas, así que corrieron las dos `perf`. Checkpoint `208117e`, encima del merge de F4 `e2fcd08`, que llegó mientras tanto y no toca `types.ts`. Con ese merge, `tsc --noEmit` sigue limpio y `types.contract.test.ts` da 5 ok.
- El api sigue `healthy` y se recargó por el bind: `WatchFiles detected changes in 'src/app/modules/payments/queries.py'` y `Application startup complete`; el contenedor ve `_enrich` y la guarda de LOW-1. En los 20 minutos de la demo el log del api no tiene ningún `ERROR`, y hay 0 sesiones `idle in transaction`. Sin migración: `apex-db-1` sigue en `0011_payments_immutability`.
- Demo por Nginx `:8180`. Los accesos del admin y de un coach se firmaron dentro del contenedor del api y solo quedaron en variables de la shell; el script temporal se borró del contenedor y del scratchpad, igual que el archivo de los accesos.
  - `GET /api/v1/payments?from=2026-10-01T05:00:00Z&to=2026-11-01T05:00:00Z&voided=false` (admin): **200**, `total 3`, de más reciente a más viejo: `d22f1867…` 1.000, `a0be93c6…` 60.000 y `6ac028ed…` 120.000, todos en efectivo, con `registered_by_name` `a•••@ejemplo.local` y `backdated false`. La **suma de `amount_cop` da 181.000**.
  - `GET /api/v1/payments/summary?month=2026-10`: **200** con `Cache-Control: no-store` y `{"month": "2026-10", "total_cop": 181000, "by_method": {"cash": 181000, "nequi": 0, "breb": 0}, "voided_count": 1, "payments_count": 3}`. Cuadra: **`total_cop` 181.000 es igual a la suma de la lista, 181.000**. psql, con la consulta de RUNBOOK §10, da `cash 181000 3 1` y `TOTAL 181000 3 1`.
  - `GET /api/v1/payments/34c5effc…` (el pago anulado en la demo 3 de B5): **200** con `voided true`, `void_reason "Monto mal digitado"`, `voided_by_name "a•••@ejemplo.local"` (parcial), `voided_at 2026-10-25T08:54:11Z`, socio "Demo B4Dos", plan y fechas de la membresía `b21e25b5…`.
  - `GET /api/v1/payments?q=Demo`: **200**, `total 4` (3 de "Demo B4Dos" y 1 de "Demo B4Uno"). No trae ningún campo cifrado (`apx1.`, documento, teléfono, nacimiento ni correo del socio).
  - `GET /api/v1/payments/summary?month=2026-13`: **422** `validation_error`, `field "month"`, mensaje sin el valor.
  - Coach: **200** en la lista, el resumen y el detalle. Sin token: **401** `unauthorized`.
  - `/health` y `/api/v1/health`: 200.

### S3-B9a · Partición de `members/service.py` (sin cambio de comportamiento)

- Rojo (B9a.2): `PRIVATE_HELPERS["members"] = frozenset({"rules", "detail", "changes"})` en
  `tests/architecture/_imports.py`; en `test_no_cross_models.py`,
  `test_los_privados_de_members_son_los_de_b9a` (los tres archivos existen),
  `test_nadie_fuera_de_members_importa_rules_detail_ni_changes` (con control por fuente falsa) y
  `test_members_service_es_fachada_con_all` (`__all__` sin repetidos, contiene la fachada y las
  puras son el mismo objeto que en `rules.py`). Rojo confirmado: 2 fallos (sin archivos y sin
  `__all__`), 14 ok.
- Extracción (B9a.1), mecánica por rangos de líneas y comprobada con `ast.dump`: las 49
  definiciones de primer nivel del `service.py` original están, idénticas, en `service.py` o en
  `rules.py` (ni faltan, ni sobran, ni cambian). A `rules.py` van `MaskField`, `MaskValue`,
  `BIRTH_DATE_MIN`, `PHONE_MIN_DIGITS`, `MASK_TAIL`, `DOCUMENT_MIN_MASKED`, `DOTS`,
  `EMERGENCY_CONTACT_MASK`, `PHONE_DATA_CLASS`, `EMAIL_DATA_CLASS`, `_MENSAJES`, `_invalido`,
  `_normalizado`, `validate_member_input`, `compute_warnings`, `_mask_document`, `_mask_phone`,
  `_mask_email`, `mask`, `QueryPlan`, `PLAN_VACIO`, `_es_documento` y `classify_query`, más
  `LIKE_ESCAPE` re-exportado de `core.search` (con `__all__` propio). En `service.py` quedan
  `DOCUMENT_DATA_CLASS` y `DOCUMENT_ALIVE_INDEX` (solo los usa el código con sesión), el alta, los
  contratos, la búsqueda y la lista; cierra la desviación de B7: `active_ids` ya está en `__all__`.
  `detail.py` (B9b) y `changes.py` (B10) nacen con solo docstring.
- Líneas: `service.py` 531 → 406; `rules.py` 202; `detail.py` 6; `changes.py` 6.
- Importadores verificados (siguen en `service`, sin cambios): `members/router.py`,
  `memberships/{sell,queries,lifecycle}.py`, `payments/queries.py` (`auth` no importa
  `members`); en pruebas, `tests/members/*` y `tests/memberships/test_status_queries_service.py`.
  `grep` de `members.rules|detail|changes`: solo `members/service.py` y la prueba de arquitectura.
- `ruff format`, `ruff check` y `mypy src` (96 archivos) limpios. Regresión sin `perf`:
  `tests/members tests/architecture tests/memberships tests/payments` 1.552 ok, 1 saltada.
- Contrato: `export-openapi` y `git diff --exit-code docs/openapi.json` sin cambios.

### S3-B9b · Rojo (B9b.1 stubs y B9b.2 Rojo; sin migración)

- Línea base: HEAD `ee609f1` (checkpoint de B9a), árbol limpio; suite en dos mitades con
  `-m "not perf"` y `TEST_DATABASE_URL`: (1) `core crypto auth settings cli audit` +
  `test_ci_database.py` y `test_smoke.py` 1.483 ok, 3 saltadas; (2) `members plans memberships
  payments migrations architecture` 1.932 ok, 1 saltada, 7 deseleccionadas. Total **3.415 ok**, 4
  saltadas (el brief decía 3.412: son las 3 pruebas de arquitectura que sumó B9a). `ruff check` y
  `mypy src` (96 archivos) limpios. Durante el Rojo el orquestador fusionó F5 en la rama
  (`5fdf793`, merge `87df3cc`): solo `web/` de memberships y docs del front, sin cruce con este
  slice; la API no cambia.
- Rojo: 3.528 recolectadas (3.520 sin `perf`). Con `-m "not perf"`: **78 fallan**, 3.438 ok, 4
  saltadas, 8 deseleccionadas. Mitad 1: 1 falla (`test_docs_openapi_json_esta_al_dia`, P-API de
  B9b.5), 1.482 ok, 3 saltadas. Mitad 2: 77 fallan (todas de B9b), 1.956 ok, 1 saltada, 8
  deseleccionadas. `tests/members/test_list_perf.py` aparte: 1 falla (el caso nuevo de 5.000 ids,
  500 por el stub), 3 ok. De las 77: 66 son `NotImplementedError` de los stubs (`chip_to_filter`
  23, `detail.get` 20, filtros de `list` 20, `_decrypt_fields` 3; las de router llegan como 500)
  y 11 son aserciones sobre lo que aún no existe: el decorado (`membership_status` `None` en vez
  de `none`, `plan_name` y `membership_end_date` nulos, cero sentencias a
  `memberships.memberships`), el grafo (`perezosas["members"]` vacío) y la puerta única (ninguna
  llamada a `types.reveal`). `ruff format`, `ruff check` y `mypy src` (96 archivos) limpios.
  `db_test` sin residuos: `alembic_version = 0011_payments_immutability`, 0 socios, membresías,
  congelaciones, pagos y planes, 0 usuarios `@test.apex`, 0 sesiones `idle in transaction`, los
  siete triggers en `A` (también tras la `perf` de 5.000, que siembra con SQL dentro de la
  transacción de `session`). `apex-db-1` no se tocó.
  - Verdes de la línea base que pasan a rojo (4): `test_docs_openapi_json_esta_al_dia` (P-API),
    `test_service_list.py::test_las_filas_no_traen_campos_sensibles_ni_enmascarados` y
    `test_router_list.py::test_admin_y_coach_reciben_la_pagina_con_el_contrato` [admin, coach]:
    `CAMPOS_FILA` gana `membership_end_date` y la fila sin membresías pasa de `None` a `"none"`
    (decisión 3).
  - Nuevas: 102 (101 sin `perf`). En rojo 74 + 1 `perf`; verdes sobre los stubs 27 (el stub ya es
    el contrato): `test_chip_to_filter.py` 2 (`MEMBER_CHIPS` y los seis valores de
    `MembershipFilterStatus`), `test_service_list_membership_filters.py` 1 (página vacía sin
    decorar), `test_router_list_filters.py` 14 (seis 422 con `field`, 403 y 401 con filtros, el
    `APIRouter` sin 429, las tres rutas con 429, las demás de `/api/v1/members` sin 429, los
    parámetros y la fila en el OpenAPI), `test_service_get.py` 1 (`CAMPOS_CIFRADOS`),
    `test_router_get.py` 5 (403, 401 y tres 422 de UUID), `test_reveal_single_door.py` 3 (sin
    `bus.decrypt` fuera de `core` y los dos controles) y
    `test_list_rows_without_sensitive_fields.py` 1.
- Verde desechable (revertido; sin migración, solo `db_test`): `chip_to_filter`,
  `_decrypt_fields`, `detail.get` (carga, `mask` sobre lo descifrado con `purpose="mask"`,
  `status_for([id])` perezoso), `_por_membresia` (`member_ids_by_status` perezoso, `= ANY` y
  `<> ALL` con un `uuid[]`), la salida temprana de `none` con `plan_id` y el decorado con un
  `status_for` por página. `tests/members` y `tests/architecture`: 603 ok y 2 fallas de prueba
  (abajo); corregidas, todo verde. `test_list_perf.py`: 4 ok (5.000 ids: `active` 35,1 ms y
  `none` 32,1 ms; búsqueda por documento con 1.000 socios 31,4 ms). Mutación: con `Member.id.in_`
  en lugar de `any_`, el caso de 5.000 falla (`[5000, 5002]` parámetros). Después, `rules.py`,
  `detail.py` y `service.py` restaurados desde copia (sha256 iguales a los del stub).
  - Defectos de prueba encontrados y corregidos: (1) `test_router_get.py` exigía `no-store` en el
    404 (los errores salen por el handler sin la cabecera de la dependencia; misma decisión que
    S3-B5); (2) la prueba de las 121 fichas leía `socio.id` después del 429, cuando el rollback
    de la petición ya había expirado el objeto (`MissingGreenlet`): la ruta se calcula antes del
    bucle.
- Stubs (B9b.1): `members/schemas.py`: `MembershipFilterStatus`,
  `MemberListQuery.membership_status` y `plan_id`, `MemberRowOut.membership_end_date`,
  `MemberDetailOut.plan_name` y `membership_end_date` (por defecto `None`); `members/rules.py`:
  `MemberChip`, `MEMBER_CHIPS`, `MemberChipFilter` (dataclass congelada con `status` y
  `membership_status`) y `chip_to_filter` (con `NotImplementedError`); `members/detail.py`:
  `CAMPOS_CIFRADOS = ENCRYPTED_FIELDS`, `MASK_PURPOSE = "mask"`, `_decrypt_fields` y `get` (con
  `NotImplementedError`); `members/service.py`: re-exporta `get`, `chip_to_filter`,
  `MemberChipFilter` y `MEMBER_CHIPS` en `__all__`, `_por_membresia(session, filters)` (sin
  filtros `None`; con filtros `NotImplementedError`) aplicada en `list`, y `_fila` con
  `membership_end_date`; `members/router.py`: el `APIRouter` con `responses_for(401, 403)`, 429
  por ruta en `POST /members` (`responses_for(409, 429)`) y `GET /members`
  (`responses_for(429)`), `GET /members` con `membership_status` y `plan_id`, y
  `GET /members/{member_id}` (`StaffDep`, `enforce_user_limit(request, "members-detail", ...)`,
  `responses_for(404, 422, 429)`, `no_store` del router). Ningún stub importa
  `memberships.service` (un import sin uso lo rechaza `ruff`; el par perezoso entra en el Verde).
- Archivos de prueba nuevos: `tests/members/test_chip_to_filter.py` (25),
  `test_service_list_membership_filters.py` (20), `test_router_list_filters.py` (20),
  `test_service_get.py` (16), `test_router_get.py` (13) y
  `tests/architecture/test_reveal_single_door.py` (4). Cambiados: `tests/members/_apoyo.py`
  (`CAMPOS_DETALLE` con `plan_name` y `membership_end_date`; `CAMPOS_FILA` nuevo; `ruta_socio`),
  `test_service_list.py` y `test_router_list.py` (usan `CAMPOS_FILA` de `_apoyo` y esperan
  `"none"`), `test_list_perf.py` (+1 `perf`: 5.000 ids),
  `tests/architecture/test_error_codes_per_route.py` (E2: `CON_LIMITE` gana
  `("get", "/api/v1/members/{member_id}")`), `test_user_limits_catalog.py`
  (`CLAVES_SIN_RUTA_TODAVIA` pierde `members-detail`), `test_service_import_graph.py` (+2: el par
  perezoso `members -> memberships` real y permitido, y que vive en `service.py` y `detail.py`),
  `test_list_rows_without_sensitive_fields.py` (+1: `MemberRowOut` con `membership_end_date` y
  sin campos sensibles; `membership_end_date` en la lista de no sensibles) y
  `test_no_cross_models.py` (`FACHADA_MEMBERS` y `PURAS_DE_RULES` ganan los nombres nuevos).
- Front (D35, excepción del slice): `web/src/features/members/schemas.ts` (`memberRowSchema`
  gana `membership_end_date: z.string().nullable().optional().default(null)`;
  `memberDetailSchema` acepta `plan_name` y `membership_end_date` igual), `schemas.test.ts` (+3
  casos y el de `memberDetailSchema` con los dos `null`), `web/src/test/members.tsx`
  (`MemberRowFixture` y `memberDetail` con los campos) y `web/tests/e2e/members.spec.ts` (filas y
  alta con los campos). `npx vitest run src/features/members/schemas.test.ts`: 35 ok;
  `src/features/members` completo: 358 ok; `tsc --noEmit` y `eslint` limpios.
- Importadores de lo tocado: `members/schemas.py` lo importan `members/{router,rules,service,
  detail}.py`, `memberships/sell.py` (`MemberRef`) y pruebas; `members/rules.py` solo
  `members/{service,detail}.py` (ahora importa `MembershipFilterStatus` y `MemberStatusFilter`
  de `schemas`, sin ciclo); `members/detail.py` solo `members/service.py` (importa `models` y
  `schemas`; no importa `service`); `members/service.py` `members/router.py`,
  `memberships/{lifecycle,queries,sell}.py`, `payments/queries.py` y pruebas (solo agrega);
  `members/router.py` solo `main.py` (por `MODULES`); `memberRowSchema` y `memberDetailSchema`
  los usan `features/members/api.ts` y `schemas.test.ts`. Ninguna firma existente cambia.

#### Decisiones de prueba que el Verde debe respetar

1. **`chip_to_filter(chip: str) -> MemberChipFilter`:** los chips `active`, `expiring`,
   `expired`, `frozen`, `pending_payment` y `none` fijan `membership_status` con `status=None`;
   `deleted` fija `status="deleted"` con `membership_status=None`; `MEMBER_CHIPS` en ese orden;
   cualquier otro valor (mayúsculas, espacios, vacío, `inactive`, `cancelled`) es `ValueError`
   con "chip" en el mensaje. El filtro es una entrada válida de
   `MemberListQuery(**asdict(filtro))`.
2. **Filtros de `list` (D22):** `membership_status` y `plan_id` piden el conjunto a
   `memberships.service.member_ids_by_status` con import perezoso (`# lazy: G-03 (members ->
   memberships)`) y lo aplican en la consulta externa con UN parámetro `uuid[]` (`= ANY`; `none`
   es `<> ALL` de los cinco estados); con 5.000 ids la consulta de socios lleva como mucho 20
   parámetros. Solo `plan_id` mira los cinco estados (nunca `none`) por el plan de la membresía
   que DECIDE. `none` con `plan_id` devuelve la página vacía (con el `limit` y el `offset`
   pedidos) sin ninguna sentencia a `members.members` ni a `memberships.memberships`. Un plan
   inexistente da la página vacía. Los filtros se combinan con `q`, `status` (`deleted`,
   `active`, `inactive`), `sort` y la paginación. Ninguna consulta de socios nombra
   `memberships.memberships` (sin `JOIN`).
3. **Decorado:** cada página no vacía llama UNA vez a `memberships.service.status_for` con los
   ids de la página (la prueba espía reemplazando el atributo del módulo `memberships.service`:
   el import perezoso debe resolver `status_for` al llamar): una sentencia a
   `memberships.memberships` y una a `plans.plans` sin filtro de membresía; dos a
   `memberships.memberships` con filtro. Una fila sin entrada lleva `membership_status = "none"`
   y `plan_name` y `membership_end_date` nulos (blueprint B7: "el llamador usa `none`"). Página
   vacía: ninguna sentencia a `memberships.memberships`. El alta (`create`) sigue devolviendo
   `membership_status = None` (fuera del alcance; `test_router_create.py` no cambia).
4. **Índice:** con un filtro de membresía activo, la consulta con `document_idx` sigue usando
   `uq_members_document_idx_alive` (`EXPLAIN` con `SET LOCAL enable_seqscan = off`: con pocas
   filas el barrido sería más barato); el `EXPLAIN` original de `test_list_perf.py` no cambia.
   Listar nunca descifra (cero `decrypt`, también con `q` y filtros).
5. **`detail.get(session, member_id)`:** carga el socio aunque esté dado de baja;
   `MemberNotFound` (404 `member_not_found`) sin descifrar; los cinco campos con `mask` sobre lo
   que devuelve `_decrypt_fields(socio, CAMPOS_CIFRADOS, "mask")` (máscaras de
   `MASCARAS_KNOWN`); en `crypto_ops`, una fila `decrypt` por campo no nulo con
   `purpose='mask'`, el `record_id` del socio, la `data_class` del campo, el actor como
   `user_id`, `result='ok'` y `batch_id` nulo (D20: sin `bus.batch`); ninguna fila con
   `purpose='reveal'` y ninguna fila nueva en `audit.audit_log`; `membership_status`, `plan_name`
   y `membership_end_date` de `status_for([id])` con import perezoso en `detail.py` (sin entrada:
   `none` y nulos); `warnings == []` siempre; claves exactas `CAMPOS_DETALLE`. Las pruebas leen
   la ficha con la sesión vacía (`expunge_all`), como una petición nueva.
6. **`_decrypt_fields(socio, campos, purpose) -> dict[str, object]`:** solo los campos pedidos y
   no nulos, con su tipo (`birth_date` como `date`, `emergency_contact` como `dict`), una fila
   `decrypt` por campo con el `purpose` recibido; sin campos, `{}` y ninguna fila. Es la única
   llamada a `types.reveal` fuera de `core/` (`test_reveal_single_door.py`, D-4) y nadie fuera de
   `core/` llama a `bus.decrypt`.
7. **Router:** `GET /members/{member_id}` para admin y coach (también sobre un dado de baja,
   N-20), 403 `member`, 401 sin token, 404, 422 con `field="member_id"`; `Cache-Control:
   no-store` solo se exige en el 200; ni la respuesta ni los logs (stdout JSON y `caplog`) llevan
   valores de `KNOWN`, máscaras ni `apx1.`. M-2: 120 fichas por minuto por usuario; la 121 da 429
   `rate_limited` con `Retry-After` y el registro `rate limit` con `bucket="members-detail"`; la
   de otro usuario pasa y la lista del mismo usuario sigue (otra cubeta); un 404 también consume
   la cubeta (el límite va antes del service). Los filtros sin `q` no gastan `members-search`.
8. **Contrato:** 429 por ruta en `POST /members`, `GET /members` y `GET /members/{member_id}`, y
   no en el `APIRouter`; `GET /members` declara `membership_status` (seis valores) y `plan_id`
   (`uuid`); `MemberRowOut` tiene exactamente `CAMPOS_FILA`, con `membership_end_date` como
   fecha. Grafo: `perezosas["members"] == {"memberships"}`, `arriba["members"] == set()`, y los
   archivos con la perezosa son exactamente `detail.py` y `service.py`.

#### Desviaciones del Rojo

- Línea base 3.415 y no 3.412 (las 3 pruebas de arquitectura de B9a).
- La fila sin membresía pasa de `membership_status = None` a `"none"` (decisión 3): cambian dos
  pruebas existentes de `test_service_list.py` y `test_router_list.py`; `CAMPOS_FILA` se mueve
  de esas dos pruebas a `_apoyo.py`.
- El caso de 5.000 ids (S3-D71) se siembra con SQL crudo (como B7) para que la `perf` mida la
  lista y no 5.000 altas cifradas; mide el número de parámetros de la consulta de socios además
  del tiempo (con `IN` expandido, 5.000 parámetros no revientan asyncpg: el tiempo solo no
  probaría D22).
- Agregados que el plan no nombraba: `MemberChip`, `MEMBER_CHIPS`, `CAMPOS_CIFRADOS`,
  `MASK_PURPOSE`, `ruta_socio`, `_por_membresia` (nombre del stub; el Verde puede partir `list`
  como quiera mientras respete las decisiones), la prueba de que un 404 consume la cubeta y la de
  `bus.decrypt` en `test_reveal_single_door.py`.
- El 404 de la ficha no exige `no-store` (defecto de prueba 1, misma decisión que S3-B5).
- No se tocan `docs/openapi.json`, `DECISIONES.md`, `CLAUDE.md`, `RUNBOOK.md` ni otros archivos
  de `web/`.

### S3-B9b · Verde (B9b.3 a B9b.6)

- Verde (B9b.3), sin migración: `members/rules.py` (`chip_to_filter` con `_CHIPS_DE_MEMBRESIA`),
  `members/detail.py` (`_decrypt_fields` con `types.reveal` sobre los campos no nulos,
  `_mascaras`, `get` con `select(Member)` sin filtro de baja, `status_for([id])` perezoso y
  `SIN_MEMBRESIA = "none"`), `members/service.py` (`_uuids` = un `uuid[]` ligado,
  `_por_membresia` con `member_ids_by_status` perezoso y `= ANY` / `<> ALL`, salida temprana de
  `none` + `plan_id` en `list`, `_filas` con UNA llamada a `status_for` por página y `_fila` con
  la membresía; `MemberMembership` solo bajo `TYPE_CHECKING`). Las dos perezosas viven en
  `service.py` y `detail.py`. Tamaños: `service.py` 476, `detail.py` 89, `rules.py` 263; todas
  las funciones bajo 50 líneas. El router ya venía cableado del stub.
- Defecto de prueba demostrado y corregido: `test_la_rama_de_documento_sigue_usando_el_indice_
  unico_parcial` fallaba de forma determinista también SIN filtro de membresía (prueba temporal
  borrada: `{}`, `none` y `active` daban `False` en las dos consultas). Causa: `pg_class` de
  `db_test` con `reltuples 0` y los índices engordados por altas revertidas (`uq_…` 58 páginas,
  `ix_members_alive_last_name` 51); con `ANALYZE members.members` las tres variantes usan el
  único parcial. La prueba ahora hace el `ANALYZE` antes de capturar (como `test_list_perf.py`).
  El Verde desechable del QA pasó por el estado que dejó la base en ese momento.
- Revisión (`security-reviewer` sobre `git diff 87df3cc -- api/src`): 0 CRITICAL, 0 HIGH, 0
  MEDIUM, 2 LOW, 1 INFO. LOW-2 corregido con prueba nueva
  (`test_sin_ninguna_membresia_none_trae_a_todos_y_los_demas_a_nadie`); LOW-1 e INFO aceptados
  (detalle en `DECISIONES.md`, "S3-B9b").
- Números: mitad 1 1.483 ok, 3 saltadas; mitad 2 2.034 ok, 1 saltada, 8 deseleccionadas. Total
  **3.517 ok**, 0 fallos, 4 saltadas (3.529 recolectadas). `test_list_perf.py` 4 ok. `ruff
  format`, `ruff check` y `mypy src` (96 archivos) limpios.
- Contrato (B9b.5, P-API con el paso 6 de D35): `export-openapi` dos veces idénticas;
  `npm run gen:api`; `types.contract.test.ts` + `schemas.test.ts` 40 ok; `tsc --noEmit` limpio;
  `src/features/members` 358 ok.
- Docs (B9b.4): RUNBOOK §4 "Filtros por membresía y ficha del socio"; `DECISIONES.md` "S3-B9b".
- **F2 puede arrancar**: `memberRowSchema` ya trae `membership_end_date` y el contrato de
  `GET /members` (`membership_status`, `plan_id`) y `GET /members/{member_id}` está en
  `docs/openapi.json` y `web/src/core/api/types.ts`.

### S3-B9b · Evidencia (B9b.7, demo 6 y 7; después del sello, checkpoint `7d78c05`)

- Gate que selló (sin `PYTEST_ADDOPTS`, `ls` previo de los nueve archivos): `slice-gate.sh
  members` con la lista del plan más `tests/architecture`: `ruff`, `format` y `mypy` limpios;
  **437 ok**, 1 saltada (incluye las 4 `perf` de `test_list_perf.py`).
- api `healthy`, recargado por el bind (el contenedor ya tenía `_uuids` y `_CHIPS_DE_MEMBRESIA`);
  sin migración. Por Nginx `:8180` con accesos del admin y de un coach firmados dentro del
  contenedor del api (script y tokens borrados del contenedor y del scratchpad):
  - Demo 6: `GET /api/v1/members/2b5b6860-…` (socio de CC `1.020.304.417`) → **200** con
    `Cache-Control: no-store`, `document "CC •••• 4417"`, `phone "••• ••• 0417"`, correo con
    inicial y dominio enmascarados, `birth_date "••/••/1990"`, `emergency_contact "Registrado"`,
    `membership_status "none"` (su membresía de B1 está anulada), plan y fin nulos,
    `warnings []`. psql: `SELECT verb, purpose, count(*) … WHERE record_id = <id> GROUP BY 1, 2`
    → `decrypt | mask | 5` (cinco `data_class`, sin lote, `ok`), más `encrypt` 5 e `index` 3 del
    alta; 0 filas `purpose='reveal'` en `crypto_ops`, 0 `action='reveal'` en `audit.audit_log` y
    ninguna fila de auditoría nueva del socio.
  - Demo 7: `GET /members?membership_status=active&plan_id=b6fab314-…` (plan de 120.000) →
    `total 1`, "Demo B4Uno" (`9786ef0a…`) con `active`, "Mensual mvjipju3" y fin `2026-11-24`;
    `membership_status=none` → `total 17` sin "Demo B4Uno" (cuadra con los 17 `none` del resumen
    de B7); `none` + `plan_id` → página vacía (`limit 25`); `pending_payment` → "Demo B4Dos";
    `membership_status=moroso` → **422** `field = membership_status`, sin el valor.
  - Coach → **200** en la ficha de "Demo B4Uno" (`CC •••• 6641`, `active`); id inexistente →
    **404** `member_not_found`; sin token → **401**; `/health` y `/api/v1/health` → 200. Log del
    api sin `ERROR` y sin máscaras, blobs ni documentos en los 15 minutos de la demo.
  - Nota: la respuesta por Nginx lleva `Cache-Control: no-store` dos veces (la de Nginx y la del
    api); es igual en las demás rutas de datos y no cambia el efecto.

### S3-B10 · Rojo (B10.1 stubs y B10.2 Rojo; sin migración)

- Línea base: HEAD `cc8ee69`, árbol limpio. `tests/members tests/architecture
  tests/audit/test_reveal_entry.py tests/core/test_logging_redact.py
  tests/memberships/test_lock_order.py` con `-m "not perf"`: **631 ok, 1 saltada** (la de
  `reveal`), 4 deseleccionadas. `ruff check`, `ruff format --check` y `mypy src` (96 archivos)
  limpios. `apex-db-1` no se tocó; todo contra `db_test`.
- Stubs (B10.1): `members/rules.py` (`ADMIN_ONLY_FIELDS`, `diff_fields`, `ensure_can_change` con
  `NotImplementedError`); `members/schemas.py` (`RevealField`, `PATCH_NOT_NULL`,
  `EmergencyContactOut`, `RevealIn` y `RevealOut` con `extra="forbid"` en la entrada,
  `MemberPatch` cerrado con los diez campos de S3-D46, `data_consent: StrictBool | None` y un
  `field_validator` que rechaza `null` en `PATCH_NOT_NULL`; `EmergencyContactIn.phone` pasa a
  `SafeText`); `members/exceptions.py` (`MemberIsDeactivated` 409 `member_deactivated`,
  `MemberFieldForbidden(field)` 403 `forbidden_field`, `MemberAlreadyDeactivated` 409,
  `MemberNotDeactivated` 409, `ConsentCannotBeWithdrawn` 422 `consent_cannot_be_withdrawn` con
  `field="data_consent"`); `members/detail.py` (`REVEAL_PURPOSE` y `reveal(session, member_id,
  field, *, ip)` con `NotImplementedError`); `members/changes.py` (eventos `MemberUpdated(member_id,
  changed_fields: tuple[str, ...])` y `MemberDeactivated(member_id)`; `update`, `deactivate` y
  `reactivate` con `NotImplementedError`); `members/service.py` re-exporta todo en `__all__`;
  `members/router.py` cableado entero: `POST /members/{member_id}/reveal` (`StaffDep`, las tres
  `enforce_user_limit` `members-reveal`, `-hour` y `-day`, `ip` de `client_ip` con
  `app.state.trusted_proxies`, `responses_for(404, 422, 429)`), `PATCH /members/{member_id}`
  (`StaffDep`, `members-write`, `role=principal.role`, `responses_for(403, 404, 409, 422, 429)`),
  `DELETE /members/{member_id}` (204, `AdminDep`, `response_class=Response`,
  `responses_for(404, 409, 422)`) y `POST /members/{member_id}/reactivate` (`AdminDep`,
  `responses_for(404, 409, 422)`). El aviso `reveal volume` NO va en el stub (lo hace el Verde).
  `auth/models.py`: solo el docstring apunta a `test_no_physical_delete.py`.
- Cubetas y catálogo (E2): `USER_LIMITS`, `user_limits_from`, las `USER_REVEAL_*` de `Settings` y
  `.env.example` ya existían desde W0-2: **no se tocó `config.py`, `.env.example`, `ci.yml` ni
  `test_compose_config.sh`** (el `ci.yml` sigue sin las `USER_*`: eso es de V4, E15).
  `test_error_codes_per_route.py`: `CON_LIMITE` gana `("patch", "/api/v1/members/{member_id}")` y
  `("post", "/api/v1/members/{member_id}/reveal")`. `test_user_limits_catalog.py`:
  `CLAVES_SIN_RUTA_TODAVIA = frozenset()` y prueba nueva de las tres ventanas en la ruta de
  `reveal` con sus topes por defecto.
- Pruebas (archivos nuevos y cambiados; recolectadas / en rojo sobre los stubs / motivo):
  - `tests/members/test_member_patch_rules.py` (nuevo): 49 / 33 (`NotImplementedError` de
    `diff_fields` 25 y `ensure_can_change` 8). Verdes sobre el stub 16: `ADMIN_ONLY_FIELDS` y los
    15 de `MemberPatch` (diez campos, seis claves ajenas, cinco `null` prohibidos, `null` en
    opcional, `StrictBool`, NUL en `emergency_contact.phone`).
  - `tests/members/test_service_reveal.py` (nuevo): 24 / 24 (`NotImplementedError: reveal`; el de
    la auditoría rota llega como `NotImplementedError` en lugar de `AuditoriaRota`).
  - `tests/members/test_router_reveal.py` (nuevo): 24 / 14 (`NotImplementedError: reveal` por el
    transporte; el del commit roto, `[] == ['reveal']`: no hubo `decrypt`). Verdes 10: seis 422
    `field="field"`, clave de más, 403 `member`, 401 y 422 de UUID.
  - `tests/members/test_service_update.py` (nuevo): 31 / 31 (`NotImplementedError: update`; el de
    la carrera, dos `NotImplementedError`).
  - `tests/members/test_router_update.py` (nuevo): 26 / 14 (`update`). Verdes 12: 403 `member`,
    401 y los diez 422 de schema (apellido vacío y en blanco, sexo, `document`/`first_name` nulos,
    `status`, `deleted_at`, `data_consent_at`, `notes`, NUL en el contacto). En rojo los 422 que
    decide el service (`birth_date` futura, `data_consent=false`).
  - `tests/members/test_service_deactivate.py` (nuevo): 15 / 15 (`deactivate`/`reactivate`; las
    dos de candado, "no quedó esperando el candado del socio").
  - `tests/members/test_router_deactivate.py` (nuevo): 14 / 7 (`deactivate`/`reactivate`). Verdes
    7: 403 coach y `member` en baja y en reactivar, 401 y 422 de UUID en las dos.
  - `tests/audit/test_reveal_entry.py` (reescrito con `make_member` y `service.reveal`, sin
    `uuid4()`): 1 / 1.
  - `tests/core/test_logging_redact.py` (+1, `reveal` real de los cinco campos, T8 de US-018):
    18 / 1.
  - `tests/memberships/test_lock_order.py` (+2, `sell` frente a `deactivate` en los dos órdenes):
    9 / 2.
  - `tests/architecture/test_no_sensitive_in_logs.py` (la de `reveal` deja de saltarse: login de
    coach, alta, ficha, `reveal` de documento y teléfono, `PATCH` del teléfono): 2 / 1.
  - `tests/architecture/test_no_physical_delete.py` (nuevo; `git rm` de
    `test_no_physical_delete_users.py`): 4 / 0. `test_events_without_pii.py` (+3): 7 / 0.
    `test_user_limits_catalog.py` (+1): 7 / 0. `test_no_cross_models.py`
    (`FACHADA_MEMBERS`, `PURAS_DE_RULES`, `DE_DETAIL`, `DE_CHANGES`): 16 / 0.
    `test_error_codes_per_route.py`: 8 / 0.
  - Apoyo: `tests/members/_apoyo.py` (`ruta_reveal`, `ruta_reactivar`, `auditoria_del_socio`,
    `descifrar`, `peticion`) y `tests/members/conftest.py` (`ops_tras_el_rollback`).
- Conteo: 143 pruebas nuevas o cambiadas en rojo, más `tests/core/test_openapi_export.py::
  test_docs_openapi_json_esta_al_dia` (P-API de B10.5). Corrida del slice
  (`tests/members tests/architecture` + los tres de otros módulos + `test_openapi_export.py`):
  **144 fallan, 686 ok**, 4 deseleccionadas; ninguna verde de la línea base pasó a rojo salvo la
  de `openapi.json`. `ruff check`, `ruff format --check` y `mypy src` (96 archivos) limpios con
  los stubs. `db_test` sin residuos: `alembic_version = 0011_payments_immutability`, 0 socios,
  membresías, congelaciones, pagos, planes, usuarios `@test.apex`, `crypto_ops` y `crypto_keys`;
  0 sesiones `idle in transaction`; los siete triggers en `A`.
- Verde desechable (revertido; sha256 de los siete archivos de `members/` iguales al stub):
  `diff_fields`, `ensure_can_change`, `reveal` (con `_decrypt_fields(..., "reveal")` y
  `audit.record`), `update`, `deactivate`, `reactivate` (todos con `lock_member` primero) y el
  aviso `reveal volume` en el router. `tests/members tests/architecture` + los tres de otros
  módulos: **824 ok**. Mutación: sin `lock_member` en `changes.py` caen las cuatro pruebas de
  candado (`update`, venta durante la baja, baja durante la venta, reactivar) y la de
  `test_lock_order` en orden `venta-primero`.
  - Defectos de prueba encontrados con el Verde y corregidos: (1) `FrozenClock.advance` solo
    acepta `days`, `hours` y `minutes` (la de 201 en una hora usa `minutes=1`); (2) la fábrica no
    fija `sex`: el PATCH "sin cambios" lo siembra con `sex="f"`; (3) `socio.id` leído después de
    un rollback o de una petición con error expira el objeto (`MissingGreenlet`): las pruebas de
    router capturan `socio_id` justo después de `make_member` y la del candado de `update`
    también; (4) esperar "cualquier candado asesor" era ambiguo (la cadena de auditoría también
    lo es: sin `lock_member` la baja esperaba igual por la cadena); la espera ahora busca la
    llave exacta de `hashtextextended(<uuid>, 0)` en `pg_locks` (`classid`/`objid`).

#### Decisiones de prueba que el Verde debe respetar

1. **`reveal`:** carga el socio sin filtro de baja (N-20) o `MemberNotFound` sin auditar ni
   descifrar; `_decrypt_fields(socio, [field], "reveal")` (única puerta, D-4) y
   `core.audit.record(action="reveal", table_name="members.members", record_id=id, before=None,
   after={"field": field, "ip": ip}, subject_member_id=id)` en la misma transacción, sin
   `commit()` y sin evento. `RevealOut.value`: texto tal como se guardó (documento, teléfono,
   correo), `birth_date` como `AAAA-MM-DD`, `emergency_contact` como `EmergencyContactOut`
   (`relationship` nulo si no hay); un campo nulo da `None`, audita y no deja `decrypt`. Las
   pruebas de la auditoría rota parchean `app.core.audit.append_entry` (debe llamarse vía
   `audit.record`).
2. **Router de `reveal`:** las tres `enforce_user_limit` antes del service (el 429 nombra la
   cubeta en el registro `rate limit`); después, `usage("members-reveal-hour", str(user_id),
   window_s=<ventana>)` y, si pasa de la mitad del tope horario vigente (`app.state.user_limits`),
   `logger.warning("reveal volume", extra={"user_id": str(user_id), "count": n})` con `n` que
   incluye la petición actual (101 con 100 previos; con 99 previos no avisa). La IP sale de
   `client_ip` con `app.state.trusted_proxies`.
3. **`update`** (orden que usó el Verde desechable; las pruebas solo exigen que ningún error
   deje cambios parciales y que `lock_member` vaya antes de leer): `ensure_can_change(patch.model_fields_set, role)` → `data_consent is
   False` → `ConsentCannotBeWithdrawn` → `lock_member` → carga (o `MemberNotFound`) → baja →
   `MemberIsDeactivated` → reglas del alta (`birth_date` entre 1900 y hoy, documento, teléfono y
   correo que no se normalizan a vacío: `MemberValidationError` con `field`) → `diff_fields`
   contra lo descifrado con `mask` → pre-chequeo del documento entre vivos (sin el propio socio)
   → asignación con `Secret.from_plain` → flush. **Sin cambios efectivos no hay `UPDATE`,
   auditoría ni evento** (se mide con `contador_de_consultas`). `data_consent=true` solo fija
   `data_consent_at` con el reloj si estaba nula. Respuesta: la ficha de `detail.get` con
   `warnings = ["data_consent_missing"]` si `data_consent_at` sigue nula.
4. **Traducción de `uq_members_document_idx_alive` en un UPDATE (punto delicado, demostrado con el
   Verde desechable):** si las asignaciones se hacen FUERA del `begin_nested()` y el flush falla
   dentro, la consulta siguiente (`id_by_document` para `existing_id`) dispara
   `PendingRollbackError`; y tras el rollback del savepoint `socio.id` está expirado
   (`MissingGreenlet`). Lo que funcionó: asignar DENTRO del `begin_nested()` y leer el id antes.
   La carrera exige `existing_id` = el ganador. Ojo también al ciclo de imports: `id_by_document`
   vive en `service.py`, que importa `changes.py`.
5. **`MemberUpdated.changed_fields`:** tupla ordenada de nombres de columna cambiados, sin
   `*_idx` (`("first_name", "phone")`; `("deleted_at", "status")` al reactivar). La auditoría
   `update` del hook lleva solo esas columnas y sus índices (`phone`, `phone_idx` como `"***"`).
6. **`deactivate`/`reactivate`:** `lock_member` primero (las pruebas miran `pg_locks` con la llave
   exacta); baja: `deleted_at = now_utc()`, `status = "inactive"`, `MemberDeactivated`; repetida
   `MemberAlreadyDeactivated`; no toca membresías ni pagos. Reactivar: `MemberNotDeactivated` si
   está vivo; documento tomado por otro vivo → `MemberDocumentDuplicated(existing_id)` (por
   `document_idx`, sin descifrar) y la fila sigue dada de baja; si no, limpia ambos, audita,
   emite `MemberUpdated(("deleted_at", "status"))` y devuelve la ficha.
7. **Orden de candados:** `lock_member` → `FOR SHARE` del plan → fila de la membresía → fila del
   pago → cadena de auditoría (hook). `members` nunca pide los de `memberships`; `sell` frente a
   `deactivate` se serializa en el candado del socio (la venta que entra después recibe 422
   `member_inactive`; si gana la venta, su `insert` de auditoría tiene `seq` menor que el
   `update` de la baja).
8. **`ops_tras_el_rollback`** (conftest de `members`) se pide ANTES que `api_prueba` en la firma:
   borra los `decrypt` que el rollback confirma en otra conexión; `lock_timeout` de 5 s evita una
   espera infinita si alguien cambia el orden.

#### Desviaciones del plan y hallazgos

- `test_events_without_pii.py` no es nuevo (nació en B6); se amplió (+3).
- El día completo de `reveal` (601) se prueba con 599 marcas de `ratelimit.record` en la misma
  cubeta más dos peticiones reales; el minuto (31) y la hora (201, con `reloj.advance(minutes=1)`
  cada 30) van con peticiones reales.
- "Fallo simulado del commit → 500 sin el valor": el `before_commit` que falla se registra con
  `insert=True` para que corra antes de que `oplog` vuelque su buffer; así el `decrypt` sobrevive
  al rollback y la prueba lo exige (en el stub no hay `decrypt`: es la aserción que la deja roja,
  porque el `NotImplementedError` también da 500).
- `test_no_physical_delete.py` cubre además auditoría y llaves (regla de datos 4).
- Blueprint B10 con nota de corrección (ver `DECISIONES.md`, "S3-B10"): siete puntos superados
  por el plan y la revisión de seguridad.
- No se tocaron `web/`, `docs/openapi.json`, `types.ts`, `config.py`, `.env.example` ni `ci.yml`.

#### Gates de B10.6 (`ls` confirmado de cada archivo)

1. `slice-gate.sh audit tests/audit/test_reveal_entry.py` — existe.
2. `slice-gate.sh core/logging tests/core/test_logging_redact.py` — existe.
3. `slice-gate.sh memberships tests/memberships/test_lock_order.py` — existe.
4. Para sellar: `slice-gate.sh members tests/members/test_service_reveal.py
   tests/members/test_router_reveal.py tests/members/test_member_patch_rules.py
   tests/members/test_service_update.py tests/members/test_router_update.py
   tests/members/test_service_deactivate.py tests/members/test_router_deactivate.py
   tests/architecture/test_no_physical_delete.py tests/architecture/test_no_sensitive_in_logs.py
   tests/architecture/test_events_without_pii.py` — los diez existen;
   `tests/architecture/test_no_physical_delete_users.py` ya no existe (`git rm`).

### S3-B10 · Verde (B10.3 a B10.6)

- Verde (B10.3): `rules.py` (`diff_fields` con documento, teléfono y correo normalizados y el
  contacto como mapeo sin nulos; `ensure_can_change` por presencia, `ADMIN_ROLE`; nueva pura
  `validate_member_patch`); `detail.py` (`reveal` con `_decrypt_fields(socio, [field],
  "reveal")` y `audit.record(action="reveal", table_name="members.members", after={field, ip},
  subject_member_id)`, sin evento ni commit; `_revelado`); `changes.py` (`update`, `deactivate`,
  `reactivate`, `_bloquear_y_cargar` con `lock_member` + `populate_existing`, `_escribir` con la
  traducción de `uq_members_document_idx_alive` dentro de `begin_nested()`, y `id_by_document`
  mudado desde `service.py`, S3-D84); `router.py` (aviso `reveal volume`, S3-D88). Decisiones
  S3-D84 a S3-D88 en `DECISIONES.md`. Funciones de menos de 50 líneas; `service.py` 486 líneas,
  `changes.py` 280.
- Hallazgo del Verde: el pre-chequeo del documento iba después de descifrar; las dos pruebas del
  409 dejaban 3 filas `decrypt | mask` confirmadas (sobreviven al rollback, D19) y en la corrida
  conjunta caían `test_la_lista_nunca_descifra`,
  `test_active_ids_emite_una_sola_consulta_y_no_descifra` y
  `test_sin_q_no_hay_operaciones_de_cripto_y_con_q_solo_indices` (verdes por separado). Se movió el pre-chequeo antes del descifrado (S3-D85); `db_test` queda con 0 filas
  en `crypto_ops` tras cada archivo.
- Revisión de seguridad (`security-reviewer`, `git diff cc8ee69 -- api/src`): 0 CRITICAL, 0
  HIGH, 0 MEDIUM; LOW-1 (`SafeText` en documento y teléfono) y LOW-2 (error opaco del contacto
  ilegible) corregidos con dos pruebas nuevas en archivos del gate
  (`test_member_patch_rules.py` +4, `test_service_reveal.py` +1, esta con
  `ops_tras_el_rollback` antes de `session`); INFO-1 documentado en RUNBOOK §4; INFO-2 e INFO-3
  aceptados (DECISIONES).
- Corridas sin `--cov`: `tests/members tests/architecture` + `test_reveal_entry.py`,
  `test_logging_redact.py` y `test_lock_order.py`: 824 ok antes de la revisión. Mitades de la
  suite tras la revisión: `tests/core tests/crypto tests/auth tests/settings tests/cli
  tests/audit tests/test_ci_database.py tests/test_smoke.py` **1484 ok, 3 saltadas** (NTFS);
  `tests/members tests/plans tests/memberships tests/payments tests/migrations
  tests/architecture` **2231 ok**, 8 deseleccionadas (`perf`). `ruff check`, `ruff format
  --check` y `mypy src` (96 archivos) limpios.
- Contrato (B10.5, P-API): `export-openapi` dos veces idéntica (sha256 `7c9590a8…`; +769/-59 en
  `docs/openapi.json`, cuatro rutas nuevas y `RevealIn`, `RevealOut`, `EmergencyContactOut`,
  `MemberPatch`); `npm run gen:api` (+456 en `web/src/core/api/types.ts`, único cambio en
  `web/`); `npx vitest run src/core/api` 7 archivos, 158 ok; `npx tsc --noEmit` limpio.
  `test_docs_openapi_json_esta_al_dia` verde. Ningún esquema `.strict()` del front gana campos.
- Docs (B10.4): RUNBOOK §4 "Revelar, editar, dar de baja y reactivar" (los tres cupos, qué es
  `reveal volume`, recuperar a un dado de baja, psql); `BRECHAS.md` §10 ("Dado de baja",
  "Reactivar" y campos sensibles en la edición, con `// DESIGN-GAP:` para el front).
- Gates (B10.6), en orden y con `ls` previo de cada archivo: ver el bloque de evidencia.

### S3-B10 · Evidencia (B10.6 y B10.7, demo 6; después del sello, checkpoint `4b4ce60`)

- Gates (sin `PYTEST_ADDOPTS`, `ls` previo de cada archivo), seguidos y sin editar entre uno y
  otro: (1) `slice-gate.sh audit tests/audit/test_reveal_entry.py` **286 ok**; (2)
  `slice-gate.sh core/logging tests/core/test_logging_redact.py` **303 ok**; (3)
  `slice-gate.sh memberships tests/memberships/test_lock_order.py` **294 ok**; (4) el que sella,
  `slice-gate.sh members` con los diez archivos del plan **473 ok**. `ruff`, `format` y `mypy`
  limpios en los cuatro (incluyen `tests/architecture`).
- api `healthy`, recargado por el bind (WatchFiles); sin migración ni reconstrucción. Por Nginx
  `:8180` con accesos del admin y del coach desechable firmados dentro del contenedor del api
  (script borrado del contenedor y del scratchpad; tokens solo en variables de la shell; no se
  tocó ninguna contraseña). Socio de demo propio "Demo B10Revelar" (`d7345990-…`, CC de 10
  dígitos al azar, teléfono y correo de prueba); queda activo al final:
  - `POST /members` (admin) → 201, `document "CC •••• <4 últimos>"`.
  - `POST /members/{id}/reveal {"field":"document"}` (admin) → **200** con `Cache-Control:
    no-store` y el valor igual al sembrado. psql: una fila `reveal` (seq 900, `user_id` = admin,
    `after = {"ip": "172.30.0.128", "field": "document"}`, sin el valor; la IP es la del host
    vista por Nginx) y una `decrypt | reveal | member.document` en `crypto_ops`.
  - `PATCH {"phone": ...}` (coach) → **200**; `phone_idx` distinto; la fila `update` (seq 901,
    `user_id` = coach) lleva solo `phone` (blob) y `phone_idx` (`***`).
  - `PATCH {"document": <el mismo>}` (coach) → **403** `forbidden_field`, `field="document"`,
    sin el valor en el cuerpo.
  - `DELETE /members/{id}` (admin) → **204**; `GET` → `status "inactive"` y `deleted_at`;
    auditoría `update` con `status` y `deleted_at` (seq 902). `DELETE` con el coach → **403**.
  - `POST /members/{id}/memberships` sobre el dado de baja → **422** `member_inactive`; `PATCH`
    sobre él → **409** `member_deactivated`.
  - `POST /members/{id}/reactivate` (admin) → **200**, `status "active"`, `deleted_at null`
    (seq 903).
  - Ninguna fila de auditoría del socio contiene el documento ni el teléfono nuevo en claro.
    `$DC logs --since 30m api` (306 líneas): 0 apariciones del documento, del teléfono viejo y
    del nuevo, 0 `apx1.`, 0 `ERROR`.

### S3-B11 · Rojo (B11.1 stubs y B11.2 Rojo; sin migración)

- Rama `feat/sprint-03-membresias-pagos`, HEAD `8241f8b`, árbol limpio al empezar. Sin commit. No se tocó `apex-db-1`, `web/`, `docs/openapi.json` ni `types.ts`.
- **Línea base** (antes de tocar nada; `tests/plans tests/memberships tests/payments tests/architecture -q -m "not perf"`, `TEST_DATABASE_URL` en `127.0.0.1:5443`): 1.524 ok, 4 deseleccionadas, 0 fallos.

**B11.1 · Stubs** (`ruff format --check`, `ruff check` y `mypy src` (96 archivos) limpios con los stubs):
- `plans/service.py`: `search_ids(session, q) -> set[UUID]` (en `__all__`, docstring del módulo).
- `memberships/queries.py`: `list_for_member(session, member_id, page, *, q=None) -> Page[MembershipOut]`; `memberships/service.py` lo re-exporta (import y `__all__`): el router llama a `service.list_for_member`, así que la fachada también cambia (el plan solo nombra `queries.py`).
- `payments/queries.py`: `list_for_member(session, member_id, voided, page, *, q=None) -> Page[PaymentRow]`; `payments/service.py` lo re-exporta (import, `__all__` y docstring).
- `memberships/router.py`: `GET /members/{member_id}/memberships` (`member_memberships`), declarada antes de `/renewal-preview`; `payments/router.py`: `GET /members/{member_id}/payments` (`member_payments`, con `voided: bool | None = None`). Las dos con el path completo, `StaffDep`, `responses_for(404, 422)`, `q: SearchQuery = None` y `Annotated[PageParams, Depends()]`. No llaman a `enforce_user_limit` ni entran en `CON_LIMITE` (D28: `q` no busca personas).
- Los tres stubs lanzan `NotImplementedError("S3-B11: ...")`.

**B11.2 · Rojo.** 85 en rojo y 1.544 ok (1.629 recolectadas sin `perf` = 1.524 de la línea base más 105 nuevas). Los 85 fallan por `NotImplementedError` de los stubs: 32 en `payments.list_for_member`, 31 en `memberships.list_for_member` y 22 en `plans.search_ids`. Ninguno falla por import, fixture o aserción. Las rutas propagan la excepción por `ASGITransport`.

Por archivo:
- `tests/plans/test_search_ids.py`: 22 en rojo y 1 ok. Tildes y mayúsculas plegadas (9 casos), incluye dados de baja, devuelve `set[UUID]`, sin coincidencias, comodines `%` y `_` literales (4), sin `q` o en blanco da `set()` sin ninguna sentencia (4), una sola sentencia y `crypto_ops` intacta tras el commit. Queda ok `__all__`.
- `tests/memberships/test_member_memberships_service.py`: 23 en rojo y 1 ok. Orden `start_date DESC, id` con desempate por id (C y E empiezan el mismo día); incluye anuladas; solo las del socio; estado efectivo (A `active` guardada sale `expired`, C `active` guardada sale `frozen`); `MembershipOut` con claves exactas, congelaciones en orden con `days` y plan dado de baja; `paid_cop` sin anulados; dado de baja devuelve las suyas; inexistente da `MemberNotFound` 404, también con `q`; socio sin membresías; página y total; `q` por nombre de plan con tildes, incluido un plan dado de baja (4); `q` sin otro socio; `q` en blanco (2); `q` sin coincidencias no consulta pagos ni congelaciones; `q` llama a `plans.search_ids` una vez y nunca a `members.search_ids` (espía); sin `q` no busca planes; congelaciones, sumas y planes en una sentencia cada uno y socios a lo sumo dos (`contador_de_consultas`); el número de sentencias no crece entre 1 y 5 filas (prueba de N+1); sin `decrypt` ni `index`. Queda ok `__all__`.
- `tests/memberships/test_member_memberships_router.py`: 8 en rojo y 8 ok. En rojo: 200 admin y coach con forma paginada, `no-store`, orden y estados; `limit` y `offset`; `limit=200`; `q` por plan; dado de baja 200; inexistente 404 `member_not_found`; 61 búsquedas seguidas dan 200 y `GET /members?q=` sigue en 200 (sin 429). Ok desde ya, porque el stub ya fija el contrato: 422 con `field` para `limit` 0 y 201, `offset` -1, `q` de 101 y `q` con NUL (5); `member_id` no UUID; 403 `member` y 401; OpenAPI (`{200,401,403,404,422,500,503}` sin 429, tag, parámetros `limit`, `offset` y `q`, `Page_MembershipOut_`).
- `tests/payments/test_list_for_member.py`: 23 en rojo y 1 ok. Tres pagos en dos membresías (uno anulado) en orden descendente; `voided=false` devuelve dos; `voided=true` devuelve el anulado; contrato `CAMPOS_ROW` con `backdated` (solo p3, registrado 50 h después) y correo parcial; dado de baja; inexistente 404 (también con `q` y `voided`); sin pagos; página y total; `q` por referencia exacta sin distinguir mayúsculas (3; el pago de Pedro con la misma referencia no aparece); `q` parcial o de persona no encuentra nada (6); `q` en blanco (2); `q` con `voided`; nunca llama a `members.search_ids`; el número de sentencias no crece; sin `decrypt` ni `index`. Queda ok `__all__`.
- `tests/payments/test_router_member_payments.py`: 9 en rojo y 8 ok. En rojo: 200 admin y coach (contrato, `no-store`, `backdated`); `voided` (2); `q` exacta; `limit` y `offset`; dado de baja; inexistente 404; sin 429 (61 seguidas). Ok desde ya: 422 (`limit` 0 y 201, `offset` -1, `voided=quizas`, `q` de 101), `member_id` no UUID, 403 y 401, y OpenAPI (sin 429, tag `payments`, parámetros `limit`, `offset`, `q` y `voided`, `Page_PaymentRow_`).
- Arquitectura: `test_list_routes_use_page_params.py` amplía el conjunto con las dos rutas anidadas y suma `test_las_listas_anidadas_de_la_ficha_paginan_y_aceptan_q` (`PageParams`, parámetros de query exactos, `limit` de 1 a 200 y `q` con `maxLength` 100). Está en verde con los stubs, porque es una prueba de forma. `test_list_rows_without_sensitive_fields.py` (ya recorre `/api/v1/members...` y recoge las dos rutas nuevas) y `test_service_import_graph.py` siguen en verde sin cambios. `test_error_codes_per_route.py` y `test_user_limits_catalog.py` también siguen en verde sin tocar `CON_LIMITE`.

**Verde desechable (regla S3-B1).** Implementé solo `plans.search_ids`, `memberships.list_for_member` y `payments.list_for_member`. Resultado: los cinco archivos 104 ok, y `tests/plans tests/memberships tests/payments tests/architecture` dio 1.629 ok. Siete pruebas dieron error de setup, pero solo porque esa corrida usó `-p no:logging` (sin `caplog`); sin esa opción pasaron (24 ok). No apareció ningún defecto de prueba. Después revertí copiando los stubs guardados en el scratchpad y lo comprobé por sha256: los siete archivos de `src` quedaron idénticos a los stubs (`plans/service.py` `d3491445…`, `memberships/queries.py` `99bdf36a…`, `payments/queries.py` `5e58304c…`, `memberships/service.py` `181d52d6…`, `memberships/router.py` `0ef0186a…`, `payments/service.py` `1b0fbfe0…`, `payments/router.py` `14897cf2…`). Ojo: `git checkout --` no sirve para revertir, porque los stubs no están confirmados.

**`db_test` sin residuos** tras todas las corridas: 0 socios, planes, membresías, congelaciones, pagos y filas de `crypto_ops`; 0 sesiones `idle in transaction`; los siete triggers en `A`.

**Desviaciones.**
- Las fachadas `memberships/service.py` y `payments/service.py` re-exportan `list_for_member`. El plan solo nombra `queries.py`, pero el router solo habla con `service.py` (regla de módulos 1).
- Hay 19 pruebas nuevas en verde en el Rojo (OpenAPI, 422, 403/401 y `__all__`), más la nueva de arquitectura: el contrato lo fija el stub. El comportamiento queda en rojo.
- No encontré ningún error del blueprint: `responses_for(404)` del blueprint y `responses_for(404, 422)` del plan dan el mismo OpenAPI, porque el gancho convierte el 422 de FastAPI. Por eso no hay entrada "S3-B11" en DECISIONES.

**Lo que el Verde debe saber.**
- `memberships/queries.py` queda en 700 líneas con el stub; el tope es 800 por archivo y 50 por función (`test_file_and_function_size`). Mi verde desechable de `list_for_member`, con todo en línea, rozó las 50 líneas: hay que partirlo, por ejemplo en `_member_outs(session, filas, hoy, dias)`. No reusar `membership_out` (consulta nombres y suma por membresía: daría N+1 y rompe `test_las_sentencias_no_crecen_con_las_filas`). Lo que sirve es una sentencia por vecino: `members.names_for`, `plans.names_for`, `payments.sums_not_voided` y `_freeze_rows_for`, con el estado de `compute_status` y las ventanas de esas filas.
- El orden importa: `members.ensure_exists(include_deleted=True)` va antes de `q`, porque el 404 gana aunque `q` no coincida. Con `q` no vacío, `plans.search_ids(session, q)`; si da vacío, la página vacía sale sin consultar pagos ni congelaciones. El filtro puede ser `Membership.plan_id == _ids_param(ids)`. Sin `q`, o con `q` en blanco, no se llama a `search_ids` (lo vigila un espía). Se ordena por `start_date.desc(), id` (`paginate` agrega el id ascendente).
- `plans.search_ids`: `clean_query`, `sql_fold(literal(contains_pattern(t), Text))` e `ilike(..., escape=LIKE_ESCAPE)` sobre `sql_fold(Plan.name)`, SIN filtrar `deleted_at`. Sin término no envía ninguna sentencia.
- `payments.list_for_member`: `ensure_exists(include_deleted=True)` y después `build_filters(PaymentFilters(q=q, voided=voided, member_id=member_id))` con `member_ids_from_q` vacío, así `q` queda en `lower(reference) = lower(q)` (recortado). Luego `paginate` con `paid_at DESC, id DESC` y `_enrich`/`_as_row`. NUNCA `members.search_ids`: lo vigila un espía y también la cuenta de filas `index` en `crypto_ops`.
- Las rutas no llevan límite: no se agregan a `CON_LIMITE` ni llaman a `enforce_user_limit` (lo fijan las pruebas de 61 búsquedas y el OpenAPI sin 429).
- P-API (B11.4) sigue pendiente: `export-openapi` dos veces, `gen:api`, `types.contract.test.ts`.

**Gates B11.5** (`ls` hecho, los seis archivos existen): `api/tests/plans/test_search_ids.py`, `api/tests/plans/test_service_list.py`, `api/tests/payments/test_list_for_member.py`, `api/tests/payments/test_router_member_payments.py`, `api/tests/memberships/test_member_memberships_service.py` y `api/tests/memberships/test_member_memberships_router.py`.
1. `slice-gate.sh plans tests/plans/test_search_ids.py tests/plans/test_service_list.py`
2. `slice-gate.sh payments tests/payments/test_list_for_member.py tests/payments/test_router_member_payments.py`
3. El que sella: `slice-gate.sh memberships tests/memberships/test_member_memberships_service.py tests/memberships/test_member_memberships_router.py`

### S3-B11 · Verde (B11.3 a B11.5, y el ciclo de Alembic de B11.6 sobre `db_test`)

- Verde (B11.3): `plans/service.py` `search_ids` (`clean_query`, `sql_fold(literal(contains_pattern(t), Text))`, `ilike` con `LIKE_ESCAPE` sobre `sql_fold(Plan.name)`, sin `deleted_at`; sin término `set()` sin sentencia). `memberships/queries.py` `list_for_member` (`ensure_exists(include_deleted=True)` → `q` con `plans.search_ids`, vacío da la página vacía → `Membership.plan_id = ANY(:ids)` → `ORDER BY start_date DESC, id` → `paginate`) y `_member_outs` (una sentencia por vecino y una de congelaciones; sin `membership_out`). `payments/queries.py` `list_for_member` (`ensure_exists(include_deleted=True)` y `build_filters(PaymentFilters(q, voided, member_id))` sin ids de socios) y `_page_of`, la cola compartida con `list`. Funciones de menos de 50 líneas; `memberships/queries.py` 750 líneas (no hizo falta un privado nuevo).
- Corridas sin `--cov`: los cinco archivos del slice más `tests/architecture` **390 ok**; `tests/plans tests/memberships tests/payments tests/members -m "not perf"` **1.859 ok**, 8 deseleccionadas. `ruff check`, `ruff format` y `mypy src` (96 archivos) limpios.
- Contrato (B11.4, P-API): `export-openapi` dos veces idéntica (sha256 `54ad17e4498ed6e9372c4c8b86b438df40ea073293bf0ffa2905fdb6688b16e5`; +320 en `docs/openapi.json`, dos rutas nuevas, `Page_MembershipOut_` y `Page_PaymentRow_`). Frente a la base del sprint (`d65056e`): 31 → 53 operaciones, **22 nuevas** y 0 quitadas, más `membership_status` y `plan_id` en `GET /members`; cuadra con el plan. `npm run gen:api` (+193/-1 en `web/src/core/api/types.ts`, único cambio en `web/`); `npx vitest run src/core/api` 7 archivos, **158 ok**; `npx tsc --noEmit` limpio; `tests/core/test_openapi_export.py` (incluye `test_docs_openapi_json_esta_al_dia`) 6 ok.
- Docs: RUNBOOK §4 "Pestañas de la ficha: membresías y pagos" (`q` de cada pestaña, errores, sin cupo propio, costo fijo por página, psql) y el índice; DECISIONES "S3-B11" (fachadas, `_member_outs`, `search_ids` sin `LIMIT`, `_page_of`, conteo del contrato, revisión y ciclo de Alembic).
- Revisión de seguridad (`security-reviewer`, `git diff 8241f8b -- api/src`): 0 CRITICAL, 0 HIGH, 0 MEDIUM, 2 LOW, 4 INFO. LOW-1 (`search_ids` sin `LIMIT`) aceptado: truncar perdería filas y el catálogo es pequeño. LOW-2 verificado: `ix_memberships_member_status_start` e `ix_payments_member_paid` existen en `db_test`. Los INFO, aceptados (DECISIONES). Sin código nuevo por la revisión.
- Ciclo de Alembic (B11.6 punto 3, desviación autorizada: `db_test` en `127.0.0.1:5443`, no `apex-db-1`, que usan los E2E de F1): `current` `0011_payments_immutability (head)` → `downgrade 0007_plans` (cuatro pasos, sin errores) → `current` `0007_plans` → `upgrade head` (cuatro pasos) → `current` **`0011_payments_immutability (head)`**; `alembic heads` = una. Los siete triggers de `memberships` y `payments` en `A` tras el ciclo. El ciclo en `apex-db-1` queda para V2 punto 4.

### S3-B11 · Evidencia (B11.5 a B11.7; después del sello, checkpoint `41e244e`)

- `pre-commit run --all-files` corrido ANTES de los gates (todo `Passed`, sin cambios) para no tener que resellar.
- Gates (sin `PYTEST_ADDOPTS`, `ls` previo de los seis archivos), seguidos y sin editar entre uno y otro: (1) `slice-gate.sh plans tests/plans/test_search_ids.py tests/plans/test_service_list.py` **344 ok**; (2) `slice-gate.sh payments tests/payments/test_list_for_member.py tests/payments/test_router_member_payments.py` **327 ok**; (3) el que sella, `slice-gate.sh memberships tests/memberships/test_member_memberships_service.py tests/memberships/test_member_memberships_router.py` **326 ok**. `ruff`, `format` y `mypy` limpios en los tres (incluyen `tests/architecture`).
- Cierre del backend (B11.6), sin cambiar archivos rastreados (huella de `git diff` idéntica antes y después):
  1. `run-gates.sh` **todos los gates en verde** (exit 0): api `ruff`, `format`, `mypy`; pytest `--cov=app -m "not perf"` **3.820 ok, 3 saltadas** (NTFS), cobertura global **96,61 %**; scripts de CI; web `lint`, `tsc`, vitest con cobertura **137 archivos, 2.404 ok**, `build`. No hizo falta repetir la sección web aparte. `pytest tests/architecture -q -rs` **286 ok, 0 saltadas**.
  2. `pytest -m perf -q -s` **8 ok** (dos corridas, tiempos de la segunda): búsqueda por documento con 1.000 socios 32,8 ms; L-11 login fallido x20 p50 0,398 s, p95 0,407 s; `membership_status=active` con 5.000 ids 42,6 ms; `membership_status=none` con 5.000 ids 143,5 ms; lista `expiring` con 1.000 socios y 3.000 membresías 15,4 ms; resumen sin caché con 1.000 socios 14,8 ms; lista de pagos con 10.000 pagos 17,4 ms; resumen del mes con 10.000 pagos 9,5 ms.
  3. Ciclo de Alembic en `db_test` (bloque Verde; desviación autorizada, `apex-db-1` en V2 punto 4).
  4. `uvx pre-commit run --all-files` tras `run-gates.sh` y `perf`: todo `Passed`, sin cambios.
- `db_test` sin residuos al final: 0 socios, planes, membresías, pagos y filas de `crypto_ops`; 0 sesiones `idle in transaction`.
- Docker (B11.7): api `healthy`, recargado por el bind; no se reinició (los E2E de F1 corren contra él). Por Nginx `:8180` con un access del coach desechable firmado dentro del contenedor del api (script borrado del contenedor y del scratchpad; token solo en una variable de la shell; ninguna contraseña tocada):
  - `GET /members/<Demo B4Uno>/memberships` → **200**, `total 2` (la futura `pending_payment` del 2026-11-25 y la `active` del 2026-10-25 con `paid_cop 120000`, en ese orden); `?q=Mensual` → 200 con las mismas dos; `?q=Anual` → 200 `total 0`.
  - `GET /members/<Demo B4Dos>/payments` → **200**, `total 3` (`DEMO-3`, `DEMO-2` anulado y el pago sin referencia, por `paid_at` descendente); `?q=demo-3` → 200 `total 1` (`DEMO-3`: sin distinguir mayúsculas); `?q=DEMO` → 200 `total 0` (referencia exacta); `?voided=false` → 200 `total 2`.
  - Socio inexistente → **404**.
  - Todas con `Cache-Control: no-store`. Nginx agrega su propio `Cache-Control: no-store` a las rutas del api y la respuesta lleva el encabezado dos veces con el mismo valor; ya pasaba antes de este slice.
  - psql en `apex-db-1`: 0 filas de `crypto.crypto_ops` del coach en los 10 minutos de la demo (las pestañas no descifran ni indexan).

## Fase 4 · Backend

Corrección consolidada de los informes `code-reviewer` y `python-reviewer` sobre `c9720ea`, en el árbol principal (rama `feat/sprint-03-membresias-pagos`). Detalle por hallazgo y decisiones S3-D89 a S3-D97 en `docs/ddd/DECISIONES.md`, sección "Fase 4 · Sprint 3 · Backend".

- Orden seguido: M2 (`memberships/summary.py`, S3-D90) → M1/PM1 (`MemberReactivated` y suscripciones, S3-D89) → H1 (CI `USER_*`) → L2 (`test_images_pinned.sh` con `ci.yml`) → M3 (Nginx `proxy_hide_header`) → M4 (RUNBOOK en presente) → L1 (`admin-write` en baja y reactivación, S3-D97) → PM3 (`reraise_with_prefix`, S3-D94) → PL2 (código muerto y `:ns`) y PL6 (docstring de `core/locks.py`, S3-D95) → PL1 (`ctx.obj` en el CLI) → PL4 (`"none"` en el alta) → PL7 (sin guardas en `LIMPIAR_PAYMENTS`; índice aceptado con `EXPLAIN`) → PM4 y PM5 juntos (constructores únicos, `rules.snapshot`, `core.pagination.any_uuids`, `MembershipStatus` y `Role` en el contrato, S3-D91 y S3-D96) → PM2 (prueba del comportamiento actual, S3-D92) → docs.
- Rojos vistos antes de cada corrección: `test_summary_cache.py` (baja y reactivación servían la caché vieja), `test_events_without_pii`/`test_handlers_no_new_locks` (sin `MemberReactivated`), paso E15 simulado sobre una copia de `.env.example` (sin `USER_DETAIL_LIMIT_PER_MIN` falla con "hay 7"), `test_images_pinned.sh` sobre una copia con `image: postgres:16` en `ci.yml` (pasaba con 0 fallas), `test_nginx_conf.sh` (2 `Cache-Control` y 2 `Pragma` por `/api/` con upstream falso), `test_router_deactivate.py` y `CON_LIMITE` (sin 429), `test_rules.py` con `DatabaseBusy` y `TooManyRequestsError` (`TypeError`), `test_locks.py` y `test_sql_literals_constant.py` (`:ns`), `test_db_timeouts_cli.py` (sin `RuntimeOptions`), `test_service_create.py`/`test_router_create.py` (`None` en lugar de `"none"`), `test_triggers_siempre_activos.py` (guarda `pg_trigger`), `test_out_parity.py` (estado como `str` y OpenAPI `string`). `copy.copy(DatabaseBusy())` también da `TypeError` (comprobado): por eso S3-D94 usa `__new__`.
- `EXPLAIN` en `db_test` (`enable_seqscan = off`): `list_for_member` → `Index Scan using ix_memberships_member_status_start` + `Sort (start_date DESC, id)`; su `count(*)` → `Index Only Scan` sobre el mismo; las no canceladas de la venta → `ex_memberships_member_dates` (gist parcial, `WHERE status <> 'cancelled'`, no sirve a la pestaña que incluye anuladas).
- Conteos (sin `--cov`, `-m "not perf"`, una corrida a la vez): primera mitad (`tests/core tests/crypto tests/auth tests/settings tests/cli tests/audit tests/test_ci_database.py tests/test_smoke.py`) **1.493 ok, 3 saltadas**; segunda mitad (`tests/members tests/plans tests/memberships tests/payments tests/migrations tests/architecture`) **2.356 ok, 8 deseleccionadas**. `ruff check .` y `ruff format --check .` limpios (411 archivos), `mypy src` sin errores (97 archivos), `uvx pre-commit run --all-files` todo `Passed`, `bash -n` de `test_images_pinned.sh` y `test_nginx_conf.sh`, `test_images_pinned.sh` 0 fallas, `test_nginx_conf.sh` 0 fallas, `test_compose_config.sh` 0 fallas, `scripts/workflow/tests/run.sh` 5 de 5 en verde.
- Contrato (P-API): `export-openapi` dos veces idéntico; 53 operaciones (0 nuevas, 0 quitadas); componente nuevo `MembershipStatus` y `status` de `MembershipOut`/`MembershipRow`/`SellMembershipOut` como `$ref`; 429 en `DELETE /members/{member_id}` y `POST /members/{member_id}/reactivate`. `npm run gen:api` regeneró `web/src/core/api/types.ts` (único archivo de `web/` tocado). `npx vitest run src/core/api src/shared/data src/features/memberships`: 20 archivos, 422 pruebas en verde.

**Pendientes que pasan al orquestador.**
- V1 (front): `npx tsc --noEmit` en el árbol principal da UN error tras el enum: `src/shared/data/memberships.test.ts(79,71)`, el fixture `membershipRow({ status: "paused" })` (la prueba que exige `invalid_response` con un estado desconocido) ya no tipa porque `status` es la unión de seis valores. No se tocó (fuera de `types.ts`): el ajuste es un cast en el fixture (`status: "paused" as never` o `as unknown as MembershipStatus`) o que el constructor del fixture acepte `string`. Revisar también en el worktree del F7 tras fusionar.
- V1 (front, sin cambio esperado): el alta de socio responde `membership_status: "none"` en lugar de `null` (PL4), lo mismo que ya daban la ficha y la lista.
- V2/V4: prueba funcional de Nginx por `:8180` (una sola `Cache-Control` y un solo `Pragma` en `/api/`); exige reconstruir la imagen `web` (copia `infra/nginx/snippets/`). No se reinició ni se reconstruyó nada: el api recarga por bind mount.
- V2/V4: el job `e2e-stack` de la CI con las ocho `USER_*` x100 solo se ve en GitHub Actions.

## Validación V2–V8

Rama `feat/sprint-03-membresias-pagos` en `d5f494d` al entrar, árbol limpio. Alias
`DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"`. Informes,
logs y scripts de la demo en el scratchpad de la sesión (fuera del repo); capturas en
`web/test-results/captures/` (gitignored). Sin credenciales en este bloque: `admin@ejemplo.local`
no se tocó; un access suyo se firmó dentro de `apex-api-1` (script temporal en `/tmp`, borrado
como root al terminar) solo para crear y luego borrar el admin desechable
`admin-e2e-1792950100@apex.test` (`99fd5d95-…`, `POST /users` + `POST /auth/reset` con
contraseña aleatoria; `DELETE /users/{id}` 204 al final). El coach `coach-mvjpe527@apex.test`
se restableció con `tools issue-reset-link … --as admin@ejemplo.local` + `POST /auth/reset`.
Contraseñas y tokens vivieron solo en archivos del scratchpad, borrados al terminar.

### V2 · Stack desde cero de código
- `docker compose build` sigue roto en este equipo (RUNBOOK §7, `--allow=network.host`; con
  `COMPOSE_BAKE=false` también falla: "failed to execute bake"). Imágenes con buildx directo y
  `--no-cache`: `apex-api:local` `699523dc7e8d` (contexto `api/`, 18 s) y `apex-web:local`
  `c4d45f01b338` (contexto raíz, 26 s); `$DC up -d --no-build`: api y web recreados, `healthy`.
- `tools init-keys`: KEK, firma y par JWT "ya existe". `alembic current` =
  `0011_payments_immutability (head)`.
- `pg_dump` previo a `docs/scratch/sprint-03-antes-v2.dump` (2,4 MB, ignorado por `*.dump`, NO
  confirmado; lo borra V12). Antes: 13 membresías, 3 congelaciones, 15 pagos, 43 socios, 25
  planes, 76 usuarios, 1.157 filas de auditoría.
- Ciclo en `apex-db-1` con el api parado (`$DC stop api`) y `$DC run --rm --entrypoint alembic
  tools …`: `downgrade 0007_plans` (0011 → 0010 → 0009 → 0008 → 0007, sin errores; no quedan
  tablas en `memberships` ni `payments`) → `current` `0007_plans` → `upgrade head` (cuatro pasos)
  → `current` `0011_payments_immutability (head)`; `alembic heads` (contenedor y `uv run` en
  `api/`): una sola cabeza. Para ver la migración aplicada por el engine propio de `env.py` se
  bajó un paso más sin datos (`downgrade 0010_payments`, tablas vacías) y se arrancó el api: log
  `Running upgrade 0010_payments -> 0011_payments_immutability` y `migraciones al día` en
  0,08 s, sin timeouts. Los siete triggers de `memberships` y `payments` en `A`.
- `$DC logs --tail 50 api`: solo `INFO` (arranque, alembic, `Keyring(llaves=8, activas=8)`),
  0 `ERROR`, 0 trazas.
- Nginx (M3 de la Fase 4) por 8180: `GET /api/v1/health` y `GET /api/v1/members?limit=1` con
  token → **una** `Cache-Control: no-store` y **una** `Pragma: no-cache` (también en el 401 sin
  token y en el 503 `busy`). Queda cerrada la observación de B9b/B11 (cabecera duplicada).
- Efecto del ciclo: se perdieron las membresías, congelaciones y pagos de B1 a B11 y de F1–F7
  (aprobado en el plan; el dump los conserva).

### V3 · Datos reales
- `auth.users` vivos: 3 admin (`admin@ejemplo.local`, `system@apex.local` inactivo y el
  desechable) y 58 coach (de specs anteriores); todos con `must_change_password = f`.
- `settings.settings_sections`: `gym` 19, `memberships` 16, `payment_methods` 1, `privacy` 14
  (las versiones suben con las specs). `memberships`: `max_freezes_per_membership` 2,
  `max_freeze_days_per_membership` 30, `max_retroactive_days` 7, `expiring_days` 7.
- `plans.plans`: 25 vivos; **no** hay "Mensual" 120.000/30: `POST /plans {"name":"Mensual"}` →
  409 `plan_name_duplicated` contra "mensual" (320.000/90, `37f1e7d4-…`, creado por error en V2
  del Sprint 2; sin edición de planes hasta US-082). Se creó **"Mensual V50137"** (120.000, 30
  días, `2f240e77-7038-4560-936d-17f21b21a909`) y la demo lo usa.
- Socios de la demo por API (documento y teléfono aleatorios, correo `@apex.test`):
  `demo-venta` `dab44d0a-6cac-4a29-9177-0fe7df906fca`, `demo-parcial`
  `2b46a4bd-d5c4-4690-9f95-a4b3aa3d5bc4`, `demo-renovar` `7a647c69-9d4a-4064-8fda-c91e67028afd`,
  `demo-congelar` `f5a582ff-3651-46b7-88bb-c79d89b9c9ce`, `demo-ficha`
  `9e786531-c4e3-4fd2-8ed6-6b88e4834080` (nombres "Demo <X> V50137"); en V7 se sumó "Demo
  CongelarLimite V50137" `ae258a0e-987b-4df4-b1a7-12850ff0238e`.

### V4 · E2E contra el stack
- Copia de `.env` al scratchpad; bloque al final con las ocho `LOGIN_*`/`*_IP_LIMIT` de E5
  (1000; `LOGIN_ACCOUNT_GLOBAL_LIMIT` 10000) y las ocho `USER_*` ×100 de E10 (los valores del
  `sed` del job `e2e-stack`); `$DC -f infra/compose.e2e.yml up -d --no-build api web`: 16
  variables dentro del api y `rate=6000r/m` en `auth-zone.conf` de web.
- `npm run e2e:stack -- --workers=1` (`E2E_BASE_URL=http://localhost:8180`), 35 pruebas en 15
  specs. Corridas 1 y 2: **34 ok, 1 fallo**, `refresh-two-tabs` (`refreshes` = `[200, 200]`
  en lugar de `[200]`); corrida 3: 35 ok. Sola, 8 de 8 ok.
  - Diagnóstico (copia temporal de la spec con registro de peticiones, ya borrada): en el caso
    malo la segunda pestaña recibió por el canal el access nuevo de la primera ANTES de pedir
    `/settings/gym`; el 401 falso de la spec se aplica a la primera lectura sin mirar el token, así
    que "venció" un token recién emitido y la app pidió, con razón, otro refresh (sin reuso ni
    pérdida de sesión). **Defecto de sincronización de la prueba, no del producto.**
  - Corrección `7bb4e55` `fix(web)`: los dos 401 falsos se retienen con una barrera hasta que
    llegan las dos lecturas; la aserción `[200]` no cambia. 15 de 15 ok repetida sola.
- Resultado final, dos corridas completas seguidas tras la corrección: **35 ok, 0 fallos, 0
  saltadas** (46,3 s y 46,8 s; `retries: 0`, así que no hay flaky), y una tercera de 35 ok (48,4
  s) para regenerar las capturas. Incluye completas `settings-gym` (5 de 5, con "el coach ve Sin
  permiso…") y `captures` (13 de 13, con "inicio en dark" a 768, 1024 y 1440), las dos que F7 no
  pudo cerrar por los 429 de desarrollo. 0 respuestas 429 en el log de Nginx.
  Por spec: `captures` 13, `login` 4, `settings-gym` 5, `plans` 2 y una cada una `logout-expired`,
  `member-detail`, `member-tabs`, `members-mobile`, `members`, `memberships-freeze-cancel`,
  `payment-void`, `refresh-two-tabs`, `sell-with-payment`, `users-activation`, `users-manage`.
- `npx playwright test --project=preview --workers=1`: primera corrida **143 ok, 1 fallo**
  (`members.spec.ts` "alta: el 409 enlaza al socio existente…", axe `color-contrast` en el
  botón recién pulsado: hover a mitad de la transición, el caso del Sprint 2; sola 10 de 10 ok).
  Corrección `dab1cc4` `fix(web)`: los cinco ayudantes axe del preview que no esperaban las
  animaciones (`members`, `plans`, `settings-config`, `users-access`, `users-manage`) ahora lo
  hacen, como ya hacían los demás; sin cambio de aserciones. Después: **144 ok, 0 fallos** (2,0
  min), dos veces. 120 capturas del preview (320, 768, 1024 y 1440 en claro y oscuro donde las
  piden; `members-mobile` a 390 y 320) más 23 del stack.
- Restauración: `.env` copiado de vuelta, `cmp` idéntico a la copia; `$DC up -d --no-build api
  web` sin `compose.e2e.yml`: 0 variables de límites en el api, `rate=60r/m`, sin el montaje
  E2E. Seis logins fallidos (61 s después): `401 ×5, 429`.

### V5 · Rendimiento
`uv run pytest -m perf -q -s` (`TEST_DATABASE_URL` en `127.0.0.1:5443`), dos corridas: **8 ok**
cada una (79,8 s y 85,2 s). Tiempos (corrida 1 / corrida 2; entre paréntesis B11.6):
- búsqueda por documento con 1.000 socios: 34,6 / 30,9 ms (32,8);
- L-11 login fallido ×20: p50 0,403 / 0,399 s, p95 0,411 / 0,412 s (0,398 y 0,407);
- `membership_status=active` con 5.000 ids: 43,1 / 42,6 ms (42,6);
- `membership_status=none` con 5.000 ids: 138,8 / 161,4 ms (143,5);
- lista `expiring` con 1.000 socios y 3.000 membresías: 15,0 / 16,2 ms (15,4);
- resumen de membresías sin caché con 1.000 socios: 17,2 / 13,0 ms (14,8);
- lista de pagos con 10.000 pagos (`limit=25`): 13,7 / 12,9 ms (17,4);
- resumen del mes con 10.000 pagos: 8,2 / 8,6 ms (9,5).
Todo muy por debajo de los topes (500 y 300 ms); no hace falta `0014_payments_registered_by_idx`.

### V6 · Smoke con evidencia SQL (sobre `apex-db-1`, tras las acciones de V7)
- Activación atómica (V7.1, membresía `7ea35042-20be-4f30-9c76-2358917e0c90`):
  `SELECT m.status, p.member_id = m.member_id … JOIN payments.payments p …` → `active | t`
  (120.000, `cash`); auditoría del socio por `seq`: 1170 `insert members.members`, 2869 `insert
  memberships.memberships`, 2870 `insert payments.payments`, 2871 `update
  memberships.memberships`.
- Reversión (V7.3, membresía `6f655274-c72d-449d-9dae-5dcd80131afc`, pago anulado
  `dea8ba75-dbcb-46ee-8b95-3056d1af19ff`): `pending_payment`, `2026-10-25 – 2026-11-24` intactas,
  0 congelaciones, pagado 62.000; el pago con `voided = t`, motivo y quién.
- `EXCLUDE`: `INSERT` crudo solapado para `demo-renovar` (`2026-11-01 – 2026-11-30`) → `ERROR
  23P01 … "ex_memberships_member_dates"` con el rango de la vigente.
- Triggers (cada uno en `BEGIN … ROLLBACK`): `UPDATE payments SET amount_cop = 1` sobre un pago
  válido → `payments_immutable: column`; anular por SQL y volver a tocar → `payments_immutable:
  already_voided` (también `amount_cop` sobre el ya anulado); `DELETE` → `payments_immutable:
  delete`; `TRUNCATE` → `payments_immutable: truncate`; `UPDATE memberships SET status='active'
  WHERE status='cancelled'` → `memberships_identity: una membresía anulada no cambia`; `DELETE
  FROM memberships.memberships` y `TRUNCATE … CASCADE` → `memberships_no_delete`; `UPDATE
  membership_freezes SET days=1` y `DELETE` → `membership_freezes_append_only`; `SET LOCAL
  session_replication_role = replica; UPDATE payments …` → `payments_immutable: column` (los
  triggers `ENABLE ALWAYS` siguen). El pago tocado sigue en 1.000 y válido.
- Ficha y reveal (`demo-ficha`): `crypto_ops` por `verb, purpose` → `decrypt | mask | 28`,
  `decrypt | reveal | 1`, `encrypt 4`, `index 4`. Observación: el plan dice `mask | 5` para UNA
  carga; este socio tiene 4 campos cifrados (sin contacto de emergencia ni nacimiento) y la ficha
  se cargó 7 veces en la demo (admin, recarga, coach, edición, tras guardar, baja y reactivación):
  7 × 4 = 28. Auditoría `reveal` seq 2907, `user_id` = admin desechable, `after = {"ip":
  "172.30.0.128", "field": "document"}` sin el valor. `decrypt` sin `purpose`: **0** en toda
  `crypto_ops`. Claves de auditoría del socio: `insert` (blobs e índices), `reveal` (`ip`,
  `field`), `update` del coach solo `phone`, `phone_idx`, y dos `update` `status`, `deleted_at`.
- `verify_chain` (script por stdin en el contenedor del api, `create_engine_from` y
  `AuditEntry.__table__` por `seq`; no hay comando del CLI): `VerifyResult(ok=True,
  rows_checked=2914, broken_at_seq=None)`, 2.914 de 2.914.
- 503 `busy` (W0-2.7 repetida): psql `BEGIN; SELECT pg_advisory_xact_lock(4270002);
  pg_sleep(20)`; `POST /members` 2 s después → **503** en **10,03 s** con `retry-after: 1` y una
  `Cache-Control: no-store`; log `WARNING app.db "db busy"` `sqlstate 55P03` y `http_request`
  `status 503` `duration_ms 10017`; tras el `ROLLBACK`, el mismo `POST` → **201** en 0,015 s.
- Logs del api (`$DC logs --since 90m`, 315 líneas desde la recreación de las 18:03 UTC; las de
  V3 se fueron con la recreación de V4): 0 apariciones de los documentos y teléfonos de V3, de
  las referencias `V7-REN-`/`V7-CONG-`, de los motivos de anulación de V7, de `apx1.` y de los
  correos de demo; 0 `ERROR`, 0 trazas.

### V7 · Demo por la pantalla en 8180 (Playwright con el admin desechable y el coach; capturas `v7-p*-*.png`)
1. `demo-venta`: `/membresias/vender?socio=<id>`, "Mensual V50137", Efectivo, $ 120.000 →
   `POST` 201 `active`; "Venta registrada" con Estado **"Al día"** (`v7-p1-*`). SQL en V6.
2. `demo-parcial`: venta con $ 60.000 → 201 `pending_payment`, **"Pendiente de pago"**. Saldo por
   el panel (`/socios?pago=`, precargado $ 60.000): el api respondió **409
   `payment_possible_duplicate`** (mismo valor, medio y quien registra que el abono de la venta,
   hace segundos: S3-D41, como en F7) y la pantalla mostró "¿Registrar otro pago igual?"; al
   confirmar, 201 y estado `active` ("Al día"). Tercer pago de $ 1.000: la pantalla muestra
   "¿Registrar un pago mayor al saldo? Este pago supera el saldo de la membresía en $ 1.000…"
   sin enviar nada; el mismo pago por API sin `confirm_overpayment` → **409
   `payment_exceeds_balance`** (`field amount_cop`); al confirmar, **201** con
   `confirm_overpayment: true`. Repetido en menos de 2 minutos: modal de sobrepago, luego el api
   409 `payment_possible_duplicate` y el **segundo modal** "¿Registrar otro pago igual?"; al
   confirmar, 201 con `confirm_duplicate: true` (`v7-p2-*`). Observación de texto: el plan dice
   "supera el saldo pendiente"; la pantalla dice "supera el saldo de la membresía".
3. El admin anula el segundo pago (el saldo de 60.000) desde la pestaña Pagos de la ficha con
   motivo → `POST /payments/{id}/void` 200; la vigente vuelve a **"Pendiente de pago"** (pagado
   62.000, saldo 58.000). La misma anulación desde una pestaña abierta antes → 409
   `payment_already_voided` y la alerta **"Otra persona lo anuló antes. Actualizamos el pago…"**;
   por API otra vez → 409. `UPDATE … amount_cop = 1` rechazado por el trigger (V6) (`v7-p3-*`).
4. `demo-renovar` vendida y pagada por API (Nequi, 201 `active`, `2026-10-25 – 2026-11-24`).
   "Renovar membresía" (`?renovar=1`) muestra **Inicio 25 nov 2026** ("al día siguiente de que
   termine la actual", solo lectura; Q1) y fin 25 dic 2026; `renew: true` → 201, la futura
   `ee1ccfd8-5212-45e0-892b-3d77c3664289` `2026-11-25 – 2026-12-25`. Vender otra sin `renew` (con y
   sin `start_date` dentro de la vigente) → **409 `membership_conflict`** con `existing_id` de la
   vigente: según `sell.py`, con una vigente o futura el conflicto gana a `membership_overlap`
   (D8); `membership_overlap` solo sale contra una no cancelada que ya no es vigente (lo cubre
   `test_sell_service.py`). El `INSERT` crudo lo rechaza la `EXCLUDE` (V6) (`v7-p4-*`).
   Observación: el texto del plan ("responde 409 `membership_overlap`") no coincide con el
   orden de D8 del código; se anota, no es un defecto.
5. `demo-congelar` (al día, Bre-B): congelar desde la pantalla de membresías "Desde" hoy, "Hasta"
   +9 → "Son 10 días; la membresía terminará el 4 dic 2026"; aviso "Ahora termina el 4 dic 2026",
   fila "Congelado", `end_date` 2026-11-24 → **2026-12-04**. La misma ventana otra vez y una
   segunda antes de terminar la primera → **409 `membership_not_freezable`** (la membresía está
   `frozen`: es la primera regla de `rules.py`, antes de `freeze_already_scheduled`). La tercera
   (`freeze_limit_reached`) no se alcanza en el mismo socio mientras la primera sigue en curso,
   así que se mostró en "Demo CongelarLimite" (venta desde hoy −7, dos congelaciones pasadas por
   API, 200 y 200): la tercera por la pantalla → **409 `freeze_limit_reached`** y "Esta membresía
   ya usó todas las congelaciones que permite el gimnasio." Anular la membresía congelada de
   `demo-congelar` (admin, motivo) → 200, "Sus pagos siguen registrados.", fila "Cancelado";
   registrar un pago sobre ella → **409 `membership_cancelled`** (`v7-p5-*`).
6. `demo-ficha`: la ficha muestra el documento como `CC •••• <4 últimos>`; "Mostrar" lo revela
   (igual al sembrado) y "Ocultar" vuelve a la máscara sin dejarlo en el HTML; una fila `reveal`
   y una `decrypt | reveal` (V6). El coach: sin "Dar de baja"; en "Editar socio" el documento
   sale como "Solo un administrador puede cambiar el documento" sin "Cambiar"; cambia el teléfono
   (el `PATCH` lleva solo `phone`, "Cambios guardados", máscara nueva); `PATCH {document}`
   distinto y también el mismo → **403 `forbidden_field`** `field document` (M-3). El admin da de
   baja → "Dado de baja el 25 oct 2026. Su ficha es de solo lectura…", sin "Editar"; reactivar →
   "Socio reactivado" y "Editar" de nuevo (`v7-p6-*`).
7. `/socios`: chips de "Estado" con conteos (Todos 50, Al día 3, Por vencer 0, Vencidos 0,
   Congelados 0, Pendiente de pago 1, Sin membresía 46, Dados de baja); `plan_id` de "Mensual
   V50137" → 4 filas; + "Al día" → `?plan_id=…&membership_status=active`, 3 filas (las mismas 3
   del API `membership_status=active&plan_id=…`); + "Pendiente de pago" → 1 fila. Los conteos de
   los chips son los globales del resumen (`/memberships/summary` → `active 3, pending_payment
   1`), no se recalculan por plan. A 390 px: 0 tablas, 25 tarjetas y "Cargar más" → 50.
   `GET /payments/summary?month=2026-10` → `total_cop 7.682.000`, `payments_count 86`,
   `voided_count 27`, efectivo 6.662.000, Nequi 900.000, Bre-B 120.000; `/pagos?mes=2026-10`
   muestra lo mismo ("86 pagos válidos", "Anulados 27", 113 en total); la lista `voided=false`
   del mes paginada por el API suma 86 pagos y 7.682.000 con el mismo reparto por medio
   (`v7-p7-*`).

### V8 · Repetición
- `tools seed` dos veces sin `.env.seed`: "faltan ADMIN_EMAIL o ADMIN_INITIAL_PASSWORD"
  (S3-D64: el archivo ya no existe); con un `.env.seed` efímero (correo `admin@seed-v8…`,
  contraseña aleatoria, borrado al terminar): "omitido: ya existe un admin activo" dos veces; no
  se creó ningún usuario.
- `tools init-keys` dos veces: las tres llaves "ya existe". `export-openapi` dos veces:
  idénticas entre sí e idénticas a `docs/openapi.json` (sha256 `7f30f2e02289…`).
- Specs `stack` dos veces seguidas en verde (V4). Anular el mismo pago dos veces: 200 (pantalla)
  y 409 `payment_already_voided` (pestaña vieja y API). Congelar la misma ventana dos veces: 200
  (pantalla) y 409 (`membership_not_freezable`, V7.5). `renew: true` dos veces: 201 (pantalla) y
  409 `future_membership_exists` con el id de la futura.
- `SMOKE_KEEP=1 bash scripts/ci/compose-smoke.sh`: no corre tal cual en este equipo (su `$DC
  build api` y `up --build` chocan con el `--allow=network.host` de Compose). Usa el mismo
  project `apex`, el mismo `.env` y los mismos puertos (no pisa otros proyectos; con
  `SMOKE_KEEP=1` no baja nada). Se corrió una copia en el scratchpad con solo esos dos cambios
  (buildx directo de api y web, `up -d --no-build`): **verde en 29 s**; db, db_test, api y web
  healthy, `.env.seed` efímero creado y borrado, seed "omitido", api sin `ADMIN_*`, web en
  `172.30.0.10` = `TRUSTED_PROXIES`, `web-smoke` 0 fallas, `headers` 0 fallas (con
  `Cache-Control` y `Pragma` únicos; ráfaga de 45 logins: 40 respuestas 429). Imágenes
  resultantes `apex-api:local` `18158a4577c7` y `apex-web:local` `dc21074575fc` (la web incluye
  las specs corregidas; el bundle servido sigue siendo `assets/main-CvatLbOO.js`); api y web
  recreados con ellas (`--force-recreate`), `healthy`, `alembic current` head.

### Commits de la validación
- `7bb4e55` fix(web): `refresh-two-tabs` sin carrera del 401 falso.
- `dab1cc4` fix(web): axe del preview tras las transiciones.
- El de este bloque (`docs(sprint-03)`).

### Estado al terminar
- Stack `apex` arriba sin `compose.e2e.yml`: db, db_test, api y web healthy en 5442/5443/8181/8180;
  web con `rate=60r/m`; `.env` idéntico a la copia previa (`cmp`); seis logins fallidos `401 ×5,
  429` tras la última recreación.
- Admin desechable `admin-e2e-1792950100@apex.test` borrado (204, `deleted_at`); script de firma
  borrado del contenedor; secretos del scratchpad borrados.
- `docs/scratch/sprint-03-antes-v2.dump` en disco, sin confirmar (V12 lo borra).
- Datos de la demo que quedan: plan "Mensual V50137"; socios "Demo Venta/Parcial/Renovar/
  Congelar/Ficha/CongelarLimite V50137" activos con sus membresías y pagos (y "Demo Busy V50137"
  del 201 posterior al 503); los socios y planes de las specs.
- Fuera de este bloque: V1 y V9 a V12 (otros pasos del plan); el job `e2e-stack` de la CI solo
  se ve en GitHub Actions.

## V10 · Corrección

Corrección de la revisión de seguridad final V10 (backend e infra) en el árbol principal, rama `feat/sprint-03-membresias-pagos`, desde `3c7db38`. Detalle y decisiones S3-D100 a S3-D102 en `docs/ddd/DECISIONES.md`, sección "V10 · Sprint 3 · Seguridad posterior". La sesión se cortó por el límite semanal tras el Verde de M-A y L-B; se retomó tras el reinicio de la máquina con `apex-db_test-1` healthy.

- Orden: M-A (prueba de arquitectura `test_writes_have_user_limit.py`, `CON_LIMITE` +10, pruebas de router de `plans`, `settings` y `auth`; luego `enforce_user_limit(..., "admin-write", ...)` y 429 en las diez rutas) → L-B (`redact_text` recorta `DETAIL:`, `Failing row contains` y `Key (`; `_from_bytes` de fechas sin el valor) → L-A (64k en `/api/` y `/api/v1/tv/`, 128k en `= /api/v1/settings/privacy`, casos estáticos y funcionales en `test_nginx_conf.sh`) → L-C (RUNBOOK §10) → I-2 (SPRINT-04B, W0-2) → P-API → docs.
- Rojos vistos: `test_user_limits_catalog` y `test_error_codes_per_route` con `CON_LIMITE` ampliado (2 fallas); las tres pruebas de router (18 fallas: sin 429 ni declaración); `test_logging_redact` y `test_types` (5 fallas); `test_nginx_conf.sh` contra el `default.conf` de `3c7db38` (7 fallas: los topes y los 413 de 70 KB y 140 KB).
- Cuerpos legítimos revisados frente a 64k: motivos de 2.000 caracteres, `MemberPatch`, planes y settings caben; `policy_text` (20.000 caracteres, hasta 80.000 bytes) no, por eso su location propio de 128k.
- Conteos (sin `--cov`, `-m "not perf"`, una corrida a la vez): primera mitad **1.517 ok, 3 saltadas**; segunda mitad **2.366 ok, 8 deseleccionadas**. `ruff check .` y `ruff format --check .` limpios (415 archivos), `mypy src` sin errores (97 archivos), `uvx pre-commit run --all-files` en verde, `bash -n` y `test_nginx_conf.sh` 0 fallas, `scripts/workflow/tests/run.sh` en verde.
- Contrato (P-API): `export-openapi` dos veces idéntico (sha256 `3559f376…`), 10 respuestas 429 nuevas, 0 operaciones nuevas; `npm run gen:api` (solo `web/src/core/api/types.ts`), `npx tsc --noEmit` limpio, `npx vitest run src/core/api` 164 ok.

**Pendientes que pasan al orquestador.**
- V9: reconstruir la imagen `web` para ver los 413 del borde por `:8180` (el script ya lo prueba con Nginx real en un contenedor desechable). No se reinició ni se reconstruyó nada.
- V12: borrar los volcados `docs/scratch/sprint-03-antes-*.dump` (L-C).
- Front (no tocado salvo `types.ts`): las diez rutas ahora pueden responder 429 `rate_limited`; falta comprobar que las pantallas de planes, ajustes y usuarios lo muestran con un mensaje claro (hoy solo `LoginPage` trata `rate_limited` de forma explícita).

## V9 · Gates ligeros

Puntos V9.2 a V9.7 y V9.9 del plan (sección 7), sobre `fd2e8a3` con el árbol limpio, sin tocar Docker del stack, `.env`, `infra/` ni Playwright. V9.1 (`run-gates.sh`) y V9.8 (imagen del api) quedan para el orquestador.

- V9.2 · `uv run pytest tests/architecture -q -rs`: **293 ok, 0 saltadas** (30,7 s). Verde.
- V9.3 · `uvx pre-commit run --all-files`: ruff, ruff format, detect private key, fin de archivo, conflictos, sin llaves ni `.env` y `mypy --strict` en verde; `git status` limpio después (no reformateó nada). Verde.
- V9.4 · `bash scripts/workflow/tests/run.sh`: 5 de 5 archivos en verde. `bash -n` de los 24 `scripts/**/*.sh` versionados: 0 fallos. Verde.
- V9.5 · `bash scripts/ci/check-licenses-api.sh`: todas las licencias del runtime en la lista permitida (con la excepción MPL-2.0 registrada). `cd web && npm run licenses`: MIT 12, ISC 1, salida 0. `bash scripts/ci/notice.sh && git diff --exit-code NOTICE`: sin diferencia. Dependencias entre `d65056e` y `fd2e8a3`: `api/pyproject.toml` y `api/uv.lock` sin cambios; en `web/package.json` solo cambian `vitest` y `@vitest/coverage-v8` (3.2.7 a 5.0.5, desarrollo). **No hay dependencias de producción nuevas en el Sprint 3**; `NOTICE` al día. Verde.
- V9.6 · `uv export --frozen --no-dev --no-emit-project` + `uvx pip-audit@2.10.1 --strict --disable-pip --require-hashes` (igual que el job `api` de la CI): "No known vulnerabilities found". Verde.
- V9.6 · `cd web && npm audit --omit=dev --audit-level=high`: **BLOQUEANTE, salida 1**. Aviso nuevo de producción: `zod <4.6.6`, GHSA-mrhx-c7xc-m3w5 (alto, CVSS 7,5: agotamiento de memoria al validar colecciones grandes con restricciones). El front usa `zod ^3.25.76` (instalado 3.25.76, también lo trae `eslint-plugin-react-hooks` vía `zod-validation-error`); no hay 3.x corregida: la única salida es `zod` 4.6.7 (mayor, rompe API) y 31 archivos de `web/src` importan `zod`. El paso "auditoría de dependencias de producción" del job `web` fallará igual en la CI. No se corrigió aquí: migrar a Zod 4 (y revisar `@hookform/resolvers`) toca todos los formularios y exige vitest completo y build, fuera del alcance ligero de V9.
- V9.6 · `npm audit --audit-level=high` (informativo): el mismo único aviso (`zod`). El residual de desarrollo `braces` vía stylelint 17 **ya no aparece**.
- V9.7 · gitleaks con la imagen por digest de `ci.yml` (`zricethezav/gitleaks@sha256:c00b6bd0…`), contenedor efímero con el repo en solo lectura, `--config /repo/.gitleaks.toml --redact --log-opts="--all"`: 133 commits, ~16 MB, **no leaks found**. Verde.
- V9.9 · `npm run gen:api && git diff --exit-code src/core/api/types.ts`: sin deriva. Verde.
- Extra · `ruff check .` limpio, `ruff format --check .` 415 archivos formateados, `mypy src` sin errores en 97 archivos; `grep -rn "DISABLE TRIGGER\|TRUNCATE" api/src` vacío.
- Conteos · api por recolección: **3.894 pruebas, 3.886 con `-m "not perf"`** (8 `perf`). Front: `npx vitest list` da **1.907** líneas de prueba sobre 142 archivos `*.test.ts(x)` de `src`; no cuadra con las 2.758 de la Fase 4 (es probable que `vitest list` no expanda igual los casos parametrizados o cuente distinto); vitest completo no se corrió aquí y la cifra válida la da V9.1.

**Veredicto de V9 ligero:** todo en verde salvo `npm audit --omit=dev` (zod 3.x, GHSA-mrhx-c7xc-m3w5), que bloquea el gate y la CI hasta migrar a `zod` ≥ 4.6.6 o registrar un riesgo aceptado con su decisión en `DECISIONES.md`.

## Validación final del stack tras Fase 4 y V10

Rama `feat/sprint-03-membresias-pagos`, desde `fd2e8a3` con el árbol limpio. Repite V2 parcial, V4 y V9.8 con las imágenes reconstruidas. Mismo método que en "Validación V2–V8". `admin@ejemplo.local` no se tocó: solo se firmó un access suyo dentro de `apex-api-1`, con un script temporal borrado como root al terminar. Ese access sirvió para crear y borrar el admin desechable `admin-e2e-1793220078@apex.test` (`200d0bb0-…`). La contraseña del desechable se fijó con `tools issue-reset-link --as admin@ejemplo.local` y `POST /auth/reset`. El coach `coach-mvjpe527@apex.test` se restableció igual. Contraseñas, tokens y la copia de `.env` vivieron solo en el scratchpad y se borraron. Mientras tanto, otro agente trabajaba en el árbol: V9 ligero y la migración a zod 4, sin confirmar. Ninguno de sus archivos entra en estos commits.

### 1 · Imágenes
- Se construyeron con buildx directo y sin `--no-cache`:
  - `apex-api:local` `7ebd75528265`, en 11 s. El contexto es `api/`: el Dockerfile copia `pyproject.toml` y `src` con rutas relativas a `api/`, como dice RUNBOOK §7, así que el contexto raíz no sirve.
  - `apex-web:local` `1b2739fc20b7`, en 20 s, con contexto raíz.
- `$DC up -d --no-build api web`: los cuatro servicios quedaron `healthy`.
- `alembic current` da `0011_payments_immutability (head)`.
- Por 8180 se sirve `assets/main-DnvXISUu.js`. Antes era `main-CvatLbOO.js`: el bundle ya incluye la Fase 4 del front.

### 2 · V9.8
- `check-image-secrets.sh apex-api:local`: **0 fallas**. Sin `.env`, sin llaves privadas, nada bajo `/app` y gitleaks limpio.
- `test_api_image.sh apex-api:local`: **0 fallas**. Revisó UID 10001, tzdata, alembic, ausencia de herramientas de desarrollo y que `app.main` importa.
- Ninguno de los dos scripts construye cuando recibe la imagen, así que no hubo desviaciones.

### 3 · Nginx en vivo por 8180
- Cabeceras de caché: exactamente **una** `Cache-Control: no-store` y **una** `Pragma: no-cache` en:
  - `GET /api/v1/health` (200);
  - `GET /members?limit=1` con token (200);
  - el 401 sin token.
  - `HEAD /health` da 405, porque el api no tiene HEAD, y también trae una de cada una.
- Topes de cuerpo:
  - `POST /api/v1/members` con 60 KB: **422** `validation_error` del api. Con 70 KB: **413** de Nginx.
  - `PATCH /api/v1/settings/privacy` con 100 KB: **422** del api. Con 140 KB: **413**.
  - Los 413 llevan una sola `Cache-Control: no-store` y una sola `Pragma`.
- Observación: el 413 de Nginx sale en HTML (`text/html`), no con el envelope JSON. El 429 de auth sí tiene envelope (`@rate_limited`). No bloquea: el front lo trata como error genérico. Queda anotado para cuando lleguen los adjuntos.

### 4 · Topes `admin-write` (S3-D100)
- Con el admin desechable y los topes de desarrollo (30 por minuto) se lanzaron 31 `POST /plans` seguidos, del `E2E-tope-d78ef5-1` al 31:
  - los 30 primeros dieron **201**;
  - el 31 dio **429** `rate_limited` con `retry-after: 59` y una sola `Cache-Control`;
  - un 32 también dio 429.
- Con la cubeta agotada, `POST /users/{id}/lock` y luego `/unlock` sobre el coach viejo `coach-mvo4z83m@apex.test` respondieron **200 y 200**. Son rutas exentas.
- No existe `DELETE /plans/{id}` hasta el Sprint 4A, así que quedan **30 planes activos `E2E-tope-d78ef5-<n>`** como datos de prueba.

### 5 · `e2e:stack`
Antes de correr se ajustó el entorno:
- copia de `.env` y bloque al final con las ocho `LOGIN_*` y `*_IP_LIMIT` de E5 y las ocho `USER_*` ×100;
- `-f infra/compose.e2e.yml`;
- dentro del api quedaron 16 variables y Nginx con `rate=6000r/m`.

Todas las corridas usaron `--workers=1`, `retries: 0` y `E2E_BASE_URL=http://localhost:8180`, sin `E2E_COACH_*`, de modo que todas las specs pasan por `crearCoach`.

- **Corrida 1: 31 ok y 4 fallos** (`member-detail`, `members`, `plans`, `settings-gym`). En las cuatro, el login del coach respondió 422.
  - Causa: `crearCoach` devuelve ahora `{ id, email, password }` y `login()` mandaba el objeto entero. `LoginIn` tiene `extra="forbid"` y rechaza el `id`.
  - Se reprodujo fuera de la spec: con solo `email` y `password`, el login da 200.
  - Es un **defecto de la prueba**, no del producto.
  - Corrección `59bf09d`: `login()` envía solo `email` y `password`. Prueba nueva en `tests/unit/e2e-stack-guard.test.ts`, en rojo antes del cambio.
  - Los cuatro coaches de esa corrida se borraron en el `finally`, aunque la spec falló: `borrarUsuario` ya funciona contra el stack.
- **Corrida 2: 35 ok.**
- **Corrida 3: 34 ok y 1 fallo** en `sell-with-payment`: no encontraba el radio `^Mensual mvsl6sf5`.
  - La venta pide los 100 primeros planes activos ordenados por nombre (`SELL_PLANS_LIMIT`) y muestra "Se muestran 100 de N planes…". Es diseño, ya probado en `SellPage.test.tsx`.
  - Había 136 planes activos: los 30 `E2E-tope` más los de corridas anteriores, que no se pueden dar de baja.
  - El nombre `Mensual <hora>` del helper siempre queda detrás de los de corridas anteriores, así que la spec se iba a romper tarde o temprano. Es un **defecto de la prueba** que dependía de datos acumulados.
  - Corrección `43b4f09`: `nombrePlanE2E()` devuelve `0 E2E <cuenta regresiva base 36>`, que ordena primero y deja el más nuevo delante. Comprobado con `ORDER BY` en `apex-db-1` y con una prueba unitaria.
- **Corridas 4 y 5: 35 ok cada una.**
- Coaches restantes: `coach-activa-<hora>` subía en uno por corrida y seguía vivo.
  - `users-activation.spec.ts` crea ese coach desde la pantalla con una contraseña sacada de la misma hora y nunca lo borraba. Su guarda solo miraba las specs que usan `crearCoach`.
  - Corrección `561ae32`: la contraseña sale de `crypto.randomUUID()`, el `id` se lee de la respuesta de `POST /users` y la cuenta se borra en un `finally`. La guarda unitaria cubre ahora las altas por la pantalla, con `users-manage` exenta porque prueba la baja por la pantalla.
  - Se comprobó con la spec sola (1 ok, coach con `deleted_at`).
  - Los cinco `coach-activa-mvsl*` de estas corridas se borraron por API (204 ×5).
- **Resultado final: dos corridas completas seguidas tras las tres correcciones, 35 ok, 0 fallos y 0 flaky cada una**, en 53,4 s y 53,8 s. Por spec: `captures` 13, `settings-gym` 5, `login` 4, `plans` 2 y una cada una las otras once.
- psql: `coach-%@apex.test` vivos = **120**, igual que antes de empezar.
  - Son cuentas viejas de sprints anteriores, todas con `created_at` ≤ 2026-10-25 18:03 UTC, más `coach-mvjpe527@apex.test`.
  - De esta validación quedan **0** coaches vivos.
  - `coach-<uuid>` vivos: 0 de 21.
  - El "0 salvo `coach-mvjpe527`" que pedía la tarea no aplica a esta base: las 120 viejas no vienen de estas specs.
- Guarda `exigirStackLocal`: con `E2E_BASE_URL=http://example.invalid`, `sell-with-payment` y `members` fallaron en **2,4 s en total**, con el mensaje "E2E_BASE_URL debe apuntar a localhost o 127.0.0.1…". Los conteos de `members.members`, `plans.plans` y `auth.users` no cambiaron (210, 156 y 200).

### 6 · Restauración
- `.env` se copió de vuelta y `cmp` dio idéntico.
- `$DC up -d --no-build api web` sin `compose.e2e.yml`: 0 variables de topes en el api, `rate=60r/m` y sin el montaje E2E. Compose recreó también `db`, porque cambió el hash de `env_file`; quedó `healthy` y con los datos.
- Seis logins fallidos: **`401 ×5, 429`**.
- `$DC ps`: db, db_test, api y web `healthy`.
- `$DC logs --since 1h api`: 28 líneas, que solo cubren el contenedor recreado tras restaurar.
  - `grep -ci error` da 3. Las tres son del logger `uvicorn.error` en nivel `INFO` (arranque), así que hay 0 `ERROR` y 0 trazas.
  - 0 apariciones de `apx1.`, `E2E-tope`, el correo del admin desechable, el correo de los logins fallidos y el coach bloqueado.
  - Límite: los logs de los contenedores de las corridas E2E se perdieron al recrear, y los documentos aleatorios de las specs no se conocen fuera de Playwright.

### Commits
- `59bf09d` fix(web): login de los helpers sin `id`.
- `43b4f09` fix(web): nombre del plan de las specs que ordena primero.
- `561ae32` fix(web): `users-activation` borra su coach.
- El de este bloque.

### Estado al terminar
- Stack `apex` normal (sin `compose.e2e.yml`) con las imágenes `7ebd75528265` y `1b2739fc20b7`. `.env` idéntico al previo.
- Admin desechable borrado (204, `deleted_at`).
- Quedan como datos de prueba los 30 planes `E2E-tope-d78ef5-*` y los planes, socios y ventas de las specs. Los planes se podrán limpiar cuando exista `DELETE /plans` (Sprint 4A).
- Quedan 120 cuentas `coach-*` viejas, varias con contraseñas derivables de la hora, en la base de desarrollo. Hay que darlas de baja en V12 o con un comando auditado.

## V12 · Baja de cuentas de prueba

Rama `feat/sprint-03-membresias-pagos`, 2026-10-28. Solo API y psql de lectura sobre `apex-db-1`; ningún SQL de escritura, ni `down -v`, ni imágenes reconstruidas, ni `.env`/`infra/`/`web/` tocados. Otro agente migraba el front a zod 4 en el mismo árbol; ninguno de sus archivos entra en este commit.

### Método
- `admin@ejemplo.local` no se tocó: se firmó un access suyo dentro de `apex-api-1` (`configure_security` + `create_access_token`, script temporal en `/tmp`). El access vivió solo en un archivo del scratchpad. Sin admin desechable.
- Al terminar, los scripts de `/tmp` del contenedor se borraron como root (`/tmp` vacío) y el access y los scripts se borraron del scratchpad.
- `DELETE /api/v1/users/{id}` por `8181`, uno cada ~2,2 s (≈27 por minuto, por debajo de la cubeta `admin-write` de 30), con reintento según `Retry-After` si llegaba un 429.

### Alcance
- Lista previa con psql de solo lectura: `email LIKE 'coach-%@apex.test' AND deleted_at IS NULL` = **120**, `created_at` de 2026-10-22 12:05 a 2026-10-25 18:03 UTC. `coach-mvjpe527@apex.test` está dentro de esas 120.
- `admin-e2e-%`: los cinco que existen ya tenían `deleted_at`; no había ninguno vivo.
- Fuera del alcance y sin tocar: `admin@ejemplo.local`, `system@apex.local` y tres coaches con dominio `@test.apex` (`coach-b3-smoke`, `coach-b7-smoke`, `coach-demo-mvjipju3`). No encajan en el patrón pedido; quedan anotados para decidir aparte.

### Resultado
- **120 × 204**, **0 × 429**, 0 otros códigos. De 21:03:23 a 21:08:20 UTC (4 min 57 s).
- psql después:
  - `coach-%@apex.test` vivos: **0** (antes 120).
  - `auth.users` vivos: **5** de 200 (antes 125 de 200): los cinco de fuera del alcance.
- Auditoría:
  - `audit.audit_log` pasó de seq 3955 a 4195: **+240 filas**, todas `update` sobre `auth.users`, 120 `record_id` distintos (dos por baja), y las 120 con `deleted_at` en `after`. Actor único: el admin real.
  - 0 filas `delete` (la baja es lógica). `insert` y `login` sin cambios (199 y 1138).
  - Aún no existe `sign-audit --verify` en el CLI. La cadena se verificó con `core.audit.verify_chain` sobre toda la tabla, leída en una transacción `READ ONLY` dentro del api: **`ok=True`, 4195 filas, sin ruptura**.

### Queda como dato de prueba
- Los 30 planes `E2E-tope-d78ef5-*`, "Mensual V50137" y los planes, socios y ventas de las specs. `DELETE /plans` llega en el Sprint 4A; hasta entonces no hay baja auditada para ellos.
- Los volcados `docs/scratch/sprint-03-antes-*.dump` (L-C) no son parte de este paso de V12; siguen pendientes de borrar al cerrar el sprint.
