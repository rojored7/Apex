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
