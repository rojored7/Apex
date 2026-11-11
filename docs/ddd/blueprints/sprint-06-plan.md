# Plan de implementación · Sprint 6 · v0.3: auditoría firmada, administración de llaves, adjuntos y autorización de datos, TLS híbrido

> Fase 2 de `/flow-update`, **enmendado, ronda 3**: la crítica 2 (`docs/ddd/blueprints/sprint-06-critica-2.md`, RECHAZADO por B1 y B2) se aplica en sitio con las decisiones de su sección final: E10 (S6-D81: `migrate-provider` sigue excluyendo `sign`; cambio de proveedor de la firma solo por `rotate-key audit.signature --provider`; `crypto_keys.public_key` en `0021`; `verify_signatures` verifica con la clave pública sin proveedor, lo que cierra M-1 del todo y elimina el estado `unavailable` y el muestreo), E11 (S6-D82: `real-ip.conf` renderizado en `${DEPLOY_STATE_DIR}` y montado por `APEX_REAL_IP_CONF`; árbol limpio probado), E12 (D77 sin `staging`), E13 (D59 y paso 85: corte por trozos probado por ASGI sin Nginx; tmpfs de `web` acotado), M1 (`acme-challenge` sin 308 en `test_caddyfile.sh`; ACME real como paso humano) y M2 (servicios sin `cap_drop` enumerados por grep). Antes, ronda 2: la crítica 1 (`docs/ddd/blueprints/sprint-06-critica-1.md`, RECHAZADO por B1 y B2) se aplica en sitio: E1 (cuerpo crudo acotado con `?kind=`, sin `python-multipart`; S6-D59, D73 reescritas), E2 (contradicción 16 y D61 corregidas: `migrate-provider` con filas `sign` va en A2; `0024` no toca `sign`), E3 (api y worker parados de W0-2.3 a W0-2.6; layout plano en `deploy.sh`), E4 (Engine 26 / API 1.45 y Compose 2.26 mínimos, S6-D78), E5 (una sola fila `update` por rotación), E6 (`guard_jobs_insert` y residual en D61), E7 (topes reales de `TOPE_CLI_OPS` y un archivo por comando nuevo, S6-D80), E8 (healthcheck de Caddy por `/_caddy_health`), E9 (`test_adr_docs` a siete en docstring, lista y mensajes; servicios sin `cap_drop` enumerados), O1 (todas las firmas con proveedor `local`), O3 (`ALLOW_DOMAIN_PORT`), O4 (un solo worker del api, S6-D79), O5 (snippet de Nginx renderizado por `deploy.sh`) y O11 (`worker_crypto_classes()` en `runtime.py` y `notify.py`). Pendiente de la crítica 2 y del gate humano, que además aprueba de forma explícita la creación de ADR-006 y ADR-007 (S6-D55, S4B-D47). Solo plano: no cambia código.

- Rama: `feat/sprint-06-auditoria-firmada-llaves-adjuntos-tls`. HEAD de partida: `df38264` (= `47ec673`, cierre documental del Sprint 5 y `v0.2.0` local, más los tres documentos de planificación: exploración, blueprint y revisión de seguridad, y el análisis de impacto). `main` sigue en `a1ad4cb`: el Sprint 5 no está fusionado (S6-D55, paso humano). Última migración aplicada en `apex-db-1`: `0020_notifications_indexes`. Este sprint añade `0021` a `0024` (S6-D39).
- Veredicto de entrada: AMARILLO (`docs/ddd/impacto/sprint-06.md`, `--allow-amber`). Este plan absorbe C1 a C9 (sección 10) y los bloqueantes de su sección 7.
- Entradas leídas, en el orden en que mandan: `impacto/sprint-06.md` (nueve condiciones, 17 bugs y contradicciones, 15 preguntas), `sprint-06-seguridad-diseno.md` (H-1, H-2, M-1 a M-11, L-1 a L-6; S6-D34 a D38), `DECISIONES.md` bloque «Sprint 6» (S6-D39 a D55, cerradas por el orquestador), `sprint-06-blueprint.md` (S6-D1 a D33, slices W0-1..W0-5, A1..A3, B1..B3, C1..C5, R1, E1, F1..F5, V1..V12, E1..E14 y Q1..Q12), `sprint-06-exploracion.md` (24 hallazgos, 18 preguntas), `SPRINT-06.md` y US-140 a US-153 con sus `BREAKDOWN.md`, `CLAUDE.md`, `docs/scratch/sprint-05.md` (patrón que funcionó y lecciones del entorno), `scripts/workflow/{slice-gate,checkpoint-commit,run-gates,wave0-gate}.sh`, `infra/compose*.yml`, `infra/nginx/*`, `infra/db/grants.sql`, `core/ratelimit.py`, `.env.example`, `.github/workflows/ci.yml`, `api/tests/architecture/*`, `api/tests/conftest.py`, `web/src/config/features.ts` y, como plantilla, `sprint-05-plan.md`.
- Mandan este plan y su sección 1. Donde el plan y el blueprint choquen manda el plan; donde el blueprint y la revisión de seguridad choquen manda la revisión; donde cualquiera choque con S6-D39 a D55 mandan esas decisiones. La sección 1 se copia a `DECISIONES.md` («Sprint 6 · decisiones de implementación») en el checkpoint de S6-W0-1.
- Decisiones del orquestador incorporadas tal cual (S6-D39 a D55): migraciones `0021` a `0024` en secuencia; Ed25519 único en v0.3 sin sonda de ML-DSA; políticas de OpenBao por servicio (el api verifica y nunca firma; el worker firma); keyring del worker por job; rotación desde el api con la guarda `0024` y las tres condiciones de H-2; router de llaves en `core/crypto/router.py` con el puerto `set_audit_writer` cableado desde `main.py`; puerto `Reencryptor` en `core/crypto/reencryptor.py`; adjuntos por cuerpo crudo acotado a 5 MiB con `?kind=` (la línea «multipart con `python-multipart`» de S6-D45 la sustituye la enmienda E1 de la crítica 1, por decisión del orquestador: sin dependencia nueva), semáforo global, fila `download` después de descifrar y antes de transmitir, foto por streaming con ADR-007, coach solo foto, S3 probado y apagado, sin borrado en v0.3; `data_consent_at` única fuente de verdad; cinco cubetas nuevas; Caddy con perfil `tls` y `real_ip`; ADR-006 y ADR-007 nuevos; subruta JWT del volumen `keys` en W0; fusión del Sprint 5 como paso humano.
- Doctrina: TDD por slice, deuda cero (todo HIGH y MEDIUM es un paso; todo LOW se corrige o se acepta con dueño) y ejecución al 100 %. Modelos (S6-D50): Fable diseña y revisa (`plan-critic`, `security-reviewer`, `database-reviewer`, revisiones finales); Sonnet ejecuta (Rojo, Verde, front, DevOps, QA). Paradas de la doctrina más las propias del sprint:
  - cualquier escritura en `apex-db-1` fuera de P-MIG y del P-ROL único de V2;
  - `down -v` fuera de `apex-ensayo` y `apex-smoke`;
  - `migrate-provider`, `rotate-kek`, `retire-local-kek`, `retire-key` o `init-keys --migrate-layout` sobre el proyecto `apex` de desarrollo (salvo `--migrate-layout` en W0-2.6, único y con volcado previo del volumen);
  - cambiar el formato del blob `apx1` o el serializador canónico de la auditoría (ADR-004);
  - modificar ADR-002, ADR-004 o ADR-005 (S6-D49; solo se crean ADR-006 y ADR-007);
  - un certificado ACME real o un dominio público desde el flujo (paso humano, `tls.md`).

## 0. Convenciones comunes a todos los slices

**Alias y entorno.** Todo desde Bash:

- `DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"`: desarrollo, proyecto `apex`, seis contenedores (`api`, `worker`, `web`, `backup`, `db`, `db_test`); `openbao` bajo `--profile openbao`; `caddy` bajo `--profile tls` (W0-4).
- `DCE="docker compose -p apex-ensayo --env-file docs/scratch/ensayo/.env --env-file docs/scratch/ensayo/.env.ops -f infra/compose.yml"`: ensayo de producción, puerto 8280, subred `172.31.2.0/24`, `custody` `172.31.12.0/24` (S5-D77). **El ensayo del Sprint 5 se destruyó en V12 (`down -v`): nace de cero en W0-2.7 (S6-D56).** Los dos `--env-file` son obligatorios siempre (una variable de shell no llega al `env_file` del api, lección V2 de S5).
- `DCEB="$DCE -f infra/compose.openbao.yml"`: ensayo ya migrado a OpenBao, desde W0-2.7.
- `DCET="$DCEB -f infra/compose.tls.yml --profile tls"`: ensayo con Caddy, desde W0-4.7; `TLS_PORT=8443` en su `.env.ops`.
- `apex-smoke`: lo maneja `scripts/ci/prod-smoke.sh`, puerto 8380, subred `172.31.3.0/24`, `custody` `172.31.13.0/24`; efímero.
- Pruebas del api: `TEST_DATABASE_URL=postgresql+asyncpg://apex:apex-test@127.0.0.1:5443/apex_test` exportada en cada comando; `uv` vive en `~/.local/bin`; siempre `127.0.0.1`; `-p no:cacheprovider`. **Un solo `pytest` a la vez** en todo el equipo (`db_test` es compartida y `LIMPIEZA_DE_SESION` borra tablas enteras).
- Puertos de desarrollo: 8180 (web), 8181 (api), 5442 (db), 5443 (db_test), 8443 (caddy de desarrollo, W0-4). 8280, 8380, 8443 y 8200 deben estar libres (W0-1.1).
- Las variables de la shell no persisten entre llamadas. Bajo MSYS, `MSYS_NO_PATHCONV=1` delante de todo `exec` que pase `/dev/null` o rutas POSIX.

**Cuadernos.** `docs/scratch/sprint-06.md` (backend y orquestador) y `docs/scratch/sprint-06-front.md` (worktree). Cada slice deja cuatro bloques, como en S5: Rojo (línea base, conteo y motivo de cada fallo), Verde (conteo, desviaciones numeradas, cobertura por archivo), Revisiones (conteos C/H/M/L y la decisión que cierra cada hallazgo) y Evidencia (primer bloque del slice siguiente o commit `docs(sprint-06): evidencia de S6-<slice>`). Las pruebas saltadas (`age`, `pty`, `openbao` real, modos POSIX, `tls`) se cuentan por archivo, con el motivo y el sitio donde sí corrieron (contenedor Linux o CI). Nunca se marca verde lo saltado.

**Ciclo estándar de un slice** (los pasos de cada slice solo dicen lo propio):

1. Stubs con `NotImplementedError` y Rojo, por `backend-qa-executor` o `frontend-qa-automation` en Sonnet. Se confirma el rojo con conteo.
2. Verde, por `backend-implementor` o `frontend-ux-engineer` en Sonnet, corriendo gates no sellantes (`slice-gate.sh` de los módulos tocados, salvo el último).
3. `database-reviewer` (si hay migración o grants: A1, A3, C1, R1) y `security-reviewer` (todos los slices) en Fable, en paralelo. El Verde corrige todo hallazgo CRITICAL, HIGH o MEDIUM; los LOW se corrigen o se aceptan con dueño (decisión numerada).
4. P-API si cambió el contrato.
5. Documentación y bloque del cuaderno.
6. Gate sellante al final.
7. Docker y evidencia, sin tocar el árbol (si obliga a cambiar código, se vuelve a 2 y se resella).
8. Checkpoint: `CHECKPOINT_TRAILER='Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>' bash scripts/workflow/checkpoint-commit.sh "S6-<id> <resumen>"`, más `git commit -m "docs(sprint-06): evidencia de S6-<id>" -m 'Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>'`, verificado con `git log -1 --format=%B`.

Antes de cada línea de gate con lista se corre `ls` de cada archivo. `PYTEST_ADDOPTS="-m 'not perf'"` en todos los gates. `tests/architecture` corre en cada gate. Todo gate que toque `Settings` o `NON_API_ENV_VARS` incluye `tests/core/test_config.py` y `tests/core/test_env_example.py` (lección S5-D150).

### Agentes por slice

- Rojo y Verde: como en el ciclo estándar.
- `devops-wsl2-docker`: W0-2, W0-3, W0-4, la evidencia Docker de cada slice, los smokes en Linux (`prod-smoke`, `openbao-smoke`, `tls-smoke`, `restore_e2e`) y las reconstrucciones con `buildx`; es quien ejecuta los proyectos aparte.
- `database-reviewer`: A1 (`0021`, grants de `audit.signatures`), A3 (`0022`), C1 (`0023`, esquema `attachments`, grants), R1 (`0024`, grants del api sobre `crypto_jobs` y `crypto_keys`) y V9. Los demás slices solo llevan `security-reviewer`.
- `security-reviewer`: todos los slices (incluido W0-1 sobre T-DOC y decisiones), más V11 sobre el árbol fusionado.
- `plan-critic`: este plan, antes de W0-1 (Fase 2.5).
- Un slice no empieza hasta el checkpoint del anterior en la misma rama. El front sigue la sección 3.

### Mapeo de `slice-gate.sh` (verificado en HEAD, líneas 96 a 121)

- `core/<x>` exige `src/app/core/<x>.py` o `src/app/core/<x>/`, un nivel: valen `core/config`, `core/ratelimit`, `core/http`, `core/alerts`, `core/jobs`, `core/audit_verify`, `core/security` y, desde el stub de A1, `core/audit_sign`.
- `crypto` cubre `src/app/core/crypto/` entero (`router`, `inventory`, `schemas`, `reencryptor`, `cbom`, `rotate_job` nuevos incluidos) con `tests/crypto`.
- `main` → `main.py`. `worker` → `src/app/worker/`. `cli` → `cli.py`, `cli_base.py`, `cli_manifest.py`, `cli_ops/`, `seed/`, `imports/`.
- `<modulo>` → `src/app/modules/<modulo>`: `attachments` vale desde el stub de C1 (con `tests/attachments/`).
- `web/<feature>`, `web/shared`, `web/core`, `web/app`: `web/attachments` vale desde F3.
- Ningún cambio al script hace falta. `wave0-gate.sh` y `run-gates.sh` suman en W0-4 las combinaciones `-f infra/compose.yml -f infra/compose.openbao.yml -f infra/compose.tls.yml --profile tls` y `--profile tls -f infra/compose.yml -f infra/compose.dev.yml`, con su caso en `scripts/workflow/tests/test_wave0_gate.sh` y `test_run_gates.sh`. `tls-smoke.sh` y `openbao-smoke.sh` no entran en `run-gates.sh` (necesitan Docker); `test_infra_scripts.sh` los cubre con `bash -n` y aserciones estáticas.

### Memoria del equipo

- Suite completa del api: nunca junto a vitest o Playwright. Fuera de `run-gates.sh` se corre en tres partes con `--cov=app --cov-append`: `tests/{architecture,core,crypto,cli,worker,migrations,integration,settings}`; `tests/{audit,auth,dashboard,notifications,attachments}`; `tests/{members,memberships,payments,plans}` más `test_ci_database.py` y `test_smoke.py`; `coverage report --fail-under=80` al final.
- `run-gates.sh` se corre al cerrar A3, C5, E1 y V10, en primer plano, en solitario y con el ensayo detenido con `$DCEB stop api worker web backup` (nunca `down -v`; nunca `stop` sin lista de servicios, porque para también el stack base). Si muere la parte web, se repite solo esa parte con `npx vitest run --coverage --pool=forks --maxWorkers=2`.
- `docker stats --no-stream` al cuaderno en W0-1, W0-2.7, W0-4.7 y antes de cada `run-gates.sh`.
- Después de recrear el api (desarrollo o ensayo) siempre `restart web` (Nginx guarda la IP vieja: 502 hasta entonces). Todo `compose run` que recree el api exporta `GIT_SHA=<sha>` o usa `--no-deps`.
- `pre-commit run --all-files` desde `api/` con `-c ../.pre-commit-config.yaml` (hook de ruff alineado en S5, 0.17.1).

### P-MIG · Migración nueva (`0021` a `0024`)

1. Volcado: `$DC exec -T db pg_dump -U apex -Fc apex > docs/scratch/sprint-06-antes-00NN.dump` (`*.dump` ignorado, comprobado con `git check-ignore -v`). Se borra en V12.
2. `$DC stop api worker` mientras se redacta (el worker escribe `audit_log` por sus jobs y, desde A2, `audit.signatures`; siempre).
3. Escribir `api/migrations/versions/00NN_<tema>.py` y `api/tests/migrations/test_00NN_<tema>.py`. `migrations/env.py` importa los modelos nuevos (`core/audit_sign.py` en A1, `modules/attachments/models.py` en C1).
4. Contra `db_test`: `cd api && uv run pytest tests/core/test_migrations.py tests/migrations -q`, con el ciclo `head → base → head`.
5. `cd api && uv run alembic heads`: una sola cabeza.
6. `$DC start api worker`; esperar `healthy`; `$DC exec api alembic current` = `00NN (head)`. Es la única forma en que la migración llega a `apex-db-1`.
7. `$DC exec api alembic downgrade -1 && $DC exec api alembic upgrade head && $DC exec api alembic current`.
8. Esquema de solo lectura: `$DC exec -T db psql -U apex -d apex -c '\d <tabla>'` (más `\df+ crypto.guard_keys_update` en `0024`) y la consulta de `tgenabled` (los diez triggers de 4B en `A`, más `signatures_forbid_mutation` desde `0021` y `attachments_guard` desde `0023`). Al cuaderno.
9. La prueba de la migración anterior pasa de «es head» a «está en la cadena de head» (`test_0020_notifications_indexes.py` en A1, y así sucesivamente).

### P-ROL · Grants

- Cada slice que cambia `grants.sql` (A1, C1, R1) actualiza en el mismo paso las tres listas (matriz, `-- clasificada:` y `ARRAY clasificadas`, S4B-D201), las cuatro sentencias de esquemas si hay esquema nuevo (C1), `revoke.sql` y `tests/migrations/test_db_grants.py` (`PRIVILEGIOS`); prueba sobre `apex_roles` en `db_test` con el ciclo `apply → revoke → apply`; corre `dbsetup` en `apex-ensayo` (conteo de tablas clasificadas: 20 hoy, 21 tras `0021`, 22 tras `0023`) y `OPS_ENV_FILE=docs/scratch/ensayo/.env.ops DB_OWNER_MODE=nueva DC="$DCE" bash scripts/ci/test_db_roles.sh`.
- `apex-db-1` recibe `dbsetup` una sola vez, en V2: `$DC --profile prod-init run --rm --no-deps dbsetup`, con `--no-deps` obligatorio (S4B-D99). En desarrollo el api y el worker corren como propietario (S4B-D11).

### P-API · Contrato (A3, B1, B2, B3, C2, C3, C4, C5, R1)

`cd api && uv run python -m app.cli export-openapi ../docs/openapi.json`, después `cd web && npm run gen:api && npx vitest run src/core/api/types.contract.test.ts`. Se exporta dos veces y debe salir idéntico. Los dos archivos entran en el checkpoint del slice. Solo el backend toca `types.ts`; el worktree hace rebase antes de cada F.

### P-BAO · OpenBao: desellar, sellar, políticas (de S5, con lo aprendido)

- Desarrollo: `$DC --profile openbao up -d openbao` (`dev-entrypoint.sh`, volumen `openbao-dev-data`, reaplica políticas en cada arranque); sellar con `bash scripts/dev/openbao-seal.sh`; `$DC restart openbao` desella; apagar con `$DC --profile openbao stop openbao` (nunca `stop` a secas).
- Ensayo y smoke (5 de 5, umbral 3): `--first-install` por pty en el auxiliar `docker:cli` (S4B-D192), llaves a `docs/scratch/ensayo/openbao/init.txt` (600, carpeta ignorada; nunca al cuaderno); **desellar por API con `wget --post-file=/dev/stdin` a `/v1/sys/unseal` leyendo la llave con `read -rs`** (S5-D103: `bao operator unseal -` no lee stdin); sellar como en la demo con `$DCE restart openbao`; «reinicio de servidor» = `restart openbao` y luego `restart api worker` (S5-D69).
- Políticas nuevas (W0-3): en el ensayo `bootstrap.sh --reissue-tokens` reaplica las políticas y reemite los cuatro tokens (`docs/operacion/openbao.md` §6); después `restart api worker`. `bao` no existe en el host: todo pasa por `$DCE exec -T openbao bao ...` sin imprimir tokens.
- Snapshot: `$DCE -f infra/compose.verify.yml run --rm backup /opt/backup/run.sh` (S5-D100).

### P-ADJ · Archivos de prueba y evidencia de adjuntos (nuevo)

- Archivos generados por `tests/factories/files.py` (JPEG, PNG, PDF mínimos válidos; ELF y PE con cabecera real; tamaños exactos 5.242.880 y 5.242.881 rellenando después de la cabecera). Para la evidencia en Docker se generan en `docs/scratch/ensayo/adjuntos/` (ignorada) con el mismo módulo desde `tools`.
- Subida por cuerpo crudo (E1): `curl -sS -o /dev/null -w '%{http_code}' --data-binary @<ruta> -H 'Content-Type: image/jpeg' -H "Authorization: Bearer <token>" "http://127.0.0.1:8280/api/v1/members/<id>/attachments?kind=photo"`; variante `chunked`: la misma con `-H 'Transfer-Encoding: chunked'`; `Content-Length` falso: desde `tools` con `http.client` de la biblioteca estándar (`putheader("Content-Length", "10")` y un cuerpo de 5.242.881 bytes), nunca con `curl`. Descarga con `curl -sS -D - -o <salida>` y `cmp` contra el original.
- El contenido en reposo se inspecciona en el contenedor del api: `$DCE exec -T api sh -c 'ls -la /data/uploads/attachments && head -c 5 /data/uploads/attachments/<hex>'` (sensible empieza por `apx1.`; nunca se vuelca un archivo entero al cuaderno).
- Las pruebas del api escriben en un `tmp_path` por sesión (`UPLOADS_DIR`), nunca en `/data/uploads`.

### P-TLS · Cómo se prueba TLS sin dominio real (S6-D63)

- `scripts/ci/tls-smoke.sh [--dc "<alias>"] [--lan]` (junto a `openbao-smoke.sh`; el blueprint lo situaba en `scripts/workflow/`, se mueve por convención): levanta el stack con `-f infra/compose.tls.yml --profile tls`, `APEX_DOMAIN=apex.localhost:<puerto>` y `APEX_TLS_ISSUER=internal` (Caddy emite con su CA interna), extrae la raíz con `docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt <tmp>` y, desde un contenedor `alpine:3.22@sha256:…` (fijado por digest y fecha en W0-1.1; `apk add --no-cache openssl=<versión 3.5.x fijada>` en el propio script, como los pines de `apex-backup`), ejecuta en la red del proyecto:
  - `openssl s_client -connect caddy:443 -servername apex.localhost -groups X25519MLKEM768 -CAfile root.crt` y exige `Negotiated TLS1.3 group: X25519MLKEM768` y `Verify return code: 0`;
  - `-groups X25519` → `Negotiated TLS1.3 group: X25519` (caída);
  - `-tls1_1` → rechazo; `-tls1_2` → acepta;
  - `wget -S --max-redirect=0 http://caddy/login` → `308` con `Location: https://apex.localhost…/login`;
  - `Strict-Transport-Security: max-age=300` presente por HTTPS (valor inicial escalonado, M-8) y ausente en el stack sin perfil (`--lan`);
  - la cookie de `refresh` lleva `Secure` por HTTPS (desde E1) y no la lleva en `--lan`;
  - limitador por IP real (S6-D29): dos contenedores cliente con IP distinta en la red `default` hacen 6 logins fallidos cada uno contra `https://caddy`; el sexto de cada uno es `429` y el primero del segundo cliente sigue `401` (si contaran a Caddy, el segundo cliente recibiría `429` desde su primer intento);
  - `docker compose config` con y sin perfil (`web` sin `ports` con el overlay; `caddy` ausente sin perfil).
- Corre en el ensayo (`$DCET`), en `apex-smoke` (`prod-smoke.sh --tls`) y en el job `images` de la CI. ACME real, renovación con staging y SSL Labs son pasos humanos con dominio público (`docs/operacion/tls.md`).

### Docker y quirks (RUNBOOK §7)

- `docker compose build` y `up --build` están rotos en este equipo: `docker buildx build --load --network host --allow network.host --build-arg GIT_SHA=<sha> -t apex-api:local -f api/Dockerfile api`; `... -t apex-web:local -f web/Dockerfile .`; `... -t apex-backup:local -f infra/backup/Dockerfile infra/backup`; se levanta con `up -d --no-build` (y `--force-recreate` de lo que cambie, más `restart web`).
- `caddy` y `alpine:3.22` se descargan con `docker pull <imagen>@sha256:…` (W0-1.1 fija los digests). `prod-smoke.sh` repunta `apex-*:local`: tras cada smoke se comprueba `docker image inspect` y se re-etiquetan los ids del cuaderno (lección V3 de S5).
- **S4B-D98:** todo cambio en `api/src`, `api/migrations` o `uv.lock` exige reconstruir `apex-api:local` antes de `migrate`, `dbsetup`, el ensayo o el smoke; `web` cambia en F y por `default.conf` (W0-2, W0-4).
- api de desarrollo: bind con `--reload`; una migración exige P-MIG; `restart api` después de migrar. No editar `src/` durante un E2E del proyecto `stack`.
- worker: bind sin reload. `$DC stop worker` mientras se edita `app/worker/`, `core/jobs.py`, `core/audit_sign.py`, `core/crypto/` o `modules/attachments/`; `$DC restart worker` en el checkpoint.
- `apex-db-1`: solo `SELECT`, `\d` y sentencias que deben fallar dentro de `BEGIN; ... ROLLBACK;`.
- Smokes en Linux (`prod-smoke`, `openbao-smoke`, `tls-smoke`, `restore_e2e`, `openbao_restore_e2e`): contenedor auxiliar `docker:cli` con el socket montado, el árbol en el volumen `apex-b4-work` (`git archive HEAD`), `--network host` y `TMPDIR` dentro del volumen; se lanza con `docker run -d` y se vigila con Monitor (el recolector de memoria mata los Bash en segundo plano). Nunca se reinicia Docker Desktop.
- Los agentes Sonnet pierden las barras invertidas en los heredocs y PowerShell escribe BOM o ANSI: toda regex, todo `.hcl`, todo `.sh`, el `Caddyfile` y todo archivo con tildes se escriben con Write (UTF-8 sin BOM) y el orquestador los revisa con Grep después de cada edición de un agente (lista en el cuaderno).
- El hook `config-protection` puede bloquear `pyproject.toml`: las dependencias se cambian con `uv add`; marcadores de pytest con una edición mínima anotada.
- gitleaks, `pip-audit` y `npm audit` como en 4B (V10). Ningún literal de llave de desellado, token `hvs.`/`s.`, `AGE-SECRET-KEY-1` ni certificado privado en pruebas ni documentos (la CA interna de Caddy se usa solo desde el volumen y se borra en V12).

## 1. Bloque «Sprint 6 · decisiones de implementación» para `docs/ddd/DECISIONES.md`

Formato del bloque del Sprint 5: `Fuente:`; contradicciones resueltas; S6-D1 a S6-D33 en forma final; S6-D34 a S6-D38 con la opción final; S6-D39 a S6-D55 tal cual (ya cerradas); S6-D56 en adelante de este plan; contradicciones de contrato cerradas en T-DOC; y un bloque por slice que añade cada checkpoint.

### Contradicciones resueltas

1. **D5 (sonda de ML-DSA en `bootstrap.sh`, `cli_ops/rotate_sign.py`, `--algorithm ML-DSA-65`) frente a S6-D51 y al sondeo del impacto.** Mandan D51 y el dato: no hay sonda, no nace `rotate_sign.py`, la llave es Ed25519 en v0.3; `SIGNATURE_ALGS` conserva `ML-DSA-65` para EP-26; `payload_version` y `alg` por fila dejan la rotación futura sin migración.
2. **D8 (`WORKER_CRYPTO_CLASSES` gana `audit.signature`) frente a S6-D42.** Manda D42: las clases son por job (`JobSpec.crypto_classes`); `notify` sigue con `member.phone` y `member.email`; `sign_audit` abre solo `audit.signature`; el arranque sondea la unión (S6-D60).
3. **D3 y D8 (`sign_latest` firma el hash de la última fila) frente a H-1 (S6-D34).** Manda la seguridad: ancla y recorrido incremental desde `last_signed_seq` antes de firmar; si no cuadra, no firma, `JobResult(ok=False)` y `alert("audit_chain_broken", through_seq=)`.
4. **D10 (`verify_signatures` llama a Transit por cada firma; `unavailable` opcional) frente a M-1 (S6-D36), S6-D40 y la crítica 2 (E10).** Manda E10 (S6-D81): la verificación nunca llama al proveedor; cada firma se verifica en el api con la clave pública guardada en `crypto_keys.public_key` de su `key_id` (Ed25519 en proceso), así que funciona con OpenBao sellado, no existe el estado `unavailable` ni el muestreo, y las firmas de llaves retiradas siguen verificando; el anti-retroceso sigue evaluándose sin Transit (S6-D62 reescrita). Firmar es lo único que exige Transit.
5. **D15 (grants y `0024` con una sola transición) frente a H-2 (S6-D35) y S6-D43.** Mandan: las tres condiciones de la guarda, columnas acotadas de `crypto_jobs`, un solo rotador en vuelo con conexión dedicada fuera del pool y tope de duración (S6-D61). `retired` sigue siendo solo de `retire-key`.
6. **D17 y D32 (cubetas `crypto-rotate`, `attachments-write`, `attachments-download`; CBOM por `export`) frente a S6-D47.** Manda D47: `attachments-upload`, `attachments-photo`, `attachments-download`, `keys-rotate`, `cbom-export` (S6-D57).
7. **D24 (fila `download` antes de enviar; coach descarga sensibles) frente a M-3 y M-6 (S6-D45).** Manda D45: descifrar, luego fila, luego transmitir; semáforo global de 4 (S6-D59); `consent` y `other` solo admin en v0.3; el coach sube y ve fotos.
8. **D19 (el archivo de autorización no toca `data_consent_at`) frente a S6-D46.** Manda D46: subir `kind = consent` fija `data_consent_at` si estaba nulo y copia `current_privacy_version`; `POST /members` no cambia de contrato; `consent_required_from` nulo no exige.
9. **D22 y S6-D45 (multipart con `python-multipart`, «lee como máximo 5.242.881 bytes del `UploadFile`») frente a M-4 y a la crítica 1 (B1: en Starlette 1.9.0 `max_part_size` solo acota los campos de texto, el archivo va a un `SpooledTemporaryFile` sin tope y `request.form()` parsea todo antes de devolver el control; `kind` dentro del multipart no existe hasta parsear).** Manda la crítica (E1, decisión del orquestador): cuerpo crudo con `?kind=` validado antes de leer un solo byte, `request.stream()` acotado a 5 MiB exactos, 413 JSON al superarlo, sin `python-multipart` (S6-D59, D73).
10. **D27 (HSTS `max-age=31536000; includeSubDomains`; Caddy 2.10.x) frente a M-8 (S6-D48) y al host.** Manda M-8: `max-age` escalonado desde 300 s sin `includeSubDomains` (`APEX_HSTS_MAX_AGE`), 2.11.3 por digest (S6-D64). US-153 criterio 2 se enmienda en T-DOC.
11. **D28 (`LAN_ORIGIN`, `cookie_secure` derivado) frente al impacto (condición C1 g) y S6-D48.** Mandan: `FRONT_BASE_URL` es el origen LAN (N-11); `COOKIE_SECURE` y `ALLOW_INSECURE_COOKIE` siguen explícitos; `validate_origins` solo suma coherencia con `APEX_DOMAIN` (S6-D65).
12. **D29 (`map` por cabecera, `real_ip_recursive on`) frente a M-7 (S6-D48).** Manda M-7: `map` sobre `$realip_remote_addr`, `set_real_ip_from <ip de Caddy>/32`, `real_ip_recursive off`, Caddy con `admin off` y sin `trusted_proxies`, `cap_drop ALL` en todos los miembros de `default` y `custody` (S6-D64).
13. **D12 (el router audita con `core.audit`) frente a `test_core_import_direction` y S6-D52.** Manda D52: puerto `set_audit_writer` cableado desde `main.py`; sin puerta, las rutas auditadas fallan cerrado con 503 `busy`.
14. **D24 (`SensitiveFieldRevealed`) frente a S6-D53.** Sin evento: la fila `download` es la única señal; tercera puerta de descifrado en `modules/attachments/files.py` (S6-D60).
15. **D1 (orden W0-1, W0-5, W0-3, W0-2, W0-4) frente a este plan.** Orden W0-1, W0-5, W0-2, W0-3, W0-4 (S6-D56): el ensayo nace en W0-2 junto con la subruta del volumen `keys` (S6-D54, D58) y las políticas de W0-3 se aplican sobre él.
16. **S6-D40 (`migrate-provider` incluye filas `sign`) frente a S5-D183 y a la crítica 2 (B1).** S5-D183 queda intacta (S6-D81): una fila `sign` guarda una referencia a una llave cuyo material no viaja (`sign-ed25519.key` local; llave Transit no exportable), así que «cambiar de proveedor» cambiaría la llave y las firmas guardadas dejarían de verificar. `core/crypto/migration.py` (docstring línea 6, tupla de propósitos de la línea 52) sigue excluyendo `sign`, y lo dice: forzar `--data-class audit.signature` sale 2 `signatures_reference_key`. El cambio de proveedor de la firma es una llave **nueva**: `rotate-key audit.signature --provider <nuevo>` (A2) inserta la fila `version + 1` `active` con la referencia del proveedor nuevo y su clave pública, deja la anterior `decrypt_only` y no recifra nada; las firmas antiguas verifican por `key_id` con `crypto_keys.public_key` (D81). La guarda de `0015` (que ya admite `sign`) no cambia y `0024` no la toca. En el ensayo la fila `sign` nace ya `openbao` (W0-2.7 migra antes de A1).
17. **D13 (`summary.provider` desde `crypto.state`) frente a S6-D54.** «Proveedor activo» se lee de `crypto_keys` (proveedores distintos de las filas `active`, S5-D3) y el estado de `recovery.current_state()` (el mismo de `/health`, no la configuración).
18. **D30 (`scripts/workflow/tls-smoke.sh`) frente a la convención de `openbao-smoke.sh`.** `scripts/ci/tls-smoke.sh` (S6-D63).
19. **US-145 criterio 7 (`retired` al terminar) frente a S4B-D63, D140 y S6-D43.** `decrypt_only`; `retired` solo por `retire-key`. T-DOC.
20. **US-149 criterio 1 (`data_consent_at` del cliente obligatorio «desde v0.3») frente a S6-D46.** El contrato de `POST /members` no cambia (`data_consent: bool`); la obligación nace de `consent_required_from`; T-DOC.
21. **US-152 criterios 5 (renovación contra staging sin intervención) y 8 (SSL Labs) frente a un flujo sin dominio.** Pasos humanos con dominio público, documentados en `tls.md`; la evidencia del flujo es `tls-smoke.sh` con CA interna. T-DOC.
22. **`SPRINT-06.md` (`0040` a `0051`, `0042`, `0045`, `0046`, `0051`) frente a S6-D39.** `0021` a `0024`; las demás sobran. T-DOC.
23. **D21 (S3 con `boto3` como segundo adaptador) frente a M-9 y S6-D45.** Probado con `botocore.stub.Stubber` y apagado: `STORAGE_PROVIDER=s3` en producción exige `S3_ENABLE_PRODUCTION=true`, credenciales explícitas, `https` salvo `ENV=dev`, `verify=True`, `proxies={}` y reintentos acotados; `boto3` en el grupo opcional `s3`.
24. **S5-D201 (subruta `custody/` y `jwt/` «en EP-17») frente al blueprint (sin slice).** Entra en W0-2 (S6-D54, D58).
25. **Exploración 11 (`AUDITABLE_TABLES`) y blueprint hallazgo 19.** Entran `attachments.attachments` (C1) y `crypto.crypto_keys` (R1, la rotación se audita explícita); no `audit.signatures`. Como `crypto_keys` no es `__audited__`, entrar en `AUDITABLE_TABLES` no duplica filas: lo fija la aserción de una sola fila `update` por rotación (E5, paso 110).
26. **S6-D21/D31 (`python-multipart` como dependencia de ejecución) frente a E1.** Con cuerpo crudo no hace falta: no entra ninguna dependencia de ejecución nueva; `boto3`/`botocore` siguen en el grupo opcional `s3`.
27. **D64 (healthcheck de Caddy con `wget --max-redirect=0` aceptando 308) frente a la crítica 1 (M4).** Ruta propia `/_caddy_health` con `respond 200` en el sitio HTTP, antes de la redirección (E8).
28. **D64 (`envsubst` del entrypoint de Nginx) frente a O5, a la imagen `web` (hornea `default.conf` y `snippets/` en el build) y a `deploy.sh:101,218` (árbol limpio obligatorio; crítica 2, B2).** El snippet `real-ip.conf` se renderiza **fuera del árbol** (`${DEPLOY_STATE_DIR}/real-ip.conf`; en los smokes, un directorio temporal) y Compose lo monta por `APEX_REAL_IP_CONF` con el `.conf` versionado como valor por defecto (S6-D82); el árbol nunca se ensucia y `test_deploy_script.sh` lo prueba con `git status --porcelain` vacío.

### Decisiones del blueprint (S6-D1 a S6-D33) en forma final

Se copian como están en `sprint-06-blueprint.md` §1, con estas enmiendas:

- **D1:** orden de W0 según D56; worktree del front tras C5 (D70).
- **D2:** sin cambio; `0024` no toca las filas `sign` (contradicción 16 corregida; E2).
- **D3, D4:** sin cambio; `audit_sign.py` suma `check_unsigned_segment` (H-1, D34).
- **D5:** reemplazada por D51 (Ed25519 único; sin sonda; sin `rotate_sign.py`); `rotate-key audit.signature` solo admite `--provider <nuevo>` (llave nueva, D81); sin `--provider` o con el mismo proveedor sale 2 `purpose_not_rotatable` (D69).
- **D6:** sin cambio; D41 lo confirma; la política del token de la CI también cubre `sign` y `verify`.
- **D7:** sin cambio en `audit.signatures` (`payload_version smallint`, trigger `ENABLE ALWAYS`); `0021` añade además `crypto_keys.public_key text` nula, con CHECK `(purpose <> 'sign') OR (public_key IS NOT NULL)` (D81; hoy no hay filas `sign`, así que el CHECK entra sin llenado).
- **D8:** `crypto_classes` por job (D42, D60); claves de `details` según D60; la alerta `audit_chain_broken` (D34) se suma.
- **D9:** sin cambio.
- **D10:** D62 reescrita (todas las firmas con la clave pública en proceso; sin Transit; sin `unavailable` ni muestreo; anti-retroceso sin Transit; D81).
- **D11:** sin cambio; `init-keys --data-class` crea la fila `sign` y `ensure_keys` del api no la crea (D40).
- **D12:** más las condiciones de la revisión: el router no importa `core.audit_verify` ni `core.audit_sign`; `inventory` con columnas explícitas (D44, D52).
- **D13:** `summary.provider` según D54; `q` sobre `data_class` en las tres listas (D57).
- **D14:** sin cambio; `finish_rotation` recuenta con `count_pending` bajo `FOR SHARE` y falla si es mayor que 0.
- **D15:** D43, D61.
- **D16, D17:** cubetas de D57; CBOM sin referencias de `sign` (L-5).
- **D18:** sin cambio; privados de `attachments`: `files`, `rules`, `queries`, `reencrypt`, `storage/` (D60); `router.py` nace con el `APIRouter` vacío en C1 y gana su única ruta en C4.
- **D19:** D46 (el archivo fija `data_consent_at` si estaba nulo).
- **D20:** sin cambio.
- **D21:** D45 (S3 apagado con bandera).
- **D22:** reemplazada por D59 (cuerpo crudo con `?kind=`, `request.stream()` acotado, 413 al superar 5 MiB, sin `python-multipart`; E1).
- **D23:** sin cambio.
- **D24:** D45 (orden descifrar → fila → transmitir; coach solo foto; cubeta `attachments-photo`); sin `SensitiveFieldRevealed` (D53).
- **D25:** sin cambio; `__audit_exclude__` para `filename_random` y `key_id` (L-1, D75).
- **D26:** lote de 50 adjuntos (riesgo 8 del impacto).
- **D27:** D64 (2.11.3; HSTS escalonado; `admin off`; variables `APEX_TLS_ISSUER`, `APEX_HSTS_MAX_AGE`, `APEX_ACME_CA`).
- **D28:** D65 (sin `LAN_ORIGIN`; `COOKIE_SECURE` explícito).
- **D29:** D64 (`$realip_remote_addr`, `/32`, `recursive off`).
- **D30:** D63.
- **D31:** sin `python-multipart` (E1); `boto3` y `botocore` en el grupo opcional `s3`; `alpine:3.22` (MIT, solo smoke) al bloque fijo de `NOTICE`.
- **D32:** D57.
- **D33:** sin cambio; `docs/operacion/llaves.md`, `adjuntos.md`, `tls.md` nuevos; RUNBOOK §14.

### Decisiones de seguridad (S6-D34 a S6-D38) con la opción final

Todas aceptadas tal como las propone `sprint-06-seguridad-diseno.md`:

- **D34 (H-1):** `check_unsigned_segment` recalcula `prev_hash`/`hash` con el serializador canónico (lectura; `core/audit.py` no cambia) desde el ancla; A1 y A2.
- **D35 (H-2):** las tres condiciones; la segunda se precisa en D61 (lo que la guarda puede y no puede recontar).
- **D36 (M-1):** cerrada por completo con D81: la verificación no depende del custodio (clave pública en `crypto_keys`), así que no hay resultado parcial que mostrar; el anti-retroceso sin Transit se conserva; D62.
- **D37 (M-5):** foto sin fila por vista, cubeta `attachments-photo` 600/min, ADR-007, `no-store`, `blob:` en memoria; C4 y F3.
- **D38 (M-10):** sin borrado en v0.3; ADR-007 declara el residual con dueño (titular) y fecha (v0.4); RUNBOOK documenta el procedimiento manual de supresión a petición (D76).
- M-2 a M-4, M-6 a M-9, M-11 y L-1 a L-6 entran como criterios de aceptación de sus slices (sección 10).

### Decisiones de este plan (S6-D56 en adelante)

- **S6-D56 · Orden y ensayo.** W0-1, W0-5, W0-2, W0-3, W0-4, A1, A2, A3, B1, B2, B3, C1, C2, C3, C4, C5, R1, E1; front F1, F3, F4, F5, F2 en el worktree (D70); V1 a V12. `apex-ensayo` nace de cero en W0-2.7 (igual que S5 V2.5: `init-keys` con el layout nuevo, `migrate` como `apex_owner`, `dbsetup`, `--first-install`, `seed`, custodia H-1, `migrate-provider`, overlay y `retire-local-kek`) y vive hasta V12; `apex-smoke` es efímero (W0-2, W0-4, C5, V2). `down -v` solo sobre ellos, comprobado antes con `docker compose ls`.
- **S6-D57 · Cubetas y variables.** `USER_LIMITS` gana `attachments-upload` (10/60), `attachments-photo` (600/60), `attachments-download` (30/60) y `attachments-download-hour` (200/3600), `keys-rotate` (3/60) y `keys-rotate-hour` (10/3600), `cbom-export` (2/60); variables `USER_ATTACHMENTS_UPLOAD_LIMIT_PER_MIN`, `USER_ATTACHMENTS_PHOTO_LIMIT_PER_MIN`, `USER_ATTACHMENTS_DOWNLOAD_LIMIT_PER_MIN`, `USER_ATTACHMENTS_DOWNLOAD_LIMIT_PER_HOUR`, `USER_KEYS_ROTATE_LIMIT_PER_MIN`, `USER_KEYS_ROTATE_LIMIT_PER_HOUR`, `USER_CBOM_EXPORT_LIMIT_PER_MIN`. El catálogo pasa de 16 cubetas y 15 variables a **23 cubetas y 22 variables** (comentario de `.env.example`, `test_env_example.py`, el `sed` y el conteo «15» de `ci.yml` pasan a 22). Patrón S5-D98: W0-5 registra las siete claves con `CLAVES_SIN_RUTA_TODAVIA` de `test_user_limits_catalog.py` y cada slice las quita al darles ruta (B3, C2, C4, R1). Lecturas de llaves, bitácora, trabajos, firmas y listado de adjuntos: `staff-read`. `q` sobre `data_class` en `GET /crypto/{keys,ops,jobs}`; `GET /members/{id}/attachments` queda como exclusión nombrada en `test_list_routes_use_page_params` (lista corta por socio, sin búsqueda).
- **S6-D58 · Subruta del volumen `keys` (S5-D201, S6-D54).** Layout nuevo: `custody/` (`kek.bin`, `sign-ed25519.key`) y `jwt/` (par JWT). `api` y `tools` montan el volumen entero en `/run/apex/keys`; `worker` monta solo `custody` con `volume: {subpath: custody}` en `/run/apex/keys/custody` en `compose.yml` base (proveedor local: necesita la KEK y la llave de firma) y nada con `compose.openbao.yml` (ya hoy). Las rutas por defecto de `Settings` cambian a las nuevas; `init-keys` crea el layout nuevo; `init-keys --migrate-layout` (idempotente, `os.replace` dentro del volumen, sin sobrescribir, auditado en el log del comando) mueve un volumen plano al nuevo y lo ejecuta `deploy.sh` antes de `up`; `check-key-files.sh`, `test_compose_config.sh`, `test_deploy_script.sh` y `prod-smoke.sh` lo cubren. El volumen `keys` de desarrollo se migra una vez en W0-2.6 con `tar` previo a `docs/scratch/` (ignorado). W0-1.1 comprueba que Compose 5.6.1 renderiza `volume.subpath`.
- **S6-D59 · Subida por cuerpo crudo acotado y descarga con semáforo (M-3, M-4; E1, reescrita).** `POST /members/{member_id}/attachments?kind=photo|consent|other`: `kind` es un parámetro de consulta tipado (`Literal`) que FastAPI valida antes de ejecutar el handler, y el handler comprueba el socio (`ensure_exists`) y el rol por `kind` (coach solo `photo`) **antes de leer un solo byte**; el cuerpo es el archivo en crudo con el `Content-Type` del cliente (ignorado: el tipo lo deciden los bytes mágicos), sin multipart, sin `request.form()`, sin `UploadFile` ni `SpooledTemporaryFile` y sin `python-multipart`. Lectura con `async for trozo in request.stream()` acumulando en un `bytearray` hasta `ATTACHMENT_MAX_BYTES = 5_242_880`; el byte 5.242.881 corta la lectura (`ATTACHMENT_READ_LIMIT = 5_242_881` es cuánto se consume como máximo) y responde 413 `file_too_large` en el envelope JSON del api (D73); un `Content-Length` declarado mayor que 5.242.880 responde 413 sin leer; sin `Content-Length` (`chunked`) se aplica el mismo corte; un `Content-Length` falso (declara menos y manda más) cae en el corte, y uno que declara más y manda menos termina en 413 sin leer o en 422 `unsupported_type` por cabecera incompleta, nunca en un cuerpo colgado (timeout de lectura de uvicorn). Sin spool: nada se escribe en `/tmp`; el pico de memoria por subida es el cuerpo más el blob cifrado (unos 12 MiB para un sensible), acotado por el semáforo. Semáforo global del proceso `attachments.SENSITIVE_SLOTS = 4` para cifrar y descifrar; el excedente responde 503 `busy` con `Retry-After: 1` (el código ya existe). Nginx conserva `client_max_body_size 6m` en ese `location` (D23) para que 5.242.881 llegue al api y sea el api quien responda 413 (demo 3 y E2E lo exigen); de 6 MiB en adelante corta Nginx con el mismo envelope. **Qué prueba cada capa (E13):** `proxy-api.conf` tiene `proxy_request_buffering on`, así que Nginx lee el cuerpo entero (hasta 6m) a `/var/cache/nginx` y reenvía al api con `Content-Length` aunque el cliente use `chunked`; detrás de Nginx el api casi siempre responde 413 por `Content-Length` sin leer, y el corte por trozos solo actúa sin proxy. Por eso el corte por trozos, el `Content-Length` falso en los dos sentidos, `chunked`, el iterador infinito y los «0 trozos consumidos» se prueban **en el api por ASGI/`httpx` sin Nginx** (pasos 78 y 86), y a través de Nginx (demo 3, E2E, `test_nginx_conf.sh`) se prueba solo lo observable: 5.242.880 → 201, 5.242.881 → 413 del api (prueba de que el `client_max_body_size 5m` global del `server` no corta antes: el `location` más específico manda), 6 MiB o más → 413 de Nginx. El tmpfs `/var/cache/nginx` de `web` lleva `size=64m` en `compose.yml` (hoy sin `size`, hereda la mitad de la RAM; `test_compose_config.sh` lo exige). El front manda `fetch` con `body: File` (`api.upload`, F4).
- **S6-D60 · Módulo `attachments` y puertas.** `main.MODULES` registra `attachments` antes de `members`; `main.py` y `cli_base.py` llaman `attachments.service.register_reencryptor()` al armar el proceso (`test_reencryptor_registered_in_every_root.py`); tercera puerta de descifrado `modules/attachments/files.py:_decrypt_file` (y `_encrypt_file`) anotada en `test_reveal_single_door.py` e `IMPORTADORES_REALES`; `PRIVATE_HELPERS["attachments"] = {files, rules, queries, reencrypt, storage}`; `ALLOWED_EDGES` gana `members → attachments` (C2) y `members → settings` (C3). Claves de `details` de `sign_audit`: `firmadas`, `nada_nuevo`, `reintentos`, `sellado`, `atrasada`, `cadena_rota` (enteros); `ALERT_CONTEXT_KEYS` gana `through_seq` y `age_h`. El worker sondea al arrancar la unión de `crypto_classes` de `JOBS`; cada job llama `recovery.try_load(classes=spec.crypto_classes)` antes de trabajar.
- **S6-D61 · Rotación desde el api (H-2, D43).** `core/crypto/rotate_job.py`: `run_rotation(session_factory, job_id, *, batch_size)` extraído de `cli_ops/rotate_key.py` (el CLI lo llama con la misma conducta y pruebas); `rotation_engine(settings)` crea un `AsyncEngine` dedicado con `pool_size=1, max_overflow=0` para el candado de sesión `apex:rotate:<clase>` (el pool principal no pierde conexiones); `ROTATION_SLOTS = 1` por proceso (un segundo `POST` de cualquier clase mientras hay uno en vuelo responde 409 `rotation_running`); `ROTATION_MAX_S = 3600` deja el job `failed` con `error = "timeout"`; lotes de 500 filas o 50 adjuntos; `main.py` reanuda un job `running` al arrancar solo si el keyring está cargado, y si no lo anota en el log y espera al siguiente `POST` o al CLI. Guarda `0024` (`CREATE OR REPLACE crypto.guard_keys_update()` como `0015`, `downgrade` al texto de `0015`): con `current_user = 'apex_api'` solo pasa `active → decrypt_only`, en `purpose = 'encrypt'`, con otra fila `active` de `version` mayor en la misma clase y un `crypto_jobs` `running` de esa clase en la misma transacción, y `rotated_by` un `auth.users.id` distinto de `SYSTEM_USER_ID`; trigger nuevo `crypto.guard_jobs_update()` sobre `crypto_jobs`: `done` nunca decrece, `total` no cambia, `status = 'done'` exige `done = total`, el api solo toca `done, status, error, started_at, finished_at, updated_at`. **Precisión de H-2 (2):** la guarda no puede recontar los pendientes de una clase (no conoce ni el registro de clases ni el esquema `attachments`); el recuento con `FOR SHARE` lo hace `finish_rotation` por `count_pending` (D14) y la guarda exige `done = total`; `security-reviewer` de R1 confirma. **INSERT acotado (E6):** trigger `crypto.guard_jobs_insert()` `BEFORE INSERT` sobre `crypto_jobs`: con `current_user = 'apex_api'` solo pasa `kind = 'rotate'`, `status = 'running'`, `data_class` no nula, `total > 0`, `done = 0`, `error` nulo y `created_by` un `auth.users.id` distinto de `SYSTEM_USER_ID`; un job por clase lo garantiza el índice `uq_crypto_jobs_in_progress` existente. **Residual declarado (D61, `llaves.md`, RUNBOOK §14):** `apex_api` conserva `INSERT` en `crypto_keys` (S4B-D61, `ensure_keys`) y gana `INSERT` en `crypto_jobs`; un api comprometido podría insertar un job `running` con un `total` que no corresponde a la clase, o una fila `active` de versión mayor y pasar la vigente a `decrypt_only`; el daño queda acotado porque ninguna llave pasa de `decrypt_only` por el api (ningún dato se vuelve ilegible), `finish_rotation` recuenta por `count_pending` y cerrar en `done` exige `done = total`, y `retire-key` sigue siendo solo del CLI con manifiesto posterior; se detecta en `GET /crypto/jobs` y en la bitácora. ADR-005 no se toca (S6-D49). `0024` no modifica nada de las filas `sign` (E2). `AUDITABLE_TABLES` suma `crypto.crypto_keys`; como la tabla no es `__audited__`, una rotación deja exactamente una fila `update` (E5, paso 110).
- **S6-D62 · Verificación de firmas con la clave pública (M-1, D36; E10, reescrita).** `verify_signatures(session, *, through_seq)` verifica **todas** las firmas del tramo recorrido, por lotes de 100 con la misma pausa que la cadena, en el api y sin llamar a ningún proveedor: `bus.verify("audit.signature", payload, firma)` busca la llave por el `key_id` del blob (en cualquier estado: `active`, `decrypt_only`, `retired`) y verifica Ed25519 con `crypto_keys.public_key` de esa fila mediante `core/crypto/signature.py` (`verify_ed25519(public_key, data, signature)`, `cryptography` dentro de `core/crypto`); registra `crypto_ops(verify)` como hoy. Funciona con OpenBao sellado o inalcanzable: la firma es lo único que exige Transit. El estado es `none`, `ok` o `invalid`; `invalid` voltea `ok` y fija `broken_at_seq = first_invalid_seq` si la cadena estaba sana; la regla anti-retroceso (`max(through_seq)` firmado y persistido en `audit.signatures` frente al `last_valid_signature_seq` de la verificación anterior, más el recuento de filas) se evalúa igual sin red; el constructor del payload se elige por `payload_version`. `KeyProvider.verify` queda para la suite de contrato del proveedor; `ML-DSA-65` por clave pública llega con EP-26 (hoy `verify_ed25519` rechaza otro `algorithm` con `unsupported`). Sin `SIGNATURE_SAMPLE`, sin `secrets`, sin estado `unavailable` en `signature_state`, en el CLI ni en la pantalla.
- **S6-D63 · TLS sin dominio real.** P-TLS: `scripts/ci/tls-smoke.sh`, CA interna de Caddy, `alpine:3.22` por digest con OpenSSL 3.5 fijado por versión de `apk`, `apex.localhost`; job `tls-smoke` en `images` de la CI; `prod-smoke.sh --tls`; `deploy.sh` sondea `/health` con `docker compose exec web wget -qO- http://127.0.0.1/api/v1/health` cuando `DEPLOY_COMPOSE_EXTRA` contiene `--profile tls` y avisa si `caddy` no quedó `healthy`.
- **S6-D64 · Caddy y Nginx.** `caddy:2.11.3@sha256:…` (digest con fecha y comando en W0-1.1; 2.10 o superior), `profiles: ["tls"]`, `read_only`, `cap_drop: [ALL]` más `cap_add: [NET_BIND_SERVICE]`, `no-new-privileges`, IP fija `${APEX_CADDY_IP:-172.30.0.11}` fuera del `ip_range` dinámico, volúmenes `caddy_data` y `caddy_config`, `infra/caddy/Caddyfile:ro`, `ports: ${WEB_PORT:-80}:80` y `${TLS_PORT:-443}:443` (en `compose.tls.yml`, que además pone `ports: !override []` en `web`), healthcheck con `wget -qO- http://127.0.0.1/_caddy_health` (E8: ruta propia que responde 200 por HTTP antes de la redirección; sin depender de cómo BusyBox trate un 308). `Caddyfile`: `{ admin off; acme_ca {$APEX_ACME_CA:https://acme-v02.api.letsencrypt.org/directory}; email {$APEX_ACME_EMAIL} }`; un sitio `http://` en `:80` con `handle /_caddy_health { respond "ok" 200 }` y, para todo lo demás, `redir https://{$APEX_DOMAIN}{uri} 308` (redirección explícita, no la automática: así la ruta de salud nunca redirige y el 308 queda escrito y probado); el sitio `https://{$APEX_DOMAIN}` con `tls {$APEX_TLS_ISSUER} { curves x25519mlkem768 x25519; protocols tls1.2 tls1.3 }` (`APEX_TLS_ISSUER` = `internal` solo en smoke y desarrollo, o el correo ACME), `header Strict-Transport-Security "max-age={$APEX_HSTS_MAX_AGE:300}"` (sin `includeSubDomains` ni `preload`; escalones 300 s, 604800, 31536000 en `tls.md`) y `reverse_proxy web:80` (Caddy escribe su propio `X-Forwarded-For` y `X-Forwarded-Proto https`; sin `trusted_proxies`); `test_caddyfile.sh` comprueba la ruta de salud, el 308 explícito, que `/_caddy_health` no existe en el sitio HTTPS y (M1) que `/.well-known/acme-challenge/x` **no** responde 308 en el sitio `http://` (`handle /.well-known/acme-challenge/*` delante del `redir`, dejando pasar al solucionador ACME de Caddy); el ACME HTTP-01 real con dominio queda como paso humano explícito en `tls.md`. Nginx (O5 y E11, S6-D82; la imagen `web` hornea `default.conf` y `snippets/` en el build, así que nada se renderiza dentro del contenedor `read_only` ni dentro del árbol versionado): `infra/nginx/snippets/real-ip.conf.in` es la plantilla versionada con `__APEX_CADDY_IP__`; `infra/nginx/snippets/real-ip.conf` es el renderizado con el valor por defecto `172.30.0.11`, versionado y horneado; `compose.yml` monta `${APEX_REAL_IP_CONF:-./nginx/snippets/real-ip.conf}:/etc/nginx/snippets/real-ip.conf:ro` (bind de un solo archivo, que gana al horneado); `deploy.sh` renderiza con `sed` desde el `.in` a `${DEPLOY_STATE_DIR}/real-ip.conf` (fuera del árbol) y exporta `APEX_REAL_IP_CONF` para `up` cuando `APEX_CADDY_IP` difiere del valor por defecto; `prod-smoke.sh`, `compose-smoke.sh` y `tls-smoke.sh` renderizan en un directorio temporal propio; `test_nginx_conf.sh` exige que el `.conf` versionado sea el `.in` renderizado con el valor por defecto; `test_deploy_script.sh` cubre el render y comprueba que `git status --porcelain` queda vacío tras desplegar con otra IP (los chequeos de árbol limpio de `deploy.sh:101,218` siguen pasando). El snippet trae `set_real_ip_from <ip>/32; real_ip_header X-Forwarded-For; real_ip_recursive off;` en el contexto `server` antes de todo `limit_req`, y `default.conf` el `map $realip_remote_addr $apex_proto` que vale `https` solo si el par TCP es Caddy y `$http_x_forwarded_proto` es exactamente `https`, `http` en cualquier otro caso; `proxy-api.conf` pasa `X-Forwarded-Proto $apex_proto`. `cap_drop: [ALL]` (M-7c, L-6; E9, M2): `grep -n cap_drop infra/compose.yml` en HEAD lo encuentra en nueve de los diez servicios declarados (`api`, `backup`, `dbsetup`, `migrate`, `openbao-bootstrap`, `openbao`, `tools`, `web`, `worker`; `web` ya con `CHOWN`, `SETGID`, `SETUID`, `NET_BIND_SERVICE`); el único sin `cap_drop` es `db` (se suma con las capacidades mínimas de la imagen de Postgres verificadas en W0-4.1: `CHOWN`, `DAC_OVERRIDE`, `FOWNER`, `SETGID`, `SETUID`) y el nuevo `caddy` nace con `NET_BIND_SERVICE`; nunca `NET_RAW` en ninguno.
- **S6-D65 · `public_origin` y `validate_origins`.** `APEX_DOMAIN: str | None` en `Settings` validado como `host[:puerto]`; `public_origin(settings)` = `https://{APEX_DOMAIN}` o `FRONT_BASE_URL`; `validate_origins(settings)` falla el arranque, nombrando la variable, cuando con dominio: `CORS_ORIGINS` trae un origen `http:`, `FRONT_BASE_URL != public_origin` (N-11), `COOKIE_SECURE != true` («el navegador no guardaría la cookie»), `ALLOW_INSECURE_COOKIE = true`; sin dominio no cambia nada (el validador P7 de S4B-D154 sigue). `cookie_secure(settings)` devuelve `COOKIE_SECURE` (explícito); `auth/cookies.py` lo usa; CORS en `create_app()` acepta `CORS_ORIGINS` más `public_origin`. `ACME`/Caddy (`APEX_CADDY_IP`, `APEX_TLS_ISSUER`, `APEX_ACME_EMAIL`, `APEX_ACME_CA`, `APEX_HSTS_MAX_AGE`, `TLS_PORT`) van en `.env.ops.example` y `NON_API_ENV_VARS`; solo `caddy` las recibe (`test_env_isolation.sh`).
- **S6-D66 · Versión y release.** `api/pyproject.toml`, `uv.lock`, `web/package.json` y su lock a `0.3.0`; `CHANGELOG.md` gana `## [0.3.0]` con fecha, SHA de cierre y cuatro bloques (EP-17 a EP-20); `bash scripts/ci/check-release-version.sh --check v0.3.0`; `git tag -a v0.3.0` local. Push, PR (con el del Sprint 5 fusionado antes, D55), merge, Release y firma de la etiqueta: pasos humanos.
- **S6-D67 · Revisiones por slice.** `database-reviewer` en A1, A3, C1, R1 y V9; `security-reviewer` en todos; V11 sobre el árbol fusionado con los puntos de la DoD (api no firma; guarda `0024`; adjuntos solo por el api con rol, `no-store`, `nosniff`, bytes mágicos; HSTS solo con dominio; ningún material en auditoría ni CBOM; foto sin fila por vista).
- **S6-D68 · `run-gates.sh`:** cuatro corridas (A3, C5, E1, V10).
- **S6-D69 · La llave de firma solo cambia de proveedor, nunca se recifra ni se rota «en sitio» en v0.3.** `POST /crypto/keys/{id}/rotate` sobre `purpose = sign` responde 409 `purpose_not_rotatable` (N-07) y `rotate-key audit.signature` sin `--provider` o con el proveedor vigente sale 2 `purpose_not_rotatable`; con `--provider <otro>` (D81) crea la llave nueva. La rotación de la llave de firma dentro del mismo proveedor (llave Transit nueva con otro nombre) queda descrita en ADR-006 con dueño EP-26. `retire-key` rechaza una llave `sign` referenciada por `audit.signatures.key_id` (M-2a, 2 `signatures_reference_key`); la referencia se valida con `^apex-sign-audit[a-z0-9-]*$` (M-2b); ninguna política concede `rotate` ni `config` de esa llave (M-2c); `tools` exige `--as` para firmar en producción (M-2d); el índice único parcial existente de `(purpose, data_class)` `active` cubre M-2e (A1 lo prueba).
- **S6-D70 · Worktree del front.** `.claude/worktrees/sprint-06-front` (rama `feat/sprint-06-front`) nace tras el checkpoint de C5; orden F1, F3, F4, F5; F2 tras el checkpoint de R1 con `git rebase feat/sprint-06-auditoria-firmada-llaves-adjuntos-tls`. `SLICE_BASE=$(git merge-base HEAD main)` en cada comando del worktree; comandos pesados serializados; fusión única en V1.
- **S6-D71 · Evidencia de las demos.** Demo 1 (firma) y 2 (llaves) en el ensayo con overlay OpenBao (8280); demo 3 (adjuntos) en el ensayo a través de Nginx; demo 4 (TLS) con `$DCET` y `APEX_DOMAIN=apex.localhost:8443`, más el modo LAN con `$DCEB`. La «firma atrasada» se simula con `--date --simulate` sobre `apex_sim` en `db_test` (S4A-D48), nunca en el ensayo.
- **S6-D72 · `init-keys --data-class`.** Único creador de filas `sign` (`audit.signature`) y, para `attachment.sensitive`, atajo explícito; `ensure_keys` del api sigue creando las clases `encrypt|index` del registro (incluida `attachment.sensitive` al arrancar tras C1) y nunca una fila `sign`. Idempotente; imprime el algoritmo y el proveedor; auditado (`crypto_ops` `wrap` para `encrypt`, `audit_log` `insert` sobre `crypto.crypto_keys` con `after` sin material); `--as` obligatorio en producción.
- **S6-D73 · Un solo código de tamaño, dos emisores (E1, reescrita).** El tamaño siempre responde **413** con el envelope `{"code": "file_too_large", "message": …, "field": "file"}`: lo emite el api (`FileTooLarge` → 413) al superar 5.242.880 bytes leyendo o ante un `Content-Length` declarado mayor, sin leer; y lo emite Nginx (`@too_large`, mismo envelope) de 6 MiB en adelante. `_DESCRIPCIONES` gana el 413 (`test_error_codes_per_route`, `test_error_responses_in_openapi`); el 422 queda solo para `unsupported_type` (campo `file`) y para `kind` o `member_id` inválidos. El front muestra el mismo mensaje venga de quien venga.
- **S6-D74 · `retire-key` y el respaldo (L-3).** `retire-key` de una llave `encrypt` cuenta además `attachments.attachments.key_id` y exige un manifiesto firmado con `created_at` posterior al `finished_at` del job de rotación que dejó la llave en `decrypt_only` (el respaldo conserva lo recifrado); se suma a las precondiciones de S5-D72.
- **S6-D75 · `__audit_exclude__` (L-1).** Único toque a `core/audit.py` del sprint: el hook genérico omite de `before`/`after` las columnas listadas en `__audit_exclude__` del modelo (`attachments`: `filename_random`, `key_id`); prueba en `tests/core/test_audit_hook_db.py` con un modelo de prueba. El serializador canónico y `record` no cambian.
- **S6-D76 · Supresión a petición (M-10, D38).** En v0.3 no hay comando; `docs/operacion/adjuntos.md` y RUNBOOK §14 documentan el procedimiento manual del operador ante una solicitud bajo la Ley 1581: guardar la evidencia de la solicitud, `attachments-check --as` antes y después, borrar el objeto del volumen `uploads` desde `tools` (la fila no se toca: el trigger prohíbe `DELETE` y el `UPDATE` solo admite `key_id`) y dejar la constancia con `audit.record(action="delete", table_name="attachments.attachments", record_id=<id>)` desde `tools` con `--as`; el respaldo conserva el archivo hasta su rotación; el comando `attachments purge` con columna `purged_at` tiene dueño titular (v0.4). `security-reviewer` de C1 valida el texto.
- **S6-D77 · `APEX_DOMAIN` con puerto (O3; E12, corregida).** `Settings.ENV` sigue siendo `Literal["dev", "production"]` (no existe `staging` y no se añade). `APEX_DOMAIN` admite `host:puerto` (`apex.localhost:8443`) solo si `ALLOW_DOMAIN_PORT=true` (campo nuevo de `Settings`, por defecto `false`, en `.env.example`) y el host termina en `.localhost`; el api NO lee `APEX_TLS_ISSUER` (sigue siendo variable solo de `caddy`, en `.env.ops.example` y `NON_API_ENV_VARS`, como fija el paso 7): que el emisor `internal` solo se use con hosts `*.localhost` lo exige `test_caddyfile.sh` sobre la configuración de Caddy, no `Settings` (corrección de la verificación acotada, ronda 3); con `ENV=production` y cualquier otro host, un puerto en `APEX_DOMAIN` o `ALLOW_DOMAIN_PORT=true` fallan el arranque nombrando la variable; en `dev` la misma regla (sin excepción por `ENV`). Así el ensayo y el smoke (`ENV=production`, `apex.localhost:8443`, `tls internal`) arrancan y un servidor real con `ALLOW_DOMAIN_PORT=true` no. `public_origin` copia el valor tal cual; Caddy sirve el sitio `apex.localhost:8443` (`TLS_PORT=8443`). W0-5.1 lo prueba con la tabla de los cuatro factores.
- **S6-D78 · Versiones mínimas de Docker (E4).** `volume.subpath` exige Docker Engine 26 (API 1.45) y Compose 2.26; `deploy.sh` lo comprueba al principio con `docker version --format '{{.Server.APIVersion}}'` y `docker compose version --short` (sale 2 con «Docker Engine 26 / API 1.45 y Compose 2.26 o superiores; tiene X e Y») antes de tocar nada; `test_deploy_script.sh` cubre 1.44 (2), 1.45 (sigue) y Compose 2.25 (2); `instalar-en-servidor.md`, `actualizar.md` y RUNBOOK §12 fijan los mínimos; `prod-smoke.sh` los imprime. El host de desarrollo tiene Engine 29.9.2 (API 1.56) y Compose 5.6.1.
- **S6-D79 · Un solo proceso del api (O4).** El semáforo (D59), el rotador único (D61) y `single_flight` de S5 suponen un solo worker de uvicorn: `scripts/ci/test_compose_config.sh` falla si `api` declara `command` con `--workers`, o si algún servicio recibe `UVICORN_WORKERS` o `WEB_CONCURRENCY`; `scripts/ci/test_api_image.sh` falla si el `CMD` de la imagen lleva `--workers`; `tests/core/test_single_process.py` fija `uvicorn` sin `workers` en el `Dockerfile` leído como texto. Escalar a varios procesos exige mover esos tres candados a la base (anotado como deuda con dueño en RUNBOOK §1).
- **S6-D80 · Archivos de `cli_ops/` y topes reales (E7).** `TOPE_CLI_OPS` real: `kek.py` 400, `rotate_key.py` 260, `retire_key.py` 200, `rotate_kek.py` 200, el resto 150. Un archivo por comando nuevo, cada uno bajo 150: `cli_ops/sign_audit.py` (`sign-audit`), `cli_ops/attachments_check.py` (`attachments-check`), `cli_ops/keys_layout.py` (`migrate_layout(paths) -> LayoutReport`) y `cli_ops/keys_data_class.py` (`ensure_data_class(session, settings, data_class, actor) -> DataClassReport`); `init-keys` sigue definido en `cli.py` (línea 130; el archivo mide 350 con tope 700) y despacha `--migrate-layout` y `--data-class` a esos dos módulos, que no se importan entre sí ni importan `keys.py` (S4B-D76); `cli_ops/keys.py` solo gana las subcarpetas en `key_paths_in`. `rotate_key.py` y `retire_key.py` se mantienen bajo sus topes de 260 y 200 al extraer `run_rotation`, sumar `--provider` para `sign` (D81) y el conteo de `attachments.key_id`; si alguno no cabe, `TOPE_CLI_OPS` cambia solo con decisión numerada.
- **S6-D81 · La llave de firma no migra de proveedor: clave pública en `crypto_keys` y llave nueva por `rotate-key --provider` (E10, crítica 2).** (1) `migrate-provider` sigue excluyendo `purpose = 'sign'` (S5-D183 intacta; `migration.py` líneas 6 y 52) y, si se fuerza `--data-class audit.signature`, sale 2 `signatures_reference_key` sin tocar nada. (2) `0021` añade `crypto_keys.public_key text` nula con CHECK `(purpose <> 'sign') OR (public_key IS NOT NULL)`: base64 estándar de los 32 bytes crudos de la clave pública Ed25519 (el mismo formato que devuelve Transit en `transit/keys/apex-sign-audit` → `keys.<versión>.public_key`); la llena quien crea la fila `sign`: `init-keys --data-class audit.signature` (leyendo `key_info` del proveedor: Transit, o derivada del archivo `custody/sign-ed25519.key` con `local`) y `rotate-key audit.signature --provider`; `ensure_keys` sigue sin crear filas `sign` (D72); `KeyInfo` y `FakeTransit.key_info` exponen `public_key`; `public_key` es inmutable (sin `UPDATE` por columna para `apex_api` y `apex_worker`; `0024` la suma a las columnas que la guarda rechaza cambiar) y nunca sale en el inventario ni en el CBOM (no es material, pero tampoco hace falta). (3) `bus.verify` verifica con esa clave pública en proceso (D62); la validación `^apex-sign-audit[a-z0-9-]*$` de la referencia (M-2b) y `sign_key_ref()` se conservan para crear filas. (4) Cambiar la firma de proveedor es `rotate-key audit.signature --provider <local|openbao> --reason … --as …` (`cli_ops/rotate_key.py`, bajo 260): comprueba que el proveedor destino está configurado y que su llave existe (`key_info` de Transit o el archivo local), inserta la fila `version + 1` `active` con `provider`, `wrapped_material` = referencia (`sign_key_ref()` del destino) y `public_key`, pasa la anterior a `decrypt_only` (`next_key_state`) en la misma transacción, deja `crypto_ops(wrap)` y una fila `update` de auditoría sin material, y no recifra nada (una firma es inmutable); a partir de ahí `sign_latest` firma con la nueva y las firmas anteriores verifican por su `key_id`. (5) `retire-key` de una llave `sign` referenciada por `audit.signatures.key_id` sigue saliendo 2 (M-2a), de modo que la clave pública de toda firma guardada se conserva mientras existan firmas.
- **S6-D82 · `real-ip.conf` fuera del árbol (E11, crítica 2).** `compose.yml`: `web` monta `${APEX_REAL_IP_CONF:-./nginx/snippets/real-ip.conf}:/etc/nginx/snippets/real-ip.conf:ro`; `.env.ops.example` documenta `APEX_REAL_IP_CONF` (vacía por defecto). `deploy.sh` renderiza `infra/nginx/snippets/real-ip.conf.in` con `sed` a `${DEPLOY_STATE_DIR}/real-ip.conf` (modo 644, idempotente) y pasa `APEX_REAL_IP_CONF` a Compose cuando `APEX_CADDY_IP` difiere de `172.30.0.11`; `prod-smoke.sh`, `compose-smoke.sh` y `tls-smoke.sh` renderizan en un temporal propio (`mktemp -d` dentro de `TMPDIR` del auxiliar) y lo borran al salir; nadie escribe dentro de `infra/`. `test_deploy_script.sh`: con `APEX_CADDY_IP=172.31.2.11` el archivo aparece en `DEPLOY_STATE_DIR`, `up` recibe la variable y `git status --porcelain` queda vacío; con la IP por defecto no se renderiza nada. `test_compose_config.sh`: el bind con la variable y su valor por defecto. RUNBOOK §12 y `tls.md` lo explican.

### Contradicciones de contrato cerradas en T-DOC (W0-1.3)

- `0040`…`0051` → `0021`…`0024`; `0042`, `0045`, `0046`, `0051` no existen.
- «ML-DSA si OpenBao la ofrece» y «consultar capacidades de Transit» → Ed25519 único (D51); sin sonda.
- «`sign_latest` en `core/audit.py`» → `core/audit_sign.py`.
- «el router importa `core.audit`» → `set_audit_writer` (D52).
- «`core/crypto/__init__.py` vacío» → vacío de verdad en B1.
- US-145 criterio 7 (`retired`) → `decrypt_only`; sin `--resume` (`start_rotation` reanuda por clase).
- US-141 criterio 3 → `error` con alerta; sin `skipped`; además H-1 (no se firma una cadena que no cuadra).
- US-142 → verificación con la clave pública de `crypto_keys`, completa y sin custodio (D81); sin estado parcial ni muestreo.
- US-141/US-135 «`migrate-provider` migra la fila `sign`» → no: sale 2 `signatures_reference_key`; el cambio de proveedor es `rotate-key audit.signature --provider` (D81).
- US-147 criterio 5 y «`sensitive` lo envía el cliente» → `download` existe desde `0002`; `sensitive` lo decide el servidor.
- US-148 → la foto no se audita por vista (ADR-007); `Socio_Form.html` sin campo de foto (`DESIGN-GAP`).
- US-149 criterio 1 → contrato sin cambio; `consent_required_from` nulo no exige; versión copiada; US-149 criterio 4 (`sensitive=false` del cliente) → el campo no existe (422 por `extra`).
- US-150 «emite `SensitiveFieldRevealed`» → no existe ni se crea (D53); coach no descarga `consent`/`other` (M-6).
- US-151 «`0051` y KPI nuevo» → sin migración; el KPI existe (S5-D240); queda el filtro y el enlace.
- US-152 criterios 5 y 8 → pasos humanos; «Caddy 2.10» → 2.11.3 por digest.
- US-153 criterio 2 → `max-age=300` inicial sin `includeSubDomains`, escalonado; criterio 4 y 7 → D65.
- `docs/runbooks/tls.md` → `docs/operacion/tls.md`; `LAN_ORIGIN` → `FRONT_BASE_URL`; `scripts/workflow/tls-smoke.sh` → `scripts/ci/tls-smoke.sh`.
- «Puerto `Reencryptor` en `registry.py`» (`CLAUDE.md`, `SPRINT-06.md`) → `core/crypto/reencryptor.py`.
- «`test_audited_tables.py`: `wrapped_material` excluido del diff» → `crypto_keys` no es auditada; auditoría explícita saneada.
- «`JOB_KINDS` admite `rewrap`» → ya lo admite. «`test_core_independent.py`» → consolidado en `test_core_import_direction.py`.
- `CLAUDE.md`: `liboqs-python` → EP-26; `registry.py` sin `Reencryptor`; archivos nuevos (`core/audit_sign.py`, `core/crypto/{router,inventory,schemas,reencryptor,cbom,rotate_job}.py`, `modules/attachments/`, `worker/jobs/sign_audit.py`, `cli_ops/{sign_audit,attachments_check}.py`, `infra/caddy/`, `infra/compose.tls.yml`, `scripts/ci/tls-smoke.sh`); «Caddy opcional» → perfil `tls`; bloque de licencias (boto3 opcional, Caddy, alpine; ninguna dependencia de ejecución nueva).
- `POST /members/{id}/attachments` «multipart con `file` y `kind`» (US-147, US-148, D22, D45) → cuerpo crudo con `?kind=` y `Content-Type` del archivo (E1); `ROUTES.md` lo dice.
- «`init-keys --data-class` en `cli_ops/keys.py`» → `init-keys` sigue en `cli.py` y despacha a `cli_ops/keys_data_class.py` y `cli_ops/keys_layout.py` (E7, D80).
- `openbao/config.hcl:23` («TLS llega con Caddy/EP-20») → Caddy no cifra `custody`; residual v0.4 (operador).
- `instalar-en-servidor.md` («TLS todavía no») → perfil `tls` y `tls.md`.

## 2. Fixtures y utilidades de prueba compartidas

- **W0-2:** `scripts/ci/fixtures/attachments/make_attachments.py` (biblioteca estándar; genera `foto-5242880.jpg`, `foto-5242881.jpg`, `grande-6300000.bin` y `pequeno-100k.bin` en una carpeta temporal para `test_nginx_conf.sh`; nada binario grande en git); `scripts/ci/fakes/docker` gana `volume.subpath` para `test_deploy_script.sh`.
- **W0-4:** `infra/caddy/tests/test_caddyfile.sh` (Bash puro, `grep`/`awk`); `scripts/ci/tls-smoke.sh --dry-run` (solo renderiza y lista comprobaciones, para `test_infra_scripts.sh`).
- **A1:** `tests/factories/signatures.py` (`make_signature(session, through_seq, *, key, algorithm="Ed25519", payload_version=1)`, `cadena_con_firmas(session, filas, firmas)` que escribe entradas reales por `audit.record` y firma por `sign_latest`, `alterar_fila(session, seq)` con los triggers apagados, `borrar_firma(session, through_seq)`); `tests/conftest.py` gana `LIMPIAR_SIGNATURES` (`DO $$ … IF to_regclass('audit.signatures') IS NOT NULL` con `DISABLE TRIGGER USER` y `rearm_always_sql`) **antes** de `audit_log` en `LIMPIEZA_DE_SESION`; `tests/factories/fake_transit.py` firma y verifica Ed25519 de verdad bajo `transit/sign|verify/<nombre>` y expone `key_info(nombre)` con `type`; `tests/crypto/conftest.py` gana `fila_sign(session, provider)`.
- **A2:** `tests/worker/conftest.py` gana `sign_ctx(frozen_clock)`, `espera_falsa` (parchea `asyncio.sleep` del job y registra los segundos) y `alertas_capturadas` (sink de lista); `tests/cli/conftest.py` gana `fila_sign_local`.
- **A3:** `tests/audit/conftest.py` gana `cadena_firmada(session, firmas=3)`, `custodio_sellado(fake_transit)` (estado `sealed` en `status()` y 503 en `sign` y `verify`: sirve para probar que la verificación no lo toca) y `firma_de_llave_retirada(session)` (una firma cuya llave pasó a `decrypt_only` y luego a `retired` por `rotate-key --provider` y `retire-key` con las firmas migradas a otra llave en la prueba; D81).
- **B1:** `tests/crypto/conftest.py` gana `cliente_admin` (app con `set_audit_writer` cableado), `sin_audit_writer` (app sin puerta, para el 503 `busy`), `reencryptor_doble` (implementación en memoria del `Protocol` con contadores) y `llaves_mixtas(session)` (encrypt, index, sign, decrypt_only).
- **B3:** `tests/crypto/conftest.py` gana `cbom_de(keys)`.
- **C1:** `tests/factories/files.py` (JPEG, PNG, PDF, ELF, PE; `de_tamano(n, kind)`); `tests/attachments/conftest.py` gana `uploads_tmp` (autouse: `UPLOADS_DIR` a `tmp_path`), `storage_local`, `s3_stubber` (`botocore.stub.Stubber`, sin red), `socio(session)` (reutiliza `tests/factories/members.py`), `adjunto_sensible(session, socio)` y `adjunto_foto(session, socio)`; `tests/conftest.py` gana `LIMPIAR_ATTACHMENTS` antes de `LIMPIAR_MEMBERS`.
- **C2:** `tests/members/conftest.py` gana `cuerpo_crudo(data, *, chunked=False, content_length=None, infinito=False)` (devuelve `content=` para `httpx`: bytes, un generador asíncrono que cuenta trozos consumidos, o uno infinito; y las cabeceras `Content-Length`/`Transfer-Encoding` pedidas) y `sin_tempfile` (monkeypatch que falla si `tempfile` se usa durante la petición; E1).
- **R1:** `tests/crypto/conftest.py` gana `socios_cifrados(session, n)` (de `_rotacion.py`), `rotacion_en_vuelo(cliente_admin)` (arranca y detiene la tarea con un evento) y `motor_dedicado_contado` (cuenta conexiones del pool principal durante la rotación).
- **E1:** `tests/core/_cripto_apoyo.py` gana `settings_dominio()` y `settings_lan()`.
- **Front:** `web/src/test/upload.ts` (respuestas de `api.upload` falsas y `File` de tamaños exactos); `web/tests/e2e/helpers/stack.ts` gana `subirAdjunto(memberId, kind, ruta)`, `rotarLlave(dataClass)` y `firmaActual()` (API del ensayo).

## 3. Paralelismo: cuándo lanzar el front

- El backend corre en serie en la rama del sprint.
- El worktree nace tras el checkpoint de C5 (S6-D70): contratos de firma (A3), llaves de lectura (B1 a B3), adjuntos y consentimiento (C1 a C5) ya exportados. Corren F1 (A3), F3 (C2, C4), F4 (C2, C3) y F5 (C5; E1 solo en textos) mientras el backend hace R1 y E1.
- F2 empieza tras el checkpoint de R1 (`POST /crypto/keys/{id}/rotate`), con `git rebase` y `npm run gen:api` sin diff.
- Comandos pesados serializados (un `pytest`, un `vitest`, un Playwright, un `buildx` a la vez en todo el equipo; lo anota el cuaderno). Ningún paso del front toca `api/`, `docs/openapi.json`, `types.ts`, `DECISIONES.md` ni `CLAUDE.md`; sí toca `docs/BRECHAS.md` §14 (filas del front) y su cuaderno.
- V empieza cuando F2 tiene checkpoint.

## 4. Wave 0

### S6-W0-1 · Línea base, T-DOC, decisiones, ADR-006 y ADR-007, dependencias y licencias

- **Historias:** T-DOC de US-140 a US-153.
- **Cierra:** C1 (a..k), parte de C4 (dependencias) y C7 (licencias), Q1 a Q12 del blueprint y P1 a P18 de la exploración (por decisión), bugs 1, 5, 12, 14, 15, 17 del impacto §7, `test_adr_docs` (5 → 7).
- **Depende de:** aprobación de este plan (incluido el punto explícito de ADR-006 y ADR-007, S6-D55). **Migración:** ninguna.

**Paso 1 · W0-1.1 · Línea base**

1. Estado del stack: `$DC ps` (seis `healthy`); `$DC exec api alembic current` = `0020 (head)`; `git status` limpio salvo este plan; `git worktree list` solo el principal; ids de imagen con `docker image inspect --format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}}'` (revisión `3cd752a`); `docker stats --no-stream`; `git log --oneline main..HEAD | wc -l` (el Sprint 5 sin fusionar: paso humano pendiente, no bloquea).
2. Red y puertos: `netstat -ano | findstr -E "8280|8380|8443|8200"` vacío; `docker network ls` e `inspect`: `172.31.2.0/24`, `172.31.3.0/24`, `172.31.12.0/24`, `172.31.13.0/24` libres; `docker compose version` 5.6.1.
3. Digests con `docker buildx imagetools inspect`, anotados con fecha y comando: `caddy:2.11.3` (índice multi-arquitectura; `docker run --rm caddy:2.11.3@sha256:… caddy version` y `caddy validate --config -` con un `Caddyfile` mínimo con `curves x25519mlkem768` y `admin off`), `alpine:3.22` (en un contenedor desechable `apk add --no-cache openssl` → `openssl version` 3.5.x y `openssl s_client -help 2>&1 | grep -c groups` = 1; se anota la versión exacta del paquete para fijarla en `tls-smoke.sh`).
4. Supuestos del plan en contenedores desechables (al cuaderno, sin cambiar el árbol): Compose renderiza `volumes: [{type: volume, source: keys, target: /run/apex/keys/custody, volume: {subpath: custody}}]` y `ports: !override []` (`docker compose -f <scratch>.yml config`); la imagen de Nginx de `web` con `cap_drop: [ALL]` más `NET_BIND_SERVICE, CHOWN, SETGID, SETUID` arranca; `python -c "import starlette; print(starlette.__version__)"` desde `api/` (1.9.0) y, con una app mínima bajo `uvicorn`, que `request.stream()` entrega trozos sin spool y acepta `Transfer-Encoding: chunked` y un `Content-Length` distinto del real (E9, E1); `uv pip show python-multipart` ausente y así sigue; `docker version --format '{{.Server.APIVersion}}'` (host: Engine 29.9.2, API 1.56) y `docker compose version --short` (5.6.1) frente a los mínimos de D78.
5. `apex-db-1`, solo lectura: `count(*)` de socios; `SELECT provider, purpose, state, count(*) FROM crypto.crypto_keys GROUP BY 1,2,3` (8 `local` `active`, ninguna `sign`); `SELECT max(seq) FROM audit.audit_log`; `pg_roles` `apex%`; última fila de `worker.job_runs`; `\dn` (diez esquemas, sin `attachments`).
6. Gates baratos en HEAD: `ruff check`, `ruff format --check`, `mypy src`, `tsc --noEmit`, `bash scripts/workflow/tests/run.sh`, `bash scripts/ci/test_compose_config.sh`, `bash scripts/ci/test_nginx_conf.sh`, `bash scripts/ci/test_openbao_infra.sh` (101 ok), `bash scripts/ci/test_deploy_script.sh` (282 ok). Conteos al cuaderno.

**Paso 2 · W0-1.2 · Cuaderno.** `docs/scratch/sprint-06.md` gana «Planificación» (rutas de los cinco documentos de las Fases 0 a 2) y «W0-1 · línea base» con todo el paso 1 (sin secretos).

**Paso 3 · W0-1.3 · T-DOC**

- `SPRINT-06.md`: migraciones `0021` a `0024`, slices y orden (D56), endpoints reales (9 nuevos; `GET /dashboard` y `GET /health` sin cambio), DoD con «Ed25519 en v0.3», «HSTS escalonado», «`decrypt_only` al terminar», demo con `apex.localhost` y CA interna, `restore_e2e.sh` con un adjunto.
- Desgloses de EP-17 a EP-20 e historias: US-140 (`payload_version`, `core/audit_sign.py`, Ed25519, H-1), US-141 (reintentos dentro de la corrida, `audit_chain_broken`, keyring por job), US-142 (verificación con la clave pública, sin custodio, D81), US-143 (sin `0045`; `records_count` por el registro; «Proveedor activo» de `crypto_keys`), US-144 (`JOB_KINDS` ya trae `rewrap`), US-145 (grants acotados y `0024`; `decrypt_only`; sin `--resume`; pasa de `ARCHITECTURAL_GAP_DETECTED` a READY), US-146 (`cbom-export`, sin referencias `sign`), US-147 (`sensitive` del servidor; multipart `>= 0.0.20`; S3 apagado), US-148 (foto sin fila por vista; `attachments-photo`; `DESIGN-GAP` del campo), US-149 (contrato sin cambio; fecha nula no exige; la autorización subida fija `data_consent_at`), US-150 (sin `SensitiveFieldRevealed`; coach solo foto), US-151 (sin `0051`; KPI existente), US-152 (2.11.3; criterios 5 y 8 humanos), US-153 (HSTS escalonado; `FRONT_BASE_URL`; `COOKIE_SECURE` explícito).
- `docs/design/ROUTES.md`: `POST /members/:id/attachments?kind=photo|consent|other` con el archivo como cuerpo crudo (E1; la fila actual dice foto y autorización sin forma), `GET /attachments/:id` y `GET /members?consent=missing`.
- `CLAUDE.md`: árbol (`core/audit_sign.py`, `core/crypto/{router,inventory,schemas,reencryptor,cbom,rotate_job}.py`, `modules/attachments/`, `worker/jobs/sign_audit.py`, `cli_ops/{sign_audit,attachments_check}.py`, `infra/caddy/`, `infra/compose.tls.yml`, `scripts/ci/tls-smoke.sh`, `docs/operacion/{llaves,adjuntos,tls}.md`), stack (`liboqs-python` → EP-26), bus (puerto `Reencryptor`, clases `attachment.sensitive` y `audit.signature`), seguridad (cubetas nuevas; Caddy; `real_ip`), licencias (boto3 opcional, Caddy, alpine; sin python-multipart), comandos (`sign-audit`, `init-keys --data-class`, `attachments-check`, `--run-once sign_audit`, `tls-smoke.sh`).
- `RUNBOOK.md`: índice con §14 «Firma, llaves por pantalla, adjuntos y TLS (Sprint 6)»; `BRECHAS.md` §14 (nueva, filas del sprint; 13.26 se cierra; 13.6, 13.10 y 13.11 siguen con dueño); `openbao/config.hcl` (comentario de TLS en `custody`); `instalar-en-servidor.md` (TLS por perfil).

**Paso 4 · W0-1.4 · DECISIONES y ADR**

- `DECISIONES.md` gana «Sprint 6 · decisiones de implementación» (la sección 1 de este plan) debajo del bloque S6-D39..D55.
- Rojo primero: `tests/architecture/test_adr_docs.py` pasa a exigir **exactamente siete** archivos (`ADR-006-firma-de-la-cadena-de-auditoria.md`, `ADR-007-adjuntos-y-foto-sin-auditoria-por-vista.md`) en los cuatro sitios donde hoy dice «cinco» (E9): el docstring, la tupla `ARCHIVOS`, los mensajes de las aserciones y la comprobación de `docs/adr/README.md` → 2 fallos; luego Verde: los dos ADR (seis secciones, frase de detenerse y preguntar, «Cómo se verifica» cita `tests/architecture/test_adr_docs.py` y `tests/core/test_chain_hash_vector.py` hasta que A1 y C1 sumen las propias), `docs/adr/README.md` (siete archivos).
- ADR-006: payload `apex-audit-sig-v1`, bloque `signature-payload-vector` con `through_seq=1` y el hash de la fila (no `prev_hash`), qué prueba y qué no, Ed25519 único en v0.3 y el procedimiento futuro de rotación de la llave de firma (EP-26), verificación incremental antes de firmar (H-1). ADR-007: almacenamiento, cifrado por el bus, descarga auditada, por qué la foto no se audita por vista, foto sin cifrar en disco como dato personal (Ley 1581), S3 apagado, retención y supresión con dueño y fecha (D38, D76).

**Paso 5 · W0-1.5 · Dependencias y licencias**

- Sin dependencia de ejecución nueva (E1: la subida es cuerpo crudo; `python-multipart` no entra y `test_third_party_confinement.py` lo prohíbe por nombre). `cd api && uv add --optional s3 boto3 botocore` (grupo opcional `s3`, Apache-2.0; `s3transfer` Apache-2.0, `jmespath` MIT, `python-dateutil` BSD/Apache, `urllib3` MIT); `uv sync --extra s3` en desarrollo y en el job `api` de la CI (las pruebas del adaptador usan `Stubber`); la imagen `apex-api:local` **no** instala el extra (`Dockerfile` sin `--extra s3`; `test_api_image.sh` comprueba que `boto3` no importa dentro de la imagen).
- `bash scripts/ci/check-licenses-api.sh` (con y sin `--extra s3`) y `bash scripts/ci/test_licenses.sh` con casos de control nuevos: `oqs` y `liboqs-python` rechazados por nombre (decisión, no por licencia) y `python-telegram-bot` sigue rechazado.
- `scripts/ci/notice.sh` gana al bloque fijo: Caddy 2.11.3 (Apache-2.0, imagen oficial sin módulos) y `alpine:3.22` (MIT, solo `tls-smoke`); `boto3`, `botocore`, `s3transfer`, `jmespath` entran por `pip-licenses` (los del extra, marcados «opcional, grupo s3»). `NOTICE` se regenera dos veces sin diferencias (`cmp`). `uv.lock` entra en el checkpoint.
- `CLAUDE.md` «Licencias»: la lista de dependencias nuevas del sprint.

**Paso 6 · W0-1.6 · Gate y checkpoint**

1. `cd api && uv run ruff check tests/architecture/test_adr_docs.py && uv run ruff format --check tests/architecture/test_adr_docs.py`.
2. `bash scripts/ci/test_licenses.sh && bash scripts/ci/check-licenses-api.sh`.
3. `security-reviewer`: T-DOC y decisiones (que S6-D34 a D38 y D39 a D55 estén todas absorbidas; que ADR-006 y ADR-007 no prometan lo que v0.3 no entrega).
4. Sello: `bash scripts/workflow/slice-gate.sh architecture tests/architecture/test_adr_docs.py`.
5. `checkpoint-commit.sh "S6-W0-1 decisiones del Sprint 6, T-DOC, ADR-006 y ADR-007, grupo opcional s3, NOTICE con Caddy y alpine"`.

### S6-W0-5 · `Settings`, cubetas nuevas y entorno por servicio

- **Historias:** parte de US-145, US-146, US-147, US-148, US-150, US-153 (variables).
- **Cierra:** parte de C4 y C7 (`Settings`), bugs 7 (`STORAGE_PROVIDER`), 11 (`APEX_DOMAIN`) y 13 (`test_env_example`, catálogo) del impacto, D47, D57, D65 (campos), riesgo 7 del impacto.
- **Depende de:** W0-1. **Migración:** ninguna.

**Paso 7 · W0-5.1 · Rojo**

- `tests/core/test_config.py`: `STORAGE_PROVIDER` solo `local|s3` (por defecto `local`); `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` (`SecretStr`) y `S3_ENABLE_PRODUCTION` todo o nada con `s3`; `S3_ENDPOINT_URL` `https` salvo `ENV=dev`; `s3` con `ENV=production` sin `S3_ENABLE_PRODUCTION=true` → error que nombra la variable; `APEX_DOMAIN` opcional validado como `host[:puerto]` (D77, E12; `http://x`, espacios y `_` rechazados); tabla del puerto (D77): con puerto pasa solo si `ALLOW_DOMAIN_PORT=true`, host `*.localhost` y `APEX_TLS_ISSUER=internal` (en `dev` y en `production`); falla, nombrando la variable, con puerto y sin la bandera, con la bandera y host `apex.example.com`, con la bandera e `APEX_TLS_ISSUER` igual a un correo, y `ALLOW_DOMAIN_PORT=true` con `ENV=production` y host que no sea `*.localhost`; `ENV` sigue admitiendo solo `dev` y `production` (sin `staging`); las siete `USER_*` de D57 con sus valores por defecto; `NON_API_ENV_VARS` = claves de `.env.ops.example` que no son de `Settings` (suma `APEX_CADDY_IP`, `APEX_TLS_ISSUER`, `APEX_ACME_EMAIL`, `APEX_ACME_CA`, `APEX_HSTS_MAX_AGE`, `TLS_PORT`); `missing_secrets` con `s3` exige `S3_SECRET_ACCESS_KEY`.
- `tests/core/test_env_example.py`: lo no secreto (`STORAGE_PROVIDER`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_ENABLE_PRODUCTION`, `APEX_DOMAIN`, `ALLOW_DOMAIN_PORT`, las siete `USER_*`) en `.env.example`; `S3_SECRET_ACCESS_KEY` y las seis de Caddy en `.env.ops.example`; el comentario del catálogo dice 23 cubetas y 22 variables; sin claves repetidas.
- Un solo proceso del api (O4, D79): `scripts/ci/test_compose_config.sh` falla si `api` declara `command` con `--workers` o si algún servicio recibe `UVICORN_WORKERS` o `WEB_CONCURRENCY` (en `compose.yml` y `compose.dev.yml`); `scripts/ci/test_api_image.sh` falla si el `CMD` de `apex-api:local` lleva `--workers`; `tests/core/test_single_process.py` lee `api/Dockerfile` y exige `uvicorn` sin `--workers`.
- `tests/architecture/test_user_limits_catalog.py`: `USER_LIMITS` con las siete claves nuevas; `CLAVES_SIN_RUTA_TODAVIA = {attachments-upload, attachments-photo, attachments-download, attachments-download-hour, keys-rotate, keys-rotate-hour, cbom-export}` (patrón S5-D98).
- `tests/architecture/test_settings_no_secrets.py`: `S3_SECRET_ACCESS_KEY` enmascarada en `repr`; `test_no_sensitive_in_logs.py` y `tests/core/test_logging_redact.py`: `s3_secret_access_key` en `SENSITIVE_KEYS`.
- `scripts/ci/test_env_isolation.sh`: `S3_SECRET_ACCESS_KEY` solo en `api`; las de Caddy en ningún servicio existente (la aserción de `caddy` se activa en W0-4); ninguna en `web`, `db`, `backup`, `migrate`, `dbsetup`, `worker`.
- `.github/workflows/ci.yml`: el `sed` suma las siete `USER_*` (`attachments-upload` 1000, `attachments-photo` 60000, `attachments-download` 3000 y 20000, `keys-rotate` 300 y 1000, `cbom-export` 200) y el conteo pasa de 15 a 22 (se comprueba con `grep -c` en el Verde).

**Paso 8 · W0-5.2 · Verde.** `core/config.py` (campos, validadores, `ALLOW_DOMAIN_PORT`, `NON_API_ENV_VARS`), `scripts/ci/{test_compose_config,test_api_image}.sh` (D79), `core/ratelimit.py` (`USER_LIMITS` y los topes desde `Settings`), `core/logging.py`, `.env.example`, `.env.ops.example`, `compose.yml` (bloque `environment` del `api` con `STORAGE_PROVIDER`, `S3_*`, `APEX_DOMAIN`; `worker` y `tools` no reciben `APEX_DOMAIN` porque `validate_origins` solo corre en el api), `ci.yml`. El `.env` de desarrollo se amplía con las claves nuevas antes de levantar nada.

**Paso 9 · W0-5.3 · Documentación.** RUNBOOK §14 (variables nuevas y qué servicio las lee); `docs/operacion/adjuntos.md` y `tls.md` nacen con su sección de variables (el resto llega en C1 y W0-4); cuaderno.

**Paso 10 · W0-5.4 · Gate**

1. `slice-gate.sh core/ratelimit tests/architecture/test_user_limits_catalog.py tests/core/test_ratelimit.py`.
2. `slice-gate.sh core/logging tests/core/test_logging_redact.py`.
3. `bash scripts/ci/test_env_isolation.sh && bash scripts/ci/test_compose_config.sh`.
4. `security-reviewer` (S3 apagado por bandera, secretos por servicio).
5. Sello: `slice-gate.sh core/config tests/core/test_config.py tests/core/test_env_example.py tests/core/test_config_secrets.py`.

**Paso 11 · W0-5.5 · Docker, evidencia y checkpoint.** `$DC up -d --no-build --force-recreate api worker` con el `.env` nuevo (`extra="forbid"` satisfecho; `healthy`); `restart web`; `/health` 200. `checkpoint-commit.sh "S6-W0-5 Settings de adjuntos y S3 apagado, APEX_DOMAIN y siete USER_* para las cinco cubetas nuevas (23 cubetas, 22 variables)"`.

### S6-W0-2 · Nginx de adjuntos, subruta `custody/jwt` del volumen `keys` y ensayo desde cero

- **Historias:** parte de US-147 y US-148 (Nginx), deuda S5-D201.
- **Cierra:** parte de C4 (Nginx, borde 5.242.880/5.242.881, CSP `blob:`), bugs 9 (parte) y 14 del impacto, D23, D54, D56 (ensayo), D58, E10, E14, S3-D101 (413 JSON).
- **Depende de:** W0-5. **Migración:** ninguna.

**Paso 12 · W0-2.1 · Rojo de infraestructura y CLI**

- `scripts/ci/test_nginx_conf.sh`: un `location ~ ^/api/v1/members/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/attachments$` antes de `location /api/` con `client_max_body_size 6m`, `error_page 413 = @too_large`, `limit_req` como el resto, `include snippets/proxy-api.conf` e `include snippets/security-headers.conf`; `@too_large` responde `413` con `Content-Type: application/json` y el envelope `{"code":"file_too_large","message":…}`; el `client_max_body_size` del `server` baja a `64k` y `128k` sigue solo en `settings/privacy`; la CSP de `= /index.html` dice `img-src 'self' data: blob:` y nada más cambia; casos funcionales con Nginx real (contenedor `apex-web:local` con un upstream falso de la biblioteca estándar): 5.242.880 → pasa a upstream; 5.242.881 → pasa a upstream (el api decide); 6.300.000 → 413 JSON; 100 KB en `/api/v1/members` → 413 (E14: el script ya levanta Nginx real; se confirma en el Rojo).
- `scripts/ci/test_compose_config.sh`: `worker` monta `keys` con `volume.subpath: custody` en `/run/apex/keys/custody` solo lectura en `compose.yml`; `api` y `tools` montan el volumen entero; con `compose.openbao.yml` el `worker` no monta `keys` (ya); el `tmpfs /tmp` del `api` no cambia (sin spool de subida, D59); el tmpfs `/var/cache/nginx` de `web` lleva `size=64m` (E13: Nginx guarda ahí los cuerpos de hasta 6m con `proxy_request_buffering on`).
- `scripts/ci/test_check_key_files.sh` y `check-key-files.sh`: layout `custody/kek.bin`, `custody/sign-ed25519.key`, `jwt/*` con modos 600 y dueño 10001; el layout plano es error con el mensaje «corra `init-keys --migrate-layout`».
- `scripts/ci/test_deploy_script.sh`: `deploy.sh` ejecuta `tools init-keys --migrate-layout` antes de `up -d` (idempotente; con `docker` falso); casos (E3): volumen plano → migra y sigue; layout nuevo → «nada que migrar» y sigue; layout mixto o salida distinta de 0 → aborta con 2 sin `up` y nombra el volumen; versiones mínimas (E4, D78): `docker` falso que devuelve API 1.44 → 2 con el mensaje, 1.45 → sigue; Compose 2.25 → 2, 2.26 → sigue.
- `tests/cli/test_init_keys_layout.py`: `init-keys` crea `custody/` y `jwt/`; `--migrate-layout` mueve un directorio plano (los seis archivos) sin sobrescribir, deja modos 600, es idempotente (segunda corrida: «nada que migrar», 0), rechaza si ambos layouts tienen el mismo archivo (2); `tests/core/test_config.py`: rutas por defecto nuevas (`CRYPTO_LOCAL_KEK_PATH`, `CRYPTO_LOCAL_SIGNING_KEY_PATH`, las dos JWT); `tests/crypto/test_init_keys.py` y `tests/cli/test_init_keys_cli.py` se adaptan (`key_paths_in(dir)` con subcarpetas).
- `prod-smoke.sh`: comprueba el layout en `api`, `worker` (solo `custody` con proveedor local) y `tools`.

**Paso 13 · W0-2.2 · Verde de Nginx.** `infra/nginx/default.conf` (location de subida, `@too_large`, `64k`, CSP), `snippets/too-large.conf` si la respuesta JSON se reutiliza, `scripts/ci/fixtures/attachments/make_attachments.py`.

**Paso 14 · W0-2.3 · Verde del layout de llaves.** **Antes de tocar `core/config.py` o `local_provider.py`: `$DC stop api worker`** (E3: el api de desarrollo con `--reload` arrancaría con las rutas nuevas sobre un volumen plano y quedaría roto); siguen parados hasta el punto 3 de W0-2.6. `cli_ops/keys_layout.py` (nuevo: `migrate_layout(paths) -> LayoutReport`, bajo 150 líneas, D80), `cli.py` (`init-keys --migrate-layout` despacha a ese módulo; `cli.py` sigue bajo 700), `cli_ops/keys.py` (`key_paths_in` con `custody/` y `jwt/`), `core/crypto/local_provider.py` y `core/config.py` (rutas por defecto), `compose.yml` (`subpath`), `compose.dev.yml` (los binds de `keys` de desarrollo con el mismo layout), `infra/deploy.sh` (chequeo de versiones de D78; `--migrate-layout`; caso del layout plano), `scripts/ci/check-key-files.sh`, `prod-smoke.sh` (imprime las versiones), `scripts/ci/fakes/docker`.

**Paso 15 · W0-2.4 · Documentación.** RUNBOOK §12 (migrar el layout en un servidor existente: `tools init-keys --migrate-layout` con el stack parado; `deploy.sh` lo hace solo; versiones mínimas Docker Engine 26 / API 1.45 y Compose 2.26, D78) y §14; `docs/operacion/actualizar.md` e `instalar-en-servidor.md`; `infra/README.md`; cuaderno.

**Paso 16 · W0-2.5 · Gate**

1. `bash scripts/ci/test_nginx_conf.sh && bash scripts/ci/test_compose_config.sh && bash scripts/ci/test_check_key_files.sh && bash scripts/ci/test_deploy_script.sh && bash scripts/workflow/tests/run.sh`.
2. `slice-gate.sh cli tests/cli/test_init_keys_layout.py tests/cli/test_init_keys_cli.py`.
3. `slice-gate.sh crypto tests/crypto/test_init_keys.py tests/crypto/test_local_provider.py`.
4. `security-reviewer` de W0-2 (regex anclado, `@too_large` sin eco del cuerpo, modos del layout, nada del JWT visible al worker).
5. Sello: `bash scripts/workflow/wave0-gate.sh W0-2 tests/cli/test_init_keys_layout.py tests/core/test_config.py tests/core/test_env_example.py`.

**Paso 17 · W0-2.6 · Docker de desarrollo**

1. Buildx de `apex-api:local` y `apex-web:local` (`GIT_SHA` del HEAD del Verde).
2. `api` y `worker` siguen parados desde W0-2.3 (E3; se comprueba con `$DC ps`); respaldo del volumen de desarrollo: `docker run --rm -v apex_keys:/k:ro -v "$PWD/docs/scratch:/out" alpine tar czf /out/keys-dev-antes-layout.tgz -C /k .` (ignorado; se borra en V12); `$DC run --rm --no-deps tools init-keys --migrate-layout` → seis archivos movidos; segunda corrida → «nada que migrar».
3. `$DC up -d --no-build --force-recreate api worker web` → `healthy`; `restart web`; `/health` ok; login en 8181 (JWT desde `jwt/`); `GET /members/{id}` descifra (KEK desde `custody/`).
4. Nginx: desde el host, `curl -sS -o /dev/null -w '%{http_code}\n' --data-binary @<foto-5242880.jpg> -H 'Content-Type: image/jpeg' http://127.0.0.1:8180/api/v1/members/<uuid>/attachments` → 404 o 405 del api (pasó Nginx), 5.242.881 → igual, 6.300.000 → 413 con JSON; `curl -sI http://127.0.0.1:8180/` → CSP con `blob:`.

**Paso 18 · W0-2.7 · Ensayo de producción desde cero (S6-D56)**

1. `docker compose ls` (sin `apex-ensayo`); `docs/scratch/ensayo/{.env,.env.ops}` desde los ejemplos (8280, `172.31.2.0/24`, `custody` `172.31.12.0/24`, `TLS_PORT=8443`, `CRYPTO_PROVIDER=local` al principio, `ALLOW_INSECURE_COOKIE=true`, `MIGRATE_DB_USER`/`TOOLS_DB_USER=apex_owner`), `.env.seed` del ensayo.
2. `$DCE up -d db`; `$DCE run --rm --no-deps tools init-keys` (layout nuevo); `$DCE up -d` → `migrate` como `apex_owner` (`0001` a `0020`), `dbsetup` («20 tablas clasificadas»), api, worker, web, backup y openbao `healthy`.
3. P-BAO: `--first-install` por pty en el auxiliar `docker:cli` → llaves a `docs/scratch/ensayo/openbao/init.txt` (600); desellar con 3 por `wget --post-file`; `bao status` desellado, 5/3; `seed` (admin del ensayo).
4. Custodia H-1 (S5-D72): `export-kek` y `verify-kek-backup` por pty; `$DCE -f infra/compose.verify.yml run --rm backup /opt/backup/run.sh` → manifiesto firmado con `openbao_snapshot.verified = true`.
5. `migrate-provider --dry-run` (8) → `MIGRAR` → `hecho=8/8` → `--verify` 0 → repetición «nada que migrar»; `.env` del ensayo a `CRYPTO_PROVIDER=openbao`; `$DCEB up -d --no-build --force-recreate api worker` + `restart web`; `retire-local-kek` con `RETIRAR`; `test ! -e /run/apex/keys/custody/kek.bin` en api (el worker ya no monta `keys`); `SELECT provider, count(*) FROM crypto.crypto_keys GROUP BY 1` → 8 `openbao`.
6. `OPS_ENV_FILE=docs/scratch/ensayo/.env.ops DB_OWNER_MODE=nueva DC="$DCE" bash scripts/ci/test_db_roles.sh` → 0 fallas; `/health` en 8280 `ok` con `crypto: ok`; `docker stats --no-stream`.
7. Smoke de producción en Linux (gate): `prod-smoke.sh --no-build --provider openbao` en `apex-smoke` desde el auxiliar; verde; `down -v` del smoke; re-etiquetar `apex-*:local` si el smoke las repuntó.

**Paso 19 · W0-2.8 · Checkpoint.** `"S6-W0-2 Nginx 6m solo en la subida con 413 JSON y CSP blob:, subruta custody/jwt del volumen keys con init-keys --migrate-layout (S5-D201) y ensayo apex-ensayo desde cero con OpenBao"`, seguido del commit de evidencia.

### S6-W0-3 · OpenBao: políticas de firma y verificación, tokens y smoke

- **Historias:** US-141 (criterio 6), parte de US-140.
- **Cierra:** C2 (políticas), bugs 2 (políticas) y 4 (exploración) del impacto, D6, D41, M-2 c, L-6 (parte), E4 de la exploración.
- **Depende de:** W0-2. **Migración:** ninguna.

**Paso 20 · W0-3.1 · Rojo de infraestructura**

- `scripts/ci/test_openbao_infra.sh`: `apex-worker.hcl` suma exactamente `transit/sign/apex-sign-audit` y `transit/verify/apex-sign-audit` con `update`; `apex-api.hcl` suma solo `transit/verify/apex-sign-audit`; `apex-tools.hcl` suma `transit/sign/apex-sign-audit`, `transit/verify/apex-sign-audit` y `transit/keys/apex-sign-audit` con `read`; ninguna concede `rotate`, `config`, `delete`, `trim` ni `export` de esa llave (M-2c); `bootstrap.sh` sin `ml-dsa` (grep negativo; D51) y con `apex-sign-audit` `ed25519` no exportable (ya); `--reissue-tokens` reaplica las cuatro políticas antes de reemitir; todos los servicios de `custody` con `cap_drop: [ALL]` (L-6).
- `scripts/ci/openbao-smoke.sh` gana cuatro pasos: firmar con el token del worker (`bao write transit/sign/apex-sign-audit input=<b64>` desde `exec openbao` con el token leído del volumen por el propio script, sin imprimirlo) → 200; verificar con el token del api → `valid: true`; firmar con el token del api → 403; rotar la llave de firma con el token de `tools` → 403.
- `.github/workflows/ci.yml`: la política del token `apex-ci` suma `transit/sign/*` y `transit/verify/*` (S5-D264; `-m openbao` exige 0 saltos en A1).

**Paso 21 · W0-3.2 · Verde.** `infra/openbao/policies/{apex-api,apex-worker,apex-tools}.hcl`, `bootstrap.sh` (comentario de `--reissue-tokens`; sin sonda), `scripts/ci/openbao-smoke.sh`, `ci.yml`, `compose.yml` (`cap_drop` completo en `custody`).

**Paso 22 · W0-3.3 · Documentación.** `docs/operacion/openbao.md` §6 (reaplicar políticas y reemitir tokens en una instalación existente: `--reissue-tokens` tras desellar, `restart api worker`; v0.3 añade sign y verify) y §9 (qué puede cada token en v0.3); RUNBOOK §13; cuaderno.

**Paso 23 · W0-3.4 · Gate**

1. `bash scripts/ci/test_openbao_infra.sh && bash scripts/ci/test_infra_scripts.sh && bash scripts/ci/test_compose_config.sh`.
2. `security-reviewer` de W0-3 (el api no firma; `*` solo dentro de `apex-sign-audit`; `cap_drop`).
3. Sello: `bash scripts/workflow/wave0-gate.sh W0-3`.

**Paso 24 · W0-3.5 · Docker y evidencia**

1. Desarrollo: `$DC --profile openbao up -d openbao` (el `dev-entrypoint` reaplica políticas); `$DC exec -T openbao bao policy read apex-worker | grep -c sign` ≥ 1; `$DC --profile openbao stop openbao`.
2. Ensayo: `$DCE --profile bootstrap run --rm -T openbao-bootstrap --reissue-tokens` (desellado antes) → cuatro tokens nuevos; `$DCEB restart api worker` + `restart web`; `/health` `crypto: ok`.
3. `bash scripts/ci/openbao-smoke.sh` en `apex-smoke` desde el auxiliar Linux → verde con los cuatro pasos nuevos; `down -v` del smoke.

**Paso 25 · W0-3.6 · Checkpoint.** `"S6-W0-3 políticas de Transit por servicio: el worker firma, el api solo verifica, tools firma y verifica con --as; tokens reemitidos y openbao-smoke con 403 del api al firmar"`.

### S6-W0-4 · Caddy, perfil `tls`, `real_ip`, HSTS escalonado y `tls-smoke.sh`

- **Historias:** US-152 completa; US-153 criterios 1, 2, 3, 6 y 8 (la cookie y CORS llegan en E1).
- **Cierra:** C7 (infra TLS), bugs 9 (`proxy-api.conf`), 10 y 17 del impacto, D27, D29, D30, D48, D63, D64, M-7 (a..e), M-8, L-6 (`cap_drop` en `default`), E10, E11, riesgo 4 del impacto (limitador detrás de Caddy).
- **Depende de:** W0-3. **Migración:** ninguna.

**Paso 26 · W0-4.1 · Verificaciones previas (E10, E11, M-7c)**, en contenedores desechables y al cuaderno: `caddy validate` del `Caddyfile` real con las variables de entorno del ensayo; `caddy` publica 80/443 con `cap_drop ALL` + `NET_BIND_SERVICE` (si la imagen necesita más, se anota con decisión del slice); el bind de un solo archivo `${APEX_REAL_IP_CONF:-./nginx/snippets/real-ip.conf}:/etc/nginx/snippets/real-ip.conf:ro` gana al horneado y Nginx lo incluye, con la variable apuntando a un archivo fuera del árbol (O5, E11, D82; `web` sigue `read_only` sin `envsubst`); `caddy` con `/_caddy_health` responde 200 por HTTP, `/login` 308 y `/.well-known/acme-challenge/x` **no** 308 (E8, M1); la imagen de Postgres de `db` arranca con `cap_drop ALL` más `CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID` (E9); `ports: !override []` renderiza; `alpine:3.22` con `openssl` fijado negocia `X25519MLKEM768` contra un Caddy desechable con `tls internal`.

**Paso 27 · W0-4.2 · Rojo de infraestructura**

- `scripts/ci/test_compose_config.sh`: servicio `caddy` con `profiles: ["tls"]`, imagen por digest, `read_only`, `cap_drop: [ALL]`, `cap_add: [NET_BIND_SERVICE]`, `no-new-privileges`, `ipv4_address ${APEX_CADDY_IP:-172.30.0.11}` fuera del `ip_range`, volúmenes `caddy_data`, `caddy_config` y `./caddy/Caddyfile:ro`, `depends_on: web: service_healthy`, `environment` solo `APEX_DOMAIN`, `APEX_TLS_ISSUER`, `APEX_ACME_EMAIL`, `APEX_ACME_CA`, `APEX_HSTS_MAX_AGE`, sin puerto 2019; `compose.tls.yml`: `caddy` con `ports` 80 y 443 y `web` con `ports: !override []`; sin el overlay `caddy` no existe y `web` publica `${WEB_PORT:-80}:80`; `compose.dev.yml`: `caddy` bajo perfil `tls` con `APEX_DOMAIN=apex.localhost:8443`, `APEX_TLS_ISSUER=internal`, `127.0.0.1:8443:443` (y `web` conserva 8180); la lista literal de volúmenes suma `caddy_data` y `caddy_config`; `cap_drop: [ALL]` en los once servicios (E9, M2; contrastado con `grep -n cap_drop infra/compose.yml` en HEAD: lo tienen `api`, `backup`, `dbsetup`, `migrate`, `openbao-bootstrap`, `openbao`, `tools`, `web` y `worker`; no lo tiene `db`, que lo gana con `CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID`; `caddy` nace con `NET_BIND_SERVICE`; ninguno con `NET_RAW`); `web` monta `${APEX_REAL_IP_CONF:-./nginx/snippets/real-ip.conf}:/etc/nginx/snippets/real-ip.conf:ro` (D82) y su tmpfs `/var/cache/nginx` lleva `size=64m` (E13); `api` sin `command` con `--workers` y sin `UVICORN_WORKERS` (D79, ya desde W0-5).
- `scripts/ci/test_images_pinned.sh`: `caddy` y `alpine` (en `tls-smoke.sh`) por digest con fecha.
- `scripts/ci/test_nginx_conf.sh`: `real_ip` (`set_real_ip_from` con `/32`, `real_ip_header X-Forwarded-For`, `real_ip_recursive off`) declarado en el contexto `server` antes de los `limit_req` de `auth-zone` y `health-zone`; `map $realip_remote_addr $apex_proto` con el valor `https` solo para la IP de Caddy y `$http_x_forwarded_proto` igual a `https`, `http` por defecto; `proxy-api.conf` con `X-Forwarded-Proto $apex_proto` y `X-Forwarded-For $remote_addr` (sin cambio: `remote_addr` ya es el real tras `real_ip`); HSTS ausente en todo `infra/nginx/`; funcional con Nginx real: una petición desde la IP de Caddy con `X-Forwarded-For: 203.0.113.9` llega al upstream con `X-Forwarded-For: 203.0.113.9`; la misma desde otra IP llega con la IP del par y `X-Forwarded-Proto: http`.
- `infra/caddy/tests/test_caddyfile.sh`: `admin off`; `curves x25519mlkem768 x25519`; `protocols tls1.2 tls1.3`; `Strict-Transport-Security` con `{$APEX_HSTS_MAX_AGE:300}` y sin `includeSubDomains` ni `preload`; `reverse_proxy web:80`; sin `trusted_proxies`; `acme_ca` por variable con el valor de producción por defecto; `tls {$APEX_TLS_ISSUER}`; (E8) el sitio `http://` trae `handle /_caddy_health { respond "ok" 200 }` antes del `redir … 308`, el sitio HTTPS no expone `/_caddy_health`, y el healthcheck de `compose.yml` apunta a esa ruta; con `caddy validate` en la imagen fijada, el `Caddyfile` renderizado con las variables del ensayo valida.
- `scripts/ci/test_nginx_conf.sh` (O5): `snippets/real-ip.conf` versionado es igual a `real-ip.conf.in` con `__APEX_CADDY_IP__` sustituido por `172.30.0.11`; `default.conf` lo incluye en el contexto `server`; `scripts/ci/test_deploy_script.sh` (E11, D82): con `APEX_CADDY_IP=172.31.2.11`, `deploy.sh` escribe `${DEPLOY_STATE_DIR}/real-ip.conf` renderizado, pasa `APEX_REAL_IP_CONF` al `up` y `git status --porcelain` del árbol queda vacío (los chequeos de `deploy.sh:101,218` pasan); con la IP por defecto no escribe nada ni exporta la variable; nunca toca `infra/nginx/`.
- `scripts/ci/test_deploy_script.sh`: con `DEPLOY_COMPOSE_EXTRA` que contiene `--profile tls`, la sonda usa `exec web wget`, exige `caddy` `healthy` y el aviso final lo dice; las variables prohibidas de `caddy` (todo salvo las cinco) y de `web` (`APEX_TLS_*`); `prod-smoke.sh --tls` y `compose-smoke.sh` aceptan el perfil (sonda interna).
- `scripts/ci/test_env_isolation.sh`: las de Caddy solo en `caddy`; `APEX_CADDY_IP` en `web` y `caddy`.
- `scripts/ci/test_infra_scripts.sh`: `bash -n` de `tls-smoke.sh`; `tls-smoke.sh --dry-run` renderiza las dos configuraciones y lista las comprobaciones.
- `scripts/workflow/tests/test_wave0_gate.sh` y `test_run_gates.sh`: las dos combinaciones nuevas.

**Paso 28 · W0-4.3 · Verde de Caddy y Compose.** `infra/caddy/Caddyfile` (D64), `infra/compose.yml` (servicio `caddy`, volúmenes, `cap_drop` en todos, `APEX_CADDY_IP` en `web`), `infra/compose.tls.yml` (nuevo), `infra/compose.dev.yml` (perfil `tls`), `.env.ops.example` (`APEX_CADDY_IP`, `APEX_TLS_ISSUER=<correo ACME>`, `APEX_ACME_EMAIL`, `APEX_ACME_CA`, `APEX_HSTS_MAX_AGE=300`, `TLS_PORT=443`); `NON_API_ENV_VARS` ya en W0-5 (se verifica).

**Paso 29 · W0-4.4 · Verde de Nginx, scripts y CI.** `infra/nginx/default.conf` y `snippets/proxy-api.conf`; `infra/nginx/snippets/real-ip.conf.in` y `real-ip.conf` (renderizado por defecto; O5); `infra/deploy.sh` (render a `${DEPLOY_STATE_DIR}/real-ip.conf` y `APEX_REAL_IP_CONF`, D82); `.env.ops.example` (`APEX_REAL_IP_CONF`); `scripts/ci/{prod-smoke,compose-smoke}.sh`; `scripts/ci/tls-smoke.sh` (P-TLS, con `--dry-run` y `--lan`); `scripts/workflow/{wave0-gate,run-gates}.sh`; `.github/workflows/ci.yml` (job `tls-smoke` dentro de `images`: `docker pull` de Caddy y alpine por digest, `tls-smoke.sh` con el stack de CI y el modo LAN).

**Paso 30 · W0-4.5 · Documentación.** `docs/operacion/tls.md` (LAN → dominio: `APEX_DOMAIN`, `APEX_TLS_ISSUER` con el correo, `FRONT_BASE_URL=https://…`, `COOKIE_SECURE=true`, `ALLOW_INSECURE_COOKIE=false`, `DEPLOY_COMPOSE_EXTRA="-f infra/compose.tls.yml --profile tls"`, reenvío de 80 y 443; vuelta atrás; staging con `APEX_ACME_CA`; el ACME HTTP-01 real con dominio es un paso humano explícito (M1: el flujo solo prueba con CA interna que `/.well-known/acme-challenge/*` no redirige); `APEX_REAL_IP_CONF` y dónde queda el snippet renderizado (D82); HSTS escalonado 300 s → 604800 → 31536000 y por qué un error de certificado deja el panel inaccesible sin bypass; monitores externos que ven 308; SSL Labs como evidencia humana; TLS en `custody` como residual v0.4 del operador), `instalar-en-servidor.md`, `actualizar.md`, `infra/README.md`, RUNBOOK §14; cuaderno.

**Paso 31 · W0-4.6 · Gate**

1. `bash scripts/ci/test_compose_config.sh && bash scripts/ci/test_images_pinned.sh && bash scripts/ci/test_nginx_conf.sh && bash scripts/ci/test_deploy_script.sh && bash scripts/ci/test_env_isolation.sh && bash infra/caddy/tests/test_caddyfile.sh && bash scripts/ci/test_infra_scripts.sh && bash scripts/workflow/tests/run.sh`.
2. `slice-gate.sh core/config tests/core/test_config.py tests/core/test_env_example.py`.
3. `security-reviewer` de W0-4 (M-7 a..e, M-8, L-6, `admin off`, nada publicado salvo 80 y 443, CA interna solo en smoke y desarrollo).
4. Sello: `bash scripts/workflow/wave0-gate.sh W0-4 tests/core/test_env_example.py`.

**Paso 32 · W0-4.7 · Docker y evidencia (demo 4, parte de infraestructura)**

1. `docker pull` de Caddy y alpine por digest; buildx de `apex-web:local` (cambió `default.conf`).
2. Desarrollo: `$DC up -d --no-build --force-recreate web` + `$DC --profile tls up -d caddy`; `curl -sk https://127.0.0.1:8443/api/v1/health` 200; `curl -sI http://127.0.0.1:8180/` sin HSTS; `$DC --profile tls stop caddy`.
3. Ensayo: `.env.ops` con `APEX_DOMAIN=apex.localhost:8443`, `APEX_TLS_ISSUER=internal`; `$DCET up -d --no-build --force-recreate web caddy` → `web` sin puerto publicado (`curl http://127.0.0.1:8280` falla) y `caddy` `healthy`; `bash scripts/ci/tls-smoke.sh --dc "$DCET"` → todas las comprobaciones de P-TLS menos la cookie (E1); `bash scripts/ci/tls-smoke.sh --dc "$DCEB" --lan` → sin HSTS, 8280 por HTTP; se deja el ensayo en modo LAN (`$DCET stop caddy`, `$DCEB up -d --no-build --force-recreate web`).
4. Smoke de producción en Linux: `prod-smoke.sh --no-build --provider openbao --tls` en `apex-smoke` desde el auxiliar → verde; `down -v`; re-etiquetar imágenes.
5. `docker stats --no-stream` al cuaderno.

**Paso 33 · W0-4.8 · Checkpoint.** `"S6-W0-4 Caddy 2.11.3 con perfil tls e intercambio X25519MLKEM768, compose.tls.yml sin puerto 80 en web, real_ip y map de protocolo en Nginx, HSTS escalonado, cap_drop ALL en todos los servicios y tls-smoke.sh con CA interna"`, seguido del commit de evidencia.

## 5. Backend

### S6-A1 · `audit.signatures` (`0021`), `core/audit_sign.py` y bus con algoritmo real (US-140)

- **Cierra:** parte de C2 (tabla, bus, `sign_key_ref`, grants), H-1 (verificación incremental antes de firmar), M-2 b y e, bugs 1 (`SIGN_ALG_V01`), 2 (`signing_specs`, `bootstrap`), 3 (`core/audit.py`) y 6 (grants) de la exploración, D3, D4, D7, D34, D40 (fila `sign`), D72, E2, E3.
- **Depende de:** W0-4. **Migración:** `0021_audit_signatures`.

**Paso 34 · A1.1 · P-MIG, verificación y stubs**

- P-MIG pasos 1 y 2: volcado `sprint-06-antes-0021.dump` y `$DC stop api worker`.
- E2 y E3 por `grep -rn "SIGN_ALG_V01\|SIGNING_KEY_REF\|_ALGORITHM\[\|signing_specs\|LoadedKey(\|KeyInfo(" api/src`; la lista va al cuaderno.
- Stubs: `core/audit_sign.py` (`AuditSignature` (modelo, `__tablename__ = "signatures"`, esquema `audit`, no `__audited__`), `AUDIT_SIGN_LOCK_KEY = 4_270_004`, `signature_payload(through_seq, chain_hash, *, version=1) -> bytes`, `needs_signature(last_seq, last_signed_seq) -> bool`, `is_signature_late(last_signed_at, last_seq, last_signed_seq, first_unsigned_at, now, threshold_h=48) -> bool`, `SegmentCheck(ok, from_seq, to_seq, broken_at_seq)`, `async check_unsigned_segment(session, *, from_seq, to_seq, anchor_hash) -> SegmentCheck`, `SignOutcome(kind: Literal["signed","nothing_new","chain_broken"], through_seq, signature_id)`, `async sign_latest(session, *, by=SYSTEM_USER_ID) -> SignOutcome`, `async latest_signature(session) -> AuditSignature | None`); `core/crypto/registry.py` (`audit.signature`: `encrypt=False`, `index_kind=None`, `sign=True`, `columns=()`); `keyring.LoadedKey.algorithm`; `provider.KeyProvider.sign_key_ref() -> str` (local: `local:sign-ed25519`; OpenBao: `apex-sign-audit`) y `sign_public_key() -> str` (base64 de los 32 bytes; local: derivada del archivo de `custody/`; OpenBao: `keys.<versión>.public_key` de `key_info`; D81); `openbao_wire.KeyInfo.algorithm` y `KeyInfo.public_key` (`ed25519 → Ed25519`; otro → `CryptoError("unsupported")`); `core/crypto/models.CryptoKey.public_key` y `keyring.LoadedKey.public_key`; `core/crypto/signature.verify_ed25519(public_key, data, signature) -> bool` (`cryptography`, dentro de `core/crypto`); `bus.verify` deja de llamar al proveedor y verifica con `llave.public_key` (D62); `bus.sign` formatea con `llave.algorithm`; `bootstrap._create_missing` nunca crea `purpose = "sign"` (D72); `migrations/env.py` importa `AuditSignature`; `tests/factories/signatures.py`; `LIMPIAR_SIGNATURES` en `tests/conftest.py`.

**Paso 35 · A1.2 · Rojo de arquitectura**

- `test_core_import_direction.py`: `core/audit_sign.py` importa `core.audit` y `core.crypto.bus` y nada de `app.modules` ni `core.jobs`; nada de `core/crypto/` importa `core.audit*` (sigue); `core/audit.py` sigue importando solo `core/crypto/digest`.
- `test_sql_literals_constant.py`: cuarta llave `4_270_004` por igualdad.
- `test_audited_tables.py`: `audit.signatures` en `EXCLUIDAS` con motivo («auditaría la auditoría»); `test_las_excluidas_no_declaran_audited`.
- `test_no_trigger_tampering.py` y `tests/migrations/test_triggers_siempre_activos.py`: `signatures_forbid_mutation` y `signatures_forbid_truncate` en `A`.
- `test_adr_docs.py`: ADR-006 cita `tests/core/test_signature_payload_vector.py` (existe desde este slice).
- `tests/migrations/test_db_grants.py`: `audit.signatures` clasificada; `apex_api` `S`; `apex_worker` `S I`; `apex_backup` como `verifications`.
- `test_crypto_bus_importers.py`: `core/audit_sign.py` entra en los importadores reales del bus (lista por igualdad).

**Paso 36 · A1.3 · Rojo**

- `tests/migrations/test_0021_audit_signatures.py`: columnas y tipos de D7; `crypto.crypto_keys.public_key` nula de texto con CHECK `(purpose <> 'sign') OR (public_key IS NOT NULL)` (insertar `sign` sin clave pública falla; `encrypt` con clave pública nula pasa); las ocho filas existentes de `apex-db-1` y de `db_test` quedan intactas; `apex_api` y `apex_worker` no tienen `UPDATE` sobre `public_key`; el `downgrade` quita la columna y el CHECK; CHECK de `hash` (64 hex minúsculos), `algorithm IN ('Ed25519','ML-DSA-65')`, `payload_version >= 1`; índice único `through_seq`; índice `signed_at DESC`; triggers `BEFORE UPDATE OR DELETE` y `BEFORE TRUNCATE` con `ENABLE ALWAYS`; `downgrade` borra triggers, función y tabla; ciclo `head → base → head`; sobre `apex_roles`: `apex_worker` inserta y no puede actualizar ni borrar; `apex_api` lee y no inserta; `test_0020_notifications_indexes.py` pasa a «en la cadena de head».
- `tests/core/test_signature_payload_vector.py`: lee el bloque `signature-payload-vector` de ADR-006 y compara bytes (`through_seq=1`, hash de la fila); `tests/core/test_audit_sign_pure.py`: `signature_payload` byte a byte (`b"apex-audit-sig-v1\n1\n<64 hex>"`), `CanonicalError` con `through_seq` 0 o negativo, hash de 63 caracteres, mayúsculas, `version` 0; `needs_signature`; `is_signature_late` tabla completa (sin filas nuevas → falso; nunca firmada y `first_unsigned_at` 49 h → verdadero; 47 h → falso; gimnasio sin actividad → falso).
- `tests/audit/test_sign_latest.py`: firma la última fila y deja `crypto_ops(sign)` con `data_class = audit.signature` y `key_id`; `nothing_new` sin fila nueva (no firma dos veces el mismo `through_seq`); **H-1:** `alterar_fila` entre dos firmas (triggers apagados) → `chain_broken`, ninguna fila nueva, `broken_at_seq`; ancla que no coincide (`borrar_firma` y reescribir) → `chain_broken`; `check_unsigned_segment` recalcula con el serializador canónico (`core.audit.chain_hash`) sin tocar `core/audit.py`; concurrencia con `dos_sesiones` bajo `pg_advisory_xact_lock(4_270_004)` → una sola fila; `by` queda en `created_by`; el primer firmado de una base sin firmas recorre desde `seq = 1`.
- `tests/crypto/test_sign_algorithm.py` (parametrizado `local`, `fake_transit`, `openbao_real` con el marcador `openbao`): `bus.sign("audit.signature", payload)` etiqueta con `llave.algorithm`; la fila `sign` `local` lleva `local:sign-ed25519` y la `openbao` lleva `apex-sign-audit` (referencia, no material, S5-D183); una referencia que no cumpla `^apex-sign-audit[a-z0-9-]*$` o `local:sign-ed25519` → `CryptoError("bad_key_ref")` (M-2b); `bus.verify` acepta llaves `decrypt_only` y `retired` por `key_id`; `KeyInfo.algorithm` y `KeyInfo.public_key`; `bus.verify` verifica con `public_key` de la fila y **no** llama a `provider.verify` (contador del `FakeTransit` en 0; con `custodio_sellado` verifica igual; D62, D81); `verify_ed25519` con clave pública ajena → falso; con `algorithm = ML-DSA-65` → `unsupported`; `sign_public_key()` de `local` coincide con la derivada del archivo y la de `fake_transit` con `key_info`; `ensure_keys` del api no crea filas `sign` aunque el registro tenga la clase (D72); `Keyring.load_all(classes={"audit.signature"})` no hace `unwrap`; dos filas `active` de `(sign, audit.signature)` violan el índice único parcial (M-2e); `test_sign.py` y `test_signature_format.py` existentes se adaptan al algoritmo por fila.
- `tests/crypto/test_bootstrap.py`: sin filas `sign` creadas por `ensure_keys`; `tests/crypto/test_provider_contract.py`: `sign_key_ref()` por proveedor.

**Paso 37 · A1.4 · Verde de `0021`.** P-MIG pasos 3 a 8 (`\d audit.signatures`; consulta de `tgenabled`); `grants.sql` (matriz, `-- clasificada:`, `ARRAY`), `revoke.sql`, `test_db_grants.py` (P-ROL).

**Paso 38 · A1.5 · Verde de código.** `core/audit_sign.py` (< 400 líneas; funciones < 50), `registry.py`, `keyring.py`, `bus.py` (`SIGN_ALG_V01` desaparece; `verify` con clave pública), `signature.py` (`verify_ed25519`), `models.py` (`public_key`), `bootstrap.py` (`public_key` lo rellena quien crea la fila `sign`: `init-keys --data-class audit.signature` y el bootstrap, leyendo la clave pública del proveedor; hoy no existe ninguna fila `sign`, y si una instalación la tuviera sin clave pública, `init-keys --data-class audit.signature` la completa de forma idempotente y lo audita), `provider.py` (`sign_public_key`), `local_provider.py`, `openbao_provider.py`, `openbao_wire.py`, `tests/factories/fake_transit.py`, `migrations/env.py`, `tests/conftest.py`.

**Paso 39 · A1.6 · Documentación.** ADR-006 cita `tests/core/test_signature_payload_vector.py`, `tests/core/test_audit_sign_pure.py` y `tests/audit/test_sign_latest.py`; `docs/operacion/openbao.md` (la fila `sign` y su referencia); RUNBOOK §6 (rollback de `0021`) y §14; bloque A1 en DECISIONES; cuaderno.

**Paso 40 · A1.7 · Gate**

1. `slice-gate.sh architecture tests/architecture/test_core_import_direction.py tests/architecture/test_sql_literals_constant.py tests/architecture/test_audited_tables.py tests/architecture/test_no_trigger_tampering.py tests/architecture/test_adr_docs.py tests/architecture/test_crypto_bus_importers.py`.
2. `slice-gate.sh crypto tests/crypto/test_sign_algorithm.py tests/crypto/test_sign.py tests/crypto/test_signature_format.py tests/crypto/test_bootstrap.py tests/crypto/test_provider_contract.py tests/crypto/test_provider_per_row.py`.
3. `slice-gate.sh audit tests/audit/test_sign_latest.py`.
4. `database-reviewer` (`0021`, grants, índices) y `security-reviewer` (H-1, M-2 b/e, referencias fuera de las respuestas), en paralelo.
5. Sello: `slice-gate.sh core/audit_sign tests/core/test_signature_payload_vector.py tests/core/test_audit_sign_pure.py tests/audit/test_sign_latest.py tests/migrations/test_0021_audit_signatures.py tests/migrations/test_0020_notifications_indexes.py tests/migrations/test_db_grants.py tests/migrations/test_triggers_siempre_activos.py`.

**Paso 41 · A1.8 · Docker y evidencia**

1. P-MIG pasos 6 y 7 ya hechos en el Verde; buildx de `apex-api:local`; `$DC up -d --no-build --force-recreate api worker` + `restart web`.
2. Ensayo: `$DCEB stop worker`; `$DCE run --rm migrate` → `0020 -> 0021`; `dbsetup` → «21 tablas clasificadas»; `test_db_roles.sh` → 0 fallas; `$DCEB up -d --no-build --force-recreate api worker` + `restart web`; `\d audit.signatures` igual que en desarrollo.
3. OpenBao real en el auxiliar Linux (`apex_custody`, `OPENBAO_TEST_ADDR`, token de desarrollo con la política ampliada): `uv run pytest -m openbao tests/crypto -q` → 0 saltos (firma y verificación reales con `apex-sign-audit`).

**Paso 42 · A1.9 · Checkpoint.** `"S6-A1 audit.signatures (0021) append-only, core/audit_sign con payload apex-audit-sig-v1 y verificación incremental antes de firmar (H-1), bus con algoritmo real por fila y sign_key_ref por proveedor"`.

### S6-A2 · Job `sign_audit`, CLI de firma, alertas y keyring por job (US-141)

- **Cierra:** parte de C2 (job, CLI, alertas), M-2 a y d, L-4, bugs 5 (worker) y 20 (alertas, `test_schedule`) de la exploración, D8, D9, D11, D42, D60, D69, E4, E13.
- **Depende de:** A1. **Migración:** ninguna.

**Paso 43 · A2.1 · Stubs (con el worker detenido).** `worker/jobs/sign_audit.py` (`NAME = "sign_audit"`, `CRYPTO_CLASSES = frozenset({"audit.signature"})`, `RETRY_WAITS_S = (2, 4, 8)`, `async run(ctx) -> JobResult`); `worker/registry.JobSpec.crypto_classes: frozenset[str] = frozenset()`; `worker/jobs/__init__.py` (`JOBS`: `expirations`, `notify`, `sign_audit` con `timeout_s=300`, `backup_check`); `worker/runtime.worker_crypto_classes()` (unión de `JobSpec.crypto_classes`) y, por O11, desaparecen `runtime.WORKER_CRYPTO_CLASSES` (líneas 69, 105 y 111) y `notify.CRYPTO_CLASSES` (línea 30): el arranque sondea `worker_crypto_classes()` y cada job usa `spec.crypto_classes`; `cli_ops/sign_audit.py` (`sign-audit [--as]`); `cli_ops/keys_data_class.py` (nuevo, D80: `ensure_data_class(...)`; `cli.py` quita el stub y despacha `init-keys --data-class <clase> [--as]`: confirma o crea la fila con la referencia y la `public_key` del proveedor vigente, imprime proveedor y algoritmo, idempotente; D81); `core/crypto/migration.py` (E10: sigue excluyendo `sign`; `--data-class audit.signature` forzado → 2 `signatures_reference_key` sin tocar nada); `cli_ops/retire_key.py` (M-2a: `sign` referenciada → 2 `signatures_reference_key`; bajo su tope de 200); `cli_ops/rotate_key.py` (D81: `rotate-key audit.signature --provider <local|openbao> --reason … --as …` crea la llave de firma nueva en el proveedor destino con su `public_key` y deja la anterior `decrypt_only`, sin recifrar; sin `--provider` o con el vigente → 2 `purpose_not_rotatable`, D69; `--provider` con `purpose = encrypt` → 2; bajo su tope de 260); `core/jobs.DETAIL_KEYS` (+ `firmadas`, `nada_nuevo`, `reintentos`, `sellado`, `atrasada`, `cadena_rota`); `core/alerts.ALERT_CONTEXT_KEYS` (+ `through_seq`, `age_h`); `core/alerts_telegram.render_message` (`audit_sign_failed`, `audit_sign_late`, `audit_chain_broken`: solo enteros y el nombre del job). E13: `tests/worker/test_schedule.py` y `test_worker_boundaries.py` leídos; la lista de archivos del worker (`<=`) suma `jobs/sign_audit.py`.

**Paso 44 · A2.2 · Rojo**

- `tests/worker/test_sign_audit_job.py`: firma y `details = {firmadas: 1, ...}` enteros; sin novedades → `nada_nuevo = 1`, `ok`, sin alerta; dos corridas el mismo día no duplican; con `custodio_sellado` → tres reintentos con `espera_falsa` (2, 4, 8 s), `JobResult(ok=False)`, `reintentos = 3`, `sellado = 1`, `crypto_ops` con `result = error`, `alert("audit_sign_failed", job=, result=, error_type=, attempts=3)`; «atrasada» (48 h con filas sin firmar) → `alert("audit_sign_late", job=, age_h=)` una sola por corrida; cadena rota (H-1) → `ok=False`, `cadena_rota = 1`, `alert("audit_chain_broken", through_seq=)` y ninguna fila; `JOBS` en el orden `expirations`, `notify`, `sign_audit`, `backup_check` con `timeout_s = 300`; tras correr, el keyring contiene solo `audit.signature` (D42) y no abre ninguna DEK (`unwrap` no se llama); nunca `now()` directo (`current_clock()`).
- `tests/worker/test_schedule.py` (cuatro jobs; `should_run` sin reintento horario) y `test_worker_crypto_runtime.py` (el arranque sondea `worker_crypto_classes()` = `{member.phone, member.email, audit.signature}`; `notify` sigue con sus dos clases; O11: `grep` negativo de `WORKER_CRYPTO_CLASSES` y `CRYPTO_CLASSES` en `src/app/worker/`, y `tests/worker/test_notify_job.py` y `test_notify_sealed.py` siguen en verde).
- `tests/crypto/test_migrate_provider.py` y `tests/cli/test_migrate_provider_cli.py` (E10, D81): el plan sigue sin incluir las filas `sign` (las pruebas existentes de S5-D183 se conservan tal cual) y `migrate-provider --data-class audit.signature` sale 2 `signatures_reference_key` sin tocar la fila ni escribir `crypto_ops`.
- `tests/cli/test_rotate_sign_provider.py` y `tests/crypto/test_rotate_sign_provider.py` (D81): con una fila `sign` `local` versión 1 y dos firmas en `audit.signatures`, `rotate-key audit.signature --provider openbao --reason … --as …` (con `fake_transit`) inserta la versión 2 `active` `openbao` con referencia `apex-sign-audit` y `public_key` igual a la de `key_info`, pasa la 1 a `decrypt_only`, no cambia ninguna fila de `audit.signatures`, deja `crypto_ops(wrap)` y una sola fila `update` de auditoría sin material; `sign_latest` siguiente firma con la versión 2 y `crypto_ops(sign)` lleva su `key_id`; **una firma hecha con la llave anterior verifica por `key_id` con su clave pública tras rotar la llave de firma al proveedor nuevo** (`verify_signatures` → `ok`, `checked = 3`, `valid = 3`, sin llamadas al proveedor); la reversa `--provider local` funciona si existe `custody/sign-ed25519.key` y sale 2 si no; sin `--provider` o con el proveedor vigente → 2 `purpose_not_rotatable`; con el proveedor destino sin configurar → 2 nombrando la variable; `retire-key` de la versión 1 → 2 `signatures_reference_key` mientras existan firmas con ese `key_id`; `--as` obligatorio en producción; `cli_ops/rotate_key.py` bajo 260 (`test_cli_base.py`).
- `tests/cli/test_sign_audit_cli.py`: 0 al firmar y sin novedades; 1 si falla la firma; 2 con el custodio sellado («desellar OpenBao»); `--as` obligatorio con `ENV=production`; comparte el candado con el job (`dos_sesiones`: una sola fila); el error nunca lleva texto del proveedor.
- `tests/cli/test_init_keys_data_class.py`: `audit.signature` crea la fila `sign` con la referencia del proveedor vigente (`local:sign-ed25519` o `apex-sign-audit`) y `algorithm = Ed25519`; idempotente (segunda corrida «ya existe», 0); clase desconocida → 2; `attachment.sensitive` → 2 hasta C1 (`unknown_data_class`; C1 lo pone en verde); auditado (`audit_log` `insert` sobre `crypto.crypto_keys` sin material; `crypto_ops` solo en `encrypt`); `--as` en producción.
- `tests/cli/test_retire_key_cli.py` y `tests/crypto/test_retire_key.py`: llave `sign` referenciada por `audit.signatures` → 2 y ninguna transición; sin referencias → como hoy. `tests/cli/test_rotate_key_cli.py`: `audit.signature` → 2 `purpose_not_rotatable`.
- `tests/core/test_alerts.py` (claves nuevas enteras) y `tests/core/test_alerts_telegram.py` (tres textos sin nombres ni hashes).
- Arquitectura: `test_crypto_bus_importers.py` (`SOLO_RECOVERY` suma `worker/jobs/sign_audit.py`), `test_worker_boundaries.py` (el job no escribe SQL ni importa `models`; llama `core.audit_sign`), `test_no_sensitive_in_logs.py`, `test_app_layer_importers.py` (`cli_ops/sign_audit.py` no importa `bus`: pasa por `cli_base.crypto_runtime` y `core.audit_sign`, S4B-D30).

**Paso 45 · A2.3 · Verde.** Los archivos del paso 43; cada archivo de `cli_ops/` bajo su tope real de `TOPE_CLI_OPS` (150 para `sign_audit.py` y `keys_data_class.py`, 260 para `rotate_key.py`, 200 para `retire_key.py`; D80); `worker/main.py` (`--run-once sign_audit`, `--status sign_audit`); `core/crypto/migration.py` (solo el mensaje `signatures_reference_key`); `core/crypto/service.py` (`next_key_state` reutilizado; sin crecer).

**Paso 46 · A2.4 · Documentación.** RUNBOOK §11 (`--run-once sign_audit`, `--status`, qué hacer ante `audit_chain_broken`: `verify-audit` y el procedimiento de incidente) y §14; `openbao.md` (`init-keys --data-class audit.signature` tras instalar; tras `migrate-provider` la firma **no** migra: se cambia de proveedor con `rotate-key audit.signature --provider openbao`, orden operativo de D18 ampliado); `rotar-llave.md` (`rotate-key audit.signature --provider`: llave nueva, firmas viejas verifican por su clave pública, `retire-key` las protege; `migrate-provider` excluye `sign` y por qué, S5-D183 intacta); `docs/operacion/llaves.md` (la llave de firma no se rota en sitio en v0.3, D69); bloque A2; cuaderno.

**Paso 47 · A2.5 · Gate**

1. `slice-gate.sh cli tests/cli/test_sign_audit_cli.py tests/cli/test_init_keys_data_class.py tests/cli/test_init_keys_cli.py tests/cli/test_retire_key_cli.py tests/cli/test_rotate_key_cli.py tests/cli/test_rotate_sign_provider.py tests/cli/test_migrate_provider_cli.py tests/cli/test_cli_base.py`.
2. `slice-gate.sh crypto tests/crypto/test_retire_key.py tests/crypto/test_rotate.py tests/crypto/test_rotate_sign_provider.py tests/crypto/test_migrate_provider.py tests/crypto/test_sign_algorithm.py`.
3. `slice-gate.sh core/jobs tests/worker/test_jobs_core.py`.
4. `slice-gate.sh core/alerts tests/core/test_alerts.py tests/core/test_alerts_telegram.py tests/core/test_alerts_telegram_gate.py`.
5. `slice-gate.sh architecture tests/architecture/test_crypto_bus_importers.py tests/architecture/test_worker_boundaries.py tests/architecture/test_no_sensitive_in_logs.py tests/architecture/test_app_layer_importers.py`.
6. `security-reviewer` de A2 (reintentos sin fuga, alertas sin PII, M-2 a/d).
7. Sello: `slice-gate.sh worker tests/worker/test_sign_audit_job.py tests/worker/test_schedule.py tests/worker/test_worker_crypto_runtime.py tests/worker/test_runner.py tests/worker/test_notify_job.py tests/worker/test_main.py`.

**Paso 48 · A2.6 · Docker y evidencia (demo 1, parte)**

1. Buildx del api; `$DC up -d --no-build --force-recreate api worker` + `restart web`.
2. Desarrollo (proveedor local): `$DC run --rm tools init-keys --data-class audit.signature --as <admin>` dos veces (la segunda «ya existe»); `$DC run --rm worker python -m app.worker.main --run-once sign_audit` dos veces (`ok`, luego `nada_nuevo`); `SELECT through_seq, algorithm, payload_version FROM audit.signatures` (una fila, `Ed25519`, 1); `--status sign_audit`.
3. Ensayo (OpenBao): `$DCEB run --rm tools init-keys --data-class audit.signature --as <admin>` → fila `openbao` con referencia `apex-sign-audit` (la referencia no se imprime en la respuesta HTTP; el CLI sí la muestra, es operación); `--run-once sign_audit` → `ok`, `firmadas = 1`; `crypto_ops` `sign` `ok`.
4. Sellado: `$DCE restart openbao` (sin desellar); `--run-once sign_audit` → tres reintentos en el log (2, 4, 8 s), `error`, `sellado = 1`, alerta `audit_sign_failed` en el sink de log; desellar con 3; `--run-once sign_audit` → firma hasta el último `seq` (`nada_nuevo` si no hubo filas).
5. Evidencia de `job_runs` y `crypto_ops` (solo lectura) al cuaderno.

**Paso 49 · A2.7 · Checkpoint.** `"S6-A2 job sign_audit a las 07:00 tras notify con 3 reintentos y alertas audit_sign_failed, audit_sign_late y audit_chain_broken; keyring del worker por job; sign-audit e init-keys --data-class; retire-key niega la llave de firma referenciada"`.

### S6-A3 · Verificación con firmas, `0022` y estado en pantalla (US-142)

- **Cierra:** parte de C2 (`verify` con firmas, `GET /audit/signatures/latest`), M-1, bug 19 de la exploración, D10, D36, D62, Q5.
- **Depende de:** A2. **Migración:** `0022_audit_verifications_signatures`.

**Paso 50 · A3.1 · P-MIG y stubs.** Volcado `antes-0022`; `stop api worker`. Stubs: `core/audit_verify.py` (`SignatureVerdict(state, checked, valid, first_invalid_seq, last_valid_seq, last_valid_at, last_valid_algorithm)`, `signature_state(checked, valid, first_invalid_seq) -> Literal["none","ok","invalid"]` pura, `async verify_signatures(session, *, through_seq) -> SignatureVerdict` (todas las firmas, por lotes de 100, con la clave pública; D62, D81), `anti_rollback(prev_last_valid_seq, max_signed_seq, signatures_count) -> bool` pura, `AuditVerification` con las seis columnas, `VerificationView` ampliada); `modules/audit/schemas.py` (`VerifyResultOut` y `VerifyStartedOut` con los campos opcionales; `SignaturesLatestOut(latest, last_valid, is_late, state)`); `modules/audit/{service,verify,router}.py` (`GET /audit/signatures/latest` antes de `/audit/{seq}`; `AdminDep`; `staff-read`; `no_store`); `cli_ops/verify_audit.py` (firmas en la salida; 1 con `invalid`; sigue sin depender del custodio).

**Paso 51 · A3.2 · Rojo**

- `tests/migrations/test_0022_audit_verifications_signatures.py`: seis columnas nulas; filas previas intactas; `signatures_forbid`/`verifications_*` de `0013` conservados en `A`; `downgrade` quita las columnas; ciclo; `test_0021_*` pasa a «en la cadena».
- `tests/core/test_signature_state_pure.py`: tabla de `signature_state` y de `anti_rollback`.
- `tests/audit/test_verify_signatures.py`: cadena sana con tres firmas → `ok`, `checked = 3`, `valid = 3`; firma alterada → `invalid`, `ok = false`, `broken_at_seq = first_invalid_seq`; firma borrada con el trigger apagado → `anti_rollback` lo detecta sin ninguna llamada a Transit (contador del `FakeTransit` en 0 para esa parte); llave `decrypt_only` y llave `retired` (`firma_de_llave_retirada`) verifican por su `public_key`; `custodio_sellado` → la verificación completa sigue en `ok` con `checked = valid = 3` y cero llamadas al proveedor (D81: cierra M-1); con 365 firmas (`cadena_con_firmas`, mitad `local` y mitad `openbao` con `fake_transit`) se verifican las 365 (`checked = 365`) y el contador de `verify` del `FakeTransit` queda en 0; una `public_key` alterada en la fila → `invalid`; `payload_version` elige el constructor (una firma con `payload_version = 1` y un constructor falso `v2` registrado en la prueba).
- `tests/audit/test_router_signatures.py`: `GET /audit/signatures/latest` admin; coach y socio 403; 401; `no-store`; cubeta `staff-read`; `is_late` verdadero a las 49 h; `state`; `last_valid` nulo sin verificaciones; `POST /audit/verify` y `GET /audit/verify/last` con los campos nuevos (nulos para verificaciones viejas); `tests/audit/test_router_verify.py`, `test_verify.py` y `test_verify_concurrency.py` existentes siguen en verde.
- `tests/cli/test_verify_audit.py`: salida con firmas; 1 `invalid`; 0 con el custodio sellado (`custodio_sellado`).
- `tests/core/test_format_verify_message.py`: el mensaje incluye el estado de firmas.
- Arquitectura: `test_error_codes_per_route.py`, `test_no_store_routes.py`, `test_every_route_has_role.py`, `test_routes_under_api_v1.py`, `test_user_limits_catalog.py` (`staff-read` ya tiene ruta).

**Paso 52 · A3.3 · Verde.** P-MIG pasos 3 a 8 de `0022`; `core/audit_verify.py` (sigue < 800; si pasa de 600, `core/audit_verify_signatures.py` hermano con decisión del slice); `modules/audit/*`; `cli_ops/verify_audit.py`.

**Paso 53 · A3.4 · Contrato y documentación.** P-API (`VerifyResultOut`, `VerifyStartedOut`, `SignaturesLatestOut`); RUNBOOK §9 (verify con firmas: completa, con la clave pública guardada, también con OpenBao sellado) y §14; ADR-006 (`tests/audit/test_verify_signatures.py`); bloque A3; cuaderno.

**Paso 54 · A3.5 · Gate**

1. `slice-gate.sh core/audit_verify tests/core/test_signature_state_pure.py tests/core/test_format_verify_message.py tests/audit/test_verify_signatures.py tests/migrations/test_0022_audit_verifications_signatures.py`.
2. `slice-gate.sh cli tests/cli/test_verify_audit.py`.
3. `slice-gate.sh architecture tests/architecture/test_error_codes_per_route.py tests/architecture/test_no_store_routes.py tests/architecture/test_every_route_has_role.py tests/architecture/test_user_limits_catalog.py`.
4. `database-reviewer` (`0022`) y `security-reviewer` (M-1 cerrada: verificación sin custodio con la clave pública; `public_key` inmutable; anti-retroceso sin Transit), en paralelo.
5. Sello: `slice-gate.sh audit tests/audit/test_verify_signatures.py tests/audit/test_router_signatures.py tests/audit/test_router_verify.py tests/audit/test_verify.py tests/audit/test_verify_concurrency.py tests/migrations/test_0022_audit_verifications_signatures.py tests/migrations/test_0021_audit_signatures.py`.
6. Después del sello, sin tocar el árbol: `run-gates.sh` (primera de cuatro) con el ensayo detenido.

**Paso 55 · A3.6 · Docker y evidencia (demo 1 completa)**

1. Buildx; `$DC up -d --no-build --force-recreate api worker` + `restart web`; ensayo: `stop worker`, `migrate` → `0021 -> 0022`, `dbsetup`, `test_db_roles.sh`, recrear api y worker, `restart web`.
2. Ensayo: `POST /api/v1/audit/verify` en 8280 (admin) → `ok: true`, `signatures_checked ≥ 1`, `signatures_valid` igual; `GET /audit/signatures/latest` → `latest`, `last_valid`, `is_late: false`, `state: ok`; `GET /audit/verify/last` con los campos.
3. Custodio sellado: `$DCE restart openbao`; `POST /audit/verify` → 200 con `ok: true` y `signatures_valid` igual que desellado (D81); `$DCEB run --rm tools verify-audit --as <admin>` → salida 0; `--run-once sign_audit` sí falla (firmar exige Transit); desellar.
4. Cadena reescrita y firma inválida: se cita la prueba de `db_test` (`test_verify_signatures.py`), nunca contra el ensayo.
5. Evidencia al cuaderno; `docker stats`.

**Paso 56 · A3.7 · Checkpoint.** `"S6-A3 verificación con firmas (0022) completa con la clave pública de crypto_keys, sin custodio, anti-retroceso sin Transit y GET /audit/signatures/latest"`.

### S6-B1 · Router de llaves, inventario y puerto `Reencryptor` (US-143)

- **Cierra:** parte de C3 (router, inventario, `records_count`, `__init__` vacío, `set_audit_writer`), bugs 9 y 10 de la exploración, D12, D13, D14, D44, D52, D54, E6, E7.
- **Depende de:** A3. **Migración:** ninguna.

**Paso 57 · B1.1 · Stubs y E6/E7**

- E6 (`core/errors.responses_for` y `_DESCRIPCIONES` para rutas de `core/`) y E7 (cómo `main.py` incluye `health.router`) por lectura; la respuesta va al cuaderno.
- Stubs: `core/crypto/router.py` (`router = APIRouter()`, `set_audit_writer(fn)`, `GET /crypto/keys`); `core/crypto/inventory.py` (`async list_keys(session, filters, page) -> Page[CryptoKeyOut]`, `async summary(session) -> KeysSummary`, `async records_count(session, data_class) -> int | None`, `age_days(created_at, rotated_at, now)` pura); `core/crypto/schemas.py` (`CryptoKeyOut`, `KeysSummary`, `KeysFilters`; nunca `wrapped_material` ni la referencia); `core/crypto/reencryptor.py` (`Reencryptor` `Protocol` con `count_total`, `count_pending`, `reencrypt_batch`; `register_reencryptor`, `get_reencryptor`, `reencryptor_registered`); `core/crypto/__init__.py` vacío (0 bytes); `main.py` registra `core.crypto.router` bajo `/api/v1` de forma explícita, llama `set_audit_writer(audit.record)` y nada más; `core/crypto/service.py`: `_pending_total` y `reencrypt_batch` ramifican por el puerto; `start_rotation` responde `rotation_not_supported` para una clase cifrada sin columnas ni puerto; `finish_rotation` recuenta por `count_pending` bajo `FOR SHARE` y falla si es mayor que 0; `cli_ops/rotate_key.py` quita la constante `ATTACHMENT_CLASS` y usa el error del service.

**Paso 58 · B1.2 · Rojo de arquitectura**

- `test_core_import_direction.py`: `core/crypto/{router,inventory,schemas,reencryptor}.py` sin `app.modules` ni `core.audit*` (ni `core.audit_verify` ni `core.audit_sign`); `core/crypto/__init__.py` vacío; solo `main.py` importa `core.crypto.router`; `core.security` no lo importa.
- `test_every_route_has_role.py`, `test_no_store_routes.py`, `test_routes_under_api_v1.py`, `test_list_routes_use_page_params.py` (`q` sobre `data_class`), `test_error_codes_per_route.py` (503 `busy` cuando falta la puerta, en las rutas auditadas que lleguen en B3 y R1), `test_banned_imports.py` (`router.py` e `inventory.py` sin `cryptography`, `hashlib`, `hmac`), `test_health_check_registrars.py` (sin cambio).
- Nueva `tests/architecture/test_crypto_inventory_no_material.py`: recorre el OpenAPI y una respuesta real: ninguna clave `wrapped_material`, `key_ref`, `material`, `reference`; ningún valor con prefijo `vault:`, `apxw1`, `local:` ni `apex-sign-audit`.
- `test_file_and_function_size.py`: `core/crypto/service.py` no crece (se fija el tope actual, 556 líneas, como máximo).

**Paso 59 · B1.3 · Rojo**

- `tests/crypto/test_inventory.py`: campos de D13 (`id`, `purpose`, `data_class`, `algorithm`, `version`, `state`, `provider`, `created_at`, `rotated_at`, `age_days`, `records_count`); `records_count` por `discovery.encrypted_columns` para `member.document`, por `reencryptor_doble` para una clase registrada con puerto, nulo para `kek.backup` y `audit.signature`; filtros `purpose`, `state`, `provider`, `data_class`, `q`; paginación (25 por defecto, 200 máximo, `offset`); orden estable `data_class, purpose, version DESC`; `summary` con `active_count`, `operations_today` (hora de Bogotá), `running_jobs` y `provider` (`names` = proveedores distintos de las filas `active`; `state` = `recovery.current_state()`, D54); no escribe `crypto_ops`; la consulta usa columnas explícitas (sin `select(CryptoKey)`, aserción sobre el SQL emitido).
- `tests/crypto/test_router_keys.py`: admin 200; coach y socio 403; sin token 401; `no-store`; cubeta `staff-read` (429 al pasar el tope); 422 en filtros inválidos.
- `tests/crypto/test_reencryptor.py`: `register`/`get`/`registered`; registrar dos veces la misma clase → error; `start_rotation` de una clase cifrada sin columnas ni puerto → `CryptoError("rotation_not_supported")` sin crear job ni llave; con `reencryptor_doble`, `_pending_total`, `reencrypt_batch` y `finish_rotation` delegan; `finish_rotation` con `count_pending > 0` → `fail_job` y la llave anterior sigue `decrypt_only`.
- `tests/cli/test_rotate_key_cli.py`: `attachment.sensitive` (sin puerto todavía) → 2 con el mensaje del service.

**Paso 60 · B1.4 · Verde.** Archivos del paso 57, cada uno < 400 líneas; `service.py` sin crecer (si la rama del puerto no cabe, se extrae `core/crypto/service_pending.py` con decisión del slice); `CLAUDE.md` regla 4 gana la frase «`core/` puede exponer HTTP (`health`, `crypto/router`) registrado desde `main.py`».

**Paso 61 · B1.5 · Contrato y documentación.** P-API (`GET /crypto/keys`); `docs/operacion/llaves.md` (inventario y lectura del estado del proveedor); `CLAUDE.md`; BRECHAS 13.26 cerrada; bloque B1; cuaderno.

**Paso 62 · B1.6 · Gate**

1. `slice-gate.sh main tests/crypto/test_router_keys.py tests/core/test_startup_failure.py`.
2. `slice-gate.sh architecture tests/architecture/test_core_import_direction.py tests/architecture/test_crypto_inventory_no_material.py tests/architecture/test_list_routes_use_page_params.py tests/architecture/test_every_route_has_role.py tests/architecture/test_no_store_routes.py tests/architecture/test_banned_imports.py tests/architecture/test_file_and_function_size.py`.
3. `slice-gate.sh cli tests/cli/test_rotate_key_cli.py`.
4. `security-reviewer` de B1 (sin material ni referencias; roles; puerta de auditoría).
5. Sello: `slice-gate.sh crypto tests/crypto/test_inventory.py tests/crypto/test_router_keys.py tests/crypto/test_reencryptor.py tests/crypto/test_rotate.py tests/crypto/test_rotate_concurrency.py tests/crypto/test_rotate_index.py`.

**Paso 63 · B1.7 · Docker y evidencia.** Buildx; recrear api y worker en desarrollo y en el ensayo (+ `restart web`); `GET /api/v1/crypto/keys` en 8181 (9 filas: 5 `encrypt`, 3 `index`, 1 `sign`; `provider.names = ["local"]`) y en 8280 (`["openbao"]`, `state: ok`); `grep -c 'vault:' <respuesta>` = 0.

**Paso 64 · B1.8 · Checkpoint.** `"S6-B1 router de llaves en core/crypto con set_audit_writer desde main.py, inventario sin material con records_count por el registro, puerto Reencryptor y rotation_not_supported para clases sin columnas ni puerto"`.

### S6-B2 · Bitácora y trabajos (US-144)

- **Cierra:** parte de C3, D16, bug 22 de la exploración (`JOB_KINDS`).
- **Depende de:** B1. **Migración:** ninguna.

**Paso 65 · B2.1 · Rojo.** `tests/crypto/test_ops_jobs.py`: `GET /crypto/ops` con `from`/`to` (`check_instant_range`, 422 si el rango está invertido o pasa de 366 días), `verb`, `data_class`, `key_id`, `user_id`, `result`, `batch_id`, `q`; orden `at DESC, id DESC`; no escribe `crypto_ops` (conteo antes y después); `GET /crypto/jobs` con `status`, `kind` (solo `JOB_KINDS`), `data_class`, `q`; `percent = job_percent(total, done)` pura (0 con `total = 0`; `done*100//total`); paginación 200 máximo; roles y `no-store`; cubeta `staff-read`. `tests/crypto/test_job_percent_pure.py`.

**Paso 66 · B2.2 · Verde.** `inventory.list_ops`, `list_jobs`, `job_percent`; `schemas.CryptoOpOut`, `CryptoJobOut`; `router.py`.

**Paso 67 · B2.3 · Contrato y documentación.** P-API; `llaves.md` (bitácora y trabajos); cuaderno.

**Paso 68 · B2.4 · Gate y evidencia.** `security-reviewer` de B2 (sin `user_id` ajeno en texto libre; sin material). Sello: `slice-gate.sh crypto tests/crypto/test_ops_jobs.py tests/crypto/test_job_percent_pure.py tests/crypto/test_router_keys.py`. Buildx y recreación; en el ensayo `GET /crypto/ops?verb=sign` (las firmas de A2) y `GET /crypto/jobs` (`migrate_provider` `done`, `percent = 100`).

**Paso 69 · B2.5 · Checkpoint.** `"S6-B2 bitácora de crypto_ops y trabajos con porcentaje, filtros con rango acotado, solo lectura"`.

### S6-B3 · CBOM (US-146)

- **Cierra:** parte de C3 (CBOM, `file_download`), L-5, D17, Q26.
- **Depende de:** B2. **Migración:** ninguna.

**Paso 70 · B3.1 · Stubs.** `core/crypto/cbom.py` (`FIXED_ALGORITHMS` (JWT Ed25519, contraseñas argon2id, índice HMAC-SHA256, cadena SHA-256, firma Ed25519, respaldo age), `build_cbom(keys, *, app_version, generated_at, provider, tls_declared) -> dict` pura, `CBOM_FORMAT = "apex-cbom/1"`); `core/http.file_download(body: bytes, *, filename, media_type) -> Response` (`attachment`, `no-store`, `nosniff`, `Content-Security-Policy: default-src 'none'; sandbox`); `router.GET /crypto/cbom`; `core/ratelimit` (`cbom-export` con ruta).

**Paso 71 · B3.2 · Rojo.** `tests/crypto/test_cbom_pure.py` (orden estable por `data_class, purpose, version`; `fixed_algorithms` completo; `tls.declared` desde `APEX_DOMAIN` y `source = "configuration"`; sin `records_count`; `format`, `generated_at`, `app_version`, `provider`); `tests/architecture/test_cbom_no_key_material.py` (ante `bytes`, base64 de 40 o más caracteres, la palabra `wrapped`, `vault:`, `apex-sign-audit` o `local:` la prueba falla; recorre un CBOM real de `llaves_mixtas`); `tests/crypto/test_router_cbom.py` (admin; 403 coach y socio; `application/json; charset=utf-8`; `Content-Disposition: attachment; filename=apex-cbom-AAAA-MM-DD.json` con `today_bogota()`; `no-store`; `nosniff`; auditoría `export` sobre `crypto.crypto_keys` con `after = {"count": n, "format": "apex-cbom/1"}` en la misma transacción vía el escritor registrado; sin puerta (`sin_audit_writer`) → 503 `busy` y nada descargado; cubeta `cbom-export` 2/min); `tests/core/test_http.py` (cabeceras de `file_download`); arquitectura: `test_core_import_direction.py` (`core/http.py` y `cbom.py` sin módulos), `test_user_limits_catalog.py` (quita `cbom-export`), `test_error_codes_per_route.py`.

**Paso 72 · B3.3 · Verde.** `cbom.py` (< 200 líneas), `core/http.py`, `router.py`, `core/ratelimit.py`.

**Paso 73 · B3.4 · Contrato y documentación.** P-API; `llaves.md` (CBOM: qué contiene, qué no, `tls` declarado); bloque B3; cuaderno.

**Paso 74 · B3.5 · Gate**

1. `slice-gate.sh core/http tests/core/test_http.py`.
2. `slice-gate.sh architecture tests/architecture/test_cbom_no_key_material.py tests/architecture/test_user_limits_catalog.py tests/architecture/test_error_codes_per_route.py tests/architecture/test_core_import_direction.py`.
3. `security-reviewer` de B3 (L-5; nada de material; auditoría antes del cuerpo).
4. Sello: `slice-gate.sh crypto tests/crypto/test_cbom_pure.py tests/crypto/test_router_cbom.py`.

**Paso 75 · B3.6 · Docker, evidencia y checkpoint (demo 2, parte).** Buildx; recreación; en el ensayo `curl -sS -D - -o docs/scratch/ensayo/apex-cbom.json` de `GET /crypto/cbom` con el token del admin → nombre con la fecha de Bogotá, `grep -c -E 'vault:|wrapped|apex-sign' apex-cbom.json` = 0, `jq '.keys | length'` = 9, `.tls.declared = false` (modo LAN); `audit_log` con `export` sobre `crypto.crypto_keys`. `checkpoint-commit.sh "S6-B3 CBOM apex-cbom/1 sin material ni referencias, descargado por file_download con cubeta cbom-export y auditado como export"`.

### S6-C1 · Módulo `attachments` (`0023`): almacenamiento, cifrado, recifrado y `attachments-check` (US-147)

- **Cierra:** parte de C4 (módulo, `0023`, grants, registro, tercera puerta, `STORAGE_PROVIDER` ya en W0-5), bugs 7 (parte) y 15, 16 de la exploración, M-3 (semáforo y orden en `open`), M-4 (lectura acotada por `chunks` sin spool; la validación antes de leer llega en C2 con la ruta), M-9, M-10 (texto), L-1, L-3 (conteo por `key_id`), D18, D21, D22, D25, D26, D45 (S3, retención), D53, D59, D60, D75, D76, E9.
- **Depende de:** B3. **Migración:** `0023_attachments`.

**Paso 76 · C1.1 · P-MIG, verificación y stubs**

- P-MIG pasos 1 y 2: volcado `antes-0023`; `stop api worker`.
- E9 (E1): en el `.venv` del api (Starlette 1.9.0) se confirma lo que fijó la crítica 1: `max_part_size` solo acota campos de texto y `request.form()` consume todo el cuerpo; por eso el módulo lee con `request.stream()` y nunca con `form()`, `UploadFile` ni `SpooledTemporaryFile` (`test_third_party_confinement.py` y `test_banned_imports.py` prohíben `starlette.formparsers`, `python_multipart` y `tempfile.SpooledTemporaryFile` en `src/app/modules/attachments/` y `members/`); la respuesta va al cuaderno.
- Stubs del módulo `attachments`: `__init__.py`; `models.py` (`Attachment`, `__audited__ = True`, `__audit_subject__ = "owner_id"`, `__audit_exclude__ = ("filename_random", "key_id")`); `schemas.py` (`AttachmentOut` sin `filename_random`; `AttachmentBody(meta, data | stream)`; `KIND`, `MIME`); `exceptions.py` (`AttachmentNotFound` 404 `attachment_not_found`, `FileTooLarge` **413** `file_too_large` campo `file` (D73), `UnsupportedType` 422 `unsupported_type` campo `file`, `StorageUnavailable`); `core/errors.py` (`_DESCRIPCIONES` gana el 413); `rules.py` (`detect_mime(head) -> str | None`, `validate_upload(size_bytes, mime, kind) -> None`, `kind_is_sensitive(kind) -> bool`, `find_orphans(row_keys, stored_keys) -> OrphanReport`, `ATTACHMENT_MAX_BYTES`, `ATTACHMENT_READ_LIMIT`); `files.py` (privado: `_encrypt_file(data, attachment_id) -> bytes`, `_decrypt_file(blob, attachment_id) -> bytes`, única puerta a `bus.encrypt`/`bus.decrypt` del módulo); `queries.py`; `service.py` (fachada: `async store(session, *, owner_table, owner_id, kind, chunks: AsyncIterator[bytes], by) -> Attachment` (consume `chunks` acumulando hasta `ATTACHMENT_MAX_BYTES` y lanza `FileTooLarge` al byte 5.242.881 sin seguir leyendo; `chunks` es `request.stream()` en el router de `members`, D59), `async open(session, attachment_id, *, by, audit=True) -> AttachmentBody`, `async current_photo_id(session, owner_table, owner_ids) -> dict[UUID, UUID | None]`, `async list_for_owner(session, owner_table, owner_id, page) -> Page[AttachmentOut]`, `register_reencryptor()`, `SENSITIVE_SLOTS = 4`); `reencrypt.py` (implementación del `Reencryptor`, lote 50); `storage/{__init__,base,local,s3}.py` (`StorageProvider` `Protocol`: `put`, `get`, `stream`, `exists`, `delete_object`; `LocalDiskStorage(root)`; `S3CompatibleStorage(settings)` con `boto3` perezoso; `storage_from_settings(settings)`); `router.py` (`router = APIRouter()` vacío hasta C4); `cli_ops/attachments_check.py` (`attachments-check [--as]`: solo lectura; sale 1 con huérfanos).
- Registro: `core/crypto/registry.py` (`attachment.sensitive`: `encrypt=True`, `index_kind=None`, `sign=False`, `value_type="str"` con comentario «el blob textual se guarda en el objeto», `columns=()`); `main.MODULES` con `attachments` antes de `members`; `main.py` y `cli_base.py` llaman `attachments.service.register_reencryptor()`; `core/db.APP_SCHEMAS` suma `attachments`; `migrations/env.py`; `modules/audit/queries.AUDITABLE_TABLES` suma `attachments.attachments`; `core/audit.py` lee `__audit_exclude__` (D75); `tests/factories/files.py`; `tests/attachments/conftest.py`; `LIMPIAR_ATTACHMENTS` en `tests/conftest.py`.

**Paso 77 · C1.2 · Rojo de arquitectura**

- `test_audit_module.py` (`MODULES` con `attachments` antes de `members`); `test_audited_tables.py` (`attachments.attachments` auditada; `__audit_exclude__` admitido solo para columnas existentes); `test_audit_subject.py` (`owner_id`); `test_no_cross_models.py` (`PRIVATE_HELPERS["attachments"] = {files, rules, queries, reencrypt, storage}` por igualdad; `attachments` no importa `members.models`); `test_service_import_graph.py` (`attachments` sin aristas salientes a módulos; la de `members → attachments` llega en C2); `test_crypto_bus_importers.py` (`IMPORTADORES_REALES` suma `modules/attachments/files.py`); `test_reveal_single_door.py` (tercera puerta `("modules/attachments/files.py", "_decrypt_file")` en el conjunto exacto; `_encrypt_file` como única llamada a `bus.encrypt` fuera de `members`); `test_no_plaintext_at_rest.py` (sube un PDF sensible por `service.store` y lee el archivo del `tmp_path`: no contiene los bytes del PDF y empieza por `apx1.`); `test_third_party_confinement.py` (`boto3`/`botocore` solo en `storage/s3.py`; `python_multipart`, `multipart`, `starlette.formparsers`, `starlette.datastructures.UploadFile` y `tempfile.SpooledTemporaryFile` no se importan en ningún sitio de `src/app`; E1); `test_no_physical_delete.py` y `test_no_trigger_tampering.py` (`attachments_guard_update`, `attachments_forbid_delete`, `attachments_forbid_truncate` en `A`); `test_db_grants.py` (esquema `attachments` en las cuatro sentencias; tabla clasificada: `apex_api` `S I` más `U (key_id, updated_at)`; `apex_worker` nada; `apex_backup` lectura); nueva `tests/architecture/test_reencryptor_registered_in_every_root.py` (`main.create_app()` y `cli_base.cli_runtime()` dejan `reencryptor_registered("attachment.sensitive")` verdadero); `test_core_import_direction.py` (`core/audit.py` sigue importando solo `digest`); `tests/core/test_audit_hook_db.py` (`__audit_exclude__` con un modelo de prueba: las columnas excluidas no aparecen en `before`/`after`, el resto sí).

**Paso 78 · C1.3 · Rojo**

- `tests/migrations/test_0023_attachments.py`: `CREATE SCHEMA attachments`; columnas y CHECKs de D25 (`owner_table` solo `members`; `kind` `photo|consent|other`; `filename_random` único de 32 hex; `mime` tres valores; `size_bytes` entre 1 y 5242880; `sensitive` obligatorio con `consent`; `sensitive = (key_id IS NOT NULL)`; `storage_provider` `local|s3`); índice `(owner_table, owner_id, kind, created_at DESC)`; trigger `attachments_guard_update` (un `UPDATE` que toque otra columna que `key_id`/`updated_at` falla); `DELETE` y `TRUNCATE` prohibidos; los tres `ENABLE ALWAYS`; `downgrade` borra tabla, triggers, función y esquema; ciclo; `test_0022_*` pasa a «en la cadena»; sobre `apex_roles`: `apex_api` inserta y actualiza `key_id`, no borra ni cambia `kind`; `apex_worker` no lee.
- `tests/attachments/test_rules_pure.py`: `detect_mime` JPEG, PNG, PDF, ELF, PE, vacío, 3 bytes; `validate_upload` con 5.242.880 ok y 5.242.881 → `FileTooLarge`; matriz `kind × mime` (foto solo imagen; `consent` y `other` imagen o PDF); `kind_is_sensitive`; `find_orphans` (filas sin objeto, objetos sin fila, ambos vacíos).
- `tests/attachments/test_storage_contract.py` (parametrizado `local`, `s3` con `s3_stubber`): `put`/`get`/`exists`/`stream` (trozos de 64 KiB) /`delete_object`; clave inválida (`../x`, `ABC…`, 31 hex, con `/`) → `ValueError` sin tocar disco ni red; `local`: temporal en la misma carpeta, `fsync`, `os.replace`, modo 600, raíz `UPLOADS_DIR/attachments`, I/O en `to_thread`; `s3`: `Config(proxies={}, retries={"max_attempts": 3})`, `verify=True`, credenciales explícitas (nunca la cadena por defecto: la prueba borra `AWS_*` y `~/.aws` falsos y exige que no se lean), `endpoint https`.
- `tests/attachments/test_s3_flags.py`: `STORAGE_PROVIDER=s3` con `ENV=production` sin `S3_ENABLE_PRODUCTION=true` → el arranque (`storage_from_settings`) falla nombrando la variable; `endpoint http` fuera de `dev` → falla; `boto3` ausente → mensaje «instale el extra s3».
- `tests/attachments/test_service_store.py`: sensible → objeto con `apx1.` y sin los bytes originales, `key_id` tomado del blob (`core.crypto.blob`), `crypto_ops(encrypt)` con `record_id = id`, `aad = aad_for(id)`; foto → objeto en claro, `key_id` nulo, sin `crypto_ops`; ELF renombrado `.jpg` → `UnsupportedType` y nada escrito; 5.242.881 bytes por `chunks` → `FileTooLarge` (413) antes de escribir, y el lector corta en `ATTACHMENT_READ_LIMIT` (un iterador que cuenta demuestra que nunca consume más; un iterador infinito no cuelga); nada se escribe en `tempfile` ni en `/tmp` (monkeypatch de `tempfile` que falla si se llama; medición del spool, E1); pico de memoria de una subida sensible de 5 MiB con `tracemalloc` por debajo de 14 MiB; `put` fallido → sin fila; flush fallido tras `put` → `delete_object` compensatorio con log sin nombre de archivo (`caplog`); semáforo: la quinta operación sensible concurrente → 503 `busy` con `Retry-After: 1` (D59); auditoría `insert` con `uploaded_by` y sin `filename_random` ni `key_id` (L-1); la foto nueva no borra la anterior y `current_photo_id` devuelve la más reciente por `created_at DESC, id DESC`.
- `tests/attachments/test_service_open.py`: orden descifrar → `audit.record("download", table_name="attachments.attachments", record_id=id, subject_member_id=owner_id, after={kind, sensitive, owner_id})` → commit → cuerpo (secuencia observada con `dos_sesiones`); con `custodio_sellado` → `CryptoUnavailable` y **ninguna** fila `download` (M-3); foto con `audit=False` → sin fila y `stream` (no `get`); `crypto_ops(decrypt)` solo en sensibles; una sola fila por `open`; 404 para un id inexistente.
- `tests/attachments/test_reencrypt.py`: `count_total`, `count_pending(active_key_id)` por `key_id`; `reencrypt_batch` toma 50 con `FOR UPDATE SKIP LOCKED`, descifra con la llave `decrypt_only`, cifra con la activa, reemplaza el objeto de forma atómica y luego actualiza `key_id`; corte simulado entre el objeto y el `UPDATE` → el siguiente lote lo recifra otra vez sin error; `crypto_ops` con el mismo `batch_id`; 0 pendientes al terminar.
- `tests/attachments/test_current_photo_ids.py`: una consulta por lote de 200 ids.
- `tests/cli/test_attachments_check.py`: 0 sin huérfanos; 1 con huérfanos y la lista (solo ids e hex, sin nombres); solo lectura (ninguna escritura en la base ni en el volumen); `--as`; `tests/cli/test_init_keys_data_class.py`: `attachment.sensitive` ahora crea la fila `encrypt` A256GCM (pasa a verde el caso de A2).

**Paso 79 · C1.4 · Verde de `0023`.** P-MIG pasos 3 a 8 (`\dn`, `\d attachments.attachments`, triggers); `grants.sql` (cuatro sentencias de esquemas, matriz, `-- clasificada:`, `ARRAY`), `revoke.sql`, `test_db_grants.py`; `tests/conftest.py` (limpieza).

**Paso 80 · C1.5 · Verde del módulo.** Archivos del paso 76 (< 400 líneas cada uno; funciones < 50); `core/audit.py` (solo `__audit_exclude__`, D75); `core/crypto/registry.py`; `main.py`; `cli_base.py`; `core/db.py`; `cli_ops/attachments_check.py` (bajo el tope de 150 de `TOPE_CLI_OPS`, D80); `cli_ops/keys_data_class.py` (`attachment.sensitive`); `pyproject.toml` sin dependencia nueva (E1).

**Paso 81 · C1.6 · Documentación.** `docs/operacion/adjuntos.md` (tipos, tamaños, bytes mágicos, cifrado, huérfanos y `attachments-check`, S3 apagado, procedimiento manual de supresión de D76, residual de retención v0.4); ADR-007 cita `tests/architecture/test_no_plaintext_at_rest.py`, `tests/attachments/test_service_open.py` y `test_reencrypt.py`; `respaldo-y-restauracion.md` (los adjuntos viajan en `<name>-uploads.tar.age`; la prueba con un adjunto llega en C5); RUNBOOK §6 (rollback de `0023`: los objetos quedan huérfanos en `uploads`) y §14; `CLAUDE.md` (`attachments/`); bloque C1; cuaderno.

**Paso 82 · C1.7 · Gate**

1. `slice-gate.sh architecture tests/architecture/test_audit_module.py tests/architecture/test_audited_tables.py tests/architecture/test_audit_subject.py tests/architecture/test_no_cross_models.py tests/architecture/test_service_import_graph.py tests/architecture/test_crypto_bus_importers.py tests/architecture/test_reveal_single_door.py tests/architecture/test_no_plaintext_at_rest.py tests/architecture/test_third_party_confinement.py tests/architecture/test_no_physical_delete.py tests/architecture/test_no_trigger_tampering.py tests/architecture/test_reencryptor_registered_in_every_root.py tests/architecture/test_core_import_direction.py`.
2. `slice-gate.sh cli tests/cli/test_attachments_check.py tests/cli/test_init_keys_data_class.py`.
3. `slice-gate.sh main tests/architecture/test_reencryptor_registered_in_every_root.py`.
4. `slice-gate.sh crypto tests/crypto/test_reencryptor.py tests/crypto/test_registry.py`.
5. `slice-gate.sh core/audit tests/core/test_audit_hook_db.py tests/core/test_audit_serialize.py tests/core/test_chain_hash_vector.py`.
6. `database-reviewer` (`0023`, esquema, grants, índice, triggers) y `security-reviewer` (M-3, M-4, M-9, L-1, D76), en paralelo.
7. Sello: `slice-gate.sh attachments tests/attachments tests/migrations/test_0023_attachments.py tests/migrations/test_0022_audit_verifications_signatures.py tests/migrations/test_db_grants.py tests/migrations/test_triggers_siempre_activos.py`.

**Paso 83 · C1.8 · Docker y evidencia.** P-MIG 6 y 7 hechos; buildx (cambió `src`); recreación en desarrollo (+ `restart web`); `$DC run --rm tools init-keys --data-class attachment.sensitive --as <admin>` → fila `encrypt` A256GCM (en desarrollo `ensure_keys` también la habría creado al arrancar: se comprueba que no hay dos); `GET /crypto/keys` → 10 filas; `\dn attachments`; ensayo: `stop worker`, `migrate` → `0022 -> 0023`, `dbsetup` → «22 tablas clasificadas», `test_db_roles.sh`, recreación, `restart web`; `$DCEB run --rm tools attachments-check --as <admin>` → 0 filas, 0 objetos, salida 0; `GET /crypto/keys` en 8280 → 10 filas, la nueva `openbao`.

**Paso 84 · C1.9 · Checkpoint.** `"S6-C1 módulo attachments (0023): almacenamiento local atómico y S3 probado y apagado, cifrado por attachment.sensitive con tercera puerta, descarga con fila download tras descifrar, semáforo global, recifrado por el puerto Reencryptor y attachments-check"`.

### S6-C2 · Foto del socio: `POST` y `GET /members/{id}/attachments` (US-148)

- **Cierra:** parte de C4 (rutas, cuerpo crudo acotado con `?kind=`, `photo_attachment_id`), M-4 (`kind` y socio validados antes de leer un byte; `Content-Length` falso y `chunked`; sin spool; E1), M-6 (coach solo foto al subir), bug 8 (parte) y 23 (`api.upload`, en F4) de la exploración, D18 (rutas en `members`), D20 (`photo_attachment_id`), D22, D59, E8.
- **Depende de:** C1. **Migración:** ninguna.

**Paso 85 · C2.1 · Stubs y E8.** E8: cómo `members/router.py` y `service.py` arman la lista y la ficha (al cuaderno). Stubs: `modules/members/attachments.py` (privado: `async attach(session, member_id, *, kind, chunks, by) -> AttachmentOut`, `async list_attachments(session, member_id, page) -> Page[AttachmentOut]`, `async current_photo(session, member_ids) -> dict[UUID, UUID | None]`), reexportados por `members/service.py`; `members/router.py` (`POST /members/{member_id}/attachments?kind=` con `kind: Literal["photo","consent","other"]` como parámetro de consulta (422 de FastAPI antes del handler), `Request` crudo, `ensure_exists` y rol por `kind` antes de tocar el cuerpo, rechazo de `Content-Length` mayor que `ATTACHMENT_MAX_BYTES` sin leer, y `service.attach(..., chunks=request.stream())` (E1, D59); E13: el corte por trozos, el `Content-Length` falso, `chunked` y el iterador infinito se prueban por ASGI/`httpx` sin Nginx (paso 86); detrás de Nginx (`proxy_request_buffering on`) el api recibe `Content-Length` y el tope efectivo es el `6m` del `location`; `GET /members/{member_id}/attachments` paginado); `members/schemas.py` (`MemberDetailOut.photo_attachment_id: UUID | None`, `MemberListItem.photo_attachment_id`); `core/ratelimit.py` (`attachments-upload` con ruta); `PRIVATE_HELPERS["members"]` suma `attachments`; `ALLOWED_EDGES` suma `("members", "attachments")`.

**Paso 86 · C2.2 · Rojo**

- `tests/members/test_attach_photo.py` (E1; todas por ASGI/`httpx` directamente contra el api, sin Nginx, E13): 404 `member_not_found` para socio inexistente o de baja al subir (N-20); listado para socios de baja sigue; 422 `unsupported_type` con `field = "file"`; 413 `file_too_large` con `field = "file"` (D73); la foto nueva pasa a ser la vigente; coach sube `photo` (201) y recibe 403 con `?kind=consent` y `?kind=other` (M-6); socio 403; `?kind=x` o sin `kind` → 422 de FastAPI **antes de leer un solo byte** (el cuerpo es un iterador que cuenta: 0 trozos consumidos; `httpx` con `content=` generador); socio inexistente → 404 con 0 trozos consumidos; `Content-Length: 5242881` → 413 con 0 trozos; `Content-Length` falso que declara 10 y manda 5.242.881 → 413 al cortar en el byte 5.242.881 (el iterador no se consume más allá); `Content-Length` que declara 5.242.881 con un cuerpo de 100 bytes → 413 sin leer; `Transfer-Encoding: chunked` sin `Content-Length`: 5.242.880 → 201 y 5.242.881 → 413; `Content-Type` del cliente ignorado (`text/plain` con bytes JPEG → 201 `image/jpeg`); ningún campo de formulario existe (`sensitive` lo decide el servidor); un cuerpo de exactamente 5.242.880 → 201; `tempfile` nunca se llama durante la petición (medición del spool).
- `tests/members/test_router_attachments.py`: cuerpo crudo por `httpx` (`content=bytes` y `content=generador`); cubeta `attachments-upload` (11.ª en un minuto → 429); `no-store`; 201 con `AttachmentOut` sin `filename_random`; `GET` paginado con `limit`/`offset` y sin `q` (exclusión anotada, D57); roles; `tests/architecture/test_error_responses_in_openapi.py` describe el 413.
- `tests/members/test_list_photo_ids.py`: ficha con `photo_attachment_id`; lista de 50 socios con una sola consulta adicional (conteo de sentencias); nulo sin foto.
- Arquitectura: `test_no_cross_models.py` (`PRIVATE_HELPERS["members"]`), `test_service_import_graph.py` (`members → attachments`; `attachments` sin aristas), `test_writes_have_user_limit.py`, `test_user_limits_catalog.py` (quita `attachments-upload`), `test_error_codes_per_route.py` (422 nuevos, 404), `test_list_routes_use_page_params.py` (exclusión), `test_file_and_function_size.py` (`members/service.py` < 800; `router.py` < 400 o se parte en `members/router_attachments.py` privado con decisión).

**Paso 87 · C2.3 · Verde.** `members/{router,service,schemas,detail,attachments}.py`, `core/ratelimit.py`, `tests/architecture/_imports.py`.

**Paso 88 · C2.4 · Contrato y documentación.** P-API; `adjuntos.md` (foto: quién sube, tamaño, reemplazo); RUNBOOK §4; bloque C2; cuaderno.

**Paso 89 · C2.5 · Gate**

1. `slice-gate.sh architecture tests/architecture/test_no_cross_models.py tests/architecture/test_service_import_graph.py tests/architecture/test_writes_have_user_limit.py tests/architecture/test_user_limits_catalog.py tests/architecture/test_error_codes_per_route.py tests/architecture/test_list_routes_use_page_params.py tests/architecture/test_file_and_function_size.py`.
2. `security-reviewer` de C2 (M-4, M-6; nada se lee antes de validar).
3. Sello: `slice-gate.sh members tests/members/test_attach_photo.py tests/members/test_router_attachments.py tests/members/test_list_photo_ids.py tests/members/test_router_get.py tests/members/test_router_list.py tests/members/test_service_get.py tests/members/test_service_list.py`.

**Paso 90 · C2.6 · Docker, evidencia y checkpoint (demo 3, parte).** Buildx; recreación en desarrollo y ensayo (+ `restart web`). P-ADJ contra 8280 (a través de Nginx, cuerpo crudo con `?kind=photo`): `foto-5242880.jpg` → 201; `foto-5242881.jpg` → 413 `file_too_large` del api (cruzó Nginx: demuestra que el `5m` global del `server` no corta antes); la misma con `Transfer-Encoding: chunked` → 413 (Nginx reenvía con `Content-Length`, E13); `grande-6300000.bin` → 413 JSON de Nginx (mismo envelope); `?kind=x` con 5 MiB → 422 (Nginx ya leyó el cuerpo entero a su tmpfs: el «antes de leer» solo se observa por ASGI, paso 86); ELF renombrado `.jpg` → 422 `unsupported_type`; `ls -la /data/uploads/attachments` en el api (modo 600, nombre de 32 hex, dueño 10001); `GET /members/{id}` con `photo_attachment_id`; coach con `kind=consent` → 403. `checkpoint-commit.sh "S6-C2 foto del socio por cuerpo crudo acotado a 5 MiB con ?kind= validado antes de leer, POST y GET /members/{id}/attachments, photo_attachment_id en ficha y lista, coach solo foto"`.

### S6-C3 · Autorización de datos (US-149)

- **Cierra:** parte de C4 (consentimiento), M-11, bugs 8 (`data_consent_version`, arista `members → settings`) y 18 de la exploración, D19, D46, Q7, Q8.
- **Depende de:** C2. **Migración:** ninguna.

**Paso 91 · C3.1 · Stubs.** `members/rules.py` (`consent_required(today, consent_required_from) -> bool` pura; `CONSENT_MISSING_CONDITION` compartida por conteo, filtro y KPI); `members/service.create(..., *, enforce_consent: bool = True)` que consulta `settings.service.current_privacy_version()` y `consent_required_from` (arista `members → settings`); `members/changes.py` (el `PATCH` tardío con `data_consent: true` copia la versión vigente); `members/exceptions.PrivacyVersionMissing` (409 `privacy_version_missing`); `members/attachments.attach` con `kind = consent` fija `data_consent_at = now` y la versión si estaban nulos (auditoría `update` con antes y después); `imports/persist.py` y `seed/apply.py` llaman `create(enforce_consent=False)`.

**Paso 92 · C3.2 · Rojo**

- `tests/members/test_consent_required_pure.py`: fecha nula → falso; futura → falso; hoy → verdadero; pasada → verdadero.
- `tests/members/test_consent_create.py`: con `consent_required_from` vigente, `POST /members` sin `data_consent=true` → 422 `field = "data_consent_at"`; con `data_consent=true` → 201 y `data_consent_version = current_privacy_version()`; sin política publicada → 409 `privacy_version_missing`; `MemberCreate` no admite `data_consent_version` ni `enforce_consent` (422 por `extra`, M-11); sin corte (fecha nula) el alta sin consentimiento sigue dando 201 con `warnings = ["data_consent_missing"]` (Q16).
- `tests/members/test_consent_late_patch.py`: `PATCH` con `data_consent: true` sobre un socio sin autorización fija fecha y versión vigente; una versión enviada por el cliente se ignora o da 422; `MemberUpdated` sin valores; fila `update` con antes y después.
- `tests/members/test_consent_by_attachment.py`: subir `consent` a un socio sin autorización fija `data_consent_at` y la versión y deja `update`; con autorización previa no cambia nada; la foto no toca el consentimiento.
- `tests/imports/test_import_without_consent.py` y `tests/cli/test_seed_demo.py`: `import-members` con socios sin consentimiento y `seed --demo` siguen funcionando con el corte vigente.
- Arquitectura: `test_service_import_graph.py` (`members → settings`; sin ciclo), `test_error_codes_per_route.py` (409 nuevo), `test_no_cross_models.py`.

**Paso 93 · C3.3 · Verde.** `members/{rules,service,changes,schemas,exceptions,attachments}.py`, `imports/persist.py`, `seed/apply.py` (la única llamada con `enforce_consent=False` fuera de `cli.py`, como `enforce_retroactive_limit`, S4B-D33).

**Paso 94 · C3.4 · Contrato y documentación.** P-API (409 `privacy_version_missing`); RUNBOOK §4 y §14 (`consent_required_from` nulo no exige; fijarla es acción obligatoria del responsable del tratamiento; el KPI «Sin autorización» y el filtro como lista de trabajo, M-11); `instalar-en-servidor.md` (post-instalación: publicar la política y fijar la fecha); bloque C3; cuaderno.

**Paso 95 · C3.5 · Gate**

1. `slice-gate.sh architecture tests/architecture/test_service_import_graph.py tests/architecture/test_error_codes_per_route.py tests/architecture/test_no_cross_models.py`.
2. `slice-gate.sh cli tests/cli/test_seed_demo.py tests/cli/test_import_members.py`.
3. `security-reviewer` de C3 (M-11: `enforce_consent` nunca por HTTP; versión del cliente ignorada).
4. Sello: `slice-gate.sh members tests/members/test_consent_required_pure.py tests/members/test_consent_create.py tests/members/test_consent_late_patch.py tests/members/test_consent_by_attachment.py tests/members/test_service_create.py tests/members/test_router_create.py tests/members/test_service_update.py tests/imports/test_import_without_consent.py`.

**Paso 96 · C3.6 · Docker, evidencia y checkpoint.** Buildx; recreación. Ensayo: `PATCH /settings/privacy` con `consent_required_from` = hoy; `POST /members` sin `data_consent` → 422 `data_consent_at`; con `data_consent: true` → 201 y `data_consent_version` igual a la publicada; subir `consent` (PDF) a un socio antiguo sin autorización → `data_consent_at` fijado (fila `update` en `audit_log`); `$DCEB run --rm tools import-members --dry-run` de la plantilla con socios sin consentimiento → sigue; `PATCH /settings/privacy` de vuelta a nulo. `checkpoint-commit.sh "S6-C3 autorización de datos: consent_required pura, versión copiada de privacy, 409 privacy_version_missing, la autorización subida fija data_consent_at, import y seed exentos"`.

### S6-C4 · `GET /attachments/{id}`: descarga auditada y foto por streaming (US-150)

- **Cierra:** parte de C4 (descarga), M-3 (ruta), M-5 (cubeta `attachments-photo`, sin fila por vista), M-6 (descarga de sensibles solo admin), bug 17 de la exploración, D24, D37, D45, Q3, Q11.
- **Depende de:** C3. **Migración:** ninguna.

**Paso 97 · C4.1 · Stubs.** `modules/attachments/router.py` (`GET /attachments/{attachment_id}`: `require_role("admin", "coach")`; el service decide 403 para `consent`/`other` con coach); `core/http.file_stream(iterator, *, filename, media_type)` (misma cabecera que `file_download`); cubetas `attachments-download` (+ `-hour`) para sensibles y `attachments-photo` para `photo` (la cubeta se elige después de leer la fila, antes de descifrar).

**Paso 98 · C4.2 · Rojo**

- `tests/attachments/test_router_download.py`: admin descarga `consent` y `other` (200, `application/pdf` o la imagen); coach 403 en sensibles y 200 en `photo`; socio 403; 404 `attachment_not_found`; cabeceras `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Content-Disposition: attachment; filename="adjunto-<8 hex>.<ext>"`, `Content-Type` del `mime` guardado, `Content-Security-Policy: default-src 'none'; sandbox`; una sola fila `download` aunque el cliente corte tras las cabeceras; `photo` → sin fila; `custodio_sellado` → 503 `crypto_unavailable` sin fila (M-3); cubetas distintas para sensibles (`attachments-download`, 31.ª → 429) y foto (`attachments-photo`, 601.ª → 429); un socio de baja sigue descargable (N-20).
- `tests/attachments/test_download_streaming.py`: la foto sale por `stream` (el service nunca llama `get`); el pico de memoria de un sensible de 5 MiB medido con `tracemalloc` queda por debajo de 14 MiB (D24: unos 12 MiB estimados); `tests/attachments/test_semaphore.py`: cinco descargas sensibles concurrentes → una recibe 503 `busy` con `Retry-After: 1`.
- Arquitectura: `test_no_store_routes.py`, `test_every_route_has_role.py`, `test_user_limits_catalog.py` (quita `attachments-download`, `attachments-download-hour`, `attachments-photo`), `test_error_codes_per_route.py` (404 nuevo), `test_reveal_single_door.py` (sin puertas nuevas).

**Paso 99 · C4.3 · Verde.** `attachments/router.py` (< 400 líneas; el tope de 150 es solo de `cli_ops/`), `service.open` (cubeta y rol), `core/http.py`, `core/ratelimit.py`.

**Paso 100 · C4.4 · Contrato y documentación.** P-API; `adjuntos.md` (descarga, roles, auditoría, la foto sin fila por vista); ADR-007 cita `tests/attachments/test_router_download.py`; RUNBOOK §14; bloque C4; cuaderno.

**Paso 101 · C4.5 · Gate**

1. `slice-gate.sh core/http tests/core/test_http.py`.
2. `slice-gate.sh architecture tests/architecture/test_no_store_routes.py tests/architecture/test_every_route_has_role.py tests/architecture/test_user_limits_catalog.py tests/architecture/test_error_codes_per_route.py tests/architecture/test_reveal_single_door.py`.
3. `security-reviewer` de C4 (M-3, M-5, M-6; CSP de la respuesta; nada de `filename_random`).
4. Sello: `slice-gate.sh attachments tests/attachments/test_router_download.py tests/attachments/test_download_streaming.py tests/attachments/test_semaphore.py tests/attachments/test_service_open.py`.

**Paso 102 · C4.6 · Docker, evidencia y checkpoint (demo 3 completa).** Buildx; recreación. Ensayo (P-ADJ): subir `consent` PDF (admin) → `head -c 5` del objeto en el api = `apx1.` y `grep -c '%PDF' <objeto>` = 0; `GET /attachments/{id}` → `cmp` con el PDF original; `audit_log` una fila `download` con `subject_member_id`; `crypto_ops` `decrypt`; coach → 403; foto → 200 sin fila nueva; sellar OpenBao → sensible 503 `crypto_unavailable` y ninguna fila; foto sigue 200; desellar. `checkpoint-commit.sh "S6-C4 GET /attachments/{id}: descifrado en memoria con semáforo, fila download confirmada después de descifrar y antes de transmitir, foto por streaming sin fila con cubeta propia, consent y other solo admin"`.

### S6-C5 · Socios sin autorización y restauración con un adjunto (US-151)

- **Cierra:** parte de C4 (filtro, prueba de restauración), bug 18 (parte) de la exploración, D20, riesgo 5 del plan original (restauración con un adjunto).
- **Depende de:** C4. **Migración:** ninguna.

**Paso 103 · C5.1 · Rojo**

- `tests/members/test_filter_consent_missing.py`: `GET /members?consent=missing` usa `CONSENT_MISSING_CONDITION`; excluye bajas; coincide con `count_without_consent`; combinado con `q`, `status` y `membership_status`; paginación; valor distinto de `missing` → 422; `MemberExportQuery` gana el mismo filtro (`GET /members/export?consent=missing`).
- `tests/dashboard/test_consent_kpi.py`: `members_without_consent` igual al total del filtro.
- `infra/tests/restore_e2e.sh`: en `apex-smoke` sube una foto y un `consent` sensible por la API, corre `run.sh`, restaura con `restore.sh` en una pila limpia, descarga los dos y compara con `cmp` (el sensible se descifra con las llaves restauradas); `infra/backup/tests/test_scripts_static.sh` cubre el `bash -n`.

**Paso 104 · C5.2 · Verde.** `members/{rules,service,router,schemas,exports}.py`; `infra/tests/restore_e2e.sh`.

**Paso 105 · C5.3 · Contrato y documentación.** P-API; `respaldo-y-restauracion.md` (la prueba con adjuntos); RUNBOOK §4; bloque C5; cuaderno.

**Paso 106 · C5.4 · Gate**

1. `slice-gate.sh dashboard tests/dashboard/test_consent_kpi.py tests/dashboard/test_service.py`.
2. `bash scripts/ci/test_infra_scripts.sh && bash infra/backup/tests/test_scripts_static.sh`.
3. `security-reviewer` de C5.
4. Sello: `slice-gate.sh members tests/members/test_filter_consent_missing.py tests/members/test_router_list.py tests/members/test_router_list_filters.py tests/members/test_service_list.py tests/members/test_export.py tests/members/test_count_without_consent.py`.
5. Después del sello: `run-gates.sh` (segunda de cuatro).

**Paso 107 · C5.5 · Docker, evidencia y checkpoint.** Buildx; recreación. Ensayo: `GET /members?consent=missing` y `GET /dashboard` con el mismo conteo; `restore_e2e.sh` en `apex-smoke` desde el auxiliar Linux → verde con los dos adjuntos; `down -v` del smoke; re-etiquetar imágenes. `checkpoint-commit.sh "S6-C5 filtro consent=missing compartido con el KPI y la exportación, y restauración de respaldo con un adjunto sensible descifrable"`. **Desde aquí nace el worktree del front (sección 3).**

### S6-R1 · Rotación desde la pantalla, `0024` y grants acotados (US-145)

- **Cierra:** C5 completa, C6 (decisión aplicada y revisada), H-2 (tres condiciones), L-3 (`retire-key` y respaldo), bugs 4 (impacto) y 7, 8 (exploración), D15, D26 (recifrado real), D35, D40 (`migrate-provider` con `sign`), D43, D61, D69 (409 en la ruta), D74, E5, E7 (reanudación), Q6.
- **Depende de:** C5. **Migración:** `0024_crypto_rotation_from_api`.

**Paso 108 · R1.1 · P-MIG, verificación y stubs**

- P-MIG pasos 1 y 2: volcado `antes-0024`; `stop api worker`.
- E5: qué partes de `cli_ops/rotate_key.py` (`_rotate_data`, `_retry`, `_fail`) pasan a `rotate_job.py`; al cuaderno.
- Stubs: `core/crypto/rotate_job.py` (`ROTATION_SLOTS = 1`, `ROTATION_MAX_S = 3600`, `BATCH_ROWS = 500`, `BATCH_FILES = 50`, `rotation_engine(settings) -> AsyncEngine`, `async run_rotation(session_factory, job_id, *, batch_size=None) -> None`, `async resume_running_jobs(session_factory)`); `core/crypto/inventory.py` (`validate_rotation_request(reason, confirm) -> None` pura; `async start_from_screen(session, key_id, *, reason, by) -> RotationStarted`); `schemas.py` (`RotateIn(reason, confirm)`, `RotationStartedOut(job_id, new_key_id, previous_key_id)`); `router.py` (`POST /crypto/keys/{key_id}/rotate` 202; cubeta `keys-rotate` y `keys-rotate-hour`); `main.py` (`resume_running_jobs` en el `lifespan` si el keyring está cargado; `app.state.rotation_task`); `cli_ops/rotate_key.py` llama `run_rotation` (bajo 260); `cli_ops/retire_key.py` (cuenta `attachments.key_id`; manifiesto posterior al `finished_at`, D74; bajo 200); migración `0024` (guarda de `crypto_keys` por rol, triggers `guard_jobs_update` y `guard_jobs_insert`, D61; nada sobre filas `sign`, E2).

**Paso 109 · R1.2 · Rojo de migración y grants**

- `tests/migrations/test_0024_crypto_rotation_from_api.py`, sobre `apex_roles` con el rol real `apex_api`: `active → decrypt_only` con otra fila `active` de versión mayor y un job `running` de la clase → pasa; sin la fila nueva → falla; sin job `running` → falla; `purpose` `index` o `sign` → falla; `rotated_by = SYSTEM_USER_ID` o nulo → falla; `active → retired` → falla; `decrypt_only → active` → falla; cualquier cambio de `provider`, `wrapped_material`, `version`, `data_class` por `apex_api` → falla; `crypto_jobs` (`guard_jobs_insert`, E6): `INSERT` como `apex_api` con `kind = rotate`, `status = running`, `data_class` no nula, `total > 0`, `done = 0`, `error` nulo y `created_by` real → pasa; `status = pending` o `done` → falla; `total = 0` → falla; `done > 0` → falla; `kind = migrate_provider` → falla; `created_by = SYSTEM_USER_ID` → falla; un segundo job `running` de la misma clase → falla por `uq_crypto_jobs_in_progress`; como propietario todo pasa (el CLI no cambia); (`guard_jobs_update`) `UPDATE` de `done`, `status`, `error`, `started_at`, `finished_at`, `updated_at` pasa; `done` decreciente → falla; `total` cambiado → falla; `status = done` con `done <> total` → falla; `UPDATE` de `kind` o `data_class` → falla por grant; una fila `sign` no se ve afectada: la guarda de `0015` sigue admitiendo `local → openbao` con referencia nueva como propietario y `apex_api` sigue sin poder tocarla (E2); `downgrade` restaura el cuerpo de `0015` (`pg_get_functiondef`) y borra `guard_jobs_update` y `guard_jobs_insert`; `tgenabled = 'A'` en los tres; ciclo; `test_0023_*` pasa a «en la cadena».
- `tests/migrations/test_db_grants.py`: `apex_api` con `S I U (done, status, error, started_at, finished_at, updated_at)` en `crypto.crypto_jobs` y `U (state, rotated_at, rotated_by, updated_at)` en `crypto.crypto_keys`; el resto sin cambio; `revoke.sql`; las tres listas; `tests/migrations/test_api_role_paths.py` gana `start_from_screen` y `run_rotation` como `apex_api`.

**Paso 110 · R1.3 · Rojo**

- `tests/crypto/test_rotate_from_screen.py`: con 1.200 socios (`socios_cifrados`) rotar `member.document` por `POST /crypto/keys/{id}/rotate` con `{"reason": "sospecha", "confirm": "ROTAR"}` → 202 con `job_id`, `new_key_id`, `previous_key_id`; en la misma transacción la nueva `active` (versión + 1), la anterior `decrypt_only`, el `CryptoJob` y la fila `update` sobre `crypto.crypto_keys` con `reason`, `data_class`, `state` y sin `wrapped_material`; lectura durante el recifrado (fila vieja y nueva descifran); `GET /crypto/jobs` con `percent` creciente; al terminar `done`, `count_pending = 0`, tres lotes de 500 con el mismo `batch_id` por lote; 409 `key_not_active` (`decrypt_only`), `purpose_not_rotatable` (`index`, `sign`), `rotation_running` (job abierto de la clase o `ROTATION_SLOTS` ocupado por otra clase), `rotation_not_supported` (clase sin columnas ni puerto); 422 con `field` `confirm` (`rotar`, ` ROTAR`) o `reason` (vacío, 501 caracteres); 404; 503 `crypto_unavailable`; cubeta `keys-rotate` (4.º en un minuto → 429); un error de lote (`reencrypt_batch` parcheado) → `failed` con un código y la anterior sigue `decrypt_only`; reanudar con el mismo `POST` → 202 y continúa; `ROTATION_MAX_S` superado (reloj inyectado) → `failed` `timeout`; reinicio con un job `running` y keyring cargado → `resume_running_jobs` lo termina; sin keyring → lo anota y no lo toca.
- `tests/crypto/test_rotate_attachment_class.py`: rotar `attachment.sensitive` con 120 adjuntos sensibles → tres lotes de 50, objetos recifrados (cada uno descifra con la nueva), `key_id` actualizado, `count_pending = 0`; un objeto nuevo con `key_id` viejo (corte simulado) se recifra en el siguiente lote.
- `tests/crypto/test_rotate_audit_row.py`: la fila de auditoría no contiene `wrapped_material`, `vault:` ni referencias; `record_id = key_id`; (E5) una rotación completa deja **exactamente una** fila `update` sobre `crypto.crypto_keys` en `audit_log` (conteo antes y después: `crypto_keys` no es `__audited__` y entrar en `AUDITABLE_TABLES` no activa el hook), y `GET /audit?table=crypto.crypto_keys` la devuelve.
- `tests/crypto/test_rotation_engine.py`: durante una rotación el pool principal conserva sus conexiones (`motor_dedicado_contado`); el candado `apex:rotate:<clase>` vive en la conexión dedicada; la tarea se cancela limpiamente en el `finally` del `lifespan`.
- `tests/cli/test_rotate_key_cli.py`, `tests/crypto/test_rotate.py`, `test_rotate_concurrency.py`, `test_rotate_index.py`: sin regresión con `run_rotation`; `rotate-key attachment.sensitive` ahora sale 0.
- `tests/cli/test_retire_key_cli.py` y `tests/crypto/test_retire_key.py`: cuenta `attachments.key_id`; sin manifiesto posterior al `finished_at` del job → 2 `backup_older_than_rotation`.
- Arquitectura: `test_file_and_function_size.py` (las funciones de rotación < 50 líneas; `rotate_job.py` < 400), `test_user_limits_catalog.py` (quita `keys-rotate` y `keys-rotate-hour`), `test_writes_have_user_limit.py`, `test_error_codes_per_route.py` (cuatro 409 y los 422), `test_core_import_direction.py` (`rotate_job.py` sin módulos), `test_no_direct_now.py` (la tarea usa `current_clock()`), `test_sql_literals_constant.py` (sin candados nuevos).

**Paso 111 · R1.4 · Verde de `0024`.** P-MIG pasos 3 a 8 (`\df+ crypto.guard_keys_update`, `\df+ crypto.guard_jobs_update`); `grants.sql`, `revoke.sql`, `test_db_grants.py` (P-ROL); `AUDITABLE_TABLES` suma `crypto.crypto_keys`.

**Paso 112 · R1.5 · Verde de código.** Archivos del paso 108; `core/crypto/service.py` sin crecer; `cli_ops/rotate_key.py` bajo 260 y `retire_key.py` bajo 200 (`TOPE_CLI_OPS` real, D80); `main.py`.

**Paso 113 · R1.6 · Contrato y documentación.** P-API (`POST /crypto/keys/{id}/rotate`); `llaves.md` (rotar desde la pantalla; qué pasa si falla; retirar sigue en el CLI con manifiesto posterior; **residual de E6**: lo que un api comprometido podría hacer con `INSERT` en `crypto_keys` y `crypto_jobs`, por qué ningún dato queda ilegible y cómo se detecta en Trabajos y en la bitácora); `rotar-llave.md` (CLI y pantalla comparten `run_rotation`; `attachment.sensitive` rotable); RUNBOOK §6 (rollback de `0024`) y §14 (job huérfano tras un reinicio, reanudación); `CLAUDE.md`; bloque R1 (precisión de H-2 (2), D61); cuaderno.

**Paso 114 · R1.7 · Gate**

1. `slice-gate.sh cli tests/cli/test_rotate_key_cli.py tests/cli/test_migrate_provider_cli.py tests/cli/test_retire_key_cli.py`.
2. `slice-gate.sh main tests/crypto/test_rotate_from_screen.py tests/core/test_startup_failure.py`.
3. `slice-gate.sh attachments tests/attachments/test_reencrypt.py`.
4. `slice-gate.sh architecture tests/architecture/test_file_and_function_size.py tests/architecture/test_user_limits_catalog.py tests/architecture/test_writes_have_user_limit.py tests/architecture/test_error_codes_per_route.py tests/architecture/test_core_import_direction.py tests/architecture/test_no_direct_now.py`.
5. `database-reviewer` (`0024`, grants por columna, `guard_jobs_update`) y `security-reviewer` (H-2: las tres condiciones y la precisión de D61; un RCE del api no puede dejar la clase sin llave activa ni cerrar un job sin recifrar), en paralelo.
6. Sello: `slice-gate.sh crypto tests/crypto/test_rotate_from_screen.py tests/crypto/test_rotate_attachment_class.py tests/crypto/test_rotate_audit_row.py tests/crypto/test_rotation_engine.py tests/crypto/test_rotate.py tests/crypto/test_rotate_concurrency.py tests/crypto/test_rotate_index.py tests/crypto/test_migrate_provider.py tests/crypto/test_retire_key.py tests/migrations/test_0024_crypto_rotation_from_api.py tests/migrations/test_0023_attachments.py tests/migrations/test_db_grants.py tests/migrations/test_api_role_paths.py`.

**Paso 115 · R1.8 · Docker y evidencia (demo 2 completa)**

1. P-MIG 6 y 7 hechos; buildx; recreación en desarrollo (+ `restart web`); ensayo: `stop worker`, `migrate` → `0023 -> 0024`, `dbsetup` («22 tablas clasificadas», grants nuevos), `test_db_roles.sh`, recreación, `restart web`; como `apex_api` en el ensayo: `BEGIN; UPDATE crypto.crypto_keys SET state = 'retired' WHERE state = 'active' LIMIT 1; ROLLBACK;` → falla por la guarda (evidencia de solo lectura).
2. Rotar `member.document` desde la API en 8280 (`ROTAR`) → 202; `GET /members/{id}` durante la rotación → 200; `GET /crypto/jobs` → `percent` y `done`; `crypto_keys`: versión 2 `active`, versión 1 `decrypt_only`; `audit_log` `update` sin material.
3. Rotar `attachment.sensitive` (los adjuntos de C4) → `done`; `attachments.key_id` todos con la nueva; `GET /attachments/{id}` descifra.
4. `retire-key` de la versión 1 de `member.document` → 2 `backup_older_than_rotation`; `run.sh` (manifiesto nuevo con instantánea); `retire-key … --confirm-audit-blobs N` → `retired`.
5. `--run-once sign_audit` sigue en `ok`; `docker stats`.

**Paso 116 · R1.9 · Checkpoint.** `"S6-R1 rotación desde la pantalla (0024): guarda de crypto_keys con las tres condiciones de H-2 y guard_jobs_update, api con grants acotados, rotador único con conexión dedicada y reanudación, recifrado de adjuntos, migrate-provider con filas sign y retire-key con manifiesto posterior"`.

### S6-E1 · Origen público, CORS y cookie coherentes con `APEX_DOMAIN` (US-153)

- **Cierra:** US-153 criterios 4, 5 y 7, bug 11 (`cookie_secure`, `LAN_ORIGIN`) y 13 de la exploración, D28, D65, D77, riesgo 4 (prueba del limitador en el api).
- **Depende de:** R1. **Migración:** ninguna.

**Paso 117 · E1.1 · Stubs.** `core/config.py` (`public_origin(settings) -> str`, `validate_origins(settings) -> None`, `cookie_secure(settings) -> bool`; `Settings` llama `validate_origins` en su validador final); `modules/auth/cookies.py` usa `cookie_secure(settings)`; `main.create_app()` arma CORS con `CORS_ORIGINS` más `public_origin`.

**Paso 118 · E1.2 · Rojo**

- `tests/core/test_public_origin.py`: LAN → `FRONT_BASE_URL`; dominio → `https://apex.example.com`; con puerto → `https://apex.localhost:8443` (D77); `validate_origins` con dominio falla nombrando la variable ante `CORS_ORIGINS` con `http:`, `FRONT_BASE_URL` distinta de `public_origin`, `COOKIE_SECURE=false`, `ALLOW_INSECURE_COOKIE=true`; sin dominio todo sigue como en S4B-D154 (producción exige `COOKIE_SECURE` salvo `ALLOW_INSECURE_COOKIE`); `cookie_secure` devuelve `COOKIE_SECURE`.
- `tests/auth/test_cookie_secure_modes.py`: la cookie de `refresh` lleva `Secure` con `settings_dominio()` y no la lleva con `settings_lan()`; `SameSite=Strict` en ambos.
- `tests/core/test_cors.py` (existente, ampliado): con dominio, `Origin: https://apex.example.com` aceptado; `http://apex.example.com` y otro origen rechazados; sin dominio, `CORS_ORIGINS` como hoy.
- `tests/core/test_limiter_behind_proxies.py`: con `TRUSTED_PROXIES` solo Nginx, `X-Forwarded-For: 203.0.113.9, <nginx>` cuenta a `203.0.113.9`; una cadena con la IP de Caddy en medio no amplía la confianza (Caddy no está en `TRUSTED_PROXIES`: Nginx ya restauró la IP real y el api solo salta a Nginx).
- `tests/core/test_config.py` y `test_env_example.py` (sin variables nuevas; se verifica); `tests/core/test_config_error_message.py` (el mensaje nombra la variable).

**Paso 119 · E1.3 · Verde.** `core/config.py`, `auth/cookies.py`, `main.py`, `.env.example` (comentarios de `APEX_DOMAIN`, `FRONT_BASE_URL` y `COOKIE_SECURE` con dominio).

**Paso 120 · E1.4 · Documentación.** `tls.md` (sección de variables del api y los dos modos; mensajes de arranque); `instalar-en-servidor.md`; RUNBOOK §14; bloque E1; cuaderno.

**Paso 121 · E1.5 · Gate**

1. `slice-gate.sh auth tests/auth/test_cookie_secure_modes.py tests/auth/test_login_router.py tests/auth/test_refresh_router.py`.
2. `slice-gate.sh main tests/core/test_cors.py`.
3. `slice-gate.sh core/ratelimit tests/core/test_limiter_behind_proxies.py tests/core/test_ratelimit.py`.
4. `security-reviewer` de E1 (sin ampliar `TRUSTED_PROXIES`; cookie `Secure` con dominio; CORS sin `http:`).
5. Sello: `slice-gate.sh core/config tests/core/test_public_origin.py tests/core/test_config.py tests/core/test_env_example.py tests/core/test_config_error_message.py`.
6. Después del sello: `run-gates.sh` (tercera de cuatro).

**Paso 122 · E1.6 · Docker, evidencia y checkpoint (demo 4 completa).** Buildx; recreación en desarrollo. Ensayo en modo dominio: `.env` con `APEX_DOMAIN=apex.localhost:8443`, `FRONT_BASE_URL=https://apex.localhost:8443`, `COOKIE_SECURE=true`, `ALLOW_INSECURE_COOKIE=false`; `$DCET up -d --no-build --force-recreate api worker web caddy` + `restart web`; `bash scripts/ci/tls-smoke.sh --dc "$DCET"` completo (incluida la cookie `Secure` y CORS); un `.env` con `CORS_ORIGINS=http://otro` → el api sale con el mensaje que nombra la variable (`$DCET run --rm --no-deps api python -c 'from app.core.config import get_settings; get_settings()'`); vuelta al modo LAN (`.env` restaurado con `cmp`, `$DCET stop caddy`, `$DCEB up -d --no-build --force-recreate api worker web`) y `tls-smoke.sh --lan` → sin HSTS, cookie sin `Secure`. `checkpoint-commit.sh "S6-E1 public_origin y validate_origins: CORS y cookie coherentes con APEX_DOMAIN sin romper COOKIE_SECURE ni ALLOW_INSECURE_COOKIE, limitador por la IP real detrás de Caddy y Nginx"`.

## 6. Front (worktree `.claude/worktrees/sprint-06-front`; S6-F1, F3, F4, F5, F2)

**Reglas comunes:**

- `docs/design/` manda (`DESIGN.md`, `ROUTES.md`, `Auditoria.html`, `Llaves.html`, `Socio_Ficha.html`, `Socio_Form.html`, `Inicio.html` y sus `.dark.html`). Solo tokens; componentes compartidos en `shared/ui` (`Tabs`, `DataTable`, `ConfirmModal`, `StatusTag`, `KpiCard`, `FilterBar`, `Pagination`, `SidePanel`, `CustodyNotice` existen); datos compartidos en `shared/data`; una feature nunca importa otra; React Hook Form con Zod; TanStack Query; `// DESIGN-GAP:` cuando falte algo.
- Vitest por página y componente, en claro y oscuro. Gate sellante: `SLICE_BASE=$(git merge-base HEAD main) bash scripts/workflow/slice-gate.sh web/<feature> <archivos>`. `security-reviewer` en cada F.
- `features.test.ts` pasa a 11 en F2 (`crypto`). Antes de cada F: `git rebase feat/sprint-06-auditoria-firmada-llaves-adjuntos-tls` y `npm run gen:api` (sin diff).
- `api.blob` (S5-F4) gana en F3 los tipos `image/jpeg`, `image/png` y `application/json` en `BLOB_CONTENT_TYPES` y `BLOB_ACCEPT`; `api.upload(path, file: File, {kind, timeoutMs: 30000})` nace en F4 en `core/api/client.ts`: `fetch` con `body: file`, `Content-Type: file.type || "application/octet-stream"` y `?kind=` en la URL (cuerpo crudo, E1; sin `FormData`), respetando la regla ESLint que prohíbe `fetch` directo (E12).

### S6-F1 · Estado de la firma en Auditoría (US-142)

**Paso 123 · F1.1 · Preparación.** Crear el worktree y la rama, `npm ci`, cuaderno `docs/scratch/sprint-06-front.md`; `npm run gen:api` sin diff.

**Paso 124 · F1.2 · Rojo.** `features/system/api.test.tsx` (`useLatestSignature()` y el tipo ampliado de `useVerifyChain()`); `components/SignatureStatus.test.tsx` (texto «Última firma válida: seq N · <fecha de Bogotá> · Ed25519»; `StatusTag` de texto para los cuatro estados: Íntegra, Alterada, Firma atrasada, Sin firmas (sin «no verificable»: la verificación no depende del custodio, D81); sin colores literales); `VerifyChainButton.test.tsx` (muestra `signatures_checked`, `signatures_valid`, `first_invalid_signature_seq`; con el custodio sellado la verificación sigue completa y solo el aviso global `CustodyNotice` de S5-F5 informa del sellado; el `DESIGN-GAP` de «ML-DSA» se cierra con el texto real `Ed25519`); `AuditPage.test.tsx` (el bloque arriba del botón, claro y oscuro).

**Paso 125 · F1.3 · Verde.** `features/system/{api,schemas}.ts`, `components/SignatureStatus.tsx`, `VerifyChainButton.tsx`, `pages/AuditPage.tsx`.

**Paso 126 · F1.4 · E2E.** `web/tests/e2e/audit.spec.ts` (preview: los cinco estados) y `web/tests/e2e/stack/audit-signature.spec.ts` (contra el ensayo, en V7: firma presente tras `--run-once sign_audit`, «Verificar» muestra firmas válidas).

**Paso 127 · F1.5 · Documentación.** BRECHAS §14 (filas de F1; cierre de la fila 15 de la firma) y el cuaderno del front.

**Paso 128 · F1.6 · Gate y checkpoint.** `security-reviewer`; sello: `slice-gate.sh web/system src/features/system/components/SignatureStatus.test.tsx src/features/system/components/VerifyChainButton.test.tsx src/features/system/pages/AuditPage.test.tsx src/features/system/api.test.tsx`. Checkpoint (en el worktree): `"S6-F1 estado de la firma en Auditoría con los cinco estados y verificación con firmas"`.

### S6-F3 · Ficha del socio: foto y pestaña Adjuntos (US-148, US-150)

**Paso 129 · F3.1 · Rojo.** `features/attachments/pages/AttachmentsTab.test.tsx` (ruta hija `/socios/:id/adjuntos` registrada en `isPageAvailable` y en `MemberDetailPage` sin `disabledUntil`; tabla de tipo, fecha de Bogotá, tamaño legible y quién subió; «Descargar» por `api.blob` y `downloadBlob` con `a[download]`, nunca `window.open` ni `blob:` en pestaña para PDF (L-2); vacío «Este socio no tiene adjuntos»; estados de carga y error; con rol coach el botón «Descargar» no aparece en `consent`/`other` (M-6) y el 403 del api se muestra si llega); `shared/data/memberPhoto.test.ts` (hook `useMemberPhoto(photoAttachmentId)`: baja la foto con el token por `api.blob`, crea `blob:` en memoria, lo revoca al desmontar y al cambiar de id, nada en `localStorage`/`sessionStorage`; con id nulo no pide nada); `features/members/components/MemberPhoto.test.tsx` (miniatura del encabezado y de la lista con `alt` fijo y marcador sin foto); `core/api/client.test.ts` (`BLOB_CONTENT_TYPES` con `image/jpeg`, `image/png`, `application/json`).

**Paso 130 · F3.2 · Verde.** `features/attachments/{api,schemas}.ts`, `pages/AttachmentsTab.tsx`, `shared/data/memberPhoto.ts`, `features/members/components/MemberPhoto.tsx`, `MemberDetailPage.tsx`, `MembersListPage.tsx`, `core/api/client.ts`, `config/features.ts` (`attachments` no es feature aparte: la pestaña vive bajo `members` como `notifications` en S3-D65; se anota).

**Paso 131 · F3.3 · E2E.** `member-tabs.spec.ts` (pestaña Adjuntos en preview) y `stack/members-attachments.spec.ts` (descarga de la autorización contra el ensayo, en V7).

**Paso 132 · F3.4 · Documentación.** BRECHAS §14 y el cuaderno del front.

**Paso 133 · F3.5 · Gate y checkpoint.** `slice-gate.sh web/shared src/shared/data/memberPhoto.test.ts`; `slice-gate.sh web/core src/core/api/client.test.ts`; `slice-gate.sh web/members src/features/members/components/MemberPhoto.test.tsx src/features/members/pages/MemberDetailPage.test.tsx`; `security-reviewer`; sello: `slice-gate.sh web/attachments src/features/attachments/pages/AttachmentsTab.test.tsx`. Checkpoint: `"S6-F3 pestaña Adjuntos con descarga por api.blob y miniatura de la foto por blob en memoria"`.

### S6-F4 · Alta y edición del socio: foto y autorización (US-148, US-149)

**Paso 134 · F4.1 · Rojo.** `core/api/client.test.ts` (`api.upload(path, file, {kind})`: `fetch` con `body: file`, `?kind=photo|consent|other` en la URL, `Content-Type` igual a `file.type` o `application/octet-stream`, sin `FormData`, `timeoutMs` 30 s; 413 `file_too_large` (venga de Nginx o del api, mismo mensaje), 422 `unsupported_type`, 503 con el mensaje del api; cumple la regla `no-direct-fetch`; E1); `features/members/components/PhotoField.test.tsx` (`// DESIGN-GAP:` porque `Socio_Form.html` no trae el campo; vista previa; valida tipo y 5 MB en el cliente con «La foto supera 5 MB» sin perder el formulario; al crear, sube la foto después del `POST /members` y, si falla, avisa «El socio quedó creado sin foto» y conserva el id; al editar, reemplaza); `ConsentSection.test.tsx` (casilla existente; fecha de aceptación «ahora en Bogotá» de solo lectura; versión vigente de solo lectura desde `settings/privacy` o «versión no registrada»; archivo opcional del documento firmado (PDF o imagen) subido como `kind=consent` tras guardar; el 422 de `data_consent_at` se muestra en el campo); `schemas.test.ts` (Zod de los dos campos); `MemberFormPage.test.tsx` en claro y oscuro.

**Paso 135 · F4.2 · Verde.** `core/api/client.ts` (`api.upload` por cuerpo crudo), `features/members/components/{PhotoField,ConsentSection}.tsx`, `features/members/{api,schemas}.ts` (`subirAdjunto(memberId, kind, file)`), el formulario.

**Paso 136 · F4.3 · E2E.** `members.spec.ts` (preview) y `stack/members-photo.spec.ts` (contra el ensayo a través de Nginx: 5.242.880 pasa y 5.242.881 muestra el mensaje; en V7).

**Paso 137 · F4.4 · Documentación.** BRECHAS §14 (`DESIGN-GAP` del campo de foto) y el cuaderno del front.

**Paso 138 · F4.5 · Gate y checkpoint.** `slice-gate.sh web/core src/core/api/client.test.ts`; `security-reviewer`; sello: `slice-gate.sh web/members src/features/members/components/PhotoField.test.tsx src/features/members/components/ConsentSection.test.tsx src/features/members/schemas.test.ts`. Checkpoint: `"S6-F4 foto y autorización en el alta y la edición con api.upload acotado y el 422 de data_consent_at en el campo"`.

### S6-F5 · Inicio y Config (US-151, US-153 en textos)

**Paso 139 · F5.1 · Rojo.** `features/dashboard/components/NotificationKpis.test.tsx` o `KpiCard` (la tarjeta «Sin consentimiento» pasa a «Sin autorización» con enlace a `/socios?consent=missing`; «Todos con autorización» en 0); `features/members/pages/MembersListPage.test.tsx` (la URL `?consent=missing` se lee y se muestra como chip en la `FilterBar`; quitar el chip limpia la URL); `features/system/components/PrivacySettingsForm.test.tsx` (texto de ayuda «desde esa fecha el alta exige la autorización de datos»; el campo ya existe).

**Paso 140 · F5.2 · Verde.** Los tres componentes y `features/members/api.ts` (`consent` en la consulta).

**Paso 141 · F5.3 · E2E.** `home.spec.ts` (enlace de la tarjeta) y `members.spec.ts` (chip) en preview; `stack/home.spec.ts` suma el conteo contra `/members?consent=missing` (V7).

**Paso 142 · F5.4 · Documentación.** BRECHAS §14 (fila 13.24 cerrada) y el cuaderno del front.

**Paso 143 · F5.5 · Gate y checkpoint.** `slice-gate.sh web/dashboard src/features/dashboard/components/NotificationKpis.test.tsx`; `slice-gate.sh web/system src/features/system/components/PrivacySettingsForm.test.tsx`; `security-reviewer`; sello: `slice-gate.sh web/members src/features/members/pages/MembersListPage.test.tsx`. Checkpoint: `"S6-F5 tarjeta Sin autorización con enlace al filtro consent=missing y texto de ayuda de la fecha de corte"`.

### S6-F2 · Pantalla Llaves (US-143 a US-146); empieza tras el checkpoint de R1

**Paso 144 · F2.1 · Rebase y contrato.** `git rebase`, `npm run gen:api` sin diff.

**Paso 145 · F2.2 · Rojo.** `config/features.test.ts` (`crypto` habilitada, 11 en total; `/sistema/llaves` con `load` y en el menú Sistema solo para admin); `features/system/pages/KeysPage.test.tsx` (`Tabs` Inventario, Bitácora, Trabajos; «Exportar CBOM» en el `PageHeader`; tarjetas de resumen con `active_count`, `operations_today`, `running_jobs` y «Proveedor activo: <nombre> · <estado>» desde `summary`; «Rotación vencida (30 días)» como `// DESIGN-GAP:` y se muestra `age_days`); `components/KeysInventory.test.tsx` (`DataTable` con filtros de propósito, estado y proveedor en la URL, `StatusTag` de texto, hora de Bogotá, `records_count` o «n/a», botón «Rotar» solo en filas `active` de propósito `encrypt`, nunca en `index` ni `sign`); `CryptoOpsLog.test.tsx` (filtros de fecha con `check_instant_range` en el cliente, `Pagination` con `offset`); `CryptoJobs.test.tsx` (barra de progreso con el porcentaje en texto; `refetchInterval` de 5 s solo mientras haya un job `running`, con temporizadores falsos; se detiene al terminar); `RotateKeyModal.test.tsx` (`ConfirmModal` con la clase, `records_count`, motivo de 3 a 500 y campo «Escribe ROTAR»; confirmar deshabilitado hasta el texto exacto; al 202 salta a Trabajos; 409 y 422 con el mensaje del api; 503 con el aviso de custodio); `ExportCbomButton.test.tsx` (`api.blob` con el nombre del api sanitizado y `downloadBlob`; 429 con mensaje).

**Paso 146 · F2.3 · Verde.** `config/{features,routeTable}.ts`, `features/system/pages/KeysPage.tsx`, `components/{KeysInventory,CryptoOpsLog,CryptoJobs,RotateKeyModal,ExportCbomButton}.tsx`, `features/system/{api,schemas}.ts`.

**Paso 147 · F2.4 · E2E.** `web/tests/e2e/keys.spec.ts` (preview: tabla, modal) y `stack/keys-rotate.spec.ts` (rotación de `member.phone` desde la pantalla contra el ensayo con lectura de un socio durante el proceso; CBOM descargado; en V7).

**Paso 148 · F2.5 · Documentación.** BRECHAS §14 (filas de Llaves; `DESIGN-GAP` de rotación vencida) y el cuaderno del front.

**Paso 149 · F2.6 · Gate.** `slice-gate.sh web/core src/config/features.test.ts`; `security-reviewer` (ningún material en el estado ni en la caché; `gcTime` corto para el CBOM); sello: `slice-gate.sh web/system src/features/system/pages/KeysPage.test.tsx src/features/system/components/KeysInventory.test.tsx src/features/system/components/CryptoOpsLog.test.tsx src/features/system/components/CryptoJobs.test.tsx src/features/system/components/RotateKeyModal.test.tsx src/features/system/components/ExportCbomButton.test.tsx`.

**Paso 150 · F2.7 · Checkpoint.** `"S6-F2 pantalla Llaves: inventario sin material, bitácora, trabajos con progreso, rotar con ROTAR exacto y exportar CBOM"`.

## 7. Validación del sprint

Evidencia en `docs/scratch/sprint-06.md`, bloque «Validación V1–V12», sin credenciales, llaves ni la CA interna. Las demos 1 a 4 de `SPRINT-06.md` son V3 a V6, paso a paso.

**V1 · Fusión y documentos**

1. Fusionar `feat/sprint-06-front` con el árbol limpio tras un checkpoint (`GIT_EDITOR=true git merge --continue` si el hook falla, o lotes de 40 archivos). `npm run gen:api` y la prueba de contrato sin deriva. `git worktree remove`.
2. `grep -rn "DESIGN-GAP" web/src` contra BRECHAS §14 (campo de foto; rotación vencida; cualquiera nuevo con fila).
3. Documentos al día: `CLAUDE.md`, RUNBOOK (§4, §6, §7, §9, §11 a §14), `SPRINT-06.md`, DECISIONES (bloques por slice), `CHANGELOG.md`, `docs/operacion/{llaves,adjuntos,tls,openbao,rotar-llave,respaldo-y-restauracion,instalar-en-servidor,actualizar}.md`, ADR-006 y ADR-007 (todas las rutas de prueba citadas existen).
4. Criterio: `grep -rn` sin `ML-DSA en v0.3`, `0040_`, `0045_`, `SIGN_ALG_V01`, `LAN_ORIGIN`, `rotate_sign`, `SensitiveFieldRevealed`, `includeSubDomains`, `docs/runbooks/`, `scripts/workflow/tls-smoke` ni `--resume` fuera de `docs/ddd/blueprints`, `impacto` y `07_user_stories`/`08_implementation_breakdown` con nota de T-DOC.

**V2 · Stack de cero y Alembic**

1. Buildx de api, web y backup con `GIT_SHA` del HEAD fusionado. `$DC up -d --no-build --force-recreate`: seis contenedores `healthy`; `restart web`.
2. Ciclo en `db_test`: `tests/core/test_migrations.py tests/migrations` (`0001` a `0024` arriba y abajo).
3. `apex-db-1` (P-MIG): `$DC stop worker`, `downgrade 0020_notifications_indexes`, `upgrade head` (`0024`) y `current`. Se pierden las firmas y los adjuntos de desarrollo (los objetos quedan huérfanos en `uploads`: `attachments-check` los lista y se borran a mano como D76 documenta); se anota. Consulta de `tgenabled` (trece triggers en `A`).
4. P-ROL único: `$DC --profile prod-init run --rm --no-deps dbsetup` y `test_db_roles.sh` contra `apex-db-1`.
5. Ensayo de producción desde cero, por segunda vez: `$DCE down -v --remove-orphans` (comprobado con `docker compose ls`), W0-2.7 completo (llaves nuevas de OpenBao; las viejas se borran), `init-keys --data-class audit.signature`, `--reissue-tokens`, overlay, `retire-local-kek`; `alembic_version = 0024`.
6. Smoke de producción en Linux con `--provider openbao --tls`; `openbao_restore_e2e.sh` y `restore_e2e.sh` (con adjuntos) en `apex-smoke`; `down -v`; re-etiquetar imágenes.

**V3 · Demo 1 · Firma nocturna de la cadena (EP-17).** En el ensayo (8280, OpenBao desellado):

1. `$DCEB run --rm worker python -m app.worker.main --run-once sign_audit` → `ok`, `firmadas = 1`; una segunda corrida el mismo día → `nada_nuevo = 1`; `SELECT through_seq, algorithm, signed_at FROM audit.signatures` (solo lectura).
2. Pantalla Auditoría (Playwright del ensayo o captura): «Última firma válida: seq N · fecha · Ed25519», estado «Íntegra»; «Verificar» → cadena y firmas válidas (`signatures_checked`, `signatures_valid`).
3. Sellado: `$DCE restart openbao`; `--run-once sign_audit` → tres reintentos, `error`, alerta `audit_sign_failed` en el log del worker (sink de log; sin Telegram en el ensayo); «Verificar» en pantalla sigue completo e «Íntegra» (la clave pública está en `crypto_keys`, D81) y `verify-audit` sale 0 con el custodio sellado; desellar con 3 → la corrida siguiente firma. Además, demo de D81: `rotate-key audit.signature --provider local` en el ensayo (con `custody/sign-ed25519.key` presente en `tools`) → versión 2 `local` `active`, la 1 `decrypt_only`; «Verificar» → todas las firmas anteriores válidas; `--run-once sign_audit` firma con la 2; luego `--provider openbao` de vuelta → versión 3 `openbao`.
4. «Firma atrasada»: sobre `apex_sim` en `db_test` con `--date <hoy + 3 días> --simulate` y filas sin firmar → `atrasada = 1` y `alert("audit_sign_late", age_h=…)`; la pantalla contra `apex_sim` (api efímero en 8191, patrón S5-D79) muestra «Firma atrasada». Nunca contra el ensayo ni `apex-db-1`.
5. Cadena reescrita: se cita `tests/audit/test_sign_latest.py` (no se firma) y `tests/audit/test_verify_signatures.py` (firma inválida señalada y llave `decrypt_only` verificando), con sus conteos de V10.

**V4 · Demo 2 · Pantalla Llaves (EP-18).** En el ensayo:

1. Inventario: 10 filas sin material (`grep -c 'vault:'` de la respuesta = 0), `records_count` de `member.document` igual a `count(*)` de socios, «Proveedor activo: openbao · ok».
2. Bitácora con las firmas de V3 (`verb = sign`) y Trabajos con `migrate_provider` `done` al 100 %.
3. «Rotar» sobre `member.phone` con motivo y `ROTAR` → 202, salto a Trabajos, porcentaje creciente (refresco de 5 s), `done`; durante la rotación `GET /members/{id}` (admin) revela el teléfono correcto; después, versión 2 `active` y 1 `decrypt_only`; `audit_log` `update` con `reason` y sin material.
4. «Exportar CBOM» → `apex-cbom-AAAA-MM-DD.json` con 10 llaves, `tls.declared = false` en LAN (y `true` en V6 con dominio), sin `wrapped`; `audit_log` `export`.
5. `retire-key` de la versión 1 de `member.phone` → 2 hasta un respaldo posterior; `run.sh`; `retire-key --confirm-audit-blobs N` → `retired`.

**V5 · Demo 3 · Foto y autorización de datos (EP-19).** En el ensayo, a través de Nginx (P-ADJ):

1. Foto de 5.242.880 bytes → 201; 5.242.881 → 413 `file_too_large` del api (cruzó Nginx; también con `chunked`); 6.300.000 → 413 JSON de Nginx (mismo envelope); ELF renombrado → 422 `unsupported_type`; desde la pantalla, `PhotoField` muestra la vista previa y la ficha la miniatura.
2. `PATCH /settings/privacy` con `consent_required_from = hoy`; alta sin autorización → 422 en el campo; alta con autorización y archivo `consent` → 201, versión vigente, adjunto sensible: `head -c 5` del objeto = `apx1.`, `grep -c '%PDF'` = 0.
3. Descarga de la autorización desde la pestaña Adjuntos (admin) → PDF íntegro (`cmp`); `audit_log` una fila `download` con `subject_member_id`; coach → sin botón y 403 por API; foto → 200 sin fila.
4. Inicio: «Sin autorización» igual a `GET /members?consent=missing`; el enlace abre la lista con el chip.
5. `attachments-check --as` → 0 huérfanos; `restore_e2e.sh` de V2 citado. `consent_required_from` de vuelta a nulo al terminar.

**V6 · Demo 4 · TLS híbrido (EP-20).** Ensayo en modo dominio (`$DCET`, `APEX_DOMAIN=apex.localhost:8443`, `APEX_TLS_ISSUER=internal`, `COOKIE_SECURE=true`):

1. `bash scripts/ci/tls-smoke.sh --dc "$DCET"`: `Negotiated TLS1.3 group: X25519MLKEM768`; caída a `X25519`; TLS 1.1 rechazado; `curl -I http://…/login` → 308 a `https://…/login`; `Strict-Transport-Security: max-age=300`; `web` sin puerto publicado; cookie `Secure`; CORS acepta `https://apex.localhost:8443` y rechaza `http://`; limitador por IP real con dos clientes.
2. Login por HTTPS desde Playwright con la CA interna (contexto `ignoreHTTPSErrors: false` y `--ca` del navegador, o `NODE_EXTRA_CA_CERTS`); la pantalla carga; CBOM con `tls.declared = true`.
3. Modo LAN (`$DCEB`, sin perfil): `tls-smoke.sh --lan` → sin HSTS, cookie sin `Secure`, 8280 por HTTP; `docker compose config` sin `caddy`.
4. Arranque con `CORS_ORIGINS=http://otro` y dominio → el api sale con el mensaje que nombra la variable.
5. ACME real, renovación con staging y SSL Labs: pasos humanos documentados en `tls.md` (sin dominio público en el flujo).

**V7 · E2E**

- Ensayo (producción con OpenBao, modo LAN): `npx playwright test --project=stack --workers=1` con `audit-signature.spec.ts`, `keys-rotate.spec.ts`, `members-attachments.spec.ts`, `members-photo.spec.ts`, `home.spec.ts` y los críticos de 4B y S5. Dos corridas seguidas sin fallos ni flaky; topes ×100 con `compose.e2e.yml` y las 22 sustituciones del `.env` del ensayo como en S5 V5 (restauración con `cmp`); si aparece un 429, se espera un minuto.
- Desarrollo: `--project=preview` completo con capturas en 320, 768, 1024 y 1440, claro y oscuro (Auditoría con firma, Llaves, pestaña Adjuntos, formulario con foto, Inicio).
- `csp.spec.ts` con `img-src blob:`.

**V8 · Rendimiento (`perf`, no gate).** `pytest -m perf -q -s` dos corridas: inventario con 10.000 filas en `crypto_ops` (`GET /crypto/ops` < 300 ms); verificación de 365 firmas con la clave pública en proceso (< 5 s, cero llamadas al proveedor; D81); subida de 5 MiB y descarga de un sensible (pico de memoria con `tracemalloc` < 14 MiB; tiempo); rotación de 1.000 adjuntos de 100 KB (lotes de 50); `GET /members?consent=missing` con 1.000 socios. `EXPLAIN (ANALYZE, BUFFERS)` de `list_ops`, `list_for_owner`, el filtro `consent=missing` y `count_pending` de adjuntos (en el ensayo); si el filtro lo pide, el índice parcial de consentimiento entra como `0025` con decisión (hoy no).

**V9 · `database-reviewer` final.** `grants.sql` (dos tablas nuevas, esquema `attachments`, grants por columna de `crypto_jobs` y `crypto_keys`), índices de `attachments` y `audit.signatures`, las cuatro migraciones, las guardas de `0024` frente a H-2.

**V10 · Gates completos.**

- `run-gates.sh`, cuarta corrida, con la suite del api en tres partes con `--cov-append` si la memoria lo exige. Cobertura del 80 % o más, también en `core/audit_sign.py`, `core/audit_verify.py`, `core/crypto/{router,inventory,cbom,reencryptor,rotate_job}.py`, `modules/attachments/*`, `worker/jobs/sign_audit.py`, `cli_ops/{sign_audit,attachments_check}.py`.
- `pre-commit --all-files`; licencias de api y web; `NOTICE`; `pip-audit`; `npm audit`; gitleaks del historial; `check-image-secrets` ×3; `test_api_image` (sin `boto3` en la imagen); `test_backup_apk_pins`; `scripts/ci/test_*.sh` todos.
- Conteo de saltadas: `age`, `pty`, `openbao` real y `tls` corren en el contenedor Linux o en el ensayo con 0 saltos.

**V11 · Revisiones y `verify-delivery`.**

- `security-reviewer` sobre el árbol fusionado con los puntos de la DoD y de D67: el api no firma (políticas y prueba de 403); guarda `0024` y grants acotados; adjuntos servidos solo por el api con rol, `no-store`, `nosniff`, bytes mágicos y semáforo; HSTS solo con dominio y escalonado; ningún material ni referencia en auditoría, CBOM, inventario ni logs del ensayo (`grep` de los logs); foto sin fila por vista con cubeta propia; H-1 y H-2 cerrados; `real_ip` solo desde la IP de Caddy. `code-reviewer`, `python-reviewer` y `typescript-reviewer` sobre `git diff main...HEAD`; tamaños de archivo y de función. Todo hallazgo se corrige (se vuelve al slice y se resella) o se acepta con dueño.
- `verify-delivery`: matriz `docs/scratch/sprint-06-verify-delivery.md` con los dos pilares: historias US-140 a US-153 criterio por criterio (con los desvíos de T-DOC marcados), DoD y demos 1 a 4, cada uno con su evidencia; sistema real: imágenes vigentes de cada componente (api, web, backup, worker, caddy), una escritura real por camino (firma, rotación, subida, descarga, alta con autorización), base cruzada, `sign_audit` ×2 y `attachments-check`, idempotencia. Pasos humanos declarados: PR y merge del Sprint 5, dominio y ACME real, SSL Labs, custodia de la CA interna (no existe en producción), `consent_required_from` en producción (M-11).

**V12 · Limpieza y release.**

- Borrar `docs/scratch/*.dump`, `docs/scratch/keys-dev-antes-layout.tgz`, `docs/scratch/ensayo/` (llaves de OpenBao del ensayo, adjuntos de prueba, CBOM, CA interna) y `apex_sim` si quedara.
- `docker compose -p apex-ensayo down -v --remove-orphans` y el smoke, comprobados con `docker compose ls`; nunca `apex`. `$DC --profile openbao stop openbao`; `$DC --profile tls stop caddy`.
- Reconstruir las imágenes con el SHA de cierre; `/health.version` en 8181; `--run-once sign_audit` en desarrollo con la imagen de cierre.
- Versiones a `0.3.0` (D66), `CHANGELOG.md` `## [0.3.0]`, `git tag -a v0.3.0` local, `bash scripts/ci/check-release-version.sh --check v0.3.0`.
- Estado al cierre y dueños en DECISIONES (incluido el valor de `consent_required_from` que debe fijarse en producción, M-11; la fusión pendiente del Sprint 5, D55; ML-DSA en EP-26; retención y supresión v0.4; TLS en `custody` v0.4; AppRole; `display_name`; logo; «Exportar rango»).
- Pasos humanos: PR del Sprint 5 fusionado antes, push, PR del Sprint 6 con la CI en verde (`api` con 0 saltos de `openbao`, `images` con `tls-smoke` y `restore_e2e`, `prod-smoke` con `--tls`), merge, Release, firma de la etiqueta si el titular la hace.

## 8. Riesgos y mitigación

1. **[HIGH] El api gana escritura sobre `crypto_keys` y `crypto_jobs` (H-2).** Guarda `0024` con las tres condiciones, `guard_jobs_update`, grants por columna, un rotador en vuelo, conexión dedicada, tope de duración, auditoría explícita, retiro solo por CLI con manifiesto posterior; pruebas con el rol real; `database-reviewer` y `security-reviewer` de R1. Residual: la guarda no recuenta pendientes (D61); lo hace `finish_rotation`.
2. **[HIGH] El worker firma y quien lo comprometa junto con la base podría firmar una cadena reescrita.** El api no firma (403 probado); verificación incremental antes de firmar (H-1); anti-retroceso sin Transit; alerta de firma atrasada; copia del ancla en el respaldo. Residual: sin sello de tiempo externo (ADR-006).
3. **[HIGH] Adjuntos sensibles cifrados y descifrados en memoria (hasta unos 12 MiB por petición), sin spool.** Semáforo de 4, cubetas, lectura acotada por el propio bucle (`request.stream()`), `tempfile` nunca llamado, medición en V8. La foto queda sin cifrar en disco: ADR-007.
4. **[HIGH] `real_ip` confía en la IP fija de Caddy.** `/32`, `recursive off`, IP fuera del `ip_range`, `cap_drop ALL` sin `NET_RAW` en todos los miembros, prueba del limitador con dos clientes en el smoke y en la CI.
5. **[MEDIUM] Subruta del volumen `keys` (D58): migrar el layout en servidores existentes.** `init-keys --migrate-layout` idempotente, `deploy.sh` lo ejecuta antes de `up`, `check-key-files.sh` falla cerrado, `tar` previo del volumen de desarrollo, prueba en `apex-smoke` desde un volumen plano.
6. **[MEDIUM] `__audit_exclude__` toca `core/audit.py`.** Un solo atributo, sin cambio en el serializador ni en `record`; `test_chain_hash_vector` y `test_audit_serialize` en el gate de C1.
7. **[MEDIUM] La verificación confía en `crypto_keys.public_key` (D81).** Quien pueda escribir esa columna podría sustituir la clave pública y «validar» firmas propias: inmutable por grant (ningún `UPDATE` por columna para `apex_api` ni `apex_worker`) y por la guarda de `0024`; se llena solo desde `tools`; `retire-key` conserva la fila mientras haya firmas; el anti-retroceso cubre el borrado; residual: el propietario de la base (`apex_owner`, `tools`) puede cambiarla, igual que hoy puede apagar triggers (ADR-004/006).
8. **[MEDIUM] Memoria del equipo (ensayo con OpenBao y Caddy, auxiliar Linux, vitest).** Caddy solo bajo perfil y apagado fuera de W0-4, E1 y V6; ensayo detenido durante `run-gates`; comandos serializados; vitest con `--pool=forks --maxWorkers=2`.
9. **[MEDIUM] Listas cerradas por igualdad (impacto, bug 13).** Cada Rojo las toca en el mismo slice (sección 10); `grants.sql` fail-closed con `dbsetup` del ensayo en A1, C1 y R1.
10. **[MEDIUM] Lectura cruda con `request.stream()` (E1).** El tope real lo pone el propio bucle de lectura, no una cabecera: pruebas con `Content-Length` falso en los dos sentidos, `chunked`, iterador infinito, `kind` inválido con 0 trozos consumidos y medición del spool (`tempfile` nunca se llama); Nginx a 6m en esa ruta corta lo que pase de 6 MiB. Residual: un cliente que abre muchas subidas lentas consume conexiones de uvicorn hasta su timeout de lectura; lo acotan la cubeta `attachments-upload` y `limit_req` de Nginx.
11. **[MEDIUM] Compose `volume.subpath` y `ports: !override []`.** W0-1.1 lo renderiza; en CI los runners usan Compose 2.x con las dos funciones; si un runner no las admite, `ci.yml` fija la versión de Compose.
12. **[MEDIUM] OpenSSL 3.5 en Alpine 3.22 y la negociación con Caddy 2.11.3.** W0-1.1 lo prueba antes de escribir nada; si Alpine 3.22 no trae 3.5.x, se usa `alpine:edge` por digest con decisión del slice o la imagen `caddy` misma como cliente (`curl` de Caddy no expone grupos: segunda opción solo si la primera falla).
13. **[LOW] `consent_required_from` nulo no exige nada.** KPI y filtro visibles; guía de instalación y V12 lo anotan (M-11).
14. **[LOW] El `downgrade` de V2 en `apex-db-1` borra firmas y adjuntos de desarrollo.** Huérfanos listados por `attachments-check`; se anota.
15. **[LOW] El Sprint 5 sin fusionar.** Paso humano antes del PR del 6 (D55); el PR del 6 nace de la rama del 5.

## 9. Rollback por migración

Regla de RUNBOOK §6: `downgrade` primero, después `git revert`, después `restart api worker`. Volcados `sprint-06-antes-00NN.dump`.

- **`0024`:** `downgrade 0023` restaura la guarda de `0015` y borra `guard_jobs_update`; un job `running` del api queda huérfano y se cierra con `rotate-key` desde `tools` (propietario); los grants nuevos se retiran con `revoke.sql` y `dbsetup`.
- **`0023`:** `downgrade 0022` borra la tabla y el esquema `attachments`; los objetos quedan huérfanos en `uploads` (RUNBOOK §6 y D76) y la fila `encrypt` de `attachment.sensitive` queda sin uso (no se borra: regla de datos 4).
- **`0022`:** `downgrade 0021` quita las seis columnas; las verificaciones viejas no cambian.
- **`0021`:** `downgrade 0020` borra `audit.signatures`; las firmas se pierden (sin datos de producción todavía); `crypto_ops` conserva las filas `sign`.
- **Grants y esquema:** `revoke.sql` por base; `dbsetup` del ensayo.
- **Layout de `keys` (D58):** no es migración de base; volver atrás es `git revert` más mover los archivos a la raíz del volumen con el stack parado (RUNBOOK §12 lo describe con `tar`); el `tar` de W0-2.6 cubre el desarrollo.
- **Compose, Caddy y Nginx:** `git revert` y `up -d`; sin el perfil `tls` el sistema vuelve a HTTP en `WEB_PORT`.
- **Políticas de OpenBao:** `bootstrap.sh --reissue-tokens` con las políticas revertidas.

## 10. Trazabilidad

### C1 a C9 → paso

- **C1 (T-DOC):** pasos 3, 4 (a..k: numeración en 3; Q27 en 3 y sección 1; `audit_sign.py` y `set_audit_writer` en 3 y 4; contrato de US-149 en 3; `retired` en 3; multipart y S3 en 3 y 5; cookie y origen en 3; deudas v0.3 en 4 (sección 1, D58, D69, D76 y «lo que pasa a v0.4»); `CLAUDE.md` y textos en 3; ADR en 4 y gate humano; US-145 READY en 3).
- **C2 (bloque A):** pasos 20-25 (políticas), 34-42 (`0021`, bus, `sign_latest`), 43-49 (job, CLI, alertas), 50-56 (`verify`, `0022`, ruta).
- **C3 (bloque B):** pasos 57-64, 65-69, 70-75 (y F2: 144-150).
- **C4 (bloque C):** pasos 5 (dependencia), 7-11 (`STORAGE_PROVIDER`, cubetas), 12-19 (Nginx y borde), 76-84, 85-90, 91-96, 97-102, 103-107.
- **C5 (bloque D):** pasos 57-59 (puerto), 108-116.
- **C6 (decisión de seguridad antes de D):** sección 1 (D35, D43, D61) y las revisiones de 82, 101, 114 y V11.
- **C7 (Wave 0 TLS y Nginx):** pasos 12-13 (Nginx), 26-33 (Caddy, `real_ip`, `tls-smoke`), 117-122 (`public_origin`).
- **C8 (front):** pasos 123-150.
- **C9 (validación y cierre):** V1 a V12 y `run-gates.sh` en 54, 106, 121 y V10.

### Revisión de seguridad → paso

- **HIGH:** H-1 en 34-36, 38, 44 (alerta) y V3; H-2 en 108-115 (guarda, grants, semáforo, conexión dedicada) y V9, V11.
- **MEDIUM:** M-1 en 50-55. M-2 en 36 (b, e), 20-21 (c), 43-44 (a, d). M-3 en 76, 78 (`open`), 97-98. M-4 en 1 (E9), 12-13 (Nginx), 76, 78, 85-86 y 90 (cuerpo crudo acotado, E1). M-5 en 4 (ADR-007), 97-98, 129. M-6 en 85-86 (subida) y 97-98 (descarga), 129. M-7 en 26-29 (a..e). M-8 en 27-28, 30. M-9 en 7-8, 76, 78. M-10 en 4 (ADR-007), 81 (D76). M-11 en 91-92, 94, V12.
- **LOW:** L-1 en 76-77, 80 (D75). L-2 en 129. L-3 en 108, 110, 115 (D74). L-4 en 43-44. L-5 en 70-71. L-6 en 20-21, 27-28 (`cap_drop`) y residual v0.4 en 30.

### Bloqueantes de la exploración (1 a 24) → paso

- 1 → sección 1 (D39) y 3. 2, 3 → 34-38 y 43-44. 4 → 20-25. 5 → 43-44 (D42). 6 → 35, 37. 7, 8 → 108-115. 9 → 57-59. 10 → 57-58, 60. 11 → 60 y 111 (`AUDITABLE_TABLES`), 77. 12 → 26-33. 13 → 117-119. 14 → 12-13, 85-86. 15 → 76-84, 103 (restauración). 16 → 76, 78. 17 → 70, 97-99. 18 → 91-96, 103-104. 19 → 34-36, 50-52. 20 → 43-45. 21 → 36 (sin ML-DSA; D51). 22 → 65 (`JOB_KINDS`) y 43-47 (`migrate-provider` sigue excluyendo `sign` con salida 2; `rotate-key --provider`, D81). 23 → 129-130, 134-135. 24 → 4, 30, 81.

### Preguntas del impacto (1 a 15), del blueprint (Q1 a Q12, E1 a E14) y de la exploración (1 a 18)

- Impacto 1 → D51. 2 → D52. 3 → D43, D61. 4 → D36, D62. 5 → D46. 6 → D45, D59. 7 → D45 (S3 apagado). 8 → D48, D65. 9 → L-6 residual v0.4. 10 → D49, D55. 11 → D72. 12 → D54, D58. 13 → D54. 14 → D53. 15 → D55.
- Q1 → D51. Q2 → EP-26. Q3 → D37. Q4 → D40 (sin reintento horario). Q5 → D36. Q6 → D43. Q7 → D46. Q8 → D46 (no obligatorio). Q9 → D45. Q10 → L-6, v0.4. Q11 → D45. Q12 → D38, D76.
- E1 → impacto (sondeo) y D51. E2, E3 en 34. E4 → D42, 43. E5 en 108. E6, E7 en 57. E8 en 85. E9 en 1 y 76. E10 en 26. E11 en 1 y 26. E12 → sección 6 (reglas). E13 en 43. E14 en 12.
- Exploración 1-18: 1 → D39; 2, 3 → D40, D51, D72; 4 → D41; 5 → D42; 6 → 35, 37; 7 → D36; 8 → D43; 9 → D45; 10 → D44, D52; 11 → D14, D44; 12 → D18, D22, D25; 13 → D46; 14 → D47, D57; 15 → D48, D63, D64; 16 → D65; 17 → D49; 18 → D23 y sección 6.

### Historias y demo

- US-140 → A1 (demo 1, V3). US-141 → W0-3, A2 (demo 1, V3). US-142 → A3, F1 (demo 1, V3).
- US-143 → B1, F2 (demo 2, V4). US-144 → B2, F2 (V4). US-145 → R1, F2 (demo 2, V4). US-146 → B3, F2 (V4).
- US-147 → W0-1 (dependencia), W0-5, W0-2, C1 (demo 3, V5). US-148 → C2, F3, F4 (V5). US-149 → C3, F4 (V5). US-150 → C4, F3 (V5). US-151 → C5, F5 (V5).
- US-152 → W0-4 (demo 4, V6). US-153 → W0-4, E1, F5 (demo 4, V6).

### Deuda heredada con dueño v0.3 y su destino

- S5-D201 (subruta JWT) → W0-2 (D58). G-09 `rotation_not_supported` → B1 y R1. S5-D183 (filas `sign` fuera de `migrate-provider`) → intacta (D81): el cambio de proveedor de la firma es `rotate-key audit.signature --provider` en A2 y las firmas viejas verifican por `public_key`. S5-D63 TLS en `custody` → residual v0.4, operador (L-6). S5-D272 llavero → procedimiento en `openbao.md` (W0-3.3), dueño titular. S5-D226 (índice `memberships(end_date)` y CHECK) → solo si V8 lo pide, con decisión. S5-D207 (`SMTP_TLS_MODE=ssl`), `display_name`, logo del recibo, «Exportar rango», `unwrap` con `bytearray`, AppRole, `audit.append`, L-4 de S5 → dueños sin cambio (se anotan en V12).

### Lo que pasa a v0.4 o después (con dueño)

- ML-DSA en Transit o local, con su verificación por clave pública (EP-26, v1.0); rotación de la llave de firma dentro del mismo proveedor (D69, EP-26).
- Retención y supresión de adjuntos con `attachments purge` y `purged_at` (titular, v0.4; D38, D76).
- TLS en `custody` y AppRole (operador, v0.4).
- Retiro de llaves desde la pantalla (titular, si se pide).
- AEAD por trozos para sensibles grandes (solo si sube el tope de 5 MiB).
- Reintento horario de `sign_audit` (operación, si lo pide).
- Índice parcial de consentimiento y S5-D226 (si V8 lo pide).
- Portal y foto del socio en el portal (EP-25, v1.0).

## 11. Riesgos y supuestos que `plan-critic` debe atacar

1. **`volume.subpath` en Compose 5.6.1 y en los runners de CI, y `ports: !override []`** (W0-1.1). Si no renderizan, D58 cae a dos volúmenes (`keys` y `keys-jwt`) con decisión, y la anulación de puertos a `WEB_PORT` vacío en el overlay.
2. **`init-keys --migrate-layout` sobre el volumen de desarrollo** (W0-2.6): primer cambio al layout desde S1; el `tar` previo es la vuelta atrás. ¿Debe ser un paso humano?
3. **Alpine 3.22 con OpenSSL 3.5.x y `-groups X25519MLKEM768`** (W0-1.1). Alternativas en el riesgo 12.
4. **Cuerpo crudo con `request.stream()` (E1, E13, D59):** que uvicorn entregue el cuerpo por trozos sin acumularlo y que, al responder 413 antes de consumir el resto, el cliente directo reciba la respuesta (uvicorn puede cerrar la conexión con cuerpo pendiente: el cliente ve el 413 o un cierre). Detrás de Nginx con `proxy_request_buffering on` el api casi siempre responde 413 por `Content-Length` sin leer y el corte por trozos solo actúa sin proxy: por eso esas pruebas son de api (ASGI) y la demo solo observa 201/413. Supuesto: que el `location` de 6m (regex) gane al `5m` del `server`; `test_nginx_conf.sh` lo demuestra con 5.242.881 llegando al upstream.
5. **La guarda de `0024` no recuenta pendientes (D61 frente a H-2 (2)).** `plan-critic` y `security-reviewer` de R1 deben aceptar que `done = total` en el trigger, `guard_jobs_insert` (E6) y `count_pending` bajo `FOR SHARE` en `finish_rotation` cierran la variante (b) de H-2 con el residual declarado, o proponer una función SQL por clase.
6. **`rotate-key audit.signature --provider` (D81):** `--provider local` exige `sign-ed25519.key` en `custody/` del contenedor `tools` (con el overlay de OpenBao `tools` sigue montando `keys`: se verifica en A2.6); `--provider openbao` exige el token de `tools` con `read` de `transit/keys/apex-sign-audit` (W0-3). Con la versión 2 de la llave de firma en otro proveedor, el worker firma con el proveedor de esa fila (S5-D3) y su token debe tener `sign` en ese proveedor: el ensayo lo prueba volviendo a `openbao` en V3.
7. **`public_key` en `crypto_keys` (D81):** formato base64 de los 32 bytes crudos; plan-critic debe confirmar que `transit/keys/apex-sign-audit` devuelve la clave pública Ed25519 en ese formato en OpenBao 2.7.2 (impacto: `key_info` existe; el campo `public_key` se verifica en A1.8 con OpenBao real) y que `0021` puede sumar la columna a `crypto_keys` sin romper «una migración por tabla» (decisión del orquestador, E10).
8. **`__audit_exclude__` en `core/audit.py` (D75)** frente a «no tocar `core/audit.py`»: un atributo leído por el hook (O2 lo acepta); alternativa: anotar L-1 como aceptado y dejar `filename_random`/`key_id` en `after`.
9. **`APEX_DOMAIN` con puerto (D77, E12):** sin `staging` (`ENV` sigue `dev|production`); `ALLOW_DOMAIN_PORT=true` solo con host `*.localhost`; `APEX_TLS_ISSUER` sigue siendo solo de Caddy (`NON_API_ENV_VARS`, `.env.ops.example`, `test_env_isolation.sh` la admite solo en `caddy`) y `test_caddyfile.sh` exige que `internal` solo acompañe a hosts `*.localhost`. Supuesto: `apex.localhost` resuelve a loopback en el navegador de Playwright sin `/etc/hosts` (RFC 6761; Chromium lo hace).
10. **Un solo proceso del api (D59, D61, D79):** la prueba de O4 fija `uvicorn` sin `--workers` en `Dockerfile` y en Compose; escalar exige mover los tres candados a la base (deuda con dueño).
11. **Healthcheck de Caddy por `/_caddy_health` (E8, M1)** con `redir … 308` explícito en el sitio HTTP: W0-4.1 comprueba que Caddy no añade además su redirección automática (con un sitio `http://` explícito no lo hace) y `test_caddyfile.sh` que `/.well-known/acme-challenge/x` no da 308 (`handle` delante del `redir`); el ACME HTTP-01 real con dominio es paso humano en `tls.md`.
12. **Snippet `real-ip.conf` fuera del árbol (E11, D82):** `${DEPLOY_STATE_DIR}/real-ip.conf` montado por `APEX_REAL_IP_CONF`; `deploy.sh:101,218` siguen exigiendo árbol limpio y la prueba lo demuestra; supuesto: `DEPLOY_STATE_DIR` existe antes del render (ya lo crea `deploy.sh` para `rollback-<fecha>.txt`).
13. **Nginx con `cap_drop ALL` y cuatro `cap_add`**: si la imagen necesita más, se anota con decisión (nunca `NET_RAW`).
14. **El orden de W0 cambia respecto al blueprint (D56)**: W0-3 (políticas) después del ensayo de W0-2 obliga a reemitir tokens en W0-3.5; alternativa: crear el ensayo en W0-3. El plan prefiere el ensayo temprano para que W0-2.7 y el smoke de Nginx corran sobre producción.
15. **`test_adr_docs` a siete archivos antes de que existan las pruebas que los ADR citan**: los ADR citan pruebas existentes hasta A1 y C1; plan-critic debe confirmar que la regla «toda ruta citada existe» lo admite.
16. **La prueba de dos clientes del limitador (P-TLS)** necesita dos contenedores en la red `default` del ensayo con IPs fuera del `ip_range` o dentro (da igual) y Nginx viendo a Caddy como par: depende de que Caddy escriba `X-Forwarded-For` con la IP del contenedor cliente.
17. **Paralelismo del front (D70):** F3 y F4 dependen de C2/C3/C4 ya en la rama; F2 espera a R1. Serialización manual de comandos pesados.
18. **Cuatro corridas de `run-gates.sh` (A3, C5, E1, V10)** con la suite ya por encima de 8.000 pruebas: tiempo y memoria; si la segunda parte muere, se parte en cuatro con decisión.

## 12. Conteo

- **Slices:** 23 más V.
  - Wave 0: 5 (W0-1, W0-5, W0-2, W0-3, W0-4).
  - Backend: 13, en orden A1, A2, A3, B1, B2, B3, C1, C2, C3, C4, C5, R1, E1.
  - Front: 5 (F1, F3, F4, F5, F2).
- **Pasos:** 150 numerados (W0-1 6; W0-5 5; W0-2 8; W0-3 6; W0-4 8; A1 9; A2 7; A3 7; B1 8; B2 5; B3 6; C1 9; C2 6; C3 6; C4 6; C5 5; R1 9; E1 6; F1 6; F3 5; F4 5; F5 5; F2 7), más V1 a V12: 162.
- **Checkpoints:** 23 de slice (18 del backend en la rama del sprint y 5 del front en el worktree), más los de evidencia y validación.
- **Migraciones:** 4 (`0021_audit_signatures`, `0022_audit_verifications_signatures`, `0023_attachments`, `0024_crypto_rotation_from_api`); revisión de base de datos en A1, A3, C1, R1 y V9.
- **Endpoints:** 9 nuevos, todos con rol y `no-store` (`GET /audit/signatures/latest`; `GET /crypto/keys`, `GET /crypto/ops`, `GET /crypto/jobs`, `POST /crypto/keys/{id}/rotate`, `GET /crypto/cbom`; `POST` y `GET /members/{id}/attachments`; `GET /attachments/{id}`). Cambian de respuesta `POST /audit/verify`, `GET /audit/verify/last`, `GET /members` (`consent`), `GET /members/{id}` (`photo_attachment_id`) y `POST /members` (409 `privacy_version_missing`; mismo cuerpo). `PUBLIC_ROUTES` sigue en ocho.
- **Códigos nuevos del catálogo:** 409 `key_not_active`, `purpose_not_rotatable`, `rotation_running`, `rotation_not_supported`, `privacy_version_missing`; 413 `file_too_large` (api y Nginx, mismo envelope; D73); 422 `unsupported_type`, `field` `confirm`, `reason`, `data_consent_at`; 404 `attachment_not_found`.
- **Comandos de CLI nuevos o ampliados:** `sign-audit`, `init-keys --data-class` (real), `init-keys --migrate-layout`, `attachments-check`, `retire-key` (llave `sign` y respaldo posterior), `rotate-key` (`run_rotation`; `attachment.sensitive`; `audit.signature --provider`, D81), `migrate-provider` (sigue excluyendo `sign`, con salida 2 si se fuerza), `verify-audit` (firmas, sin custodio). El worker suma `--run-once sign_audit`.
- **Cubetas:** 5 nuevas (7 variables); catálogo de 23 cubetas y 22 variables.
- **Servicios de Compose nuevos:** `caddy` (perfil `tls`); archivo `compose.tls.yml`; volúmenes `caddy_data` y `caddy_config`; subruta `custody`/`jwt` del volumen `keys`.
- **Dependencias:** ninguna de ejecución nueva (E1: cuerpo crudo, sin `python-multipart`); `boto3` y `botocore` (grupo opcional `s3`, Apache-2.0, fuera de la imagen). Imágenes: `caddy:2.11.3` (Apache-2.0) y `alpine:3.22` (MIT, solo smoke), por digest.
- **ADR:** 2 nuevos (ADR-006, ADR-007); `test_adr_docs` a 7; ninguno modificado.
- **Pruebas nuevas, aproximadas:** unas 620 del api (crypto 170, attachments 140, audit 70, members 90, core 60, worker 40, cli 50) y unas 170 del front; arquitectura: 3 nuevas (`test_crypto_inventory_no_material`, `test_cbom_no_key_material`, `test_reencryptor_registered_in_every_root`) y 24 ampliadas; Bash: `tls-smoke.sh`, `infra/caddy/tests/test_caddyfile.sh`, `restore_e2e.sh` con adjuntos, ampliaciones de `test_nginx_conf`, `test_compose_config`, `test_openbao_infra`, `test_deploy_script`, `openbao-smoke`.
- **Decisiones:** S6-D1 a S6-D33 en forma final; S6-D34 a S6-D38 con su opción final; S6-D39 a S6-D55 tal cual; S6-D56 a S6-D82 de este plan (27; D59, D61, D62, D64, D73 y D77 reescritas y D78 a D80 nuevas por la crítica 1; D62, D64, D69 y D77 reescritas y D81 y D82 nuevas por la crítica 2); 28 contradicciones resueltas (4, 16 y 28 reescritas en la ronda 3).
- **Enmiendas de la crítica 2 (ronda 3):** E10 → D81 (más D5, D7, D10, D36, D62, D69), contradicciones 4 y 16, fixtures de A3, pasos 3, 34, 36, 38, 43-47, 50-56, 124, V3, V8, §10, §11.6-7; E11 → D82, contradicción 28, D64, pasos 26, 27, 29, 30, §11.12; E12 → D77, paso 7, §11.9; E13 → D59, pasos 12, 27, 85, 86, 90, §11.4; M1 → D64, pasos 26, 27, 30, §11.11; M2 → D64 y paso 27 (grep de `cap_drop`: nueve servicios lo tienen, `db` no, `caddy` nuevo). Pasos: siguen siendo 150; nuevas pruebas `tests/cli/test_rotate_sign_provider.py` y `tests/crypto/test_rotate_sign_provider.py` (A2); columna `crypto_keys.public_key` en `0021`.
- **Enmiendas de la crítica 1 (ronda 2):** E1 → D59, D73, P-ADJ, pasos 1, 5, 76-78, 85-86, 90, 134-135, riesgo 10, §11.4; E2 → contradicción 16, D2, D61, pasos 43-47, 108-110, §10; E3 → pasos 12, 14, 17; E4 → D78, pasos 1, 12, 14, 15; E5 → paso 110; E6 → D61, pasos 108-109, 113; E7 → D80, pasos 14, 43, 45, 80, 112; E8 → D64, pasos 26, 27, §11.11; E9 → D64, pasos 4, 26, 27; O1 → D62, paso 51, V8; O3 → D77, pasos 7-8; O4 → D79, pasos 7-8, 27; O5 → D64, pasos 26, 27, 29, §11.12; O11 → pasos 43-44. Pasos: siguen siendo 150 (ningún paso insertado ni quitado).
- **`run-gates.sh`:** 4 corridas (A3, C5, E1, V10).
- **Proyectos Compose aparte:** `apex-ensayo` (W0-2.7 a V12, recreado en V2) y `apex-smoke` (W0-2, W0-3, W0-4, C5, V2; efímero).
