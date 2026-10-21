# US-098 · Como coach o administrador quiero listar y filtrar los pagos para revisar la caja por fecha, medio, persona que registró o socio

- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context:** Payments (esquema `payments`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Pagos` (`/pagos`)

## Historia

Como coach o administrador
quiero ver la lista de pagos con filtros de fecha, medio, quién registró, anulados y socio
para encontrar rápido un pago y revisar la caja sin depender de la memoria de nadie

## Contexto de dominio

- **Aggregate / entidades:** `Payment` (lectura).
- **Reglas que aplica:** regla de datos 6 (toda lista pagina con `limit`/`offset`, máximo 200, y acepta búsqueda), RN-01 (montos enteros), fechas en UTC, mapa de contextos (Payments no hace joins con otros esquemas; nombres de socio por service).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** ninguna.

## Alcance

- **Backend:** `payments.service.list(q, from, to, method, registered_by, voided, member_id, membership_id, limit, offset)`; `member_id` se resuelve pidiendo a `memberships.service` los ids de membresía del socio; cada fila trae el nombre del socio obtenido por `members.service` (nombre y apellido en claro), sin joins entre esquemas.
- **Front:** pantalla `Pagos` con `FilterBar` (rango de fechas, medio, registrado por, incluir anulados, búsqueda), `DataTable` con fecha y hora de Bogotá, socio, plan, monto `$ 120.000`, medio, referencia, registrado por y etiqueta "Anulado", y `Pagination`.

## Criterios de aceptación

1. `GET /api/v1/payments` responde `{ items, total, limit, offset }`; `limit` por defecto 25, mínimo 1, máximo 200; `limit=201` o `offset=-1` devuelve 422.
2. `from` y `to` son fechas-hora ISO 8601 con zona y filtran por `paid_at` (incluye `from`, excluye `to`); el front envía el inicio y fin del día de Bogotá convertidos a UTC.
3. `method` filtra por `cash`, `nequi` o `breb`; un valor distinto devuelve 422.
4. `registered_by` filtra por id de usuario; `membership_id` y `member_id` filtran por membresía o por socio (todas sus membresías).
5. `voided=true` devuelve solo anulados, `voided=false` solo vigentes; sin el parámetro devuelve ambos.
6. `q` busca por coincidencia exacta de `reference` (sin distinguir mayúsculas) o por nombre o apellido del socio (parcial, vía `members.service`).
7. El orden por defecto es `paid_at` descendente; los montos se devuelven como enteros y las fechas en UTC.
8. Ninguna fila incluye datos cifrados del socio (solo `member_id`, `first_name`, `last_name`).
9. Rol: `require_role("admin", "coach")`; un `member` recibe 403; sin token, 401.
10. La lista responde en menos de 500 ms con 10.000 pagos de prueba y `limit=25`.

## Escenarios BDD

```gherkin
# language: es
Característica: Listar y buscar pagos

  Antecedentes:
    Dado que existen 40 pagos de octubre de 2026, 3 de ellos anulados, de varios medios
    Y que estoy autenticado como "coach"

  Escenario: Veo la primera página de pagos del mes
    Cuando abro la lista de pagos filtrada del 1 al 31 de octubre de 2026
    Entonces veo 25 pagos ordenados del más reciente al más antiguo
    Y el total es 40
    Y cada monto aparece con el formato "$ 120.000"

  Escenario: Filtro solo los anulados por Nequi
    Cuando filtro por medio "nequi" y "voided" verdadero
    Entonces solo veo pagos Nequi con la etiqueta "Anulado"

  Escenario: Busco por referencia
    Cuando busco "nq-778812"
    Entonces veo el pago con referencia "NQ-778812"

  Escenario: Límite fuera de rango
    Cuando pido la lista con "limit" 500
    Entonces la respuesta es 422 con "field" igual a "limit"

  Escenario: Un socio no puede ver la caja
    Dado que estoy autenticado como "member"
    Cuando pido la lista de pagos
    Entonces la respuesta es 403
```

## Endpoints

- `GET /api/v1/payments?q&from&to&method&registered_by&voided&member_id&membership_id&limit&offset` — rol(es): admin, coach — salida: `Page[PaymentRow { id, paid_at, amount_cop, method, reference, voided, void_reason, registered_by, registered_by_name, membership_id, member_id, member_first_name, member_last_name, plan_name }]` — códigos: 200, 401, 403, 422.

## Pantalla

- `Pagos` en `/pagos`: `FilterBar`, `DataTable` (estados de carga, vacío "No hay pagos con estos filtros" y error), `Pagination` que traduce página a `offset`. Filtros en la URL.

## Notas técnicas

- **Migración:** no (índices de `paid_at` y `membership_id` creados en US-095; agregar índice por `registered_by` si la prueba de rendimiento lo pide, con migración propia).
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service con base real (cada filtro, paginación, orden); router (422 de `limit` y `method`, roles); front (filtros en URL, paginación).
- **Archivos principales:** `api/src/app/modules/payments/{service,router,schemas}.py`, `web/src/features/payments/pages/PaymentsPage.tsx`.

## Supuestos

- Supuesto: `q` en pagos busca por referencia exacta (sin distinguir mayúsculas) o por nombre o apellido parcial del socio.
- Supuesto: el nombre del socio y del plan en cada fila se obtienen por `memberships.service` y `members.service`/`plans.service` desde `payments.service` (no desde el router), en una sola llamada por página, para no violar la regla de no encadenar services en un endpoint.

## Dependencias

- US-095 · Registrar pago.
- US-063 · Tabla, paginación, filtros y chips.

## INVEST

- **Independiente:** solo lectura sobre la tabla de pagos.
- **Negociable:** columnas visibles y filtros secundarios.
- **Valiosa:** es la revisión diaria de caja.
- **Estimable:** una consulta paginada y una pantalla de lista estándar.
- **Pequeña:** dos o tres días.
- **Testeable:** cada filtro tiene prueba.

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
- [ ] Revisión de PR aprobada
