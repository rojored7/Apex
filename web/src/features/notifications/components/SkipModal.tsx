// S5-F1 · US-129 (front): "Omitir" de PorAvisarHoy.html pide un motivo corto (3 a 500 caracteres).
// Usa ConfirmModal (motivo obligatorio, un solo envío, el error del api dentro del diálogo). El motivo
// se guarda en claro: la ayuda pide no escribir teléfonos, documentos ni datos de salud (M-7).
import { SKIP_REASON_LIMITS } from "../schemas";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { useSkip } from "../api";
import { skipError } from "../noticeErrors";

export interface SkipTarget {
  id: string;
  member_name: string;
}

export interface SkipModalProps {
  /** El aviso a omitir; `null` mantiene el diálogo cerrado. */
  target: SkipTarget | null;
  onClose: () => void;
  /** Se llama con el nombre del socio cuando el api confirmó. */
  onSkipped: (memberName: string) => void;
}

export function SkipModal({ target, onClose, onSkipped }: SkipModalProps) {
  const skip = useSkip();
  const name = target?.member_name ?? "";

  const confirm = async (reason: string | undefined): Promise<void> => {
    if (!target) return;
    try {
      await skip.mutateAsync({ id: target.id, reason: reason ?? "" });
    } catch (error) {
      throw skipError(error);
    }
    onSkipped(name);
  };

  return (
    <ConfirmModal
      open={target !== null}
      title={`¿Omitir el aviso de ${name}?`}
      consequence="El aviso queda en el historial como omitido, con tu motivo, y no se envía."
      confirmLabel="Omitir aviso"
      tone="primary"
      reasonRequired
      minReasonLength={SKIP_REASON_LIMITS.min}
      maxReasonLength={SKIP_REASON_LIMITS.max}
      reasonHint="Por ejemplo: ya pagó, pidió que no lo contactemos. No escribas teléfonos, documentos ni datos de salud."
      onConfirm={confirm}
      onClose={onClose}
    />
  );
}
