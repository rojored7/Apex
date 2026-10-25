// S3-F4 · US-095 (front): panel "Registrar pago" (Pagos.html, "Panel · Registrar pago"), abierto
// por la URL (S3-D65). Se prueba montado como lo monta PanelShell (RegisterPaymentPanelHost).
// - Preselección: `?pago=nuevo&socio=` fija el socio; `?pago=<membresía>` fija la membresía.
// - Opciones "Mensual 25 oct–24 nov · saldo $ 60.000" desde GET /memberships?member_id=&status=
//   active,expiring,frozen,pending_payment (S3-D66, con `paid_cop`).
// - Monto entero; errores del envelope bajo su campo; aviso M-7 bajo la referencia; envío en UTC.
// - Q5 (H-1, S3-D41): un valor mayor al saldo abre ConfirmModal y solo entonces viaja
//   `confirm_overpayment: true`; un 409 `payment_exceeds_balance` también lo abre. Un 409
//   `payment_possible_duplicate` abre el segundo modal y `confirm_duplicate: true` solo viaja al
//   confirmar. `payment_limit_reached` se explica y no se reintenta.
// - S3-D52 (M-9): tras responder, la caché de mutaciones no conserva `variables`.
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { BUSY_MESSAGE } from "../../../core/api/errorCodes";
import { MEMBERS } from "../../../test/members";
import { apiError, MEMBERSHIP_ID, membershipRow, membershipRowsPage } from "../../../test/memberships";
import {
  findPaymentPanel,
  membershipSelect,
  panelAmount,
  panelPaidAt,
  panelReference,
  panelSubmit,
  PAYMENT_NOW,
  paymentPanel,
  registerBodies,
  registerKey,
  renderPaymentPanel,
} from "../../../test/paymentPanel";
import { paymentOut } from "../../../test/payments";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { PAYMENT_MESSAGES } from "../paymentErrors";

const LAURA = MEMBERS.laura.id;
const OTHER_MEMBERSHIP = "77777777-0000-4000-8000-000000000077";
const OPTION = "Mensual 25 oct–24 nov · saldo $ 60.000";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: PAYMENT_NOW });
  setViewportWidth(1440);
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** Abre el panel de la membresía de Laura y espera a que quede elegida. */
async function openForMembership(options: Parameters<typeof renderPaymentPanel>[1] = {}) {
  const view = renderPaymentPanel(`/membresias?pago=${MEMBERSHIP_ID}`, options);
  await findPaymentPanel();
  await waitFor(() => {
    expect(membershipSelect()).toHaveValue(MEMBERSHIP_ID);
  });
  return view;
}

const openStatusParams = (url: string | undefined): URLSearchParams => new URL(url ?? "", "http://apex.test").searchParams;

describe("RegisterPaymentPanel · preselección", () => {
  it("?pago=nuevo&socio= fija el socio, pide sus membresías abiertas y elige la única", async () => {
    const { mock } = renderPaymentPanel(`/socios?pago=nuevo&socio=${LAURA}`);

    await findPaymentPanel();
    await waitFor(() => {
      expect(membershipSelect()).toHaveValue(MEMBERSHIP_ID);
    });
    expect(within(paymentPanel()).queryByRole("searchbox", { name: "Buscar socio" })).not.toBeInTheDocument();
    expect(within(paymentPanel()).getByText("Laura Gómez")).toBeInTheDocument();
    const params = openStatusParams(mock.callsTo("GET /memberships")[0]?.url);
    expect(params.get("member_id")).toBe(LAURA);
    expect(params.get("status")).toBe("active,expiring,frozen,pending_payment");
    expect(within(membershipSelect()).getAllByRole("option").map((o) => o.textContent)).toEqual(["Elige la membresía", OPTION]);
  });

  it("?pago=<membresía> lee esa membresía, la deja elegida y precarga el valor con su saldo", async () => {
    const { mock } = await openForMembership();

    expect(mock.callsTo(`GET /memberships/${MEMBERSHIP_ID}`)).toHaveLength(1);
    expect(openStatusParams(mock.callsTo("GET /memberships")[0]?.url).get("member_id")).toBe(LAURA);
    await waitFor(() => {
      expect(panelAmount()).toHaveValue("$ 60.000");
    });
    expect(within(paymentPanel()).getByText("Saldo pendiente: $ 60.000")).toBeInTheDocument();
    expect(within(paymentPanel()).getByText("Laura Gómez")).toBeInTheDocument();
  });

  it("varias membresías abiertas: cada opción dice plan, fechas y saldo; ninguna se elige sola", async () => {
    renderPaymentPanel(`/socios?pago=nuevo&socio=${LAURA}`, {
      handlers: {
        "GET /memberships": membershipRowsPage([
          membershipRow(),
          membershipRow({ id: OTHER_MEMBERSHIP, plan_name: "12 clases", status: "active", start_date: "2026-12-15", end_date: "2027-01-14", paid_cop: 110_000, agreed_price_cop: 110_000 }),
        ]),
      },
    });
    await findPaymentPanel();

    await waitFor(() => {
      expect(within(membershipSelect()).getAllByRole("option")).toHaveLength(3);
    });
    expect(within(membershipSelect()).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Elige la membresía",
      OPTION,
      "12 clases 15 dic 2026–14 ene 2027 · sin saldo pendiente",
    ]);
    expect(membershipSelect()).toHaveValue("");
  });

  it("?pago=nuevo pide buscar el socio; al elegirlo carga sus membresías", async () => {
    const { user, mock } = renderPaymentPanel("/pagos?pago=nuevo");
    await findPaymentPanel();

    await user.type(within(paymentPanel()).getByRole("searchbox", { name: "Buscar socio" }), "laura");
    await user.click(await within(paymentPanel()).findByRole("button", { name: /Laura Gómez/ }));

    await waitFor(() => {
      expect(membershipSelect()).toHaveValue(MEMBERSHIP_ID);
    });
    expect(openStatusParams(mock.callsTo("GET /memberships")[0]?.url).get("member_id")).toBe(LAURA);
    await user.click(within(paymentPanel()).getByRole("button", { name: "Cambiar socio" }));
    expect(within(paymentPanel()).getByRole("searchbox", { name: "Buscar socio" })).toHaveFocus();
    expect(within(paymentPanel()).queryByRole("combobox", { name: /^Membresía/ })).not.toBeInTheDocument();
  });

  it("un socio sin membresías abiertas: lo dice y ofrece vender una", async () => {
    renderPaymentPanel(`/socios?pago=nuevo&socio=${LAURA}`, { handlers: { "GET /memberships": membershipRowsPage([]) } });
    await findPaymentPanel();

    expect(await within(paymentPanel()).findByText(PAYMENT_MESSAGES.noOpenMemberships)).toBeInTheDocument();
    expect(within(paymentPanel()).getByRole("link", { name: "Vender una membresía" })).toHaveAttribute("href", `/membresias/vender?socio=${LAURA}`);
  });

  it("S3-F7: un socio de la URL sin membresías abiertas se nombra con GET /members/{id} (no 'Socio elegido')", async () => {
    const { mock } = renderPaymentPanel(`/socios?pago=nuevo&socio=${LAURA}`, {
      handlers: { "GET /memberships": membershipRowsPage([]), [`GET /members/${LAURA}`]: { status: 200, body: { id: LAURA, first_name: "Laura", last_name: "Gómez" } } },
    });
    await findPaymentPanel();

    expect(await within(paymentPanel()).findByText("Laura Gómez")).toBeInTheDocument();
    expect(within(paymentPanel()).queryByText("Socio elegido")).not.toBeInTheDocument();
    expect(mock.callsTo(`GET /members/${LAURA}`)).toHaveLength(1);
  });

  it("S3-F7: con membresías abiertas el nombre sale de ellas y no se pide GET /members/{id}", async () => {
    const { mock } = renderPaymentPanel(`/socios?pago=nuevo&socio=${LAURA}`);
    await findPaymentPanel();

    expect(await within(paymentPanel()).findByText("Laura Gómez")).toBeInTheDocument();
    expect(mock.callsTo(`GET /members/${LAURA}`)).toHaveLength(0);
  });

  it("si las membresías no cargan, lo dice con Reintentar", async () => {
    const { user, mock } = renderPaymentPanel(`/socios?pago=nuevo&socio=${LAURA}`, { handlers: { "GET /memberships": apiError(500, "internal_error") } });
    await findPaymentPanel();

    expect(await within(paymentPanel()).findByText(PAYMENT_MESSAGES.membershipsFailed)).toBeInTheDocument();
    await user.click(within(paymentPanel()).getByRole("button", { name: "Reintentar" }));
    await waitFor(() => {
      expect(mock.callsTo("GET /memberships")).toHaveLength(2);
    });
  });

  it("precarga desde una anulación: valor y medio del pago anulado, no el saldo", async () => {
    await openForMembership({ state: { paymentPrefill: { amountCop: 120_000, method: "nequi" } } });

    expect(panelAmount()).toHaveValue("$ 120.000");
    expect(within(paymentPanel()).getByRole("radio", { name: "Nequi" })).toBeChecked();
  });
});

describe("RegisterPaymentPanel · campos y envío", () => {
  it("la fecha y hora del pago empieza en ahora (Bogotá) y se envía en UTC con el monto entero", async () => {
    const { user, mock } = await openForMembership();
    expect(panelPaidAt()).toHaveValue("2026-10-28T10:00");
    await waitFor(() => {
      expect(panelAmount()).toHaveValue("$ 60.000");
    });

    fireEvent.change(panelPaidAt(), { target: { value: "2026-10-27T19:30" } });
    await user.click(panelSubmit());

    expect(await within(paymentPanel()).findByText("Pago registrado")).toBeInTheDocument();
    expect(registerBodies(mock)).toEqual([{ amount_cop: 60_000, method: "cash", paid_at: "2026-10-28T00:30:00.000Z", confirm_overpayment: false, confirm_duplicate: false }]);
  });

  it("un monto que no es entero no se envía y se explica bajo el campo", async () => {
    const { user, mock } = await openForMembership();

    await user.clear(panelAmount());
    await user.type(panelAmount(), "12,5");
    await user.click(panelSubmit());

    expect(await within(paymentPanel()).findByText(PAYMENT_MESSAGES.amountInvalid)).toBeInTheDocument();
    expect(panelAmount()).toHaveAttribute("aria-invalid", "true");
    expect(mock.callsTo(registerKey())).toHaveLength(0);
  });

  it("sin membresía elegida no se envía", async () => {
    const { user, mock } = renderPaymentPanel(`/socios?pago=nuevo&socio=${LAURA}`, {
      handlers: { "GET /memberships": membershipRowsPage([membershipRow(), membershipRow({ id: OTHER_MEMBERSHIP })]) },
    });
    await findPaymentPanel();
    await waitFor(() => {
      expect(within(membershipSelect()).getAllByRole("option")).toHaveLength(3);
    });

    await user.click(panelSubmit());

    expect(await within(paymentPanel()).findByText(PAYMENT_MESSAGES.membershipRequired)).toBeInTheDocument();
    expect(mock.calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("con Nequi muestra la referencia con el aviso M-7 y la envía recortada", async () => {
    const { user, mock } = await openForMembership();
    expect(panelReference()).not.toBeInTheDocument();

    await user.click(within(paymentPanel()).getByRole("radio", { name: "Nequi" }));
    const reference = panelReference() as HTMLElement;
    expect(reference).toHaveAccessibleDescription(/No escribas teléfonos, documentos ni datos de salud\./);
    await user.type(reference, "  M12345678  ");
    await user.click(panelSubmit());
    await within(paymentPanel()).findByText("Pago registrado");

    expect(registerBodies(mock)[0]).toMatchObject({ method: "nequi", reference: "M12345678" });
  });

  it("un doble clic envía una sola vez", async () => {
    let release: () => void = () => undefined;
    const { user, mock } = await openForMembership({
      handlers: {
        [registerKey()]: () =>
          new Promise((resolve) => {
            release = () => {
              resolve({ status: 201, body: paymentOut({ amount_cop: 60_000 }) });
            };
          }),
      },
    });

    await user.dblClick(panelSubmit());
    await waitFor(() => {
      expect(mock.callsTo(registerKey())).toHaveLength(1);
    });
    act(() => {
      release();
    });
    await within(paymentPanel()).findByText("Pago registrado");
    expect(mock.callsTo(registerKey())).toHaveLength(1);
  });

  it("tras registrar: invalida pagos, membresías, socios y resúmenes; la caché de mutaciones no guarda el cuerpo", async () => {
    const { user, queryClient } = await openForMembership();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    await user.click(panelSubmit());
    await within(paymentPanel()).findByText("Pago registrado");

    const keys = invalidate.mock.calls.map(([filters]) => filters?.queryKey);
    expect(keys).toEqual(expect.arrayContaining([["payments"], ["payments-summary"], ["memberships"], ["memberships-summary"], ["members"]]));
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll().filter((m) => m.state.variables !== undefined)).toEqual([]);
    });
  });

  it("tras registrar se ve el resumen; Registrar otro pago vuelve al formulario y Cancelar quita ?pago= de la URL", async () => {
    const { user, router } = await openForMembership();
    await waitFor(() => {
      expect(panelAmount()).toHaveValue("$ 60.000");
    });
    await user.click(panelSubmit());

    const done = await within(paymentPanel()).findByRole("status", { name: "Pago registrado" });
    expect(done).toHaveTextContent("$ 60.000");
    expect(done).toHaveTextContent("Efectivo");
    await user.click(within(paymentPanel()).getByRole("button", { name: "Registrar otro pago" }));
    expect(panelSubmit()).toBeInTheDocument();

    await user.click(within(paymentPanel()).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Registrar pago" })).not.toBeInTheDocument();
    });
    expect(router.state.location.pathname).toBe("/membresias");
    expect(router.state.location.search).toBe("");
  });

  it("no tiene violaciones de axe con Nequi elegido", async () => {
    const { user } = await openForMembership();
    await user.click(within(paymentPanel()).getByRole("radio", { name: "Nequi" }));

    expect(await axe(document.body)).toHaveNoViolations();
  });
});

describe("RegisterPaymentPanel · errores del api", () => {
  it.each([
    [apiError(422, "validation_error", { field: "paid_at" }), PAYMENT_MESSAGES.paidAtServer],
    [apiError(422, "paid_at_too_retroactive", { field: "paid_at" }), PAYMENT_MESSAGES.paidAtTooRetroactive],
  ])("%j va bajo Fecha y hora del pago con foco", async (reply, message) => {
    const { user } = await openForMembership({ handlers: { [registerKey()]: reply } });

    await user.click(panelSubmit());

    expect(await within(paymentPanel()).findByText(message)).toBeInTheDocument();
    await waitFor(() => {
      expect(panelPaidAt()).toHaveFocus();
    });
  });

  it("el texto del coach para paid_at_too_retroactive dice los 7 días", () => {
    expect(PAYMENT_MESSAGES.paidAtTooRetroactive).toContain("últimos 7 días");
    expect(PAYMENT_MESSAGES.paidAtTooRetroactive).toContain("administrador");
  });

  it("422 de amount_cop va bajo Valor recibido", async () => {
    const { user } = await openForMembership({ handlers: { [registerKey()]: apiError(422, "validation_error", { field: "amount_cop" }) } });

    await user.click(panelSubmit());

    expect(await within(paymentPanel()).findByText(PAYMENT_MESSAGES.amountServer)).toBeInTheDocument();
  });

  it("409 membership_cancelled va bajo Membresía y relee las membresías del socio", async () => {
    const { user, mock } = await openForMembership({ handlers: { [registerKey()]: apiError(409, "membership_cancelled") } });
    const before = mock.callsTo("GET /memberships").length;

    await user.click(panelSubmit());

    expect(await within(paymentPanel()).findByText(PAYMENT_MESSAGES.membershipCancelled)).toBeInTheDocument();
    expect(membershipSelect()).toHaveAttribute("aria-invalid", "true");
    await waitFor(() => {
      expect(mock.callsTo("GET /memberships").length).toBeGreaterThan(before);
    });
    expect(screen.queryByRole("dialog", { name: PAYMENT_MESSAGES.overpayTitle })).not.toBeInTheDocument();
  });

  it("409 payment_limit_reached se explica y no se reintenta", async () => {
    const { user, mock } = await openForMembership({ handlers: { [registerKey()]: apiError(409, "payment_limit_reached") } });

    await user.click(panelSubmit());

    expect(await within(paymentPanel()).findByRole("alert")).toHaveTextContent(PAYMENT_MESSAGES.limitReached);
    expect(mock.callsTo(registerKey())).toHaveLength(1);
    expect(screen.queryByRole("dialog", { name: PAYMENT_MESSAGES.duplicateTitle })).not.toBeInTheDocument();
  });

  it("503 busy muestra el mensaje común y no limpia el formulario", async () => {
    const { user } = await openForMembership({ handlers: { [registerKey()]: apiError(503, "busy", {}, { "Retry-After": "1" }) } });
    await user.clear(panelAmount());
    await user.type(panelAmount(), "50000");

    await user.click(panelSubmit());

    expect(await within(paymentPanel()).findByRole("alert")).toHaveTextContent(BUSY_MESSAGE);
    expect(panelAmount()).toHaveValue("$ 50.000");
  });

  it.each([
    [apiError(403, "forbidden"), PAYMENT_MESSAGES.forbidden],
    [apiError(429, "rate_limited", {}, { "Retry-After": "30" }), PAYMENT_MESSAGES.tooMany("30 segundos")],
    [apiError(500, "internal_error"), PAYMENT_MESSAGES.server],
  ])("%j se explica en un aviso general", async (reply, message) => {
    const { user } = await openForMembership({ handlers: { [registerKey()]: reply } });

    await user.click(panelSubmit());

    expect(await within(paymentPanel()).findByRole("alert")).toHaveTextContent(message);
  });
});

describe("RegisterPaymentPanel · confirmaciones (Q5 y duplicado, S3-D41)", () => {
  async function typeAmount(user: Awaited<ReturnType<typeof openForMembership>>["user"], amount: string): Promise<void> {
    await waitFor(() => {
      expect(panelAmount()).toHaveValue("$ 60.000");
    });
    await user.clear(panelAmount());
    await user.type(panelAmount(), amount);
  }

  it("un valor mayor al saldo pide confirmar antes de enviar; Volver no envía", async () => {
    const { user, mock } = await openForMembership();
    await typeAmount(user, "80000");

    await user.click(panelSubmit());

    const modal = await screen.findByRole("dialog", { name: PAYMENT_MESSAGES.overpayTitle });
    expect(modal).toHaveTextContent(PAYMENT_MESSAGES.overpay("$ 20.000"));
    expect(mock.callsTo(registerKey())).toHaveLength(0);
    await user.click(within(modal).getByRole("button", { name: "Volver" }));
    expect(mock.callsTo(registerKey())).toHaveLength(0);
  });

  it("al confirmar el sobrepago envía con confirm_overpayment: true", async () => {
    const { user, mock } = await openForMembership();
    await typeAmount(user, "80000");
    await user.click(panelSubmit());

    await user.click(within(await screen.findByRole("dialog", { name: PAYMENT_MESSAGES.overpayTitle })).getByRole("button", { name: "Registrar pago" }));

    await within(paymentPanel()).findByText("Pago registrado");
    expect(registerBodies(mock)).toEqual([expect.objectContaining({ amount_cop: 80_000, confirm_overpayment: true, confirm_duplicate: false })]);
  });

  it("un 409 payment_exceeds_balance inesperado también abre la confirmación y reenvía", async () => {
    let calls = 0;
    const { user, mock } = await openForMembership({
      handlers: {
        [registerKey()]: () => {
          calls += 1;
          return calls === 1 ? apiError(409, "payment_exceeds_balance", { field: "amount_cop" }) : { status: 201, body: paymentOut({ amount_cop: 60_000 }) };
        },
      },
    });
    await waitFor(() => {
      expect(panelAmount()).toHaveValue("$ 60.000");
    });

    await user.click(panelSubmit());
    const modal = await screen.findByRole("dialog", { name: PAYMENT_MESSAGES.overpayTitle });
    expect(modal).toHaveTextContent(PAYMENT_MESSAGES.overpayUnknown);
    await user.click(within(modal).getByRole("button", { name: "Registrar pago" }));

    await within(paymentPanel()).findByText("Pago registrado");
    expect(registerBodies(mock).map((b) => b.confirm_overpayment)).toEqual([false, true]);
  });

  it("409 payment_possible_duplicate abre el segundo modal y confirm_duplicate: true solo viaja al confirmar", async () => {
    let calls = 0;
    const { user, mock } = await openForMembership({
      handlers: {
        [registerKey()]: () => {
          calls += 1;
          return calls <= 2 ? apiError(409, "payment_possible_duplicate") : { status: 201, body: paymentOut({ amount_cop: 60_000 }) };
        },
      },
    });
    await waitFor(() => {
      expect(panelAmount()).toHaveValue("$ 60.000");
    });

    await user.click(panelSubmit());
    let modal = await screen.findByRole("dialog", { name: PAYMENT_MESSAGES.duplicateTitle });
    expect(modal).toHaveTextContent("Ya registraste un pago igual hace menos de 2 minutos");
    await user.click(within(modal).getByRole("button", { name: "Volver" }));
    expect(registerBodies(mock).map((b) => b.confirm_duplicate)).toEqual([false]);

    await user.click(panelSubmit());
    modal = await screen.findByRole("dialog", { name: PAYMENT_MESSAGES.duplicateTitle });
    await user.click(within(modal).getByRole("button", { name: "Sí, registrar otro" }));

    await within(paymentPanel()).findByText("Pago registrado");
    expect(registerBodies(mock).map((b) => b.confirm_duplicate)).toEqual([false, false, true]);
  });

  it("un duplicado tras confirmar el sobrepago conserva confirm_overpayment", async () => {
    let calls = 0;
    const { user, mock } = await openForMembership({
      handlers: {
        [registerKey()]: () => {
          calls += 1;
          return calls === 1 ? apiError(409, "payment_possible_duplicate") : { status: 201, body: paymentOut({ amount_cop: 80_000 }) };
        },
      },
    });
    await typeAmount(user, "80000");
    await user.click(panelSubmit());
    await user.click(within(await screen.findByRole("dialog", { name: PAYMENT_MESSAGES.overpayTitle })).getByRole("button", { name: "Registrar pago" }));

    await user.click(within(await screen.findByRole("dialog", { name: PAYMENT_MESSAGES.duplicateTitle })).getByRole("button", { name: "Sí, registrar otro" }));

    await within(paymentPanel()).findByText("Pago registrado");
    expect(registerBodies(mock).map((b) => [b.confirm_overpayment, b.confirm_duplicate])).toEqual([
      [true, false],
      [true, true],
    ]);
  });
});

describe("RegisterPaymentPanel · revisión S3-F4", () => {
  it("H1: si la membresía de ?pago= no carga, lo explica con Reintentar y no ofrece el buscador", async () => {
    const { user, mock } = renderPaymentPanel(`/membresias?pago=${MEMBERSHIP_ID}`, { handlers: { [`GET /memberships/${MEMBERSHIP_ID}`]: apiError(404, "membership_not_found") } });
    await findPaymentPanel();

    expect(await within(paymentPanel()).findByRole("alert")).toHaveTextContent(PAYMENT_MESSAGES.membershipFromUrlFailed);
    expect(within(paymentPanel()).queryByRole("searchbox", { name: "Buscar socio" })).not.toBeInTheDocument();
    expect(panelSubmit()).toBeDisabled();
    await user.click(within(paymentPanel()).getByRole("button", { name: "Reintentar" }));
    await waitFor(() => {
      expect(mock.callsTo(`GET /memberships/${MEMBERSHIP_ID}`)).toHaveLength(2);
    });
  });

  it("H1: mientras carga la membresía de ?pago= dice que está cargando", async () => {
    renderPaymentPanel(`/membresias?pago=${MEMBERSHIP_ID}`, { handlers: { [`GET /memberships/${MEMBERSHIP_ID}`]: () => new Promise(() => undefined) } });
    await findPaymentPanel();

    expect(within(paymentPanel()).getByText("Cargando la membresía…")).toBeInTheDocument();
    expect(within(paymentPanel()).queryByRole("searchbox", { name: "Buscar socio" })).not.toBeInTheDocument();
  });

  it("M1: sin socio o sin membresías abiertas, Registrar queda deshabilitado", async () => {
    renderPaymentPanel("/pagos?pago=nuevo");
    await findPaymentPanel();
    expect(panelSubmit()).toBeDisabled();
    cleanup();

    renderPaymentPanel(`/socios?pago=nuevo&socio=${LAURA}`, { handlers: { "GET /memberships": membershipRowsPage([]) } });
    await findPaymentPanel();
    await within(paymentPanel()).findByText(PAYMENT_MESSAGES.noOpenMemberships);
    expect(panelSubmit()).toBeDisabled();
  });

  it("M2: tras registrar el foco va al resumen y, con Registrar otro pago, al valor", async () => {
    const { user } = await openForMembership();
    await user.click(panelSubmit());

    const title = await within(paymentPanel()).findByRole("heading", { name: "Pago registrado" });
    await waitFor(() => {
      expect(title).toHaveFocus();
    });
    await user.click(within(paymentPanel()).getByRole("button", { name: "Registrar otro pago" }));
    await waitFor(() => {
      expect(panelAmount()).toHaveFocus();
    });
  });
});
