// S3-F3 · US-084, US-085 y US-088 (front): errores de la venta en palabras de la pantalla ("qué
// pasó y qué hacer"). Los mensajes del api no se muestran: pueden nombrar campos en inglés.
// - sellFieldError: lo que va bajo un campo, con foco. El api prefija los errores del primer pago
//   con `first_payment.` (E5): `first_payment.amount_cop`, `first_payment.paid_at`...
// - sellAlert: el resto, como aviso general arriba del formulario. 409 `membership_conflict`
//   enlaza a la renovación del socio (`?socio=:id&renovar=1`); 409 `future_membership_exists`, a su
//   ficha (llega con US-073, S3-F1). 503 `busy`, red y respuesta inválida usan los mensajes comunes.
// - isOverpaymentError: 409 `payment_exceeds_balance` (S3-D41) no es un error para el usuario: abre
//   la confirmación del sobrepago.
import type { FieldPath } from "react-hook-form";
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { isApiError, type ApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_SERVER_ERROR, HTTP_TOO_MANY, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, waitText } from "../../shared/lib/apiMessages";
import { REFERENCE_MESSAGES } from "../../shared/data/schemas/payment";
import { memberHref, renewHref } from "./membershipLinks";
import type { SellFormValues } from "./schemas";

export const SELL_MESSAGES = {
  memberRequired: "Elige el socio al que le vendes la membresía.",
  planRequired: "Elige un plan.",
  startDateRequired: "Escribe la fecha de inicio.",
  startDateInvalid: "Escribe una fecha de inicio válida (día, mes y año).",
  startDateTooFar: "La fecha de inicio está muy lejos. Elige una dentro del próximo año.",
  startDateTooRetroactive: "La fecha de inicio es demasiado antigua. Elige una más reciente.",
  overlap: "Estas fechas se cruzan con otra membresía del socio. Elige otra fecha de inicio.",
  planUnavailable: "Este plan ya no está disponible para vender. Elige otro.",
  amountRequired: "Escribe el valor recibido.",
  amountInvalid: "Escribe el valor en pesos enteros, sin centavos (por ejemplo $ 120.000).",
  amountRange: "El valor debe estar entre $ 1 y $ 1.000.000.000.",
  amountServer: "El servidor no aceptó este valor. Revísalo e intenta de nuevo.",
  methodRequired: "Elige el medio de pago.",
  paidAtRequired: "Escribe la fecha y la hora del pago.",
  paidAtInvalid: "Escribe una fecha y una hora del pago válidas.",
  paidAtFuture: "La fecha del pago no puede estar en el futuro.",
  paidAtTooRetroactive: "La fecha del pago es demasiado antigua para tu rol. Pídele a un administrador que lo registre.",
  paidAtServer: "El servidor no aceptó la fecha del pago. Revísala e intenta de nuevo.",
  conflict: (name: string) => `${name} ya tiene una membresía vigente o por empezar. Si quieres extenderla, renuévala.`,
  futureExists: (name: string) => `${name} ya tiene una renovación por empezar. Revísala en su ficha.`,
  memberInactive: "Este socio no está activo. Reactívalo antes de venderle una membresía.",
  memberNotFound: "No encontramos a este socio. Búscalo de nuevo.",
  limitReached: "Esta membresía ya tiene el máximo de pagos registrados. Revisa sus pagos.",
  forbidden: "No tienes permiso para vender membresías. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string) => `Hiciste muchas ventas seguidas. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos registrar la venta. Intenta de nuevo en un momento.",
  generic: "No pudimos registrar la venta. Revisa los datos e intenta de nuevo.",
  previewFailed: "No pudimos calcular las fechas de la renovación. Intenta de nuevo.",
  plansFailed: "No pudimos cargar los planes. Intenta de nuevo.",
  methodsFailed: "No pudimos cargar los nombres de los medios de pago; se muestran los de siempre.",
  searchFailed: "No pudimos buscar socios. Intenta de nuevo en un momento.",
} as const;

/** Quién es el socio en los avisos cuando no se conoce su nombre. */
export const UNKNOWN_MEMBER = "Este socio";

export interface SellFieldError {
  path: FieldPath<SellFormValues>;
  message: string;
}

const START_DATE_ERRORS: Readonly<Record<string, string>> = {
  [API_ERROR_CODES.startDateTooRetroactive]: SELL_MESSAGES.startDateTooRetroactive,
  [API_ERROR_CODES.startDateTooFar]: SELL_MESSAGES.startDateTooFar,
};

const PAYMENT_FIELDS: Readonly<Record<string, SellFieldError>> = {
  "first_payment.amount_cop": { path: "amount", message: SELL_MESSAGES.amountServer },
  "first_payment.method": { path: "method", message: SELL_MESSAGES.methodRequired },
  "first_payment.reference": { path: "reference", message: REFERENCE_MESSAGES.pattern },
  "first_payment.paid_at": { path: "paidAt", message: SELL_MESSAGES.paidAtServer },
};

function paymentFieldError(error: ApiError): SellFieldError | null {
  const target = error.field ? PAYMENT_FIELDS[error.field] : undefined;
  if (!target) return null;
  if (target.path === "paidAt" && error.code === API_ERROR_CODES.paidAtTooRetroactive) return { path: "paidAt", message: SELL_MESSAGES.paidAtTooRetroactive };
  return target;
}

/** El error que va bajo un campo, o null si es un aviso general. */
export function sellFieldError(error: unknown): SellFieldError | null {
  if (!isApiError(error)) return null;
  if (error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.membershipOverlap) return { path: "startDate", message: SELL_MESSAGES.overlap };
  if (error.status !== HTTP_UNPROCESSABLE) return null;
  const startDate = START_DATE_ERRORS[error.code];
  if (startDate) return { path: "startDate", message: startDate };
  if (error.code === API_ERROR_CODES.planInvalid || error.code === API_ERROR_CODES.planInactive) return { path: "planId", message: SELL_MESSAGES.planUnavailable };
  if (error.field === "start_date") return { path: "startDate", message: SELL_MESSAGES.startDateInvalid };
  return paymentFieldError(error);
}

/** 409 `payment_exceeds_balance`: se pide confirmar el sobrepago (S3-D41). */
export function isOverpaymentError(error: unknown): boolean {
  return isApiError(error) && error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.paymentExceedsBalance;
}

export interface SellAlertAction {
  href: string;
  text: string;
}

export interface SellAlert {
  message: string;
  action?: SellAlertAction;
}

export interface SellAlertContext {
  memberId: string;
  /** Nombre del socio, o null si no se conoce (renovar desde un enlace directo). */
  memberName: string | null;
}

/** Un 409 que se explica con un enlace al socio: renovarlo o ver su ficha. */
function conflictAlert(error: ApiError, { memberId, memberName }: SellAlertContext): SellAlert | null {
  const name = memberName ?? UNKNOWN_MEMBER;
  if (error.code === API_ERROR_CODES.membershipConflict) return { message: SELL_MESSAGES.conflict(name), action: { href: renewHref(memberId), text: "Renovar" } };
  if (error.code === API_ERROR_CODES.futureMembershipExists) return { message: SELL_MESSAGES.futureExists(name), action: { href: memberHref(memberId), text: "Ver ficha del socio" } };
  if (error.code === API_ERROR_CODES.paymentLimitReached) return { message: SELL_MESSAGES.limitReached };
  return null;
}

function statusMessage(error: ApiError): string {
  if (error.code === API_ERROR_CODES.memberInactive) return SELL_MESSAGES.memberInactive;
  if (error.status === HTTP_NOT_FOUND) return SELL_MESSAGES.memberNotFound;
  if (error.status === HTTP_FORBIDDEN) return SELL_MESSAGES.forbidden;
  if (error.status === HTTP_TOO_MANY) return SELL_MESSAGES.tooMany(waitText(error.retryAfterS));
  if (error.status >= HTTP_SERVER_ERROR) return SELL_MESSAGES.server;
  return SELL_MESSAGES.generic;
}

/** El aviso general de una venta (o de la vista previa) que falló. */
export function sellAlert(error: unknown, context: SellAlertContext): SellAlert {
  if (!isApiError(error)) return { message: SELL_MESSAGES.generic };
  const connection = connectionMessage(error);
  if (connection) return { message: connection };
  if (error.status === HTTP_CONFLICT) return conflictAlert(error, context) ?? { message: SELL_MESSAGES.generic };
  return { message: statusMessage(error) };
}

/** ¿Es el 409 de la vista previa que impide renovar (ya hay una renovación por empezar)? */
export function isFutureMembershipError(error: unknown): boolean {
  return isApiError(error) && error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.futureMembershipExists;
}
