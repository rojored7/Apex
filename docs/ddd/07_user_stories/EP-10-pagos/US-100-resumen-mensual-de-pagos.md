# US-100 · Como coach o administrador quiero ver el resumen de ingresos del mes por medio de pago para cuadrar la caja sin hacer sumas a mano

- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context:** Payments (esquema `payments`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica (alimenta el tablero, US-108)
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Pagos` (`/pagos`, bloque de resumen del mes)

## Historia

Como coach o administrador
quiero ver cuánto entró en el mes, cuánto por efectivo, Nequi y Bre-B, y cuántos pagos se anularon
para cuadrar la caja del mes de un vistazo

## Contexto de dominio

- **Aggregate / entidades:** `Payment` (lectura agregada).
- **Reglas que aplica:** RN-01 (sumas enteras en COP), RN-03 (un pago anulado no suma), Q28 (el "mes" y el "hoy" son de `America/Bogota`, vía `core/clock.py`).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `payments.month_bounds_utc(month: "AAAA-MM") -> (inicio_utc, fin_utc)` (inicio del mes de Bogotá y del mes siguiente, convertidos a UTC).

## Alcance

- **Backend:** `payments.service.summary(month)` que suma `amount_cop` de pagos no anulados con `paid_at` dentro del mes de Bogotá, total por medio y número de anulados; `GET /payments/summary?month=`.
- **Front:** bloque de resumen arriba de la lista de `Pagos` con selector de mes (por defecto el mes actual de Bogotá) y `KpiCard` de total y por medio.

## Criterios de aceptación

1. `GET /api/v1/payments/summary?month=2026-10` devuelve `{ month, total_cop, by_method: { cash, nequi, breb }, voided_count, payments_count }`, todos enteros.
2. Sin `month` se usa el mes actual de `today_bogota()`; un `month` que no cumple `AAAA-MM` o con mes fuera de 01 a 12 devuelve 422 con `field = "month"`.
3. Un pago pertenece al mes si su `paid_at`, convertido a hora de Bogotá, cae dentro de ese mes: un pago con `paid_at = 2026-11-01T03:00:00Z` (31 de octubre, 22:00 en Bogotá) cuenta en octubre.
4. Los pagos anulados no suman en `total_cop` ni en `by_method` y sí cuentan en `voided_count`; `payments_count` cuenta solo los no anulados.
5. `total_cop` es exactamente la suma de `by_method` y cuadra con la suma de los pagos no anulados del mes devueltos por `GET /payments` con el mismo rango (prueba con datos de demo).
6. Un mes sin pagos devuelve ceros, no 404.
7. Rol: `require_role("admin", "coach")`; `member` recibe 403; sin token, 401.
8. El front muestra `$ 0` cuando el total es cero y el mes seleccionado en la URL.

## Escenarios BDD

```gherkin
# language: es
Característica: Resumen mensual de pagos

  Antecedentes:
    Dado que en octubre de 2026 (hora de Bogotá) hay pagos no anulados de 300000 en efectivo, 240000 por Nequi y 120000 por Bre-B
    Y un pago anulado de 120000 por Nequi
    Y que estoy autenticado como "admin"

  Escenario: Veo el resumen de octubre
    Cuando pido el resumen del mes "2026-10"
    Entonces el total es 660000
    Y el total por efectivo es 300000, por Nequi 240000 y por Bre-B 120000
    Y hay 1 pago anulado

  Escenario: Un pago de la noche del último día cuenta en ese mes
    Dado un pago de 50000 en efectivo con hora "2026-11-01T03:00:00Z"
    Cuando pido el resumen del mes "2026-10"
    Entonces el total es 710000

  Escenario: Mes con formato inválido
    Cuando pido el resumen del mes "2026-13"
    Entonces la respuesta es 422 con "field" igual a "month"

  Escenario: Mes sin pagos
    Cuando pido el resumen del mes "2025-01"
    Entonces el total es 0 y no hay pagos anulados

  Escenario: Un socio no ve el resumen de caja
    Dado que estoy autenticado como "member"
    Cuando pido el resumen del mes "2026-10"
    Entonces la respuesta es 403
```

## Endpoints

- `GET /api/v1/payments/summary?month=AAAA-MM` — rol(es): admin, coach — salida: `PaymentsSummary { month, total_cop, by_method, voided_count, payments_count }` — códigos: 200, 401, 403, 422.
- Nota de enrutamiento: la ruta `/payments/summary` se registra antes que `/payments/{id}` para no chocar con el parámetro.

## Pantalla

- `Pagos` en `/pagos`: bloque de resumen con selector de mes y `KpiCard` (estado de carga y error).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `month_bounds_utc("2026-10")` = (`2026-10-01T05:00:00Z`, `2026-11-01T05:00:00Z`); diciembre cruza de año; mes inválido levanta error.
- **Pruebas:** pura; service con base real (bordes de mes, anulados); router (422, rol); front (selector de mes).
- **Archivos principales:** `api/src/app/modules/payments/{service,router,schemas}.py`, `web/src/features/payments/components/MonthSummary.tsx`.

## Supuestos

- Supuesto: el mes de un pago se decide por `paid_at` (fecha en que se recibió el dinero), no por `created_at` (fecha de registro), convertido a hora de Bogotá.
- Supuesto: un pago registrado tarde con `paid_at` en un mes ya revisado cambia el resumen de ese mes; no hay cierre de caja mensual en v0.1.

## Dependencias

- US-095 · Registrar pago.
- US-013 · Reloj y fecha de Bogotá.

## INVEST

- **Independiente:** solo lectura agregada sobre pagos.
- **Negociable:** presentación del bloque y campos extra.
- **Valiosa:** es el cuadre de caja y la fuente del KPI "ingresos del mes".
- **Estimable:** una consulta agregada y una función pura.
- **Pequeña:** dos días.
- **Testeable:** bordes de mes con casos concretos.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
