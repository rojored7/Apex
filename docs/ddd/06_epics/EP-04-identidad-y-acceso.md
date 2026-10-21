# EP-04 · Identidad y acceso

- **Versión del plan:** v0.1 (Tarea 3, con las ampliaciones de `BRECHAS.md` sección 2 y el supuesto S7).
- **Bounded context:** Auth (soporte, esquema `auth`).
- **Estimación relativa:** M.

## Objetivo de negocio

Que el dueño pueda dar y quitar acceso al sistema a su equipo sin depender de nadie: crear cuentas de coach, bloquear a quien ya no trabaja ahí, cerrar sus sesiones abiertas y reponer una contraseña olvidada, todo con rastro de auditoría.

## Actores

- Administrador: crea, edita, bloquea y desbloquea usuarios, cierra sesiones, genera enlaces de activación.
- Coach y administrador: inician y cierran sesión, cambian su contraseña.
- Socio: el modelo admite el rol `member` desde v0.1, pero su acceso al portal llega en EP-25.

## Capacidades incluidas

### Backend
- Aggregate `User` (`email` único, `password_hash` argon2id, `role`, `member_id` nulo desde v0.1 y obligatorio si `role = member` (S7), `is_active`, `locked_at`, `deleted_at`), auditado.
- Entidad `RefreshToken` con rotación en cada refresh y revocación.
- Entidad `OneTimeToken` (`activate` | `reset`, vencimiento, un solo uso).
- `login`, `refresh`, `logout`, `me`, `POST /auth/me/password`.
- `forgot` (siempre 204) y `reset` (sirve para nueva contraseña y para activar cuenta). En v0.1 el enlace solo se ve desde la pantalla de usuarios (admin); el envío por correo llega con EP-14.
- CRUD de usuarios solo admin, `lock`, `unlock`, `revoke-sessions`, `resend-link`.
- Invariantes: un token de un solo uso se consume una vez; bloquear impide el login y revoca sesiones; no se puede bloquear ni borrar al último admin activo; baja lógica (RN-14).
- Eventos `UserCreated`, `UserLocked`, `SessionsRevoked`, `PasswordChanged`; los dos del medio llegan a auditoría.
- `cli seed`: admin inicial con contraseña tomada de una variable de entorno de un solo uso.

### Front
- Sesión en `web/src/core/auth/`: almacenamiento del access token, refresh automático en `api/client.ts`, guardas de ruta por rol y redirección según rol (`/` para admin y coach, `/mi` para socio).
- Pantalla de acceso (tarjeta "Ingresar") y pantalla de usuarios con crear, editar, bloquear, desbloquear, cerrar sesiones y copiar enlace de activación.

## Fuera de alcance

- Envío del enlace de activación o recuperación por correo y tarjetas "Olvidé mi contraseña" y "Nueva contraseña / Activar cuenta" con correo real (EP-14).
- Creación automática de la cuenta de portal al crear un socio (EP-25).
- Diferenciar "dueño" de "recepcionista" (P1, v1.1, fuera de alcance).
- Coach que también es socio (P6, v1.1).

## Criterios de éxito medibles

- Pruebas de login correcto e incorrecto, refresh, revocación y acceso denegado por rol (criterio de salida de la Tarea 3).
- Un refresh token ya usado no sirve una segunda vez.
- Un token de activación usado o vencido devuelve error y no cambia la contraseña.
- Intentar bloquear al único admin activo devuelve error de dominio.
- Bloquear a un usuario deja inválidos todos sus refresh tokens en la misma transacción.
- E2E de Playwright: login de admin, crear coach, copiar enlace, activar cuenta con el enlace y entrar como coach.

## Dependencias

- EP-03 Seguridad de la plataforma (argon2, JWT, roles, rate limit).
- EP-01 Núcleo compartido (auditoría, errores).
- EP-06 Layout y componentes compartidos del front (para las pantallas).

## Riesgos

- P5: el correo de login vive en claro en `auth.users.email` mientras `members.email` va cifrado. Si el gate decide lo contrario, cambia el login.
- Sin canal de correo en v0.1, el admin debe entregar el enlace a mano; existe el riesgo de que lo comparta por un medio inseguro.
- El refresh automático del front puede crear carreras con varias pestañas abiertas.

## Pantallas del diseño que habilita

- `Login` (tarjeta de acceso).
- `Usuarios`.
