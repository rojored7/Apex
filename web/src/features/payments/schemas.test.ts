// S3-F4 · US-095 y US-097 (front): esquemas de pagos. Montos enteros (D17), referencia con el patrón
// de comprobante (S3-D50), motivo de anulación recortado de 1 a 500 (D17), fila con `backdated`
// (S3-D51) y el cuerpo de POST /memberships/{id}/payments con `paid_at` en UTC.
import { paymentDetail, paymentOut, paymentRow } from "../../test/payments";
import { PAYMENT_MESSAGES } from "./paymentErrors";
import {
  EMPTY_REGISTER_FORM,
  paymentDetailSchema,
  paymentOutSchema,
  paymentRowSchema,
  registerPaymentSchema,
  toPaymentBody,
  VOID_REASON_MAX,
  voidPaymentSchema,
  type RegisterPaymentFormValues,
} from "./schemas";

/** 28 oct 2026, 10:00 a. m. en Bogotá. */
const NOW = Date.parse("2026-10-28T15:00:00Z");
const MEMBERSHIP = "66666666-6666-4666-8666-666666666666";

const valid = (overrides: Partial<RegisterPaymentFormValues> = {}): RegisterPaymentFormValues => ({
  ...EMPTY_REGISTER_FORM,
  membershipId: MEMBERSHIP,
  method: "cash",
  amount: "$ 60.000",
  reference: "",
  paidAt: "2026-10-28T09:30",
  ...overrides,
});

function issues(values: RegisterPaymentFormValues): Record<string, string> {
  const result = registerPaymentSchema(NOW).safeParse(values);
  if (result.success) return {};
  return Object.fromEntries(result.error.issues.map((issue) => [issue.path.join("."), issue.message]));
}

describe("registerPaymentSchema", () => {
  it("acepta un pago completo y uno sin referencia", () => {
    expect(issues(valid())).toEqual({});
    expect(issues(valid({ method: "nequi", reference: "" }))).toEqual({});
    expect(issues(valid({ method: "breb", reference: "BRB-99812" }))).toEqual({});
  });

  it("exige la membresía", () => {
    expect(issues(valid({ membershipId: "" }))).toEqual({ membershipId: PAYMENT_MESSAGES.membershipRequired });
  });

  it.each([
    ["", PAYMENT_MESSAGES.amountRequired],
    ["120000.50", PAYMENT_MESSAGES.amountInvalid],
    ["12,5", PAYMENT_MESSAGES.amountInvalid],
    ["-100", PAYMENT_MESSAGES.amountInvalid],
    ["0", PAYMENT_MESSAGES.amountRange],
    ["$ 1.000.000.001", PAYMENT_MESSAGES.amountRange],
  ])("el valor %j da «%s»: montos enteros de 1 a 1.000.000.000", (amount, message) => {
    expect(issues(valid({ amount }))).toEqual({ amount: message });
  });

  it("la referencia sigue el patrón de comprobante solo en Nequi y Bre-B", () => {
    expect(issues(valid({ method: "nequi", reference: "laura@correo.com" }))).toEqual({ reference: expect.stringContaining("letras, números") as string });
    expect(issues(valid({ method: "nequi", reference: "A".repeat(65) }))).toEqual({ reference: expect.stringContaining("64") as string });
    // En efectivo la referencia no se muestra ni se valida (y no se envía).
    expect(issues(valid({ method: "cash", reference: "laura@correo.com" }))).toEqual({});
  });

  it.each([
    ["", PAYMENT_MESSAGES.paidAtRequired],
    ["2026-02-30T10:00", PAYMENT_MESSAGES.paidAtInvalid],
    ["28/10/2026", PAYMENT_MESSAGES.paidAtInvalid],
    ["2026-10-28T10:06", PAYMENT_MESSAGES.paidAtFuture],
  ])("la fecha %j da «%s»", (paidAt, message) => {
    expect(issues(valid({ paidAt }))).toEqual({ paidAt: message });
  });

  it("hasta 5 minutos en el futuro se acepta (tolerancia del api)", () => {
    expect(issues(valid({ paidAt: "2026-10-28T10:05" }))).toEqual({});
  });
});

describe("toPaymentBody", () => {
  it("arma PaymentIn con el monto entero, paid_at en UTC y sin confirmaciones", () => {
    expect(toPaymentBody(valid())).toEqual({ amount_cop: 60_000, method: "cash", paid_at: "2026-10-28T14:30:00.000Z", confirm_overpayment: false, confirm_duplicate: false });
  });

  it("la referencia va recortada solo con Nequi y Bre-B; vacía no viaja", () => {
    expect(toPaymentBody(valid({ method: "nequi", reference: "  M12345678 " }))).toMatchObject({ method: "nequi", reference: "M12345678" });
    expect(toPaymentBody(valid({ method: "nequi", reference: "   " }))).not.toHaveProperty("reference");
    expect(toPaymentBody(valid({ method: "cash", reference: "M1" }))).not.toHaveProperty("reference");
  });

  it("las confirmaciones solo viajan en verdadero cuando se confirmaron (S3-D41)", () => {
    expect(toPaymentBody(valid(), { confirmOverpayment: true })).toMatchObject({ confirm_overpayment: true, confirm_duplicate: false });
    expect(toPaymentBody(valid(), { confirmDuplicate: true })).toMatchObject({ confirm_overpayment: false, confirm_duplicate: true });
  });

  it("un formulario sin validar es un error de programación, no un 0 que el api rechace", () => {
    expect(() => toPaymentBody(valid({ amount: "abc" }))).toThrow(/amount/);
    expect(() => toPaymentBody(valid({ paidAt: "" }))).toThrow(/paidAt/);
  });
});

describe("voidPaymentSchema", () => {
  it("recorta el motivo y acepta de 1 a 500 caracteres", () => {
    expect(voidPaymentSchema.parse({ reason: "  Pago duplicado  " })).toEqual({ reason: "Pago duplicado" });
    expect(voidPaymentSchema.safeParse({ reason: "x" }).success).toBe(true);
    expect(voidPaymentSchema.safeParse({ reason: "a".repeat(VOID_REASON_MAX) }).success).toBe(true);
    expect(VOID_REASON_MAX).toBe(500);
  });

  it.each([
    ["vacío", ""],
    ["solo espacios", "   "],
    ["más de 500", "a".repeat(501)],
  ])("un motivo %s no pasa", (_case, reason) => {
    expect(voidPaymentSchema.safeParse({ reason }).success).toBe(false);
  });

  it("cuenta caracteres, no unidades UTF-16: 500 emojis caben", () => {
    expect(voidPaymentSchema.safeParse({ reason: "😀".repeat(500) }).success).toBe(true);
  });
});

describe("respuestas", () => {
  it("paymentOutSchema es estricto y con enteros", () => {
    expect(paymentOutSchema.safeParse(paymentOut()).success).toBe(true);
    expect(paymentOutSchema.safeParse({ ...paymentOut(), amount_cop: 1.5 }).success).toBe(false);
    expect(paymentOutSchema.safeParse({ ...paymentOut(), extra: 1 }).success).toBe(false);
  });

  it("paymentRowSchema lleva `backdated` (S3-D51) y montos enteros", () => {
    expect(paymentRowSchema.parse(paymentRow({ backdated: true })).backdated).toBe(true);
    const withoutBackdated = Object.fromEntries(Object.entries(paymentRow()).filter(([key]) => key !== "backdated"));
    expect(paymentRowSchema.safeParse(withoutBackdated).success).toBe(false);
    expect(paymentRowSchema.safeParse(paymentRow({ amount_cop: 10.5 })).success).toBe(false);
    expect(paymentRowSchema.safeParse(paymentRow({ method: "card" as never })).success).toBe(false);
  });

  it("paymentDetailSchema suma quién anuló, cuándo y la creación", () => {
    const parsed = paymentDetailSchema.parse(paymentDetail({ voided: true, void_reason: "Duplicado", voided_by: "u", voided_by_name: "a•••@apex.test", voided_at: "2026-10-21T15:00:00Z" }));

    expect(parsed).toMatchObject({ voided: true, void_reason: "Duplicado", voided_by_name: "a•••@apex.test", created_at: "2026-10-20T19:10:00Z" });
  });
});
