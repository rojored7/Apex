# US-091 · Como administrador o coach quiero ver y filtrar las membresías por estado, plan y fecha de vencimiento para saber quién vence esta semana y a quién cobrar

- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context:** Memberships (esquema `memberships`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Membresias` (`/membresias`)

## Historia

Como administrador o coach
quiero una lista de membresías con filtros por estado, plan, rango de vencimiento y búsqueda por socio
para encontrar en segundos a los que vencen esta semana o están pendientes de pago

## Contexto de dominio

- **Aggregate / entidades:** `Membership`.
- **Reglas que aplica:** RN-06/Q11 (estados), Q3 ("Pendiente de pago" visible con borde y texto `--warning`), regla de datos 6 (paginación y búsqueda), fechas como fecha civil.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna nueva

## Alcance

- **Backend:** `memberships.service.list(status, q, plan_id, ends_from, ends_to, member_id, limit, offset)` y `get(id)`; `q` se resuelve con `members.service.search_ids(q)` (supuesto) para no hacer join entre esquemas; nombres de socio y plan se completan con `members.service` y `plans.service` por lote. Endpoints `GET /memberships` y `GET /memberships/{id}`.
- **Front:** página `Membresias` con `Chips` de estado (Al día, Por vencer, Vencidas, Congeladas, Pendiente de pago, Canceladas), filtro de plan, rango "Vence entre", búsqueda, `DataTable` y `Pagination`; acciones por fila Renovar, Congelar y Anular (esta solo admin).

## Criterios de aceptación

1. `GET /api/v1/memberships` responde `{ items, total, limit, offset }`; `limit` 1 a 200 (25 por defecto); fuera de rango 422.
2. `status` acepta uno o varios valores separados por coma entre `pending_payment`, `active`, `expiring`, `expired`, `frozen`, `cancelled`; un valor desconocido devuelve 422.
3. `ends_from` y `ends_to` filtran por `end_date` inclusive (fechas `AAAA-MM-DD`); `ends_from > ends_to` devuelve 422.
4. `q` busca por nombre, documento o teléfono del socio usando el mismo mecanismo de búsqueda del padrón (índice ciego o `ILIKE` en nombre); nunca descifra la tabla.
5. Cada ítem trae `id`, `member_id`, `member_name` (nombre y apellido en claro), `plan_id`, `plan_name`, `agreed_price_cop` (entero), `start_date`, `end_date`, `classes_remaining`, `status`.
6. Orden por defecto: `end_date` ascendente.
7. `GET /api/v1/memberships/{id}` devuelve el detalle con datos de congelación y cancelación; 404 si no existe.
8. Roles: admin y coach; `member` 403; sin token 401.
9. Respuesta en menos de 500 ms con 1.000 socios y sus membresías (volumen de `01_product_discovery.md` 6).
10. En el front, el chip "Pendiente de pago" usa los tokens `--warning`; el `StatusTag` siempre lleva texto; el botón Anular no aparece para el coach; la fecha se muestra `31 oct 2026` y el precio `$ 120.000`.

## Escenarios BDD

```gherkin
# language: es
Característica: Listar membresías

  Antecedentes:
    Dado que hoy en Bogotá es 2026-10-26
    Y existen 3 membresías "expiring" que vencen entre el 2026-10-27 y el 2026-11-01
    Y 2 membresías en "pending_payment"
    Y que estoy autenticado como coach

  Escenario: Ver las que vencen esta semana
    Cuando filtro membresías con estado "expiring" y vencimiento entre 2026-10-26 y 2026-11-01
    Entonces recibo 3 membresías ordenadas por fecha de fin
    Y cada una trae el nombre del socio y del plan

  Escenario: Ver las pendientes de pago
    Cuando filtro membresías con estado "pending_payment"
    Entonces recibo 2 membresías

  Escenario: Rango de fechas invertido
    Cuando filtro membresías con vencimiento entre 2026-11-01 y 2026-10-26
    Entonces la respuesta es 422

  Escenario: Estado desconocido
    Cuando filtro membresías con estado "vigente"
    Entonces la respuesta es 422
    Y el error señala el campo "status"

  Escenario: Socio del portal denegado
    Dado que estoy autenticado con rol "member"
    Cuando consulto la lista de membresías
    Entonces la respuesta es 403
```

## Endpoints

- `GET /api/v1/memberships?status&q&plan_id&ends_from&ends_to&member_id&limit&offset` — rol(es): admin, coach — salida: `{ items: MembershipRow[], total, limit, offset }` — códigos: 200, 401, 403, 422.
- `GET /api/v1/memberships/{id}` — rol(es): admin, coach — salida: `MembershipOut` — códigos: 200, 401, 403, 404.

## Pantalla

- `Membresias` en `/membresias`: chips, filtros, tabla, paginación y acciones por fila (los modales de congelar y anular son US-089 y US-090). Estados de carga, vacío ("No hay membresías con estos filtros") y error. `// DESIGN-GAP:` chip "Pendiente de pago" (Q3).

## Notas técnicas

- **Migración:** no; índice `memberships.memberships (status, end_date)`.
- **Trigger / restricciones:** no.
- **Funciones puras a probar:** ninguna nueva.
- **Pruebas:** service con base real (filtros combinados, orden, búsqueda vía members); router (roles, 422); prueba de arquitectura (sin join entre esquemas); prueba de tiempo con 1.000 socios; front (chips y filtros en URL).
- **Archivos principales:** `api/src/app/modules/memberships/{service,router,schemas}.py`, `web/src/features/memberships/pages/MembershipsPage.tsx`.

## Supuestos

- Supuesto: `members.service` expone `search_ids(q) -> list[UUID]` y `names_for(ids)` para que Memberships filtre y muestre nombres sin join cruzado.

## Dependencias

- US-084 · Vender membresía
- US-063 · DataTable, Pagination, FilterBar y Chips
- US-069 / US-070 deben exponer members.service.search_ids(q) y names_for(ids) (evitan el join entre esquemas; agregado en consolidación)

## INVEST

- **Independiente:** solo lectura sobre la tabla de membresías.
- **Negociable:** columnas, orden por defecto y chips.
- **Valiosa:** es la vista diaria de cobro y vencimientos.
- **Estimable:** filtros conocidos.
- **Pequeña:** tres días.
- **Testeable:** conteos exactos por filtro.

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
