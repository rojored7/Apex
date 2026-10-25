// S3-F4 · US-097 (front): anular un pago (Pagos.html, "Anular pago"; DESIGN.md regla 3: anular es un
// modal con confirmación y motivo; regla 4: un pago nunca se edita).
// - Solo con `payments.void` (admin): para el coach no pinta nada; el api vuelve a verificar (403).
// - ConfirmModal con motivo obligatorio de 1 a 500 caracteres tras recortar (D17), la consecuencia
//   "El pago no se borra: queda anulado con este motivo" y el aviso M-7 bajo el motivo (S3-D50).
// - Errores dentro del modal en palabras de la pantalla (toVoidError); 409 `payment_already_voided`
//   dice que otra persona lo anuló antes y useVoidPayment relee los pagos.
// - Tras anular, un segundo diálogo ofrece "Registrar pago nuevo": abre el panel de pagos sobre la
//   misma pantalla (`?pago=<membresía>`) con el valor y el medio del anulado precargados.
// Lo usan, dentro de features/payments, el detalle de un pago (S3-F6) y la pestaña Pagos de la ficha
// (S3-F7).
import { useRef, useState } from "react";
import { Link, useLocation } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { formatCop } from "../../../core/i18n/format";
import { SENSITIVE_TEXT_WARNING, type PaymentMethodCode } from "../../../shared/data/schemas/payment";
import { paymentPanelHref, paymentPanelState } from "../../../shared/lib/paymentPanel";
import { Button } from "../../../shared/ui/Button";
import buttonStyles from "../../../shared/ui/Button.module.css";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { Modal } from "../../../shared/ui/Modal";
import { cx } from "../../../shared/ui/cx";
import { useVoidPayment } from "../api";
import { toVoidError, VOID_MESSAGES } from "../paymentErrors";
import { VOID_REASON_MAX, voidPaymentSchema } from "../schemas";

export interface VoidTarget {
  id: string;
  membership_id: string;
  amount_cop: number;
  method: PaymentMethodCode;
}

export interface VoidPaymentModalProps {
  /** El pago a anular; null cierra el modal. */
  payment: VoidTarget | null;
  onClose: () => void;
}

function VoidDone({ payment, onClose }: { payment: VoidTarget; onClose: () => void }) {
  const location = useLocation();
  const href = paymentPanelHref(location, { membershipId: payment.membership_id });
  return (
    <Modal
      open
      title={VOID_MESSAGES.doneTitle}
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cerrar
          </Button>
          <Link className={cx(buttonStyles.button, buttonStyles.primary, buttonStyles.md)} to={href} state={paymentPanelState({ amountCop: payment.amount_cop, method: payment.method })} onClick={onClose}>
            Registrar pago nuevo
          </Link>
        </>
      }
    >
      <p>{VOID_MESSAGES.done(formatCop(payment.amount_cop))}</p>
    </Modal>
  );
}

export function VoidPaymentModal({ payment, onClose }: VoidPaymentModalProps) {
  const canVoid = useCan("payments.void");
  const { voidPayment } = useVoidPayment();
  const [voided, setVoided] = useState<VoidTarget | null>(null);
  // ConfirmModal llama a onClose justo después de un onConfirm que sale bien: en ese caso el modal
  // de confirmación se cierra pero queda el de "Pago anulado".
  const justVoided = useRef(false);

  if (!canVoid) return null;
  if (voided) {
    return (
      <VoidDone
        payment={voided}
        onClose={() => {
          setVoided(null);
          onClose();
        }}
      />
    );
  }
  const target = payment;
  return (
    <ConfirmModal
      open={target !== null}
      title={VOID_MESSAGES.title}
      consequence={VOID_MESSAGES.consequence}
      confirmLabel="Anular pago"
      reasonRequired
      reasonLabel="Motivo"
      reasonHint={SENSITIVE_TEXT_WARNING}
      minReasonLength={1}
      maxReasonLength={VOID_REASON_MAX}
      onConfirm={async (reason) => {
        if (target === null) return;
        // ConfirmModal ya valida el mismo rango; un motivo inválido aquí es un error de programación.
        const parsed = voidPaymentSchema.safeParse({ reason: reason ?? "" });
        if (!parsed.success) throw toVoidError(null);
        try {
          await voidPayment({ id: target.id, reason: parsed.data.reason });
        } catch (error) {
          throw toVoidError(error);
        }
        justVoided.current = true;
        setVoided(target);
      }}
      onClose={() => {
        if (justVoided.current) {
          justVoided.current = false;
          return;
        }
        onClose();
      }}
    />
  );
}
