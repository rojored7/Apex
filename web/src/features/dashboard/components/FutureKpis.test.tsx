// S4A-F3 · US-109 (paso 122): las tarjetas de Inicio que llegan en versiones futuras (Hoy en el box,
// Asistencia de la semana, WOD de hoy). S5-F3: Por avisar hoy y Sin consentimiento ya tienen dato y
// viven en NotificationKpis. El api las manda en null y
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

// S7-F6: Hoy en el box y Asistencia de la semana viven en ClassesKpis.
const CARDS = [
  ["WOD de hoy", "Disponible en v0.5"],
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
    mockDashboard(ok(dashboardBody({ wod_today: { id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb01", title: "Helen", score_type: "time", is_benchmark: true } })));
    renderDashboard(<FutureKpis />);

    await screen.findByText("Helen");
    expect(within(screen.getByRole("group", { name: "WOD de hoy" })).getByText("Helen")).toBeInTheDocument();
    expect(screen.queryByText(/Disponible en/)).not.toBeInTheDocument();
  });

  it("tiene su sección con título", async () => {
    mockDashboard(ok());
    renderDashboard(<FutureKpis />);

    const region = await screen.findByRole("region", { name: "Próximamente en Inicio" });
    expect(within(region).getAllByRole("group")).toHaveLength(1);
  });

  it("S5-F3: ya no trae Por avisar hoy ni Sin autorización (viven en Avisos)", async () => {
    mockDashboard(ok());
    renderDashboard(<FutureKpis />);

    await screen.findByRole("group", { name: "WOD de hoy" });
    expect(screen.queryByRole("group", { name: "Hoy en el box" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Por avisar hoy" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Sin autorización" })).not.toBeInTheDocument();
  });

  it("si el tablero falla no inventa valores (el error lo explica KpiGrid)", async () => {
    mockDashboard(serverError);
    renderDashboard(<FutureKpis />);

    expect(await screen.findAllByText("No se pudo cargar")).toHaveLength(1);
    expect(screen.queryByText(/Disponible en/)).not.toBeInTheDocument();
  });

  it("el código nombra los DESIGN-GAP de las tarjetas futuras", () => {
    const gaps = Object.values(SOURCE)
      .join("\n")
      .split("\n")
      .filter((line) => line.includes("DESIGN-GAP:"))
      .join("\n");

    for (const topic of ["WOD de hoy"]) {
      expect(gaps).toContain(topic);
    }
  });

  it("es accesible", async () => {
    mockDashboard(ok());
    const { container } = renderDashboard(<FutureKpis />);
    await screen.findByText("Disponible en v0.5");
    expect(await axe(container)).toHaveNoViolations();
  });
});
