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
} as const;

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
