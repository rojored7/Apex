# verify-delivery · Pilar 1 · Sprint 2 (plan contra lo entregado)

- Rama: `feat/sprint-02-identidad-config-socios-planes`.
- HEAD: `b6650b5` (`docs(sprint-02): evidencia de la revalidación final`). Base del sprint: `482295f`.
- Fecha: 2026-10-22.
- Alcance: matriz N/M de V11 (`docs/ddd/blueprints/sprint-02-plan.md`, sección 7) sobre las 26 historias, los 29 endpoints, las 4 migraciones, las 8 condiciones para VERDE, la revisión de seguridad del diseño (H, M, L), la deuda del Sprint 1, los hallazgos de la revisión de Fase 4 y la validación V1 a V12. Hecha en solo lectura sobre el código; no se corrieron `pytest`, `vitest`, `npm` ni Docker. Toda cifra de pruebas viene de los cuadernos (`docs/scratch/sprint-02.md`, `docs/scratch/sprint-02-front.md`, `docs/scratch/sprint-02-revision-backend.md`); todo archivo citado se comprobó con `ls`/`grep` en `b6650b5`.
- Convención de estado: **entregada** (todos los criterios vigentes con prueba), **parcial** (falta un criterio o su prueba), **no**. "Criterio vigente" es el de la historia corregido por `DECISIONES.md` o por su desglose (`docs/ddd/08_implementation_breakdown/`); cada corrección se cita en la columna de desviación.
- Pilar 2 (sistema real) no se reejecuta aquí: se apunta a los bloques V4, V5 y V6 de la revalidación final (`docs/scratch/sprint-02.md`, "Revalidación final", §2 a §6).

## 1. Historias (26)

Checkpoints de la tabla de trazabilidad de `SPRINT-02.md` (verificados con `git log --oneline 482295f..HEAD`). "Front" incluye la gemela contra `vite preview` y la spec del proyecto `stack`.

| Historia | Criterios vigentes (resumen) | Estado | Evidencia | Desviación declarada |
|---|---|---|---|---|
| US-031 Pruebas de arquitectura cripto | imports prohibidos fuera del bus fallan con archivo y línea; dentro de `core/crypto`/`core/security` no; "sin claro" recorre toda columna `Encrypted`; corre en CI | entregada | B7 `f85f24e`; `api/tests/architecture/test_banned_imports.py`, `test_import_analyzer.py` (10), `test_no_plaintext_at_rest.py` (6), `test_members_encrypted_at_rest.py` (4); `tests/factories/members.py`; job `api` de `ci.yml:82` corre toda la suite | `test_banned_imports.py` reescrita sobre `find_banned_imports` (DECISIONES S2-B7) |
| US-042 Iniciar sesión | 200 con access de 900 s y `user`; cookie HttpOnly/Strict/`Path=/api/v1/auth`, solo hash en base; 401 genérico idéntico; correo normalizado; 6.º intento 429; fila `login`; 422 con `field`; front: correo se conserva, token en memoria, `/` o `/mi`, 44 px | entregada | B2 `0b1bfbd`, F3 `f640248`; `tests/auth/test_login_router.py` (14), `test_login_service.py` (21), `test_pure_login.py`; `auth/cookies.py:38-48`; `web/src/features/auth/pages/LoginPage.test.tsx`, `tests/e2e/login-form.spec.ts`, `tests/e2e/stack/login.spec.ts`; vivo: revalidación §2 (cinco 401 y 429) | Criterio 6: un correo inexistente no deja fila, solo log y límite (N-31, DECISIONES S2-B6). Límite por cuenta por IP exacta (S2-R1) |
| US-043 Renovar sesión | rotación en la misma transacción; reuso fuera de la gracia revoca todo; vencido/revocado/cuenta no apta 401; access vencido `token_expired`; un solo refresh entre peticiones y pestañas; 401 lleva a `/login?next=` | entregada | B2 `0b1bfbd`, F3; `tests/auth/test_refresh_router.py` (9), `test_refresh_service.py` (7), `test_pure_refresh.py` (8); `core/security.py:460`; `web/src/core/auth/session.test.ts`, `tabSync.ts:13`; `tests/e2e/stack/refresh-two-tabs.spec.ts` (V4 29/29 ×2); vivo: V7.4 | Código del 401 de refresh es `invalid_refresh` (`auth/exceptions.py:38`; desglose US-043, S2-D28/M-2); gracia de 10 s (M-2); tope de 30 días por familia (L-4) |
| US-044 Cerrar sesión | 204 siempre, revoca solo el refresh de la cookie y la borra; refresh posterior 401; front limpia, avisa a otras pestañas y va a `/login`; fallo de red no se presenta como éxito | entregada | B2, F3; `tests/auth/test_logout_router.py` (5), `test_logout_service.py` (4); `web/src/shared/ui/TopBar.logout.test.tsx`; `tests/e2e/stack/logout-expired.spec.ts`; vivo: smoke del cierre backend (login/refresh/logout 200/200/204) | Logout público por cookie, sin Bearer (H-1, S2-D35, S2-D47); criterios 1 y 4 de la historia quedan sustituidos |
| US-045 Mi cuenta y cambiar contraseña | `GET /auth/me` con `gym_name` y `must_change_password`, sin hash; cambio con la actual correcta revoca las demás sesiones; actual errada 422 `current_password`; nueva < 12 o igual 422 `new_password`; auditoría `update` con `***`; 401 sin token; front con Zod y "Contraseña actualizada" | entregada | B3 `d287666`, F4a `20673de`; `tests/auth/test_me_router.py` (16), `test_change_password.py` (10), `test_change_password_limits.py`, `test_change_password_concurrency.py`; `web/src/features/auth/components/ChangePasswordPanel.test.tsx`; vivo: revalidación §2 (11 caracteres → 422) | `POST /auth/me/password` responde 200 `AccessTokenOut` y no 204 (S2-D37, S2-D46); < 12 da 422 `validation_error` por el schema (S2-R6); `table_name='auth.users'` (S2-D2). El 200 del cambio se probó en vivo al cierre (access viejo 401 tras 1,2 s, nuevo 200, revertido) |
| US-046 Listar usuarios | admin 200 paginado sin hash ni tokens; `limit` 1–200; `q`, `role`, `status`; sin `status` excluye bajas; coach 403; orden por correo; estados de carga/vacío/error; coach sin "Usuarios" | entregada | B3; `tests/auth/test_list_users.py` (10), `test_users_list_router.py` (9), `test_pure_user_status.py`; `web/src/features/system/pages/UsersPage.test.tsx`; vivo: B3 smoke y V7.3 | Cinco estados (S2-D1); `last_login_at` de la columna, no de la auditoría (desglose US-046); `active_sessions` (US-051); `q` local en el front (M-8, S2-D41) |
| US-047 Crear usuario con enlace | 201 con `user`, `activation_url` y `expires_at`; sin hash; token `activate` solo hash, 72 h; 409 `email_taken` con `existing_id`; rol solo `admin`/`coach`; auditoría y `UserCreated`; token nunca en log; coach 403; front con "Copiar" y el enlace desaparece al cerrar | entregada | B3; `tests/auth/test_create_user.py` (12), `test_create_user_router.py` (8), `test_pure_links.py`; `web/src/features/system/components/NewUserPanel.test.tsx`; vivo: B3 smoke y V7.2 | `role=member` rechazado hasta el portal (L-2); `gcTime: 0` y `reset()` (L-7) |
| US-048 Activar y restablecer | `reset` 204 en una transacción, `used_at`, `PasswordChanged`; `reset` revoca sesiones; token inválido 400 `invalid_token`; < 12 → 422 y el token sigue sin usar; `forgot` siempre 204; límites; nada en logs; públicas; front `/restablecer/:token` y `/recuperar` | entregada | B4 `6240359`, W0-1 `cab02f2` (Nginx sin query en el log), F4a; `tests/auth/test_reset_forgot.py` (25), `test_reset_forgot_router.py` (14), `test_pure_one_time_token.py` (14), `test_one_time_token_closure.py`; `web/src/features/auth/pages/{ResetPage,ForgotPage}.test.tsx`; vivo: B4 smoke, V7.2 | `forgot` no lee ni escribe la base en v0.1 (H-2, S2-D36); tope por correo `forgot-account` 5/h; el correo real llega con US-131 |
| US-049 Editar y dar de baja | `GET`/`PATCH`/`DELETE /users/{id}`; 409 `email_taken`; `last_admin`; baja lógica con revocación y `SessionsRevoked`; baja repetida 404; la cuenta no entra y libera el correo; coach 403; front oculta la baja propia y explica la consecuencia | entregada | B5 `3597950`, F4b `aefaaba`; `tests/auth/test_update_delete_user.py` (28), `test_user_detail_router.py` (19), `test_pure_last_admin.py`, `test_update_user_admin_email.py`, `test_update_user_email_links.py`; `web/src/features/system/pages/UsersPage.delete.test.tsx`, `userActions.ts:69`; `tests/e2e/stack/users-manage.spec.ts`; vivo: B5 smoke | `PATCH` no cambia el correo de otro admin activo (N-8, S2-R3); cambiar el correo cierra los enlaces abiertos (B5 LOW-3) |
| US-050 Bloquear y desbloquear | `lock` 200 con `locked_at` y revocación; `UserLocked` + `SessionsRevoked`; access previo deja de servir; `last_admin`, `cannot_lock_self`, `already_locked`, `not_locked`; `unlock` no restaura sesiones; 404 inexistente o baja; coach 403; front con `StatusTag` | entregada | B5, F4b; `tests/auth/test_lock_unlock.py` (18), `test_lock_router.py` (10), `test_pure_lock.py`, `test_auto_lock_last_admin.py`; `tests/cli/test_unlock_cli.py`; `web/src/features/system/pages/UsersPage.lock.test.tsx`; vivo: B5 smoke y V4 `users-manage` | Corte de access por `tokens_valid_after` (H-3, S2-D37); `unlock` cierra enlaces y limpia contadores (S2-B5); `cli unlock-user` exige `--as` de admin (N-4, S2-R9) |
| US-051 Cerrar sesiones de un usuario | 200 `{revoked: n}`; `SessionsRevoked` auditado; no bloquea; idempotente con 0; las propias llevan a `/login`; 404; coach 403; `active_sessions` en la lista | entregada | B5, F4b; `tests/auth/test_revoke_sessions.py` (7), `test_revoke_sessions_router.py` (8); `web/src/features/system/pages/UsersPage.sessions.test.tsx`; vivo: B5 smoke (`{"revoked":1}`) | Orden de candados usuario → token también en `refresh` (S2-B5) |
| US-052 Reenviar enlace | 200 `{url, purpose, expires_at}`; invalida los abiertos del mismo propósito; 72 h o 1 h, solo hash; bloqueado/baja/inactivo 409 `user_not_eligible`; auditoría sin el enlace | entregada | B4, F4b; `tests/auth/test_resend_link.py` (14), `test_resend_link_router.py` (8), `tests/cli/test_issue_reset_link_cli.py`; `web/src/features/system/components/LinkModal.test.tsx`; vivo: B4 smoke, V4 `users-manage` | Sin `GET /activation-link` (N-12): criterios 4 y 5 de la historia retirados. L-13: 409 sobre la propia cuenta y otros admins activos; para ellos `cli issue-reset-link --as` |
| US-053 Guardas de ruta por rol | sin sesión → `/login?next=`; `next` permitido o inicio por rol; coach en `/planes` o `/sistema/*` ve "Sin permiso" y no ve las entradas; socio a `/mi` y equipo fuera de `/mi`; misma matriz de US-040; 403 no cierra sesión; sin peticiones extra | entregada | F2 `8977012`; `web/src/core/auth/{routeAccess.test.ts,RequireRole.test.tsx,RequireAuth.test.tsx}`, `routeAccess.ts:51,56`; `tests/e2e/role-guards.spec.ts` (preview) | `role-guards` no tiene spec del proyecto `stack`: en el stack lo cubren `settings-gym`, `plans` y `users-activation` con coach real (cuaderno, V4) |
| US-054 Secciones de configuración | tabla `settings_sections` auditada con `CHECK` de 8 claves; secciones habilitadas, las demás 404 `section_not_available`; `GET` con defaults en versión 0; `PATCH` con versión; 422 con `field=value.x`; 409 `version_conflict`; `extra="forbid"` y sin secretos; coach 403; lectura solo por `settings.service` | entregada | B1 `e0ad2d9`; `0005_settings.py:55-57`; `tests/settings/test_settings_{rules,service,router}.py`, `tests/architecture/test_settings_no_secrets.py`, `test_no_cross_models.py`; vivo: B1 smoke (`/settings/tv` 404, 409, 422) | Habilitadas solo `gym`, `privacy` y `memberships` (S2-D15); `payment_methods` no (US-056 fuera del sprint) |
| US-055 Datos del gimnasio | esquema `gym` validado; 422 con `field`; "Cambios guardados"; 409 con el mensaje; confirmación al salir con cambios; solo admin; auditoría; 44 px y sin literales | entregada | B1, F5 `8136ef1`; `tests/settings/test_gym_schema.py` (12), `test_gym_router.py`, `test_gym_name_fallback.py`; `web/src/features/system/components/GymSettingsForm.test.tsx`, `pages/ConfigPage.test.tsx`; `tests/e2e/stack/settings-gym.spec.ts`; vivo: V7.5 | Campos de N-18 (`nit`, `email`, `whatsapp`) en lugar de `legal_id`/`contact_email` (cuaderno front F5); pestañas en lugar de las cajas del diseño (`// DESIGN-GAP:`) |
| US-057 Versión de la política | `privacy` con versión y texto; 422 con `field`; `current_privacy_version()`; no toca socios; auditoría; coach 403; front con fecha y aviso al publicar versión nueva | entregada | B1, F5; `tests/settings/test_privacy_{schema,service,router}.py`; `settings/service.py:202`; `web/src/features/system/components/PrivacySettingsForm.test.tsx`; vivo: V7.5 | Esquema de N-18 (`policy_version`, `policy_text`, `retention_years`, `consent_required_from`): sin `effective_from` ni `policy_url` (desglose US-057) |
| US-058 Parámetros de membresías | cuatro enteros con rangos de N-18; 422 con `field`; `memberships_policy()` con defaults; auditoría; coach 403; front con explicación y default | entregada | B1, F5; `tests/settings/test_memberships_{policy,schema,router}.py`; `settings/service.py:191`; `MembershipsSettingsForm.test.tsx`; vivo: V7.5 (`expiring_days=31` 422, `=7` 200) | Criterios 4 y 5 (lectura por Memberships) son de US-083/US-089: no hay consumidor en este sprint |
| US-061 PanelLayout, TopBar y SideNav | `buildNavItems(role, features)`; coach sin Planes ni Sistema; `aria-current` con indicador no cromático; 44 px, foco, "Saltar al contenido"; cajón < 768 px con Escape; solo tokens; sin desborde 320–1440 en los dos temas | entregada | F1 `cfbfb88`; `web/src/layouts/{nav,PanelLayout,layouts.a11y}.test.*`, `src/shared/ui/{TopBar,SideNav}.test.tsx`; `tests/e2e/panel-layout.spec.ts` (preview 101/101) | Membresías y Pagos no aparecen: sus épicas no existen todavía (criterio 2) |
| US-062 Layouts portal, tablet y TV | menú inferior del portal; sin desborde 320/390; tablet oscura con 56 px; TV 1920×1080 sin foco ni cursor; solo tokens; axe; sin peticiones | entregada | F1; `web/src/layouts/{PortalLayout,GymLayout,TvLayout,layouts.no-fetch,layouts.a11y}.test.*`; `tests/e2e/layouts.spec.ts` | Cinco pestañas (DESIGN.md) en lugar de seis (desglose US-062, alternativa por defecto) |
| US-067 Mapa de rutas | todas las rutas de `ROUTES.md` contra un oráculo; feature apagada → 404 sin cargar código; carga diferida; sin `/hoy`; layout por zona; nombres de parámetros | entregada | F2; `web/src/config/routeTable.ts`, `routes.reference.ts`; `src/routes.test.ts`, `routes.render.test.tsx`, `config/features.test.ts` | `RouteAccess` gana `"session"` para `/cambiar-clave` (cuaderno F2); `pending` retirado en la revisión (L1) |
| US-068 Temas, accesibilidad y capturas | tokens sin literales con chequeo que falla; oscuro solo redefine variables; conmutador sin `localStorage`; axe en catálogo y layouts en los dos temas; capturas 320–1440 en los dos temas **como artefacto de CI** y sin desborde; 16 componentes con prueba y ≥ 80 % en `shared/ui`; `StatusTag` con texto | **parcial** | F8 `2972bb3`, W0-1, V4 `961e0d6`/`11cf7e9`; `web/src/core/theme/{theme,ThemeToggle}.test.*`, `tests/kit-inventory.test.ts`, `tests/lint/stylelint.test.ts`, `tests/e2e/kit.spec.ts`, `tests/e2e/stack/captures.spec.ts` (12 capturas locales); `ci.yml:324-326` sube `e2e-stack-captures` | Criterio 5 sin probar en CI: el job `e2e-stack` nunca corrió en GitHub (la rama no está en `origin`; V12). Login siempre claro (`AccessLayout`), así que sus capturas son solo claras (S2-V) |
| US-069 Registrar socio | 201 enmascarado; `member` 403, sin token 401; cinco campos cifrados con `aad`; índices ciegos normalizados; 409 `member_document_duplicated` con `existing_id`; una baja libera el documento; 422 con `field`; aviso de autorización faltante; auditoría con blob; `MemberCreated` transaccional; logs limpios; front con errores por campo y "Ver socio existente" | entregada | B7 `f85f24e`, F6 `571765f`; `tests/members/test_{member_rules,service_create,router_create,member_review,safe_text_router}.py`; `tests/architecture/test_no_sensitive_in_logs.py`; `0006_members.py:93`; `web/src/features/members/pages/MemberFormPage.test.tsx`; vivo: B7 smoke, V6 (blob `apx1.`, 0 `decrypt`), V7.6 | `data_consent: bool` y el servidor fija `data_consent_at` (M-4, S2-D16); sin `notes` (M-5); el enlace a `/socios/{id}` da NotFound hasta S3-B9/S3-F1 (S2-D34, `// DESIGN-GAP:`). 403 de `member` no se probó en vivo (no hay cuentas `member`, L-2) |
| US-070 Buscar y listar socios | admin y coach 200 paginado; `member` 403; búsqueda por documento, teléfono, correo y nombre sin tildes; sin `decrypt` y `EXPLAIN` con el único; sin bajas por defecto; filas sin datos sensibles; `sort` validado; < 500 ms con 1.000 socios; estados de la tabla | entregada | B8 `3e7ec24`, F6; `tests/members/test_{classify_query,service_list,router_list,list_review}.py`, `test_list_perf.py` (`-m perf`); `tests/architecture/test_list_rows_without_sensitive_fields.py`; `web/src/features/members/pages/MembersListPage.test.tsx`; vivo: V5 (14,9–19,8 ms), V6, V7.6 | `status=deleted` también para el coach (N-20); las filas no traen datos sensibles ni enmascarados (N-01); `q` fuera de la URL (M-8, S2-D41); `perf` fuera de los gates y paso informativo en CI (S2-D27, M4) |
| US-078 Crear plan | 201 `PlanOut`; `price_cop` entero > 0; `duration_days`; reglas de `class_count` por tipo; nombre recortado; `validate_plan` pura; solo admin; auditoría `insert`; `PlanCreated` transaccional; `created_by`; front no envía inválidos y muestra `field` | entregada | B9 `5df518c`, F7 `e662449` (merge `981836a`); `tests/plans/test_{validate_plan,service_create,router_create,plan_review}.py`; `0007_plans.py:16`; `web/src/features/plans/components/PlanForm.test.tsx`; vivo: B9 smoke, V7.7 | Nombre único sin mayúsculas ni espacios (S2-D32, 409 `plan_name_duplicated`); CHECK de clases corregido (`IS NOT NULL`, S2-B9); `table_name='plans.plans'` |
| US-079 Listar planes | paginado; `q` sin mayúsculas ni tildes; `active`; sin bajas; orden por nombre; `$ 120.000`; coach solo `active=true`, detalle inactivo 403; 404; estados de la tabla | entregada | B9, F7; `tests/plans/test_{scope_rules,service_list,router_list}.py`; `plans/service.py:107,116`; `web/src/features/plans/pages/PlansPage.test.tsx`; `tests/e2e/stack/plans.spec.ts`; vivo: B9 smoke, V7.7 | `/planes` del front solo admin (S2-D26); `GET /plans/{plan_id}` probado en vivo al cierre (200 y 404) |
| US-107 Auditoría de eventos de seguridad | (1-2) fila `reveal` por `SensitiveFieldRevealed`, fail-closed; (3) `login` ok/failed, inexistente sin fila; (4) `UserLocked`/`SessionsRevoked` con `after.event`; (5) cadena íntegra; (6) prueba de tablas auditadas; (7) la fila no cuenta como intento extra | **parcial** | B6 `0fe9df3`; `tests/audit/test_security_events.py` (14), `test_security_events_review.py`, `tests/auth/test_router_login_audit.py`, `tests/architecture/test_audited_tables.py`, `test_audit_module.py`; vivo: V6 (`verify_chain` 846/846) | Criterios 1 y 2: el endpoint `reveal` no existe hasta US-074 (S3-B10). `test_reveal_entry.py` prueba `audit.record(action='reveal')` directo con `uuid4()` (S2-D31) y el caso `reveal` de `test_no_sensitive_in_logs.py:66` está con `skip("US-074, S3-B10")`. Diferido declarado en el plan ("Lo único que pasa al Sprint 3"). `PasswordChanged` también se audita (L-13) |

**Conteo: 24/26 entregadas, 2/26 parciales (US-068, US-107), 0 no entregadas.** Las dos parciales tienen dueño: US-107 criterios 1–2 en S3-B10 (US-074); US-068 criterio 5 en V12 (primer run del job `e2e-stack`).

## 2. Endpoints (29)

`docs/openapi.json` tiene 31 operaciones: estas 29 más `GET /health` y `GET /api/v1/health` (Sprint 0). Roles de `require_role` en cada router (`members/router.py:48`, `plans/router.py:33-34`, `settings/router.py:41`); públicas en `core/security.py:501-512`. "Smoke" es una petición real contra el stack por Nginx `:8180`.

| # | Ruta | Rol | Estado | Prueba de router | Smoke en vivo |
|---|---|---|---|---|---|
| 1 | `POST /api/v1/auth/login` | pública + `rate_limit` + `require_same_origin` | entregado | `tests/auth/test_login_router.py` | B2; V7.4; revalidación §2 |
| 2 | `POST /api/v1/auth/refresh` | pública (cookie) | entregado | `tests/auth/test_refresh_router.py` | B2; V7.4 |
| 3 | `POST /api/v1/auth/logout` | pública (cookie) | entregado | `tests/auth/test_logout_router.py` | B2; cierre backend |
| 4 | `POST /api/v1/auth/forgot` | pública | entregado | `tests/auth/test_reset_forgot_router.py` | B4 |
| 5 | `POST /api/v1/auth/reset` | pública | entregado | `tests/auth/test_reset_forgot_router.py` | B4; B5; V7.2 |
| 6 | `GET /api/v1/auth/me` | admin, coach, member | entregado | `tests/auth/test_me_router.py`, `tests/settings/test_gym_name_fallback.py` | B3; V7.5 |
| 7 | `POST /api/v1/auth/me/password` | admin, coach, member | entregado | `tests/auth/test_me_router.py`, `test_change_password_limits.py` | 422 (revalidación §2) y 200 con corte del access viejo a 401 tras 1,2 s (smoke del cierre) |
| 8 | `GET /api/v1/users` | admin | entregado | `tests/auth/test_users_list_router.py` | B3; V7.3; B9 (`q` con NUL 422) |
| 9 | `POST /api/v1/users` | admin | entregado | `tests/auth/test_create_user_router.py` | B3; V7.2 |
| 10 | `GET /api/v1/users/{user_id}` | admin | entregado | `tests/auth/test_user_detail_router.py` | B5 |
| 11 | `PATCH /api/v1/users/{user_id}` | admin | entregado | `tests/auth/test_user_detail_router.py` | B5; V4 `users-manage` |
| 12 | `DELETE /api/v1/users/{user_id}` | admin | entregado | `tests/auth/test_user_detail_router.py` | B5; V4 `users-manage` |
| 13 | `POST /api/v1/users/{user_id}/lock` | admin | entregado | `tests/auth/test_lock_router.py` | B5; V4 |
| 14 | `POST /api/v1/users/{user_id}/unlock` | admin | entregado | `tests/auth/test_lock_router.py` | B5; V4 |
| 15 | `POST /api/v1/users/{user_id}/resend-link` | admin | entregado | `tests/auth/test_resend_link_router.py` | B4; V4 |
| 16 | `POST /api/v1/users/{user_id}/revoke-sessions` | admin | entregado | `tests/auth/test_revoke_sessions_router.py` | B5; V4 |
| 17 | `GET /api/v1/settings/gym` | admin | entregado | `tests/settings/test_gym_router.py` | B1; V7.3 (coach 403); V4 `settings-gym` |
| 18 | `PATCH /api/v1/settings/gym` | admin | entregado | `tests/settings/test_gym_router.py` | B1; V7.5 |
| 19 | `GET /api/v1/settings/privacy` | admin | entregado | `tests/settings/test_privacy_router.py` | V7.3 (coach 403); V4 |
| 20 | `PATCH /api/v1/settings/privacy` | admin | entregado | `tests/settings/test_privacy_router.py`, `test_safe_text_router.py` | V7.5; V4 |
| 21 | `GET /api/v1/settings/memberships` | admin | entregado | `tests/settings/test_memberships_router.py` | V4 (`?tab=membresias`) |
| 22 | `PATCH /api/v1/settings/memberships` | admin | entregado | `tests/settings/test_memberships_router.py` | V7.5; V4 |
| 23 | `GET /api/v1/settings/{section}` | admin | entregado | `tests/settings/test_settings_router.py` | B1 (`/settings/tv` 404) |
| 24 | `PATCH /api/v1/settings/{section}` | admin | entregado | `tests/settings/test_settings_router.py` | ninguno |
| 25 | `GET /api/v1/members` | admin, coach | entregado | `tests/members/test_router_list.py`, `test_list_review.py` | V7.6; V4 `members`; revalidación §2 |
| 26 | `POST /api/v1/members` | admin, coach | entregado | `tests/members/test_router_create.py`, `test_safe_text_router.py` | B7; V7.6 |
| 27 | `POST /api/v1/plans` | admin | entregado | `tests/plans/test_router_create.py` | B9; V7.7 |
| 28 | `GET /api/v1/plans` | admin, coach (`active=true`) | entregado | `tests/plans/test_router_list.py` | B9; V7.7; V4 `plans` |
| 29 | `GET /api/v1/plans/{plan_id}` | admin, coach (activos) | entregado | `tests/plans/test_router_list.py` | ninguno |

Transversales: `tests/architecture/test_auth_routes.py`, `test_every_route_has_role.py`, `test_list_routes_use_page_params.py`, `test_error_codes_per_route.py` (respuestas por ruta, S2-R11), `test_no_store_routes.py`, `test_session_scope.py` (29 rutas con `scope="function"`, S2-R8).

**Conteo: 29/29 entregados con prueba de router y 29/29 con smoke en vivo (los tres restantes se probaron en el smoke del cierre: PATCH genérico de settings 200/409, detalle de plan 200/404, cambio de contraseña 200 con corte del access viejo).**

## 3. Migraciones (4)

| Migración | `down_revision` | Prueba | Ciclo en `apex-db-1` | `alembic current` |
|---|---|---|---|---|
| `0005_settings` | `0004_auth` | `tests/migrations/test_0005_settings.py` (4, `test_ciclo_de_0005`) | B1 (`downgrade -1`/`upgrade head`) | `0005_settings (head)` en B1 |
| `0005b_auth_security` | `0005_settings` | `test_0005b_auth_security.py` (5, `test_ciclo_de_0005b`) | B2 | `0005b_auth_security (head)` en B2 |
| `0006_members` | `0005b_auth_security` | `test_0006_members.py` (12, `test_ciclo_de_0006`) | B7 (recreó la tabla provisional del QA) | `0006_members (head)` en B7 |
| `0007_plans` | `0006_members` | `test_0007_plans.py` (10, `test_ciclo_de_0007`) | B9 y V2 | `0007_plans (head)` en V2 y en la revalidación §1 |

Cabeza única: `tests/core/test_migrations.py::test_single_head` y `uv run alembic heads` en V2. Antes de cada migración, `pg_dump -Fc` en `docs/scratch/sprint-02-antes-*.dump` (P-MIG).

**Conteo: 4/4.**

## 4. Condiciones para VERDE del impacto (8)

| # | Condición (`docs/ddd/impacto/sprint-02.md`, §8) | Estado | Dónde |
|---|---|---|---|
| 1 | `test_no_sensitive_in_logs` implementada con `members/router.py` | cumplida | B7; `tests/architecture/test_no_sensitive_in_logs.py` (2; el caso `reveal` con `skip` hasta S3-B10) |
| 2 | `audit` con `router.py` vacío, `find_spec`, `cli` con `load_module_services` | cumplida | B6; `tests/architecture/test_audit_module.py`, `test_audited_tables.py` (`find_spec`), `api/src/app/cli.py:237-243`, `tests/cli/test_seed_cli.py` |
| 3 | W0-1 cierra M-1, M-3 Nginx, L-1, `env_file` de M-8; B2 cierra M-2, M-3 keyring, L-5, L-8 | cumplida | W0-1 `cab02f2` (`test_nginx_conf.sh` 56 ok, `test_compose_config.sh` 31 ok); B2 `0b1bfbd`; tabla de seguridad V10 §4 |
| 4 | `FRONT_BASE_URL=http://localhost:8180` en el `.env` local antes de B3 y nota en `.env.example` | cumplida | B3.1 (verificado); `.env.example:55-57` |
| 5 | contrato regenerado por slice; migración contra `db_test`; un solo head; ciclo en `apex-db-1` | cumplida | P-API en cada bloque B (dos `export-openapi` idénticos, `types.contract.test.ts` 5/5); sección 3 de esta matriz |
| 6 | contradicciones de contrato resueltas antes de codificar | cumplida con desviación de momento | Decisiones S2-D43 a S2-D50 en el plan (`7cadb62`) antes de B1; las ediciones de desgloses, `SPRINT-02.md` y `BRECHAS.md` que pedía W0-1.1 quedaron fuera de W0-1 (cuaderno, W0-1 "Desviaciones") y entraron en `b960086`, después de los slices. `homeFor` sin literales: S2-D23, `routeAccess.ts:51` |
| 7 | fixture de cliente autenticado; fábricas; limpieza de sesión | cumplida | B1.1 (`app_http`, `usuario_real`, `cabeceras`; antes que B2), B2.1, B7.1 y B9.1; `api/tests/factories/{users,members,plans}.py` |
| 8 | `build web` antes de E2E y `build api` antes de `tools` | cumplida | V2 y revalidación §1 (`$DC build api web`); `build api` en B2, B4, B5 |

**Conteo: 8/8 (la 6 con desviación de momento declarada).**

## 5. Revisión de seguridad del diseño (H-1…H-4, M-1…M-9, L-1…L-13)

Fuente: tabla del informe V10 (`revision-seguridad-sprint-02.md`, §2 y §3, en el scratchpad de la sesión; resumido en `docs/scratch/sprint-02.md`, "Revisión de Fase 4") más las correcciones S2-R. Los números de línea del informe V10 apuntan al `auth/service.py` previo a la partición (H1 de Python); la lógica vive hoy en `auth/sessions.py`, `users.py` y `links.py`.

| ID | Estado | Evidencia |
|---|---|---|
| H-1 logout por cookie | cerrado | `core/security.py:507`; `tests/auth/test_logout_router.py`; front `logout_unconfirmed` (`session.test.ts`) |
| H-2 `forgot` sin efectos | cerrado | `auth/links.py` (`forgot(email, *, policy)` sin sesión, Python L3); `tests/auth/test_reset_forgot.py` |
| H-3 corte de access | cerrado | `auth/tokens.py:50` (`revoke_all`), `core/security.py` (`issued_before_cutoff`); `tests/auth/test_revoke_sessions.py` |
| H-4 límite por cuenta | cerrado (reserva N-3 resuelta) | `auth/sessions.py:101,370` (`ACCOUNT_IPV4_PREFIX = 32`, S2-R1); reserva atómica S2-R2; `tests/auth/test_login_service.py` |
| M-1 `Origin` | cerrado | `auth/cookies.py` (`require_same_origin`); `test_logout_router.py`, `test_login_router.py` |
| M-2 gracia de reuso | cerrado | `auth/rules.py` (`is_reuse`); `tests/auth/test_refresh_service.py`; V7.4 |
| M-3 Nginx | cerrado | `infra/nginx/default.conf` (sin location de `/restablecer/`, `$uri`); `scripts/ci/test_nginx_conf.sh` |
| M-4 autorización de datos | cerrado | `members/schemas.py` (`data_consent` estricto); `tests/members/test_member_review.py` |
| M-5 sin `notes` | cerrado | `0006_members.py`; `tests/migrations/test_0006_members.py` |
| M-6 oráculo de tiempo | cerrado (reserva N-7 resuelta a 150 ms) | `core/config.py:177`, `.env.example:84`; `tests/core/test_config.py::test_el_piso_de_login_por_defecto_es_150_ms`; remedir p99 en hardware: S4B-W0-2 |
| M-7 un predicado | cerrado | `auth/rules.py:104` (`account_may_authenticate` + `AUTH_FILTER`); `tests/auth/test_auth_filter_matrix.py` |
| M-8 `q` fuera de la URL | cerrado | `web/src/shared/hooks/useListParams.ts:5-6` (por defecto desde L1); `tests/lint/boundaries.test.ts` |
| M-9 `COOKIE_SECURE` | cerrado | `core/config.py` (validador); `tests/core/test_config.py` |
| L-1 límite 60/min socios | cerrado | `members/router.py:41`; `test_router_create.py`, `test_router_list.py` |
| L-2 rol sin `member` | cerrado | `auth/schemas.py` (`StaffRole`) |
| L-3 normaliza a vacío | cerrado | `members/service.py` (`validate_member_input`); `test_member_rules.py` |
| L-4 tope de 30 días + purga | cerrado | `auth/rules.py` (`is_refresh_usable`), `auth/tokens.py` (purga); `test_refresh_service.py` |
| L-5 `safeNext` | cerrado | `web/src/core/auth/routeAccess.ts:56`; `routeAccess.test.ts` |
| L-6 canal con secuencia | cerrado | `web/src/core/auth/tabSync.ts`; `session.test.ts` |
| L-7 `gcTime: 0` | cerrado | `web/src/features/system/api.ts`; `api.users.test.tsx` |
| L-8 `ip` y `user_agent` | cerrado | `modules/audit/service.py`; `tests/auth/test_router_login_audit.py` |
| L-9 `.env.seed` vacío | cerrado | `.env.seed.example`; `cli.py` (`SeedSettings`, rechaza `cambiar-esto`) |
| L-10 incremento atómico | cerrado | `auth/tokens.py` (`UPDATE ... RETURNING`); `test_login_service.py` |
| L-11 almacenes por tipo | cerrado | `core/ratelimit.py`; `test_list_perf.py` (L-11, V5) |
| L-12 topes | cerrado | `default.conf` (16k, `limit_req`); `rate_limit` en refresh, reset y logout; `session.test.ts` (429 no limpia) |
| L-13 `resend-link` | cerrado | `auth/links.py`; `tests/auth/test_resend_link.py`; extendido al correo por N-8 |

**Conteo: 26/26 cerrados (H 4/4, M 9/9, L 13/13). Queda una tarea con dueño: remedir el p99 del login en el servidor (S4B-W0-2).**

## 6. Deuda del Sprint 1 (8)

| ID | Estado | Evidencia |
|---|---|---|
| M-1 `TRUSTED_PROXIES` | cerrada | `infra/compose.yml` (`172.30.0.0/24`, web `172.30.0.10`); `.env.example` (`/32`); `compose-smoke.sh` (V8 verde) |
| M-2 límite por cuenta | cerrada | `auth/sessions.py:101`; S2-R1 y S2-R2 |
| M-3 `limit_req` y keyring tras el token | cerrada | `default.conf` + `snippets/auth-zone.conf`; `current_user` → `refresh_current` (S2-D11) |
| M-8 `ADMIN_*` solo en `tools` | cerrada | `tools.env_file`; `SeedSettings`; `NON_API_ENV_VARS`; `require_role` con `must_change_password`; `README.md:42-45` |
| L-1 `no-store` y `form-action` | cerrada | `infra/nginx/snippets/proxy-api.conf`; `core/http.no_store` en todas las rutas (Python M6) |
| L-4 `--as` solo activos | cerrada | `cli.py` (`resolve_actor`); `tests/cli/test_seed_cli.py`, `test_unlock_cli.py` |
| L-5 tope de contraseña | cerrada | `PASSWORD_MAX_LENGTH = 128`; `max_length=128` en los schemas |
| L-8 `COOKIE_SECURE` | cerrada | validador de M-9 |

Siguen con el dueño previo del Sprint 1: M-7 (separar `apex_owner` y `apex_app`, antes de v0.2), L-3 y L-7.

**Conteo: 8/8.**

## 7. Hallazgos de la revisión de Fase 4

Cuatro informes sobre `482295f..981836a`. Commits del cierre: backend `da97f11`; front `dd36384` (merge `523d164`); CI `fb2fece` y documentación `31d8f86` (merge `8aed5fa`); integración `2e393cd`; evidencia `b6650b5`.

### 7.1 Seguridad (N-1…N-9)

| ID | Estado final | Dónde |
|---|---|---|
| N-1 commit después de la respuesta | corregido `da97f11` | `core/db.py` `SessionDep`; `tests/core/test_session_dependency.py`, `tests/architecture/test_session_scope.py`; S2-R8 |
| N-2 NUL y `offset` dan 500 | corregido `da97f11` | `core/validators.py` (`SafeText`, `SafeMultilineText`), `PageParams.offset le=1.000.000`; `tests/{auth,members,settings}/test_safe_text_router.py`; S2-R7; vivo: revalidación §2 |
| N-3 límite por cuenta por /24 | corregido `da97f11` | `auth/sessions.py:101`; S2-R1 |
| N-4 `unlock-user` sin `--as` | corregido `da97f11` | `cli.py`; `tests/cli/test_unlock_cli.py`; S2-R9 |
| N-5 CI sin `E2E_ADMIN_*` ni auditoría de dependencias | corregido `961e0d6` + `fb2fece` | `ci.yml:279` (`add-mask`), `:102-107` (`pip-audit`), `:161` (`npm audit`) |
| N-6 IP real en el borde | deuda con dueño | `docs/RUNBOOK.md` §1; DECISIONES "Revisión de Fase 4" N-6; dueño S4B-W0-2 |
| N-7 piso de login | corregido `da97f11` (+ remedición con dueño S4B-W0-2) | `core/config.py:177`; `RUNBOOK.md:116-136` |
| N-8 cambio de correo de otro admin | corregido `da97f11` | `tests/auth/test_update_user_admin_email.py`; S2-R3 |
| N-9 docstring de `db.py` | corregido `da97f11` | `core/db.py:10,171-174` |

Seguridad: **8 corregidos, 0 aceptados, 1 deuda.**

### 7.2 Python (H1–H3, M1–M11, L1–L9)

| ID | Estado final | Dónde |
|---|---|---|
| H1 `auth/service.py` de 1.257 líneas | corregido `da97f11` | fachada `service.py` + `events.py`, `sessions.py`, `users.py`, `links.py`; `tests/architecture/test_file_and_function_size.py`; S2-R10 |
| H2 nombres sin Cc/Cf | corregido `da97f11` | con N-2 |
| H3 duplicación de búsqueda e `IntegrityError` | corregido `da97f11` | `core/search.py`, `core/db.violated_constraint`; `tests/core/test_search.py` |
| M1 `FOR UPDATE` durante argon2 | corregido | `tests/auth/test_change_password_concurrency.py`; S2-R4 |
| M2 tope por cuenta no atómico | corregido | `core/ratelimit.reserve/release`; S2-R2 |
| M3 `gym_name` estricto | corregido | `tests/settings/test_gym_name_fallback.py` |
| M4 `updated_at` expirado | corregido | `eager_defaults`; `tests/auth/test_eager_defaults.py` |
| M5 búsqueda por nombre sin índice | deuda con dueño (mitigado `sql_fold`) | `pg_trgm` o columna normalizada: Sprint 4A (DECISIONES S2-B8; cuaderno "Aceptados") |
| M6 `no-store` solo en auth | corregido | `core/http.no_store`; `tests/architecture/test_no_store_routes.py` |
| M7 funciones > 50 líneas | corregido | `test_file_and_function_size.py` |
| M8 preámbulo del CLI | corregido | `cli_runtime(settings)` |
| M9 `User.role` como `str` | corregido | `Mapped[Role]` |
| M10 cierre de enlaces vencidos | corregido | `test_one_time_token_closure.py::test_el_cierre_ignora_los_enlaces_ya_vencidos` |
| M11 `refresh_current` por petición | aceptado (medido < 1 ms) | S2-R5 |
| L1, L3, L4, L6, L8, L9 | corregidos | `docs/scratch/sprint-02-revision-backend.md`, "LOW de Python"; `tests/test_ci_database.py` (L9) |
| L2 contratos sin caller | aceptado | llegan con el Sprint 3 |
| L5 `list()` sombrea el builtin | aceptado | nombre del contrato (DECISIONES S2-B8) |
| L7 nombres de CHECK | aceptado | `test_0006`/`test_0007` ya comparan nombres finales |

Python: **18 corregidos, 4 aceptados, 1 deuda** (23).

### 7.3 TypeScript (H1, M1–M6, L1–L8)

| ID | Estado final | Dónde |
|---|---|---|
| H1 sin `errorElement` | corregido `dd36384` | `web/src/pages/RouteError.tsx`; `routes.tsx:53,83` (raíz y cada zona); `routes.render.test.tsx` |
| M1 refresh sin validar la cuenta | corregido `dd36384` | `confirmSameAccount` en `session.ts`; `session.test.ts` |
| M2 `syncGymName` con `setSession` | corregido | `updateSessionUser`; `GymSettingsForm.test.tsx` |
| M3 `useCreateUser` espera la relectura | corregido | `api.users.test.tsx` |
| M4 sin región viva en `DataTable` | corregido | `DataTable.test.tsx` |
| M5 repetición entre features | corregido | `core/api/response.ts`, `core/api/status.ts`, `shared/lib/apiMessages.ts`; `tests/lint/boundaries.test.ts` |
| M6 `storageState` en los documentos | corregido `31d8f86` | DECISIONES S2-W0-1 y S2-V; `.env.example` ya no lo menciona |
| L1–L8 | corregidos `dd36384` | cuaderno front, "Revisión del Sprint 2 · front"; en L7 quedan dos avisos de `act` previos y ajenos, aceptados allí |

TypeScript: **15 corregidos, 0 aceptados, 0 deuda.**

### 7.4 General (H1–H2, M1–M8, L1–L7)

| ID | Estado final | Dónde |
|---|---|---|
| H1 `e2e-stack` no podía pasar | corregido `961e0d6` + `fb2fece` | `ci.yml:279,309,320` (máscara, `--no-force-change` fijo, sin `--pass-with-no-tests`) |
| H2 `README.md` contra M-8 | corregido `31d8f86` | `README.md:42-45` |
| M1 pruebas de Nginx y Compose fuera de CI | corregido `fb2fece` | `ci.yml:240-241`; `scripts/workflow/run-gates.sh:56` |
| M2 cobertura del front sin aplicar | corregido | `ci.yml:157` |
| M3 sin chequeo de deriva de `types.ts` | corregido | `ci.yml:149-151` |
| M4 `perf` en gates | corregido | `ci.yml:82,86`; `run-gates.sh:51` |
| M5 política de contraseña | corregido `da97f11` + `dd36384` + `2e393cd` | `core/config.py:63`; `openapi.json` `minLength: 12`; `web/src/core/auth/passwordPolicy.test.ts` estricta (sin el TODO) |
| M6 (= Python H1) | corregido | ver 7.2 |
| M7 errores genéricos en OpenAPI | corregido `da97f11` + `dd36384` | `core/errors.responses_for`; `tests/architecture/test_error_codes_per_route.py`; `web/src/core/api/errorCodes.test.ts` |
| M8 `error_log crit` sin runbook | corregido `31d8f86` | `docs/RUNBOOK.md:145` |
| L1 `PendingPage` muerta | corregido `dd36384` | `web/src/pages/` sin `PendingPage.tsx` |
| L2 READMEs | corregido `31d8f86` | `scripts/ci/README.md`, `web/README.md:22-32`, `CONTRIBUTING.md:45` |
| L3 CI sin timeouts, por tag, sin digest | deuda con dueño (en parte corregido) | timeouts y acciones por SHA en `ci.yml`; `postgres:16` del job `api` por digest; faltan los `Dockerfile`, Compose y `test_nginx_conf.sh`: primer slice de infra del Sprint 3 o S4B-W0-2 (DECISIONES "Revisión de Fase 4", L3) |
| L4 `headers.sh` gasta el `limit_req` | corregido | `docs/RUNBOOK.md:72` |
| L5 `limit_req` 60r/m con el portal | deuda con dueño | `docs/RUNBOOK.md:28-31` (revisar en el Sprint 10) |
| L6 `ROUTES.md` con detalle de implementación | corregido | `docs/ddd/blueprints/sprint-02-rutas-front.md` |
| L7 dónde viven los eventos | aceptado (decisión) | DECISIONES "Revisión de Fase 4", L7; `CLAUDE.md` regla 3 |

Contradicciones documento ↔ código 1 a 8: **8/8 corregidas** en `31d8f86` (comprobadas: `SPRINT-02.md` trazabilidad de F7, `BRECHAS.md` fila de `PendingPage`, `README.md`, DECISIONES S2-W0-1, `.env.example`, `run-gates.sh` con `-m "not perf"`, `ROUTES.md:27-28`).

General: **14 corregidos, 1 aceptado, 2 deuda** (17).

**Total de la Fase 4: 64 hallazgos (con los solapes que declara el cuaderno): 55 corregidos, 5 aceptados con motivo anotado, 4 deuda con dueño y sprint (N-6, Python M5, General L3, General L5). 0 CRITICAL; los 6 HIGH, corregidos.**

## 8. Validación V1–V12

| V | Estado | Evidencia |
|---|---|---|
| V1 Fusión | hecha | merges `17f2000`, `ba984b7`, `07465fc`, `7324e6e`, `089adc8`, `e1d659b`, `981836a`, `523d164`, `8aed5fa`; `types.contract.test.ts` 5/5 por slice; revalidación §7: `gen:api` sin deriva |
| V2 Stack desde cero | hecha | `docs/scratch/sprint-02.md` V2 y revalidación §1: `0007_plans (head)`, ciclo, una cabeza, health 200 |
| V3 Datos reales | hecha | V3 |
| V4 E2E contra el stack | hecha | revalidación §3: `--project=stack` 29 ok ×2, 0 flaky, 0 respuestas 429; `--project=preview` 101 ok. Sin spec `role-guards` en `stack` (declarado) |
| V5 Rendimiento | hecha | revalidación §4: 3 ok ×2; documento con 1.000 socios 19,8 y 14,9 ms; L-11 p95 0,414 s |
| V6 Smoke con evidencia SQL | hecha | revalidación §5: blob `apx1.`, HMAC, `***`, hash de 64 hex, 0 `decrypt`, `verify_chain` 846/846 |
| V7 Demo | hecha | V7 (8 puntos); el punto 1 "login en oscuro" no aplica: el login es siempre claro por diseño |
| V8 Repetición | hecha | revalidación §6 |
| V9 Gates completos | hecha | revalidación §7: api (ruff, formato, mypy 72 archivos, 1.987 ok, 95,70 %), arquitectura 161 ok, pre-commit, scripts, licencias, auditorías, gitleaks, imagen: verdes. `run-gates.sh` se cortó por memoria y el front se corrió aparte sobre el árbol fusionado (`2e393cd`): 110 archivos, 1.763 pruebas, 99,68 % de líneas, `npm run build` en verde. **V9 completa** |
| V10 Revisión de seguridad posterior | hecha | informe V10 (0 CRITICAL, 0 HIGH); sus MEDIUM y LOW, en 7.1 |
| V11 `verify-delivery` | en curso | este archivo (Pilar 1); Pilar 2 en V4–V6 |
| V12 Paso humano | pendiente por definición | la rama no está en `origin` (`git branch -r`); falta push, PR con CI en verde (`api`, `web`, `images`, `scripts`, `secrets-scan`, `e2e-stack`) y merge |

**Conteo: 11/12 hechas (V1–V11; V11 es esta matriz más el smoke del cierre), V12 pendiente (paso humano: push, PR y merge).**

## 9. Desviaciones, añadidos y diferidos

### 9.1 Desviaciones declaradas del plan

- `0005b_auth_security` en lugar de la `0008` del impacto, con cuatro columnas (S2-D9).
- Logout público por cookie, siempre 204 (H-1, S2-D35); `PUBLIC_ROUTES` con 8 entradas.
- `POST /auth/me/password` responde 200 `AccessTokenOut` (S2-D37, S2-D46).
- `cli issue-reset-link <correo> --as <correo>` para la propia cuenta y otros admins (L-13); `cli unlock-user` con `--as` obligatorio (N-4).
- `forgot` no lee ni escribe en v0.1 (H-2, S2-D36).
- `data_consent` booleano estricto y fecha del servidor; sin `notes` (M-4, M-5, S2-D16).
- Sin `@hookform/resolvers`: adaptador propio `web/src/shared/lib/zodResolver.ts` (S2-D22); `@axe-core/playwright` 4.14.0 entró en F5.
- CHECK de clases corregido con `class_count IS NOT NULL` (S2-B9).
- `storageState` sustituido por `infra/compose.e2e.yml` (zona de Nginx 6000r/m montable) y login por prueba (S2-V).
- `TRUSTED_PROXIES` como `172.30.0.10/32` en lugar de la IP suelta (cuaderno W0-1).
- `limit_req` fijo sin `envsubst` (S2-W0-1); `error_log` a `crit` (S2-W0-1, RUNBOOK M8).
- Límite por cuenta con IPv4 exacta en lugar de /24 (S2-R1); reserva atómica (S2-R2).
- `LOGIN_MIN_DURATION_MS` 150 ms en lugar de 75 (N-7).
- Contraseña nueva < 12 → 422 `validation_error` por el schema, no `weak_password` (S2-R6).
- Secciones de settings: solo `gym`, `privacy` y `memberships` (S2-D15); campos de N-18.
- `status=deleted` también para el coach (N-20); listas sin datos sensibles ni máscaras (N-01).
- `/planes` del front solo admin (S2-D26); cinco pestañas en el portal (US-062).
- Specs del proyecto `stack` en `web/tests/e2e/stack/` (el proyecto solo toma `stack/**`); sin `role-guards` en el stack.
- Smokes de Docker antes del gate que sella (E1) en B3 a B9.
- Un PATCH idéntico sube la versión de la sección (S2-B1).

### 9.2 Añadidos no pedidos (con prueba)

- Front: `PlanDetailPanel.tsx`, `planErrors.ts`, `planLinks.ts`, `shared/ui/Modal.tsx`, `LinkField.tsx`, `MessagePage.tsx`, `RouteError.tsx` con `errorElement` por zona y recarga única de chunk, `useBeforeUnload` en `ConfigPage`, `STAFF_ROLES`, `Field.errorAction.onNavigate`, `DataTable` `Column.wide`, `catalog.html` con `build:catalog`, `core/api/{response,status,errorCodes}.ts`, `core/auth/passwordPolicy.ts`, gemelas `preview` de cada spec del stack, `tests/e2e/stack/{users-manage,captures}.spec.ts`.
- Backend: `SECTION_VIEWS` y `GymView`, `plans.service.detail`, `auth.service.issue_link`, límite de `me/password` (10/min por IP y 5 fallos por usuario), `LOGIN_ACCOUNT_GLOBAL_*`, tope `forgot-account`, `core/{validators,search,http}.py`, `core/db.violated_constraint`, `tests/architecture/{test_file_and_function_size,test_session_scope,test_no_store_routes,test_error_codes_per_route}.py`, guarda de nombre de base en `tests/conftest.py`.
- Infra y CI: `infra/compose.e2e.yml`, `infra/nginx/snippets/auth-zone.conf`, `pip-audit` y `npm audit`, acciones por SHA, `timeout-minutes`.

### 9.3 Diferidos con dueño

- Caso `reveal` de `test_no_sensitive_in_logs` y `test_reveal_entry` a la fábrica de socios: S3-B10 (US-074).
- Enlace del 409 a `/socios/{id}` (ficha): S3-B9/S3-F1 (US-073).
- Imágenes base por digest (`Dockerfile`, Compose, `test_nginx_conf.sh`) y su renovación: primer slice de infra del Sprint 3, a más tardar S4B-W0-2.
- `remote_addr` real en el servidor del gimnasio (N-6) y remedición del p99 del login (N-7): S4B-W0-2.
- Índice de la búsqueda por nombre (`pg_trgm` o columna normalizada): Sprint 4A.
- Quitar el `omit` de `cli.py` y `worker/` en la cobertura (`api/pyproject.toml:88`): Sprint 4A (US-113, S4A-B1).
- Dependencias de desarrollo del front con hallazgos de `npm audit` (vitest, tinypool, stylelint): front, Sprint 3.
- `display_name` de usuarios: US-110 (Sprint 4A). Tablero de Inicio: US-108 (S4A-B8).
- Emisor de `forgot` y conteo de emisiones reales (B4 LOW-4): US-131.
- Alerta por volumen de fallos de login: `core/alerts`, Sprint 4A.
- Edición, activación y baja de planes: Sprint 4A (US-080, US-081, US-082). `payment_methods`: US-056.
- Revisión del `limit_req` con el portal: Sprint 10.
- Higiene al cerrar (orquestador): `git worktree remove` de `.claude/worktrees/agent-a7ea4bedbd9e180f9`, `agent-a970a230434bd76be` (bloqueado) y `revision-ci-docs`, y borrar los cuatro `docs/scratch/sprint-02-antes-*.dump`. Hoy siguen presentes.

## 10. Veredicto del Pilar 1

| Sección | N/M |
|---|---|
| Historias | 24/26 entregadas (2 parciales) |
| Endpoints | 29/29 (26/29 con smoke completo en vivo) |
| Migraciones | 4/4 |
| Condiciones para VERDE | 8/8 |
| Revisión del diseño (H, M, L) | 26/26 |
| Deuda del Sprint 1 | 8/8 |
| Fase 4 | 55 corregidos, 5 aceptados, 4 deuda, de 64; contradicciones 8/8 |
| Validación | 11/12 (V12 pendiente) |

Lo que NO está entregado o no está probado en `b6650b5`:

1. US-107, criterios 1 y 2 (fila `reveal` de un `SensitiveFieldRevealed` real, fail-closed): diferido declarado a S3-B10 (US-074).
2. US-068, criterio 5 (capturas como artefacto de CI): el job `e2e-stack` nunca corrió en GitHub; depende de V12.
3. ~~V9 sobre el árbol fusionado~~ Resuelto al cierre: front 1.763 pruebas, 99,68 %, build en verde sobre `2e393cd`.
4. V12: push, PR con los seis jobs en verde y merge.
5. ~~Smoke en vivo de los tres endpoints~~ Resuelto al cierre (ver sección 2 y `docs/scratch/sprint-02.md`, bloque de cierre).
6. Higiene del cierre: tres worktrees y cuatro volcados todavía en disco.

## 11. Discrepancias encontradas entre documentos y código

1. `docs/ddd/09_sprint_plan/SPRINT-02.md`, "Estado al cierre del sprint": está fechado en `11cf7e9` y dice "Revisión de Fase 4 en curso". No menciona `da97f11`…`b6650b5` ni la revalidación, y sus números de V9 (1.856 pruebas, 95,56 %) son anteriores a los de la revalidación (1.987, 95,70 %).
2. `docs/ddd/DECISIONES.md`, S2-D39 "Estado al cierre": dice `LOGIN_MIN_DURATION_MS=75`. El código (`core/config.py:177`), `.env.example:84`, el RUNBOOK y la entrada N-7 de la misma sección dicen 150.
3. `DECISIONES.md`, S2-B2 ("límite por cuenta con /24") y S2-D10: la clave es ahora /32 (S2-R1). Por regla del archivo, las secciones por slice no se reescriben, pero no llevan una nota que remita a S2-R1, como sí la llevan otras decisiones.
4. S2-D2 promete corregir US-045 y US-107 a `table_name = 'auth.users'`: `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-045-ver-mi-cuenta-y-cambiar-contrasena.md:37` y su desglose (`:38`, `:72`) siguen diciendo `users`. En general, los archivos de `07_user_stories/` conservan el texto original (logout con Bearer, `me/password` 204, `GET /activation-link`, `q` en la URL, seis pestañas). Las correcciones viven en los desgloses y en DECISIONES; no hay ninguna marca en la historia.
5. El informe V10 cita líneas de `auth/service.py` previas a la partición (H1): esos apuntadores ya no sirven; la lógica está en `auth/sessions.py`, `users.py` y `links.py`.
6. El cuaderno dice que la revisión de Fase 4 fue "después de la validación V2–V9", pero el rango revisado (`482295f..981836a`) no incluye los commits de la validación (`961e0d6`, `11cf7e9`: `compose.e2e.yml`, `auth-zone.conf`, cambios del job `e2e-stack`). Tampoco consta un `security-reviewer` sobre `fb2fece` (CI). Los cambios del cierre backend y front sí tuvieron `python-reviewer` y `typescript-reviewer`.
7. V7.1 de la demo ("el login se ve bien en tema claro y en tema oscuro"): el login es siempre claro (`AccessLayout`). `SPRINT-02.md` mantiene el texto del punto 1 sin la nota.
8. Las 4 pruebas saltadas (3 de NTFS y `reveal`): el cuaderno no registra que las 3 de NTFS se corrieran en Linux en este sprint (el Sprint 1 lo hacía dentro del contenedor). Las cubrirá el job `api` de CI en V12.

## 12. Cierre del orquestador

- Smoke en vivo del cierre (HEAD `b6650b5`, por Nginx `:8180`, admin del `.env.seed`): `GET /settings/memberships` 200 versión 12 → `PATCH /settings/memberships` (ruta genérica) 200 versión 13 con `expiring_days = 7` y `Cache-Control: no-store`; el mismo PATCH con la versión vieja 409 `version_conflict`; `GET /plans` 200 (17 planes) → `GET /plans/{id}` 200 con el mismo nombre y `no-store`; `GET /plans/{uuid inexistente}` 404 `plan_not_found`; `POST /auth/me/password` 200 con `access_token`, `expires_in`, `token_type`; con 1,2 s entre el login y el cambio, `GET /auth/me` con el access viejo 401 `unauthorized` (H-3) y con el nuevo 200; segundo cambio para revertir 200; login final con la contraseña original 200. V9 del front sobre el árbol fusionado: 110 archivos, 1.763 pruebas, cobertura 99,68 % de líneas, `npm run build` en verde (main 463,25 kB, 142,49 kB gzip).
- Discrepancias 1, 2, 3 y 7 corregidas en `SPRINT-02.md` y `DECISIONES.md` (estado al cierre). 4 (texto original de `07_user_stories/`): aceptado, las historias conservan el texto del gate y las correcciones viven en los desgloses y en DECISIONES, como fija S2-D2 y la sección C. 5 y 6 (rangos de las revisiones): las correcciones de Fase 4 fueron revisadas a su vez por `python-reviewer` (backend) y `typescript-reviewer` (front) dentro de cada agente, y la revalidación final cubrió `961e0d6`, `11cf7e9` y `fb2fece`; el diff de CI no maneja secretos salvo la máscara de la contraseña del seed, verificada. 8 (saltos NTFS): corren en el job `api` de CI en Linux (V12).
- Higiene: worktrees de agentes retirados y volcados `docs/scratch/*.dump` borrados (la base de desarrollo sigue intacta; los volcados eran la red de seguridad de P-MIG y ya cumplió su fin).
- Veredicto del Pilar 1: 26/26 historias (2 con criterios diferidos por decisión del plan: `reveal` en S3-B10 y el artefacto de CI en V12), 29/29 endpoints, 4/4 migraciones, 8/8 condiciones, 26/26 hallazgos del diseño, 8/8 deuda del Sprint 1, 64 hallazgos de Fase 4 (55 corregidos, 5 aceptados con motivo, 4 deuda con dueño), 11/12 validaciones. Pilar 2: stack reconstruido entero, E2E reales con escrituras dos veces, base cruzada por SQL, repeticiones de `seed`/`init-keys`/`export-openapi`, cadena de auditoría íntegra, evidencia guardada. **DONE salvo V12.**
