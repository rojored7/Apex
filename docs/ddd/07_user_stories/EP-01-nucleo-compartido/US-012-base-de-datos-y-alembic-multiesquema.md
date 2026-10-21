# US-012 · Como equipo quiero el acceso asíncrono a PostgreSQL con columnas comunes, un esquema por contexto y Alembic multiesquema para que cada módulo tenga su espacio y toda tabla nazca con `id`, `created_at`, `updated_at` y `created_by`

- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context:** `core/` (`core/db.py`, `migrations/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `core/db.py` con engine async, `async_session`, `Base` y `CommonColumnsMixin`, y Alembic con un `env.py` que incluya todos los esquemas
para que las tablas de cada contexto vivan en su esquema, compartan columnas comunes y solo cambien por migraciones revisadas

## Contexto de dominio

- **Aggregate / entidades:** base de todos los aggregates.
- **Reglas que aplica:** reglas de datos 2 (UTC con zona, `TIMESTAMPTZ`), 3 (`id` UUID, `created_at`, `updated_at`, `created_by`), 4 y RN-14 (`deleted_at` en socios, planes y usuarios) y 7 (una migración por cambio de tabla, nunca `create_all` en producción) de `CLAUDE.md`; `04_architecture_decision.md` sección 7 (un esquema por contexto).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `create_async_engine` con asyncpg desde `Settings.DATABASE_URL`; `async_sessionmaker(expire_on_commit=False)`; dependencia FastAPI `get_session` que abre una transacción por petición (commit al final, rollback en excepción); `Base` con `MetaData` y convención de nombres de restricciones; `CommonColumnsMixin` con `id: UUID` (default `uuid4`), `created_at`/`updated_at: TIMESTAMPTZ` en UTC (`server_default=now()`, `onupdate`), `created_by: UUID | None`; `SoftDeleteMixin` con `deleted_at: TIMESTAMPTZ | None`; `api/alembic.ini` y `migrations/env.py` async con `include_schemas=True`, `target_metadata = Base.metadata` y creación de esquemas (`CREATE SCHEMA IF NOT EXISTS`) en la migración inicial para `auth`, `settings`, `members`, `plans`, `memberships`, `payments`, `audit`, `crypto`; fixture de pytest con sesión por prueba y rollback contra `db_test`.
- **Front:** No aplica.

## Criterios de aceptación

1. `uv run alembic upgrade head` sobre una base vacía crea los ocho esquemas de v0.1 y la tabla de versión de Alembic.
2. Un modelo de prueba que hereda `CommonColumnsMixin` tiene `id` UUID, `created_at`, `updated_at` como `TIMESTAMPTZ` y `created_by`; los valores de fecha se guardan en UTC.
3. `Base.metadata.create_all` solo se usa en `tests/` (una prueba de arquitectura busca `create_all` en `src/` y falla si lo encuentra).
4. La dependencia `get_session` hace rollback si el handler lanza una excepción (prueba de router que inserta y luego falla: la fila no existe).
5. Cada prueba de service corre en una transacción que se revierte al final; dos pruebas no ven datos entre sí.
6. `alembic downgrade -1` de la migración inicial funciona en base vacía.

## Escenarios BDD

```gherkin
# language: es
Característica: Base de datos por contextos

  Escenario: Migración inicial en base vacía
    Dado una base PostgreSQL 16 vacía
    Cuando ejecuto "alembic upgrade head"
    Entonces existen los esquemas "auth", "settings", "members", "plans", "memberships", "payments", "audit" y "crypto"

  Escenario: Error en la petición revierte la transacción
    Dado un endpoint de prueba que inserta una fila y luego lanza una excepción
    Cuando lo invoco
    Entonces la respuesta es un error
    Y la fila no existe en la base

  Escenario: create_all prohibido en código de producción
    Dado un archivo en "src/app" que llama "metadata.create_all"
    Cuando corre la prueba de arquitectura
    Entonces la prueba falla nombrando el archivo
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** sí, la inicial: solo esquemas (las tablas las crea cada historia de su módulo).
- **Trigger / restricciones:** convención de nombres `ix_`, `uq_`, `ck_`, `fk_`, `pk_` en `MetaData`.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** `tests/conftest.py` (engine de `db_test`, sesión con rollback), `tests/core/test_db.py`, `tests/architecture/test_no_create_all.py`.
- **Archivos principales:** `api/src/app/core/db.py`, `api/alembic.ini`, `api/migrations/env.py`, `api/migrations/versions/0001_schemas.py`.

## Supuestos

- Supuesto: los esquemas de versiones posteriores (`notifications`, `attachments`, `classes`, `wods`, `results`, `athletes`) los crea la primera migración de su épica, no esta.

## Dependencias

- US-011 · Configuración desde .env (`DATABASE_URL`).
- US-005 · Dockerfile del api y Compose (`db` y `db_test`).

## INVEST

- **Independiente:** no depende de ningún módulo de negocio.
- **Negociable:** nombres de mixins y convención de restricciones.
- **Valiosa:** base de todas las tablas.
- **Estimable:** patrón conocido.
- **Pequeña:** dos días.
- **Testeable:** migración y rollback verificables.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas con PostgreSQL real en verde
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] Revisión de PR aprobada
