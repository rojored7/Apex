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
      cli.py             # comandos: seed, import-members, rotate-key, sign-audit
      core/
        config.py        # Settings con pydantic-settings, todo desde .env
        db.py            # engine async, sesión, Base, CommonColumnsMixin
        clock.py         # Clock, SystemClock, FrozenClock, today_bogota()
        context.py       # SYSTEM_USER_ID, actor y lote actuales (contextvars), request_id
        security.py      # argon2, JWT Ed25519, Principal, PrincipalLoader, dependencias de rol
        errors.py        # envelope de error y handlers
        pagination.py    # PageParams, Page y SearchQuery (contrato común de listas)
        validators.py    # tipos de entrada compartidos (EmailAddress)
        search.py        # búsqueda común de las listas: limpieza de q, sin tildes, escape de LIKE
        http.py          # ayudas HTTP comunes a los routers (por ejemplo Cache-Control: no-store)
        ratelimit.py     # límite de intentos en memoria: por IP (rate_limit) y por clave (enforce)
        locks.py         # candados de fila y de aviso (lock_member); única puerta del orden de candados (Sprint 3)
        logging.py       # JSON a stdout con redacción
        audit.py         # escritura en AuditLog + cadena de hashes (usa core/crypto/digest.py)
        events.py        # bus de eventos interno (en memoria)
        jobs.py          # worker.job_runs y run_job(); lo importan solo el worker y /health
        alerts.py        # AlertSink, register_sink(), alert(): alertas internas del equipo
        crypto/          # EL BUS DE CRIPTOGRAFÍA (ver abajo)
          registry.py    #   registro de data_class y puerto Reencryptor
          digest.py      #   SHA-256 sin dependencias (lo usa core/audit)
          archive.py     #   digest_file() y verify_age_archive() sobre el binario age
      modules/
        auth/        router.py schemas.py models.py service.py exceptions.py
                     rules.py tokens.py cookies.py   # ayudas privadas del módulo (S2-D4)
                     sessions.py users.py links.py events.py   # privados tras la fachada service.py (Fase 4 del Sprint 2)
        settings/    router.py schemas.py models.py service.py
        members/     router.py schemas.py models.py service.py
        plans/       ...
        memberships/
        payments/
        audit/       # router (vacío hasta US-102, Sprint 4A), service (se suscribe a los eventos de auth), schemas al llegar US-102; los models viven en core/audit.py
        dashboard/   # router, schemas, service; sin models
        notifications/ # v0.2
        attachments/   # v0.3
        classes/       # v0.4
        wods/          # v0.5
        results/       # v0.5
        tv/            # v0.5; router, schemas, service; sin models
        athletes/      # v0.6
        portal/        # v1.0; router, schemas, service; sin models
      worker/
        main.py          # APScheduler: jobs diarios
        jobs/            # expirations.py, notify.py, sign_audit.py, backup_check.py
    migrations/          # Alembic
    tests/
      architecture/      # pruebas de arquitectura; corren en todos los gates
  web/                   # front React 19 + TypeScript + Vite; se construye aquí
  scripts/
    workflow/            # slice-gate.sh, checkpoint-commit.sh, run-gates.sh, validate-impact-analysis.sh
    ci/                  # smoke de compose, prueba de imagen, licencias
  infra/
    compose.yml
    compose.dev.yml
    compose.e2e.yml      # solo E2E (V4): zona de limit_req alta para Nginx
    nginx/default.conf
    backup/              # Dockerfile y script de pg_dump cifrado
    openbao/             # config.hcl (desde v0.2)
  docs/
    PLAN.md              # referencia original del backend
    ddd/                 # plan de trabajo aprobado: 00b a 09, DECISIONES.md, GATE.md
    design/              # diseño aprobado del front
    openapi.json         # contrato exportado del API
    adr/                 # ADR-001-arquitectura.md, ADR-002-criptografia.md, ...
  .env.example
  .env.seed.example      # ADMIN_* del primer seed; la copia .env.seed solo la lee tools
  .pre-commit-config.yaml
  .github/workflows/ci.yml
```

## Reglas de módulos

1. Cada módulo tiene `router.py`, `schemas.py`, `service.py` y, si tiene tablas propias, `models.py` (y `exceptions.py` si hace falta). Lógica de negocio solo en `service.py`; los routers validan, llaman al service y devuelven. Un router plano por módulo (S2-D3): un solo `APIRouter` en `router.py`, con la ruta completa en cada decorador (`/auth/login`, no prefijos anidados). Las ayudas privadas de un módulo (en `auth`: `rules.py`, `tokens.py`, `cookies.py`, `sessions.py`, `users.py`, `links.py`, `events.py`) solo las importa ese módulo (regla `private_helper` de `tests/architecture`). Un `service.py` que pasa de 800 líneas se parte en archivos privados como estos y queda como fachada: es lo único que importan los demás módulos.
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

1. Única puerta: `encrypt(data_class, plaintext, aad)`, `decrypt(blob, aad)`, `blind_index(data_class, value)`, `sign(data_class, data)`, `verify(data_class, data, signature)`, más `digest(data)` (SHA-256 para la cadena de auditoría, en `core/crypto/digest.py`) y, desde v0.2, `digest_file(path)` y `verify_age_archive(path, identity)` en `core/crypto/archive.py`.
2. `data_class` es un string como `member.document`; decide la llave. El que llama nunca elige llave ni algoritmo.
3. Envelope: KEK en el `KeyProvider`; DEK por `data_class`, envuelta en la tabla `crypto_keys`, abierta en memoria al arrancar. Campos en AES-256-GCM con `aad = id del registro`.
4. Formato del blob (texto): `apx1.<key_id>.<alg>.<nonce_b64url>.<ciphertext_b64url>`. `alg` en v0.1 es `A256GCM`. El algoritmo va en el dato, no en el código.
5. Índice ciego: HMAC-SHA-256 del valor normalizado con una llave propia por `data_class`; se guarda en columna `<campo>_idx`. Normalización (N-02, irreversible con datos): NFKD sin diacríticos, minúsculas, sin espacios, puntos ni guiones; teléfono solo dígitos, sin el prefijo `57` o `+57` inicial; correo en minúsculas y sin espacios. Ningún fragmento de un dato cifrado se guarda en claro (no existen columnas `*_hint`); el enmascarado se calcula en memoria al leer la ficha.
6. `KeyProvider` es una interfaz con `wrap`, `unwrap`, `sign`, `verify`, `rotate`. Implementaciones: `LocalFileProvider` (v0.1, KEK en archivo 600 fuera del repo) y `OpenBaoProvider` (v0.2, Transit).
7. Tablas `crypto_keys` (metadatos, nunca material de llave en claro) y `crypto_ops` (bitácora inmutable: quién, verbo, data_class, key_id, versión, record_id, resultado).
8. Regla de lint obligatoria en `pyproject.toml` (ruff `flake8-tidy-imports` banned-api): fuera de `core/crypto` y `core/security` está prohibido importar `cryptography`, `oqs`, `hashlib`, `hmac`, `jwt`, `argon2`. Si el lint lo permite, alguien lo hará.
9. Campos cifrados en v0.1: `members.document`, `members.phone`, `members.email`, `members.emergency_contact`, `members.birth_date`. Nombre y apellido en claro (van en el leaderboard).

## Seguridad

- Contraseñas con argon2id. JWT firmado con Ed25519, vida 15 minutos, más refresh token de 7 días en tabla con revocación.
- Roles: `admin`, `coach`, `member`. Cada endpoint declara su rol con una dependencia de FastAPI; no hay endpoints sin rol salvo las ocho entradas de `PUBLIC_ROUTES` (`core/security.py`): health (dos), login, refresh, logout (por cookie), forgot, reset y la TV con token de dispositivo.
- Rate limit en login. CORS solo para el dominio del front.
- Nada de secretos en el código ni en imágenes. Todo por `.env`; se versiona `.env.example`. `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` van en `.env.seed` (se versiona `.env.seed.example`), que solo lee el servicio `tools` (con `SeedSettings`) y se borra tras el primer seed; `.env.example` ya no las lleva y `Settings` las ignora (`NON_API_ENV_VARS`). `TRUSTED_PROXIES` es solo la IP fija de Nginx (`172.30.0.10/32`, red de `infra/compose.yml`). `Settings` usa `extra="forbid"`; las variables que no son del api (`WEB_PORT`, las de Postgres y backup) van en `NON_API_ENV_VARS`.
- Telegram es solo un canal interno del equipo (resumen diario de "por avisar hoy" y alertas del worker, vía `core/alerts.py`); nunca un canal al socio. Canales al socio: correo, enlace de WhatsApp y, en v1.0, push.
- Códigos 401: `token_expired` solo para un access token vencido con firma válida; `unauthorized` para todo lo demás.
- 503 `busy` con `Retry-After: 1` cuando la base agota `lock_timeout`, `statement_timeout` o detecta un interbloqueo (Sprint 3, S3-D67); nunca un 500.
- Archivos subidos: volumen `/data/uploads`, nombre aleatorio, validación por bytes mágicos, tamaño máximo 5 MB, servidos solo por el api con rol y auditoría. Los sensibles pasan por el bus (`attachment.sensitive`).

## Licencias

Solo dependencias MIT, BSD (2 y 3 cláusulas), 0BSD, ISC, Apache 2.0, PSF-2.0, OFL-1.1 (solo fuentes) o licencia PostgreSQL. MPL-2.0 aceptada solo sin modificar (OpenBao, pywebpush, certifi, axe-core). Prohibidas GPL, LGPL, AGPL, BSL y SSPL. Telegram se llama con httpx directo (python-telegram-bot es LGPL). ShellCheck es GPL: los scripts se revisan con `bash -n`. La pipeline corre `pip-licenses --allow-only` en `api/` y `license-checker` en `web/`, y falla si entra algo fuera de la lista. Mantener `NOTICE` con las licencias de terceros.

## Calidad y Git

- `ruff` (lint y formato) y `mypy --strict` en `src/`. `pre-commit` corre ambos.
- `pytest` con PostgreSQL de prueba en Docker (`compose.dev.yml`, `TEST_DATABASE_URL` obligatoria). Toda regla de negocio en `service.py` tiene prueba. Cobertura global de `app` de al menos 80 %. Las pruebas marcadas `perf` miden con reloj y no son gate: `run-gates.sh` y la CI corren `-m "not perf"`, y la CI las corre aparte sin bloquear (S2-D27).
- Cada slice se trabaja en TDD: primero pruebas en rojo sobre stubs, luego implementación hasta pasar `scripts/workflow/slice-gate.sh <modulo> [pruebas...]`, y se confirma con `scripts/workflow/checkpoint-commit.sh`. `tests/architecture` corre en todos los gates. Cada wave cierra con `scripts/workflow/run-gates.sh`.
- Rama `main` protegida; ramas `feat/`, `fix/`, `chore/`; commits en Conventional Commits. Los scripts nunca hacen push: el push y el PR los hace una persona al cerrar cada sprint.
- CI en cada PR: lint, mypy, pruebas, licencias, auditoría de dependencias de producción, build de imágenes y E2E contra el stack.
- Logs en JSON a stdout. Healthcheck en `/health`.

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
cd web && npm run lint && npx tsc --noEmit && npm test && npm run build
```

`--env-file .env` es obligatorio: Compose interpola `${WEB_PORT:-80}` desde la carpeta de los archivos, no desde la raíz. Dentro de los contenedores no hay `uv` (el `PATH` apunta a `/app/.venv/bin`): `docker compose exec api alembic current`, `docker compose run --rm tools seed`.

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
