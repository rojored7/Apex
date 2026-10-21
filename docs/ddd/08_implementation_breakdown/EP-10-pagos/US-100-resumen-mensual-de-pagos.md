# US-100 · Resumen mensual de pagos — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-10-pagos/US-100-resumen-mensual-de-pagos.md`
- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context / módulo:** Payments (`api/src/app/modules/payments/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El criterio del mes (por `paid_at` convertido a hora de Bogotá) y la ausencia de cierre de caja están decididos en DECISIONES N-27 y Q28. Contrato, bordes de mes y roles están definidos con ejemplos concretos.

## Resumen

Agrega la función pura `month_bounds_utc(month)` y `payments.service.summary(month)`, que suma `amount_cop` de pagos no anulados con `paid_at` dentro del mes de Bogotá, total por medio, número de pagos vigentes y de anulados, más `GET /payments/summary?month=` (admin y coach). Es la fuente del KPI "ingresos del mes" del tablero (US-108). En el front, el bloque de resumen con selector de mes y `KpiCard`.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md. Los supuestos "mes por `paid_at` en Bogotá" y "sin cierre de caja" quedan aceptados por DECISIONES N-27 (el cierre de mes se anota como mejora v1.1). El "mes actual" sale de `today_bogota()`: DECISIONES Q28.

## Validación contra el dominio

- Lectura agregada del aggregate `Payment`. RN-01 (sumas enteras), RN-03 (los anulados no suman).
- Funciones puras: `month_bounds_utc(month: str) -> tuple[datetime, datetime]` (inicio del mes y del mes siguiente en `America/Bogota`, convertidos a UTC; Bogotá no tiene horario de verano, pero se usa `zoneinfo` y no un desfase fijo), `parse_month(value: str) -> tuple[int, int]` (formato `AAAA-MM`, mes de 01 a 12). Coincide con la historia.
- Eventos: ninguno.

## Validación contra la arquitectura

- Módulo dueño: `payments`. Sin llamadas a otros services (la suma es sobre su propia tabla).
- `core/clock.py` aporta `today_bogota()` y la constante de zona `BOGOTA`; no se modifica `core`.
- Contrato para el tablero: `payments.service.summary(session, month: str | None) -> PaymentsSummary`, el mismo que consume `dashboard.service` (composición de lectura permitida).
- Rol `require_role("admin", "coach")`. La ruta `/payments/summary` se registra antes de `/payments/{id}`.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (usa `ix_payments_paid_at` de `0010_payments`).

### Models
- No aplica.

### Service
- [ ] T1 · Funciones puras `parse_month` y `month_bounds_utc` en `payments/service.py`, con `InvalidMonth` (422 `field="month"`) en `exceptions.py` — 1 h
- [ ] T2 · `async def summary(session, month: str | None) -> PaymentsSummary`: `month = month or today_bogota().strftime("%Y-%m")`; una sola consulta con `SUM(amount_cop) FILTER (WHERE NOT voided)`, `SUM(...) FILTER (WHERE NOT voided AND method = 'cash')` (y `nequi`, `breb`), `COUNT(*) FILTER (WHERE NOT voided)`, `COUNT(*) FILTER (WHERE voided)` sobre `paid_at >= :start AND paid_at < :end`; `COALESCE` a 0; resultado entero — 1,5 h

### Schemas
- [ ] T3 · `PaymentsSummary { month: str, total_cop: int, by_method: { cash: int, nequi: int, breb: int }, voided_count: int, payments_count: int }` y query `month: str | None` con patrón `^\d{4}-\d{2}$` — 0,5 h

### Router
- [ ] T4 · `GET /payments/summary` registrado antes de `/payments/{id}`, `Depends(require_role("admin", "coach"))`; códigos 200, 401, 403, 422 — 0,5 h

### Tests unitarios puros
- [ ] T5 · `api/tests/payments/test_month_bounds.py`: `month_bounds_utc("2026-10")` = (`2026-10-01T05:00:00Z`, `2026-11-01T05:00:00Z`); diciembre cruza de año (`2026-12` → `2027-01-01T05:00:00Z`); `2026-13`, `2026-1`, `26-10`, `abcd-ef` levantan `InvalidMonth` — 1 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/payments/test_summary.py` con los datos del escenario (300.000 efectivo, 240.000 Nequi, 120.000 Bre-B y un anulado de 120.000 Nequi): total 660.000, por medio exacto, `voided_count = 1`, `payments_count = 3`; pago `2026-11-01T03:00:00Z` cuenta en octubre (710.000); pago `2026-11-01T05:00:00Z` cuenta en noviembre; mes sin pagos devuelve ceros; sin `month` usa el mes de `today_bogota()` con `FrozenClock` en `2026-10-31T23:30-05:00`; `total_cop` igual a la suma de los pagos no anulados devueltos por `payments.service.list` con el mismo rango (cuadre con US-098) — 2 h

### Tests de router
- [ ] T7 · `api/tests/payments/test_router_summary.py`: 200 admin y coach, 422 `field="month"` con `2026-13`, 403 member, 401 sin token, todos los valores enteros en JSON — 1 h

### Tests de arquitectura
- No aplica: siguen verdes `test_every_route_has_role.py` y `test_no_cross_models.py`.

### Front
- [ ] T8 · `web/src/features/payments/api.ts`: `usePaymentsSummary(month)`; `web/src/features/payments/components/MonthSummary.tsx`: selector de mes (por defecto el mes actual de Bogotá, guardado en la URL como `?mes=AAAA-MM`), `KpiCard` de total y por medio con `$ 0` cuando es cero, contador de anulados, estados de carga y error; montado arriba de la lista en `PaymentsPage.tsx` — 2 h
- [ ] T9 · `web/src/features/payments/components/MonthSummary.test.tsx`: mes por defecto, cambio de mes en la URL, `$ 0` — 1 h

### DevOps
- [ ] T10 · Cerrar el E2E de US-095 en `web/tests/e2e/payments.spec.ts`: el pago Nequi registrado aparece en el resumen del mes; regenerar `docs/openapi.json` — 1 h

### Seguridad
- [ ] T11 · Revisión: rol, `month` validado antes de construir fechas, sin SQL interpolado — 0,5 h

## Orden de ejecución
1. T5 (pura en rojo)
2. T1
3. T6 (service en rojo)
4. T2
5. T3
6. T7 (router en rojo)
7. T4
8. T8, T9
9. T10
10. T11

## Dependencias técnicas
- US-095 · Registrar pago: tabla e índice `paid_at`.
- US-013 · Reloj y fecha de Bogotá: `today_bogota()`, `FrozenClock`.
- US-098 · Listar y buscar pagos: prueba de cuadre de T6.
- US-108 · Tablero (consumidor de `summary`).

## Endpoints
- `GET /api/v1/payments/summary` — roles: admin, coach

## Riesgos
- Un pago registrado tarde cambia un mes ya revisado (sin cierre de caja, N-27) — mitigación: documentado; se anota "cierre de mes" como mejora v1.1.
- Usar un desfase fijo de -5 h en lugar de `zoneinfo` funcionaría hoy pero rompería si Colombia adopta horario de verano — mitigación: `zoneinfo("America/Bogota")` en `month_bounds_utc`.
- Front condicionado a D1.

## Estimación
- Backend: 3,5 h (T1 a T4)
- Front: 2 h (T8)
- Pruebas: 5 h (T5 a T7 y T9)
- DevOps / seguridad: 1,5 h (T10, T11)
- **Total: 12 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/payments/test_month_bounds.py -q`
- [ ] `cd api && uv run pytest tests/payments/test_summary.py -q`
- [ ] `cd api && uv run pytest tests/payments/test_router_summary.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/payments/components/MonthSummary.test.tsx`
- [ ] `curl "/api/v1/payments/summary?month=2026-10"` con los datos de demo devuelve `total_cop` igual a `SELECT sum(amount_cop) FROM payments.payments WHERE NOT voided AND paid_at >= '2026-10-01T05:00Z' AND paid_at < '2026-11-01T05:00Z'`
- [ ] `curl "/api/v1/payments/summary?month=2026-13"` devuelve 422 con `field = "month"`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.payments --cov-fail-under=80`
