// S8-F3 (front): errores de lectura y anulación de resultados en palabras de la pantalla («qué pasó y qué hacer»).
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, toScreenError, waitText } from "../lib/apiMessages";

export const RESULTS_LOAD_MESSAGES = {
  forbidden: "No tienes permiso para ver los resultados. Si lo necesitas, pídeselo a un administrador.",
  notFound: "Este WOD ya no existe. Vuelve a la lista de WODs.",
  tooLarge: "Este WOD tiene demasiados resultados para armar la tabla. Pide ayuda a un administrador.",
  tooMany: (wait: string): string => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos cargar los resultados. Intenta de nuevo en un momento.",
} as const;

export const VOID_MESSAGES = {
  forbidden: "Solo un administrador puede anular resultados. Pídele a uno que lo haga.",
  notFound: "Este resultado ya no existe. Cierra este aviso y actualiza la lista.",
  already: "Este resultado ya estaba anulado. Cierra este aviso y actualiza la lista.",
  notVoidable: "Solo se anula el resultado vigente. Si fue corregido, anula el más reciente.",
  reason: "Escribe un motivo de 1 a 200 caracteres, sin saltos de línea.",
  tooMany: (wait: string): string => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos anular el resultado. Intenta de nuevo en un momento.",
} as const;

export function resultsLoadError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => {
      if (e.status === HTTP_FORBIDDEN) return RESULTS_LOAD_MESSAGES.forbidden;
      if (e.status === HTTP_NOT_FOUND) return RESULTS_LOAD_MESSAGES.notFound;
      if (e.status === HTTP_UNPROCESSABLE && e.code === API_ERROR_CODES.leaderboardTooLarge) return RESULTS_LOAD_MESSAGES.tooLarge;
      if (e.status === HTTP_TOO_MANY) return RESULTS_LOAD_MESSAGES.tooMany(waitText(e.retryAfterS));
      return RESULTS_LOAD_MESSAGES.failed;
    },
    RESULTS_LOAD_MESSAGES.failed,
  );
}

/** El mensaje de una anulación fallida; el modal lo muestra dentro. */
export function voidMessage(error: unknown): string {
  if (!isApiError(error)) return VOID_MESSAGES.failed;
  const connection = connectionMessage(error);
  if (connection !== null) return connection;
  if (error.status === HTTP_FORBIDDEN) return VOID_MESSAGES.forbidden;
  if (error.status === HTTP_NOT_FOUND) return VOID_MESSAGES.notFound;
  if (error.status === HTTP_CONFLICT) return error.code === API_ERROR_CODES.resultAlreadyVoided ? VOID_MESSAGES.already : VOID_MESSAGES.notVoidable;
  if (error.status === HTTP_UNPROCESSABLE) return VOID_MESSAGES.reason;
  if (error.status === HTTP_TOO_MANY) return VOID_MESSAGES.tooMany(waitText(error.retryAfterS));
  return VOID_MESSAGES.failed;
}
