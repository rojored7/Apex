// S5-F3 · US-132 (front): las tarjetas de avisos de Inicio (Inicio.html, "Por avisar hoy").
// - "Por avisar hoy": `notifications_today` con enlace a /avisos/hoy; en 0 dice "Nadie por avisar".
// - "Sin consentimiento": `members_without_consent` con su texto ("sin consentimiento no se avisa").
// - Ya no dicen "Disponible en v0.2": el dato llega con avisos (EP-14). Un null no inventa un cero.
import { screen, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { dashboardBody, mockDashboard, ok, renderDashboard, serverError } from "../../../test/dashboard";
import { signOutForTests } from "../../../test/session";
import { NotificationKpis } from "./NotificationKpis";

const SOURCE = import.meta.glob<string>("./NotificationKpis.tsx", { query: "?raw", import: "default", eager: true });

beforeEach(() => {
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("NotificationKpis", () => {
  it("'Por avisar hoy' muestra el conteo y lleva a /avisos/hoy", async () => {
    mockDashboard(ok(dashboardBody({ notifications_today: 9, members_without_consent: 2 })));
    renderDashboard(<NotificationKpis />);

    const link = await screen.findByRole("link", { name: "Por avisar hoy: 9" });
    expect(link).toHaveAttribute("href", "/avisos/hoy");
    expect(within(link).getByText("9")).toBeInTheDocument();
    expect(within(link).getByText("Abre la lista para avisar por WhatsApp u omitir.")).toBeInTheDocument();
  });

  it("con 0 dice 'Nadie por avisar' (y sigue siendo un enlace a la lista)", async () => {
    mockDashboard(ok(dashboardBody({ notifications_today: 0 })));
    renderDashboard(<NotificationKpis />);

    const link = await screen.findByRole("link", { name: "Por avisar hoy: 0" });
    expect(within(link).getByText("Nadie por avisar")).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/avisos/hoy");
  });

  it("'Sin consentimiento' muestra el conteo con su texto", async () => {
    mockDashboard(ok(dashboardBody({ members_without_consent: 2 })));
    renderDashboard(<NotificationKpis />);

    await screen.findByText("Socios que no autorizaron el uso de sus datos: no se les avisa.");
    expect(within(screen.getByRole("group", { name: "Sin consentimiento" })).getByText("2")).toBeInTheDocument();
  });

  it("con 0 sin consentimiento dice que todos autorizaron", async () => {
    mockDashboard(ok(dashboardBody({ members_without_consent: 0 })));
    renderDashboard(<NotificationKpis />);

    await screen.findByText("Todos los socios autorizaron el uso de sus datos.");
    expect(within(screen.getByRole("group", { name: "Sin consentimiento" })).getByText("0")).toBeInTheDocument();
  });

  it("la fila vieja 'Disponible en v0.2' desaparece para esos dos KPI", async () => {
    mockDashboard(ok(dashboardBody({ notifications_today: 9, members_without_consent: 2 })));
    renderDashboard(<NotificationKpis />);

    await screen.findByRole("link", { name: "Por avisar hoy: 9" });
    expect(screen.queryByText(/Disponible en/)).not.toBeInTheDocument();
  });

  it("un null del api no se muestra como 0", async () => {
    mockDashboard(ok(dashboardBody({ notifications_today: null, members_without_consent: null })));
    renderDashboard(<NotificationKpis />);

    const card = await screen.findByRole("group", { name: "Sin consentimiento" });
    expect(within(card).queryByText("0")).not.toBeInTheDocument();
    expect(screen.queryByText(/Disponible en/)).not.toBeInTheDocument();
  });

  it("tiene su sección con título", async () => {
    mockDashboard(ok());
    renderDashboard(<NotificationKpis />);

    const region = await screen.findByRole("region", { name: "Avisos" });
    expect(within(region).getAllByText(/Por avisar hoy|Sin consentimiento/)).toHaveLength(2);
  });

  it("si el tablero falla no inventa valores", async () => {
    mockDashboard(serverError);
    renderDashboard(<NotificationKpis />);

    expect(await screen.findAllByText("No se pudo cargar")).toHaveLength(2);
    expect(screen.queryByRole("link", { name: /Por avisar hoy/ })).not.toBeInTheDocument();
  });

  it("el código nombra el DESIGN-GAP de la tarjeta Por avisar hoy", () => {
    const gaps = Object.values(SOURCE)
      .join("\n")
      .split("\n")
      .filter((line) => line.includes("DESIGN-GAP:"))
      .join("\n");

    expect(gaps).toContain("Por avisar hoy");
  });

  it.each([["claro", null], ["oscuro", "dark"]])("es accesible en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    mockDashboard(ok());
    const { container } = renderDashboard(<NotificationKpis />);
    await screen.findByRole("link", { name: /Por avisar hoy/ });

    expect(await axe(container)).toHaveNoViolations();
  });
});
