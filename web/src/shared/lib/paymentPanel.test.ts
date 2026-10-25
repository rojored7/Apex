// S3-F4 (S3-D65, condición 8): el panel "Registrar pago" se abre por la URL desde cualquier
// pantalla del panel. Funciones puras: armar el enlace, leerlo, cerrarlo y la precarga.
import { closePaymentPanelHref, paymentPanelHref, paymentPanelState, readPaymentPanel, readPaymentPrefill } from "./paymentPanel";

const MEMBERSHIP = "66666666-6666-4666-8666-666666666666";
const MEMBER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

describe("paymentPanelHref", () => {
  it("abre el panel de una membresía conservando la ruta y los demás filtros", () => {
    expect(paymentPanelHref({ pathname: "/membresias", search: "?status=pending_payment&limit=50" }, { membershipId: MEMBERSHIP })).toBe(
      `/membresias?status=pending_payment&limit=50&pago=${MEMBERSHIP}`,
    );
  });

  it("abre el panel de un pago nuevo con el socio elegido", () => {
    expect(paymentPanelHref({ pathname: "/socios", search: "" }, { memberId: MEMBER })).toBe(`/socios?pago=nuevo&socio=${MEMBER}`);
  });

  it("sin socio abre el panel vacío (y quita un socio anterior)", () => {
    expect(paymentPanelHref({ pathname: "/pagos", search: `?pago=nuevo&socio=${MEMBER}&mes=2026-10` }, { memberId: null })).toBe("/pagos?pago=nuevo&mes=2026-10");
  });

  it("reemplaza un ?pago= anterior en vez de repetirlo", () => {
    expect(paymentPanelHref({ pathname: "/pagos", search: "?pago=nuevo" }, { membershipId: MEMBERSHIP })).toBe(`/pagos?pago=${MEMBERSHIP}`);
  });
});

describe("readPaymentPanel", () => {
  it("sin ?pago= no hay panel", () => {
    expect(readPaymentPanel("")).toBeNull();
    expect(readPaymentPanel("?status=active")).toBeNull();
  });

  it("?pago=<uuid> es el panel de esa membresía", () => {
    expect(readPaymentPanel(`?pago=${MEMBERSHIP}`)).toEqual({ kind: "membership", membershipId: MEMBERSHIP });
  });

  it("?pago=nuevo&socio=<uuid> es un pago nuevo para ese socio; sin socio, para elegirlo", () => {
    expect(readPaymentPanel(`?pago=nuevo&socio=${MEMBER}`)).toEqual({ kind: "new", memberId: MEMBER });
    expect(readPaymentPanel("?pago=nuevo")).toEqual({ kind: "new", memberId: null });
  });

  it("un socio que no es un UUID se ignora; un ?pago= que no es nuevo ni un UUID no abre nada", () => {
    expect(readPaymentPanel("?pago=nuevo&socio=1234")).toEqual({ kind: "new", memberId: null });
    expect(readPaymentPanel("?pago=<script>")).toBeNull();
    expect(readPaymentPanel("?pago=")).toBeNull();
  });
});

describe("closePaymentPanelHref", () => {
  it("quita ?pago= y conserva lo demás", () => {
    expect(closePaymentPanelHref({ pathname: "/membresias", search: `?status=active&pago=${MEMBERSHIP}&limit=50` })).toBe("/membresias?status=active&limit=50");
  });

  it("al cerrar un pago nuevo quita también su socio", () => {
    expect(closePaymentPanelHref({ pathname: "/socios", search: `?pago=nuevo&socio=${MEMBER}` })).toBe("/socios");
  });

  it("al cerrar el panel de una membresía no toca un ?socio= de la pantalla", () => {
    expect(closePaymentPanelHref({ pathname: "/membresias/vender", search: `?socio=${MEMBER}&pago=${MEMBERSHIP}` })).toBe(`/membresias/vender?socio=${MEMBER}`);
  });
});

describe("precarga desde una anulación", () => {
  it("paymentPanelState y readPaymentPrefill van y vuelven", () => {
    const state = paymentPanelState({ amountCop: 120_000, method: "nequi" });

    expect(readPaymentPrefill(state)).toEqual({ amountCop: 120_000, method: "nequi" });
  });

  it.each([null, undefined, "x", { paymentPrefill: { amountCop: 1.5, method: "cash" } }, { paymentPrefill: { amountCop: 1000, method: "tarjeta" } }, { paymentPrefill: { amountCop: 0, method: "cash" } }])(
    "un estado ajeno o mal formado (%j) no precarga nada",
    (state) => {
      expect(readPaymentPrefill(state)).toBeNull();
    },
  );
});
