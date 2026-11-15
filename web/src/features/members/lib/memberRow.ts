// S3-F2 (US-071, US-072): lo que la tabla y las tarjetas de /socios dicen de una fila de
// GET /members (MemberRowOut, sin nada cifrado ni enmascarado, N-01).
// - membershipStatusOf: el `membership_status` resuelto si es uno que StatusTag sabe pintar; otro
//   texto (un estado nuevo del api) no se pinta.
// - accountStatusOf: la cuenta del socio para StatusTag ("Dado de baja" manda sobre el estado).
// - membershipDetail: la línea de la tarjeta de Socios_Movil.html ("Mensual · vence 28 oct 2026",
//   "12 clases · venció 15 oct 2026" o "Sin membresía"); la fecha con año (DESIGN.md regla 7).
import { civilDaysBetween, EMPTY_VALUE, formatDate, formatTime24 } from "../../../core/i18n/format";
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

/** S7-F5 (US-163): «12 clases · quedan 2» / «queda 1»; sin clases que contar, el nombre del plan. */
export function planWithClasses(row: Pick<MemberRowView, "plan_name"> & { membership_classes_remaining?: number | null }): string | null {
  if (!row.plan_name) return null;
  const left = row.membership_classes_remaining;
  if (left === null || left === undefined) return row.plan_name;
  return `${row.plan_name} · ${left === 1 ? "queda" : "quedan"} ${String(left)}`;
}

export function membershipDetail(row: Pick<MemberRowView, "membership_status" | "plan_name" | "membership_end_date"> & { membership_classes_remaining?: number | null }): string {
  const plan = planWithClasses(row);
  if (plan === null || row.membership_status === "none") return NO_MEMBERSHIP_TEXT;
  if (!row.membership_end_date) return plan;
  const verb = row.membership_status === "expired" ? "venció" : "vence";
  return `${plan} · ${verb} ${formatDate(row.membership_end_date)}`;
}

const BOGOTA_OFFSET_MS = 5 * 3_600_000;

/** El día civil de Bogotá de un instante en milisegundos ("AAAA-MM-DD"). Colombia no tiene horario de verano. */
const bogotaDay = (ms: number): string => new Date(ms - BOGOTA_OFFSET_MS).toISOString().slice(0, 10);

/**
 * S7-F5 (US-163): la última asistencia de una fila de la lista. «hoy 07:02» y «ayer 18:05» (24 horas, Bogotá), una fecha con
 * año si es anterior y «Nunca» si el api no trae instante (nunca asistió). Un instante que no es válido da «—».
 */
export function lastAttendanceText(iso: string | null | undefined, nowMs: number): string {
  if (iso === null || iso === undefined) return "Nunca";
  const time = formatTime24(iso);
  const ms = Date.parse(iso);
  if (time === EMPTY_VALUE || Number.isNaN(ms)) return EMPTY_VALUE;
  const days = civilDaysBetween(bogotaDay(ms), bogotaDay(nowMs));
  if (days === 0) return `hoy ${time}`;
  if (days === 1) return `ayer ${time}`;
  return formatDate(iso);
}
