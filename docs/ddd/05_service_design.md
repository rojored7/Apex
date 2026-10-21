# 05 · Diseño de servicios

Fecha: 21 de octubre de 2026. Entradas: `02_domain_model.md`, `03_context_map.md`, `04_architecture_decision.md`, `CLAUDE.md`. Corregido tras el gate con `DECISIONES.md` (Q2, Q6, Q11, G-01, G-02, G-04, G-06, G-07, G-08, G-09, N-12, N-20, N-30, N-34).

## 1. Capas (versión ligera de Clean Architecture, como exige `CLAUDE.md`)

`CLAUDE.md` prohíbe entidades de dominio separadas de los modelos y repositorios abstractos por tabla. Por eso las capas son tres, no cuatro, y los "puertos" solo existen donde hay algo que intercambiar.

```
router.py    ─ adaptador HTTP: valida (schemas), resuelve rol, llama al service, devuelve
service.py   ─ casos de uso + reglas de negocio (funciones puras) + emisión de eventos
models.py    ─ SQLAlchemy: tablas del esquema del módulo, tipos Encrypted/BlindIndexed
schemas.py   ─ Pydantic v2: entrada y salida HTTP; nunca se usan como modelo interno
exceptions.py─ errores de dominio del módulo (opcional)
```

Reglas de dependencia:
- `router` → `service` → `models`. Nunca `router` → `models` directo.
- `service` de A → `service` de B. Nunca `models` de B.
- `service` → `core.events.emit(...)`. Handlers registrados en `modules/<x>/service.py` al importar el módulo (`core/events.subscribe`).
- `models` → `core.db.Base`, `core.crypto.types`. Nada más.

Puertos (interfaces `Protocol`) y sus adaptadores:

| Puerto | Dónde | Adaptadores |
|---|---|---|
| `KeyProvider` | `core/crypto/provider.py` | `LocalFileProvider` (v0.1), `OpenBaoProvider` (v0.2) |
| `NotificationChannel` | `modules/notifications/channels/base.py` | `EmailChannel`, `WhatsAppLinkChannel` (v0.2), `WebPushChannel` (v1.0, Q14). Telegram no es canal al socio (N-34) |
| `StorageProvider` | `modules/attachments/storage/base.py` | `LocalDiskStorage` (v0.3), `S3CompatibleStorage` (v0.3) |
| `Clock` | `core/clock.py` | `SystemClock`, `FrozenClock` (tests) |
| `PrincipalLoader` (G-02) | `core/security.py`, con `Principal(user_id, role, member_id)` y `register_principal_loader()` | `auth.service.get_principal`, registrado en `create_app()`; el arranque falla sin cargador; el rol vale el de la base; `SYSTEM_USER_ID` se rechaza |
| `AlertSink` (G-08) | `core/alerts.py`, con `register_sink()` y `alert(kind, text)` | `LogAlertSink` (v0.1, por defecto); `TelegramAlertSink` en `modules/notifications/channels/telegram.py` (v0.2), registrado en `main.py` y `worker/main.py` |
| `Reencryptor` (G-09) | `core/crypto/registry.py`, con `count_pending` y `reencrypt_batch` | cada módulo con blobs fuera de columnas lo registra al importarse; `attachments` en v0.3. Hasta entonces, rotar `attachment.sensitive` responde 409 `rotation_not_supported` |

## 2. Árbol de `api/`

```
api/
  pyproject.toml                 uv, ruff (+banned-api), mypy --strict, pytest asyncio_mode=auto
  alembic.ini
  migrations/
    env.py                       incluye todos los esquemas; target_metadata = Base.metadata
    versions/
  src/app/
    main.py                      create_app(): routers, middlewares, startup (migraciones, DEKs)
    cli.py                       typer: init-keys, seed, seed --demo, import-members, rotate-key,
                                 verify-audit, sign-audit, migrate-provider, cbom
    core/
      config.py                  Settings (pydantic-settings) desde .env; extra="forbid"; NON_API_ENV_VARS
      db.py                      engine async, async_session, Base, CommonColumnsMixin
      clock.py                   Clock Protocol, SystemClock, FrozenClock, today_bogota()
      context.py                 SYSTEM_USER_ID, current_actor, current_batch, request_id_var,
                                 actor_scope(), batch_scope() (solo biblioteca estándar; G-01)
      security.py                argon2id, JWT Ed25519, Principal, PrincipalLoader, require_role,
                                 new_opaque_token(), hash_opaque_token()
      jobs.py                    JobRun (worker.job_runs), claim_run, finish_run, last_run (G-06)
      alerts.py                  AlertSink, register_sink, alert, LogAlertSink (G-08)
      ratelimit.py               limitador por IP (login, forgot)
      events.py                  bus en memoria
      audit.py                   record(), hook after_flush, chain_hash
      errors.py                  envelope de error, handlers de excepciones
      logging.py                 JSON a stdout, filtro de campos sensibles
      crypto/
        registry.py              registro de data_class (constantes, N-04) y puerto Reencryptor (G-09)
        digest.py                digest(data) SHA-256 sin dependencias; lo usa core/audit (N-06)
        archive.py               digest_file(path), verify_age_archive(path, identity) por subprocess
                                 sobre el binario age (G-07)
        provider.py              KeyProvider Protocol: wrap(key_ref, dek), unwrap(key_ref, wrapped), sign, verify, rotate
        local_provider.py        LocalFileProvider
        openbao_provider.py      OpenBaoProvider (v0.2)
        models.py                crypto_keys, crypto_ops, crypto_jobs
        bus.py                   CryptoBus: encrypt, decrypt, blind_index, sign, verify
        types.py                 Encrypted(data_class), BlindIndexed(data_class)
        router.py                /crypto/* solo admin (v0.3)
        service.py               rotate, reencrypt por lotes, cbom
    modules/
      auth/        router schemas models service exceptions
      settings/    router schemas models service
      members/     router schemas models service exceptions
      plans/       router schemas models service exceptions
      memberships/ router schemas models service exceptions
      payments/    router schemas models service exceptions
      audit/       router schemas service          (models viven en core/audit.py)
      dashboard/   router schemas service          (sin models)
      notifications/ router schemas models service channels/
      attachments/ router schemas models service storage/
      classes/     router schemas models service exceptions
      wods/        router schemas models service
      results/     router schemas models service exceptions
      athletes/    router schemas models service
      tv/          router schemas service          (sin models)
      portal/      router schemas service          (sin models)
    worker/
      main.py                    APScheduler, 07:00 America/Bogota
      jobs/expirations.py notify.py sign_audit.py backup_check.py
  tests/
    conftest.py                  Postgres de prueba (compose.dev), sesión por test con rollback,
                                 FrozenClock, factories
    architecture/                corre en todos los gates: test_no_cross_models.py, test_every_route_has_role.py,
                                 test_banned_imports.py, test_core_import_direction.py,
                                 test_service_import_graph.py (lista blanca de G-03), ...
    core/ crypto/ auth/ members/ plans/ memberships/ payments/ audit/ ...
```

## 3. Contratos de los services principales (v0.1)

Firmas en pseudocódigo Python; los tipos exactos van en `schemas.py` y `models.py`.

### auth.service
- `login(email, password, ip) -> TokenPair` — rate limit, argon2 verify, usuario activo y no bloqueado, refresh en tabla.
- `refresh(refresh_token) -> TokenPair` — rota el refresh (revoca el anterior).
- `logout(refresh_token) -> None`
- `me(user) -> UserOut`
- `create_user(data, by) -> User` — admin; si `role = member` exige `member_id`; genera `OneTimeToken(activate)` y devuelve el enlace.
- `forgot(email) -> None` — siempre 204; genera `OneTimeToken(reset)` si existe; en v0.1, hasta que exista el canal de correo, el admin obtiene el enlace con `resend_link` (`POST /users/{id}/resend-link`), que genera un token nuevo e invalida el anterior. No existe `GET /users/{id}/activation-link` (N-12).
- `reset(token, new_password) -> None`
- `lock(user_id, by)`, `revoke_sessions(user_id, by)`, `resend_link(user_id, by) -> str`
- Regla: no se puede bloquear ni borrar al último admin activo.

### settings.service
- `get_section(key) -> dict`, `update_section(key, value, by) -> dict` — valida con el esquema de la sección y `version` (409 `version_conflict`, N-17); `tv.regenerate_token(by) -> str`.
- Secciones de v0.1 (Q11, N-18): `gym`, `hours`, `payment_methods`, `memberships` (`expiring_days` y los límites `max_freeze_days_per_membership`, `max_freezes_per_membership`, `max_retroactive_days`), `classes` (`default_capacity`, `checkin_window_min`), `tv`, `privacy`. `channels` llega en v0.2 y solo guarda lo no secreto (Q12). Una sección futura responde 404 `section_not_available`.
- `memberships_policy() -> MembershipsPolicy` — lo usa `memberships.service` para `expiring_days` y los límites; `current_privacy_version() -> str` para `privacy.policy_version`.
- `payment_methods()` devuelve el enum fijo en v0.1 (S8) decorado con etiquetas de la sección; se expone en `GET /payments/methods` (US-056).

### members.service
- `list(q, status, membership_status, plan_id, limit, offset, sort) -> Page[MemberRow]` — `q` se normaliza y se busca por `document_idx`, `phone_idx`, `email_idx` o `ILIKE` en nombre; `membership_status` se resuelve pidiendo a `memberships.service.status_for(ids)`.
- `create(data, by) -> Member` — verifica duplicado por `document_idx` entre no borrados; devuelve el id del existente en el error (`Field` del diseño enlaza al registro).
- `get(id, by) -> MemberDetail` — campos cifrados enmascarados por defecto.
- `reveal(id, field, by) -> str` — admin y coach (Q6); descifra un campo y audita `reveal` con el campo y el usuario (RN-13). El enmascarado de la ficha se calcula en memoria al leer (propósito `mask` en `crypto_ops`) y nunca se persiste; las listas no muestran datos cifrados ni enmascarados (N-01).
- `reactivate(id, by)` — admin; deshace la baja (N-20). Admin y coach ven a los dados de baja en la lista y en la ficha, en solo lectura; solo admin cambia el documento.
- `update(id, data, by)`, `deactivate(id, by)` (admin), `export(filters, by) -> CSV` (admin, audita `export`, v0.2).
- `contact_for_notification(id, purpose) -> Contact` — para notifications, audita con propósito.

### plans.service
- `list(q, active, limit, offset)`, `create`, `update`, `set_active(id, bool, by)`, `deactivate_or_fail(id, by)` — consulta `memberships.service.count_active_by_plan`.
- `validate_plan(kind, duration_days, class_count)` pura.

### memberships.service
- `sell(member_id, plan_id, start_date, first_payment: PaymentIn | None, by, renew: bool = False, max_retroactive_days: int | None = None) -> Membership` — valida socio activo y la invariante de Q1 (una vigente y una futura); copia precio; calcula `end_date`; crea en `pending_payment`; si hay `first_payment`, llama a `payments.service.register(...)` en la misma sesión (con `flush` antes de emitir); el evento `PaymentRegistered` activa si cubre. Con `renew = True` ignora `start_date` y usa `next_start_for_renewal`. El router pasa `max_retroactive_days` de Settings; seed e importación pasan `None` (N-24).
- Renovar no es una operación aparte (Q2): `renewal_preview(member_id) -> {start_date, current_end_date}` alimenta la vista previa del front.
- `freeze(id, frozen_from, frozen_to, by)` — admin y coach (Q7), con los límites de `settings.service.memberships_policy()`; `cancel(id, reason, by)` (admin).
- `payability(membership_id) -> MembershipPayability(exists, cancelled, member_id)` — puerto que `payments` registra con `set_membership_gate` (G-03).
- `list(status, q, plan_id, ends_from, ends_to, member_id, limit, offset)`, `get(id)`, `summary() -> {active, expiring, expired, frozen, pending_payment}`.
- `status_for(member_ids) -> dict[member_id, {status, plan_id, plan_name, end_date}]` — lectura a profundidad 2 (G-04): resuelve nombres con `plans.service.names_for`; `member_ids_by_status(statuses, plan_id) -> set[UUID]`; `count_active_by_plan(plan_id) -> int`.
- `recompute_statuses(today) -> list[events]` — usada por el worker.
- Handlers: `on_payment_registered`, `on_payment_voided`, `on_member_checked_in` (v0.4), `on_attendance_removed` (v0.4).
- Puras: `compute_end_date`, `compute_status(membership, freezes, today, expiring_days)`, `apply_freeze(membership, freezes, frozen_from, frozen_to, limits)`, `next_start_for_renewal`, `is_covered`.

### payments.service
- `register(membership_id, amount_cop, method, reference, paid_at, by) -> Payment` — valida membresía no cancelada; emite `PaymentRegistered`.
- `void(id, reason, by) -> Payment` (admin) — una sola vez; emite `PaymentVoided`.
- `list(q, from, to, method, registered_by, voided, member_id, membership_id, limit, offset)`, `get(id)`, `summary(month) -> {total, by_method, voided_count}`.
- `receipt_pdf(id, by) -> bytes` (v0.2, audita).

### audit.service
- `list(from, to, user_id, table, record_id, action, q, limit, offset)`, `get(seq)`, `verify(by) -> VerifyResult` (admin; corre en hilo aparte si hay más de 100.000 filas), `last_verification()`; cada verificación se persiste en `audit.verifications` con `broken_at_seq` (N-30). `list_for_subject(member_id)` alimenta el historial de la ficha con `members`, `memberships` y `payments` del socio (G-05, N-31); `recent(tables, limit)` alimenta "últimos movimientos" (Q10).

### dashboard.service
- `summary(today) -> DashboardOut` — compone `memberships.summary()`, `payments.summary(month)`, y desde v0.2/v0.4/v0.5 `notifications.today_count()`, `classes.today()`, `wods.today()`. Campos ausentes vienen `null`.

### core.crypto.bus
- `encrypt(data_class, plaintext: bytes, aad: bytes) -> str` (blob `apx1.<key_id>.<alg>.<nonce>.<ct>`)
- `decrypt(blob: str, aad: bytes) -> bytes`
- `blind_index(data_class, value: str) -> str`
- `sign(data_class, data: bytes) -> str` (formato `apx1.<key_id>.<alg>.<sig_b64url>`, N-04), `verify(data_class, data, signature) -> bool`
- `digest(data: bytes) -> str` (SHA-256, `core/crypto/digest.py`; lo usa `core/audit`, N-06); `digest_file(path)` y `verify_age_archive(path, identity)` desde v0.2 (G-07).
- Registro en `crypto_ops` por operación, con `purpose` cuando aplica (N-21); en lotes, un `batch_id` y `count` por lote (N-05). Actor: `current_actor()` de `core/context.py` (G-01).

## 4. Contrato HTTP (v0.1, prefijo `/api/v1`)

Convenciones: JSON; `limit` (1 a 200, por defecto 25) y `offset`; respuesta de lista `{ "items": [...], "total": n, "limit": l, "offset": o }`; errores `{ "error": { "code": "...", "message": "...", "field": "..."? , "existing_id": "..."? } }`; fechas ISO 8601 en UTC; dinero entero.

Público: `GET /health`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/forgot`, `POST /auth/reset`.

Admin y coach salvo nota:
- Auth: `POST /auth/logout`, `GET /auth/me`, `POST /auth/me/password`.
- Usuarios (admin): `GET/POST /users`, `GET/PATCH/DELETE /users/{id}`, `POST /users/{id}/lock`, `POST /users/{id}/unlock`, `POST /users/{id}/revoke-sessions`, `POST /users/{id}/resend-link` (única ruta para obtener un enlace, N-12).
- Settings (admin): `GET /settings/{section}`, `PATCH /settings/{section}`, `POST /settings/tv/regenerate-token`.
- Members: `GET /members`, `POST /members`, `GET /members/{id}`, `PATCH /members/{id}`, `DELETE /members/{id}` (admin), `POST /members/{id}/reactivate` (admin, N-20), `POST /members/{id}/reveal` `{field}` (admin y coach, Q6), `GET /members/{id}/memberships`, `GET /members/{id}/memberships/renewal-preview`, `GET /members/{id}/payments`, `GET /members/{id}/audit`, `POST /members/{id}/memberships` (sell: `first_payment` opcional y `renew: true` para renovar; D5 y Q2), `GET /members/export` (admin, v0.2).
- Plans (admin): `GET/POST /plans`, `GET/PATCH /plans/{id}`, `POST /plans/{id}/activate`, `POST /plans/{id}/deactivate`. Coach: solo `GET /plans?active=true` para vender.
- Memberships: `GET /memberships`, `GET /memberships/summary`, `GET /memberships/{id}`, `POST /memberships/{id}/freeze` (admin y coach), `POST /memberships/{id}/cancel` (admin), `POST /memberships/{id}/payments` (409 `membership_cancelled` si está anulada). No existe una ruta `/renew` sobre membresías (Q2).
- Payments: `GET /payments`, `GET /payments/summary?month=`, `GET /payments/methods`, `GET /payments/{id}`, `POST /payments/{id}/void` (admin), `GET /payments/{id}/receipt.pdf` (v0.2, audita `download`).
- Audit (admin): `GET /audit`, `GET /audit/{seq}`, `POST /audit/verify`, `GET /audit/verify/last` (N-30).
- Dashboard: `GET /dashboard`.

Las rutas que `ROUTES.md` nombra distinto se mapean así y `ROUTES.md` se actualiza al exportar `docs/openapi.json`:
`POST /payments` → `POST /memberships/{id}/payments`; `/payments/summary` se mantiene; `POST /memberships` (vender) → `POST /members/{id}/memberships`; `?renovar=1` del front → `renew: true` en el cuerpo del mismo endpoint; `page`/`page_size` → `limit`/`offset` (D2, ya aplicado en `ROUTES.md` y `DESIGN.md`).

## 5. Front (`web/`)

```
web/
  package.json                   react 19, react-router 7, @tanstack/react-query 5,
                                 react-hook-form 7, zod 3, lucide-react, vite 6, vitest,
                                 @testing-library/react, playwright
  src/
    core/
      styles/tokens.css          copia de docs/design/tokens.css
      api/client.ts              fetch con base /api/v1, refresh automático, envelope de error
      api/types.ts               generado desde docs/openapi.json (openapi-typescript)
      auth/                      sesión, roles, guardas de ruta
      i18n/format.ts             $ 120.000, 20 oct 2026, hora Bogotá
    shared/ui/                   TopBar SideNav PageHeader Button StatusTag FilterBar DataTable
                                 Pagination Chips Tabs KpiCard SidePanel ConfirmModal Field
                                 MaskedValue HistoryAside
    layouts/                     PanelLayout, PortalLayout, GymLayout (oscuro), TvLayout
    features/
      auth/ members/ plans/ memberships/ payments/ dashboard/ system/
      classes/ wods/ results/ athletes/ notifications/ portal/ tv/
    routes.tsx                   mapa de ROUTES.md
  public/brand/                  logos
  public/fonts/                  Michroma, Titillium Web (respaldo local)
  tests/e2e/                     Playwright: login, socios, vender, pago, check-in
```

Reglas: cada `feature` tiene `api.ts` (hooks de TanStack Query), `schemas.ts` (Zod), `pages/`, `components/`. Nada de colores literales. `DESIGN-GAP:` cuando falte algo.

## 6. Pruebas por capa

- **Puras:** funciones de regla de negocio, sin base. Rápidas, cientos.
- **Service con base real:** PostgreSQL de `compose.dev.yml`, una transacción por test con rollback; verifican invariantes, triggers, eventos y auditoría.
- **Router:** `httpx.AsyncClient` contra la app; verifican rol, validación y envelope.
- **Arquitectura:** imports cruzados, rutas sin rol, imports prohibidos, blob cifrado nunca en claro en la base (`SELECT document FROM members` no contiene el valor).
- **Worker:** jobs con `FrozenClock`.
- **Front:** Vitest + Testing Library por componente compartido y por página; Playwright para los cinco flujos críticos; capturas en 320, 768, 1024 y 1440 en claro y oscuro.
- Umbral: 80 % en `src/` del API y del front (`CLAUDE.md` y reglas globales).

## 7. Infraestructura mínima del Sprint 0

- `infra/compose.yml` (web, api, worker, db, backup) y `infra/compose.dev.yml` (puertos abiertos, hot reload, `db_test`).
- `api/Dockerfile` multi-stage con `uv`, usuario no root.
- `web/Dockerfile` (build de Vite) o build en CI copiado a la imagen de Nginx.
- `infra/nginx/default.conf`.
- `scripts/workflow/slice-gate.sh`, `checkpoint-commit.sh`, `run-gates.sh`, `validate-impact-analysis.sh` (los gates del flujo, creados aquí para los sprints siguientes).
- `.github/workflows/ci.yml`: ruff, mypy, pytest con servicio Postgres, pip-licenses, license-checker del front, build de imágenes.
