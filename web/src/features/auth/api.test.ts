// S2-F3 · US-042: contrato de POST /auth/login (LoginOut de B2) y mensajes de error.
import { ApiError, GENERIC_MESSAGES } from "../../core/api/errors";
import type { LoginOut } from "./api";
import { loginErrorMessage, sessionFromLogin } from "./api";
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
