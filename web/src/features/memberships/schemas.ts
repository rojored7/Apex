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
// - Fase 4 del Sprint 3 (M2): las reglas del pago y su cuerpo son checkPaymentFields y
//   buildPaymentBody de shared/data/schemas/payment.ts (las mismas del panel de pagos) con los textos
//   de la venta.
// - membershipOutSchema, sellMembershipOutSchema y renewalPreviewSchema: el contrato de B1 a B6,
//   estrictos y con enteros (una forma inesperada es `invalid_response`).
import { z } from "zod";
import type { components } from "../../core/api/types";
import { addDaysCivil } from "../../core/i18n/format";
import { membershipOutShape } from "../../shared/data/memberships";
import { copAmount } from "../../shared/data/schemas/money";
import { buildPaymentBody, checkPaymentFields, PAYMENT_METHOD_CODES, type PaymentMethodCode } from "../../shared/data/schemas/payment";
import { FREEZE_FORM_MESSAGES, SELL_MESSAGES } from "./membershipErrors";
import { CUSTOM_ISSUE } from "../../shared/lib/zodIssues";

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


/** `nowMs` fijo solo en pruebas; sin él, la hora se lee al validar (la página puede llevar rato abierta). */
export function sellMembershipSchema(today: string, nowMs?: number): z.ZodType<SellFormValues, SellFormValues> {
  return z
    .object({
      memberId: z.string(),
      planId: z.string(),
      renew: z.boolean(),
      startDate: z.string(),
      withPayment: z.boolean(),
      method: z.enum(PAYMENT_METHOD_CODES, { error: SELL_MESSAGES.methodRequired }),
      amount: z.string(),
      reference: z.string(),
      paidAt: z.string(),
    })
    .superRefine((values, ctx) => {
      const add: AddIssue = (path, message) => {
        ctx.addIssue({ code: CUSTOM_ISSUE, path: [path], message });
      };
      if (values.memberId === "") add("memberId", SELL_MESSAGES.memberRequired);
      if (values.planId === "") add("planId", SELL_MESSAGES.planRequired);
      if (!values.renew) checkStartDate(values.startDate, today, add);
      if (values.withPayment) checkPaymentFields(values, nowMs ?? Date.now(), SELL_MESSAGES, add);
    });
}

/** El primer pago: `confirm_duplicate` siempre falso (la venta no revisa duplicados, S3-D41). */
function toFirstPayment(values: SellFormValues, options: SellBodyOptions): NonNullable<SellMembershipBody["first_payment"]> {
  return buildPaymentBody(values, { confirmOverpayment: options.confirmOverpayment === true, confirmDuplicate: false }, "toSellBody");
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

// S3-F7: MembershipOut vive en shared/data/memberships.ts (lo pide useMemberMemberships); aquí se
// reexporta y la venta lo extiende con el primer pago.
export { membershipOutSchema, type MembershipOutView } from "../../shared/data/memberships";

export const sellMembershipOutSchema = z.object({ ...membershipOutShape, first_payment_id: z.string().nullable() }).strict();
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

// S3-F5 · US-089 y US-090 (front): formularios de congelar y anular.
// - freezeFormSchema: las dos fechas de FreezeIn ("AAAA-MM-DD" reales); "Hasta" no puede ser
//   anterior a "Desde" (el api daría 422 `validation_error` en `frozen_to`). Los límites (días,
//   veces, retroactividad, vigencia) los decide el servidor con la política de Configuración (D14).
// - cancelMembershipSchema: el motivo de CancelMembershipIn, de 5 a 500 caracteres tras recortar
//   (D17, `normalize_cancel_reason`); cuenta caracteres, no unidades UTF-16.
export interface FreezeFormValues {
  frozenFrom: string;
  frozenTo: string;
}

export type FreezeBody = components["schemas"]["FreezeIn"];

/** ¿Es una fecha civil real "AAAA-MM-DD"? */
const isCivilDate = (value: string): boolean => addDaysCivil(value, 0) === value;

const freezeDate = (required: string, invalid: string) =>
  z
    .string()
    .trim()
    .min(1, required)
    .refine(isCivilDate, invalid);

export const freezeFormSchema = z
  .object({
    frozenFrom: freezeDate(FREEZE_FORM_MESSAGES.fromRequired, FREEZE_FORM_MESSAGES.fromInvalid),
    frozenTo: freezeDate(FREEZE_FORM_MESSAGES.toRequired, FREEZE_FORM_MESSAGES.toInvalid),
  })
  // "AAAA-MM-DD" se compara bien como texto.
  .refine((values) => values.frozenTo >= values.frozenFrom, { path: ["frozenTo"], error: FREEZE_FORM_MESSAGES.inverted });

export function toFreezeBody(values: FreezeFormValues): FreezeBody {
  return { frozen_from: values.frozenFrom.trim(), frozen_to: values.frozenTo.trim() };
}

export const CANCEL_REASON_MIN = 5;
export const CANCEL_REASON_MAX = 500;

export const cancelMembershipSchema = z.object({
  reason: z
    .string()
    .trim()
    .refine((value) => {
      const length = Array.from(value).length;
      return length >= CANCEL_REASON_MIN && length <= CANCEL_REASON_MAX;
    }),
});
export type CancelMembershipBody = components["schemas"]["CancelMembershipIn"];
