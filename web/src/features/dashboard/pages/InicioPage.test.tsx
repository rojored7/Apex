// S4A-F3 · US-108 a US-110 (paso 122; reemplaza la Inicio mínima de S2-D25): Inicio.html con
// GET /dashboard. Saludo con la parte local del correo y el día de Bogotá (DESIGN-GAP frente a
// "Hola, Ana": `display_name` llega en v0.2, S4A-D19), accesos del encabezado según el rol, los KPI,
// las tarjetas futuras y los últimos movimientos con una sola petición; el member va a /mi.
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { RouterProvider } from "react-router";
import { axe } from "vitest-axe";
import { ENABLED_FEATURES, type Feature } from "../../../config/features";
import { SessionRoleProvider } from "../../../core/auth/SessionRole";
import { createAppRouter } from "../../../routes";
import { NOW, coachDashboardBody, mockDashboard, ok, renderDashboard } from "../../../test/dashboard";
import { testQueryClient } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import InicioPage from "./InicioPage";

const SOURCE = import.meta.glob<string>("./InicioPage.tsx", { query: "?raw", import: "default", eager: true });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(NOW));
});

afterEach(() => {
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("InicioPage", () => {
  it("saluda con la parte local del correo y el día de Bogotá", async () => {
    mockDashboard(ok());
    renderDashboard(<InicioPage />);

    expect(await screen.findByRole("heading", { level: 1, name: "Hola, admin · martes 20 de octubre" })).toBeInTheDocument();
    expect(screen.queryByText(/llega en la próxima versión/)).not.toBeInTheDocument();
    expect(screen.queryByText("admin@apex.test")).not.toBeInTheDocument();
  });

  it("el día del saludo sale de `today` del api cuando llega", async () => {
    vi.setSystemTime(new Date("2026-10-21T04:59:00Z")); // 11:59 p. m. del 20 en Bogotá
    mockDashboard(ok(coachDashboardBody({ today: "2026-10-21" })));
    renderDashboard(<InicioPage />, "coach");

    expect(await screen.findByRole("heading", { level: 1, name: "Hola, coach · miércoles 21 de octubre" })).toBeInTheDocument();
  });

  it("pinta los KPI, las tarjetas futuras y los últimos movimientos con una sola petición", async () => {
    const api = mockDashboard(ok());
    renderDashboard(<InicioPage />);

    expect(await screen.findByRole("link", { name: "Socios al día: 120" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Membresías e ingresos" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Próximamente en Inicio" })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Últimos movimientos" })).getAllByRole("listitem")).toHaveLength(10);
    expect(api.callsTo("GET /dashboard")).toHaveLength(1);
  });

  it("el admin tiene Nuevo socio y Vender membresía en el encabezado", async () => {
    mockDashboard(ok());
    renderDashboard(<InicioPage />);

    await screen.findByRole("link", { name: "Socios al día: 120" });
    expect(screen.getByRole("link", { name: "+ Nuevo socio" })).toHaveAttribute("href", "/socios/nuevo");
    expect(screen.getByRole("link", { name: "Vender membresía" })).toHaveAttribute("href", "/membresias/vender");
  });

  it("el coach también vende y registra socios, y ve ingresos como Solo administración", async () => {
    mockDashboard(ok(coachDashboardBody()));
    renderDashboard(<InicioPage />, "coach");

    expect(await screen.findByText("Solo administración")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "+ Nuevo socio" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Vender membresía" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ver auditoría" })).not.toBeInTheDocument();
  });

  it("el member que abre / va a /mi y no pide el tablero", async () => {
    const api = mockDashboard(ok());
    signInAs("member");
    const enabled = new Set<Feature>([...ENABLED_FEATURES, "portal"]);
    const router = createAppRouter({ enabled, initialEntries: ["/"] });
    render(
      <QueryClientProvider client={testQueryClient()}>
        <SessionRoleProvider>
          <RouterProvider router={router} />
        </SessionRoleProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/mi");
    });
    expect(api.callsTo("GET /dashboard")).toHaveLength(0);
  });

  it("el código nombra el DESIGN-GAP del saludo y de los accesos que faltan", () => {
    const gaps = Object.values(SOURCE)
      .join("\n")
      .split("\n")
      .filter((line) => line.includes("DESIGN-GAP:"))
      .join("\n");

    expect(gaps).toContain("Hola, Ana");
    expect(gaps).toContain("Check-in");
  });

  it("es accesible", async () => {
    mockDashboard(ok());
    const { container } = renderDashboard(<InicioPage />);
    await screen.findByRole("link", { name: "Socios al día: 120" });
    expect(await axe(container)).toHaveNoViolations();
  });
});
