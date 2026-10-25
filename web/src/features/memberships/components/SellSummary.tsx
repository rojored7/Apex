// S3-F3 · resumen de la venta (Membresia_Vender.html, columna derecha) y la venta registrada.
// - SellSummary: socio, plan, vigencia, precio, pago, saldo y quién registra, con el botón de envío
//   ("Vender y cobrar", o "Vender" sin pago) y Cancelar. Todo dinero y fecha sale de core/i18n.
//   DESIGN-GAP: "Registra" muestra el correo de la sesión (no hay nombre de usuario hasta US-110).
//   DESIGN-GAP: el botón dice "Vender y cobrar" (blueprint) en vez de "Confirmar venta y pago", y
//   Cancelar vuelve a Socios (la lista de membresías llega con S3-F5).
// - SellDone: lo que respondió el api (201): estado con StatusTag ("Al día" o "Pendiente de pago"),
//   pagado y saldo. El título recibe el foco. DESIGN-GAP: el diseño lleva a la ficha del socio
//   (US-073, S3-F1); hasta entonces la venta registrada se queda en la página.
import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router";
import { EMPTY_VALUE, formatCop, formatDate } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { cx } from "../../../shared/ui/cx";
import { saldo } from "../lib/rules";
import { MEMBERS_PATH } from "../membershipLinks";
import type { SellMembershipOutView } from "../schemas";
import styles from "./Sell.module.css";

export interface SummaryRow {
  label: string;
  value: ReactNode;
}

function Rows({ rows }: { rows: readonly SummaryRow[] }) {
  return (
    <dl className={styles.list}>
      {rows.map((row) => (
        <div key={row.label} className={styles.row}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** "28 oct 2026 – 27 nov 2026", o una raya sin fechas. */
export function validityText(start: string | null, end: string | null): string {
  return start && end ? `${formatDate(start)} – ${formatDate(end)}` : EMPTY_VALUE;
}

export interface SellSummaryProps {
  memberName: string | null;
  planName: string | null;
  start: string | null;
  end: string | null;
  price: number | null;
  withPayment: boolean;
  /** El valor escrito, o null si todavía no es un monto. */
  amount: number | null;
  methodLabel: string;
  registeredBy: string | null;
  submitting: boolean;
  submitDisabled: boolean;
}

function paymentText({ withPayment, amount, methodLabel }: Pick<SellSummaryProps, "withPayment" | "amount" | "methodLabel">): string {
  if (!withPayment) return "Sin pago";
  return amount === null ? EMPTY_VALUE : `${formatCop(amount)} · ${methodLabel}`;
}

function balanceText({ price, withPayment, amount }: Pick<SellSummaryProps, "price" | "withPayment" | "amount">): string {
  if (price === null) return EMPTY_VALUE;
  return formatCop(saldo(price, withPayment ? (amount ?? 0) : 0));
}

export function SellSummary(props: SellSummaryProps) {
  const { memberName, planName, start, end, price, registeredBy, withPayment, submitting, submitDisabled } = props;
  const rows: SummaryRow[] = [
    { label: "Socio", value: memberName ?? EMPTY_VALUE },
    { label: "Plan", value: planName ?? EMPTY_VALUE },
    { label: "Vigencia", value: validityText(start, end) },
    { label: "Precio", value: price === null ? EMPTY_VALUE : formatCop(price) },
    { label: "Pago", value: paymentText(props) },
    { label: "Saldo", value: balanceText(props) },
    { label: "Registra", value: registeredBy ?? EMPTY_VALUE },
  ];
  const label = withPayment ? "Vender y cobrar" : "Vender";
  return (
    <aside className={styles.summary} aria-labelledby="sell-summary-title">
      <h2 id="sell-summary-title" className={styles.h2}>
        Resumen
      </h2>
      <Rows rows={rows} />
      <div className={styles.actions}>
        <Button type="submit" className={styles.submit} loading={submitting} disabled={submitDisabled}>
          {submitting ? "Vendiendo…" : label}
        </Button>
        <Link className={styles.secondaryLink} to={MEMBERS_PATH}>
          Cancelar
        </Link>
      </div>
    </aside>
  );
}

export interface SellDoneProps {
  sold: SellMembershipOutView;
  onSellAnother: () => void;
}

export function SellDone({ sold, onSellAnother }: SellDoneProps) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    titleRef.current?.focus();
  }, []);
  const rows: SummaryRow[] = [
    { label: "Plan", value: sold.plan_name },
    { label: "Vigencia", value: validityText(sold.start_date, sold.end_date) },
    { label: "Precio", value: formatCop(sold.agreed_price_cop) },
    { label: "Pagado", value: formatCop(sold.paid_cop) },
    { label: "Saldo", value: formatCop(saldo(sold.agreed_price_cop, sold.paid_cop)) },
    { label: "Estado", value: <StatusTag status={sold.status} /> },
  ];
  return (
    <section className={styles.box} aria-labelledby="sell-done-title">
      <h2 id="sell-done-title" ref={titleRef} tabIndex={-1} className={cx(styles.h2, styles.doneTitle)}>
        Venta registrada
      </h2>
      <p className={styles.note}>La membresía de {sold.member_name} quedó registrada.</p>
      <Rows rows={rows} />
      <div className={styles.doneActions}>
        <Button onClick={onSellAnother}>Vender otra membresía</Button>
        <Link className={styles.secondaryLink} to={MEMBERS_PATH}>
          Ir a Socios
        </Link>
      </div>
    </section>
  );
}
