# US-051 · Como administrador quiero cerrar todas las sesiones abiertas de un usuario para obligarlo a ingresar de nuevo si dejó la sesión abierta en otro equipo

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (esquema `auth`, módulo `auth`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P2 mejora
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Usuarios` (`/sistema/usuarios`, acción "Cerrar sesiones")

## Historia

Como administrador
quiero cerrar todas las sesiones abiertas de un usuario sin bloquearlo
para obligarlo a ingresar de nuevo cuando dejó la sesión abierta en la tablet o en otro computador

## Contexto de dominio

- **Aggregate / entidades:** `User`, `RefreshToken`.
- **Reglas que aplica:** "revocar sesiones revoca todos los refresh tokens" (`02_domain_model.md` 2.11); RN-15.
- **Eventos que emite:** `SessionsRevoked` (llega a auditoría, US-107)
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `auth.service.revoke_sessions(user_id, by)` y `POST /users/{id}/revoke-sessions`.
- **Front:** acción por fila "Cerrar sesiones" con `ConfirmModal` que muestra cuántas sesiones activas tiene.

## Criterios de aceptación

1. `POST /api/v1/users/{id}/revoke-sessions` (admin) responde 200 con `{ revoked: n }`, donde `n` es el número de refresh tokens vigentes que quedaron con `revoked_at` (UTC).
2. Se emite `SessionsRevoked` con `user_id`, `by` y `n`, y queda en auditoría.
3. El usuario no queda bloqueado: puede volver a iniciar sesión de inmediato.
4. Si el usuario no tenía sesiones vigentes responde 200 con `{ revoked: 0 }` (idempotente).
5. Si el admin cierra sus propias sesiones, también se revoca la actual y el front lo lleva a `/login`.
6. Un id inexistente responde 404; un coach recibe 403.
7. La lista de usuarios (US-046) expone `active_sessions` por usuario para que el modal muestre el número antes de confirmar.

## Escenarios BDD

```gherkin
# language: es
Característica: Cerrar las sesiones de un usuario

  Antecedentes:
    Dado el coach "ana@apex.co" con sesiones abiertas en la tablet y en recepción
    Y un admin con sesión en "/sistema/usuarios"

  Escenario: Cerrar todas las sesiones
    Cuando elige "Cerrar sesiones" sobre "ana@apex.co" y confirma
    Entonces recibe 200 con "revoked" igual a 2
    Y Ana tiene que ingresar otra vez en ambos equipos
    Y Ana no queda bloqueada

  Escenario: Usuario sin sesiones
    Dado que "ana@apex.co" no tiene sesiones vigentes
    Cuando el admin cierra sus sesiones
    Entonces recibe 200 con "revoked" igual a 0

  Escenario: Usuario inexistente
    Cuando se envía la acción sobre un id que no existe
    Entonces recibe 404

  Escenario: El coach no puede cerrar sesiones ajenas
    Dado un coach con sesión
    Cuando envía "POST /users/{id}/revoke-sessions"
    Entonces recibe 403
```

## Endpoints

- `POST /api/v1/users/{id}/revoke-sessions` — rol(es): admin — salida: `{ revoked }` — códigos: 200, 401, 403, 404.

## Pantalla

- `Usuarios`: acción "Cerrar sesiones" con confirmación y número de sesiones.

## Notas técnicas

- **Migración:** no.
- **Pruebas:** service (conteo y evento), router (403, 404), front (modal con número).
- **Archivos principales:** `api/src/app/modules/auth/service.py`, `router.py`; `web/src/features/system/pages/UsersPage.tsx`.
- La revocación reutiliza la misma función que usan `lock` (US-050) y `reset` (US-048).

## Supuestos

- Supuesto: la lista de usuarios incluye `active_sessions` (conteo de refresh vigentes); no está en el contrato y se agrega aquí.

## Dependencias

- US-046 · Listar usuarios

## INVEST

- **Independiente:** solo requiere la lista.
- **Negociable:** mostrar o no el conteo es ajustable.
- **Valiosa:** cierra sesiones olvidadas en equipos compartidos.
- **Estimable:** un endpoint y una acción.
- **Pequeña:** uno o dos días.
- **Testeable:** el conteo devuelto es exacto.

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
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `SessionsRevoked`
- [ ] Revisión de PR aprobada
