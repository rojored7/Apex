// Reglas de membresías que pinta el front. Manda el servidor: esto solo muestra lo que el api va a
// calcular, y sus respuestas traen los valores definitivos. Fase 4 del Sprint 3 (L8): un bloque por
// slice, cada uno con su encabezado: S3-F3 (venta, aquí), S3-F5 (lista y congelar) y S3-F7 (pestaña
// Membresías de la ficha).
//
// S3-F3 · la vista previa de la venta (US-084, US-085):
// - computeEndDate: fin inclusivo `inicio + duration_days` (RN-05, N-23, `compute_end_date` de
//   memberships/rules.py). DESIGN-GAP (D16): Membresia_Vender.html dibuja "29 oct – 27 nov" para un
//   mes desde el 29 oct; por N-23 el fin es el 28 nov y la pantalla dice "hasta el 28 nov 2026".
// - saldo, exceedsBalance y excessOver: Q5 y S3-D41. Un pago que supera el saldo se confirma; no
//   queda saldo a favor. Fase 4 del Sprint 3 (M4): la regla vive en shared/lib/balance.ts (la usa
//   también el panel de pagos) y aquí se reexporta; `saldo` es `balance`.
// - planTermsText: lo que dice cada plan en el selector ("30 días · $ 120.000").
import { addDaysCivil, civilDaysBetween, EMPTY_VALUE, formatCop, formatCount, formatDate } from "../../../core/i18n/format";
import { can, type Role } from "../../../core/auth/permissions";
import { isFreezableMembershipStatus, isOpenMembershipStatus, type MembershipStatus } from "../../../shared/data/memberships";
import type { PlanKind } from "../../../shared/data/plans";

export { balance as saldo, exceedsBalance, excessOver } from "../../../shared/lib/balance";

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

// S3-F5 · US-089 y US-091 (front): textos de la lista y vista previa de congelar.
// - paidText: la columna Pagado de Membresias.html. Un abono dice "$ 60.000 de $ 120.000 · abono";
//   sin pagos, "$ 0 de $ 120.000"; pagada completa, "$ 120.000 · pagado". DESIGN-GAP: el diseño
//   marca la pagada con "✓"; aquí va en palabras (el color ni un símbolo llevan solos el sentido).
// - classesRemainingText: "2 de 12" en un plan de clases; "—" en uno por días.
// - freezePreview: RN-07 y el CHECK `days_match` de 0009: los días cuentan los dos extremos
//   (`hasta - desde + 1`) y el fin se corre esos días ("Son 10 días; la membresía terminará el 10 nov
//   2026"). Fechas vacías, que no existen o invertidas no dan vista previa (el formulario las marca).
//   Manda el servidor: el 200 trae el fin definitivo. Fase 4 del Sprint 3 (L8): los días los cuenta
//   `civilDaysBetween` de core/i18n/format (antes había aquí otro lector de fechas civiles).

export function paidText(paid: number, price: number): string {
  if (paid >= price) return `${formatCop(paid)} · pagado`;
  const partial = `${formatCop(paid)} de ${formatCop(price)}`;
  return paid > 0 ? `${partial} · abono` : partial;
}

export function classesRemainingText(remaining: number | null, total: number | null): string {
  if (remaining === null || total === null) return EMPTY_VALUE;
  return `${formatCount(remaining)} de ${formatCount(total)}`;
}

export interface FreezePreview {
  /** Días congelados, contando los dos extremos. */
  days: number;
  /** El fin de la membresía corrido esos días ("AAAA-MM-DD"). */
  newEndDate: string;
  text: string;
}

export function freezePreview(from: string, to: string, endDate: string): FreezePreview | null {
  const span = civilDaysBetween(from, to);
  if (span === null || span < 0) return null;
  const days = span + 1;
  const newEndDate = addDaysCivil(endDate, days);
  if (newEndDate === null) return null;
  const count = days === 1 ? "Es 1 día" : `Son ${formatCount(days)} días`;
  return { days, newEndDate, text: `${count}; la membresía terminará el ${formatDate(newEndDate)}` };
}

// S3-F7 · US-093 (front): la pestaña Membresías de la ficha.
// - splitMemberships(memberships, today): la vigente (empezó y recibe pagos o cuenta: al día, por
//   vencer, congelada o pendiente de pago) y la futura (no anulada, empieza después de hoy). Un socio
//   tiene a lo sumo una de cada (B1, `classify_open`); si llegaran más, se toma la primera del orden
//   del api (`start_date` descendente).
// - membershipActions(memberships, role, today, memberDeleted): qué botones lleva la pestaña. Renovar
//   si no hay futura y hay vigente o la última no anulada está vencida; Vender si no hay vigente ni
//   futura; Registrar saldo sobre la vigente o la futura que recibe pagos y debe plata; Congelar solo
//   (admin y coach) la vigente al día o por vencer; Anular (solo admin) sobre la
//   vigente o la futura. Nada para un socio dado de baja (su ficha es de solo lectura, N-20). El rol se
//   mira con la matriz de US-040 (`can`); el api vuelve a verificar (RN-15).
// - daysLeftText(today, endDate): "Quedan 8 días", "Queda 1 día", "Vence hoy" o "Venció".

export interface MembershipFacts {
  id: string;
  status: MembershipStatus;
  start_date: string;
  end_date: string;
  agreed_price_cop: number;
  paid_cop: number;
}

export interface MembershipSplit<T extends MembershipFacts> {
  current: T | null;
  future: T | null;
}

export interface MembershipActions {
  renew: boolean;
  sell: boolean;
  payIds: readonly string[];
  freezeIds: readonly string[];
  cancelIds: readonly string[];
}

export const NO_MEMBERSHIP_ACTIONS: MembershipActions = Object.freeze({ renew: false, sell: false, payIds: [], freezeIds: [], cancelIds: [] });

export function splitMemberships<T extends MembershipFacts>(memberships: readonly T[], today: string): MembershipSplit<T> {
  // "AAAA-MM-DD" se compara bien como texto.
  const current = memberships.find((m) => m.start_date <= today && isOpenMembershipStatus(m.status)) ?? null;
  const future = memberships.find((m) => m.start_date > today && m.status !== "cancelled") ?? null;
  return { current, future };
}

/** La última no anulada (el api ordena por `start_date` descendente) está vencida. */
function lastIsExpired(memberships: readonly MembershipFacts[]): boolean {
  return memberships.find((m) => m.status !== "cancelled")?.status === "expired";
}

export function membershipActions(memberships: readonly MembershipFacts[], role: Role | null, today: string, memberDeleted: boolean): MembershipActions {
  if (memberDeleted) return NO_MEMBERSHIP_ACTIONS;
  const { current, future } = splitMemberships(memberships, today);
  const canSell = can(role, "memberships.sell");
  // Las de las tarjetas, en el orden del api (la futura primero).
  const open = memberships.filter((m) => m === current || m === future);
  const ids = (allowed: boolean, test: (m: MembershipFacts) => boolean): string[] => (allowed ? open.filter(test).map((m) => m.id) : []);
  return {
    renew: canSell && future === null && (current !== null || lastIsExpired(memberships)),
    sell: canSell && current === null && future === null,
    payIds: ids(can(role, "payments.register"), (m) => m.paid_cop < m.agreed_price_cop),
    // Revisión S3-F7 (M4): solo la vigente; congelar una futura cae fuera de su vigencia (422).
    freezeIds: ids(can(role, "memberships.freeze"), (m) => m === current && isFreezableMembershipStatus(m.status)),
    cancelIds: ids(can(role, "memberships.cancel"), () => true),
  };
}

export function daysLeftText(today: string, endDate: string): string {
  const days = civilDaysBetween(today, endDate);
  if (days === null) return EMPTY_VALUE;
  if (days < 0) return "Venció";
  if (days === 0) return "Vence hoy";
  return days === 1 ? "Queda 1 día" : `Quedan ${formatCount(days)} días`;
}
