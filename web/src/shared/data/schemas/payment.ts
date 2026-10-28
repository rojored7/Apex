// S3-F3 (S3-D65): reglas de entrada de un pago que comparten la venta con primer pago
// (features/memberships) y el registro de pagos (features/payments, S3-F4). Ninguna feature
// importa de otra: lo común vive aquí.
// - Medios fijos (D24): cash, nequi y breb; las etiquetas salen de GET /payments/methods.
// - Referencia (D17, S3-D50, M-7): opcional, recortada, de 1 a 64 caracteres y con el patrón de
//   comprobante del api (`REFERENCE_PATTERN` de payments/rules.py): letras, números, espacio y
//   . _ / # -, empezando por letra o número. Así no cabe un correo ni un texto libre.
import { z } from "zod";
import type { components } from "../../../core/api/types";
import { bogotaInputToUtc, parseCop } from "../../../core/i18n/format";
import { copInt } from "./money";

export type PaymentInBody = components["schemas"]["PaymentIn"];
export type PaymentMethodCode = PaymentInBody["method"];

export const PAYMENT_METHOD_CODES = ["cash", "nequi", "breb"] as const satisfies readonly PaymentMethodCode[];

/** Medios en los que el diseño pide la referencia (Membresia_Vender.html: "Referencia (Nequi / Bre-B)"). */
export const METHODS_WITH_REFERENCE: ReadonlySet<PaymentMethodCode> = new Set<PaymentMethodCode>(["nequi", "breb"]);

export const REFERENCE_MAX = 64;
export const REFERENCE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9 ._/#-]{0,63}$/;

/** M-7 (S3-D50): aviso bajo la referencia y bajo cualquier motivo. */
export const SENSITIVE_TEXT_WARNING = "No escribas teléfonos, documentos ni datos de salud.";

export const REFERENCE_MESSAGES = {
  tooLong: `La referencia admite hasta ${String(REFERENCE_MAX)} caracteres.`,
  pattern: "Escribe solo el número de la transacción: letras, números, espacios y . _ / # -.",
} as const;

/** La referencia tal como se envía: recortada; vacía es `undefined`. */
export function cleanReference(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed === "" ? undefined : trimmed;
}

/** Mensaje de error de una referencia escrita en el formulario, o null si sirve (vacía sirve). */
export function referenceError(value: string): string | null {
  const reference = cleanReference(value);
  if (reference === undefined) return null;
  if (Array.from(reference).length > REFERENCE_MAX) return REFERENCE_MESSAGES.tooLong;
  return REFERENCE_PATTERN.test(reference) ? null : REFERENCE_MESSAGES.pattern;
}

export const paymentMethodCodeSchema = z.enum(PAYMENT_METHOD_CODES);

/**
 * Tolerancia de `paid_at` hacia el futuro (`PAID_AT_FUTURE_TOLERANCE` de payments/rules.py). S3-F4:
 * nace en features/memberships/schemas.ts (S3-F3) y se mueve aquí porque la usa también el panel de
 * pagos; memberships la reexporta.
 */
export const PAID_AT_FUTURE_TOLERANCE_MS = 5 * 60 * 1_000;

// Fase 4 del Sprint 3 (M2): la venta con primer pago (features/memberships) y el panel de pagos
// (features/payments) validaban y armaban el pago con dos copias que solo cambiaban los textos. Las
// reglas viven aquí y cada pantalla pasa sus mensajes:
// - checkPaymentFields: valor entero de 1 a 1.000.000.000 (D17), referencia con el patrón de
//   comprobante solo en Nequi y Bre-B (S3-D50) y fecha y hora válidas que no pasen de ahora más la
//   tolerancia del api. El tope hacia atrás lo decide el servidor (N-24, M-8).
// - buildPaymentBody: PaymentIn con `paid_at` en UTC y las confirmaciones de S3-D41 en verdadero solo
//   cuando se confirmaron.

/** Los campos del pago tal como se ven en el formulario. */
export interface PaymentFieldValues {
  method: PaymentMethodCode;
  /** Lo que se ve en el campo, por ejemplo "$ 60.000". */
  amount: string;
  reference: string;
  /** "AAAA-MM-DDTHH:mm" en hora de Bogotá. */
  paidAt: string;
}

export type PaymentField = "amount" | "reference" | "paidAt";

/** Los textos de cada pantalla para los errores del pago (la referencia usa REFERENCE_MESSAGES). */
export interface PaymentFieldMessages {
  amountRequired: string;
  amountInvalid: string;
  amountRange: string;
  paidAtRequired: string;
  paidAtInvalid: string;
  paidAtFuture: string;
}

export interface PaymentBodyOptions {
  /** El usuario confirmó un pago mayor al saldo (Q5, S3-D41). */
  confirmOverpayment?: boolean;
  /** El usuario confirmó que no es un duplicado (409 `payment_possible_duplicate`, S3-D41). */
  confirmDuplicate?: boolean;
}

type AddPaymentIssue = (path: PaymentField, message: string) => void;

function amountError(amount: string, messages: PaymentFieldMessages): string | null {
  if (amount.trim() === "") return messages.amountRequired;
  const value = parseCop(amount);
  if (value === null) return messages.amountInvalid;
  return copInt.safeParse(value).success ? null : messages.amountRange;
}

function paidAtError(paidAt: string, nowMs: number, messages: PaymentFieldMessages): string | null {
  if (paidAt.trim() === "") return messages.paidAtRequired;
  const utc = bogotaInputToUtc(paidAt);
  if (utc === null) return messages.paidAtInvalid;
  return Date.parse(utc) > nowMs + PAID_AT_FUTURE_TOLERANCE_MS ? messages.paidAtFuture : null;
}

/** Revisa valor, referencia y fecha del pago; cada error va con `add` bajo su campo. */
export function checkPaymentFields(values: PaymentFieldValues, nowMs: number, messages: PaymentFieldMessages, add: AddPaymentIssue): void {
  const amount = amountError(values.amount, messages);
  if (amount) add("amount", amount);
  if (METHODS_WITH_REFERENCE.has(values.method)) {
    const reference = referenceError(values.reference);
    if (reference) add("reference", reference);
  }
  const paidAt = paidAtError(values.paidAt, nowMs, messages);
  if (paidAt) add("paidAt", paidAt);
}

/** PaymentIn a partir de campos ya validados; `caller` nombra a quien lo pidió en el error. */
export function buildPaymentBody(values: PaymentFieldValues, options: PaymentBodyOptions, caller: string): PaymentInBody {
  // Un formulario sin validar es un error de programación, no un 0 que el api rechace.
  const required = <T>(value: T | null, field: PaymentField): T => {
    if (value === null) throw new Error(`${caller}: ${field} no pasó por la validación del formulario`);
    return value;
  };
  const reference = METHODS_WITH_REFERENCE.has(values.method) ? cleanReference(values.reference) : undefined;
  return {
    amount_cop: required(parseCop(values.amount), "amount"),
    method: values.method,
    ...(reference ? { reference } : {}),
    paid_at: required(bogotaInputToUtc(values.paidAt), "paidAt"),
    confirm_overpayment: options.confirmOverpayment === true,
    confirm_duplicate: options.confirmDuplicate === true,
  };
}
