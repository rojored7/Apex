// S4A-F3 · US-109 (front): los cuatro KPI de v0.1 de Inicio (Inicio.html) con KpiCard del kit sin
// cambios (S4A-D33), más la línea de pendientes de pago.
// - Socios al día, Por vencer y Vencidos enlazan a /socios con el chip del estado; ingresos del mes, a
//   /pagos con el mes de Bogotá (links.ts).
// - Ingresos en null (el coach, S4A-D118) dicen "Solo administración", sin enlace: ni "$ 0" ni
//   "Disponible en v0.x", porque el dato existe y el rol no lo ve.
// - Carga: las cuatro tarjetas en esqueleto. Error: un aviso con el qué pasó y qué hacer (429 con la
//   espera) y un solo "Reintentar" que vuelve a pedir GET /dashboard.
// DESIGN-GAP: "Vencen en 7 días" del diseño se llama "Por vencer" (los días salen de Configuración,
// `expiring_days`, y el chip de /socios usa ese nombre); sus notas "3 vencen hoy", "12 hace más de 15
// días" y "vs sept" no tienen dato en GET /dashboard (v0.1).
// DESIGN-GAP: la línea de pendientes de pago no está en Inicio.html; `members_pending_payment` se muestra
// y enlaza al chip "Pendiente de pago" (Q3, S4A-D29).
import { Link } from "react-router";
import { formatCount, formatMonth } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { KpiCard } from "../../../shared/ui/KpiCard";
import { useDashboard } from "../api";
import { dashboardErrorMessage } from "../dashboardErrors";
import { kpiLinks } from "../links";
import type { DashboardView } from "../schemas";
import styles from "./KpiGrid.module.css";

const LABELS = { active: "Socios al día", expiring: "Por vencer", expired: "Vencidos", income: "Ingresos del mes" } as const;
export const FINANCE_HIDDEN = "Solo administración";

function incomeLabel(month: string | undefined): string {
  return month ? `Ingresos de ${formatMonth(month)}` : LABELS.income;
}

function pendingText(count: number): string {
  if (count === 0) return "Ningún socio con pago pendiente";
  return count === 1 ? "1 socio con pago pendiente" : `${formatCount(count)} socios con pago pendiente`;
}

function RestrictedKpi({ label }: { label: string }) {
  return (
    <div role="group" aria-label={label} className={styles.restricted}>
      <span className={styles.restrictedLabel}>{label}</span>
      <span className={styles.restrictedValue}>{FINANCE_HIDDEN}</span>
    </div>
  );
}

function Cards({ data }: { data: DashboardView }) {
  const links = kpiLinks(data.today);
  const withMembership = data.members_active + data.members_expiring + data.members_expired + data.members_frozen + data.members_pending_payment;
  const income = incomeLabel(data.income_month);
  return (
    <>
      <div className={styles.grid}>
        <KpiCard label={LABELS.active} value={data.members_active} kind="count" note={`de ${formatCount(withMembership)} con membresía`} href={links.active} />
        <KpiCard label={LABELS.expiring} value={data.members_expiring} kind="count" note="Renovar antes de que venzan" href={links.expiring} attention />
        <KpiCard label={LABELS.expired} value={data.members_expired} kind="count" href={links.expired} />
        {data.income_month_cop === null ? <RestrictedKpi label={income} /> : <KpiCard label={income} value={data.income_month_cop} kind="money" href={links.income} />}
      </div>
      <p className={styles.pending}>
        {data.members_pending_payment > 0 ? (
          <Link to={links.pendingPayment} className={styles.pendingLink}>
            {pendingText(data.members_pending_payment)}
          </Link>
        ) : (
          pendingText(0)
        )}
      </p>
    </>
  );
}

export function KpiGrid() {
  const dashboard = useDashboard();
  const { data, isPending, isError, error, refetch, isFetching } = dashboard;

  let body;
  if (data) {
    body = <Cards data={data} />;
  } else if (isError) {
    body = (
      <div role="alert" className={styles.error}>
        <p className={styles.errorText}>{dashboardErrorMessage(error)}</p>
        <Button
          variant="secondary"
          loading={isFetching}
          onClick={() => {
            void refetch();
          }}
        >
          Reintentar
        </Button>
      </div>
    );
  } else {
    body = (
      <div className={styles.grid}>
        {[LABELS.active, LABELS.expiring, LABELS.expired, LABELS.income].map((label) => (
          <KpiCard key={label} label={label} value={null} kind="count" isLoading />
        ))}
      </div>
    );
  }

  return (
    <section aria-label="Membresías e ingresos" aria-busy={isPending ? true : undefined} className={styles.section}>
      {body}
    </section>
  );
}
