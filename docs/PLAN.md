# APEX — plan de implementación para Claude Code (backend e infraestructura)

Orden de trabajo. Cada tarea termina con su criterio de salida cumplido y sus pruebas en verde antes de pasar a la siguiente. El front no se construye aquí; solo se deja el contrato de la API documentado en `/docs` (OpenAPI) y el lugar en Nginx para servir `web/dist`.

Lee primero `CLAUDE.md`. Lo que diga ahí manda sobre cualquier cosa de este plan.

---

## Versión 0.1 — Base: socios, planes, membresías, pagos, cifrado

### Tarea 0 — Arranque del repositorio
1. Crear la estructura de carpetas de `CLAUDE.md`.
2. `api/pyproject.toml` con `uv`: dependencias de runtime y de desarrollo separadas. Configurar `ruff` (lint, formato, `flake8-tidy-imports` con la lista de importaciones prohibidas), `mypy --strict`, `pytest` con `asyncio_mode=auto`.
3. `.pre-commit-config.yaml` con ruff y mypy.
4. `.github/workflows/ci.yml`: lint, mypy, pruebas con servicio PostgreSQL, `pip-licenses --fail-on` con la lista prohibida, build de imágenes.
5. `.env.example` con todas las variables: `DATABASE_URL`, `JWT_PRIVATE_KEY_PATH`, `CRYPTO_PROVIDER=local`, `CRYPTO_LOCAL_KEK_PATH`, `TZ_DISPLAY=America/Bogota`, `UPLOADS_DIR=/data/uploads`, `CORS_ORIGINS`.
6. `README.md`: levantar el proyecto en 5 minutos.
Criterio de salida: `uv run ruff check .`, `uv run mypy src` y `uv run pytest` corren en verde con una prueba trivial.

### Tarea 1 — `core/`
1. `config.py`: `Settings` con pydantic-settings.
2. `db.py`: engine async, `async_session`, `Base` con mixin de columnas comunes (`id` UUID, `created_at`, `updated_at`, `created_by`, `deleted_at` opcional).
3. `security.py`: hash y verificación argon2id; JWT Ed25519 (`create_access_token`, `create_refresh_token`, `decode`); dependencias `current_user` y `require_role("admin")`.
4. `events.py`: bus en memoria con `subscribe(event_type, handler)` y `emit(event)`; los handlers corren en la misma transacción.
5. `audit.py`: función `record(action, table, record_id, before, after, user_id)` que escribe en `audit.audit_log` con `prev_hash` y `hash` (SHA-256 de la fila anterior más la actual). Evento de SQLAlchemy `after_flush` que la invoca para las tablas marcadas con `__audited__ = True`.
Criterio de salida: pruebas de hash de contraseñas, de emisión y verificación de JWT, de encadenamiento de hashes de auditoría.

### Tarea 2 — `core/crypto/` (el bus)
1. `provider.py`: interfaz `KeyProvider` (`wrap`, `unwrap`, `sign`, `verify`, `rotate`, `key_info`).
2. `local_provider.py`: `LocalFileProvider`. KEK de 32 bytes en el archivo de `CRYPTO_LOCAL_KEK_PATH`; si no existe, comando `cli init-keys` la crea con permisos 600. Envuelve DEK con AES-256-GCM. Firma con Ed25519 (llave en archivo aparte).
3. `models.py`: tablas `crypto.crypto_keys` (id, purpose, data_class, algorithm, provider, version, state: active | decrypt_only | retired, wrapped_material, created_at, rotated_at, rotate_by) y `crypto.crypto_ops` (inmutable).
4. `bus.py`: `CryptoBus` con `encrypt`, `decrypt`, `blind_index`, `sign`, `verify`. Carga las DEK activas al arrancar y las mantiene en memoria. Blob `apx1.<key_id>.<alg>.<nonce>.<ct>`. Registra cada operación en `crypto_ops` (operaciones masivas por lote).
5. `types.py`: tipo de columna SQLAlchemy `Encrypted(data_class)` que cifra al guardar y descifra al leer usando el id del registro como AAD, y `BlindIndexed(data_class)` que mantiene la columna `_idx`.
6. `cli rotate-key <data_class>`: crea DEK nueva, pone la anterior en `decrypt_only`, recifra por lotes de 500 en segundo plano, retira la anterior al terminar.
Criterio de salida: pruebas de ida y vuelta de cifrado, de AAD (un blob movido a otro registro no descifra), de índice ciego (mismo valor con distinta forma da el mismo índice), de rotación con datos viejos legibles, y una prueba que falle si un módulo importa `cryptography` directamente.

### Tarea 3 — Módulo `auth`
1. Tabla `auth.users` (email, password_hash, role, is_active) y `auth.refresh_tokens` (hash, user_id, expires_at, revoked_at).
2. Endpoints: `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`. CRUD de usuarios solo para `admin`: `GET/POST /api/v1/users`, `GET/PATCH/DELETE /api/v1/users/{id}`.
3. Rate limit en login (5 intentos por minuto por IP).
4. `cli seed`: crea el usuario admin inicial con contraseña tomada de una variable de entorno de un solo uso.
Criterio de salida: pruebas de login correcto e incorrecto, refresh, revocación, acceso denegado por rol.

### Tarea 4 — Módulo `members`
1. Tabla `members.members`: first_name, last_name, document (cifrado + índice), phone (cifrado + índice), email (cifrado + índice), birth_date (cifrado), emergency_contact (cifrado, JSON con nombre y teléfono), status: active | inactive, notes, deleted_at. `__audited__ = True`.
2. Endpoints: `GET /api/v1/members` (búsqueda por nombre, documento o teléfono usando índices ciegos; filtro por estado; paginado), `POST`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}` (lógico).
3. Evento `MemberCreated`.
Criterio de salida: prueba de búsqueda por documento sin descifrar la tabla; prueba de que en la base el documento no aparece en claro.

### Tarea 5 — Módulo `plans`
1. Tabla `plans.plans`: name, price_cop, kind: days | classes, duration_days, class_count, is_active, deleted_at. `__audited__ = True`.
2. CRUD completo bajo `/api/v1/plans`, solo `admin`.
Criterio de salida: no se puede borrar un plan con membresías activas; se desactiva.

### Tarea 6 — Módulo `memberships`
1. Tabla `memberships.memberships`: member_id, plan_id, agreed_price_cop (copia del precio del plan), start_date, end_date, classes_remaining, status: active | expiring | expired | frozen | cancelled, frozen_from, frozen_to, cancel_reason. `__audited__ = True`.
2. Reglas en `service.py` como funciones puras probables sin base de datos: `compute_end_date(start, plan)`, `compute_status(membership, today)`, `freeze(membership, from, to)` extiende `end_date` por los días congelados.
3. Endpoints: `GET /api/v1/memberships` (filtros: estado, vence antes de, socio), `POST /api/v1/members/{id}/memberships` (vender), `POST /{id}/renew`, `POST /{id}/freeze`, `POST /{id}/cancel`, `GET /{id}`.
4. Vista de resumen: `GET /api/v1/memberships/summary` devuelve conteos de al día, vencen en 7 días, vencidos.
5. Evento `MembershipActivated`, `MembershipExpired`.
Criterio de salida: pruebas de cálculo de fecha de fin para plan por días y por clases, de cambio de estado al cruzar la fecha, de congelación.

### Tarea 7 — Módulo `payments`
1. Tabla `payments.payments`: membership_id, amount_cop, method: cash | nequi | breb, reference, paid_at, registered_by, voided, void_reason, voided_by, voided_at. `__audited__ = True`. Sin `UPDATE` ni `DELETE`: trigger de PostgreSQL que los rechaza, además de la regla en código.
2. Endpoints: `POST /api/v1/memberships/{id}/payments`, `POST /api/v1/payments/{id}/void`, `GET /api/v1/payments` (filtros: fecha, medio, socio), `GET /api/v1/members/{id}/payments`.
3. Evento `PaymentRegistered`: el módulo `memberships` se suscribe y activa la membresía cuando la suma de pagos no anulados cubre `agreed_price_cop`.
4. Reporte: `GET /api/v1/payments/report?month=` ingresos por medio de pago.
Criterio de salida: prueba de que un `UPDATE` directo falla; prueba de anulación y pago nuevo; prueba de activación por evento.

### Tarea 8 — Módulo `audit`
1. Endpoint `GET /api/v1/audit` (filtros: tabla, registro, usuario, rango de fechas), solo `admin`.
2. `cli verify-audit`: recorre la cadena de hashes y reporta si está íntegra.
Criterio de salida: prueba de detección de una fila alterada a mano.

### Tarea 9 — Migraciones y datos de prueba
1. Alembic configurado con un esquema por módulo (`auth`, `members`, `plans`, `memberships`, `payments`, `audit`, `crypto`). Migración inicial generada y revisada a mano.
2. `cli seed --demo`: 3 planes, 30 socios con datos ficticios, membresías en los tres estados, pagos.
3. `cli import-members archivo.xlsx`: importación idempotente por documento, con reporte de filas rechazadas.
Criterio de salida: base limpia + `alembic upgrade head` + `seed --demo` deja el sistema usable.

### Tarea 10 — Docker e infraestructura
1. `api/Dockerfile` multi-stage (builder con uv, runtime sin herramientas de compilación, usuario no root).
2. `infra/compose.yml`: servicios `web` (Nginx; sirve `web/dist` y hace proxy de `/api` a `api:8000`), `api`, `worker` (misma imagen, comando distinto; por ahora solo el job de vencimientos), `db` (PostgreSQL 16, volumen), `backup` (pg_dump nocturno cifrado con `age`, subida con `rclone`). Healthchecks; `api` corre `alembic upgrade head` antes de aceptar tráfico; `web` y `worker` dependen de `api` sano. Volúmenes: `pgdata`, `uploads`, `backups`.
3. `infra/compose.dev.yml`: hot reload, puertos abiertos, base de pruebas.
4. `infra/nginx/default.conf`: raíz en `/usr/share/nginx/html`, `location /api/` → api, cabeceras de seguridad, tamaño máximo de subida 5 MB.
5. Script `infra/deploy.sh`: pg_dump previo, pull, up, verificación de `/health`.
Criterio de salida: `docker compose up` desde cero deja `/health` en verde y el seed cargado.

### Tarea 11 — Worker (mínimo de v0.1)
1. `worker/main.py` con APScheduler; job diario 7:00 am America/Bogota.
2. `jobs/expirations.py`: recalcula estados de membresías y emite `MembershipExpired`.
Criterio de salida: prueba del job con fechas simuladas.

### Tarea 12 — Documentación
1. `docs/adr/ADR-001-monolito-modular.md`, `ADR-002-bus-de-criptografia.md`, `ADR-003-pagos-inmutables.md`.
2. OpenAPI exportado a `docs/openapi.json` para el equipo del front.
Criterio de salida: el equipo del front puede generar su cliente desde `openapi.json`.

---

## Versión 0.2 — OpenBao y avisos

1. `infra/openbao/config.hcl`, servicio `openbao` en Compose, desellado con llaves fuera del servidor, motor Transit habilitado con una llave por `data_class` y una de firma.
2. `OpenBaoProvider` implementando `KeyProvider` con la API de Transit. `cli migrate-provider local→openbao`: re-envuelve las DEK, no recifra datos.
3. Módulo `notifications`: tablas `rules`, `templates`, `notifications`; interfaz `NotificationChannel` con `WebPushChannel` (pywebpush), `EmailChannel` (SMTP/Brevo), `TelegramChannel` (httpx), `WhatsAppLinkChannel` (genera `wa.me` con mensaje). Endpoints de CRUD de reglas y plantillas, historial, y `GET /api/v1/notifications/today` para la pantalla "por avisar hoy".
4. Job `notify.py`: 3 días antes, el día, 1, 7 y 15 días después; respeta canales activos del socio; registra cada intento.
5. Tabla `members.push_subscriptions` y endpoints para registrar la suscripción del navegador.

## Versión 0.3 — Auditoría firmada y TLS híbrido

1. Job `sign_audit.py`: firma nocturna del último hash de la cadena con ML-DSA desde OpenBao Transit (OpenBao 2.7+). Tabla `audit.signatures`.
2. Caddy delante de Nginx con TLS automático y grupo de intercambio `X25519MLKEM768`.
3. Adjuntos: módulo `attachments` con `StorageProvider` (`LocalDisk`, `S3Compatible`), endpoints de subida y descarga con auditoría, cifrado de los sensibles vía bus.

## Versión 0.4 — Clases y asistencia

1. Módulo `classes`: `schedule_templates` (horario semanal configurable), `class_sessions` (generadas desde el horario, cupo configurable, coach), `attendance` (único por sesión y socio). Check-in valida membresía activa y devuelve advertencia si está vencida.
2. Reportes de asistencia por socio y por semana.

## Versión 0.5 — WODs y resultados

1. Módulo `wods`: `movements` (catálogo), `wods`, `wod_movements` (copia de reps y cargas RX), `is_benchmark`.
2. Módulo `results`: `wod_results` con puntaje en campos separados (`seconds`, `rounds`, `reps`, `load_kg`), `level`: rx | rx_plus | scaled, `scaled_notes`, único por WOD y socio. Leaderboard del día por nivel y sexo. Endpoint público de solo lectura para la pantalla de TV, protegido por token de dispositivo.

## Versión 0.6 — Atleta

1. Módulo `athletes`: `body_metrics` (cifradas), `personal_records` (manuales y derivados: evento `WodResultRecorded` crea PR cuando `load_kg` supera el anterior para ese movimiento), comparación de benchmarks.

## Versión 1.0 — Portal del socio y cierre

1. Endpoints del portal: mi plan, mis pagos, mis WODs, mis récords, mis datos, mis avisos; el socio solo ve lo suyo (regla en `require_role("member")` + filtro por `member_id` del token).
2. Resultado auto-registrado por el socio con estado `pending` hasta validación del coach.
3. Firma de backups con ML-DSA; informe CBOM exportado desde `crypto_keys` (`cli cbom --format cyclonedx`).
4. Envoltura de llaves con ML-KEM cuando OpenBao Transit lo implemente; si no, `liboqs-python` detrás del mismo `KeyProvider`.
