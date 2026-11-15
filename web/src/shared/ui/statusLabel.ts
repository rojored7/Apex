import type { components } from "../../core/api/types";

/**
 * Estado de membresía tal como lo ve el front: los seis del enum `MembershipStatus` del contrato más
 * `none` (socio sin membresía, consulta derivada `membership_status`). Fase 4 del Sprint 3 (L1): sale
 * de types.ts; un estado nuevo en el contrato rompe la compilación de STATUS_LABELS y STATUS_TONES.
 */
export type MembershipStatusView = components["schemas"]["MembershipStatus"] | "none";

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

/** ¿Es `value` un estado que StatusTag sabe pintar? Un texto desconocido (un estado nuevo) no lo es. */
export function isMembershipStatusView(value: string): value is MembershipStatusView {
  return Object.hasOwn(STATUS_LABELS, value);
}

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

/**
 * S6-F1 · US-142: estado de la firma de la cadena de auditoría. Lo decide el api (`state`, `is_late`,
 * `latest`); aquí solo se pinta. Sin «no verificable»: la verificación no depende del custodio (S6-D81).
 */
export type SignatureStateView = "intact" | "altered" | "late" | "none";

export const SIGNATURE_LABELS = Object.freeze({
  intact: "Íntegra",
  altered: "Alterada",
  late: "Firma atrasada",
  none: "Sin firmas",
} as const satisfies Record<SignatureStateView, string>);

/** Íntegra como «al día»; atrasada como advertencia; alterada como error; sin firmas neutro. */
export const SIGNATURE_TONES = Object.freeze({
  intact: "ok",
  altered: "danger",
  late: "warning",
  none: "neutral",
} as const satisfies Record<SignatureStateView, StatusTone>);

export function signatureLabel(state: SignatureStateView): string {
  return SIGNATURE_LABELS[state];
}

export function signatureTone(state: SignatureStateView): StatusTone {
  return SIGNATURE_TONES[state];
}

/**
 * S6-F2 · US-143, US-145: estado de una llave de cifrado (`CryptoKeyOut.state`) o de un trabajo de
 * rotación o recifrado (`CryptoJobOut.status`). Dos listas distintas del contrato, una sola píldora.
 */
export type CryptoStatusView = "active" | "decrypt_only" | "retired" | "pending" | "running" | "done" | "failed";

export const CRYPTO_LABELS = Object.freeze({
  active: "Activa",
  decrypt_only: "Solo descifrar",
  retired: "Retirada",
  pending: "Pendiente",
  running: "En curso",
  done: "Terminado",
  failed: "Falló",
} as const satisfies Record<CryptoStatusView, string>);

/** Activa y terminado como «al día»; solo descifrar y en curso piden atención; falló es error. */
export const CRYPTO_TONES = Object.freeze({
  active: "ok",
  decrypt_only: "warning",
  retired: "neutral",
  pending: "neutral",
  running: "warning",
  done: "ok",
  failed: "danger",
} as const satisfies Record<CryptoStatusView, StatusTone>);

export function cryptoLabel(status: CryptoStatusView): string {
  return CRYPTO_LABELS[status];
}

export function cryptoTone(status: CryptoStatusView): StatusTone {
  return CRYPTO_TONES[status];
}

/** S7-F3b (M3): estado de una franja del horario (Horario.html, w-tag «Activa» o «Pausada»). */
export type SlotStateView = "active" | "paused";

export const SLOT_LABELS = Object.freeze({
  active: "Activa",
  paused: "Pausada",
} as const satisfies Record<SlotStateView, string>);

/** Activa es «al día»; pausada es neutra (no genera sesiones nuevas, pero no es un error). */
export const SLOT_TONES = Object.freeze({
  active: "ok",
  paused: "neutral",
} as const satisfies Record<SlotStateView, StatusTone>);

export function slotLabel(state: SlotStateView): string {
  return SLOT_LABELS[state];
}

export function slotTone(state: SlotStateView): StatusTone {
  return SLOT_TONES[state];
}

/**
 * S7-F4 (BRECHAS 15.6): las siete banderas de un check-in (`CHECKIN_FLAGS` del api). Las cuatro de membresía
 * se pintan en rojo (el coach habla con el socio después); cupo lleno, fuera de horario y otro día son
 * advertencias: la llegada se registró y nunca es un error (N-38, N-39, S7-D27).
 */
export type FlagView = "expired" | "no_membership" | "frozen" | "pending_payment" | "over_capacity" | "out_of_window" | "other_day";

export const FLAG_LABELS = Object.freeze({
  expired: "Vencido",
  no_membership: "Sin plan",
  frozen: "Congelado",
  pending_payment: "Pendiente de pago",
  over_capacity: "Cupo lleno",
  out_of_window: "Fuera de horario",
  other_day: "Otro día",
} as const satisfies Record<FlagView, string>);

export const FLAG_TONES = Object.freeze({
  expired: "danger",
  no_membership: "danger",
  // S7-V7f (M-6): congelado y pendiente de pago llevan el mismo tono que como estado de membresía (STATUS_TONES).
  frozen: "neutral",
  pending_payment: "warning",
  over_capacity: "warning",
  out_of_window: "warning",
  other_day: "warning",
} as const satisfies Record<FlagView, StatusTone>);

export function isFlagView(value: string): value is FlagView {
  return Object.hasOwn(FLAG_LABELS, value);
}

export function flagLabel(flag: FlagView): string {
  return FLAG_LABELS[flag];
}

export function flagTone(flag: FlagView): StatusTone {
  return FLAG_TONES[flag];
}
