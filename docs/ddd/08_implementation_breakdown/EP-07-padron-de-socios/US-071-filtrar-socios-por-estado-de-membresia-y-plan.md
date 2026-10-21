# US-071 · Filtrar socios por estado de membresía y plan — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-07-padron-de-socios/US-071-filtrar-socios-por-estado-de-membresia-y-plan.md`
- **Épica:** EP-07 · Padrón de socios
- **Bounded context / módulo:** Members, Conformist de Memberships (`api/src/app/modules/members/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**ARCHITECTURAL_GAP_DETECTED**

La columna `plan_name` de cada fila obliga a que una lectura de `members` componga tres módulos (members → memberships → plans), y eso solo está permitido en `dashboard`, `portal` y `tv`. Además, el contrato que la historia consume no coincide con el que define US-092: `status_for` devuelve solo el estado (sin plan) y `member_ids_by_status` no está en el alcance de US-092, solo en su lista de dependencias. El filtro por estado, en cambio, sí tiene solución dentro de las reglas (ver "Preguntas abiertas").

## Resumen

- `GET /api/v1/members` acepta `membership_status` (`active`, `expiring`, `expired`, `frozen`, `pending_payment`, `none`) y `plan_id`, además de los filtros de US-070.
- Para filtrar, `members.service.list` pide a `memberships.service.member_ids_by_status(...)` el conjunto de socios que cumplen y pagina en su propio esquema; para pintar la página pide `memberships.service.status_for(ids)` una sola vez por página. Nunca hace `JOIN` con `memberships`.
- Cada `MemberRow` trae `membership_status` y `plan_name`.
- Front: chips de estado (incluido "Pendiente de pago", Q3, y "Dados de baja" para admin y coach, N-20), selector de plan y `StatusTag` con texto.
- Resuelve el ciclo de imports members ↔ memberships con import perezoso documentado y una prueba de arquitectura nueva.

## Correcciones aplicadas por DECISIONES.md

- El criterio 8 y el escenario "Coach no ve dados de baja" dicen que el chip "Dados de baja" es solo para admin y que el coach recibe 403 con `status=deleted` → el chip se muestra a admin y coach, y el API responde 200 a ambos: corregido por DECISIONES N-20.
- La historia ya incorpora Q1 (vigente más futura), Q3 (chip "Pendiente de pago" con estilo `--warning`), Q11 (`expiring_days` de Settings) y Q28 (el "hoy" es `today_bogota()`); se mantienen tal cual.
- El estado resuelto por socio sigue la prioridad de US-092 (vigente > `pending_payment` > `expired` > `none`), coherente con N-26.

## Validación contra el dominio

- Lectura derivada `membership_status` del socio (`02_domain_model.md` 2.1): la calcula `memberships`, no `members`. Correcto.
- RN-06 con `expiring_days` (Q11), Q1, Q3 y RN-14: los aplica `memberships.service.resolve_member_status` (US-092); `members` solo traduce chips a filtros.
- Función pura nueva: `chip_to_filter(chip) -> MemberChipFilter` (siete chips).
- Sin eventos. Sin discrepancias de dominio.

## Validación contra la arquitectura

- `members.service` llama a `memberships.service` (Customer/Supplier documentado en `03_context_map.md` 2: "Members pide a Memberships `membership_status_for(member_ids)`"). Sin imports de `memberships.models` ni `JOIN` entre esquemas (US-022).
- Ciclo de imports: `memberships.service` importa `members.service` a nivel de módulo (validar socio en `sell`, US-084) y `members.service` necesita `memberships.service` para la lista. Solución sin violar reglas: el sentido minoritario (members → memberships) se importa de forma perezosa dentro de la función (`from app.modules.memberships import service as memberships_service` en el cuerpo de `list` y de `get`), con comentario `# lazy: ciclo documentado members↔memberships` y `# noqa: PLC0415` si ruff tiene activa esa regla. Una prueba de arquitectura nueva garantiza que el grafo de imports de nivel de módulo entre `modules/*/service.py` es acíclico y que los imports perezosos solo existen en los pares permitidos. Es un riesgo controlado, no una brecha.
- Brecha: decorar la fila con `plan_name` exige un tercer módulo (`plans`) en una lectura fuera de `dashboard`/`portal`/`tv`.
- Rol: `require_role("admin", "coach")`. Paginación de US-019 intacta (el filtro reduce el universo antes de paginar).

## Preguntas abiertas

- Brecha 1 · `plan_name` en la lista: la fila necesita el nombre del plan de la membresía que determina el estado. Propuesta por defecto: `memberships.service.status_for(member_ids)` devuelve `dict[UUID, MemberMembershipStatus]` con `status`, `plan_id` y `plan_name`, y `memberships` resuelve los nombres con `plans.service.names_for(plan_ids)` (arista memberships → plans ya existente, Conformist). `members` sigue llamando a un solo service. Se documenta en `03_context_map.md` sección 5 que una lectura puede recorrer aristas ya existentes del mapa hasta profundidad 2 para decorar filas, sin escribir nada. Alternativa: quitar `plan_name` de la fila y mostrarlo solo en la ficha (cambia el alcance de la historia; requiere el gate).
- Brecha 2 · contrato con US-092: US-092 define `status_for(member_ids) -> dict[UUID, status]` y no tiene `member_ids_by_status` en su alcance. Propuesta: agregar a US-092 `member_ids_by_status(statuses: frozenset[MemberMembershipStatusValue], plan_id: UUID | None) -> set[UUID]` (excluye `none`; para `none` members usa `NOT IN` del conjunto de todos los estados resueltos) y ampliar `status_for` como en la brecha 1. Ambos calculan "hoy" con `today_bogota()` y `expiring_days` dentro de `memberships`.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `chip_to_filter(chip: MemberChip) -> MemberChipFilter` para "Al día" (`active`), "Por vencer" (`expiring`), "Vencidos" (`expired`), "Congelados" (`frozen`), "Pendiente de pago" (`pending_payment`), "Sin membresía" (`none`) y "Dados de baja" (`status=deleted`) — 1 h
- [ ] T2 · Ampliar `members.service.list` con `membership_status` y `plan_id`: import perezoso de `memberships.service` dentro de la función; para un estado distinto de `none` filtra `id = ANY(:ids)` con `member_ids_by_status({estado}, plan_id)`; para `none` filtra `id <> ALL(:ids)` con todos los estados resueltos y, si viene `plan_id`, devuelve página vacía (sin vigente no hay plan); combina con `q`, `status` y `sort` de US-070 — 3 h
- [ ] T3 · Decorar la página: una sola llamada `status_for(ids_de_la_página)` (máximo 200 ids) que llena `membership_status` y `plan_name` de cada fila; un socio sin entrada queda `none` — 1.5 h

### Schemas
- [ ] T4 · `MemberListQuery.membership_status: Literal["active","expiring","expired","frozen","pending_payment","none"] | None` y `plan_id: UUID | None`; `MemberRowOut.membership_status` y `plan_name` ya declarados en US-070 — 0.5 h

### Router
- [ ] T5 · `GET /api/v1/members` con los dos parámetros nuevos; 422 con `field = "membership_status"` o `field = "plan_id"` (no UUID); un `plan_id` inexistente devuelve lista vacía — 0.5 h

### Tests unitarios puros
- [ ] T6 · `api/tests/members/test_chip_to_filter.py`: los siete chips y un chip desconocido — 0.5 h

### Tests de service con PostgreSQL
- [ ] T7 · `api/tests/members/test_service_list_membership_filters.py` con `FrozenClock` en 2026-10-20 Bogotá y `expiring_days = 7`: "por vencer" (fin 25 de octubre) frente a "al día" (fin 30 de noviembre); `pending_payment`; `none`; vigente más futura muestra la vigente; filtro por plan de la vigente; plan inexistente da vacío; usa el `memberships.service` real cuando exista US-092 y un doble inyectado con `monkeypatch` antes — 2.5 h

### Tests de router
- [ ] T8 · `api/tests/members/test_router_list_filters.py`: 422 de `membership_status = "moroso"` y de `plan_id` no UUID; 200 de coach con `status=deleted` (N-20); `plan_name` presente en cada fila — 1 h

### Tests de arquitectura
- [ ] T9 · `api/tests/architecture/test_service_import_cycles.py`: analiza con `ast` cada `app/modules/*/service.py`, arma el grafo de imports de nivel de módulo hacia `app.modules.<x>.service` y falla si tiene ciclos; lista los imports dentro de funciones y falla si alguno no está en `ALLOWED_LAZY = {("members", "memberships")}` (US-082 agrega `("plans", "memberships")`) o si apunta a algo distinto de `service`; además importa cada `service.py` en un subproceso limpio para detectar `ImportError` por ciclo. `test_no_cross_models.py` (US-022) sigue en verde — 1.5 h

### Front
- [ ] T10 · `web/src/features/members/components/MemberStatusChips.tsx` (`Chips` del kit con `aria-pressed`, siete chips con texto; "Dados de baja" para admin y coach) y selector de plan con `usePlans({ active: true })` de `features/plans/api.ts`; columna Membresía con `StatusTag` (texto más color, "Pendiente de pago" con el token `--warning`); chip y plan en la URL; cambiarlos reinicia `offset`; `// DESIGN-GAP:` chip "Pendiente de pago" (Q3) — 2.5 h
- [ ] T11 · Vitest `web/src/features/members/components/MemberStatusChips.test.tsx`: URL, reinicio de offset, `aria-pressed`, etiqueta con texto — 1.5 h

### DevOps
- [ ] T12 · `docs/openapi.json` regenerado con los parámetros nuevos — 0.5 h

### Seguridad
- [ ] T13 · Revisar que el conjunto de ids devuelto por `member_ids_by_status` nunca salga en la respuesta ni en logs, y que el filtro no permita enumerar socios por plan a un rol sin permiso (solo admin y coach) — 0.5 h

## Orden de ejecución

1. T6 (en rojo) y T1.
2. T9 (prueba de ciclos en rojo con el import perezoso aún ausente).
3. T4, luego T7 (en rojo), T2 y T3.
4. T5 y T8.
5. T12 y T13.
6. T10 y T11.

## Dependencias técnicas

- US-070 · Buscar y listar socios: `list`, `MemberRowOut`, `MemberListQuery`.
- US-092 · Resumen y consultas de estado: `status_for` ampliado y `member_ids_by_status` (brecha 2).
- US-084 · Vender membresía: es quien crea el import de nivel de módulo memberships → members; la prueba T9 vigila el ciclo desde que existan los dos.
- US-079 · Listar planes: `usePlans({ active: true })` para el selector.
- US-022 · Prueba de arquitectura sin models cruzados.
- US-013 · Reloj y fecha de Bogotá: `FrozenClock` en las pruebas.

## Endpoints

- `GET /api/v1/members` — roles: admin, coach

## Riesgos

- Ciclo de imports members ↔ memberships: un import de nivel de módulo en el sentido equivocado rompe el arranque con `ImportError` — mitigación: import perezoso documentado y T9, que falla en CI ante cualquier ciclo nuevo.
- El conjunto de ids crece con el padrón (hasta 1.000 socios): pasa como parámetro `ANY(:ids)` — mitigación: aceptable al volumen de `01_product_discovery.md` sección 6; medir junto con la prueba de 500 ms de US-070.
- Si el gate rechaza la composición de profundidad 2, `plan_name` sale de la fila — mitigación: el resto de la historia no depende de esa columna.
- Front condicionado a D1.

## Estimación

- Backend: 6.5 h
- Front: 4 h
- Pruebas: 5.5 h
- DevOps / seguridad: 1 h
- **Total: 17 h**

Supera en 2 h la referencia de 3 puntos por la prueba de arquitectura de ciclos, que también sirve a US-073 y US-082.

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/members/test_chip_to_filter.py -q`
- [ ] `cd api && uv run pytest tests/members/test_service_list_membership_filters.py -q`
- [ ] `cd api && uv run pytest tests/members/test_router_list_filters.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/members/components`
- [ ] `grep -rn "memberships.models" api/src/app/modules/members` no devuelve nada.
- [ ] `cd api && uv run python -I -c "import app.modules.members.service, app.modules.memberships.service"` termina sin error en los dos órdenes de import.
- [ ] `curl "/api/v1/members?membership_status=pending_payment"` devuelve solo socios con membresía vendida sin cobertura completa.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.members --cov-fail-under=80`
