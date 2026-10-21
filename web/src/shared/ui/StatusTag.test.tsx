import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import type { MembershipStatusView, StatusTone } from "./statusLabel";
import { StatusTag } from "./StatusTag";

const CASES: [MembershipStatusView, string, StatusTone][] = [
  ["active", "Al día", "ok"],
  ["expiring", "Por vencer", "warning"],
  ["expired", "Vencido", "danger"],
  ["frozen", "Congelado", "neutral"],
  ["cancelled", "Cancelado", "neutral"],
  ["pending_payment", "Pendiente de pago", "warning"],
  ["none", "Sin plan", "danger"],
];

describe("StatusTag", () => {
  it.each(CASES)("%s muestra '%s' con el tono %s", (status, label, tone) => {
    render(<StatusTag status={status} />);
    const tag = screen.getByText(label);

    expect(tag).toHaveClass("tag", tone);
    expect(tag).toHaveAttribute("data-status", status);
  });

  it("pendiente de pago lleva la clase warning (decisión Q3)", () => {
    render(<StatusTag status="pending_payment" />);

    expect(screen.getByText("Pendiente de pago")).toHaveClass("warning");
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(
      <ul>
        {CASES.map(([status]) => (
          <li key={status}>
            <StatusTag status={status} />
          </li>
        ))}
      </ul>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
