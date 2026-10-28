// Revisión del Sprint 2 (M5): las piezas de "qué pasó y qué hacer" que comparten todas las
// pantallas. Antes cada feature (y una feature desde otra) tenía su copia.
// - waitText: la espera de un 429 en palabras ("30 segundos", "1 segundo", "un momento").
// - connectionMessage: sin respuesta (red o timeout) o respuesta con forma inesperada; null
//   si el error vino con respuesta del api.
// - toScreenError: el error de una consulta como ApiError con el mensaje de la pantalla (lo
//   pinta DataTable o un aviso), conservando status y code.
// - Fase 4 del Sprint 3 (M5): statusMessage reparte un error por su status (404, 403, 422, 429 con
//   la espera, 5xx o genérico) con los textos de cada pantalla; toFormError es el error de una
//   escritura de un modal con ese mensaje, conservando status, code y field (ConfirmModal lo pinta
//   bajo el campo o en su alerta).
import { API_ERROR_CODES, BUSY_MESSAGE, CLIENT_ERROR_CODES } from "../../core/api/errorCodes";
import { ApiError, GENERIC_MESSAGES, isApiError } from "../../core/api/errors";
import { HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_SERVER_ERROR, HTTP_SERVICE_UNAVAILABLE, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";

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

/** Los textos de una pantalla por status; el que falta cae en `generic`. */
export interface StatusMessages {
  notFound?: string;
  forbidden?: string;
  unprocessable?: string;
  /** Con la espera en palabras (`waitText`). */
  tooMany?: (wait: string) => string;
  server?: string;
  generic: string;
}

/** El texto de la pantalla para el status de `error` (404, 403, 422, 429, 5xx o genérico). */
export function statusMessage(error: ApiError, messages: StatusMessages): string {
  const { status } = error;
  if (status === HTTP_NOT_FOUND && messages.notFound !== undefined) return messages.notFound;
  if (status === HTTP_FORBIDDEN && messages.forbidden !== undefined) return messages.forbidden;
  if (status === HTTP_UNPROCESSABLE && messages.unprocessable !== undefined) return messages.unprocessable;
  if (status === HTTP_TOO_MANY && messages.tooMany !== undefined) return messages.tooMany(waitText(error.retryAfterS));
  if (status >= HTTP_SERVER_ERROR && messages.server !== undefined) return messages.server;
  return messages.generic;
}

/**
 * El error de una escritura (anular, congelar) con el mensaje de la pantalla: conserva status, code y
 * field. Sin respuesta, base ocupada o respuesta inválida usan los mensajes comunes; un error ajeno al
 * cliente del api, `fallback`.
 */
export function toFormError(error: unknown, message: (error: ApiError) => string, fallback: string): ApiError {
  if (!isApiError(error)) return new ApiError({ status: 0, code: CLIENT_ERROR_CODES.unknown, message: fallback });
  return new ApiError({ status: error.status, code: error.code, message: connectionMessage(error) ?? message(error), ...(error.field ? { field: error.field } : {}) });
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
