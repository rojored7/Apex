# US-108 · Como coach o administrador quiero un tablero con un contrato estable desde v0.1 para ver los números del día en una sola llamada y que cada versión solo llene sus campos

- **Épica:** EP-12 · Tablero de inicio
- **Bounded context:** Dashboard (módulo `dashboard`, sin esquema ni `models.py`)
- **Versión:** v0.1 (crece en v0.2, v0.3, v0.4 y v0.5)
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica (frase guía del producto)
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Inicio` (`/`)

## Historia

Como coach o administrador
quiero que `GET /dashboard` me entregue en una sola respuesta los conteos de membresías y los ingresos del mes
para saber en 10 segundos quién está al día, quién vence y cuánto ha entrado

## Contexto de dominio

- **Aggregate / entidades:** ninguno propio (contexto de lectura, Conformist de Memberships y Payments).
- **Reglas que aplica:** RN-06 con Q11 y Q28 (los estados ya los calcula Memberships con `expiring_days` y `today_bogota()`), RN-01 (ingresos enteros en COP), RN-03 (los anulados no suman), Q3 (`pending_payment` visible), mapa de contextos (Dashboard solo lee por services, sin joins ni models ajenos).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** ninguna.

## Alcance

- **Backend:** `dashboard.service.summary(today)` que compone `memberships.service.summary()` y `payments.service.summary(month_of(today))`; `GET /dashboard`. Contrato con los campos de versiones futuras en `null`.
- **Front:** hook `useDashboard()` en `web/src/features/dashboard/api.ts`; la presentación la hacen US-109 y US-110.

## Criterios de aceptación

1. `GET /api/v1/dashboard` devuelve 200 con: `today` (fecha de Bogotá `AAAA-MM-DD`), `members_active`, `members_expiring`, `members_expired`, `members_frozen`, `members_pending_payment`, `income_month_cop` (entero), `income_month` (`AAAA-MM`), `last_movements` (lista, la llena US-110), y en `null`: `notifications_today` (v0.2), `members_without_consent` (v0.3), `attendance_week` (v0.4), `sessions_today` (v0.4), `wod_today` (v0.5).
2. Los conteos son exactamente los de `GET /memberships/summary` y `income_month_cop` es exactamente `total_cop` de `GET /payments/summary?month=<mes de hoy en Bogotá>` (prueba con `seed --demo` y `FrozenClock`).
3. El mes de ingresos es el de `today_bogota()`: a las 20:00 del 31 de octubre en Bogotá (01:00 UTC del 1 de noviembre) el tablero muestra octubre.
4. Los campos futuros vienen presentes con `null` (no ausentes) para que el contrato no cambie al llenarlos.
5. Rol: `require_role("admin", "coach")`; `member` recibe 403; sin token, 401.
6. Responde en menos de 300 ms con 1.000 socios y 12 meses de pagos de prueba.
7. Prueba de arquitectura: el módulo `dashboard` no tiene `models.py` ni importa `models` de otro módulo.

## Escenarios BDD

```gherkin
# language: es
Característica: Contrato del tablero de inicio

  Antecedentes:
    Dado los datos de demostración cargados
    Y que hoy es 20 de octubre de 2026 en Bogotá

  Escenario: El coach obtiene el tablero del día
    Dado que estoy autenticado como "coach"
    Cuando pido el tablero
    Entonces los conteos de membresías coinciden con el resumen de membresías
    Y los ingresos del mes coinciden con el resumen de pagos de "2026-10"
    Y "notifications_today", "attendance_week", "sessions_today" y "wod_today" vienen en null

  Escenario: Al final del día en Bogotá se sigue mostrando el mes en curso
    Dado que son las 20:00 del 31 de octubre de 2026 en Bogotá
    Cuando pido el tablero
    Entonces "income_month" es "2026-10"

  Escenario: Sin token
    Cuando pido el tablero sin autenticarme
    Entonces la respuesta es 401

  Escenario: Un socio no ve el tablero del gimnasio
    Dado que estoy autenticado como "member"
    Cuando pido el tablero
    Entonces la respuesta es 403
```

## Endpoints

- `GET /api/v1/dashboard` — rol(es): admin, coach — salida: `DashboardOut` (campos del criterio 1) — códigos: 200, 401, 403.

## Pantalla

- `Inicio` en `/`: solo provee los datos (ver US-109 y US-110).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna nueva (usa `today_bogota()` y `month_bounds_utc` de US-100).
- **Pruebas:** service con base real y `FrozenClock` (cuadre con los resúmenes, borde de mes); router (rol); arquitectura (sin `models.py`); prueba de contrato (todas las llaves presentes).
- **Archivos principales:** `api/src/app/modules/dashboard/{router,schemas,service}.py`, `web/src/features/dashboard/api.ts`.

## Supuestos

- Supuesto: los conteos son de socios según su membresía vigente (lo que devuelve `memberships.service.summary()`), no de filas de membresías; una membresía futura de renovación (Q1) no se cuenta dos veces.
- Supuesto: se agrega `members_pending_payment` al contrato por Q3; el diseño de `Inicio` no tiene tarjeta para ese estado (`DESIGN-GAP`).
- Supuesto: el campo `members_without_consent` (Q16, v0.3) se reserva desde v0.1 en `null`.

## Dependencias

- US-092 · Resumen y consultas de estado (`memberships.service.summary()`).
- US-100 · Resumen mensual de pagos (`payments.service.summary(month)`).

## INVEST

- **Independiente:** compone dos services ya existentes.
- **Negociable:** nombres de campos antes de publicar el contrato.
- **Valiosa:** es la frase guía del producto.
- **Estimable:** un service de composición y un endpoint.
- **Pequeña:** dos días.
- **Testeable:** cuadre exacto con los resúmenes.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol y envelope de error
- [ ] Prueba de arquitectura del módulo `dashboard` en verde
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
