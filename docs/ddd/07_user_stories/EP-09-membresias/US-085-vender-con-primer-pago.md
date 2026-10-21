# US-085 · Como administrador o coach quiero registrar el primer pago en la misma venta para cobrar y activar la membresía en un solo paso

- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context:** Memberships (esquema `memberships`), con llamada a Payments en la misma transacción
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Membresia_Vender` (`/membresias/vender`, sección "Primer pago")

## Historia

Como administrador o coach
quiero indicar el monto, el medio y la referencia del primer pago al vender
para que la venta y el cobro queden registrados juntos y la membresía quede al día si el pago cubre el precio

## Contexto de dominio

- **Aggregate / entidades:** `Membership` y `Payment` (aggregates distintos; la llamada `memberships.service.sell → payments.service.register` es la única dependencia de Memberships hacia Payments, `03_context_map.md` 2).
- **Reglas que aplica:** S5 (vender con primer pago es atómico), RN-01, RN-02 (el pago nace inmutable), RN-03 (activa si cubre), Q5 (un pago mayor que el saldo se permite, sin saldo a favor; el front advierte y pide confirmación), S8 (medios `cash`, `nequi`, `breb`).
- **Eventos que emite:** `MembershipSold`; Payments emite `PaymentRegistered` y, por su handler, Memberships emite `MembershipActivated` si cubre.
- **Eventos que consume:** `PaymentRegistered` (handler de US-086)
- **Funciones puras:** `is_covered`

## Alcance

- **Backend:** rama `first_payment` de `sell`: tras crear la membresía llama a `payments.service.register(membership_id, amount_cop, method, reference, paid_at, by)` dentro de la misma sesión.
- **Front:** sección "Primer pago" opcional en `SellPage` con monto (precargado con el precio pactado), medio (etiquetas de `settings.payment_methods`, US-056), referencia (visible para Nequi y Bre-B) y fecha del pago; advertencia de Q5 con confirmación cuando el monto supera el precio.

## Criterios de aceptación

1. `POST /api/v1/members/{id}/memberships` con `first_payment = { amount_cop, method, reference?, paid_at? }` crea la membresía y el pago en una sola transacción y responde 201 con `MembershipOut` y `first_payment_id`.
2. Si `amount_cop` es igual o mayor al `agreed_price_cop`, la respuesta ya trae `status = active` (o `expiring` según `compute_status`); si es menor, `pending_payment`.
3. `amount_cop` entero mayor que 0; decimales, cero o negativo devuelven 422 `field = "first_payment.amount_cop"` y no se crea ni la membresía ni el pago.
4. `method` fuera de `cash`, `nequi`, `breb` devuelve 422 `field = "first_payment.method"`.
5. `paid_at` es un timestamp con zona; por defecto `now()` en UTC; se guarda en UTC.
6. Atomicidad: si `payments.service.register` lanza (por validación o porque falla un handler), no queda membresía ni pago ni filas de auditoría (prueba con un handler que lanza).
7. Un monto mayor que el precio se acepta (Q5) sin crear saldo ni crédito; el front muestra "Este pago supera el saldo pendiente en $ X" y exige confirmar antes de enviar.
8. El pago queda auditado (`insert` en `payments`) con `registered_by` del usuario; la membresía, con su propia fila de auditoría.
9. Roles iguales a US-084: admin y coach; `member` 403; sin token 401.

## Escenarios BDD

```gherkin
# language: es
Característica: Vender con primer pago

  Antecedentes:
    Dado que hoy en Bogotá es 2026-10-01
    Y existe el plan activo "Mensual" de 120000 y 30 días
    Y el socio "Juan Rodríguez" está activo y sin membresías
    Y que estoy autenticado como coach

  Escenario: Pago completo deja la membresía al día
    Cuando vendo "Mensual" a "Juan Rodríguez" con primer pago de 120000 en "nequi" con referencia "M123456"
    Entonces la respuesta es 201
    Y la membresía queda "active" del 2026-10-01 al 2026-10-31
    Y existe un pago de 120000 en "nequi" con referencia "M123456" registrado por mí

  Escenario: Pago parcial deja la membresía pendiente
    Cuando vendo "Mensual" a "Juan Rodríguez" con primer pago de 60000 en "cash"
    Entonces la membresía queda "pending_payment"
    Y existe un pago de 60000

  Escenario: Pago mayor que el precio
    Cuando vendo "Mensual" a "Juan Rodríguez" con primer pago de 150000 en "cash" y confirmo la advertencia
    Entonces la membresía queda "active"
    Y no se registra ningún saldo a favor

  Escenario: Monto con decimales no crea nada
    Cuando vendo "Mensual" a "Juan Rodríguez" con primer pago de 120000.50 en "cash"
    Entonces la respuesta es 422
    Y el error señala el campo "first_payment.amount_cop"
    Y "Juan Rodríguez" no tiene membresías

  Escenario: Falla del registro del pago revierte la venta
    Dado que el registro de pagos falla por un error interno
    Cuando vendo "Mensual" a "Juan Rodríguez" con primer pago de 120000 en "cash"
    Entonces "Juan Rodríguez" no tiene membresías ni pagos

  Escenario: Rol socio denegado
    Dado que estoy autenticado con rol "member"
    Cuando vendo "Mensual" a "Juan Rodríguez" con primer pago de 120000 en "cash"
    Entonces la respuesta es 403
```

## Endpoints

- `POST /api/v1/members/{id}/memberships` — rol(es): admin, coach — entrada: `{ plan_id, start_date?, first_payment?: { amount_cop: int, method: "cash"|"nequi"|"breb", reference?: str, paid_at?: datetime } }` — salida: `MembershipOut` + `first_payment_id` — códigos: 201, 401, 403, 404, 409, 422.

## Pantalla

- `Membresia_Vender`: sección "Primer pago" plegable; advertencia de excedente; botón "Vender y cobrar". Estados de envío y error por campo.

## Notas técnicas

- **Migración:** no (usa la tabla de pagos de US-095).
- **Trigger / restricciones:** las de pagos (US-095, US-096).
- **Funciones puras a probar:** `is_covered` con pago igual, menor y mayor al precio.
- **Pruebas:** service con base real (atomicidad con doble de `payments.service.register` que lanza; activación en la misma respuesta); router; E2E Playwright "vender con pago completo y ver al socio Al día" (criterio de EP-09).
- **Archivos principales:** `api/src/app/modules/memberships/service.py`, `web/src/features/memberships/components/FirstPaymentSection.tsx`.

## Supuestos

- Ninguno.

## Dependencias

- US-084 · Vender membresía
- US-095 · Registrar pago (`payments.service.register`)

## INVEST

- **Independiente:** agrega una rama a una operación existente.
- **Negociable:** precarga del monto y textos de advertencia.
- **Valiosa:** recepción vende y cobra en una sola acción (S5).
- **Estimable:** una rama y una sección de formulario.
- **Pequeña:** dos a tres días.
- **Testeable:** estado resultante por monto y prueba de reversión.

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
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] E2E Playwright de venta con pago completo en verde
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `memberships` y `payments`
- [ ] Revisión de PR aprobada
