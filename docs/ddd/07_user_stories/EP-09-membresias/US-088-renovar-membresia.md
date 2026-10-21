# US-088 · Como administrador o coach quiero renovar la membresía de un socio antes o después de que venza para que no pierda días ni quede con dos planes encimados

- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context:** Memberships (esquema `memberships`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Membresia_Vender` (`/membresias/vender?socio=:id&renovar=1`)

## Historia

Como administrador o coach
quiero renovar con un clic desde la ficha o la lista, eligiendo el plan, y que el sistema calcule cuándo empieza la nueva membresía
para que la renovación arranque justo al día siguiente de la actual o hoy si ya venció

## Contexto de dominio

- **Aggregate / entidades:** `Membership`.
- **Reglas que aplica:** Q1 (como máximo una vigente y una futura; al renovar, `start_date` es el día siguiente al `end_date` de la vigente; nunca se solapan), Q2 (no hay `POST /memberships/{id}/renew`; renovar es `POST /members/{id}/memberships` con `renew: true` y el service calcula `start_date`), RN-04, RN-05, S5 (puede traer `first_payment`).
- **Eventos que emite:** `MembershipSold` (con `renewal = true`); `MembershipActivated` si el primer pago cubre (US-086)
- **Eventos que consume:** ninguno
- **Funciones puras:** `next_start_for_renewal(current, today)`, `compute_end_date`

## Alcance

- **Backend:** rama `renew = true` de `memberships.service.sell` (el `renew` de `05_service_design.md` es azúcar sobre `sell`): busca la vigente del socio, calcula `start_date = next_start_for_renewal(vigente, today_bogota())`, ignora un `start_date` enviado y aplica las mismas validaciones de US-084 y US-085.
- **Front:** `SellPage` en modo renovar (`?socio=:id&renovar=1`): socio fijo, plan precargado con el de la membresía actual si sigue activo, fecha de inicio calculada y de solo lectura ("Empieza el 1 nov 2026, al día siguiente de que termine la actual"), primer pago opcional. Botón "Renovar" en la pestaña Membresías (US-093) y en `Membresias` (US-091).

## Criterios de aceptación

1. `POST /api/v1/members/{id}/memberships` con `{ plan_id, renew: true }` y una vigente que termina el 2026-10-31, con hoy 2026-10-28, crea una membresía con `start_date = 2026-11-01`; con plan de 30 días, `end_date = 2026-12-01`.
2. Con la última membresía vencida (`end_date = 2026-10-31`, hoy 2026-11-05) o sin membresías, `start_date = 2026-11-05` (hoy en Bogotá).
3. Si viene `start_date` junto con `renew: true`, se ignora y la respuesta trae la fecha calculada (supuesto).
4. La membresía futura nace `pending_payment`; con `first_payment` que cubre, nace `active` aunque su `start_date` sea posterior a hoy (Q1: futura puede ser `active` con `start_date > hoy`).
5. Si el socio ya tiene una membresía futura (`pending_payment`, o `active` con `start_date > hoy`), devuelve 409 `code = "future_membership_exists"` con `existing_id`.
6. Si la vigente está `frozen`, el inicio se calcula sobre su `end_date` ya extendido.
7. Las fechas de la vigente y la nueva no se solapan nunca (lo verifica la restricción de exclusión de US-084).
8. El plan elegido puede ser distinto al actual; debe estar activo (422 `plan_inactive` si no).
9. Roles: admin y coach; `member` 403; sin token 401.
10. Queda auditoría `insert` de la nueva membresía; la vigente no se modifica.
11. Q3: mientras la futura está `pending_payment`, el chip del socio sigue mostrando el estado de la vigente (ver US-092).

## Escenarios BDD

```gherkin
# language: es
Característica: Renovar una membresía

  Antecedentes:
    Dado que existe el plan activo "Mensual" de 120000 y 30 días
    Y que estoy autenticado como coach

  Escenario: Renovar antes de vencer
    Dado que hoy en Bogotá es 2026-10-28
    Y "Laura Gómez" tiene una membresía "expiring" del 2026-10-01 al 2026-10-31
    Cuando renuevo a "Laura Gómez" con el plan "Mensual"
    Entonces la respuesta es 201
    Y la nueva membresía va del 2026-11-01 al 2026-12-01 en "pending_payment"
    Y la membresía actual no cambia

  Escenario: Renovar después de vencer
    Dado que hoy en Bogotá es 2026-11-05
    Y "Laura Gómez" tiene una membresía "expired" del 2026-10-01 al 2026-10-31
    Cuando renuevo a "Laura Gómez" con el plan "Mensual" y primer pago de 120000 en "cash"
    Entonces la nueva membresía va del 2026-11-05 al 2026-12-05
    Y queda "active"

  Escenario: Renovar con pago completo antes de vencer
    Dado que hoy en Bogotá es 2026-10-28
    Y "Laura Gómez" tiene una membresía "expiring" del 2026-10-01 al 2026-10-31
    Cuando renuevo a "Laura Gómez" con el plan "Mensual" y primer pago de 120000 en "nequi"
    Entonces la nueva membresía queda "active" con inicio 2026-11-01

  Escenario: Ya hay una renovación pendiente
    Dado que hoy en Bogotá es 2026-10-28
    Y "Laura Gómez" ya tiene una membresía futura en "pending_payment" que empieza el 2026-11-01
    Cuando renuevo a "Laura Gómez" con el plan "Mensual"
    Entonces la respuesta es 409
    Y el error tiene el código "future_membership_exists"

  Escenario: Socio del portal no puede renovar por aquí
    Dado que estoy autenticado con rol "member"
    Cuando renuevo a "Laura Gómez" con el plan "Mensual"
    Entonces la respuesta es 403
```

## Endpoints

- `POST /api/v1/members/{id}/memberships` — rol(es): admin, coach — entrada: `{ plan_id, renew: true, first_payment? }` — salida: `MembershipOut` (con `start_date` calculada) — códigos: 201, 401, 403, 404, 409, 422.

## Pantalla

- `Membresia_Vender` en modo renovar (`/membresias/vender?socio=:id&renovar=1`): socio fijo, fecha calculada visible y no editable, mismo bloque de primer pago. El front pide la fecha calculada con un `GET /api/v1/members/{id}/memberships/renewal-preview?plan_id=` (supuesto) o la calcula igual que el backend y la confirma con la respuesta.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** exclusión de solape de US-084.
- **Funciones puras a probar:** `next_start_for_renewal` con vigente sin vencer, vencida, congelada (fin extendido) y sin membresía.
- **Pruebas:** service con base real (futura única, no solape, plan distinto); router; front (modo renovar, fecha de solo lectura).
- **Archivos principales:** `api/src/app/modules/memberships/service.py`, `web/src/features/memberships/pages/SellPage.tsx`.

## Supuestos

- Supuesto: con `renew: true` el `start_date` enviado se ignora.
- Supuesto: la vista previa de la fecha de inicio se obtiene con `GET /api/v1/members/{id}/memberships/renewal-preview?plan_id=` (rol admin y coach, devuelve `{ start_date, end_date, agreed_price_cop }`); no está en el contrato. Alternativa sin endpoint: el front calcula y muestra "aproximada" hasta la respuesta.

## Dependencias

- US-084 · Vender membresía
- US-086 · Activar por cobertura de pagos

## INVEST

- **Independiente:** rama nueva sobre `sell`, sin tocar la vigente.
- **Negociable:** si existe o no el endpoint de vista previa.
- **Valiosa:** renovar a tiempo es la principal fuente de ingresos recurrentes.
- **Estimable:** reglas cerradas por Q1 y Q2.
- **Pequeña:** cuatro días.
- **Testeable:** fechas exactas por escenario.

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
- [ ] Auditoría verificada para `memberships`
- [ ] Revisión de PR aprobada
