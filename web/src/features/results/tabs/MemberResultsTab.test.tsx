// S8-F5 · US-173 (front): pestaña Resultados de la ficha (/socios/:id/resultados), admin y coach. Ruta hija de /socios/:id (S3-D65):
// la ficha la pinta en su <Outlet />. Lista GET /members/{id}/results paginada en el servidor.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { ROUTE_TABLE } from "../../../config/routeTable";
import { MEMBER_ID, pageOf, renderMemberTab } from "../../../test/memberTabs";
import { memberResultRow } from "../../../test/results";
import { setViewportWidth, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import MemberResultsTab from "./MemberResultsTab";

const LIST = `GET /members/${MEMBER_ID}/results`;

const ROWS = [
  memberResultRow(1, { wod_title: "Helen", seconds: 702, level: "rx", source: "kiosk" }),
  memberResultRow(2, { id: "e1e1e1e1-0000-4000-8000-000000000002", wod_id: "f2f2f2f2-0000-4000-8000-0000000000bb", wod_title: "Cindy", score_type: "rounds_reps", seconds: null, rounds: 14, reps: 3, level: "scaled", wod_date: "2026-10-18", status: "pending", source: "desk", is_benchmark: true }),
  memberResultRow(3, { id: "e1e1e1e1-0000-4000-8000-000000000003", wod_id: "f2f2f2f2-0000-4000-8000-0000000000cc", wod_title: "Fran", seconds: null, reps: 18, capped: true, level: "rx_plus", wod_date: "2026-10-15" }),
];

const rows =
  (items: readonly unknown[], total = items.length): MockHandler =>
  (call) =>
    pageOf(call, items, total);

const renderTab = (handlers: Record<string, MockHandler> = {}, entry?: string) => renderMemberTab(MemberResultsTab, "resultados", entry, { handlers: { [LIST]: rows(ROWS), ...handlers } });
const table = () => screen.getByRole("table", { name: "Resultados del socio" });

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("MemberResultsTab · registro (S3-D65)", () => {
  it("es una hija de /socios/:id de la feature results, con carga diferida y acceso results.record", () => {
    const route = ROUTE_TABLE.find((r) => r.path === "/socios/:id/resultados");

    expect(route).toMatchObject({ parent: "/socios/:id", feature: "results", access: "results.record", layout: "panel" });
    expect(typeof route?.load).toBe("function");
  });
});

describe("MemberResultsTab · contenido", () => {
  it("pide la lista con limit 25 y offset 0 y muestra WOD, fecha, nivel, marca y dónde se registró", async () => {
    const { mock } = renderTab();

    await screen.findByText("Cindy");
    const params = new URL(mock.callsTo(LIST)[0]?.url ?? "", "http://apex.test").searchParams;
    expect(params.get("limit")).toBe("25");
    expect(params.get("offset")).toBe("0");
    expect(params.has("benchmark")).toBe(false);
    const body = within(table());
    expect(body.getByRole("columnheader", { name: "WOD" })).toBeInTheDocument();
    expect(body.getByText("11:42")).toBeInTheDocument();
    expect(body.getByText("14 + 3")).toBeInTheDocument();
    expect(body.getByText("DNF · 18 reps")).toBeInTheDocument();
    expect(body.getByText("RX+")).toBeInTheDocument();
    expect(body.getByText("Escalado")).toBeInTheDocument();
  });

  it("marca «en tablet» o «en recepción» según la fuente y «Por validar» al pendiente", async () => {
    renderTab();

    await screen.findByText("Cindy");
    expect(within(table()).getAllByText("En tablet")).toHaveLength(2);
    expect(within(table()).getByText("En recepción")).toBeInTheDocument();
    const pendingRow = screen.getByText("Cindy").closest("tr");
    expect(within(pendingRow as HTMLElement).getByText("Por validar")).toBeInTheDocument();
  });

  it("el título del WOD lleva a su detalle", async () => {
    renderTab();

    expect(await screen.findByRole("link", { name: "Helen" })).toHaveAttribute("href", "/wods/f2f2f2f2-0000-4000-8000-0000000000aa");
  });

  it("«Solo benchmarks» pide benchmark=true y vuelve a la primera página", async () => {
    const { mock, user } = renderTab();
    await screen.findByText("Cindy");

    await user.click(screen.getByRole("checkbox", { name: "Solo benchmarks" }));

    await waitFor(() => {
      const last = mock.callsTo(LIST).at(-1);
      expect(new URL(last?.url ?? "", "http://apex.test").searchParams.get("benchmark")).toBe("true");
    });
  });

  it("sin resultados guía al detalle de los WODs y no dice «No hay datos»", async () => {
    renderTab({ [LIST]: rows([]) });

    expect(await screen.findByText(/Todavía no tiene resultados/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver los WODs" })).toHaveAttribute("href", "/wods");
  });

  it("con un error de lectura dice qué hacer y Reintentar vuelve a pedir", async () => {
    let calls = 0;
    const { user } = renderTab({
      [LIST]: (call) => {
        calls += 1;
        return calls === 1 ? { status: 500, body: { error: { code: "internal_error", message: "x" } } } : pageOf(call, ROWS);
      },
    });

    expect(await screen.findByText("No pudimos cargar los resultados del socio. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Cindy")).toBeInTheDocument();
  });

  it("un 404 dice que el socio ya no existe", async () => {
    renderTab({ [LIST]: { status: 404, body: { error: { code: "not_found", message: "x" } } } });

    expect(await screen.findByText(/Este socio ya no existe/)).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderTab();
    await screen.findByText("Cindy");

    expect(await axe(container)).toHaveNoViolations();
  });
});
