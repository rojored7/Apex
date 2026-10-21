# US-052 · Como administrador quiero generar de nuevo el enlace de activación o de recuperación de un usuario para entregárselo cuando lo perdió o venció

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (esquema `auth`, módulo `auth`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Usuarios` (`/sistema/usuarios`, acción "Reenviar enlace")

## Historia

Como administrador
quiero obtener un enlace nuevo de activación o de recuperación para un usuario
para entregárselo en persona cuando el anterior venció o lo perdió, mientras no exista envío por correo

## Contexto de dominio

- **Aggregate / entidades:** `User`, `OneTimeToken`.
- **Reglas que aplica:** RN-15 (solo admin); en v0.1 el enlace solo se ve desde Usuarios (`05_service_design.md` 3, `forgot` y `resend_link`); un token de un solo uso se consume una vez.
- **Eventos que emite:** ninguno de dominio (auditoría de `insert` y `update` en `one_time_tokens`)
- **Eventos que consume:** ninguno
- **Funciones puras:** `auth.link_purpose_for(user) -> "activate" | "reset"` (activar si nunca activó, restablecer si ya está activo).

## Alcance

- **Backend:** `auth.service.resend_link(user_id, by) -> str`, `POST /users/{id}/resend-link`; `GET /users/{id}/activation-link` para ver el enlace de recuperación pedido por el usuario con `forgot` (US-048).
- **Front:** acción "Reenviar enlace" que muestra el enlace en un `ConfirmModal` con "Copiar" y la advertencia de entregarlo por un medio seguro.

## Criterios de aceptación

1. `POST /api/v1/users/{id}/resend-link` (admin) responde 200 con `{ url, purpose, expires_at }`; `purpose` es `activate` si el usuario nunca activó y `reset` si ya está activo.
2. Al generar el enlace nuevo, todos los tokens anteriores sin usar del mismo propósito quedan con `used_at` (inválidos) en la misma transacción.
3. El token nuevo vence a las 72 horas (`activate`) o a 1 hora (`reset`) en UTC, y se guarda solo como hash.
4. `GET /api/v1/users/{id}/activation-link` (admin) responde 200 con el enlace vigente sin usar si existe, y 404 `no_active_link` si no hay ninguno.
5. Como el token se guarda hasheado, `GET /activation-link` solo puede devolver el enlace mientras el valor en claro esté disponible; en su lugar genera uno nuevo bajo la misma regla del criterio 2 y lo audita.
6. Un usuario bloqueado o dado de baja responde 409 `user_not_eligible`; un id inexistente 404; un coach 403.
7. Cada enlace generado deja auditoría con el admin que lo pidió; el enlace en claro nunca va a logs ni a auditoría.

## Escenarios BDD

```gherkin
# language: es
Característica: Reenviar enlace de activación o recuperación

  Antecedentes:
    Dado un admin con sesión en "/sistema/usuarios"

  Escenario: Enlace de activación vencido
    Dado que "ana@apex.co" nunca activó y su enlace venció
    Cuando el admin elige "Reenviar enlace"
    Entonces recibe un enlace con propósito "activate" que vence en 72 horas
    Y el enlace anterior queda inválido

  Escenario: Coach activo que olvidó su contraseña
    Dado que "luis@apex.co" está activo y pidió "Olvidé mi contraseña"
    Cuando el admin elige "Reenviar enlace"
    Entonces recibe un enlace con propósito "reset" que vence en 1 hora

  Escenario: Usuario bloqueado
    Dado que "pedro@apex.co" está bloqueado
    Cuando el admin pide su enlace
    Entonces recibe 409 con código "user_not_eligible"

  Escenario: El coach no puede pedir enlaces
    Dado un coach con sesión
    Cuando envía "POST /users/{id}/resend-link"
    Entonces recibe 403
```

## Endpoints

- `POST /api/v1/users/{id}/resend-link` — rol(es): admin — salida: `{ url, purpose, expires_at }` — códigos: 200, 401, 403, 404, 409.
- `GET /api/v1/users/{id}/activation-link` — rol(es): admin — salida: `{ url, purpose, expires_at }` — códigos: 200, 401, 403, 404.

## Pantalla

- `Usuarios`: acción "Reenviar enlace" y modal con el enlace y "Copiar".

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `link_purpose_for` con usuario pendiente y activo.
- **Pruebas:** service (invalidación de anteriores, vencimiento por propósito), router (403, 404, 409), front (modal y copiar).
- **Archivos principales:** `api/src/app/modules/auth/service.py`, `router.py`; `web/src/features/system/components/LinkModal.tsx`.

## Supuestos

- Supuesto: como los tokens se guardan hasheados, `GET /activation-link` no puede mostrar un enlace ya emitido y en su lugar emite uno nuevo; las dos rutas convergen en el mismo comportamiento. Se propone dejar solo `resend-link` (pregunta abierta).
- Supuesto: duración 72 horas (`activate`) y 1 hora (`reset`), igual que US-048.

## Dependencias

- US-047 · Crear usuario con enlace de activación

## INVEST

- **Independiente:** reutiliza la emisión de tokens de US-047.
- **Negociable:** se puede quedar con una sola ruta.
- **Valiosa:** recupera el acceso de un coach sin correo en v0.1.
- **Estimable:** dos rutas pequeñas.
- **Pequeña:** uno o dos días.
- **Testeable:** el token anterior inválido se verifica directo.

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
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `auth.one_time_tokens`
- [ ] Revisión de PR aprobada
