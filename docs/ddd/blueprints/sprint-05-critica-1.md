# Crítica 1 del plan del Sprint 5 (plan-critic) · Veredicto: APROBADO CON OBSERVACIONES

Sobre `docs/ddd/blueprints/sprint-05-plan.md` (1.682 líneas, 157 pasos, 22 slices, S5-D1..D94) en `4e78327`, solo lectura. El crítico no ejecutó `docker`, `bao` ni Compose: lo que depende de su comportamiento queda como supuesto del propio plan (sección 11). Contrastó con `slice-gate.sh`, `wave0-gate.sh`, `compose.yml`, `compose.dev.yml`, `grants.sql`, `0003_crypto.py`, `0001_core_schemas.py`, `cli_ops/*`, `test_cli_base.py`, `test_contact_callers.py`, `test_user_limits_catalog.py`, `ci.yml`, `alerts.py`, `worker/jobs/__init__.py` y `members/models.py`.

## Bloqueante

- **B1. B13 usa `migrate-provider`, que nace en B2.** Plan:757 describe `infra/tests/openbao_restore_e2e.sh` con "migración simulada de una fila … `migrate-provider --verify` → 0" y plan:779 (B13.7.5) lo ejecuta en `apex-smoke`; plan:790 y :792 crean `core/crypto/migration.py` y `cli_ops/migrate_provider.py` recién en B2, y S5-D67 pone B13 antes de B2. Hoy `cli_ops/` no lo tiene. Efecto: el gate Docker de B13 no puede dar verde.
  - **E1:** en B13 el e2e verifica el snapshot sin esa CLI: envuelve una cadena con `bao write transit/encrypt/apex-kek`, restaura el snapshot, desella y descifra con el token de `tools`. La versión con `migrate-provider --verify` pasa a B2.7 y se cita en V3.

## Altos

- **H1. `MIGRATE_DB_USER` y `TOOLS_DB_USER` con `apex_owner` por defecto.** Plan:293 (S5-D89) usa `${MIGRATE_DB_USER:-apex_owner}`; un servidor existente que no defina la variable falla en `migrate` al actualizar porque el rol no existe, y nada lo detecta (ni `deploy.sh` plan:476 ni `test_deploy_script`). El desarrollo no se afecta (`compose.dev.yml:25,41,50` redefine `DATABASE_URL` con `${POSTGRES_USER}`).
  - **E2:** `deploy.sh` comprueba antes de `migrate` que el rol existe, o exige la variable sin valor por defecto en producción; caso en `test_deploy_script.sh` y en `test_db_roles.sh` en modo existente.
- **H2. Tope de 150 líneas por archivo de `cli_ops/`.** `tests/cli/test_cli_base.py:268` lo exige (y :252 fija `cli.py` ≤ 700; hoy 336). Plan:81 (B6.5) mete `notify` y `seed-notifications` en un solo `cli_ops/notify.py`; plan:1186 (B8.1) lo "completa" con `--generate-only`, `--send-only`, `--as` y `claim_run`; plan:792 mete `rotate-kek` y `rotate-kek --trim` en `rotate_kek.py`. Casi seguro superan el tope.
  - **E3:** repartir en `seed_notifications.py`, `notify.py`, `rotate_kek.py` y `trim_kek.py`, con ayudas puras fuera de `cli_ops/`; anotar "menos de 150 líneas" en B2.4, B6.5 y B8.3 y los comandos nuevos en `register_ops`.

## Medios

- **M1. Desfase entre `.env.example`, `ci.yml` y `ratelimit`.** W0-3 mete en `.env.example` las 4 variables `USER_*` y el comentario "16 cubetas y 15 variables" (plan:553), pero las claves de `USER_LIMITS` llegan en B5 y B12 y el `sed`/conteo de `ci.yml` (:365-366, "11 subidas") solo se tocan en B12 (plan:1358).
  - **E4:** registrar las cuatro claves en `USER_LIMITS` ya en W0-3 con `CLAVES_SIN_RUTA_TODAVIA` (`test_user_limits_catalog.py:240-241`); actualizar regex y conteo de `ci.yml` en el mismo checkpoint que `.env.example`.
- **M2. `test_contact_callers.py:106` aserta que el conjunto está vacío** (`test_contact_callers_esta_vacio_en_el_sprint_4a`); el plan (:1040) solo dice "se declara".
  - **E5:** B5.2 reescribe esa prueba nombrándola. Supuesto 17 confirmado: la regla de :113 no exige que exista un llamador.
- **M3. Orden mal escrito en un comando.** Plan:777 usa `$DCE run --rm -f infra/compose.verify.yml backup …`; `-f` no es opción de `run`.
  - **E6:** `$DCE -f infra/compose.verify.yml run --rm backup /opt/backup/run.sh`.
- **M4. Restauración de base como `apex_owner` sin probar.** `restore.sh:140` hace `pg_restore --clean --single-transaction` y no se prueba con propietario no superusuario; `0001_core_schemas.py:39` hace `CREATE EXTENSION btree_gist` (extensión de confianza en PG13+, no debería fallar, pero el plan no lo comprueba).
  - **E7:** W0-4.4 corre `restore.sh` en `apex-smoke` con la pila nueva.

## Observaciones

- Paso 148 (F5.2) dice solo "Verde." sin contenido y no menciona `ForgotPage` ni `users`.
- Hoy `compose.yml:131` y `:106` tienen el worker sin `keys`; el plan monta `keys:ro` en B3 (:912) y a la vez lo quita en el overlay: dejar escrito que el cambio en la base es para `CRYPTO_PROVIDER=local`.
- Plan:1177 crea en B7 un `notify --generate-only` provisional "que se completa en B8": aceptable, pero B7 debe cubrirlo con prueba porque `cli_ops/notify.py` es nuevo.
- `wave0-gate.sh` corre `test_api_image apex-api:local` (:53-55) antes del `buildx` de W0-2.7: funciona con la imagen vieja; anotarlo en el cuaderno.

## Supuestos verificados

Numeración S5-D64..D94 (31 decisiones, sin huecos ni duplicados), pasos 1..157 y conteo 22 slices / 17 checkpoints de backend: confirmados. `slice-gate.sh` mapea `core/<x>` a un solo nivel, `crypto`, `main`, `worker`, `cli`, `architecture`, `<modulo>` y `web/<feature>` (:96-119); `cli_manifest.py` no está en el bucle extra (:112) y B13 lo añade. La guarda de `0003:203-239` bloquea `provider` y `wrapped_material`: `0015` tiene que reemplazarla. `alert(code, **context)` y `ALERT_CONTEXT_KEYS` existen. `memberships/queries.py` existe. `members.data_consent_at` y `status` existen (`members/models.py:79,85`). `apex_worker` tiene hoy `SELECT` completo sobre `members.members` (`grants.sql:92`) y no sobre `crypto_keys`: coincide con W0-3. Las sentencias de esquema de `grants.sql:55-65` son lista fija: `notifications` se añade ahí (plan:1093).

## Cobertura

Sin hueco en US-120..US-139 ni en la demo de 5 puntos (plan:1612-1619). H-1, H-2, M-1..M-12 y L-1..L-9 tienen paso (plan:1588-1600); L-4 aceptado con dueño (el titular). Pasos humanos declarados: custodia 2/2/1, rekey por una segunda persona y firma de la etiqueta.

## Lo que está bien

Orden W0-3 (`0015`) → B1 → B13 → B2, `--first-install`, tokens por servicio y la excepción de `sys/` por ruta exacta; cinco migraciones, una por tabla, con volcado, downgrade y rollback explícitos; smoke de producción en Linux como gate en W0-2, W0-4, B13, B3 y V2 (lecciones D190..D196); rebuild con `buildx` tras cada cambio de `src/` y `stop worker` al editar `worker/`; `smtplib` en `to_thread`, PDF propio, `pypdf` solo en desarrollo y `wa-link` por POST.

## Qué hacer antes de ejecutar

1. Antes de W0-3: E4. Antes de W0-4: E2 y E7. Antes de B13: E1 y E6. Antes de B5: E5. Antes de B2, B6 y B8: E3.
2. Las cuatro observaciones se aplican en sitio (F5.2 con contenido, nota de `keys:ro`, prueba del `notify --generate-only` provisional en B7, nota de `wave0-gate.sh` en el cuaderno).
3. Ejecutar sin otra ronda de crítica: las enmiendas se aplican en el plan en sitio y se citan en las decisiones S5-D95 a S5-D101.
