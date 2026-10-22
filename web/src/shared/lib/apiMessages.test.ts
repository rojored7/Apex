// Revisión del Sprint 2 (M5): mensajes comunes de los errores del api.
import { ApiError, GENERIC_MESSAGES } from "../../core/api/errors";
import { INVALID_RESPONSE_MESSAGE, invalidResponseError } from "../../core/api/response";
import { connectionMessage, toScreenError, waitText } from "./apiMessages";

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
