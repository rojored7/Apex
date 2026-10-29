// S4A-F3 · US-109 (front): a dónde lleva cada KPI de Inicio.
// - Membresías: /socios con el chip del estado (`membership_status`, los nombres del api; D22).
// - Ingresos: /pagos con el mes de Bogotá de `today` (el día civil del api). /pagos lee `from` y `to`
//   como días civiles de Bogotá, `to` incluido (usePaymentFilters, S3-F6), y los lleva al rango UTC
//   [día 1 a las 05:00Z, día 1 del mes siguiente a las 05:00Z) que pidió el plan; por eso el enlace
//   lleva los días y no los instantes (desviación anotada en el cuaderno del front, F3.2). Una fecha
//   que no es real deja /pagos sin rango.
import { addDaysCivil } from "../../core/i18n/format";
import { MEMBERS_PATH, PAYMENTS_PATH } from "../../shared/lib/routes";

export interface KpiLinks {
  active: string;
  expiring: string;
  expired: string;
  pendingPayment: string;
  income: string;
}

type MembershipChip = "active" | "expiring" | "expired" | "pending_payment";

const membersWith = (status: MembershipChip): string => `${MEMBERS_PATH}?${new URLSearchParams({ membership_status: status }).toString()}`;

/** El primer y el último día del mes civil de `day`, o null si `day` no es una fecha real. */
function monthOf(day: string): { first: string; last: string } | null {
  if (addDaysCivil(day, 0) !== day) return null;
  const first = `${day.slice(0, 7)}-01`;
  const [year, month] = [Number(day.slice(0, 4)), Number(day.slice(5, 7))];
  const nextFirst = month === 12 ? `${String(year + 1)}-01-01` : `${String(year)}-${String(month + 1).padStart(2, "0")}-01`;
  const last = addDaysCivil(nextFirst, -1);
  return last === null ? null : { first, last };
}

export function kpiLinks(today: string): KpiLinks {
  const month = monthOf(today);
  return {
    active: membersWith("active"),
    expiring: membersWith("expiring"),
    expired: membersWith("expired"),
    pendingPayment: membersWith("pending_payment"),
    income: month ? `${PAYMENTS_PATH}?${new URLSearchParams({ from: month.first, to: month.last }).toString()}` : PAYMENTS_PATH,
  };
}
