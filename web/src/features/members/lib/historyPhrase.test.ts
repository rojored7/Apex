// S4A-F2 · US-106 (front), S4A-D32: frases del historial por acción y tabla, con el nombre de quien
// actuó ("Sistema" para el usuario técnico) y sin valores; y el paso de MemberHistoryItem a la
// AuditEntryView de HistoryAside (historyEntries).
import { entityLabel } from "../../../shared/lib/audit-labels";
import { DOCUMENT_VALUE, historyItem, PHONE_VALUE, SYSTEM_USER_ID } from "../../../test/history";
import { toAuditEntryView } from "./historyEntries";
import { historyPhrase } from "./historyPhrase";

const SYSTEM = { user_id: SYSTEM_USER_ID, user_name: "Sistema" } as const;

describe("historyPhrase · socio (members.members)", () => {
  it.each([
    [["phone", "email"], "ana editó teléfono y correo"],
    [["phone"], "ana editó teléfono"],
    [["first_name", "phone", "email"], "ana editó nombres, teléfono y correo"],
    [["deleted_at", "status"], "ana editó fecha de baja y estado"],
    [[], "ana editó la ficha"],
  ] as const)("update con %j da %s", (fields, phrase) => {
    expect(historyPhrase(historyItem({ fields: [...fields] }))).toBe(phrase);
  });

  it("insert da 'creó el socio' y delete 'eliminó al socio'", () => {
    expect(historyPhrase(historyItem({ action: "insert" }))).toBe("ana creó el socio");
    expect(historyPhrase(historyItem({ action: "delete" }))).toBe("ana eliminó al socio");
  });

  it.each([
    ["document", "juan mostró el documento"],
    ["phone", "juan mostró el teléfono"],
    ["email", "juan mostró el correo"],
    ["birth_date", "juan mostró la fecha de nacimiento"],
    ["emergency_contact", "juan mostró el contacto de emergencia"],
  ] as const)("reveal de %s", (field, phrase) => {
    expect(historyPhrase(historyItem({ user_name: "juan", action: "reveal", fields: [field] }))).toBe(phrase);
  });

  it("reveal sin campo conocido dice 'mostró un dato'", () => {
    expect(historyPhrase(historyItem({ action: "reveal", fields: [] }))).toBe("ana mostró un dato");
    expect(historyPhrase(historyItem({ action: "reveal", fields: ["notes"] }))).toBe("ana mostró un dato");
  });

  it("un reveal automático del sistema nombra a Sistema", () => {
    expect(historyPhrase(historyItem({ ...SYSTEM, action: "reveal", fields: ["phone"], purpose: "notify" }))).toBe("Sistema mostró el teléfono");
  });
});

describe("historyPhrase · membresía y pago", () => {
  it("vendió una membresía", () => {
    expect(historyPhrase(historyItem({ action: "insert", table_name: "memberships.memberships" }))).toBe("ana vendió una membresía");
  });

  it("Sistema marcó la membresía como vencida (el job de vencimientos solo cambia el estado)", () => {
    expect(historyPhrase(historyItem({ ...SYSTEM, table_name: "memberships.memberships", fields: ["status"] }))).toBe("Sistema marcó la membresía como vencida o por vencer");
  });

  it("anular una membresía y otros cambios de membresía", () => {
    expect(historyPhrase(historyItem({ table_name: "memberships.memberships", fields: ["cancel_reason", "cancelled_at", "cancelled_by", "status"] }))).toBe("ana anuló una membresía");
    expect(historyPhrase(historyItem({ table_name: "memberships.memberships", fields: ["end_date", "status"] }))).toBe("ana modificó una membresía: vence y estado");
    expect(historyPhrase(historyItem({ table_name: "memberships.memberships", fields: ["status"] }))).toBe("ana modificó una membresía: estado");
  });

  it("registró un pago y anuló un pago (S4A-D109: la anulación es voided, voided_at y voided_by)", () => {
    expect(historyPhrase(historyItem({ action: "insert", table_name: "payments.payments" }))).toBe("ana registró un pago");
    expect(historyPhrase(historyItem({ table_name: "payments.payments", fields: ["voided", "voided_at", "voided_by"] }))).toBe("ana anuló un pago");
    expect(historyPhrase(historyItem({ table_name: "payments.payments", fields: ["method"] }))).toBe("ana modificó un pago: medio de pago");
  });
});

describe("historyPhrase · quién y casos raros", () => {
  it("el usuario técnico es Sistema aunque el nombre venga distinto; sin nombre, 'Usuario'", () => {
    expect(historyPhrase(historyItem({ user_id: SYSTEM_USER_ID, user_name: "system", action: "insert" }))).toBe("Sistema creó el socio");
    expect(historyPhrase(historyItem({ user_name: null, action: "insert" }))).toBe("Usuario creó el socio");
    expect(historyPhrase(historyItem({ user_name: "  ", action: "insert" }))).toBe("Usuario creó el socio");
  });

  it("una tabla o acción desconocida da una frase genérica sin lanzar", () => {
    expect(historyPhrase(historyItem({ action: "export", table_name: "members.members" }))).toBe("ana exportó (Socio)");
    expect(historyPhrase(historyItem({ action: "insert", table_name: "classes.sessions" }))).toBe("ana creó (classes.sessions)");
  });

  it("ninguna frase contiene un valor", () => {
    const phrases = [historyPhrase(historyItem({ fields: ["phone", "document"] })), historyPhrase(historyItem({ action: "reveal", fields: ["document"] }))].join(" ");

    expect(phrases).not.toContain(PHONE_VALUE);
    expect(phrases).not.toContain(DOCUMENT_VALUE);
    expect(phrases).not.toContain("apx1.");
  });
});

describe("toAuditEntryView (historyEntries)", () => {
  it("mapea seq, fecha, usuario, tabla completa, acción, fields, propósito y la frase", () => {
    const item = historyItem({ seq: 13, user_name: "ana", fields: ["email", "phone"], purpose: null });

    expect(toAuditEntryView(item)).toEqual({
      id: "13",
      at: "2026-10-20T15:00:00Z",
      actor_id: item.user_id,
      actor_name: "ana",
      entity: "members.members",
      action: "update",
      fields: ["email", "phone"],
      purpose: null,
      phrase: "ana editó correo y teléfono",
    });
  });

  it("conserva el propósito de un reveal automático y no inventa before ni after", () => {
    const view = toAuditEntryView(historyItem({ ...SYSTEM, action: "reveal", fields: ["phone"], purpose: "notify" }));

    expect(view.purpose).toBe("notify");
    expect(view.actor_name).toBe("Sistema");
    expect(view).not.toHaveProperty("before");
    expect(view).not.toHaveProperty("after");
  });

  it("no comparte el arreglo fields con la entrada (sin mutación)", () => {
    const item = historyItem({ fields: ["phone"] });
    const view = toAuditEntryView(item);

    expect(view.fields).toEqual(["phone"]);
    expect(view.fields).not.toBe(item.fields);
  });
});

// S7-F5 · E5 (S7-D17): el check-in y quitar una asistencia llegan como filas de `classes.attendance` con `subject_member_id`
// y solo nombres de campo (el motivo de quitar es texto libre y nunca viaja).
describe("historyPhrase · asistencia (classes.attendance)", () => {
  it("el check-in (insert) dice 'registró una asistencia'", () => {
    expect(historyPhrase(historyItem({ action: "insert", table_name: "classes.attendance" }))).toBe("ana registró una asistencia");
  });

  it("quitarla (update de borrado lógico) dice 'quitó una asistencia', con o sin campos", () => {
    expect(historyPhrase(historyItem({ table_name: "classes.attendance", fields: ["removed_at", "removed_by", "removed_reason"] }))).toBe("ana quitó una asistencia");
    expect(historyPhrase(historyItem({ table_name: "classes.attendance", fields: [] }))).toBe("ana quitó una asistencia");
  });

  it("nunca incluye valores: ni el motivo ni nombres de campo", () => {
    const phrase = historyPhrase(historyItem({ table_name: "classes.attendance", fields: ["removed_reason"] }));
    expect(phrase).not.toContain("removed");
    expect(phrase).not.toContain("motivo");
  });

  it("la entidad se llama 'Asistencia' en la entrada del historial", () => {
    const entry = toAuditEntryView(historyItem({ action: "insert", table_name: "classes.attendance" }));
    expect(entityLabel(entry.entity)).toBe("Asistencia");
  });

  it("el sistema (o un usuario sin nombre) no cambia la frase", () => {
    expect(historyPhrase(historyItem({ ...SYSTEM, action: "insert", table_name: "classes.attendance" }))).toBe("Sistema registró una asistencia");
  });
});

// S9-V8: las filas de `athletes.body_metrics`, `athletes.personal_records` y `results.wod_results` llegan al historial del socio
// con `subject_member_id` y solo nombres de campo; sin frase propia salían como «<acción> (<esquema.tabla>)».
describe("historyPhrase · atleta y resultados (S9-V8)", () => {
  const BM = "athletes.body_metrics";
  const PR = "athletes.personal_records";
  const WR = "results.wod_results";

  it("medidas: registrar, anular y mostrar cada campo", () => {
    expect(historyPhrase(historyItem({ action: "insert", table_name: BM }))).toBe("ana registró una medición");
    expect(historyPhrase(historyItem({ table_name: BM, fields: ["voided_at", "voided_by"] }))).toBe("ana anuló una medición");
    expect(historyPhrase(historyItem({ action: "reveal", table_name: BM, fields: ["weight_g"] }))).toBe("ana mostró el peso");
    expect(historyPhrase(historyItem({ action: "reveal", table_name: BM, fields: ["height_cm"] }))).toBe("ana mostró la altura");
    expect(historyPhrase(historyItem({ action: "reveal", table_name: BM, fields: ["body_fat_pct"] }))).toBe("ana mostró el % de grasa");
    expect(historyPhrase(historyItem({ action: "reveal", table_name: BM, fields: ["notes"] }))).toBe("ana mostró las notas de una medición");
  });

  it("récords: registrar e invalidar (a mano o por el resultado)", () => {
    expect(historyPhrase(historyItem({ action: "insert", table_name: PR }))).toBe("ana registró un récord");
    expect(historyPhrase(historyItem({ table_name: PR, fields: ["invalidated_at", "invalidated_by", "invalidated_reason"] }))).toBe("ana invalidó un récord");
    expect(historyPhrase(historyItem({ ...SYSTEM, action: "insert", table_name: PR }))).toBe("Sistema registró un récord");
  });

  it("resultados: registrar, corregir y anular", () => {
    expect(historyPhrase(historyItem({ action: "insert", table_name: WR }))).toBe("ana registró un resultado");
    expect(historyPhrase(historyItem({ table_name: WR, fields: ["is_current"] }))).toBe("ana corrigió un resultado");
    expect(historyPhrase(historyItem({ table_name: WR, fields: ["is_current", "status", "voided_at", "voided_by", "void_reason"] }))).toBe("ana anuló un resultado");
  });

  it("las entidades tienen nombre en el historial", () => {
    expect(entityLabel(BM)).toBe("Medición");
    expect(entityLabel(PR)).toBe("Récord");
    expect(entityLabel(WR)).toBe("Resultado");
  });

  it("nunca incluye valores ni nombres de campo técnicos", () => {
    for (const fields of [["voided_at"], ["invalidated_reason"], ["void_reason", "status"]]) {
      for (const table_name of [BM, PR, WR]) {
        const phrase = historyPhrase(historyItem({ table_name, fields }));
        expect(phrase).not.toMatch(/voided|invalidated|reason|_/);
      }
    }
  });
});
