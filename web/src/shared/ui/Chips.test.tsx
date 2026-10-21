// US-063 T7 y T8: chips de filtro rápido con conteo y aria-pressed (el estado no es solo color).
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Chips, type ChipOption } from "./Chips";

const STATUS: ChipOption[] = [
  { value: "all", label: "Todos", count: 342 },
  { value: "active", label: "Al día", count: 210 },
  { value: "expiring", label: "Por vencer", count: 18, tone: "warning" },
  { value: "pending_payment", label: "Pendiente de pago", count: 7, tone: "warning" },
  { value: "expired", label: "Vencidos", count: 41, tone: "danger" },
  { value: "frozen", label: "Congelados", count: 4 },
  { value: "none", label: "Sin membresía", count: 1069 },
  { value: "deleted", label: "Dados de baja" },
];

describe("Chips", () => {
  it("cada chip es un botón con texto, conteo y aria-pressed", () => {
    render(<Chips label="Estado" mode="single" options={STATUS} value={["active"]} onChange={() => undefined} />);

    const group = screen.getByRole("group", { name: "Estado" });
    const buttons = within(group).getAllByRole("button");
    expect(buttons).toHaveLength(8);
    const active = screen.getByRole("button", { name: /Al día/ });
    expect(active).toHaveAttribute("aria-pressed", "true");
    expect(active).toHaveTextContent("Al día210");
    expect(active).toHaveClass("active");
    expect(within(active).getByTestId("chip-check")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Todos/ })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /Sin membresía/ })).toHaveTextContent("1.069");
    expect(screen.getByRole("button", { name: "Dados de baja" })).toBeInTheDocument();
  });

  it("incluye Pendiente de pago con el tono de advertencia (Q3)", () => {
    render(<Chips label="Estado" mode="single" options={STATUS} value={[]} onChange={() => undefined} />);

    expect(screen.getByRole("button", { name: /Pendiente de pago/ })).toHaveClass("warning");
    expect(screen.getByRole("button", { name: /Vencidos/ })).toHaveClass("danger");
  });

  it("selección única: elegir otro reemplaza y volver a pulsar el activo lo quita", async () => {
    const onChange = vi.fn();
    const { rerender } = render(<Chips label="Estado" mode="single" options={STATUS} value={["active"]} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: /Vencidos/ }));
    expect(onChange).toHaveBeenLastCalledWith(["expired"]);
    rerender(<Chips label="Estado" mode="single" options={STATUS} value={["expired"]} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /Vencidos/ }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("selección múltiple: suma y quita sin perder las demás", async () => {
    const onChange = vi.fn();
    render(<Chips label="Estado" mode="multiple" options={STATUS} value={["active"]} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: /Por vencer/ }));
    expect(onChange).toHaveBeenLastCalledWith(["active", "expiring"]);
    await userEvent.click(screen.getByRole("button", { name: /Al día/ }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("la fila se desplaza dentro de su caja para no desbordar en 320 px", () => {
    const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "Chips.module.css"), "utf8");

    expect(css).toMatch(/\.chips\s*\{[^}]*overflow-x:\s*auto/);
  });
});
