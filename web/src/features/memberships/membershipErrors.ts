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
import { ApiError, isApiError } from "../../core/api/errors";
import { HTTP_CONFLICT, HTTP_UNPROCESSABLE } from "../../core/api/status";
import { connectionMessage, statusMessage, toFormError, toScreenError } from "../../shared/lib/apiMessages";
import { AMOUNT_RANGE_MESSAGE } from "../../shared/data/schemas/money";
import { REFERENCE_MESSAGES } from "../../shared/data/schemas/payment";
import { memberHref, renewHref } from "./membershipLinks";
import type { FreezeFormValues, SellFormValues } from "./schemas";

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
  amountRange: AMOUNT_RANGE_MESSAGE,
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

function sellStatusMessage(error: ApiError): string {
  if (error.code === API_ERROR_CODES.memberInactive) return SELL_MESSAGES.memberInactive;
  return statusMessage(error, { ...SELL_MESSAGES, notFound: SELL_MESSAGES.memberNotFound });
}

/** El aviso general de una venta (o de la vista previa) que falló. */
export function sellAlert(error: unknown, context: SellAlertContext): SellAlert {
  if (!isApiError(error)) return { message: SELL_MESSAGES.generic };
  const connection = connectionMessage(error);
  if (connection) return { message: connection };
  if (error.status === HTTP_CONFLICT) return conflictAlert(error, context) ?? { message: SELL_MESSAGES.generic };
  return { message: sellStatusMessage(error) };
}

/** ¿Es el 409 de la vista previa que impide renovar (ya hay una renovación por empezar)? */
export function isFutureMembershipError(error: unknown): boolean {
  return isApiError(error) && error.status === HTTP_CONFLICT && error.code === API_ERROR_CODES.futureMembershipExists;
}

// S3-F5 · US-089 a US-092 (front): errores de la lista, de congelar y de anular.
// - listError: el error de GET /memberships en palabras de la pantalla (lo pinta DataTable).
// - freezeFieldError: los 422 de FreezeIn bajo su fecha (`frozen_from`, `frozen_to`; D14 y S3-B2).
// - freezeAlert: los 409 de estado y de límites (con los días que quedan, tomados del mensaje del
//   api: "Quedan N días de congelación para esta membresía.") y el resto como aviso del modal.
// - toCancelError: el error de anular como ApiError con el mensaje de la pantalla (ConfirmModal lo
//   pinta bajo el motivo si `field = "reason"` o en su alerta).
/** Los errores del formulario de congelar (freezeFormSchema) y el 422 equivalente del api. */
export const FREEZE_FORM_MESSAGES = {
  fromRequired: "Escribe desde qué fecha se congela.",
  fromInvalid: "Escribe una fecha de inicio válida.",
  toRequired: "Escribe hasta qué fecha se congela.",
  toInvalid: "Escribe una fecha final válida.",
  inverted: "La fecha final no puede ser anterior a la inicial.",
} as const;

export const LIST_MESSAGES = {
  forbidden: "No tienes permiso para ver las membresías. Si lo necesitas, pídeselo a un administrador.",
  invalidFilters: "Revisa los filtros: alguna fecha o estado no es válido. Límpialos e intenta de nuevo.",
  tooMany: (wait: string) => `Hiciste muchas búsquedas seguidas. Espera ${wait} e intenta de nuevo.`,
  generic: "No pudimos cargar las membresías. Intenta de nuevo.",
} as const;

export const FREEZE_MESSAGES = {
  notFreezable: "Esta membresía ya no se puede congelar: solo se congelan las membresías al día o por vencer.",
  alreadyScheduled: "Esta membresía ya tiene una congelación en curso o programada. Congélala de nuevo cuando esa termine.",
  limitReached: "Esta membresía ya usó todas las congelaciones que permite el gimnasio.",
  daysLeft: (days: number) =>
    days === 0
      ? "Esta membresía ya no tiene días de congelación disponibles."
      : `${days === 1 ? "Queda 1 día" : `Quedan ${String(days)} días`} de congelación para esta membresía. Elige un rango más corto.`,
  daysExceeded: "El rango supera los días de congelación que le quedan a esta membresía. Elige un rango más corto.",
  overlapsFuture: "Con esta congelación la membresía se cruzaría con la siguiente del socio. Elige menos días.",
  tooRetroactive: "La congelación no puede empezar tan atrás. Elige una fecha más reciente.",
  outsideValidity: "La congelación tiene que empezar dentro de la vigencia de la membresía.",
  memberInactive: "Este socio no está activo. Reactívalo antes de congelar su membresía.",
  notFound: "No encontramos esta membresía. Actualiza la lista e intenta de nuevo.",
  forbidden: "No tienes permiso para congelar membresías. Si lo necesitas, pídeselo a un administrador.",
  tooMany: (wait: string) => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos congelar la membresía. Intenta de nuevo en un momento.",
  generic: "No pudimos congelar la membresía. Revisa las fechas e intenta de nuevo.",
} as const;

export const CANCEL_MESSAGES = {
  alreadyCancelled: "Otra persona ya anuló esta membresía. Actualizamos la lista.",
  reasonInvalid: "Escribe un motivo de 5 a 500 caracteres, sin caracteres invisibles.",
  notFound: "No encontramos esta membresía. Actualiza la lista e intenta de nuevo.",
  forbidden: "Solo un administrador puede anular membresías.",
  tooMany: (wait: string) => `Hiciste muchos cambios seguidos. Espera ${wait} e intenta de nuevo.`,
  server: "No pudimos anular la membresía. Intenta de nuevo en un momento.",
  generic: "No pudimos anular la membresía. Intenta de nuevo.",
} as const;

/** El error de la lista de membresías como ApiError con el mensaje de la pantalla, o null. */
export function listError(error: unknown): ApiError | null {
  return toScreenError(error, (e) => statusMessage(e, { ...LIST_MESSAGES, unprocessable: LIST_MESSAGES.invalidFilters }), LIST_MESSAGES.generic);
}

export interface FreezeFieldError {
  path: FieldPath<FreezeFormValues>;
  message: string;
}

const FREEZE_FIELD_CODES: Readonly<Record<string, FreezeFieldError>> = {
  [API_ERROR_CODES.freezeTooRetroactive]: { path: "frozenFrom", message: FREEZE_MESSAGES.tooRetroactive },
  [API_ERROR_CODES.freezeOutsideValidity]: { path: "frozenFrom", message: FREEZE_MESSAGES.outsideValidity },
};

/** El 422 de congelar que va bajo una fecha, o null si es un aviso del modal. */
export function freezeFieldError(error: unknown): FreezeFieldError | null {
  if (!isApiError(error) || error.status !== HTTP_UNPROCESSABLE) return null;
  const byCode = FREEZE_FIELD_CODES[error.code];
  if (byCode) return byCode;
  if (error.field === "frozen_to") return { path: "frozenTo", message: error.code === API_ERROR_CODES.validationError ? FREEZE_FORM_MESSAGES.inverted : FREEZE_FORM_MESSAGES.toInvalid };
  if (error.field === "frozen_from") return { path: "frozenFrom", message: FREEZE_FORM_MESSAGES.fromInvalid };
  return null;
}

const DAYS_LEFT = /^Quedan? (\d+) días? de congelación/;

/** "Quedan 5 días de congelación…" del api (S3-B2): los días que quedan, o null si no los dice. */
export function freezeDaysLeft(message: string): number | null {
  const match = DAYS_LEFT.exec(message);
  return match ? Number(match[1]) : null;
}

const FREEZE_CONFLICTS: Readonly<Record<string, string>> = {
  [API_ERROR_CODES.membershipNotFreezable]: FREEZE_MESSAGES.notFreezable,
  [API_ERROR_CODES.freezeAlreadyScheduled]: FREEZE_MESSAGES.alreadyScheduled,
  [API_ERROR_CODES.freezeLimitReached]: FREEZE_MESSAGES.limitReached,
  [API_ERROR_CODES.overlapsFutureMembership]: FREEZE_MESSAGES.overlapsFuture,
};

function freezeConflict(error: ApiError): string {
  if (error.code === API_ERROR_CODES.freezeDaysExceeded) {
    const days = freezeDaysLeft(error.message);
    return days === null ? FREEZE_MESSAGES.daysExceeded : FREEZE_MESSAGES.daysLeft(days);
  }
  return FREEZE_CONFLICTS[error.code] ?? FREEZE_MESSAGES.generic;
}

/** El aviso del modal de congelar. */
export function freezeAlert(error: unknown): string {
  if (!isApiError(error)) return FREEZE_MESSAGES.generic;
  const connection = connectionMessage(error);
  if (connection) return connection;
  if (error.status === HTTP_CONFLICT) return freezeConflict(error);
  if (error.code === API_ERROR_CODES.memberInactive) return FREEZE_MESSAGES.memberInactive;
  return statusMessage(error, FREEZE_MESSAGES);
}

function cancelMessage(error: ApiError): string {
  if (error.code === API_ERROR_CODES.membershipAlreadyCancelled) return CANCEL_MESSAGES.alreadyCancelled;
  if (error.status === HTTP_UNPROCESSABLE && error.field === "reason") return CANCEL_MESSAGES.reasonInvalid;
  return statusMessage(error, CANCEL_MESSAGES);
}

/** El error de anular con el mensaje de la pantalla; conserva status, code y field. */
export function toCancelError(error: unknown): ApiError {
  return toFormError(error, cancelMessage, CANCEL_MESSAGES.generic);
}

// S3-F7 · US-093 (front): errores de la pestaña Membresías de la ficha (GET /members/{id}/memberships).
export const MEMBER_TAB_MESSAGES = {
  notFound: "No encontramos a este socio. Vuelve a la lista de socios.",
  forbidden: "No tienes permiso para ver las membresías. Si lo necesitas, pídeselo a un administrador.",
  generic: "No pudimos cargar las membresías de este socio. Intenta de nuevo.",
} as const;

/** El error de la pestaña como ApiError con el mensaje de la pantalla, o null. */
export function memberTabError(error: unknown): ApiError | null {
  return toScreenError(error, (e) => statusMessage(e, MEMBER_TAB_MESSAGES), MEMBER_TAB_MESSAGES.generic);
}
