// S5-F4: errores de descargas (recibo PDF y exportaciones CSV) en palabras de la pantalla
// ("qué pasó y qué hacer"). Los códigos propios de las exportaciones (409 `export_in_progress`,
// 422 `export_too_large`, 503 `crypto_unavailable`) y un 422 de filtros llevan texto fijo en español
// del api (S5-D41, S5-D82, S5-D14): se muestran tal cual. El resto usa los mensajes de la pantalla.
import { API_ERROR_CODES, CLIENT_ERROR_CODES } from "../../core/api/errorCodes";
import { ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_SERVICE_UNAVAILABLE, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { statusMessage, toFormError, waitText } from "./apiMessages";

const BUSY_DEFAULT_WAIT_S = 1;

export const DOWNLOAD_MESSAGES = {
  busy: (wait: string) => `El sistema está ocupado. Espera ${wait} e intenta de nuevo.`,
  forbidden: "No tienes permiso para descargar esta información. Si lo necesitas, pídeselo a un administrador.",
  notFound: "No encontramos este pago. Actualiza la lista e intenta de nuevo.",
  tooMany: (wait: string) => `Hiciste muchas descargas seguidas. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos preparar la descarga. Intenta de nuevo en un momento.",
  generic: "No pudimos preparar la descarga. Intenta de nuevo.",
} as const;

/** Los textos del api que ya dicen qué pasó y qué hacer, y que se muestran sin cambios. */
function apiTextOwns(error: ApiError): boolean {
  if (error.message.trim() === "") return false;
  if (error.code === CLIENT_ERROR_CODES.unexpectedContentType) return true;
  if (error.status === HTTP_CONFLICT) return error.code === API_ERROR_CODES.exportInProgress;
  if (error.status === HTTP_SERVICE_UNAVAILABLE) return error.code === API_ERROR_CODES.cryptoUnavailable;
  return error.status === HTTP_UNPROCESSABLE;
}

function downloadMessage(error: ApiError): string {
  if (apiTextOwns(error)) return error.message;
  return statusMessage(error, DOWNLOAD_MESSAGES);
}

/** El error de una descarga como ApiError con el mensaje de la pantalla; conserva status, code y field. */
export function toDownloadError(error: unknown): ApiError {
  // Revisión LOW 2: un 503 busy dice cuánto esperar y conserva retryAfterS (quien llama bloquea el botón).
  if (error instanceof ApiError && error.status === HTTP_SERVICE_UNAVAILABLE && error.code === API_ERROR_CODES.busy) {
    return new ApiError({ status: error.status, code: error.code, message: DOWNLOAD_MESSAGES.busy(waitText(error.retryAfterS)), retryAfterS: error.retryAfterS ?? BUSY_DEFAULT_WAIT_S });
  }
  return toFormError(error, downloadMessage, DOWNLOAD_MESSAGES.generic);
}
