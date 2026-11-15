// S7-F4 · US-159 y US-161 (front): «Ya llegaron (N)» (CheckIn.html, columna derecha).
// Cada asistente con la hora de Bogotá, sus banderas con texto («Vencida», «Otro día»...) y «Quitar» (motivo opcional).
// DESIGN-GAP: CheckIn.html muestra «saldo pendiente» y «vence hoy» junto a la hora; AttendeeOut solo trae las banderas, así que se
// muestran estas. «Ver asistencia completa» y «Terminó la clase → registrar resultados» salen a pantallas del panel (o de v0.5, wods
// y results): en modo tablet no hay enlaces al panel (S7-D24), por eso no se dibujan.
import { useState } from "react";
import { formatTime24 } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { StatusTag } from "../../../shared/ui/StatusTag";
import type { AttendeeView } from "../api";
import { knownFlags } from "../flags";
import styles from "./AttendeeList.module.css";
import { RemoveAttendanceModal } from "./RemoveAttendanceModal";

export interface AttendeeListProps {
  attendees: readonly AttendeeView[];
}

export const REMOVE_NOTE = "«Quitar» borra la llegada y queda en la auditoría. El coach solo puede quitar las de hoy o ayer.";

export function AttendeeList({ attendees }: AttendeeListProps) {
  const [target, setTarget] = useState<AttendeeView | null>(null);
  return (
    <section className={styles.box} aria-labelledby="attendees-title">
      <h2 id="attendees-title" className={styles.title}>{`Ya llegaron (${String(attendees.length)})`}</h2>
      {attendees.length === 0 ? (
        <p className={styles.empty}>Todavía no llegó nadie. Busca al primer socio y toca «Llegó».</p>
      ) : (
        <ul className={styles.list} aria-label="Asistentes">
          {attendees.map((attendee) => {
            const name = `${attendee.first_name} ${attendee.last_name}`.trim();
            return (
              <li key={attendee.id} className={styles.row}>
                <b className={styles.name}>{name}</b>
                <span className={styles.time}>{formatTime24(attendee.checked_in_at)}</span>
                {knownFlags(attendee.flags).map((flag) => (
                  <StatusTag key={flag} flag={flag} />
                ))}
                <Button
                  size="lg"
                  variant="secondary"
                  aria-label={`Quitar a ${name}`}
                  onClick={() => {
                    setTarget(attendee);
                  }}
                >
                  Quitar
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      <p className={styles.note}>{REMOVE_NOTE}</p>
      <RemoveAttendanceModal
        attendee={target}
        onClose={() => {
          setTarget(null);
        }}
      />
    </section>
  );
}
