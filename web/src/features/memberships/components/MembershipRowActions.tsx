// S3-F5 · US-088 a US-090 y US-095 (front): las acciones de una fila de /membresias (Membresias.html:
// "Renovar · Congelar · Anular", "Registrar saldo · Renovar").
// - Renovar (`memberships.sell`): la venta con el socio fijo y `renovar=1` (US-088), con su nombre en
//   el estado de la navegación; no en una anulada.
// - Registrar saldo (`payments.register`): abre el panel de pagos sobre esta misma pantalla con
//   `?pago=<membresía>` (S3-D65: un enlace de shared/lib/paymentPanel, sin importar features/payments),
//   solo si la membresía recibe pagos (al día, por vencer, congelada o pendiente) y le falta plata.
// - Congelar (`memberships.freeze`): solo al día o por vencer (el api da 409 `membership_not_freezable`
//   en las demás).
// - Anular (`memberships.cancel`, solo admin): toda membresía no anulada.
// Cada acción nombra al socio para el lector de pantalla ("Congelar la membresía de Elena Vargas"); el
// texto visible es el corto del diseño. Sin acciones, "—".
import { Link, useLocation } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { EMPTY_VALUE } from "../../../core/i18n/format";
import { OPEN_MEMBERSHIP_STATUSES, type MembershipRowView, type MembershipStatus } from "../../../shared/data/memberships";
import { paymentPanelHref } from "../../../shared/lib/paymentPanel";
import { cx } from "../../../shared/ui/cx";
import { renewHref } from "../membershipLinks";
import styles from "./MembershipRowActions.module.css";

const FREEZABLE: readonly MembershipStatus[] = ["active", "expiring"];

export interface MembershipRowActionsProps {
  row: MembershipRowView;
  onFreeze: (row: MembershipRowView) => void;
  onCancel: (row: MembershipRowView) => void;
}

export function MembershipRowActions({ row, onFreeze, onCancel }: MembershipRowActionsProps) {
  const location = useLocation();
  const canSell = useCan("memberships.sell");
  const canRegister = useCan("payments.register");
  const canFreeze = useCan("memberships.freeze");
  const canCancel = useCan("memberships.cancel");
  const isCancelled = row.status === "cancelled";
  const owes = row.paid_cop < row.agreed_price_cop;
  const receivesPayments = (OPEN_MEMBERSHIP_STATUSES as readonly MembershipStatus[]).includes(row.status);
  const name = row.member_name;

  const actions = [
    canRegister && receivesPayments && owes ? (
      <Link key="pay" className={styles.action} to={paymentPanelHref(location, { membershipId: row.id })} aria-label={`Registrar saldo de ${name}`}>
        Registrar saldo
      </Link>
    ) : null,
    canSell && !isCancelled ? (
      <Link key="renew" className={styles.action} to={renewHref(row.member_id)} state={{ memberName: name }} aria-label={`Renovar la membresía de ${name}`}>
        Renovar
      </Link>
    ) : null,
    canFreeze && FREEZABLE.includes(row.status) ? (
      <button
        key="freeze"
        type="button"
        className={styles.action}
        aria-label={`Congelar la membresía de ${name}`}
        onClick={() => {
          onFreeze(row);
        }}
      >
        Congelar
      </button>
    ) : null,
    canCancel && !isCancelled ? (
      <button
        key="cancel"
        type="button"
        className={cx(styles.action, styles.danger)}
        aria-label={`Anular la membresía de ${name}`}
        onClick={() => {
          onCancel(row);
        }}
      >
        Anular
      </button>
    ) : null,
  ].filter((action) => action !== null);

  if (actions.length === 0) return <span className={styles.none}>{EMPTY_VALUE}</span>;
  return <div className={styles.actions}>{actions}</div>;
}
