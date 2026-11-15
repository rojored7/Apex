// S7-F2 y S7-F3: errores del api de clases en palabras de la pantalla («qué pasó y qué hacer»).
// - slotFieldError y sessionFieldError: el 409 `slot_conflict` va bajo los días; el 422 con `field` (y `coach_invalid`)
//   bajo su campo; los mensajes son propios (los del api nombran el campo en inglés).
// - Escrituras (franja, cancelar sesiones futuras, sesión extra, cancelar sesión): 403, 404, 409, 429, 5xx y red.
import type { FieldPath } from "react-hook-form";
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, statusMessage, toFormError, toScreenError, waitText } from "../../shared/lib/apiMessages";
import { SLOT_MESSAGES, type SlotFormValues } from "./schemas";

export const COACH_INVALID_MESSAGE = "Ese usuario ya no puede ser coach. Elige otro o deja la franja sin coach.";
export const SLOT_CONFLICT_MESSAGE = "Ya hay una franja activa a esa hora en alguno de esos días. Cambia la hora o quita esos días.";

const tooMany = (wait: string): string => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`;

export const SLOT_SAVE_MESSAGES = {
  forbidden: "Solo un administrador puede crear franjas. Si lo necesitas, pídeselo a uno.",
  notFound: "Esta franja ya no existe. Cierra el panel y actualiza la lista.",
  tooMany,
  server: "No pudimos guardar la franja. Intenta de nuevo en un momento.",
  generic: "No pudimos guardar la franja. Revisa los datos e intenta de nuevo.",
} as const;

export const CANCEL_FUTURE_MESSAGES = {
  forbidden: "Solo un administrador puede cancelar sesiones. Si lo necesitas, pídeselo a uno.",
  notFound: "Esta franja ya no existe. Cierra este aviso y actualiza la lista.",
  unprocessable: "Escribe un motivo de 3 a 200 caracteres.",
  tooMany,
  server: "No pudimos cancelar las sesiones. Intenta de nuevo en un momento.",
  generic: "No pudimos cancelar las sesiones. Intenta de nuevo en un momento.",
} as const;

export const SLOTS_LIST_MESSAGES = {
  forbidden: "No tienes permiso para ver el horario. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string): string => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos cargar el horario. Intenta de nuevo en un momento.",
} as const;

const SLOT_FIELDS: Readonly<Record<string, { path: FieldPath<SlotFormValues>; message: string }>> = {
  weekdays: { path: "weekdays", message: SLOT_MESSAGES.weekdays },
  start_time: { path: "start_time", message: SLOT_MESSAGES.startTime },
  duration_min: { path: "duration_min", message: SLOT_MESSAGES.duration },
  capacity: { path: "capacity", message: SLOT_MESSAGES.capacity },
  name: { path: "name", message: SLOT_MESSAGES.name },
  valid_from: { path: "valid_from", message: SLOT_MESSAGES.validFrom },
  default_coach_id: { path: "coach_id", message: COACH_INVALID_MESSAGE },
};

export interface SlotFieldError {
  path: FieldPath<SlotFormValues>;
  message: string;
}

/** El error que va bajo un campo del formulario de franja, o null si es general. */
export function slotFieldError(error: unknown): SlotFieldError | null {
  if (!isApiError(error)) return null;
  if (error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.slotConflict) return { path: "weekdays", message: SLOT_CONFLICT_MESSAGE };
  if (error.code === API_ERROR_CODES.coachInvalid) return { path: "coach_id", message: COACH_INVALID_MESSAGE };
  if (error.status !== HTTP_UNPROCESSABLE || !error.field) return null;
  return SLOT_FIELDS[error.field] ?? null;
}

/** Mensaje general de una franja que no se pudo guardar. */
export function slotSaveMessage(error: unknown): string {
  if (!isApiError(error)) return SLOT_SAVE_MESSAGES.generic;
  return connectionMessage(error) ?? statusMessage(error, SLOT_SAVE_MESSAGES);
}

/** El error de cancelar sesiones futuras con el mensaje de la pantalla (ConfirmModal). */
export function cancelFutureError(error: unknown): ApiError {
  return toFormError(error, (e) => statusMessage(e, CANCEL_FUTURE_MESSAGES), CANCEL_FUTURE_MESSAGES.generic);
}

/** El error de la lista de franjas como ApiError con el mensaje de la pantalla (lo pinta DataTable). */
export function slotsListError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => (e.status === HTTP_FORBIDDEN ? SLOTS_LIST_MESSAGES.forbidden : e.status === HTTP_TOO_MANY ? SLOTS_LIST_MESSAGES.tooMany(waitText(e.retryAfterS)) : SLOTS_LIST_MESSAGES.failed),
    SLOTS_LIST_MESSAGES.failed,
  );
}
