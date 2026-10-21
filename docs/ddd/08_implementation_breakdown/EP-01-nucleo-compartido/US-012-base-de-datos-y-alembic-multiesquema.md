# US-012 · Base de datos async, columnas comunes y Alembic multiesquema — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-01-nucleo-compartido/US-012-base-de-datos-y-alembic-multiesquema.md`
- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context / módulo:** core (`api/src/app/core/db.py`, `api/migrations/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El alcance está claro, y DECISIONES.md y la numeración canónica cierran los puntos que la historia dejaba distintos: la lista de esquemas, `btree_gist` y el nombre de la migración. El mixin debe asignar el UUID al construir el objeto, no al ejecutar el INSERT, porque US-028 cifra con `aad = id` antes del flush. Esto se resuelve con un listener `init` y no cambia el contrato.

## Resumen

Esta historia entrega:
- `core/db.py`: engine async con asyncpg, `async_sessionmaker`, `Base` con convención de nombres, `CommonColumnsMixin`, `SoftDeleteMixin` y la dependencia `get_session` (una transacción por petición);
- `alembic.ini` y `migrations/env.py` async multiesquema;
- la migración `0001_core_schemas`, que crea los nueve esquemas de v0.1 y la extensión `btree_gist`;
- la infraestructura de pruebas: `conftest.py` contra `db_test`, con un savepoint por prueba.

## Correcciones aplicadas por DECISIONES.md

- La historia lista ocho esquemas. Se crean nueve: también `worker`, para `worker.job_runs`. Corregido por DECISIONES N-50 y por la numeración canónica (`0001_core_schemas`).
- La historia no menciona extensiones. La migración inicial crea `btree_gist`, que exige el `EXCLUDE USING gist` de Q1. Corregido por DECISIONES, "Requisito de infraestructura detectado" (Q1).
- La historia nombra el archivo `0001_schemas.py`. Se usa `0001_core_schemas.py`, por la numeración canónica del orquestador.
- La historia deja `created_by: UUID | None`. Se declara `NOT NULL`, porque siempre hay un actor: una persona o el usuario técnico `SYSTEM_USER_ID`. Lo llena el `before_flush` de US-016. Corregido por DECISIONES N-15.
- `pg_trgm` no se crea aquí. US-070 lo deja opcional, "si la prueba de 500 ms lo exige". Si se necesita, entra en una migración propia de US-070.

## Validación contra el dominio

- Es la base de todos los aggregates. La regla de datos 3 se cumple con `id` UUID, `created_at`, `updated_at` y `created_by`.
- RN-14: `SoftDeleteMixin` con `deleted_at` solo en socios, planes y usuarios. Pagos, resultados, auditoría y llaves nunca lo heredan.
- Regla de datos 2: todas las fechas son `TIMESTAMPTZ`, a través de `type_annotation_map` (`datetime` → `TIMESTAMP(timezone=True)`).
- Sin eventos ni funciones puras.

## Validación contra la arquitectura

- Un esquema por contexto (`04_architecture_decision.md` sección 7).
- `core/db.py` no importa ningún módulo de negocio ni `core/audit.py`. Los listeners de auditoría los registra `core/audit.py` (US-016) sobre la clase de sesión, así se evita el ciclo `db` → `audit` → `db`.
- `migrations/env.py` está fuera de `src/app/core`. Puede importar los `models` de cada módulo para `target_metadata` sin violar la regla de que `core/` no depende de módulos.
- `create_all` solo se usa en `tests/` (criterio 3); lo vigila una prueba de arquitectura.
- El engine se crea con `hide_parameters=True` y `echo=False`, que es lo que pide el criterio 5 de US-018.
- Rol, paginación y auditoría `__audited__`: no aplican.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- [ ] T1 · `0001_core_schemas` (`api/migrations/versions/0001_core_schemas.py`):
  - `CREATE SCHEMA IF NOT EXISTS` para `audit`, `crypto`, `auth`, `settings`, `members`, `plans`, `memberships`, `payments` y `worker`;
  - `CREATE EXTENSION IF NOT EXISTS btree_gist`;
  - downgrade: `DROP EXTENSION IF EXISTS btree_gist` y `DROP SCHEMA ... RESTRICT` en orden inverso; falla a propósito si algún esquema tiene tablas.
  
  — 1,5 h

### Models
- [ ] T2 · `core/db.py`:
  - `create_engine_from(settings) -> AsyncEngine` con `postgresql+asyncpg`, `pool_pre_ping=True`, `hide_parameters=True` y `echo=False`;
  - `async_session = async_sessionmaker(engine, expire_on_commit=False)`.
  
  — 1 h
- [ ] T3 · `class Base(DeclarativeBase)` con `MetaData(naming_convention={"ix": "ix_%(column_0_label)s", "uq": "uq_%(table_name)s_%(column_0_name)s", "ck": "ck_%(table_name)s_%(constraint_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s", "pk": "pk_%(table_name)s"})` y `type_annotation_map = {datetime: TIMESTAMP(timezone=True), UUID: postgresql.UUID(as_uuid=True)}` — 1 h
- [ ] T4 · Mixins en `core/db.py`:
  - `CommonColumnsMixin`: `id: Mapped[UUID]` como clave primaria con `default=uuid4` y además un listener `event.listens_for(CommonColumnsMixin, "init", propagate=True)` que asigna `uuid4()` al construir, si no viene uno; así el `id` existe antes del flush (US-028);
  - `created_at` y `updated_at` con `server_default=func.now()`; `updated_at` además con `onupdate=func.now()`;
  - `created_by: Mapped[UUID]` `NOT NULL`, sin FK, porque `auth.users` llega en `0004_auth` y el núcleo no se acopla a auth;
  - `SoftDeleteMixin`: `deleted_at: Mapped[datetime | None]`.
  
  — 1,5 h
- [ ] T5 · Helper `migrations/helpers.py`: `common_columns() -> list[sa.Column]` y `soft_delete_column() -> sa.Column`, para que cada migración de módulo declare las columnas comunes igual que el mixin — 0,5 h

### Service
- [ ] T6 · Dependencia `get_session() -> AsyncIterator[AsyncSession]` en `core/db.py`: abre `async with session.begin()`, cede la sesión, hace commit al salir y rollback ante cualquier excepción. No hace commit fuera de esa salida. Su docstring explica que el commit ocurre antes de enviar la respuesta, para que un error de commit (trigger, restricción) llegue como envelope de error (US-017) — 1 h
- [ ] T7 · Alembic: `api/alembic.ini` y `api/migrations/env.py` async (`run_async_migrations` con `connection.run_sync(do_run_migrations)`), con:
  - `include_schemas=True`;
  - `target_metadata = Base.metadata`;
  - `include_name` limitado a los esquemas de la aplicación;
  - importación explícita de los `models` de cada módulo (en `env.py`, no en `core/`);
  - la URL tomada de `get_settings().DATABASE_URL`.
  
  — 2 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- No aplica (no hay funciones puras).

### Tests de service con PostgreSQL
- [ ] T8 · `api/tests/conftest.py`:
  - fixture de sesión `engine` contra `TEST_DATABASE_URL` (servicio `db_test`) que ejecuta `alembic upgrade head` una vez por corrida;
  - fixture `session` por prueba con una conexión en transacción externa y `join_transaction_mode="create_savepoint"`, más rollback al final (criterio 5).
  
  Es infraestructura que usan todas las suites del API — 2 h
- [ ] T9 · `tests/core/test_db.py`:
  - un modelo de prueba con `CommonColumnsMixin` (tabla creada con `create_all` solo en la prueba) tiene `id` no nulo justo después de construirse;
  - `information_schema.columns` muestra `created_at` y `updated_at` como `timestamp with time zone`;
  - el valor leído viene en UTC (criterio 2);
  - dos pruebas seguidas no ven las filas de la otra (criterio 5).
  
  — 1,5 h
- [ ] T10 · `tests/core/test_migrations.py`:
  - sobre una base vacía, `upgrade head` crea los nueve esquemas, `btree_gist` en `pg_extension` y `alembic_version` (criterio 1);
  - `downgrade -1` de `0001` en una base vacía funciona (criterio 6).
  
  — 1 h

### Tests de router
- [ ] T11 · `tests/core/test_session_dependency.py`: en una app mínima, un endpoint que inserta una fila y luego lanza una excepción responde con error, y la fila no existe (criterio 4) — 1 h

### Tests de arquitectura
- [ ] T12 · `api/tests/architecture/test_no_create_all.py`: busca con `ast` llamadas a `create_all` y `drop_all` en `src/app/**`; falla nombrando el archivo y la línea (criterio 3) — 1 h

### Front
- No aplica.

### DevOps
- [ ] T13 · Verificar con US-003 y US-005 que `db_test` existe en `compose.dev.yml` y que el job de CI exporta `TEST_DATABASE_URL`; documentar la variable en `.env.example` como variable solo de pruebas — 0,5 h

### Seguridad
- [ ] T14 · Revisión:
  - `hide_parameters=True`;
  - `DATABASE_URL` nunca en logs;
  - en el downgrade, `DROP SCHEMA` con `RESTRICT` (nunca `CASCADE`), para no borrar datos por accidente.
  
  — 0,5 h

## Orden de ejecución
1. T12 (prueba de arquitectura en rojo)
2. T1
3. T3
4. T4
5. T2
6. T6
7. T7
8. T5
9. T8
10. T10
11. T9
12. T11
13. T13
14. T14

## Dependencias técnicas
- US-011 · Configuración desde .env: `DATABASE_URL` como `SecretStr`.
- US-005 · Dockerfile del api y Compose: servicios `db` y `db_test`.
- US-003 · Pipeline CI: Postgres de servicio y `TEST_DATABASE_URL`.
- US-016 · Hook de auditoría: llena `created_by` en el `before_flush`. Hasta que exista, las pruebas lo asignan a mano.
- US-020 · create_app: agrega a `env.py` el lock asesor para que dos procesos no migren a la vez.

## Endpoints
- Ninguno.

## Riesgos
- `default=uuid4` solo se aplica al ejecutar el INSERT, así que el AAD de US-028 vería `id = None` — mitigación: listener `init` que asigna el UUID al construir, verificado en T9.
- Un `created_by NOT NULL` rompe inserciones sin actor antes de que exista US-016 — mitigación: las pruebas asignan `created_by`; desde US-016 lo llena el `before_flush` con el actor o falla con un error claro.
- Ordenar el commit de `get_session` frente a las demás dependencias de FastAPI: si el commit corre después de enviar la respuesta, un error de trigger no llega al cliente — mitigación: prueba T11 y prueba de commit fallido en US-017.
- Downgrade de la migración inicial con datos: con `RESTRICT` falla en vez de borrar; es intencional.

## Estimación
- Backend: 8,5 h
- Front: 0 h
- Pruebas: 6,5 h
- DevOps / seguridad: 1 h
- **Total: 16 h**

Queda una hora por encima de la referencia de 3 puntos, porque `conftest.py` (T8) es infraestructura compartida por todas las suites.

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_db.py tests/core/test_migrations.py tests/core/test_session_dependency.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `psql "$DATABASE_URL" -c "SELECT nspname FROM pg_namespace WHERE nspname IN ('audit','crypto','auth','settings','members','plans','memberships','payments','worker')"` devuelve 9 filas
- [ ] `psql "$DATABASE_URL" -c "SELECT extname FROM pg_extension WHERE extname='btree_gist'"` devuelve 1 fila
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.db --cov-fail-under=80`
