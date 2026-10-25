// S3-F6: textos de un pago que comparten la lista de /pagos y su detalle.
// - memberName: "Laura Gómez" (nombre y apellido van en claro, CLAUDE.md).
// - memberHref: la ficha del socio.
// - membershipText: "Mensual 29 oct–28 nov" (Pagos.html), con formatDateRange.
import { formatDateRange } from "../../../core/i18n/format";
import type { PaymentRowView } from "../schemas";

export const memberName = (row: Pick<PaymentRowView, "member_first_name" | "member_last_name">): string => `${row.member_first_name} ${row.member_last_name}`;

export const memberHref = (memberId: string): string => `/socios/${encodeURIComponent(memberId)}`;

export const membershipText = (row: Pick<PaymentRowView, "plan_name" | "membership_start_date" | "membership_end_date">): string =>
  `${row.plan_name} ${formatDateRange(row.membership_start_date, row.membership_end_date)}`;
