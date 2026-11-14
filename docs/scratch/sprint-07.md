# Sprint 7 · cuaderno (backend y orquestador)

Rama `feat/sprint-07-clases-horario-checkin`, HEAD de partida `8e751eb` (sobre `a2f38ad`, cierre de v0.3.0).

## Planificación

- Impacto: `docs/ddd/blueprints/sprint-07-impacto.md`
- Exploración: `docs/ddd/blueprints/sprint-07-exploracion.md`
- Blueprint: `docs/ddd/blueprints/sprint-07-blueprint.md`
- Diseño de seguridad: `docs/ddd/blueprints/sprint-07-seguridad-diseno.md`
- Plan (aprobado por la orden del usuario del 2026-11-14, S7-D35): `docs/ddd/blueprints/sprint-07-plan.md`
- Críticas del plan: `docs/ddd/blueprints/sprint-07-critica-1.md`, `sprint-07-critica-2.md`

## W0-1 · documentos y decisiones (2026-11-14)

- Decisiones S7-D1 a D35 en `docs/ddd/DECISIONES.md` (bloque «Sprint 7»); migraciones reales `0025` a `0029_memberships_orig_end_date` en `SPRINT-07.md`, `BREAKDOWN.md` y DECISIONES.
- T-DOC en US-154, US-155, US-159, US-160, US-161, US-163 y US-164; `BRECHAS.md` §15; `03_context_map.md` (aristas de S7-D6); `CLAUDE.md` (módulo `classes`, job y CLI de generación, layout `sign/`, 25 cubetas y 24 variables, aristas).
- No hay Rojo ni Verde (documentos).

### Línea base (de `sprint-07-impacto.md` §5)

- Cierre del Sprint 6 (S6-D141, sobre `af23e51`): api 9544 pasan y 100 saltadas; web 3930 de 3930 (2 hilos, 98,37 % de líneas).
- `tests/architecture` en `a2f38ad`: 806 passed en 93,8 s (`db_test` respondió en 5443). Suite completa no corrida (poca memoria); mypy y web se toman del cierre de S6. La línea base completa se toma en W0-4.

### Evidencia

- Gate `bash scripts/workflow/slice-gate.sh architecture`: exit 0, 806 passed en 88,3 s (igual que la línea base; el primer intento sin `TEST_DATABASE_URL` dio 84 errores de entorno, no de documentos).

## W0-2 · migración `0025_s6_hardening` (2026-11-14)

### Consultas previas sobre `apex-db-1` (solo lectura, antes de escribir; api y worker parados)

- `fk_attachments_key_id` (adjuntos con `key_id` sin llave): 0
- `sign_iff_public_key` (`(purpose='sign') <> (public_key IS NOT NULL)`): 0
- `photo_not_sensitive` (foto sensible): 0
- `alembic_version` previa: `0024_crypto_rotation_from_api`. Volcado: `docs/scratch/sprint-07-antes-0025.dump` (2,1 MB, ignorado por git).

### Rojo

- `tests/migrations/test_0025_s6_hardening.py` (nueva), `tests/crypto/test_rotation_no_key_update_lock.py` (nueva), `test_0024` (cadena de head) y `tests/core/test_migrations.py` (ids <= 32).
- Rojo confirmado: 15 failed + 5 errors de 33 (28 sin contar los 5 errores de fixtures) por motivo único: no existía la revisión `0025_s6_hardening` (sin FK, sin CHECK `sign_iff_public_key`/`photo_not_sensitive`, guardas de 0024). Pasaron en rojo los dos de forma (id corto de revisiones y cadena de 0024) porque no dependen de la migración.

### Verde

- `migrations/versions/0025_s6_hardening.py`: consultas previas que abortan con regla y conteo, `SET LOCAL lock_timeout = '5s'`, FK `NOT VALID`+`VALIDATE`, dos CHECK, `guard_keys_update` (regla de `public_key` tras DELETE/TRUNCATE y AFTER) y `guard_jobs_update` (solo `rotate`); `downgrade` con los cuerpos de 0024 como constantes.
- `core/crypto/service.py`: `FOR NO KEY UPDATE` (`with_for_update(key_share=True)`) en `start_rotation`, `finish_rotation` y `_lock_key`. [DECISIÓN DE DISEÑO] `count_rows_by_key` conserva `FOR UPDATE` a propósito: el conteo previo a `retire-key` debe impedir subidas nuevas con esa llave (el `KEY SHARE` de la FK choca con `FOR UPDATE`).
- Modelos: CHECK `sign_iff_public_key` y `photo_not_sensitive` (sin FK, E2). Docstring de `0023`. RUNBOOK §12: consultas previas con su remedio (L-6).
- Regresiones por la FK/CHECK nuevos corregidas en pruebas heredadas (la FK exige llave real): `tests/attachments/_apoyo.py` (`llave_retirada`), `test_attachments_check.py`, `test_init_keys_data_class.py` (nombre y forma del CHECK), `test_0021`, `test_0022`, `test_0023` (llaves reales, FK esperada). Tras corregir: 5.232 passed en la corrida de attachments/cli/crypto/members/core/audit/migrations (11 fallos previos, todos por esto).

### Evidencia

- Gate no sellante `slice-gate.sh crypto tests/crypto/test_rotation_no_key_update_lock.py tests/crypto/test_rotate.py`: exit 0, 841 passed.
- Sello `slice-gate.sh attachments` con las cinco pruebas del plan: exit 0, 1.195 passed.
- P-MIG: `$DC start api` -> healthy, `alembic current` = `0025_s6_hardening (head)`; `$DC start worker` healthy; `downgrade -1` y `upgrade head` sin error, `current` = 0025 (head). `/health`: status ok, migrations ok, crypto ok.
- Esquema en `apex-db-1`: FK `fk_attachments_key_id` validada, `ON DELETE RESTRICT`; `ck_crypto_keys_sign_iff_public_key` y `ck_attachments_photo_not_sensitive` validados; `ck_crypto_keys_sign_public_key` ya no existe. Todos los triggers de `crypto_keys`, `crypto_jobs` y `attachments` con `tgenabled = A` (10 filas).

## W0-3 · volumen `keys` con `sign/` y el api sin la llave de firma (2026-11-14)

### Rojo

- Nuevas: `tests/crypto/test_local_provider_without_signing.py` (5), `tests/core/test_missing_secrets_signing.py` (2), `tests/core/test_settings_signing_path.py` (6), `tests/core/test_signing_key_exposure.py` (6), `tests/cli/test_keys_layout_sign.py` (12), `tests/architecture/test_api_never_loads_signing_key.py` (4); `test_env_example.py::test_firma_sin_linea_documentada_en_comentario`; en Bash `test_compose_config.sh`, `test_deploy_script.sh` (cuatro casos de firma y el de `deploy.sh` de v0.3.0), `test_check_key_files.sh`, `test_env_isolation.sh`.
- Honestidad del Rojo: el agente escribió las pruebas primero pero el código quedó antes de la primera corrida de esa tanda; el rojo no se midió por separado (la corrida inicial ya mezcló pruebas y Verde). Lo que sí falló antes de ajustar fixtures fue: 15 de `tests/core` + `tests/crypto` y 40 de `tests/cli` por la ruta de firma nueva (`sign/`), la firma de `get_provider_named(..., with_signing=)` en falsos de prueba y rutas planas en `.env` de prueba.

### Verde

- `core/crypto/local_provider.py` (`signing_key_path: Path | None`, `sign_unavailable`), `provider.py`, `recovery.py` (`with_signing=False` por omisión), `sign_rotation.py` (`switch_provider(..., with_signing=)`, solo el CLI pasa `True`), `errors.py`, `core/config.py` + `config_signing.py` (ruta por omisión `sign/`, validador S7-D23 (1), vacía = error) y `config_ops.py` (extraído para no pasar de 800 líneas), `core/crypto/exposure.py` + `main.py` (`signing_key_exposed`, el arranque falla sin ruta ni contenido), `worker/runtime.py`, `worker/jobs/sign_audit.py`, `cli_base.py`, `cli_ops/rotate_key.py` (`True`), `cli_ops/keys.py` (`key_paths_in` -> `sign/`), `cli_ops/keys_layout.py` (`sign/`, desde `custody/` o plano, `reverse_layout`), `cli.py` (`--reverse`).
- Compose: api con subpaths `custody` y `jwt` (también en `compose.openbao.yml`), worker `custody` y `sign`, tools entero; `compose.dev.yml` no los redefine. `.env.example` solo comenta la ruta. `deploy.sh` (aborta con 2 si la línea está vacía o fuera de `sign/`), `check-key-files.sh` (`--only api`), `prod-smoke.sh` (ausencia en el api, `--reverse`, `sign_audit` del worker), `test_env_isolation.sh`.
- Docs: ADR-006 (párrafo autorizado, S7-D28), adenda a S6-D142 en DECISIONES, RUNBOOK §12 (layout y rollback paso a paso), `actualizar.md` paso 6, `infra/README.md`, `llaves.md`.
- Residuo de W0-2 corregido de paso: `tests/migrations/test_0023_attachments.py::_sql_llave` insertaba llaves `encrypt` de relleno que quedaban en la base de roles y hacían fallar `test_api_role_paths` (`unwrap_failed`) al correr juntas; ahora son llaves `sign` con su pública (no cuentan para `ensure_keys`).

### Evidencia

- Suite del api completa en dos tandas: 6.821 passed (resto) y 2.787 passed (cli, core, crypto), 0 fallos tras corregir el residuo de `test_0023`; `mypy src` y `ruff` limpios.
- Docker (desarrollo): `$DC stop api worker` antes de escribir código; `.env` sin la línea de firma (borrada por patrón, sin imprimir); buildx del api; antes: `custody/` con `kek.bin` y `sign-ed25519.key`; `init-keys --migrate-layout` 1.ª «movido sign-ed25519.key», 2.ª «nada que migrar»; después: `custody/kek.bin`, `sign/sign-ed25519.key`, `jwt/` (modos 600/700 conservados). `up -d --no-build --force-recreate api worker`: api healthy. Ausencia en el api: `ls /run/apex/keys` = `custody jwt`; `test ! -e` de `sign`, `custody/sign-ed25519.key` y `sign-ed25519.key` plano, los tres rc 0. El worker ve `custody` y `sign`. `--run-once sign_audit`: `result: ok`. `/health` 8181: status ok, db ok, migrations ok, crypto ok.
- `test_env_isolation.sh` contra desarrollo: la parte de llaves 0 fallas (api no ve sign/ ni la llave; worker ve sign/ y no jwt/); 11 fallas de la parte de variables (el `.env` de desarrollo es la suma de `.env` y `.env.ops`: contraseñas y `BACKUP_*` en api y worker), que ese script solo prueba bien contra ensayo/smoke (así quedó anotado en S6).
- Bash: `test_compose_config.sh` 0 fallas, `test_deploy_script.sh` 497 ok / 0 fallas, `test_check_key_files.sh` 0 fallas.

### Gates y smokes de W0-3

- Gates: `crypto` (827 passed), `core/config` (1.095), `cli` layout (839, 4 skipped), `cli` init-keys y rotate-sign (verde), `crypto` init-keys (815, 1 skipped), `test_compose_config.sh`, `test_deploy_script.sh` (497 ok) y `test_check_key_files.sh` con 0 fallas; sello `slice-gate.sh main ...` exit 0 (826 passed). Checkpoint `0d65e8b`.
- `prod-smoke.sh` (`SMOKE_DOWN=1 SMOKE_WEB_PORT=8380`, auxiliar `docker:cli` con el árbol de `0d65e8b` en el volumen `apex-b4-work`, imagen api `4ba399a5fbf8`): `--no-build` EXIT=0, 233 ok, 0 FALLA; `--no-build --provider openbao` EXIT=0, 252 ok, 0 FALLA. Ambos comprueban api con custody+jwt sin `sign/`, worker (local) con custody+sign sin jwt, `--migrate-layout` plano -> nuevo, segunda corrida, `--reverse` y de vuelta, `init-keys --data-class audit.signature` y `sign_audit` ok del worker; `test_env_isolation` 0 fallas. Sin `apex-smoke` residual.
- Incidente de proceso: un `TaskStop` no mató los hijos de un script de gates y dos tandas corrieron a la vez sobre `db_test` (8 fallos espurios); se mataron ambas y se repitió una sola, limpia.

## Revisión W0-1/W0-2 (S7-W0-2b, 2026-11-14)

Seis hallazgos de la revisión (0 CRITICAL, 0 HIGH, 2 MEDIUM, 4 LOW).

- M1 `CLAUDE.md`: `generate_sessions` (jobs, `cli_ops`, `cli.py`) marcado «desde S7-B1»; lo de W0-3 (api solo con `custody/` y `jwt/`, `signing_key_exposed`, `--reverse`) ya existe y queda en presente.
- M2 prueba nueva `test_count_rows_by_key_espera_una_subida_de_adjunto_sin_confirmar` (otra conexión deja sin confirmar un `INSERT` en `attachments.attachments` con `key_id` = v1; el recuento vence con `DatabaseBusy`). Con `FOR UPDATE`: 1 passed. Mutación temporal de `count_rows_by_key` a `with_for_update(key_share=True)`: 1 FAILED (no espera); revertida (`git diff src/` vacío).
- L3 `test_0025_s6_hardening.py`: `assert "violan 1 fila" in mensaje`.
- L4 residual de `finish_rotation` documentado: DECISIONES S7-D36 y `docs/operacion/llaves.md`.
- L5 docstring de `0023_attachments.py` revertido al de `6481d43^` (la explicación queda en el docstring de `0025`).
- L6 `tests/conftest.py`: `LIMPIAR_LLAVES_DE_ADJUNTO` (borra `prueba.adjunto` con triggers apagados y rearmados en ALWAYS) dentro de `limpiar_tras_dos_sesiones`, tras los adjuntos.
- `test_env_isolation.sh` (11 fallas de variables contra desarrollo): NO es defecto del Sprint 7. `sprint-05.md` (gates, línea base): «11 fallas, las mismas 11 de la línea base (parte dinámica sobre un `.env` de desarrollo, suma de los dos ejemplos)»; `sprint-06.md` solo lo corre vivo contra el ensayo (0 fallas). Script sin cambios.

## Revisión W0-3 (S7-W0-3b, 2026-11-14)

Siete hallazgos de seguridad (0 CRITICAL, 0 HIGH, 3 MEDIUM, 4 LOW). Rojo primero en todos.

### Rojo
- Python: 9 fallas nuevas sobre el código de W0-3 (`test_signing_key_exposure` 3, `test_settings_signing_path` 3, `test_keys_layout_sign` 2, arquitectura 1 por la lista de lectores). Los 3 casos con enlaces simbólicos se saltan en Windows: se probaron en Linux (`python:3.12-alpine`, módulos viejos de `HEAD` vs nuevos): viejo = enlace `sign` no expuesto, carpeta ilegible `False`, `sign/` enlace movió la llave a `fuera/`, `sign/` en 755; nuevo = `True`, `OSError`, conflicto sin mover nada, 700.
- `test_deploy_script.sh`: 6 FALLA (`..` y relativa, 3 asserts cada una) antes de tocar `deploy.sh`.

### Verde
- M-1 `core/crypto/exposure.py`: `os.walk(..., followlinks=False, onerror=<relanzar>)`, un enlace `sign` o una carpeta `sign-ed25519.key` cuentan; `main._forbid_exposed_signing_key` convierte `OSError` en `StartupError("signing_key_exposure_unverifiable")`.
- M-2 `core/config_signing.py`: forma MÍNIMA, no la estricta. Rechaza vacía, relativa, con `..`, y SIEMPRE `/run/apex/keys/custody` y `/jwt` (con KEK `None`/OpenBao también) más la carpeta de `JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH` y KEK. Motivo de no usar la estricta («solo bajo `/run/apex/keys/sign/`»): las fixtures de pruebas y del CLI usan rutas `tmp_path` para la semilla (~20 sitios) y las rompería; la estricta para producción ya la hace `deploy.sh`.
- M-3 `tests/architecture/test_api_never_loads_signing_key.py` reescrito: cualquier valor distinto de `False` (o del reenvío del mismo parámetro) y todo `**` hacia funciones con flag; prueba del propio detector; cierre de `main.py` con `importlib` (también el f-string de módulos) sin alcanzar `cli*` ni `worker/`; `core/` y `modules/` nunca importan `app.cli*`; `LocalFileProvider(` solo en `provider.py`; `DEFAULT_SIGNING_KEY_PATH` solo en `config*`; lectores por Attribute/Name/keyword/string; valores por omisión revisados en todo `src/app` (incluye `switch_provider`).
- L-1 `cli_ops/keys_layout.py`: `os.link` + `os.unlink` (falla con `FileExistsError` en vez de pisar), subcarpetas enlace = conflicto, `chmod 700` al crear y al reponer; `reverse_layout` igual.
- L-2 `missing_secrets`: solo se corrigió el docstring (nadie pasa `signing_key=True`; worker y tools fallan al abrir el proveedor con `with_signing=True`). Sin cambio de comportamiento, por eso sin rojo.
- L-3 `infra/deploy.sh`: la ruta debe ser absoluta, sin `..`, y bajo `sign/`; 2 casos nuevos en `test_deploy_script.sh`.
- L-4 documentos: ADR-006 (líneas 41 y 70, solo la ruta), RUNBOOK §residuales (1151 cerrado en v0.4, 1152 ruta; el §12 de rollback conserva `custody/` a propósito), `llaves.md`, `openbao.md`, `rotar-llave.md`.

### Evidencia
- `$DC restart api`: `/health` 8181 `status ok`, `migrations ok`, `crypto ok`; `ls /run/apex/keys` en el api = `custody jwt`.
- `slice-gate.sh main` (4 archivos): 850 passed, 3 skipped (enlaces y modo POSIX en NTFS). `ruff` y `mypy src` limpios.
- `bash scripts/ci/test_deploy_script.sh`: 0 fallas, 503 ok, EXIT=0 (tarda más de 9 minutos: correrlo sin `timeout` corto; con 560 s salió 124 en el rojo).
- Suites ampliadas por el cambio del validador (rutas `tmp_path` de la semilla): `tests/core tests/crypto tests/architecture` 2.985 passed, 65 skipped; `tests/cli` 628 passed, 33 skipped.

## S7-W0-4 · Línea base, cubetas y gates del entorno (2026-11-14, HEAD 4297a26)

### Línea base (antes del Verde)
- `tests/architecture`: 814 passed, 0 skipped, 0 failed (93 s).
- Suite completa del api (un solo pytest, `-m "not perf"`): 9.624 passed, 103 skipped, 1 failed, 38 deselected (24 min 34 s). Skips: 34 `cmd.exe` no arranca con `env={}` (age falso, corre en CI/Linux), 23 OpenBao real (contenedor Linux), 8 + 2 + 2 enlaces simbólicos sin privilegios, 6 NTFS sin modo POSIX, 5 age real y pty solo en Linux, 3 `mkfifo`, 2 solo proveedor local. El fallo: `tests/notifications/test_sending.py::test_dos_pasadas_en_paralelo_no_envian_el_mismo_aviso_dos_veces` (`3 + 2 == 4`, una pasada con `pendientes=1`): carrera entre las dos pasadas bajo la carga de la suite; el archivo entero, dos veces aislado, da 43 passed. Intermitente de la línea base, ajeno a W0-4.
- `uv run mypy src`: 227 archivos, sin errores.
- Vitest (`npm test -- --run --pool=forks --maxWorkers=2`): 212 archivos, 3.930 passed, 0 skipped, 0 failed.

### Rojo
- 13 fallas pytest (`test_ratelimit` 4: catálogo del plan, `user_limits_from` x2 y `test_hay_25_cubetas`; `test_user_limits_catalog` 3; `test_env_example` 5 incluido `test_24_variables_user` y los dos renombres; `test_config::test_limites_de_clases_y_asistencia` AttributeError) y 4 FALLA de shell (`test_vitest_recibe_max_workers_2` y `VITEST_MAX_WORKERS=3` en `test_slice_gate.sh` y `test_run_gates.sh`). Motivo: el catálogo tenía 23 cubetas y 22 variables y los gates no pasaban `--maxWorkers`.
- `test_no_cross_schema_sql`: `ESQUEMAS` suma `classes`; `test_hay_modulos_que_revisar` excluye `MODULOS_PENDIENTES={"classes"}` hasta A2 (el módulo aún no existe). `CLAVES_SIN_RUTA_TODAVIA` = las dos cubetas nuevas hasta B2/C3.

### Verde
- `ratelimit.py`: `classes-write` (30/min) y `attendance-write` (60/min); `config.py` (`USER_CLASSES_WRITE_LIMIT_PER_MIN`, `USER_ATTENDANCE_WRITE_LIMIT_PER_MIN`, `gt=0`; se compactaron dos comentarios para quedar en 800 líneas, límite de `test_file_and_function_size`); `.env.example` (25 cubetas, 24 variables); `compose.yml` (api); `ci.yml` (dos `-e`, regex y conteo 24); `slice-gate.sh` y `run-gates.sh` con `--maxWorkers="${VITEST_MAX_WORKERS:-2}"`.

### Evidencia
- `bash scripts/workflow/tests/run.sh`: 6 de 6 archivos en verde (36 ok en `test_run_gates`).
- `slice-gate.sh architecture test_user_limits_catalog test_no_cross_schema_sql`: 815 passed, exit 0.
- Sello `slice-gate.sh core/ratelimit test_ratelimit test_config test_env_example`: 1.140 passed, exit 0.
