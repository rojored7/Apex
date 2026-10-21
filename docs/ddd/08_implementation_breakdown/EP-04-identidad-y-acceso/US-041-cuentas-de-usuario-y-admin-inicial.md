# US-041 · Cuentas de usuario y admin inicial — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-041-cuentas-de-usuario-y-admin-inicial.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth (`api/src/app/modules/auth/`, `api/src/app/cli.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El esquema de `auth`, las restricciones y el comando `seed` están definidos por la historia, y DECISIONES N-10 y N-15 cierran la contraseña mínima y el usuario técnico. La migración es la canónica `0004_auth` e incluye el INSERT de `SYSTEM_USER_ID`. Queda una dependencia de núcleo que no cambia el contrato de esta historia: el hook de US-016 tiene que poder enmascarar columnas (`__audit_redact__`). Está listada en dependencias y en riesgos.

## Resumen

Crea las tres tablas del esquema `auth` (`users`, `refresh_tokens`, `one_time_tokens`) en la migración `0004_auth`, inserta el usuario técnico `system@apex.local` con UUID fijo y deja listos los models de SQLAlchemy y las funciones base de `auth.service`: validación de rol, normalización del correo, `get_principal` (lo usa `current_user` de US-034) y `names_for` (lo usa US-110). Agrega `cli seed`, que crea el primer admin activo a partir de `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD`. Es idempotente, emite `UserCreated` y deja auditoría sin el hash.

## Correcciones aplicadas por DECISIONES.md

- La historia solo pide crear el admin inicial. Ahora la migración `0004_auth` también inserta el usuario técnico único `00000000-0000-0000-0000-000000000001` (`system@apex.local`, rol `admin`, `is_active = false`, sin contraseña). `cli seed` lo usa como `created_by` y actor de auditoría, y acepta `--as <email>`. No existe usuario `seed` ni `SYSTEM_ACTOR_ID`: corregido por DECISIONES N-15.
- Para la idempotencia, "ya existe al menos un admin activo" excluye al usuario técnico, porque tiene `is_active = false` y no cuenta como admin activo: corregido por DECISIONES N-15.
- La historia exige como mínimo 12 caracteres en la contraseña del seed. Además se valida contra la lista corta de contraseñas comunes de `validate_password_policy`: corregido por DECISIONES N-10.
- El correo de login va en claro en `auth.users.email`. Es un supuesto aceptado del gate (P5), así que no es una corrección y se anota como riesgo.

## Validación contra el dominio

- El aggregate `User` (raíz) tiene las entidades internas `RefreshToken` y `OneTimeToken` (`02_domain_model.md` 2.11). Coincide con la historia.
- RN-14: los usuarios se dan de baja con `deleted_at` y nunca se borran físicamente. Lo garantizan la falta de funciones `DELETE` y una prueba de arquitectura.
- RN-15: esta historia no expone endpoints. `cli seed` corre fuera de HTTP con el actor `SYSTEM_USER_ID`.
- S7: `member_id` existe desde v0.1 y la base exige `CHECK (role <> 'member' OR member_id IS NOT NULL)`. La regla "admin y coach sin `member_id` en v0.1" vive solo en la función pura y no en la base, para no obligar a migrar cuando llegue P6 en v1.1.
- Invariante "no se puede borrar el último admin activo": aquí solo se define qué es un "admin activo" (rol `admin`, `is_active`, sin `locked_at` ni `deleted_at`, con `password_hash`). La regla la aplican US-049 y US-050.
- Evento emitido: `UserCreated(user_id, role, by)`, una dataclass congelada que se declara en `auth/service.py`. No consume eventos.
- Funciones puras: `validate_user_role(role, member_id)`, `normalize_login_email(email)`, `is_active_admin(user)` y `validate_password_policy(password)`. Esta última se comparte con US-045 y US-048.

## Validación contra la arquitectura

- El módulo dueño es `modules/auth` y el esquema es `auth`. No se importan models de otros módulos. `member_id` es un UUID sin FK entre esquemas: la validez del socio la comprueba `members.service` cuando haga falta (v1.0, US-185).
- Las tablas usan `CommonColumnsMixin` (id UUID asignado en Python, `created_at`, `updated_at`, `created_by`).
- Primitivas: el hash de la contraseña se hace con `core.security.hash_password`, de US-032. `modules/auth` no importa `argon2`, `hashlib` ni `jwt`, y el lint banned-api lo verifica.
- Auditoría: `User` y `OneTimeToken` llevan `__audited__ = True`. `RefreshToken` no se audita, porque rota cada 15 minutos y llenaría la cadena; su ciclo de vida lo registran `SessionsRevoked` y los timestamps de la tabla. `User` declara `__audit_redact__ = {"password_hash"}` para que el hook escriba `"***"`.
- El CLI fija `current_actor` con `SYSTEM_USER_ID` o con el usuario de `--as`, como exige US-016 (sin actor, el flush de una tabla auditada falla).
- `get_principal(user_id)` es la función que US-034 consume desde `core/security`. Ver riesgos: `core` no debe importar `modules`.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- [ ] T1 · `0004_auth`. Tabla `auth.users`:
  - columnas: `id` UUID PK, `email` text NOT NULL, `password_hash` text NULL, `role` text NOT NULL, `member_id` UUID NULL, `is_active` boolean NOT NULL DEFAULT true, `locked_at`, `last_login_at` y `deleted_at` TIMESTAMPTZ NULL, `created_at` y `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now(), `created_by` UUID NOT NULL;
  - CHECK `role IN ('admin','coach','member')`, CHECK `role <> 'member' OR member_id IS NOT NULL` y CHECK `email = lower(btrim(email))`;
  - índice único parcial `uq_users_email_alive` sobre `users(email) WHERE deleted_at IS NULL`. — 1.5 h
- [ ] T2 · `0004_auth`. Tabla `auth.refresh_tokens`:
  - columnas: `id`, `user_id` UUID NOT NULL con FK a `auth.users(id)`, `token_hash` text NOT NULL UNIQUE, `expires_at` TIMESTAMPTZ NOT NULL, `revoked_at` TIMESTAMPTZ NULL, `replaced_by_id` UUID NULL con FK a `auth.refresh_tokens(id)` (para detectar reuso, N-13), `user_agent` varchar(255) NULL y las columnas comunes;
  - índice `ix_refresh_tokens_user_id` sobre `user_id`.

  Tabla `auth.one_time_tokens`:
  - columnas: `id`, `user_id` con FK, `token_hash` text NOT NULL UNIQUE, `purpose` text NOT NULL con CHECK `purpose IN ('activate','reset')`, `expires_at` NOT NULL, `used_at` NULL y las columnas comunes;
  - índice parcial `ix_ott_user_purpose_open` sobre `(user_id, purpose) WHERE used_at IS NULL`. — 1 h
- [ ] T3 · `0004_auth`. `op.execute` del INSERT del usuario técnico:
  - valores: `id = '00000000-0000-0000-0000-000000000001'`, `email = 'system@apex.local'`, `role = 'admin'`, `is_active = false`, `password_hash = NULL` y `created_by` igual al mismo id;
  - el downgrade borra las tablas en orden inverso y conserva el esquema `auth` (lo crea `0001_core_schemas`);
  - comentario en la migración: el INSERT no pasa por el hook de auditoría porque es la "migración inicial" de N-15. — 0.5 h

### Models
- [ ] T4 · `api/src/app/modules/auth/models.py`:
  - `User` con `__audited__ = True` y `__audit_redact__ = {"password_hash"}`;
  - `RefreshToken` sin auditar;
  - `OneTimeToken` con `__audited__ = True`;
  - los tres heredan `CommonColumnsMixin`, con relaciones dentro del propio esquema y tipos `Mapped[...]` estrictos para mypy. — 1.5 h

### Service
- [ ] T5 · Funciones puras en `api/src/app/modules/auth/service.py`:
  - `validate_user_role(role: Role, member_id: UUID | None) -> None`, que lanza `AuthError("member_id_required" | "member_id_not_allowed")`;
  - `normalize_login_email(email: str) -> str`, que aplica `strip` y `lower`;
  - `is_active_admin(user: User) -> bool`;
  - `validate_password_policy(password: str, *, current_hash: str | None = None) -> None`, que exige 12 caracteres o más y rechaza la lista corta `COMMON_PASSWORDS` como constante del módulo (N-10). La comparación con la contraseña actual usa `core.security.verify_password`.
  
  Las excepciones van en `auth/exceptions.py`. — 1.5 h
- [ ] T6 · Casos de uso:
  - `seed_admin(session, email: str, password: str, *, by: UUID) -> SeedResult` (`created` o `skipped`): si existe un admin activo distinto del usuario técnico, devuelve `skipped`; si no, crea el `User` admin activo con `core.security.hash_password` y emite `UserCreated(user_id, role="admin", by)`;
  - `get_principal(session, user_id: UUID) -> Principal | None`, que devuelve `id`, `email`, `role`, `member_id`, `is_active`, `locked_at` y `deleted_at` para `current_user` (US-034);
  - `names_for(session, user_ids: Sequence[UUID]) -> dict[UUID, str]`, que devuelve el correo porque los usuarios no tienen nombre (lo pide US-110);
  - constante `SYSTEM_USER_ID` reexportada desde `core/config.py`. — 2 h

### Schemas
- [ ] T7 · `api/src/app/modules/auth/schemas.py`: tipo `Role = Literal["admin","coach","member"]` y `UserOut` (`id`, `email`, `role`, `member_id`, `status`), sin `password_hash`. Es la base que reutilizan US-045 a US-052. — 0.5 h

### Router
- No aplica.

### Tests unitarios puros
- [ ] T8 · `api/tests/auth/test_pure_users.py`:
  - `validate_user_role` con `member` y `None` (falla), `coach` y `None` (pasa), `coach` con id (falla);
  - `normalize_login_email(" Dueno@Apex.co ")`;
  - `validate_password_policy` con 11 y con 12 caracteres, y con una contraseña común de 12 o más;
  - `is_active_admin` para el usuario técnico (false), un admin bloqueado (false) y un admin activo (true). — 1 h

### Tests de service con PostgreSQL
- [ ] T9 · `api/tests/auth/test_seed.py`:
  - con base vacía, el seed crea el admin con un hash que empieza por `$argon2id$`;
  - hay una fila `insert` en `audit.audit_log` con `after.password_hash == "***"` y `user_id == SYSTEM_USER_ID`;
  - se emite `UserCreated`;
  - un segundo seed devuelve `skipped` y sigue habiendo un solo admin activo;
  - el usuario técnico no hace que el seed devuelva `skipped`. — 1.5 h
- [ ] T10 · `api/tests/auth/test_auth_schema.py`:
  - la base rechaza un INSERT de `member` sin `member_id` (CHECK) y un correo con mayúsculas;
  - el índice parcial deja repetir un correo si el anterior tiene `deleted_at`;
  - el usuario técnico existe tras `upgrade head` con `is_active = false`. — 1 h
- [ ] T11 · `api/tests/cli/test_seed_cli.py` con `typer.testing.CliRunner`:
  - sin `ADMIN_INITIAL_PASSWORD`, o con `"corta"`, el código de salida no es 0 y no se crea ningún usuario;
  - la salida y los logs capturados no contienen la contraseña;
  - `--as dueno@apex.co` atribuye el `created_by` a esa persona. — 1 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T12 · `api/tests/architecture/test_no_physical_delete_users.py`: busca en `src/app` `delete(User)`, `session.delete(` sobre instancias de `User` y SQL `DELETE FROM auth.users`, y falla si encuentra alguno. Deben seguir verdes `test_banned_imports.py` (sin `argon2` en `modules/auth`), `test_no_cross_models.py` y `test_audited_tables.py` de US-107 (`auth.users` auditada). — 1 h

### Front
- No aplica.

### DevOps
- [ ] T13 · Agregar `ADMIN_EMAIL`, `ADMIN_INITIAL_PASSWORD` (de un solo uso y opcional, solo para el seed) y `FRONT_BASE_URL` a `core/config.py` (US-011) y a `.env.example`. La contraseña es `SecretStr`. — 0.5 h
- [ ] T14 · `cli seed` en `api/src/app/cli.py` (typer):
  - lee la configuración, abre la sesión, fija `current_actor`, llama a `auth.service.seed_admin`, hace commit e imprime `creado` u `omitido: ya existe un admin activo` sin datos sensibles;
  - sale con código 2 si falta o es débil la contraseña;
  - acepta `--as <email>`. — 1 h

### Seguridad
- [ ] T15 · Revisión:
  - la contraseña del seed no se loguea (filtro `redact` de US-018) y el runbook de US-117/US-118 dice que la variable se borra después del primer arranque;
  - `password_hash` está enmascarado en la auditoría;
  - el usuario técnico no puede autenticarse (`is_active = false` y `password_hash` nulo), con una prueba cruzada en US-042. — 0.5 h

## Orden de ejecución
1. T8 (pruebas puras, en rojo)
2. T1, T2, T3 (migración)
3. T4 (models)
4. T5 (funciones puras, en verde)
5. T10 (esquema contra la base)
6. T9 y luego T6 (service guiado por la prueba)
7. T7
8. T13, T14 y T11
9. T12
10. T15

## Dependencias técnicas
- US-012 · Base de datos y Alembic multiesquema: `CommonColumnsMixin` con UUID asignado en Python y esquema `auth` creado en `0001_core_schemas`.
- US-015 · Tabla de auditoría y US-016 · Hook after_flush: auditar `users` y `one_time_tokens`. **El hook debe soportar `__audit_redact__` (valor reemplazado por `"***"`) y `__audit_exclude__` (columnas que no generan diff; lo usa `last_login_at` en US-042).** US-016 no lo define hoy.
- US-032 · argon2id: `hash_password` y `verify_password`.
- US-011 · Configuración: `SYSTEM_USER_ID`, `FRONT_BASE_URL` y las variables del seed.
- US-014 · Bus de eventos: emitir `UserCreated`.
- US-018 · Logging sin datos sensibles: prueba de la salida del CLI.

## Endpoints
- Ninguno.

## Riesgos
- P5, correo de login en claro: si el gate pide índice ciego, cambian la columna y el login. Mitigación: la columna se aísla detrás de `normalize_login_email` y de una sola consulta `_find_alive_by_email`.
- Sin `__audit_redact__` en US-016 el hash quedaría en la cadena de auditoría, que es inmutable. Mitigación: T9 falla en rojo hasta que US-016 lo soporte, y esta historia no se cierra antes.
- US-034 dice que `core/security` "carga el usuario por `auth.service`", lo que haría que `core` dependa de `modules`. Mitigación propuesta: `core/security.py` define el `Protocol` `PrincipalLoader` y `register_principal_loader()`, y `main.py` registra `auth.service.get_principal` al arrancar. Esto se reporta al orquestador.
- El INSERT del usuario técnico en la migración no deja fila de auditoría. Es aceptable porque es estructura y no una acción de una persona; queda documentado en la migración.

## Estimación
- Backend: 9.5 h
- Front: 0 h
- Pruebas: 5.5 h
- DevOps / seguridad: 1 h
- **Total: 16 h**
- Queda 1 h por encima de la referencia de 3 puntos (10 a 15 h). La diferencia sale del INSERT del usuario técnico (N-15), de la columna `replaced_by_id` para N-13 y de `get_principal` y `names_for`, que piden otras épicas.

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/auth/test_pure_users.py -q`
- [ ] `cd api && uv run pytest tests/auth/test_seed.py tests/auth/test_auth_schema.py -q`
- [ ] `cd api && uv run pytest tests/cli/test_seed_cli.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `psql -c "SELECT email, role, is_active FROM auth.users WHERE id = '00000000-0000-0000-0000-000000000001'"` devuelve `system@apex.local | admin | f`.
- [ ] `ADMIN_EMAIL=dueno@apex.co ADMIN_INITIAL_PASSWORD=<16 caracteres> uv run python -m app.cli seed` corrido dos veces deja exactamente un admin activo, y `SELECT after->>'password_hash' FROM audit.audit_log WHERE table_name = 'users'` devuelve `***`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.auth --cov-fail-under=80`
