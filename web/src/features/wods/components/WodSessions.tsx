// S8-F3 · US-172 (front): las sesiones que usan el WOD (GET /class-sessions?wod_id). Cada una enlaza a la tablet de resultados.
// DESIGN-GAP: WOD_Detalle.html no dibuja la lista de sesiones; asignar el WOD a otra sesión se hace desde Clases.
import { useState } from "react";
import { Link } from "react-router";
import { formatDate, addDaysCivil, formatTime24, todayBogota } from "../../../core/i18n/format";
import { useWodSessions, type WodSessionView } from "../../../shared/data/results";
import { Button } from "../../../shared/ui/Button";
import { Chips } from "../../../shared/ui/Chips";
import { Pagination } from "../../../shared/ui/Pagination";
import { resultsLoadError } from "../../../shared/data/resultErrors";
import styles from "./WodSessions.module.css";

export const SESSIONS_EMPTY = "Ninguna clase usa este WOD todavía. Asígnalo a una sesión desde Clases.";
/** El api acepta ventanas de hasta 62 días (MAX_RANGE_DAYS): hoy y los 61 días siguientes. */
const UPCOMING_DAYS = 61;
export const SESSIONS_EMPTY_UPCOMING = "No hay clases próximas con este WOD.";

type SessionsScope = "upcoming" | "all";
// «Día del WOD» no manda ventana: el api devuelve las sesiones del día del WOD (S8-A4b, L-1).
const SCOPE_OPTIONS = [
  { value: "upcoming", label: "Próximas" },
  { value: "all", label: "Día del WOD" },
];

const STATUS_LABELS: Readonly<Record<WodSessionView["status"], string>> = { scheduled: "Programada", cancelled: "Cancelada", done: "Realizada" };

function upcomingWindow(scope: SessionsScope): { from?: string; to?: string } {
  if (scope !== "upcoming") return {};
  const from = todayBogota();
  const to = addDaysCivil(from, UPCOMING_DAYS);
  return to === null ? { from, to: from } : { from, to };
}

export function WodSessions({ wodId, canRecord }: { wodId: string; canRecord: boolean }) {
  const [scope, setScope] = useState<SessionsScope>("upcoming");
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);
  const sessions = useWodSessions(wodId, { limit, offset, ...upcomingWindow(scope) });
  const error = resultsLoadError(sessions.error);
  const items = sessions.data?.items ?? [];
  const total = sessions.data?.total ?? 0;
  return (
    <section className={styles.sessions} aria-labelledby="wod-sessions-title">
      <h2 id="wod-sessions-title" className={styles.title}>
        Sesiones con este WOD
      </h2>
      <Chips
        label="Sesiones"
        mode="single"
        options={SCOPE_OPTIONS}
        value={[scope]}
        onChange={(next) => {
          const chosen = next[0];
          if (chosen === undefined) return;
          setScope(chosen === "all" ? "all" : "upcoming");
          setOffset(0);
        }}
      />
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
        <p className={styles.note}>{scope === "upcoming" ? SESSIONS_EMPTY_UPCOMING : SESSIONS_EMPTY}</p>
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
      {total > 0 ? (
        <Pagination
          label="Paginación de sesiones"
          total={total}
          limit={limit}
          offset={offset}
          onPageChange={(next) => {
            setOffset((next - 1) * limit);
          }}
          onLimitChange={(next) => {
            setLimit(next);
            setOffset(0);
          }}
        />
      ) : null}
    </section>
  );
}
