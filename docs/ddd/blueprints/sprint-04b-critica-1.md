# Crítica 1 del plan del Sprint 4B (plan-critic) · Veredicto: RECHAZADO

Anclaje: `docs/ddd/blueprints/sprint-04b-plan.md` (899 líneas), HEAD `280addd`, rama `feat/sprint-04b-continuidad-release`. Solo lectura. El crítico no pudo ejecutar `docker ps`; el orquestador comprobó después: puertos 8280 y 8380 libres, única red `172.30.0.0/24` (`apex_default`; el ensayo y el smoke van en `172.31.x`), 6 GB libres. Los 3 HIGH, los 10 MEDIUM y los 10 LOW de seguridad y C1..C10 tienen paso en el plan (§10 y §1, contradicciones 1 a 16). M-8 (Caddy) está justificadamente no adoptado, con dueño v0.2. El rechazo se debe a tres supuestos falsos que dejan un slice o la CI en rojo.

## Bloqueantes

1. **`restore.sh` invoca un prefijo que `run.sh` rechaza (B3a contra W0-1).**
   - Plan líneas 557 y 150 (S4B-D57): `restore.sh` toma `pre-restore-<ts>` con `run.sh --prefix pre-restore`.
   - Plan línea 234 (W0-1.2): `valid_prefix` acepta solo `apex` y `pre-deploy`. La línea 254 repite `--prefix <apex|pre-deploy>`. S4B-D80 y `manifest.schema.json` limitan `name` a `apex-...` o `pre-deploy-...`.
   - Consecuencia: el volcado de seguridad previo a restaurar (la salvaguarda de H-2) nunca se genera, o `restore.sh` aborta antes de tocar la base. `restore_e2e.sh` lo descubriría recién en B3a.4, con W0-1 ya sellado.
   - Corrección: ver E1.

2. **P-ROL y el ensayo usan una imagen `apex-api:local` sin la `0014` ni los cambios de W0-3.**
   - `api/Dockerfile:19-21` hace `COPY src`, `COPY alembic.ini` y `COPY migrations`.
   - Plan línea 383 (W0-3.10.1): "Dockerfile sin cambios desde W0-1: se reutiliza si el id coincide". La línea 65 solo manda reconstruir por `pyproject.toml`, `uv.lock`, `alembic.ini` o `Dockerfile`.
   - Pero la imagen de W0-1.10 se construyó antes de la `0014` (W0-2) y antes de `main.py`, `config.py`, `db.py` y `oplog.py` (W0-3.6). El `migrate` del ensayo sale como producción y no monta bind. Con la imagen vieja: sobre una base nueva migraría solo hasta `0013`; sobre `apex-db-1` (en `0014`) fallaría con "Can't locate revision"; el `api` vendría sin `MIGRATE_ON_STARTUP`, y `Settings` es `extra="forbid"`.
   - Además, `$DC --profile prod-init run --rm dbsetup` (W0-3.11) arranca por `depends_on` el servicio `migrate`. Ese ejecutaría `alembic upgrade head` como propietario sobre `apex-db-1`, justo lo que la sección 0 limita a P-MIG 6/7 y V2.
   - Corrección: ver E2 y E3.

3. **El job `images` de la CI correría `test_db_roles.sh` contra un stack sin roles.**
   - Plan línea 368 (W0-3.7): `images` corre `test_db_roles.sh` "contra el stack del smoke".
   - Pero `scripts/ci/compose-smoke.sh:19` levanta `compose.yml` + `compose.dev.yml`. En ese overlay `migrate` y `dbsetup` llevan `profiles: ["prod-init"]` (plan línea 344) y el api usa el propietario. El mismo paso 27 dice que el smoke solo comprueba que esos servicios no se listan.
   - Resultado: `test_db_roles.sh` falla por rol inexistente en CI. S4B-D81 exige los siete jobs verdes antes de empujar la etiqueta, así que el release queda bloqueado.
   - Corrección: ver E4.

## Enmiendas (mandan sobre el plan)

- **E1 (W0-1, `lib.sh`, `run.sh`, `manifest.schema.json`, `test_lib.sh`).** `valid_prefix` acepta `apex`, `pre-deploy` y `pre-restore`. `name` del esquema y de `parse_manifest` admite `pre-restore-AAAAMMDD-HHMMSS`. `pre-restore-*` no toca `latest.json`, igual que `pre-deploy`. Añadir el caso a `test_lib.sh`, a `test_manifest.sh` y a `test_restore_guard.sh` (B3a.2), que debe afirmar que `restore.sh` genera `pre-restore-*.json` y `.minisig` antes del `pg_restore`. `backup_check` ya descarta cualquier manifiesto que no sea `apex-*` como `latest.json`.
- **E2 (W0-3.10 y W0-3.11).** Se elimina "se reutiliza si el id coincide". Reconstruir `apex-api:local` con buildx siempre en W0-3.10 (y en W0-2.7 si algún paso usa la imagen), y anotar el id. Añadir a la regla de Docker (sección 0) que cualquier cambio en `src/` o `migrations/` exige rebuild para los servicios sin bind (`migrate`, `dbsetup`, el ensayo, el smoke). Esto también cubre B2.9 y B4.10 para el ensayo.
- **E3 (W0-3.11 y P-ROL).** Usar `$DC --profile prod-init run --rm --no-deps dbsetup`. Con `--no-deps`, `migrate` no corre sobre `apex-db-1`. La salida del `migrate` del ensayo (W0-3.10) debe mostrar "revisión 0014 aplicada" antes de aceptar `dbsetup`. Añadir una aserción a `test_compose_config.sh`: `dbsetup` en `depends_on migrate` solo en el overlay de producción, y en dev el comando documentado lleva `--no-deps`.
- **E4 (W0-3.7, `ci.yml`, `compose-smoke.sh`).** Elegir una de dos: (a) `test_db_roles.sh` corre en `prod-smoke` y en `e2e-stack` (que sí aplican `dbsetup`), no en `images`; (b) `compose-smoke.sh` añade `--profile prod-init run --rm dbsetup` antes del script. Una sola opción por decisión numerada. **Decisión del orquestador: (a).**
- **E5 (W0-2.2, spec de `test_0014`).** El plan afirma que `audit.forbid_mutation` sirve a "los cuatro `*_forbid_mutation`/`*_guard`" y que el mensaje de `crypto_ops` sale de `TG_TABLE_NAME`. Verificado: `audit.forbid_mutation` la usan 4 triggers, `audit_log`×2 y `verifications`×2 (`0002_audit_log.py:88-93`, `0013:60-63`). `crypto_ops` usa `crypto.forbid_ops_mutation` con su texto fijo (`0003_crypto.py:184-198`), y `crypto_keys_guard` y `crypto_jobs_guard` tienen funciones propias. Corregir el Rojo: `tgfoid` solo para los 4 triggers de audit; el mensaje de `crypto_ops` es una aserción independiente que no depende del `CREATE OR REPLACE`; el único efecto real del `CREATE OR REPLACE` es el texto de `audit.verifications`; corregir el comentario de DECISIONES (S4B-D4): el texto "audit.audit_log es append-only" en `verifications` es la deuda que cierra.
- **E6 (W0-1.11).** La puerta de W0-1 toca `core/config.py` (`NON_API_ENV_VARS`) pero `wave0-gate.sh` sella con `slice-gate.sh architecture`, que no corre `ruff`/`mypy` (`codigo=""`, `slice-gate.sh:108,133`). Añadir antes del sello `slice-gate.sh core/config tests/core/test_config.py tests/core/test_env_example.py`. Es el mismo patrón que el paso 29 de W0-3 y que el plan ya aplica allí.
- **E7 (W0-1, orden de `.env.example`).** Verificado: `.env.example:9,13` aún trae `POSTGRES_PASSWORD` y `DATABASE_URL`, y `infra/compose.yml:16,31,54` sigue con `env_file: ../.env`. Lo leen también `compose-smoke.sh:18` y `test_compose_config.sh:22`, que copian `.env.example` si falta `.env`. Con la partición de W0-1, el árbol de W0-1 y W0-2 no levanta desde un clon limpio hasta W0-3: `db` sin contraseña, `Settings` sin `DATABASE_URL`, y el `backup` de W0-1 con `PGPASSWORD` vacío. Mover el recorte de `.env.example` a W0-3 (W0-1 solo crea `.env.ops.example`), o hacer que `compose-smoke.sh` y `test_compose_config.sh` pasen ambos `--env-file` ya en W0-1. Una de las dos con decisión numerada. **Decisión del orquestador: mover el recorte a W0-3.** Sin esto, el bisect y los checkpoints intermedios quedan inválidos.

## Observaciones menores

- `JOBS == [("expirations", 7, 0, 900), ...]` (plan líneas 500 y 487) no corresponde al tipo real. `worker/jobs/__init__.py:9` define `tuple[JobSpec, ...]` con campos `name`, `run`, `hour`, `minute` y `timeout_s`. La prueba debe comparar `(spec.name, spec.hour, spec.minute, spec.timeout_s)`.
- `EXIT_BY_RESULT` (`worker/main.py:57`) está indexado por `result`, no por `status`. La prueba de B2.3 debe cubrir `ok_unverified` → 0 con la clave nueva y que un `result` desconocido siga yendo a `EXIT_JOB_FAILED` (`main.py:143`).
- Fixture `apex_roles` en `db_test`: los roles son del clúster, no de la base. Un fallo a mitad deja `apex_api`, `apex_worker` y `apex_backup` vivos en `db_test`, y `DROP ROLE` falla si quedan `GRANT` en otras bases. El teardown debe hacer `DROP OWNED BY` y luego `DROP ROLE`, y la fixture debe empezar con `revoke.sql` idempotente.
- `apex_roles`: `roles.sql` usa `\getenv`/`\gexec` (psql) y la fixture lo reproduce con `asyncpg`. El riesgo 8 del plan ya lo admite. Fijar desde el Rojo la alternativa `docker exec` en `apex-db_test-1` para que el Verde de `grants.sql` no se desvíe del archivo real que ejecuta `dbsetup`.
- Memoria (~5-6 GB): `apex-ensayo` queda arriba desde W0-3.10 hasta V12, junto a `apex` (6 servicios), `dian` y `db_test`, y el plan prohíbe correr pytest completo con vitest. Añadir en W0-3.10 un `docker stats --no-stream` de línea base y la regla "el ensayo se detiene con `stop` (sin `-v`) mientras corren las suites completas y `run-gates.sh`". Puertos 8280/8380 y subred 172.31.x: comprobados libres por el orquestador.
- `age` en el job `api` de la CI (riesgo 10): fijar versión y comprobar `age --version` en un paso previo, o la prueba `pty` se salta en silencio. Con `skipif`, la CI puede quedar "verde" sin haber ejercido `age` real. Añadir un paso de CI que falle si el conteo de saltadas de `test_archive_real_age.py` y `test_kek_real_age.py` es mayor que cero.
- Escrituras post-sello: el plan ya lo gobierna con la huella (`slice-gate.sh:69-77` incluye `git diff` más no rastreados, no ignorados). `docs/scratch/ensayo/` y `.env*` están ignorados. Confirmar con `git check-ignore -v docs/scratch/ensayo/x` en W0-1.1, porque `docs/scratch/sprint-04b.md` sí está rastreado y debe escribirse antes del sello (el plan lo ordena bien).
- `CHANGELOG.md` con SHA (riesgo 17): aceptable como está, pero `check-release-version.sh --check v0.1.0` no debe exigir el SHA, o la CI sobre `main` fallaría tras cualquier commit posterior.

## Verificado sin hallazgo

- `tests/conftest.py`: exactamente 4 `ENABLE TRIGGER USER` (líneas 187, 308, 312, 719) y 3 comentarios (223, 261, 287). Hay 15 archivos de prueba más `test_no_trigger_tampering.py`, que el plan deja intacto. Coincide con S4B-D6.
- Limpieza de `audit_log` bajo `ENABLE ALWAYS`: `DISABLE TRIGGER USER` desactiva también los triggers `ALWAYS` (`tgenabled='D'`), así que `DELETE` entre pruebas sigue funcionando y el re-armado por nombre con `ENABLE ALWAYS` es correcto. No rompe la suite. El caso `test_tras_la_limpieza_de_sesion_los_diez_triggers_siguen_en_always` es el vigilante adecuado.
- Los ocho triggers de la `0014` existen con esos nombres (`0002:88-93`, `0003:193-266`). `verifications` ya tiene `ENABLE ALWAYS` en `0013:65-67`, de ahí "diez".
- Ninguna prueba busca el texto "audit.audit_log es append-only" fuera de las migraciones. Los asserts usan solo `"append-only"` (`test_audit_log_db.py:92`, `test_crypto_tables.py:74-76`, `test_oplog.py:170`).
- `slice-gate.sh`: mapeo real de `cli` (línea 107, solo `cli.py`), `core/<x>` de un nivel (99), `architecture` sin código (108) y archivos de prueba bajo `api/tests/` (124). Todos los archivos de gate que el plan cita y no crea en su propio slice existen (`test_digest`, `test_jobs_core`, `test_db`, `test_verify_audit`, `test_bootstrap`, `test_registry`, `test_errors_busy`, `test_startup_failure`).
- `wave0-gate.sh` delegando en `slice-gate.sh architecture`: `checkpoint-commit.sh` solo lee `.git/apex/slice-gate.ok` y compara la huella (`checkpoint-commit.sh:37-53`). La huella cubre diff más no rastreados no ignorados, o sea `infra/` y `scripts/` también.
- `test_crypto_bus_importers.py:37,46,201` y `test_guarded_calls.py:122`: B0.1 los trata en el mismo paso; la extracción mueve el único import de `core.crypto.types` a `cli_base.py`. `cli.py` hoy no llama `enforce_retroactive_limit`, por lo que mover el permiso a `seed/apply.py` es consistente.
- `test_compose_config.sh:171` ("worker sin volumenes") es la aserción que W0-3.2 reemplaza. `main.py:188` tiene `run_migrations_on_startup: bool = True`, que W0-3.6 convierte en `bool | None`. `cli.py` tiene 760 líneas (S4B-D28).
- `infra/compose.dev.yml` monta `src` y `migrations` solo en `api`, `worker` y `tools`, y no en `migrate`/`dbsetup`. De ahí el hallazgo 2.
- Sin migración en B0..B4 salvo la `0014`. El rollback por migración (sección 9) es coherente.

## Qué le falta para ser APROBADO

1. Aplicar E1 a E4 (bloqueantes) y E5 a E7 (rojo mal especificado, gate sin lint, árbol intermedio no arrancable).
2. Re-ejecutar plan-critic solo sobre W0-1, W0-3.7, W0-3.10 y W0-3.11 tras las enmiendas.
3. Confirmado por el orquestador en W0-1.1 anticipado: puertos 8280/8380 libres, subred 172.31.x libre, 6 GB libres; `docker stats` de línea base se toma en W0-3.10.
