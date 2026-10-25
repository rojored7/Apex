// S3-F7 · US-101 (front): pestaña Pagos de la ficha (/socios/:id/pagos), admin y coach. Vive en
// features/payments (S3-D65), no en features/members.
// - GET /members/{id}/payments (B11): DataTable paginada en el orden del api (`paid_at` descendente):
//   fecha y hora de Bogotá, membresía, valor (tachado si está anulado), medio, referencia, registró y
//   StatusTag "Válido" o "Anulado" con su motivo, y la marca "Retroactivo" (S3-D51).
// - Conmutador "Ocultar anulados" (voided=false); "Registrar pago" abre el panel con el socio
//   (?pago=nuevo&socio=, S3-D65) y se oculta para un dado de baja; "Anular" solo con payments.void y
//   abre VoidPaymentModal.
// - Vacío "Este socio no tiene pagos."; carga; error con "Reintentar".
import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { formatCop, formatDateTime } from "../../../core/i18n/format";
import { DELETED_TAB_MEMBER, listCallsTo, MEMBER_ID, MEMBER_PAYMENTS_PATH, memberPayments, pageOf, renderMemberTab, VALID_PAYMENT_ID } from "../../../test/memberTabs";
import { paymentRow } from "../../../test/payments";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { VOID_MESSAGES } from "../paymentErrors";
import MemberPaymentsTab from "./MemberPaymentsTab";

const renderTab = (options: Parameters<typeof renderMemberTab>[3] = {}, entry?: string) => renderMemberTab(MemberPaymentsTab, "pagos", entry, options);
const table = (): Promise<HTMLElement> => screen.findByRole("region", { name: "Pagos del socio" });
const bodyRows = async (): Promise<HTMLElement[]> => within(await table()).getAllByRole("row").slice(1);

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("MemberPaymentsTab · lista", () => {
  it("pide GET /members/{id}/payments sin `voided` y pinta las filas en el orden del api (más reciente primero)", async () => {
    const { mock } = renderTab();
    const rows = await bodyRows();

    expect(rows.map((row) => within(row).getAllByRole("cell")[0]?.textContent)).toEqual(memberPayments().map((p) => formatDateTime(p.paid_at)));
    const call = listCallsTo(mock, MEMBER_PAYMENTS_PATH)[0];
    expect(call?.get("limit")).toBe("25");
    expect(call?.get("offset")).toBe("0");
    expect(call?.has("voided")).toBe(false);
    const first = rows[0] as HTMLElement;
    expect(within(first).getByText("Nequi")).toBeInTheDocument();
    expect(within(first).getByText("M12345678")).toBeInTheDocument();
    expect(within(first).getByText("Válido")).toBeInTheDocument();
    // Dentro de la ficha la fila no lleva a otra pantalla.
    expect(within(await table()).queryAllByRole("link")).toHaveLength(0);
  });

  it("un pago anulado: valor tachado, 'Anulado' y su motivo; sin 'Anular'", async () => {
    renderTab();
    const voided = (await bodyRows())[1] as HTMLElement;

    expect(within(voided).getByText("Anulado")).toBeInTheDocument();
    expect(within(voided).getByText("Motivo: Duplicado")).toBeInTheDocument();
    expect(within(voided).getByText(formatCop(60_000)).tagName).toBe("S");
    expect(within(voided).queryByRole("button", { name: /^Anular/ })).not.toBeInTheDocument();
  });

  it("un pago registrado más de 24 h después lleva la marca 'Retroactivo' (S3-D51)", async () => {
    renderTab();
    const backdated = (await bodyRows())[2] as HTMLElement;

    expect(within(backdated).getByText("Retroactivo")).toBeInTheDocument();
    expect(within(backdated).getByText("Efectivo")).toBeInTheDocument();
    expect(within((await bodyRows())[0] as HTMLElement).queryByText("Retroactivo")).not.toBeInTheDocument();
  });

  it("'Ocultar anulados' pide voided=false, vuelve a la primera página y lo deja en la URL", async () => {
    const { mock, user } = renderTab({}, `/socios/${MEMBER_ID}/pagos?offset=25`);
    await table();

    await user.click(screen.getByRole("checkbox", { name: "Ocultar anulados" }));

    await waitFor(() => {
      expect(listCallsTo(mock, MEMBER_PAYMENTS_PATH).at(-1)?.get("voided")).toBe("false");
    });
    expect(listCallsTo(mock, MEMBER_PAYMENTS_PATH).at(-1)?.get("offset")).toBe("0");
    expect(screen.getByRole("checkbox", { name: "Ocultar anulados" })).toBeChecked();
    expect(screen.getByTestId("location")).toHaveTextContent("voided=false");

    await user.click(screen.getByRole("checkbox", { name: "Ocultar anulados" }));
    await waitFor(() => {
      expect(listCallsTo(mock, MEMBER_PAYMENTS_PATH).at(-1)?.has("voided")).toBe(false);
    });
  });

  it("pagina en el servidor: la página 2 pide offset 25", async () => {
    const { mock, user } = renderTab({ handlers: { [`GET ${MEMBER_PAYMENTS_PATH}`]: (call) => pageOf(call, memberPayments(), 30) } });
    await table();

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));

    await waitFor(() => {
      expect(listCallsTo(mock, MEMBER_PAYMENTS_PATH).map((p) => p.get("offset"))).toEqual(["0", "25"]);
    });
  });
});

describe("MemberPaymentsTab · acciones", () => {
  it("'Registrar pago' abre el panel con el socio preseleccionado (?pago=nuevo&socio=)", async () => {
    renderTab();

    expect(await screen.findByRole("link", { name: "Registrar pago" })).toHaveAttribute("href", `/socios/${MEMBER_ID}/pagos?pago=nuevo&socio=${MEMBER_ID}`);
  });

  it("un socio dado de baja no tiene 'Registrar pago'", async () => {
    renderTab({ member: DELETED_TAB_MEMBER });
    await table();

    expect(screen.queryByRole("link", { name: "Registrar pago" })).not.toBeInTheDocument();
  });

  it("'Anular' solo con payments.void (admin) y en los pagos válidos; abre VoidPaymentModal", async () => {
    const { user } = renderTab();
    const rows = await bodyRows();
    const valid = rows[0] as HTMLElement;

    expect(within(await table()).getAllByRole("button", { name: /^Anular el pago/ })).toHaveLength(2);
    await user.click(within(valid).getByRole("button", { name: `Anular el pago de ${formatCop(60_000)} en Nequi del ${formatDateTime(memberPayments()[0]?.paid_at ?? "")}` }));

    expect(await screen.findByRole("dialog", { name: VOID_MESSAGES.title })).toBeInTheDocument();
  });

  it("anular envía el motivo y la pestaña se relee", async () => {
    const { mock, user } = renderTab({
      handlers: {
        [`POST /payments/${VALID_PAYMENT_ID}/void`]: {
          status: 200,
          body: {
            id: VALID_PAYMENT_ID,
            membership_id: "11111111-1111-4111-8111-111111111111",
            member_id: MEMBER_ID,
            amount_cop: 60_000,
            method: "nequi",
            reference: "M12345678",
            paid_at: "2026-10-20T19:10:00Z",
            registered_by: "00000000-0000-4000-8000-000000000002",
            voided: true,
            voided_at: "2026-10-21T15:00:00Z",
            voided_by: "00000000-0000-4000-8000-000000000001",
            void_reason: "Error de digitación",
            created_at: "2026-10-20T19:10:00Z",
          },
        },
      },
    });
    const valid = (await bodyRows())[0] as HTMLElement;
    await user.click(within(valid).getByRole("button", { name: /^Anular el pago/ }));
    const dialog = await screen.findByRole("dialog", { name: VOID_MESSAGES.title });

    await user.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Error de digitación");
    await user.click(within(dialog).getByRole("button", { name: /^Anular/ }));

    await waitFor(() => {
      expect(mock.callsTo(`POST /payments/${VALID_PAYMENT_ID}/void`)).toHaveLength(1);
    });
    expect(mock.callsTo(`POST /payments/${VALID_PAYMENT_ID}/void`)[0]?.body).toEqual({ reason: "Error de digitación" });
    await waitFor(() => {
      expect(listCallsTo(mock, MEMBER_PAYMENTS_PATH).length).toBeGreaterThan(1);
    });
  });

  it("el coach no ve 'Anular' pero sí 'Registrar pago'", async () => {
    signInAs("coach");
    renderTab();
    await table();

    expect(screen.queryByRole("button", { name: /^Anular/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Registrar pago" })).toBeInTheDocument();
  });
});

describe("MemberPaymentsTab · estados", () => {
  it("vacío: 'Este socio no tiene pagos.' con Registrar pago", async () => {
    renderTab({ handlers: { [`GET ${MEMBER_PAYMENTS_PATH}`]: (call) => pageOf(call, []) } });

    expect(await screen.findByText("Este socio no tiene pagos.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Registrar pago" }).length).toBeGreaterThan(0);
  });

  it("vacío con 'Ocultar anulados': 'Este socio no tiene pagos válidos.'", async () => {
    renderTab({ handlers: { [`GET ${MEMBER_PAYMENTS_PATH}`]: (call) => pageOf(call, []) } }, `/socios/${MEMBER_ID}/pagos?voided=false`);

    expect(await screen.findByText("Este socio no tiene pagos válidos.")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Ocultar anulados" })).toBeChecked();
  });

  it("mientras carga lo anuncia", () => {
    renderTab({ handlers: { [`GET ${MEMBER_PAYMENTS_PATH}`]: () => new Promise(() => undefined) } });

    expect(screen.getByText("Cargando los pagos…")).toBeInTheDocument();
  });

  it("un error se explica con Reintentar, que vuelve a pedir", async () => {
    let fail = true;
    const { mock, user } = renderTab({
      handlers: { [`GET ${MEMBER_PAYMENTS_PATH}`]: (call) => (fail ? { status: 500, body: { error: { code: "internal_error", message: "x" } } } : pageOf(call, memberPayments())) },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar los pagos de este socio. Intenta de nuevo.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await table()).toBeInTheDocument();
    expect(listCallsTo(mock, MEMBER_PAYMENTS_PATH).length).toBeGreaterThanOrEqual(2);
  });

  it("un 404 dice que el socio no existe", async () => {
    renderTab({ handlers: { [`GET ${MEMBER_PAYMENTS_PATH}`]: { status: 404, body: { error: { code: "member_not_found", message: "x" } } } } });

    expect(await screen.findByRole("alert")).toHaveTextContent("No encontramos a este socio. Vuelve a la lista de socios.");
  });

  it("sin el socio de la ficha usa el :id de la ruta y no ofrece Registrar pago ni Anular", async () => {
    const { mock } = renderTab({ member: null, handlers: { [`GET ${MEMBER_PAYMENTS_PATH}`]: (call) => pageOf(call, [paymentRow({ member_id: MEMBER_ID })]) } });
    await table();

    expect(listCallsTo(mock, MEMBER_PAYMENTS_PATH)).toHaveLength(1);
    expect(screen.queryByRole("link", { name: "Registrar pago" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Anular/ })).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad (axe)", async () => {
    const { container } = renderTab();
    await table();

    expect(await axe(container)).toHaveNoViolations();
  });
});
