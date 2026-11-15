// S8-F4: errores del api de la tablet de resultados en palabras de la pantalla («qué pasó y qué hacer»).
// - resultsLoadMessage: leer la clase (403 `kiosk_mode`: solo hoy o ayer; 404; 429; 5xx).
// - saveMessage: PUT /results (403 `kiosk_mode` al corregir uno de escritorio, 409 `result_exists`, `invalid_supersedes` y
//   `session_cancelled`, 422 con campo, 429, 5xx y red).
// - shouldReload: el 409 dice que otra persona cambió la lista; la pantalla la relee.
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, toScreenError, waitText } from "../../shared/lib/apiMessages";

export const LOAD_MESSAGES = {
  kiosk: "Esta clase no es de hoy ni de ayer. Elige otra clase en el check-in.",
  forbidden: "No tienes permiso para registrar resultados. Si lo necesitas, pídeselo a un administrador.",
  notFound: "Esta clase ya no existe. Vuelve a Clases y elige otra.",
  tooMany: (wait: string): string => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos cargar la clase. Intenta de nuevo en un momento.",
} as const;

export const SAVE_MESSAGES = {
  deskResult: "Este resultado no se registró en la tablet: solo un administrador puede corregirlo desde el panel. Pasa al siguiente atleta.",
  kiosk: "Esta clase no es de hoy ni de ayer: ya no se puede registrar desde la tablet. Pídele a un administrador que lo haga desde el panel.",
  exists: "Este atleta ya tiene un resultado en este WOD. Actualizamos la lista: revisa la marca y corrígela si hace falta.",
  superseded: "El resultado de este atleta cambió mientras lo editabas. Actualizamos la lista: revisa la marca y vuelve a guardar.",
  cancelled: "Esta sesión fue cancelada: ya no se registran resultados. Avísale a un administrador.",
  notScored: "Este WOD no registra resultados.",
  invalid: "Revisa la marca: el servidor no la aceptó. Corrígela y vuelve a guardar.",
  forbidden: "No tienes permiso para registrar resultados. Si lo necesitas, pídeselo a un administrador.",
  notFound: "El atleta o la clase ya no existe. Actualiza la lista e intenta de nuevo.",
  tooMany: (wait: string): string => `Guardaste muchos resultados seguidos. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos guardar el resultado. Intenta de nuevo en un momento.",
} as const;

export const WALKIN_MESSAGES = {
  alreadyIn: "Esa persona ya está en la lista de la clase. Búscala arriba.",
  cancelled: "Esta sesión fue cancelada: no se puede registrar la llegada.",
  tooMany: (wait: string): string => `Hiciste muchas llegadas seguidas. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos registrar la llegada. Intenta de nuevo en un momento.",
  search: "No pudimos buscar. Intenta de nuevo en un momento.",
  searchTooMany: "Demasiadas búsquedas. Espera un momento.",
} as const;

export function resultsLoadError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => {
      if (e.status === HTTP_FORBIDDEN) return e.code === API_ERROR_CODES.kioskMode ? LOAD_MESSAGES.kiosk : LOAD_MESSAGES.forbidden;
      if (e.status === HTTP_NOT_FOUND) return LOAD_MESSAGES.notFound;
      if (e.status === HTTP_TOO_MANY) return LOAD_MESSAGES.tooMany(waitText(e.retryAfterS));
      return LOAD_MESSAGES.failed;
    },
    LOAD_MESSAGES.failed,
  );
}

export function saveMessage(error: unknown): string {
  if (!isApiError(error)) return SAVE_MESSAGES.failed;
  const connection = connectionMessage(error);
  if (connection !== null) return connection;
  if (error.status === HTTP_FORBIDDEN) return error.code === API_ERROR_CODES.kioskMode ? SAVE_MESSAGES.deskResult : SAVE_MESSAGES.forbidden;
  if (error.status === HTTP_NOT_FOUND) return SAVE_MESSAGES.notFound;
  if (error.status === HTTP_CONFLICT) {
    if (error.code === API_ERROR_CODES.sessionCancelled) return SAVE_MESSAGES.cancelled;
    return error.code === API_ERROR_CODES.invalidSupersedes ? SAVE_MESSAGES.superseded : SAVE_MESSAGES.exists;
  }
  if (error.status === HTTP_UNPROCESSABLE) return error.code === API_ERROR_CODES.wodNotScored ? SAVE_MESSAGES.notScored : error.message.trim() !== "" ? `${SAVE_MESSAGES.invalid} (${error.message})` : SAVE_MESSAGES.invalid;
  if (error.status === HTTP_TOO_MANY) return SAVE_MESSAGES.tooMany(waitText(error.retryAfterS));
  return SAVE_MESSAGES.failed;
}

/** El 409 de resultado repetido o corregido por otra persona: la lista de la clase se relee. */
export function shouldReload(error: unknown): boolean {
  return isApiError(error) && error.status === HTTP_CONFLICT;
}

export function addAttendanceMessage(error: unknown): string {
  if (!isApiError(error)) return WALKIN_MESSAGES.failed;
  const connection = connectionMessage(error);
  if (connection !== null) return connection;
  if (error.status === HTTP_CONFLICT) return error.code === API_ERROR_CODES.sessionCancelled ? WALKIN_MESSAGES.cancelled : WALKIN_MESSAGES.alreadyIn;
  if (error.status === HTTP_TOO_MANY) return WALKIN_MESSAGES.tooMany(waitText(error.retryAfterS));
  return WALKIN_MESSAGES.failed;
}

export function searchFailedText(error: unknown): string {
  return isApiError(error) && error.status === HTTP_TOO_MANY ? WALKIN_MESSAGES.searchTooMany : WALKIN_MESSAGES.search;
}
