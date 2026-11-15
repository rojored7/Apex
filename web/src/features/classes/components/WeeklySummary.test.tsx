// S7-F5 · US-162 (front): el resumen semanal de Asistencia (GET /attendance/summary).
// - Una sección por semana, la más reciente primero; cada una con su total y las asistencias con marca.
// - Una tabla por semana con la franja, las sesiones, las asistencias, la ocupación en texto («75 %») y las marcadas.
// - Semana vacía lo dice; cupo 0 no muestra un porcentaje inventado; las sesiones extra se llaman «Extra».
import { cleanup, render, screen, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { WEEK_BUCKETS } from "../../../test/attendance";
import type { WeekBucketView } from "../attendanceApi";
import { WeeklySummary } from "./WeeklySummary";

const weeks = WEEK_BUCKETS as unknown as WeekBucketView[];

afterEach(cleanup);

describe("WeeklySummary", () => {
  it("una sección por semana con su rango en palabras, la más reciente primero", () => {
    render(<WeeklySummary weeks={weeks} />);

    const sections = screen.getAllByRole("region");
    expect(sections.map((s) => s.getAttribute("aria-label"))).toEqual(["Semana del 19 al 25 de octubre de 2026", "Semana del 12 al 18 de octubre de 2026"]);
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["Semana del 19 al 25 de octubre de 2026", "Semana del 12 al 18 de octubre de 2026"]);
  });

  it("dice el total de la semana y cuántas llegaron con marca", () => {
    render(<WeeklySummary weeks={weeks} />);

    const week = screen.getByRole("region", { name: /19 al 25 de octubre/ });
    expect(within(week).getByText("49 asistencias · 2 con marca")).toBeInTheDocument();
  });

  it("singular: «1 asistencia · 1 con marca»", () => {
    render(<WeeklySummary weeks={[{ ...WEEK_BUCKETS[1], total: 1, flagged: 1 }] as unknown as WeekBucketView[]} />);

    expect(screen.getByText("1 asistencia · 1 con marca")).toBeInTheDocument();
  });

  it("la tabla de franjas tiene sus cinco columnas y una fila por franja", () => {
    render(<WeeklySummary weeks={weeks} />);

    const table = screen.getByRole("table", { name: "Franjas de la semana del 19 al 25 de octubre de 2026" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Franja", "Sesiones", "Asistencias", "Ocupación", "Con marca"]);
    const rows = within(table).getAllByRole("row").slice(1);
    const cells = (row: HTMLElement | undefined) => [...(row as HTMLElement).querySelectorAll("th, td")].map((c) => c.textContent);
    expect(cells(rows[0])).toEqual(["CrossFit · 06:00", "5", "45 de 60", "75 %", "2"]);
    expect(cells(rows[2])).toEqual(["Extra", "1", "4 de 20", "20 %", "0"]);
  });

  it("una franja sin cupo no inventa un porcentaje", () => {
    render(<WeeklySummary weeks={weeks} />);

    const table = screen.getByRole("table", { name: /19 al 25/ });
    const open = within(table).getByRole("row", { name: /Open box/ });
    expect([...open.querySelectorAll("th, td")].map((c) => c.textContent)).toEqual(["Open box · 09:30", "1", "0 de 0", "Sin cupo", "0"]);
  });

  it("una semana sin asistencias lo dice y no pinta una tabla vacía", () => {
    render(<WeeklySummary weeks={weeks} />);

    const empty = screen.getByRole("region", { name: /12 al 18 de octubre/ });
    expect(within(empty).getByText("Sin asistencias esta semana.")).toBeInTheDocument();
    expect(within(empty).queryByRole("table")).toBeNull();
  });

  it("una semana con asistencias pero sin franjas no rompe", () => {
    render(<WeeklySummary weeks={[{ ...WEEK_BUCKETS[0], total: 3, slots: [] }] as unknown as WeekBucketView[]} />);

    expect(screen.getByText("3 asistencias · 0 con marca")).toBeInTheDocument();
  });

  it("la ocupación va en texto, no solo en la barra, y no tiene violaciones de accesibilidad", async () => {
    const { container } = render(<WeeklySummary weeks={weeks} />);

    expect(screen.getByText("75 %")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
});
