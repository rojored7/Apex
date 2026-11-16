// S8-V8b · US-172 (front): las sesiones del WOD se paginan en el servidor y por defecto se ven las próximas.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { mockApi, testQueryClient, type MockReply } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { WODS } from "../../../test/wods";
import { WodSessions, SESSIONS_EMPTY, SESSIONS_EMPTY_UPCOMING } from "./WodSessions";

const PATH = `GET /class-sessions`;

function sessionRow(n: number): Record<string, unknown> {
  return {
    id: `d2d2d2d2-0000-4000-8000-${String(n).padStart(12, "0")}`,
    slot_id: null,
    session_date: "2026-11-15",
    starts_at: "2026-11-15T12:00:00Z",
    duration_min: 60,
    capacity: 20,
    coach_id: null,
    coach_name: "Carlos",
    name: `Clase ${String(n)}`,
    status: "scheduled",
    attendance_count: 3,
    cancel_reason: null,
    cancelled_at: null,
    wod_id: WODS.fran.id,
    effective_wod_id: WODS.fran.id,
  };
}

const page = (rows: number[], total: number, limit = 25, offset = 0): MockReply => ({ status: 200, body: { items: rows.map(sessionRow), total, limit, offset } });

function renderSessions(reply: MockReply | ((url: URL) => MockReply)) {
  const api = mockApi({ [PATH]: typeof reply === "function" ? (call) => reply(new URL(call.url, "http://apex.test")) : reply });
  render(
    <QueryClientProvider client={testQueryClient()}>
      <MemoryRouter>
        <WodSessions wodId={WODS.fran.id} canRecord />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return api;
}

const lastQuery = (api: ReturnType<typeof mockApi>): URLSearchParams => new URL(api.callsTo(PATH).at(-1)?.url ?? "", "http://apex.test").searchParams;

beforeEach(() => {
  signInAs("admin");
  // 2026-11-15T15:00Z = 10:00 en Bogotá (UTC-5): hoy es 2026-11-15.
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-15T15:00:00Z") });
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("WodSessions", () => {
  it("al inicio pide las próximas: limit=25, offset=0 y from=hoy en Bogotá", async () => {
    const api = renderSessions(page([1, 2], 60));
    await screen.findByText(/Clase 1/);
    const q = lastQuery(api);
    expect(q.get("limit")).toBe("25");
    expect(q.get("offset")).toBe("0");
    expect(q.get("from")).toBe("2026-11-15");
    // hoy + 61 días = 2027-01-15 (noviembre +15, diciembre +31, enero +15): el api topa la ventana en 62 días.
    expect(q.get("to")).toBe("2027-01-15");
    expect(q.get("wod_id")).toBe(WODS.fran.id);
    expect(screen.getByRole("button", { name: /Próximas/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/1 a 25 de 60|1–25 de 60|1-25 de 60/)).toBeInTheDocument();
  });

  it("pasar a la página 2 pide offset=25", async () => {
    const api = renderSessions(page([1], 60));
    await screen.findByText(/Clase 1/);
    fireEvent.click(screen.getByRole("button", { name: /Siguiente/ }));
    await vi.waitFor(() => {
      expect(lastQuery(api).get("offset")).toBe("25");
    });
    expect(lastQuery(api).get("from")).toBe("2026-11-15");
  });

  it("Todas quita from y vuelve a la página 1", async () => {
    const api = renderSessions(page([1], 60));
    await screen.findByText(/Clase 1/);
    fireEvent.click(screen.getByRole("button", { name: /Siguiente/ }));
    await vi.waitFor(() => {
      expect(lastQuery(api).get("offset")).toBe("25");
    });
    fireEvent.click(screen.getByRole("button", { name: /Todas/ }));
    await vi.waitFor(() => {
      expect(lastQuery(api).get("from")).toBeNull();
    });
    expect(lastQuery(api).get("to")).toBeNull();
    expect(lastQuery(api).get("offset")).toBe("0");
    expect(screen.getByRole("button", { name: /Todas/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("vacío en Próximas y vacío en Todas dicen cosas distintas", async () => {
    renderSessions((url) => (url.searchParams.has("from") ? page([], 0) : page([], 0)));
    expect(await screen.findByText(SESSIONS_EMPTY_UPCOMING)).toBeInTheDocument();
    expect(SESSIONS_EMPTY_UPCOMING).toBe("No hay clases próximas con este WOD.");
    fireEvent.click(screen.getByRole("button", { name: /Todas/ }));
    expect(await screen.findByText(SESSIONS_EMPTY)).toBeInTheDocument();
  });
});
