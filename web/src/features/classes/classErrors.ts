// S7-F2 y S7-F3: errores del api de clases en palabras de la pantalla («qué pasó y qué hacer»).
// - slotFieldError y sessionFieldError: el 409 `slot_conflict` va bajo los días; el 422 con `field` (y `coach_invalid`)
//   bajo su campo; los mensajes son propios (los del api nombran el campo en inglés).
// - Escrituras (franja, cancelar sesiones futuras, sesión extra, cancelar sesión): 403, 404, 409, 429, 5xx y red.
import type { FieldPath } from "react-hook-form";
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, statusMessage, toFormError, toScreenError, waitText } from "../../shared/lib/apiMessages";
import { EXTRA_MESSAGES, SLOT_MESSAGES, type ExtraSessionFormValues, type SlotFormValues } from "./schemas";

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

// S7-F3 · US-157: sesión extra, cancelar una sesión y leer una semana.
export const SESSION_DUPLICATE_MESSAGE = "Ya existe una sesión extra con ese horario y ese coach. Cambia la hora o el coach.";
export const SESSION_COACH_INVALID_MESSAGE = "Ese usuario ya no puede ser coach. Elige otro o deja la sesión sin coach.";

export const EXTRA_SAVE_MESSAGES = {
  forbidden: "No tienes permiso para crear sesiones. Si lo necesitas, pídeselo a un administrador.",
  tooMany,
  server: "No pudimos crear la sesión. Intenta de nuevo en un momento.",
  generic: "No pudimos crear la sesión. Revisa los datos e intenta de nuevo.",
} as const;

export const CANCEL_SESSION_MESSAGES = {
  forbidden: "No tienes permiso para cancelar sesiones. Si lo necesitas, pídeselo a un administrador.",
  notFound: "Esta sesión ya no existe. Cierra este aviso y actualiza la semana.",
  unprocessable: "Escribe un motivo de 3 a 200 caracteres.",
  tooMany,
  server: "No pudimos cancelar la sesión. Intenta de nuevo en un momento.",
  generic: "No pudimos cancelar la sesión. Intenta de nuevo en un momento.",
  finished: "Esta sesión ya terminó y no se puede cancelar.",
  alreadyCancelled: "Otra persona ya canceló esta sesión. Actualizamos la semana.",
} as const;

export const SESSIONS_LIST_MESSAGES = {
  forbidden: "No tienes permiso para ver las sesiones. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string): string => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos cargar las sesiones. Intenta de nuevo en un momento.",
} as const;

const EXTRA_FIELDS: Readonly<Record<string, { path: FieldPath<ExtraSessionFormValues>; message: string }>> = {
  starts_at: { path: "starts_at", message: EXTRA_MESSAGES.startsAtRange },
  duration_min: { path: "duration_min", message: SLOT_MESSAGES.duration },
  capacity: { path: "capacity", message: EXTRA_MESSAGES.capacity },
  name: { path: "name", message: SLOT_MESSAGES.name },
};

export interface ExtraSessionFieldError {
  path: FieldPath<ExtraSessionFormValues>;
  message: string;
}

/** El error que va bajo un campo del formulario de sesión extra, o null si es general. */
export function extraSessionFieldError(error: unknown): ExtraSessionFieldError | null {
  if (!isApiError(error)) return null;
  if (error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.sessionDuplicate) return { path: "starts_at", message: SESSION_DUPLICATE_MESSAGE };
  if (error.code === API_ERROR_CODES.coachInvalid) return { path: "coach_id", message: SESSION_COACH_INVALID_MESSAGE };
  if (error.status !== HTTP_UNPROCESSABLE || !error.field) return null;
  return EXTRA_FIELDS[error.field] ?? null;
}

/** Mensaje general de una sesión extra que no se pudo crear. */
export function extraSessionSaveMessage(error: unknown): string {
  if (!isApiError(error)) return EXTRA_SAVE_MESSAGES.generic;
  return connectionMessage(error) ?? statusMessage(error, EXTRA_SAVE_MESSAGES);
}

/** El error de cancelar una sesión con el mensaje de la pantalla (ConfirmModal). */
export function cancelSessionError(error: unknown): ApiError {
  return toFormError(
    error,
    (e) => {
      if (e.status === HTTP_CONFLICT && e.code === API_ERROR_CODES.sessionFinished) return CANCEL_SESSION_MESSAGES.finished;
      if (e.status === HTTP_CONFLICT && e.code === API_ERROR_CODES.sessionAlreadyCancelled) return CANCEL_SESSION_MESSAGES.alreadyCancelled;
      return statusMessage(e, CANCEL_SESSION_MESSAGES);
    },
    CANCEL_SESSION_MESSAGES.generic,
  );
}

/** El error de la semana como ApiError con el mensaje de la pantalla. */
export function sessionsListError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => (e.status === HTTP_FORBIDDEN ? SESSIONS_LIST_MESSAGES.forbidden : e.status === HTTP_TOO_MANY ? SESSIONS_LIST_MESSAGES.tooMany(waitText(e.retryAfterS)) : SESSIONS_LIST_MESSAGES.failed),
    SESSIONS_LIST_MESSAGES.failed,
  );
}

/** El error de la lista de franjas como ApiError con el mensaje de la pantalla (lo pinta DataTable). */
export function slotsListError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => (e.status === HTTP_FORBIDDEN ? SLOTS_LIST_MESSAGES.forbidden : e.status === HTTP_TOO_MANY ? SLOTS_LIST_MESSAGES.tooMany(waitText(e.retryAfterS)) : SLOTS_LIST_MESSAGES.failed),
    SLOTS_LIST_MESSAGES.failed,
  );
}

// S7-F4 · US-159 y US-161: check-in en la tablet y quitar una asistencia.
export const CHECKIN_MESSAGES = {
  alreadyCheckedIn: "Ya registró asistencia en esta clase.",
  sessionCancelled: "Esta sesión fue cancelada. Ya no se puede registrar la llegada.",
  notFound: "Ese socio ya no existe. Búscalo de nuevo.",
  forbidden: "No tienes permiso para registrar asistencia. Pídele ayuda a un administrador.",
  tooMany: (wait: string): string => `Hiciste muchas llegadas seguidas. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos registrar la llegada. Intenta de nuevo.",
  generic: "No pudimos registrar la llegada. Intenta de nuevo.",
} as const;

export const REMOVE_ATTENDANCE_MESSAGES = {
  locked: "Esta asistencia ya no se puede quitar desde la tablet. Pídele a un administrador que la quite.",
  notFound: "Esa asistencia ya no existe. Cierra este aviso; actualizamos la lista.",
  tooMany,
  server: "No pudimos quitar la asistencia. Intenta de nuevo en un momento.",
  generic: "No pudimos quitar la asistencia. Intenta de nuevo en un momento.",
} as const;

export const SESSION_LOAD_MESSAGES = {
  notFound: "Esta sesión ya no existe. Vuelve a Clases y elige otra.",
  forbidden: "No tienes permiso para registrar asistencia en esta clase.",
  tooMany: (wait: string): string => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos cargar la sesión. Intenta de nuevo en un momento.",
  generic: "No pudimos cargar la sesión. Intenta de nuevo en un momento.",
} as const;

export const MEMBER_SEARCH_MESSAGES = {
  tooMany: "Espera un momento y vuelve a buscar.",
  failed: "No pudimos buscar. Intenta de nuevo en un momento.",
} as const;

/** El mensaje de un check-in que no se registró (409 duplicado o cancelada, 404, 403, 429, 5xx, red). */
export function checkInMessage(error: unknown): string {
  if (!isApiError(error)) return CHECKIN_MESSAGES.generic;
  const connection = connectionMessage(error);
  if (connection !== null) return connection;
  if (error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.alreadyCheckedIn) return CHECKIN_MESSAGES.alreadyCheckedIn;
  if (error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.sessionCancelled) return CHECKIN_MESSAGES.sessionCancelled;
  return statusMessage(error, CHECKIN_MESSAGES);
}

/** Quitar una asistencia: 403 `attendance_locked` (el coach solo quita hoy o ayer), 404, 429, 5xx (ConfirmModal). */
export function removeAttendanceError(error: unknown): ApiError {
  return toFormError(
    error,
    (e) => (e.status === HTTP_FORBIDDEN ? REMOVE_ATTENDANCE_MESSAGES.locked : statusMessage(e, REMOVE_ATTENDANCE_MESSAGES)),
    REMOVE_ATTENDANCE_MESSAGES.generic,
  );
}

/** El error de leer la sesión del check-in con el mensaje de la pantalla. */
export function sessionLoadError(error: unknown): ApiError | null {
  return toScreenError(error, (e) => statusMessage(e, SESSION_LOAD_MESSAGES), SESSION_LOAD_MESSAGES.generic);
}

/** La búsqueda de socios falló: el 429 pide esperar, lo demás pide reintentar. */
export function memberSearchFailedText(error: unknown): string {
  return isApiError(error) && error.status === HTTP_TOO_MANY ? MEMBER_SEARCH_MESSAGES.tooMany : MEMBER_SEARCH_MESSAGES.failed;
}

// S7-F5 · US-162: leer la asistencia (lista, resumen semanal y pestaña de la ficha).
export const ATTENDANCE_LIST_MESSAGES = {
  forbidden: "No tienes permiso para ver la asistencia. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string): string => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos cargar las asistencias. Intenta de nuevo en un momento.",
} as const;

export const ATTENDANCE_SUMMARY_MESSAGES = {
  forbidden: ATTENDANCE_LIST_MESSAGES.forbidden,
  tooMany: ATTENDANCE_LIST_MESSAGES.tooMany,
  failed: "No pudimos cargar el resumen por semana. Intenta de nuevo en un momento.",
} as const;

export const MEMBER_ATTENDANCE_MESSAGES = {
  notFound: "Este socio ya no existe. Vuelve a Socios y búscalo de nuevo.",
  forbidden: ATTENDANCE_LIST_MESSAGES.forbidden,
  tooMany: ATTENDANCE_LIST_MESSAGES.tooMany,
  failed: "No pudimos cargar la asistencia del socio. Intenta de nuevo en un momento.",
} as const;

export const RANGE_INVERTED_MESSAGE = "La fecha inicial no puede ser posterior a la final. Corrige el rango.";
export const RANGE_TOO_LONG_MESSAGE = "El rango no puede pasar de 26 semanas. Acórtalo y vuelve a intentar.";

interface ReadMessages {
  forbidden: string;
  tooMany: (wait: string) => string;
  failed: string;
  notFound?: string;
}

function readError(error: unknown, messages: ReadMessages): ApiError | null {
  return toScreenError(
    error,
    (e) => {
      if (e.status === HTTP_FORBIDDEN) return messages.forbidden;
      if (e.status === HTTP_TOO_MANY) return messages.tooMany(waitText(e.retryAfterS));
      if (e.status === HTTP_NOT_FOUND && messages.notFound !== undefined) return messages.notFound;
      return messages.failed;
    },
    messages.failed,
  );
}

/** El error de la lista de asistencias como ApiError con el mensaje de la pantalla (lo pinta DataTable). */
export const attendanceListError = (error: unknown): ApiError | null => readError(error, ATTENDANCE_LIST_MESSAGES);
/** El error del resumen semanal. */
export const attendanceSummaryError = (error: unknown): ApiError | null => readError(error, ATTENDANCE_SUMMARY_MESSAGES);
/** El error de la pestaña de la ficha (404: el socio ya no existe). */
export const memberAttendanceError = (error: unknown): ApiError | null => readError(error, MEMBER_ATTENDANCE_MESSAGES);
