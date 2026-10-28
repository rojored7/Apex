// @vitest-environment node
// Fase 4 del Sprint 3 (M2): las reglas de un pago y su cuerpo, compartidas por la venta con primer
// pago y el panel de pagos; cada pantalla pone sus textos.
import { buildPaymentBody, checkPaymentFields, type PaymentField, type PaymentFieldMessages, type PaymentFieldValues } from "./payment";

const MESSAGES: PaymentFieldMessages = {
  amountRequired: "valor vacío",
  amountInvalid: "valor inválido",
  amountRange: "valor fuera de rango",
  paidAtRequired: "fecha vacía",
  paidAtInvalid: "fecha inválida",
  paidAtFuture: "fecha futura",
};

const NOW = Date.parse("2026-10-28T15:00:00Z");
const VALID: PaymentFieldValues = { method: "nequi", amount: "$ 60.000", reference: " NQ-123 ", paidAt: "2026-10-28T09:30" };

function issues(values: Partial<PaymentFieldValues>): [PaymentField, string][] {
  const found: [PaymentField, string][] = [];
  checkPaymentFields({ ...VALID, ...values }, NOW, MESSAGES, (path, message) => {
    found.push([path, message]);
  });
  return found;
}

describe("checkPaymentFields", () => {
  it("un pago válido no tiene errores", () => {
    expect(issues({})).toEqual([]);
  });

  it.each([
    [{ amount: " " }, [["amount", "valor vacío"]]],
    [{ amount: "60.000,50" }, [["amount", "valor inválido"]]],
    [{ amount: "$ 0" }, [["amount", "valor fuera de rango"]]],
    [{ amount: "$ 1.000.000.001" }, [["amount", "valor fuera de rango"]]],
    [{ paidAt: "" }, [["paidAt", "fecha vacía"]]],
    [{ paidAt: "28/10/2026" }, [["paidAt", "fecha inválida"]]],
    [{ paidAt: "2026-10-28T10:06" }, [["paidAt", "fecha futura"]]],
    [{ reference: "correo@x.co" }, [["reference", "Escribe solo el número de la transacción: letras, números, espacios y . _ / # -."]]],
  ])("%j → %j", (values, expected) => {
    expect(issues(values)).toEqual(expected);
  });

  it("en efectivo la referencia no se revisa", () => {
    expect(issues({ method: "cash", reference: "correo@x.co" })).toEqual([]);
  });

  it("5 minutos hacia el futuro todavía sirven (tolerancia del api)", () => {
    expect(issues({ paidAt: "2026-10-28T10:05" })).toEqual([]);
  });
});

describe("buildPaymentBody", () => {
  it("arma PaymentIn con paid_at en UTC, la referencia recortada y las confirmaciones", () => {
    expect(buildPaymentBody(VALID, { confirmOverpayment: true }, "prueba")).toEqual({
      amount_cop: 60_000,
      method: "nequi",
      reference: "NQ-123",
      paid_at: "2026-10-28T14:30:00.000Z",
      confirm_overpayment: true,
      confirm_duplicate: false,
    });
  });

  it("en efectivo o sin referencia no envía `reference`", () => {
    expect(buildPaymentBody({ ...VALID, method: "cash" }, {}, "prueba")).not.toHaveProperty("reference");
    expect(buildPaymentBody({ ...VALID, reference: "  " }, { confirmDuplicate: true }, "prueba")).toMatchObject({ confirm_duplicate: true, confirm_overpayment: false });
  });

  it("un formulario sin validar es un error de programación que nombra al llamador y el campo", () => {
    expect(() => buildPaymentBody({ ...VALID, amount: "abc" }, {}, "toSellBody")).toThrow(/toSellBody: amount/);
    expect(() => buildPaymentBody({ ...VALID, paidAt: "x" }, {}, "toPaymentBody")).toThrow(/toPaymentBody: paidAt/);
  });
});
