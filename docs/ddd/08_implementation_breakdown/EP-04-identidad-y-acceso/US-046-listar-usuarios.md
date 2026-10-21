# US-046 · Listar usuarios — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-046-listar-usuarios.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth (`api/src/app/modules/auth/`, `web/src/features/system/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El contrato de la lista (filtros, paginación, campos y rol) está definido. Hay una decisión técnica de este desglose que la propia historia deja abierta en su supuesto: `last_login_at` se guarda en una columna de `auth.users`, en lugar de calcularlo desde la auditoría. Así se evita un ciclo de dependencias entre `auth.service` y `audit.service`, porque US-102 ya llama de audit a auth. La columna entra en la migración `0004_auth`, que todavía no está aplicada, así que no hace falta otra migración.

## Resumen

`auth.service.list_users(q, role, status, limit, offset)` devuelve `{items, total, limit, offset}` ordenado por `email` ascendente. Cada ítem trae `id`, `email`, `role`, `status`, `member_id`, `last_login_at` y `created_at`. Sin filtro de estado, excluye a los usuarios borrados. El usuario técnico `SYSTEM_USER_ID` nunca aparece. `status` se calcula con la función pura `user_status`. El front crea la pantalla `Usuarios` en `/sistema/usuarios` con `PageHeader`, `FilterBar`, `DataTable`, `Pagination` y `StatusTag` con texto, y el `SideNav` oculta la entrada al coach.

## Correcciones aplicadas por DECISIONES.md

- El usuario técnico `system@apex.local` no se lista ni cuenta en `total`, porque es un actor técnico y no una persona con acceso. Es una decisión de este desglose coherente con DECISIONES N-15 (no puede iniciar sesión ni es "admin activo").
- Criterio 6 ("`last_login_at` sale de la última auditoría `login`") → sale de la columna `auth.users.last_login_at`, que se actualiza en el login correcto (US-042). El valor es el mismo y no hay dependencia circular con `audit.service`. No es una corrección de DECISIONES.md: es la alternativa que la historia prevé en su supuesto, y se anota aquí para que se revise en el gate.
- Paginación con `limit` de 1 a 200 (25 por defecto) y `offset`: coincide con DECISIONES D2, sin cambio.

## Validación contra el dominio

- La entidad es `User`.
- RN-14: los usuarios borrados no aparecen por defecto; con `status=deleted`, sí.
- Función pura: `user_status(user) -> "active" | "locked" | "pending_activation" | "deleted"`, con este orden de prioridad:
  - `deleted_at` → `deleted`;
  - `locked_at` → `locked`;
  - `password_hash IS NULL` → `pending_activation`;
  - en cualquier otro caso → `active`.
- Equivalencia con el criterio 5: un usuario sin `password_hash` nunca activó ni inició sesión. Además, `create_user` (US-047) y `resend_link` (US-052) le dejan siempre exactamente un `OneTimeToken(activate)` con `used_at` nulo. Así se evita una subconsulta por fila.
- No emite ni consume eventos.

## Validación contra la arquitectura

- El módulo dueño es `modules/auth`, que solo consulta su propio esquema. No llama a otros services.
- Rol: `require_role("admin")`. El coach recibe 403 y una petición sin token, 401.
- Paginación con el contrato común de US-019 (`PageParams` y `Page[T]`). Un `limit` de 201 o negativo responde 422 con `field: "limit"`.
- `q` usa `ILIKE` con `%`, `_` y `\` escapados. El filtro `status` se traduce a condiciones SQL equivalentes a `user_status`.
- Sin datos cifrados (P5) y sin auditoría, porque es una lectura.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (`last_login_at` ya está en `0004_auth`, US-041).

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `user_status(user: User) -> UserStatus` y su traducción a SQL `status_filter(status: UserStatus) -> ColumnElement[bool]` en `auth/service.py`. — 0.5 h
- [ ] T2 · `list_users(session, *, q: str | None, role: Role | None, status: UserStatus | None, limit: int, offset: int) -> Page[UserRow]`:
  - excluye `SYSTEM_USER_ID`;
  - sin `status`, aplica `deleted_at IS NULL`;
  - calcula `total` con `count(*) OVER ()` o con una consulta aparte;
  - ordena por `email ASC`. — 2 h

### Schemas
- [ ] T3 · `UserRow` (`id`, `email`, `role`, `status`, `member_id`, `last_login_at`, `created_at`) y `UserListQuery` (`q`, `role: Role | None`, `status: UserStatus | None`, más `limit` y `offset` de US-019), en `auth/schemas.py`. — 0.5 h

### Router
- [ ] T4 · `GET /api/v1/users` con `require_role("admin")` en `auth/router.py` (prefijo `/users`). Códigos: 200, 401, 403 y 422. — 0.75 h

### Tests unitarios puros
- [ ] T5 · `api/tests/auth/test_pure_user_status.py`: todas las combinaciones de `deleted_at`, `locked_at` y `password_hash`, con la prioridad documentada. — 0.5 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/auth/test_list_users.py`, con los usuarios del escenario BDD:
  - sin filtro, 3 ítems;
  - `status=deleted` devuelve solo `viejo@apex.co`;
  - `role=coach`;
  - `q="APEX"` sin distinguir mayúsculas, y `q="_"` escapado;
  - el orden es por correo;
  - el usuario técnico no aparece;
  - `last_login_at` refleja el login hecho con la función de US-042. — 1.5 h

### Tests de router
- [ ] T7 · `api/tests/auth/test_users_list_router.py`:
  - el coach recibe 403 y sin token, 401;
  - `limit=500` y `limit=-1` responden 422 con `field: "limit"`;
  - `status=otro` responde 422;
  - la respuesta no contiene `password_hash` ni tokens. — 1 h

### Tests de arquitectura
- [ ] T8 · Que `test_every_route_has_role.py` y `test_no_cross_models.py` sigan verdes. — 0.1 h

### Front
- [ ] T9 · Hook `useUsers(filters)` (`useQuery` con la clave `["users", filters]`) en `web/src/features/system/api.ts`, esquema Zod de la respuesta en `web/src/features/system/schemas.ts`, y filtros en la URL (`q`, `role`, `status`, `offset`). — 0.75 h
- [ ] T10 · `web/src/features/system/pages/UsersPage.tsx`:
  - `PageHeader` "Usuarios" con el botón "Nuevo usuario" (la acción la conecta US-047);
  - `FilterBar` con búsqueda, rol y estado;
  - `DataTable` con correo, rol, `StatusTag` (Activo, Bloqueado, Pendiente de activación, Dado de baja; texto y color de token), último acceso en hora de Bogotá con `core/i18n/format.ts`, y fecha de creación;
  - `Pagination`;
  - estados de carga, vacío ("No hay usuarios con estos filtros") y error;
  - ruta `/sistema/usuarios` con la acción `users.manage` (US-040), y el `SideNav` la oculta con `<Can>`. — 3 h
- [ ] T11 · Vitest `web/src/features/system/pages/UsersPage.test.tsx`: con datos, vacío, error, la etiqueta de estado con texto y la entrada de `SideNav` que no aparece para coach. — 1.25 h

### DevOps
- No aplica.

### Seguridad
- [ ] T12 · Revisión: solo admin, sin `password_hash` ni tokens en la salida, `ILIKE` escapado, y el usuario técnico oculto. — 0.25 h

## Orden de ejecución
1. T5 (en rojo)
2. T1
3. T6 (en rojo)
4. T3
5. T2
6. T7 (en rojo)
7. T4
8. T8
9. T11 (en rojo)
10. T9 y T10
11. T12

## Dependencias técnicas
- US-041 · Cuentas de usuario: las tablas y la columna `last_login_at`.
- US-042 · Iniciar sesión: actualiza `last_login_at`.
- US-034 · current_user y require_role.
- US-019 · Contrato de paginación.
- US-040 · Matriz de permisos del front: la acción `users.manage`.
- US-061 · Panel layout, TopBar y SideNav, y US-063 · Tabla, paginación, filtros y chips.

## Endpoints
- `GET /api/v1/users` — roles: admin

## Riesgos
- Que `last_login_at` sea columna y no auditoría puede divergir del texto del criterio 6. Mitigación: el valor observable es el mismo y se anota para el gate. Si el gate exige leerlo de la auditoría, la alternativa sin ciclo es una consulta en `core/audit.py` (núcleo compartido) y no en `audit.service`.
- US-051 agrega `active_sessions` a esta respuesta. Si las dos historias se hacen en sprints distintos, el esquema de la respuesta cambia. Mitigación: el campo es aditivo y los tipos del front se regeneran desde `docs/openapi.json`.
- Front condicionado a D1.

## Estimación
- Backend: 3.75 h
- Front: 5 h
- Pruebas: 3.1 h
- DevOps / seguridad: 0.25 h
- **Total: 12 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/auth/test_pure_user_status.py tests/auth/test_list_users.py tests/auth/test_users_list_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system/pages/UsersPage.test.tsx`
- [ ] `curl -H 'Authorization: Bearer <admin>' 'http://localhost/api/v1/users?limit=500'` responde 422 con `field: "limit"`, y `curl -H 'Authorization: Bearer <coach>' http://localhost/api/v1/users` responde 403.
- [ ] `curl -H 'Authorization: Bearer <admin>' 'http://localhost/api/v1/users?q=system'` no devuelve `system@apex.local`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.auth --cov-fail-under=80`
