import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import { paymentLabel, paymentTone, type AccountStatusView, type MembershipStatusView, type PaymentStatusView, type StatusTone } from "./statusLabel";
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

// S3-F6: estado de un pago (Pagos.html: "Válido" relleno azul, "Anulado" neutro). Un pago no tiene
// más estados: nunca se edita ni se borra (DESIGN.md regla 4).
const PAYMENT_CASES: [PaymentStatusView, string, StatusTone][] = [
  ["valid", "Válido", "ok"],
  ["voided", "Anulado", "neutral"],
];

describe("StatusTag con payment", () => {
  it.each(PAYMENT_CASES)("%s muestra '%s' con el tono %s", (payment, label, tone) => {
    render(<StatusTag payment={payment} />);
    const tag = screen.getByText(label);

    expect(tag).toHaveClass("tag", tone);
    expect(tag).toHaveAttribute("data-payment", payment);
    expect(tag).not.toHaveAttribute("data-status");
    expect(tag).not.toHaveAttribute("data-account");
  });

  it("las etiquetas y los tonos salen de statusLabel", () => {
    expect(paymentLabel("voided")).toBe("Anulado");
    expect(paymentTone("valid")).toBe("ok");
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(
      <ul>
        {PAYMENT_CASES.map(([payment]) => (
          <li key={payment}>
            <StatusTag payment={payment} className="extra" />
          </li>
        ))}
      </ul>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
