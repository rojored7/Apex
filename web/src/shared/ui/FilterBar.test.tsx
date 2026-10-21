// US-063 T6 y T8: buscador con espera de 300 ms, selects, rango de fechas, ordenar y Limpiar.
import { act, render, screen } from "@testing-library/react";
import { fakeTimersUser, restoreRtlTimers, useRtlFakeTimers } from "../../test/fakeTimers";
import { MemoryRouter, useLocation } from "react-router";
import { useListParams } from "../hooks/useListParams";
import { FilterBar, SEARCH_DEBOUNCE_MS, type FilterBarProps } from "./FilterBar";

const base: FilterBarProps = {
  query: "",
  onQueryChange: () => undefined,
  onClear: () => undefined,
};

describe("FilterBar", () => {
  beforeEach(() => {
    useRtlFakeTimers();
  });
  afterEach(() => {
    restoreRtlTimers();
  });

  it("espera 300 ms sin teclear y avisa una sola vez", async () => {
    const user = fakeTimersUser();
    const onQueryChange = vi.fn();
    render(<FilterBar {...base} onQueryChange={onQueryChange} searchPlaceholder="Nombre, documento o teléfono" />);

    const search = screen.getByRole("searchbox", { name: "Buscar" });
    expect(search).toHaveAttribute("placeholder", "Nombre, documento o teléfono");
    await user.type(search, "pérez");
    expect(onQueryChange).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });

    expect(SEARCH_DEBOUNCE_MS).toBe(300);
    expect(onQueryChange).toHaveBeenCalledTimes(1);
    expect(onQueryChange).toHaveBeenCalledWith("pérez");
  });

  it("selects con opción Cualquiera, rango de fechas civiles y ordenar", async () => {
    const user = fakeTimersUser();
    const onSelectChange = vi.fn();
    const onDateChange = vi.fn();
    const onSortChange = vi.fn();
    render(
      <FilterBar
        {...base}
        selects={[
          {
            name: "plan",
            label: "Plan",
            value: "",
            options: [
              { value: "p1", label: "Mensual" },
              { value: "p2", label: "12 clases" },
            ],
          },
        ]}
        onSelectChange={onSelectChange}
        dateRange={{ label: "Fecha de pago", from: "2026-10-01", to: "", onChange: onDateChange }}
        sort={{ value: "", options: [{ value: "-end_date", label: "Vencimiento más próximo" }], onChange: onSortChange }}
      />,
    );

    const plan = screen.getByRole("combobox", { name: "Plan" });
    expect(plan).toHaveValue("");
    expect(screen.getByRole("option", { name: "Cualquiera" })).toBeInTheDocument();
    await user.selectOptions(plan, "p2");
    expect(onSelectChange).toHaveBeenCalledWith("plan", "p2");

    const group = screen.getByRole("group", { name: "Fecha de pago" });
    expect(group).toBeInTheDocument();
    const desde = screen.getByLabelText("Desde");
    expect(desde).toHaveValue("2026-10-01");
    expect(screen.getByLabelText("Hasta")).toHaveAttribute("min", "2026-10-01");
    await user.type(screen.getByLabelText("Hasta"), "2026-10-31");
    expect(onDateChange).toHaveBeenLastCalledWith({ from: "2026-10-01", to: "2026-10-31" });
    await user.clear(desde);
    expect(onDateChange).toHaveBeenLastCalledWith({ from: "", to: "" });

    await user.selectOptions(screen.getByRole("combobox", { name: "Ordenar por" }), "-end_date");
    expect(onSortChange).toHaveBeenCalledWith("-end_date");
  });

  it("Limpiar llama a onClear y vacía el buscador", async () => {
    const user = fakeTimersUser();
    const onClear = vi.fn();
    const onQueryChange = vi.fn();
    const { rerender } = render(<FilterBar {...base} query="ana" onQueryChange={onQueryChange} onClear={onClear} />);

    expect(screen.getByRole("searchbox", { name: "Buscar" })).toHaveValue("ana");
    await user.click(screen.getByRole("button", { name: "Limpiar" }));
    expect(onClear).toHaveBeenCalledTimes(1);
    rerender(<FilterBar {...base} query="" onQueryChange={onQueryChange} onClear={onClear} />);

    expect(screen.getByRole("searchbox", { name: "Buscar" })).toHaveValue("");
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });
    expect(onQueryChange).not.toHaveBeenCalled();
  });

  it("una etiqueta de búsqueda propia", () => {
    render(<FilterBar {...base} searchLabel="Buscar socio" />);

    expect(screen.getByRole("searchbox", { name: "Buscar socio" })).toBeInTheDocument();
  });
});

describe("FilterBar con la URL", () => {
  beforeEach(() => {
    useRtlFakeTimers();
  });
  afterEach(() => {
    restoreRtlTimers();
  });

  function Screen({ onParams }: { onParams: (search: string) => void }) {
    const list = useListParams({ filters: ["plan"] as const });
    const location = useLocation();
    onParams(location.search);
    return <FilterBar query={list.q} onQueryChange={list.setQuery} onClear={list.clear} />;
  }

  it("escribir 'pérez' desde la página 4 produce una sola petición a los 300 ms con offset=0", async () => {
    const user = fakeTimersUser();
    const seen: string[] = [];
    render(
      <MemoryRouter initialEntries={["/socios?offset=75"]}>
        <Screen
          onParams={(s) => {
            if (seen.at(-1) !== s) seen.push(s);
          }}
        />
      </MemoryRouter>,
    );

    await user.type(screen.getByRole("searchbox", { name: "Buscar" }), "pérez");
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });

    expect(seen).toEqual(["?offset=75", "?q=p%C3%A9rez"]);
  });
});
