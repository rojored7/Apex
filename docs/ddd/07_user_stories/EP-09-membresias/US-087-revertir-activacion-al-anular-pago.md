# US-087 · Como administrador quiero que al anular un pago la membresía vuelva a pendiente si ya no está cubierta para que el estado nunca muestre al día a quien no pagó

- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context:** Memberships (esquema `memberships`), reacción a eventos de Payments
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (efecto visible en `Membresias`, `Socios_Lista` y la ficha)

## Historia

Como administrador
quiero que, cuando anulo un pago y la suma de los demás ya no cubre el precio pactado, la membresía vuelva a pendiente de pago
para que el error corregido no deje a un socio marcado como al día sin haber pagado

## Contexto de dominio

- **Aggregate / entidades:** `Membership`.
- **Reglas que aplica:** RN-03 (cobertura con pagos no anulados), RN-02 (el pago no se borra: se anula), `02_domain_model.md` 2.4 (si la cobertura cae y la membresía estaba activa vuelve a `pending_payment` y se emite `MembershipActivationReverted`).
- **Eventos que emite:** `MembershipActivationReverted`
- **Eventos que consume:** `PaymentVoided(membership_id, payment_id)`
- **Funciones puras:** `is_covered`

## Alcance

- **Backend:** handler `memberships.service.on_payment_voided`; recalcula `is_covered` con los pagos no anulados y, si ya no cubre y el estado es `active` o `expiring`, pasa a `pending_payment`.
- **Front:** No aplica (invalidación de consultas tras anular, US-097).

## Criterios de aceptación

1. Membresía `active` de 120.000 con un único pago de 120.000: al anular ese pago queda `pending_payment` en la misma transacción y se emite `MembershipActivationReverted` una vez.
2. Membresía `active` con pagos de 120.000 y 20.000: anular el de 20.000 no cambia el estado ni emite eventos (sigue cubierta).
3. Membresía `expiring` que deja de estar cubierta vuelve a `pending_payment`.
4. Membresías `frozen`, `expired` o `cancelled` no cambian de estado al anular un pago (supuesto).
5. Si el handler falla, la anulación del pago se revierte.
6. El cambio deja fila de auditoría `update` en `memberships` con el usuario que anuló.
7. El handler solo se dispara por el evento; el endpoint de anular sigue siendo solo admin (US-097).

## Escenarios BDD

```gherkin
# language: es
Característica: Revertir activación al anular un pago

  Antecedentes:
    Dado que hoy en Bogotá es 2026-10-10
    Y "Laura Gómez" tiene una membresía "Mensual" "active" de 120000 del 2026-10-01 al 2026-10-31

  Escenario: Anular el único pago devuelve a pendiente
    Dado que su único pago es de 120000
    Cuando el administrador anula ese pago con motivo "Pago duplicado por error"
    Entonces la membresía queda "pending_payment"
    Y se emite "MembershipActivationReverted"

  Escenario: Sigue cubierta con otros pagos
    Dado que tiene pagos de 120000 y 20000
    Cuando el administrador anula el pago de 20000 con motivo "Monto mal digitado"
    Entonces la membresía sigue "active"
    Y no se emite ningún evento de membresía

  Escenario: Membresía congelada no se revierte
    Dado que la membresía está "frozen" y su único pago es de 120000
    Cuando el administrador anula ese pago con motivo "Error"
    Entonces la membresía sigue "frozen"

  Escenario: Falla del handler revierte la anulación
    Dado que su único pago es de 120000
    Y que la reversión falla por un error interno
    Cuando el administrador anula ese pago con motivo "Error"
    Entonces el pago sigue sin anular
    Y la membresía sigue "active"
```

## Endpoints

- Ninguno propio. Se dispara desde `POST /api/v1/payments/{id}/void` (US-097, solo admin).

## Pantalla

- Ninguna propia.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no.
- **Funciones puras a probar:** `is_covered` tras anular.
- **Pruebas:** service con base real vía bus de eventos; reversión transaccional.
- **Archivos principales:** `api/src/app/modules/memberships/service.py`.

## Supuestos

- Supuesto: la reversión aplica solo a `active` y `expiring` (el dominio dice "si estaba active"; `expiring` es un active cercano al fin). Una membresía `frozen` o `expired` que deja de estar cubierta conserva su estado; queda como pregunta abierta si `frozen` también debe volver a `pending_payment`.

## Dependencias

- US-086 · Activar por cobertura de pagos
- US-097 · Anular pago (emisión de `PaymentVoided`)

## INVEST

- **Independiente:** un handler, simétrico al de US-086.
- **Negociable:** qué estados se revierten (supuesto declarado).
- **Valiosa:** evita socios "al día" sin plata.
- **Estimable:** pequeño y acotado.
- **Pequeña:** un día.
- **Testeable:** transición binaria por suma.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y bordes (rol cubierto por US-097)
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Auditoría verificada para `memberships`
- [ ] Revisión de PR aprobada
