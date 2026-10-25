// S3-F4 (S3-D65, E10): RegisterPaymentPanelHost, el punto de montaje único del panel "Registrar
// pago" en PanelShell. Sin `?pago=` no pinta nada ni pide datos; con `?pago=` abre el panel;
// cerrarlo quita el parámetro (y su `socio`) y conserva los demás filtros de la URL.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { MEMBERS } from "../../../test/members";
import { MEMBERSHIP_ID } from "../../../test/memberships";
import { findPaymentPanel, PAYMENT_NOW, renderPaymentPanel } from "../../../test/paymentPanel";
import { signInAs, signOutForTests } from "../../../test/session";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: PAYMENT_NOW });
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("RegisterPaymentPanelHost", () => {
  it("sin ?pago= no pinta nada ni pide datos", () => {
    const { mock } = renderPaymentPanel("/membresias?status=active");

    expect(screen.getByRole("heading", { name: "Pantalla" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.calls).toHaveLength(0);
  });

  it("un ?pago= que no es una membresía ni nuevo no abre nada", () => {
    renderPaymentPanel("/membresias?pago=basura");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("con ?pago= abre el panel", async () => {
    renderPaymentPanel(`/membresias?pago=${MEMBERSHIP_ID}`);

    expect(await findPaymentPanel()).toBeInTheDocument();
  });

  it("cerrar quita ?pago= y conserva los demás filtros, sin dejar una entrada nueva en el historial", async () => {
    const { user, router } = renderPaymentPanel(`/membresias?status=pending_payment&pago=${MEMBERSHIP_ID}&limit=50`);
    const panel = await findPaymentPanel();

    await user.click(within(panel).getByRole("button", { name: "Cancelar" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(router.state.location.search).toBe("?status=pending_payment&limit=50");
    expect(router.state.historyAction).toBe("REPLACE");
  });

  it("cerrar un pago nuevo quita también su socio", async () => {
    const { user, router } = renderPaymentPanel(`/socios?pago=nuevo&socio=${MEMBERS.laura.id}`);
    const panel = await findPaymentPanel();

    await user.click(within(panel).getByRole("button", { name: "Cerrar" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
    expect(router.state.location.pathname).toBe("/socios");
  });
});
