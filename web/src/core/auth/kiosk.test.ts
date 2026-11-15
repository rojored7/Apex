// S7-F4b · S7-D41: entrar y salir del modo quiosco por el servidor. La respuesta trae un access nuevo que reemplaza al de la sesión.
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiErrorBody } from "../../test/classes";
import { mockApi } from "../../test/server";
import { signInAs, signOutForTests } from "../../test/session";
import { enterKiosk, exitKiosk, KIOSK_MESSAGES, logoutDevice } from "./kiosk";
import { getAccessToken, getSession } from "./session";

const PATH = "/clases/11111111-1111-4111-8111-111111111111/checkin";
const out = (kioskPath: string | null) => ({ status: 200, body: { access_token: "access-quiosco", token_type: "bearer", expires_in: 900, kiosk_path: kioskPath } });

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("enterKiosk", () => {
  it("POST /auth/kiosk con la ruta, toma el access nuevo y deja kioskPath en la sesión", async () => {
    signInAs("coach");
    const mock = mockApi({ "POST /auth/kiosk": out(PATH) });

    await expect(enterKiosk(PATH)).resolves.toBeNull();

    expect(mock.callsTo("POST /auth/kiosk")[0]?.body).toEqual({ path: PATH });
    expect(getAccessToken()).toBe("access-quiosco");
    expect(getSession().user?.kioskPath).toBe(PATH);
  });

  it("si el api no lo activa, dice qué hacer y la sesión no cambia", async () => {
    signInAs("coach");
    mockApi({ "POST /auth/kiosk": { status: 500, body: apiErrorBody("internal_error") } });

    await expect(enterKiosk(PATH)).resolves.toBe(KIOSK_MESSAGES.enterFailed);

    expect(getSession().user?.kioskPath).toBeNull();
  });
});

describe("exitKiosk", () => {
  it("contraseña correcta: POST /auth/kiosk/exit (nunca /auth/login), access nuevo y sin marca", async () => {
    signInAs("coach", { kioskPath: PATH });
    const mock = mockApi({ "POST /auth/kiosk/exit": out(null) });

    await expect(exitKiosk("buena")).resolves.toBeNull();

    expect(mock.callsTo("POST /auth/kiosk/exit")[0]?.body).toEqual({ password: "buena" });
    expect(mock.callsTo("POST /auth/login")).toHaveLength(0);
    expect(getAccessToken()).toBe("access-quiosco");
    expect(getSession().user?.kioskPath).toBeNull();
  });

  it.each([
    [401, "invalid_password", KIOSK_MESSAGES.wrong],
    [429, "rate_limited", KIOSK_MESSAGES.tooMany("un momento")],
    [500, "internal_error", KIOSK_MESSAGES.generic],
  ])("%i %s dice qué hacer y la marca sigue", async (status, code, message) => {
    signInAs("coach", { kioskPath: PATH });
    mockApi({ "POST /auth/kiosk/exit": { status, body: apiErrorBody(code) } });

    await expect(exitKiosk("x")).resolves.toBe(message);

    expect(getSession().user?.kioskPath).toBe(PATH);
  });

  it("access vencido con la tablet quieta: renueva una vez y repite sin pedir otra contraseña", async () => {
    signInAs("coach", { kioskPath: PATH });
    let calls = 0;
    const mock = mockApi({
      "POST /auth/kiosk/exit": () => (++calls === 1 ? { status: 401, body: apiErrorBody("token_expired") } : out(null)),
      "POST /auth/refresh": { status: 200, body: { access_token: "renovado", token_type: "bearer", expires_in: 900 } },
      "GET /auth/me": { status: 200, body: { id: "00000000-0000-4000-8000-000000000002", email: "coach@apex.test", role: "coach", member_id: null, gym_name: "Box", must_change_password: false, kiosk_path: PATH } },
    });

    await expect(exitKiosk("buena")).resolves.toBeNull();

    expect(mock.callsTo("POST /auth/kiosk/exit")).toHaveLength(2);
    expect(getSession().user?.kioskPath).toBeNull();
  });

  it("un 401 invalid_password no cierra la sesión", async () => {
    signInAs("coach", { kioskPath: PATH });
    mockApi({ "POST /auth/kiosk/exit": { status: 401, body: apiErrorBody("invalid_password") } });

    await exitKiosk("x");

    expect(getSession().status).toBe("authenticated");
  });
});

describe("logoutDevice (LOW c)", () => {
  it("si el cierre no llegó al api lo reintenta hasta confirmarlo", async () => {
    vi.useFakeTimers();
    signInAs("coach", { kioskPath: PATH });
    let calls = 0;
    const mock = mockApi({ "POST /auth/logout": () => (++calls < 3 ? { status: 500, body: apiErrorBody("internal_error") } : { status: 204 }) });

    const pending = logoutDevice();
    await vi.advanceTimersByTimeAsync(20_000);
    const result = await pending;

    expect(mock.callsTo("POST /auth/logout")).toHaveLength(3);
    expect(result.serverConfirmed).toBe(true);
    expect(getSession().reason).toBe("logout");
  });

  it("agotados los intentos queda logout_unconfirmed (el login lo avisa)", async () => {
    vi.useFakeTimers();
    signInAs("coach");
    const mock = mockApi({ "POST /auth/logout": { status: 500, body: apiErrorBody("internal_error") } });

    const pending = logoutDevice();
    await vi.advanceTimersByTimeAsync(60_000);
    const result = await pending;

    expect(mock.callsTo("POST /auth/logout")).toHaveLength(3);
    expect(result.serverConfirmed).toBe(false);
    expect(getSession().reason).toBe("logout_unconfirmed");
  });
});

describe("403 kiosk_mode en cualquier pantalla (S7-D41)", () => {
  it("el puente de sesión relee /auth/me y deja la marca para que RequireAuth lleve al check-in", async () => {
    const { installSessionBridge } = await import("./session");
    const { api } = await import("../api/client");
    signInAs("coach");
    const uninstall = installSessionBridge();
    const mock = mockApi({
      "GET /members/1": { status: 403, body: apiErrorBody("kiosk_mode") },
      "GET /auth/me": { status: 200, body: { id: "00000000-0000-4000-8000-000000000002", email: "coach@apex.test", role: "coach", member_id: null, gym_name: "Box", must_change_password: false, kiosk_path: PATH } },
    });

    await expect(api.get("/members/1")).rejects.toMatchObject({ code: "kiosk_mode" });
    await vi.waitFor(() => { expect(getSession().user?.kioskPath).toBe(PATH); });
    expect(mock.callsTo("GET /auth/me")).toHaveLength(1);
    uninstall();
  });
});
