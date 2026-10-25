// S3-F3 · reglas de la vista previa de la venta (US-084, US-085). Manda el servidor: esto solo pinta
// lo que el api va a calcular, y el 201 trae los valores definitivos.
// - computeEndDate: fin inclusivo `inicio + duration_days` (RN-05, N-23, `compute_end_date` de
//   memberships/rules.py). DESIGN-GAP (D16): Membresia_Vender.html dibuja "29 oct – 27 nov" para un
//   mes desde el 29 oct; por N-23 el fin es el 28 nov y la pantalla dice "hasta el 28 nov 2026".
// - saldo, exceedsBalance y excessOver: Q5 y S3-D41. Un pago que supera el saldo se confirma; no
//   queda saldo a favor.
// - planTermsText: lo que dice cada plan en el selector ("30 días · $ 120.000").
import { addDaysCivil, formatCop, formatCount, formatDate } from "../../../core/i18n/format";
import type { PlanKind } from "../../../shared/data/plans";

export interface PlanTerms {
  kind: PlanKind;
  duration_days: number;
  class_count: number | null;
  price_cop: number;
}

/** Fin de la vigencia ("AAAA-MM-DD"), o null sin una fecha de inicio válida. */
export function computeEndDate(startDate: string, durationDays: number): string | null {
  return addDaysCivil(startDate, durationDays);
}

/** "hasta el 28 nov 2026". */
export function untilText(endDate: string): string {
  return `hasta el ${formatDate(endDate)}`;
}

/** Lo que falta para el precio; nunca negativo. */
export function saldo(price: number, paid: number): number {
  return Math.max(price - paid, 0);
}

/** ¿El pago supera el saldo (y hay que confirmarlo)? */
export function exceedsBalance(price: number, paid: number, amount: number): boolean {
  return amount > saldo(price, paid);
}

/** Cuánto supera el pago al saldo, o 0. */
export function excessOver(price: number, paid: number, amount: number): number {
  return Math.max(amount - saldo(price, paid), 0);
}

const daysText = (days: number): string => (days === 1 ? "1 día" : `${formatCount(days)} días`);

/** "30 días · $ 120.000" o "12 clases · 60 días para usarlas · $ 110.000". */
export function planTermsText(plan: PlanTerms): string {
  const price = formatCop(plan.price_cop);
  if (plan.kind === "classes" && plan.class_count !== null) {
    const classes = plan.class_count === 1 ? "1 clase" : `${formatCount(plan.class_count)} clases`;
    const use = plan.class_count === 1 ? "para usarla" : "para usarlas";
    return `${classes} · ${daysText(plan.duration_days)} ${use} · ${price}`;
  }
  return `${daysText(plan.duration_days)} · ${price}`;
}
