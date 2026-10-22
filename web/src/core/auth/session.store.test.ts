// S2-D33, parte de F2: almacén de sesión en memoria y restoreSession (una sola promesa:
// POST /auth/refresh y luego GET /auth/me). La coordinación del refresh, el logout y el
// puente con el cliente son de F3 (session.test.ts).
import { act, cleanup, renderHook } from "@testing-library/react";
import { mockApi } from "../../test/server";
import {
  clearSession,
  getAccessToken,
  getSession,
  resetSessionForTests,
  restoreSession,
  setSession,
  subscribe,
  useSession,
} from "./session";

const ME = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "ana@apex.test",
  role: "admin",
  member_id: null,
  gym_name: "Box Norte",
  must_change_password: false,
};
const REFRESH = { access_token: "nuevo-access", token_type: "bearer", expires_in: 900 };

const USER = {
  id: ME.id,
  email: ME.email,
  role: "coach" as const,
  memberId: null,
  gymName: "Box Norte",
  mustChangePassword: false,
};

afterEach(() => {
  cleanup();
  resetSessionForTests();
  vi.unstubAllGlobals();
});

describe("almacén de sesión", () => {
  it("arranca en loading sin usuario ni token", () => {
    expect(getSession()).toEqual({ status: "loading", user: null });
    expect(getAccessToken()).toBeNull();
  });

  it("setSession autentica y guarda el token solo en memoria", () => {
    setSession({ accessToken: "abc", user: USER });

    expect(getSession()).toEqual({ status: "authenticated", user: USER });
    expect(getAccessToken()).toBe("abc");
    for (const storage of [localStorage, sessionStorage]) {
      const values = Array.from({ length: storage.length }, (_, i) => storage.getItem(storage.key(i) ?? "") ?? "");
      expect(values.join("|")).not.toContain("abc");
    }
  });

  it("clearSession deja anonymous con la razón y sin token", () => {
    setSession({ accessToken: "abc", user: USER });
    clearSession("logout");

    expect(getSession()).toEqual({ status: "anonymous", user: null, reason: "logout" });
    expect(getAccessToken()).toBeNull();
  });

  it("subscribe avisa cada cambio y se puede quitar", () => {
    const listener = vi.fn();
    const unsubscribe = subscribe(listener);

    setSession({ accessToken: "abc", user: USER });
    clearSession("expired");
    unsubscribe();
    setSession({ accessToken: "x", user: USER });

    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("useSession sigue el estado", () => {
    const { result } = renderHook(() => useSession());
    expect(result.current.status).toBe("loading");

    act(() => {
      setSession({ accessToken: "abc", user: USER });
    });
    expect(result.current.user?.email).toBe("ana@apex.test");
  });
});

describe("restoreSession", () => {
  it("hace un refresh y un me, y llena el usuario con gym_name y must_change_password", async () => {
    const api = mockApi({ "POST /auth/refresh": { status: 200, body: REFRESH }, "GET /auth/me": { status: 200, body: ME } });

    await expect(restoreSession()).resolves.toBe(true);

    expect(api.callsTo("POST /auth/refresh")).toHaveLength(1);
    const me = api.callsTo("GET /auth/me");
    expect(me).toHaveLength(1);
    expect(me[0]?.headers.get("Authorization")).toBe("Bearer nuevo-access");
    expect(getSession()).toEqual({
      status: "authenticated",
      user: { id: ME.id, email: ME.email, role: "admin", memberId: null, gymName: "Box Norte", mustChangePassword: false },
    });
    expect(getAccessToken()).toBe("nuevo-access");
  });

  it("llamadas concurrentes comparten una sola promesa (un refresh, un me)", async () => {
    const api = mockApi({ "POST /auth/refresh": { status: 200, body: REFRESH }, "GET /auth/me": { status: 200, body: ME } });

    const results = await Promise.all([restoreSession(), restoreSession(), restoreSession()]);

    expect(results).toEqual([true, true, true]);
    expect(api.callsTo("POST /auth/refresh")).toHaveLength(1);
    expect(api.callsTo("GET /auth/me")).toHaveLength(1);
  });

  it("un refresh 401 deja la sesión anónima y no pide me", async () => {
    const api = mockApi({
      "POST /auth/refresh": { status: 401, body: { error: { code: "invalid_refresh", message: "Tu sesión terminó." } } },
    });

    await expect(restoreSession()).resolves.toBe(false);

    expect(getSession()).toEqual({ status: "anonymous", user: null, reason: "restore_failed" });
    expect(api.callsTo("GET /auth/me")).toHaveLength(0);
    expect(getAccessToken()).toBeNull();
  });

  it("una respuesta de me que no cumple el contrato no autentica", async () => {
    mockApi({
      "POST /auth/refresh": { status: 200, body: REFRESH },
      "GET /auth/me": { status: 200, body: { ...ME, role: "root" } },
    });

    await expect(restoreSession()).resolves.toBe(false);
    expect(getSession().status).toBe("anonymous");
    expect(getAccessToken()).toBeNull();
  });

  it("un refresh sin token no autentica", async () => {
    mockApi({ "POST /auth/refresh": { status: 200, body: { token_type: "bearer", expires_in: 900 } } });

    await expect(restoreSession()).resolves.toBe(false);
  });

  it("refresh y me van sin reintento por 401 (skipAuthRetry) y con credentials same-origin", async () => {
    const fetchSpy = vi.fn(async () => Promise.resolve(new Response(JSON.stringify({ error: { code: "unauthorized", message: "x" } }), { status: 401 })));
    vi.stubGlobal("fetch", fetchSpy);

    await restoreSession();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.credentials).toBe("same-origin");
    expect(init.method).toBe("POST");
  });
});
