// S4A-F3 · US-109 (paso 122): los cuatro KPI de v0.1 de Inicio (Inicio.html) y la línea de pendientes
// de pago. Valores de GET /dashboard, enlaces a /socios con el estado y a /pagos con el mes, carga,
// error con "Reintentar" que vuelve a pedir, 429 con la espera y el KPI de ingresos del coach en
// "Solo administración" (S4A-D118: llega null; ni "$ 0" ni "Disponible en v0.x").
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { coachDashboardBody, dashboardBody, mockDashboard, ok, renderDashboard, serverError, tooMany } from "../../../test/dashboard";
import { signOutForTests } from "../../../test/session";
import { KpiGrid } from "./KpiGrid";

const SOURCE = import.meta.glob<string>("./KpiGrid.tsx", { query: "?raw", import: "default", eager: true });

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("KpiGrid", () => {
  it("muestra 120, 14, 9 y $ 3.250.000 con sus enlaces", async () => {
    mockDashboard(ok());
    renderDashboard(<KpiGrid />);

    const active = await screen.findByRole("link", { name: "Socios al día: 120" });
    expect(active).toHaveAttribute("href", "/socios?membership_status=active");
    expect(screen.getByRole("link", { name: "Por vencer: 14" })).toHaveAttribute("href", "/socios?membership_status=expiring");
    expect(screen.getByRole("link", { name: "Vencidos: 9" })).toHaveAttribute("href", "/socios?membership_status=expired");
    expect(screen.getByRole("link", { name: "Ingresos de octubre 2026: $ 3.250.000" })).toHaveAttribute("href", "/pagos?from=2026-10-01&to=2026-10-31");
  });

  it("la nota de Socios al día cuenta a todos los que tienen membresía (los cinco estados)", async () => {
    mockDashboard(ok());
    renderDashboard(<KpiGrid />);

    expect(await screen.findByText("de 148 con membresía")).toBeInTheDocument();
  });

  it("Por vencer pide atención con texto, no solo con color", async () => {
    mockDashboard(ok());
    renderDashboard(<KpiGrid />);

    const expiring = await screen.findByRole("link", { name: "Por vencer: 14" });
    expect(within(expiring).getByText("Renovar antes de que venzan")).toBeInTheDocument();
  });

  it("la línea de pendientes de pago lleva al chip Pendiente de pago (Q3)", async () => {
    mockDashboard(ok());
    renderDashboard(<KpiGrid />);

    const line = await screen.findByRole("link", { name: "3 socios con pago pendiente" });
    expect(line).toHaveAttribute("href", "/socios?membership_status=pending_payment");
  });

  it("un pendiente va en singular y cero no enlaza", async () => {
    mockDashboard(ok(dashboardBody({ members_pending_payment: 1 })));
    const first = renderDashboard(<KpiGrid />);
    expect(await screen.findByRole("link", { name: "1 socio con pago pendiente" })).toBeInTheDocument();
    first.unmount();

    mockDashboard(ok(dashboardBody({ members_pending_payment: 0 })));
    renderDashboard(<KpiGrid />);
    expect(await screen.findByText("Ningún socio con pago pendiente")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /pago pendiente/ })).not.toBeInTheDocument();
  });

  it("al coach le muestra Solo administración en ingresos, sin enlace, sin $ 0 ni Disponible en", async () => {
    mockDashboard(ok(coachDashboardBody()));
    renderDashboard(<KpiGrid />, "coach");

    const income = await screen.findByRole("group", { name: "Ingresos de octubre 2026" });
    expect(within(income).getByText("Solo administración")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Ingresos/ })).not.toBeInTheDocument();
    expect(screen.queryByText("$ 0")).not.toBeInTheDocument();
    expect(screen.queryByText(/Disponible en/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Socios al día: 120" })).toBeInTheDocument();
  });

  it("mientras carga, las cuatro tarjetas dicen Cargando", async () => {
    mockDashboard(() => new Promise(() => undefined));
    renderDashboard(<KpiGrid />);

    expect(await screen.findAllByText("Cargando")).toHaveLength(4);
    expect(screen.getByRole("region", { name: "Membresías e ingresos" })).toHaveAttribute("aria-busy", "true");
  });

  it("si falla, explica qué pasó y Reintentar vuelve a pedir", async () => {
    const api = mockDashboard(serverError, ok());
    renderDashboard(<KpiGrid />);

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar el tablero. Intenta de nuevo en un momento.");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("link", { name: "Socios al día: 120" })).toBeInTheDocument();
    expect(api.callsTo("GET /dashboard")).toHaveLength(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("un 429 dice cuánto esperar", async () => {
    mockDashboard(tooMany);
    renderDashboard(<KpiGrid />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Demasiadas consultas seguidas; espera 30 segundos y vuelve a intentarlo.");
  });

  it("una respuesta con forma inesperada es un error, nunca ceros", async () => {
    mockDashboard({ status: 200, body: { ...dashboardBody(), members_active: "120" } });
    renderDashboard(<KpiGrid />);

    expect(await screen.findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida");
    await waitFor(() => {
      expect(screen.queryByText("0")).not.toBeInTheDocument();
    });
  });

  it("el código nombra el DESIGN-GAP de la línea de pendientes (Q3) y de las notas del diseño", () => {
    const code = Object.values(SOURCE).join("\n");
    const gaps = code.split("\n").filter((line) => line.includes("DESIGN-GAP:")).join("\n");

    expect(gaps).toContain("pendientes de pago");
    expect(gaps).toContain("Vencen en 7 días");
    expect(code).not.toContain("dangerouslySetInnerHTML");
  });

  it("es accesible", async () => {
    mockDashboard(ok());
    const { container } = renderDashboard(<KpiGrid />);
    await screen.findByRole("link", { name: "Socios al día: 120" });
    expect(await axe(container)).toHaveNoViolations();
  });
});
