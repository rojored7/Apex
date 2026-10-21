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
}

export class ApiError extends Error {
  override readonly name = "ApiError";
  /** Código HTTP; 0 cuando no hubo respuesta (red caída o timeout). */
  readonly status: number;
  readonly code: string;
  readonly field: string | undefined;
  readonly existingId: string | undefined;

  constructor({ status, code, message, field, existingId }: ApiErrorInit) {
    super(message);
    this.status = status;
    this.code = code;
    this.field = field;
    this.existingId = existingId;
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

/** Convierte la respuesta de error del api (texto o JSON ya leído) en un ApiError. */
export function parseApiError(status: number, body: unknown): ApiError {
  const parsed = envelopeSchema.safeParse(decode(body));
  if (!parsed.success) {
    return new ApiError({ status, code: "network_error", message: GENERIC_MESSAGES.network_error });
  }
  const { code, message, field, existing_id } = parsed.data.error;
  return new ApiError({ status, code, message, field: field ?? undefined, existingId: existing_id ?? undefined });
}
