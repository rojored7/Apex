// US-064 T3 y T4: tarjeta de indicador con dinero, conteo, vacío, carga, error y enlace.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { KpiCard } from "./KpiCard";

describe("KpiCard", () => {
  it("con valor null muestra Disponible en v0.2 y nunca un cero", () => {
    render(<KpiCard label="Por avisar hoy" value={null} kind="count" availableIn="v0.2" />);

    expect(screen.getByText("Disponible en v0.2")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("sin availableIn y valor ausente muestra Sin datos", () => {
    render(<KpiCard label="Asistencia" value={undefined} kind="count" />);

    expect(screen.getByText("Sin datos")).toBeInTheDocument();
  });

  it("dinero con formatCop", () => {
    render(<KpiCard label="Ingresos de octubre" value={120000} kind="money" note="vs sept: $ 17.100.000" />);

    expect(screen.getByText("$ 120.000")).toBeInTheDocument();
    expect(screen.getByText("vs sept: $ 17.100.000")).toBeInTheDocument();
  });

  it("conteo con separador de miles y variación", () => {
    render(<KpiCard label="Socios al día" value={1250} kind="count" delta="+12 esta semana" />);

    expect(screen.getByText("1.250")).toBeInTheDocument();
    expect(screen.getByText("+12 esta semana")).toBeInTheDocument();
  });

  it("con enlace es un único destino con nombre que combina etiqueta y valor", () => {
    render(
      <MemoryRouter>
        <KpiCard label="Por vencer" value={12} kind="count" href="/membresias?status=expiring" note="3 vencen hoy" attention />
      </MemoryRouter>,
    );

    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAccessibleName("Por vencer: 12");
    expect(links[0]).toHaveAccessibleDescription("3 vencen hoy");
    expect(links[0]).toHaveAttribute("href", "/membresias?status=expiring");
    expect(links[0]).toHaveClass("attention");
  });

  it("con enlace y sin valor el nombre usa el texto de disponibilidad", () => {
    render(
      <MemoryRouter>
        <KpiCard label="Sesiones de hoy" value={null} kind="count" availableIn="v0.4" href="/clases" />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link")).toHaveAccessibleName("Sesiones de hoy: Disponible en v0.4");
  });

  it("cargando muestra un esqueleto ocupado sin cifra", () => {
    render(<KpiCard label="Vencidos" value={41} kind="count" isLoading />);

    const card = screen.getByRole("group", { name: "Vencidos" });
    expect(card).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Cargando")).toBeInTheDocument();
    expect(screen.queryByText("41")).not.toBeInTheDocument();
  });

  it("con error muestra No se pudo cargar y Reintentar", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<KpiCard label="Vencidos" value={null} kind="count" error onRetry={onRetry} />);

    expect(screen.getByText("No se pudo cargar")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("con error y sin reintento no muestra el botón", () => {
    render(<KpiCard label="Vencidos" value={null} kind="count" error />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("sin enlace es un grupo con su etiqueta", () => {
    render(<KpiCard label="Vencidos" value={41} kind="count" attention />);

    expect(screen.getByRole("group", { name: "Vencidos" })).toHaveClass("attention");
    expect(screen.getByText("41")).toHaveClass("value");
  });
});
