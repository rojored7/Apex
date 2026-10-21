# US-093 · Como administrador o coach quiero ver todas las membresías de un socio en su ficha para conocer su historia y renovar o congelar desde ahí

- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context:** Memberships (esquema `memberships`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Socio_Ficha` (`/socios/:id`, pestaña Membresías)

## Historia

Como administrador o coach
quiero ver en la ficha del socio su membresía vigente, la futura si existe y las anteriores
para atenderlo en recepción sin cambiar de pantalla

## Contexto de dominio

- **Aggregate / entidades:** `Membership`.
- **Reglas que aplica:** RN-06/Q11, Q1 (vigente y futura), Q3, Q7 (congelar admin y coach), RN-15 (anular solo admin), paginación.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** endpoint `GET /members/{id}/memberships` (delegando en `memberships.service.list(member_id=...)`).
- **Front:** pestaña Membresías de `Socio_Ficha`: tarjeta destacada de la vigente (plan, fechas, días restantes, clases restantes si aplica, estado), tarjeta de la futura si existe, tabla paginada del historial; botones "Renovar" (a `/membresias/vender?socio=:id&renovar=1`), "Vender" si no tiene vigente ni futura, "Congelar" y "Anular" (solo admin).

## Criterios de aceptación

1. `GET /api/v1/members/{id}/memberships` responde `{ items, total, limit, offset }` con todas las membresías del socio (incluidas `cancelled`), ordenadas por `start_date` descendente; `limit` 1 a 200, 25 por defecto.
2. Socio inexistente devuelve 404; socio dado de baja devuelve sus membresías (solo lectura) para conservar la historia.
3. Roles: admin y coach; `member` 403; sin token 401.
4. La pestaña muestra la vigente arriba con `StatusTag` con texto ("Al día", "Por vencer", "Congelada", "Pendiente de pago"), fechas en formato `31 oct 2026` y precio pactado `$ 120.000`.
5. "Renovar" aparece si hay vigente o la última está vencida y no existe futura; "Vender" aparece si no hay vigente ni futura; ninguno aparece si el socio está dado de baja.
6. "Anular" solo se muestra a admin (`useCan`); "Congelar" a admin y coach y solo sobre `active` o `expiring`.
7. Estados de carga, vacío ("Este socio no tiene membresías. Vender") y error.

## Escenarios BDD

```gherkin
# language: es
Característica: Pestaña Membresías de la ficha

  Antecedentes:
    Dado que hoy en Bogotá es 2026-10-28
    Y "Laura Gómez" tiene una membresía vencida de septiembre, una "expiring" del 2026-10-01 al 2026-10-31 y una futura en "pending_payment" desde el 2026-11-01

  Escenario: Ver historia de membresías
    Dado que estoy autenticado como coach
    Cuando abro la pestaña Membresías de "Laura Gómez"
    Entonces veo la vigente "Por vencer" hasta 31 oct 2026
    Y veo la futura "Pendiente de pago" desde 1 nov 2026
    Y veo la de septiembre en el historial
    Y no veo el botón "Renovar" porque ya existe una futura
    Y no veo el botón "Anular"

  Escenario: Paginación fuera de rango
    Dado que estoy autenticado como administrador
    Cuando consulto las membresías de "Laura Gómez" con limit 0
    Entonces la respuesta es 422

  Escenario: Socio inexistente
    Dado que estoy autenticado como administrador
    Cuando consulto las membresías de un socio que no existe
    Entonces la respuesta es 404

  Escenario: Socio del portal denegado
    Dado que estoy autenticado con rol "member"
    Cuando consulto las membresías de "Laura Gómez"
    Entonces la respuesta es 403
```

## Endpoints

- `GET /api/v1/members/{id}/memberships?limit&offset` — rol(es): admin, coach — salida: `{ items: MembershipOut[], total, limit, offset }` — códigos: 200, 401, 403, 404, 422.

## Pantalla

- `Socio_Ficha` pestaña Membresías en `/socios/:id`. `// DESIGN-GAP:` tarjeta de membresía futura y chip "Pendiente de pago" (Q1, Q3).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no.
- **Funciones puras a probar:** ninguna; la lógica de qué botón mostrar va en una función pura del front `membershipActions(memberships, role, today)` con pruebas de Vitest.
- **Pruebas:** router (roles, 404, paginación); front (botones por rol y por estado).
- **Archivos principales:** `api/src/app/modules/members/router.py` (ruta anidada que delega en `memberships.service`), `web/src/features/memberships/components/MemberMembershipsTab.tsx`.

## Supuestos

- Supuesto: la ruta `GET /members/{id}/memberships` vive en el router de `memberships` con prefijo `/members/{id}` para no hacer que `members` dependa de `memberships`.

## Dependencias

- US-091 · Listar membresías
- US-073 · Ver ficha del socio

## INVEST

- **Independiente:** reutiliza la lista con un filtro fijo.
- **Negociable:** disposición de las tarjetas.
- **Valiosa:** atención en recepción desde una sola pantalla.
- **Estimable:** una ruta y una pestaña.
- **Pequeña:** uno a dos días.
- **Testeable:** botones visibles por rol y estado.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
