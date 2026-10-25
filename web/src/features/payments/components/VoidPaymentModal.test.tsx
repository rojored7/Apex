// S3-F4 · US-097 (front): anular un pago (Pagos.html, "Anular pago"; DESIGN.md: anular es un
// modal con motivo). Solo admin (`payments.void`); motivo obligatorio de 1 a 500 con el texto "El
// pago no se borra: queda anulado con este motivo" y el aviso M-7; 409 `payment_already_voided`
// dice "Otra persona lo anuló antes" y refresca; tras anular ofrece "Registrar pago nuevo", que abre
// el panel (?pago=<membresía>) con el valor y el medio precargados. S3-D52: la caché de mutaciones
// no conserva el motivo.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { axe } from "vitest-axe";
import { RoleProvider, type Role } from "../../../core/auth";
import { apiError } from "../../../test/memberships";
import { voidKey } from "../../../test/paymentPanel";
import { PAYMENT_ID, paymentOut } from "../../../test/payments";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { VOID_MESSAGES } from "../paymentErrors";
import { VoidPaymentModal, type VoidTarget } from "./VoidPaymentModal";

const MEMBERSHIP = "66666666-6666-4666-8666-666666666666";
const TARGET: VoidTarget = { id: PAYMENT_ID, membership_id: MEMBERSHIP, amount_cop: 120_000, method: "nequi" };

function Screen({ onClose }: { onClose: () => void }) {
  const [payment, setPayment] = useState<VoidTarget | null>(TARGET);
  return (
    <main>
      <h1>Pagos</h1>
      <VoidPaymentModal
        payment={payment}
        onClose={() => {
          setPayment(null);
          onClose();
        }}
      />
    </main>
  );
}

function renderModal(role: Role, handlers: Record<string, MockHandler> = {}, queryClient: QueryClient = testQueryClient()) {
  const mock = mockApi({ [voidKey(PAYMENT_ID)]: { status: 200, body: paymentOut({ id: PAYMENT_ID, voided: true, void_reason: "Pago duplicado" }) }, ...handlers });
  const onClose = vi.fn();
  const router = createMemoryRouter([{ path: "*", element: <Screen onClose={onClose} /> }], { initialEntries: ["/pagos?mes=2026-10"] });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RoleProvider value={role}>
        <RouterProvider router={router} />
      </RoleProvider>
    </QueryClientProvider>,
  );
  return { mock, router, onClose, queryClient, user: userEvent.setup(), ...view };
}

const dialog = () => screen.getByRole("dialog", { name: VOID_MESSAGES.title });
const reasonBox = () => within(dialog()).getByRole("textbox", { name: /^Motivo/ });
const confirmButton = () => within(dialog()).getByRole("button", { name: "Anular pago" });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("VoidPaymentModal", () => {
  it("el coach no lo ve: anular es solo del admin (payments.void)", () => {
    renderModal("coach");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("pide un motivo obligatorio con la consecuencia y el aviso M-7", async () => {
    const { user } = renderModal("admin");

    expect(dialog()).toHaveAccessibleDescription(VOID_MESSAGES.consequence);
    expect(reasonBox()).toHaveAttribute("aria-required", "true");
    expect(reasonBox()).toHaveAccessibleDescription(/No escribas teléfonos, documentos ni datos de salud\./);
    expect(confirmButton()).toBeDisabled();

    await user.type(reasonBox(), "   ");
    expect(confirmButton()).toBeDisabled();
    await user.type(reasonBox(), "x");
    expect(confirmButton()).toBeEnabled();
  });

  it("un motivo de más de 500 caracteres se explica y no se envía", async () => {
    const { user, mock } = renderModal("admin");

    await user.click(reasonBox());
    await user.paste("a".repeat(501));

    expect(within(dialog()).getByText("El motivo admite hasta 500 caracteres.")).toBeInTheDocument();
    expect(confirmButton()).toBeDisabled();
    expect(mock.calls).toHaveLength(0);
  });

  it("anula con el motivo recortado y ofrece Registrar pago nuevo con la precarga", async () => {
    const { user, mock, router, onClose } = renderModal("admin");

    await user.type(reasonBox(), "  Pago duplicado  ");
    await user.click(confirmButton());

    const done = await screen.findByRole("dialog", { name: VOID_MESSAGES.doneTitle });
    expect(mock.callsTo(voidKey(PAYMENT_ID)).map((c) => c.body)).toEqual([{ reason: "Pago duplicado" }]);
    expect(done).toHaveTextContent(VOID_MESSAGES.done("$ 120.000"));
    const link = within(done).getByRole("link", { name: "Registrar pago nuevo" });
    expect(link).toHaveAttribute("href", `/pagos?mes=2026-10&pago=${MEMBERSHIP}`);

    await user.click(link);

    expect(router.state.location.search).toBe(`?mes=2026-10&pago=${MEMBERSHIP}`);
    expect(router.state.location.state).toEqual({ paymentPrefill: { amountCop: 120_000, method: "nequi" } });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Cerrar tras anular cierra sin abrir el panel", async () => {
    const { user, router, onClose } = renderModal("admin");
    await user.type(reasonBox(), "Error de digitación");
    await user.click(confirmButton());

    await user.click(within(await screen.findByRole("dialog", { name: VOID_MESSAGES.doneTitle })).getByRole("button", { name: "Cerrar" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(router.state.location.search).toBe("?mes=2026-10");
  });

  it("anular invalida pagos, membresías, socios y resúmenes", async () => {
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { user } = renderModal("admin", {}, queryClient);

    await user.type(reasonBox(), "Pago duplicado");
    await user.click(confirmButton());
    await screen.findByRole("dialog", { name: VOID_MESSAGES.doneTitle });

    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual(
      expect.arrayContaining([["payments"], ["payments-summary"], ["memberships"], ["memberships-summary"], ["members"]]),
    );
  });

  it("409 payment_already_voided dice que otra persona lo anuló antes y refresca el pago", async () => {
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { user } = renderModal("admin", { [voidKey(PAYMENT_ID)]: apiError(409, "payment_already_voided") }, queryClient);

    await user.type(reasonBox(), "Pago duplicado");
    await user.click(confirmButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(VOID_MESSAGES.alreadyVoided);
    expect(VOID_MESSAGES.alreadyVoided).toContain("Otra persona lo anuló antes");
    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toContainEqual(["payments"]);
    expect(screen.queryByRole("dialog", { name: VOID_MESSAGES.doneTitle })).not.toBeInTheDocument();
  });

  it("un 422 del motivo va bajo el campo con el mensaje de la pantalla", async () => {
    const { user } = renderModal("admin", { [voidKey(PAYMENT_ID)]: apiError(422, "validation_error", { field: "reason" }) });

    await user.type(reasonBox(), "Pago duplicado");
    await user.click(confirmButton());

    await waitFor(() => {
      expect(reasonBox()).toHaveAccessibleDescription(expect.stringContaining(VOID_MESSAGES.reasonInvalid));
    });
  });

  it.each([
    [apiError(403, "forbidden"), VOID_MESSAGES.forbidden],
    [apiError(404, "payment_not_found"), VOID_MESSAGES.notFound],
    [apiError(500, "internal_error"), VOID_MESSAGES.server],
  ])("%j se explica dentro del modal", async (reply, message) => {
    const { user } = renderModal("admin", { [voidKey(PAYMENT_ID)]: reply });

    await user.type(reasonBox(), "Pago duplicado");
    await user.click(confirmButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
  });

  it("tras responder, la caché de mutaciones no conserva el motivo (S3-D52)", async () => {
    const { user, queryClient } = renderModal("admin", { [voidKey(PAYMENT_ID)]: apiError(500, "internal_error") });

    await user.type(reasonBox(), "Pago duplicado");
    await user.click(confirmButton());
    await within(dialog()).findByRole("alert");

    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll().filter((m) => m.state.variables !== undefined)).toEqual([]);
    });
  });

  it("Volver cierra sin enviar", async () => {
    const { user, mock, onClose } = renderModal("admin");

    await user.click(within(dialog()).getByRole("button", { name: "Volver" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(mock.calls).toHaveLength(0);
  });

  it("no tiene violaciones de axe (con el motivo y tras anular)", async () => {
    const { user } = renderModal("admin");
    expect(await axe(document.body)).toHaveNoViolations();

    await user.type(reasonBox(), "Pago duplicado");
    await user.click(confirmButton());
    await screen.findByRole("dialog", { name: VOID_MESSAGES.doneTitle });
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
