# US-047 · Como administrador quiero crear la cuenta de un coach y obtener su enlace de activación para darle acceso sin conocer su contraseña

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (esquema `auth`, módulo `auth`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Usuarios` (`/sistema/usuarios`, `SidePanel` "Nuevo usuario")

## Historia

Como administrador
quiero crear una cuenta con correo y rol y recibir un enlace de activación para copiarlo
para que cada coach defina su propia contraseña y yo nunca la conozca

## Contexto de dominio

- **Aggregate / entidades:** `User`, `OneTimeToken(activate)`.
- **Reglas que aplica:** RN-15 (solo admin), S7 (`role = member` exige `member_id`), P5 (correo en claro), "un token de un solo uso se consume una vez". En v0.1 el enlace solo se entrega en pantalla (sin correo hasta EP-14, US-131).
- **Eventos que emite:** `UserCreated`
- **Eventos que consume:** ninguno
- **Funciones puras:** `auth.validate_user_role(role, member_id)`; `auth.activation_url(base_url, token) -> str`.

## Alcance

- **Backend:** `auth.service.create_user(data, by)` y `POST /users`; genera un `OneTimeToken(activate)` y devuelve el enlace una sola vez.
- **Front:** `SidePanel` "Nuevo usuario" con correo y rol (`admin` o `coach`); al guardar muestra el enlace con botón "Copiar" y la advertencia de entregarlo por un medio seguro.

## Criterios de aceptación

1. `POST /api/v1/users` con rol `admin` y `{ email, role }` válido responde 201 con `{ user: { id, email, role, status: "pending_activation" }, activation_url }`.
2. El usuario se crea sin contraseña utilizable (`password_hash` nulo o marcador inválido): no puede iniciar sesión hasta activar.
3. Se crea un `OneTimeToken` con `purpose = activate`, guardado solo como hash, y `expires_at` = ahora + 72 horas en UTC; `activation_url` tiene la forma `<FRONT_BASE_URL>/restablecer/<token>`.
4. Un correo ya usado por un usuario no borrado responde 409 con `field: "email"` y `existing_id`.
5. `role` fuera de `admin`, `coach` o `member` responde 422; `role = member` sin `member_id` responde 422 con `field: "member_id"`.
6. `created_by` es el admin que crea; la creación queda en auditoría (`insert` sobre `users` e `insert` sobre `one_time_tokens` sin el token en claro) y se emite `UserCreated`.
7. El token en claro no se guarda en la base ni en logs; solo viaja en la respuesta 201.
8. Un coach recibe 403.
9. El front muestra el enlace en un campo de solo lectura con "Copiar", y al cerrar el panel el enlace ya no se puede volver a ver (para eso está US-052).

## Escenarios BDD

```gherkin
# language: es
Característica: Crear usuario con enlace de activación

  Antecedentes:
    Dado un admin con sesión en "/sistema/usuarios"

  Escenario: Crear un coach
    Cuando crea el usuario "ana@apex.co" con rol "coach"
    Entonces recibe 201 con un "activation_url" que contiene "/restablecer/"
    Y "ana@apex.co" aparece como "Pendiente de activación"
    Y el token de activación vence en 72 horas
    Y hay auditoría "insert" de "users" hecha por el admin

  Escenario: Correo repetido
    Dado que ya existe "ana@apex.co"
    Cuando crea otro usuario "ana@apex.co"
    Entonces recibe 409 con field "email" y el "existing_id"

  Escenario: Rol socio sin socio asociado
    Cuando crea un usuario con rol "member" sin "member_id"
    Entonces recibe 422 con field "member_id"

  Escenario: Un coach intenta crear usuarios
    Dado un coach con sesión
    Cuando envía "POST /users"
    Entonces recibe 403
```

## Endpoints

- `POST /api/v1/users` — rol(es): admin — entrada: `{ email, role, member_id? }` — salida: `{ user, activation_url }` — códigos: 201, 401, 403, 409, 422.

## Pantalla

- `Usuarios`: botón "Nuevo usuario" y `SidePanel` con `Field` de correo y selector de rol. Estado posterior al guardado con el enlace y "Copiar".

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `activation_url` y `validate_user_role`.
- **Pruebas:** service (token hasheado, vencimiento, evento, auditoría), router (201, 403, 409, 422), front (panel y copiar al portapapeles), E2E Playwright "crear coach y copiar enlace" (continúa en US-048).
- **Archivos principales:** `api/src/app/modules/auth/service.py`, `router.py`, `schemas.py`; `web/src/features/system/components/NewUserPanel.tsx`.
- Token de 32 bytes aleatorios en base64url generado en `core/security`.

## Supuestos

- Supuesto: el token de activación vence a las 72 horas (no definido en los documentos).
- Supuesto: en v0.1 la pantalla solo ofrece los roles `admin` y `coach`; crear un usuario `member` queda para EP-25 (US-185), aunque el API ya valida `member_id`.
- Supuesto: la URL base del front sale de una variable `FRONT_BASE_URL` en `.env`.

## Dependencias

- US-046 · Listar usuarios (pantalla donde vive la acción)
- US-065 · Panel lateral y modal de confirmación

## INVEST

- **Independiente:** el envío por correo queda fuera (US-131).
- **Negociable:** vencimiento del enlace y roles visibles ajustables.
- **Valiosa:** el dueño da acceso a su equipo sin compartir contraseñas.
- **Estimable:** un endpoint y un panel.
- **Pequeña:** dos o tres días.
- **Testeable:** cada validación tiene un código HTTP fijo.

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
