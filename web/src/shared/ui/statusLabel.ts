/**
 * Estado de membresía tal como lo ve el front: los seis de `Membership.status` más
 * `none` (socio sin membresía, consulta derivada `membership_status`).
 * Cuando US-059 genere los tipos desde `docs/openapi.json`, este tipo debe coincidir con el enum.
 */
export type MembershipStatusView = "active" | "expiring" | "expired" | "frozen" | "cancelled" | "pending_payment" | "none";

/** Tono visual del estado según docs/design/DESIGN.md (Estados de membresía). */
export type StatusTone = "ok" | "warning" | "danger" | "neutral";

export const STATUS_LABELS = Object.freeze({
  active: "Al día",
  expiring: "Por vencer",
  expired: "Vencido",
  frozen: "Congelado",
  cancelled: "Cancelado",
  pending_payment: "Pendiente de pago",
  none: "Sin plan",
} as const satisfies Record<MembershipStatusView, string>);

export const STATUS_TONES = Object.freeze({
  active: "ok",
  expiring: "warning",
  expired: "danger",
  frozen: "neutral",
  cancelled: "neutral",
  // Decisión Q3: pendiente de pago se pinta igual que por vencer.
  pending_payment: "warning",
  none: "danger",
} as const satisfies Record<MembershipStatusView, StatusTone>);

export function statusLabel(status: MembershipStatusView): string {
  return STATUS_LABELS[status];
}

export function statusTone(status: MembershipStatusView): StatusTone {
  return STATUS_TONES[status];
}
