// S7-F6 · US-164 (front): «Hoy en el box» y «Asistencia de la semana» de Inicio (Inicio.html). Salen de
// GET /dashboard (`sessions_today` y `attendance_week`, S7-R3). Cada sesión de hoy lleva a su check-in.
import { screen, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { dashboardBody, mockDashboard, ok, renderDashboard, serverError } from "../../../test/dashboard";
import { signOutForTests } from "../../../test/session";
import { ClassesKpis } from "./ClassesKpis";

const SOURCE = import.meta.glob<string>("./ClassesKpis.tsx", { query: "?raw", import: "default", eager: true });

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
});

const ID_1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa01";
const ID_2 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa02";
const ID_3 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa03";
const ID_4 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa04";

const SESIONES = [
  { id: ID_1, starts_at: "2026-10-20T11:00:00Z", coach_name: "Carlos", capacity: 12, attendance_count: 8, duration_min: 60, status: "done" as const },
  { id: ID_2, starts_at: "2026-10-20T12:00:00Z", coach_name: "Carlos", capacity: 12, attendance_count: 12, duration_min: 60, status: "scheduled" as const },
  { id: ID_3, starts_at: "2026-10-20T22:00:00Z", coach_name: null, capacity: 15, attendance_count: 0, duration_min: 60, status: "scheduled" as const },
  { id: ID_4, starts_at: "2026-10-20T23:00:00Z", coach_name: "María", capacity: 12, attendance_count: 0, duration_min: 60, status: "cancelled" as const },
];

function rowAt(rows: readonly HTMLElement[], index: number): HTMLElement {
  const row = rows[index];
  if (!row) throw new Error(`falta la fila ${String(index)}`);
  return row;
}

describe("ClassesKpis", () => {
  it("no_hay_clases_hoy: dice que no hay clases y lleva a las sesiones, nunca un 0 suelto", async () => {
    mockDashboard(ok());
    renderDashboard(<ClassesKpis />);

    await screen.findByText("Hoy no hay clases programadas");
    const card = screen.getByRole("group", { name: "Hoy en el box" });
    expect(within(card).getByRole("link", { name: "Ver sesiones" })).toHaveAttribute("href", "/clases?dia=hoy");
    expect(within(card).queryByRole("link", { name: /Check-in/ })).not.toBeInTheDocument();
  });

  it("lista cada sesión con hora de Bogotá, coach y ocupación", async () => {
    mockDashboard(ok(dashboardBody({ sessions_today: SESIONES })));
    renderDashboard(<ClassesKpis />);

    const list = await screen.findByRole("list", { name: "Clases de hoy" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(4);
    expect(within(rowAt(rows, 0)).getByText("06:00")).toBeInTheDocument();
    expect(within(rowAt(rows, 0)).getByText("Carlos")).toBeInTheDocument();
    expect(within(rowAt(rows, 0)).getByText("8 / 12")).toBeInTheDocument();
    expect(within(rowAt(rows, 2)).getByText("17:00")).toBeInTheDocument();
    expect(within(rowAt(rows, 2)).getByText("Open box")).toBeInTheDocument();
  });

  it("una clase llena dice Llena y sigue permitiendo el check-in (la tablet no bloquea: over_capacity)", async () => {
    mockDashboard(ok(dashboardBody({ sessions_today: SESIONES })));
    renderDashboard(<ClassesKpis />);

    const rows = within(await screen.findByRole("list", { name: "Clases de hoy" })).getAllByRole("listitem");
    expect(within(rowAt(rows, 1)).getByText("12 / 12")).toBeInTheDocument();
    expect(within(rowAt(rows, 1)).getByText("Llena")).toBeInTheDocument();
    expect(within(rowAt(rows, 1)).getByRole("link", { name: "Check-in de las 07:00" })).toBeInTheDocument();
  });

  it("enlaza el check-in de cada sesión programada a /clases/:id/checkin", async () => {
    mockDashboard(ok(dashboardBody({ sessions_today: SESIONES })));
    renderDashboard(<ClassesKpis />);

    await screen.findByRole("list", { name: "Clases de hoy" });
    expect(screen.getByRole("link", { name: "Check-in de las 07:00" })).toHaveAttribute("href", `/clases/${ID_2}/checkin`);
    expect(screen.getByRole("link", { name: "Check-in de las 17:00" })).toHaveAttribute("href", `/clases/${ID_3}/checkin`);
  });

  it("una sesión cancelada o terminada no ofrece Check-in y lo dice", async () => {
    mockDashboard(ok(dashboardBody({ sessions_today: SESIONES })));
    renderDashboard(<ClassesKpis />);

    const rows = within(await screen.findByRole("list", { name: "Clases de hoy" })).getAllByRole("listitem");
    expect(within(rowAt(rows, 0)).getByText("Terminó")).toBeInTheDocument();
    expect(within(rowAt(rows, 0)).queryByRole("link")).not.toBeInTheDocument();
    expect(within(rowAt(rows, 3)).getByText("Cancelada")).toBeInTheDocument();
    expect(within(rowAt(rows, 3)).queryByRole("link")).not.toBeInTheDocument();
  });

  it("Asistencia de la semana muestra el conteo y las marcadas, con enlace a /clases/asistencia", async () => {
    mockDashboard(ok(dashboardBody({ attendance_week: { count: 1250, flagged_count: 7 } })));
    renderDashboard(<ClassesKpis />);

    const link = await screen.findByRole("link", { name: "Asistencia de la semana: 1.250" });
    expect(link).toHaveAttribute("href", "/clases/asistencia");
    expect(within(link).getByText("7 con alguna bandera")).toBeInTheDocument();
  });

  it("sin marcadas no inventa una nota", async () => {
    mockDashboard(ok(dashboardBody({ attendance_week: { count: 0, flagged_count: 0 } })));
    renderDashboard(<ClassesKpis />);

    const link = await screen.findByRole("link", { name: "Asistencia de la semana: 0" });
    expect(within(link).queryByText(/bandera/)).not.toBeInTheDocument();
  });

  it("tiene su sección con título y las dos tarjetas", async () => {
    mockDashboard(ok());
    renderDashboard(<ClassesKpis />);

    const region = await screen.findByRole("region", { name: "Clases" });
    expect(within(region).getByRole("group", { name: "Hoy en el box" })).toBeInTheDocument();
    expect(await within(region).findByRole("link", { name: /^Asistencia de la semana/ })).toBeInTheDocument();
  });

  it("mientras carga muestra Cargando en las dos tarjetas", () => {
    mockDashboard(() => new Promise(() => undefined) as never);
    renderDashboard(<ClassesKpis />);

    expect(screen.getByRole("group", { name: "Hoy en el box" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("group", { name: "Asistencia de la semana" })).toHaveAttribute("aria-busy", "true");
  });

  it("si el tablero falla no inventa valores (el error lo explica KpiGrid)", async () => {
    mockDashboard(serverError);
    renderDashboard(<ClassesKpis />);

    expect(await screen.findAllByText("No se pudo cargar")).toHaveLength(2);
    expect(screen.queryByText("Hoy no hay clases programadas")).not.toBeInTheDocument();
  });

  it("el código nombra los DESIGN-GAP del gráfico, el promedio y los socios distintos", () => {
    const gaps = Object.values(SOURCE)
      .join("\n")
      .split("\n")
      .filter((line) => line.includes("DESIGN-GAP:"))
      .join("\n");

    for (const topic of ["gráfico", "Promedio por clase", "Socios distintos"]) {
      expect(gaps).toContain(topic);
    }
  });

  it("es accesible", async () => {
    mockDashboard(ok(dashboardBody({ sessions_today: SESIONES })));
    const { container } = renderDashboard(<ClassesKpis />);
    await screen.findByRole("list", { name: "Clases de hoy" });
    expect(await axe(container)).toHaveNoViolations();
  });
});
