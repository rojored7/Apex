# US-085 · Vender con primer pago — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-09-membresias/US-085-vender-con-primer-pago.md`
- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context / módulo:** Memberships (`api/src/app/modules/memberships/`) con llamada a Payments (`api/src/app/modules/payments/service.py`) en la misma transacción
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**ARCHITECTURAL_GAP_DETECTED**

S5 obliga a que `memberships.service.sell` llame a `payments.service.register` en la misma sesión, y US-095 hace que `payments.service.register` valide la membresía llamando a `memberships.service`. Además US-086 y US-087 hacen que `memberships.service` importe `payments.service` (eventos `PaymentRegistered`/`PaymentVoided` y `sum_not_voided`). Eso es un ciclo de imports entre services que ni `CLAUDE.md` ni `04_architecture_decision.md` ni `05_service_design.md` resuelven, y US-086 (criterio 8) prohíbe que `payments` importe algo de `memberships`. Abajo va la propuesta concreta para cerrarlo; aprobada esa propuesta, la historia queda lista sin más cambios de alcance.

## Resumen

Agregar la rama `first_payment` a `sell`: tras crear la membresía (US-084) llama a `payments.service.register(...)` en la misma sesión; el `PaymentRegistered` que emite Payments lo atiende el handler de US-086, que activa la membresía si cubre el precio, y la respuesta 201 ya trae el estado final y `first_payment_id`. Si algo falla, no queda ni membresía ni pago ni auditoría. En el front, sección "Primer pago" de `SellPage` con la advertencia de excedente de Q5. Incluye el cierre del ciclo entre services con un puerto inyectado y dos pruebas de arquitectura.

## Correcciones aplicadas por DECISIONES.md

- Ninguna sobre el comportamiento; la historia ya es coherente con DECISIONES.md (Q5 permite el excedente sin saldo a favor; N-27 fija `paid_at` opcional, no futuro con 5 minutos de tolerancia; N-28 deja `reference` opcional en los tres medios).
- Precisión de contrato: la validación semántica de `paid_at` (futuro) la hace `payments.service.register` (N-27) y Memberships solo antepone `first_payment.` al `field` del error.

## Validación contra el dominio

- Dos aggregates distintos (`Membership` y `Payment`) en una transacción: es exactamente S5 y la operación de dominio `sell(member_id, plan_id, start_date, first_payment?)` de `02_domain_model.md` 2.3.
- RN-02: el pago nace inmutable (tabla y trigger de US-095/US-096); Memberships nunca escribe en `payments`.
- RN-03: la activación la decide Memberships por el evento `PaymentRegistered` (US-086), no `sell` directamente; `sell` no cambia el estado a mano.
- RN-01 y S8: `amount_cop` entero > 0; `method` en `cash`, `nequi`, `breb`.
- Q5: un pago mayor que el precio activa y no genera crédito.
- Eventos: emite `MembershipSold` (US-084); Payments emite `PaymentRegistered`; Memberships, vía handler, `MembershipActivated` si cubre.
- Sin discrepancias con el dominio.

## Validación contra la arquitectura

- Dependencia Memberships → Payments: es la "única dependencia de Memberships hacia Payments" del mapa de contextos (2) y existe para S5. Correcta.
- Dependencia Payments → Memberships: el mapa de contextos la describe como Customer/Supplier ("Payments valida que la membresía exista y no esté cancelada"), pero en código produce el ciclo descrito en la sección siguiente.
- No es un encadenamiento de tres services de escritura: escriben `memberships` y `payments`; `members`, `plans` y `settings` solo se leen para validar (US-084).
- Sin bus de criptografía ni primitivas; `banned-api` no aplica.
- Rol `require_role("admin", "coach")`, igual a US-084. Auditoría: `memberships.memberships` y `payments.payments` con `__audited__ = True`; las dos filas comparten transacción.
- Los services se pasan DTOs (`PaymentView`, `MembershipView`), nunca instancias ORM ajenas.

## Preguntas abiertas

Brecha: ciclo de imports `memberships.service` ↔ `payments.service` sin solución documentada.

- Qué falta: un patrón aprobado para que Payments valide una membresía sin importar `memberships`. Hoy, con imports de módulo en ambos sentidos, Python carga uno de los dos parcialmente y `subscribe(PaymentRegistered, ...)` o `from ... import` falla según el orden de arranque; además US-086 (criterio 8) exige que `payments` no importe nada de `memberships`.
- Propuesta (inyección del validador, elegida): Payments define el puerto que necesita y Memberships lo registra al importarse, igual que se registran los handlers de eventos (US-014).
  - En `payments/service.py`: `@dataclass(frozen=True, slots=True) class MembershipPayability: exists: bool; cancelled: bool; member_id: UUID | None` (el `member_id` lo usa US-095 para copiarlo en `payments.member_id`); `MembershipGate = Callable[[AsyncSession, UUID], Awaitable[MembershipPayability]]`; `set_membership_gate(gate: MembershipGate) -> None`; `register` llama al gate y responde 404 si `exists = False` y 409 `membership_cancelled` si `cancelled = True`; si el gate no está registrado lanza un error de configuración (falla cerrado, nunca registra un pago sin validar).
  - En `memberships/service.py`, al importar: `payments_service.set_membership_gate(membership_payability)`; `membership_payability(session, id)` lee la fila propia con `SELECT ... FOR UPDATE` (serializa pagos y anulación concurrentes sobre la misma membresía).
  - Grafo resultante: `memberships.service` importa `payments.service` (arriba del archivo, sin imports perezosos); `payments` no importa nada de `memberships`. Sin ciclo.
  - Pruebas de arquitectura: `api/tests/architecture/test_payments_does_not_import_memberships.py` (AST: ningún archivo de `app/modules/payments/` importa `app.modules.memberships`) y `api/tests/architecture/test_service_import_graph.py` (el grafo de imports de nivel superior entre `app.modules.*.service` es acíclico). Una prueba de arranque verifica que tras `create_app()` (y en `worker/main.py` y `cli.py`) el gate está registrado.
  - Documentación: sección "Dependencia inversa entre services por puerto inyectado" en `docs/adr/ADR-001-monolito-modular.md` (US-119), como excepción justificada a la regla 5 de módulos (la interfaz existe para romper el ciclo y para aislar las pruebas de Payments con un doble).
  - Impacto en otra épica: US-095 cambia "pide a `memberships.service.get(membership_id)`" por "usa el `MembershipGate` registrado"; los códigos de respuesta (404, 409 `membership_cancelled`) no cambian.
- Alternativa descartada 1 (import perezoso en `payments.service.register`): deja a `payments` importando `memberships`, contra el criterio 8 de US-086, y esconde la dependencia a mypy y al análisis estático.
- Alternativa descartada 2 (validar por evento): `register` necesita la respuesta en el acto para devolver 404/409 y no registrar el pago; un evento no devuelve valor.
- Decisión que se pide al orquestador: aprobar la inyección del validador y su reflejo en US-095. Alternativa por defecto si no se aprueba: import perezoso dentro de `payments.service.register`, documentado en ADR-001, y corregir el criterio 8 de US-086 a "payments no importa `memberships.models`".

## Tareas

### Migración Alembic
- No aplica (usa `0010_payments` de US-095).

### Models
- No aplica.

### Service
- [ ] T1 · Rama `first_payment` de `memberships.service.sell`: después del `flush` y de `emit(MembershipSold)`, `payment = await payments_service.register(session, membership_id=row.id, amount_cop=..., method=..., reference=..., paid_at=..., by=by, clock=clock)`; captura `payments_service.PaymentValidationError` y la relanza con `field = "first_payment." + err.field`; no captura nada más (cualquier otro error revierte la transacción de la petición); devuelve `SaleResult(membership=_to_view(row, ...), first_payment_id=payment.id)` leyendo el estado ya actualizado por el handler de US-086 (misma identidad en la sesión) — 2.5 h
- [ ] T2 · `membership_payability(session, membership_id) -> MembershipPayability` con `SELECT ... FOR UPDATE` sobre `memberships.memberships` y registro `payments_service.set_membership_gate(membership_payability)` al importar `memberships/service.py` — 1 h
- [ ] T3 · Función pura `prefix_field(prefix: str, field: str | None) -> str | None` para el mapeo de errores — 0.5 h

### Schemas
- [ ] T4 · `FirstPaymentIn` en `memberships/schemas.py` (propio del módulo, sin importar `payments.schemas`): `amount_cop: StrictInt` con `gt=0`, `method: Literal["cash", "nequi", "breb"]`, `reference: str | None` recortada, máximo 64, `paid_at: AwareDatetime | None`; `extra="forbid"`; `SellMembershipOut.first_payment_id` ya existe desde US-084 — 1 h

### Router
- No aplica (el endpoint de US-084 no cambia de firma; solo se habilita el campo).

### Tests unitarios puros
- [ ] T5 · `api/tests/memberships/test_rules.py::test_prefix_field` y validación de `FirstPaymentIn` con 0, −1, 1, 120000, 120000.5, `"120000"` y `method = "tarjeta"` — 0.5 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/memberships/test_sell_with_payment_service.py`: pago igual al precio → `active` en la respuesta (con el handler real de US-086); pago parcial → `pending_payment`; pago mayor (Q5) → `active` y sin filas extra; `paid_at` por defecto en UTC; atomicidad: un handler de `PaymentRegistered` de prueba que lanza deja cero filas en `memberships`, `payments` y `audit.audit_log`; un gate de prueba que lanza produce lo mismo; dos filas de auditoría `insert` (una por tabla) con el mismo `user_id`; `registered_by` igual al usuario — 3 h

### Tests de router
- [ ] T7 · `api/tests/memberships/test_sell_router.py` (casos nuevos): 201 con `first_payment_id`; 422 con `field = "first_payment.amount_cop"` (decimal, cero) y `"first_payment.method"`; 422 `first_payment.paid_at` en el futuro; 403 `member`; 401 — 1.5 h

### Tests de arquitectura
- [ ] T8 · `api/tests/architecture/test_payments_does_not_import_memberships.py`, `api/tests/architecture/test_service_import_graph.py` y `api/tests/architecture/test_gates_registered.py` (tras `create_app()` el gate está registrado; `payments.service.register` sin gate falla cerrado) — 2 h

### Front
- [ ] T9 · `web/src/features/memberships/components/FirstPaymentSection.tsx`: sección plegable con monto precargado con el precio pactado, medio con las etiquetas de US-056, referencia visible para Nequi y Bre-B, fecha y hora del pago (por defecto ahora, enviada en UTC); botón "Vender y cobrar"; errores por `error.field` con prefijo `first_payment.`; Zod `firstPaymentSchema` en `schemas.ts` (entero > 0) — 3 h
- [ ] T10 · Advertencia de Q5: si el monto supera el precio, `ConfirmModal` "Este pago supera el saldo pendiente en $ X" y solo envía al confirmar — 1 h
- [ ] T11 · Vitest `FirstPaymentSection.test.tsx` (referencia según medio, advertencia de excedente, error por campo) y E2E Playwright `web/tests/e2e/sell-with-payment.spec.ts`: vender con pago completo y ver al socio "Al día" en `/socios` (criterio de EP-09) — 3 h

### DevOps
- [ ] T12 · Regenerar `docs/openapi.json` y anotar la sección de ADR-001 descrita en "Preguntas abiertas" — 0.5 h

### Seguridad
- [ ] T13 · Revisar: el coach no puede fijar `registered_by` ni `voided` (no existen en `FirstPaymentIn`); el gate falla cerrado; montos como entero estricto; el log del error de pago no incluye datos del socio — 0.5 h

## Orden de ejecución
1. Cierre de la brecha aprobado (puerto en `payments.service`, lo implementa US-095)
2. T5 (rojo), T3, T4
3. T8 (rojo), T2 (verde)
4. T6, T7 (rojo), T1 (verde)
5. T12
6. T11 Vitest (rojo), T9, T10 (verde), E2E de T11
7. T13

## Dependencias técnicas
- US-084 · Vender membresía: `sell`, `SellMembershipOut`, endpoint.
- US-095 · Registrar pago: `payments.service.register(session, membership_id, amount_cop, method, reference, paid_at, by, clock) -> PaymentView`, `PaymentValidationError(field)`, evento `PaymentRegistered` y el puerto `set_membership_gate` de la propuesta.
- US-086 · Activar por cobertura: para que la respuesta traiga `active` cuando el pago cubre (criterio 2).
- US-096 · Inmutabilidad de pagos (trigger), sin efecto en esta rama pero parte del mismo esquema.
- US-056 · Etiquetas de medios de pago (front).
- US-065 · `ConfirmModal` (front).
- US-119 · ADR iniciales: recibe la sección del puerto inyectado.

## Endpoints
- `POST /api/v1/members/{id}/memberships` — roles: admin, coach

## Riesgos
- El ciclo de imports se resuelve distinto en EP-10: si US-095 importa `memberships.service`, el arranque falla según el orden de imports — mitigación: `test_service_import_graph.py` y `test_payments_does_not_import_memberships.py` rompen CI antes de llegar a producción; coordinar con el desglose de US-095.
- El estado de la respuesta depende de que el handler de US-086 haya actualizado la misma instancia de la sesión — mitigación: el handler usa `session.get(Membership, id, with_for_update=True)`, que devuelve la instancia del mapa de identidad; prueba explícita de que la respuesta trae `active`.
- Un `paid_at` del front sin zona horaria — mitigación: `AwareDatetime` rechaza fechas ingenuas con 422.
- Front condicionado a D1.

## Estimación
- Backend: 5 h
- Front: 4 h
- Pruebas: 10 h
- DevOps / seguridad: 1 h
- **Total: 20 h**

Supera el rango de 3 puntos (10 a 15 h) por el cierre de la brecha (puerto y tres pruebas de arquitectura) y el E2E de Playwright que la épica exige en esta historia.

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/memberships/test_rules.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_sell_with_payment_service.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_sell_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/memberships`
- [ ] `cd web && npx playwright test tests/e2e/sell-with-payment.spec.ts`
- [ ] Tras una venta con pago completo por `curl`, `SELECT status FROM memberships.memberships WHERE id = '<id>'` devuelve `active` y `SELECT count(*) FROM payments.payments WHERE membership_id = '<id>'` devuelve 1
- [ ] Con un pago inválido (`amount_cop = 0`) la misma consulta no encuentra ninguna membresía nueva del socio
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.memberships --cov-fail-under=80`
