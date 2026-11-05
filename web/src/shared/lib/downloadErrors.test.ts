// @vitest-environment node
// S5-F4: errores de descargas en palabras de la pantalla; los textos fijos del api de las
// exportaciones se muestran tal cual.
import { ApiError } from "../../core/api/errors";
import { DOWNLOAD_MESSAGES, toDownloadError } from "./downloadErrors";

const error = (status: number, code: string, message: string, extra: { field?: string; retryAfterS?: number } = {}): ApiError => new ApiError({ status, code, message, ...extra });

describe("toDownloadError", () => {
  it.each([
    [error(409, "export_in_progress", "Ya tienes una exportación en curso. Espera a que termine."), "Ya tienes una exportación en curso. Espera a que termine."],
    [error(422, "export_too_large", "La exportación supera el máximo de filas. Acota los filtros."), "La exportación supera el máximo de filas. Acota los filtros."],
    [error(422, "invalid_date_range", "El rango de fechas no es válido.", { field: "to" }), "El rango de fechas no es válido."],
    [error(503, "crypto_unavailable", "El custodio de llaves no está disponible."), "El custodio de llaves no está disponible."],
  ])("conserva el mensaje del api (%#)", (input, message) => {
    expect(toDownloadError(input).message).toBe(message);
  });

  it("conserva status, code y field", () => {
    expect(toDownloadError(error(422, "invalid_date_range", "x", { field: "to" }))).toMatchObject({ status: 422, code: "invalid_date_range", field: "to" });
  });

  it.each([
    [error(403, "forbidden", "Forbidden"), DOWNLOAD_MESSAGES.forbidden],
    [error(404, "not_found", "Not found"), DOWNLOAD_MESSAGES.notFound],
    [error(429, "rate_limited", "x", { retryAfterS: 1 }), DOWNLOAD_MESSAGES.tooMany("1 segundo")],
    [error(429, "rate_limited", "x"), DOWNLOAD_MESSAGES.tooMany("un momento")],
    [error(500, "internal_error", "boom"), DOWNLOAD_MESSAGES.server],
    [error(409, "other_conflict", "x"), DOWNLOAD_MESSAGES.generic],
    [error(422, "validation_error", ""), DOWNLOAD_MESSAGES.generic],
    [error(503, "internal_error", "x"), DOWNLOAD_MESSAGES.server],
  ])("usa el texto de la pantalla para el resto (%#)", (input, message) => {
    expect(toDownloadError(input).message).toBe(message);
  });

  it("un 503 busy dice la espera y conserva retryAfterS (LOW 2)", () => {
    expect(toDownloadError(error(503, "busy", "x", { retryAfterS: 7 }))).toMatchObject({ message: "El sistema está ocupado. Espera 7 segundos e intenta de nuevo.", retryAfterS: 7 });
    expect(toDownloadError(error(503, "busy", "x"))).toMatchObject({ message: "El sistema está ocupado. Espera un momento e intenta de nuevo.", retryAfterS: 1 });
  });

  it("sin respuesta usa los mensajes comunes de conexión", () => {
    expect(toDownloadError(error(0, "network_error", "x")).message).toContain("No pudimos conectar");
    expect(toDownloadError(error(0, "timeout", "x")).message).toContain("tardó demasiado");
  });

  it("un error ajeno al cliente del api es genérico", () => {
    expect(toDownloadError(new Error("boom")).message).toBe(DOWNLOAD_MESSAGES.generic);
  });
});
