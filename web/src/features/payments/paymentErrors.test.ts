// S3-F4 · US-095 y US-097 (front): traducción de los errores de registrar y anular pagos. Las ramas
// que las pruebas de los componentes no recorren: errores ajenos al cliente del api, 404 de la
// membresía, 422 sin campo conocido, 429 y el resto de los de anular.
import { ApiError, GENERIC_MESSAGES } from "../../core/api/errors";
import { formatCop } from "../../core/i18n/format";
import { AMOUNT_RANGE_MESSAGE, COP_MAX, COP_MIN } from "../../shared/data/schemas/money";
import { PAYMENT_MESSAGES, registerAlert, registerFieldError, toVoidError, VOID_MESSAGES } from "./paymentErrors";

const apiError = (status: number, code: string, field?: string, retryAfterS?: number): ApiError => new ApiError({ status, code, message: "Mensaje del api.", field, retryAfterS });

describe("registerFieldError", () => {
  it("404 membership_not_found va bajo Membresía", () => {
    expect(registerFieldError(apiError(404, "membership_not_found"))).toEqual({ path: "membershipId", message: PAYMENT_MESSAGES.membershipNotFound });
  });

  it.each([
    ["method", "method", PAYMENT_MESSAGES.methodRequired],
    ["reference", "reference", PAYMENT_MESSAGES.referenceServer],
  ])("422 en %s va bajo su campo", (field, path, message) => {
    expect(registerFieldError(apiError(422, "validation_error", field))).toEqual({ path, message });
  });

  it.each([
    ["un 422 sin campo", apiError(422, "validation_error")],
    ["un 422 de un campo ajeno", apiError(422, "validation_error", "first_payment")],
    ["un 409 que no es de campo", apiError(409, "payment_limit_reached")],
    ["algo que no es ApiError", new Error("x")],
  ])("%s no va bajo un campo", (_case, error) => {
    expect(registerFieldError(error)).toBeNull();
  });
});

describe("registerAlert", () => {
  it("un error ajeno al cliente del api da el mensaje genérico", () => {
    expect(registerAlert(new Error("x"))).toBe(PAYMENT_MESSAGES.generic);
  });

  it("un 422 sin campo da el mensaje genérico", () => {
    expect(registerAlert(apiError(422, "validation_error"))).toBe(PAYMENT_MESSAGES.generic);
  });

  it("un 429 sin Retry-After pide esperar un momento", () => {
    expect(registerAlert(apiError(429, "rate_limited"))).toBe(PAYMENT_MESSAGES.tooMany("un momento"));
  });
});

describe("toVoidError", () => {
  it("conserva status, code y field y pone el mensaje de la pantalla", () => {
    const error = toVoidError(apiError(422, "validation_error", "reason"));

    expect(error).toMatchObject({ status: 422, code: "validation_error", field: "reason", message: VOID_MESSAGES.reasonInvalid });
  });

  it.each([
    [apiError(429, "rate_limited", undefined, 30), VOID_MESSAGES.tooMany("30 segundos")],
    [apiError(400, "payment_error"), VOID_MESSAGES.generic],
    [apiError(0, "network_error"), GENERIC_MESSAGES.network_error],
  ])("%s da «%s»", (error, message) => {
    expect(toVoidError(error).message).toBe(message);
  });

  it("un error ajeno al cliente del api da el mensaje genérico", () => {
    expect(toVoidError(new Error("x"))).toMatchObject({ status: 0, code: "unknown", message: VOID_MESSAGES.generic });
  });
});

// Fase 4 del Sprint 3 (M7): los textos no fijan valores de negocio que el api decide. El rango sale de
// COP_MIN y COP_MAX con formatCop; el límite retroactivo del coach (`max_retroactive_days`, que el
// coach no puede leer y el 422 no trae) y la ventana del duplicado (120 s en el api) van sin cifra.
describe("textos sin cifras fijas (M7)", () => {
  it("el rango del valor se arma con formatCop(COP_MIN) y formatCop(COP_MAX)", () => {
    expect(PAYMENT_MESSAGES.amountRange).toBe(`El valor debe estar entre ${formatCop(COP_MIN)} y ${formatCop(COP_MAX)}.`);
    expect(PAYMENT_MESSAGES.amountRange).toBe(AMOUNT_RANGE_MESSAGE);
  });

  it("paid_at_too_retroactive no dice un número de días y pide un administrador", () => {
    expect(PAYMENT_MESSAGES.paidAtTooRetroactive).not.toMatch(/\d/);
    expect(PAYMENT_MESSAGES.paidAtTooRetroactive).toContain("los días que permite el gimnasio");
    expect(PAYMENT_MESSAGES.paidAtTooRetroactive).toContain("administrador");
  });

  it("el aviso de duplicado no dice la ventana del api", () => {
    expect(PAYMENT_MESSAGES.duplicate).not.toMatch(/\d/);
    expect(PAYMENT_MESSAGES.duplicate).toContain("hace unos minutos");
  });
});
