// S5-F3: errores del api de la pestaña Avisos de la ficha en palabras de la pantalla ("qué pasó y qué hacer").
// - channelsLoadError y memberHistoryError: lecturas (403, 404, 429 con la espera, 5xx, red, respuesta inválida).
// - channelSaveMessage: guardar una preferencia. Los 400, 404, 409 y 422 (`consent_required`, `member_deleted`)
//   traen su mensaje en español desde el api y se muestran tal cual; 429, 403 y 5xx tienen texto propio.
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_BAD_REQUEST, HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, toScreenError, waitText } from "../../shared/lib/apiMessages";

const NOT_FOUND = "No encontramos a este socio. Puede que lo hayan eliminado; vuelve a la lista de socios.";

function readMessages(what: string, forbidden: string): (e: ApiError) => string {
  return (e) => {
    if (e.status === HTTP_FORBIDDEN) return forbidden;
    if (e.status === HTTP_NOT_FOUND) return NOT_FOUND;
    if (e.status === HTTP_TOO_MANY) return `Hiciste muchas consultas seguidas. Espera ${waitText(e.retryAfterS)} e intenta de nuevo.`;
    return `No pudimos cargar ${what}. Intenta de nuevo en un momento.`;
  };
}

export function channelsLoadError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    readMessages("los canales del socio", "No tienes permiso para ver los canales de este socio. Si lo necesitas, pídeselo a un administrador."),
    "No pudimos cargar los canales del socio. Intenta de nuevo en un momento.",
  );
}

export function memberHistoryError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    readMessages("los avisos del socio", "No tienes permiso para ver los avisos de este socio. Si lo necesitas, pídeselo a un administrador."),
    "No pudimos cargar los avisos del socio. Intenta de nuevo en un momento.",
  );
}

export const CHANNEL_SAVE_FAILED = "No pudimos guardar la preferencia. Intenta de nuevo en un momento.";
const API_TEXT_STATUSES: readonly number[] = [HTTP_BAD_REQUEST, HTTP_NOT_FOUND, HTTP_CONFLICT, HTTP_UNPROCESSABLE];

export function channelSaveMessage(error: unknown): string {
  if (!isApiError(error)) return CHANNEL_SAVE_FAILED;
  const connection = connectionMessage(error);
  if (connection) return connection;
  if (error.status === HTTP_FORBIDDEN) return "No tienes permiso para cambiar las preferencias. Si lo necesitas, pídeselo a un administrador.";
  if (error.status === HTTP_TOO_MANY) return `Hiciste muchos cambios seguidos. Espera ${waitText(error.retryAfterS)} e intenta de nuevo.`;
  const text = error.message.trim();
  return API_TEXT_STATUSES.includes(error.status) && text !== "" ? text : CHANNEL_SAVE_FAILED;
}
