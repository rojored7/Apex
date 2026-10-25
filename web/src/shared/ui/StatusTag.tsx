import {
  accountLabel,
  accountTone,
  paymentLabel,
  paymentTone,
  statusLabel,
  statusTone,
  type AccountStatusView,
  type MembershipStatusView,
  type PaymentStatusView,
} from "./statusLabel";
import styles from "./StatusTag.module.css";
import { cx } from "./cx";

/**
 * S2-D24: un estado de membresía (`status`), de cuenta de usuario (`account`) o, desde S3-F6, de un
 * pago (`payment`); nunca más de uno.
 */
export type StatusTagProps =
  | { status: MembershipStatusView; account?: never; payment?: never; className?: string | undefined }
  | { account: AccountStatusView; status?: never; payment?: never; className?: string | undefined }
  | { payment: PaymentStatusView; status?: never; account?: never; className?: string | undefined };

/** Píldora de estado: el texto siempre visible lleva el significado, el color lo refuerza. */
export function StatusTag(props: StatusTagProps) {
  if (props.account !== undefined) {
    const { account, className } = props;
    return (
      <span className={cx(styles.tag, styles[accountTone(account)], className)} data-account={account}>
        {accountLabel(account)}
      </span>
    );
  }
  if (props.payment !== undefined) {
    const { payment, className } = props;
    return (
      <span className={cx(styles.tag, styles[paymentTone(payment)], className)} data-payment={payment}>
        {paymentLabel(payment)}
      </span>
    );
  }
  const { status, className } = props;
  return (
    <span className={cx(styles.tag, styles[statusTone(status)], className)} data-status={status}>
      {statusLabel(status)}
    </span>
  );
}
