// @vitest-environment node
// US-059 T1: el envelope { error: { code, message, field?, existing_id? } } del api se
// convierte en ApiError; lo que no es envelope da network_error con mensaje en español.
import { ApiError, GENERIC_MESSAGES, isApiError, parseApiError } from "./errors";

describe("parseApiError", () => {
  it("lee un envelope completo con field y existing_id", () => {
    const body = JSON.stringify({
      error: {
        code: "member_document_duplicated",
        message: "Ya existe un socio con este documento",
        field: "document",
        existing_id: "11111111-2222-3333-4444-555555555555",
      },
    });

    const error = parseApiError(409, body);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toBeInstanceOf(Error);
    expect(error.status).toBe(409);
    expect(error.code).toBe("member_document_duplicated");
    expect(error.message).toBe("Ya existe un socio con este documento");
    expect(error.field).toBe("document");
    expect(error.existingId).toBe("11111111-2222-3333-4444-555555555555");
    expect(error.name).toBe("ApiError");
  });

  it("acepta un envelope sin field ni existing_id (o con null)", () => {
    const sinCampos = parseApiError(422, JSON.stringify({ error: { code: "validation_error", message: "Dato inválido" } }));
    const conNull = parseApiError(
      422,
      JSON.stringify({ error: { code: "validation_error", message: "Dato inválido", field: null, existing_id: null } }),
    );

    for (const error of [sinCampos, conNull]) {
      expect(error.code).toBe("validation_error");
      expect(error.field).toBeUndefined();
      expect(error.existingId).toBeUndefined();
    }
  });

  it("acepta el cuerpo ya parseado como objeto", () => {
    const error = parseApiError(403, { error: { code: "forbidden", message: "Sin permiso" } });

    expect(error.code).toBe("forbidden");
  });

  it("trata 503 crypto_unavailable como un error del api, no de red (N-16)", () => {
    const error = parseApiError(
      503,
      JSON.stringify({ error: { code: "crypto_unavailable", message: "El servicio de llaves no está disponible" } }),
    );

    expect(error.status).toBe(503);
    expect(error.code).toBe("crypto_unavailable");
  });

  it.each([
    ["cuerpo HTML de Nginx", 502, "<html><body>Bad Gateway</body></html>"],
    ["cuerpo vacío", 502, ""],
    ["JSON sin envelope", 500, JSON.stringify({ detail: "boom" })],
    ["envelope con code vacío", 500, JSON.stringify({ error: { code: "", message: "x" } })],
    ["cuerpo nulo", 504, null],
  ])("con %s da network_error y un mensaje en español", (_caso, status, body) => {
    const error = parseApiError(status, body);

    expect(error.status).toBe(status);
    expect(error.code).toBe("network_error");
    expect(error.message).toBe(GENERIC_MESSAGES.network_error);
    expect(error.message).toMatch(/servidor/);
  });

  it("isApiError distingue un ApiError de otro error", () => {
    expect(isApiError(new ApiError({ status: 500, code: "x", message: "y" }))).toBe(true);
    expect(isApiError(new Error("y"))).toBe(false);
    expect(isApiError("y")).toBe(false);
  });

  it("los mensajes genéricos están en español", () => {
    expect(GENERIC_MESSAGES.network_error).toBe("No pudimos conectar con el servidor. Intenta de nuevo.");
    expect(GENERIC_MESSAGES.timeout).toBe("El servidor tardó demasiado en responder. Intenta de nuevo.");
  });
});
