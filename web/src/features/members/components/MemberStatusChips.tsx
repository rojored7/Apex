// S3-F2 · US-071 (front): chips de estado de /socios (Socios_Lista.html, Socios_Movil.html).
// - `Chips` de modo único: Todos, Al día, Por vencer, Vencidos, Congelados, Pendiente de pago,
//   Sin membresía y Dados de baja. "Dados de baja" solo con `members.view` (admin y coach, N-20).
// - Conteos (D37): los cinco estados de GET /memberships/summary (useMembershipSummary, socios por
//   la membresía que decide su estado, N-26); "Todos" es el total de socios vivos
//   (useMembersTotal) y "Sin membresía" ese total menos la suma de los cinco (nunca negativo).
//   Sin resumen o sin total, el chip va sin número; los chips siguen sirviendo.
// - El valor lo da la URL (MembersListPage); el componente solo avisa del chip elegido.
// DESIGN-GAP:
// - "Pendiente de pago" (Q3) no está dibujado en Socios_Lista.html; va con el tono de "Por vencer".
// - Socios_Movil.html muestra cuatro chips ("Al día", "Por vencer", "Vencidos", "Inactivos") y
//   pliega los filtros en "Filtros ▾"; el celular usa los mismos ocho chips del escritorio,
//   desplazables en su caja, y la FilterBar apilada (ver FilterBar.tsx).
import { useCan } from "../../../core/auth/useCan";
import { useMembershipSummary, type MembershipSummaryView } from "../../../shared/data/memberships";
import { Chips, type ChipOption } from "../../../shared/ui/Chips";
import { useMembersTotal } from "../api";
import { DELETED_STATUS, MEMBERSHIP_CHIP_LABELS, MEMBERSHIP_CHIPS, type MemberChip } from "../schemas";

export interface MemberStatusChipsProps {
  value: MemberChip | null;
  onChange: (chip: MemberChip | null) => void;
}

const ALL_CHIP = "all";

const TONES: Partial<Record<MemberChip, ChipOption["tone"]>> = {
  expiring: "warning",
  pending_payment: "warning",
  expired: "danger",
};

/** "Sin membresía": los socios vivos que no cuenta ningún estado del resumen. */
export function withoutMembership(total: number, summary: MembershipSummaryView): number {
  const counted = summary.active + summary.expiring + summary.expired + summary.frozen + summary.pending_payment;
  return Math.max(0, total - counted);
}

function countOf(chip: MemberChip, total: number | undefined, summary: MembershipSummaryView | undefined): number | undefined {
  if (chip === DELETED_STATUS || summary === undefined) return undefined;
  if (chip === "none") return total === undefined ? undefined : withoutMembership(total, summary);
  return summary[chip];
}

export function MemberStatusChips({ value, onChange }: MemberStatusChipsProps) {
  const canSeeDeleted = useCan("members.view");
  const summary = useMembershipSummary().data;
  const total = useMembersTotal().data;

  const visible = MEMBERSHIP_CHIPS.filter((chip) => chip !== DELETED_STATUS || canSeeDeleted);
  const options: ChipOption[] = [
    { value: ALL_CHIP, label: "Todos", ...(total === undefined ? {} : { count: total }) },
    ...visible.map((chip) => {
      const count = countOf(chip, total, summary);
      const tone = TONES[chip];
      return { value: chip, label: MEMBERSHIP_CHIP_LABELS[chip], ...(count === undefined ? {} : { count }), ...(tone ? { tone } : {}) };
    }),
  ];

  return (
    <Chips
      label="Estado"
      mode="single"
      options={options}
      value={[value ?? ALL_CHIP]}
      onChange={(next) => {
        const picked = visible.find((chip) => next.includes(chip));
        onChange(picked ?? null);
      }}
    />
  );
}
