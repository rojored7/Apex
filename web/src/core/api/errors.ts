// US-059 T4: errores del api. El envelope es { error: { code, message, field?, existing_id? } }
// (04_architecture_decision.md sección 5). Todo lo que no tenga esa forma, como un 502 de
// Nginx, se vuelve network_error con un mensaje genérico en español.
import { z } from "zod";

export const GENERIC_MESSAGES = {
  network_error: "No pudimos conectar con el servidor. Intenta de nuevo.",
  timeout: "El servidor tardó demasiado en responder. Intenta de nuevo.",
} as const;

export interface ApiErrorInit {
  status: number;
  code: string;
  message: string;
  field?: string | undefined;
  existingId?: string | undefined;
  /** Segundos de `Retry-After` de un 429 (S2-F3); sin cabecera válida, `undefined`. */
  retryAfterS?: number | undefined;
}

export class ApiError extends Error {
  override readonly name = "ApiError";
  /** Código HTTP; 0 cuando no hubo respuesta (red caída o timeout). */
  readonly status: number;
  readonly code: string;
  readonly field: string | undefined;
  readonly existingId: string | undefined;
  readonly retryAfterS: number | undefined;

  constructor({ status, code, message, field, existingId, retryAfterS }: ApiErrorInit) {
    super(message);
    this.status = status;
    this.code = code;
    this.field = field;
    this.existingId = existingId;
    this.retryAfterS = retryAfterS;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

const envelopeSchema = z.object({
  error: z.object({
    code: z.string().min(1),
    message: z.string(),
    field: z.string().nullish(),
    existing_id: z.string().nullish(),
  }),
});

function decode(body: unknown): unknown {
  if (typeof body !== "string") return body;
  if (body.trim() === "") return null;
  try {
    return JSON.parse(body) as unknown;
  } catch {
    return null;
  }
}

/** Un día: más que eso no es una espera razonable de un 429 y se ignora. */
const MAX_RETRY_AFTER_S = 86_400;
const MS_PER_S = 1_000;

/**
 * S2-F3: segundos de `Retry-After` (RFC 9110): un entero de segundos o una fecha HTTP. Una
 * fecha pasada da 0; un valor vacío, negativo, decimal o absurdo da `undefined`.
 */
export function parseRetryAfter(value: string | null | undefined, nowMs: number = Date.now()): number | undefined {
  const text = value?.trim() ?? "";
  if (text === "") return undefined;
  if (/^\d+$/.test(text)) {
    const seconds = Number(text);
    return seconds <= MAX_RETRY_AFTER_S ? seconds : undefined;
  }
  if (!/[a-z]/i.test(text)) return undefined;
  const at = Date.parse(text);
  if (Number.isNaN(at)) return undefined;
  const seconds = Math.ceil((at - nowMs) / MS_PER_S);
  return Math.min(Math.max(seconds, 0), MAX_RETRY_AFTER_S);
}

/**
 * Convierte la respuesta de error del api (texto o JSON ya leído) en un ApiError. Con la
 * cabecera `Retry-After` (429) guarda la espera en segundos.
 */
export function parseApiError(status: number, body: unknown, retryAfter?: string | null): ApiError {
  const retryAfterS = parseRetryAfter(retryAfter);
  const parsed = envelopeSchema.safeParse(decode(body));
  if (!parsed.success) {
    return new ApiError({ status, code: "network_error", message: GENERIC_MESSAGES.network_error, retryAfterS });
  }
  const { code, message, field, existing_id } = parsed.data.error;
  return new ApiError({ status, code, message, field: field ?? undefined, existingId: existing_id ?? undefined, retryAfterS });
}
