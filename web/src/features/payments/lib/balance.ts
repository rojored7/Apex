// S3-F4 · US-095 (front): cómo se ofrece el saldo de una membresía en el panel de pagos. Fase 4 del
// Sprint 3 (M4): la regla del saldo (Q5, S3-D41) vive en shared/lib/balance.ts, la misma de la venta.
import { formatCop, formatDateRange } from "../../../core/i18n/format";
import type { MembershipRowView } from "../../../shared/data/memberships";
import { balanceOf } from "../../../shared/lib/balance";

export { balanceOf, excessOver } from "../../../shared/lib/balance";

/** "Mensual 25 oct–24 nov". */
export function membershipText(membership: Pick<MembershipRowView, "plan_name" | "start_date" | "end_date">): string {
  return `${membership.plan_name} ${formatDateRange(membership.start_date, membership.end_date)}`;
}

/** "Mensual 25 oct–24 nov · saldo $ 60.000" o "… · sin saldo pendiente" (Pagos.html). */
export function membershipOptionText(membership: Pick<MembershipRowView, "plan_name" | "start_date" | "end_date" | "agreed_price_cop" | "paid_cop">): string {
  const balance = balanceOf(membership);
  return `${membershipText(membership)} · ${balance > 0 ? `saldo ${formatCop(balance)}` : "sin saldo pendiente"}`;
}
