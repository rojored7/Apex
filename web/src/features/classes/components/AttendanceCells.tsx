// S7-F5 · US-162 (front): lo que la lista de asistencias dice de una fila (AttendanceRowOut), igual en la pantalla de Clases y en
// la pestaña de la ficha. Las marcas siempre con texto (el color solo refuerza); una marca que el front no conoce se descarta.
import { EMPTY_VALUE } from "../../../core/i18n/format";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { isMembershipStatusView } from "../../../shared/ui/statusLabel";
import type { AttendanceRowView } from "../attendanceApi";
import { knownFlags } from "../flags";
import styles from "./AttendanceCells.module.css";

export const NAMELESS_MEMBER = "Socio sin nombre";

export function attendanceMemberName(row: Pick<AttendanceRowView, "first_name" | "last_name">): string {
  const name = `${row.first_name ?? ""} ${row.last_name ?? ""}`.trim();
  return name === "" ? NAMELESS_MEMBER : name;
}

/** El estado de la membresía cuando llegó; uno que el front no conoce no se pinta. */
export function MembershipAtCheckin({ status }: { status: string }) {
  return isMembershipStatusView(status) ? <StatusTag status={status} /> : <>{EMPTY_VALUE}</>;
}

/** Las marcas de la llegada, una etiqueta por marca. */
export function MarksCell({ flags }: { flags: readonly string[] }) {
  const known = knownFlags(flags);
  if (known.length === 0) return <>{EMPTY_VALUE}</>;
  return (
    <span className={styles.marks}>
      {known.map((flag) => (
        <StatusTag key={flag} flag={flag} />
      ))}
    </span>
  );
}
