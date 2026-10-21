# US-099 · Como coach o administrador quiero ver el detalle de un pago para confirmar sus datos y, si fue anulado, quién lo anuló y por qué

- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context:** Payments (esquema `payments`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 1
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Pagos` (`/pagos`, modal de detalle)

## Historia

Como coach o administrador
quiero abrir el detalle de un pago
para ver monto, medio, referencia, fecha, socio, membresía, quién lo registró y los datos de anulación si los hay

## Contexto de dominio

- **Aggregate / entidades:** `Payment` (lectura).
- **Reglas que aplica:** RN-01, RN-02 (el detalle no ofrece editar), fechas UTC en API.
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** ninguna.

## Alcance

- **Backend:** `payments.service.get(id)` y `GET /payments/{id}`.
- **Front:** modal de detalle al hacer clic en una fila de `Pagos`; sin botón de editar; acción "Anular" solo para admin (la implementa US-097).

## Criterios de aceptación

1. `GET /api/v1/payments/{id}` devuelve 200 con `id`, `membership_id`, `member_id`, nombre del socio, plan, `amount_cop` entero, `method`, `reference`, `paid_at` en UTC, `registered_by` y su nombre, `voided`, `void_reason`, `voided_by` y `voided_at`.
2. Un id inexistente devuelve 404; un id que no es UUID devuelve 422.
3. El modal no muestra ninguna acción de edición ni de borrado.
4. Rol: `require_role("admin", "coach")`; `member` recibe 403; sin token, 401.

## Escenarios BDD

```gherkin
# language: es
Característica: Ver el detalle de un pago

  Escenario: Veo el detalle de un pago anulado
    Dado que estoy autenticado como "coach"
    Y un pago de 120000 por "nequi" anulado con motivo "Se registró dos veces"
    Cuando abro su detalle
    Entonces veo el monto "$ 120.000", el medio "Nequi", la referencia y la fecha en hora de Bogotá
    Y veo el motivo de anulación, quién lo anuló y cuándo
    Y no veo ningún botón de editar ni borrar

  Escenario: Id inválido
    Dado que estoy autenticado como "admin"
    Cuando pido el pago "no-es-uuid"
    Entonces la respuesta es 422

  Escenario: Pago inexistente
    Dado que estoy autenticado como "admin"
    Cuando pido un pago con un UUID que no existe
    Entonces la respuesta es 404

  Escenario: Un socio no ve pagos por esta ruta
    Dado que estoy autenticado como "member"
    Cuando pido el detalle de cualquier pago
    Entonces la respuesta es 403
```

## Endpoints

- `GET /api/v1/payments/{id}` — rol(es): admin, coach — salida: `PaymentDetail` — códigos: 200, 401, 403, 404, 422.

## Pantalla

- `Pagos` en `/pagos`: modal de detalle con carga y error; etiqueta `StatusTag` "Anulado" con texto, no solo color.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** router (200, 404, 422, 403); front (modal sin acciones de edición).
- **Archivos principales:** `api/src/app/modules/payments/{service,router,schemas}.py`, `web/src/features/payments/components/PaymentDetailModal.tsx`.

## Supuestos

- Ninguno.

## Dependencias

- US-098 · Listar y buscar pagos (desde donde se abre el modal).

## INVEST

- **Independiente:** lectura simple.
- **Negociable:** campos visibles del modal.
- **Valiosa:** responde dudas de caja en un clic.
- **Estimable:** un endpoint y un modal.
- **Pequeña:** menos de un día.
- **Testeable:** cuatro respuestas probadas.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
