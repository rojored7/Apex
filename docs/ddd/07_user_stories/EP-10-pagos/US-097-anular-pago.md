# US-097 · Como administrador quiero anular un pago con motivo para corregir un error de caja sin borrar el rastro del pago original

- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context:** Payments (esquema `payments`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Pagos` (`/pagos`, modal "Anular pago")

## Historia

Como administrador
quiero anular un pago escribiendo el motivo
para corregir un error de registro dejando constancia de quién lo anuló, cuándo y por qué

## Contexto de dominio

- **Aggregate / entidades:** `Payment` (columnas `voided`, `void_reason`, `voided_by`, `voided_at`).
- **Reglas que aplica:** RN-02 (se anula con motivo, una sola vez; la corrección es un pago nuevo), RN-03 (un pago anulado no suma para la cobertura), RN-15 (coach no anula), `BRECHAS.md` sección 5 (`POST /payments/{id}/void` solo admin).
- **Eventos que emite:** `PaymentVoided(membership_id, payment_id)`.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `payments.can_void(payment)`.

## Alcance

- **Backend:** `payments.service.void(id, reason, by)`: verifica `can_void`, escribe las cuatro columnas de anulación en un solo `UPDATE` y emite `PaymentVoided` en la misma transacción. La reversión de la activación la hace Memberships (US-087).
- **Front:** acción "Anular" visible solo para admin en el detalle del pago y en la fila de la lista; `ConfirmModal` con motivo obligatorio; tras anular, la fila muestra la etiqueta "Anulado" con el motivo y se ofrece "Registrar pago nuevo" con los datos precargados.

## Criterios de aceptación

1. `POST /api/v1/payments/{id}/void` con `{ reason }` no vacío tras recortar (máximo 500 caracteres) devuelve 200 con el pago con `voided = true`, `void_reason`, `voided_by` igual al admin autenticado y `voided_at` en UTC.
2. `reason` ausente, vacío o solo espacios devuelve 422 con `field = "reason"`; más de 500 caracteres también devuelve 422.
3. Un pago ya anulado devuelve 409 con `code = "payment_already_voided"` y no cambia nada.
4. Un pago inexistente devuelve 404.
5. La anulación no modifica `amount_cop`, `method`, `reference` ni `paid_at` y no borra la fila (RN-02; lo garantiza también el trigger de US-096).
6. En la misma transacción se emite `PaymentVoided(membership_id, payment_id)`; si el handler falla, la anulación se revierte.
7. Anular y registrar un pago nuevo deja dos filas: la original con motivo y autor de la anulación, y la nueva vigente.
8. La anulación deja una fila de auditoría `update` en `payments` con `before.voided = false` y `after.voided = true`.
9. Rol: `require_role("admin")`; un coach recibe 403 y el front no le muestra la acción "Anular"; sin token, 401.

## Escenarios BDD

```gherkin
# language: es
Característica: Anular un pago con motivo

  Antecedentes:
    Dado un pago de 120000 por "nequi" de "Juan Ruiz" no anulado

  Escenario: El administrador anula un pago mal registrado
    Dado que estoy autenticado como "admin"
    Cuando anulo el pago con motivo "Se registró dos veces"
    Entonces la respuesta es 200
    Y el pago queda con "voided" verdadero, el motivo, mi usuario y la hora de anulación
    Y se emite "PaymentVoided"
    Y la lista de pagos muestra el pago con la etiqueta "Anulado"

  Escenario: Corrijo el error con un pago nuevo
    Dado que estoy autenticado como "admin"
    Y que anulé el pago con motivo "Monto equivocado"
    Cuando registro un pago nuevo de 100000 por "nequi" en la misma membresía
    Entonces la membresía tiene dos pagos, uno anulado y uno vigente

  Escenario: Anular sin motivo es rechazado
    Dado que estoy autenticado como "admin"
    Cuando anulo el pago con motivo "   "
    Entonces la respuesta es 422 con "field" igual a "reason"
    Y el pago sigue sin anular

  Escenario: No se anula dos veces
    Dado que estoy autenticado como "admin"
    Y que el pago ya está anulado
    Cuando anulo el pago con motivo "otro"
    Entonces la respuesta es 409 con "code" igual a "payment_already_voided"

  Escenario: El coach no puede anular
    Dado que estoy autenticado como "coach"
    Cuando anulo el pago con motivo "error"
    Entonces la respuesta es 403
    Y en la pantalla de pagos no veo la acción "Anular"
```

## Endpoints

- `POST /api/v1/payments/{id}/void` — rol(es): admin — entrada: `{ reason: str (1 a 500, recortado) }` — salida: `PaymentOut` con columnas de anulación — códigos: 200, 401, 403, 404, 409, 422.

## Pantalla

- `Pagos` en `/pagos`: acción "Anular" en el modal de detalle y en la fila; `ConfirmModal` con campo de motivo obligatorio y texto "El pago no se borra: queda anulado con este motivo". Estado de error si el servidor responde 409 (otra persona lo anuló antes).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** depende del trigger de US-096; una anulación concurrente de dos admins produce un error del trigger en la segunda, que el service traduce a 409 (se lee la fila con `SELECT ... FOR UPDATE` antes de `can_void`).
- **Funciones puras a probar:** `can_void`.
- **Pruebas:** service con base real (anulación, doble anulación, rollback por handler fallido); router (rol admin, 403 coach, 422 motivo); front (botón oculto para coach con `useCan`, modal exige motivo).
- **Archivos principales:** `api/src/app/modules/payments/{service,router,schemas,exceptions}.py`, `web/src/features/payments/components/VoidPaymentModal.tsx`.

## Supuestos

- Supuesto: el motivo de anulación tiene un máximo de 500 caracteres.

## Dependencias

- US-096 · Inmutabilidad de pagos en la base (la transición permitida).
- US-065 · Panel lateral y modal de confirmación.

## INVEST

- **Independiente:** la reversión de la membresía (US-087) es otra historia que reacciona al evento.
- **Negociable:** textos del modal y largo del motivo.
- **Valiosa:** permite corregir errores sin perder rastro.
- **Estimable:** un endpoint, un evento y un modal.
- **Pequeña:** dos o tres días.
- **Testeable:** cada respuesta tiene prueba de router y service.

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
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `payments.payments`
- [ ] Revisión de PR aprobada
