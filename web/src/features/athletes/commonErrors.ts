// V7 L7: lo que repiten los errores de las pantallas del atleta (athleteErrors y recordErrors): los dos mensajes de lectura que
// comparten y el 422 con `field` que va bajo su campo del formulario.
import type { FieldPath, FieldValues } from "react-hook-form";
import { isApiError } from "../../core/api/errors";
import { HTTP_UNPROCESSABLE } from "../../core/api/status";

export const COMMON_ERROR_MESSAGES = {
  memberGone: "Este socio ya no existe. Vuelve a Socios y elige otro.",
  tooManyReads: (wait: string): string => `Hiciste muchas consultas seguidas. Espera ${wait} e intenta de nuevo.`,
} as const;

export interface FieldErrorTarget<V extends FieldValues> {
  path: FieldPath<V>;
  message: string;
}

/** El 422 con `field` conocido de `table` va bajo su campo; cualquier otro error es general (`null`). */
export function fieldErrorIn<V extends FieldValues>(table: Readonly<Record<string, FieldErrorTarget<V>>>, error: unknown): FieldErrorTarget<V> | null {
  if (!isApiError(error) || error.status !== HTTP_UNPROCESSABLE || error.field === undefined) return null;
  return table[error.field] ?? null;
}
