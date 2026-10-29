// Revisión del Sprint 2 (M7 de la revisión general, parte front): los `code` del envelope de
// error que el front reconoce, en un solo lugar. Antes vivían como strings sueltos en cada
// pantalla. errorCodes.test.ts comprueba que cada código de API_ERROR_CODES existe como
// literal en api/src: si el backend renombra uno, la prueba falla antes que la pantalla.
// - API_ERROR_CODES: los que emite el api (core/errors.py, core/security.py y los
//   exceptions.py de cada módulo).
// - CLIENT_ERROR_CODES: los que arma el propio front (sin respuesta, respuesta inválida...).
export const API_ERROR_CODES = {
  // core
  unauthorized: "unauthorized",
  tokenExpired: "token_expired",
  forbidden: "forbidden",
  notFound: "not_found",
  validationError: "validation_error",
  rateLimited: "rate_limited",
  internalError: "internal_error",
  passwordChangeRequired: "password_change_required",
  tooLong: "too_long",
  // auth y usuarios
  invalidCredentials: "invalid_credentials",
  invalidRefresh: "invalid_refresh",
  invalidToken: "invalid_token",
  emailTaken: "email_taken",
  lastAdmin: "last_admin",
  cannotLockSelf: "cannot_lock_self",
  alreadyLocked: "already_locked",
  notLocked: "not_locked",
  userNotEligible: "user_not_eligible",
  userNotFound: "user_not_found",
  // configuración
  versionConflict: "version_conflict",
  sectionNotAvailable: "section_not_available",
  // socios y planes
  memberDocumentDuplicated: "member_document_duplicated",
  memberNotFound: "member_not_found",
  planNameDuplicated: "plan_name_duplicated",
  planNotFound: "plan_not_found",
  // S3-F3: la base no dio el candado a tiempo (503, S3-D67; core/db.py).
  busy: "busy",
  // S3-F3: membresías (vender y renovar, US-084, US-088).
  memberInactive: "member_inactive",
  planInvalid: "plan_invalid",
  planInactive: "plan_inactive",
  startDateTooRetroactive: "start_date_too_retroactive",
  startDateTooFar: "start_date_too_far",
  membershipConflict: "membership_conflict",
  membershipOverlap: "membership_overlap",
  futureMembershipExists: "future_membership_exists",
  membershipNotFound: "membership_not_found",
  // S3-F3: pagos (primer pago de la venta, US-085; S3-D41).
  paymentExceedsBalance: "payment_exceeds_balance",
  paymentPossibleDuplicate: "payment_possible_duplicate",
  paymentLimitReached: "payment_limit_reached",
  paidAtTooRetroactive: "paid_at_too_retroactive",
  // S3-F4: registrar y anular pagos (US-095, US-097; payments/exceptions.py).
  membershipCancelled: "membership_cancelled",
  paymentNotFound: "payment_not_found",
  paymentAlreadyVoided: "payment_already_voided",
  // S3-F5: congelar y anular membresías (US-089, US-090; D14, memberships/exceptions.py).
  membershipNotFreezable: "membership_not_freezable",
  freezeAlreadyScheduled: "freeze_already_scheduled",
  freezeLimitReached: "freeze_limit_reached",
  freezeDaysExceeded: "freeze_days_exceeded",
  freezeTooRetroactive: "freeze_too_retroactive",
  freezeOutsideValidity: "freeze_outside_validity",
  overlapsFutureMembership: "overlaps_future_membership",
  membershipAlreadyCancelled: "membership_already_cancelled",
  // S3-F1: revelar, editar, dar de baja y reactivar socios (US-074 a US-076; members/exceptions.py).
  forbiddenField: "forbidden_field",
  memberDeactivated: "member_deactivated",
  memberAlreadyDeactivated: "member_already_deactivated",
  memberNotDeactivated: "member_not_deactivated",
  consentCannotBeWithdrawn: "consent_cannot_be_withdrawn",
  // S4A-F1: auditoría (US-103, US-104; audit/exceptions.py, S4A-D35).
  verificationRunning: "verification_running",
  auditEntryNotFound: "audit_entry_not_found",
  // S4A-F4: dar de baja un plan con membresías activas (US-082; plans/exceptions.py, S4A-D24).
  planHasActiveMemberships: "plan_has_active_memberships",
} as const;

/** S3-F3: mensaje genérico del 503 `busy` (S3-D67); toda pantalla lo muestra igual. */
export const BUSY_MESSAGE = "El sistema está ocupado; intenta de nuevo.";

export const CLIENT_ERROR_CODES = {
  networkError: "network_error",
  timeout: "timeout",
  invalidResponse: "invalid_response",
  /** La sesión cambió mientras se guardaba la contraseña (S2-D37). */
  sessionChanged: "session_changed",
  /** La sección de configuración todavía no se leyó. */
  notLoaded: "not_loaded",
  /** Un error que no vino del cliente del api. */
  unknown: "unknown",
} as const;

export type ApiErrorCode = (typeof API_ERROR_CODES)[keyof typeof API_ERROR_CODES];
export type ClientErrorCode = (typeof CLIENT_ERROR_CODES)[keyof typeof CLIENT_ERROR_CODES];
