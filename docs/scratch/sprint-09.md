# Sprint 9 · cuaderno (backend y orquestador)

Rama `feat/sprint-09-perfil-atleta`, HEAD de partida `b8c9255` (sobre `cd0cc0b`, cierre de v0.5.0). Head de Alembic de partida: `0041_results_session_index`.

## Planificación

- Impacto: `docs/ddd/blueprints/sprint-09-impacto.md`
- Exploración: `docs/ddd/blueprints/sprint-09-exploracion.md`
- Blueprint: `docs/ddd/blueprints/sprint-09-blueprint.md`
- Diseño de seguridad: `docs/ddd/blueprints/sprint-09-seguridad-diseno.md`
- Plan (aprobado): `docs/ddd/blueprints/sprint-09-plan.md` (la sección 10 manda)
- Críticas del plan: `docs/ddd/blueprints/sprint-09-critica-1.md`, `sprint-09-critica-2.md`

## W0-1 · documentos y decisiones (2026-11-15)

- Decisiones S9-D1 a D42 en `docs/ddd/DECISIONES.md` (bloque «Sprint 9»), con la confirmación de S9-D41 (el usuario ordenó el 2026-11-15 el push del orquestador).
- Migraciones reales `0042_athletes_body_metrics` y `0043_athletes_personal_records` en `SPRINT-09.md`, `BREAKDOWN.md` (EP-24) y DECISIONES.
- T-DOC en US-178 a US-184; `02_domain_model.md` §2.9, tabla de eventos y de clases de dato; `03_context_map.md` (aristas de S9-D20 y puerto `RecordsProbe`); `05_service_design.md`; `BRECHAS.md` (fila de `benchmark_id` y §17 nueva); `ROUTES.md` (pestaña `/atleta` y rutas reales); `CLAUDE.md` (módulo `athletes` y privados, reglas 1 y 2 bis, bus 9, 28 cubetas y 27 variables, `derive-records`, `0042` y `0043`, frase del push de S9-D41).
- Los conteos de cubetas y variables de `CLAUDE.md` (28 y 27) los fija el código hasta W0-2.
- No hay Rojo ni Verde (documentos).

### Evidencia

- Gate `bash scripts/workflow/slice-gate.sh architecture` (con `TEST_DATABASE_URL` exportada; sin ella el gate da 90 errores de fixture, no de documentos): 885 passed en 246,9 s, exit 0.
- Desviaciones: ninguna prueba de documentos falló; la prueba de cubetas y variables sigue fijada por el código (26/27 hasta W0-2).

## W0-2 · cubeta `athletes-write`, variables y línea base (2026-11-15)

### Línea base (antes del Verde; con el Rojo del slice ya en el árbol)

- Suite completa del api, un solo `pytest -m "not perf"`: 10.999 pasan, 103 saltan, 47 deseleccionadas, **13 fallan** en 2.974,5 s. Las 13 son exactamente las del Rojo de este slice (conteos 28/27, `athletes-write`, `USER_ATHLETES_WRITE_LIMIT_PER_MIN`); ninguna otra.
- Saltos (103): 34 por `cmd.exe` sin entorno para el `age` falso (CI/Linux), 23 por OpenBao real (contenedor Linux y CI), 8 por enlaces simbólicos sin privilegios, 6 por modo POSIX en NTFS, 5 por `age` real y pty solo en Linux, resto del mismo tipo (Linux/CI).
- `mypy src`: Success, 0 errores en 279 archivos.
- Vitest (`--pool=forks --maxWorkers=2`): 261 archivos y 4.537 pruebas pasan, 0 fallan (355 s). `stack` y `preview` no se corren aquí (Playwright, P-E2E).

### Rojo

- Archivos: `tests/core/test_ratelimit.py`, `tests/core/test_env_example.py`, `tests/core/test_config.py`, `tests/architecture/test_user_limits_catalog.py` (`athletes-write` en `CLAVES_SIN_RUTA_TODAVIA`, 28 cubetas, 27 variables, `ci.yml` sube las 27).
- `grep "== 27|== 26|27 cubetas|26 variables"` en `api/tests`: migrados todos los de cubetas (los demás `== 26/25` son longitudes de listas ajenas).
- Medido: 4 archivos, **13 failed, 347 passed**; motivo: `KeyError 'athletes-write'`, `AttributeError USER_ATHLETES_WRITE_LIMIT_PER_MIN`, `27 == 28`, `.env.example` y `ci.yml` sin la variable.

### Verde

- `core/config.py` (`USER_ATHLETES_WRITE_LIMIT_PER_MIN`, 30, `gt=0`), `core/ratelimit.py` (cubeta y `user_limits_from`), `.env.example`, `infra/compose.yml` (api), `ci.yml` (`sed` y regex del conteo: 27).
- Mismos 4 archivos: 360 passed.

### Evidencia de W0-2 (checkpoint `8431263`)

- Gate no sellante `core/config tests/core/test_config.py`: 1.124 passed (176 s), exit 0.
- Gate sellante `core/ratelimit tests/core/test_ratelimit.py tests/core/test_env_example.py`: 987 passed (172 s), ruff y mypy del módulo en verde, exit 0 (el primer intento falló por E501 en un comentario de `ratelimit.py`; corregido, 2.º intento verde).
- `$DC restart api` hecho (P-REBUILD 1). Desviación menor: el `restart` no relee `infra/compose.yml`; el valor por defecto del código (30) es el que rige hasta el próximo `up`.
- Los archivos de W0-3 ya escritos se apartaron del árbol durante el gate y se restauraron después, para que el checkpoint de W0-2 no los arrastrara.

## W0-3 · claves de alerta, arranque de clases y aviso de volumen (2026-11-15)

- `$DC stop api worker` antes de tocar código (regla de W0-3). `grep -rn "warn_reveal_volume\|reveal_volume" api/src api/tests` antes: sin resultados (la función existente era `_avisar_volumen_de_reveal`, solo en `members/router.py`; su prueba, `tests/members/test_router_reveal.py`, solo mira el mensaje `reveal volume`). Usos actualizados: el router llama `warn_reveal_volume`; `REVEAL_HOUR_BUCKET`, `logger` e imports quedan solo en `core/ratelimit.py`.

### Rojo

- Archivos: `tests/core/test_alerts.py`, `tests/core/test_alerts_telegram.py` (enmienda 1 de la crítica 2), `tests/core/test_reveal_volume.py` (nuevo), `tests/crypto/test_boot_data_classes.py` (nuevo), `tests/architecture/test_no_cross_schema_sql.py` (`athletes` en `ESQUEMAS` y en `MODULOS_PENDIENTES` hasta A1).
- Stub: `warn_reveal_volume` con `NotImplementedError`.
- Medido: **22 failed, 95 passed** en los 5 archivos. Motivos: `ValueError` por claves `revelados` y `marcas` (11), mensajes de Telegram sin contexto (3), `NotImplementedError` (7), `test_las_claves_de_contexto_son_las_del_plan` (1).
- `test_boot_data_classes.py` pasa desde el primer momento (3 passed): `ensure_keys` ya crea la llave de toda clase que cifra; es una red de seguridad para `athlete.metric` (A1), no un Rojo. Se anota como desviación del «rojo medido»: no hay cambio de producción que lo pueda poner en rojo.

### Verde

- `core/alerts.py` (`revelados`, `marcas` en las dos listas), `core/alerts_telegram.py` (tres entradas en `_DINAMICOS`), `core/ratelimit.py` (`warn_reveal_volume`, `REVEAL_HOUR_BUCKET`, `_reveal_alertado` vaciado por `reset_store`; una alerta por usuario y hora; contexto exacto `{"revelados": N}`; la alerta en su propio `try`), `members/router.py` (lo usa).
- Los cinco archivos más `test_router_reveal.py` y `test_ratelimit.py`: 188 passed. `ruff check src tests` y `mypy src` (279 archivos) en verde.
- `security-reviewer` no se lanzó (sin agentes en esta corrida): autorrevisión: la alerta nunca lleva ids de personas (probado con `str(usuario) not in llamadas`), el registro de fallo solo guarda el tipo de la excepción.

### Evidencia de W0-3 (checkpoint `ba1b648`)

- Gates no sellantes: `core/alerts tests/core/test_alerts.py` 932 passed, exit 0; `crypto tests/crypto/test_boot_data_classes.py` 889 passed, exit 0; `members tests/members/test_router_reveal.py` 910 passed, exit 0.
- Gate sellante `core/ratelimit tests/core/test_reveal_volume.py tests/core/test_alerts.py tests/crypto/test_boot_data_classes.py`: 943 passed, ruff y mypy del módulo en verde, exit 0.
- P-REBUILD 2: `$DC start api` y `$DC start worker` tras el checkpoint (estaban parados desde el paso 0); ambos `healthy`.
- Cierre de Wave 0: `bash scripts/workflow/wave0-gate.sh W0-3` (scripts, compose config, imagen `apex-api:local`, sello `architecture`): 886 passed, exit 0. `run-gates.sh` no se corrió (lo corre el orquestador).
- Smoke `GET /api/v1/health`: `status ok`, `db ok`, `migrations ok`, `crypto ok`, `backup attention` (informativo, preexistente), `version cd0cc0b21b65` (la imagen del api no se reconstruyó: P-REBUILD 4 es del cierre de wave con GIT_SHA, a cargo del orquestador).
- `docker ps -a`: sin contenedores parados nuevos; los `Exited` de `apex` (`openbao`, `caddy`, de hace 44 h y 4 días) y los de `apex-ensayo` son anteriores y no se tocaron.

## W0-3b · correcciones de la revisión de seguridad de W0-3 (2026-11-16)

- Revisión de Fable sobre `d63daf9..ba1b648`: 0 CRITICAL, 0 HIGH, 1 MEDIUM, 4 LOW. Decisión S9-D43 en `DECISIONES.md` (cuatro corregidos, uno aceptado sin código). No hay migración: sin bandera. `run-gates.sh` del worktree `gates` terminó antes (2 fallas ajenas al slice: `test_health::test_base_caida_da_503_en_menos_de_3_segundos` y `test_sending::test_dos_pasadas_en_paralelo...`; las atiende el orquestador).

### Rojo

- Archivos: `tests/core/test_alerts_telegram.py` (dos usuarios en el mismo minuto envían dos mensajes; el resto de códigos sigue deduplicando; `error_type` no ASCII, de 41 y con dígito Unicode no pasa en las tres alertas; uno de 40 sí pasa) y `tests/core/test_reveal_volume.py` (tope de claves de las marcas, vencimiento sin acumular y `reset_store` sobre el almacén nuevo).
- Medido: **13 failed, 67 passed**. Motivos: 1 por la deduplicación de `reveal_volume`, 9 porque `isidentifier()` deja pasar `Erroré`, 41 letras y `Error١`, 3 por `AttributeError: _reveal_alertas_store` (la memoria era un `dict` sin cota).

### Verde

- `core/alerts_telegram.py`: `_SIN_DEDUP` (`reveal_volume`), `_tipo_error` con `_NOMBRE` en `_job_failed`, `_audit_sign_failed` y `_athletes_derive_skipped`. `core/ratelimit.py`: `_reveal_alertado` pasa a `SlidingWindowStore` (`REVEAL_ALERT_MAX_KEYS`, tope 1, ventana 3600 s), vaciado por `reset_store`. `docs/RUNBOOK.md` (logger `app.ratelimit` y alerta `reveal_volume`).
- 5 archivos del módulo (`test_alerts_telegram`, `test_reveal_volume`, `test_ratelimit`, `test_alerts`, `test_router_reveal`): 197 passed.
- Gate no sellante `core/alerts tests/core/test_alerts_telegram.py tests/core/test_alerts.py`: 1.002 passed (235 s), exit 0.

### Evidencia de W0-3b (checkpoint `37c5d3a`)

- Gate sellante `core/ratelimit tests/core/test_ratelimit.py tests/core/test_reveal_volume.py tests/core/test_alerts_telegram.py tests/members/test_router_reveal.py`: 1.037 passed (256 s), ruff y mypy del módulo en verde, exit 0.
- `$DC restart api worker` y `GET /api/v1/health` : status ok, db ok, migrations ok, crypto ok.
