# US-084 · Vender membresía — desglose técnico

> **Corregido en S3-W0-1** (`docs/ddd/blueprints/sprint-03-plan.md`, sección 1; registro en `docs/ddd/DECISIONES.md`, "Sprint 3"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - `members.service.ref(member_id) -> MemberRef | None` no existe: es `get_ref(session, member_id) -> MemberRef`, que lanza `MemberNotFound` y expone `is_deleted` (S3-C1).
> - `MemberNotFound` no se duplica en `memberships/exceptions.py`: se importa de `members.exceptions` (S3-C10).
> - `sell(..., enforce_retroactive_limit: bool = True)` en lugar de `max_retroactive_days`; sin `by` ni `clock`: el actor sale de `get_actor()` y la fecha de `current_clock()`; el service lee `memberships_policy` (S3-C13, D3).
> - `Depends(get_session)`, `Depends(get_clock)` y `current_user.id` → `SessionDep`, `current_clock()` y `principal.user_id` (S3-C5).
> - `start_date <= hoy + 366` (422 `start_date_too_far`, salvo `renew`; S3-D47); cubeta por usuario `memberships-write` (S3-D42).

- **Historia:** `docs/ddd/07_user_stories/EP-09-membresias/US-084-vender-membresia.md`
- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context / módulo:** Memberships (`api/src/app/modules/memberships/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

El esquema, la invariante de una vigente y una futura (Q1), el no solape con `EXCLUDE USING gist` y el límite de `start_date` retroactiva (N-24) están decididos. La historia solo dejaba dos supuestos y ambos los corrige DECISIONES.md: no hay límite libre hacia atrás (N-24) y las congelaciones no van como columnas en `memberships` (N-25). Las llamadas a `members.service`, `plans.service` y `settings.service` son lecturas de validación ya previstas en el mapa de contextos; se listan como dependencias.

## Resumen

Crear la tabla `memberships.memberships` (migración `0008_memberships`), su modelo auditado y la operación `memberships.service.sell` en su camino sin pago: valida socio y plan por sus services, aplica Q1 y N-24, copia el precio (RN-04), calcula el fin (RN-05), crea la membresía en `pending_payment` y emite `MembershipSold` en la misma transacción. Expone `POST /api/v1/members/{id}/memberships` y la pantalla `Membresia_Vender` sin la sección de pago (US-085) ni el modo renovar (US-088).

## Correcciones aplicadas por DECISIONES.md

- La historia propone columnas `frozen_from`, `frozen_to`, `freeze_count` y `frozen_days_total` en `memberships` → no se crean; las congelaciones van en la tabla `memberships.membership_freezes` (migración `0009_membership_freezes`, US-089) y los conteos se derivan de sus filas: corregido por DECISIONES N-25.
- Supuesto "se acepta cualquier `start_date` que no solape, sin antigüedad máxima" → por el API `start_date` puede ser como máximo `max_retroactive_days` días antes de `today_bogota()` (por defecto 7, de `settings.memberships`); si no, 422 `code = "start_date_too_retroactive"`, `field = "start_date"`. El CLI de importación (US-112) llama a `sell` sin ese límite: corregido por DECISIONES N-24.
- Índice `(member_id, status)` de la historia → se usan los índices canónicos `(status, end_date)` y `(member_id, status, start_date)` de la numeración de migraciones (respaldan US-091, US-092 y US-094).
- "Vigente" y "futura" según Q1: vigente es `active`, `expiring` o `frozen` con `start_date <= hoy`; futura es `pending_payment` (cualquier fecha) o `active` con `start_date > hoy`. "Hoy" es `today_bogota()`: DECISIONES Q1 y Q28.
- El actor de la auditoría y `created_by` sale de `current_actor` (usuario autenticado por HTTP; `SYSTEM_USER_ID` o `--as` en CLI): DECISIONES N-15.

## Validación contra el dominio

- Aggregate `Membership` (raíz) con `agreed_price_cop` (copia, RN-04), `start_date`, `end_date`, `classes_total`, `classes_remaining`, `status`, datos de cancelación. Coincide con `02_domain_model.md` 2.3 salvo `frozen_from`/`frozen_to`, que pasan a la entidad interna `MembershipFreeze` (N-25).
- Invariantes: nace en `pending_payment` (2.3); `end_date = compute_end_date(start_date, plan)` (RN-05); Q1 con chequeo en código y red de seguridad `EXCLUDE` en base; Q4: `classes_total = classes_remaining = class_count` para planes por clases y nulos para planes por días.
- RN-01: `agreed_price_cop` es `int` > 0.
- Evento emitido: `MembershipSold(membership_id, member_id, plan_id, agreed_price_cop, start_date, end_date, renewal: bool)`; ningún suscriptor en v0.1 (el catálogo lo lista para payments, pero en la práctica S5 es una llamada directa, US-085).
- Funciones puras usadas: `compute_end_date` (US-083) y dos nuevas, `classify_open(memberships, today) -> OpenMemberships(current, future)` y `find_overlap(start, end, others) -> UUID | None`.
- Sin discrepancias adicionales.

## Validación contra la arquitectura

- Módulo dueño: `memberships`, esquema `memberships`. Sin FK hacia `members` ni `plans` (fronteras de contexto): la integridad la valida el service.
- Llamadas service a service (solo lectura, Customer/Supplier y Conformist del mapa de contextos 2): `members.service.get_ref(session, member_id)` (existencia, baja y `status`; sin campos cifrados), `plans.service.get(plan_id)` (precio, tipo, duración, clases, activo) y `settings.service.memberships_policy()` (US-058). Nunca se importan sus `models` (US-022 lo verifica). Los services devuelven DTOs inmutables, no instancias ORM.
- No es un encadenamiento de tres services de escritura: las tres llamadas son lecturas de validación; el único módulo que escribe es `memberships` (en US-085 se suma `payments`, ver su desglose).
- Evento `MembershipSold` definido como dataclass congelada pública en `memberships/service.py` (el emisor lo publica; los suscriptores lo importan del service, nunca de `models`) y emitido con `core.events.emit(event, session)` (US-014).
- Sin bus de criptografía: la membresía no tiene campos cifrados. Lint `banned-api` no aplica. El bloqueo por socio usa `pg_advisory_xact_lock(hashtextextended(member_id::text, 0))`, que es SQL de PostgreSQL y no importa `hashlib`.
- Rol: `require_role("admin", "coach")`. Auditoría: `Membership.__audited__ = True` (hook de US-016).
- La ruta `/members/{id}/memberships` vive en `memberships/router.py` (no en `members`) para que `members` no dependa de `memberships`.
- No hay listas en esta historia (paginación no aplica).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- [ ] T1 · `0008_memberships`: tabla `memberships.memberships` con `id uuid PK`, `member_id uuid NOT NULL`, `plan_id uuid NOT NULL`, `agreed_price_cop integer NOT NULL`, `start_date date NOT NULL`, `end_date date NOT NULL`, `classes_total integer NULL`, `classes_remaining integer NULL`, `status text NOT NULL`, `cancel_reason text NULL`, `cancelled_by uuid NULL`, `cancelled_at timestamptz NULL`, `created_at`, `updated_at` (timestamptz), `created_by uuid NOT NULL`; CHECKs `agreed_price_cop > 0`, `start_date <= end_date`, `status IN ('pending_payment','active','expiring','expired','frozen','cancelled')`, `classes_remaining IS NULL OR classes_remaining >= 0`, `(classes_total IS NULL) = (classes_remaining IS NULL)`, `classes_remaining IS NULL OR classes_remaining <= classes_total`, `status <> 'cancelled' OR (cancel_reason IS NOT NULL AND cancelled_by IS NOT NULL AND cancelled_at IS NOT NULL)` (lo usa US-090 sin otra migración); `EXCLUDE USING gist (member_id WITH =, daterange(start_date, end_date, '[]') WITH &&) WHERE (status <> 'cancelled')` (Q1; `btree_gist` ya creada en `0001_core_schemas`); índices `ix_memberships_status_end_date (status, end_date)` y `ix_memberships_member_status_start (member_id, status, start_date)`; `downgrade` borra índices, restricción y tabla (el esquema lo gestiona `0001`) — 3 h

### Models
- [ ] T2 · `memberships/models.py`: `class Membership(CommonColumnsMixin, Base)` con `__tablename__ = "memberships"`, `__table_args__ = {"schema": "memberships"}` más las restricciones declaradas igual que la migración (para que `create_all` de pruebas las tenga), `__audited__ = True`; `status` tipado como `Mapped[str]` validado contra `MembershipStatus`; sin relaciones a otros esquemas — 1.5 h

### Service
- [ ] T3 · Funciones puras nuevas en `service.py`: `classify_open(memberships: Sequence[OpenCandidate], today: date) -> OpenMemberships` (vigente y futura según Q1) y `find_overlap(start: date, end: date, others: Sequence[OpenCandidate]) -> UUID | None` (rangos cerrados `[]`) — 1.5 h
- [ ] T4 · `memberships/exceptions.py`: `MemberNotFound` (404), `MemberInactive` (422 `member_inactive`), `PlanInvalid` (422 `field = "plan_id"`), `PlanInactive` (422 `plan_inactive`), `StartDateTooRetroactive` (422 `start_date_too_retroactive`, `field = "start_date"`), `MembershipConflict` (409 `membership_conflict` con `existing_id`), `MembershipOverlap` (409 `membership_overlap`); todas heredan de la base de errores de dominio de `core/errors.py` (US-017) — 1 h
- [ ] T5 · `async def sell(session, *, member_id: UUID, plan_id: UUID, start_date: date | None, by: UUID, clock: Clock, renew: bool = False, first_payment: FirstPayment | None = None, enforce_retroactive_limit: bool = True) -> SaleResult`: (1) `members.service.ref` → 404 o 422; (2) `plans.service.get` → 422; (3) `settings.service.memberships_policy()`; (4) `today = clock.today_bogota()`, `start = start_date or today`, límite N-24 si `enforce_retroactive_limit`; (5) `pg_advisory_xact_lock` por socio; (6) carga las no canceladas del socio, `classify_open` → 409 `membership_conflict` si hay vigente o futura y `renew = False`; (7) `find_overlap` → 409 `membership_overlap`; (8) crea `Membership(id=uuid4(), status="pending_payment", agreed_price_cop=plan.price_cop, end_date=compute_end_date(...), classes_*)`, `flush`, traduce `IntegrityError` con SQLSTATE `23P01` a `MembershipOverlap`; (9) `emit(MembershipSold(...), session)`; devuelve `SaleResult(membership: MembershipView, first_payment_id: UUID | None)`. Las ramas `renew` y `first_payment` quedan con `NotImplementedError` hasta US-088 y US-085 — 4 h
- [ ] T6 · `MembershipView` (DTO congelado que el service entrega a routers y a otros módulos) y `_to_view(row, plan_name, freezes)`; dataclass pública `MembershipSold` — 1 h

### Schemas
- [ ] T7 · `memberships/schemas.py`: `SellMembershipIn(plan_id: UUID, start_date: date | None = None, renew: bool = False, first_payment: FirstPaymentIn | None = None)` con `model_config = ConfigDict(extra="forbid")` (`FirstPaymentIn` lo completa US-085); `MembershipOut` (`id`, `member_id`, `plan_id`, `plan_name`, `agreed_price_cop: int`, `start_date`, `end_date`, `classes_total`, `classes_remaining`, `status`, `freezes: list[FreezeOut] = []`, `cancel_reason`, `cancelled_by`, `cancelled_at`, `created_at`) y `SellMembershipOut(MembershipOut)` con `first_payment_id: UUID | None` — 1.5 h

### Router
- [ ] T8 · `memberships/router.py`: `POST /api/v1/members/{member_id}/memberships` con `Depends(require_role("admin", "coach"))`, `SessionDep`, `current_clock()`; llama a `service.sell(..., by=current_user.id)`; responde 201 `SellMembershipOut`; los errores de dominio salen por el envelope de US-017 (401, 403, 404, 409, 422); registrar el router en `main.py` — 1.5 h

### Tests unitarios puros
- [ ] T9 · `api/tests/memberships/test_rules.py`: `classify_open` (vigente activa, vigente congelada, futura pendiente, futura activa con `start_date > hoy`, solo vencidas o canceladas → ninguna) y `find_overlap` (adyacentes no solapan, mismo día de fin e inicio sí solapan, canceladas ignoradas por el llamador) — 1 h

### Tests de service con PostgreSQL
- [ ] T10 · `api/tests/memberships/test_sell_service.py`: venta por días (fin 2026-10-31, `pending_payment`, precio copiado), tiquetera 12 clases (fin 2026-11-30, 12/12), cambiar el precio del plan después no cambia `agreed_price_cop`, socio inexistente, dado de baja e inactivo, plan inexistente e inactivo, `membership_conflict` con `existing_id`, `membership_overlap` (incluida la violación de `EXCLUDE` insertando directo), venta permitida con previa `expired` o `cancelled`, `start_date` = hoy − 7 permitido y hoy − 8 rechazado, `enforce_retroactive_limit=False` sin límite, fila de auditoría `insert`, `MembershipSold` emitido una vez, handler de prueba que lanza → no queda fila ni auditoría — 4 h

### Tests de router
- [ ] T11 · `api/tests/memberships/test_sell_router.py`: 201 con el cuerpo de `MembershipOut`, 401 sin token, 403 `member`, 404 socio, 409 con envelope y `existing_id`, 422 por `plan_id`, `start_date` con hora o con formato inválido, campo desconocido (`extra="forbid"`) — 1.5 h

### Tests de arquitectura
- [ ] T12 · Confirmar que `api/tests/architecture/test_no_cross_models.py` (US-022) cubre `memberships` (no importa `members.models`, `plans.models` ni `settings.models`) y que `test_every_route_has_role.py` ve la ruta nueva con rol — 0.5 h

### Front
- [ ] T13 · `web/src/features/memberships/api.ts` (`useSellMembership` con `useMutation` que invalida `["memberships"]` y `["members", id]`) y `schemas.ts` (Zod `sellMembershipSchema`, `membershipOutSchema`); función pura `computeEndDate` en `web/src/features/memberships/lib/rules.ts` para la vista previa del resumen (el servidor manda) — 1.5 h
- [ ] T14 · `web/src/features/memberships/pages/SellPage.tsx` en `/membresias/vender` y `?socio=:id`: buscador de socio (`GET /members?q=`), selector de plan activo (`GET /plans?active=true`), fecha de inicio por defecto hoy en Bogotá, resumen con `$ 120.000`, fin `31 oct 2026` y clases; estados cargando, sin planes activos, error 409 con enlace "Renovar" a `?socio=:id&renovar=1`, error por campo desde `error.field`, éxito que redirige a `/socios/:id` pestaña Membresías; react-hook-form + Zod; solo tokens de `tokens.css` — 3.5 h
- [ ] T15 · Vitest + Testing Library `web/src/features/memberships/pages/SellPage.test.tsx` y `lib/rules.test.ts`: resumen, formato de moneda y fecha, 409 con enlace, sin planes activos, error de `start_date` — 2 h

### DevOps
- [ ] T16 · Regenerar `docs/openapi.json` y los tipos `web/src/core/api/types.ts` — 0.5 h

### Seguridad
- [ ] T17 · Revisar: rol en la ruta; `member_id` de la URL validado como UUID; un coach no puede fijar `agreed_price_cop` (no existe en el schema, `extra="forbid"`); los errores 404/409 no filtran datos del socio más allá de `existing_id`; logs sin datos personales — 0.5 h

## Orden de ejecución
1. T9 (pruebas puras en rojo), T3
2. T1, T2
3. T4, T6
4. T10 (rojo), T5 (verde)
5. T7, T11 (rojo), T8 (verde)
6. T12
7. T16
8. T13, T15 (rojo), T14 (verde)
9. T17

## Dependencias técnicas
- US-083 · Reglas puras: `compute_end_date`, `compute_status`, tipos `MembershipStatus` y `PlanTerms`.
- US-012 · Base de datos y Alembic multiesquema: `CommonColumnsMixin` con UUID asignado en Python y `0001_core_schemas` con el esquema `memberships` y la extensión `btree_gist`.
- US-014 · Bus de eventos transaccional: `emit(event, session)`.
- US-016 · Hook de auditoría: `__audited__` y `current_actor`.
- US-017 · Envelope de errores con `existing_id`.
- US-034 · `require_role`.
- US-013 · `Clock` y `today_bogota()`.
- US-058 · `settings.service.memberships_policy()` (`max_retroactive_days`).
- US-069 · Registrar socio: debe exponer `members.service.get_ref(session, member_id) -> MemberRef | None` (`id`, `first_name`, `last_name`, `status`, `deleted_at`; sin campos cifrados). No está nombrado en EP-07; se agrega a su contrato.
- US-078 / US-079 · Planes: `plans.service.get(plan_id)` con `price_cop`, `kind`, `duration_days`, `class_count`, `is_active`, `deleted_at`.
- US-063 / US-064 · Componentes `Field`, `Button`, `PageHeader` del kit (front).

## Endpoints
- `POST /api/v1/members/{id}/memberships` — roles: admin, coach

## Riesgos
- Esquema difícil de cambiar con datos reales (historia de riesgo 2 del README): un error en la restricción de exclusión se propaga a renovar, congelar, resumen y job — mitigación: la migración se prueba con `upgrade`/`downgrade`/`upgrade` y la suite de solape inserta filas directas que deben fallar con `23P01`.
- Una `pending_payment` vieja sin pagar bloquea nuevas ventas (Q1 la cuenta como futura) — mitigación: el 409 trae `existing_id` y el front ofrece abrirla para cobrar o anular (US-090).
- Concurrencia: dos ventas simultáneas al mismo socio con fechas no solapadas podrían pasar el chequeo de "una futura" — mitigación: `pg_advisory_xact_lock` por socio antes de leer.
- Front condicionado a D1: si el gate no aprueba S1, T13 a T15 salen del alcance.
- Contrato `members.service.ref` no escrito en EP-07 — mitigación: se integra en el desglose de US-069; mientras tanto se prueba con un doble.

## Estimación
- Backend: 15 h
- Front: 7 h
- Pruebas: 7 h
- DevOps / seguridad: 1 h
- **Total: 30 h**

Se pasa del rango de 5 puntos (16 a 26 h) porque incluye la migración con la restricción de exclusión, la clasificación de Q1 y la pantalla completa de venta; se mantiene como una sola historia porque las tres piezas se prueban juntas.

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/memberships/test_rules.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_sell_service.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_sell_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/memberships`
- [ ] En la base de desarrollo, insertar a mano dos membresías no canceladas del mismo socio con rangos solapados falla con `conflicting key value violates exclusion constraint`
- [ ] `SELECT action, table_name FROM audit.audit_log WHERE table_name = 'memberships' ORDER BY seq DESC LIMIT 1` devuelve `insert` tras una venta por `curl -X POST /api/v1/members/<id>/memberships`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.memberships --cov-fail-under=80`
