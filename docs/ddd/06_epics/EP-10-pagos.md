# EP-10 · Registro inmutable de pagos

- **Versión del plan:** v0.1 (Tarea 7, con los detalles de `BRECHAS.md` sección 2, "Detalles menores de pagos").
- **Bounded context:** Payments (negocio, esquema `payments`).
- **Estimación relativa:** M.

## Objetivo de negocio

Que cada peso que entra al gimnasio (efectivo, Nequi o Bre-B) quede registrado una sola vez, sin que nadie pueda editarlo ni borrarlo, y que un error se corrija anulando con motivo y registrando de nuevo. El dueño puede auditar la caja del mes sin depender de la memoria de nadie.

## Actores

- Administrador: registra, consulta y anula con motivo.
- Coach: registra y consulta; no anula.
- Memberships: escucha los eventos de pago para activar o revertir.

## Capacidades incluidas

### Backend
- Aggregate `Payment`: `membership_id`, `amount_cop` (`Money` mayor que 0, RN-01), `method` (`cash`, `nequi`, `breb`, S8), `reference` opcional, `paid_at`, `registered_by`, y las cuatro columnas de anulación (`voided`, `void_reason`, `voided_by`, `voided_at`); auditado.
- RN-02: trigger de PostgreSQL que rechaza todo `DELETE` y cualquier `UPDATE` que no sea la anulación, y la anulación solo una vez; además, la regla en código con `payments.can_void`.
- `register` valida que la membresía exista y no esté cancelada, y emite `PaymentRegistered`.
- `void` (solo admin, motivo obligatorio) emite `PaymentVoided`; un pago anulado no suma para RN-03.
- Payments nunca cambia el estado de una membresía directamente (mapa de contextos, sección 5).
- `list` con filtros de fecha, medio, `registered_by`, anulado o no, socio, membresía y búsqueda `q`; `get`; `summary(month)` con total, total por medio y número de anulados.
- Endpoints: `POST /memberships/{id}/payments`, `POST /payments/{id}/void` (admin), `GET /payments`, `GET /payments/{id}`, `GET /payments/summary?month=`, `GET /members/{id}/payments`.

### Front
- Pantalla de pagos con resumen del mes, filtros, registro en `SidePanel` (elige la membresía y llama al endpoint anidado), modal de detalle y modal de anular con motivo (solo admin).
- Pestaña Pagos de la ficha del socio.

## Fuera de alcance

- Recibo en PDF y exportación CSV (EP-16).
- Pasarela de pagos en línea y facturación electrónica DIAN (fuera de alcance del producto).
- Medios de pago adicionales (S8).

## Criterios de éxito medibles

- Un `UPDATE` directo sobre un pago falla en la base; un `DELETE` también (criterio de salida de la Tarea 7).
- Anular y registrar un pago nuevo deja dos filas, la primera con motivo y autor de la anulación.
- Un pago que completa el precio pactado activa la membresía por evento; anularlo la devuelve a `pending_payment`.
- Un monto con decimales o negativo devuelve 422.
- El resumen del mes cuadra exactamente con la suma de los pagos no anulados del mes por medio (prueba con datos de demo).
- Un coach recibe 403 al anular.
- E2E de Playwright: registrar un pago Nequi con referencia y verlo en el resumen del mes.

## Dependencias

- EP-09 Membresías (el pago siempre es contra una membresía; activación por evento).
- EP-06 Layout y componentes compartidos del front.
- EP-03 Seguridad de la plataforma (solo admin anula).

## Riesgos

- El trigger de inmutabilidad debe permitir exactamente la transición de anulación; un trigger mal escrito bloquea las anulaciones legítimas o deja pasar ediciones.
- Pagos que superan el precio pactado: no hay regla sobre excedentes (ver preguntas abiertas).
- `paid_at` puede diferir de `created_at` (pago registrado después); el resumen del mes debe usar uno y documentarlo.

## Pantallas del diseño que habilita

- `Pagos` (sin recibo PDF ni exportación), pestaña Pagos de `Socio_Ficha`.
