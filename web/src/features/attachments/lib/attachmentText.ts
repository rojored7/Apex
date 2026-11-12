// S6-F3 · US-150: textos de la tabla de adjuntos.
// - formatBytes: tamaño legible con base 1024 y coma decimal de Colombia ("220 KB", "1,5 MB").
// - kindLabel: el tipo del adjunto en palabras del gimnasio.
// - uploaderText: el nombre de quien subió si el contrato lo trae; si no, "Usuario" y el id corto.
import { EMPTY_VALUE } from "../../../core/i18n/format";
import type { AttachmentKind, AttachmentView } from "../schemas";

const KB = 1024;
const MB = KB * KB;
const SHORT_ID_LENGTH = 8;

function oneDecimal(value: number): string {
  return (Math.round(value * 10) / 10).toString().replace(".", ",");
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return EMPTY_VALUE;
  if (bytes < KB) return `${String(bytes)} B`;
  if (bytes < MB) {
    const kb = Math.round((bytes / KB) * 10) / 10;
    return `${oneDecimal(kb)} KB`;
  }
  return `${oneDecimal(bytes / MB)} MB`;
}

export const KIND_LABELS: Readonly<Record<AttachmentKind, string>> = { photo: "Foto de perfil", consent: "Autorización de datos", other: "Otro documento" };

export function kindLabel(kind: AttachmentKind): string {
  return KIND_LABELS[kind];
}

export function uploaderText(row: Pick<AttachmentView, "uploaded_by" | "uploaded_by_name">): string {
  const name = row.uploaded_by_name?.trim();
  return name ? name : `Usuario ${row.uploaded_by.slice(0, SHORT_ID_LENGTH)}`;
}
