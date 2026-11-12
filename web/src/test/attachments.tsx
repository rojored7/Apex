// S6-F3 · US-148 y US-150: datos y montaje de prueba de la pestaña Adjuntos y de la foto del socio.
// - Los adjuntos imitan AttachmentOut de GET /members/{id}/attachments (S6-C2): la foto de perfil
//   (JPEG, 220 KB), la autorización de datos firmada (PDF cifrado, 1,5 MB) y otro documento (PDF
//   cifrado, 5 MB), en el orden del api (`created_at` descendente).
// - fileReply imita GET /attachments/{id} (S6-C4): el archivo con `Content-Disposition:
//   attachment; filename=adjunto-<8 hex>.<ext>`.
// - renderAttachmentsTab monta la pestaña como hija de /socios/:id con un padre que le pasa el socio.
import type { components } from "../core/api/types";
import AttachmentsTab from "../features/attachments/pages/AttachmentsTab";
import { MEMBER_ID, pageOf, renderMemberTab, TAB_MEMBER } from "./memberTabs";
import type { MockHandler, RecordedCall } from "./server";
import type { MemberTabMember } from "../shared/data/members";

export { MEMBER_ID };

export type AttachmentFixture = components["schemas"]["AttachmentOut"];

export const ATTACHMENTS_PATH = `/members/${MEMBER_ID}/attachments`;
export const PHOTO_ID = "bbbb0001-0000-4000-8000-000000000001";
export const CONSENT_ID = "bbbb0002-0000-4000-8000-000000000002";
export const OTHER_ID = "bbbb0003-0000-4000-8000-000000000003";
export const UPLOADER_ID = "a0a0a0a0-0000-4000-8000-000000000001";

export function attachment(overrides: Partial<AttachmentFixture> = {}): AttachmentFixture {
  return {
    id: PHOTO_ID,
    owner_table: "members.members",
    owner_id: MEMBER_ID,
    kind: "photo",
    mime: "image/jpeg",
    size_bytes: 225_280,
    sensitive: false,
    uploaded_by: UPLOADER_ID,
    created_at: "2026-03-12T15:00:00Z",
    ...overrides,
  };
}

/** Foto, autorización firmada y otro documento, en el orden del api. */
export function attachments(): AttachmentFixture[] {
  return [
    attachment({ id: OTHER_ID, kind: "other", mime: "application/pdf", size_bytes: 5_242_880, sensitive: true, created_at: "2026-10-01T15:00:00Z" }),
    attachment({ id: CONSENT_ID, kind: "consent", mime: "application/pdf", size_bytes: 1_572_864, sensitive: true, created_at: "2026-03-12T16:00:00Z" }),
    attachment(),
  ];
}

export function fileReply(id: string, contentType: string, ext: string, content = "contenido"): MockHandler {
  return { status: 200, file: { content, contentType, filename: `adjunto-${id.slice(0, 8)}.${ext}` } };
}

export function attachmentsReply(items: readonly AttachmentFixture[], total = items.length): (call: RecordedCall) => ReturnType<typeof pageOf> {
  return (call) => pageOf(call, items, total);
}

export interface RenderAttachmentsOptions {
  handlers?: Record<string, MockHandler>;
  member?: MemberTabMember | null;
  entry?: string;
}

export function renderAttachmentsTab({ handlers = {}, member = TAB_MEMBER, entry = `/socios/${MEMBER_ID}/adjuntos` }: RenderAttachmentsOptions = {}) {
  return renderMemberTab(AttachmentsTab, "adjuntos", entry, {
    member,
    handlers: { [`GET ${ATTACHMENTS_PATH}`]: attachmentsReply(attachments()), ...handlers },
  });
}
