# Sprint 2 · Identidad, configuración, shell del front, primeros socios y planes

- Versión: v0.1.
- Épicas: EP-04 (el resto), EP-05 (salvo US-056), EP-06 (el resto), US-107 de EP-11, US-031 de EP-02, y la base de EP-07 y EP-08.
- Tamaño: 26 historias, 87 puntos y 374 h relativas.
- Rama: `feat/sprint-02-identidad-socios-planes`.
- Historias del sprint: US-031, US-042, US-043, US-044, US-045, US-046, US-047, US-048, US-049, US-050, US-051, US-052, US-053, US-054, US-055, US-057, US-058, US-061, US-062, US-067, US-068, US-069, US-070, US-078, US-079, US-107.

## Objetivo

Que el admin y el coach entren al sistema con su rol y vean solo lo que les corresponde. El admin, además:
- administra usuarios con enlaces de activación;
- configura el gimnasio, la política de privacidad y los parámetros de membresías.

Los dos registran y buscan socios con documento, teléfono y correo cifrados por el bus, y el admin crea los planes que se venden en el Sprint 3.

## Demo al final del sprint

1. Con `docker compose up`, abrir `http://localhost`. La pantalla de login aparece en tema claro y en tema oscuro.
2. **Admin y usuarios:**
   - entrar con el admin del seed;
   - crear un coach desde Usuarios: la respuesta trae el enlace de activación de 72 h;
   - abrir el enlace en otra ventana, fijar una contraseña de 12 o más caracteres y entrar como coach.
3. **Lo que ve el coach:** no tiene en el menú Usuarios ni Configuración. Si navega a `/sistema/configuracion` a mano, ve "Sin permiso".
4. **Rate limit y sesión:**
   - el sexto login fallido en un minuto responde 429;
   - reusar un refresh ya rotado revoca todas las sesiones del usuario (N-13).
5. **Configuración (admin):**
   - guardar los datos del gimnasio;
   - publicar la versión de la política;
   - fijar `expiring_days = 7`;
   - el TopBar del coach muestra el nombre del gimnasio, que viene de `GET /auth/me` con `gym_name` y respaldo "APEX".
6. **Socios:**
   - registrar un socio con CC 1.020.304.417 y buscarlo por documento, por teléfono y por nombre;
   - `SELECT document, document_idx FROM members.members` muestra un blob `apx1.` y un HMAC, nunca el número;
   - el segundo socio con el mismo documento responde 409 con `existing_id`.
7. **Planes:** crear el plan "Mensual" en $ 120.000 por 30 días. Un nombre repetido responde 409. El coach solo lista los planes activos.
8. **Auditoría:** `SELECT action, table_name FROM audit.audit_log ORDER BY seq DESC LIMIT 10` muestra los login, los `insert` de `members` y `plans`, y los cambios de `settings_sections`.

## Dependencias de sprints anteriores

- **Sprint 0:** `create_app`, `0001`, envelope de errores, logging y el esqueleto `web/`.
- **Sprint 1:**
  - US-015 y US-016 (auditoría y hook);
  - US-019 (paginación);
  - US-021 (OpenAPI);
  - US-022 (fronteras);
  - US-023 a US-029 (bus completo);
  - US-032 a US-039 (seguridad);
  - US-041 (`0004_auth`, `SYSTEM_USER_ID`, cargador de principal y seed);
  - el kit US-040, US-059, US-060 y US-063 a US-066.

Decisiones que aplica este sprint:
- N-10: contraseña de 12 caracteres.
- N-11: enlaces de 72 h y de 1 h.
- N-12: solo `resend-link`.
- N-13: refresh en cookie HttpOnly, rotación y reuso que revoca todo.
- N-17: `version` en Settings.
- N-18: campos y rangos.
- N-19: `warnings: []`.
- N-20: bajas visibles.
- N-22: nombre de plan único entre los no borrados.
- Refinamientos de US-057 (`policy_text` obligatorio, `retention_years` de 1 a 20), de US-061 (`gym_name` en `/auth/me`) y de US-062 (5 pestañas del portal).
- Contradicción de US-107: el login emite `LoginAttempted` y US-107 se suscribe; no hay escritura directa.

## Historias en orden de ejecución

### Wave 0 · Infraestructura (`devops-wsl2-docker`)

- **Slice S2-W0-1 · Playwright contra el stack y Nginx para los enlaces.** Son las tareas DevOps de US-068 y de US-048.
  - Job de CI que levanta `infra/compose.yml` y corre Playwright, con capturas en 320, 768, 1024 y 1440 px, en claro y en oscuro.
  - Nginx no registra las query strings de `/restablecer/` ni la `q` de `/members`.
  - Gate: smoke de Compose y `bash -n` de los scripts.

### Wave 3a · Tests de backend en rojo (`backend-qa-executor`)

- **S2-B1:**
  - `tests/settings/test_settings_rules.py`, `test_settings_service.py` y `test_settings_router.py`;
  - `tests/settings/test_gym_schema.py` y `test_gym_router.py`;
  - `tests/settings/test_privacy_schema.py`, `test_privacy_service.py` y `test_privacy_router.py`;
  - `tests/settings/test_memberships_policy.py`, `test_memberships_schema.py` y `test_memberships_router.py`;
  - `tests/architecture/test_settings_no_secrets.py`.
- **S2-B2:**
  - `tests/auth/test_pure_login.py`, `test_login_service.py` y `test_login_router.py`;
  - `tests/auth/test_pure_refresh.py`, `test_refresh_service.py` y `test_refresh_router.py`;
  - `tests/auth/test_logout_service.py` y `test_logout_router.py`.
- **S2-B3:**
  - `tests/auth/test_pure_password_policy.py`, `test_change_password.py` y `test_me_router.py`;
  - `tests/auth/test_pure_user_status.py`, `test_list_users.py` y `test_users_list_router.py`;
  - `tests/auth/test_pure_links.py`, `test_create_user.py` y `test_create_user_router.py`.
- **S2-B4:**
  - `tests/auth/test_pure_one_time_token.py`, `test_reset_forgot.py` y `test_reset_forgot_router.py`;
  - `tests/auth/test_resend_link.py` y `test_resend_link_router.py`;
  - `tests/architecture/test_auth_routes.py`.
- **S2-B5:**
  - `tests/auth/test_pure_last_admin.py`, `test_update_delete_user.py` y `test_user_detail_router.py`;
  - `tests/auth/test_pure_lock.py`, `test_lock_unlock.py` y `test_lock_router.py`;
  - `tests/auth/test_revoke_sessions.py` y `test_revoke_sessions_router.py`.
- **S2-B6:**
  - `tests/audit/test_security_events.py`;
  - `tests/audit/test_reveal_entry.py`, que deja el contrato de la fila `reveal`; la llena US-074 en el Sprint 3;
  - `tests/auth/test_router_login_audit.py`.
- **S2-B7:**
  - `tests/members/test_member_rules.py`, `test_service_create.py` y `test_router_create.py`;
  - `tests/architecture/test_members_encrypted_at_rest.py`;
  - `tests/architecture/test_no_plaintext_at_rest.py`;
  - `tests/architecture/test_import_analyzer.py`.
- **S2-B8:**
  - `tests/members/test_classify_query.py`, `test_service_list.py` y `test_router_list.py`;
  - `tests/members/test_list_perf.py` (marca `perf`);
  - `tests/architecture/test_list_rows_without_sensitive_fields.py`.
- **S2-B9:**
  - `tests/plans/test_validate_plan.py`, `test_service_create.py` y `test_router_create.py`;
  - `tests/plans/test_scope_rules.py`, `test_service_list.py` y `test_router_list.py`.

### Wave 3b · Implementación de backend (`backend-implementor`)

- **Slice S2-B1 · Configuración del gimnasio.** Historias: US-054, US-055 (backend), US-057 y US-058.
  - **Migración `0005_settings`:** `settings.settings_sections`, con `key` única, `version` y `updated_by`. Sin filas sembradas: los valores por defecto salen del esquema Pydantic con `version: 0`.
  - Secciones `gym`, `privacy` y `memberships`, con los campos y rangos de N-18. 409 `version_conflict` y 404 `section_not_available`.
  - `memberships_policy()` y `current_privacy_version()`, que usarán US-083, US-084, US-089, US-094 y US-149.
  - Gate: `slice-gate.sh settings`, más el ciclo de Alembic.
- **Slice S2-B2 · Sesión.** Historias: US-042, US-043 y US-044.
  - Login con `rate_limit("login")`:
    - emite `LoginAttempted`;
    - `last_login_at` va en `__audit_exclude__`;
    - el refresh se entrega en cookie HttpOnly.
  - Refresh con rotación: si un refresh rotado se reusa, se revocan todas las sesiones del usuario.
  - Logout.
  - Gate: `slice-gate.sh auth`.
- **Slice S2-B3 · Mi cuenta y usuarios.** Historias: US-045, US-046 y US-047.
  - `GET /auth/me` con `gym_name` y respaldo "APEX".
  - Cambiar contraseña revoca las demás sesiones.
  - Lista de usuarios paginada.
  - Crear usuario con enlace de activación de 72 h. Su firma queda fijada para US-131 y US-185.
  - Gate: `slice-gate.sh auth`.
- **Slice S2-B4 · Activación, recuperación y reenvío.** Historias: US-048 y US-052.
  - `forgot` con `rate_limit("forgot")`, `reset` y `activate`.
  - 400 `invalid_token`.
  - `POST /users/{id}/resend-link`, que invalida el enlace anterior (N-12).
  - Gate: `slice-gate.sh auth`.
- **Slice S2-B5 · Ciclo de vida del usuario.** Historias: US-049, US-050 y US-051.
  - Editar y dar de baja con borrado lógico.
  - Impedir que se quite el último admin.
  - Bloquear y desbloquear, con `locked_at` revisado en cada petición.
  - Cerrar las sesiones de un usuario.
  - Emiten `UserLocked` y `SessionsRevoked`.
  - Gate: `slice-gate.sh auth`.
- **Slice S2-B6 · Auditoría de eventos de seguridad.** Historia: US-107.
  - Suscriptores de `LoginAttempted`, `UserLocked` y `SessionsRevoked`.
  - Un login fallido con un correo inexistente solo deja log y cuenta para el rate limit; no se audita (N-31).
  - Gate: `slice-gate.sh audit`.
- **Slice S2-B7 · Registrar socio y pruebas de cifrado en reposo.** Historias: US-069 y US-031.
  - **Migración `0006_members`:**
    - campos cifrados con sus `*_idx`, sin `*_hint` (N-01);
    - `sex`, `data_consent_at` y `data_consent_version`;
    - índice único parcial `document_idx WHERE deleted_at IS NULL`;
    - índices `phone_idx` y `email_idx`.
  - `members.service`: `create`, `ref`/`get_ref`, `ensure_exists`, `id_by_document` y `count`. La respuesta lleva `warnings: []`. Cada alta emite `MemberCreated`.
  - US-031 recorre la primera tabla real con su fábrica en `api/tests/factories/`.
  - Gate: `slice-gate.sh members && slice-gate.sh crypto`, más el ciclo de Alembic.
- **Slice S2-B8 · Buscar y listar socios.** Historia: US-070.
  - Búsqueda por índice ciego para documento, teléfono y correo, y por nombre en claro.
  - `search_ids` y `names_for`, que incluyen a los dados de baja y el sexo.
  - Las filas de la lista no traen campos cifrados ni enmascarados (N-01).
  - Gate: `slice-gate.sh members`.
- **Slice S2-B9 · Crear y listar planes.** Historias: US-078 y US-079.
  - **Migración `0007_plans`:** CHECK de `validate_plan`, índice único parcial de `name` (N-22) e `ix_plans_active_alive`.
  - `plans.service`: `get`, `get(for_share=True)`, `get_including_deleted` y `names_for`.
  - Para el coach, `GET /plans` solo admite `active=true`.
  - Gate: `slice-gate.sh plans`, más el ciclo de Alembic.

### Wave 5a · Tests de front en rojo (`frontend-qa-automation`)

- **S2-F1:**
  - `src/layouts`;
  - `src/shared/ui/TopBar` y `src/shared/ui/SideNav`;
  - `tests/e2e/panel-layout.spec.ts` y `tests/e2e/layouts.spec.ts`.
- **S2-F2:**
  - `src/routes` y `src/config`;
  - `src/routes.test.ts`;
  - `tests/e2e/role-guards.spec.ts`.
- **S2-F3:**
  - `src/features/auth` y `src/core/auth`;
  - `src/shared/ui/TopBar.logout.test.tsx`;
  - `tests/e2e/login.spec.ts`.
- **S2-F4:**
  - `src/features/auth/components` y `src/features/auth/pages`;
  - `src/features/system/pages/UsersPage.test.tsx`;
  - `src/features/system/components/NewUserPanel.test.tsx` y `LinkModal.test.tsx`;
  - `tests/e2e/users-activation.spec.ts`.
- **S2-F5:**
  - `src/features/system/components/PrivacySettingsForm` y `MembershipsSettingsForm`;
  - `tests/e2e/settings-gym.spec.ts`.
- **S2-F6:** `src/features/members`.
- **S2-F7:** `src/features/plans/pages/PlansPage.test.tsx` y `src/features/plans` (formulario de alta).
- **S2-F8:**
  - `src/core/theme`;
  - `tests/kit-inventory.test.ts`;
  - `tests/e2e/kit.spec.ts`.

### Wave 5b · Implementación de front (`frontend-ux-engineer`)

- **Slice S2-F1 · Layouts.** Historias: US-061 y US-062.
  - `PanelLayout`, `TopBar` y `SideNav`, con `useCan` y "Saltar al contenido".
  - `PortalLayout` con 5 pestañas (`PORTAL_TABS`), `GymLayout` y `TvLayout`.
  - Gate: `slice-gate.sh web/layouts`.
- **Slice S2-F2 · Rutas y guardas.** Historias: US-067 y US-053.
  - `routes.tsx` con `feature` y `roles`.
  - `isRouteEnabled`.
  - `RequireRole`, que muestra "Sin permiso", y `homeFor` por rol.
  - Gate: `slice-gate.sh web/core`.
- **Slice S2-F3 · Login, refresh y logout.** Historias: US-042, US-043 y US-044 (front).
  - `LoginPage`.
  - `session.ts`, con el access token en memoria.
  - Refresh compartido entre pestañas por el canal `apex-auth`.
  - Logout desde el TopBar.
  - Gate: `slice-gate.sh web/features/auth`.
- **Slice S2-F4 · Mi cuenta y usuarios.** Historias: US-045, US-046, US-047, US-048, US-049, US-050, US-051 y US-052 (front).
  - Panel "Mi cuenta".
  - Páginas de activar y restablecer.
  - Pantalla Usuarios: lista, alta con enlace, edición, baja, bloqueo, cierre de sesiones y reenvío.
  - Se parte en dos checkpoints: `web/features/auth` y `web/features/system`.
- **Slice S2-F5 · Configuración.** Historias: US-055, US-057 y US-058 (front).
  - Pantalla `Config` con las pestañas Gimnasio, Privacidad y Membresías.
  - `useSettingsSection` y `useSaveSettingsSection`, con manejo del 409 `version_conflict`.
  - Gate: `slice-gate.sh web/features/system`.
- **Slice S2-F6 · Socios: alta y lista.** Historias: US-069 y US-070 (front).
  - `Socio_Form` con los errores por campo y el enlace al socio existente en el 409.
  - `Socios_Lista` con búsqueda y paginación.
  - Gate: `slice-gate.sh web/features/members`.
- **Slice S2-F7 · Planes: alta y lista.** Historias: US-078 y US-079 (front).
  - Pantalla `Planes` con la lista y el `PlanForm` de alta.
  - Gate: `slice-gate.sh web/features/plans`.
- **Slice S2-F8 · Temas, accesibilidad y capturas.** Historia: US-068.
  - Cierra el kit:
    - conmutador de tema;
    - axe sobre todo el inventario;
    - capturas de referencia en los 4 anchos y los 2 temas.
  - Gate: `slice-gate.sh web/core` y `npx playwright test tests/e2e/kit.spec.ts`.

### Validación del sprint

- E2E contra el stack: `login.spec.ts`, `users-activation.spec.ts`, `role-guards.spec.ts`, `settings-gym.spec.ts` y `kit.spec.ts`.
- E2E de dos pestañas para el refresh (US-043).
- Prueba de rendimiento de la lista de socios con 1.000 socios (`-m perf`).

## Migraciones que aplica

- `0005_settings` (US-054).
- `0006_members` (US-069).
- `0007_plans` (US-078).

## Endpoints que expone

29 endpoints:

- **Auth:**
  - `POST /api/v1/auth/login` y `POST /api/v1/auth/forgot`: públicos, en lista blanca, con 5 por minuto por IP.
  - `POST /api/v1/auth/refresh` y `POST /api/v1/auth/reset`: públicos.
  - `POST /api/v1/auth/logout`, `GET /api/v1/auth/me` y `POST /api/v1/auth/me/password`: admin, coach y member.
- **Users (admin):**
  - `GET /api/v1/users` y `POST /api/v1/users`;
  - `GET /api/v1/users/{id}`, `PATCH /api/v1/users/{id}` y `DELETE /api/v1/users/{id}`;
  - `POST /api/v1/users/{id}/lock` y `POST /api/v1/users/{id}/unlock`;
  - `POST /api/v1/users/{id}/resend-link` y `POST /api/v1/users/{id}/revoke-sessions`.
- **Settings (admin):**
  - `GET` y `PATCH /api/v1/settings/{section}`;
  - `GET` y `PATCH /api/v1/settings/gym`;
  - `GET` y `PATCH /api/v1/settings/privacy`;
  - `GET` y `PATCH /api/v1/settings/memberships`.
- **Members (admin y coach):** `POST /api/v1/members` y `GET /api/v1/members`, con búsqueda `q`.
- **Plans:**
  - admin: `POST /api/v1/plans`;
  - admin y coach: `GET /api/v1/plans` y `GET /api/v1/plans/{id}`.

`PATCH /plans/{id}`, `activate`, `deactivate` y `DELETE /plans/{id}` no se registran en este sprint. Entran en el Sprint 4 con US-080, US-081 y US-082, que son sus dueñas.

## Tests de arquitectura que deben pasar

- Los de los Sprints 0 y 1.
- `tests/architecture/test_settings_no_secrets.py` (US-054 y US-055).
- `tests/architecture/test_no_cross_models.py`, ampliada a `settings` (US-054).
- `tests/architecture/test_auth_routes.py` (US-052).
- `tests/architecture/test_audited_tables.py`, ampliada (US-107).
- `tests/architecture/test_members_encrypted_at_rest.py` (US-069).
- `tests/architecture/test_no_plaintext_at_rest.py`, `tests/architecture/test_import_analyzer.py` y `tests/architecture/test_banned_imports.py`, ampliadas (US-031).
- `tests/architecture/test_list_rows_without_sensitive_fields.py` (US-070).

## Riesgos y mitigación

1. [HIGH] US-069 fija con datos el índice único parcial, el blob y la normalización del padrón. Un error después obliga a recifrar o reindexar a todos los socios.
   - Mitigación:
     - US-031 entra en el mismo slice;
     - `test_members_encrypted_at_rest.py` bloquea el checkpoint;
     - no se cargan socios reales hasta el release v0.1.
2. [MEDIUM] El refresh con varias pestañas y el reuso de un refresh rotado pueden cerrar sesiones legítimas.
   - Mitigación: refresh compartido por `BroadcastChannel` (`apex-auth`) y E2E de dos pestañas.
3. [MEDIUM] Inconsistencia entre la matriz de permisos del front y los roles del API.
   - Mitigación: `useCan` lee la matriz única de US-040; `role-guards.spec.ts` y las pruebas de router cubren los 403 de cada ruta.
4. [LOW] Durante los Sprints 2 y 3, un plan creado por error no se puede editar ni desactivar desde la API, porque US-080 a US-082 llegan en el Sprint 4.
   - Mitigación: no hay datos reales antes del release v0.1, y en desarrollo se recrea la base.
5. [MEDIUM] Es el sprint con más front (8 slices).
   - Mitigación: el shell (S2-F1 y S2-F2) va antes que cualquier página, y las capturas de US-068 cierran al final.

## Definición de hecho del sprint

- Los 9 slices de backend y los 8 de front confirmados con `checkpoint-commit.sh`.
- `scripts/workflow/run-gates.sh` en verde, con cobertura del 80 % en `auth`, `settings`, `members` y `plans`.
- `cd api && uv run pytest tests/architecture -q` en verde.
- Ciclo de Alembic sobre `0007`.
- `docs/openapi.json` regenerado. Los tipos del front se regeneran y `npx tsc --noEmit` queda en verde.
- E2E en verde contra el stack:
  - `tests/e2e/login.spec.ts`;
  - `tests/e2e/users-activation.spec.ts`;
  - `tests/e2e/role-guards.spec.ts`;
  - `tests/e2e/settings-gym.spec.ts`;
  - `tests/e2e/panel-layout.spec.ts`;
  - `tests/e2e/layouts.spec.ts`;
  - `tests/e2e/kit.spec.ts`.
- Smoke con evidencia SQL: blob en `members.members`, filas `login` e `insert` en la auditoría y `password_hash` como `<redacted>`.
- Seguridad, revisada por `security-reviewer`:
  - refresh en cookie HttpOnly con `SameSite` y `Secure` según `COOKIE_SECURE`;
  - enlaces de un solo uso guardados como hash;
  - `forgot` sin diferencia observable entre un correo existente y uno inexistente;
  - ningún dato cifrado en las listas;
  - 403 en todas las rutas de admin para el coach;
  - logs sin el correo ni el token.
- `verify-delivery`, con el login real y el socio real verificados en la base.
