// S5-F4 · US-137 (front): "Recibo" de un pago (Pagos.html, detalle y fila): descarga el PDF de
// GET /payments/{id}/receipt.pdf por api.blob (sin caché ni almacenamiento; L-8). Lo ven admin y coach
// (`payments.receipt`); el socio no. Estados: descargando (botón ocupado y aviso), 404 (pago que ya no
// existe), 403, 429, 503 (con el mensaje del api) y cualquier otro error, siempre con qué hacer. El
// aviso del error queda junto al botón con role="alert".
import { useState } from "react";
import { useCan } from "../../../core/auth/useCan";
import { useBlobDownload } from "../../../shared/data/download";
import { Button } from "../../../shared/ui/Button";
import { cx } from "../../../shared/ui/cx";
import styles from "./ReceiptButton.module.css";

export const RECEIPT_LABEL = "Recibo";
export const RECEIPT_BUSY = "Preparando el recibo…";

export interface ReceiptButtonProps {
  paymentId: string;
  /** Para el nombre accesible de la fila ("Descargar el recibo del pago de Ana Gómez"). */
  memberName?: string;
  /** `inline` es el enlace de texto de la fila; `button` el botón secundario del detalle. */
  appearance?: "inline" | "button";
}

export function ReceiptButton({ paymentId, memberName, appearance = "button" }: ReceiptButtonProps) {
  const canReceipt = useCan("payments.receipt");
  const { download, isPending, blocked } = useBlobDownload();
  const [error, setError] = useState<string | null>(null);
  if (!canReceipt) return null;

  const label = memberName ? `Descargar el recibo del pago de ${memberName}` : "Descargar el recibo del pago";
  const run = (): void => {
    setError(null);
    download({ path: `/payments/${encodeURIComponent(paymentId)}/receipt.pdf`, fallbackName: `recibo-${paymentId.slice(0, 8)}.pdf` }).catch((failure: unknown) => {
      setError(failure instanceof Error ? failure.message : null);
    });
  };

  return (
    <span className={styles.root}>
      {appearance === "inline" ? (
        <button type="button" className={cx(styles.inline, isPending && styles.busy)} aria-label={label} aria-busy={isPending ? true : undefined} disabled={isPending || blocked} onClick={run}>
          {RECEIPT_LABEL}
        </button>
      ) : (
        <Button variant="secondary" aria-label={label} loading={isPending} disabled={blocked} onClick={run}>
          {RECEIPT_LABEL}
        </Button>
      )}
      <span role="status" className={styles.busyText}>
        {isPending ? RECEIPT_BUSY : ""}
      </span>
      {error ? (
        <span role="alert" className={styles.error}>
          {error}
        </span>
      ) : null}
    </span>
  );
}
