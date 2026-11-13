// S5-F3 · US-132 (front): las tarjetas de avisos de Inicio (Inicio.html, "Por avisar hoy"). Salen de
// GET /dashboard (`notifications_today` y `members_without_consent`, S5-B10): ya no son "Disponible en
// v0.2". Comparten la consulta ["dashboard"] con el resto de Inicio (una sola petición).
// - "Por avisar hoy": el conteo con enlace a /avisos/hoy; en 0 dice "Nadie por avisar".
// - S6-F5 (US-151) "Sin autorización" (antes "Sin consentimiento"): socios sin la autorización de datos; a ellos no
//   se les avisa. Lleva a /socios?consent=missing (la lista filtrada, misma condición que el conteo); en 0 dice
//   "Todos con autorización". Un null no es enlace ni cero.
// DESIGN-GAP: Inicio.html dibuja "Por avisar hoy" como una caja con el desglose (vencen hoy, en 3 días,
// vencidos, retención, pendientes de WhatsApp) y "Abrir lista"; GET /dashboard solo manda el total, así
// que es una tarjeta con el conteo que lleva a la lista (/avisos/hoy), que sí tiene el desglose.
import { MEMBERS_PATH } from "../../../shared/lib/routes";
import { KpiCard } from "../../../shared/ui/KpiCard";
import { useDashboard } from "../api";
import styles from "./FutureKpis.module.css";

export const NOTIFICATIONS_PATH = "/avisos/hoy";
export const CONSENT_MISSING_PATH = `${MEMBERS_PATH}?consent=missing`;

function todayNote(count: number | null | undefined): string | undefined {
  if (count === 0) return "Nadie por avisar";
  if (count === null || count === undefined) return undefined;
  return "Abre la lista para avisar por WhatsApp u omitir.";
}

function consentNote(count: number | null | undefined): string | undefined {
  if (count === 0) return "Todos con autorización";
  if (count === null || count === undefined) return undefined;
  return "Socios sin la autorización de datos: no se les avisa. Abre la lista para pedírsela.";
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
        <KpiCard
          label="Sin autorización"
          kind="count"
          value={consent}
          {...(typeof consent === "number" ? { href: CONSENT_MISSING_PATH } : {})}
          {...(consentText ? { note: consentText } : {})}
          attention={typeof consent === "number" && consent > 0}
          isLoading={isPending}
          error={failed}
        />
      </div>
    </section>
  );
}
