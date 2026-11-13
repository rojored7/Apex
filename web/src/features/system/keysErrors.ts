// S6-F2 · US-143 a US-146: los errores de la pantalla de llaves en palabras de la pantalla ("qué pasó y qué
// hacer"), con statusMessage, toScreenError y toFormError de shared/lib/apiMessages. Un 409 o un 422 de la
// rotación traen un texto del api que ya dice qué pasó (key_not_active, purpose_not_rotatable,
// rotation_running, rotation_not_supported, nothing_to_rotate; el motivo con correos o números largos):
// se muestra tal cual, igual que el 503 crypto_unavailable (como downloadErrors.ts): el sellado lo explica el CustodyNotice global.
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_SERVICE_UNAVAILABLE, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { statusMessage, toFormError, toScreenError } from "../../shared/lib/apiMessages";

const tooMany = (wait: string): string => `Demasiadas consultas seguidas; espera ${wait} y vuelve a intentarlo.`;

export const KEYS_MESSAGES = {
  keysFailed: "No pudimos cargar las llaves. Intenta de nuevo en un momento.",
  keysForbidden: "No tienes permiso para ver las llaves. Solo un administrador puede consultarlas.",
  opsFailed: "No pudimos cargar la bitácora. Intenta de nuevo en un momento.",
  opsForbidden: "No tienes permiso para ver la bitácora. Solo un administrador puede consultarla.",
  opsBadFilters: "Revisa los filtros: las fechas van desde 2020 hasta hoy y el rango admite como máximo 366 días. Corrígelos e intenta de nuevo.",
  jobsFailed: "No pudimos cargar los trabajos. Intenta de nuevo en un momento.",
  jobsForbidden: "No tienes permiso para ver los trabajos. Solo un administrador puede consultarlos.",
  rotateFailed: "No pudimos iniciar la rotación. Intenta de nuevo en un momento.",
  rotateForbidden: "No tienes permiso para rotar llaves. Solo un administrador puede hacerlo.",
  rotateNotFound: "Esa llave ya no existe. Cierra este aviso y actualiza el inventario.",
  rotateTooMany: (wait: string) => `Demasiadas rotaciones seguidas; espera ${wait} y vuelve a intentarlo.`,
  rotateInvalidKey: "No pudimos iniciar la rotación porque la llave no es válida. Actualiza el inventario e intenta de nuevo.",
} as const;

/** El error de la lista de llaves (lo pinta DataTable o la tarjeta). */
export function keysListError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => statusMessage(e, { forbidden: KEYS_MESSAGES.keysForbidden, tooMany, generic: KEYS_MESSAGES.keysFailed }),
    KEYS_MESSAGES.keysFailed,
  );
}

/** El error de la bitácora; un 422 pide revisar las fechas. */
export function opsListError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => statusMessage(e, { forbidden: KEYS_MESSAGES.opsForbidden, unprocessable: KEYS_MESSAGES.opsBadFilters, tooMany, generic: KEYS_MESSAGES.opsFailed }),
    KEYS_MESSAGES.opsFailed,
  );
}

/** El error de los trabajos. */
export function jobsListError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => statusMessage(e, { forbidden: KEYS_MESSAGES.jobsForbidden, tooMany, generic: KEYS_MESSAGES.jobsFailed }),
    KEYS_MESSAGES.jobsFailed,
  );
}

/** El error de POST /crypto/keys/{id}/rotate como ApiError (ConfirmModal lo pinta); conserva status, code y field. */
export function rotateError(error: unknown): ApiError {
  return toFormError(
    error,
    (e) => {
      const custody = e.code === API_ERROR_CODES.cryptoUnavailable && e.status === HTTP_SERVICE_UNAVAILABLE;
      const ownsText = (e.status === HTTP_CONFLICT || e.status === HTTP_UNPROCESSABLE || custody) && e.message.trim() !== "";
      if (ownsText) return e.message;
      return statusMessage(e, { notFound: KEYS_MESSAGES.rotateNotFound, forbidden: KEYS_MESSAGES.rotateForbidden, tooMany: KEYS_MESSAGES.rotateTooMany, generic: KEYS_MESSAGES.rotateFailed });
    },
    KEYS_MESSAGES.rotateFailed,
  );
}
