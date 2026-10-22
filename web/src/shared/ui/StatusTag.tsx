import { accountLabel, accountTone, statusLabel, statusTone, type AccountStatusView, type MembershipStatusView } from "./statusLabel";
import styles from "./StatusTag.module.css";
import { cx } from "./cx";

/** S2-D24: un estado de membresía (`status`) o de cuenta de usuario (`account`), nunca los dos. */
export type StatusTagProps =
  | { status: MembershipStatusView; account?: never; className?: string | undefined }
  | { account: AccountStatusView; status?: never; className?: string | undefined };

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
  const { status, className } = props;
  return (
    <span className={cx(styles.tag, styles[statusTone(status)], className)} data-status={status}>
      {statusLabel(status)}
    </span>
  );
}
