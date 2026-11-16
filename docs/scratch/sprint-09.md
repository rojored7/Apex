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

## W0-4 · avisos sin envío doble entre pasadas paralelas y cronómetro de health (2026-11-16)

- Origen: corrida de cierre de la Wave 0 (`run-gates.sh`, worktree limpio, SHA `41162ce`), 2 fallas. No hay migración: sin bandera. Decisión S9-D44 en `DECISIONES.md` (corrige S5-D228).

### Rojo

- Prueba nueva `tests/notifications/test_sending.py::test_una_pasada_no_reenvia_un_aviso_que_otra_tiene_en_vuelo` (A detenida en el canal con `asyncio.Event`, B completa, sin sleeps). Medido sin cambios en `src`: **1 failed, 1 passed** (con la vieja); motivo: 5 correos en vez de 4, `p0@example.com` repetido.
- Hallazgo durante el verde: el arreglo propuesto (solo control optimista por `attempts`) NO bastaba: con el arreglo a medias el rojo siguió en 5 correos, porque B lista después de que A ya sumó el intento y `attempts` coincide. Se añadió el candado de aviso en vuelo (`pg_try_advisory_xact_lock`, sin migración). Ambas defensas quedan (ver S9-D44).
- `test_health::test_base_caida_da_503_en_menos_de_3_segundos`: no tiene rojo (corrección del cronómetro de la prueba: `create_app` queda fuera de la medición, solo se mide el `get`; umbral de 3 s intacto, S4B-D115).

### Verde

- `notifications/sending.py`: `_eligible_ids` devuelve `(id, attempts)`; `_lock_eligible` exige `attempts` igual; `_in_flight` (candado advisory xact, `NOTIFY_LOCK_NS = 4_270_010`) rodea `_prepare` + envío + cierre; `pendientes` cuenta el aviso en vuelo (probado: `b.pendientes == 1`). Docstring del módulo actualizado. La prueba vieja exige además destinatarios únicos.
- `tests/notifications/test_sending.py` completo: 44 passed.

### Evidencia de W0-4 (checkpoint `689f52a`)

- Gate no sellante `core/health tests/core/test_health.py`: 916 passed (228 s), exit 0.
- Gate sellante `notifications tests/notifications/test_sending.py`: 930 passed (227 s), ruff y mypy del módulo en verde, exit 0.
- `tests/notifications/test_sending.py` completo 3 veces seguidas: 44 passed las tres (20 s cada una). `tests/notifications` + `tests/worker` una vez: 840 passed, 4 skipped (mkfifo y enlaces simbólicos en Windows, preexistentes), 2 deselected (perf).
- `$DC restart worker api` y `GET /api/v1/health`: status ok, db ok, migrations ok, crypto ok; api y worker `healthy`.
- No quedó probada la defensa (2) (control optimista de `attempts`) con una prueba propia: la prueba nueva solo la ejerce de forma indirecta; el rojo y el verde cubren la defensa (1). Queda anotado por si el orquestador quiere una prueba de lista vieja.

## W0-4b · candado de aviso a prueba de inactividad y cancelación, skip 409 en vuelo y opt-in al enviar (2026-11-16)

- Origen: revisiones Fable (database-reviewer y security-reviewer) de W0-4. Decisión S9-D45 en `DECISIONES.md` (S9-D44 actualizado). Sin migración: sin bandera. Los 8 hallazgos se verificaron leyendo el código; ninguno resultó falso. El 9 (entrega «al menos una vez») queda aceptado.

### Rojo

- Archivo nuevo `tests/notifications/test_sending_candado.py` (21 pruebas). Antes de escribirlas se dejaron dos costuras sin comportamiento: `try_in_flight_lock` (refactor puro de `_in_flight`) y la constante `NOTIFY_SEND_TIMEOUT_S` sin usar.
- Medido: **8 failed, 13 passed**. Motivos: idle timeout (el candado se soltó a mitad del envío), tope total (el canal colgado no se corta), fallo al tomar el candado (gasta intento y queda `failed`), cancelación (otra pasada envía con la unidad aún enviando), `_finish` pisa `sent` y `skipped` (2), `NotificationInFlight` no existe, opt-in (el correo se envía). Las otras 13 son las de `_lock_key` (8), `_lock_eligible`, la defensa 2 y los casos del `skip` que ya se cubrían por el candado de fila.
- Defensa 2 (`attempts == expected_attempts`): la prueba pasa con el código actual; el rojo se midió quitando temporalmente esa línea de `_lock_eligible` (`sed '/Notification.attempts == expected_attempts,/d'`): **2 failed, 63 passed** (`test_una_lista_vieja_...` y `test_lock_eligible_exige_...`). Restaurada.

### Verde

- `notifications/sending.py`: `_in_flight` con `set_config(idle_in_transaction_session_timeout, 0, true)` y fallo al tomar el candado = intacto; `_deliver` con `asyncio.wait_for(NOTIFY_SEND_TIMEOUT_S = 90)` (vence como `timeout`); `_locked_unit` (candado + preparación + envío + cierre bajo un solo `shield`, `_UNITS` guarda las tareas); `_finish` no pisa `sent` ni `skipped`; `_deliverable_contact` (consentimiento, correo y opt-in vía `members.service.channels_for`, `canal_desactivado_socio`; separado de `_prepare` por el tope de 50 líneas de `test_file_and_function_size`).
- `service.skip` prueba el candado antes de la fila: 409 `notification_in_flight` (`exceptions.NotificationInFlight`). Front: `noticeErrors.ts` y su prueba en `SkipModal.test.tsx` (170 passed en `features/notifications`; `tsc` y `eslint` limpios). `docs/openapi.json`: dos exportaciones idénticas, sin cambio (el 409 ya estaba declarado).
- `core/locks.py` (docstring de orden) y `tests/architecture/test_sql_literals_constant.py` (valor y forma de dos claves de `NOTIFY_LOCK_NS`); `infra/db/roles.sql` (comentario de 2 conexiones por aviso); `docs/operacion/avisos.md`.
- `test_sending_candado.py` + `test_sending.py` + `test_today_and_skip.py`: 80 passed antes del último refactor.

### Evidencia de W0-4b

- Primer intento del gate no sellante `core/locks tests/core/test_locks.py`: 1 failed (`test_ninguna_funcion_supera_50_lineas`: `_prepare` de 55 líneas), 892 passed. Corregido extrayendo `_deliverable_contact`. Segundo intento: 893 passed (226 s), exit 0.
- Gate sellante `notifications` (`test_sending_candado.py`, `test_sending.py`, `test_today_and_skip.py` + `tests/architecture`): 967 passed (278 s), ruff y mypy del módulo en verde, exit 0. Checkpoint `a08ee44`.
- `tests/notifications` + `tests/worker` completos: 861 passed, 4 skipped (enlaces simbólicos de Windows), 2 deselected (`perf`).
- `test_sending.py` + `test_sending_candado.py` tres veces seguidas: 65 passed las tres.
- `$DC restart api worker` y `GET /api/v1/health`: status ok, db ok, migrations ok, crypto ok; api y worker `healthy`.

## W0-4c · errores de conexión sin gastar intento, unidades drenadas y pruebas del candado (2026-11-16)

- Origen: revisión de verificación Fable (security-reviewer) de W0-4b: 0 CRITICAL/HIGH, 2 MEDIUM, 6 LOW. Decisión S9-D46 en `DECISIONES.md` (S9-D45 con su alcance real). Sin migración, sin bandera. Los 8 hallazgos se verificaron; ninguno falso. Medido: puerto cerrado = `ConnectionRefusedError` pelado (no `SQLAlchemyError`); rol sin cupo = `DBAPIError` 53300.

### Rojo

- Costuras sin comportamiento: `core.db.is_connection_error` y `sending.drain_units` con `NotImplementedError`, `NOTIFY_CLOSE_MARGIN_S = 0`.
- `tests/core/test_db_connection_error.py` (7): **7 failed** (`NotImplementedError`).
- Notifications (`test_sending_conexion.py` nuevo, 9; `test_sending_candado.py` reescrito; `test_sending.py`; `test_router_notifications.py`): **12 failed, 120 passed**. Motivos: puerto cerrado al tomar el candado y al abrir la preparación y `TooManyConnections` real en la segunda conexión (3: gastan intento, `(0,1,0) != (0,0,0)`); skip por canal apagado de una unidad aún enviando (B la omite); `_mark_failed` fuera del candado (`[True] != [False]`); `_finish` sin `warning` (0 != 1); drenado (2: `_UNITS` no vacío); `drain_units` con tope (`NotImplementedError`); margen del plazo (0 < 50); cancelación (la pasada no espera a su unidad); descifrado de un correo apagado (`1 != 0`).
- Ya verdes antes del arreglo (cobertura, LOW 7 y consentimiento): tope de 90 s con hilo, 409 HTTP `notification_in_flight`, sin consentimiento sin descifrar. `test_skip_conserva_el_candado...`: rojo medido anulando el try-lock de `service.skip` (`if False and ...`): 1 failed; restaurado.

### Verde

- `core/db.py`: `is_connection_error` y `CONNECTION_SQLSTATES`.
- `notifications/sending.py`: `_in_flight` atrapa conexión; `_prepare_or_skip`, `_guarded_prepare` (conexión = intacto; otro fallo = `_mark_failed` bajo candado), `_handle` delgado, `drain_units` + `_PASS_UNITS` + `finally` en `send_pending`, `_deliverable_contact` con `channels_for` primero, `warning` en `_finish`, `NOTIFY_SOFT_DEADLINE_S` 480 -> 420, `NOTIFY_CLOSE_MARGIN_S = 50`, `NOTIFY_DRAIN_TIMEOUT_S = 30`.
- Pruebas: `tests/core/_apoyo_conexion.py` (errores reales; rol temporal `CONNECTION LIMIT 1`), `habilitar_correo(version=)`; `test_sending.py` (420 y `sin_correo` con la preferencia activa). Docs: `avisos.md` (peor caso de 3 correos, conexión, cierre), RUNBOOK (420 s).

### Evidencia de W0-4c

- Lint de todo `api/`: `ruff check .` y `ruff format --check .` limpios, `mypy src` sin errores (279 archivos).
- Gate no sellante `core/db` (`test_db.py`, `test_db_timeouts.py`, `test_db_connection_error.py` + `tests/architecture`): 929 passed (177 s), exit 0. Worker y CLI no se tocaron: sin gate propio.
- Gate sellante `notifications` (`test_sending_candado.py`, `test_sending_conexion.py`, `test_sending.py`, `test_router_notifications.py` + `tests/architecture`): 1019 passed (240 s), exit 0. Checkpoint `266af7f`.
- `tests/notifications` + `tests/worker` + `tests/cli` completos: 840 passed, 4 skipped (enlaces simbólicos y `mkfifo` de Windows), 2 deselected (`perf`).
- `test_sending.py` + `test_sending_candado.py` + `test_sending_conexion.py` tres veces seguidas: 44 passed las tres.
- `$DC restart api worker`: `GET /api/v1/health` status ok, db ok, migrations ok, crypto ok; api y worker `healthy`. `run --rm worker ... --run-once notify`: job `ok` (0 avisos, resumen de solo conteos).
- Desviación: la prueba de `sin_correo` de `test_sending.py` ahora activa la preferencia de correo (con el opt-in primero, un socio sin preferencia sale `canal_desactivado_socio`).

## W0-4d · sin gastar intento solo al abrir la conexión, job no-ok por saturación y rol temporal aleatorio (2026-11-16)

- Origen: revisión de verificación Fable de W0-4c (`009a8aa..266af7f`): 0 CRITICAL/HIGH, 2 MEDIUM, 4 LOW (ocho puntos). Decisión **S9-D47** en `DECISIONES.md`. Sin migración, sin bandera. Los 8 se verificaron; ninguno falso. LOW 3 (COMMIT ambiguo) se resuelve solo: solo la apertura queda sin gastar.

### Rojo

- Pruebas escritas antes del código (`test_db_connection_error.py` +8, `test_sending_apertura.py` nuevo, 10, `test_sending_conexion.py`, `test_sending_candado.py`, `test_notify_job.py`, `test_worker_notify_env.py`, `test_notifications_details_clean.py`): **19 failed** (de 87 en los 7 archivos), más 1 error de mi propio ayudante (`'5 minutes'` como parámetro de intervalo; corregido con literal).
- Motivos: `is_connection_error` aceptaba `FileNotFoundError`/`TimeoutError`/`OSError` (5); `FileNotFoundError`/`TimeoutError` en `load_contact` no gastaban intento (2); `_open_connection` y `SendResult.sin_conexion` inexistentes (apertura, pool, corte a 3, reinicio de cuenta); `_handle` sin `except` (1); `NOTIFY_PRE_MARGIN_S` inexistente; job sin `sin_conexion`; compose sin `stop_grace_period`; clave fuera de `DETAIL_KEYS`.

### Verde

- `core/db.py`: `_is_socket_failure` (`ConnectionError`, `socket.gaierror`); `is_connection_error` ya no acepta `OSError` genérico.
- `sending.py`: `is_open_failure`, `_ConnectionNotOpened`, `_open_connection` (costura), `_tx` abre la conexión al entrar, `_in_flight` cede `None`/`UNTOUCHED`/`NO_CONNECTION`, `_guarded_prepare` solo trata la apertura, `_handle` con `except Exception` (custodio y cancelación suben), `_run_pass` (extraído por el tope de 50 líneas) con corte a `NOTIFY_MAX_CONNECTION_ERRORS = 3`, `NOTIFY_SOFT_DEADLINE_S` 420 -> 330, `NOTIFY_PRE_MARGIN_S` 60, `NOTIFY_PREPARE_MARGIN_S` 40 (60 + 330 + 40 + 90 + 50 = 570 < 600); docstring recortado para quedar en 800 líneas.
- `SendResult.sin_conexion`; job `notify`: `ok = fallidos == 0 and sin_conexion == 0`, `details["sin_conexion"]` solo si > 0; `DETAIL_KEYS` suma `sin_conexion`. `infra/compose.yml`: worker `stop_grace_period: 45s`.
- Pruebas: rol temporal aleatorio con clave aleatoria y `VALID UNTIL` (5 min) y `barrer_roles_huerfanos` al arrancar la sesión (`tests/conftest.py`); `asyncio.Event` en lugar de `sleep(0.5)`.
- Docs: DECISIONES S9-D47 (y nota en S9-D46), RUNBOOK (plazo 330 s, `sin_conexion`, parada), `avisos.md`.

### Evidencia de W0-4d

- Lint de todo `api/`: `ruff check .` y `ruff format --check .` limpios, `mypy src` sin errores (279 archivos).
- Gates no sellantes: `core/db` (`test_db_connection_error.py` + `tests/architecture`) 904 passed, exit 0; `worker` (`test_jobs_core.py`, `test_notify_job.py` + arquitectura) 910 passed, exit 0 (la primera pasada del full dio 1 failed: `test_detail_keys_es_el_conjunto_cerrado_del_plan` no conocía `sin_conexion`; corregido).
- Gate sellante `notifications` (`test_sending*.py` x4 + `test_router_notifications.py` + arquitectura): 1030 passed (242 s), exit 0. Antes falló 1: `test_los_topes_por_corrida...` pedía 420. Checkpoint `5cabb36`.
- `tests/notifications tests/worker tests/cli tests/core` completos tras el sello: 2963 passed, 39 skipped (enlaces simbólicos y `mkfifo` de Windows), 7 deselected (`perf`), exit 0 (491 s).
- Repetición (orquestador, tras el sello): `test_sending.py`, `test_sending_candado.py`, `test_sending_conexion.py` y `test_sending_apertura.py` tres veces seguidas: 87 passed, 87 passed, 87 passed (exit 0).
- Worker recreado con `$DC up -d --no-build worker`: `StopTimeout` = 45. `/health`: `status ok`, `db ok`, `migrations ok`, `crypto ok` (`backup attention`, informativo en desarrollo). La pasada real de `notify` va tras la P-REBUILD del cierre de la Wave 0 (la imagen del worker aún no lleva el código nuevo).
