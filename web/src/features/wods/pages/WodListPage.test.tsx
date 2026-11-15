// S8-F2 · US-166 (front): /wods (WOD_Lista.html). Semana por ?semana=AAAA-Www, hoy resaltado, «+ Crear» a /wods/nuevo?date=,
// vista lista con «Solo benchmarks» y ?dia=hoy. Estados: carga, vacío, error con Reintentar.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { wodsPage, wodRow, WODS } from "../../../test/wods";
import WodListPage from "./WodListPage";

const NOW = new Date("2026-10-21T17:00:00Z");

function Where() {
  const location = useLocation();
  return <output data-testid="where">{`${location.pathname}${location.search}`}</output>;
}

function renderPage(handlers: Record<string, MockHandler> = {}, entry = "/wods") {
  const mock = mockApi({ "GET /wods": wodsPage(), ...handlers });
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter initialEntries={[entry]}>
          <WodListPage />
          <Where />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, user: userEvent.setup(), ...view };
}

const query = (calls: { url: string }[]) => new URL(calls[calls.length - 1]?.url ?? "", "http://apex.test").searchParams;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("WodListPage · semana", () => {
  it("pide la semana de hoy y pinta un día por columna con su WOD", async () => {
    const { mock } = renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "WODs" })).toBeInTheDocument();
    await screen.findByText("Fran");
    expect(query(mock.callsTo("GET /wods")).get("week")).toBe("2026-W43");
    expect(screen.getAllByRole("listitem", { name: /^(lun|mar|mié|jue|vie|sáb|dom)/i })).toHaveLength(7);
    expect(screen.getByRole("link", { name: /Fran/ })).toHaveAttribute("href", `/wods/${WODS.fran.id}`);
    expect(screen.getByText("Back Squat 5x5")).toBeInTheDocument();
  });

  it("resalta hoy y ofrece «+ Crear» en los días vacíos con la fecha", async () => {
    renderPage();
    await screen.findByText("Fran");
    const today = screen.getByRole("listitem", { name: /mié 21/i });
    expect(today).toHaveAttribute("aria-current", "date");
    const lunes = screen.getByRole("listitem", { name: /lun 19/i });
    expect(within(lunes).getByRole("link", { name: "+ Crear" })).toHaveAttribute("href", "/wods/nuevo?date=2026-10-19");
  });

  it("respeta ?semana= y navega a la anterior, la siguiente y hoy", async () => {
    const { user, mock } = renderPage({}, "/wods?semana=2026-W40");
    await screen.findByText("Semana del 28 de septiembre al 4 de octubre de 2026");
    expect(query(mock.callsTo("GET /wods")).get("week")).toBe("2026-W40");
    await user.click(screen.getByRole("button", { name: "Semana siguiente" }));
    expect(screen.getByTestId("where")).toHaveTextContent("semana=2026-W41");
    await user.click(screen.getByRole("button", { name: "Semana anterior" }));
    expect(screen.getByTestId("where")).toHaveTextContent("semana=2026-W40");
    await user.click(screen.getByRole("button", { name: "Hoy" }));
    expect(screen.getByTestId("where")).toHaveTextContent("semana=2026-W43");
  });

  it("una semana mal escrita cae en la semana actual", async () => {
    const { mock } = renderPage({}, "/wods?semana=hola");
    await screen.findByText("Fran");
    expect(query(mock.callsTo("GET /wods")).get("week")).toBe("2026-W43");
  });
});

describe("WodListPage · lista y estados", () => {
  it("la vista lista pagina en el servidor y filtra «Solo benchmarks» y búsqueda", async () => {
    const { user, mock } = renderPage({}, "/wods?vista=lista");
    await screen.findByText("Fran");
    expect(query(mock.callsTo("GET /wods")).get("limit")).toBe("25");
    expect(query(mock.callsTo("GET /wods")).get("week")).toBeNull();
    await user.click(screen.getByRole("checkbox", { name: "Solo benchmarks" }));
    await screen.findByText("Fran");
    expect(query(mock.callsTo("GET /wods")).get("benchmark")).toBe("true");
    await user.type(screen.getByRole("searchbox"), "fran");
    await vi.waitFor(() => {
      expect(query(mock.callsTo("GET /wods")).get("q")).toBe("fran");
    });
  });

  it("?dia=hoy lleva a la semana actual", async () => {
    const { mock } = renderPage({}, "/wods?dia=hoy&semana=2026-W30");
    await screen.findByText("Fran");
    expect(query(mock.callsTo("GET /wods")).get("week")).toBe("2026-W43");
  });

  it("sin WODs en la semana invita a crear el primero", async () => {
    renderPage({ "GET /wods": wodsPage([]) });
    expect(await screen.findByText(/Esta semana todavía no tiene WODs./)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "+ Crear" }).length).toBeGreaterThan(0);
  });

  it("error con Reintentar", async () => {
    const { user } = renderPage({ "GET /wods": apiError(500, "internal_error") });
    expect(await screen.findByText(/No pudimos cargar los WODs/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
  });

  it("un WOD con resultados lo dice y un benchmark lleva su insignia", async () => {
    renderPage({ "GET /wods": wodsPage([WODS.fran, wodRow("f2f2f2f2-0000-4000-8000-000000000009", { date: "2026-10-23", title: "Cindy", result_count: 6 })]) });
    expect(await screen.findByText("6 resultados")).toBeInTheDocument();
    expect(screen.getAllByText("Benchmark").length).toBeGreaterThan(0);
  });

  it("el socio no ve la pantalla", () => {
    signOutForTests();
    signInAs("member");
    renderPage();
    expect(screen.getByText(/No tienes permiso para ver los WODs/)).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderPage();
    await screen.findByText("Fran");
    expect(await axe(container)).toHaveNoViolations();
  });
});
