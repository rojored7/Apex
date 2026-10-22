# Sprint 2 · Identidad, configuración, shell del front, primeros socios y planes

- Versión: v0.1.
- Épicas que cubre:
  - EP-04, el resto;
  - EP-05, salvo US-056;
  - EP-06, el resto;
  - US-107 de EP-11;
  - US-031 de EP-02;
  - la base de EP-07 y EP-08.
- Tamaño: 26 historias, 87 puntos, 374 h relativas.
- Rama: `feat/sprint-02-identidad-config-socios-planes` (S2-D48; el borrador decía `feat/sprint-02-identidad-socios-planes`).
- Historias del sprint: US-031, US-042, US-043, US-044, US-045, US-046, US-047, US-048, US-049, US-050, US-051, US-052, US-053, US-054, US-055, US-057, US-058, US-061, US-062, US-067, US-068, US-069, US-070, US-078, US-079, US-107.

## Objetivo

Que el admin y el coach entren con su rol y vean solo lo que les corresponde.

El admin, además:
- administra usuarios con enlaces de activación;
- configura el gimnasio, la política de privacidad y los parámetros de membresías.

Los dos registran y buscan socios. El documento, el teléfono y el correo quedan cifrados por el bus. El admin crea los planes que se venden en el Sprint 3.

## Demo al final del sprint

Ocho puntos. Las seis comprobaciones de V7 del plan (`docs/ddd/blueprints/sprint-02-plan.md`, sección 7) están en los puntos 4 a 7; los puntos 1, 2, 3 y 8 ya estaban en el archivo.

1. `docker compose up -d --build` y abrir `http://localhost:${WEB_PORT:-80}` (en el entorno local, `http://localhost:8180`). El login se ve bien en tema claro (siempre claro por `AccessLayout`, F3); el tema oscuro se comprueba en Inicio.
2. Entrar como admin y crear un coach con `POST /api/v1/users`. La respuesta trae `activation_url` (`<FRONT_BASE_URL>/restablecer/<token>`), válido por 72 h. Abrirlo en otra ventana, fijar una contraseña de 12 o más caracteres (la página vuelve a `/login` sin iniciar sesión, S2-D18) y entrar como coach.
3. El coach no ve Usuarios ni Configuración. Si entra a `/sistema/configuracion` por la URL, ve "Sin permiso"; la API responde 403 en las rutas de `settings` y `users`.
4. Límite de intentos y sesiones:
   - el sexto intento fallido en un minuto responde 429 `rate_limited` (`LOGIN_IP_LIMIT=5`);
   - reusar un refresh ya rotado fuera de la gracia de 10 s revoca todas las sesiones del usuario (N-13, M-2); dentro de la gracia responde 401 `invalid_refresh` sin revocar nada.
5. El admin guarda los datos del gimnasio, publica una versión de la política y fija `expiring_days = 7` (rango de 1 a 30). El TopBar del coach muestra `gym_name`, que viene de `GET /api/v1/auth/me`.
6. Registrar un socio con CC 1.020.304.417 y buscarlo por documento, por teléfono y por nombre.
   - `SELECT document, document_idx FROM members.members` muestra un blob `apx1.` y un HMAC.
   - Registrar otro socio con el mismo documento responde 409 `member_document_duplicated` con `existing_id`.
7. Crear el plan "Mensual": $ 120.000, 30 días.
   - Un nombre repetido, también en mayúsculas o con espacios en los extremos, responde 409 `plan_name_duplicated` con `existing_id`.
   - El coach solo lista planes activos: `GET /api/v1/plans?active=true` responde 200 y `GET /api/v1/plans` sin ese filtro responde 403.
8. La auditoría muestra filas `login`, `insert` y `update` sobre `auth.users` (`table_name = 'auth.users'`), con `password_hash` como `***`.

## Dependencias de sprints anteriores

- **Sprint 0:**
  - `create_app`;
  - `0001`;
  - envelope de errores;
  - logging;
  - esqueleto de `web/`.
- **Sprint 1:**
  - US-015 y US-016: auditoría y hook;
  - US-019, US-021 y US-022;
  - US-023 a US-029: bus;
  - US-032 a US-039: seguridad y llave JWT en el volumen `keys`;
  - US-041: `0004`, cargador real y seed;
  - el kit: US-040, US-059, US-060 y US-063 a US-066.

Decisiones que aplica:
- N-10, N-11, N-12, N-13, N-17, N-18, N-19, N-20 y N-22;
- refinamientos de US-057, US-061 y US-062;
- la contradicción de US-107 se resuelve así: el login emite `LoginAttempted` y US-107 se suscribe a ese evento.

## Historias en orden de ejecución

Patrón de v0.1: en cada slice van primero el Rojo (stubs y pruebas), después el Verde y al final el gate con los archivos del slice más `tests/architecture`. Recién entonces el checkpoint.

### Wave 0 · Infraestructura (`devops-wsl2-docker`)

- **Slice S2-W0-1 · Playwright contra el stack y Nginx para los enlaces.** Incluye las tareas DevOps de US-068 y US-048.
  - Job de CI que levanta `infra/compose.yml --build` y corre Playwright, con capturas en 320, 768, 1024 y 1440 px, en claro y en oscuro.
  - Nginx deja de registrar las query strings de `/restablecer/` y el parámetro `q` de `/members`.
  - Gate: `bash scripts/ci/compose-smoke.sh` y `bash -n` sobre los scripts.

### Waves 3a/3b · Backend, alternadas por slice

- **Slice S2-B1 · Configuración del gimnasio.** Historias: US-054, US-055 (backend), US-057 y US-058.
  - **Rojo:**
    - `tests/settings/test_settings_rules.py`, `test_settings_service.py` y `test_settings_router.py`;
    - `tests/settings/test_gym_schema.py` y `test_gym_router.py`;
    - `tests/settings/test_privacy_schema.py`, `test_privacy_service.py` y `test_privacy_router.py`;
    - `tests/settings/test_memberships_policy.py`, `test_memberships_schema.py` y `test_memberships_router.py`;
    - `tests/architecture/test_settings_no_secrets.py`.
  - **Verde:**
    - **migración `0005_settings`**, sin filas sembradas;
    - secciones `gym`, `privacy` y `memberships`, con los rangos de N-18;
    - 409 `version_conflict` y 404 `section_not_available`;
    - `memberships_policy()` y `current_privacy_version()`.
  - **Gate:** `slice-gate.sh settings <archivos de Rojo>` y el ciclo de Alembic.
- **Slice S2-B2 · Sesión.** Historias: US-042, US-043 y US-044.
  - **Rojo:**
    - `tests/auth/test_pure_login.py`, `test_login_service.py` y `test_login_router.py`;
    - `tests/auth/test_pure_refresh.py`, `test_refresh_service.py` y `test_refresh_router.py`;
    - `tests/auth/test_logout_service.py` y `test_logout_router.py`.
  - **Verde:**
    - login con `rate_limit("login")` y el evento `LoginAttempted`;
    - `last_login_at` en `__audit_exclude__`;
    - refresh en cookie HttpOnly, con rotación; reusar uno rotado revoca todo;
    - logout.
  - **Gate:** `slice-gate.sh auth <archivos de Rojo>`.
- **Slice S2-B3 · Mi cuenta y usuarios.** Historias: US-045, US-046 y US-047.
  - **Rojo:**
    - `tests/auth/test_pure_password_policy.py`, `test_change_password.py` y `test_me_router.py`;
    - `tests/auth/test_pure_user_status.py`, `test_list_users.py` y `test_users_list_router.py`;
    - `tests/auth/test_pure_links.py`, `test_create_user.py` y `test_create_user_router.py`.
  - **Verde:**
    - `GET /auth/me` con `gym_name` (respaldo: "APEX");
    - cambiar la contraseña revoca las demás sesiones;
    - lista de usuarios;
    - crear usuario con enlace de 72 h.
  - **Gate:** `slice-gate.sh auth <archivos de Rojo>`.
- **Slice S2-B4 · Activación, recuperación y reenvío.** Historias: US-048 y US-052.
  - **Rojo:**
    - `tests/auth/test_pure_one_time_token.py`, `test_reset_forgot.py` y `test_reset_forgot_router.py`;
    - `tests/auth/test_resend_link.py` y `test_resend_link_router.py`;
    - `tests/architecture/test_auth_routes.py`.
  - **Verde:**
    - `forgot`, `reset` y `activate`;
    - 400 `invalid_token`;
    - `resend-link` invalida el enlace anterior.
  - **Gate:** `slice-gate.sh auth <archivos de Rojo>`.
- **Slice S2-B5 · Ciclo de vida del usuario.** Historias: US-049, US-050 y US-051.
  - **Rojo:**
    - `tests/auth/test_pure_last_admin.py`, `test_update_delete_user.py` y `test_user_detail_router.py`;
    - `tests/auth/test_pure_lock.py`, `test_lock_unlock.py` y `test_lock_router.py`;
    - `tests/auth/test_revoke_sessions.py` y `test_revoke_sessions_router.py`.
  - **Verde:**
    - edición y baja lógica;
    - nunca queda el sistema sin al menos un admin;
    - bloquear y desbloquear;
    - cerrar sesiones;
    - eventos `UserLocked` y `SessionsRevoked`.
  - **Gate:** `slice-gate.sh auth <archivos de Rojo>`.
- **Slice S2-B6 · Auditoría de eventos de seguridad.** Historia: US-107.
  - **Rojo:**
    - `tests/audit/test_security_events.py`;
    - `tests/auth/test_router_login_audit.py`;
    - `tests/audit/test_reveal_entry.py`, que prueba `audit.record(action='reveal', ...)` directo, con un socio de fábrica. **No lleva `skip`** (M-4). US-074 la reutiliza en el Sprint 3.
  - **Verde:**
    - suscriptores de `LoginAttempted`, `UserLocked` y `SessionsRevoked`;
    - un correo inexistente solo deja log y cuenta para el límite de intentos (N-31).
  - **Gate:** `slice-gate.sh audit <archivos de Rojo>`.
- **Slice S2-B7 · Registrar socio y pruebas de cifrado en reposo.** Historias: US-069 y US-031.
  - **Rojo:**
    - `tests/members/test_member_rules.py`, `test_service_create.py` y `test_router_create.py`;
    - `tests/architecture/test_members_encrypted_at_rest.py`;
    - `tests/architecture/test_no_plaintext_at_rest.py`;
    - `tests/architecture/test_import_analyzer.py`;
    - extensión de `tests/core/test_logging_redact.py` con un socio real. Cierra la parte de US-069 de la tarea T8 de US-018 (A-6).
  - **Verde:**
    - **migración `0006_members`**, sin `*_hint`;
    - índice único parcial `document_idx`;
    - `members.service`: `create`, `ref`/`get_ref`, `ensure_exists`, `id_by_document`, `count` y `warnings: []`;
    - fábrica en `api/tests/factories/`.
  - **Gate:**
    - `slice-gate.sh members` con sus archivos;
    - `slice-gate.sh core/logging tests/core/test_logging_redact.py`;
    - ciclo de Alembic.
    - `test_members_encrypted_at_rest.py` bloquea el checkpoint porque `tests/architecture` corre siempre (A-5).
- **Slice S2-B8 · Buscar y listar socios.** Historia: US-070.
  - **Rojo:**
    - `tests/members/test_classify_query.py`, `test_service_list.py` y `test_router_list.py`;
    - `tests/members/test_list_perf.py` (`-m perf`);
    - `tests/architecture/test_list_rows_without_sensitive_fields.py`.
  - **Verde:**
    - búsqueda por índice ciego y por nombre;
    - `search_ids` y `names_for`, que incluyen los dados de baja y el sexo.
  - **Gate:** `slice-gate.sh members <archivos de Rojo>`.
- **Slice S2-B9 · Crear y listar planes.** Historias: US-078 y US-079.
  - **Rojo:**
    - `tests/plans/test_validate_plan.py`, `test_service_create.py` y `test_router_create.py`;
    - `tests/plans/test_scope_rules.py`, `test_service_list.py` y `test_router_list.py`.
  - **Verde:**
    - **migración `0007_plans`**;
    - `get`, `get(for_share=True)`, `get_including_deleted` y `names_for`;
    - el coach solo consulta con `active=true`.
  - **Gate:** `slice-gate.sh plans <archivos de Rojo>` y el ciclo de Alembic.

### Waves 5a/5b · Front, alternadas por slice

En el front, el gate acota lint y tsc a los archivos que toca el slice (A-01).

- **Slice S2-F1 · Layouts.** Historias: US-061 y US-062.
  - **Rojo:**
    - stubs y pruebas en `src/layouts`, `src/shared/ui/TopBar` y `src/shared/ui/SideNav`;
    - `tests/e2e/panel-layout.spec.ts` y `tests/e2e/layouts.spec.ts`.
  - **Verde:**
    - `PanelLayout`, `TopBar` y `SideNav`, con `useCan`;
    - `PortalLayout` con 5 pestañas, `GymLayout` y `TvLayout`.
  - **Gate:** `slice-gate.sh web/layouts` y `slice-gate.sh web/shared`, cada uno con sus archivos.
- **Slice S2-F2 · Rutas y guardas.** Historias: US-067 y US-053.
  - **Rojo:**
    - `src/routes.test.ts` y pruebas en `src/config`;
    - `tests/e2e/role-guards.spec.ts`.
  - **Verde:**
    - `routes.tsx` e `isRouteEnabled`;
    - `RequireRole`, que muestra "Sin permiso";
    - `homeFor`.
  - **Gate:** `slice-gate.sh web/app <archivos de Rojo>`.
- **Slice S2-F3 · Login, refresh y logout.** Historias: US-042, US-043 y US-044 (front).
  - **Rojo:**
    - pruebas en `src/features/auth` y `src/core/auth`;
    - `src/shared/ui/TopBar.logout.test.tsx`;
    - `tests/e2e/login.spec.ts`.
  - **Verde:**
    - `LoginPage`;
    - `session.ts`, con el access token solo en memoria;
    - canal `apex-auth` para coordinar pestañas;
    - logout.
  - **Gate:** `slice-gate.sh web/auth <archivos de Rojo>`.
- **Slice S2-F4a · Mi cuenta, alta, activación y lista de usuarios.** Historias: US-045, US-046, US-047 y US-048 (front). (M-3)
  - **Rojo:**
    - pruebas en `src/features/auth/components` y `src/features/auth/pages`;
    - `src/features/system/pages/UsersPage.test.tsx`;
    - `src/features/system/components/NewUserPanel.test.tsx`;
    - `tests/e2e/users-activation.spec.ts`.
  - **Verde:**
    - panel "Mi cuenta";
    - páginas de activar y restablecer;
    - lista y alta de usuarios.
  - **Gate:** `slice-gate.sh web/auth` y `slice-gate.sh web/system`, cada uno con sus archivos. Checkpoint propio.
- **Slice S2-F4b · Gestión de usuarios.** Historias: US-049, US-050, US-051 y US-052 (front). (M-3)
  - **Rojo:**
    - pruebas en `src/features/system/pages` para editar, bloquear y cerrar sesiones;
    - `src/features/system/components/LinkModal.test.tsx`.
  - **Verde:**
    - editar y dar de baja;
    - bloquear y desbloquear;
    - cerrar sesiones;
    - reenviar el enlace.
  - **Gate:** `slice-gate.sh web/system <archivos de Rojo>`. Checkpoint propio.
- **Slice S2-F5 · Configuración.** Historias: US-055, US-057 y US-058 (front).
  - **Rojo:**
    - `src/features/system/components/PrivacySettingsForm` y `MembershipsSettingsForm`;
    - `tests/e2e/settings-gym.spec.ts`.
  - **Verde:**
    - `Config` con tres pestañas;
    - `useSettingsSection`;
    - manejo del 409.
  - **Gate:** `slice-gate.sh web/system <archivos de Rojo>`.
- **Slice S2-F6 · Socios: alta y lista.** Historias: US-069 y US-070 (front).
  - **Rojo:** pruebas en `src/features/members`.
  - **Verde:**
    - `Socio_Form`, que muestra los errores por campo y enlaza al socio existente;
    - `Socios_Lista`.
  - **Gate:** `slice-gate.sh web/members <archivos de Rojo>`.
- **Slice S2-F7 · Planes: alta y lista.** Historias: US-078 y US-079 (front).
  - **Rojo:**
    - `src/features/plans/pages/PlansPage.test.tsx`;
    - pruebas del formulario de alta.
  - **Verde:** `Planes` con lista y `PlanForm`.
  - **Gate:** `slice-gate.sh web/plans <archivos de Rojo>`.
- **Slice S2-F8 · Temas, accesibilidad y capturas.** Historia: US-068.
  - **Rojo:**
    - pruebas en `src/core/theme`;
    - `tests/kit-inventory.test.ts`;
    - `tests/e2e/kit.spec.ts`.
  - **Verde:**
    - conmutador de tema;
    - axe sobre todo el kit;
    - capturas de referencia.
  - **Gate:** `slice-gate.sh web/core <archivos de Rojo>` y `npx playwright test tests/e2e/kit.spec.ts`.

### Validación del sprint

- E2E contra el stack:
  - `login.spec.ts`;
  - `users-activation.spec.ts`;
  - `role-guards.spec.ts`;
  - `settings-gym.spec.ts`;
  - `panel-layout.spec.ts`;
  - `layouts.spec.ts`;
  - `kit.spec.ts`.
- E2E de refresh con dos pestañas.
- Prueba de rendimiento con 1.000 socios (`-m perf`).
- **Paso humano:** push de la rama y PR.

## Migraciones que aplica

Cadena de cuatro migraciones, con un solo head (`alembic heads`):

- `0005_settings` (US-054), `down_revision = 0004_auth`.
- `0005b_auth_security` (S2-D9), `down_revision = 0005_settings`: columnas de `auth.users` y `auth.refresh_tokens.family_started_at`.
- `0006_members` (US-069), `down_revision = 0005b_auth_security`.
- `0007_plans` (US-078), `down_revision = 0006_members`.

## Endpoints que expone

29 operaciones nuevas, verificadas contra `docs/openapi.json`. No cuentan `GET /health` ni `GET /api/v1/health`, que son del Sprint 0.

- **Públicos, sin Bearer (5):** `POST /api/v1/auth/login` (límites por IP y por cuenta); `POST /api/v1/auth/refresh` (cookie `apex_refresh`); `POST /api/v1/auth/logout` (por cookie, siempre 204; S2-D35); `POST /api/v1/auth/forgot` (siempre 204, no escribe en v0.1; S2-D36); `POST /api/v1/auth/reset` (204, sin sesión).
- **Cualquier rol con sesión (2):** `GET /api/v1/auth/me` (con `gym_name` y `must_change_password`); `POST /api/v1/auth/me/password` (200 `AccessTokenOut`; S2-D46).
- **Admin, usuarios (9):** `GET` y `POST /api/v1/users`; `GET`, `PATCH` y `DELETE /api/v1/users/{user_id}`; `POST /api/v1/users/{user_id}/lock`, `/unlock`, `/resend-link` y `/revoke-sessions`. No hay `/activation-link` (N-12).
- **Admin, configuración (8):** `GET` y `PATCH` de `/api/v1/settings/gym`, `/settings/privacy` y `/settings/memberships` (rutas tipadas, declaradas antes que la genérica); `GET` y `PATCH /api/v1/settings/{section}`, que responde 404 `section_not_available` para cualquier otra clave (S2-D15).
- **Admin y coach, socios (2):** `GET` y `POST /api/v1/members`.
- **Planes (3):** `POST /api/v1/plans` (admin); `GET /api/v1/plans` y `GET /api/v1/plans/{plan_id}` (admin y coach; el coach solo ve los activos, S2-D26).

`PATCH`, la activación, la desactivación y la baja de planes entran en el Sprint 4A con US-080, US-081 y US-082.

## Tests de arquitectura que deben pasar

Corren en cada gate de slice (A-5).

- Los de los Sprints 0 y 1.
- `test_settings_no_secrets.py` (US-054 y US-055).
- `test_no_cross_models.py`, ampliada a `settings`.
- `test_auth_routes.py` (US-052).
- `test_audited_tables.py`, ampliada (US-107).
- `test_members_encrypted_at_rest.py` (US-069).
- `test_no_plaintext_at_rest.py`, `test_import_analyzer.py` y `test_banned_imports.py`, ampliadas (US-031).
- `test_list_rows_without_sensitive_fields.py` (US-070).

## Riesgos y mitigación

1. [HIGH] US-069 fija con datos reales el índice único, el formato del blob y la normalización.
   - Mitigación: US-031 entra en el mismo slice, `test_members_encrypted_at_rest.py` corre en cada gate y no se cargan socios reales antes del release.
2. [MEDIUM] Con varias pestañas abiertas, el refresh puede cerrar sesiones legítimas.
   - Mitigación: `BroadcastChannel` (`apex-auth`) y un E2E con dos pestañas.
3. [MEDIUM] La matriz de permisos del front puede no coincidir con la del API.
   - Mitigación: `role-guards.spec.ts` y pruebas de router que esperan 403.
4. [LOW] Durante los Sprints 2 y 3 no se puede editar ni desactivar un plan.
   - Mitigación: no hay datos reales todavía; en desarrollo se recrea la base.
5. [MEDIUM] Es el sprint con más trabajo de front (9 slices).
   - Mitigación: el shell (F1 y F2) va antes que cualquier página, y el gate acota lint y tsc a los archivos del slice.

## Trazabilidad: historia → slice → checkpoint

Checkpoints tomados de `git log --oneline 482295f..HEAD`. El front se fusionó desde el worktree del agente; en la columna de front, el hash del merge va entre paréntesis cuando existe. `W0-1` es la infraestructura compartida (`cab02f2`).

| Historia | Backend: slice → checkpoint | Front: slice → checkpoint |
|---|---|---|
| US-031 | B7 → `f85f24e` | — |
| US-042 | B2 → `0b1bfbd` | F3 → `f640248` (merge `07465fc`) |
| US-043 | B2 → `0b1bfbd` | F3 → `f640248` (merge `07465fc`) |
| US-044 | B2 → `0b1bfbd` | F3 → `f640248` (merge `07465fc`) |
| US-045 | B3 → `d287666` | F4a → `20673de` (merge `7324e6e`) |
| US-046 | B3 → `d287666` | F4a → `20673de` (merge `7324e6e`) |
| US-047 | B3 → `d287666` | F4a → `20673de` (merge `7324e6e`) |
| US-048 | B4 → `6240359`; W0-1 (Nginx, enlaces) → `cab02f2` | F4a → `20673de` (merge `7324e6e`) |
| US-049 | B5 → `3597950` | F4b → `aefaaba` (merge `089adc8`) |
| US-050 | B5 → `3597950` | F4b → `aefaaba` (merge `089adc8`) |
| US-051 | B5 → `3597950` | F4b → `aefaaba` (merge `089adc8`) |
| US-052 | B4 → `6240359` | F4b → `aefaaba` (merge `089adc8`) |
| US-053 | — | F2 → `8977012` (merge `17f2000`) |
| US-054 | B1 → `e0ad2d9` | — |
| US-055 | B1 → `e0ad2d9` | F5 → `8136ef1` (merge `ba984b7`) |
| US-057 | B1 → `e0ad2d9` | F5 → `8136ef1` (merge `ba984b7`) |
| US-058 | B1 → `e0ad2d9` | F5 → `8136ef1` (merge `ba984b7`) |
| US-061 | — | F1 → `cfbfb88` (merge `17f2000`) |
| US-062 | — | F1 → `cfbfb88` (merge `17f2000`) |
| US-067 | — | F2 → `8977012` (merge `17f2000`) |
| US-068 | W0-1 → `cab02f2`; V4 (perfil E2E del borde, job `e2e-stack`) → `961e0d6` | F8 → `2972bb3` (merge `17f2000`); V4 (specs del stack, `PageHeader` a 320 px) → `11cf7e9` |
| US-069 | B7 → `f85f24e` | F6 → `571765f` (merge `e1d659b`) |
| US-070 | B8 → `3e7ec24` | F6 → `571765f` (merge `e1d659b`) |
| US-078 | B9 → `5df518c` | F7 → `e662449` (merge `981836a`) |
| US-079 | B9 → `5df518c` | F7 → `e662449` (merge `981836a`) |
| US-107 | B6 → `0fe9df3` | — |

US-053, US-061, US-062 y US-067 son solo de front; US-031 y US-107 son solo de backend. US-078 y US-079 tienen backend (B9) y front (F7, fusionado en `981836a`; `/planes` ya carga la página en `routeTable.ts`).

## Definición de hecho del sprint



- 9 slices de backend y 9 de front confirmados con `checkpoint-commit.sh`.
- `run-gates.sh` en verde:
  - cobertura global de `app` en 80 % o más, con el `omit` de coverage documentado (M-6; pytest-cov no tiene `--cov-omit`);
  - front: lint, tsc, test y build.
- `cd api && uv run pytest tests/architecture -q` en verde.
- Ciclo de Alembic sobre `0007`.
- `docs/openapi.json` y los tipos del front regenerados.
- Los E2E de la validación en verde.
- Smoke con evidencia SQL: un blob en `members.members` y filas de auditoría.
- Seguridad (`security-reviewer`):
  - cookie HttpOnly, con `SameSite` y `Secure` según `COOKIE_SECURE`;
  - enlaces de un solo uso guardados como hash;
  - `forgot` no revela qué correos existen;
  - ninguna lista devuelve datos cifrados;
  - el coach recibe 403 en todas las rutas de admin;
  - los logs no contienen correos ni tokens.
- **Paso humano:** push, PR con CI en verde y merge.
- `verify-delivery`.

## Estado al cierre del sprint (documentación)

Actualizado con `git log` hasta `11cf7e9`. Commits que no son checkpoints de slice: `4cac40b` (salto de línea en `NewUserPanel.module.css`), `42c8595` (gitleaks), `b960086` y `434d82e` (documentación).

- **Slices:** los 9 de backend (B1 a B9) y los 9 de front (F1 a F8, con F4 en F4a y F4b) tienen checkpoint. F7 (Planes: alta y lista) es `e662449`, fusionado en `981836a`; `/planes` ya carga `PlansPage` (`load` en `routeTable.ts`) y US-078 y US-079 tienen backend y front.
- **Validación V2 a V9 en verde** (`docs/scratch/sprint-02.md`, "Validación del sprint"; decisiones en `DECISIONES.md`, S2-V). Checkpoints de la validación: `961e0d6` (perfil E2E del borde con `infra/compose.e2e.yml` y job `e2e-stack` con topes y admin del seed) y `11cf7e9` (`PageHeader` sin desborde a 320 px, specs del stack reparadas y evidencia).
  - V4: `--project=stack` con 29 ok y 0 fallos en dos corridas seguidas; `--project=preview` con 101 ok.
  - V5: pruebas `perf` en verde (búsqueda por documento con 1.000 socios en 12,1 ms; 20 logins fallidos concurrentes con p95 de 0,399 s).
  - V9: `run-gates.sh` con `-m "not perf"` en verde: 1.856 pruebas del api, 4 saltadas, 3 deseleccionadas, cobertura de `app` del 95,56 %; front con 1.676 pruebas y 99,71 % de líneas.
- **Revisión de Fase 4 en curso** (cuatro informes: general, seguridad, Python y TypeScript; resumen en `docs/scratch/sprint-02.md`, "Revisión de Fase 4", y decisiones en `DECISIONES.md`, "Revisión de Fase 4 del Sprint 2"). El backend, el front y la CI con la documentación corrigen en paralelo; el orquestador corre `run-gates.sh` tras fusionar las tres ramas. Falta el paso humano: push, PR con CI en verde y merge.

### Cierre final

- Revisión de Fase 4 corregida en `da97f11` (backend), `dd36384` (front) y `fb2fece`/`31d8f86` (CI y docs), fusionadas en `8aed5fa` y `523d164`, integración en `2e393cd`; revalidación final en `b6650b5`.
- Números finales: api 1.987 pruebas (4 saltadas, 3 `perf` aparte en verde), cobertura 95,70 %; front 1.763 pruebas, 99,68 % de líneas, build en verde; E2E `stack` 29 de 29 en dos corridas, `preview` 101; gates, pre-commit, licencias, auditorías de dependencias, gitleaks e imagen en verde.
- Smoke en vivo del cierre (HEAD `b6650b5`, por Nginx `:8180`, admin del `.env.seed`): `GET /settings/memberships` 200 versión 12 → `PATCH /settings/memberships` (ruta genérica) 200 versión 13 con `expiring_days = 7` y `Cache-Control: no-store`; el mismo PATCH con la versión vieja 409 `version_conflict`; `GET /plans` 200 (17 planes) → `GET /plans/{id}` 200 con el mismo nombre y `no-store`; `GET /plans/{uuid inexistente}` 404 `plan_not_found`; `POST /auth/me/password` 200 con `access_token`, `expires_in`, `token_type`; con 1,2 s entre el login y el cambio, `GET /auth/me` con el access viejo 401 `unauthorized` (H-3) y con el nuevo 200; segundo cambio para revertir 200; login final con la contraseña original 200. V9 del front sobre el árbol fusionado: 110 archivos, 1.763 pruebas, cobertura 99,68 % de líneas, `npm run build` en verde (main 463,25 kB, 142,49 kB gzip).
- Nota a la demo, punto 1: el login se muestra siempre en tema claro (`AccessLayout` fuerza claro, F3); el tema oscuro se comprueba en Inicio y en el panel (capturas de `captures.spec.ts`).
- Pendiente humano (V12): push de la rama, PR con los seis jobs de CI en verde y merge. El orquestador intenta el push.
