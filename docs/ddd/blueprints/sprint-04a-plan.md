# Enmiendas de plan-critic (crítica 1, veredicto APROBADO CON OBSERVACIONES)

Estas enmiendas MANDAN sobre cualquier paso del plan y sobre las decisiones S4A-D1 a S4A-D74 donde las contradigan. Cada una se aplica en el slice indicado, antes del gate que sella; ninguna cambia el alcance ni el orden de slices. Detalle y evidencia en `docs/ddd/blueprints/sprint-04a-critica-1.md`.

- **E1 (W0-1.6, B1.1, DECISIONES):** el job marcador tiene una sola forma, la de S4A-D64 (`details={"placeholder_ok": 1}`, claves enteras de `DETAIL_KEYS`); se borra la forma de la "contradicción 12". `--run-once expirations` nace verde en B1; el Rojo real de B1 es `core/jobs`, `runner` y `schedule` (anotarlo en el cuaderno).
- **E2 (B2.3):** prueba que exige `set(asdict(RecomputeSummary(...))) <= DETAIL_KEYS` con todos los valores enteros.
- **E3 (B2.9):** orden de evidencia: psql "antes", luego `restart worker`, luego `--run-once`; anotar si `--status` ya muestra un intento automático.
- **E4 (V2.5, V8, B3.14):** `$DC stop worker` antes de cualquier `alembic downgrade` que borre `worker.job_runs`, `$DC start worker` después, con `healthy` y `RestartCount` anotados; en B3.14 dejar escrito que no hace falta parar el worker.
- **E5 (B1.6, B2.5, S4A-D63):** guarda dura de `--date`: una fecha distinta de hoy exige `--simulate`, `ENV=dev` y que el nombre de la base de `DATABASE_URL` termine en `_sim` o sea `apex_test`; si no, salida 2; se prueba con `.../apex` y `.../apex_sim`.
- **E6 (W0-2.1, compose-smoke):** la primera invocación de `--run-once expirations` acepta código 0 o 3 (o se espera a que `--status` no muestre `running`); la segunda exige 0.
- **E7 (B1.10):** en el contenedor endurecido (`read_only`, sin `keys`) correr también `--run-once expirations` (marcador), no solo `--status`, para ejercitar `load_module_services` e importar `memberships.service`.
- **E8 (F2.2, F1.5.4):** `MemberDataTab.test.tsx` no existe: el Rojo de F2 lo crea; `web/tests/e2e/audit.spec.ts` de preview se crea en el Rojo de F1 o se quita de la línea de gate. Regla de `ls` previo a cada línea de gate.
- **E9 (B3.8, ci.yml):** el `grep -cE` de CI añade al patrón `^USER_READ_LIMIT_PER_MIN=12000$|^USER_AUDIT_VERIFY_LIMIT_PER_MIN=300$|^USER_AUDIT_VERIFY_LIMIT_PER_HOUR=2000$`, cambia el mensaje "se esperaban 8 cubetas" y el comentario de `.env.example`; quedan 12 cubetas y 11 variables.
- **E10 (B3.4, B3.8):** `conn = await conn.execution_options(isolation_level="AUTOCOMMIT")` (se espera); la excepción de `test_guarded_calls.py` se aplica por ruta relativa exacta (`core/audit_verify.py`, `modules/audit/verify.py`) con control negativo que cubra también `connect(...).execution_options(...)` dentro de una función; la prueba H-2 fija `DB_IDLE_IN_TX_TIMEOUT_MS` bajo en `server_settings` del engine de prueba (el implementador confirma cómo `conftest` construye ese engine).
- **Observaciones menores que el ejecutor aplica en su slice:** parar el worker (`$DC stop worker`) mientras se edita `app/worker/` o `memberships/expirations.py` y arrancarlo en el checkpoint (RUNBOOK §7); riesgo 9 (`read_only`) pasa a "verificado" (`PYTHONDONTWRITEBYTECODE=1` y usuario 10001 ya en la imagen); la prueba inversa de `AUDITABLE_TABLES` en B8.2 no exige `__audited__` a `audit.verifications`; en B1.7 medir la cobertura de `cli.py` por separado; `CLAVES_SIN_RUTA_TODAVIA` es el nombre real de la lista de `test_user_limits_catalog.py`; en B3.4 comparar las claves de candado con las constantes reales; P2-1 por API respeta 30 escrituras por minuto en `cancel` y en `DELETE` por separado; `finish_run` registra `type(exc).__name__` y la prueba lo fija.

---

# Plan de implementación · Sprint 4A · Worker, auditoría verificable, tablero y planes restantes

- Rama: `feat/sprint-04a-worker-auditoria-tablero`. HEAD de partida: `f5f2503` (= `main`, cierre del Sprint 3). Última migración aplicada en `apex-db-1`: `0011_payments_immutability`. Este sprint aplica `0012_worker_job_runs` y `0013_audit_verifications` y ninguna más.
- Veredicto de entrada: AMARILLO (`docs/ddd/impacto/sprint-04a.md`). Este plan absorbe las 13 condiciones para VERDE (C1 a C13); la sección 10 da el paso de cada una.
- Entradas leídas completas: `sprint-04a-blueprint.md` (S4A-D1 a S4A-D42, secciones 1 a 10), `sprint-04a-seguridad-diseno.md` (H-1, H-2, M-1 a M-7, L-1 a L-10, S4A-D43 a S4A-D61), `impacto/sprint-04a.md`, `sprint-04a-exploracion.md`, `SPRINT-04A.md`, `CRITICA-2.md` (N-3), las historias y desgloses de US-077, 080, 081, 082, 094, 102 a 106, 108 a 110 y 113, `CLAUDE.md`, `DECISIONES.md` (bloque Sprint 3, "Estado al cierre del Sprint 3", "Dueños asignados al cierre del Sprint 3", P2-1), `docs/scratch/sprint-03.md` y `sprint-03-verify-delivery.md` (patrón de cuaderno y de evidencia), `sprint-03-plan.md` (modelo de formato), `scripts/workflow/*.sh` y su `README.md`, `scripts/ci/*.sh`, `.github/workflows/ci.yml`, `docs/RUNBOOK.md`, y el código real que el sprint toca (`core/{audit,db,config,ratelimit,health,clock,context,locks}.py`, `cli.py`, `main.py`, `modules/{audit,plans,members,memberships,auth}`, `tests/conftest.py`, `tests/architecture/*`, `tests/factories/*`, `infra/*`, `web/src/config/*`, `web/src/shared/lib/audit-labels.ts`, `web/tests/e2e/helpers/stack.ts`).
- Mandan este plan y su bloque de decisiones (sección 1). **Donde el plan y el blueprint choquen manda el plan; donde el blueprint y la revisión de seguridad choquen manda la revisión, salvo que la sección 1 diga lo contrario con motivo; la decisión final se copia a `DECISIONES.md` (sección "Sprint 4A") en el checkpoint de S4A-W0-1.** Lo que el orquestador no fijó se decide aquí con una decisión `S4A-D62` o posterior y se reporta al final.
- Doctrina: TDD por slice (Rojo sobre stubs por el agente QA, Verde por el implementador, gate que sella, checkpoint), deuda técnica cero (los 2 HIGH y los 7 MEDIUM de seguridad son pasos explícitos del slice que los cierra; ningún LOW se difiere sin dueño) y ejecución al 100 % sin pausas intermedias, con las tres paradas que fija la doctrina (gate que no se arregla dentro del plan, acción destructiva no prevista, cambio real de alcance) y la cuarta de este sprint: `verify-audit` contra `apex-db-1` da "rota" (sección 5, B3.14).

## 0. Convenciones comunes a todos los slices

Alias usado en todo el plan (solo desde Bash): `DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"`. Las pruebas del api necesitan `TEST_DATABASE_URL=postgresql+asyncpg://apex:apex-test@127.0.0.1:5443/apex_test` exportada en la shell; `uv` vive en `~/.local/bin` y `python` no está en el `PATH` del host (todo Python del host va con `uv run`). Siempre `127.0.0.1`, nunca `localhost`.

Cuaderno del sprint: `docs/scratch/sprint-04a.md` (backend y orquestador) y `docs/scratch/sprint-04a-front.md` (worktree del front). Cada slice deja su bloque Rojo (línea base, conteo de pruebas en rojo y motivo de cada una) y Verde (conteo en verde, desviaciones), como en el Sprint 3.

### Agentes por slice

- Rojo: `backend-qa-executor` (api) o `frontend-qa-automation` (front) escribe stubs y pruebas, confirma el rojo con conteo y lo anota en el cuaderno.
- Verde: `backend-implementor` (api) o `frontend-ux-engineer` (front, en worktree) hace la implementación, los docs, el contrato, los gates, Docker y el checkpoint.
- `security-reviewer` por slice sensible, antes del gate que sella: B1 (worker y `core/jobs`), B3 (verificación), B4 (lista y detalle), B5 (historial para el coach), B6 (`contact_for_notification`), B8 (tablero), F1 (pantalla de auditoría). Su informe va al cuaderno; todo CRITICAL o HIGH se corrige dentro del slice.
- `database-reviewer` antes del Verde de las dos migraciones (B1.5 y B3.6).
- `plan-critic` revisa este plan antes de ejecutar W0-1 (Fase 2.5).
- Un slice no empieza hasta el checkpoint del anterior en la misma rama. El front corre en su worktree por disponibilidad del backend (sección 3).

### Gate y checkpoint (orden heredado del Sprint 3)

- Orden obligatorio: (1) Verde completo; (2) P-API si cambió el contrato; (3) escribir el bloque del slice en el cuaderno y cualquier doc (`DECISIONES.md`, `CLAUDE.md`, `RUNBOOK.md`, `BRECHAS.md`, `ROUTES.md`, `SPRINT-04A.md`); (4) **último** `slice-gate.sh` del slice, el que sella; (5) solo pasos que no tocan el árbol (Docker, psql de lectura, curl, Playwright contra el stack); (6) `checkpoint-commit.sh`. Si (5) obliga a cambiar código, se vuelve a (1). `checkpoint-commit.sh` aborta si la huella del árbol cambió después del sello.
- Trailer obligatorio en todo commit: antes de cualquier checkpoint, `export CHECKPOINT_TRAILER='Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>'`; los commits de evidencia y de docs que no pasan por el script llevan la misma línea como último párrafo (`git commit -m "..." -m "$CHECKPOINT_TRAILER"`).
- Evidencia posterior al sello (E8 del Sprint 3): se guarda en el scratchpad de la sesión y se escribe en el cuaderno como primer bloque del slice siguiente ("Evidencia de <slice anterior>") o en un commit `docs(sprint-04a): evidencia de <slice>` inmediatamente después del checkpoint (sin gate, solo docs). Nunca se edita el árbol entre el sello y el checkpoint.
- `slice-gate.sh <modulo> [archivos]`: se corren todos los gates del slice seguidos, sin editar entre uno y otro; `tests/architecture` corre en cada gate (A-5). Antes de cada línea de gate con lista, `ls` de cada archivo (E4; en PowerShell `Test-Path`): un archivo ausente aborta con "archivo inexistente" y no deja sello. `PYTEST_ADDOPTS="-m 'not perf'"` en todos los gates salvo los que listan un archivo `perf` (ninguno de este plan: las `perf` se corren aparte, ver cada slice).
- Mapeo de módulos (S3-D61, el script no cambia; verificado en `scripts/workflow/slice-gate.sh`): `core/<x>` exige `api/src/app/core/<x>.py` o `.../<x>/` (`core/jobs`, `core/alerts`, `core/audit`, `core/audit_verify`, `core/validators`, `core/config`, `core/ratelimit`); `worker` exige `api/src/app/worker/`; `cli` exige `api/src/app/cli.py`; `architecture` sin código; `<modulo>` exige `api/src/app/modules/<modulo>/` (`audit`, `auth`, `members`, `memberships`, `plans`, `dashboard`); `web/<feature>` exige `web/src/features/<feature>` (`web/system`, `web/dashboard`, `web/members`, `web/plans` existen en HEAD), `web/shared` → `web/src/shared`, `web/app` → `src/config`, `src/routes*`, `tests/unit`, `tests/lint`. Los que no existen en HEAD los crea el Rojo del slice antes del primer gate: `worker/__init__.py` y `core/jobs.py` y `core/alerts.py` (B1.1), `core/audit_verify.py` (B3.2), `modules/dashboard/__init__.py` (B8.1). Con lista, los archivos de prueba pueden vivir en cualquier carpeta bajo `api/tests/` (`tests/integration/`, `tests/migrations/`, `tests/worker/`).
- Checkpoint: `bash scripts/workflow/checkpoint-commit.sh "S4A-<id> <resumen>"` (el script antepone `chore(checkpoint):`). Antes, `git status` muestra solo cambios del slice.
- Suite completa del api (memoria del equipo, ~5 GB libres): nunca junto a vitest o Playwright; fuera de `run-gates.sh` se corre en dos mitades sin `--cov`: `uv run pytest tests/architecture tests/core tests/crypto tests/auth tests/settings tests/migrations tests/cli tests/worker -q -m "not perf"` y `uv run pytest tests/members tests/plans tests/memberships tests/payments tests/audit tests/dashboard tests/integration -q -m "not perf"`. `run-gates.sh` (con `--cov`) se corre solo con el front y el navegador cerrados, en B2.8, B3.13, B8.9 y V9.

### P-MIG · Protocolo de migración nueva (B1 `0012`, B3 `0013`)

1. Volcado previo, solo desde Bash: `$DC exec -T db pg_dump -U apex -Fc apex > docs/scratch/sprint-04a-antes-<rev>.dump && chmod 600 docs/scratch/sprint-04a-antes-<rev>.dump` (`-T` evita la TTY que corrompe el binario; volcado completo porque `0012` toca `worker` y la primera corrida del job toca `memberships` y `audit`). `*.dump` ya está en `.gitignore`. Se borran al cerrar (V12).
2. Detener el api mientras se redacta: `$DC stop api`. El api monta `migrations/` por bind y corre `upgrade head` en cada arranque; un archivo a medio escribir se aplicaría o rompería el arranque. Regla heredada: un Verde desechable del QA solo contra `db_test` con el api parado.
3. Escribir `api/migrations/versions/<rev>.py` y `api/tests/migrations/test_<rev>.py`; `migrations/env.py` importa el modelo nuevo (`app.core.jobs` en B1, `app.core.audit_verify` en B3).
4. Probar contra `db_test`: `cd api && uv run pytest tests/core/test_migrations.py tests/migrations/test_<rev>.py -q` (ciclo `upgrade head → downgrade base → upgrade head` incluido en `test_downgrade_a_base_vacia_y_vuelta_a_head`).
5. Un solo head: `cd api && uv run alembic heads` (también `test_single_head`). Obligatorio porque el front corre en un worktree.
6. `$DC start api`; esperar `healthy`; `$DC exec api alembic current` debe dar `<rev> (head)`; `$DC logs --tail 20 api` sin errores. Esta es la **única** forma en que `0012` y `0013` se aplican a `apex-db-1`: el api las aplica al arrancar. El `alembic upgrade head` explícito sobre `apex-db-1` solo se autoriza en el paso 7 de este protocolo (B1.11 y B3.14) y en V2.
7. Ciclo en `apex-db-1`: `$DC exec api alembic downgrade -1`, `$DC exec api alembic upgrade head`, `$DC exec api alembic current`.
8. Verificación del esquema desde Bash, de solo lectura: `$DC exec -T db psql -U apex -d apex -c '\d worker.job_runs'` (B1) y `-c '\d audit.verifications'` (B3); el resultado va al cuaderno.
9. La prueba de la migración anterior pasa de "es head" a "está en la cadena hasta head" (`test_0011_payments_immutability.py:112-117` en B1; `test_0012_worker_job_runs.py` en B3).

### P-API · Contrato (B3, B4, B5, B7, B8)

1. `cd api && uv run python -m app.cli export-openapi ../docs/openapi.json`.
2. `cd web && npm run gen:api`.
3. `cd web && npx vitest run src/core/api/types.contract.test.ts`.
4. Exportar dos veces: idénticas.
5. Los dos archivos regenerados entran en el checkpoint del slice. Solo el backend toca `types.ts`; el worktree del front hace rebase antes de cada slice.
6. Si una respuesta que el front valida con un esquema Zod `.strict()` gana un campo (`PlanOut.active_members_count` en B7, D25), el mismo checkpoint agrega el campo al esquema como opcional con valor por defecto y corre `cd web && npx vitest run src/shared/data/plans.test.ts src/features/plans/schemas.test.ts`.
7. `errorCodes.ts` solo gana un código cuando su literal ya existe en `api/src` (`errorCodes.test.ts`): `verification_running` (B3), `audit_entry_not_found` (B4), `plan_has_active_memberships` (B7); el front los agrega en F1 y F4.

### Docker y quirks de este equipo (RUNBOOK §7, cuaderno del Sprint 3)

- `docker compose build` y `up --build` fallan (Compose 5.6.1 + buildx 0.38.1 rechazan `build.network: host`). Se construye con `docker buildx build --load --network host --allow network.host -t apex-api:local -f api/Dockerfile api` y `docker buildx build --load --network host --allow network.host -t apex-web:local -f web/Dockerfile .` y se levanta con `$DC up -d --no-build`. En la CI (Linux) no aplica.
- **api:** el bind de `src` con `--reload` recoge los cambios de código. Una migración nueva exige P-MIG. Solo `pyproject.toml`, `uv.lock`, `alembic.ini` o `Dockerfile` exigen reconstruir `apex-api:local` (en este sprint: B1 quita el `omit` de `pyproject.toml`, que no afecta a la imagen; no hay dependencias nuevas).
- **worker y tools:** desde W0-1 ven el código por bind en desarrollo (`compose.dev.yml`, S4A-D9); un cambio en `app/worker/` exige `$DC restart worker` (no hay `--reload`). `apex-api:local` se reconstruye con buildx en W0-2.4, B8.9 y V2.
- **web:** sin bind. `apex-web:local` se reconstruye con buildx antes de cualquier E2E del proyecto `stack` o demo en `http://localhost:8180` (cada F.6 y V2).
- `compose-smoke.sh` no corre tal cual en este equipo (su `$DC build api` y `up --build`): se corre una copia en el scratchpad con solo esos dos cambios (buildx directo y `up -d --no-build`), como en V8 del Sprint 3; en la CI corre el original.
- `E2E_BASE_URL=http://localhost:8180`. Topes para V4: apilar `infra/compose.e2e.yml` y el bloque de `.env` con los topes ×100 (sección 7, V4); restaurar `.env` con `cmp` contra la copia del scratchpad.
- Tras editar `.env`, siempre `$DC up -d api` (no `restart`). No editar `api/src` mientras corre un E2E `stack` ni una verificación en segundo plano.
- Hook `commit-quality` falla con ~100 archivos preparados: fusiones del worktree con `GIT_EDITOR=true git merge --continue` o commits por lotes de 40 archivos como máximo.
- Prohibiciones absolutas: nunca `$DC down -v`; nunca Alembic sobre `apex-db-1` fuera de P-MIG pasos 6 y 7 y de V2; nunca SQL de escritura directa sobre `apex-db-1` (psql solo `SELECT` y `\d`; la limpieza P2-1 va por la API); nunca resetear la contraseña del admin real (`admin@ejemplo.local`): las credenciales de E2E y demo son `E2E_ADMIN_EMAIL` y `E2E_ADMIN_PASSWORD` de un admin desechable creado por API y borrado al cerrar, como en la validación final del Sprint 3 (RUNBOOK §8). `gh` no está instalado: el estado de la CI lo mira una persona en GitHub Actions.
- Hook global `config-protection` bloquea `Write`/`Edit` sobre configuraciones de lint: ninguno de los slices las toca. Los heredocs de Bash pierden barras invertidas: el contenido con `\` se escribe con la herramienta Write.

## 1. Bloque "Sprint 4A" para `docs/ddd/DECISIONES.md`

Se agrega como sección nueva `## Sprint 4A · decisiones de implementación` en el checkpoint de S4A-W0-1 (paso 7). Las decisiones del blueprint (S4A-D1 a S4A-D42) se registran en su forma final, con la corrección que la revisión de seguridad o este plan les impone; las de seguridad (S4A-D43 a S4A-D61) con la opción elegida; las de este plan continúan en S4A-D62. Cada contradicción entre blueprint y seguridad dice cuál manda y por qué.

### Contradicciones resueltas (resumen; el detalle va en cada decisión)

1. **S4A-D26 "`USER_LIMITS` no cambia" frente a S4A-D45 (`staff-read`) y S4A-D47 (`audit-verify`, `audit-verify-hour`).** Manda la seguridad: `USER_LIMITS` gana tres cubetas y `Settings` tres variables (`USER_READ_LIMIT_PER_MIN=120`, `USER_AUDIT_VERIFY_LIMIT_PER_MIN=3`, `USER_AUDIT_VERIFY_LIMIT_PER_HOUR=20`), las tres nacen en **B3** (un solo cambio de `Settings`, `.env.example`, `user_limits_from`, `test_env_example.py` y la CI); `staff-read` queda en la lista de pendientes de `test_user_limits_catalog.py` hasta B4. Motivo: las lecturas nuevas leen la tabla más grande del sistema y el patrón de S3 M-2 (`members-detail`) ya fijó que toda lectura cara por usuario lleva cubeta; la verificación repetida es un vector de denegación barato. Lo que D26 conserva: las cuatro escrituras de planes siguen con `admin-write`.
2. **S4A-D4 (`--date`) frente a S4A-D48 (`--simulate`).** Manda la seguridad: `--date` distinto de hoy exige `ENV=dev` **y** `--simulate`; el job simulado reclama `job_name = "<job>_sim"`; la demo con fecha adelantada corre contra una copia (`apex_sim` en `apex-db_test-1`, S4A-D63), nunca contra `apex-db-1`. Motivo: `.env.example` trae `ENV=dev` y la guarda de D4 falla abierta; una corrida con fecha futura sobre la base viva falsifica `at` en la cadena inmutable, deja `expired` guardado sin vuelta atrás y ocupa la ranura del día real.
3. **S4A-D13 y S4A-D14 (umbral 50.000, lote de 5.000, 202, `admin-write`) frente a S4A-D43, S4A-D44 y S4A-D47.** Manda la seguridad en lo que corrige y se conserva lo demás: `0013` suma `through_hash` y `run_verification` compara contra el ancla de la última verificación `ok` (D43); la conexión del candado es `AUTOCOMMIT` e invalidada en `finally`, con `VERIFY_MAX_SECONDS = 900` y cancelación en el `shutdown` (D44); `VERIFY_BATCH_SIZE = 1000` con `await asyncio.sleep(0)` entre lotes y cubetas propias (D47). Se conservan el contrato 200/202/409 y `SYNC_VERIFY_MAX_ROWS = 50_000` como valor inicial, calibrado por `test_verify_performance.py` con el lote de 1.000 (si 100.000 filas caben en 20 s sube a 100.000; si 50.000 no caben en 20 s baja a 20.000; el valor final se anota).
4. **S4A-D9 (`keys:ro` y `uploads` en el worker) frente a S4A-D49.** Manda la seguridad: el worker de 4A no monta volúmenes, va `read_only` con `tmpfs /tmp`, `cap_drop ALL` y `no-new-privileges`; `test_compose_config.sh` invierte la aserción de `keys` para el worker. Motivo: en 4A el worker no cifra ni descifra; el Sprint 5 vuelve a montar `keys:ro`.
5. **S4A-D19 (`user_refs_for` con correo para todos) frente a S4A-D54.** Manda la seguridad: `user_names_for` (solo `display_name`) para `members` y `dashboard`; `user_refs_for` (con correo) solo para `audit`; prueba AST. La parte local del correo al coach queda registrada como regresión consciente de S3-D57.
6. **S4A-D28 (`recent` en una consulta por `ix_audit_log_table_seq`) frente a S4A-D51.** Manda la seguridad: una consulta por tabla y unión en memoria; la prueba perf lo exige con `EXPLAIN` por tabla.
7. **S4A-D21 y S4A-D20 frente a S4A-D50.** Se añaden `test_contact_callers.py`, la regla de composición y `MemberHistoryItem.purpose`; nada del blueprint se retira.
8. **S4A-D3 y S4A-D6 (reclamo antes de `actor_scope`) frente a S4A-D55.** Manda la seguridad: el runner fija `actor_scope(SYSTEM_USER_ID)` y `batch_scope` **antes** de `claim_run`; `stale_after = 2 × timeout_s`; `finish_run` bajo `asyncio.shield`.
9. **S4A-D9 punto CI (`datosDeBase()` no cuenta `job_runs`) frente a S4A-D59.** Manda la seguridad: el archivo real es `web/tests/e2e/helpers/stack.ts` y `datosDeBase()` devuelve credenciales; la verificación es `grep -rn "job_runs\|audit_log" web/tests` vacío y specs que no dependen del orden de `GET /audit`.
10. **S4A-D17 (blobs tal cual en el detalle) frente a S4A-D52.** Manda la seguridad: el servidor sustituye todo valor `apx1.` por el marcador `{"encrypted": true, "key_id", "alg"}`; `FieldChange.encrypted` se conserva. El front reconoce el marcador y también el prefijo (defensa en profundidad).
11. **S4A-D16 y S4A-D17 (rangos sin tope) frente a S4A-D46.** Manda la seguridad: `from`/`to` acotados, `seq ≤ 2**63 - 1`, `table` con longitud. La regla `check_instant_range` vive en `core/validators.py` (S4A-D66).
12. **Blueprint W0-2 ("`--run-once expirations` con código 0") frente a TDD (el job de B1 sería un stub que lanza).** Este plan decide (S4A-D64): en B1 `jobs/expirations.run` es un marcador explícito que no toca nada y devuelve `ok` con `details={"revisados": 0, "placeholder": "S4A-B2"}`; B2 lo reemplaza. Así W0-2 puede exigir código 0 y una fila en `job_runs` sin adelantar B2.

### Decisiones del blueprint (S4A-D1 a S4A-D42) en forma final

- **S4A-D1:** aceptada tal cual (columna `status` como espejo; lecturas derivadas; eventos `MembershipExpiring` y `MembershipExpired` sin suscriptores; `_mark_summary_dirty` no se suscribe; primera corrida real documentada en RUNBOOK). Añadido por S4A-D48: el docstring de `memberships/events.py` fija que un consumidor del Sprint 5 descarta eventos cuyo `on_date` no sea `today_bogota()` ni el día anterior.
- **S4A-D2:** aceptada (dos fases, una transacción por socio, `lock_member` y `sell.lock_membership`, reintento acotado, `RecomputeSummary` solo con conteos). Añadido por S4A-D57: la sesión de la fase 1 se cierra antes de la fase 2 y las esperas de reintento ocurren fuera de `session.begin()`; lo vigila `test_expirations_lock_order.py` por AST.
- **S4A-D3:** aceptada con S4A-D55: `claim_run` recibe el actor ya fijado (`actor_scope` antes del reclamo); `stale_after` por defecto `timedelta(seconds=2 * spec.timeout_s)` (30 min con `timeout_s=900`); `finish_run(session, run_id, *, result, error, details)` acepta `error` solo como nombre de tipo de excepción (`type(exc).__name__`) y `details` solo como diccionario de enteros con claves de `DETAIL_KEYS = frozenset({"revisados", "cambiadas", "por_vencer", "vencidas", "otras", "busy_omitidos", "errores", "placeholder_ok"})` más `attempts` (que escribe el propio `finish_run`) y `clock_override` (booleano, S4A-D48); cualquier otra clave o valor lanza `ValueError` antes de escribir. Se llama bajo `asyncio.shield` desde el runner.
- **S4A-D4:** reemplazada por S4A-D48 (ver abajo). Se conservan los códigos de salida de `--run-once` (0, 1, 2, 3) y `--status <job>`; `--status` admite también `<job>_sim`.
- **S4A-D5, S4A-D6, S4A-D7, S4A-D10:** aceptadas tal cual. Precisión a D6 por S4A-D56: el trabajo de latido hace `SELECT 1` con `statement_timeout` de 5 s en una sesión corta y solo toca `HEARTBEAT_PATH` si responde. Precisión a D7: `alert()` recibe `code` y un contexto de conteos y nombres de job; `LogAlertSink` no imprime ids ni nombres de personas (prueba con un contexto que trae un documento: se rechaza por `ValueError` si una clave no es de `ALERT_CONTEXT_KEYS = {"job", "result", "error_type", "attempts", "run_date"}`).
- **S4A-D8:** aceptada con S4A-D56 (latido condicionado a `SELECT 1`) y S4A-D49 (`/tmp` en `tmpfs`). RUNBOOK §7 dice que `unhealthy` en `docker compose ps` es el aviso hasta `/health` con `job_runs` (v0.2).
- **S4A-D9:** corregida por S4A-D49 (sin `keys` ni `uploads`, endurecimiento) y S4A-D59 (verificación real de `web/tests`). Se conservan: perfil hasta W0-2, `depends_on` de `db` y `api` healthy, binds de `src` y `migrations` en `compose.dev.yml` para `worker` y `tools` (solo lectura), aserciones de `test_compose_config.sh`, smoke ampliado en W0-2.
- **S4A-D11:** aceptada (`verify_chain(rows, *, start_prev_hash=ZERO_HASH, start_seq=1)`, `VerifyResult.last_seq` y `last_hash` al final con `None` por defecto; semántica del salto sin cambio). La "cola perdida" se detecta con el ancla de S4A-D43, no con `through_seq` de la misma tabla.
- **S4A-D12:** aceptada con S4A-D43 (`through_hash`, ancla, línea de log `audit anchor`) y S4A-D47 (`VERIFY_BATCH_SIZE = 1000`, `sleep(0)`). `core/audit_verify.py` importa de `core/audit` y de `core/db`, `core/clock`, `core/context`, de nadie más.
- **S4A-D13:** corregida por S4A-D44 (conexión `AUTOCOMMIT` + `invalidate()`, `VERIFY_MAX_SECONDS = 900`, cancelación en el `shutdown` del lifespan) y S4A-D47 (lote de 1.000); umbral inicial 50.000 calibrado (contradicción 3).
- **S4A-D14:** corregida por S4A-D47: `POST /audit/verify` consume `audit-verify` (3/min) y `audit-verify-hour` (20/h), no `admin-write`; declara 429 y entra en `CON_LIMITE`. Se conservan 200/202/409, `VerifyResultOut`, `VerifyStartedOut`, `verification_running`, `GET /audit/verify/last` sin límite y antes de `/audit/{seq}`.
- **S4A-D15:** aceptada con S4A-D53: con `ENV=production`, `verify-audit` y `recompute-memberships` exigen `--as` (salida 2 si falta) y rechazan `--db-timeouts off` (salida 2); con `ENV=dev` `--as` sigue opcional. `cli.py` se parte en `app/cli_ops.py` (registrado desde `cli.py`, `app.add_typer` o `app.command` importado) si supera 760 líneas; la prueba de tamaño lo decide en B2.
- **S4A-D16:** aceptada con S4A-D45 (`staff-read`, `MAX_AUDIT_OFFSET = 100_000` con 422 `field="offset"`) y S4A-D46 (rangos). El selector de usuario del front envía `user_id`.
- **S4A-D17:** corregida por S4A-D52 (marcador en vez de blob) y S4A-D46 (`seq ≤ MAX_SEQ`). El servicio sigue sin importar el bus; el marcador lo arma la pura `blob_marker(value)` de `audit/diff.py` partiendo el texto por `.` según el formato `apx1.<key_id>.<alg>.<nonce>.<ct>` de `CLAUDE.md`; una prueba fija la paridad del prefijo y del separador con `core/crypto/types` (la prueba importa `types`; el módulo no).
- **S4A-D18:** aceptada (`audit` partido: `verify.py` en B3, `queries.py` y `diff.py` en B4; `PRIVATE_HELPERS["audit"]` crece por slice).
- **S4A-D19:** aceptada en lo esencial (sin `0014`, `display_name` = parte local del correo, `Sistema` para `SYSTEM_USER_ID`) y corregida por S4A-D54: dos funciones, `user_names_for(session, user_ids) -> dict[UUID, str]` y `user_refs_for(session, user_ids) -> dict[UUID, UserRef]`; `UserRef(id, email, display_name)`. `names_for` e `ids_by_email` no cambian.
- **S4A-D20:** aceptada con S4A-D45 (`staff-read` en `GET /members/{member_id}/audit`, 429 declarado y en `CON_LIMITE`; `MAX_AUDIT_OFFSET`) y S4A-D50 (`MemberHistoryItem.purpose: Literal["notify", "auth_link"] | None`). Lo demás tal cual (arista `members -> audit`, `q` por parte local, `fields` sin valores, congelaciones por el `update` de la membresía, renombre de la prueba de `test_audited_tables.py`).
- **S4A-D21:** aceptada con S4A-D50 (`CONTACT_CALLERS` vacío en 4A; regla de composición: una unidad por socio, en transacción propia o tras `lock_member` del mismo socio y antes de cualquier candado posterior, nunca en un bucle sobre varios socios en la misma transacción; el llamador confirma antes de enviar).
- **S4A-D22, S4A-D23, S4A-D24, S4A-D25:** aceptadas tal cual. Añadido a D22 por S4A-D60: sin `version` y precio vigente al vender (riesgo aceptado, `SellMembershipIn` sin `expected_price_cop`). Añadido a D24 por S4A-D60: el 409 entrega solo un conteo; la limpieza P2-1 va por la API con un admin desechable, nunca por SQL.
- **S4A-D26:** corregida por la contradicción 1: `USER_LIMITS` pasa de 9 a 12 cubetas y `Settings` de 8 a 11 variables `USER_*`; las cuatro escrituras de planes conservan `admin-write`; `POST /audit/verify` usa las cubetas de D47; las lecturas de D45 usan `staff-read`.
- **S4A-D27:** aceptada con S4A-D45: `GET /dashboard` consume `staff-read`, declara 429 y entra en `CON_LIMITE` (deja de ser "sin 429").
- **S4A-D28:** corregida por S4A-D51 (una consulta por tabla, unión en memoria, `limit ≤ 50`, hasta seis tablas) y por S4A-D61 (una sola constante de tablas auditables en `audit/queries.py`). Catálogo de frases sin cambio.
- **S4A-D29:** aceptada.
- **S4A-D30 a S4A-D36:** aceptadas tal cual, con los añadidos de S4A-D58 (F1: filtros de la URL validados y construidos con `URLSearchParams`, `?seq=` entero seguro, sondeo con tope de `VERIFY_MAX_SECONDS`, valores como texto y recorte a 2.000 caracteres) y S4A-D52 (`encryptedBlob.ts` reconoce el marcador y el prefijo).
- **S4A-D37, S4A-D38:** aceptadas; `0013` gana `through_hash char(64) NOT NULL` con CHECK `^[0-9a-f]{64}$` (S4A-D43). P-MIG de la sección 0 es la forma operativa.
- **S4A-D39:** aceptada (`omit` fuera en el Verde de B1; pruebas de `export-openapi` e `init-keys` en el Rojo de B1; `run-gates.sh` al cerrar B2, B3, B8 y el sprint).
- **S4A-D40:** aceptada; el script no cambia (verificado).
- **S4A-D41:** aceptada; la lista de correcciones documentales es el paso W0-1.6 y suma las de la revisión de seguridad (D4, D9, D12, D13, D14, D16, D17, D19, D21, D26, D28 y la ruta de `stack.ts`).
- **S4A-D42:** aceptada con la precisión de la sección 3: el front corre en un worktree por disponibilidad del backend (F1 tras B4, F2 tras B5, F4 tras B7, F3 tras B8) y se fusiona en V1.

### Decisiones de la revisión de seguridad (S4A-D43 a S4A-D61), con la opción final

- **S4A-D43 (H-1):** `audit.verifications.through_hash`; `run_verification` lee la última verificación `ok` (el ancla) y, tras recorrer la cadena, exige `max(seq) >= ancla.through_seq` y que la fila `seq = ancla.through_seq` exista con `hash = ancla.through_hash`; si no, `ok = false` y `broken_at_seq = min(last_seq + 1, ancla.through_seq)`; solo una verificación `ok` mueve el ancla; cada `ok` escribe `logger.info("audit anchor", extra={"through_seq", "through_hash"})`; primera vez sin ancla: mensaje "íntegra desde el origen, sin verificación anterior que comparar". Residual registrado: sin firma externa hasta v0.3 (`sign-audit`). Slice B3.
- **S4A-D44 (H-2):** la conexión del candado `4_270_003` se abre con `execution_options(isolation_level="AUTOCOMMIT")` y se cierra con `await conn.invalidate()` en el `finally`, tras intentar `pg_advisory_unlock`; `VERIFY_MAX_SECONDS = 900` con `asyncio.timeout`; la tarea 202 se guarda en `_BACKGROUND_TASKS` y el `shutdown` del lifespan la cancela; misma conexión y mismo cuidado en la CLI. `test_guarded_calls.py` (L-11 del Sprint 3) prohíbe `isolation_level` en `execution_options`: gana una excepción explícita para `core/audit_verify.py` (único archivo permitido) con la prueba de que sigue fallando en cualquier otro. Slice B3.
- **S4A-D45 (M-1):** cubeta `staff-read` (120/min, `USER_READ_LIMIT_PER_MIN`) en `GET /audit`, `GET /audit/{seq}`, `GET /members/{member_id}/audit` y `GET /dashboard`; `MAX_AUDIT_OFFSET = 100_000` en `GET /audit` y en el historial (422 `field="offset"`); sin límite en `GET /audit/verify/last`. Nace en B3 (variable y catálogo); rutas en B4, B5 y B8.
- **S4A-D46 (M-2):** `from`/`to` entre `2020-01-01T00:00Z` y `now + 1 día`, `from < to`, 422 con `field`; `seq: Annotated[int, Path(ge=1, le=MAX_SEQ)]` con `MAX_SEQ = 2**63 - 1`; `table` con `^[a-z_]{1,63}\.[a-z_]{1,63}$` y `max_length=127`. La regla vive en `core/validators.py` como `check_instant_range(start, end, *, floor, ceiling, field_start, field_end)` (S4A-D66). Slice B4.
- **S4A-D47 (M-3):** cubetas `audit-verify` (3/min, `USER_AUDIT_VERIFY_LIMIT_PER_MIN`) y `audit-verify-hour` (20/h, `USER_AUDIT_VERIFY_LIMIT_PER_HOUR`) en `POST /audit/verify`; `VERIFY_BATCH_SIZE = 1000` y `await asyncio.sleep(0)` entre lotes; la prueba perf mide que ningún bloque síncrono pasa de 100 ms con 1.000 filas. Slice B3.
- **S4A-D48 (M-4):** `--date` distinto de hoy exige `Settings.ENV == "dev"` y `--simulate` (si no, código 2 con mensaje); primera línea de salida `RELOJ SIMULADO: <fecha>` y `logger.warning("clock override", extra={"date": ...})`; con `--simulate` el reclamo usa `job_name = f"{job}_sim"` y `details["clock_override"] = True`; `should_run`, `last_run` y `--status <job>` del job real ignoran `*_sim`. `.env.example` gana el comentario "en el servidor real debe ser `production`" junto a `ENV=dev`; RUNBOOK fija que la demo con fecha corre contra `apex_sim` (S4A-D63). Slices B1 (worker y `serve`) y B2 (CLI, regla de `on_date`).
- **S4A-D49 (M-5):** `worker` sin `volumes`, con `read_only: true`, `tmpfs: ["/tmp"]`, `cap_drop: ["ALL"]`, `security_opt: ["no-new-privileges:true"]`; `test_compose_config.sh` cambia la aserción de `keys` del worker a "no monta `keys` ni `uploads` hasta el Sprint 5", suma las cuatro de endurecimiento y una de que ningún servicio de `compose.yml` monta `../api/src` ni `../api/migrations`. Residual registrado: mientras no exista el rol de base separado (S4B-W0-2) el worker usa la credencial del api. Slice W0-1.
- **S4A-D50 (M-6):** `tests/architecture/test_contact_callers.py` (AST sobre `app/`): `CONTACT_CALLERS = frozenset()` en 4A; nadie fuera de `modules/members/` (ni `cli.py`, ni `worker/`, ni un `router.py`) referencia `contact_for_notification`; el Sprint 5 agrega solo `notifications.service`. Regla de composición en el docstring y en una prueba con espía de candados. `MemberHistoryItem.purpose`. Slices B6 y B5.
- **S4A-D51 (M-7):** `audit.service.recent` consulta cada tabla por separado (`table_name = :t AND action = ANY(:acciones) AND user_id <> ALL(:excluidos) ORDER BY seq DESC LIMIT :n`), une por `seq` en memoria y recorta; `limit ≤ 50`; `RECENT_TABLES_ALLOWED` de seis tablas como máximo. Slice B8.
- **S4A-D52 (L-1):** `AuditDetail.before/after` y `FieldChange.before/after` sustituyen los valores `apx1.` por `{"encrypted": true, "key_id": "<uuid>", "alg": "A256GCM"}`; `FieldChange.encrypted` se conserva; prueba de que la respuesta serializada no contiene `apx1.`. Slices B4 y F1.
- **S4A-D53 (L-2):** con `ENV=production`, `verify-audit` y `recompute-memberships` exigen `--as` y rechazan `--db-timeouts off` (salida 2 en ambos casos). Slices B2 y B3.
- **S4A-D54 (L-3):** `user_names_for` (solo nombre) separada de `user_refs_for` (con correo, solo la importa `audit`); prueba AST en `tests/architecture/test_user_refs_scope.py` de que `dashboard` y `members` no acceden a `.email` de un `UserRef` ni llaman a `user_refs_for`. Regresión consciente de S3-D57 registrada. Slices B4, B5, B8.
- **S4A-D55 (L-4):** actor fijado antes de reclamar; `stale_after = 2 × timeout_s`; `finish_run` bajo `shield`; `error` solo tipo y `details` con claves cerradas (`DETAIL_KEYS`). Slice B1.
- **S4A-D56 (L-5):** el latido solo se toca si `SELECT 1` responde; `unhealthy` es el aviso. Slice B1.
- **S4A-D57 (L-6):** sesión de lectura cerrada antes de la fase 2; esperas fuera de la transacción; prueba AST. Slice B2.
- **S4A-D58 (L-7):** front de auditoría: `auditFilters.ts` valida y construye con `URLSearchParams`; `?seq=` con `Number.isSafeInteger(x) && x >= 1`; `useLastVerification` sondea con tope de 900 s y luego "la verificación no terminó; vuelve a intentarlo"; `AuditDetailPanel` pinta todo valor como texto y recorta a 2.000 caracteres. Slice F1.
- **S4A-D59 (L-8):** `grep -rn "job_runs\|audit_log" web/tests` vacío en W0-2 y en V9; `audit.spec.ts` y `home.spec.ts` (stack) con el admin del seed (`E2E_ADMIN_*`), `crearCoach`, `exigirStackLocal` y `borrarUsuario`, sin dependencia del contenido de la primera página de `GET /audit` ni del orden de `recent`; `compose.e2e.yml` no toca al worker salvo que una spec dependa del orden (entonces `profiles: ["worker"]` allí y se anota). Slices W0-2, F1, F3.
- **S4A-D60 (L-9):** sin `version` y precio vigente al vender (riesgo aceptado); el 409 de la baja entrega solo `N`; limpieza P2-1 por API con un admin desechable, con el tope de `admin-write` (≈ 270 llamadas a 30/min ≈ 10 min) y un script de ritmo en el scratchpad. Slice B7 (decisión) y V12 (ejecución).
- **S4A-D61 (L-10):** `tests/architecture/test_settings_no_secrets.py` (existe) gana el caso "ningún esquema de sección tiene un campo cuyo nombre contenga `token`, `secret` o `password`"; `AUDITABLE_TABLES` única en `audit/queries.py` con `RECENT_TABLES_ALLOWED` derivada y una prueba que falla si un modelo auditado nuevo no está ni en la lista ni en `AUDIT_TABLES_EXCLUDED_FROM_RECENT` con motivo; la lectura de la auditoría (`GET /audit`, `GET /audit/{seq}`) no se audita: el log de acceso del api (ruta y estado, sin parámetros) es el único rastro. Slices B4 y B8.

### Decisiones de este plan (lo que el orquestador no fijó; S4A-D62 en adelante)

- **S4A-D62 · Front en worktree.** Los cuatro slices de front corren en `.claude/worktrees/sprint-04a-front` (rama `feat/sprint-04a-front`, creada desde la rama del sprint tras el checkpoint de B4), con `SLICE_BASE` fijado a la base del worktree y `git rebase feat/sprint-04a-worker-auditoria-tablero` antes de cada slice. Orden de ejecución: F1 (tras B4), F2 (tras B5), F4 (tras B7), F3 (tras B8). El front no edita `docs/scratch/sprint-04a.md`, `DECISIONES.md`, `CLAUDE.md`, `BRECHAS.md`, `docs/openapi.json` ni `types.ts`; sí edita `docs/design/ROUTES.md`. Se fusiona en V1 (`GIT_EDITOR=true git merge --continue` si el hook falla por el tamaño).
- **S4A-D63 · Demo con fecha adelantada sobre una copia.** La corrida `--run-once expirations --date 2026-11-01 --simulate` de la demo (B2.9) corre contra `apex_sim`, una base creada en `apex-db_test-1` (`createdb`) y restaurada desde un `pg_dump -Fc` de `apex` tomado tras aplicar `0012`, con `DATABASE_URL` sobrescrita por `-e DATABASE_URL` del entorno de la shell; se borra con `dropdb` al terminar el paso. `apex-db-1` solo recibe corridas sin `--date`.
- **S4A-D64 · Job marcador en B1.** `worker/jobs/expirations.py` nace en B1 como marcador que devuelve `JobResult(ok=True, details={"placeholder_ok": 1})` sin abrir sesión de negocio (docstring "marcador hasta S4A-B2"); B2 lo reemplaza y su Rojo cambia la prueba. Motivo: W0-2 exige `--run-once expirations` con código 0 antes de B2.
- **S4A-D65 · Las tres cubetas nacen en B3.** `USER_READ_LIMIT_PER_MIN`, `USER_AUDIT_VERIFY_LIMIT_PER_MIN` y `USER_AUDIT_VERIFY_LIMIT_PER_HOUR` entran a `Settings`, `.env.example`, `user_limits_from`, `USER_LIMITS`, `test_env_example.py` (caso "las tres variables de S4A-B3 van activas"), el `sed` y el conteo (8 → 11) del job `e2e-stack` de `ci.yml` y el bloque ×100 de V4 en un solo paso (B3.8). `staff-read` queda en las pendientes de `test_toda_clave_del_catalogo_tiene_ruta_salvo_las_pendientes` hasta B4.
- **S4A-D66 · `check_instant_range` en `core/validators.py`.** El módulo `audit` no puede importar `payments.rules`; la regla de S3-D47 se generaliza en `core/validators.py` con constantes `INSTANT_FLOOR = datetime(2020, 1, 1, tzinfo=UTC)` y `instant_ceiling(now) = now + timedelta(days=1)`; `payments.rules` no cambia (una prueba fija que `PAID_AT_FLOOR == INSTANT_FLOOR`). `core/validators.py` es compartido y lo toca solo B4.
- **S4A-D67 · `tests/integration/` nace en B7** con `__init__.py` y `conftest.py` vacío; el gate `plans` lo recibe por lista. `run-gates.sh` y la CI lo recogen sin cambios (recorren `tests/`).
- **S4A-D68 · Corridas `perf` del sprint.** Cinco archivos: `tests/worker/test_expirations.py` (B2), `tests/audit/test_verify_performance.py` (B3), `tests/audit/test_list_performance.py` (B4), `tests/audit/test_recent.py` (caso perf, B8) y `tests/dashboard/test_perf.py` (B8). Se corren en su slice con `uv run pytest -m perf <archivo> -q` fuera del gate y en V5; sus tiempos van al cuaderno.
- **S4A-D69 · `tests/factories/audit_chain.py` escribe con Core y respeta el hash.** `make_audit_chain(session, n, *, table_name, user_id=SYSTEM_USER_ID)` calcula `chain_hash` con la misma `canonical` de `core/audit.py` (importa `core.audit`, permitido en pruebas) e inserta por lotes de 5.000 con `insert(AuditEntry.__table__)`; `tamper_row` y `drop_rows` usan `ALTER TABLE audit.audit_log DISABLE TRIGGER USER` dentro de la transacción de prueba y la cierran con `ENABLE ALWAYS TRIGGER audit_log_forbid_mutation` (misma regla E1 del Sprint 3; `test_no_trigger_tampering.py` solo barre `app/`).
- **S4A-D70 · Limpieza de `db_test`.** `LIMPIAR_JOB_RUNS` (`DELETE FROM worker.job_runs` bajo `to_regclass`) entra en `LIMPIEZA_DE_SESION`, en el `finally` de `dos_sesiones` y en `limpiar_tras_dos_sesiones` (B1); `LIMPIAR_VERIFICATIONS` (bloque `DO $$` con `DISABLE TRIGGER USER`, `DELETE`, `ENABLE ALWAYS TRIGGER verifications_forbid_mutation` y `verifications_forbid_truncate`, bajo `to_regclass` y guarda `EXISTS` sobre `pg_trigger` mientras `0013` no exista) entra **antes** de borrar `audit.audit_log` en las tres limpiezas (B3). `test_triggers_siempre_activos.py` suma los dos triggers de `verifications` (B3).
- **S4A-D71 · Admin desechable para demos y E2E.** Como en la validación final del Sprint 3: se crea por API un admin `admin-e2e-<epoch>@apex.test` con el admin real autenticado una sola vez por el operador (credenciales del gestor, nunca en archivos ni en el cuaderno), su contraseña se fija con `tools issue-reset-link --as admin@ejemplo.local` y `POST /auth/reset`, se exporta como `E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD` en la shell y se borra en V12. La contraseña del admin real no se toca.
- **S4A-D72 · `test_file_and_function_size.py` manda sobre la partición.** `cli.py` (541 → ~660) se parte en `cli_ops.py` solo si pasa de 760 (B2 lo mide); `plans/service.py` en `plans/changes.py` solo si pasa de 600 (B7). Ninguna función nueva supera 50 líneas: `recompute_statuses`, `run_verification`, `movement_phrase`, `verify` y `serve` se parten desde el diseño (los auxiliares del blueprint).
- **S4A-D73 · `tests/architecture/test_worker_boundaries.py` absorbe la regla de importadores de `core.jobs`.** `core/jobs` y `core/alerts` sin `app.modules` lo cubre ya `test_core_no_importa_modulos` (recorre todo `core/`); la regla "solo `app.worker.*` importa `app.core.jobs`" vive en la prueba nueva junto a las fronteras del worker y de `cli.py`.
- **S4A-D74 · `audit.verifications` y `worker.job_runs` fuera de `test_no_physical_delete` para `job_runs`.** `job_runs` es bitácora operativa y sus filas se reutilizan por día (`ON CONFLICT DO UPDATE`), no se borran por código: la prueba suma solo `AuditVerification` y `audit.verifications` (append-only, N-30).

### Contradicciones de contrato cerradas en los desgloses (T-DOC, W0-1.6)

Las de S4A-D41 (`verify_chain`, `bus.op_context`, `SensitiveFieldRevealed`, `SYSTEM_ACTOR`, `get_by_email`, `ids_by_email` parcial, `names_for -> UserRef`, `refs_for`, `Depends(Clock)`, `table_name="verifications"`, nombres `esquema.tabla`, `by: Actor`, `broken_seq`, `slow`, `test_service_import_cycles.py`, `command: uv run`, `HomePage.tsx`, `0014_audit_subject_member`, lecturas del estado guardado, healthcheck por `job_runs`, US-041 y `display_name`, `WORKER_*`), más las de este plan: `contact_for_notification(member_id, fields, purpose)` → `(session, member_id, purpose)`; "`GET /members/{id}/audit` sin 429" → con `staff-read`; "`GET /dashboard` sin 429" → con `staff-read`; "`POST /audit/verify` con `admin-write`" → `audit-verify`; "`--date` solo con `ENV=dev`" → y `--simulate`; `VERIFY_BATCH_SIZE = 5000` → `1000`; "`keys:ro` en el worker" → sin volúmenes; `web/tests/e2e/stack/helpers/stack.ts` → `web/tests/e2e/helpers/stack.ts`; `list_for_subject(member_id)` (SPRINT-04A B5) → `member_history(session, member_id, page, q)`.

## 2. Fixtures y utilidades de prueba compartidas

Cada una entra en el primer slice que la necesita.

- **B1:**
  - `api/tests/factories/job_runs.py`: `make_job_run(session, job_name, run_date, *, result="ok", started_at=None, finished_at=None, error=None, details=None, created_by=SYSTEM_USER_ID) -> JobRunView` (inserta con Core y confirma como `make_plan`); entrada `"worker.job_runs"` en `FACTORIES` (`tests/factories/__init__.py`; `test_no_plaintext_at_rest.py` no la exige porque la tabla no tiene columnas cifradas).
  - `api/tests/worker/__init__.py` y `conftest.py`: `session_factory` (sobre `get_sessionmaker()` del engine de prueba), `reloj_worker` (`FrozenClock` en `2026-10-21T15:00:00Z` instalado con `set_clock` y restaurado), `spec_que_escribe` y `spec_que_lanza` (dos `JobSpec` de prueba: uno inserta un plan por el service real bajo `actor_scope(SYSTEM_USER_ID)`, el otro lanza `RuntimeError("documento 1020304417 en el mensaje")` para la prueba de redacción), `limpiar_job_runs` (autouse: `DELETE FROM worker.job_runs` al terminar cada prueba), `latido_tmp` (`monkeypatch` de `HEARTBEAT_PATH` a `tmp_path`).
  - `api/tests/conftest.py`: `LIMPIAR_JOB_RUNS` en las tres limpiezas (S4A-D70).
  - `api/tests/cli/_apoyo.py` (si no existe): `correr(app, args, env)` sobre `CliRunner` con `ENV` inyectado por `monkeypatch` de `Settings` (nunca `os.environ`, `test_no_os_environ.py`).
- **B2:** `make_memberships_para_recalculo(session, *, n_socios, por_socio, hoy)` en `tests/factories/memberships.py` (reutiliza `make_member`, `make_plan`, `make_membership`, `make_freeze`; fija `status` guardado a voluntad); `capturar_eventos` para `MembershipExpiring` y `MembershipExpired`; `dos_sesiones` para `test_recompute_lock_order.py`.
- **B3:**
  - `api/tests/factories/audit_chain.py` (S4A-D69): `make_audit_chain`, `tamper_row(session, seq, column, value)`, `drop_rows(session, seqs)`, `drop_tail(session, n)`, `table_digest(session) -> str` (hash de `string_agg(hash, '' ORDER BY seq)` para "la verificación no cambia ninguna fila").
  - `api/tests/audit/conftest.py`: `audit_chain_factory` (fixture que expone las funciones anteriores sobre `session`), `candado_tomado` (abre una conexión aparte con `pg_try_advisory_lock(4_270_003)` y la libera al salir), `umbral_bajo` (`monkeypatch` de `SYNC_VERIFY_MAX_ROWS` a 10), `plazo_corto` (`monkeypatch` de `VERIFY_MAX_SECONDS` a 2), `audit_service` importado al nivel del módulo para que `restaurar_bus` conserve las suscripciones.
  - `api/tests/conftest.py`: `LIMPIAR_VERIFICATIONS` (S4A-D70).
  - `api/tests/cli/conftest.py`: `settings_produccion` (copia de `settings_prueba` con `ENV="production"` y los pisos de S3-D79 cumplidos) para S4A-D53.
- **B4:** `api/tests/audit/_apoyo.py`: `AUDIT = "/api/v1/audit"`, `CAMPOS_ROW`, `CAMPOS_DETAIL`, `CAMPOS_CHANGE`, `leer_entrada(session, seq)`; `sembrar_actividad(session, *, ana, juan)` (socia creada por Ana, editada y revelada por Juan, una venta, un pago y su anulación, por los services reales bajo `actor_scope` de cada usuario; devuelve los ids) que reutilizan B5 y B8.
- **B5:** nada nuevo (usa `sembrar_actividad`).
- **B6:** `bus_listo` (existe), `batch_scope` de `core.context`, `contar_crypto_ops(session, record_id, verb, purpose)` en `tests/members/_apoyo.py`.
- **B7:** `tests/integration/__init__.py` y `conftest.py` (S4A-D67); `tests/plans/_apoyo.py` gana `cuerpo_patch(**cambios)`.
- **B8:** `tests/dashboard/__init__.py`, `_apoyo.py` (`DASHBOARD = "/api/v1/dashboard"`, `CAMPOS_DASHBOARD` exacto con los cinco futuros, `CAMPOS_MOVEMENT`), `conftest.py` (`sin_cache_de_resumen` reutilizada desde `tests/memberships/conftest.py` por import, `dashboard_service` al nivel del módulo).
- **Front (worktree):** `web/src/test/audit.tsx` (`auditRow`, `auditDetail`, `verifyResult`, `verifyStarted`), `web/src/test/dashboard.tsx` (`dashboardOut` con los cinco futuros en `null`, `movement`), `web/src/test/history.tsx` (`memberHistoryItem`), `planRow` con `active_members_count` en `web/src/test/plans.tsx` (si no existe, se crea); `web/tests/e2e/helpers/stack.ts` gana `verificarCadena(page, admin)` y `leerDashboard(page, admin)` por API; `mockSession` para el proyecto `preview`.

## 3. Paralelismo: cuándo lanzar cada slice de front

El backend corre en serie en la rama del sprint (W0-1, B1, W0-2, B2, B3, B4, B5, B6, B7, B8). Un agente de front (`frontend-ux-engineer`) corre los cuatro slices en el worktree de S4A-D62:

- **F1 (pantalla de auditoría):** tras el checkpoint de B4 (necesita B3 y B4). Primer slice del worktree: lo crea desde la rama del sprint en ese momento.
- **F2 (historial de la ficha):** tras B5.
- **F4 (acciones de planes):** tras B7.
- **F3 (Inicio):** tras B8 (último; necesita `GET /dashboard`).
- Los E2E `stack` de cada F se corren en el slice si `apex-web:local` ya se reconstruyó con ese código (F.6); si no, en V4. Los `preview` se corren siempre en su slice.
- B5, B6, B7 y B8 pueden avanzar mientras F1 y F2 están en curso: ninguno toca `web/`.

## 4. Wave 0

### S4A-W0-1 · Worker en Compose (solo preparación), T-DOC y decisiones del sprint

- **Historias:** US-113 (tareas DevOps sin código del worker), T-DOC de C13 y copia de las decisiones.
- **Cierra:** C2 (parte: healthcheck con perfil, binds de desarrollo), C13 (T-DOC, cierre de la revisión de diseño previa), M-5 (S4A-D49), S4A-D8, S4A-D9, S4A-D36, S4A-D41, S4A-D49, S4A-D62 a S4A-D74 (registro).
- **Depende de:** nada. **Migración:** ninguna (el volcado previo a `0012` se toma aquí, paso 2).

**Paso 1 · W0-1.1 · Línea base**
1. `$DC ps`: los cuatro servicios `healthy`; `$DC exec api alembic current` = `0011_payments_immutability (head)`; `git status` limpio salvo los cuatro documentos de planificación sin seguimiento; `git worktree list` solo el principal.
2. Gates baratos sobre HEAD: `cd api && uv run ruff check . && uv run ruff format --check . && uv run mypy src`; `cd web && npx tsc --noEmit`. La suite completa no se repite (V9.1 del Sprint 3 sobre el mismo código: 3.883 ok, 97 %; se cita).
3. Crear `docs/scratch/sprint-04a.md` con la línea base (HEAD, ids de `apex-api:local` y `apex-web:local` por `docker image inspect --format '{{.Id}} {{.Created}}'`, puertos de `.env` solo por nombre, `alembic current`, conteos citados).
4. `export CHECKPOINT_TRAILER='Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>'` y `export TEST_DATABASE_URL=...` en la shell de la sesión.

**Paso 2 · W0-1.2 · Volcado previo a `0012` (P-MIG paso 1)**
`$DC exec -T db pg_dump -U apex -Fc apex > docs/scratch/sprint-04a-antes-0012.dump && chmod 600 docs/scratch/sprint-04a-antes-0012.dump`; `ls -l` al cuaderno (tamaño, no contenido). `git status` no lo lista (`*.dump` ignorado; se comprueba con `git check-ignore`).

**Paso 3 · W0-1.3 · Rojo de infraestructura (`scripts/ci/test_compose_config.sh`)**
- Aserciones nuevas (fallan contra el `compose.yml` de HEAD): `worker` tiene `healthcheck` con `test[0] == "CMD"`, `test[1] == "python"`, `interval 30s`, `timeout 5s`, `retries 3`, `start_period 90s`; `worker.depends_on` tiene `api` con `condition: service_healthy` y `db` healthy; `worker` sin `ports`; `worker` sin `volumes` (S4A-D49); `worker.read_only is True`; `tmpfs` contiene `/tmp`; `cap_drop == ["ALL"]`; `security_opt` contiene `no-new-privileges:true`; ningún servicio de `prod` monta un `source` que termine en `api/src` ni `api/migrations`; en `dev`, `worker` y `tools` montan `../api/src` en `/app/src` y `../api/migrations` en `/app/migrations` ambos `read_only`; `worker.command == ["python", "-m", "app.worker.main"]`.
- Cambia: el bucle `for svc in ("api", "worker")` de `keys` en solo lectura pasa a solo `api`; se agrega "worker no monta keys ni uploads hasta el Sprint 5".
- Se mantiene: `"worker" in prod["worker"].get("profiles", [])` ("worker queda tras un perfil hasta S4A-W0-2").
- `bash -n scripts/ci/test_compose_config.sh`; correrlo: debe fallar en las aserciones nuevas (conteo al cuaderno).

**Paso 4 · W0-1.4 · Verde de `infra/compose.yml`**
Servicio `worker`: `image: apex-api:local`, `command: ["python", "-m", "app.worker.main"]`, `env_file: ../.env`, sin `volumes`, `read_only: true`, `tmpfs: ["/tmp"]`, `cap_drop: ["ALL"]`, `security_opt: ["no-new-privileges:true"]`, `depends_on: db: condition: service_healthy` y `api: condition: service_healthy`, `healthcheck.test: ["CMD", "python", "-c", "import os, sys, time; p = '/tmp/apex-worker-heartbeat'; sys.exit(0 if os.path.exists(p) and time.time() - os.path.getmtime(p) < 120 else 1)"]` con `interval: 30s`, `timeout: 5s`, `retries: 3`, `start_period: 90s`, `restart: unless-stopped`, **`profiles: ["worker"]`** conservado con el comentario actualizado ("hasta S4A-W0-2, que lo quita cuando existe `app/worker/main.py`; N-3"). Comentario de endurecimiento (S4A-D49) y del latido (S4A-D8, S4A-D56).

**Paso 5 · W0-1.5 · Verde de `infra/compose.dev.yml`**
`worker` y `tools` ganan `volumes: - ../api/src:/app/src:ro` y `- ../api/migrations:/app/migrations:ro` (comentario: "solo desarrollo; la imagen de producción no cambia; un cambio en `app/worker/` exige `restart worker`"). `$DC config --quiet` y `docker compose --env-file .env --profile worker --profile tools -f infra/compose.yml config --quiet` sin errores.

**Paso 6 · W0-1.6 · Documentación de contrato (T-DOC, S4A-D41 y sección 1)**
- Desgloses en `docs/ddd/08_implementation_breakdown/`: `EP-07-padron-de-socios/US-077-...md` (firma `contact_for_notification(session, member_id, purpose)`, `_decrypt_fields` + `audit.record` + `SYSTEM_USER_ID`, sin `bus.batch`, `test_contact_callers.py`), `EP-08-catalogo-de-planes/US-080`, `US-081`, `US-082` (`get_actor()`, `test_service_import_graph.py` y `LAZY_IMPORT_WHITELIST`, `counts_active_by_plans`, regla de `pending_payment`, rutas `POST .../activate` y `/deactivate`), `EP-09-membresias/US-094` (lecturas derivadas por S4A-D1, una transacción por socio, `perf`, `--simulate`, `on_date`), `EP-11-auditoria/US-102` (filtros reales, `search_user_ids`, `user_refs_for`, `staff-read`, rangos, `MAX_AUDIT_OFFSET`), `US-103` (marcador de blobs, `MAX_SEQ`), `US-104` (`verify_chain` ampliada, `audit.verifications`, `broken_at_seq`, `through_hash` y ancla, 202 a mano, cubetas `audit-verify`, lote 1.000), `US-105` (`cli.resolve_actor`, `--wait-timeout`, `ENV=production` exige `--as`), `US-106` (`member_history`, `q`, `MemberHistoryItem` sin `user_email` y con `purpose`, `0002` ya trae el sujeto, congelaciones por el `update`), `EP-12-tablero-de-inicio/US-108` (`current_clock()`, `staff-read`), `US-109` (`InicioPage.tsx`), `US-110` (`refs_for` real, `user_names_for`, tablas `esquema.tabla`, `recent` por tabla), `EP-13-puesta-en-marcha-y-continuidad/US-113` (`compose.yml` real, constantes de horario, `--simulate`, `_sim`, endurecimiento, latido). Cada corrección como nota `> -` de cabecera (patrón del Sprint 3); las historias de `07_user_stories/` no se tocan.
- `docs/ddd/09_sprint_plan/SPRINT-04A.md`: `-m perf`; `0014` no se crea; `GET /audit` con sus filtros reales; `contact_for_notification` con la firma real; US-041 no creó `display_name` (S4A-D19); `/health` no lee `job_runs` en 4A; "Verificar ahora"; `GET /members/{id}/audit` y `GET /dashboard` con `staff-read`; `POST /audit/verify` con `audit-verify`; `--date` solo con `--simulate`; `datosDeBase()`; sección "Validación del sprint" con V1 a V12 de este plan.
- `CLAUDE.md`: estructura real de `core/` (`jobs.py`, `alerts.py`, `audit_verify.py`), de `worker/` (`schedule.py`, `registry.py`, `runner.py`, `runtime.py`, `main.py`, `jobs/`), `modules/audit` partido (`verify.py`, `queries.py`, `diff.py`), `modules/dashboard`, `members/contact.py`, `memberships/expirations.py`; comandos `verify-audit` y `recompute-memberships` en "Comandos"; "`/health` lee `job_runs`" pasa a v0.2; `PUBLIC_ROUTES` sigue en ocho; las tres variables `USER_*` nuevas en la línea de rate limit de Seguridad; `core/validators.py` con `check_instant_range`.
- `docs/design/ROUTES.md`: línea 39 (activar y desactivar por `POST /plans/:id/activate` y `/deactivate`; `DELETE /plans/:id`; columna "Socios con él" por `active_members_count`), línea 89 (`GET /audit?from&to&user_id&table&record_id&subject_member_id&action&q&limit&offset`; `GET /audit/:seq`), línea 18 (Inicio deja de ser mínima en S4A-F3). El front solo las ajusta si F1 a F4 cambian algo más.
- `docs/BRECHAS.md`: sección nueva `## 11. Sprint 4A: brechas con el diseño` con las filas de S4A-D36 (`Auditoria.html`: Qué cambió, búsqueda por nombre de socio, Descifrar dato o Mostrar, Exportar rango v0.2, firma ML-DSA v0.3, entidades Resultado y Llave, valores enmascarados; `Inicio.html`: Sistema marcó..., saludo con nombre, Hoy en el box, Por avisar hoy, Asistencia, WOD de hoy, pendientes de pago; `Planes.html`: Descripción, Días para usarlas, casilla Activo; `ROUTES.md`: PATCH `active`, filtros de `GET /audit`), cada una con su slice y dueño; la "Contradicción abierta" de §9 (línea 244, `display_name` en `0004`) se cierra: manda S4A-D19 (no en 4A; dueño v0.2 con EP-04); §10.14 gana el cierre de la "revisión de diseño previa al Sprint 4A": S3-D98 fuera de v0.1 con dueño "backlog v0.2, junto a EP-16", los "Pendiente de diseño" de §10 conservan su estado sin cambio de código.
- `docs/ddd/DECISIONES.md`: sección "Sprint 4A" con el bloque completo de la sección 1 (S4A-D1 a S4A-D42 en forma final, S4A-D43 a S4A-D61, S4A-D62 a S4A-D74, contradicciones de contrato) y, en "Dueños asignados al cierre del Sprint 3", la nota de que S3-D98 y los pendientes de §10 quedaron resueltos aquí.
- `docs/RUNBOOK.md`: §6 gana los esqueletos de `0012` y `0013` (se completan en B1 y B3); §7 gana el esqueleto "Worker" (comando, `--run-once`, `--status`, `--date --simulate`, latido, `unhealthy` como aviso; se completa en W0-2); §11 nuevo "Worker, auditoría verificable y tablero (Sprint 4A)" con los esqueletos que B2, B3, B4 y B8 completan (primera corrida del job, caché del resumen, `verify-audit`, candado y códigos, ancla y línea `audit anchor`, copia del log junto al respaldo, limpieza P2-1).
- `scripts/workflow/README.md`: ejemplos `worker`, `core/jobs`, `core/audit_verify`, `dashboard`, `web/system`, `web/dashboard`; la nota de cobertura (M-6) pasa a "desde S4A-B1 el `omit` ya no existe".
- Nota al inicio de `sprint-04a-blueprint.md`: "corregido por `sprint-04a-plan.md`: D3, D4, D6, D9, D12, D13, D14, D16, D17, D19, D20, D21, D26, D27, D28 y S4A-D62 a S4A-D74".
- `.env.example`: comentario junto a `ENV=dev` ("en el servidor real debe ser `production`", S4A-D48). Sin variables nuevas aquí (llegan en B3).

**Paso 7 · W0-1.7 · Cuaderno y `BRECHAS` §11 inicial**
Bloque W0-1 en `docs/scratch/sprint-04a.md` (línea base, volcado, aserciones en rojo y en verde, archivos tocados). Crear `docs/scratch/sprint-04a-front.md` vacío con el encabezado y la regla del worktree.

**Paso 8 · W0-1.8 · Verificación de infraestructura**
1. `bash -n scripts/ci/*.sh scripts/workflow/*.sh`.
2. `bash scripts/ci/test_compose_config.sh` (todas las aserciones en verde, incluida la del perfil); `bash scripts/ci/test_images_pinned.sh`; `bash scripts/ci/test_nginx_conf.sh`.
3. Smoke **sin** el perfil `worker`: copia de `compose-smoke.sh` en el scratchpad con buildx y `up -d --no-build` (sección 0), `SMOKE_KEEP=1`: verde; `$DC ps` no muestra `worker`.
4. `bash scripts/workflow/tests/run.sh`.

**Paso 9 · W0-1.9 · Gate**
Para sellar (la única línea con código del api; no hay pruebas nuevas de Python en este slice): `bash scripts/workflow/slice-gate.sh architecture tests/architecture/test_no_os_environ.py tests/core/test_env_example.py` (`ls` previo de los dos; corre `tests/architecture` completo y confirma que el comentario nuevo de `.env.example` no rompe `test_env_example.py`).

**Paso 10 · W0-1.10 · Checkpoint**
`bash scripts/workflow/checkpoint-commit.sh "S4A-W0-1 worker en compose con perfil, endurecimiento, binds de desarrollo, T-DOC y decisiones del sprint"`.

## 5. Backend

Orden estricto: B1 → W0-2 → B2 → B3 → B4 → B5 → B6 → B7 → B8. Todo router nuevo: `APIRouter(tags=[...], dependencies=[Depends(no_store)], responses=responses_for(401, 403))`, rutas fijas antes que las de parámetro, `SessionDep`, `StaffDep`/`AdminDep`, `responses_for(...)` por ruta con 429 solo donde hay `enforce_user_limit` (que ahora incluye las lecturas con `staff-read`).

### S4A-B1 · Proceso worker programado, `core/jobs.py`, `core/alerts.py` y `0012`

- **Historias:** US-113.
- **Depende de:** W0-1.
- **Migración:** `0012_worker_job_runs` (`down_revision = "0011_payments_immutability"`).
- **Cierra:** C1, C11 (parte), C12 (`omit`); L-4 (S4A-D55), L-5 (S4A-D56), M-4 en el worker (S4A-D48 en `main.py` y `serve`); S4A-D3, D5, D6, D7, D8, D10, D38, D39, D40, D64, D70, D73.

**Paso 11 · B1.1 · Directorios, stubs y apoyos (lo que `slice-gate.sh` exige)**
- `api/src/app/worker/__init__.py`, `core/jobs.py`, `core/alerts.py`, `api/tests/worker/__init__.py` (primero: sin ellos `slice-gate.sh worker` y `core/jobs` fallan con "módulo inexistente").
- Stubs con firmas tipadas y `NotImplementedError`: `core/jobs.py` (`JobRun(CommonColumnsMixin, Base)` con `__tablename__ = "job_runs"`, `__table_args__ = {"schema": "worker"}`, columnas de S4A-D38, sin `__audited__`; `JobRunView`; `DETAIL_KEYS`; `claim_run(session, job_name, run_date, *, now, stale_after) -> JobRunView | None`; `finish_run(session, run_id, *, result, error, details) -> JobRunView`; `last_run(session, job_name) -> JobRunView | None`); `core/alerts.py` (`AlertSink` Protocol, `ALERT_CONTEXT_KEYS`, `register_sink`, `alert(code, **context)`, `LogAlertSink`); `worker/schedule.py` (`WORKER_TIMEZONE`, `DAILY_HOUR`, `DAILY_MINUTE`, `STALE_FACTOR = 2`, `next_run`, `should_run`, `is_simulated(job_name) -> bool`, `simulated_name(job) -> str`); `worker/registry.py` (`JobSpec(name, run, hour, minute, timeout_s=900)`, `register`, `get_registry`); `worker/jobs/__init__.py` (`JOBS`); `worker/jobs/expirations.py` (marcador de S4A-D64, ya real: devuelve `JobResult(ok=True, details={"placeholder_ok": 1})`); `worker/runner.py` (`JobContext(session_factory, today, clock, simulated: bool)`, `JobResult(ok, details)`, `JobOutcome(job_name, run_date, result, error_type, details)`, `run_job(spec, *, clock, session_factory, simulated=False) -> JobOutcome`, `run_cycle(registry, ...)`); `worker/runtime.py` (`HEARTBEAT_PATH`, `HEARTBEAT_INTERVAL_S = 30`, `worker_runtime(settings)`, `wait_for_database(settings, *, sleep=asyncio.sleep, max_wait_s=60)`, `touch_heartbeat_if_db_ok(session_factory, path)`); `worker/main.py` (`build_parser()`, `run_once(job, *, date, simulate, settings) -> int`, `status(job, settings) -> int`, `serve(settings, *, stop) -> int`, `main(argv=None) -> int`).
- `migrations/env.py`: `from app.core import jobs  # noqa: F401` (para `target_metadata`).
- Fixtures de la sección 2 (B1): `tests/factories/job_runs.py`, `FACTORIES`, `tests/worker/conftest.py`, `tests/cli/_apoyo.py`, `LIMPIAR_JOB_RUNS` en `tests/conftest.py`. Verificar que nada se rompió: `cd api && uv run pytest tests/core/test_migrations.py tests/architecture -q` (fallan solo las que el Rojo de B1.3 prevé).

**Paso 12 · B1.2 · Rojo de arquitectura (C1)**
- `tests/architecture/test_audited_tables.py`: `EXCLUIDAS` gana `"worker.job_runs": "bitácora operativa del worker; no se audita (US-113, S4A-D3)"`; `_cargar_modelos` importa `app.core.jobs` (así `test_las_exclusiones_existen` la encuentra siempre).
- `tests/architecture/test_core_import_direction.py`: sin cambios de código (recorre `core/`); se añade un caso explícito `test_jobs_y_alerts_no_importan_modulos_ni_audit` (por claridad: `core/jobs.py` y `core/alerts.py` no importan `app.modules` ni `app.core.audit`; `core/audit.py` y `core/health.py` no importan `app.core.jobs`).
- Nueva `tests/architecture/test_worker_boundaries.py` (S4A-D10, S4A-D73): por `ast` con `find_forbidden_imports` sobre `app/worker/**` y `app/cli.py`: ningún `app.modules.<x>.models`, `.router` ni privado de `PRIVATE_HELPERS`; ningún `text(` ni `exec_driver_sql(` en `app/worker/**`; los importadores de `app.core.jobs` en `src/app/` son exactamente archivos bajo `app/worker/` (ni `main.py`, ni `core/health.py`, ni `core/audit.py`); control con fuente falsa que debe fallar.
- `tests/migrations/test_0011_payments_immutability.py:112-117`: de "es head" a "está en la cadena hasta head" (P-MIG paso 9).
- `tests/architecture/test_no_physical_delete.py`: sin cambio (S4A-D74).
- `tests/architecture/test_file_and_function_size.py`: sin cambio; los archivos nuevos entran al recorrido.

**Paso 13 · B1.3 · Rojo de `worker`, `core/jobs`, `core/alerts` y `cli`**
- `tests/worker/test_schedule.py`: `next_run` desde `2026-10-21T11:59Z` da `12:00Z` del mismo día (07:00 Bogotá) y desde `12:00:01Z` el día siguiente; `today_bogota` a `2026-10-22T01:00Z` da `2026-10-21`; `should_run` sin fila (sí tras la hora, no antes), con `ok` del día (no), con `error` del día (no), con `running` de hace 31 min con `timeout_s=900` (sí: `2 × 900 s`), con `running` de hace 10 min (no); `should_run` ignora una fila `expirations_sim` del día (S4A-D48); `is_simulated("expirations_sim")`, `simulated_name("expirations") == "expirations_sim"`; el CHECK de forma acepta `expirations_sim`.
- `tests/worker/test_jobs_core.py` (base real, `session_factory`, `dos_sesiones` donde hay commit; todo bajo `actor_scope(SYSTEM_USER_ID)`): `claim_run` crea la fila `running` con `created_by = SYSTEM_USER_ID`; sin actor lanza `MissingActorError` antes de escribir (S4A-D55 a); el segundo reclamo con `running` vigente da `None`; tras `finish_run` ok, un nuevo reclamo del mismo día reutiliza la fila y `details["attempts"]` tiene 2; un `running` de más de `stale_after` se reclama; dos reclamos concurrentes con `dos_sesiones` dejan una sola ejecución; `finish_run` con `error="RuntimeError"` guarda el tipo; `finish_run` con `error="documento 1020304417"` (no es un nombre de tipo) o con `details={"socio": "Laura"}` lanza `ValueError` y no escribe (S4A-D55 d); `attempts` se recorta a 20; `last_run`; `last_run("expirations")` no devuelve la fila `expirations_sim`.
- `tests/worker/test_runner.py` (`reloj_worker`, `spec_que_escribe`, `spec_que_lanza`): el segundo job corre aunque el primero lance; la escritura del que lanza se revierte; `job_runs` queda con `error` (tipo `RuntimeError`, sin el documento del mensaje) y `ok`; `alert` se llama con `code="job_failed"` y contexto de `ALERT_CONTEXT_KEYS`; `caplog` y stdout no contienen el documento; `timeout_s=1` con un job que duerme 3 s marca `error="TimeoutError"` y la fila no queda `running` (`shield`, S4A-D55 c); el actor de las escrituras del job es `SYSTEM_USER_ID` y `batch_scope` está fijado; `simulated=True` reclama `expirations_sim` y escribe `details["clock_override"] = True`; reinicio a las 09:00 de Bogotá con el ciclo hecho no ejecuta nada y sin ciclo hecho ejecuta una sola vez.
- `tests/core/test_alerts.py`: `register_sink` y `alert` llaman a todos los sinks; un sink que lanza no propaga y se registra; `LogAlertSink` escribe `logger.error` con `code` y el contexto; contexto con clave fuera de `ALERT_CONTEXT_KEYS` lanza `ValueError`; `core/alerts.py` no importa `app.modules`.
- `tests/worker/test_main.py` (`CliRunner` no aplica: `main(argv)` directo con `settings_prueba` inyectado y `monkeypatch` de `load_settings`): `--run-once expirations` da 0 y deja una fila `ok` con `details["placeholder_ok"] == 1` (S4A-D64); `--run-once` con un job de prueba que falla da 1; job inexistente da 2 y la salida lista los registrados; con una corrida `running` vigente da 3; `--date 2026-11-01` sin `--simulate` da 2 con el mensaje; `--date 2026-11-01 --simulate` con `ENV=dev` instala `FrozenClock` (12:00 Bogotá de esa fecha), reclama `expirations_sim`, imprime `RELOJ SIMULADO: 2026-11-01` en la primera línea y deja `logger.warning("clock override")`; con `ENV=production` y `--date --simulate` da 2; `--date <hoy>` sin `--simulate` da 0 (no es distinto de hoy); `--status expirations` imprime el último intento en JSON sin `attempts` y sale 0, o 2 sin corridas; `--status expirations_sim` muestra la simulada; `wait_for_database` con un `sleep` falso respeta 1, 2, 4, ... y el tope de 60 s, y sondea `SELECT 1 FROM worker.job_runs LIMIT 0`; `serve` con la parada ya disparada arranca el scheduler, escribe el latido en `latido_tmp` y sale 0; el latido no se escribe si `SELECT 1` falla (engine roto por `monkeypatch`, S4A-D56); `load_module_services` queda cargado (el gate de pagos está registrado).
- `tests/cli/test_export_openapi_cli.py` y `test_init_keys_cli.py` (`CliRunner`; S4A-D39): `export-openapi` a un archivo temporal produce el mismo JSON que `app.openapi()`; `init-keys` sobre un directorio vacío crea los archivos 600 y una segunda corrida es idempotente.
- `tests/migrations/test_0012_worker_job_runs.py`: columnas y nulabilidad; cada CHECK con SQL crudo (23514: `job_name` con mayúscula, con 1 carácter, con 64; `result` fuera de la lista; `finished_at < started_at`); índice único `(job_name, run_date)` (23505) e índice `(job_name, started_at DESC)`; `down_revision == "0011_payments_immutability"`; es head; sin triggers; `downgrade` deja el esquema `worker` vacío.
- Confirmar el rojo con conteo y motivo por archivo (cuaderno).

**Paso 14 · B1.4 · Migración `0012` (P-MIG pasos 2 a 5)**
`database-reviewer` revisa el archivo antes de probarlo contra `db_test`. `0012_worker_job_runs`: tabla `worker.job_runs` con `id uuid PK`, `job_name text NOT NULL CHECK (job_name ~ '^[a-z][a-z0-9_]{1,62}$')`, `run_date date NOT NULL`, `started_at timestamptz NOT NULL`, `finished_at timestamptz NULL`, `result text NOT NULL CHECK (result IN ('running','ok','error','ok_unverified','stale','missing','corrupt','undecryptable'))`, `error text NULL`, `details jsonb NOT NULL DEFAULT '{}'::jsonb`, `created_at`, `updated_at`, `created_by uuid NOT NULL`, `CHECK (finished_at IS NULL OR finished_at >= started_at)`; `uq_job_runs_name_date (job_name, run_date)` único; `ix_job_runs_name_started (job_name, started_at DESC)`. Sin triggers. `downgrade`: los dos índices y la tabla; nunca el esquema. SQL literal sin f-strings. Pasos 4 y 5 de P-MIG (`pytest tests/core/test_migrations.py tests/migrations/test_0012_worker_job_runs.py -q`; `alembic heads` una).

**Paso 15 · B1.5 · Verde de `core`**
`core/jobs.py` (S4A-D3 y S4A-D55: `claim_run` con `postgresql.insert(JobRun).on_conflict_do_update(index_elements=["job_name", "run_date"], set_={...}, where=or_(JobRun.result != "running", JobRun.started_at < now - stale_after)).returning(...)`, `created_by = get_actor()` evaluado antes de construir la sentencia; `finish_run` valida `error` (`str.isidentifier()` y sin espacios) y `details` contra `DETAIL_KEYS` y tipos, relee la fila, agrega el intento y recorta a 20; `last_run` con `started_at DESC` y `job_name` exacto). `core/alerts.py` (S4A-D7 con `ALERT_CONTEXT_KEYS`). Ninguna función de más de 50 líneas.

**Paso 16 · B1.6 · Verde de `worker`**
`schedule.py`, `registry.py`, `runner.py` (`run_job`: `actor_scope(SYSTEM_USER_ID)` y `batch_scope(uuid4())` **antes** de `claim_run`; `today = clock.today_bogota()`; `job_name = simulated_name(spec.name) if simulated else spec.name`; `asyncio.wait_for(spec.run(ctx), spec.timeout_s)`; `await asyncio.shield(finish_run(...))` en `finally`; `alert("job_failed", job=..., result="error", error_type=...)`), `runtime.py` (`worker_runtime` con las líneas de `cli_runtime` repetidas a propósito, sin keyring ni JWT; `wait_for_database`; `touch_heartbeat_if_db_ok` con `SET LOCAL statement_timeout = '5s'` y `SELECT 1`), `main.py` (argparse con `--run-once <job>`, `--date`, `--simulate`, `--status <job>`; la guarda de S4A-D48 lee `Settings.ENV`, nunca `os.environ`; `serve` con `AsyncIOScheduler(timezone=WORKER_TIMEZONE)`, `CronTrigger(hour=DAILY_HOUR, minute=DAILY_MINUTE)`, `coalesce=True`, `max_instances=1`, `IntervalTrigger(seconds=30)` para el latido, recuperación al arrancar con `should_run`, `SIGTERM` con espera acotada a 30 s). `main.py` delgado (lógica en `schedule`, `runner`, `runtime`).

**Paso 17 · B1.7 · Cobertura (S4A-D39)**
`api/pyproject.toml`: quitar `omit = ["*/app/cli.py", "*/app/worker/*"]` y su comentario (líneas 86-88); `scripts/workflow/README.md` y `run-gates.sh` (comentario de cobertura) al día. Medir: `cd api && uv run pytest tests/worker tests/cli tests/core/test_alerts.py --cov=app --cov-report=term-missing -q -m "not perf"` solo como lectura (la cobertura global se mide en B2.8).

**Paso 18 · B1.8 · Documentación**
RUNBOOK §6 (`0012`: `downgrade 0011_payments_immutability` borra los dos índices y la tabla; sin datos que conservar salvo la bitácora de corridas) y §7 "Worker" (parcial: `--run-once`, `--status`, `--date --simulate`, códigos de salida, latido, `unhealthy` como aviso). `CLAUDE.md` ya recoge la estructura (W0-1). Cuaderno: bloque Verde de B1.

**Paso 19 · B1.9 · Gate**
1. `slice-gate.sh core/alerts tests/core/test_alerts.py`.
2. `slice-gate.sh core/jobs tests/worker/test_jobs_core.py tests/migrations/test_0012_worker_job_runs.py tests/core/test_migrations.py tests/migrations/test_0011_payments_immutability.py`.
3. `slice-gate.sh cli tests/cli/test_export_openapi_cli.py tests/cli/test_init_keys_cli.py tests/cli/test_seed_cli.py`.
4. `slice-gate.sh architecture tests/architecture/test_worker_boundaries.py tests/architecture/test_audited_tables.py tests/architecture/test_core_import_direction.py`.
5. Al final, para sellar: `slice-gate.sh worker tests/worker/test_schedule.py tests/worker/test_runner.py tests/worker/test_main.py tests/worker/test_jobs_core.py`.
`security-reviewer` de B1 antes del gate 5 (actor del worker, `error` y `details` cerrados, sin `os.environ`, latido condicionado).

**Paso 20 · B1.10 · Docker y evidencia (P-MIG pasos 6 a 8)**
1. `$DC start api` (estaba detenido desde B1.4); `healthy`; `$DC exec api alembic current` = `0012_worker_job_runs (head)`; `$DC logs --tail 20 api` sin errores.
2. Ciclo: `$DC exec api alembic downgrade -1` → `upgrade head` → `current`.
3. `$DC exec -T db psql -U apex -d apex -c '\d worker.job_runs'` al cuaderno (columnas, CHECKs, los dos índices).
4. Smoke del endpoint tras la migración: `curl -s http://127.0.0.1:8181/health` 200 (el api sigue sano con la tabla nueva).
5. `$DC --profile worker run --rm worker python -m app.worker.main --status expirations` → código 2 ("sin corridas"): prueba que el contenedor endurecido (`read_only`, sin volúmenes) arranca con el bind de desarrollo y llega a la base. Nada de `--run-once` todavía (W0-2).

**Paso 21 · B1.11 · Checkpoint**
`checkpoint-commit.sh "S4A-B1 worker programado, core/jobs y core/alerts, migración 0012"`; después `docs(sprint-04a): evidencia de S4A-B1`.

### S4A-W0-2 · Activar el worker

- **Historias:** US-113 (cierra el criterio diferido de US-005).
- **Depende de:** B1 (N-3: el perfil se quita solo cuando existe `app/worker/main.py`).
- **Migración:** ninguna.
- **Cierra:** C2 (resto), L-8 (S4A-D59 parte CI), S4A-D9 (smoke), S4A-D42 (primera reconstrucción con buildx).

**Paso 22 · W0-2.1 · Rojo de infraestructura**
- `scripts/ci/test_compose_config.sh`: la aserción del perfil se invierte (`"profiles" not in prod["worker"]`, "worker sin perfil desde S4A-W0-2"); las demás de W0-1 se mantienen. Correrla: falla solo en esa.
- `scripts/ci/compose-smoke.sh` (Rojo del script: se escribe y se corre la copia del scratchpad, que debe fallar porque el perfil sigue): tras `esperar_healthy api 90`, `up -d --no-build worker` (en la CI `up -d worker`), `esperar_healthy worker 120`, comprobar `RestartCount == 0` con `docker inspect -f '{{.RestartCount}}'` tras 30 s, `run --rm worker python -m app.worker.main --run-once expirations` con código 0 **dos veces**, `run --rm worker python -m app.worker.main --status expirations` cuyo JSON muestra `result: ok` (y en la segunda corrida la misma fila: el script compara el `id` de las dos salidas de `--status`).
- `grep -rn "job_runs\|audit_log" web/tests`: debe dar vacío (S4A-D59); se anota el resultado en el cuaderno. Confirmado en HEAD que `datosDeBase()` devuelve credenciales y no cuenta tablas.

**Paso 23 · W0-2.2 · Verde de `infra/compose.yml`**
Quitar `profiles: ["worker"]` y su comentario; el comentario del servicio pasa a describir el endurecimiento, el latido y `depends_on`. `$DC config --quiet`.

**Paso 24 · W0-2.3 · Reconstrucción y arranque**
1. `docker buildx build --load --network host --allow network.host -t apex-api:local -f api/Dockerfile api` (la imagen de producción lleva `app/worker/`; el bind de desarrollo ya lo mostraba, pero la CI y `verify-delivery` usan la imagen). Anotar el id.
2. `$DC up -d --no-build` (recrea `api` con la imagen nueva y arranca `worker`); esperar `api` y `worker` `healthy`; `docker inspect -f '{{.RestartCount}}' apex-worker-1` = 0 tras 30 s; `$DC logs --tail 30 worker` muestra la espera de la base, el arranque del scheduler y el primer latido.
3. `$DC exec api alembic current` sigue en `0012_worker_job_runs (head)`.

**Paso 25 · W0-2.4 · Primera corrida real del marcador**
`$DC run --rm worker python -m app.worker.main --run-once expirations` dos veces (código 0 las dos; sin `--date`); `--status expirations` muestra `result: ok`, `attempts` de 2 (en la vista no sale, pero el `id` es el mismo); psql de lectura: `SELECT job_name, run_date, result, details FROM worker.job_runs` → una fila. Si la hora de Bogotá ya pasó de las 07:00, el `serve` del contenedor pudo recuperar el ciclo antes: entonces habrá un intento más en la misma fila; se anota.

**Paso 26 · W0-2.5 · Documentación**
RUNBOOK §7 "Worker" completo (arranque, `depends_on`, latido y `unhealthy`, `--run-once` dos veces el mismo día, `--status`, `--date --simulate` solo en desarrollo y contra una copia, `restart worker` tras cambiar `app/worker/`, imagen reconstruida con buildx). `SPRINT-04A.md`: W0-2 cumplido.

**Paso 27 · W0-2.6 · Gate**
1. `bash -n scripts/ci/*.sh`.
2. `bash scripts/ci/test_compose_config.sh` (perfil invertido en verde).
3. Smoke completo con el worker: copia del scratchpad de `compose-smoke.sh` con buildx y `up -d --no-build`, `SMOKE_KEEP=1`: verde (worker healthy, 0 reinicios, `--run-once` ×2 con 0, `--status` ok).
4. `bash scripts/workflow/tests/run.sh`.
5. Al final, para sellar: `slice-gate.sh architecture tests/architecture/test_worker_boundaries.py` (sin código nuevo de Python; el sello exige un gate del api).

**Paso 28 · W0-2.7 · Checkpoint**
`checkpoint-commit.sh "S4A-W0-2 worker activo sin perfil, smoke con --run-once y latido"`; después `docs(sprint-04a): evidencia de S4A-W0-2`.

### S4A-B2 · Job diario de vencimientos y `recompute-memberships`

- **Historias:** US-094.
- **Depende de:** B1 y W0-2.
- **Migración:** ninguna.
- **Cierra:** C3, C12 (primer `run-gates.sh`); M-4 (S4A-D48 en la CLI y regla de `on_date`), L-2 (S4A-D53 en `recompute-memberships`), L-6 (S4A-D57); S4A-D1, D2, D15 (parte), D63, D64 (reemplazo del marcador), D72 (medida de `cli.py`).

**Paso 29 · B2.1 · Stubs**
`memberships/expirations.py` (privado): `RECOMPUTE_PAGE = 200`, `MAX_BUSY_RETRIES = 2`, `RETRY_DELAYS_S = (0.5, 1.0)`, `RecomputeSummary` (dataclass congelada de enteros), `async recompute_statuses(session_factory, *, today, page_size=RECOMPUTE_PAGE) -> RecomputeSummary`, `_candidate_member_ids(session, today, expiring_days, after) -> list[UUID]`, `_recompute_member(session_factory, member_id, today, expiring_days) -> tuple[int, int, int, int]`, `_apply_to_member(session, member_id, today, expiring_days)` (cuerpo de la transacción). `memberships/events.py`: `MembershipExpiring(membership_id, member_id, end_date, on_date)` y `MembershipExpired(...)` con el docstring de S4A-D48 punto 3. `memberships/rules.py`: `transition_event(old, new) -> Literal["expiring", "expired"] | None`. `memberships/service.py`: re-exporta `recompute_statuses`, `RecomputeSummary`, `MembershipExpiring`, `MembershipExpired` (a `__all__`); no suscribe nada. `worker/jobs/expirations.py`: `run(ctx)` real (reemplaza el marcador). `cli.py`: comando `recompute-memberships [--date] [--simulate] [--as]`. `tests/architecture/_imports.py`: `PRIVATE_HELPERS["memberships"]` suma `expirations`.

**Paso 30 · B2.2 · Rojo de arquitectura (C3)**
- `tests/architecture/test_no_cross_models.py::test_los_privados_de_memberships_son_los_de_d7`: el conjunto exacto suma `expirations`.
- `tests/architecture/test_handlers_no_new_locks.py`: `SUSCRIPTORES_ESPERADOS` suma `"MembershipExpiring": []` y `"MembershipExpired": []` (S4A-D1); `HANDLERS_ESPERADOS` no cambia; caso nuevo: `expirations.py` no define funciones `on_*`.
- `tests/architecture/test_events_without_pii.py`: los dos eventos pasan (campos `membership_id`, `member_id`, `end_date`, `on_date`).
- `tests/architecture/test_guarded_calls.py`: sin cambio; el caso nuevo afirma que `expirations.py` no contiene `with_for_update`.
- Nueva `tests/architecture/test_expirations_lock_order.py` (AST sobre `memberships/expirations.py`, S4A-D2 y S4A-D57): dentro de `_apply_to_member`, la primera llamada a `lock_member` precede a `lock_membership` y esta al primer `flush`; ningún `await asyncio.sleep` dentro de un `async with ... begin()`; `_candidate_member_ids` se llama fuera del `async with` de la fase 2 (la sesión de lectura se cierra antes); control con fuente falsa que invierte el orden.
- `tests/worker/test_main.py`: el caso del marcador (`placeholder_ok`) se reescribe: `--run-once expirations` sobre la base vacía da 0 con `details["revisados"] == 0`.

**Paso 31 · B2.3 · Rojo de `memberships`, `worker` y `cli`**
- `tests/memberships/test_rules.py::test_transition_event`: active→expiring, active→expired, expiring→expired, frozen→expiring, frozen→active (`None`), active→frozen (`None`), sin cambio (`None`), pending_payment→cualquiera (`None`).
- `tests/worker/test_expirations.py` (`reloj_worker`, base real, `actor_scope(SYSTEM_USER_ID)`, `capturar_eventos`): 2026-10-24 active→expiring con un `MembershipExpiring`; 2026-11-01 expiring→expired con un `MembershipExpired`; dos corridas el mismo día: un solo evento y una sola fila `update`; 2026-11-03 sobre active con fin 2026-10-31 da expired y solo `MembershipExpired`; congelación que empieza hoy da frozen; terminada ayer da active o expiring según el fin; `pending_payment`, `cancelled` y `expired` guardados intactos; `2026-11-01T02:00Z` sigue en el 31 de Bogotá; auditoría con `user_id = SYSTEM_USER_ID` y `subject_member_id`; `expiring_days = 3` desde settings; paridad: tras el job `status` guardado == `compute_status` para toda candidata; `memberships.summary` igual antes y después; ningún suscriptor en los dos eventos; error por socio (`page_size = 2`, handler que lanza para un socio: los demás actualizados, `errores = 1`, log sin nombres ni documentos); ocupación (sesión que sostiene `lock_member` con `lock_timeout` bajo: `busy_omitidos = 1` tras los reintentos y el ciclo sigue); `RecomputeSummary` solo con enteros; con `simulated=True` en el `JobContext` el job reclama `expirations_sim` y la fila real del día no existe. Caso `@pytest.mark.perf`: 1.000 socios y 3.000 membresías en menos de 60 s.
- `tests/memberships/test_recompute_lock_order.py` (`dos_sesiones`, `SET LOCAL lock_timeout = '2s'`): el job frente a `freeze`, `cancel`, `sell` y `register` del mismo socio, simultáneos: sin 55P03 ni 40P01 sin resolver; la anulación gana (una `cancelled` no vuelve a otro estado).
- `tests/cli/test_recompute_memberships.py` (`CliRunner`): código 0 sin errores y 1 con `busy_omitidos + errores > 0`; `--as` con un usuario activo → auditoría atribuida a él; `--as` inexistente da 2; `--date 2026-11-01` sin `--simulate` da 2; con `--simulate` y `ENV=dev` reclama `expirations_sim` e imprime `RELOJ SIMULADO`; con `settings_produccion` sin `--as` da 2; con `settings_produccion` y `--db-timeouts off` da 2 (S4A-D53); la salida solo trae conteos (ningún UUID ni nombre).
- Confirmar el rojo.

**Paso 32 · B2.4 · Verde de `memberships`**
Según S4A-D1, D2 y D57: fase 1 en una sesión propia que se cierra (`async with session_factory() as s:` sin `begin()`; consulta con `status_expr(today, expiring_days) != Membership.status`, `Membership.status.in_(("active", "expiring", "frozen"))`, `member_id > :after`, `ORDER BY member_id LIMIT :page`); fase 2 por socio (`lock_member`, `sell.lock_membership` por fila con `populate_existing`, salto si ya coincide o ya no es candidata, `queries._load_freezes_for`, `compute_status`, asignación, un solo `flush`, `events.emit` según `transition_event`); reintento ante `BUSY_SQLSTATES` con `await asyncio.sleep(RETRY_DELAYS_S[i])` **fuera** del `begin()`; `expiring_days` de `settings_service.memberships_policy` una vez por corrida; `errores` cuenta solo tipos.

**Paso 33 · B2.5 · Verde de `worker` y `cli`**
`worker/jobs/expirations.py`: `run(ctx)` llama `memberships.service.recompute_statuses(ctx.session_factory, today=ctx.today)` y devuelve `JobResult(ok=summary.busy_omitidos + summary.errores == 0, details=asdict(summary))`. `cli.py` `recompute-memberships` (S4A-D15, D48, D53): `cli_runtime`, `resolve_actor`, `unit_of_work(actor)`, `FrozenClock` solo con `--date --simulate`, guarda de `ENV`, `db.get_sessionmaker()` como fábrica, salida de conteos. Medir `wc -l api/src/app/cli.py`: si supera 760, extraer `cli_ops.py` (S4A-D72) y anotarlo.

**Paso 34 · B2.6 · Documentación**
RUNBOOK §11: primera corrida sobre la base viva (decenas de filas `update` con `SYSTEM_USER_ID`: es el rastro correcto), caché del resumen no invalidada desde el worker (visible hasta `SUMMARY_CACHE_TTL_S` tras las 07:00, S3-D93), `recompute-memberships` con `--as`, `--date --simulate` contra `apex_sim`, regla de `on_date` para los consumidores del Sprint 5. `DECISIONES.md`: nada nuevo salvo la medida de `cli.py`.

**Paso 35 · B2.7 · Gate**
1. `slice-gate.sh memberships tests/memberships/test_rules.py tests/memberships/test_recompute_lock_order.py tests/architecture/test_expirations_lock_order.py tests/architecture/test_handlers_no_new_locks.py tests/architecture/test_events_without_pii.py`.
2. `slice-gate.sh cli tests/cli/test_recompute_memberships.py`.
3. `uv run pytest -m perf tests/worker/test_expirations.py -q` (fuera del gate; tiempo al cuaderno).
4. Al final, para sellar: `slice-gate.sh worker tests/worker/test_expirations.py tests/worker/test_main.py tests/worker/test_runner.py`.

**Paso 36 · B2.8 · `run-gates.sh` (C12)**
`bash scripts/workflow/run-gates.sh` con el front y el navegador cerrados: api con `--cov` global ≥ 80 % ya sin `omit` (se anota el porcentaje real y las líneas sin cubrir de `cli.py` y `worker/`), scripts de infraestructura, web lint, tsc, pruebas con cobertura y build. Si la cobertura baja de 80 %, es un gate fallido: se agregan pruebas en `tests/worker` o `tests/cli` dentro del slice (vuelve a B2.3), nunca se restaura el `omit`.

**Paso 37 · B2.9 · Docker y evidencia (demo 2)**
1. `$DC restart worker` (código nuevo por bind); `healthy`.
2. Corrida real sin fecha: psql de lectura antes (`SELECT count(*) FROM audit.audit_log`, `SELECT status, count(*) FROM memberships.memberships GROUP BY 1`); `$DC run --rm worker python -m app.worker.main --run-once expirations` → 0; psql después: las filas `update` nuevas de `audit.audit_log` con `user_id = '00000000-0000-0000-0000-000000000001'` y los `status` corregidos (la base tenía `active` vencidas); segunda corrida → 0 y `count(*)` de `audit.audit_log` sin cambio; `--status expirations` muestra la misma fila con dos intentos.
3. Demo con fecha (S4A-D63): `$DC exec -T db pg_dump -U apex -Fc apex > docs/scratch/sprint-04a-sim.dump && chmod 600 ...`; `$DC exec -T db_test createdb -U apex apex_sim`; `cat docs/scratch/sprint-04a-sim.dump | $DC exec -T db_test pg_restore -U apex -d apex_sim --no-owner --no-privileges`; en la shell `export DATABASE_URL=postgresql+asyncpg://apex:apex-test@db_test:5432/apex_sim` (contraseña pública de `compose.dev.yml`); `$DC run --rm -e DATABASE_URL worker python -m app.worker.main --run-once expirations --date 2026-11-01 --simulate` → `RELOJ SIMULADO: 2026-11-01` y 0; `--status expirations_sim` con la misma `DATABASE_URL`; psql de lectura sobre `apex_sim` (puerto 5443): membresías pasadas a `expiring` y `expired` según la fecha; `unset DATABASE_URL`; `$DC exec -T db_test dropdb -U apex apex_sim`; `rm docs/scratch/sprint-04a-sim.dump`. `apex-db-1` no recibe ninguna corrida con fecha.
4. `$DC logs --tail 50 worker` y `api` sin nombres ni documentos (grep de los valores de prueba de V3 del Sprint 3).

**Paso 38 · B2.10 · Checkpoint**
`checkpoint-commit.sh "S4A-B2 job diario de vencimientos, eventos de transición y recompute-memberships"`; después `docs(sprint-04a): evidencia de S4A-B2`.

### S4A-B3 · Verificar la cadena desde la API y desde la CLI

- **Historias:** US-104 y US-105.
- **Depende de:** B2 (orden de la rama; `0013` cuelga de `0012`).
- **Migración:** `0013_audit_verifications` (`down_revision = "0012_worker_job_runs"`), con volcado previo.
- **Cierra:** C4, C11 (resto), C12 (segundo `run-gates.sh`); **H-1 (S4A-D43), H-2 (S4A-D44)**, M-1 (parte: cubeta `staff-read` nace), M-3 (S4A-D47), L-2 (S4A-D53 en `verify-audit`); S4A-D11, D12, D13, D14, D15, D18 (`verify.py`), D26 (cubetas), D38, D65, D69, D70.

**Paso 39 · B3.1 · Volcado previo a `0013`**
`$DC exec -T db pg_dump -U apex -Fc apex > docs/scratch/sprint-04a-antes-0013.dump && chmod 600 ...`; `$DC stop api` (P-MIG paso 2).

**Paso 40 · B3.2 · Stubs**
- `core/audit.py`: `verify_chain(rows, *, start_prev_hash=ZERO_HASH, start_seq=1)` y `VerifyResult` con `last_seq: int | None = None` y `last_hash: str | None = None` al final.
- `core/audit_verify.py` (nuevo): `AuditVerification(CommonColumnsMixin, Base)` (esquema `audit`, tabla `verifications`, columnas de S4A-D38 más `through_hash`), `VERIFY_BATCH_SIZE = 1000`, `VERIFY_MAX_SECONDS = 900`, `AUDIT_VERIFY_LOCK_KEY: Final[int] = 4_270_003`, `TRY_LOCK_SQL`, `UNLOCK_SQL` (constantes de módulo), `VerificationView`, `async run_verification(session, *, source, by) -> AuditVerification`, `format_verify_message(result) -> tuple[str, int]`, `_anchor(session)`, `_scan_chain(session, through_seq)`, `_check_anchor(...)`, `_persist(...)`.
- `audit/verify.py` (privado): `SYNC_VERIFY_MAX_ROWS = 50_000`, `_BACKGROUND_TASKS: set[asyncio.Task[None]]`, `async acquire_verify_lock() -> AsyncConnection | None` (conexión `AUTOCOMMIT`), `async release_verify_lock(conn)` (`unlock` y `invalidate()` en `finally`), `Finished(result)`, `Started(last)`, `async verify(session, *, by) -> Finished | Started`, `async last_verification(session) -> VerificationView | None`, `cancel_background_verifications()` (lo llama el `shutdown` del lifespan de `main.py`).
- `audit/schemas.py`: `VerifyResultOut`, `VerifyStartedOut`. `audit/exceptions.py`: `AuditError(DomainError)`, `VerificationRunning` (409 `verification_running`). `audit/router.py`: `APIRouter(tags=["audit"], dependencies=[Depends(no_store)], responses=responses_for(401, 403))`, `GET /audit/verify/last` y `POST /audit/verify` (`AdminDep`; `enforce_user_limit(request, "audit-verify", ...)` y `enforce_user_limit(request, "audit-verify-hour", ...)`; `responses={**responses_for(409, 429), 202: {"model": VerifyStartedOut}}`). `audit/service.py`: re-exporta `verify`, `last_verification`, `cancel_background_verifications`.
- `core/config.py`: `USER_READ_LIMIT_PER_MIN: int = Field(default=120, gt=0)`, `USER_AUDIT_VERIFY_LIMIT_PER_MIN: int = Field(default=3, gt=0)`, `USER_AUDIT_VERIFY_LIMIT_PER_HOUR: int = Field(default=20, gt=0)`. `core/ratelimit.py`: `USER_LIMITS` gana `"staff-read": (120, 60)`, `"audit-verify": (3, 60)`, `"audit-verify-hour": (20, 3600)`; `user_limits_from` las lee.
- `cli.py`: comando `verify-audit [--as] [--wait-timeout 300]`.
- `main.py`: el `lifespan` llama `audit.service.cancel_background_verifications()` en el `shutdown`.
- `migrations/env.py`: `from app.core import audit_verify  # noqa: F401`.
- `tests/architecture/_imports.py`: `PRIVATE_HELPERS["audit"] = frozenset({"verify"})`.

**Paso 41 · B3.3 · Fixtures y limpieza**
`tests/factories/audit_chain.py` (S4A-D69), `tests/audit/conftest.py` (sección 2), `LIMPIAR_VERIFICATIONS` antes de `audit.audit_log` en las tres limpiezas de `tests/conftest.py` (S4A-D70), `tests/cli/conftest.py::settings_produccion`. `uv run pytest tests/audit tests/core/test_audit_chain.py -q`: las existentes siguen verdes.

**Paso 42 · B3.4 · Rojo de arquitectura (C4)**
- `tests/architecture/test_audit_module.py::test_audit_tiene_router_vacio_y_no_tiene_models` → `test_audit_publica_verify_y_sigue_sin_models`: las rutas son exactamente `POST /audit/verify` y `GET /audit/verify/last`; sin `models.py`; el router lleva `no_store`.
- `tests/architecture/test_audited_tables.py`: `EXCLUIDAS` gana `"audit.verifications": "su resultado entra a la cadena como fila verify (N-30, S4A-D12)"`; `_cargar_modelos` importa `app.core.audit_verify`.
- `tests/architecture/test_no_physical_delete.py`: `MODELOS` suma `AuditVerification`, `TABLAS` suma `audit.verifications` (S4A-D74).
- `tests/architecture/test_sql_literals_constant.py`: `AUDIT_VERIFY_LOCK_KEY == 4_270_003` y distinta de las otras dos.
- `tests/architecture/test_guarded_calls.py`: la regla L-11 (sin `isolation_level` en `execution_options`) gana la excepción única `core/audit_verify.py` y `modules/audit/verify.py` (S4A-D44) y un control de que cualquier otro archivo sigue fallando.
- `tests/architecture/test_error_codes_per_route.py`: `CON_LIMITE` suma `("post", "/api/v1/audit/verify")`; `test_user_limits_catalog.py`: las pendientes ganan `staff-read` (hasta B4); `test_writes_have_user_limit.py` la ve.
- `tests/core/test_config.py` y `tests/core/test_env_example.py`: las tres variables nuevas (defaults, `gt=0`, "van activas con sus valores"); `tests/core/test_ratelimit.py`: `user_limits_from` devuelve 12 cubetas y `audit-verify-hour` conserva la ventana de 3.600 s.
- `tests/migrations/test_0012_worker_job_runs.py`: de head a cadena; `test_triggers_siempre_activos.py`: tupla de `verifications` (`verifications_forbid_mutation`, `verifications_forbid_truncate`).
- `tests/core/test_audit_chain.py`: sin cambio (sus 11 pruebas con construcciones posicionales deben seguir verdes con la firma ampliada).

**Paso 43 · B3.5 · Rojo de `core/audit`, `core/audit_verify`, `audit` y `cli`**
- `tests/core/test_verify_chain.py` (puras): cadena vacía, una fila, íntegra de 50, fila 1 alterada, del medio, última, fila borrada (el `seq` siguiente es el reportado), `prev_hash` manipulado, columna espejo distinta, dos lotes con `start_prev_hash` y `start_seq` igual a una vez, `last_seq`/`last_hash` de la última fila o `None`.
- `tests/core/test_format_verify_message.py`: íntegra (texto y código 0), íntegra primera vez ("sin verificación anterior que comparar"), rota en el seq 42 (texto y código 1), rota por ancla.
- `tests/audit/test_verify.py` (base real, `audit_chain_factory`): 5.000 filas → `ok`, `rows_checked = 5000`, `through_hash` igual al `hash` de la última; fila 1234 alterada → `broken_at_seq = 1235`; **H-1:** verificar (ok), `drop_tail(3)`, verificar de nuevo → `ok = false` con `broken_at_seq = min(last_seq + 1, ancla.through_seq)`; cola reemplazada por una cadena internamente válida pero distinta (`tamper_row` sobre `ancla.through_seq` y recálculo de hashes posteriores) → `ok = false`; primera verificación sin ancla → `ok` y mensaje de "sin verificación anterior"; una verificación rota no mueve el ancla (la siguiente compara contra la última `ok`); cada verificación deja una fila en `audit.verifications` y una entrada `verify` con `table_name = "audit.verifications"` y `after` con `through_hash` que entra a la cadena (la siguiente sigue íntegra); una transacción auditada revertida no deja huecos; `table_digest` igual antes y después; `UPDATE`, `DELETE` y `TRUNCATE` sobre `audit.verifications` rechazados; `logger.info("audit anchor")` con `through_seq` y `through_hash` en `caplog` y sin `before`/`after`; con `VERIFY_BATCH_SIZE = 1000` una cadena de 2.500 filas hace tres lotes (`contador_de_consultas`).
- `tests/audit/test_verify_concurrency.py` (`dos_sesiones`, `candado_tomado`, `umbral_bajo`, `plazo_corto`): con el candado tomado por otra conexión `verify` lanza `VerificationRunning`; con el umbral bajado devuelve `Started`, la tarea termina, deja la fila y libera el candado (también si falla por `monkeypatch`); **H-2:** con `DB_IDLE_IN_TX_TIMEOUT_MS = 2000` en el engine de prueba y una tarea que dura 5 s (sleep inyectado entre lotes), el candado sigue tomado y un segundo `verify` lanza `VerificationRunning` durante toda la corrida; tras un `unlock` que falla (`monkeypatch` que lanza) otra conexión obtiene el candado (la conexión fue invalidada, no devuelta al pool); con `plazo_corto` la tarea vence, no deja fila, libera el candado y registra solo el tipo; `cancel_background_verifications` cancela y libera.
- `tests/audit/test_verify_performance.py` (`perf`): 100.000 filas con lote de 1.000: tiempo total (< 60 s) y el máximo bloque síncrono por lote (< 100 ms, medido con un hook en `sleep(0)`); la medida decide `SYNC_VERIFY_MAX_ROWS` (contradicción 3).
- `tests/audit/test_router_verify.py` (`app_http`): 200 admin con `VerifyResultOut`; 202 con `umbral_bajo` y `VerifyStartedOut {status: "running", last}`; 409 `verification_running`; **429 a la 4.ª petición del minuto** y, con `reloj.advance(minutes=1)` por tanda, 429 a la 21.ª de la hora; `GET /audit/verify/last` con y sin verificaciones (200 `null`) y sin 429; 403 coach; 401; el 202 y el 429 aparecen en el OpenAPI de la ruta; `GET /audit/verify/last` no cae en `{seq}` (aún no existe, se afirma 404 de FastAPI para `/audit/99`).
- `tests/cli/test_verify_audit.py` (`CliRunner`): íntegra da 0 y el texto; fila 42 alterada da 1; la entrada `verify` lleva `user_id = SYSTEM_USER_ID` y `after.source = "cli"`; con `--as` la entrada y `triggered_by` llevan ese usuario; `--as` inexistente da 2; base caída (`DATABASE_URL` a un puerto cerrado por `monkeypatch`) da 2 sin la URL en la salida; `--wait-timeout 1` con el candado tomado da 2; con `settings_produccion` sin `--as` da 2; con `settings_produccion` y `--db-timeouts off` da 2; la salida no contiene ningún valor de `before` ni `after`; la conexión del candado de la CLI también es `AUTOCOMMIT` e invalidada (espía).
- `tests/migrations/test_0013_audit_verifications.py`: columnas y nulabilidad (incluida `through_hash`); CHECKs con SQL crudo (`through_seq >= 0`, `rows_checked >= 0`, `source IN ('api','cli')`, `ok` sin `broken_at_seq` y no `ok` con él, `started_at <= finished_at`, `through_hash ~ '^[0-9a-f]{64}$'`); índice `ix_verifications_finished_at`; `UPDATE`, `DELETE` y `TRUNCATE` rechazados; triggers con `tgenabled = 'A'`; `tgfoid` igual a `audit.forbid_mutation`; siguen disparando bajo `session_replication_role = replica`; `down_revision == "0012_worker_job_runs"`; `downgrade` quita triggers, índice y tabla y conserva `audit.forbid_mutation()`.
- Confirmar el rojo.

**Paso 44 · B3.6 · Migración `0013` (P-MIG pasos 3 a 5)**
`database-reviewer` revisa antes de probar. Tabla `audit.verifications` (S4A-D38 + `through_hash char(64) NOT NULL`), CHECKs, índice `ix_verifications_finished_at (finished_at DESC)`, triggers `verifications_forbid_mutation BEFORE UPDATE OR DELETE FOR EACH ROW` y `verifications_forbid_truncate BEFORE TRUNCATE FOR EACH STATEMENT` sobre `audit.forbid_mutation()` existente, con `ALTER TABLE audit.verifications ENABLE ALWAYS TRIGGER <nombre>`; `downgrade` simétrico sin tocar la función. `pytest tests/core/test_migrations.py tests/migrations/test_0013_audit_verifications.py tests/migrations/test_0012_worker_job_runs.py -q`; `alembic heads` una.

**Paso 45 · B3.7 · Verde de `core`**
`core/audit.py` (firma ampliada). `core/audit_verify.py` (S4A-D12, D43, D47): `run_verification` = `started_at`, `through_seq = max(seq)`, `_anchor` (última `ok`), `_scan_chain` por lotes de 1.000 con `verify_chain(lote, start_prev_hash=..., start_seq=...)` y `await asyncio.sleep(0)` entre lotes, parada en la primera ruptura, `_check_anchor` (existencia y hash de `ancla.through_seq`, `max(seq) >= ancla.through_seq`), `through_hash` de la fila `through_seq` (o `ZERO_HASH`), `_persist` (fila + `audit.record(action="verify", table_name="audit.verifications", record_id=v.id, before=None, after={ok, rows_checked, broken_at_seq, through_seq, through_hash, started_at, finished_at, source}, user_id=by)`), `logger.info("audit anchor", ...)` si `ok`. Cada función de menos de 50 líneas.

**Paso 46 · B3.8 · Verde de `audit`, router, cubetas y CI (S4A-D65)**
`audit/verify.py` (S4A-D13, D44, D47: `acquire_verify_lock` con `db.get_engine().connect()` y `execution_options(isolation_level="AUTOCOMMIT")`, `TRY_LOCK_SQL`; `verify` toma el candado antes de responder, decide por `max(seq) <= SYNC_VERIFY_MAX_ROWS`, tarea con `asyncio.timeout(VERIFY_MAX_SECONDS)` y su propia sesión, `finally` que libera e invalida y registra solo el tipo, `_BACKGROUND_TASKS.add` y `discard`), `audit/schemas.py`, `exceptions.py`, `router.py`, `service.py`. `core/config.py`, `core/ratelimit.py`, `.env.example` (tres líneas activas con comentario "S4A-B3, M-1 y M-3"), `main.py` (`shutdown`). `.github/workflows/ci.yml`, job `e2e-stack`: el `sed` gana `-e 's/^USER_READ_LIMIT_PER_MIN=.*/USER_READ_LIMIT_PER_MIN=12000/' -e 's/^USER_AUDIT_VERIFY_LIMIT_PER_MIN=.*/USER_AUDIT_VERIFY_LIMIT_PER_MIN=300/' -e 's/^USER_AUDIT_VERIFY_LIMIT_PER_HOUR=.*/USER_AUDIT_VERIFY_LIMIT_PER_HOUR=2000/'`, el `grep -cE` las incluye y el conteo pasa de `8` a `11` (el mensaje "se esperaban 8 cubetas" también). `tests/conftest.py::app_http` sigue tomando `user_limits_from(settings_prueba)`.

**Paso 47 · B3.9 · Verde de `cli`**
`verify-audit` (S4A-D15, D44, D53): `cli_runtime`, `resolve_actor`, bucle de `pg_try_advisory_lock` cada 2 s hasta `--wait-timeout` en una conexión `AUTOCOMMIT` que se invalida en `finally`, `run_verification(session, source="cli", by=actor)` bajo `unit_of_work(actor)`, `format_verify_message`, códigos 0/1/2, guardas de producción. Medir `cli.py` (S4A-D72).

**Paso 48 · B3.10 · Documentación**
RUNBOOK §6 (`0013`: `downgrade 0012_worker_job_runs` quita triggers, índice y tabla; las filas `verify` de la cadena quedan), §11 (`verify-audit`, candado `4_270_003` y qué hacer si queda tomado: la conexión se invalida sola; el ancla y la línea `audit anchor`, que se copia junto al respaldo; códigos de salida; 202 y sondeo; `VERIFY_MAX_SECONDS`; cubetas `audit-verify`). `DECISIONES.md`: residual de S4A-D43 (sin firma externa hasta v0.3) y el valor calibrado de `SYNC_VERIFY_MAX_ROWS`. `SPRINT-04A.md`: cubetas y `through_hash`.

**Paso 49 · B3.11 · Contrato**
P-API (primeras rutas de `audit`; `types.ts` cambia). `errorCodes.ts` no se toca aquí (F1).

**Paso 50 · B3.12 · Gate**
1. `slice-gate.sh core/audit tests/core/test_audit_chain.py tests/core/test_verify_chain.py tests/core/test_audit_log_db.py tests/core/test_audit_concurrency.py`.
2. `slice-gate.sh core/audit_verify tests/core/test_verify_chain.py tests/core/test_format_verify_message.py tests/audit/test_verify.py`.
3. `slice-gate.sh core/config tests/core/test_config.py tests/core/test_env_example.py`; `slice-gate.sh core/ratelimit tests/core/test_ratelimit.py`.
4. `slice-gate.sh architecture tests/core/test_migrations.py tests/migrations/test_0013_audit_verifications.py tests/migrations/test_0012_worker_job_runs.py tests/migrations/test_triggers_siempre_activos.py tests/architecture/test_audit_module.py tests/architecture/test_audited_tables.py tests/architecture/test_no_physical_delete.py tests/architecture/test_sql_literals_constant.py tests/architecture/test_guarded_calls.py tests/architecture/test_user_limits_catalog.py tests/architecture/test_writes_have_user_limit.py`.
5. `slice-gate.sh main tests/core/test_health.py tests/core/test_startup_failure.py` (el `shutdown` nuevo del lifespan).
6. `slice-gate.sh cli tests/cli/test_verify_audit.py tests/cli/test_db_timeouts_cli.py`.
7. Corrida conjunta: `cd api && uv run pytest tests/audit tests/migrations -q -m "not perf"`.
8. `uv run pytest -m perf tests/audit/test_verify_performance.py -q` (fuera del gate; decide el umbral; si cambia la constante se vuelve a B3.8 y al gate 2).
9. `security-reviewer` de B3 (H-1 y H-2 cerrados: ancla, `AUTOCOMMIT`, `invalidate`, plazo, cancelación, cubetas; nada de `before`/`after` en la CLI ni en los logs).
10. Al final, para sellar: `slice-gate.sh audit tests/audit/test_verify.py tests/audit/test_verify_concurrency.py tests/audit/test_router_verify.py tests/migrations/test_0013_audit_verifications.py`.

**Paso 51 · B3.13 · `run-gates.sh` (C12)**
`bash scripts/workflow/run-gates.sh` (front y navegador cerrados): cobertura global sin `omit` con `verify-audit` dentro; porcentaje al cuaderno.

**Paso 52 · B3.14 · Docker, evidencia y la parada del sprint (P-MIG pasos 6 a 8)**
1. `$DC start api`; `healthy`; `alembic current` = `0013_audit_verifications (head)`; ciclo `downgrade -1` → `upgrade head` → `current`; `psql -c '\d audit.verifications'` al cuaderno (columnas, CHECKs, los dos triggers con `ENABLE ALWAYS`); `$DC up -d api` tras `.env` (las tres variables tienen default: `.env` local no cambia salvo que se quiera; se deja igual).
2. Smoke del endpoint: con el admin desechable (S4A-D71, creado aquí si no existe), `POST http://127.0.0.1:8181/api/v1/audit/verify` → 200 `VerifyResultOut`; `GET /audit/verify/last` igual; cuarta llamada en el minuto → 429.
3. **Primera verificación con datos reales (riesgo 2 del blueprint):** `$DC run --rm tools verify-audit --as <E2E_ADMIN_EMAIL>` sobre `apex-db-1` (4.504 filas más las del job de B2 y la del punto 2): esperado "Cadena íntegra" y código 0, con `triggered_by` del admin desechable. **Si da "rota", el sprint se detiene** con contexto (seq roto, hash esperado y hallado) y opciones: es un hallazgo de la cadena real, no del código nuevo.
4. psql de lectura: `SELECT ok, rows_checked, through_seq, left(through_hash, 12), source FROM audit.verifications ORDER BY finished_at`; `SELECT action, table_name FROM audit.audit_log ORDER BY seq DESC LIMIT 3` muestra las filas `verify`; `$DC logs api | grep "audit anchor"` muestra la línea sin `before`/`after`.

**Paso 53 · B3.15 · Checkpoint**
`checkpoint-commit.sh "S4A-B3 verificación de la cadena con ancla, migración 0013, API y verify-audit"`; después `docs(sprint-04a): evidencia de S4A-B3`.

### S4A-B4 · Consultar la auditoría y ver el detalle

- **Historias:** US-102 y US-103.
- **Depende de:** B3 (`PRIVATE_HELPERS["audit"]`, router, `audit_chain_factory`).
- **Migración:** ninguna (no hay `0014_audit_indexes`: los cinco índices existen).
- **Cierra:** C5, C9 (parte: `user_names_for`/`user_refs_for`); M-1 (S4A-D45 en las dos lecturas), M-2 (S4A-D46), L-1 (S4A-D52), L-3 (S4A-D54), L-10 (S4A-D61 parte `settings`); S4A-D16, D17, D18 (`queries`, `diff`), D19, D66.

**Paso 54 · B4.1 · Stubs**
- `audit/queries.py` (privado): `AUDITABLE_TABLES` (constante única: `members.members`, `memberships.memberships`, `memberships.membership_freezes`, `payments.payments`, `plans.plans`, `auth.users`, `auth.one_time_tokens`, `settings.settings_sections`, `audit.verifications`), `AuditFilters` (dataclass congelada), `build_audit_filters(...)` (pura), `async list(session, filters, page) -> Page[AuditRow]`, `async get(session, seq) -> AuditDetail`; `audit/diff.py` (puras): `FieldChange`, `diff(before, after, action)`, `blob_marker(value)`, `redact_blobs(mapping)`; `audit/schemas.py`: `AuditRow`, `AuditDetail`, `FieldChange`, `AuditListQuery` (`from`/`to` con alias, `user_id`, `table` con patrón y `max_length=127`, `record_id`, `subject_member_id`, `action: Literal[AUDIT_ACTIONS]`), `MAX_AUDIT_OFFSET = 100_000`, `MAX_SEQ = 2**63 - 1`; `audit/exceptions.py`: `AuditEntryNotFound` (404 `audit_entry_not_found`), `AuditRangeInvalid` (422 con `field`); `audit/router.py`: `GET /audit` (`AdminDep`, `enforce_user_limit(request, "staff-read", ...)`, `Annotated[PageParams, Depends()]`, `q: SearchQuery = None`, `responses_for(422, 429)`) y `GET /audit/{seq}` (`seq: Annotated[int, Path(ge=1, le=MAX_SEQ)]`, `staff-read`, `responses_for(404, 422, 429)`) **después** de `/audit/verify/last`.
- `auth/schemas.py`: `UserRef(id, email, display_name)` (dataclass congelada); `auth/users.py` y `service.py`: `user_names_for(session, user_ids) -> dict[UUID, str]`, `user_refs_for(session, user_ids) -> dict[UUID, UserRef]`, `search_user_ids(session, term, *, local_part_only=False, limit=200) -> set[UUID]`.
- `core/validators.py`: `INSTANT_FLOOR`, `instant_ceiling(now)`, `check_instant_range(start, end, *, now, field_start, field_end) -> None` (lanza `ValueError` con el campo; el módulo lo traduce a `AuditRangeInvalid`).
- `tests/architecture/_imports.py`: `PRIVATE_HELPERS["audit"] = frozenset({"verify", "queries", "diff"})`.

**Paso 55 · B4.2 · Rojo de arquitectura (C5)**
- `test_audit_module.py`: las rutas de `audit` pasan a las cuatro; `test_audit_no_importa_models_router_ni_helpers_de_otros_modulos` sigue (`AuditEntry` viene de `core.audit`, permitido; `auth.models` no).
- `test_no_cross_models.py`: caso exacto `PRIVATE_HELPERS["audit"] == {"verify", "queries", "diff"}` y los tres archivos existen.
- `test_error_codes_per_route.py`: `CON_LIMITE` suma `("get", "/api/v1/audit")` y `("get", "/api/v1/audit/{seq}")`; el 422 de ambas se declara.
- `test_user_limits_catalog.py`: `staff-read` sale de las pendientes.
- `test_list_routes_use_page_params.py`: sin cambio de conjuntos (`GET /audit` cumple `PageParams`, `q`, `limit ≤ 200`).
- Nueva `tests/architecture/test_user_refs_scope.py` (S4A-D54): por AST, `app/modules/members/**` y `app/modules/dashboard/**` (cuando exista) no referencian `user_refs_for` ni el atributo `.email` de un `UserRef`; `audit` sí puede.
- `tests/architecture/test_settings_no_secrets.py`: caso nuevo "ningún esquema de sección registrado en `SECTION_REGISTRY` tiene un campo cuyo nombre contenga `token`, `secret` o `password`" (S4A-D61 a).
- `tests/core/test_validators.py`: `check_instant_range` (piso, techo `now + 1 día`, invertido, iguales, zona obligatoria) y `PAID_AT_FLOOR == INSTANT_FLOOR` (S4A-D66).

**Paso 56 · B4.3 · Rojo de `audit` y `auth`**
- `tests/audit/test_filters.py` (puras): `build_audit_filters` por cada filtro; `q` UUID → `record_id`; `q` texto → término de correo; rango `[from, to)`; `from = 0001-01-01T00:00:00+05:00`, `to = 9999-12-31`, invertido, `from == to` → `AuditRangeInvalid` con `field`; `table` con mayúsculas, tres segmentos o 128 caracteres → 422; `offset = 100_001` → 422 `field="offset"`; `blob_marker("apx1.<uuid>.A256GCM.n.c")` da `{"encrypted": True, "key_id": "<uuid>", "alg": "A256GCM"}`, texto sin prefijo y malformado dan `None`; paridad del prefijo y del separador con `core/crypto/types` (la prueba importa `types`).
- `tests/audit/test_list.py` (`sembrar_actividad`): cada filtro (`table` con `esquema.tabla`, `subject_member_id`, `user_id`, `record_id`, `action`, rango); orden `seq DESC`; paginación y `total`; `q` por `record_id` y por correo parcial sin distinguir mayúsculas ni tildes; filas sin `before` ni `after`; `user_name` = parte local y `Sistema`; la consulta no modifica `audit_log` (conteo y `table_digest` iguales); con `offset = 100_000` responde 200 vacío.
- `tests/audit/test_list_coverage_v01.py`: una fila en `members`, `plans`, `memberships`, `payments`, `users` y `settings` por sus services y cada `insert` aparece con usuario y fecha; `audit.verifications` aparece tras `verify`.
- `tests/audit/test_list_performance.py` (`perf`): 100.000 filas, `limit=25`, menos de 500 ms con y sin filtros de tabla y usuario; `count(*)` medido aparte (si falla, `max(seq)` sin filtros, S4A-D16).
- `tests/audit/test_diff.py`: insert (todo `added`), update sin cambios (lista vacía), update con dos campos, delete (todo `removed`), campo que pasa a `null`, reveal con `after.field`, verify y login sobre `after`; `encrypted` verdadero para valores `apx1.` y el valor sustituido por el marcador (S4A-D52); orden estable por nombre.
- `tests/audit/test_get.py`: socio creado y editado (teléfono y correo) por el service real: `changes` con `phone` y `email` marcados `encrypted`; `before.phone` es el marcador con `key_id` y la respuesta serializada completa no contiene `apx1.` ni el teléfono en claro; los `_idx` llegan como `***`; el service no llama al bus (espía sobre `types.reveal` y `bus.decrypt`); `seq` inexistente → `AuditEntryNotFound`; `seq = 2**63` → 422 en el router, nunca 500.
- `tests/audit/test_router_list.py` y `test_router_get.py`: 200 admin; 403 coach y member; 401; 422 (`action` desconocida, `limit` 201, `offset` 100.001, `from` extremo, `table` con mayúsculas, `seq` no numérico, 0 o `2**63`); 404; `/audit/verify/last` no cae en `{seq}`; **la 121.ª lectura del minuto da 429** (`staff-read`) y la 121.ª de otro usuario pasa; `GET /audit/verify/last` nunca da 429.
- `tests/auth/test_user_refs.py`: `user_names_for` da la parte local y `Sistema` para `SYSTEM_USER_ID`; `user_refs_for` da además el correo; `search_user_ids` es parcial, sin mayúsculas ni tildes, escapa `%` y `_`, y con `local_part_only=True` no coincide con el dominio; `names_for` e `ids_by_email` no cambian (prueba de regresión con las mismas entradas).
- Confirmar el rojo.

**Paso 57 · B4.4 · Verde de `auth` y `core/validators`**
`search_user_ids` con `ILIKE`, `core.search.clean_query` y `contains_pattern`, valor ligado; `user_names_for` y `user_refs_for` por lote con `chunked`; `UserRef`. `core/validators.py` con `check_instant_range` (sin `datetime` extremos: compara contra `INSTANT_FLOOR` y `instant_ceiling(now)` antes de convertir).

**Paso 58 · B4.5 · Verde de `audit`**
`queries.list` (`select(AuditEntry)` con los filtros, `ORDER BY seq DESC`, `paginate`; nombres por `auth.service.user_refs_for`; `q` por `search_user_ids`), `queries.get` (todas las columnas; `diff`; `redact_blobs` sobre `before` y `after`), `diff.py` puro, router con `staff-read` y `MAX_AUDIT_OFFSET`. `audit` solo importa `auth.service`, `auth.schemas` y `core.*`.

**Paso 59 · B4.6 · Documentación**
`docs/design/ROUTES.md:89` ya corregida en W0-1 (se confirma). RUNBOOK §11: lectura de la auditoría (filtros, `q`, por qué no se audita la lectura, S4A-D61 c). `DECISIONES.md`: nada nuevo.

**Paso 60 · B4.7 · Contrato**
P-API.

**Paso 61 · B4.8 · Gate**
1. `slice-gate.sh auth tests/auth/test_user_refs.py`.
2. `slice-gate.sh core/validators tests/core/test_validators.py`.
3. `slice-gate.sh architecture tests/architecture/test_user_refs_scope.py tests/architecture/test_settings_no_secrets.py tests/architecture/test_audit_module.py tests/architecture/test_error_codes_per_route.py tests/architecture/test_user_limits_catalog.py tests/architecture/test_list_routes_use_page_params.py`.
4. `uv run pytest -m perf tests/audit/test_list_performance.py -q` (fuera del gate).
5. `security-reviewer` de B4 (marcador de blobs, rangos, `staff-read`, `search_user_ids` sin `text()` dinámico, `user_refs_for` solo en `audit`).
6. Al final, para sellar: `slice-gate.sh audit tests/audit/test_filters.py tests/audit/test_list.py tests/audit/test_list_coverage_v01.py tests/audit/test_diff.py tests/audit/test_get.py tests/audit/test_router_list.py tests/audit/test_router_get.py tests/audit/test_router_verify.py`.

**Paso 62 · B4.9 · Docker y evidencia (demo 3, lista y detalle)**
Por 8181 con el admin desechable: `GET /api/v1/audit?table=memberships.memberships&limit=5` (las filas `update` del job de B2 con `user_name = "Sistema"`); `GET /audit?user_id=<SYSTEM_USER_ID>`; `GET /audit/<seq de un update de members>` con `changes` y el marcador `encrypted` (sin `apx1.` en la respuesta: `grep -c apx1.` sobre el cuerpo = 0); `GET /audit?from=0001-01-01T00:00:00%2B05:00` → 422; `GET /audit/99999999999999999999` → 422.

**Paso 63 · B4.10 · Checkpoint**
`checkpoint-commit.sh "S4A-B4 lista y detalle de auditoría con filtros acotados, user_refs_for y search_user_ids"`; después `docs(sprint-04a): evidencia de S4A-B4`. **Tras este checkpoint arranca el worktree del front con F1 (sección 3).**

### S4A-B5 · Historial del socio

- **Historias:** US-106.
- **Depende de:** B4 (`diff`, `history_fields`, `user_names_for`).
- **Migración:** ninguna.
- **Cierra:** C6; M-1 (S4A-D45 en el historial), M-6 punto 3 (`purpose`), L-3 (S4A-D54 en `members`); S4A-D20.

**Paso 64 · B5.1 · Stubs**
`audit/queries.py`: `member_history(session, member_id, page, q) -> Page[MemberHistoryItem]`; `audit/diff.py`: `history_fields(entry) -> list[str]`, `history_purpose(entry) -> str | None`; `audit/schemas.py`: `MemberHistoryItem {seq, at, user_id, user_name, action, table_name, record_id, fields, purpose}`; `audit/service.py`: re-exporta `member_history`. `members/service.py`: `history(session, member_id, page, q)` con `from app.modules.audit import service as audit_service` al nivel del módulo; `members/router.py`: `GET /members/{member_id}/audit` (`StaffDep`, `enforce_user_limit(request, "staff-read", ...)`, `Annotated[PageParams, Depends()]`, `q: SearchQuery = None`, `responses_for(404, 422, 429)`).

**Paso 65 · B5.2 · Rojo de arquitectura (C6)**
- `test_service_import_graph.py`: `ALLOWED_EDGES` suma `("members", "audit")`; `test_el_par_perezoso_members_memberships_existe_y_esta_permitido` pasa de `arriba["members"] == set()` a `== {"audit"}` con `perezosas["members"] == {"memberships"}`; `test_cada_arista_permitida_existe` y el subproceso en los dos órdenes cubren el par; el grafo sigue acíclico (`audit -> auth`).
- `test_audited_tables.py:185`: `test_membership_freezes_es_requerida_y_no_declara_sujeto_hasta_us_106` → `..._por_decision_s4a_d20` (docstring con la decisión).
- `test_error_codes_per_route.py`: `CON_LIMITE` suma `("get", "/api/v1/members/{member_id}/audit")`.
- `test_list_rows_without_sensitive_fields.py`: sin cambio de código; barre la ruta nueva (`Page_MemberHistoryItem` sin `user_email` ni sufijos).
- `test_user_refs_scope.py`: `members` usa `user_names_for`, no `user_refs_for`.
- Nueva `tests/architecture/test_audit_subject.py`: `Member` (`id`), `Membership` y `Payment` (`member_id`) declaran `__audit_subject__` y el atributo existe; `MembershipFreeze` no; `modules/members/service.py` no importa `memberships.service` ni `payments.service` a nivel de módulo (solo la perezosa de la lista blanca).

**Paso 66 · B5.3 · Rojo**
- `tests/audit/test_history_fields.py`: insert y delete → lista vacía; update con teléfono y correo → sus nombres sin `_idx` ni técnicas (`updated_at`); reveal con `document` → `["document"]`, nunca `ip`; reveal con `purpose` → `history_purpose == "notify"`; `canonical` con y sin `subject_member_id` (sin la clave cuando es nula el hash es el de US-015).
- `tests/audit/test_member_history.py` (`sembrar_actividad`): entradas de `members.members`, `memberships.memberships` y `payments.payments` en orden descendente con el `subject_member_id` correcto; ninguna de otro socio; la respuesta serializada no contiene `apx1.`, `reference` ni `void_reason`; una congelación aparece por el `update` de la membresía; abrir la ficha no agrega entradas; un dado de baja devuelve su historial; `q` filtra por la parte local de quien actuó y no por el dominio; `purpose` es `null` en el `reveal` interactivo; la cadena sigue íntegra (`verify_chain`); `offset = 100_001` → `AuditRangeInvalid`.
- `tests/members/test_router_member_audit.py`: 200 coach y admin con el mismo cuerpo; 404 socio inexistente; 422 `limit=0`, 201 y `offset` 100.001; 403 member; 401; **la 121.ª lectura del minuto da 429** (`staff-read`, compartida con `GET /audit`: 60 aquí más 61 en `/audit` del mismo admin dan 429); el OpenAPI declara 429.
- Confirmar el rojo.

**Paso 67 · B5.4 · Verde**
`member_history` sobre `ix_audit_log_subject_member_seq` con `PageParams`, `q` por `search_user_ids(..., local_part_only=True)`, nombres por `user_names_for`; `history_fields` y `history_purpose` puras; `members.history` con `ensure_exists(member_id, include_deleted=True)`; ruta en `members/router.py`.

**Paso 68 · B5.5 · Documentación**
RUNBOOK §4 (historial de la ficha: qué ve el coach, `purpose`, por qué las congelaciones aparecen por la membresía). `docs/design/ROUTES.md`: la hija `/socios/:id/historial` la escribe F2.

**Paso 69 · B5.6 · Contrato**
P-API.

**Paso 70 · B5.7 · Gate**
1. `slice-gate.sh audit tests/audit/test_history_fields.py tests/audit/test_member_history.py`.
2. `slice-gate.sh architecture tests/architecture/test_service_import_graph.py tests/architecture/test_audited_tables.py tests/architecture/test_error_codes_per_route.py tests/architecture/test_list_rows_without_sensitive_fields.py tests/architecture/test_user_refs_scope.py`.
3. `security-reviewer` de B5 (mismo cuerpo para admin y coach; sin correo, IP ni valores; `q` acotado al socio).
4. Al final, para sellar: `slice-gate.sh members tests/members/test_router_member_audit.py tests/architecture/test_audit_subject.py tests/members/test_router_get.py`.

**Paso 71 · B5.8 · Docker y evidencia (demo 4, backend)**
Por 8181 con el coach de pruebas (`crearCoach` por API o el existente `@test.apex`): `GET /members/<socio de B2>/audit` → entradas de membresías del job con `user_name = "Sistema"` y `fields = ["status"]`; el cuerpo no contiene `@` (sin correos) ni `apx1.`; con el admin el cuerpo es idéntico.

**Paso 72 · B5.9 · Checkpoint**
`checkpoint-commit.sh "S4A-B5 historial del socio por subject_member_id con fields sin valores"`; después `docs(sprint-04a): evidencia de S4A-B5`.

### S4A-B6 · Contacto para avisos auditado

- **Historias:** US-077.
- **Depende de:** nada del sprint (solo `members`); se ejecuta tras B5 por orden de rama.
- **Migración:** ninguna (`OP_PURPOSES` ya trae `notify` y `auth_link`).
- **Cierra:** C7; M-6 (S4A-D50); S4A-D21.

**Paso 73 · B6.1 · Stubs**
`members/contact.py` (privado): `Contact(first_name, phone, email)` con `field(repr=False)` en teléfono y correo, `validate_purpose(purpose) -> Literal["notify", "auth_link"]`, `async contact_for_notification(session, member_id, purpose) -> Contact` (docstring con la regla de composición de S4A-D50); `members/exceptions.py`: `InvalidPurpose` (`MemberError`, `invalid_purpose`), `MemberNotContactable` (`MemberError`, `member_not_contactable`); `members/service.py` re-exporta los cuatro nombres. `tests/architecture/_imports.py`: `PRIVATE_HELPERS["members"]` suma `contact`. `tests/members/_apoyo.py`: `contar_crypto_ops`.

**Paso 74 · B6.2 · Rojo**
- `test_no_cross_models.py::test_los_privados_de_members_son_los_de_b9a`: conjunto exacto con `contact`.
- `tests/members/test_validate_purpose.py`: `notify` y `auth_link` válidos; `marketing`, `mask`, `reveal`, `export`, vacío y `None` → `InvalidPurpose`.
- `tests/members/test_service_contact.py` (`bus_listo`, `actor_scope(SYSTEM_USER_ID)`, `batch_scope`): devuelve teléfono y correo sembrados; dos filas `reveal` en la auditoría con `after == {"field": ..., "purpose": "notify"}`, `subject_member_id` y `user_id = SYSTEM_USER_ID`; dos filas `decrypt` en `crypto_ops` con `purpose = "notify"`, el `record_id` del socio y el mismo `batch_id`; propósito inválido no lee la base ni deja filas (espía sobre `session.execute`); socio dado de baja o inexistente → `MemberNotContactable` sin `decrypt`; correo vacío → `None` y una sola fila de cada tipo; con otro actor la fila lleva su `user_id`; `repr(contact)` y `str(contact)` no contienen el teléfono ni el correo; composición (S4A-D50): con un espía de candados, la llamada no pide `lock_member` ni `with_for_update`, y llamada después de `lock_member` del mismo socio en la misma transacción termina sin 55P03 con `dos_sesiones`; el rollback de la transacción borra las filas `reveal` pero no las `decrypt` (se documenta como la razón de "confirmar antes de enviar").
- `tests/architecture/test_crypto_bus_importers.py`: los importadores de `app.core.crypto.bus` y `app.core.crypto.types` fuera de `core/` son exactamente `modules/members/service.py`, `changes.py`, `detail.py` y `contact.py` (si `contact` importa `types`; si solo llama `_decrypt_fields`, no entra); lista blanca `app.core.*`, `app.modules.members.*`, y `athletes` y `attachments` cuando existan; control con una fuente falsa en `notifications` que debe fallar; `test_reveal_single_door.py` sigue verde.
- Nueva `tests/architecture/test_contact_callers.py` (S4A-D50): `CONTACT_CALLERS = frozenset()`; por AST, ninguna referencia a `contact_for_notification` en `app/` fuera de `modules/members/` (incluye `cli.py` y `worker/`), ni en ningún `router.py`; control con fuente falsa.
- Confirmar el rojo.

**Paso 75 · B6.3 · Verde**
Según S4A-D21: `validate_purpose` antes de leer; carga del socio con `deleted_at`; `detail._decrypt_fields(socio, ("phone", "email"), purpose)`; `audit.record(action="reveal", table_name="members.members", record_id=id, subject_member_id=id, after={"field": campo, "purpose": purpose})` por campo no nulo; sin `bus.batch`; sin `lock_member`. `members/service.py` solo re-exporta (sigue bajo 800).

**Paso 76 · B6.4 · Documentación**
RUNBOOK §4: `contact_for_notification` (quién puede llamarla en 4A: nadie; regla de composición; rastro en `crypto_ops` y auditoría; el Sprint 5 agrega `notifications.service` a `CONTACT_CALLERS`). `DECISIONES.md`: nada nuevo.

**Paso 77 · B6.5 · Gate**
1. `slice-gate.sh architecture tests/architecture/test_crypto_bus_importers.py tests/architecture/test_contact_callers.py tests/architecture/test_reveal_single_door.py tests/architecture/test_no_cross_models.py`.
2. `security-reviewer` de B6 (única puerta, propósito antes de leer, `repr`, llamadores vacíos).
3. Al final, para sellar: `slice-gate.sh members tests/members/test_validate_purpose.py tests/members/test_service_contact.py tests/architecture/test_crypto_bus_importers.py tests/architecture/test_contact_callers.py`.

**Paso 78 · B6.6 · Checkpoint**
`checkpoint-commit.sh "S4A-B6 contact_for_notification auditado por la única puerta de descifrado"` (sin evidencia Docker: nada lo llama en `src/`).

### S4A-B7 · Editar, activar o desactivar y dar de baja un plan

- **Historias:** US-080, US-081 y US-082.
- **Depende de:** `count_active_by_plan` (S3); por rama, B6.
- **Migración:** ninguna.
- **Cierra:** C8; L-9 (S4A-D60); S4A-D22, D23, D24, D25, D26 (planes con `admin-write`), D67, D72 (`plans/service.py`).

**Paso 79 · B7.1 · Stubs**
`plans/schemas.py`: `PlanPatch` (`extra="forbid"`, `str_strip_whitespace`, `name: SafeText | None` 1..80, `price_cop`, `duration_days`, `class_count` como `StrictInt | None` con los topes de `PlanCreate`, `kind`), `PlanState`, `PlanOut.active_members_count: int`; `plans/exceptions.py`: `PlanHasActiveMemberships(count)` (409 `plan_has_active_memberships`, mensaje "este plan tiene N membresías activas, desactívalo en su lugar"); `plans/service.py`: `merge_plan(current, patch) -> PlanState` (pura), `update(session, plan_id, patch) -> PlanOut`, `set_active(session, plan_id, active) -> PlanOut`, `deactivate_or_fail(session, plan_id) -> None`, `_out_with_counts(session, planes)`, eventos `PlanUpdated(plan_id, changed_fields)` y `PlanDeactivated(plan_id)` (`frozen=True, slots=True, kw_only=True`), `__all__`; `plans/router.py`: `PATCH /plans/{plan_id}` (200, `AdminDep`, `admin-write`, `responses_for(404, 409, 422, 429)`), `POST /plans/{plan_id}/activate` y `/deactivate` (200, `responses_for(404, 422, 429)`), `DELETE /plans/{plan_id}` (204, `responses_for(404, 409, 422, 429)`). `memberships/queries.py` y `service.py`: `counts_active_by_plans(session, plan_ids) -> dict[UUID, int]`. `tests/integration/__init__.py` y `conftest.py` (S4A-D67); `tests/plans/_apoyo.py::cuerpo_patch`.

**Paso 80 · B7.2 · Rojo de arquitectura (C8)**
- `test_service_import_graph.py:281-286`: `test_plans_no_importa_services_y_solo_memberships_lo_importa` → `arriba["plans"] == set()` y `perezosas["plans"] == {"memberships"}`; importadores de `plans.service` siguen `{"memberships"}` (B8 no lo cambia: `dashboard` no importa `plans`); caso nuevo: la perezosa vive en `plans/service.py`, lleva `# lazy: G-03 (plans -> memberships)` y `plans` no nombra `Membership` (`test_guarded_calls.py::test_fuera_de_memberships_nadie_nombra_membership` sigue).
- `test_error_codes_per_route.py`: `CON_LIMITE` suma las cuatro rutas de planes; el 422 por `{plan_id}` se declara; `DELETE` responde 204 y 409.
- `test_writes_have_user_limit.py` y `test_user_limits_catalog.py`: las ven por `CON_LIMITE`.
- `test_events_without_pii.py`: `PlanUpdated.changed_fields` son nombres; `PlanDeactivated` solo `plan_id`.
- `test_no_physical_delete.py`: ya cubre `plans.plans` (la baja es `update`).

**Paso 81 · B7.3 · Rojo de `plans`, `memberships` e integración**
- `tests/plans/test_merge_plan.py`: solo precio; a `classes` sin `class_count` (error `field="class_count"`); a `classes` con 12; a `days` sin `class_count: null` (error) y con `null` (válido); precio negativo (error); `model_fields_set` distingue no enviado de `null`.
- `tests/plans/test_service_update.py`: cambio de precio → una fila `update` con `price_cop` antes y después; `PlanUpdated` con nombres; PATCH sin cambios → sin auditoría ni evento (200); dado de baja → `PlanNotFound`; nombre repetido → `PlanNameDuplicated` con `existing_id`; dos renombres a la vez con `dos_sesiones` → uno gana y el otro 409 (sin 55P03 ni 40P01); `active_members_count` en la respuesta.
- `tests/integration/test_rn04_plan_price_change.py`: vende Mensual a 120.000 con `memberships.service.sell`, sube el plan a 135.000: `agreed_price_cop`, `end_date` y `classes_total` iguales; un `UPDATE` crudo del precio pactado lo rechaza `guard_identity` (23000); una venta posterior cobra 135.000 (S4A-D60).
- `tests/plans/test_service_set_active.py`: desactivar deja `is_active` falso, una fila `update` y `PlanDeactivated`; repetir no agrega auditoría ni evento; activar emite `PlanUpdated(("is_active",))`; dado de baja → `PlanNotFound`; el desactivado no sale en `GET /plans?active=true`. `tests/integration/test_plan_deactivation_with_memberships.py`: con cuatro membresías activas, desactivar no cambia su estado, precio ni fechas; vender con el plan inactivo → `PlanInactive` (422 `plan_inactive`).
- `tests/plans/test_service_deactivate_or_fail.py`: solo `expired` y `cancelled` → baja con `deleted_at` e `is_active` falso en **una** fila `update` y `PlanDeactivated` solo si estaba activo; con 12 `active` → `PlanHasActiveMemberships(12)` y el plan intacto; con una `pending_payment` bloquea (S4A-D24); con una `frozen` bloquea; baja repetida → `PlanNotFound`; el nombre queda libre para un plan nuevo; `get_including_deleted` conserva el nombre; carrera con una venta en vuelo (`dos_sesiones`: la baja espera el commit de la venta y después responde 409; si la baja gana, `sell` recibe `PlanInvalid`); el 409 solo lleva el conteo.
- `tests/memberships/test_counts_active_by_plans.py`: igual a `count_active_by_plan` plan por plan; plan sin ventas → 0; sin ids no consulta (`contador_de_consultas`); 450 ids en lotes de `ID_BATCH`.
- `tests/plans/test_router_update.py`, `test_router_set_active.py`, `test_router_delete.py`: 200, 204, 403 coach (plan intacto), 401, 404, 409 (`plan_name_duplicated` con `existing_id`, `plan_has_active_memberships`), 422 (`is_active` o `deleted_at` en el cuerpo, `class_count` incoherente, `price_cop` negativo o decimal, `plan_id` no UUID), la escritura 31 del minuto → 429 (`admin-write`, compartida con `POST /plans`), `no-store`.
- `tests/plans/test_service_list.py` y `test_router_list.py` (existentes): ganan `active_members_count` en cada fila y `create` devuelve 0.
- Confirmar el rojo.

**Paso 82 · B7.4 · Verde de `memberships`**
`counts_active_by_plans` con `GROUP BY plan_id`, `status_expr` y la exclusión de `cancelled`/`expired`, por trozos de `ID_BATCH`; re-exportada.

**Paso 83 · B7.5 · Verde de `plans`**
Según S4A-D22 a D25: `update` (`SELECT ... FOR UPDATE` del plan vivo, `merge_plan`, `validate_plan`, pre-chequeo de nombre y traducción de `uq_plans_name_alive`, `flush` solo con cambios, `PlanUpdated`), `set_active`, `deactivate_or_fail` (perezosa con `# lazy: G-03 (plans -> memberships)`, `count_active_by_plan`, un solo `flush`), `_out_with_counts` (perezosa, `counts_active_by_plans`) en `list`, `detail`, `update`, `set_active`; `create` devuelve 0. Medir `plans/service.py`: si pasa de 600, `plans/changes.py` (S4A-D72) y `PRIVATE_HELPERS["plans"]`.

**Paso 84 · B7.6 · Documentación**
`docs/design/ROUTES.md:39` ya corregida en W0-1 (se confirma; F4 ajusta el texto del front). `docs/BRECHAS.md` §11: casilla Activo, Descripción y Días para usarlas (ya listadas; se confirma el slice). RUNBOOK §5 (Planes): editar, activar o desactivar, dar de baja y la regla de `pending_payment`; §11: limpieza P2-1 por API (procedimiento: listar `E2E-tope-*` y los de las specs, anular sus `pending_payment` con `POST /memberships/{id}/cancel`, `DELETE /plans/{id}`, ritmo de 30/min). `DECISIONES.md`: S4A-D60 (precio vigente al vender, riesgo aceptado).

**Paso 85 · B7.7 · Contrato**
P-API con el paso 6 (`PlanOut.active_members_count`: `web/src/shared/data/plans.ts` `planRowSchema` gana `active_members_count: z.number().int().optional().default(0)` y se corre `npx vitest run src/shared/data/plans.test.ts src/features/plans/schemas.test.ts`).

**Paso 86 · B7.8 · Gate**
1. `slice-gate.sh memberships tests/memberships/test_counts_active_by_plans.py tests/memberships/test_sell_service.py`.
2. `slice-gate.sh architecture tests/architecture/test_service_import_graph.py tests/architecture/test_error_codes_per_route.py tests/architecture/test_writes_have_user_limit.py tests/architecture/test_user_limits_catalog.py tests/architecture/test_events_without_pii.py tests/architecture/test_guarded_calls.py`.
3. Al final, para sellar: `slice-gate.sh plans tests/plans/test_merge_plan.py tests/plans/test_service_update.py tests/plans/test_router_update.py tests/plans/test_service_set_active.py tests/plans/test_router_set_active.py tests/plans/test_service_deactivate_or_fail.py tests/plans/test_router_delete.py tests/plans/test_service_list.py tests/plans/test_router_list.py tests/integration/test_rn04_plan_price_change.py tests/integration/test_plan_deactivation_with_memberships.py`.

**Paso 87 · B7.9 · Docker y evidencia (demo 6, backend)**
Por 8181 con el admin desechable: crear un plan de prueba `S4A-demo-<epoch>`, vender a un socio de demo con `first_payment` completo, `PATCH` el precio a 135.000 → 200 y psql de lectura: `agreed_price_cop = 120000`; `POST .../deactivate` → 200 y una venta → 422 `plan_inactive`; `DELETE` → 409 `plan_has_active_memberships` con "1 membresía"; anular la membresía (`POST /memberships/{id}/cancel`) y `DELETE` → 204; `GET /plans?limit=1&active=true` y `active=false` con `total`. `GET /plans` muestra `active_members_count`.

**Paso 88 · B7.10 · Checkpoint**
`checkpoint-commit.sh "S4A-B7 editar, activar o desactivar y dar de baja planes con conteo por lote"`; después `docs(sprint-04a): evidencia de S4A-B7`.

### S4A-B8 · Tablero

- **Historias:** US-108 y US-110 (backend).
- **Depende de:** B4 (`recent` nace aquí sobre `audit/queries.py`, `user_names_for`), `memberships.summary`, `payments.summary`, `refs_for`.
- **Migración:** ninguna.
- **Cierra:** C9; M-1 (S4A-D45 en `GET /dashboard`), M-7 (S4A-D51), L-3 (S4A-D54 en `dashboard`), L-10 (S4A-D61 b); S4A-D27, D28, D29, D42 (reconstrucción al cerrar el backend).

**Paso 89 · B8.1 · Stubs**
`modules/dashboard/__init__.py`, `router.py` (`GET /dashboard`, `StaffDep`, `enforce_user_limit(request, "staff-read", ...)`, `responses_for(429)`), `schemas.py` (`DashboardOut`, `MovementOut`), `service.py` (`month_of`, `short_name`, `format_cop`, `movement_phrase`, `last_movements`, `summary`). `audit/queries.py`: `RECENT_TABLES_ALLOWED` derivada de `AUDITABLE_TABLES` menos `AUDIT_TABLES_EXCLUDED_FROM_RECENT` (`memberships.membership_freezes`: "aparece por el update de la membresía"; `auth.one_time_tokens`: "técnica"; `audit.verifications`: "es la verificación misma"), `recent(session, tables, limit, *, actions=("insert","update","delete"), exclude_user_ids=()) -> list[AuditEntryView]`; `audit/diff.py`: `reduce_entry(entry) -> AuditEntryView` con la lista blanca de llaves; `audit/schemas.py`: `AuditEntryView`; `audit/service.py`: re-exporta `recent`. `main.py`: `MODULES` suma `"dashboard"` al final. `tests/dashboard/__init__.py`, `_apoyo.py`, `conftest.py`.

**Paso 90 · B8.2 · Rojo de arquitectura (C9)**
- `test_audit_module.py:44-47`: la tupla pasa a ocho con `dashboard` al final; docstring.
- `test_service_import_graph.py`: `ALLOWED_EDGES` suma `("dashboard", "audit")`, `("dashboard", "auth")`, `("dashboard", "members")`, `("dashboard", "memberships")`, `("dashboard", "payments")`; cada una existe (`test_cada_arista_permitida_existe`); subproceso en los dos órdenes; `dashboard` no importa `plans` (los importadores de `plans.service` siguen `{"memberships"}`).
- `test_error_codes_per_route.py`: `CON_LIMITE` suma `("get", "/api/v1/dashboard")`; sin 422.
- `test_no_store_routes.py`, `test_session_scope.py`, `test_every_route_has_role.py`, `test_routes_under_api_v1.py`: cubren el router nuevo sin cambios.
- `test_handlers_no_new_locks.py`: `dashboard` no se suscribe a nada (sin cambio en `SUSCRIPTORES_ESPERADOS`).
- `test_user_refs_scope.py`: `dashboard` usa `user_names_for`.
- Nueva `tests/architecture/test_read_modules.py` (S4A-D28): `dashboard` no tiene `models.py`, no importa `app.modules.*.models`, `app.core.audit` ni `app.core.audit_verify`, y no contiene `session.execute(` (solo compone services); control con fuente falsa.
- Nueva prueba en `tests/architecture/test_audited_tables.py` (S4A-D61 b): todo modelo con `__audited__` está en `AUDITABLE_TABLES`, y toda tabla de `AUDITABLE_TABLES` está en `RECENT_TABLES_ALLOWED` o en `AUDIT_TABLES_EXCLUDED_FROM_RECENT` con motivo.

**Paso 91 · B8.3 · Rojo de `dashboard` y `audit`**
- `tests/dashboard/test_pure.py`: `month_of` en fin de mes y de año; `short_name("Laura", "Gómez Restrepo") == "Laura G."` y con tildes; `format_cop(120000) == "$ 120.000"`, `format_cop(0)`.
- `tests/dashboard/test_movement_phrase.py`: una prueba por frase del catálogo de S4A-D28 y el fallback; una entrada con blobs `apx1.` en `document` no los incluye; actor `Sistema`; socio o plan ausente usa el genérico.
- `tests/audit/test_recent.py` (`sembrar_actividad` más filas `login`, `reveal`, `verify` y `export` por `audit.record`): filtra por tablas y acciones (`reveal`, `login`, `export`, `verify` y `download` no aparecen; `plans` y `users` solo si se piden); respeta `limit` y el orden global por `seq`; excluye `SYSTEM_USER_ID`; rechaza tablas fuera de `RECENT_TABLES_ALLOWED` (`crypto.*`, `audit.verifications`) y `limit` fuera de 1..50 con `ValueError`; la vista reducida no contiene `apx1.`, `reference` ni `void_reason` (serialización completa); con `contador_de_consultas`, tres tablas son tres consultas (S4A-D51). Caso `perf`: 100.000 filas de `login` y `reveal` más recientes que las de negocio, `recent` en menos de 50 ms y `EXPLAIN` por tabla usa `ix_audit_log_table_seq`.
- `tests/dashboard/test_service.py`: con fábricas y `reloj` en 2026-10-20, los cinco conteos idénticos a `memberships.service.summary()` e `income_month_cop` a `payments.service.summary("2026-10").total_cop`; borde de mes con el reloj en `2026-11-01T01:00Z`: `income_month == "2026-10"` y un pago de `2026-11-01T03:00Z` cuenta en octubre; `today` del reloj; los cinco futuros presentes y `null`.
- `tests/dashboard/test_last_movements.py`: venta de Plan Mensual a Laura Gómez y pago de 120.000 por Ana → frases esperadas, la más reciente primero; 3 entradas → 3; sin entradas → vacío; un `reveal` no aparece; el trabajo de `SYSTEM_USER_ID` no aparece y el límite de 10 se llena con lo demás; la respuesta serializada completa no contiene documento, teléfono, correo, nacimiento, contacto de emergencia, `apx1.`, `reference` ni `void_reason`; un socio dado de baja conserva su nombre; el actor es `display_name` (parte local) y nunca el correo completo.
- `tests/dashboard/test_router.py`: 200 admin y coach con el mismo cuerpo; 403 member; 401; todas las llaves de `CAMPOS_DASHBOARD` presentes; `last_movements` ≤ 10; **la 121.ª lectura del minuto da 429** (`staff-read`); `no-store`.
- `tests/dashboard/test_perf.py` (`perf`): 1.000 socios y 12 meses de pagos, `summary` del tablero en menos de 300 ms (mediana de 5).
- Confirmar el rojo.

**Paso 92 · B8.4 · Verde de `audit`**
`recent` por tabla (S4A-D51), `reduce_entry` con la lista blanca `member_id, plan_id, membership_id, amount_cop, voided, deleted_at, status`, `AuditEntryView` congelada.

**Paso 93 · B8.5 · Verde de `dashboard`**
`summary` (`today = current_clock().today_bogota()`, `memberships.service.summary(session, today=today)`, `payments.service.summary(session, month_of(today))`, `last_movements`), `last_movements` (`audit.service.recent(session, tables=(...), limit=10, exclude_user_ids=(SYSTEM_USER_ID,))`, nombres por `members.names_for`, `memberships.refs_for`, `auth.user_names_for`, `movement_phrase` por entrada), `movement_phrase` partida por tabla (`_member_phrase`, `_membership_phrase`, `_payment_phrase`), `router`. `main.py` con `MODULES` final.

**Paso 94 · B8.6 · Documentación**
RUNBOOK §11: tablero (de dónde sale cada número, caché de 30 s del resumen, por qué el sistema no aparece en movimientos). `docs/design/ROUTES.md:18`: el front la ajusta en F3. `BRECHAS.md` §11: filas de `Inicio.html` confirmadas con slice F3.

**Paso 95 · B8.7 · Contrato**
P-API (contrato definitivo del sprint: 10 endpoints nuevos y `active_members_count`; `docs/openapi.json` sin diferencias al exportar dos veces).

**Paso 96 · B8.8 · Gate**
1. `slice-gate.sh audit tests/audit/test_recent.py tests/audit/test_diff.py`.
2. `slice-gate.sh main tests/core/test_health.py tests/architecture/test_audit_module.py`.
3. `slice-gate.sh architecture tests/architecture/test_read_modules.py tests/architecture/test_service_import_graph.py tests/architecture/test_error_codes_per_route.py tests/architecture/test_user_refs_scope.py tests/architecture/test_audited_tables.py tests/architecture/test_no_store_routes.py tests/architecture/test_every_route_has_role.py tests/architecture/test_session_scope.py`.
4. `uv run pytest -m perf tests/audit/test_recent.py tests/dashboard/test_perf.py -q` (fuera del gate).
5. `security-reviewer` de B8 (vista reducida, sin `apx1.`, sin `reference`, actor sin correo, `staff-read`).
6. Al final, para sellar: `slice-gate.sh dashboard tests/dashboard/test_pure.py tests/dashboard/test_movement_phrase.py tests/dashboard/test_service.py tests/dashboard/test_last_movements.py tests/dashboard/test_router.py tests/architecture/test_read_modules.py`.

**Paso 97 · B8.9 · Cierre del backend**
1. `bash scripts/workflow/run-gates.sh` (front y navegador cerrados): cobertura ≥ 80 % sin `omit`; `cd api && uv run pytest tests/architecture -q`: 0 saltadas nuevas.
2. `cd api && uv run pytest -m perf -q` completo con `TEST_DATABASE_URL` (los cinco archivos de S4A-D68): tiempos al cuaderno.
3. Reconstruir las dos imágenes con buildx (sección 0) y `$DC up -d --no-build`; los cinco servicios `healthy`; `$DC exec api alembic current` = `0013_audit_verifications (head)`; `$DC run --rm worker python -m app.worker.main --status expirations` desde la imagen (sin bind sería lo mismo: el bind sigue en desarrollo).
4. `uvx pre-commit run --all-files`.

**Paso 98 · B8.10 · Docker y evidencia (demo 5, backend)**
Por 8181 con el coach: `GET /api/v1/dashboard` → los cinco conteos iguales a `GET /memberships/summary`, `income_month_cop` igual a `GET /payments/summary?month=<mes>`, `last_movements` sin frases de `Sistema` y sin `apx1.` (grep sobre el cuerpo); con el admin el cuerpo es el mismo; la 121.ª llamada del minuto → 429.

**Paso 99 · B8.11 · Checkpoint**
`checkpoint-commit.sh "S4A-B8 tablero con KPI, últimos movimientos por tabla y cierre del backend"`; después `docs(sprint-04a): evidencia de S4A-B8`.

## 6. Front (worktree; orden de ejecución F1, F2, F4, F3 según S4A-D62)

En todos los slices de front:
- `git rebase feat/sprint-04a-worker-auditoria-tablero` antes de empezar (trae `docs/openapi.json` y `types.ts`); nunca se regeneran en el worktree; `npm ci` si cambió `package-lock.json` (no debería: sin dependencias nuevas).
- El gate acota lint y tsc a los archivos del slice (A-01) y vitest a la lista; `tests/lint/boundaries.test.ts` corre en cada gate `web/app`.
- Antes de cualquier E2E del proyecto `stack` o demo en 8180: `docker buildx build --load --network host --allow network.host -t apex-web:local -f web/Dockerfile .` desde la raíz del worktree y `$DC up -d --no-build web` desde la raíz del repositorio principal (el stack es uno solo).
- Toda mutación nueva pasa por `useSensitiveMutation` (S3-D104); no se agrega nada a la lista blanca de `tests/lint/sensitive-mutations.test.ts`.
- `errorCodes.ts` gana sus códigos en el primer slice que los usa (`errorCodes.test.ts` los busca en `api/src`, que el worktree ve por el rebase).
- Cada faltante del diseño lleva `// DESIGN-GAP:` y se anota en `docs/scratch/sprint-04a-front.md` para que el orquestador lo pase a `BRECHAS.md` §11 en V1.
- Solo variables de `tokens.css`; sin `console`, `fetch` ni `Intl` fuera de `core/api` y `core/i18n`; sin rol comparado con literal fuera de `permissions.ts`.

### S4A-F1 · Pantalla de auditoría

- **Historias:** US-102, US-103 y US-104 (front).
- **Depende de:** B4 (checkpoint); primer slice del worktree.
- **Cierra:** C10 (`features.test.ts`, `routes.test.ts`, `nav.test.ts`, `errorCodes.test.ts`); L-1 (S4A-D52 en el front), L-7 (S4A-D58), L-8 (S4A-D59: `audit.spec.ts`); S4A-D30 (parte), D31, D35, D36 (parte).

**Paso 100 · F1.1 · Worktree, rebase, códigos y stubs**
- `git worktree add .claude/worktrees/sprint-04a-front -b feat/sprint-04a-front feat/sprint-04a-worker-auditoria-tablero`; `export SLICE_BASE=$(git merge-base HEAD main)` dentro del worktree; `npm ci`.
- `web/src/core/api/errorCodes.ts`: `verificationRunning: "verification_running"`, `auditEntryNotFound: "audit_entry_not_found"` (y sus mensajes).
- Stubs: `web/src/shared/lib/encryptedBlob.ts` (`parseEncryptedBlob(value: unknown): { keyId: string; alg: string } | null`, reconoce el marcador `{encrypted: true, key_id, alg}` y el prefijo `apx1.`); `features/system/pages/AuditPage.tsx` (+ `.module.css`), `components/AuditFilters.tsx`, `AuditDetailPanel.tsx`, `VerifyChainButton.tsx`, `auditFilters.ts`, `auditErrors.ts`; en `features/system/api.ts`: `useAudit(params)`, `useAuditEntry(seq)`, `useLastVerification({ polling })`, `useVerifyChain()`; en `features/system/schemas.ts`: `auditRowSchema`, `auditDetailSchema`, `fieldChangeSchema`, `verifyResultSchema`, `verifyStartedSchema`; `web/src/test/audit.tsx`.
- `web/src/config/features.ts`: `ENABLED_FEATURES` suma `audit`; `routeTable.ts:146`: `load` de `/sistema/auditoria`; `routes.reference.ts` si la fila cambia.

**Paso 101 · F1.2 · Rojo**
- `src/config/features.test.ts:10-13`: nueve features con `audit`; `src/routes.test.ts:72-91`: `/sistema/auditoria` en la lista con `load`; `src/layouts/nav.test.ts:14`: "Auditoría" entre "Usuarios y roles" y "Configuración" para el admin; el coach no la ve (`role-guards`); `src/core/api/errorCodes.test.ts`: los dos códigos nuevos existen en `api/src`.
- `src/shared/lib/encryptedBlob.test.ts`: marcador válido da `keyId` y `alg`; blob `apx1.` válido igual; texto sin prefijo, vacío, no texto, marcador sin `key_id` y blob malformado dan `null`; nunca devuelve el texto cifrado (la salida no contiene el cuarto ni el quinto segmento).
- `src/features/system/auditFilters.test.ts` (S4A-D58): `toApiParams(search)` construye con `URLSearchParams`; descarta `user_id`, `record_id` y `subject_member_id` que no sean UUID, `table` que no cumpla `^[a-z_]{1,63}\.[a-z_]{1,63}$`, `action` fuera de la lista y `seq` que no sea entero seguro ≥ 1; `from`/`to` de fecha de Bogotá a UTC con `core/i18n`; `q` nunca va a la URL; `offset` como múltiplo de `limit`.
- `src/features/system/pages/AuditPage.test.tsx`: filtros en la URL con los nombres del api (`from`, `to`, `table`, `user_id`, `action`, `record_id`); selector de usuario con `GET /users?limit=200` más "Sistema (worker)" = `SYSTEM_USER_ID`; paginación por `offset` (25/50/100); carga, vacío y error con reintento; una fila abre el detalle con `?seq=`; el coach no ve el ítem de menú ni la ruta; `// DESIGN-GAP:` visibles en el código (Qué cambió, búsqueda por nombre de socio, Exportar rango, firma ML-DSA, entidades Resultado y Llave, valores enmascarados).
- `src/features/system/components/AuditDetailPanel.test.tsx`: metadatos; lista de cambios antes → después; valores cifrados como "Cifrado" con el `key_id` (del marcador o del prefijo); ausencia de cualquier acción de descifrar o mostrar (`// DESIGN-GAP:` frente a `Auditoria.html`); `prev_hash` y `hash` en fuente monoespaciada; 404 "ese registro ya no existe"; carga y error; un valor con `<script>` se pinta como texto (S4A-D58 d, `innerHTML` sin etiqueta); un objeto anidado se aplana y se corta a 2.000 caracteres; `?seq=abc` o `?seq=0` no dispara petición.
- `src/features/system/components/VerifyChainButton.test.tsx`: texto "Verificar ahora"; 200 → "Cadena íntegra: N filas verificadas" con la fecha en Bogotá; primera verificación → "sin verificación anterior que comparar"; 202 → sondeo de `GET /audit/verify/last` con `fakeTimers` hasta que `finished_at` cambie, y tope de 900 s con el mensaje "la verificación no terminó; vuelve a intentarlo"; 409 → mensaje; 429 → "Demasiadas verificaciones; espera un momento"; cadena rota → "Cadena rota en el registro seq X" con enlace a `?seq=X`; la mutación usa `useSensitiveMutation` y el `MutationCache` no conserva `data` tras `onSettled`.
- `tests/e2e/stack/audit.spec.ts` (S4A-D59): con `E2E_ADMIN_*` y `exigirStackLocal`: filtrar por entidad `memberships.memberships`, abrir un detalle, pulsar "Verificar ahora" y ver "Cadena íntegra"; con `crearCoach` el coach recibe 403 en `/sistema/auditoria`; `borrarUsuario` al final; sin aserciones sobre la primera página ni el número de filas. Captura en `preview` con `page.route`.
- Confirmar el rojo.

**Paso 102 · F1.3 · Verde**
Según S4A-D31 y S4A-D58: `AuditPage` con `FilterBar`, `DataTable`, `Pagination`, `SidePanel` para el detalle; `useLastVerification` con `refetchInterval` solo mientras el estado es `running` y `maxPolls = 900 s / intervalo`; `VerifyChainButton` con `useSensitiveMutation`; `auditErrors.ts`.

**Paso 103 · F1.4 · Documentación**
`docs/design/ROUTES.md`: `/sistema/auditoria` con `?seq=` y los filtros reales. `docs/scratch/sprint-04a-front.md`: bloque F1 con los DESIGN-GAP.

**Paso 104 · F1.5 · Gate**
1. `slice-gate.sh web/core src/core/api/errorCodes.test.ts`.
2. `slice-gate.sh web/shared src/shared/lib/encryptedBlob.test.ts`.
3. `slice-gate.sh web/app src/config/features.test.ts src/routes.test.ts src/layouts/nav.test.ts tests/lint/boundaries.test.ts tests/lint/sensitive-mutations.test.ts`.
4. `cd web && npx playwright test --project=preview tests/e2e/audit.spec.ts` (si se crea la captura en preview).
5. `security-reviewer` de F1 (valores como texto, sin descifrar, filtros validados, sondeo acotado).
6. Al final, para sellar: `slice-gate.sh web/system src/features/system/pages/AuditPage.test.tsx src/features/system/components/AuditDetailPanel.test.tsx src/features/system/components/VerifyChainButton.test.tsx src/features/system/auditFilters.test.ts`.

**Paso 105 · F1.6 · Docker**
Reconstruir `apex-web:local` con buildx y `$DC up -d --no-build web`; `cd web && E2E_BASE_URL=http://localhost:8180 npx playwright test --project=stack tests/e2e/stack/audit.spec.ts` (B3 y B4 ya están en la rama: se corre aquí, no en V4); captura al cuaderno del front.

**Paso 106 · F1.7 · Checkpoint**
`checkpoint-commit.sh "S4A-F1 pantalla de auditoría con detalle sin descifrar y verificación con sondeo"` (en el worktree, con el trailer).

### S4A-F2 · Historial de la ficha

- **Historias:** US-106 (front).
- **Depende de:** B5 y F1 (rebase).
- **Cierra:** C10 (`routes.test.ts:127` y `:35`, `MemberDetailPage.test.tsx:101-114`); el criterio diferido de US-066; S4A-D30 (hija), D32.

**Paso 107 · F2.1 · Rebase y stubs**
Rebase. `web/src/shared/lib/audit-labels.ts`: `AuditEntryView` gana `fields?: readonly string[]`, `phrase?: string` y `purpose?: string | null`; `summarizeChange` acepta `fields` (línea "Cambió: Teléfono, Correo" con `FIELD_LABELS`, sin valores) cuando no hay `before` ni `after`; `ENTITY_LABELS` gana `members.members`, `memberships.memberships`, `payments.payments` (las viejas se conservan); `web/src/shared/ui/HistoryAside.tsx`: pinta `entry.phrase` como línea fuerte y una etiqueta "automático (aviso)" cuando `purpose` existe. `features/members/lib/historyEntries.ts` (`toAuditEntryView(item: MemberHistoryItem)`), `historyPhrase.ts`; `features/members/api.ts`: `useMemberHistory(memberId)` (`useInfiniteQuery`, `maxPages: 20`, `limit` 25, `gcTime: 0`); `features/members/schemas.ts`: `memberHistoryItemSchema`; `components/MemberHistoryTab.tsx`; `routeTable.ts`: hija `/socios/:id/historial` (`childRoute(MEMBER_DETAIL, "historial", "Historial", { access: "members.history.view", load: () => import("../features/members/components/MemberHistoryTab") })`, feature `members`); `routes.reference.ts`; `MemberDetailPage.tsx:57` sin `disabledUntil`; `MemberDataTab.tsx`: caja "Historial reciente" con las 5 últimas y el enlace "historial completo →"; `web/src/test/history.tsx`.

**Paso 108 · F2.2 · Rojo**
- `src/routes.test.ts:127`: los hijos de la ficha pasan a `["index", "/socios/:id/membresias", "/socios/:id/pagos", "/socios/:id/historial"]`; `:35` compara con `routes.reference.ts` (gana la hija); `src/features/members/pages/MemberDetailPage.test.tsx:101-114`: Historial habilitada y última, navega a la hija.
- `src/shared/lib/audit-labels.test.ts`: `summarizeChange` con `fields` y sin valores; con `before`/`after` sigue igual; `ENTITY_LABELS` reales; `src/shared/ui/HistoryAside.test.tsx`: línea `phrase` y etiqueta de `purpose`; sin HTML (un `phrase` con `<b>` se ve literal).
- `src/features/members/lib/historyPhrase.test.ts`: frase por acción y tabla ("editó teléfono y correo", "vendió una membresía", "registró un pago", "anuló un pago", "mostró el documento", "marcó la membresía como vencida" para `Sistema`), con el nombre de quien actuó y sin valores; `historyEntries` mapea `table_name` completo y `fields`.
- `src/features/members/components/MemberHistoryTab.test.tsx`: orden descendente; "Cargar más" acumulativo y tope `maxPages`; vacío; error con reintento; el coach lo ve; ningún valor mostrado; 429 muestra "Demasiadas consultas; espera un momento".
- `src/features/members/components/MemberDataTab.test.tsx` (existente, ampliado): la caja con 5 entradas y el enlace a `/socios/:id/historial`.
- `tests/e2e/stack/member-tabs.spec.ts` y `member-detail.spec.ts`: si capturan las pestañas, ganan "Historial"; `tests/e2e/stack/member-history.spec.ts` nuevo: crear socio por API, editar el teléfono, abrir Historial y ver "editó teléfono" sin el número.
- Confirmar el rojo.

**Paso 109 · F2.3 · Verde**
Según S4A-D32.

**Paso 110 · F2.4 · Documentación**
`docs/design/ROUTES.md`: hija `/socios/:id/historial`. Cuaderno del front.

**Paso 111 · F2.5 · Gate**
1. `slice-gate.sh web/shared src/shared/lib/audit-labels.test.ts src/shared/ui/HistoryAside.test.tsx`.
2. `slice-gate.sh web/app src/routes.test.ts tests/lint/boundaries.test.ts`.
3. Al final, para sellar: `slice-gate.sh web/members src/features/members/components/MemberHistoryTab.test.tsx src/features/members/lib/historyPhrase.test.ts src/features/members/pages/MemberDetailPage.test.tsx src/features/members/components/MemberDataTab.test.tsx`.

**Paso 112 · F2.6 · Docker**
Reconstruir `apex-web:local` y `$DC up -d --no-build web`; `npx playwright test --project=stack tests/e2e/stack/member-history.spec.ts tests/e2e/stack/member-tabs.spec.ts tests/e2e/stack/member-detail.spec.ts`.

**Paso 113 · F2.7 · Checkpoint**
`checkpoint-commit.sh "S4A-F2 historial de la ficha sobre HistoryAside con frases y sin valores"`.

### S4A-F4 · Acciones de planes

- **Historias:** US-080, US-081 y US-082 (front).
- **Depende de:** B7 (y rebase sobre B7; puede ir antes que F3).
- **Cierra:** C10 (`errorCodes.test.ts`, `plans.spec.ts`), S4A-D34, D35, D36 (`Planes.html`).

**Paso 114 · F4.1 · Rebase, códigos y stubs**
Rebase. `errorCodes.ts`: `planHasActiveMemberships: "plan_has_active_memberships"`. `features/plans/api.ts`: `useUpdatePlan(id)`, `useSetPlanActive()`, `useDeletePlan()` (todas con `useSensitiveMutation`, invalidan `PLANS_QUERY_KEY`); `planErrors.ts` traduce el código nuevo; `components/PlanForm.tsx` modo edición; `components/PlanRowActions.tsx` (menú Editar, Activar o Desactivar, Dar de baja bajo `<Can action="plans.manage">`); `pages/PlansPage.tsx` con la columna de acción, "Socios con él" (`active_members_count`) y el total partido (dos `usePlans({ limit: 1, active })`); `planRowSchema` ya trae `active_members_count` (B7, P-API paso 6).

**Paso 115 · F4.2 · Rojo**
- `src/core/api/errorCodes.test.ts`: el código nuevo existe en `api/src`.
- `src/features/plans/components/PlanForm.edit.test.tsx`: precarga; aviso fijo "Cambiar el precio no modifica las membresías ya vendidas"; envía solo los campos modificados (`dirtyFields`), con `class_count: null` al pasar a `days`; error de campo del 422 (`class_count`) y del 409 de nombre (`plan_name_duplicated`); `reset()` tras guardar.
- `src/features/plans/pages/PlansPage.actions.test.tsx`: Desactivar con `ConfirmModal` ("Las membresías vigentes con este plan siguen igual; el plan deja de aparecer al vender") y cambio de la etiqueta de estado; Activar; acciones ocultas al coach; columna "Socios con él"; total "N activos · M inactivos"; `// DESIGN-GAP:` por Descripción, Días para usarlas y la casilla Activo.
- `src/features/plans/pages/PlansPage.delete.test.tsx`: baja exitosa quita la fila; 409 `plan_has_active_memberships` muestra el mensaje del API y el botón "Desactivar" que llama a `useSetPlanActive`; acción oculta al coach; el `MutationCache` no conserva `variables`.
- `tests/e2e/stack/plans.spec.ts`: se revisa (captura "Detalle del plan" y las acciones); caso nuevo: crear un plan por API, editarlo por la pantalla, desactivarlo y darlo de baja (204).
- Confirmar el rojo.

**Paso 116 · F4.3 · Verde**
Según S4A-D34.

**Paso 117 · F4.4 · Documentación**
`docs/design/ROUTES.md:39` (texto final del front). Cuaderno del front.

**Paso 118 · F4.5 · Gate**
1. `slice-gate.sh web/core src/core/api/errorCodes.test.ts`.
2. `slice-gate.sh web/app tests/lint/boundaries.test.ts tests/lint/sensitive-mutations.test.ts`.
3. Al final, para sellar: `slice-gate.sh web/plans src/features/plans/components/PlanForm.edit.test.tsx src/features/plans/pages/PlansPage.actions.test.tsx src/features/plans/pages/PlansPage.delete.test.tsx src/features/plans/pages/PlansPage.test.tsx src/features/plans/planErrors.test.ts`.

**Paso 119 · F4.6 · Docker**
Reconstruir `apex-web:local` y `$DC up -d --no-build web`; `npx playwright test --project=stack tests/e2e/stack/plans.spec.ts`; demo 6 por la pantalla en 8180 (editar precio, desactivar, dar de baja con 409 y luego 204) al cuaderno.

**Paso 120 · F4.7 · Checkpoint**
`checkpoint-commit.sh "S4A-F4 acciones de planes: editar, activar o desactivar, dar de baja y socios con él"`.

### S4A-F3 · Inicio

- **Historias:** US-108, US-109 y US-110 (front).
- **Depende de:** B8 (último slice de front).
- **Cierra:** C10 (`InicioPage.test.tsx`), L-8 (S4A-D59: `home.spec.ts`), S4A-D33, D36 (`Inicio.html`). Criterio diferido: T8 de US-109 (cuadre con datos de demostración) se cierra en 4B con US-111.

**Paso 121 · F3.1 · Rebase y stubs**
Rebase. `features/dashboard/api.ts` (`useDashboard`, clave `["dashboard"]`, `staleTime` 60 s), `schemas.ts` (`dashboardSchema` con los futuros `nullable()`, `movementSchema`), `links.ts` (`kpiLinks(today)`), `components/KpiGrid.tsx`, `FutureKpis.tsx`, `LastMovements.tsx`; `pages/InicioPage.tsx` actualizada; `web/src/test/dashboard.tsx`; `routeTable.ts:103` sin cambio (`InicioPage`).

**Paso 122 · F3.2 · Rojo**
- `src/features/dashboard/links.test.ts`: `kpiLinks("2026-10-20")` da los cuatro destinos de `/socios?membership_status=` (active, expiring, expired, pending_payment) y `/pagos?from=2026-10-01T05:00:00Z&to=2026-11-01T05:00:00Z`.
- `components/KpiGrid.test.tsx`: valores 120, 14, 9 y `$ 3.250.000`; línea de pendientes de pago (`// DESIGN-GAP:` Q3); enlaces; carga y error con "Reintentar" que vuelve a pedir; 429 muestra el mensaje.
- `components/FutureKpis.test.tsx`: `null` dice "Disponible en v0.x" y nunca 0; con valor lo muestra.
- `components/LastMovements.test.tsx`: diez en orden, vacío, enlace a `/socios/:id`, hora relativa de Bogotá con reloj falso, la frase como texto (sin HTML), `// DESIGN-GAP:` por "Sistema marcó...".
- `pages/InicioPage.test.tsx`: reemplazo completo (el saludo usa la parte local del correo con `// DESIGN-GAP:` frente a "Hola, Ana"; ya no dice "llega en la próxima versión"); el member va a `/mi`.
- `tests/e2e/home.spec.ts` (preview, API simulada, coach) y `tests/e2e/stack/home.spec.ts` (login real con `E2E_ADMIN_*`, KPI iguales a `GET /dashboard` leído por API, clic en "Por vencer" llega a `/socios?membership_status=expiring`; sin aserciones sobre el orden ni el contenido de los movimientos, S4A-D59); capturas a 320, 768, 1024 y 1440 en claro y oscuro; ninguna tarjeta depende solo del color (axe).
- Confirmar el rojo.

**Paso 123 · F3.3 · Verde**
Según S4A-D33 (`KpiCard` y `HistoryAside` del kit sin cambios).

**Paso 124 · F3.4 · Documentación**
`docs/design/ROUTES.md:18` (Inicio ya no es mínima). Cuaderno del front con los DESIGN-GAP de `Inicio.html`.

**Paso 125 · F3.5 · Gate**
1. `cd web && npx playwright test --project=preview tests/e2e/home.spec.ts`.
2. Al final, para sellar: `slice-gate.sh web/dashboard src/features/dashboard/links.test.ts src/features/dashboard/components/KpiGrid.test.tsx src/features/dashboard/components/FutureKpis.test.tsx src/features/dashboard/components/LastMovements.test.tsx src/features/dashboard/pages/InicioPage.test.tsx`.

**Paso 126 · F3.6 · Cierre del front**
`cd web && npm run lint && npx tsc --noEmit && npm test -- --run --coverage && npm run build && npm run licenses`; `npx playwright test --project=preview` completo; reconstruir `apex-web:local`, `$DC up -d --no-build web` y `E2E_BASE_URL=http://localhost:8180 npm run e2e:stack` completo (las 15 specs del Sprint 3 más `audit`, `member-history`, `plans` ampliada y `home`); `git diff --exit-code src/core/api/types.ts` tras `npm run gen:api` (sin deriva); `grep -rn "job_runs\|audit_log" web/tests` vacío.

**Paso 127 · F3.7 · Checkpoint**
`checkpoint-commit.sh "S4A-F3 Inicio con KPI, futuros en null y últimos movimientos; cierre del front"`.

## 7. Validación del sprint

Cada paso deja su evidencia en `docs/scratch/sprint-04a.md` (bloque "Validación V1–V12"), con comandos, salidas resumidas y los ids de imagen; las credenciales nunca.

**V1 · Fusión y documentos**
1. Fusionar `feat/sprint-04a-front` en la rama del sprint (`GIT_EDITOR=true git merge --continue` si el hook de calidad falla por el tamaño); resolver `docs/openapi.json` y `types.ts` a favor del backend; `cd web && npm run gen:api && npx vitest run src/core/api/types.contract.test.ts`; `git worktree remove .claude/worktrees/sprint-04a-front`; `git worktree list` solo el principal.
2. Pasar a `docs/BRECHAS.md` §11 los DESIGN-GAP de `docs/scratch/sprint-04a-front.md`; confirmar que cada `// DESIGN-GAP:` nuevo de `web/src` tiene su fila (`grep -rn "DESIGN-GAP" web/src/features/{system,dashboard,plans,members}` contra §11).
3. Documentos al día: `CLAUDE.md` (estructura y comandos), `RUNBOOK.md` (§6, §7, §11, §4, §5), `SPRINT-04A.md` (contratos finales), `ROUTES.md`, `DECISIONES.md` (bloque Sprint 4A con S4A-D62 a S4A-D74 y las decisiones de ejecución que cada slice añadió). Criterio: ninguna referencia a `admin-write` en `POST /audit/verify`, a `--date` sin `--simulate`, a `VERIFY_BATCH_SIZE = 5000` ni a `web/tests/e2e/stack/helpers`.

**V2 · Stack desde cero de código y ciclo de Alembic**
1. Reconstruir `apex-api:local` y `apex-web:local` con buildx desde el árbol fusionado; `$DC up -d --no-build`; los cinco servicios `healthy`; anotar los ids de imagen y `docker image inspect` de las dos.
2. `$DC run --rm tools init-keys` (idempotente).
3. `$DC exec api alembic current` = `0013_audit_verifications (head)`; `cd api && uv run alembic heads` una sola.
4. Ciclo completo sobre `db_test`: `cd api && uv run pytest tests/core/test_migrations.py tests/migrations -q` (upgrade head → downgrade base → upgrade head, con `0012` y `0013`).
5. Ciclo autorizado sobre `apex-db-1`: `$DC exec api alembic downgrade 0011_payments_immutability` → `upgrade head` → `current` = `0013 (head)` (la bitácora de corridas y las verificaciones de desarrollo se pierden con el `downgrade`: V3 y V7 las vuelven a crear; la cadena de auditoría no se toca porque `0013` no borra `audit_log`). `$DC logs --tail 50 api` sin errores; `psql '\d worker.job_runs'` y `'\d audit.verifications'` otra vez al cuaderno.
6. `$DC restart worker`; `healthy`; `docker inspect -f '{{.RestartCount}}' apex-worker-1` = 0.

**V3 · Datos reales antes de navegar**
- Credenciales: `E2E_ADMIN_EMAIL` y `E2E_ADMIN_PASSWORD` del admin desechable (S4A-D71) en la shell; si el `downgrade` de V2 no lo tocó (`auth.users` no baja), sigue válido; si falta, se crea de nuevo. La contraseña del admin real no se toca.
- psql de lectura: `SELECT id, email, role FROM auth.users WHERE deleted_at IS NULL`; `SELECT name, price_cop, is_active FROM plans.plans WHERE deleted_at IS NULL ORDER BY name LIMIT 20` (debe existir "Mensual" 120.000/30); `SELECT count(*) FROM audit.audit_log`.
- Crear por API los socios de la demo (`demo-s4a-expira`, `demo-s4a-historial`, `demo-s4a-plan`, documentos aleatorios) y una venta con fin ya pasado para `demo-s4a-expira` (`start_date` retroactivo con el admin, `enforce_retroactive_limit` por rol; si el tope lo impide, una venta `pending_payment` con fin próximo y `reloj` real: se usa la que la base ya trae del Sprint 3); guardar los ids en la shell.
- `$DC run --rm worker python -m app.worker.main --run-once expirations` → 0 (crea la fila del día para V7 y V8).

**V4 · E2E contra el stack (preview y stack ×2)**
- Copia de `.env` en el scratchpad; apilar `infra/compose.e2e.yml` y el bloque de topes ×100 en `.env` (`LOGIN_*` y `REFRESH/RESET/FORGOT/LOGOUT_*` a 1000, `LOGIN_ACCOUNT_GLOBAL_LIMIT=10000`, las ocho `USER_*` del Sprint 3 ×100 y las tres nuevas: `USER_READ_LIMIT_PER_MIN=12000`, `USER_AUDIT_VERIFY_LIMIT_PER_MIN=300`, `USER_AUDIT_VERIFY_LIMIT_PER_HOUR=2000`); `$DC -f infra/compose.e2e.yml up -d api web`.
- `cd web && E2E_BASE_URL=http://localhost:8180 npm run e2e:stack` dos veces seguidas: 0 fallos, 0 flaky (las specs crean lo suyo con documentos y nombres aleatorios y lo dan de baja; `audit.spec.ts` no depende del orden).
- `npx playwright test --project=preview` completo con capturas a 320, 768, 1024 y 1440 en claro y oscuro (`home`, `audit`).
- Restaurar `.env` (`cmp` contra la copia; borrar la copia) y `$DC up -d api web` sin `compose.e2e.yml`; comprobar que seis fallidos de login dan `401 ×5, 429` y que la 4.ª verificación del minuto da 429.
- El job `e2e-stack` de la CI ya lleva las once variables (B3.8); se anota que el `grep -c` espera 11.

**V5 · Rendimiento**
`cd api && uv run pytest -m perf -q` (con `TEST_DATABASE_URL`), dos corridas: `tests/worker/test_expirations.py` (1.000 socios, 3.000 membresías < 60 s), `tests/audit/test_verify_performance.py` (100.000 filas < 60 s, bloque síncrono < 100 ms, y el valor final de `SYNC_VERIFY_MAX_ROWS`), `tests/audit/test_list_performance.py` (100.000 filas, `limit=25` < 500 ms), `tests/audit/test_recent.py` (< 50 ms con `EXPLAIN` por tabla), `tests/dashboard/test_perf.py` (< 300 ms). Tiempos al cuaderno. Si `recent` o la lista fallan, se ajusta la consulta dentro del sprint (no hay migración de índices prevista: los cinco existen).

**V6 · Smoke con evidencia SQL y `verify_chain`**
Se guarda en el cuaderno (todo psql de lectura sobre `apex-db-1`):
- worker: `SELECT job_name, run_date, result, jsonb_array_length(details->'attempts') FROM worker.job_runs ORDER BY started_at DESC LIMIT 5` → la fila del día con los intentos de V3 y V8; ninguna fila `*_sim`;
- vencimientos: `SELECT status, count(*) FROM memberships.memberships GROUP BY 1` antes y después de V8; `SELECT seq, action, table_name, user_id FROM audit.audit_log WHERE user_id = '00000000-0000-0000-0000-000000000001' ORDER BY seq DESC LIMIT 5` → filas `update` de `memberships.memberships`;
- verificación: `SELECT ok, rows_checked, through_seq, left(through_hash, 12), source, triggered_by FROM audit.verifications ORDER BY finished_at` → las de V7 (api y cli) con `ok = true` y `through_seq` creciente; `SELECT action, table_name, after->>'through_hash' FROM audit.audit_log WHERE action = 'verify' ORDER BY seq DESC LIMIT 2`; `$DC logs api | grep "audit anchor" | tail -2`;
- `verify_chain` en verde sobre toda `audit.audit_log` por dos vías: `$DC run --rm tools verify-audit --as $E2E_ADMIN_EMAIL` (código 0) y `POST /audit/verify` (200 `ok: true`); ambas con el mismo `through_seq` si no hubo escrituras entre medias;
- triggers: `UPDATE audit.verifications SET ok = false` → rechazado por `verifications_forbid_mutation`; `DELETE` y `TRUNCATE` → rechazados; `SET session_replication_role = replica; UPDATE ...` → rechazado (todo dentro de `BEGIN; ... ROLLBACK;` de solo prueba: la sentencia falla antes de escribir; se anota como la única excepción a "psql solo lectura", heredada de V6 del Sprint 3);
- historial y tablero: `GET /members/<demo-s4a-historial>/audit` con el coach no contiene `@` ni `apx1.`; `GET /dashboard` no contiene `apx1.`, `reference` ni `void_reason`; `GET /audit/<seq de un update de members>` no contiene `apx1.` (marcador);
- planes: `SELECT agreed_price_cop FROM memberships.memberships WHERE plan_id = <plan de V7.6>` sigue en el precio pactado tras el `PATCH`;
- `$DC logs api worker` sin documentos, teléfonos, correos completos, referencias ni motivos (grep de los valores de V3).

**V7 · Demo (los 6 puntos de `SPRINT-04A.md` con el texto corregido)**
1. `$DC ps` muestra `worker` sin perfil y `healthy`; `$DC exec api alembic current` = `0013_audit_verifications`.
2. `$DC run --rm worker python -m app.worker.main --run-once expirations` sobre `apex-db-1` (sin fecha): pasa a `expiring`/`expired` lo que el calendario real exige (la base trae vencidas del Sprint 3) y `worker.job_runs` registra la corrida; una segunda corrida el mismo día no duplica (conteo de `audit_log` igual; `--status` con la misma fila). La corrida con fecha adelantada se demuestra con `--date 2026-11-01 --simulate` contra `apex_sim` (S4A-D63; se repite el procedimiento de B2.9 y se borra la copia).
3. Auditoría por la pantalla en 8180: filtrar por entidad, usuario (Sistema) y fecha; abrir el detalle de un `update` de socio y ver "Cifrado" con `key_id` (sin descifrar); "Verificar ahora" → "Cadena íntegra" y la fila en `audit.verifications`; `$DC run --rm tools verify-audit --as $E2E_ADMIN_EMAIL` da el mismo resultado y código 0.
4. Pestaña Historial de `demo-s4a-historial`: cambios del socio, de sus membresías y de sus pagos con frases y sin valores (N-31); el coach ve lo mismo.
5. Inicio: KPI de membresías iguales a `/membresias` (resumen) e ingresos del mes iguales a `/pagos`; "Últimos movimientos" en frases, sin entradas del sistema.
6. Planes por la pantalla: editar el precio del plan de `demo-s4a-plan` (la membresía vendida conserva el precio: pestaña Membresías de la ficha); desactivar el plan impide venderlo (`/membresias/vender` no lo ofrece y la API responde 422 `plan_inactive`); dar de baja con una membresía activa responde 409 con el mensaje y el botón "Desactivar"; tras anular la membresía, la baja da 204.

**V8 · Repetición e idempotencia**
- `--run-once expirations` dos veces el mismo día sobre `apex-db-1` (además de V7.2): código 0 las dos, una sola fila en `job_runs` con un intento más, sin filas nuevas en `audit_log`.
- `verify-audit` dos veces: 0 las dos; la segunda verifica también la fila `verify` de la primera; `POST /audit/verify` cuatro veces en un minuto: 200 ×3 y 429.
- `tools seed` dos veces: "omitido"; `init-keys` dos veces; `export-openapi` dos veces: idénticas e iguales a `docs/openapi.json`.
- `PATCH /plans/{id}` con el mismo cuerpo dos veces: 200 y 200 sin segunda fila de auditoría; `POST .../deactivate` dos veces: 200 y 200 sin auditoría nueva; `DELETE` dos veces: 204 y 404.
- Las specs `stack` dos veces (V4).
- Smoke: copia de `compose-smoke.sh` del scratchpad con `SMOKE_KEEP=1`: verde con el worker (healthy, 0 reinicios, `--run-once` ×2, `--status`).

**V9 · Gates completos**
1. `bash scripts/workflow/run-gates.sh` (front y navegador cerrados): api `-m "not perf"` con cobertura global de `app` ≥ 80 % **sin `omit`** (esperado ≥ 90 %; se anota el porcentaje y las líneas sin cubrir de `cli.py` y `worker/`), scripts de infraestructura (`test_check_key_files`, `test_images_pinned`, `test_nginx_conf`, `test_compose_config` con las aserciones del worker), web lint, tsc, pruebas con cobertura y build. Si la máquina se queda sin memoria en el front, repetir solo la sección web con `npm test -- --run --coverage` y `npm run build` y anotarlo.
2. `cd api && uv run pytest tests/architecture -q`: 0 saltadas (las seis pruebas nuevas: `test_worker_boundaries`, `test_expirations_lock_order`, `test_user_refs_scope`, `test_audit_subject`, `test_crypto_bus_importers`, `test_contact_callers`, `test_read_modules`).
3. `uvx pre-commit run --all-files`.
4. `bash scripts/workflow/tests/run.sh`.
5. `bash scripts/ci/check-licenses-api.sh` y `cd web && npm run licenses`; `NOTICE` sin cambios (sin dependencias nuevas).
6. `npm audit --omit=dev --audit-level=high` (gate) y `npm audit --audit-level=high` (informativo); `pip-audit` sobre `uv export --frozen --no-dev --no-emit-project`.
7. gitleaks sobre el historial (imagen por digest de `ci.yml`): ninguna credencial del admin desechable ni `DATABASE_URL` de `apex_sim` en commits ni en el cuaderno.
8. `bash scripts/ci/check-image-secrets.sh apex-api:local` y `bash scripts/ci/test_api_image.sh apex-api:local` (la imagen trae `app/worker/`).
9. `cd web && npm run gen:api && git diff --exit-code src/core/api/types.ts`; `grep -rn "job_runs\|audit_log" web/tests` vacío.

**V10 · Revisión de seguridad posterior (`security-reviewer` sobre el código fusionado)**
Verifica contra el árbol de V1: la definición de hecho del sprint (la auditoría no muestra material de llave ni blobs: marcador en el detalle, vista reducida en el tablero, `fields` en el historial; el historial respeta el rol con el mismo cuerpo; `verify-audit` atribuido con `--as`; el worker sin puertos, sin volúmenes y endurecido); H-1 y H-2 cerrados con sus pruebas (ancla y `through_hash`, `AUTOCOMMIT` + `invalidate`, plazo, cancelación); M-1 a M-7 y L-1 a L-10 con su slice de la sección 10; los riesgos aceptados registrados (S4A-D43 residual sin firma externa, S4A-D49 credencial compartida hasta S4B-W0-2, S4A-D54 regresión de S3-D57, S4A-D60 precio vigente, S4A-D61 lectura no auditada); que `USER_LIMITS` cubre todas las escrituras y las cuatro lecturas de D45; que ningún handler toma candados nuevos; que ninguna corrida con `--date` llegó a `apex-db-1` (no hay filas `*_sim` ni `at` futuros en `audit_log`: `SELECT max(at) <= now() FROM audit.audit_log`). Todo CRITICAL o HIGH se corrige dentro del sprint antes de V11, con el mismo esquema de agentes de la Fase 4 del Sprint 3.

**V11 · `verify-delivery`**
- Pilar 1 (`docs/scratch/sprint-04a-verify-delivery.md`): matriz N/M de las 14 historias, los 10 endpoints más `active_members_count`, las 2 migraciones, las 13 condiciones para VERDE, H-1, H-2, M-1 a M-7, L-1 a L-10, las decisiones S4A-D1 a S4A-D74, la deuda heredada del Sprint 3 con dueño 4A (`display_name` diferido, "Socios con él", job de vencimientos, historial, `omit`, P2-1) y las contradicciones de contrato, cada fila con su evidencia (archivo de prueba, línea del cuaderno o consulta de V6).
- Desviaciones declaradas: `display_name` sin columna (S4A-D19); `--date` solo con `--simulate` y nunca sobre `apex-db-1`; tres cubetas nuevas frente a "USER_LIMITS no cambia"; `VERIFY_BATCH_SIZE` 1.000; `SYNC_VERIFY_MAX_ROWS` calibrado; marcador en lugar de blob; worker sin volúmenes; `GET /members/{id}/audit` y `GET /dashboard` con 429; `recent` por tabla; `contact_for_notification` sin `fields` ni `by`; T8 de US-109 diferido a 4B; orden del front F1, F2, F4, F3.
- Pilar 2: V2 a V8 contra el stack con las imágenes reconstruidas de api y web (ids anotados), una corrida real del worker, una verificación real por API y por CLI, una edición y una baja de plan reales por la pantalla, las specs `stack` dos veces, la evidencia SQL de V6 y la comprobación de que `apex-worker-1` lleva más de una hora `healthy` sin reinicios.

**V12 · Cierre documental y paso humano**
- Limpieza P2-1 por la API con el admin desechable (S4A-D60; script de ritmo en el scratchpad, 30 escrituras por minuto): para cada plan `E2E-tope-*` y de las specs (`nombrePlanE2E`), listar sus membresías (`GET /memberships?plan_id=&status=pending_payment,active,expiring,frozen`), anular las `pending_payment` con `POST /memberships/{id}/cancel` (motivo "limpieza de datos de prueba S4A-V12"), `DELETE /plans/{id}` (204; un 409 por membresías activas reales se anota y el plan se desactiva en su lugar); al final `GET /plans?limit=1&active=true` muestra `total` ≤ 100 y la venta ya no avisa "Se muestran 100 de N". Todo queda en la cadena (`verify-audit` otra vez: 0).
- Borrar `docs/scratch/sprint-04a-antes-0012.dump`, `-0013.dump` y cualquier `sprint-04a-sim.dump`; `dropdb apex_sim` si quedó; borrar el admin desechable por API (`DELETE /users/{id}`) y limpiar las variables de la shell; `git worktree list` solo el principal; `.env` idéntico a la copia; stack arriba sin `compose.e2e.yml`.
- `DECISIONES.md`: "Estado al cierre del Sprint 4A" (por decisión que cambió, con el valor final de `SYNC_VERIFY_MAX_ROWS`, el tamaño de `cli.py` y `plans/service.py`, y si hubo `cli_ops.py` o `plans/changes.py`) y "Dueños asignados al cierre del Sprint 4A" (lo que pasa a 4B: `display_name` en v0.2, rol de base S4B-W0-2, `/health` con `job_runs` v0.2, `sign-audit` v0.3, `notifications.service` en `CONTACT_CALLERS` Sprint 5, T8 de US-109). `SPRINT-04A.md`: "Estado al cierre" con conteos, cobertura, tiempos `perf` y desviaciones. Memoria del proyecto al día.
- Merge a `main` por avance rápido (`git checkout main && git merge --ff-only feat/sprint-04a-worker-auditoria-tablero`), push de `main` y de la rama (si el clasificador bloquea el push, reintentar en la sesión siguiente, como en los Sprints 2 y 3). Paso humano: ver los seis jobs de CI en GitHub Actions (`api`, `web`, `images` con el smoke del worker, `scripts`, `secrets-scan`, `e2e-stack` con el worker activo) y el PR si se abre; `gh` no está instalado.

## 8. Riesgos y mitigación

1. **[HIGH] Interbloqueo entre el recálculo y `freeze`, `cancel`, `sell` o `register`.** S4A-D2 (orden D3, una transacción por socio, reintento y omisión), S4A-D57 (sin dormir con candados), `test_expirations_lock_order.py` (AST) y `test_recompute_lock_order.py` (`dos_sesiones`).
2. **[HIGH] La cadena real da "rota" en B3.14.** Parada del sprint con contexto; no es del código nuevo (`canonical` y `chain_hash` no cambian). Mitigación previa: `test_audit_chain.py` intacto y la fábrica de B3 calcula los hashes con la misma `canonical`.
3. **[HIGH] El candado de verificación queda tomado o la tarea 202 corre sin él.** S4A-D44 (`AUTOCOMMIT`, `invalidate`, plazo, cancelación) con las pruebas de H-2; la CLI usa el mismo camino.
4. **[HIGH] Una corrida con fecha adelantada llega a `apex-db-1`.** S4A-D48 (`--simulate`, `_sim`, guarda de `ENV`), S4A-D63 (copia en `db_test`), comprobación en V10 (`max(at) <= now()`, sin filas `*_sim`).
5. **[MEDIUM] Cobertura al quitar el `omit`.** `main.py` del worker delgado, pruebas de CLI en B1, `run-gates.sh` en B2.8, B3.13, B8.9 y V9; si baja de 80 %, pruebas nuevas dentro del slice.
6. **[MEDIUM] Las trece pruebas literales rompen fuera del gate.** Cada una tiene su paso Rojo (sección 10, C1 a C10); `tests/architecture` corre en todos los gates.
7. **[MEDIUM] Verificación larga contra Nginx de 60 s.** Umbral síncrono calibrado, lote de 1.000 con cesión del loop, 202 con sondeo acotado.
8. **[MEDIUM] Fuga de blobs, `reference` o correos en tablero, historial y detalle.** Marcador (D52), vista reducida (D28/D51), `fields` sin valores (D20), `user_names_for` (D54), y las pruebas que buscan `apx1.`, `reference`, `void_reason` y `@` en la respuesta serializada completa.
9. **[MEDIUM] `read_only: true` rompe el arranque del worker** (escrituras de `__pycache__` o de APScheduler). Python tolera `PermissionError` al escribir `.pyc`; `tmpfs /tmp` cubre el latido. Si el contenedor no arranca en W0-2.3, se agrega `PYTHONDONTWRITEBYTECODE=1` al servicio (sin tocar la imagen) antes de pensar en quitar `read_only`; se anota.
10. **[MEDIUM] Worker y `tools` con código viejo.** Binds de desarrollo (W0-1), `restart worker` tras cada cambio, buildx en W0-2.3, B8.9 y V2.
11. **[MEDIUM] Las tres variables nuevas rompen `test_env_example.py` o el `grep -c` de la CI.** B3.8 cambia los cuatro sitios en el mismo paso; V4 anota el 11.
12. **[MEDIUM] `isolation_level="AUTOCOMMIT"` choca con `test_guarded_calls.py` (L-11 del Sprint 3).** B3.4 abre la excepción única con control negativo.
13. **[LOW] El resumen cacheado del api no se invalida desde el worker.** Derivado (S4A-D1, S3-D93); RUNBOOK §11.
14. **[LOW] `e2e-stack` arranca el worker y recupera el ciclo tras las 07:00 de Bogotá.** Con la base de CI vacía no escribe; las specs no dependen de `job_runs` (D59).
15. **[LOW] P2-1 tarda ~10 minutos por el tope de `admin-write`.** Script de ritmo; alternativa anotada: correrlo dentro de la ventana de V4 con los topes ×100.
16. **[LOW] `cli.py` o `plans/service.py` superan el tope.** S4A-D72 fija la partición y el momento de medirla.

## 9. Rollback por migración

Regla general (RUNBOOK §6): (1) `$DC exec api alembic downgrade <revisión anterior>`; (2) `git revert <sha>` del checkpoint; (3) `$DC restart api` y `$DC restart worker`. Si se revierte primero el código, el archivo de migración desaparece y el arranque falla con "Can't locate revision". Volcados: `docs/scratch/sprint-04a-antes-0012.dump` y `-0013.dump` (completos, 600, borrados en V12); restaurar es `pg_restore --clean` sobre `apex-db-1` con el api y el worker detenidos.

- **`0013_audit_verifications`:** `downgrade 0012_worker_job_runs` ejecuta `DROP TRIGGER verifications_forbid_mutation`, `DROP TRIGGER verifications_forbid_truncate`, `DROP INDEX ix_verifications_finished_at` y `DROP TABLE audit.verifications`; no toca `audit.forbid_mutation()` ni `audit.audit_log` (las filas `verify` de la cadena quedan y la cadena sigue íntegra). Se revierten B3 y posteriores (B4 a B8, F1 a F4).
- **`0012_worker_job_runs`:** `downgrade 0011_payments_immutability` borra los dos índices y `worker.job_runs` (bitácora de desarrollo). Se revierten B1 y posteriores; `compose.yml` vuelve al perfil (W0-2 revertido antes que B1). Los `status` que el job corrigió en `memberships` se quedan (son el estado efectivo real) y la auditoría también.
- W0-1, W0-2, B2, B4 a B8 y F1 a F4 no tienen migración: su rollback es `git revert` del checkpoint y `$DC up -d api` (y `restart worker`).
- En CI y `db_test` no hace falta rollback: `migrated_database` migra desde cero y `test_downgrade_a_base_vacia_y_vuelta_a_head` ejercita los dos `downgrade`.

## 10. Trazabilidad

### Condiciones para VERDE del impacto (C1 a C13) y su paso

- **C1** (B1: `test_audited_tables`, `test_core_import_direction`, `conftest`, `env.py`, `omit`, `core/alerts.py`, constantes de horario): pasos 11, 12, 13, 15, 17.
- **C2** (W0-1 healthcheck con perfil; W0-2 sin perfil, aserción invertida, smoke, buildx, binds): pasos 3, 4, 5, 22, 23, 24, 25, 27.
- **C3** (B2: privado en `PRIVATE_HELPERS`, sin `with_for_update`, lote por socio, `dos_sesiones`, eventos en `SUSCRIPTORES_ESPERADOS` con lista vacía por S4A-D1, `perf`, CLI con `--date --simulate` y `--as`): pasos 29, 30, 31, 32, 33.
- **C4** (B3): pasos 40 a 50.
- **C5** (B4): pasos 54 a 58.
- **C6** (B5): pasos 64, 65, 66, 67.
- **C7** (B6, con el matiz sin `bus.batch`): pasos 73, 74, 75.
- **C8** (B7, con "Socios con él" resuelto por `counts_active_by_plans`): pasos 79 a 83.
- **C9** (B8 y `display_name` por S4A-D19/D54): pasos 54, 57 (auth), 89, 90, 93.
- **C10** (front): pasos 100, 101, 107, 108, 114, 115, 121, 122.
- **C11** (migraciones, volcados, ciclo, `alembic heads`): pasos 2, 14, 20, 39, 44, 52 y V2.
- **C12** (cobertura y `run-gates.sh` en B2 y B3): pasos 17, 36, 51 (y 97, V9).
- **C13** (T-DOC y cierre de la revisión de diseño previa): paso 6 (y V1).

### Revisión de seguridad del diseño

- **H-1:** B3 (pasos 40, 43, 44, 45, 48, 52). **H-2:** B3 (pasos 40, 42, 43, 46, 47, 50).
- **M-1:** B3 (40, 42, 46), B4 (54, 55, 56, 58), B5 (64, 65, 66, 67), B8 (89, 90, 91, 93). **M-2:** B4 (54, 55, 56, 57, 58). **M-3:** B3 (40, 42, 43, 46, 48). **M-4:** B1 (13, 16), B2 (29, 31, 33, 34, 37), W0-1 (6, `.env.example`). **M-5:** W0-1 (3, 4), W0-2 (22). **M-6:** B6 (73, 74, 75, 76), B5 (64, 66). **M-7:** B8 (89, 91, 92).
- **LOW:** L-1 en B4 (54, 56, 58) y F1 (100, 101); L-2 en B2 (31, 33) y B3 (43, 47); L-3 en B4 (54, 55, 56, 57), B5 (65, 67), B8 (90, 93); L-4 en B1 (13, 15, 16); L-5 en B1 (13, 16); L-6 en B2 (30, 32); L-7 en F1 (101, 102); L-8 en W0-2 (22), F1 (101, 105), F3 (122, 126), V9; L-9 en B7 (81, 84) y V12; L-10 en B4 (55), B8 (90). Ninguno se difiere.

### Historias y demo

US-113 → W0-1, B1, W0-2 (demo 1 y 2); US-094 → B2 (demo 2); US-104 y US-105 → B3 y F1 (demo 3); US-102 y US-103 → B4 y F1 (demo 3); US-106 → B5 y F2 (demo 4); US-077 → B6 (sin demo: lo consume el Sprint 5); US-080, US-081, US-082 → B7 y F4 (demo 6); US-108, US-110 → B8 y F3; US-109 → F3 (demo 5; T8 a 4B).

### Deuda heredada del Sprint 3 con dueño 4A

"Socios con él" (B7, F4); job de vencimientos y eventos (B2); historial y congelaciones sin `subject_member_id` (B5, por el `update` de la membresía); `display_name` (B4: parte local; columna a v0.2 con dueño); `omit` de `cli.py` y `worker/` (B1); `plans.update` sin bloquear filas de `memberships` (B7); `DELETE /plans/{id}` y P2-1 (B7, V12); borrado de volcados (V12).

### Lo que pasa al Sprint 4B o a versiones futuras (con dueño)

`display_name` como columna (v0.2, con EP-04); rol de base separado y `25P03`/`crypto_ops` como 503 (S4B-W0-2); `/health` con `job_runs` (US-115, v0.2); `sign-audit` y anclaje externo firmado (v0.3); `notifications.service` en `CONTACT_CALLERS` y `keys:ro` en el worker (Sprint 5); T8 de US-109 (US-111, 4B); S3-D98 (backlog v0.2 con EP-16); 413 de Nginx con envelope (v0.3).

## 11. Riesgos y supuestos que plan-critic debe atacar

1. **`read_only: true` en el worker con la imagen actual** (riesgo 9): supone que el entrypoint no escribe fuera de `/tmp`. Verificar `api/Dockerfile` (usuario 10001, `WORKDIR /app`, `.venv`) y que APScheduler no persiste nada en disco.
2. **`docker compose run -e DATABASE_URL`** toma el valor de la shell y lo antepone a `env_file`: supuesto de precedencia de Compose (documentado) que B2.9 depende de; si falla, la alternativa es un `env_file` temporal en el scratchpad apilado con `-f` de un override de desarrollo.
3. **`createdb`/`pg_restore` en `apex-db_test-1`**: supone que el contenedor `db_test` (tmpfs) tiene espacio para la copia de `apex` (~ decenas de MB) y que el `pg_restore --no-owner` de un volcado completo (incluidos `crypto` y `auth`) no exige extensiones ausentes (`btree_gist` está en la imagen).
4. **`isolation_level="AUTOCOMMIT"` sobre `AsyncConnection` de asyncpg** y `pg_try_advisory_lock` de sesión: supone que SQLAlchemy no envuelve la sentencia en `BEGIN` con esa opción y que `invalidate()` cierra la conexión física (libera el candado de sesión). La prueba H-2 de B3.5 lo verifica con `idle_in_transaction_session_timeout` bajo.
5. **`test_guarded_calls.py` L-11** prohíbe `isolation_level` en `execution_options`: la excepción única de B3.4 debe quedar antes del Verde o el gate de arquitectura cae en todos los slices posteriores.
6. **El conteo `8` del `grep -cE` de `ci.yml`** y el mensaje "se esperaban 8 cubetas" pasan a 11 en B3.8; si `.env.example` ordena las variables de otro modo el `sed` sigue valiendo (línea a línea).
7. **`staff-read` compartida entre `GET /audit`, `/audit/{seq}`, `/members/{id}/audit` y `/dashboard`** a 120/min por usuario: la pantalla de Inicio con `refetchOnWindowFocus` más el historial con `useInfiniteQuery` podrían rozarlo en una sesión intensa; V4 sube el tope ×100 solo para E2E. Si plan-critic lo considera corto, se sube el default a 240 en B3 (una línea en `Settings` y `.env.example`).
8. **`MAX_AUDIT_OFFSET = 100_000` con `PageParams`**: supone que `PageParams` admite un tope por ruta sin tocar `core/pagination.py` (validación en el router o en `AuditListQuery`); si no, el 422 se emite desde el service con `AuditRangeInvalid(field="offset")`.
9. **Orden del front F1, F2, F4, F3** frente a la numeración: F4 antes que F3 porque B7 cierra antes que B8; plan-critic debe confirmar que ningún archivo compartido (`routeTable.ts`, `routes.reference.ts`, `errorCodes.ts`) genera conflictos de rebase entre F2 y F4 (tocan filas distintas).
10. **La primera corrida real del job en W0-2.4** usa el marcador (no toca datos); la primera corrida con datos es B2.9 y deja decenas de filas `update` en `apex-db-1`: aceptado y documentado (S4A-D1), pero es irreversible salvo restaurar el volcado de W0-1.2.
11. **`SYNC_VERIFY_MAX_ROWS` calibrado en B3.12 paso 8** después del Verde: si cambia, se vuelve al gate 2 de B3.12; plan-critic puede exigir que la calibración vaya antes del gate que sella (ya está: el gate 10 sella después del paso 8).
12. **`test_toda_clave_del_catalogo_tiene_ruta_salvo_las_pendientes`** debe admitir `staff-read` como pendiente en B3: supone que la prueba tiene una lista de pendientes editable (el nombre lo sugiere; se verifica en B3.4).
13. **`tests/integration/`** como carpeta nueva: supone que `pyproject.toml` no restringe `testpaths` a subcarpetas conocidas (el gate con lista lo acepta; `run-gates.sh` recorre `tests/`).
14. **Suite en dos mitades** fuera de `run-gates.sh`: supone que `tests/conftest.py` no depende del orden global (ya se corrió así en el Sprint 3).
15. **El admin desechable** (S4A-D71) necesita una sesión del admin real para crearlo: el operador la aporta una vez (como en la validación final del Sprint 3); si no está disponible, `tools seed` con un `.env.seed` efímero solo crea un admin cuando no existe ninguno activo, así que la vía es `issue-reset-link` del admin real entregada al usuario, nunca un reset silencioso.

## 12. Conteo

- **Slices:** 14. W0-1, B1, W0-2, B2, B3, B4, B5, B6, B7, B8; F1, F2, F4, F3 (orden de ejecución).
- **Pasos:** 127 numerados globalmente (W0-1 10; B1 11; W0-2 7; B2 10; B3 15; B4 10; B5 9; B6 6; B7 10; B8 11; F1 7; F2 7; F4 7; F3 7), más 12 pasos de validación (V1 a V12): **139** en total.
- **Checkpoints:** 14 (más los commits `docs(sprint-04a): evidencia de ...` y los de la validación).
- **Migraciones:** 2 (`0012`, `0013`); ninguna condicional.
- **Endpoints:** 10 nuevos más `active_members_count` en `GET /plans` y `GET /plans/{plan_id}`.
- **Pruebas de arquitectura nuevas:** 7 (`test_worker_boundaries`, `test_expirations_lock_order`, `test_user_refs_scope`, `test_audit_subject`, `test_crypto_bus_importers`, `test_contact_callers`, `test_read_modules`) y 13 ampliadas en su Rojo (sección 10, C1 a C10).
- **Cubetas nuevas:** 3 (`staff-read`, `audit-verify`, `audit-verify-hour`); variables `USER_*`: 11.
- **Decisiones del bloque "Sprint 4A":** S4A-D1 a S4A-D42 en forma final, S4A-D43 a S4A-D61 de seguridad con opción final, S4A-D62 a S4A-D74 de este plan.
- **`run-gates.sh`:** 4 corridas (B2.8, B3.13, B8.9, V9).
- **Reconstrucciones con buildx:** api en W0-2.3, B8.9 y V2; web en F1.6, F2.6, F4.6, F3.6 y V2.
