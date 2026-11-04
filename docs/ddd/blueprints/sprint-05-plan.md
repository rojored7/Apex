
# Plan de implementación · Sprint 5 · v0.2: OpenBao, avisos de vencimiento, recibos y exportaciones

> Enmiendas de la crítica 1 aplicadas en sitio: E1..E7 (S5-D95..D101) y cuatro observaciones; veredicto APROBADO CON OBSERVACIONES, sin segunda ronda (`docs/ddd/blueprints/sprint-05-critica-1.md`).

- Rama: `feat/sprint-05-openbao-avisos-recibos`. HEAD de partida: `43641f3` (= `a1ad4cb` de `main` más los documentos de planificación). Última migración aplicada en `apex-db-1`: `0014_audit_log_triggers_always`. Este sprint añade `0015` a `0019` (S5-D66).
- Veredicto de entrada: AMARILLO (`docs/ddd/impacto/sprint-05.md`, `--allow-amber`). Este plan absorbe C1 a C10 (sección 10).
- Entradas leídas: `impacto/sprint-05.md`, `sprint-05-exploracion.md` (5 bloqueantes, 16 hallazgos, 18 preguntas), `sprint-05-blueprint.md` (S5-D1 a S5-D48, E1 a E16), `sprint-05-seguridad-diseno.md` (H-1, H-2, M-1 a M-12, L-1 a L-9; S5-D49 a S5-D63), `docs/scratch/sprint-05.md` (respuestas del orquestador a Q1 a Q10), `SPRINT-05.md`, `DECISIONES.md` (Sprint 4B: estado al cierre, dueños, D56, D77, D93, D98, D103, D190 a D196, D200 a D206), `CLAUDE.md`, `RUNBOOK.md` §7, `scripts/workflow/{slice-gate,checkpoint-commit,run-gates,wave0-gate}.sh`, `infra/compose*.yml`, `infra/db/grants.sql`, `api/pyproject.toml`, `.github/workflows/ci.yml`, `web/src/config/features.ts`, y como modelo `sprint-04b-plan.md`.
- Mandan este plan y su sección 1. Donde el plan y el blueprint choquen manda el plan; donde blueprint y revisión de seguridad choquen manda la revisión salvo que la sección 1 diga otra cosa con motivo. La sección 1 se copia a `DECISIONES.md` ("Sprint 5 · decisiones de implementación") en el checkpoint de S5-W0-1.
- Decisiones del orquestador incorporadas tal cual: PDF propio en `core/pdf.py` sin `reportlab` ni `pillow` (`pypdf` solo en desarrollo); una llave Transit `apex-kek`; `apex_owner` en W0-4, obligatorio y también para `tools` (M-12); sin `data_consent_at` no se avisa por ningún canal (los socios afectados se listan aparte); recibo sin documento; `members_without_consent` calculado; la auditoría de exportación guarda `has_q` y filtros estructurados; `display_name` pasa a v0.3; B13 (respaldo de OpenBao) entra en el sprint y bloquea `migrate-provider` (H-1); custodia de las llaves de desellado 2 titular / 2 operador / 1 copia sellada en un tercero.
- Doctrina: TDD por slice, deuda cero (todo HIGH y MEDIUM es un paso; todo LOW se corrige o se acepta con dueño) y ejecución al 100 %. Paradas de la doctrina más las propias del sprint:
  - `migrate-provider`, `rotate-kek`, `rotate-kek --trim` o `retire-local-kek` fuera de `db_test`, `*_sim`, `apex-ensayo` o `apex-smoke`;
  - cualquier escritura en `apex-db-1` fuera de P-MIG y de P-ROL en V2;
  - `down -v` fuera de `apex-ensayo` y `apex-smoke`;
  - inicializar OpenBao con llaves reales (paso humano);
  - enviar correo o Telegram reales desde el flujo.

## 0. Convenciones comunes a todos los slices

**Alias y entorno.** Todo desde Bash:

- `DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"`: desarrollo, proyecto `apex`.
- `DCE="docker compose -p apex-ensayo --env-file docs/scratch/ensayo/.env --env-file docs/scratch/ensayo/.env.ops -f infra/compose.yml"`: ensayo de producción, puerto 8280, subred `172.31.2.0/24` (S5-D77).
- `DCEB="$DCE -f infra/compose.openbao.yml"`: ensayo ya migrado a OpenBao, desde B2.
- `apex-smoke`: lo maneja `scripts/ci/prod-smoke.sh`, puerto 8380, subred `172.31.3.0/24`.
- Pruebas del api: `TEST_DATABASE_URL=postgresql+asyncpg://apex:apex-test@127.0.0.1:5443/apex_test` exportada en cada comando; `uv` vive en `~/.local/bin`; siempre `127.0.0.1`.
- Puertos de desarrollo: 8180 (web), 8181 (api), 5442 (db), 5443 (db_test).
- Las variables de la shell no persisten entre llamadas.

**Cuadernos.** `docs/scratch/sprint-05.md` (backend y orquestador) y `docs/scratch/sprint-05-front.md` (worktree). Cada slice deja cuatro bloques:

- Rojo: línea base, conteo y motivo de cada fallo.
- Verde: conteo, desviaciones numeradas, cobertura por archivo.
- Revisiones: conteos C/H/M/L y la decisión que cierra cada hallazgo.
- Evidencia: primer bloque del slice siguiente o commit `docs(sprint-05): evidencia de S5-<slice>`.

Las pruebas saltadas (`age`, `pty`, `openbao` real, modos POSIX) se cuentan por archivo, con el motivo y el sitio donde sí corrieron (contenedor Linux o CI). Nunca se marca verde lo saltado.

**Ciclo estándar de un slice** (los pasos de cada slice solo dicen lo propio):

1. Stubs con `NotImplementedError` y Rojo, por `backend-qa-executor` o `frontend-qa-automation` en Sonnet. Se confirma el rojo con conteo.
2. Verde, por `backend-implementor` o `frontend-ux-engineer` en Sonnet, corriendo gates no sellantes (`slice-gate.sh` de los módulos tocados, salvo el último).
3. `database-reviewer` (si hay migración o grants) y `security-reviewer` en Fable, en paralelo. El Verde corrige todo hallazgo CRITICAL, HIGH o MEDIUM; los LOW se corrigen o se aceptan con dueño (decisión numerada).
4. P-API si cambió el contrato.
5. Documentación y bloque del cuaderno.
6. Gate sellante al final.
7. Docker y evidencia, sin tocar el árbol (si obliga a cambiar código, se vuelve a 2 y se resella).
8. Checkpoint: `CHECKPOINT_TRAILER='Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>' bash scripts/workflow/checkpoint-commit.sh "S5-<id> <resumen>"`, más `git commit -m "docs(sprint-05): evidencia de S5-<id>" -m 'Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>'`, verificado con `git log -1 --format=%B`.

Antes de cada línea de gate con lista se corre `ls` de cada archivo. `PYTEST_ADDOPTS="-m 'not perf'"` en todos los gates. `tests/architecture` corre en cada gate.

### Agentes por slice

- Rojo y Verde: como en el ciclo estándar.
- `devops-wsl2-docker`: W0-2, W0-3, W0-4, B13, B3 (Compose, imágenes, ensayo, smoke) y la evidencia Docker de cada slice; es quien ejecuta buildx y los proyectos aparte.
- `database-reviewer`: W0-3 (`0015`, grants por columna), W0-4 (`apex_owner`), B5 (`0016`), B6 (`0017`, `0018`), B7 (`0019`) y V8.
- `security-reviewer`: todos los slices salvo B10, más V10 sobre el árbol fusionado.
- `plan-critic`: este plan, antes de W0-1 (Fase 2.5).
- Un slice no empieza hasta el checkpoint del anterior en la misma rama. El front sigue la sección 3.

### Mapeo de `slice-gate.sh` (verificado en HEAD, líneas 96 a 121)

- `core/<x>` exige `src/app/core/<x>.py` o `src/app/core/<x>/`, un nivel. Valen `core/config`, `core/logging`, `core/health`, `core/errors`, `core/alerts`, `core/jobs`, `core/backup_status`; y `core/mail`, `core/alerts_telegram`, `core/export`, `core/pdf` en cuanto el Rojo crea el stub.
- `crypto` cubre `src/app/core/crypto/` entero (`openbao_provider`, `state`, `recovery`, `migration`, `minisign`).
- `main` → `main.py`. `worker` → `src/app/worker/`.
- `cli` → `cli.py`, `cli_base.py`, `cli_ops/`, `seed/`, `imports/`. `cli_manifest.py` (S5-D72) **no** está en esa lista: B13 lo añade al bucle `extra` del caso `cli`, con su caso en `scripts/workflow/tests/test_slice_gate.sh`.
- `<modulo>` → `src/app/modules/<modulo>`: `notifications` vale desde el stub de B6.
- `web/<feature>`, `web/shared`, `web/core`, `web/app`.
- Ningún módulo nuevo más hay que mapear (E16 respondida).
- `wave0-gate.sh` y `run-gates.sh` suman `test_openbao_infra` a su lista de scripts (W0-2). Las combinaciones de `wave0-gate.sh` suman `-f infra/compose.openbao.yml`, `--profile bootstrap`, `--profile openbao -f compose.dev.yml` y `--profile avisos -f compose.dev.yml`, con su caso en `scripts/workflow/tests/test_wave0_gate.sh`.

### Memoria del equipo

- Suite completa del api: nunca junto a vitest o Playwright. Fuera de `run-gates.sh` se corre en tres partes:
  - `tests/architecture tests/core tests/crypto tests/auth tests/settings tests/migrations`;
  - `tests/cli tests/worker tests/members tests/plans tests/memberships`;
  - `tests/payments tests/audit tests/dashboard tests/notifications tests/integration`.
- Para la cobertura: `--cov=app --cov-append` en las tres partes, con `coverage report --fail-under=80` al final.
- `run-gates.sh` se corre al cerrar B3, B8, B12 y V9, en primer plano, con el ensayo detenido (`docker compose -p apex-ensayo stop`, nunca `down -v`). Si muere la parte web, se repite solo esa parte en primer plano.
- `docker stats --no-stream` al cuaderno en W0-1, W0-2, B3 y antes de cada `run-gates.sh`.
- El ensayo con OpenBao suma un contenedor. El `openbao` de desarrollo vive bajo perfil (`--profile openbao`) y solo se levanta cuando un paso lo usa.

### P-MIG · Migración nueva (`0015` a `0019`)

1. Volcado: `$DC exec -T db pg_dump -U apex -Fc apex > docs/scratch/sprint-05-antes-00NN.dump` (`*.dump` ignorado, comprobado con `git check-ignore -v`). Se borra en V12.
2. `$DC stop api` mientras se redacta. Si la migración afecta tablas que lee el worker, también `$DC stop worker`; desde `0017` siempre, porque `notify` existe a partir de B8.
3. Escribir `api/migrations/versions/00NN_<tema>.py` y `api/tests/migrations/test_00NN_<tema>.py`. `migrations/env.py` importa los modelos nuevos (B6).
4. Contra `db_test`: `cd api && uv run pytest tests/core/test_migrations.py tests/migrations -q`, con el ciclo `head → base → head`.
5. `cd api && uv run alembic heads`: una sola cabeza.
6. `$DC start api` (y `worker`); esperar `healthy`; `$DC exec api alembic current` = `00NN (head)`. Es la única forma en que la migración llega a `apex-db-1`.
7. `$DC exec api alembic downgrade -1 && $DC exec api alembic upgrade head && $DC exec api alembic current`.
8. Esquema de solo lectura: `$DC exec -T db psql -U apex -d apex -c '\d <tabla>'` (más `\df+ crypto.guard_keys_update` en `0015`) y la consulta de `tgenabled` de 4B (los diez triggers en `A`, más los nuevos si los hubiera). Al cuaderno.
9. La prueba de la migración anterior pasa de "es head" a "está en la cadena de head" (`test_0014_*.py` en W0-3, y así sucesivamente).

### P-ROL · Grants

- Cada slice que cambia `grants.sql`:
  - actualiza en el mismo paso las tres listas (matriz, `-- clasificada:` y `ARRAY clasificadas`, S4B-D201), `revoke.sql` (esquema `notifications`) y `tests/migrations/test_db_grants.py` (`PRIVILEGIOS`);
  - prueba sobre `apex_roles` en `db_test`, con el ciclo `apply → revoke → apply`;
  - corre `dbsetup` en `apex-ensayo` y `bash scripts/ci/test_db_roles.sh` con `DC="$DCE"`.
- `apex-db-1` recibe `dbsetup` una sola vez, en V2: `$DC --profile prod-init run --rm --no-deps dbsetup`, con `--no-deps` obligatorio (S4B-D99). En desarrollo el api y el worker corren como propietario (S4B-D11), así que no dependen de los grants.

### P-API · Contrato (B3, B4, B5, B6, B7, B9, B10, B11, B12)

`cd api && uv run python -m app.cli export-openapi ../docs/openapi.json`, después `cd web && npm run gen:api && npx vitest run src/core/api/types.contract.test.ts`. Se exporta dos veces y debe salir idéntico. Los dos archivos entran en el checkpoint del slice. Solo el backend toca `types.ts`; el worktree hace rebase antes de cada F.

### P-BAO · OpenBao: desellar, sellar, snapshot (nuevo)

**Desarrollo.**

- `$DC --profile openbao up -d openbao`. `infra/openbao/dev-entrypoint.sh` inicializa con 1 de 1 en el volumen `openbao-dev-data` (nunca `openbao-data`), desella, corre `bootstrap.sh` con `BOOTSTRAP_NONINTERACTIVE=1` solo si `APEX_ENV=dev`, y vuelve a desellar en cada reinicio.
- Sellar: `bash scripts/dev/openbao-seal.sh` (usa la raíz de desarrollo del propio volumen).
- `bao` no existe en el host; todo pasa por `$DC exec -T openbao bao ...`.

**Ensayo y smoke (producción, 5 de 5 con umbral 3).**

- Inicialización: `$DCE --profile bootstrap run --rm -T openbao-bootstrap --first-install`.
  - La confirmación `INICIALIZAR` y las respuestas van por stdin.
  - La salida (5 llaves) se redirige a `docs/scratch/ensayo/openbao/init.txt`, carpeta ignorada, con `chmod 600`.
  - Nunca al cuaderno ni a los logs (el servicio lleva `logging: none`).
- Desellar: tres veces `$DCE exec -T openbao bao operator unseal -`, con la llave por stdin (supuesto verificado en W0-1.1). Si `-` no lee stdin, la alternativa escrita es `PUT /v1/sys/unseal` desde un contenedor de `custody` con el cuerpo en un archivo 600 de `tmpfs`.
- Sellar como en la demo: `$DCE restart openbao`. El almacenamiento raft sin auto-desellado queda sellado; no hace falta raíz.
- "Reinicio de servidor": `$DCE restart openbao && $DCE restart api worker` (S5-D69).
- Snapshot: `$DCE run --rm backup /opt/backup/run.sh` (B13).
- Restauración: `infra/tests/openbao_restore_e2e.sh` en el proyecto `apex-smoke`. Necesita `generate-root` con 3 llaves efímeras; se documenta así en `docs/operacion/openbao.md`.
- Reemitir tokens: `bootstrap.sh --reissue-tokens`, después de desellar.
- Las llaves del ensayo se borran en V12.

**Producción real.** La inicialización y la custodia son pasos humanos (S5-D82).

### P-MAIL · Correo y Telegram en desarrollo (nuevo)

- Mailpit solo existe en `compose.dev.yml` (perfil `avisos`, SMTP `mailpit:1025`, `SMTP_TLS_MODE=none`, aceptado solo con `ENV=dev`). Su interfaz está en `127.0.0.1:8025`.
- Leer: `curl -s http://127.0.0.1:8025/api/v1/messages`. Vaciar: `curl -s -X DELETE http://127.0.0.1:8025/api/v1/messages`.
- `telegram-fake` (perfil `avisos`) recibe en `http://telegram-fake:8081/bot<token>/sendMessage` y escribe el cuerpo JSON en su stdout. Se lee con `$DC logs telegram-fake`.
- `TELEGRAM_API_BASE` solo admite una base distinta de `https://api.telegram.org` con `ENV=dev` (S5-D78).
- El token de prueba es un valor fijo de prueba; no es un bot real.
- Nunca SMTP real ni un bot real desde el flujo; el ensayo corre sin Telegram (sink de log) y sin SMTP (canal `email` sin credenciales).

### Docker y quirks (RUNBOOK §7)

- `docker compose build` y `up --build` están rotos en este equipo. Se construye con:
  - `docker buildx build --load --network host --allow network.host -t apex-api:local -f api/Dockerfile api`;
  - `... -t apex-web:local -f web/Dockerfile .`;
  - `... -t apex-backup:local -f infra/backup/Dockerfile infra/backup`;
  - se levanta con `up -d --no-build` (y `--force-recreate web` si cambia la imagen web).
- `openbao`, `mailpit` y `python:3.12-alpine` se descargan con `docker pull <imagen>@sha256:...` (W0-1.1 fija los digests).
- **S4B-D98:** todo cambio en `api/src` o `api/migrations` exige reconstruir `apex-api:local` antes de usar `migrate`, `dbsetup`, el ensayo o el smoke. El ensayo se recrea con `--force-recreate`.
- api de desarrollo: bind con `--reload`; una migración exige P-MIG; `restart api` después de migrar (el `lifespan` no se repite con `--reload`).
- worker: bind sin reload. `$DC stop worker` mientras se edita `app/worker/`, `core/jobs.py`, `modules/notifications/` o `members/contact.py`; `$DC restart worker` en el checkpoint.
- `apex-db-1`: solo `SELECT`, `\d` y sentencias que deben fallar dentro de `BEGIN; ... ROLLBACK;`.
- Smoke de producción en Linux (gate de W0-2, W0-4, B13, B3 y V2): `prod-smoke.sh` corre en un contenedor auxiliar `docker:cli`, con el socket montado, el volumen del árbol montado en su propio Mountpoint y `--network host`. El clasificador bloquea reiniciar Docker Desktop: no se intenta.
- Los agentes Sonnet pierden las barras invertidas en los heredocs: toda regex, todo `.hcl` y todo `.sh` con `\` se escriben con Write, y el orquestador los revisa con Grep después de cada edición de un agente (lista en el cuaderno).
- El hook `config-protection` puede bloquear `pyproject.toml`: las dependencias se cambian con `uv add`; los marcadores de pytest (`openbao`) con una edición mínima anotada.
- gitleaks, `pip-audit` y `npm audit` como en 4B (V9). Ningún literal de llave de desellado, token `hvs.`/`s.`, `AGE-SECRET-KEY-1` ni token `bot<digitos>:` realista en pruebas ni documentos (los literales se parten).

## 1. Bloque "Sprint 5" para `docs/ddd/DECISIONES.md`

Formato del bloque 4B:

- `Fuente:`;
- contradicciones resueltas;
- S5-D1 a S5-D48 en forma final;
- S5-D49 a S5-D63 con la opción final;
- S5-D64 a S5-D101 de este plan;
- contradicciones de contrato cerradas en T-DOC;
- un bloque por slice que añade cada checkpoint.

### Contradicciones resueltas

1. **D2 (una llave Transit) frente a US-133 (una por `data_class`).** Manda D2, aceptada por el orquestador y por la seguridad (§4): un token abre todas las clases de todos modos. El puerto conserva `wrap(dek)` y `unwrap(wrapped)`. US-133 y US-134 se enmiendan en T-DOC.
2. **D8 (B13 "si cabe") frente a H-1.** Manda la seguridad. B13 entra antes de B2 (S5-D67). `migrate-provider` (salvo `--dry-run`), `rotate-kek` y `retire-local-kek` exigen un manifiesto firmado de menos de 24 h con `openbao_snapshot.verified = true`. `bootstrap.sh` solo crea `apex-kek` con `--first-install`.
3. **D18 (retirar la KEK local por paso humano) frente a H-2.** Manda la seguridad: `compose.openbao.yml` sin `keys` en api y worker, `retire-local-kek`, `prod-smoke` comprueba que no hay `kek.bin` en esos servicios y `deploy.sh` avisa si queda.
4. **D11 (políticas amplias, tokens de 768 h) frente a M-2.** Manda la seguridad:
   - api: `encrypt` y `decrypt` de `apex-kek` más `renew-self`;
   - worker: solo `decrypt` más `renew-self`;
   - tools: añade `rewrap`, `rotate` y `config`, nunca `delete` ni `trim`;
   - rotación de los tres tokens cada 90 días (RUNBOOK).
   La firma con Transit (`sign`/`verify`) queda solo en la suite de contrato con el token de pruebas; ninguna política de servicio la concede en v0.2.
5. **D10 (ninguna política toca `sys/*`) frente a D8 (snapshot en `sys/storage/raft/snapshot`).** Se precisa en S5-D75: una sola excepción, por nombre y ruta exacta.
6. **D12 (volumen de desarrollo con el mismo nombre que producción) frente a M-3.** Manda la seguridad: volumen `openbao-dev-data`, guarda `APEX_ENV=dev`, y `compose.yml` no puede contener `dev-entrypoint`, `BOOTSTRAP_NONINTERACTIVE` ni `openbao-seal`.
7. **D13 (`/health` llama `try_load`) frente a M-4.** Manda la seguridad: `try_load` solo desde el sondeo (S5-D70). `refresh_current` tolera `CryptoUnavailable`. `_startup` degrada solo ante `sealed|unreachable`.
8. **D20 (`Keyring.load_all` completo en el worker) frente a M-6.** Manda la seguridad: el worker carga solo `member.phone` y `member.email`, y `notify` toma `claim_run('notify')` también desde el CLI.
9. **D26 (`INSERT ... ON CONFLICT`) frente a M-6 y al hallazgo 6 de la exploración.** Manda la seguridad: inserción por ORM con `begin_nested` (S5-D71).
10. **D27 (`GET /notifications/{id}/wa-link`) frente a M-9.** Manda la seguridad: `POST`, con `useMutation` y `gcTime: 0`. `ROUTES.md` y el contrato se enmiendan en T-DOC.
11. **D36 (`export` 5/min y 20/h) frente a M-10.** Manda la seguridad: `export` 2/min, `export-hour` 6/h, `export-day` 20/día, un flujo por usuario, fila de cierre (S5-D81, D82).
12. **D40 y D43 (`reportlab`, logo PNG) frente a Q1 y M-11.** Manda el orquestador: `core/pdf.py` propio, sin logo (S5-D65).
13. **D28 (`aiosmtplib`) frente a la exploración, hallazgo 17.** Manda este plan: `smtplib` de la biblioteca estándar en `asyncio.to_thread` (S5-D64).
14. **D6 (`tools` con `POSTGRES_USER`) frente a M-12.** Manda la seguridad: `tools` y `migrate` usan `apex_owner` en pilas nuevas. Los servidores existentes conservan su propietario por `MIGRATE_DB_USER` y `TOOLS_DB_USER` (S5-D89).
15. **D5 (`0017` con dos tablas) frente a la regla "una migración por tabla".** Cinco migraciones (S5-D66).
16. **D10 (`openbao` sin perfil, también en desarrollo) frente a la memoria del equipo y a `test_compose_config.sh` (`depende(dev, api) == {db}`).** En desarrollo, perfil `openbao` y `depends_on: !override` (S5-D68).
17. **D22 (recuperación en 40 s o menos) frente a US-136 (30 s).** Sondeo de 20 s y caché de 5 s (S5-D70).
18. **D8 (`wget --header` con el token en `argv`) frente a L-2.** `curl -K` con un archivo 600 en `tmpfs` (B13).

### Decisiones del blueprint (S5-D1 a S5-D48) en forma final

Se copian como están en `sprint-05-blueprint.md` §1, con estas enmiendas:

- **D1:** orden con B13 tras B1 (D67).
- **D3:** se confirma que manda la columna `provider`; el prefijo (`apxw1`/`vault:`) solo se comprueba como coherencia (exploración P1).
- **D5:** reemplazada por D66.
- **D8:** `curl -K` (L-2), raft, firma verificada (D72).
- **D11:** políticas de M-2 y `--first-install` (D76).
- **D12:** volumen `openbao-dev-data` y perfil `openbao` (D68).
- **D13:** `try_load` solo por sondeo y caché de 5 s (D70).
- **D14:** "al reiniciar" según D69.
- **D15:** sin cambio. Se confirma que `deploy.sh` sale 0 con el aviso de sellado.
- **D16:** `CRYPTO_RECOVERY_POLL_S=20` (D70).
- **D17:** `TELEGRAM_API_BASE` se suma a los ajustes (D78).
- **D18:** precondiciones de H-1 vía `cli_manifest` (D72); `retire-local-kek` (D73).
- **D19:** `--trim` en un paso aparte (M-5b).
- **D20:** clases limitadas (M-6). La duda de `FOR SHARE` (E6) se resuelve en B3.3: si descifrar la exige, se concede `UPDATE (updated_at)` al worker con decisión del slice.
- **D21:** `aiosmtplib` → `smtplib`; `reportlab` → `core/pdf.py`.
- **D22:** `openbao-smoke.sh` reinicia api y worker tras `openbao` (D69).
- **D25:** sin cambio.
- **D26:** ORM (D71).
- **D27:** `POST` (D59).
- **D28:** `smtplib` y `EmailMessage` (D64, D57).
- **D29:** tarea que atrapa todo (D58) y `TELEGRAM_API_BASE` (D78).
- **D35:** `claim_run` compartido y `sellado` como detalle (D86).
- **D36:** D81.
- **D40:** sin logo, PDF propio (D65).
- **D41:** paginación por llave `(created_at, id)` y `(paid_at, id)`, tope de 20.000 filas, fila de cierre (D82).
- **D43:** sin dependencias nuevas de ejecución; `pypdf` en desarrollo; casos de control `fpdf2` y `python-telegram-bot` rechazados.
- **D44:** suma `TELEGRAM_API_BASE`, `APEX_CUSTODY_SUBNET`, `BACKUP_SIGN_PUBKEY` (pasa a `Settings` para D72), `MIGRATE_DB_USER`, `TOOLS_DB_USER`, `APEX_OWNER_DB_PASSWORD`.
- **D47:** sin cambio (ninguna arista `auth → notifications`).
- **D48:** ADR-005 nace en W0-1.

### Decisiones de seguridad (S5-D49 a S5-D63) con la opción final

Todas aceptadas tal como las propone `sprint-05-seguridad-diseno.md`, con estas precisiones:

- **D49 (H-1):** la verificación es criptográfica (D72).
- **D50 (H-2):** `retire-local-kek` según D73.
- **D52 (M-2):** excepción del snapshot según D75.
- **D54 (M-4):** primera opción, sin `try_load` en `/health`.
- **D55 (M-5):** (a) se verifica en B1.7 con OpenBao real; si `rewrap` no admite AAD, `rotate-kek` usa `decrypt` y `encrypt` en `tools` con `bytearray` puesto a cero.
- **D57 (M-7):** con `smtplib`.
- **D59 (M-9):** `POST`.
- **D60 (M-10):** según D81 y D82.
- **D61 (M-11):** Courier.
- **D62 (M-12):** según D89.
- **D63:** L-1, L-2, L-3, L-5, L-6, L-7, L-8 y L-9 corregidos o documentados en su paso (sección 10). L-4 (retención de `rendered_body`) queda aceptado con dueño v0.3, titular.

### Decisiones de este plan (S5-D64 en adelante)

- **S5-D64 · Correo con `smtplib`.** `core/mail.py`: `send_mail(settings, message) -> MailResult` corre `smtplib.SMTP` o `SMTP_SSL` en `asyncio.to_thread`, con `timeout=NOTIFY_NET_TIMEOUT_S`, `starttls(context=ssl.create_default_context())` y `EmailMessage` con `Address`. `smtplib` queda confinado a `core/mail.py`. Sin dependencia nueva (cumple C5 sin `aiosmtplib`).
- **S5-D65 · PDF propio.** `core/pdf.py`: `render_text_pdf(lines: Sequence[PdfLine], *, title: str) -> bytes`, una página A4, Courier de las 14 fuentes estándar sin incrustar, WinAnsi, cadenas hexadecimales, `xref` y `/Length` calculados, 100 KB como máximo. El recibo va sin logo; BRECHAS §13 lo anota con dueño v0.3, titular (vector propio o licencia aceptada).
- **S5-D66 · Migraciones.** `0015_crypto_provider_migration`, `0016_member_channel_preferences`, `0017_notification_templates` (con `CREATE SCHEMA notifications`), `0018_notification_rules`, `0019_notifications`. Sin `0020`.
- **S5-D67 · Orden.** W0-1, W0-2, W0-3, W0-4, B1, B13, B2, B3, B4, B5, B6, B7, B8, B9, B10, B11, B12. El front según D84.
- **S5-D68 · `apex-db-1` sigue `local` todo el sprint.** En desarrollo, `openbao` va bajo el perfil `openbao` con `dev-entrypoint.sh` y el volumen `openbao-dev-data`; `api`, `worker` y `tools` de desarrollo con `depends_on: !override {db: service_healthy}`. Las operaciones de proveedor solo se ejercen en `db_test`, `*_sim`, `apex-ensayo` y `apex-smoke`.
- **S5-D69 · "Al reiniciar" de la demo.** Es el reinicio simulado del servidor: `restart openbao` y después `restart api worker`. Además se demuestra que sellar con el api arriba no corta lecturas, pero `/health` dice `sealed` (L-1: el interruptor de emergencia es revocar tokens y reiniciar).
- **S5-D70 · Tiempos de recuperación.** `CRYPTO_RECOVERY_POLL_S=20`, `HEALTH_CACHE_TTL_S["crypto"]=5`: recuperación visible en 25 s o menos. `/health` solo lee el estado del proceso y `status()` del proveedor, nunca `try_load`.
- **S5-D71 · Generación auditada por ORM.** Por lote de 200 candidatos: se consultan las claves existentes `(rule_id, membership_id, target_date)`, se hace `session.add(Notification(...))` por cada nueva dentro de `begin_nested()`, y un `IntegrityError` cuenta como ya existente. `NotificationQueued` se emite después del flush. Cada fila deja su `insert` en `audit_log`.
- **S5-D72 · Firma del manifiesto verificada en Python.**
  - `core/crypto/minisign.py`: `parse_pubkey(text) -> MinisignKey`, `verify_minisign(key, data: bytes, sig_text: str) -> bool`. Ed25519 sobre BLAKE2b-512 (algoritmo `ED`); el `Ed` heredado se rechaza; el comentario de confianza se verifica.
  - `app/cli_manifest.py` (capa de aplicación, como `cli_keyring.py`): `recent_signed_manifest(base: Path, now: datetime, pubkey: str, *, require_openbao_snapshot: bool) -> ManifestCheck`.
  - Lo usan `retire-key` (que deja de mirar solo la existencia de `.minisig`), `migrate-provider`, `rotate-kek` y `retire-local-kek`; `backup_check` verifica la firma por el bus.
  - `BACKUP_SIGN_PUBKEY` pasa a `Settings` (no es secreta).
  - Cierra D57, D80 y D149 en v0.2, su dueño original.
- **S5-D73 · `retire-local-kek`.** `cli_ops/retire_local_kek.py`: `retire-local-kek --as <correo> [--yes]`.
  - Precondiciones: `migrate-provider --verify` en 0 (ninguna fila `encrypt|index` `local`), `recent_kek_verify` de una persona en menos de 24 h, `recent_signed_manifest(require_openbao_snapshot=True)`.
  - Confirmación escrita `RETIRAR`. Después, `os.unlink` de `kek.bin` en el volumen `keys`, que bajo `compose.openbao.yml` solo monta `tools`.
  - Auditoría `update` sobre `crypto.crypto_keys` con `record_id=None` y `after={"kek_local":"retirada"}`. Sin fila en `crypto_ops`: ningún verbo de `OP_VERBS` aplica y su CHECK no se toca.
  - Las filas `sign` siguen `local` como referencia (D9) y no necesitan el archivo.
- **S5-D74 · `infra/compose.openbao.yml`.** `api` y `worker` con `volumes: !override` sin `keys` y con su token. Los volúmenes de token existen en `compose.yml` (vacíos e inertes con `local`). `deploy.sh` exige el archivo cuando `.env` dice `CRYPTO_PROVIDER=openbao` y avisa si `kek.bin` sigue en `keys`.
- **S5-D75 · Excepción `sys/` del snapshot.** `apex-backup-snapshot` es la única política con una ruta `sys/`: `path "sys/storage/raft/snapshot" { capabilities = ["read"] }`, exacta. `test_openbao_infra.sh` la admite por archivo y ruta y rechaza cualquier otra.
- **S5-D76 · `bootstrap.sh`.** `--first-install` más `INICIALIZAR` para crear `apex-kek` sobre un volumen vacío; sin eso aborta con "volumen de OpenBao vacío: restaurar snapshot". `--reissue-tokens` reemite los cuatro tokens. Umbral mínimo de 3 de 5, comprobado. La raíz nunca se imprime y se revoca al final.
- **S5-D77 · Redes.** `custody` con `internal: true` y subred `${APEX_CUSTODY_SUBNET:-172.30.1.0/24}`; ensayo `172.31.2.0/24` (`custody` `172.31.12.0/24`); smoke `172.31.3.0/24` (`172.31.13.0/24`). W0-1.1 comprueba que están libres.
- **S5-D78 · Telegram simulado.** `TELEGRAM_API_BASE` en `Settings` (`https` obligatorio salvo `ENV=dev`); servicio `telegram-fake` (`python:3.12-alpine@sha256`, `scripts/dev/telegram_fake.py` montado `:ro`, sin puertos, perfil `avisos`) y Mailpit en el mismo perfil.
- **S5-D79 · Evidencia de `notify` con correo.**
  - Va contra la base `apex_avisos_demo` creada en `db_test`, con `-e DATABASE_URL=...apex_avisos_demo` por comando. `seed --demo` admite `*_demo`. Nunca contra `apex`.
  - Las preferencias y el consentimiento de los dos socios de prueba se fijan por `PATCH` contra un api efímero apuntado a esa base: `$DC run --rm -p 127.0.0.1:8191:8000 -e DATABASE_URL=... api`.
- **S5-D80 · `members_without_consent`.** Se llena en B10 con `members.service.count_without_consent(session) -> int` (Q6).
- **S5-D81 · Cubetas.** `notifications-write` 30/min; `export` 2/min; `export-hour` 6/h; `export-day` 20/día. Variables `USER_NOTIFICATIONS_WRITE_LIMIT_PER_MIN`, `USER_EXPORT_LIMIT_PER_MIN`, `USER_EXPORT_LIMIT_PER_HOUR`, `USER_EXPORT_LIMIT_PER_DAY`. El catálogo pasa a 16 cubetas y 15 variables (comentario de `.env.example`, `test_env_example.py`, el `sed` de `ci.yml`). `POST wa-link` usa `members-reveal*`.
- **S5-D82 · Exportación.** `core/export.single_flight(user_id)` en memoria (un solo proceso del api, RUNBOOK §1) → 409 `export_in_progress`. Fila `export` inicial y fila de cierre (`completed`, `rows_sent`) en `finally` con sesión propia.
- **S5-D83 · Destino de la deuda del 4B.**
  - W0-3: D202 (`INSERT` de `payments.payments` por columna sin `void_reason`, `voided_by`, `voided_at`), D203 (`UPDATE` por columna en `auth.users`, del inventario de asignaciones de `modules/auth`), D204 (`SELECT` por columna de `members.members` para `apex_worker` y `load_only` en sus caminos).
  - W0-4: D206. B2: D137, D148, D151. B13: D57, D80, D149. B3: alerta `crypto_sealed`.
  - v0.3 con dueño: Caddy y TLS, también en `custody` (D45, D66; titular, EP-20); `audit.append()` y residuales de `INSERT` (D61; tras `sign-audit`); `display_name` (titular); índices de `audit_log` (D5, solo si V7 lo pide); AppRole (operador); retención de `rendered_body` (L-4, titular).
  - Firma de etiquetas (D181, D208): paso humano del titular en V12; si no firma, pasa a v0.3 con el titular como dueño.
- **S5-D84 · Worktree del front.**
  - `.claude/worktrees/sprint-05-front` (rama `feat/sprint-05-front`), creado desde el checkpoint de B10. Orden F1, F2, F3, F5; F4 después del checkpoint de B12, con `git rebase feat/sprint-05-openbao-avisos-recibos`.
  - `SLICE_BASE=$(git merge-base HEAD main)` en cada comando del worktree.
  - Los comandos pesados (suite del api, vitest, Playwright, buildx) nunca corren a la vez en los dos árboles; lo anota el cuaderno.
  - Fusión única en V1, con el árbol principal limpio tras un checkpoint.
- **S5-D85 · CI.**
  - El job `api` suma `services.openbao` (imagen fijada, `server -dev`, token fijo de CI) y exige 0 saltos del marcador `openbao` (patrón D103).
  - `prod-smoke` ejecuta `openbao-smoke.sh`.
  - `e2e-stack` sigue con `CRYPTO_PROVIDER=local` y `openbao` inerte.
  - `images` corre `test_backup_apk_pins.sh` con el pin nuevo de `curl`.
- **S5-D86 · Sin `skipped` ni `needs_crypto`.** `notify` registra `ok=True` y `details["sellado"]=1` cuando omite `send`; `RESULTS` y `JobSpec` no cambian.
- **S5-D87 · Descargas en el front.** `api.blob(path, {timeoutMs})` en `web/src/core/api/client.ts` (120 s para CSV, 30 s para PDF) y `downloadBlob(blob, nombre)` en `web/src/shared/lib/download.ts`, sin `sessionStorage` ni `localStorage` (L-8).
- **S5-D88 · `test_openbao_infra.sh`.** Parsea `.hcl` con `grep`/`awk` (sin `jq`).
- **S5-D89 · `apex_owner` en pilas nuevas.** `infra/db/initdb/10-apex-owner.sh`, montado `:ro` en `db` como `/docker-entrypoint-initdb.d/10-apex-owner.sh`; solo corre con el volumen vacío. Crea `apex_owner` (`LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE`), le pasa la propiedad de la base y le da `REVOKE CREATE ON SCHEMA public FROM PUBLIC`. `migrate` usa `${MIGRATE_DB_USER:-apex_owner}` y `tools` `${TOOLS_DB_USER:-apex_owner}`; un servidor existente fija ambos al propietario actual (RUNBOOK §12, `REASSIGN OWNED` como paso humano).
- **S5-D90 · Proyectos aparte.** `apex-ensayo` nace en W0-2 y vive hasta V12; `apex-smoke` es efímero (gate de W0-2, W0-4, B13, B3 y V2). `down -v` solo sobre ellos, comprobado antes con `docker compose ls`.
- **S5-D91 · `forgot_deliver` acotado.** Semáforo de 4 y cola acotada a 32 tareas; si se llena, se descarta con log del tipo (M-7e).
- **S5-D92 · Avisos sin `q` libre.** `GET /notifications` y `GET /notifications/today` aceptan `q` (nombre del socio, por `members.service.search_ids`), y `test_list_routes_use_page_params` las cubre. Las exportaciones quedan como excepción nombrada en esa prueba.
- **S5-D93 · Etiqueta.** `v0.2.0` anotada en local, más `check-release-version.sh --check v0.2.0`. El push, el PR y el merge los hace una persona.
- **S5-D94 · Comprobaciones del explorador.** E1 a E16 se responden en el Rojo del slice indicado (sección 10). Si una respuesta contradice este plan, nace una decisión numerada en ese slice; no se improvisa.
- **S5-D95 · B13 verifica el snapshot sin `migrate-provider` (E1 de la crítica 1).** `migrate-provider` nace en B2 y B13 va antes (S5-D67). `openbao_restore_e2e.sh` envuelve una cadena de prueba con `bao write transit/encrypt/apex-kek plaintext=<base64>` con el token de `tools`, toma el snapshot, restaura en un OpenBao limpio, desella y descifra con `bao write transit/decrypt/apex-kek`; el resultado debe igualar al original. La variante con `migrate-provider --verify` pasa a B2.7 y se cita en V3.
- **S5-D96 · `deploy.sh` comprueba el rol de `MIGRATE_DB_USER` (E2 de la crítica 1).** Antes de `migrate`, con `psql` como propietario (`exec db`), comprueba que el rol existe; si no, sale con 2 y "el rol <x> no existe: corra `dbsetup` o fije MIGRATE_DB_USER". En producción la variable se exige sin valor por defecto en `.env.ops`; `.env.ops.example` la trae con `apex_owner` y `test_env_example` lo cubre. Casos en `test_deploy_script.sh` (rol ausente: 2 sin tocar nada) y en `test_db_roles.sh` en modo `existente`.
- **S5-D97 · Archivos de `cli_ops/` de menos de 150 líneas (E3 de la crítica 1).** Tope de `tests/cli/test_cli_base.py:268` (S4B-D95/D121): `rotate_kek.py` y `trim_kek.py` separados, `seed_notifications.py` y `notify.py` separados, ayudas puras en `core/crypto/migration.py`/`rotation.py` y `modules/notifications/service.py`; los comandos nuevos se registran en `register_ops`. Si algo no cabe, `TOPE_CLI_OPS` solo cambia con decisión.
- **S5-D98 · Cubetas `USER_*` desde W0-3 (E4 de la crítica 1).** W0-3 registra las cuatro claves nuevas en `USER_LIMITS` (`core/ratelimit.py`) con `CLAVES_SIN_RUTA_TODAVIA` de `tests/core/test_user_limits_catalog.py` (:240-241), y actualiza la regex y el conteo de `ci.yml` (:365-366, hoy "11 subidas") en el mismo checkpoint que `.env.example`. B5 y B12 solo quitan las claves de `CLAVES_SIN_RUTA_TODAVIA` al darles ruta.
- **S5-D99 · `test_contact_callers` fija el único llamador (E5 de la crítica 1).** B5.2 renombra `test_contact_callers_esta_vacio_en_el_sprint_4a` por una prueba que fija `CONTACT_CALLERS == frozenset({"app.modules.notifications.service"})` y mantiene la regla de :113.
- **S5-D100 · Orden de `-f` en `compose run` (E6 de la crítica 1).** `-f` es opción de `docker compose`, no de `run`: `$DCE -f infra/compose.verify.yml run --rm backup /opt/backup/run.sh`.
- **S5-D101 · `restore.sh` como `apex_owner` (E7 de la crítica 1).** W0-4.4 corre `restore.sh` en `apex-smoke` con la pila nueva (propietario no superusuario): `pg_restore --clean --single-transaction` y `CREATE EXTENSION btree_gist` de `0001` deben pasar. Si `btree_gist` exige superusuario, W0-4 lo instala en `roles.sql`/`dbsetup` como propietario bootstrap y lo anota.

### Contradicciones de contrato cerradas en T-DOC (W0-1.3)

- `KeyProvider` síncrono con `anyio` → `async` con `httpx.AsyncClient`.
- `wrap(key_ref, dek)` → `wrap(dek)`.
- `0030`/`0031`/`0035` → `0015` a `0019`.
- `result=skipped` → `details.sellado`.
- `register_health_check("crypto", fn)` → con `critical`, `allowed` y `healthy`.
- `/health` → incluye `migrations`.
- "Nginx no depende del api" → healthcheck tolerante (D15).
- `alert(kind, text)` → `alert(code, **context)`.
- `test_core_no_modules.py` → `test_core_import_direction`.
- `exists`, `labels_for`, `current_for` → `ensure_exists`, `refs_for`, `status_for`.
- `contact_for_notification(..., fields=)` → kwarg nuevo compatible.
- US-123 criterio 3 → N-20. US-123 criterio 1 → consentimiento obligatorio (D31).
- US-137 `export` → `download`. US-138 → columnas de N-29.
- `uv run python -m app.cli` → `docker compose run --rm tools`.
- `chat_id` en `settings.channels` → `TELEGRAM_CHAT_ID` en `.env.ops`.
- `downloadBlob` en `shared/ui` → `shared/lib`.
- `GET wa-link` → `POST`.
- `reportlab` → `core/pdf.py`. `aiosmtplib` → `smtplib`.
- `bootstrap.sh` "por la terminal" → `run --rm -T` con stdin.
- Textos viejos: RUNBOOK:311 (`rotate-key` ya existe), BRECHAS:32 (OpenBao en v0.2), `CLAUDE.md` (`sign_audit` en v0.3).

## 2. Fixtures y utilidades de prueba compartidas

- **W0-2:** `scripts/ci/test_openbao_infra.sh`, en Bash puro con `docker` falso para el render; `scripts/ci/fakes/bao` (falso para `test_deploy_script.sh`).
- **W0-3:** `tests/migrations/test_worker_role_paths.py`, que usa la fixture `apex_roles` y `url_por_rol("apex_worker")` existentes.
- **B1:** `tests/factories/fake_transit.py`:
  - `FakeTransit` (AES-GCM real, `vault:v<n>:`, `rewrap`, `rotate`, `min_decryption_version`, estados `sealed`, `forbidden`, `timeout`, `uninitialized`);
  - `fake_transit_client(ft) -> httpx.AsyncClient` con `MockTransport`.
  
  `tests/crypto/conftest.py` gana `token_file(tmp_path)` (600), `provider_param` (`local`, `fake_transit`, `openbao_real` con `skipif(not OPENBAO_TEST_ADDR)` y el marcador `openbao`) y `filas_mixtas(session)`. El marcador `openbao` se registra en `pyproject.toml`.
- **B13:** `tests/factories/minisign.py` (par Ed25519 de prueba y `sign_like_minisign(data)`, con vectores producidos por el `minisign` real de la imagen `apex-backup` y guardados como constantes); `tests/factories/backup.py` gana `with_openbao_snapshot` y `signed=True`. En `infra/backup/tests/` llegan un `curl` falso y `test_snapshot.sh`.
- **B2:** `tests/crypto/conftest.py` gana `manifiesto_firmado_reciente(tmp_path, snapshot=True)`, `kek_verify_reciente(session, actor)` y `migracion_a_medias` (con `dos_sesiones`).
- **B3:** `tests/core/conftest.py` gana `crypto_state_limpio` (autouse en `test_health_crypto.py` y `test_crypto_recovery.py`) y `app_sellada(fake_transit)`.
- **B4:** `tests/core/conftest.py` gana `smtp_falso` (servidor `smtpd` mínimo en un hilo sobre `socket` de la biblioteca estándar, que guarda los mensajes; sin dependencia nueva) y `telegram_transport` (`MockTransport` que registra las peticiones).
- **B5:** `tests/factories/members.py` gana `with_consent` y `channel_prefs`.
- **B6:** `tests/factories/notifications.py` (`make_template`, `make_rule`, `seed_defaults_db`); `tests/conftest.py` gana en `LIMPIEZA_DE_SESION` `notifications.notifications`, `notification_rules`, `notification_templates` y `members.member_channel_preferences`, en ese orden, antes de `LIMPIAR_MEMBERS`.
- **B7:** `tests/factories/notifications.py` gana `make_notification`; `escenario_vencimientos(session, today)` con fechas fijas del 17, 20, 21 y 27 de octubre y del 4 de noviembre, y cruce de medianoche UTC/Bogotá.
- **B8:** `tests/worker/conftest.py` gana `notify_ctx(frozen_clock, smtp_falso)`.
- **B12:** `tests/factories/payments.py` gana `mes_con_anulados_y_medianoche`; `tests/members/conftest.py` gana `socios_masivos(n)` para `perf`.
- **Front:** `web/src/test/blob.ts` (respuestas `Blob` falsas); `web/tests/e2e/helpers/stack.ts` gana `crearAvisoPendiente` (API del ensayo) y `baseUrlEnsayo()` (si no existe).

## 3. Paralelismo: cuándo lanzar el front

- El backend corre en serie en la rama del sprint.
- El worktree nace tras el checkpoint de B10 (contratos de avisos completos). Corren F1 (B7), F2 (B4, B6), F3 (B5, B7, B10) y F5 (B9) mientras el backend hace B11 y B12.
- F4 empieza tras el checkpoint de B12, con `git rebase`.
- Comandos pesados serializados (D84). Ningún paso del front toca `api/`, `docs/openapi.json`, `types.ts`, `DECISIONES.md` ni `CLAUDE.md`; sí toca `docs/BRECHAS.md` §13 (filas del front) y su cuaderno.
- V empieza cuando F4 tiene checkpoint.

## 4. Wave 0

### S5-W0-1 · Decisiones, T-DOC, licencias y ADR-005

- **Historias:** T-DOC de US-120 a US-139.
- **Cierra:** C1, C8 (licencias y `NOTICE`), parte de C7 (licencias), Q1 a Q10 del blueprint y P1 a P18 de la exploración (por decisión), contradicción de M-9 en `ROUTES.md`.
- **Depende de:** nada. **Migración:** ninguna.

**Paso 1 · W0-1.1 · Línea base**

1. Estado del stack:
   - `$DC ps`: seis contenedores `healthy`.
   - `$DC exec api alembic current` = `0014 (head)`.
   - `git status` limpio salvo este plan; `git worktree list` solo el principal.
   - Ids de imagen con `docker image inspect --format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}}'`.
   - `docker stats --no-stream`.
2. Red y puertos:
   - `netstat -ano | findstr -E "8280|8380|8200|8025"` vacío.
   - `docker network ls` y `inspect`: `172.30.1.0/24`, `172.31.2.0/24`, `172.31.3.0/24`, `172.31.12.0/24` y `172.31.13.0/24` libres.
   - `docker compose version` 2.24 o mayor (`!override`, `internal`).
3. Digests con `docker buildx imagetools inspect`: `openbao/openbao:<2.x estable más reciente>`, `axllent/mailpit:<v1.x>`, `python:3.12-alpine`. Se anotan con fecha.
4. E11 y E12 en un contenedor desechable de OpenBao:
   - `bao version`;
   - `id` (uid y gid del usuario de la imagen);
   - `bao operator unseal -h` (¿lee `-` de stdin?);
   - `which wget curl`;
   - `bao server` con raft sobre un volumen temporal y `--read-only --tmpfs /tmp` (¿arranca?).
   
   Render de un compose de prueba en el scratchpad con `internal: true` y `!override`.
5. `apex-db-1`, solo lectura:
   - `count(*)` de socios;
   - `SELECT provider, state, count(*) FROM crypto.crypto_keys GROUP BY 1,2` (8 `local` `active`);
   - `SELECT rolname, rolsuper FROM pg_roles WHERE rolname LIKE 'apex%'`;
   - última fila de `worker.job_runs`.
6. Gates baratos en HEAD: `ruff check`, `ruff format --check`, `mypy src`, `tsc --noEmit`, `bash scripts/workflow/tests/run.sh`.

**Paso 2 · W0-1.2 · Cuaderno.** `docs/scratch/sprint-05.md` gana el bloque "W0-1 · línea base" con todo lo del paso 1 (sin secretos).

**Paso 3 · W0-1.3 · T-DOC**

- `SPRINT-05.md`: migraciones `0015` a `0019`, slices y orden (D67), DoD con "reinicio de servidor" (D69), `POST wa-link`, sin `reportlab`.
- Desgloses de EP-14, EP-15 y EP-16 e historias:
  - US-123 y US-126 pasan a READY;
  - US-133 (una llave, tokens por servicio, `--first-install`), US-134 (`async`, `status`, `rewrap`), US-135 (precondiciones H-1, `retire-local-kek`), US-136 (healthcheck, 20 s y 5 s), US-124 (ORM), US-125 (`smtplib`), US-127 (`POST`), US-131 (sin arista), US-137 (PDF propio, sin documento), US-138 y US-139 (N-29, `has_q`, cubetas).
- `docs/design/ROUTES.md`: `wa-link` como `POST`.
- `CLAUDE.md`: estructura (`notifications/`, `core/{mail,alerts_telegram,export,pdf}.py`, `core/crypto/{openbao_provider,state,recovery,migration,minisign}.py`, `cli_manifest.py`, `infra/openbao/`, `compose.openbao.yml`, `worker/jobs/notify.py`; `sign_audit` en v0.3; `rotate-key` existente).
- `RUNBOOK.md:311`, `04_architecture_decision.md` §4, `BRECHAS.md:32` y §13 (nueva sección con las filas del sprint).
- `memberships/events.py` (docstring: el barrido por fecha reemplaza la suscripción) se corrige en B7, porque es código.

**Paso 4 · W0-1.4 · DECISIONES y ADR**

- `DECISIONES.md` gana la sección "Sprint 5 · decisiones de implementación" (la sección 1 de este plan).
- `docs/adr/ADR-005-custodia-openbao.md`, el README de ADR y `tests/architecture/test_adr_docs.py` (ADR-005 presente).

**Paso 5 · W0-1.5 · Dependencias y licencias**

- `cd api && uv add --dev pypdf`.
- `bash scripts/ci/check-licenses-api.sh` y `bash scripts/ci/test_licenses.sh`. Esta última gana casos de control: `fpdf2` (LGPL) y `python-telegram-bot` (LGPL) se rechazan.
- `scripts/ci/notice.sh` gana un bloque fijo: imagen OpenBao (MPL-2.0 sin modificar), Mailpit (MIT, solo desarrollo), `python:3.12-alpine` (PSF-2.0, solo desarrollo, `telegram-fake`), `curl` (licencia curl, imagen `apex-backup` desde B13).
- La licencia curl no está en la lista de `CLAUDE.md`: es un binario de contenedor, permisivo, del tipo MIT. Se añade al bloque de binarios de contenedor de `CLAUDE.md` con esta decisión.
- `NOTICE` se regenera. `uv.lock` entra en el checkpoint.

**Paso 6 · W0-1.6 · Gate y checkpoint**

1. `cd api && uv run ruff check tests/architecture/test_adr_docs.py && uv run ruff format --check tests/architecture/test_adr_docs.py`.
2. `bash scripts/ci/test_licenses.sh`.
3. `security-reviewer`: T-DOC y decisiones, que S5-D49 a D63 estén todas y que la custodia D82 esté escrita.
4. Sello: `bash scripts/workflow/slice-gate.sh architecture tests/architecture/test_adr_docs.py`.
5. `checkpoint-commit.sh "S5-W0-1 decisiones del Sprint 5, T-DOC, pypdf de desarrollo, NOTICE y ADR-005"`.

### S5-W0-2 · Infra OpenBao, redes, bootstrap, healthcheck tolerante y despliegue

- **Historias:** US-133, parte de US-136 (Compose).
- **Cierra:** C3 (Compose y `deploy.sh`), C8 (infra), H-1 parte `bootstrap`, H-2 parte overlay y `deploy.sh`, M-1, M-2, M-3 (estático), L-3, D10, D11, D12, D15, D22 (parte), D74 a D77.
- **Depende de:** W0-1. **Migración:** ninguna.

**Paso 7 · W0-2.1 · Rojo de infraestructura**

- `scripts/ci/test_openbao_infra.sh` (nuevo):
  - `bash -n` de `infra/openbao/*.sh`, `scripts/dev/openbao-seal.sh` y `scripts/ci/openbao-smoke.sh`.
  - Políticas `infra/openbao/policies/{apex-api,apex-worker,apex-tools,apex-backup-snapshot}.hcl`:
    - api: exactamente `transit/encrypt/apex-kek` y `transit/decrypt/apex-kek` con `update`, más `auth/token/renew-self`;
    - worker: solo `decrypt` y `renew-self`;
    - tools: además `transit/rewrap/apex-kek`, `transit/keys/apex-kek/rotate` y `transit/keys/apex-kek/config`;
    - ninguna con `delete`, `sudo`, `trim`, `*` fuera de `apex-` ni `sys/`, salvo la ruta exacta de D75.
  - `bootstrap.sh`: sin `set -x`; con `set -euo pipefail` y `umask 077`; exige `--first-install` y `INICIALIZAR` antes de `transit/keys/apex-kek`; comprueba el umbral de 3 o más; no escribe la raíz a archivo ni hace `echo` de ella; termina con `token revoke -self`; los tokens se escriben con modo 600 y uid 10001.
  - `dev-entrypoint.sh`: aborta si `APEX_ENV != dev`.
  - `config.hcl`: `ui = false`, `disable_mlock = true`, `storage "raft"`, `tls_disable` comentado con el motivo.
- `scripts/ci/test_compose_config.sh`, aserciones nuevas:
  - `openbao`: sin `ports`, `read_only`, `tmpfs /tmp`, `cap_drop ALL`, `no-new-privileges`, solo en la red `custody`, `custody` con `internal: true`, volúmenes `openbao-data` y `config.hcl:ro` (nunca la carpeta entera), healthcheck `sys/health` con `sealedcode=200&uninitcode=200`.
  - `openbao-bootstrap`: perfil `bootstrap`, `logging.driver: none`, `cap_drop ALL` más `CHOWN`.
  - Tokens: `openbao-token-api` `:ro` solo en `api`, `-worker` solo en `worker`, `-tools` solo en `tools`.
  - `api`, `worker` y `tools` en `default` y `custody`; `web`, `db` y `backup` (hasta B13) fuera de `custody`.
  - `api` y `worker` dependen de `openbao: service_healthy`; `tools` con `cap_drop ALL` (L-3).
  - Healthcheck del api: un `python -c` que acepta 200, o 503 con `db == "ok"` y `migrations == "ok"`.
  - `compose.yml` no contiene `dev-entrypoint`, `BOOTSTRAP_NONINTERACTIVE` ni `openbao-seal` (M-3).
  - `compose.openbao.yml`: `api` y `worker` sin `keys`.
  - Desarrollo: `openbao` con perfil `openbao` y volumen `openbao-dev-data`; `depende(dev, api) == depende(dev, worker) == {db}`.
  - La lista de volúmenes suma `openbao-data`, `openbao-token-api`, `openbao-token-worker` y `openbao-token-tools` (las dos aserciones literales de `:92-93`).
- `scripts/ci/test_images_pinned.sh`: la imagen de OpenBao por digest con fecha.
- `scripts/ci/test_deploy_script.sh`:
  - el cuerpo 503 con `crypto: "sealed"`, `db: "ok"` y `migrations: "ok"` → sale 0 con "api en estado sellado: desellar OpenBao (docs/operacion/openbao.md)";
  - `CRYPTO_PROVIDER=openbao` sin `compose.openbao.yml` → sale 2;
  - con `kek.bin` presente en `keys` (`docker` falso) → aviso;
  - `openbao` entra en el `up -d`.
- `scripts/workflow/tests/test_wave0_gate.sh` y el caso de `run-gates`: `test_openbao_infra` se llama; las combinaciones nuevas se renderizan.
- Correr todo y anotar el rojo.

**Paso 8 · W0-2.2 · Verde de `infra/openbao/`**

- `config.hcl`.
- `bootstrap.sh`: init 5/3 solo con `--first-install`; desellado leyendo 3 llaves de stdin; `transit`; `apex-kek` (`aes256-gcm96`, `exportable=false`, `allow_plaintext_backup=false`) y `apex-sign-audit` (`ed25519`); las cuatro políticas; cuatro tokens periódicos (`period=768h`, la de backup entra en B13); `--reissue-tokens`; revocación de la raíz.
- `dev-entrypoint.sh` y `policies/*.hcl`.
- `scripts/dev/openbao-seal.sh`.
- `.gitignore`: `docs/scratch/ensayo/openbao/` (ya cubierta por `docs/scratch/ensayo/`; se comprueba con `git check-ignore -v`).

**Paso 9 · W0-2.3 · Verde de Compose**

- `infra/compose.yml`: servicios `openbao` y `openbao-bootstrap`, red `custody`, volúmenes, `depends_on`, montajes, healthcheck del api (D15), `tools` con `cap_drop ALL`.
- `infra/compose.openbao.yml` (nuevo).
- `infra/compose.dev.yml`: `openbao` con perfil y `dev-entrypoint`, `depends_on: !override` para api, worker y tools.
- `.env.ops.example`: `APEX_CUSTODY_SUBNET`.

**Paso 10 · W0-2.4 · Verde de scripts y CI**

- `infra/deploy.sh` (S5-D96): antes de `migrate`, comprueba con `psql` como propietario (`exec db`) que el rol de `MIGRATE_DB_USER` existe y, si no, sale con 2 y "el rol <x> no existe: corra `dbsetup` o fije MIGRATE_DB_USER" sin tocar nada; en producción la variable se exige sin valor por defecto en `.env.ops` (`.env.ops.example` la trae con `apex_owner`, cubierto por `test_env_example`); casos en `test_deploy_script.sh` (rol ausente: 2). Además: sondeo con `curl -sS` que lee el cuerpo de un 503; mensaje de sellado; exige el overlay; aviso de `kek.bin`; `openbao` en `up -d`.
- `scripts/ci/compose-smoke.sh` y `prod-smoke.sh`: `openbao` en la lista de servicios; `prod-smoke --provider openbao` deja la comprobación de `kek.bin` para B2.
- `scripts/workflow/wave0-gate.sh` y `run-gates.sh`: `test_openbao_infra` y las combinaciones nuevas.
- `.github/workflows/ci.yml`: job `scripts` con `test_openbao_infra.sh`; `services.openbao` en el job `api` (D85; inerte hasta B1); `docker pull` de OpenBao por digest en `images`, `e2e-stack` y `prod-smoke`.

**Paso 11 · W0-2.5 · Documentación**

- `docs/operacion/openbao.md` (nuevo):
  - instalar: `--first-install`, salida por terminal, nunca a archivo;
  - custodia 2/2/1 con la copia sellada en un tercero (caja de seguridad o notario), nunca en manos de una de las dos partes (D82, paso humano);
  - desellar tres veces tras cada reinicio;
  - `rekey` ante la pérdida de una llave; rotar los tokens cada 90 días y tras un incidente (M-2);
  - interruptor de emergencia: revocar tokens y reiniciar api y worker (L-1);
  - qué significa cada valor de `/health.crypto`.
- `infra/README.md`: las dos redes.
- RUNBOOK §13 "OpenBao, avisos y exportaciones (Sprint 5)" (inicio) y §7 (renovar los digests de OpenBao y Mailpit).
- Cuaderno.

**Paso 12 · W0-2.6 · Gate**

1. `bash scripts/ci/test_openbao_infra.sh && bash scripts/ci/test_compose_config.sh && bash scripts/ci/test_deploy_script.sh && bash scripts/workflow/tests/run.sh`.
2. `security-reviewer` de W0-2: políticas, bootstrap, logs, red, montajes, overlay, `deploy.sh`.
3. Sello: `bash scripts/workflow/wave0-gate.sh W0-2`. Nota: `wave0-gate.sh` corre `test_api_image apex-api:local` antes del `buildx` de W0-2.7, así que usa la imagen anterior; se anota en el cuaderno y W0-2.7 repite `test_api_image` sobre la nueva.

**Paso 13 · W0-2.7 · Docker y evidencia**

1. `docker pull` de OpenBao por digest.
2. Desarrollo: `$DC --profile openbao up -d openbao`; `$DC exec -T openbao bao status` (desellado, 1/1); `bash scripts/dev/openbao-seal.sh` → `bao status` sellado; `$DC restart openbao` → desellado; el api de desarrollo sigue `healthy` y no depende de OpenBao; `$DC --profile openbao stop openbao`.
3. Ensayo nuevo: `docs/scratch/ensayo/{.env,.env.ops}` desde los ejemplos (subred 8280, `CRYPTO_PROVIDER=local`). Después:
   - buildx de `apex-api:local`, porque el Dockerfile no cambió pero `src` está en la imagen de HEAD;
   - `$DCE up -d`;
   - P-BAO: init 5/3 con `--first-install`, desellar con 3;
   - `$DCE exec -T openbao bao status` (desellado, 5/3);
   - inspección de `docker inspect` del contenedor bootstrap: sin logs (`logging none`);
   - `$DCE restart openbao` → sellado; `api` sigue `healthy` (`CRYPTO_PROVIDER=local`; aún no hay estado sellado);
   - desellar; `test_db_roles.sh` con `DC="$DCE"`.
4. Smoke de producción en Linux (gate): `prod-smoke.sh --no-build` en `apex-smoke` desde el contenedor auxiliar `docker:cli`; verde; `down -v` del smoke.
5. `docker stats --no-stream` al cuaderno.

**Paso 14 · W0-2.8 · Checkpoint.** `"S5-W0-2 servicio openbao, red custody, bootstrap 5/3 con --first-install, políticas mínimas, compose.openbao.yml, healthcheck tolerante y deploy.sh con aviso de sellado"`, seguido del commit de evidencia.

### S5-W0-3 · `0015`, `Settings`, entorno por servicio, redacción y grants por columna

- **Historias:** US-134 y US-135 (esquema), deuda D202, D203, D204.
- **Cierra:** C2 (`0015`), C4 (grants de `crypto_keys`), parte de C8 (`Settings`), M-7f, M-8 (redacción), L-9, D4, D17, D44, D34 (parte).
- **Depende de:** W0-2. **Migración:** `0015_crypto_provider_migration`.

**Paso 15 · W0-3.1 · Preparación P-MIG.** P-MIG pasos 1 y 2: volcado `sprint-05-antes-0015.dump` y `$DC stop api`.

**Paso 16 · W0-3.2 · Rojo**

- `tests/migrations/test_0015_crypto_provider_migration.py`:
  - `local → openbao` con `wrapped_material` nuevo, aceptado;
  - `openbao → local`, aceptado (reversa de D18);
  - solo `wrapped_material` con el mismo proveedor (rewrap), aceptado;
  - `provider` sin cambiar `wrapped_material`, rechazado;
  - `state` junto con `wrapped_material`, rechazado;
  - `version` o `data_class`, rechazado;
  - fila `sign`, rechazada;
  - `tgenabled = 'A'` tras el upgrade;
  - el `downgrade` restaura el cuerpo de `0003` (comparación de `pg_get_functiondef`);
  - `apex_api` y `apex_worker` no pueden `UPDATE provider` (sobre `apex_roles`).
- `tests/migrations/test_0014_audit_log_triggers_always.py`: pasa a "en la cadena de head".
- `tests/core/test_config.py`:
  - `OPENBAO_ADDR` exige `https` salvo `openbao`, `localhost` y `127.0.0.1`;
  - `OPENBAO_TOKEN_PATH` obligatoria con `CRYPTO_PROVIDER=openbao`;
  - `missing_secrets` con `openbao` exige el token y no la KEK;
  - `SMTP_*` todo o nada; `SMTP_TLS_MODE=none` solo con `ENV=dev`;
  - `TELEGRAM_API_BASE` distinta de la oficial solo con `ENV=dev`;
  - `SMTP_PASSWORD` y `TELEGRAM_BOT_TOKEN` son `SecretStr` y su `repr` va enmascarado;
  - valores por defecto: `CRYPTO_RECOVERY_POLL_S=20`, `OPENBAO_TIMEOUT_S=5`, `NOTIFY_MAX_ATTEMPTS=3`, `NOTIFY_NET_TIMEOUT_S=10`, `EXPORT_MAX_ROWS=20000`;
  - las cuatro `USER_*` de D81;
  - `BACKUP_SIGN_PUBKEY` opcional y con formato validado;
  - `NON_API_ENV_VARS` = las claves de `.env.ops.example` que no son de `Settings`.
- `tests/core/test_env_example.py`:
  - lo no secreto (`OPENBAO_*`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_FROM`, `SMTP_TLS_MODE`, `TELEGRAM_CHAT_ID`, `TELEGRAM_API_BASE`, `NOTIFY_*`, `EXPORT_MAX_ROWS`, `CRYPTO_RECOVERY_POLL_S`, `USER_*`) va en `.env.example`;
  - `SMTP_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `APEX_CUSTODY_SUBNET`, `MIGRATE_DB_USER`, `TOOLS_DB_USER` y `BACKUP_SIGN_PUBKEY` van en `.env.ops.example`;
  - el comentario del catálogo dice 16 cubetas y 15 variables;
  - (S5-D98) las cuatro claves nuevas quedan registradas en `USER_LIMITS` de `core/ratelimit.py` con `CLAVES_SIN_RUTA_TODAVIA` de `tests/core/test_user_limits_catalog.py` (:240-241), y la regex y el conteo de `ci.yml` (:365-366, hoy "11 subidas") se actualizan en este mismo checkpoint; B5 y B12 solo quitan las claves de `CLAVES_SIN_RUTA_TODAVIA` al darles ruta;
  - sin claves repetidas entre los dos archivos.
- `tests/core/test_logging_redact.py`:
  - `bot123456:AAH<30 caracteres>` queda redactado;
  - `SENSITIVE_KEYS` suma `x-vault-token`, `smtp_password`, `telegram_bot_token` y `bot_token`;
  - `httpx` y `httpcore` a `WARNING`.
- `tests/architecture/test_settings_no_secrets.py` y `test_no_sensitive_in_logs.py`: casos nuevos de los secretos.
- `tests/migrations/test_db_grants.py`:
  - `apex_worker`: `SELECT` en `crypto.crypto_keys`;
  - `members.members` por columna (`id, first_name, last_name, phone, email, status, deleted_at, data_consent_at, created_at, updated_at`), y falla un `SELECT document` como `apex_worker`;
  - `auth.users`: `apex_api` con `UPDATE` solo en las columnas del inventario;
  - `payments.payments`: `INSERT` por columna sin `void_reason`, `voided_by`, `voided_at`, y un `INSERT` con `voided=true` falla;
  - las tres listas coinciden.
- `tests/migrations/test_worker_role_paths.py` (E6), como `apex_worker` sobre `apex_roles`:
  - `memberships.expirations.recompute_statuses` corre;
  - `members.service.names_for` corre;
  - `contact_for_notification` con `load_only` corre (el descifrado llega en B5; aquí solo la carga).
- `scripts/ci/test_env_isolation.sh`: `SMTP_PASSWORD` y `TELEGRAM_BOT_TOKEN` solo en `api` y `worker`; `OPENBAO_TOKEN_PATH` en `api`, `worker` y `tools`; ninguna de ellas en `web`, `db`, `backup`, `migrate` ni `dbsetup` (L-9).
- `test_deploy_script.sh`: la lista de variables prohibidas del api suma `POSTGRES_*`; en `web` se prohíben `SMTP_*` y `TELEGRAM_*`.

**Paso 17 · W0-3.3 · Verde de `0015`**

- `CREATE OR REPLACE FUNCTION crypto.guard_keys_update()` (S5-D4), con `rearm_always_sql` y `downgrade` al texto literal de `0003`.
- P-MIG pasos 3 a 8 (incluido `\df+`).

**Paso 18 · W0-3.4 · Verde de ajustes, entorno y grants**

- `core/config.py` (campos y validadores; `missing_secrets`) y `core/logging.py` (patrón y claves).
- `.env.example` y `.env.ops.example`.
- `compose.yml`: bloques `environment` de `api`, `worker` y `tools` interpolados desde `.env.ops`, con `SMTP_PASSWORD` y `TELEGRAM_BOT_TOKEN` solo en api y worker.
- `deploy.sh` y `prod-smoke.sh` (variables prohibidas por servicio).
- `infra/db/grants.sql` y `revoke.sql` (D202, D203, D204, `crypto_keys` del worker).
- `load_only` en los caminos del worker que hacen `select(Member)` completo (`memberships/expirations.py`, `members/service.names_for`, `members/contact.py`).
- El `.env` de desarrollo se amplía con las claves nuevas antes de levantar nada.

**Paso 19 · W0-3.5 · Documentación.** RUNBOOK §6 (rollback de `0015`) y §12 (grants por columna, `apex_worker` con `crypto_keys`); bloque W0-3 en DECISIONES (lista de columnas de D203); cuaderno.

**Paso 20 · W0-3.6 · Gate**

1. `slice-gate.sh core/logging tests/core/test_logging_redact.py`.
2. `slice-gate.sh memberships tests/migrations/test_worker_role_paths.py`.
3. `slice-gate.sh members tests/migrations/test_worker_role_paths.py tests/members/test_service_contact.py`.
4. `slice-gate.sh core/config tests/core/test_config.py tests/core/test_env_example.py tests/migrations/test_0015_crypto_provider_migration.py tests/migrations/test_0014_audit_log_triggers_always.py tests/migrations/test_db_grants.py`.
5. `bash scripts/ci/test_env_isolation.sh && bash scripts/ci/test_deploy_script.sh`.
6. `database-reviewer` (`0015`, grants por columna) y `security-reviewer` (entorno, redacción), en paralelo.
7. Sello: `bash scripts/workflow/wave0-gate.sh W0-3 tests/migrations/test_db_grants.py`.

**Paso 21 · W0-3.7 · Docker y evidencia**

1. Buildx de `apex-api:local` (cambió `src`).
2. `$DC up -d --no-build --force-recreate api worker` → `healthy`; `restart worker`.
3. Ensayo: `$DCE up -d --no-build --force-recreate api worker tools`; `migrate` muestra `0014 -> 0015`; `dbsetup` en 0; `test_db_roles.sh`.
4. `$DCE run --rm worker python -m app.worker.main --run-once expirations` → 0 como `apex_worker` con el grant por columna.
5. `/proc/1/environ` de `web` y `backup` del ensayo sin `SMTP_` ni `TELEGRAM_`.

**Paso 22 · W0-3.8 · Checkpoint.** `"S5-W0-3 0015 guarda de crypto_keys para migrar proveedor, Settings de OpenBao/SMTP/Telegram/exportación, redacción y grants por columna (D202-D204)"`.

### S5-W0-4 · `apex_owner` NOSUPERUSER (M-12, D206)

- **Cierra:** D6, D62, D89, S4B-D206.
- **Depende de:** W0-3. **Migración:** ninguna (sin cambios en `apex-db-1`).

**Paso 23 · W0-4.1 · Rojo**

- `tests/migrations/test_db_grants.py`, sobre `apex_roles` con `apex_owner` creado por `10-apex-owner.sh` vía `docker exec`:
  - `rolsuper = false`, `rolcreaterole = false`, `rolcreatedb = false`;
  - `SET session_replication_role = replica` falla;
  - `COPY ... TO PROGRAM` falla;
  - `CREATE` en `public` falla;
  - `alembic upgrade head` como `apex_owner` sobre una base vacía funciona.
- `scripts/ci/test_db_roles.sh`: modo `nueva` (dueño `apex_owner`) y modo `existente` (`MIGRATE_DB_USER` igual al propietario; incluye el caso de rol inexistente que `deploy.sh` rechaza con 2, S5-D96).
- `test_compose_config.sh`:
  - `db` monta `initdb/10-apex-owner.sh:ro`;
  - `migrate` y `tools` usan `${MIGRATE_DB_USER:-apex_owner}` y `${TOOLS_DB_USER:-apex_owner}`;
  - `POSTGRES_USER` solo en `db` y `dbsetup`.
- `test_env_example.py`: `APEX_OWNER_DB_PASSWORD=cambiar-esto` en `.env.ops.example`.

**Paso 24 · W0-4.2 · Verde.** `infra/db/initdb/10-apex-owner.sh` (contraseña por variable, sin registrar sentencias); `roles.sql` y `revoke.sql` (`apex_owner` conocido); `compose.yml`; `.env.ops.example`; RUNBOOK §12 (pila nueva frente a servidor existente; `REASSIGN OWNED BY apex TO apex_owner` como paso humano).

**Paso 25 · W0-4.3 · Gate.** `database-reviewer` y `security-reviewer`, en paralelo. `slice-gate.sh core/config tests/core/test_env_example.py`. Sello: `bash scripts/workflow/wave0-gate.sh W0-4 tests/migrations/test_db_grants.py`.

**Paso 26 · W0-4.4 · Docker y evidencia**

1. `docker compose ls`.
2. `$DCE down -v`, que reinicia OpenBao: P-BAO otra vez con llaves nuevas; las viejas se borran.
3. `$DCE up -d`: `migrate` como `apex_owner` (`0001` a `0015`), `dbsetup`, `test_db_roles.sh` en modo `nueva`.
4. `SELECT nspname, nspowner::regrole FROM pg_namespace` del ensayo (dueño `apex_owner`).
5. Smoke de producción en Linux (pila nueva) en verde.
6. `apex-db-1`: `pg_roles` sin `apex_owner`.
7. (S5-D101) `restore.sh` en `apex-smoke` con la pila nueva (`apex_owner` como propietario no superusuario): `pg_restore --clean --single-transaction` y `CREATE EXTENSION btree_gist` de `0001` deben pasar; si `btree_gist` exige superusuario, el plan de W0-4 lo instala en `roles.sql`/`dbsetup` como propietario bootstrap y lo anota.

**Paso 27 · W0-4.5 · Checkpoint.** `"S5-W0-4 apex_owner NOSUPERUSER dueño en pilas nuevas; migrate y tools sin superusuario (M-12, S4B-D206)"`.

## 5. Backend

### S5-B1 · `OpenBaoProvider`, puerto ampliado y proveedor por fila (US-134)

- **Cierra:** parte de C2, H-2 (arranque sin `kek.bin`), M-5a, D2, D3, D9, D17, D21a/b, E1, E2.
- **Depende de:** W0-3. **Migración:** ninguna.

**Paso 28 · B1.1 · Verificación y stubs**

- E1 y E2 por `grep -rn "keyring.provider\|current_provider()\|provider=\"local\"\|current_keyring()\|refresh_current"` sobre `api/src`; la lista va al cuaderno.
- Stubs:
  - `core/crypto/openbao_provider.py` (firmas de S5-D17 y del blueprint B1: `KEK_KEY`, `SIGN_KEY`, `map_error(status, errors) -> CryptoError`, `parse_version(wrapped) -> int`, `OpenBaoProvider(addr, token_path, *, timeout_s, client=None)` con `name`, `wrap`, `unwrap`, `rewrap`, `sign`, `verify`, `rotate`, `key_info`, `status`, `renew`, `maybe_renew(now)`);
  - `provider.py` (`ProviderStatus = Literal["ok","sealed","unreachable"]`, `name`, `status`, `rewrap`, `ProviderResolver = Callable[[str], KeyProvider]`, `get_provider_named(settings, name)`);
  - `local_provider.py` (`name="local"`, `status() -> "ok"`, `rewrap` lanza `unsupported`);
  - `errors.py` (`CryptoUnavailable(CryptoError)` con `reason ∈ {sealed, unreachable, forbidden, not_loaded}`);
  - `keyring.py` (`load_all(session, resolver, *, classes: frozenset[str] | None = None)`);
  - `bootstrap.py` (`ensure_keys(session, provider, resolver)`).
- `tests/factories/fake_transit.py`; el marcador `openbao` en `pyproject.toml`.

**Paso 29 · B1.2 · Rojo de arquitectura**

- `test_third_party_confinement.py`: `httpx` solo en `core/crypto/openbao_provider.py` (B4 suma `core/alerts_telegram.py`); control con una fuente falsa.
- `test_crypto_bus_importers.py`: `openbao_provider` solo lo importan `core/crypto/*`.
- `test_kek_path_single_door.py`: `OPENBAO_TOKEN_PATH` solo se lee en `openbao_provider.py`.
- `test_core_import_direction.py`: `core/crypto` no importa `core/audit`.

**Paso 30 · B1.3 · Rojo de `crypto`**

- `tests/crypto/test_provider_contract.py`, parametrizado por `local`, `fake_transit` y `openbao_real`:
  - `wrap` y `unwrap` ida y vuelta;
  - `unwrap` de basura → `unwrap_failed`;
  - `rewrap` conserva la DEK (no aplica a `local`);
  - `sign` y `verify` (no aplica a `local` sin fila `sign`);
  - `status`;
  - AAD `apx-dek-wrap` en `rewrap`, que solo prueba de verdad `openbao_real` (M-5a).
- `tests/crypto/test_openbao_provider.py`:
  - tabla de `map_error` (`503`+sealed, `403`, timeout, conexión, `404`, `500`);
  - `parse_version`;
  - el token no aparece en `repr`, en los logs (caplog a DEBUG, `httpx` a INFO), en las excepciones ni en `crypto_ops`;
  - `https` obligatorio fuera de los hosts permitidos;
  - archivo de token con grupo u otros con permisos → rechazo (salta en NT, con motivo); archivo de más de 256 bytes → rechazo;
  - se relee al cambiar `mtime`;
  - `follow_redirects=False` y `trust_env=False`;
  - `maybe_renew` cada 12 h con `FrozenClock`;
  - `status` → `sealed` para sellado y para sin inicializar; `unreachable` para timeout y 403.
- `tests/crypto/test_provider_per_row.py`:
  - filas mixtas `local` y `openbao` se abren cada una con su proveedor;
  - `local` no se construye si no hay filas `encrypt|index` `local`;
  - el api arranca sin `kek.bin` con una fila `sign` `local` (H-2.3);
  - `_create_missing` escribe `provider=provider.name`;
  - `_swap_key` usa el proveedor de creación;
  - `load_all(classes=...)` abre solo esas clases;
  - si el prefijo y la columna no coinciden → `unwrap_failed`.
- Pruebas existentes de `tests/crypto` y `tests/cli/test_rotate_key*.py` que fijan `load_all(session, provider)` se adaptan a la firma con `resolver`.

**Paso 31 · B1.4 · Verde.** `openbao_provider.py` (menos de 300 líneas); `provider.py`; `local_provider.py`; `errors.py`; `keyring.py`; `bootstrap.py`; `service._swap_key`; `bus._provider(llave)`; `cli_keyring.py`; `cli_ops/rotate_key.py` y `retire_key.py` (resolver); `main._startup` (`configure_provider` con resolver; el arranque degradado llega en B3). Funciones de menos de 50 líneas.

**Paso 32 · B1.5 · Documentación.** ADR-002 (proveedor por fila, `vault:v<n>:`), `CLAUDE.md` (bus), bloque B1 en DECISIONES, cuaderno.

**Paso 33 · B1.6 · Gate**

1. `slice-gate.sh cli tests/cli/test_rotate_key.py`.
2. `slice-gate.sh main tests/core/test_startup_failure.py`.
3. `slice-gate.sh architecture tests/architecture/test_third_party_confinement.py tests/architecture/test_crypto_bus_importers.py tests/architecture/test_kek_path_single_door.py tests/architecture/test_core_import_direction.py`.
4. `security-reviewer` de B1.
5. Sello: `slice-gate.sh crypto tests/crypto/test_provider_contract.py tests/crypto/test_openbao_provider.py tests/crypto/test_provider_per_row.py tests/crypto/test_bootstrap.py tests/crypto/test_local_provider.py`.

**Paso 34 · B1.7 · Docker y evidencia (M-5a)**

1. Buildx del api; `$DC up -d --no-build --force-recreate api worker`; `GET /members/{id}` descifra (sigue `local`).
2. OpenBao real: `$DC --profile openbao up -d openbao`; contenedor Linux `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` (el de 4B) en la red `apex_custody` con `api/` montado, `OPENBAO_TEST_ADDR=http://openbao:8200` y el token de desarrollo leído del volumen de desarrollo; `uv run pytest -m openbao tests/crypto -q` → 0 saltos.
3. Veredicto de M-5a (`rewrap` con AAD) al cuaderno. Si falla, decisión S5-D55a en el bloque B1 y el plan de `rotate-kek` usa `decrypt` y `encrypt` en B2.
4. `$DC --profile openbao stop openbao`.

**Paso 35 · B1.8 · Checkpoint.** `"S5-B1 OpenBaoProvider por httpx.AsyncClient, puerto con name/status/rewrap, proveedor por fila y suite de contrato"`.

### S5-B13 · Respaldo de OpenBao y firma del manifiesto verificada (H-1, D8, D72)

- **Cierra:** H-1 (snapshot), L-2, D8, D72, S4B-D57, D80, D149, E11 (backup).
- **Depende de:** B1. **Migración:** ninguna.

**Paso 36 · B13.1 · Stubs y Rojo de Python**

- Stubs: `core/crypto/minisign.py` y `app/cli_manifest.py` (`ManifestCheck(ok, reason, created_at, has_snapshot)`, `recent_signed_manifest(...)`).
- `scripts/workflow/slice-gate.sh`: el caso `cli` suma `src/app/cli_manifest.py`, con su caso en `test_slice_gate.sh`.
- `tests/crypto/test_minisign.py`:
  - vectores reales `ok`;
  - un byte alterado en los datos → falso; firma alterada → falso; comentario de confianza alterado → falso;
  - algoritmo `Ed` heredado → falso; llave de otro id → falso.
- `tests/cli/test_cli_manifest.py`:
  - sin `.minisig` → `no_signature`; firma inválida → `bad_signature`;
  - más de 24 h → `stale`; `created_at` en el futuro más de 5 min → `stale`;
  - `require_openbao_snapshot` sin la entrada o con `verified=false` → `no_snapshot`;
  - manifiesto de más de 1 MiB → rechazo; enlace simbólico → rechazo.
- `tests/cli/test_retire_key*.py`: el texto `NO_MANIFEST` exige una firma válida, no solo que exista.
- `tests/worker/test_backup_check.py`:
  - manifiesto con firma inválida → `corrupt`;
  - `openbao_snapshot` ausente → no degrada; presente con `sha256` o tamaño malos → `corrupt`;
  - presente y bien → `ok`.
- `tests/architecture/test_app_layer_importers.py`: `cli_manifest.py` solo lo importan `cli_ops/*`; `test_crypto_bus_importers` admite `minisign` vía el bus.

**Paso 37 · B13.2 · Rojo de infraestructura**

- `infra/backup/tests/test_snapshot.sh`:
  - `run.sh` llama `curl -K <archivo en /tmp>` y nunca pone el token en `argv` ni hace `wget --header` (L-2);
  - snapshot cifrado con `age` y `sha256`;
  - entrada `openbao_snapshot {name, size_bytes, sha256, verified}` en el manifiesto;
  - sin el token montado, el paso se salta con un log `info`.
- `test_manifest.sh`: el esquema admite `openbao_snapshot` opcional.
- `scripts/ci/test_compose_config.sh`: `backup` en `custody`; `openbao-token-backup:ro` solo en `backup`.
- `test_openbao_infra.sh`: la política `apex-backup-snapshot` y la excepción de D75.
- `test_backup_apk_pins.sh`: incluye `curl`.
- `infra/tests/openbao_restore_e2e.sh` (nuevo, Bash): pila de smoke, init, migración simulada de una fila, snapshot, `down -v` de `openbao-data`, restauración con `generate-root` efímero, desellar. Sin `migrate-provider` (nace en B2, S5-D95): envuelve una cadena de prueba con `bao write transit/encrypt/apex-kek plaintext=<base64>` (token de `tools`) antes del snapshot y, tras restaurar y desellar, la descifra con `bao write transit/decrypt/apex-kek`; debe ser igual al original.

**Paso 38 · B13.3 · Verde de Python.** `minisign.py` (con `cryptography` y `hashlib`, dentro de `core/crypto`); `bus.verify_signed_manifest` como única puerta pública; `cli_manifest.py`; `retire_key.py` sobre `cli_manifest`; `backup_check.py` (verificación por el bus y `openbao_snapshot`); `Settings.BACKUP_SIGN_PUBKEY` llega al `environment` de `worker` y `tools`.

**Paso 39 · B13.4 · Verde de infraestructura.** `infra/backup/{run.sh,lib.sh,Dockerfile (curl fijado),manifest.schema.json}`; `bootstrap.sh` (política y token `backup`, también con `--reissue-tokens`); `compose.yml` (`backup` en `custody`, volumen `openbao-token-backup`); `restore.sh` restaura además el snapshot cuando se pide `--with-openbao` (documentado: exige desellar con las llaves originales); `openbao_restore_e2e.sh`.

**Paso 40 · B13.5 · Documentación.** `docs/operacion/respaldo-y-restauracion.md` (base y snapshot en pareja, siempre); `openbao.md` (restaurar snapshot y `generate-root`); RUNBOOK §12 y §13; cuaderno.

**Paso 41 · B13.6 · Gate**

1. `slice-gate.sh crypto tests/crypto/test_minisign.py`.
2. `slice-gate.sh cli tests/cli/test_cli_manifest.py tests/cli/test_retire_key.py`.
3. `bash scripts/ci/test_infra_scripts.sh && bash scripts/ci/test_openbao_infra.sh`.
4. `security-reviewer` de B13.
5. Sello: `slice-gate.sh worker tests/worker/test_backup_check.py tests/worker/test_backup_check_evaluate.py`.

**Paso 42 · B13.7 · Docker y evidencia**

1. Buildx de api y backup; recrear el ensayo.
2. `$DCE --profile bootstrap run --rm -T openbao-bootstrap --reissue-tokens` (token de backup).
3. `$DCE -f infra/compose.verify.yml run --rm backup /opt/backup/run.sh` → manifiesto con `openbao_snapshot.verified=true` y `.minisig`.
4. `$DCE run --rm worker python -m app.worker.main --run-once backup_check` → 0 `ok`.
5. Smoke en Linux: `prod-smoke.sh` más `infra/tests/openbao_restore_e2e.sh` en `apex-smoke` → verde; `down -v`.

**Paso 43 · B13.8 · Checkpoint.** `"S5-B13 instantánea raft de OpenBao cifrada y firmada en el respaldo, firma minisign verificada en Python y restauración de base y OpenBao en pareja"`.

### S5-B2 · `migrate-provider`, `rotate-kek` y `retire-local-kek` (US-135)

- **Cierra:** parte de C2, H-1 (precondiciones), H-2 (retiro), M-5b, D18, D19, D73, S4B-D137, D148, D151.
- **Depende de:** B13. **Migración:** ninguna.

**Paso 44 · B2.1 · Stubs**

- `core/crypto/migration.py`: `KeyRowView`, `plan_provider_migration(rows, from_) -> tuple[UUID, ...]`, `MigrationResult(total, done, skipped, failed_key_id)`, `async migrate_provider(session_factory, *, from_, to, resolver, actor, dry_run)`, `async rewrap_all(session_factory, *, resolver, actor)`, `async verify_provider(session_factory, *, expected, resolver)`, `async trim_ready(session_factory, *, resolver) -> bool`.
- `cli_ops/migrate_provider.py`, `cli_ops/rotate_kek.py` (`rotate-kek --as`) y `cli_ops/trim_kek.py` (`rotate-kek --trim --as`, registrado desde `trim_kek.py`; ayudas puras en `core/crypto/migration.py` y `rotation.py`; S5-D97), `cli_ops/retire_local_kek.py`, registrados en `register_ops`.

**Paso 45 · B2.2 · Rojo de `crypto`**

- `tests/crypto/test_migrate_provider.py`:
  - el plan incluye `active`, `decrypt_only` y `retired` de `encrypt` e `index`, y excluye `sign`;
  - orden `(data_class, purpose, version)`;
  - interrupción a la mitad con `migracion_a_medias` y reanudación → `done = total`;
  - segunda corrida: nada que migrar, salida 0;
  - blobs de `members.members` idénticos byte a byte antes y después;
  - `crypto_ops` con `unwrap` y `wrap` y el mismo `batch_id`;
  - un `UPDATE` sin verificación previa es imposible (el `compare_digest` falla con un `FakeTransit` corrupto y no hay `UPDATE`);
  - la DEK se pone en ceros (`bytearray` observable);
  - `uq_crypto_jobs_in_progress` impide dos a la vez;
  - `--dry-run` no escribe;
  - reversa `openbao → local`.
- `tests/crypto/test_rotate_kek.py`:
  - `rotate` y luego `rewrap` por fila (versión nueva igual a `latest`);
  - reanudable;
  - `trim_ready` falso si queda una fila vieja (`FOR SHARE`) o si el job no está en `done`;
  - nunca se llama a `transit/keys/.../trim`;
  - `rotate_index` mantiene la DEK en `bytearray` en ceros (D151).

**Paso 46 · B2.3 · Rojo de `cli`**

- `tests/cli/test_migrate_provider_cli.py`:
  - sin `--as` con `ENV=production` → 2;
  - sin manifiesto firmado con snapshot de menos de 24 h → 2 (H-1);
  - sin `recent_kek_verify` → 2;
  - confirmación distinta de `MIGRAR` → 2 sin escribir;
  - `--yes`;
  - `--verify` → 1 si queda una fila `local`;
  - auditoría `update` con `after={from,to,total,done}`;
  - el error nunca lleva texto del proveedor.
- `tests/cli/test_rotate_kek_cli.py`: precondiciones de H-1; `--trim` exige `trim_ready`, un snapshot posterior a la rotación y `RECORTAR`.
- `tests/cli/test_retire_local_kek_cli.py`:
  - precondiciones (verify, kek reciente, snapshot);
  - `RETIRAR`;
  - borra `kek.bin` en `tmp_path`;
  - auditoría;
  - con filas `local` → 2;
  - después, el api arranca con `openbao` sin el archivo.

**Paso 47 · B2.4 · Verde.** `migration.py` (cada función de menos de 50 líneas; una transacción por llave; `SELECT ... FOR UPDATE`); los cuatro `cli_ops` (`migrate_provider.py`, `rotate_kek.py`, `trim_kek.py`, `retire_local_kek.py`; `cli_runtime`, sin keyring; `production_guard_error`; textos fijos; cada archivo de `cli_ops/` < 150 líneas (S4B-D95/D121: si no cabe, `TOPE_CLI_OPS` solo con decisión; S5-D97); los comandos nuevos en `register_ops`); `prod-smoke.sh --provider openbao` comprueba que no hay `kek.bin` en api ni worker (H-2.3).

**Paso 48 · B2.5 · Documentación.** RUNBOOK §13 (orden operativo de D18, ahora con snapshot y `retire-local-kek`); `docs/operacion/rotar-llave.md` (KEK de OpenBao, compromiso, `--trim`); `openbao.md`; bloque B2; cuaderno.

**Paso 49 · B2.6 · Gate**

1. `slice-gate.sh crypto tests/crypto/test_migrate_provider.py tests/crypto/test_rotate_kek.py`.
2. `security-reviewer` de B2.
3. Sello: `slice-gate.sh cli tests/cli/test_migrate_provider_cli.py tests/cli/test_rotate_kek_cli.py tests/cli/test_retire_local_kek_cli.py`.

**Paso 50 · B2.7 · Docker y evidencia (demo 1, parte)**

1. Buildx del api; recrear el ensayo.
2. `pg_dump` del ensayo; `export-kek` y `verify-kek-backup` del ensayo con el ayudante de pty de `prod-smoke.sh` (S4B-D192), desde el contenedor auxiliar Linux (la frase solo en memoria del ayudante); `run.sh` con snapshot.
3. `$DCE run --rm tools migrate-provider --from local --to openbao --as <admin del ensayo> --dry-run`, luego sin `--dry-run` con `MIGRAR` por stdin; una segunda corrida dice "nada que migrar"; `--verify` → 0. Variante de restauración (S5-D95, citada en V3): `openbao_restore_e2e.sh` repetido con una fila migrada, snapshot, `down -v` de `openbao-data`, restauración, desellado y `migrate-provider --verify` → 0.
4. `CRYPTO_PROVIDER=openbao` en el `.env` del ensayo; `$DCEB up -d --no-build --force-recreate api worker`; `GET /api/v1/members/{id}` en 8280 descifra.
5. `rotate-kek --as` → `rewrap` de las 8 filas; `run.sh`; `rotate-kek --trim --as` con `RECORTAR`.
6. `retire-local-kek --as` con `RETIRAR`.
7. `docker exec` de api y worker: `test ! -e /run/apex/keys/kek.bin`.
8. `SELECT provider, count(*) FROM crypto.crypto_keys GROUP BY 1` → 8 `openbao`.

**Paso 51 · B2.8 · Checkpoint.** `"S5-B2 migrate-provider reanudable con verificación previa y snapshot exigido, rotate-kek con rewrap y --trim aparte, retire-local-kek"`.

### S5-B3 · Estado sellado, `/health.crypto`, 503 `crypto_unavailable` y keyring del worker (US-136)

- **Cierra:** C3 (salud), C4 (worker), M-3 (guarda en ejecución), M-4, M-6 (clases del worker), L-7, D13, D14, D16, D20, D70, D86 (base), alerta `crypto_sealed`, E2, E3, E5, E6.
- **Depende de:** B2. **Migración:** ninguna.

**Paso 52 · B3.1 · Stubs.**

- `core/crypto/state.py`: `CryptoState = Literal["ok","sealed","unreachable","unknown"]` y `health_state(provider_status, keyring_loaded, *, threshold_ok) -> CryptoState`.
- `core/crypto/recovery.py`: `try_load(session_factory, settings, *, create_missing, classes=None) -> CryptoState`, `async poll_forever(...)`, `current_state()`, `is_loaded()`.
- `core/errors.py` (handler); `core/health.py` (`HealthOut.crypto`).
- `worker/runtime.py`: `worker_runtime(settings, *, with_crypto: bool = False)`.

**Paso 53 · B3.2 · Rojo de arquitectura.**

- `test_health_check_registrars.py`: `crypto` solo desde `main.py`.
- `test_crypto_bus_importers.py`: el `ARRANQUE` del worker suma `core.crypto.recovery`.
- `test_error_responses_in_openapi.py` y `test_error_codes_per_route.py`: el 503 común describe `busy` o `crypto_unavailable`, y `/health` conserva `HealthOut`.
- `test_core_import_direction.py`: `core/errors.py` solo importa `core/crypto/errors`.

**Paso 54 · B3.3 · Rojo de `core`**

- `tests/core/test_health_crypto.py`:
  - `health_state`, tabla completa;
  - `local` con keyring → `ok`;
  - `sealed` → 503 `degraded`;
  - caché de 5 s;
  - `/health` nunca llama `try_load` (contador);
  - `ENV=production` con umbral de desellado menor que 2 → `unreachable` y una línea crítica (M-3);
  - el cuerpo no trae versión ni clúster de OpenBao (L-7).
- `tests/core/test_crypto_recovery.py`:
  - sondeo cada 20 s con `FrozenClock`;
  - una línea de log y `alert("crypto_sealed")` por transición, y `crypto_recovered` al volver;
  - recuperación sin reiniciar;
  - cancelación en el `finally` del `lifespan`;
  - el worker carga solo las clases pedidas (M-6).
- `tests/core/test_startup_failure.py`, reescrita:
  - `sealed` o `unreachable` → arranque degradado;
  - `unwrap_failed`, `key_missing` o `forbidden` → el arranque aborta y nunca crea llaves (M-4);
  - sin KEK local y con `local` → aborta;
  - `gc.freeze()` también corre en modo degradado.
- `tests/core/test_errors_crypto_unavailable.py`: 503 con `{code: "crypto_unavailable", message: <texto fijo>}` y `Retry-After: 30`; otros `CryptoError` siguen igual.
- `tests/core/test_refresh_current_sealed.py`: `refresh_current` con el proveedor caído conserva el keyring y la petición no falla (M-4).
- E6: sobre `apex_roles`, como `apex_worker`, ¿el descifrado necesita `FOR SHARE`? La prueba `tests/migrations/test_worker_role_paths.py::test_worker_descifra_sin_update` fija la respuesta.

**Paso 55 · B3.4 · Rojo de `worker` y `members`**

- `tests/worker/test_worker_crypto_runtime.py`: `with_crypto` carga phone y email; sellado → estado `sealed` sin abortar; sin `INSERT` en `crypto_keys`.
- `tests/members/test_router_crypto_unavailable.py`: api sellado → `GET /members/{id}` da 503 `crypto_unavailable`; la lista (sin descifrar) da 200; login da 200.

**Paso 56 · B3.5 · Verde**

- `state.py`, `recovery.py`.
- `main.py`: `_startup` tolerante, `poll_forever` en `app.state`, registro de `crypto` (`critical=True`, `allowed`, `healthy={"ok"}`), cancelación.
- `core/health.py` (TTL de 5 s), `core/errors.py` (handler y descripción del 503), `core/security.refresh_current`, `keyring.current_keyring()` → `CryptoUnavailable("not_loaded")`.
- `worker/runtime.py` y `worker/main.py` (`try_load` al arrancar).
- `compose.yml`: `worker` monta `keys:ro` (base) o su token (overlay); el montaje `keys:ro` en `compose.yml` base es para `CRYPTO_PROVIDER=local`; `compose.openbao.yml` lo quita (H-2); se ajusta `test_compose_config.sh:86` y la línea "hasta el Sprint 5".
- `grants.sql`, solo si E6 lo exige.
- `scripts/ci/openbao-smoke.sh` (nuevo): D22 con D69; guarda la evidencia de `/health` en cada estado en `docs/scratch/ensayo/` o en el artefacto de CI.
- `ci.yml`: `prod-smoke` ejecuta `openbao-smoke.sh`.

**Paso 57 · B3.6 · Contrato y documentación**

- P-API (`HealthOut.crypto`, descripción del 503).
- RUNBOOK §13 (estado sellado, qué ve el usuario, monitores que miden solo el código HTTP).
- `openbao.md` y `docs/operacion/actualizar.md` (`deploy.sh` con sellado sale 0 con el aviso).
- Bloque B3; cuaderno.

**Paso 58 · B3.7 · Gate**

1. `slice-gate.sh core/errors tests/core/test_errors_crypto_unavailable.py`.
2. `slice-gate.sh core/security tests/core/test_refresh_current_sealed.py`.
3. `slice-gate.sh main tests/core/test_startup_failure.py tests/core/test_health_crypto.py`.
4. `slice-gate.sh worker tests/worker/test_worker_crypto_runtime.py`.
5. `slice-gate.sh members tests/members/test_router_crypto_unavailable.py`.
6. `slice-gate.sh crypto tests/core/test_crypto_recovery.py tests/migrations/test_worker_role_paths.py`.
7. `security-reviewer` de B3.
8. Sello: `slice-gate.sh core/health tests/core/test_health_crypto.py tests/core/test_health.py tests/core/test_crypto_recovery.py`.
9. Después del sello, sin tocar el árbol: `run-gates.sh` (primera de cuatro) con el ensayo detenido.

**Paso 59 · B3.8 · Docker y evidencia (demo 1 completa)**

1. Buildx del api; `$DC up -d --no-build --force-recreate api worker` (local, `crypto: ok`); `$DCEB up -d --no-build --force-recreate api worker`.
2. Sellar con el api arriba: `$DCE restart openbao` → `/health` 503 `crypto: sealed`, y `GET /members/{id}` sigue 200 (DEK en memoria, L-1).
3. Reinicio de servidor (D69): `restart api worker` → `GET /members/{id}` da 503 `crypto_unavailable`; `web` y `worker` siguen `healthy`; `deploy.sh` en modo prueba sale 0 con el aviso.
4. Desellar con 3 llaves → `crypto: ok` en 25 s o menos (cronometrado); `GET` da 200.
5. `bash scripts/ci/openbao-smoke.sh` en `apex-smoke` desde el contenedor auxiliar Linux → verde.
6. Evidencia de `/health` en los tres estados al cuaderno.

**Paso 60 · B3.9 · Checkpoint.** `"S5-B3 estado sellado: arranque degradado, /health.crypto, 503 crypto_unavailable, sondeo de 20 s y keyring limitado del worker"`.

### S5-B4 · Canales: `core/mail.py`, `TelegramAlertSink` y `settings.channels` (US-122, US-125 parcial, US-126)

- **Cierra:** parte de C5, M-7 a/b/c, M-8, D28, D29, D30, D64, D78, E10, E13.
- **Depende de:** B3. **Migración:** ninguna.

**Paso 61 · B4.1 · Stubs.**

- `core/mail.py`: `MailMessage`, `MailResult(ok, error_code)`, `MAIL_ERROR_CODES = ("timeout","auth","refused","invalid_recipient","unknown")`, `async send_mail(settings, message)`, `mail_configured(settings)`.
- `core/alerts_telegram.py`: `TelegramAlertSink`, `render_message(code, context, front_base_url) -> str`, `register_from_settings(settings) -> bool`, `async flush()`.
- `settings/schemas.py`: `ChannelsSettings`. `settings/service.py`: `channels_credentials_present(settings) -> dict[str,bool]`.
- `scripts/dev/telegram_fake.py`.

**Paso 62 · B4.2 · Rojo de arquitectura.**

- `test_third_party_confinement.py`: `smtplib` solo en `core/mail.py`; `httpx` además en `core/alerts_telegram.py`.
- `test_core_import_direction.py`: `core/mail.py` y `core/alerts_telegram.py` no importan `app.modules`.
- `test_settings_no_secrets.py`: `channels`.
- `test_no_sensitive_in_logs.py`: una excepción de `httpx` con la URL `bot<token>` no deja el token en ningún registro; tampoco una tarea fallida sin esperar.

**Paso 63 · B4.3 · Rojo**

- `tests/core/test_mail.py`, con `smtp_falso`:
  - envío en texto plano;
  - `"Ana\r\nBcc: x"` en el asunto o en el nombre → rechazo (M-7a);
  - destinatario inválido → `invalid_recipient`;
  - `starttls` con verificación de certificado (contexto por defecto);
  - `none` rechazado fuera de `ENV=dev`;
  - timeout → `timeout`; autenticación fallida → `auth`;
  - `repr` sin `to` ni `body`;
  - sin HTML (M-7c).
- `tests/core/test_alerts_telegram.py`, con `telegram_transport`:
  - `render_message` para `job_failed`, `backup_unhealthy`, `crypto_sealed`, `crypto_recovered` y `notify_summary` (solo enteros y el enlace a `/avisos/hoy`; sin nombres);
  - sin `parse_mode`;
  - la tarea atrapa todo y registra solo el tipo (M-8);
  - `flush` espera las pendientes;
  - sin token o sin chat no se registra.
- `tests/core/test_alerts.py`: `ALERT_CONTEXT_KEYS` suma `generados`, `enviados`, `fallidos`, `omitidos` y `pendientes`.
- `tests/settings/test_channels_schema.py`, `test_channels_router.py` y `test_channels_service.py`:
  - E10 confirmado: el router de secciones es genérico;
  - `GET` y `PATCH /settings/channels` admin; coach con 403 en `PATCH`;
  - claves extra → 422;
  - `credentials_present` sin valores;
  - cubeta `admin-write`.

**Paso 64 · B4.4 · Verde.**

- `core/mail.py`, `core/alerts_telegram.py`, `core/alerts.py`.
- `main.py` y `worker/main.py` (`register_from_settings`; `flush` en el apagado y en `--run-once`).
- `settings` (`ENABLED_SECTIONS`, `SECTION_REGISTRY`, `SECTION_VIEWS`, `SECTION_DEFAULTS`).
- `compose.dev.yml`: `mailpit` y `telegram-fake` (perfil `avisos`, por digest, sin puertos salvo `127.0.0.1:8025` de Mailpit); `test_images_pinned.sh` y `test_compose_config.sh` (servicios solo en desarrollo, nunca en `compose.yml`).

**Paso 65 · B4.5 · Contrato y documentación.** P-API (`ChannelsSettings`); `docs/operacion/avisos.md` (SMTP de solo envío con tope diario; Telegram con chat del equipo; nunca datos de socios); P-MAIL en RUNBOOK §13; cuaderno.

**Paso 66 · B4.6 · Gate**

1. `slice-gate.sh core/mail tests/core/test_mail.py`.
2. `slice-gate.sh core/alerts_telegram tests/core/test_alerts_telegram.py`.
3. `slice-gate.sh core/alerts tests/core/test_alerts.py`.
4. `slice-gate.sh main tests/core/test_alerts_telegram.py`.
5. `bash scripts/ci/test_compose_config.sh && bash scripts/ci/test_images_pinned.sh`.
6. `security-reviewer` de B4.
7. Sello: `slice-gate.sh settings tests/settings/test_channels_schema.py tests/settings/test_channels_router.py tests/settings/test_channels_service.py`.

**Paso 67 · B4.7 · Docker y evidencia.**

1. `$DC --profile avisos up -d mailpit telegram-fake`.
2. Script en el contenedor `tools` (desarrollo, `ENV=dev`) que llama `send_mail` hacia Mailpit; `curl` a la API de Mailpit muestra un mensaje en texto plano.
3. `alert("notify_summary", ...)` con `TELEGRAM_API_BASE=http://telegram-fake:8081` en el `worker --run-once` de prueba (`tools`); `$DC logs telegram-fake` muestra el JSON sin nombres; `$DC logs api worker | grep -c bot` da 0.
4. `GET /settings/channels` en 8181.
5. `$DC --profile avisos stop`.

**Paso 68 · B4.8 · Checkpoint.** `"S5-B4 correo SMTP con smtplib y STARTTLS, TelegramAlertSink sin datos personales, settings.channels con credentials_present, Mailpit y telegram-fake de desarrollo"`.

### S5-B5 · Preferencias de canal y contacto con `fields` (US-123)

- **Cierra:** parte de C5, D31, D32, E6 (contacto).
- **Depende de:** B4. **Migración:** `0016_member_channel_preferences`.

**Paso 69 · B5.1 · P-MIG y stubs.** Volcado `antes-0016`; `stop api worker`. Stubs:

- `members/models.MemberChannelPreference` (`__audited__`, `__audit_subject__="member_id"`);
- `rules.effective_channels(active, inactive, has_consent) -> frozenset[str]`;
- `service.channels_for(session, member_ids) -> dict[UUID, frozenset[str]]`, `get_channels(session, member_id) -> ChannelsOut`, `set_channels(session, member_id, items, by) -> ChannelsOut`;
- `schemas.ChannelsOut`, `ChannelsPatch`; `exceptions.InvalidField`, `MemberNotContactable`.

**Paso 70 · B5.2 · Rojo**

- `tests/migrations/test_0016_member_channel_preferences.py`: FK, CHECK de canal, único `(member_id, channel)`, ciclo.
- `tests/members/test_channels_rules.py`: tabla de verdad completa (sin consentimiento → vacío; WhatsApp por defecto; el correo exige fila activa y consentimiento).
- `tests/members/test_channels_service.py`: lectura por lote; `set` con socio dado de baja → 409 `member_deleted`; emite `MemberUpdated` sin valores.
- `tests/members/test_channels_router.py`: admin y coach; member → 403; cubeta `notifications-write`; `no-store`.
- `tests/members/test_contact_fields.py`: `fields={"phone"}` descifra y audita solo el teléfono; campo desconocido → `InvalidField`; `notify` sin consentimiento → `MemberNotContactable`; `load_only`.
- `tests/architecture/test_contact_callers.py`: se reescribe renombrando `test_contact_callers_esta_vacio_en_el_sprint_4a` por una prueba que fija `CONTACT_CALLERS == frozenset({"app.modules.notifications.service"})` (el único archivo) y mantiene la regla de :113, que no exige que exista un llamador (S5-D99).
- `test_audited_tables.py`, `test_audit_subject.py`, `test_writes_have_user_limit.py`, `test_user_limits_catalog.py` (cubeta `notifications-write` con ruta), `test_db_grants.py` (tabla nueva: api `S I U`, worker `S`).

**Paso 71 · B5.3 · Verde de `0016`.** P-MIG pasos 3 a 8; `grants.sql`, `revoke.sql` y `test_db_grants.py` (P-ROL).

**Paso 72 · B5.4 · Verde de `members`.** `rules.py`, `service.py` (debe quedar por debajo de 800 líneas; se mide), `router.py`, `schemas.py`, `contact.py`, `exceptions.py`; `core/ratelimit.py` y `config` (`notifications-write`); `tests/conftest.py` (limpieza).

**Paso 73 · B5.5 · Contrato y documentación.** P-API; RUNBOOK §4 (consentimiento y opt-in; importados sin consentimiento no reciben avisos); cuaderno.

**Paso 74 · B5.6 · Gate**

1. `slice-gate.sh architecture tests/architecture/test_contact_callers.py tests/architecture/test_audited_tables.py tests/architecture/test_user_limits_catalog.py`.
2. `database-reviewer` y `security-reviewer`, en paralelo.
3. Sello: `slice-gate.sh members tests/members/test_channels_rules.py tests/members/test_channels_service.py tests/members/test_channels_router.py tests/members/test_contact_fields.py tests/members/test_service_contact.py tests/migrations/test_0016_member_channel_preferences.py tests/migrations/test_db_grants.py`.

**Paso 75 · B5.7 · Docker y evidencia.** `restart api worker`; `\d members.member_channel_preferences`; buildx; el ensayo migra `0016` y corre `dbsetup` y `test_db_roles`; `PATCH /members/{id}/channels` contra el ensayo; `audit_log` con `subject_member_id`.

**Paso 76 · B5.8 · Checkpoint.** `"S5-B5 preferencias de canal con consentimiento obligatorio y opt-in de correo; contact_for_notification con fields y load_only"`.

### S5-B6 · `notifications`: plantillas, reglas y siembra (US-120, US-121)

- **Cierra:** parte de C5, parte de C6 (siembra), D23, D24 (plantillas y reglas), D25, D47 (parte).
- **Depende de:** B5. **Migración:** `0017_notification_templates`, `0018_notification_rules`.

**Paso 77 · B6.1 · P-MIG y stubs.** Volcado `antes-0017`; `stop api worker`. Stubs:

- módulo `notifications` (`__init__`, `models`, `schemas`, `exceptions`, `rules`, `templates`, `rules_crud`, `router`, `service`) con las firmas puras del blueprint B6;
- `main.MODULES` lo registra después de `memberships` y antes de `dashboard`;
- `migrations/env.py` importa sus modelos;
- `core/db.APP_SCHEMAS` suma `notifications`;
- `tests/factories/notifications.py`.

**Paso 78 · B6.2 · Rojo de arquitectura.**

- `test_audit_module.py` (`MODULES`); `test_audited_tables.py` (`PENDING_AUDITED` pasa a requerida para las dos tablas).
- `test_no_cross_models.py` (privados de `notifications`); `test_every_route_has_role.py`; `test_no_store_routes.py` (router con `no_store`).
- `test_list_routes_use_page_params.py`; `test_writes_have_user_limit.py`.
- `test_service_import_graph.py` (`notifications → settings`); `test_no_cross_schema_sql.py` y `test_sql_literals_constant.py` (`ESQUEMAS` suma `notifications`).
- `test_events_without_pii.py` (preparado para B7).

**Paso 79 · B6.3 · Rojo**

- `tests/migrations/test_0017_notification_templates.py` y `test_0018_notification_rules.py`: CHECK de `trigger`, `channel` y signo del desfase; único parcial; FK; ciclos.
- `tests/notifications/test_rules_pure.py`: `render` con `{nombre} {plan} {vence} {dias}`, `{{`/`}}`, variable desconocida → `TemplateError` con `field`; `validate_rule`; `target_dates`; `days_value`; `can_skip`; `next_attempt_allowed`.
- `tests/notifications/test_templates_service.py`: 409 `template_name_taken`; `preview`.
- `tests/notifications/test_rules_service.py`: 409 `duplicate_active_rule`.
- `tests/notifications/test_router_templates_rules.py`:
  - `POST /notification-templates/preview` registrada antes de `/{id}`;
  - el admin escribe; el coach lee y recibe 403 al escribir; member → 403;
  - cubeta `notifications-write`; listas con `q` y paginación.
- `tests/notifications/test_seed_defaults.py`: dos plantillas y cinco reglas; idempotente; auditado.
- `tests/cli/test_seed_notifications_cli.py`: `seed-notifications --as`; `seed` lo invoca.
- `test_db_grants.py`: plantillas y reglas (api `S I U`, worker `S`).

**Paso 80 · B6.4 · Verde de migraciones.** P-MIG pasos 3 a 8 para `0017` y luego para `0018` (dos ciclos); `grants.sql` (las cuatro sentencias de esquemas más la matriz), `revoke.sql`, `test_db_grants.py`; limpieza en `tests/conftest.py`.

**Paso 81 · B6.5 · Verde del módulo y del CLI.** Módulo (archivos de menos de 600 líneas); `cli_ops/seed_notifications.py` con `seed-notifications` (archivo aparte de `notify.py`, que nace en B7; cada archivo de `cli_ops/` < 150 líneas (S4B-D95/D121: si no cabe, `TOPE_CLI_OPS` solo con decisión; S5-D97); registrado en `register_ops`); `cli.py` (`seed` llama `notifications.service.seed_defaults`).

**Paso 82 · B6.6 · Contrato y documentación.** P-API; `avisos.md` (plantillas, reglas, variables); `CLAUDE.md`; cuaderno.

**Paso 83 · B6.7 · Gate**

1. `slice-gate.sh cli tests/cli/test_seed_notifications_cli.py`.
2. `slice-gate.sh architecture tests/architecture/test_audit_module.py tests/architecture/test_service_import_graph.py tests/architecture/test_no_cross_models.py`.
3. `database-reviewer` y `security-reviewer`, en paralelo.
4. Sello: `slice-gate.sh notifications tests/notifications/test_rules_pure.py tests/notifications/test_templates_service.py tests/notifications/test_rules_service.py tests/notifications/test_router_templates_rules.py tests/notifications/test_seed_defaults.py tests/migrations/test_0017_notification_templates.py tests/migrations/test_0018_notification_rules.py tests/migrations/test_db_grants.py`.

**Paso 84 · B6.8 · Docker y evidencia.** `restart api worker`; `\dn notifications`; buildx; el ensayo migra `0017` y `0018`, `dbsetup`; `$DCE run --rm tools seed-notifications --as <admin>` dos veces (la segunda no cambia nada); `GET /notification-rules`.

**Paso 85 · B6.9 · Checkpoint.** `"S5-B6 módulo notifications: plantillas y reglas con siembra idempotente auditada"`.

### S5-B7 · Generar, hoy, WhatsApp, omitir e historial (US-124, US-127 a US-130)

- **Cierra:** parte de C5 y C6, M-6 (ORM), M-9, D26, D27, D71, D92, E7.
- **Depende de:** B6. **Migración:** `0019_notifications`.

**Paso 86 · B7.1 · P-MIG y stubs.**

- Volcado `antes-0019`; `stop api worker`.
- E7: firma real de la función pura de estado por fecha en `memberships`.
- Stubs:
  - `models.Notification` (`__audited__`, `__audit_subject__`);
  - `generate.py`, `queries.py`, `whatsapp.py` (`build_link(phone, text) -> str`), `sending.py` (firma), `channels/{base,email,whatsapp_link}.py`;
  - `service.py`: `generate_today`, `today_list`, `today_count`, `wa_link`, `skip`, `list`, `get`, `list_for_member`, los cuatro eventos;
  - `memberships/queries.py`: `notification_candidates(session, on_dates) -> list[NotificationCandidate]` y `has_current_or_future(session, member_ids, today) -> set[UUID]`, reexportadas; `NotificationCandidate` en `memberships/schemas.py`.

**Paso 87 · B7.2 · Rojo**

- `tests/migrations/test_0019_notifications.py`: `membership_id NOT NULL`; único `(rule_id, membership_id, target_date)`; CHECK de `status`, `attempts` y `skip_reason`; índices; ciclo.
- `tests/memberships/test_notification_candidates.py`: lote, sin JOIN entre esquemas, estado por fecha.
- `tests/notifications/test_generate.py`:
  - dos corridas → sin duplicados;
  - ventana de 15 días;
  - no se avisa como vencido a quien renovó (N-35);
  - sin consentimiento → no genera y se cuenta en `sin_consentimiento`;
  - canal según preferencia;
  - cruce de medianoche;
  - cada fila nueva deja `insert` en `audit_log` (M-6, D71);
  - `NotificationQueued` solo para filas nuevas;
  - lotes de 200.
- `tests/notifications/test_today_and_skip.py`:
  - hoy incluye `pending`, `failed` y los `failed` anteriores;
  - `skip` con motivo de 3 a 500 caracteres;
  - 409 `notification_closed` si ya está `sent` o `skipped`;
  - el evento no lleva el motivo.
- `tests/notifications/test_wa_link.py`:
  - `POST` (M-9): marca `sent` una sola vez;
  - cada llamada audita `reveal` con `purpose=notify` y escribe `crypto_ops`;
  - 422 `member_without_phone`; 409 si está omitido o el canal es otro;
  - `no-store`; cubeta `members-reveal*`;
  - el teléfono solo aparece en la URL;
  - prefijo `57` con 10 dígitos.
- `tests/notifications/test_history_and_member_tab.py`: filtros, `q` (D92), socio dado de baja incluido (N-20).
- `tests/notifications/test_router_notifications.py`: rutas, roles, `/today` registrada antes de `/{id}`.
- Arquitectura: `test_events_without_pii.py`, `test_contact_callers.py` (ya en verde), `test_service_import_graph.py` (`notifications → members`, `memberships`), `test_reveal_single_door.py`, `test_no_physical_delete.py`.
- `test_db_grants.py`: `notifications.notifications` (api `S I U`; worker `S I` más `U` por columna).

**Paso 88 · B7.3 · Verde.** P-MIG pasos 3 a 8 de `0019`; grants (P-ROL); generación por ORM (D71); `wa_link` y `skip`; consultas; `whatsapp.build_link`; los canales; docstring de `memberships/events.py`.

**Paso 89 · B7.4 · Verde de cubetas y limpieza.** `core/ratelimit.py` (`POST wa-link` con `members-reveal*`; `skip` con `notifications-write`); limpieza en `tests/conftest.py`.

**Paso 90 · B7.5 · Contrato y documentación.** P-API (incluido `POST /notifications/{id}/wa-link`); `avisos.md` (operación diaria); RUNBOOK §13; cuaderno.

**Paso 91 · B7.6 · Gate**

1. `slice-gate.sh memberships tests/memberships/test_notification_candidates.py`.
2. `slice-gate.sh architecture tests/architecture/test_events_without_pii.py tests/architecture/test_contact_callers.py tests/architecture/test_service_import_graph.py tests/architecture/test_reveal_single_door.py`.
3. `database-reviewer` y `security-reviewer`, en paralelo.
4. Sello: `slice-gate.sh notifications tests/notifications/test_generate.py tests/notifications/test_today_and_skip.py tests/notifications/test_wa_link.py tests/notifications/test_history_and_member_tab.py tests/notifications/test_router_notifications.py tests/migrations/test_0019_notifications.py tests/migrations/test_db_grants.py`.

**Paso 92 · B7.7 · Docker y evidencia.** `restart api worker`; `\d notifications.notifications`; buildx; el ensayo migra `0019` y corre `dbsetup`. En el ensayo:

- `$DCE run --rm tools notify --generate-only --as <admin>` dos veces → mismo conteo;
- `GET /notifications/today`;
- `POST wa-link` → URL `https://wa.me/57...` y `sent`; una segunda llamada no cambia `sent_at`;
- `skip` con motivo;
- `audit_log` con `reveal` y `purpose=notify`.

Antes, `notify` del CLI se comprueba con el job de B8 pendiente: en B7 la generación se expone por un comando provisional `notify --generate-only`, que nace aquí en `cli_ops/notify.py` y se completa en B8, con prueba en `tests/cli/test_notify_cli.py` desde B7 porque `cli_ops/notify.py` es nuevo.

**Paso 93 · B7.8 · Checkpoint.** `"S5-B7 avisos del día idempotentes y auditados, por avisar hoy, POST wa-link, omitir con motivo e historial"`.

### S5-B8 · Job `notify`, envío de correo y resumen (US-124, US-125, US-126)

- **Cierra:** parte de C4, C6, M-6 (`claim_run`), D35, D86, L-5.
- **Depende de:** B7. **Migración:** ninguna.

**Paso 94 · B8.1 · Stubs (con el worker detenido).** `worker/jobs/notify.py` (`NAME="notify"`, `async run(ctx) -> JobResult`); `sending.send_pending(session_factory, today, *, load_contact, channel, max_attempts) -> SendSummary`; `channels/email.EmailChannel`; `cli_ops/notify.py` completo (`--generate-only`, `--send-only`, `--as`, `claim_run`; cada archivo de `cli_ops/` < 150 líneas (S4B-D95/D121: si no cabe, `TOPE_CLI_OPS` solo con decisión; S5-D97), con las ayudas en `modules/notifications/service.py`; comandos en `register_ops`); `core/jobs.DETAIL_KEYS` con `generados`, `ya_renovaron`, `sin_consentimiento`, `sin_reglas`, `enviados`, `fallidos`, `omitidos`, `pendientes`, `sellado`.

**Paso 95 · B8.2 · Rojo**

- `tests/worker/test_notify_job.py`:
  - tres fases;
  - `JOBS == [expirations, notify, backup_check]` con sus `timeout_s`;
  - detalles solo enteros;
  - dos corridas el mismo día sin duplicar;
  - `claim_run('notify')` compartido con el CLI: un segundo proceso no envía el mismo aviso;
  - `alert("notify_summary")` con enteros;
  - `flush`.
- `tests/worker/test_notify_sealed.py`: `send` omitido, `sellado=1`, `ok`, `alert("crypto_sealed")`.
- `tests/notifications/test_sending.py`:
  - `FOR UPDATE SKIP LOCKED`;
  - envío fuera de la transacción;
  - `attempts` llega como máximo a 3;
  - `last_error` solo con códigos;
  - el cambio de estado por ORM deja `update` en `audit_log` (M-6);
  - ningún log con correo, nombre ni cuerpo; solo `notification_id`;
  - un corte entre el envío y la marca → el correo se repite una vez como máximo (documentado).
- `tests/notifications/test_email_channel.py`: sin credenciales → `skipped` con `canal_no_configurado`.
- `tests/cli/test_notify_cli.py`: `--generate-only`, `--send-only`, `--as`.
- `tests/architecture/test_worker_boundaries.py`: `jobs/notify.py` solo importa `service` (`notifications`, `memberships`).
- `test_notifications_details_clean.py` (nueva).

**Paso 96 · B8.3 · Verde.** `notify.py`, `sending.py`, `email.py`, `cli_ops/notify.py` (< 150 líneas, S5-D97), `core/jobs.py`, `worker/jobs/__init__.py` y `worker/main.py` (`flush`).

**Paso 97 · B8.4 · Verde de infraestructura.** `compose.yml` (`environment` del worker con `SMTP_*` y `TELEGRAM_*`, ya preparado en W0-3; solo se verifica); `grants.sql` (sin cambio; se confirma `U` por columna).

**Paso 98 · B8.5 · Documentación.** `avisos.md` (entrega "al menos una vez"; el proveedor SMTP como encargado del tratamiento según la Ley 1581, L-5; resumen diario); RUNBOOK §11 y §13 (`--run-once notify`, `--status notify`); cuaderno.

**Paso 99 · B8.6 · Gate**

1. `slice-gate.sh notifications tests/notifications/test_sending.py tests/notifications/test_email_channel.py`.
2. `slice-gate.sh cli tests/cli/test_notify_cli.py`.
3. `slice-gate.sh core/jobs tests/worker/test_jobs_core.py`.
4. `security-reviewer` de B8.
5. Sello: `slice-gate.sh worker tests/worker/test_notify_job.py tests/worker/test_notify_sealed.py tests/worker/test_jobs_core.py tests/worker/test_runner.py`.
6. Después del sello: `run-gates.sh` (segunda de cuatro).

**Paso 100 · B8.7 · Docker y evidencia (demo 2, D79)**

1. `restart worker`.
2. `createdb apex_avisos_demo` en `db_test`; `tools` con `-e DATABASE_URL=<apex_avisos_demo>`: `alembic upgrade head`, `init-keys`, `seed --demo`, `seed-notifications`.
3. Api efímero en 8191 hacia esa base: socio A con consentimiento y opt-in de correo; socio B con consentimiento y sin opt-in.
4. `$DC --profile avisos up -d mailpit telegram-fake`.
5. `$DC run --rm -e DATABASE_URL=... worker python -m app.worker.main --run-once notify` dos veces: sin duplicados; Mailpit con exactamente un correo (A) y ninguno a B; `telegram-fake` con el resumen en enteros y sin nombres.
6. `--status notify`.
7. Ensayo: `--run-once notify` ×2, correo omitido por `canal_no_configurado`.
8. `drop database apex_avisos_demo`.

**Paso 101 · B8.8 · Checkpoint.** `"S5-B8 job notify con generar, enviar y resumir; claim_run compartido; correo solo con opt-in y consentimiento; sellado como detalle"`.

### S5-B9 · Correos de cuenta (US-131)

- **Cierra:** parte de C5, M-7 d/e, D37, D38, D91, E14.
- **Depende de:** B8. **Migración:** ninguna.

**Paso 102 · B9.1 · Stubs y E14.** `auth/mail_texts.py` (`activation_mail(url, sender) -> tuple[str,str]`, `reset_mail(url, sender)`); `links.forgot_deliver(email, *, session_factory, settings)` con semáforo de 4 y cola de 32; `email_sent: bool` en `CreateUserOut` e `IssuedLinkOut`. E14: pruebas actuales que fijan "no lee la base" en `tests/auth/test_reset_forgot*.py`.

**Paso 103 · B9.2 · Rojo**

- `tests/auth/test_forgot_delivery.py`:
  - mismo 204 y tiempos comparables con cuenta existente y sin ella (medianas dentro de un margen de 50 ms sobre 20 corridas, con `wait_floor`);
  - una cuenta no elegible no recibe correo;
  - un fallo del correo no cambia la respuesta;
  - la cola llena se descarta con un log de tipo;
  - el enlace nunca aparece en los logs.
- `tests/auth/test_user_link_mail.py`: `email_sent` verdadero o falso en el alta y en el reenvío.
- `tests/auth/test_mail_texts.py`: texto fijo (N-36).
- `tests/auth/test_reset_forgot*.py`: se reescriben (S2-D36 enmendada).
- `test_no_sensitive_in_logs.py` y `test_service_import_graph.py` (sin `auth → notifications`).

**Paso 104 · B9.3 · Verde.** `links.py`, `users.py`, `schemas.py`, `router.py` (`BackgroundTasks`), `mail_texts.py`.

**Paso 105 · B9.4 · Contrato y documentación.** P-API (`email_sent`); RUNBOOK §2 (recuperación por correo); bloque B9 (enmienda de S2-D36); cuaderno.

**Paso 106 · B9.5 · Gate y Docker**

1. `security-reviewer` de B9.
2. Sello: `slice-gate.sh auth tests/auth/test_forgot_delivery.py tests/auth/test_user_link_mail.py tests/auth/test_mail_texts.py tests/auth/test_reset_forgot.py tests/auth/test_reset_forgot_router.py`.
3. Evidencia sobre `apex_avisos_demo` recreada como en B8, con su api efímero y Mailpit: `POST /auth/forgot` de una cuenta existente → correo en Mailpit con el texto fijo; inexistente → nada; `POST /users` → `email_sent: true`. Después, `drop` de la base.

**Paso 107 · B9.6 · Checkpoint.** `"S5-B9 forgot y activación por correo en segundo plano acotado, sin canal de tiempos; email_sent en el alta y el reenvío"`.

### S5-B10 · KPI `notifications_today` y `members_without_consent` (US-132)

- **Cierra:** D39, D80.
- **Depende de:** B9. **Migración:** ninguna.

**Paso 108 · B10.1 · Rojo.** `tests/dashboard/test_service.py` (`notifications_today` igual a `today_count`; `members_without_consent` igual al conteo; finanzas sin cambio); `tests/dashboard/test_router.py`; `tests/members/test_count_without_consent.py`; `test_read_modules.py` y `test_service_import_graph.py` (`dashboard → notifications`).

**Paso 109 · B10.2 · Verde.** `dashboard/service.py` y `schemas.py`; `members.service.count_without_consent`.

**Paso 110 · B10.3 · Contrato y documentación.** P-API; cuaderno.

**Paso 111 · B10.4 · Gate y evidencia.** Sello: `slice-gate.sh dashboard tests/dashboard/test_service.py tests/dashboard/test_router.py tests/members/test_count_without_consent.py`. `GET /dashboard` del ensayo con los dos campos llenos.

**Paso 112 · B10.5 · Checkpoint.** `"S5-B10 KPI notifications_today y members_without_consent en el tablero"`. **Desde aquí nace el worktree del front (sección 3).**

### S5-B11 · Recibo PDF propio (US-137)

- **Cierra:** C7 (recibo), M-11, D40, D65.
- **Depende de:** B10. **Migración:** ninguna.

**Paso 113 · B11.1 · Stubs.** `core/pdf.py` (`PdfLine(text, x_mm, y_mm, size, bold=False)`, `render_text_pdf(lines, *, title) -> bytes`, `MAX_PDF_BYTES = 100_000`); `payments/receipt.py` (`format_cop`, `format_bogota`, `receipt_context`, `render_receipt(ctx) -> bytes`); `payments.service.receipt_pdf(session, payment_id, by) -> bytes`.

**Paso 114 · B11.2 · Rojo**

- `tests/core/test_pdf.py`, con `pypdf`:
  - el texto extraído es íntegro con `(`, `)`, `\`, tildes y `ñ`;
  - U+202E y un emoji → `?`; NUL → `?`;
  - ausencia de `/JavaScript`, `/OpenAction`, `/AA`, `/URI`, `/Launch`, `/Annots` y `/EmbeddedFile`;
  - `xref` válido (lo abre `pypdf` estricto);
  - tamaño de 100 KB o menos con 200 líneas.
- `tests/payments/test_receipt_pure.py`: `120.000`; hora de Bogotá; cruce de medianoche; anulado con motivo; sin referencia; truncado (nombre a 60, referencia a 40).
- `tests/payments/test_receipt_service.py`: frase fija presente; documento, teléfono y correo ausentes; no usa el bus (funciona con el sistema sellado); auditoría `download` con `record_id` y `subject_member_id`; una sola fila por descarga.
- `tests/payments/test_router_receipt.py`: admin y coach; member → 403; 404; `application/pdf`; `attachment; filename=recibo-<8 hex>.pdf`; `no-store`; `nosniff`; ruta antes de `/{id}`.
- `test_no_store_routes.py` y `test_core_import_direction.py` (`core/pdf.py` sin `app.modules`).

**Paso 115 · B11.3 · Verde.** `core/pdf.py` (menos de 300 líneas); `receipt.py`; `service.py`; `router.py`.

**Paso 116 · B11.4 · Revisión de M-11.** `security-reviewer` específico del escritor de PDF (escapes, claves prohibidas, tamaño). Los hallazgos se corrigen antes del gate.

**Paso 117 · B11.5 · Contrato y documentación.** P-API; BRECHAS §13 (recibo sin logo, dueño v0.3); RUNBOOK §10; cuaderno.

**Paso 118 · B11.6 · Gate y evidencia.**

1. `slice-gate.sh core/pdf tests/core/test_pdf.py`.
2. Sello: `slice-gate.sh payments tests/payments/test_receipt_pure.py tests/payments/test_receipt_service.py tests/payments/test_router_receipt.py`.
3. Buildx; en el ensayo, descargar el recibo y extraer el texto en el contenedor Linux con `pypdf`: frase fija presente. `SELECT action FROM audit.audit_log ... 'download'`.

**Paso 119 · B11.7 · Checkpoint.** `"S5-B11 recibo PDF propio en core/pdf.py sin documento, auditado como download"`.

### S5-B12 · Exportaciones CSV (US-138, US-139)

- **Cierra:** C7 (CSV), M-10, D41, D42, D46, D60, D81, D82, L-6, E8, E9.
- **Depende de:** B11. **Migración:** ninguna.

**Paso 120 · B12.1 · Stubs y E8/E9.** `core/export.py` (`escape_formula`, `csv_stream(header, rows, *, delimiter=";")`, `single_flight(user_id)`, `ExportInProgress`); `members/exports.py` y `payments/exports.py` (privados; se suman al conjunto exacto de `test_no_cross_models`); `_consulta(session, filters)` compartida por la lista y la exportación; `MemberExportQuery` y `PaymentExportQuery`; cubetas `export`, `export-hour` y `export-day`.

**Paso 121 · B12.2 · Rojo de `core` y arquitectura**

- `tests/core/test_export.py`: escape de `=`, `+`, `-`, `@`, tabulador y retorno de carro; `+57...` también recibe apóstrofo (L-6, documentado); enteros sin escape; BOM; `;`; comillas; `\r\n`; `single_flight` → `ExportInProgress`.
- `test_no_store_routes.py`; `test_list_routes_use_page_params.py` (excepción nombrada); `test_reveal_single_door.py`; `test_session_scope.py` (el generador no usa la sesión de la petición); `test_user_limits_catalog.py`; `test_core_import_direction.py`.

**Paso 122 · B12.3 · Rojo de `members`**

- `tests/members/test_export.py`:
  - columnas de N-29; filtros; dados de baja;
  - lotes de 500 por llave `(created_at, id)`;
  - `crypto_ops` con `count=500` y `purpose=export` por lote y clase;
  - fila `export` antes del primer byte (`filters`, `has_q`, `rows`, `fields`, IP) y fila de cierre con `completed` y `rows_sent`, también cuando se corta;
  - el texto de `q` nunca se guarda;
  - el coach recibe 403 sin ninguna fila nueva en `crypto_ops`;
  - sellado → 503 antes de las cabeceras;
  - más de 20.000 filas → 422 `export_too_large` antes de las cabeceras;
  - un segundo flujo → 409 `export_in_progress`;
  - cubetas.
- `tests/members/test_export_perf.py` (marcador `perf`): 1.000 socios en menos de 10 s.

**Paso 123 · B12.4 · Rojo de `payments`**

- `tests/payments/test_export.py`:
  - el CSV del mes suma, sobre los no anulados, exactamente `summary(month).total_cop` y `payments_count`, con datos que cruzan medianoche;
  - anulados presentes con `anulado=si`;
  - 422 en `from`;
  - no usa el bus (funciona sellado);
  - `reference` escapada;
  - lotes por llave `(paid_at, id)`.

**Paso 124 · B12.5 · Verde.** `core/export.py`, los dos `exports.py`, servicios, routers (las rutas `/export` registradas antes de `/{id}`), `core/ratelimit.py`, `core/config.py`, `.env.example` (ya en W0-3; se verifica), el `sed` de `ci.yml` (15).

**Paso 125 · B12.6 · Contrato y documentación.** P-API; RUNBOOK §4 y §10 (exportar, auditoría, tope, L-6); cuaderno.

**Paso 126 · B12.7 · Gate**

1. `slice-gate.sh core/export tests/core/test_export.py`.
2. `slice-gate.sh payments tests/payments/test_export.py`.
3. `security-reviewer` de B12.
4. Sello: `slice-gate.sh members tests/members/test_export.py tests/core/test_export.py`.
5. Después del sello: `run-gates.sh` (tercera de cuatro).

**Paso 127 · B12.8 · Docker y evidencia (demo 4)**

1. Buildx; recrear el ensayo.
2. `curl` con el token del admin del ensayo de `GET /members/export` y `GET /payments/export?from=<mes>&to=<mes>` hacia `docs/scratch/ensayo/`: BOM, `;`, fórmulas escapadas.
3. Suma de `monto` de los no anulados igual a `GET /payments/summary?month=` (con `awk`).
4. Auditoría: filas `export` de inicio y de cierre.
5. Un segundo `curl` simultáneo → 409.

**Paso 128 · B12.9 · Checkpoint.** `"S5-B12 exportaciones CSV de socios y pagos en streaming con escape de fórmulas, auditoría de inicio y cierre, un flujo por usuario y cuadre con summary"`.

## 6. Front (worktree `.claude/worktrees/sprint-05-front`; S5-F1 a F5)

**Reglas comunes:**

- `docs/design/` manda. Solo tokens; componentes compartidos en `shared/ui`; datos compartidos en `shared/data`; una feature nunca importa otra; React Hook Form con Zod; TanStack Query; `// DESIGN-GAP:` cuando falte algo.
- Vitest por página y componente, en claro y oscuro.
- Gate sellante: `SLICE_BASE=$(git merge-base HEAD main) bash scripts/workflow/slice-gate.sh web/<feature> <archivos>`.
- `security-reviewer` en cada F.
- `features.test.ts` pasa a 10 en F1.
- Antes de cada F: `git rebase feat/sprint-05-openbao-avisos-recibos` y `npm run gen:api` (sin diff).

### S5-F1 · Por avisar hoy (US-127, US-128)

**Paso 129 · F1.1 · Preparación.** Crear el worktree y la rama, `npm ci`, cuaderno `docs/scratch/sprint-05-front.md`.

**Paso 130 · F1.2 · Rojo.**

- `features.test.ts`: `notifications` habilitada, 10 en total.
- `features/notifications/api.test.ts`: `useToday`, `useWaLink` como `useMutation` con `gcTime 0`, `useSkip`.
- `TodayPage.test.tsx`: textos de `PorAvisarHoy.html`, estados vacío, carga y error; "Regenerar lista" con `DESIGN-GAP`.
- `SkipModal.test.tsx`: motivo de 3 a 500; botón deshabilitado si está vacío.
- `WaButton.test.tsx`: `window.open(url, "_blank", "noopener,noreferrer")` solo tras el 200; la URL no queda en el estado ni en la caché; objetivo táctil de 44 px.

**Paso 131 · F1.3 · Verde.** `features/notifications/{api,schemas}.ts`, `pages/TodayPage.tsx`, `components/{SkipModal,WaButton}.tsx`, `config/features.ts`.

**Paso 132 · F1.4 · E2E.** `web/tests/e2e/avisos.spec.ts` (preview) y `web/tests/e2e/stack/avisos.spec.ts` (WhatsApp y omitir contra el ensayo, en V5).

**Paso 133 · F1.5 · Documentación.** BRECHAS §13 (filas de F1) y el cuaderno del front.

**Paso 134 · F1.6 · Gate.** `security-reviewer`; sello: `slice-gate.sh web/notifications src/features/notifications/pages/TodayPage.test.tsx src/features/notifications/components/SkipModal.test.tsx src/features/notifications/components/WaButton.test.tsx src/features/notifications/api.test.ts src/config/features.test.ts`.

**Paso 135 · F1.7 · Checkpoint (en el worktree).** `"S5-F1 por avisar hoy con WhatsApp por POST y omitir con motivo"`.

### S5-F2 · Reglas, plantillas, historial y pestaña Canales (US-120 a US-122, US-129)

**Paso 136 · F2.1 · Rojo.** `RulesPage.test.tsx` (pestañas con `Tabs` existente, `SidePanel` con vista previa, coach en solo lectura); `HistoryPage.test.tsx` (`FilterBar` en la URL, `Pagination` con `offset`); `features/system/components/ChannelsSettingsForm.test.tsx` (insignia "Credenciales listas" o "Faltan credenciales en .env"; `?tab=canales`).

**Paso 137 · F2.2 · Verde.** Las dos páginas, `ConfigPage` (quinta pestaña) y la sección en `features/system/{api,schemas}.ts`.

**Paso 138 · F2.3 · E2E.** `settings-config.spec.ts` (pestaña Canales) y `avisos.spec.ts` (reglas).

**Paso 139 · F2.4 · Documentación.** BRECHAS §13 y el cuaderno del front.

**Paso 140 · F2.5 · Gate.** `slice-gate.sh web/system src/features/system/components/ChannelsSettingsForm.test.tsx`; `security-reviewer`; sello: `slice-gate.sh web/notifications src/features/notifications/pages/RulesPage.test.tsx src/features/notifications/pages/HistoryPage.test.tsx`.

**Paso 141 · F2.6 · Checkpoint.** `"S5-F2 reglas y plantillas, historial de envíos y pestaña Canales de Config"`.

### S5-F3 · Ficha del socio, preferencias e Inicio (US-123, US-130, US-132)

**Paso 142 · F3.1 · Rojo.** `features/notifications/tabs/NotificationsTab.test.tsx` (hija de la feature `notifications`, registrada como `membresias` y `pagos`, S3-D65; carga diferida; historial); `components/ChannelPreferences.test.tsx` (nota de consentimiento y de opt-in; interruptores con etiqueta de texto); `FutureKpis.test.tsx` y `dashboard` (tarjeta "Por avisar" con enlace a `/avisos/hoy`; "Nadie por avisar" en 0; `members_without_consent`).

**Paso 143 · F3.2 · Verde.** Pestaña habilitada (`isPageAvailable`), componentes, `FutureKpis` sin la fila vieja.

**Paso 144 · F3.3 · E2E y documentación.** `member-tabs.spec.ts` (pestaña Avisos), `home.spec.ts` (KPI); BRECHAS §13 (fila 25 y la pestaña).

**Paso 145 · F3.4 · Gate.** `slice-gate.sh web/dashboard src/features/dashboard/components/FutureKpis.test.tsx`; `slice-gate.sh web/members <pruebas de la ficha tocadas>`; `security-reviewer`; sello: `slice-gate.sh web/notifications src/features/notifications/tabs/NotificationsTab.test.tsx src/features/notifications/components/ChannelPreferences.test.tsx`.

**Paso 146 · F3.5 · Checkpoint.** `"S5-F3 pestaña Avisos de la ficha con preferencias de canal y KPI por avisar en Inicio"`.

### S5-F5 · Cuentas por correo y aviso de custodio (US-131, US-136)

**Paso 147 · F5.1 · Rojo.** `ForgotPage.test.tsx` ("Si el correo está registrado, te enviamos un enlace"; `DESIGN-GAP` de H-2 cerrado); `features/users` (`email_sent`: "Enviamos el enlace por correo" o el enlace copiable); `core/api/client.test.ts` (respuesta con `crypto_unavailable` → aviso global discreto); `shared/ui` aviso global (si no existe, se crea en `shared/ui` con el nombre de `DESIGN.md`).

**Paso 148 · F5.2 · Verde.** `ForgotPage` real (formulario con React Hook Form + Zod, respuesta constante "Si el correo está registrado, te enviamos un enlace", sin enumeración de cuentas); pantalla de usuarios/cuentas con el envío del correo de activación (`email_sent` o enlace copiable), estados de carga y de error, aviso global discreto de `crypto_unavailable`; pruebas de componentes de las tres piezas y `preview` de la pantalla.

**Paso 149 · F5.3 · E2E y documentación.** `users-activation.spec.ts` (stack); BRECHAS fila 230.

**Paso 150 · F5.4 · Gate.** `slice-gate.sh web/users <pruebas>`; `slice-gate.sh web/core src/core/api/client.test.ts`; `security-reviewer`; sello: `slice-gate.sh web/auth src/features/auth/pages/ForgotPage.test.tsx`.

**Paso 151 · F5.5 · Checkpoint.** `"S5-F5 recuperar y activar cuenta por correo, email_sent en Usuarios y aviso de custodio no disponible"`.

### S5-F4 · Recibo y exportaciones (US-137 a US-139); empieza tras el checkpoint de B12

**Paso 152 · F4.1 · Rebase y contrato.** `git rebase`, `npm run gen:api`.

**Paso 153 · F4.2 · Rojo.** `core/api/client.test.ts` (`api.blob` con timeout propio, sin almacenamiento, L-8); `shared/lib/download.test.ts`; `features/payments/components/ReceiptButton.test.tsx` (detalle y fila); los dos `ExportButton.test.tsx` (solo admin con `useCan`; `ConfirmModal` con "La descarga contiene datos personales y queda registrada en la auditoría"; filtros de la URL; estados 403, 409, 422 y 503 con el mensaje del api).

**Paso 154 · F4.3 · Verde.** `client.ts`, `shared/lib/download.ts` y los componentes.

**Paso 155 · F4.4 · E2E y documentación.** `stack/payments-receipt-export.spec.ts` y `stack/members-export.spec.ts` (contra el ensayo, en V5); BRECHAS §10.1 y §10.8.

**Paso 156 · F4.5 · Gate.** `slice-gate.sh web/core src/core/api/client.test.ts`; `slice-gate.sh web/shared src/shared/lib/download.test.ts`; `slice-gate.sh web/members <ExportButton>`; `security-reviewer`; sello: `slice-gate.sh web/payments src/features/payments/components/ReceiptButton.test.tsx src/features/payments/components/ExportButton.test.tsx`.

**Paso 157 · F4.6 · Checkpoint.** `"S5-F4 recibo PDF y exportaciones CSV con confirmación y descarga por api.blob"`.

## 7. Validación del sprint

Evidencia en `docs/scratch/sprint-05.md`, bloque "Validación V1–V12", sin credenciales ni llaves.

**V1 · Fusión y documentos**

1. Fusionar `feat/sprint-05-front` con el árbol limpio (`GIT_EDITOR=true git merge --continue` si el hook falla, o lotes de 40 archivos). `npm run gen:api` y la prueba de contrato sin deriva. `git worktree remove`.
2. `grep -rn "DESIGN-GAP" web/src` contra BRECHAS §13.
3. Documentos al día: `CLAUDE.md`, RUNBOOK (§2, §4, §6, §7, §10 a §13), `SPRINT-05.md`, DECISIONES, `CHANGELOG.md`, `docs/operacion/{openbao,avisos,rotar-llave,respaldo-y-restauracion,instalar-en-servidor,actualizar}.md`, ADR-002 y ADR-005.
4. Criterio: `grep -rn` sin `reportlab`, `aiosmtplib`, `0030_`, `GET /notifications/{id}/wa-link`, `wrap(key_ref`, `anyio.to_thread` ni `uv run python -m app.cli` fuera de `docs/ddd/blueprints` e `impacto`.

**V2 · Stack de cero y Alembic**

1. Buildx de api, web y backup con `GIT_SHA`. `$DC up -d --no-build --force-recreate`: seis contenedores `healthy`.
2. Ciclo en `db_test`: `tests/core/test_migrations.py tests/migrations`.
3. `apex-db-1` (P-MIG): `$DC stop worker`, `downgrade 0014_audit_log_triggers_always`, `upgrade head` (`0019`) y `current`. Se pierden los avisos de desarrollo generados por el worker; se anota. Consulta de `tgenabled`.
4. P-ROL único: `$DC --profile prod-init run --rm --no-deps dbsetup` y `test_db_roles.sh` contra `apex-db-1`.
5. Ensayo de producción desde cero: `$DCE down -v` y `up` con `apex_owner`, P-BAO, migrar proveedor, overlay.
6. Smoke de producción en Linux con `--provider openbao`.

**V3 · OpenBao (demo 1).** `openbao-smoke.sh` en el ensayo:

- migrar dos veces (la segunda no hace nada);
- `--verify`;
- sin `kek.bin`;
- reinicio de servidor → `crypto: sealed`, 503 `crypto_unavailable`, `web` y `worker` `healthy`;
- desellar con 3 → recuperación en 25 s o menos;
- `/health` en cada estado.

Además: sellar con el api arriba (lecturas siguen, L-1); restauración de base y snapshot en `apex-smoke` (`openbao_restore_e2e.sh`); `migrate-provider` interrumpido y reanudado (prueba en `db_test`, citada).

**V4 · Avisos y cuentas (demos 2 y 3).** Repetir B8.7 y B9.6 sobre `apex_avisos_demo`: `notify` ×2 sin duplicados; Mailpit con un solo correo (opt-in); `telegram-fake` con el resumen sin nombres; `forgot` y activación con el texto fijo. En el ensayo, `notify` ×2 y `--status notify`.

**V5 · E2E**

- Ensayo, que es el stack de producción con OpenBao (DoD): `npx playwright test --project=stack --workers=1` con `avisos.spec.ts`, `payments-receipt-export.spec.ts`, `members-export.spec.ts`, `users-activation.spec.ts`, `home.spec.ts` y los cinco críticos de 4B. Dos corridas seguidas sin fallos ni flaky; si aparece un 429, se espera un minuto.
- Desarrollo: `--project=preview` completo con capturas en 320, 768, 1024 y 1440, claro y oscuro.
- Topes ×100 con `compose.e2e.yml` como en 4B y restauración con `cmp`.

**V6 · Recibo y CSV (demo 4).** Repetir B12.8 y B11.6. SQL de lectura del ensayo: filas `download` y `export` (inicio y cierre); `crypto_ops` con `purpose=export` por lote; cuadre con `summary`.

**V7 · Rendimiento.** `pytest -m perf -q -s` dos corridas: exportación de 1.000 socios en menos de 10 s; generación de 5.000 socios; `/health` bajo carga; `forgot` con y sin cuenta. `EXPLAIN (ANALYZE, BUFFERS)` de `today_list`, `notification_candidates` y la exportación (en el ensayo); línea base de D5.

**V8 · `database-reviewer` final.** `grants.sql` (cuatro tablas nuevas, columnas de D202 a D204, `apex_owner`), índices de `notifications` y las cinco migraciones.

**V9 · Gates completos.**

- `run-gates.sh`, cuarta corrida, con la suite del api en tres partes con `--cov-append` si la memoria lo exige. Cobertura del 80 % o más, también en `notifications/`, `openbao_provider.py`, `notify.py` y `cli_ops/{migrate_provider,rotate_kek,retire_local_kek,notify}.py`.
- `pre-commit --all-files`; licencias de api y web; `NOTICE`; `pip-audit`; `npm audit`; gitleaks del historial; `check-image-secrets` ×3; `test_api_image`.
- Conteo de saltadas: `age`, `pty` y `openbao` real corren en el contenedor Linux con 0 saltos.

**V10 · Revisiones.** `security-reviewer` sobre el árbol fusionado con los seis puntos de la DoD:

- token de OpenBao fuera de los logs y de `crypto_ops` (grep de los logs del ensayo);
- `last_error` solo con códigos;
- Telegram sin datos personales;
- `wa-link` con `no-store`;
- CSV con escape de fórmulas;
- correo solo con opt-in y consentimiento.

Además: grants por columna, `/health` y H-1/H-2 cerrados. `code-reviewer`, `python-reviewer` y `typescript-reviewer` sobre `git diff main...HEAD`; tamaños de archivo y de función. Todo hallazgo se corrige (se vuelve al slice y se resella) o se acepta con dueño.

**V11 · `verify-delivery`.** Matriz `docs/scratch/sprint-05-verify-delivery.md` con los dos pilares:

- historias US-120 a US-139, DoD y demos 1 a 5, cada una con su evidencia;
- sistema real: imágenes vigentes de cada componente, una escritura real por camino, base cruzada, `notify` ×2, idempotencia.

Pasos humanos declarados: custodia 2/2/1 y ensayo de `rekey` por una segunda persona.

**V12 · Limpieza y release.**

- Borrar `docs/scratch/*.dump`, `docs/scratch/ensayo/` (incluidas las llaves de OpenBao del ensayo) y `apex_avisos_demo` si quedara.
- `docker compose -p apex-ensayo down -v` y el smoke, comprobados con `docker compose ls`; nunca `apex`.
- `$DC --profile openbao --profile avisos stop`.
- Reconstruir las imágenes con el SHA de cierre.
- `CHANGELOG.md` (v0.2.0) y `git tag -a v0.2.0` local.
- `bash scripts/ci/check-release-version.sh --check v0.2.0`.
- Estado al cierre y dueños en DECISIONES.
- Pasos humanos: push, PR con la CI en verde (`api` con 0 saltos de `openbao`, `prod-smoke` con `openbao-smoke`), merge, firma de la etiqueta si el titular la hace (D83).

## 8. Riesgos y mitigación

1. **[HIGH] Pérdida de la custodia: llaves de desellado, `openbao-data` o una KEK local retirada antes de tiempo.** H-1 y H-2 son pasos; base y snapshot van en pareja, verificados; `--first-install`; restauración de punta a punta en el smoke; custodia 2/2/1; `apex-db-1` nunca migra (D68).
2. **[HIGH] Una migración de proveedor deja una clase ilegible.** Verificación antes del `UPDATE`, una transacción por llave, `0015` admite solo el par, prueba de interrupción, volcado y KEK respaldada.
3. **[HIGH] El worker que descifra amplía la superficie.** Clases limitadas, `SELECT` por columna, token solo `decrypt`, único llamador de `contact_for_notification`, `reveal` por campo.
4. **[MEDIUM] Arranque sellado que no levanta `web` ni `worker`.** Healthcheck tolerante, `deploy.sh` y prueba en el smoke.
5. **[MEDIUM] Secretos de SMTP y Telegram.** Entorno por servicio, redacción, tarea que atrapa todo, prueba de logs.
6. **[MEDIUM] Canal de tiempos en `forgot`.** `BackgroundTasks`, piso de tiempo, prueba de medianas.
7. **[MEDIUM] Exportación masiva.** Cubetas de D81, un flujo por usuario, tope de filas, auditoría de inicio y cierre.
8. **[MEDIUM] PDF propio.** M-11 y una revisión de seguridad dedicada.
9. **[MEDIUM] Memoria.** OpenBao y Mailpit bajo perfil; el ensayo se detiene durante los gates; comandos serializados entre los árboles.
10. **[MEDIUM] `grants.sql` falla cerrado.** `test_db_grants` en cada slice con tabla nueva; `dbsetup` del ensayo en cada slice.
11. **[MEDIUM] `apex_owner` y el script de inicio de la base.** Solo pilas nuevas; servidores existentes con `MIGRATE_DB_USER`; smoke en Linux.
12. **[LOW] El worker de desarrollo corre `notify` sobre `apex-db-1` a las 07:00.** Sin SMTP en el `.env` de desarrollo, solo genera filas de WhatsApp; la vuelta de V2 las borra; se anota.
13. **[LOW] Entrega "al menos una vez" del correo.** Tope de 3 intentos; documentado.

## 9. Rollback por migración

Regla de RUNBOOK §6: `downgrade` primero, después `git revert`, después `restart api worker`. Volcados `sprint-05-antes-00NN.dump`.

- **`0019`:** `downgrade 0018` borra `notifications.notifications` (se pierden los avisos).
- **`0018` y `0017`:** borran reglas y plantillas, y `0017` el esquema. Antes, `stop worker`.
- **`0016`:** borra las preferencias.
- **`0015`:** restaura la guarda de `0003`, sin filas. Con filas ya `openbao` no hay que revertirla: la reversa de datos es `migrate-provider --from openbao --to local` mientras la KEK local exista.
- **Grants y `apex_owner`:** `revoke.sql` por base. `apex_owner` solo existe en pilas nuevas, que se recrean.
- **Compose y OpenBao:** `git revert` y `up -d`.
- **Tras `retire-local-kek` no hay vuelta sin OpenBao:** la restauración es base más snapshot más llaves de desellado (`openbao.md`).

## 10. Trazabilidad

### C1 a C10 → paso

- **C1:** pasos 1-6, 19, 32, 40, 48, 57, 65, 73, 82, 90, 98, 105, 117, 125 y V1.
- **C2:** pasos 15-22 (`0015`), 28-35 y 44-51; `export-kek` y snapshot previos en 50; precondición en 45-46.
- **C3:** pasos 7-14 (healthcheck, `deploy.sh`, Compose) y 52-60.
- **C4:** pasos 18 (`crypto_keys` del worker), 52-56 y 94-101; D86.
- **C5:** pasos 61-68, 69-76, 77-85, 86-93 y 102-107. La parte `aiosmtplib` se sustituye por D64.
- **C6:** pasos 79-81 (siembra), 86-88 (generación) y 94-101 (job).
- **C7:** pasos 113-119 y 120-128. La parte `reportlab` se sustituye por D65; las licencias en 5.
- **C8:** pasos 5 (`NOTICE`), 7-14, 16-18 (`Settings`), 23-27 (`apex_owner`) y 36-43 (respaldo).
- **C9:** pasos 129-157.
- **C10:** V1 a V12 y `run-gates.sh` en 58, 99, 126 y V9.

### Revisión de seguridad → paso

- **HIGH:**
  - H-1: pasos 7-8 (`--first-install`), 36-43, 45-46 y V3.
  - H-2: pasos 9-10 (overlay, `deploy.sh`), 30 (arranque sin `kek.bin`), 46-47, 50 y V3.
- **MEDIUM:**
  - M-1: 7-8. M-2: 7-8 y 11. M-3: 7-9 y 54.
  - M-4: 54 y 56. M-5: 30 y 34 (a); 45-46 (b).
  - M-6: 54-56 (clases), 87-88 (ORM) y 95-96 (`claim_run`).
  - M-7: 16-18 (f), 63-64 (a, b, c) y 103-104 (d, e).
  - M-8: 16-18 y 62-64. M-9: 3, 87-88 y 130-131.
  - M-10: 121-124 y 153. M-11: 114-116. M-12: 23-27.
- **LOW:** L-1 en 11, 59 y V3; L-2 en 37 y 39; L-3 en 7 y 9; L-4 aceptado (v0.3, titular; D83); L-5 en 98; L-6 en 121 y 125; L-7 en 54; L-8 en 153; L-9 en 16 y 18.

### Enmiendas de la crítica 1 y su paso

- E1 → B13 (e2e sin `migrate-provider`) y B2.7 (variante con `migrate-provider --verify`; V3). S5-D95.
- E2 → W0-2.4 (`deploy.sh`) y W0-4 (`test_db_roles.sh`, modo existente). S5-D96.
- E3 → B2.4, B6.5 y B8.1/B8.3. S5-D97.
- E4 → W0-3. S5-D98.
- E5 → B5.2. S5-D99.
- E6 → B13.7. S5-D100.
- E7 → W0-4.4. S5-D101.
- Observaciones: F5.2 (paso 148), B3 (`keys:ro`), B7 (prueba de `notify --generate-only`) y W0-2.6 (nota de `wave0-gate.sh`).

### Preguntas de la exploración (P1 a P18) y del blueprint (Q1 a Q10, E1 a E16)

- **P1** → D3. **P2** → D18. **P3** → D14 y D69. **P4** → D15. **P5** → D20 y D52. **P6** → D44 y D57.
- **P7** → D29 y D78. **P8** → D86. **P9** → D8, D68 y B13. **P10** → D49 y paso 46. **P11** → D37. **P12** → D26 y paso 88.
- **P13** → D31 y D32. **P14** → D71. **P15** → D41 y D82. **P16** → D87 y `Tabs` existente. **P17** → D66, W0-3 y W0-4. **P18** → D64, D65 y paso 5.
- **Q1 a Q10:** respuestas del orquestador en la cabecera; Q6 → D80.
- **E1 a E16:**
  - E1 y E2 en 28; E3 en 53; E4 → D86; E5 en 52 y 56; E6 en 16 y 54; E7 en 86; E8 y E9 en 120;
  - E10 en 63; E11 en 1 y 34; E12 en 1; E13 → D64 y D65; E14 en 102; E15 en 153; E16 en la sección 0.

### Historias y demo

- US-133 → W0-2. US-134 → B1. US-135 → B13 y B2. US-136 → B3 y F5 (demo 1, V3).
- US-120 y US-121 → B6 y F2. US-122 → B4 y F2. US-123 → B5 y F3.
- US-124 → B7 y B8. US-125 → B8. US-126 → B4 y B8 (demo 2, V4).
- US-127 y US-128 → B7 y F1 (demo 2, V5). US-129 → B7 y F2. US-130 → B7 y F3.
- US-131 → B9 y F5 (demo 3). US-132 → B10 y F3 (demo 5).
- US-137 → B11 y F4. US-138 y US-139 → B12 y F4 (demo 4, V6).

### Deuda heredada del 4B con dueño v0.2

- D202, D203, D204 → W0-3. D206 → W0-4. D137, D148, D151 → B2. D57, D80, D149 → B13. `notifications` y la Ley 1581 → B5 a B8.
- D45 y D66 (Caddy), D61, `display_name` y D5 → v0.3 o condición (D83). D181 y D208 → paso humano en V12 (D83).

### Lo que pasa a v0.3 o después (con dueño)

- `sign-audit` y las filas `sign` en Transit (EP-17).
- TLS en `custody` y Caddy (titular, EP-20).
- `audit.append()` (tras `sign-audit`).
- AppRole (operador).
- Retención de `rendered_body` (titular).
- `display_name` (titular).
- Logo en el recibo (titular).
- Aviso de servicio sin consentimiento (responsable del tratamiento).
- Push y portal (v1.0).
- Exportar el rango de auditoría (`DESIGN-GAP` existente).
- Índices de `audit_log` (D5, si V7 lo pide).

## 11. Riesgos y supuestos que `plan-critic` debe atacar

1. `bao operator unseal -` lee la llave por stdin (W0-1.1). Si no, la alternativa es `PUT /v1/sys/unseal` desde un contenedor de `custody`.
2. Raft con `read_only: true` y el usuario de la imagen en el volumen (W0-1.1). Salvaguarda: quitar `read_only` solo a `openbao`, con decisión.
3. `--first-install` con salida por stdout redirigida en el ensayo: las llaves pasan por el proceso del agente hasta un archivo ignorado. Aceptable solo para llaves efímeras; nunca en producción.
4. `core/crypto/minisign.py` propio (D72) amplía B13: vectores reales de `minisign` 0.12, `ED` con prehash. Plan-critic puede preferir dejar D57/D80/D149 en v0.3 y que H-1 se apoye solo en la existencia de la firma; el plan elige cerrarlo porque su dueño era v0.2.
5. `export-kek` con `age -p` en el ensayo vía el ayudante de pty de `prod-smoke.sh` (S4B-D192), del que dependen las precondiciones de B2.7. Si no funciona, `recent_kek_verify` no se satisface y `migrate-provider` no puede ejercerse en el ensayo.
6. `10-apex-owner.sh` en `docker-entrypoint-initdb.d` corre solo con el volumen vacío; `migrate` como `apex_owner` necesita que `0001` cree esquemas en una base suya; `dbsetup` sigue como superusuario.
7. El sink de Telegram con `send` síncrono que agenda un `asyncio.Task`: no hay bucle en contextos síncronos del CLI. Se espera que `register_from_settings` solo registre donde hay bucle, y que `--run-once` llame `flush`.
8. `smtplib` en `to_thread` frente a la cancelación del job por `timeout_s`: el hilo no se cancela. Se acota con `timeout` del socket de 10 s o menos por envío.
9. `single_flight` en memoria supone un solo proceso del api (RUNBOOK §1). Con `--workers` se rompería.
10. La prueba de tiempos de `forgot` (margen de 50 ms con medianas) puede ser inestable en Windows. Se marca `perf` si fluctúa y la versión determinista prueba que el camino medido no consulta la base.
11. Que `CRYPTO_RECOVERY_POLL_S=20` y la caché de 5 s cumplan 30 s con margen en Docker Desktop.
12. `!override` en `compose.dev.yml` y `compose.openbao.yml` con Compose 5.6.1 y en los runners de CI.
13. El ensayo con OpenBao suma un contenedor; Mailpit y `telegram-fake` corren solo en desarrollo bajo perfil.
14. El ciclo de `downgrade` en V2 sobre `apex-db-1` borra los avisos de desarrollo.
15. `POST wa-link` cambia `ROUTES.md` (contrato del diseño), con decisión en W0-1.
16. Las cinco migraciones aplicadas al `apex-db-1` de desarrollo con el worker detenido desde `0017`.
17. `test_contact_callers` se declara en B5 pero solo puede quedar en verde de verdad con B7. El plan lo resuelve aceptando el conjunto declarado sin llamador real hasta B7: plan-critic debe confirmar que la prueba no exige que exista un llamador.
18. Paralelismo del front (D84): comandos pesados serializados a mano por el orquestador, sin candado automático.

## 12. Conteo

- **Slices:** 22 más V.
  - Wave 0: 4 (W0-1, W0-2, W0-3, W0-4).
  - Backend: 13, en orden B1, B13, B2, B3, B4, B5, B6, B7, B8, B9, B10, B11, B12.
  - Front: 5 (F1, F2, F3, F5, F4).
- **Pasos:** 157 numerados (W0-1 6; W0-2 8; W0-3 8; W0-4 5; B1 8; B13 8; B2 8; B3 9; B4 8; B5 8; B6 9; B7 8; B8 8; B9 6; B10 5; B11 7; B12 9; F1 7; F2 6; F3 5; F5 5; F4 6), más V1 a V12: 169.
- **Checkpoints:** 22 de slice (17 del backend en la rama del sprint y 5 del front en el worktree), más los de evidencia y validación.
- **Migraciones:** 5 (`0015` a `0019`).
- **Endpoints:** 23 nuevos, todos con rol (`POST wa-link` en lugar de `GET`). `/health`, `forgot`, `users`, `dashboard` y `settings/{section}` cambian.
- **Comandos de CLI nuevos:** `migrate-provider`, `rotate-kek`, `retire-local-kek`, `notify`, `seed-notifications` (5). El worker suma `--run-once notify`.
- **Servicios de Compose nuevos:** `openbao` y `openbao-bootstrap` (producción), `mailpit` y `telegram-fake` (desarrollo). Archivo `compose.openbao.yml`; red `custody`; volúmenes `openbao-data`, `openbao-dev-data` y cuatro de token.
- **Dependencias:** ninguna de ejecución nueva; `pypdf` en desarrollo. Binario `curl` en `apex-backup`.
- **Pruebas nuevas, aproximadas:** unas 760 del api (crypto 180, notifications 220, members 70, core 120, worker 50, cli 60, payments 60) y unas 190 del front; arquitectura: 1 nueva (`test_notifications_details_clean`) y 22 ampliadas; Bash: `test_openbao_infra.sh`, `infra/backup/tests/test_snapshot.sh`, `infra/tests/openbao_restore_e2e.sh` y `scripts/ci/openbao-smoke.sh`.
- **Decisiones:**
  - S5-D1 a S5-D48 en forma final;
  - S5-D49 a S5-D63 de seguridad con su opción final;
  - S5-D64 a S5-D101 de este plan (38; S5-D95 a S5-D101 son las enmiendas E1 a E7 de la crítica 1);
  - 18 contradicciones resueltas.
- **`run-gates.sh`:** 4 corridas (B3, B8, B12, V9).
- **Proyectos Compose aparte:** `apex-ensayo` (W0-2 a V12) y `apex-smoke` (W0-2, W0-4, B13, B3, V2, efímero).

