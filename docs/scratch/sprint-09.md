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

## S9-W0-4e · Código `notification_in_flight` en el catálogo del front

- Origen: P-GATES de cierre de la Wave 0 sobre `5cabb36` (worktree limpio, `gates-w0c.log`): api completo en verde (ruff, formato, mypy; pytest 11126 passed, 103 skipped, 47 deselected, cobertura 96 %; scripts, caddy, lint y `tsc` del web en verde). Falló 1 prueba del web: `errorCodes.test.ts` «fuera de core/api nadie compara un code con un literal»: `features/notifications/noticeErrors.ts` (W0-4b) comparaba `e.code === "notification_in_flight"`.
- Rojo: esa misma prueba del gate (1 failed de 4540), medida antes del cambio.
- Verde: `web/src/core/api/errorCodes.ts` suma `notificationInFlight: "notification_in_flight"` (S9-D45; la prueba de contexto lo encuentra en `notifications/exceptions.py:98`, `code = "notification_in_flight"`); `noticeErrors.ts` usa `API_ERROR_CODES.notificationInFlight`.
- Gates: `web/core` (`errorCodes.test.ts`) 104 passed, verde (no sellante).
- Sello `web/notifications` (`SkipModal.test.tsx`, `api.test.ts`, `errorCodes.test.ts`): verde. Checkpoint `04791bc`.

## Cierre de la Wave 0

- P-GATES sobre `5cabb36`: api completo en verde (ruff, formato, mypy; 11126 passed, 103 skipped, 47 deselected, cobertura 96 %), scripts y caddy en verde; web: 1 failed (corregido en W0-4e).
- **Desviación anotada:** tras `04791bc` no se repitió la mitad del api. `git diff --quiet 5cabb36 04791bc -- api infra scripts` confirma que api, infra y scripts son idénticos (solo cambiaron dos archivos de `web/` y este cuaderno). Mitad web sobre `04791bc` (alias 14): lint, `tsc`, vitest con 2 hilos 4541 passed (261 archivos, cobertura 95,86 %), build, exit 0.
- P-REBUILD: `apex-api:local` con `GIT_SHA=04791bc`, `up -d --no-build --force-recreate api worker`. `/health`: `status ok`, `db ok`, `migrations ok`, `crypto ok`, `version 04791bc` (`backup attention`, informativo en desarrollo).
- `notify` real dos veces (`--run-once notify`): `result ok` las dos (0 generados, 0 pendientes, 0 enviados, 0 fallidos).
- Worktree `gates` revisado antes de borrarlo: HEAD `04791bc` contenido en la rama, sin cambios ni stash; ignorados solo cachés, `.venv`, `node_modules`, `coverage`, `dist` y un `.env` idéntico a `.env.example` (lo copia `scripts/ci/compose-smoke.sh`). Borrado con `git worktree remove --force`. `drop_caches` hecho.


## S9-A1 · Tabla, clase y alta de medidas (2026-11-16)

### Rojo

Paso 0: sin `apex-e2e.flag`; `apex-migracion.flag` creada; `api` y `worker` parados (`$DC stop api worker`, siguen parados);
volcado `docs/scratch/sprint-09-antes-0042.dump` (3,4 MB, ignorado por git: `*.dump`).

**Stubs** (todos importan; fallan con `NotImplementedError` o con aserción):
- `api/src/app/modules/athletes/{__init__,exceptions,events,rules,models,schemas,metrics,service,router}.py`. `rules`, `metrics`, `router` y
  `members.service.consent_missing_for` lanzan `NotImplementedError`. `models.py` usa columnas `Text` (NO `Encrypted`) y la clase
  `athlete.metric` NO está en `core/crypto/registry.py` (registrarla sin la tabla rompe `discovery.encrypted_columns` en toda la suite):
  el Verde cambia ambas cosas en el mismo checkpoint. `schemas.py` sin límites (los rangos son del Verde).
- `api/migrations/versions/0042_athletes_body_metrics.py`: stub VACÍO (`upgrade` y `downgrade` con `pass`); cabeza de Alembic = 0042.
- `main.MODULES` suma `athletes` tras `tv`. `core/db.APP_SCHEMAS`, `migrations/env.py`, `infra/db/grants.sql`, `audit/queries.py`,
  `audit/diff.py` y `registry.py` NO se tocan (son del Verde; sus pruebas están en rojo).
- `tests/factories/athletes.py` (`make_metric`, stub con el contrato en el docstring) y entrada `athletes.body_metrics` en `FACTORIES`.

**Pruebas nuevas** (valores derivados a mano; `notes` = `n` + 4 dígitos de bytes UTF-8 + texto + espacios hasta que el claro COMPLETO mida
múltiplo de 128 bytes: interpretación del plan, el Verde debe confirmarla):
- `tests/athletes/test_metric_rules_pure.py` (reglas puras), `test_metrics_service.py` (service + puerta), `test_factory_metrics.py`,
  `test_router_metrics.py` (rutas 1 y 2), `test_metric_rotation.py` (rotación con commit real), `_apoyo.py`.
- `tests/migrations/test_0042_athletes_body_metrics.py` (una prueba por regla de S9-D31, CHECK, índice, `tgenabled = 'A'`, downgrade).
- `tests/members/test_consent_missing_for.py`.
- Ampliadas: `tests/migrations/test_db_grants.py` (31 tablas, esquema `athletes`, INSERT por columna sin `voided_*`, sin DELETE/TRUNCATE),
  `test_api_role_paths.py` (alta, anulación, rotación como `apex_api`), `test_worker_role_paths.py`, `test_triggers_siempre_activos.py`
  (`LIMPIAR_ATHLETES`), `test_0014_audit_log_triggers_always.py` (excluye `athletes.body_metrics`), `tests/crypto/test_boot_data_classes.py`
  (clase real), `test_registry.py`, `test_discovery.py`, conteos de llaves +1 en `test_inventory.py`, `test_kek_backup.py`,
  `test_router_cbom.py`, `test_router_keys.py`, `tests/architecture/test_cbom_no_key_material.py` (P-CAT 6), `tests/core/test_db.py`
  (`APP_SCHEMAS` con `athletes`), `tests/audit/{test_filters,test_history_fields,test_recent}.py`.
- Arquitectura y catálogos (P-CAT 1 a 6): `test_user_limits_catalog.py` (`CLAVES_SIN_RUTA_TODAVIA` vacío), `test_error_codes_per_route.py`
  (`CON_LIMITE` con las dos rutas), `test_audit_module.py`, `test_audited_tables.py`, `test_service_import_graph.py` (aristas a `members` y
  `auth`), `_imports.py` (`PRIVATE_HELPERS["athletes"]`), `test_reveal_single_door.py` (tercera puerta y control), `test_crypto_bus_importers.py`,
  `test_no_plaintext_at_rest.py`, `test_list_rows_without_sensitive_fields.py`, `test_list_routes_use_page_params.py` (la lista de medidas no
  acepta `q`: exclusión anotada), `test_no_sensitive_in_logs.py`, `test_no_physical_delete.py`, `test_no_trigger_tampering.py`,
  `test_no_cross_schema_sql.py`. `tests/conftest.py`: `LIMPIAR_ATHLETES` (antes de las llaves y de los resultados, en las dos limpiezas) y
  `tests/factories/triggers.py` (`BODY_METRICS_TRIGGERS`). P-CAT 4: el grep de `LIMPIAR_MEMBERS|DELETE FROM members|TRUNCATE` en
  `tests/*/conftest.py` no devuelve ningún conftest propio.
- No cambió ninguna prueba que fijara `0041` como cabeza (P-MIG 8: todas usan «está en la cadena de head»).

**Rojo medido** (`LC_ALL=C.UTF-8`, `TEST_DATABASE_URL` a `db_test`, un solo pytest a la vez):
- `tests/athletes`: 165 failed / 3 passed (los 3 son estructurales: fábrica registrada, 4 campos, rutas publicadas). Motivos: `NotImplementedError`
  en `decode_metric` 46, `encode_metric` 35, `add_metric` 30, `validate_metric` 20, `POST /athletes/{id}/metrics` 16 (+1 `MissingGreenlet` de
  arrastre), `make_metric` 12, `list_metrics` 1; y 4 `UndefinedTable athletes.body_metrics` (pruebas que cuentan filas).
- `tests/migrations/test_0042_athletes_body_metrics.py`: 90 failed / 1 passed (la cadena). Motivo: migración vacía, no existe el esquema ni la tabla.
- `test_db_grants.py` + `test_api_role_paths.py` + `test_worker_role_paths.py`: 25 failed / 311 passed. Motivo: esquema/tabla ausentes y `grants.sql`
  sin `athletes` (incluidas 5 pruebas generales que recorren `ESQUEMAS`).
- `test_triggers_siempre_activos.py`: 3 failed (trigger por tabla `athletes.body_metrics` inexistente). `test_0014`: verde.
- `tests/crypto` (boot, registry, discovery, inventory, kek_backup, router_cbom, router_keys): 16 failed / 102 passed. Motivo: `athlete.metric` no
  está en el registro (aserciones de clase y conteos +1).
- `tests/members/test_consent_missing_for.py`: 8 failed / 0 passed (`NotImplementedError`). `tests/core/test_db.py`: 1 failed (`APP_SCHEMAS`).
- `tests/audit` (filters, history_fields, recent): 4 failed (tabla y campos ocultos sin registrar).
- `tests/architecture`: 12 failed / 886 passed (898); las 12 son las de A1 (auditoría, CBOM, importadores del bus, no-plaintext,
  puerta de `reveal`, aristas, catálogo de cubetas, log sin valores).
- `tests/core/test_migrations.py` + `tests/migrations` completo: 118 failed / 1192 passed; los 118 son de `athletes` (90 de `test_0042`, 25 de
  grants/roles, 3 de triggers; ninguna ajena).
- `ruff check`, `ruff format --check` y `mypy src` (288 archivos) limpios sobre todo el árbol.

**Estado al cerrar el Rojo:** `apex-migracion.flag` puesta; `api` y `worker` parados; `apex-db-1` (desarrollo) sigue en `0041` (el stub de `0042` se
aplicó solo a `apex_test` y se bajó de nuevo a `0041` al final para que el DDL real del Verde se ejecute); `alembic heads` = una cabeza
(`0042_athletes_body_metrics`). Sin commit ni checkpoint.

**Notas para el Verde:** (1) el relleno de `notes` cuenta el claro completo (cabecera de 5 bytes incluida); (2) `MetricDecodeError` vive en
`rules.py`, `ConsentRequired`/`MetricVoided`/`MetricValidationError` en `exceptions.py`; (3) `_decrypt_metric_field` lanza `ValueError` ante un
campo o `purpose` inválido y `MetricVoided` ante una anulada; (4) `add_metric(session, member_id, data, *, by)` y
`list_metrics(session, member_id, page, *, include_voided=False)`; (5) tras registrar la clase y volver `Encrypted` el modelo hay que dar de alta
`ALLOWED_EDGES`, `APP_SCHEMAS`, `env.py`, `grants.sql` (tres listas + USAGE para api y backup), `audit/queries.py`, `audit/diff.py`
(`HIDDEN_HISTORY_FIELDS` con los cuatro campos) y `PUT`/ruta con `enforce_user_limit("athletes-write")` en el `POST`; (6) la fábrica y los
`apex_roles` de las pruebas de rotación necesitan que `rotate-key athlete.metric` descubra las columnas por el registro.

### Verde

Implementación de A1 hasta dejar el Rojo en verde sin relajar pruebas. Api y worker siguen parados; `apex-migracion.flag` puesta; `apex-db-1` sigue en `0041`.

**Código nuevo o modificado**
- Migración `api/migrations/versions/0042_athletes_body_metrics.py`: esquema, tabla de S9-D3, CHECK `at_least_one_measure` y `voided_pair`, índice `ix_body_metrics_member_date`, tres funciones (`guard_body_metrics_insert`, `guard_body_metrics_update`, `forbid_mutation`; `SECURITY INVOKER`, `search_path = pg_catalog`) y cuatro triggers `ENABLE ALWAYS`; `downgrade` simétrico. No hay trigger de auditoría por tabla: la auditoría es el hook del ORM (`__audited__`), como `results.wod_results`.
- `modules/athletes/{rules,models,schemas,metrics,service,router}.py`; `core/crypto/registry.py` (clase `athlete.metric`, 4 columnas); `core/db.APP_SCHEMAS`; `migrations/env.py`; `members/service.py::consent_missing_for` (una consulta, sin descifrar); `audit/queries.py` (`AUDITABLE_TABLES` y excluida de recientes con motivo); `audit/diff.py` (`HIDDEN_HISTORY_FIELDS` + los cuatro nombres); `infra/db/grants.sql` (tres listas, USAGE api+backup, REVOKE con `athletes`, INSERT por columna sin `voided_*`, UPDATE por columna, nadie DELETE); `web/src/core/api/errorCodes.ts` (`consentRequired`); `tests/factories/athletes.py` (`make_metric`); `docs/openapi.json` y `web/src/core/api/types.ts` (P-API; export idéntico en dos corridas).

**Resolución de las interpretaciones del Rojo**
- (a) Relleno de `notes`: se confirma. S9-D36 L-1 dice «n + 4 dígitos con los bytes UTF-8 del texto + texto + espacios hasta un múltiplo de 128 bytes» y habla del claro completo: la cabecera de 5 bytes cuenta. `decode_metric` además exige el relleno MÍNIMO (largo exacto = siguiente múltiplo) y solo espacios.
- (b) «Mismo largo» solo en `weight_g`, `height_cm`, `body_fat_pct`: se confirma con S9-D31 («en las tres columnas de ancho fijo `length(NEW) = length(OLD)`»); `notes` es de largo variable.

**Decisiones de diseño y desvíos (con la regla que los respalda)**
1. Guardas sin funciones auxiliares: `grants.sql` hace `REVOKE ALL ON ALL FUNCTIONS ... FROM PUBLIC` y `test_grants_sql_es_sql_puro` prohíbe `GRANT ... ALL ... TO apex_*`; un `GRANT EXECUTE` por función además ensucia la prueba de las tres listas. Las comprobaciones (regex de forma completa y estado de la llave en `crypto.crypto_keys`) van dentro de cada guarda con `CASE WHEN b ~ regex THEN (...)` para que un texto sin forma salga como guarda `P0001` y no como `22P02`. Todo NULL se trata como falso con `coalesce` (un `IF NOT NULL` no dispara).
2. `MetricIn` es de tipos estrictos sin rangos; los rangos y la fecha los valida `rules.validate_metric` (una sola fuente; la prueba del service construye `MetricIn` con 19.999 g y espera `MetricValidationError`, no un error de Pydantic). Los rangos quedan en el `description` del OpenAPI.
3. `BodyMetric.voided_at/voided_by` con `server_default=FetchedValue()` (patrón de `payments.payments`): el ORM omite esas columnas del INSERT y `apex_api` no necesita INSERT sobre ellas.
4. `core/errors._handler_dominio` pone `Cache-Control: no-store` en TODO error de dominio (la prueba de rutas exige `no-store` también en 404 y 409; el 404 de `members` sale por el mismo handler). Decisión de diseño: un error de ruta con rol nunca se guarda.
5. Pruebas del Rojo corregidas por contradecir una decisión o por error de la prueba (ninguna relajada): `test_0042` (reanular con el mismo `now()` en la misma transacción es un no-op; ahora cambia instante y usuario, S9-D31 «terminal»); `test_metric_rotation` (`reencrypt_batch` cuenta blobs: 2 filas x 4 columnas = 8, no 2); `test_metrics_service` (la puerta necesita `actor_scope` para las filas `decrypt` al confirmar); `test_router_metrics` y `test_no_sensitive_in_logs` (leer `miembro.id` tras un 403/404/422 que revierte la sesión compartida da `MissingGreenlet`: la ruta se calcula una vez); `test_db_grants` (la sentencia de `GRANT USAGE` con `athletes` es la del api y backup, no la primera, que incluye al worker: ahora se comprueba que ninguna que nombre `apex_worker` lleve `athletes`); `test_api_role_paths` (rotación: usuario real autor del job y limpieza de jobs y llaves); `test_db_apply` y `test_0014` (esquema y prefijo `athletes.` en la lista de posteriores); `test_inventory` (+1 llave: 12), `test_registry` (`DE_MEDIDAS` en las clases que cifran) y `test_history_fields` (el caso genérico usaba `notes`, ahora oculto: usa `cancel_reason`).
6. `_decrypt_metric_field` (tercera puerta) ya existe y pasa sus pruebas. **Pendiente de A2:** la ruta de `reveal` debe llamar a las tres cubetas `members-reveal`, `-hour` y `-day` y a `warn_reveal_volume`; el 500 `internal_error` sin texto ante `MetricDecodeError`; el reintento de `voided_at` dentro de la transacción del `reveal`; L-8 (blobs de `athletes.body_metrics` como «cifrado» en `GET /audit/{id}`).
7. Etiquetas del front para la auditoría («frases»): `diff.py` no tiene frases por tabla (solo campos ocultos); la etiqueta de `athletes.body_metrics` va en F1 (`grep -rn "wods.wods" web/src`).

**Conteos reales (un pytest a la vez, `-m "not perf"`, exit 0)**
- `tests/athletes` + `tests/members/test_consent_missing_for.py`: verde (athletes 165 de reglas, service, fábrica, router y rotación; consent 8).
- `tests/migrations/test_0042_athletes_body_metrics.py`: 91 passed.
- `tests/core/test_migrations.py` + `tests/migrations`: 1310 passed.
- `tests/crypto` + `tests/audit` + `tests/core/test_db.py`: 1312 passed, 63 skipped (tras corregir 5 conteos antiguos; los 5 ya en verde).
- `tests/members`: 870 passed.
- `tests/architecture`: 898 passed.
- `ruff check .` y `ruff format --check .` (todo `api/`, 1101 archivos) limpios; `mypy src` (288 archivos) limpio. Web: `tsc --noEmit`, `npm run lint`, vitest de `types.contract.test.ts` y `errorCodes.test.ts` (111 passed).
- P-MIG 1 a 4: `alembic heads` una sola cabeza (`0042_athletes_body_metrics`); el ciclo `downgrade`/`upgrade` pasa en `test_0042` y en `tests/core/test_migrations.py`.

**Para los revisores:** `database-reviewer`: el `pg_restore` completo de `restore.sh` carga los datos antes de los triggers (S9-D31); el costo de `FOR SHARE`-less lookup a `crypto.crypto_keys` en cada INSERT; la regex de forma. `security-reviewer`: la puerta, el 409 antes de cifrar y `no-store` en errores.

### Revisiones

`security-reviewer` (0 CRITICAL/HIGH/MEDIUM, 5 LOW) y `database-reviewer` (0 CRITICAL/HIGH, 1 MEDIUM, 5 LOW). Los once se verificaron leyendo el código: ninguno falso. Decisión **S9-D48** en `docs/ddd/DECISIONES.md`. Rojo medido antes del arreglo: 12 failed (4 de la regex, 2 de la carrera de `retire-key`, 1 candado del socio, 1 `isinstance` de la puerta, 1 `no-store` del 422, 3 de ocultos por tabla; las de retirada L-1 y el `FOR SHARE` como `apex_api` ya pasaban: eran huecos de prueba).

| Hallazgo | Corrección | Prueba |
|---|---|---|
| M-1 base | `FOR SHARE OF k` en `STATE_OF` de `0042`; `apex_api` lo puede (`UPDATE (state, ...)` de `crypto_keys`) | `test_0042::test_la_guarda_toma_for_share...` (INSERT y recifrado contra `FOR UPDATE` de B con `lock_timeout`: 55P03), `test_api_role_paths::test_apex_api_toma_for_share...` |
| L-1 base | prueba | INSERT y recifrado con llave `retired` fallan |
| L-2 base | regex `{22,}` | blob con 21 caracteres de texto cifrado falla |
| L-3 base | docstring del `downgrade` | **V3 (rollback a v0.5.0) debe comprobar que v0.5.0 arranca con la fila `athlete.metric` de `crypto_keys`** |
| L-4 base | `tgrelid = 'athletes.body_metrics'::regclass` en `LIMPIAR_ATHLETES` | la limpieza de la suite |
| L-5 base | decisión: la auditoría es el hook del ORM, no un trigger por tabla | S9-D48 |
| L-A | `lock_member` antes de `ensure_exists` | `test_el_alta_toma_el_candado_del_socio_antes...` |
| L-B | `no-store` en `_responder` (todo error) | `test_los_errores_422_404_y_409_llevan_no_store`; `tests/core` completo en verde |
| L-C | `HIDDEN_HISTORY_FIELDS_BY_TABLE` | `test_notes_de_otra_tabla_no_se_oculta` y la de los cuatro campos solo de su tabla |
| L-D | `isinstance(metric, BodyMetric)` primero | `test_la_puerta_rechaza_un_objeto_que_no_es_una_medicion` |
| L-E | diferido a A2 (L-8) | sin cambio |

**Prueba de concurrencia razonable:** sí, con dos conexiones asyncpg contra `db_test` (A abre INSERT o recifrado sin confirmar; B pide `FOR UPDATE` de la llave con `lock_timeout 300 ms`). **Residual `members.*`:** la misma carrera no tiene guarda de base; queda aceptada (S9-D48).

**Pendiente de A2** (junto con lo anotado en «Verde»): cubetas `members-reveal*` y `warn_reveal_volume` en el `reveal`; 500 `internal_error` opaco ante `MetricDecodeError`; relectura de `voided_at` en la transacción; **L-E / L-8: `GET /audit/{id}` debe sustituir los blobs de `athletes.body_metrics` por «cifrado»**.

Prueba corregida en esta ronda: `tests/core/test_env_example.py` (`CLAVES_SIN_RUTA_TODAVIA == frozenset()`: `athletes-write` ya tiene ruta; P-CAT 2) y `tests/audit/test_history_fields.py` (el caso genérico vuelve a usar `notes`, que ya no se oculta globalmente).

### Evidencia (S9-A1, tras el sello y el checkpoint `8019dee`)

- Gates: no sellantes `crypto` (1756 passed, 63 skipped), `members` (1768 passed), `audit` (1352 passed) y `core/errors` (tests/core + arquitectura, verde), cada uno con `tests/architecture` (898); sellante exacto del plan sobre `athletes` con 14 archivos: 1529 passed, exit 0. `ruff check .`, `ruff format --check .` (1101 archivos) y `mypy src` (288) limpios. P-API: `export-openapi` idéntico a la versión del checkpoint tras las revisiones (sin cambio de contrato).
- P-MIG 5: `$DC start api` → `healthy`; `alembic current` = `0042_athletes_body_metrics (head)`; `$DC start worker`. P-MIG 6: la tabla estaba vacía (0 filas): `alembic downgrade -1 && alembic upgrade head` en `apex-db-1` → `0042 (head)`.
- P-MIG 7: `\d athletes.body_metrics` (13 columnas, `pk_body_metrics`, `ix_body_metrics_member_date (member_id, measured_on DESC, created_at DESC)`, `ck_body_metrics_at_least_one_measure`, `ck_body_metrics_voided_pair`); funciones `guard_body_metrics_insert`, `guard_body_metrics_update` y `forbid_mutation` con `prosecdef = f` y `search_path=pg_catalog`; `tgenabled = 'A'` en los cuatro triggers (`body_metrics_forbid_delete`, `_forbid_truncate`, `_guard_insert`, `_guard_update`).
- `/health`: `status ok`, `db ok`, `migrations ok`, `crypto ok`, `backup attention` (informativo). `version` marca `04791bc`: la imagen baked del api no se reconstruye en A1 (P-REBUILD 4 es de cierre de wave).
- Curl con el admin de desarrollo (login por cookie y token sin imprimir): socios ficticios `27c8e28b-e87d-4bd8-808e-ec40e2a47279` (CON autorización) y `eca92e11-55e8-48ee-99b1-cab5ba32abc4` (SIN autorización). `POST /athletes/{con}/metrics` → 201 (id de la medición `3afd6b6b-80ad-45e6-ac04-4e100c6de1ba`; la respuesta trae solo `has_*`, el valor no aparece); `POST /athletes/{sin}/metrics` → 409 `consent_required` con `cache-control: no-store` y 0 filas en `athletes.body_metrics` para ese socio; `GET /athletes/{con}/metrics` → 200.
- `$PSQL`: `left(weight_g, 5) = apx1.`, `length` 98 / 94 / 93 / 259 (peso, estatura, grasa, notas), `voided_at` nulo; `crypto.crypto_keys`: `athlete.metric`, `encrypt`, `active`, versión 1, `local`; `crypto_ops` de la medición: 4 filas `encrypt`; `audit.audit_log`: una fila `insert` de `athletes.body_metrics`.
- Archivos temporales de la evidencia (cookie, token) borrados. Los dos socios y la medición quedan como datos de prueba de desarrollo (sin DELETE por diseño).

## S9-A2 · Mostrar una medida (2026-11-16)

### Rojo

Sin migración: api y worker arriba, sin banderas. Stubs: `MetricRevealIn/Out` (schemas), `reveal_metric` (`NotImplementedError`) en `metrics.py` y `service.py`, y la ruta 3 solo con la llamada al service (sin cubetas ni IP). Pruebas nuevas: `tests/athletes/test_reveal_service.py` (20), `tests/athletes/test_router_reveal.py` (30 con parametrizaciones), `tests/audit/test_detail_hides_metric_blobs.py` (5); P-CAT: `CON_LIMITE` con la ruta nueva y `test_el_reveal_de_medidas_consume_las_tres_ventanas_de_la_ficha` en `test_user_limits_catalog.py`. Valores derivados a mano del alta por omisión (62.500 g, 165 cm, 22 %).

**Rojo medido** (`-m "not perf"`, un pytest a la vez): sobre esos cinco archivos más `test_error_codes_per_route` y `test_user_limits_catalog`: **40 failed / 55 passed**. 35 por `NotImplementedError` (service y rutas que lo llaman), 2 de L-8 (el detalle devolvía el marcador `{encrypted, key_id, alg}` y no «cifrado»; una tercera de la fila `reveal`/HTTP por el mismo motivo), 1 del catálogo (`test_las_rutas_con_enforce_user_limit_son_con_limite_menos_auth`: la ruta nueva sin `enforce_user_limit`) y 1 de la prueba nueva de las tres ventanas. Pasaron en rojo las que solo dependen de roles, 401, quiosco y 422 (ya cubiertos por el router y los esquemas).

### Verde

- `athletes/metrics.py::reveal_metric(session, member_id, metric_id, field, *, ip, role)`: `members.get_ref` (404 `member_not_found`), lectura de la medición por `id` Y `member_id` con `FOR SHARE OF` y `populate_existing` (404 `metric_not_found` sin delatar; releer `voided_at` dentro de la transacción y bloquear contra una anulación concurrente), socio dado de baja y `role != admin` -> `ForbiddenError` antes de descifrar (M-4), la puerta `_decrypt_metric_field` (409 si anulada), `audit.record("reveal", after={"field", "ip"})`. Un `MetricDecodeError` sube sin capturar: lo vuelve 500 `internal_error` el handler genérico (L-2); no queda fila `reveal` (la `decrypt` ya salió del bus, como en `members`). Campo vacío: `None`, `reveal` sí, `decrypt` no.
- `schemas.py` (`MetricRevealIn` con `extra="forbid"` y `Literal` de cuatro campos; `MetricRevealOut`), `service.py` (fachada), `router.py` (`POST /athletes/{member_id}/metrics/{metric_id}/reveal`: `members-reveal`, `-hour`, `-day` como literales, `warn_reveal_volume`, IP con `client_ip` y los proxies de confianza; admin y coach por `StaffDep`).
- L-8: `audit/diff.py` (`mask_health_fields`, `mask_health_changes`, `ENCRYPTED_MARK = "cifrado"`) y `audit/queries.get`: por tabla y campo (`HIDDEN_HISTORY_FIELDS_BY_TABLE`), no por forma de blob; `changes` con `encrypted = True`; `notes` de otra tabla intacto.
- P-API: `export-openapi` idéntico en dos corridas; `npm run gen:api`; `types.contract.test.ts` 6 passed. `docs/openapi.json` y `web/src/core/api/types.ts` cambian.
- Conteos: nuevas 95 passed junto con los dos catálogos; `tests/athletes` 216 passed (exit 0); `tests/audit` 459 passed (exit 0); `tests/architecture` 899 passed (exit 0); gate no sellante `slice-gate.sh audit tests/audit/test_detail_hides_metric_blobs.py` 904 passed, exit 0. `ruff check .`, `ruff format --check .` (todo `api/`) y `mypy src` (288) limpios. Valores revelados: nunca en esta nota (solo «coincide»).

### Revisiones

`security-reviewer`: 0 CRITICAL/HIGH/MEDIUM y 4 LOW; decisión **S9-D49** en `docs/ddd/DECISIONES.md`.

| Hallazgo | Corrección | Prueba (rojo medido: 2 failed antes del arreglo) |
|---|---|---|
| L-1 | `lock_member` antes de `get_ref` en `reveal_metric` | `test_el_reveal_toma_el_candado_del_socio_antes_de_leer_si_esta_de_baja` |
| L-2 | `logger.warning` en `app.athletes` con `user_id` y `metric_id` en el 403 de la baja | `test_el_403_de_la_baja_deja_un_aviso_con_usuario_y_medicion_sin_valores` |
| L-3 | orden por `lineno` en el catálogo | `test_el_reveal_de_medidas_consume_las_tres_ventanas_de_la_ficha` (hueco de prueba: ya pasaba) |
| L-4 | aceptado (S9-D49) | sin código |

**Pendiente de A3:** la anulación toma la fila de la medición antes que el candado de la cadena de auditoría (mismo orden que el `reveal`).

### Evidencia (S9-A2, tras el sello y el checkpoint `97b6b6d`)

- Gates: no sellante `audit` (904 passed, exit 0); sello `athletes` con los tres archivos del plan: 951 passed, exit 0. `ruff check .`, `ruff format --check .` (todo `api/`) y `mypy src` (288) limpios; el contrato no cambió tras las correcciones (`export-openapi` idéntico al del checkpoint).
- Curl con el admin de desarrollo (token sin imprimir; el api recarga con `--reload`, sin migración). El valor de la medición de A1 (`3afd6b6b-80ad-45e6-ac04-4e100c6de1ba`) no quedó anotado en A1, así que se creó una medición nueva en el mismo socio (`27c8e28b-...`) con un peso conocido: `reveal` 200 y el valor **coincide**. Sobre la de A1: `reveal` 200 con valor numérico presente.
- Conteos (`audit_log` `reveal` de `athletes.body_metrics` | `crypto_ops` `decrypt` de `athlete.metric`): antes 0 | 0; después de los dos `reveal` 2 | 2; las filas `reveal` llevan solo `field` e `ip`.
- `metric_id` de A1 pedido con el socio `eca92e11-...` (otro): 404 `metric_not_found`; los conteos siguen en 2 | 2 (sin filas).
- Archivos temporales borrados. La medición nueva queda como dato de prueba de desarrollo (sin DELETE por diseño).

## S9-A3

Anular una medición (ruta 11, S9-D13, S9-D33; M-3, L-3). Sin migración (la guarda de `0042` ya permite anular, terminal).

### Rojo

- Stubs: `void_metric` y `can_void` con `NotImplementedError`; ruta, fachada y `MetricAlreadyVoided` reales. `tests/athletes/conftest.py` nuevo (`bus_confirmado`).
- `test_void_metric.py` (10), `test_router_void_metric.py` (13), `test_void_rules_pure.py` (18), `test_void_concurrency.py` (1): **37 failed, 4 passed** (exit 1). Los 4 que ya pasaban son los que no llegan al service (socio 403, 401, quiosco, 422 de ids); los 37 fallan por `NotImplementedError` (en los de ruta, 500).
- Incidente de prueba: la prueba de concurrencia en el mismo módulo que `bus_listo` se colgó 6 min (`bus_confirmado` commitea llaves y choca con la transacción de `bus_listo`); se movió a su módulo.

### Verde

- `athletes/metrics.py::void_metric(session, member_id, metric_id, *, by, role)`: `lock_member`, `ensure_exists` (baja = 404 `member_not_found`), fila `FOR UPDATE` + `populate_existing` (404 `metric_not_found`), `can_void` (403 `forbidden` con aviso `user_id`/`metric_id`), 409 `metric_already_voided`, `voided_at` (reloj) y `voided_by`, flush. La auditoría `update` sale del listener de `__audited__`.
- `rules.py`: `SELF_UNDO_WINDOW_H = 24`, `can_void` pura (admin todo; coach lo suyo hasta la hora 24 exacta). `exceptions.py`: `MetricAlreadyVoided`. `router.py`: `POST .../void`, `athletes-write`, `no-store`. `service.py` exporta `void_metric`.
- P-CAT: la ruta en `CON_LIMITE` de `test_error_codes_per_route.py`. P-API: dos exportaciones idénticas; `gen:api`; `types.contract.test.ts` 6 passed.
- Nuevas: 42 passed. `tests/athletes` + `test_0042` + `tests/audit`: 817 passed (exit 0). `tests/architecture`: 899 passed (exit 0). `ruff check .`, `ruff format --check .` (1109) y `mypy src` (288) limpios.
- Nota: `test_la_auditoria_guarda_el_blob_y_el_sujeto_nunca_el_valor` (A1) falló UNA vez por azar (la subcadena `165` apareció dentro de un blob base64 aleatorio); 4 corridas posteriores pasan. Es una prueba de A1 con falso positivo raro, no de A3.

### Revisiones

`security-reviewer`: 0 CRITICAL/HIGH/MEDIUM y 4 LOW. `database-reviewer`: 0 CRITICAL/HIGH, 1 MEDIUM y 4 LOW. Decisión **S9-D50** en `docs/ddd/DECISIONES.md`. El código estaba bien; se corrigieron las pruebas.

| Hallazgo | Tratamiento | Prueba |
|---|---|---|
| DB M-1, DB L-1, Seg L-1 | prueba por protección | `test_void_concurrency.py`: `..._for_update_...` y `..._copia_vieja_...`. Rojo medido quitando la protección: sin `with_for_update`, 1 failed (la de `FOR UPDATE`) y 2 passed; sin `populate_existing`, 1 failed (la de la copia vieja) y 2 passed; restauradas, 3 passed |
| DB L-2 | `try/finally` anidado | misma prueba de dos anulaciones |
| DB L-3 | espera de `pg_locks granted = false` con tope de 10 s | misma prueba |
| DB L-4 | sello con los 5 archivos de A3 y `test_0042` | gate |
| Seg L-2 | 403 antes que 409 | `test_sobre_una_ya_anulada_el_permiso_manda_sobre_el_409` |
| Seg L-3 | `extra` exactos del `warning` y del `info` | `test_el_403_deja_un_warning_...`, `test_la_anulacion_deja_un_info_...` |
| Seg L-4 | aceptado sin código (S9-D50) | sin código |
| Prueba inestable A1 | `claros_en` salta blobs | `test_metrics_service.py` y `test_claros_en_ignora_los_blobs_...` |

### Evidencia (S9-A3, tras el sello y el checkpoint `b987d41`)

- Gate sellante `slice-gate.sh athletes` con los 5 archivos (4 de A3 y `test_0042`): 1045 passed, exit 0. `ruff check .`, `ruff format --check .` (1109) y `mypy src` (288) limpios.
- Curl con el admin de desarrollo (token sin imprimir; api con `--reload`, sin migración) sobre el socio ficticio `27c8e28b-...` con 2 mediciones vivas: anular la más reciente (`0316cd8d-...`, la de A2) 200; repetir 409 `metric_already_voided`; `reveal` 409 `metric_voided`; la lista sin `include_voided` da total 1 y no la trae; con `include_voided=true` total 2 y sí la trae.
- Conteos `audit_log` (`update` de `athletes.body_metrics` de esa medición): antes 0, después 1.
- Archivos temporales borrados. La medición anulada queda como dato de prueba de desarrollo (sin DELETE por diseño).

## Cierre de la Wave 3a (medidas: A1 a A3)

- P-GATES sobre `508f57f` en el worktree limpio `gates`: api lint, formato y `mypy` en verde; `pytest` completo 11547 passed, 103 skipped, 47 deselected, cobertura 95,80 %, con **1 failed y 1 error**. Los dos con código de salida `3221225794` (`0xC0000142`, `STATUS_DLL_INIT_FAILED`: Windows no pudo arrancar el proceso hijo) en el mismo minuto en que el equipo se quedó sin memoria y Claude Code cortó la shell que lanzó la corrida (el `run-gates.sh` siguió vivo y terminó solo): `tests/worker/test_main.py::test_en_un_proceso_limpio_run_once_carga_los_services` (lanza `python -I`) y el teardown de `apex_roles` en `tests/migrations/conftest.py` (lanza `docker exec ... psql`). Ninguno es del código: repetidos aislados en el mismo worktree, junto con `tests/worker/test_worker_crypto_runtime.py` y `tests/migrations/test_db_grants.py` enteros, 326 passed.
- **Desviación anotada:** el resto de `run-gates.sh` (los pasos después de `api pruebas`) se corrió con una copia del script sin la mitad del api (mismo texto, mismo orden): scripts de infraestructura (8), Caddy, web lint, `tsc`, vitest con 2 hilos 4542 passed (261 archivos, cobertura 95,86 %) y build; «todos los gates en verde», exit 0. No se repitió la hora y diez del api: ya estaba en verde salvo los dos fallos de arranque de proceso, comprobados aparte.
- P-REBUILD: `apex-api:local` y `apex-web:local` con `GIT_SHA=508f57f` (etiqueta `org.opencontainers.image.revision` = `508f57f`); `up -d --no-build --force-recreate api worker web`; los tres `healthy`; `nginx -t` ok. El web se construye con `docker buildx build --network host --allow network.host` (con `up --build` buildx pide el permiso y falla). `/health`: `status ok`, `db ok`, `migrations ok`, `crypto ok`, `version 508f57f` (`backup attention`, informativo en desarrollo); web 200.
- Smoke en vivo en 8181 con el admin de desarrollo (clave leída del archivo, nunca impresa; cabecera `Origin` del front) sobre el socio ficticio `27c8e28b-...`: lista 200; alta 201; `reveal` de `weight_g` 200 con el valor enviado y `Cache-Control: no-store`; anular 200; anular otra vez 409 `metric_already_voided`; `reveal` de la anulada 409 `metric_voided`; la lista sigue en total 1. Medición nueva `0f2e75e1-...` (queda anulada como dato de prueba, sin DELETE por diseño).
- `audit_log` de esa medición: `insert` 1, `reveal` 1, `update` 1; ninguna fila contiene el valor en claro.

## S9-B1 · Récords manuales (2026-11-16)

### Rojo

Paso 0: `apex-migracion.flag` tomada por el orquestador; `api` y `worker` parados; volcado `docs/scratch/sprint-09-antes-0043.dump`.

**Stubs** (todos importan; fallan con `NotImplementedError` o con aserción):
- `api/src/app/modules/athletes/records.py` (`add_record`, `list_records`; importa `wods.service` y `results.service`), `rules.py` (`RecordRow` y `pick_current`),
  `schemas.py` (`RecordIn` con `extra="forbid"` y `RecordOut`, sin rangos: son del Verde), `events.py` (`PersonalRecordSet`: es solo forma, ya es real),
  `exceptions.py` (`RecordValidationError`), `service.py` (fachada), `router.py` (rutas 4 y 5 que lanzan `NotImplementedError`; sin `enforce_user_limit` todavía).
- `models.py`: `PersonalRecord` (solo columnas y marcas de auditoría; las `invalidated_*` con `FetchedValue`; sin CHECK ni índices del modelo). Registrarlo SIN
  migración no rompió ninguna prueba vieja (se midió), así que quedó en el Rojo.
- `wods/catalog.py` (`MovementRef`, `BenchmarkRef`, `movement_refs`, `benchmark_refs`) y `wods/service.py` (`movement_for_record`, `benchmark_for_record`, más las
  reexportaciones). `results/leaderboard.py` (`ScoreLike`, `score_key`) y `results/service.py` (`score_key` y `validate_score` en el `__all__`).
- `api/migrations/versions/0043_athletes_personal_records.py`: stub VACÍO (`upgrade` y `downgrade` con `pass`), hijo de `0042`; cabeza única.
- `tests/factories/athletes.py` (`make_record`, stub con el contrato) y entrada `athletes.personal_records` en `FACTORIES`.

**Pruebas nuevas** (valores a mano):
- `tests/athletes/test_pick_current_pure.py` (23), `test_manual_records_service.py` (54), `test_router_records.py` (31), `test_records_concurrency.py` (2, dos altas a
  la vez con `pg_locks`), `tests/results/test_score_key_pure.py` (20), `tests/wods/test_record_catalog_reads.py` (10),
  `tests/migrations/test_0043_athletes_personal_records.py` (104: cada CHECK, rangos, los seis índices con la columna desnuda, cada columna fija del trigger
  parametrizada, terminal, INSERT con `invalidated_*`, DELETE/TRUNCATE, replica, `tgenabled = 'A'`, funciones, downgrade que deja `forbid_mutation` de `0042`).
- Apoyo: `tests/athletes/_apoyo.py` (`ruta_records`, `cuerpo_rm`, `cuerpo_benchmark`, `alta_record`, `filas_de_records`, `auditoria_de_records`).
- Ampliadas: `test_db_grants.py` (32 tablas, listas por columna, DELETE/TRUNCATE negados, worker sin acceso, `-- clasificada:`), `test_api_role_paths.py` (alta
  con `FOR SHARE` del catálogo, invalidación y negados), `test_worker_role_paths.py`, `test_triggers_siempre_activos.py` y `test_0014_*` (`ALWAYS_TRIGGERS`),
  `tests/conftest.py` (`LIMPIAR_ATHLETES` con las dos tablas) y `tests/factories/triggers.py`.
- Arquitectura y catálogos (P-CAT 1 y 4): `test_audited_tables.py` (E4: `athletes.personal_records` pasa a requerida; pendiente `members.push_subscriptions`),
  `test_events_without_pii.py`, `test_service_import_graph.py` (aristas `athletes -> wods` y `athletes -> results`), `test_error_codes_per_route.py`,
  `test_user_limits_catalog.py` (literales `athletes-write` y `staff-read`), `test_list_routes_use_page_params.py`, `test_list_rows_without_sensitive_fields.py`,
  `test_no_physical_delete.py`, `test_no_trigger_tampering.py`, `_imports.py`; `tests/audit/{test_filters,test_recent,test_history_fields}.py`.
- P-CAT 4: `grep` de conftests propios que borren socios: ninguno distinto de los de A1 (sin cambios).

**Rojo medido** (`LC_ALL=C.UTF-8`, `TEST_DATABASE_URL` a `db_test`, un pytest a la vez):
- Nuevas: 240 failed / 4 passed (los 4 son estructurales: rutas publicadas, 403 sin cupo, `service` exporta `score_key` y la cadena de `0043`).
  Motivos: `NotImplementedError` en `add_record` 48, `pick_current` 23, `score_key` 19, ruta POST 10, `make_record` 8 y `movement_for_record`/`benchmark_for_record` 10;
  `42P01` (tabla ausente) en la migración (103) y en las pruebas que cuentan filas.
- Ampliadas: 31 failed (`test_db_grants` 21, `test_triggers_siempre_activos` 3, `test_api_role_paths` 1, `test_audited_tables` 1, `test_user_limits_catalog` 2,
  `tests/audit` 3). Todas por la tabla, el grant, la cubeta o `AUDITABLE_TABLES` que faltan.
- Resto: `tests/athletes tests/wods tests/architecture tests/audit tests/core/test_db.py`: 124 failed / 1774 passed; `tests/results tests/migrations
  tests/core/test_migrations.py`: 147 failed / 1451 passed. **Cero pruebas viejas rotas por los stubs**; todos los fallos son de este slice.
- `ruff check`, `ruff format --check` (1072 archivos) y `mypy src` (289) limpios; `alembic heads` = `0043_athletes_personal_records`.

**Para el Verde:** CHECK, índices, guardas y funciones de `0043` (nombres fijados por las pruebas: `guard_personal_records_insert`/`_update`, triggers
`personal_records_*`, índices `uq_personal_records_result_kind`, `ix_personal_records_{rm,bench,member_date,movement,benchmark}`); `grants.sql` (tres listas y `USAGE`);
`audit/queries.py` (`AUDITABLE_TABLES`, excluida de recientes); `ratelimit` literales en el router; CHECK e índices del modelo; la fábrica `make_record`.
**Estado:** `apex-migracion.flag` puesta; `api` y `worker` parados; sin commit.

### Verde

**Archivos (Verde):**
- Migración `api/migrations/versions/0043_athletes_personal_records.py`: tabla, 15 CHECK (forma, rangos, origen, razón de invalidación), seis índices (los dos de vigentes con la columna desnuda `invalidated_at IS NULL`, S8-D50), funciones `guard_personal_records_insert/_update`, cuatro triggers `personal_records_*` `ENABLE ALWAYS`; el downgrade no borra `athletes.forbid_mutation()`.
- `athletes/records.py` (`add_record`, `list_records`), `rules.pick_current` (+ `_Score`), `models.PersonalRecord` (CHECK e índices espejo), `router.py` (rutas 4 y 5 con `athletes-write` y `staff-read`).
- `wods/catalog.py` (`movement_refs`, `benchmark_refs`) y `wods/service.py` (`movement_for_record`, `benchmark_for_record`, `FOR SHARE`, dataclasses planas); `results/leaderboard.py` (`ScoreLike` solo lectura, `score_key` = `_tie_key_of`; las claves aceptan cualquier `ScoreLike`).
- `infra/db/grants.sql` (tres listas: comentario, INSERT por columna sin `invalidated_*`, UPDATE de las cuatro de invalidación y `updated_at`, `clasificada`), `audit/queries.py` (`AUDITABLE_TABLES` y excluida de recientes), `core/locks.py` (docstring del orden), `tests/factories/athletes.py` (`make_record`), `docs/ddd/DECISIONES.md` (S9-D51, S9-D52), `docs/openapi.json` y `web/src/core/api/types.ts` regenerados.

**Desviaciones:** (1) la guarda de UPDATE rechaza cualquier UPDATE de una fila ya invalidada, incluso uno sin cambio de valores (la prueba «terminal» lo exige; S9-D52). (2) `created_at` del récord manual y de `make_record` usa `clock_timestamp()` (S9-D52; el desempate N-45 con `now()` de inicio de transacción daba el orden invertido bajo concurrencia). (3) `db_test` estaba estampada en `0043` por el stub vacío del Rojo: se devolvió a `0042` y se subió con la migración real. Arista `athletes -> results` en B1 (S9-D51). Ningún cambio a pruebas del Rojo.

**Medido:** `0043` 104/104; `pick_current` + `score_key` + `record_catalog_reads` 53/53; `athletes` (3 archivos nuevos) 87/87 + factory 6; `athletes+wods+results` 678 passed. `ruff check`, `ruff format --check` (1118) y `mypy src` (289) limpios. `export-openapi` dos veces idéntico (cmp), `npm run gen:api`, `types.contract.test.ts` 6/6 (`--maxWorkers=2`), `tsc --noEmit` exit 0.

**Ronda de corrección tras la primera corrida completa (3 fallos, todos de este slice):** (a) `test_audited_tables::test_recent_permite_las_seis...`: el conjunto esperado de excluidas no incluía `athletes.personal_records`; es la prueba la que estaba mal (S9-D19 la excluye de recientes), se le añadió la entrada. (b) `test_file_and_function_size`: `add_record` pasaba de 50 líneas; se extrajo `_new_record`. (c) `test_history_fields::test_la_invalidacion_de_un_record...`: `diff.history_fields` devolvía todas las claves de `before` y `after` y su docstring dice «las columnas que cambiaron»; ahora devuelve solo las que difieren (código, no prueba; sin efecto en las pruebas ya existentes).

**Corridas finales (un pytest a la vez, `db_test`, `-m "not perf"`):** `tests/athletes tests/wods tests/results tests/architecture tests/audit tests/core/test_db.py tests/migrations/test_0043_...` 2155 passed, 17 deselected (exit 0); `tests/migrations tests/core/test_migrations.py` 1445 passed (exit 0; corrida previa a (a)-(c), que no tocan migraciones). Una sola cabeza de Alembic: `0043_athletes_personal_records`.

**Gates no sellantes:** `slice-gate.sh wods tests/wods/test_record_catalog_reads.py` verde (916 passed, exit 0); `slice-gate.sh results tests/results/test_score_key_pure.py` verde (926 passed, exit 0). Sin commit, sin gate sellante de `athletes`, api/worker sin arrancar, bandera intacta.

### Revisiones

`security-reviewer`: 0 CRITICAL/HIGH/MEDIUM, 4 LOW. `database-reviewer`: 3 MEDIUM, 6 LOW. `0043` no estaba aplicada en ningún servidor: se editó en sitio (db_test: bajada a `0042` y vuelta a subir). Rojo medido antes del arreglo: 20 failed (9 de migración, 11 de las pruebas nuevas `tests/athletes/test_records_review_b1.py`); luego verde.

- **BD M1** (`kind` como parámetro no casa con el índice parcial): `current_query`, `list_query` y la comprobación del duplicado usan `literal_column("'rm'")` / `'benchmark'` (S8-D50). Pruebas que compilan las consultas y afirman `kind = 'rm'` y ningún `kind = %(`. Revisadas las demás comparaciones contra columnas de predicado parcial: `invalidated_at IS NULL` ya iba desnuda; `source`, `result_id` y `movement_id IS NOT NULL` no se consultan en B1 (B2 en S9-D54).
- **BD M2** (`created_at` con `clock_timestamp()` solo en el alta manual): ahora es el `DEFAULT` de la columna en la migración y el modelo; `_new_record` y `make_record` ya no lo ponen. Cubre a B3. Prueba de la base: dos altas en la misma transacción quedan en orden y el default es `clock_timestamp()`. S9-D52 reescrita.
- **BD M3** (`updated_at < created_at` al nacer): mismo default y `CHECK updated_at >= created_at` (`ck_personal_records_updated_after_created`, probado).
- **Seg L1** (sin tope de manuales): 409 `record_duplicate` ante el idéntico vivo (mismo socio, objetivo, marca y fecha), bajo `lock_member`; la misma marca otro día no lo es. Código en `errorCodes.ts` y 409 declarado en la ruta; OpenAPI y tipos regenerados (dos exportaciones idénticas). Efecto sobre pruebas del Rojo: las tres que repetían EXACTAMENTE un récord para probar «igual queda histórico» (`test_un_rm_menor_o_igual...`, `test_un_benchmark_mas_rapido...` y la de concurrencia) usan ahora la misma marca un día después (empata y gana el más antiguo); la intención de cada una se conserva. `_current_ids` y la lista tienen orden total (id).
- **Seg L2** (el INSERT del api lleva `source`, `result_id`, `wod_id`, `capped`): aceptado, S9-D53.
- **Seg L3** (`validate_score` filtraba «WOD» y campos ajenos): se captura `ResultValidationError` y sale `RecordValidationError` con un `field` de `RecordIn` (`wod_id` -> `benchmark_id`; `capped` y `scaled_movement_ids` -> `level`) y mensaje propio. Prueba parametrizada con `monkeypatch`.
- **Seg L4** (CHECK `source <> 'manual' OR NOT capped`) y **BD L6** (`benchmark_shape` con `num_nonnulls(seconds, rounds, reps, load_g) >= 1`): hechos y probados. Las pruebas del Rojo que usaban un manual `capped` válido pasaron a derivado.
- **BD L4/L5** (desempate por id): `pick_current` (prueba: mismo resultado con tres órdenes de entrada) y lista `(achieved_on, created_at, id)` descendentes (prueba sobre el SQL compilado).
- **BD L7**: `invalidated_by_pair`, `invalidated_result_superseded` (verificado contra S9-D10/D11: solo la corrección, `superseded`, tiene resultado nuevo; anular no; la prueba que invalidaba un `voided` con resultado nuevo ahora espera CHECK) e `invalidated_after_created`. Los CHECK que la guarda tapa se prueban saltando SOLO la guarda de INSERT dentro de la transacción de la prueba (se revierte). Los ayudantes de invalidación usan `clock_timestamp()` (S9-D52).
- **BD L8**: la guarda rechaza cambiar `updated_at` sin invalidar (la prueba que lo avanzaba suelto pasó de `OK` a `GUARDA`).
- **BD L9** (índices `_movement` y `_benchmark` sin consulta): aceptado, S9-D54. **CONDICIÓN PARA B2:** `RecordsProbe` usará `EXISTS ... WHERE movement_id = :id AND invalidated_at IS NULL` (y `benchmark_id`), columna desnuda, verificado con `EXPLAIN`.

**Corrida completa tras las revisiones:** `tests/athletes tests/wods tests/results tests/architecture tests/audit tests/migrations tests/core/test_migrations.py tests/core/test_db.py` 3516 passed, 17 deselected (exit 0); ruff, ruff format y mypy limpios; `export-openapi` x2 idéntico, `gen:api`, vitest `src/core/api` y `tsc --noEmit` verdes.

### Evidencia (S9-B1, tras el sello y el checkpoint a90afe8)

- Sello `slice-gate.sh athletes` (11 archivos: los del plan, `test_records_concurrency.py` y `test_records_review_b1.py`): 1521 passed, exit 0. Antes, los gates no sellantes de `wods` (916) y `results` (926) otra vez en verde, exit 0. Checkpoint `a90afe8`.
- P-MIG 5 a 7 sobre `apex-db-1`: `start api` healthy; `alembic current` = `0043_athletes_personal_records (head)`; `start worker`; ciclo `downgrade 0042` / `upgrade head` sin error (tabla vacía) y de nuevo `current` = 0043 head. `\d athletes.personal_records`: 23 columnas, `created_at` y `updated_at` con `DEFAULT clock_timestamp()`, 6 índices (los dos de vigentes con `kind = '...' AND invalidated_at IS NULL`, columna desnuda), 19 CHECK `ck_personal_records_*`, cuatro triggers «firing always»; `tgenabled` = A en los cuatro (`forbid_delete`, `forbid_truncate`, `guard_insert`, `guard_update`); `\df+`: las dos guardas nuevas y `forbid_mutation` `SECURITY INVOKER` (`prosecdef = f`) con `search_path=pg_catalog`.
- Smoke con el admin de desarrollo sobre el socio ficticio `27c8e28b-...` (solo códigos): login 200; `POST /athletes/{id}/records` (RM manual) 201; el mismo cuerpo otra vez 409 `record_duplicate`; `GET /athletes/{id}/records` 200 (1 ítem, `total` 1, `is_current` true); `POST` sin `value_g` 422 con `field = value_g`. Queda UNA fila de prueba en `apex-db-1` (la tabla prohíbe DELETE; es de un socio ficticio de desarrollo). Temporales borrados; sin secretos en pantalla ni aquí.
- Pendiente de despliegue (no de este slice): `dbsetup` con `--no-deps` para las 32 tablas clasificadas y `derive-records` (V2, cierre de v0.6).

## S9-B2 · Puerto RecordsProbe (2026-11-16)

### Rojo

Stubs con `NotImplementedError` (`wods/probe.records_probe`, `athletes/service._RecordsProbe`), `LockedByRecords` y `RecordsProbeNotRegistered` ya definidas, el cableado en `movements.update_movement` y `benchmarks.update_benchmark`. Pruebas nuevas: `tests/wods/test_locked_by_records.py` (5), `tests/athletes/test_records_probe.py` (6) y 6 casos nuevos en `tests/architecture/test_gates_registered.py` (create_app, CLI y proceso limpio main/cli/worker). Corrida de los tres archivos: **10 failed, 19 passed** (los 19 incluyen los ya existentes de gates y los casos de registro, que pasan con el stub registrado). Los 10 fallos: `NotImplementedError: S9-B2: stub` (puerto sin implementar: 4 de wods, 5 de athletes, y el de «sin puerto falla cerrado» en gates).

### Verde

- `wods/probe.py`: `RecordsProbe` (Protocol), `set_records_probe`, `current_records_probe`, `records_probe()` (falla cerrado con `RecordsProbeNotRegistered`); reexportados en `wods/service.py`. `wods/exceptions.py`: `LockedByRecords` (422 `locked_by_records`, `field`) y `RecordsProbeNotRegistered`.
- `movements.update_movement` (`unit`) y `benchmarks.update_benchmark` (`score_type`) consultan el puerto bajo el `FOR UPDATE` que ya toman, tras la comprobación de WODs.
- `athletes/service.py`: `_RecordsProbe` con `SELECT EXISTS (SELECT * FROM athletes.personal_records WHERE movement_id = :id AND invalidated_at IS NULL)` (y `benchmark_id`), columna desnuda (S8-D50); se registra al importarse.
- P-API: 422 ya estaba declarado en las dos rutas PATCH; `locked_by_records` en `web/src/core/api/errorCodes.ts`. `export-openapi` x2 idéntico y sin diferencia con `docs/openapi.json` (no cambia el contrato, no hace falta `gen:api`); `tsc --noEmit` limpio; vitest `src/core/api` 285 passed.
- Desviación menor: el plan dice «`LIMIT 1`»; se usa `EXISTS` (S9-D54), que corta en la primera fila; la prueba afirma `EXISTS` y la columna desnuda.
- **EXPLAIN (S9-D54)** sobre `db_test`, sentencia preparada con `plan_cache_mode = force_generic_plan` y `enable_seqscan = off` (tabla vacía): movimiento = `Index Scan using ix_personal_records_movement`, `Index Cond: (movement_id = $1)`, `Filter: (invalidated_at IS NULL)`; benchmark = `Index Scan using ix_personal_records_benchmark`, `Index Cond: (benchmark_id = $1)`. Con `enable_seqscan = on` y tabla vacía el plan también eligió el índice. El índice sirve: 0043 no se toca.

- Corrida: `tests/wods tests/athletes tests/results tests/architecture` 1612 passed, 3 deselected (exit 0); ruff check, ruff format y mypy limpios. Gate no sellante `slice-gate.sh athletes tests/athletes/test_records_probe.py` abajo. Sin commit, sin sello de `wods`.
- Gate `slice-gate.sh athletes tests/athletes/test_records_probe.py`: 917 passed, exit 0 (el script escribe su sello de `athletes` aunque el plan lo llame no sellante; el sello de `wods` queda pendiente). Árbol sin commit.

### Revisiones

`security-reviewer`: APROBADO, 0 CRITICAL/HIGH/MEDIUM, 5 LOW (decisión S9-D56).
- **LOW-1** (TOCTOU depende de READ COMMITTED): la prueba de la carrera afirma `SHOW transaction_isolation = read committed` en las dos sesiones y `_has_live` lo documenta.
- **LOW-2** (puerto permisivo desde otro módulo): `tests/architecture/test_probe_registration_sites.py`, barrido por AST de `src`; caso sintético dentro de la prueba demuestra que detecta una llamada indebida (`modules/members/service.py` llamando `set_records_probe`). Sin rojo posible: protege un invariante que ya se cumple; el caso sintético es la prueba de que el detector no está vacío.
- **LOW-3** (derivados sin `FOR SHARE` del catálogo): ACEPTADO. Condición para B3 en S9-D56: dejarlo escrito y probar que con un derivado vivo el `PATCH` de `unit` da 422 (por uso o por el puerto), nunca pasa.
- **LOW-4**: docstring de `wods/router.py` cita `locked_by_records` también en `PATCH /movements`.
- **LOW-5**: docstring de `athletes/service.py` corregido a `EXISTS`; prueba `test_los_dos_indices_parciales_sirven_a_la_consulta_del_puerto` (plan genérico, sin Seq Scan) afirma los dos índices.

**Corrida tras las revisiones:** `tests/wods tests/athletes tests/results tests/architecture` 1615 passed, 3 deselected (exit 0); ruff, format y mypy limpios; contrato sin cambios (P-API no aplica de nuevo). Sello: `slice-gate.sh wods tests/wods/test_locked_by_records.py tests/athletes/test_records_probe.py tests/architecture/test_probe_registration_sites.py`.

### Evidencia (S9-B2, tras el sello y el checkpoint 62d947f)

- Gate no sellante `slice-gate.sh athletes tests/athletes/test_records_probe.py`: 920 passed, exit 0. Sello `slice-gate.sh wods tests/wods/test_locked_by_records.py tests/athletes/test_records_probe.py tests/architecture/test_probe_registration_sites.py`: 925 passed, exit 0. Checkpoint `62d947f`.
- `$DC restart worker` (carga `athletes`): arrancó; `/health` 200.
- Smoke 8181 con el admin de desarrollo sobre el movimiento del récord RM vivo del socio ficticio de B1: login 200; `PATCH /movements/{id}` con `{"unit":"reps"}` = 422 (`validation_error`, `field = unit`: respondió la guarda de uso por WODs, que va antes que el puerto; el camino del puerto lo cubren las pruebas con base real). No cambió nada. Temporales borrados.

## S9-B3 · RM derivado por carga (2026-11-16)

### Rojo

Stubs con `NotImplementedError`: `athletes/derive.py` (`on_wod_result_validated`, `subscribe_handlers`; NO suscritos: un stub suscrito tumbaría todo `PUT /results` de las pruebas viejas, la suscripción queda para el Verde), `athletes/rules.py` (`RecordDraft` y `derive_rm`), `results/reads.get_mark` + `ResultMark` (con `source`) en `results/schemas.py` y `results/service.py`, `wods/catalog.record_meta_for` + `WodRecordMeta` reexportados en `wods/service.py`, `RecordOut.result_source` (por omisión `None`) y `derive` en `PRIVATE_HELPERS["athletes"]` de `tests/architecture/_imports.py`.

Pruebas nuevas (valores a mano, gramos enteros): `tests/athletes/test_derive_rm_pure.py` (17), `test_derive_rm_service.py` (14, por `PUT /results` real; incluye el 23505 con fila invalidada, keyring sin cargar, convivencia con manual, `result_source` desk/kiosk/manual, presupuesto de sentencias contra el mismo registro sin handler y S9-D56), `test_derive_soft_fail.py` (6: fallo forzado por suscriptor de `PersonalRecordSet`, `alert` parcheado que lanza, sink que lanza, sesión usable + `run_verification` ok, fallo del segundo resultado, y «base ocupada» con la app real, `get_session` real y un suscriptor de `WodResultRecorded` que inserta desde otra conexión sin confirmar con el mismo `(result_id, kind)` → 503 `busy`, enmienda 4), `tests/results/test_get_mark.py` (7), `tests/wods/test_record_meta_for.py` (5), `tests/architecture/test_athletes_handlers_no_locks.py` (4, AST + suscripción) y ayudas `tests/athletes/_apoyo_derivar.py` (fixture `alertas` en `conftest`).

Corrida de los seis archivos: **46 failed, 7 passed**. Motivos: `NotImplementedError: derive_rm` (17 puras); `get_mark` (6) y `record_meta_for` (5) sin implementar; 11 del service y 6 del soft-fail porque el handler aún no está suscrito (no hay récord, ni log `derivación omitida`, ni alerta, ni 503: `201` en vez de 503 en «base ocupada»); 1 de arquitectura (nadie suscrito a `WodResultValidated`). Los 7 verdes son negativos o ya ciertos: 2 «marcas que no derivan» (0 g y scaled), «WOD que no es de carga», `get_mark` en `__all__` y 3 de AST (handlers exactos, sin candados, control del analizador).

Regresión de lo viejo: `tests/athletes tests/results tests/wods tests/architecture` sin los 6 archivos nuevos = 1611 passed y 4 failed en la primera pasada; los 4 eran míos, no de lo viejo, y quedaron corregidos: `test_router_records` (el conjunto exacto de campos de `RecordOut` suma `result_source`, L-4, cambio legítimo del plan) y 2 de `test_no_cross_models` (el stub importaba `results.events`; ahora `results.service`). Segunda pasada de `test_router_records.py` y `tests/architecture`: 947 passed, 1 failed (la suscripción pendiente del Verde). `ruff check`, `ruff format --check` y `mypy src` limpios.

Para el Verde: suscribir `on_wod_result_validated` al importar `athletes/service.py` (`subscribe_handlers`), implementar `derive_rm`, `get_mark`, `record_meta_for`, el handler con el patrón de savepoint (S9-D42), `result_source` en `_to_out`/`_present` de `athletes/records.py` (lectura por lote de `get_mark`/marcas, sin consulta por fila), y `session.py`/`__all__` de `athletes/service.py`. Nota: el presupuesto de sentencias exige que `record_meta_for` sea UNA consulta (principal incluido) y `get_mark` otra.

### Verde

S9-D56 (paso 1): la prueba `test_el_patch_de_unit_con_un_derivado_vivo_da_422_y_nunca_pasa` YA estaba en `test_derive_rm_service.py` (la 14.ª); corrida sola antes de implementar: **1 failed** (no había derivado vivo que comprobar). Con el Verde pasa: la guarda de uso del catálogo (y el puerto) da 422 `field = unit` y la unidad queda en `kg`; es una prueba de invariante, no de comportamiento nuevo.

Implementado: `athletes/rules.py::derive_rm` (pura); `athletes/derive.py` (handler con el patrón S9-D42: lecturas y `flush` fuera, `begin_nested` con `add`, `flush` y `PersonalRecordSet` dentro; `except DBAPIError` re-lanza el original si `translate_busy`, 23505 de `uq_personal_records_result_kind` = no-op sin alerta, el resto fallo blando con log `derivación omitida` (ids solo en el log) y `alert` en su propio `try` con `{"error_type": ...}`; si `derive_rm(mark, meta, None)` ya da `None` no lee el vigente: presupuesto de 2 sentencias); `athletes/records.py::current_rm` (una consulta, sin candado) y `result_source` por lote; `athletes/service.py` llama `derive.subscribe_handlers()` al importarse; `results/reads.py::get_mark` (una consulta por clave, sin candado ni JOIN) y `result_sources` (por lote, nueva, exportada en `results/service.py`; no estaba en el plan: sin ella `result_source` habría costado una consulta por fila); `wods/catalog.py::record_meta_for` (UNA consulta con `LEFT JOIN` al principal, sin candado).

Corrección de una prueba mala: `test_presupuesto_de_sentencias_por_put_results` quitaba el handler del bus para medir la base «sin handler» y no lo devolvía, así que la medición «con derivación» corría sin handler (4 − 4 = 0). Ahora lo vuelve a suscribir en un `finally`; la afirmación no cambió.

Resultados: los 6 archivos del Rojo = 53 passed (antes 46 failed, 7 passed). `tests/athletes tests/results tests/wods tests/architecture tests/core/test_alerts.py` = **1714 passed** (3 perf deseleccionados). `ruff check`, `ruff format` y `mypy src` limpios. P-API: `RecordOut.result_source` suma 15 líneas a `docs/openapi.json` (export dos veces, mismo sha) y 2 a `web/src/core/api/types.ts`; `types.contract.test.ts` 6 passed, `tsc --noEmit` limpio.

Gates no sellantes: `slice-gate.sh results tests/results/test_get_mark.py tests/results/test_record_service.py` = 940 passed, exit 0; `slice-gate.sh wods tests/wods/test_record_meta_for.py` = verde, exit 0. `$DC restart worker`: `apex-worker-1` healthy a los 25 s; `/health` ok (`migrations: ok`, `crypto: ok`). Sin sellar `athletes` y sin commit (revisiones de seguridad y base de datos pendientes).

### Revisiones

Rojo medido (`tests/athletes/test_derive_review_b3.py`, 12 pruebas, antes del arreglo): **8 failed, 4 passed** (los 4 verdes: 23514, presupuesto `== 4`, y los dos planes, que ya eran ciertos). Verde: 12 passed; `tests/athletes tests/results tests/wods tests/architecture tests/core/test_alerts.py` = **1726 passed**; ruff, format y mypy limpios; contrato sin cambios (sin P-API).
- MEDIUM (seguridad y base de datos): el fallo blando solo cubría el INSERT. Arreglo: `on_wod_result_validated` hace `flush` fuera y abre UN `begin_nested()` que envuelve `_derive` (lecturas, reglas, `current_rm`, `_record_of`, add, flush, emisión); S9-D57 en `DECISIONES.md`. Pruebas: `derive_rm` y `current_rm` que lanzan, 42P01 real en `get_mark` con la misma transacción confirmando después, `ProgrammingError` simulado.
- LOW 1: `except (DatabaseBusy, EventDepthExceeded): raise` antes de lo genérico; pruebas con suscriptores de `PersonalRecordSet`.
- LOW 2: prueba en ejecución de sentencias desde el inicio del handler: sin FOR UPDATE ni FOR SHARE; el único candado asesor es el de la cadena de auditoría (lo toma `core/audit` al `flush`, último del orden), a lo sumo uno.
- LOW 3: 23514 (`rm_shape` violada) alerta `IntegrityError` y no se confunde con el 23505.
- LOW 4: docstrings de `get_mark` y `result_sources`: no filtran por socio, el llamador responde del alcance.
- LOW 5: presupuesto `== 2` sin récord y `== 4` con derivación (también en `test_derive_rm_service.py`).
- LOW 6: `validated_by` nulo deja `logger.warning` con ids.
- LOW 7: `EXPLAIN EXECUTE` genérico con `enable_seqscan = off`: `current_rm` usa `ix_personal_records_rm`; `record_meta_for` usa `uq_wod_movements_primary`; sin Seq Scan.
Nota: un `except A, B:` sin paréntesis es sintaxis de 3.14; el proyecto es 3.12, se usó la tupla.

### Evidencia (S9-B3, tras el sello y el checkpoint 09a4134)

Worker reiniciado (`apex-worker-1` healthy a los 25 s). No había WOD `load` con principal en desarrollo: creé por la API, con el admin, un movimiento ficticio «Back Squat ficticio S9B3» (kg, `POST /movements` 201) y un WOD ficticio del 2026-11-14 de tipo `load` con ese principal (`POST /wods` 201). Login 200. `PUT /results` (socio ficticio `27c8e28b-...`, rx, 100000 g) = **201**. `$PSQL` de `athletes.personal_records` del socio: `kind=rm, source=derived, value_g=100000, result_id presente = t` (coincide con el id devuelto por el PUT); la otra fila, `manual 123000` (ya existía), queda como vigente por ser mayor (N-45).

## S9-B4 · Récord de benchmark derivado (2026-11-16)

### Rojo

Stub con `NotImplementedError`: `athletes/rules.py::derive_benchmark`. La rama del handler NO se cableó en el Rojo (un stub cableado caería en el fallo blando y alertaría en todo `PUT /results` de WOD con benchmark de las pruebas viejas); se cablea en el Verde.

Pruebas nuevas (valores a mano): `tests/athletes/test_derive_benchmark_pure.py` (30 casos: los cuatro tipos de marca, empate, `scaled` contra `rx`, `rx_plus`, `capped` primero y detrás de quien terminó, sin benchmark, tipo `none`, marca sin valores) y `tests/athletes/test_derive_benchmark_service.py` (14, por `PUT /results` real: 245 s sobre 260 crea y 270 no, empate, dos WODs del mismo benchmark y otro benchmark, capped, benchmark `load` con principal = dos récords, cada uno contra su vigente, fallo blando en benchmark, fallo en el segundo récord sin deshacer el primero, fallo en el primero sin impedir el segundo, base ocupada en benchmark = 503 sin RM ni resultado, doble emisión no-op, presupuesto 4 y 6 sentencias).

Corrida: **43 failed, 1 passed**. Motivos: 30 `NotImplementedError: derive_benchmark` (puras); 13 del service porque la rama no existe (no hay récord de benchmark, ni alerta, ni 503). El verde es la doble emisión (no-op ya cierto). Ajuste de pruebas durante el Rojo: un WOD por fecha (`WodDateTaken`), los WODs de benchmark usan fechas distintas del WOD de la escena.

### Verde

Implementado: `athletes/rules.py::derive_benchmark` (pura: `score_key` del leaderboard, estrictamente menor; tipo sin leaderboard o marca sin valores no derivan), `athletes/records.py::current_benchmark` (desviación menor: el plan solo nombraba `rules` y `derive`; la lectura vive junto a `current_rm`), `athletes/derive.py` reestructurado con un savepoint por tramo (`_guarded`, `_plan`, `_derive_rm`, `_derive_benchmark`, `_insert`) = decisión nueva **S9-D58** en `DECISIONES.md`. Sin migración ni cambio de contrato (sin P-API).

Resultados: los 5 archivos de derivación (`test_derive_benchmark_pure`, `_service`, `test_derive_rm_service`, `test_derive_soft_fail`, `test_derive_review_b3`) = 76 passed (antes 43 failed, 1 passed en los dos nuevos). `tests/athletes tests/results tests/wods tests/architecture tests/core/test_alerts.py` = **1770 passed** (3 perf deseleccionados). Presupuesto de sentencias de S9-D30 intacto: 2 y 4 (RM), y 4 (benchmark de tiempo) y 6 (benchmark de carga con principal) en la prueba nueva. `ruff check`, `ruff format --check` y `mypy src` limpios. Pendiente: revisión de seguridad; sin sellar ni commit.

### Revisiones

Revisión de seguridad: APROBADO, 0 CRITICAL/HIGH, 1 MEDIUM y 6 LOW; decisión nueva S9-D59 en `DECISIONES.md`.

Rojo medido: **14 failed, 42 passed** en `test_derive_benchmark_pure.py`, `test_derive_benchmark_review.py` (nuevo) y `test_derive_soft_fail.py`. Los 14 rojos: 9 puros (0 g, otro benchmark, marca sin el campo de su tipo x6, capped sin reps) y 5 de service (regla que lanza omitía el RM, otro benchmark sin aviso, 0 g, y dos de conexión caída). Los 42 verdes incluyen toda la cobertura MEDIUM-1, que ya era cierta con el código de B4 y ahora queda fijada.

- MEDIUM-1: pruebas (a) `DBAPIError` real (42P01) y 23514 solo en el tramo benchmark con el RM ya creado: 201, el RM queda, sesión usable y commit; (b) `EventDepthExceeded` re-lanzada y 55P03 real en el tramo benchmark (app real, otra conexión retiene un `benchmark` con el mismo `(result_id, kind)`): 503 `busy` con `Retry-After: 1`, ni resultado ni RM, sin alerta; (c) tras un fallo blando del benchmark, una sola fila `insert` de `personal_records` (la del RM) y `run_verification` ok; (d) con dos récords el handler no pide `FOR UPDATE`, `FOR SHARE` ni más de un asesor distinto (el de la cadena).
- LOW-2: `_possible` evalúa cada regla en su propio `try`; una `derive_benchmark` que lanza deja el RM y una alerta `ValueError`.
- LOW-3: `derive_benchmark` exige el campo de su tipo (`_BENCHMARK_FIELDS`, `capped` suma `reps`).
- LOW-4: no deriva con `mark.benchmark_id != meta.benchmark_id`; `warning` con ids.
- LOW-5: un benchmark `load` con 0 g no crea récord (la prueba que lo aceptaba se invirtió con motivo: coherente con `derive_rm`).
- LOW-6: un error de conexión (`is_connection_error`, incluido un `ConnectionRefusedError` pelado) se re-lanza sin alertas ni más tramos.
- LOW-7: docstring de `derive.py` al día (tres tramos, `current_benchmark`, S9-D59). Condición para EP-25 anotada en S9-D59 (`_guarded` traga un `DomainError` de un suscriptor de `PersonalRecordSet`).

Verde tras las revisiones: `tests/athletes tests/results tests/wods tests/architecture tests/core/test_alerts.py` = **1790 passed** (3 perf deseleccionados); ruff, format y mypy limpios. Sin cambio de contrato.

### Evidencia (S9-B4, tras el sello y el checkpoint d4af13f)

Sello de `athletes` (gate: 987 passed, exit 0) y checkpoint `d4af13f`. Worker reiniciado (`apex-worker-1` healthy). En desarrollo ya existía un WOD con benchmark utilizable (`372d44af-...`, 2026-11-15, `time`, cap 600, con `benchmark_id`); no se creó ningún dato nuevo salvo el resultado. Login admin 200 (token de 334 caracteres, sin mostrarlo). `PUT /results` del socio ficticio `27c8e28b-...`, rx, 245 s = **201**. `$PSQL` de `athletes.personal_records` del socio, `kind = benchmark`: `source=derived, seconds=245, level=rx, capped=f, result_id presente=t, vivo=t`.
