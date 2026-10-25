// Revisión del Sprint 2 (M5): las piezas de "qué pasó y qué hacer" que comparten todas las
// pantallas. Antes cada feature (y una feature desde otra) tenía su copia.
// - waitText: la espera de un 429 en palabras ("30 segundos", "1 segundo", "un momento").
// - connectionMessage: sin respuesta (red o timeout) o respuesta con forma inesperada; null
//   si el error vino con respuesta del api.
// - toScreenError: el error de una consulta como ApiError con el mensaje de la pantalla (lo
//   pinta DataTable o un aviso), conservando status y code.
import { API_ERROR_CODES, BUSY_MESSAGE, CLIENT_ERROR_CODES } from "../../core/api/errorCodes";
import { ApiError, GENERIC_MESSAGES, isApiError } from "../../core/api/errors";
import { HTTP_SERVICE_UNAVAILABLE } from "../../core/api/status";

/** Un 429 sin `Retry-After` útil. */
export const TOO_MANY_MESSAGE = "Demasiados intentos. Espera un momento y vuelve a intentarlo.";

/** "30 segundos", "1 segundo" o "un momento" (sin Retry-After). */
export function waitText(seconds: number | undefined): string {
  if (seconds === undefined || seconds <= 0) return "un momento";
  return seconds === 1 ? "1 segundo" : `${String(seconds)} segundos`;
}

/**
 * Sin respuesta, respuesta inválida o base ocupada (503 `busy`, S3-F3): mensajes que no dependen de
 * la pantalla. `null` si el api respondió con otro error de su envelope.
 */
export function connectionMessage(error: ApiError): string | null {
  if (error.code === CLIENT_ERROR_CODES.invalidResponse) return error.message;
  if (error.status === HTTP_SERVICE_UNAVAILABLE && error.code === API_ERROR_CODES.busy) return BUSY_MESSAGE;
  if (error.status === 0) return error.code === CLIENT_ERROR_CODES.timeout ? GENERIC_MESSAGES.timeout : GENERIC_MESSAGES.network_error;
  return null;
}

/**
 * El error de una consulta en palabras de la pantalla. `message` decide por status o code
 * cuando hubo respuesta; un error ajeno al cliente del api usa `fallback`.
 */
export function toScreenError(error: unknown, message: (error: ApiError) => string, fallback: string): ApiError | null {
  if (!error) return null;
  if (!isApiError(error)) return new ApiError({ status: 0, code: CLIENT_ERROR_CODES.unknown, message: fallback });
  return new ApiError({ status: error.status, code: error.code, message: connectionMessage(error) ?? message(error) });
}
