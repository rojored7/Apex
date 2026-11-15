# Sprint 8 · cuaderno (backend y orquestador)

Rama `feat/sprint-08-wods-resultados-tv`, HEAD de partida `4859031` (sobre `8b2db15`, cierre de v0.4.0 y `main`). Head de Alembic de partida: `0031_refresh_kiosk_path`.

## Planificación

- Impacto: `docs/ddd/blueprints/sprint-08-impacto.md`
- Exploración: `docs/ddd/blueprints/sprint-08-exploracion.md`
- Blueprint: `docs/ddd/blueprints/sprint-08-blueprint.md`
- Diseño de seguridad: `docs/ddd/blueprints/sprint-08-seguridad-diseno.md`
- Plan (aprobado por la orden del usuario del 2026-11-14, S8-D43): `docs/ddd/blueprints/sprint-08-plan.md`
- Críticas del plan: `docs/ddd/blueprints/sprint-08-critica-1.md`, `sprint-08-critica-2.md`

## W0-1 · documentos y decisiones (2026-11-15)

- Decisiones S8-D1 a D43 en `docs/ddd/DECISIONES.md` (bloque «Sprint 8»); migraciones reales `0032` a `0038_kiosk_results_path` en `SPRINT-08.md`, `BREAKDOWN.md` (EP-22) y DECISIONES.
- T-DOC en US-165, US-166, US-168, US-169, US-170, US-171, US-173, US-174, US-175, US-176 y US-177; `BRECHAS.md` (§4: validar resultados a EP-25; §16 nueva con los DESIGN-GAP de S8-D5, D6, D7, D8, D19 y D20); `03_context_map.md` (aristas de S8-D4); `CLAUDE.md` (módulos `wods`, `results` y `tv`, `seed-benchmarks`, 12 rutas de quiosco, 27 cubetas y 26 variables, `TV_IP_LIMIT` y `TV_TOKEN_LIMIT`, `0038`, `nightly.yml`).
- No hay Rojo ni Verde (documentos).

### Línea base de partida (de `sprint-08-impacto.md` §5)

- Cierre del Sprint 7 (S7-D43, sobre `e38b65b`): api 10 375 pasan y 103 omitidas, cobertura 95,39 %; web 4 261 pasan, 98,19 % de líneas (2 hilos).
- `tests/architecture` en `8b2db15`: 847 passed en 113,3 s (`db_test` en 5443).

### Evidencia

- Gate `bash scripts/workflow/slice-gate.sh architecture`: exit 0, 847 passed en 110,9 s (igual que la línea base).

## W0-2 · Nginx, redacción del log y job nocturno (2026-11-15)

### Rojo

- `tests/core/test_logging_redact.py` (en el archivo existente): `test_redacta_x_device_token_en_cualquier_mayuscula` y `test_redact_text_recorta_x_device_token_en_texto_libre` (4 casos): 5 failed (la clave no estaba en `SENSITIVE_KEYS` y el texto libre dejaba el valor).
- `scripts/ci/test_nightly_workflow.sh` (nuevo): exit 1, `nightly.yml` no existía.
- `scripts/ci/test_nginx_conf.sh` (bloque «Rojo S8-W0-2»): 1 falla, falta el comentario junto a `location /` que diga que `/tv` pasa por ahí. Las comprobaciones funcionales de `/tv` (200, `no-store`, `no-referrer`, CSP con nonce, log sin consulta) ya pasaban con la configuración vigente (hallazgo 12: no hace falta `location` nuevo) y quedan como guarda.

### Verde

- `infra/nginx/default.conf`: solo el comentario junto a `location /` (sin `location` nuevo).
- `api/src/app/core/logging.py`: `x-device-token` en `SENSITIVE_KEYS` y en la expresión de cabecera de texto libre (`x-(vault|device)-token`).
- `.github/workflows/nightly.yml` (nuevo): `schedule` (07:17 UTC) y `workflow_dispatch`, permisos de lectura, acciones por SHA, job `tv-soak` con un paso que pasa (la spec real llega en F6). `ci.yml` (job `scripts`), `run-gates.sh` y `wave0-gate.sh` corren `test_nightly_workflow.sh`.
- Resultado: `test_logging_redact.py` 49 passed; `test_nginx_conf.sh` 0 fallas; `test_nightly_workflow.sh` 0 fallas; `test_images_pinned.sh` 0 fallas.

### Evidencia

- P-REBUILD 3: `docker buildx build --load --network host --allow network.host -t apex-web:local -f web/Dockerfile .` y `$DC up -d --no-build --force-recreate web` (con `apex-migracion.flag` tomada y soltada); `nginx -t` ok.
- `curl -s -D - -o /dev/null 'http://127.0.0.1:8180/tv?token=prueba-sin-valor'`: 200, `Cache-Control: no-store`, `Referrer-Policy: no-referrer` y CSP con `nonce-` por petición. `$DC logs web --tail 20 | grep -c 'token='`: 0.
- Gate: `wave0-gate.sh S8-W0-2` quedó colgado ~20 min en `test_infra_scripts.sh` (`test_restore_guard.sh`: fallos de `fork` de Cygwin en Windows, `Win32 error 299`), ajeno al slice; se cortó y no se cuenta. Corridos aparte, en verde: `test_nginx_conf.sh` 0 fallas, `test_nightly_workflow.sh` 0 fallas, `test_images_pinned.sh` 0 fallas, `bash -n` de `run-gates.sh` y `wave0-gate.sh`. Sello con `slice-gate.sh core/logging tests/core/test_logging_redact.py` (ruff, mypy y pruebas del módulo).

## W0-3 · línea base, cubetas y listas de arquitectura (2026-11-15)

Paso 0: `apex-migracion.flag` tomada (el slice reinicia el api) y `$DC stop api worker` antes de escribir código.

### Línea base (antes del Verde, sobre `cdcba31`)

- `tests/architecture`: 847 passed en 110,9 s (gate de W0-1); con W0-2, 896 passed en el sello de `core/logging`.
- Suite completa del api (una corrida): 10 387 passed, 103 skipped, 44 deselected (`perf`), en 1 717,7 s (28 min 38 s). Cero fallas.
- `mypy src`: Success, sin errores en 243 archivos.
- Web: vitest con `--pool=forks --maxWorkers=2`: 4 273 passed (4 273), 307 s, exit 0.
- `ruff check .` y `ruff format --check .` de todo el api: ver el resultado al final del bloque.
- `ruff check .`: All checks passed; `ruff format --check .`: 956 files already formatted (todo el api, antes del Verde).
- La suite completa corrió en segundo plano del arnés (el primer plano topa a los 10 min) y fue la única `pytest` en marcha.

### Rojo

Archivos de prueba tocados: `tests/core/test_ratelimit.py` (`test_hay_27_cubetas`, `test_tv_fail_y_tv_existen_con_su_ventana`, los `== 25` pasan a 27, `CATALOGO` y el dict de `user_limits_from`), `tests/core/test_config.py` (`test_limites_de_wods_resultados_y_tv`, `test_tv_limit_fuera_de_1_a_120_falla_nombrando_la_variable` ×8), `tests/core/test_env_example.py` (`test_26_variables_user`, `test_el_comentario_del_catalogo_dice_27_cubetas_y_26_variables`, `test_ci_sube_las_veintiseis_variables_user_y_cuenta_veintiseis`, `test_tv_ip_y_token_documentadas`, `test_ci_fija_tv_ip_y_token_en_120_dentro_de_la_cota` y los `== 24`/`== 25` de las otras), `tests/core/test_db.py` (`classes` en `APP_SCHEMAS`), `tests/architecture/test_user_limits_catalog.py` (`CLAVES_SIN_RUTA_TODAVIA` con `wods-write` y `results-write`, 27 cubetas), `test_no_cross_schema_sql.py` (`ESQUEMAS` con `wods` y `results`; `MODULOS_PENDIENTES` con los dos hasta A1 y B1) y `test_audited_tables.py` (`PENDING_AUDITED`: sale `results.results`, entran las cinco de v0.5 y `athletes.personal_records`).
Antes se corrió `grep -rn "== 25\|== 24\|25 cubetas\|24 variables\|veinticuatro" api/tests` y se migró todo lo que era de cubetas (los demás `== 25` son tamaños de página).
Rojo medido sobre los 8 archivos: 26 failed, 379 passed (campos y cubetas inexistentes, `.env.example` y `ci.yml` sin las variables, `classes` fuera de `APP_SCHEMAS`).

### Verde

- `core/config.py`: `USER_WODS_WRITE_LIMIT_PER_MIN` (30), `USER_RESULTS_WRITE_LIMIT_PER_MIN` (60), `TV_IP_LIMIT` (12) y `TV_TOKEN_LIMIT` (30), estas dos con `ge=1, le=120`.
- `core/ratelimit.py`: `wods-write` y `results-write` en `USER_LIMITS` y `user_limits_from`; `tv-fail` y `tv` en `rate_limits_from` (ventana 60 s).
- `core/db.py`: `classes` en `APP_SCHEMAS`.
- `.env.example` (comentario «27 cubetas y 26 variables»), `infra/compose.yml` (bloque `environment` del api) y `.github/workflows/ci.yml` (job E2E: dos `-e` de las `USER_*`, una línea `-e 's/^(TV_IP_LIMIT|TV_TOKEN_LIMIT)=.*/\1=120/'` aparte, conteo 26).
- Desviación: `config.py` pasó de 799 a 808 líneas (`test_ningun_archivo_supera_800_lineas` falló en el primer gate); se extrajo `NON_API_ENV_VARS` (solo datos) a `core/config_non_api.py`, que `config.py` reexporta (mismo patrón que `config_ops.py`); `config.py` queda en 752 líneas.
- Resultado: los 8 archivos del Rojo, 405 passed.

### Evidencia

- Gate no sellante `slice-gate.sh architecture` + `test_user_limits_catalog`, `test_no_cross_schema_sql`, `test_audited_tables`: 853 passed en 109,4 s (el primer intento dio 1 failed por el límite de 800 líneas).
- P-REBUILD 1: `$DC up -d --no-build api worker` (el compose cambió, hace falta recrear): api healthy, `/health` = `status ok, db ok, migrations ok, crypto ok`, `alembic current` = `0031_refresh_kiosk_path (head)` (el slice no lleva migración), y el entorno del api trae `USER_WODS_WRITE_LIMIT_PER_MIN=30`, `USER_RESULTS_WRITE_LIMIT_PER_MIN=60`, `TV_IP_LIMIT=12` y `TV_TOKEN_LIMIT=30`. `apex-migracion.flag` tomada al empezar y borrada tras el reinicio.
- Sello: `slice-gate.sh core/ratelimit tests/core/test_ratelimit.py tests/core/test_config.py tests/core/test_env_example.py tests/core/test_db.py tests/core/test_migrations.py` (ruff, mypy y pruebas; ver el reporte).

## S8-A1 · Movimientos (US-165, S8-D5) · 0032

### Rojo
- `tests/migrations/test_0032_wods_movements.py` sin la revisión: 1 failed + 8 errors (`no existe la revisión 0032_wods_movements`).
- Tras la migración y con stubs `NotImplementedError` (rules, movements) y router vacío: 31 failed (9 de `test_normalize_pure`, 12 de `test_movements_service` por `NotImplementedError`, 10 de `test_router_movements`: rutas ausentes) y 95 passed (la migración, ya escrita, 9 de 9).
- Un primer rojo falso (29 errors) fue un `$$` mal escapado por mi script de edición en `LIMPIAR_MOVEMENTS` (`syntax error at or near "$"`); corregido antes de medir.

### Verde
- Migración `0032_wods_movements` (esquema `wods`, `wods.movements`, `uq_movements_name_norm`, 4 CHECK, `wods.forbid_mutation()` y 2 triggers `ENABLE ALWAYS`), módulo `wods` (`rules`, `movements`, `models`, `schemas`, `exceptions`, `service`, `router`), `main.MODULES`, `APP_SCHEMAS`, `env.py`, `audit/queries.py`, P-ROL (las tres listas, REVOKE/USAGE por esquema: el worker sin USAGE sobre `wods`), P-CAT (`MODULOS_PENDIENTES`, `CLAVES_SIN_RUTA_TODAVIA`, `CON_LIMITE`, `MODULES`, `PRIVATE_HELPERS`, `PENDING_AUDITED`, conftest, `ALWAYS_TRIGGERS`, `test_no_physical_delete`, `test_0014` y `test_db_apply` fijaban listas de esquemas/tablas).
- Desviaciones: (1) `wod_count` es 0 en A1 (`wod_movements` nace en A3) detrás de la costura `usage_counts`, una llamada por página (probado con un espía); `test_desactivar_no_cambia_wods` prueba solo `is_active` y A3 suma la parte de WODs. (2) El esquema se llama `CatalogMovementOut`: `MovementOut` ya existe en `dashboard` y el OpenAPI lo renombraba a `app__modules__dashboard__schemas__MovementOut`. (3) `name` se guarda con espacios internos colapsados (`clean_movement_name`). (4) No hay `events.py` (A1 no emite eventos).
- grep de conftest propios que borran socios/usuarios/clases (`LIMPIAR_MEMBERS|DELETE FROM members|DELETE FROM classes|TRUNCATE` en `api/tests/*/conftest.py`): sin coincidencias; `wods.movements` no tiene FK.

### Evidencia
- Pruebas nuevas: 41 (10 puras, 12 de service, 10 de router, 9 de migración) y `test_wods_no_tiene_aristas_salientes_en_a1`.
- `tests/core/test_migrations.py tests/migrations tests/core/test_db.py`: 2 failed al primer intento (`test_0014` inventario y `test_db_apply` conteo de tablas) por listas fijas; corregidas, 56 passed.
- `ruff check .` y `ruff format --check .` de todo el api limpios (971 archivos); `mypy src` sin errores en 252 archivos.
- Gate sellante `slice-gate.sh wods <10 archivos del plan>`: 1 169 passed en 143 s, exit 0.
- P-API: `openapi.json` idéntico en dos corridas (+589 líneas, ninguna borrada), `types.ts` regenerado, `types.contract.test.ts` 6 passed.
- P-MIG 5-7: `$DC start api` healthy, `alembic current` = `0032_wods_movements (head)`; `$DC start worker`; `downgrade -1` + `upgrade head` + `current` = 0032 (head); `\d wods.movements` con sus índices, CHECK y los dos triggers `tgenabled = A`; `wods.forbid_mutation` invoker.
- Smoke por curl a 8181: `/health` ok/ok/ok/ok; `GET`, `POST` y `PATCH /api/v1/movements` sin token = 401; `/openapi.json` publica `/api/v1/movements` y `/api/v1/movements/{movement_id}`. Smoke con rol NO hecho: el arnés denegó acuñar un token de admin fuera del login y el dev no tiene contraseña conocida; los 41 casos con rol corrieron contra la base real en las pruebas.
- Volcado previo: `docs/scratch/sprint-08-antes-0032.dump` (ignorado por git; se borra en V9).

## S8-W0b · Correcciones de la revisión de la Wave 0 (5 LOW)

- L1 (rojo medido: 11 failed en `tests/core/test_logging_redact.py`): `core/logging.py` suma `device_token` y `x_device_token` a `SENSITIVE_KEYS`, `_VAULT_HEADER` acepta `-` o `_`, la coma de la tupla ASGI `(b'x-device-token', b'...')` y el prefijo `b`, y `_TOKEN_PARAM` limpia `?token=`, `&token=` y `#token=` en texto libre. Control sin falsos positivos.
- L4 (rojo medido: 2 failed con el stub): `tests/architecture/test_tv_bucket_not_by_ip.py` (control con una ruta falsa que lleva `rate_limit("tv")` y barrido de las rutas reales); comentario en `rate_limits_from` (C2 usa `enforce(..., kind="account")`).
- L5 (rojo medido: un workflow con `packages: write` y otro con `workflow_run` daban exit 0): `scripts/ci/test_nightly_workflow.sh` rechaza cualquier `: write` y `workflow_run`; los dos falsos dan exit 1 y el real 0 fallas.
- L2: `ci.yml` exige `grep -c ... = 2` de `TV_IP_LIMIT` y `TV_TOKEN_LIMIT`. L3: `DECISIONES.md` (f) suma S8-D32 a las correcciones de S8-D18 (W0-2 no añade `location = /tv`).
- Gate sellante `slice-gate.sh core/logging` + los 4 archivos de prueba: 1 016 passed en 117 s, exit 0; `ruff` y `mypy src` limpios.

## S8-A2 · Benchmarks y `seed-benchmarks` (US-166, N-46, S8-D6, L-6) · 0033

### Rojo
- Con stubs `NotImplementedError` (`benchmarks.py`, `seed.py`), comando registrado como no-op y sin la migración: 25 failed + 8 errors + 12 passed (los 12 son 403/401/422 del router y movimientos que no dependen del stub). Motivos: service y seed `NotImplementedError`; comando ausente (exit 2); `no existe la revisión 0033_wods_benchmarks` (1 failed + 8 errors); `test_ci_siembra_benchmarks_tras_el_admin` sin el paso en `ci.yml`.

### Verde
- Migración `0033_wods_benchmarks` (tabla, `uq_benchmarks_name_norm`, 4 CHECK, 2 triggers `ENABLE ALWAYS` sobre `wods.forbid_mutation()` de 0032; el `downgrade` no la borra), `wods/{benchmarks,seed}.py`, `cli_ops/seed_benchmarks.py` + `register_ops`, 3 rutas en el router plano de `wods`, `ci.yml` (paso tras el seed del admin), P-ROL (las tres listas de `grants.sql` + `test_db_grants`), P-CAT (`AUDITABLE_TABLES`, excluida de recientes, `test_audited_tables`, `test_no_physical_delete`, `triggers.py`, `test_0014`, `CON_LIMITE`, `conftest` con `LIMPIAR_BENCHMARKS`, `tests/audit/test_filters.py`, que A1 había dejado sin `wods.movements`).
- Desviaciones: (1) `score_type_locked` se prueba con un doble de `benchmarks.wod_counts` (misma costura que `usage_counts` de A1), no de `ResultsProbe`: en A2 no hay WODs; A3 la reemplaza. (2) `description` usa `check_multiline_text` (vacía vale; admite saltos de línea) en vez de `SafeText`, que rechaza el vacío. (3) La prueba A1 `test_el_router_publica_tres_rutas_...` pasó a seis rutas (router plano único). (4) El `INSERT ... ON CONFLICT` de Core no pasa por el hook del ORM: `seed.py` escribe una fila `insert` por benchmark creado con `core.audit.record`.
- Normalización de nombres: la misma `normalize_movement_name` (pliega mayúsculas y espacios, NO tildes).

### Evidencia
- 120 passed de los archivos nuevos y `test_env_example`; `tests/migrations tests/architecture tests/core/test_migrations.py tests/core/test_db.py tests/audit`: 2 380 passed, 1 failed (`test_filters`, corregido) y `alembic heads` = una sola cabeza.
- `ruff check .`, `ruff format` y `mypy src` (255 archivos) limpios.
- Gate sellante `slice-gate.sh wods <12 archivos>`: 1 362 passed en 151 s, exit 0.
- P-API: `openapi.json` idéntico en dos corridas (+539 líneas), `types.ts` regenerado, `types.contract.test.ts` 6 passed.
- P-MIG: `$DC start api` healthy, `alembic current` = `0033_wods_benchmarks (head)`; `downgrade -1` + `upgrade head` OK; `\d wods.benchmarks` con índices, 4 CHECK y los dos triggers `tgenabled = A`.
- `seed-benchmarks --as admin@ejemplo.local` dos veces: «creados 12» y «creados 0»; `count(*) wods.benchmarks` = 12 y 12; filas `audit_log` de `wods.benchmarks` = 12 y 12.
- Smoke con rol (admin de desarrollo): `GET /api/v1/benchmarks?q=fra` = 200 (total 1, Fran, time, wod_count 0); sin token = 401.
- Checkpoint `31850e9`.

## S8-A1b · Correcciones de la revisión de A1

- Rojo: 3 failed (2 de la carrera 23505 con `PendingRollbackError` y 1 de `x-device-token, content-type` redactado de más).
- Hallazgo real: `begin_nested()` vacía lo pendiente al abrirse, así que el `INSERT` fallaba FUERA del savepoint y dejaba la sesión inservible (un 500 en vez del 409). `_flush_unico` pasó a `_guardar_unico(session, norm, exclude, aplicar)`: el cambio se aplica dentro del savepoint (movimientos y benchmarks).
- `_VAULT_HEADER`: la coma solo vale tras comilla de cierre. DECISIONES: S8-D21 (USAGE sin el worker) y S8-D5 (unicidad sin pliegue de tildes; `seed-benchmarks` usa el mismo `name_norm`).
- Verde: gate sellante `slice-gate.sh wods <6 archivos>` 966 passed, exit 0; `ruff` y `mypy` limpios. `docker cp` no necesario: el api recarga con `--reload` (dev).
