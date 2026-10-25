// S3-F4 · US-095 y US-097 (front): esquemas de pagos.
// - RegisterPaymentFormValues: lo que se ve en el panel (el valor como "$ 60.000", la fecha del pago
//   como "AAAA-MM-DDTHH:mm" en hora de Bogotá). registerPaymentSchema(now) aplica las reglas de
//   PaymentIn en el cliente: membresía elegida, valor entero de 1 a 1.000.000.000 (D17), referencia
//   opcional con el patrón de comprobante solo con Nequi y Bre-B (S3-D50) y fecha y hora válidas que
//   no pasen de ahora más 5 minutos. El tope hacia atrás del coach (7 días por defecto, M-8) lo decide
//   el servidor (422 `paid_at_too_retroactive`).
// - toPaymentBody: el cuerpo de POST /memberships/{id}/payments, con `paid_at` en UTC y las
//   confirmaciones de S3-D41 en verdadero solo cuando se confirmaron.
// - voidPaymentSchema: el motivo de anular, recortado, de 1 a 500 caracteres (D17; el api recorta y
//   cuenta igual).
// - paymentOutSchema (el contrato de B3 a B5), paymentRowSchema, paymentDetailSchema y
//   paymentsSummarySchema (el contrato de B8, D26, con `backdated` de S3-D51): todos estrictos y con
//   enteros (S3-F6).
// Las reglas de entrada que comparte la venta con primer pago viven en shared/data (S3-D65) y aquí
// se reexportan.
import { z } from "zod";
import type { components } from "../../core/api/types";
import { bogotaInputToUtc, parseCop } from "../../core/i18n/format";
import { copAmount, copInt } from "../../shared/data/schemas/money";
import { paymentRowShape } from "../../shared/data/payments";
import {
  cleanReference,
  METHODS_WITH_REFERENCE,
  PAID_AT_FUTURE_TOLERANCE_MS,
  PAYMENT_METHOD_CODES,
  paymentMethodCodeSchema,
  referenceError,
  type PaymentInBody,
  type PaymentMethodCode,
} from "../../shared/data/schemas/payment";
import { PAYMENT_MESSAGES } from "./paymentErrors";
export {
  cleanReference,
  METHODS_WITH_REFERENCE,
  PAYMENT_METHOD_CODES,
  REFERENCE_MAX,
  REFERENCE_PATTERN,
  referenceError,
  SENSITIVE_TEXT_WARNING,
  type PaymentInBody,
  type PaymentMethodCode,
} from "../../shared/data/schemas/payment";
export { paymentMethodSchema, paymentMethodsSchema, type PaymentMethodView } from "../../shared/data/paymentMethods";

export type VoidPaymentBody = components["schemas"]["VoidPaymentIn"];

/** D17: el motivo de anular admite de 1 a 500 caracteres tras recortar. */
export const VOID_REASON_MAX = 500;

export interface RegisterPaymentFormValues {
  membershipId: string;
  method: PaymentMethodCode;
  /** Lo que se ve en el campo, por ejemplo "$ 60.000". */
  amount: string;
  reference: string;
  /** "AAAA-MM-DDTHH:mm" en hora de Bogotá. */
  paidAt: string;
}

export const EMPTY_REGISTER_FORM: RegisterPaymentFormValues = { membershipId: "", method: "cash", amount: "", reference: "", paidAt: "" };

export interface PaymentBodyOptions {
  /** El usuario confirmó un pago mayor al saldo (Q5, S3-D41). */
  confirmOverpayment?: boolean;
  /** El usuario confirmó que no es un duplicado (409 `payment_possible_duplicate`, S3-D41). */
  confirmDuplicate?: boolean;
}

type AddIssue = (path: keyof RegisterPaymentFormValues, message: string) => void;

function checkAmount(amount: string, add: AddIssue): void {
  if (amount.trim() === "") {
    add("amount", PAYMENT_MESSAGES.amountRequired);
    return;
  }
  const value = parseCop(amount);
  if (value === null) add("amount", PAYMENT_MESSAGES.amountInvalid);
  else if (!copInt.safeParse(value).success) add("amount", PAYMENT_MESSAGES.amountRange);
}

function checkPaidAt(paidAt: string, nowMs: number, add: AddIssue): void {
  if (paidAt.trim() === "") {
    add("paidAt", PAYMENT_MESSAGES.paidAtRequired);
    return;
  }
  const utc = bogotaInputToUtc(paidAt);
  if (utc === null) add("paidAt", PAYMENT_MESSAGES.paidAtInvalid);
  else if (Date.parse(utc) > nowMs + PAID_AT_FUTURE_TOLERANCE_MS) add("paidAt", PAYMENT_MESSAGES.paidAtFuture);
}

/** `nowMs` fijo solo en pruebas; sin él, la hora se lee al validar (el panel puede llevar rato abierto). */
export function registerPaymentSchema(nowMs?: number): z.ZodType<RegisterPaymentFormValues, z.ZodTypeDef, RegisterPaymentFormValues> {
  return z
    .object({
      membershipId: z.string(),
      method: z.enum(PAYMENT_METHOD_CODES, { errorMap: () => ({ message: PAYMENT_MESSAGES.methodRequired }) }),
      amount: z.string(),
      reference: z.string(),
      paidAt: z.string(),
    })
    .superRefine((values, ctx) => {
      const add: AddIssue = (path, message) => {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: [path], message });
      };
      if (values.membershipId === "") add("membershipId", PAYMENT_MESSAGES.membershipRequired);
      checkAmount(values.amount, add);
      if (METHODS_WITH_REFERENCE.has(values.method)) {
        const reference = referenceError(values.reference);
        if (reference) add("reference", reference);
      }
      checkPaidAt(values.paidAt, nowMs ?? Date.now(), add);
    });
}

/** Un formulario sin validar es un error de programación, no un 0 que el api rechace. */
function required<T>(value: T | null, field: keyof RegisterPaymentFormValues): T {
  if (value === null) throw new Error(`toPaymentBody: ${field} no pasó por registerPaymentSchema`);
  return value;
}

/** El cuerpo de POST /memberships/{id}/payments a partir de un formulario ya validado. */
export function toPaymentBody(values: RegisterPaymentFormValues, options: PaymentBodyOptions = {}): PaymentInBody {
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

const charCount = (value: string): number => Array.from(value).length;

export const voidPaymentSchema = z.object({
  reason: z
    .string()
    .trim()
    .refine((value) => value.length > 0, { message: "Escribe el motivo de la anulación." })
    .refine((value) => charCount(value) <= VOID_REASON_MAX, { message: `El motivo admite hasta ${String(VOID_REASON_MAX)} caracteres.` }),
});

// PaymentOut (B3 a B5): lo que devuelven registrar y anular.
export const paymentOutSchema = z
  .object({
    id: z.string().min(1),
    membership_id: z.string().min(1),
    member_id: z.string().min(1),
    amount_cop: copInt,
    method: paymentMethodCodeSchema,
    reference: z.string().nullable(),
    paid_at: z.string(),
    registered_by: z.string().min(1),
    voided: z.boolean(),
    voided_at: z.string().nullable(),
    voided_by: z.string().nullable(),
    void_reason: z.string().nullable(),
    created_at: z.string(),
  })
  .strict();
export type PaymentOutView = z.infer<typeof paymentOutSchema>;

// PaymentRow y PaymentDetail (contrato de B8, D26). Las fechas de la membresía son civiles
// ("AAAA-MM-DD"); `registered_by_name` y `voided_by_name` son el correo parcial ("l•••@dominio",
// S3-D57) y llegan en null si la cuenta ya no existe.
// S3-F7: la fila (PaymentRow) vive en shared/data/payments.ts (la pide useMemberPayments); aquí se
// reexporta y el detalle la extiende.
export { paymentRowSchema, paymentsPageSchema, type PaymentRowView } from "../../shared/data/payments";

export const paymentDetailSchema = z
  .object({
    ...paymentRowShape,
    voided_by: z.string().nullable(),
    voided_by_name: z.string().nullable(),
    voided_at: z.string().nullable(),
    created_at: z.string(),
  })
  .strict();
export type PaymentDetailView = z.infer<typeof paymentDetailSchema>;

// PaymentsSummary (B8, D23): el mes en Bogotá, lo cobrado por medio (solo pagos vigentes) y los conteos.
// Revisión S3-F6 (M4): las claves de `by_method` son los medios de PAYMENT_METHOD_CODES; `satisfies`
// hace que un medio nuevo en el contrato rompa la compilación aquí y no en la pantalla.
const BY_METHOD_SHAPE = { cash: copAmount, nequi: copAmount, breb: copAmount } satisfies Record<PaymentMethodCode, typeof copAmount>;
export const paymentsSummarySchema = z
  .object({
    month: z.string(),
    total_cop: copAmount,
    payments_count: z.number().int().nonnegative(),
    voided_count: z.number().int().nonnegative(),
    by_method: z.object(BY_METHOD_SHAPE).strict(),
  })
  .strict();
export type PaymentsSummaryView = z.infer<typeof paymentsSummarySchema>;
