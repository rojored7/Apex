// S8-F2 · US-166 (front): calendario de la semana de WOD_Lista.html. Un día por celda, lunes a domingo (Bogotá).
// - El día con WOD enlaza a su detalle y muestra título, tipo de marca, movimientos y resultados; el día vacío ofrece «+ Crear».
// - Hoy lleva aria-current="date" y borde azul (no solo color: también el texto «Hoy»).
// DESIGN-GAP (S8-D7): «2 sesiones faltan» y el estado de publicación no existen en el contrato.
import { Link } from "react-router";
import { formatCount } from "../../../core/i18n/format";
import { dayHeader } from "../../../shared/data/weeks";
import { cx } from "../../../shared/ui/cx";
import type { WodRowView } from "../wodSchemas";
import { WOD_SCORE_LABELS } from "../wodSchemas";
import styles from "./WeekCalendar.module.css";

export interface WeekCalendarProps {
  /** Las siete fechas civiles de lunes a domingo. */
  dates: readonly string[];
  wods: readonly WodRowView[];
  today: string;
}

export const resultsText = (count: number): string => (count === 1 ? "1 resultado" : `${formatCount(count)} resultados`);

export function WeekCalendar({ dates, wods, today }: WeekCalendarProps) {
  return (
    <ol className={styles.week} aria-label="Semana">
      {dates.map((date) => {
        const wod = wods.find((row) => row.date === date);
        const isToday = date === today;
        return (
          <li key={date} aria-label={dayHeader(date)} aria-current={isToday ? "date" : undefined} className={cx(styles.day, isToday && styles.today)}>
            <p className={styles.dayName} aria-hidden="true">
              {dayHeader(date)}
              {isToday ? <span className={styles.todayTag}>Hoy</span> : null}
            </p>
            {wod ? (
              <Link to={`/wods/${encodeURIComponent(wod.id)}`} className={styles.card} aria-label={`${wod.title}, ${dayHeader(date)}`}>
                <span className={styles.title}>{wod.title}</span>
                <span className={styles.meta}>
                  {wod.is_benchmark ? <span className={styles.badge}>Benchmark</span> : null}
                  <span>{WOD_SCORE_LABELS[wod.score_type]}</span>
                </span>
                <span className={styles.movements}>{wod.movement_names.join(" · ")}</span>
                {wod.result_count > 0 ? <span className={styles.results}>{resultsText(wod.result_count)}</span> : null}
              </Link>
            ) : (
              <Link to={`/wods/nuevo?date=${date}`} className={styles.create}>
                + Crear
              </Link>
            )}
          </li>
        );
      })}
    </ol>
  );
}
