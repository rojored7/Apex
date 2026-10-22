// S2-F6: traducción de los errores del api de socios a la pantalla.
import { ApiError } from "../../core/api/errors";
import { createErrorMessage, fieldErrorOf, listError, waitText } from "./memberErrors";

const error = (status: number, code: string, extra: Partial<ConstructorParameters<typeof ApiError>[0]> = {}) => new ApiError({ status, code, message: "Mensaje del api.", ...extra });

describe("fieldErrorOf", () => {
  it("un error que no es del api no va a ningún campo", () => {
    expect(fieldErrorOf(new Error("x"))).toBeNull();
  });

  it("el 409 por campo document, aunque el código cambie, va al documento con el socio existente", () => {
    expect(fieldErrorOf(error(409, "conflict", { field: "document", existingId: "abc" }))).toEqual({
      path: "document",
      message: "Ya existe un socio con este documento.",
      existingId: "abc",
    });
  });

  it("otro 409 no es de campo", () => {
    expect(fieldErrorOf(error(409, "version_conflict"))).toBeNull();
  });

  it("un 422 sin campo no es de campo", () => {
    expect(fieldErrorOf(error(422, "validation_error"))).toBeNull();
  });

  it.each([
    ["first_name", "first_name", "Escribe el nombre del socio."],
    ["last_name", "last_name", "Escribe el apellido del socio."],
    ["sex", "sex", "Elige una opción de la lista."],
    ["document_type", "document_type", "Elige el tipo de documento."],
    ["emergency_contact.relationship", "emergency_contact.relationship", "Revisa este dato e intenta de nuevo."],
  ])("el 422 de %s va a %s", (field, path, message) => {
    expect(fieldErrorOf(error(422, "validation_error", { field }))).toEqual({ path, message, existingId: null });
  });
});

describe("waitText", () => {
  it.each([
    [undefined, "un momento"],
    [0, "un momento"],
    [1, "1 segundo"],
    [45, "45 segundos"],
  ])("%s → %s", (seconds, text) => {
    expect(waitText(seconds)).toBe(text);
  });
});

describe("createErrorMessage", () => {
  it.each([
    [new Error("x"), "No pudimos registrar el socio. Revisa los datos e intenta de nuevo."],
    [error(0, "timeout"), "El servidor tardó demasiado en responder. Intenta de nuevo."],
    [error(0, "network_error"), "No pudimos conectar con el servidor. Intenta de nuevo."],
    [error(429, "rate_limited", { retryAfterS: 1 }), "Registraste muchos socios seguidos. Espera 1 segundo e intenta de nuevo."],
    [error(503, "unavailable"), "No pudimos registrar el socio. Intenta de nuevo en un momento."],
  ])("%s", (value, message) => {
    expect(createErrorMessage(value)).toBe(message);
  });
});

describe("listError", () => {
  it("sin error no hay nada que mostrar", () => {
    expect(listError(null)).toBeNull();
  });

  it("un error que no es del api se explica como fallo de carga", () => {
    expect(listError(new Error("x"))?.message).toBe("No pudimos cargar los socios. Intenta de nuevo en un momento.");
  });

  it.each([
    [error(0, "timeout"), "El servidor tardó demasiado en responder. Intenta de nuevo."],
    [error(429, "rate_limited"), "Hiciste muchas búsquedas seguidas. Espera un momento e intenta de nuevo."],
    [error(404, "not_found"), "No pudimos cargar los socios. Intenta de nuevo en un momento."],
  ])("%s", (value, message) => {
    expect(listError(value)?.message).toBe(message);
  });

  it("conserva el estado y el código del error original", () => {
    expect(listError(error(403, "forbidden"))).toMatchObject({ status: 403, code: "forbidden" });
  });
});
