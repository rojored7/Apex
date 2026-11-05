// S5-F3 · US-132 (front): las tarjetas de avisos de Inicio (Inicio.html, "Por avisar hoy"). Salen de
// GET /dashboard (`notifications_today` y `members_without_consent`, S5-B10): ya no son "Disponible en
// v0.2". Comparten la consulta ["dashboard"] con el resto de Inicio (una sola petición).
// - "Por avisar hoy": el conteo con enlace a /avisos/hoy; en 0 dice "Nadie por avisar".
// - "Sin consentimiento": socios que no autorizaron el uso de sus datos; a ellos no se les avisa.
// DESIGN-GAP: Inicio.html dibuja "Por avisar hoy" como una caja con el desglose (vencen hoy, en 3 días,
// vencidos, retención, pendientes de WhatsApp) y "Abrir lista"; GET /dashboard solo manda el total, así
// que es una tarjeta con el conteo que lleva a la lista (/avisos/hoy), que sí tiene el desglose.
import { KpiCard } from "../../../shared/ui/KpiCard";
import { useDashboard } from "../api";
import styles from "./FutureKpis.module.css";

export const NOTIFICATIONS_PATH = "/avisos/hoy";

function todayNote(count: number | null | undefined): string | undefined {
  if (count === 0) return "Nadie por avisar";
  if (count === null || count === undefined) return undefined;
  return "Abre la lista para avisar por WhatsApp u omitir.";
}

function consentNote(count: number | null | undefined): string | undefined {
  if (count === 0) return "Todos los socios autorizaron el uso de sus datos.";
  if (count === null || count === undefined) return undefined;
  return "Socios que no autorizaron el uso de sus datos: no se les avisa.";
}

export function NotificationKpis() {
  const { data, isPending, isError } = useDashboard();
  const failed = !data && isError;
  const today = data?.notifications_today;
  const consent = data?.members_without_consent;
  const todayText = todayNote(today);
  const consentText = consentNote(consent);

  return (
    <section aria-labelledby="inicio-avisos" className={styles.section}>
      <h2 id="inicio-avisos" className={styles.title}>
        Avisos
      </h2>
      <div className={styles.grid}>
        <KpiCard
          label="Por avisar hoy"
          kind="count"
          value={today}
          {...(failed || isPending ? {} : { href: NOTIFICATIONS_PATH })}
          {...(todayText ? { note: todayText } : {})}
          attention={typeof today === "number" && today > 0}
          isLoading={isPending}
          error={failed}
        />
        <KpiCard label="Sin consentimiento" kind="count" value={consent} {...(consentText ? { note: consentText } : {})} isLoading={isPending} error={failed} />
      </div>
    </section>
  );
}
