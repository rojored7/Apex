// S4A-F3 · US-109 (paso 122): las tarjetas de Inicio que llegan en versiones futuras (Hoy en el box,
// Asistencia de la semana, WOD de hoy, Por avisar hoy, Sin consentimiento). El api las manda en null y
// la tarjeta dice "Disponible en v0.x", nunca 0 (EP-12, S4A-D33); con valor, lo muestra.
import { screen, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { dashboardBody, mockDashboard, ok, renderDashboard, serverError } from "../../../test/dashboard";
import { signOutForTests } from "../../../test/session";
import { FutureKpis } from "./FutureKpis";

const SOURCE = import.meta.glob<string>("./FutureKpis.tsx", { query: "?raw", import: "default", eager: true });

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
});

const CARDS = [
  ["Hoy en el box", "Disponible en v0.4"],
  ["Asistencia de la semana", "Disponible en v0.4"],
  ["WOD de hoy", "Disponible en v0.5"],
  ["Por avisar hoy", "Disponible en v0.2"],
  ["Sin consentimiento", "Disponible en v0.2"],
] as const;

describe("FutureKpis", () => {
  it.each(CARDS)("%s en null dice %s y nunca 0", async (label, text) => {
    mockDashboard(ok());
    renderDashboard(<FutureKpis />);

    await screen.findAllByText(/^Disponible en/); // la carga también es un grupo con el mismo nombre
    const card = screen.getByRole("group", { name: label });
    expect(within(card).getByText(text)).toBeInTheDocument();
    expect(within(card).queryByText("0")).not.toBeInTheDocument();
  });

  it("con valor, lo muestra", async () => {
    mockDashboard(ok(dashboardBody({ sessions_today: 4, attendance_week: 1250, notifications_today: 0, members_without_consent: 7, wod_today: "Helen" })));
    renderDashboard(<FutureKpis />);

    await screen.findByText("Helen");
    expect(within(screen.getByRole("group", { name: "Hoy en el box" })).getByText("4")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Asistencia de la semana" })).getByText("1.250")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Por avisar hoy" })).getByText("0")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Sin consentimiento" })).getByText("7")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "WOD de hoy" })).getByText("Helen")).toBeInTheDocument();
    expect(screen.queryByText(/Disponible en/)).not.toBeInTheDocument();
  });

  it("tiene su sección con título", async () => {
    mockDashboard(ok());
    renderDashboard(<FutureKpis />);

    const region = await screen.findByRole("region", { name: "Próximamente en Inicio" });
    expect(within(region).getAllByRole("group")).toHaveLength(5);
  });

  it("si el tablero falla no inventa valores (el error lo explica KpiGrid)", async () => {
    mockDashboard(serverError);
    renderDashboard(<FutureKpis />);

    expect(await screen.findAllByText("No se pudo cargar")).toHaveLength(5);
    expect(screen.queryByText(/Disponible en/)).not.toBeInTheDocument();
  });

  it("el código nombra los DESIGN-GAP de las tarjetas futuras", () => {
    const gaps = Object.values(SOURCE)
      .join("\n")
      .split("\n")
      .filter((line) => line.includes("DESIGN-GAP:"))
      .join("\n");

    for (const topic of ["Hoy en el box", "Por avisar hoy", "Asistencia", "WOD de hoy"]) {
      expect(gaps).toContain(topic);
    }
  });

  it("es accesible", async () => {
    mockDashboard(ok());
    const { container } = renderDashboard(<FutureKpis />);
    await screen.findByRole("group", { name: "Hoy en el box" });
    expect(await axe(container)).toHaveNoViolations();
  });
});
