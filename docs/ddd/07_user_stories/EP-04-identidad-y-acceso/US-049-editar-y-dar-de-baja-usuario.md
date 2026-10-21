# US-049 · Como administrador quiero editar el correo o el rol de un usuario y darlo de baja cuando ya no trabaja en el box para que solo el equipo actual tenga acceso

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (esquema `auth`, módulo `auth`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Usuarios` (`/sistema/usuarios`, `SidePanel` de edición y `ConfirmModal` de baja)

## Historia

Como administrador
quiero corregir el correo o el rol de un usuario y darlo de baja cuando sale del equipo
para que el acceso al sistema refleje al equipo actual sin perder su historial

## Contexto de dominio

- **Aggregate / entidades:** `User`, `RefreshToken`.
- **Reglas que aplica:** RN-14 (baja lógica con `deleted_at`, nunca física), RN-15 (solo admin), invariante "no se puede borrar el último admin activo", S7.
- **Eventos que emite:** `SessionsRevoked` (al dar de baja)
- **Eventos que consume:** ninguno
- **Funciones puras:** `auth.would_remove_last_admin(users, target_id, new_role | deleted) -> bool`.

## Alcance

- **Backend:** `GET /users/{id}`, `PATCH /users/{id}`, `DELETE /users/{id}` (baja lógica) en `auth.service`.
- **Front:** acción "Editar" por fila con `SidePanel` (correo y rol) y acción "Dar de baja" con `ConfirmModal`.

## Criterios de aceptación

1. `GET /api/v1/users/{id}` (admin) responde 200 con el usuario sin `password_hash`; un id inexistente responde 404.
2. `PATCH /api/v1/users/{id}` (admin) acepta `email` y `role`; responde 200 con el usuario actualizado y deja auditoría `update` con antes y después.
3. Cambiar el correo a uno usado por otro usuario no borrado responde 409 con `field: "email"` y `existing_id`.
4. Cambiar el rol del único admin activo a `coach` responde 409 `last_admin` y no cambia nada.
5. `DELETE /api/v1/users/{id}` (admin) responde 204, pone `deleted_at` en UTC, revoca todos sus refresh tokens en la misma transacción y emite `SessionsRevoked`; la fila no se borra físicamente.
6. Dar de baja al único admin activo responde 409 `last_admin`; dar de baja un usuario ya borrado responde 404.
7. Un usuario dado de baja no puede iniciar sesión (401 genérico de US-042) y su correo queda libre para una cuenta nueva.
8. Un coach recibe 403 en los tres endpoints.
9. El front oculta "Dar de baja" sobre el propio usuario conectado y, al confirmar la baja, el modal explica que la cuenta pierde el acceso y que su historial se conserva.

## Escenarios BDD

```gherkin
# language: es
Característica: Editar y dar de baja usuarios

  Antecedentes:
    Dado los usuarios "dueno@apex.co" admin y "luis@apex.co" coach con una sesión abierta
    Y un admin con sesión en "/sistema/usuarios"

  Escenario: Dar de baja a un coach que se fue
    Cuando da de baja a "luis@apex.co" y confirma
    Entonces recibe 204
    Y "luis@apex.co" tiene "deleted_at" y su sesión queda revocada
    Y la fila sigue existiendo en "auth.users"
    Y "luis@apex.co" ya no puede iniciar sesión

  Escenario: No se puede quitar el último admin
    Dado que "dueno@apex.co" es el único admin activo
    Cuando intenta cambiar su rol a "coach"
    Entonces recibe 409 con código "last_admin"

  Escenario: Correo ya usado
    Cuando cambia el correo de "luis@apex.co" a "dueno@apex.co"
    Entonces recibe 409 con field "email"

  Escenario: El coach no puede editar usuarios
    Dado un coach con sesión
    Cuando envía "PATCH /users/{id}"
    Entonces recibe 403
```

## Endpoints

- `GET /api/v1/users/{id}` — rol(es): admin — salida: usuario — códigos: 200, 401, 403, 404.
- `PATCH /api/v1/users/{id}` — rol(es): admin — entrada: `{ email?, role? }` — salida: usuario — códigos: 200, 401, 403, 404, 409, 422.
- `DELETE /api/v1/users/{id}` — rol(es): admin — salida: vacío — códigos: 204, 401, 403, 404, 409.

## Pantalla

- `Usuarios`: acciones por fila "Editar" (`SidePanel`) y "Dar de baja" (`ConfirmModal`).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** la comprobación del último admin se hace con `SELECT ... FOR UPDATE` sobre los admins activos para evitar que dos bajas simultáneas dejen el sistema sin admin.
- **Funciones puras a probar:** `would_remove_last_admin` con uno y con dos admins.
- **Pruebas:** service (baja lógica, revocación, último admin), router (403, 404, 409), front (panel y modal).
- **Archivos principales:** `api/src/app/modules/auth/service.py`, `router.py`; `web/src/features/system/components/EditUserPanel.tsx`.

## Supuestos

- Supuesto: el admin puede cambiar el rol entre `admin` y `coach`; pasar a `member` no se ofrece en v0.1.
- Supuesto: un correo de usuario dado de baja se puede reutilizar (unicidad parcial sobre no borrados).

## Dependencias

- US-046 · Listar usuarios

## INVEST

- **Independiente:** solo requiere la lista de usuarios.
- **Negociable:** qué campos se editan es ajustable.
- **Valiosa:** retira el acceso de quien ya no trabaja ahí.
- **Estimable:** tres endpoints y dos componentes.
- **Pequeña:** dos o tres días.
- **Testeable:** la regla del último admin es binaria.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `auth.users`
- [ ] Revisión de PR aprobada
