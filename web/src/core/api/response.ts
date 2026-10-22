// Revisión del Sprint 2 (M5): toda respuesta del api se valida con Zod antes de usarla. Una
// forma inesperada es un error (`invalid_response`, status 0) con un mensaje "qué pasó y qué
// hacer", nunca datos. Antes cada feature tenía su copia del mensaje y de la función.
import type { ZodType, ZodTypeDef } from "zod";
import { CLIENT_ERROR_CODES } from "./errorCodes";
import { ApiError } from "./errors";

export const INVALID_RESPONSE_MESSAGE = "La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.";

export const INVALID_RESPONSE_CODE = CLIENT_ERROR_CODES.invalidResponse;

export function invalidResponseError(): ApiError {
  return new ApiError({ status: 0, code: INVALID_RESPONSE_CODE, message: INVALID_RESPONSE_MESSAGE });
}

/** Devuelve el cuerpo validado o lanza `invalid_response`. */
export function parseResponse<T>(schema: ZodType<T, ZodTypeDef, unknown>, raw: unknown): T {
  const parsed = schema.safeParse(raw);
  if (!parsed.success) throw invalidResponseError();
  return parsed.data;
}
