// S6-F2 · US-146 (S6-D57, S6-B3): «Exportar CBOM» de /sistema/llaves, solo admin (la ruta ya lo exige).
// - GET /crypto/cbom por api.blob con `allow: ["application/json"]` solo para esta llamada (el CBOM es JSON,
//   S6-D120) y entrega con downloadBlob: nombre del api saneado (apex-cbom-AAAA-MM-DD.json) o, si no vino, el
//   de respaldo. La descarga ocurre dentro de una mutación (useBlobDownload): el archivo no pasa por la caché de
//   TanStack Query ni por ningún almacenamiento y el ObjectURL se revoca al terminar.
// - El CBOM no trae material ni referencias de llaves `sign` (L-5); aun así no se guarda ni se muestra aquí.
// - Errores junto al botón (role="alert"): 403, 429 con la espera, 503 busy (bloquea el botón) y crypto_unavailable.
import { useState } from "react";
import { todayBogota } from "../../../core/i18n/format";
import { useBlobDownload } from "../../../shared/data/download";
import { Button } from "../../../shared/ui/Button";
import styles from "./ExportCbomButton.module.css";

export const CBOM_LABEL = "Exportar CBOM";
const CBOM_TYPES = ["application/json"] as const;
const GENERIC_FAILURE = "No pudimos preparar el CBOM. Intenta de nuevo en un momento.";

/** El nombre de respaldo `apex-cbom-AAAA-MM-DD.json` con la fecha de hoy en Bogotá. */
export function cbomFallbackName(today: string): string {
  return `apex-cbom-${today}.json`;
}

export function ExportCbomButton() {
  const { download, isPending, blocked } = useBlobDownload();
  const [error, setError] = useState<string | null>(null);

  const run = async (): Promise<void> => {
    setError(null);
    try {
      await download({ path: "/crypto/cbom", fallbackName: cbomFallbackName(todayBogota()), allow: CBOM_TYPES });
    } catch (failure) {
      setError(failure instanceof Error && failure.message.trim() !== "" ? failure.message : GENERIC_FAILURE);
    }
  };

  return (
    <div className={styles.root}>
      <Button
        variant="secondary"
        loading={isPending}
        disabled={blocked}
        onClick={() => {
          void run();
        }}
      >
        {CBOM_LABEL}
      </Button>
      {error ? (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
