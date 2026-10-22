// S2-F3 · US-042: contrato de POST /auth/login (LoginOut de B2) y mensajes de error.
import { ApiError, GENERIC_MESSAGES } from "../../core/api/errors";
import type { LoginOut } from "./api";
import {
  commonErrorMessage,
  INVALID_RESPONSE_MESSAGE,
  isInvalidLink,
  loginErrorMessage,
  PASSWORD_ERRORS,
  passwordErrorMessage,
  passwordFieldError,
  sessionFromLogin,
} from "./api";
import { loginSchema } from "./schemas";

const OUT: LoginOut = {
  access_token: "abc",
  token_type: "bearer",
  expires_in: 900,
  must_change_password: false,
  user: { id: "11111111-1111-4111-8111-111111111111", email: "ana@apex.test", role: "coach" },
};

const apiError = (status: number, code: string, extra: { retryAfterS?: number; field?: string } = {}) =>
  new ApiError({ status, code, message: "mensaje del api", ...extra });

describe("sessionFromLogin", () => {
  it("arma la sesión desde LoginOut; el gimnasio queda en APEX hasta que llega me", () => {
    expect(sessionFromLogin(OUT)).toEqual({
      accessToken: "abc",
      user: {
        id: OUT.user.id,
        email: "ana@apex.test",
        role: "coach",
        memberId: null,
        gymName: "APEX",
        mustChangePassword: false,
      },
    });
  });

  it.each([
    ["sin access", { ...OUT, access_token: "" }],
    ["rol desconocido", { ...OUT, user: { ...OUT.user, role: "root" } }],
    ["sin usuario", { ...OUT, user: undefined }],
    ["no es objeto", "abc"],
  ])("rechaza una respuesta con forma inesperada (%s)", (_caso, body) => {
    expect(() => sessionFromLogin(body)).toThrow();
  });
});

describe("loginErrorMessage", () => {
  it.each<[string, unknown, string]>([
    ["401", apiError(401, "invalid_credentials"), "Correo o contraseña incorrectos. Revísalos e intenta de nuevo."],
    ["401 de cuenta bloqueada", apiError(401, "account_locked"), "Correo o contraseña incorrectos. Revísalos e intenta de nuevo."],
    ["429 con espera", apiError(429, "rate_limited", { retryAfterS: 12 }), "Demasiados intentos. Espera 12 s y vuelve a intentarlo."],
    ["429 sin espera", apiError(429, "rate_limited"), "Demasiados intentos. Espera un momento y vuelve a intentarlo."],
    ["403", apiError(403, "forbidden"), "No pudimos iniciar sesión desde esta página. Recárgala e intenta de nuevo."],
    ["422", apiError(422, "validation_error"), "Revisa el correo y la contraseña e intenta de nuevo."],
    ["500", apiError(500, "internal_error"), "El servidor tuvo un problema. Intenta de nuevo en un momento."],
    ["red", apiError(0, "network_error"), GENERIC_MESSAGES.network_error],
    ["timeout", apiError(0, "timeout"), GENERIC_MESSAGES.timeout],
    ["429 de Nginx sin envelope", apiError(429, "network_error", { retryAfterS: 5 }), "Demasiados intentos. Espera 5 s y vuelve a intentarlo."],
    ["502 de Nginx sin envelope", apiError(502, "network_error"), "El servidor tuvo un problema. Intenta de nuevo en un momento."],
    ["401 de Nginx sin envelope", apiError(401, "network_error"), "Correo o contraseña incorrectos. Revísalos e intenta de nuevo."],
    ["otro 4xx", apiError(400, "bad_request"), "No pudimos iniciar sesión desde esta página. Recárgala e intenta de nuevo."],
    ["error ajeno", new Error("zod"), "No pudimos iniciar sesión desde esta página. Recárgala e intenta de nuevo."],
  ])("%s", (_caso, error, message) => {
    expect(loginErrorMessage(error)).toBe(message);
  });
});

describe("loginSchema", () => {
  it("recorta el correo y acepta una contraseña de 1 a 128 caracteres", () => {
    expect(loginSchema.parse({ email: "  ana@apex.test ", password: " x " })).toEqual({ email: "ana@apex.test", password: " x " });
    expect(loginSchema.safeParse({ email: "ana@apex.test", password: "x".repeat(128) }).success).toBe(true);
  });

  it.each([
    [{ email: "", password: "x" }, "Escribe tu correo."],
    [{ email: "ana", password: "x" }, "Escribe un correo válido, por ejemplo ana@correo.com."],
    [{ email: `${"a".repeat(250)}@x.co`, password: "x" }, "El correo admite hasta 254 caracteres."],
    [{ email: "ana@apex.test", password: "" }, "Escribe tu contraseña."],
    [{ email: "ana@apex.test", password: "x".repeat(129) }, "La contraseña admite hasta 128 caracteres."],
  ])("rechaza %j con '%s'", (values, message) => {
    const result = loginSchema.safeParse(values);
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toBe(message);
  });
});

// S2-F4a: errores de los formularios de contraseña (cambio, restablecimiento).
describe("passwordFieldError", () => {
  const unprocessable = (field: string, message = "x"): ApiError => new ApiError({ status: 422, code: "weak_password", message, field });

  it("current_password va a la contraseña actual con un mensaje propio", () => {
    expect(passwordFieldError(unprocessable("current_password"))).toEqual({ field: "currentPassword", message: PASSWORD_ERRORS.currentWrong });
  });

  it("new_password usa el motivo del api y pide otra", () => {
    expect(passwordFieldError(unprocessable("new_password", "La contraseña es demasiado débil."))).toEqual({
      field: "newPassword",
      message: "La contraseña es demasiado débil. Elige otra.",
    });
  });

  it("un motivo sin punto final (o vacío) usa el mensaje genérico de contraseña rechazada", () => {
    expect(passwordFieldError(unprocessable("new_password", "weak"))?.message).toBe(PASSWORD_ERRORS.rejected);
    expect(passwordFieldError(unprocessable("new_password", "  "))?.message).toBe(PASSWORD_ERRORS.rejected);
  });

  it("otro campo, otro código HTTP o un error ajeno no marcan nada", () => {
    expect(passwordFieldError(unprocessable("token"))).toBeNull();
    expect(passwordFieldError(new ApiError({ status: 400, code: "invalid_token", message: "x", field: "new_password" }))).toBeNull();
    expect(passwordFieldError(new Error("x"))).toBeNull();
  });
});

describe("passwordErrorMessage y commonErrorMessage", () => {
  it("400 invalid_token es el enlace vencido", () => {
    const error = new ApiError({ status: 400, code: "invalid_token", message: "x" });

    expect(isInvalidLink(error)).toBe(true);
    expect(passwordErrorMessage(error)).toBe(PASSWORD_ERRORS.invalidLink);
  });

  it("red, timeout, 429, 5xx y respuesta inválida tienen su mensaje", () => {
    expect(passwordErrorMessage(new ApiError({ status: 0, code: "network_error", message: "x" }))).toBe(GENERIC_MESSAGES.network_error);
    expect(passwordErrorMessage(new ApiError({ status: 0, code: "timeout", message: "x" }))).toBe(GENERIC_MESSAGES.timeout);
    expect(passwordErrorMessage(new ApiError({ status: 429, code: "rate_limited", message: "x", retryAfterS: 9 }))).toBe(
      "Demasiados intentos. Espera 9 s y vuelve a intentarlo.",
    );
    expect(passwordErrorMessage(new ApiError({ status: 429, code: "rate_limited", message: "x" }))).toBe("Demasiados intentos. Espera un momento y vuelve a intentarlo.");
    expect(passwordErrorMessage(new ApiError({ status: 503, code: "network_error", message: "x" }))).toBe("El servidor tuvo un problema. Intenta de nuevo en un momento.");
    expect(passwordErrorMessage(new ApiError({ status: 0, code: "invalid_response", message: INVALID_RESPONSE_MESSAGE }))).toBe(INVALID_RESPONSE_MESSAGE);
  });

  it("cualquier otro error da el genérico de contraseña", () => {
    expect(passwordErrorMessage(new ApiError({ status: 403, code: "forbidden", message: "x" }))).toBe(PASSWORD_ERRORS.generic);
    expect(passwordErrorMessage(new Error("x"))).toBe(PASSWORD_ERRORS.generic);
    expect(commonErrorMessage(new Error("x"))).toBeNull();
    expect(commonErrorMessage(new ApiError({ status: 404, code: "not_found", message: "x" }))).toBeNull();
  });
});
