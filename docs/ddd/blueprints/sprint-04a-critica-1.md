# Crítica 1 del plan del Sprint 4A (plan-critic) · Veredicto: APROBADO CON OBSERVACIONES

Sobre `docs/ddd/blueprints/sprint-04a-plan.md` en `f5f2503` (rama `feat/sprint-04a-worker-auditoria-tablero`). Cero bloqueantes con evidencia de código, diez enmiendas y observaciones menores. La revisión fue de solo lectura y sin shell: no pudo ejecutar nada, así que lo marcado "sin ejecutar" queda sin comprobar.

## Bloqueantes

Ninguno.
- Los 2 HIGH (H-1, H-2) y los 7 MEDIUM (M-1..M-7) de `sprint-04a-seguridad-diseno.md` son pasos del plan. La tabla de la sección 10 los lleva a B3 (pasos 40-50), B4, B5, B6, B8, W0-1/W0-2, B1 y B2.
- Las C1..C13 también están mapeadas a pasos (sección 10).
- No se encontró ninguna prueba literal que se actualice en un slice posterior al que la rompe. Detalle en "Verificado sin hallazgo".

## Enmiendas (mandan sobre el plan)

**E1 · W0-1.6 y B1.1: dos formas del job marcador, y una no pasa `finish_run`.**
- Contradicción 12 (plan:86) dice `details={"revisados": 0, "placeholder": "S4A-B2"}`.
- S4A-D64 (plan:146) y B1.1 dicen `{"placeholder_ok": 1}`.
- `DETAIL_KEYS` (plan:92) solo admite claves enteras y trae `placeholder_ok`, no `placeholder`. La forma de la contradicción 12 haría que `finish_run` lance `ValueError`.
- Manda S4A-D64. Se borra el texto de la contradicción 12 en el bloque que va a `DECISIONES.md`.
- B1.3 afirma que `--run-once expirations` está en rojo, pero B1.1 ya deja el marcador "real". Ese caso nace verde; el Rojo real de B1 es `core/jobs`, `runner` y `schedule`. Anotarlo en el cuaderno.

**E2 · B2.5: las claves de `asdict(RecomputeSummary)` deben ser subconjunto de `DETAIL_KEYS`.**
- `DETAIL_KEYS` = `revisados, cambiadas, por_vencer, vencidas, otras, busy_omitidos, errores, placeholder_ok`.
- B2.1 no enumera los campos de `RecomputeSummary`. Si un campo no está en la lista, el job falla en producción y no en unitario.
- Se añade a B2.3 una prueba que lo exija: `set(asdict(RecomputeSummary(...))) <= DETAIL_KEYS`, con todos los valores enteros.

**E3 · B2.9: el orden de la evidencia anula el "antes".**
- El paso 1 reinicia el worker y el paso 2 toma el "antes". `serve` recupera el ciclo al arrancar con `should_run`.
- Si W0-2.4 y B2.9 caen en días distintos y ya pasaron las 07:00 de Bogotá, el reinicio ejecuta el job real antes del `SELECT count(*)`.
- Orden obligatorio: psql "antes", luego `restart worker`, luego `--run-once`. Anotar si `--status` ya muestra un intento automático.

**E4 · V2.5 y V8: parar el worker antes de cualquier `downgrade`.**
- Tras W0-2 el worker queda arriba con `restart: unless-stopped`, sin perfil.
- V2.5 hace `alembic downgrade 0011_payments_immutability`, que borra `worker.job_runs` bajo un worker vivo. Su `wait_for_database` y su latido consultan esa tabla, y el scheduler puede dispararse a las 07:00.
- Agregar `$DC stop worker` antes del `downgrade` y `$DC start worker` después, con `healthy` y `RestartCount` anotados (V2.6 ya reinicia).
- Mismo cuidado en B3.14 (`downgrade -1` borra `audit.verifications`): no afecta al worker, pero hay que dejar escrito que no hay que pararlo.

**E5 · B1.6 y B2.5: la guarda de S4A-D48 falla abierta en este equipo.**
- `.env.example:32` trae `ENV=dev` y `.env` hereda ese valor. `--date X --simulate` pasa la guarda `ENV==dev` contra `apex-db-1`.
- Eso es el riesgo 4 (falsificar `at` en la cadena inmutable). El plan lo mitiga solo con procedimiento (S4A-D63 y V10).
- Añadir una guarda dura: `--date != hoy` exige `--simulate`, `ENV=dev` y que el nombre de la base de `DATABASE_URL` termine en `_sim` o sea `apex_test`. Si no, salida 2. Se prueba con una URL `.../apex` y otra `.../apex_sim`.
- Ajustar S4A-D63 y B2.9 (la copia ya se llama `apex_sim`).

**E6 · W0-2.1 y smoke: `--run-once` puede chocar con el `serve` del mismo contenedor.**
- El smoke arranca `worker`, espera `healthy` y corre `run --rm worker ... --run-once`. Si el reloj del runner pasa de las 07:00 de Bogotá, `serve` recupera el ciclo al arrancar.
- Si coincide con el `--run-once`, el reclamo devuelve `None` y el código de salida es 3, que rompe el smoke.
- Opciones, elegir una: aceptar 0 o 3 en la primera invocación, o esperar a que `--status` muestre un `result` distinto de `running` antes de invocar.
- La segunda invocación debe seguir exigiendo 0.

**E7 · B1.10 paso 5: el contenedor endurecido solo se prueba con `--status`.**
- `--status` no importa `memberships` ni `audit`. La primera vez que el worker corre un job real sin volumen `keys` es B2.9.
- `cli_runtime` (`cli.py:291-316`) instala listeners y `load_module_services()` sin tocar el keyring, y `worker_runtime` lo repite. Es probable que funcione, pero no está demostrado en contenedor.
- Añadir a B1.10 un `--run-once expirations` (marcador) dentro del contenedor `read_only`, sin `keys`, que ejercite `load_module_services` e importe `memberships.service`.
- Si falla, se descubre en B1 y no en B2.9, con datos reales de por medio.

**E8 · F2.2: archivo de prueba inexistente.**
- `web/src/features/members/components/MemberDataTab.test.tsx` no existe. Solo hay `.tsx` y `.module.css`.
- El plan lo llama "existente, ampliado" y lo pasa por el gate sellante F2.5.3. `slice-gate.sh` aborta con "archivo inexistente" si el Rojo no lo crea.
- Redactar F2.2 como "se crea" y aplicar la regla de `ls` previo (plan:29).
- Mismo cuidado con `web/tests/e2e/audit.spec.ts` (F1.5.4, "si se crea"): el Rojo de F1 solo lista `tests/e2e/stack/audit.spec.ts`. Crear el preview o quitar la línea del gate.

**E9 · B3.8 y ci.yml:290-291: el `grep -cE` exacto de CI.**
- El patrón actual lista literales por valor (`=3000`, `=6000`, `=12000`, `=20000`, `=60000`).
- La enmienda debe añadir al patrón `^USER_READ_LIMIT_PER_MIN=12000$|^USER_AUDIT_VERIFY_LIMIT_PER_MIN=300$|^USER_AUDIT_VERIFY_LIMIT_PER_HOUR=2000$`, no solo cambiar `8` por `11`.
- Cambiar también el mensaje "se esperaban 8 cubetas" y el comentario de `.env.example` que cita el conteo.
- Nota para el implementador: son 8 variables hoy; `USER_LIMITS` tiene 9 cubetas porque `memberships-write`, `payments-write` y `admin-write` comparten variables. Con las tres nuevas serán 12 cubetas y 11 variables, como dice el plan.

**E10 · B3.8: `AUTOCOMMIT` con asyncpg y `invalidate`.**
- En SQLAlchemy async, `AsyncConnection.execution_options(...)` se **espera** (`conn = await conn.execution_options(isolation_level="AUTOCOMMIT")`).
- `test_guarded_calls.py:54-61` detecta la llamada `execution_options` con `isolation_level` por AST. La excepción de B3.4 debe aplicarse por ruta relativa exacta (`core/audit_verify.py`, `modules/audit/verify.py`), con control negativo.
- Ese control debe cubrir también `connect(...).execution_options(...)` dentro de una función.
- Fijar en la prueba H-2 que el engine de prueba use el `DB_IDLE_IN_TX_TIMEOUT_MS` bajo en `server_settings`, o la prueba pasa vacía. No se pudo verificar cómo `conftest` construye ese engine (¿`NullPool`?); el implementador debe confirmarlo.

## Observaciones menores

- **Worker con código vivo montado.** Desde W0-1 el worker de desarrollo monta `../api/src` en solo lectura y no tiene `--reload`. Durante B2..B8 se edita `api/src`. Un reinicio inesperado del contenedor (`restart: unless-stopped`, reinicio del host) importaría código a medio escribir. Anotar en RUNBOOK §7: parar el worker (`$DC stop worker`) cuando se edite `app/worker/` o `memberships/expirations.py`, y arrancarlo en el checkpoint.
- **`read_only: true` es viable.** El riesgo 9 es casi inexistente: la imagen ya trae `PYTHONDONTWRITEBYTECODE=1` (`api/Dockerfile:41`) y usuario 10001. No hace falta añadir la variable al servicio. Cambiar el riesgo 9 por "verificado". `tmpfs: /tmp` es 1777 por defecto y el latido es escribible.
- **B8 y `AUDITABLE_TABLES`.** Incluye `audit.verifications` y `auth.one_time_tokens`. `audit.verifications` no es `__audited__` (va en `EXCLUIDAS`, B3.4). La prueba nueva de B8.2 ("todo `__audited__` ⊆ `AUDITABLE_TABLES`") no choca, pero la inversa no debe exigir `__audited__` a las tablas de la lista. Redactarlo así.
- **Cobertura sin `omit`.** `cli.py` tiene 541 líneas hoy y B2/B3 le suman dos comandos más. B1.7 solo mide a modo de lectura. Medir también `cli.py` por separado en B1, para no enterarse en B2.8 de que falta más de un slice de pruebas. `pyproject.toml:88` es el `omit` a quitar.
- **`test_user_limits_catalog.py` y `staff-read`.** La lista de pendientes se llama `CLAVES_SIN_RUTA_TODAVIA` (línea 157-159), no "pendientes". Es una constante editable. Confirma el supuesto 12 del plan. En B3.4, `audit-verify` y `audit-verify-hour` sí tienen ruta (B3) y `staff-read` queda pendiente hasta B4.2, como dice el plan.
- **Equilibrio del lock `4_270_003`.** `test_sql_literals_constant.py` ya valida las otras dos claves de candado. B3.4 debe compararlas con las constantes reales, sin copiar valores.
- **P2-1 por API.** El `DELETE /plans/{id}` nace en B7. V12 lo usa después, así que el orden es correcto. El ritmo de 30 escrituras por minuto aplica a `POST .../cancel` y al `DELETE` por separado; calcular ~270 llamadas más las anulaciones.
- **Mensaje de error de `finish_run`.** `str.isidentifier()` acepta nombres de tipo, pero también rechaza `asyncio.exceptions.TimeoutError` si se pasa el nombre calificado. El plan usa `type(exc).__name__`; fijarlo en la prueba.

## Verificado sin hallazgo

- `slice-gate.sh` (`scripts/workflow/slice-gate.sh:96-111`) resuelve los módulos como el plan asume. `core/<x>` exige `core/<x>.py` o `core/<x>/`, `worker` exige `src/app/worker`, `cli` exige `cli.py`, `main` exige `main.py`. `<modulo>` exige `src/app/modules/<modulo>/`. Existen `audit`, `auth`, `members`, `memberships` y `plans`. `dashboard` no existe hoy: lo crea B8.1. Con lista exige `tests/` bajo `api/` y `[ -f ]`, lo que valida la regla del plan de hacer `ls` previo.
- Front: `web/<feature>` existe para `system`, `dashboard`, `members` y `plans` (`features/`). `web/shared`, `web/core` y `web/app` usan las rutas del script (151-152).
- `tests/migrations/test_0011_payments_immutability.py:112-117` afirma `get_heads() == [REVISION]`: es la prueba que B1.2 cambia a "cadena hasta head".
- `core/db.py:116 create_engine_from` y `server_settings_from` existen. `cli.py:291 cli_runtime` es la plantilla que `worker_runtime` repite, y no toca el keyring.
- `LIMPIEZA_DE_SESION` (`tests/conftest.py:274-289`), `LIMPIAR_PAYMENTS` y `LIMPIAR_MEMBERSHIPS` ya usan `ENABLE ALWAYS`. `test_triggers_siempre_activos.py` cubre memberships y payments; B3.4 y S4A-D70 lo extienden a `verifications`. `audit.audit_log` se limpia con `DISABLE`/`ENABLE TRIGGER USER` (líneas 281-283 y 683-687). Es previo a este sprint y no lo toca. `LIMPIAR_VERIFICATIONS` va antes de `audit_log` (plan:152). Además `triggered_by` puede apuntar a `auth.users`, y `LIMPIAR_AUTH` va después.
- `test_audit_module.py:44-55` fija `MODULES` de siete elementos: B8.2 lo cambia a ocho. `test_service_import_graph.py:231-298` y `LAZY_IMPORT_WHITELIST` coinciden con lo que B5.2 y B7.2 editan (`members` hoy `arriba == set()` y `plans` `== set()`).
- `test_error_codes_per_route.py:26-76` es igualdad exacta con `CON_LIMITE`. El plan la actualiza en el Rojo de cada slice con ruta nueva (B3, B4, B5, B7, B8).
- `test_user_limits_catalog.py:157-159` usa `CLAVES_SIN_RUTA_TODAVIA` y `test_las_rutas_con_enforce_user_limit_son_con_limite_menos_auth` compara con `CON_LIMITE`.
- `apscheduler>=3.10,<4` y `tzdata` ya están en `pyproject.toml:16,21` y el lock (3.11.3). No hay dependencias nuevas.
- `Settings` tiene `extra="forbid"` y `ENV` con default `production`; `.env.example:32` pone `ENV=dev`.
- `web`: `features.ts` ya lista `audit` en `FEATURES`; falta solo en `ENABLED_FEATURES` (`features.test.ts:11-12` espera 8). `routeTable.ts:146` tiene la ruta `/sistema/auditoria` y `nav.ts:83` el ítem. `childRoute`, `parent`, `routes.tsx:55-61` y `routes.reference.ts:35-38` ya soportan rutas hijas (E14 del Sprint 3 resuelta); `/socios/:id/historial` es una hija más. `permissions.ts:44` ya define `members.history.view`. `MemberDetailPage.tsx:57` tiene `disabledUntil: "v0.1 · Sprint 4A"`. Existen las 15 specs `stack` del Sprint 3 y `helpers/stack.ts` exporta `datosDeBase`, `exigirStackLocal`, `crearCoach`, `borrarUsuario` y `nombrePlanE2E`. Existen `tests/lint/boundaries.test.ts` y `sensitive-mutations.test.ts`.
- Archivos de gate del api comprobados: `test_env_example`, `test_config`, `test_ratelimit`, `test_migrations`, `test_health`, `test_startup_failure`, `test_validators`, `cli/test_seed_cli`, `cli/test_db_timeouts_cli`, `members/test_router_get`, `memberships/test_sell_service`, `memberships/test_rules`, `plans/test_service_list`, `plans/test_router_list`, `core/test_audit_chain`, `core/test_audit_log_db`, `core/test_audit_concurrency` y las pruebas de arquitectura citadas. Faltan solo los que el Rojo crea según el plan: `test_crypto_bus_importers`, `test_export_openapi_cli`, `test_init_keys_cli` y los de `tests/audit`, `tests/worker` y `tests/dashboard`.
- Tamaños: `members/service.py` 483, `memberships/queries.py` 579, `plans/service.py` 314, `auth/users.py` 615, `core/audit.py` 502, `cli.py` 541. Hay margen contra las 800 líneas de `test_file_and_function_size.py:15`.
- B8 puede obtener nombres de socio, plan y actor: `members.service.names_for`, `memberships.refs_for` (devuelve socio y plan, `queries.py:106-131`, re-exportada en `service.py:81`) y `auth.users.names_for`.
- `api/Dockerfile`: usuario 10001, `.venv` en el `PATH`, `COPY migrations`, `PYTHONDONTWRITEBYTECODE=1`. `compose.dev.yml` ya monta `../api/src` y `../api/migrations` en `api`. `main.py:6` confirma que el api migra en el lifespan, coherente con P-MIG paso 6.
- `compose-smoke.sh` y `ci.yml:241-252` coinciden con lo que W0-2 dice que edita.

## Qué le falta al plan para ser APROBADO

Incorporar las enmiendas E1, E3, E4, E5, E7 y E8 en su slice (son las que cambian pasos o evidencia). E2, E6, E9 y E10 se aplican como precisión de pasos ya existentes. Ninguna cambia el alcance ni el orden de slices.
