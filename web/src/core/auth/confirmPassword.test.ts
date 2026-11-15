// S7-F4 · S7-D24: comprobar la contraseña de la cuenta (salir del modo tablet) sin tocar la sesión.
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiErrorBody } from "../../test/classes";
import { getAccessToken } from "./session";
import { confirmPassword } from "./confirmPassword";
import { mockApi } from "../../test/server";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("confirmPassword", () => {
  it("contraseña correcta: null y no cambia el token de la sesión", async () => {
    const before = getAccessToken();
    const mock = mockApi({ "POST /auth/login": { status: 200, body: { access_token: "otro", user: {} } } });

    await expect(confirmPassword("coach@apex.test", "buena")).resolves.toBeNull();

    expect(mock.callsTo("POST /auth/login")[0]?.body).toEqual({ email: "coach@apex.test", password: "buena" });
    expect(getAccessToken()).toBe(before);
  });

  it.each([
    [401, "unauthorized", "Contraseña incorrecta. Escríbela de nuevo."],
    [429, "rate_limited", "Hiciste muchos intentos. Espera un momento e intenta de nuevo."],
    [500, "internal_error", "No pudimos verificar la contraseña. Intenta de nuevo en un momento."],
  ])("%i %s dice qué hacer", async (status, code, message) => {
    mockApi({ "POST /auth/login": { status, body: apiErrorBody(code) } });

    await expect(confirmPassword("coach@apex.test", "x")).resolves.toBe(message);
  });
});
