// S3-F4 · US-095 y US-097 (front): errores de registrar y anular pagos en palabras de la pantalla
// ("qué pasó y qué hacer"). Los mensajes del api no se muestran: pueden nombrar campos en inglés.
// - registerFieldError: lo que va bajo un campo del panel, con foco (`amount_cop`, `method`,
//   `reference`, `paid_at`; 409 `membership_cancelled` y 404 `membership_not_found` bajo Membresía).
// - registerAlert: el resto, como aviso general (límite de 60 pagos, 403, 429 con la espera, 5xx,
//   red, busy y respuesta inválida con los mensajes comunes).
// - isOverpaymentError e isDuplicateError: 409 que no son errores para el usuario sino una
//   confirmación (S3-D41).
// - toVoidError: el error de anular como ApiError con el mensaje de la pantalla (ConfirmModal lo
//   pinta bajo el motivo si `field = "reason"` o en su alerta).
import type { FieldPath } from "react-hook-form";
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { ApiError, isApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_NOT_FOUND, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, statusMessage, toFormError, toScreenError } from "../../shared/lib/apiMessages";
import { AMOUNT_RANGE_MESSAGE } from "../../shared/data/schemas/money";
import { REFERENCE_MESSAGES } from "../../shared/data/schemas/payment";
import type { RegisterPaymentFormValues } from "./schemas";

// Fase 4 del Sprint 3 (M7): ningún texto fija un valor de negocio que decide el api. El tope hacia
// atrás del coach es `max_retroactive_days` de Configuración (N-18): el coach no la lee y el 422
// `paid_at_too_retroactive` no trae el número, así que el texto no lo dice. La ventana del duplicado
// (120 s, `DUPLICATE_WINDOW` del api) tampoco.
export const PAYMENT_MESSAGES = {
  memberRequired: "Elige el socio que paga.",
  membershipRequired: "Elige la membresía a la que se abona el pago.",
  amountRequired: "Escribe el valor recibido.",
  amountInvalid: "Escribe el valor en pesos enteros, sin centavos (por ejemplo $ 60.000).",
  amountRange: AMOUNT_RANGE_MESSAGE,
  amountServer: "El servidor no aceptó este valor. Revísalo e intenta de nuevo.",
  methodRequired: "Elige el medio de pago.",
  referenceServer: REFERENCE_MESSAGES.pattern,
  paidAtRequired: "Escribe la fecha y la hora del pago.",
  paidAtInvalid: "Escribe una fecha y una hora del pago válidas.",
  paidAtFuture: "La fecha del pago no puede estar en el futuro.",
  paidAtTooRetroactive: "Como coach solo puedes registrar pagos de los días que permite el gimnasio. Pídele a un administrador que registre este pago.",
  paidAtServer: "El servidor no aceptó la fecha del pago. Revísala e intenta de nuevo.",
  membershipCancelled: "Esta membresía está anulada y ya no recibe pagos. Elige otra o vende una nueva.",
  membershipNotFound: "No encontramos esta membresía. Elige otra de la lista.",
  membershipFromUrlFailed: "No pudimos cargar la membresía de este enlace. Reintenta o cierra el panel y ábrelo de nuevo desde la lista.",
  limitReached: "Esta membresía ya tiene el máximo de pagos registrados. Revisa sus pagos antes de registrar otro.",
  forbidden: "No tienes permiso para registrar pagos. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string) => `Registraste muchos pagos seguidos. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos registrar el pago. Intenta de nuevo en un momento.",
  generic: "No pudimos registrar el pago. Revisa los datos e intenta de nuevo.",
  searchFailed: "No pudimos buscar socios. Intenta de nuevo en un momento.",
  membershipsFailed: "No pudimos cargar las membresías del socio. Intenta de nuevo.",
  methodsFailed: "No pudimos cargar los nombres de los medios de pago; se muestran los de siempre.",
  noOpenMemberships: "Este socio no tiene membresías que reciban pagos.",
  overpayTitle: "¿Registrar un pago mayor al saldo?",
  overpay: (excess: string) => `Este pago supera el saldo de la membresía en ${excess}. No queda saldo a favor.`,
  overpayUnknown: "El valor supera el saldo de la membresía. No queda saldo a favor.",
  duplicateTitle: "¿Registrar otro pago igual?",
  duplicate: "Ya registraste un pago igual hace unos minutos. Regístralo solo si es un pago distinto.",
} as const;

export const VOID_MESSAGES = {
  title: "¿Anular este pago?",
  consequence: "El pago no se borra: queda anulado con este motivo.",
  alreadyVoided: "Otra persona lo anuló antes. Actualizamos el pago para que veas su estado.",
  notFound: "No encontramos este pago. Actualiza la lista e intenta de nuevo.",
  reasonInvalid: "Escribe un motivo de 1 a 500 caracteres, sin caracteres invisibles.",
  forbidden: "Solo un administrador puede anular pagos.",
  tooMany: (wait: string) => `Hiciste muchas anulaciones seguidas. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos anular el pago. Intenta de nuevo en un momento.",
  generic: "No pudimos anular el pago. Intenta de nuevo.",
  doneTitle: "Pago anulado",
  done: (amount: string) => `El pago de ${amount} quedó anulado. Si el socio pagó de otra forma, registra el pago correcto.`,
} as const;

export interface RegisterFieldError {
  path: FieldPath<RegisterPaymentFormValues>;
  message: string;
}

const FIELD_TARGETS: Readonly<Record<string, RegisterFieldError>> = {
  amount_cop: { path: "amount", message: PAYMENT_MESSAGES.amountServer },
  method: { path: "method", message: PAYMENT_MESSAGES.methodRequired },
  reference: { path: "reference", message: PAYMENT_MESSAGES.referenceServer },
  paid_at: { path: "paidAt", message: PAYMENT_MESSAGES.paidAtServer },
};

const isCode = (error: unknown, status: number, code: string): boolean => isApiError(error) && error.status === status && error.code === code;

/** 409 `payment_exceeds_balance`: se pide confirmar el sobrepago (Q5, S3-D41). */
export function isOverpaymentError(error: unknown): boolean {
  return isCode(error, HTTP_CONFLICT, API_ERROR_CODES.paymentExceedsBalance);
}

/** 409 `payment_possible_duplicate`: se pide confirmar que es otro pago (S3-D41). */
export function isDuplicateError(error: unknown): boolean {
  return isCode(error, HTTP_CONFLICT, API_ERROR_CODES.paymentPossibleDuplicate);
}

/** 409 `membership_cancelled`: la lista de membresías del socio quedó vieja. */
export function isMembershipCancelledError(error: unknown): boolean {
  return isCode(error, HTTP_CONFLICT, API_ERROR_CODES.membershipCancelled);
}

/** El error que va bajo un campo del panel, o null si es un aviso general. */
export function registerFieldError(error: unknown): RegisterFieldError | null {
  if (!isApiError(error)) return null;
  if (isMembershipCancelledError(error)) return { path: "membershipId", message: PAYMENT_MESSAGES.membershipCancelled };
  if (error.status === HTTP_NOT_FOUND && error.code === API_ERROR_CODES.membershipNotFound) return { path: "membershipId", message: PAYMENT_MESSAGES.membershipNotFound };
  if (error.status !== HTTP_UNPROCESSABLE) return null;
  if (error.code === API_ERROR_CODES.paidAtTooRetroactive) return { path: "paidAt", message: PAYMENT_MESSAGES.paidAtTooRetroactive };
  return error.field ? (FIELD_TARGETS[error.field] ?? null) : null;
}

/** El aviso general de un registro que falló. */
export function registerAlert(error: unknown): string {
  if (!isApiError(error)) return PAYMENT_MESSAGES.generic;
  const connection = connectionMessage(error);
  if (connection) return connection;
  if (error.code === API_ERROR_CODES.paymentLimitReached) return PAYMENT_MESSAGES.limitReached;
  return statusMessage(error, { forbidden: PAYMENT_MESSAGES.forbidden, tooMany: PAYMENT_MESSAGES.tooMany, server: PAYMENT_MESSAGES.server, generic: PAYMENT_MESSAGES.generic });
}

function voidMessage(error: ApiError): string {
  if (error.code === API_ERROR_CODES.paymentAlreadyVoided) return VOID_MESSAGES.alreadyVoided;
  if (error.status === HTTP_UNPROCESSABLE && error.field === "reason") return VOID_MESSAGES.reasonInvalid;
  return statusMessage(error, VOID_MESSAGES);
}

/** El error de anular con el mensaje de la pantalla; conserva status, code y field. */
export function toVoidError(error: unknown): ApiError {
  return toFormError(error, voidMessage, VOID_MESSAGES.generic);
}

// S3-F6 · US-098, US-099 y US-100 (front): la lista de pagos, el detalle y el resumen del mes.
export const LIST_MESSAGES = {
  forbidden: "No tienes permiso para ver los pagos. Si lo necesitas, pídeselo a un administrador.",
  invalidFilters: "Revisa las fechas del filtro: alguna está fuera del rango permitido. Límpialas e intenta de nuevo.",
  tooMany: (wait: string) => `Hiciste muchas búsquedas seguidas. Espera ${wait} e intenta de nuevo.`,
  generic: "No pudimos cargar los pagos. Intenta de nuevo.",
} as const;

export const DETAIL_MESSAGES = {
  notFound: "No encontramos este pago. Cierra el detalle y actualiza la lista.",
  forbidden: "No tienes permiso para ver este pago. Si lo necesitas, pídeselo a un administrador.",
  generic: "No pudimos cargar el pago. Intenta de nuevo.",
} as const;

export const SUMMARY_MESSAGES = {
  /** D23: el api acepta meses de 2020 a 2100 (422 `field="month"`). */
  monthOutOfRange: "Elige un mes entre enero de 2020 y diciembre de 2100.",
} as const;

/** El error de la lista de pagos como ApiError con el mensaje de la pantalla, o null. */
export function paymentListError(error: unknown): ApiError | null {
  return toScreenError(error, (e) => statusMessage(e, { ...LIST_MESSAGES, unprocessable: LIST_MESSAGES.invalidFilters }), LIST_MESSAGES.generic);
}

/** El mensaje del detalle que no cargó (red, busy, 404, 403 o cualquier otro). */
export function paymentDetailMessage(error: unknown): string {
  return toScreenError(error, (e) => statusMessage(e, DETAIL_MESSAGES), DETAIL_MESSAGES.generic)?.message ?? DETAIL_MESSAGES.generic;
}

/** Un 422 del mes del resumen: se explica el rango en vez de mostrar tarjetas en error. */
export function isMonthOutOfRange(error: unknown): boolean {
  return isApiError(error) && error.status === HTTP_UNPROCESSABLE && error.field === "month";
}

// S3-F7 · US-101 (front): errores de la pestaña Pagos de la ficha (GET /members/{id}/payments).
export const MEMBER_TAB_MESSAGES = {
  notFound: "No encontramos a este socio. Vuelve a la lista de socios.",
  forbidden: "No tienes permiso para ver los pagos. Si lo necesitas, pídeselo a un administrador.",
  generic: "No pudimos cargar los pagos de este socio. Intenta de nuevo.",
} as const;

/** El error de la pestaña como ApiError con el mensaje de la pantalla, o null. */
export function memberTabError(error: unknown): ApiError | null {
  return toScreenError(error, (e) => statusMessage(e, MEMBER_TAB_MESSAGES), MEMBER_TAB_MESSAGES.generic);
}
