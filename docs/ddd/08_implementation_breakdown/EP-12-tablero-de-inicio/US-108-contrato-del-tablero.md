# US-108 · Contrato del tablero — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-12-tablero-de-inicio/US-108-contrato-del-tablero.md`
- **Épica:** EP-12 · Tablero de inicio
- **Bounded context / módulo:** Dashboard, contexto de lectura sin esquema (`api/src/app/modules/dashboard/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El contrato de `GET /dashboard` queda cerrado por la historia y por DECISIONES.md: conteos por estado resuelto del socio (N-26), mes de ingresos en hora de Bogotá (N-27, Q28) y `pending_payment` visible (Q3). El módulo solo compone dos services existentes, una composición de lectura que el mapa de contextos permite. Las dependencias de US-092 y US-100 no quitan el READY.

## Resumen

Se crea el módulo de lectura `dashboard` con `router.py`, `schemas.py` y `service.py`, sin `models.py`. `dashboard.service.summary(today)` llama a `memberships.service.summary()` y a `payments.service.summary(month_of(today))`, y devuelve `DashboardOut` con todos los campos del contrato. Los campos de versiones futuras vienen presentes con valor `null`. `last_movements` se declara aquí como lista vacía y lo llena US-110. En el front solo se crea el hook `useDashboard()` y el esquema Zod; la presentación es de US-109 y US-110.

## Correcciones aplicadas por DECISIONES.md

- La historia supone que los conteos son de socios según su membresía vigente → se acepta tal cual y se documenta como regla del contrato: aceptado por DECISIONES N-26 (sin cambio de comportamiento).
- La historia supone que el mes de ingresos es el de `today_bogota()` → se usa `payments.month_bounds_utc` de US-100 con el mes de `today_bogota()`: aceptado por DECISIONES N-27 y Q28.
- El campo `members_pending_payment` del contrato → se mantiene porque Q3 hace visible el estado; la falta de tarjeta en el diseño queda como `DESIGN-GAP` (Q3).

## Validación contra el dominio

- No hay aggregate propio. Dashboard es Conformist de Memberships y Payments: solo lee.
- RN-06 con Q11 y Q28: el estado de cada socio lo resuelve `memberships.service` con `resolve_member_status` (US-092) usando `expiring_days` de Settings y `today_bogota()`. Dashboard no recalcula estados.
- RN-03: `payments.service.summary` ya excluye pagos anulados; Dashboard copia `total_cop` sin sumar nada.
- RN-01: `income_month_cop` es `int` en COP.
- N-26: un socio con una vigente y una futura cuenta una sola vez; lo garantiza US-092.
- No emite ni consume eventos. No hay funciones puras nuevas; `month_of(today) -> "AAAA-MM"` es un formateo trivial que se prueba junto con el service.
- Confirmado: sin discrepancias con `02_domain_model.md`.

## Validación contra la arquitectura

- Módulo dueño: `modules/dashboard` (contexto 14 del mapa). Tiene `router.py`, `schemas.py` y `service.py`. No tiene `models.py`, como prevé `05_service_design.md` sección 2.
- Llamadas service a service: `memberships.service.summary()` y `payments.service.summary(month)`. Es una composición de solo lectura de dos services, permitida para Dashboard por el mapa de contextos. No hay joins ni lectura de models ajenos.
- Eventos: ninguno.
- Bus de criptografía: no se usa. El contrato no tiene ningún campo cifrado.
- Lint banned-api: sin imports de primitivas.
- Rol: `require_role("admin", "coach")` en el endpoint.
- Paginación: no aplica (no es una lista; `last_movements` tiene tope fijo de 10 en US-110).
- Auditoría: lectura, no se audita (no es un `reveal` ni un `export`).
- Fechas: `today` sale como fecha de Bogotá (`AAAA-MM-DD`). Es una fecha de negocio, no un instante, así que es coherente con la regla de UTC en el API para instantes.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica (el módulo no tiene `models.py`; lo verifica T10).

### Service
- [ ] T1 · `dashboard/service.py`: función `month_of(today: date) -> str` (formato `AAAA-MM`) — 0,5 h
- [ ] T2 · `dashboard/service.py`: caso de uso `async def summary(session, today: date) -> DashboardOut` que llama a `memberships.service.summary(session)` y a `payments.service.summary(session, month_of(today))`, mapea `active→members_active`, `expiring→members_expiring`, `expired→members_expired`, `frozen→members_frozen`, `pending_payment→members_pending_payment`, `total_cop→income_month_cop`, deja `last_movements=[]` y los cinco campos futuros en `None` — 2 h

### Schemas
- [ ] T3 · `dashboard/schemas.py`: `DashboardOut` (Pydantic v2) con `today: date`, los cinco conteos `int`, `income_month_cop: int`, `income_month: str` (patrón `^\d{4}-\d{2}$`), `last_movements: list[MovementOut]` y `notifications_today`, `members_without_consent`, `attendance_week`, `sessions_today` y `wod_today` como `int | None` u objeto `| None` con valor `None` por defecto, serializados siempre (sin `exclude_none`); `MovementOut` vacío de contenido aquí (sus campos los define US-110: `seq`, `at`, `phrase`, `table_name`, `record_id`) — 1,5 h

### Router
- [ ] T4 · `dashboard/router.py`: `GET /dashboard` con `Depends(require_role("admin", "coach"))`, obtiene `today = today_bogota(clock)` desde la dependencia de `Clock` de `core/clock.py`; respuestas 200, 401 y 403 con el envelope de US-017; registro del router en `main.py` bajo `/api/v1` — 1 h

### Tests unitarios puros
- [ ] T5 · `api/tests/dashboard/test_pure.py`: `month_of` con `2026-10-31` → `2026-10` y `2026-12-31` → `2026-12` — 0,5 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/dashboard/test_service.py`: con datos de demo (fixture de US-111 o factory equivalente) y `FrozenClock` en 2026-10-20, los conteos son idénticos a `memberships.service.summary()` y `income_month_cop` es idéntico a `payments.service.summary("2026-10").total_cop` — 2 h
- [ ] T7 · `api/tests/dashboard/test_service.py`: borde de mes con `FrozenClock` en `2026-11-01T01:00:00Z` (20:00 del 31 de octubre en Bogotá): `income_month == "2026-10"` y un pago con `paid_at = 2026-11-01T03:00:00Z` cuenta en octubre — 1 h
- [ ] T8 · `api/tests/dashboard/test_perf.py` (marcado `slow`): 1.000 socios y 12 meses de pagos; `summary` responde en menos de 300 ms (mediana de 5 corridas) — 1,5 h

### Tests de router
- [ ] T9 · `api/tests/dashboard/test_router.py`: 200 con admin y con coach; 403 con `member`; 401 sin token; prueba de contrato que todas las llaves del criterio 1 están presentes y que las cinco futuras son `null` (no ausentes) en el JSON — 1,5 h

### Tests de arquitectura
- [ ] T10 · `api/tests/architecture/test_read_modules.py`: falla si existe `app/modules/dashboard/models.py` o si `dashboard` importa `app.modules.*.models` o `app.core.audit` models; además deben seguir verdes `test_no_cross_models.py` (US-022), `test_every_route_has_role.py` (US-035) y `test_banned_imports.py` (US-031) — 1 h

### Front
- [ ] T11 · `web/src/features/dashboard/schemas.ts`: esquema Zod `dashboardSchema` que refleja `DashboardOut` (campos futuros `nullable()`, no `optional()`) y `web/src/features/dashboard/api.ts`: hook `useDashboard()` con TanStack Query 5 (`queryKey: ["dashboard"]`, `staleTime` 60 s, refresco al volver el foco) sobre `core/api/client.ts` y los tipos generados de `docs/openapi.json` — 1 h

### DevOps
- [ ] T12 · Regenerar `docs/openapi.json` (US-021) y verificar que CI lo encuentra al día — 0,5 h

### Seguridad
- [ ] T13 · Revisión: el endpoint declara rol; `DashboardOut` no expone ningún dato personal ni cifrado; el log de la petición no incluye el cuerpo de la respuesta — 0,5 h

## Orden de ejecución

1. T5 (prueba pura, en rojo) y T1.
2. T3 (contrato).
3. T6 y T7 (en rojo), luego T2.
4. T9 (en rojo), luego T4.
5. T10 y T8.
6. T12 y T11.
7. T13.

## Dependencias técnicas

- US-092 · Resumen y consultas de estado: provee `memberships.service.summary()` con las llaves `active`, `expiring`, `expired`, `frozen` y `pending_payment` contadas por socio (N-26).
- US-100 · Resumen mensual de pagos: provee `payments.service.summary(month)` con `total_cop` y `month_bounds_utc`.
- US-013 · Reloj y fecha de Bogotá: `today_bogota()` y `FrozenClock`.
- US-034 · Dependencias `current_user` y `require_role`.
- US-017 · Envelope de errores.
- US-021 · Exportación de OpenAPI (los tipos del front).
- US-059 · Cliente API y tipos generados (front).
- US-111 · Datos de demostración (fixture para el cuadre de T6; se puede sustituir por factories si US-111 no está lista).

## Endpoints

- `GET /api/v1/dashboard` — roles: admin, coach

## Riesgos

- Que una versión futura cambie el contrato en lugar de llenar un `null`: rompe el front y los tipos generados — mitigación: la prueba de contrato de T9 fija las llaves y US-021 falla si `openapi.json` cambia sin regenerarse.
- Que `memberships.service.summary()` cuente membresías y no socios: el tablero no cuadraría con la lista de socios — mitigación: T6 compara contra el service y US-092 tiene su propia prueba de suma total.
- Latencia al crecer el tablero en v0.2 a v0.5: se suman consultas — mitigación: T8 mide desde v0.1; se mide antes de pensar en caché.
- Front condicionado a D1: si el gate no aprueba S1, T11 sale del alcance.

## Estimación

- Backend: 5 h
- Front: 1 h
- Pruebas: 8 h
- DevOps / seguridad: 1 h
- **Total: 15 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/dashboard -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/dashboard`
- [ ] `curl -s -H "Authorization: Bearer <token coach>" http://localhost/api/v1/dashboard | jq 'has("wod_today") and .wod_today == null'` devuelve `true`
- [ ] `curl -s -o /dev/null -w "%{http_code}" http://localhost/api/v1/dashboard` devuelve `401`
- [ ] `docs/openapi.json` regenerado y sin diferencias en CI
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.dashboard --cov-fail-under=80`
