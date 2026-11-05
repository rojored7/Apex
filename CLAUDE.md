# APEX — reglas del repositorio

APEX es un sistema web para administrar un gimnasio de CrossFit en Colombia: socios, planes, membresías, pagos, vencimientos, avisos, clases, WODs, resultados y perfil del atleta. Repositorio privado. El plan de trabajo aprobado está en `docs/ddd/` (dominio, arquitectura, épicas, historias, desglose técnico, sprints y `DECISIONES.md`); `docs/PLAN.md` es la referencia original del backend. Este archivo resume lo que no se negocia. Si contradice al plan aprobado en el gate, manda el plan y este archivo se corrige en el mismo cambio.

## Alcance de Claude Code en este repo

- Construye y mantiene el backend (`api/`), el worker, la infraestructura (`infra/`), las migraciones y los scripts de gate (`scripts/`).
- Construye y mantiene también el front en `web/`, dentro de este mismo flujo (decisión D1 del gate), con `docs/design/` como fuente de verdad y en el orden de versiones del backend. El contrato entre los dos es `docs/openapi.json`.
- Antes de cualquier decisión irreversible (borrar datos, cambiar el formato del blob cifrado, cambiar una migración aplicada) se detiene y pregunta.

## Stack fijo

- Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, pydantic-settings, Uvicorn, APScheduler, httpx, argon2-cffi, PyJWT, `cryptography`, liboqs-python.
- PostgreSQL 16. Un solo servidor, un esquema por módulo.
- Docker Engine en Linux, Docker Compose. Nginx para servir el front y hacer proxy. Caddy opcional para TLS automático.
- OpenBao (motor Transit) como KMS desde la v0.2. En v0.1 el proveedor de llaves es local.
- Front: React 19 + TypeScript + Vite, React Router, TanStack Query, React Hook Form + Zod, Vitest y Playwright; build estático servido por Nginx.
- Herramientas: `uv`, `ruff`, `mypy`, `pytest`, `pre-commit`, GitHub Actions.

## Estructura del repositorio

```
apex/
  api/
    pyproject.toml
    src/app/
      main.py            # crea la app, registra routers, corre migraciones al arrancar
      cli.py             # app Typer, callback y registro: seed, init-keys, export-openapi, issue-reset-link, unlock-user, verify-audit y recompute-memberships; `seed --demo` (S4B-D32) y reexporta cli_base (S4B-D28); `import-members` vive en `cli_ops/` (B1); `rotate-key` y `retire-key` viven en `cli_ops/` (B3b); `migrate-provider`, `rotate-kek` (con `--trim`, S5-D184) y `retire-local-kek` viven en `cli_ops/` (S5-B2); `seed-notifications` (S5-B6, `cli_ops/seed_notifications.py`; `seed` la invoca también dentro de su transacción) y `notify` (B8) llegan en el Sprint 5 (S5-D97: un archivo cada uno en `cli_ops/`); sign-audit llega en v0.3 (EP-17)
      cli_base.py        # base común del CLI (S4B-B0): unit_of_work, resolve_actor, resolve_admin_actor, cli_runtime, crypto_runtime, production_guard_error, get_settings; único archivo de la capa que arranca el cifrado de columnas (install_crypto_type_listeners)
      cli_manifest.py    # verificación del manifiesto firmado de respaldo (S5-D72, B13): recent_signed_manifest, custody_proofs, confirmation_error (S5-D186) y custody_errors/exit_after_failure (S5-D189); lo usan retire-key, migrate-provider, rotate-kek y retire-local-kek; capa de aplicación como cli_keyring.py
      cli_keyring.py     # carga del keyring de crypto_runtime (confirma solo si creó llaves; `persist=False` para --dry-run); la usa solo cli_base
      cli_session.py     # read_only_session: sesión de solo lectura con rollback explícito (la usan seed/ e imports/)
      cli_ops/           # un archivo por familia de comandos, solo los importa cli.py (S4B-D76): accounts, keys, kek (export-kek, verify-kek-backup y restore-kek, B3a), openapi, recompute, seed_demo, import_members, verify_audit, rotate_key y retire_key (B3b, S4B-D140), migrate_provider, rotate_kek (con --trim) y retire_local_kek (S5-B2, S5-D184), seed_notifications (S5-B6) y notify (S5-B7/B8: `--generate-only` sin reclamo; lo demás por `run_job`, S5-D226); register_ops(app); nunca se importan entre sí ni importan cli
      seed/              # `seed --demo` (S4B-D32): dataset.py puro (3 planes, 30 socios ficticios) y apply.py (dos transacciones por socio, lock_member primero; única llamada a enforce_retroactive_limit=False fuera de cli.py, S4B-D33); solo lo importa cli_ops/seed_demo.py
      imports/           # `import-members` (S4B-D34): members_xlsx.py (fachada y lector openpyxl), limits.py, parse.py, persist.py, report.py, results.py; único sitio de openpyxl y defusedxml; solo lo importa cli_ops/import_members.py
      core/
        config.py        # Settings con pydantic-settings, todo desde .env
        db.py            # engine async, sesión, Base, CommonColumnsMixin
        clock.py         # Clock, SystemClock, FrozenClock, today_bogota()
        context.py       # SYSTEM_USER_ID, actor y lote actuales (contextvars), request_id
        security.py      # argon2, JWT Ed25519, Principal, PrincipalLoader, dependencias de rol
        errors.py        # envelope de error y handlers
        pagination.py    # PageParams, Page y SearchQuery (contrato común de listas)
        validators.py    # tipos de entrada compartidos (EmailAddress) y check_instant_range (rangos de instantes, S4A-D66)
        search.py        # búsqueda común de las listas: limpieza de q, sin tildes, escape de LIKE
        http.py          # ayudas HTTP comunes a los routers (por ejemplo Cache-Control: no-store)
        ratelimit.py     # límite de intentos en memoria: por IP (rate_limit) y por clave (enforce)
        locks.py         # candados de fila y de aviso (lock_member); única puerta del orden de candados (Sprint 3)
        health.py        # /health: HealthOut (db, version, backup, migrations, crypto), checks registrados solo desde main.py con caché TTL (crypto 5 s; S5-B3)
        logging.py       # JSON a stdout con redacción
        audit.py         # escritura en AuditLog + cadena de hashes (usa core/crypto/digest.py)
        audit_verify.py  # audit.verifications, candado y recorrido por lotes de la cadena (Sprint 4A, S4A-D12)
        events.py        # bus de eventos interno (en memoria)
        jobs.py          # worker.job_runs: claim_run, finish_run, last_run (Sprint 4A); lo importan app/worker/ y, solo para leer `last_run`, core/backup_status.py (S4B-D26, S4B-D71); también `last_results`
        backup_status.py # backup_health() (S4B-B2): última corrida de backup_check -> ok|attention|unknown para /health; solo lee (único importador de core.jobs fuera de worker/, y solo last_run)
        migrations_status.py # migrations_health() (S4B-B4, S4B-D170): compara la única fila de public.alembic_version con el head del código -> ok|mismatch|unknown para /health; check crítico (solo `ok` da 200); main.py le entrega head y revisiones conocidas con configure_migrations; no importa app.main ni módulos
        alerts.py        # AlertSink, register_sink(), alert(): alertas internas del equipo (Sprint 4A: LogAlertSink)
        alerts_telegram.py # TelegramAlertSink y register_from_settings (Sprint 5, S5-D29): el sink de Telegram con httpx directo; chat en TELEGRAM_CHAT_ID
        mail.py          # send_mail(settings, message): SMTP con smtplib en asyncio.to_thread (Sprint 5, S5-D64); único sitio de smtplib
        export.py        # escape_formula, csv_header/csv_rows/csv_stream, single_flight (flujo único por usuario, caduca a los 15 min), begin_export/guarded_body, ExportStream y EXPORT_MAX_ROWS de las exportaciones CSV (Sprint 5, S5-D41, S5-D82, S5-D247); `core/http.py` suma csv_download
        pdf.py           # render_text_pdf: escritor de PDF propio, una página A4 en Courier (Sprint 5, S5-D65)
        crypto/          # EL BUS DE CRIPTOGRAFÍA (ver abajo)
          registry.py    #   registro de data_class y puerto Reencryptor
          provider.py    #   puerto KeyProvider (name, status, rewrap), get_provider_named y make_resolver: proveedor por fila de crypto_keys (Sprint 5, S5-D3)
          openbao_provider.py #   OpenBaoProvider (Transit, httpx async) y map_error (Sprint 5, S5-D17); único sitio de httpx hacia OpenBao
          state.py       #   estado del proveedor y health_state puro (Sprint 5, S5-D13)
          recovery.py    #   sondeo y try_load de las DEK tras el sellado (Sprint 5, S5-D16, D70)
          migration.py   #   plan_provider_migration, migrate_provider, verify_provider y el motor de re-envoltura por llave (unwrap + wrap, FOR UPDATE, DEK en ceros); solo encrypt|index (Sprint 5, S5-D18, D183)
          rotation.py    #   rotate_kek, rotate_or_resume, rewrap_all, trim_ready(_version), trim_kek y trim_kek_checked bajo el candado apex:rotate:kek (config, nunca trim; S5-D188) sobre el motor de migration (Sprint 5, S5-D19, D55a, D185)
          minisign.py    #   verify_minisign y parse_pubkey de la firma del manifiesto (Sprint 5, S5-D72)
          digest.py      #   SHA-256 sin dependencias (solo `hashlib`; lo usa core/audit)
          file_digest.py #   digest_file(path, chunk, max_bytes=): SHA-256 de un archivo en reposo sin seguir enlaces, el único lector de archivos de respaldo que usa el worker; solo biblioteca estándar (S4B-D134, S4B-D139)
          service.py     #   rotación reanudable (start_rotation, reencrypt_batch, finish_rotation, fail_job, rotate_index) y retiro (count_rows_by_key, count_audit_blobs, retire_key, recent_kek_verify, next_key_state, validate_reason); candado `apex:rotate:<clase>`, único sitio con FOR UPDATE de llaves y tablas cifradas; sin core/audit (S4B-D39, D142 a D146)
          discovery.py   #   encrypted_columns(metadata, data_class): columnas Encrypted de una clase por el registro, sin importar módulos (S4B-D39)
          archive.py     #   digest_file() y, desde B3a, export_kek_file/restore_kek_file/verify_kek_backup: `age -p`/`age -d` por Popen (lista, env={}, sin shell), la KEK por descriptor, salida O_EXCL 0o600, errores tipados sin texto del hijo (S4B-D20, D58, D121 a D126); única puerta de la KEK junto con local_provider
          kek_backup.py  #   WrappedDek, verify_wrapped (AESGCM + parse_wrapped; deja el bytearray en ceros) y load_wrapped (un SELECT de solo lectura); la clase de dato `kek.backup` (registry.py, sin llave) da nombre a las filas de crypto_ops de export-kek, verify-kek-backup y restore-kek (S4B-D85)
          state.py       #   CryptoState (ok|sealed|unreachable|unknown) y health_state puro: proveedor + keyring + umbral de desello (Sprint 5, S5-B3, S5-D13, D194)
          recovery.py    #   try_load (api: ensure_keys; worker: solo load_all con classes), poll_forever (cada CRYPTO_RECOVERY_POLL_S), current_state, is_loaded; una línea de log y una alerta por transición; solo lo importan main.py y worker/runtime.py (S5-B3, S5-D16, D195)
      modules/
        auth/        router.py schemas.py models.py service.py exceptions.py
                     rules.py tokens.py cookies.py   # ayudas privadas del módulo (S2-D4)
                     sessions.py users.py links.py events.py mail_texts.py   # privados tras la fachada service.py (Fase 4 del Sprint 2)
        settings/    router.py schemas.py models.py service.py
        members/     router.py schemas.py models.py service.py
                     exports.py   # exportación CSV de socios, privado (Sprint 5, S5-B12, US-138): lotes de 500 por (created_at, id), `_decrypt_batch` es la segunda puerta de `types.reveal` (purpose `export`), auditoría de apertura y cierre
                     channels.py  # preferencias de canal de aviso, privado (Sprint 5, S5-B5, S4A-D72); contact.py acepta `fields` (S5-D32)
                     contact.py   # contact_for_notification(session, member_id, purpose, *, fields=None), privado (Sprint 4A, S4A-D21; `fields` y consentimiento en S5-B5)
        plans/       ...           # changes.py si service.py pasa de 600 líneas (S4A-D72; en 4A service.py mide 506 y no se extrajo)
        memberships/
                     expirations.py   # recompute_statuses del job diario, privado (Sprint 4A, S4A-D2)
        payments/    # router, schemas, service, models, rules, queries; `exports.py` privado (Sprint 5, S5-B12, US-139: CSV de pagos en lotes por (paid_at, id), sin bus de cifrado); `receipt.py` privado (Sprint 5, S5-B11, US-137, S5-D40, D241): `format_cop`, `format_bogota`, `receipt_context` y `render_receipt` sobre `core/pdf.py`, sin documento, teléfono ni correo; `service.receipt_pdf` audita `download` (D242)
        audit/       # router, schemas, service (se suscribe a los eventos de auth); privados verify.py (S4A-B3), queries.py y diff.py (S4A-B4); los models viven en core/audit.py y core/audit_verify.py
        dashboard/   # router, schemas, service; sin models (Sprint 4A); en B10 (S5-D47) suma la arista `dashboard -> notifications` (`today_count`) y `members.service.count_without_consent`
        notifications/ # v0.2 (Sprint 5): router, schemas, models, service, exceptions; esquema `notifications` (plantillas, reglas, avisos); el job notify y el único llamador de contact_for_notification (S5-D23, D32). En B6 (US-120, US-121): `models.py` (`NotificationTemplate`, `NotificationRule`; migraciones 0017 y 0018), `router.py` (9 rutas `/notification-templates` y `/notification-rules`; `notifications-write` y `staff-read`) y `service.py` (fachada y `seed_defaults`); privados tras la fachada: `rules.py` (puro: `render`, `validate_rule`, `target_dates`, `days_value` y la siembra por defecto), `templates.py` y `rules_crud.py`. En B7 (US-124, US-127 a US-130; migración 0019): `models.Notification` (`__audit_subject__ = "member_id"`), `events.py` (cuatro eventos sin datos personales), privados `generate.py` (importa `members.service` y `memberships.service`, S5-D26), `queries.py`, `whatsapp.py` (`build_link`, pura) y `sending.py`/`channels/` (el envío llega en B8); `service.py` suma `generate_today`, `today_list`, `today_count`, `list`, `get`, `list_for_member`, `wa_link` (único llamador de `contact_for_notification`) y `skip`; 6 rutas más (`/notifications/today` antes de `/{id}`)
        attachments/   # v0.3
        classes/       # v0.4
        wods/          # v0.5
        results/       # v0.5
        tv/            # v0.5; router, schemas, service; sin models
        athletes/      # v0.6
        portal/        # v1.0; router, schemas, service; sin models
      worker/
        main.py          # punto de entrada delgado: --run-once <job> [--date --simulate], --status <job>, serve (APScheduler)
        schedule.py      # WORKER_TIMEZONE, DAILY_HOUR, DAILY_MINUTE, next_run, should_run, *_sim (S4A-D5, S4A-D48)
        registry.py      # JobSpec y registro de jobs
        runner.py        # run_job y run_cycle: actor del sistema, reclamo, tiempo máximo, finish_run, alert
        runtime.py       # worker_runtime(with_crypto=True: keyring con phone y email, sin INSERT, sondeo si arranca sellado; S5-B3), espera de la base y latido (/tmp/apex-worker-heartbeat)
        jobs/            # expirations.py (Sprint 4A); backup_check.py (S4B-B2: manifiesto, sin age); notify.py (v0.2, Sprint 5, S5-D35, B8: generar, enviar y resumir); sign_audit.py (v0.3, EP-17)
    migrations/          # Alembic
    tests/
      architecture/      # pruebas de arquitectura; corren en todos los gates
  web/                   # front React 19 + TypeScript + Vite; se construye aquí
  scripts/
    workflow/            # slice-gate.sh, checkpoint-commit.sh, run-gates.sh, validate-impact-analysis.sh
    ci/                  # smoke de compose, prueba de imagen, licencias, prod-smoke.sh (stack de producción en apex-smoke), check-release-version.sh (etiqueta = pyproject = package.json = CHANGELOG), test_deploy_script.sh con fakes/
    dev/                 # telegram_fake.py (S5-B4, S5-D78): Telegram falso de la biblioteca estándar, solo lo monta el perfil `avisos` de compose.dev.yml
  infra/
    compose.yml
    compose.dev.yml      # desarrollo; perfiles opcionales `openbao` y `avisos` (mailpit y telegram-fake por digest, solo aquí, S5-D78)
    compose.e2e.yml      # solo E2E (V4): zona de limit_req alta para Nginx
    compose.verify.yml   # solo backup: monta la identidad age de verificación (S4B-D59)
    compose.openbao.yml  # overlay con CRYPTO_PROVIDER=openbao: api y worker sin el volumen `keys` y con su token (Sprint 5, S5-D74)
    nginx/default.conf       # y snippets/ (zonas de limit_req: auth-zone.conf y health-zone.conf)
    db/                  # roles.sql, grants.sql, revoke.sql y apply.sh: roles de aplicación y permisos por tabla/columna; los aplica el servicio dbsetup (S4B-W0-3)
    backup/              # Dockerfile (postgres:16-alpine + age, minisign, rclone, supercronic), run.sh, lib.sh,
                         # entrypoint.sh, healthcheck.sh, manifest.schema.json y tests/ (Bash puro), restore.sh (B3a, restauración con firma e inspección del tar)
    openbao/             # config.hcl, bootstrap.sh (--first-install, S5-D76), dev-entrypoint.sh (solo APEX_ENV=dev) y policies/*.hcl: una llave Transit apex-kek, tokens por servicio, red `custody` (Sprint 5)
    deploy.sh            # despliegue en el servidor (B4): `--ref <etiqueta> --expect-sha <sha> --kek-file <copia age de la KEK>` más `--i-know-unsigned-ref` (obligatoria en v0.1: sin firma de etiqueta) y `--i-know-no-backup` (omite el respaldo pre-deploy); variables `DEPLOY_STATE_DIR`, `DEPLOY_HEALTH_TIMEOUT`, `DEPLOY_SKIP_BUILD`, `DEPLOY_COMPOSE_EXTRA`; preverificación, respaldo pre-deploy, build, up, sondeo de /health con migrations ok, rollback-<fecha>.txt si falla; nunca down -v, push, pull ni --force
    tests/               # deploy_e2e.sh: solo apex-smoke y CI
  docs/
    PLAN.md              # referencia original del backend
    ddd/                 # plan de trabajo aprobado: 00b a 09, DECISIONES.md, GATE.md
    design/              # diseño aprobado del front
    openapi.json         # contrato exportado del API
    adr/                 # ADR-001-monolito-modular.md, ADR-002-criptografia.md, ADR-003-pagos-inmutables.md, ADR-004-serializacion-canonica-de-auditoria.md y README.md (plantilla de seis secciones); cambiarlos exige detenerse y preguntar (S4B-D47)
    operacion/           # guías para quien opera: instalar-en-servidor, actualizar, respaldo-y-restauracion, rotar-llave, importar-socios, demo
    plantillas/          # importar-socios.xlsx (plantilla del import-members)
    RUNBOOK.md           # operación del día a día; §12 despliegue, rollback y `migrations: mismatch` (B4)
  .env.example
  .env.ops.example       # variables de operación (respaldo, firma, roles de base, red); la copia .env.ops no se versiona
  .env.seed.example      # ADMIN_* del primer seed; la copia .env.seed solo la lee tools
  .pre-commit-config.yaml
  .github/workflows/ci.yml        # lint, pruebas, imágenes, E2E y prod-smoke
  .github/workflows/release.yml   # etiqueta vX.Y.Z: verify (versión, imágenes, prod-smoke, contrato) y Release en borrador; sin push de imágenes
  LICENSE, CHANGELOG.md, README.md  # licencia propietaria, versiones y mapa de la documentación
```

## Reglas de módulos

1. Cada módulo tiene `router.py`, `schemas.py`, `service.py` y, si tiene tablas propias, `models.py` (y `exceptions.py` si hace falta). Lógica de negocio solo en `service.py`; los routers validan, llaman al service y devuelven. Un router plano por módulo (S2-D3): un solo `APIRouter` en `router.py`, con la ruta completa en cada decorador (`/auth/login`, no prefijos anidados). Las ayudas privadas de un módulo (en `auth`: `rules.py`, `tokens.py`, `cookies.py`, `sessions.py`, `users.py`, `links.py`, `events.py`, `mail_texts.py`; en `payments`: `receipt.py` y `exports.py`; en `members`: `exports.py`) solo las importa ese módulo (regla `private_helper` de `tests/architecture`). Un `service.py` que pasa de 800 líneas se parte en archivos privados como estos y queda como fachada: es lo único que importan los demás módulos.
2. Un módulo solo llama a otro a través de su `service.py`. Puede importar `schemas.py` y `exceptions.py` de otro módulo; nunca su `models.py` ni su `router.py`. Prohibido hacer joins cruzados fuera de su esquema.
2 bis. Dependencias mutuas entre services (G-03). Entre dos módulos, el sentido mayoritario llama al `service.py` del otro. El sentido minoritario, si solo valida o consulta, usa un puerto que el módulo dueño registra al arrancar, igual que `subscribe` (por ejemplo `payments.set_membership_gate(memberships.service.payability)`). Si es una lectura de presentación, usa un import perezoso dentro de la función, con comentario, y solo para los pares de la lista blanca de `tests/architecture/test_service_import_graph.py`: en v0.1 `memberships` ↔ `payments`, `members` ↔ `memberships` y `plans` ↔ `memberships`; en v0.4 `members` ↔ `classes`.
3. Cuando una acción interesa a varios módulos, el origen emite un evento por el bus de `core/events.py` (por ejemplo `PaymentRegistered`) y los demás se suscriben. El tipo del evento se define en el módulo emisor y se exporta desde su `service.py`; `core/events.py` es solo el bus (decisión L7, `docs/ddd/DECISIONES.md`, revisión de Fase 4 del Sprint 2). No se encadenan services de tres módulos en un endpoint. Una lectura sí puede recorrer aristas existentes del mapa de contextos hasta profundidad 2, por lote, sin escribir ni emitir eventos (G-04; `docs/ddd/03_context_map.md`, sección 5).
4. `core/` es compartido y ningún módulo lo modifica desde su dominio.
5. SOLID en versión ligera: interfaces solo donde hay algo que intercambiar (`KeyProvider`, `NotificationChannel`, `StorageProvider`). No se crean entidades de dominio separadas de los modelos ni repositorios abstractos por tabla.

## Reglas de datos

1. Dinero en entero, en COP, sin decimales. Columna `amount_cop: int`.
2. Fechas y horas en UTC con zona horaria (`TIMESTAMPTZ`); la conversión a hora de Bogotá es del front.
3. Toda tabla lleva `id` (UUID), `created_at`, `updated_at`, `created_by`.
4. Borrado lógico (`deleted_at`) en socios, planes y usuarios. Prohibido el borrado físico en pagos, resultados, auditoría y llaves.
5. Pagos inmutables: nunca `UPDATE` ni `DELETE`; un error se corrige con `voided=true`, `void_reason` y un pago nuevo.
6. Toda lista pagina (`limit`, `offset`, máximo 200) y acepta búsqueda.
7. Una migración de Alembic por cada cambio de tabla. Nunca `create_all` en producción. Nunca editar una migración ya aplicada. Cambios con datos en tres pasos: columna nula, llenar, obligatoria.
8. Las migraciones de datos (importar socios, recifrar campos) son comandos en `cli.py`, idempotentes y auditados; no van en Alembic. Única excepción (N-15): la fila del usuario técnico `system@apex.local`, UUID fijo `00000000-0000-0000-0000-000000000001` expuesto como `SYSTEM_USER_ID` en `core/context.py`, la inserta la migración `0004_auth`, porque es dato de referencia para llaves foráneas. Ese usuario tiene `is_active = false` y nunca autentica; worker, seed, importación y migraciones de proveedor lo usan como `created_by`, y todo comando del CLI acepta `--as <email>` para atribuir la acción a una persona.

## El bus de criptografía (`core/crypto/`)

1. Única puerta: `encrypt(data_class, plaintext, aad)`, `decrypt(blob, aad)`, `blind_index(data_class, value)`, `sign(data_class, data)`, `verify(data_class, data, signature)`, más `digest(data)` (SHA-256 para la cadena de auditoría, en `core/crypto/digest.py`) y `digest_file(path)` (en `core/crypto/file_digest.py`, S4B-D139) más las funciones de respaldo de la KEK (`age -p` por `subprocess`) en `core/crypto/archive.py` (`export_kek_file`, `restore_kek_file`, `verify_kek_backup`; implementadas en B3a y expuestas por los comandos `export-kek`, `verify-kek-backup` y `restore-kek`; S4B-D20, D58; no hay `verify_age_archive`: la verificación de descifrado de los respaldos la hace el servicio `backup`).
2. `data_class` es un string como `member.document`; decide la llave. El que llama nunca elige llave ni algoritmo.
3. Envelope: KEK en el `KeyProvider`; DEK por `data_class`, envuelta en la tabla `crypto_keys`, abierta en memoria al arrancar. Campos en AES-256-GCM con `aad = id del registro`.
4. Formato del blob (texto): `apx1.<key_id>.<alg>.<nonce_b64url>.<ciphertext_b64url>`. `alg` en v0.1 es `A256GCM`. El algoritmo va en el dato, no en el código.
5. Índice ciego: HMAC-SHA-256 del valor normalizado con una llave propia por `data_class`; se guarda en columna `<campo>_idx`. Normalización (N-02, irreversible con datos): NFKD sin diacríticos, minúsculas, sin espacios, puntos ni guiones; teléfono solo dígitos, sin el prefijo `57` o `+57` inicial; correo en minúsculas y sin espacios. Ningún fragmento de un dato cifrado se guarda en claro (no existen columnas `*_hint`); el enmascarado se calcula en memoria al leer la ficha.
6. `KeyProvider` es una interfaz con `wrap`, `unwrap`, `sign`, `verify`, `rotate`. Implementaciones: `LocalFileProvider` (v0.1, KEK en archivo 600 fuera del repo) y `OpenBaoProvider` (v0.2, Transit).
7. Tablas `crypto_keys` (metadatos, nunca material de llave en claro) y `crypto_ops` (bitácora inmutable: quién, verbo, data_class, key_id, versión, record_id, resultado).
8. Regla de lint obligatoria en `pyproject.toml` (ruff `flake8-tidy-imports` banned-api): fuera de `core/crypto` y `core/security` está prohibido importar `cryptography`, `oqs`, `hashlib`, `hmac`, `jwt`, `argon2`. Si el lint lo permite, alguien lo hará.
9. Campos cifrados en v0.1: `members.document`, `members.phone`, `members.email`, `members.emergency_contact`, `members.birth_date`. Nombre y apellido en claro (van en el leaderboard). La clase `kek.backup` (registry, sin llave ni columnas) solo nombra las filas de `crypto_ops` del respaldo de la KEK (S4B-D85).

## Seguridad

- Contraseñas con argon2id. JWT firmado con Ed25519, vida 15 minutos, más refresh token de 7 días en tabla con revocación.
- Roles: `admin`, `coach`, `member`. Cada endpoint declara su rol con una dependencia de FastAPI; no hay endpoints sin rol salvo las ocho entradas de `PUBLIC_ROUTES` (`core/security.py`): health (dos), login, refresh, logout (por cookie), forgot, reset y la TV con token de dispositivo.
- Rate limit en login. Límite por usuario en las escrituras y lecturas caras (`USER_LIMITS` de `core/ratelimit.py`); desde S4A-B3 suma `USER_READ_LIMIT_PER_MIN` (cubeta `staff-read`), `USER_AUDIT_VERIFY_LIMIT_PER_MIN` y `USER_AUDIT_VERIFY_LIMIT_PER_HOUR` (cubetas de `POST /audit/verify`). CORS solo para el dominio del front.
- Nada de secretos en el código ni en imágenes. Todo por `.env`; se versiona `.env.example`. `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` van en `.env.seed` (se versiona `.env.seed.example`), que solo lee el servicio `tools` (con `SeedSettings`) y se borra tras el primer seed; `.env.example` ya no las lleva y `Settings` las ignora (`NON_API_ENV_VARS`). `TRUSTED_PROXIES` es solo la IP fija de Nginx (`172.30.0.10/32`, red de `infra/compose.yml`). `Settings` usa `extra="forbid"`; las variables que no son del api (`WEB_PORT`, las de Postgres y backup) van en `NON_API_ENV_VARS`. **Dos archivos de ejemplo (S4B-D79):** `.env.example` (lo que lee `Settings`) y `.env.ops.example` (respaldo `BACKUP_*`, `RCLONE_CONFIG_APEX_*`, firma `BACKUP_SIGN_*`, `BACKUP_VERIFY_IDENTITY_FILE`, contraseñas de rol, red, `DEPLOY_HEALTH_TIMEOUT`; `.env.ops` no se versiona y desde 4B-W0-3 ningún servicio web lo lee entero). `POSTGRES_*`, `DATABASE_URL`, `TEST_DATABASE_URL` y los puertos viven en `.env.ops.example` (S4B-W0-3); `.env.example` no lleva ninguna contraseña. En desarrollo `.env` es la suma de los dos; en producción Compose se invoca con `--env-file .env --env-file .env.ops` y cada servicio recibe solo su bloque `environment`. **Base de datos (S4B-W0-3):** el propietario (`POSTGRES_USER`) solo lo usan `db`, `migrate`, `dbsetup` y `tools`; `api` corre como `apex_api`, `worker` como `apex_worker` y `backup` como `apex_backup` (`infra/db/`). `MIGRATE_ON_STARTUP` (`Settings`, `false` por defecto; `compose.dev.yml` la pone en `true`) la fija Compose en `false` en producción: migra el servicio `migrate` (`alembic upgrade head`), después `dbsetup`, y recién entonces arrancan api, worker y web; en desarrollo `migrate` y `dbsetup` solo existen con `--profile prod-init` y el api migra al arrancar. Una tabla nueva debe clasificarse en `infra/db/grants.sql` y en `tests/migrations/test_db_grants.py` o `dbsetup` falla cerrado. `TRUSTED_PROXIES` sigue a `APEX_WEB_IP`.
- Telegram es solo un canal interno del equipo (resumen diario de "por avisar hoy" y alertas del worker, vía `core/alerts.py`); nunca un canal al socio. Canales al socio: correo, enlace de WhatsApp y, en v1.0, push.
- Códigos 401: `token_expired` solo para un access token vencido con firma válida; `unauthorized` para todo lo demás.
- 503 `busy` con `Retry-After: 1` cuando la base agota `lock_timeout`, `statement_timeout` o detecta un interbloqueo (Sprint 3, S3-D67); nunca un 500. 503 `crypto_unavailable` con `Retry-After: 30` cuando el custodio de llaves está sellado o inalcanzable y la ruta necesita descifrar (Sprint 5, S5-D14); `/health` lo refleja en `crypto` (crítico).
- Archivos subidos: volumen `/data/uploads`, nombre aleatorio, validación por bytes mágicos, tamaño máximo 5 MB, servidos solo por el api con rol y auditoría. Los sensibles pasan por el bus (`attachment.sensitive`).

## Licencias

Solo dependencias MIT, BSD (2 y 3 cláusulas), 0BSD, ISC, Apache 2.0, PSF-2.0, OFL-1.1 (solo fuentes) o licencia PostgreSQL. MPL-2.0 aceptada solo sin modificar (OpenBao, pywebpush, certifi, axe-core). Prohibidas GPL, LGPL, AGPL, BSL y SSPL. Telegram se llama con httpx directo (python-telegram-bot es LGPL). ShellCheck es GPL: los scripts se revisan con `bash -n`. La pipeline corre `pip-licenses --allow-only` en `api/` y `license-checker` en `web/`, y falla si entra algo fuera de la lista. Mantener `NOTICE` con las licencias de terceros. Binarios de contenedor (no son dependencias de Python; bloque fijo de `NOTICE`): `age` BSD-3, `rclone` MIT, `supercronic` MIT, `minisign` ISC, `pg_dump` (licencia PostgreSQL) y `curl` (licencia curl, permisiva tipo MIT, desde B13; S5-D105) en la imagen `apex-backup`; `age` también en la del api. Imágenes de terceros del Sprint 5, también en el bloque fijo de `NOTICE`: OpenBao (MPL-2.0 sin modificar), Mailpit (MIT, solo desarrollo) y `python:3.12-alpine` (PSF-2.0, solo desarrollo, `telegram-fake`). Dependencias nuevas del api en 4B: `openpyxl` (MIT) y `defusedxml` (PSF-2.0), solo bajo `imports/`. Sprint 5: ninguna de ejecución; `pypdf` (BSD-3) solo en el grupo de desarrollo, para las pruebas del PDF; `fpdf2` y `python-telegram-bot` (LGPL) siguen prohibidos y la CI los rechaza.

## Calidad y Git

- `ruff` (lint y formato) y `mypy --strict` en `src/`. `pre-commit` corre ambos.
- `pytest` con PostgreSQL de prueba en Docker (`compose.dev.yml`, `TEST_DATABASE_URL` obligatoria). Toda regla de negocio en `service.py` tiene prueba. Cobertura global de `app` de al menos 80 %. Las pruebas marcadas `perf` miden con reloj y no son gate: `run-gates.sh` y la CI corren `-m "not perf"`, y la CI las corre aparte sin bloquear (S2-D27).
- Cada slice se trabaja en TDD: primero pruebas en rojo sobre stubs, luego implementación hasta pasar `scripts/workflow/slice-gate.sh <modulo> [pruebas...]`, y se confirma con `scripts/workflow/checkpoint-commit.sh`. `tests/architecture` corre en todos los gates. Cada wave cierra con `scripts/workflow/run-gates.sh`.
- Rama `main` protegida; ramas `feat/`, `fix/`, `chore/`; commits en Conventional Commits. Los scripts nunca hacen push: el push y el PR los hace una persona al cerrar cada sprint.
- CI en cada PR: lint, mypy, pruebas, licencias, auditoría de dependencias de producción, build de imágenes y E2E contra el stack.
- Logs en JSON a stdout. Healthcheck en `/health`; `/health` suma `backup` (`ok|attention|unknown`, informativo, S4B-B2) leído de `worker.job_runs` por `core/backup_status.py` y `migrations` (`ok|mismatch|unknown`, **crítico**: solo `ok` da 200; S4B-B4) leído de `public.alembic_version` por `core/migrations_status.py`, con caché en proceso (`db` 2 s, `backup` y `migrations` 30 s); el aviso del worker es además su healthcheck por latido (`unhealthy` en `docker compose ps`).

## Comandos

```
cd api && uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run python -m app.worker.main
uv run pytest
uv run ruff check . && uv run ruff format . && uv run mypy src
docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml up -d --build
bash scripts/workflow/slice-gate.sh core/config tests/core/test_config.py
bash scripts/workflow/run-gates.sh
docker compose --env-file .env -f infra/compose.yml run --rm tools seed --demo   # SOLO sobre bases *_demo|*_ensayo|*_smoke (docs/operacion/demo.md)
docker compose --env-file .env -f infra/compose.yml run --rm -v "$PWD/importar:/data/imports" tools import-members /data/imports/socios.xlsx --as <correo> [--dry-run] [--report r.csv]   # IMPORT_DIR, docs/operacion/importar-socios.md
cd web && npm run lint && npx tsc --noEmit && npm test && npm run build
```

`--env-file .env` es obligatorio: Compose interpola `${WEB_PORT:-80}` desde la carpeta de los archivos, no desde la raíz. Dentro de los contenedores no hay `uv` (el `PATH` apunta a `/app/.venv/bin`): `docker compose exec api alembic current`, `docker compose run --rm tools seed`.

Worker y comandos del Sprint 4A (detalle en `docs/RUNBOOK.md` §7 y §11):

```
docker compose run --rm worker python -m app.worker.main --run-once expirations
docker compose run --rm worker python -m app.worker.main --status expirations
docker compose run --rm tools recompute-memberships --as <email>
docker compose run --rm tools verify-audit --as <email>
docker compose --profile tools run --rm -v "$PWD/salida:/salida" tools export-kek --out /salida/kek.age --as <email>   # B3a: age -p pide la frase por la terminal; verify-kek-backup <archivo> [--as] y restore-kek <archivo> --out <ruta> --as <email> (docs/operacion/respaldo-y-restauracion.md)
docker compose --profile tools run --rm tools rotate-key member.document --reason "rotación trimestral" --as <email> [--index] [--batch-size 500]   # B3b: reanudable; deja la anterior en decrypt_only (docs/operacion/rotar-llave.md)
docker compose --profile tools run --rm tools retire-key <key_id> --as <email> --confirm-audit-blobs N   # B3b: irreversible
```

Despliegue y release (B4; guías en `docs/operacion/actualizar.md` y `docs/RUNBOOK.md` §12):

```
bash infra/deploy.sh --ref v0.1.0 --expect-sha <sha> --kek-file /ruta/kek.age --i-know-unsigned-ref   # en el servidor; el SHA se lee del CHANGELOG.md o del Release
SMOKE_WEB_PORT=8380 bash scripts/ci/prod-smoke.sh --no-build   # stack de producción desechable en el proyecto apex-smoke; necesita sistema de archivos Linux (modos 600 reales): CI o contenedor auxiliar, no NTFS
bash scripts/ci/check-release-version.sh --check v0.1.0
curl -s http://127.0.0.1:8181/api/v1/health   # status, db, version, backup y migrations
```

`--date <fecha> --simulate` solo con `ENV=dev` y contra una base `*_sim` o `apex_test` (S4A-D48, S4A-D63); con `ENV=production`, `verify-audit` y `recompute-memberships` exigen `--as` (S4A-D53). El worker arranca con el stack (`up -d`, sin perfil desde S4A-W0-2), después de `db` y `api` `healthy`.

## Cómo trabajar conmigo

- Explica de forma simple y ordenada, paso a paso, sin tablas.
- Un slice del sprint por vez (`docs/ddd/09_sprint_plan/`); al terminar, lista qué archivos cambiaron y qué prueba lo cubre.
- Si `docs/ddd/` (el plan aprobado en el gate) y este archivo se contradicen, manda el plan aprobado: este archivo se corrige en el mismo cambio y la decisión se anota en `docs/ddd/DECISIONES.md`. Si la contradicción es con `docs/PLAN.md`, mandan este archivo y el plan aprobado.

## Front: diseño aprobado

La carpeta `docs/design/` es la fuente de verdad del front. El front vive en `web/` (React 19 + TypeScript + Vite). Quien construya o modifique cualquier pantalla, componente o estilo:

1. Lee `docs/design/DESIGN.md` completo (colores, tipografía, componentes, patrones, reglas).
2. Busca la ruta que vas a construir en `docs/design/ROUTES.md`: ahí está la pantalla de referencia, el rol que la ve y los endpoints que consume.
3. Abre el HTML de esa pantalla en `docs/design/screens/<Clave>.html` y reprodúcelo en React con los mismos textos, la misma estructura, los mismos estados y las mismas acciones. Mira también `<Clave>.dark.html` para el tema oscuro (la TV solo existe en oscuro).
4. Usa solo las variables de `docs/design/tokens.css` (copiado en `web/src/core/styles/tokens.css`). Ningún color ni fuente literal en componentes.
5. Los componentes compartidos viven en `web/src/shared/ui/` con los nombres que da `DESIGN.md` (TopBar, SideNav, PageHeader, Button, StatusTag, FilterBar, DataTable, Pagination, Chips, Tabs, KpiCard, SidePanel, ConfirmModal, Field, MaskedValue, HistoryAside). Si uno no existe, créalo ahí antes de usarlo en una pantalla; nunca dupliques estilos por pantalla. Los hooks y esquemas que comparten dos features viven en `web/src/shared/data/`; una feature nunca importa de otra.
6. Toda lista se pagina en el servidor. Todo formulario usa React Hook Form + Zod. Todo dato del servidor pasa por TanStack Query.
7. Los logos de `docs/design/assets/logo/` se copian a `web/public/brand/`.
8. Si algo del diseño no se puede cumplir o falta una pantalla, no inventes: deja un comentario `// DESIGN-GAP:` explicando qué falta y sigue con lo demás.
9. Las listas piden al servidor `limit` y `offset` (regla de datos 6; decisión D2). `Pagination` calcula `offset = (página - 1) * limit` con tamaños 25, 50 y 100. Vender y renovar usan un solo endpoint, `POST /members/{id}/memberships`, con `first_payment` opcional y `renew: true` para renovar (D5). El estado `pending_payment` se muestra con el chip "Pendiente de pago" (Q3).

Orden de construcción del front: login y layout del panel → socios → planes → membresías y pagos → inicio → clases y check-in → movimientos, WODs y resultados → atleta → avisos → sistema → TV → portal del socio. Cada pantalla solo se construye cuando el backend de su versión existe (ver `docs/BRECHAS.md`, sección de trazabilidad).

Las diferencias conocidas entre el diseño y el plan del backend están en `docs/BRECHAS.md`. Antes de implementar un endpoint que aparece ahí, se resuelve la brecha en los documentos y luego se codifica.
