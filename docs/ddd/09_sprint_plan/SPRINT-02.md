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
- Rama: `feat/sprint-02-identidad-socios-planes`.
- Historias del sprint: US-031, US-042, US-043, US-044, US-045, US-046, US-047, US-048, US-049, US-050, US-051, US-052, US-053, US-054, US-055, US-057, US-058, US-061, US-062, US-067, US-068, US-069, US-070, US-078, US-079, US-107.

## Objetivo

Que el admin y el coach entren con su rol y vean solo lo que les corresponde.

El admin, además:
- administra usuarios con enlaces de activación;
- configura el gimnasio, la política de privacidad y los parámetros de membresías.

Los dos registran y buscan socios. El documento, el teléfono y el correo quedan cifrados por el bus. El admin crea los planes que se venden en el Sprint 3.

## Demo al final del sprint

1. `docker compose up -d --build` y abrir `http://localhost:${WEB_PORT:-80}`. El login se ve bien en tema claro y en tema oscuro.
2. Entrar como admin y crear un coach. La respuesta trae el enlace de activación, válido por 72 h. Abrirlo en otra ventana, fijar una contraseña de 12 o más caracteres y entrar como coach.
3. El coach no ve Usuarios ni Configuración. Si entra a `/sistema/configuracion` por la URL, ve "Sin permiso".
4. Límite de intentos y sesiones:
   - el sexto login fallido en un minuto responde 429;
   - reusar un refresh ya rotado revoca todas las sesiones del usuario (N-13).
5. El admin guarda los datos del gimnasio, publica la versión de la política y fija `expiring_days = 7`. El TopBar del coach muestra `gym_name`, que viene de `GET /auth/me`.
6. Registrar un socio con CC 1.020.304.417 y buscarlo por documento, por teléfono y por nombre.
   - `SELECT document, document_idx FROM members.members` muestra un blob `apx1.` y un HMAC.
   - Registrar otro socio con el mismo documento responde 409 con `existing_id`.
7. Crear el plan "Mensual": $ 120.000, 30 días.
   - Un nombre repetido responde 409.
   - El coach solo lista planes activos.
8. La auditoría muestra filas `login`, `insert` y `update`, con `password_hash` como `<redacted>`.

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

- `0005_settings` (US-054).
- `0006_members` (US-069).
- `0007_plans` (US-078).

## Endpoints que expone

29 endpoints.

- **Auth:**
  - `POST /api/v1/auth/login` y `POST /api/v1/auth/forgot`: públicos, en lista blanca, con un límite de 5 por minuto por IP;
  - `POST /api/v1/auth/refresh` y `POST /api/v1/auth/reset`: públicos;
  - `POST /api/v1/auth/logout`, `GET /api/v1/auth/me` y `POST /api/v1/auth/me/password`: admin, coach y member.
- **Users (admin):**
  - `GET` y `POST /api/v1/users`;
  - `GET`, `PATCH` y `DELETE /api/v1/users/{id}`;
  - `POST /api/v1/users/{id}/lock`, `/unlock`, `/resend-link` y `/revoke-sessions`.
- **Settings (admin):**
  - `GET` y `PATCH /api/v1/settings/{section}`;
  - `GET` y `PATCH` de `/settings/gym`, `/settings/privacy` y `/settings/memberships`.
- **Members (admin y coach):** `POST` y `GET /api/v1/members`.
- **Plans:**
  - `POST /api/v1/plans` (admin);
  - `GET /api/v1/plans` y `GET /api/v1/plans/{id}` (admin y coach).

`PATCH`, `activate`, `deactivate` y `DELETE` de planes entran en el Sprint 4A con US-080, US-081 y US-082.

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

## Definición de hecho del sprint

- 9 slices de backend y 9 de front confirmados con `checkpoint-commit.sh`.
- `run-gates.sh` en verde:
  - cobertura global de `app` en 80 % o más, con `--cov-omit` documentado;
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
