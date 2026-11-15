// S8-F5 · US-175: los errores de generar y revocar el token de la TV en palabras de la pantalla («qué pasó y qué hacer»).
// El diálogo de confirmación muestra el `message` de un ApiError; cualquier otro error cae en su texto genérico.
import { CLIENT_ERROR_CODES } from "../../core/api/errorCodes";
import { ApiError, isApiError } from "../../core/api/errors";
import { HTTP_FORBIDDEN, HTTP_TOO_MANY } from "../../core/api/status";
import { connectionMessage, waitText } from "../../shared/lib/apiMessages";

export const TV_TOKEN_MESSAGES = {
  regenerateFailed: "No pudimos generar el enlace. Intenta de nuevo en un momento.",
  revokeFailed: "No pudimos revocar el token. Intenta de nuevo en un momento.",
  forbidden: "No tienes permiso para cambiar la pantalla de TV. Solo un administrador puede hacerlo.",
  tooMany: (wait: string): string => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
} as const;

function toError(error: unknown, failed: string): ApiError {
  if (!isApiError(error)) return new ApiError({ status: 0, code: CLIENT_ERROR_CODES.unknown, message: failed });
  const message =
    connectionMessage(error) ??
    (error.status === HTTP_FORBIDDEN ? TV_TOKEN_MESSAGES.forbidden : error.status === HTTP_TOO_MANY ? TV_TOKEN_MESSAGES.tooMany(waitText(error.retryAfterS)) : failed);
  return new ApiError({ status: error.status, code: error.code, message });
}

export const regenerateTokenError = (error: unknown): ApiError => toError(error, TV_TOKEN_MESSAGES.regenerateFailed);
export const revokeTokenError = (error: unknown): ApiError => toError(error, TV_TOKEN_MESSAGES.revokeFailed);
