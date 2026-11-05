// S5-F2 · US-130 (front): "Ver mensaje" del historial (Notif_Historial.html). Muestra el asunto y el
// mensaje tal como se generaron para el socio, en un panel de solo lectura. El texto ya viene escrito por
// el servidor; el teléfono y el correo nunca llegan al front.
import { formatDateTime } from "../../../core/i18n/format";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { whenOf } from "../historyView";
import type { NotificationRowView } from "../schemas";
import styles from "./AdminPanel.module.css";

export interface MessagePanelProps {
  notification: NotificationRowView | null;
  onClose: () => void;
}

export function MessagePanel({ notification, onClose }: MessagePanelProps) {
  if (!notification) return null;
  return (
    <SidePanel open title={`Mensaje para ${notification.member_name}`} onClose={onClose} cancelLabel="Cerrar">
      <div className={styles.form}>
        <p className={styles.label}>{formatDateTime(whenOf(notification))}</p>
        <p className={styles.label}>Asunto</p>
        <p className={styles.readonly}>{notification.rendered_subject}</p>
        <p className={styles.label}>Mensaje</p>
        <p className={styles.readonly}>{notification.rendered_body}</p>
      </div>
    </SidePanel>
  );
}
