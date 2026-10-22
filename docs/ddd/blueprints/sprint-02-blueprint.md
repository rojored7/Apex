# Blueprint de implementación · Sprint 2 · Identidad, configuración, shell del front, socios y planes

- Rama: `feat/sprint-02-identidad-config-socios-planes`, desde `482295f` (cierre del Sprint 1).
- Entradas: `SPRINT-02.md`, los desgloses de US-031, US-042 a US-055, US-057, US-058, US-061, US-062, US-067 a US-070, US-078, US-079 y US-107, `05_service_design.md`, `DECISIONES.md`, `docs/design/`, el código del Sprint 1 y la revisión de seguridad del cuaderno `docs/scratch/sprint-01.md`.
- Este archivo es solo un plano. No cambia código. Donde el desglose y el código existente chocan hay una línea que empieza por **DECISIÓN**, con la opción recomendada. Las decisiones que se acepten se anotan en `docs/ddd/DECISIONES.md` (sección "Sprint 2") en el primer checkpoint.

## 0. Cómo leerlo

1. Sección 1: decisiones donde el desglose, el plan y el código chocan (léelas antes de empezar).
2. Sección 2: reglas transversales del backend, del front y de las pruebas.
3. Sección 3: orden de construcción y dependencias entre slices.
4. Secciones 4 a 6: slice por slice (W0, backend B1 a B9, front F1 a F8).
5. Sección 7: flujos de datos (sesión, activación y reset, configuración, alta de socio).
6. Sección 8: pruebas de arquitectura que se amplían y las que nacen.
7. Sección 9: fixtures de prueba que faltan.
8. Sección 10: cierre de la deuda de seguridad M-1, M-2, M-3, M-8, L-1, L-4, L-5 y L-8, slice por slice.
9. Sección 11: riesgos y puntos abiertos.

Convención de cada slice: Rojo (stubs y pruebas que fallan), Verde (implementación), Gate (comando). En cada slice backend que cambia rutas se regenera `docs/openapi.json` con `cd api && uv run python -m app.cli export-openapi ../docs/openapi.json` (la prueba `test_docs_openapi_json_esta_al_dia` y el paso de CI lo exigen). En cada slice front que consume el contrato se regeneran los tipos con `cd web && npm run gen:api`.

## 1. DECISIONES: choques entre el desglose, el plan y el código existente

**DECISIÓN 1 · Estado de cuenta `pending_activation`.** El código tiene `UserStatus = active | inactive | locked | deleted` y `user_status()` (`auth/service.py`) con la prueba `test_pure_users.py`, donde el usuario técnico (`is_active=false`, sin hash) debe dar `inactive`. El desglose de US-046 pide `active | locked | pending_activation | deleted` con `pending_activation` antes que `inactive`. Recomendado: ampliar el literal a cinco valores y fijar el orden `deleted > locked > not is_active (inactive) > password_hash is None (pending_activation) > active`. La prueba existente sigue verde; un usuario creado con enlace (`is_active=true`, sin hash) es `pending_activation`. El filtro `status` de `GET /users` acepta los cinco valores; sin filtro excluye `deleted`.

**DECISIÓN 2 · Nombre de tabla y redacción en la auditoría.** El hook escribe `table_name = "auth.users"` (esquema y tabla) y redacta con `"***"` (`REDACTED`), no con `"<redacted>"` (texto de la demo del sprint) ni `table_name = 'users'` (texto de US-045 y US-107). Recomendado: mantener el código y corregir pruebas y demo: `table_name = 'auth.users'` y `password_hash = '***'`. Los handlers de `modules/audit` usan `"auth.users"`.

**DECISIÓN 3 · Un router plano por módulo.** FastAPI 0.157 incluye los routers de forma perezosa; `test_list_routes_use_page_params` lee `router.routes` de cada módulo y no vería rutas de sub-routers anidados (pasaría en falso). Recomendado: cada `router.py` define todas sus rutas sobre un solo `APIRouter` con la ruta completa en cada decorador (`@router.post("/auth/login")`, `@router.get("/users")`), y además endurecer esa prueba para que recorra `effective_routes(create_app(...))` en vez de `router.routes`. Los helpers de cookie y de `Cache-Control` viven en `auth/cookies.py` para que `router.py` no pase de unas 400 líneas.

**DECISIÓN 4 · Tamaño de `auth/service.py`.** Con login, refresh, cuentas, enlaces y ciclo de vida supera con facilidad las 800 líneas del reglamento. Recomendado: `auth/rules.py` (funciones puras: `can_login`, `user_status`, `is_active_admin`, `validate_user_role`, `validate_password_policy`, `would_remove_last_admin`, `lock_precondition`, `link_purpose_for`, `activation_url`, `is_refresh_usable`, `is_reuse`, `is_one_time_token_usable`, TTL) y `auth/tokens.py` (helpers con sesión: `revoke_all`, `issue_one_time_token`, `lock_active_admins`, `get_alive_or_404`). `service.py` queda como fachada pública (casos de uso, eventos, cargador de principal) y re-exporta las puras con `__all__`; las pruebas importan siempre desde `app.modules.auth.service`. `rules.py` y `tokens.py` son privados del módulo.

**DECISIÓN 5 · Correo sin `EmailStr`.** `EmailStr` exige `email-validator` (licencia Unlicense, fuera de la lista de `CLAUDE.md`) y `dnspython`. Recomendado: no agregar dependencias. Crear `app/core/validators.py` con `EmailAddress = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=254), AfterValidator(_check_shape)]`, donde `_check_shape` usa la regex `^[^@\s]+@[^@\s]+\.[^@\s]+$`. Lo usan `auth`, `settings` (`gym.email`) y `members`. El correo de login se sigue normalizando con `normalize_login_email` (CHECK `email = lower(btrim(email))`).

**DECISIÓN 6 · Nombres reales del código frente al desglose.**
- Hash ficticio: ya existe `core.security.dummy_verify(plain)`; no se crea `DUMMY_HASH` (T3 de US-042).
- Índice ciego: la firma real es `normalize_for_index(value, kind)` en `core/crypto/normalize.py` (kind: `generic`, `phone`, `email`), no `(data_class, value)` como dice US-070. `classify_query` obtiene el `kind` con `get_spec(data_class).index_kind` y captura `CryptoError("empty_value")`.
- `--as`: `active_admin_id_by_email` devuelve a cualquier persona no borrada, también inactiva o bloqueada, y hasta `system@apex.local` (L-4). Recomendado: renombrar a `active_user_id_by_email` y exigir `user_status == "active"` y `id != SYSTEM_USER_ID`; actualizar `cli.resolve_actor` y las pruebas que lo usan.
- Registro de errores en `core/errors.py` (T7 de US-069, T5 de US-078): no hace falta tocar `core/`; `MemberError`, `PlanError` y `SettingsError` heredan de `DomainError` y ya salen por el handler de dominio.

**DECISIÓN 7 · Escrituras por ORM con `SELECT ... FOR UPDATE`, no `UPDATE ... RETURNING`.** US-048 (consumo del token) y US-043 (rotación del refresh) proponen `UPDATE` condicional de Core. Un `UPDATE` de Core se salta el hook de auditoría (sin fila `update` en `one_time_tokens`, que US-048 y US-052 piden). Recomendado: leer la fila con `select(...).with_for_update()`, comprobar la regla pura y mutar el objeto; el segundo concurrente espera el candado, ve `used_at` o `replaced_by_id` ya puestos y recibe `invalid_token` o reuso. Es atómico y auditable. `revoke_all` sí puede ser un `UPDATE` masivo porque `refresh_tokens` no está auditada.

**DECISIÓN 8 · Auditoría del login: evento, no llamada directa.** US-107 T1 dice que `auth.service.login` llama a `core.audit.record` con una sesión propia; el plan del sprint ya resolvió lo contrario: `login` emite `LoginAttempted` y `modules/audit` se suscribe. Recomendado: el plan del sprint. El handler escribe en la sesión del emisor y, para sobrevivir al 401, el service hace `await session.commit()` justo después de `events.emit` y antes de lanzar `InvalidCredentials` (contrato de US-042 T2). `get_session` usa `session.begin()` como context manager; un `commit()` explícito dentro del bloque es válido en SQLAlchemy 2 y, al salir por la excepción, no queda nada pendiente. El bloque del fallo corre dentro de `actor_scope(user.id)` y el commit va dentro del mismo scope. Lo cubren `test_login_service.py` y `test_router_login_audit.py`.

**DECISIÓN 9 · Migración nueva de auth: `0005b_auth_security`.** La numeración canónica del desglose (`0001` a `0013`) reserva 0008 en adelante para memberships y pagos. Para no renumerar, la migración nueva de `auth` se llama `0005b_auth_security` con `down_revision = "0005_settings"`, y `0006_members` depende de ella (`down_revision = "0005b_auth_security"`). Contenido: `auth.users.must_change_password boolean NOT NULL DEFAULT false` y `auth.users.failed_login_count integer NOT NULL DEFAULT 0` con `CHECK (failed_login_count >= 0)`. Nunca se edita `0004`. Va en el slice S2-B2 (primer uso). Orden de aplicación: 0004 → 0005_settings (B1) → 0005b (B2) → 0006 (B7) → 0007 (B9).

**DECISIÓN 10 · Cuenta bloqueada por intentos (M-2).** El límite por IP no frena un ataque distribuido ni IPv6. Recomendado, en tres capas:
1. Límite por cuenta en memoria dentro de `login`: 10 intentos por correo normalizado cada 900 s, contados antes de argon2 y también para correos inexistentes (misma respuesta 429, sin enumerar). Settings: `LOGIN_ACCOUNT_LIMIT=10`, `LOGIN_ACCOUNT_WINDOW_S=900`.
2. Bloqueo persistente: tras `LOGIN_LOCK_AFTER=20` fallos consecutivos de contraseña de una cuenta existente se pone `locked_at`, se emite `UserLocked(by=SYSTEM_USER_ID, reason="too_many_failures")` y `SessionsRevoked(reason="lock")`. Excepción: nunca se auto-bloquea al último admin activo (un atacante podría dejar el sistema sin acceso); a esa cuenta solo le aplica la capa 1. `failed_login_count` vuelve a 0 con cada login correcto, activación o restablecimiento, y no genera fila de auditoría (`__audit_exclude__`).
3. IPv6 por /64: en `core/ratelimit` la clave del limitador por IP usa la red /64 cuando la IP es IPv6 (el log conserva la IP completa).
Complemento barato: `cli unlock-user <correo> [--as <correo>]` para el caso en que no quede ningún admin que pueda desbloquear.

**DECISIÓN 11 · `refresh_keyring` pasa a `current_user` (M-3).** Hoy es una dependencia de todo el router de cada módulo (`main.include_module_routers`) y corre con una sesión de base de datos antes de validar el token (también en el login). Recomendado: quitar esa dependencia de `main.py` y llamar a una función nueva `refresh_current(session)` de `core/crypto/keyring.py` dentro de `current_user`, justo después de que el cargador de principal devuelva un usuario válido. `core/security` ya puede importar `core/crypto` (no hay ciclo: `keyring` no importa `security`; lo vigila `test_sin_ciclos_entre_modulos_de_core`). Las rutas públicas no tocan el keyring.

**DECISIÓN 12 · `ADMIN_*` solo en `tools` y contraseña inicial de un solo uso (M-8).**
- Sacar `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` de `Settings` (hoy el api los recibe por `env_file`). Agregarlos a `NON_API_ENV_VARS` y leerlos con una clase nueva `SeedSettings` (`BaseSettings`, `extra="forbid"`, `env_file=".env.seed"`) dentro de `core/config.py`, único lugar permitido para leer el entorno. Las pruebas actuales de `cli seed` usan `monkeypatch.setenv`, que `SeedSettings` también lee.
- `.env.example` deja de traer esas dos variables; se crea `.env.seed.example`. `.env.seed` va a `.gitignore` y a `scripts/ci/check-key-files.sh` (bloquear `.env.seed`, permitir `.env.seed.example`). En `infra/compose.yml` el servicio `tools` usa `env_file: [../.env, {path: ../.env.seed, required: false}]`; `api` y `worker` siguen solo con `../.env`.
- `seed_admin` crea al admin con `must_change_password=true`. El cambio forzado lo impone `require_role` (B3). Opción `seed --no-force-change`, solo con `ENV=dev`, para E2E y scripts de CI.

**DECISIÓN 13 · `COOKIE_SECURE`.** El desglose (T16 de US-042) pide valor por defecto `true`; el código y `.env.example` lo dejan en `false` porque en v0.1 se sirve por HTTP en la LAN (P7) y el navegador descarta cookies `Secure` sobre HTTP. Recomendado: mantener `false` y agregar en el lifespan un `logger.warning` cuando `ENV=production` y `COOKIE_SECURE=false`. La cookie siempre sale `HttpOnly`, `SameSite=Strict`, `Path=/api/v1/auth`, `Max-Age=REFRESH_TOKEN_TTL_DAYS*86400` y `Secure` según el valor (L-8).

**DECISIÓN 14 · `GET /auth/me` sí consulta la base.** US-045 T1 dice "sin volver a consultar", pero el plan del sprint pide `gym_name` (US-061) y `must_change_password`. Recomendado: `me()` carga el `User` por `principal.user_id` y llama a `settings.service.gym_name(session)` (service a service; `auth` → `settings`, `settings` no importa `auth`). Dos lecturas por llamada; aceptable.

**DECISIÓN 15 · Secciones de configuración del Sprint 2 y rutas tipadas.** `ENABLED_SECTIONS = {gym, privacy, memberships}`; `payment_methods` (US-056) queda fuera del sprint y responde 404 `section_not_available` junto con `hours`, `channels`, `classes` y `tv`. Los 29 endpoints del plan cuentan `GET/PATCH /settings/{section}` (genérico) más `GET/PATCH` de `/settings/gym`, `/settings/privacy` y `/settings/memberships` (tipados, declarados antes que el genérico para que ganen el emparejamiento): 7 de auth + 9 de usuarios + 2 + 6 de settings + 2 de socios + 3 de planes = 29. `section` en la ruta genérica es `str` (no enum) para que una clave desconocida dé 404 y no 422. `PATCH` reemplaza el valor completo de la sección (sin merge); los campos opcionales omitidos vuelven a su valor por defecto.

**DECISIÓN 16 · Campos de socio frente al diseño `Socio_Form`.**
- El diseño trae "Nombre completo"; el contrato tiene `first_name` y `last_name` (van al leaderboard). El formulario lleva dos campos (`// DESIGN-GAP:`).
- El diseño trae "Tipo de documento" (CC, CE, TI, Pasaporte) y la lista muestra `CC •••• 4417`, pero el desglose de `0006_members` no tiene columna. Recomendado agregar `document_type text NOT NULL DEFAULT 'CC'` con `CHECK (document_type IN ('CC','CE','TI','PA'))` (dato no sensible, sin cifrar) ahora, mientras la migración no se ha aplicado. La unicidad sigue siendo por `document_idx` (el índice ciego se calcula solo del número). `mask` antepone el tipo: `CC •••• 0304`. Si no se acepta, el formulario omite el campo y la ficha muestra `•••• 0304` (`MaskedValue` ya acepta `documentType` opcional).
- Teléfono obligatorio en el diseño y opcional en N-19: manda N-19.
- Fuera del sprint (`// DESIGN-GAP:`): foto, firma y archivo de autorización (attachments, v0.3), "Acceso al portal" (v1.0), "Unidad para cargas" (atleta) y "Observaciones de salud". La casilla "El socio autorizó el tratamiento de datos" sí entra y envía `data_consent_at = ahora`.
- `emergency_contact` (JSON cifrado): `{name, phone, relationship?}`; `relationship` es opcional porque es JSON y no cuesta migración.
- La lista del diseño trae teléfono, plan, vence y última asistencia; la lista del sprint no devuelve ningún campo cifrado ni enmascarado (N-01) y no hay membresías todavía: columnas Nombre, Estado del socio, Membresía (vacía hasta el Sprint 3). Los chips del Sprint 2 son "Todos" y "Dados de baja".

**DECISIÓN 17 · Usuarios sin nombre.** `Usuarios.html` muestra "Nombre"; `auth.users` no tiene nombre (el `display_name` llega con US-110). La tabla del sprint muestra Correo, Rol, Último acceso, Estado, Sesiones abiertas y Acciones; el panel de edición pide Correo y Rol (`// DESIGN-GAP:`). Las cuentas de rol `member` no se crean desde esta pantalla (el filtro "Socio" y la fila "socia" del diseño quedan fuera).

**DECISIÓN 18 · Activación y restablecimiento no inician sesión.** El diseño dice "Guardar y entrar"; US-048 responde `204` y el front lleva a `/login` con aviso. Recomendado: `204`, texto del botón "Guardar contraseña" y `// DESIGN-GAP:`. Evita emitir una sesión desde un enlace. Para `must_change_password` se agrega la ruta `/cambiar-clave` (fuera de `ROUTES.md`, `// DESIGN-GAP:`), con la misma tarjeta de `ResetPage`, accesible con sesión.

**DECISIÓN 19 · Fixtures.** `bus_listo`, `sin_llaves` y `proveedor_local` viven en `tests/crypto/conftest.py` y no los ven `tests/members` ni `tests/auth`. Recomendado: moverlos a `tests/conftest.py`. El fixture de la app HTTP no corre el `lifespan` (su `ensure_keys` confirmaría en otra conexión mientras el savepoint de la prueba tiene un `DELETE` abierto sobre `crypto_keys`: espera de candado); configura seguridad, proveedor y keyring a mano y sustituye `get_session` por la sesión de la prueba. Detalle en la sección 9.

**DECISIÓN 20 · El centinela `test_no_sensitive_in_logs.py` se activa solo.** Su `skipif` se apaga en cuanto existe `app/modules/members/router.py` (S2-B7) y entonces falla con `AssertionError("implementar al activar")`. Recomendado: implementarlo en S2-B7 (login real y `POST /members` real con captura de stdout y `caplog`), y dejar la pata de `reveal` como una prueba aparte saltada con dueño "US-074, Sprint 3".

**DECISIÓN 21 · `test_audited_tables` y módulos sin modelos.** `_cargar_modelos()` importa `app.modules.<m>.models` para cada `m` en `MODULES`; `audit` (y luego `dashboard`) no tienen `models.py`. Recomendado: importar solo si `importlib.util.find_spec` lo encuentra. `audit` entra en `MODULES` con un `router.py` vacío (el mismo recurso que usó `auth` en el Sprint 1) para que `include_module_routers` no cambie. Orden final de `MODULES`: `("auth", "settings", "audit", "members", "plans")`.

**DECISIÓN 22 · Dependencias nuevas del front.**
- `@hookform/resolvers` (MIT): `react-hook-form` y `zod` están, el resolver no. Recomendado agregarlo y pasar `npm run licenses`. Alternativa: un adaptador propio de 20 líneas en `shared/lib/zodResolver.ts`.
- Para W0 y F8: `@axe-core/playwright` (MPL-2.0, solo desarrollo; `axe-core` ya figura en `scripts/ci/licenses-exceptions.txt`, agregar la línea del paquete). `vitest-axe` ya está.

**DECISIÓN 23 · Fuente única de rutas del front.** El desglose reparte la tabla de rutas en tres sitios (`handle.roles` de US-067, `access` de US-053 y `routes.reference.ts`). Recomendado: `web/src/config/routeTable.ts` como única tabla (`path`, `feature`, `access`, `layout`, página `lazy`), que consumen `routes.tsx`, `core/auth/routeAccess.ts` y `layouts/nav.ts`; `routes.reference.ts` queda como oráculo escrito a mano desde `ROUTES.md` para la prueba de inventario. `homeFor` vive en `routeAccess.ts` (no en un `home.ts` aparte). Sin respaldo de candado en `localStorage` para Web Locks (los navegadores objetivo lo tienen): sin `navigator.locks` solo se usa el single-flight de la pestaña más el canal; así `core/auth` no toca almacenamiento persistente.

**DECISIÓN 24 · `StatusTag` solo conoce estados de membresía.** `Usuarios` necesita "Activo", "Bloqueado", "Pendiente de activación", "Dado de baja", y `Socios` necesita "Dado de baja". Recomendado extender `shared/ui/statusLabel.ts` con `ACCOUNT_LABELS` y `ACCOUNT_TONES` y que `StatusTag` reciba `status` (membresía) o `account` (cuenta). Etiquetas: `active` "Activo", `inactive` "Inactivo", `locked` "Bloqueado" (tono error), `pending_activation` "Pendiente de activación" (tono advertencia), `deleted` "Dado de baja" (tono neutro). Va en S2-F4a (gate `web/shared`) y F8 lo mete al catálogo.

**DECISIÓN 25 · Inicio.** El destino de `homeFor` es `/`, y `GET /dashboard` llega en el Sprint 3. Recomendado: `features/dashboard/pages/InicioPage.tsx` mínima (saludo con el correo y accesos a Socios y, para admin, Usuarios y Configuración) con `// DESIGN-GAP:`. Features habilitadas en el Sprint 2: `auth`, `dashboard`, `members`, `plans`, `users`, `settings`.

**DECISIÓN 26 · `/planes` en el front y `GET /plans` para el coach.** `ROUTES.md` dice "Planes, solo admin" y el API deja al coach `GET /plans?active=true` (selector de venta del Sprint 3). Se mantiene: la ruta `/planes` exige `plans.view` (admin); el endpoint conserva su regla de alcance para el coach.

**DECISIÓN 27 · Marca `perf`.** `pyproject.toml` usa `--strict-markers` y solo declara `db`. Agregar `perf` a `markers` (S2-B8). La prueba con 1.000 socios queda dentro del gate del slice y de `run-gates`.

**DECISIÓN 28 · Reuso de un refresh por reintento de red.** Con N-13 estricto, si el navegador pierde la respuesta de un `refresh` exitoso y reintenta con la cookie vieja, el segundo intento parece un reuso y revoca todas las sesiones. Recomendado: aceptar el riesgo (probabilidad baja; el efecto es volver a iniciar sesión), anotarlo en el runbook y no agregar período de gracia.

**DECISIÓN 29 · Nginx y la query string.** El `log_format apex` ya escribe `$uri` (sin query), así que `q` de `/members` no se registra hoy; lo que sí queda en el log es el token en la ruta `/restablecer/<token>`. S2-W0-1 agrega `location ~ ^/restablecer/ { access_log off; ... }` con `Referrer-Policy: no-referrer` y una prueba que fija que ningún `log_format` use `$request_uri` ni `$args`.

**DECISIÓN 30 · Longitud máxima de contraseña (L-5).** Constante `PASSWORD_MAX_LENGTH = 128` en `core/security.py`; `WeakReason` gana `"too_long"` y `validate_password_policy` lo aplica. Los schemas de entrada (`LoginIn`, `ChangePasswordIn`, `ResetIn`) usan `max_length=128` (422 con `field`).

## 2. Reglas transversales

### Backend
1. Routers: solo validan, declaran rol (`require_role`), llaman al service y devuelven; cero `select` en routers. Listas con `Annotated[PageParams, Depends()]` y `Page[T]`.
2. Un módulo solo llama a otro por su `service.py`. Aristas nuevas del sprint: `auth` → `settings` (`gym_name`) y `audit` → `auth` (importa las clases de evento). No hay aristas inversas ni ciclos. `members`, `plans` y `settings` no llaman a nadie.
3. Los eventos se declaran en el `service.py` del emisor como `@dataclass(frozen=True, kw_only=True)` que heredan de `DomainEvent`; los handlers se registran al importar el `service.py` del suscriptor con `events.subscribe`. Un efecto que debe sobrevivir al 401 se confirma con `commit()` antes de lanzar.
4. Todo caso de uso async recibe `session: AsyncSession` primero. El actor sale de `current_actor`; las rutas públicas lo fijan con `actor_scope(...)` y hacen `flush()` dentro del scope.
5. Escrituras sobre tablas auditadas siempre por ORM. En columnas JSONB se reemplaza el `dict` completo (no se muta en sitio) para que el historial del atributo vea el cambio.
6. Excepciones de dominio en `exceptions.py` heredando de `DomainError(code, message, field=..., existing_id=..., status=...)`. Nunca valores del usuario en `message`.
7. Ningún secreto, hash ni token en `message`, logs ni auditoría. `core/logging.py` gana dos patrones en `redact_text` (`/restablecer/[A-Za-z0-9_-]+` y `apex_refresh=[^;\s]+`) y las claves `activation_url`, `url` y `set-cookie` en `SENSITIVE_KEYS` (S2-B3, con prueba en `tests/core/test_logging_redact.py`).
8. Cada migración se prueba con `tests/migrations/test_<revision>.py` (esquema, CHECKs, índices) y entra en el ciclo `upgrade head → downgrade -1 → upgrade head`.
9. Cada cambio de contrato regenera `docs/openapi.json`.

### Front
1. Todo dato del servidor por TanStack Query; todo formulario por React Hook Form + Zod; toda lista pagina en el servidor con `useListParams` (la URL es el estado).
2. Cada feature: `api.ts` (hooks), `schemas.ts` (Zod y mapeo de errores), `pages/`, `components/`. Los tipos del API salen de `core/api/types.ts` (generado).
3. Ningún rol comparado con un literal fuera de `core/auth/permissions.ts` y `core/auth/session.ts` (`tests/unit/no-role-literals.test.ts`, `tests/lint/restricted-config.ts`): se usa `can()`, `useCan()`, `<Can>`. Las etiquetas de rol (`ROLE_LABELS`) viven en `permissions.ts`.
4. Ningún `console`, `fetch` directo ni `Intl`/`toLocale*` fuera de `core/api` y `core/i18n`.
5. Ni el access token ni el enlace de activación en `localStorage` o `sessionStorage`.
6. Todo componente compartido nuevo va a `shared/ui/` con su prueba; todo faltante de diseño lleva `// DESIGN-GAP:`.

### Pruebas
1. TDD por slice: Rojo con stubs que lanzan `NotImplementedError`, Verde y gate (`bash scripts/workflow/slice-gate.sh <modulo> <archivos de Rojo>` más `tests/architecture`).
2. Puras sin base; de service con la sesión de savepoint (`session`); de router con el cliente HTTP de la sección 9.
3. Reloj con `FrozenClock` vía `set_clock`; argon2 con parámetros mínimos solo en pruebas (`configure_password_hasher(time_cost=1, memory_cost_kib=8, parallelism=1)`, restaurado al terminar).

## 3. Orden de construcción y dependencias

Orden de ejecución (el del plan): S2-W0-1, B1, B2, B3, B4, B5, B6, B7, B8, B9, F1, F2, F3, F4a, F4b, F5, F6, F7, F8. Un checkpoint por slice (`scripts/workflow/checkpoint-commit.sh`).

Dependencias duras:
- W0-1 antes de B2: la red fija de Compose y `.env.seed` se usan al probar login y seed contra el stack.
- B1 (`settings`, migración 0005) antes de B3: `me()` llama a `settings.service.gym_name`. B1 también fija la cadena de migraciones: `0005_settings` es el padre de `0005b_auth_security` (B2).
- B2 trae todo lo común de sesión: migración `0005b`, `core/validators`, `core/ratelimit` (IPv6 y clave por cuenta), `core/security` (`PASSWORD_MAX_LENGTH`, `Principal.must_change_password`, `refresh_current` en `current_user`), `SeedSettings`, `auth/{rules,tokens,cookies}.py`, eventos `LoginAttempted`, `SessionsRevoked` y `UserLocked`.
- B3 después de B2 (usa `revoke_all`, cookie de sesión actual, `Principal`).
- B4 después de B3 (`issue_one_time_token` se crea en B3 con `create_user`; B4 lo reutiliza en `forgot`, `reset` y `resend_link`).
- B5 después de B4 (`resend_link` comparte elegibilidad con bloquear) y de B3 (`list_users` se amplía con `active_sessions`).
- B6 después de B2, B3 y B5: los tres eventos ya existen. Antes de B6 los eventos se emiten sin suscriptores (no-ops).
- B7 requiere `bus_listo` en el conftest raíz y las fábricas (`tests/factories/`). Antes de B7 hay que ampliar `core/logging` (hecho en B3).
- B8 después de B7 (misma tabla). B9 independiente de B7 y B8 (pero después, por orden de migración).
- F1 y F2 no necesitan backend. F3 necesita el contrato de B2 (`LoginOut`, `RefreshOut`, `MeOut` de B3). F4a necesita B3 y B4; F4b necesita B5; F5 necesita B1; F6 necesita B7 y B8; F7 necesita B9. F8 va al final porque el catálogo incluye los componentes de F1 a F7.

Archivos compartidos que más de un slice toca (para no pisarse):
- `api/src/app/main.py`: `MODULES` crece en B1 (`settings`), B6 (`audit`), B7 (`members`), B9 (`plans`); quitar `refresh_keyring` en B2.
- `api/src/app/core/security.py`: B2 (`PASSWORD_MAX_LENGTH`, `Principal`, `refresh_current`) y B3 (`require_role` con `must_change_password`).
- `api/src/app/modules/auth/service.py`, `schemas.py`, `router.py`, `exceptions.py`: B2 a B5.
- `web/src/core/auth/session.ts` y `web/src/core/api/client.ts`: F3 y F4b; `web/src/routes.tsx`/`config/routeTable.ts`: F2 y todas las pantallas.

## 4. Wave 0 y backend

### S2-W0-1 · Infraestructura: red fija del proxy, Nginx, `.env.seed` y Playwright contra el stack

Cierra M-1, la parte de Nginx de M-3, L-1 y la parte de Compose de M-8. Incluye las tareas DevOps de US-068 (job de CI) y US-048 (token fuera del log).

Archivos a modificar:
- `infra/compose.yml`:
  - red por defecto con subred fija: `networks: default: ipam: config: [{subnet: 172.30.0.0/24}]`;
  - `web.networks.default.ipv4_address: 172.30.0.10`;
  - `tools.env_file: [../.env, {path: ../.env.seed, required: false}]` (el api y el worker no reciben `ADMIN_*`).
- `.env.example`: `TRUSTED_PROXIES=172.30.0.10` con el comentario "solo la IP de Nginx"; se quitan `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` (pasan a `.env.seed.example`); `CORS_ORIGINS` sigue vacío.
- `infra/nginx/default.conf`:
  - `limit_req_zone $binary_remote_addr zone=apex_auth:10m rate=30r/m;` y `limit_req_status 429;`;
  - `location /api/v1/auth/ { limit_req zone=apex_auth burst=10 nodelay; include snippets/proxy-api.conf; }` (más largo que `/api/`, gana el emparejamiento); el IPv6 /64 lo cubre el limitador de la app (la LAN de v0.1 es IPv4);
  - `error_page 429 = @rate_limited;` y un `location @rate_limited` con `default_type application/json`, `add_header Retry-After 60 always` y un `return 429` con el envelope `{"error":{"code":"rate_limited","message":"Demasiados intentos. Espera un momento."}}`, para que el front reciba el envelope también del 429 de Nginx;
  - `location ~ ^/restablecer/` con `access_log off`, `Referrer-Policy: no-referrer` (más el resto de cabeceras del snippet, porque un `add_header` en el location anula los del server) y `try_files $uri /index.html` (el token viaja en la ruta);
  - CSP del `index.html`: agregar `form-action 'self'` (L-1).
- `infra/nginx/snippets/proxy-api.conf`: `add_header Cache-Control "no-store" always;` (L-1) y la CSP del api con `form-action 'none'`.
- `scripts/ci/test_nginx_conf.sh` (26 comprobaciones hoy): agregar `limit_req` en `/api/v1/auth/`, 429 con envelope, `access_log off` en `/restablecer/`, `no-store` en `/api/`, `form-action` en las dos CSP, y que ningún `log_format` use `$request_uri` ni `$args`.
- `scripts/smoke/headers.sh` (19 comprobaciones hoy): agregar `Cache-Control: no-store` en `/api/v1/health`, `form-action` en la CSP del index y `Referrer-Policy: no-referrer` en `/restablecer/abc`.
- `scripts/ci/test_compose_config.sh`: afirmar que `TRUSTED_PROXIES` de `.env.example` es exactamente la IP `ipv4_address` de `web`, que cae dentro de la subred, y que `api` y `worker` no listan `.env.seed`.
- `.gitignore`: `.env.seed`. `scripts/ci/check-key-files.sh`: bloquear `.env.seed` y permitir `.env.seed.example`.
- `.github/workflows/ci.yml`: job nuevo `e2e-stack` (después de `images`): `cp .env.example .env`, `docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml up -d --build`, `tools init-keys`, `tools seed --no-force-change` con un `.env.seed` efímero generado en el job, `npx playwright install --with-deps chromium`, `E2E_BASE_URL=http://localhost:${WEB_PORT} npx playwright test --project=stack --pass-with-no-tests`, y subida de `web/test-results/captures/` como artefacto. El flag `--no-force-change` nace en B2; hasta entonces el paso del seed queda condicionado a que el comando exista.
- `web/playwright.config.ts`: dos proyectos. `preview` (lo de hoy: `vite preview`; specs `smoke`, `csp`, `panel-layout`, `layouts`, `kit`) y `stack` (sin `webServer`, `baseURL` de `E2E_BASE_URL`; specs `login`, `users-activation`, `role-guards`, `settings-gym`, `refresh-two-tabs`). Capturas en 320, 768, 1024 y 1440 px, en claro y oscuro, a `test-results/captures/<tema>-<ancho>.png`.
- `web/package.json`: script `e2e:stack`.

Archivos a crear:
- `.env.seed.example` (`ADMIN_EMAIL=admin@ejemplo.local`, `ADMIN_INITIAL_PASSWORD=cambiar-esto`, con la nota de borrar el archivo tras el primer `seed`).
- `web/tests/e2e/helpers/stack.ts`: `loginComo(page, rol)`, `crearCoach(page)`, `VIEWPORTS = [320, 768, 1024, 1440]`, `captura(page, nombre)`.

Gate: `bash -n scripts/ci/*.sh scripts/smoke/*.sh`, `bash scripts/ci/test_nginx_conf.sh`, `bash scripts/ci/test_compose_config.sh`, `bash scripts/ci/compose-smoke.sh` (api y web healthy y `headers.sh` en verde con las comprobaciones nuevas).

### S2-B1 · Configuración del gimnasio (US-054, US-055 back, US-057, US-058)

Además de `settings`, este slice crea la infraestructura de pruebas HTTP que usarán todos los routers autenticados (sección 9): `app_http`, `usuario_real`, `cliente`, `reloj`, `reset_rate_limit`, la promoción de `bus_listo` al conftest raíz y `tests/factories/{__init__,users}.py`. Va en el Rojo de B1 porque `test_settings_router.py` es el primer router autenticado del sprint.

Archivos a crear:
- `api/migrations/versions/0005_settings.py`:
  - `revision = "0005_settings"`, `down_revision = "0004_auth"`.
  - Tabla `settings.settings_sections`: columnas comunes (`id uuid pk`, `created_at`, `updated_at`, `created_by`), `key text not null`, `value jsonb not null`, `version integer not null default 0`, `updated_by uuid null`.
  - `CHECK key IN ('gym','hours','payment_methods','channels','classes','memberships','tv','privacy')` (nombre `key_valid`), `CHECK version >= 0` (nombre `version_non_negative`), índice único `uq_settings_sections_key (key)`.
  - Sin filas sembradas y sin FK hacia `auth.users`. `downgrade`: `drop_table` (el esquema lo crea y borra `0001`).
- `api/src/app/modules/settings/{__init__,models,schemas,exceptions,service,router}.py`.
- `api/tests/migrations/test_0005_settings.py`: columnas, CHECKs, índice único y `version` por defecto 0.
- `api/tests/settings/__init__.py` y los archivos de Rojo del plan (abajo).

`models.py`:
- `SettingsSection(CommonColumnsMixin, Base)`, `__tablename__ = "settings_sections"`, esquema `settings`, `__audited__ = True`.
- Columnas: `key: Mapped[str]` (Text), `value: Mapped[dict[str, Any]]` (`postgresql.JSONB`; en cada guardado se asigna un `dict` nuevo), `version: Mapped[int]` (default 0), `updated_by: Mapped[UUID | None]`.

`exceptions.py` (heredan de `DomainError`):
- `SettingsError` (base).
- `SectionNotAvailable`: 404, código `section_not_available`, sin `field`.
- `VersionConflict`: 409, `version_conflict`, mensaje "Otra persona cambió esta sección. Recarga para ver los cambios."
- `SettingsValidationError`: 422, `validation_error`, `field = "value.<ruta>"` (por ejemplo `value.name`, `value.email`), sin repetir el valor recibido.

`schemas.py`:
- `SectionKey(StrEnum)` con los 8 valores. `ENABLED_SECTIONS = frozenset({gym, privacy, memberships})`.
- `SectionValue(BaseModel)`: `ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)`.
- `GymSettings`: `name` (1 a 80), `nit: str | None` (patrón `^\d+(-\d)?$`, hasta 15), `address` (hasta 120), `city` (hasta 60), `phone` (hasta 20), `whatsapp` (hasta 20), `email: EmailAddress | None`. `name` no tiene valor por defecto en el modelo (vacío o ausente da 422); el `"APEX"` vive en `SECTION_DEFAULTS`.
- `PrivacySettings`: `policy_version` (1 a 20), `policy_text` (1 a 20.000), `retention_years` estricto 1 a 20 (5 por defecto), `consent_required_from: date | None = None`. `PrivacyView` (solo salida): igual, pero `policy_version` y `policy_text` pueden ser `None` (política nunca publicada).
- `MembershipsSettings`: cuatro `StrictInt`: `expiring_days` 1 a 30 (7), `max_freeze_days_per_membership` 0 a 180 (30), `max_freezes_per_membership` 0 a 12 (2), `max_retroactive_days` 0 a 30 (7). Un `7.5` o un `"7"` dan 422.
- `MembershipsPolicy`: `@dataclass(frozen=True)` con esos cuatro enteros; es el contrato que `memberships.service` importará desde `settings.schemas`.
- `SECTION_REGISTRY: dict[SectionKey, type[SectionValue]]` (solo las tres habilitadas) y `SECTION_DEFAULTS: dict[SectionKey, dict[str, Any]]`.
- Salidas: `SectionOut(key, value: dict[str, Any], version, updated_at: datetime | None, updated_by: UUID | None)` y las tipadas `GymSectionOut`, `PrivacySectionOut`, `MembershipsSectionOut`. Entradas: `SectionPatchIn(value: dict[str, Any], version: int = Field(ge=0))` y `GymPatchIn`, `PrivacyPatchIn`, `MembershipsPatchIn` (con `value` tipado), todas `extra="forbid"`.

`service.py` (las puras primero):
- `validate_section(key: SectionKey, value: Mapping[str, Any]) -> SectionValue`: arma `field = "value." + ".".join(map(str, loc))`.
- `check_version(stored: int, sent: int) -> None`; `defaults_for(key: SectionKey) -> dict[str, Any]`; `ensure_enabled(key: str) -> SectionKey` (clave desconocida o no habilitada: `SectionNotAvailable`).
- `async get_section(session, key: str) -> SectionOut`: la fila o los defaults con `version=0` y `updated_at=None`.
- `async update_section(session, key: str, value: Mapping[str, Any], version: int, by: UUID) -> SectionOut`: `ensure_enabled`, `validate_section` y `SELECT ... FOR UPDATE` por `key`.
  - Sin fila: exige `version == 0` e inserta con `version=1` dentro de `session.begin_nested()`; un `IntegrityError` del índice único se traduce a `VersionConflict`.
  - Con fila: `check_version`, asigna un `dict` nuevo (`model_dump(mode="json")`), `version += 1`, `updated_by = by`, `flush`.
  - El hook audita `insert` en el primer guardado y `update` desde el segundo.
- `async get(session, key: SectionKey) -> SectionValue` (modelo validado con defaults, para consumidores), `async memberships_policy(session) -> MembershipsPolicy`, `async current_privacy_version(session) -> str | None`, `async gym_name(session) -> str` (respaldo `"APEX"`).
- El log del service registra solo `key` y `version`.

`router.py` (plano, todas con `require_role("admin")`; el orden de declaración importa):
- `GET` y `PATCH` de `/settings/gym`, `/settings/privacy`, `/settings/memberships` (tipadas).
- Después `GET` y `PATCH` de `/settings/{section}` (genéricas).
- Códigos: 200, 401, 403, 404, 409, 422.

`main.py`: `MODULES = ("auth", "settings")`.

Rojo (plano): `tests/settings/test_settings_rules.py`, `test_settings_service.py`, `test_settings_router.py`, `test_gym_schema.py`, `test_gym_router.py`, `test_privacy_schema.py`, `test_privacy_service.py`, `test_privacy_router.py`, `test_memberships_policy.py`, `test_memberships_schema.py`, `test_memberships_router.py`, `tests/architecture/test_settings_no_secrets.py`, más `tests/migrations/test_0005_settings.py`.

Casos que no hay que olvidar:
- Dos primeros guardados concurrentes con `version=0` dejan una sola fila y uno recibe `version_conflict`.
- Un valor inválido no cambia la fila ni crea auditoría.
- El coach recibe 403 en las ocho rutas.
- `/settings/tv`, `/hours`, `/channels`, `/classes` y `/payment_methods` dan 404 `section_not_available`.
- `max_freeze_days_per_membership = 0` es válido y `181` da 422 con `field = "value.max_freeze_days_per_membership"`.
- `current_privacy_version` es `None` sin fila y `"2026-10"` después.
- `MembershipsPolicy` es inmutable.

Gate: `bash scripts/workflow/slice-gate.sh settings <archivos de Rojo>`, ciclo de Alembic y `export-openapi`.

### S2-B2 · Sesión: login, refresh y logout (US-042, US-043, US-044)

Cierra M-2, M-3 (keyring), L-4, L-5 y L-8, y la parte de código de M-8. Es el slice más ancho del sprint porque deja todo lo común de sesión.

Migración nueva `api/migrations/versions/0005b_auth_security.py` (`down_revision = "0005_settings"`):
- `auth.users.must_change_password boolean NOT NULL DEFAULT false`.
- `auth.users.failed_login_count integer NOT NULL DEFAULT 0` con `CHECK (failed_login_count >= 0)` (nombre `failed_login_count_non_negative`).
- `downgrade`: quita el CHECK y las dos columnas. `0004` no se toca. Prueba: `tests/migrations/test_0005b_auth_security.py`.
- `0006_members` (B7) apunta a esta revisión como padre.

`core/` (cada archivo con su prueba en `tests/core/`, gate `core/<archivo>`):
- `core/validators.py` (nuevo): `EmailAddress` (decisión 5). Prueba `test_validators.py`: espacios y mayúsculas, sin arroba, sin punto en el dominio, 255 caracteres.
- `core/security.py`:
  - `PASSWORD_MAX_LENGTH: Final = 128`; `WeakReason` suma `"too_long"`; `validate_password_policy` revisa `too_long`, luego `too_short`, luego `too_common`.
  - `Principal` gana `must_change_password: bool = False` (el cargador real lo llena; `Principal(id, "member", socio)` de la prueba existente sigue igual).
  - `current_user`: después de que el cargador devuelva el principal, `await refresh_current(session)` (decisión 11).
- `core/crypto/keyring.py`: `async def refresh_current(session) -> None`: si no hay keyring cargado no hace nada; si lo hay, `refresh_if_stale(session, provider)`.
- `core/ratelimit.py`:
  - `ip_bucket_key(ip: str) -> str`: IPv4 igual; IPv6 devuelve la dirección de red de `ip/64`. La dependencia `rate_limit` usa esa clave y sigue registrando la IP completa en el log.
  - `async def enforce(bucket: str, key: str, *, limit: int, window_s: int, max_keys: int = DEFAULT_MAX_KEYS, log_key: bool = False) -> None`: una sola función para el límite por clave arbitraria (la usa el límite por cuenta); lanza `TooManyRequestsError`. Con `log_key=False` el log guarda solo el bucket (nunca el correo).
  - `rate_limit(bucket)` se reescribe sobre `enforce`; sin cambio de comportamiento para login y forgot (5 por 60 s por IP).
- `core/config.py`:
  - Quitar `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` de `Settings`; agregarlos a `NON_API_ENV_VARS`.
  - Clase nueva `SeedSettings(BaseSettings)`: `ADMIN_EMAIL: str | None`, `ADMIN_INITIAL_PASSWORD: SecretStr | None`, `extra="forbid"`, `env_file=".env.seed"` (si el archivo no existe lee el entorno).
  - `Settings` suma `LOGIN_ACCOUNT_LIMIT: int = 10`, `LOGIN_ACCOUNT_WINDOW_S: int = 900`, `LOGIN_LOCK_AFTER: int = 20` (todos `gt=0`), documentados en `.env.example`.
- `main.py`: quitar `refresh_keyring` y la dependencia de `include_module_routers`; en el lifespan, `logger.warning` si `ENV=production` y `COOKIE_SECURE=false`; `MODULES` no cambia.
- `core/logging.py`: sin cambios en este slice (los patrones nuevos van en B3).

`modules/auth/` (archivos nuevos `rules.py`, `tokens.py`, `cookies.py`; modificados `models.py`, `schemas.py`, `exceptions.py`, `service.py`, `router.py`):
- `models.py`: `User.must_change_password: Mapped[bool]` y `User.failed_login_count: Mapped[int]`; `__audit_exclude__ = {"last_login_at", "failed_login_count"}`.
- `exceptions.py`: `InvalidCredentials` (401, `invalid_credentials`, "Correo o contraseña incorrectos.") e `InvalidRefresh` (401, `invalid_refresh`, "La sesión ya no es válida. Inicia sesión de nuevo."). Ambos heredan de `DomainError`.
- `schemas.py`:
  - `UserSummary(id, email, role)`.
  - `LoginIn(email: EmailAddress, password: SecretStr)` con `min_length=1`, `max_length=128`, `extra="forbid"`.
  - `LoginOut(access_token, token_type: Literal["bearer"], expires_in: int, user: UserSummary, must_change_password: bool)`.
  - `RefreshOut(access_token, token_type, expires_in)`.
  - `UserStatus` pasa a cinco valores (decisión 1).
- `rules.py` (puras): `user_status` (orden de la decisión 1), `can_login(user)`, `is_active_admin`, `is_refresh_usable(token, user, now)`, `is_reuse(token)`, `should_auto_lock(failed_count, lock_after, *, is_last_admin)`, `AuthPolicy` (dataclass congelada con `refresh_ttl: timedelta`, `account_limit`, `account_window_s`, `lock_after`).
- `tokens.py`: `async revoke_all(session, user_id, *, now, except_id=None) -> int` (un `UPDATE ... WHERE user_id = :u AND revoked_at IS NULL AND expires_at > :now [AND id <> :except]`, devuelve `rowcount`).
- `cookies.py` (L-8):
  - constantes `REFRESH_COOKIE = "apex_refresh"` y `REFRESH_COOKIE_PATH = "/api/v1/auth"`.
  - `set_refresh_cookie(response, token, settings)`: `httponly=True`, `samesite="strict"`, `path=REFRESH_COOKIE_PATH`, `secure=settings.COOKIE_SECURE`, `max_age=settings.REFRESH_TOKEN_TTL_DAYS * 86400`.
  - `clear_refresh_cookie(response, settings)`; `clear_cookie_header(settings) -> str` (para adjuntarlo a una excepción); `read_refresh_cookie(request) -> str | None`.
  - `policy_from(settings) -> AuthPolicy`.
  - `async no_store(response: Response) -> None`: dependencia que fija `Cache-Control: no-store`; todas las rutas de `auth` y `users` la llevan.
- `service.py`:
  - Eventos nuevos: `LoginAttempted(user_id: UUID, result: Literal["ok","failed"], reason: Literal["bad_password","locked","inactive","pending"] | None = None)`, `SessionsRevoked(user_id, by, revoked: int, reason: Literal["admin","lock","delete","refresh_reuse","password_changed","password_reset"])` y `UserLocked(user_id, by, reason: Literal["admin","too_many_failures"])` (el bloqueo automático lo emite aquí; B5 lo reutiliza). `UserCreated` ya existe.
  - Resultados: `LoginResult(access_token, expires_in, refresh_token, user, must_change_password)` y `RefreshResult(access_token, expires_in, refresh_token)` (dataclasses congeladas; el refresh en claro solo sirve para la cookie).
  - `async login(session, email, password, *, user_agent, policy) -> LoginResult` (ver sección 7.1).
  - `async refresh(session, token, *, user_agent, policy) -> RefreshResult` (sección 7.1).
  - `async logout(session, user_id, token) -> None`: `UPDATE ... SET revoked_at = now WHERE token_hash = :h AND user_id = :u AND revoked_at IS NULL`; sin token no hace nada; un token ajeno no se toca y la respuesta sigue siendo 204. No deja `replaced_by_id`, así un `refresh` posterior con ese token no es reuso.
  - `seed_admin(..., force_change: bool = True)` pone `must_change_password=force_change`. `active_admin_id_by_email` pasa a `active_user_id_by_email` (L-4).
  - `load_active_principal` devuelve `Principal(..., must_change_password=usuario.must_change_password)`.
- `router.py` (plano): `POST /auth/login` (`rate_limit("login")`, 200), `POST /auth/refresh` (público, 200), `POST /auth/logout` (`require_role("admin","coach","member")`, 204). Detalles:
  - login y refresh llaman a `set_refresh_cookie`; el cuerpo nunca trae el refresh.
  - refresh captura `InvalidRefresh`, le agrega `headers["Set-Cookie"] = clear_cookie_header(settings)` y la vuelve a lanzar (la cookie se borra en el 401).
  - logout lee la cookie, llama al service y siempre la borra.
- `cli.py`: `seed` lee `SeedSettings`, acepta `--no-force-change` (solo con `ENV=dev`, si no sale con 2), `resolve_actor` usa `active_user_id_by_email`; mensaje explícito si el correo es de una cuenta inactiva o bloqueada.

Rojo de B2 (nombres del plan y adiciones):
- `tests/auth/test_pure_login.py`: `can_login` con activo, bloqueado, `is_active=false`, borrado, sin hash y el técnico; `should_auto_lock` (umbral y excepción del último admin).
- `tests/auth/test_login_service.py` (con `FrozenClock`):
  - login correcto deja una fila en `refresh_tokens` con `token_hash` distinto del token y `expires_at` a 7 días, `last_login_at` en ahora, `failed_login_count` en 0 y un solo `LoginAttempted("ok")`;
  - contraseña errada emite `LoginAttempted("failed")`, suma 1 a `failed_login_count` y el efecto sobrevive al 401: tras `InvalidCredentials` se hace `await session.rollback()` (lo que haría `get_session`) y la cuenta sigue en 1;
  - correo inexistente, correo del usuario técnico y cuenta borrada no emiten eventos y llaman a `dummy_verify` (espía);
  - bloqueado, inactivo y pendiente de activación dan el mismo `InvalidCredentials`;
  - un hash con parámetros viejos se rehace;
  - 10 intentos en 900 s sobre el mismo correo (existente o no) dan `TooManyRequestsError` en el undécimo sin llamar a argon2;
  - 20 fallos consecutivos bloquean (`locked_at`), emiten `UserLocked(by=SYSTEM_USER_ID, reason="too_many_failures")` y `SessionsRevoked`; el último admin activo no se bloquea.
- `tests/auth/test_login_router.py`:
  - las cinco causas de rechazo dan el mismo cuerpo y código 401;
  - `email` mal formado o ausente: 422 con `field`; contraseña de 129 caracteres: 422 con `field = "password"`;
  - el sexto intento por IP en 60 s: 429 sin llamar al service;
  - `Set-Cookie` con `HttpOnly`, `SameSite=Strict`, `Path=/api/v1/auth`, `Max-Age=604800`, y `Secure` solo con `COOKIE_SECURE=true`;
  - el cuerpo no contiene el refresh; `" Coach@Apex.co "` entra; cabecera `Cache-Control: no-store`;
  - dos IPv6 del mismo /64 comparten bucket.
- `tests/auth/test_pure_refresh.py`, `test_refresh_service.py`, `test_refresh_router.py`:
  - la rotación deja el anterior con `revoked_at` y `replaced_by_id` en la misma transacción;
  - reusar el rotado revoca los tres vigentes, emite `SessionsRevoked(revoked=3, reason="refresh_reuse")` y el efecto queda tras el 401 (commit explícito);
  - dos `refresh` concurrentes con el mismo token (dos sesiones, `asyncio.gather`) terminan en una rotación y un reuso;
  - token de usuario bloqueado, vencido o inexistente: `InvalidRefresh`, y el 401 trae `Set-Cookie` que borra la cookie;
  - sin cookie: 401 `invalid_refresh`; el cuerpo se ignora;
  - ruta protegida con access vencido (reloj adelantado 16 min): 401 `token_expired`; firma inválida: 401 `unauthorized`.
- `tests/auth/test_logout_service.py`, `test_logout_router.py`: logout revoca solo la sesión de la cookie; el refresh posterior da `InvalidRefresh` y no es reuso; un token de otro usuario no se revoca; 204 con y sin cookie; sin access: 401.
- Core y CLI: `tests/core/test_ratelimit.py` (clave /64, `enforce` sin correo en el log), `tests/core/test_passwords.py` (`too_long` en 129), `tests/core/test_require_role.py` (`refresh_current` solo se llama tras un token válido; login no abre keyring), `tests/core/test_config.py` y `test_env_example.py` (sin `ADMIN_*`, con las tres variables nuevas), `tests/cli/test_seed_cli.py` (`SeedSettings`, `--no-force-change` rechazado fuera de `dev`, `must_change_password` en el admin sembrado, `--as` con cuenta inactiva o `system@apex.local` sale con 2).

Gate: `bash scripts/workflow/slice-gate.sh auth <archivos de Rojo de auth>`, `slice-gate.sh core/ratelimit tests/core/test_ratelimit.py`, `slice-gate.sh core/security tests/core/test_passwords.py tests/core/test_require_role.py`, `slice-gate.sh core/config tests/core/test_config.py tests/core/test_env_example.py`, `slice-gate.sh core/validators tests/core/test_validators.py`, `slice-gate.sh cli tests/cli/test_seed_cli.py`, ciclo de Alembic y `export-openapi`.

### S2-B3 · Mi cuenta y usuarios (US-045, US-046, US-047)

Archivos nuevos o modificados:
- `core/security.py`: `require_role(*roles, allow_pending_password: bool = False)`. Si `principal.must_change_password` y la ruta no es de las exentas, lanza `ForbiddenError("password_change_required")` (403, "Debes cambiar tu contraseña para continuar."). Exentas: `GET /auth/me`, `POST /auth/me/password` y `POST /auth/logout` (`refresh` es pública). La marca `__apex_roles__` no cambia, así `test_every_route_has_role` sigue en pie. Prueba en `tests/core/test_require_role.py`.
- `core/logging.py`: patrones de la regla 7 de la sección 2 (token en la ruta `/restablecer/`, cookie, claves `activation_url`, `url`, `set-cookie`). Prueba en `tests/core/test_logging_redact.py`.
- `auth/rules.py`: `validate_password_policy(password, *, current_hash=None, field="password")` (el campo es `new_password` en cambio y reset), `activation_url(base_url, token)`, constantes `ACTIVATE_TTL = timedelta(hours=72)` y `RESET_TTL = timedelta(hours=1)`.
- `auth/tokens.py`: `async issue_one_time_token(session, user_id, purpose, *, now) -> tuple[str, OneTimeToken]`. Pone `used_at = now` en los tokens abiertos del mismo usuario y propósito (por ORM, así queda `update` auditado), crea el nuevo con `expires_at = now + TTL` y devuelve el token en claro (nunca se guarda ni se loguea).
- `auth/exceptions.py`: `EmailTaken` (409, `email_taken`, `field="email"`, `existing_id`), `InvalidCurrentPassword` (422, `invalid_current_password`, `field="current_password"`).
- `auth/schemas.py`:
  - `MeOut(id, email, role, member_id, gym_name, must_change_password)`.
  - `ChangePasswordIn(current_password: SecretStr, new_password: SecretStr)` con `max_length=128`.
  - `UserRow(id, email, role, status, member_id, last_login_at, created_at, active_sessions)`; `active_sessions` entra aquí para no cambiar el esquema en B5.
  - `CreateUserIn(email: EmailAddress, role: Role, member_id: UUID | None = None)` y `CreateUserOut(user: UserOut, activation_url: str, expires_at: datetime)`.
  - `UserOut` suma `must_change_password`.
- `auth/service.py`:
  - Evento `PasswordChanged(user_id, by, via: Literal["change","activate","reset"])`.
  - `async me(session, principal) -> MeOut` (decisión 14).
  - `async change_password(session, user_id, current_password, new_password, *, current_refresh: str | None) -> None`: verifica la actual (`InvalidCurrentPassword`); aplica la política con `current_hash` (la nueva debe diferir de la actual); guarda el hash; pone `must_change_password=False` y `failed_login_count=0`; llama a `revoke_all(user_id, except_id=<id del refresh de la cookie>)` (sin cookie revoca todo); emite `PasswordChanged(via="change")` y, si revocó alguna, `SessionsRevoked(reason="password_changed")`.
  - `async list_users(session, *, q, role, status, page: PageParams) -> Page[UserRow]`: excluye `SYSTEM_USER_ID`; sin `status` aplica `deleted_at IS NULL`; `q` con `ILIKE` escapando `%`, `_` y `\`; orden `email ASC`; `active_sessions` con un `LEFT JOIN` a la subconsulta agregada de `refresh_tokens` (`revoked_at IS NULL AND expires_at > now`) y `coalesce(..., 0)`. `status_filter(status)` es el espejo SQL de `user_status`.
  - `async create_user(session, *, email, role, member_id, by) -> CreatedUser`: `validate_user_role`, normaliza el correo, busca un no borrado con ese correo (si existe, `EmailTaken(existing_id)`), crea el `User` sin hash, emite el token `activate`, emite `UserCreated`. Un `IntegrityError` de `uq_users_email_alive` (carrera) se atrapa con `begin_nested()` y se traduce a `EmailTaken`. Sin parámetro `notify` en v0.1.
- `auth/router.py` (mismo router plano):
  - `GET /auth/me` y `POST /auth/me/password` con los tres roles y `allow_pending_password=True`; el segundo lee la cookie `apex_refresh` (el `Path=/api/v1/auth` la cubre) y responde 204.
  - `GET /users` (admin, `PageParams`, filtros `q`, `role`, `status`) y `POST /users` (admin, 201).

Rojo: `tests/auth/test_pure_password_policy.py`, `test_change_password.py`, `test_me_router.py`, `test_pure_user_status.py`, `test_list_users.py`, `test_users_list_router.py`, `test_pure_links.py`, `test_create_user.py`, `test_create_user_router.py`.

Casos clave:
- Cambiar contraseña deja viva solo la sesión de la cookie, con auditoría `update` sobre `auth.users` y `password_hash = "***"` en `before` y `after`; una nueva de 11 caracteres, igual a la actual o de 129 no cambia nada y da 422 con el `field` correcto.
- Con `must_change_password=true`, `GET /users` da 403 `password_change_required` y `GET /auth/me` da 200.
- La lista no incluye al técnico, respeta el orden por correo, `q="_"` va escapado, `limit=500` da 422 con `field="limit"`, no trae `password_hash` ni tokens, y el coach recibe 403.
- Crear usuario: `password_hash` nulo, `user_status == "pending_activation"`, token `activate` a 72 h guardado como hash, dos filas `insert` en `audit.audit_log` (`auth.users` y `auth.one_time_tokens`) sin el token en claro, 409 con `existing_id` (y se permite si el anterior está borrado), 422 para `member` sin `member_id`, y el log capturado no contiene el token ni la URL.

Gate: `slice-gate.sh auth <archivos de Rojo de B3>`, `slice-gate.sh core/security tests/core/test_require_role.py`, `slice-gate.sh core/logging tests/core/test_logging_redact.py`, `export-openapi`.

### S2-B4 · Activación, recuperación y reenvío (US-048, US-052)

Archivos nuevos o modificados (dentro de `modules/auth/`, salvo la prueba de arquitectura):
- `rules.py`: `is_one_time_token_usable(token, user, now)` (sin usar, `expires_at > now`, usuario no bloqueado, no borrado y con `is_active`) y `link_purpose_for(user)` (`activate` si no tiene hash, si no `reset`).
- `tokens.py`: `async get_alive_or_404(session, user_id, *, include_deleted=False) -> User` (el usuario técnico y los inexistentes dan `UserNotFound`; con `include_deleted=True` devuelve también los borrados).
- `exceptions.py`: `InvalidToken` (400, `invalid_token`, "El enlace ya no es válido. Pide uno nuevo al administrador."; mismo texto para token inexistente, usado, vencido o de usuario bloqueado), `UserNotEligible` (409, `user_not_eligible`) y `UserNotFound` (404, `user_not_found`).
- `schemas.py`: `ResetIn(token: str de 20 a 200 caracteres, new_password: SecretStr hasta 128)`, `ForgotIn(email: EmailAddress)` e `IssuedLinkOut(url, purpose: Literal["activate","reset"], expires_at)`; todos `extra="forbid"`.
- `service.py`:
  - `async reset(session, token: str, new_password: str) -> None`, en este orden (decisión 7):
    1. `hash_opaque_token(token)` y `SELECT ... FOR UPDATE` del `OneTimeToken` con su usuario; si no existe o no es usable: `InvalidToken` (400);
    2. política de contraseña con `field="new_password"` (422; el token queda sin usar porque la transacción se revierte);
    3. dentro de `actor_scope(token.user_id)`: `used_at = now`, `password_hash`, `must_change_password = False`, `failed_login_count = 0` y `flush`;
    4. si el propósito es `reset`: `revoke_all(user_id)` y, si revocó alguna, `SessionsRevoked(reason="password_reset", by=user_id)`;
    5. `PasswordChanged(via=purpose)`.
  - `reset` no inicia sesión (decisión 18). La auditoría deja `update` sobre `auth.users` (`password_hash = "***"`) y sobre `auth.one_time_tokens` (`used_at`, `token_hash = "***"`).
  - `async forgot(session, email: str) -> None`: normaliza; si el usuario existe y `user_status == "active"` con hash, emite un token `reset` (invalida los `reset` abiertos) bajo `actor_scope(SYSTEM_USER_ID)` y descarta el token en claro (v0.1 no tiene canal; US-131 lo enviará). Nunca lanza por un correo inexistente.
  - `async resend_link(session, user_id, *, by) -> IssuedLink`: `get_alive_or_404(include_deleted=True)`; `locked` o `deleted` dan `UserNotEligible`; `purpose = link_purpose_for(user)`; `issue_one_time_token`; devuelve `url` (`<FRONT_BASE_URL>/restablecer/<token>`), `purpose` y `expires_at`. El enlace solo viaja en esta respuesta.
- `router.py`: `POST /auth/forgot` (`rate_limit("forgot")`, 204, mismo cuerpo vacío exista o no la cuenta), `POST /auth/reset` (público, 204) y `POST /users/{id}/resend-link` (admin, 200 `IssuedLinkOut`). `GET /users/{id}/activation-link` no existe (N-12).

Rojo: `tests/auth/test_pure_one_time_token.py` (límite exacto de `expires_at`), `test_reset_forgot.py`, `test_reset_forgot_router.py`, `test_resend_link.py`, `test_resend_link_router.py` y `tests/architecture/test_auth_routes.py`.

Casos clave:
- Activar deja el usuario `active` y el login funciona; un segundo uso da `InvalidToken` y el hash no cambia; una contraseña corta da 422 y el token sigue sin usar; `reset` con dos sesiones abiertas las revoca; un token vencido (más de 1 h) se rechaza; dos `reset` concurrentes con el mismo token (`asyncio.gather`) dan exactamente un éxito.
- `forgot` con correo inexistente no crea filas; repetido deja un solo `reset` abierto; con usuario bloqueado o pendiente no crea nada; los cuerpos son idénticos; el sexto por IP da 429; funciona sin `Authorization`.
- `resend_link`: un pendiente con enlace vencido recibe `activate` a 72 h; un activo que pidió `forgot` recibe `reset` a 1 h e invalida el de `forgot`; el token anterior da `InvalidToken` en `reset`; bloqueado o borrado: 409; el técnico: 404; la auditoría deja `insert` y `update` de `auth.one_time_tokens` hechos por el admin y sin el token.
- Ni la auditoría, ni los logs capturados, ni la respuesta de `forgot` contienen el token.

`tests/architecture/test_auth_routes.py` (nace aquí):
- Ninguna ruta termina en `/activation-link`.
- `/auth/login` y `/auth/forgot` llevan la marca `__apex_rate_limit__`.
- Toda ruta bajo `/users` exige exactamente `{"admin"}` (marca `__apex_roles__`).
- `/auth/logout`, `/auth/me` y `/auth/me/password` aceptan los tres roles.
- Las rutas públicas de `auth` son exactamente `login`, `refresh`, `forgot` y `reset`.

Gate: `slice-gate.sh auth <archivos de Rojo de B4>` y `export-openapi`.

### S2-B5 · Ciclo de vida del usuario (US-049, US-050, US-051)

Archivos nuevos o modificados:
- `rules.py`: `would_remove_last_admin(active_admin_ids: frozenset[UUID], target_id: UUID, *, new_role: Role | None, deleting: bool) -> bool` y `lock_precondition(user, by_id, *, is_last_admin) -> None` (orden fijo de errores: `CannotLockSelf`, `AlreadyLocked`, `LastAdmin`).
- `tokens.py`: `async lock_active_admins(session) -> frozenset[UUID]`: `SELECT id` de los admins activos (rol admin, `is_active`, sin `locked_at`, sin `deleted_at`, con hash, distintos de `SYSTEM_USER_ID`) `ORDER BY id FOR UPDATE`, para serializar bajas, cambios de rol y bloqueos.
- `exceptions.py`: `LastAdmin` (409, `last_admin`), `CannotLockSelf` (409, `cannot_lock_self`), `AlreadyLocked` (409, `already_locked`), `NotLocked` (409, `not_locked`).
- `schemas.py`: `UpdateUserIn(email: EmailAddress | None, role: Role | None)` con `extra="forbid"` y `RevokeSessionsOut(revoked: int)`.
- `service.py` (el evento `UserLocked(user_id, by, reason: Literal["admin","too_many_failures"])` ya nace en B2 por el bloqueo automático):
  - `async get_user(session, user_id) -> User`: incluye borrados; el técnico da 404.
  - `async update_user(session, user_id, *, email, role, by) -> User`: 404 si está borrado; correo normalizado y único entre no borrados (`EmailTaken` con `existing_id`; la carrera se atrapa con `begin_nested()`); si cambia el rol, `validate_user_role` con el `member_id` actual y `would_remove_last_admin` (`LastAdmin`).
  - `async delete_user(session, user_id, *, by) -> None`: baja lógica (`deleted_at = now`, sin `session.delete`); `LastAdmin` si corresponde; `revoke_all` en la misma transacción y `SessionsRevoked(reason="delete", revoked=n)`.
  - `async lock(session, user_id, *, by) -> User`: `get_alive_or_404`, `lock_active_admins`, `lock_precondition`, `locked_at = now`, `revoke_all`, y emite `UserLocked(reason="admin")` y `SessionsRevoked(reason="lock")`. Todo en una transacción: si un handler falla no queda nada aplicado.
  - `async unlock(session, user_id, *, by) -> User`: `NotLocked` si no está bloqueado; `locked_at = None` y `failed_login_count = 0`; las sesiones siguen revocadas; sin eventos de dominio (el hook deja el `update`).
  - `async revoke_sessions(session, user_id, *, by) -> int`: emite `SessionsRevoked(reason="admin", revoked=n)` también con `n = 0`; no bloquea al usuario.
  - `list_users` ya trae `active_sessions` desde B3.
- `router.py`: `GET /users/{id}` (200), `PATCH /users/{id}` (200), `DELETE /users/{id}` (204), `POST /users/{id}/lock` y `/unlock` (200 `UserOut`) y `POST /users/{id}/revoke-sessions` (200 `RevokeSessionsOut`); todas con `require_role("admin")`.
- `cli.py`: `unlock-user <correo> [--as <correo>]`, que llama a `unlock` y deja la fila `update` auditada.

Rojo: `tests/auth/test_pure_last_admin.py`, `test_update_delete_user.py`, `test_user_detail_router.py`, `test_pure_lock.py`, `test_lock_unlock.py`, `test_lock_router.py`, `test_revoke_sessions.py`, `test_revoke_sessions_router.py` y `tests/cli/test_unlock_cli.py`.

Casos clave:
- Dos `delete_user` concurrentes sobre los dos únicos admins terminan con uno solo dado de baja.
- El técnico no cuenta como último admin y responde 404 en todas las rutas.
- Un correo liberado por la baja se puede reutilizar.
- Bloquear surte efecto en la siguiente petición: un access emitido antes recibe 401 en `GET /auth/me` (el cargador lee la base).
- Un cambio de rol surte efecto inmediato con un token emitido antes.
- Un admin que cierra sus propias sesiones deja su refresh revocado y `refresh` da 401.
- Si un handler de `UserLocked` falla (doble que lanza), no queda `locked_at` ni sesiones revocadas.

Gate: `slice-gate.sh auth <archivos de Rojo de B5>`, `slice-gate.sh cli tests/cli/test_unlock_cli.py` y `export-openapi`.

### S2-B6 · Auditoría de eventos de seguridad (US-107)

**DECISIÓN 31 · El test de `reveal` no usa un socio de fábrica.** El plan dice "con un socio de fábrica", pero la tabla de socios nace en B7 (después de B6). `audit_log` no tiene llave foránea hacia socios, así que `test_reveal_entry.py` usa un `uuid4()` como `record_id` y `subject_member_id`; sigue sin `skip` (M-4). Cuando US-074 cree el endpoint (Sprint 3) la prueba se repunta a la fábrica de `tests/factories/members.py`.

Archivos a crear:
- `api/src/app/modules/audit/{__init__,router,service}.py`. `router.py` es un `APIRouter()` vacío (decisión 21).
- `modules/audit/service.py`:
  - `async on_login_attempted(event, session)`: `core.audit.record(session, action="login", table_name="auth.users", record_id=event.user_id, before=None, after={"result": ..., "reason": ...}, user_id=event.user_id)`.
  - `async on_user_locked(event, session)`: `action="update"`, `table_name="auth.users"`, `record_id=event.user_id`, `after={"event": "UserLocked", "reason": event.reason}`, `user_id=event.by`.
  - `async on_sessions_revoked(event, session)`: igual, `after={"event": "SessionsRevoked", "reason": ..., "revoked": n}`.
  - Se registran con `events.subscribe` al importar el módulo. `audit` importa de `auth.service` solo las clases de evento; `auth` no importa nada de `audit`. Los handlers corren en la transacción del emisor: si fallan, el bloqueo o la revocación se revierten.
  - `after` solo lleva `result`, `reason`, `event`, `revoked`; nunca correos tecleados, contraseñas, hashes ni tokens.

Archivos a modificar:
- `main.py`: `MODULES = ("auth", "settings", "audit")`.
- `cli.py`: los comandos que escriben tablas auditadas llaman a `load_module_services()` (import perezoso de `app.main`) para que los handlers existan en el proceso del CLI; el worker hará lo mismo en el Sprint 4A.
- `tests/architecture/test_audited_tables.py`: `_cargar_modelos()` importa `models` solo si `find_spec` lo encuentra; nueva constante `REQUIRED_AUDITED_TABLES_V01 = {"auth.users", "auth.one_time_tokens", "settings.settings_sections"}` más `PENDING_AUDITED = {"members.members": "B7", "plans.plans": "B9", "memberships.memberships": "Sprint 3", "payments.payments": "Sprint 3"}`. Una tabla de `PENDING_AUDITED` que ya exista y no tenga `__audited__ = True` falla; una que no exista no falla. B7 y B9 mueven su entrada a `REQUIRED_AUDITED_TABLES_V01`.

Rojo: `tests/audit/__init__.py`, `tests/audit/test_security_events.py`, `tests/auth/test_router_login_audit.py`, `tests/audit/test_reveal_entry.py`.

Casos clave:
- Login correcto deja una entrada `login` con `result = ok`; el fallido de un correo existente deja `result = failed` aunque la petición responda 401 y su transacción se revierta; el de un correo inexistente no deja nada (N-31).
- Cinco logins fallidos dejan cinco entradas y el sexto da 429 (la auditoría no cuenta intentos).
- `UserLocked` y `SessionsRevoked` dejan su entrada con el admin como `user_id` y el afectado como `record_id`; el reuso de refresh deja `SessionsRevoked` con `SYSTEM_USER_ID`; el bloqueo automático deja `UserLocked` con `reason = "too_many_failures"`.
- Ninguna entrada contiene la contraseña tecleada ni el hash (búsqueda en `before` y `after` serializados).
- Un handler que falla revierte el bloqueo; la cadena sigue íntegra (`verify_chain`) tras todos los eventos.
- `test_reveal_entry.py`: `record(action="reveal", table_name="members.members", after={"field": "document"}, subject_member_id=...)` deja exactamente una entrada sin el valor revelado.

Gate: `slice-gate.sh audit tests/audit/test_security_events.py tests/auth/test_router_login_audit.py tests/audit/test_reveal_entry.py`.

### S2-B7 · Registrar socio y pruebas de cifrado en reposo (US-069, US-031)

Trampa a tener presente en B7, B9 y B1: después de un `flush`, las columnas con `server_default` (`created_at`) o `onupdate` (`updated_at`) quedan sin cargar y leerlas en un contexto async lanza `MissingGreenlet`. Antes de armar una respuesta se hace `await session.refresh(obj, attribute_names=["created_at", "updated_at"])`.

Archivos a crear:
- `api/migrations/versions/0006_members.py` (`down_revision = "0005b_auth_security"`), tabla `members.members`:
  - columnas comunes (`id`, `created_at`, `updated_at`, `created_by`) y `deleted_at`;
  - en claro: `first_name`, `last_name` (text, no nulos), `sex` (nulo), `status` (default `'active'`), `notes` (nulo), `document_type` (default `'CC'`, decisión 16), `data_consent_at` (timestamptz, nulo), `data_consent_version` (nulo);
  - cifradas, todas `text`: `document` (no nulo), `phone`, `email`, `birth_date`, `emergency_contact` (nulas);
  - índices ciegos: `document_idx` (no nulo), `phone_idx`, `email_idx` (nulos);
  - CHECKs: `sex IN ('f','m','x')`, `status IN ('active','inactive')`, `document_type IN ('CC','CE','TI','PA')`, nombres no vacíos (`btrim(...) <> ''`), cada blob `LIKE 'apx1.%'` cuando no es nulo, `(phone IS NULL) = (phone_idx IS NULL)` y el par de `email`;
  - índice único parcial `uq_members_document_idx_alive ON (document_idx) WHERE deleted_at IS NULL`; índices `ix_members_phone_idx`, `ix_members_email_idx` y `ix_members_alive_last_name (last_name, first_name) WHERE deleted_at IS NULL`;
  - sin columnas `*_hint`. `downgrade`: `drop_table`.
- `api/tests/migrations/test_0006_members.py`: columnas, CHECKs (blob en claro rechazado), único parcial (un dado de baja libera el documento), ausencia de `*_hint`.
- `api/src/app/modules/members/{__init__,models,schemas,exceptions,service,router}.py`.
- `api/tests/factories/members.py` y `tests/members/__init__.py`.

`models.py`: `Member(CommonColumnsMixin, SoftDeleteMixin, Base)`, esquema `members`, `__audited__ = True`, `__audit_subject__ = "id"` (llena `subject_member_id`). Columnas cifradas como `Mapped[Secret]` o `Mapped[Secret | None]` con `Encrypted("member.document")`, `Encrypted("member.phone")`, `Encrypted("member.email")`, `Encrypted("member.birth_date")`, `Encrypted("member.emergency_contact")`; índices con `BlindIndexed("member.document", source="document")`, `BlindIndexed("member.phone", source="phone")` y `BlindIndexed("member.email", source="email")`. Se asigna siempre `Secret.from_plain(...)`; nunca se llama a `bus.encrypt` desde el módulo.

`exceptions.py`: `MemberError` (base), `MemberValidationError` (422, `validation_error`, con `field`), `MemberDocumentDuplicated` (409, `member_document_duplicated`, `field="document"`, `existing_id`, mensaje "Ya existe un socio con este documento"), `MemberNotFound` (404, `member_not_found`).

`schemas.py`:
- `EmergencyContactIn(name, phone, relationship: str | None = None)`.
- `MemberCreate` (`extra="forbid"`, `str_strip_whitespace=True`): `first_name`, `last_name`, `document_type: Literal["CC","CE","TI","PA"] = "CC"`, `document` (obligatorio, 3 a 30 caracteres), `phone: str | None`, `email: EmailAddress | None`, `birth_date: date | None`, `sex: Literal["f","m","x"] | None`, `notes: str | None` (hasta 2.000), `emergency_contact: EmergencyContactIn | None`, `data_consent_at: AwareDatetime | None`.
- `MemberDetailOut`: `id`, nombres, `sex`, `status`, `notes`, `document_type`, `document`, `phone`, `email`, `birth_date`, `emergency_contact` (todos enmascarados, `str | None`), `data_consent_at`, `data_consent_version` (siempre `None` en v0.1), `deleted_at`, `membership_status: str | None` (`None` hasta el Sprint 3), `created_at`, `updated_at`, `warnings: list[str]`.
- `MemberRef` (dataclass congelada: `id`, `first_name`, `last_name`, `status`, `is_deleted`), contrato para otros módulos.

`service.py`:
- Evento `MemberCreated(member_id: UUID)`.
- Puras: `validate_member_input(data, today)` (nombres vacíos, sexo, `birth_date > today`; `today` viene de `today_bogota()`), `compute_warnings(data) -> list[str]` (`["data_consent_missing"]` si falta la autorización, si no `[]`) y `mask(field, value, *, document_type=None) -> str | None` (documento `CC •••• 0304`, teléfono `••• ••• 4567`, correo `l•••@•••.co`, fecha `••/••/1991`, contacto `"Registrado"`; opera sobre el valor en memoria, nunca sobre el blob).
- `async create(session, data: MemberCreate) -> MemberDetailOut` (el actor sale de `current_actor`; el desglose pasaba `by`, no hace falta):
  1. valida; 2. `id_by_document` (pre-chequeo con `bus.blind_index`) y, si existe, `MemberDocumentDuplicated(existing_id)`; 3. arma el `Member` con `Secret.from_plain` y `data_consent_version=None`; 4. `session.begin_nested()` + `flush`: un `IntegrityError` de `uq_members_document_idx_alive` (carrera) se traduce a `MemberDocumentDuplicated` buscando el id existente; 5. `refresh` de las columnas de servidor; 6. `MemberCreated`; 7. respuesta enmascarada desde los valores de entrada (no se descifra nada).
- Contratos para otros módulos (devuelven dataclasses, nunca el ORM): `get_ref(session, member_id) -> MemberRef` (`MemberNotFound`), `ensure_exists(session, member_id, *, include_deleted=False) -> None`, `id_by_document(session, document) -> UUID | None` (entre no borrados), `count(session, *, include_deleted=False) -> int`.

`router.py`: `POST /members` con `require_role("admin","coach")`, 201, `response_model=MemberDetailOut`. Códigos 201, 401, 403, 409, 422.

`main.py`: `MODULES = ("auth", "settings", "audit", "members")`.

Fábrica y pruebas de arquitectura de B7:
- `tests/factories/members.py`: `KNOWN` con los valores conocidos (`"7319582046"`, `"+57 300 765 4321"`, `"Lucia.Gomez@Correo.co"`, `date(1991, 7, 23)`, `{"name": "Rosa", "phone": "3115550199"}`); `async make_member(session, **cambios) -> Member` (bajo `actor_scope(SYSTEM_USER_ID)`, `Secret.from_plain`, `flush`, `commit` del savepoint) y `async make_members(session, n) -> list[Member]` con documentos únicos (para la prueba de rendimiento). Necesita `bus_listo` (sección 9).
- `tests/factories/__init__.py`: `FACTORIES: dict[str, Callable[..., Awaitable[object]]]` por nombre `esquema.tabla`; B7 registra `members.members`.
- `tests/architecture/_imports.py`: se agrega `find_banned_imports(source: str, path: str) -> list[BannedImport]` (nodos `Import`, `ImportFrom`, y llamadas a `importlib.import_module` o `__import__` con argumento literal) e `is_allowed(path)` para `core/crypto/`, `core/security.py` y `core/security/`. No se mezcla con las reglas entre módulos que ya hay.
- `tests/architecture/test_import_analyzer.py` (nace): `import hashlib` y `from cryptography.hazmat.primitives import hashes` en `app/modules/members/service.py` se reportan con línea; `importlib.import_module("hmac")` y `__import__("jwt")` se reportan; lo mismo en `app/core/crypto/aead.py` y `app/core/security.py` no; `import hashlibx` no.
- `tests/architecture/test_banned_imports.py` (se amplía): recorre `src/app` con el analizador nuevo (también imports dinámicos literales) y agrega un control en directorio temporal.
- `tests/architecture/test_members_encrypted_at_rest.py` (nace; bloquea el checkpoint porque `tests/architecture` corre siempre, A-5): crea socios con la fábrica y comprueba con SQL crudo que `SELECT document, phone, email, birth_date, emergency_contact FROM members.members` no contiene ningún valor de `KNOWN` ni su forma normalizada (`row_to_json(t)::text`), que cada blob empieza por `apx1.<uuid>.A256GCM.`, que `document_idx` coincide con `bus.blind_index("member.document", ...)` y que no hay columnas `*_hint`.
- `tests/architecture/test_no_plaintext_at_rest.py` (nace): descubre las columnas cuyo tipo expone `is_encrypted` en `Base.metadata`, solo de modelos cuyo módulo empieza por `app.` (ignora el modelo de prueba de `tests/crypto/models_fixture.py`); exige una fábrica por tabla en `FACTORIES` ("agregue una fábrica para <tabla>"); `test_registry_columns_are_encrypted` cruza `registry.columns` con los metadatos (las tablas aún inexistentes avisan; `members.members` ya es error).
- `tests/architecture/test_audited_tables.py`: `members.members` pasa de `PENDING_AUDITED` a `REQUIRED_AUDITED_TABLES_V01`.
- `tests/architecture/test_no_sensitive_in_logs.py` (decisión 20): login real y `POST /members` real con `capsys`/`caplog`; el stdout no contiene token de acceso, refresh, contraseña, documento, teléfono, correo ni blob; la pata de `reveal` queda como prueba aparte con `skip(reason="US-074, Sprint 3")`.
- `tests/core/test_logging_redact.py` (se amplía, cierra la parte de US-069 de T8 de US-018, A-6): con un socio real de la fábrica se loguea la fila, su `repr` y un `IntegrityError` forzado, y ninguna línea JSON contiene un valor de `KNOWN`.
- `tests/core/test_migrations.py` / ciclo de Alembic con `0006`.

Rojo: `tests/members/test_member_rules.py`, `test_service_create.py`, `test_router_create.py` y las pruebas de arquitectura de arriba.

Casos clave:
- `"1.020.304"` y `"1020304"` dan el mismo `document_idx`; duplicado entre vivos da 409 con `existing_id`; contra un socio dado de baja se crea; dos sesiones que insertan el mismo documento a la vez: una gana y la otra recibe el 409.
- La fila `insert` de auditoría trae blobs y `subject_member_id` igual al id del socio; `created_by` es el actor.
- Un handler de `MemberCreated` que falla revierte el alta.
- `warnings == ["data_consent_missing"]` sin autorización y `[]` con ella; 403 para `member`, 401 sin token, 422 con `field` (`first_name`, `sex`, `birth_date`, `document`).
- El log capturado no contiene documento, teléfono, correo ni token.

Gate: `slice-gate.sh members <archivos de Rojo>`, `slice-gate.sh core/logging tests/core/test_logging_redact.py`, ciclo de Alembic hasta `0006` y `export-openapi`.

### S2-B8 · Buscar y listar socios (US-070)

Archivos a modificar (`modules/members/`) y crear:
- `schemas.py`:
  - `MemberRowOut(id, first_name, last_name, sex, status, deleted_at, membership_status: str | None, plan_name: str | None)`; ningún campo sensible ni enmascarado (N-01); los dos últimos van `None` hasta el Sprint 3.
  - `MemberListQuery` con `q` (`SearchQuery`, hasta 100), `status: Literal["active","inactive","deleted"] | None`, `sort: Literal["last_name","-last_name","first_name","-first_name","created_at","-created_at"] = "last_name"`.
  - `MemberName(id, first_name, last_name, sex)` (dataclass congelada).
- `service.py`:
  - `QueryPlan(q, name_pattern, by_document, by_phone, by_email)` y la pura `classify_query(q) -> QueryPlan`: `name_pattern` recortado con `%`, `_` y `\` escapados; `by_document` si `normalize_for_index(q, "generic")` no queda vacío; `by_phone` solo con al menos 7 dígitos; `by_email` solo si contiene `@`. Captura `CryptoError("empty_value")` (decisión 6).
  - `async list(session, filters: MemberListFilters, page: PageParams) -> Page[MemberRowOut]`: dentro de `bus.batch("index", None)` calcula los índices necesarios con `bus.blind_index(data_class, q)`; arma un `UNION` de subconsultas de ids (una por índice y una por `ILIKE` sobre `first_name || ' ' || last_name`, así la rama de documento usa `uq_members_document_idx_alive`); aplica `status` (`deleted` = `deleted_at IS NOT NULL`; `active` e `inactive` miran `deleted_at IS NULL` y `status`; sin filtro = `deleted_at IS NULL`), el orden de `sort` y `paginate`. Nunca descifra (cero filas `decrypt` en `crypto_ops`).
  - `async search_ids(session, q, include_deleted=False) -> set[UUID]` y `async names_for(session, ids) -> dict[UUID, MemberName]` (una consulta, incluye dados de baja y trae el sexo; sin N+1).
  - Admin y coach ven a los dados de baja con `status=deleted` (N-20).
- `router.py`: `GET /members` con `require_role("admin","coach")`, `Annotated[PageParams, Depends()]`, `response_model=Page[MemberRowOut]`; 200, 401, 403 y 422 (`limit`, `offset`, `sort`, `status`, `q`).
- `pyproject.toml`: agregar `perf` a `markers` (decisión 27).

Rojo: `tests/members/test_classify_query.py`, `test_service_list.py`, `test_router_list.py`, `test_list_perf.py` (`@pytest.mark.perf`: 1.000 socios sembrados con `make_members`, búsqueda por documento en menos de 500 ms y `EXPLAIN` de la rama de documento que usa `uq_members_document_idx_alive`) y `tests/architecture/test_list_rows_without_sensitive_fields.py`.

Casos clave:
- Se encuentra por `"1.020.304"`, por `"300 123 4567"` y `"+57 300 123 4567"`, por correo en mayúsculas y por `"góm"`.
- Excluye dados de baja por defecto y los muestra con `status=deleted`, también para el coach; ordena por cada `sort`; el término con `%` o `_` no actúa como comodín.
- `q` nunca aparece en los logs capturados.
- `test_list_rows_without_sensitive_fields.py`: recorre los `response_model` `Page[...]` de las rutas de `members` (con `effective_routes`) y falla si el esquema de la fila declara `document`, `phone`, `email`, `birth_date`, `emergency_contact` o cualquier `*_idx` o `*_hint`.

Gate: `slice-gate.sh members <archivos de Rojo de B8>` y `export-openapi`.

### S2-B9 · Crear y listar planes (US-078, US-079)

**DECISIÓN 32 · Nombre de plan único sin distinguir mayúsculas.** El desglose deja abierta la unicidad "Mensual" frente a "mensual" y dice que, si se quiere sin distinguir mayúsculas, el índice pasa a `lower(name)` en la misma migración antes de aplicarla. Recomendado: hacerlo ahora. `uq_plans_name_alive` es único sobre `lower(btrim(name))` donde `deleted_at IS NULL`; el pre-chequeo del service compara con `func.lower(Plan.name) == nombre.lower()`. Además, para que un valor desbordado no produzca un 500, `PlanCreate` acota `price_cop` a 1 a 1.000.000.000, `duration_days` a 1 a 3.650 y `class_count` a 1 a 1.000.

Archivos a crear:
- `api/migrations/versions/0007_plans.py` (`down_revision = "0006_members"`), tabla `plans.plans`:
  - columnas comunes y `deleted_at`;
  - `name text`, `price_cop integer`, `kind text`, `duration_days integer`, `class_count integer` (nula), `is_active boolean` (default `true`), todas no nulas salvo `class_count`;
  - CHECKs: `price_cop > 0`, `duration_days > 0`, `kind IN ('days','classes')`, `(kind = 'classes' AND class_count IS NOT NULL AND class_count > 0) OR (kind = 'days' AND class_count IS NULL)` (corregido en B9: ver DECISIONES S2-B9), `btrim(name) <> ''`;
  - índices `uq_plans_name_alive` (decisión 32) e `ix_plans_active_alive (is_active) WHERE deleted_at IS NULL`;
  - `downgrade`: `drop_table`.
- `api/tests/migrations/test_0007_plans.py` (CHECKs con `INSERT` crudo: precio 0, `days` con clases, nombre repetido en distinta capitalización).
- `api/src/app/modules/plans/{__init__,models,schemas,exceptions,service,router}.py`, `tests/plans/__init__.py`, `tests/factories/plans.py`.

`exceptions.py`: `PlanError` (base), `PlanValidationError` (422, `validation_error`, `field`), `PlanNameDuplicated` (409, `plan_name_duplicated`, `field="name"`, `existing_id`), `PlanNotFound` (404, `plan_not_found`), `PlanScopeForbidden` (403, `forbidden`).

`schemas.py`:
- `PlanCreate` (`extra="forbid"`, `str_strip_whitespace=True`): `name` (1 a 80), `price_cop: StrictInt`, `kind: Literal["days","classes"]`, `duration_days: StrictInt`, `class_count: StrictInt | None = None` (`120000.5`, `"120000"` y `true` dan 422).
- `PlanOut(id, name, price_cop, kind, duration_days, class_count, is_active, created_at, updated_at)`.
- `PlanSnapshot` (dataclass congelada: `id`, `name`, `price_cop`, `kind`, `duration_days`, `class_count`, `is_active`, `deleted_at`), el contrato que `memberships` importará (nunca el ORM).
- `PlanListQuery(q: SearchQuery, active: bool | None)`.

`service.py`:
- Evento `PlanCreated(plan_id: UUID)`.
- Puras: `validate_plan(kind, duration_days, class_count) -> None` (`PlanValidationError(field)`), `ensure_list_scope(role, active)` (el coach solo con `active=True`; si no, `PlanScopeForbidden`), `ensure_read_scope(role, plan)` (el coach sobre un plan inactivo: `PlanScopeForbidden`).
- `async create(session, data: PlanCreate) -> PlanOut`: recorta el nombre, `validate_plan`, pre-chequea el nombre entre vivos, `begin_nested()` + `flush` (la carrera por `IntegrityError` se traduce a `PlanNameDuplicated`), `refresh` de las columnas de servidor, `PlanCreated`.
- `async list(session, *, q, active, page: PageParams, role: Role) -> Page[PlanOut]`: excluye `deleted_at IS NOT NULL`; busca sin tildes ni mayúsculas con `translate(lower(name), 'áéíóúüñ', 'aeiouun')` aplicado a columna y término (comodines escapados); orden `name, id`.
- `async get(session, plan_id, *, for_share: bool = False) -> PlanSnapshot` (`PlanNotFound` si no existe o está dado de baja; con `for_share=True` toma `FOR SHARE` para que la venta del Sprint 3 no compita con una baja), `async get_including_deleted(session, plan_id) -> PlanSnapshot`, `async names_for(session, plan_ids) -> dict[UUID, str]` (incluye dados de baja, una consulta).

`router.py` (plano): `POST /plans` (`require_role("admin")`, 201), `GET /plans` y `GET /plans/{id}` (`require_role("admin","coach")` más la regla de alcance del service, `PageParams`). `PATCH`, `activate`, `deactivate` y `DELETE` entran en el Sprint 4A.

`main.py`: `MODULES = ("auth", "settings", "audit", "members", "plans")`. `test_audited_tables`: `plans.plans` pasa a `REQUIRED_AUDITED_TABLES_V01`.

Rojo: `tests/plans/test_validate_plan.py`, `test_service_create.py`, `test_router_create.py`, `test_scope_rules.py`, `test_service_list.py` y `test_router_list.py`.

Casos clave:
- Alta de "Mensual" y "Tiquetera 12"; fila `insert` en `audit.audit_log` con `table_name = 'plans.plans'`; `PlanCreated` emitido y un handler que falla revierte; nombre repetido (también "mensual") da 409 con `existing_id`; el nombre de un plan dado de baja se puede reutilizar.
- 403 al coach y a `member` en `POST /plans`; 422 con `field` para `price_cop` (`120000.5`, `-1`, `0`, `"120000"`), `duration_days`, `class_count` y `name` (`"   "`).
- El coach: `GET /plans?active=true` 200; `active=false` o sin parámetro: 403; `GET /plans/{id}` de un plan inactivo: 403; un dado de baja: 404.
- `limit=500` da 422 con `field="limit"`; `price_cop` sale entero; `q="TRIMES"` y `q="promo"` encuentran; un plan con tilde se encuentra sin tilde.

Gate: `slice-gate.sh plans <archivos de Rojo>`, ciclo de Alembic hasta `0007` y `export-openapi`.

## 5. Front: base común y slices F1 a F8

Antes de F1: `docs/openapi.json` queda definitivo con B9, se corre `cd web && npm run gen:api` y se agrega `@hookform/resolvers` (decisión 22). Los tipos de cada feature salen de `components["schemas"]["..."]` de `core/api/types.ts`.

**DECISIÓN 33 · F2 antes de F3 y el almacén de sesión.** Las guardas de F2 necesitan una sesión que F3 recién completa. Recomendado: F2 crea `core/auth/session.ts` con el almacén y la restauración; F3 le agrega la coordinación de refresh y el cierre de sesión. Reparto:
- F2: tipo `SessionUser { id, email, role, memberId, gymName, mustChangePassword }`, `SessionState { status: "loading" | "anonymous" | "authenticated"; user: SessionUser | null }`, `getAccessToken()`, `setSession(payload)`, `clearSession(reason)`, `subscribe(listener)`, `useSession()` (con `useSyncExternalStore`) y `restoreSession(): Promise<boolean>` (una sola promesa compartida: `POST /auth/refresh` y luego `GET /auth/me`).
- F3: `refreshAccessToken()` (single-flight, Web Locks `apex-refresh`, canal `apex-auth`), `logout()` e `installSessionBridge()` (registra `setAccessTokenGetter` y `registerOnUnauthorized` de `core/api/client.ts` y escucha el canal). `main.tsx` llama a `installSessionBridge()` antes de montar.

Estructura común que nace en F1 a F3:
- `web/src/core/api/queryClient.ts`: `QueryClient` con `retry` desactivado para 4xx y `staleTime` de 30 s; `clearSession` lo limpia.
- `web/src/core/auth/SessionRole.tsx`: `<SessionRoleProvider>` que lee `useSession()` y entrega el rol a `RoleProvider` (así `useCan` y `<Can>` funcionan sin cambiar su firma).
- `web/src/main.tsx` y `web/src/App.tsx`: `QueryClientProvider`, `SessionRoleProvider` y `RouterProvider`.
- Etiquetas de rol (`ROLE_LABELS`) en `core/auth/permissions.ts`: Admin, Coach, Socio.
- Un 403 del API (por ejemplo, un coach que llega a una pantalla de admin) se muestra en el estado de error de la página (`DataTable.error` o el mensaje del formulario) y no cierra la sesión; no hay toast global (no existe en el kit).

### S2-F1 · Layouts (US-061, US-062)

Archivos a crear (cada uno con su `*.test.tsx` y su `*.module.css` con tokens, sin literales):
- `web/src/layouts/nav.ts`: tipos `NavGroup` y `NavItem {label, to, feature, action?, group}`, catálogo `NAV_CATALOG` con los grupos de `DESIGN.md` (Inicio, Hoy, Gestión, Entrenamiento, Avisos, Sistema) y la pura `buildNavItems(role: Role | null, enabled: ReadonlySet<Feature>): NavGroup[]`, que filtra con `can()` e `isRouteEnabled`. Los grupos vacíos se omiten; "Hoy" no se muestra (Q25); para `member` devuelve `[]`.
- `web/src/layouts/PanelLayout.tsx`: presentacional, con props `{ user: { email, roleLabel }, gymName, navGroups, onChangePassword, onLogout, logoutPending, themeToggle? }` y `<Outlet />`. Grid con `TopBar`, `SideNav` de `var(--sidebar)` y `<main id="contenido" tabIndex={-1}>`; enlace "Saltar al contenido"; escritorio desde 1024 px, tablet con menú plegado a iconos, celular con cajón. (El contenedor que lee la sesión es `PanelShell`, se crea en F3.)
- `web/src/shared/ui/TopBar.tsx`: fondo `--black`, logo `apex-logo-dark-bg.png`, `gymName` (por defecto "APEX"), fecha y hora de Bogotá con `formatDateTime` en un subcomponente con su propio temporizador de un minuto, correo y rol, menú de usuario (`aria-haspopup`, `aria-expanded`) con "Mi cuenta" y "Cerrar sesión", ranura `themeToggle` y botón ☰ de 44 px solo en celular.
- `web/src/shared/ui/SideNav.tsx`: grupos con títulos `--text-section-title`, `aria-current="page"` más un indicador no cromático, modo cajón (`role="dialog"`, foco atrapado con `useFocusTrap`, Escape y clic fuera devuelven el foco al ☰); `// DESIGN-GAP:` por el cajón y el modo plegado.
- `web/src/layouts/PortalLayout.tsx` y `portalTabs.ts` (`PORTAL_TABS`: Inicio, Pagos, WODs, Progreso, Yo; columna de 600 px como máximo, menú inferior fijo, relleno inferior igual al alto del menú más `env(safe-area-inset-bottom)`).
- `web/src/layouts/GymLayout.tsx` (tema oscuro forzado, `--control` sustituido por `var(--control-gym)` en el contenedor, barra mínima con título y "Salir") y `TvLayout.tsx` (1920×1080, `overflow: hidden`, `cursor: none`, raíz `inert`, escalado con `transform: scale()`).
- `web/src/shared/hooks/useForcedTheme.ts`: fija `document.documentElement.dataset.theme` y lo restaura al desmontar.
- `web/src/dev/LayoutsPreview.tsx`: página de muestra de los cuatro layouts, solo con `import.meta.env.DEV` o dentro del catálogo de F8.
- `web/src/layouts/layouts.no-fetch.test.ts` (ningún archivo de `layouts/` importa `core/api` ni `@tanstack/react-query`) y `layouts.a11y.test.tsx` (`vitest-axe` sobre los cuatro).
- `web/tests/e2e/panel-layout.spec.ts` y `layouts.spec.ts` (proyecto `preview`; capturas en 320, 768, 1024 y 1440 px y `scrollWidth <= clientWidth`).

Rojo: `nav.test.ts` (el admin ve Inicio, Socios, Planes, Usuarios y Configuración; el coach no ve Planes ni Sistema; `member` lista vacía; grupos vacíos omitidos), `PanelLayout.test.tsx`, `TopBar.test.tsx`, `SideNav.test.tsx` (orden de tabulación, "Saltar al contenido", con 390 px el ☰ abre el cajón, Escape lo cierra y el foco vuelve), `PortalLayout.test.tsx`, `GymLayout.test.tsx`, `TvLayout.test.tsx` y los dos E2E.

Gate: `slice-gate.sh web/layouts <pruebas de src/layouts>` y `slice-gate.sh web/shared <pruebas de TopBar y SideNav>`.

### S2-F2 · Rutas y guardas (US-067, US-053)

Archivos a crear o modificar:
- `web/src/config/features.ts`: tipo `Feature` (17: `auth`, `dashboard`, `members`, `plans`, `memberships`, `payments`, `users`, `audit`, `settings`, `crypto`, `classes`, `wods`, `results`, `athletes`, `notifications`, `portal`, `tv`), `ENABLED_FEATURES` del Sprint 2 (`auth`, `dashboard`, `members`, `plans`, `users`, `settings`) y la pura `isRouteEnabled(route, enabled)` (una ruta sin `feature` siempre está habilitada).
- `web/src/config/routeTable.ts` (decisión 23): `RouteDef {path, feature?, access: "public" | Action, layout: "access" | "panel" | "portal" | "gym" | "tv", load?}`. Declara todas las rutas de `ROUTES.md` (las de versiones futuras sin `load`, deshabilitadas) más `/cambiar-clave` (`// DESIGN-GAP:`). Acciones del Sprint 2: `/` (`dashboard.view`), `/socios` (`members.view`), `/socios/nuevo` (`members.create`), `/planes` (`plans.view`), `/sistema/usuarios` (`users.manage`), `/sistema/configuracion` (`settings.manage`). No existe `/hoy` (Q25).
- `web/src/config/routes.reference.ts`: oráculo escrito a mano desde `ROUTES.md`.
- `web/src/routes.tsx`: `createAppRouter()` con React Router 7 a partir de la tabla; cada ruta lleva `handle: {feature, access}` y `lazy`; una ruta deshabilitada da `NotFound` sin descargar su código. `web/src/pages/NotFound.tsx`: "No encontrada", `h1` único, enlace a `homeFor(role)`.
- `web/src/core/auth/routeAccess.ts`: `canAccessRoute(role, path)`, `homeFor(role)` (`/` para admin y coach, `/mi` para `member`) y `safeNext(next, role)` (solo rutas internas que empiezan por `/`, no por `//` ni por un esquema, y permitidas para el rol).
- `web/src/core/auth/session.ts` (la parte de F2, decisión 33), `RequireAuth.tsx` (restaura la sesión una vez por carga; sin sesión va a `/login?next=<ruta>`; con `mustChangePassword` va a `/cambiar-clave`), `RequireRole.tsx` (un `member` en el panel va a `/mi`; admin o coach en `/mi/*` van a `/`; sin permiso muestra `NoPermissionPage`) y `NoPermissionPage.tsx` ("Sin permiso", enlace a `homeFor`, `// DESIGN-GAP:`).
- `web/src/features/dashboard/pages/InicioPage.tsx` (decisión 25).
- `web/src/layouts/nav.ts` pasa a usar `canAccessRoute` y `isRouteEnabled`; `web/src/core/auth/index.ts` exporta lo nuevo.

Rojo: `src/routes.test.ts` (inventario contra `routes.reference.ts`; `/socios` carga dentro de `PanelLayout`; `/clases` da NotFound y su `import` no se ejecuta; `/hoy` da NotFound), `src/config/features.test.ts`, `src/core/auth/routeAccess.test.ts` (matriz de los tres roles contra cada ruta; `safeNext` rechaza `//evil.com`, `https://x` y rutas de otro rol), `RequireAuth.test.tsx`, `RequireRole.test.tsx` (la restauración hace un refresh y un `me`) y `tests/e2e/role-guards.spec.ts` (proyecto `stack`: el coach escribe `/planes` y `/sistema/configuracion` y ve "Sin permiso", el menú no muestra Planes ni Sistema, y el admin ve ambos).

Gate: `slice-gate.sh web/app <archivos de Rojo>` y `slice-gate.sh web/core <pruebas de core/auth>`.

### S2-F3 · Login, refresh y logout (US-042, US-043, US-044 front)

Archivos a crear o modificar:
- `web/src/features/auth/schemas.ts`: `loginSchema` (Zod: correo con formato, contraseña no vacía).
- `web/src/features/auth/api.ts`: `useLogin()` (`useMutation` sobre `POST /auth/login` con `skipAuthRetry: true`; al terminar llama a `setSession`).
- `web/src/features/auth/pages/LoginPage.tsx` y `components/LoginCard.tsx` (`Login.html`, tema claro): `Field`, `Button`, React Hook Form; estados inicial, cargando (botón deshabilitado) y error genérico sobre la tarjeta; ante un error conserva el correo y limpia la contraseña; un 429 muestra "Demasiados intentos. Espera un momento." con el `Retry-After`; al terminar navega a `safeNext(next, role)` o `homeFor(role)`, o a `/cambiar-clave` si `must_change_password`. Enlace "Olvidé mi contraseña" a `/recuperar`.
- `web/src/core/auth/session.ts` (completa): `refreshAccessToken()` con tres defensas (sección 7.6), `logout()` (`POST /auth/logout`; en `finally` limpia la sesión, publica `logout` en el canal, vacía el `QueryClient` y navega a `/login`), `installSessionBridge()`.
- `web/src/layouts/PanelShell.tsx`: contenedor de `PanelLayout` con `useSession()`, `buildNavItems`, `logout()` y `gymName`.
- `web/src/main.tsx`: `installSessionBridge()` antes de montar; `web/src/shared/ui/TopBar.tsx` recibe `onLogout` y deshabilita la opción mientras dura la petición.
- `web/src/core/api/client.ts`: sin cambios de contrato; login, refresh y logout usan `skipAuthRetry`.

Rojo: `src/features/auth/pages/LoginPage.test.tsx` (éxito con redirección por rol, 401 que conserva el correo, 422, 429, botón deshabilitado durante la petición), `src/core/auth/session.test.ts` (tres peticiones concurrentes con `token_expired` hacen un solo refresh y tres reintentos; un refresh 401 lleva a `/login?next=/socios`; dos "pestañas" simuladas con `BroadcastChannel` y `navigator.locks` hacen un solo refresh; nunca se llama a `console` con el token; ningún `localStorage` ni `sessionStorage` en `src/core/auth`), `src/shared/ui/TopBar.logout.test.tsx` (tras el 204 y tras un error de red la sesión queda limpia, se publica el mensaje y se navega a `/login`) y `tests/e2e/login.spec.ts` (proyecto `stack`: admin entra y ve `/`).

Gate: `slice-gate.sh web/auth <pruebas de features/auth>`, `slice-gate.sh web/core <pruebas de core/auth y core/api>` y `slice-gate.sh web/shared src/shared/ui/TopBar.logout.test.tsx`.

### S2-F4a · Mi cuenta, activación, recuperación, alta y lista de usuarios (US-045, US-046, US-047, US-048 front)

Archivos a crear o modificar:
- `web/src/shared/ui/statusLabel.ts` y `StatusTag.tsx` (decisión 24): `ACCOUNT_LABELS` y `ACCOUNT_TONES`; `StatusTag` acepta `status` (membresía) o `account` (cuenta). Gate `web/shared`.
- `web/src/features/auth/api.ts`: `useMe()` (`GET /auth/me`, clave `["me"]`), `useChangePassword()` (`POST /auth/me/password`), `useResetPassword()` (`POST /auth/reset`), `useForgotPassword()` (`POST /auth/forgot`).
- `web/src/features/auth/schemas.ts`: `changePasswordSchema` (actual, nueva de 12 a 128 caracteres, confirmación con `refine`), `resetSchema` y `forgotSchema`.
- `web/src/features/auth/components/ChangePasswordPanel.tsx`: `SidePanel` con tres `Field`; el 422 con `field: "current_password"` o `"new_password"` se muestra bajo su campo; el éxito cierra el panel y avisa "Contraseña actualizada". Lo abre "Mi cuenta" del `TopBar`.
- `web/src/features/auth/pages/ResetPage.tsx` (`/restablecer/:token`; llama a `history.replaceState` para sacar el token de la barra; 204 lleva a `/login` con aviso; 400 muestra "El enlace ya no es válido. Pide uno nuevo al administrador."), `ForgotPage.tsx` (`/recuperar`; siempre muestra "Pídele al administrador tu enlace de recuperación"; `// DESIGN-GAP:`) y `ChangePasswordPage.tsx` (`/cambiar-clave`, mismo formulario que `ResetPage` pero con sesión; al terminar va a `homeFor`).
- `web/src/features/system/api.ts`: `useUsers(params)` (clave `["users", params]`), `useCreateUser()` (invalida `["users"]`).
- `web/src/features/system/schemas.ts`: esquema de la respuesta de lista (`pageSchema(userRowSchema)`), `createUserSchema` (correo, rol `admin` o `coach`).
- `web/src/features/system/pages/UsersPage.tsx`: `PageHeader` "Usuarios" con "Nuevo usuario", `FilterBar` (búsqueda, rol, estado), `DataTable` (correo, rol, `StatusTag`, último acceso en hora de Bogotá, sesiones abiertas), `Pagination`, estados de carga, vacío ("No hay usuarios con estos filtros") y error; `useListParams({filters: ["role", "status"], sorts: ["email"]})`.
- `web/src/features/system/components/NewUserPanel.tsx`: `SidePanel` con correo y rol; tras el 201 muestra el enlace en un campo de solo lectura, el botón "Copiar" (`navigator.clipboard.writeText`) y "Entrega este enlace por un medio seguro; vence en 72 horas"; al cerrar el enlace se descarta del estado; el 409 se muestra bajo el correo con enlace al usuario existente.
- `tests/e2e/users-activation.spec.ts` (proyecto `stack`): admin entra, crea un coach, copia el enlace, lo abre en otra ventana, fija una contraseña de 12 o más caracteres y entra como coach a `/`; el coach no ve Usuarios ni Configuración.

Rojo: pruebas en `src/features/auth/components` (`ChangePasswordPanel.test.tsx`) y `src/features/auth/pages` (`ResetPage.test.tsx`, `ForgotPage.test.tsx`), `src/features/system/pages/UsersPage.test.tsx`, `src/features/system/components/NewUserPanel.test.tsx` y el E2E.
Gate: `slice-gate.sh web/auth <pruebas de features/auth>` y `slice-gate.sh web/system <pruebas de features/system>`. Checkpoint propio.

### S2-F4b · Gestión de usuarios (US-049, US-050, US-051, US-052 front)

- `web/src/features/system/api.ts`: `useUser(id)`, `useUpdateUser()`, `useDeleteUser()`, `useLockUser()`, `useUnlockUser()`, `useRevokeSessions()`, `useResendLink()`; todas invalidan `["users"]`.
- `web/src/features/system/components/EditUserPanel.tsx`: `SidePanel` con correo y rol (`admin` o `coach`); los 409 salen por campo y `last_admin` como mensaje general.
- `web/src/features/system/components/LinkModal.tsx`: enlace de solo lectura, "Copiar", el propósito en texto ("Activación, vence en 72 horas" o "Recuperación, vence en 1 hora", con la hora de Bogotá) y "Entrégalo por un medio seguro. Al generar uno nuevo, el anterior deja de servir."; al cerrar se descarta; el 409 `user_not_eligible` muestra su mensaje.
- `UsersPage.tsx`: acciones por fila: "Editar", "Dar de baja" (`ConfirmModal`: "La cuenta pierde el acceso de inmediato. Su historial se conserva."), "Bloquear" (`ConfirmModal`: "Cierra todas sus sesiones y le impide entrar hasta que lo desbloquees"), "Desbloquear" (solo si `locked`), "Cerrar sesiones" (con el número de sesiones; sobre uno mismo termina en `clearSession()` y `/login`) y "Reenviar enlace" (oculta para bloqueados y dados de baja). "Dar de baja" y "Bloquear" no aparecen en la fila del usuario conectado (se compara `row.id` con `session.user.id`; el API igual protege).
- Rojo: `UsersPage.delete.test.tsx`, `UsersPage.lock.test.tsx`, `UsersPage.sessions.test.tsx`, `EditUserPanel.test.tsx`, `LinkModal.test.tsx`.
- Gate: `slice-gate.sh web/system <archivos de Rojo>`. Checkpoint propio.

### S2-F5 · Configuración (US-055, US-057, US-058 front)

- `web/src/features/system/api.ts`: `useSettingsSection(key)` devuelve `{ query, save, isSaving, isConflict, reload }`: `query` es `GET /settings/{key}` (clave `["settings", key]`, rutas tipadas de gym, privacy y memberships); `save(value)` hace `PATCH` con `{ value, version: query.data.version }`; si sale bien actualiza solo la caché de esa clave; un 409 `version_conflict` pone `isConflict` y no reintenta; `reload()` hace refetch.
- `web/src/features/system/schemas.ts`: `gymSettingsSchema`, `privacySettingsSchema`, `membershipsSettingsSchema` (mismos rangos que el API, mensajes en español) y el helper `applyApiFieldError(form, error)` que quita el prefijo `value.` de `error.field` y marca el campo del formulario.
- `web/src/features/system/pages/ConfigPage.tsx`: `PageHeader` "CONFIGURACIÓN" y `Tabs` (`?tab=`) con Gimnasio, Privacidad y Membresías (las demás no se muestran; `// DESIGN-GAP:` por pestañas en vez de secciones y por "Zona horaria"); un `useBlocker` con `ConfirmModal` ("Tienes cambios sin guardar. ¿Descartarlos?") al cambiar de pestaña o salir. La ruta ya está en la tabla desde F2.
- `components/GymSettingsForm.tsx` (siete `Field` de 44 px), `PrivacySettingsForm.tsx` (versión, texto con contador, años de retención, "Autorización obligatoria desde"; muestra "Versión vigente: 2026-10 · vigente desde 21 oct 2026" con `formatDate(updated_at)`; al cambiar `policy_version` abre `ConfirmModal` con "Los socios que ya aceptaron conservan la versión anterior."; el texto se renderiza como texto plano) y `MembershipsSettingsForm.tsx` (cuatro enteros con su explicación y el valor por defecto; `// DESIGN-GAP:` porque `Config.html` muestra "Días de gracia").
- Todos los formularios: botón "Guardar" con estado de envío, aviso "Cambios guardados", aviso de conflicto "Otra persona cambió esta sección. Recarga para ver los cambios." con botón "Recargar" y sin sobrescribir; sin borradores en `localStorage`.
- Rojo: `GymSettingsForm.test.tsx`, `PrivacySettingsForm.test.tsx`, `MembershipsSettingsForm.test.tsx`, `ConfigPage.test.tsx` y `tests/e2e/settings-gym.spec.ts` (proyecto `stack`: el admin guarda nombre y NIT, recarga y los ve; publica una versión de privacidad; fija `expiring_days = 7`; el coach ve "Sin permiso"; el TopBar del coach muestra `gym_name`; `axe` sin violaciones).
- Gate: `slice-gate.sh web/system <archivos de Rojo>`.

### S2-F6 · Socios: alta y lista (US-069, US-070 front)

**DECISIÓN 34 · Destino tras guardar y enlace al socio existente.** La ficha (`/socios/:id`) llega en el Sprint 3 (US-073). Recomendado: tras el 201 el formulario lleva a `/socios` con un aviso "Socio registrado" (`// DESIGN-GAP:`), y el enlace "Ver socio existente" del 409 apunta a `/socios/{existing_id}` aunque hoy dé NotFound hasta US-073 (`Field.errorAction` solo acepta rutas internas). No se enlaza a `/socios?q=<documento>` porque pondría el documento en la URL, en el historial y en los logs.

- `web/src/features/members/schemas.ts`: `memberCreateSchema` (mismas reglas que `MemberCreate`; documento obligatorio; teléfono y correo opcionales; la fecha de nacimiento no puede ser futura) y `memberRowSchema`.
- `web/src/features/members/api.ts`: `useCreateMember()` (`POST /members`; invalida `["members"]`; mapea el envelope a errores de campo con `applyApiFieldError`; en el 409 deja `existingId`) y `useMembers(params)` (`GET /members`, clave `["members", params]`, cancela con el `signal` de TanStack Query).
- `web/src/features/members/pages/MemberFormPage.tsx` (`Socio_Form`) y `components/MemberFormFields.tsx`: secciones Identificación (nombres, apellidos, sexo, tipo y número de documento, fecha de nacimiento), Contacto (teléfono, correo), Contacto de emergencia (nombre, teléfono, parentesco) y la casilla "El socio autorizó el tratamiento de datos" que envía `data_consent_at = ahora`; si la respuesta trae `data_consent_missing` muestra "Falta la autorización de tratamiento de datos". Botones Cancelar y Guardar. `// DESIGN-GAP:` por foto, firma y archivo, "Acceso al portal", unidad de cargas, observaciones de salud, nombre en un solo campo y "Guardar y vender membresía" (Sprint 3). Texto de ayuda: "No escribas datos sensibles en Notas".
- `web/src/features/members/pages/MembersListPage.tsx` (`Socios_Lista`): `PageHeader` con "Nuevo socio" (`<Can action="members.create">`), `Chips` ("Todos", "Dados de baja"), `FilterBar` con búsqueda (300 ms, placeholder "Nombre, documento o teléfono") y orden, `DataTable` (nombre, estado del socio, membresía vacía), `Pagination`; parámetros en la URL con `useListParams({filters: ["status"], sorts: ["last_name", "first_name", "created_at"]})`; cambiar la búsqueda reinicia `offset`; estados de carga, vacío ("No hay socios que coincidan con la búsqueda") y error. `// DESIGN-GAP:` por las columnas de teléfono, plan y asistencia y los chips por estado de membresía.
- Rojo: `MemberFormPage.test.tsx` (validación en el cliente, error de campo del API, enlace del 409, aviso de autorización, nada del formulario en `localStorage`) y `MembersListPage.test.tsx` (URL, reinicio de `offset`, tres estados, `status=deleted` para el coach).
- Gate: `slice-gate.sh web/members <archivos de Rojo>`.

### S2-F7 · Planes: alta y lista (US-078, US-079 front)

- `web/src/features/plans/schemas.ts`: `planSchema` con `superRefine` (`class_count` obligatorio solo con `kind = "classes"`, precio entero positivo) y `planRowSchema`.
- `web/src/features/plans/api.ts`: `usePlans(params)` (clave `["plans", params]`), `usePlan(id)` y `useCreatePlan()` (invalida `["plans"]`).
- `web/src/features/plans/components/PlanForm.tsx`: `SidePanel` con React Hook Form; "Número de clases" aparece y es obligatorio solo con "Por clases"; el precio se escribe y se muestra con `core/i18n/format.ts` (`$ 120.000`); botón deshabilitado mientras envía; muestra el error de `field` del 422 y del 409 (`plan_name_duplicated`) bajo "Nombre".
- `web/src/features/plans/pages/PlansPage.tsx`: `PageHeader` con "Nuevo plan", `FilterBar` (búsqueda y Activos, Inactivos, Todos), `DataTable` (plan, tipo, precio, duración, clases, `StatusTag` "Activo" o "Inactivo" con texto), `Pagination`, parámetros en la URL y estados de carga, vacío ("No hay planes") y error. `// DESIGN-GAP:` por "Socios con él" y por la acción "Editar" (Sprint 4A); `rowHref` apunta a `/planes?plan=<id>`.
- Rojo: `PlansPage.test.tsx` y `PlanForm.test.tsx` (campo condicional, validación en el cliente, error de campo del API, envío bloqueado si es inválido).
- Gate: `slice-gate.sh web/plans <archivos de Rojo>`.

### S2-F8 · Temas, accesibilidad y capturas (US-068)

- `web/src/core/theme/theme.ts`: `resolveTheme(stored, zoneDefault, prefersDark)`, `readStoredTheme` y `writeStoredTheme` (clave `apex.theme`, con `try/catch`), `applyTheme`, store con `useSyncExternalStore` (`useTheme()`, `toggleTheme()`) que escucha `prefers-color-scheme`.
- `web/src/core/theme/ThemeToggle.tsx`: botón de 44 px con texto accesible ("Cambiar a tema oscuro"); se pasa a `PanelShell` como `themeToggle`.
- `web/src/dev/Catalog.tsx` y `web/catalog.html` (`vite build --mode catalog`; fuera del build de producción y de la imagen de Nginx): los 16 componentes (`Button`, `Field`, `StatusTag` con los estados de membresía y de cuenta, `TopBar`, `SideNav`, `PageHeader`, `FilterBar`, `DataTable`, `Pagination`, `Chips`, `Tabs`, `KpiCard`, `SidePanel`, `ConfirmModal`, `MaskedValue`, `HistoryAside`) en sus estados y los cuatro layouts.
- `web/.stylelintrc.cjs` y la regla de ESLint para colores y `font-family` literales ya existen (`tests/lint`); se agrega `web/tests/lint/stylelint.test.ts` si falta.
- `web/vitest.config.ts`: el umbral de 80 % para `src/shared/ui/**` ya está; `web/tests/kit-inventory.test.ts` falla si alguno de los 16 componentes no tiene su `*.test.tsx`.
- `web/tests/e2e/kit.spec.ts` (proyecto `preview`): para cada tema y ancho (320, 768, 1024, 1440) abre el catálogo y los layouts, corre `AxeBuilder` con `wcag2a`, `wcag2aa` y `wcag21aa`, comprueba `scrollWidth <= clientWidth` y guarda la captura. `web/package.json`: `@axe-core/playwright` (dev) y el script `build:catalog`.
- Rojo: `src/core/theme/theme.test.ts` (un `localStorage` que lanza no rompe), `tests/kit-inventory.test.ts` y `tests/e2e/kit.spec.ts`.
- Gate: `slice-gate.sh web/core <pruebas de core/theme>` y `npx playwright test tests/e2e/kit.spec.ts`.

## 6. Mapa de los 29 endpoints al front

- `POST /auth/login`: `useLogin` (`features/auth/api.ts`), `LoginCard`.
- `POST /auth/refresh`: `restoreSession` y `refreshAccessToken` (`core/auth/session.ts`).
- `POST /auth/logout`: `logout()` (`core/auth/session.ts`), menú de usuario del `TopBar`.
- `GET /auth/me`: `restoreSession` (llena `SessionUser`, incluye `gymName` y `mustChangePassword`) y `useMe`.
- `POST /auth/me/password`: `useChangePassword`, `ChangePasswordPanel` y `ChangePasswordPage`.
- `POST /auth/forgot` y `POST /auth/reset`: `useForgotPassword`, `useResetPassword`, `ForgotPage`, `ResetPage`.
- `GET /users` y `POST /users`: `useUsers`, `useCreateUser`, `UsersPage`, `NewUserPanel`.
- `GET`, `PATCH`, `DELETE /users/{id}`: `useUser`, `useUpdateUser`, `useDeleteUser`, `EditUserPanel`, acción "Dar de baja".
- `POST /users/{id}/lock`, `/unlock`, `/revoke-sessions`, `/resend-link`: `useLockUser`, `useUnlockUser`, `useRevokeSessions`, `useResendLink`, `LinkModal`.
- `GET` y `PATCH /settings/gym`, `/settings/privacy`, `/settings/memberships`: `useSettingsSection(key)` y los tres formularios. `GET` y `PATCH /settings/{section}` (genérico) no los usa el front; sirve a clientes del API y a las pruebas del 404.
- `POST /members` y `GET /members`: `useCreateMember`, `useMembers`, `MemberFormPage`, `MembersListPage`.
- `POST /plans`, `GET /plans`, `GET /plans/{id}`: `useCreatePlan`, `usePlans`, `usePlan`, `PlanForm`, `PlansPage`.

## 7. Flujos de datos

### 7.1 Login → cookie → refresh (rotación y reuso, N-13)

Login (`POST /api/v1/auth/login`):
1. Nginx aplica `limit_req` de `/api/v1/auth/` (30 por minuto por IP, ráfaga 10). La dependencia `rate_limit("login")` cuenta 5 por 60 s por IP (IPv6 por /64) y responde 429 con `Retry-After` antes de leer el cuerpo y de evaluar argon2.
2. El router valida `LoginIn` (422 con `field` si falla; contraseña de hasta 128) y llama a `auth.service.login(session, email, password, user_agent=..., policy=policy_from(settings))`.
3. El service normaliza el correo y llama a `ratelimit.enforce("login-account", correo, limit=10, window_s=900)`: 429 también para correos inexistentes (misma respuesta, sin enumerar).
4. Busca un usuario no borrado con ese correo, distinto de `SYSTEM_USER_ID`.
   - No existe: `dummy_verify(password)` en un hilo (`anyio.to_thread.run_sync`), log sin el correo y `InvalidCredentials`. Sin evento (N-31).
   - Existe: `verify_password` en un hilo. Si falla o `can_login(user)` es falso, dentro de `actor_scope(user.id)`: suma `failed_login_count` (solo si la contraseña era incorrecta; si llega a `LOGIN_LOCK_AFTER` y no es el último admin activo, pone `locked_at` y emite `UserLocked` y `SessionsRevoked`), emite `LoginAttempted(result="failed", reason=...)`, hace `flush` y `await session.commit()`, y lanza `InvalidCredentials`. El handler de `audit` ya escribió la fila `login` con `result=failed` en esa misma transacción y, por el commit, sobrevive al 401.
5. Éxito: rehace el hash si `needs_rehash`, pone `last_login_at = now` y `failed_login_count = 0`, inserta `RefreshToken(token_hash, expires_at = now + 7 d, user_agent[:255])` con `new_refresh_token()` y emite `LoginAttempted("ok")`. Crea el access JWT (`create_access_token`, 15 min) y devuelve `LoginResult`.
6. El router llama a `set_refresh_cookie` (`apex_refresh`, `HttpOnly`, `SameSite=Strict`, `Path=/api/v1/auth`, `Max-Age=604800`, `Secure` según `COOKIE_SECURE`), pone `Cache-Control: no-store` y devuelve `LoginOut` sin el refresh. `get_session` hace commit al salir.

Refresh (`POST /api/v1/auth/refresh`, público, cookie):
1. Sin cookie: `InvalidRefresh` (401) con `Set-Cookie` que borra la cookie.
2. `hash_opaque_token(cookie)` (un token no ASCII es inválido) y `SELECT ... FOR UPDATE` de la fila `RefreshToken`. Dos refresh simultáneos con el mismo token se serializan: el segundo ve `replaced_by_id` y cae en el reuso.
3. Reuso (`revoked_at` y `replaced_by_id` no nulos): bajo `actor_scope(SYSTEM_USER_ID)`, `revoke_all(user_id)`, `SessionsRevoked(by=SYSTEM_USER_ID, reason="refresh_reuse", revoked=n)`, `await session.commit()` e `InvalidRefresh` con la cookie borrada. El usuario debe iniciar sesión de nuevo en todos sus dispositivos.
4. Token vencido, revocado por logout (sin `replaced_by_id`, no es reuso) o de un usuario que ya no cumple `can_login`: `InvalidRefresh`.
5. Rotación: crea el nuevo `RefreshToken` (7 días) bajo `actor_scope(user.id)`, marca el anterior con `revoked_at` y `replaced_by_id` en la misma transacción y devuelve un access nuevo y la cookie nueva (distinta de la anterior).

Logout (`POST /api/v1/auth/logout`, access válido): revoca solo el refresh de la cookie si pertenece al usuario autenticado; siempre 204 y cookie borrada.

Cambio de contraseña (`POST /auth/me/password`): mantiene viva la sesión de la cookie y revoca las demás (`revoke_all(except_id=...)`); sin cookie revoca todo.

Cada petición autenticada: `current_user` decodifica el access, rechaza `SYSTEM_USER_ID`, pide el principal vigente a la base (rol, bloqueo, baja y `must_change_password` salen de la base, no del token) y solo entonces refresca el keyring si otro proceso rotó llaves. Un bloqueo, una baja o un cambio de rol surten efecto en la siguiente petición.

### 7.2 Activación y restablecimiento (tokens de un solo uso)

- Emisión (`issue_one_time_token`): `new_opaque_token()` (32 bytes, base64url); solo se guarda `hash_opaque_token(token)` en `auth.one_time_tokens.token_hash` (redactado en la auditoría). TTL `activate` 72 h y `reset` 1 h. Antes de insertar, los tokens abiertos del mismo usuario y propósito se cierran con `used_at = now` (por ORM, queda `update` auditado), así a lo sumo hay uno abierto.
- Entrega en v0.1: solo la respuesta de `POST /users` (activación) y de `POST /users/{id}/resend-link` (activación o recuperación, según `link_purpose_for`). La URL es `<FRONT_BASE_URL>/restablecer/<token>` y viaja una sola vez; el front la muestra en un campo de solo lectura y la descarta al cerrar. `forgot` crea el token `reset` pero no lo entrega (no hay canal hasta US-131); el admin lo reemplaza con `resend-link`.
- Consumo (`POST /auth/reset`): token → usable → política → marcado como usado y cambio de contraseña, en una transacción con `FOR UPDATE`. Cualquier fallo del token (inexistente, usado, vencido, usuario bloqueado o borrado) es el mismo 400 `invalid_token`. Un `reset` revoca todas las sesiones; una activación no. Ninguna de las dos inicia sesión.
- Sin enumeración: `forgot` responde siempre 204 con cuerpo vacío; Nginx y la app limitan por IP.
- El token nunca está en la auditoría, en los logs (`redact_text` cubre `/restablecer/<token>`), en el almacenamiento del navegador ni en el log de acceso de Nginx (`access_log off` en esa ruta, `replaceState` en el front, `Referrer-Policy: no-referrer`).

### 7.3 Configuración con versión optimista (N-17)

1. `GET /settings/gym` devuelve la fila o los defaults con `version = 0`.
2. El formulario guarda con `PATCH {value, version}` (la versión que leyó).
3. El service toma `FOR UPDATE` por `key`. Sin fila: exige `version = 0` e inserta con `version = 1` (el hook audita `insert`). Con fila: compara versiones (`version_conflict` 409 si difieren), asigna un `dict` nuevo, `version += 1` y `updated_by` (el hook audita `update` con `before` y `after`).
4. Dos primeros guardados simultáneos: uno inserta; el otro choca con `uq_settings_sections_key`, el `IntegrityError` se atrapa en un savepoint y se traduce a 409.
5. El front, ante el 409, muestra el aviso, no reenvía y ofrece "Recargar".
6. Consumidores: `memberships.service` (Sprint 3) llamará a `settings.service.memberships_policy(session)`; `members` (v0.3) a `current_privacy_version(session)`; `auth.me` a `gym_name(session)`. Nadie importa `settings.models`.

### 7.4 Alta y búsqueda de socios

- Alta: `MemberCreate` → `validate_member_input` → pre-chequeo `id_by_document` → `Member` con `Secret.from_plain` → `flush` dentro de `begin_nested()` → el listener `before_flush` de `core/crypto/types.py` cifra con `aad = id` y llena `document_idx`, `phone_idx` y `email_idx` en el mismo flush → INSERT → el hook escribe `insert` con blobs y `subject_member_id` → `MemberCreated` → respuesta enmascarada calculada desde la entrada. `crypto_ops` recibe `encrypt` e `index` por campo, atribuidos al actor.
- Búsqueda: `classify_query` decide qué índices calcular; `bus.blind_index` (dentro de `bus.batch("index", None)`) los calcula; `UNION` de ids por índice y por `ILIKE` de nombre; la lista nunca descifra (cero filas `decrypt`). El término buscado no se registra: ni en Nginx (`$uri`), ni en Uvicorn (acceso apagado), ni en `RequestLogMiddleware` (solo la plantilla de ruta).

### 7.5 Eventos y suscriptores

- `UserCreated` (ya existe): sin suscriptor; la fila `insert` la deja el hook.
- `LoginAttempted`: lo emite `login` (solo si el correo existe) y lo atiende `audit.service.on_login_attempted`, que escribe una fila `action="login"` sobre `auth.users` con `after = {result, reason?}` y `user_id` del propio usuario.
- `UserLocked` (admin o bloqueo automático): lo atiende `on_user_locked`, que escribe una fila `update` con `after.event = "UserLocked"`; además el hook ya dejó el `update` de `locked_at` (dos filas por bloqueo, a propósito).
- `SessionsRevoked` (admin, lock, delete, refresh_reuse, password_changed, password_reset): lo atiende `on_sessions_revoked`, que escribe una fila `update` con `after.event = "SessionsRevoked"`, `reason` y `revoked`; `user_id` es quien actúa (`SYSTEM_USER_ID` en el reuso y en el bloqueo automático).
- `PasswordChanged`, `MemberCreated` y `PlanCreated`: sin suscriptores en v0.1.
- Todos los handlers corren en la sesión del emisor: si uno falla, la transacción completa se revierte.

### 7.6 Sesión en el front

- Memoria: el access token y el usuario viven solo en el módulo `session.ts` (nada en `localStorage` ni `sessionStorage`). Al recargar la página `RequireAuth` llama una vez a `restoreSession()`: `POST /auth/refresh` (cookie) y `GET /auth/me`; si falla va a `/login?next=<ruta>`.
- Renovación: `core/api/client.ts` ante un 401 con `code === "token_expired"` invoca el gancho registrado, que llama a `refreshAccessToken()` y reintenta la petición una sola vez. Un 401 `unauthorized` limpia la sesión.
- Tres defensas contra el reuso por concurrencia: una sola promesa en curso por pestaña (single-flight); `navigator.locks.request("apex-refresh", ...)` entre pestañas, donde quien obtiene el candado primero mira si llegó un token nuevo por el canal en los últimos segundos; y `BroadcastChannel("apex-auth")` con mensajes `token` (access y vencimiento; nunca el refresh) y `logout`. Sin `navigator.locks` solo rigen la promesa y el canal (decisión 23).
- Cierre: `logout()` llama al API y, en `finally`, limpia la sesión, publica `logout`, vacía el `QueryClient` y navega a `/login`. Un `logout` recibido por el canal limpia la sesión de las demás pestañas.
- `tests/e2e/refresh-two-tabs.spec.ts` (proyecto `stack`): dos pestañas del mismo contexto con el access vencido (reloj del navegador adelantado 16 min) hacen peticiones a la vez y ninguna pierde la sesión; la base muestra un solo refresh rotado y ninguno revocado por reuso.

## 8. Pruebas de arquitectura

Corren en cada gate de slice (A-5). Existentes que se amplían:
- `test_audited_tables.py` (B6, B7, B9): `_cargar_modelos()` tolera módulos sin `models.py` (decisión 21); `REQUIRED_AUDITED_TABLES_V01` (`auth.users`, `auth.one_time_tokens`, `settings.settings_sections` y luego `members.members` y `plans.plans`); `PENDING_AUDITED` para las que llegan después; `auth.refresh_tokens` sigue excluida con su razón.
- `test_no_cross_models.py` (B1): caso explícito de que ningún módulo distinto de `settings` importa `app.modules.settings.models`. Ampliación opcional de `_imports.py` (decisión 4): una regla `private_helper` que prohíbe importar `app.modules.auth.rules` y `app.modules.auth.tokens` desde otro módulo.
- `test_every_route_has_role.py` (B2 a B5): `test_la_lista_blanca_es_la_esperada` no cambia; la prueba de límite de intentos en login y forgot ya existe y ahora se ejerce con rutas reales; se agrega que las 29 rutas del sprint están registradas por método y ruta, y que la genérica `/settings/{section}` se declara después de las tipadas.
- `test_list_routes_use_page_params.py` (B3): recorre `effective_routes(create_app(...))` en vez de `router.routes` (decisión 3).
- `test_banned_imports.py` (B7): usa `find_banned_imports` (imports dinámicos literales) y un control en directorio temporal. `test_ruff_banned_api.py` no cambia.
- `test_core_import_direction.py` (B2): sin cambios; vigila que `core/security` → `core/crypto/keyring` no cree ciclo.
- `test_no_sensitive_in_logs.py` (B7): se implementa (decisión 20).
- `test_error_responses_in_openapi.py` y `test_routes_under_api_v1.py`: sin cambios; cubren las rutas nuevas. `test_no_physical_delete_users.py`: sin cambios; `delete_user` no usa `session.delete`.

Nuevas:
- `test_settings_no_secrets.py` (B1): recorre `SECTION_REGISTRY` y falla si algún campo coincide con `password|secret|api_key|private_key|smtp_pass|vapid`, o si algún esquema no tiene `extra="forbid"`.
- `test_auth_routes.py` (B4): sin `/activation-link`; login y forgot con límite; `/users*` solo admin; públicas exactas.
- `test_members_encrypted_at_rest.py`, `test_no_plaintext_at_rest.py` y `test_import_analyzer.py` (B7).
- `test_list_rows_without_sensitive_fields.py` (B8).
- Opcional, sin dueño en el plan: `test_service_import_graph.py` (lo nombra `CLAUDE.md` y todavía no existe), en versión mínima que verifique que el grafo de imports entre `service.py` es acíclico (`audit → auth → settings`); la lista blanca de pares perezosos llega con el Sprint 3.
- Front: siguen vigentes `tests/unit/no-role-literals.test.ts` y `tests/lint/no-direct-fetch.test.ts`; son nuevas `src/routes.test.ts` (inventario), `src/layouts/layouts.no-fetch.test.ts` y `tests/kit-inventory.test.ts`.

## 9. Fixtures de prueba que faltan (se crean en B1; las de socios en B7 y las de planes en B9)

En `api/tests/conftest.py` (raíz):
- `proveedor_local`, `sin_llaves`, `bus_listo`: se mueven desde `tests/crypto/conftest.py` (que deja de definirlas). Sin cambios de comportamiento.
- `reset_rate_limit` (autouse): `ratelimit.reset_store()` antes y después de cada prueba.
- `reloj`: `set_clock(FrozenClock(...))` con `reset_clock` al terminar; por defecto `2026-10-21T15:00:00Z`.
- `argon2_rapido`: `configure_password_hasher(time_cost=1, memory_cost_kib=8, parallelism=1)`, y restaura los valores por defecto al terminar. Los fixtures de usuarios lo piden.
- `cargador_real`: registra `auth.service.load_active_principal` (el conftest registra el doble al importarse) y devuelve el doble al terminar.
- `app_http(settings_prueba, session, bus_listo, cargador_real, reloj)`:
  - `create_app(settings_prueba, run_migrations_on_startup=False)` sin ejecutar el `lifespan`; llama a `configure_security(settings)` y `configure_provider`;
  - sustituye `db.get_session` con `app.dependency_overrides` por un generador que cede la `session` de la prueba y, al salir, hace `await session.commit()` (libera el savepoint y dispara los listeners de commit como el real, así `crypto_ops` queda escrito) o `await session.rollback()` si hubo excepción;
  - el cliente es `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t")`.
- `usuario_real` (fábrica asíncrona): `crear(role="coach", email=None, password=CLAVE_PRUEBA, member_id=None, activo=True, bloqueado=False, must_change_password=False) -> UsuarioPrueba(user, password, token)`. Inserta el `User` con `hash_password` real bajo `actor_scope(SYSTEM_USER_ID)`, hace `commit` del savepoint y crea el token con `create_access_token(user.id, user.role, user.member_id, clock)`. Se llama después de `configure_security`.
- `cabeceras(usuario) -> dict[str, str]`: `{"Authorization": "Bearer <token>"}`.
- `capturar_eventos(*tipos)`: suscribe una lista y devuelve los eventos. Al terminar quita solo su suscripción (no usa `events.clear_subscribers()`, porque `audit.service` y `auth.service` se registran al importarse y vaciarlo los dejaría sin handlers para el resto de la sesión).
- `dos_sesiones(engine)`: dos `AsyncSession` independientes con commit real para las pruebas de concurrencia (`asyncio.gather`); limpian lo que escriben.

En `api/tests/factories/`:
- `__init__.py`: `FACTORIES` por `esquema.tabla`.
- `users.py`: `make_user(session, **cambios) -> User` (lo usa `usuario_real`) y `make_one_time_token(session, user, purpose, *, expires_in)`, que devuelve el token en claro y la fila.
- `members.py` (B7) y `plans.py` (B9).
- Todas terminan con `await session.commit()`, para que los datos queden fuera del savepoint que una petición puede revertir.

En `web/`:
- `src/test/server.ts`: `fetch` simulado por ruta del API (sin red) y `renderWithProviders(ui, {role, route})` con `QueryClientProvider`, `MemoryRouter` y `RoleProvider`.
- `src/test/session.ts`: `signInAs(role)` para fijar la sesión en memoria sin pasar por el login.
- `tests/e2e/helpers/stack.ts` (W0-1).

## 10. Cierre de la deuda de seguridad del Sprint 1

- **M-1 (subred fija e IP del proxy).** W0-1: red `172.30.0.0/24`, `web` en `172.30.0.10`, `TRUSTED_PROXIES=172.30.0.10`. `test_compose_config.sh` exige que coincidan. Con el proxy confiable único, `client_ip` solo cree en `X-Forwarded-For` de Nginx, que lo fija a `$remote_addr`.
- **M-2 (límite por cuenta, `locked_at`, IPv6 /64).** B2: `ratelimit.enforce("login-account", ...)` 10 por 900 s por correo normalizado (también inexistentes); bloqueo tras 20 fallos consecutivos con `locked_at`, `UserLocked` y `SessionsRevoked`, salvo el último admin activo; clave de IP por /64 en `core/ratelimit`; `cli unlock-user` en B5. Pruebas en `test_login_service.py`, `test_ratelimit.py` y `test_lock_unlock.py`.
- **M-3 (`refresh_keyring` y `limit_req`).** B2: `refresh_current(session)` dentro de `current_user` solo tras validar el token; se quita la dependencia global de `main.py`. W0-1: `limit_req` en `/api/v1/auth/` con 429 en envelope.
- **M-8 (`ADMIN_*` solo en `tools`, `must_change_password`).** W0-1: `.env.seed` solo para `tools`, `.env.example` sin esas variables. B2: `SeedSettings`, migración nueva `0005b_auth_security` (nunca se edita `0004`), `seed_admin` con `must_change_password=true`, `--no-force-change` solo en `dev`. B3: `require_role` devuelve 403 `password_change_required` hasta cambiar la contraseña; `change_password`, `reset` y activación lo ponen en `false`.
- **L-1 (`no-store` y `form-action`).** W0-1: `Cache-Control: no-store` en `/api/` y `form-action 'self'` en la CSP del index (y `'none'` en la del api); `auth/cookies.no_store` repite `no-store` en las rutas de `auth` y `users`. Se verifica en `test_nginx_conf.sh` y `headers.sh`.
- **L-4 (`--as` solo con usuarios activos).** B2: `active_user_id_by_email` exige `user_status == "active"` y excluye `SYSTEM_USER_ID`; `resolve_actor` sale con 2 y mensaje explícito.
- **L-5 (tope de contraseña).** B2: `PASSWORD_MAX_LENGTH = 128` en `core/security`, razón `too_long`, y `max_length=128` en los schemas de entrada.
- **L-8 (cookie).** B2: `HttpOnly`, `SameSite=Strict`, `Path=/api/v1/auth`, `Max-Age` de 7 días y `Secure` según `COOKIE_SECURE`; la cookie se borra con los mismos atributos en el 401 de `refresh` y en el logout; aviso de arranque con `COOKIE_SECURE=false` en producción (decisión 13).
- No tocan este sprint: M-7 (separar `apex_owner` de `apex_app`, antes de v0.2), L-3, L-7 (quedan con su dueño del cuaderno del Sprint 1).

Revisión del `security-reviewer` al cerrar el sprint (definición de hecho del plan): cookie `HttpOnly`/`SameSite`/`Secure` según `COOKIE_SECURE`; enlaces de un solo uso guardados como hash; `forgot` no revela correos; ninguna lista devuelve datos cifrados; el coach recibe 403 en todas las rutas de admin; los logs no contienen correos ni tokens.

## 11. Riesgos, puntos abiertos y tareas de documentación

Riesgos:
1. **El commit explícito en el login fallido** rompe el patrón de "una transacción por petición". Se limita a `login` y `refresh` (reuso), con pruebas que simulan el `rollback` de `get_session`. Si SQLAlchemy cambiara el comportamiento de `commit()` dentro de `session.begin()`, el plan B es devolver un resultado de fallo desde el service y que el router haga el commit antes de lanzar.
2. **Dos filas por bloqueo** (hook y evento) pueden confundir al leer el historial; el detalle de auditoría las distingue por `after.event`.
3. **Reuso por reintento de red** (decisión 28).
4. **El enlace de activación se entrega a mano**; mitigaciones: 72 h, un solo uso, advertencia en pantalla, `resend-link` invalida el anterior.
5. **`/socios/:id` no existe hasta el Sprint 3**: el enlace "Ver socio existente" del 409 da "No encontrada" hasta US-073 (decisión 34).
6. **9 slices de front en un sprint**: F1 y F2 antes de cualquier página; el gate acota lint y tsc a los archivos del slice (A-01).
7. **Pruebas de concurrencia con dos sesiones reales** (`dos_sesiones`) escriben fuera del savepoint: deben limpiar lo que crean y no compartir correos con otras pruebas.
8. **La prueba de rendimiento** cifra unas 8.000 operaciones del bus; si el gate se vuelve lento se baja la siembra a 1.000 socios con solo documento (los otros campos nulos) sin cambiar lo que mide.

Puntos abiertos para la persona (preguntar solo si se quiere cambiar la recomendación):
- Decisión 16: columna `document_type` en `0006_members` (recomendado: sí).
- Decisión 32: unicidad de plan sin distinguir mayúsculas (recomendado: sí).
- Decisión 10: umbrales de bloqueo (10 por 900 s, bloqueo a los 20) y excepción del último admin.
- Decisión 22: `@hookform/resolvers` como dependencia.

Documentación que cambia con el sprint (en los checkpoints correspondientes):
- `docs/ddd/DECISIONES.md`: sección "Sprint 2" con las decisiones aceptadas de la sección 1.
- `CLAUDE.md` (estructura): `modules/audit` con `router.py` vacío; `auth/{rules,tokens,cookies}.py`; `core/validators.py`; `.env.seed`; la regla "un router plano por módulo".
- `docs/BRECHAS.md` y `docs/design/ROUTES.md`: ruta `/cambiar-clave`; `Usuarios` sin nombre; `Socio_Form` con nombres y apellidos y sin foto, firma ni portal; `Config` en pestañas.
- `docs/ddd/09_sprint_plan/SPRINT-02.md`: la demo dice `password_hash` como `***` y `table_name` `auth.users`; la rama es `feat/sprint-02-identidad-config-socios-planes`.
- `docs/ddd/05_service_design.md`: `Principal.must_change_password`, `GET /auth/me` con `gym_name`, rutas tipadas de settings.
- Runbook: seed con `.env.seed` y borrado posterior, `cli unlock-user`, `COOKIE_SECURE`, reuso de refresh.
- `docs/scratch/sprint-02.md`: cuaderno del sprint, un bloque por slice (no es parte de este plano).

Evidencia que el sprint debe dejar (definición de hecho): 9 checkpoints de backend, 9 de front (F4 en dos), `run-gates.sh` en verde con cobertura de `app` de 80 % o más, `pytest tests/architecture -q`, ciclo de Alembic sobre `0007_plans` (cadena: 0004 → 0005_settings → 0005b_auth_security → 0006_members → 0007_plans), `docs/openapi.json` y `types.ts` regenerados, E2E de `login`, `users-activation`, `role-guards`, `settings-gym`, `panel-layout`, `layouts`, `kit` y `refresh-two-tabs`, y el smoke con evidencia SQL (un blob en `members.members` y filas `login`, `insert` y `update` con `password_hash` como `***`).
