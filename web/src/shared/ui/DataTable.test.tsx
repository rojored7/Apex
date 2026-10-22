// US-063 T4 y T8: tabla de lista con estados de carga, vacío y error, orden accesible y
// vista de tarjetas en celular (S2-F4b: columnas `wide` a todo el ancho de la tarjeta).
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { ApiError } from "../../core/api/errors";
import { DataTable, type Column, type DataTableProps } from "./DataTable";

interface Row {
  id: string;
  name: string;
  plan: string;
  amount: number;
}

const ROWS: Row[] = [
  { id: "1", name: "Laura Gómez", plan: "Mensual", amount: 120000 },
  { id: "2", name: "Andrés Ruiz", plan: "12 clases", amount: 110000 },
];

const COLUMNS: Column<Row>[] = [
  { key: "name", header: "Socio", render: (r) => r.name, sortable: true },
  { key: "plan", header: "Plan vigente", render: (r) => r.plan },
  { key: "amount", header: "Precio", render: (r) => String(r.amount), align: "end", sortable: true },
];

function renderTable(props: Partial<DataTableProps<Row>> = {}): ReturnType<typeof render> {
  const ui: ReactElement = (
    <MemoryRouter>
      <DataTable<Row>
        caption="Socios"
        columns={COLUMNS}
        rows={ROWS}
        total={ROWS.length}
        rowKey={(r) => r.id}
        rowHref={(r) => `/socios/${r.id}`}
        {...props}
      />
    </MemoryRouter>
  );
  return render(ui);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DataTable", () => {
  it("pinta encabezados y filas, con la primera columna como enlace a la ficha", () => {
    renderTable();

    const table = screen.getByRole("table", { name: "Socios" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Socio", "Plan vigente", "Precio"]);
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(screen.getByRole("link", { name: "Laura Gómez" })).toHaveAttribute("href", "/socios/1");
    expect(screen.getAllByRole("link")).toHaveLength(2);
    expect(screen.getByText("Mensual").closest("td")).not.toHaveClass("end");
    expect(screen.getByText("120000").closest("td")).toHaveClass("end");
  });

  it("la caja de la tabla se desplaza sola y es enfocable con teclado", () => {
    renderTable();

    const region = screen.getByRole("region", { name: "Socios" });
    expect(region).toHaveClass("scroll");
    expect(region).toHaveAttribute("tabindex", "0");
  });

  it("durante la carga muestra un esqueleto con tantas filas como el limit, máximo 10", () => {
    renderTable({ isLoading: true, rows: undefined, limit: 25 });

    const region = screen.getByRole("region", { name: "Socios" });
    expect(region).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Cargando")).toBeInTheDocument();
    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(10);
  });

  it("esqueleto de 3 filas con limit 3", () => {
    renderTable({ isLoading: true, rows: undefined, limit: 3 });

    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(3);
  });

  it("con total = 0 muestra el mensaje de vacío y la acción sugerida", () => {
    renderTable({ rows: [], total: 0, emptyMessage: "No hay socios con estos filtros.", emptyAction: <a href="/socios/nuevo">Nuevo socio</a> });

    expect(screen.getByText("No hay socios con estos filtros.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Nuevo socio" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("vacío por defecto guía a cambiar los filtros", () => {
    renderTable({ rows: [], total: 0 });

    expect(screen.getByText("No hay resultados. Prueba con otra búsqueda o limpia los filtros.")).toBeInTheDocument();
  });

  it("con error muestra el message del envelope y Reintentar llama a onRetry", async () => {
    const onRetry = vi.fn();
    renderTable({ rows: undefined, error: new ApiError({ status: 500, code: "internal_error", message: "Error interno" }), onRetry });

    expect(screen.getByRole("alert")).toHaveTextContent("Error interno");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("un error que no es del api muestra un mensaje genérico", () => {
    renderTable({ rows: undefined, error: new Error("boom") });

    expect(screen.getByRole("alert")).toHaveTextContent("No se pudo cargar la lista. Intenta de nuevo.");
    expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
  });

  it("los encabezados ordenables son botones con aria-sort", async () => {
    const onSortChange = vi.fn();
    const { rerender } = renderTable({ sort: null, onSortChange });

    const socio = screen.getByRole("columnheader", { name: "Socio" });
    expect(socio).toHaveAttribute("aria-sort", "none");
    expect(screen.getByRole("columnheader", { name: "Plan vigente" })).not.toHaveAttribute("aria-sort");
    await userEvent.click(within(socio).getByRole("button", { name: "Socio" }));
    expect(onSortChange).toHaveBeenLastCalledWith({ field: "name", direction: "asc" });

    rerender(
      <MemoryRouter>
        <DataTable<Row>
          caption="Socios"
          columns={COLUMNS}
          rows={ROWS}
          total={2}
          rowKey={(r) => r.id}
          rowHref={(r) => `/socios/${r.id}`}
          sort={{ field: "name", direction: "asc" }}
          onSortChange={onSortChange}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("columnheader", { name: "Socio" })).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(screen.getByRole("button", { name: "Socio" }));
    expect(onSortChange).toHaveBeenLastCalledWith({ field: "name", direction: "desc" });
  });

  it("aria-sort descendente y orden por teclado", async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    renderTable({ sort: { field: "amount", direction: "desc" }, onSortChange });

    expect(screen.getByRole("columnheader", { name: "Precio" })).toHaveAttribute("aria-sort", "descending");
    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "Socio" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onSortChange).toHaveBeenCalledWith({ field: "name", direction: "asc" });
  });

  it("sin onSortChange los encabezados no son botones", () => {
    renderTable();

    expect(screen.queryByRole("button", { name: "Socio" })).not.toBeInTheDocument();
  });

  it("en celular muestra una tarjeta por fila con la primera columna como enlace", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: true, addEventListener: () => undefined, removeEventListener: () => undefined })),
    );
    renderTable();

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Socios" });
    const cards = within(list).getAllByRole("listitem");
    expect(cards).toHaveLength(2);
    expect(within(cards[0] as HTMLElement).getByRole("link", { name: "Laura Gómez" })).toHaveAttribute("href", "/socios/1");
    expect(within(cards[0] as HTMLElement).getByText("Plan vigente")).toBeInTheDocument();
    expect(within(cards[0] as HTMLElement).getByText("Mensual")).toBeInTheDocument();
  });

  it("en celular un campo wide ocupa todo el ancho de la tarjeta (S2-F4b)", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: true, addEventListener: () => undefined, removeEventListener: () => undefined })),
    );
    renderTable({ columns: [...COLUMNS, { key: "actions", header: "Acción", render: () => "Editar", wide: true }] });

    const [card] = within(screen.getByRole("list", { name: "Socios" })).getAllByRole("listitem");
    const field = (label: string) => within(card as HTMLElement).getByText(label).parentElement;
    expect(field("Acción")).toHaveClass("cardFieldWide");
    expect(field("Plan vigente")).not.toHaveClass("cardFieldWide");
  });
});
