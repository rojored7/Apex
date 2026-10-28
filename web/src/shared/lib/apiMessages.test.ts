// Revisión del Sprint 2 (M5): mensajes comunes de los errores del api.
import { ApiError, GENERIC_MESSAGES } from "../../core/api/errors";
import { INVALID_RESPONSE_MESSAGE, invalidResponseError } from "../../core/api/response";
import { connectionMessage, statusMessage, toFormError, toScreenError, waitText } from "./apiMessages";

const error = (status: number, code: string) => new ApiError({ status, code, message: "Mensaje del api." });

describe("waitText", () => {
  it.each([
    [undefined, "un momento"],
    [0, "un momento"],
    [-3, "un momento"],
    [1, "1 segundo"],
    [45, "45 segundos"],
  ])("%s → %s", (seconds, text) => {
    expect(waitText(seconds)).toBe(text);
  });
});

describe("connectionMessage", () => {
  it.each([
    [error(0, "timeout"), GENERIC_MESSAGES.timeout],
    [error(0, "network_error"), GENERIC_MESSAGES.network_error],
    [invalidResponseError(), INVALID_RESPONSE_MESSAGE],
    [error(403, "forbidden"), null],
    [error(500, "internal_error"), null],
  ])("%s", (value, expected) => {
    expect(connectionMessage(value)).toBe(expected);
  });
});

describe("toScreenError", () => {
  const byStatus = (e: ApiError): string => (e.status === 403 ? "Sin permiso." : "Falló.");

  it("sin error no hay error de pantalla", () => {
    expect(toScreenError(null, byStatus, "Ajeno.")).toBeNull();
  });

  it("un error ajeno al cliente usa el texto de respaldo", () => {
    expect(toScreenError(new Error("x"), byStatus, "Ajeno.")).toMatchObject({ status: 0, code: "unknown", message: "Ajeno." });
  });

  it("con respuesta decide la pantalla y conserva status y code", () => {
    expect(toScreenError(error(403, "forbidden"), byStatus, "Ajeno.")).toMatchObject({ status: 403, code: "forbidden", message: "Sin permiso." });
  });

  it("sin respuesta manda el mensaje de conexión", () => {
    expect(toScreenError(error(0, "timeout"), byStatus, "Ajeno.")).toMatchObject({ status: 0, code: "timeout", message: GENERIC_MESSAGES.timeout });
  });
});

describe("connectionMessage con 503 busy (S3-F3, S3-D67)", () => {
  it("un 503 busy da el mensaje genérico de sistema ocupado", () => {
    expect(connectionMessage(new ApiError({ status: 503, code: "busy", message: "Base de datos ocupada" }))).toBe("El sistema está ocupado; intenta de nuevo.");
  });

  it("toScreenError también lo usa", () => {
    const error = toScreenError(new ApiError({ status: 503, code: "busy", message: "x" }), () => "pantalla", "respaldo");

    expect(error).toMatchObject({ status: 503, code: "busy", message: "El sistema está ocupado; intenta de nuevo." });
  });
});

// Fase 4 del Sprint 3 (M5): el reparto 404/403/422/429/5xx/genérico que repetían las features.
describe("statusMessage", () => {
  const ALL = {
    notFound: "No está.",
    forbidden: "Sin permiso.",
    unprocessable: "Revisa los filtros.",
    tooMany: (wait: string) => `Espera ${wait}.`,
    server: "Falló el servidor.",
    generic: "Algo falló.",
  };

  it.each([
    [404, "No está."],
    [403, "Sin permiso."],
    [422, "Revisa los filtros."],
    [500, "Falló el servidor."],
    [503, "Falló el servidor."],
    [409, "Algo falló."],
    [400, "Algo falló."],
  ])("%i → %s", (status, text) => {
    expect(statusMessage(error(status, "x"), ALL)).toBe(text);
  });

  it("429 dice la espera del Retry-After", () => {
    const tooMany = new ApiError({ status: 429, code: "rate_limited", message: "x", retryAfterS: 30 });

    expect(statusMessage(tooMany, ALL)).toBe("Espera 30 segundos.");
    expect(statusMessage(error(429, "rate_limited"), ALL)).toBe("Espera un momento.");
  });

  it("un mensaje que la pantalla no da cae en el genérico", () => {
    for (const status of [404, 403, 422, 429, 500]) expect(statusMessage(error(status, "x"), { generic: "Algo falló." })).toBe("Algo falló.");
  });
});

describe("toFormError", () => {
  it("conserva status, code y field y pone el mensaje de la pantalla", () => {
    const out = toFormError(new ApiError({ status: 422, code: "validation_error", message: "reason too long", field: "reason" }), () => "Revisa el motivo.", "Falló.");

    expect(out).toMatchObject({ status: 422, code: "validation_error", field: "reason", message: "Revisa el motivo." });
  });

  it("sin respuesta usa el mensaje de conexión; un error ajeno, el genérico", () => {
    expect(toFormError(error(0, "timeout"), () => "x", "Falló.").message).toBe(GENERIC_MESSAGES.timeout);
    expect(toFormError(new Error("boom"), () => "x", "Falló.")).toMatchObject({ status: 0, code: "unknown", message: "Falló." });
  });
});
