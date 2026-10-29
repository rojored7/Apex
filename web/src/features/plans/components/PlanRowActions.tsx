// S4A-F4 · US-080, US-081 y US-082 (front; S4A-D34): las acciones de una fila de /planes (columna
// "Acción" de Planes.html), solo con `plans.manage` (<Can>; el api vuelve a verificar).
// - Editar: abre PlanForm en modo edición.
// - Desactivar (plan activo) o Activar (plan inactivo): el padre confirma la desactivación.
// - Dar de baja: el padre confirma; un plan con membresías activas responde 409.
// Cada botón nombra el plan para el lector de pantalla ("Desactivar: Mensual"; el nombre accesible
// empieza por el texto visible, WCAG 2.5.3).
// DESIGN-GAP: Planes.html solo dibuja "Editar" en la fila y la casilla "Activo (se puede vender)" en
// el panel; activar, desactivar y dar de baja son POST y DELETE propios (S4A-D23, S4A-D24) y van como
// acciones de la fila, igual que en Usuarios y Membresías (botones con aspecto de enlace, no un menú
// desplegable).
import { Can } from "../../../core/auth/Can";
import { cx } from "../../../shared/ui/cx";
import type { PlanRowView } from "../schemas";
import styles from "./PlanRowActions.module.css";

export type PlanRowAction = "edit" | "activate" | "deactivate" | "delete";

export interface PlanRowActionsProps {
  row: PlanRowView;
  onAction: (action: PlanRowAction, row: PlanRowView) => void;
  /** Revisión de seguridad de F4 (LOW-2): mientras cambia el estado de un plan, Activar y Desactivar no responden. */
  isChangingState?: boolean;
}

const LABELS: Readonly<Record<PlanRowAction, string>> = Object.freeze({
  edit: "Editar",
  activate: "Activar",
  deactivate: "Desactivar",
  delete: "Dar de baja",
});

/** Las acciones de la fila en orden: Editar, Activar o Desactivar según el estado, Dar de baja. */
export function planRowActions(row: Pick<PlanRowView, "is_active">): readonly PlanRowAction[] {
  return ["edit", row.is_active ? "deactivate" : "activate", "delete"];
}

export function PlanRowActions({ row, onAction, isChangingState = false }: PlanRowActionsProps) {
  return (
    <Can action="plans.manage">
      <div role="group" aria-label={`Acciones de ${row.name}`} className={styles.actions}>
        {planRowActions(row).map((action) => (
          <button
            key={action}
            type="button"
            className={cx(styles.action, action === "delete" && styles.danger)}
            aria-label={`${LABELS[action]}: ${row.name}`}
            disabled={isChangingState && (action === "activate" || action === "deactivate")}
            onClick={() => {
              onAction(action, row);
            }}
          >
            {LABELS[action]}
          </button>
        ))}
      </div>
    </Can>
  );
}
