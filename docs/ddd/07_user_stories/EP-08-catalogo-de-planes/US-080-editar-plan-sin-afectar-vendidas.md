# US-080 · Como administrador quiero editar un plan sin afectar las membresías ya vendidas para subir precios sin cambiar lo pactado con cada socio

- **Épica:** EP-08 · Catálogo de planes
- **Bounded context:** Plans (esquema `plans`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Planes` (`/planes`, panel lateral "Editar plan")

## Historia

Como administrador
quiero cambiar el nombre, el precio, la duración o el número de clases de un plan
para actualizar mi oferta sin que las membresías vendidas cambien de precio ni de fechas

## Contexto de dominio

- **Aggregate / entidades:** `Plan`.
- **Reglas que aplica:** RN-01, RN-04 (la membresía copia el precio al vender; cambiar el plan no cambia `agreed_price_cop`, `end_date` ni `classes_total` de las vendidas), invariantes de `validate_plan`, RN-15 (solo admin).
- **Eventos que emite:** `PlanUpdated`
- **Eventos que consume:** ninguno
- **Funciones puras:** `plans.validate_plan` (se aplica sobre el estado resultante)

## Alcance

- **Backend:** `plans.service.update(id, data, by)` con validación del estado final, endpoint `PATCH /plans/{id}`.
- **Front:** acción "Editar" en cada fila de `Planes`, `SidePanel` precargado con el mismo formulario de US-078 y aviso fijo: "Cambiar el precio no modifica las membresías ya vendidas".

## Criterios de aceptación

1. `PATCH /api/v1/plans/{id}` acepta cualquier subconjunto de `name`, `price_cop`, `kind`, `duration_days`, `class_count` y responde 200 con el plan actualizado.
2. La validación se hace sobre el plan resultante: pasar a `kind = classes` sin `class_count` (ni existente ni nuevo) devuelve 422 con `field = "class_count"`; pasar a `kind = days` exige enviar `class_count: null`, si no, 422.
3. `price_cop` sigue las reglas de RN-01 (entero mayor que 0; decimales o negativo dan 422).
4. Ninguna fila de `memberships.memberships` cambia por editar un plan: prueba conjunta que vende una membresía a 120.000, cambia el plan a 135.000 y verifica que `agreed_price_cop` sigue en 120.000 y `end_date` igual.
5. `is_active` y `deleted_at` no se cambian por este endpoint (se ignoran o devuelven 422 si vienen): activar y desactivar es US-081.
6. Un plan inexistente o dado de baja devuelve 404.
7. Rol `admin` obligatorio; coach recibe 403; sin token, 401.
8. Queda una fila de auditoría `update` con `before` y `after`; `updated_at` cambia (UTC).
9. Se emite `PlanUpdated` en la misma transacción.

## Escenarios BDD

```gherkin
# language: es
Característica: Editar un plan

  Antecedentes:
    Dado que estoy autenticado como administrador
    Y existe el plan "Mensual" con precio 120000 y 30 días
    Y la socia "Laura Gómez" tiene una membresía "Mensual" vendida a 120000 del 2026-10-01 al 2026-10-31

  Escenario: Subir el precio no cambia lo vendido
    Cuando cambio el precio del plan "Mensual" a 135000
    Entonces la respuesta es 200
    Y el plan "Mensual" tiene precio 135000
    Y la membresía de "Laura Gómez" conserva el precio pactado 120000 y la fecha de fin 2026-10-31
    Y queda una entrada de auditoría "update" con el precio anterior y el nuevo

  Escenario: Pasar a por clases sin número de clases
    Cuando cambio el tipo del plan "Mensual" a "classes" sin indicar número de clases
    Entonces la respuesta es 422
    Y el error señala el campo "class_count"

  Escenario: Precio negativo
    Cuando cambio el precio del plan "Mensual" a -1000
    Entonces la respuesta es 422
    Y el error señala el campo "price_cop"

  Escenario: El coach no puede editar
    Dado que estoy autenticado como coach
    Cuando cambio el precio del plan "Mensual" a 135000
    Entonces la respuesta es 403
    Y el plan conserva el precio 120000
```

## Endpoints

- `PATCH /api/v1/plans/{id}` — rol(es): admin — entrada: `{ name?, price_cop?, kind?, duration_days?, class_count? }` — salida: `PlanOut` — códigos: 200, 401, 403, 404, 422.

## Pantalla

- `Planes`: acción "Editar" abre el `SidePanel` precargado; muestra el aviso de RN-04; al guardar refresca la fila.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** las `CHECK` de US-078 protegen el estado final.
- **Funciones puras a probar:** `validate_plan` con los estados resultantes de cambio de tipo.
- **Pruebas:** service con base real (incluida la prueba conjunta con Memberships, que se completa cuando exista US-084; antes, con una membresía creada por factory); router; front.
- **Archivos principales:** `api/src/app/modules/plans/{service,router,schemas}.py`, `web/src/features/plans/components/PlanForm.tsx`.

## Supuestos

- Ninguno.

## Dependencias

- US-079 · Listar planes

## INVEST

- **Independiente:** solo toca `plans`; la prueba de RN-04 usa una factory si US-084 no está terminada.
- **Negociable:** el texto del aviso y qué campos se ven primero.
- **Valiosa:** el dueño ajusta precios sin miedo de alterar cobros.
- **Estimable:** un PATCH con validación conocida.
- **Pequeña:** dos días.
- **Testeable:** la prueba conjunta de RN-04 es binaria.

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
