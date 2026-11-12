// S6-F2 · US-145 (Llaves.html «Modal · Rotar DEK»; S6-R1, S6-D121, S6-D122): confirmación para rotar una llave
// de cifrado sobre ConfirmModal.
// - Dice la clase, la versión nueva y cuántos registros recifra el worker en segundo plano; la anterior queda en
//   «solo descifrar» y no hay corte de servicio.
// - Motivo obligatorio de 1 a 200 caracteres (el límite del contrato; el api rechaza correos y números largos y
//   el aviso lo dice) y el campo «Escribe ROTAR para confirmar»: confirmar sigue deshabilitado hasta el texto
//   exacto (ni «rotar» ni con espacios).
// - Al 202 salta a la pestaña Trabajos. 409 y 422 muestran el texto del api, 503 avisa del custodio y 429 la
//   espera, todo dentro del modal (rotateError). Nada del cuerpo queda en la caché de mutaciones.
// DESIGN-GAP: el diseño ofrece el motivo como lista (Rotación programada, Sospecha de exposición, Cambio de
// algoritmo); el api recibe texto libre de 1 a 200 caracteres (RotateIn.reason) y la CLI también (S6-D122):
// aquí es un campo de texto, como en el resto de los motivos del panel.
import { useSearchParams } from "react-router";
import { formatCount } from "../../../core/i18n/format";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { ROTATE_CONFIRM, useRotateKey } from "../api";
import type { CryptoKeyView } from "../schemas";

export const REASON_MAX = 200;
export const REASON_HINT = "No escribas correos, teléfonos ni documentos.";
export const JOBS_TAB = "trabajos";

function recordsText(count: number | null): string {
  if (count === null) return "los registros";
  return count === 1 ? "el único registro" : `los ${formatCount(count)} registros`;
}

export interface RotateKeyModalProps {
  /** La llave que se rotaría; null cierra el modal. */
  target: CryptoKeyView | null;
  onClose: () => void;
}

export function RotateKeyModal({ target, onClose }: RotateKeyModalProps) {
  const rotate = useRotateKey();
  const [, setSearchParams] = useSearchParams();

  const confirm = async (reason: string | undefined): Promise<void> => {
    if (!target) return;
    await rotate.mutateAsync({ keyId: target.id, reason: reason ?? "" });
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set("tab", JOBS_TAB);
      next.delete("offset");
      return next;
    });
  };

  return (
    <ConfirmModal
      open={target !== null}
      title={target ? `¿Rotar la llave de ${target.data_class}?` : ""}
      consequence={
        target
          ? `Se crea la versión v${String(target.version + 1)} y el worker recifra en segundo plano ${recordsText(target.records_count)} por lotes. Mientras tanto v${String(target.version)} queda en «solo descifrar». No hay corte de servicio.`
          : ""
      }
      confirmLabel="Rotar llave"
      tone="danger"
      reasonRequired
      showReason
      minReasonLength={1}
      maxReasonLength={REASON_MAX}
      reasonHint={REASON_HINT}
      confirmText={ROTATE_CONFIRM}
      onConfirm={confirm}
      onClose={onClose}
    />
  );
}
