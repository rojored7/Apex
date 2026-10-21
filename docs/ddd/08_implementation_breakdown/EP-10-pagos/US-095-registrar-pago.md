# US-095 · Registrar pago — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-10-pagos/US-095-registrar-pago.md`
- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context / módulo:** Payments (`api/src/app/modules/payments/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

El contrato (`POST /memberships/{id}/payments`, `PaymentOut`, códigos), el esquema y la regla de activación por evento están resueltos por la historia más DECISIONES N-27, N-28 y Q5. El ciclo de imports entre `payments.service` y `memberships.service` se resuelve con el puerto `MembershipGate` que propone la brecha de US-085 (Payments no importa nada de Memberships); si el gate no aprueba esa propuesta, la alternativa es un import diferido documentado en ADR-001. La columna `member_id` que se agrega a `0010_payments` es una decisión de implementación que no cambia el contrato HTTP. (Alineado por el orquestador con la brecha de US-085: puerto `MembershipGate`.)

## Resumen

Crea el módulo `payments` completo en su primera versión: tabla `payments.payments` (migración `0010_payments`), modelo auditado, `payments.service.register(...)` que valida la membresía por `memberships.service`, guarda el pago y emite `PaymentRegistered` en la misma transacción, `payments.service.sum_not_voided(membership_id)` que usa US-086, el endpoint `POST /memberships/{id}/payments` (admin y coach) y el `SidePanel` "Registrar pago" del front con la advertencia de excedente de Q5. Es también la función que llama `memberships.service.sell` cuando viene `first_payment` (US-085).

## Correcciones aplicadas por DECISIONES.md

- La historia supone que `paid_at` no puede ser futuro (5 minutos de tolerancia) y no tiene límite hacia atrás → se implementa tal cual: aceptado por DECISIONES N-27. El mes del pago se decide por `paid_at` en Bogotá (lo usa US-100): N-27.
- La historia supone pagos sobre `pending_payment`, `active`, `expiring`, `frozen` y `expired`, y `reference` opcional en los tres medios → se implementa tal cual: aceptado por DECISIONES N-28. Solo `cancelled` se rechaza con 409.
- Pago por encima del saldo → se acepta sin saldo a favor; el front advierte y pide confirmación: DECISIONES Q5.
- `created_by` y `registered_by` cuando el pago lo crea un proceso sin usuario (importación, seed) → `SYSTEM_USER_ID` o el usuario de `--as`: corregido por DECISIONES N-15 (la historia no lo nombra; aplica a cualquier llamada no HTTP a `register`).
- Nombre de la migración: la historia dice `*_payments.py`; se usa el nombre canónico `0010_payments` de la especificación de desglose.

## Validación contra el dominio

- Aggregate `Payment` (raíz) con `membership_id`, `amount_cop` (value object `Money`, entero mayor que 0, RN-01), `method` (`cash` | `nequi` | `breb`, S8), `reference` opcional, `paid_at`, `registered_by` y las cuatro columnas de anulación. Coincide con `02_domain_model.md` 2.4.
- Se agrega `member_id` (copia inmutable del socio de la membresía en el momento del registro). No es una regla nueva: una membresía nunca cambia de socio y el pago es inmutable, así que la copia no puede quedar desactualizada. Sirve para el filtro por socio de US-098 y US-101 sin pedir a Memberships la lista de membresías, y para el sujeto del historial que propone US-106.
- RN-02: el pago nace con `voided = false`; la protección en base la cierra US-096 (`0011_payments_immutability`). En este paso se agregan los `CHECK` de coherencia de las columnas de anulación.
- RN-03: Payments no decide la activación; solo emite `PaymentRegistered(membership_id, amount_cop)`. Memberships (US-086) escucha y llama a `payments.service.sum_not_voided`.
- Mapa de contextos sección 5: Payments nunca escribe en `memberships`.
- Evento emitido: `PaymentRegistered(membership_id, amount_cop)`, dataclass congelada declarada en `payments/service.py`. Eventos consumidos: ninguno.
- Funciones puras nuevas: `validate_paid_at(paid_at, now) -> None` (levanta `PaidAtInFutureError`; tolerancia `PAID_AT_FUTURE_TOLERANCE = timedelta(minutes=5)`), `normalize_reference(value) -> str | None`. La validación de `Money` vive en `schemas.py` (`StrictInt`, `gt=0`).

## Validación contra la arquitectura

- Módulo dueño: `modules/payments` con `router.py`, `schemas.py`, `models.py`, `service.py`, `exceptions.py`.
- Llamadas service a service: `payments.service.register` consulta la membresía por el puerto `MembershipGate` que Memberships registra al importarse (`set_membership_gate`, US-085) y que devuelve `MembershipPayability(exists, cancelled, member_id)`; `payments` no importa `memberships`. `memberships.service.sell` → `payments.service.register` (S5). `memberships.service.on_payment_registered` → `payments.service.sum_not_voided`.
- Ciclo de imports: resuelto por inversión de dependencia. `payments/service.py` define `MembershipPayability`, `MembershipGate`, `set_membership_gate()` y los eventos `PaymentRegistered`/`PaymentVoided`; `register` falla cerrado si no hay gate registrado. `memberships/service.py` importa `payments.service` como módulo, registra el gate y se suscribe a los eventos al importarse. (Alineado por el orquestador con la brecha de US-085: puerto `MembershipGate`.)
- Ningún import de `memberships.models` ni de `members.models` (US-022).
- Bus de criptografía: no aplica (Payments no tiene campos cifrados). Lint `banned-api`: no se usa ninguna primitiva.
- Rol: `require_role("admin", "coach")` en el endpoint.
- Auditoría: `Payment.__audited__ = True`; el hook de US-016 escribe el `insert`.
- Paginación: no aplica en esta historia (la lista es US-098).
- Fechas: `paid_at` `TIMESTAMPTZ`; el schema exige zona horaria y el service normaliza a UTC. "Ahora" sale de `core/clock.py` (`Clock.now()`), para poder congelar el reloj en pruebas.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- [ ] T1 · `0010_payments`: tabla `payments.payments` con `id UUID PK`, `membership_id UUID NOT NULL`, `member_id UUID NOT NULL`, `amount_cop BIGINT NOT NULL CHECK (amount_cop > 0)`, `method TEXT NOT NULL CHECK (method IN ('cash','nequi','breb'))`, `reference TEXT NULL CHECK (reference IS NULL OR char_length(reference) BETWEEN 1 AND 64)`, `paid_at TIMESTAMPTZ NOT NULL`, `registered_by UUID NOT NULL`, `voided BOOLEAN NOT NULL DEFAULT false`, `void_reason TEXT NULL CHECK (void_reason IS NULL OR char_length(void_reason) <= 500)`, `voided_by UUID NULL`, `voided_at TIMESTAMPTZ NULL`, columnas comunes (`created_at`, `updated_at`, `created_by`); `CHECK` de coherencia `payments_void_coherent`: `(voided = false AND void_reason IS NULL AND voided_by IS NULL AND voided_at IS NULL) OR (voided = true AND btrim(void_reason) <> '' AND voided_by IS NOT NULL AND voided_at IS NOT NULL)`; sin FK cruzada entre esquemas; índices `ix_payments_paid_at (paid_at DESC)`, `ix_payments_membership_id`, `ix_payments_member_id_paid_at (member_id, paid_at DESC)`; `downgrade` borra índices y tabla — 3 h

### Models
- [ ] T2 · `payments/models.py`: clase `Payment(CommonColumnsMixin, Base)` con `__tablename__ = "payments"`, `__table_args__ = {"schema": "payments"}` más los `CheckConstraint` de T1, `__audited__ = True`, tipos `Mapped[...]` estrictos, `method` como `Literal`/`StrEnum` `PaymentMethod`; id asignado en Python antes del flush (mixin de US-012) — 1 h

### Service
- [ ] T3 · Funciones puras en `payments/service.py`: `validate_paid_at(paid_at: datetime, now: datetime) -> None` (exige `tzinfo`, levanta `PaidAtInFutureError` si `paid_at > now + 5 min`), `normalize_reference(value: str | None) -> str | None` (recorta; vacío pasa a `None`), constante `PAID_AT_FUTURE_TOLERANCE` — 1 h
- [ ] T4 · Eventos y errores: `PaymentRegistered(DomainEvent)` con `membership_id: UUID`, `amount_cop: int` (y `PaymentVoided`, que usa US-097, declarado aquí para fijar el orden del archivo); `payments/exceptions.py` con `MembershipNotFound` (404), `MembershipCancelled` (409 `membership_cancelled`), `PaidAtInFutureError` (422 `field="paid_at"`) mapeados al envelope de US-017 — 1 h
- [ ] T5 · Caso de uso `async def register(session: AsyncSession, *, membership_id: UUID, amount_cop: int, method: PaymentMethod, reference: str | None, paid_at: datetime | None, by: UUID) -> Payment`: `target = await _gate(session, membership_id)` (error de configuración si no hay gate; 404 si `exists = False`, 409 `membership_cancelled` si `cancelled`); `paid_at = paid_at or clock.now()` y `validate_paid_at`; crea `Payment(member_id=target.member_id, registered_by=by, ...)`; `session.add` + `flush`; `await events.emit(PaymentRegistered(...), session)`; devuelve la fila — 3 h
- [ ] T6 · Lectura `async def sum_not_voided(session, membership_id: UUID) -> int` (`COALESCE(SUM(amount_cop), 0) WHERE membership_id = :id AND voided = false`), contrato que consume US-086 y US-087 — 1 h

### Schemas
- [ ] T7 · `payments/schemas.py`: `PaymentIn { amount_cop: StrictInt (gt=0, le=2**63-1), method: Literal["cash","nequi","breb"], reference: str | None (strip, max 64), paid_at: AwareDatetime | None }` (reutilizado como `first_payment` por US-085); `PaymentOut { id, membership_id, member_id, amount_cop, method, reference, paid_at, registered_by, voided, void_reason, voided_by, voided_at, created_at }`; configuración `extra="forbid"` — 1 h

### Router
- [ ] T8 · `payments/router.py`: `POST /memberships/{id}/payments` con `Depends(require_role("admin", "coach"))`, `id: UUID` en el path, cuerpo `PaymentIn`, `by = current_user.id`, respuesta 201 `PaymentOut`; códigos 201, 401, 403, 404, 409, 422; registro del router en `main.py` — 1 h

### Tests unitarios puros
- [ ] T9 · `api/tests/payments/test_rules.py`: `validate_paid_at` (ahora, ahora + 4 min 59 s, ahora + 5 min 1 s, sin zona, un año atrás aceptado) y `normalize_reference` (espacios, vacío, 64 y 65 caracteres); `PaymentIn` con montos 0, -1, 1, 120000, 120000.5, "120000", `true` — 2 h

### Tests de service con PostgreSQL
- [ ] T10 · `api/tests/payments/test_register.py`: registro feliz (fila, `registered_by`, `created_by`, `member_id` copiado, `paid_at` por defecto con `FrozenClock`); membresía inexistente; membresía `cancelled` sin fila creada; membresías `expired` y `frozen` aceptadas (N-28); evento emitido una vez con el monto; handler que lanza excepción revierte el pago; fila de auditoría `insert` en `payments` con el usuario; `sum_not_voided` con pagos vigentes y anulados (anulados insertados por SQL directo con trigger aún ausente o con la transición permitida) — 4 h

### Tests de router
- [ ] T11 · `api/tests/payments/test_router_register.py`: 201 coach y admin; 403 `member`; 401 sin token; 422 con `field` para `amount_cop`, `method`, `reference`, `paid_at`; 404 y 409 con envelope; monto devuelto como entero JSON — 2 h

### Tests de arquitectura
- [ ] T12 · `api/tests/architecture/test_payments_does_not_import_memberships.py` (compartida con US-085): `app.modules.payments` no importa `app.modules.memberships` en ningún nivel; ambos services cargan en un subproceso limpio; `test_no_cross_models.py` (US-022) sigue verde para `payments`; `test_every_route_has_role.py` cubre la ruta nueva — 1 h

### Front
- [ ] T13 · `web/src/features/payments/schemas.ts` (Zod: monto entero positivo, medio, referencia máx. 64, fecha opcional) y `web/src/features/payments/api.ts` (`useRegisterPayment(membershipId)` con TanStack Query; invalida `payments`, `payments-summary`, `memberships` y `members` al guardar) — 2 h
- [ ] T14 · `web/src/features/payments/components/RegisterPaymentPanel.tsx`: `SidePanel` con `Field` de socio (búsqueda `GET /members?q=`), selector de membresías no canceladas del socio (`GET /members/{id}/memberships`), monto, medio (etiquetas de US-056), referencia, fecha y hora local de Bogotá convertida a UTC; errores del envelope en el `Field` de `field`; prop `memberId` opcional para la preselección de US-101 — 3 h
- [ ] T15 · Advertencia de excedente Q5 en el mismo panel: saldo = `agreed_price_cop - paid_cop` de `GET /memberships/{id}` (US-091); si el monto lo supera, `ConfirmModal` "este pago supera el saldo pendiente en $ X" antes de enviar; `// DESIGN-GAP:` anotado — 1 h
- [ ] T16 · `web/src/features/payments/components/RegisterPaymentPanel.test.tsx` (Vitest + Testing Library): validación de monto, error de `field`, advertencia Q5 y confirmación, envío en UTC — 2 h

### DevOps
- [ ] T17 · Regenerar `docs/openapi.json` y los tipos `web/src/core/api/types.ts`; E2E Playwright `web/tests/e2e/payments.spec.ts` "registrar pago Nequi con referencia" (el paso "verlo en el resumen del mes" se cierra con US-100) — 1 h

### Seguridad
- [ ] T18 · Revisión: rol en el endpoint, IDOR (cualquier admin o coach puede registrar en cualquier membresía; es el comportamiento esperado), el log JSON no incluye `reference` ni montos en mensajes de error, `extra="forbid"` evita que el cliente fije `registered_by`, `voided` o `member_id` — 1 h

## Orden de ejecución
1. T9 (pruebas puras en rojo)
2. T1
3. T2
4. T3, T4
5. T10 (pruebas de service en rojo)
6. T5, T6
7. T7
8. T11 (pruebas de router en rojo)
9. T8
10. T12
11. T13, T14, T15, T16
12. T17
13. T18

## Dependencias técnicas
- US-084 / US-085 · Vender membresía y vender con primer pago: Memberships registra `membership_payability` en el puerto `MembershipGate` (devuelve `exists`, `cancelled` y `member_id`).
- US-086 · Activar por cobertura: consume `PaymentRegistered` y `sum_not_voided`; se construye en la misma iteración.
- US-085 · Vender con primer pago: llama a `register` en la misma sesión.
- US-014 · Bus de eventos transaccional: `DomainEvent`, `emit`, `subscribe`.
- US-016 · Hook de auditoría after_flush: `__audited__`.
- US-013 · Reloj y fecha de Bogotá: `Clock.now()` y `FrozenClock`.
- US-017 · Envelope de errores.
- US-034 · `current_user` y `require_role`.
- US-056 · Etiquetas de medios de pago (front).
- US-065 · Panel lateral y modal de confirmación (front).
- US-091 · `GET /memberships/{id}` con `paid_cop` (advertencia Q5).

## Endpoints
- `POST /api/v1/memberships/{id}/payments` — roles: admin, coach

## Riesgos
- Ciclo de imports `payments` ↔ `memberships`: si alguien agrega un import de `memberships` en `payments` vuelve el ciclo — mitigación: puerto `MembershipGate` y prueba T12.
- `member_id` agregado a `0010_payments` no figura en la lista canónica: si el orquestador lo rechaza, US-098, US-101 y la propuesta de US-106 deben pedir las membresías del socio a Memberships — mitigación: se informa en el resumen; la columna es aditiva y no cambia el contrato HTTP.
- Autoflush: el handler de US-086 suma pagos en la misma sesión; si el pago no se hizo `flush` antes de emitir, la suma no lo ve — mitigación: `flush` explícito antes de `emit` y prueba en T10.
- Montos enormes que desbordan `BIGINT` darían 500 — mitigación: `le=2**63-1` en el schema.
- Front condicionado a D1: si el gate no aprueba S1, T13 a T16 salen del alcance.

## Estimación
- Backend: 12 h (T1 a T8)
- Front: 6 h (T13 a T15)
- Pruebas: 11 h (T9 a T12 y T16)
- DevOps / seguridad: 2 h (T17, T18)
- **Total: 31 h**
- Desvío sobre la referencia de 5 puntos (16 a 26 h): la historia junta la primera migración del módulo, el ciclo de imports con Memberships y un panel de front con advertencia; la suma de tareas lo justifica.

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/payments/test_rules.py -q`
- [ ] `cd api && uv run pytest tests/payments/test_register.py -q`
- [ ] `cd api && uv run pytest tests/payments/test_router_register.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/payments`
- [ ] `curl -X POST /api/v1/memberships/<id>/payments -d '{"amount_cop":120000,"method":"nequi","reference":"NQ-778812"}'` con token de coach devuelve 201 y `SELECT action, table_name FROM audit.audit_log ORDER BY seq DESC LIMIT 1` devuelve `insert | payments`
- [ ] `SELECT amount_cop FROM payments.payments` devuelve enteros; un `INSERT` con `amount_cop = 0` falla por `CHECK`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.payments --cov-fail-under=80`
