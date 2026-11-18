// S9-F2: errores del api de RMs y récords en palabras de la pantalla («qué pasó y qué hacer»). Nunca el texto técnico del api.
// - rmsListError y recordsListError: lo que pinta una consulta (403, 404, 429, 5xx).
// - recordFieldError: el 422 con `field` va bajo su campo del formulario «Registrar récord».
// - recordSaveError: POST .../records (403, 404, 409 record_duplicate, 429, 5xx).
// - invalidateRecordError: POST .../invalidate (403 del coach, 404, 409 record_is_derived y record_already_invalidated, 429, 5xx).
// - S9-F3: benchmarksListError y benchmarkSeriesError (403, 404, 429, 5xx) de la subpestaña Benchmarks.
// - isStaleRecordError: el error dice que la lista que se ve quedó vieja (hay que releerla).
import type { FieldPath } from "react-hook-form";
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { statusMessage, toFormError, toScreenError, waitText } from "../../shared/lib/apiMessages";
import type { RecordFormValues } from "./schemas";

export const RECORD_ERROR_MESSAGES = {
  memberGone: "Este socio ya no existe. Vuelve a Socios y elige otro.",
  tooManyReads: (wait: string): string => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`,
  rmsFailed: "No pudimos cargar los RMs. Intenta de nuevo en un momento.",
  rmsForbidden: "No tienes permiso para ver los RMs de este socio.",
  recordsFailed: "No pudimos cargar los récords. Intenta de nuevo en un momento.",
  recordsForbidden: "No tienes permiso para ver los récords de este socio.",
  saveDuplicate: "Ya registraste ese mismo récord. Revisa la lista antes de guardarlo otra vez.",
  saveForbidden: "No tienes permiso para registrar récords. Si lo necesitas, pídeselo a un administrador.",
  saveGone: "El socio ya no existe o está dado de baja: no se pueden registrar récords.",
  saveTooMany: (wait: string): string => `Guardaste muchos récords seguidos. Espera ${wait} e intenta de nuevo.`,
  saveFailed: "No pudimos guardar el récord. Intenta de nuevo en un momento.",
  invalidateForbidden: "Solo un administrador puede invalidar este récord. Un coach solo invalida el que registró él en las últimas 24 horas.",
  invalidateDerived: "Este récord es automático: se corrige corrigiendo o anulando el resultado que lo originó. Actualizamos la lista.",
  invalidateAlready: "Este récord ya estaba invalidado. Actualizamos la lista.",
  invalidateGone: "Este récord ya no existe. Actualizamos la lista.",
  invalidateTooMany: (wait: string): string => `Invalidaste muchos récords seguidos. Espera ${wait} e intenta de nuevo.`,
  invalidateFailed: "No pudimos invalidar el récord. Intenta de nuevo en un momento.",
  movementsFailed: "No pudimos cargar los movimientos. Intenta de nuevo en un momento.",
  benchmarksFailed: "No pudimos cargar los benchmarks. Intenta de nuevo en un momento.",
  benchmarksForbidden: "No tienes permiso para ver los benchmarks de este socio.",
  seriesFailed: "No pudimos cargar la serie de este benchmark. Intenta de nuevo en un momento.",
  benchmarkGone: "Este benchmark ya no está en el catálogo. Elige otro.",
  noKgMovements: "No hay movimientos activos que se midan en kg. Créalos en Movimientos.",
} as const;

const M = RECORD_ERROR_MESSAGES;

export function rmsListError(error: unknown): ApiError | null {
  return toScreenError(error, (e) => statusMessage(e, { notFound: M.memberGone, forbidden: M.rmsForbidden, tooMany: M.tooManyReads, generic: M.rmsFailed }), M.rmsFailed);
}

export function recordsListError(error: unknown): ApiError | null {
  return toScreenError(error, (e) => statusMessage(e, { notFound: M.memberGone, forbidden: M.recordsForbidden, tooMany: M.tooManyReads, generic: M.recordsFailed }), M.recordsFailed);
}

export function benchmarksListError(error: unknown): ApiError | null {
  return toScreenError(error, (e) => statusMessage(e, { notFound: M.memberGone, forbidden: M.benchmarksForbidden, tooMany: M.tooManyReads, generic: M.benchmarksFailed }), M.benchmarksFailed);
}

function seriesText(error: ApiError): string {
  // 404 de la serie: el benchmark (benchmark_not_found) o el socio (member_not_found) ya no existen.
  if (error.status === HTTP_NOT_FOUND) return error.code === API_ERROR_CODES.memberNotFound ? M.memberGone : M.benchmarkGone;
  return statusMessage(error, { forbidden: M.benchmarksForbidden, tooMany: M.tooManyReads, generic: M.seriesFailed });
}

export function benchmarkSeriesError(error: unknown): ApiError | null {
  return toScreenError(error, seriesText, M.seriesFailed);
}

const CHECK_MARK = "Revisa la marca: el servidor no la aceptó. Corrígela y vuelve a guardar.";
const CHECK_LOAD = "Revisa la carga: el servidor no la aceptó. Corrígela y vuelve a guardar.";

/** Campo del api → campo del formulario y su mensaje. */
const FIELD_ERRORS: Readonly<Record<string, { path: FieldPath<RecordFormValues>; message: string }>> = {
  value_g: { path: "load", message: CHECK_LOAD },
  load_g: { path: "load", message: CHECK_LOAD },
  movement_id: { path: "movement_id", message: "Revisa el movimiento: el servidor no lo aceptó. Elige otro y vuelve a guardar." },
  benchmark_id: { path: "benchmark_id", message: "Revisa el benchmark: el servidor no lo aceptó. Elige otro y vuelve a guardar." },
  achieved_on: { path: "achieved_on", message: "Revisa la fecha: el servidor no la aceptó. Corrígela y vuelve a guardar." },
  seconds: { path: "time", message: CHECK_MARK },
  rounds: { path: "rounds", message: CHECK_MARK },
  reps: { path: "reps", message: CHECK_MARK },
};

export interface RecordFieldError {
  path: FieldPath<RecordFormValues>;
  message: string;
}

/** El 422 con `field` conocido va bajo su campo; cualquier otro error es general. */
export function recordFieldError(error: unknown): RecordFieldError | null {
  if (!isApiError(error) || error.status !== HTTP_UNPROCESSABLE || error.field === undefined) return null;
  return FIELD_ERRORS[error.field] ?? null;
}

function saveText(error: ApiError): string {
  if (error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.recordDuplicate) return M.saveDuplicate;
  if (error.status === HTTP_FORBIDDEN) return M.saveForbidden;
  if (error.status === HTTP_NOT_FOUND) return M.saveGone;
  if (error.status === HTTP_TOO_MANY) return M.saveTooMany(waitText(error.retryAfterS));
  return M.saveFailed;
}

/** El mensaje general de un error al guardar un récord (los de campo salen de `recordFieldError`). */
export function recordSaveError(error: unknown): ApiError {
  return toFormError(error, saveText, M.saveFailed);
}

function invalidateText(error: ApiError): string {
  if (error.status === HTTP_FORBIDDEN) return M.invalidateForbidden;
  if (error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.recordIsDerived) return M.invalidateDerived;
  if (error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.recordAlreadyInvalidated) return M.invalidateAlready;
  if (error.status === HTTP_NOT_FOUND) return M.invalidateGone;
  if (error.status === HTTP_TOO_MANY) return M.invalidateTooMany(waitText(error.retryAfterS));
  return M.invalidateFailed;
}

/** El error de «Invalidar» con su mensaje (lo pinta el ConfirmModal). */
export function invalidateRecordError(error: unknown): ApiError {
  return toFormError(error, invalidateText, M.invalidateFailed);
}

/** ¿El error dice que el récord ya no se puede invalidar (derivado, ya invalidado o inexistente)? La lista que se ve quedó vieja. */
export function isStaleRecordError(error: unknown): boolean {
  if (!isApiError(error)) return false;
  if (error.status === HTTP_NOT_FOUND) return true;
  return error.status === HTTP_CONFLICT && (error.code === API_ERROR_CODES.recordIsDerived || error.code === API_ERROR_CODES.recordAlreadyInvalidated);
}
