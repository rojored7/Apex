// S2-F6: traducción de los errores del api de socios a la pantalla.
import { ApiError } from "../../core/api/errors";
import { CONSENT_REQUIRED_MESSAGE, createdWithoutMessage, createErrorMessage, editFieldErrorOf, fieldErrorOf, listError, savedWithoutMessage, uploadErrorMessage } from "./memberErrors";

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

describe("S6-F4 · el 422 de data_consent_at y los errores de subida", () => {
  it("el 422 de data_consent_at del alta va bajo la casilla de autorización", () => {
    expect(fieldErrorOf(error(422, "validation_error", { field: "data_consent_at" }))).toMatchObject({ path: "data_consent", existingId: null, message: CONSENT_REQUIRED_MESSAGE });
  });

  it("el 422 de data_consent_at de la edición va bajo la casilla", () => {
    expect(editFieldErrorOf(error(422, "validation_error", { field: "data_consent_at" }))).toMatchObject({ path: "data_consent", message: CONSENT_REQUIRED_MESSAGE });
  });

  it.each([
    ["photo", error(413, "file_too_large"), "La foto supera 5 MB. Elige una de menos de 5 MB."],
    ["consent", error(413, "file_too_large"), "El documento supera 5 MB. Elige uno de menos de 5 MB."],
    ["photo", error(422, "unsupported_type"), "La foto debe ser JPEG o PNG. Elige otra imagen."],
    ["consent", error(422, "unsupported_type"), "El documento debe ser PDF, JPEG o PNG. Elige otro archivo."],
    ["photo", error(409, "privacy_version_missing"), "Falta publicar la política de privacidad. Pídele a un administrador que la publique en Configuración."],
    ["photo", error(408, "upload_timeout"), "La subida tardó demasiado. Revisa tu conexión e intenta de nuevo."],
    ["photo", error(403, "forbidden"), "No tienes permiso para subir este archivo. Si lo necesitas, pídeselo a un administrador."],
    ["photo", error(404, "member_not_found"), "Este socio ya no existe. Vuelve a la lista de socios."],
    ["photo", error(429, "rate_limited", { retryAfterS: 30 }), "Subiste muchos archivos seguidos. Espera 30 segundos e intenta de nuevo."],
    ["photo", error(503, "crypto_unavailable", { retryAfterS: 30 }), "Mensaje del api."],
    ["photo", error(500, "internal_error"), "No pudimos subir el archivo. Intenta de nuevo en un momento."],
  ] as const)("uploadErrorMessage(%s) %#", (kind, value, message) => {
    expect(uploadErrorMessage(kind, value)).toBe(message);
  });

  it("un error ajeno al cliente del api es genérico", () => {
    expect(uploadErrorMessage("photo", new Error("x"))).toBe("No pudimos subir el archivo. Intenta de nuevo en un momento.");
  });

  it("el aviso de socio creado sin archivo nombra qué falta", () => {
    expect(createdWithoutMessage("photo", "Razón.")).toBe("El socio quedó creado sin foto. Razón.");
    expect(createdWithoutMessage("consent", "Razón.")).toBe("El socio quedó creado sin el documento firmado. Razón.");
    expect(savedWithoutMessage("photo", "Razón.")).toBe("Los cambios se guardaron, pero la foto no se subió. Razón.");
    expect(savedWithoutMessage("consent", "Razón.")).toBe("Los cambios se guardaron, pero el documento firmado no se subió. Razón.");
  });
});
