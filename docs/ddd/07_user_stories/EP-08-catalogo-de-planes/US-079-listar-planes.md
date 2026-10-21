# US-079 · Como administrador o coach quiero ver la lista de planes para saber qué se vende y a qué precio

- **Épica:** EP-08 · Catálogo de planes
- **Bounded context:** Plans (esquema `plans`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Planes` (`/planes`)

## Historia

Como administrador
quiero ver todos los planes con su precio, tipo, duración y estado, y buscarlos por nombre
para mantener el catálogo al día
(y como coach quiero ver solo los planes activos para poder venderlos)

## Contexto de dominio

- **Aggregate / entidades:** `Plan`.
- **Reglas que aplica:** RN-01 (precio entero mostrado como `$ 120.000`), RN-14 (los planes con `deleted_at` no aparecen), RN-15 (admin ve todo; coach solo `GET /plans?active=true`), regla de datos 6 (paginación y búsqueda).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `plans.service.list(q, active, limit, offset)`, `plans.service.get(id)` (lo consume Memberships), endpoints `GET /plans` y `GET /plans/{id}`.
- **Front:** página `Planes` con `DataTable`, `FilterBar` (búsqueda y filtro Activos/Inactivos/Todos) y `Pagination`. El selector de planes de `Membresia_Vender` (US-084) reutiliza el hook con `active=true`.

## Criterios de aceptación

1. `GET /api/v1/plans` devuelve `{ items, total, limit, offset }`; `limit` acepta 1 a 200 (25 por defecto) y fuera de rango devuelve 422; `offset` negativo devuelve 422.
2. `q` filtra por nombre sin distinguir mayúsculas ni tildes de forma `ILIKE '%q%'`.
3. `active=true` devuelve solo `is_active = true`; `active=false` solo los inactivos; sin `active` devuelve ambos.
4. Los planes con `deleted_at` no nulo nunca aparecen en la lista ni en `GET /plans/{id}` (404).
5. El orden por defecto es por nombre ascendente.
6. `price_cop` sale como entero; el front lo muestra como `$ 120.000` con `format.ts`.
7. Admin puede llamar con cualquier valor de `active`. Coach recibe 200 solo con `active=true`; sin el parámetro o con `active=false` recibe 403. Sin token, 401.
8. `GET /api/v1/plans/{id}` devuelve el plan para admin; para coach solo si está activo (si está inactivo, 403); un id inexistente devuelve 404.
9. Para el coach la entrada "Planes" del menú está oculta (`useCan`); el selector de planes de la venta sí la usa.
10. La tabla muestra estados de carga, vacío ("No hay planes") y error.

## Escenarios BDD

```gherkin
# language: es
Característica: Listar planes

  Antecedentes:
    Dado que existen los planes "Mensual" activo, "Trimestral" activo y "Promo 2025" inactivo

  Escenario: El administrador ve todos los planes
    Dado que estoy autenticado como administrador
    Cuando consulto la lista de planes sin filtro de estado
    Entonces recibo 3 planes ordenados por nombre
    Y el total es 3

  Escenario: El coach ve solo los activos para vender
    Dado que estoy autenticado como coach
    Cuando consulto la lista de planes con "active=true"
    Entonces recibo "Mensual" y "Trimestral"

  Escenario: Límite de página fuera de rango
    Dado que estoy autenticado como administrador
    Cuando consulto la lista de planes con limit 500
    Entonces la respuesta es 422
    Y el error señala el campo "limit"

  Escenario: El coach intenta ver los inactivos
    Dado que estoy autenticado como coach
    Cuando consulto la lista de planes con "active=false"
    Entonces la respuesta es 403

  Escenario: Un plan dado de baja no aparece
    Dado que el plan "Promo 2025" fue dado de baja
    Y que estoy autenticado como administrador
    Cuando consulto la lista de planes
    Entonces "Promo 2025" no está en la lista
```

## Endpoints

- `GET /api/v1/plans?q&active&limit&offset` — rol(es): admin; coach solo con `active=true` — salida: `{ items: PlanOut[], total, limit, offset }` — códigos: 200, 401, 403, 422.
- `GET /api/v1/plans/{id}` — rol(es): admin; coach solo si está activo — salida: `PlanOut` — códigos: 200, 401, 403, 404.

## Pantalla

- `Planes` en `/planes`: tabla con columnas nombre, tipo, precio, duración, clases y estado (`StatusTag` "Activo"/"Inactivo" con texto). Búsqueda y filtro de estado en `FilterBar`.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** índice sobre `plans.plans (is_active) WHERE deleted_at IS NULL`.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service con base real (filtros, baja lógica, orden); router (matriz de rol admin/coach/sin token, 422 de paginación); front (tabla y filtros).
- **Archivos principales:** `api/src/app/modules/plans/{service,router,schemas}.py`, `web/src/features/plans/{api.ts,pages/PlansPage.tsx}`.

## Supuestos

- Supuesto: el coach obtiene 403 (no una lista filtrada en silencio) si pide planes sin `active=true`, porque el contrato de `05_service_design.md` le permite solo esa consulta.

## Dependencias

- US-078 · Crear plan (tabla y modelo)
- US-063 · DataTable, Pagination, FilterBar y Chips

## INVEST

- **Independiente:** solo lee la tabla creada en US-078.
- **Negociable:** columnas y orden visibles se pueden ajustar.
- **Valiosa:** el admin gestiona su catálogo y el coach puede vender.
- **Estimable:** lectura simple con filtros conocidos.
- **Pequeña:** uno a dos días.
- **Testeable:** filtros y matriz de roles con respuestas exactas.

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
