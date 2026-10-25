// S3-F7 · US-093 (front): pestaña Membresías de la ficha (/socios/:id/membresias), admin y coach.
// - GET /members/{id}/memberships (B11): tarjeta de la vigente (plan, vigencia, días restantes,
//   clases, precio, pagado y saldo, StatusTag, congelaciones) y de la futura ("Pendiente de pago",
//   DESIGN-GAP Q3), e historial paginado con todas (también las anuladas, con su motivo).
// - Botones de membershipActions: Renovar (/membresias/vender?socio=&renovar=1), Vender, Registrar
//   saldo (?pago=<membresía>, S3-D65), Congelar (FreezeModal) y Anular (CancelMembershipModal, solo
//   admin); nada para un socio dado de baja.
// - Vacío "Este socio no tiene membresías." con "Vender"; carga; error con "Reintentar".
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { formatDate } from "../../../core/i18n/format";
import {
  CURRENT_ID,
  dayFromToday,
  DELETED_TAB_MEMBER,
  FUTURE_ID,
  listCallsTo,
  MEMBER_ID,
  MEMBER_MEMBERSHIPS_PATH,
  memberMembership,
  memberMemberships,
  pageOf,
  renderMemberTab,
} from "../../../test/memberTabs";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import MemberMembershipsTab from "./MemberMembershipsTab";
import { cancelTitle } from "./CancelMembershipModal";
import { freezeTitle } from "./FreezeModal";

const renderTab = (options: Parameters<typeof renderMemberTab>[3] = {}, entry?: string) => renderMemberTab(MemberMembershipsTab, "membresias", entry, options);
const card = (name: string): Promise<HTMLElement> => screen.findByRole("region", { name });
const history = (): Promise<HTMLElement> => screen.findByRole("region", { name: "Historial de membresías" });
const range = (start: string, end: string): string => `${formatDate(start)} – ${formatDate(end)}`;

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("MemberMembershipsTab · tarjetas", () => {
  it("la vigente 'Por vencer': plan, vigencia, días restantes, precio, pagado, saldo y congelaciones", async () => {
    const { mock } = renderTab();
    const current = await card("Membresía vigente");

    expect(within(current).getByText("Mensual")).toBeInTheDocument();
    expect(within(current).getByText("Por vencer")).toBeInTheDocument();
    expect(within(current).getByText(range(dayFromToday(-22), dayFromToday(8)))).toBeInTheDocument();
    expect(within(current).getByText("Quedan 8 días")).toBeInTheDocument();
    const value = (label: string): string | null => within(current).getByText(label, { selector: "dt" }).nextElementSibling?.textContent ?? null;
    expect(value("Precio")).toBe("$ 120.000");
    expect(value("Pagado")).toBe("$ 60.000");
    expect(value("Saldo")).toBe("$ 60.000");
    expect(within(current).queryByText("Clases", { selector: "dt" })).not.toBeInTheDocument();
    expect(value("Congelaciones")).toBe(`Del ${formatDate(dayFromToday(-15))} al ${formatDate(dayFromToday(-11))} · 5 días`);
    const call = listCallsTo(mock, MEMBER_MEMBERSHIPS_PATH)[0];
    expect(call?.get("limit")).toBe("25");
    expect(call?.get("offset")).toBe("0");
  });

  it("la futura dice 'Pendiente de pago' y cuándo empieza (DESIGN-GAP: el diseño solo dibuja la vigente)", async () => {
    renderTab();
    const future = await card("Próxima membresía");

    expect(within(future).getByText("Trimestral")).toBeInTheDocument();
    expect(within(future).getByText("Pendiente de pago")).toBeInTheDocument();
    expect(within(future).getByText(`Empieza el ${formatDate(dayFromToday(9))}`)).toBeInTheDocument();
  });

  it("un plan de clases muestra las clases restantes y sin congelaciones lo dice", async () => {
    renderTab({
      handlers: { [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: (call) => pageOf(call, [memberMembership({ plan_name: "12 clases", classes_total: 12, classes_remaining: 2, freezes: [] })]) },
    });
    const current = await card("Membresía vigente");
    const value = (label: string): string | null => within(current).getByText(label, { selector: "dt" }).nextElementSibling?.textContent ?? null;

    expect(value("Clases")).toBe("2 de 12");
    expect(value("Congelaciones")).toBe("Sin congelaciones");
  });

  it("sin vigente ni futura lo dice y no pinta tarjetas", async () => {
    renderTab({ handlers: { [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: (call) => pageOf(call, memberMemberships().slice(2)) } });

    expect(await screen.findByText("Este socio no tiene una membresía vigente.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Membresía vigente" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Próxima membresía" })).not.toBeInTheDocument();
  });
});

describe("MemberMembershipsTab · historial", () => {
  it("lista todas en el orden del api, la anulada con su estado y su motivo", async () => {
    renderTab();
    const table = await history();
    const rows = within(table).getAllByRole("row").slice(1);

    expect(rows.map((row) => within(row).getAllByRole("cell")[0]?.textContent)).toEqual(["Trimestral · $ 320.000", "Mensual · $ 120.000", "Mensual · $ 120.000", "12 clases · $ 110.000"]);
    const cancelled = rows[3] as HTMLElement;
    expect(within(cancelled).getByText("Cancelado")).toBeInTheDocument();
    expect(within(cancelled).getByText("Motivo: Error de venta")).toBeInTheDocument();
    expect(within(cancelled).getByText("12 de 12")).toBeInTheDocument();
    expect(within(rows[2] as HTMLElement).getByText("Vencido")).toBeInTheDocument();
    expect(within(rows[2] as HTMLElement).getByText("$ 120.000 · pagado")).toBeInTheDocument();
    // La fila no lleva a otra pantalla: dentro de la ficha no hay enlace en la primera columna.
    expect(within(table).queryAllByRole("link")).toHaveLength(0);
  });

  it("pagina en el servidor: la página 2 pide offset 25 y las tarjetas siguen con la primera", async () => {
    const rows = memberMemberships();
    const { mock, user } = renderTab({
      handlers: {
        [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: (call) => {
          const offset = Number(new URL(call.url, "http://apex.test").searchParams.get("offset"));
          return pageOf(call, offset === 0 ? rows : [memberMembership({ id: "99999999-0000-4000-8000-000000000001", status: "expired", plan_name: "Anual" })], 26);
        },
      },
    });
    await history();

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));

    await waitFor(() => {
      expect(listCallsTo(mock, MEMBER_MEMBERSHIPS_PATH).map((p) => p.get("offset"))).toEqual(["0", "25"]);
    });
    expect(await within(await history()).findByText("Anual · $ 120.000")).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("offset=25");
    expect(within(await card("Membresía vigente")).getByText("Mensual")).toBeInTheDocument();
  });
});

describe("MemberMembershipsTab · acciones (membershipActions)", () => {
  it("admin con vigente y futura: Registrar saldo, Congelar y Anular en las tarjetas; sin Renovar ni Vender", async () => {
    renderTab();
    const current = await card("Membresía vigente");
    const future = await card("Próxima membresía");

    expect(within(current).getByRole("link", { name: "Registrar saldo de la membresía Mensual" })).toHaveAttribute("href", `/socios/${MEMBER_ID}/membresias?pago=${CURRENT_ID}`);
    expect(within(current).getByRole("button", { name: "Congelar la membresía Mensual" })).toBeInTheDocument();
    expect(within(current).getByRole("button", { name: "Anular la membresía Mensual" })).toBeInTheDocument();
    expect(within(future).getByRole("link", { name: "Registrar saldo de la membresía Trimestral" })).toHaveAttribute("href", `/socios/${MEMBER_ID}/membresias?pago=${FUTURE_ID}`);
    expect(within(future).queryByRole("button", { name: /Congelar/ })).not.toBeInTheDocument();
    expect(within(future).getByRole("button", { name: "Anular la membresía Trimestral" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Renovar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Vender membresía" })).not.toBeInTheDocument();
  });

  it("el coach no ve Anular ni en la vigente ni en la futura", async () => {
    signInAs("coach");
    renderTab();
    const current = await card("Membresía vigente");

    expect(within(current).getByRole("button", { name: "Congelar la membresía Mensual" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Anular/ })).not.toBeInTheDocument();
  });

  it("vigente sin futura: Renovar lleva a la venta con el socio y renovar=1", async () => {
    const { user } = renderTab({ handlers: { [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: (call) => pageOf(call, memberMemberships().slice(1)) } });
    const renew = await screen.findByRole("link", { name: "Renovar" });

    expect(renew).toHaveAttribute("href", `/membresias/vender?socio=${MEMBER_ID}&renovar=1`);
    expect(screen.queryByRole("link", { name: "Vender membresía" })).not.toBeInTheDocument();
    await user.click(renew);
    expect(await screen.findByRole("heading", { name: "Vender membresía" })).toBeInTheDocument();
  });

  it("solo vencidas: Renovar y Vender membresía (con el socio fijo)", async () => {
    renderTab({ handlers: { [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: (call) => pageOf(call, memberMemberships().slice(2)) } });

    expect(await screen.findByRole("link", { name: "Renovar" })).toHaveAttribute("href", `/membresias/vender?socio=${MEMBER_ID}&renovar=1`);
    expect(screen.getByRole("link", { name: "Vender membresía" })).toHaveAttribute("href", `/membresias/vender?socio=${MEMBER_ID}`);
  });

  it("Congelar abre FreezeModal de esa membresía; al congelar avisa con el fin nuevo y relee la pestaña", async () => {
    const { mock, user } = renderTab({
      handlers: { [`POST /memberships/${CURRENT_ID}/freeze`]: { status: 200, body: memberMembership({ end_date: dayFromToday(18), status: "frozen" }) } },
    });
    await user.click(within(await card("Membresía vigente")).getByRole("button", { name: "Congelar la membresía Mensual" }));
    const dialog = await screen.findByRole("dialog", { name: freezeTitle("Laura Gómez") });

    fireEvent.change(within(dialog).getByLabelText(/^Hasta/), { target: { value: dayFromToday(9) } });
    await user.click(within(dialog).getByRole("button", { name: "Congelar" }));

    const notice = await screen.findByText(`Membresía Mensual congelada. Ahora termina el ${formatDate(dayFromToday(18))}.`);
    // Revisión S3-F7: el foco queda en el aviso, no en el botón que abrió el modal.
    await waitFor(() => {
      expect(notice).toHaveFocus();
    });
    expect(mock.callsTo(`POST /memberships/${CURRENT_ID}/freeze`)).toHaveLength(1);
    await waitFor(() => {
      expect(listCallsTo(mock, MEMBER_MEMBERSHIPS_PATH).length).toBeGreaterThan(1);
    });
  });

  it("Anular abre CancelMembershipModal de esa membresía (solo admin)", async () => {
    const { user } = renderTab();
    await user.click(within(await card("Próxima membresía")).getByRole("button", { name: "Anular la membresía Trimestral" }));

    expect(await screen.findByRole("dialog", { name: cancelTitle("Laura Gómez") })).toBeInTheDocument();
  });

  it("un socio dado de baja ve sus membresías sin ningún botón", async () => {
    renderTab({ member: DELETED_TAB_MEMBER, handlers: { [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: (call) => pageOf(call, memberMemberships().slice(1)) } });
    const current = await card("Membresía vigente");

    expect(within(current).queryAllByRole("button")).toHaveLength(0);
    expect(within(current).queryAllByRole("link")).toHaveLength(0);
    expect(screen.queryByRole("link", { name: "Renovar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Vender membresía" })).not.toBeInTheDocument();
  });
});

describe("MemberMembershipsTab · estados", () => {
  it("vacío: 'Este socio no tiene membresías.' con Vender (venta con el socio fijo)", async () => {
    renderTab({ handlers: { [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: (call) => pageOf(call, []) } });

    expect(await screen.findByText("Este socio no tiene membresías.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Vender" })).toHaveAttribute("href", `/membresias/vender?socio=${MEMBER_ID}`);
    expect(screen.queryByRole("region", { name: "Historial de membresías" })).not.toBeInTheDocument();
  });

  it("vacío de un dado de baja: sin Vender", async () => {
    renderTab({ member: DELETED_TAB_MEMBER, handlers: { [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: (call) => pageOf(call, []) } });

    expect(await screen.findByText("Este socio no tiene membresías.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Vender" })).not.toBeInTheDocument();
  });

  it("mientras carga lo anuncia", () => {
    renderTab({ handlers: { [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: () => new Promise(() => undefined) } });

    expect(screen.getByText("Cargando las membresías…")).toBeInTheDocument();
  });

  it("un error se explica con Reintentar, que vuelve a pedir", async () => {
    let fail = true;
    const { mock, user } = renderTab({
      handlers: {
        [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: (call) => (fail ? { status: 500, body: { error: { code: "internal_error", message: "x" } } } : pageOf(call, memberMemberships())),
      },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar las membresías de este socio. Intenta de nuevo.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await card("Membresía vigente")).toBeInTheDocument();
    expect(listCallsTo(mock, MEMBER_MEMBERSHIPS_PATH).length).toBeGreaterThanOrEqual(2);
  });

  it("revisión S3-F7 (M2): una relectura fallida en la página 1 avisa una sola vez y deja las tarjetas", async () => {
    let fail = false;
    const { queryClient } = renderTab({
      handlers: {
        [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: (call) => (fail ? { status: 500, body: { error: { code: "internal_error", message: "x" } } } : pageOf(call, memberMemberships())),
      },
    });
    await card("Membresía vigente");

    fail = true;
    await queryClient.invalidateQueries({ queryKey: ["memberships"] });

    await waitFor(() => {
      expect(screen.getAllByRole("alert")).toHaveLength(1);
    });
    expect(screen.getByRole("region", { name: "Membresía vigente" })).toBeInTheDocument();
  });

  it("un 404 dice que el socio no existe", async () => {
    renderTab({ handlers: { [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: { status: 404, body: { error: { code: "member_not_found", message: "x" } } } } });

    expect(await screen.findByRole("alert")).toHaveTextContent("No encontramos a este socio. Vuelve a la lista de socios.");
  });

  it("sin el socio de la ficha usa el :id de la ruta y no muestra botones", async () => {
    const { mock } = renderTab({ member: null });

    expect(await card("Membresía vigente")).toBeInTheDocument();
    expect(listCallsTo(mock, MEMBER_MEMBERSHIPS_PATH)).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /^Congelar/ })).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad (axe) con tarjetas e historial", async () => {
    const { container } = renderTab();
    await card("Membresía vigente");
    await history();

    expect(await axe(container)).toHaveNoViolations();
  });
});
