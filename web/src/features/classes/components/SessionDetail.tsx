// S7-F3 · US-157 (front): el detalle de la sesión elegida en Sesiones.html: título «Sesión · mar 20 oct · 17:00 · María»,
// cupo y check-ins, «Abrir check-in» (no en una cancelada) y «Cancelar sesión» (solo una programada).
// DESIGN-GAP: Sesiones.html trae «Registrar resultados» y «WOD "Helen" asignado» (llegan con v0.5, wods y results) y «Editar
// (coach, cupo, hora)»: el api no tiene editar sesión (solo cancelar y crear extra), así que ninguno de los tres se dibuja.
import { Link } from "react-router";
import { useId } from "react";
import buttonStyles from "../../../shared/ui/Button.module.css";
import { Button } from "../../../shared/ui/Button";
import { cx } from "../../../shared/ui/cx";
import type { SessionView } from "../api";
import { formatTime24 } from "../../../core/i18n/format";
import { shortDate } from "../weeks";
import styles from "./SessionDetail.module.css";
import { OPEN_BOX } from "./WeekGrid";

export interface SessionDetailProps {
  session: SessionView;
  onCancel: (session: SessionView) => void;
}

export const detailTitle = (session: SessionView): string =>
  `Sesión · ${shortDate(session.session_date)} · ${formatTime24(session.starts_at)} · ${session.coach_name ?? OPEN_BOX}`;

export const checkInHref = (id: string): string => `/clases/${encodeURIComponent(id)}/checkin`;

export function SessionDetail({ session, onCancel }: SessionDetailProps) {
  const titleId = useId();
  const cancelled = session.status === "cancelled";
  return (
    <section className={styles.detail} aria-labelledby={titleId}>
      <h2 id={titleId} className={styles.title}>
        {detailTitle(session)}
      </h2>
      <p className={styles.note}>{`Cupo ${String(session.capacity)} · ${String(session.attendance_count)} con check-in`}</p>
      {session.name ? <p className={styles.note}>{session.name}</p> : null}
      {cancelled ? <p className={styles.cancelled}>{session.cancel_reason ? `Cancelada: ${session.cancel_reason}` : "Cancelada"}</p> : null}
      <div className={styles.actions}>
        {cancelled ? null : (
          <Link className={cx(buttonStyles.button, buttonStyles.primary, buttonStyles.md)} to={checkInHref(session.id)}>
            Abrir check-in
          </Link>
        )}
        {session.status === "scheduled" ? (
          <Button
            variant="secondary"
            onClick={() => {
              onCancel(session);
            }}
          >
            Cancelar sesión
          </Button>
        ) : null}
      </div>
    </section>
  );
}
