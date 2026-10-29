// S4A-F4 · US-081 y US-082 (front; S4A-D34): las confirmaciones y los avisos de las acciones de /planes.
// - PlanConfirmDialog: ConfirmModal para desactivar ("Las membresías vigentes con este plan siguen
//   igual; el plan deja de aparecer al vender") o dar de baja, con el nombre del plan en la pregunta.
// - PlanNotices: el aviso de lo que salió bien (role="status", se puede cerrar) y el de lo que salió
//   mal (role="alert"); el 409 de la baja trae el mensaje del api y el botón "Desactivar". Todo como
//   texto de React (sin HTML del api).
import { X } from "lucide-react";
import { Button } from "../../../shared/ui/Button";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import type { PlanConfirmation, PlanProblem } from "../pages/usePlanRowActions";
import type { PlanRowView } from "../schemas";
import styles from "./PlanActionDialogs.module.css";

export const DEACTIVATE_CONSEQUENCE = "Las membresías vigentes con este plan siguen igual; el plan deja de aparecer al vender.";
export const DELETE_CONSEQUENCE = "El plan sale de la lista y ya no se puede vender. Solo se puede si no tiene membresías activas.";

export interface PlanConfirmDialogProps {
  confirming: PlanConfirmation | null;
  onDeactivate: (row: PlanRowView) => Promise<void>;
  onDelete: (row: PlanRowView) => Promise<void>;
  onClose: () => void;
}

export function PlanConfirmDialog({ confirming, onDeactivate, onDelete, onClose }: PlanConfirmDialogProps) {
  if (!confirming) return null;
  const { kind, row } = confirming;
  const isDelete = kind === "delete";
  return (
    <ConfirmModal
      open
      title={isDelete ? `¿Dar de baja el plan ${row.name}?` : `¿Desactivar el plan ${row.name}?`}
      consequence={isDelete ? DELETE_CONSEQUENCE : DEACTIVATE_CONSEQUENCE}
      confirmLabel={isDelete ? "Dar de baja" : "Desactivar"}
      tone={isDelete ? "danger" : "primary"}
      onConfirm={() => (isDelete ? onDelete(row) : onDeactivate(row))}
      onClose={onClose}
    />
  );
}

export interface PlanNoticesProps {
  notice: string | null;
  problem: PlanProblem | null;
  isDeactivating: boolean;
  onDismissNotice: () => void;
  onDismissProblem: () => void;
  onDeactivate: (row: PlanRowView) => void;
}

export function PlanNotices({ notice, problem, isDeactivating, onDismissNotice, onDismissProblem, onDeactivate }: PlanNoticesProps) {
  const blockedRow = problem?.row ?? null;
  return (
    <>
      {/* Las regiones existen siempre para que el lector de pantalla anuncie el texto nuevo. */}
      <div role="status">
        {notice ? (
          <div className={styles.notice}>
            <p className={styles.text}>{notice}</p>
            <button type="button" className={styles.dismiss} aria-label="Cerrar aviso" onClick={onDismissNotice}>
              <X size={20} aria-hidden="true" />
            </button>
          </div>
        ) : null}
      </div>
      {problem ? (
        <div role="alert" className={styles.problem}>
          <p className={styles.text}>{problem.message}</p>
          {blockedRow ? (
            <Button
              variant="secondary"
              loading={isDeactivating}
              aria-label={`Desactivar el plan ${blockedRow.name}`}
              onClick={() => {
                onDeactivate(blockedRow);
              }}
            >
              Desactivar
            </Button>
          ) : null}
          <button type="button" className={styles.dismiss} aria-label="Cerrar el aviso de error" onClick={onDismissProblem}>
            <X size={20} aria-hidden="true" />
          </button>
        </div>
      ) : null}
    </>
  );
}
