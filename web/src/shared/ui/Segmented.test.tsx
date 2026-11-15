// S8-F2 (S8-D15): grupo de opciones excluyentes (nivel RX, RX+, Escalado). role="radiogroup", flechas y 44 o 56 px.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
import { Segmented } from "./Segmented";

const OPTIONS = [
  { value: "rx", label: "RX" },
  { value: "rx_plus", label: "RX+" },
  { value: "scaled", label: "Escalado" },
];

describe("Segmented", () => {
  it("es un radiogroup con la opción activa marcada", () => {
    render(<Segmented label="Nivel" options={OPTIONS} value="rx_plus" onChange={vi.fn()} />);
    expect(screen.getByRole("radiogroup", { name: "Nivel" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "RX+" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "RX" })).not.toBeChecked();
  });

  it("elige con clic y con las flechas", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Segmented label="Nivel" options={OPTIONS} value="rx" onChange={onChange} />);
    await user.click(screen.getByRole("radio", { name: "Escalado" }));
    expect(onChange).toHaveBeenLastCalledWith("scaled");
    screen.getByRole("radio", { name: "RX" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenLastCalledWith("rx_plus");
    await user.keyboard("{ArrowLeft}");
    expect(onChange).toHaveBeenLastCalledWith("rx");
  });

  it("solo la opción activa entra en el orden de tabulación", () => {
    render(<Segmented label="Nivel" options={OPTIONS} value="rx" onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: "RX" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("radio", { name: "Escalado" })).toHaveAttribute("tabindex", "-1");
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(<Segmented label="Nivel" options={OPTIONS} value="rx" onChange={vi.fn()} size="large" />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
