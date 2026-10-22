# Enmiendas de la iteración 2 (tras `plan-critic`, veredicto RECHAZADO)

Estas enmiendas MANDAN sobre cualquier paso del plan que las contradiga. El ejecutor de cada slice las lee primero.

## E1 · Orden "gate y checkpoint" (sección 0, todos los slices)
`checkpoint-commit.sh` aborta si el árbol cambia después del sello (`checkpoint-commit.sh:51-54`; `docs/scratch/` no está en `.gitignore`). Orden obligatorio en cada slice: (1) Verde completo; (2) regenerar `docs/openapi.json` y `web/src/core/api/types.ts` si cambió el contrato; (3) escribir el bloque del slice en `docs/scratch/sprint-02.md` y cualquier doc (`DECISIONES.md`, `CLAUDE.md`, `ROUTES.md`, `BRECHAS.md`); (4) **último** `slice-gate.sh` del slice; (5) solo pasos que no tocan el árbol (Docker, psql, curl, Playwright contra el stack); (6) `checkpoint-commit.sh`. Si (5) obliga a cambiar código, se vuelve a (1).

## E2 · `.gitignore` en W0-1.3
Agregar `!.env.seed.example` después de `!.env.example` (`.env.*` lo excluiría y `git add -A` lo omitiría). `scripts/ci/check-key-files.sh` permite `.env.seed.example` igual que `.env.example`.

## E3 · Validador M-9 de `COOKIE_SECURE` (B2.3 y B2.6)
El validador exige `COOKIE_SECURE=true` o `ALLOW_INSECURE_COOKIE=true` cuando `ENV=production`. Llamadores existentes que construyen `Settings` en producción y deben actualizarse en el mismo slice: `tests/core/test_config.py` (`BASE`), `tests/core/test_health.py:88-96`, `tests/architecture/test_every_route_has_role.py` (`_produccion`), y cualquier otro que encuentre `grep -rn "ENV=production\|ENV\": \"production" api/tests`. `.env.example` lleva `ALLOW_INSECURE_COOKIE=true` comentado como riesgo aceptado P7 (LAN sin TLS) y `COOKIE_SECURE=false`.

## E4 · W0-1 (Nginx y smoke)
- W0-1.7 paso 6: el smoke existente es `scripts/ci/web-smoke.sh` (no existe `scripts/smoke/web-smoke.sh`).
- W0-1.2 (Rojo) incluye reemplazar las aserciones `Referrer-Policy = strict-origin-when-cross-origin` de `scripts/smoke/headers.sh:40` y `:60` y de `scripts/ci/test_nginx_conf.sh:45` por la política nueva (`no-referrer` en `/restablecer/`, `/activar/` e `index.html`; `strict-origin-when-cross-origin` se mantiene en `/api/`), y agregar el caso de la respuesta interna de `= /index.html` que sirve `/restablecer/<token>`: debe llevar `Referrer-Policy: no-referrer`, así que la cabecera se pone en `location = /index.html` (que es quien responde tras `try_files`) y no en un `location /restablecer/` que nunca responde.
- `docker network ls --format '{{.Name}} {{.ID}}'` + `docker network inspect` de cada red para confirmar que `172.30.0.0/24` está libre antes de fijar la subred; si choca, usar `172.31.0.0/24`. Rollback de W0-1: quitar el bloque `networks` y `ipv4_address` y `down`/`up` del proyecto.
- `env_file` con `required: false` exige Compose ≥ 2.24: verificar con `docker compose version` y anotar; si es menor, `.env.seed` se monta como `environment` del servicio `tools` desde variables `ADMIN_*` interpoladas con default vacío.

## E5 · Límites de intentos (B2 y V4)
Valores fijos, configurables en `Settings` con defaults de producción: `LOGIN_IP_LIMIT=5`/`LOGIN_IP_WINDOW_S=60`; `LOGIN_ACCOUNT_LIMIT=10` fallos/`900 s` (solo fallos, clave (correo normalizado, red /24 o /64), exento el último admin activo); bloqueo persistente `LOCK_AFTER_FAILURES=20`; `REFRESH_IP_LIMIT=60/60 s`; `RESET_IP_LIMIT=10/60 s`; `FORGOT_IP_LIMIT=5/60 s`; `LOGOUT_IP_LIMIT=30/60 s`; `limit_req` de Nginx en `/api/v1/auth/` a `60r/m burst=30 nodelay` (no 30). Perfil E2E: `.env` de CI y local con `LOGIN_IP_LIMIT=1000` y demás topes altos solo durante la validación V4 (variables de `.env`, `up -d api` para releerlas, y restaurar después); el smoke del "sexto intento" (B2.11) corre con el perfil de producción antes de cambiar el `.env`. `loginComo` en los E2E reutiliza la cookie entre pruebas del mismo rol (`storageState` de Playwright) para no repetir logins.

## E6 · B1 (configuración) y sesiones reales
La fixture `dos_sesiones` (dos sesiones con commit real y limpieza en `finally` de `settings.settings_sections` con `DISABLE TRIGGER USER` si aplica) nace en **B1.1**, antes de la prueba concurrente de B1.3. `LIMPIEZA_DE_SESION` de `tests/conftest.py` incluye `settings.settings_sections` desde B1 y, en los slices siguientes, `auth.refresh_tokens`, `auth.one_time_tokens`, `auth.users` (salvo `SYSTEM_USER_ID`), `members.members`, `plans.plans`.

## E7 · Bus de eventos en pruebas (B2.1 y B6)
`tests/conftest.py` llama `load_module_services()` al importarse (antes de cualquier foto del bus) y define la fixture autouse `restaurar_bus` que copia `{tipo: list(handlers)}` y lo restaura en el teardown. Se migran a esa fixture **todos** los usuarios de `clear_subscribers()`: `tests/core/test_events.py`, `test_events_db.py`, `test_events_router.py:35,43` y `tests/auth/test_seed.py:49`. Las pruebas que necesitan un bus vacío lo vacían dentro de su cuerpo y la fixture lo restaura.

## E8 · Observaciones aceptadas
- Tras editar `.env`, siempre `up -d api` (no `restart`): `env_file` se lee al crear el contenedor.
- `tokens_valid_after` se fija con `clock.now_utc()` truncado a segundos (nunca `now()` de SQL): el `iat` del JWT sale del reloj de la app.
- `Principal` recibe defaults en los campos nuevos (`must_change_password=False`, `tokens_valid_after=None`): hay construcciones posicionales en `tests/core/test_require_role.py`, `tests/auth/test_principal_loader.py` y `auth/service.py`.
- La regla `private_helper` se implementa en `tests/architecture/_imports.py` en B2.3 (paso explícito), con sus casos en `test_find_forbidden_imports.py`.
- Todo campo nuevo de `Settings` lleva default (o entra en `export_settings()` de `cli.py`).
- Cambiar `pyproject.toml` (marcador `perf` en B8) sí exige `up -d --build api`; se hace una sola vez al cerrar B8.
- Los E2E `perf` se marcan y los gates corren `-m "not perf"` salvo V4; `slice-gate.sh` acepta `PYTEST_ADDOPTS`.
- Documentos compartidos entre el backend y el worktree del front: el front NO edita `docs/scratch/sprint-02.md`, `DECISIONES.md`, `CLAUDE.md` ni `BRECHAS.md` (usa `docs/scratch/sprint-02-front.md`); `ROUTES.md` solo lo edita el front; `docs/openapi.json` y `types.ts` solo el backend (el front los toma del merge).
- Trazabilidad: tabla de los 10 riesgos de integración (§6.1-6.10 de la exploración) → slice: 6.1 B2.4 (commit explícito), 6.2 B2.4 (`current_actor.set` en rutas públicas), 6.3 B2.1 (`cargador_real`), 6.4 B7.3, 6.5 E7, 6.6 B2.1 (`reset_store` autouse), 6.7 B2.1, 6.8 B2.5 (D11), 6.9 B3 (router plano, D3), 6.10 B6 (`audit` en `MODULES` con `router.py` vacío y `find_spec` en `test_audited_tables`).
- S2-D10: el último admin activo queda exento del límite por cuenta y del bloqueo persistente; `cli unlock-user` limpia `locked_at` y `failed_login_count`; los contadores en memoria se limpian con `up -d api` (documentado en el runbook).


## E9 · Correcciones de la segunda crítica (APROBADO CON OBSERVACIONES)
- **E3:** toda variable nueva de `Settings` va como línea ACTIVA en `.env.example` (`test_env_example` ignora comentarios): `ALLOW_INSECURE_COOKIE=false`, `LOGIN_*`, `REFRESH_*`, `AUTH_ALLOWED_ORIGINS`, `LOGIN_MIN_DURATION_MS`, `REFRESH_REUSE_GRACE_S`. El riesgo aceptado P7 va en el comentario de al lado.
- **E4:** `Referrer-Policy` sale del snippet común `security-headers.conf`; cada location pone la suya: `no-referrer` en `location = /index.html` (responde toda la SPA, incluida `/restablecer/<token>`), `strict-origin-when-cross-origin` en `/assets`, `/fonts`, `/brand` y `proxy-api.conf`. `headers.sh:40` (`/`) espera `no-referrer`; `headers.sh:60` (`/api/v1/health`) sigue con `strict-origin-when-cross-origin`; `test_nginx_conf.sh` verifica esa partición y que ningún location quede sin `Referrer-Policy`. No existe `/activar/`: solo `/restablecer`.
- **E7:** en `tests/conftest.py`, `load_module_services()` corre ANTES del import de `principal_double` y de `register_principal_loader(principal_double)`, para que el doble quede registrado al final.
- **E8:** `PYTEST_ADDOPTS="-m 'not perf'"` no se usa en el gate de B8 (que lista `test_list_perf.py`) ni en V5; solo en los demás gates.
- **E5 nombres únicos en `Settings` y `.env.example`:** `LOGIN_IP_LIMIT`, `LOGIN_IP_WINDOW_S`, `LOGIN_ACCOUNT_LIMIT`, `LOGIN_ACCOUNT_WINDOW_S`, `LOGIN_LOCK_AFTER` (sustituye a `LOCK_AFTER_FAILURES`), `REFRESH_IP_LIMIT`, `RESET_IP_LIMIT`, `FORGOT_IP_LIMIT`, `LOGOUT_IP_LIMIT`. Clave de red del límite por cuenta: /24 en IPv4 y /64 en IPv6; la prueba "fallos desde la IP A no bloquean a la IP B" usa /24 distintos. El `limit_req` de Nginx admite `NGINX_AUTH_RATE` por entorno (default `60r/m`), con `limit_req_zone` parametrizado por `envsubst` en el `entrypoint` de la imagen web o un valor fijo documentado si eso complica la imagen: decide el ejecutor de W0-1 y lo anota.
# Plan de implementación · Sprint 2 · Identidad, configuración, shell del front, socios y planes

- Rama: `feat/sprint-02-identidad-config-socios-planes`. HEAD de partida: `482295f`.
- Veredicto de entrada: AMARILLO (`docs/ddd/impacto/sprint-02.md`). Este plan absorbe las 8 condiciones para VERDE; la sección 9 da el slice de cada una.
- Entradas leídas completas:
  - `docs/ddd/09_sprint_plan/SPRINT-02.md`;
  - `docs/ddd/impacto/sprint-02.md`;
  - `docs/ddd/blueprints/sprint-02-exploracion.md`;
  - `docs/ddd/blueprints/sprint-02-blueprint.md`;
  - `docs/ddd/blueprints/sprint-02-seguridad-diseno.md`;
  - `docs/scratch/sprint-01.md`;
  - `CLAUDE.md`;
  - `scripts/workflow/README.md`.
- Mandan este plan y su bloque de decisiones. Donde el blueprint y la revisión de seguridad chocan, manda la revisión; el ajuste se anota en el bloque "Sprint 2".
- Doctrina: TDD por slice (Rojo sobre stubs, Verde, gate, checkpoint), deuda técnica cero y ejecución al 100 % sin pausas intermedias.

## 0. Convenciones comunes a todos los slices

Alias de Compose usado en todo el plan:
`DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"`.

### P-MIG · Protocolo de migración nueva (B1, B2, B7, B9)

1. `pg_dump -Fc` de `apex-db-1` en `docs/scratch/sprint-02-antes-<rev>.dump`. Git lo ignora por `*.dump`.
2. Detener el api mientras se redacta: `$DC stop api`. El api monta `migrations/` por bind y corre `upgrade head` en cada arranque; un archivo a medio escribir se aplicaría o rompería el arranque.
3. Escribir `api/migrations/versions/<rev>.py` y su prueba `api/tests/migrations/test_<rev>.py`. Agregar la línea de import de `models` del módulo en `api/migrations/env.py`.
4. Probar contra `db_test`: `cd api && uv run pytest tests/core/test_migrations.py tests/migrations/test_<rev>.py -q`, con `TEST_DATABASE_URL` apuntando a `127.0.0.1:5443`.
5. Verificar un solo head con `cd api && uv run alembic heads`. También lo exige `test_single_head`, que nace en B1.
6. `$DC start api`. Esperar `healthy` y revisar `$DC exec api alembic current`: debe dar `<rev> (head)`.
7. Ciclo en `apex-db-1`: `$DC exec api alembic downgrade -1`, luego `$DC exec api alembic upgrade head`, luego `alembic current`.

Decisión de la condición 5: no se agrega un paso de ciclo de Alembic a CI. `test_migrations.py::test_downgrade_a_base_vacia_y_vuelta_a_head` y el nuevo `test_single_head` ya corren en el job `api`. Los desgloses US-069 T19 y US-078 T14 se corrigen para apuntar a esas pruebas.

### P-API · Contrato (todo slice de backend que cambie rutas)

1. `cd api && uv run python -m app.cli export-openapi ../docs/openapi.json`.
2. `cd web && npm run gen:api`.
3. `cd web && npx vitest run src/core/api/types.contract.test.ts`.
4. Correr dos veces la exportación: deben salir idénticas.
5. Los dos archivos regenerados entran en el checkpoint del slice. Solo los slices de backend tocan `types.ts`; el worktree del front hace rebase sobre la rama antes de cada slice que consuma un contrato nuevo.

### Gate y checkpoint

- Se corren todos los `slice-gate.sh` del slice seguidos, sin editar entre uno y otro. Si se edita algo, se repiten todos. El último gate es el que sella.
- `tests/architecture` corre en cada gate (A-5).
- Antes del checkpoint:
  - `git status` debe mostrar solo cambios del slice;
  - se agrega el bloque del slice a `docs/scratch/sprint-02.md` (Rojo, Verde, evidencia, desviaciones).
- Checkpoint: `bash scripts/workflow/checkpoint-commit.sh "S2-<id> <resumen>"`.

### Docker

- **api:** el bind de `src` con `--reload` recoge solo los cambios de código; se verifica con `$DC logs --tail 20 api`. Una migración nueva exige `restart`/`start api` (paso 6 de P-MIG). Un cambio en `pyproject.toml`, `uv.lock` o `alembic.ini` exige `$DC up -d --build api`.
- **tools:** usa COPY. Si cambió `cli.py` o código que el CLI usa, hay que correr `$DC build api` antes de `$DC run --rm tools <cmd>` (condición 8).
- **web:** usa COPY. Hace falta `$DC build web && $DC up -d web` antes de cualquier E2E o demo contra `http://localhost:8180` y tras cada cambio de Nginx (condición 8).

## 1. Bloque "Sprint 2" para `docs/ddd/DECISIONES.md`

Se agrega como sección nueva `## F. Sprint 2` en el checkpoint de S2-W0-1.

### Decisiones del blueprint (D1 a D34) con la opción elegida

- **S2-D1:** `UserStatus` con cinco valores. Orden: `deleted > locked > inactive > pending_activation > active`.
- **S2-D2:** la auditoría usa `table_name = 'auth.users'` y la redacción `'***'`. Se corrigen la demo y US-045/US-107.
- **S2-D3:** un router plano por módulo, con la ruta completa en cada decorador. `test_list_routes_use_page_params` recorre `effective_routes(create_app(...))`.
- **S2-D4:** `auth/service.py` queda como fachada. `auth/rules.py` (puras), `auth/tokens.py` (con sesión) y `auth/cookies.py` son privados del módulo. La regla `private_helper` en `tests/architecture/_imports.py` es obligatoria, no opcional.
- **S2-D5:** `core/validators.py` define `EmailAddress` sin `email-validator`, que tiene licencia Unlicense y queda fuera de la lista.
- **S2-D6:** se usan los nombres reales del código:
  - `dummy_verify`;
  - `normalize_for_index(value, kind)`;
  - `active_admin_id_by_email` se renombra a `active_user_id_by_email`, que exige `active` y excluye `SYSTEM_USER_ID` (L-4 del Sprint 1);
  - las excepciones de dominio no tocan `core/errors.py`.
- **S2-D7:** las escrituras auditadas van por ORM con `SELECT ... FOR UPDATE`. Hay dos excepciones, porque ninguna de las dos se audita:
  - `revoke_all` (un UPDATE masivo);
  - el incremento de `failed_login_count` (`UPDATE ... RETURNING`, L-10).
- **S2-D8:** la auditoría del login va por el evento `LoginAttempted`, con commit explícito antes del 401. El patrón actor_scope + flush + commit vive en una sola función, `auth/tokens.commit_failure(session)`.
- **S2-D9:** la migración `0005b_auth_security` (padre `0005_settings`) reemplaza la `0008` que sugería el análisis de impacto. Contenido:
  - `auth.users.must_change_password` (bool, por defecto false);
  - `auth.users.failed_login_count` (int ≥ 0, por defecto 0);
  - `auth.users.tokens_valid_after` (timestamptz, nulo; H-3);
  - `auth.refresh_tokens.family_started_at` (timestamptz NOT NULL, `server_default now()`; L-4).
- **S2-D10:** el límite por intentos queda corregido por H-4:
  1. Solo cuentan los fallos. Se comprueba el contador antes de argon2 sin sumar y se suma al fallar.
  2. Clave `(correo normalizado, ip_bucket_key)`: 10 fallos por 900 s.
  3. Tope global por cuenta: 100 fallos por 3.600 s.
  4. Bloqueo persistente (`locked_at`) a los 20 fallos consecutivos.
  5. Al último admin activo solo le rigen el límite por IP y argon2.
  6. Settings nuevas: `LOGIN_ACCOUNT_LIMIT=10`, `LOGIN_ACCOUNT_WINDOW_S=900`, `LOGIN_ACCOUNT_GLOBAL_LIMIT=100`, `LOGIN_ACCOUNT_GLOBAL_WINDOW_S=3600`, `LOGIN_LOCK_AFTER=20`.
  7. `unlock` por API limpia los contadores en memoria de esa cuenta (`ratelimit.forget`). `cli unlock-user` corre en otro proceso; el runbook documenta que `restart api` limpia la memoria.
- **S2-D11:** `refresh_current(session)` corre dentro de `current_user` tras validar el token. Se quita la dependencia global de `main.include_module_routers` (M-3 del Sprint 1).
- **S2-D12:** `ADMIN_*` solo en `tools`. `SeedSettings` lee `.env.seed`; se crea `.env.seed.example` con valores vacíos (L-9). `seed` rechaza el literal `cambiar-esto`. `seed_admin` siembra con `must_change_password=true`; `--no-force-change` solo con `ENV=dev`, leído de `Settings`.
- **S2-D13 (reemplazada por M-9):** `COOKIE_SECURE=false` por defecto en v0.1. Con `ENV=production` se exige `COOKIE_SECURE=true`, salvo `ALLOW_INSECURE_COOKIE=true` explícito (validador de `Settings`).
- **S2-D14:** `GET /auth/me` consulta la base: usuario más `settings.service.gym_name`.
- **S2-D15:** las secciones habilitadas son `gym`, `privacy` y `memberships`.
  - Las demás responden 404 `section_not_available`.
  - Las rutas tipadas se declaran antes que la genérica.
  - `PATCH` reemplaza la sección completa.
- **S2-D16:** sí a `document_type` (`CC`, `CE`, `TI`, `PA`; por defecto `CC`), con dos correcciones de seguridad:
  - sin columna `notes` (M-5);
  - `MemberCreate.data_consent: bool`, y el servidor fija `data_consent_at = clock.now_utc()` (M-4).
- **S2-D17:** `auth.users` no tiene nombre. La tabla y el panel usan el correo, con `// DESIGN-GAP:`; `display_name` llega con US-110.
- **S2-D18:** activar es `POST /auth/reset`: el token lleva su `purpose`, responde 204 y no inicia sesión. Nace la ruta `/cambiar-clave` con `// DESIGN-GAP:`.
- **S2-D19:** `proveedor_local`, `sin_llaves` y `bus_listo` suben a `tests/conftest.py`. El cliente HTTP de pruebas no corre el lifespan.
- **S2-D20:** `test_no_sensitive_in_logs.py` se implementa en B7. El caso `reveal` queda como prueba aparte saltada, con dueño S3-B10 (US-074).
- **S2-D21:** `test_audited_tables` importa `models` solo si `find_spec` lo encuentra. `audit` entra en `MODULES` con `router.py` vacío. Orden final: `("auth","settings","audit","members","plans")`.
- **S2-D22:** se agregan dos dependencias, con `npm run licenses` y `NOTICE`:
  - sí a `@hookform/resolvers` (MIT), en F3;
  - `@axe-core/playwright` (MPL-2.0 sin modificar, solo desarrollo), en F5, con su línea en `scripts/ci/licenses-exceptions.txt`.
- **S2-D23:** `web/src/config/routeTable.ts` es la única tabla de rutas. `homeFor`, `canAccessRoute` y `safeNext` viven en `core/auth/routeAccess.ts` y no comparan roles con literales: `homeFor` usa `can(role, "portal.view")`, una acción nueva que solo tiene `member` en `permissions.ts`. No se amplía el `ignores` de la regla de literales (resuelve la última parte de la condición 6).
- **S2-D24:** `StatusTag` acepta `account`, con `ACCOUNT_LABELS` y `ACCOUNT_TONES`.
- **S2-D25:** `InicioPage` mínima, con `// DESIGN-GAP:`, hasta `GET /dashboard` del Sprint 3.
- **S2-D26:** en el front `/planes` es solo para admin (`plans.view`). El API deja al coach `GET /plans?active=true` y `GET /plans/{id}` de planes activos.
- **S2-D27:** el marcador `perf` se registra en `api/pyproject.toml` (B8). La prueba de 1.000 socios corre en el gate de B8 y en `run-gates.sh`.
- **S2-D28 (reemplazada por M-2):** gracia de 10 s en el reuso de refresh (`REFRESH_REUSE_GRACE_S=10`). Dentro de la gracia responde 401 `invalid_refresh` sin revocar la familia; fuera de ella es reuso real (N-13).
- **S2-D29 (reemplazada por M-3):**
  - `Referrer-Policy: no-referrer` en `snippets/security-headers.conf`, para todo el sitio;
  - no se crea un `location` especial para `/restablecer/`;
  - `log_format apex` sigue con `$uri`;
  - una prueba con `curl` demuestra que la línea de log de `/restablecer/<token>` no contiene el token;
  - ningún `log_format` usa `$request_uri` ni `$args`.
- **S2-D30:** `PASSWORD_MAX_LENGTH = 128` y razón `too_long` (L-5 del Sprint 1). Topes en los schemas:
  - `max_length=128` en `LoginIn`, `ChangePasswordIn` y `ResetIn.new_password`;
  - `ResetIn.token` de 20 a 200 caracteres;
  - `ForgotIn.email` hasta 254.
- **S2-D31:** `test_reveal_entry.py` usa `uuid4()` (no existe fábrica de socios en B6). En S3-B10 se cambia a la fábrica.
- **S2-D32:** sí a nombre de plan único sin distinguir mayúsculas: `uq_plans_name_alive` sobre `lower(btrim(name)) WHERE deleted_at IS NULL`, con pre-chequeo igual. Topes:
  - `price_cop` de 1 a 1.000.000.000;
  - `duration_days` de 1 a 3.650;
  - `class_count` de 1 a 1.000.
- **S2-D33:** `session.ts` se reparte entre F2 (almacén y `restoreSession`) y F3 (refresh coordinado, logout y puente con el cliente).
- **S2-D34:** tras el 201 el alta va a `/socios` con aviso. El 409 enlaza a `/socios/{existing_id}`, que da NotFound hasta S3-B9/S3-F1. Nunca se usa `?q=<documento>`.

### Decisiones de la revisión de seguridad del diseño

- **S2-D35 (H-1):** `POST /auth/logout` se autentica por la cookie, no por el Bearer.
  - Entra en `PUBLIC_ROUTES`, que pasa a 8 rutas.
  - Lleva `rate_limit("logout")` y `require_same_origin`.
  - Revoca el refresh de la cookie si existe, siempre responde 204 y siempre borra la cookie.
  - En el front, un fallo de red o un 5xx no se presenta como éxito.
- **S2-D36 (H-2):** en v0.1, `forgot` no escribe nada.
  - Normaliza el correo y aplica `ratelimit.enforce("forgot-account", ...)` además de `rate_limit("forgot")` por IP.
  - Aplica el piso de duración de S2-D39 y deja un log sin el correo.
  - Responde siempre 204. El emisor real llega con US-131.
- **S2-D37 (H-3):** `auth.users.tokens_valid_after` corta los access ya emitidos.
  - Se fija con `date_trunc('second', now)` dentro de `revoke_all`, así lo usan cambio de contraseña, reset, cerrar sesiones, bloqueo, baja y reuso.
  - `Principal` lo recibe del cargador, y `current_user` responde 401 `unauthorized` si `iat < tokens_valid_after`.
  - Ventana residual aceptada: menos de 1 s, para tokens emitidos en el mismo segundo antes de la revocación.
  - `POST /auth/me/password` responde 200 `AccessTokenOut` (`access_token`, `token_type`, `expires_in`) con un access nuevo. El front lo reparte a las demás pestañas por `apex-auth`.
- **S2-D38 (M-1):** dependencia `require_same_origin` en `auth/cookies.py` para login, refresh y logout.
  - Compara `Origin` (o `Referer` si falta) con `AUTH_ALLOWED_ORIGINS`; si esa lista está vacía, usa el origen de `FRONT_BASE_URL`. También acepta `Sec-Fetch-Site: same-origin|none`.
  - Sin ninguna de las tres cabeceras responde 403 `forbidden` sin tocar la cookie.
  - Los scripts de smoke y la fixture `cabeceras` envían `Origin`.
- **S2-D39 (M-6):** se nivela el tiempo de login y forgot.
  - Piso `LOGIN_MIN_DURATION_MS`; se mide en B2 como 1,5 veces la mediana de argon2 más commit dentro del contenedor y se fija su valor por defecto.
  - Se aplica a toda respuesta 401 de login y a todo forgot, con un `sleeper` inyectable para que las pruebas no duerman.
  - Un usuario sin hash (pendiente) usa `dummy_verify`, nunca `verify_password(None, ...)`.
- **S2-D40 (M-7):** un solo predicado `rules.account_may_authenticate(user)` y su espejo SQL `rules.AUTH_FILTER`, usados por el cargador, login y refresh.
  - `is_one_time_token_usable` reutiliza el predicado, excepto la exigencia de hash cuando el propósito es `activate`.
  - `status_filter` es el espejo SQL de `user_status`. Ambos se prueban en matriz contra los cinco estados.
- **S2-D41 (M-8):** el `q` de las listas (`/socios` y `/sistema/usuarios`) vive en estado local con debounce y nunca en la URL. En la URL quedan solo filtros, `sort`, `limit` y `offset`.
- **S2-D42:** los LOW de la revisión del diseño, todos dentro del sprint:
  - **L-1:** límite por usuario autenticado de 60 por minuto en `POST /members` (B7) y en `GET /members` con `q` (B8).
  - **L-2:** `CreateUserIn.role` es `Literal["admin","coach"]`, sin `member_id`, hasta el portal (B3).
  - **L-3:** un documento, teléfono o correo que se normaliza a vacío da 422 con `field` (B7).
  - **L-4:** tope absoluto de 30 días por familia (`REFRESH_ABSOLUTE_TTL_DAYS=30`, desde `family_started_at`) y purga oportunista en cada login de los refresh del usuario vencidos hace más de 30 días (B2).
  - **L-5:** `safeNext` rechaza `\` y caracteres de control (F2).
  - **L-6:** los mensajes de `apex-auth` llevan secuencia monótona, y un `token` se ignora tras un logout (F3).
  - **L-7:** las mutaciones con `activation_url` usan `gcTime: 0` y `reset()` al cerrar el panel o el modal (F4a, F4b).
  - **L-8:** `LoginAttempted` lleva `ip` y `user_agent` (hasta 120 caracteres) y la fila `login` los guarda en `after`, nunca el correo tecleado (B2, B6).
  - **L-9:** el ejemplo de `.env.seed` va vacío y `seed` rechaza el literal del ejemplo (W0-1, B2).
  - **L-10:** el incremento de fallos es atómico (B2).
  - **L-11:** un almacén por tipo de clave (`ip`, `account`, `account-global`, `user`), cada uno con tope propio y expulsión O(1) con `OrderedDict` (B2).
  - **L-12:** `client_max_body_size 16k` en `/api/v1/auth/` (W0-1); `rate_limit` en refresh, reset y logout (B2, B4); un 429 no limpia la sesión del front (F3).
  - **L-13:** `resend-link` responde 409 `user_not_eligible` sobre la propia cuenta del emisor y sobre otros admins activos con contraseña. Para esos casos, `cli issue-reset-link <correo> --as <correo>` (B4). `PasswordChanged` lleva `via_link_issued_by` (el `created_by` del token) y la auditoría lo registra (B6).

### Contradicciones de contrato cerradas (exploración e impacto, condición 6)

- **S2-D43:** el login emite `LoginAttempted` y `audit` se suscribe. Se corrige US-107 T1.
- **S2-D44:** el cliente usa `credentials: "same-origin"`. Se corrigen US-042 T12 y US-044 T6.
- **S2-D45:** las funciones canónicas de settings son `settings.service.memberships_policy()`, `current_privacy_version()` y `gym_name()`. Se corrigen las referencias de US-089 y US-149.
- **S2-D46:** la ruta canónica en v0.1 es `POST /api/v1/auth/me/password`, no `/me/password`. Se anota en `docs/BRECHAS.md`.
- **S2-D47:** no existe `/auth/activate`; las rutas públicas exactas son `login`, `refresh`, `logout`, `forgot` y `reset`.
- **S2-D48:** la rama real es `feat/sprint-02-identidad-config-socios-planes`. Se corrige `SPRINT-02.md`.
- **S2-D49:** la revocación de sesiones queda auditada por `SessionsRevoked`, porque `refresh_tokens` no se audita. `last_login_at` sale de la auditoría por `__audit_exclude__`; la fila `login` la deja el evento.
- **S2-D50:** el login muestra "APEX", porque `gym_name` solo llega autenticado. Va con `// DESIGN-GAP:`.
- **S2-D51:** el comando de desarrollo de uvicorn sigue sin `--proxy-headers`. La IP real la resuelve `core/ratelimit.client_ip` con `TRUSTED_PROXIES`. Se documenta en el runbook.
- **S2-D52:** CI gana el job `e2e-stack`. No se renombra ningún check protegido.
- **S2-D53:** existe `tests/architecture/test_service_import_graph.py` (nace en B3). Exige un grafo acíclico entre los `service.py` (`audit → auth → settings`) y deja la lista blanca de imports perezosos vacía hasta el Sprint 3.

## 2. Fixtures y utilidades de prueba compartidas

Cada una entra en el primer slice que la necesita.

- **B1:**
  - en `api/tests/conftest.py`:
    - `proveedor_local`, `sin_llaves` y `bus_listo`, movidas desde `tests/crypto/conftest.py`, que deja de definirlas;
    - `reloj` (`FrozenClock` `2026-10-21T15:00:00Z` y `reset_clock`);
    - `argon2_rapido`;
    - `cargador_real` (registra `load_active_principal` y restaura `principal_double`);
    - `app_http` (`create_app(..., run_migrations_on_startup=False)` sin lifespan, `configure_security`, `configure_provider`, `get_session` sustituido por la sesión de la prueba con commit o rollback al salir, `httpx.AsyncClient(ASGITransport)`);
    - `usuario_real` (fábrica que devuelve `UsuarioPrueba(user, password, token)`);
    - `cabeceras(usuario)` (Bearer más `Origin` del front);
  - `api/tests/factories/__init__.py` con `FACTORIES` y `api/tests/factories/users.py` con `make_user`;
  - `settings.settings_sections` entra en `LIMPIEZA_DE_SESION`.
- **B2:**
  - autouse `reset_rate_limit` (`ratelimit.reset_store()` antes y después de cada prueba);
  - autouse `restaurar_bus` (copia y restaura `events._subscribers`). `tests/core/test_events.py` y `tests/core/test_events_db.py` dejan su `clear_subscribers()` global y pasan a usarla;
  - `capturar_eventos(*tipos)` (quita solo su propia suscripción);
  - `dos_sesiones(engine)` (commit real, limpia lo que escribe);
  - `sleeper_nulo` (anula el piso de S2-D39);
  - en `LIMPIEZA_DE_SESION`: `auth.refresh_tokens`, `auth.one_time_tokens` y los `auth.users` del dominio `@test.apex`.
- **B3:** `make_one_time_token(session, user, purpose, *, expires_in)` en `factories/users.py`.
- **B7:** `api/tests/factories/members.py` (`KNOWN`, `make_member`, `make_members`); `FACTORIES["members.members"]`; `members.members` en la limpieza.
- **B8:** marcador `perf` en `[tool.pytest.ini_options].markers` de `api/pyproject.toml`.
- **B9:** `api/tests/factories/plans.py`; `plans.plans` en la limpieza.
- **W0-1 y front:**
  - `web/tests/e2e/helpers/stack.ts` (W0-1): `loginComo`, `crearCoach`, `VIEWPORTS`, `captura` y `datosDeBase()`, que lee `E2E_ADMIN_EMAIL` y `E2E_ADMIN_PASSWORD`;
  - `web/src/test/server.ts` (`fetch` simulado y `renderWithProviders`) en F1;
  - `web/src/test/session.ts` (`signInAs`) en F2.

## 3. Paralelismo: cuándo lanzar cada slice de front

El backend corre en serie en la rama principal. Un agente de front corre F1 a F8, en orden, en un worktree bajo `.claude/worktrees/`, con `SLICE_BASE` fijado a la base del worktree. Antes de un slice que consume un contrato nuevo, ese worktree hace rebase sobre la rama del sprint para traer `docs/openapi.json` y `web/src/core/api/types.ts`. Al cierre se fusiona como en el Sprint 1.

- **F1 (layouts):** no depende de endpoints. Se lanza junto con S2-W0-1, después del checkpoint de W0-1 por `playwright.config.ts`.
- **F2 (rutas y guardas):** no depende de endpoints. Va después de F1.
- **F8 (temas y kit):** no depende de endpoints, pero va al final porque el catálogo incluye los componentes de F1 a F7.
- **F3 (login, refresh, logout):** se lanza tras el checkpoint de B2. El tipo `MeOut` llega en B3; mientras tanto las pruebas lo simulan. `login.spec.ts` y `refresh-two-tabs.spec.ts` (proyecto `stack`) se corren cuando existan B2 y B3, o en la validación del sprint.
- **F4a:** tras el checkpoint de B4 (también necesita B3).
- **F4b:** tras el checkpoint de B5.
- **F5:** tras el checkpoint de B1.
- **F6:** tras el checkpoint de B8 (también necesita B7).
- **F7:** tras el checkpoint de B9.
- **E2E del proyecto `stack`:** `role-guards.spec.ts` necesita B1 a B3; `users-activation.spec.ts` B3 y B4; `settings-gym.spec.ts` B1 y B3. Se corren en el slice si el backend ya existe; si no, en la validación del sprint.

## 4. Wave 0

### S2-W0-1 · Playwright contra el stack, Nginx, red fija y `.env.seed`

- **Historias:** tareas DevOps de US-068 y US-048.
- **Cierra:** M-1 (resto), M-3 (parte de Nginx), L-1 y la parte de Compose de M-8, todas del Sprint 1; M-3, L-9 y L-12 (Nginx) de la revisión del diseño; condiciones 3 (parte de infraestructura), 4, 6 y 8.
- **Depende de:** nada.
- **Migración:** ninguna.

**W0-1.1 · Documentación de contrato (T-DOC, condición 6)**
- Agregar la sección `## F. Sprint 2` a `docs/ddd/DECISIONES.md` con el bloque de la sección 1.
- Corregir los desgloses:
  - US-042 T12 y US-044 T6: `same-origin`;
  - US-042 T16: `COOKIE_SECURE`;
  - US-107 T1: evento;
  - US-069 T19 y US-078 T14: `test_migrations.py`;
  - US-089 y US-149: funciones canónicas.
- `SPRINT-02.md`: nombre de la rama; demo con `***` y `auth.users`; 8 rutas públicas; migración `0005b` en la lista de migraciones.
- `docs/BRECHAS.md`: usuarios sin nombre, `/auth/me/password`, `/cambiar-clave`, campos de `Socio_Form` (sin notas, foto ni portal), `Config` en pestañas, nombre del gimnasio en el login.
- Nota al inicio del blueprint: "corregido por `sprint-02-plan.md`, decisiones D13, D28, D29 y 7.1".
- `CLAUDE.md`: `.env.seed` en la estructura.
- Crear `docs/RUNBOOK.md`: seed con `.env.seed` y borrado posterior, `COOKIE_SECURE` y `ALLOW_INSECURE_COOKIE`, divergencia de `--proxy-headers`.
- Crear `docs/scratch/sprint-02.md` con la línea base (443 ok y 4 saltadas en api; 593 ok en web).

**W0-1.2 · Rojo de infraestructura**
- `scripts/ci/test_nginx_conf.sh`:
  - `limit_req zone=apex_auth` en `location /api/v1/auth/`;
  - `client_max_body_size 16k` en ese location;
  - `error_page 429` con el envelope JSON;
  - `Cache-Control "no-store" always` y `Pragma no-cache` en `proxy-api.conf`;
  - `form-action 'self'` en la CSP del index y `'none'` en la del api;
  - `Referrer-Policy: no-referrer` en `security-headers.conf`;
  - ningún `log_format` con `$request_uri` ni `$args`;
  - ningún `location` de `/restablecer/`.
- `scripts/smoke/headers.sh`:
  - `no-store` en `/api/v1/health`;
  - `form-action` en la CSP del index;
  - `no-referrer` en `/restablecer/abc`;
  - una ráfaga de 45 POST a `/api/v1/auth/login` da al menos un 429 con el envelope;
  - `curl /restablecer/TOKENPRUEBA` y luego `$DC exec web` sobre el access log: la línea no contiene `TOKENPRUEBA`.
- `scripts/ci/test_compose_config.sh`:
  - subred `172.30.0.0/24` y `web` en `172.30.0.10`;
  - `TRUSTED_PROXIES` de `.env.example` igual a esa IP;
  - `tools` con `.env.seed` y `required: false`;
  - `api` y `worker` sin `.env.seed`.
- Casos de `check-key-files.sh`: bloquea `.env.seed` y permite `.env.seed.example`.
- Del lado web:
  - `web/tests/unit/playwright-config.test.ts`: dos proyectos; `stack` sin `webServer` y con `baseURL` desde `E2E_BASE_URL`;
  - `web/tests/unit/dev-proxy.test.ts`: `server.proxy['/api']`.
- Correr todo y confirmar que falla.

**W0-1.3 · Verde de infraestructura**
- `infra/compose.yml`:
  - `networks.default.ipam.config[0].subnet: 172.30.0.0/24`;
  - `web.networks.default.ipv4_address: 172.30.0.10`;
  - `tools.env_file: [../.env, {path: ../.env.seed, required: false}]`.
- `infra/nginx/default.conf`:
  - `limit_req_zone $binary_remote_addr zone=apex_auth:10m rate=30r/m`;
  - `limit_req_status 429`;
  - `location /api/v1/auth/ { limit_req zone=apex_auth burst=10 nodelay; client_max_body_size 16k; include snippets/proxy-api.conf; }`;
  - `location @rate_limited` con el envelope y `Retry-After 60`;
  - `form-action 'self'` en la CSP del index.
- `snippets/proxy-api.conf`: `no-store`, `Pragma no-cache` y CSP con `form-action 'none'`.
- `snippets/security-headers.conf`: `Referrer-Policy: no-referrer`.
- `.gitignore` y `scripts/ci/check-key-files.sh`: `.env.seed`.
- Crear `.env.seed.example` con `ADMIN_EMAIL=` y `ADMIN_INITIAL_PASSWORD=` vacíos, y la nota de borrar el archivo tras el primer seed.
- `.env.example`:
  - `TRUSTED_PROXIES=172.30.0.10` (solo la IP de Nginx);
  - comentario de `FRONT_BASE_URL`: su puerto debe coincidir con `WEB_PORT`;
  - un solo comentario coherente para `CORS_ORIGINS` (C3);
  - limpiar el comentario obsoleto de `TRUSTED_PROXIES`.
  - Las variables `ADMIN_*` se quedan hasta B2: `test_env_example` falla si `Settings` las declara y el ejemplo no las documenta.
- `scripts/ci/compose-smoke.sh`: genera un `.env.seed` efímero con una contraseña aleatoria antes de `tools seed` y lo borra al terminar.

**W0-1.4 · Entorno local (no versionado; condición 4)**
- En `.env`:
  - `FRONT_BASE_URL=http://localhost:8180`;
  - `TRUSTED_PROXIES=172.30.0.10`.
- Mover `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` del `.env` a un `.env.seed` local. Desde aquí el api deja de recibirlas; `tools` las sigue leyendo por su `env_file`.

**W0-1.5 · Verde de herramientas web**
- `web/playwright.config.ts`:
  - proyecto `preview`, como hoy: specs `smoke`, `csp`, `panel-layout`, `layouts` y `kit`;
  - proyecto `stack`: sin `webServer`, `baseURL` desde `E2E_BASE_URL`, specs `login`, `users-activation`, `role-guards`, `settings-gym`, `refresh-two-tabs` y `logout-expired`;
  - capturas en `test-results/captures/<tema>-<ancho>.png`.
- Crear `web/tests/e2e/helpers/stack.ts`.
- `web/package.json`: script `e2e:stack`.
- `web/vite.config.ts`: `server.proxy` de `/api` hacia `process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000"` (C8). Si el hook `config-protection` bloquea la edición, se detiene y se informa con opciones; no se rodea.

**W0-1.6 · CI**
- Job `e2e-stack` en `.github/workflows/ci.yml`, con `needs: images`:
  1. `cp .env.example .env`;
  2. `.env.seed` efímero;
  3. `$DC up -d --build`;
  4. `tools init-keys`;
  5. esperar al api `healthy`;
  6. `tools seed --no-force-change`, ejecutado solo si `tools seed --help` lista esa opción;
  7. `npx playwright install --with-deps chromium`;
  8. `E2E_BASE_URL=http://localhost:${WEB_PORT:-80} npx playwright test --project=stack --pass-with-no-tests`;
  9. subir `web/test-results/captures/` como artefacto.

**W0-1.7 · Docker**
1. `$DC down`, sin `-v`, para recrear la red con subred fija. Los volúmenes se conservan; `db_test` es tmpfs y no importa.
2. `$DC up -d --build`.
3. `$DC run --rm tools init-keys` (idempotente).
4. Esperar los cuatro servicios `healthy`.
5. `$DC exec api alembic current` debe dar `0004_auth (head)`.
6. `bash scripts/smoke/headers.sh` y `scripts/smoke/web-smoke.sh` contra `http://localhost:8180`.
7. `docker network inspect`: `web` está en `172.30.0.10`.

**W0-1.8 · Gate**
1. `bash -n scripts/ci/*.sh scripts/smoke/*.sh scripts/workflow/*.sh`.
2. `bash scripts/ci/test_nginx_conf.sh`.
3. `bash scripts/ci/test_compose_config.sh`.
4. Las pruebas de `check-key-files.sh`.
5. `bash scripts/smoke/headers.sh` contra 8180. `compose-smoke.sh` corre en el job `images`, porque usa los puertos de `.env.example`.
6. `bash scripts/workflow/slice-gate.sh web/app tests/unit/playwright-config.test.ts tests/unit/dev-proxy.test.ts tests/unit/index-html.test.ts`.
7. Al final, para sellar: `bash scripts/workflow/slice-gate.sh core/config tests/core/test_env_example.py tests/core/test_config.py`.

**W0-1.9 · Checkpoint**
`checkpoint-commit.sh "S2-W0-1 red fija del proxy, nginx endurecido, env.seed y playwright contra el stack"`. Incluye el bloque de `DECISIONES.md`.

## 5. Backend

### S2-B1 · Configuración del gimnasio

- **Historias:** US-054, US-055 (backend), US-057 y US-058.
- **Depende de:** W0-1.
- **Migración:** `0005_settings` (`down_revision = "0004_auth"`).
- **Cierra:** condiciones 5 y 7 (fixtures HTTP); S2-D15 y S2-D45.

**B1.1 · Kit de fixtures de la sección 2 (B1)**
Mover las fixtures del bus y crear `reloj`, `argon2_rapido`, `cargador_real`, `app_http`, `usuario_real`, `cabeceras`, `factories/__init__.py` y `factories/users.py`. Sumar la tabla nueva a la limpieza. Verificar que nada se rompió con `cd api && uv run pytest tests/crypto -q`.

**B1.2 · Stubs**
- `api/src/app/modules/settings/{__init__,models,schemas,exceptions,service,router}.py`, con `NotImplementedError` en los casos de uso.
- `test_single_head` en `api/tests/core/test_migrations.py` (condición 5).

**B1.3 · Rojo**
- En `tests/settings/`: `test_settings_rules.py`, `test_settings_service.py`, `test_settings_router.py`, `test_gym_schema.py`, `test_gym_router.py`, `test_privacy_schema.py`, `test_privacy_service.py`, `test_privacy_router.py`, `test_memberships_policy.py`, `test_memberships_schema.py`, `test_memberships_router.py`.
- `tests/architecture/test_settings_no_secrets.py`.
- `tests/architecture/test_no_cross_models.py`, ampliada: ningún módulo distinto de `settings` importa `settings.models`.
- `tests/migrations/test_0005_settings.py`.
- Casos que no hay que olvidar:
  - dos primeros guardados concurrentes (`dos_sesiones` llega en B2; aquí, dos sesiones reales de `engine`) dejan una fila y un 409;
  - un valor inválido no cambia la fila ni crea auditoría;
  - el coach recibe 403 en las 8 rutas;
  - `tv`, `hours`, `channels`, `classes` y `payment_methods` dan 404;
  - 181 en `max_freeze_days_per_membership` da 422 con `field = "value.max_freeze_days_per_membership"`;
  - `current_privacy_version` es `None` sin fila y `"2026-10"` después;
  - `MembershipsPolicy` es inmutable.
- Confirmar el rojo.

**B1.4 · Migración**
`0005_settings` por P-MIG:
- tabla `settings.settings_sections`;
- `CHECK key_valid` (8 claves) y `CHECK version_non_negative`;
- `uq_settings_sections_key`;
- sin filas sembradas y sin FK;
- import de `settings.models` en `env.py`.

**B1.5 · Verde**
Implementar `models`, `schemas`, `exceptions`, `service` y `router` según el blueprint B1. `MODULES = ("auth","settings")`.

**B1.6 · Contrato**
P-API.

**B1.7 · Gate**
1. `bash scripts/workflow/slice-gate.sh crypto`.
2. `bash scripts/workflow/slice-gate.sh architecture tests/core/test_migrations.py tests/migrations/test_0005_settings.py`.
3. Al final, para sellar: `bash scripts/workflow/slice-gate.sh settings` con los 11 archivos de `tests/settings/` de B1.3 más `tests/architecture/test_settings_no_secrets.py` y `tests/architecture/test_no_cross_models.py`.

**B1.8 · Docker**
Pasos 6 y 7 de P-MIG; `alembic current` debe dar `0005_settings`. Además, `$DC logs --tail 20 api` sin errores.

**B1.9 · Checkpoint**
`"S2-B1 configuración del gimnasio"`.

### S2-B2 · Sesión: login, refresh y logout

- **Historias:** US-042, US-043 y US-044.
- **Depende de:** W0-1 y B1.
- **Migración:** `0005b_auth_security` (`down_revision = "0005_settings"`).
- **Cierra:**
  - del Sprint 1: M-2, M-3 (keyring), M-8 (código y migración), L-4, L-5 y L-8;
  - de la revisión del diseño: H-1, H-3 (columna y `current_user`), H-4, M-1, M-2, M-6, M-7 y M-9;
  - los LOW L-4, L-8 (evento), L-9, L-10, L-11 y L-12 (refresh y logout);
  - condición 3 (parte de la aplicación) y condición 7.
- Este slice deja lista toda la base común de sesión.

**B2.1 · Fixtures de la sección 2 (B2)**
Incluye el cambio de `test_events.py` y `test_events_db.py` a `restaurar_bus`. Verificar con `pytest tests/core -q`.

**B2.2 · Stubs**
- `core/validators.py`;
- `ratelimit`: `ip_bucket_key`, `enforce`, `forget`;
- `security`: `PASSWORD_MAX_LENGTH`, campos nuevos de `Principal`;
- `crypto/keyring.refresh_current`;
- `config`: `SeedSettings`;
- `auth/{rules,tokens,cookies}.py`;
- funciones nuevas de `auth/service.py`.

**B2.3 · Rojo de core**
- `tests/core/test_validators.py`.
- `tests/core/test_ratelimit.py`: clave /64; `enforce` sin la clave en el log; almacenes por tipo con tope propio; expulsión O(1); `forget`.
- `tests/core/test_passwords.py`: `too_long` a los 129 caracteres.
- `tests/core/test_require_role.py`:
  - `refresh_current` solo tras un token válido;
  - las rutas públicas no tocan el keyring;
  - `iat < tokens_valid_after` da 401 `unauthorized`.
- `tests/crypto/test_refresh_current.py`.
- `tests/core/test_config.py`:
  - `SeedSettings`;
  - validador de `COOKIE_SECURE` y `ALLOW_INSECURE_COOKIE` (M-9);
  - las variables `LOGIN_*`, `AUTH_ALLOWED_ORIGINS`, `REFRESH_REUSE_GRACE_S`, `REFRESH_ABSOLUTE_TTL_DAYS` y `LOGIN_MIN_DURATION_MS`.
- `tests/core/test_env_example.py`: sin `ADMIN_*`, con las nuevas, `ADMIN_*` en `NON_API_ENV_VARS`.
- `tests/architecture/test_every_route_has_role.py`: lista blanca de 8 rutas; logout con límite de intentos.
- `tests/architecture/test_no_cross_models.py`: regla `private_helper` (S2-D4).
- `tests/migrations/test_0005b_auth_security.py`.

**B2.4 · Rojo de auth y CLI**
- `tests/auth/test_pure_login.py`: `account_may_authenticate` sobre los 5 estados más el usuario técnico; `should_auto_lock` con su excepción; `is_refresh_usable`; `is_reuse` con gracia; tope absoluto de 30 días.
- `tests/auth/test_auth_filter_matrix.py` (M-7): `AUTH_FILTER`, cargador, `login` y `refresh` coinciden en los 5 estados; `status_filter` coincide con `user_status`.
- `tests/auth/test_login_service.py`:
  - los casos del blueprint;
  - H-4: solo cuentan fallos; 10 fallos desde la IP A no impiden entrar desde la IP B; tope global; el último admin queda exento;
  - M-6: `verify_password` o `dummy_verify` se llama exactamente una vez por rama; un pendiente usa `dummy_verify`; el piso se aplica con el `sleeper` espía;
  - L-10: dos fallos concurrentes con `dos_sesiones` suman 2;
  - L-8: el evento trae `ip` y `user_agent`;
  - L-4: la purga oportunista solo borra lo vencido hace más de 30 días.
- `tests/auth/test_login_router.py`:
  - casos del blueprint;
  - `Origin` ajeno da 403;
  - contraseña de 129 da 422;
  - atributos de la cookie y `no-store`;
  - IPv6 del mismo /64 comparten bucket.
- `tests/auth/test_pure_refresh.py`.
- `tests/auth/test_refresh_service.py`:
  - rotación;
  - reuso: revoca, emite `SessionsRevoked` y el commit sobrevive al 401;
  - M-2 con `FrozenClock`: a los 5 s, 401 sin revocar; a los 11 s, revoca todo;
  - concurrencia con `dos_sesiones`;
  - `family_started_at` más 30 días da `InvalidRefresh`;
  - el reuso fija `tokens_valid_after`.
- `tests/auth/test_refresh_router.py`: `Origin`; la cookie se borra en el 401; `rate_limit("refresh")`.
- `tests/auth/test_logout_service.py` y `tests/auth/test_logout_router.py` (H-1):
  - access vencido (+16 min) con cookie válida: 204, el refresh queda revocado y `Set-Cookie` lo borra; un refresh posterior da 401;
  - sin cookie: 204;
  - `Origin` ajeno: 403 sin tocar la cookie;
  - `rate_limit("logout")`.
- `tests/cli/test_seed_cli.py`:
  - `SeedSettings`;
  - `--no-force-change` sale con 2 fuera de `dev`;
  - el admin sembrado queda con `must_change_password=true`;
  - L-9: rechaza el literal del ejemplo;
  - L-4: `--as` con una cuenta inactiva o con `system@apex.local` sale con 2.
- Confirmar el rojo.

**B2.5 · Migración**
`0005b_auth_security` por P-MIG, con las cuatro columnas de S2-D9 y el CHECK `failed_login_count_non_negative`. El `downgrade` quita el CHECK y las cuatro columnas.

**B2.6 · Verde de core**
- `core/validators.py`.
- `core/security.py`:
  - `PASSWORD_MAX_LENGTH` y `too_long`;
  - `Principal(must_change_password, tokens_valid_after)`;
  - en `current_user`: comparar `iat` y después `refresh_current`;
  - `PUBLIC_ROUTES` suma `POST /api/v1/auth/logout`.
- `core/crypto/keyring.py`: `refresh_current`.
- `core/ratelimit.py`.
- `core/config.py`:
  - quitar `ADMIN_*` y agregarlas a `NON_API_ENV_VARS`;
  - crear `SeedSettings`;
  - las variables nuevas, todas `gt=0`;
  - validador M-9.
- `main.py`: quitar `refresh_keyring` de `include_module_routers`.
- `.env.example`: quitar `ADMIN_*` y documentar las variables nuevas.
- `.env` local: `AUTH_ALLOWED_ORIGINS=http://localhost:8180,http://localhost:5173`.

**B2.7 · Verde de auth y CLI**
- `models.py`: columnas nuevas; `__audit_exclude__ = {last_login_at, failed_login_count, tokens_valid_after}`.
- `exceptions.py`: `InvalidCredentials` e `InvalidRefresh`.
- `schemas.py`: `UserSummary`, `LoginIn`, `LoginOut`, `RefreshOut` y `UserStatus` con 5 valores.
- `rules.py`: `account_may_authenticate`, `AUTH_FILTER`, `status_filter`, `user_status`, `is_refresh_usable`, `is_reuse(token, now, grace)`, `should_auto_lock` y `AuthPolicy`.
- `tokens.py`: `revoke_all` (fija `tokens_valid_after`), `commit_failure`, `purge_expired_for_user` e `increment_failures` (`UPDATE ... RETURNING`).
- `cookies.py`: `set_refresh_cookie`, `clear_refresh_cookie`, `clear_cookie_header`, `read_refresh_cookie`, `policy_from`, `no_store` y `require_same_origin`.
- `service.py`:
  - eventos `LoginAttempted` (con `ip` y `user_agent`), `SessionsRevoked` y `UserLocked`;
  - `login` (flujo 7.1 del blueprint corregido por H-4 y M-6);
  - `refresh` (gracia y tope absoluto);
  - `logout(session, token)`, por cookie;
  - `seed_admin(force_change=True)`;
  - `active_user_id_by_email`;
  - `load_active_principal` con `AUTH_FILTER`.
- `router.py` (plano):
  - `POST /auth/login`: `rate_limit("login")`, `require_same_origin`, `no_store`;
  - `POST /auth/refresh`: `rate_limit("refresh")`, `require_same_origin`, `no_store`;
  - `POST /auth/logout`: `rate_limit("logout")`, `require_same_origin`, responde 204.
- `cli.py`: `SeedSettings`, `--no-force-change`, L-9 y `resolve_actor`.

**B2.8 · Documentación**
- `CLAUDE.md`: `auth/{rules,tokens,cookies}.py`, `core/validators.py` y la regla "un router plano por módulo".
- `docs/RUNBOOK.md`:
  - capas del límite de intentos;
  - `restart api` limpia los contadores en memoria;
  - gracia del reuso de refresh;
  - el valor medido de `LOGIN_MIN_DURATION_MS`.

**B2.9 · Contrato**
P-API.

**B2.10 · Gate**
1. `slice-gate.sh core/validators tests/core/test_validators.py`.
2. `slice-gate.sh core/ratelimit tests/core/test_ratelimit.py`.
3. `slice-gate.sh core/security tests/core/test_passwords.py tests/core/test_require_role.py tests/core/test_jwt.py`.
4. `slice-gate.sh crypto tests/crypto/test_refresh_current.py tests/crypto/test_provider_startup.py`.
5. `slice-gate.sh core/config tests/core/test_config.py tests/core/test_env_example.py tests/core/test_config_secrets.py`.
6. `slice-gate.sh core/events tests/core/test_events.py tests/core/test_events_db.py`.
7. `slice-gate.sh cli tests/cli/test_seed_cli.py`.
8. `slice-gate.sh architecture tests/core/test_migrations.py tests/migrations/test_0005b_auth_security.py`.
9. Al final, para sellar: `slice-gate.sh auth` con los 11 archivos de auth de B2.4, más `tests/auth/test_pure_users.py` y `tests/auth/test_principal_loader.py` como regresión.

**B2.11 · Docker**
1. Pasos 6 y 7 de P-MIG.
2. `$DC build api`, porque cambió `cli.py`.
3. Con `.env.seed` local: `$DC run --rm tools seed`. Una segunda corrida debe decir "omitido". Si la base está vacía, el admin nuevo queda con `must_change_password=true` (comprobar con psql).
4. Smoke por Nginx:
   - `curl -X POST http://localhost:8180/api/v1/auth/login` con `Origin`: da 200, `Set-Cookie` con `apex_refresh; HttpOnly; SameSite=Strict; Path=/api/v1/auth` y `Cache-Control: no-store`;
   - el sexto intento desde la misma IP da 429;
   - un `Origin` ajeno da 403;
   - psql: `token_hash` de 64 hex y `family_started_at` lleno.

**B2.12 · Checkpoint**
`"S2-B2 sesión: login, refresh y logout por cookie"`.

### S2-B3 · Mi cuenta y usuarios

- **Historias:** US-045, US-046 y US-047.
- **Depende de:** B1 y B2.
- **Migración:** ninguna.
- **Cierra:** M-8 (exigencia de `must_change_password`), L-5 (en contraseñas), H-3 (`change_password`), L-2 y S2-D53. Requiere la condición 4 ya cumplida.

**B3.1 · Precondición y stubs**
- Verificar `FRONT_BASE_URL` del `.env` local, que debe ser `http://localhost:8180`.
- Agregar `make_one_time_token` a las fábricas.
- Stubs: `require_role(allow_pending_password)`, `issue_one_time_token`, `me`, `change_password`, `list_users` y `create_user`.

**B3.2 · Rojo**
- Los 9 archivos del plan, en `tests/auth/`: `test_pure_password_policy.py`, `test_change_password.py`, `test_me_router.py`, `test_pure_user_status.py`, `test_list_users.py`, `test_users_list_router.py`, `test_pure_links.py`, `test_create_user.py`, `test_create_user_router.py`. Casos que agrega este plan:
  - `change_password` responde 200 con un access nuevo; un access anterior da 401 y el nuevo 200; la sesión de la cookie sigue viva;
  - `CreateUserIn` con `role=member` da 422 (L-2).
- `tests/core/test_require_role.py`: recorre todas las rutas autenticadas con un principal con `must_change_password=True` y espera 403 `password_change_required`, salvo `GET /auth/me` y `POST /auth/me/password`.
- `tests/core/test_logging_redact.py`: `/restablecer/<token>`, `apex_refresh=` y las claves `activation_url`, `url` y `set-cookie`.
- `tests/architecture/test_list_routes_use_page_params.py`, endurecida con `effective_routes`.
- `tests/architecture/test_service_import_graph.py`, nueva.
- Confirmar el rojo.

**B3.3 · Verde**
- `core/security.py`: `require_role(*roles, allow_pending_password=False)`.
- `core/logging.py`: los patrones y claves nuevos.
- `auth/rules.py`: `validate_password_policy(field=...)`, `activation_url`, `ACTIVATE_TTL` y `RESET_TTL`.
- `auth/tokens.py`: `issue_one_time_token`.
- `auth/exceptions.py`: `EmailTaken` e `InvalidCurrentPassword`.
- `auth/schemas.py`: `MeOut`, `ChangePasswordIn`, `AccessTokenOut`, `UserRow` (con `active_sessions`), `CreateUserIn` (rol admin o coach), `CreateUserOut` y `UserOut` con `must_change_password`.
- `auth/service.py`:
  - evento `PasswordChanged(user_id, by, via, via_link_issued_by: UUID | None)`;
  - `me`, `change_password`, `list_users` y `create_user`.
- `auth/router.py`:
  - `GET /auth/me` y `POST /auth/me/password` (200 `AccessTokenOut`), con `allow_pending_password=True` y `no_store`;
  - `GET /users` y `POST /users`, solo admin, con `no_store`.

**B3.4 · Documentación**
`docs/ddd/05_service_design.md`:
- `Principal.must_change_password` y `tokens_valid_after`;
- `me` con `gym_name`;
- rutas tipadas de settings;
- `me/password` responde 200.

**B3.5 · Contrato**
P-API.

**B3.6 · Gate**
1. `slice-gate.sh core/security tests/core/test_require_role.py`.
2. `slice-gate.sh core/logging tests/core/test_logging_redact.py`.
3. Al final, para sellar: `slice-gate.sh auth` con los 9 archivos de B3.

**B3.7 · Docker**
Comprobar la recarga en los logs. Luego, `GET /api/v1/auth/me` vía 8180 con el token del admin: trae `gym_name` y `must_change_password`.

**B3.8 · Checkpoint**
`"S2-B3 mi cuenta y usuarios"`.

### S2-B4 · Activación, recuperación y reenvío

- **Historias:** US-048 y US-052.
- **Depende de:** B3.
- **Migración:** ninguna.
- **Cierra:** H-2, H-3 (`reset`), L-12 (`reset`) y L-13.

**B4.1 · Stubs**
- `is_one_time_token_usable` (S2-D40), `link_purpose_for`, `get_alive_or_404`;
- `reset`, `forgot` y `resend_link`;
- `cli issue-reset-link`.

**B4.2 · Rojo**
- `tests/auth/test_pure_one_time_token.py`: límite exacto de `expires_at`; un pendiente es usable solo con propósito `activate`.
- `tests/auth/test_reset_forgot.py`:
  - casos de reset del blueprint;
  - reset fija `tokens_valid_after` y revoca las sesiones;
  - `PasswordChanged` lleva `via_link_issued_by`;
  - H-2: `forgot` con correo existente no crea filas, no cierra tokens abiertos y no escribe auditoría; su duración tiene el mismo piso que con un correo inexistente (sleeper espía); `forgot-account` da 429 a los 5 intentos por cuenta.
- `tests/auth/test_reset_forgot_router.py`: cuerpo vacío en todos los casos; `rate_limit("reset")`; `ForgotIn` de más de 254 da 422.
- `tests/auth/test_resend_link.py`: casos del blueprint, más L-13 (sobre sí mismo y sobre un admin activo con contraseña: 409 `user_not_eligible`).
- `tests/auth/test_resend_link_router.py`.
- `tests/architecture/test_auth_routes.py`:
  - rutas públicas exactas: login, refresh, logout, forgot, reset;
  - las cinco con `__apex_rate_limit__`;
  - `/users*` solo para `{"admin"}`;
  - `me` y `me/password` con los tres roles;
  - ninguna ruta `/activation-link`.
- `tests/cli/test_issue_reset_link_cli.py`: imprime la URL una sola vez; exige `--as` de un admin activo; deja `insert` auditado.
- Confirmar el rojo.

**B4.3 · Verde**
- `rules.py`, `tokens.py`, `exceptions.py` (`InvalidToken`, `UserNotEligible`, `UserNotFound`) y `schemas.py` (`ResetIn`, `ForgotIn`, `IssuedLinkOut`).
- `service.py`:
  - `reset` (orden del blueprint más `tokens_valid_after`);
  - `forgot` (S2-D36);
  - `resend_link` (con L-13).
- `router.py`:
  - `POST /auth/forgot`: `rate_limit("forgot")`, 204;
  - `POST /auth/reset`: `rate_limit("reset")`, 204;
  - `POST /users/{id}/resend-link`: admin, `no_store`.
- `cli.py`: comando `issue-reset-link`.

**B4.4 · Documentación**
`docs/RUNBOOK.md`: cómo recuperar a un admin con `tools issue-reset-link`; `forgot` no envía nada hasta US-131.

**B4.5 · Contrato**
P-API.

**B4.6 · Gate**
1. `slice-gate.sh cli tests/cli/test_issue_reset_link_cli.py`.
2. Al final, para sellar: `slice-gate.sh auth` con los 5 archivos de `tests/auth/` de B4.2 más `tests/architecture/test_auth_routes.py`.

**B4.7 · Docker**
1. `$DC build api`, porque cambió `cli.py`.
2. `$DC run --rm tools issue-reset-link <correo de prueba> --as <admin>`.
3. Abrir la URL en `http://localhost:8180/restablecer/...`.
4. psql: `one_time_tokens.token_hash` es hash, no el token.

**B4.8 · Checkpoint**
`"S2-B4 activación, recuperación y reenvío"`.

### S2-B5 · Ciclo de vida del usuario

- **Historias:** US-049, US-050 y US-051.
- **Depende de:** B3 y B4.
- **Migración:** ninguna.
- **Cierra:** H-3 (`revoke_sessions`) y el punto 5 de H-4 (`unlock` limpia los contadores).

**B5.1 · Stubs**
- `would_remove_last_admin`, `lock_precondition`, `lock_active_admins`;
- `get_user`, `update_user`, `delete_user`, `lock`, `unlock`, `revoke_sessions`;
- `cli unlock-user`.

**B5.2 · Rojo**
- Los 8 archivos del plan, en `tests/auth/`: `test_pure_last_admin.py`, `test_update_delete_user.py`, `test_user_detail_router.py`, `test_pure_lock.py`, `test_lock_unlock.py`, `test_lock_router.py`, `test_revoke_sessions.py`, `test_revoke_sessions_router.py`. Casos que agrega este plan:
  - un access emitido antes de `revoke_sessions` da 401 en `GET /auth/me`; uno emitido después, 200;
  - `unlock` limpia `failed_login_count` y los contadores en memoria de la cuenta;
  - dos `delete_user` concurrentes con `dos_sesiones`.
- `tests/cli/test_unlock_cli.py`.
- Confirmar el rojo.

**B5.3 · Verde**
- `rules.py`, `tokens.py` y `exceptions.py` (`LastAdmin`, `CannotLockSelf`, `AlreadyLocked`, `NotLocked`).
- `schemas.py`: `UpdateUserIn` y `RevokeSessionsOut`.
- `service.py`: todos los casos de uso; `unlock` llama a `ratelimit.forget`.
- `router.py`: `GET`, `PATCH` y `DELETE /users/{id}`, `POST /lock`, `/unlock` y `/revoke-sessions`, todas solo admin con `no_store`.
- `cli.py`: `unlock-user`.

**B5.4 · Contrato**
P-API.

**B5.5 · Gate**
1. `slice-gate.sh cli tests/cli/test_unlock_cli.py`.
2. Al final, para sellar: `slice-gate.sh auth` con los 8 archivos de B5.2.

**B5.6 · Docker**
`$DC build api`, porque cambió `cli.py`.

**B5.7 · Verificación con datos reales**
psql: `SELECT id FROM auth.users WHERE deleted_at IS NULL AND role='admin'`. Por API, bloquear a un coach de prueba y comprobar `locked_at` y `tokens_valid_after`.

**B5.8 · Checkpoint**
`"S2-B5 ciclo de vida del usuario"`.

### S2-B6 · Auditoría de eventos de seguridad

- **Historia:** US-107.
- **Depende de:** B2, B3, B4 y B5.
- **Migración:** ninguna.
- **Cierra:** condición 2, L-8 (fila de auditoría), L-13 (auditoría) y S2-D31.

**B6.1 · Stubs**
`api/src/app/modules/audit/{__init__,router,service}.py`. El router es un `APIRouter()` vacío.

**B6.2 · Rojo**
- `tests/audit/__init__.py`.
- `tests/audit/test_security_events.py`:
  - los casos del blueprint;
  - `after` de la fila `login` trae `ip` y `user_agent` y nunca el correo;
  - `PasswordChanged` deja su fila con `via_link_issued_by`;
  - el reuso y el bloqueo automático quedan con `SYSTEM_USER_ID`;
  - `verify_chain` queda íntegra al final.
- `tests/auth/test_router_login_audit.py`.
- `tests/audit/test_reveal_entry.py`: con `uuid4()`, sin `skip`.
- `tests/architecture/test_audited_tables.py`: `find_spec`; `REQUIRED_AUDITED_TABLES_V01` y `PENDING_AUDITED`.
- `tests/cli/test_seed_cli.py`: `_seed`, `unlock-user` e `issue-reset-link` llaman a `load_module_services()` (espía).
- Confirmar el rojo.

**B6.3 · Verde**
- `audit/service.py`: `on_login_attempted`, `on_user_locked`, `on_sessions_revoked` y `on_password_changed`, registrados al importarse.
- `MODULES = ("auth","settings","audit")`.
- `cli.py`: `load_module_services()` con import perezoso en los comandos que escriben tablas auditadas.

**B6.4 · Documentación**
`CLAUDE.md`: `modules/audit` con `router.py` vacío y sin `models.py`.

**B6.5 · Contrato**
P-API. Debe confirmar que no cambia: `git diff --exit-code docs/openapi.json` en verde.

**B6.6 · Gate**
1. `slice-gate.sh cli tests/cli/test_seed_cli.py`.
2. Al final, para sellar: `slice-gate.sh audit tests/audit/test_security_events.py tests/auth/test_router_login_audit.py tests/audit/test_reveal_entry.py tests/architecture/test_audited_tables.py`.

**B6.7 · Docker**
1. `$DC build api`.
2. Un login fallido vía 8180 con el correo del admin y luego `SELECT action, after FROM audit.audit_log ORDER BY seq DESC LIMIT 3`: aparece la fila `login` con `result=failed`, `ip` y `user_agent`.

**B6.8 · Checkpoint**
`"S2-B6 auditoría de eventos de seguridad"`.

### S2-B7 · Registrar socio y pruebas de cifrado en reposo

- **Historias:** US-069 y US-031.
- **Depende de:** B6 (y B3 por `core/logging`).
- **Migración:** `0006_members` (`down_revision = "0005b_auth_security"`).
- **Cierra:** condiciones 1 y 7 (fábricas y limpieza); M-4, M-5, L-1 (alta) y L-3; S2-D16 y S2-D20.

**B7.1 · Fábrica y limpieza**
`tests/factories/members.py`, `FACTORIES["members.members"]` y `members.members` en `LIMPIEZA_DE_SESION`.

**B7.2 · Stubs**
- `api/src/app/modules/members/{__init__,models,schemas,exceptions,service,router}.py`;
- `find_banned_imports` en `tests/architecture/_imports.py`.

**B7.3 · Rojo**
- `tests/members/test_member_rules.py`, `tests/members/test_service_create.py` y `tests/members/test_router_create.py`. Casos que agrega este plan:
  - `data_consent=true` deja `data_consent_at = now` del reloj del servidor; un `data_consent_at` enviado por el cliente da 422 (`extra="forbid"`);
  - no existe `notes`;
  - `"..."` o `"+57"` dan 422 con `field`;
  - el alta número 61 en un minuto por usuario da 429.
- En `tests/architecture/`:
  - `test_members_encrypted_at_rest.py`;
  - `test_no_plaintext_at_rest.py`;
  - `test_import_analyzer.py`;
  - `test_banned_imports.py` (ampliada);
  - `test_audited_tables.py` (`members.members` pasa a la lista obligatoria);
  - `test_no_sensitive_in_logs.py`, implementada: login real más `POST /members` real; el caso `reveal` queda aparte con `skip(reason="US-074, S3-B10")`.
- `tests/core/test_logging_redact.py`, ampliada con un socio real.
- `tests/migrations/test_0006_members.py`.
- Confirmar el rojo.

**B7.4 · Migración**
`0006_members` por P-MIG: el esquema del blueprint, sin `notes` y con `document_type`. `data_consent_at` y `data_consent_version` quedan nulos.

**B7.5 · Verde**
- `models`, `schemas`, `exceptions`, `service` y `router` según el blueprint B7, con las correcciones M-4, M-5 y L-3.
- `POST /members` usa `ratelimit.enforce("members-write", str(principal.user_id), limit=60, window_s=60)`.
- `MODULES` suma `members`.

**B7.6 · Contrato**
P-API.

**B7.7 · Gate**
1. `slice-gate.sh core/logging tests/core/test_logging_redact.py`.
2. `slice-gate.sh architecture tests/core/test_migrations.py tests/migrations/test_0006_members.py`.
3. Al final, para sellar: `slice-gate.sh members tests/members/test_member_rules.py tests/members/test_service_create.py tests/members/test_router_create.py tests/architecture/test_members_encrypted_at_rest.py tests/architecture/test_no_plaintext_at_rest.py tests/architecture/test_import_analyzer.py tests/architecture/test_banned_imports.py tests/architecture/test_no_sensitive_in_logs.py`.

**B7.8 · Docker y evidencia**
1. Pasos 6 y 7 de P-MIG.
2. Registrar por API (vía 8180) el socio de CC `1.020.304.417`.
3. Evidencia:
   - `SELECT document, document_idx FROM members.members`: un blob `apx1.` y un HMAC;
   - `crypto_ops` con las filas `encrypt` e `index` atribuidas al actor.

**B7.9 · Checkpoint**
`"S2-B7 registrar socio y cifrado en reposo"`.

### S2-B8 · Buscar y listar socios

- **Historia:** US-070.
- **Depende de:** B7.
- **Migración:** ninguna.
- **Cierra:** C1 (marcador `perf`), L-1 (búsqueda), S2-D27 y la parte de servidor de S2-D41.

**B8.1 · Marcador y stubs**
Registrar `perf` en `api/pyproject.toml`. Stubs: `classify_query`, `list`, `search_ids` y `names_for`.

**B8.2 · Rojo**
- `tests/members/test_classify_query.py`.
- `tests/members/test_service_list.py`: cero filas `decrypt` en `crypto_ops`.
- `tests/members/test_router_list.py`: la búsqueda número 61 con `q` en un minuto da 429; `q` no aparece en los logs capturados.
- `tests/members/test_list_perf.py` (`@pytest.mark.perf`):
  - 1.000 socios;
  - búsqueda por documento en menos de 500 ms;
  - `EXPLAIN` que usa `uq_members_document_idx_alive`;
  - mide la latencia del login fallido bajo el candado de la cadena (L-11).
- `tests/architecture/test_list_rows_without_sensitive_fields.py`.
- Confirmar el rojo.

**B8.3 · Verde**
`schemas` (`MemberRowOut`, `MemberListQuery`, `MemberName`), `service` y `router` (`GET /members` con `Page[MemberRowOut]`), según el blueprint B8. Más el límite por usuario cuando hay `q`.

**B8.4 · Contrato**
P-API.

**B8.5 · Gate**
Para sellar: `slice-gate.sh members tests/members/test_classify_query.py tests/members/test_service_list.py tests/members/test_router_list.py tests/members/test_list_perf.py tests/architecture/test_list_rows_without_sensitive_fields.py`.

**B8.6 · Docker**
`pyproject.toml` solo cambió en los marcadores de pytest, así que no se reconstruye nada. Buscar por documento, por teléfono y por nombre vía 8180 con el socio de B7.

**B8.7 · Checkpoint**
`"S2-B8 buscar y listar socios"`.

### S2-B9 · Crear y listar planes

- **Historias:** US-078 y US-079.
- **Depende de:** B8 (orden de la cadena de migraciones).
- **Migración:** `0007_plans` (`down_revision = "0006_members"`).
- **Cierra:** S2-D26 y S2-D32.

**B9.1 · Fábrica y limpieza**
`tests/factories/plans.py`, su entrada en `FACTORIES` (la tabla no tiene columnas cifradas, así que es opcional) y `plans.plans` en la limpieza.

**B9.2 · Stubs**
`api/src/app/modules/plans/{__init__,models,schemas,exceptions,service,router}.py`.

**B9.3 · Rojo**
- En `tests/plans/`: `test_validate_plan.py`, `test_service_create.py`, `test_router_create.py`, `test_scope_rules.py`, `test_service_list.py` y `test_router_list.py`.
- `tests/migrations/test_0007_plans.py`.
- `tests/architecture/test_audited_tables.py`: `plans.plans` pasa a la lista obligatoria.
- Confirmar el rojo.

**B9.4 · Migración**
`0007_plans` por P-MIG, con el índice `lower(btrim(name))`.

**B9.5 · Verde**
Según el blueprint B9. `MODULES` queda en su forma final.

**B9.6 · Contrato**
P-API. Con este slice el contrato queda definitivo para el front.

**B9.7 · Gate**
1. `slice-gate.sh architecture tests/core/test_migrations.py tests/migrations/test_0007_plans.py tests/architecture/test_audited_tables.py`.
2. Al final, para sellar: `slice-gate.sh plans` con los 6 archivos de `tests/plans/` de B9.3.

**B9.8 · Docker y checkpoint**
1. Pasos 6 y 7 de P-MIG.
2. Crear "Mensual" ($ 120.000, 30 días). Crear "mensual" debe dar 409. El coach con `active=false` debe recibir 403.
3. Checkpoint `"S2-B9 crear y listar planes"`.

## 6. Front (worktree, en paralelo)

En todos los slices de front:
- el gate acota lint y tsc a los archivos del slice (A-01);
- `$DC build web && $DC up -d web` antes de cualquier E2E del proyecto `stack` o de una demo en 8180.

### S2-F1 · Layouts

- **Historias:** US-061 y US-062.
- **Depende de:** W0-1.

**F1.1 · Stubs y utilidades**
`web/src/test/server.ts` y los stubs de `layouts/nav.ts`, `PanelLayout`, `PortalLayout`, `GymLayout`, `TvLayout`, `shared/ui/TopBar`, `shared/ui/SideNav` y `shared/hooks/useForcedTheme`.

**F1.2 · Rojo**
- `nav.test.ts`, `PanelLayout.test.tsx`, `TopBar.test.tsx`, `SideNav.test.tsx`, `PortalLayout.test.tsx`, `GymLayout.test.tsx` y `TvLayout.test.tsx`;
- `layouts.no-fetch.test.ts` y `layouts.a11y.test.tsx`;
- `tests/e2e/panel-layout.spec.ts` y `tests/e2e/layouts.spec.ts` (proyecto `preview`).

**F1.3 · Verde**
Según el blueprint F1: tokens de `tokens.css`, `// DESIGN-GAP:` por el cajón y el modo plegado, y `web/src/dev/LayoutsPreview.tsx`.

**F1.4 · Inventario del kit**
`shared/ui/index.ts` y su prueba incluyen `TopBar` y `SideNav`.

**F1.5 · Gate**
1. `slice-gate.sh web/shared src/shared/ui/TopBar.test.tsx src/shared/ui/SideNav.test.tsx`.
2. `cd web && npx playwright test --project=preview tests/e2e/panel-layout.spec.ts tests/e2e/layouts.spec.ts`.
3. Al final, para sellar: `slice-gate.sh web/layouts` con sus pruebas.

**F1.6 · Checkpoint**
`"S2-F1 layouts"`.

### S2-F2 · Rutas y guardas

- **Historias:** US-067 y US-053.
- **Depende de:** F1.
- **Cierra:** la condición 6 (`homeFor` sin literales de rol), L-5 y S2-D23.

**F2.1 · Stubs**
`config/features.ts`, `config/routeTable.ts`, `config/routes.reference.ts`, `routes.tsx`, `core/auth/routeAccess.ts`, la parte de F2 de `session.ts`, `RequireAuth`, `RequireRole`, `NoPermissionPage`, `pages/NotFound.tsx` y `features/dashboard/pages/InicioPage.tsx`. Además, `web/src/test/session.ts`.

**F2.2 · Permisos**
Acción `portal.view` (solo member) en `core/auth/permissions.ts`, con su prueba en la matriz.

**F2.3 · Rojo**
- `src/routes.test.ts`, `src/config/features.test.ts`;
- `src/core/auth/routeAccess.test.ts`: `safeNext` rechaza `//evil.com`, `/\evil.com`, `/\t/evil.com`, `https://x` y rutas de otro rol;
- `RequireAuth.test.tsx` y `RequireRole.test.tsx`;
- `tests/e2e/role-guards.spec.ts` (proyecto `stack`).

**F2.4 · Verde**
- Según el blueprint F2.
- `App.tsx` y `main.tsx` pasan a `QueryClientProvider`, `SessionRoleProvider` y `RouterProvider`.
- Se reescriben `src/App.test.tsx` y `tests/e2e/smoke.spec.ts`.

**F2.5 · Documentación**
`docs/design/ROUTES.md` y `docs/BRECHAS.md`: `/cambiar-clave` e `InicioPage` mínima.

**F2.6 · Gate**
1. `slice-gate.sh web/core` con las pruebas de `core/auth`.
2. Al final, para sellar: `slice-gate.sh web/app src/routes.test.ts src/config/features.test.ts tests/unit/no-role-literals.test.ts`.

**F2.7 · Checkpoint**
`"S2-F2 rutas y guardas"`.

### S2-F3 · Login, refresh y logout

- **Historias:** US-042, US-043 y US-044 (front).
- **Depende de:** B2 (checkpoint) y F2.
- **Cierra:** H-1 (front), L-6, L-12 (front) y S2-D22 (`@hookform/resolvers`).

**F3.1 · Dependencia**
`npm i @hookform/resolvers` (MIT), `npm run licenses` y `NOTICE`. Rebase sobre la rama del sprint para traer `types.ts` de B2.

**F3.2 · Stubs**
`features/auth/{schemas,api}.ts`, `LoginPage`, `LoginCard`, `refreshAccessToken`, `logout`, `installSessionBridge`, `core/api/queryClient.ts`, `SessionRole.tsx` y `PanelShell.tsx`.

**F3.3 · Rojo**
- `LoginPage.test.tsx`.
- `src/core/auth/session.test.ts`, con los casos del blueprint más:
  - L-6: un `token` que llega después de un `logout` se ignora;
  - L-12: `GET /auth/me` con 429 mantiene al usuario;
  - H-1: si el logout falla por red o 5xx, se muestra el aviso "No se pudo cerrar la sesión en el servidor".
- `src/shared/ui/TopBar.logout.test.tsx`.
- `tests/e2e/login.spec.ts`, `tests/e2e/refresh-two-tabs.spec.ts` y `tests/e2e/logout-expired.spec.ts` (proyecto `stack`; H-1: tras un logout con el access vencido, recargar `/` lleva a `/login`).

**F3.4 · Verde**
- Según el blueprint F3.
- Login, refresh y logout usan `skipAuthRetry`.
- Login con el nombre "APEX" y `// DESIGN-GAP:`.

**F3.5 · Gate**
1. `slice-gate.sh web/core` con las pruebas de `core/auth` y `core/api`.
2. `slice-gate.sh web/shared src/shared/ui/TopBar.logout.test.tsx`.
3. Al final, para sellar: `slice-gate.sh web/auth src/features/auth/pages/LoginPage.test.tsx`.

**F3.6 · Docker**
`$DC build web && $DC up -d web`. Si B3 ya existe, correr `npm run e2e:stack -- tests/e2e/login.spec.ts`.

**F3.7 · Checkpoint**
`"S2-F3 login, refresh y logout"`.

### S2-F4a · Mi cuenta, activación, recuperación, alta y lista de usuarios

- **Historias:** US-045, US-046, US-047 y US-048 (front).
- **Depende de:** B3, B4 y F3.
- **Cierra:** L-7 (alta), la parte de front de H-3 y S2-D41 (usuarios).

**F4a.1 · Contrato y estados**
Rebase para traer los tipos de B4. `StatusTag` con `account`, más `ACCOUNT_LABELS` y `ACCOUNT_TONES` (S2-D24).

**F4a.2 · Stubs**
- En `features/auth`: `useMe`, `useChangePassword`, `useResetPassword`, `useForgotPassword`, `ChangePasswordPanel`, `ResetPage`, `ForgotPage` y `ChangePasswordPage`.
- En `features/system`: `useUsers`, `useCreateUser`, `UsersPage` y `NewUserPanel`.

**F4a.3 · Rojo**
- `ChangePasswordPanel.test.tsx`: el 200 deja el token nuevo con `setSession` y lo publica por el canal.
- `ResetPage.test.tsx` (`replaceState`) y `ForgotPage.test.tsx`.
- `UsersPage.test.tsx`: `q` en estado local y nunca en la URL.
- `NewUserPanel.test.tsx`: `gcTime: 0`; al cerrar, `reset()` y el enlace desaparece del estado y de la caché.
- `src/shared/ui/StatusTag.test.tsx`, ampliada.
- `tests/e2e/users-activation.spec.ts`.

**F4a.4 · Verde**
Según el blueprint F4a. En `createUserSchema` el rol es admin o coach.

**F4a.5 · Gate**
1. `slice-gate.sh web/shared src/shared/ui/StatusTag.test.tsx`.
2. `slice-gate.sh web/auth` con sus pruebas.
3. Al final, para sellar: `slice-gate.sh web/system src/features/system/pages/UsersPage.test.tsx src/features/system/components/NewUserPanel.test.tsx`.

**F4a.6 · Docker**
`build web`. Si B4 ya existe, correr el E2E `users-activation`.

**F4a.7 · Checkpoint**
`"S2-F4a mi cuenta, activación y alta de usuarios"`.

### S2-F4b · Gestión de usuarios

- **Historias:** US-049, US-050, US-051 y US-052 (front).
- **Depende de:** B5 y F4a.
- **Cierra:** L-7 (reenvío) y L-13 (front).

**F4b.1 · Stubs**
`useUser`, `useUpdateUser`, `useDeleteUser`, `useLockUser`, `useUnlockUser`, `useRevokeSessions`, `useResendLink`, `EditUserPanel` y `LinkModal`.

**F4b.2 · Rojo**
- `UsersPage.delete.test.tsx`, `UsersPage.lock.test.tsx` y `UsersPage.sessions.test.tsx`.
- `EditUserPanel.test.tsx`.
- `LinkModal.test.tsx`:
  - `gcTime: 0` y descarte al cerrar;
  - "Reenviar enlace" oculto en la propia fila y en las de admins activos con contraseña;
  - mensaje del 409 `user_not_eligible`.

**F4b.3 · Verde**
Según el blueprint F4b.

**F4b.4 · Gate**
Para sellar: `slice-gate.sh web/system` con los 5 archivos de F4b.2.

**F4b.5 · Docker**
`build web`.

**F4b.6 · Checkpoint**
`"S2-F4b gestión de usuarios"`.

### S2-F5 · Configuración

- **Historias:** US-055, US-057 y US-058 (front).
- **Depende de:** B1 y F2. El E2E `settings-gym` además necesita B3.

**F5.1 · Dependencia**
`npm i -D @axe-core/playwright`, su línea en `scripts/ci/licenses-exceptions.txt` y `npm run licenses`.

**F5.2 · Stubs**
`useSettingsSection`, `gymSettingsSchema`, `privacySettingsSchema`, `membershipsSettingsSchema`, `applyApiFieldError`, `ConfigPage` y los tres formularios.

**F5.3 · Rojo**
`GymSettingsForm.test.tsx`, `PrivacySettingsForm.test.tsx` (el texto se muestra como texto plano), `MembershipsSettingsForm.test.tsx`, `ConfigPage.test.tsx` y `tests/e2e/settings-gym.spec.ts`.

**F5.4 · Verde**
Según el blueprint F5.

**F5.5 · Gate**
Para sellar: `slice-gate.sh web/system` con los 4 archivos de F5.3.

**F5.6 · Docker y checkpoint**
`build web`; correr el E2E si B3 ya existe. Checkpoint `"S2-F5 configuración"`.

### S2-F6 · Socios: alta y lista

- **Historias:** US-069 y US-070 (front).
- **Depende de:** B7, B8 y F2.
- **Cierra:** M-4 y M-5 (front), M-8 y S2-D34.

**F6.1 · Contrato y stubs**
Rebase para traer los tipos de B8. Stubs: `features/members/{schemas,api}.ts`, `MemberFormPage`, `MemberFormFields` y `MembersListPage`.

**F6.2 · Rojo**
- `MemberFormPage.test.tsx`:
  - la casilla envía `data_consent: true`;
  - no hay campo de notas;
  - errores de campo, incluido el 422 de L-3;
  - enlace del 409 a `/socios/{id}`;
  - nada del formulario en `localStorage`.
- `MembersListPage.test.tsx`: `q` fuera de la URL; `status=deleted` para el coach; reinicio de `offset`; los tres estados.

**F6.3 · Verde**
Según el blueprint F6, con las correcciones de S2-D16 y S2-D41. `// DESIGN-GAP:` por notas, foto, firma, portal y cargas.

**F6.4 · Gate**
Para sellar: `slice-gate.sh web/members src/features/members/pages/MemberFormPage.test.tsx src/features/members/pages/MembersListPage.test.tsx`.

**F6.5 · Docker**
`build web`.

**F6.6 · Checkpoint**
`"S2-F6 socios: alta y lista"`.

### S2-F7 · Planes: alta y lista

- **Historias:** US-078 y US-079 (front).
- **Depende de:** B9 y F2.

**F7.1 · Contrato y stubs**
Rebase para traer los tipos de B9. Stubs: `features/plans/{schemas,api}.ts`, `PlanForm` y `PlansPage`.

**F7.2 · Rojo**
`PlansPage.test.tsx` y `PlanForm.test.tsx`.

**F7.3 · Verde**
Según el blueprint F7.

**F7.4 · Gate**
Para sellar: `slice-gate.sh web/plans src/features/plans/pages/PlansPage.test.tsx src/features/plans/components/PlanForm.test.tsx`.

**F7.5 · Docker**
`build web`.

**F7.6 · Checkpoint**
`"S2-F7 planes: alta y lista"`.

### S2-F8 · Temas, accesibilidad y capturas

- **Historia:** US-068.
- **Depende de:** F1 a F7.

**F8.1 · Stubs**
`core/theme/theme.ts`, `ThemeToggle.tsx`, `dev/Catalog.tsx`, `web/catalog.html` y el script `build:catalog`.

**F8.2 · Rojo**
`src/core/theme/theme.test.ts` (un `localStorage` que lanza no rompe nada), `tests/kit-inventory.test.ts` (los 16 componentes, cada uno con su prueba) y `tests/e2e/kit.spec.ts` (proyecto `preview`; `AxeBuilder` con `wcag2a`, `wcag2aa` y `wcag21aa`; 4 anchos por 2 temas; sin desbordes).

**F8.3 · Verde**
Según el blueprint F8. `ThemeToggle` se conecta a `PanelShell`. Se agrega `tests/lint/stylelint.test.ts` si falta.

**F8.4 · Gate**
1. `cd web && npx playwright test --project=preview tests/e2e/kit.spec.ts`.
2. Al final, para sellar: `slice-gate.sh web/core src/core/theme/theme.test.ts tests/kit-inventory.test.ts`.

**F8.5 · Docker**
`build web`.

**F8.6 · Checkpoint**
`"S2-F8 temas, accesibilidad y capturas"`.

## 7. Validación del sprint

**V1 · Fusión**
Fusionar la rama del worktree del front en la rama del sprint, como el merge `6511f47` del Sprint 1. Resolver `types.ts` a favor de la versión que exporta el backend. Volver a correr `npm run gen:api` y `types.contract.test.ts`.

**V2 · Stack desde cero de código**
1. `$DC build api web && $DC up -d`.
2. `$DC run --rm tools init-keys`.
3. Esperar el api `healthy`.
4. `$DC exec api alembic current` debe dar `0007_plans (head)`.
5. Ciclo `downgrade -1` y `upgrade head` en `apex-db-1`; `uv run alembic heads` debe dar uno solo.

**V3 · Datos reales antes de navegar**
- `psql -h 127.0.0.1 -p 5442 -U apex -c "SELECT id, email, role, must_change_password FROM auth.users WHERE deleted_at IS NULL"`.
- `SELECT key, version FROM settings.settings_sections`.
- `SELECT count(*) FROM members.members`.
- `SELECT name, is_active FROM plans.plans`.
- Con esos datos se fijan `E2E_ADMIN_EMAIL` y `E2E_ADMIN_PASSWORD` (la contraseña sale del `.env.seed` local). Si el admin tiene `must_change_password=true`, la spec cambia primero la contraseña.

**V4 · E2E contra el stack**
- `cd web && E2E_BASE_URL=http://localhost:8180 npm run e2e:stack`: `login`, `users-activation`, `role-guards`, `settings-gym`, `refresh-two-tabs` y `logout-expired`.
- `npx playwright test --project=preview`: `smoke`, `csp`, `panel-layout`, `layouts` y `kit`, con las capturas a 320, 768, 1024 y 1440 px en claro y oscuro.
- Las specs del proyecto `stack` se corren dos veces seguidas. Deben ser idempotentes: correos únicos por corrida.

**V5 · Rendimiento**
`cd api && uv run pytest -m perf tests/members/test_list_perf.py -q`: 1.000 socios, búsqueda por documento en menos de 500 ms, `EXPLAIN` con `uq_members_document_idx_alive` y la latencia del login fallido registrada.

**V6 · Smoke con evidencia SQL**
Se guarda en el cuaderno:
- `SELECT document, document_idx FROM members.members LIMIT 1`: un blob `apx1.` y un HMAC;
- `SELECT action, table_name, after->>'password_hash' FROM audit.audit_log WHERE table_name='auth.users' ORDER BY seq DESC LIMIT 10`: filas `login`, `insert` y `update`, con `***`;
- `SELECT token_hash FROM auth.one_time_tokens LIMIT 1`: es un hash;
- `SELECT verb, count(*) FROM crypto.crypto_ops GROUP BY verb`: cero `decrypt` por las listas;
- `verify_chain` en verde.

**V7 · Demo**
Los 8 puntos de `SPRINT-02.md` con su texto corregido:
- el sexto intento da 429;
- el reuso fuera de la gracia revoca todo;
- `expiring_days = 7`;
- duplicado de socio: 409 con `existing_id`;
- plan duplicado: 409;
- el coach solo ve planes activos.

**V8 · Repetición**
- `tools seed` dos veces: la segunda dice "omitido".
- `init-keys` dos veces.
- `export-openapi` dos veces: idénticas.
- `compose-smoke.sh` en CI: job `images` en verde.

**V9 · Gates completos**
1. `bash scripts/workflow/run-gates.sh`: cobertura global de `app` en 80 % o más (`cli.py` y `worker/` siguen en `omit` según `api/pyproject.toml`, como documenta `scripts/workflow/README.md`); front con lint, tsc, test con cobertura y build.
2. `cd api && uv run pytest tests/architecture -q`.
3. `pre-commit run --all-files`.
4. `bash scripts/workflow/tests/run.sh`.
5. `pip-licenses --allow-only` y `npm run licenses`.
6. gitleaks sobre el historial.
7. `check-image-secrets.sh` contra `apex-api:local`.

**V10 · Revisión de seguridad posterior (`security-reviewer`)**
Verifica:
- la definición de hecho del sprint;
- H-1 a H-4 y M-1 a M-9 de la revisión del diseño;
- L-1 a L-13 de la revisión del diseño;
- la deuda del Sprint 1 cerrada (M-1, M-2, M-3, M-8, L-1, L-4, L-5, L-8).

Todo CRITICAL o HIGH se corrige dentro del sprint antes de cerrar.

**V11 · `verify-delivery`**
- Matriz N/M de las 26 historias, los 29 endpoints, las 4 migraciones, las 8 condiciones para VERDE, los hallazgos H, M y L y la deuda del Sprint 1, cada fila con su evidencia.
- Desviaciones declaradas (`0005b`, logout público, `me/password` con 200, `issue-reset-link`).
- Prueba contra el sistema real (V4 a V6).

**V12 · Paso humano**
Push de la rama, PR con CI en verde (`api`, `web`, `images`, `scripts`, `secrets-scan`, `e2e-stack`) y merge.

## 8. Riesgos y mitigación

1. **[HIGH] El cifrado de `members` queda fijado con datos reales (índice único, blob, normalización).** `test_members_encrypted_at_rest.py` corre en cada gate desde B7, no se cargan socios reales antes del release y `document_type` entra ahora, antes de aplicar `0006`.
2. **[HIGH] El commit explícito antes del 401** (login, reuso y `commit_failure`) rompe "una transacción por petición". Queda acotado a `auth/tokens.commit_failure`, con pruebas que simulan el rollback de `get_session`. Plan B: el service devuelve un resultado de fallo y el router confirma antes de lanzar.
3. **[HIGH] Bloqueo de cuentas por intentos (DoS).** Solo cuentan fallos, la clave es `(correo, red)` y el último admin queda exento. Existen `unlock` por API, `cli unlock-user` y `restart api`.
4. **[MEDIUM] El `--reload` aplica migraciones a medias.** P-MIG detiene el api mientras se redacta.
5. **[MEDIUM] Concurrencia de refresh entre pestañas.** Single-flight, Web Locks, canal con secuencia, gracia de 10 s y el E2E `refresh-two-tabs`.
6. **[MEDIUM] Con `require_same_origin`, un cliente sin `Origin` recibe 403.** Las fixtures, `compose-smoke` y `headers.sh` envían `Origin`, y `AUTH_ALLOWED_ORIGINS` cubre el proxy de Vite.
7. **[MEDIUM] Recrear la red de Compose** exige `down`. Se hace sin `-v` y los volúmenes se conservan.
8. **[MEDIUM] Divergencia entre `types.ts` del worktree y el de la rama del sprint.** Solo el backend lo regenera; rebase antes de cada slice dependiente y verificación en V1.
9. **[MEDIUM] La matriz de permisos del front no coincide con la del API.** `role-guards.spec.ts`, pruebas de router con 403 y `test_auth_routes`.
10. **[MEDIUM] El hook `config-protection` puede bloquear `vite.config.ts` o `playwright.config.ts`.** Se detiene y se presentan opciones; no se rodea.
11. **[LOW] Ventana menor de 1 s en `tokens_valid_after`.** Aceptada y documentada.
12. **[LOW] Node 24 local frente a Node 22 en CI.** Manda `package-lock.json`; el job `web` de CI lo valida.
13. **[LOW] El enlace del 409 da NotFound hasta S3-B9/S3-F1.** Documentado como `// DESIGN-GAP:`.
14. **[LOW] La prueba de rendimiento puede alargar el gate.** Si ocurre, se siembra solo el documento, sin cambiar lo que mide.

## 9. Rollback por migración

Regla general:
1. Bajar la migración primero: `$DC exec api alembic downgrade <revisión anterior>`.
2. Después revertir el checkpoint del slice con `git revert <sha>`.
3. Después `$DC restart api`.

Si se revierte primero el código, el archivo de migración desaparece y el arranque falla con "Can't locate revision". Antes de cada migración se guarda un `pg_dump -Fc` (P-MIG, paso 1); restaurar es `pg_restore --clean` sobre `apex-db-1`.

- **`0005_settings`:** `downgrade 0004_auth` borra `settings.settings_sections`; se pierde la configuración de desarrollo. Hay que revertir B1, y también B2 o posteriores si existen, porque `0005b` depende de ella: bajar en cadena `0007 → 0006 → 0005b → 0005`.
- **`0005b_auth_security`:** `downgrade 0005_settings` quita las cuatro columnas y el CHECK. El código de B2 a B5 las usa: se revierten esos checkpoints en orden inverso. Las sesiones vigentes siguen siendo válidas.
- **`0006_members`:** `downgrade 0005b_auth_security` borra `members.members` y sus blobs. Las llaves de `crypto_keys` se conservan. Solo hay datos de desarrollo. Se revierten B7 y B8 (y F6 si se fusionó).
- **`0007_plans`:** `downgrade 0006_members` borra `plans.plans`. Se revierte B9 (y F7).
- En CI y `db_test` no hace falta rollback: `migrated_database` vuelve a migrar desde cero.

## 10. Trazabilidad

### Condiciones para VERDE del impacto

1. `test_no_sensitive_in_logs` implementada: B7.3.
2. `audit` con `router.py` vacío, `test_audited_tables` con `find_spec`, y `cli` llamando a `load_module_services`: B6.
3. M-1, M-3 (Nginx), L-1 y M-8 (Compose): W0-1.3. M-2, M-3 (keyring), L-5 y L-8: B2.
4. `FRONT_BASE_URL` del `.env` local y comentario de `.env.example`: W0-1.3 y W0-1.4, verificado en B3.1.
5. Contrato, migraciones contra `db_test`, un solo head y ciclo en `apex-db-1`: P-API y P-MIG. Se decide no agregar un paso de CI y apuntar a `test_migrations.py` (W0-1.1 y B1.2).
6. Contradicciones de contrato: W0-1.1 y S2-D43 a S2-D50. `homeFor` sin literales: S2-D23, en F2.
7. Fixture de cliente autenticado: B1.1. Fábricas: B1.1 (usuarios), B7.1 y B9.1. Limpieza de sesión: B1, B2, B7 y B9.
8. `build web` antes de E2E y `build api` antes de `tools`: sección 0 y los pasos de Docker de cada slice.

### Revisión de seguridad del diseño

- **H-1:** B2 y F3.
- **H-2:** B4.
- **H-3:** B2, B3, B4 y B5.
- **H-4:** B2 (y B5 para limpiar los contadores).
- **M-1:** B2.
- **M-2:** B2.
- **M-3:** W0-1.
- **M-4:** B7 y F6.
- **M-5:** B7 y F6.
- **M-6:** B2 y B4.
- **M-7:** B2 y B4.
- **M-8:** B8 y F6 (socios), F4a (usuarios).
- **M-9:** B2.
- **LOW:**
  - L-1 en B7 y B8;
  - L-2 en B3;
  - L-3 en B7;
  - L-4 en B2;
  - L-5 en F2;
  - L-6 en F3;
  - L-7 en F4a y F4b;
  - L-8 en B2 y B6;
  - L-9 en W0-1 y B2;
  - L-10 en B2;
  - L-11 en B2 (y su latencia se mide en B8);
  - L-12 en W0-1, B2, B4 y F3;
  - L-13 en B4, B6 y F4b.
  - Ninguno se difiere.

### Deuda del Sprint 1

- **M-1:** W0-1, verificada en B2.
- **M-2:** B2.
- **M-3:** W0-1 (Nginx) y B2 (keyring).
- **M-8:** W0-1 (Compose), B2 (`SeedSettings` y columna) y B3 (`require_role`).
- **L-1:** W0-1.
- **L-4:** B2.
- **L-5:** B2 y B3.
- **L-8:** B2, con el validador de M-9.
- Fuera de este sprint, con el dueño que ya tienen en el cuaderno del Sprint 1: M-7, L-3 y L-7.

### Lo único que pasa al Sprint 3

- El caso `reveal` de `test_no_sensitive_in_logs` y el cambio de `test_reveal_entry` a la fábrica de socios: S3-B10 (US-074). El endpoint `reveal` no existe hasta entonces.
- El enlace del 409 a `/socios/{id}`, que funciona desde S3-B9 y S3-F1. La ficha es US-073.

### Conteo

- **Slices:** 18. W0-1; B1 a B9; F1, F2, F3, F4a, F4b, F5, F6, F7 y F8.
- **Pasos:** 139.
  - W0-1: 9.
  - Backend: B1 9, B2 12, B3 8, B4 8, B5 8, B6 8, B7 9, B8 7, B9 7.
  - Front: F1 6, F2 7, F3 7, F4a 7, F4b 6, F5 6, F6 6, F7 6, F8 6.
- **Validación:** 12 pasos (V1 a V12).
- **Checkpoints:** 18.
- **Migraciones:** 4.
- **Endpoints:** 29.
- **Decisiones del bloque "Sprint 2":** 53 (S2-D1 a S2-D53).

---

Ruta del archivo: `C:\Users\PC\Proyectos\Apex\docs\ddd\blueprints\sprint-02-plan.md`. Hay que crearlo con el contenido de arriba, porque no pude escribirlo yo.
