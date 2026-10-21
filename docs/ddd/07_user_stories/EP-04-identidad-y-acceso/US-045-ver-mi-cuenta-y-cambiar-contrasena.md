# US-045 · Como administrador o coach quiero ver mi cuenta y cambiar mi contraseña para mantener mi acceso seguro sin pedirle ayuda a nadie

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (esquema `auth`, módulo `auth`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `TopBar` (menú de usuario, opción "Cambiar contraseña" en `SidePanel`)

## Historia

Como administrador o coach
quiero ver con qué cuenta y rol estoy y cambiar mi contraseña
para mantener mi acceso seguro sin depender de otra persona

## Contexto de dominio

- **Aggregate / entidades:** `User`, `RefreshToken`.
- **Reglas que aplica:** RN-15; argon2id; evento `PasswordChanged`.
- **Eventos que emite:** `PasswordChanged`
- **Eventos que consume:** ninguno
- **Funciones puras:** `auth.validate_password_policy(password) -> None | AuthError`.

## Alcance

- **Backend:** `auth.service.me(user)`, `GET /auth/me`, `POST /auth/me/password`.
- **Front:** el `TopBar` muestra correo y rol del usuario desde `GET /auth/me`; "Cambiar contraseña" abre un `SidePanel` con contraseña actual, nueva y confirmación.

## Criterios de aceptación

1. `GET /api/v1/auth/me` con access token válido responde 200 con `{ id, email, role, member_id }` y nunca incluye `password_hash`.
2. `POST /api/v1/auth/me/password` con `{ current_password, new_password }` correctos responde 204, guarda el nuevo hash argon2id, emite `PasswordChanged` y revoca todos los refresh tokens del usuario salvo el de la sesión actual.
3. Con `current_password` incorrecta responde 422 con `field: "current_password"` y no cambia nada.
4. Con `new_password` de menos de 12 caracteres o igual a la actual responde 422 con `field: "new_password"`.
5. El cambio queda en auditoría como `update` sobre `users` con `password_hash` enmascarado como `"***"` en `before` y `after`.
6. Ambos endpoints sin access token responden 401.
7. El front valida con Zod que la confirmación coincida antes de enviar, muestra el error del API bajo el campo indicado en `field` y, al terminar, cierra el panel con el mensaje "Contraseña actualizada".

## Escenarios BDD

```gherkin
# language: es
Característica: Mi cuenta y cambio de contraseña

  Antecedentes:
    Dado un admin "dueno@apex.co" con sesión iniciada en dos computadores

  Escenario: Cambiar la contraseña
    Cuando envía su contraseña actual y una nueva de 14 caracteres
    Entonces recibe 204
    Y la sesión del otro computador queda revocada
    Y la sesión actual sigue activa
    Y hay una auditoría "update" de "users" sin el hash en claro

  Escenario: Contraseña actual incorrecta
    Cuando envía una contraseña actual equivocada
    Entonces recibe 422 con field "current_password"
    Y la contraseña no cambia

  Escenario: Ver mi cuenta sin sesión
    Cuando se llama "/auth/me" sin access token
    Entonces recibe 401
```

## Endpoints

- `GET /api/v1/auth/me` — rol(es): admin, coach, member — salida: `{ id, email, role, member_id }` — códigos: 200, 401.
- `POST /api/v1/auth/me/password` — rol(es): admin, coach, member — entrada: `{ current_password, new_password }` — salida: vacío — códigos: 204, 401, 422.

## Pantalla

- Menú de usuario del `TopBar` y un `SidePanel` "Cambiar contraseña". Estados: guardando, error por campo, éxito.

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `validate_password_policy` con 11 y 12 caracteres.
- **Pruebas:** service (revocación de las demás sesiones, evento, auditoría enmascarada), router (401, 422), front (formulario con Zod).
- **Archivos principales:** `api/src/app/modules/auth/service.py`, `router.py`, `schemas.py`; `web/src/features/auth/components/ChangePasswordPanel.tsx`.

## Supuestos

- Supuesto: la política mínima es 12 caracteres y distinta de la actual (no está definida en los documentos).
- Supuesto: cambiar la contraseña revoca las demás sesiones del usuario, no la actual.

## Dependencias

- US-042 · Iniciar sesión

## INVEST

- **Independiente:** solo necesita sesión.
- **Negociable:** la política de contraseña se puede ajustar.
- **Valiosa:** el usuario rota su contraseña solo.
- **Estimable:** dos endpoints y un panel.
- **Pequeña:** uno o dos días.
- **Testeable:** cada regla tiene un escenario.

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
- [ ] Auditoría verificada para `auth.users`
- [ ] Revisión de PR aprobada
