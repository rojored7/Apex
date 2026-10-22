// S2-F6: errores del api de socios en palabras de la pantalla ("qué pasó y qué hacer").
// - fieldErrorOf: el 422 con `field` (incluido L-3, un valor que se normaliza a vacío) y el 409
//   `member_document_duplicated` van bajo su campo. Los mensajes son propios: el del api nombra
//   el campo en inglés ("El campo email no es válido.") y nunca repite el valor.
// - createErrorMessage y listError: el resto (403, 429 con la espera, 5xx, red, respuesta
//   inválida) como mensaje general.
import type { FieldPath } from "react-hook-form";
import { ApiError, GENERIC_MESSAGES, isApiError } from "../../core/api/errors";
import { MEMBER_MESSAGES, type MemberFormValues } from "./schemas";

const HTTP_FORBIDDEN = 403;
const HTTP_CONFLICT = 409;
const HTTP_UNPROCESSABLE = 422;
const HTTP_TOO_MANY = 429;
const HTTP_SERVER_ERROR = 500;

export const CREATE_MESSAGES = {
  duplicated: "Ya existe un socio con este documento.",
  forbidden: "No tienes permiso para registrar socios. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string) => `Registraste muchos socios seguidos. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos registrar el socio. Intenta de nuevo en un momento.",
  generic: "No pudimos registrar el socio. Revisa los datos e intenta de nuevo.",
} as const;

export const LIST_MESSAGES = {
  forbidden: "No tienes permiso para ver los socios. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string) => `Hiciste muchas búsquedas seguidas. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos cargar los socios. Intenta de nuevo en un momento.",
} as const;

const RECHECK = "Revisa este dato e intenta de nuevo.";

/** Campo del api → campo del formulario y su mensaje. */
const FIELD_ERRORS: Readonly<Record<string, { path: FieldPath<MemberFormValues>; message: string }>> = {
  first_name: { path: "first_name", message: MEMBER_MESSAGES.firstNameRequired },
  last_name: { path: "last_name", message: MEMBER_MESSAGES.lastNameRequired },
  sex: { path: "sex", message: MEMBER_MESSAGES.sex },
  document_type: { path: "document_type", message: MEMBER_MESSAGES.documentType },
  document: { path: "document", message: "El documento no tiene letras ni números válidos. Revísalo e intenta de nuevo." },
  birth_date: { path: "birth_date", message: MEMBER_MESSAGES.birthDateFuture },
  phone: { path: "phone", message: "El teléfono no tiene suficientes dígitos. Revísalo e intenta de nuevo." },
  email: { path: "email", message: "El servidor no aceptó este correo. Revísalo e intenta de nuevo." },
  emergency_contact: { path: "emergency_contact.name", message: RECHECK },
  "emergency_contact.name": { path: "emergency_contact.name", message: RECHECK },
  "emergency_contact.phone": { path: "emergency_contact.phone", message: RECHECK },
  "emergency_contact.relationship": { path: "emergency_contact.relationship", message: RECHECK },
};

export interface MemberFieldError {
  path: FieldPath<MemberFormValues>;
  message: string;
  /** 409: el socio que ya tiene ese documento (S2-D34). */
  existingId: string | null;
}

/** El error que va bajo un campo, o null si es un error general. */
export function fieldErrorOf(error: unknown): MemberFieldError | null {
  if (!isApiError(error)) return null;
  if (error.status === HTTP_CONFLICT && (error.code === "member_document_duplicated" || error.field === "document")) {
    return { path: "document", message: CREATE_MESSAGES.duplicated, existingId: error.existingId ?? null };
  }
  if (error.status !== HTTP_UNPROCESSABLE || !error.field) return null;
  const target = FIELD_ERRORS[error.field];
  return target ? { ...target, existingId: null } : null;
}

/** "30 segundos", "1 segundo" o "un momento" (sin Retry-After). */
export function waitText(seconds: number | undefined): string {
  if (seconds === undefined || seconds <= 0) return "un momento";
  return seconds === 1 ? "1 segundo" : `${String(seconds)} segundos`;
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

/** El error de la lista como ApiError con el mensaje de la pantalla (lo pinta DataTable). */
export function listError(error: unknown): ApiError | null {
  if (!error) return null;
  if (!isApiError(error)) return new ApiError({ status: 0, code: "unknown", message: LIST_MESSAGES.failed });
  const connection = connectionMessage(error);
  if (connection) return new ApiError({ status: error.status, code: error.code, message: connection });
  const message =
    error.status === HTTP_FORBIDDEN ? LIST_MESSAGES.forbidden : error.status === HTTP_TOO_MANY ? LIST_MESSAGES.tooMany(waitText(error.retryAfterS)) : LIST_MESSAGES.failed;
  return new ApiError({ status: error.status, code: error.code, message });
}
