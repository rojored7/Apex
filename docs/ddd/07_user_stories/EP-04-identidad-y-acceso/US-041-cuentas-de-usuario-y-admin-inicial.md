# US-041 · Como administrador quiero que existan las cuentas de usuario y un admin inicial creado por comando para poder entrar al sistema el primer día

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (esquema `auth`, módulo `auth`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero que existan las tablas de usuarios, sesiones y tokens de un solo uso, y un comando que cree la primera cuenta admin
para poder entrar al sistema el primer día sin tocar la base a mano

## Contexto de dominio

- **Aggregate / entidades:** `User` (raíz) con `RefreshToken` y `OneTimeToken` como entidades internas (`02_domain_model.md` 2.11).
- **Reglas que aplica:** RN-14 (baja lógica de usuarios con `deleted_at`), RN-15 (rol por endpoint), S7 (`member_id` existe desde v0.1, obligatorio si `role = member`), P5 (correo de login en claro en `auth.users.email`).
- **Eventos que emite:** `UserCreated` (al sembrar el admin inicial).
- **Eventos que consume:** ninguno
- **Funciones puras:** `auth.validate_user_role(role, member_id) -> None | AuthError` (rol `member` exige `member_id`; `admin` y `coach` lo exigen nulo en v0.1).

## Alcance

- **Backend:** `models.py` de `auth` con `users`, `refresh_tokens`, `one_time_tokens`; migración de Alembic; `cli seed` que crea el admin inicial con la contraseña de una variable de entorno de un solo uso.
- **Front:** No aplica

## Criterios de aceptación

1. Existe la migración que crea en el esquema `auth` las tablas `users`, `refresh_tokens` y `one_time_tokens`, cada una con `id` UUID, `created_at`, `updated_at` y `created_by` (TIMESTAMPTZ en UTC).
2. `users` tiene `email` único (en claro, P5), `password_hash`, `role` restringido a `admin`, `coach` o `member`, `member_id` nulo, `is_active`, `locked_at` y `deleted_at`; la unicidad de `email` aplica solo a filas con `deleted_at IS NULL`.
3. Una restricción `CHECK` en la base impide `role = 'member'` con `member_id` nulo.
4. `refresh_tokens` guarda solo `token_hash` (nunca el token), `expires_at`, `revoked_at` y `user_agent`; `one_time_tokens` guarda `token_hash`, `purpose` (`activate` o `reset`), `expires_at` y `used_at`.
5. `users` está marcada con `__audited__ = True`: crear el admin inicial deja una fila en `audit.audit_log` con acción `insert`, y `password_hash` no aparece en `before` ni en `after` (se reemplaza por `"***"`).
6. `uv run python -m app.cli seed` con `APEX_SEED_ADMIN_EMAIL` y `APEX_SEED_ADMIN_PASSWORD` definidas crea un usuario `admin` activo con la contraseña hasheada con argon2id y emite `UserCreated`.
7. Si ya existe al menos un admin activo no borrado, `cli seed` no crea nada, termina con código 0 y lo informa (idempotente).
8. Si falta `APEX_SEED_ADMIN_PASSWORD` o tiene menos de 12 caracteres, `cli seed` termina con código distinto de 0 sin escribir en la base.
9. La contraseña del seed nunca se imprime en logs ni en la salida del comando.
10. No existe borrado físico de usuarios: no hay ruta ni función de service que ejecute `DELETE` sobre `auth.users`.

## Escenarios BDD

```gherkin
# language: es
Característica: Cuentas de usuario y admin inicial

  Antecedentes:
    Dado una base de datos con todas las migraciones aplicadas

  Escenario: Sembrar el admin inicial en una base vacía
    Dado que no existe ningún usuario en "auth.users"
    Y la variable "APEX_SEED_ADMIN_EMAIL" vale "dueno@apex.co"
    Y la variable "APEX_SEED_ADMIN_PASSWORD" tiene 16 caracteres
    Cuando el operador ejecuta "cli seed"
    Entonces existe un usuario "dueno@apex.co" con rol "admin" activo
    Y su "password_hash" empieza por "$argon2id$"
    Y hay una fila de auditoría "insert" sobre "users" sin el hash en claro

  Escenario: Correr el seed dos veces no duplica el admin
    Dado que ya existe un admin activo "dueno@apex.co"
    Cuando el operador ejecuta "cli seed" otra vez
    Entonces el comando termina con código 0
    Y sigue existiendo un solo usuario con rol "admin"

  Escenario: Contraseña de seed demasiado corta
    Dado que no existe ningún usuario
    Y la variable "APEX_SEED_ADMIN_PASSWORD" vale "corta"
    Cuando el operador ejecuta "cli seed"
    Entonces el comando termina con código distinto de 0
    Y no se crea ningún usuario

  Escenario: La base rechaza un socio sin member_id
    Cuando se intenta insertar un usuario con rol "member" y "member_id" nulo
    Entonces la base rechaza la fila por la restricción de rol
```

## Endpoints

- Ninguno. Comando CLI: `uv run python -m app.cli seed`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** sí; esquema `auth` con las tres tablas; índice único parcial `users(email) WHERE deleted_at IS NULL`; índice en `refresh_tokens(user_id)` y `one_time_tokens(token_hash)`.
- **Trigger / restricciones:** `CHECK (role IN ('admin','coach','member'))`; `CHECK (role <> 'member' OR member_id IS NOT NULL)`; `CHECK (purpose IN ('activate','reset'))`.
- **Funciones puras a probar:** `validate_user_role("member", None)` falla; `validate_user_role("coach", None)` pasa.
- **Pruebas:** service con base real (seed, idempotencia, auditoría sin hash), arquitectura (sin `DELETE` sobre users), prueba de que el filtro de logs oculta la contraseña.
- **Archivos principales:** `api/src/app/modules/auth/models.py`, `service.py`, `api/src/app/cli.py`, `api/migrations/versions/<rev>_auth_tables.py`.

## Supuestos

- Supuesto: el comando lee `APEX_SEED_ADMIN_EMAIL` y `APEX_SEED_ADMIN_PASSWORD` (nombres no definidos en los documentos) y exige al menos 12 caracteres de contraseña; la política de contraseñas no está definida en ningún documento.
- Supuesto: en v0.1 `admin` y `coach` tienen `member_id` nulo (coach que también es socio es P6, v1.1).

## Dependencias

- US-032 · Hash de contraseñas argon2id (hash del admin inicial)
- US-016 · Hook de auditoría after_flush (auditar `users`)

## INVEST

- **Independiente:** solo necesita argon2 y el hook de auditoría; no depende de pantallas.
- **Negociable:** los nombres de variables y la política de contraseña se pueden ajustar sin cambiar el modelo.
- **Valiosa:** sin admin inicial nadie puede entrar al sistema.
- **Estimable:** tres tablas, una migración y un comando.
- **Pequeña:** cabe en dos o tres días.
- **Testeable:** cada criterio se prueba con base real y con el código de salida del comando.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error (no aplica: sin endpoints)
- [ ] Front: pruebas de componente y página; sin colores literales (no aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado (no aplica)
- [ ] Auditoría verificada para `auth.users`
- [ ] Revisión de PR aprobada
