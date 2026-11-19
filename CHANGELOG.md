# Changelog

Formato: una sección por versión, la más reciente primero. `scripts/ci/check-release-version.sh`
compara la etiqueta con el encabezado de la primera sección, con `api/pyproject.toml` y con
`web/package.json`. El SHA de cierre vive en el cuerpo de la sección (no lo exige ningún script) y
es el que se pasa a `infra/deploy.sh --expect-sha`.

## [0.6.0]

Fecha de cierre: 2026-11-19. SHA de cierre: el del commit etiquetado `v0.6.0` (`git rev-parse v0.6.0^{commit}`); es el valor que se pasa a `infra/deploy.sh --expect-sha`. La etiqueta se publica en GitHub junto con `main`; el Release en borrador lo arma la CI (`release.yml`).

Sexta versión desplegable: perfil del atleta. Medidas corporales cifradas, récords personales manuales y derivados de los resultados (RM por carga y benchmarks), su invalidación al corregir o anular, la serie de cada benchmark y la pestaña Atleta de la ficha con cinco subpestañas. Cierra las tres deudas aceptadas de la v0.5.

### Sprint 9 · Medidas corporales (EP-24, US-178, US-179)
- Módulo `athletes` (esquema `athletes`, migraciones 0042 a 0044): `athletes.body_metrics` con peso en gramos, estatura en cm, % de grasa y notas, las cuatro cifradas con la clase nueva `athlete.metric` (blob `apx1.`, sin índice ciego). La llave la crea el arranque del api; no hay paso `init-keys` (S9-D5).
- Sin autorización de datos del socio no se guarda ninguna medida: 409 `consent_required` y ningún `encrypt` (S9-D29).
- La lista nunca descifra: cada valor se ve con «Mostrar» (`POST /athletes/{id}/metrics/{metric_id}/reveal`), que deja una fila `reveal` en la auditoría y un `decrypt` en `crypto_ops`, también para un campo vacío (P6), con las ventanas de `members-reveal`. Anular una medida es lógico (`voided_at`), con CHECK de orden temporal (0044, S9-D70).

### Sprint 9 · Récords personales (US-180 a US-183)
- `athletes.personal_records`: récords manuales (RM en kg, con fecha) y derivados de `results` en la misma transacción del resultado: un `rx` o `rx_plus` validado de un WOD por carga crea el RM del movimiento principal; un mejor tiempo o marca de un benchmark crea su récord, agrupado por `benchmark_id`. Un `scaled` no deriva (N-45).
- Corregir o anular el resultado invalida el récord sin borrarlo (`invalidated_at`, motivo `superseded` o `voided`) y repone el mejor que quede (S9-D11). Un fallo del handler no tumba el resultado: queda una alerta sin ids y `derive-records` repara (fallo blando, S9-D42).
- `derive-records [--dry-run] --as <admin>` (S9-D21): paso de despliegue de v0.6 que deriva los récords de los resultados anteriores; idempotente, auditado, una transacción por socio. Puerto `RecordsProbe` para que `wods` sepa si un movimiento o benchmark tiene récords sin importar `athletes`.
- Rutas: 11 bajo `/athletes/{member_id}`, solo admin y coach. Cubeta nueva `athletes-write` (30/min): 28 cubetas y 27 variables `USER_*`.

### Sprint 9 · Pestaña Atleta (US-184)
- En la ficha del socio: Resumen, Medidas corporales, RMs por movimiento, Récords y Benchmarks (con la gráfica de la serie y «Mejor»), con `Tabs variant="pills"`, `StatusTag mark="best"` y `TrendChart` en `shared/ui`. Ninguna subpestaña pide un `reveal` al abrirse. Controles de 44 px.
- Historial del socio con frases para medidas, récords y resultados, y la pantalla Auditoría con las 25 tablas que audita el api (la lista se había quedado en la de v0.1; una prueba de contrato las mantiene iguales).

### Sprint 9 · Deudas de la v0.5 cerradas
- Inactividad de 10 minutos del quiosco: E2E de stack con reloj falso (`kiosk-idle.spec.ts`) y una espera REAL de 10 minutos en V8: cierre de sesión a los 600 s, refresh revocado y marca borrada (S9-D23).
- TV: `tv-soak` con 12 h aceleradas y job nuevo `tv-soak-real` en `nightly.yml` (solo `workflow_dispatch`, `real_hours` hasta 5,5): 5 h reales en GitHub, 30 muestras, 0 errores de consola, heap +7 % entre el primer y el último cuarto (tope 20 %) (S9-D24, S9-D38).
- WhatsApp: los avisos traen `can_whatsapp` (vivo, con autorización y con teléfono, sin descifrar); sin él el botón sale deshabilitado con «No se puede abrir WhatsApp» y un enlace a la ficha (S9-D22). El api y el web de v0.6 van juntos: una pestaña abierta con el bundle anterior debe recargarse.

### Sprint 9 · Validación (V1 a V8)
- Gates completos (V9, sobre `e4e1cbc`): api con ruff, formato y mypy limpios y pytest con 12.312 pasan, 103 omitidas y cobertura de 95,83 % (las 18 que cayeron por agotamiento de recursos de Windows, WinError 10055 y 0xC0000142, pasan al repetirlas: 410 de 410); scripts de infraestructura (923 comprobaciones ok) y Caddyfile con 0 fallas; web con lint, tipos, 5.034 pruebas en 278 archivos (cobertura de líneas 97,68 %) y build.
- Stack de producción en Linux (V3, prod-smoke): proveedor local 280 comprobaciones ok y OpenBao 296 ok, 0 fallas; las 18 del módulo `athletes` (llave sin `init-keys`, 409 sin autorización, `reveal`, blobs `apx1.`, `rotate-key athlete.metric`, nada en claro en los logs) y los permisos por columna de `apex_api`, `apex_worker` y `apex_backup`. Rojo por sabotaje (`REVOKE INSERT`) detectado por las dos comprobaciones.
- **Rollback a v0.5.0 probado** (V3, `apex-smoke`): `alembic downgrade 0041_results_session_index` con la imagen v0.6 (0044 → 0041) y, con el árbol y la imagen de v0.5.0, api y worker sanos, `/health` 200 con `crypto ok` y `migrations ok`, login y `reveal` del documento. Las llaves de `athlete.metric` se quedan en `crypto_keys` y v0.5 arranca con ellas. Compose y `dbsetup` deben correr desde el árbol de v0.5.0 (`docs/operacion/actualizar.md`, «Volver de v0.6 a v0.5»). Con medidas reales el camino es restaurar el respaldo pre-deploy.
- Demos 1 a 4 por la interfaz (V4) con conteos en la base; E2E (V5) `stack` 72 pasan y 0 fallan dos veces seguidas (las que se omiten por hora pasan después de medianoche) y `preview` 219 pasan; dos fallas reales corregidas (contraste de «+ Crear» del calendario y una spec de avisos).
- Rendimiento (V6, `perf`, 5.300 resultados, 4.061 récords, 200 mediciones): el handler suma 12,7 a 12,9 ms a la mediana de `PUT /results` (tope 20 ms); corrección de un socio con 2.000 marcas en 96 a 171 ms; `/summary` en 6 ms (tope 300 ms); lecturas por índice sin apagar el planificador (S9-D70).
- verify-delivery (V8): pilar 1, 57 de 60 entregados y los 3 parciales (esperas reales) cerrados en vivo; pilar 2 por la interfaz real: avisos bloqueados, tablet con RM, corrección repetida idempotente (409 `invalid_supersedes`) y anulación, `derive-records` crea 0, `verify-audit` íntegra con 8 de 8 firmas.

### Deuda aceptada con dueño
- Con `--provider openbao`, el api del prod-smoke sigue con proveedor local: el alta y el `reveal` de medidas con OpenBao como proveedor del api no se probaron en el smoke (dueño: Sprint 10, overlay `compose.openbao.yml` en el smoke).
- Contraseñas y tokens de desarrollo impresos en sesiones anteriores: no se rotan por orden del usuario.

## [0.5.0]

Fecha de cierre: 2026-11-15. SHA de cierre: el del commit etiquetado `v0.5.0` (`git rev-parse v0.5.0^{commit}`); es el valor que se pasa a `infra/deploy.sh --expect-sha`. La etiqueta se publica en GitHub junto con `main`; el Release en borrador lo arma la CI (`release.yml`).

Quinta versión desplegable: catálogo de movimientos y benchmarks, WODs con calendario semanal, resultados registrados desde la tablet del coach, leaderboard por nivel y sexo, y una pantalla de TV con token de dispositivo. Cierra la deuda aceptada del Sprint 7.

### Sprint 8 · WODs (EP-22)
- Módulo `wods` (esquema `wods`, migraciones 0032 a 0035): movimientos con nombre normalizado único, benchmarks (`seed-benchmarks` siembra 12, idempotente por nombre normalizado), WODs con lista de movimientos y calendario semanal (`GET /wods?week=`), y el WOD del día.
- Las cargas son gramos enteros (S8-D41); el front las muestra y las pide en kilos.
- Asignación del WOD a una sesión (`PATCH /class-sessions/{id}` con `wod_id`): la sesión de hoy hereda el WOD del día; cambiar el WOD efectivo de una sesión con resultados vigentes da 409 `locked_by_results`.
- Con resultados vigentes quedan bloqueados la unidad de un movimiento, el `score_type` de un benchmark y el principal del WOD.

### Sprint 8 · Resultados y leaderboard (EP-23, EP-24)
- Módulo `results` (esquema `results`, migraciones 0036 a 0041): `PUT /results` registra un resultado de tiempo, rondas y repeticiones, repeticiones o carga, con corte por time cap, y lo corrige con `supersedes_id` (el anterior queda `is_current = false`). La forma de los datos la protegen CHECK y triggers de la base.
- Leaderboard por nivel (Rx y Rx+ juntos, scaled después) y posición de competencia, con filtro Mujeres, Hombres y Todos; resultados del WOD, del socio y pestaña Resultados en la ficha.
- Anulación por admin (`POST /results/{id}/void`, con motivo, migración 0040): sin sucesor y fuera del leaderboard. Con un resultado vigente, quitar la asistencia, cancelar la clase o cancelar las futuras da 409 `locked_by_results` (0039 y revisión final).
- Índice parcial por sesión (0041) y predicados que usan los índices parciales (S8-D50).

### Sprint 8 · Pantalla de TV (EP-25)
- Token de dispositivo en la sección `tv` de `/settings`: se genera, se rota y se revoca; solo se guarda su hash y viaja en el fragmento de la URL (`/tv#token=`), nunca en la consulta ni en los logs (Nginx y el api lo redactan).
- `GET /tv/today` con `X-Device-Token`: nombres cortos («Ana P.»), sin documento, teléfono, correo ni sexo; excluye socios dados de baja o sin autorización de datos. Dos cubetas, `tv-fail` por IP (token inválido) y `tv` por token, con tope también en Nginx.

### Sprint 8 · Quiosco y front
- Migración 0038: el quiosco suma `GET /class-sessions/{id}/attendance` y `PUT /results` (origen `kiosk`; solo clases de hoy o de ayer; 12 rutas permitidas en total).
- Front: Movimientos, Benchmarks, calendario y detalle de WOD (leaderboard, sesiones e historial), registro de resultados en la tablet, tarjeta «WOD de hoy» en Inicio, pestaña TV de Configuración y la pantalla de TV en oscuro.
- Cubetas `wods-write` y `results-write`: 27 cubetas y 26 variables `USER_*`.

### Sprint 8 · Deuda del Sprint 7 cerrada
- Token de dispositivo para la tablet (S8-D24): se cierra sin código; el quiosco con cuenta coach auditada ya da rutas mínimas, ventana de hoy o ayer y salida con contraseña, y un token en la tablet sería peor. Solo la TV lleva token.
- Residual de `finish_rotation` (S8-D26): sigue aceptado; v0.5 no suma escritores cifrados, así que no crece.
- Inicio con sesiones canceladas (S8-D25): las vivas van primero y las canceladas quedan en una línea plegada.

### Sprint 8 · Validación (V1 a V8)
- Gates completos (V1): api 11.006 pasan, 103 omitidas (Windows, solo Linux), cobertura 95,70 %; web 4.537 pruebas en 261 archivos.
- Datos y demos en desarrollo (V2, V4): migraciones hasta la 0041 con ciclo `downgrade`/`upgrade`, 19 guardas con `tgenabled = A`, `dbsetup` con 30 tablas clasificadas; cinco demos por curl, topes de Nginx y token ausente de los logs.
- E2E (V5): `stack` 61 pasan, 2 fallos reales corregidos en V5b (contraste del calendario y WhatsApp sin teléfono); `preview` 219 pasan; 15 resultados en la tablet en 10 s (tope 5 minutos); resistencia de la TV con reloj acelerado de 12 h, heap +3,4 % (tope 20 %).
- Rendimiento (V6, `perf`): leaderboard, resultados del socio y TV entre 4 y 16 ms con 30 WODs y unos 3.300 resultados (tope 300 ms), todos por índice. Hallazgo S8-D50: `is_current IS TRUE` no usaba el índice parcial; corregido en 12 sitios.
- Revisión final (V7, S8-D49): cancelación masiva con resultados, índice 0041, invalidaciones del front y textos.
- verify-delivery en vivo (V8): 51 de 53 puntos entregados y los dos parciales cerrados: «Sesiones con este WOD» paginado en el servidor y con las próximas por defecto (`4c05107`, `85f4cc1`) y el prod-smoke (V3). Una clase completa por la interfaz real: 15 resultados en el quiosco en 9 s, una corrección y la TV al día.
- Stack de producción en Linux (V3, prod-smoke, imágenes de `85f4cc1`): proveedor local 238 comprobaciones ok y OpenBao 257 ok, 0 fallas en ambas.
- La lista de privados de `tests/architecture` (`PRIVATE_HELPERS`) quedó exacta para `classes`, `wods`, `results` y `tv`, con una prueba que la compara con los archivos en disco.

### Deuda aceptada con dueño (Sprint 9 o posterior)
- El cierre por inactividad de 10 minutos del quiosco solo tiene prueba unitaria; no se ejercitó en vivo ni en E2E (dueño Sprint 9).
- La TV se probó con reloj acelerado de 12 h, no con 12 h reales (dueño Sprint 9, job nocturno `tv-soak`).
- `NotificationOut` no trae el teléfono, así que «Abrir WhatsApp» se ofrece también a un socio sin teléfono y el 422 `member_without_phone` se explica en pantalla (dueño Sprint 9).
- Contraseña de desarrollo de un coach impresa una vez en la salida de V4: la cuenta está dada de baja y no se rota por orden del usuario.

## [0.4.0]

Fecha de cierre: 2026-11-15. SHA de cierre: el del commit etiquetado `v0.4.0` (`git rev-parse v0.4.0^{commit}`); es el valor que se pasa a `infra/deploy.sh --expect-sha`. La etiqueta es local: el push, el PR, el merge y el Release los hace una persona.

Cuarta versión desplegable: clases con horario semanal, sesiones generadas cada día, check-in desde la tablet del coach, tiqueteras que descuentan y devuelven clases, reportes de asistencia y tablero con las clases de hoy. Cierra la deuda aceptada del Sprint 6.

### Sprint 7 · Clases, horario y check-in (EP-21)
- Módulo `classes` (esquema `classes`, migraciones 0026 a 0028): franjas semanales, sesiones (el job `generate_sessions` las crea a las 07:00 para los próximos 14 días y es idempotente; cancelar una sesión o las futuras de una franja) y asistencia con guardas append-only (`tgenabled = A`); secciones `hours` y `classes` de `/settings/{section}`.
- Check-in (US-159): siete banderas informativas (vencido, sin membresía, congelada, pendiente de pago, sobre cupo, fuera de ventana, otro día) que nunca bloquean; quitar una asistencia con motivo (`DELETE /attendance/{id}`), todo auditado.
- Tiqueteras (US-160, migraciones 0029 y 0030): el check-in descuenta una clase de la tiquetera vigente, quitar la devuelve, y agotar una recorta `end_date` guardando `original_end_date`; la membresía futura no descuenta (S7-D25).
- Reportes (US-161, US-163): `GET /attendance/summary` por semana y franja, asistencia por socio, filtro `last_attendance` en `GET /members` y `attendance_week` más `sessions_today` en el tablero.
- Front: Horario, Sesiones, Asistencia, Hoy y pantalla de check-in en modo tablet (sin enlaces ni `reveal`), pestaña Asistencia en la ficha del socio y tarjetas de clases en Inicio.

### Sprint 7 · Modo quiosco del servidor (S7-D41, S7-D42)
- Migración 0031: la sesión de refresh guarda la ruta de check-in de la tablet (`kiosk_path`); `POST /auth/kiosk` y `exit_kiosk` con contraseña; con la marca, el access solo alcanza lo necesario del check-in y `GET /members?q=` busca solo por nombre. Cambiar de clase dentro del quiosco solo acepta sesiones de hoy o de ayer.

### Sprint 7 · Deuda del Sprint 6 cerrada
- Migración 0025: FK `attachments.key_id → crypto_keys`, guarda de jobs solo para `rotate`, `public_key` inmutable también para el propietario y `CHECK` bidireccional de `public_key` (S6-D81, S6-D130, S6-D133).
- Layout del volumen `keys` con `custody/`, `sign/` y `jwt/`: el api monta solo `custody/` y `jwt/`, y ya no ve la llave privada de firma local (S7-D23; `init-keys --migrate-layout`).

### Sprint 7 · Validación (V1 a V9)
- Gates completos (V1): api 10.375 pasan, 103 omitidas (Windows, solo Linux), cobertura 95,39 %; web 4.261 pasan, 98,19 % de líneas con 2 hilos.
- Stack de producción en Linux (V3, `prod-smoke`): 233 y 252 comprobaciones ok. E2E `stack`: 52 pasan, 0 fallan, 3 omitidas, dos veces seguidas; `preview`: 219.
- Demos 1 y 2 en desarrollo (V4, job idempotente), verify-delivery en vivo con la interfaz real (V8): 57 de 58 requisitos con evidencia; el parcial (imagen `apex-api:local` sin el SHA del árbol) se cerró en V9.
- Rendimiento (V6, `perf`): check-in entre 15 y 121 ms con 1.000 socios y 15 asistentes (límite 2 s), filtro `last_attendance=30d` 19 ms, tablero 18 ms con 20.000 asistencias, resumen de 26 semanas bajo 500 ms; `EXPLAIN (ANALYZE, BUFFERS)` de las tres consultas en `docs/scratch/sprint-07.md` (todas por índice, menos de 6 ms).
- Defecto hallado por el E2E de V5: la ruta `/clases/:id/checkin` no montaba la pantalla del check-in (corregido en `d1fa18b`).

### Deuda aceptada con dueño (v0.5, Sprint 8)
- Token de dispositivo para la tablet: hoy el modo quiosco es una sesión de una cuenta coach (S7-D24); la inactividad de 10 minutos solo tiene prueba unitaria.
- Residual de `finish_rotation` con una subida de adjunto a medio confirmar en una llave `decrypt_only` (S7-D36): no pierde datos, `attachments-check` lo detecta.
- Inicio lista todas las sesiones canceladas del día; con un horario real no se nota.

## [0.3.0]

Fecha de cierre: 2026-11-14. SHA de cierre: el del commit etiquetado `v0.3.0` (`git rev-parse v0.3.0^{commit}`); es el valor que se pasa a `infra/deploy.sh --expect-sha`. La etiqueta es local: el push, el PR, el merge y el Release los hace una persona (después de fusionar el Sprint 5).

Tercera versión desplegable: cadena de auditoría firmada cada noche, pantalla Llaves con rotación desde el panel y CBOM, foto y autorización de datos del socio como adjuntos cifrados, y TLS 1.3 híbrido post-cuántico con Caddy. Cierra el riesgo aceptado P7 (sin TLS) para quien configure un dominio.

### Sprint 6 · Auditoría firmada (EP-17)
- Firma Ed25519 de la cadena de auditoría por el worker a las 07:00 (`audit.signatures`, append-only, migraciones 0021 y 0022), con verificación incremental antes de firmar (H-1) y anti-retroceso; el api solo verifica, con la clave pública guardada en `crypto_keys` (funciona con el custodio sellado, S6-D81).
- `sign-audit` y `--run-once sign_audit`; alerta `audit_sign_late` por firma atrasada; `rotate-key audit.signature --provider local|openbao` cambia de proveedor creando una llave nueva.
- ADR-006 precisado (S6-D142): `--provider local` solo con `CRYPTO_PROVIDER=local` y residual del volumen `keys` en el api declarado.
- Front: estado de la firma en Auditoría («Íntegra», «Alterada», «Firma atrasada», «Sin firmas») y verificación con firmas.

### Sprint 6 · Administración de llaves (EP-18)
- Inventario de llaves sin material, bitácora `crypto_ops`, trabajos con progreso y exportación del CBOM (sin material ni referencias de llaves `sign`).
- Rotación desde la pantalla (`POST /crypto/keys/{id}/rotate`, confirmación `ROTAR` exacta) con migración 0024: guarda de `crypto_keys` en dos triggers (H-2), `guard_jobs_*`, grants por columna para `apex_api`, un rotador en vuelo con conexión dedicada, reanudación tras reinicio; `retire-key` exige un manifiesto firmado posterior a la rotación.
- Front: pantalla Llaves con Inventario, Bitácora, Trabajos, modal de rotación y botón «Exportar CBOM».

### Sprint 6 · Adjuntos y autorización de datos (EP-19)
- Módulo `attachments` (migración 0023): subida como cuerpo crudo con tope exacto de 5 MiB y bytes mágicos, almacenamiento local (S3 opcional y apagado), adjuntos sensibles cifrados con `attachment.sensitive`, descarga auditada solo por el api con `no-store`, `nosniff` y CSP `sandbox`; la foto se sirve por streaming sin fila de auditoría (ADR-007).
- Autorización de datos con versión de la política copiada al registrar; filtro `consent=missing` compartido con el KPI y la exportación; `attachments-check` (huérfanos y `key_id` distinto del blob).
- Front: foto en la ficha y la lista, pestaña Adjuntos, foto y autorización en el alta y la edición, tarjeta «Sin autorización» con enlace al filtro.

### Sprint 6 · Validación (V1 a V12)
- Demos 1 a 4 en el ensayo de producción con OpenBao desellado, E2E `stack` dos veces (53 pasan, 0 fallan) y `preview` (219), pruebas `perf` del sprint (S6-D134).
- Correcciones que destapó el ensayo (S6-D136): el proveedor `local` se resuelve por fila también con `CRYPTO_PROVIDER=openbao` (`lazy_kek`); `rotate-key audit.signature --provider local` se rechaza con OpenBao (el worker no monta `keys`); tras `retire-local-kek`, `retire-key`, `rotate-kek` y `migrate-provider` aceptan como prueba de custodia el manifiesto firmado con la instantánea de OpenBao verificada (antes exigían un `verify-kek-backup` imposible).

### Sprint 6 · TLS híbrido (EP-20)
- Caddy 2.11.3 bajo el perfil `tls`: TLS 1.3 con `x25519mlkem768`, redirección 308, HSTS escalonado solo con dominio, `admin off`; Nginx restaura la IP real solo desde Caddy.
- `public_origin`/`validate_origins`: CORS, `AUTH_ALLOWED_ORIGINS` y cookie `Secure` coherentes con `APEX_DOMAIN`; el api no arranca con una configuración incoherente y nombra la variable.
- `tls-smoke.sh` (dominio y LAN) con login real, cookie, CORS y CSP; `prod-smoke.sh --tls` en la CI.

### Deuda aceptada con dueño (v0.4, Sprint 7)
- Migración `0025`: FK `attachments.key_id → crypto_keys`, `guard_jobs_update` solo sobre jobs `rotate`, `public_key` inmutable también para el propietario (S6-D81 punto 2), `CHECK` bidireccional de `public_key` y foto nunca sensible (S6-D130, D133).
- Montar en el api solo `custody/kek.bin` y `jwt/` (hoy ve la llave privada de firma local en solo lectura; la barrera es el grant).
- Brechas de contrato del front: `uploaded_by_name`, versión de la política legible para el coach, plazo de rotación para «Rotación vencida» (BRECHAS §14.10, 14.12, 14.15).
- Demo en vivo de la ida y vuelta de la llave de firma entre proveedores (local → openbao → local): hoy solo por pruebas con `FakeTransit` y `openbao-smoke` (S6-D139).

## [0.2.0]

Fecha de cierre: 2026-11-05. SHA de cierre: el del commit etiquetado `v0.2.0` (`git rev-parse v0.2.0^{commit}`), publicado en el Release en borrador; es el valor que se pasa a `infra/deploy.sh --expect-sha`.

Segunda versión desplegable: custodia de llaves en OpenBao, avisos de vencimiento por correo y WhatsApp, cuentas por correo, recibo PDF y exportaciones CSV. El TLS sigue pendiente (riesgo aceptado P7).

### Sprint 5 · Custodia de llaves con OpenBao (EP-15)
- OpenBao (motor Transit, una llave `apex-kek`) como custodio de las DEK: `migrate-provider` reanudable, `rotate-kek` con `--trim` (unwrap + wrap, S5-D55a) y `retire-local-kek`, todos con pruebas de custodia (manifiesto firmado reciente con instantánea, S5-D72).
- Estado sellado: arranque degradado, `/health.crypto` crítico, 503 `crypto_unavailable` con `Retry-After: 30`, sondeo de recuperación cada 20 s; el worker arranca con el keyring mínimo.
- Instantánea raft de OpenBao en cada respaldo y `restore.sh --with-openbao`; `openbao-smoke.sh` y `openbao_restore_e2e.sh` en la CI y el smoke de producción.
- Roles de base de datos: `apex_owner` como propietario, `MIGRATE_DB_USER`/`TOOLS_DB_USER`, permisos por columna para `apex_api` y `apex_worker` (S5-D202 a D204, D256).

### Sprint 5 · Avisos de vencimiento (EP-14)
- Plantillas y reglas de aviso (`notification_templates`, `notification_rules`, `seed-notifications` idempotente), avisos del día generados por el job `notify` con candado por lote, envío por correo (SMTP con STARTTLS, al menos una vez, tope de 3 intentos) solo con consentimiento y opt-in del socio, enlace de WhatsApp por `POST /notifications/{id}/wa-link` auditado, omisión con motivo e historial por socio.
- Preferencias de canal por socio (`member_channel_preferences`) con consentimiento obligatorio; resumen diario del equipo por Telegram sin datos personales; KPI `notifications_today` y `members_without_consent` en el tablero.
- Correos de cuenta: activación y recuperación por SMTP (`email_sent` en el alta y el reenvío), `forgot` sin canal de tiempos (trabajo en segundo plano acotado, S5-D38, D91).
- Front: por avisar hoy, reglas y plantillas, historial, pestaña Canales de Config, pestaña Avisos de la ficha, KPI de Inicio, recuperar y activar cuenta por correo, aviso global de custodio no disponible.

### Sprint 5 · Recibos y exportaciones (EP-16)
- Recibo PDF propio (`core/pdf.py`, Courier sin incrustar, sin datos cifrados, auditado como `download`).
- Exportaciones CSV de socios y pagos en streaming (BOM, `;`, escape de fórmulas), un flujo por usuario (409), tope configurable, auditoría de apertura y cierre, `crypto_ops` por lote con `purpose=export`, cubetas `export*`; front con confirmación y descarga por `api.blob`.
- Migraciones 0015 a 0020 (proveedor de llaves, preferencias de canal, plantillas, reglas, avisos, índices).

### Deuda aceptada con dueño (v0.3)
- Índice `memberships(end_date)` y CHECK `sent ⇒ sent_at` en avisos; SMTP implícito (465); subruta del volumen `keys` para la llave JWT del worker; ADR-005 punto 2 (`rewrap`) por corregir.

## [0.1.0]

Fecha de cierre: 2026-11-04. SHA de cierre: el del commit etiquetado `v0.1.0` (`git rev-parse v0.1.0^{commit}`), publicado en el Release en borrador; es el valor que se pasa a `infra/deploy.sh --expect-sha` (ver `docs/operacion/actualizar.md`).

Primera versión desplegable: administración de un gimnasio de CrossFit (socios, planes,
membresías, pagos y vencimientos) con datos personales cifrados, auditoría verificable y
continuidad operativa. Despliegue de LAN sin TLS (riesgo aceptado P7); el TLS llega en v0.2.

### Sprint 0 · Terreno, gates y esqueleto ejecutable
- Repositorio, estructura de módulos, CI (lint, tipos, pruebas, licencias, imágenes) y los scripts de
  gate del flujo por slice.
- Stack de Compose con `db`, `api` y `web` (Nginx), `/health` y PostgreSQL 16 de prueba.

### Sprint 1 · Núcleo de auditoría, bus de criptografía y seguridad de plataforma
- Bitácora de auditoría con cadena de hashes y tablas inmutables.
- Bus de criptografía (`core/crypto`): AES-256-GCM por clase de dato, índices ciegos, llaves
  envueltas por una KEK local, `init-keys`.
- Argon2id, JWT Ed25519, roles, límites de intentos, cabeceras de seguridad.

### Sprint 2 · Identidad, configuración, socios y planes
- Login con refresh por cookie, usuarios del equipo con activación y recuperación por enlace.
- Configuración del gimnasio, alta y búsqueda de socios con los datos personales cifrados, planes.
- Shell del front (React 19) con las pantallas de acceso, usuarios, configuración, socios y planes.

### Sprint 3 · Núcleo comercial: membresías, pagos y ficha del socio
- Membresías (alta, renovación, congelamiento, cancelación) y pagos inmutables (anulación por
  `voided`, nunca borrado).
- Ficha del socio con revelado auditado de datos sensibles, límites por usuario, 503 `busy`.

### Sprint 4A · Worker, auditoría verificable, tablero y planes restantes
- Worker con APScheduler y `worker.job_runs`; vencimientos diarios.
- Verificación de la cadena de auditoría (`POST /audit/verify`, `verify-audit`), consulta de
  auditoría, tablero de inicio y `recompute-memberships`.

### Sprint 4B · Continuidad operativa y release
- Respaldo cifrado con `age` y manifiesto firmado con `minisign` (servicio `backup`), retención,
  subida opcional con `rclone copyto`; `backup_check` del worker y `backup` en `/health`.
- Respaldo de la KEK (`export-kek`, `verify-kek-backup`, `restore-kek`) y `restore.sh` con firma e
  inspección del tar.
- Rotación de llave reanudable (`rotate-key`) y `retire-key` con conteo confirmado.
- Datos de demostración (`seed --demo`) e importación de socios (`import-members`).
- Roles de base separados (`apex_api`, `apex_worker`, `apex_backup`), servicios `migrate` y
  `dbsetup`, entorno repartido en `.env` y `.env.ops`.
- `/health` con `migrations` (`ok|mismatch|unknown`).
- `infra/deploy.sh --ref vX.Y.Z --expect-sha <sha>` con respaldo previo, etiquetas `prev-*` y
  `rollback-*.txt`; `scripts/ci/prod-smoke.sh`, `release.yml`, ADR 001 a 004, guías de operación.
- Deuda del front de los sprints anteriores (F1).

### Fuera de esta versión
- TLS y Caddy (v0.2), firma de etiquetas con `.github/allowed_signers` (v0.2), OpenBao como KMS
  (v0.2), notificaciones al socio (v0.2), clases, WODs y portal (v0.4 en adelante).
