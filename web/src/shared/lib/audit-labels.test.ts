// @vitest-environment node
// US-066 T1: etiquetas del historial y enmascarado. Nada de lo que sale de aquí contiene
// un blob cifrado ("apx1.").
import {
  ACTION_LABELS,
  ENCRYPTED_FIELDS,
  ENTITY_LABELS,
  PURPOSE_LABEL,
  SYSTEM_USER_ID,
  actionLabel,
  actorLabel,
  entityLabel,
  fieldNameLabel,
  maskValue,
  summarizeChange,
  type AuditEntryView,
} from "./audit-labels";

const BLOB_A = "apx1.k1.A256GCM.bm9uY2U.Y2lwaGVy";
const BLOB_B = "apx1.k1.A256GCM.b3Rybw.b3Rybw";

function entry(partial: Partial<AuditEntryView>): AuditEntryView {
  return {
    id: "e1",
    at: "2026-10-20T15:00:00Z",
    actor_id: "u1",
    actor_name: "Ana P.",
    entity: "members",
    action: "update",
    before: null,
    after: null,
    ...partial,
  };
}

describe("maskValue", () => {
  it.each([
    ["document", "CC •••• 4417"],
    ["phone", "310 ••• 221"],
    ["email", "laura@…"],
  ] as const)("devuelve el texto del api sin tocarlo (%s)", (kind, masked) => {
    expect(maskValue(kind, masked)).toBe(masked);
  });

  it.each([null, undefined, "", "   "])("sin valor da Sin dato (%j)", (masked) => {
    expect(maskValue("phone", masked)).toBe("Sin dato");
  });

  it("antepone el tipo de documento solo si el api no lo trae", () => {
    expect(maskValue("document", "•••• 4417", "CC")).toBe("CC •••• 4417");
    expect(maskValue("document", "CC •••• 4417", "CC")).toBe("CC •••• 4417");
    expect(maskValue("phone", "310 ••• 221", "CC")).toBe("310 ••• 221");
  });

  it("nunca devuelve un blob cifrado", () => {
    expect(maskValue("document", BLOB_A)).toBe("Sin dato");
  });
});

describe("etiquetas", () => {
  it("traduce las ocho acciones de N-08", () => {
    expect(ACTION_LABELS).toEqual({
      insert: "creó",
      update: "modificó",
      delete: "eliminó",
      reveal: "mostró",
      export: "exportó",
      download: "descargó",
      login: "inició sesión",
      verify: "verificó",
    });
    expect(actionLabel("reveal")).toBe("mostró");
    expect(actionLabel("rotate")).toBe("rotate");
  });

  it("traduce las entidades de la ficha del socio (N-31)", () => {
    expect(ENTITY_LABELS).toMatchObject({ members: "Socio", memberships: "Membresía", payments: "Pago" });
    expect(entityLabel("payments")).toBe("Pago");
    expect(entityLabel("classes")).toBe("classes");
  });

  it("los campos cifrados son los de v0.1", () => {
    expect([...ENCRYPTED_FIELDS].sort()).toEqual(["birth_date", "document", "email", "emergency_contact", "phone"]);
  });

  it("el usuario técnico se muestra como Sistema", () => {
    expect(SYSTEM_USER_ID).toBe("00000000-0000-0000-0000-000000000001");
    expect(actorLabel(entry({ actor_id: SYSTEM_USER_ID, actor_name: "system@apex.local" }))).toBe("Sistema");
    expect(actorLabel(entry({ actor_name: "Ana P." }))).toBe("Ana P.");
    expect(actorLabel(entry({ actor_name: null }))).toBe("Usuario");
  });
});

describe("summarizeChange", () => {
  it("un cambio de teléfono cifrado da 'dato cifrado modificado'", () => {
    const lines = summarizeChange(entry({ before: { phone: BLOB_A }, after: { phone: BLOB_B } }));

    expect(lines).toEqual(["Teléfono: dato cifrado modificado"]);
  });

  it("un cambio de nombres muestra la etiqueta y los valores en claro", () => {
    expect(summarizeChange(entry({ before: { first_name: "Ana" }, after: { first_name: "Ana María" } }))).toEqual([
      "Nombres: Ana → Ana María",
    ]);
  });

  it("omite los campos que no cambiaron y formatea dinero, booleanos y nulos", () => {
    const lines = summarizeChange(
      entry({
        entity: "payments",
        before: { amount_cop: 120000, voided: false, void_reason: null, method: "nequi" },
        after: { amount_cop: 120000, voided: true, void_reason: "Pago duplicado", method: "nequi" },
      }),
    );

    expect(lines).toEqual(["Anulado: no → sí", "Motivo de anulación: — → Pago duplicado"]);
  });

  it("dinero con formatCop", () => {
    expect(
      summarizeChange(entry({ entity: "memberships", before: { price_cop: 110000 }, after: { price_cop: 120000 } })),
    ).toEqual(["Precio: $ 110.000 → $ 120.000"]);
  });

  it("un campo desconocido usa su nombre y un valor que es blob nunca se muestra", () => {
    const lines = summarizeChange(entry({ before: { notes: "a", extra: BLOB_A }, after: { notes: "b", extra: BLOB_B } }));

    expect(lines).toEqual(["notes: a → b", "extra: dato cifrado modificado"]);
  });

  it("las columnas de índice ciego (_idx) nunca muestran el HMAC", () => {
    const lines = summarizeChange(entry({ before: { phone_idx: "a1b2c3" }, after: { phone_idx: "d4e5f6" } }));

    expect(lines).toEqual(["phone_idx: dato cifrado modificado"]);
    expect(summarizeChange(entry({ action: "insert", after: { document_idx: "a1b2" } }))).toEqual(["document_idx: dato cifrado"]);
  });

  it("un valor compuesto se resume sin volcarlo", () => {
    expect(summarizeChange(entry({ before: { tags: ["a"] }, after: { tags: ["a", "b"] } }))).toEqual(["tags: modificado"]);
  });

  it("insert lista los campos creados sin valores cifrados", () => {
    expect(summarizeChange(entry({ action: "insert", after: { first_name: "Laura", document: BLOB_A } }))).toEqual([
      "Nombres: Laura",
      "Documento: dato cifrado",
    ]);
  });

  it("reveal nombra el campo mostrado", () => {
    expect(summarizeChange(entry({ action: "reveal", after: { field: "document" } }))).toEqual(["Campo: Documento"]);
    expect(summarizeChange(entry({ action: "reveal", after: null }))).toEqual([]);
  });

  it("delete y una acción desconocida no lanzan", () => {
    expect(summarizeChange(entry({ action: "delete", before: { first_name: "Laura" } }))).toEqual([]);
    expect(() => summarizeChange(entry({ action: "rotate", after: { x: 1 } }))).not.toThrow();
  });

  it("ningún resumen contiene apx1.", () => {
    const all = [
      ...summarizeChange(entry({ before: { phone: BLOB_A, email: "x" }, after: { phone: BLOB_B, email: "y" } })),
      ...summarizeChange(entry({ action: "insert", after: { phone: BLOB_A, birth_date: BLOB_B } })),
    ];

    expect(all.join("\n")).not.toContain("apx1.");
    expect(all).toContain("Correo: dato cifrado modificado");
  });
});

describe("S4A-F2 · historial del socio (S4A-D32)", () => {
  it("ENTITY_LABELS tiene las tablas reales de GET /members/{id}/audit y conserva las viejas", () => {
    expect(ENTITY_LABELS).toMatchObject({
      "members.members": "Socio",
      "memberships.memberships": "Membresía",
      "payments.payments": "Pago",
      members: "Socio",
      memberships: "Membresía",
      payments: "Pago",
    });
    expect(entityLabel("memberships.memberships")).toBe("Membresía");
  });

  it("con fields y sin before ni after da una línea 'Cambió:' con las etiquetas, sin valores", () => {
    expect(summarizeChange(entry({ entity: "members.members", fields: ["phone", "email"] }))).toEqual(["Cambió: Teléfono, Correo"]);
  });

  it("un campo sin etiqueta usa su nombre y un fields vacío no da líneas", () => {
    expect(summarizeChange(entry({ fields: ["status", "notes"] }))).toEqual(["Cambió: Estado, notes"]);
    expect(summarizeChange(entry({ fields: [] }))).toEqual([]);
  });

  it("los campos de anulación y de auditoría tienen etiqueta (S4A-D109: sin void_reason ni reference)", () => {
    expect(summarizeChange(entry({ entity: "payments.payments", fields: ["voided", "voided_at", "voided_by"] }))).toEqual(["Cambió: Anulado, Fecha de anulación, Anulado por"]);
  });

  it("un reveal con fields nombra el campo mostrado", () => {
    expect(summarizeChange(entry({ action: "reveal", fields: ["document"] }))).toEqual(["Campo: Documento"]);
  });

  it("con before o after sigue el resumen de valores (fields no manda)", () => {
    expect(summarizeChange(entry({ before: { first_name: "Ana" }, after: { first_name: "Ana María" }, fields: ["first_name"] }))).toEqual(["Nombres: Ana → Ana María"]);
  });

  it("una columna de índice ciego en fields se nombra sin valor", () => {
    const lines = summarizeChange(entry({ fields: ["phone_idx"] }));

    expect(lines).toEqual(["Cambió: phone_idx"]);
    expect(lines.join("")).not.toContain("apx1.");
  });

  it("actorLabel acepta solo el id y el nombre", () => {
    expect(actorLabel({ actor_id: SYSTEM_USER_ID, actor_name: "Sistema" })).toBe("Sistema");
    expect(actorLabel({ actor_id: "u9", actor_name: "juan" })).toBe("juan");
  });

  it("PURPOSE_LABEL es la etiqueta de un reveal automático", () => {
    expect(PURPOSE_LABEL).toBe("automático (aviso)");
  });
});

describe("fieldNameLabel · revisión de seguridad S4A-F2 (LOW-2)", () => {
  it("un campo con etiqueta da la etiqueta y uno desconocido con forma de columna se nombra tal cual", () => {
    expect(fieldNameLabel("phone")).toBe("Teléfono");
    expect(fieldNameLabel("notes")).toBe("notes");
    expect(fieldNameLabel("phone_idx")).toBe("phone_idx");
  });

  it.each([
    ["<img src=x onerror=alert(1)>"],
    ["Teléfono"],
    ["phone; drop"],
    ["a".repeat(41)],
    [""],
    ["3001234567"],
    ["laura@correo.co"],
  ])("un nombre que no cumple ^[a-z_]{1,40}$ se dice 'campo' (%s)", (field) => {
    expect(fieldNameLabel(field)).toBe("campo");
  });

  it("un nombre con apx1. sigue siendo 'campo cifrado'", () => {
    expect(fieldNameLabel("apx1.k1.A256GCM.bm9uY2U.Y2lwaGVy")).toBe("campo cifrado");
  });

  it("el resumen con fields usa la misma regla", () => {
    expect(summarizeChange(entry({ fields: ["phone", "<b>x</b>"] }))).toEqual(["Cambió: Teléfono, campo"]);
  });
});
