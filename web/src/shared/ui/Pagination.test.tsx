// US-063 T5 y T8: paginación con 25, 50 o 100 por página y offset = (página - 1) * limit.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { useListParams } from "../hooks/useListParams";
import { Pagination } from "./Pagination";

function setup(props: { total: number; limit: number; offset: number }) {
  const onPageChange = vi.fn();
  const onLimitChange = vi.fn();
  render(<Pagination {...props} onPageChange={onPageChange} onLimitChange={onLimitChange} />);
  return { onPageChange, onLimitChange };
}

describe("Pagination", () => {
  it("es una navegación con el tramo, la página y los tamaños 25, 50 y 100", () => {
    setup({ total: 312, limit: 50, offset: 100 });

    expect(screen.getByRole("navigation", { name: "Paginación" })).toBeInTheDocument();
    expect(screen.getByText("Mostrando 101–150 de 312")).toBeInTheDocument();
    expect(screen.getByText("Página 3 de 7")).toBeInTheDocument();
    const size = screen.getByRole("combobox", { name: "Mostrar" });
    expect(size).toHaveValue("50");
    expect(Array.from((size as HTMLSelectElement).options).map((o) => o.value)).toEqual(["25", "50", "100"]);
  });

  it("Anterior y Siguiente piden la página vecina", async () => {
    const { onPageChange } = setup({ total: 312, limit: 50, offset: 100 });

    await userEvent.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(onPageChange).toHaveBeenLastCalledWith(4);
    await userEvent.click(screen.getByRole("button", { name: "Anterior" }));
    expect(onPageChange).toHaveBeenLastCalledWith(2);
  });

  it("deshabilita Anterior en la primera y Siguiente en la última", () => {
    setup({ total: 312, limit: 50, offset: 300 });
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Anterior" })).toBeEnabled();
  });

  it("con un offset más allá del final, Anterior lleva a la última página", async () => {
    const { onPageChange } = setup({ total: 40, limit: 25, offset: 100 });

    expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Anterior" }));

    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("sin resultados deshabilita las dos y lo dice", () => {
    setup({ total: 0, limit: 25, offset: 0 });

    expect(screen.getByText("Sin resultados")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
  });

  it("cambiar el tamaño avisa el nuevo limit", async () => {
    const { onLimitChange } = setup({ total: 312, limit: 25, offset: 0 });

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Mostrar" }), "100");

    expect(onLimitChange).toHaveBeenCalledWith(100);
  });

  it("un limit fuera de los tamaños estándar se muestra como opción adicional", () => {
    setup({ total: 312, limit: 30, offset: 0 });

    const size = screen.getByRole<HTMLSelectElement>("combobox", { name: "Mostrar" });
    expect(size).toHaveValue("30");
    expect(Array.from(size.options).map((o) => o.value)).toEqual(["25", "30", "50", "100"]);
  });
});

describe("Pagination con la URL", () => {
  function Screen({ total }: { total: number }) {
    const list = useListParams();
    const location = useLocation();
    return (
      <>
        <Pagination
          total={total}
          limit={list.params.limit}
          offset={list.params.offset}
          onPageChange={list.setPage}
          onLimitChange={list.setLimit}
        />
        <output data-testid="search">{location.search}</output>
      </>
    );
  }

  it("de la página 2 a la 3 con 50 por página produce limit=50&offset=100", async () => {
    render(
      <MemoryRouter initialEntries={["/pagos?limit=50&offset=50"]}>
        <Screen total={312} />
      </MemoryRouter>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Siguiente" }));

    expect(screen.getByTestId("search")).toHaveTextContent("?limit=50&offset=100");
    expect(screen.getByText("Mostrando 101–150 de 312")).toBeInTheDocument();
  });
});
