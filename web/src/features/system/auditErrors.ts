// S4A-F1 · US-102 a US-104: los errores de la auditoría en palabras de la pantalla ("qué pasó y qué
// hacer"), con statusMessage y toScreenError de shared/lib/apiMessages. Los códigos salen de
// core/api/errorCodes (nunca un literal suelto).
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT } from "../../core/api/status";
import { connectionMessage, statusMessage, toScreenError } from "../../shared/lib/apiMessages";

export const AUDIT_MESSAGES = {
  listFailed: "No pudimos cargar la auditoría. Intenta de nuevo en un momento.",
  forbidden: "No tienes permiso para ver la auditoría. Solo un administrador puede consultarla.",
  badFilters: "Revisa los filtros: las fechas van desde 2020 hasta mañana. Corrígelas e intenta de nuevo.",
  tooMany: (wait: string) => `Demasiadas consultas seguidas; espera ${wait} y vuelve a intentarlo.`,
  entryNotFound: "Ese registro ya no existe. Cierra el panel y elige otra entrada de la lista.",
  entryFailed: "No pudimos cargar la entrada. Intenta de nuevo en un momento.",
  verifyFailed: "No pudimos verificar la cadena. Intenta de nuevo en un momento.",
  verifyRunning: "Ya hay una verificación en curso. Espera a que termine; el resultado aparece aquí.",
  verifyTooMany: (wait: string) => `Demasiadas verificaciones; espera ${wait} y vuelve a intentarlo.`,
  verifyForbidden: "No tienes permiso para verificar la cadena. Solo un administrador puede hacerlo.",
} as const;

/** El error de la lista (lo pinta DataTable). */
export function auditListError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => statusMessage(e, { forbidden: AUDIT_MESSAGES.forbidden, unprocessable: AUDIT_MESSAGES.badFilters, tooMany: AUDIT_MESSAGES.tooMany, generic: AUDIT_MESSAGES.listFailed }),
    AUDIT_MESSAGES.listFailed,
  );
}

/** El error del detalle: 404 `audit_entry_not_found` dice que el registro ya no existe. */
export function auditEntryError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) =>
      e.code === API_ERROR_CODES.auditEntryNotFound
        ? AUDIT_MESSAGES.entryNotFound
        : statusMessage(e, { notFound: AUDIT_MESSAGES.entryNotFound, forbidden: AUDIT_MESSAGES.forbidden, tooMany: AUDIT_MESSAGES.tooMany, generic: AUDIT_MESSAGES.entryFailed }),
    AUDIT_MESSAGES.entryFailed,
  );
}

/** 409 `verification_running`: otra verificación tiene el candado. */
export function isVerificationRunning(error: unknown): boolean {
  return isApiError(error) && error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.verificationRunning;
}

/** El mensaje de un POST /audit/verify que falló. */
export function verifyErrorMessage(error: unknown): string {
  if (!isApiError(error)) return AUDIT_MESSAGES.verifyFailed;
  if (isVerificationRunning(error)) return AUDIT_MESSAGES.verifyRunning;
  return (
    connectionMessage(error) ??
    statusMessage(error, { forbidden: AUDIT_MESSAGES.verifyForbidden, tooMany: AUDIT_MESSAGES.verifyTooMany, generic: AUDIT_MESSAGES.verifyFailed })
  );
}
