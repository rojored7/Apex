# US-187 · Como socio quiero ver en el inicio del portal mi plan, su estado y cuándo vence para saber si estoy al día sin preguntar en recepción

- **Épica:** EP-25 · Portal del socio
- **Bounded context:** Portal (módulo `portal`), Conformist de Memberships, Payments y Training
- **Versión:** v1.0
- **Actor:** socio
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Portal_Inicio` (`/mi`)

## Historia

Como socio
quiero abrir el portal y ver mi plan, su estado, la fecha de fin, las clases que me quedan y el WOD de hoy
para saber de un vistazo si estoy al día y qué entreno hoy

## Contexto de dominio

- **Aggregate / entidades:** `Membership` (lectura), `Payment` (último pago), `Wod` del día.
- **Reglas que aplica:** RN-06 con `expiring_days` (Q11) y `today_bogota()` (Q28), RN-15, Q1 (vigente y futura), RN-01 (dinero entero).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `portal.summary(current, future, last_payment, wod_today) -> MeSummary`

## Alcance

- **Backend:** `portal.service.summary(member_id)` compone `memberships.service.current_and_future(member_id)`, `payments.service.last_for_member(member_id)` y `wods.service.today()`.
- **Front:** `Portal_Inicio` en `PortalLayout` con tarjeta de membresía, último pago y WOD de hoy.

## Criterios de aceptación

1. `GET /api/v1/me/summary` con rol member responde con: membresía vigente (plan, `status`, `start_date`, `end_date`, `classes_remaining` si es por clases, `agreed_price_cop` entero), membresía futura si existe (Q1), saldo pendiente en COP entero si está `pending_payment`, último pago no anulado (`amount_cop`, `method`, `paid_at` en UTC) y WOD de hoy (título y tipo) o `null`.
2. El `status` es el calculado con `expiring_days` de `settings.memberships` y la fecha de Bogotá.
3. Un socio sin membresía devuelve `membership = null` y `status = none`; la pantalla muestra "Sin plan vigente" y el texto para acercarse a recepción.
4. Solo datos del `member_id` de la sesión (prueba anti IDOR de US-186).
5. Admin y coach reciben 403; sin token, 401.
6. La pantalla funciona en 390 × 844, controles de 44 px, y el estado se muestra con texto ("Al día", "Por vencer", "Vencido", "Congelado", "Pendiente de pago") además del color.
7. La fecha de fin se muestra como `20 oct 2026` y el dinero como `$ 120.000`.

## Escenarios BDD

```gherkin
# language: es
Característica: Inicio del portal

  Escenario: Socio al día con plan mensual
    Dado que "Laura" tiene el plan "Mensual" activo que vence el 20 de noviembre de 2026
    Cuando entra al portal
    Entonces ve "Mensual", "Al día" y "Vence 20 nov 2026"
    Y ve su último pago

  Escenario: Socio sin plan vigente
    Dado que "Juan" no tiene membresía
    Cuando entra al portal
    Entonces ve "Sin plan vigente"
```

## Endpoints

- `GET /api/v1/me/summary` — rol(es): member — salida: `MeSummaryOut` — códigos: 200, 401, 403

## Pantalla

- `Portal_Inicio`: tarjetas de membresía, último pago y WOD de hoy; estados de carga, vacío y error.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `portal.summary` con vigente, con vigente y futura, sin membresía, `pending_payment` con saldo.
- **Pruebas:** pura; service con base real; router con anti IDOR; Vitest de la página; captura en 390 × 844 claro y oscuro.
- **Archivos principales:** `api/src/app/modules/portal/`, `web/src/features/portal/pages/PortalHome.tsx`.

## Supuestos

- Supuesto: `memberships.service.current_and_future` y `payments.service.last_for_member` son consultas nuevas en los services dueños.

## Dependencias

- US-186 · Autorización propia en rutas me
- US-092 · Resumen y consultas de estado
- US-062 · Layouts portal, gym y TV

## INVEST

- **Independiente:** solo lectura.
- **Negociable:** qué tarjetas aparecen.
- **Valiosa:** segunda mitad de la frase guía.
- **Estimable:** una consulta compuesta y una pantalla.
- **Pequeña:** pocos días.
- **Testeable:** estados exactos por fecha con `FrozenClock`.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol y envelope de error
- [ ] Front: pruebas de página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
