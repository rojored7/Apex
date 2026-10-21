# US-048 · Como coach quiero activar mi cuenta o restablecer mi contraseña con un enlace de un solo uso para entrar al sistema con una contraseña que solo yo conozco

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (esquema `auth`, módulo `auth`)
- **Versión:** v0.1
- **Actor:** coach, administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Login` (`/restablecer/:token`, tarjeta "Nueva contraseña / Activar cuenta"; `/recuperar`, tarjeta "Olvidé mi contraseña")

## Historia

Como coach (o administrador)
quiero abrir el enlace que me dieron y definir mi contraseña, o pedir uno nuevo si la olvidé
para entrar al sistema con una contraseña que solo yo conozco

## Contexto de dominio

- **Aggregate / entidades:** `User`, `OneTimeToken` (`activate` | `reset`), `RefreshToken`.
- **Reglas que aplica:** "un token de un solo uso se consume una vez"; `forgot` siempre responde 204 (`05_service_design.md` 3); en v0.1 el enlace de recuperación solo se ve desde `GET /users/{id}/activation-link` (admin) porque no hay canal de correo hasta EP-14; rate limit de `forgot` (5 por minuto por IP).
- **Eventos que emite:** `PasswordChanged`
- **Eventos que consume:** ninguno
- **Funciones puras:** `auth.is_one_time_token_usable(token, now) -> bool`; `auth.validate_password_policy(password)`.

## Alcance

- **Backend:** `auth.service.reset(token, new_password)` y `POST /auth/reset` (sirve para activar y para restablecer); `auth.service.forgot(email)` y `POST /auth/forgot`.
- **Front:** tarjeta "Nueva contraseña / Activar cuenta" en `/restablecer/:token` (contraseña y confirmación) y tarjeta "Olvidé mi contraseña" en `/recuperar` con el texto de v0.1: "Pídele al administrador tu enlace de recuperación".

## Criterios de aceptación

1. `POST /api/v1/auth/reset` con `{ token, new_password }` y un token vigente y sin usar responde 204, guarda el hash argon2id, marca `used_at` (UTC) en el token y emite `PasswordChanged`, todo en una transacción.
2. Si el token era `activate`, el usuario pasa de `pending_activation` a `active`; si era `reset`, además se revocan todos sus refresh tokens.
3. Un token usado, vencido, inexistente o de un usuario bloqueado o borrado responde 400 `invalid_token` y no cambia la contraseña.
4. `new_password` de menos de 12 caracteres responde 422 con `field: "new_password"` y el token sigue sin usar.
5. `POST /api/v1/auth/forgot` con `{ email }` responde siempre 204, exista o no el correo; si existe un usuario activo, crea un `OneTimeToken(reset)` con vencimiento de 1 hora e invalida (`used_at`) los `reset` anteriores sin usar.
6. `forgot` aplica el rate limit de 5 por minuto por IP (429 en el sexto).
7. Ni el token en claro ni la contraseña aparecen en logs; en auditoría el token se guarda solo como hash y `password_hash` como `"***"`.
8. Ambos endpoints son públicos (lista blanca) y no aceptan access token como requisito.
9. El front en `/restablecer/:token` valida con Zod que las dos contraseñas coincidan; ante 400 muestra "El enlace ya no es válido. Pide uno nuevo al administrador."; ante 204 muestra éxito y lleva a `/login`.
10. En v0.1 la tarjeta "Olvidé mi contraseña" envía `forgot` y muestra siempre el mismo mensaje, sin indicar si el correo existe.

## Escenarios BDD

```gherkin
# language: es
Característica: Activar cuenta y restablecer contraseña

  Antecedentes:
    Dado el usuario "ana@apex.co" con rol "coach" pendiente de activación
    Y un enlace de activación vigente para "ana@apex.co"

  Escenario: Activar la cuenta con el enlace
    Cuando Ana abre el enlace y define la contraseña "Kettlebell2026!"
    Entonces recibe 204
    Y su estado pasa a "active"
    Y el enlace queda marcado como usado
    Y puede iniciar sesión con "Kettlebell2026!"

  Escenario: Enlace usado por segunda vez
    Dado que Ana ya activó su cuenta con el enlace
    Cuando vuelve a abrir el mismo enlace y envía otra contraseña
    Entonces recibe 400 con código "invalid_token"
    Y su contraseña no cambia

  Escenario: Contraseña demasiado corta
    Cuando Ana envía la contraseña "corta1"
    Entonces recibe 422 con field "new_password"
    Y el enlace sigue sin usar

  Escenario: Olvidé mi contraseña con un correo que no existe
    Cuando alguien pide recuperar "nadie@apex.co"
    Entonces recibe 204
    Y no se crea ningún token

  Escenario: Restablecer revoca las sesiones abiertas
    Dado que Ana está activa con dos sesiones abiertas
    Y el admin le entregó un enlace de recuperación vigente
    Cuando Ana define una contraseña nueva con ese enlace
    Entonces sus dos sesiones anteriores quedan revocadas
```

## Endpoints

- `POST /api/v1/auth/reset` — rol(es): público (lista blanca) — entrada: `{ token, new_password }` — salida: vacío — códigos: 204, 400, 422.
- `POST /api/v1/auth/forgot` — rol(es): público (lista blanca) — entrada: `{ email }` — salida: vacío — códigos: 204, 422 (correo mal formado), 429.

## Pantalla

- `Login` de `docs/design/screens/`: tarjetas "Nueva contraseña / Activar cuenta" (`/restablecer/:token`) y "Olvidé mi contraseña" (`/recuperar`). `// DESIGN-GAP:` el texto de v0.1 sin correo ("pídele el enlace al administrador") no está en el diseño.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** el consumo del token usa `UPDATE ... SET used_at = now() WHERE id = :id AND used_at IS NULL` y comprueba una fila afectada, para que dos envíos simultáneos no lo consuman dos veces.
- **Funciones puras a probar:** `is_one_time_token_usable` con vigente, usado, vencido.
- **Pruebas:** service (activación, revocación en reset, consumo concurrente), router (400, 422, 204 siempre en forgot, 429), front (dos tarjetas), E2E Playwright "activar cuenta con el enlace y entrar como coach".
- **Archivos principales:** `api/src/app/modules/auth/service.py`, `router.py`; `web/src/features/auth/pages/ResetPage.tsx`, `ForgotPage.tsx`.

## Supuestos

- Supuesto: el token `activate` vence a las 72 horas y el `reset` a 1 hora; los documentos no definen la duración.
- Supuesto: un token inválido responde 400 `invalid_token` (los documentos no fijan el código).
- Supuesto: pedir un `reset` nuevo invalida los `reset` anteriores sin usar del mismo usuario.

## Dependencias

- US-047 · Crear usuario con enlace de activación (genera el token `activate`)
- Observación: también usa US-036 (rate limit de `forgot`), que ya es dependencia de US-042.
- US-036 · rate limit en forgot (agregado en consolidación)

## INVEST

- **Independiente:** el envío por correo queda en US-131.
- **Negociable:** duración de los tokens y textos ajustables.
- **Valiosa:** sin activación ningún coach puede entrar.
- **Estimable:** dos endpoints públicos y dos tarjetas.
- **Pequeña:** cabe en un sprint.
- **Testeable:** un solo uso y vencimiento son binarios.

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
- [ ] Auditoría verificada para `auth.users` y `auth.one_time_tokens`
- [ ] Revisión de PR aprobada
