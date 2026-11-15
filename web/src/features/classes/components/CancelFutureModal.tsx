// S7-F2 · US-158 (front): cancelar de una vez las sesiones futuras de una franja (Horario.html, acción de la franja).
// - Solo admin (`classes.schedule`): para el coach no pinta nada; el api vuelve a verificar (403).
// - ConfirmModal con motivo obligatorio de 3 a 200 caracteres (el api guarda el motivo en cada sesión) y el aviso M-7.
//   Dice que NO desactiva la franja: para que deje de generar sesiones se pausa (US-155).
// - 200 con `cancelled_count`: el padre avisa cuántas se cancelaron.
// DESIGN-GAP: la historia pide mostrar «cuántas sesiones se cancelarán» antes de confirmar; el api no tiene un conteo
// previo (solo responde `cancelled_count` al cancelar), así que el número se informa después.
import { useCan } from "../../../core/auth/useCan";
import { SENSITIVE_TEXT_WARNING } from "../../../shared/data/schemas/payment";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { useCancelFutureSessions, type SlotView } from "../api";
import { cancelFutureError } from "../classErrors";
import { CANCEL_REASON_MAX, CANCEL_REASON_MIN, cancelReasonSchema } from "../schemas";

export interface CancelFutureModalProps {
  /** La franja; null cierra el modal. */
  slot: SlotView | null;
  onClose: () => void;
  /** Las sesiones quedaron canceladas (el padre avisa cuántas y cierra). */
  onDone: (slot: SlotView, cancelledCount: number) => void;
}

export const CANCEL_FUTURE_CONSEQUENCE =
  "Se cancelan todas las sesiones futuras ya generadas de esta franja, con este motivo. Esto no desactiva la franja: seguirá generando sesiones nuevas. Para que no genere más, páusala al editarla.";

export const cancelFutureTitle = (time: string): string => `¿Cancelar las sesiones futuras de la franja de las ${time}?`;

export function CancelFutureModal({ slot, onClose, onDone }: CancelFutureModalProps) {
  const canSchedule = useCan("classes.schedule");
  const cancel = useCancelFutureSessions();
  if (!canSchedule || slot === null) return null;
  const target = slot;
  return (
    <ConfirmModal
      open
      title={cancelFutureTitle(target.start_time)}
      consequence={CANCEL_FUTURE_CONSEQUENCE}
      confirmLabel="Sí, cancelar sesiones"
      reasonRequired
      reasonLabel="Motivo"
      reasonHint={SENSITIVE_TEXT_WARNING}
      minReasonLength={CANCEL_REASON_MIN}
      maxReasonLength={CANCEL_REASON_MAX}
      onConfirm={async (reason) => {
        const parsed = cancelReasonSchema.safeParse({ reason: reason ?? "" });
        if (!parsed.success) throw cancelFutureError(null);
        let count: number;
        try {
          count = await cancel.mutateAsync({ id: target.id, reason: parsed.data.reason });
        } catch (error) {
          throw cancelFutureError(error);
        }
        onDone(target, count);
      }}
      onClose={onClose}
    />
  );
}
