export type MembershipStatusView = "active" | "expiring" | "expired" | "frozen" | "cancelled" | "pending_payment" | "none";
export type StatusTone = "ok" | "warning" | "danger" | "neutral";

export const STATUS_LABELS = {} as Record<MembershipStatusView, string>;
export const STATUS_TONES = {} as Record<MembershipStatusView, StatusTone>;

export function statusLabel(_status: MembershipStatusView): string {
  return "";
}

export function statusTone(_status: MembershipStatusView): StatusTone {
  return "neutral";
}
