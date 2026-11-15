import {
  accountLabel,
  accountTone,
  cryptoLabel,
  cryptoTone,
  paymentLabel,
  paymentTone,
  signatureLabel,
  slotLabel,
  slotTone,
  flagLabel,
  flagTone,
  type FlagView,
  signatureTone,
  statusLabel,
  statusTone,
  type AccountStatusView,
  type CryptoStatusView,
  type MembershipStatusView,
  type PaymentStatusView,
  type SignatureStateView,
  type SlotStateView,
} from "./statusLabel";
import styles from "./StatusTag.module.css";
import { cx } from "./cx";

/**
 * S2-D24: un estado de membresía (`status`), de cuenta de usuario (`account`) o, desde S3-F6, de un
 * pago (`payment`); nunca más de uno.
 */
export type StatusTagProps =
  | { status: MembershipStatusView; account?: never; payment?: never; signature?: never; crypto?: never; className?: string | undefined; slot?: never; flag?: never }
  | { account: AccountStatusView; status?: never; payment?: never; signature?: never; crypto?: never; className?: string | undefined; slot?: never; flag?: never }
  | { payment: PaymentStatusView; status?: never; account?: never; signature?: never; crypto?: never; className?: string | undefined; slot?: never; flag?: never }
  | { signature: SignatureStateView; status?: never; account?: never; payment?: never; crypto?: never; className?: string | undefined; slot?: never; flag?: never }
  | { crypto: CryptoStatusView; status?: never; account?: never; payment?: never; signature?: never; className?: string | undefined; slot?: never; flag?: never }
  | { slot: SlotStateView; status?: never; account?: never; payment?: never; signature?: never; crypto?: never; className?: string | undefined; flag?: never }
  | { flag: FlagView; status?: never; account?: never; payment?: never; signature?: never; crypto?: never; className?: string | undefined; slot?: never };

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
  if (props.crypto !== undefined) {
    const { crypto, className } = props;
    return (
      <span className={cx(styles.tag, styles[cryptoTone(crypto)], className)} data-crypto={crypto}>
        {cryptoLabel(crypto)}
      </span>
    );
  }
  if (props.flag !== undefined) {
    const { flag, className } = props;
    return (
      <span className={cx(styles.tag, styles[flagTone(flag)], className)} data-flag={flag}>
        {flagLabel(flag)}
      </span>
    );
  }
  if (props.slot !== undefined) {
    const { slot, className } = props;
    return (
      <span className={cx(styles.tag, styles[slotTone(slot)], className)} data-slot={slot}>
        {slotLabel(slot)}
      </span>
    );
  }
  if (props.signature !== undefined) {
    const { signature, className } = props;
    return (
      <span className={cx(styles.tag, styles[signatureTone(signature)], className)} data-signature={signature}>
        {signatureLabel(signature)}
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
