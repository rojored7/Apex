# US-092 · Como administrador o coach quiero contar cuántos socios están al día, por vencer, vencidos, congelados y pendientes de pago para saber en segundos cómo está el gimnasio

- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context:** Memberships (esquema `memberships`), proveedor de consultas para Members, Plans y Dashboard
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna propia (alimenta `Inicio`, chips de `Socios_Lista` y `Planes`)

## Historia

Como administrador o coach
quiero un resumen con el número de socios en cada estado de membresía y que los demás módulos pregunten el estado de un socio con una sola regla
para que el tablero, la lista de socios y el catálogo de planes digan lo mismo

## Contexto de dominio

- **Aggregate / entidades:** `Membership`; consulta derivada `membership_status` del socio (`02_domain_model.md` 2.1).
- **Reglas que aplica:** RN-06/Q11, Q1 (vigente y futura), Q3 (`pending_payment` visible), RN-08 (`count_active_by_plan` para Plans), mapa de contextos (Members pide `status_for`; Plans pide `count_active_by_plan`, única llamada en sentido contrario).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `resolve_member_status(memberships, today) -> MembershipStatus | "none"` (nueva, pura)

## Alcance

- **Backend:** `memberships.service.summary()`, `status_for(member_ids) -> dict[UUID, status]`, `count_active_by_plan(plan_id) -> int`, función pura `resolve_member_status`; endpoint `GET /memberships/summary`.
- **Front:** hook `useMembershipSummary` en `features/memberships/api.ts` para que lo consuman Inicio (US-108/US-109) y Socios (US-071). Sin pantalla propia.

## Criterios de aceptación

1. `GET /api/v1/memberships/summary` responde `{ active, expiring, expired, frozen, pending_payment }` con enteros que cuentan **socios no dados de baja** según su `membership_status` (supuesto).
2. `resolve_member_status` es pura y aplica la prioridad: membresía vigente (`active`, `expiring` o `frozen` con `start_date <= hoy`) > `pending_payment` > `expired` > `none`; las `cancelled` se ignoran; una futura `active` con `start_date > hoy` no reemplaza a la vigente.
3. Un socio con vigente `expiring` y futura `pending_payment` (renovación sin pagar) cuenta como `expiring`.
4. Un socio con solo una futura `active` (vendida para empezar la semana próxima) cuenta como `active` (supuesto).
5. `status_for([ids])` devuelve un valor para cada id pedido (`none` si no tiene membresías no canceladas) con una sola consulta a la base para hasta 200 ids (sin N+1).
6. `count_active_by_plan(plan_id)` cuenta membresías del plan en `pending_payment`, `active`, `expiring` o `frozen`.
7. La suma `active + expiring + expired + frozen + pending_payment` más los socios `none` es igual al total de socios no dados de baja (prueba con datos de demo).
8. Los conteos coinciden con `GET /memberships?status=...` agrupado por socio.
9. Roles: admin y coach; `member` 403; sin token 401.
10. Responde en menos de 300 ms con 1.000 socios.

## Escenarios BDD

```gherkin
# language: es
Característica: Resumen y consultas de estado de membresías

  Antecedentes:
    Dado que hoy en Bogotá es 2026-10-26
    Y existen 10 socios con membresía "active", 3 "expiring", 4 "expired", 1 "frozen" y 2 en "pending_payment"
    Y "Laura Gómez" tiene una membresía "expiring" y una renovación futura en "pending_payment"

  Escenario: Resumen del gimnasio
    Dado que estoy autenticado como administrador
    Cuando consulto el resumen de membresías
    Entonces recibo 10 al día, 4 por vencer, 4 vencidos, 1 congelado y 2 pendientes de pago
    Y "Laura Gómez" cuenta como por vencer

  Escenario: Estado de varios socios en una consulta
    Cuando el módulo de socios pide el estado de 3 socios, uno de ellos sin membresías
    Entonces recibe un estado para cada uno
    Y el socio sin membresías tiene estado "none"

  Escenario: Conteo de membresías activas por plan
    Dado que el plan "Mensual" tiene 2 membresías "active", 1 "pending_payment" y 5 "expired"
    Cuando el módulo de planes cuenta las membresías activas de "Mensual"
    Entonces el resultado es 3

  Escenario: Socio del portal denegado
    Dado que estoy autenticado con rol "member"
    Cuando consulto el resumen de membresías
    Entonces la respuesta es 403
```

## Endpoints

- `GET /api/v1/memberships/summary` — rol(es): admin, coach — salida: `{ active: int, expiring: int, expired: int, frozen: int, pending_payment: int }` — códigos: 200, 401, 403.
- Contratos internos (sin HTTP): `status_for(member_ids)`, `count_active_by_plan(plan_id)`.

## Pantalla

- Ninguna propia.

## Notas técnicas

- **Migración:** no; índice `memberships.memberships (member_id, status, start_date)`.
- **Trigger / restricciones:** no.
- **Funciones puras a probar:** `resolve_member_status` con: solo vigente, vigente + futura pendiente, solo futura activa, solo vencida, solo cancelada (→ `none`), vigente congelada.
- **Pruebas:** puras; service con base real (sin N+1: contar consultas); router; prueba de consistencia de la suma.
- **Archivos principales:** `api/src/app/modules/memberships/{service,router,schemas}.py`.

## Supuestos

- Supuesto: el resumen cuenta socios (por su estado resuelto), no filas de membresía, para que "socios al día" del tablero no cuente dos veces a quien renovó.
- Supuesto: un socio cuya única membresía es una futura ya pagada cuenta como "al día".
- Supuesto: los socios dados de baja no entran al resumen; Members entrega la lista de ids no borrados con `members.service.active_ids()`.

## Dependencias

- US-084 · Vender membresía

## INVEST

- **Independiente:** consultas sobre la tabla existente.
- **Negociable:** si se cuentan socios o filas (supuesto declarado).
- **Valiosa:** es la fuente única de "quién está al día".
- **Estimable:** tres consultas y una función pura.
- **Pequeña:** dos a tres días.
- **Testeable:** conteos exactos con datos fijos.

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
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
