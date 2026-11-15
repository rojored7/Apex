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

## S7-A1 · Horas y clases en Configuración (US-154, S7-D8)

### Rojo
- Stubs (`HoursSettings`/`ClassesSettings` vacías, `service.classes` con `NotImplementedError`, secciones sin habilitar): 3 archivos nuevos, 33 failed y 8 passed (los 8 son los 403 de coach y socio, que llegan antes del 404). Motivo: `section_not_available` 404 y `KeyError` de `SECTION_REGISTRY`.

### Verde
- `settings/schemas.py`: `TimeRange`, `HoursSettings` (siete días, 0 a 2 rangos, `open < close`, ordenados y sin solaparse, validado por día para que el `field` sea `value.<día>`), `ClassesSettings` (`StrictInt`, 1 a 100 y 0 a 240, sin `allow_over_capacity`), habilitadas en `ENABLED_SECTIONS`, `SECTION_REGISTRY`, `SECTION_VIEWS` (hereda) y `SECTION_DEFAULTS`; salidas y entradas tipadas.
- `settings/service.py`: `classes(session)` (tolerante a lo guardado). `settings/router.py`: cuatro rutas tipadas (`admin`, `admin-write` en los PATCH).
- Pruebas ajustadas: `NO_HABILITADAS = ("tv",)`, `test_settings_rules` (siete habilitadas), catálogos `CON_LIMITE` y `test_writes_have_user_limit` suman los dos PATCH.
- P-API: `docs/openapi.json` (dos exportaciones idénticas) y `web/src/core/api/types.ts`; `types.contract.test.ts` 6 passed.

### Evidencia
- `slice-gate.sh settings test_hours_section test_classes_section test_router_hours_classes`: 856 passed, exit 0.

## Cierre de la Wave 0 (orquestador, 2026-11-14)

- `run-gates.sh` (tercera corrida, sin otros procesos; los `dian-*` parados por memoria con orden del usuario): RC 0. api 9629 passed, 103 skipped, cobertura 94,72 %; scripts de infraestructura 0 fallas; web 212 archivos, 3930 pruebas, 98,37 % de líneas; build OK. Las dos corridas anteriores: la primera cayó en lint (dos E501, corregidas) y la segunda la mató el sistema por memoria (quedó un pytest huérfano de 1,2 GB que se mató a mano).
- Incidente: con api y worker arriba, el `--reload` del api aplicó a `apex-db-1` la `0026_class_slots` a medio escribir de A2 (riesgo previsto en P-MIG 2). Corregido: `stop api worker` y `alembic downgrade 0025_s6_hardening` (esquema `classes` ausente). Lección: un slice con migración no puede escribir mientras el api de desarrollo corre, aunque espere para las pruebas.
- La reconstrucción de la imagen y el smoke de cierre se hacen en P-MIG 5 de A2 (api y worker quedaron parados para A2).

## S7-A2 · Franjas (US-155, S7-D7, S7-D9, M-3)

### Rojo
- Desvío: el código se escribió durante la espera de W0 (sin stubs previos), así que el rojo con stubs no se pudo confirmar; las pruebas nacieron con el código y la primera corrida dio 67 passed y 1 failed (límite por omisión 25, no 50, error de la prueba). Pruebas nuevas: `tests/classes/{test_validate_slot_pure,test_slots_service,test_router_slots}.py`, `tests/auth/test_is_active_staff.py`, `tests/migrations/test_0026_class_slots.py` y un camino con rol real `apex_api` en `test_api_role_paths.py`.
- La lista de otras pruebas ajustadas (corrida amplia dio 6 fallos de arquitectura por la regla «toda lista acepta `q`» y 3 de migraciones): `GET /class-slots` suma `q` (nombre); `test_audit_module` (MODULES con `classes`), `test_db_apply` (esquema `classes`), `test_0025` (ya no es head), `test_0014` (inventario y triggers), `test_audited_tables`, `test_service_import_graph` (aristas `classes -> auth` y `classes -> settings`), `test_no_cross_schema_sql`, `test_user_limits_catalog`, `test_error_codes_per_route`, `test_db_grants` (23 tablas).

### Verde
- `migrations/versions/0026_class_slots.py`: esquema `classes`, `class_slots` (CHECK de días, duración, cupo y nombre), índice `ix_class_slots_is_active`, triggers `forbid_delete`/`forbid_truncate` `ENABLE ALWAYS` sobre `classes.forbid_mutation()`.
- `modules/classes/{__init__,models,schemas,exceptions,events,rules,slots,service,router}.py`; `auth.service.is_active_staff`; `main.MODULES` (tras `notifications`, antes de `dashboard`); `migrations/env.py`; `audit/queries.py` (`AUDITABLE_TABLES`, excluida de recientes con motivo); `infra/db/grants.sql` (esquema, matriz, clasificada, GRANT api por columna y SELECT worker); `tests/conftest.py` (`LIMPIAR_CLASS_SLOTS` en las dos limpiezas), `tests/factories/{classes,triggers}.py`.
- [DECISIÓN DE DISEÑO] `start_time` es `time` en la base y `str` `HH:MM` en el ORM (`LocalTime`): el serializador canónico de la auditoría (ADR-004) no admite `datetime.time` y no se toca.
- Desvíos del plan: no se genera sesiones al crear la franja (no hay `class_sessions` hasta B1); aristas del grafo solo las usadas (`classes -> members` llega en C1); `PRIVATE_HELPERS["classes"]` = `rules`, `slots`, `events`.
- Incluye en este checkpoint los dos cambios de línea larga pendientes de W0 en `core/config.py` y `tests/conftest.py` (los pidió el orquestador; ruff los exige).
- P-API: `docs/openapi.json` (dos exportaciones idénticas) y `web/src/core/api/types.ts`; `types.contract.test.ts` 6 passed.

### Evidencia
- P-MIG 5: `$DC start api` migró 0025 -> 0026 (`alembic current` = `0026_class_slots (head)`), health `ok` con `migrations: ok`; `$DC start worker`; `ls /run/apex/keys` en el api = `custody jwt` (smoke de cierre de W0). P-MIG 6: `downgrade -1` y `upgrade head` sin error, head otra vez 0026.
- P-MIG 7: `\d classes.class_slots` con 4 CHECK, PK e índice; triggers `class_slots_forbid_delete` y `_forbid_truncate` en `tgenabled = A`; `classes.forbid_mutation()` `SECURITY INVOKER`. `GET /class-slots` sin token da 401.
- `slice-gate.sh auth tests/auth/test_is_active_staff.py` (no sellante): 827 passed, exit 0.
- Sello `slice-gate.sh classes` (puras, service, router, migración, grants, no_cross_models): 1.125 passed, exit 0.
- Incidente repetido: el `--reload` del api aplicó 0026 en `apex-db-1` durante la espera (el orquestador ya lo revirtió).

## S7-A1b · Correcciones de la revisión de A1 (HH:MM, contrato, auditoría)

### Rojo
- 3 failed, 72 passed: `0٥:00` (dígito árabe-índico) validaba en `hours` y en `validate_slot` (`\d` acepta dígitos Unicode); un salto final en `hours` se recorta por `str_strip_whitespace` (no es defecto: se quitó el caso). Las pruebas de `field == "value.monday"`, antes/después de la auditoría (18 → 20), `default_capacity: true` y `settings.service.classes` (sin fila, válida, corrupta) nacieron verdes: cubren lo que la revisión halló sin prueba.

### Verde
- `HHMM_PATTERN` (settings) y `TIME_PATTERN` (classes) con `[0-9]`; docstring de `settings/router.py` (catorce rutas, siete `PATCH`); DECISIONES S7-D8 y US-154 documentan `field = "value.<día>"`. Gate `slice-gate.sh settings` (5 archivos): 894 passed, exit 0. Checkpoint `0a9bbf1`.

## S7-B1 · Sesiones, generación, job y CLI (US-156, S7-D10, M-3)

### Rojo
- Stubs con `NotImplementedError` (`planned_sessions`, `generate_sessions`, job, comando) y modelo `ClassSession`; 61 failed + 25 errors: `NotImplementedError` (27), «no existe la revisión 0027_class_sessions» (26), `relation classes.class_sessions does not exist` (grants y rutas de rol, 42P01 en lugar de 42501).
- Desvío: `planned_sessions`, `PlannedSession` y `SlotSpec` viven en `rules.py` (puras, sin ORM) y no en `sessions.py`; `sessions.py` tiene la generación y el candado.

### Verde
- `0027_class_sessions.py`: tabla, 6 CHECK (el trío `cancel_*` va junto y ya rechaza `done`), FK `RESTRICT` a franjas, índice único parcial `(slot_id, starts_at)`, índices por `starts_at` y `session_date`, guarda `classes.guard_sessions_update()` (solo `scheduled → cancelled`, `cancel_*` una vez, identidad inmutable; `wod_id` queda libre para EP-22) y triggers `forbid_delete`/`forbid_truncate`, todos `ENABLE ALWAYS`.
- `classes/{models,rules,events,sessions,slots,service}.py`: `generate_sessions` bajo `pg_advisory_xact_lock(4_270_006)`, crea las que faltan (cualquier estado cuenta como existente), `SessionGenerated` por sesión; `create_slot` genera su ventana tras el candado 4_270_005 (orden único 005 → 006). Job `worker/jobs/generate_sessions.py` (300 s, entre `expirations` y `notify`), `DETAIL_KEYS` `creadas` y `franjas`, CLI `generate-sessions --days 1..28 --as` (sin `job_runs`).
- Grants (`grants.sql`, tres listas): api `S I U(status, cancel_*, updated_at)`, worker `S I`. `AUDITABLE_TABLES` suma la tabla (excluida de «recientes» con motivo) y `PENDING_AUDITED` pasa a `results.results`. `conftest.py`: `LIMPIAR_CLASS_SESSIONS` antes de `LIMPIAR_CLASS_SLOTS` en las dos limpiezas (hallazgo 6).

### Evidencia (B1)
- Gates: `slice-gate.sh worker` (job y `test_schedule`) 850 passed antes del ajuste de tamaño y, tras partir `generate_sessions` en dos funciones (regla de 50 líneas), exit 0; `slice-gate.sh cli` exit 0; sello `slice-gate.sh classes` (puras, service, migración, grants, rol del worker): 1.138 passed, exit 0. Checkpoint `5753e0b`.
- P-MIG: volcado `sprint-07-antes-0027.dump` (2,1 MB, ignorado por git); `$DC start api` migró 0026 → 0027 (`alembic current` = `0027_class_sessions (head)`, api `healthy`); `downgrade -1` y `upgrade head` limpios; `\d classes.class_sessions` con 6 CHECK, FK `RESTRICT`, índice único parcial y los tres triggers en `tgenabled = A`. `$DC start worker` y `$DC restart worker`: `healthy`, y el reinicio ejecutó el job nuevo (`job_runs`: `generate_sessions` ok, `{"creadas": 0, "franjas": 0}`).
- `--run-once generate_sessions` dos veces el mismo día: filas en `classes.class_sessions` 0 antes, 0 después de cada corrida (la base de desarrollo no tiene franjas; se evitó sembrar datos). La idempotencia con filas la prueban `test_dos_corridas_no_duplican`, `test_job_y_cli_a_la_vez_una_sola_insercion` y `test_dos_corridas_el_mismo_dia_no_duplican`. `tools generate-sessions`: «creadas 0, franjas 0».
- Pendiente para el orquestador: `database-reviewer` y `security-reviewer` de B1; el volcado se borra en V9.

## S7-A2b y S7-B1b · Correcciones de revisiones (A2, B1)

- A2b (checkpoint `2bea58e`): rojo 1 failed (PATCH con días repetidos se aceptaba; ahora valida antes de normalizar, como el alta), 16 passed (hora con dígito árabe da 422 `start_time` en POST y PATCH, 409 por PATCH, coach inactivo/pendiente/sistema, `q` con `%` y `_`, dos altas concurrentes con el candado 4_270_005). Gate classes 894 passed.
- B1b: rojo medido de las pruebas nuevas: 6 failed (`not_before`, hoy ya pasado, `--as` coach y socio) y el cruce `create_slot` contra el job dio `DeadlockDetectedError` (40P01: `create_slot` pedía 4_270_006 con 4_270_002 en la mano). Verde: `take_generate_lock` en `create_slot` justo tras 4_270_005 (orden 005, 006, 002), `planned_sessions(..., not_before)` con el reloj, `--as` por `resolve_admin_actor`, pruebas de dígitos Unicode en `/settings/hours`. S7-D37 en DECISIONES (CHECK de `session_date` en la 0028 de C1, nota de `wod_id`). Gate classes 907 passed. Checkpoint arriba.

## Demostración viva de B1 (tarea 4)
- Franja ficticia `POST /api/v1/class-slots` «Prueba S7 CrossFit» (lunes a viernes 06:00, cupo 15, sin coach), id `5b7c8006-dc42-45cb-bbf2-4b395a861e9a`: 201 y `count(*) classes.class_sessions` 0 → 10 (16 al 27 de noviembre; hoy sábado no hay clase).
- `--run-once generate_sessions` dos veces: 10 y 10 (ok, sin duplicar); `tools generate-sessions --as admin@ejemplo.local`: «creadas 0, franjas 1», conteo 10. Token borrado. La franja y sus 10 sesiones quedan en la base de desarrollo.

## S7-B2 · Semana, sesión extra y cancelar (US-157, S7-D11, L-1, L-2, L-3, L-5)

### Rojo
- Stubs (`parse_week`, `week_range`, `week_of`, `date_range_utc`, `local_date`, `session_status`, `validate_extra_start`, `list_sessions`, `get_session`, `create_extra`, `cancel_session`) y router/schemas/excepciones reales: 56 failed, todos `NotImplementedError` (27 puras, 23 de service, 6 de router); 96 passed de arquitectura (rutas con límite, helpers privados, eventos sin datos personales).

### Verde
- Sin migración. `rules.py`: semana ISO validada con `[0-9]` y años 2020 a 2100 (`9999-W52` ya no desborda), `week_range` lunes a lunes de Bogotá en UTC, `session_status` (`done` calculado), `validate_extra_start` (de ayer a 90 días). `queries.py` (nuevo, privado): lista por semana o `from`/`to` (máximo 62 días, `range_too_long`), por omisión la semana actual; filtros `coach_id` y `status` (`done` por SQL con `make_interval`); detalle con `attendees: []`. `sessions.py`: `create_extra` (coach solo a sí mismo o nulo, L-3; `session_date` desde `starts_at`, S7-D37) y `cancel_session` (`FOR UPDATE`, 409 `session_finished` primero, luego `session_already_cancelled`, L-5; el evento `SessionCancelled(session_id, slot_id, starts_at)` y el log no llevan el motivo, L-2).
- Router: `GET/POST /class-sessions`, `GET /class-sessions/{id}`, `POST /class-sessions/{id}/cancel` con `StaffDep` (socio 403), `staff-read` y `classes-write`. `PRIVATE_HELPERS["classes"]` suma `queries`.
- [ASUNCIÓN] `attendance_count` es 0 y `attendees` va vacía hasta C1 (la tabla de asistencia no existe).
- P-API: `docs/openapi.json` (dos exportaciones idénticas; 75 → 78 rutas; además cambian `SlotCreate`, `SlotPatch` y `TimeRange` por el patrón ASCII de A1b, que no se había regenerado) y `web/src/core/api/types.ts`; `types.contract.test.ts` 6 passed.

## S7-B3 · Cancelar sesiones futuras (US-158, S7-D26)

- Rojo: stubs con `NotImplementedError`; `test_cancel_future.py` + `test_router_cancel_future.py` = 17 pruebas, 11 failed (NotImplementedError; 403/404/200 del router y 7 del service) y 6 passed (422 y ruta publicada, que no llegan al service).
- Verde: `sessions.cancel_future_sessions` (candado 4_270_006, comprobación de franja, un `SELECT ... FOR UPDATE ORDER BY starts_at, id`, UPDATE por ORM en un flush, un `SessionCancelled` por sesión); 17 passed. Futura = `starts_at > ahora`; solo `scheduled` de esa franja (extras y pasadas intactas).
- Concurrencia: `test_concurrente_con_generate_sessions_sin_quedar_scheduled` (job con 006 y sleep, cancelación espera): creadas 2, canceladas 2, ninguna scheduled, sin 40P01.
- Catálogo `test_error_codes_per_route.py` suma la ruta (`classes-write`). P-API: openapi idéntico en dos corridas, types.contract 6 passed.
- Gate `slice-gate.sh classes ...`: 840 passed, exit 0.

## S7-B2b · Correcciones de la revisión de B2 (S7-D38)

- Rojo: `test_extra_duplicate.py` (4) + 3 parámetros de rango y `test_sesion_extra_duplicada_409_por_http` en `test_router_sessions.py`: 5 failed (OverflowError en `9999-12-31`; sin `SessionDuplicate`/409), 7 passed.
- Verde: `queries._window` acota años 2020-2100 (`from`/`to`); `create_extra` toma 4_270_006 y comprueba duplicado (409 `session_duplicate`); `test_router_slots` ahora filtra `/class-slots*` e incluye `cancel-future-sessions` (estaba roto por B2 y B3, fuera de los gates de esos slices). `tests/classes`: 184 passed.
- P-API regenerado.

## S7-B3b · Correcciones de la revisión de B3 (LOW de B2b/B3)

- Rojo: 4 failed (`test_extra_duplicate.py` 2 y `test_week_range_pure.py` 2: 06:00:30 y 1 microsegundo no daban 422) y 39 passed (las pruebas nuevas de orden de sentencias y de sesión en curso ya cumplían).
- Verde: `rules.validate_extra_start` rechaza segundos y microsegundos distintos de cero (422 `field=starts_at`); así 06:00:30 ya no esquiva el 409 `session_duplicate`. `test_cancel_future` suma una sesión en curso (09:30, 60 min, reloj 10:00) que sigue `scheduled`; `test_extra_duplicate` afirma `pg_advisory_xact_lock` antes del SELECT de duplicado y del INSERT. `core/locks.py` documenta el orden ampliado y que los suscriptores de `SessionCancelled`, `SessionGenerated` y `MemberCheckedIn` no toman candados (la cadena 002 ya está tomada); la prueba de concurrencia de C1 lo cubre (`test_los_suscriptores_de_sesion_no_toman_candados` y los dos cruces cancelación/check-in).
- Gate `slice-gate.sh classes` (3 pruebas): 866 passed, exit 0. Checkpoint `a98164e`.

## S7-C1 · Check-in (US-159, S7-D12, S7-D13, S7-D25, S7-D27, M-3, L-1, L-4)

### Rojo
- Stubs: reglas puras (`membership_flag`, `capacity_outcome`, `within_checkin_window`, `is_other_day`, `checkin_on_date`, `checkin_flags`), `attendance.check_in` y `list_attendance` con `NotImplementedError`; modelo, excepciones, evento, esquemas y rutas reales; sin migración.
- 5 archivos nuevos (93 pruebas): 57 failed (31 `NotImplementedError`, 26 `Can't locate revision '0028_attendance'`), 25 errors (tabla `classes.attendance` inexistente en los fixtures) y 12 passed (las que no llegan a la lógica).

### Verde
- Migración `0028_attendance` (id de 15 caracteres; padre `0027`): tabla `classes.attendance` (FK `RESTRICT` a sesiones, 4 CHECK, único parcial `(session_id, member_id) WHERE removed_at IS NULL` e índices parciales de ficha y semana), guarda `classes.guard_attendance()` (solo `removed_*` y `updated_at`, una vez; nunca se «desborra»), triggers `attendance_forbid_delete/_truncate`, los tres `ENABLE ALWAYS`; y el CHECK `ck_class_sessions_session_date_bogota` de S7-D37 (2). Downgrade lo quita todo.
- `rules`: siete banderas en orden fijo (`expired|no_membership|frozen|pending_payment`, `over_capacity`, `out_of_window`, `other_day`); `other_day` = `session_date` ni hoy ni ayer (Bogotá); `on_date = min(session_date, hoy)` (S7-D25).
- `attendance.py` (privado): puerto `MembershipPort` (`checkin_view`, `lock`), `set_membership_port`/`membership_port`, `MembershipPortNotRegistered`; `check_in` en una transacción: `ensure_exists`, `lock_member`, `ensure_exists` otra vez (L-4), sesión `FOR UPDATE` con `populate_existing`, puerto (bloquea la membresía antes del primer flush), duplicado, conteo de vivas, banderas, `INSERT` en savepoint (23505 a 409 `already_checked_in`), `MemberCheckedIn`. `list_attendance` (`GET /attendance`: `member_id`, `session_id`, `flagged`, `from`, `to` con `check_instant_range`, `q` por socio con `members.service.search_ids`; nombre y apellido por `names_for`, sin campos cifrados).
- `queries.py` y `sessions.py`: `attendance_count` real y `attendees` del detalle de la sesión (antes 0 y `[]`).
- Router: `POST /attendance` (201, `attendance-write`, `StaffDep`) y `GET /attendance` (`staff-read`).
- P-ROL: `infra/db/grants.sql` (`classes.attendance` S I U(`removed_at`, `removed_by`, `removed_reason`, `updated_at`) para `apex_api`; el worker no la toca; 25 tablas clasificadas), `test_db_grants.py`, `test_api_role_paths.py::test_check_in_como_apex_api_...`. `tests/conftest.py`: `LIMPIAR_ATTENDANCE` y `LIMPIAR_CLASS_SESSIONS` borran primero la asistencia (hallazgo 6); `triggers.py` suma los tres triggers.
- Arquitectura: `PRIVATE_HELPERS["classes"]` suma `attendance`; arista `classes -> members` en `ALLOWED_EDGES`; `classes.attendance` en las tablas auditadas, en `AUDITABLE_TABLES` y excluida de `recent`; `attendance-write` ya tiene ruta (`CLAVES_SIN_RUTA_TODAVIA` vacío).
- Hallazgos en el camino: (1) `SELECT ... FOR UPDATE` de la sesión devolvía el estado viejo si la identidad ya estaba cargada en la sesión de SQLAlchemy; `populate_existing=True` lo corrige (lo detectó `test_check_in_tras_la_cancelacion_masiva_da_409_sin_interbloqueo`). (2) Las pruebas con `dos_sesiones` no pueden usar `bus_listo` (su savepoint retiene `crypto_keys` y cuelga el `ALTER TABLE` de la limpieza): usan `bus_confirmado` de `tests/members`.
- Pruebas: 94 passed en los cinco archivos nuevos. Gate `slice-gate.sh classes` (flags_pure, service, concurrency, router_checkin, 0028, db_grants + `tests/architecture`): 1181 passed, exit 0.
- P-API: `docs/openapi.json` idéntico en dos corridas y `types.ts` regenerado; `types.contract.test.ts` 6 passed.

### Evidencia (Docker, sin llamar `POST /attendance`: el puerto no está registrado hasta C2, hallazgo 10)
- Volcado `docs/scratch/sprint-07-antes-0028.dump` (2,2 MB, ignorado por git). `$DC stop api worker` antes de escribir; `$DC start api` migró `apex-db-1`: `alembic current` = `0028_attendance (head)`; `downgrade -1` y `upgrade head` bien; el CHECK de la fecha de Bogotá aceptó las 10 sesiones existentes.
- Esquema: `\d classes.attendance` (columnas, 3 índices, 4 CHECK, FK `RESTRICT`), los seis triggers de `classes.attendance` y `class_sessions` en `tgenabled = 'A'`, 0 triggers de guarda fuera de `A`, `guard_attendance` `SECURITY INVOKER`.
- Smoke 8181: `/health` ok (`migrations: ok`, `crypto: ok`); `POST /attendance` y `GET /attendance` sin token: 401. **Ventana C1 a C2:** con token, `POST /attendance` daría 500 `MembershipPortNotRegistered` hasta que C2 registre el puerto; el primer check-in real es la evidencia de C2. Sin token de admin en esta sesión no se llamó `GET /class-sessions/{id}` con rol.

## S7-W3a-fix · Pruebas de catálogo y truncate tras el gate de la Wave 3a

El gate completo de la Wave 3a (copia limpia de `0393b35`) dio 5 fallas que los gates por slice no corrían:
- `tests/audit/test_filters.py::test_auditable_tables_es_la_lista_unica_de_las_doce_tablas`: la lista esperada suma `classes.class_slots`, `classes.class_sessions` y `classes.attendance`.
- `tests/core/test_env_example.py::test_las_cuatro_cubetas_nuevas_...`: `classes-write` y `attendance-write` ya tienen ruta; `CLAVES_SIN_RUTA_TODAVIA` queda vacío (`attendance-write` la recibió en C1).
- `tests/migrations/test_0026_class_slots.py::test_delete_y_truncate_estan_prohibidos`: desde `0027` el `TRUNCATE classes.class_slots` a secas choca con la FK de `class_sessions` (0A000) antes del trigger. La prueba ahora espera P0001 en `DELETE` y en `TRUNCATE ... CASCADE` (que sí ejecuta la guarda) y 0A000 en el `TRUNCATE` a secas: no se debilita, se suma un caso.
- `tests/worker/test_jobs_core.py::test_detail_keys_es_el_conjunto_cerrado_del_plan`: suma `creadas` y `franjas`.
- `tests/worker/test_notify_job.py::test_notify_esta_entre_expirations_y_sign_audit_a_las_siete`: `generate_sessions` va entre `expirations` y `notify`.

Saltos: el gate de la copia limpia saltó 183 pruebas y la línea base de W0 103. Comparados los `SKIPPED` de los dos logs por archivo y motivo, la única diferencia son 80: 13 de `tests/attachments/test_s3_flags.py` y 67 de `tests/attachments/test_storage_contract.py` por «falta el extra s3 (boto3/botocore)». Es del entorno: el `.venv` de la copia limpia (`.claude/worktrees/gates/api/.venv`) no tiene `boto3` ni `botocore` (extra opcional `s3`); el del árbol principal sí. En el árbol principal esas dos carpetas corren (154 passed, 1 skipped por los modos POSIX en NTFS). No viene del código del sprint.

Tras corregirlas, la corrida única `tests/audit tests/core tests/migrations tests/worker tests/classes tests/architecture` (`-m "not perf" -rs`) dio una falla más, causada por C1: `tests/migrations/test_0027_class_sessions.py::test_delete_y_truncate_estan_prohibidos` (desde `0028` el `TRUNCATE classes.class_sessions` a secas choca con la FK de `classes.attendance`, 0A000); se corrigió igual que la de `0026` (`CASCADE` da P0001, el `TRUNCATE` a secas 0A000). Resultado final de la corrida única: 4212 passed, 6 skipped (4 de `test_backup_check.py`, 1 de `test_jwt.py`, 1 de `test_signing_key_exposure.py`: enlaces simbólicos, mkfifo y modos POSIX de Windows), 18 deselected, 0 failed, 6 min 59 s.

## S7-C2 · Descontar y devolver clases (US-160, S7-D14, S7-D25, S7-D29, L-5)

### Rojo
- `$DC stop api worker` antes de escribir. Stubs con `NotImplementedError` (`consumes_class`, `consume_class`, `return_class`, handlers `on_member_checked_in` y `on_attendance_removed`, `ClassesPort`), eventos reales (`ClassConsumed`, `ClassReturned`, `AttendanceRemoved`) y la migración `0029` fuera del árbol: 51 failed + 7 errors, 72 passed en los archivos nuevos y tocados. Motivos: `NotImplementedError` (pura, handlers y puerto: 44), «no existe la revisión 0029_memberships_orig_end_date» (8: 7 errors + 1 failed), `plan_renewal() got an unexpected keyword 'after'` (1), arquitectura (2: `lock_membership` de los handlers nuevos) y 3 que dependían del stub (check-in de C1 con el puerto de memberships, rol `apex_api`). Nacieron verdes (ya cumplía): `test_create_app_deja_el_puerto_registrado` (el registro entró con los stubs), `test_upgrade_desde_0027_falla...` (0028 ya lo hacía) y el par de 0028.
- Puntos de la revisión de C1: (1) prueba de arranque (`create_app` y subproceso limpio: `membership_port()` no es `None`); (2) `test_los_handlers_de_check_in_y_de_quitar_solo_bloquean_la_fila_del_emisor` en `test_checkin_concurrency.py` + `test_handlers_de_clases_solo_bloquean_la_fila_del_evento` (arquitectura, ata `lock_membership(session, event.membership_id)`); (3) `ck_attendance_membership_pair` en `0029` con consulta previa y su prueba (`test_check_del_par_de_la_asistencia`, `test_upgrade_aborta_con_el_conteo_si_hay_pares_malos`); (4) `test_upgrade_desde_0027_falla_y_revierte_con_una_sesion_desfasada` en `test_0028_attendance.py`. Punto 4 de la revisión (lista `IN` de `search_ids`): aceptado en S7-D40 (7).

### Verde
- `0029_memberships_orig_end_date` (30 caracteres): `original_end_date date NULL`, CHECK `ck_memberships_original_end_date_needs_classes` y `ck_attendance_membership_pair` (con aborto y conteo). `grants.sql` (matriz, lista) y `test_db_grants.py`: `original_end_date` en el `UPDATE` de `apex_api`.
- `rules.py`: `ClassBalance`, `ClassUsage`, `consumes_class`, `consume_class` (`min(end, max(start, hoy))`; conserva el `original_end_date` más antiguo), `return_class`, y `plan_renewal(..., after=)`. `lifecycle.py`: los dos handlers (un único `lock_membership` con `event.membership_id`). `sell.py`: `ClassesPort` (puerto real) y la renovación empuja el inicio al día siguiente de una agotada (S7-D40 (4)). `service.py`: registro del puerto y las dos suscripciones; `ClassConsumed` y `ClassReturned` marcan el resumen. `classes/events.py`: `AttendanceRemoved`.
- Desvíos: (a) [DECISIÓN DE DISEÑO] `plan_renewal(after=)`: sin ella la renovación inmediata a una agotada daba `MembershipOverlap`; (b) `FakeMembershipPort.membership_id` pasó a propiedad (con `.status = "none"` el doble dejaba un id y violaba el par nuevo); (c) `test_0008` y `test_db_grants` suman la columna; (d) el nombre `test_vencida_mas_futura...da_no_membership...` se conserva pero afirma `expired` (S7-D40 (6)); (e) sin cambio en `memberships/schemas.py` ni en el contrato (no hay P-API).

### Evidencia (C2)
- Suite ancha antes del gate (`tests/classes tests/memberships tests/migrations tests/audit tests/core/test_migrations.py tests/payments`): 3042 passed, 2 failed, ambas por mi cambio y corregidas: `test_0008` (columna exacta nueva) y `test_checkin_service[none]` (el doble `FakeMembershipPort` dejaba un id con `status = "none"` y violaba el par nuevo; ahora el id es una propiedad). `ruff check`, `ruff format` y `mypy --strict src` en verde.
- Sello `slice-gate.sh memberships` (11 archivos: `test_consume_return_pure`, `test_class_consumption`, `test_sell_service`, `test_0029...`, `test_api_role_paths`, `test_db_grants`, `test_membership_port`, `test_checkin_service`, `test_checkin_concurrency`, `test_0028_attendance`, `test_0008_memberships` + `tests/architecture`): 1284 passed, exit 0. Sin sellar aparte: `slice-gate classes` queda cubierto por los mismos archivos de `tests/classes`.
- P-MIG: volcado `sprint-07-antes-0029.dump` (2,2 MB, ignorado por git; se borra en V9); `$DC start api` migró 0028 a 0029 (`alembic current` = `0029_memberships_orig_end_date (head)`, api `healthy`); `downgrade -1` y `upgrade head` limpios; `\d memberships.memberships` muestra `original_end_date date` y el CHECK `ck_memberships_original_end_date_needs_classes`; `ck_attendance_membership_pair` existe; 0 triggers de guarda fuera de `A` en `memberships`, `class_sessions` y `attendance`. P3 (S7-D30): `classes_remaining = 0 AND end_date > current_date AND status <> 'cancelled'` = 0. `$DC start worker` y `$DC restart worker` sin errores.
- Prueba viva (admin de desarrollo, token en `$TMPDIR` con `umask 077` y borrado al terminar; el login exige `Origin: http://localhost:8180`): plan «Prueba S7 Tiquetera 10» (10 clases), socio «Prueba S7 Tiquetera» (id `91362905-d47c-4815-b6c1-eb2d45cb5bc5`), venta con primer pago en efectivo (201, `active`), sesión extra de hoy «Prueba S7 CrossFit» a las 22:45 Bogotá (201) y `POST /attendance` 201 con la bandera `out_of_window` (son las 21:12). `SELECT classes_remaining, end_date, original_end_date, status` pasó de `10|2027-01-13||active` a `9|2027-01-13||active`. Dos check-in anteriores del mismo socio dieron 201 con `no_membership` (la venta falló 422 por el código de método de pago `Efectivo`: es `cash`) y no descontaron nada; quedan en la base de desarrollo, junto con las tres sesiones extra de hoy (03:00Z, 03:30Z y 03:45Z del 15, es decir 22:00, 22:30 y 22:45 de Bogotá del 14). La devolución en vivo queda para C3 (`DELETE /attendance/{id}` no existe todavía).
- Pendiente para el orquestador: `database-reviewer` y `security-reviewer` de C2; el volcado se borra en V9.

## S7-C3 · Quitar una asistencia (US-161, S7-D13, S7-D27 b, E4, E5, S7-D40 (9) a (11))

### Rojo
- Stubs: `remove_attendance` con `NotImplementedError`, ruta `DELETE /attendance/{attendance_id}`, `AttendanceNotFound` (404 `attendance_not_found`), `AttendanceLocked` (403 `attendance_locked`), `AttendanceRemove`. Pruebas nuevas: `tests/classes/test_remove_attendance.py` (15), `test_router_remove_attendance.py` (17 con parametrización), `tests/audit/test_member_history_attendance.py` (2): 25 failed + 2 errors (por `NotImplementedError` y por el fixture `puerto` ausente en `tests/audit`; el segundo era del test, se definió local), 8 passed (los que no llegan a la implementación: 403/401/422, rol, ruta publicada).
- Prueba de concurrencia `test_remove_concurrency.py`: con `lock_member` quitado a propósito falla (`[True] == [False]`); con él pasa.

### Verde
- `classes/attendance.py` `remove_attendance`: asistencia previa (404) → `lock_member` → `FOR UPDATE` con `populate_existing` (404 si ya quitada) → coach: `is_other_day` ⇒ 403 → `port.lock` si hay membresía (sin puerto y con membresía: `MembershipPortNotRegistered`, falla cerrado) → `removed_*` + `flush` (auditoría `update`) → `AttendanceRemoved`. Router `DELETE` 204 con `Body(default=None)`, cubeta `attendance-write`. P-API: `docs/openapi.json` (idéntico en dos corridas) y `types.ts`; `types.contract.test.ts` 6 passed.
- Desvíos: `test_error_codes_per_route.py` (`CON_LIMITE`) y el comentario de `test_user_limits_catalog.py` suman la ruta nueva (los gates de arquitectura lo exigían). Se había definido `puerto` en `tests/audit/test_member_history_attendance.py` por no existir el fixture fuera de `tests/classes`.

### Evidencia (C3)
- Sello `slice-gate.sh classes` (4 archivos + `tests/architecture`): 866 passed, exit 0.
- Checkpoint `840a7e1`. Prueba viva (admin de desarrollo, token en `$TMPDIR` con `umask 077`, borrado al terminar): `DELETE /api/v1/attendance/15b833c9-9865-4daa-9f32-476e643394af` con `{"reason":"Prueba viva C3"}` dio 204; un segundo `DELETE` dio 404 `attendance_not_found`. En la base: `classes_remaining` de la membresía `04be2fc3-c805-46b9-aede-8f994ee63b39` pasó de 9 a 10 (`active`); la asistencia tiene `removed_at`, `removed_by` y `removed_reason` no nulos; `audit.audit_log` para esa asistencia: `6150 insert` y `6153 update`, ambas con `subject_member_id` del socio; la membresía suma 3 `update` y 1 `insert`. Quedan en la base de desarrollo las otras dos asistencias `none` del socio.

## S7-C2b · Correcciones de la revisión de C2 (M1, L2, L3, L4, L5, L7; S7-D40 (12) a (16))

### Rojo
- `$DC stop api worker` antes de escribir (hay migración). Volcado `docs/scratch/sprint-07-antes-0030.dump` (2,2 MB, ignorado por git; se borra en V9); consulta previa en desarrollo: 0 filas con `original_end_date` no posterior a `end_date`.
- Pruebas nuevas: `tests/memberships/test_review_c2_points.py` (M1: renovar y vista previa sobre una heredada agotada, vista previa tras agotar hoy; L4: ya vencida no emite, activa sí; L5: descontar y devolver con la membresía de otro socio, y el mismo socio sí), `tests/migrations/test_0030_memberships_end_guard.py` (revisión y cadena, CHECK igual/anterior/posterior/nulo, CHECK de `0029` sigue, guarda de anuladas, downgrade, aborto con conteo, ciclo) y el reforzamiento de `test_apex_api_escribe_original_end_date` (residuos y fecha de Bogotá en SQL). Sin código: 7 failed + 6 errors (la revisión `0030` no existía) y 3 passed (los casos positivos); el de L7 falla con `assert 3 == 0` (3 filas residuales: membresía, socio y plan).
- Dos errores míos de la prueba, corregidos antes del Verde: `make_member` dos veces repite el documento (se usa `make_members(session, 2)`) y se había clavado `ruff format` sobre `0029` (revertido con `git checkout`: una migración aplicada no se toca).

### Verde
- `sell.py` (`m.end_date == ctx.today`), `lifecycle.py` (`_usable_class_row(..., member_id, ...)`, `ya_vencida` antes de `_store_usage`), `expirations.py` (docstring), `migrations/versions/0030_memberships_end_guard.py`, y la limpieza por id de L7.
- Sello `slice-gate.sh memberships` (11 archivos + `tests/architecture`): 1248 passed, exit 0.

### Evidencia (C2b)
- P-MIG: `$DC start api` migró `0029` a `0030` (`alembic current` = `0030_memberships_end_guard (head)`, api `healthy`); `downgrade -1` deja `0029_memberships_orig_end_date` y quita el CHECK (0 filas en `pg_constraint`); `upgrade head` vuelve a `0030 (head)`. `pg_get_constraintdef`: `CHECK (((original_end_date IS NULL) OR (original_end_date > end_date)))`. Triggers de `memberships.memberships`: los tres en `tgenabled = A`; `guard_identity()` contiene `original_end_date`. Sin cambio de grants (P-ROL no aplica).

## S7-R1 · Reportes de asistencia (US-162, S7-D15, M-5, L-1)

### Rojo
- Stubs: `classes/reports.py` (`check_summary_range`, `week_starts`, `weekly_summary`, `summary_rows`, `attendance_summary`, `member_attendance` con `NotImplementedError`), schemas `SlotBucket`, `WeekBucket`, `AttendanceSummary` y las dos rutas. Pruebas nuevas: `test_weekly_summary_pure.py`, `test_attendance_list.py` (la lista ya existía desde C1), `test_attendance_summary.py`, `test_member_attendance.py` y `test_perf_summary.py` (`perf`): 45 failed (todas `NotImplementedError`) y 10 passed (lista existente, 401/403) de 55.

### Verde
- `reports.py`: el resumen se agrega en UNA consulta SQL (subconsulta de asistencias vivas por sesión, `date_trunc('week')` sobre `session_date` de Bogotá, `GROUP BY` semana y franja); `weekly_summary` pura solo arma grupos y rellena semanas vacías; `occupancy_pct` entero con cupo 0 = 0; extras bajo «Extra». Rango: `from > to`, año fuera de 2020 a 2100 o más de 26 semanas (182 días) dan 422 `field = "from"`. `GET /members/{id}/attendance` por `members.service.get_ref` (baja visible, 404 si no existe), con `q` por el contrato de listas (lo exigió `test_list_routes_use_page_params`). Ambas rutas consumen `staff-read`; `test_error_codes_per_route` las suma.
- [ASUNCIÓN] El resumen cuenta solo sesiones `scheduled` que ya empezaron (`starts_at <= ahora`): las futuras o canceladas diluirían la ocupación.
- Desvío: `list_attendance` sigue en `attendance.py` (C1); `reports.member_attendance` lo reutiliza. Un `summary_rows` de más de 50 líneas rompió `test_ninguna_funcion_supera_50_lineas`: se extrajo `_live_by_session`.

### Evidencia (R1)
- Pruebas nuevas: 55 passed (+1 perf: 26 semanas con 1.170 asistencias, bajo 500 ms). Sello `slice-gate.sh classes` (4 archivos + `tests/architecture`): 886 passed, exit 0 (primer intento falló por `q` ausente y por la lista de `staff-read`; segundo, 2 pasos corregidos). Nota: el gate necesita `TEST_DATABASE_URL` exportada (sin ella 118 errores de fixture).
- P-API: `docs/openapi.json` idéntico en dos corridas, `types.ts` regenerado, `types.contract.test.ts` 6 passed.
- Prueba viva (admin de desarrollo, token en `$TMPDIR` con `umask 077`, borrado): `GET /attendance/summary` 200 (semana 2026-W46: total 1, marcadas 1), 422 con `from > to` y con más de 26 semanas, 401 sin token; `GET /members/{id}/attendance` del socio «Prueba S7 Tiquetera» 200 con `total` 2, 404 con un id inexistente.

## S7-C3b · Correcciones de la revisión de C3 (S7-D40 (17) a (20))

### Rojo
- `tests/memberships/test_review_c3_freeze.py` (4): con el camino real resumido (tiquetera `active`, fin = hoy, `original_end_date` 4 días después, 3 clases) congelar 10 días da `IntegrityError` por `ck_memberships_original_end_date_after_end` (el 500); la regla pura no acepta `original_end_date` ni devuelve `new_original_end_date`. Sin código: 3 failed (el `IntegrityError` y 2 `TypeError`) y 1 passed (sin original, igual que antes).
- Borde de las 04:30Z en `test_remove_attendance.py` y comparación de `pg_get_functiondef` en `test_0030`: pasan de entrada (la implementación ya era correcta; son pruebas de borde, sin rojo).

### Verde
- `rules.apply_freeze(..., original_end_date=)` y `FreezeOutcome.new_original_end_date`; `lifecycle._apply` lo pasa y `_store_freeze` lo guarda; CHECK `original_end_date_after_end` en `memberships/models.py`; `test_0030` compara la función de `0029` con la que deja el `downgrade`. DECISIONES (17) a (20) y la nota de R1.
