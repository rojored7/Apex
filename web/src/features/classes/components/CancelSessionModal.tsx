// S7-F3 · US-157 (front): cancelar una sesión (Sesiones.html, «Cancelar sesión»), admin y coach (`classes.view`).
// - ConfirmModal con motivo obligatorio de 3 a 200 caracteres (el api lo guarda en la sesión) y el aviso M-7.
// - 409 `session_finished` (la sesión ya terminó) y `session_already_cancelled` (otra persona se adelantó), 404, 403,
//   429 y 5xx dentro del modal. La mutación lleva el motivo: `gcTime: 0` y `reset()` (S3-D52).
import { useQueryClient } from "@tanstack/react-query";
import { isApiError } from "../../../core/api/errors";
import { HTTP_CONFLICT, HTTP_NOT_FOUND } from "../../../core/api/status";
import { useCan } from "../../../core/auth/useCan";
import { SENSITIVE_TEXT_WARNING } from "../../../shared/data/schemas/payment";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { SESSIONS_QUERY_KEY, useCancelSession, type SessionView } from "../api";
import { cancelSessionError } from "../classErrors";
import { CANCEL_REASON_MAX, CANCEL_REASON_MIN, cancelReasonSchema } from "../schemas";
import { formatTime24 } from "../../../core/i18n/format";

export interface CancelSessionModalProps {
  /** La sesión a cancelar; null cierra el modal. */
  session: SessionView | null;
  onClose: () => void;
  /** La sesión quedó cancelada (el padre avisa y relee la semana). */
  onDone: (session: SessionView) => void;
}

export const CANCEL_SESSION_CONSEQUENCE = "La sesión queda cancelada con el motivo que escribas y deja de aceptar check-in. Esto no se puede deshacer.";

export const cancelSessionTitle = (time: string): string => `¿Cancelar la sesión de las ${time}?`;

export function CancelSessionModal({ session, onClose, onDone }: CancelSessionModalProps) {
  const canView = useCan("classes.view");
  const cancel = useCancelSession();
  const queryClient = useQueryClient();
  if (!canView || session === null) return null;
  const target = session;
  return (
    <ConfirmModal
      open
      title={cancelSessionTitle(formatTime24(target.starts_at))}
      consequence={CANCEL_SESSION_CONSEQUENCE}
      confirmLabel="Sí, cancelar sesión"
      reasonRequired
      reasonLabel="Motivo"
      reasonHint={SENSITIVE_TEXT_WARNING}
      minReasonLength={CANCEL_REASON_MIN}
      maxReasonLength={CANCEL_REASON_MAX}
      onConfirm={async (reason) => {
        const parsed = cancelReasonSchema.safeParse({ reason: reason ?? "" });
        if (!parsed.success) throw cancelSessionError(null);
        try {
          await cancel.mutateAsync({ id: target.id, reason: parsed.data.reason });
        } catch (error) {
          // 409 (ya cancelada o terminada) y 404: otra persona cambió la sesión; el aviso dice «Actualizamos la semana», así que se relee.
          if (isApiError(error) && (error.status === HTTP_CONFLICT || error.status === HTTP_NOT_FOUND)) void queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY });
          throw cancelSessionError(error);
        }
        onDone(target);
      }}
      onClose={onClose}
    />
  );
}
