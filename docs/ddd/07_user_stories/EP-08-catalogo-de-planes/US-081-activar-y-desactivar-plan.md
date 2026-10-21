# US-081 · Como administrador quiero activar y desactivar un plan para dejar de venderlo sin perder su historia

- **Épica:** EP-08 · Catálogo de planes
- **Bounded context:** Plans (esquema `plans`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Planes` (`/planes`, acción Activar/Desactivar)

## Historia

Como administrador
quiero desactivar un plan que ya no ofrezco y volver a activarlo si lo retomo
para que no aparezca al vender, sin tocar las membresías que ya se vendieron con él

## Contexto de dominio

- **Aggregate / entidades:** `Plan` (`is_active`).
- **Reglas que aplica:** RN-08 (un plan con membresías activas no se borra, se desactiva), RN-04 (las vendidas no cambian), RN-15 (solo admin).
- **Eventos que emite:** `PlanDeactivated` (al desactivar); `PlanUpdated` (al activar)
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `plans.service.set_active(id, bool, by)`, endpoints `POST /plans/{id}/activate` y `POST /plans/{id}/deactivate`. Memberships rechaza vender un plan inactivo (criterio verificado en US-084).
- **Front:** acción por fila "Desactivar" (con `ConfirmModal` que explica que las membresías vigentes siguen igual) y "Activar".

## Criterios de aceptación

1. `POST /api/v1/plans/{id}/deactivate` pone `is_active = false` y responde 200 con el plan; desactivar un plan ya inactivo responde 200 sin cambios ni nueva auditoría (idempotente).
2. `POST /api/v1/plans/{id}/activate` pone `is_active = true`; sobre uno activo es idempotente.
3. Desactivar siempre se permite aunque el plan tenga membresías activas (RN-08); esas membresías no cambian de estado, precio ni fechas.
4. Un plan inactivo no aparece en `GET /plans?active=true` y vender con él devuelve 422 con `code = "plan_inactive"` (lo implementa `memberships.service.sell`, US-084).
5. Un plan inexistente o con `deleted_at` devuelve 404.
6. Rol `admin`; coach 403; sin token 401.
7. Cada cambio efectivo deja fila de auditoría `update` con `is_active` antes y después.

## Escenarios BDD

```gherkin
# language: es
Característica: Activar y desactivar un plan

  Antecedentes:
    Dado que estoy autenticado como administrador
    Y existe el plan activo "Promo Octubre" con 4 membresías activas

  Escenario: Desactivar un plan con membresías activas
    Cuando desactivo el plan "Promo Octubre"
    Entonces la respuesta es 200
    Y el plan queda inactivo
    Y las 4 membresías siguen activas con su precio pactado
    Y "Promo Octubre" no aparece entre los planes activos

  Escenario: Reactivar un plan
    Dado que el plan "Promo Octubre" está inactivo
    Cuando activo el plan "Promo Octubre"
    Entonces el plan aparece entre los planes activos

  Escenario: Desactivar dos veces es idempotente
    Dado que el plan "Promo Octubre" está inactivo
    Cuando desactivo el plan "Promo Octubre"
    Entonces la respuesta es 200
    Y no se agrega una nueva entrada de auditoría

  Escenario: Plan inexistente
    Cuando desactivo un plan con un id que no existe
    Entonces la respuesta es 404

  Escenario: El coach no puede desactivar
    Dado que estoy autenticado como coach
    Cuando desactivo el plan "Promo Octubre"
    Entonces la respuesta es 403
```

## Endpoints

- `POST /api/v1/plans/{id}/activate` — rol(es): admin — entrada: vacía — salida: `PlanOut` — códigos: 200, 401, 403, 404.
- `POST /api/v1/plans/{id}/deactivate` — rol(es): admin — entrada: vacía — salida: `PlanOut` — códigos: 200, 401, 403, 404.

## Pantalla

- `Planes`: botón por fila según estado; `ConfirmModal` al desactivar; la fila cambia su `StatusTag`.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna nueva.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service (idempotencia, auditoría solo si cambia, evento); router (roles, 404); front (modal).
- **Archivos principales:** `api/src/app/modules/plans/{service,router}.py`, `web/src/features/plans/pages/PlansPage.tsx`.

## Supuestos

- Supuesto: las operaciones son idempotentes y no auditan cuando no hay cambio de estado.

## Dependencias

- US-079 · Listar planes

## INVEST

- **Independiente:** solo cambia un booleano del plan.
- **Negociable:** el texto del modal.
- **Valiosa:** retirar ofertas sin perder historia.
- **Estimable:** dos endpoints sencillos.
- **Pequeña:** dos días.
- **Testeable:** estados y respuestas exactas.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `plans`
- [ ] Revisión de PR aprobada
