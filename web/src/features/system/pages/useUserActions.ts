// S2-F4b · US-050 y US-051: estado y textos de las confirmaciones de la fila de Usuarios
// (dar de baja, bloquear, desbloquear y cerrar sesiones) y el aviso que deja cada una.
// - Cada confirmación es un ConfirmModal: la pregunta en el título, la consecuencia en una
//   frase y la acción con su texto. "Dar de baja" va en `danger` (DESIGN.md: solo anular y dar
//   de baja); las demás en `primary`.
// - Un error se queda en el modal con el mensaje de userActionMessage() (por código).
// - Cerrar las sesiones propias (S2-D37) termina en endSession() y /login: el api ya cortó el
//   access token de esta pestaña y el canal avisa a las demás (L3 de la revisión del Sprint 2).
import { useCallback, useState } from "react";
import { useNavigate } from "react-router";
import { endSession } from "../../../core/auth/session";
import { formatCount } from "../../../core/i18n/format";
import { useDeleteUser, useLockUser, useRevokeSessions, useUnlockUser } from "../api";
import type { ButtonAction } from "../components/UserRowActions";
import type { UserRowView } from "../schemas";
import { toUserActionError } from "../userActions";

export type ConfirmKind = Exclude<ButtonAction, "resend">;

export interface PendingConfirm {
  kind: ConfirmKind;
  row: UserRowView;
}

export interface ConfirmCopy {
  title: string;
  consequence: string;
  confirmLabel: string;
  tone: "danger" | "primary";
}

export const DELETE_CONSEQUENCE = "La cuenta pierde el acceso de inmediato. Su historial se conserva.";
export const LOCK_CONSEQUENCE = "Cierra todas sus sesiones y le impide entrar hasta que lo desbloquees.";

function sessionsConsequence(count: number, isSelf: boolean): string {
  if (isSelf) return `Se cierran tus ${formatCount(count)} sesiones abiertas. También se cierra la de este navegador y tendrás que volver a iniciar sesión.`;
  if (count === 0) return "No tiene sesiones abiertas; igual se corta cualquier acceso que siga vigente.";
  if (count === 1) return "Se cierra su sesión abierta y tendrá que volver a iniciar sesión.";
  return `Se cierran sus ${formatCount(count)} sesiones abiertas y tendrá que volver a iniciar sesión.`;
}

export function confirmCopy({ kind, row }: PendingConfirm, isSelf: boolean): ConfirmCopy {
  switch (kind) {
    case "delete":
      return { title: `¿Dar de baja a ${row.email}?`, consequence: DELETE_CONSEQUENCE, confirmLabel: "Dar de baja", tone: "danger" };
    case "lock":
      return { title: `¿Bloquear a ${row.email}?`, consequence: LOCK_CONSEQUENCE, confirmLabel: "Bloquear", tone: "primary" };
    case "unlock":
      return { title: `¿Desbloquear a ${row.email}?`, consequence: "Podrá volver a entrar con su contraseña.", confirmLabel: "Desbloquear", tone: "primary" };
    case "revoke":
      return {
        title: isSelf ? "¿Cerrar todas tus sesiones?" : `¿Cerrar las sesiones de ${row.email}?`,
        consequence: sessionsConsequence(row.active_sessions, isSelf),
        confirmLabel: "Cerrar sesiones",
        tone: "primary",
      };
  }
}

export function revokedNotice(revoked: number, email: string): string {
  if (revoked === 0) return `No había sesiones abiertas de ${email}.`;
  if (revoked === 1) return `Se cerró 1 sesión de ${email}.`;
  return `Se cerraron ${formatCount(revoked)} sesiones de ${email}.`;
}

export interface UserActionsApi {
  pending: PendingConfirm | null;
  open: (kind: ConfirmKind, row: UserRowView) => void;
  close: () => void;
  /** Hace la acción pendiente; rechaza con el mensaje de la pantalla si falla. */
  confirm: () => Promise<void>;
  notice: string;
  setNotice: (notice: string) => void;
}

export function useUserActions(currentUserId: string | null): UserActionsApi {
  const navigate = useNavigate();
  const remove = useDeleteUser();
  const lock = useLockUser();
  const unlock = useUnlockUser();
  const revoke = useRevokeSessions();
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const [notice, setNotice] = useState("");
  // Estables: la columna "Acción" de UsersPage se memoriza con ellas.
  const open = useCallback((kind: ConfirmKind, row: UserRowView): void => {
    setPending({ kind, row });
  }, []);
  const close = useCallback((): void => {
    setPending(null);
  }, []);

  const run = async ({ kind, row }: PendingConfirm): Promise<void> => {
    const target = { id: row.id };
    switch (kind) {
      case "delete":
        await remove.mutateAsync(target);
        setNotice(`Se dio de baja a ${row.email}.`);
        return;
      case "lock":
        await lock.mutateAsync(target);
        setNotice(`${row.email} quedó bloqueado.`);
        return;
      case "unlock":
        await unlock.mutateAsync(target);
        setNotice(`${row.email} quedó desbloqueado.`);
        return;
      case "revoke": {
        const revoked = await revoke.mutateAsync(target);
        if (row.id === currentUserId) {
          endSession();
          void navigate("/login", { replace: true });
          return;
        }
        setNotice(revokedNotice(revoked, row.email));
      }
    }
  };

  const confirm = async (): Promise<void> => {
    if (!pending) return;
    try {
      await run(pending);
    } catch (error) {
      throw toUserActionError(error);
    }
  };

  return {
    pending,
    open,
    close,
    confirm,
    notice,
    setNotice,
  };
}
