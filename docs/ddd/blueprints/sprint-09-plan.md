# Plan de implementación · Sprint 9 · v0.6: perfil del atleta (EP-24)

Estado: aprobado para ejecución (críticas 1 y 2 incorporadas; enmiendas finales en la sección 10)

> Fase 2 de `/flow-update`, enmendado tras `sprint-09-critica-1.md` (RECHAZADO; diez hallazgos aplicados en sitio y tres puntos verificados en el código de `cd0cc0b`; mapa en la sección 9). Solo plano: no cambia código. Imita `sprint-08-plan.md` (alias, P-MIG, P-ROL, P-API, P-REBUILD, P-GATES, P-CAT, P-E2E, ciclo de slice, waves, V1 a V9) y suma las lecciones de S8-D43 a S8-D51.

Veredicto de impacto: AMARILLO (condiciones C1 a C7 incorporadas; mapa en la sección 8).

- Rama `feat/sprint-09-perfil-atleta`, HEAD de partida `cd0cc0b` (= `main`, v0.5.0). Cabeza de Alembic: `0041_results_session_index`. Este sprint añade `0042_athletes_body_metrics` y `0043_athletes_personal_records` (ids de 26 y 30 caracteres).
- Entradas, en el orden en que mandan: `sprint-09-critica-1.md`, `sprint-09-seguridad-diseno.md` (H-1, H-2, M-1 a M-6, L-1 a L-8, S9-D29 a D35, P9 a P11), `sprint-09-blueprint.md` (S9-D1 a D28, P1 a P8, E1 a E8), `sprint-09-impacto.md` (C1 a C7), `sprint-09-exploracion.md`, `SPRINT-09.md`, US-178 a US-184, `CLAUDE.md`, S8-D43 a S8-D51 y, como plantilla, `sprint-08-plan.md`. Donde el blueprint y la revisión de seguridad chocan, manda la revisión; donde cualquiera choca con la crítica o con una precisión de este plan (sección 1), manda este plan.
- Doctrina: TDD por slice con rojo medido antes del verde (sin excepciones por encargo, S8-D51), deuda cero (todo HIGH y MEDIUM es un paso; todo LOW se corrige o se acepta con motivo), ejecución al 100 % sin pausas.
- Modelos: Fable diseña y revisa (`plan-critic`, `security-reviewer`, `database-reviewer`, Fase 4; Opus si su cupo se agota, como en S8-D43). Sonnet ejecuta Rojo, Verde, front, DevOps y QA. Haiku hace lo mecánico (T-DOC, conteos de catálogo, P-API, versión, limpieza).
- Paradas (además de las de la doctrina):
  1. Cualquier escritura en `apex-db-1` fuera de: P-MIG; el `dbsetup` único de V2; `derive-records` (B6, V2 y P-E2E); la evidencia por curl de A1, A2, B3 y B5 (socios, WODs y resultados ficticios creados por el propio slice, con su id al cuaderno); los smokes de cierre de wave; los E2E de los slices F, de X2 y de V5; las demos de V4 y la clase de V8.
  2. `down -v`, `docker volume rm` o `wsl --shutdown` en cualquier proyecto (única excepción: el proyecto `apex-smoke`, que baja `SMOKE_DOWN=1` o el paso de rollback de V3); arrancar o tocar contenedores `dian-*` o `apex-ensayo` (siguen parados).
  3. Cambiar el formato del blob `apx1`, el serializador de auditoría (ADR-004) o cualquier ADR. P11 (una DEK por socio) cambiaría ADR-002: no se hace.
  4. Editar una migración ya aplicada en `apex-db-1` (se crea otra, S8-D49).
  5. El tope de consumo del 80 %: se cierra el slice en curso y se reporta.
  6. Un `git push` rechazado por el sistema de permisos o por la protección de `main`, o sin la autorización de S9-D41: se entregan los comandos exactos, no se busca otra vía.

## 0. Convenciones comunes

### Alias y entorno (todo desde Bash, en el árbol principal)

1. `DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"`: desarrollo, proyecto `apex`. Puertos: web 8180, api 8181, db 5442, db_test 5443. **Compose se invoca SIEMPRE desde el árbol principal, nunca desde un worktree** (cambiaría el proyecto y los montajes).
2. `DCE2E="$DC -f infra/compose.e2e.yml"`: solo mientras corre un E2E del proyecto `stack` (P-E2E).
3. `PSQL="$DC exec -T db psql -U apex -d apex -v ON_ERROR_STOP=1"`: solo `SELECT`, `\d`, `\df+` y sentencias que deben fallar dentro de `BEGIN; ... ROLLBACK;`.
4. Pruebas del api: `export TEST_DATABASE_URL=postgresql+asyncpg://apex:apex-test@127.0.0.1:5443/apex_test` en cada comando, `uv` en `~/.local/bin`, `-p no:cacheprovider`, `PYTEST_ADDOPTS="-m 'not perf'"`. **Un solo `pytest` a la vez en todo el equipo**, también con el front en su worktree.
5. Vitest siempre con `--maxWorkers=2`.
6. `apex-smoke` (S8-D51): `scripts/ci/prod-smoke.sh` (puerto 8380) en el contenedor auxiliar `docker:cli` con el socket y `--network host`. El árbol llega por `git clone` del repositorio montado en solo lectura (`git -c core.autocrlf=false clone /src /work/apex && git -C /work/apex checkout <sha>`); nunca `rsync` ni copia desde NTFS (trae CRLF). Se lanza con `docker run -d`, se vigila con Monitor, con `SMOKE_DOWN=1`. **Tras cada corrida se reconstruyen `apex-api:local` y `apex-web:local`** (P-REBUILD 4 y 3): el smoke pisa esas etiquetas.
7. Bajo MSYS, `MSYS_NO_PATHCONV=1` delante de todo `docker run` o `exec` con rutas POSIX.
8. Secretos: nunca se imprimen contraseñas, tokens ni llaves. El access del admin va a `$TMPDIR/apex-token` con `umask 077`. El token de GitHub va a `$TMPDIR/apex-gh.curlrc` (S9-D38). **El valor revelado de una medida de prueba tampoco va al cuaderno ni a la salida: solo «coincide».** Nunca `set -x` en un guion que toque esos archivos. Todo se borra al cerrar el slice o en V9.
9. Memoria: tras cada wave, `wsl -d docker-desktop -- sh -c "echo 3 > /proc/sys/vm/drop_caches"`; solo `apex` e infraestructura corriendo, sin procesos de fondo.
10. Worktrees: front en `.claude/worktrees/sprint-09-front` (rama `sprint-09-front`); gates de cierre en `.claude/worktrees/gates` (desechable).
11. Banderas de exclusión (S8-D42) en `LOCKS=C:/Users/PC/Proyectos/Apex/.git/apex-locks/`: `apex-migracion.flag` y `apex-e2e.flag`, cada una con `<slice> <id del agente> <fecha ISO>`.
    - Toma `apex-migracion.flag`: el paso 0 de A1 y de B1 (hasta su checkpoint) y todo `up`, `start` o `restart` del api o de `web` fuera de un slice F.
    - Toma `apex-e2e.flag`: P-E2E y la P-REBUILD 3 de un slice F o de X2.
    - Antes de crear una se espera con Monitor a que la otra no exista. Una huérfana (más de 90 minutos y su dueño muerto) se anota y se borra.
12. **Una carpeta, un agente que confirma (S8-D51).** `checkpoint-commit.sh` hace `git add -A`: solo lo usa el único agente que escribe en esa carpeta. Los slices de backend y de deuda van en serie en el árbol principal; el front, en su worktree. Si dos agentes deben escribir a la vez en la misma carpeta, ninguno usa el guion: cada uno hace `git add <rutas explícitas>` y `git commit`.
13. `/health` con el SHA: `export GIT_SHA=$(git rev-parse --short HEAD)` antes de cada buildx y de cada `$DC up` de cierre; el smoke comprueba que `version` lo refleja.
14. Gates largos (S8-D51): `run-gates.sh` se lanza en segundo plano con la salida a un archivo del scratchpad y se vigila con Monitor. Si el harness lo mata por memoria, se corre en dos mitades sobre el MISMO SHA (api: ruff, mypy, pytest; web: lint, `tsc`, vitest con 2 hilos, build) y se anota; vale solo con las dos en verde.
15. **Cómo se usa `slice-gate.sh` (verificado en el guion).**
    - `slice-gate.sh <modulo> [archivos...]`. Módulos del api: `core/<x>` (un nivel), `crypto` (`core/crypto`, pruebas en `tests/crypto`), `main`, `worker`, `cli` (`cli.py`, `cli_base.py`, `cli_ops/`, `seed/`, `imports/`), `architecture` y `<modulo>` de `modules/`. Del front: `web/<feature>`, `web/shared`, `web/core`, `web/layouts`, `web/app`.
    - Con lista, cada argumento debe ser un ARCHIVO que exista bajo `api/tests/` (o bajo `web/`): una carpeta se rechaza. `tests/architecture` se agrega solo; no se pasa.
    - Ruff y mypy corren SOLO sobre el código del módulo nombrado. Por cada otro módulo que el slice toque se corre antes un gate no sellante de ese módulo. El último gate que corre es el que sella, y cualquier cambio posterior (también de documentos) invalida la huella: la documentación del slice va antes del sello.
    - Las specs de Playwright no se pasan al gate (vitest las tomaría como pruebas): van por P-E2E.
    - El sello vive en el `.git` de cada worktree: el del front no pisa el del árbol principal.

### Ciclo estándar de un slice

0. **Si el slice tiene migración (A1, B1): esperar a que no exista `apex-e2e.flag`, crear `apex-migracion.flag` y `$DC stop api worker` ANTES de escribir cualquier archivo**, stubs incluidos. El api de desarrollo corre con `--reload` y `MIGRATE_ON_STARTUP=true`: aplicaría a `apex-db-1` una migración a medio escribir.
1. Stubs con `NotImplementedError` y Rojo (`backend-qa-executor` o `frontend-qa-automation`, Sonnet). El rojo se confirma con conteo y motivo de cada fallo, al cuaderno.
2. Verde (`backend-implementor` o `frontend-ux-engineer`, Sonnet) con gates no sellantes de los módulos tocados (alias 15).
3. `security-reviewer` (todos) y `database-reviewer` (A1, A3, B1, B3, B5, B6, C1), Fable, en paralelo y en solo lectura. El Verde corrige todo CRITICAL, HIGH y MEDIUM; los LOW se corrigen o se aceptan con decisión numerada.
4. **Antes del gate:** P-API si cambió el contrato; **P-MIG 1 a 4** (volcado, api parado, archivos, ciclo contra `db_test`) y P-ROL si hay migración o grants; P-CAT si hay ruta, módulo, tabla o esquema nuevos.
5. Documentación del slice y bloque del cuaderno `docs/scratch/sprint-09.md` (Rojo, Verde, Revisiones; el front en `docs/scratch/sprint-09-front.md`).
6. Gate sellante: `bash scripts/workflow/slice-gate.sh <modulo> <archivos de prueba...>` (antes, `ls` de cada archivo).
7. **Después del gate, sin tocar el árbol versionado:** **P-MIG 5 a 7** (arrancar el api, que migra `apex-db-1`; ciclo `downgrade`/`upgrade`; esquema al cuaderno), Docker y evidencia por curl. El cuaderno de evidencia se confirma en el segundo commit del paso 9. Si algo obliga a cambiar código, se vuelve a 2 y se resella.
8. Slices F: E2E de stack mínimo de cada ruta nueva en el mismo slice, con P-E2E contra la imagen web construida desde el worktree.
9. Checkpoint: `CHECKPOINT_TRAILER='<línea Co-Authored-By de la sesión>' bash scripts/workflow/checkpoint-commit.sh "S9-<slice> <resumen>"` (un solo argumento) y `git commit -m "docs(sprint-09): evidencia de S9-<slice>"`; se verifica con `git log -1 --format=%B`. Se borra la bandera.
10. Cierre de wave: P-GATES, P-REBUILD, smoke por curl a 8181, `drop_caches`.

### P-MIG · Migración nueva (`0042`, `0043`)

Los puntos 1 a 4 van en el paso 4 del ciclo (antes del gate); los puntos 5 a 7, en el paso 7 (después del gate).

1. Volcado: `$DC exec -T db pg_dump -U apex -Fc apex > docs/scratch/sprint-09-antes-0042.dump` (y `-0043.dump` antes de B1). Ignorados por git; se borran en V9.
2. `$DC stop api worker` (ya hecho en el paso 0) hasta el punto 5.
3. Escribir `api/migrations/versions/00NN_<tema>.py` y `api/tests/migrations/test_00NN_<tema>.py`. `migrations/env.py` importa `modules/athletes/models.py` desde A1.
4. Contra `db_test`: `cd api && uv run pytest tests/core/test_migrations.py tests/migrations -q` (ciclo `head → base → head`, ids de 32 o menos) y `uv run alembic heads` con una sola cabeza.
5. Solo con el gate del slice en verde: `$DC start api` (migra al arrancar), esperar `healthy`, `$DC exec api alembic current` = `00NN (head)`; luego `$DC start worker`.
6. Ciclo en la base real de desarrollo: `$DC exec api alembic downgrade -1 && $DC exec api alembic upgrade head && $DC exec api alembic current`. Con filas reales en la tabla se omite el `downgrade` y se anota (pierde datos).
7. Al cuaderno: `$PSQL -c '\d athletes.<tabla>'`, `\df+` de cada guarda y `tgenabled` de todo trigger (debe ser `A`).
8. Las pruebas de migración usan «está en la cadena de head», nunca «es head». El Rojo de A1 corre `tests/migrations` con `0042` como stub vacío y corrige cualquier prueba que fije `0041` como cabeza (E1).

### P-ROL · Grants y smoke con rol real

En el mismo slice que la tabla (C5):
1. Las tres listas de `infra/db/grants.sql` (matriz de cabecera, `-- clasificada:` y `ARRAY clasificadas`).
2. `GRANT USAGE ON SCHEMA athletes` a `apex_api` y `apex_backup` (el worker no ve el esquema) y `athletes` en los `REVOKE ... IN SCHEMA`.
3. `tests/migrations/test_db_grants.py` (`ESQUEMAS`, `PRIVILEGIOS`); `core/db.APP_SCHEMAS` y `tests/core/test_db.py`.
4. **Smoke con rol real:** `tests/migrations/test_api_role_paths.py` y `test_worker_role_paths.py` (ciclo `apply → revoke → apply` sobre `db_test`): `apex_api` inserta y solo actualiza las columnas permitidas; `apex_worker` no tiene acceso; nadie borra.
5. Tablas clasificadas: 30 hoy, 31 tras `0042`, 32 tras `0043`.
6. En desarrollo el api corre como propietario: el grant solo se demuestra en estas pruebas, en el `dbsetup` de V2 y en `prod-smoke` (V3).

### P-API · Contrato (A1, A2, A3, B1, B2, B5, C1, C2, X1)

`cd api && uv run python -m app.cli export-openapi ../docs/openapi.json` (dos veces, idéntico), después `cd web && npm run gen:api && npx vitest run --maxWorkers=2 src/core/api/types.contract.test.ts`. `docs/openapi.json` y `web/src/core/api/types.ts` entran en el checkpoint del mismo slice. Solo el backend toca esos dos archivos.

### P-REBUILD · Qué se reinicia y cuándo

1. api de desarrollo: `--reload`. Con migración en curso está parado y se arranca con `$DC start api`. `$DC restart api` cuando cambian variables (W0-2).
2. worker: sin reload. `$DC restart worker` tras W0-3 (`core/alerts.py`), B3 y B5 (carga `load_module_services`, que importa `athletes`) y X1 (`members` y `notifications` los usa `notify`).
3. web: `$DC up -d --build web` desde el árbol principal. En los slices F, con `apex-e2e.flag`, la imagen se construye desde el worktree y el stack se recrea desde el árbol principal: `docker buildx build --load --network host --allow network.host -t apex-web:local -f .claude/worktrees/sprint-09-front/web/Dockerfile .claude/worktrees/sprint-09-front` y `$DC up -d --no-build --force-recreate web`.
4. Imagen del api (`api`, `worker`, `tools`, `migrate`), al cierre de cada wave con migraciones o contrato y tras cada `prod-smoke`: `docker buildx build --load --network host --allow network.host --build-arg GIT_SHA=$GIT_SHA -t apex-api:local -f api/Dockerfile api` y `$DC up -d --no-build --force-recreate api worker`.
5. Smoke: `curl -s http://127.0.0.1:8181/api/v1/health` (`status`, `db`, `migrations: ok`, `crypto: ok`, `version` con el SHA) y un GET con rol de cada ruta nueva de la wave (solo el código HTTP al cuaderno).

### P-GATES · Cierre de wave en worktree limpio (S8-D51)

1. `SHA=$(git rev-parse HEAD) && git worktree add --detach .claude/worktrees/gates "$SHA"`.
2. `cd .claude/worktrees/gates/api && uv sync --extra s3` y `cd ../web && npm ci`.
3. `cd .. && TEST_DATABASE_URL=... bash scripts/workflow/run-gates.sh` (alias 14; ningún otro `pytest` mientras tanto).
4. Si falla: el arreglo va en el árbol principal como slice de vuelta a gate; se repite desde 1 con el SHA nuevo.
5. `git worktree remove --force .claude/worktrees/gates`.

### P-CAT · Catálogos fijos (en el Rojo del mismo slice, no al cierre)

1. Ruta nueva con 429: `CON_LIMITE` de `tests/architecture/test_error_codes_per_route.py` y `test_writes_have_user_limit.py`.
2. Cubeta con su primera ruta: `athletes-write` entra en `CLAVES_SIN_RUTA_TODAVIA` en W0-2 y sale en A1; las afirmaciones `== frozenset(...)` de `test_user_limits_catalog.py` y `test_env_example.py` se reescriben en el mismo paso.
3. Módulo nuevo: la tupla de `tests/architecture/test_audit_module.py` (A1).
4. Tabla nueva: `tests/conftest.py` (`LIMPIAR_ATHLETES` en `LIMPIEZA_DE_SESION` y en `limpiar_tras_dos_sesiones`, ANTES de `LIMPIAR_WOD_RESULTS` y de la limpieza de llaves, con los triggers apagados y rearmados por nombre). Además `grep -ln "LIMPIAR_MEMBERS\|DELETE FROM members\|TRUNCATE" api/tests/*/conftest.py`: cada conftest propio que borre socios suma las tablas nuevas; el resultado del grep va al cuaderno.
5. Esquema nuevo: `core/db.APP_SCHEMAS` y `tests/core/test_db.py`.
6. Conteos por la clase de dato nueva (A1): `grep -rn "encrypting_specs\|REGISTRY\|LIMPIAR_LLAVES" api/tests` antes de tocar; se migra todo lo que cuente clases cifradas (inventario, CBOM, `crypto_keys`).
7. Clave de alerta nueva (W0-3): el conjunto que fija `tests/core/test_alerts.py:78`.

### P-E2E · Corrida contra el stack

1. Esperar a que no exista `apex-migracion.flag` y crear `apex-e2e.flag`.
2. `umask 077; cp .env <scratchpad>/env.antes-e2e` (nunca se imprime).
3. `$DC --profile tools run --rm tools seed-benchmarks` y, desde B6, `$DC --profile tools run --rm tools derive-records` (los dos idempotentes).
4. En `.env`, el mismo `sed` del job E2E de `ci.yml` (desde W0-2 sube también `USER_ATHLETES_WRITE_LIMIT_PER_MIN`).
5. `$DCE2E up -d --no-build --force-recreate api web`.
6. `E2E_BASE_URL=http://127.0.0.1:8180 npx playwright test --project=stack <specs>` (desde `web/` del árbol o del worktree; Playwright no es compose).
7. En un `trap`: restaurar `.env`, borrar la copia, `$DC up -d --no-build --force-recreate api web` sin el overlay, `grep` de una variable `USER_*` con su valor de desarrollo y borrar `apex-e2e.flag`.

## 1. Decisiones (bloque «## Sprint 9» de `docs/ddd/DECISIONES.md`, se copia en W0-1)

1. **S9-D1 a S9-D28:** se adoptan como están en `sprint-09-blueprint.md` §1, con estas correcciones, que mandan sobre el blueprint:
   - (a) S9-D3 y S9-D4: el claro lleva marca de campo (S9-D32) y `notes` va rellenado (S9-D36, L-1).
   - (b) S9-D7 (4): ya no «todo fallo revierte»; rigen S9-D30 y S9-D42.
   - (c) S9-D10: `_invalidate` escribe por ORM, no con un `UPDATE` de Core (S9-D42).
   - (d) S9-D11: tope 200 y filtro en SQL; solo repone si se invalidó algo (S9-D30).
   - (e) S9-D13: el coach solo anula o invalida lo suyo y dentro de 24 h (S9-D33).
   - (f) S9-D14: `reveal` de un socio dado de baja solo para admin (S9-D34).
   - (g) S9-D15: el aviso de volumen además alerta (S9-D35).
   - (h) S9-D18: guardas y grants endurecidos (S9-D31).
   - (i) S9-D22: `can_whatsapp` usa las cinco condiciones reales de `wa_link` (S9-D36, L-5).
   - (j) S9-D24: sin `gh`; se dispara por la API REST (S9-D38).
   - (k) S9-D3: el alta exige autorización vigente (S9-D29).
   - (l) S9-D6, nombres verificados en el código:
     - En `wods/catalog.py` existen `movements_by_id` (lee con `FOR SHARE`, S8-D45), `benchmark_for_share`, `ensure_wod`, `day_wod_ids`, `wod_date`, `scoring_for`, `today_title` y `titles_for`. `movement_for_record` y `benchmark_for_record` NO son consultas nuevas: son envolturas públicas en `wods/service.py` sobre `movements_by_id` y `benchmark_for_share` que devuelven una dataclass plana (un service no entrega modelos ORM a otro módulo). `record_meta_for`, `wod_ids_with_primary`, `movement_refs` y `benchmark_refs` son funciones NUEVAS.
     - En `results/reads.py` existen `leaderboard`, `public_leaderboard`, `wod_results` y `member_results` (que `results/service.py` exporta como `list_member_results`); no cambian. `get_mark` y `member_marks` son NUEVAS.
     - En `results/leaderboard.py` existen `_tie_key_of`, `leaderboard_order` y `rank_rows`. `score_key` es una función pública NUEVA que envuelve a `_tie_key_of`. `validate_score` no está hoy en el `__all__` de `results/service.py`: B1 la suma junto con `score_key`.
2. **S9-D29 (H-1) · Sin autorización de datos no se guardan medidas.** `members.service.consent_missing_for(session, ids) -> set[UUID]` (la misma `CONSENT_MISSING_CONDITION` de `members/rules.py`; no descifra). `add_metric` responde 409 `consent_required` ANTES de codificar y cifrar: cero filas `encrypt`. La lista, el `reveal` de lo ya guardado y los récords (no son dato de salud) no cambian. El front deshabilita «Registrar medidas» con enlace a la ficha.
3. **S9-D30 (H-2) · El handler no puede tumbar la tablet.**
   - Dos políticas. **Invalidar falla cerrado:** si `_invalidate` falla, se revierte la corrección o la anulación, porque un RM falso vigente no lo repara ningún comando. **Derivar y reponer fallan en blando:** van dentro de un savepoint; ante un fallo que no sea «base ocupada» (S9-D42) se revierte el savepoint, se registra `athletes: derivación omitida` (los ids solo en el log), se alerta sin ids y el resultado se confirma. `derive-records` lo repara. Corrige US-181 CA8.
   - `_restore_best` solo corre si `_invalidate` tocó al menos una fila viva, y solo para el `kind` y el objetivo de esa fila. En `on_wod_result_validated` con `supersedes_id`, eso se sabe leyendo las filas del socio con `invalidated_by_result_id = <resultado nuevo>`.
   - Las marcas se filtran en SQL: benchmark por `benchmark_id`; RM por `wods.service.wod_ids_with_primary(session, movement_id)` y `results.service.member_marks(..., wod_ids=...)`. Tope `RESTORE_MAX_MARKS = 200`. Si se alcanza: alerta con el conteo y no repone (en el comando, además código de salida 1; S9-D36, M-6).
   - Presupuesto de sentencias por `PUT /results`, que fija el Rojo de B3 y B5: sin récord posible, 2 de más; con derivación, 6; con corrección y reposición, 12. Si el Verde necesita más, lo justifica en el cuaderno y lo aprueba `database-reviewer`.
4. **S9-D31 (M-1) · La base protege las medidas también de `apex_api`.** En `0042`, la rama de recifrado del `BEFORE UPDATE` exige:
   - que el id de llave del blob nuevo sea la llave `encrypt` `active` de `athlete.metric` en `crypto.crypto_keys` y sea DISTINTA de la del blob viejo (fuera de una rotación no hay `UPDATE` de blob posible);
   - la forma completa del blob por expresión regular, no `LIKE 'apx1.%'`;
   - en las tres columnas de ancho fijo, `length(NEW) = length(OLD)`;
   - que el mismo `UPDATE` no toque `voided_*` (recifrar y anular son ramas excluyentes);
   - una fila anulada SÍ se recifra (si no, `retire-key` quedaría bloqueado).
   `BEFORE INSERT`: `voided_*` nulos y cada blob con la forma y una llave de la clase. En `personal_records`, `invalidated_*` nulos al nacer. Grants de `INSERT` por columna, sin `voided_*` ni `invalidated_*` (patrón de `payments.payments`).
   - **Precisión de este plan:** en el INSERT la llave puede ser `active` o `decrypt_only` de la clase. Una rotación que empieza entre el cifrado en memoria y el `INSERT` daría un 500 con «solo activa». El recifrado sí exige la activa y distinta.
   - `apex_api` ya tiene `SELECT` sobre `crypto.crypto_keys` (`grants.sql:181`, verificado por la crítica). Los nombres reales de sus columnas y el formato del id en el blob se confirman en el Rojo de A1. `database-reviewer` confirma que el `pg_restore` completo de `restore.sh` carga los datos antes de crear los triggers (las guardas de INSERT no disparan al restaurar).
5. **S9-D32 (M-2) · Marca de campo dentro del claro.** `encode_metric` antepone `w`, `h`, `f` o `n` (`w062500`, `h165`, `f07`, `n…`). `decode_metric` exige marca, largo exacto y solo dígitos, y falla con error opaco. Un blob copiado a otra columna de la misma fila no revela nada. Es formato de dato: se decide antes de la primera fila real.
6. **S9-D33 (M-3) · Quién anula e invalida.** El coach solo anula una medición o invalida un récord manual que registró él (`recorded_by` o `created_by` = quien llama) y dentro de `SELF_UNDO_WINDOW_H = 24` horas; lo demás, 403 `forbidden`. El admin, todo. Sin texto libre.
7. **S9-D34 (M-4) · Socio dado de baja.** `reveal` de una medición suya: solo admin (coach 403 `forbidden`, sin fila `decrypt`). La lista con `has_*` sigue para los dos. `docs/operacion/atleta.md` dice qué se conserva y por qué.
8. **S9-D35 (M-5) · Alerta por volumen de `reveal`.** Cupo compartido con la ficha. `core/ratelimit.py::warn_reveal_volume` conserva su `logger.warning` (ahí va el usuario) y además llama `alert("reveal_volume", revelados=<conteo>)` una vez por usuario y hora. **La alerta lleva solo el conteo, sin id de usuario** (regla de `core/alerts.py:7`: nunca datos de personas); corrige el «usuario y conteo» de la revisión. La guía enseña a filtrar `GET /audit?action=reveal&table=athletes.body_metrics`.
9. **S9-D36 · MEDIUM y LOW restantes, con destino.**
   - M-6 (B5 y B6): tope de S9-D30; `derive-records` documenta que puede crear históricos que la vía en vivo no creó; la prueba afirma el invariante que importa (tras cualquier corrida, el vigente de cada objetivo es el máximo real de las marcas vigentes y validadas); `--dry-run` y la fila resumen sin ids de socio.
   - L-1 (A1, se corrige): `notes` se rellena antes de cifrar. Claro = `n` + 4 dígitos con los bytes UTF-8 del texto + texto + espacios hasta un múltiplo de 128 bytes.
   - L-2 (A1 y A2, se corrige): la puerta acepta un solo campo de la tupla de cuatro y `purpose: Literal["reveal"]`, y rechaza la fila anulada dentro de la puerta; un blob que no decodifica da 500 `internal_error` sin el texto; `test_no_sensitive_in_logs` prohíbe `value` en los `extra` de `app.athletes`.
   - L-3 (A3 y B5, se corrige): `FOR UPDATE` de la fila (tras `lock_member` en récords) y 409 en la segunda petición; el `reveal` vuelve a mirar `voided_at` en su transacción.
   - L-4 (B3 y F2, se corrige): `ResultMark.source` y `RecordOut.result_source`; el front escribe «Automático (tablet)».
   - L-5 (X1, se corrige; hallazgo 5 de la crítica): `can_whatsapp` es verdadero solo si se cumplen las cinco condiciones REALES de `wa_link` (`notifications/service.py:184-196` y `members/contact.py:107-110`): el aviso no está `skipped`; su canal es `whatsapp_link`; `channels.whatsapp.enabled`; el socio existe, no está dado de baja y tiene autorización de datos; y tiene teléfono. No existe ninguna condición de «opt-in» en `wa_link` (la revisión lo suponía). El 422 `invalid_phone` exige descifrar: queda como defensa, igual que `member_without_phone` ante una carrera.
   - L-6 (X3, se corrige): `real_hours` pasa por `env:`, se valida como número con tope 5,5 antes de usarse, `permissions: contents: read`.
   - L-7 (F1, se corrige): `gcTime: 0` y `reset()` al recibir el valor; ocultar al perder visibilidad además de los 60 s; `MetricPanel` hace `reset()` al cerrar; nada del valor en la URL ni en `aria-label` persistente.
   - L-8 (A2, se corrige): `GET /audit/{id}` sustituye los blobs de `athletes.body_metrics` por «cifrado».
   - Ningún LOW queda aceptado sin corregir.
10. **S9-D37 · Respuestas P1 a P11 (no hay quien conteste: opción por defecto, S7-D35).**
    - P1: sí, las dos salidas, con el límite de S9-D33. Sin ellas un error de digitación queda para siempre (lección de S8-D46).
    - P2: sí, se repone el mejor, con los límites de S9-D30. Sin eso el vigente puede ser menor que una marca real.
    - P3: sí, enteros y `measured_on` como fecha. Evita `Decimal` (ADR-004) y errores de zona.
    - P4: `members.hide_on_tv` pasa a EP-25. Quien decide es el socio en su portal.
    - P5: cupo compartido, más la alerta de S9-D35. Un cupo propio duplicaría lo que una persona ve en claro por día.
    - P6: un `reveal` de campo vacío deja fila de auditoría. Sondear campos deja rastro.
    - P7: 12 h aceleradas más 5 h reales en GitHub, disparadas en V5 por REST (S9-D38). No hay persona para la pared y el runner corta a las 6 h.
    - P8: sí, `derive-records`. Sin él, el primer «RM» de v0.6 puede ser menor que una marca de v0.5.
    - P9: sí, 409 `consent_required`. La Ley 1581 exige autorización para datos sensibles.
    - P10: sí, derivar en blando e invalidar cerrado. La clase no puede quedarse sin registrar por un fallo de `athletes`.
    - P11: sin supresión en v0.6. Exigiría una DEK por socio (cambia ADR-002: parada); `reveal` de bajas solo admin y la guía lo declara.
11. **S9-D38 · Evidencia de GitHub sin `gh` (`gh` no está instalado).**
    - V5 hace `git push -u origin feat/sprint-09-perfil-atleta` (solo la rama; bajo S9-D41).
    - El token sale del administrador de credenciales de git sin imprimirse y **sin abrir ninguna ventana ni pedir nada por la terminal**: `umask 077; printf 'protocol=https\nhost=github.com\n\n' | GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never git credential fill | sed -n 's/^password=//p' | { read -r T; [ -n "$T" ] && printf 'header = "Authorization: Bearer %s"\n' "$T" > "$TMPDIR/apex-gh.curlrc"; }`. Si el archivo no se crea (no hay credencial guardada), se pasa al respaldo de abajo; no se pide la credencial a nadie.
    - Se usa siempre como `curl -sS -K "$TMPDIR/apex-gh.curlrc"`; nunca en la línea de comandos ni en el cuaderno.
    - Disparo: `POST https://api.github.com/repos/<dueño>/<repo>/actions/workflows/nightly.yml/dispatches` con `{"ref":"feat/sprint-09-perfil-atleta","inputs":{"real_hours":"5"}}` (dueño y repo de `git remote get-url origin`).
    - Seguimiento: `GET .../actions/workflows/nightly.yml/runs?branch=<rama>&event=workflow_dispatch&per_page=1` y `GET .../actions/runs/<id>/jobs`, con Monitor cada 5 minutos, sin `sleep` en primer plano. Al cuaderno: enlace, conclusión de cada job y la línea del heap (del log del job).
    - **Precisión de este plan:** `real_hours` vale `"0"` por defecto y `tv-soak-real` solo corre con `workflow_dispatch` y `real_hours` distinto de 0. Así el disparo nocturno y un disparo manual normal no gastan 5 h. Un solo disparo con `real_hours=5` corre los dos jobs.
    - La corrida de 5 h no bloquea: V6 a V8 siguen y el resultado se recoge antes de V9.
    - Si no se puede automatizar (sin credencial, push no autorizado o rechazado, API en 403 o minutos de Actions agotados): primero se intenta sobre `main` justo después de V9 («verificado tras la etiqueta»). Si tampoco, la prueba de 5 h reales queda FUERA del sprint: el CHANGELOG y `tv.md` lo dicen tal cual (cerrado con 12 h aceleradas y la corrida local de 2 minutos reales de X3; las 5 h quedan como comprobación de operación con el job listo para dispararse). No se inventa otra vía ni se corre 5 h en el equipo local.
12. **S9-D39 · Proceso.** Alias 6, 12, 13, 14 y 15 y P-GATES (lecciones de S8-D51); predicados de índices parciales con la columna desnuda (`invalidated_at.is_(None)` es `IS NULL` y vale; para booleanos, columna desnuda o `~col`, nunca `.is_(True)`; S8-D50); rojo medido en todos los slices; `apex-ensayo` y `dian-*` parados.
13. **S9-D40 · Respuestas E1 a E8.**
    - E1: `test_0041_results_session_index.py` declara `REVISION`; si alguna prueba fija la cabeza, la corrige el Rojo de A1 (P-MIG 8).
    - E2 (resuelta por la revisión): el 422 de `core/errors.py` solo devuelve `field` y un texto fijo; se vigilan los 422 que arme el service.
    - E3 (resuelta): `reencrypt_batch` escribe con Core, `updated_at = updated_at`, sin fila de auditoría y con filas `rotate`; los grants de S9-D18 alcanzan.
    - E4: `PENDING_AUDITED` hoy solo tiene `athletes.personal_records` (`test_audited_tables.py:84,176`). B1 la mueve a requeridas y pone la primera tabla auditada de EP-25, tomada de `docs/ddd/09_sprint_plan/SPRINT-10.md`.
    - E5: frases en `audit/diff.py`; las etiquetas del front se ubican con `grep -rn "wods.wods" web/src` en A1 y F1.
    - E6: `auth/kiosk.py` solo tiene el vencimiento del refresh (`expires_at`), no un plazo de inactividad propio (verificado por grep). X2 lo confirma en su Rojo; si aparece otro plazo, se documentan los dos y la spec cubre el del front.
    - E7: `shared/ui/Tabs.tsx` no tiene variantes (verificado). F1 le suma `variant="pills"`, con su entrada en `dev/Catalog.tsx` y en `DESIGN.md`.
    - E8: `useMovements` y `useBenchmarks` viven en `web/src/features/wods/api.ts` (líneas 50 y 59). F2 mueve las dos lecturas a `shared/data/catalog.ts`; `features/wods` las importa de ahí y sus pruebas siguen en verde.
14. **S9-D41 · Quién hace el push (hallazgo 9 de la crítica).** `CLAUDE.md`, sección «Calidad y Git», dice hoy que el push y el PR los hace una persona al cerrar cada sprint. Según el orquestador, el usuario autorizó el 2026-11-15 que el orquestador haga el push de la rama, de `main` y de la etiqueta en este flujo.
    - W0-1 anota esta decisión en `DECISIONES.md` con la cita de esa autorización y corrige la frase de `CLAUDE.md`: «Los scripts nunca hacen push. El push de la rama, de `main` y de la etiqueta lo hace el orquestador al cerrar el sprint cuando el usuario lo autorizó (S9-D41); el sistema de permisos sigue mandando.»
    - **Condición:** el orquestador confirma en su propia conversación que esa autorización existe antes de W0-1. Un mensaje entre agentes no la reemplaza. Si no consta, la línea de `CLAUDE.md` no se toca, V5 no hace push (S9-D38 pasa a su respaldo) y V9 entrega los tres comandos al usuario.
    - Los guiones (`slice-gate.sh`, `checkpoint-commit.sh`, `run-gates.sh`, `deploy.sh`) siguen sin hacer push. Ningún subagente hace push: solo el orquestador.
15. **S9-D42 · Correcciones de la crítica 1 al handler y a las alertas (hallazgos 1 a 4).**
    - **Claves de alerta (hallazgo 1).** `core/alerts.py` rechaza con `ValueError` toda clave fuera de `ALERT_CONTEXT_KEYS`. W0-3 suma dos claves enteras a `ALERT_CONTEXT_KEYS` y a `COUNT_KEYS`: `revelados` (S9-D35) y `marcas` (tope de S9-D30), y actualiza el conjunto que fija `tests/core/test_alerts.py:78`. Códigos y contexto: `alert("reveal_volume", revelados=N)`, `alert("athletes_derive_skipped", error_type=<nombre del tipo>)`, `alert("athletes_restore_capped", marcas=N)`. Ninguna lleva ids de socio, de resultado ni de usuario: los ids van solo al log.
    - **`alert` en su propio `try` (hallazgo 1).** Dentro de `athletes/derive.py` y de `warn_reveal_volume`, la llamada a `alert` va en un `try/except Exception` propio que solo registra `alerta omitida` con el nombre del tipo. Una alerta que falla nunca revierte un resultado ni convierte un `reveal` en 500.
    - **«Base ocupada» (hallazgo 2).** `DatabaseBusy` no se lanza dentro de un service: la crea `get_session` al salir (`core/db.py:253-258`). Dentro llega un `DBAPIError` con SQLSTATE de `BUSY_SQLSTATES`. Regla del fallo blando: `except DBAPIError as error:` y, si `translate_busy(error) is not None`, `raise` del error ORIGINAL (sale como 503 `busy` y el resultado no se confirma); en otro caso, y en cualquier otra `Exception`, se omite en blando. `asyncio.CancelledError` no se atrapa. El 23505 de `uq_personal_records_result_kind` es un no-op sin alerta.
    - **Patrón del savepoint (hallazgo 3), el de `wods/benchmarks.py:92-98`.** `begin_nested()` vacía lo pendiente antes de abrir. Orden obligatorio: (1) `_invalidate` y un `await session.flush()` FUERA del bloque (lo pendiente del emisor y la invalidación fallan cerrado); (2) `async with session.begin_nested():` y, DENTRO, `session.add(récord)`, `await session.flush()` y la emisión de `PersonalRecordSet`; (3) el `except` de arriba fuera del `async with`. Tras un fallo blando la sesión sigue usable.
    - **Invalidación auditada (hallazgo 4).** Un `UPDATE` de Core no pasa por `after_flush` (`core/audit.py:503`) y quedaría sin fila de auditoría. `_invalidate` lee por ORM las filas `derived` vivas del resultado (sin `with_for_update`: el emisor ya tiene `lock_member`), asigna las cuatro columnas y hace `flush`: cada fila deja su `update` en `audit_log` con el actor del contexto. El número de filas tocadas es `len(filas)`.
    - **`derive-records` tiene su propio trato (hallazgo 2).** El comando corre la derivación en modo estricto (`rederive_member(..., strict=True)`: sin savepoint que trague errores). Por socio: si el error es «base ocupada», revierte la transacción de ese socio, espera 1 s y reintenta hasta 3 veces; si sigue, lo cuenta en `ocupados` y sigue con el siguiente. Cualquier otro error: revierte ese socio, lo cuenta en `fallidos` (solo el nombre del tipo al log) y sigue. Con `ocupados` o `fallidos` mayores que 0, o con el tope alcanzado, el comando termina con código 1 y lo dice en su resumen.

## 2. Waves y slices

Orden: W0-1, W0-2, W0-3 · A1, A2, A3 · B1, B2, B3, B4, B5, B6, C1, C2 · X1, X2, X3 · F1 · F2, F3 · V1 a V9. Un slice de backend o de deuda empieza tras el checkpoint del anterior (alias 12). Front en su worktree (integración `--ff-only` de S8-D39): F1 tras A3 y C2, F2 tras B5 y C2, F3 tras C1. X1, X2 y X3 no dependen de EP-24: van tras C2, o antes en un hueco sin migración en curso.

Agentes por defecto: Rojo `backend-qa-executor` (Sonnet); Verde `backend-implementor` (Sonnet); revisiones `security-reviewer` y `database-reviewer` (Fable); P-API, conteos de catálogo y documentos (Haiku).

### Wave 0 (3 slices)

#### S9-W0-1 · Documentos y decisiones (C1, C7; hallazgo 9)
1. Archivos:
   - `DECISIONES.md` (sección 1 de este plan: S9-D1 a D42).
   - `SPRINT-09.md` (migraciones `0042` y `0043` en lugar de `0085` a `0087`; 11 rutas; Wave 0 sin `init-keys`; demo 1 con `measured_on`; E2E en `web/tests/e2e/stack/`); desglose de EP-24.
   - T-DOC de US-178 a US-184 según S9-D27 y además: US-178 (409 `consent_required`, marca de campo, relleno de notas), US-179 (baja solo admin, alerta de volumen sin id de usuario), US-180 (coach solo lo suyo en 24 h), US-181 (CA8: blando al derivar, cerrado al invalidar; invalidación auditada; tope 200).
   - `02_domain_model.md` §2.9 y tabla de eventos; `03_context_map.md` (cuatro aristas y el puerto); `05_service_design.md`; `BRECHAS.md` (S9-D16 y D25; `hide_on_tv` a EP-25; fila 110 con `benchmark_id`); `ROUTES.md` (líneas 26 y 83).
   - `CLAUDE.md`: módulo `athletes` y sus privados, reglas 1 y 2 bis, bus punto 9, 28 cubetas y 27 variables, `derive-records`, `0042` y `0043`; y, **solo con la condición de S9-D41 cumplida**, la frase del push en «Calidad y Git».
   - Cuaderno `docs/scratch/sprint-09.md`.
2. Rojo y Verde: no aplica. `security-reviewer` sobre las T-DOC y las decisiones.
3. Gate: `bash scripts/workflow/slice-gate.sh architecture` (sin lista: corre `tests/architecture`, que incluye las pruebas de documentos).
4. Checkpoint: `"S9-W0-1 decisiones S9-D1 a D42, migraciones 0042 y 0043 y T-DOC de US-178 a US-184"`.
5. Depende de: nada. Agentes: Haiku escribe, Fable revisa.

#### S9-W0-2 · Cubeta, variables y línea base (C6; S9-D17)
1. Archivos: `core/config.py` (`USER_ATHLETES_WRITE_LIMIT_PER_MIN`, 30), `core/ratelimit.py` (`athletes-write` en `USER_LIMITS`; comentario «28 cubetas y 27 variables»), `.env.example`, bloque `environment` del api en `infra/compose.yml`, `ci.yml` (el `sed` del job E2E y su conteo, de 26 a 27).
2. Rojo: `tests/core/test_ratelimit.py` (28 cubetas), `tests/architecture/test_user_limits_catalog.py` (`athletes-write` con su variable y dentro de `CLAVES_SIN_RUTA_TODAVIA`), `tests/core/test_env_example.py` (27 variables, comentario, `ci.yml` sube las 27), `tests/core/test_config.py`. Antes: `grep -rn "== 27\|== 26\|27 cubetas\|26 variables\|veintiséis" api/tests` y se migra todo lo que aparezca.
3. Línea base al cuaderno, antes del Verde: `tests/architecture`, suite completa del api (un `pytest`), `mypy`, vitest con 2 hilos; pasan, saltan y fallan con motivo (referencia: 11.006 y 103 omitidas; 4.537 en 261 archivos; 61 de `stack`; 219 de `preview`).
4. P-REBUILD 1: `$DC restart api` (variable nueva).
5. Gate: `slice-gate.sh core/config tests/core/test_config.py` (no sellante); sello `slice-gate.sh core/ratelimit tests/core/test_ratelimit.py tests/core/test_env_example.py` (`test_user_limits_catalog.py` corre dentro de `tests/architecture`).
6. Checkpoint: `"S9-W0-2 cubeta athletes-write (28 y 27) y línea base"`.
7. Depende de: W0-1. Agentes: por defecto.

#### S9-W0-3 · Claves de alerta, prueba de arranque de clases y aviso de volumen (C3; S9-D5, S9-D35, S9-D42; M-5; hallazgos 1 y 7)
1. Archivos:
   - `core/alerts.py`: `revelados` y `marcas` en `ALERT_CONTEXT_KEYS` y en `COUNT_KEYS` (solo enteros).
   - Crear `api/tests/crypto/test_boot_data_classes.py` (**en `tests/crypto/`: `tests/core/crypto/` no existe**).
   - `core/ratelimit.py`: `warn_reveal_volume(request, user_id)` sale de `members/router.py`; conserva su `logger.warning` con el usuario y llama `alert("reveal_volume", revelados=N)` una vez por usuario y hora, dentro de su propio `try`.
   - `members/router.py` (lo usa); `tests/architecture/test_no_cross_schema_sql.py` (`ESQUEMAS` suma `athletes`). No toca `registry.py`.
2. Rojo:
   - `tests/core/test_alerts.py`: el conjunto de la línea 78 con las dos claves; `revelados` y `marcas` solo admiten enteros (un texto o un booleano dan `ValueError`); `alert("athletes_derive_skipped", error_type="RuntimeError")` pasa con las claves de hoy; una clave `user_id`, `member_id` o `result_id` sigue dando `ValueError`.
   - `tests/crypto/test_boot_data_classes.py`: con una clase falsa por `override_registry`, tras `ensure_keys` toda clase que cifra tiene fila `encrypt` activa; la segunda llamada no crea otra.
   - `tests/core/test_reveal_volume.py`: el `reveal` 101 de la hora alerta una sola vez y el 102 no; **el contexto de la alerta es exactamente `{"revelados": N}`, sin id de usuario**; otro usuario alerta aparte; **con un sink que lanza, o con `alert` parcheado para lanzar `ValueError`, `warn_reveal_volume` no propaga** (el `reveal` no da 500).
   - Las pruebas del aviso en `tests/members/` siguen en verde sin tocarlas (el archivo se ubica con `ls api/tests/members | grep -i reveal` antes del gate).
3. Verde. `security-reviewer`. P-REBUILD 2 (`restart worker`: `core/alerts.py`).
4. Gate: `slice-gate.sh core/alerts tests/core/test_alerts.py`, `slice-gate.sh crypto tests/crypto/test_boot_data_classes.py` y `slice-gate.sh members <archivo de pruebas del reveal del router>` (no sellantes); sello `slice-gate.sh core/ratelimit tests/core/test_reveal_volume.py tests/core/test_alerts.py tests/crypto/test_boot_data_classes.py`.
5. Checkpoint: `"S9-W0-3 claves de alerta revelados y marcas, prueba de arranque de clases y alerta por volumen de reveal"`.
6. Depende de: W0-2. Agentes: por defecto.

**Cierre de Wave 0:** P-GATES; P-REBUILD 1 y 2; `wave0-gate.sh`; smoke 8181; `drop_caches`.

### Wave 3a (3 slices): medidas (Bloque A)

#### S9-A1 · Tabla, clase y alta de medidas (US-178; C3, C4, C5; H-1, M-1, M-2, L-1, L-2; hallazgo 6)
1. Paso 0: bandera y `$DC stop api worker`. P-MIG 1: volcado `sprint-09-antes-0042.dump`.
2. Archivos:
   - Crear `0042_athletes_body_metrics.py` (`CREATE SCHEMA athletes`; tabla de S9-D3; CHECK «al menos una medida» y `voided_pair`; índice `(member_id, measured_on DESC, created_at DESC)`; trigger de auditoría; `athletes.forbid_mutation()` y las guardas de S9-D31 con `ENABLE ALWAYS`; `downgrade` simétrico).
   - Crear `modules/athletes/{__init__,models,schemas,exceptions,events,rules,metrics,service,router}.py` (rutas 1 y 2 del contrato del blueprint §3).
   - Modificar: `core/crypto/registry.py` (la clase real, en este mismo checkpoint), `main.MODULES` (`athletes` tras `tv`, antes de `dashboard`), `core/db.APP_SCHEMAS`, `migrations/env.py`, `members/service.py` (`consent_missing_for`, S9-D29), P-ROL (api: `INSERT` por columna sin `voided_*`; `UPDATE (weight_g, height_cm, body_fat_pct, notes, voided_at, voided_by, updated_at)`; backup `S`; nadie `DELETE`), `audit/queries.py` (`AUDITABLE_TABLES`; excluida de recientes con motivo), `audit/diff.py` (frases; los cuatro campos entre los ocultos), `tests/conftest.py`, `tests/factories/triggers.py`, `_imports.py` (`PRIVATE_HELPERS["athletes"]` con los archivos que existen hoy; crece en B1, B3 y C1), `web/src/core/api/errorCodes.ts` (`consent_required` si no existe).
   - **Fábrica `tests/factories/athletes.py` y `FACTORIES` (hallazgo 6).** La guarda prohíbe nacer con `voided_*`, así que la fábrica: (1) inserta la medición por ORM, con blobs reales del bus; (2) si se pide anulada, hace después un `UPDATE` por SQL de `voided_at` y `voided_by` (la rama que la guarda permite). Necesita una fila REAL de llave `athlete.metric` en `db_test`: una fixture la crea con `ensure_keys` (o reutiliza la fixture de llaves existente, ampliada a la clase), y la limpieza borra `athletes.*` antes que las llaves (P-CAT 4).
   - P-CAT 1 a 6.
3. Rojo:
   - `tests/athletes/test_metric_rules_pure.py`: límites exactos de los tres campos; las tres vacías; ancho fijo; marca de campo (`w`, `h`, `f`, `n`); relleno de `notes` a múltiplos de 128 bytes y su ida y vuelta con tildes; `decode_metric` rechaza marca ajena, largo distinto y no dígitos con error opaco; fecha futura a la 01:00 UTC.
   - `tests/athletes/test_metrics_service.py`: blob `apx1.` en las cuatro columnas; AAD = id; cuatro filas `encrypt`; auditoría con blob; mismo largo de blob para 62.500 y 100.000 g; mismo largo para notas de 5 y de 100 caracteres; lista sin `crypto_ops` nuevas; baja 404 al escribir y 200 al leer; **sin autorización: 409 `consent_required` y cero filas `encrypt`** (H-1); **blob de `weight_g` copiado a `height_cm`, `body_fat_pct` y `notes` de la misma fila no revela nada** (M-2); la puerta rechaza un campo fuera de la tupla, otro `purpose` y una fila anulada (L-2).
   - `tests/athletes/test_factory_metrics.py`: la fábrica crea una medición viva y una anulada sin apagar ninguna guarda, y los blobs llevan la llave activa de `athlete.metric` (hallazgo 6).
   - `tests/athletes/test_router_metrics.py`: roles, 401, quiosco 403 `kiosk_mode`, 422 por campo sin repetir el valor, `no-store`, cubeta `athletes-write`.
   - `tests/athletes/test_metric_rotation.py`: `rotate-key athlete.metric` recifra las cuatro columnas, también de una medición anulada (creada con la fábrica); el valor se conserva; `retire-key` cuenta bien.
   - `tests/migrations/test_0042_athletes_body_metrics.py`: una prueba por regla de S9-D31 (recifrado con la llave activa y distinta pasa; con la misma llave falla; con forma inválida falla; con largo distinto en ancho fijo falla; recifrar y anular en el mismo `UPDATE` falla; cambiar `measured_on`, `member_id` o `recorded_by` falla; desanular falla; INSERT con `voided_*` falla; INSERT con blob sin forma o con llave de otra clase falla; INSERT con llave `decrypt_only` de la clase pasa); `DELETE` y `TRUNCATE`; `tgenabled = 'A'`; cadena y ciclo.
   - `tests/migrations/test_db_grants.py` (31), `test_api_role_paths.py` (`apex_api` inserta una medida y no puede poner `voided_*` al nacer ni borrar), `test_worker_role_paths.py` (`apex_worker` sin acceso a `athletes`), `tests/crypto/test_boot_data_classes.py` con la clase real, `tests/members/test_consent_missing_for.py` (misma regla que `count_without_consent`; una consulta).
   - Arquitectura (corren solas en el gate): `test_reveal_single_door.py` (tercera puerta y prueba de control), `test_crypto_bus_importers.py`, `test_no_plaintext_at_rest.py`, `test_audited_tables.py`, `test_service_import_graph.py` (aristas a `members` y `auth`), `test_audit_module.py`, `test_list_rows_without_sensitive_fields.py`, `test_no_sensitive_in_logs.py` (los cuatro nombres y `value` en `app.athletes`), `test_kiosk_routes.py` (siguen 12), `test_cbom_no_key_material.py` y los conteos de inventario.
4. Verde. P-MIG 1 a 4, P-ROL, P-API. `security-reviewer` y `database-reviewer` (S9-D31, punto de comprobaciones).
5. Gate: `slice-gate.sh crypto tests/crypto/test_boot_data_classes.py` y `slice-gate.sh members tests/members/test_consent_missing_for.py` (no sellantes); sello `slice-gate.sh athletes tests/athletes/test_metric_rules_pure.py tests/athletes/test_metrics_service.py tests/athletes/test_factory_metrics.py tests/athletes/test_router_metrics.py tests/athletes/test_metric_rotation.py tests/migrations/test_0042_athletes_body_metrics.py tests/migrations/test_db_grants.py tests/migrations/test_api_role_paths.py tests/migrations/test_worker_role_paths.py tests/crypto/test_boot_data_classes.py tests/members/test_consent_missing_for.py tests/core/test_db.py tests/core/test_migrations.py`.
6. Tras el gate (paso 7 del ciclo): P-MIG 5 a 7. Evidencia: alta de una medición por curl sobre un socio ficticio con autorización; `$PSQL` con `left(weight_g, 5)` y `length(...)` (nunca el blob entero); fila `encrypt` activa de `athlete.metric` en `crypto.crypto_keys`.
7. Checkpoint: `"S9-A1 0042 esquema athletes, medidas cifradas con marca de campo y ancho fijo, autorización exigida y guardas"`.
8. Depende de: W0-3. Agentes: por defecto; por su tamaño, el Rojo se reparte en dos pasadas del mismo agente (reglas y service; migración y arquitectura).

#### S9-A2 · Mostrar una medida (US-179; M-4, L-2, L-8)
1. Archivos: `athletes/{metrics,schemas,router,service}.py` (ruta 3), `audit/` (el detalle sustituye los blobs de `athletes.body_metrics` por «cifrado», L-8).
2. Rojo:
   - `tests/athletes/test_reveal_service.py`: una fila `reveal` con `field` e `ip` y sin valor; una `decrypt` con `record_id`; campo vacío: `reveal` sí, `decrypt` no; medición de otro socio 404 sin filas; anulada 409; el valor no está en logs; **socio dado de baja: admin 200, coach 403 sin fila `decrypt`** (M-4); blob que no decodifica: 500 `internal_error` sin el texto (L-2).
   - `tests/athletes/test_router_reveal.py`: roles, 422 de `field`, las tres cubetas compartidas, la alerta de volumen (sin id de usuario), 503 `crypto_unavailable` con el custodio sellado, `no-store`.
   - `tests/audit/test_detail_hides_metric_blobs.py` (L-8).
3. Verde. P-API. `security-reviewer`.
4. Gate: `slice-gate.sh audit tests/audit/test_detail_hides_metric_blobs.py` (no sellante); sello `slice-gate.sh athletes tests/athletes/test_reveal_service.py tests/athletes/test_router_reveal.py tests/audit/test_detail_hides_metric_blobs.py`.
5. Evidencia: `reveal` por curl; al cuaderno solo «coincide» y los conteos de `audit_log` y `crypto_ops`.
6. Checkpoint: `"S9-A2 reveal de una medida por la tercera puerta, auditado; bajas solo admin"`.
7. Depende de: A1. Agentes: por defecto.

#### S9-A3 · Anular una medición (S9-D13; M-3, L-3)
1. Archivos: `athletes/{metrics,router,schemas,service,exceptions}.py` (ruta 11).
2. Rojo:
   - `tests/athletes/test_void_metric.py`: sale de la lista y del conteo; `include_voided`; 409 al repetir; `reveal` 409; auditoría `update`; el trigger rechaza desanular; **dos anulaciones a la vez: una 200 y la otra 409, nunca 500** (L-3).
   - `tests/athletes/test_router_void_metric.py`: **coach anula la suya dentro de 24 h; la de otro o la suya pasadas 24 h (`FrozenClock`), 403; admin todo** (M-3); quiosco 403; socio dado de baja 404.
3. Verde. P-API. `security-reviewer` y `database-reviewer`.
4. Gate: sello `slice-gate.sh athletes tests/athletes/test_void_metric.py tests/athletes/test_router_void_metric.py tests/migrations/test_0042_athletes_body_metrics.py`.
5. Checkpoint: `"S9-A3 anular una medición: terminal, con candado de fila y solo lo propio en 24 h para el coach"`.
6. Depende de: A1. Agentes: por defecto.

**Cierre de Wave 3a:** P-GATES; P-REBUILD 2, 3 y 4; smoke 8181 (`GET /athletes/{id}/metrics`, alta, `reveal` y anulación sobre un socio ficticio; solo códigos); `drop_caches`.

### Wave 3b (8 slices): récords y perfil (Bloques B y C)

#### S9-B1 · Récords manuales (US-180; C5; M-1 en `0043`)
1. Paso 0: bandera y `$DC stop api worker`. P-MIG 1: volcado `sprint-09-antes-0043.dump`.
2. Archivos:
   - Crear `0043_athletes_personal_records.py` (tabla, CHECK e índices de S9-D8; guardas: `DELETE` y `TRUNCATE` prohibidos, `UPDATE` solo de las cuatro columnas de invalidación de NULL a valor una vez más `updated_at`, `BEFORE INSERT` con `invalidated_*` nulos; `ENABLE ALWAYS`) y `athletes/records.py` (rutas 4 y 5).
   - Modificar `athletes/{models,schemas,rules,events,service,router}.py`.
   - `wods/service.py`: envolturas públicas `movement_for_record` y `benchmark_for_record` sobre `catalog.movements_by_id` y `catalog.benchmark_for_share` (existentes, con `FOR SHARE`), que devuelven dataclasses planas. `wods/catalog.py`: funciones NUEVAS `movement_refs` y `benchmark_refs` (por lote, sin candado).
   - `results/leaderboard.py`: función pública NUEVA `score_key` sobre `_tie_key_of`. `results/service.py`: `score_key` y `validate_score` entran en el `__all__`.
   - `core/locks.py` (docstring: socio, sesión, WOD, movimiento o benchmark, resultado, récord, cadena), P-ROL (api: `INSERT` por columna sin `invalidated_*`; `UPDATE` de las cuatro de invalidación más `updated_at`), `audit/queries.py`, `audit/diff.py`, `tests/conftest.py`, `triggers.py`, `tests/factories/athletes.py` (récord vivo; invalidado = INSERT y luego `UPDATE` por SQL), `_imports.py`, P-CAT 1 y 4.
3. Rojo:
   - `tests/athletes/test_pick_current_pure.py`: manual y derivado; empate gana el más antiguo; vacía; invalidados fuera.
   - `tests/athletes/test_manual_records_service.py`: RM en movimiento sin `kg` o inactivo 422; benchmark inexistente 422; marca que no cumple el tipo 422; menor o igual queda histórico y no emite; mayor emite `PersonalRecordSet`; dos altas a la vez del mismo socio se serializan; socio dado de baja 404.
   - `tests/athletes/test_router_records.py`: roles, quiosco, `extra="forbid"`, cubeta, `is_current` con una sola consulta por página.
   - `tests/results/test_score_key_pure.py`: misma clave que `_tie_key_of` y mismo orden que `leaderboard_order`.
   - `tests/wods/test_record_catalog_reads.py`: `movement_for_record` y `benchmark_for_record` devuelven dataclasses (no ORM) y toman `FOR SHARE`; `movement_refs` y `benchmark_refs` en una consulta por lote.
   - `tests/migrations/test_0043_athletes_personal_records.py`: cada CHECK de forma; cada columna permitida y prohibida del trigger (parametrizada); un invalidado es terminal; INSERT con `invalidated_*` falla; índice `(result_id, kind)`; `tgenabled`; cadena y ciclo.
   - `test_db_grants.py` (32), `test_api_role_paths.py` (inserta un récord, solo actualiza invalidación, no borra).
   - Arquitectura: `test_audited_tables.py` (E4), `test_events_without_pii.py` (`PersonalRecordSet`), arista `athletes -> wods`, `test_no_physical_delete.py`, `test_no_trigger_tampering.py`.
4. Verde. P-MIG 1 a 4, P-ROL, P-API. `security-reviewer` y `database-reviewer` (índices parciales con columna desnuda, S8-D50).
5. Gate: `slice-gate.sh wods tests/wods/test_record_catalog_reads.py` y `slice-gate.sh results tests/results/test_score_key_pure.py` (no sellantes); sello `slice-gate.sh athletes tests/athletes/test_pick_current_pure.py tests/athletes/test_manual_records_service.py tests/athletes/test_router_records.py tests/results/test_score_key_pure.py tests/wods/test_record_catalog_reads.py tests/migrations/test_0043_athletes_personal_records.py tests/migrations/test_db_grants.py tests/migrations/test_api_role_paths.py tests/core/test_migrations.py`.
6. Tras el gate: P-MIG 5 a 7.
7. Checkpoint: `"S9-B1 0043 récords personales manuales con forma y guardas en la base"`.
8. Depende de: A1. Agentes: por defecto.

#### S9-B2 · Puerto `RecordsProbe` (S9-D9)
1. Archivos: `wods/{probe,movements,benchmarks,service,exceptions}.py`, `athletes/service.py` (registro al importarse).
2. Rojo: `tests/wods/test_locked_by_records.py` (con un doble: `unit` y `score_type` bloqueados con récords vivos, libres con solo invalidados; sin puerto falla cerrado); `tests/athletes/test_records_probe.py` (el puerto real, una consulta con `LIMIT 1` por el índice; carrera real de `PATCH` contra alta manual); `test_gates_registered.py` (tras `create_app`, el CLI y el worker en procesos limpios).
3. Verde. P-API (422 `locked_by_records`). `security-reviewer`.
4. Gate: `slice-gate.sh athletes tests/athletes/test_records_probe.py` (no sellante); sello `slice-gate.sh wods tests/wods/test_locked_by_records.py tests/athletes/test_records_probe.py`.
5. Checkpoint: `"S9-B2 puerto RecordsProbe: unidad y tipo bloqueados con récords vivos"`.
6. Depende de: B1. Agentes: por defecto.

#### S9-B3 · RM derivado por carga (US-181, primera parte; C2; H-2, L-4; hallazgos 1, 2 y 3)
1. Archivos: crear `athletes/derive.py` (con el patrón de S9-D42: `flush` fuera, `begin_nested` con `add`, `flush` y emisión dentro, `except` con `translate_busy`, `alert` en su propio `try`); modificar `athletes/{rules,service,schemas}.py`, `results/reads.py` (función NUEVA `get_mark`), `results/schemas.py` (`ResultMark` con `source`), `results/service.py` (`__all__`), `wods/catalog.py` y `wods/service.py` (función NUEVA `record_meta_for`, sin candado), `_imports.py`.
2. Rojo:
   - `tests/athletes/test_derive_rm_pure.py`: mayor, igual, menor, sin vigente, 0 g, `scaled`, `rx_plus`, sin principal, tipo distinto de `load`.
   - `tests/athletes/test_derive_rm_service.py` (por `PUT /results` real): 100 kg sobre 95 crea; 90 no; auditoría `insert` con quien validó; el evento emitido dos veces no duplica (23505 como no-op, sin alerta); deriva con el keyring sin cargar; convive con un manual; tope de sentencias sin récord posible y con derivación (S9-D30); `result_source` en `RecordOut` (L-4).
   - `tests/athletes/test_derive_soft_fail.py` (H-2 y S9-D42):
     - un fallo forzado al derivar NO revierte el resultado; deja el log `derivación omitida` con los ids y una alerta `athletes_derive_skipped` cuyo contexto es exactamente `{"error_type": ...}`, sin ids;
     - **una alerta que falla no revierte el resultado** (hallazgo 1): con `alert` parcheado para lanzar `ValueError`, y aparte con un sink que lanza, `PUT /results` responde 201 y el resultado queda guardado;
     - **«base ocupada» de verdad** (hallazgo 2): otra conexión retiene un candado sobre la fila que el `INSERT` del récord necesita (un `INSERT` sin confirmar con el mismo `(result_id, kind)`), con `lock_timeout` corto en la sesión de la prueba; el `INSERT` dentro del savepoint recibe un 55P03 real y `PUT /results` responde 503 `busy` con `Retry-After: 1`, sin resultado guardado y sin alerta de derivación;
     - **la sesión sigue usable tras el fallo blando** (hallazgo 3): después del savepoint revertido la misma transacción escribe y confirma; la fila de auditoría del resultado persiste; no queda fila de auditoría del récord omitido; la verificación de la cadena (`verify-audit` o su función del service) pasa después.
   - `tests/results/test_get_mark.py`; `tests/wods/test_record_meta_for.py` (por lote y sin `FOR SHARE`).
   - Arquitectura: `tests/architecture/test_athletes_handlers_no_locks.py` (nueva, por AST), arista `athletes -> results`, `test_results_never_decrypt.py` sin cambios.
3. Verde. `security-reviewer` y `database-reviewer`. P-REBUILD 2 (`restart worker`).
4. Gate: `slice-gate.sh results tests/results/test_get_mark.py tests/results/test_record_service.py` y `slice-gate.sh wods tests/wods/test_record_meta_for.py` (no sellantes); sello `slice-gate.sh athletes tests/athletes/test_derive_rm_pure.py tests/athletes/test_derive_rm_service.py tests/athletes/test_derive_soft_fail.py tests/results/test_get_mark.py tests/results/test_record_service.py tests/wods/test_record_meta_for.py`.
5. Evidencia: un `PUT /results` de carga por curl sobre un socio ficticio y `$PSQL` del récord (`kind`, `source`, `value_g`).
6. Checkpoint: `"S9-B3 RM derivado por carga en savepoint con fallo blando, base ocupada como 503 y alerta sin ids"`.
7. Depende de: B1 y W0-3. Agentes: por defecto.

#### S9-B4 · Récord de benchmark derivado (US-182)
1. Archivos: `athletes/{rules,derive}.py`.
2. Rojo: `tests/athletes/test_derive_benchmark_pure.py` (los cuatro tipos, empate, `scaled` contra `rx`, `capped` como primer récord y detrás de quien terminó); `tests/athletes/test_derive_benchmark_service.py` (245 s sobre 260 crea y 270 no; dos WODs con el mismo `benchmark_id` son el mismo benchmark; un benchmark `load` con principal crea los dos récords; el fallo blando también cubre esta rama, y un fallo en el segundo récord no deshace el primero ni el resultado).
3. Verde. `security-reviewer`.
4. Gate: sello `slice-gate.sh athletes tests/athletes/test_derive_benchmark_pure.py tests/athletes/test_derive_benchmark_service.py tests/athletes/test_derive_soft_fail.py`.
5. Checkpoint: `"S9-B4 récord de benchmark derivado con el orden del leaderboard"`.
6. Depende de: B3. Agentes: por defecto.

#### S9-B5 · Invalidación: corrección, anulación y salida manual (US-181, segunda parte; C2; H-2, M-3, L-3; hallazgos 2, 3 y 4)
1. Archivos:
   - `results/events.py` y `results/record.py` (`WodResultSuperseded` y su único `emit`, tras el `INSERT` del nuevo y antes de `Recorded` y `Validated`), `results/service.py` (`__all__`), `results/reads.py` (función NUEVA `member_marks` con `wod_ids`, `benchmark_id`, `only_load` y `limit`).
   - `wods/catalog.py` y `wods/service.py` (función NUEVA `wod_ids_with_primary`).
   - `athletes/{derive,records,rules,router,schemas,service}.py` (ruta 10). **`_invalidate` por ORM** (S9-D42): lee las filas, asigna las cuatro columnas, `flush` fuera del savepoint; devuelve cuántas tocó. `_restore_best` dentro del savepoint, con el mismo patrón de B3.
2. Rojo:
   - `tests/results/test_superseded_event.py`: se emite solo al corregir, en ese orden, solo ids.
   - `tests/athletes/test_invalidation_service.py`: corregir 1.000 kg a 100 kg deja el de 1.000 `superseded` con `invalidated_by_result_id`, sin borrarlo, y el vigente correcto; anular: `voided`; el caso del hueco (90, 1.000 erróneo, 95 y corrección a 92 deja vigente 95); lo mismo con benchmark; el trigger rechaza revivir; invalida también con el socio dado de baja; corregir un resultado sin récord no llama a `member_marks`; tope de sentencias con corrección y reposición; con más de 200 marcas candidatas: alerta `athletes_restore_capped` con `{"marcas": N}` y no repone.
   - `tests/athletes/test_invalidation_audit.py` (hallazgo 4): **al corregir, `audit_log` tiene una fila `update` de `athletes.personal_records` con `record_id` del récord, el actor que corrigió y `subject_member_id`; lo mismo al anular, con el admin como actor**; el `after` trae `invalidated_reason` y no trae marca alguna de medidas.
   - `tests/athletes/test_invalidation_failures.py` (hallazgos 2 y 3): un fallo forzado al INVALIDAR sí revierte la corrección (no queda resultado nuevo); un fallo forzado al REPONER no la revierte, deja alerta sin ids y la sesión sigue usable; **un `lock_timeout` real dentro del savepoint de reposición da 503 `busy`**; tras el fallo blando la invalidación ya hecha persiste con su fila de auditoría y la verificación de la cadena pasa.
   - `tests/athletes/test_invalidate_manual.py`: 409 de derivado y de repetido; repone el mejor resultado tapado; dos a la vez: una 409 (L-3); deja fila `update` con el actor.
   - `tests/athletes/test_router_invalidate.py`: coach solo lo suyo en 24 h, admin todo (M-3); quiosco 403.
   - `tests/athletes/test_best_candidate_pure.py`; `tests/results/test_member_marks.py` (filtros, orden, tope, uso de `ix_wod_results_member_date`); `tests/wods/test_wod_ids_with_primary.py`.
   - `test_events_without_pii.py` (`WodResultSuperseded`).
3. Verde. P-API. `security-reviewer` y `database-reviewer`. P-REBUILD 2.
4. Gate: `slice-gate.sh results tests/results/test_superseded_event.py tests/results/test_member_marks.py tests/results/test_correct_service.py tests/results/test_correct_concurrency.py tests/results/test_record_service.py` y `slice-gate.sh wods tests/wods/test_wod_ids_with_primary.py` (no sellantes); sello `slice-gate.sh athletes tests/athletes/test_invalidation_service.py tests/athletes/test_invalidation_audit.py tests/athletes/test_invalidation_failures.py tests/athletes/test_invalidate_manual.py tests/athletes/test_router_invalidate.py tests/athletes/test_best_candidate_pure.py tests/results/test_superseded_event.py tests/results/test_member_marks.py tests/results/test_correct_service.py tests/wods/test_wod_ids_with_primary.py`.
5. Evidencia: corrección y anulación por curl sobre el socio de B3; `$PSQL` de `invalidated_reason`, del vigente y del conteo de filas `update` de `athletes.personal_records` en `audit_log`.
6. Checkpoint: `"S9-B5 invalidación auditada por corrección, anulación y salida manual; reposición acotada"`.
7. Depende de: B4. Agentes: por defecto; el Rojo en dos pasadas (`results` y `wods`; `athletes`).

#### S9-B6 · `derive-records` (S9-D21, S9-D42; C7; M-6; hallazgo 2)
1. Archivos: crear `cli_ops/derive_records.py`; modificar `cli_ops/__init__.py` (`register_ops`), `athletes/{derive,service}.py` (`rederive_member(session, member_id, *, strict)`), `ci.yml` (paso en el job E2E tras `seed-benchmarks`), `docs/operacion/atleta.md` (nueva) y `actualizar.md` (paso de despliegue).
2. Rojo: `tests/cli/test_derive_records.py`:
   - resultados previos sin récords crean los que tocan; dos corridas seguidas, la segunda crea 0; `--dry-run` no escribe; `--as` obligatorio en producción y de un admin; 120 kg en v0.5 y 110 kg después deja vigente 120;
   - **invariante: tras cualquier corrida el vigente de cada objetivo es el máximo real** (M-6);
   - **trato propio de los fallos** (S9-D42): un socio con «base ocupada» real (candado retenido por otra conexión) se reintenta 3 veces, cuenta en `ocupados`, los demás socios se procesan y el comando sale con 1; un fallo forzado en un socio cuenta en `fallidos`, no deja medio socio escrito (su transacción se revierte entera) y sale con 1; sin fallos sale con 0;
   - tope alcanzado: alerta `athletes_restore_capped` y código de salida 1;
   - auditoría con conteos y sin ids de socio en `details`; no emite `PersonalRecordSet`.
   `tests/core/test_env_example.py` (la CI corre `derive-records`).
3. Verde. `security-reviewer` y `database-reviewer` (lotes de 200, una transacción por socio, `lock_member`).
4. Gate: `slice-gate.sh cli tests/cli/test_derive_records.py tests/core/test_env_example.py` (no sellante; cubre `cli_ops/`); sello `slice-gate.sh athletes tests/cli/test_derive_records.py tests/core/test_env_example.py`.
5. Evidencia: `$DC --profile tools run --rm tools derive-records --dry-run --as <correo del admin de desarrollo>` (conteos al cuaderno; la corrida real es de V2).
6. Checkpoint: `"S9-B6 derive-records idempotente, con reintento ante base ocupada y código de salida"`.
7. Depende de: B5. Agentes: por defecto.

#### S9-C1 · Benchmarks y serie (US-183)
1. Archivos: crear `athletes/reads.py`; modificar `athletes/{rules,schemas,router,service}.py` (rutas 8 y 9), `_imports.py`. `member_marks` la crea B5; si C1 se adelanta a B5, la crea C1 con su prueba y B5 solo la amplía.
2. Rojo: `tests/athletes/test_benchmark_series_pure.py` (por tipo, un intento, empates: un solo `is_best`, `level_changed`); `tests/athletes/test_benchmarks_service.py` (solo vigentes y validados: fuera `pending`, corregidos y anulados; 404 `benchmark_not_found`; sin campos cifrados; tope 200 intentos); `tests/athletes/test_router_benchmarks.py`.
3. Verde. P-API. `security-reviewer` y `database-reviewer`.
4. Gate: sello `slice-gate.sh athletes tests/athletes/test_benchmark_series_pure.py tests/athletes/test_benchmarks_service.py tests/athletes/test_router_benchmarks.py tests/results/test_member_marks.py`.
5. Checkpoint: `"S9-C1 benchmarks del socio y su serie en el tiempo"`.
6. Depende de: B3 (y B5 para `member_marks`). Agentes: por defecto.

#### S9-C2 · RMs vigentes y resumen (US-184)
1. Archivos: `athletes/{reads,rules,schemas,router,service}.py` (rutas 6 y 7).
2. Rojo: `tests/athletes/test_summary_pure.py`; `tests/athletes/test_rms_service.py` (un ítem por movimiento; el SQL `DISTINCT ON` da lo mismo que `pick_current`; invalidados fuera); `tests/athletes/test_summary_service.py` (sin `crypto_ops` ni `reveal`; funciona con el custodio sellado; a lo sumo seis consultas; anuladas fuera del conteo); `tests/athletes/test_router_profile.py`.
3. Verde. P-API. `security-reviewer`.
4. Gate: sello `slice-gate.sh athletes tests/athletes/test_summary_pure.py tests/athletes/test_rms_service.py tests/athletes/test_summary_service.py tests/athletes/test_router_profile.py`.
5. Checkpoint: `"S9-C2 RMs vigentes y resumen del atleta sin descifrar"`.
6. Depende de: B5. Agentes: por defecto.

**Cierre de Wave 3b:** P-GATES (incluye la suite completa de `tests/results`, riesgo 3); P-REBUILD 2, 3 y 4; smoke 8181 (las 11 rutas con rol, `PATCH /movements/{id}` con récord vivo; solo códigos); `drop_caches`.

### Wave D (3 slices): deuda de v0.5 (C7)

#### S9-X1 · WhatsApp ofrecido cuando no se puede abrir (S9-D22, S9-D36 L-5; hallazgo 5; api y web en un checkpoint, en el árbol principal)
1. Archivos:
   - `members/{contact,service}.py`: `whatsapp_ready(session, ids) -> dict[UUID, bool]` (reemplaza al `phone_presence` del blueprint): en SQL, `deleted_at IS NULL`, `NOT CONSENT_MISSING_CONDITION` y `phone IS NOT NULL`. Una consulta por lote; no descifra, no deja `crypto_ops` ni `reveal`, no registra ids.
   - `notifications/{schemas,queries,service}.py`: `NotificationOut.can_whatsapp` = `status != "skipped"` Y `channel == "whatsapp_link"` Y `channels.whatsapp.enabled` (leído UNA vez por página con la misma lectura de `wa_link`) Y `whatsapp_ready[member_id]`.
   - `docs/openapi.json`, `types.ts`, `web/src/features/notifications/components/WaButton.tsx` y la fila de avisos.
2. Rojo:
   - `tests/members/test_whatsapp_ready.py`: con teléfono, autorización y vivo, verdadero; sin teléfono, falso; sin autorización, falso; dado de baja, falso; una consulta; cero filas nuevas en `crypto_ops` y en `audit_log`.
   - `tests/notifications/test_can_whatsapp.py`: **una prueba por cada una de las cinco condiciones reales de `wa_link`**: (1) aviso `skipped` → falso; (2) canal distinto de `whatsapp_link` → falso; (3) `channels.whatsapp.enabled` falso → falso; (4) socio sin autorización o dado de baja → falso; (5) socio sin teléfono → falso; con las cinco cumplidas → verdadero. Además, **coherencia**: para cada caso falso, `POST /notifications/{id}/wa-link` responde el error que corresponde (`notification_closed`, `wrong_channel`, `channel_disabled`, el de `MemberNotContactable`, `member_without_phone`); y con verdadero no responde ninguno de esos cinco. Una sola llamada a `whatsapp_ready` y una sola lectura de la configuración por página. No se prueba ningún «opt-in»: `wa_link` no lo tiene.
   - Vitest de `WaButton` (deshabilitado con el motivo y enlace a la ficha; los 409 y 422 siguen manejados).
   - `test_notifications_details_clean.py` y `test_list_rows_without_sensitive_fields.py` en verde.
3. Verde. P-API. `security-reviewer`. P-REBUILD 2 y 3.
4. Gate: `slice-gate.sh web/notifications src/features/notifications/components/WaButton.test.tsx` y `slice-gate.sh members tests/members/test_whatsapp_ready.py` (no sellantes); sello `slice-gate.sh notifications tests/notifications/test_can_whatsapp.py tests/members/test_whatsapp_ready.py`.
5. Checkpoint: `"S9-X1 can_whatsapp con las cinco condiciones de wa_link, sin descifrar"`.
6. Depende de: nada. Agentes: `backend-qa-executor`, `backend-implementor` y `frontend-ux-engineer` (Sonnet), en serie en la misma carpeta (alias 12).

#### S9-X2 · E2E de la inactividad del quiosco (S9-D23; E6)
1. Archivos: crear `web/tests/e2e/stack/kiosk-idle.spec.ts`. Sin cambios de producto salvo que la prueba destape un fallo (entonces, slice de vuelta con su rojo).
2. Rojo: la spec entra al quiosco de una clase de hoy, instala `page.clock`, avanza `TABLET_IDLE_MS + 1 s` sin tocar la pantalla y comprueba el cierre de sesión y que el api ya no acepta esa sesión; segundo caso: toca al minuto 9 y a los 10 sigue dentro. Se confirma primero que falla por el motivo esperado si se rompe el temporizador (mutación local, no confirmada).
3. Gate: P-E2E con esa spec dos veces seguidas (la spec no se pasa a `slice-gate.sh`, alias 15); sello `slice-gate.sh web/layouts` sin lista, antes del checkpoint.
4. Checkpoint: `"S9-X2 E2E del cierre por inactividad del quiosco"`.
5. Depende de: nada. Agentes: `frontend-qa-automation` (Sonnet).

#### S9-X3 · TV en tiempo real (S9-D24, S9-D38; L-6)
1. Archivos: `web/tests/soak/tv.soak.spec.ts` (modo `SOAK_REAL_HOURS`: sin `page.clock`, muestra del heap por CDP cada 10 minutos, mismo criterio del 20 %, cero errores de consola), `.github/workflows/nightly.yml` (job `tv-soak-real`: solo `workflow_dispatch` con `real_hours` distinto de 0; valor por `env:`, validado como número con tope 5,5; `timeout-minutes: 350`; `permissions: contents: read`; acciones fijadas por SHA; el heap también a `$GITHUB_STEP_SUMMARY`), `scripts/ci/test_nightly_workflow.sh`, `docs/operacion/tv.md`.
2. Rojo: el guion de vigilancia exige el job nuevo, que no está en `schedule`, que no interpola `inputs.` dentro de `run:` y que declara `permissions`; `bash -n`.
3. Verde. Corrida local de 2 minutos reales (`SOAK_REAL_HOURS=0.03`) con el heap al cuaderno. `security-reviewer`.
4. Gate: `bash scripts/ci/test_nightly_workflow.sh`, `bash scripts/ci/test_images_pinned.sh` y `cd web && npm run soak`; sello `slice-gate.sh architecture` sin lista.
5. Checkpoint: `"S9-X3 tv-soak-real: prueba de la TV en tiempo real por workflow_dispatch"`.
6. Depende de: nada. Agentes: `frontend-qa-automation` y DevOps (Sonnet).

**Cierre de Wave D:** P-GATES; P-REBUILD 2 y 3; smoke 8181 (`GET /notifications/today`); `drop_caches`.

### Wave 5a (1 slice) y Wave 5b (2 slices): front

Reglas comunes de F: `DESIGN.md`, `ROUTES.md`, `Atleta_Perfil.html` y `.dark.html`; solo `tokens.css`; componentes en `web/src/shared/ui/`; RHF + Zod; TanStack Query; `// DESIGN-GAP:` donde no se cumple; `features/athletes` no importa de otra feature. Cada F empieza con `git rebase feat/sprint-09-perfil-atleta` y `gen:api` al día. Gate: `slice-gate.sh web/<feature> <archivos>` y, antes del checkpoint, `cd web && npm run lint && npx tsc --noEmit && npx vitest run --maxWorkers=2 && npm run build`. Luego P-REBUILD 3 desde el worktree, el E2E de la ruta y el checkpoint con `checkpoint-commit.sh` DENTRO del worktree (alias 12 y 15). Integración: `git merge --ff-only sprint-09-front` en la rama del sprint, sin un slice de backend a medias. Agentes: `frontend-qa-automation` (Rojo y E2E) y `frontend-ux-engineer` (Verde), Sonnet; `typescript-reviewer` y `security-reviewer`, Fable.

#### S9-F1 · Pestaña, Resumen y Medidas (US-178, US-179, US-184; H-1, L-7)
1. Archivos: `web/src/features/athletes/{api.ts,schemas.ts,athleteErrors.ts,tabs/AthleteTab.tsx,components/{SummaryCards,MetricsTab,MetricPanel,MetricField}.tsx}`; `config/features.ts` (`athletes` en `ENABLED_FEATURES`); `MemberDetailPage.tsx` (`CHILD_TABS` con `atleta`, sin `disabledUntil`); `core/auth/permissions` (`athletes.view`, `athletes.write`, `athletes.reveal`); `shared/ui/Tabs.tsx` (`variant="pills"`, E7), `dev/Catalog.tsx`, `DESIGN.md`; `shared/data/athletes.ts` (`invalidateAthleteViews`; la llama `invalidateResultViews`); `shared/data/score.ts` (`formatWeightKg`); `errorCodes.ts`. DESIGN-GAP: valores en claro en la tabla, gráfica de peso, «Cintura», medidas configurables, «Exportar progreso», «Laura (portal)».
2. Rojo:
   - `AthleteTab.test.tsx`: cinco subpestañas en `?tab=`, por defecto `resumen`; acciones ocultas con el socio dado de baja.
   - `MetricField.test.tsx`: «•••» si `has_*` y «—» si no; «Mostrar» llama al `reveal`; el valor vive 60 s y se oculta al perder visibilidad; no queda en la caché de TanStack (`gcTime: 0`, `reset()`); nada del valor en la URL ni en `aria-label` (L-7); 403 de un coach con socio dado de baja explicado.
   - `MetricPanel.test.tsx`: Zod; kg con un decimal enviados en gramos; 422 bajo su campo; **409 `consent_required` con el mensaje y el enlace a la ficha; botón deshabilitado si la ficha ya dice que falta la autorización** (H-1; si el dato no viene en la ficha, se muestra solo el 409 y se deja `// DESIGN-GAP:`); `reset()` al cerrar.
   - `MetricsTab.test.tsx` (paginación en el servidor, «Anular» con `ConfirmModal`, vacío), `SummaryCards.test.tsx`, `Tabs.test.tsx` (píldoras, teclado y a11y), `features.test.ts`, `permissions.test.ts`, `routeAccess.test.ts`, `nav.test.ts`, `routes.test.ts`, `MemberDetailPage.test.tsx`.
   - E2E `web/tests/e2e/stack/athlete-profile.spec.ts`: abre la ficha y la pestaña Atleta, registra una medición, revela el peso y lo ve; `?tab=medidas` se conserva al recargar; ninguna petición a `/reveal` al abrir.
3. Gate: `slice-gate.sh web/shared src/shared/ui/Tabs.test.tsx`, `slice-gate.sh web/members src/features/members/pages/MemberDetailPage.test.tsx` y `slice-gate.sh web/app` sin lista (no sellantes; `src/config` es del módulo `web/app`); sello `slice-gate.sh web/athletes src/features/athletes/tabs/AthleteTab.test.tsx src/features/athletes/components/MetricField.test.tsx src/features/athletes/components/MetricPanel.test.tsx src/features/athletes/components/MetricsTab.test.tsx src/features/athletes/components/SummaryCards.test.tsx`; E2E con P-E2E.
4. Checkpoint: `"S9-F1 pestaña Atleta con Resumen y Medidas, reveal de 60 s y E2E de la ruta"`.
5. Depende de: A3 y C2.

**Cierre de Wave 5a:** P-GATES; P-REBUILD 3; preview en 8180 (claro y oscuro); `drop_caches`.

#### S9-F2 · RMs y Récords (US-180, US-181, US-182; L-4)
1. Archivos: `features/athletes/components/{RmsTab,RecordsTab,RecordPanel}.tsx`; `shared/data/catalog.ts` (opciones de movimientos y benchmarks, E8; `features/wods` las importa de ahí); `shared/data/score.ts` (`formatScoreDelta`). DESIGN-GAP: 3RM, 5RM, «máx. reps», unidad preferida y «editar».
2. Rojo: `RmsTab.test.tsx` (un movimiento por fila; origen con texto: «Manual», «Automático del WOD», «Automático (tablet)»); `RecordsTab.test.tsx` (chips «RMs», «Benchmarks», «Ver invalidados»; «Vigente» con texto; un derivado enlaza a su WOD y explica que se corrige desde el resultado; «Invalidar» solo en un manual vivo, con `ConfirmModal`; 403 explicado); `RecordPanel.test.tsx` (`Segmented` RM o Benchmark; campos del `score_type`; 422 bajo su campo); `catalog.test.ts`; `score.test.ts`; las pruebas de `features/wods` en verde. E2E `athlete-records.spec.ts`: valida un resultado de 100 kg y ve el RM automático; lo corrige y lo ve invalidado.
3. Gate: `slice-gate.sh web/shared src/shared/data/catalog.test.ts src/shared/data/score.test.ts` y `slice-gate.sh web/wods` sin lista (no sellantes); sello `slice-gate.sh web/athletes src/features/athletes/components/RmsTab.test.tsx src/features/athletes/components/RecordsTab.test.tsx src/features/athletes/components/RecordPanel.test.tsx`; E2E con P-E2E.
4. Checkpoint: `"S9-F2 RMs y Récords con origen a la vista, invalidar y E2E de carga y corrección"`.
5. Depende de: B5, C2 y F1.

#### S9-F3 · Benchmarks (US-183)
1. Archivos: `features/athletes/components/BenchmarksTab.tsx`; `shared/ui/TrendChart.tsx` (SVG con tokens, `role="img"` con `aria-label`, la tabla como equivalente accesible), `shared/ui/index.ts`, `dev/Catalog.tsx`, `DESIGN.md`. DESIGN-GAP: columna «Escaló» y «solo se compara entre el mismo nivel».
2. Rojo: `BenchmarksTab.test.tsx` (chips con `?benchmark=`; tabla con Fecha, Marca, Nivel y Diferencia; «Mejor» con texto; «cambió de nivel»; vacío); `TrendChart.test.tsx` (a11y; un punto; sin datos). E2E mínimo dentro de `athlete-profile.spec.ts` (`?tab=benchmarks` muestra «Fran» y su serie).
3. Gate: `slice-gate.sh web/shared src/shared/ui/TrendChart.test.tsx` (no sellante); sello `slice-gate.sh web/athletes src/features/athletes/components/BenchmarksTab.test.tsx`; E2E con P-E2E.
4. Checkpoint: `"S9-F3 Benchmarks con la serie del socio y TrendChart"`.
5. Depende de: C1 y F1.

**Cierre de Wave 5b:** P-GATES; P-REBUILD 3 y 4; capturas de las cinco subpestañas en 768, 1024 y 1440, claro y oscuro; `drop_caches`.

## 3. Validación (wave V, 9 pasos)

1. **V1 · Gates completos.** P-GATES sobre el último commit (alias 14); Alembic `0001 → 0043` arriba y abajo contra `db_test`; `export-openapi` y `gen:api` sin diff; licencias (sin dependencias nuevas); `pre-commit run --all-files`; `pip-audit`; `npm audit --omit=dev`; gitleaks. Cobertura del api de 80 % o más y del front sin bajar de la línea base de W0-2. Agente: QA (Sonnet).
2. **V2 · Datos de `apex-db-1`.** Agente: DevOps (Sonnet).
   - Volcado; `$DC exec api alembic current` = `0043_athletes_personal_records (head)`; `\d` de las dos tablas; guardas con `tgenabled = 'A'`; fila `encrypt` activa de `athlete.metric`.
   - **`dbsetup` (verificado en `compose.yml:69-94` y `compose.dev.yml:21-22`).** En desarrollo el servicio solo existe con el perfil `prod-init` y sin `--no-deps` arrancaría `migrate`. Antes: comprobar por NOMBRE, sin imprimir valores, que `.env` trae las tres contraseñas que valida `apply.sh` (`grep -c '^APEX_API_DB_PASSWORD=\|^APEX_WORKER_DB_PASSWORD=\|^APEX_BACKUP_DB_PASSWORD=' .env` debe dar 3; si no, se copian de `.env.ops` a `.env` como en S8 y se anota). Comando, una sola vez: `$DC --profile prod-init run --rm --no-deps dbsetup`. Debe terminar con código 0 y las 32 tablas clasificadas; una tabla sin clasificar lo hace fallar cerrado (es la prueba de P-ROL sobre la base real). Es una escritura permitida por la parada 1 (roles y grants; no toca datos). El api de desarrollo sigue corriendo como propietario.
   - Después, comprobar con `$PSQL` (solo lectura) `has_table_privilege('apex_api', 'athletes.body_metrics', 'DELETE')` = falso y `has_schema_privilege('apex_worker', 'athletes', 'USAGE')` = falso.
   - `derive-records --dry-run` y luego real, dos veces (la segunda crea 0 y sale con 0), con los conteos al cuaderno.
3. **V3 · `prod-smoke` en Linux, dos variantes y rollback** (alias 6).
   - `SMOKE_DOWN=1 SMOKE_WEB_PORT=8380 bash scripts/ci/prod-smoke.sh --no-build` y después con `--provider openbao`. Comprueban: `apex_api` inserta medidas y récords, solo actualiza las columnas permitidas y no borra; `apex_worker` sin acceso a `athletes`; la DEK de `athlete.metric` existe tras el primer arranque (sin `init-keys`); alta y `reveal` de una medida con OpenBao; `rotate-key athlete.metric` con una medición anulada; alta sin autorización 409. Las comprobaciones nuevas entran a `prod-smoke.sh` en un slice de vuelta con `bash -n`.
   - **Rollback a v0.5.0 con la llave nueva ya creada (hallazgo 8).** `core/crypto/keyring.py:156` carga TODAS las filas de `crypto_keys`: no está probado que la imagen v0.5.0 arranque con una fila de una clase que su registro no conoce. Paso explícito, en el auxiliar y solo sobre `apex-smoke`:
     1. tercera corrida de la variante local dejando el stack arriba (`SMOKE_DOWN=0`), con una medición creada;
     2. `alembic downgrade 0041_results_session_index` con la imagen v0.6.0;
     3. construir la imagen del api desde la etiqueta `v0.5.0` con OTRA etiqueta (`apex-api:v050`, para no pisar `apex-api:local`) y arrancar `api` y `worker` con ella;
     4. `/health` debe dar 200 con `crypto: ok` y `migrations: ok`, un login y una lectura con descifrado (`reveal` de un campo de la ficha) deben funcionar;
     5. `docker compose -p apex-smoke down -v` y `docker image rm apex-api:v050`.
   - Resultado al cuaderno y a §6.2 y `docs/operacion/actualizar.md`: si arranca, el rollback por `downgrade` queda documentado como probado. Si NO arranca, el rollback de producción documentado pasa a ser únicamente «restaurar el respaldo pre-deploy» (no se borra una llave ni se toca v0.5).
   - Si `prod-smoke.sh` no admite dejar el stack arriba, o el paso no se puede completar, §6.2 y la guía lo declaran **«no probado»** con esas palabras y recomiendan el respaldo pre-deploy; no se afirma lo que no se midió.
   - Tras cada corrida: P-REBUILD 4 y 3 y health en 8181 con el SHA.
4. **V4 · Demos 1 a 4 de `SPRINT-09.md`**, por la interfaz de 8180 con conteos en `$PSQL`:
   - (1) Medición con blobs en las cuatro columnas; «Mostrar» el peso deja una fila `reveal` y una `decrypt`.
   - (2) 100 kg crea el RM; un `scaled` no; corregir lo invalida sin borrarlo (con su fila `update` en la auditoría); anular también.
   - (3) Mejor tiempo en Fran y la serie.
   - (4) Ficha con cinco subpestañas, sin filas `reveal` ni `crypto_ops` al abrir.
   Contraseñas con `read -rs`; ningún valor revelado al cuaderno (lección de S8-D51 (6)).
5. **V5 · E2E, preview y evidencia en GitHub.** P-E2E del proyecto `stack` completo **dos veces seguidas** (con `athlete-profile`, `athlete-records` y `kiosk-idle`); `npm run e2e` (preview) con capturas. Con S9-D41 cumplida: push de la rama por el orquestador y disparo de `nightly.yml` con `real_hours=5` por REST (S9-D38); el seguimiento queda en Monitor mientras siguen V6 a V8. Sin S9-D41: respaldo de S9-D38.
6. **V6 · Rendimiento (`perf`, no gate), con datos mezclados.** En `db_test` con 30 WODs, unos 3.300 resultados, 500 récords y 200 mediciones:
   - 15 `PUT /results` seguidos con el handler activo: la mediana no sube más de 20 ms frente a la de S8.
   - Una corrección de un socio con 2.000 marcas: bajo el `statement_timeout`, con el tiempo al cuaderno (H-2).
   - `EXPLAIN (ANALYZE, BUFFERS)` de `/rms`, `/records`, `member_marks`, `wod_ids_with_primary`, el puerto `RecordsProbe`, la lectura ORM de `_invalidate` (por `uq_personal_records_result_kind`) y la lectura por `invalidated_by_result_id`: todos por índice, sin `Seq Scan` y sin apagar el planificador (S8-D50).
   - `/summary` bajo 300 ms.
   Si una lectura no usa su índice: slice de vuelta (y migración NUEVA si hace falta un índice; `0043` ya está aplicada).
7. **V7 · Revisión de Fase 4, deuda cero.** En paralelo, Fable y solo lectura: `security-reviewer` (puerta, listas, logs, largo del blob, marca de campo, guardas, autorización, cupo y alerta de `reveal`, bajas, fallo blando y sus alertas sin ids), `code-reviewer`, `python-reviewer`, `typescript-reviewer` y `database-reviewer` (grants, índices, candados, guardas, savepoints). Todo CRITICAL, HIGH y MEDIUM se corrige con su slice de vuelta a gate (Sonnet, con rojo); los LOW se corrigen o se aceptan con decisión numerada.
8. **V8 · `verify-delivery` en vivo.**
   - Pilar 1: US-178 a US-184, demos 1 a 4, C1 a C7, H-1, H-2, M-1 a M-6, L-1 a L-8, P1 a P11, los diez hallazgos de la crítica 1 y S9-D21 a D25, cada uno con su evidencia y el N/M real. Desviaciones dichas tal cual.
   - Pilar 2, por la interfaz real del stack de desarrollo: artefactos actuales (`docker image inspect` con el SHA del árbol en api, worker y web); medición y «Mostrar» con los conteos de `audit_log` y `crypto_ops`; alta sin autorización rechazada; una clase de carga en la tablet con RM automático, una corrección y una anulación (dos veces la corrección, para probar idempotencia) y sus filas `update` de auditoría; `derive-records` otra vez (crea 0); `verify-audit` en verde al final; la espera REAL de 10 minutos del quiosco (vigilada con Monitor, con la captura final y el estado de la fila de `auth.refresh_tokens`); un aviso de WhatsApp de un socio sin teléfono y otro de un socio sin autorización, los dos con el botón deshabilitado; los resultados de los dos jobs de GitHub de V5 (o la justificación de S9-D38).
   - Si algo no se pudo probar en vivo, se dice; «las pruebas pasan» no lo reemplaza.
9. **V9 · Release `0.6.0`, push y limpieza.** Versión en `api/pyproject.toml`, `api/uv.lock` (`uv lock`), `web/package.json` y `web/package-lock.json` (`npm version 0.6.0 --no-git-tag-version`), `docs/openapi.json` y `CHANGELOG.md` (`## [0.6.0]`, con las tres deudas de v0.5 y cómo se cerró cada una, y el resultado del rollback de V3); `bash scripts/ci/check-release-version.sh --check v0.6.0`; `CLAUDE.md` con los conteos finales; `DECISIONES.md` (cierre, conteos, desviaciones); commit `chore(release): cierre del Sprint 9, v0.6.0`; `git tag -a v0.6.0 -m "v0.6.0: perfil del atleta"`; buildx de las dos imágenes con el `GIT_SHA` etiquetado y `$DC up -d --no-build --force-recreate api worker web` (health con `version 0.6.0`). Push, por el orquestador y solo con S9-D41 cumplida: `git push -u origin feat/sprint-09-perfil-atleta`, `git checkout main && git merge --ff-only feat/sprint-09-perfil-atleta && git push origin main`, `git push origin v0.6.0`; sin ella o si lo bloquean, parada 6. Limpieza: volcados, `$TMPDIR/apex-token` y `apex-gh.curlrc`, banderas, worktrees `sprint-09-front` y `gates`, auxiliares parados, procesos de fondo cerrados, `drop_caches`. Agente: Haiku lo mecánico.

## 4. Despliegue de v0.6.0 en un servidor (para `docs/operacion/actualizar.md`, B6)

1. Respaldo previo y copia de la KEK como siempre (`deploy.sh` lo exige).
2. `bash infra/deploy.sh --ref v0.6.0 --expect-sha <sha> --kek-file <copia> --i-know-unsigned-ref`: `migrate` aplica `0042` y `0043`, `dbsetup` clasifica las 32 tablas y recién entonces arrancan api, worker y web.
3. El primer arranque del api crea la DEK de `athlete.metric` (no hay paso `init-keys`). Comprobar `/health` con `migrations: ok` y `crypto: ok`, y la llave en la pantalla Llaves. Con el custodio sellado el alta responde 503 hasta que se recupere.
4. Variable nueva opcional en `.env`: `USER_ATHLETES_WRITE_LIMIT_PER_MIN` (por omisión 30).
5. `docker compose --profile tools run --rm tools derive-records --as <correo de un admin>` (una vez; repetirlo no duplica). Si sale con código 1, su resumen dice cuántos socios quedaron `ocupados` o `fallidos`: se repite.
6. Registrar la autorización de datos de los socios importados sin ella antes de tomarles medidas.

## 5. Riesgos y mitigación

1. [ALTA] Un valor de medida fuera de su puerta (lista, log, auditoría, 422, largo del blob, otra columna). Mitigación: S9-D4, D15, D16, D32 y D36; pruebas de arquitectura de A1; `security-reviewer` en cada slice de A y en V7.
2. [ALTA] El handler tumba la tablet en plena clase, por un fallo propio o por una alerta mal armada. Mitigación: S9-D30 y S9-D42 (savepoint, claves de alerta en W0-3, `alert` en su propio `try`), las pruebas de B3 y B5, V6 con 2.000 marcas y V8 con una clase real.
3. [ALTA] Tocar `results`, cerrado en v0.5. Mitigación: cambio aditivo, un solo `emit` y dos lecturas nuevas; `test_correct_service.py`, `test_correct_concurrency.py` y `test_record_service.py` en los gates de B3 y B5; suite de `results` en el cierre de wave.
4. [ALTA] La guarda de `body_metrics` bloquea una rotación legítima, un alta durante la rotación o a la propia fábrica de pruebas. Mitigación: una prueba por regla, rotación con una medición anulada (A1 y V3), llave `active` o `decrypt_only` en el INSERT y fábrica en dos pasos (hallazgo 6).
5. [ALTA] Una invalidación sin rastro o un fallo blando que rompe la cadena de auditoría. Mitigación: `_invalidate` por ORM, `test_invalidation_audit.py` y la verificación de la cadena tras el fallo blando (B3, B5 y V8).
6. [MEDIA] Datos de salud sin autorización, o de socios dados de baja. Mitigación: S9-D29 y D34; la guía declara qué se conserva.
7. [MEDIA] Vigente incorrecto tras corregir, o un fallo blando que nadie repara. Mitigación: la prueba del hueco, la alerta, `derive-records` con su invariante y su código de salida (M-6).
8. [MEDIA] Grant faltante invisible en desarrollo. Mitigación: P-ROL en el slice de cada tabla, `dbsetup` en V2 y `prod-smoke` en V3.
9. [MEDIA] Rollback a v0.5.0 que no arranca por la fila de llave nueva. Mitigación: el paso de V3; si no se prueba, se declara «no probado» y el camino documentado es el respaldo pre-deploy.
10. [MEDIA] Conteos fijos que cambian (clases cifradas, claves de alerta, cubetas). Mitigación: P-CAT 2, 6 y 7.
11. [MEDIA] Una migración a medio escribir aplicada por el api que recarga. Mitigación: paso 0, banderas y P-MIG 5 después del gate.
12. [MEDIA] Dos agentes en la misma carpeta y `git add -A`; un sello invalidado por un cambio tardío. Mitigación: alias 12 y 15.
13. [MEDIA] El harness mata un gate largo por memoria. Mitigación: alias 14; un `pytest` a la vez; vitest con 2 hilos; `drop_caches`.
14. [MEDIA] `prod-smoke` pisa las imágenes locales o falla por CRLF. Mitigación: `git clone` dentro del auxiliar y reconstrucción después (alias 6).
15. [MEDIA] La evidencia de GitHub no se puede disparar (sin `gh`, credencial, autorización de push o minutos: la corrida de 5 h consume unos 300 minutos de Actions). Mitigación: S9-D38 y D41, con su orden de respaldo y la justificación escrita.
16. [MEDIA] Abuso interno: lectura masiva de medidas o anulación en masa. Mitigación: S9-D33 y D35.
17. [BAJA] El reloj falso del E2E del quiosco contra un plazo del servidor. Mitigación: E6 y la espera real de V8.
18. [BAJA] Push sin autorización verificable, o rechazado. Mitigación: S9-D41 y parada 6.
19. [BAJA] Mover los hooks de catálogo rompe `features/wods`. Mitigación: sus pruebas en el gate de F2.

## 6. Rollback

1. **Por migración, en desarrollo y antes de V9:** `$DC exec api alembic downgrade 0042_athletes_body_metrics` (borra `personal_records`) y luego `downgrade 0041_results_session_index` (borra `body_metrics` y el esquema). Con mediciones o récords reales se para y se pregunta, o se restaura `sprint-09-antes-0042.dump`. Cada `downgrade` está probado en su `test_00NN`.
2. **En producción (v0.6.0 → v0.5.0):** `deploy.sh` deja `rollback-<fecha>.txt` si falla `/health`. Camino seguro, siempre válido: volcado inmediato y restaurar el respaldo pre-deploy (decisión irreversible si ya hay medidas reales: se para y se pregunta). Camino alterno, sin medidas reales: `alembic downgrade 0041_results_session_index` con la imagen v0.6.0 y `deploy.sh --ref v0.5.0 --expect-sha <sha>`. **Probado en V3 (2026-11-18, `apex-smoke`, `ac9d7f4`):** con la imagen v0.6 el `downgrade` bajó `0044 → 0043 → 0042 → 0041` con salida 0; las filas de `athlete.metric` siguen en `crypto_keys` (3 tras la rotación del smoke; una llave nunca se borra) y, con el árbol y la imagen de v0.5.0 (`apex-api:v050`), `api` y `worker` quedaron `healthy`, `/health` 200 con `crypto ok` y `migrations ok`, login del admin y `reveal` de `document` con 200, sin `Traceback` en el log. Compose y `dbsetup` deben correr desde el árbol de v0.5.0 (su `grants.sql`): con el de v0.6 `dbsetup` fallaría cerrado al dar permisos sobre tablas de `athletes` ya borradas. `deploy.sh --ref v0.5.0` ya trabaja sobre ese árbol.
3. **Apagar solo el front:** `athletes` sale de `ENABLED_FEATURES` y se reconstruye `web`.
4. **Handler problemático sin rollback:** el fallo blando ya confirma el resultado; `derive-records` repara después.
5. **Imágenes:** `apex-api:local` y `apex-web:local` desde la etiqueta `v0.5.0` con buildx y su `GIT_SHA`.

## 7. Conteo

1. Wave 0: 3 slices (W0-1 a W0-3). Wave 3a: 3 (A1 a A3). Wave 3b: 8 (B1 a B6, C1, C2). Wave D: 3 (X1 a X3). Wave 5a: 1 (F1). Wave 5b: 2 (F2, F3). Wave V: 9 pasos. Total: 29 slices en 6 waves de construcción más la wave V.
2. Decisiones: S9-D1 a S9-D42 (28 del blueprint, 7 de seguridad, 5 de la primera versión de este plan y 2 de la crítica 1).
3. Migraciones: 2. Rutas nuevas del api: 11. Cambios de contrato existentes: `can_whatsapp` y el 422 `locked_by_records`. Eventos nuevos: `WodResultSuperseded` y `PersonalRecordSet`. Puerto: `RecordsProbe`. Aristas: 4. Cubetas: 28 (27 variables `USER_*`). Claves de alerta nuevas: 2 (`revelados`, `marcas`). Tablas clasificadas: 32. Comando de CLI: `derive-records`. Rutas de quiosco: 12, sin cambio. Rutas públicas: 8, sin cambio.
4. Funciones nuevas en módulos ajenos: `wods` (`record_meta_for`, `wod_ids_with_primary`, `movement_refs`, `benchmark_refs` y las envolturas `movement_for_record` y `benchmark_for_record`), `results` (`get_mark`, `member_marks`, `score_key`), `members` (`consent_missing_for`, `whatsapp_ready`).

## 8. Mapa: dónde quedó cada decisión, hallazgo y condición

### Condiciones del impacto
1. C1 (numeración, gramos, rutas, E2E en `stack/`): S9-D2, D8 y D27 → W0-1.
2. C2 (eventos y `get_mark`, con pruebas en `results`): S9-D6 y D7 → B3 y B5.
3. C3 (sin `init-keys`; clase y prueba de arranque): S9-D5 → W0-3 y A1; guías en B6; V3.
4. C4 (tercera puerta, importadores, texto en reposo y auditadas con `0042`): S9-D15, D16 y D19 → A1.
5. C5 (grants, guardas y limpieza con cada migración; aristas, `MODULES` y privados): S9-D18, D20 y D31 → A1 y B1; aristas en A1, B1 y B3.
6. C6 (cubetas por escrito antes de las rutas): S9-D15 y D17 → W0-2 y W0-3.
7. C7 (tres deudas y resultados de v0.5): S9-D21 → B6 y V2; S9-D22 → X1; S9-D23 → X2 y V8; S9-D24 y D38 → X3 y V5.

### Revisión de seguridad
1. H-1 → S9-D29: A1 (service, 409, cero `encrypt`), F1 (botón y mensaje), V3 y V8.
2. H-2 → S9-D30 y D42: W0-3 (claves de alerta), B3 (savepoint, fallo blando, base ocupada, tope de sentencias), B5 (cerrado al invalidar, reposición acotada, tope 200), B6 (trato propio), V6 (2.000 marcas).
3. M-1 → S9-D31: A1 (`0042` y grants por columna), B1 (`0043`), V3.
4. M-2 → S9-D32: A1.
5. M-3 → S9-D33: A3 y B5.
6. M-4 → S9-D34: A2 y F1; guía en B6.
7. M-5 → S9-D35 y D42: W0-3 y A2; guía en B6.
8. M-6 → S9-D36 y D42: B5 (tope) y B6 (invariante, salida 1, sin ids).
9. L-1 → A1. L-2 → A1 y A2. L-3 → A3 y B5. L-4 → B3 y F2. L-5 → X1. L-6 → X3. L-7 → F1. L-8 → A2. Todos corregidos; ninguno aceptado.

### Preguntas
1. P1 a P11: S9-D37. Slices: P1 → A3 y B5; P2 → B5; P3 → A1 y B1; P4 → W0-1 (BRECHAS); P5 → W0-3 y A2; P6 → A2; P7 → X3 y V5; P8 → B6; P9 → A1; P10 → B3 y B5; P11 → A2 y la guía.
2. E1 a E8: S9-D40. Slices: E1 → A1; E2 y E3 → resueltas; E4 → B1; E5 → A1 y F1; E6 → X2; E7 → F1; E8 → F2.

### Decisiones del blueprint
1. S9-D1, D2, D25, D27, D28 → W0-1. S9-D3, D4, D5, D16, D18 (medidas), D19 → A1. S9-D15 → W0-3, A1 y A2. S9-D13 → A3 y B5. S9-D14 → A1, A2, A3 y B1. S9-D17 → W0-2 y A1. S9-D6 → B1, B3, B5 y C1. S9-D7 → B3 y B5. S9-D8, D12, D18 (récords) → B1. S9-D9 → B2. S9-D10 → B3, B4 y B5. S9-D11 → B5. S9-D20 → A1, B1 y B3. S9-D21 → B6. S9-D22 → X1. S9-D23 → X2 y V8. S9-D24 → X3 y V5. S9-D26 → F1 a F3.

### Historias y demos
1. US-178 → A1, A3, F1. US-179 → A2, F1. US-180 → B1, B2, B5, F2. US-181 → B3, B5, B6, F2. US-182 → B4, F2. US-183 → C1, F3. US-184 → C2, F1.
2. Demo 1 → F1, V4 y V8. Demo 2 → F2, V4 y V8. Demo 3 → F3 y V4. Demo 4 → F1 y V4.
3. Definición de hecho: E2E de medida y `reveal` (F1), de RM y corrección (F2); seguridad (cada slice y V7); `verify-delivery` (V8).

### Lecciones de S8-D43 a D51
1. `run-gates` en worktree limpio con `uv sync --extra s3` y `npm ci` → P-GATES. `checkpoint-commit.sh` y `git add -A` → alias 12. `prod-smoke` con `git clone` y `MSYS_NO_PATHCONV=1` → alias 6 y 7. `/health` con `GIT_SHA` → alias 13. `.is_(True)` prohibido → S9-D39 y V6. Gate muerto por memoria → alias 14. Sin `gh` → S9-D38. Rojo medido siempre → doctrina. Migración aplicada no se edita → parada 4. Secretos en salidas → alias 8 y V4.

### Lo que no se resuelve en v0.6 (con dueño)
1. `members.hide_on_tv`, validar resultados `pending`, gráfica de peso con descifrado por lote, portal del socio: EP-25.
2. «PR» y «vs. su anterior» en WOD, tablet y TV; 3RM, 5RM, «máx. reps», unidad en libras: backlog sin historia (`DESIGN-GAP` en `BRECHAS.md`).
3. Supresión de medidas a pedido del titular: exige cambiar ADR-002; queda como pregunta abierta para el titular (P11).
4. Las 5 h reales de la TV, solo si S9-D38 no logra automatizarlas: comprobación de operación, dicha en el CHANGELOG.
5. El rollback por `downgrade` a v0.5.0, solo si V3 no logra probarlo: declarado «no probado» en §6.2 y en la guía.

## 9. Cambios tras la crítica 1 (`sprint-09-critica-1.md`): mapa hallazgo → sección

Cada corrección se contrastó con el código de `cd0cc0b` (`core/alerts.py:23-47` y `:82-97`, `core/db.py:182-258`, `wods/benchmarks.py:89-102`, `notifications/service.py:184-196`, `members/contact.py:104-110`).

1. **Hallazgo 1 (crítico, `alert()` rechaza las claves).** S9-D42 (claves y `try` propio) y S9-D35 (alerta de volumen sin id de usuario). Pasos: W0-3 (`core/alerts.py`, `tests/core/test_alerts.py`, `tests/core/test_reveal_volume.py`), P-CAT 7, B3 (`test_derive_soft_fail.py`: una alerta que falla no revierte el resultado), B5 (`athletes_restore_capped` con `marcas`), B6. Riesgo 2.
2. **Hallazgo 2 (crítico, `DatabaseBusy` no se lanza dentro de un service).** S9-D42 («base ocupada» con `translate_busy` y relanzar el original; trato propio de `derive-records`). Pasos: B3 y B5 (Rojo con un `lock_timeout` real dentro del savepoint que espera 503), B6 (reintentos, `ocupados`, `fallidos`, código de salida). §4, punto 5.
3. **Hallazgo 3 (alto, patrón del savepoint).** S9-D42 (orden: `flush` fuera, `begin_nested` con `add`, `flush` y emisión dentro, `except` fuera). Pasos: B3 (sesión usable, auditoría del resultado persiste, cadena verificada), B4 (rama de benchmark), B5 (`_invalidate` y su `flush` antes del savepoint), V8 (`verify-audit` al final). Riesgo 5.
4. **Hallazgo 4 (alto, invalidación sin auditoría).** S9-D42 y S9-D1 (c): `_invalidate` por ORM. Pasos: B5 (`test_invalidation_audit.py`: fila `update` con el actor, por corrección y por anulación; `test_invalidate_manual.py`), V4 (demo 2), V6 (`EXPLAIN` de la lectura ORM), V8.
5. **Hallazgo 5 (medio, condición inexistente en `wa_link`).** S9-D36 (L-5) y S9-D1 (i). Paso: X1 (`whatsapp_ready` y una prueba por cada una de las cinco condiciones reales, con su coherencia contra `wa-link`); V8.
6. **Hallazgo 6 (medio, fábrica contra la guarda).** A1, punto 2 («Fábrica»): INSERT por ORM y luego `UPDATE` por SQL, con una fila real de llave `athlete.metric`; `test_factory_metrics.py`; P-CAT 4 (limpieza antes de las llaves). B1 hace lo mismo con el récord invalidado. Riesgo 4.
7. **Hallazgo 7 (medio, `tests/core/crypto/` no existe).** `test_boot_data_classes.py` va en `api/tests/crypto/`: W0-3 (archivos, Rojo y gate con el módulo `crypto`), A1 (gate) y alias 15.
8. **Hallazgo 8 (medio, comprobación prometida y ausente en V3).** V3 («Rollback a v0.5.0 con la llave nueva ya creada», cinco pasos sobre `apex-smoke`, o declaración «no probado»), §6.2 reescrito, parada 2, riesgo 9, V9 (CHANGELOG) y §8 «Lo que no se resuelve», punto 5.
9. **Hallazgo 9 (bajo, credencial y push).** S9-D38 (`GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never`, sin credencial se pasa al respaldo), S9-D41 (push por el orquestador con la autorización del usuario del 2026-11-15, condicionada a que conste), W0-1 (`DECISIONES.md` y la frase de «Calidad y Git» de `CLAUDE.md`), parada 6, V5, V9 y riesgo 18.
10. **Hallazgo 10 (bajo, orden de P-MIG en el ciclo).** Ciclo de slice, pasos 4 y 7 (P-MIG 1 a 4 antes del gate; 5 a 7 después), cabecera de P-MIG, y los pasos «Tras el gate» de A1 y B1.

### Los tres puntos que el crítico no revisó (verificados)
1. **Argumentos de `slice-gate.sh`.** Verificado en el guion: con lista solo acepta archivos existentes bajo `api/tests/` o bajo `web/`; agrega `tests/architecture` solo; ruff y mypy corren únicamente sobre el módulo nombrado. Correcciones: alias 15 nuevo; se quitaron las carpetas y los `tests/architecture/...` de las listas; cada slice que toca otros módulos lleva sus gates no sellantes (W0-2, W0-3, A1, A2, B1, B2, B3, B5, B6, X1, F1, F2); B6 usa el módulo `cli` para `cli_ops/`; `src/config` del front va por `web/app`; las specs de Playwright no se pasan al gate (X2).
2. **`dbsetup` de V2.** Verificado en `compose.yml:69-94` y `compose.dev.yml:21-22`: el comando `$DC --profile prod-init run --rm --no-deps dbsetup` es el correcto en desarrollo. Corrección: V2 comprueba antes, por nombre y sin imprimir, las tres `APEX_*_DB_PASSWORD` que valida `apply.sh`, y después confirma dos privilegios con `has_table_privilege` y `has_schema_privilege`.
3. **Nombres de función.** Verificado en `wods/catalog.py`, `results/reads.py`, `results/leaderboard.py` y `results/service.py`. Corrección: S9-D1 (l) separa lo que existe (`movements_by_id`, `benchmark_for_share`, `scoring_for`, `titles_for`, `member_results` exportada como `list_member_results`, `_tie_key_of`, `leaderboard_order`) de lo NUEVO (`record_meta_for`, `wod_ids_with_primary`, `movement_refs`, `benchmark_refs`, `get_mark`, `member_marks`, `score_key`), y B1, B3 y B5 lo dicen en sus archivos, con una prueba por función nueva; §7, punto 4.

## 10. Enmiendas de la crítica 2 (APROBADO CON OBSERVACIONES, `sprint-09-critica-2.md`)

Mandan sobre las secciones citadas.

1. **W0-3 (obs. 1):** además de `core/alerts.py` y `tests/core/test_alerts.py`, W0-3 toca `core/alerts_telegram.py`: tres entradas en `_DINAMICOS` para `reveal_volume`, `athletes_derive_skipped` y `athletes_restore_capped` que muestran `revelados`, `marcas` y `error_type`, con su prueba de `render_message` en `tests/core/test_alerts_telegram.py` (Rojo: hoy el mensaje sale sin contexto).
2. **V3 y §6.2 (obs. 2):** el rollback se prueba en el auxiliar de prod-smoke: `$DC run --rm migrate alembic downgrade 0041_results_session_index` (el propietario tiene DDL; el api corre como `apex_api`), luego un `compose.override.v050.yml` escrito dentro del auxiliar (nunca en el repo) con `image: apex-api:v050` para `api`, `worker`, `migrate` y `tools` (la imagen se construye con `git worktree add` de `v0.5.0` o `docker buildx build` sobre `git archive v0.5.0`), `up -d`, `/health` con `crypto: ok` y `migrations: ok`. `docs/operacion/actualizar.md` describe el mismo procedimiento.
3. **X1 (obs. 3):** `can_whatsapp` se excluye del armado por `getattr` en `notifications/queries.py:54` (como `member_name`); `service.py` calcula el valor con `_whatsapp_config` y `members.service.whatsapp_ready` por lote y lo pasa a `queries` como argumento (sin importar `service` desde `queries`). Rojo: `get`, `list`, `today_list`, `list_for_member` y `skip` traen `can_whatsapp` correcto, y una sola consulta de `whatsapp_ready` por página.
4. **B3 (obs. 4):** la prueba de base ocupada suscribe en la prueba un handler a `WodResultRecorded` (se emite antes que `Validated`, `results/record.py:203-205`) que, desde OTRA conexión, inserta sin confirmar una fila de `athletes.personal_records` con el mismo `(result_id, kind)` y cumpliendo la guarda de INSERT; el handler real choca con `lock_timeout` y `PUT /results` responde 503 `busy`.
5. **S9-D41 (obs. 5):** confirmado por el orquestador: el usuario ordenó el 2026-11-15 «cuando esté listo sube todo y procede» y que `/flow-update` haga todo sin pasos humanos; el orquestador hace el push de rama, `main` y etiqueta en V9. El push de la rama en V5 (para disparar `tv-soak`) lo hace también el orquestador.

Estado final: **aprobado para ejecución** (crítica 2: APROBADO CON OBSERVACIONES, las cinco aplicadas aquí).
