# Crítica 2 del plan del Sprint 4B (plan-critic) · Veredicto: APROBADO CON OBSERVACIONES

Sobre `docs/ddd/blueprints/sprint-04b-plan.md` (932 líneas) en `280addd`, solo lectura. El crítico no ejecutó `docker`, así que no probó el comportamiento de Compose.

Los tres bloqueantes de la crítica 1 y E1 a E7 están aplicados en los pasos que el plan cita, en sitio, con decisiones nuevas S4B-D97 a D103. Aparecen dos defectos nuevos que no bloquean el diseño pero sí romperían W0-1 y W0-3 en ejecución; sus enmiendas (E8 y E9) se aplican antes de ejecutar el slice afectado.

## Estado de cada hallazgo de la primera crítica

- **B1 (prefijo `pre-restore`): aplicado.** W0-1.2 (plan:258) cubre `valid_prefix`, el esquema, `test_lib`, `test_manifest` y `retention_to_delete`; W0-1.5 (:277-278) hace que `run.sh --prefix pre-restore` no toque `latest.json`; B3a.2 (:576) afirma que `pre-restore-*.json` y su `.minisig` existen antes del `pg_restore`; B2.3 (:525) rechaza un `pre-*` como `latest.json`; S4B-D80 y D97 coherentes.
- **B2 (imagen vieja en `migrate`/`dbsetup`): aplicado.** Sección 0 (:81) y W0-3.10 (:410) reconstruyen siempre; W0-2.7 (:356) no usa servicios sin bind; B2.9 (:554), B3a.7 (:597), B4.10 (:695) y V2 repiten el rebuild. Coincide con `api/Dockerfile:19-21` y con `compose.dev.yml` (sin bind en `migrate`/`dbsetup`).
- **B3 (`test_db_roles.sh` en `images`): aplicado.** W0-3.7 (:395), S4B-D100 y B4.7 lo mueven a `e2e-stack` y `prod-smoke`; `e2e-stack` usa `compose.yml` + `compose.e2e.yml` sin `compose.dev.yml` (`ci.yml:266`), así que sí aplica `dbsetup`.
- **E1, E2, E4, E5, E6: aplicados.** E3 aplicado (`--no-deps` en P-ROL :67, W0-3.11 :415, RUNBOOK y S4B-D99; el `migrate` del ensayo debe mostrar `0013 -> 0014` antes de `dbsetup` :411; `test_compose_config.sh` aserta `depends_on migrate` en producción y el `grep` del RUNBOOK :371). E5: W0-2.2 (:331) limita `tgfoid` a los cuatro triggers de audit, aserción de `crypto_ops` independiente, único efecto real en el texto de `audit.verifications` (coincide con `0002:88-93`, `0013:60-63`, `0003:184-266`). E6: W0-1.11 (:315) corre `slice-gate.sh core/config` antes de `wave0-gate.sh`.
- **E7: parcial.** El orden está bien (`.env.example` no cambia hasta W0-3.5; `test_compose_config.sh:22` y `compose-smoke.sh:18` siguen con un solo `--env-file` en W0-1 y W0-2), pero `.env.ops.example` no sobrevive a un clon limpio (ver H1).
- **Observaciones (8): aplicadas** (`JOBS` y `EXIT_BY_RESULT` :527; fixture `apex_roles` y `psql` real D101; `docker stats` y `stop` D102; `age` en CI D103; `check-ignore`; `check-release-version` sin SHA). Nota: `JOBS` debe devolver `timeout_s` 900 por defecto; hoy `worker/jobs/__init__.py:10` no lo pasa y el plan lo da por supuesto.

## Hallazgos nuevos

**Altos**
- **H1. `.env.ops.example` queda ignorado por git (E7, clon limpio).** `.gitignore:22` ignora `.env.*` y solo `.env.example` y `.env.seed.example` se re-incluyen (:23-24). W0-1.6 (plan:285) lista patrones nuevos y no menciona `!.env.ops.example`. `scripts/ci/check-key-files.sh:21` tampoco lo permite y cae en `.env|.env.*` (:22). Efecto: en local pasa porque el archivo existe en disco, pero `checkpoint-commit.sh` no lo versiona; en CI `test_env_example.py`, `test_compose_config.sh` y el `images` de W0-3 fallan por archivo ausente; un clon limpio en el servidor no lo tiene.
  - **E8:** W0-1.6 añade `!.env.ops.example` a `.gitignore`; `check-key-files.sh` pasa a `.env.example|.env.seed.example|.env.ops.example) ;;`; `test_check_key_files.sh` cubre ambos; W0-1.11 verifica con `git check-ignore -v .env.ops.example` (vacío) y `git status` mostrándolo como no rastreado antes del sello.

**Medios**
- **M1. `backup` en el overlay de desarrollo no está especificado desde W0-3.** W0-3.2 (:371) le fija `PGUSER=apex_backup` y `depends_on dbsetup completed`; W0-3.5 (:389) no lo toca en `compose.dev.yml`, que hoy no tiene entrada para `backup`. En desarrollo `dbsetup` lleva `profiles: ["prod-init"]`: un `depends_on` hacia un servicio de perfil inactivo hace que Compose rechace el proyecto o no arranque `backup`. Además `compose-smoke.sh` (W0-1.6, :286) corre `run.sh` como `backup`; en el overlay de desarrollo de CI no existen los roles y `pg_dump` falla por `apex_backup` inexistente.
  - **E9:** `compose.dev.yml` define `backup` con `depends_on: !override {db: healthy}` y `PGUSER`/`PGPASSWORD` del propietario, igual que `api` y `worker` (S4B-D11); `test_compose_config.sh` aserta en el render de desarrollo que `backup` no depende de `dbsetup` y usa `${POSTGRES_USER}`; ese render valida con `config --quiet`.
- **M2. Entre W0-1 y W0-3 el ensayo manual de `compose.yml` con un solo `--env-file` sale con variables vacías** (`BACKUP_*`, `APEX_*`, `RCLONE_*`: avisos "variable not set"). Fijarlo en W0-1.10.1: "añadir al `.env` de este equipo las claves de `.env.ops.example` con sus valores por defecto".

**Observaciones**
- Riesgo 8 (`psql` 16 con `\getenv`/`\gexec`): `ubuntu-24.04` trae `postgresql-client-16`; fijar la versión con `apt` y añadir `psql --version` previo, como con `age --version`.
- Riesgo 18 (`images` con `.env.ops.example`): `ci.yml:251` hace `cp .env.example .env` y `compose-smoke.sh` copia el segundo si falta; W0-3.7 debe nombrar el `cp .env.ops.example .env.ops` explícito en el job.
- `${BACKUP_SIGN_KEY_FILE:-/dev/null}` (riesgo 7): decidir `compose.sign.yml` opcional o el valor por defecto en W0-1.6 y verificarlo en Docker Desktop en W0-1.10.
- `pre-restore` frente a `backup_check`/`latest.json`: sin contradicción. Rebuild obligatorio: reconciliado en :81 (tachar la mención residual en RUNBOOK §7). `--no-deps` frente a `depends_on` en producción: coherente. `test_db_roles.sh` en `e2e-stack`: coherente.

## Qué hacer antes de ejecutar

1. Aplicar E8 en W0-1.6/W0-1.11 antes del sello de W0-1.
2. Aplicar E9 en W0-3.2/W0-3.5 antes de su Rojo, y añadir al paso 22 la aserción del render de desarrollo.
3. Añadir M2 y las observaciones (`psql --version` y el `cp .env.ops.example` en el job `images`) a W0-1.10 y W0-3.7.
4. Ejecutar sin otra ronda de crítica: la segunda iteración queda cerrada.
