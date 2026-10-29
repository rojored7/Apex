// S2-F7: errores del api de planes en palabras de la pantalla ("qué pasó y qué hacer").
// - fieldErrorOf: el 422 con `field` (PlanCreate y validate_plan de B9) y el 409
//   `plan_name_duplicated` (S2-D32, `field="name"` y `existing_id`) van bajo su campo. Los mensajes
//   son propios: el del api nombra el campo en inglés y nunca repite el valor.
// - createErrorMessage, listError y detailError: el resto (403, 404, 429 con la espera, 5xx, red,
//   respuesta inválida) como mensaje general.
import type { FieldPath } from "react-hook-form";
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_SERVER_ERROR, HTTP_TOO_MANY, HTTP_UNPROCESSABLE, isClientErrorStatus } from "../../core/api/status";
import { connectionMessage, statusMessage, toFormError, toScreenError, waitText } from "../../shared/lib/apiMessages";
import { PLAN_MESSAGES, type PlanFormValues } from "./schemas";

export const CREATE_MESSAGES = {
  forbidden: "Solo un administrador puede crear planes. Si lo necesitas, pídeselo a uno.",
  tooMany: (wait: string) => `Hiciste muchos intentos seguidos. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos crear el plan. Intenta de nuevo en un momento.",
  generic: "No pudimos crear el plan. Revisa los datos e intenta de nuevo.",
} as const;

export const LIST_MESSAGES = {
  forbidden: "No tienes permiso para ver estos planes. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string) => `Hiciste muchas búsquedas seguidas. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos cargar los planes. Intenta de nuevo en un momento.",
} as const;

export const DETAIL_MESSAGES = {
  forbidden: "Este plan está inactivo y solo un administrador puede verlo.",
  notFound: "No encontramos este plan. Puede que lo hayan dado de baja; ciérralo y elige otro de la lista.",
  failed: "No pudimos cargar el plan. Intenta de nuevo en un momento.",
} as const;

/** Campo del api → campo del formulario y su mensaje. */
const FIELD_ERRORS: Readonly<Record<string, { path: FieldPath<PlanFormValues>; message: string }>> = {
  name: { path: "name", message: PLAN_MESSAGES.nameRejected },
  price_cop: { path: "price", message: PLAN_MESSAGES.priceRange },
  kind: { path: "kind", message: PLAN_MESSAGES.kind },
  duration_days: { path: "duration_days", message: PLAN_MESSAGES.durationRange },
  class_count: { path: "class_count", message: PLAN_MESSAGES.classCountRange },
};

export interface PlanFieldError {
  path: FieldPath<PlanFormValues>;
  message: string;
  /** 409: el plan vivo que ya tiene ese nombre. */
  existingId: string | null;
}

/** El error que va bajo un campo, o null si es un error general. */
export function fieldErrorOf(error: unknown): PlanFieldError | null {
  if (!isApiError(error)) return null;
  if (error.status === HTTP_CONFLICT && (error.code === API_ERROR_CODES.planNameDuplicated || error.field === "name")) {
    return { path: "name", message: PLAN_MESSAGES.duplicated, existingId: error.existingId ?? null };
  }
  if (error.status !== HTTP_UNPROCESSABLE || !error.field) return null;
  const target = FIELD_ERRORS[error.field];
  return target ? { ...target, existingId: null } : null;
}

/** Mensaje general de un alta fallida. */
export function createErrorMessage(error: unknown): string {
  if (!isApiError(error)) return CREATE_MESSAGES.generic;
  const connection = connectionMessage(error);
  if (connection) return connection;
  if (error.status === HTTP_FORBIDDEN) return CREATE_MESSAGES.forbidden;
  if (error.status === HTTP_TOO_MANY) return CREATE_MESSAGES.tooMany(waitText(error.retryAfterS));
  if (error.status >= HTTP_SERVER_ERROR) return CREATE_MESSAGES.server;
  return CREATE_MESSAGES.generic;
}

/** El error de la lista como ApiError con el mensaje de la pantalla (lo pinta DataTable). */
export function listError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => (e.status === HTTP_FORBIDDEN ? LIST_MESSAGES.forbidden : e.status === HTTP_TOO_MANY ? LIST_MESSAGES.tooMany(waitText(e.retryAfterS)) : LIST_MESSAGES.failed),
    LIST_MESSAGES.failed,
  );
}

/** ¿Puede salir bien al reintentar? Un 4xx (permiso, no existe) no; un 5xx, la red o lo ajeno sí. */
export function isTransientError(error: unknown): boolean {
  return !(isApiError(error) && isClientErrorStatus(error.status));
}

/** El mensaje del detalle fallido: 403 del coach sobre un inactivo (S2-D26), 404 y el resto. */
export function detailErrorMessage(error: unknown): string {
  const screen = toScreenError(
    error,
    (e) => (e.status === HTTP_FORBIDDEN ? DETAIL_MESSAGES.forbidden : e.status === HTTP_NOT_FOUND ? DETAIL_MESSAGES.notFound : DETAIL_MESSAGES.failed),
    DETAIL_MESSAGES.failed,
  );
  return screen?.message ?? DETAIL_MESSAGES.failed;
}

// S4A-F4 · US-080 a US-082: errores de editar, activar o desactivar y dar de baja.
export const UPDATE_MESSAGES = {
  forbidden: "Solo un administrador puede editar planes. Si lo necesitas, pídeselo a uno.",
  notFound: "Este plan ya no existe: lo dieron de baja. Cierra el panel y elige otro de la lista.",
  tooMany: (wait: string) => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos guardar el plan. Intenta de nuevo en un momento.",
  generic: "No pudimos guardar el plan. Revisa los datos e intenta de nuevo.",
} as const;

export const ACTIVE_MESSAGES = {
  forbidden: "Solo un administrador puede activar o desactivar planes. Si lo necesitas, pídeselo a uno.",
  notFound: "Este plan ya no existe: lo dieron de baja. La lista se actualiza sola.",
  tooMany: (wait: string) => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
  generic: "No pudimos cambiar el estado del plan. Intenta de nuevo en un momento.",
} as const;

export const DELETE_MESSAGES = {
  forbidden: "Solo un administrador puede dar de baja planes. Si lo necesitas, pídeselo a uno.",
  notFound: "Este plan ya estaba dado de baja. La lista se actualiza sola.",
  tooMany: (wait: string) => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
  inUse: "Este plan tiene membresías activas, desactívalo en su lugar.",
  generic: "No pudimos dar de baja el plan. Intenta de nuevo en un momento.",
} as const;

/** Mensaje general de una edición fallida (lo que no va bajo un campo). */
export function updateErrorMessage(error: unknown): string {
  if (!isApiError(error)) return UPDATE_MESSAGES.generic;
  return connectionMessage(error) ?? statusMessage(error, UPDATE_MESSAGES);
}

/** El error de activar o desactivar con el mensaje de la pantalla (ConfirmModal o aviso). */
export function activeError(error: unknown): ApiError {
  return toFormError(error, (e) => statusMessage(e, ACTIVE_MESSAGES), ACTIVE_MESSAGES.generic);
}

/** El error de la baja con el mensaje de la pantalla (ConfirmModal). */
export function deleteError(error: unknown): ApiError {
  return toFormError(error, (e) => statusMessage(e, DELETE_MESSAGES), DELETE_MESSAGES.generic);
}

/** Tope del mensaje del api que se pinta (el del 409 es corto; uno anómalo no desborda el aviso). */
const IN_USE_MAX_LENGTH = 300;

/**
 * El 409 `plan_has_active_memberships`: el mensaje del api (solo el conteo, S4A-D60), o null si es
 * otro error. Se pinta como texto; sin mensaje, el propio.
 */
export function planInUseMessage(error: unknown): string | null {
  if (!isApiError(error) || error.status !== HTTP_CONFLICT || error.code !== API_ERROR_CODES.planHasActiveMemberships) return null;
  const text = error.message.trim();
  return text === "" ? DELETE_MESSAGES.inUse : Array.from(text).slice(0, IN_USE_MAX_LENGTH).join("");
}
