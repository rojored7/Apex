// S3-F3 · US-084, US-085 y US-088 (front): formulario de la venta y respuestas de membresías.
// - SellFormValues: lo que se ve en la pantalla (el valor como "$ 120.000", la fecha del pago como
//   "AAAA-MM-DDTHH:mm" en hora de Bogotá). sellMembershipSchema(today, now) aplica las reglas de
//   SellMembershipIn y PaymentIn en el cliente: socio y plan obligatorios; inicio real y a no más de
//   366 días de hoy (M-4, `MAX_START_AHEAD_DAYS`; el tope hacia atrás depende de Configuración y lo
//   decide el servidor, N-24); al renovar el inicio no se valida (lo calcula el servidor, Q1); con
//   pago, valor entero de 1 a 1.000.000.000 (D17), referencia opcional con el patrón de comprobante
//   (S3-D50) y fecha y hora válidas que no pasen de ahora más 5 minutos (tolerancia del api).
// - toSellBody: el cuerpo de POST /members/{id}/memberships. Con `renew` no va `start_date` (regla 9
//   de CLAUDE.md); el pago va con `paid_at` en UTC y `confirm_overpayment` solo cuando se confirmó
//   el sobrepago (S3-D41). `confirm_duplicate` siempre es falso: la venta no revisa duplicados.
// - membershipOutSchema, sellMembershipOutSchema y renewalPreviewSchema: el contrato de B1 a B6,
//   estrictos y con enteros (una forma inesperada es `invalid_response`).
import { z } from "zod";
import type { components } from "../../core/api/types";
import { addDaysCivil, bogotaInputToUtc, parseCop } from "../../core/i18n/format";
import { MEMBERSHIP_STATUSES } from "../../shared/data/memberships";
import { copAmount, copInt } from "../../shared/data/schemas/money";
import { cleanReference, METHODS_WITH_REFERENCE, PAID_AT_FUTURE_TOLERANCE_MS, PAYMENT_METHOD_CODES, referenceError, type PaymentMethodCode } from "../../shared/data/schemas/payment";
import { SELL_MESSAGES } from "./membershipErrors";

export type SellMembershipBody = components["schemas"]["SellMembershipIn"];

/** M-4 (S3-D47): el inicio no puede pasar de hoy más 366 días (`MAX_START_AHEAD_DAYS`). */
export const MAX_START_AHEAD_DAYS = 366;
/** Tolerancia de `paid_at` hacia el futuro (S3-F4: vive en shared/data/schemas/payment.ts). */
export { PAID_AT_FUTURE_TOLERANCE_MS } from "../../shared/data/schemas/payment";

export interface SellFormValues {
  memberId: string;
  planId: string;
  renew: boolean;
  /** "AAAA-MM-DD"; al renovar no se envía. */
  startDate: string;
  withPayment: boolean;
  method: PaymentMethodCode;
  /** Lo que se ve en el campo, por ejemplo "$ 120.000". */
  amount: string;
  reference: string;
  /** "AAAA-MM-DDTHH:mm" en hora de Bogotá. */
  paidAt: string;
}

export const EMPTY_SELL_FORM: SellFormValues = {
  memberId: "",
  planId: "",
  renew: false,
  startDate: "",
  withPayment: true,
  method: "cash",
  amount: "",
  reference: "",
  paidAt: "",
};

export interface SellBodyOptions {
  /** El usuario confirmó el sobrepago en el modal (S3-D41). */
  confirmOverpayment?: boolean;
}

const CIVIL_DATE = /^\d{4}-\d{2}-\d{2}$/;

type AddIssue = (path: keyof SellFormValues, message: string) => void;

function checkStartDate(startDate: string, today: string, add: AddIssue): void {
  if (startDate.trim() === "") {
    add("startDate", SELL_MESSAGES.startDateRequired);
    return;
  }
  if (!CIVIL_DATE.test(startDate) || addDaysCivil(startDate, 0) === null) {
    add("startDate", SELL_MESSAGES.startDateInvalid);
    return;
  }
  const latest = addDaysCivil(today, MAX_START_AHEAD_DAYS);
  if (latest !== null && startDate > latest) add("startDate", SELL_MESSAGES.startDateTooFar);
}

function checkAmount(amount: string, add: AddIssue): void {
  if (amount.trim() === "") {
    add("amount", SELL_MESSAGES.amountRequired);
    return;
  }
  const value = parseCop(amount);
  if (value === null) add("amount", SELL_MESSAGES.amountInvalid);
  else if (!copInt.safeParse(value).success) add("amount", SELL_MESSAGES.amountRange);
}

function checkPaidAt(paidAt: string, nowMs: number, add: AddIssue): void {
  if (paidAt.trim() === "") {
    add("paidAt", SELL_MESSAGES.paidAtRequired);
    return;
  }
  const utc = bogotaInputToUtc(paidAt);
  if (utc === null) add("paidAt", SELL_MESSAGES.paidAtInvalid);
  else if (Date.parse(utc) > nowMs + PAID_AT_FUTURE_TOLERANCE_MS) add("paidAt", SELL_MESSAGES.paidAtFuture);
}

function checkPayment(values: SellFormValues, nowMs: number, add: AddIssue): void {
  checkAmount(values.amount, add);
  if (METHODS_WITH_REFERENCE.has(values.method)) {
    const reference = referenceError(values.reference);
    if (reference) add("reference", reference);
  }
  checkPaidAt(values.paidAt, nowMs, add);
}

/** `nowMs` fijo solo en pruebas; sin él, la hora se lee al validar (la página puede llevar rato abierta). */
export function sellMembershipSchema(today: string, nowMs?: number): z.ZodType<SellFormValues, z.ZodTypeDef, SellFormValues> {
  return z
    .object({
      memberId: z.string(),
      planId: z.string(),
      renew: z.boolean(),
      startDate: z.string(),
      withPayment: z.boolean(),
      method: z.enum(PAYMENT_METHOD_CODES, { errorMap: () => ({ message: SELL_MESSAGES.methodRequired }) }),
      amount: z.string(),
      reference: z.string(),
      paidAt: z.string(),
    })
    .superRefine((values, ctx) => {
      const add: AddIssue = (path, message) => {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: [path], message });
      };
      if (values.memberId === "") add("memberId", SELL_MESSAGES.memberRequired);
      if (values.planId === "") add("planId", SELL_MESSAGES.planRequired);
      if (!values.renew) checkStartDate(values.startDate, today, add);
      if (values.withPayment) checkPayment(values, nowMs ?? Date.now(), add);
    });
}

/** Un formulario sin validar es un error de programación, no un 0 que el api rechace. */
function required<T>(value: T | null, field: keyof SellFormValues): T {
  if (value === null) throw new Error(`toSellBody: ${field} no pasó por sellMembershipSchema`);
  return value;
}

function toFirstPayment(values: SellFormValues, options: SellBodyOptions): NonNullable<SellMembershipBody["first_payment"]> {
  const reference = METHODS_WITH_REFERENCE.has(values.method) ? cleanReference(values.reference) : undefined;
  return {
    amount_cop: required(parseCop(values.amount), "amount"),
    method: values.method,
    ...(reference ? { reference } : {}),
    paid_at: required(bogotaInputToUtc(values.paidAt), "paidAt"),
    confirm_overpayment: options.confirmOverpayment === true,
    confirm_duplicate: false,
  };
}

/** El cuerpo de POST /members/{id}/memberships a partir de un formulario ya validado. */
export function toSellBody(values: SellFormValues, options: SellBodyOptions = {}): SellMembershipBody {
  return {
    plan_id: values.planId,
    renew: values.renew,
    ...(values.renew ? {} : { start_date: values.startDate }),
    ...(values.withPayment ? { first_payment: toFirstPayment(values, options) } : {}),
  };
}

// S3-F4: la lista de estados vive en shared/data/memberships.ts (la usa también el panel de pagos).
export { MEMBERSHIP_STATUSES, type MembershipStatus } from "../../shared/data/memberships";

const freezeOutSchema = z
  .object({
    id: z.string().min(1),
    frozen_from: z.string(),
    frozen_to: z.string(),
    days: z.number().int(),
    created_at: z.string(),
  })
  .strict();

const membershipShape = {
  id: z.string().min(1),
  member_id: z.string().min(1),
  member_name: z.string(),
  plan_id: z.string().min(1),
  plan_name: z.string(),
  status: z.enum(MEMBERSHIP_STATUSES),
  start_date: z.string(),
  end_date: z.string(),
  agreed_price_cop: copAmount,
  paid_cop: copAmount,
  classes_total: z.number().int().nullable(),
  classes_remaining: z.number().int().nullable(),
  cancel_reason: z.string().nullable(),
  cancelled_at: z.string().nullable(),
  freezes: z.array(freezeOutSchema),
  created_at: z.string(),
};

export const membershipOutSchema = z.object(membershipShape).strict();
export type MembershipOutView = z.infer<typeof membershipOutSchema>;

export const sellMembershipOutSchema = z.object({ ...membershipShape, first_payment_id: z.string().nullable() }).strict();
export type SellMembershipOutView = z.infer<typeof sellMembershipOutSchema>;

export const renewalPreviewSchema = z
  .object({
    start_date: z.string(),
    end_date: z.string(),
    agreed_price_cop: copAmount,
    current_end_date: z.string().nullable(),
  })
  .strict();
export type RenewalPreviewView = z.infer<typeof renewalPreviewSchema>;
