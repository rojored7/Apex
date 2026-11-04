# Cuaderno del Sprint 5 (v0.2: OpenBao, avisos de vencimiento, recibos y exportaciones)

Rama `feat/sprint-05-openbao-avisos-recibos` desde `main` `a1ad4cb` (cierre del Sprint 4B, 2026-11-04). Mismo formato que `sprint-04b.md`: un bloque por slice (Rojo, Verde, Revisiones, Evidencia) y al final "Validación V1–V12". Sin credenciales, frases ni rutas de identidades.

## Planificación (2026-11-04)

- Fase 0: `docs/ddd/impacto/sprint-05.md`, veredicto AMARILLO con C1..C10; `validate-impact-analysis.sh --allow-amber` → 0.
- Fase 1: `docs/ddd/blueprints/sprint-05-exploracion.md` (5 bloqueantes de diseño, 18 preguntas) y `sprint-05-blueprint.md` (S5-D1..D48; W0-1..W0-4, B1..B13, F1..F5).
- Decisiones del orquestador sobre las preguntas del arquitecto (Q1..Q10): PDF mínimo propio en `core/pdf.py` (sin `reportlab`/`pillow`; `pypdf` BSD solo en dev); una sola llave Transit `apex-kek`; `apex_owner` NOSUPERUSER en W0-4; sin `data_consent_at` no se avisa por ningún canal (se listan aparte); recibo sin documento; `members_without_consent` calculado; auditoría de exportación con `has_q` y filtros estructurados; `display_name` a v0.3 salvo que quepa sin contrato nuevo; respaldo de `openbao-data` (B13) dentro del sprint; custodia de las 5 llaves de desello 2 titular / 2 operador / 1 copia sellada (paso humano).
- Fase 1.5: `docs/ddd/blueprints/sprint-05-seguridad-diseno.md` (en curso).

## W0-1 · línea base (2026-11-04, HEAD `8dafdb1`, árbol limpio)

**Stack.** Seis contenedores `healthy` (api, worker, web, backup, db, db_test). `alembic current` = `0014_audit_log_triggers_always (head)`. `git worktree list`: solo el principal. Compose v5.6.1 (>= 2.24: `!override` e `internal` renderizan, comprobado con un compose de prueba).

**Imágenes locales** (id; etiqueta OCI `revision`): `apex-api:local` `sha256:20a30740af53919a4205fef24012eaf5d38f2bfea486cbe07bc24b80104ac05a` rev `a1ad4cb`; `apex-web:local` `sha256:7362c951e9e3503c9de939cdebcce4b58a1637f5ef5889e13a2c8ccfb9fdb6ce` rev `a1ad4cb`; `apex-backup:local` `sha256:34874b888a0a4e16bf05326ba1967cb66ad37f85312b47a51ce9965098f8939c` (sin etiquetas OCI). `docker stats --no-stream` (apex): api 115 MiB, worker 78 MiB, db 59 MiB, db_test 632 MiB, backup 9 MiB, web 7 MiB; host con 11,68 GiB y otros proyectos (dian, vi) activos.

**Puertos y redes.** 8280, 8380 y 8200 libres. **8025 NO está libre**: `127.0.0.1:8025` lo publica `dian-mailhog` de otro proyecto (PID 12672 = `com.docker.backend`). Mailpit de desarrollo no puede publicar 8025 en este equipo: el orquestador confirmó `127.0.0.1:${MAILPIT_PORT:-8125}` (S5-D102); el plan lee 8125. Subredes en uso: 172.17/16, 172.18/16, 172.19/16, 172.20/16, 172.21/16, 172.22/16, 172.23/16, 172.24/16 y `apex_default` 172.30.0.0/24; **libres** 172.30.1.0/24, 172.31.2.0/24, 172.31.3.0/24, 172.31.12.0/24 y 172.31.13.0/24.

**Digests (`docker buildx imagetools inspect`, 2026-11-04).**
- `openbao/openbao:2.7.2` (estable más reciente de la rama 2.x, publicada 2026-10-26; `2.6.5` mantenimiento): índice `sha256:5046911075e137e154ce49ab051502f4ec7cf367d484ae4a4dce665d9b90561f`; amd64 `sha256:a78eb12a9fc7a3ebb4bec1724e2bdd6a28e33394820641d061166919a3f1866b`.
- `axllent/mailpit:v1.33.0` (2026-10-31): índice `sha256:9b3a463be15354c0f0eba91697d80e3e0d8a5623ef0e627cacc836bc17fd5231`.
- `python:3.12-alpine` (2026-10-29): índice `sha256:e6dae589c1c05976188fd3bd019afd091445fc533ed2ea29001beddc7368a9c8`.
- Se fija el digest del índice (multi-arquitectura). `openbao/openbao:2.7.2` quedó descargada en el equipo; Mailpit y python no.

**E11/E12 (contenedor desechable `openbao/openbao:2.7.2`, borrado junto con su volumen).**
- `bao version`: OpenBao v2.7.2. `id`: **uid 100 (openbao), gid 1000**. Alpine; hay `wget` (busybox), **no hay `curl`**. Dato para B13: `curl` entra a la imagen `apex-backup`, no a la de OpenBao; el healthcheck de OpenBao usa `wget`.
- **`bao operator unseal -` NO lee stdin**: manda el literal `-` y la API responde 400. Sin argumento y con stdin entubado, falla ("usually because you attempted to pipe ... outside a tty"). **Se aplica la alternativa escrita del plan:** `PUT/POST /v1/sys/unseal` con `wget`. Verificado: `printf '{"key":"<k>"}' | docker exec -i <c> wget -qO- --header "Content-Type: application/json" --post-file=/dev/stdin http://127.0.0.1:8200/v1/sys/unseal` desella sin dejar la llave en `argv` ni en un archivo (ni siquiera `tmpfs`). Esto mejora la alternativa del plan (archivo 600 en `tmpfs`); S5-D103.
- `bao server` con raft, `--read-only --tmpfs /tmp`: arranca **solo si la configuración viene de un archivo montado `:ro` con `-config=`**. Con `BAO_LOCAL_CONFIG` el entrypoint escribe `/openbao/config/local.json` y aborta ("Read-only file system"). El volumen raft se monta en `/openbao/file` (propiedad `openbao`). Init 1/1, desello por `wget` y `transit` con `apex-kek` (`aes256-gcm96`, `exportable=false`, `allow_plaintext_backup=false`): funcionan. `GET /v1/sys/health?sealedcode=200&uninitcode=200` responde con `wget`.
- Compose de prueba con `internal: true` (subred fija) y `volumes: !override` / `depends_on: !override`: renderiza como se espera (el volumen `keys` desaparece del servicio y del compose).

**`apex-db-1` (solo `SELECT`).** `members.members`: 285 filas. `crypto.crypto_keys`: `local|active|8`. `pg_roles apex%`: `apex` superusuario (`rolsuper = t`), `apex_api`, `apex_backup` y `apex_worker` no. Última fila de `worker.job_runs`: `expirations` del 2026-11-04, `result = ok`, `details {"otras": 0, "errores": 0, ...}`. Esquema de `job_runs`: `job_name, run_date, started_at, finished_at, result, error, details` (no `status`).

**Gates baratos en HEAD.** `ruff check` 0; `ruff format --check` 595 archivos ya formateados; `mypy src` 151 archivos sin problemas; `tsc --noEmit` 0; `bash scripts/workflow/tests/run.sh` 6 de 6 archivos (23 ok, 0 fallas en el último).

## W0-1 · Verde documental (2026-11-04)

- **T-DOC.** `SPRINT-05.md` (nota de cabecera, sección "Slices y orden de ejecución", migraciones `0015` a `0019`, `POST wa-link`, DoD con "reinicio de servidor", sin `reportlab`); `BREAKDOWN.md` de EP-14, EP-15 y EP-16 (nota de cabecera; US-123 y US-126 a READY con la línea de estado en el formato de `verificar.mjs`); notas y correcciones mínimas en US-123 a US-127, US-131 y US-133 a US-139; `docs/design/ROUTES.md` (`wa-link` POST); `CLAUDE.md` (estructura, `sign_audit` en v0.3, `cli_manifest.py`, `compose.openbao.yml`, `infra/openbao/`, bloque de binarios con `curl`); `RUNBOOK.md` (rotación existente); `04_architecture_decision.md` §4; `BRECHAS.md` (§4 D4 y §13 nueva con 12 filas). `memberships/events.py` queda para B7.
- **DECISIONES.** Sección "Sprint 5 · decisiones de implementación" al final: 18 contradicciones, S5-D1 a S5-D101 (D1 a D48 del blueprint con "Forma final" del plan, D49 a D63 de seguridad, D64 a D101 del plan), contradicciones de contrato de T-DOC, Q1 a Q10 y la sección de W0-1 con S5-D102 (puerto de Mailpit, propuesta), S5-D103 (desello por API con `wget`), S5-D104 (configuración por archivo y usuario de la imagen), S5-D105 (`curl`) y S5-D106 (custodia 2/2/1: el plan la cita como "D82" por error, S5-D82 es la exportación).
- **ADR-005.** `docs/adr/ADR-005-custodia-openbao.md` (seis secciones), entrada en `docs/adr/README.md` y `test_adr_docs.py` con los cinco archivos: rojo primero (5 fallos), luego 9 passed. Las pruebas propias de OpenBao se citarán en el ADR cuando existan (B1 a B3).
- **Dependencias y licencias.** `uv add --dev pypdf` (6.21.4, BSD-3; `uv.lock` entra al checkpoint; fuera del runtime, `pip-licenses` del runtime no lo lista). `check-licenses-api.sh` verde. `test_licenses.sh` con el caso nuevo `python-telegram-bot`: 0 fallas (fpdf2, python-telegram-bot, sin licencia y runtime). El caso nuevo no podía estar en rojo: el chequeo ya rechaza toda LGPL; es un caso de control. `notice.sh` suma `curl`, OpenBao, Mailpit, `python:3.12-alpine` y `pypdf`; segunda corrida idéntica (`cmp`).
- **Gates.** `ruff check` y `ruff format --check` de `test_adr_docs.py` en verde; `tests/architecture` 533 passed; `verificar.mjs` sin errores nuevos (queda el preexistente de EP-00/US-008).
- **Sin sello ni checkpoint:** esperan al mensaje del orquestador tras el `security-reviewer` de T-DOC.

## W0-1 · Revisión

`security-reviewer` de T-DOC y decisiones: 0 CRITICAL, 0 HIGH, 1 MEDIUM, 2 LOW; 3 de 3 corregidos.
- MEDIUM (S5-D103, ADR-005 punto 3): el desello documentado ponía la llave en la línea de la shell. Ahora `set +o history; read -rs K && printf ... "$K" | ... wget ... --post-file=/dev/stdin ...; unset K; set -o history`; los scripts y `docs/operacion/openbao.md` de W0-2 deben leerla con `read -rs`, nunca por argumento ni por `printf` literal.
- LOW (S5-D102): Mailpit en 8125 confirmado; sin "propuesta"; el plan (P-MAIL, W0-1.1, B4) y el cuaderno unificados en 8125.
- LOW: la custodia ya no se cita como "D82" sino como S5-D106 (tres menciones del plan; las de exportación se quedan en D82).

## W0-1 · Evidencia

Checkpoint `52b1922` (`chore(checkpoint): S5-W0-1 ...`). Sello `slice-gate.sh architecture tests/architecture/test_adr_docs.py`: 533 passed. `ruff check` y `ruff format --check` de `test_adr_docs.py`, `test_licenses.sh` (0 fallas) y `check-licenses-api.sh` en verde; `NOTICE` regenerado dos veces sin diferencias.

## W0-2 · Rojo (2026-11-04, HEAD `b4e1dc1`, árbol limpio al empezar)

**Línea base (antes de tocar nada), todo en verde:** `test_compose_config.sh` 168 ok / 0 fallas; `test_deploy_script.sh` 191 ok / 0; `test_images_pinned.sh` 11 ok / 0; `scripts/workflow/tests/run.sh` 6 de 6 archivos (153 ok).

**Stubs creados (solo para que los arneses tengan qué comprobar):** `infra/openbao/{config.hcl (comentario),bootstrap.sh,dev-entrypoint.sh}` (los dos .sh con exit 99), `infra/openbao/policies/{apex-api,apex-worker,apex-tools,apex-backup-snapshot}.hcl` (vacías), `scripts/dev/openbao-seal.sh` y `scripts/ci/openbao-smoke.sh` (exit 99), `infra/compose.openbao.yml` (`services: {}`, renderiza con `config -q`), `docs/operacion/openbao.md` (título + pendiente W0-2.5).

**Arnés nuevo y cambios:**
- `scripts/ci/test_openbao_infra.sh` (nuevo, 76 comprobaciones). Validado en verde contra un árbol de ejemplo temporal con scripts y políticas correctos (76 ok / 0 fallas; árbol borrado): el Verde puede satisfacerlo.
- `test_compose_config.sh`: 3 renders nuevos (`--profile bootstrap`; overlay `compose.openbao.yml`; desarrollo con `--profile openbao`) y 69 aserciones S5; las dos literales de volúmenes (`:92-93`) ahora exigen `openbao-data` y `openbao-token-{api,worker,tools}`.
- `test_images_pinned.sh`: exige `openbao/openbao:2.7.2@sha256:5046911075e137e154ce49ab051502f4ec7cf367d484ae4a4dce665d9b90561f` en `compose.yml` y `ci.yml` (más `docker pull` y `services.openbao.image` en ci.yml); la fecha y el comando de renovación los revisa el bucle existente.
- `test_deploy_script.sh`: `mk_repo` suma `MIGRATE_DB_USER=apex_owner` a `.env.ops`; 3 bloques nuevos (sellado, overlay y kek.bin, rol). Falsos: `fakes/docker` gana `FAKE_DOCKER_ROLE_EXISTS` (responde a `psql`) y `FAKE_DOCKER_KEK_PRESENT` (responde a cualquier comando que nombre `keys/kek.bin`); `fakes/curl` gana `FAKE_CURL_HTTP` (con HTTP >= 400 y `-f` o `--fail` sale con 22 sin cuerpo, como el real; sin `-f` entrega el cuerpo del 503).
- `test_wave0_gate.sh` y `test_run_gates.sh`: `test_openbao_infra` se llama y su fallo detiene; el gate renderiza `-f compose.yml -f compose.openbao.yml`, `--profile bootstrap -f compose.yml` y `--profile openbao -f compose.yml -f compose.dev.yml`.

**Conteo en rojo (ok / fallas):** `test_openbao_infra` 41 / 35 (stubs 99, políticas vacías, config sin directivas); `test_compose_config` 186 / 51 (2 literales de volúmenes y 49 S5: servicio `openbao`, `custody`, bootstrap, tokens, redes, healthcheck, overlay, desarrollo); `test_deploy_script` 202 / 24 (los 191 viejos siguen verdes; 11 casos nuevos ya los cumple deploy.sh, p. ej. 503 con db no ok sale con 1); `test_images_pinned` 13 / 4; `test_wave0_gate` 23 / 7; `test_run_gates` 26 / 2; `run.sh` 4 de 6 archivos; `test_infra_scripts` 1 falla (arrastra la de deploy). Todos los casos nuevos fallan por aserción real. `bash -n` limpio en los 12 scripts tocados o nuevos. `docker compose --env-file .env --env-file .env.ops -f infra/compose.yml -f infra/compose.openbao.yml config -q` sale 0.

**Dudas para el Verde (numeradas):**
1. Dueño de los volúmenes `openbao-token-*`: la imagen corre con uid 100 / gid 1000 y api, worker y tools con 10001. Propuesta: `openbao-bootstrap` corre como root con `cap_drop: [ALL]` y `cap_add: [CHOWN]` (el arnés lo exige), escribe cada token con `umask 077` y hace `chown 10001:10001` y `chmod 600` por archivo. El volumen vacío nace root:root, así que los archivos quedan legibles solo por el uid 10001. Verificar en W0-2.7 con Docker real (un root sin `DAC_OVERRIDE` sigue siendo dueño de lo que crea).
2. `openbao` (servicio largo): `user: "100:1000"` (el arnés solo pide usuario fijo no raíz). El volumen `openbao-data` nuevo nace root:root: `bootstrap` también debe hacer `chown 100:1000` sobre él (ya tiene `CHOWN`) o se precrea; con `cap_drop: ALL` el servidor no puede hacerlo solo. Ojo con el orden: `api`/`worker` dependen de `openbao: service_healthy` y `openbao` necesita el volumen escribible para arrancar.
3. Destino del token en api, worker y tools: el arnés solo exige `:ro` y propietario único; el plan no fija ruta. Propuesta `/run/apex/openbao/token` (carpeta propia del volumen) y que `OpenBaoProvider` lea el archivo (`OPENBAO_TOKEN_FILE`). `tools` conserva `keys` con escritura (`migrate-provider` la necesita) y recibe su token.
4. Healthcheck del api sin curl: el arnés exige `["CMD","python","-c", <guion>]` con `127.0.0.1:8000/health`, `HTTPError`, `503`, `db`, `migrations` y "ok" al menos dos veces, sin `curl`. El guion va en una línea (YAML): intenta `urlopen`; ante `HTTPError` con código 503 lee el cuerpo JSON; sale 0 si (200) o (503 con `db == "ok"` y `migrations == "ok"`).
5. `deploy.sh` y el rol (S5-D96): contrato del falso: una llamada `docker compose ... exec -T db psql ...` cuya línea contenga `psql`, el nombre del rol (`apex_owner`) y ` db `; sin fila (`FAKE_DOCKER_ROLE_EXISTS=0`) sale 2 con el mensaje exacto del plan, ANTES de `build`, `up` y `tag prev-`. `MIGRATE_DB_USER` ausente o vacía en `.env.ops` → 2 en la preverificación (sin docker salvo `config -q`); `.env.ops.example` debe traer `apex_owner`. Falta decidir con qué usuario corre `psql -U` (probablemente `POSTGRES_USER`).
6. `deploy.sh` y el overlay: con `CRYPTO_PROVIDER=openbao` en `.env` agrega `-f infra/compose.openbao.yml` a TODO `compose` (también `config -q` y `up -d`); si el archivo no existe, sale 2 con un mensaje que nombra `compose.openbao.yml` y sin docker salvo `config -q`. Con `local` (o variable ausente) no lo aplica. Su posición respecto del `checkout` queda a criterio del Verde (el overlay llega con el código nuevo; el arnés no fija el orden).
7. `kek.bin`: el falso responde a cualquier comando de docker que contenga `keys/kek.bin` (p. ej. `compose ... run --rm --no-deps tools test -f /run/apex/keys/kek.bin`); aviso exacto `aviso: kek.bin sigue en el volumen keys`, solo con `openbao`, salida 0. "`openbao` entra en el `up -d`" se comprueba como: la línea `up -d` lleva el overlay y el reporte final nombra `openbao`; si el Verde prefiere nombrar el servicio en el `up -d`, se ajusta esa aserción.
8. Sondeo con curl: el falso solo entiende `-f` y `--fail` para simular el HTTP; si el Verde usa `-w` con `%{http_code}`, hay que extender `fakes/curl`. La salud sigue pidiendo `"db":"ok"` y `"migrations":"ok"` (con o sin espacio tras los dos puntos).
9. Política del api: el plan (paso 7) la fija en `encrypt`, `decrypt` y `renew-self` y el arnés lo exige EXACTO (también worker y tools con sus dos y seis rutas). Eso deja fuera `sign`/`verify` de `apex-sign-audit` y `read` de llaves que mencionaba S5-D11; si un slice B los necesita, se amplían arnés y política juntos.
10. `custody`: el arnés pide subred /24 que no solape con `default`; D77 da `${APEX_CUSTODY_SUBNET:-172.30.1.0/24}`. `.env.ops.example` suma `APEX_CUSTODY_SUBNET`; el ensayo (`172.31.12.0/24`) y el smoke (`172.31.13.0/24`) la sobrescriben.
11. Desarrollo: `openbao-dev-data` solo en `compose.dev.yml` (el arnés lo exige ausente de `compose.yml`) y `APEX_ENV=dev` en el entorno del servicio de desarrollo (guarda de `dev-entrypoint.sh`); `entrypoint` o `command` nombra `dev-entrypoint`.
12. `wave0-gate.sh`: las tres combinaciones nuevas se omiten si falta `infra/compose.openbao.yml`, igual que `compose.verify.yml` (`test_wave0_gate` crea el archivo en el repo temporal). `run-gates.sh` suma `test_openbao_infra` a su bucle.
13. `ci.yml`: el arnés de imágenes exige `services.openbao.image` por digest, al menos un `docker pull` con el digest, y que ninguna mención de `openbao/openbao:` quede sin él.

## W0-2 · Verde (2026-11-04, sobre HEAD `b4e1dc1` + Rojo sin confirmar; sin commit, sin sello, sin W0-2.7)

**Conteos finales (ok / fallas):** `test_openbao_infra` 76 / 0; `test_compose_config` 239 / 0; `test_deploy_script` 232 / 0 (226 del Rojo + 6 del curl falso); `test_images_pinned` 20 / 0; `scripts/workflow/tests/run.sh` 6 de 6 archivos; `test_infra_scripts` 0 fallas; api: `test_env_example` + `test_config` + `test_export_openapi_cli` 144 pasan, `ruff` y `mypy src` limpios; `bash -n` limpio en `infra/openbao/*.sh`, `scripts/dev/*.sh`, `scripts/ci/*.sh`, `infra/deploy.sh` y `scripts/workflow/**/*.sh`; `ci.yml` parsea con PyYAML (7 jobs); renders `config -q` en verde para `compose.yml`, `--profile bootstrap`, overlay `compose.openbao.yml`, dev con `--profile openbao` y dev solo.

**Entregado:** `infra/openbao/{config.hcl,bootstrap.sh,dev-entrypoint.sh,policies/*.hcl}`, `scripts/dev/openbao-seal.sh`, `scripts/ci/openbao-smoke.sh`, `infra/compose.yml` (servicios `openbao` y `openbao-bootstrap`, red `custody`, 4 volúmenes, `depends_on`, healthcheck del api tolerante, `tools` endurecido), `infra/compose.openbao.yml`, `infra/compose.dev.yml` (`openbao` con perfil y `openbao-dev-data`), `.env.ops.example` (`APEX_CUSTODY_SUBNET`, `MIGRATE_DB_USER`), `infra/deploy.sh`, `scripts/ci/{compose-smoke,prod-smoke}.sh`, `scripts/workflow/{wave0-gate,run-gates}.sh`, `.github/workflows/ci.yml`, `docs/operacion/openbao.md`, `infra/README.md`, RUNBOOK §7 y §13, DECISIONES S5-D107 a S5-D113.

**Contenedor desechable (imagen fijada, bandera por bandera igual a la de Compose):** `/openbao/file` es `openbao:openbao` (100:1000) en la imagen y el volumen nombrado nuevo lo hereda: no hace falta `chown` ni `init`; `server` arranca con `read_only`, `tmpfs /tmp`, `cap_drop ALL`, `no-new-privileges` y usuario 100:1000. `bootstrap.sh --first-install` de punta a punta con `cap_drop ALL` + solo `CHOWN` como root: tokens `-rw------- 10001:10001` en carpetas `root:root` 755; tras reiniciar, sellado (3/5); desello normal con tres llaves por stdin; `--first-install` sobre inicializado, rechazado; token del api: cifra, descifra y renueva (768 h), NO rota ni lee la llave; worker NO cifra; tools rota y cambia `config` y no puede borrar; `--reissue-tokens` con tres llaves: token nuevo, el viejo revocado, sin intento de generación pendiente. `dev-entrypoint.sh`: se niega sin `APEX_ENV=dev`; init 1/1, llave en el volumen con modo 600, 0 apariciones de llaves o raíz en `docker logs`, `seal` con el token de sellado, reinicio y desello solo. Todos los contenedores, volúmenes y la red desechables se borraron (`docker ps -a`/`volume ls` sin restos); no se tocó ningún proyecto Compose.

**Desviaciones (numeradas):**
1. `test_compose_config.sh` (assert original, línea 375): "worker monta exactamente backups" contradecía la aserción nueva (`openbao-token-worker` montado solo en worker, `:ro`). Se cambió a "exactamente backups y su token, ambos de solo lectura". Mínimo y registrado; el Rojo no lo había visto.
2. `bootstrap.sh` no es bash sino `ash` (la imagen no trae bash ni jq; S5-D109) y no usa `bao operator generate-root`/`-decode` (OpenBao 2.7.2 los manda a una ruta con token; S5-D107): API genérica y decodificación manual. Hizo falta `disable_unauthed_generate_root_endpoints = false` y `disable_unauthed_rekey_endpoints = false` en el listener.
3. Duda 1 y 2 del Rojo: `CHOWN` solo (el arnés lo exige) alcanza porque los archivos se crean root, `chmod` antes y `chown` después, y se reescriben con `mv`; `openbao-data` no necesita nada (la imagen ya la deja 100:1000).
4. Duda 3: el token va en `/run/apex/openbao/token` (volumen montado en la carpeta, `:ro`); `OPENBAO_TOKEN_FILE` solo en `compose.openbao.yml` (no en `compose.yml`).
5. Duda 8: `fakes/curl` extendido con `-o` y `-w %{http_code}`, con 6 casos en `test_deploy_script.sh`.
6. Duda 9: política del api exacta (encrypt, decrypt, renew-self); `apex-sign-audit` queda sin política hasta v0.3 (nota para B-slices: los tokens no tienen política `default`, S5-D108, y no pueden hacer `lookup-self`).
7. Token de `apex-backup-snapshot`: solo su política; el token llega con B13 (no hay volumen ni consumidor). El plan decía "cuatro tokens".
8. `NON_API_ENV_VARS` y `test_env_example.py` ganaron `APEX_CUSTODY_SUBNET` y `MIGRATE_DB_USER` (Python tocado fuera del cuaderno de infra; sin ello el ejemplo de `.env.ops` fallaba `test_las_claves_de_operacion_estan_en_non_api_env_vars`). Nota: `slice-gate.sh core/config` queda para el sello de W0-2 (no se corrió; instrucciones).
9. `prod-smoke --provider openbao` no pone `CRYPTO_PROVIDER=openbao` en el api (no hay proveedor hasta B1) y deja la comprobación de `kek.bin` para B2; `openbao-smoke.sh` cubre solo lo de infraestructura (S5-D113). **No se ejecutó** (prohibido `up`): solo `bash -n`; se ejecutó en W0-2.7.
10. `test_images_pinned`: el comentario sobre cada `image:` de OpenBao no puede nombrar `openbao/openbao:<tag>` sin digest (la aserción de "sueltas"), así que el comando de renovación va con el digest en compose/ci y la consulta del tag nuevo en RUNBOOK §7.
11. `deploy.sh`: `openbao` figura en el mensaje de arranque ("openbao, migrate y dbsetup corren solos antes del api") y en el reporte final ("proveedor de llaves openbao"); el `up -d` queda sin lista de servicios (Compose arranca `openbao` porque no tiene perfil).

**Pendiente (para el orquestador):** `security-reviewer` de W0-2 (políticas, bootstrap, logs, red, montajes, overlay, `deploy.sh`; ojo especial a S5-D107 y al `exec ... psql` de `deploy.sh`); `slice-gate.sh core/config` y sello `wave0-gate.sh W0-2`; W0-2.7 (Docker de verdad: `up` de `openbao` en `apex`, ensayo, `openbao-smoke.sh` real y `docker stats`); checkpoint `S5-W0-2 ...`. Nota de ejecución: los scripts nuevos no llevan bit `+x` desde Windows (se invocan con `bash`).


**Desviaciones de W0-2.7 (corrida del ensayo, 2026-11-04):**
1. `prod-smoke.sh` fallaba en `deploy_e2e.sh` ("el rol apex_owner no existe", salida 2): `deploy.sh` exige el rol `MIGRATE_DB_USER` (S5-D96) y el `.env.ops` del humo traía `apex_owner` del ejemplo, que no existe hasta W0-4. Corregido con prueba primero (`test_deploy_script.sh`, rojo 237/1 y verde 238/0): `prod-smoke.sh` fija `MIGRATE_DB_USER` al propietario (`apex`) con `fijar`. `TOOLS_DB_USER` no existe en el repositorio; no se añadió. `deploy_e2e.sh` copia el `.env.ops` del humo, no genera el suyo.
2. El ensayo con volúmenes nuevos necesita `init-keys` antes del primer `up` (como en 4B); sin él el api sale con "Faltan secretos".
3. `bootstrap.sh --first-install` pide, además de `INICIALIZAR`, escribir `GUARDADAS` tras mostrar las 5 llaves; y ya desella con tres llaves él mismo (no se observa el estado "sellado tras init").
## W0-2 · Revisiones (security-reviewer: 0 CRITICAL, 0 HIGH, 2 MEDIUM, 4 LOW; todo corregido)

Decisiones S5-D114 a S5-D119 (y S5-D107 reescrita) en `docs/ddd/DECISIONES.md`. Cambios: M1 segundo listener `127.0.0.1:8210` con `generate-root` y `rekey` abiertos solo ahí, `openbao-bootstrap` con `network_mode: service:openbao` y `BAO_ADDR=http://127.0.0.1:8210`; M2 `limpiar` revoca la raíz del entorno; L1 `printf '\033c'` tras `GUARDADAS`; L2 `trap ... EXIT` del temporal del sondeo de `deploy.sh`; L3 comentario alineado en `ci.yml`; L4 `OPENBAO_TOKEN_FILE` entra en `Settings` en W0-3/B1 y `OpenBaoProvider` no usa `lookup-self`.

**Prueba primero:** los arneses se ajustaron antes de tocar el código y fallaron donde debían (config con un solo listener; `bootstrap` sin `limpiar` revocando; `openbao-bootstrap` aún en `custody`). Contenedor desechable con la configuración nueva: 8200 responde 405 a `sys/generate-root/attempt` y `sys/rekey/init`; 8210 los acepta; `--first-install` y `--reissue-tokens` completan por 8210 (token nuevo, viejo revocado); con un intento ajeno abierto, `--reissue-tokens` aborta con el comando real y no lo cancela. Recursos desechables borrados.

**Conteos tras las correcciones (ok / fallas):** `test_openbao_infra` 81 / 0; `test_compose_config` 240 / 0; `test_deploy_script` 237 / 0; `test_images_pinned` 20 / 0; `scripts/workflow/tests/run.sh` 6 de 6; `test_infra_scripts` 0 fallas; `bash -n` de todo `infra/` y `scripts/` limpio; renders `config -q` base, `--profile bootstrap`, overlay y dev con `--profile openbao` en verde; `slice-gate.sh core/config` verde (674 pruebas, sello `core/config`).

## W0-2 · Evidencia (W0-2.7, ensayo `apex-ensayo` y humo en Linux, 2026-11-04; checkpoint `e40c5f3`)

- **Imágenes:** `apex-api:local` id `2267ce8b49df` (GIT_SHA `b4e1dc1`, buildx 15 s); OpenBao `openbao/openbao:2.7.2` id `5046911075e1` (el mismo en `openbao` y en `openbao-bootstrap`, por digest).
- **Ensayo:** `$DCE up -d` falló la primera vez por llaves ausentes; tras `init-keys` (KEK, firma, JWT) migrate y dbsetup salieron 0 y db, api, web, worker, backup y openbao quedaron healthy. `bao status` antes del bootstrap: Initialized false, Sealed true.
- **Bootstrap 5/3** (auxiliar `docker:cli`, `pty.fork`, `run --rm --no-deps openbao-bootstrap --first-install`, respuestas `INICIALIZAR` y `GUARDADAS`): salida 0; transit, `apex-kek`, `apex-sign-audit`, 4 políticas, 3 tokens (modo 600, dueño 10001) y raíz revocada. Las 5 llaves quedaron solo en `docs/scratch/ensayo/openbao/llaves-ensayo.txt` (ensayo desechable, ignorado por git; el chmod 600 no aplica en NTFS); no se imprimieron ni están en ningún log ni archivo versionado. `docker inspect` de un contenedor creado con `compose create`: `LogConfig.Type=none`, Tty true, user 0:0, cap_add CHOWN, cap_drop ALL, rootfs de solo lectura. `bao status` tras el bootstrap: inicializado, desellado, 5/3.
- **Sellado/desello:** `restart openbao` -> Sealed true (Unseal Progress 0/3) con el api healthy; desello con 3 llaves por `wget --post-file=/dev/stdin` (progreso 1, 2, desellado) -> 5/3.
- **Red:** desde el api `openbao:8210` -> Connection refused; `openbao:8200/v1/sys/health` -> 200; `sys/generate-root/attempt` por 8200 -> 405 (GET y PUT).
- **`test_db_roles.sh` sobre el ensayo:** 0 fallas.
- **Humo de producción (auxiliar Linux, `SMOKE_WEB_PORT=8380 SMOKE_DOWN=1 --no-build`):** 1.ª corrida 15:29:17 a 15:31:28 (2 min 11 s), EXIT 1: 97 ok y 11 FALLA, todas por `deploy_e2e` (rol `apex_owner` inexistente; desviación 1, corregida con prueba primero). Tras la corrección y el resello: sin `--provider` 15:48:20 a 15:51:53 (3 min 33 s), EXIT 0, "todo en verde", 0 FALLA; con `--provider openbao` 15:52:00 a 15:55:47 (3 min 47 s), EXIT 0, "todo en verde" incluido `openbao-smoke.sh` (reinicio -> sellado, api healthy sellado, desello con otras tres llaves). `grep -iE 'PASSWORD|SECRET-KEY|AGE-SECRET|BAO_TOKEN|hvs\.'` sobre ambos logs: 0. Auxiliar y volumen borrados; `apex-smoke` inexistente.
- **Pruebas tras la corrección:** `test_deploy_script` 238/0 (rojo previo 237/1), `test_infra_scripts` 0 fallas, `test_openbao_infra` 81/0, `test_compose_config` 0 fallas, `scripts/workflow/tests/run.sh` 6 de 6, `bash -n` de los tocados. `wave0-gate.sh W0-2`: 533 passed en `tests/architecture`, sello escrito.
- **`docker stats --no-stream` (ensayo):** web 8,8 MiB, worker 77,5, backup 10,0, api 91,6, db 53,2, openbao 23,7; CPU ~0 %.
- **Estado final:** dev (api, worker, web, backup, db, db_test) healthy; `apex-ensayo` arriba con openbao desellado (5/3).


## W0-3 · Rojo (2026-11-04)

**Línea base** (antes de tocar nada): `pytest tests/migrations + test_config + test_env_example + test_logging_redact + architecture/{test_user_limits_catalog,test_settings_no_secrets,test_no_sensitive_in_logs}` 616 passed. `test_deploy_script.sh` 238 ok / 0 fallas. `test_env_isolation.sh` 11 fallas ya existentes (el stack de desarrollo trae `.env` suma de los dos ejemplos; la prueba es para un stack de producción: no es del slice). Nota: `test_user_limits_catalog.py` vive en `tests/architecture/`, no en `tests/core/`.

**Rojo por archivo (fallan / total del archivo tras el Rojo):**
- `tests/migrations/test_0015_crypto_provider_migration.py`: 8 rojas / 31. Las aceptaciones (local->openbao, openbao->local, rewrap x2, decrypt_only, propietario sobre `apex_roles`) fallan con `CheckViolationError` de la guarda de `0003`; `la_guarda_en_head_ya_no_es_la_de_0003` y el ciclo `downgrade` fallan porque el cuerpo sigue siendo el de `0003`. Las 23 verdes son guardas de lo que debe seguir rechazado (provider sin material, state+material, columnas fijas, fila `sign`, `ALWAYS`, roles sin UPDATE).
- `test_0014_*`: 44 verdes; "es head" pasó a "en la cadena de head" (verde con el stub).
- `tests/core/test_config.py`: 46 rojas / 164 (`AttributeError`/`ValidationError` reales; `_rechaza` exige que el campo exista en `Settings` para que `extra="forbid"` no dé falsos verdes). Se añadieron `NUEVAS_S5` y `TOOLS_DB_USER` al borrado de entorno.
- `tests/core/test_env_example.py`: 11 rojas / 36 (una es la reparada `test_el_comentario_de_s4a_b3...` que ahora pide 16 cubetas y 15 variables).
- `tests/core/test_ratelimit.py`: 2 rojas (reparadas: dict completo de `user_limits_from` y `len == 16`).
- `tests/architecture/test_user_limits_catalog.py`: 1 roja (`CLAVES_SIN_RUTA_TODAVIA` con las cuatro cubetas, que aún no están en `USER_LIMITS`).
- `tests/core/test_logging_redact.py`: 13 rojas / 37 (patrón `bot\d+:`, cuatro `SENSITIVE_KEYS`); la de `httpx`/`httpcore` en WARNING ya era verde (guarda).
- `tests/architecture/test_no_sensitive_in_logs.py`: 3 rojas; `test_settings_no_secrets.py`: 1 roja.
- `tests/migrations/test_db_grants.py`: 27 rojas / 154 (matriz `PRIVILEGIOS` actualizada para 4 pares; `PROHIBIDAS_WORKER` pierde `crypto_keys` y gana `SELECT document`; `PROHIBIDAS_API` suma tres UPDATE de `auth.users`).
- `tests/migrations/test_worker_role_paths.py` (nuevo): 2 rojas / 5; tres guardas verdes (recompute, `names_for`, carga con `load_only`) que protegen el paso a `SELECT` por columna.
- `scripts/ci/test_env_isolation.sh`: 7 fallas nuevas (sección estática sobre `compose --profile '*' config`); `test_deploy_script.sh`: 8 fallas nuevas (242 ok). `scripts/ci/fakes/docker` suma `FAKE_DOCKER_API_ENV_EXTRA` y `FAKE_DOCKER_WEB_ENV`.
- Total pytest: 114 rojas / 803; `ruff check`, `ruff format --check` y `mypy src` limpios; `bash -n` de los tres arneses limpio.

**Dudas para el Verde**
1. Nombre del token: las pruebas usan `OPENBAO_TOKEN_FILE` (el de `compose.openbao.yml`; el plan decía `OPENBAO_TOKEN_PATH`). `missing_secrets` debe nombrar `OPENBAO_TOKEN_FILE`. Anotarlo en DECISIONES.
2. `auth.users` UPDATE de `apex_api`: inventario del Rojo = `email, password_hash, role, deleted_at, locked_at, last_login_at, must_change_password, failed_login_count, tokens_valid_after, updated_at` (asignaciones de `modules/auth` links/sessions/tokens/users). Confirmar con `cli seed`/`unlock` y cualquier otro escritor antes de cerrar `grants.sql`; `is_active` y `member_id` quedan fuera.
3. `names_for` selecciona `Member.sex`, que NO está en la lista de columnas del worker del plan (D204). O se añade `sex` a la lista (y a la constante `COLUMNAS_WORKER_MEMBERS`) o `names_for` deja de pedirla. Lo detecta `test_names_for_corre_como_apex_worker` cuando cambie el grant.
4. Cómo parchear `guard_keys_update` sin romper `0014`: `0014` solo re-arma los triggers por nombre; `0015` hace `CREATE OR REPLACE` (sin tocar triggers) y el `downgrade` debe reponer el cuerpo literal de `0003` (la prueba lo compara con el texto de `0003` con `{ERR}` resuelto, normalizando espacios). Mensajes de error: deben empezar por `crypto.crypto_keys` y usar `check_violation`.
5. `BACKUP_SIGN_PUBKEY` pasa a `Settings` (opcional, formato minisign `RW` + 54 caracteres base64, 56 en total): `ops_secret_names` con el prefijo `BACKUP_SIGN_` hoy la marca como secreto de operación; hay que exceptuarla (la prueba exige que `BACKUP_SIGN_KEY_FILE` siga marcada).
6. `SMTP_*` todo o nada = `SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM` (puerto y modo tienen defecto); `SMTP_TLS_MODE` admite `starttls` (defecto) y `none`. Si el diseño prevé `tls` implícito, ampliar la prueba.
7. El comentario del catálogo en `.env.example` debe seguir dentro de las 4 líneas previas a `USER_READ_LIMIT_PER_MIN=` (lo exige la prueba S4A reparada) y decir "16 cubetas" y "15 variables" y citar "S4A-B3, M-1 y M-3".
8. `ci.yml`: la prueba exige `[ "$subidas" = "15" ]`, el mensaje "se esperaban 15 cubetas USER_* subidas" y las cuatro `USER_*` al menos dos veces (sed y regex del conteo).
9. `deploy.sh` debe leer `/proc/1/environ` de `web` (`exec -T web`) y prohibir `SMTP_*`/`TELEGRAM_*`; para el api suma `POSTGRES_*` a la regex (sin imprimir valores). `compose.yml` debe dar a `api`/`worker` `SMTP_PASSWORD` y `TELEGRAM_BOT_TOKEN` y a `api`/`worker`/`tools` `OPENBAO_TOKEN_FILE` (la sección estática de `test_env_isolation.sh` lo comprueba con `compose --profile '*' config`).
10. `test_worker_role_paths` siembra socio/plan/membresía sin limpiar (una membresía no se borra: trigger); `apex_roles` se descarta al terminar la sesión.

## W0-3 · Verde (2026-11-04)

**P-MIG en `apex-db-1`:** volcado `docs/scratch/sprint-05-antes-0015.dump` (1.652.789 bytes, `.gitignore:47:*.dump`; se borra en V12). `$DC stop api worker` antes de escribir `0015`. `$DC start api` aplicó `0014 -> 0015`; `alembic current` = `0015_crypto_provider_migration (head)`; `crypto_keys` = 8 antes y después; `crypto_keys_guard` y `crypto_keys_forbid_truncate` en `A` (17 triggers no internos en `A`). `\df+` / `pg_get_functiondef`: antes el cuerpo de `0003` (32 líneas), después el nuevo (51). Ciclo `downgrade -1` (cuerpo = `0003`, md5 anotado) -> `upgrade head` -> `current` 0015. Api y worker `healthy` al terminar.

**En verde por archivo:** `test_0015` 31/31; `test_worker_role_paths` 5/5; `test_db_grants` 154/154; `test_0014` 44/44; `test_config` 164/164; `test_env_example` 36/36; `test_logging_redact` 37/37; `test_ratelimit` 45/45; `test_user_limits_catalog` 9/9; `test_settings_no_secrets` 10/10; `test_no_sensitive_in_logs` 6/6. Cobertura (solo con esos dos archivos de prueba): `config.py` 93 %, `logging.py` 78 % (el resto de `logging.py` lo cubren las pruebas del middleware).

**Gates (slice-gate):** `core/logging` 577 verde; `memberships` 545; `members` 569; `core/config` 969; `test_deploy_script.sh` 0 fallas; `test_env_isolation.sh`: 11 fallas, las mismas 11 de la línea base (parte dinámica sobre un `.env` de desarrollo, suma de los dos ejemplos); la parte estática nueva pasa. `ruff check`, `ruff format --check`, `mypy src` limpios.

**Desviaciones:**
1. `tests/core/test_ratelimit.py::CATALOGO` (el Rojo no lo actualizó) fijaba las 12 cubetas: se le añadieron las 4 de D81.
2. `sex` en el `SELECT` por columna del worker (S5-D122): `COLUMNAS_WORKER_MEMBERS` del Rojo gana `sex`.
3. `test_env_isolation.sh` (sección estática): a `tools` solo se le prohíben `SMTP_PASSWORD` y `TELEGRAM_BOT_TOKEN`; con un `.env` de producción (copia de `.env.example`) `tools` recibe `SMTP_HOST`, `TELEGRAM_CHAT_ID`... por `env_file` y el Rojo lo trataba como `web` (S5-D128). Comprobado con una pila de producción emulada (`APEX_ENV_DIR`), borrada después.
4. `memberships/expirations.py` no selecciona `Member`: no necesitó `load_only` (el paso 18 lo preveía). Solo `members/contact.py`.
5. `prod-smoke.sh` no se tocó: su reparto lo cubre `test_env_isolation.sh`, que ya invoca; `web` solo se comprueba en `deploy.sh`.
6. El `.env` de desarrollo se amplió solo con las claves nuevas de `Settings` (+ `TOOLS_DB_USER`); `SMTP_PASSWORD` y `TELEGRAM_BOT_TOKEN` no se añadieron (con claves en blanco `tools` los vería).
7. La `test_0015` y el nombre "S5-D120" que usé al principio en comentarios pasaron a "S5-D44, D72" (D120 ya existe).

**Decisiones nuevas:** S5-D121 a S5-D129 (bloque "S5-W0-3" de DECISIONES).

## W0-3 · Revisiones (2026-11-04)

database-reviewer: 1 HIGH, 2 MEDIUM, 2 LOW. security-reviewer: 0 HIGH, 3 MEDIUM, 3 LOW. Estado 11/11 corregidos (decisiones S5-D130 a S5-D139).
- HIGH: confirmado en rojo (`42501` al registrar un pago como `apex_api`); arreglado en el ORM con `FetchedValue()` (D130). `tests/migrations/test_api_role_paths.py`: 2 pruebas (registrar y anular con `payments.service` como `apex_api`).
- MEDIUM filas `sign`, mensaje de `upgrade`, LOW material vacío: `0015` y `test_0015` (ahora 37 pruebas; `test_0014` ajustado al mensaje nuevo). `tests/crypto/test_crypto_tables.py` pinaba «`wrapped_material` solo se rechaza»: contradecía S5-D4, usa `version = 2` (desviación 8); `test_provider_startup::test_proveedor_desconocido` pasó a llevar `OPENBAO_TOKEN_FILE` porque `openbao` ya lo exige (desviación 9).
- LOW `contact.py`: nota (D134).
- Seguridad M1/M2: `deploy.sh` (casos nuevos en `test_deploy_script.sh`: 261 ok, 0 fallas), `.env.ops.example` y RUNBOOK §12. Compose no puede quitar una clave de un `env_file`: la garantía de que `tools` no ve los secretos es que `deploy.sh` rechaza `.env` con ellos con valor. `prod-smoke.sh` ya parte de `.env.example` (sin ellas). `BACKUP_SIGN_PUBKEY` en el api vivo sale con 1 (convención del resto de comprobaciones vivas), no con 2.
- M3: `redact_text` (3 casos de `X-Vault-Token`, token suelto y control de horas/ids).
- L4: comentario de orden en `Settings` y `tests/architecture/test_settings_single_door.py` (2 pruebas). `_a_config_error` usa solo `loc` y `type` (`include_input=False`).
- L5/L6: notas.
- Suite completa (`-m "not perf"`): 6156 pasaron antes de corregir un comentario de `payments/models.py` que mencionaba un nombre de rol (`test_db_roles_confined`); `tests/architecture` entero, 542, ya en verde. 52 omitidas, 27 deseleccionadas. `ruff`, `ruff format --check`, `mypy src`, `bash -n` limpios.

## W0-3 · Evidencia (2026-11-04)

- Checkpoint `07e7bfc`. Sello `wave0-gate.sh W0-3 tests/migrations/test_db_grants.py`: 696 passed (archivos de infraestructura en verde, `tests/architecture` + `test_db_grants`); se repitió una vez porque un archivo de salida en `docs/scratch` quedó sin ignorar durante el primer sello y cambiaba la huella. Gates 1-4 de nuevo: 585, 549, 571 y 974 pasaron; `test_deploy_script.sh` 261 ok / 0 fallas; `test_env_isolation.sh` 11 fallas de la línea base. Suite completa `-m "not perf"`: 6156 pasaron y 1 falló por un comentario de `payments/models.py` (corregido; `tests/architecture` entero, 542, verde).
- W0-3.7: imagen `apex-api:local` reconstruida (`GIT_SHA=07e7bfc`); `up -d --no-build --force-recreate api worker` y `restart worker`: ambos `healthy`; `alembic current` = `0015 (head)`.
- Ensayo (`apex-ensayo`): `migrate` mostró `0014 -> 0015`; `dbsetup` terminó con «roles aplicados; 16 tablas clasificadas»; `test_db_roles.sh` 52 ok / 0 fallas; la guarda nueva está en la base (`alembic_version` 0015, texto con «provider y wrapped_material», los dos triggers en `A`); `worker --run-once expirations` terminó con `result: ok` y 0 errores como `apex_worker`; `/proc/1/environ` de `web`, `backup` y `tools` sin `SMTP_*` ni `TELEGRAM_*`. El ensayo queda arriba (api, worker, web, backup, db, openbao).
- Desviación 10: `scripts/ci/test_db_roles.sh` pinaba que `apex_worker` no puede `SELECT` de `crypto.crypto_keys` (contradice S5-D34): se actualizó la matriz (worker lee `crypto_keys` y `members` por columna; `apex_api` no actualiza `is_active` ni inserta `void_reason`). Va en un commit aparte posterior al sello.
- `apex-db-1` (desarrollo): quedó con el primer texto de `0015` (antes de las revisiones: filas `sign` rechazadas, sin material vacío, mensaje viejo). El ciclo `downgrade -1` / `upgrade head` fue denegado por el clasificador de permisos y NO se ejecutó. Pendiente humano o del orquestador: `$DC exec -T api alembic downgrade -1 && $DC exec -T api alembic upgrade head`. El ensayo y `db_test` sí tienen el texto final.
