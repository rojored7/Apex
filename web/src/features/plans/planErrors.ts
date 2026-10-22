// S2-F7: errores del api de planes en palabras de la pantalla ("qué pasó y qué hacer").
// - fieldErrorOf: el 422 con `field` (PlanCreate y validate_plan de B9) y el 409
//   `plan_name_duplicated` (S2-D32, `field="name"` y `existing_id`) van bajo su campo. Los mensajes
//   son propios: el del api nombra el campo en inglés y nunca repite el valor.
// - createErrorMessage, listError y detailError: el resto (403, 404, 429 con la espera, 5xx, red,
//   respuesta inválida) como mensaje general.
import type { FieldPath } from "react-hook-form";
import { ApiError, GENERIC_MESSAGES, isApiError } from "../../core/api/errors";
import { waitText } from "../members/memberErrors";
import { PLAN_MESSAGES, type PlanFormValues } from "./schemas";

const HTTP_CLIENT_ERROR = 400;
const HTTP_FORBIDDEN = 403;
const HTTP_NOT_FOUND = 404;
const HTTP_CONFLICT = 409;
const HTTP_UNPROCESSABLE = 422;
const HTTP_TOO_MANY = 429;
const HTTP_SERVER_ERROR = 500;

export const INVALID_RESPONSE_MESSAGE = "La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.";

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
  if (error.status === HTTP_CONFLICT && (error.code === "plan_name_duplicated" || error.field === "name")) {
    return { path: "name", message: PLAN_MESSAGES.duplicated, existingId: error.existingId ?? null };
  }
  if (error.status !== HTTP_UNPROCESSABLE || !error.field) return null;
  const target = FIELD_ERRORS[error.field];
  return target ? { ...target, existingId: null } : null;
}

function connectionMessage(error: ApiError): string | null {
  if (error.code === "invalid_response") return error.message;
  if (error.status === 0) return error.code === "timeout" ? GENERIC_MESSAGES.timeout : GENERIC_MESSAGES.network_error;
  return null;
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

function asScreenError(error: unknown, message: (error: ApiError) => string, fallback: string): ApiError | null {
  if (!error) return null;
  if (!isApiError(error)) return new ApiError({ status: 0, code: "unknown", message: fallback });
  const connection = connectionMessage(error);
  return new ApiError({ status: error.status, code: error.code, message: connection ?? message(error) });
}

/** El error de la lista como ApiError con el mensaje de la pantalla (lo pinta DataTable). */
export function listError(error: unknown): ApiError | null {
  return asScreenError(
    error,
    (e) => (e.status === HTTP_FORBIDDEN ? LIST_MESSAGES.forbidden : e.status === HTTP_TOO_MANY ? LIST_MESSAGES.tooMany(waitText(e.retryAfterS)) : LIST_MESSAGES.failed),
    LIST_MESSAGES.failed,
  );
}

/** ¿Puede salir bien al reintentar? Un 4xx (permiso, no existe) no; un 5xx, la red o lo ajeno sí. */
export function isTransientError(error: unknown): boolean {
  return !(isApiError(error) && error.status >= HTTP_CLIENT_ERROR && error.status < HTTP_SERVER_ERROR);
}

/** El mensaje del detalle fallido: 403 del coach sobre un inactivo (S2-D26), 404 y el resto. */
export function detailErrorMessage(error: unknown): string {
  const screen = asScreenError(
    error,
    (e) => (e.status === HTTP_FORBIDDEN ? DETAIL_MESSAGES.forbidden : e.status === HTTP_NOT_FOUND ? DETAIL_MESSAGES.notFound : DETAIL_MESSAGES.failed),
    DETAIL_MESSAGES.failed,
  );
  return screen?.message ?? DETAIL_MESSAGES.failed;
}
