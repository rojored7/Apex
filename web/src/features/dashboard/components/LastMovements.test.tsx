// S4A-F3 · US-110 (paso 122): "Últimos movimientos" de Inicio. Diez frases en el orden del api, la
// hora relativa de Bogotá (reloj falso), el enlace a la ficha del socio, la frase como texto (nunca
// HTML), vacío, carga, error con reintento, "Ver auditoría" solo para quien la puede ver y el
// DESIGN-GAP por "Sistema marcó..." (el api excluye al usuario del sistema, Q10).
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { DIEGO_ID, LAURA_ID, MOVEMENTS, MOVEMENT_TIMES, NOW, coachDashboardBody, dashboardBody, mockDashboard, movement, ok, renderDashboard, serverError } from "../../../test/dashboard";
import { signOutForTests } from "../../../test/session";
import { LastMovements, MovementItem } from "./LastMovements";

const SOURCE = import.meta.glob<string>("./LastMovements.tsx", { query: "?raw", import: "default", eager: true });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(NOW));
});

afterEach(() => {
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function list(): Promise<HTMLElement> {
  return screen.findByRole("list", { name: "Últimos movimientos" });
}

describe("LastMovements", () => {
  it("muestra las diez frases en el orden del api", async () => {
    mockDashboard(ok());
    renderDashboard(<LastMovements />);

    const items = within(await list()).getAllByRole("listitem");
    expect(items).toHaveLength(10);
    expect(items.map((item) => item.querySelector("[data-phrase]")?.textContent)).toEqual(MOVEMENTS.map((m) => m.phrase));
  });

  it("cada una con su hora relativa de Bogotá y la fecha completa en el elemento time", async () => {
    mockDashboard(ok());
    renderDashboard(<LastMovements />);

    const times = within(await list())
      .getAllByRole("listitem")
      .map((item) => item.querySelector("time"));
    expect(times.map((time) => time?.textContent)).toEqual(MOVEMENT_TIMES);
    expect(times[0]).toHaveAttribute("datetime", MOVEMENTS[0]?.at);
    expect(times[2]).toHaveAttribute("title", "20 oct 2026, 12:10 p. m.");
  });

  it("la frase de un movimiento con socio enlaza a su ficha; sin socio queda como texto", async () => {
    mockDashboard(ok());
    renderDashboard(<LastMovements />);

    const items = within(await list()).getAllByRole("listitem");
    expect(within(items[1] as HTMLElement).getByRole("link", { name: "coach vendió Mensual a Diego M." })).toHaveAttribute("href", `/socios/${DIEGO_ID}`);
    expect(within(items[0] as HTMLElement).getByRole("link")).toHaveAttribute("href", `/socios/${LAURA_ID}`);
    expect(within(items[8] as HTMLElement).queryByRole("link")).not.toBeInTheDocument();
    expect(within(items[8] as HTMLElement).getByText("admin modificó la ficha de un socio")).toBeInTheDocument();
  });

  it("una frase con HTML se ve literal", async () => {
    mockDashboard(ok());
    const { container } = renderDashboard(<LastMovements />);

    expect(await screen.findByText("admin registró a <b>Laura</b> G.")).toBeInTheDocument();
    expect(container.querySelector("b")).toBeNull();
  });

  it("al coach le llegan las frases de pagos sin monto y las pinta tal cual", async () => {
    mockDashboard(ok(coachDashboardBody()));
    renderDashboard(<LastMovements />, "coach");

    expect(await screen.findByText("admin registró un pago de Laura G.")).toBeInTheDocument();
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
  });

  it("Ver auditoría solo para quien puede verla", async () => {
    mockDashboard(ok());
    const admin = renderDashboard(<LastMovements />);
    expect(await screen.findByRole("link", { name: "Ver auditoría" })).toHaveAttribute("href", "/sistema/auditoria");
    admin.unmount();
    signOutForTests();

    mockDashboard(ok(coachDashboardBody()));
    renderDashboard(<LastMovements />, "coach");
    await list();
    expect(screen.queryByRole("link", { name: "Ver auditoría" })).not.toBeInTheDocument();
  });

  it("sin movimientos invita a empezar", async () => {
    mockDashboard(ok(dashboardBody({ last_movements: [] })));
    renderDashboard(<LastMovements />);

    expect(await screen.findByText("Todavía no hay movimientos del equipo. Cuando alguien registre un socio, venda una membresía o reciba un pago, aparece aquí.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Últimos movimientos" })).not.toBeInTheDocument();
  });

  it("revisión de seguridad de F3 (M2): un member_id que no es UUID no se vuelve enlace", () => {
    renderDashboard(
      <ol>
        <MovementItem movement={movement({ member_id: "../x", phrase: "admin registró a Laura G." })} nowMs={Date.parse(NOW)} />
      </ol>,
    );

    expect(screen.getByText("admin registró a Laura G.")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("mientras carga lo dice con role=status (L3)", async () => {
    mockDashboard(() => new Promise(() => undefined));
    renderDashboard(<LastMovements />);

    expect(await screen.findByRole("status")).toHaveTextContent("Cargando movimientos");
    expect(screen.getByRole("region", { name: "Últimos movimientos" })).toHaveAttribute("aria-busy", "true");
  });

  it("si falla, explica qué pasó y Reintentar vuelve a pedir", async () => {
    const api = mockDashboard(serverError, ok());
    renderDashboard(<LastMovements />);

    expect(await screen.findByText("No pudimos cargar los últimos movimientos. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(within(await list()).getAllByRole("listitem")).toHaveLength(10);
    expect(api.callsTo("GET /dashboard")).toHaveLength(2);
  });

  it("el código nombra el DESIGN-GAP de Sistema marcó y no inyecta HTML", () => {
    const code = Object.values(SOURCE).join("\n");
    const gaps = code.split("\n").filter((line) => line.includes("DESIGN-GAP:")).join("\n");

    expect(gaps).toContain("Sistema marcó");
    expect(code).not.toContain("dangerouslySetInnerHTML");
    expect(code).not.toContain("innerHTML");
  });

  it("es accesible", async () => {
    mockDashboard(ok());
    const { container } = renderDashboard(<LastMovements />);
    await list();
    expect(await axe(container)).toHaveNoViolations();
  });
});
