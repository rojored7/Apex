// S8-F3 · US-172 (front): las sesiones que usan el WOD (GET /class-sessions?wod_id). Cada una enlaza a la tablet de resultados.
// DESIGN-GAP: WOD_Detalle.html no dibuja la lista de sesiones; asignar el WOD a otra sesión se hace desde Clases.
import { Link } from "react-router";
import { formatDate, formatTime24 } from "../../../core/i18n/format";
import { useWodSessions, type WodSessionView } from "../../../shared/data/results";
import { Button } from "../../../shared/ui/Button";
import { resultsLoadError } from "../../../shared/data/resultErrors";
import styles from "./WodSessions.module.css";

export const SESSIONS_EMPTY = "Ninguna clase usa este WOD todavía. Asígnalo a una sesión desde Clases.";

const STATUS_LABELS: Readonly<Record<WodSessionView["status"], string>> = { scheduled: "Programada", cancelled: "Cancelada", done: "Realizada" };

export function WodSessions({ wodId, canRecord }: { wodId: string; canRecord: boolean }) {
  const sessions = useWodSessions(wodId);
  const error = resultsLoadError(sessions.error);
  const items = sessions.data?.items ?? [];
  return (
    <section className={styles.sessions} aria-labelledby="wod-sessions-title">
      <h2 id="wod-sessions-title" className={styles.title}>
        Sesiones con este WOD
      </h2>
      {error ? (
        <div role="alert" className={styles.error}>
          <p>{error.message}</p>
          <Button
            variant="secondary"
            onClick={() => {
              void sessions.refetch();
            }}
          >
            Reintentar
          </Button>
        </div>
      ) : sessions.isLoading ? (
        <p role="status" className={styles.note}>
          Cargando las sesiones…
        </p>
      ) : items.length === 0 ? (
        <p className={styles.note}>{SESSIONS_EMPTY}</p>
      ) : (
        <ul className={styles.list}>
          {items.map((session) => (
            <li key={session.id} className={styles.row}>
              <span>
                <b>{`${formatDate(session.session_date)} · ${formatTime24(session.starts_at)}`}</b>
                {` · ${session.name ?? (session.coach_name ? `Coach ${session.coach_name}` : "Open box")} · ${String(session.attendance_count)} asistentes · ${STATUS_LABELS[session.status]}`}
              </span>
              {canRecord && session.status === "scheduled" ? <Link to={`/clases/${encodeURIComponent(session.id)}/resultados`}>Registrar resultados</Link> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
