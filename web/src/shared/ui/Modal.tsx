// S2-F4b: diálogo centrado para mostrar un resultado que no es una confirmación (el enlace
// reenviado de Usuarios). Mismo velo, caja y trampa de foco que ConfirmModal; título, cuerpo
// libre y una fila de acciones. Escape cierra, salvo mientras `busy` (una petición en curso
// no se abandona a medias). El contenido se monta al abrir: cada apertura empieza limpia.
// DESIGN-GAP: DESIGN.md solo nombra ConfirmModal; este es su hermano para contenido.
import { useId, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useFocusTrap } from "../hooks/useFocusTrap";
import styles from "./Modal.module.css";

export interface ModalProps {
  open: boolean;
  title: string;
  /** Hay una petición en curso: Escape no cierra y el diálogo se marca ocupado. */
  busy?: boolean;
  onClose: () => void;
  /** Botones del pie (Volver, la acción, Listo). */
  actions: ReactNode;
  children: ReactNode;
}

function ModalContent({ title, busy = false, onClose, actions, children }: Omit<ModalProps, "open">) {
  const titleId = useId();
  const dialogRef = useFocusTrap<HTMLDivElement>(true, {
    onEscape: () => {
      if (!busy) onClose();
    },
  });
  return (
    <div className={styles.backdrop}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-busy={busy ? true : undefined} tabIndex={-1} className={styles.modal}>
        <h2 id={titleId} className={styles.title}>
          {title}
        </h2>
        <div className={styles.body}>{children}</div>
        <div className={styles.actions}>{actions}</div>
      </div>
    </div>
  );
}

export function Modal({ open, ...props }: ModalProps) {
  return open ? createPortal(<ModalContent {...props} />, document.body) : null;
}
