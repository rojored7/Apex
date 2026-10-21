# US-082 · Como administrador quiero dar de baja un plan que no tiene membresías activas para limpiar el catálogo sin perder historia

- **Épica:** EP-08 · Catálogo de planes
- **Bounded context:** Plans (esquema `plans`), con consulta a Memberships
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P2 mejora
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Planes` (`/planes`, acción "Dar de baja")

## Historia

Como administrador
quiero dar de baja (borrado lógico) un plan que ya nadie tiene vigente
para que deje de aparecer en el catálogo, sabiendo que el sistema me lo impide si todavía hay socios con ese plan activo

## Contexto de dominio

- **Aggregate / entidades:** `Plan` (`deleted_at`).
- **Reglas que aplica:** RN-08 (plan con membresías activas no se borra, solo se desactiva), RN-14 (borrado lógico con `deleted_at`, nunca físico), RN-15 (solo admin). Relación Plans → Memberships documentada como única llamada en sentido contrario (`03_context_map.md` 2).
- **Eventos que emite:** `PlanDeactivated` (si el plan estaba activo al darlo de baja)
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `plans.service.deactivate_or_fail(id, by)` que llama a `memberships.service.count_active_by_plan(plan_id)` (US-092); si el conteo es mayor que 0 lanza error de dominio; si es 0 pone `deleted_at = now()` y `is_active = false`. Endpoint según el supuesto.
- **Front:** acción "Dar de baja" en `Planes` con `ConfirmModal`; si el API responde 409, el modal muestra "Este plan tiene N membresías activas. Desactívalo en su lugar." con botón "Desactivar".

## Criterios de aceptación

1. `DELETE /api/v1/plans/{id}` (supuesto) con `count_active_by_plan(plan_id) = 0` responde 204 y deja `deleted_at` en UTC e `is_active = false`; la fila no se borra físicamente.
2. Con `count_active_by_plan(plan_id) > 0` responde 409 con `code = "plan_has_active_memberships"` y el conteo en `message`; el plan no cambia.
3. `count_active_by_plan` cuenta las membresías del plan en `pending_payment`, `active`, `expiring` o `frozen` (supuesto); las `expired` y `cancelled` no impiden la baja.
4. Un plan dado de baja no aparece en ninguna lista ni en `GET /plans/{id}` (404), pero las membresías vendidas siguen mostrando su nombre (lo leen por `plans.service.get_including_deleted`).
5. Dar de baja un plan ya dado de baja devuelve 404.
6. Rol `admin`; coach 403; sin token 401.
7. Queda fila de auditoría `update` con `deleted_at` antes y después (borrado lógico es un update, no un `delete`).
8. Prueba de arquitectura: `plans` llama a `memberships.service`, nunca importa `memberships.models`.

## Escenarios BDD

```gherkin
# language: es
Característica: Dar de baja un plan

  Antecedentes:
    Dado que estoy autenticado como administrador

  Escenario: Baja de un plan sin membresías activas
    Dado que el plan "Promo 2025" solo tiene membresías vencidas
    Cuando doy de baja el plan "Promo 2025"
    Entonces la respuesta es 204
    Y el plan no aparece en la lista de planes
    Y las membresías vencidas siguen mostrando el nombre "Promo 2025"

  Escenario: Baja bloqueada por membresías activas
    Dado que el plan "Mensual" tiene 12 membresías activas
    Cuando doy de baja el plan "Mensual"
    Entonces la respuesta es 409
    Y el error tiene el código "plan_has_active_memberships"
    Y el plan "Mensual" sigue en el catálogo

  Escenario: Una membresía pendiente de pago también bloquea
    Dado que el plan "Trimestral" tiene 1 membresía en "pending_payment"
    Cuando doy de baja el plan "Trimestral"
    Entonces la respuesta es 409

  Escenario: El coach no puede dar de baja
    Dado que estoy autenticado como coach
    Cuando doy de baja el plan "Promo 2025"
    Entonces la respuesta es 403
```

## Endpoints

- `DELETE /api/v1/plans/{id}` (supuesto, no está en `05_service_design.md` sección 4) — rol(es): admin — entrada: vacía — salida: sin cuerpo — códigos: 204, 401, 403, 404, 409.

## Pantalla

- `Planes`: acción "Dar de baja" en el menú de la fila; `ConfirmModal`; manejo del 409 con salida a "Desactivar" (US-081). `// DESIGN-GAP:` el diseño no muestra el mensaje de bloqueo por membresías activas.

## Notas técnicas

- **Migración:** no (la columna `deleted_at` ya existe por US-078).
- **Trigger / restricciones:** ninguno; no hay `DELETE` físico en el código.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service con base real usando el `count_active_by_plan` real; router; prueba de arquitectura de imports; front (manejo del 409).
- **Archivos principales:** `api/src/app/modules/plans/{service,router,exceptions}.py`, `web/src/features/plans/pages/PlansPage.tsx`.

## Supuestos

- Supuesto: el contrato HTTP de v0.1 no tiene endpoint de baja de planes; se agrega `DELETE /api/v1/plans/{id}` como borrado lógico para cumplir RN-08 y RN-14. Si el gate decide que en v0.1 solo existe desactivar, esta historia se descarta sin afectar a las demás.
- Supuesto: "membresías activas" para RN-08 son las que están en `pending_payment`, `active`, `expiring` o `frozen`.

## Dependencias

- US-081 · Activar y desactivar plan
- US-092 · Resumen y consultas de estado (`count_active_by_plan`)

## INVEST

- **Independiente:** prescindible; el resto del catálogo funciona sin ella.
- **Negociable:** si el gate rechaza el endpoint, se descarta.
- **Valiosa:** mantiene el catálogo limpio y hace cumplir RN-08.
- **Estimable:** un endpoint con una consulta externa conocida.
- **Pequeña:** un día y medio.
- **Testeable:** 204 o 409 según un conteo.

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
