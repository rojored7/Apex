// S3-F5 · US-092 (front): el resumen de /membresias (GET /memberships/summary, useMembershipSummary de
// shared/data, S3-D53). Cinco tarjetas KpiCard: socios al día, por vencer, vencidos, congelados y
// pendientes de pago. Cada una carga, falla con Reintentar o muestra la cifra por separado de la lista.
// "Pendientes de pago" pide atención cuando hay alguno (hay que cobrarles).
// DESIGN-GAP: Membresias.html pone los conteos en los chips ("Activas 210"). El resumen cuenta socios
// por la membresía que decide su estado (N-26, US-092), no filas de la lista: un socio con una vigente
// y una renovación pendiente suma una vez, y la lista muestra las dos. Para no mostrar en un chip un
// número distinto del total que da al pulsarlo, los conteos van en tarjetas con su propio título.
import { useMembershipSummary, type MembershipSummaryView } from "../../../shared/data/memberships";
import { KpiCard } from "../../../shared/ui/KpiCard";
import styles from "./MembershipsSummary.module.css";

export const SUMMARY_TITLE = "Socios por estado de su membresía";

const CARDS: readonly { key: keyof MembershipSummaryView; label: string }[] = [
  { key: "active", label: "Al día" },
  { key: "expiring", label: "Por vencer" },
  { key: "expired", label: "Vencidos" },
  { key: "frozen", label: "Congelados" },
  { key: "pending_payment", label: "Pendientes de pago" },
];

export function MembershipsSummary() {
  const summary = useMembershipSummary();
  const { data } = summary;
  return (
    <section aria-label={SUMMARY_TITLE} className={styles.summary}>
      {CARDS.map(({ key, label }) => (
        <KpiCard
          key={key}
          label={label}
          kind="count"
          value={data?.[key]}
          isLoading={summary.isLoading}
          error={summary.isError}
          attention={key === "pending_payment" && (data?.pending_payment ?? 0) > 0}
          onRetry={() => {
            void summary.refetch();
          }}
        />
      ))}
    </section>
  );
}
