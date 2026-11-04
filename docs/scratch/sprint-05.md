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
