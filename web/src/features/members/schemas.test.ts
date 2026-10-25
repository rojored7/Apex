// S2-F6: reglas puras del alta de socios (MemberCreate de B7) y de la fila de la lista.
// S3-F1: la ficha (MemberDetailOut), revelar (RevealOut) y la edición (MemberPatch, S3-D46).
import { MEMBER_ID, memberDetailBody, REVEALED } from "../../test/memberDetail";
import {
  chipFromFilters,
  chipToFilter,
  editDefaults,
  flattenRevealed,
  EMPTY_MEMBER_FORM,
  memberDetailSchema,
  memberDetailViewSchema,
  memberEditSchema,
  memberFormSchema,
  memberRowSchema,
  MEMBERSHIP_CHIP_LABELS,
  MEMBERSHIP_CHIPS,
  REVEAL_FIELDS,
  revealOutSchema,
  toMemberCreate,
  toMemberPatch,
  type MemberDetailView,
  type MemberEditValues,
  type MemberFormValues,
} from "./schemas";

const TODAY = "2026-10-22";

const valid = (overrides: Partial<MemberFormValues> = {}): MemberFormValues => ({
  ...EMPTY_MEMBER_FORM,
  first_name: "Laura",
  last_name: "Gómez",
  document: "1020304417",
  ...overrides,
});

/** Mensaje de la primera regla rota en `path`, o undefined. */
function issue(values: MemberFormValues, path: string): string | undefined {
  const result = memberFormSchema(TODAY).safeParse(values);
  if (result.success) return undefined;
  return result.error.issues.find((i) => i.path.join(".") === path)?.message;
}

describe("memberFormSchema", () => {
  it("acepta lo mínimo y recorta los espacios", () => {
    const result = memberFormSchema(TODAY).safeParse(valid({ first_name: "  Laura ", document: " 1020304417 " }));

    expect(result.success).toBe(true);
    expect(result.success && result.data.first_name).toBe("Laura");
    expect(result.success && result.data.document).toBe("1020304417");
  });

  it.each([
    ["first_name", "", "Escribe el nombre del socio."],
    ["first_name", "a".repeat(101), "El nombre admite hasta 100 caracteres."],
    ["last_name", " ", "Escribe el apellido del socio."],
    ["last_name", "a".repeat(101), "El apellido admite hasta 100 caracteres."],
    ["document", "", "Escribe el número de documento."],
    ["document", "ab", "El documento debe tener entre 3 y 30 caracteres."],
    ["document", "a".repeat(31), "El documento debe tener entre 3 y 30 caracteres."],
    ["phone", "123456", "El teléfono debe tener al menos 7 dígitos."],
    ["phone", `+57 ${"3".repeat(30)}`, "El teléfono admite hasta 30 caracteres."],
    ["email", "laura", "Escribe un correo válido, por ejemplo ana@correo.com."],
    ["email", `${"a".repeat(250)}@x.co`, "El correo admite hasta 254 caracteres."],
    ["birth_date", "2026-10-23", "La fecha de nacimiento no puede ser futura."],
    ["birth_date", "2026-02-30", "Escribe una fecha válida."],
    ["birth_date", "22/10/1990", "Escribe una fecha válida."],
  ] as const)("%s = %j: %s", (field, value, message) => {
    expect(issue(valid({ [field]: value }), field)).toBe(message);
  });

  it("un sexo o un tipo de documento fuera de la lista se rechazan", () => {
    const tampered = { ...valid(), sex: "z", document_type: "XX" } as unknown as MemberFormValues;

    expect(issue(tampered, "sex")).toBe("Elige una opción de la lista.");
    expect(issue(tampered, "document_type")).toBe("Elige el tipo de documento.");
  });

  it("revisión L3: el correo usa la misma forma que el api (acepta lo que el servidor acepta)", () => {
    expect(issue(valid({ email: "josé@correo.co" }), "email")).toBeUndefined();
    expect(issue(valid({ email: "ana@correo" }), "email")).toBe("Escribe un correo válido, por ejemplo ana@correo.com.");
    expect(issue(valid({ email: "ana @correo.co" }), "email")).toBe("Escribe un correo válido, por ejemplo ana@correo.com.");
  });

  it("hoy sí es una fecha de nacimiento válida", () => {
    expect(issue(valid({ birth_date: TODAY }), "birth_date")).toBeUndefined();
  });

  it("un teléfono de 7 dígitos con separadores es válido", () => {
    expect(issue(valid({ phone: "(1) 234-5678" }), "phone")).toBeUndefined();
  });

  it("el contacto de emergencia vacío no se valida", () => {
    expect(memberFormSchema(TODAY).safeParse(valid()).success).toBe(true);
  });

  it.each([
    [{ name: "Marta", phone: "", relationship: "" }, "emergency_contact.phone", "Escribe el teléfono del contacto de emergencia."],
    [{ name: "", phone: "3109876543", relationship: "" }, "emergency_contact.name", "Escribe el nombre del contacto de emergencia."],
    [{ name: "a".repeat(101), phone: "3109876543", relationship: "" }, "emergency_contact.name", "El nombre admite hasta 100 caracteres."],
    [{ name: "Marta", phone: "3".repeat(31), relationship: "" }, "emergency_contact.phone", "El teléfono admite hasta 30 caracteres."],
    [{ name: "Marta", phone: "3109876543", relationship: "a".repeat(51) }, "emergency_contact.relationship", "El parentesco admite hasta 50 caracteres."],
  ])("contacto de emergencia %j: %s", (emergency_contact, path, message) => {
    expect(issue(valid({ emergency_contact }), path)).toBe(message);
  });

  it("sin la fecha de hoy usa la de Bogotá", () => {
    expect(memberFormSchema().safeParse(valid({ birth_date: "2999-01-01" })).success).toBe(false);
  });
});

describe("toMemberCreate", () => {
  it("lo mínimo: sin opcionales vacíos y data_consent false", () => {
    expect(toMemberCreate(valid())).toEqual({ first_name: "Laura", last_name: "Gómez", document_type: "CC", document: "1020304417", data_consent: false });
  });

  it("todo lleno: el contacto de emergencia como objeto y data_consent true; nunca notes ni data_consent_at", () => {
    const body = toMemberCreate(
      valid({
        sex: "x",
        document_type: "PA",
        birth_date: "1991-04-17",
        phone: "3001234567",
        email: "laura@correo.co",
        emergency_contact: { name: "Marta", phone: "3109876543", relationship: "Madre" },
        data_consent: true,
      }),
    );

    expect(body).toEqual({
      first_name: "Laura",
      last_name: "Gómez",
      sex: "x",
      document_type: "PA",
      document: "1020304417",
      birth_date: "1991-04-17",
      phone: "3001234567",
      email: "laura@correo.co",
      emergency_contact: { name: "Marta", phone: "3109876543", relationship: "Madre" },
      data_consent: true,
    });
    expect(Object.keys(body)).not.toContain("notes");
    expect(Object.keys(body)).not.toContain("data_consent_at");
  });

  it("el contacto sin parentesco no envía relationship", () => {
    expect(toMemberCreate(valid({ emergency_contact: { name: "Marta", phone: "3109876543", relationship: "" } })).emergency_contact).toEqual({
      name: "Marta",
      phone: "3109876543",
    });
  });
});

describe("esquemas de respuesta", () => {
  it("memberRowSchema rechaza una fila con datos sensibles de más", () => {
    expect(
      memberRowSchema.safeParse({ id: "x", first_name: "A", last_name: "B", sex: null, status: "active", deleted_at: null, document: "CC •••• 1" }).success,
    ).toBe(false);
  });

  it("memberRowSchema acepta la fila sin membership_status, plan_name ni membership_end_date", () => {
    expect(memberRowSchema.parse({ id: "x", first_name: "A", last_name: "B", sex: null, status: "inactive", deleted_at: null })).toMatchObject({
      membership_status: null,
      plan_name: null,
      membership_end_date: null,
    });
  });

  it("S3-B9b (D35): memberRowSchema acepta la fila con membership_end_date y la de B9b completa", () => {
    const row = { id: "x", first_name: "A", last_name: "B", sex: "f", status: "active", deleted_at: null, membership_status: "expiring", plan_name: "Mensual", membership_end_date: "2026-10-25" };

    expect(memberRowSchema.parse(row)).toEqual(row);
    expect(memberRowSchema.parse({ ...row, membership_status: "none", plan_name: null, membership_end_date: null }).membership_end_date).toBeNull();
  });

  it("S3-B9b (D35): memberRowSchema sigue estricto con los campos nuevos", () => {
    const row = { id: "x", first_name: "A", last_name: "B", sex: null, status: "active", deleted_at: null, membership_end_date: "2026-10-25" };

    expect(memberRowSchema.safeParse({ ...row, plan_id: "p" }).success).toBe(false);
    expect(memberRowSchema.safeParse({ ...row, membership_end_date: 20261025 }).success).toBe(false);
  });

  it("memberDetailSchema exige warnings como lista de textos", () => {
    expect(memberDetailSchema.safeParse({ id: "x", first_name: "A", last_name: "B", warnings: "data_consent_missing" }).success).toBe(false);
    expect(memberDetailSchema.parse({ id: "x", first_name: "A", last_name: "B", warnings: [] })).toEqual({
      id: "x",
      first_name: "A",
      last_name: "B",
      warnings: [],
      plan_name: null,
      membership_end_date: null,
    });
  });

  it("S3-B9b (D35): memberDetailSchema acepta plan_name y membership_end_date de la ficha", () => {
    const detail = { id: "x", first_name: "A", last_name: "B", warnings: [], plan_name: "Mensual", membership_end_date: "2026-11-30" };

    expect(memberDetailSchema.parse(detail)).toEqual(detail);
    expect(memberDetailSchema.safeParse({ ...detail, plan_name: 7 }).success).toBe(false);
  });
});

describe("S3-F2 · chips de la lista (US-071)", () => {
  it("MEMBERSHIP_CHIPS son los siete de Socios_Lista.html en su orden, con su texto", () => {
    expect(MEMBERSHIP_CHIPS).toEqual(["active", "expiring", "expired", "frozen", "pending_payment", "none", "deleted"]);
    expect(MEMBERSHIP_CHIPS.map((chip) => MEMBERSHIP_CHIP_LABELS[chip])).toEqual([
      "Al día",
      "Por vencer",
      "Vencidos",
      "Congelados",
      "Pendiente de pago",
      "Sin membresía",
      "Dados de baja",
    ]);
  });

  it("chipToFilter: 'Dados de baja' es status=deleted y los otros seis, el membership_status del mismo nombre", () => {
    expect(chipToFilter("deleted")).toEqual({ status: "deleted" });
    for (const chip of ["active", "expiring", "expired", "frozen", "pending_payment", "none"] as const) {
      expect(chipToFilter(chip)).toEqual({ membership_status: chip });
    }
    expect(chipToFilter(null)).toEqual({});
  });

  it("chipFromFilters lee el chip de la URL; lo desconocido es 'Todos' y la baja manda sobre la membresía", () => {
    expect(chipFromFilters([], [])).toBeNull();
    expect(chipFromFilters(["deleted"], [])).toBe("deleted");
    expect(chipFromFilters([], ["expired"])).toBe("expired");
    expect(chipFromFilters([], ["none"])).toBe("none");
    expect(chipFromFilters(["deleted"], ["active"])).toBe("deleted");
    expect(chipFromFilters(["active"], ["cancelled"])).toBeNull();
    expect(chipFromFilters([], ["hack"])).toBeNull();
    expect(chipFromFilters([], ["deleted"])).toBeNull();
  });

  it("memberRowSchema sigue estricto con las nueve claves (las ocho de B8 más membership_end_date)", () => {
    const row = {
      id: "x",
      first_name: "A",
      last_name: "B",
      sex: "f",
      status: "active",
      deleted_at: null,
      membership_status: "active",
      plan_name: "Mensual",
      membership_end_date: "2026-11-27",
    };

    expect(Object.keys(memberRowSchema.parse(row))).toHaveLength(9);
    expect(memberRowSchema.safeParse({ ...row, document: "CC •••• 4417" }).success).toBe(false);
    expect(memberRowSchema.safeParse({ ...row, phone: "••• ••• 4567" }).success).toBe(false);
  });
});

// ---------------------------------------------------------------------------------------------
// S3-F1 · US-073 a US-076: ficha (MemberDetailOut), revelar (RevealOut) y edición (MemberPatch).
describe("S3-F1 · memberDetailViewSchema (GET /members/{id})", () => {
  it("lee la ficha enmascarada con el plan y el fin de la membresía", () => {
    const parsed = memberDetailViewSchema.parse(memberDetailBody());

    expect(parsed).toMatchObject({ id: MEMBER_ID, document: "CC •••• 4417", emergency_contact: "Registrado", plan_name: "Mensual", membership_end_date: "2026-10-28" });
  });

  it("descarta una clave que no está en el contrato (nunca llega a la pantalla)", () => {
    const parsed = memberDetailViewSchema.parse({ ...memberDetailBody(), document_plain: "1020304417" });

    expect(JSON.stringify(parsed)).not.toContain("1020304417");
  });

  it("sin plan ni fin (opcionales en el contrato) quedan en null; sin warnings o con un sexo desconocido es inválida", () => {
    const without = (keys: readonly string[]) => Object.fromEntries(Object.entries(memberDetailBody()).filter(([key]) => !keys.includes(key)));
    const rest = without(["plan_name", "membership_end_date", "membership_status"]);

    expect(memberDetailViewSchema.parse(rest)).toMatchObject({ plan_name: null, membership_end_date: null, membership_status: null });
    const withoutWarnings = without(["warnings"]);
    expect(memberDetailViewSchema.safeParse(withoutWarnings).success).toBe(false);
    expect(memberDetailViewSchema.safeParse({ ...memberDetailBody(), sex: "z" }).success).toBe(false);
  });
});

describe("S3-F1 · revealOutSchema y flattenRevealed (POST /members/{id}/reveal)", () => {
  it("acepta texto, el contacto como objeto o null, cada uno en su campo", () => {
    expect(revealOutSchema.safeParse({ field: "document", value: "1020304417" }).success).toBe(true);
    expect(revealOutSchema.safeParse({ field: "emergency_contact", value: REVEALED.emergency_contact }).success).toBe(true);
    expect(revealOutSchema.safeParse({ field: "email", value: null }).success).toBe(true);
  });

  it("rechaza una clave de más, un campo desconocido y un valor que no corresponde al campo", () => {
    expect(revealOutSchema.safeParse({ field: "document", value: "1", extra: 1 }).success).toBe(false);
    expect(revealOutSchema.safeParse({ field: "notes", value: "x" }).success).toBe(false);
    expect(revealOutSchema.safeParse({ field: "document", value: REVEALED.emergency_contact }).success).toBe(false);
    expect(revealOutSchema.safeParse({ field: "emergency_contact", value: "Marta" }).success).toBe(false);
    expect(revealOutSchema.safeParse({ field: "emergency_contact", value: { name: "M", phone: "1", extra: "x" } }).success).toBe(false);
  });

  it("aplana el valor para la pantalla: el contacto como 'Nombre · Parentesco · Teléfono' y la fecha con formatDate", () => {
    expect(REVEAL_FIELDS).toEqual(["document", "phone", "email", "birth_date", "emergency_contact"]);
    expect(flattenRevealed("document", "1020304417")).toBe("1020304417");
    expect(flattenRevealed("phone", "3001234567")).toBe("3001234567");
    expect(flattenRevealed("birth_date", "1991-03-12")).toBe("12 mar 1991");
    expect(flattenRevealed("emergency_contact", REVEALED.emergency_contact)).toBe("Marta Gómez · Madre · 3110000008");
    expect(flattenRevealed("emergency_contact", { name: "Marta Gómez", phone: "3110000008", relationship: null })).toBe("Marta Gómez · 3110000008");
    expect(flattenRevealed("email", null)).toBe("Sin dato");
  });
});

const memberDetailView = (): MemberDetailView => memberDetailViewSchema.parse(memberDetailBody());
const editValues = (overrides: Partial<MemberEditValues> = {}): MemberEditValues => ({ ...editDefaults(memberDetailView()), ...overrides });
const withModes = (modes: Partial<MemberEditValues["modes"]>, overrides: Partial<MemberEditValues> = {}): MemberEditValues => {
  const base = editValues(overrides);
  return { ...base, modes: { ...base.modes, ...modes } };
};

function editIssue(values: MemberEditValues, path: string): string | undefined {
  const result = memberEditSchema(TODAY).safeParse(values);
  if (result.success) return undefined;
  return result.error.issues.find((i) => i.path.join(".") === path)?.message;
}

describe("S3-F1 · editDefaults y memberEditSchema (US-075)", () => {
  it("precarga lo no sensible; los cinco sensibles empiezan vacíos y sin cambio, y la autorización sin marcar", () => {
    expect(editDefaults(memberDetailView())).toEqual({
      first_name: "Laura",
      last_name: "Gómez",
      sex: "f",
      document_type: "CC",
      document: "",
      birth_date: "",
      phone: "",
      email: "",
      emergency_contact: { name: "", phone: "", relationship: "" },
      data_consent: false,
      modes: { document: "keep", phone: "keep", email: "keep", birth_date: "keep", emergency_contact: "keep" },
    });
    expect(JSON.stringify(editDefaults(memberDetailView()))).not.toContain("•");
  });

  it("los valores iniciales pasan; nombres y apellidos siguen siendo obligatorios", () => {
    expect(memberEditSchema(TODAY).safeParse(editValues()).success).toBe(true);
    expect(editIssue(editValues({ first_name: " " }), "first_name")).toBe("Escribe el nombre del socio.");
    expect(editIssue(editValues({ last_name: "" }), "last_name")).toBe("Escribe el apellido del socio.");
  });

  it("un campo sensible sin cambio no se valida, aunque tenga cualquier cosa", () => {
    expect(memberEditSchema(TODAY).safeParse(editValues({ phone: "x", email: "y", document: "z", birth_date: "w" })).success).toBe(true);
  });

  it("al cambiar un sensible hay que escribir el valor nuevo, con las reglas del alta", () => {
    expect(editIssue(withModes({ phone: "change" }), "phone")).toBe("Escribe el nuevo teléfono o cancela el cambio.");
    expect(editIssue(withModes({ phone: "change" }, { phone: "123" }), "phone")).toBe("El teléfono debe tener al menos 7 dígitos.");
    expect(editIssue(withModes({ email: "change" }), "email")).toBe("Escribe el nuevo correo o cancela el cambio.");
    expect(editIssue(withModes({ email: "change" }, { email: "laura" }), "email")).toBe("Escribe un correo válido, por ejemplo ana@correo.com.");
    expect(editIssue(withModes({ document: "change" }), "document")).toBe("Escribe el nuevo número de documento o cancela el cambio.");
    expect(editIssue(withModes({ document: "change" }, { document: "12" }), "document")).toBe("El documento debe tener entre 3 y 30 caracteres.");
    expect(editIssue(withModes({ birth_date: "change" }), "birth_date")).toBe("Escribe la nueva fecha de nacimiento o cancela el cambio.");
    expect(editIssue(withModes({ birth_date: "change" }, { birth_date: "2026-10-23" }), "birth_date")).toBe("La fecha de nacimiento no puede ser futura.");
    expect(editIssue(withModes({ birth_date: "change" }, { birth_date: "2026-02-30" }), "birth_date")).toBe("Escribe una fecha válida.");
    expect(editIssue(withModes({ emergency_contact: "change" }, { emergency_contact: { name: "Marta", phone: "", relationship: "" } }), "emergency_contact.phone")).toBe(
      "Escribe el teléfono del contacto de emergencia.",
    );
    expect(editIssue(withModes({ emergency_contact: "change" }), "emergency_contact.name")).toBe("Escribe el nombre del contacto de emergencia.");
    expect(memberEditSchema(TODAY).safeParse(withModes({ phone: "change", email: "remove" }, { phone: "300 123 4567" })).success).toBe(true);
  });
});

describe("S3-F1 · toMemberPatch (solo lo modificado, S3-D46)", () => {
  it("sin cambios el cuerpo es vacío", () => {
    expect(toMemberPatch(editValues(), {})).toEqual({});
  });

  it("los no sensibles viajan solo si están sucios; el sexo vacío es null", () => {
    expect(toMemberPatch(editValues({ first_name: " Laurita ", last_name: "Gómez" }), { first_name: true })).toEqual({ first_name: "Laurita" });
    expect(toMemberPatch(editValues({ sex: "" }), { sex: true })).toEqual({ sex: null });
    expect(toMemberPatch(editValues({ document_type: "CE" }), { document_type: true })).toEqual({ document_type: "CE" });
  });

  it("un sensible con 'Cambiar' lleva el valor nuevo; con 'Quitar', null; sin cambio no viaja aunque el campo esté sucio", () => {
    const values = withModes(
      { phone: "change", email: "remove", birth_date: "remove", emergency_contact: "remove", document: "change" },
      { phone: " 300 123 4567 ", email: "viejo@correo.co", document: "1020304418" },
    );

    expect(toMemberPatch(values, {})).toEqual({ phone: "300 123 4567", email: null, birth_date: null, emergency_contact: null, document: "1020304418" });
    expect(toMemberPatch(editValues({ phone: "3001234567" }), { phone: true })).toEqual({});
  });

  it("el contacto nuevo lleva nombre y teléfono, y el parentesco solo si se escribió", () => {
    const contact = (relationship: string) => withModes({ emergency_contact: "change" }, { emergency_contact: { name: "Marta", phone: "3110000008", relationship } });

    expect(toMemberPatch(contact("Madre"), {})).toEqual({ emergency_contact: { name: "Marta", phone: "3110000008", relationship: "Madre" } });
    expect(toMemberPatch(contact(""), {})).toEqual({ emergency_contact: { name: "Marta", phone: "3110000008" } });
  });

  it("el documento nunca se quita (null da 422) y la autorización solo viaja como true (retirarla es otro proceso)", () => {
    expect(toMemberPatch(withModes({ document: "remove" }), {})).toEqual({});
    expect(toMemberPatch(editValues({ data_consent: true }), { data_consent: true })).toEqual({ data_consent: true });
    expect(toMemberPatch(editValues({ data_consent: false }), { data_consent: true })).toEqual({});
  });

  it("nunca envía estado, baja ni fecha de autorización", () => {
    const body = toMemberPatch(withModes({ phone: "change" }, { phone: "3001234567", data_consent: true, first_name: "Ana" }), { first_name: true, data_consent: true });

    expect(Object.keys(body).sort()).toEqual(["data_consent", "first_name", "phone"]);
  });
});

describe("S3-F1 · memberEditSchema con valores demasiado largos (topes de MemberPatch)", () => {
  it("aplica los topes del alta a lo que se cambia", () => {
    const long = (n: number) => "1".repeat(n);
    expect(editIssue(withModes({ phone: "change" }, { phone: long(31) }), "phone")).toBe("El teléfono admite hasta 30 caracteres.");
    expect(editIssue(withModes({ email: "change" }, { email: `${"a".repeat(250)}@correo.co` }), "email")).toBe("El correo admite hasta 254 caracteres.");
    const contact = (name: string, phone: string, relationship: string) => withModes({ emergency_contact: "change" }, { emergency_contact: { name, phone, relationship } });
    expect(editIssue(contact("a".repeat(101), "3110000008", ""), "emergency_contact.name")).toBe("El nombre admite hasta 100 caracteres.");
    expect(editIssue(contact("Marta", long(31), ""), "emergency_contact.phone")).toBe("El teléfono admite hasta 30 caracteres.");
    expect(editIssue(contact("Marta", "3110000008", "a".repeat(51)), "emergency_contact.relationship")).toBe("El parentesco admite hasta 50 caracteres.");
  });
});
