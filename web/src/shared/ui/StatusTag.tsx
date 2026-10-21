import { statusLabel, statusTone, type MembershipStatusView } from "./statusLabel";
import styles from "./StatusTag.module.css";
import { cx } from "./cx";

export interface StatusTagProps {
  status: MembershipStatusView;
  className?: string;
}

/** Píldora de estado de membresía: el texto siempre visible lleva el significado, el color lo refuerza. */
export function StatusTag({ status, className }: StatusTagProps) {
  return (
    <span className={cx(styles.tag, styles[statusTone(status)], className)} data-status={status}>
      {statusLabel(status)}
    </span>
  );
}
