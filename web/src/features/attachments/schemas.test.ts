// S6-F3 (revisión de seguridad LOW-2 y LOW-3): ids con forma de UUID y mime abierto.
import { attachment } from "../../test/attachments";
import { attachmentSchema } from "./schemas";

describe("attachmentSchema", () => {
  it("acepta el AttachmentOut del contrato", () => {
    expect(attachmentSchema.safeParse(attachment()).success).toBe(true);
  });

  it.each(["id", "owner_id", "uploaded_by"])("rechaza %s que no es un UUID", (field) => {
    expect(attachmentSchema.safeParse({ ...attachment(), [field]: "no-es-uuid" }).success).toBe(false);
  });

  it("rechaza un created_at que no es un instante ISO (revisión V11, LOW 7)", () => {
    expect(attachmentSchema.safeParse({ ...attachment(), created_at: "ayer" }).success).toBe(false);
    expect(attachmentSchema.safeParse({ ...attachment(), created_at: "2026-10-21" }).success).toBe(false);
  });

  it("un mime nuevo del api no tumba la fila", () => {
    expect(attachmentSchema.safeParse({ ...attachment(), mime: "image/webp" }).success).toBe(true);
  });
});
