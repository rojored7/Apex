# US-078 · Crear plan — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-08-catalogo-de-planes/US-078-crear-plan.md`
- **Épica:** EP-08 · Catálogo de planes
- **Bounded context / módulo:** Plans (`api/src/app/modules/plans/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

El aggregate, las validaciones (RN-01, P2 e invariante de `class_count`) y el rol están definidos. El único supuesto de la historia (nombre sin unicidad) lo corrige N-22: el nombre es único entre planes no borrados. Con eso el esquema de `0007_plans` queda completo.

## Resumen

- Crea la tabla `plans.plans` (migración `0007_plans`) con `CHECK` de precio, duración, tipo y número de clases, e índice único parcial sobre `name` entre no borrados.
- Expone `POST /api/v1/plans` solo para admin; responde 201 con `PlanOut`.
- Función pura `validate_plan(kind, duration_days, class_count)` como contrato de pruebas.
- Emite `PlanCreated` en la misma transacción; la fila `insert` de auditoría la escribe el hook.
- Front: botón "Nuevo plan" y `SidePanel` con formulario condicional (número de clases solo si el tipo es "Por clases").

## Correcciones aplicadas por DECISIONES.md

- El supuesto "el nombre del plan no tiene regla de unicidad; se admiten dos planes con el mismo nombre" → el nombre es único entre planes no borrados (índice único parcial `name WHERE deleted_at IS NULL`); crear con un nombre ya usado responde 409 `plan_name_duplicated` con `field = "name"` y `existing_id`: corregido por DECISIONES N-22.
- `created_by` cuando el plan lo crea el seed o un CLI → `SYSTEM_USER_ID` o el usuario de `--as <email>` (US-111): corregido por DECISIONES N-15.

## Validación contra el dominio

- Aggregate `Plan` (raíz) con value object `Money` (`price_cop`, entero mayor que 0, RN-01).
- Invariantes: `kind = classes` exige `class_count > 0`; `kind = days` exige `class_count` nulo; `duration_days > 0` siempre (P2); nombre no vacío y único entre vivos (N-22). Se protegen en `validate_plan`, en el esquema y con `CHECK` en la base.
- RN-14: la columna `deleted_at` existe desde esta migración (la usa US-082).
- Evento emitido: `PlanCreated(plan_id)`. Sin suscriptores en v0.1.
- Sin discrepancias.

## Validación contra la arquitectura

- Módulo dueño: `plans`, con `models.py`, `schemas.py`, `service.py`, `router.py`, `exceptions.py`.
- Sin datos sensibles: no usa el bus.
- Rol: `require_role("admin")`.
- Auditoría: `__audited__ = True`; el hook de US-016 escribe `insert` con el `after` y llena `created_by`.
- Envelope de errores de US-017 (422 con `field`, 409 con `existing_id`).
- Sin llamadas a otros módulos.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- [ ] T1 · `0007_plans`: tabla `plans.plans` (el esquema lo crea `0001_core_schemas`) con `id uuid PK`, `name text NOT NULL`, `price_cop integer NOT NULL`, `kind text NOT NULL`, `duration_days integer NOT NULL`, `class_count integer NULL`, `is_active boolean NOT NULL DEFAULT true`, `deleted_at timestamptz NULL`, `created_at`/`updated_at timestamptz NOT NULL DEFAULT now()`, `created_by uuid NOT NULL`; `CHECK (price_cop > 0)`, `CHECK (duration_days > 0)`, `CHECK (kind IN ('days','classes'))`, `CHECK ((kind = 'classes' AND class_count > 0) OR (kind = 'days' AND class_count IS NULL))`, `CHECK (btrim(name) <> '')`; índice único parcial `uq_plans_name_alive ON (name) WHERE deleted_at IS NULL` (N-22); índice `ix_plans_active_alive ON (is_active) WHERE deleted_at IS NULL` (lo pide US-079; va aquí para no abrir otra migración); downgrade `DROP TABLE plans.plans` — 3 h

### Models
- [ ] T2 · `plans/models.py`: `Plan(CommonColumnsMixin, Base)` con `__table_args__` (esquema `plans`, los `CheckConstraint` e índices de T1) y `__audited__ = True` — 1.5 h

### Service
- [ ] T3 · Función pura `validate_plan(kind: PlanKind, duration_days: int, class_count: int | None) -> None` que lanza `PlanValidationError(field)` (`duration_days` menor o igual a 0; `classes` sin `class_count` o con `class_count` menor o igual a 0; `days` con `class_count`) — 1.5 h
- [ ] T4 · Caso de uso `async def create(session, data: PlanCreate, by: Actor) -> PlanOut`: recorta el nombre, aplica `validate_plan`, pre-chequea el nombre entre vivos, asigna `id = uuid4()`, `is_active = True`, hace `flush`; traduce la `IntegrityError` de `uq_plans_name_alive` a `PlanNameDuplicated(existing_id)`; emite `PlanCreated` — 2.5 h
- [ ] T5 · `plans/exceptions.py` (`PlanError`, `PlanValidationError`, `PlanNameDuplicated`, `PlanNotFound`) con su traducción al envelope; evento `PlanCreated(DomainEvent)` con `plan_id` en `service.py` — 1 h

### Schemas
- [ ] T6 · `plans/schemas.py`: `PlanCreate` (`extra="forbid"`, `str_strip_whitespace=True`, `name` de 1 a 80 caracteres, `price_cop: StrictInt` para que `120000.5`, `"120000"` y `true` den 422, `kind: Literal["days","classes"]`, `duration_days: StrictInt`, `class_count: StrictInt | None`); `PlanOut { id, name, price_cop, kind, duration_days, class_count, is_active, created_at, updated_at }` — 1.5 h

### Router
- [ ] T7 · `plans/router.py`: `POST /api/v1/plans` con `Depends(require_role("admin"))`, `status_code=201`; códigos 201, 401, 403, 409, 422; registro en `main.py` — 1 h

### Tests unitarios puros
- [ ] T8 · `api/tests/plans/test_validate_plan.py`: `("days", 30, None)` válido, `("classes", 60, 12)` válido, `("classes", 60, None)` error `class_count`, `("days", 30, 8)` error `class_count`, `("days", 0, None)` error `duration_days`, `("classes", 60, 0)` error `class_count` — 1 h

### Tests de service con PostgreSQL
- [ ] T9 · `api/tests/plans/test_service_create.py`: alta "Mensual" y "Tiquetera 12"; fila `insert` en `audit.audit_log` con `table_name = 'plans'` y el usuario; `PlanCreated` emitido y un handler que falla revierte; `created_by` = actor; nombre repetido entre vivos → `PlanNameDuplicated` con `existing_id`; nombre de un plan con `deleted_at` → se crea; los `CHECK` rechazan en la base un `INSERT` crudo con precio 0 o `days` con clases — 2.5 h

### Tests de router
- [ ] T10 · `api/tests/plans/test_router_create.py`: 201 admin con `PlanOut` completo y `created_at` en UTC; 403 coach y `member` sin crear nada; 401 sin token; 422 con `field` para `price_cop` (`120000.5`, `-1`, `0`, `"120000"`), `duration_days`, `class_count` y `name` (`"   "`); 409 `plan_name_duplicated`; envelope `{ "error": { "code", "message", "field" } }` — 2 h

### Tests de arquitectura
- No aplica (siguen en verde `test_no_cross_models.py`, `test_every_route_has_role.py` y `test_banned_imports.py` con el módulo nuevo).

### Front
- [ ] T11 · `web/src/features/plans/schemas.ts` (Zod `planSchema` con `superRefine` para `class_count` según `kind`, precio entero positivo) y `web/src/features/plans/api.ts` (`useCreatePlan`, que invalida `usePlans`) — 1.5 h
- [ ] T12 · `web/src/features/plans/components/PlanForm.tsx` y botón "Nuevo plan" en `pages/PlansPage.tsx`: `SidePanel` con React Hook Form; "Número de clases" aparece y es obligatorio solo con "Por clases"; precio escrito y mostrado con `format.ts` (`$ 120.000`); botón deshabilitado mientras envía; muestra el error de `field` del 422 y del 409; al guardar cierra el panel y refresca la lista; entrada de menú oculta al coach con `useCan` — 3 h
- [ ] T13 · Vitest `web/src/features/plans/components/PlanForm.test.tsx`: campo condicional, validación en cliente, error de campo del API, envío bloqueado si es inválido — 2 h

### DevOps
- [ ] T14 · `docs/openapi.json` regenerado e inclusión de `0007_plans` en el paso de CI `upgrade → downgrade -1 → upgrade` — 0.5 h

### Seguridad
- [ ] T15 · Revisión: el rol se valida en el API (no solo en el menú); `name` con longitud máxima para evitar abuso; el 409 solo expone `existing_id` al admin — 0.5 h

## Orden de ejecución

1. T1 y T2.
2. T8 (en rojo), luego T3.
3. T5 y T6.
4. T9 (en rojo), luego T4.
5. T7 y T10.
6. T14 y T15.
7. T13 (en rojo), luego T11 y T12.

## Dependencias técnicas

- US-012 · Base de datos y Alembic multiesquema: mixin común y esquema `plans` en `0001_core_schemas`.
- US-016 · Hook de auditoría after_flush.
- US-014 · Bus de eventos transaccional.
- US-017 · Envelope de errores.
- US-034 · Dependencias current_user y require_role.
- US-061 · PanelLayout con TopBar y SideNav; US-065 · SidePanel y ConfirmModal; US-060 · Formato de dinero y fechas (front).

## Endpoints

- `POST /api/v1/plans` — roles: admin

## Riesgos

- La unicidad de N-22 es sensible a mayúsculas y espacios internos ("Mensual" y "mensual" serían distintos) — mitigación: el nombre se recorta; si el gate quiere unicidad sin distinguir mayúsculas, el índice pasa a `lower(name)` en esta misma migración antes de aplicarla.
- P2 se trata como aceptado (duración siempre presente): si el gate lo revierte, cambian el `CHECK` y el formulario — mitigación: decidirlo antes de aplicar `0007_plans`.
- Front condicionado a D1.

## Estimación

- Backend: 12 h
- Front: 6.5 h
- Pruebas: 5.5 h
- DevOps / seguridad: 1 h
- **Total: 25 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/plans/test_validate_plan.py -q`
- [ ] `cd api && uv run pytest tests/plans/test_service_create.py -q`
- [ ] `cd api && uv run pytest tests/plans/test_router_create.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/plans`
- [ ] `curl -X POST /api/v1/plans -d '{"name":"Mensual","price_cop":120000.5,"kind":"days","duration_days":30,"class_count":null}'` responde 422 con `field = "price_cop"`.
- [ ] `psql -c "\d plans.plans"` muestra `uq_plans_name_alive` con `WHERE deleted_at IS NULL` y los cuatro `CHECK`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.plans --cov-fail-under=80`
