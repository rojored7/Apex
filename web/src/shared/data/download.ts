// S5-F4 (L-8): descarga de un archivo del api (recibo PDF, exportaciones CSV) compartida por las
// features de pagos y socios. La descarga ocurre dentro de la mutación y no devuelve nada: el
// archivo (que puede traer datos personales) no pasa por la caché de TanStack Query ni por ningún
// almacenamiento. Pasa por useSensitiveMutation: no conserva variables ni resultado.
import { useEffect, useRef, useState } from "react";
import { api } from "../../core/api/client";
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import type { QueryParams } from "../../core/api/query";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import { saveDownload } from "../lib/download";
import { toDownloadError } from "../lib/downloadErrors";

/** S5-D41: lo que dice la confirmación de toda exportación con datos personales. */
export const EXPORT_CONSEQUENCE = "La descarga contiene datos personales y queda registrada en la auditoría.";

/** El nombre de respaldo `<prefijo>-AAAAMMDD.csv` con la fecha de hoy en Bogotá. */
export function exportFallbackName(prefix: string, today: string): string {
  return `${prefix}-${today.replaceAll("-", "")}.csv`;
}

export interface DownloadRequest {
  path: string;
  query?: QueryParams;
  /** Nombre si el api no propone uno en `Content-Disposition`. */
  fallbackName: string;
}

export interface BlobDownload {
  /** Descarga y entrega el archivo al navegador; rechaza con un ApiError en palabras de la pantalla. */
  download: (request: DownloadRequest) => Promise<void>;
  isPending: boolean;
  /** Revisión LOW 2: un 503 busy bloquea la acción durante el Retry-After; sin reintento automático. */
  blocked: boolean;
}

const MS_PER_S = 1_000;

/**
 * Una instancia por botón: dos descargas a la vez con la misma instancia comparten el estado de
 * espera. Para una lista de descargas, encolar las llamadas a `download` (mutateAsync), una a la vez.
 */
export function useBlobDownload(): BlobDownload {
  const controllers = useRef(new Set<AbortController>());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [blocked, setBlocked] = useState(false);

  // Revisión LOW 1: al salir de la pantalla la descarga se cancela y no se entrega nada.
  useEffect(() => {
    const pending = controllers.current;
    return () => {
      for (const controller of pending) controller.abort();
      pending.clear();
      if (timer.current !== null) clearTimeout(timer.current);
    };
  }, []);

  const block = (seconds: number): void => {
    if (timer.current !== null) clearTimeout(timer.current);
    setBlocked(true);
    timer.current = setTimeout(() => {
      setBlocked(false);
      timer.current = null;
    }, seconds * MS_PER_S);
  };

  const { mutateAsync, isPending } = useSensitiveMutation<undefined, Error, DownloadRequest>({
    mutationFn: async ({ path, query, fallbackName }) => {
      const controller = new AbortController();
      controllers.current.add(controller);
      try {
        const result = await api.blob(path, { ...(query ? { query } : {}), signal: controller.signal });
        if (!controller.signal.aborted) saveDownload(result, fallbackName);
        return undefined;
      } catch (error) {
        if (controller.signal.aborted) return undefined;
        const failure = toDownloadError(error);
        if (failure.retryAfterS !== undefined && failure.code === API_ERROR_CODES.busy) block(failure.retryAfterS);
        throw failure;
      } finally {
        controllers.current.delete(controller);
      }
    },
  });
  return { download: mutateAsync, isPending, blocked };
}
