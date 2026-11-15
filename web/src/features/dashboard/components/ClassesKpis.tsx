// S7-F6 · US-164 (front): las tarjetas de clases de Inicio (Inicio.html). Salen de GET /dashboard
// (`sessions_today` y `attendance_week`, S7-R3) y comparten la consulta ["dashboard"] con el resto de Inicio.
// - «Hoy en el box»: cada sesión de hoy con hora de Bogotá, coach y ocupación; las programadas llevan a su
//   check-in (/clases/:id/checkin). Una clase llena sigue permitiendo el check-in (over_capacity, no bloquea).
// - «Asistencia de la semana»: el conteo y, si hay, cuántas llevan alguna bandera; lleva a /clases/asistencia.
// DESIGN-GAP: gráfico de barras por día, «Promedio por clase» y «Socios distintos esta semana» de «Asistencia de la semana»: GET /dashboard
// solo manda `count` y `flagged_count`, así que es una tarjeta con el conteo (el detalle está en /clases/asistencia).
// DESIGN-GAP: Inicio.html dibuja el WOD de hoy dentro de «Hoy en el box»; llega en v0.5 y vive en FutureKpis.
// S8-D25: el api manda las canceladas al final; «Hoy en el box» lista las vivas y pliega las canceladas en «N canceladas».
// DESIGN-GAP: «Hoy en el box» no muestra saldo ni banderas por sesión (el tablero no las trae).
import { formatCount, formatTime24 } from "../../../core/i18n/format";
import { checkInPath } from "../../../shared/lib/routes";
import { useState } from "react";
import { Link } from "react-router";
import buttonStyles from "../../../shared/ui/Button.module.css";
import { cx } from "../../../shared/ui/cx";
import { KpiCard } from "../../../shared/ui/KpiCard";
import { useDashboard } from "../api";
import type { SessionTodayView } from "../schemas";
import styles from "./ClassesKpis.module.css";

export const SESSIONS_TODAY_PATH = "/clases?dia=hoy";
export const ATTENDANCE_PATH = "/clases/asistencia";
const BOX_LABEL = "Hoy en el box";

function SessionRow({ session }: { session: SessionTodayView }) {
  const time = formatTime24(session.starts_at);
  const isFull = session.attendance_count >= session.capacity;
  return (
    <li className={styles.row}>
      <span className={styles.time}>{time}</span>
      <span className={styles.coach}>{session.coach_name ?? "Open box"}</span>
      <span className={styles.occupancy}>{`${formatCount(session.attendance_count)} / ${formatCount(session.capacity)}`}</span>
      {isFull && session.status === "scheduled" ? <span className={styles.full}>Llena</span> : null}
      {session.status === "scheduled" ? (
        <Link
          to={checkInPath(session.id)}
          aria-label={`Check-in de las ${time}`}
          className={cx(buttonStyles.button, buttonStyles.secondary, buttonStyles.md)}
        >
          Check-in
        </Link>
      ) : (
        <span className={styles.state}>{session.status === "cancelled" ? "Cancelada" : "Terminó"}</span>
      )}
    </li>
  );
}

function cancelledLabel(count: number): string {
  return count === 1 ? "1 cancelada" : `${formatCount(count)} canceladas`;
}

function CancelledFold({ sessions }: { sessions: readonly SessionTodayView[] }) {
  const [open, setOpen] = useState(false);
  if (sessions.length === 0) return null;
  return (
    <div className={styles.cancelled}>
      <button type="button" className={styles.more} aria-expanded={open} aria-controls="inicio-canceladas" onClick={() => {
          setOpen((v) => !v);
        }}>
        {cancelledLabel(sessions.length)}
      </button>
      {open ? (
        <ul id="inicio-canceladas" aria-label="Clases canceladas de hoy" className={styles.list}>
          {sessions.map((session) => (
            <SessionRow key={session.id} session={session} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function BoxCard() {
  const { data, isPending } = useDashboard();

  if (isPending) {
    return (
      <div role="group" aria-label={BOX_LABEL} aria-busy="true" className={styles.card}>
        <span className={styles.label}>{BOX_LABEL}</span>
        <span className={styles.skeleton} aria-hidden="true" />
        <span className={styles.srOnly}>Cargando</span>
      </div>
    );
  }
  if (!data) {
    return (
      <div role="group" aria-label={BOX_LABEL} className={styles.card}>
        <span className={styles.label}>{BOX_LABEL}</span>
        <span className={styles.errorText}>No se pudo cargar</span>
      </div>
    );
  }
  const live = data.sessions_today.filter((s) => s.status !== "cancelled");
  const cancelled = data.sessions_today.filter((s) => s.status === "cancelled");
  return (
    <div role="group" aria-label={BOX_LABEL} className={styles.card}>
      <div className={styles.head}>
        <span className={styles.label}>{BOX_LABEL}</span>
        <Link to={SESSIONS_TODAY_PATH} className={styles.more}>
          Ver sesiones
        </Link>
      </div>
      {live.length === 0 ? (
        <p className={styles.empty}>Hoy no hay clases programadas</p>
      ) : (
        <ul aria-label="Clases de hoy" className={styles.list}>
          {live.map((session) => (
            <SessionRow key={session.id} session={session} />
          ))}
        </ul>
      )}
      <CancelledFold sessions={cancelled} />
    </div>
  );
}

export function ClassesKpis() {
  const { data, isPending, isError } = useDashboard();
  const week = data?.attendance_week;
  const flagged = week?.flagged_count ?? 0;

  return (
    <section aria-labelledby="inicio-clases" className={styles.section}>
      <h2 id="inicio-clases" className={styles.title}>
        Clases
      </h2>
      <div className={styles.grid}>
        <BoxCard />
        <KpiCard
          label="Asistencia de la semana"
          kind="count"
          value={week?.count}
          {...(week ? { href: ATTENDANCE_PATH } : {})}
          {...(flagged > 0 ? { note: `${formatCount(flagged)} con alguna bandera` } : {})}
          isLoading={isPending}
          error={!data && isError}
        />
      </div>
    </section>
  );
}
