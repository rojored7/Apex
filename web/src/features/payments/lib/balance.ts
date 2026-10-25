// S3-F4 · US-095 (front): el saldo de una membresía y cómo se ofrece en el panel de pagos. Manda el
// servidor: el saldo sale de `agreed_price_cop - paid_cop` (B7) y el 409 `payment_exceeds_balance`
// confirma lo mismo bajo el candado (S3-D41). Q5: un pago mayor al saldo no deja saldo a favor.
import { formatCop, formatDateRange } from "../../../core/i18n/format";
import type { MembershipRowView } from "../../../shared/data/memberships";

type Priced = Pick<MembershipRowView, "agreed_price_cop" | "paid_cop">;

/** Lo que falta pagar; nunca negativo. */
export function balanceOf(membership: Priced): number {
  return Math.max(membership.agreed_price_cop - membership.paid_cop, 0);
}

/** Cuánto supera el pago al saldo, o 0. */
export function excessOver(balance: number, amount: number): number {
  return Math.max(amount - balance, 0);
}

/** "Mensual 25 oct–24 nov". */
export function membershipText(membership: Pick<MembershipRowView, "plan_name" | "start_date" | "end_date">): string {
  return `${membership.plan_name} ${formatDateRange(membership.start_date, membership.end_date)}`;
}

/** "Mensual 25 oct–24 nov · saldo $ 60.000" o "… · sin saldo pendiente" (Pagos.html). */
export function membershipOptionText(membership: Pick<MembershipRowView, "plan_name" | "start_date" | "end_date" | "agreed_price_cop" | "paid_cop">): string {
  const balance = balanceOf(membership);
  return `${membershipText(membership)} · ${balance > 0 ? `saldo ${formatCop(balance)}` : "sin saldo pendiente"}`;
}
