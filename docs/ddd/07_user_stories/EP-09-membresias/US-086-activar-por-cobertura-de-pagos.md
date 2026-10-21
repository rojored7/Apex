# US-086 · Como administrador o coach quiero que la membresía se active sola cuando los pagos cubren el precio pactado para no tener que cambiar estados a mano

- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context:** Memberships (esquema `memberships`), reacción a eventos de Payments
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (efecto visible en `Membresias`, `Socios_Lista` y la ficha)

## Historia

Como administrador o coach
quiero que, al registrar un pago que completa el precio pactado, la membresía pase sola a activa
para que el estado refleje siempre la plata recibida

## Contexto de dominio

- **Aggregate / entidades:** `Membership`.
- **Reglas que aplica:** RN-03 (activa si la suma de pagos no anulados es mayor o igual a `agreed_price_cop`), RN-06/Q11 (el estado tras activar lo decide `compute_status`, puede ser `expiring` si faltan pocos días), mapa de contextos 5 (Payments nunca cambia el estado de una membresía; solo Memberships reacciona).
- **Eventos que emite:** `MembershipActivated`
- **Eventos que consume:** `PaymentRegistered(membership_id, amount_cop)`
- **Funciones puras:** `is_covered`, `compute_status`

## Alcance

- **Backend:** handler `memberships.service.on_payment_registered` suscrito con `core.events.subscribe`; pide los pagos de la membresía a `payments.service.list_for_membership(membership_id)` (no a sus models), evalúa `is_covered` y, si la membresía está en `pending_payment` y queda cubierta, la pasa al estado que dé `compute_status(..., today_bogota(), expiring_days)` con base activa.
- **Front:** No aplica (las listas y la ficha se refrescan al invalidar las consultas de TanStack Query tras registrar el pago).

## Criterios de aceptación

1. Con una membresía `pending_payment` de precio 120.000 y un pago previo de 60.000, registrar otro de 60.000 la pasa a `active` en la misma transacción del pago y emite `MembershipActivated` una vez.
2. Si al activarse faltan `expiring_days` días o menos para `end_date`, el estado resultante es `expiring` (y se emite igualmente `MembershipActivated`).
3. Un pago que no completa el precio deja la membresía en `pending_payment` sin emitir eventos.
4. Un pago sobre una membresía ya `active`, `expiring` o `frozen` no cambia su estado ni emite `MembershipActivated` de nuevo.
5. Los pagos anulados no suman (`is_covered`).
6. Si el handler falla, el pago tampoco queda registrado (misma transacción, `02_domain_model.md` 3).
7. El cambio de estado deja fila de auditoría `update` en `memberships` con `status` antes y después y el usuario que registró el pago.
8. Prueba de arquitectura: `payments` no importa nada de `memberships`; la activación ocurre solo por el evento.

## Escenarios BDD

```gherkin
# language: es
Característica: Activación por cobertura

  Antecedentes:
    Dado que hoy en Bogotá es 2026-10-05
    Y "Laura Gómez" tiene una membresía "Mensual" en "pending_payment" de 120000 del 2026-10-01 al 2026-10-31
    Y ya tiene un pago no anulado de 60000

  Escenario: El segundo pago completa y activa
    Cuando se registra un pago de 60000 en "cash"
    Entonces la membresía queda "active"
    Y se emite "MembershipActivated" una sola vez

  Escenario: Activación cerca del fin queda por vencer
    Dado que hoy en Bogotá es 2026-10-27
    Cuando se registra un pago de 60000 en "cash"
    Entonces la membresía queda "expiring"

  Escenario: Pago insuficiente no activa
    Cuando se registra un pago de 20000 en "cash"
    Entonces la membresía sigue "pending_payment"
    Y no se emite ningún evento de membresía

  Escenario: Un pago anulado no cuenta
    Dado que el pago de 60000 fue anulado
    Cuando se registra un pago de 60000 en "cash"
    Entonces la membresía sigue "pending_payment"

  Escenario: Falla del handler revierte el pago
    Dado que la activación falla por un error interno
    Cuando se registra un pago de 60000 en "cash"
    Entonces no queda registrado el pago
    Y la membresía sigue "pending_payment"
```

## Endpoints

- Ninguno propio. Se dispara desde `POST /api/v1/memberships/{id}/payments` (US-095) y `POST /api/v1/members/{id}/memberships` con `first_payment` (US-085).

## Pantalla

- Ninguna propia; el `StatusTag` de `Membresias` y `Socios_Lista` muestra "Al día" o "Por vencer" tras refrescar.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no.
- **Funciones puras a probar:** `is_covered` y `compute_status` con fecha cercana al fin.
- **Pruebas:** service con base real a través del bus de eventos (registro de handler al importar el módulo); prueba de reversión; arquitectura.
- **Archivos principales:** `api/src/app/modules/memberships/service.py`, `api/src/app/modules/payments/service.py` (`list_for_membership`).

## Supuestos

- Supuesto: `payments.service` expone `list_for_membership(membership_id)` (o un `sum_not_voided(membership_id)`) para que Memberships calcule la cobertura sin leer tablas ajenas; no está nombrado en `05_service_design.md`.

## Dependencias

- US-084 · Vender membresía
- US-095 · Registrar pago (emisión de `PaymentRegistered`)
- US-095 debe exponer payments.service.sum_not_voided(membership_id) (lectura que usa is_covered; agregado en consolidación)

## INVEST

- **Independiente:** un handler sobre dos piezas ya existentes.
- **Negociable:** si la suma la da `payments` o se calcula en `memberships`.
- **Valiosa:** el estado de cobro es automático (RN-03).
- **Estimable:** un handler y sus pruebas.
- **Pequeña:** dos días.
- **Testeable:** transición exacta por monto.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y bordes (sin endpoint propio: el rol lo cubre US-095)
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Prueba de arquitectura de dependencias Payments → Memberships en verde
- [ ] Auditoría verificada para `memberships`
- [ ] Revisión de PR aprobada
