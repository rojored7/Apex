# US-042 · Como administrador o coach quiero iniciar sesión con mi correo y contraseña para usar el panel según mi rol

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (esquema `auth`, módulo `auth`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Login` (`/login`, tarjeta "Ingresar")

## Historia

Como administrador o coach
quiero ingresar con mi correo y contraseña
para usar el panel con los permisos de mi rol

## Contexto de dominio

- **Aggregate / entidades:** `User`, `RefreshToken`.
- **Reglas que aplica:** RN-15 (login es ruta pública de la lista blanca), P5 (correo de login en claro en `auth.users.email`), invariante "bloquear impide login" (`02_domain_model.md` 2.11), rate limit de 5 intentos por minuto por IP (`04_architecture_decision.md` 6).
- **Eventos que emite:** ninguno de dominio; escribe acción `login` en auditoría (resultado correcto o fallido).
- **Eventos que consume:** ninguno
- **Funciones puras:** `auth.can_login(user) -> bool` (activo, no bloqueado, no borrado).

## Alcance

- **Backend:** `auth.service.login(email, password, ip)` y `POST /auth/login` que devuelve access token JWT Ed25519 de 15 minutos y refresh token de 7 días guardado como hash.
- **Front:** tarjeta "Ingresar" de `Login` con `Field` de correo y contraseña, `Button`, mensaje de error genérico, estado de carga y redirección por rol (`/` para admin y coach, `/mi` para socio).

## Criterios de aceptación

1. `POST /api/v1/auth/login` con correo y contraseña correctos de un usuario activo, no bloqueado y no borrado responde 200 con `{ access_token, token_type: "bearer", expires_in: 900, user: { id, email, role } }`.
2. El refresh token se entrega en una cookie `HttpOnly`, `SameSite=Strict`, con `Path=/api/v1/auth`, y en `auth.refresh_tokens` solo queda su hash con `expires_at` = ahora + 7 días en UTC.
3. Con contraseña incorrecta, correo inexistente, usuario bloqueado (`locked_at` no nulo), inactivo o con `deleted_at`, responde 401 con el mismo envelope `{ "error": { "code": "invalid_credentials", "message": "Correo o contraseña incorrectos" } }`; la respuesta no revela cuál fue la causa.
4. El correo se compara sin distinguir mayúsculas y sin espacios al inicio y al final.
5. El sexto intento desde la misma IP dentro de un minuto responde 429 sin evaluar la contraseña.
6. Cada intento, correcto o fallido, deja una fila en auditoría con acción `login`, `user_id` (nulo si el correo no existe) y resultado; nunca guarda la contraseña.
7. Un cuerpo sin `email` o sin `password`, o con `email` mal formado, responde 422 con `field`.
8. El front muestra el mensaje genérico del envelope sobre la tarjeta, mantiene el correo escrito y limpia la contraseña.
9. Tras el login el front guarda el access token solo en memoria (nunca en `localStorage`) y redirige a `/` si el rol es `admin` o `coach`, o a `/mi` si es `member`.
10. Los controles de la tarjeta miden al menos 44 px, tienen foco visible y el botón queda deshabilitado mientras la petición está en curso.

## Escenarios BDD

```gherkin
# language: es
Característica: Iniciar sesión

  Antecedentes:
    Dado un usuario "coach@apex.co" con rol "coach", activo y contraseña "Barras2026!segura"

  Escenario: Ingreso correcto del coach
    Cuando envía correo "Coach@Apex.co " y contraseña "Barras2026!segura" en la tarjeta "Ingresar"
    Entonces recibe un access token que vence en 15 minutos
    Y queda un refresh token hasheado que vence en 7 días
    Y el front lo lleva a "/"
    Y hay una fila de auditoría "login" con resultado correcto

  Escenario: Contraseña incorrecta
    Cuando envía correo "coach@apex.co" y contraseña "otra"
    Entonces recibe 401 con código "invalid_credentials"
    Y el front muestra "Correo o contraseña incorrectos"
    Y hay una fila de auditoría "login" con resultado fallido

  Escenario: Usuario bloqueado no entra
    Dado que el usuario "coach@apex.co" está bloqueado
    Cuando envía su contraseña correcta
    Entonces recibe 401 con código "invalid_credentials"

  Escenario: Correo mal formado
    Cuando envía correo "coach-apex" y una contraseña
    Entonces recibe 422 con field "email"

  Escenario: Demasiados intentos desde la misma IP
    Dado que desde la IP "192.168.1.20" se hicieron 5 intentos en el último minuto
    Cuando se hace el sexto intento
    Entonces recibe 429
```

## Endpoints

- `POST /api/v1/auth/login` — rol(es): público (lista blanca) — entrada: `{ email, password }` — salida: `{ access_token, token_type, expires_in, user: { id, email, role } }` y cookie de refresh — códigos: 200, 401, 422, 429.

## Pantalla

- `Login` de `docs/design/screens/` en `/login`: solo la tarjeta "Ingresar". Estados: inicial, cargando, error genérico. Las tarjetas "Olvidé mi contraseña" y "Nueva contraseña / Activar cuenta" las implementa US-048.

## Notas técnicas

- **Migración:** no (usa las tablas de US-041).
- **Trigger / restricciones:** ninguno nuevo.
- **Funciones puras a probar:** `can_login` con usuario activo, bloqueado, inactivo y borrado.
- **Pruebas:** service con base real (refresh guardado como hash, auditoría), router (401 idéntico para todas las causas, 422, 429), front (Vitest de la tarjeta), E2E Playwright "login de admin".
- **Archivos principales:** `api/src/app/modules/auth/router.py`, `service.py`, `schemas.py`; `web/src/features/auth/pages/LoginPage.tsx`, `web/src/core/auth/session.ts`.
- Comparación de contraseña en tiempo constante; si el usuario no existe se ejecuta igual un `verify` contra un hash ficticio para no filtrar por tiempo.

## Supuestos

- Supuesto: el refresh token viaja en cookie `HttpOnly` y el access token vive en memoria del front; los documentos no fijan el almacenamiento.
- Supuesto: usuario bloqueado, inactivo o borrado recibe el mismo 401 genérico que una contraseña incorrecta, para no permitir enumerar cuentas.

## Dependencias

- US-041 · Cuentas de usuario y admin inicial (tablas y usuario)
- US-033 · JWT Ed25519 (emisión de tokens)
- US-036 · Rate limit en login y forgot (429)
- US-059 · Cliente API y tipos generados (llamada desde el front)

## INVEST

- **Independiente:** solo depende del núcleo de seguridad y de las tablas de auth.
- **Negociable:** el texto del error y el almacenamiento del refresh se pueden ajustar.
- **Valiosa:** es la puerta de entrada de todo el panel.
- **Estimable:** un endpoint, una tarjeta y su prueba E2E.
- **Pequeña:** cabe en un sprint.
- **Testeable:** cada causa de rechazo tiene un escenario.

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
- [ ] Migración aplicada con `alembic upgrade head` y reversible (no aplica)
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para la acción `login`
- [ ] Revisión de PR aprobada
