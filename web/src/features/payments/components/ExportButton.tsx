// S5-F4 · US-139 (front): "Exportar" de /pagos (Pagos.html), solo admin (`payments.export`).
// - Abre un ConfirmModal con el texto fijo de la exportación ("La descarga contiene datos personales y
//   queda registrada en la auditoría") y, al confirmar, valida con Zod el rango de "Fecha del pago"
//   (obligatorio, de 12 meses como máximo) ANTES de llamar a GET /payments/export. Un rango inválido
//   se explica dentro del modal y no sale ninguna petición.
// - Envía los filtros vigentes de la lista (búsqueda, medio, quién registró y estado) con el rango en
//   UTC. La descarga va por api.blob: el CSV no se guarda en ninguna caché ni almacenamiento.
// - Errores del api dentro del modal: 403, 409 `export_in_progress`, 422 (rango o `export_too_large`),
//   429 y 503 `crypto_unavailable`, con su mensaje.
// DESIGN-GAP: el filtro "Retroactivos" de la lista no existe en la exportación (GET /payments/export no
// lo acepta): con él activo el botón queda deshabilitado y la nota lo explica, para que el CSV nunca
// traiga pagos que la lista no muestra.
import { useId, useState } from "react";
import { API_ERROR_CODES } from "../../../core/api/errorCodes";
import { ApiError } from "../../../core/api/errors";
import { HTTP_UNPROCESSABLE } from "../../../core/api/status";
import { useCan } from "../../../core/auth/useCan";
import { todayBogota } from "../../../core/i18n/format";
import { EXPORT_CONSEQUENCE, exportFallbackName, useBlobDownload } from "../../../shared/data/download";
import { Button } from "../../../shared/ui/Button";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { exportRangeError, paymentsExportRangeSchema, toPaymentsExportQuery, type PaymentsExportFilters } from "../exportSchema";
import styles from "./ExportButton.module.css";

export const EXPORT_TITLE = "¿Exportar los pagos?";
export const EXPORT_CONFIRM_LABEL = "Descargar CSV";
export const EXPORT_BLOCKED_NOTE = "La exportación no admite el filtro 'Retroactivos'. Quítalo para exportar.";
const RANGE_FIELD = "from";

export interface ExportButtonProps {
  /** Los días de "Fecha del pago" de la URL ("AAAA-MM-DD" o ""). */
  range: { from: string; to: string };
  filters: PaymentsExportFilters;
  /** Filtros de la lista que la exportación no puede aplicar (hoy, "Retroactivos"). */
  blocked?: boolean;
}

export function ExportButton({ range, filters, blocked = false }: ExportButtonProps) {
  const canExport = useCan("payments.export");
  const { download, blocked: waiting } = useBlobDownload();
  const [open, setOpen] = useState(false);
  const noteId = useId();
  if (!canExport) return null;

  const confirm = async (): Promise<void> => {
    const parsed = paymentsExportRangeSchema.safeParse(range);
    if (!parsed.success) {
      throw new ApiError({ status: HTTP_UNPROCESSABLE, code: API_ERROR_CODES.validationError, message: exportRangeError(range) ?? EXPORT_CONSEQUENCE, field: RANGE_FIELD });
    }
    await download({ path: "/payments/export", query: { ...toPaymentsExportQuery(parsed.data, filters) }, fallbackName: exportFallbackName("pagos", todayBogota()) });
  };

  return (
    <div className={styles.root}>
      {blocked ? (
        <p id={noteId} className={styles.note}>
          {EXPORT_BLOCKED_NOTE}
        </p>
      ) : null}
      <Button
        variant="secondary"
        disabled={blocked}
        {...(blocked ? { "aria-describedby": noteId } : {})}
        onClick={() => {
          setOpen(true);
        }}
      >
        Exportar
      </Button>
      <ConfirmModal
        open={open}
        title={EXPORT_TITLE}
        consequence={EXPORT_CONSEQUENCE}
        confirmLabel={EXPORT_CONFIRM_LABEL}
        tone="primary"
        confirmDisabled={waiting}
        onConfirm={confirm}
        onClose={() => {
          setOpen(false);
        }}
      />
    </div>
  );
}
