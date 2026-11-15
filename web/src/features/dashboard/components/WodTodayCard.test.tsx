// S8-F5 · US-174 (front): la tarjeta «WOD de hoy» de Inicio. Sale de GET /dashboard (`wod_today`, objeto o null) y comparte la
// consulta ["dashboard"] con el resto de Inicio. «Registrar resultados» lleva a la próxima sesión viva de hoy.
import { screen, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { dashboardBody, mockDashboard, NOW, ok, renderDashboard, serverError } from "../../../test/dashboard";
import { signOutForTests } from "../../../test/session";
import { WodTodayCard } from "./WodTodayCard";

const WOD_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb01";
const NEXT_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccc02";
const PAST_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccc01";
const WOD = { id: WOD_ID, title: "Helen", score_type: "time", is_benchmark: true } as const;

const session = (id: string, startsAt: string, status: "scheduled" | "done" | "cancelled" = "scheduled") => ({
  id,
  starts_at: startsAt,
  coach_name: "Ana",
  capacity: 15,
  attendance_count: 4,
  duration_min: 60,
  status,
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: new Date(NOW) });
});

afterEach(() => {
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("WodTodayCard", () => {
  it("con WOD muestra título, tipo y «Benchmark», y «Ver» lleva a su detalle", async () => {
    mockDashboard(ok(dashboardBody({ wod_today: WOD })));
    renderDashboard(<WodTodayCard />);

    await screen.findByText("Helen");
    const card = screen.getByRole("group", { name: "WOD de hoy" });
    expect(within(card).getByText("Helen")).toBeInTheDocument();
    expect(within(card).getByText("Por tiempo")).toBeInTheDocument();
    expect(within(card).getByText("Benchmark")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Ver" })).toHaveAttribute("href", `/wods/${WOD_ID}`);
  });

  it("«Registrar resultados» va a la próxima sesión viva de hoy y salta las terminadas y las canceladas", async () => {
    mockDashboard(
      ok(
        dashboardBody({
          wod_today: WOD,
          sessions_today: [session(PAST_ID, "2026-10-20T11:00:00Z", "done"), session("cccccccc-cccc-4ccc-8ccc-cccccccccc03", "2026-10-20T20:00:00Z", "cancelled"), session(NEXT_ID, "2026-10-20T22:00:00Z")],
        }),
      ),
    );
    renderDashboard(<WodTodayCard />);

    expect(await screen.findByRole("link", { name: "Registrar resultados" })).toHaveAttribute("href", `/clases/${NEXT_ID}/resultados`);
  });

  it("sin sesión viva hoy no ofrece «Registrar resultados» y lo explica", async () => {
    mockDashboard(ok(dashboardBody({ wod_today: WOD, sessions_today: [session(PAST_ID, "2026-10-20T11:00:00Z", "done")] })));
    renderDashboard(<WodTodayCard />);

    await screen.findByText("Helen");
    expect(screen.queryByRole("link", { name: "Registrar resultados" })).not.toBeInTheDocument();
    expect(screen.getByText("No quedan clases por registrar hoy.")).toBeInTheDocument();
  });

  it("un WOD que no registra marca (score_type none) no ofrece «Registrar resultados»", async () => {
    mockDashboard(ok(dashboardBody({ wod_today: { ...WOD, score_type: "none", is_benchmark: false }, sessions_today: [session(NEXT_ID, "2026-10-20T22:00:00Z")] })));
    renderDashboard(<WodTodayCard />);

    await screen.findByText("Helen");
    expect(screen.queryByRole("link", { name: "Registrar resultados" })).not.toBeInTheDocument();
    expect(screen.queryByText("Benchmark")).not.toBeInTheDocument();
  });

  it("sin WOD hoy lo dice y guía a crearlo con la fecha de hoy", async () => {
    mockDashboard(ok(dashboardBody({ wod_today: null })));
    renderDashboard(<WodTodayCard />);

    expect(await screen.findByText("Hoy no hay WOD publicado.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Crear el WOD de hoy" })).toHaveAttribute("href", "/wods/nuevo?date=2026-10-20");
  });

  it("mientras carga muestra un estado de carga y con error dice «No se pudo cargar»", async () => {
    mockDashboard(serverError);
    renderDashboard(<WodTodayCard />);

    expect(screen.getByRole("group", { name: "WOD de hoy" })).toHaveAttribute("aria-busy", "true");
    expect(await screen.findByText("No se pudo cargar")).toBeInTheDocument();
  });

  it("el coach también la ve", async () => {
    mockDashboard(ok(dashboardBody({ wod_today: WOD })));
    renderDashboard(<WodTodayCard />, "coach");

    expect(await screen.findByText("Helen")).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    mockDashboard(ok(dashboardBody({ wod_today: WOD, sessions_today: [session(NEXT_ID, "2026-10-20T22:00:00Z")] })));
    const { container } = renderDashboard(<WodTodayCard />);
    await screen.findByText("Helen");

    expect(await axe(container)).toHaveNoViolations();
  });
});
