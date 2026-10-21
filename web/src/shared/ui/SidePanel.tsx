// US-065 T2: panel lateral para formularios cortos sobre una lista (Planes.html). Entra
// desde la derecha y ocupa todo el ancho en celular. Se cierra con ✕, Cancelar, Escape o
// clic fuera; con cambios sin guardar pregunta antes con un ConfirmModal.
import { X } from "lucide-react";
import { useId, useState, type MouseEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useFocusTrap } from "../hooks/useFocusTrap";
import { Button } from "./Button";
import { ConfirmModal } from "./ConfirmModal";
import styles from "./SidePanel.module.css";

export interface SidePanelProps {
  open: boolean;
  title: string;
  /** Hay cambios sin guardar: cerrar pide confirmación. */
  isDirty?: boolean;
  onClose: () => void;
  /** Acciones del pie después de Cancelar (por ejemplo, Guardar). */
  footer?: ReactNode;
  cancelLabel?: string;
  children: ReactNode;
}

function PanelContent({ title, isDirty = false, onClose, footer, cancelLabel = "Cancelar", children }: Omit<SidePanelProps, "open">) {
  const titleId = useId();
  const [confirming, setConfirming] = useState(false);

  const requestClose = (): void => {
    if (isDirty) setConfirming(true);
    else onClose();
  };
  const panelRef = useFocusTrap<HTMLDivElement>(true, { onEscape: requestClose });

  const onBackdropMouseDown = (event: MouseEvent<HTMLDivElement>): void => {
    if (event.target === event.currentTarget) requestClose();
  };

  return (
    <>
      <div className={styles.backdrop} data-testid="side-panel-backdrop" onMouseDown={onBackdropMouseDown}>
        <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} className={styles.panel}>
          <div className={styles.head}>
            <h2 id={titleId} className={styles.title}>
              {title}
            </h2>
            <button type="button" className={styles.close} aria-label="Cerrar" onClick={requestClose}>
              <X size={20} aria-hidden="true" />
            </button>
          </div>
          <div className={styles.body}>{children}</div>
          <div className={styles.footer}>
            <Button variant="secondary" onClick={requestClose}>
              {cancelLabel}
            </Button>
            {footer}
          </div>
        </div>
      </div>
      <ConfirmModal
        open={confirming}
        title="¿Descartar los cambios?"
        consequence="Lo que escribiste en este panel se pierde."
        confirmLabel="Descartar cambios"
        onConfirm={onClose}
        onClose={() => {
          setConfirming(false);
        }}
      />
    </>
  );
}

export function SidePanel({ open, ...props }: SidePanelProps) {
  return open ? createPortal(<PanelContent {...props} />, document.body) : null;
}
