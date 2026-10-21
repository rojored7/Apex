# US-084 · Como administrador o coach quiero venderle una membresía a un socio para que quede registrado qué plan tiene, desde cuándo y hasta cuándo

- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context:** Memberships (esquema `memberships`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Membresia_Vender` (`/membresias/vender` y `/membresias/vender?socio=:id`)

## Historia

Como administrador o coach
quiero elegir un socio y un plan activo y registrar la venta con la fecha de inicio
para que el sistema copie el precio, calcule la fecha de fin y deje la membresía pendiente de pago hasta que se cubra

## Contexto de dominio

- **Aggregate / entidades:** `Membership` (raíz). Lee `Plan` por `plans.service.get(plan_id)` (Conformist) y `Member` por `members.service` (Customer/Supplier).
- **Reglas que aplica:** RN-04 (copia `agreed_price_cop` del plan), RN-05 (`end_date = compute_end_date`), RN-01 (dinero entero), Q1 (como máximo una membresía vigente `active`/`expiring`/`frozen` y una futura `pending_payment` o `active` con `start_date > hoy`; las fechas de dos membresías del mismo socio nunca se solapan), Q4 (`classes_remaining` se crea pero no baja hasta v0.4), RN-15 (admin y coach venden). S5: `sell` es la única entrada para vender y renovar.
- **Eventos que emite:** `MembershipSold`
- **Eventos que consume:** ninguno
- **Funciones puras:** `compute_end_date`, `compute_status` (US-083)

## Alcance

- **Backend:** modelo `memberships.memberships` con `__audited__ = True` y migración; `memberships.service.sell(member_id, plan_id, start_date, first_payment=None, renew=False, by)` en su camino sin pago; validaciones de socio, plan y solape; endpoint `POST /members/{id}/memberships`. El primer pago es US-085 y renovar es US-088.
- **Front:** `web/src/features/memberships/pages/SellPage.tsx`: buscador de socio (o socio precargado por `?socio=:id`), selector de plan activo (US-079 con `active=true`), fecha de inicio (por defecto hoy en Bogotá), resumen con precio, fin calculado y número de clases; botón "Vender". La sección de primer pago la agrega US-085.

## Criterios de aceptación

1. `POST /api/v1/members/{id}/memberships` con `{ plan_id, start_date? }` crea la membresía en `pending_payment` y responde 201 con `MembershipOut` (`id`, `member_id`, `plan_id`, `plan_name`, `agreed_price_cop`, `start_date`, `end_date`, `classes_total`, `classes_remaining`, `status`).
2. `start_date` es una fecha (sin hora) y por defecto es `today_bogota()`; `end_date = compute_end_date(start_date, plan)`; las fechas salen en ISO `AAAA-MM-DD` y los timestamps (`created_at`) en UTC ISO 8601.
3. `agreed_price_cop` es la copia entera de `plan.price_cop` al momento de la venta; cambiar el plan después no lo modifica (RN-04).
4. Si `plan.kind = classes`, `classes_total = classes_remaining = plan.class_count`; si es `days`, ambos son nulos.
5. Socio inexistente o dado de baja (`deleted_at` no nulo): 404. Socio con `status = inactive`: 422 `code = "member_inactive"`.
6. Plan inexistente o dado de baja: 422 `field = "plan_id"`; plan con `is_active = false`: 422 `code = "plan_inactive"`.
7. Venta sin `renew` cuando el socio ya tiene una membresía vigente (`active`, `expiring`, `frozen`) o una futura (`pending_payment` o `active` con `start_date > hoy`): 409 `code = "membership_conflict"` con `existing_id`; el mensaje sugiere renovar.
8. Si `start_date` haría que las fechas se solapen con otra membresía no cancelada del socio, 409 `code = "membership_overlap"` (garantiza Q1 también con fechas elegidas a mano).
9. Una membresía `expired` o `cancelled` previa no impide vender.
10. La operación es una sola transacción: crea la fila, deja fila de auditoría `insert` en `memberships`, emite `MembershipSold`; si un handler falla, no queda nada creado.
11. Rol: `require_role("admin", "coach")`; un usuario `member` recibe 403; sin token 401.
12. En el front, el resumen muestra precio con `$ 120.000` y fin en formato `31 oct 2026`; un 409 muestra el enlace "Renovar" hacia `/membresias/vender?socio=:id&renovar=1`.
13. `memberships.service` valida socio y plan llamando a `members.service` y `plans.service`; nunca importa sus `models` (prueba de arquitectura).

## Escenarios BDD

```gherkin
# language: es
Característica: Vender una membresía

  Antecedentes:
    Dado que hoy en Bogotá es 2026-10-01
    Y existe el plan activo "Mensual" de 120000 y 30 días
    Y el socio "Juan Rodríguez" está activo y no tiene membresías

  Escenario: Venta sin pago queda pendiente
    Dado que estoy autenticado como coach
    Cuando vendo el plan "Mensual" a "Juan Rodríguez" con inicio 2026-10-01
    Entonces la respuesta es 201
    Y la membresía queda en "pending_payment" con precio pactado 120000
    Y la fecha de fin es 2026-10-31
    Y se emite "MembershipSold"

  Escenario: Tiquetera por clases
    Dado que existe el plan activo "Tiquetera 12" de 150000, 60 días y 12 clases
    Y que estoy autenticado como administrador
    Cuando vendo el plan "Tiquetera 12" a "Juan Rodríguez" con inicio 2026-10-01
    Entonces la membresía tiene 12 clases totales y 12 restantes
    Y la fecha de fin es 2026-11-30

  Escenario: El socio ya tiene una membresía vigente
    Dado que "Juan Rodríguez" tiene una membresía "active" del 2026-09-15 al 2026-10-15
    Y que estoy autenticado como administrador
    Cuando vendo el plan "Mensual" a "Juan Rodríguez" sin indicar renovación
    Entonces la respuesta es 409
    Y el error tiene el código "membership_conflict" y el id de la membresía existente

  Escenario: Plan inactivo
    Dado que el plan "Promo 2025" está inactivo
    Y que estoy autenticado como administrador
    Cuando vendo el plan "Promo 2025" a "Juan Rodríguez"
    Entonces la respuesta es 422
    Y el error tiene el código "plan_inactive"

  Escenario: Socio dado de baja
    Dado que el socio "Pedro Díaz" fue dado de baja
    Y que estoy autenticado como administrador
    Cuando vendo el plan "Mensual" a "Pedro Díaz"
    Entonces la respuesta es 404

  Escenario: Un socio del portal no puede vender
    Dado que estoy autenticado con rol "member"
    Cuando vendo el plan "Mensual" a "Juan Rodríguez"
    Entonces la respuesta es 403
```

## Endpoints

- `POST /api/v1/members/{id}/memberships` — rol(es): admin, coach — entrada: `{ plan_id: uuid, start_date?: date, renew?: bool (US-088), first_payment?: PaymentIn (US-085) }` — salida: `MembershipOut` — códigos: 201, 401, 403, 404, 409, 422.

## Pantalla

- `Membresia_Vender` en `/membresias/vender`: buscador de socio, selector de plan, fecha de inicio y resumen. Estados: cargando planes, sin planes activos ("No hay planes activos; pide al administrador que cree uno"), error 409 con enlace a renovar, éxito (redirige a la ficha del socio, pestaña Membresías).

## Notas técnicas

- **Migración:** sí. Esquema `memberships`, tabla `memberships.memberships` (`id`, `member_id` uuid, `plan_id` uuid, `agreed_price_cop` integer, `start_date` date, `end_date` date, `classes_total` int null, `classes_remaining` int null, `status` text, `frozen_from` date null, `frozen_to` date null, `freeze_count` int default 0, `frozen_days_total` int default 0, `cancel_reason` text null, `cancelled_by` uuid null, `cancelled_at` timestamptz null, columnas comunes). Sin FK a otros esquemas (fronteras de contexto).
- **Trigger / restricciones:** `CHECK (agreed_price_cop > 0)`, `CHECK (start_date <= end_date)`, `CHECK (status IN (...))`, `CHECK (classes_remaining IS NULL OR classes_remaining >= 0)`; índice `(member_id, status)`; restricción de exclusión `EXCLUDE USING gist (member_id WITH =, daterange(start_date, end_date, '[]') WITH &&) WHERE (status <> 'cancelled')` (requiere `btree_gist`) como red de seguridad del no solape.
- **Funciones puras a probar:** las de US-083 vía la venta.
- **Pruebas:** service con base real (copia de precio, conflicto, solape, atomicidad con handler que falla); router (roles, 404, 409, 422); arquitectura (sin imports de models ajenos); front (formulario, resumen, manejo del 409).
- **Archivos principales:** `api/src/app/modules/memberships/{models,schemas,service,router,exceptions}.py`, `api/migrations/versions/<rev>_memberships.py`, `web/src/features/memberships/{api.ts,schemas.ts,pages/SellPage.tsx}`.

## Supuestos

- Supuesto: se acepta cualquier `start_date` que no solape, incluso anterior a hoy (venta registrada tarde); el estado se calcula al guardar con `compute_status`. No hay regla de antigüedad máxima.
- Supuesto: `freeze_count` y `frozen_days_total` se agregan en esta migración para que US-089 pueda aplicar los límites de Q9 sin una segunda migración con datos.

## Dependencias

- US-083 · Reglas puras de fechas y estados
- US-069 · Registrar socio
- US-079 · Listar planes (lectura de plan activo)
- US-014 · Bus de eventos transaccional

## INVEST

- **Independiente:** la venta sin pago se entrega y prueba sola; el pago llega en US-085.
- **Negociable:** el orden de los campos del formulario y los textos.
- **Valiosa:** registrar la venta es la acción central del negocio.
- **Estimable:** una tabla, una operación y una pantalla.
- **Pequeña:** cuatro a cinco días.
- **Testeable:** respuestas y fechas exactas por escenario.

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
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `memberships`
- [ ] Revisión de PR aprobada
