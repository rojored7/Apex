// S3-F1 · US-076 (front): dar de baja y reactivar desde la ficha, con ConfirmModal (DESIGN.md
// regla 3: pregunta en el título, consecuencia en una frase, "Volver" y la acción).
// - DeactivateMemberModal: DELETE /members/{id} (solo admin, members.delete). La baja es lógica
//   (N-20): "El socio deja de aparecer en la lista; sus membresías, pagos e historial se conservan".
// - ReactivateMemberModal: POST /members/{id}/reactivate (solo admin, members.reactivate). Si otro
//   socio vivo tomó el documento (409 `member_document_duplicated` con `existing_id`), el modal se
//   cierra y entrega el id a la ficha (onDuplicate), que avisa con el enlace a ese socio: un modal
//   no lleva enlaces en su error.
// - Los demás errores quedan dentro del modal en palabras de la pantalla (statusChangeError).
// DESIGN-GAP: Socio_Ficha.html pone "Dar de baja" en el menú "Más" y no dibuja ni la confirmación
// ni "Reactivar" (BRECHAS §10); se usa el ConfirmModal de DESIGN.md.
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { useDeactivateMember, useReactivateMember } from "../api";
import { duplicatedMemberId, statusChangeError } from "../memberErrors";

export interface MemberStatusTarget {
  id: string;
  /** Nombre en claro (va en el leaderboard); nunca un dato cifrado. */
  name: string;
}

export interface DeactivateMemberModalProps {
  open: boolean;
  member: MemberStatusTarget;
  onClose: () => void;
  /** La acción salió bien (la ficha avisa y se relee). */
  onDone: () => void;
}

export const DEACTIVATE_CONSEQUENCE = "El socio deja de aparecer en la lista; sus membresías, pagos e historial se conservan.";
export const REACTIVATE_CONSEQUENCE = "Vuelve a aparecer en la lista de socios y se puede editar y venderle de nuevo.";

export function DeactivateMemberModal({ open, member, onClose, onDone }: DeactivateMemberModalProps) {
  const { mutateAsync } = useDeactivateMember();

  const confirm = async (): Promise<void> => {
    try {
      await mutateAsync(member.id);
    } catch (error) {
      throw statusChangeError(error, "deactivate");
    }
    onDone();
  };

  return (
    <ConfirmModal
      open={open}
      title={`¿Dar de baja a ${member.name}?`}
      consequence={DEACTIVATE_CONSEQUENCE}
      confirmLabel="Dar de baja"
      tone="danger"
      onConfirm={confirm}
      onClose={onClose}
    />
  );
}

export interface ReactivateMemberModalProps extends DeactivateMemberModalProps {
  /** 409: otro socio vivo tiene el documento; la ficha enlaza a él. */
  onDuplicate: (existingId: string) => void;
}

export function ReactivateMemberModal({ open, member, onClose, onDone, onDuplicate }: ReactivateMemberModalProps) {
  const { mutateAsync } = useReactivateMember();

  const confirm = async (): Promise<void> => {
    try {
      await mutateAsync(member.id);
    } catch (error) {
      const existingId = duplicatedMemberId(error);
      // El modal se cierra (ConfirmModal llama a onClose al resolver) y la ficha muestra el enlace.
      if (existingId !== null) {
        onDuplicate(existingId);
        return;
      }
      throw statusChangeError(error, "reactivate");
    }
    onDone();
  };

  return (
    <ConfirmModal
      open={open}
      title={`¿Reactivar a ${member.name}?`}
      consequence={REACTIVATE_CONSEQUENCE}
      confirmLabel="Reactivar"
      tone="primary"
      onConfirm={confirm}
      onClose={onClose}
    />
  );
}
