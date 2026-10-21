# US-049 · Editar y dar de baja usuario — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-049-editar-y-dar-de-baja-usuario.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth (`api/src/app/modules/auth/`, `web/src/features/system/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Están definidos los tres endpoints, la baja lógica con revocación de sesiones, el 409 `last_admin` y el 409 por correo repetido. Con DECISIONES N-15 queda claro qué cuenta como "admin activo": el usuario técnico, con `is_active = false`, no cuenta. No queda ningún supuesto abierto.

## Resumen

Esta historia agrega tres funciones a `auth.service`:

- `get_user(id)`: devuelve también los usuarios borrados, para verlos desde el filtro `deleted`.
- `update_user(id, email?, role?, by)`: aplica la regla de correo único y la regla del último admin.
- `delete_user(id, by)`: es una baja lógica (`deleted_at`). Revoca todos los refresh tokens en la misma transacción y emite `SessionsRevoked(reason="delete")`.

La comprobación del último admin bloquea con `SELECT ... FOR UPDATE` las filas de los admins activos. El front agrega la acción "Editar" (`SidePanel`) y la acción "Dar de baja" (`ConfirmModal`), que no aparece sobre el propio usuario.

## Correcciones aplicadas por DECISIONES.md

- "Único admin activo" excluye al usuario técnico `system@apex.local`. Tiene `is_active = false` y no cuenta como último admin activo, así que no salva la baja del único admin humano: corregido por DECISIONES N-15.
- El usuario técnico no se puede ver, editar ni dar de baja desde estos endpoints: responden 404, igual que en la lista de US-046. Es una decisión del desglose coherente con N-15.

## Validación contra el dominio

- Entidades: `User` y `RefreshToken`.
- RN-14: la baja es lógica y la fila se conserva. No existe `DELETE` físico (prueba de US-041).
- Invariante "no se puede borrar el último admin activo". Se aplica con la función pura `would_remove_last_admin(active_admin_ids: frozenset[UUID], target_id: UUID, *, new_role: Role | None, deleting: bool) -> bool`. "Admin activo" es `is_active_admin` de US-041: rol `admin`, `is_active`, sin `locked_at`, sin `deleted_at` y con `password_hash`.
- S7: si se cambia el rol a `member` sin `member_id`, responde 422 con `field: "member_id"` (`validate_user_role`). La pantalla no ofrece ese cambio.
- Evento que se emite: `SessionsRevoked(user_id, by, revoked=n, reason="delete")`. No consume eventos.

## Validación contra la arquitectura

- El módulo dueño es `modules/auth` y las rutas usan `require_role("admin")`.
- Auditoría: el hook registra `update` sobre `users` con antes y después, incluida la baja (`deleted_at`, que US-016 trata como `update`). `SessionsRevoked` lo audita US-107.
- Concurrencia: dos bajas o dos cambios de rol simultáneos podrían dejar el sistema sin admin. `_lock_active_admins(session)` hace `SELECT id ... FOR UPDATE` en orden de `id`, para evitar deadlocks.
- Un correo repetido entre usuarios no borrados responde 409 `email_taken` con `field` y `existing_id`. El índice único parcial resuelve la carrera.
- Que un cambio de rol tenga efecto inmediato depende de que `current_user` (US-034) tome el rol de la base y no solo del claim del token. Ver riesgos.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `would_remove_last_admin(active_admin_ids, target_id, *, new_role, deleting) -> bool` en `auth/service.py`. Es verdadera si el objetivo está entre los admins activos, es el único y se le quita el rol o se le da de baja. La comparte US-050. — 0.5 h
- [ ] T2 · Helpers:
  - `_get_alive_or_404(session, user_id, *, include_deleted=False) -> User`, que excluye `SYSTEM_USER_ID`;
  - `_lock_active_admins(session) -> frozenset[UUID]`.

  Caso de uso `get_user(session, user_id) -> User`, que incluye a los borrados. — 0.75 h
- [ ] T3 · `update_user(session, user_id, *, email: str | None, role: Role | None, by: UUID) -> User`:
  - devuelve 404 si el usuario está borrado;
  - normaliza el correo y verifica que no esté repetido (`EmailTaken`);
  - si cambia el rol, aplica `validate_user_role` con el `member_id` actual y comprueba `would_remove_last_admin` (`LastAdmin`, 409 `last_admin`). — 1.25 h
- [ ] T4 · `delete_user(session, user_id, *, by: UUID, clock) -> None`:
  - 404 si no existe o ya está borrado;
  - 409 `last_admin`;
  - pone `deleted_at = now`, hace `n = _revoke_all(user_id)` y emite `SessionsRevoked(reason="delete", revoked=n)`. — 1 h

### Schemas
- [ ] T5 · `UpdateUserIn` (`email: EmailStr | None`, `role: Role | None`, con `model_config` que prohíbe campos extra) y `UserOut` con `status` (de US-041 y US-046). — 0.5 h

### Router
- [ ] T6 · Rutas, todas con `require_role("admin")`:
  - `GET /api/v1/users/{id}`: 200, 401, 403, 404;
  - `PATCH /api/v1/users/{id}`: 200, 401, 403, 404, 409, 422;
  - `DELETE /api/v1/users/{id}`: 204, 401, 403, 404, 409. — 1 h

### Tests unitarios puros
- [ ] T7 · `api/tests/auth/test_pure_last_admin.py`: un admin y bajarlo de rol (verdadero), dos admins (falso), el objetivo no es admin (falso), dar de baja al único admin (verdadero), cambiar el rol a `admin` (falso). — 0.5 h

### Tests de service con PostgreSQL
- [ ] T8 · `api/tests/auth/test_update_delete_user.py`:
  - la baja deja `deleted_at`, revoca la sesión de Luis, emite `SessionsRevoked(revoked=1)`, conserva la fila y Luis ya no puede iniciar sesión;
  - después de la baja, el correo de Luis se puede usar en una cuenta nueva;
  - cambiar el rol del único admin humano lanza `LastAdmin`, aunque exista el usuario técnico;
  - un correo repetido lanza `EmailTaken`;
  - la auditoría `update` tiene `before` y `after` del rol;
  - dos `delete_user` concurrentes sobre los dos únicos admins terminan con uno solo dado de baja (`asyncio.gather`);
  - operar sobre `SYSTEM_USER_ID` devuelve 404. — 2 h

### Tests de router
- [ ] T9 · `api/tests/auth/test_user_detail_router.py`: el coach recibe 403 en los tres endpoints; un id inexistente o ya borrado responde 404 en `PATCH` y `DELETE`; `GET` de un borrado responde 200 con `status: "deleted"`; 409 con `field: "email"` y `existing_id`; 409 `last_admin`; `DELETE` responde 204 sin cuerpo. — 1 h

### Tests de arquitectura
- [ ] T10 · Que sigan verdes `test_no_physical_delete_users.py` (US-041), es decir que `delete_user` no usa `session.delete`, y `test_every_route_has_role.py`. — 0.1 h

### Front
- [ ] T11 · Hooks `useUser(id)`, `useUpdateUser()` y `useDeleteUser()` en `web/src/features/system/api.ts` (invalidan `["users"]`), y Zod `updateUserSchema` en `schemas.ts`. — 0.5 h
- [ ] T12 · `web/src/features/system/components/EditUserPanel.tsx`: un `SidePanel` con correo y rol (`admin` o `coach`). Los errores 409 se muestran por campo, y `last_admin` aparece como mensaje general. — 1.5 h
- [ ] T13 · Acción "Dar de baja" en `UsersPage` con un `ConfirmModal`. El texto dice: "La cuenta pierde el acceso de inmediato. Su historial se conserva." La acción no aparece en la fila del usuario conectado (se compara con `session.user.id`). — 1 h
- [ ] T14 · Vitest `web/src/features/system/components/EditUserPanel.test.tsx` y `UsersPage.delete.test.tsx`: edición correcta, 409 por campo, `last_admin`, sin "Dar de baja" en la propia fila, y la confirmación llama a `DELETE`. — 1 h

### DevOps
- No aplica.

### Seguridad
- [ ] T15 · Revisión:
  - solo admin;
  - sin `password_hash` en las respuestas;
  - la revocación ocurre en la misma transacción que la baja;
  - el bloqueo `FOR UPDATE` cubre la carrera;
  - el usuario técnico es inaccesible;
  - el cambio de rol tiene efecto inmediato vía `current_user`. — 0.4 h

## Orden de ejecución
1. T7 (en rojo)
2. T1
3. T8 (en rojo)
4. T2, T3 y T4
5. T5
6. T9 (en rojo)
7. T6
8. T10
9. T14 (en rojo)
10. T11, T12 y T13
11. T15

## Dependencias técnicas
- US-046 · Listar usuarios: la pantalla, `UserOut` y `user_status`.
- US-041 · `is_active_admin`, `validate_user_role` y la prueba de "sin borrado físico".
- US-043 · `_revoke_all` y la declaración de `SessionsRevoked`.
- US-034 · current_user, que debe usar el rol y el estado leídos de la base en cada petición.
- US-107 · Audita `SessionsRevoked`.
- US-065 · Panel lateral y modal de confirmación.

## Endpoints
- `GET /api/v1/users/{id}` — roles: admin
- `PATCH /api/v1/users/{id}` — roles: admin
- `DELETE /api/v1/users/{id}` — roles: admin

## Riesgos
- Si `current_user` toma el rol del claim del JWT, un admin degradado a coach conserva el rol admin hasta 15 minutos. Mitigación: exigir en US-034 que el principal use el rol de la base (ya se consulta el usuario en cada petición) y probarlo aquí con T9 más un token emitido antes del cambio.
- Que un admin se dé de baja a sí mismo está permitido por el API si no es el último. El front solo oculta la acción. Mitigación: el comportamiento es el de la historia y queda documentado.
- Front condicionado a D1.

## Estimación
- Backend: 5 h
- Front: 4 h
- Pruebas: 3.6 h
- DevOps / seguridad: 0.4 h
- **Total: 13 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/auth/test_pure_last_admin.py tests/auth/test_update_delete_user.py tests/auth/test_user_detail_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system`
- [ ] Después de `curl -X DELETE -H 'Authorization: Bearer <admin>' http://localhost/api/v1/users/<luis>` (204), `SELECT deleted_at IS NOT NULL FROM auth.users WHERE id = '<luis>'` devuelve `t` y `SELECT count(*) FROM auth.refresh_tokens WHERE user_id = '<luis>' AND revoked_at IS NULL` devuelve 0.
- [ ] Con un solo admin humano, `curl -X PATCH -d '{"role":"coach"}' ...` sobre él responde 409 `last_admin`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.auth --cov-fail-under=80`
