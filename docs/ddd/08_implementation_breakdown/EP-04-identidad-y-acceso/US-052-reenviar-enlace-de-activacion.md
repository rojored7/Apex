# US-052 · Reenviar enlace de activación o recuperación — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-052-reenviar-enlace-de-activacion.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth (`api/src/app/modules/auth/`, `web/src/features/system/`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

DECISIONES N-12 cierra la pregunta abierta de la historia: queda una sola ruta, `POST /users/{id}/resend-link`, y `GET /users/{id}/activation-link` no existe. Las duraciones y la URL base las fija N-11. El resto del contrato (propósito según el estado, invalidación de los enlaces anteriores y `user_not_eligible`) está definido.

## Resumen

`auth.service.resend_link(user_id, by)` decide el propósito con la función pura `link_purpose_for(user)`: `activate` si el usuario nunca activó (sin `password_hash`) y `reset` si ya está activo. Luego emite un token nuevo con `_issue_one_time_token` (US-047). Ese helper invalida (`used_at`) los anteriores del mismo propósito que seguían sin usar, en la misma transacción. La respuesta es `{ url, purpose, expires_at }`, y es la única vez que se ve el enlace. Un usuario bloqueado o dado de baja responde 409 `user_not_eligible`. El front agrega la acción "Reenviar enlace", que abre `LinkModal` con el enlace, el botón "Copiar" y la advertencia de entregarlo por un medio seguro.

## Correcciones aplicadas por DECISIONES.md

- Alcance, criterios 4 y 5 y endpoints: se elimina `GET /api/v1/users/{id}/activation-link` y la única ruta es `POST /users/{id}/resend-link`, que genera un token nuevo, invalida el anterior y devuelve el enlace: corregido por DECISIONES N-12. También corrige la mención de esa ruta en `forgot` de `05_service_design.md` sección 3 y en US-048.
- Duración de 72 h para `activate` y de 1 h para `reset`, con la URL `<FRONT_BASE_URL>/restablecer/<token>`: aceptado por DECISIONES N-11.
- En v0.1 el enlace lo entrega solo este endpoint de admin, sin correo. US-131 lo enviará en v0.2 con texto fijo: aceptado por DECISIONES N-36.
- El usuario técnico responde 404: coherente con DECISIONES N-15.

## Validación contra el dominio

- Entidades: `User` y `OneTimeToken`. Se cumple la invariante "un token de un solo uso se consume una vez", y además a lo sumo queda un token abierto por usuario y propósito.
- Función pura: `link_purpose_for(user) -> Literal["activate", "reset"]`.
- Elegibilidad: `user_status` en `pending_activation` o `active`. Un usuario `locked` o `deleted` recibe 409.
- No emite eventos de dominio y no consume eventos. La auditoría es la del hook: `insert` y `update` sobre `one_time_tokens`, con el admin como `user_id`.

## Validación contra la arquitectura

- El módulo dueño es `modules/auth` y la ruta usa `require_role("admin")`.
- El token sale de `core.security.new_opaque_token()` y en la base solo queda su hash. El enlace en claro solo viaja en la respuesta y nunca llega a logs ni a auditoría (filtro `redact` de US-018 sobre la clave `token`, más la prueba).
- No hay llamadas a otros services ni paginación.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `link_purpose_for(user: User) -> Purpose` en `auth/service.py`. — 0.25 h
- [ ] T2 · `resend_link(session, user_id: UUID, *, by: UUID, clock) -> IssuedLink`, que devuelve `url`, `purpose` y `expires_at`. Usa `_get_alive_or_404` con borrados incluidos, porque un borrado debe dar 409 y no 404, y `SYSTEM_USER_ID` da 404. Si el estado es `locked` o `deleted`, lanza `UserNotEligible`, que responde 409 `user_not_eligible`. Después llama a `_issue_one_time_token(user_id, purpose)` y arma la URL con `activation_url`. — 0.75 h

### Schemas
- [ ] T3 · `IssuedLinkOut` (`url: str`, `purpose: Literal["activate","reset"]`, `expires_at: datetime` en UTC). — 0.25 h

### Router
- [ ] T4 · `POST /api/v1/users/{id}/resend-link` con `require_role("admin")`. Responde 200 con `IssuedLinkOut`; los demás códigos son 401, 403, 404 y 409. No se registra `GET /users/{id}/activation-link`. — 0.5 h

### Tests unitarios puros
- [ ] T5 · `api/tests/auth/test_pure_links.py` (se amplía el de US-047): `link_purpose_for` con un usuario pendiente devuelve `activate`, y con uno activo devuelve `reset`. — 0.25 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/auth/test_resend_link.py`, con `FrozenClock`:
  - Ana pendiente con un enlace vencido: recibe `activate` a 72 h y el token anterior queda con `used_at`;
  - Luis activo que pidió `forgot` (US-048): recibe `reset` a 1 h y el `reset` de `forgot` queda invalidado;
  - el token anterior de Ana devuelve `InvalidToken` en `reset` (US-048);
  - Pedro bloqueado recibe `UserNotEligible`, igual que un usuario dado de baja;
  - la auditoría tiene `insert` y `update` sobre `one_time_tokens` hechos por el admin y no contiene el token. — 1 h

### Tests de router
- [ ] T7 · `api/tests/auth/test_resend_link_router.py`:
  - 200 con `url` que contiene `/restablecer/`;
  - el coach recibe 403;
  - un id inexistente da 404;
  - un usuario bloqueado da 409 `user_not_eligible`;
  - `GET /api/v1/users/{id}/activation-link` responde 404 o 405, porque la ruta no existe (N-12). — 0.75 h

### Tests de arquitectura
- [ ] T8 · Mantener verde `test_every_route_has_role.py`. Una prueba en `api/tests/architecture/test_auth_routes.py` comprueba que ninguna ruta registrada termina en `/activation-link`. — 0.1 h

### Front
- [ ] T9 · Hook `useResendLink()` en `web/src/features/system/api.ts`. — 0.25 h
- [ ] T10 · `web/src/features/system/components/LinkModal.tsx`:
  - un `ConfirmModal` con el enlace en solo lectura y el botón "Copiar";
  - el propósito en texto ("Activación, vence en 72 horas" o "Recuperación, vence en 1 hora", con la hora de Bogotá);
  - la advertencia "Entrégalo por un medio seguro. Al generar uno nuevo, el anterior deja de servir.";
  - la acción "Reenviar enlace" por fila en `UsersPage`, oculta para usuarios bloqueados o dados de baja. — 1.5 h
- [ ] T11 · Vitest `web/src/features/system/components/LinkModal.test.tsx`: muestra el propósito y el vencimiento, copia al portapapeles, al cerrar se descarta el enlace, y un 409 muestra su mensaje. — 0.75 h

### DevOps
- No aplica.

### Seguridad
- [ ] T12 · Revisión: el enlace aparece solo en la respuesta; los enlaces anteriores quedan invalidados de forma atómica; solo admin; el token no se guarda en el front; y el riesgo de entrega manual queda anotado. — 0.25 h

## Orden de ejecución
1. T5 (en rojo)
2. T1
3. T6 (en rojo)
4. T2
5. T3
6. T7 (en rojo)
7. T4
8. T8
9. T11 (en rojo)
10. T9 y T10
11. T12

## Dependencias técnicas
- US-047 · Crear usuario con enlace de activación: `_issue_one_time_token`, `activation_url` y las TTL.
- US-048 · Activar y restablecer: consume el enlace; `forgot` crea los `reset` que esta historia invalida.
- US-046 · `user_status` y la pantalla `Usuarios`.
- US-049 · `_get_alive_or_404`.
- US-065 · `ConfirmModal`.
- US-131 (v0.2): `resend_link` enviará también por correo; el contrato de retorno se mantiene.

## Endpoints
- `POST /api/v1/users/{id}/resend-link` — roles: admin

## Riesgos
- El admin entrega el enlace a mano y puede exponerlo por WhatsApp u otros canales. Mitigación: la advertencia, la TTL corta para `reset` y que generar uno nuevo invalida el anterior.
- Si otra historia de otra épica sigue usando `GET /users/{id}/activation-link` (por ejemplo `05_service_design.md` en `forgot`), aparecería un contrato fantasma. Mitigación: la prueba de T8 y la corrección anotada.
- Front condicionado a D1.

## Estimación
- Backend: 1.75 h
- Front: 2.5 h
- Pruebas: 2.1 h
- DevOps / seguridad: 0.25 h
- **Total: 7 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/auth/test_pure_links.py tests/auth/test_resend_link.py tests/auth/test_resend_link_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system/components/LinkModal.test.tsx`
- [ ] Después de `curl -X POST -H 'Authorization: Bearer <admin>' http://localhost/api/v1/users/<ana>/resend-link`, `SELECT count(*) FROM auth.one_time_tokens WHERE user_id = '<ana>' AND purpose = 'activate' AND used_at IS NULL` devuelve 1.
- [ ] `curl -H 'Authorization: Bearer <admin>' http://localhost/api/v1/users/<ana>/activation-link` responde 404 o 405.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.auth --cov-fail-under=80`
