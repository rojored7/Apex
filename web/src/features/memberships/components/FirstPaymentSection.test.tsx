// S3-F3 · US-085 (front): sección "3 · Pago" de la venta, probada dentro de SellPage (el envío y
// el modal de sobrepago viven en la página).
// - Medios con la etiqueta de GET /payments/methods (D24); si no cargan, las de siempre.
// - Referencia solo con Nequi y Bre-B, opcional (DESIGN-GAP: el diseño no dice si es obligatoria),
//   con el aviso M-7 (S3-D50) y el patrón de comprobante.
// - Valor precargado con el precio y formateado al escribir; fecha y hora del pago en Bogotá,
//   enviada en UTC.
// - Sobrepago (Q5, H-1, S3-D41): un valor mayor al precio abre ConfirmModal "Este pago supera el
//   precio del plan en $ X" y solo se envía con `confirm_overpayment: true` al confirmar; un 409
//   `payment_exceeds_balance` inesperado (carrera) también abre el modal y reenvía.
// - Errores `first_payment.*` bajo su campo, con foco.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { apiError, pickMember, pickPlan, renderSell, SELL_NOW, sellBodies, sellKey, sellMembershipOut } from "../../../test/memberships";
import { PAYMENT_METHODS } from "../../../test/payments";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

const amountBox = () => screen.getByRole("textbox", { name: /^Valor recibido/ });
const paidAtBox = () => screen.getByLabelText(/^Fecha y hora del pago/);
const referenceBox = () => screen.queryByRole("textbox", { name: /^Referencia/ });
const submit = () => screen.getByRole("button", { name: "Vender y cobrar" });

type FirstPayment = Record<string, unknown>;
const firstPayments = (mock: Parameters<typeof sellBodies>[0]): FirstPayment[] => sellBodies(mock).map((b) => b.first_payment as FirstPayment);

async function ready(user: ReturnType<typeof renderSell>["user"], plan = "Mensual"): Promise<void> {
  await pickMember(user);
  await pickPlan(user, plan);
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: SELL_NOW });
  setViewportWidth(1440);
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("FirstPaymentSection · campos", () => {
  it("los medios llevan la etiqueta del api, en su orden, con Efectivo elegido", async () => {
    renderSell("/membresias/vender", { handlers: { "GET /payments/methods": { status: 200, body: { items: [PAYMENT_METHODS[0], { ...PAYMENT_METHODS[1], label: "Nequi del box" }, PAYMENT_METHODS[2]] } } } });

    const group = screen.getByRole("group", { name: "Medio de pago" });
    await within(group).findByRole("radio", { name: "Nequi del box" });
    expect(within(group).getAllByRole("radio").map((r) => r.getAttribute("value"))).toEqual(["cash", "nequi", "breb"]);
    expect(within(group).getByRole("radio", { name: "Efectivo" })).toBeChecked();
  });

  it("si los medios no cargan usa las etiquetas de siempre y lo avisa", async () => {
    renderSell("/membresias/vender", { handlers: { "GET /payments/methods": apiError(500, "internal_error") } });

    expect(await screen.findByText("No pudimos cargar los nombres de los medios de pago; se muestran los de siempre.")).toBeInTheDocument();
    const group = screen.getByRole("group", { name: "Medio de pago" });
    expect(within(group).getAllByRole("radio").map((r) => r.closest("label")?.textContent)).toEqual(["Efectivo", "Nequi", "Bre-B"]);
  });

  it("el valor se precarga con el precio del plan y sigue al plan mientras no se edite", async () => {
    const { user } = renderSell();
    await ready(user);
    expect(amountBox()).toHaveValue("$ 120.000");

    await pickPlan(user, "12 clases");
    expect(amountBox()).toHaveValue("$ 110.000");

    await user.clear(amountBox());
    await user.type(amountBox(), "50000");
    expect(amountBox()).toHaveValue("$ 50.000");
    await pickPlan(user, "Mensual");
    expect(amountBox()).toHaveValue("$ 50.000");
  });

  it("la referencia solo aparece con Nequi y Bre-B, es opcional y lleva el aviso M-7", async () => {
    const { user } = renderSell();
    await ready(user);
    expect(referenceBox()).not.toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Nequi" }));
    const reference = referenceBox();
    expect(reference).toBeInTheDocument();
    expect(reference).not.toHaveAttribute("aria-required");
    expect(reference).toHaveAccessibleDescription(/No escribas teléfonos, documentos ni datos de salud\./);
    expect(summaryLine()).toBe("$ 120.000 · Nequi");

    await user.click(screen.getByRole("radio", { name: "Bre-B" }));
    expect(referenceBox()).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Efectivo" }));
    expect(referenceBox()).not.toBeInTheDocument();
  });

  it("la fecha y hora del pago empieza en ahora (Bogotá)", () => {
    renderSell();

    expect(paidAtBox()).toHaveValue("2026-10-28T10:00");
  });

  it("no tiene violaciones de axe con Nequi elegido", async () => {
    const { user, container } = renderSell();
    await ready(user);
    await user.click(screen.getByRole("radio", { name: "Nequi" }));

    expect(await axe(container)).toHaveNoViolations();
  });
});

function summaryLine(): string {
  const aside = screen.getByRole("complementary", { name: "Resumen" });
  return within(aside).getByText("Pago", { selector: "dt" }).nextElementSibling?.textContent ?? "";
}

describe("FirstPaymentSection · envío", () => {
  it("con Nequi envía la referencia recortada; vacía no viaja", async () => {
    const { user, mock } = renderSell();
    await ready(user);
    await user.click(screen.getByRole("radio", { name: "Nequi" }));
    await user.type(referenceBox() as HTMLElement, "  M-123456  ");
    await user.click(submit());
    await screen.findByRole("region", { name: "Venta registrada" });

    expect(firstPayments(mock)[0]).toMatchObject({ method: "nequi", reference: "M-123456" });
  });

  it("una referencia que no es un comprobante va bajo su campo y no se envía", async () => {
    const { user, mock } = renderSell();
    await ready(user);
    await user.click(screen.getByRole("radio", { name: "Bre-B" }));
    await user.type(referenceBox() as HTMLElement, "laura@correo.com");
    await user.click(submit());

    expect(await screen.findByText("Escribe solo el número de la transacción: letras, números, espacios y . _ / # -.")).toBeInTheDocument();
    expect(mock.callsTo(sellKey())).toHaveLength(0);
  });

  it("la fecha y hora del pago se envía en UTC (Bogotá es UTC-5)", async () => {
    const { user, mock } = renderSell();
    await ready(user);
    fireEvent.change(paidAtBox(), { target: { value: "2026-10-27T19:30" } });
    await user.click(submit());
    await screen.findByRole("region", { name: "Venta registrada" });

    expect(firstPayments(mock)[0]?.paid_at).toBe("2026-10-28T00:30:00.000Z");
  });

  it("un valor vacío o con centavos no se envía y dice qué hacer", async () => {
    const { user, mock } = renderSell();
    await ready(user);
    await user.clear(amountBox());
    await user.click(submit());
    expect(await screen.findByText("Escribe el valor recibido.")).toBeInTheDocument();

    await user.type(amountBox(), "1200,50");
    await user.click(submit());
    expect(await screen.findByText("Escribe el valor en pesos enteros, sin centavos (por ejemplo $ 120.000).")).toBeInTheDocument();
    expect(mock.callsTo(sellKey())).toHaveLength(0);
  });
});

describe("FirstPaymentSection · sobrepago (Q5, H-1, S3-D41)", () => {
  it("un valor mayor al precio abre el modal y no envía nada hasta confirmar", async () => {
    const { user, mock } = renderSell();
    await ready(user);
    await user.clear(amountBox());
    await user.type(amountBox(), "150000");
    await user.click(submit());

    const dialog = await screen.findByRole("dialog", { name: "¿Registrar un pago mayor al precio?" });
    expect(dialog).toHaveTextContent("Este pago supera el precio del plan en $ 30.000. La diferencia no queda como saldo a favor.");
    expect(mock.callsTo(sellKey())).toHaveLength(0);

    await user.click(within(dialog).getByRole("button", { name: "Volver" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo(sellKey())).toHaveLength(0);
    expect(amountBox()).toHaveValue("$ 150.000");
  });

  it("al confirmar envía con confirm_overpayment: true", async () => {
    const { user, mock } = renderSell();
    await ready(user);
    await user.clear(amountBox());
    await user.type(amountBox(), "150000");
    await user.click(submit());
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Registrar pago" }));

    await screen.findByRole("region", { name: "Venta registrada" });
    expect(firstPayments(mock)).toEqual([expect.objectContaining({ amount_cop: 150_000, confirm_overpayment: true, confirm_duplicate: false })]);
  });

  it("un 409 payment_exceeds_balance inesperado también abre el modal y reenvía confirmado", async () => {
    let calls = 0;
    const { user, mock } = renderSell("/membresias/vender", {
      handlers: {
        [sellKey()]: (call) => {
          calls += 1;
          const confirmed = (call.body as { first_payment?: { confirm_overpayment?: boolean } }).first_payment?.confirm_overpayment === true;
          return calls === 1 && !confirmed
            ? apiError(409, "payment_exceeds_balance", { field: "first_payment.amount_cop" })
            : { status: 201, body: sellMembershipOut() };
        },
      },
    });
    await ready(user);
    await user.click(submit());

    const dialog = await screen.findByRole("dialog", { name: "¿Registrar un pago mayor al precio?" });
    expect(dialog).toHaveTextContent("Este pago supera el saldo de la membresía. La diferencia no queda como saldo a favor.");
    await user.click(within(dialog).getByRole("button", { name: "Registrar pago" }));

    await screen.findByRole("region", { name: "Venta registrada" });
    expect(firstPayments(mock).map((p) => p.confirm_overpayment)).toEqual([false, true]);
  });
});

describe("FirstPaymentSection · errores del pago", () => {
  it.each([
    [apiError(422, "paid_at_too_retroactive", { field: "first_payment.paid_at" }), "La fecha del pago es demasiado antigua para tu rol. Pídele a un administrador que lo registre."],
    [apiError(422, "validation_error", { field: "first_payment.paid_at" }), "El servidor no aceptó la fecha del pago. Revísala e intenta de nuevo."],
  ])("%j va bajo Fecha y hora del pago con foco", async (reply, message) => {
    const { user } = renderSell("/membresias/vender", { handlers: { [sellKey()]: reply } });
    await ready(user);
    await user.click(submit());

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(paidAtBox()).toHaveFocus();
  });

  it("422 de first_payment.amount_cop va bajo Valor recibido", async () => {
    const { user } = renderSell("/membresias/vender", { handlers: { [sellKey()]: apiError(422, "validation_error", { field: "first_payment.amount_cop" }) } });
    await ready(user);
    await user.click(submit());

    expect(await screen.findByText("El servidor no aceptó este valor. Revísalo e intenta de nuevo.")).toBeInTheDocument();
    expect(amountBox()).toHaveFocus();
  });

  it("422 de first_payment.reference va bajo Referencia", async () => {
    const { user } = renderSell("/membresias/vender", { handlers: { [sellKey()]: apiError(422, "validation_error", { field: "first_payment.reference" }) } });
    await ready(user);
    await user.click(screen.getByRole("radio", { name: "Nequi" }));
    await user.type(referenceBox() as HTMLElement, "123");
    await user.click(submit());

    expect(await screen.findByText("Escribe solo el número de la transacción: letras, números, espacios y . _ / # -.")).toBeInTheDocument();
  });
});


describe("revisión S3-F3", () => {
  it("MEDIUM 2: si el envío confirmado falla, el foco va al campo del error y no al botón", async () => {
    let calls = 0;
    const { user } = renderSell("/membresias/vender", {
      handlers: {
        [sellKey()]: () => {
          calls += 1;
          return apiError(422, "paid_at_too_retroactive", { field: "first_payment.paid_at" });
        },
      },
    });
    await ready(user);
    await user.clear(amountBox());
    await user.type(amountBox(), "150000");
    await user.click(submit());
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Registrar pago" }));

    expect(await screen.findByText("La fecha del pago es demasiado antigua para tu rol. Pídele a un administrador que lo registre.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(paidAtBox()).toHaveFocus();
    });
    expect(calls).toBe(1);
  });

  it("MEDIUM 2: un segundo 409 tras confirmar da un aviso general con foco", async () => {
    const { user } = renderSell("/membresias/vender", { handlers: { [sellKey()]: apiError(409, "payment_exceeds_balance", { field: "first_payment.amount_cop" }) } });
    await ready(user);
    await user.click(submit());
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Registrar pago" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No pudimos registrar la venta. Revisa los datos e intenta de nuevo.");
    await waitFor(() => {
      expect(alert).toHaveFocus();
    });
  });

  it("LOW 7: un valor borrado a mano no se vuelve a llenar al cambiar de plan", async () => {
    const { user } = renderSell();
    await ready(user);
    await user.clear(amountBox());
    await pickPlan(user, "12 clases");

    expect(amountBox()).toHaveValue("");
  });
});
