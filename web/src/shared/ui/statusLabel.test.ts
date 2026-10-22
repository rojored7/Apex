import type { components } from "../../core/api/types";
import {
  ACCOUNT_LABELS,
  ACCOUNT_TONES,
  STATUS_LABELS,
  STATUS_TONES,
  accountLabel,
  accountTone,
  statusLabel,
  statusTone,
  type AccountStatusView,
  type MembershipStatusView,
  type StatusTone,
} from "./statusLabel";

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

describe("estados de cuenta (S2-D24)", () => {
  const ACCOUNT = {
    active: { label: "Activo", tone: "ok" },
    pending_activation: { label: "Pendiente de activación", tone: "warning" },
    locked: { label: "Bloqueado", tone: "danger" },
    inactive: { label: "Inactivo", tone: "neutral" },
    deleted: { label: "Dado de baja", tone: "neutral" },
  } as const satisfies Record<AccountStatusView, { label: string; tone: StatusTone }>;
  const ACCOUNT_STATUSES = Object.keys(ACCOUNT) as AccountStatusView[];

  it.each(ACCOUNT_STATUSES)("%s tiene etiqueta en español y tono", (status) => {
    expect(accountLabel(status)).toBe(ACCOUNT[status].label);
    expect(accountTone(status)).toBe(ACCOUNT[status].tone);
  });

  it("cubre exactamente los cinco estados del contrato y es inmutable", () => {
    expect(Object.keys(ACCOUNT_LABELS).sort()).toEqual([...ACCOUNT_STATUSES].sort());
    expect(Object.keys(ACCOUNT_TONES).sort()).toEqual([...ACCOUNT_STATUSES].sort());
    expect(Object.isFrozen(ACCOUNT_LABELS)).toBe(true);
    expect(Object.isFrozen(ACCOUNT_TONES)).toBe(true);
  });

  it("coincide con el enum de UserRow.status del contrato", () => {
    type ContractStatus = components["schemas"]["UserRow"]["status"];
    const same: [ContractStatus] extends [AccountStatusView] ? ([AccountStatusView] extends [ContractStatus] ? true : false) : false = true;

    expect(same).toBe(true);
  });
});
