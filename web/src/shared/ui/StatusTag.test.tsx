import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import type { AccountStatusView, MembershipStatusView, StatusTone } from "./statusLabel";
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

// S2-D24 (S2-F4a): estados de cuenta de usuario con texto en español.
const ACCOUNT_CASES: [AccountStatusView, string, StatusTone][] = [
  ["active", "Activo", "ok"],
  ["pending_activation", "Pendiente de activación", "warning"],
  ["locked", "Bloqueado", "danger"],
  ["inactive", "Inactivo", "neutral"],
  ["deleted", "Dado de baja", "neutral"],
];

describe("StatusTag con account", () => {
  it.each(ACCOUNT_CASES)("%s muestra '%s' con el tono %s", (account, label, tone) => {
    render(<StatusTag account={account} />);
    const tag = screen.getByText(label);

    expect(tag).toHaveClass("tag", tone);
    expect(tag).toHaveAttribute("data-account", account);
    expect(tag).not.toHaveAttribute("data-status");
  });

  it("acepta una clase extra", () => {
    render(<StatusTag account="locked" className="extra" />);

    expect(screen.getByText("Bloqueado")).toHaveClass("tag", "danger", "extra");
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(
      <ul>
        {ACCOUNT_CASES.map(([account]) => (
          <li key={account}>
            <StatusTag account={account} />
          </li>
        ))}
      </ul>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
