// US-063 T6 y T8: buscador con espera de 300 ms, selects, rango de fechas, ordenar y Limpiar.
import { readFileSync } from "node:fs";
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

  it("un select con hint lo muestra y lo asocia al control (Fase 4 L8)", () => {
    render(<FilterBar {...base} selects={[{ name: "plan", label: "Plan", value: "", options: [], hint: "Se muestran 2 de 230 planes." }]} />);

    expect(screen.getByRole("combobox", { name: "Plan" })).toHaveAccessibleDescription("Se muestran 2 de 230 planes.");
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

  it("el eco de la URL no pisa lo que se siguió escribiendo", async () => {
    const user = fakeTimersUser();
    const onQueryChange = vi.fn();
    const { rerender } = render(<FilterBar {...base} query="" onQueryChange={onQueryChange} />);
    const search = screen.getByRole("searchbox", { name: "Buscar" });

    await user.type(search, "a");
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });
    expect(onQueryChange).toHaveBeenLastCalledWith("a");
    await user.type(search, "b");
    rerender(<FilterBar {...base} query="a" onQueryChange={onQueryChange} />);

    expect(search).toHaveValue("ab");
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });
    expect(onQueryChange).toHaveBeenLastCalledWith("ab");
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
    const list = useListParams({ filters: ["plan"] as const, localQuery: false });
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

describe("FilterBar · celular (S2-F4a)", () => {
  it("al apilarse en columna, buscador, selects y rango miden su contenido (sin base de flex como alto)", () => {
    const css = readFileSync("src/shared/ui/FilterBar.module.css", "utf8");
    const mobile = css.slice(css.indexOf("@media (width < 768px)"));

    expect(mobile).toContain("flex-direction: column");
    expect(mobile).toMatch(/\.search,\s*\.select,\s*\.range\s*\{\s*flex: 0 0 auto;/);
  });
});
