// S8-F5 · US-174 (front): la tarjeta «WOD de hoy» de Inicio (Inicio.html). Sale de GET /dashboard (`wod_today`, objeto o null; S8-D16) y
// comparte la consulta ["dashboard"] con el resto de Inicio (una sola petición).
// - Con WOD: título, tipo de marca y «Benchmark»; «Ver» lleva al detalle y «Registrar resultados» a la próxima sesión viva de hoy
//   (/clases/:id/resultados; se salta las terminadas y las canceladas). Sin sesión viva o con un WOD sin marca no se ofrece, y se explica.
// - Sin WOD: «Hoy no hay WOD publicado.» y guía a crearlo con la fecha de hoy (/wods/nuevo?date=).
// DESIGN-GAP: Inicio.html dibuja el WOD dentro de «Hoy en el box» con la descripción en una línea; el tablero solo trae título, tipo y
// si es benchmark (S8-D16), así que es una tarjeta propia sin la descripción.
import { Link } from "react-router";
import { todayBogota } from "../../../core/i18n/format";
import { SCORE_TYPE_LABELS } from "../../../shared/data/score";
import { resultsPath } from "../../../shared/lib/routes";
import buttonStyles from "../../../shared/ui/Button.module.css";
import { cx } from "../../../shared/ui/cx";
import { useDashboard } from "../api";
import type { DashboardView, WodTodayView } from "../schemas";
import { nextCheckInSession } from "../sessionsToday";
import styles from "./WodTodayCard.module.css";

const LABEL = "WOD de hoy";

function Card({ children, busy = false }: { children: React.ReactNode; busy?: boolean }) {
  return (
    <section aria-labelledby="inicio-wod" className={styles.section}>
      <h2 id="inicio-wod" className={styles.title}>
        {LABEL}
      </h2>
      <div role="group" aria-label={LABEL} {...(busy ? { "aria-busy": true } : {})} className={styles.card}>
        {children}
      </div>
    </section>
  );
}

function WodBody({ wod, data, nowMs }: { wod: WodTodayView; data: DashboardView; nowMs: number }) {
  const next = wod.score_type === "none" ? null : nextCheckInSession(data.sessions_today, nowMs);
  return (
    <>
      <span className={styles.name}>{wod.title}</span>
      <div className={styles.meta}>
        <span>{SCORE_TYPE_LABELS[wod.score_type]}</span>
        {wod.is_benchmark ? <span>Benchmark</span> : null}
      </div>
      <div className={styles.actions}>
        <Link to={`/wods/${encodeURIComponent(wod.id)}`} className={cx(buttonStyles.button, buttonStyles.secondary, buttonStyles.md)}>
          Ver
        </Link>
        {next ? (
          <Link to={resultsPath(next.id)} className={cx(buttonStyles.button, buttonStyles.primary, buttonStyles.md)}>
            Registrar resultados
          </Link>
        ) : null}
      </div>
      {wod.score_type !== "none" && !next ? <p className={styles.note}>No quedan clases por registrar hoy.</p> : null}
    </>
  );
}

export function WodTodayCard() {
  const { data, dataUpdatedAt, isPending } = useDashboard();

  if (isPending) {
    return (
      <Card busy>
        <span className={styles.skeleton} aria-hidden="true" />
        <span className={styles.srOnly}>Cargando</span>
      </Card>
    );
  }
  if (!data) {
    return (
      <Card>
        <p className={styles.note}>No se pudo cargar</p>
      </Card>
    );
  }
  if (!data.wod_today) {
    return (
      <Card>
        <p className={styles.note}>Hoy no hay WOD publicado.</p>
        <Link to={`/wods/nuevo?date=${encodeURIComponent(todayBogota())}`} className={styles.link}>
          Crear el WOD de hoy
        </Link>
      </Card>
    );
  }
  return (
    <Card>
      <WodBody wod={data.wod_today} data={data} nowMs={dataUpdatedAt} />
    </Card>
  );
}
