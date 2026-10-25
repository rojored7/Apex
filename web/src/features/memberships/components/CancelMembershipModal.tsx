// S3-F5 · US-090 (front): anular una membresía (Membresias.html, "Modal · ¿Anular la membresía de …?";
// DESIGN.md regla 3: anular es un modal con confirmación y pide motivo).
// - Solo admin (`memberships.cancel`): para el coach no pinta nada; el api vuelve a verificar (403).
// - ConfirmModal con la consecuencia del diseño, motivo obligatorio de 5 a 500 caracteres tras
//   recortar (D17) y el aviso M-7 bajo el motivo (S3-D50). La membresía queda anulada con motivo,
//   autor y fecha; sus pagos no se tocan (D3): si hay que devolver dinero, se anula cada pago aparte.
// - Errores dentro del modal en palabras de la pantalla (toCancelError): 409
//   `membership_already_cancelled` dice que otra persona la anuló y useCancelMembership relee la lista.
// - ConfirmModal ya garantiza un solo envío por confirmación; la mutación lleva el motivo:
//   `gcTime: 0` y `reset()` al terminar (S3-D52).
import { useCan } from "../../../core/auth/useCan";
import { SENSITIVE_TEXT_WARNING } from "../../../shared/data/schemas/payment";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { useCancelMembership } from "../api";
import { toCancelError } from "../membershipErrors";
import { CANCEL_REASON_MAX, CANCEL_REASON_MIN, cancelMembershipSchema } from "../schemas";

export interface CancelTarget {
  id: string;
  member_name: string;
}

export interface CancelMembershipModalProps {
  /** La membresía a anular; null cierra el modal. */
  membership: CancelTarget | null;
  onClose: () => void;
  /** La membresía quedó anulada (el padre avisa y cierra). */
  onCancelled: (target: CancelTarget) => void;
}

export const CANCEL_CONSEQUENCE = "La membresía deja de contar desde hoy. Los pagos asociados no se tocan: si hay que devolver dinero, se anula el pago aparte.";

export const cancelTitle = (memberName: string): string => `¿Anular la membresía de ${memberName}?`;

export function CancelMembershipModal({ membership, onClose, onCancelled }: CancelMembershipModalProps) {
  const canCancel = useCan("memberships.cancel");
  const { cancel } = useCancelMembership();
  if (!canCancel || membership === null) return null;
  const target = membership;
  return (
    <ConfirmModal
      open
      title={cancelTitle(target.member_name)}
      consequence={CANCEL_CONSEQUENCE}
      confirmLabel="Sí, anular"
      reasonRequired
      reasonLabel="Motivo"
      reasonHint={SENSITIVE_TEXT_WARNING}
      minReasonLength={CANCEL_REASON_MIN}
      maxReasonLength={CANCEL_REASON_MAX}
      onConfirm={async (reason) => {
        // ConfirmModal ya valida el mismo rango; un motivo inválido aquí es un error de programación.
        const parsed = cancelMembershipSchema.safeParse({ reason: reason ?? "" });
        if (!parsed.success) throw toCancelError(null);
        try {
          await cancel({ id: target.id, reason: parsed.data.reason });
        } catch (error) {
          throw toCancelError(error);
        }
        onCancelled(target);
      }}
      onClose={onClose}
    />
  );
}
