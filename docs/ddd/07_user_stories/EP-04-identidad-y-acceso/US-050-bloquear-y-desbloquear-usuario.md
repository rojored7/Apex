# US-050 · Como administrador quiero bloquear y desbloquear a un usuario para cortar su acceso de inmediato ante cualquier sospecha

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (esquema `auth`, módulo `auth`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Usuarios` (`/sistema/usuarios`, acciones "Bloquear" y "Desbloquear")

## Historia

Como administrador
quiero bloquear a un usuario y después desbloquearlo si fue un error
para cortar su acceso al instante sin darlo de baja

## Contexto de dominio

- **Aggregate / entidades:** `User`, `RefreshToken`.
- **Reglas que aplica:** "bloquear impide login y revoca sesiones"; "no se puede bloquear al último admin activo" (`05_service_design.md` 3); RN-15.
- **Eventos que emite:** `UserLocked`, `SessionsRevoked` (ambos llegan a auditoría, US-107)
- **Eventos que consume:** ninguno
- **Funciones puras:** `auth.would_remove_last_admin(...)` (compartida con US-049).

## Alcance

- **Backend:** `auth.service.lock(user_id, by)`, `unlock(user_id, by)`; `POST /users/{id}/lock`, `POST /users/{id}/unlock`.
- **Front:** acción por fila "Bloquear" con `ConfirmModal` y "Desbloquear" en usuarios bloqueados; `StatusTag` "Bloqueado".

## Criterios de aceptación

1. `POST /api/v1/users/{id}/lock` (admin) responde 200 con el usuario en estado `locked`, pone `locked_at` en UTC y revoca todos sus refresh tokens en la misma transacción.
2. Se emiten `UserLocked` y `SessionsRevoked`, y queda auditoría `update` sobre `users`.
3. Un usuario bloqueado recibe 401 genérico al iniciar sesión y 401 `invalid_refresh` al renovar; un access token emitido antes del bloqueo deja de servir en la siguiente petición (la dependencia `current_user` comprueba `locked_at`).
4. Bloquear al único admin activo o al propio usuario conectado responde 409 (`last_admin` o `cannot_lock_self`).
5. Bloquear un usuario ya bloqueado responde 409 `already_locked`; desbloquear uno no bloqueado responde 409 `not_locked`.
6. `POST /api/v1/users/{id}/unlock` (admin) responde 200, pone `locked_at` en nulo y no restaura sesiones: el usuario debe iniciar sesión otra vez.
7. Un id inexistente o dado de baja responde 404; un coach recibe 403.
8. El front muestra "Bloqueado" con `StatusTag` de texto y color de error, y refresca la fila tras la acción.

## Escenarios BDD

```gherkin
# language: es
Característica: Bloquear y desbloquear usuarios

  Antecedentes:
    Dado el coach "luis@apex.co" con sesión abierta en la tablet
    Y un admin con sesión en "/sistema/usuarios"

  Escenario: Bloquear corta el acceso de inmediato
    Cuando bloquea a "luis@apex.co" y confirma
    Entonces "luis@apex.co" aparece como "Bloqueado"
    Y su sesión en la tablet recibe 401 en la siguiente petición
    Y se registran "UserLocked" y "SessionsRevoked" en auditoría

  Escenario: Desbloquear después de un error
    Dado que "luis@apex.co" está bloqueado
    Cuando el admin lo desbloquea
    Entonces "luis@apex.co" puede iniciar sesión de nuevo

  Escenario: No se puede bloquear al último admin
    Dado que el admin es el único admin activo
    Cuando intenta bloquearse a sí mismo
    Entonces recibe 409

  Escenario: Un coach no puede bloquear
    Dado un coach con sesión
    Cuando envía "POST /users/{id}/lock"
    Entonces recibe 403
```

## Endpoints

- `POST /api/v1/users/{id}/lock` — rol(es): admin — salida: usuario — códigos: 200, 401, 403, 404, 409.
- `POST /api/v1/users/{id}/unlock` — rol(es): admin — salida: usuario — códigos: 200, 401, 403, 404, 409.

## Pantalla

- `Usuarios`: acciones "Bloquear" (con confirmación) y "Desbloquear".

## Notas técnicas

- **Migración:** no.
- **Pruebas:** service (revocación en la misma transacción, eventos), router (403, 404, 409), dependencia `current_user` rechazando usuario bloqueado con token vigente, front (acciones).
- **Archivos principales:** `api/src/app/modules/auth/service.py`, `router.py`; `api/src/app/core/security.py` (chequeo de `locked_at`); `web/src/features/system/pages/UsersPage.tsx`.

## Supuestos

- Supuesto: `current_user` consulta el estado del usuario en cada petición para que el bloqueo sea inmediato y no espere los 15 minutos del access token.
- Supuesto: un admin no puede bloquearse a sí mismo (`cannot_lock_self`).

## Dependencias

- US-046 · Listar usuarios

## INVEST

- **Independiente:** solo requiere la lista.
- **Negociable:** la confirmación y los textos son ajustables.
- **Valiosa:** corta el acceso ante una sospecha sin perder la cuenta.
- **Estimable:** dos endpoints y un chequeo en la dependencia de sesión.
- **Pequeña:** dos o tres días.
- **Testeable:** el 401 tras el bloqueo es verificable.

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
