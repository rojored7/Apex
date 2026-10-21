# US-101 · Como coach o administrador quiero ver los pagos de un socio en su ficha para responderle qué ha pagado sin salir de su registro

- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context:** Payments (esquema `payments`), consumido desde Members (ficha)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Socio_Ficha` (`/socios/:id`, pestaña Pagos)

## Historia

Como coach o administrador
quiero ver en la ficha del socio todos sus pagos, incluidos los anulados
para responderle en el momento qué pagó, cuándo y por qué medio

## Contexto de dominio

- **Aggregate / entidades:** `Payment` (lectura filtrada por socio).
- **Reglas que aplica:** regla de datos 6 (paginación), RN-01, RN-02 (sin edición), mapa de contextos (Members no importa models de Payments; el router de members llama a `payments.service`).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** ninguna.

## Alcance

- **Backend:** `GET /members/{id}/payments`, que valida que el socio exista y delega en `payments.service.list(member_id=id, ...)` (US-098).
- **Front:** pestaña Pagos de `Socio_Ficha` con `DataTable` paginada (fecha, plan, monto, medio, referencia, estado) y botón "Registrar pago" que abre el `SidePanel` de US-095 con el socio preseleccionado.

## Criterios de aceptación

1. `GET /api/v1/members/{id}/payments` devuelve `{ items, total, limit, offset }` con los pagos de todas las membresías del socio, orden `paid_at` descendente; `limit` 1 a 200 (25 por defecto).
2. Incluye pagos anulados con `voided = true` y su motivo; acepta `voided=false` para ocultarlos.
3. Un socio inexistente devuelve 404; un socio dado de baja (`deleted_at` no nulo) devuelve igual sus pagos (historia de caja).
4. Montos enteros y fechas en UTC; el front los muestra como `$ 120.000` y hora de Bogotá.
5. Rol: `require_role("admin", "coach")`; `member` recibe 403; sin token, 401.
6. La pestaña no muestra acciones de editar ni borrar; "Anular" solo para admin (US-097).

## Escenarios BDD

```gherkin
# language: es
Característica: Pestaña Pagos de la ficha del socio

  Antecedentes:
    Dado la socia "Laura Gómez" con 3 pagos, uno de ellos anulado
    Y que estoy autenticado como "coach"

  Escenario: Veo los pagos de la socia
    Cuando abro la pestaña Pagos de su ficha
    Entonces veo 3 pagos del más reciente al más antiguo
    Y el anulado aparece con la etiqueta "Anulado" y su motivo

  Escenario: Registro un pago desde la ficha
    Cuando presiono "Registrar pago" en la pestaña Pagos
    Entonces se abre el panel de registro con "Laura Gómez" preseleccionada

  Escenario: Socio inexistente
    Cuando pido los pagos de un socio que no existe
    Entonces la respuesta es 404

  Escenario: Límite inválido
    Cuando pido los pagos con "limit" 0
    Entonces la respuesta es 422

  Escenario: Un socio no ve esta ruta
    Dado que estoy autenticado como "member"
    Cuando pido los pagos de "Laura Gómez" por esta ruta
    Entonces la respuesta es 403
```

## Endpoints

- `GET /api/v1/members/{id}/payments?voided&limit&offset` — rol(es): admin, coach — salida: `Page[PaymentRow]` — códigos: 200, 401, 403, 404, 422.

## Pantalla

- `Socio_Ficha` en `/socios/:id`, pestaña Pagos: estados de carga, vacío ("Este socio no tiene pagos") y error.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** router (404, 403, paginación); prueba de arquitectura (members no importa `payments.models`); front (pestaña y panel preseleccionado).
- **Archivos principales:** `api/src/app/modules/members/router.py`, `web/src/features/members/components/MemberPaymentsTab.tsx`.

## Supuestos

- Ninguno.

## Dependencias

- US-098 · Listar y buscar pagos (filtro `member_id`).
- US-073 · Ver ficha del socio (contenedor de pestañas).

## INVEST

- **Independiente:** reutiliza la consulta de US-098.
- **Negociable:** columnas de la pestaña.
- **Valiosa:** responde al socio en recepción.
- **Estimable:** una ruta delegada y una pestaña.
- **Pequeña:** un día.
- **Testeable:** respuestas y pestaña probadas.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
