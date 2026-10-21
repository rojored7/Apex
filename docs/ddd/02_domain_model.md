# 02 · Modelo de dominio

Fecha: 21 de octubre de 2026. Entrada: `01_product_discovery.md`.

Convención: en este proyecto el modelo de dominio se implementa directamente sobre los modelos de SQLAlchemy de cada módulo (`CLAUDE.md`, regla de módulos 5: no se crean entidades separadas ni repositorios abstractos por tabla). Los aggregates de este documento son la unidad de consistencia transaccional y la frontera que `service.py` protege; las reglas viven en funciones puras de `service.py` que se prueban sin base de datos.

## 1. Lenguaje ubicuo

- **Socio (Member):** persona inscrita en el gimnasio. Puede o no tener membresía.
- **Plan:** producto que se vende: nombre, precio, tipo por días o por clases.
- **Membresía (Membership):** un plan vendido a un socio con fechas y precio pactado.
- **Pago (Payment):** dinero recibido contra una membresía; inmutable.
- **Anular (void):** marcar un pago como inválido con motivo; no lo borra.
- **Congelar (freeze):** pausar una membresía entre dos fechas; extiende el fin.
- **Al día / Por vencer / Vencido / Congelado / Cancelado:** estados de membresía.
- **Sin plan:** socio sin membresía vigente.
- **Clase (ClassSession):** instancia de entrenamiento en una fecha y hora, con coach y cupo.
- **Franja (ClassSlot):** plantilla semanal desde la que se generan las clases.
- **Asistencia (Attendance):** un socio estuvo en una clase (check-in).
- **Movimiento (Movement):** ejercicio del catálogo (back squat, pull-up…).
- **WOD:** entrenamiento del día, compuesto de movimientos con reps y cargas RX.
- **Benchmark:** WOD de referencia que se repite para medir progreso.
- **Resultado (WodResult):** marca de un socio en un WOD; nivel RX, RX+ o escalado.
- **Récord (PersonalRecord):** mejor marca de un socio en un movimiento (RM) o en un benchmark.
- **Medida (BodyMetric):** peso y medidas corporales del socio; cifradas.
- **Aviso (Notification):** mensaje generado por una regla para un socio por un canal.
- **Regla de aviso (NotificationRule):** cuándo avisar relativo al vencimiento.
- **Clase de dato (data_class):** etiqueta como `member.document` que decide qué llave cifra un campo.
- **Llave (CryptoKey):** DEK envuelta por el proveedor; tiene versión y estado.
- **Usuario (User):** cuenta con rol admin, coach o member; un usuario member apunta a un socio.
- **Auditoría (AuditEntry):** registro encadenado por hash de un cambio en una tabla auditada.

## 2. Aggregates, entidades y value objects

Cada aggregate lista su raíz, sus entidades internas, sus value objects, sus invariantes y los eventos que emite. Los identificadores son UUID. Toda tabla lleva `created_at`, `updated_at`, `created_by` (mixin común).

### 2.1 Member (raíz: Member)

- **Entidad raíz `Member`:** `first_name`, `last_name` (en claro: van al leaderboard), `sex` (`f` | `m` | `x` | null), `status` (`active` | `inactive`), `notes`, `deleted_at`, `data_consent_at`, `data_consent_version`.
- **Value objects cifrados** (tipo de columna `Encrypted(data_class)`): `Document` (`member.document`, con índice ciego), `Phone` (`member.phone`, índice ciego), `Email` (`member.email`, índice ciego), `BirthDate` (`member.birth_date`), `EmergencyContact` (`member.emergency_contact`, JSON nombre y teléfono).
- **Entidad interna `PushSubscription`** (v0.2): endpoint, llaves, `channel_enabled`.
- **Entidad interna `MemberChannelPreference`** (v0.2): canal, activo.
- **Invariantes:** documento único entre socios no borrados (por índice ciego); `first_name` y `last_name` no vacíos; `data_consent_at` obligatorio para crear desde v0.3 (cuando exista el adjunto de autorización; antes es opcional con aviso).
- **Eventos:** `MemberCreated`, `MemberUpdated`, `MemberDeactivated`, `SensitiveFieldRevealed(member_id, field, user_id)`.
- **Consulta derivada (no persistida):** `membership_status` del socio = estado de su última membresía no cancelada, o `none` si no tiene. Lo calcula el service de memberships; el service de members lo pide para la lista.

### 2.2 Plan (raíz: Plan)

- **Raíz `Plan`:** `name`, `price_cop` (int > 0), `kind` (`days` | `classes`), `duration_days` (int > 0), `class_count` (int > 0 si `kind = classes`, null si no), `is_active`, `deleted_at`.
- **Value object `Money`:** entero en COP, nunca negativo, sin decimales (RN-01).
- **Invariantes:** `kind = classes` exige `class_count`; `duration_days` siempre presente (P2: los planes por clases tienen vigencia máxima); no se borra lógicamente un plan con membresías activas (RN-08): se desactiva.
- **Eventos:** `PlanCreated`, `PlanUpdated`, `PlanDeactivated`.

### 2.3 Membership (raíz: Membership)

- **Raíz `Membership`:** `member_id`, `plan_id`, `agreed_price_cop` (copia, RN-04), `start_date`, `end_date`, `classes_total`, `classes_remaining`, `status` (`pending_payment` | `active` | `expiring` | `expired` | `frozen` | `cancelled`), `frozen_from`, `frozen_to`, `cancel_reason`, `cancelled_by`, `cancelled_at`.
- **Value object `DateRange`:** `start_date ≤ end_date`.
- **Value object `FreezeWindow`:** `frozen_from ≤ frozen_to`, dentro de la vigencia, una sola congelación vigente a la vez.
- **Invariantes:**
  - Nace en `pending_payment`; pasa a `active` solo por RN-03 (pagos cubren precio).
  - `end_date = compute_end_date(start_date, plan)`: por días `start + duration_days`; por clases también `start + duration_days` y además `classes_remaining` baja con cada asistencia (RN-05).
  - `compute_status(membership, today)` es función pura (RN-06): `cancelled` es terminal; si hay ventana de congelación que contiene `today` → `frozen`; si `today > end_date` o `classes_remaining = 0` → `expired`; si `end_date - today ≤ 7` → `expiring`; si no → `active`. `pending_payment` no cambia por fecha.
  - `freeze(from, to)` extiende `end_date` en `(to - from) + 1` días (RN-07). Solo sobre `active` o `expiring`.
  - Un socio puede tener como máximo una membresía en `pending_payment`, `active`, `expiring` o `frozen` a la vez. Renovar crea una membresía nueva cuyo `start_date` es el día siguiente al `end_date` de la vigente si aún no venció, o hoy si ya venció.
  - `cancel(reason)` exige motivo no vacío; solo admin.
- **Operación de dominio `sell(member_id, plan_id, start_date, first_payment?)`:** crea la membresía y, si viene `first_payment`, registra el pago en la misma transacción (S5). Es la única entrada para vender y renovar.
- **Eventos:** `MembershipSold`, `MembershipActivated`, `MembershipExpiring`, `MembershipExpired`, `MembershipFrozen`, `MembershipCancelled`, `ClassConsumed`.

### 2.4 Payment (raíz: Payment)

- **Raíz `Payment`:** `membership_id`, `amount_cop` (Money > 0), `method` (`cash` | `nequi` | `breb`), `reference` (opcional, para Nequi y Bre-B), `paid_at`, `registered_by`, `voided` (bool), `void_reason`, `voided_by`, `voided_at`.
- **Invariantes:** RN-02: ninguna columna cambia después de crear salvo las cuatro de anulación, y solo una vez; trigger de PostgreSQL rechaza `UPDATE` de cualquier otra columna y todo `DELETE`. Anular exige motivo. Un pago anulado no suma para RN-03.
- **Eventos:** `PaymentRegistered(membership_id, amount_cop)`, `PaymentVoided(membership_id, payment_id)`.
- **Reacción:** `memberships` escucha `PaymentRegistered` y `PaymentVoided` y recalcula cobertura. Si al anular la cobertura cae por debajo del precio y la membresía estaba `active`, vuelve a `pending_payment` y se emite `MembershipActivationReverted`.

### 2.5 ClassSlot y ClassSession (dos raíces, v0.4)

- **Raíz `ClassSlot`:** `weekday` (0 a 6), `start_time`, `duration_min`, `capacity`, `default_coach_id` (user), `is_active`. Es la plantilla semanal.
- **Raíz `ClassSession`:** `slot_id` (null si es sesión extra), `starts_at` (TIMESTAMPTZ), `duration_min`, `capacity`, `coach_id`, `wod_id` (null hasta que se asigne), `status` (`scheduled` | `cancelled` | `done`), `cancel_reason`.
- **Entidad interna de `ClassSession`: `Attendance`:** `member_id`, `checked_in_at`, `checked_in_by`, `membership_status_at_checkin` (`active` | `expiring` | `expired` | `frozen` | `none`), `flagged` (bool).
- **Invariantes:** una asistencia por sesión y socio (RN-10); el check-in nunca falla por estado de membresía (RN-09): registra y marca `flagged`; no se puede hacer check-in en una sesión `cancelled`; el cupo es advertencia, no bloqueo (el coach decide).
- **Eventos:** `SessionGenerated`, `SessionCancelled`, `MemberCheckedIn(member_id, session_id, flagged)`, `AttendanceRemoved`.
- **Reacción:** `memberships` escucha `MemberCheckedIn` y, si la membresía vigente es por clases, descuenta una clase (`ClassConsumed`); si `AttendanceRemoved`, la devuelve.

### 2.6 Movement (raíz: Movement, v0.5)

- **Raíz `Movement`:** `name` (único), `category` (`weightlifting` | `gymnastics` | `monostructural` | `other`), `unit` (`kg` | `reps` | `m` | `cal` | `s`), `is_active`.
- **Invariante:** nombre único; no se borra, se desactiva.

### 2.7 Wod (raíz: Wod, v0.5)

- **Raíz `Wod`:** `date`, `title`, `score_type` (`time` | `rounds_reps` | `reps` | `load`), `time_cap_s`, `is_benchmark`, `description`.
- **Entidad interna `WodMovement`:** `movement_id`, `order`, `reps`, `load_rx_m_kg`, `load_rx_f_kg`, `notes`. Copia de valores: cambiar el catálogo después no cambia WODs pasados.
- **Invariantes:** un WOD principal por fecha (sesiones de ese día lo heredan; se puede asignar otro a una sesión concreta); `score_type` decide qué campos del resultado son obligatorios.
- **Eventos:** `WodPublished`.

### 2.8 WodResult (raíz: WodResult, v0.5)

- **Raíz `WodResult`:** `wod_id`, `member_id`, `session_id` (opcional), `level` (`rx` | `rx_plus` | `scaled`), `seconds`, `rounds`, `reps`, `load_kg`, `scaled_notes`, `status` (`validated` | `pending`), `recorded_by`, `validated_by`, `validated_at`.
- **Value object `Score`:** según `score_type` del WOD: `time` exige `seconds`; `rounds_reps` exige `rounds` y `reps`; `reps` exige `reps`; `load` exige `load_kg`. Ordenamiento del leaderboard: tiempo ascendente, los demás descendente; `scaled` siempre después de `rx` y `rx_plus`.
- **Invariantes:** uno por WOD y socio (RN-11); nace `validated` si lo registra coach o admin, `pending` si lo envía el socio; `validate` solo coach o admin; nunca se borra (RN-14), se corrige con un nuevo registro que reemplaza (`supersedes_id`).
- **Eventos:** `WodResultRecorded(member_id, wod_id, load_kg, movements)`, `WodResultValidated`.

### 2.9 AthleteProfile (raíz lógica: Member; dos entidades, v0.6)

- **Entidad `BodyMetric`:** `member_id`, `measured_at`, `weight_kg` (cifrado, `athlete.metric`), `height_cm`, `body_fat_pct`, `notes`, `recorded_by`.
- **Entidad `PersonalRecord`:** `member_id`, `kind` (`rm` | `benchmark`), `movement_id` (si `rm`), `wod_id` (si `benchmark`), `value` (carga en kg o Score), `achieved_at`, `source` (`manual` | `derived`), `result_id` (si derivado).
- **Invariantes:** RN-12: un `WodResultValidated` con `load_kg` mayor al RM vigente del movimiento principal crea un `PersonalRecord` derivado; los manuales los registra coach o admin; nunca se borran.
- **Eventos:** `PersonalRecordSet`.

### 2.10 Notification (raíces: NotificationRule, NotificationTemplate, Notification; v0.2)

- **Raíz `NotificationRule`:** `name`, `trigger` (`membership_expiring` | `membership_expired`), `offset_days` (negativo antes, positivo después: -3, 0, 1, 7, 15), `channel` (`push` | `email` | `telegram` | `whatsapp_link`), `template_id`, `is_active`.
- **Raíz `NotificationTemplate`:** `name`, `subject`, `body` con variables (`{nombre}`, `{plan}`, `{vence}`, `{dias}`).
- **Raíz `Notification`:** `rule_id`, `member_id`, `membership_id`, `target_date`, `channel`, `status` (`pending` | `sent` | `failed` | `skipped`), `rendered_body`, `attempts`, `last_error`, `sent_at`, `sent_by` (usuario si fue manual), `skip_reason`.
- **Invariantes:** RN-17: única por (`rule_id`, `membership_id`, `target_date`); respeta las preferencias de canal del socio; `whatsapp_link` no envía nada: genera el `wa.me` y pasa a `sent` cuando el usuario lo abre; `skip` exige motivo.
- **Eventos:** `NotificationQueued`, `NotificationSent`, `NotificationFailed`, `NotificationSkipped`.

### 2.11 User (raíz: User)

- **Raíz `User`:** `email` (único), `password_hash` (argon2id), `role` (`admin` | `coach` | `member`), `member_id` (obligatorio si `role = member`, null si no), `is_active`, `locked_at`, `deleted_at`.
- **Entidad interna `RefreshToken`:** `token_hash`, `expires_at`, `revoked_at`, `user_agent`.
- **Entidad interna `OneTimeToken`:** `token_hash`, `purpose` (`activate` | `reset`), `expires_at`, `used_at`.
- **Invariantes:** un token de un solo uso se consume una vez; revocar sesiones revoca todos los refresh tokens; bloquear impide login y revoca sesiones; no se puede borrar el último admin activo.
- **Eventos:** `UserCreated`, `UserLocked`, `SessionsRevoked`, `PasswordChanged`.

### 2.12 AuditEntry (raíz: AuditEntry; append-only)

- **Raíz `AuditEntry`:** `seq` (bigserial), `at`, `user_id`, `action` (`insert` | `update` | `delete` | `reveal` | `export` | `login` | `verify`), `table_name`, `record_id`, `before` (JSON, campos cifrados se guardan como blob), `after`, `prev_hash`, `hash`.
- **Entidad `AuditSignature`** (v0.3): `through_seq`, `hash`, `signature` (ML-DSA), `key_id`, `signed_at`.
- **Invariantes:** RN-16: `hash = SHA-256(prev_hash || canonical(row))`; nunca `UPDATE` ni `DELETE` (trigger); la verificación recorre toda la cadena.

### 2.13 CryptoKey y CryptoOp (raíces; append-only para ops)

- **Raíz `CryptoKey`:** `purpose` (`encrypt` | `index` | `sign`), `data_class`, `algorithm` (`A256GCM` | `HMAC-SHA256` | `Ed25519` | `ML-DSA-65`), `provider` (`local` | `openbao`), `version`, `state` (`active` | `decrypt_only` | `retired`), `wrapped_material`, `rotated_at`, `rotate_by`.
- **Raíz `CryptoOp`:** `at`, `user_id`, `verb` (`encrypt` | `decrypt` | `index` | `sign` | `verify` | `wrap` | `unwrap` | `rotate`), `data_class`, `key_id`, `key_version`, `record_id`, `result` (`ok` | `error`), `batch_id`.
- **Entidad `CryptoJob`:** `kind` (`rotate` | `reencrypt` | `migrate_provider`), `data_class`, `status`, `total`, `done`, `started_at`, `finished_at`, `error`.
- **Invariantes:** una sola llave `active` por (`purpose`, `data_class`); rotar deja la anterior en `decrypt_only` hasta que el `CryptoJob` termine y la retire; el material en claro nunca se persiste.

### 2.14 Settings (raíz: SettingsSection)

- **Raíz `SettingsSection`:** `key` (`gym` | `hours` | `payment_methods` | `channels` | `classes` | `memberships` | `tv` | `privacy`), `value` (JSON validado por un esquema Pydantic por sección), `version`.
- **Invariantes:** cada sección tiene esquema propio; `tv.device_token` se genera, no se escribe; auditado.

### 2.15 Attachment (raíz: Attachment, v0.3)

- **Raíz `Attachment`:** `owner_table`, `owner_id`, `kind` (`photo` | `consent` | `other`), `filename_random`, `mime`, `size_bytes`, `sensitive` (cifrado vía `attachment.sensitive`), `uploaded_by`.
- **Invariantes:** máximo 5 MB; validación por bytes mágicos; nombre aleatorio; descarga solo con rol y auditada.

## 3. Catálogo de eventos de dominio

| Evento | Emisor | Suscriptores |
|---|---|---|
| `MemberCreated` | members | notifications (bienvenida, v0.2), auth (activación de portal, v1.0) |
| `SensitiveFieldRevealed` | members, athletes | audit |
| `MembershipSold` | memberships | payments (si trae `first_payment`, en la misma transacción) |
| `PaymentRegistered` | payments | memberships (RN-03) |
| `PaymentVoided` | payments | memberships (revertir activación) |
| `MembershipActivated` | memberships | notifications (confirmación) |
| `MembershipExpiring` | worker expirations | notifications |
| `MembershipExpired` | worker expirations | notifications |
| `MembershipFrozen` / `MembershipCancelled` | memberships | notifications (opcional) |
| `MemberCheckedIn` | classes | memberships (descontar clase si aplica) |
| `AttendanceRemoved` | classes | memberships (devolver clase) |
| `WodResultValidated` | results | athletes (RN-12) |
| `PersonalRecordSet` | athletes | notifications (v1.0, push al socio) |
| `NotificationSent` / `Failed` / `Skipped` | notifications | audit |
| `UserLocked` / `SessionsRevoked` | auth | audit |

Los handlers corren en la misma transacción del emisor (bus en memoria, `core/events.py`). Si un handler falla, la transacción completa se revierte.

## 4. Reglas de negocio como funciones puras (contrato de pruebas)

Cada una se implementa en el `service.py` de su módulo sin tocar la base, y tiene prueba unitaria.

- `plans.validate_plan(kind, duration_days, class_count) -> None | PlanError`
- `memberships.compute_end_date(start_date, plan) -> date`
- `memberships.compute_status(membership, today) -> MembershipStatus`
- `memberships.apply_freeze(membership, frozen_from, frozen_to) -> Membership`
- `memberships.next_start_for_renewal(current, today) -> date`
- `memberships.is_covered(agreed_price_cop, payments) -> bool`
- `payments.can_void(payment) -> bool`
- `classes.checkin_outcome(membership_status) -> (allowed=True, flagged: bool)`
- `results.validate_score(score_type, seconds, rounds, reps, load_kg) -> None | ScoreError`
- `results.leaderboard_order(score_type) -> key function`
- `athletes.derive_record(result, current_rm) -> PersonalRecord | None`
- `notifications.target_dates(rule, membership) -> list[date]`
- `notifications.render(template, context) -> str`
- `audit.chain_hash(prev_hash, row) -> str`
- `crypto.normalize_for_index(value) -> str` (minúsculas, sin espacios ni puntos)
- `settings.validate_section(key, value) -> None | SettingsError`

## 5. Clases de dato cifradas

| data_class | Campo | Índice ciego | Versión |
|---|---|---|---|
| `member.document` | `members.document` | sí | v0.1 |
| `member.phone` | `members.phone` | sí | v0.1 |
| `member.email` | `members.email` | sí | v0.1 |
| `member.birth_date` | `members.birth_date` | no | v0.1 |
| `member.emergency_contact` | `members.emergency_contact` | no | v0.1 |
| `athlete.metric` | `body_metrics.weight_kg` y medidas | no | v0.6 |
| `attachment.sensitive` | archivos marcados sensibles | no | v0.3 |
| `audit.signature` | llave de firma de auditoría (sign) | no aplica | v0.3 |
| `backup.signature` | llave de firma de backups (sign) | no aplica | v1.0 |
