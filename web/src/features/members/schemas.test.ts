// S2-F6: reglas puras del alta de socios (MemberCreate de B7) y de la fila de la lista.
import { EMPTY_MEMBER_FORM, memberDetailSchema, memberFormSchema, memberRowSchema, toMemberCreate, type MemberFormValues } from "./schemas";

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
