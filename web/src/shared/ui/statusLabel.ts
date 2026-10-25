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

/**
 * S2-D24: estado de una cuenta de usuario (`UserRow.status` del contrato de B3, cinco valores).
 */
export type AccountStatusView = "active" | "pending_activation" | "locked" | "inactive" | "deleted";

export const ACCOUNT_LABELS = Object.freeze({
  active: "Activo",
  pending_activation: "Pendiente de activación",
  locked: "Bloqueado",
  inactive: "Inactivo",
  deleted: "Dado de baja",
} as const satisfies Record<AccountStatusView, string>);

/** Tonos de la decisión 24 del blueprint: bloqueado es error, pendiente es advertencia. */
export const ACCOUNT_TONES = Object.freeze({
  active: "ok",
  pending_activation: "warning",
  locked: "danger",
  // DESIGN.md: "Congelado / Inactivo: borde --line, texto --muted".
  inactive: "neutral",
  deleted: "neutral",
} as const satisfies Record<AccountStatusView, StatusTone>);

export function accountLabel(status: AccountStatusView): string {
  return ACCOUNT_LABELS[status];
}

export function accountTone(status: AccountStatusView): StatusTone {
  return ACCOUNT_TONES[status];
}

/**
 * S3-F6: estado de un pago (Pagos.html). Un pago está vigente o anulado; nunca se edita ni se borra
 * (DESIGN.md regla 4).
 */
export type PaymentStatusView = "valid" | "voided";

export const PAYMENT_LABELS = Object.freeze({
  valid: "Válido",
  voided: "Anulado",
} as const satisfies Record<PaymentStatusView, string>);

/** Pagos.html: "Válido" con el relleno de "al día"; "Anulado" neutro (borde line, texto muted). */
export const PAYMENT_TONES = Object.freeze({
  valid: "ok",
  voided: "neutral",
} as const satisfies Record<PaymentStatusView, StatusTone>);

export function paymentLabel(status: PaymentStatusView): string {
  return PAYMENT_LABELS[status];
}

export function paymentTone(status: PaymentStatusView): StatusTone {
  return PAYMENT_TONES[status];
}
