// S5-F4 (L-8): entrega un archivo descargado al navegador sin guardarlo en ningún sitio.
// - downloadBlob crea un ObjectURL, hace clic en un enlace temporal y, en `finally`, quita el
//   enlace del DOM y revoca el ObjectURL en el tick siguiente: el contenido (un recibo, un CSV con datos personales) no
//   queda en memoria, caché ni almacenamiento del navegador.
// - safeFilename sanea el nombre que propone el api: sin rutas, sin caracteres de control ni
//   separadores, con tope de largo; si no queda nada, usa el nombre de respaldo.
// - saveDownload usa el nombre del `Content-Disposition` si existe y, si no, el de respaldo.
import type { BlobResult } from "../../core/api/client";

const MAX_FILENAME_LENGTH = 100;
const UNSAFE = /[^A-Za-z0-9._-]+/g;

/** El último tramo del nombre, solo con letras, números, punto, guion y guion bajo. */
export function safeFilename(name: string | null | undefined, fallback: string): string {
  const last = (name ?? "").split(/[\\/]/).pop() ?? "";
  const cleaned = last.replace(UNSAFE, "_").replace(/^\.+/, "").slice(0, MAX_FILENAME_LENGTH);
  return /[A-Za-z0-9]/.test(cleaned) ? cleaned : fallback;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  link.hidden = true;
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
    // Revisión V10 (S5-D260): Safari y Firefox truncan la descarga si se revoca en el mismo tick del clic.
    setTimeout(() => {
      URL.revokeObjectURL(url);
    }, 0);
  }
}

/** Descarga `result` con el nombre del api (saneado) o, si no vino, con `fallbackName`. */
export function saveDownload(result: BlobResult, fallbackName: string): void {
  downloadBlob(result.blob, safeFilename(result.filename, fallbackName));
}
