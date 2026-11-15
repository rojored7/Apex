// S8-F2: errores del api de WODs en palabras de la pantalla («qué pasó y qué hacer»).
// - wodFieldError: 409 `wod_date_taken` bajo «Fecha» (con el id del existente), 422 `locked_by_results`,
//   `score_type_mismatch` y 422 con `field` bajo su campo.
// - wodSaveMessage: el resto (403, 404, 429, 5xx, red) como aviso general. wodsListError: error de las listas.
import type { FieldPath } from "react-hook-form";
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, statusMessage, toScreenError, waitText } from "../../shared/lib/apiMessages";
import type { WodFormValues } from "./wodSchemas";

export const DATE_TAKEN_MESSAGE = "Ya hay un WOD para esa fecha. Ábrelo para editarlo o elige otro día.";
export const LOCKED_MESSAGE = "Este WOD ya tiene resultados: este dato no se puede cambiar. Crea un WOD nuevo si necesitas otro.";
export const MISMATCH_MESSAGE = "El tipo de marca no coincide con el del benchmark. Elige el tipo del benchmark.";

export const WOD_SAVE_MESSAGES = {
  forbidden: "No tienes permiso para guardar WODs. Si lo necesitas, pídeselo a un administrador.",
  notFound: "Este WOD ya no existe. Vuelve a la lista de WODs.",
  tooMany: (wait: string): string => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos guardar el WOD. Intenta de nuevo en un momento.",
  generic: "No pudimos guardar el WOD. Revisa los datos e intenta de nuevo.",
} as const;

export const WODS_LIST_MESSAGES = {
  forbidden: "No tienes permiso para ver los WODs. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string): string => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos cargar los WODs. Intenta de nuevo en un momento.",
} as const;

export const WOD_LOAD_MESSAGES = {
  forbidden: "No tienes permiso para ver este WOD. Si lo necesitas, pídeselo a un administrador.",
  notFound: "Este WOD ya no existe. Vuelve a la lista de WODs.",
  failed: "No pudimos cargar el WOD. Intenta de nuevo en un momento.",
} as const;

export interface WodFieldError {
  path: FieldPath<WodFormValues>;
  message: string;
  /** El WOD que ya ocupa la fecha (409). */
  existingId?: string | undefined;
}

const FIELDS: Readonly<Record<string, FieldPath<WodFormValues>>> = {
  date: "date",
  title: "title",
  score_type: "score_type",
  benchmark_id: "benchmark_id",
  time_cap_s: "time_cap_min",
  description: "description",
  movements: "movements",
};

export function wodFieldError(error: unknown): WodFieldError | null {
  if (!isApiError(error)) return null;
  if (error.status === HTTP_CONFLICT && (error.code === API_ERROR_CODES.wodDateTaken || error.field === "date")) {
    return { path: "date", message: DATE_TAKEN_MESSAGE, existingId: error.existingId };
  }
  if (error.status !== HTTP_UNPROCESSABLE) return null;
  const path = error.field ? FIELDS[error.field] : undefined;
  if (!path) return null;
  if (error.code === API_ERROR_CODES.lockedByResults) return { path, message: LOCKED_MESSAGE };
  if (error.code === API_ERROR_CODES.scoreTypeMismatch) return { path, message: MISMATCH_MESSAGE };
  return null;
}

export function wodSaveMessage(error: unknown): string {
  if (!isApiError(error)) return WOD_SAVE_MESSAGES.generic;
  return connectionMessage(error) ?? statusMessage(error, WOD_SAVE_MESSAGES);
}

export function wodsListError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => (e.status === HTTP_FORBIDDEN ? WODS_LIST_MESSAGES.forbidden : e.status === HTTP_TOO_MANY ? WODS_LIST_MESSAGES.tooMany(waitText(e.retryAfterS)) : WODS_LIST_MESSAGES.failed),
    WODS_LIST_MESSAGES.failed,
  );
}

export function wodLoadError(error: unknown): ApiError | null {
  return toScreenError(error, (e) => (e.status === HTTP_FORBIDDEN ? WOD_LOAD_MESSAGES.forbidden : e.status === 404 ? WOD_LOAD_MESSAGES.notFound : WOD_LOAD_MESSAGES.failed), WOD_LOAD_MESSAGES.failed);
}
