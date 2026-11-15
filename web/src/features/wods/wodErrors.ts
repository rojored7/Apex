// S8-F1: errores del api de movimientos y benchmarks en palabras de la pantalla («qué pasó y qué hacer»).
// - movementFieldError y benchmarkFieldError: el 409 de nombre duplicado y el 422 con `field` van bajo su campo
//   (`score_type_locked` bajo «Tipo de marca»). Los mensajes son propios: los del api nombran el campo en inglés.
// - movementSaveMessage y benchmarkSaveMessage: el resto (403, 404, 429, 5xx, red) como aviso general.
// - movementsListError y benchmarksListError: el error de la lista como ApiError con el mensaje de la pantalla.
import type { FieldPath } from "react-hook-form";
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, statusMessage, toScreenError, waitText } from "../../shared/lib/apiMessages";
import { BENCHMARK_MESSAGES, MOVEMENT_MESSAGES, type BenchmarkFormValues, type MovementFormValues } from "./schemas";

export const MOVEMENT_EXISTS_MESSAGE = "Ya existe un movimiento con ese nombre. Búscalo en la lista o usa otro nombre.";
export const BENCHMARK_EXISTS_MESSAGE = "Ya existe un benchmark con ese nombre. Búscalo en la lista o usa otro nombre.";
export const SCORE_TYPE_LOCKED_MESSAGE = "Ya hay WODs que usan este benchmark: el tipo de marca no se puede cambiar.";

const tooMany = (wait: string): string => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`;
const tooManyReads = (wait: string): string => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`;

export const MOVEMENT_SAVE_MESSAGES = {
  forbidden: "No tienes permiso para guardar movimientos. Si lo necesitas, pídeselo a un administrador.",
  notFound: "Este movimiento ya no existe. Cierra el panel y actualiza la lista.",
  tooMany,
  server: "No pudimos guardar el movimiento. Intenta de nuevo en un momento.",
  generic: "No pudimos guardar el movimiento. Revisa los datos e intenta de nuevo.",
} as const;

export const BENCHMARK_SAVE_MESSAGES = {
  forbidden: "No tienes permiso para guardar benchmarks. Si lo necesitas, pídeselo a un administrador.",
  notFound: "Este benchmark ya no existe. Cierra el panel y actualiza la lista.",
  tooMany,
  server: "No pudimos guardar el benchmark. Intenta de nuevo en un momento.",
  generic: "No pudimos guardar el benchmark. Revisa los datos e intenta de nuevo.",
} as const;

export const MOVEMENTS_LIST_MESSAGES = {
  forbidden: "No tienes permiso para ver los movimientos. Si lo necesitas, pídeselo a un administrador.",
  tooMany: tooManyReads,
  failed: "No pudimos cargar los movimientos. Intenta de nuevo en un momento.",
} as const;

export const BENCHMARKS_LIST_MESSAGES = {
  forbidden: "No tienes permiso para ver los benchmarks. Si lo necesitas, pídeselo a un administrador.",
  tooMany: tooManyReads,
  failed: "No pudimos cargar los benchmarks. Intenta de nuevo en un momento.",
} as const;

export interface MovementFieldError {
  path: FieldPath<MovementFormValues>;
  message: string;
}

export interface BenchmarkFieldError {
  path: FieldPath<BenchmarkFormValues>;
  message: string;
}

const MOVEMENT_FIELDS: Readonly<Record<string, MovementFieldError>> = {
  name: { path: "name", message: MOVEMENT_MESSAGES.name },
  category: { path: "category", message: MOVEMENT_MESSAGES.category },
  unit: { path: "unit", message: MOVEMENT_MESSAGES.unit },
};

const BENCHMARK_FIELDS: Readonly<Record<string, BenchmarkFieldError>> = {
  name: { path: "name", message: BENCHMARK_MESSAGES.name },
  score_type: { path: "score_type", message: BENCHMARK_MESSAGES.scoreType },
  description: { path: "description", message: BENCHMARK_MESSAGES.description },
};

/** El error que va bajo un campo del formulario de movimiento, o null si es general. */
export function movementFieldError(error: unknown): MovementFieldError | null {
  if (!isApiError(error)) return null;
  if (error.status === HTTP_CONFLICT && (error.code === API_ERROR_CODES.movementExists || error.field === "name")) return { path: "name", message: MOVEMENT_EXISTS_MESSAGE };
  if (error.status !== HTTP_UNPROCESSABLE || !error.field) return null;
  return MOVEMENT_FIELDS[error.field] ?? null;
}

/** El error que va bajo un campo del formulario de benchmark, o null si es general. */
export function benchmarkFieldError(error: unknown): BenchmarkFieldError | null {
  if (!isApiError(error)) return null;
  if (error.status === HTTP_CONFLICT && (error.code === API_ERROR_CODES.benchmarkExists || error.field === "name")) return { path: "name", message: BENCHMARK_EXISTS_MESSAGE };
  if (error.code === API_ERROR_CODES.scoreTypeLocked) return { path: "score_type", message: SCORE_TYPE_LOCKED_MESSAGE };
  if (error.status !== HTTP_UNPROCESSABLE || !error.field) return null;
  return BENCHMARK_FIELDS[error.field] ?? null;
}

export function movementSaveMessage(error: unknown): string {
  if (!isApiError(error)) return MOVEMENT_SAVE_MESSAGES.generic;
  return connectionMessage(error) ?? statusMessage(error, MOVEMENT_SAVE_MESSAGES);
}

export function benchmarkSaveMessage(error: unknown): string {
  if (!isApiError(error)) return BENCHMARK_SAVE_MESSAGES.generic;
  return connectionMessage(error) ?? statusMessage(error, BENCHMARK_SAVE_MESSAGES);
}

function listErrorOf(error: unknown, messages: { forbidden: string; tooMany: (wait: string) => string; failed: string }): ApiError | null {
  return toScreenError(
    error,
    (e) => (e.status === HTTP_FORBIDDEN ? messages.forbidden : e.status === HTTP_TOO_MANY ? messages.tooMany(waitText(e.retryAfterS)) : messages.failed),
    messages.failed,
  );
}

export const movementsListError = (error: unknown): ApiError | null => listErrorOf(error, MOVEMENTS_LIST_MESSAGES);
export const benchmarksListError = (error: unknown): ApiError | null => listErrorOf(error, BENCHMARKS_LIST_MESSAGES);
