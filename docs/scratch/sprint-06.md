# Sprint 6 · cuaderno (backend y orquestador)

Rama `feat/sprint-06-auditoria-firmada-llaves-adjuntos-tls`, HEAD de partida `0124873`.

## Planificación

- Impacto: `docs/ddd/impacto/sprint-06.md`
- Exploración: `docs/ddd/blueprints/sprint-06-exploracion.md`
- Blueprint: `docs/ddd/blueprints/sprint-06-blueprint.md`
- Diseño de seguridad: `docs/ddd/blueprints/sprint-06-seguridad-diseno.md`
- Plan (aprobado): `docs/ddd/blueprints/sprint-06-plan.md`
- Críticas del plan: `docs/ddd/blueprints/sprint-06-critica-1.md`, `sprint-06-critica-2.md`, `sprint-06-critica-3.md`

## W0-1 · línea base (2026-11-11, ~15:50 UTC, devops-wsl2-docker)

### 1.1 Estado del stack
- `$DC ps`: api, backup, db, web, worker `healthy` (Up 17 min). **`apex-db_test-1` está `Exited (255)` hace ~18 min (puerto 5443 sin escucha)**: el plan decía seis `healthy`. Hay que levantarla (`$DC up -d db_test`) antes del primer pytest; no se tocó (solo lectura). `apex-openbao-1` Exited (143) hace 6 días (perfil `openbao`, esperado).
- `alembic current` = `0020_notifications_indexes (head)`.
- `git status` al inicio: limpio (el plan ya estaba comprometido en HEAD). Durante la sesión aparecen modificados por otros agentes: `test_adr_docs.py`, `docs/adr/*`, US-140..153, BREAKDOWN EP-17..20, SPRINT-06.md, DECISIONES.md.
- `git worktree list`: solo el principal. `git log --oneline main..HEAD | wc -l` = 73 (Sprint 5 sin fusionar, paso humano).
- Imágenes (revisión `3cd752a` en todas): apex-api:local `b44a5dbd4692` (api y worker), apex-backup:local `d69bfd76b26c`, apex-web:local `bd9143cb2cf8`, db `postgres:16@sha256:9e2cf628…`.
- `docker stats`: apex-api 134 MiB, worker 85 MiB, db 53 MiB, backup 11 MiB, web 9 MiB; en el host corren además otros proyectos (dian, possi, ventasonline, motor-flujos, vi): 11.68 GiB totales.
- Aviso de Compose: `APEX_OWNER_DB_PASSWORD` sin definir (inofensivo con `.env` de desarrollo).

### 1.2 Red y puertos
- `netstat -ano` para 8280, 8380, 8443, 8200: vacío (libres). 8911 usado por la sonda y liberado.
- Redes: `apex_default` 172.30.0.0/24, `apex_custody` 172.30.1.0/24; otras 172.17, .18, .19, .20, .21, .22, .23, .24. **172.31.2.0, 172.31.3.0, 172.31.12.0 y 172.31.13.0/24 libres.**
- Docker Engine 29.9.2 (API 1.56); `docker compose version --short` = 5.6.1.

### 1.3 Digests (2026-11-11, `docker buildx imagetools inspect <tag>`)
- `caddy:2.11.3` índice `sha256:ec18ee54aab3315c22e25f3b2babda73ff8007d39b13b3bd1bfffa2f0444c7d9` (amd64: `sha256:3739ea4f0c877259a693d932693cf8f3408e9a9497c004f031b0e830e93e1546`; base alpine 3.23, creada 2026-05-12). `caddy version` = `v2.11.3 h1:/vFbdjcs2DtzcWTIxHybf5R5TspYFFThlZffChyBFHg=`. `caddy validate` con `admin off` y `tls internal { curves x25519mlkem768 }` = `Valid configuration`.
- `alpine:3.22` índice `sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f` (amd64: `sha256:9db2934886712d877c932e07249c75a59e6ca27adfbccc05261987a17bef2d63`; 3.22.8, creada 2026-11-05). `apk add --no-cache openssl` → **`openssl-3.5.9-r0`**; `openssl version` = `OpenSSL 3.5.9 29 Sep 2026`. **`openssl s_client -help 2>&1 | grep -c groups` = 2, no 1** (coinciden `-srp_moregroups` y `-groups`); para `tls-smoke.sh` usar `grep -c -- '-groups val'` o `grep -cE '^ -groups '`.

### 1.4 Supuestos en contenedores desechables
- Compose 5.6.1 renderiza `volume.subpath: custody` con target `/run/apex/keys/custody` y `ports: !override []` (puertos vacíos): OK (rc 0; el montaje base `keys:/run/apex/keys` se conserva aparte).
- `apex-web:local` con `read_only`, tmpfs, `cap_drop ALL` + `NET_BIND_SERVICE, CHOWN, SETGID, SETUID` y `no-new-privileges`: arranca, nginx master root + workers `nginx`, `GET /` 200. Necesita `api` resoluble (sin ello `[emerg] host not found in upstream "api"`; en la sonda `--add-host api:127.0.0.1`). `compose.yml` ya declara estas capacidades en `web`.
- Starlette 1.9.0, uvicorn 0.54.0; `python-multipart` ausente (`uv pip show` no lo encuentra; `import multipart` falla). App mínima con `request.stream()` bajo uvicorn: 1 MiB con Content-Length llega en 10 trozos sin spool; `Transfer-Encoding: chunked` aceptado (3 trozos, 150010 bytes, `content-length` nulo); Content-Length menor que lo enviado (10 vs 50): el flujo entrega solo 10 bytes; **Content-Length mayor que lo enviado (1000 vs 50): el flujo se queda esperando hasta que el cliente cierra y entonces lanza `ClientDisconnect`** (sin cierre del cliente no termina nunca: E13 exige tiempo máximo y tope propio por bytes leídos, no confiar en la cabecera).
- Engine 29.9.2 / API 1.56 y Compose 5.6.1 (D78: mínimos cumplidos según lo anotado en el plan).

### 1.5 `apex-db-1` (solo lectura, `default_transaction_read_only=on`)
- `members.members`: 285 filas (69 sin `deleted_at`).
- `crypto.crypto_keys` por (provider, purpose, state): `local|encrypt|active` 5, `local|index|active` 3 (8 locales activas, ninguna `sign`).
- `max(seq)` de `audit.audit_log` = 6014.
- Roles `apex%`: apex, apex_api, apex_backup, apex_worker.
- Última `worker.job_runs`: `backup_check`, 2026-11-11 15:35:04Z, `result=missing` (columna es `result`, no `status`), 1 archivo.
- `\dn`: audit, auth, crypto, members, memberships, notifications, payments, plans, public, settings, worker = 10 esquemas de aplicación + `public`; sin `attachments`.

### 1.6 Gates baratos en HEAD (sin pytest)
- `ruff check`: All checks passed. `ruff format --check`: 739 archivos ya formateados. `mypy src`: Success, 192 archivos. `tsc --noEmit` (web): 0 errores.
- `scripts/workflow/tests/run.sh`: 6 de 6 archivos en verde (30 ok, 0 fallas en el último).
- `test_compose_config.sh`: 278 ok, 0 fallas. `test_nginx_conf.sh`: 86 ok, 0 fallas. `test_openbao_infra.sh`: 101 ok, 0 fallas. `test_deploy_script.sh`: 282 ok, 0 fallas (tarda ~3 min).

## W0-1 · Rojo

- `api/tests/architecture/test_adr_docs.py` exige siete ADR (docstring, `ARCHIVOS`, pruebas renombradas y README): 5 rojas (nombres exactos, seis secciones, frase de detenerse y preguntar, pruebas citadas, README) por los dos ADR que faltaban; 4 verdes de control. Ruff y format limpios. El plan esperaba «2 fallos»: salen 5 porque cuatro aserciones leen los archivos ausentes (`FileNotFoundError`).

## W0-1 · Verde

- ADR-006 (vector `signature-payload-vector` con `through_seq=1` y el hash de la fila de ADR-004) y ADR-007; `docs/adr/README.md` con siete. `test_adr_docs.py` 9/9; `tests/architecture` 683 verdes; prueba nueva de `python-multipart` prohibido en `test_third_party_confinement.py` (62/62).
- DECISIONES con «Sprint 6 · decisiones de implementación» (sección 1 del plan, líneas 2640-2760; D81/D82 dentro, sin duplicar). T-DOC: `SPRINT-06.md` reescrito, 4 BREAKDOWN, 14 historias con «Corregido en S6», `ROUTES.md`, `CLAUDE.md`, RUNBOOK índice y §14, BRECHAS §14, `config.hcl`, `instalar-en-servidor.md`.
- Dependencias: grupo opcional `s3` (`boto3` 1.44.0, `botocore` 1.44.0, `s3transfer`, `jmespath`, `python-dateutil`, `six`, `urllib3`; `uv.lock` +88), `Dockerfile` sin el extra, `check-licenses-api.sh --extra`, `test_licenses.sh` con `oqs`/`liboqs-python` rechazados por nombre, `notice.sh` con Caddy 2.11.3 y `alpine:3.22` y venv aparte `.venv-runtime-s3` (ignorado), `NOTICE` dos veces idéntico, `ci.yml` con `uv sync --frozen --extra s3`.
- Desviaciones: US-147 corregida con cuerpo crudo (no multipart); BRECHAS 13.26 ya estaba cerrada; `tls.md`, `llaves.md` y `adjuntos.md` referenciados nacen en W0-5 y W0-4; `test_licenses.sh` instalaba `oqs` desde PyPI (red) → S6-D85 lo cambia a lista ficticia antes del sello.

## W0-1 · Revisiones

- Seguridad 0 CRITICAL, 0 HIGH, 1 MEDIUM (NOTICE sin `python-dateutil`, `six` y `urllib3` del extra `s3`: corregido en `notice.sh`), 1 LOW (ADR citan pruebas diferidas a A1..A3 y C1..C4: aceptado con obligación). S6-D85 aplicada: `test_licenses.sh` sin red (`check-licenses-api.sh --from-list`).
- Sello: `bash scripts/workflow/slice-gate.sh architecture tests/architecture/test_adr_docs.py`.


## W0-5 · Rojo

- Línea base: ruff, format y mypy en verde; `pytest --co` 8175 recogidas. Marca `# Rojo S6-W0-5`. Sin tocar `src/`.
- Rojas por archivo: `tests/core/test_config.py` 47 (campos `STORAGE_PROVIDER`, `S3_*`, `APEX_DOMAIN`, `ALLOW_DOMAIN_PORT`, siete `USER_*` y `NON_API_ENV_VARS` aún inexistentes; 166 verdes, 2 de ellas controles nuevos: `ENV` solo dev|production y `missing_secrets` local); `test_env_example.py` 10 (comentario 23/22, 23 cubetas, `CLAVES_SIN_RUTA` de 7, `ci.yml` 22, reparto S6 en los dos ejemplos); `test_logging_redact.py` 1; `architecture/test_no_sensitive_in_logs.py` 1, `test_settings_no_secrets.py` 1, `test_user_limits_catalog.py` 2 (una es la existente `toda_clave_del_catalogo_tiene_ruta`, roja por `CLAVES_SIN_RUTA_TODAVIA` ya con 7 claves ausentes de `USER_LIMITS`). `tests/core/test_single_process.py` nuevo, 5 verdes (guardia: hoy ya se cumple).
- Reparadas (números obsoletos, no debilitadas): en `test_env_example.py` 16/15 -> 23/22, `len(USER_LIMITS)` 16 -> 23, `CLAVES_SIN_RUTA == frozenset()` -> las 7, `ci.yml` 15 -> 22.
- Bash (solo `bash -n` en verde; Docker no se ejecutó): `test_api_image.sh` (CMD sin `--workers`), `test_compose_config.sh` (sin `--workers`/`UVICORN_WORKERS`/`WEB_CONCURRENCY` en ningún servicio; el `api` recibe `STORAGE_PROVIDER`, `S3_*`, `APEX_DOMAIN`; `worker` y `tools` sin `APEX_DOMAIN` ni `S3_SECRET_ACCESS_KEY`; bloque Python parsea), `test_env_isolation.sh` (`S3_SECRET_ACCESS_KEY` solo en `api`; Caddy en ningún servicio existente). Las aserciones D79 son guardias verdes por naturaleza; las rojas son las de `api` environment y `S3_SECRET_ACCESS_KEY`.
- Gate del paso 10 (Verde): `slice-gate.sh core/ratelimit tests/architecture/test_user_limits_catalog.py tests/core/test_ratelimit.py`; `slice-gate.sh core/logging tests/core/test_logging_redact.py`; `bash scripts/ci/test_env_isolation.sh && bash scripts/ci/test_compose_config.sh`; sello `slice-gate.sh core/config tests/core/test_config.py tests/core/test_env_example.py tests/core/test_config_secrets.py`.
- Dudas: 1) con `STORAGE_PROVIDER=local` y `S3_*` parciales no se afirma nada (propuesta: se ignoran). 2) La falta de `S3_SECRET_ACCESS_KEY` con `s3` se exige en la carga (todo o nada, literal del plan) y también en `missing_secrets`; si el Verde prefiere solo `missing_secrets`, mover el caso de `test_con_s3_las_cinco_variables_son_todo_o_nada[S3_SECRET_ACCESS_KEY]`. 3) Los errores de puerto aceptan nombrar `APEX_DOMAIN` o `ALLOW_DOMAIN_PORT`. 4) `ci.yml` solo se comprueba por conteo y nombres (≥2 apariciones), no por forma del `sed`. 5) Falta añadir `s3_secret_access_key` a `SENSITIVE_KEYS` y a `user_limits_from` (Verde).

## W0-5 · Verde

- `core/config.py`: campos `STORAGE_PROVIDER`, `S3_*`, `S3_ENABLE_PRODUCTION`, `APEX_DOMAIN`, `ALLOW_DOMAIN_PORT` y las siete `USER_*`; dos validadores de modelo que lanzan `ConfigError` con nombres; `NON_API_ENV_VARS` suma las seis de Caddy; `missing_secrets` exige `S3_SECRET_ACCESS_KEY` con `s3`. Reglas puras en `core/config_storage.py` (nuevo, para que `config.py` no pase de 800 líneas).
- `ratelimit.py` (siete cubetas, 23 en total), `logging.py` (`s3_secret_access_key`), `.env.example`, `.env.ops.example`, `compose.yml` (api con S3, dominio y `USER_*`; worker y tools con `STORAGE_PROVIDER=local`), `ci.yml`, `.env` de desarrollo, RUNBOOK §14, `adjuntos.md`, `tls.md`.
- Conteo del `sed` de `ci.yml`: 15 -> 22 (simulado sobre `.env.example`: `grep -cE` da 22).
- Desviaciones: `tests/core/test_ratelimit.py` (3 pruebas con 16 cubetas obsoletas, 16 -> 23) y `test_compose_config.sh` (la aserción de `APEX_DOMAIN` en worker/tools se hace sobre el render sin resolver env_file).
- Pendiente para tools/attachments-check con S3: recibirá el secreto cuando exista ese comando (C-slice).

## W0-5 · Revisiones y sello

- Gate 10.1 `slice-gate.sh core/ratelimit` 731 verdes; 10.2 `core/logging` 730 verdes; 10.3 `test_compose_config.sh` 0 fallas (`test_env_isolation.sh` solo contra ensayo/smoke: queda para W0-2.7).
- Seguridad 0 CRITICAL, 0 HIGH, 1 MEDIUM, 3 LOW, todo corregido por el orquestador (S6-D86, D87 y bloque de revisiones en DECISIONES): endpoint S3 sin credenciales/consulta/fragmento (+4 casos en `test_config.py`), aserción de `APEX_DOMAIN` renombrada, advertencia en `adjuntos.md`, comentario S5-D107 reubicado.
- Sello: `slice-gate.sh core/config tests/core/test_config.py tests/core/test_env_example.py tests/core/test_config_secrets.py`.

## W0-5 · Docker y evidencia

- `apex-api:local` reconstruida con buildx (`src/` va dentro de la imagen); `$DC up -d --no-build --force-recreate api worker` con el `.env` ampliado (`extra="forbid"` satisfecho) y `restart web`: 6/6 `healthy`.
- `GET /api/v1/health` 200: `{"status":"ok","db":"ok","version":"dev","backup":"attention","migrations":"ok","crypto":"ok"}` (`backup: attention` es el estado conocido del stack de desarrollo sin respaldo reciente).
- Checkpoint `114232b` (24 archivos, +946/-24).


## W0-2 · Rojo

- Línea base: ruff, format y mypy `src` en verde; 287 verdes / 2 saltadas en los archivos de llaves y config tocados; `test_deploy_script.sh` 282 ok / 0 fallas antes de editar. Marca `# Rojo S6-W0-2`. `pytest --co` recoge todo.
- Stubs: `cli_ops/keys_layout.py` (`LayoutReport`, `migrate_layout(directory: Path)` con `NotImplementedError`); `cli.py` registra `init-keys --migrate-layout` y despacha al stub (raíz por omisión `/run/apex/keys`); `scripts/ci/fixtures/attachments/make_attachments.py` (stub). Rutas de `Settings`, `key_paths_in`, `local_provider` y compose NO se tocaron (E3: el Verde para api y worker antes).
- Python rojas: `tests/cli/test_init_keys_layout.py` 13 rojas / 2 saltadas POSIX (layout `custody/` y `jwt/`, `migrate_layout` función y CLI, conflicto exit 2 todo o nada, idempotencia, raíz derivada de `JWT_PRIVATE_KEY_PATH` con OpenBao); `tests/crypto/test_init_keys.py` 1 (`test_crea_los_cuatro_archivos`, ya con `custody/` y `jwt/`); `tests/core/test_config.py` 2 (`.env.example` con las cuatro rutas nuevas y default de `CRYPTO_LOCAL_SIGNING_KEY_PATH`).
- Adaptadas para seguir verdes con el layout nuevo: `test_init_keys_cli.py` y `test_init_keys.py` (`rglob`, subcarpetas 700, archivos 600), `tests/cli/conftest.py` (`parents=True`), `test_local_provider.py` y `test_provider_startup.py` (la ruta de la KEK sale de `key_paths_in`, no de `keys/kek.bin`).
- Bash rojas (Nginx real corrió; el resto es fake): `test_nginx_conf.sh` 25 fallas; `test_compose_config.sh` 5; `test_check_key_files.sh` 14 (modo nuevo `--layout <dir> [--provider] [--only custody|all]`); `test_deploy_script.sh` 70 fallas / 291 ok (los 282 previos intactos; rojas: versiones D78, `--migrate-layout` antes de `up -d` y estático de `deploy.sh`/`prod-smoke.sh`); `test_env_isolation.sh` (bloque vivo worker sin jwt/, api con layout nuevo; `bash -n` solo); `fakes/docker` gana `FAKE_DOCKER_API_VERSION`, `FAKE_DOCKER_COMPOSE_VERSION`, `FAKE_DOCKER_LAYOUT` y `FAKE_DOCKER_LAYOUT_RC` (por omisión 1.45, 2.26.0 y «nada que migrar»: no cambia los 282 casos previos).
- Reemplazadas (contrato nuevo, no debilitadas): en `test_nginx_conf.sh` el `5m` del server (ahora 64k + 6m solo en la subida) y la CSP exacta del documento (ahora con `blob:`); en `test_compose_config.sh` los montajes del worker (`/run/apex/keys` -> subruta `custody`).


## W0-2 · Verde

- E3: `stop api worker` antes de tocar `config.py`; ambos `Exited` y siguen parados (el paso 17 es del orquestador).
- Python: `cli_ops/keys_layout.py` (60 líneas; `os.replace`, todo o nada, nunca sobrescribe), `cli.py` (378; `--migrate-layout`, raíz = `JWT_PRIVATE_KEY_PATH.parent.parent`, exit 2 con conflicto), `cli_ops/keys.py` (`custody/` y `jwt/`), `config.py` (default de la llave de firma en `custody/`), `.env.example` (cuatro rutas). `local_provider.py` no tenía rutas: sin cambio. 982 verdes / 3 saltadas (POSIX) en el lote del cierre; ruff, format y mypy en verde.
- Nginx: `default.conf` (64k global, location regex de la subida con 6m, `proxy_request_buffering on`, `limit_req zone=apex_upload`, `@too_large` con envelope anidado, CSP con `blob:`), `snippets/upload-zone.conf`, `make_attachments.py`. `compose.e2e.yml` solo sustituye `auth-zone.conf`: no hace falta equivalente para `apex_upload`. `test_nginx_conf.sh` 0 fallas.
- Compose: worker con `volume.subpath: custody` en `/run/apex/keys/custody`; tmpfs de web `/var/cache/nginx:size=64m`. `compose.dev.yml` no tenía binds de `keys` (volumen con nombre): sin cambio. `test_compose_config.sh` 0 fallas.
- `check-key-files.sh --layout`, `deploy.sh` (versiones D78 tras los argumentos y antes de git; `--migrate-layout` entre build y `up -d`, aborta con 2; el aviso de `kek.bin` con OpenBao mira `custody/` y la raíz), `prod-smoke.sh` (versiones, layout por stdin en api y worker, migración desde volumen plano; ejecución viva queda para W0-2.7).
- Pruebas del Rojo corregidas (objetivas): `test_nginx_conf.sh` (`UPLOAD_LOC` entre comillas: Nginx rechaza `{8}` sin comillas) y `test_deploy_script.sh` (`docker_ajeno` y las cinco aserciones «sin docker» excluyen las dos consultas de versión, que el contrato D78 hace antes que git).
- Docs: RUNBOOK §12, `actualizar.md`, `instalar-en-servidor.md`, `infra/README.md`.

## W0-2 · Revisiones y sello

- Decisiones S6-D88 y S6-D89 (cuatro archivos, raíz por el JWT, zona `apex_upload`, envelope anidado, sin cabeceras duplicadas); el orquestador quitó el `include snippets/security-headers.conf` duplicado del `location` de subida y ajustó la aserción de `test_nginx_conf.sh` (0 fallas con Nginx real).
- Gate 16.1 (`test_nginx_conf`, `test_compose_config`, `test_check_key_files`, `test_deploy_script` 361 ok, `workflow/tests` 6/6) 0 fallas; 16.2 `slice-gate.sh cli` 702 verdes; 16.3 `slice-gate.sh crypto` 702 verdes.
- Seguridad 0C/0H/2M/3L: corregidos por el orquestador `limit_conn` + `client_body_timeout` en la subida, `ensure_subdirs` en `migrate_layout`, 413 con envelope también en `/api/`, symlink = conflicto; LOW de la fixture aceptado con dueño C1. Tras las correcciones: `test_init_keys_layout.py` 14 verdes (3 saltadas POSIX/NTFS), `test_nginx_conf.sh` 0 fallas, ruff/mypy verdes, `keys_layout.py` 67 líneas.
- Primer `wave0-gate.sh W0-2` FALLÓ en `test_infra_scripts` → `test_check_release_version` («repositorio real: --check v0.1.0 sale con 0», obtenido 1): deuda del cierre del S5 (versión 0.2.0 con la prueba fija en v0.1.0). Corregido por el orquestador (S6-D90: la versión se lee de `pyproject`).
- Primer `wave0-gate.sh W0-2` en verde (infra completa + architecture 964) → paso 17.2: `--migrate-layout` dijo «nada que migrar» sobre el volumen plano porque el `.env` de desarrollo conserva la ruta plana del JWT (raíz derivada `/run/apex`): S6-D91 (raíz robusta, aviso, `deploy.sh` exige rutas nuevas, `actualizar.md` corregido); `.env` de desarrollo actualizado a las cuatro rutas nuevas; imagen del api reconstruida; sello repetido.
- Sello: `bash scripts/workflow/wave0-gate.sh W0-2 tests/cli/test_init_keys_layout.py tests/core/test_config.py tests/core/test_env_example.py`.

## W0-2 · Docker de desarrollo (paso 17)

- Segundo `wave0-gate.sh W0-2` (tras S6-D91) en verde: `test_check_release_version` 19 ok, `test_infra_scripts`, `test_openbao_infra` 101 ok, `test_api_image`, ocho `compose config --quiet`, architecture 965. Checkpoint `05ea83d` (36 archivos, +1116/-51).
- Imágenes `apex-api:local` y `apex-web:local` reconstruidas con el árbol sellado; respaldo del volumen `apex_keys` previo a la migración en `C:\Users\PC\Desktop\apex-claves\keys-dev-antes-layout.tgz` (fuera del repo: `docs/scratch` no ignora `.tgz`; se borra en V12).
- `init-keys --migrate-layout` con `tools` (api y worker parados desde el Verde, E3): primera corrida «movido kek.bin, sign-ed25519.key, jwt_ed25519.pem, jwt_ed25519.pub»; segunda «nada que migrar». Volumen: `custody/` y `jwt/` en 700, archivos en 600, dueño 10001.
- `up -d --no-build --force-recreate api worker web`: 6/6 `healthy`; `/health` `{"status":"ok","db":"ok","backup":"attention","migrations":"ok","crypto":"ok"}`. El worker monta solo `apex_keys` en `/run/apex/keys/custody` (ro) y `ls /run/apex/keys/jwt` falla; el api ve `custody/` y `jwt/`.
- Login `POST /auth/login` por Nginx (8180, con `Origin`) 200 y `GET /members/{id}` 200: JWT desde `jwt/` y KEK desde `custody/`. (Directo al 8181 sin pasar por Nginx responde 403 `forbidden`: comportamiento previo, el api exige el proxy de confianza.)
- Nginx con las fixtures de `make_attachments.py`: 102.400, 5.242.880 y 5.242.881 bytes → 404 `not_found` del api (pasaron Nginx; la ruta llega en C2); 6.300.000 → 413 `{"error":{"code":"file_too_large","message":"El archivo supera el tamaño máximo de 5 MB.","field":"file"}}`; `curl -sI /` → `img-src 'self' data: blob:`.

## W0-2 · Ensayo desde cero (paso 18, DevOps)

- Pasos 1 a 6 en verde (evidencia en `docs/scratch/ensayo/evidencia/`, ignorada): `.env`/`.env.ops`/`.env.seed` y llaves efímeras generadas sin `cambiar-esto`; `init-keys` crea `custody/` y `jwt/` (600, 10001); `migrate` 0001→0020 como `apex_owner`; `dbsetup` «20 tablas clasificadas»; 6 servicios healthy; `--first-install` por pty (5 llaves en `openbao/init.txt`, 600), desellado con 3 (`Sealed false`, 5/3), `seed`; `export-kek` y `verify-kek-backup` `total=8 failed=0`; respaldo con `compose.verify.yml` y manifiesto firmado con `openbao_snapshot.verified: true`; `migrate-provider --dry-run` 8 → `MIGRAR` `hecho=8/8` → `--verify` 0 → «nada que migrar»; `CRYPTO_PROVIDER=openbao`, `retire-local-kek` con `RETIRAR`, `custody/kek.bin` ausente en el api, el worker no monta `keys`; `crypto_keys` → `openbao|8`; `test_db_roles.sh` (nueva) 65 ok / 0 fallas; `test_env_isolation.sh` con `$DCEB` 48 ok / 0 fallas (incluido «worker no ve jwt»); `/health` 8280 `ok`, `crypto ok`, `migrations ok`, `backup attention`; `docker stats` api 99 MiB, worker 87, db 34, web 7, backup 11, openbao 26.
- Paso 7 `prod-smoke.sh --no-build --provider openbao` (auxiliar Linux): `test_db_roles`, `test_env_isolation`, `restore_e2e`, `openbao_restore_e2e` y `openbao-smoke` en verde; **2 fallas** → S6-D92 (fixture del volumen plano `root:root`; `--migrate-layout` abortaba con `Settings` roto y `deploy_e2e` «api roto» no escribía `rollback-*.txt`). Corregido; el paso 7 se repite tras reconstruir `apex-api:local`.
- Observaciones del DevOps: `exec worker ls /run/apex/keys` devuelve el directorio vacío de la imagen (rc 0): la comprobación válida es que el worker no monta el volumen `keys`; `apex-ensayo-db-1` se recreó al usar `compose.verify.yml` (hash de configuración) sin perder `pgdata`; el smoke repunta `apex-*:local` y se devolvieron las etiquetas.


## W0-3 · Rojo

- `scripts/ci/test_openbao_infra.sh`: 101 -> 157 comprobaciones; 18 en rojo (3 conjuntos exactos de política modificados: api, worker, tools; 15 nuevas). `bash -n` verde. Marca `# Rojo S6-W0-3`.
- Rojas: worker sign+verify `update`; api verify; tools sign, verify y `read` de `transit/keys/apex-sign-audit`; cabecera de `--reissue-tokens` sin mención de políticas; cuatro pasos del humo (firma con `bao write ... input=`, verificación con `signature=` y `valid`, intento de `rotate`, lectura de token del volumen con `exec -e BAO_TOKEN`, cuerpos de las cuatro funciones, marcas de Rojo); `ci.yml` sin `transit/sign/*` ni `transit/verify/*`.
- Verdes de guarda (ya cumplidos, protegen el Verde): sin subrutas ni comodines sobre `apex-sign-audit` (M-2c), api sin `transit/sign/`, `bootstrap.sh` sin `ml-dsa` y con ed25519/exportable=false, bucle de políticas con las cuatro y antes de `emitir_token`, sin sonda en bootstrap, `cap_drop: [ALL]` en los 6 servicios de `custody`.
- `openbao-smoke.sh`: funciones `firma_worker_200`, `verifica_api_valid`, `firma_api_403`, `rota_tools_403` (stubs que llaman a `falla`) y cabecera 5a-5d, entre los pasos 5 y 6. Ejecución en vivo pendiente del orquestador/Verde (sin Docker aquí).

## W0-3 · Verde

- Políticas: `apex-worker` sign+verify, `apex-api` solo verify, `apex-tools` sign, verify y `read` de la llave de firma, todo `update` salvo el `read`; sin rotate/config/delete/trim/export ni comodines.
- `bootstrap.sh`: cabecera de `--reissue-tokens` dice que reaplica las cuatro políticas; `--help` pasa a `sed -n '2,27p'`. Sin sonda `ml-dsa` (ya).
- `openbao-smoke.sh`: cuatro funciones implementadas (token leído del volumen con `run --rm -T --no-deps --entrypoint cat`, pasado por `exec -T -e BAO_TOKEN openbao bao write ...`, sin imprimirlo); `--help` a `2,37p`. Ejecución en vivo pendiente (orquestador, paso 24.3).
- `ci.yml`: política real `apex-ci` (kek encrypt/decrypt/rewrap/read, `apex-sign-audit` read+create+update, `transit/sign/*`, `transit/verify/*`) y token de prueba con `no_default_policy`.
- Docs: `docs/operacion/openbao.md` (reaplicar políticas en la sección 6, matriz de tokens antes de la 10) y RUNBOOK §13.
- Desviación: `cuerpo_de` del test usaba `"\(\)"` en regex dinámica (gawk 5 lo trata como grupo vacío y nunca encontraba el cuerpo); cambiado a `index($0, n "() {") == 1`. El test de la cabecera de `--reissue-tokens` usa `pol[ií]ticas`: pasa solo en locale UTF-8 (`LC_ALL=C.UTF-8`; la CI de ubuntu lo es).

## W0-3 · Revisiones y sello

- Seguridad 0C/0H/1M/2L, todo corregido por el orquestador (S6-D93, D94 y bloque de revisiones en DECISIONES): `token_de` en el smoke, 403 con `permission denied`, prueba positiva del token de tools, `apex-ci` sin `create/update` sobre la llave de firma, nota de la raíz dev en `ci.yml`.
- Gate 23.1: `test_openbao_infra.sh` 157 ok (con `LC_ALL=C.UTF-8` exportado por el propio test), `test_infra_scripts.sh` y `test_compose_config.sh` 0 fallas.
- Sello: `bash scripts/workflow/wave0-gate.sh W0-3`.

