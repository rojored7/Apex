// S5-F1 · US-127 (front): una fila de "Por avisar hoy" (PorAvisarHoy.html, .w-row). En celular es una
// tarjeta. Muestra el socio (enlace a su ficha), para qué día es el aviso, el mensaje ya escrito, la
// etiqueta de canal y estado, "Abrir WhatsApp" (solo el canal whatsapp_link: el api responde 409
// `wrong_channel` con otro) y "Omitir". El teléfono nunca llega aquí: el api no lo manda.
// DESIGN-GAP: PorAvisarHoy.html muestra "Vence hoy · Trimestral · 320 ••• 441" y etiquetas "push".
// NotificationOut no trae el plan ni el teléfono enmascarado y en v0.2 no hay push; la fila usa la
// fecha del aviso y su asunto.
import { Link } from "react-router";
import { formatDate, todayBogota } from "../../../core/i18n/format";
import { memberHref } from "../../../shared/lib/routes";
import { Button } from "../../../shared/ui/Button";
import { cx } from "../../../shared/ui/cx";
import { LAST_ERROR_LABELS, type NotificationRowView } from "../schemas";
import styles from "./TodayRow.module.css";
import { WaButton } from "./WaButton";

export interface TodayRowProps {
  row: NotificationRowView;
  onOpened: (memberName: string) => void;
  onSkip: (row: NotificationRowView) => void;
}

/** "Para hoy" o "Del 15 oct 2026" (un aviso de un día anterior que sigue sin atenderse). */
export function whenText(targetDate: string, today: string): string {
  return targetDate === today ? "Para hoy" : `Del ${formatDate(targetDate)}`;
}

/** La etiqueta de canal y estado, siempre con texto (el color solo la refuerza). */
export function tagText(row: NotificationRowView): string {
  if (row.channel === "whatsapp_link") return "WhatsApp pendiente";
  if (row.status === "failed") {
    const reason = LAST_ERROR_LABELS[row.last_error ?? "unknown"] ?? "error desconocido";
    return `Correo: falló · ${reason}`;
  }
  return "Correo por enviar";
}

export function TodayRow({ row, onOpened, onSkip }: TodayRowProps) {
  const warning = row.status === "failed";
  return (
    <li className={styles.row}>
      <div className={styles.who}>
        <b>
          <Link to={memberHref(row.member_id)} className={styles.name}>
            {row.member_name}
          </Link>
        </b>
        <div className={styles.note}>
          <span>{whenText(row.target_date, todayBogota())}</span>
          <span className={styles.subject}>{row.rendered_subject}</span>
        </div>
        <span className={cx(styles.tag, warning && styles.warning)}>{tagText(row)}</span>
      </div>
      <p className={styles.msg}>{row.rendered_body}</p>
      <div className={styles.actions}>
        {row.channel === "whatsapp_link" ? (
          <WaButton
            notificationId={row.id}
            memberName={row.member_name}
            onOpened={() => {
              onOpened(row.member_name);
            }}
          />
        ) : null}
        <Button
          variant="secondary"
          className={styles.skip}
          aria-label={`Omitir aviso de ${row.member_name}`}
          onClick={() => {
            onSkip(row);
          }}
        >
          Omitir
        </Button>
      </div>
    </li>
  );
}
