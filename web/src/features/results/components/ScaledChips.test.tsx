// S8-F4 · US-170 (L-2): «¿Qué escaló?» son chips de los movimientos del WOD; llenan `scaled_movement_ids`, nunca texto libre.
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { MOV_KB, MOV_PULL, MOV_RUN } from "../../../test/results";
import { ScaledChips } from "./ScaledChips";

const MOVEMENTS = [
  { movement_id: MOV_RUN, movement_name: "Run 400 m" },
  { movement_id: MOV_KB, movement_name: "Kettlebell swing" },
  { movement_id: MOV_PULL, movement_name: "Pull-up" },
];

afterEach(cleanup);

describe("ScaledChips", () => {
  it("muestra un chip por movimiento del WOD, sin campo de texto libre", () => {
    render(<ScaledChips movements={MOVEMENTS} value={[]} onChange={() => undefined} />);
    const group = screen.getByRole("group", { name: "¿Qué escaló?" });
    expect(group).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(3);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("tocar un chip suma su movement_id y volver a tocarlo lo quita", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<ScaledChips movements={MOVEMENTS} value={[]} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Pull-up" }));
    expect(onChange).toHaveBeenLastCalledWith([MOV_PULL]);
    rerender(<ScaledChips movements={MOVEMENTS} value={[MOV_PULL, MOV_KB]} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "Pull-up" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Pull-up" }));
    expect(onChange).toHaveBeenLastCalledWith([MOV_KB]);
  });

  it("sin movimientos no dibuja nada y no tiene violaciones de accesibilidad", async () => {
    const { container, rerender } = render(<ScaledChips movements={MOVEMENTS} value={[MOV_RUN]} onChange={() => undefined} />);
    expect(await axe(container)).toHaveNoViolations();
    rerender(<ScaledChips movements={[]} value={[]} onChange={() => undefined} />);
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });
});
