// S2-F6: errores del api de socios en palabras de la pantalla ("qué pasó y qué hacer").
// - fieldErrorOf: el 422 con `field` (incluido L-3, un valor que se normaliza a vacío) y el 409
//   `member_document_duplicated` van bajo su campo. Los mensajes son propios: el del api nombra
//   el campo en inglés ("El campo email no es válido.") y nunca repite el valor.
// - createErrorMessage y listError: el resto (403, 429 con la espera, 5xx, red, respuesta
//   inválida) como mensaje general.
import type { FieldPath } from "react-hook-form";
import { API_ERROR_CODES, CLIENT_ERROR_CODES } from "../../core/api/errorCodes";
import { ApiError, isApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, statusMessage, toScreenError } from "../../shared/lib/apiMessages";
import { MEMBER_MESSAGES, type MemberEditValues, type MemberFormValues } from "./schemas";

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
  if (error.status === HTTP_CONFLICT && (error.code === API_ERROR_CODES.memberDocumentDuplicated || error.field === "document")) {
    return { path: "document", message: CREATE_MESSAGES.duplicated, existingId: error.existingId ?? null };
  }
  if (error.status !== HTTP_UNPROCESSABLE || !error.field) return null;
  const target = FIELD_ERRORS[error.field];
  return target ? { ...target, existingId: null } : null;
}

/** Mensaje general de un alta fallida. */
export function createErrorMessage(error: unknown): string {
  if (!isApiError(error)) return CREATE_MESSAGES.generic;
  const connection = connectionMessage(error);
  if (connection) return connection;
  return statusMessage(error, { forbidden: CREATE_MESSAGES.forbidden, tooMany: CREATE_MESSAGES.tooMany, server: CREATE_MESSAGES.server, generic: CREATE_MESSAGES.generic });
}

/** El error de la lista como ApiError con el mensaje de la pantalla (lo pinta DataTable). */
export function listError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => statusMessage(e, { forbidden: LIST_MESSAGES.forbidden, tooMany: LIST_MESSAGES.tooMany, generic: LIST_MESSAGES.failed }),
    LIST_MESSAGES.failed,
  );
}

// ---------------------------------------------------------------------------------------------
// S3-F1 · US-073 a US-076: ficha, revelar, editar, dar de baja y reactivar.
// - detailErrorOf: la carga de la ficha (404 "Socio no encontrado", 403, 429 con la espera, 5xx,
//   red, busy, respuesta inválida).
// - revealError: el error de "Mostrar" como ApiError con el mensaje de la pantalla; MaskedValue
//   muestra su `message` (el 403 lo traduce él mismo). Los tres cupos dan 429 (RUNBOOK §4).
// - editFieldErrorOf / editErrorMessage: el PATCH. 403 `forbidden_field` y 409 de documento bajo su
//   campo (S2-D34, con enlace), `consent_cannot_be_withdrawn` bajo la autorización, 422 con `field`
//   bajo ese campo; el resto como aviso general.
// - statusChangeError / duplicatedMemberId: dar de baja y reactivar (ConfirmModal muestra el
//   `message`; el 409 de documento al reactivar sale con el id del socio vivo).

export const DETAIL_MESSAGES = {
  notFound: "Socio no encontrado",
  notFoundHint: "Puede que el enlace esté mal escrito. Búscalo en la lista de socios.",
  forbidden: "No tienes permiso para ver este socio. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string) => `Abriste muchas fichas seguidas. Espera ${wait} e intenta de nuevo.`,
  failed: "No pudimos cargar la ficha del socio. Intenta de nuevo en un momento.",
  refreshFailed: "No pudimos actualizar la ficha; se muestran los últimos datos cargados. Recarga la página en un momento.",
} as const;

export const REVEAL_MESSAGES = {
  tooMany: "Demasiadas consultas; espera un momento",
  notFound: "Este socio ya no existe. Vuelve a la lista de socios.",
  failed: "No pudimos mostrar el dato. Intenta de nuevo en un momento.",
} as const;

export const EDIT_ERROR_MESSAGES = {
  documentForbidden: "Solo un administrador puede cambiar el documento.",
  consentWithdrawn: "La autorización no se puede retirar desde aquí. Si el socio la retira, pídeselo a un administrador.",
  deactivated: "Este socio está dado de baja. Reactívalo desde su ficha antes de editarlo.",
  forbidden: "No tienes permiso para editar socios. Si lo necesitas, pídeselo a un administrador.",
  notFound: "Este socio ya no existe. Vuelve a la lista de socios.",
  tooMany: (wait: string) => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos guardar los cambios. Intenta de nuevo en un momento.",
  generic: "No pudimos guardar los cambios. Revisa los datos e intenta de nuevo.",
} as const;

export const STATUS_CHANGE_MESSAGES = {
  alreadyDeactivated: "Otra persona ya dio de baja a este socio. Cierra y recarga la ficha.",
  notDeactivated: "Este socio ya estaba activo. Cierra y recarga la ficha.",
  duplicated: "No se puede reactivar: otro socio activo ya tiene este documento.",
  forbidden: { deactivate: "No tienes permiso para dar de baja socios. Si lo necesitas, pídeselo a un administrador.", reactivate: "No tienes permiso para reactivar socios. Si lo necesitas, pídeselo a un administrador." },
  notFound: "Este socio ya no existe. Vuelve a la lista de socios.",
  tooMany: (wait: string) => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
  server: { deactivate: "No pudimos dar de baja al socio. Intenta de nuevo en un momento.", reactivate: "No pudimos reactivar al socio. Intenta de nuevo en un momento." },
} as const;

export interface DetailError {
  /** 404: la pantalla muestra "Socio no encontrado" en vez del aviso con "Reintentar". */
  notFound: boolean;
  message: string;
}

export function detailErrorOf(error: unknown): DetailError {
  if (isApiError(error) && error.status === HTTP_NOT_FOUND) return { notFound: true, message: DETAIL_MESSAGES.notFoundHint };
  const screen = toScreenError(
    error,
    (e) => statusMessage(e, { forbidden: DETAIL_MESSAGES.forbidden, tooMany: DETAIL_MESSAGES.tooMany, generic: DETAIL_MESSAGES.failed }),
    DETAIL_MESSAGES.failed,
  );
  return { notFound: false, message: screen?.message ?? DETAIL_MESSAGES.failed };
}

/** El error de "Mostrar" con el mensaje de la pantalla; conserva status y code (el 403 lo traduce MaskedValue). */
export function revealError(error: unknown): ApiError {
  return (
    toScreenError(
      error,
      (e) => statusMessage(e, { tooMany: () => REVEAL_MESSAGES.tooMany, notFound: REVEAL_MESSAGES.notFound, generic: REVEAL_MESSAGES.failed }),
      REVEAL_MESSAGES.failed,
    ) ?? new ApiError({ status: 0, code: CLIENT_ERROR_CODES.unknown, message: REVEAL_MESSAGES.failed })
  );
}

/** Campo del api → campo de la edición, con su mensaje (los 422 por campo). */
const EDIT_FIELD_ERRORS: Readonly<Record<string, { path: FieldPath<MemberEditValues>; message: string }>> = {
  ...FIELD_ERRORS,
  data_consent: { path: "data_consent", message: RECHECK },
};

export interface EditFieldError {
  path: FieldPath<MemberEditValues>;
  message: string;
  /** 409: el socio vivo que ya tiene ese documento (S2-D34). */
  existingId: string | null;
}

/** El error del PATCH que va bajo un campo, o null si es un aviso general. */
export function editFieldErrorOf(error: unknown): EditFieldError | null {
  if (!isApiError(error)) return null;
  if (error.status === HTTP_FORBIDDEN && error.code === API_ERROR_CODES.forbiddenField) {
    return { path: error.field === "document_type" ? "document_type" : "document", message: EDIT_ERROR_MESSAGES.documentForbidden, existingId: null };
  }
  if (error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.memberDocumentDuplicated) {
    return { path: "document", message: CREATE_MESSAGES.duplicated, existingId: error.existingId ?? null };
  }
  if (error.code === API_ERROR_CODES.consentCannotBeWithdrawn) return { path: "data_consent", message: EDIT_ERROR_MESSAGES.consentWithdrawn, existingId: null };
  if (error.status !== HTTP_UNPROCESSABLE || !error.field) return null;
  const target = EDIT_FIELD_ERRORS[error.field];
  return target ? { ...target, existingId: null } : null;
}

/** El aviso general de un PATCH fallido. */
export function editErrorMessage(error: unknown): string {
  if (!isApiError(error)) return EDIT_ERROR_MESSAGES.generic;
  const connection = connectionMessage(error);
  if (connection) return connection;
  if (error.code === API_ERROR_CODES.memberDeactivated) return EDIT_ERROR_MESSAGES.deactivated;
  return statusMessage(error, EDIT_ERROR_MESSAGES);
}

export type StatusChange = "deactivate" | "reactivate";

function statusChangeMessage(error: ApiError, change: StatusChange): string {
  if (error.code === API_ERROR_CODES.memberAlreadyDeactivated) return STATUS_CHANGE_MESSAGES.alreadyDeactivated;
  if (error.code === API_ERROR_CODES.memberNotDeactivated) return STATUS_CHANGE_MESSAGES.notDeactivated;
  if (error.code === API_ERROR_CODES.memberDocumentDuplicated) return STATUS_CHANGE_MESSAGES.duplicated;
  return statusMessage(error, {
    forbidden: STATUS_CHANGE_MESSAGES.forbidden[change],
    notFound: STATUS_CHANGE_MESSAGES.notFound,
    tooMany: STATUS_CHANGE_MESSAGES.tooMany,
    generic: STATUS_CHANGE_MESSAGES.server[change],
  });
}

/** El error de dar de baja o reactivar como ApiError con el mensaje que muestra ConfirmModal. */
export function statusChangeError(error: unknown, change: StatusChange): ApiError {
  return (
    toScreenError(error, (e) => statusChangeMessage(e, change), STATUS_CHANGE_MESSAGES.server[change]) ??
    new ApiError({ status: 0, code: CLIENT_ERROR_CODES.unknown, message: STATUS_CHANGE_MESSAGES.server[change] })
  );
}

/** 409 `member_document_duplicated` con `existing_id`: el id del socio vivo; si no, null. */
export function duplicatedMemberId(error: unknown): string | null {
  if (!isApiError(error) || error.status !== HTTP_CONFLICT || error.code !== API_ERROR_CODES.memberDocumentDuplicated) return null;
  return error.existingId ?? null;
}

// ---------------------------------------------------------------------------------------------
// S4A-F2 · US-106: el historial de la ficha (pestaña y caja "Historial reciente"). 429 de la cubeta
// `staff-read` (S4A-D45), 404 del socio, 403, 5xx, red, base ocupada y respuesta inválida.
export const HISTORY_MESSAGES = {
  tooMany: "Demasiadas consultas; espera un momento",
  notFound: "Este socio ya no existe. Vuelve a la lista de socios.",
  forbidden: "No tienes permiso para ver el historial de este socio. Si lo necesitas, pídeselo a un administrador.",
  failed: "No pudimos cargar el historial. Intenta de nuevo en un momento.",
  loadMoreFailed: "No pudimos cargar más entradas del historial. Intenta de nuevo.",
} as const;

/** El error del historial como ApiError con el mensaje de la pantalla (HistoryAside pinta su `message`). */
export function historyError(error: unknown): ApiError | null {
  return toScreenError(
    error,
    (e) => statusMessage(e, { tooMany: () => HISTORY_MESSAGES.tooMany, notFound: HISTORY_MESSAGES.notFound, forbidden: HISTORY_MESSAGES.forbidden, generic: HISTORY_MESSAGES.failed }),
    HISTORY_MESSAGES.failed,
  );
}

/** Revisión S4A-F2 (LOW-1): un `:id` sin forma de UUID no se pide al api; la pestaña dice que no existe. */
export function historyNotFoundError(): ApiError {
  return new ApiError({ status: HTTP_NOT_FOUND, code: CLIENT_ERROR_CODES.unknown, message: HISTORY_MESSAGES.notFound });
}
