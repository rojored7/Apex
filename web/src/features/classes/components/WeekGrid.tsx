// S7-F3 · US-157 (front): la rejilla de la semana de Sesiones.html: siete columnas de lunes a domingo, hoy resaltado
// («Mar 20 · hoy»), «Sin clases» en los días vacíos. Cada sesión es un botón con hora, coach y cupo:
// - Cancelada: borde punteado y el texto «Cancelada · motivo» (nunca solo el estilo).
// - Llena: texto «Llena»; terminada: «Terminada»; sesión extra (sin franja): «Extra».
// - Elegirla muestra su detalle debajo (`aria-pressed`).
// DESIGN-GAP: el diseño enlaza cada sesión al check-in; aquí elegir una sesión abre su detalle y desde ahí «Abrir check-in»,
// para que cancelar y abrir el check-in sean dos acciones distintas y no un solo clic ambiguo.
import { cx } from "../../../shared/ui/cx";
import type { SessionView } from "../api";
import { formatTime24 } from "../../../core/i18n/format";
import { dayHeader } from "../../../shared/data/weeks";
import styles from "./WeekGrid.module.css";

export interface WeekGridProps {
  /** Las siete fechas civiles de la semana, de lunes a domingo. */
  dates: readonly string[];
  /** Hoy en Bogotá ("AAAA-MM-DD"). */
  today: string;
  sessions: readonly SessionView[];
  selectedId: string | null;
  onSelect: (session: SessionView) => void;
}

export const NO_CLASSES = "Sin clases";
export const OPEN_BOX = "Open box";

/** «Carlos · 9/12», o «Open box · 0/20» sin coach. */
export function sessionSummary(session: SessionView): string {
  return `${session.coach_name ?? OPEN_BOX} · ${String(session.attendance_count)}/${String(session.capacity)}`;
}

function sessionNotes(session: SessionView): string[] {
  if (session.status === "cancelled") return [session.cancel_reason ? `Cancelada · ${session.cancel_reason}` : "Cancelada"];
  const notes: string[] = [];
  if (session.status === "done") notes.push("Terminada");
  else if (session.attendance_count >= session.capacity) notes.push("Llena");
  if (session.slot_id === null) notes.push("Extra");
  return notes;
}

function SessionButton({ session, selected, onSelect }: { session: SessionView; selected: boolean; onSelect: (session: SessionView) => void }) {
  const cancelled = session.status === "cancelled";
  const notes = sessionNotes(session);
  return (
    <button
      type="button"
      className={cx(styles.session, cancelled && styles.cancelled, !cancelled && session.attendance_count >= session.capacity && styles.full, selected && styles.selected)}
      aria-pressed={selected}
      data-status={session.status}
      onClick={() => {
        onSelect(session);
      }}
    >
      <b>{formatTime24(session.starts_at)}</b>
      {cancelled ? null : <span>{sessionSummary(session)}</span>}
      {notes.map((note) => (
        <span key={note} className={styles.note}>
          {note}
        </span>
      ))}
    </button>
  );
}

export function WeekGrid({ dates, today, sessions, selectedId, onSelect }: WeekGridProps) {
  return (
    <div className={styles.scroller}>
      <div className={styles.grid}>
        {dates.map((date) => {
          const header = dayHeader(date);
          const isToday = date === today;
          const daySessions = sessions.filter((s) => s.session_date === date).sort((a, b) => a.starts_at.localeCompare(b.starts_at));
          return (
            <div key={date} role="group" aria-label={isToday ? `${header} · hoy` : header} className={styles.day}>
              <h2 className={cx(styles.header, isToday && styles.today)} aria-current={isToday ? "date" : undefined}>
                {isToday ? `${header} · hoy` : header}
              </h2>
              {daySessions.length === 0 ? (
                <p className={styles.empty}>{NO_CLASSES}</p>
              ) : (
                daySessions.map((session) => <SessionButton key={session.id} session={session} selected={session.id === selectedId} onSelect={onSelect} />)
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
