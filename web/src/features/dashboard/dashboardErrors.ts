// S4A-F3 · US-108 a US-110: los errores de Inicio en palabras de la pantalla ("qué pasó y qué hacer"),
// con connectionMessage y statusMessage de shared/lib/apiMessages. GET /dashboard declara 429 (cubeta
// `staff-read`, S4A-D45): el mensaje dice cuánto esperar.
import { connectionMessage, statusMessage } from "../../shared/lib/apiMessages";
import { isApiError, type ApiError } from "../../core/api/errors";

export const DASHBOARD_MESSAGES = {
  failed: "No pudimos cargar el tablero. Intenta de nuevo en un momento.",
  movementsFailed: "No pudimos cargar los últimos movimientos. Intenta de nuevo en un momento.",
  forbidden: "No tienes permiso para ver el tablero. Pide acceso a un administrador.",
  tooMany: (wait: string) => `Demasiadas consultas seguidas; espera ${wait} y vuelve a intentarlo.`,
} as const;

function messageFor(error: ApiError, generic: string): string {
  return connectionMessage(error) ?? statusMessage(error, { forbidden: DASHBOARD_MESSAGES.forbidden, tooMany: DASHBOARD_MESSAGES.tooMany, generic });
}

/** El mensaje del tablero cuando GET /dashboard falla. */
export function dashboardErrorMessage(error: unknown): string {
  return isApiError(error) ? messageFor(error, DASHBOARD_MESSAGES.failed) : DASHBOARD_MESSAGES.failed;
}

/** El mensaje de "Últimos movimientos" cuando GET /dashboard falla. */
export function movementsErrorMessage(error: unknown): string {
  return isApiError(error) ? messageFor(error, DASHBOARD_MESSAGES.movementsFailed) : DASHBOARD_MESSAGES.movementsFailed;
}
