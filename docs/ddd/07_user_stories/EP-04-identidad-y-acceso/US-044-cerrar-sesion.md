# US-044 · Como administrador o coach quiero cerrar mi sesión para que nadie use mi cuenta en el computador de recepción

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (esquema `auth`, módulo `auth`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 1
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `TopBar` del panel (menú de usuario, opción "Cerrar sesión")

## Historia

Como administrador o coach
quiero cerrar mi sesión desde el menú de usuario
para que la siguiente persona en el computador compartido no pueda usar mi cuenta

## Contexto de dominio

- **Aggregate / entidades:** `User`, `RefreshToken`.
- **Reglas que aplica:** RN-15 (logout exige sesión); revocación de refresh (`auth.service.logout`).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `auth.service.logout(refresh_token)` y `POST /auth/logout`.
- **Front:** opción "Cerrar sesión" en el menú de usuario de `TopBar`; borra el access token de memoria, avisa a las otras pestañas y navega a `/login`.

## Criterios de aceptación

1. `POST /api/v1/auth/logout` con access token válido (rol `admin`, `coach` o `member`) y cookie de refresh responde 204, marca `revoked_at` (UTC) en ese refresh y borra la cookie.
2. Solo se revoca el refresh de la sesión actual; otras sesiones del mismo usuario siguen vigentes.
3. Después del logout, usar ese refresh en `/auth/refresh` responde 401 `unauthorized`.
4. Sin access token responde 401; con access token válido pero sin cookie responde 204 e igualmente limpia la cookie (idempotente).
5. El front, tras el 204 o ante cualquier error de red, borra el access token, notifica a las otras pestañas por `BroadcastChannel` y navega a `/login`.

## Escenarios BDD

```gherkin
# language: es
Característica: Cerrar sesión

  Antecedentes:
    Dado un coach con sesión iniciada en el computador de recepción

  Escenario: Cerrar sesión desde el menú
    Cuando elige "Cerrar sesión" en el menú de usuario
    Entonces el API responde 204
    Y su refresh queda revocado
    Y el front muestra "/login"

  Escenario: El refresh revocado ya no sirve
    Dado que el coach cerró sesión
    Cuando alguien intenta renovar con ese refresh
    Entonces recibe 401 con código "unauthorized"

  Escenario: Logout sin sesión
    Cuando se llama "/auth/logout" sin access token
    Entonces recibe 401
```

## Endpoints

- `POST /api/v1/auth/logout` — rol(es): admin, coach, member — entrada: cookie de refresh — salida: vacío — códigos: 204, 401.

## Pantalla

- Menú de usuario de `TopBar` (componente de US-061). No hay estados de vacío; durante la petición el ítem queda deshabilitado.

## Notas técnicas

- **Migración:** no.
- **Pruebas:** service (revoca solo la sesión actual), router (204, 401), front (Vitest del ítem de menú).
- **Archivos principales:** `api/src/app/modules/auth/router.py`, `service.py`; `web/src/shared/ui/TopBar.tsx`, `web/src/core/auth/session.ts`.

## Supuestos

- Ninguno.

## Dependencias

- US-042 · Iniciar sesión (sesión que se cierra)

## INVEST

- **Independiente:** solo requiere el login.
- **Negociable:** la ubicación del botón se puede mover.
- **Valiosa:** protege la cuenta en un computador compartido.
- **Estimable:** un endpoint y un botón.
- **Pequeña:** menos de un día.
- **Testeable:** el refresh revocado se verifica directo.

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
- [ ] Front: prueba del ítem de menú; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
