// S4A-F4 · US-080, US-081 y US-082 (front; S4A-D34): el estado de las acciones de la fila de /planes.
// - `editing`: el plan abierto en PlanForm (modo edición).
// - `confirming`: la confirmación abierta (desactivar o dar de baja) con su plan.
// - `notice`: el aviso de lo que salió bien ("Plan desactivado: Mensual."); `problem`: lo que salió
//   mal fuera de un modal (activar) o el 409 de la baja, con el plan a desactivar en su lugar.
// Las mutaciones van por useSetPlanActive y useDeletePlan (useSensitiveMutation). Los errores dentro
// de una confirmación se relanzan con el mensaje de la pantalla (activeError, deleteError) para que
// ConfirmModal los pinte; el 409 `plan_has_active_memberships` no: cierra el modal y deja el aviso con
// el mensaje del api (solo el conteo) y el botón "Desactivar".
import { useRef, useState } from "react";
import { useDeletePlan, useSetPlanActive } from "../api";
import type { PlanRowAction } from "../components/PlanRowActions";
import { activeError, deleteError, planInUseMessage } from "../planErrors";
import type { PlanRowView } from "../schemas";

export type ConfirmKind = "deactivate" | "delete";

export interface PlanConfirmation {
  kind: ConfirmKind;
  row: PlanRowView;
}

export interface PlanProblem {
  message: string;
  /** Con plan: el 409 de la baja ofrece "Desactivar" ese plan. */
  row: PlanRowView | null;
}

export const PLAN_NOTICES = {
  created: (name: string) => `Plan creado: ${name}.`,
  saved: (name: string) => `Plan guardado: ${name}.`,
  activated: (name: string) => `Plan activado: ${name}.`,
  deactivated: (name: string) => `Plan desactivado: ${name}.`,
  deleted: (name: string) => `Plan dado de baja: ${name}.`,
} as const;

export function usePlanRowActions() {
  const setActive = useSetPlanActive();
  const remove = useDeletePlan();
  const [editing, setEditing] = useState<PlanRowView | null>(null);
  const [confirming, setConfirming] = useState<PlanConfirmation | null>(null);
  const [notice, setNoticeState] = useState<string | null>(null);
  const [problem, setProblemState] = useState<PlanProblem | null>(null);

  // Un aviso a la vez: el nuevo reemplaza al anterior, sea bueno o malo.
  const setNotice = (text: string | null): void => {
    setProblemState(null);
    setNoticeState(text);
  };
  const setProblem = (next: PlanProblem | null): void => {
    setNoticeState(null);
    setProblemState(next);
  };

  // Revisión de seguridad de F4 (LOW-2): activar y "Desactivar" del aviso salen sin confirmación; un
  // segundo clic mientras cambia un estado no sale (bandera en ref, además de isPending y del botón
  // deshabilitado: dos clics seguidos llegan antes de que React vuelva a pintar).
  const changing = useRef(false);
  const changeDirectly = async (row: PlanRowView, active: boolean): Promise<void> => {
    if (changing.current || setActive.isPending) return;
    changing.current = true;
    try {
      const saved = await setActive.mutateAsync({ id: row.id, active });
      setNotice(active ? PLAN_NOTICES.activated(saved.name) : PLAN_NOTICES.deactivated(saved.name));
    } catch (error) {
      setProblem({ message: activeError(error).message, row: null });
    } finally {
      changing.current = false;
    }
  };

  const onAction = (action: PlanRowAction, row: PlanRowView): void => {
    if (action === "edit") setEditing(row);
    else if (action === "activate") void changeDirectly(row, true);
    else setConfirming({ kind: action, row });
  };

  /** ConfirmModal "Desactivar": un error se relanza con el mensaje de la pantalla. */
  const confirmDeactivate = async (row: PlanRowView): Promise<void> => {
    try {
      const saved = await setActive.mutateAsync({ id: row.id, active: false });
      setNotice(PLAN_NOTICES.deactivated(saved.name));
    } catch (error) {
      throw activeError(error);
    }
  };

  /** ConfirmModal "Dar de baja": el 409 de membresías activas cierra el modal y deja el aviso. */
  const confirmDelete = async (row: PlanRowView): Promise<void> => {
    try {
      await remove.mutateAsync(row.id);
      setNotice(PLAN_NOTICES.deleted(row.name));
    } catch (error) {
      const inUse = planInUseMessage(error);
      if (inUse === null) throw deleteError(error);
      setProblem({ message: inUse, row });
    }
  };

  /** "Desactivar" del aviso del 409. */
  const deactivateInstead = (row: PlanRowView): Promise<void> => changeDirectly(row, false);

  return {
    editing,
    closeEditing: () => {
      setEditing(null);
    },
    confirming,
    closeConfirming: () => {
      setConfirming(null);
    },
    notice,
    setNotice,
    problem,
    dismissProblem: () => {
      setProblemState(null);
    },
    isChangingState: setActive.isPending,
    onAction,
    confirmDeactivate,
    confirmDelete,
    deactivateInstead,
  };
}
