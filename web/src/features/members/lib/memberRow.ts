// S3-F2 (US-071, US-072): lo que la tabla y las tarjetas de /socios dicen de una fila de
// GET /members (MemberRowOut, sin nada cifrado ni enmascarado, N-01).
// - membershipStatusOf: el `membership_status` resuelto si es uno que StatusTag sabe pintar; otro
//   texto (un estado nuevo del api) no se pinta.
// - accountStatusOf: la cuenta del socio para StatusTag ("Dado de baja" manda sobre el estado).
// - membershipDetail: la línea de la tarjeta de Socios_Movil.html ("Mensual · vence 28 oct 2026",
//   "12 clases · venció 15 oct 2026" o "Sin membresía"); la fecha con año (DESIGN.md regla 7).
import { formatDate } from "../../../core/i18n/format";
import { isMembershipStatusView, type AccountStatusView, type MembershipStatusView } from "../../../shared/ui/statusLabel";
import type { MemberRowView } from "../schemas";

export const NO_MEMBERSHIP_TEXT = "Sin membresía";

export function membershipStatusOf(row: Pick<MemberRowView, "membership_status">): MembershipStatusView | null {
  const value = row.membership_status;
  return value !== null && isMembershipStatusView(value) ? value : null;
}

export function accountStatusOf(row: Pick<MemberRowView, "status" | "deleted_at">): AccountStatusView {
  return row.deleted_at ? "deleted" : row.status;
}

export function membershipDetail(row: Pick<MemberRowView, "membership_status" | "plan_name" | "membership_end_date">): string {
  if (!row.plan_name || row.membership_status === "none") return NO_MEMBERSHIP_TEXT;
  if (!row.membership_end_date) return row.plan_name;
  const verb = row.membership_status === "expired" ? "venció" : "vence";
  return `${row.plan_name} · ${verb} ${formatDate(row.membership_end_date)}`;
}
