// S7-F3b (M3): estado de una franja del horario («Activa», «Pausada») en StatusTag; el texto lleva el significado.
import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import { slotLabel, slotTone, type SlotStateView, type StatusTone } from "./statusLabel";
import { StatusTag } from "./StatusTag";

const CASES: [SlotStateView, string, StatusTone][] = [
  ["active", "Activa", "ok"],
  ["paused", "Pausada", "neutral"],
];

describe("estado de una franja", () => {
  it.each(CASES)("%s se lee «%s» con el tono %s", (state, label, tone) => {
    expect(slotLabel(state)).toBe(label);
    expect(slotTone(state)).toBe(tone);
    render(<StatusTag slot={state} />);

    expect(screen.getByText(label)).toHaveClass("tag", tone);
    expect(screen.getByText(label)).toHaveAttribute("data-slot", state);
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = render(<StatusTag slot="paused" />);

    expect(await axe(container)).toHaveNoViolations();
  });
});
