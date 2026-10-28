// Fase 4 del Sprint 3 (M3): el foco al elegir y al cambiar de socio en los dos buscadores. El control
// que tenía el foco desaparece en los dos casos: al elegir, el foco va al botón "Cambiar socio"; al
// cambiar, al buscador (revisión S3-F3, MEDIUM 3).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { useSelectionFocus } from "./useSelectionFocus";

function Picker() {
  const [picked, setPicked] = useState<string | null>(null);
  const { selectedRef, searchRef, focusChangeNext, focusSearchNext } = useSelectionFocus(picked);
  return picked ? (
    <div ref={selectedRef}>
      <span>{picked}</span>
      <button
        type="button"
        onClick={() => {
          focusSearchNext();
          setPicked(null);
        }}
      >
        Cambiar
      </button>
    </div>
  ) : (
    <>
      <input ref={searchRef} aria-label="Buscar" />
      <button
        type="button"
        onClick={() => {
          focusChangeNext();
          setPicked("Laura");
        }}
      >
        Laura
      </button>
    </>
  );
}

describe("useSelectionFocus", () => {
  it("al elegir enfoca el botón de la selección y al cambiar vuelve al buscador", async () => {
    const user = userEvent.setup();
    render(<Picker />);

    await user.click(screen.getByRole("button", { name: "Laura" }));
    expect(screen.getByRole("button", { name: "Cambiar" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Cambiar" }));
    expect(screen.getByRole("textbox", { name: "Buscar" })).toHaveFocus();
  });

  it("sin pedirlo no mueve el foco", () => {
    const { rerender } = render(<Picker />);
    rerender(<Picker />);

    expect(document.body).toHaveFocus();
  });
});
