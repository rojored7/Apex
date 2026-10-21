# 09 · Plan de sprints

Fecha: 21 de octubre de 2026. Iteración 2, después de la crítica de `plan-critic` (`CRITICA.md`). Los hallazgos se corrigen con las decisiones del orquestador; la sección "Cambios de la iteración 2" los lista.

Entradas, en orden de precedencia (manda la de arriba):
- `DECISIONES.md`: las secciones B, D y E se dan por resueltas; la sección A es un bloqueo previo del Sprint 0.
- `CLAUDE.md`.
- `08_implementation_breakdown/`: el README, los 119 desgloses de v0.1 y los 13 `BREAKDOWN.md` de v0.2 a v1.0.
- `07_user_stories/README.md`: 199 historias, puntos y orden sugerido.
- `06_epics/README.md`: grafo y ruta crítica.
- `04_architecture_decision.md`, `05_service_design.md` y `03_context_map.md` sección 4.

## Resumen

- Son **12 sprints**: 0, 1, 2, 3, 4A, 4B y del 5 al 10.
- **v0.1 completa** va del Sprint 0 al 4B, con slices detallados: EP-00 a EP-13, 119 historias, 379 puntos y 1.720 h relativas.
  - El antiguo Sprint 4 se partió en 4A y 4B (M-8).
  - El Sprint 4A lleva el worker, la auditoría verificable, el tablero y los planes que faltaban.
  - El Sprint 4B lleva la continuidad operativa y la release `v0.1.0`.
- **v0.2 a v1.0** van en los Sprints 5 a 10, uno por versión, sin slices detallados: EP-14 a EP-26, 80 historias, 311 puntos y 1.310 h relativas.
- Las 199 historias tienen sprint asignado, cada una en un solo sprint, y ninguna queda fuera.
- **Estados:** 17 historias de v0.1 y 8 posteriores tenían estado NEEDS_REFINEMENT o ARCHITECTURAL_GAP_DETECTED. `DECISIONES.md` sección E acepta la propuesta por defecto de todas, así que se tratan como READY.
- **Entregable de v0.1, al cerrar el Sprint 4B:**
  - `docker compose up` en el servidor del gimnasio;
  - login por rol;
  - socios cifrados;
  - planes;
  - venta, renovación, congelación y anulación de membresías;
  - pagos inmutables;
  - auditoría verificable;
  - tablero;
  - worker de vencimientos;
  - backup cifrado y verificado;
  - restauración probada;
  - rotación de llaves;
  - importación desde Excel.

## Supuestos de dimensionado

- **Quién ejecuta.** Claude Code con agentes. Se dimensiona por slice verificable y por dependencias, no por horas-persona. Las horas del desglose se usan solo como peso relativo.
- **Tamaño de un sprint.** Cada uno cabe en una sesión larga de agentes: entre 20 y 35 historias de v0.1, o un bloque coherente.
  - El Sprint 0 (203 h) es arranque en frío.
  - Los Sprints 1 a 3 van de 365 a 389 h.
  - Los Sprints 4A (215 h) y 4B (174 h) quedan por debajo a propósito: son cierre e infraestructura irreversible, y ahí conviene un margen.
- **Orden fijo de agentes en cada sprint:**
  1. Wave 0, infraestructura (`devops-wsl2-docker`).
  2. Waves 3a/3b, backend (`backend-qa-executor` y luego `backend-implementor`).
  3. Waves 5a/5b, front (`frontend-qa-automation` y luego `frontend-ux-engineer`).
  4. Validación.
  5. Revisión de seguridad.
- **Rojo y verde se alternan por slice (B-1).** Dentro de las waves 3 y 5, cada slice tiene su propio rojo y su propio verde:
  1. 3a escribe las pruebas del slice;
  2. 3b implementa;
  3. se pasa el gate;
  4. se pasa al slice siguiente.

  Nunca queda una wave entera en rojo.
- **Slice.** Agrupa de 1 a 4 historias que pasan juntas `slice-gate.sh` con su lista de archivos y se confirman con un solo `checkpoint-commit.sh`. Cada slice deja el proyecto en verde.
- **Dependencias.** Hay dos tipos:
  - **De bloqueo:** nunca se violan.
  - **De cierre o de consumidor:** el desglose las marca como "no bloquea", "suave", "consumidor" o "punto de extensión". Se declaran como **criterio diferido**, con el slice o el sprint que las cierra.
- **Migraciones.** Van en orden estricto de `0001` a `0013`, con números definitivos:
  - del `0008` al `0011`, en el Sprint 3;
  - `0012` y `0013`, en el Sprint 4A.
- **Front.** Una pantalla entra en el mismo sprint que su API, o en el siguiente; nunca antes.
- **Gate humano previo.** Se aprueba `DECISIONES.md` sección A, en particular D1: el front va en `web/`. Si D1 no se aprueba, salen las waves 5 de todos los sprints y la EP-06 completa (126 h).

## Índice de sprints

| Sprint | Versión | Objetivo | Historias | Puntos | Horas relativas | Waves | Entregable demostrable |
|---|---|---|---|---|---|---|---|
| [Sprint 0](SPRINT-00.md) | v0.1 | Terreno, gates y esqueleto ejecutable | 17 | 48 | 203 | 0, 3a/3b, 5a/5b | Línea base del entorno, `docker compose up -d --build` con `/health` en verde, `pytest` contra `db_test`, CI con licencias, gates con mapeo, esqueleto del front |
| [Sprint 1](SPRINT-01.md) | v0.1 | Núcleo de auditoría, bus de criptografía y seguridad de plataforma | 28 | 83 | 365 | 0, 3a/3b, 5a/5b | `tools init-keys` (KEK, firma y JWT), DEK por `ensure_keys`, cadena de auditoría con trigger, blob `apx1.`, rutas sin rol que fallan, CSP con nonce, kit del front |
| [Sprint 2](SPRINT-02.md) | v0.1 | Identidad, configuración, shell del front, primeros socios y planes | 26 | 87 | 374 | 0, 3a/3b, 5a/5b | Login por rol, usuarios con activación, configuración, crear socio y verlo cifrado en la base, crear plan |
| [Sprint 3](SPRINT-03.md) | v0.1 | Membresías, pagos y ficha del socio | 25 | 78 | 389 | 3a/3b, 5a/5b (la Wave 0 solo verifica) | Vender con primer pago, cobertura, renovar, congelar, anular, pago inmutable, ficha con revelado auditado |
| [Sprint 4A](SPRINT-04A.md) | v0.1 | Worker, auditoría verificable, tablero y planes restantes | 14 | 44 | 215 | 0, 3a/3b, 5a/5b | Worker de vencimientos, verificación de la cadena por pantalla y CLI, historial del socio, Inicio con KPI, editar y dar de baja planes |
| [Sprint 4B](SPRINT-04B.md) | v0.1 | Continuidad operativa y release v0.1 | 9 | 39 | 174 | 0, 3a/3b | Seed de demostración, importación de Excel, backup cifrado verificado, restauración, respaldo de KEK, rotación, despliegue seguro, ADR, `v0.1.0` |
| [Sprint 5](SPRINT-05.md) | v0.2 | OpenBao, avisos de vencimiento, recibos y exportaciones | 20 | 78 | 323 | todas | KEK en OpenBao, "por avisar hoy" con WhatsApp y correo, recibo PDF, CSV |
| [Sprint 6](SPRINT-06.md) | v0.3 | Auditoría firmada, llaves, adjuntos y TLS híbrido | 14 | 53 | 217 | todas | Firma nocturna, pantalla de llaves con CBOM, foto y autorización, Caddy con X25519MLKEM768 |
| [Sprint 7](SPRINT-07.md) | v0.4 | Clases, horario y check-in | 11 | 39 | 164 | todas | Horario, sesiones generadas, check-in con advertencias, descuento de clases |
| [Sprint 8](SPRINT-08.md) | v0.5 | Movimientos, WODs, resultados y TV | 13 | 49 | 213 | todas | WOD del día, resultados en tablet, leaderboard, TV con token |
| [Sprint 9](SPRINT-09.md) | v0.6 | Perfil del atleta | 7 | 26 | 109 | 3a/3b, 5a/5b | Medidas cifradas, RM derivados, benchmarks |
| [Sprint 10](SPRINT-10.md) | v1.0 | Portal del socio y cierre post-cuántico | 15 | 66 | 284 | todas | Portal de 5 pestañas, push de récord, backups firmados, ML-KEM |
| **Total** | | | **199** | **690** | **3.030** | | |

## Historias por sprint

- **Sprint 0 (17):** US-001, US-002, US-003, US-004, US-005, US-006, US-007, US-008, US-009, US-010, US-011, US-012, US-013, US-014, US-017, US-018, US-020.
- **Sprint 1 (28):** US-015, US-016, US-019, US-021, US-022, US-023, US-024, US-025, US-026, US-027, US-028, US-029, US-032, US-033, US-034, US-035, US-036, US-037, US-038, US-039, US-040, US-041, US-059, US-060, US-063, US-064, US-065, US-066.
- **Sprint 2 (26):** US-031, US-042, US-043, US-044, US-045, US-046, US-047, US-048, US-049, US-050, US-051, US-052, US-053, US-054, US-055, US-057, US-058, US-061, US-062, US-067, US-068, US-069, US-070, US-078, US-079, US-107.
- **Sprint 3 (25):** US-056, US-071, US-072, US-073, US-074, US-075, US-076, US-083, US-084, US-085, US-086, US-087, US-088, US-089, US-090, US-091, US-092, US-093, US-095, US-096, US-097, US-098, US-099, US-100, US-101.
- **Sprint 4A (14):** US-077, US-080, US-081, US-082, US-094, US-102, US-103, US-104, US-105, US-106, US-108, US-109, US-110, US-113.
- **Sprint 4B (9):** US-030, US-111, US-112, US-114, US-115, US-116, US-117, US-118, US-119.
- **Sprint 5 (20):** EP-14 (US-120 a US-132), EP-15 (US-133 a US-136) y EP-16 (US-137 a US-139).
- **Sprint 6 (14):** EP-17 (US-140 a US-142), EP-18 (US-143 a US-146), EP-19 (US-147 a US-151) y EP-20 (US-152 y US-153).
- **Sprint 7 (11):** EP-21 (US-154 a US-164).
- **Sprint 8 (13):** EP-22 (US-165 a US-174) y EP-23 (US-175 a US-177).
- **Sprint 9 (7):** EP-24 (US-178 a US-184).
- **Sprint 10 (15):** EP-25 (US-185 a US-195) y EP-26 (US-196 a US-199).

Historias que cambian de lugar respecto al orden sugerido de `07_user_stories/README.md`:
- **US-031, al Sprint 2.** Su primera tabla real es `members`.
- **US-030, al Sprint 4B.** Va después del respaldo de la KEK (US-116), en el mismo slice.
- **US-107, al Sprint 2.** Así los login de los Sprints 2 y 3 quedan auditados.
- **US-056, al Sprint 3.** El router de `payments` lo crea US-095.
- **US-080, US-081 y US-082, al Sprint 4A.** Sus pruebas conjuntas con US-084 y con `count_active_by_plan` quedan sin dobles.
- **US-094 y US-113, al Sprint 4A.** El orden de migraciones obliga: `0012` va después de `0011`.

## Mapa de dependencias entre sprints

`A → B` significa que B necesita A cerrado.

```
Sprint 0 (EP-00, EP-01 mínimo; 0001)
 └─► Sprint 1 (EP-01 resto, EP-02, EP-03, US-041, kit; 0002–0004)
      └─► Sprint 2 (EP-04, EP-05, shell, socios y planes base, US-107; 0005–0007)
           └─► Sprint 3 (EP-09, EP-10, ficha; 0008–0011)
                └─► Sprint 4A (worker, EP-11, EP-12, planes restantes; 0012–0013)
                     └─► Sprint 4B (EP-13 resto, US-030) = release v0.1
                          ├─► Sprint 5 (v0.2: EP-15 → EP-14, EP-16)
                          │    └─► Sprint 6 (v0.3: EP-17, EP-18, EP-19, EP-20)
                          ├─► Sprint 7 (v0.4: EP-21)   [técnicamente solo necesita el Sprint 4A]
                          │    └─► Sprint 8 (v0.5: EP-22, EP-23)
                          │         └─► Sprint 9 (v0.6: EP-24)
                          └──────────────► Sprint 10 (v1.0: EP-25, EP-26)
                                            necesita los Sprints 5, 6, 8 y 9
```

Dependencias que no siguen la cadena:
- **Sprint 6 necesita el 5:** EP-17 y EP-18 dependen de EP-15, y EP-17 usa `core/alerts.py` (G-08, que llega con US-126).
- **Sprint 7** depende solo de US-108 y US-113 (Sprint 4A) y de lo anterior. Se puede adelantar a los Sprints 5 y 6 si el negocio lo pide. No necesita la release.
- **Sprint 10** necesita:
  - EP-14 y EP-16, del Sprint 5;
  - EP-17, EP-18 y EP-20, del Sprint 6;
  - EP-22, del Sprint 8;
  - EP-24, del Sprint 9;
  - el backup y el respaldo de la KEK, del Sprint 4B.

## Ruta crítica entre sprints

Sprint 0 → 1 → 2 → 3 → 4A → 4B → 7 → 8 → 9 → 10.

Coincide con la ruta crítica de épicas: EP-00 → EP-01 → EP-02 → EP-07 → EP-09/EP-10 → EP-12 → EP-21 → EP-22 → EP-24 → EP-25. Los Sprints 5 y 6 van por fuera de la ruta, pero tienen que cerrar antes del Sprint 10. Si se adelanta el Sprint 7, la ruta crítica se acorta: el Sprint 7 deja de esperar al 4B.

Ruta crítica de historias en v0.1:
- **Sprint 0:** US-001 → US-002 → US-011 → US-012.
- **Sprint 1:** US-015 → US-016 → US-023/US-024 → US-025 → US-028.
- **Sprint 2:** US-069.
- **Sprint 3:** US-084 → US-095 → US-096 → US-085 → US-086 → US-092.
- **Sprint 4A:** US-113 → US-094; US-104 → US-108.
- **Sprint 4B:** US-116 → US-030; US-114 → US-115 → US-118.

## Convención de comandos

- Todos los comandos se corren desde la raíz del repositorio.
- En las demos, `docker compose` abrevia `docker compose -f infra/compose.yml -f infra/compose.dev.yml`. El Sprint 4B usa solo `infra/compose.yml`, porque es el stack de producción.
- Todas las demos levantan el stack con `docker compose up -d --build` (M-7).
- **Dentro de los contenedores no hay `uv` (B-3).** El runtime trae `PATH=/app/.venv/bin`:
  - `docker compose exec api alembic current`;
  - `docker compose run --rm tools <comando>`: `tools` tiene `entrypoint: ["python", "-m", "app.cli"]`, por ejemplo `tools init-keys`, `tools seed` o `tools rotate-key`;
  - `docker compose run --rm worker python -m app.worker.main --run-once <job>`.
- En el host, `cd api && uv run ...` se usa para pruebas, lint y mypy.
- Si el puerto 80 está ocupado, se define `WEB_PORT` en `.env` (A-4) y las URLs pasan a `http://localhost:${WEB_PORT:-80}`.

## Cómo se cierra un sprint (gates)

### Por slice (B-1), en las waves 3 y 5

1. **Rojo**, a cargo de `backend-qa-executor` o `frontend-qa-automation`:
   - crea los **stubs vacíos** de los módulos que el slice va a tocar (funciones con `raise NotImplementedError`, componentes que devuelven `null`), para que las pruebas importen;
   - escribe las pruebas del slice;
   - comprueba que fallan por falta de comportamiento. Que una prueba falle por import ya no se acepta como rojo, porque el stub existe;
   - confirma con un commit normal: `test(<modulo>): ... (rojo)`.
2. **Verde**, a cargo de `backend-implementor` o `frontend-ux-engineer`: implementa hasta que pasa `scripts/workflow/slice-gate.sh <modulo> <archivos del Rojo>`.
3. Si el slice incluye una migración, corre el ciclo `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`. Antes de `0002` y `0011` se hace un volcado `pg_dump` de la base de desarrollo.
4. Antes del checkpoint, `git status` debe mostrar solo cambios del slice, porque `checkpoint-commit.sh` hace `git add -A`.
5. `scripts/workflow/checkpoint-commit.sh "<slice>: <historias>"`. Solo funciona con el sello vigente, nunca sobre `main` y nunca hace push.

### Por wave

- `scripts/workflow/run-gates.sh`, con la suite completa:
  - api con cobertura global de `app` de al menos 80 %;
  - front con lint, tsc, test con cobertura y build.

### Al cerrar el sprint (Definición de hecho común)

1. Suite completa en verde:
   - `run-gates.sh`;
   - `cd api && uv run pytest tests/architecture -q`;
   - paso de CI de US-021 (`docs/openapi.json` al día);
   - licencias.
2. Integración y E2E:
   - pruebas de service contra `db_test`, con `TEST_DATABASE_URL` obligatoria;
   - specs de Playwright del sprint, contra el stack levantado con `--build`.
3. Smoke:
   - `docker compose -f infra/compose.yml up -d --build`;
   - `scripts/ci/compose-smoke.sh`;
   - recorrido de la demo, con evidencia.
4. Seguridad: `security-reviewer` sobre el diff del sprint. Cero CRITICAL y cero HIGH sin resolver. Checklist mínima:
   - gitleaks;
   - rol en todas las rutas;
   - nada sensible en claro;
   - `banned-api` intacto.
5. `verify-delivery`, con los dos pilares, incluidos los criterios diferidos.
6. **Paso humano explícito (A-2):** una persona empuja la rama, abre el PR, comprueba que la CI está en verde y hace el merge. Los scripts nunca hacen push.

Un sprint no se cierra con un criterio diferido sin escribir, ni con una prueba en `skip` que no tenga una historia dueña.

**Cobertura (M-6).** El umbral es global sobre `app` (`--cov=app --cov-fail-under=80`), no por módulo. Hasta el Sprint 3, `run-gates.sh` excluye `src/app/cli.py` y `src/app/worker/*` con `--cov-omit`, documentado en US-008. Desde el Sprint 4A entran en la cobertura.

## Ajustes al flujo que este plan pide

### A-01 · `slice-gate.sh` ampliado (Sprint 0, dentro de US-008; B-1, B-2 y A-5)

**Firma:** `scripts/workflow/slice-gate.sh <modulo> [archivos de prueba...]`.
- Con lista de archivos, corre solo esos archivos más `tests/architecture`.
- Sin lista, corre la carpeta de pruebas del módulo más `tests/architecture`.
- **`tests/architecture` corre siempre (A-5).** Así, las mitigaciones que dependen de pruebas de arquitectura, por ejemplo `test_members_encrypted_at_rest.py` o `test_service_import_graph.py`, bloquean de verdad cada checkpoint.

**Qué corre:**
- api: `uv run ruff check`, `uv run ruff format --check` y `uv run mypy` sobre la ruta de código del módulo, y después `uv run pytest` sobre la lista de archivos más `tests/architecture`;
- front: `npx eslint` y `npx tsc --noEmit` solo sobre los archivos que el slice toca (`git diff --name-only` contra la base del slice, más la lista de archivos), y después `npx vitest run` sobre la lista de archivos.

**Mapeo de módulos** (se escribe como lista para respetar la regla de formato: sin tablas fuera del índice):
- api:
  - `core/<x>`: código en `api/src/app/core/<x>.py` o en `api/src/app/core/<x>/`; pruebas en `api/tests/core`.
  - `crypto`: código en `api/src/app/core/crypto/`; pruebas en `api/tests/crypto`.
  - `<modulo>` (`auth`, `settings`, `members`, `plans`, `memberships`, `payments`, `audit` y, desde v0.2, los demás): código en `api/src/app/modules/<modulo>/`; pruebas en `api/tests/<modulo>`.
  - `dashboard`: código en `api/src/app/modules/dashboard/`; pruebas en `api/tests/dashboard`.
  - `main`: código en `api/src/app/main.py`; pruebas en `api/tests/core`, en los archivos de arranque y salud. Reemplaza al antiguo `core/main`.
  - `worker`: código en `api/src/app/worker/`; pruebas en `api/tests/worker`.
  - `cli`: código en `api/src/app/cli.py`; pruebas en `api/tests/cli`.
  - `architecture`: sin ruta de código propia, solo `api/tests/architecture`. Con lista de archivos, sirve para pruebas que viven en la raíz de `api/tests/`, como `test_ci_database.py`.
  - Pruebas fuera de la carpeta del módulo (`tests/migrations`, `tests/integration`): se pasan por la lista de archivos.
- front:
  - `web/<feature>`: `web/src/features/<feature>`. Por ejemplo, `web/auth`, `web/system`, `web/members`, `web/plans`, `web/memberships`, `web/payments` y `web/dashboard`.
  - `web/shared`: `web/src/shared`.
  - `web/core`: `web/src/core`.
  - `web/layouts`: `web/src/layouts`.
  - `web/app`: `web/src/App.tsx`, `web/src/routes*`, `web/src/config`, `web/src/styles` e `index.html`, más `web/tests/unit` y `web/tests/lint`.

**Validación del nombre** (reemplaza la de T14 de US-008): `^(web/)?[a-z][a-z0-9_-]*(/[a-z][a-z0-9_-]*)*$`. Acepta guiones y varios niveles. Cada archivo de la lista debe existir dentro de `api/tests/` o de `web/`.

**Notación única en todos los sprints:** `web/<feature>`, no `web/features/<x>`, y `main`, no `core/main`.

**Cobertura:**
- `run-gates.sh` aplica `--cov=app --cov-fail-under=80`.
- Desde el Sprint 0 y hasta el Sprint 3, usa `--cov-omit=src/app/cli.py,src/app/worker/*`.
- El ajuste se documenta en `scripts/workflow/README.md` y en US-008.

**Costo estimado:** entre 3 y 4 h dentro de US-008. No cambia otras historias.

### A-02 · Ramas, commits y push (A-2)

1. `main` ya tiene commits, entre ellos el plan, esta crítica y `.gitattributes`, que ya incluye `eol=lf` y `*.woff2 binary`.
2. Antes del Sprint 0, se corre `git status` y se revisan los cambios pendientes.
3. Se crea `chore/sprint-00-cimientos` desde el `main` actual. El commit de T-DOC va en esa rama, no en `main`.
4. Cada sprint siguiente abre su rama desde `main`, después del merge del anterior.
5. Al cierre de cada sprint hay un paso humano explícito: push de la rama y apertura del PR. Los scripts no hacen push.
6. La protección de `main` (US-001) se documenta y se aplica solo si el plan de GitHub del repositorio la permite; en repos privados exige Pro o Team. Si no se puede, la regla queda como disciplina del flujo: `checkpoint-commit.sh` ya rechaza `main`.

## Riesgos por sprint

- **Sprint 0:**
  - [HIGH] El gate D1 no se aprueba. Mitigación: T-DOC bloqueante.
  - [MEDIUM] El entorno WSL2 o el puerto 80 están ocupados. Mitigación: S0-W0-0 y `WEB_PORT`.
  - [MEDIUM] Arranque en frío de los gates. Mitigación: verificación manual de los dos primeros slices.
- **Sprint 1:**
  - [HIGH] Formatos irreversibles: canónico, blob y N-02.
  - [MEDIUM] Llave JWT. Mitigación: `init-keys` en S1-B4.
  - [MEDIUM] Concurrencia de `seq`.
- **Sprint 2:**
  - [HIGH] US-069 fija el padrón con datos.
  - [MEDIUM] Refresh con varias pestañas.
- **Sprint 3:**
  - [HIGH] Nudo de membresías y pagos.
  - [HIGH] Trigger de `0011`. Mitigación: volcado previo y una prueba por columna.
- **Sprint 4A:**
  - [MEDIUM] Orden `0012` → `0013`.
  - [MEDIUM] Idempotencia del worker.
  - [MEDIUM] Cobertura al quitar `--cov-omit`.
- **Sprint 4B:**
  - [HIGH] Operaciones irreversibles con llaves.
  - [HIGH] Infraestructura nueva: backup, `age` y arranque ordenado.
  - [MEDIUM] P3 sin destino definido.
- **Sprint 5:**
  - [HIGH] Pérdida de las llaves de desellado.
  - [MEDIUM] Canales externos.
- **Sprint 6:**
  - [MEDIUM] ML-DSA en OpenBao.
  - [MEDIUM] Caddy con `x25519mlkem768`.
- **Sprint 7:**
  - [MEDIUM] Par members↔classes (G-10).
  - [MEDIUM] Tiqueteras agotadas.
- **Sprint 8:**
  - [HIGH] Trigger de `wod_results`.
  - [MEDIUM] Prueba real de la tablet.
- **Sprint 9:**
  - [MEDIUM] RM erróneo permanente. Mitigación: `invalidated_at`.
- **Sprint 10:**
  - [HIGH] Re-envoltura con ML-KEM.
  - [HIGH] IDOR en `/me/*`.
  - [MEDIUM] `liboqs`.

## Historias que quedan fuera y por qué

Ninguna de las 199 historias queda fuera. Lo que queda fuera a propósito:
- Las pantallas de referencia `Mapa`, `P_Lista`, `P_Ficha` y `P_Formulario`.
- Las rutas que no existen: `POST /memberships/{id}/renew` (Q2) y `GET /users/{id}/activation-link` (N-12).
- `GET /members/export` en v0.1: es de v0.2.
- Las migraciones condicionales `0014_*`: no hacen falta, o solo entran si una prueba de rendimiento las pide.
- Mejoras de v1.1 sin historia:
  - cierre de mes (N-27);
  - rol de recepción (P1);
  - coach que también es socio (P6);
  - latido de `crypto_jobs`.
- Avisos de bienvenida y activación (Q13).
- Si D1 no se aprueba, el front completo.

## Cambios de la iteración 2 (respuesta a `CRITICA.md`)

### Bloqueantes

- **B-1:**
  - patrón de rojo y verde por slice en esta sección "Cómo se cierra un sprint" y en las waves de los Sprints 0, 1, 2, 3, 4A y 4B;
  - `slice-gate.sh` con lista de archivos;
  - lint y tsc del front limitados a los archivos tocados;
  - stubs antes de las pruebas.
- **B-2:**
  - mapeo completo de A-01;
  - regex con guiones y varios niveles;
  - notación unificada: `web/<feature>` y `main`.
- **B-3:**
  - `COPY alembic.ini migrations ./` en `builder` y en `runtime`;
  - bind mount `../api/migrations`;
  - `alembic heads` en `test_api_image.sh` (S0-W0-4);
  - comandos de demo sin `uv run` dentro de los contenedores.

### Altas

- **A-1:**
  - `init-keys` crea `jwt_ed25519.pem` y `.pub` con modo 600 (S1-B4, con su prueba);
  - demo del Sprint 1 corregida: las DEK las crea `ensure_keys` al arrancar.
- **A-2:** A-02 reescrito: rama desde `main`, T-DOC en la rama, push y PR manuales, protección de `main` según el plan de GitHub.
- **A-3:** `test_env_example.py` sale del gate de S0-W0-4 y queda en S0-B1.
- **A-4:** S0-W0-0, línea base del entorno, con resultado en `docs/scratch/sprint-00.md`. Se agrega `WEB_PORT`, en `.env.example` y en `NON_API_ENV_VARS` de US-011.
- **A-5:** `tests/architecture` en cada gate.
- **A-6:** T8 de US-018 se cierra en S2-B7 y S3-B10. T6 de US-007 se cierra en la validación del Sprint 1.

### Medias

- **M-1:** doble de `membership_payability` en `tests/payments/conftest.py` en S3-B3; la prueba del router real pasa a S3-B4.
- **M-2:** `PrincipalLoader` doble en `conftest` desde S1-B9; `test_principal_loader.py` va en el gate de B9 por lista de archivos.
- **M-3:** S2-F4 se parte en S2-F4a y S2-F4b, cada uno con su sello.
- **M-4:** `test_reveal_entry.py` prueba `audit.record(action='reveal')` directamente en S2-B6, sin `skip`.
- **M-5:** T-DOC agrega `settings/`, `dashboard/`, `attachments/`, `tv/` y `portal/` a la estructura de `CLAUDE.md`.
- **M-6:** cobertura global; `--cov-omit` de `cli.py` y `worker/` hasta el Sprint 3.
- **M-7:** todas las demos usan `up -d --build`.
- **M-8:** el Sprint 4 se parte en `SPRINT-04A.md` y `SPRINT-04B.md`; `SPRINT-04.md` se elimina.
  - La instrucción pedía "posteriores 5 a 11 (total 12)", pero con 4A y 4B eso daría 13. Se conservan los nombres 4A y 4B y el total de 12, así que los Sprints 5 a 10 mantienen su número.

### Bajas

- La excepción de `SYSTEM_USER_ID` insertado por Alembic queda documentada en el Sprint 1 y en T-DOC.
- Se agrega un volcado `pg_dump` antes de `0002` (S1-B1) y antes de `0011` (S3-B4).
- `test_ci_database.py` usa `TEST_DATABASE_URL` y falla si no está definida, en lugar de saltarse (S0-W0-3).

## Verificación del plan

Script de conteo, corrido en la iteración 2:
- **Historias:**
  - cada historia de US-001 a US-199 aparece en exactamente una línea "Historias del sprint", sin duplicados (199 únicas);
  - por sprint: 17, 28, 26, 25, 14, 9, 20, 14, 11, 13, 7 y 15.
- **Puntos:** 48, 83, 87, 78, 44, 39, 78, 53, 39, 49, 26 y 66, que suman **690**, igual que `07_user_stories/README.md`.
- **Horas relativas:** 203, 365, 374, 389, 215, 174, 323, 217, 164, 213, 109 y 284, que suman **3.030**, igual que `08_implementation_breakdown/README.md`.
- **Migraciones de v0.1, en orden estricto:**
  - Sprint 0: `0001`;
  - Sprint 1: de `0002` a `0004`;
  - Sprint 2: de `0005` a `0007`;
  - Sprint 3: de `0008` a `0011`;
  - Sprint 4A: `0012` y `0013`;
  - Sprint 4B: ninguna.
- **Endpoints de v0.1:** 2, 0, 29, 22, 10 y 0, que suman **63**.
- **Tablas:** ninguna fuera del índice de este README.
