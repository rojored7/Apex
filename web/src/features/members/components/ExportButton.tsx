// S5-F4 · US-138 (front): "Exportar" de /socios (Socios_Lista.html), solo admin (`members.export`).
// - Abre un ConfirmModal con el texto fijo de la exportación ("La descarga contiene datos personales y
//   queda registrada en la auditoría") y, al confirmar, pide GET /members/export con los filtros
//   vigentes de la URL (búsqueda, estado, estado de la membresía y plan; sin paginar ni ordenar).
// - La descarga va por api.blob: el CSV (con documento, teléfono y correo descifrados) no se guarda
//   en ninguna caché ni almacenamiento del navegador (L-8).
// - Errores dentro del modal, con el mensaje del api: 403, 409 `export_in_progress`, 422
//   `export_too_large` (acotar los filtros), 429 y 503 `crypto_unavailable`.
import { useState } from "react";
import { useCan } from "../../../core/auth/useCan";
import { todayBogota } from "../../../core/i18n/format";
import { EXPORT_CONSEQUENCE, exportFallbackName, useBlobDownload } from "../../../shared/data/download";
import { Button } from "../../../shared/ui/Button";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";

export const EXPORT_TITLE = "¿Exportar la lista de socios?";
export const EXPORT_CONFIRM_LABEL = "Descargar CSV";

export interface MembersExportFilters {
  q?: string;
  status?: string;
  membership_status?: string;
  plan_id?: string;
}

export interface ExportButtonProps {
  /** Los filtros vigentes de la lista; el orden y la paginación no viajan. */
  filters: MembersExportFilters;
}

export function ExportButton({ filters }: ExportButtonProps) {
  const canExport = useCan("members.export");
  const { download, blocked } = useBlobDownload();
  const [open, setOpen] = useState(false);
  if (!canExport) return null;

  return (
    <>
      <Button
        variant="secondary"
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
        confirmDisabled={blocked}
        onConfirm={() => download({ path: "/members/export", query: { ...filters }, fallbackName: exportFallbackName("socios", todayBogota()) })}
        onClose={() => {
          setOpen(false);
        }}
      />
    </>
  );
}
