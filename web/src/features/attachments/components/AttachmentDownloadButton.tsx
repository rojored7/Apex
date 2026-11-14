// S6-F3 · US-150: "Descargar" de una fila de adjuntos. Baja GET /attachments/{id} por api.blob (sin
// caché ni almacenamiento) y lo entrega con un enlace a[download] (downloadBlob): nunca window.open ni
// un blob: en una pestaña, y el PDF no se abre (L-2). El nombre lo propone el api (Content-Disposition).
// Un 403 o un 404 se explican con el texto de la pantalla; el resto, con el de las descargas.
import { ApiError } from "../../../core/api/errors";
import { HTTP_FORBIDDEN, HTTP_NOT_FOUND } from "../../../core/api/status";
import { useBlobDownload } from "../../../shared/data/download";
import { ATTACHMENT_MESSAGES } from "../attachmentErrors";
import { fallbackFileName, kindLabel } from "../lib/attachmentText";
import type { AttachmentView } from "../schemas";
import { formatDate } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import styles from "./AttachmentDownloadButton.module.css";

export const DOWNLOAD_BUSY = "Preparando la descarga…";

export interface AttachmentDownloadButtonProps {
  attachment: Pick<AttachmentView, "id" | "kind" | "created_at" | "mime">;
  /** Recibe el mensaje del fallo (o null al empezar otra descarga). */
  onError: (message: string | null) => void;
}

function failureText(status: number, message: string): string {
  if (status === HTTP_FORBIDDEN) return ATTACHMENT_MESSAGES.forbidden;
  if (status === HTTP_NOT_FOUND) return ATTACHMENT_MESSAGES.notFound;
  return message;
}

export function AttachmentDownloadButton({ attachment, onError }: AttachmentDownloadButtonProps) {
  const { download, isPending, blocked } = useBlobDownload();
  const label = `Descargar ${kindLabel(attachment.kind)} subido el ${formatDate(attachment.created_at)}`;
  const run = (): void => {
    onError(null);
    download({ path: `/attachments/${encodeURIComponent(attachment.id)}`, fallbackName: fallbackFileName(attachment) }).catch((failure: unknown) => {
      onError(failure instanceof ApiError ? failureText(failure.status, failure.message) : ATTACHMENT_MESSAGES.listFailed);
    });
  };
  return (
    <span className={styles.root}>
      <Button variant="secondary" aria-label={label} loading={isPending} disabled={blocked} onClick={run}>
        Descargar
      </Button>
      <span role="status" className={styles.busy}>
        {isPending ? DOWNLOAD_BUSY : ""}
      </span>
    </span>
  );
}
