// S6-F3 · US-150: Zod de AttachmentOut (GET /members/{id}/attachments, S6-C2).
// - No es estricto: un campo nuevo del api no rompe la tabla. `uploaded_by_name` no existe todavía en el
//   contrato; si llega, la tabla lo prefiere al id corto de `uploaded_by`.
// - Nunca hay nombre de archivo ni contenido: el nombre de la descarga lo propone el api en
//   Content-Disposition (adjunto-<8 hex>.<ext>).
import { z } from "zod";
import { pageSchema } from "../../core/api/page";
import { ATTACHMENT_KINDS, attachmentRefSchema, type AttachmentKind } from "../../shared/data/attachments";

export { ATTACHMENT_KINDS, type AttachmentKind };

export const attachmentSchema = attachmentRefSchema.extend({
  owner_table: z.string(),
  owner_id: z.uuid(),
  // Un mime nuevo del api no debe tumbar la lista: la tabla no usa `mime`.
  mime: z.string(),
  size_bytes: z.number().int().nonnegative(),
  sensitive: z.boolean(),
  uploaded_by: z.uuid(),
  uploaded_by_name: z.string().nullish(),
  created_at: z.string(),
});
export type AttachmentView = z.infer<typeof attachmentSchema>;

export const attachmentsPageSchema = pageSchema(attachmentSchema);
