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
