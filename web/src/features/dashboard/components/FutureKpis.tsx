// S4A-F3 · US-109 (front): las tarjetas de Inicio cuyo dato llega en una versión futura. GET /dashboard
// las manda en null y KpiCard (del kit, sin cambios) dice "Disponible en v0.x", nunca 0 (EP-12,
// S4A-D33); cuando llegue el dato, la misma tarjeta lo muestra.
// DESIGN-GAP: "Hoy en el box" (clases de hoy con cupos y Check-in) llega con clases en v0.4; aquí solo
// la tarjeta con `sessions_today`.
// DESIGN-GAP: "Asistencia de la semana" (gráfico por día, promedio y socios distintos) llega en v0.4;
// aquí solo `attendance_week`.
// DESIGN-GAP: "WOD de hoy" (nombre, Ver y Registrar resultados) llega en v0.5; aquí solo `wod_today`.
// DESIGN-GAP: "Por avisar hoy" (vencen hoy, en 3 días, vencidos, retención, pendientes de WhatsApp)
// llega con avisos en v0.2 (EP-14); aquí `notifications_today` y `members_without_consent`.
// Si GET /dashboard falla, las tarjetas dicen "No se pudo cargar" sin reintento propio: el aviso y el
// botón "Reintentar" están en KpiGrid (una sola petición para toda la pantalla).
import { KpiCard } from "../../../shared/ui/KpiCard";
import { useDashboard } from "../api";
import type { DashboardView } from "../schemas";
import styles from "./FutureKpis.module.css";

interface FutureCount {
  label: string;
  version: string;
  value: (data: DashboardView) => number | null;
}

const COUNTS: readonly FutureCount[] = [
  { label: "Hoy en el box", version: "v0.4", value: (d) => d.sessions_today },
  { label: "Asistencia de la semana", version: "v0.4", value: (d) => d.attendance_week },
  { label: "Por avisar hoy", version: "v0.2", value: (d) => d.notifications_today },
  { label: "Sin consentimiento", version: "v0.2", value: (d) => d.members_without_consent },
];

const WOD = { label: "WOD de hoy", version: "v0.5" } as const;

function WodCard({ name }: { name: string }) {
  return (
    <div role="group" aria-label={WOD.label} className={styles.text}>
      <span className={styles.textLabel}>{WOD.label}</span>
      <span className={styles.textValue}>{name}</span>
    </div>
  );
}

export function FutureKpis() {
  const { data, isPending, isError } = useDashboard();
  const loading = isPending;
  const failed = !data && isError;

  return (
    <section aria-labelledby="inicio-futuros" className={styles.section}>
      <h2 id="inicio-futuros" className={styles.title}>
        Próximamente en Inicio
      </h2>
      <div className={styles.grid}>
        {COUNTS.slice(0, 2).map((card) => (
          <KpiCard key={card.label} label={card.label} kind="count" value={data ? card.value(data) : null} availableIn={card.version} isLoading={loading} error={failed} />
        ))}
        {data?.wod_today ? (
          <WodCard name={data.wod_today} />
        ) : (
          <KpiCard label={WOD.label} kind="count" value={null} availableIn={WOD.version} isLoading={loading} error={failed} />
        )}
        {COUNTS.slice(2).map((card) => (
          <KpiCard key={card.label} label={card.label} kind="count" value={data ? card.value(data) : null} availableIn={card.version} isLoading={loading} error={failed} />
        ))}
      </div>
    </section>
  );
}
