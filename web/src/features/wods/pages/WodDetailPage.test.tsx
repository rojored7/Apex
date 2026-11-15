// S8-F3 · US-171 y US-172 (front): /wods/:id (WOD_Detalle.html). Filtros RX, RX+, Escalado, Mujeres y Hombres hacia el servidor,
// «Todos los resultados» con `include_superseded`, anular solo el admin (S8-D46 b), Historial solo con `audit.view` (E5),
// sesiones del WOD, y estados de carga, error y permiso.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { auditPage, boardPage, resultsPage, sessionsOfWod, wodFull, WODS } from "../../../test/wods";
import WodDetailPage from "./WodDetailPage";

const WOD_ID = WODS.fran.id;

function renderPage(handlers: Record<string, MockHandler> = {}, entry = `/wods/${WOD_ID}`) {
  const mock = mockApi({
    [`GET /wods/${WOD_ID}`]: { status: 200, body: wodFull(WODS.fran, { result_count: 4 }) },
    [`GET /wods/${WOD_ID}/leaderboard`]: boardPage(),
    [`GET /wods/${WOD_ID}/results`]: resultsPage(),
    "GET /class-sessions": sessionsOfWod(),
    "GET /audit": auditPage(),
    ...handlers,
  });
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/wods/:id" element={<WodDetailPage />} />
          </Routes>
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, user: userEvent.setup(), ...view };
}

const lastQuery = (calls: { url: string }[]) => new URL(calls[calls.length - 1]?.url ?? "", "http://apex.test").searchParams;

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("WodDetailPage", () => {
  it("muestra el WOD, el leaderboard y las sesiones que lo usan", async () => {
    const { mock } = renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Fran" })).toBeInTheDocument();
    expect(screen.getByText(/21-15-9 Thruster/)).toBeInTheDocument();
    expect(await screen.findByText("Valentina R.")).toBeInTheDocument();
    expect(screen.getByText("9:58")).toBeInTheDocument();
    expect(mock.callsTo("GET /class-sessions")).toHaveLength(1);
    expect(lastQuery(mock.callsTo("GET /class-sessions")).get("wod_id")).toBe(WOD_ID);
    const link = await screen.findByRole("link", { name: "Registrar resultados" });
    expect(link).toHaveAttribute("href", "/clases/d2d2d2d2-0000-4000-8000-000000000001/resultados");
  });

  it("los chips de nivel y sexo piden el filtro al servidor", async () => {
    const { user, mock } = renderPage();
    await screen.findByText("Valentina R.");
    await user.click(screen.getByRole("radio", { name: "RX+" }));
    await user.click(screen.getByRole("radio", { name: "Mujeres" }));
    await screen.findByText("Valentina R.");
    const query = lastQuery(mock.callsTo(`GET /wods/${WOD_ID}/leaderboard`));
    expect(query.get("level")).toBe("rx_plus");
    expect(query.get("sex")).toBe("f");
    await user.click(screen.getByRole("radio", { name: "Todos los niveles" }));
    await screen.findByText("Valentina R.");
    expect(lastQuery(mock.callsTo(`GET /wods/${WOD_ID}/leaderboard`)).has("level")).toBe(false);
  });

  it("Todos los resultados: pide include_superseded al marcar la casilla y marca «en tablet»", async () => {
    const { user, mock } = renderPage({}, `/wods/${WOD_ID}?tab=todos`);
    expect(await screen.findByText(/Carlos · .* · en tablet/)).toBeInTheDocument();
    expect(lastQuery(mock.callsTo(`GET /wods/${WOD_ID}/results`)).has("include_superseded")).toBe(false);
    await user.click(screen.getByRole("checkbox", { name: "Incluir corregidos y anulados" }));
    await screen.findByText(/en tablet/);
    expect(lastQuery(mock.callsTo(`GET /wods/${WOD_ID}/results`)).get("include_superseded")).toBe("true");
  });

  it("el admin anula un resultado con motivo y no hay «mover a otra sesión»", async () => {
    const { user, mock } = renderPage({ "POST /results/c1c1c1c1-0000-4000-8000-000000000001/void": { status: 200, body: { id: "c1c1c1c1-0000-4000-8000-000000000001" } } }, `/wods/${WOD_ID}?tab=todos`);
    const buttons = await screen.findAllByRole("button", { name: "Anular" });
    expect(screen.queryByText(/otra sesión/i)).not.toBeInTheDocument();
    await user.click(buttons[0] as HTMLElement);
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Motivo/), "Socio equivocado");
    await user.click(within(dialog).getByRole("button", { name: "Anular resultado" }));
    await vi.waitFor(() => {
      expect(mock.callsTo("POST /results/c1c1c1c1-0000-4000-8000-000000000001/void")).toHaveLength(1);
    });
    expect(mock.callsTo("POST /results/c1c1c1c1-0000-4000-8000-000000000001/void")[0]?.body).toEqual({ reason: "Socio equivocado" });
  });

  it("un 409 al anular se explica dentro del modal", async () => {
    const { user } = renderPage({ "POST /results/c1c1c1c1-0000-4000-8000-000000000001/void": apiError(409, "result_already_voided") }, `/wods/${WOD_ID}?tab=todos`);
    await user.click((await screen.findAllByRole("button", { name: "Anular" }))[0] as HTMLElement);
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Motivo/), "Error");
    await user.click(within(dialog).getByRole("button", { name: "Anular resultado" }));
    expect(await within(dialog).findByText(/ya estaba anulado/)).toBeInTheDocument();
  });

  it("el coach no ve «Anular» ni la pestaña Historial", async () => {
    signInAs("coach");
    renderPage({}, `/wods/${WOD_ID}?tab=todos`);
    await screen.findByText(/en tablet/);
    expect(screen.queryByRole("button", { name: "Anular" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Historial" })).not.toBeInTheDocument();
  });

  it("el admin ve el Historial desde GET /audit con la tabla y el id del WOD", async () => {
    const { user, mock } = renderPage();
    await user.click(await screen.findByRole("tab", { name: "Historial" }));
    expect(await screen.findByText(/WOD · modificó/)).toBeInTheDocument();
    const query = lastQuery(mock.callsTo("GET /audit"));
    expect(query.get("table")).toBe("wods.wods");
    expect(query.get("record_id")).toBe(WOD_ID);
  });

  it("un WOD sin marca no ofrece resultados", async () => {
    renderPage({ [`GET /wods/${WOD_ID}`]: { status: 200, body: wodFull(WODS.fran, { score_type: "none" }) } });
    expect(await screen.findByText(/no registra resultados/)).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Leaderboard" })).not.toBeInTheDocument();
  });

  it("estados: error con Reintentar, WOD inexistente y leaderboard vacío", async () => {
    const { user, mock } = renderPage({ [`GET /wods/${WOD_ID}`]: apiError(500, "internal_error") });
    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar el WOD");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(mock.callsTo(`GET /wods/${WOD_ID}`).length).toBeGreaterThan(1);
    cleanup();
    renderPage({ [`GET /wods/${WOD_ID}`]: apiError(404, "wod_not_found") });
    expect(await screen.findByRole("alert")).toHaveTextContent("ya no existe");
    cleanup();
    renderPage({ [`GET /wods/${WOD_ID}/leaderboard`]: boardPage([]) });
    expect(await screen.findByText(/Todavía no hay resultados/)).toBeInTheDocument();
  });

  it("sin permiso no pide nada", () => {
    signOutForTests();
    signInAs("member");
    const { mock } = renderPage();
    expect(screen.getByText("No tienes permiso para ver los WODs")).toBeInTheDocument();
    expect(mock.calls).toHaveLength(0);
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderPage();
    await screen.findByText("Valentina R.");
    expect(await axe(container)).toHaveNoViolations();
  });
});
