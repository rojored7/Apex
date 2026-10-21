# US-089 · Congelar membresía — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-09-membresias/US-089-congelar-membresia.md`
- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context / módulo:** Memberships (`api/src/app/modules/memberships/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

DECISIONES.md resuelve los tres supuestos de la historia: las congelaciones son filas de `membership_freezes` y no "solo la última ventana" (N-25), el choque con una futura responde 409 `overlaps_future_membership` (N-25) y los límites son parámetros de `apply_freeze` leídos de `settings.memberships` (Q9, Q11). Roles fijados por Q7. Queda la migración canónica `0009_membership_freezes`.

## Resumen

Crear la entidad interna `MembershipFreeze` (tabla `memberships.membership_freezes`, migración `0009_membership_freezes`), la función pura `apply_freeze` con los límites de Q9 como parámetro, el caso de uso `memberships.service.freeze` que corre `end_date`, recalcula el estado con la lista de congelaciones y emite `MembershipFrozen`, el endpoint `POST /api/v1/memberships/{id}/freeze` (admin y coach) y el modal "Congelar" del front.

## Correcciones aplicadas por DECISIONES.md

- Supuesto "el modelo guarda solo la última ventana (`frozen_from`, `frozen_to` en `memberships`) y contadores `freeze_count`/`frozen_days_total`" → una fila por congelación en `memberships.membership_freezes` (`membership_id`, `frozen_from`, `frozen_to`, `days`, columnas comunes); `freeze_count` y `frozen_days_total` se derivan de las filas; `compute_status` recibe la lista: corregido por DECISIONES N-25.
- Criterio 10 y supuesto de la historia (`409 membership_overlap` al chocar con una futura) → `409 code = "overlaps_future_membership"` y no cambia nada: corregido por DECISIONES N-25.
- Notas técnicas "no hay migración, columnas creadas en US-084" → migración `0009_membership_freezes`: corregido por DECISIONES N-25 (y numeración canónica).
- La historia lee los límites con `settings.service.get_section("memberships")` → se usa `settings.service.memberships_policy()`, el contrato de US-058 que ya devuelve los valores por defecto (30, 2, 7) si la sección nunca se guardó: DECISIONES Q9 y Q11.
- Firma `apply_freeze(membership, frozen_from, frozen_to, limits, today)` → `apply_freeze(membership, freezes, frozen_from, frozen_to, limits, today, expiring_days)`, porque los límites de cantidad y de días se calculan sobre la lista y la elegibilidad (`active`/`expiring`) se decide con el estado efectivo de `compute_status`: DECISIONES N-25, Q9 y Q11.
- Admin y coach congelan: DECISIONES Q7.

## Validación contra el dominio

- Entidad interna `MembershipFreeze` del aggregate `Membership` (N-25); el value object `FreezeWindow` (US-083) es su forma pura. Invariantes: `frozen_from <= frozen_to`; `frozen_from` dentro de `[start_date, end_date]` vigentes; una sola congelación vigente o programada a la vez (`frozen_to >= hoy`); `days = (frozen_to - frozen_from) + 1`.
- RN-07: `end_date` aumenta exactamente `days`.
- RN-06 con N-25: el estado lo decide `compute_status(..., freezes)`: `frozen` si la ventana contiene hoy; si es futura, `active` (o vuelve de `expiring` a `active` si la extensión lo saca de la franja).
- Q9: `max_freeze_days_per_membership`, `max_freezes_per_membership`, `max_retroactive_days` como parámetros.
- Q1: extender el fin no puede solapar otra membresía no cancelada del socio.
- Evento emitido: `MembershipFrozen(membership_id, member_id, frozen_from, frozen_to, days, end_date)`.
- `apply_freeze` es pura y no muta su entrada (devuelve un resultado nuevo).
- Sin discrepancias tras N-25.

## Validación contra la arquitectura

- Módulo dueño: `memberships`; la tabla nueva está en su esquema y tiene FK a `memberships.memberships(id)` (mismo esquema, permitido).
- Llamada service a service de lectura: `settings.service.memberships_policy()`. Sin imports de `settings.models`.
- `MembershipFreeze.__audited__ = True` y la actualización de `end_date`/`status` en `memberships` también auditada (criterio 14).
- Rol: `require_role("admin", "coach")` (Q7).
- Sin bus de criptografía; `banned-api` no aplica.
- Los demás usos de `compute_status` (US-086, US-087, US-091, US-092, US-094) cargan las congelaciones con `_load_freezes(session, id)` o `_load_freezes_for(session, ids)` (una consulta por lote, sin N+1).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- [ ] T1 · `0009_membership_freezes`: tabla `memberships.membership_freezes` con `id uuid PK`, `membership_id uuid NOT NULL REFERENCES memberships.memberships(id)`, `frozen_from date NOT NULL`, `frozen_to date NOT NULL`, `days integer NOT NULL`, `created_at`, `updated_at`, `created_by`; CHECKs `frozen_from <= frozen_to` y `days = (frozen_to - frozen_from) + 1`; `EXCLUDE USING gist (membership_id WITH =, daterange(frozen_from, frozen_to, '[]') WITH &&)` como red de seguridad de "una a la vez" (usa `btree_gist` de `0001`); índice `ix_membership_freezes_membership (membership_id)`; `downgrade` borra la tabla — 2 h

### Models
- [ ] T2 · `class MembershipFreeze(CommonColumnsMixin, Base)` en `memberships/models.py` con `__audited__ = True`; relación `Membership.freezes` ordenada por `frozen_from` (`lazy="raise"` para obligar a cargarla explícitamente y evitar N+1) — 1.5 h

### Service
- [ ] T3 · Tipos y función pura: `FreezeLimits(max_days: int, max_count: int, max_retroactive_days: int)`, `FreezeOutcome(window: FreezeWindow, new_end_date: date)`, `FreezeError(code, field | None, message)` y `apply_freeze(membership: MembershipSnapshot, freezes: Sequence[FreezeWindow], frozen_from: date, frozen_to: date, limits: FreezeLimits, today: date, expiring_days: int) -> FreezeOutcome` que valida en este orden: estado efectivo (`compute_status`) en `active`/`expiring` o `membership_not_freezable`; `frozen_from > frozen_to` → `field = "frozen_to"`; `frozen_from < today - max_retroactive_days` → `freeze_too_retroactive`; `frozen_from` fuera de `[start_date, end_date]` → `freeze_outside_validity`; alguna ventana con `frozen_to >= today` → `freeze_already_scheduled`; `len(freezes) >= max_count` → `freeze_limit_reached`; `sum(days) + N > max_days` → `freeze_days_exceeded` con los días disponibles en el mensaje — 2.5 h
- [ ] T4 · `async def freeze(session, *, membership_id: UUID, frozen_from: date, frozen_to: date, by: UUID, clock: Clock) -> MembershipView`: bloquea la fila (`FOR UPDATE`), 404 si no existe, carga congelaciones y `memberships_policy()`, `apply_freeze`; verifica con `find_overlap` que `[start_date, new_end_date]` no choque con otra no cancelada del socio → `OverlapsFutureMembership` (409 `overlaps_future_membership`); inserta `MembershipFreeze`, actualiza `end_date` y `status = compute_status(...)` con la lista nueva; `flush` traduciendo `23P01` a `OverlapsFutureMembership`; `emit(MembershipFrozen(...))` — 3 h
- [ ] T5 · `exceptions.py`: mapear cada `FreezeError` a 422 (o 409 para `freeze_already_scheduled`) y `OverlapsFutureMembership` a 409; helpers `_load_freezes(session, membership_id)` y `_load_freezes_for(session, ids) -> dict[UUID, list[FreezeWindow]]` que usan las demás historias — 1 h

### Schemas
- [ ] T6 · `FreezeIn(frozen_from: date, frozen_to: date)` con `extra="forbid"`; `FreezeOut(id, frozen_from, frozen_to, days, created_by, created_at)`; `MembershipOut` gana `freezes: list[FreezeOut]` y los campos derivados `frozen_from`, `frozen_to` (de la última ventana), `freeze_count`, `frozen_days_total` — 1 h

### Router
- [ ] T7 · `POST /api/v1/memberships/{membership_id}/freeze` con `require_role("admin", "coach")`; 200 `MembershipOut`; 401, 403, 404, 409, 422 por el envelope — 1 h

### Tests unitarios puros
- [ ] T8 · `api/tests/memberships/test_freeze_rules.py`: 10 días desde hoy (fin 2026-10-31 → 2026-11-10), ventana de un día (+1), ventana futura (2026-10-20 a 2026-10-24 → 2026-11-05, sigue `active`), cada límite de Q9 con sus fronteras (retroactiva hoy − 7 permitida y hoy − 8 rechazada; 30 días exactos permitidos y 31 rechazados; tercera congelación), fechas invertidas, fuera de vigencia, ya programada, estados no congelables (`pending_payment`, `frozen`, `expired`, `cancelled`), la entrada no se modifica — 2.5 h

### Tests de service con PostgreSQL
- [ ] T9 · `api/tests/memberships/test_freeze_service.py`: congelar desde hoy queda `frozen` y `end_date` extendido; congelación futura sigue `active`; límites leídos de `settings` guardado y por defecto si la sección no existe; choque con una futura → 409 `overlaps_future_membership` sin filas nuevas ni cambios; segunda congelación tras terminar la primera; dos filas de auditoría (`insert` en `membership_freezes`, `update` en `memberships` con `end_date` y `status` antes y después); `MembershipFrozen` una vez; violación de la `EXCLUDE` insertando a mano — 3.5 h

### Tests de router
- [ ] T10 · `api/tests/memberships/test_freeze_router.py`: 200 coach y admin, 403 `member`, 401, 404, 422 con `field = "frozen_to"`, 422 con cada `code`, 409 — 1.5 h

### Tests de arquitectura
- [ ] T11 · Confirmar `test_no_cross_models.py` (no se importa `settings.models`) y `test_every_route_has_role.py` — 0.5 h

### Front
- [ ] T12 · `web/src/features/memberships/components/FreezeModal.tsx`: dos `Field` de fecha, texto en vivo "Son N días; la membresía terminará el 10 nov 2026" (función pura `freezePreview` en `lib/rules.ts`), mensajes en español por `error.code`, botón visible para admin y coach; `useFreezeMembership` en `api.ts` (invalida `["memberships"]` y `["members", memberId]`); Zod `freezeSchema` con `frozen_from <= frozen_to` — 3 h
- [ ] T13 · Vitest `FreezeModal.test.tsx` y `lib/rules.test.ts` (`freezePreview`): cálculo de días y fin, error por código, fechas invertidas bloquean el envío — 1 h

### DevOps
- [ ] T14 · Regenerar `docs/openapi.json` y `web/src/core/api/types.ts` — 0.5 h

### Seguridad
- [ ] T15 · Revisar: rol admin y coach, IDOR (cualquier admin o coach puede congelar cualquier membresía: es el modelo de roles de v0.1), los límites no se pueden enviar en el cuerpo (`extra="forbid"`), sin datos personales en logs — 0.5 h

## Orden de ejecución
1. T1, T2
2. T8 (rojo), T3 (verde)
3. T9 (rojo), T5, T4 (verde)
4. T6, T10 (rojo), T7 (verde)
5. T11, T14
6. T13 (rojo), T12 (verde)
7. T15

## Dependencias técnicas
- US-084 · Vender membresía: tabla `memberships`, `find_overlap`, `MembershipOut`.
- US-083 · `FreezeWindow`, `compute_status` con lista de congelaciones.
- US-058 · Parámetros de membresías: `settings.service.memberships_policy()` con `max_freeze_days_per_membership`, `max_freezes_per_membership`, `max_retroactive_days`, `expiring_days`.
- US-012 · `0001_core_schemas` con `btree_gist`.
- US-065 · Modal (front). US-091 y US-093 alojan el botón "Congelar".

## Endpoints
- `POST /api/v1/memberships/{id}/freeze` — roles: admin, coach

## Riesgos
- Rangos de los límites distintos entre US-058 (`max_freeze_days_per_membership` 1 a 180, `max_freezes_per_membership` 0 a 10) y DECISIONES N-18 (0 a 180 y 0 a 12) — impacto: con `max_freeze_days = 0` toda congelación falla con `freeze_days_exceeded`, que es el comportamiento esperado; `apply_freeze` acepta cualquier valor ≥ 0 — mitigación: los rangos los valida Settings; aquí no se duplican.
- Olvidar cargar las congelaciones en otro consumidor de `compute_status` — mitigación: `lazy="raise"` en la relación y parámetro obligatorio en `compute_status`.
- Front condicionado a D1.

## Estimación
- Backend: 12 h
- Front: 4 h
- Pruebas: 8 h
- DevOps / seguridad: 1 h
- **Total: 25 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/memberships/test_freeze_rules.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_freeze_service.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_freeze_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/memberships`
- [ ] Tras `curl -X POST /api/v1/memberships/<id>/freeze -d '{"frozen_from":"2026-10-10","frozen_to":"2026-10-19"}'`, `SELECT end_date FROM memberships.memberships WHERE id = '<id>'` = `2026-11-10` y `SELECT count(*) FROM memberships.membership_freezes WHERE membership_id = '<id>'` = 1
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.memberships --cov-fail-under=80`
