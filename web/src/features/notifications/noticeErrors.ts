// S5-F1: errores del api de avisos en palabras de la pantalla ("qué pasó y qué hacer").
// - todayError: la lista (403, 429 con la espera, 5xx, red, respuesta inválida).
// - waLinkMessage: abrir WhatsApp. Los 400, 404, 409 y 422 (`invalid_phone`, `member_without_phone`,
//   `wrong_channel`, `notification_closed`) traen su mensaje en español desde el api y se muestran
//   tal cual; el 429 le suma la espera.
// - skipError: omitir; 409 y 404 (el aviso ya no está pendiente), 422 bajo el campo, 429 con la espera.
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_BAD_REQUEST, HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, statusMessage, toFormError, toScreenError, waitText } from "../../shared/lib/apiMessages";

export const TODAY_MESSAGES = {
  forbidden: "No tienes permiso para ver los avisos de hoy. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string) => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos cargar los avisos de hoy. Intenta de nuevo en un momento.",
} as const;

export const WA_MESSAGES = {
  forbidden: "No tienes permiso para abrir WhatsApp. Si lo necesitas, pídeselo a un administrador.",
  tooMany: "Hiciste muchas aperturas seguidas.",
  failed: "No pudimos abrir WhatsApp. Intenta de nuevo en un momento.",
} as const;

export const SKIP_MESSAGES = {
  closed: "Este aviso ya no está pendiente. La lista se actualiza sola; cierra este diálogo.",
  notFound: "Este aviso ya no existe. La lista se actualiza sola; cierra este diálogo.",
  forbidden: "No tienes permiso para omitir avisos. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string) => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
  generic: "No pudimos omitir el aviso. Intenta de nuevo en un momento.",
} as const;

export function todayError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => (e.status === HTTP_FORBIDDEN ? TODAY_MESSAGES.forbidden : e.status === HTTP_TOO_MANY ? TODAY_MESSAGES.tooMany(waitText(e.retryAfterS)) : TODAY_MESSAGES.failed),
    TODAY_MESSAGES.failed,
  );
}

const API_TEXT_STATUSES: readonly number[] = [HTTP_BAD_REQUEST, HTTP_NOT_FOUND, HTTP_CONFLICT, HTTP_UNPROCESSABLE];

export function waLinkMessage(error: unknown): string {
  if (!isApiError(error)) return WA_MESSAGES.failed;
  const connection = connectionMessage(error);
  if (connection) return connection;
  const text = error.message.trim();
  if (error.status === HTTP_FORBIDDEN) return WA_MESSAGES.forbidden;
  if (error.status === HTTP_TOO_MANY) {
    const base = text === "" ? WA_MESSAGES.tooMany : text;
    return error.retryAfterS === undefined ? base : `${base} Espera ${waitText(error.retryAfterS)}.`;
  }
  if (API_TEXT_STATUSES.includes(error.status) && text !== "") return text;
  return WA_MESSAGES.failed;
}

export function skipError(error: unknown): ApiError {
  return toFormError(
    error,
    (e) => {
      if (e.status === HTTP_CONFLICT) return SKIP_MESSAGES.closed;
      if (e.status === HTTP_UNPROCESSABLE && e.message.trim() !== "") return e.message;
      return statusMessage(e, SKIP_MESSAGES);
    },
    SKIP_MESSAGES.generic,
  );
}
