import { STATUS_LABELS, STATUS_TONES, statusLabel, statusTone, type MembershipStatusView, type StatusTone } from "./statusLabel";

const EXPECTED = {
  active: { label: "Al día", tone: "ok" },
  expiring: { label: "Por vencer", tone: "warning" },
  expired: { label: "Vencido", tone: "danger" },
  frozen: { label: "Congelado", tone: "neutral" },
  cancelled: { label: "Cancelado", tone: "neutral" },
  pending_payment: { label: "Pendiente de pago", tone: "warning" },
  none: { label: "Sin plan", tone: "danger" },
} as const satisfies Record<MembershipStatusView, { label: string; tone: StatusTone }>;

const STATUSES = Object.keys(EXPECTED) as MembershipStatusView[];

describe("statusLabel", () => {
  it.each(STATUSES)("devuelve la etiqueta en español de %s", (status) => {
    expect(statusLabel(status)).toBe(EXPECTED[status].label);
  });

  it("cubre exactamente los siete estados", () => {
    expect(Object.keys(STATUS_LABELS).sort()).toEqual([...STATUSES].sort());
    expect(Object.keys(STATUS_TONES).sort()).toEqual([...STATUSES].sort());
  });
});

describe("statusTone", () => {
  it.each(STATUSES)("devuelve el tono de DESIGN.md para %s", (status) => {
    expect(statusTone(status)).toBe(EXPECTED[status].tone);
  });

  it("pinta pendiente de pago igual que por vencer (decisión Q3)", () => {
    expect(statusTone("pending_payment")).toBe(statusTone("expiring"));
  });
});

describe("constantes de estado", () => {
  it("son inmutables", () => {
    expect(Object.isFrozen(STATUS_LABELS)).toBe(true);
    expect(Object.isFrozen(STATUS_TONES)).toBe(true);
  });
});
