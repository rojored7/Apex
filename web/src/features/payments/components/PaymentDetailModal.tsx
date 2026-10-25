// S3-F6 · US-099 (front): detalle de un pago (Pagos.html, "Detalle del pago"; GET /payments/{id}).
// - Socio (enlace a la ficha), membresía, valor, medio y referencia, fecha y hora de Bogotá, quién
//   registró (el correo parcial tal cual, S3-D57), el estado y, si es retroactivo (S3-D51), cuándo se
//   registró.
// - Anulado: bloque "Anulación" con el motivo, quién anuló (correo parcial) y cuándo.
// - Sin editar ni borrar (DESIGN.md regla 4): un pago nunca cambia; se anula y se registra otro.
// - "Anular pago" solo con `payments.void` (admin; el api vuelve a verificar) y solo si no está
//   anulado: el detalle se cambia por VoidPaymentModal (punto de montaje; dos diálogos a la vez se
//   pelearían el foco). Al cerrarlo vuelve el detalle, ya releído (anular invalida ["payments"]).
// - Estados: carga, 404 y otro error con Reintentar; Cerrar siempre disponible.
// DESIGN-GAP: sin el número del pago en el título ("#4812": los pagos tienen UUID, no consecutivo) y
// sin "Recibo · Reenviar · Imprimir" (el recibo es de la v0.2). "Registró" muestra el correo parcial y
// no "Carlos R. (coach)" hasta US-110.
import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { EMPTY_VALUE, formatCop, formatDateTime } from "../../../core/i18n/format";
import { usePaymentMethodOptions } from "../../../shared/data/paymentMethods";
import { Button } from "../../../shared/ui/Button";
import { Modal } from "../../../shared/ui/Modal";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { usePayment } from "../api";
import { memberHref, memberName, membershipText } from "../lib/paymentText";
import { paymentDetailMessage } from "../paymentErrors";
import type { PaymentDetailView } from "../schemas";
import styles from "./PaymentDetailModal.module.css";
import { VoidPaymentModal } from "./VoidPaymentModal";

export const DETAIL_TITLE = "Detalle del pago";
export const NEVER_EDITED = "Un pago nunca se edita: si tiene un error, se anula y se registra otro.";

export interface PaymentDetailModalProps {
  /** El pago a mostrar; null cierra el detalle. */
  paymentId: string | null;
  onClose: () => void;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.row}>
      <dt className={styles.term}>{label}</dt>
      <dd className={styles.value}>{children}</dd>
    </div>
  );
}

function DetailBody({ payment }: { payment: PaymentDetailView }) {
  const { methods } = usePaymentMethodOptions();
  const methodLabel = methods.find((method) => method.code === payment.method)?.label ?? payment.method;
  return (
    <>
      <dl className={styles.list}>
        <Row label="Socio">
          <Link to={memberHref(payment.member_id)}>{memberName(payment)}</Link>
        </Row>
        <Row label="Membresía">{membershipText(payment)}</Row>
        <Row label="Valor">
          <span className={styles.amount}>{formatCop(payment.amount_cop)}</span>
        </Row>
        <Row label="Medio · referencia">{`${methodLabel} · ${payment.reference ?? "sin referencia"}`}</Row>
        <Row label="Fecha del pago">{formatDateTime(payment.paid_at)}</Row>
        <Row label="Registró">{payment.registered_by_name ?? EMPTY_VALUE}</Row>
        {payment.backdated ? <Row label="Registrado el">{formatDateTime(payment.created_at)}</Row> : null}
        <Row label="Estado">
          <span className={styles.status}>
            <StatusTag payment={payment.voided ? "voided" : "valid"} />
            {payment.backdated ? <span className={styles.mark}>Retroactivo</span> : null}
          </span>
        </Row>
      </dl>
      {payment.voided ? (
        <section aria-labelledby={`void-${payment.id}`} className={styles.voidBlock}>
          <h3 id={`void-${payment.id}`} className={styles.voidTitle}>
            Anulación
          </h3>
          <dl className={styles.list}>
            <Row label="Motivo">{payment.void_reason ?? EMPTY_VALUE}</Row>
            <Row label="Anuló">{payment.voided_by_name ?? EMPTY_VALUE}</Row>
            <Row label="Fecha de anulación">{payment.voided_at ? formatDateTime(payment.voided_at) : EMPTY_VALUE}</Row>
          </dl>
        </section>
      ) : null}
      <p className={styles.note}>{NEVER_EDITED}</p>
    </>
  );
}

export function PaymentDetailModal({ paymentId, onClose }: PaymentDetailModalProps) {
  const canVoid = useCan("payments.void");
  const detail = usePayment(paymentId);
  const [voiding, setVoiding] = useState<string | null>(null);
  const payment = detail.data;

  if (paymentId === null) return null;
  if (voiding === paymentId && payment) {
    return (
      <VoidPaymentModal
        payment={{ id: payment.id, membership_id: payment.membership_id, amount_cop: payment.amount_cop, method: payment.method }}
        onClose={() => {
          setVoiding(null);
        }}
      />
    );
  }

  const canVoidThis = canVoid && payment !== undefined && !payment.voided;
  return (
    <Modal
      open
      title={DETAIL_TITLE}
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cerrar
          </Button>
          {canVoidThis ? (
            <Button
              variant="danger"
              onClick={() => {
                setVoiding(paymentId);
              }}
            >
              Anular pago
            </Button>
          ) : null}
        </>
      }
    >
      {payment ? (
        <DetailBody payment={payment} />
      ) : detail.isError ? (
        <div className={styles.state}>
          <p role="alert" className={styles.error}>
            {paymentDetailMessage(detail.error)}
          </p>
          <Button
            variant="secondary"
            onClick={() => {
              void detail.refetch();
            }}
          >
            Reintentar
          </Button>
        </div>
      ) : (
        <p role="status" className={styles.state} aria-busy="true">
          Cargando el pago…
        </p>
      )}
    </Modal>
  );
}
