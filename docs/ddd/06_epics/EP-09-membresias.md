# EP-09 · Venta y ciclo de vida de membresías

- **Versión del plan:** v0.1 (Tarea 6, Tarea 11 job de vencimientos, supuesto S5 de venta con primer pago).
- **Bounded context:** Memberships (negocio, esquema `memberships`). Es el dueño del estado "al día, por vencer, vencido".
- **Estimación relativa:** L.

## Objetivo de negocio

Que el dueño sepa en 10 segundos quién está al día, quién vence esta semana y quién ya venció (frase guía del producto), y que vender, renovar o congelar una membresía sea una sola acción correcta, con fechas que el sistema calcula y que nadie tiene que sacar a mano.

## Actores

- Administrador: vende, renueva, congela y anula con motivo.
- Coach: vende y renueva (`ROUTES.md`); no anula.
- Worker: recalcula estados cada día a las 7:00 hora de Bogotá.
- Módulos que reaccionan o consultan: Payments (eventos), Members (`status_for`), Plans (`count_active_by_plan`), Notifications y Dashboard.

## Capacidades incluidas

### Backend
- Aggregate `Membership`: `member_id`, `plan_id`, `agreed_price_cop` (copia del precio, RN-04), `start_date`, `end_date`, `classes_total`, `classes_remaining`, `status` (`pending_payment`, `active`, `expiring`, `expired`, `frozen`, `cancelled`), `frozen_from`, `frozen_to`, datos de cancelación; auditado.
- Value objects `DateRange` y `FreezeWindow`.
- Funciones puras: `compute_end_date` (RN-05), `compute_status` (RN-06), `apply_freeze` (RN-07: extiende el fin en `(to - from) + 1` días, solo sobre `active` o `expiring`), `next_start_for_renewal`, `is_covered` (RN-03).
- Operación de dominio `sell(member_id, plan_id, start_date, first_payment?)`: valida socio activo y sin membresía vigente, copia el precio, calcula el fin, nace en `pending_payment` y, si viene `first_payment`, llama a `payments.service.register` en la misma transacción (S5). Es la única entrada para vender y renovar.
- `renew` como azúcar sobre `sell` con `next_start_for_renewal`.
- `freeze`, `cancel` (solo admin, motivo obligatorio, `cancelled` es terminal).
- Activación por cobertura: handlers `on_payment_registered` y `on_payment_voided`; al anular, si la cobertura cae, vuelve a `pending_payment` y emite `MembershipActivationReverted`.
- Consultas: `list` (estado, `q`, plan, `ends_from`, `ends_to`, socio), `get`, `summary()` (al día, por vencer, vencidos, congelados, pendientes de pago), `status_for(member_ids)`, `count_active_by_plan(plan_id)`.
- `recompute_statuses(today)` y job `worker/jobs/expirations.py` en APScheduler a las 7:00 America/Bogota, que emite `MembershipExpiring` y `MembershipExpired`.
- Eventos `MembershipSold`, `MembershipActivated`, `MembershipExpiring`, `MembershipExpired`, `MembershipFrozen`, `MembershipCancelled`. `ClassConsumed` queda modelado pero solo se activa con EP-21.
- Endpoints: `GET /memberships`, `GET /memberships/summary`, `GET /memberships/{id}`, `POST /members/{id}/memberships` (vender, con `first_payment` opcional), `POST /memberships/{id}/freeze`, `POST /memberships/{id}/cancel` (admin), `GET /members/{id}/memberships`.

### Front
- Lista de membresías con filtros de estado, plan y rango de vencimiento, y las acciones congelar (modal) y anular (modal con motivo, solo admin).
- Pantalla de vender y renovar (`/membresias/vender` y `?socio=:id&renovar=1`) en una sola llamada con primer pago opcional.
- Pestaña Membresías de la ficha del socio.

## Fuera de alcance

- Descuento de clases por asistencia (`ClassConsumed`, EP-21).
- Avisos de vencimiento (EP-14).
- Reembolsos al anular (fuera de alcance del producto: los pagos se registran, no se cobran).

## Criterios de éxito medibles

- Pruebas puras de fecha de fin para plan por días y por clases, de cambio de estado al cruzar la fecha y de congelación (criterio de salida de la Tarea 6).
- Vender con un primer pago igual al precio deja la membresía `active` en la misma respuesta; con un pago parcial queda `pending_payment`.
- Si el pago de `sell` falla, no queda membresía creada (atomicidad de S5).
- Un socio con membresía vigente no puede recibir una segunda venta que viole la invariante de una sola vigente.
- El job de vencimientos con `FrozenClock` cambia a `expired` exactamente al día siguiente de `end_date` y a `expiring` a 7 días (criterio de salida de la Tarea 11); correrlo dos veces el mismo día no emite eventos duplicados.
- Anular una membresía exige motivo y solo la puede hacer admin.
- E2E de Playwright: vender una membresía con pago completo y verla "Al día" en la lista de socios.

## Dependencias

- EP-07 Padrón de socios (socio existe y está activo).
- EP-08 Catálogo de planes (lee precio y duración).
- EP-10 Registro inmutable de pagos: se construyen juntas en la misma iteración por `sell` y por los eventos de cobertura.
- EP-06 Layout y componentes compartidos del front.

## Riesgos

- La invariante "una sola membresía vigente" choca con renovar antes de vencer, que crea una membresía futura mientras la actual sigue activa (ver preguntas abiertas del README).
- Los planes por clases solo bajan `classes_remaining` desde v0.4; antes de eso vencen solo por fecha.
- `pending_payment` no aparece entre los chips del diseño; hay que decidir cómo se muestra.
- Cambios de zona horaria: el worker dispara en hora de Bogotá, pero las fechas de la membresía son fechas, no horas; hay que fijar qué "hoy" usa `compute_status`.

## Pantallas del diseño que habilita

- `Membresias`, `Membresia_Vender`, pestaña Membresías de `Socio_Ficha`.
