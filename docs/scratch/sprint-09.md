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
