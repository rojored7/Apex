// S6-F3 · US-150: mensajes de la pestaña Adjuntos en palabras de la pantalla ("qué pasó y qué hacer").
import { statusMessage, toScreenError } from "../../shared/lib/apiMessages";
import type { ApiError } from "../../core/api/errors";

export const ATTACHMENT_MESSAGES = {
  listFailed: "No pudimos cargar los adjuntos. Intenta de nuevo.",
  memberNotFound: "No encontramos este socio. Vuelve a Socios e intenta de nuevo.",
  listForbidden: "No tienes permiso para ver los adjuntos de este socio. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string) => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`,
  forbidden: "Solo un administrador puede descargar este adjunto. Pídele a un administrador que lo descargue.",
  notFound: "Este adjunto ya no está disponible. Actualiza la lista e intenta de nuevo.",
} as const;

/** El error de la lista como ApiError con el mensaje de la pantalla, o null. */
export function attachmentsListError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => statusMessage(e, { notFound: ATTACHMENT_MESSAGES.memberNotFound, forbidden: ATTACHMENT_MESSAGES.listForbidden, tooMany: ATTACHMENT_MESSAGES.tooMany, generic: ATTACHMENT_MESSAGES.listFailed }),
    ATTACHMENT_MESSAGES.listFailed,
  );
}
