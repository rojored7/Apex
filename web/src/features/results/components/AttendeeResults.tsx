// S8-F4 · US-169 (front): «Asistieron (toca uno)» (Resultados_Registro.html, columna izquierda). Cada asistente muestra su marca
// («10:58 RX») o «sin registrar»; el elegido lleva aria-current. Botones de 56 px (tablet).
import { markText, attendeeName, type AttendeeResultView, type ScoringType } from "../schemas";
import styles from "./AttendeeResults.module.css";

export interface AttendeeResultsProps {
  attendees: readonly AttendeeResultView[];
  scoreType: ScoringType;
  selectedId: string | null;
  onSelect: (memberId: string) => void;
}

export function AttendeeResults({ attendees, scoreType, selectedId, onSelect }: AttendeeResultsProps) {
  return (
    <ul className={styles.list} aria-label="Asistieron">
      {attendees.map((attendee) => {
        const isOn = attendee.member_id === selectedId;
        return (
          <li key={attendee.member_id}>
            <button
              type="button"
              className={styles.row}
              data-done={attendee.has_result}
              {...(isOn ? { "aria-current": "true" as const } : {})}
              onClick={() => {
                onSelect(attendee.member_id);
              }}
            >
              <span className={styles.name}>{attendeeName(attendee)}</span>
              {attendee.result ? <b className={styles.mark}>{markText(attendee.result, scoreType)}</b> : <span className={styles.pending}>sin registrar</span>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
