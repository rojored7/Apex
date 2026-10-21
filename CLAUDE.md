# APEX — reglas del repositorio

APEX es un sistema web para administrar un gimnasio de CrossFit en Colombia: socios, planes, membresías, pagos, vencimientos, avisos, clases, WODs, resultados y perfil del atleta. Repositorio privado. El plan de arquitectura completo está en `docs/PLAN.md` (exportado del documento de diseño); este archivo resume lo que no se negocia.

## Alcance de Claude Code en este repo

- Construye y mantiene el backend (`api/`), el worker, la infraestructura (`infra/`) y las migraciones.
- No crea ni rediseña el front. El front vive en `web/` y llega de otro flujo de trabajo; aquí solo se integra (proxy en Nginx, contrato de la API, build en la imagen).
- Antes de cualquier decisión irreversible (borrar datos, cambiar el formato del blob cifrado, cambiar una migración aplicada) se detiene y pregunta.

## Stack fijo

- Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, pydantic-settings, Uvicorn, APScheduler, httpx, argon2-cffi, PyJWT, `cryptography`, liboqs-python.
- PostgreSQL 16. Un solo servidor, un esquema por módulo.
- Docker Engine en Linux, Docker Compose. Nginx para servir el front y hacer proxy. Caddy opcional para TLS automático.
- OpenBao (motor Transit) como KMS desde la v0.2. En v0.1 el proveedor de llaves es local.
- Front (no se toca aquí): React 19 + TypeScript + Vite, build estático servido por Nginx.
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
        db.py            # engine async, sesión, Base
        security.py      # argon2, JWT Ed25519, dependencias de rol
        audit.py         # escritura en AuditLog + cadena de hashes
        events.py        # bus de eventos interno (en memoria)
        crypto/          # EL BUS DE CRIPTOGRAFÍA (ver abajo)
      modules/
        auth/      router.py schemas.py models.py service.py
        members/   router.py schemas.py models.py service.py
        plans/     ...
        memberships/
        payments/
        notifications/
        audit/
        classes/       # v0.4
        wods/          # v0.5
        results/       # v0.5
        athletes/      # v0.6
      worker/
        main.py          # APScheduler: jobs diarios
        jobs/            # expirations.py, notify.py, sign_audit.py, backup_check.py
    migrations/          # Alembic
    tests/
  web/                   # front React, se mantiene aparte
  infra/
    compose.yml
    compose.dev.yml
    nginx/default.conf
    backup/              # Dockerfile y script de pg_dump cifrado
    openbao/             # config.hcl (desde v0.2)
  docs/
    PLAN.md
    adr/                 # ADR-001-arquitectura.md, ADR-002-criptografia.md, ...
  .env.example
  .pre-commit-config.yaml
  .github/workflows/ci.yml
```

## Reglas de módulos

1. Cada módulo tiene exactamente `router.py`, `schemas.py`, `models.py`, `service.py` (y `exceptions.py` si hace falta). Lógica de negocio solo en `service.py`; los routers validan, llaman al service y devuelven.
2. Un módulo solo llama a otro a través de su `service.py`. Prohibido importar `models` de otro módulo o hacer joins cruzados fuera de su esquema.
3. Cuando una acción interesa a varios módulos, el origen emite un evento en `core/events.py` (por ejemplo `PaymentRegistered`) y los demás se suscriben. No se encadenan services de tres módulos en un endpoint.
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
8. Las migraciones de datos (importar socios, recifrar campos) son comandos en `cli.py`, idempotentes y auditados; no van en Alembic.

## El bus de criptografía (`core/crypto/`)

1. Única puerta: `encrypt(data_class, plaintext, aad)`, `decrypt(blob, aad)`, `blind_index(data_class, value)`, `sign(data)`, `verify(data, signature)`.
2. `data_class` es un string como `member.document`; decide la llave. El que llama nunca elige llave ni algoritmo.
3. Envelope: KEK en el `KeyProvider`; DEK por `data_class`, envuelta en la tabla `crypto_keys`, abierta en memoria al arrancar. Campos en AES-256-GCM con `aad = id del registro`.
4. Formato del blob (texto): `apx1.<key_id>.<alg>.<nonce_b64url>.<ciphertext_b64url>`. `alg` en v0.1 es `A256GCM`. El algoritmo va en el dato, no en el código.
5. Índice ciego: HMAC-SHA-256 del valor normalizado (minúsculas, sin espacios ni puntos) con una llave propia por `data_class`; se guarda en columna `<campo>_idx`.
6. `KeyProvider` es una interfaz con `wrap`, `unwrap`, `sign`, `verify`, `rotate`. Implementaciones: `LocalFileProvider` (v0.1, KEK en archivo 600 fuera del repo) y `OpenBaoProvider` (v0.2, Transit).
7. Tablas `crypto_keys` (metadatos, nunca material de llave en claro) y `crypto_ops` (bitácora inmutable: quién, verbo, data_class, key_id, versión, record_id, resultado).
8. Regla de lint obligatoria en `pyproject.toml` (ruff `flake8-tidy-imports` banned-api): fuera de `core/crypto` y `core/security` está prohibido importar `cryptography`, `oqs`, `hashlib`, `hmac`, `jwt`, `argon2`. Si el lint lo permite, alguien lo hará.
9. Campos cifrados en v0.1: `members.document`, `members.phone`, `members.email`, `members.emergency_contact`, `members.birth_date`. Nombre y apellido en claro (van en el leaderboard).

## Seguridad

- Contraseñas con argon2id. JWT firmado con Ed25519, vida 15 minutos, más refresh token de 7 días en tabla con revocación.
- Roles: `admin`, `coach`, `member`. Cada endpoint declara su rol con una dependencia de FastAPI; no hay endpoints sin rol salvo login y health.
- Rate limit en login. CORS solo para el dominio del front.
- Nada de secretos en el código ni en imágenes. Todo por `.env`; se versiona `.env.example`.
- Archivos subidos: volumen `/data/uploads`, nombre aleatorio, validación por bytes mágicos, tamaño máximo 5 MB, servidos solo por el api con rol y auditoría. Los sensibles pasan por el bus (`attachment.sensitive`).

## Licencias

Solo dependencias MIT, BSD, Apache 2.0 o licencia PostgreSQL. MPL-2.0 aceptada solo sin modificar (OpenBao, pywebpush). Prohibidas GPL, LGPL, AGPL, BSL y SSPL. Telegram se llama con httpx directo (python-telegram-bot es LGPL). La pipeline corre `pip-licenses` y falla si entra algo fuera de la lista. Mantener `NOTICE` con las licencias de terceros.

## Calidad y Git

- `ruff` (lint y formato) y `mypy --strict` en `src/`. `pre-commit` corre ambos.
- `pytest` con PostgreSQL de prueba en Docker (`compose.dev.yml`). Toda regla de negocio en `service.py` tiene prueba.
- Rama `main` protegida; ramas `feat/`, `fix/`, `chore/`; commits en Conventional Commits.
- CI en cada PR: lint, mypy, pruebas, licencias, build de imágenes.
- Logs en JSON a stdout. Healthcheck en `/health`.

## Comandos

```
cd api && uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run python -m app.worker.main
uv run pytest
uv run ruff check . && uv run ruff format . && uv run mypy src
docker compose -f infra/compose.yml -f infra/compose.dev.yml up
```

## Cómo trabajar conmigo

- Explica de forma simple y ordenada, paso a paso, sin tablas.
- Una tarea del plan por vez; al terminar, lista qué archivos cambiaron y qué prueba lo cubre.
- Si el plan y este archivo se contradicen, pregunta antes de seguir.

## Front: diseño aprobado

La carpeta `docs/design/` es la fuente de verdad del front. El front vive en `web/` (React 19 + TypeScript + Vite). Quien construya o modifique cualquier pantalla, componente o estilo:

1. Lee `docs/design/DESIGN.md` completo (colores, tipografía, componentes, patrones, reglas).
2. Busca la ruta que vas a construir en `docs/design/ROUTES.md`: ahí está la pantalla de referencia, el rol que la ve y los endpoints que consume.
3. Abre el HTML de esa pantalla en `docs/design/screens/<Clave>.html` y reprodúcelo en React con los mismos textos, la misma estructura, los mismos estados y las mismas acciones. Mira también `<Clave>.dark.html` para el tema oscuro (la TV solo existe en oscuro).
4. Usa solo las variables de `docs/design/tokens.css` (copiado en `web/src/core/styles/tokens.css`). Ningún color ni fuente literal en componentes.
5. Los componentes compartidos viven en `web/src/shared/ui/` con los nombres que da `DESIGN.md` (TopBar, SideNav, PageHeader, Button, StatusTag, FilterBar, DataTable, Pagination, Chips, Tabs, KpiCard, SidePanel, ConfirmModal, Field, MaskedValue, HistoryAside). Si uno no existe, créalo ahí antes de usarlo en una pantalla; nunca dupliques estilos por pantalla.
6. Toda lista se pagina en el servidor. Todo formulario usa React Hook Form + Zod. Todo dato del servidor pasa por TanStack Query.
7. Los logos de `docs/design/assets/logo/` se copian a `web/public/brand/`.
8. Si algo del diseño no se puede cumplir o falta una pantalla, no inventes: deja un comentario `// DESIGN-GAP:` explicando qué falta y sigue con lo demás.

Orden de construcción del front: login y layout del panel → socios → planes → membresías y pagos → inicio → clases y check-in → movimientos, WODs y resultados → atleta → avisos → sistema → TV → portal del socio. Cada pantalla solo se construye cuando el backend de su versión existe (ver `docs/BRECHAS.md`, sección de trazabilidad).

Las diferencias conocidas entre el diseño y el plan del backend están en `docs/BRECHAS.md`. Antes de implementar un endpoint que aparece ahí, se resuelve la brecha en los documentos y luego se codifica.
