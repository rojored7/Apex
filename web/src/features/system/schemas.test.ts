// S2-F5: esquemas de los formularios de configuración con los rangos del api (N-18) y el
// paso de un 422 con `field = "value.<campo>"` al campo del formulario.
import { ApiError } from "../../core/api/errors";
import { applyApiFieldError, gymSettingsSchema, membershipsSettingsSchema, privacySettingsSchema } from "./schemas";

const GYM = { name: "APEX", nit: "", address: "", city: "", phone: "", whatsapp: "", email: "" };
const PRIVACY = { policy_version: "2026-10", policy_text: "Autorizo el tratamiento.", retention_years: "5", consent_required_from: "" };
const MEMBERSHIPS = { expiring_days: "7", max_freeze_days_per_membership: "30", max_freezes_per_membership: "2", max_retroactive_days: "7" };

interface ParseLike {
  success: boolean;
  error?: { issues: { path: (string | number)[]; message: string }[] };
}

function firstMessage(result: ParseLike, field: string): string | undefined {
  return result.error?.issues.find((issue) => issue.path[0] === field)?.message;
}

const NIT_MESSAGE = "El NIT no es válido. Usa solo dígitos y, si tiene, un guion con el dígito de verificación: 901234567-8.";

describe("gymSettingsSchema", () => {
  it("acepta el nombre solo y recorta espacios", () => {
    const result = gymSettingsSchema.safeParse({ ...GYM, name: "  APEX CrossFit  " });

    expect(result.success && result.data.name).toBe("APEX CrossFit");
  });

  it.each([
    ["name", "", "Escribe el nombre del gimnasio."],
    ["name", "   ", "Escribe el nombre del gimnasio."],
    ["name", "x".repeat(81), "El nombre admite hasta 80 caracteres."],
    ["nit", "90123A", NIT_MESSAGE],
    ["nit", "901234567-89", NIT_MESSAGE],
    ["nit", "12345678901234-5", "El NIT admite hasta 15 caracteres."],
    ["address", "x".repeat(121), "La dirección admite hasta 120 caracteres."],
    ["city", "x".repeat(61), "La ciudad admite hasta 60 caracteres."],
    ["phone", "3".repeat(21), "El teléfono admite hasta 20 caracteres."],
    ["whatsapp", "3".repeat(21), "El WhatsApp admite hasta 20 caracteres."],
    ["email", "box@", "El correo no es válido. Escríbelo completo, por ejemplo box@ejemplo.com."],
  ])("rechaza %s = %j con un mensaje claro", (field, value, message) => {
    const result = gymSettingsSchema.safeParse({ ...GYM, [field]: value });

    expect(result.success).toBe(false);
    expect(firstMessage(result, field)).toBe(message);
  });

  it.each(["901234567-8", "901234567", "123456789012345"])("acepta el NIT %s", (nit) => {
    expect(gymSettingsSchema.safeParse({ ...GYM, nit }).success).toBe(true);
  });

  it("acepta los campos opcionales vacíos y un correo válido", () => {
    expect(gymSettingsSchema.safeParse({ ...GYM, email: "Box@Ejemplo.com" }).success).toBe(true);
    expect(gymSettingsSchema.safeParse(GYM).success).toBe(true);
  });
});

describe("privacySettingsSchema", () => {
  it("acepta una política completa", () => {
    expect(privacySettingsSchema.safeParse({ ...PRIVACY, consent_required_from: "2026-11-01" }).success).toBe(true);
  });

  it.each([
    ["policy_version", "", "Escribe la versión de la política, por ejemplo 2026-10."],
    ["policy_version", "v".repeat(21), "La versión admite hasta 20 caracteres."],
    ["policy_text", "  ", "Escribe o pega el texto de la política."],
    ["policy_text", "x".repeat(20_001), "El texto supera los 20.000 caracteres. Acórtalo antes de guardar."],
    ["retention_years", "0", "Escribe un número entre 1 y 20."],
    ["retention_years", "21", "Escribe un número entre 1 y 20."],
    ["retention_years", "5.5", "Escribe un número entero, sin decimales ni signos."],
    ["retention_years", "", "Escribe un número."],
    ["consent_required_from", "2026-02-30", "Escribe una fecha válida o deja el campo vacío."],
    ["consent_required_from", "el lunes", "Escribe una fecha válida o deja el campo vacío."],
  ])("rechaza %s = %j", (field, value, message) => {
    const result = privacySettingsSchema.safeParse({ ...PRIVACY, [field]: value });

    expect(result.success).toBe(false);
    expect(firstMessage(result, field)).toBe(message);
  });
});

describe("membershipsSettingsSchema", () => {
  it("acepta los valores por defecto", () => {
    expect(membershipsSettingsSchema.safeParse(MEMBERSHIPS).success).toBe(true);
  });

  it.each([
    ["expiring_days", "0", "Escribe un número entre 1 y 30."],
    ["expiring_days", "31", "Escribe un número entre 1 y 30."],
    ["expiring_days", "7.5", "Escribe un número entero, sin decimales ni signos."],
    ["expiring_days", "-1", "Escribe un número entero, sin decimales ni signos."],
    ["max_freeze_days_per_membership", "181", "Escribe un número entre 0 y 180."],
    ["max_freezes_per_membership", "13", "Escribe un número entre 0 y 12."],
    ["max_retroactive_days", "31", "Escribe un número entre 0 y 30."],
    ["max_retroactive_days", "", "Escribe un número."],
  ])("rechaza %s = %j", (field, value, message) => {
    const result = membershipsSettingsSchema.safeParse({ ...MEMBERSHIPS, [field]: value });

    expect(result.success).toBe(false);
    expect(firstMessage(result, field)).toBe(message);
  });

  it.each([
    ["expiring_days", "1"],
    ["expiring_days", "30"],
    ["max_freeze_days_per_membership", "0"],
    ["max_freezes_per_membership", "12"],
    ["max_retroactive_days", "0"],
  ])("acepta el borde %s = %s", (field, value) => {
    expect(membershipsSettingsSchema.safeParse({ ...MEMBERSHIPS, [field]: value }).success).toBe(true);
  });
});

describe("applyApiFieldError", () => {
  function fakeForm(values: Record<string, string>) {
    const setError = vi.fn();
    return { setError, getValues: () => values };
  }

  const invalid = (field?: string, status = 422) =>
    new ApiError({ status, code: "invalid_settings", message: `El campo ${field ?? "x"} no es válido.`, field });

  it("quita el prefijo value. y marca el campo con el mensaje del api", () => {
    const form = fakeForm({ email: "x" });

    expect(applyApiFieldError(form as never, invalid("value.email"))).toBe(true);
    expect(form.setError).toHaveBeenCalledWith("email", { type: "server", message: "El campo value.email no es válido." }, { shouldFocus: true });
  });

  it("usa el mensaje propio del campo cuando se le da", () => {
    const form = fakeForm({ name: "" });

    applyApiFieldError(form as never, invalid("value.name"), { name: "Revisa el nombre." });

    expect(form.setError).toHaveBeenCalledWith("name", { type: "server", message: "Revisa el nombre." }, { shouldFocus: true });
  });

  it("acepta un field sin prefijo", () => {
    const form = fakeForm({ nit: "" });

    expect(applyApiFieldError(form as never, invalid("nit"))).toBe(true);
  });

  it.each([
    ["un campo que el formulario no tiene", invalid("value.otro")],
    ["un 422 sin field", invalid(undefined)],
    ["un error que no es 422", invalid("value.name", 409)],
    ["algo que no es ApiError", new Error("x")],
  ])("no marca nada con %s", (_, error) => {
    const form = fakeForm({ name: "" });

    expect(applyApiFieldError(form as never, error)).toBe(false);
    expect(form.setError).not.toHaveBeenCalled();
  });
});
