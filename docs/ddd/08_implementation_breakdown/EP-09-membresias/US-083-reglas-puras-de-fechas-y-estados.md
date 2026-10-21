# US-083 · Reglas puras de fechas, estados y cobertura — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-09-membresias/US-083-reglas-puras-de-fechas-y-estados.md`
- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context / módulo:** Memberships (`api/src/app/modules/memberships/service.py`, solo funciones puras)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Las cuatro funciones están definidas con casos concretos y DECISIONES.md cierra las dudas que quedaban: `expiring_days` como parámetro (Q11), "hoy" en Bogotá calculado por el llamador (Q28), fin inclusivo con desfase 0 como "por vencer" (N-23) y congelaciones como lista de ventanas que recibe `compute_status` (N-25). No necesita tablas, endpoints ni otros módulos.

## Resumen

Implementar en `memberships/service.py` el núcleo de reglas que usan todas las demás historias de la épica: `compute_end_date`, `compute_status`, `next_start_for_renewal` e `is_covered`, más los tipos de entrada inmutables (`MembershipStatus`, `PlanTerms`, `MembershipSnapshot`, `FreezeWindow`, `PaymentLine`). Ninguna lee base, reloj ni configuración. Se prueban con `parametrize` hasta el 100 % de ramas.

## Correcciones aplicadas por DECISIONES.md

- La historia define `compute_status(membership, today, expiring_days)` y habla de "ventana de congelación" en singular → la firma es `compute_status(membership, today, expiring_days, freezes)`, donde `freezes` es la lista de ventanas de la membresía (tabla `membership_freezes`); devuelve `frozen` si alguna ventana contiene `today`: corregido por DECISIONES N-25 (y Q9/Q11 para que los límites y `expiring_days` sean parámetros).
- El supuesto "fin inclusivo" de la historia queda confirmado, y el día `end_date` cuenta como `expiring` (desfase 0): aceptado por DECISIONES N-23.
- `today` siempre lo calcula el llamador con `core.clock.today_bogota()` (o `to_bogota_date(event.occurred_at)` en los handlers): DECISIONES Q28.

## Validación contra el dominio

- Aggregate `Membership` (`02_domain_model.md` 2.3): las funciones trabajan sobre una instantánea inmutable (`MembershipSnapshot`), no sobre el modelo SQLAlchemy, para que sean puras y no arrastren la sesión.
- Value objects: `DateRange` queda implícito en `MembershipSnapshot` (`start_date <= end_date`, validado en `__post_init__`); `FreezeWindow(frozen_from, frozen_to)` con `frozen_from <= frozen_to` y propiedad `days = (frozen_to - frozen_from).days + 1` (RN-07).
- RN-05: `compute_end_date = start_date + duration_days` para ambos tipos de plan (P2: los planes por clases también tienen vigencia).
- RN-06 corregida por Q11: orden `cancelled` → `pending_payment` → `frozen` → `expired` → `expiring` → `active`. Coincide con el criterio 2 de la historia.
- RN-03: cobertura con pagos no anulados, `>=` al precio pactado; Q5 confirma que un excedente no es error.
- Q1: `next_start_for_renewal` devuelve `end_date + 1` si la vigente no venció; `today` si venció o no hay.
- Q4: la rama `classes_remaining == 0 → expired` se implementa y prueba aunque en v0.1 nada descuente clases.
- Eventos: ninguno (funciones puras). Sin discrepancias con el dominio una vez aplicadas N-23 y N-25.

## Validación contra la arquitectura

- Módulo dueño: `memberships`. Las funciones viven en `service.py` (regla de módulos 1 de `CLAUDE.md`: lógica de negocio solo en `service.py`).
- Sin llamadas a otros services, sin eventos, sin bus de criptografía, sin primitivas prohibidas (`banned-api` no aplica).
- No se importa `datetime.now()` ni `date.today()` (prueba de arquitectura de US-013 sigue verde).
- Los tipos de entrada son `@dataclass(frozen=True, slots=True)`: inmutabilidad exigida por las reglas globales de estilo.
- Sin endpoints: no hay rol, paginación ni auditoría que validar.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Tipos puros en `memberships/service.py`: `class MembershipStatus(StrEnum)` con `pending_payment`, `active`, `expiring`, `expired`, `frozen`, `cancelled`; `PlanTerms(kind: Literal["days","classes"], duration_days: int, class_count: int | None)`; `MembershipSnapshot(status, start_date, end_date, classes_remaining: int | None)` con validación `start_date <= end_date`; `FreezeWindow(frozen_from, frozen_to)` con `days` y `contains(day) -> bool`; `PaymentLine(amount_cop: int, voided: bool)` — 1.5 h
- [ ] T2 · `compute_end_date(start_date: date, plan: PlanTerms) -> date` (`start_date + timedelta(days=plan.duration_days)`) — 0.5 h
- [ ] T3 · `compute_status(membership: MembershipSnapshot, today: date, expiring_days: int, freezes: Sequence[FreezeWindow]) -> MembershipStatus` con el orden de RN-06/Q11 y N-25 (`frozen` si `any(f.contains(today))`); rechaza `expiring_days < 0` con `ValueError` — 1.5 h
- [ ] T4 · `next_start_for_renewal(current: MembershipSnapshot | None, today: date) -> date` — 0.5 h
- [ ] T5 · `paid_total(payments: Iterable[PaymentLine]) -> int`, `covers(agreed_price_cop: int, paid_cop: int) -> bool` e `is_covered(agreed_price_cop: int, payments: Iterable[PaymentLine]) -> bool` (= `covers(agreed, paid_total(payments))`); `covers` queda expuesta porque US-086 y US-087 reciben el total ya sumado de `payments.service.sum_not_voided` — 1 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T6 · `api/tests/memberships/test_rules.py::test_compute_end_date` parametrizado: días 30 (2026-10-01 → 2026-10-31), clases 60 días (→ 2026-11-30), fin de mes, año bisiesto (2028-02-01 + 30 → 2028-03-02) — 1 h
- [ ] T7 · `test_compute_status` parametrizado: fronteras con `expiring_days` 0, 3 y 7 (2026-10-23 `active`, 2026-10-24 `expiring`, 2026-10-31 `expiring`, 2026-11-01 `expired`), `pending_payment` en fecha pasada, `cancelled` en cualquier fecha, `classes_remaining = 0`, una ventana que contiene `today`, ventana que no lo contiene, dos ventanas (solo la segunda contiene), membresía futura `active` con `start_date > today`, `expiring_days` negativo → `ValueError` — 2 h
- [ ] T8 · `test_next_start_for_renewal`: vigente sin vencer (2026-10-28 → 2026-11-01), vencida (→ hoy), `None` (→ hoy), frontera `today == end_date` (→ `end_date + 1`) — 0.5 h
- [ ] T9 · `test_is_covered`: igual, menor, mayor (Q5), todos anulados, lista vacía, montos enteros; `test_value_objects`: `FreezeWindow` invertida y `MembershipSnapshot` con fechas invertidas lanzan `ValueError`; asignar atributo lanza `FrozenInstanceError` — 0.75 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T10 · Confirmar que siguen verdes `api/tests/architecture/test_banned_imports.py` y la prueba de reloj de US-013 (ningún `date.today()` en `memberships`); no se crea prueba nueva — 0.25 h

### Front
- No aplica.

### DevOps
- [ ] T11 · Marcar `api/tests/memberships/test_rules.py` con el umbral de 100 % de ramas para `app.modules.memberships.service` en la tarea de CI de reglas puras (`--cov-branch`) — 0.5 h

### Seguridad
- No aplica (sin entrada externa ni datos personales; la validación de tipos protege a los llamadores).

## Orden de ejecución
1. T6, T7, T8, T9 (pruebas primero, en rojo)
2. T1
3. T2, T3, T4, T5 (hasta verde)
4. T10
5. T11

## Dependencias técnicas
- US-013 · Reloj y fecha de Bogotá: los llamadores obtienen `today` con `today_bogota()`; estas funciones no lo importan.

## Endpoints
- Ninguno.

## Riesgos
- Que otra historia lea el estado sin pasar `freezes`: un congelado se vería `active` — mitigación: la lista es parámetro obligatorio (sin valor por defecto) y mypy lo exige.
- Diferencia de interpretación entre "fin inclusivo" y el número de días vendidos (30 días producen 31 días de acceso): decisión aceptada por N-23 — mitigación: los textos del front dicen "hasta el 31 oct 2026", nunca "30 días".

## Estimación
- Backend: 5 h
- Front: 0 h
- Pruebas: 4.5 h
- DevOps / seguridad: 0.5 h
- **Total: 10 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/memberships/test_rules.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run pytest tests/memberships/test_rules.py --cov=app.modules.memberships.service --cov-branch` reporta 100 % de ramas en las cuatro funciones
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.memberships --cov-fail-under=80`
