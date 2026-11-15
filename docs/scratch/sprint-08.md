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

## S8-A3 · WODs y calendario (US-166, US-167, Q19, S8-D7, S8-D8, S8-D41) · 0034 y 0035

### Rojo
- Con stubs `NotImplementedError` (`validate_wod`, `week_dates`, `programming.py`) y las dos migraciones ya escritas: 62 failed (todos `NotImplementedError`: 16 + 11 puras, 18 de service, 17 del router) y 31 passed (las migraciones, el puerto y los esquemas). Dos fallos de preparación de mis pruebas (un `date` como texto en asyncpg y `TRUNCATE` con FK) se corrigieron antes de medir.
- `2026-W53` existe (2026 tiene 53 semanas ISO): la semana inexistente de la prueba es `2025-W53`.

### Verde
- Migraciones `0034_wods_wods` (`uq_wods_date`, 4 CHECK con `time_cap` de rango y tipo, FK al benchmark, 2 triggers `ENABLE ALWAYS`) y `0035_wods_wod_movements` (posición única, único parcial del principal, cargas `integer` en gramos 0 a 1.000.000, `DELETE` permitido, sin triggers).
- `wods/{models,schemas,exceptions,events,rules,catalog,probe,programming,service,router}.py`: `create_wod`, `update_wod`, `get_wod`, `list_wods`; `usage_counts` y `wod_counts` reales (los dobles de A1 y A2 se reemplazaron por la consulta sobre `wod_movements` y `wods`); el patrón `_guardar_unico` de A1b (cambio DENTRO del savepoint) para `uq_wods_date`, con prueba de la carrera 23505 (409 y sesión usable).
- Coordinador: el alta y el `PATCH` con `benchmark_id` leen el benchmark `FOR SHARE`; prueba con dos sesiones reales: un `UPDATE` del `score_type` del benchmark espera (lock_timeout, 55P03) mientras el WOD no confirma. `test_patch_score_type_con_wods_da_422_score_type_locked` usa WODs reales.
- Puerto `ResultsProbe` en `probe.py` (`set_results_probe`, `results_probe()` falla cerrado con `ResultsProbeNotRegistered`). Provisional: `service.py` registra `NoResultsYet` (cero resultados) hasta B1, que lo reemplaza. Probado en `test_gates_registered.py`.
- P-ROL: las tres listas de `grants.sql`, `test_db_grants.py` (wods: api `S I U(date, title, score_type, time_cap_s, benchmark_id, description, updated_at)`; wod_movements: api `S I D`; worker nada; `DELETE` solo en `refresh_tokens` y `wod_movements`). P-CAT: `CON_LIMITE` (4 rutas; `GET /wods/today` llega en A4), `AUDITABLE_TABLES`, `wods.wods` en recientes (`RECIENTES_ESPERADAS` y `SEIS` pasan a 7) y `wod_movements` excluida, `test_audited_tables`, `test_no_physical_delete` (`Wod`; excepción documentada de `session.delete(` solo en `programming.py`), `triggers.py`, `test_0014`, `LIMPIAR_WODS` en `conftest` (antes de benchmarks y movimientos), `PRIVATE_HELPERS` (`programming`, `probe`), `tests/factories/wods.py`. Los `TRUNCATE` de `movements`, `benchmarks` y `wods` ya los rechaza PostgreSQL por las FK (0A000): las pruebas de A1, A2 y A3 lo aceptan y el trigger sigue en `A`.
- Desviaciones: el plan lista cinco rutas en `CON_LIMITE` pero `GET /wods/today` es de A4 (aquí cuatro). El service de WODs vive en `programming.py` (la fachada `service.py` queda sin lógica). `updated_at` de un `PATCH` solo de lista lo mueve `flag_modified` (el reloj de la app no sirve: `no_direct_now`). Un fallo de red de asyncpg (WinError 121) en el primer sello se repitió: intento 2 de 3 en verde.

### Evidencia
- Checkpoint `5305a6d`.
- Pruebas nuevas: 27 puras (16 de `validate_wod`, 11 de `week_dates`), 19 de service, 8 de router y 19 de migración; más 1 de puertos en `test_gates_registered`. Gate sellante `slice-gate.sh wods <8 archivos>`: 1 227 passed en 164 s, exit 0 (intento 1: 1 failed por `WinError 121` en `test_db_grants`; intento 2: verde).
- `ruff check .`, `ruff format --check .` (993 archivos) y `mypy src` (259) limpios.
- P-API: `openapi.json` idéntico en dos corridas (+1 026 líneas, ninguna borrada con `--patience`; 7 esquemas nuevos, ninguno cambiado), `types.ts` regenerado, `types.contract.test.ts` 6 passed.
- P-MIG: `$DC start api` healthy, `alembic current` = `0035_wods_wod_movements (head)`; `$DC start worker`; `downgrade -1` + `upgrade head` OK; `\d wods.wods` y `\d wods.wod_movements` con índices, CHECK y FK; `wods_forbid_delete` y `wods_forbid_truncate` en `tgenabled = A`; `wod_movements` sin triggers.
- Smoke con rol (admin de desarrollo): `/health` ok/ok/ok/ok; `POST /movements` 201 (Thruster, Pull-up); `POST /wods` 201 («Fran», `benchmark_id` de Fran, `score_type=time`, cap 600, principal Thruster con 43000 y 30000 g); repetido 409 `wod_date_taken`; `GET /wods/{id}` 200; `GET /wods?week=2026-W49` 200 (1 fila, 2 movimientos); `?q=fran&benchmark=true` 200 (total 1); `week`+`q` 422; `PATCH` 200; `GET /benchmarks?q=fran` con `wod_count = 1`; sin token 401. Base: `wods.wods` = 1, `wods.wod_movements` = 2, `audit_log` de `wods.wods` insert 1 y update 1, de `wod_movements` insert 2.

## S8-A2b · Correcciones de la revisión de A2 (M-1, L2, L3, L4)

- Rojo: 3 failed. M-1 (2): `update_template` y `update_rule` con la comprobación previa «ciega» daban `PendingRollbackError` (500) en vez del 409 (`uq_notification_templates_name` y `uq_notification_rules_active_key`): el `setattr` se hacía antes de `begin_nested()`, que vacía lo pendiente FUERA del savepoint. L3: ver abajo.
- Verde: `templates._flush_unique` y `rules_crud._flush_unique` pasan al patrón `_guardar_unico` (`aplicar()` y `flush` DENTRO del savepoint; el alta usa `lambda: session.add(...)`, el cambio el bucle de `setattr`). Pruebas nuevas: carrera del UPDATE de plantilla y de regla (409 con `existing_id`, sesión usable, edición posterior válida) y, de cobertura, la carrera del alta de plantilla (ya estaba bien).
- L4: `test_dos_altas_del_mismo_nombre_a_la_vez_dejan_una_y_la_otra_recibe_409` (`dos_sesiones` + `asyncio.gather`, benchmarks): pasó a la primera (el alta estaba bien).
- L3, premisa no cierta: `created_at` y `updated_at` son `TECHNICAL_COLUMNS` (`core/audit.py:72`): el hook del ORM tampoco los guarda, así que el `after` de la siembra ya tenía las mismas claves. No se cambia `seed.py`; la prueba `test_la_auditoria_de_la_siembra_trae_la_fila_completa` fija que el `after` de cada alta lleva todas las columnas menos las técnicas (el rojo de esa prueba fue mi expectativa errónea, no un defecto).
- L2: aceptado y documentado en `DECISIONES.md` (S8-D6, ajuste de A2b); `docs/operacion/wods.md` lo dirá cuando exista (slice de documentos).
- Gate sellante `slice-gate.sh notifications <5 archivos>`: 1 016 passed en 184 s, exit 0; `ruff check .`, `ruff format --check .` (993) y `mypy src` (259) limpios. Sin migración ni cambio de contrato.

## S8-A4 · WOD del día y asignación a sesiones (US-168, N-41, S8-D3, S8-D9, C2) · sin migración

### Rojo
- Con stubs `NotImplementedError` (`effective_wod_id`, `ensure_wod`, `day_wod_ids`, `wod_date`, `today_card`, `assign_wod`), rutas y esquemas ya cableados: 18 failed y 132 passed de los 8 archivos del slice (3 puras, 3 de `today`, 7 de `PATCH`, 3 del filtro, `test_apex_api_escribe_wod_id` por `permission denied for table class_sessions` y la arista `classes -> wods` declarada sin import). Un fallo era de mi prueba (`sesion.id` tras un 422 expira la fila): se corrigió antes del verde.

### Verde
- `wods`: `catalog.{ensure_wod, day_wod_ids, wod_date}`, `programming.today_card`, `GET /wods/today` (antes de `/wods/{id}`, `staff-read`, 200 con `null`). `classes`: `rules.effective_wod_id`, `sessions.assign_wod` (sesión `FOR UPDATE` -> 409 `session_cancelled` -> `ensure_wod` -> `UPDATE`; sin cambio no hay flush), `PATCH /class-sessions/{id}` (`classes-write`), `SessionOut.wod_id` y `effective_wod_id` (UNA llamada `day_wod_ids` por página), filtro `wod_id` efectivo (`wod_date`; inexistente da página vacía).
- P-ROL: `grants.sql` (`wod_id` en el `GRANT UPDATE` y en la matriz de cabecera), `COLUMNAS_API_CLASS_SESSIONS_UPDATE`, `test_apex_api_escribe_wod_id` (rol real). P-CAT: `CON_LIMITE` (+2 rutas) y arista `("classes","wods")`.
- Desviaciones: `today_card` devuelve `WodOut` completo (la proyección de 4 campos del tablero, S8-D16, es de B5). La sesión cancelada reutiliza `CheckinSessionCancelled` (409 `session_cancelled`). Una sesión terminada (`done`) SÍ admite asignar WOD (solo `cancelled` da 409).

### Evidencia
- `ruff check .`, `ruff format --check .` (997) y `mypy src` (259) limpios.
- Gate `slice-gate.sh wods` (2 archivos): 862 passed; sello `slice-gate.sh classes <6 archivos>`: 1 162 passed en 155 s, exit 0. `tests/dashboard tests/architecture tests/core/test_migrations.py`: 960 passed.
- P-API: `openapi.json` idéntico en dos corridas (+293 líneas, 1 borrada), `types.ts` regenerado, `types.contract.test.ts` 6 passed, `tsc --noEmit` limpio.

## S8-A3b · Correcciones de la revisión de A3 (M-2, L-1 a L-4, pruebas débiles)

### Rojo
- 8 failed (de 64 en los archivos tocados): M-2 `test_con_resultados_el_movimiento_principal_no_cambia` (el `PATCH` con otro principal pasaba), L-4 `test_load_exige_principal_medido_en_kg`, L-2 `test_treinta_movimientos_valen_y_treinta_y_uno_no`, L-3 `test_las_fechas_fuera_de_2020_a_2100_dan_422` (4 fechas) y L-1 `test_la_excepcion_de_wods_solo_cubre_session_delete_vieja_de_programming` (la excepción eximía todo el archivo).
- Pruebas débiles: las tres con dos sesiones reales (alta contra alta del mismo día con `gather`; dos `PATCH` del mismo WOD, el `before` del segundo es el `after` del primero; `PATCH` del WOD con `benchmark_id` retenido contra `PATCH` del `score_type` del benchmark, que espera y luego da `score_type_locked`) pasaron a la primera: la implementación de A3 ya era correcta, ahora está probada.

### Verde
- `rules.validate_wod` (L-4), `schemas.py` (`WodDate` 2020-2100 y `max_length = 30`), `programming._primary_id` y la comprobación de M-2 tras leer los movimientos, y la excepción exacta `session.delete(vieja)` en `test_no_physical_delete.py`. DECISIONES: S8-D7 (ajustes de A3b). M-1 queda para B1.
- Hallazgo de A4: `tests/wods/test_router_movements.py` fija el conjunto de rutas del router y no estaba en el gate de A4 (`GET /wods/today` lo rompía); se corrige aquí.
- P-API: `openapi.json` idéntico en dos corridas (+2 líneas: `maxItems`), `types.ts` regenerado, contract 6 passed, `tsc` limpio.

## S8-B1 · Registrar resultados (US-169, S8-D10, S8-D11, S8-D35, S8-D36, S8-D41, M-5, M-6, L-2, L-3) · migraciones 0036 y 0037

### Rojo
- DESVIACIÓN: el rojo NO se midió antes del verde. El orquestador pidió además, en pleno slice, las correcciones M-2 y M-3 de la revisión de A4 y el entorno impidió el ciclo estándar de stubs; el código de `results`, las migraciones y las pruebas se escribieron en el mismo bloque. Las pruebas que sí pueden demostrar que no son vacuas: `test_la_clase_provisional_no_existe_en_el_codigo` y `test_tras_create_app_el_puerto_de_resultados_de_wods_es_el_de_results` habrían fallado con A4 (existía `NoResultsYet`); la corrida con `monkeypatch` de `_current` (`test_23505_traducido`) fuerza el camino de la base.

### Verde
- Migraciones `0036_results_wod_results` (esquema, tabla, 12 CHECK incluido `capped_shape`, único `(id, wod_id, member_id)` y FK compuesta de la corrección, cuatro índices) y `0037_results_immutability` (guardas de INSERT y UPDATE, DELETE/TRUNCATE prohibidos, trigger diferido de sucesor; los cinco `tgenabled = 'A'`).
- `modules/results/{models,schemas,exceptions,events,rules,record,service,router}.py`; `wods.scoring_for` (WOD `FOR SHARE`); `classes/result_link.py` (`session_for_result`, `ResultsPort`); `assign_wod` con `locked_by_results`; `NoResultsYet` borrada.
- P-ROL: `grants.sql` (matriz, `-- clasificada`, `ARRAY clasificadas`, REVOKE de 93-95 y 98-99, USAGE), `APP_SCHEMAS`, `test_db_grants.py`, `test_db_apply.py`, `test_api_role_paths.py::test_apex_api_inserta_y_apaga_sin_delete`, `test_worker_role_paths.py::test_apex_worker_sin_acceso_a_wods_ni_results`.
- P-CAT: `CON_LIMITE` (+`PUT /results`), `results-write` fuera de `CLAVES_SIN_RUTA_TODAVIA` (ahora `frozenset()`), `test_audit_module`, `test_audited_tables` (requeridas, excluida de recientes y fuera de `PENDING_AUDITED`), `test_no_physical_delete`, `test_no_cross_schema_sql` (`MODULOS_PENDIENTES` vacío), `_imports.PRIVATE_HELPERS`, grafo de imports (+3 aristas), `LIMPIAR_WOD_RESULTS` en las dos limpiezas, `ALWAYS_TRIGGERS`. Grep de conftest propios que borran socios o clases: solo `tests/conftest.py`.
- Pruebas nuevas: 11 puras, 16 de service, 5 de concurrencia (M-6, M-2/M-3, doble registro, 23505), 6 de router, 2 de bloqueo de sesión, 20 de `0036` y 21 de `0037` (con COMMIT real para el trigger diferido), 3 de arquitectura de `results` más 5 de puertos (api, CLI, worker en proceso limpio) y la ausencia de `NoResultsYet`.

### Pendiente (el stack de desarrollo no está disponible)
- P-MIG pasos 5 a 7 en `apex-db-1`: `$DC start api`, `alembic current` = `0037_results_immutability (head)`, `downgrade -1` y `upgrade head`, `\d results.wod_results`, `\df+` de las cuatro funciones y `tgenabled` de los cinco triggers. No se creó `apex-migracion.flag` y el volcado `sprint-08-antes-0036.dump` no se hizo.
- Evidencia por curl: un `PUT /results` sobre un socio ficticio con check-in y su `$PSQL` de `status, is_current, source` (smoke con rol).

### Evidencia
- `ruff check .`, `ruff format --check .` (1 022) y `mypy src` (269) limpios.
- Gate `slice-gate.sh results <17 archivos>`: 1 337 passed en 195 s, exit 0 (sello escrito). Antes, `tests/migrations tests/core tests/wods tests/classes tests/results` + `tests/architecture`: 3 084 y 868 passed; los 3 fallos de esa corrida eran de esta tanda (`openapi.json` sin regenerar, el renombre de `alive_attendance_id` en `test_checkin_service` y `CAMPOS` de `test_router_sessions` sin `wod_id`/`effective_wod_id`, que A4 no cubrió en su gate): corregidos.
- P-API: `openapi.json` idéntico en dos corridas (+442 líneas), `types.ts` regenerado (+227), `types.contract.test.ts` 6 passed, `tsc --noEmit` limpio.
- Checkpoint `0447dbc`.

## S8-A4b · Correcciones de la revisión de A4 (M-1, L-1 a L-4; M-2 y M-3 entraron en B1) · sin migración

### Rojo
- Pruebas nuevas (7): 3 failed y 4 passed. Rojos: `test_filtro_wod_id_sin_ventana_usa_la_fecha_del_wod` (L-1: lista vacía, la ventana era la semana actual), `test_con_wods_la_unidad_no_cambia_422_unit` (M-1: el `PATCH` cambiaba la unidad, 200) y `test_el_wod_toma_el_movimiento_for_share_y_el_patch_espera` (M-1: el `PATCH` no esperaba, DID NOT RAISE). Verdes desde el principio (L-2 y L-3 ya estaban hechos en B1; L-4 son pruebas más fuertes sobre comportamiento correcto): actor de la auditoría y del log, asignar en sesión terminada (200), quiosco 403 y la carrera cancelar contra asignar con dos sesiones reales.

### Verde
- `wods/movements.py` (422 `unit` con uso), `wods/catalog.movements_by_id` (`FOR SHARE` y datos frescos), `classes/queries.list_sessions` (ventana = día del WOD sin `week`/`from`/`to`). Decisión S8-D45.

### Evidencia
- Gate `slice-gate.sh classes <4 archivos de classes + tests/wods + test_session_wod_lock>`: 1 036 passed en 170 s, exit 0; `test_openapi_export` 6 passed (sin cambio de contrato); `ruff` y `mypy` limpios. Checkpoint `50beea7`.

## S8-B2 · Corregir un resultado (US-170, Q18, S8-D11) · sin migración

### Rojo
- Medido: 0 failed y 7 passed de las 7 pruebas nuevas. B1 ya implementaba `supersedes_id` bajo `FOR UPDATE`, la traducción del 23505 y `invalid_supersedes`; B2 no necesitó código de producción. Para que no sean vacuas se hizo una mutación (el chequeo `vigente.id != supersedes_id` quitado en `record.py`): 1 failed (`test_409_invalid_supersedes_...`, IntegrityError); se restauró el archivo.

### Verde
- Sin cambios en `src`. Pruebas: `test_correct_service.py` (5) y `test_correct_concurrency.py` (2: dos coaches a la vez con dos conexiones; 23505 de `uq_wod_results_supersedes` aislado apagando antes el vigente).

### Evidencia
- Gate `slice-gate.sh results <3 archivos>`: 907 passed en 136 s, exit 0 (sello escrito).

## S8-B3 · Resultados en el quiosco (S8-D14 parcial, S8-D15, S8-D31, M-1, L-5) · migración 0038

### Rojo
- Con `session_attendance` en stub (`NotImplementedError`), ruta y esquemas cableados y sin migración ni cambios en auth/security/record: 20 failed y 40 passed de 60 pruebas (5 de asistencia por el stub; 5 de `test_kiosk_record` por no haber origen quiosco ni ventana; 3 de `test_kiosk_results_path` por el patrón; 6 de `test_0038` por la revisión inexistente; 1 de `test_kiosk_routes` por la lista de 10).
- Honestidad: `test_ventana_hoy_o_ayer[19/22]`, `test_corregir_resultado_de_escritorio/otra_sesion_403` y `test_ruta_con_otro_sufijo_422` pasaban en rojo por el motivo equivocado (la lista blanca daba 403 `kiosk_mode` a `PUT /results`; el patrón ya rechazaba otros sufijos). Tras el verde son reales (las de 403 ahora prueban la regla de S8-D31 con un `PUT /results` permitido).

### Verde
- `0038_kiosk_results_path` (DROP + ADD del CHECK conservando `ck_refresh_tokens_kiosk_path_shape`; `downgrade` reescribe `/resultados` a `/checkin`), `auth/models.py`, `auth/schemas.KIOSK_PATH_PATTERN`, `core/security.KIOSK_ALLOWED_ROUTES` (12), `results/attendance.py` (`GET /class-sessions/{session_id}/attendance`, paginada en memoria sobre los asistentes vivos, un solo SELECT de vigentes), `results/router.py` (`source = kiosk` con la marca), `results/record.py` (quiosco: `session_id` obligatorio, ventana de `classes.ensure_kiosk_session`, `supersedes_id` solo de un resultado `kiosk` de la misma sesión, si no 403 `kiosk_mode`).
- Desviación: el «detalle `kiosk: true` en la auditoría» se cumple con `after.source = 'kiosk'` (la auditoría guarda la fila completa; `audit_log` no tiene columna `details`). `auth/kiosk.py` no cambió de lógica (`_session_id_of` ya sirve a las dos rutas). L-7 de la revisión de B1 (docstring 30/min) quedó alineado a 60 en `router.py`.
- P-CAT: `CON_LIMITE` (+`GET /class-sessions/{session_id}/attendance`), `test_kiosk_routes` (12 rutas y ventana), P-API: `openapi.json` idéntico en dos corridas, `types.ts` regenerado, contract 6 passed, `tsc --noEmit` limpio.

### Evidencia
- Gate `slice-gate.sh results <11 archivos>`: 1 240 passed en 183 s, exit 0; `ruff check`, `ruff format`, `mypy src` (270) limpios; `alembic heads` = `0038_kiosk_results_path (head)`.

### Pendiente (el api de desarrollo está roto; no se tocaron contenedores ni banderas)
- P-MIG de `0038` en `apex-db-1`: volcado `sprint-08-antes-0038.dump` (`$DC exec -T db pg_dump -U apex -Fc apex`), `$DC start api`, `alembic current` = `0038_kiosk_results_path (head)`, `downgrade -1` + `upgrade head`, `\d auth.refresh_tokens` (el CHECK con `(checkin|resultados)`). Misma tanda pendiente que `0036` y `0037`.
- Smoke con rol: login del admin de desarrollo, `POST /auth/kiosk` con `/clases/<id>/resultados`, `GET /class-sessions/<id>/attendance` y un `PUT /results` en quiosco (solo códigos HTTP).

## S8-B1d · Correcciones de la revisión de B1 (M-1 a M-3, L-4 a L-9; S8-D46) · migración 0039

### Rojo (medido por punto)
- M-2/M-3 (`test_locked_by_results.py`, 7 pruebas): 5 failed y 2 passed (las dos que no deben bloquear): quitar asistencia y cancelar con resultado daban 204/200 en vez de 409 `locked_by_results`; corregir sin `session_id` no daba 422; registrar contra quitar y contra cancelar: `DID NOT RAISE` tras esperar.
- M-1 y L-4: son pruebas reescritas sobre código correcto (0 failed, 5 passed). Rojo por mutación: sin `lock_member` en `record.py`, `test_doble_registro_simultaneo_uno_409` falla (1 failed); sin `FOR SHARE` en `session_for_result`, `test_reasignar_wod_y_registrar_a_la_vez...` falla (1 failed). Archivos restaurados.
- L-5: aserción exacta `(P0001, None)` (antes `{GUARDA, 23514}`); ya pasaba, ahora no admite que falte la guarda. Sin rojo posible sin quitar la guarda de la migración.
- L-6: el detector viejo no veía `from app.core import crypto`, `importlib.import_module` ni `__import__` (3 de 3 sin hallazgo, medido contra la versión del HEAD); la prueba de ejecución (`reveal` prohibido, `crypto_ops` sin filas nuevas) pasa.
- L-7: docstring ya alineado a 60 en B3.
- L-8: 4 failed (`test_privilegios_de_tabla_y_columna_exactos[apex_api-results.wod_results]` y tres `UPDATE` de `status`, `validated_by`, `validated_at` que el api aún podía).
- L-9: `test_0039` 1 failed y 3 errors (revisión inexistente); `test_scaled_refs_lock.py` 1 failed y 2 passed (quitar un movimiento citado por `scaled_movement_ids` pasaba).

### Verde
- `classes/results_port.py` (puerto con `member_has_current_result_in_session`, sin ciclo con `attendance.py`), `LockedByResults(field=None)`, `remove_attendance` (`_ensure_no_result`) y `cancel_session`; `results/record.py` (misma `session_id` en la corrección, 422 `field = "session_id"`; la regla de quiosco va antes), `results/service.py`; `wods/probe.py` + `programming.update_wod` (422 `locked_by_results`, `field = "movements"`); `infra/db/grants.sql` (`UPDATE (is_current, updated_at)`); migración `0039_results_updated_guard` (`CREATE OR REPLACE` de la guarda, `downgrade` repone el cuerpo de `0037`); `DELETE /attendance` documenta 409.
- Corrección propia: el gate encontró `remove_attendance` con más de 50 líneas (`test_ninguna_funcion_supera_50_lineas`); se extrajo `_ensure_no_result`.
- No se tocó la cancelación masiva `cancel_future_sessions` (sesiones futuras: sin resultados posibles por ventana de quiosco y WOD futuro).

### Evidencia
- Gate `slice-gate.sh results <results, classes, wods, migrations completos + 5 de auth/core>`: 2 713 passed en 460 s, exit 0; `ruff`, `mypy src` (271) limpios. P-API: `openapi.json` idéntico en dos corridas (+10 líneas), `types.ts` regenerado, contract 6 passed, `tsc` limpio.

### Pendiente en desarrollo (api roto; nada tocado)
- P-MIG de `0038` y `0039` (y las de `0036`/`0037`): volcado previo, `$DC start api`, `alembic current` = `0039_results_updated_guard (head)`, `downgrade -1`/`upgrade head`, `\df+ results.guard_wod_results_update` y `tgenabled = 'A'`.
- P-ROL: `grants.sql` cambió (L-8): el `dbsetup` debe volver a correr sobre `apex-db-1` (`\dp results.wod_results`: solo `UPDATE (is_current, updated_at)`).
- Smoke con rol (admin de desarrollo): `POST /auth/kiosk` con `/clases/<id>/resultados`, `GET /class-sessions/<id>/attendance`, `PUT /results` en quiosco y su corrección, y `DELETE /attendance/<id>` de un socio con resultado (espera 409).

## S8-B4 · Leaderboard y lecturas (US-171 a US-173, S8-D13, S8-D14, L-6) · sin migración

### Rojo
- Con `leaderboard.py` y `reads.py` en stub (`NotImplementedError`), ruta, esquemas y P-CAT cableados: 32 failed y 128 passed de las pruebas nuevas y los tres archivos de arquitectura. 31 por `NotImplementedError` (9 puras, 10 de `test_leaderboard_service`, 4 de `test_wod_results`, 7 de `test_member_results`) y `test_cada_arista_permitida_existe` (la arista `results -> auth` aún no existía en el código). `test_baja_visible` falló por un `AttributeError` de la propia prueba (`reloj.now`; el reloj es `now_utc`), corregido.
- Pasaban en rojo por no depender del stub: `test_tope_por_defecto_es_mil`.

### Verde
- `results/leaderboard.py` (puro: `Mark`, `leaderboard_order`, `rank_rows`; grupo rx+rx_plus / scaled, `time` con terminados antes que `capped`, posición de competencia sobre la lista completa, desempate por apellido, nombre sin tildes e id), `results/reads.py` (`leaderboard`, `wod_results`, `member_results`; `LEADERBOARD_MAX_ROWS = 1.000` con 422 `leaderboard_too_large`; una llamada a `members.service.names_for` y una a `auth.service.user_names_for`), `wods.service.titles_for`, tres rutas `staff-read` y `no-store` en `results/router.py`, `LeaderboardRow`/`WodResultRow`/`MemberResultRow`, `LeaderboardTooLarge`. P-CAT: `CON_LIMITE` (+3), `test_service_import_graph` (`results -> auth`), `RUTAS_SIN_Q_S8` en `test_list_routes_use_page_params` (las tres listas paginan sin `q`: filtran por parámetros tipados).
- [DECISIÓN DE DISEÑO] `last_initial` es la letra mayúscula del apellido sin punto (el front agrega «.»). La posición sigue la lista completa: el primer escalado va después del último RX; solo empatan filas del mismo grupo con la misma marca. El tope de 1.000 se aplica a los resultados vigentes y validados del WOD (antes del filtro de sexo, que cruza esquemas): nunca trunca.
- Índices: ya existen `ix_wod_results_leaderboard (wod_id, status) WHERE is_current` e `ix_wod_results_member_date (member_id, wod_date DESC) WHERE is_current` (0036); no hace falta migración.
- Corrección propia: el gate encontró `leaderboard` con más de 50 líneas; se extrajo `_marks`.

### Evidencia
- Prueba `perf` (`test_leaderboard_perf.py`, con `ANALYZE results.wod_results` tras sembrar): 60 resultados 3,9 ms y 400 resultados 10,3 ms (tope 300 ms), 2 passed. `EXPLAIN (ANALYZE, BUFFERS)`: `Seq Scan` de 0,04 y 0,24 ms (la tabla es tan pequeña que el planificador no usa el índice; en V6 se repite con la base de desarrollo).
- Gate `slice-gate.sh results <8 archivos>`: 904 passed en 147 s, exit 0 (segundo intento: el primero falló `test_ninguna_funcion_supera_50_lineas`). `ruff`, `mypy src` limpios. P-API: `openapi.json` idéntico en dos corridas, `types.ts` regenerado, contract 6 passed, `tsc` limpio. Checkpoint `cd9e756`.

### Pendiente
- Smoke con rol (api de desarrollo roto): login del admin de desarrollo y GET de `/wods/<id>/leaderboard`, `/wods/<id>/results` y `/members/<id>/results` (solo códigos HTTP), junto con la tanda de B3.

## S8-B3b · Anulación de resultados por admin y correcciones de la revisión de B3 (M-1, L-1 a L-4; S8-D46 b) · migración 0040

### Rojo (medido)
- `test_void_result.py`, `test_void_concurrency.py` y `test_0040_results_void.py` con `void_result` en stub y sin revisión 0040: 14 failed y 15 errors (los 15 de `test_0040`: «no existe la revisión»; los 14: 11 de `test_void_result` por `NotImplementedError`, 2 de concurrencia y `test_cuelga_de_0039`), 19 passed. Pasaban en rojo por motivos ajenos al stub: la validación de `VoidIn`, los 403 de coach/member y de quiosco (`AdminDep` y la lista blanca ya los dan), y L-2/L-3 (código ya correcto).
- L-2 y L-3 por mutación: sin `ensure_kiosk_session` en `attendance.py`, `test_asistencia_en_quiosco_solo_de_hoy_o_ayer` falla (1 failed); sin `lock_member` en `record.py`, `test_dos_coaches_a_la_vez_uno_gana_otro_409` (reescrita con `Pausa`: la segunda espera, `not done()`, y luego 409) falla (1 failed). Archivos restaurados (`git diff` vacío).
- Lección: una prueba de dos conexiones bajo `bus_listo` (savepoint) y no `bus_confirmado` deja la sesión en un candado y cuelga; los tests de concurrencia van en un archivo con `bus_confirmado` (`test_void_concurrency.py`). Un fallo a medias con la tarea pausada también cuelga el cierre: `finally` libera `pausa.seguir`.

### Verde
- `0040_results_void` (columnas `voided_by|voided_at|void_reason`; CHECK `status` de tres estados, `validated_pair` para `validated` y `voided`, `voided_shape`, `void_reason_length`, `voided_not_current`; `CREATE OR REPLACE` de `guard_wod_results_update` (`validated -> voided` solo de una fila vigente que se apaga, campos de NULL a valor, anulado terminal), `guard_wod_results_insert` (no nace anulado) y `require_successor` (el anulado no exige sucesor); downgrade aborta con filas anuladas), `results/void.py` (candado de socio y luego `FOR UPDATE`; 404/409), `POST /results/{id}/void` (`AdminDep`, `admin-write`, `VoidIn` 1-200 sin controles), `WodResultVoided` (sin motivo), modelo y `ResultOut` con los tres campos, `infra/db/grants.sql` (`UPDATE (is_current, status, voided_by, voided_at, void_reason, updated_at)`), `docs/operacion/wods.md` (procedimiento), S8-D46 completa en DECISIONES y L-1/L-4 alineados (S8-D15: `downgrade` de 0038 reescribe; S8-D31: `after.source = kiosk`; L-4 aceptado).
- Pruebas ajustadas por el cambio de esquema: `COLUMNAS` de `test_0036`, matriz de grants (`status` ya no es denegado) y `CAMPOS` de `test_router_record`. Corregido un flake previo de B2: `test_dos_filas_de_auditoria_insert_y_update` ordenaba la auditoría por `id` (uuid); ahora por `seq`.
- El leaderboard de B4 ya excluye anulados (`status = 'validated'` e `is_current`), con prueba (`test_leaderboard_ficha_y_resultados_excluyen_al_anulado`); la TV (C2) usará la misma condición.
- [DECISIÓN DE DISEÑO] Solo se anula un resultado vigente y `validated`: uno ya corregido o `pending` da 409 `result_not_voidable` (un `pending` se rechaza en EP-25); así `validated_pair` no necesita un caso de anulación sin validación.

### Evidencia
- Gate `slice-gate.sh results <results, migrations, architecture completos + test_kiosk_results_path + test_migrations>`: 2 194 passed en 305 s, exit 0 (antes, una corrida de 2 745 con classes y wods: 2 742 passed y 3 failed por el flake de auditoría y `CAMPOS`, corregidos). `ruff` y `mypy src` (274) limpios. P-API: `openapi.json` idéntico en dos corridas, `types.ts` regenerado, contract 6 passed, `tsc` limpio. Checkpoint `9bc8e96`.

### Pendiente en desarrollo (api roto; nada tocado, sin banderas)
- P-MIG de `0040` (con `0036` a `0039` y las anteriores): volcado `sprint-08-antes-0040.dump`, `$DC start api`, `alembic current` = `0040_results_void (head)`, `downgrade -1` y `upgrade head`, `\d results.wod_results` (columnas y CHECK), `\df+ results.guard_wod_results_update` y `tgenabled = 'A'` de los cinco triggers.
- P-ROL: `grants.sql` cambió otra vez: el `dbsetup` debe volver a correr (`\dp results.wod_results`: `UPDATE (is_current, status, voided_by, voided_at, void_reason, updated_at)`).
- Smoke con rol: `POST /results/<id>/void` con el admin (200 y 409 al repetir) y con el coach (403), sobre un resultado ficticio propio del smoke.

## S8-B5 · Tablero e Inicio, api y web juntos (US-174, S8-D16, S8-D25, C4) · sin migración

### Rojo (medido)
- Con el esquema `WodTodayOut` ya declarado pero sin llenar y `today_sessions` sin reordenar: api 5 failed (3 de `test_wod_today` porque `wod_today` sale `null`; 2 de `test_today_sessions_order`) y 1 passed (`test_null_sin_wod`, correcto por construcción). `test_solo_cambia_wod_today` falló al principio por una expectativa mía (`title` ausente con `$ref`); corregida.
- Web (`FutureKpis.tsx` y `schemas.ts` en su versión anterior, pruebas nuevas): 6 failed (`FutureKpis` con valor, `schemas.test` de `wod_today`, y cuatro de `ClassesKpis`: tres filas y el plegado «N canceladas») y 28 passed.

### Verde
- api: `dashboard/schemas.py` (`WodTodayOut`, `extra=forbid`), `dashboard/service.py` (`wods.service.today_card` -> `WodTodayOut`), `classes/queries.today_sessions` con `ORDER BY (status = 'cancelled'), starts_at, id`, arista `(dashboard, wods)` en `test_service_import_graph`. P-API: `docs/openapi.json` idéntico en dos corridas, `types.ts` regenerado, contract 6 passed, `tsc` limpio.
- web: `schemas.ts` (`wodTodaySchema` estricto), `FutureKpis` (muestra el título), `ClassesKpis` (vivas en la lista y botón plegable «1 cancelada»/«N canceladas»), `test/dashboard.tsx`.
- [DECISIÓN DE DISEÑO] «N canceladas» en singular con 1 («1 cancelada»). La tarjeta completa «WOD de hoy» con Ver/Registrar llega en F5.

### Evidencia
- Gate web `slice-gate.sh web/dashboard <3 pruebas>`: 34 passed, exit 0 (tras corregir 4 errores de eslint propios). `npx vitest src/features/dashboard`: 9 archivos, 97 passed.
- Gate sellante `slice-gate.sh dashboard <4 pruebas + tests/architecture>`: exit 0 (primer intento falló por E501 en docstrings; el segundo por una prueba mía con `time_cap_s` en un WOD de `reps`, corregida; `tests/architecture` completo 874 passed). Checkpoint `bb6e4da`.
- Desviación: en el primer gate lancé dos pytest a la vez por error (un fallo espurio en `tests/architecture`); repetido en solitario, verde.

### Pendiente
- Smoke con rol (api de desarrollo roto): `GET /dashboard` con el admin de desarrollo, solo el código HTTP y la forma de `wod_today`. P-REBUILD 2 y 3 (reiniciar worker y reconstruir `web`) quedan para cuando el usuario repare el api.
