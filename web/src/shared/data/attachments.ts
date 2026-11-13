// S6-F4 (revisión LOW-2): lo que comparten las features de socios y de adjuntos del contrato
// AttachmentOut, en un solo lugar: los tipos de adjunto y la referencia mínima (id y tipo) que basta
// para confirmar una subida. No es estricta: el api puede sumar campos sin romper nada.
import { z } from "zod";

export const ATTACHMENT_KINDS = ["photo", "consent", "other"] as const;
export type AttachmentKind = (typeof ATTACHMENT_KINDS)[number];

export const attachmentRefSchema = z.object({ id: z.uuid(), kind: z.enum(ATTACHMENT_KINDS) });
export type AttachmentRef = z.infer<typeof attachmentRefSchema>;
