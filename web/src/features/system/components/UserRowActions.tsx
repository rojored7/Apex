// S2-F4b · US-049 a US-052: acciones de una fila de Usuarios (columna "Acción").
// "Editar" es un enlace real a `?usuario=<id>` (como en Usuarios.html); las demás son botones
// que abren su confirmación o el reenvío del enlace. Qué acciones hay lo decide rowActions()
// (userActions.ts); el api igual vuelve a verificar cada una.
// DESIGN-GAP: DESIGN.md pide filas sin botones de editar o borrar y Usuarios.html solo tiene
// "Editar"; el blueprint F4b pone las acciones del ciclo de vida en la fila.
import { Link } from "react-router";
import { formatCount } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import type { UserRowView } from "../schemas";
import type { RowAction } from "../userActions";
import styles from "./UserRowActions.module.css";

export type ButtonAction = Exclude<RowAction, "edit">;

export interface UserRowActionsProps {
  row: UserRowView;
  actions: readonly RowAction[];
  editHref: string;
  onAction: (action: ButtonAction, row: UserRowView) => void;
}

const LABELS: Readonly<Record<Exclude<ButtonAction, "revoke">, string>> = Object.freeze({
  resend: "Reenviar enlace",
  lock: "Bloquear",
  unlock: "Desbloquear",
  delete: "Dar de baja",
});

export function sessionsLabel(count: number): string {
  return `Cerrar sesiones (${formatCount(count)})`;
}

export function UserRowActions({ row, actions, editHref, onAction }: UserRowActionsProps) {
  return (
    <div role="group" aria-label={`Acciones de ${row.email}`} className={styles.actions}>
      {actions.map((action) => {
        if (action === "edit") {
          return (
            <Link key={action} to={editHref} className={styles.edit} aria-label={`Editar: ${row.email}`}>
              Editar
            </Link>
          );
        }
        const label = action === "revoke" ? sessionsLabel(row.active_sessions) : LABELS[action];
        // El nombre accesible empieza por el texto visible (WCAG 2.5.3) y nombra la cuenta:
        // en una lista de botones del lector de pantalla no hay dos iguales.
        return (
          <Button
            key={action}
            variant={action === "delete" ? "danger" : "ghost"}
            className={styles.button}
            aria-label={`${label}: ${row.email}`}
            onClick={() => {
              onAction(action, row);
            }}
          >
            {label}
          </Button>
        );
      })}
    </div>
  );
}
