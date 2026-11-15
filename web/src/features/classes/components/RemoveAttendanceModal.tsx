// S7-F4 · US-161 (front): quitar una asistencia. Motivo opcional (1 a 200) que viaja en el cuerpo del DELETE (E4).
// - 403 `attendance_locked` (el coach solo quita las de hoy o ayer; el admin, cualquiera), 404, 429 y 5xx dentro del modal.
// - La llegada se borra de forma lógica y auditada; si descontó una clase de un plan por clases, se devuelve (US-160).
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { SENSITIVE_TEXT_WARNING } from "../../../shared/data/schemas/payment";
import { useRemoveAttendance, type AttendeeView } from "../api";
import { removeAttendanceError } from "../classErrors";
import { CANCEL_REASON_MAX } from "../schemas";

export interface RemoveAttendanceModalProps {
  /** La asistencia a quitar; null cierra el modal. */
  attendee: AttendeeView | null;
  onClose: () => void;
}

export const REMOVE_CONSEQUENCE = "Se borra su llegada de esta clase y, si le descontó una clase de su plan, se la devolvemos. Queda en la auditoría.";

export function RemoveAttendanceModal({ attendee, onClose }: RemoveAttendanceModalProps) {
  const remove = useRemoveAttendance();
  if (attendee === null) return null;
  const target = attendee;
  const name = `${target.first_name} ${target.last_name}`.trim();
  return (
    <ConfirmModal
      open
      title={`¿Quitar a ${name} de esta clase?`}
      consequence={REMOVE_CONSEQUENCE}
      confirmLabel="Quitar asistencia"
      showReason
      reasonLabel="Motivo (opcional)"
      reasonHint={SENSITIVE_TEXT_WARNING}
      maxReasonLength={CANCEL_REASON_MAX}
      onConfirm={async (reason) => {
        try {
          await remove.mutateAsync({ id: target.id, reason });
        } catch (error) {
          throw removeAttendanceError(error);
        }
      }}
      onClose={onClose}
    />
  );
}
