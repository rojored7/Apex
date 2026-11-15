// S7-F5 · US-162 (front): resumen semanal de la asistencia (GET /attendance/summary).
// - Una sección por semana ISO (lunes a domingo, Bogotá), la más reciente primero: «49 asistencias · 2 con marca» y la tabla de
//   franjas con sesiones, asistencias («45 de 60» del cupo), ocupación en texto («75 %») y las que llegaron con marca.
// - La barra de ocupación solo refuerza el texto (aria-hidden). Cupo 0 dice «Sin cupo»: no se inventa un porcentaje.
// - Las sesiones extra llegan juntas como «Extra». Una semana sin asistencias lo dice y no pinta tabla.
// DESIGN-GAP: Sesiones.html solo nombra la pestaña «Asistencia por socio»; el resumen no tiene pantalla de diseño (S7-D15).
import type { WeekBucketView } from "../attendanceApi";
import { weekLabel } from "../weeks";
import styles from "./WeeklySummary.module.css";

export interface WeeklySummaryProps {
  weeks: readonly WeekBucketView[];
}

const plural = (count: number, one: string, many: string): string => `${String(count)} ${count === 1 ? one : many}`;
const lower = (text: string): string => text.charAt(0).toLowerCase() + text.slice(1);
const clampPct = (pct: number): number => Math.min(100, Math.max(0, pct));

function WeekSection({ week }: { week: WeekBucketView }) {
  const label = weekLabel(week.week);
  return (
    <section aria-label={label} className={styles.week}>
      <h3 className={styles.title}>{label}</h3>
      {week.total === 0 ? (
        <p className={styles.note}>Sin asistencias esta semana.</p>
      ) : (
        <>
          <p className={styles.total}>{`${plural(week.total, "asistencia", "asistencias")} · ${String(week.flagged)} con marca`}</p>
          {week.slots.length > 0 ? (
            <div className={styles.scroll}>
              <table className={styles.table} aria-label={`Franjas de la ${lower(label)}`}>
                <thead>
                  <tr>
                    <th scope="col">Franja</th>
                    <th scope="col">Sesiones</th>
                    <th scope="col">Asistencias</th>
                    <th scope="col">Ocupación</th>
                    <th scope="col">Con marca</th>
                  </tr>
                </thead>
                <tbody>
                  {week.slots.map((slot) => (
                    <tr key={slot.slot_id ?? slot.label}>
                      <th scope="row">{slot.start_time ? `${slot.label} · ${slot.start_time}` : slot.label}</th>
                      <td>{slot.sessions}</td>
                      <td>{`${String(slot.attendance)} de ${String(slot.capacity_sum)}`}</td>
                      <td>
                        {slot.capacity_sum === 0 ? (
                          "Sin cupo"
                        ) : (
                          <span className={styles.occupancy}>
                            <span aria-hidden="true" className={styles.bar}>
                              <span className={styles.fill} style={{ inlineSize: `${String(clampPct(slot.occupancy_pct))}%` }} />
                            </span>
                            {`${String(slot.occupancy_pct)} %`}
                          </span>
                        )}
                      </td>
                      <td>{slot.flagged}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

export function WeeklySummary({ weeks }: WeeklySummaryProps) {
  const ordered = [...weeks].sort((a, b) => b.week_start.localeCompare(a.week_start));
  return (
    <div className={styles.weeks}>
      {ordered.map((week) => (
        <WeekSection key={week.week} week={week} />
      ))}
    </div>
  );
}
