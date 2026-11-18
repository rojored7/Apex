// S9-F1: errores del api de atleta en palabras de la pantalla («qué pasó y qué hacer»). Nunca el texto técnico del api ni un valor.
// - summaryError y metricsListError: lo que pinta una consulta (resumen y lista de medidas).
// - metricSaveError: POST .../metrics (409 consent_required con el enlace a la ficha, 422 bajo su campo, 403, 404, 429, 5xx).
// - fieldErrorOf: el 422 con `field` va bajo su campo del formulario.
// - revealMetricError: POST .../reveal (403 con el socio dado de baja, 409 metric_voided, 429, 5xx y 503 crypto_unavailable).
// - voidMetricError: POST .../void (403 del coach, 409 metric_already_voided).
import type { FieldPath } from "react-hook-form";
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, statusMessage, toFormError, toScreenError, waitText } from "../../shared/lib/apiMessages";
import type { MetricFormValues } from "./schemas";

export const METRIC_ERROR_MESSAGES = {
  summaryFailed: "No pudimos cargar el resumen. Intenta de nuevo en un momento.",
  summaryForbidden: "No tienes permiso para ver el perfil del atleta.",
  listFailed: "No pudimos cargar las medidas. Intenta de nuevo en un momento.",
  listForbidden: "No tienes permiso para ver las medidas de este socio.",
  memberGone: "Este socio ya no existe. Vuelve a Socios y elige otro.",
  tooManyReads: (wait: string): string => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`,
  consentMissing: "Falta la autorización de datos del socio. Regístrala en su ficha para guardar medidas.",
  saveForbidden: "No tienes permiso para registrar medidas. Si lo necesitas, pídeselo a un administrador.",
  saveGone: "El socio ya no existe o está dado de baja: no se pueden registrar medidas.",
  saveTooMany: (wait: string): string => `Guardaste muchas medidas seguidas. Espera ${wait} e intenta de nuevo.`,
  saveFailed: "No pudimos guardar las medidas. Intenta de nuevo en un momento.",
  revealDeleted: "Este socio está dado de baja: solo un administrador puede mostrar sus medidas.",
  revealForbidden: "No tienes permiso para ver este dato",
  revealVoided: "Esta medición está anulada y ya no se puede mostrar.",
  revealTooMany: "Demasiadas consultas; espera un momento",
  revealFailed: "No pudimos mostrar el dato. Intenta de nuevo en un momento.",
  voidForbidden: "Solo un administrador puede anular esta medición. Un coach solo anula la que registró él en las últimas 24 horas.",
  voidAlready: "Esta medición ya estaba anulada. Actualizamos la lista.",
  voidGone: "Esta medición ya no existe. Actualizamos la lista.",
  voidTooMany: (wait: string): string => `Anulaste muchas medidas seguidas. Espera ${wait} e intenta de nuevo.`,
  voidFailed: "No pudimos anular la medición. Intenta de nuevo en un momento.",
} as const;

const M = METRIC_ERROR_MESSAGES;

export function summaryError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => statusMessage(e, { notFound: M.memberGone, forbidden: M.summaryForbidden, tooMany: M.tooManyReads, generic: M.summaryFailed }),
    M.summaryFailed,
  );
}

export function metricsListError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => statusMessage(e, { notFound: M.memberGone, forbidden: M.listForbidden, tooMany: M.tooManyReads, generic: M.listFailed }),
    M.listFailed,
  );
}

/** Campo del api → campo del formulario y su mensaje. */
const FIELD_ERRORS: Readonly<Record<string, { path: FieldPath<MetricFormValues>; message: string }>> = {
  weight_g: { path: "weight_kg", message: "Revisa el peso: el servidor no lo aceptó. Corrígelo y vuelve a guardar." },
  height_cm: { path: "height_cm", message: "Revisa la altura: el servidor no la aceptó. Corrígela y vuelve a guardar." },
  body_fat_pct: { path: "body_fat_pct", message: "Revisa el % de grasa: el servidor no lo aceptó. Corrígelo y vuelve a guardar." },
  notes: { path: "notes", message: "Revisa las notas: el servidor no las aceptó. Corrígelas y vuelve a guardar." },
  measured_on: { path: "measured_on", message: "Revisa la fecha: el servidor no la aceptó. Corrígela y vuelve a guardar." },
};

export interface MetricFieldError {
  path: FieldPath<MetricFormValues>;
  message: string;
}

/** El 422 con `field` conocido va bajo su campo; cualquier otro error es general. */
export function fieldErrorOf(error: unknown): MetricFieldError | null {
  if (!isApiError(error) || error.status !== HTTP_UNPROCESSABLE || error.field === undefined) return null;
  return FIELD_ERRORS[error.field] ?? null;
}

/** ¿El api dice que falta la autorización de datos del socio? (409 `consent_required`, H-1). */
export function isConsentRequired(error: unknown): boolean {
  return isApiError(error) && error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.consentRequired;
}

function saveText(error: ApiError): string {
  if (isConsentRequired(error)) return M.consentMissing;
  if (error.status === HTTP_FORBIDDEN) return M.saveForbidden;
  if (error.status === HTTP_NOT_FOUND) return M.saveGone;
  if (error.status === HTTP_TOO_MANY) return M.saveTooMany(waitText(error.retryAfterS));
  return M.saveFailed;
}

/** El mensaje general de un error al guardar medidas (los de campo salen de `fieldErrorOf`). */
export function metricSaveError(error: unknown): ApiError | null {
  return error ? toFormError(error, saveText, M.saveFailed) : null;
}

/** El error de «Mostrar»: el api dice 403 y la pantalla explica si es por la baja del socio (S9-D34). */
export function revealMetricError(error: unknown, memberDeleted: boolean): string {
  if (!isApiError(error)) return M.revealFailed;
  const connection = connectionMessage(error);
  if (connection !== null) return connection;
  if (error.status === HTTP_FORBIDDEN) return memberDeleted ? M.revealDeleted : M.revealForbidden;
  if (error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.metricVoided) return M.revealVoided;
  if (error.status === HTTP_TOO_MANY) return M.revealTooMany;
  return M.revealFailed;
}

function voidText(error: ApiError): string {
  if (error.status === HTTP_FORBIDDEN) return M.voidForbidden;
  if (error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.metricAlreadyVoided) return M.voidAlready;
  if (error.status === HTTP_NOT_FOUND) return M.voidGone;
  if (error.status === HTTP_TOO_MANY) return M.voidTooMany(waitText(error.retryAfterS));
  return M.voidFailed;
}

/** El error de «Anular» con su mensaje (lo pinta el ConfirmModal). */
export function voidMetricError(error: unknown): ApiError {
  return toFormError(error, voidText, M.voidFailed);
}
