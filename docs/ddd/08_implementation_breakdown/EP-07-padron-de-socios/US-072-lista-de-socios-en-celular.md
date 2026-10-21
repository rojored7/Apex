# US-072 · Lista de socios en celular — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-07-padron-de-socios/US-072-lista-de-socios-en-celular.md`
- **Épica:** EP-07 · Padrón de socios
- **Bounded context / módulo:** Members, solo presentación (`web/src/features/members/`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Es una variante de presentación sobre el API de US-070 y US-071; no toca backend ni contrato. La historia ya cumple N-01 (la tarjeta no muestra datos sensibles, ni enmascarados). El mecanismo "Cargar más" es un supuesto de presentación que no cambia contrato.

## Resumen

- En anchos menores a 768 px, `MembersListPage` cambia la tabla por tarjetas (nombre, `StatusTag` de membresía y plan).
- Búsqueda fija arriba, chips desplazables dentro de su contenedor, botón "Cargar más" que acumula páginas (`offset += limit`) y botón flotante "Nuevo socio" según permiso.
- Sin desplazamiento horizontal de la página en 320 y 390 px; cada tarjeta es un destino enfocable de al menos 44 px.

## Correcciones aplicadas por DECISIONES.md

- Ninguna corrección de contenido: la historia ya dice que la tarjeta no muestra datos sensibles ni enmascarados, coherente con DECISIONES N-01.
- Consecuencia de DECISIONES N-20 heredada de US-071: el chip "Dados de baja" también aparece en celular para admin y coach; una tarjeta de un socio dado de baja lleva la etiqueta "Dado de baja" y abre la ficha en solo lectura.

## Validación contra el dominio

- Lectura de `Member` con `membership_status` y `plan_name` ya resueltos por el API. Sin reglas, eventos ni funciones puras nuevas. Sin discrepancias.

## Validación contra la arquitectura

- No hay cambios en `api/`. Consume `GET /api/v1/members` (US-070 y US-071) con `limit`/`offset` (S2).
- Front en `web/src/features/members/components/` con hooks de TanStack Query; tokens de color y tamaño, nada literal.
- Permisos con `useCan("member.create")` de la matriz de US-040.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- No aplica.

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- No aplica.

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- No aplica (siguen en verde las pruebas de `api/tests/architecture`, que esta historia no toca).

### Front
- [ ] T1 · `web/src/features/members/components/MemberCardList.tsx`: tarjeta por socio con nombre, `StatusTag` (texto más color) y plan; toda la tarjeta es un enlace a `/socios/:id` de al menos 44 px; etiqueta "Dado de baja" cuando `deleted_at` no es nulo; sin ningún campo sensible — 2.5 h
- [ ] T2 · `MembersListPage.tsx`: alternar tabla y tarjetas con un hook `useMediaQuery("(max-width: 767px)")` del kit; búsqueda fija arriba; contenedor de chips con `overflow-x: auto` propio (la página no desborda) — 1 h
- [ ] T3 · `web/src/features/members/api.ts`: `useMembersInfinite(params)` con `useInfiniteQuery` (`getNextPageParam = offset + limit < total ? offset + limit : undefined`); "Cargar más" agrega resultados y desaparece al llegar a `total`; si la página siguiente falla, conserva las tarjetas y muestra error con "Reintentar" — 1.5 h
- [ ] T4 · Botón flotante "Nuevo socio" visible solo con `useCan("member.create")` — 0.5 h
- [ ] T5 · Vitest `web/src/features/members/components/MemberCardList.test.tsx` con `matchMedia` simulado: tarjetas en móvil, "Cargar más" acumulativo, error en la segunda página, botón según permiso — 1.5 h
- [ ] T6 · Playwright `web/tests/e2e/members-mobile.spec.ts` a 390 × 844 y 320 × 640: buscar "laura" y abrir la ficha, "Cargar más" dos veces con 60 socios, `document.documentElement.scrollWidth <= innerWidth`, capturas en claro y oscuro — 1.5 h

### DevOps
- No aplica.

### Seguridad
- [ ] T7 · Revisión de que la tarjeta y la caché de TanStack Query no guardan campos sensibles (la respuesta de lista no los trae por N-01; verificar que el tipo generado desde `docs/openapi.json` tampoco) — 0.5 h

## Orden de ejecución

1. T5 (pruebas en rojo).
2. T3, T1 y T2.
3. T4.
4. T6 y T7.

## Dependencias técnicas

- US-070 · Buscar y listar socios: endpoint y `MembersListPage`.
- US-071 · Filtrar socios por estado de membresía y plan: chips y `plan_name`.
- US-063 · Tabla, paginación, filtros y chips (kit).
- US-040 · Matriz de permisos del front: `useCan`.

## Endpoints

- `GET /api/v1/members` — roles: admin, coach

## Riesgos

- Los chips desplazables pueden generar desbordamiento horizontal de la página en 320 px — mitigación: el desplazamiento vive en el contenedor y T6 mide `scrollWidth`.
- La lista acumulada pierde coherencia si cambian los filtros a mitad de carga — mitigación: la clave de consulta incluye los filtros y cambiar uno reinicia el acumulado.
- Front condicionado a D1: si el gate no aprueba el front en `web/`, la historia entera sale de este repositorio.

## Estimación

- Backend: 0 h
- Front: 8.5 h
- Pruebas: 0 h
- DevOps / seguridad: 0.5 h
- **Total: 9 h**

Las pruebas de front (T5 y T6) se cuentan dentro de Front.

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .` (sin cambios en `api/`, debe seguir en verde)
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/members/components/MemberCardList.test.tsx`
- [ ] `cd web && npx playwright test tests/e2e/members-mobile.spec.ts`
- [ ] A 320 px, la captura de Playwright no muestra barra de desplazamiento horizontal de la página.
- [ ] Ninguna tarjeta contiene texto con `•` ni dígitos de documento o teléfono.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npm test -- --coverage src/features/members`
