// S3-F3 · US-084, US-085 y US-088 (front): formulario de la venta y respuestas de membresías.
// - sellMembershipSchema(today, now): socio y plan obligatorios; inicio real y a no más de 366 días
//   (M-4) salvo al renovar (lo calcula el servidor, Q1); con pago, valor entero de 1 a
//   1.000.000.000 (D17), referencia opcional de hasta 64 con el patrón de comprobante (S3-D50) y
//   fecha y hora válidas que no estén en el futuro.
// - toSellBody: con `renew` no envía `start_date`; el pago va en UTC y `confirm_overpayment` solo es
//   verdadero cuando se pide (S3-D41).
// - membershipOutSchema y sellMembershipOutSchema son estrictos y exigen enteros.
import { membershipOut, sellMembershipOut } from "../../test/memberships";
import { PLANS } from "../../test/plans";
import {
  EMPTY_SELL_FORM,
  membershipOutSchema,
  renewalPreviewSchema,
  sellMembershipOutSchema,
  sellMembershipSchema,
  toSellBody,
  type SellFormValues,
} from "./schemas";
import { SELL_MESSAGES } from "./membershipErrors";

const TODAY = "2026-10-28";
const NOW = Date.parse("2026-10-28T15:00:00Z");
const MEMBER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

const valid: SellFormValues = {
  memberId: MEMBER_ID,
  planId: PLANS.mensual.id,
  renew: false,
  startDate: TODAY,
  withPayment: true,
  method: "cash",
  amount: "$ 120.000",
  reference: "",
  paidAt: "2026-10-28T10:00",
};

function errorsOf(values: SellFormValues): Record<string, string> {
  const result = sellMembershipSchema(TODAY, NOW).safeParse(values);
  if (result.success) return {};
  return Object.fromEntries(result.error.issues.map((issue) => [issue.path.join("."), issue.message]));
}

describe("sellMembershipSchema", () => {
  it("acepta una venta completa con pago", () => {
    expect(errorsOf(valid)).toEqual({});
  });

  it("el formulario vacío pide socio y plan, con mensajes que dicen qué hacer", () => {
    const errors = errorsOf({ ...EMPTY_SELL_FORM, startDate: TODAY, paidAt: "2026-10-28T10:00" });

    expect(errors.memberId).toBe(SELL_MESSAGES.memberRequired);
    expect(errors.planId).toBe(SELL_MESSAGES.planRequired);
    expect(errors.memberId).toBe("Elige el socio al que le vendes la membresía.");
  });

  it.each([
    ["", SELL_MESSAGES.startDateRequired],
    ["2026-02-30", SELL_MESSAGES.startDateInvalid],
    ["28/10/2026", SELL_MESSAGES.startDateInvalid],
    ["2027-10-30", SELL_MESSAGES.startDateTooFar],
  ])("inicio %j da %j", (startDate, message) => {
    expect(errorsOf({ ...valid, startDate }).startDate).toBe(message);
  });

  it("el inicio puede ser hasta 366 días después de hoy y una fecha pasada la decide el servidor (N-24)", () => {
    expect(errorsOf({ ...valid, startDate: "2027-10-29" })).toEqual({});
    expect(errorsOf({ ...valid, startDate: "2026-09-01" })).toEqual({});
  });

  it("al renovar el inicio no se valida: lo calcula el servidor (Q1)", () => {
    expect(errorsOf({ ...valid, renew: true, startDate: "" })).toEqual({});
  });

  it("sin pago no se validan valor, referencia ni fecha del pago", () => {
    expect(errorsOf({ ...valid, withPayment: false, amount: "", reference: "laura@correo.com", paidAt: "" })).toEqual({});
  });

  it.each([
    ["", SELL_MESSAGES.amountRequired],
    ["120000,50", SELL_MESSAGES.amountInvalid],
    ["1200.5", SELL_MESSAGES.amountInvalid],
    ["-5", SELL_MESSAGES.amountInvalid],
    ["0", SELL_MESSAGES.amountRange],
    ["$ 1.000.000.001", SELL_MESSAGES.amountRange],
  ])("valor %j da %j", (amount, message) => {
    expect(errorsOf({ ...valid, amount }).amount).toBe(message);
  });

  it("acepta el valor con o sin formato", () => {
    expect(errorsOf({ ...valid, amount: "60000" })).toEqual({});
    expect(errorsOf({ ...valid, amount: "$ 1.000.000.000" })).toEqual({});
  });

  it.each([
    ["a".repeat(65), "La referencia admite hasta 64 caracteres."],
    ["laura@correo.com", "Escribe solo el número de la transacción: letras, números, espacios y . _ / # -."],
    ["-123", "Escribe solo el número de la transacción: letras, números, espacios y . _ / # -."],
  ])("referencia %j da su error (S3-D50)", (reference, message) => {
    expect(errorsOf({ ...valid, method: "nequi", reference }).reference).toBe(message);
  });

  it("la referencia es opcional y se acepta con espacios alrededor y el patrón de comprobante", () => {
    expect(errorsOf({ ...valid, method: "nequi", reference: "" })).toEqual({});
    expect(errorsOf({ ...valid, method: "breb", reference: "  M-123/45 #2  " })).toEqual({});
    expect(errorsOf({ ...valid, method: "nequi", reference: "a".repeat(64) })).toEqual({});
  });

  it.each([
    ["", SELL_MESSAGES.paidAtRequired],
    ["ayer", SELL_MESSAGES.paidAtInvalid],
    ["2026-10-28T10:06", SELL_MESSAGES.paidAtFuture],
  ])("fecha del pago %j da %j", (paidAt, message) => {
    expect(errorsOf({ ...valid, paidAt }).paidAt).toBe(message);
  });

  it("la fecha del pago acepta hasta 5 minutos de adelanto (tolerancia del api) y fechas pasadas", () => {
    expect(errorsOf({ ...valid, paidAt: "2026-10-28T10:05" })).toEqual({});
    expect(errorsOf({ ...valid, paidAt: "2026-10-20T08:00" })).toEqual({});
  });
});

describe("toSellBody", () => {
  it("venta con pago: enteros, fecha del pago en UTC y sin confirmaciones", () => {
    expect(toSellBody(valid)).toEqual({
      plan_id: PLANS.mensual.id,
      renew: false,
      start_date: TODAY,
      first_payment: { amount_cop: 120_000, method: "cash", paid_at: "2026-10-28T15:00:00.000Z", confirm_overpayment: false, confirm_duplicate: false },
    });
  });

  it("con renew: true no envía start_date (Q1, regla 9 de CLAUDE.md)", () => {
    const body = toSellBody({ ...valid, renew: true });

    expect(body.renew).toBe(true);
    expect(body).not.toHaveProperty("start_date");
  });

  it("sin pago no envía first_payment", () => {
    expect(toSellBody({ ...valid, withPayment: false })).toEqual({ plan_id: PLANS.mensual.id, renew: false, start_date: TODAY });
  });

  it("la referencia va recortada y vacía no viaja", () => {
    expect(toSellBody({ ...valid, method: "nequi", reference: "  123456  " }).first_payment?.reference).toBe("123456");
    expect(toSellBody({ ...valid, method: "nequi", reference: "   " }).first_payment).not.toHaveProperty("reference");
  });

  it("con efectivo la referencia escrita antes en Nequi no viaja", () => {
    expect(toSellBody({ ...valid, method: "cash", reference: "123456" }).first_payment).not.toHaveProperty("reference");
  });

  it("confirm_overpayment solo es verdadero cuando se pide (S3-D41)", () => {
    expect(toSellBody(valid, { confirmOverpayment: true }).first_payment?.confirm_overpayment).toBe(true);
    expect(toSellBody(valid, {}).first_payment?.confirm_overpayment).toBe(false);
  });

  it("un formulario sin validar es un error de programación, no un 0 que el api rechace", () => {
    expect(() => toSellBody({ ...valid, amount: "abc" })).toThrow(/amount/);
    expect(() => toSellBody({ ...valid, paidAt: "x" })).toThrow(/paidAt/);
  });
});

describe("respuestas de membresías (estrictas, con enteros)", () => {
  it("membershipOutSchema acepta MembershipOut y rechaza decimales, estados desconocidos y campos de más", () => {
    const row = membershipOut();

    expect(membershipOutSchema.safeParse(row).success).toBe(true);
    expect(membershipOutSchema.safeParse({ ...row, paid_cop: 1.5 }).success).toBe(false);
    expect(membershipOutSchema.safeParse({ ...row, agreed_price_cop: "120000" }).success).toBe(false);
    expect(membershipOutSchema.safeParse({ ...row, status: "paused" }).success).toBe(false);
    expect(membershipOutSchema.safeParse({ ...row, extra: true }).success).toBe(false);
  });

  it("acepta las congelaciones con días enteros", () => {
    const freeze = { id: "f1", frozen_from: "2026-11-01", frozen_to: "2026-11-05", days: 5, created_at: "2026-10-30T15:00:00Z" };

    expect(membershipOutSchema.safeParse(membershipOut({ freezes: [freeze] })).success).toBe(true);
    expect(membershipOutSchema.safeParse(membershipOut({ freezes: [{ ...freeze, days: 2.5 }] })).success).toBe(false);
  });

  it("sellMembershipOutSchema exige first_payment_id (o null) y es estricto", () => {
    expect(sellMembershipOutSchema.safeParse(sellMembershipOut()).success).toBe(true);
    expect(sellMembershipOutSchema.safeParse(sellMembershipOut({ first_payment_id: null })).success).toBe(true);
    expect(sellMembershipOutSchema.safeParse(membershipOut()).success).toBe(false);
    expect(sellMembershipOutSchema.safeParse({ ...sellMembershipOut(), extra: 1 }).success).toBe(false);
  });

  it("renewalPreviewSchema exige un precio entero y acepta un fin actual nulo", () => {
    const preview = { start_date: "2026-10-29", end_date: "2026-11-28", agreed_price_cop: 120_000, current_end_date: null };

    expect(renewalPreviewSchema.safeParse(preview).success).toBe(true);
    expect(renewalPreviewSchema.safeParse({ ...preview, agreed_price_cop: 1.5 }).success).toBe(false);
  });
});
