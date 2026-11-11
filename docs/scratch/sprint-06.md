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

