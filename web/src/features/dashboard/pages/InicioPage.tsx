// S4A-F3 · US-108 a US-110 (front; reemplaza la Inicio mínima de S2-D25): Inicio.html con GET
// /dashboard. Saludo con el día de Bogotá, accesos del encabezado según el rol, los KPI de v0.1
// (KpiGrid), las tarjetas futuras (FutureKpis) y los últimos movimientos (LastMovements). Las tres
// piezas comparten la consulta ["dashboard"]: una sola petición. El member nunca llega aquí: RequireRole
// lo manda a /mi antes de pintar el panel.
// DESIGN-GAP: "Hola, Ana": el saludo usa la parte local del correo; `display_name` llega en v0.2 con
// EP-04 (S4A-D19).
// DESIGN-GAP: "Registrar pago" y "Check-in" del encabezado: el registro de pagos se abre desde /pagos
// (sin enlace directo al panel) y Check-in llega con clases en v0.4.
import { useSession } from "../../../core/auth";
import { can } from "../../../core/auth/permissions";
import { formatLongDate, todayBogota } from "../../../core/i18n/format";
import { NEW_MEMBER_PATH, SELL_PATH } from "../../../shared/lib/routes";
import { PageHeader, type PageAction } from "../../../shared/ui/PageHeader";
import { useDashboard } from "../api";
import { FutureKpis } from "../components/FutureKpis";
import { KpiGrid } from "../components/KpiGrid";
import { LastMovements } from "../components/LastMovements";
import styles from "./InicioPage.module.css";

/** "ana" de "ana@apex.test"; el correo entero si no tiene arroba. */
function localPart(email: string): string {
  const at = email.indexOf("@");
  return at > 0 ? email.slice(0, at) : email;
}

export default function InicioPage() {
  const { user } = useSession();
  const { data } = useDashboard();
  const day = formatLongDate(data?.today ?? todayBogota());
  const title = user ? `Hola, ${localPart(user.email)} · ${day}` : "Inicio";
  const role = user?.role ?? null;
  const actions: PageAction[] = [
    ...(can(role, "members.create") ? [{ id: "nuevo-socio", label: "+ Nuevo socio", href: NEW_MEMBER_PATH, variant: "primary" as const }] : []),
    ...(can(role, "memberships.sell") ? [{ id: "vender", label: "Vender membresía", href: SELL_PATH }] : []),
  ];

  return (
    <div className={styles.page}>
      <PageHeader title={title} actions={actions} />
      <KpiGrid />
      <FutureKpis />
      <LastMovements />
    </div>
  );
}
