// S2-F3 (US-043, US-044; S2-D33 parte de F3): refresh coordinado, cierre de sesión y puente
// con el cliente del api. Casos del blueprint (sección 7.6) más L-6, L-12 y H-1.
// - Tres peticiones con token_expired hacen un solo refresh y tres reintentos.
// - Un refresh 401 limpia la sesión y RequireAuth manda a /login?next=<ruta>.
// - Dos "pestañas" (dos instancias del módulo) con BroadcastChannel y Web Locks hacen un solo
//   refresh; los mensajes de apex-auth llevan secuencia y un token tras un logout se ignora.
// - Un 429 nunca limpia la sesión; un fallo del logout se informa como tal (H-1).
// - Nada en localStorage ni sessionStorage, nada en console.
import { act, cleanup, render, screen } from "@testing-library/react";
import { createElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { api } from "../api/client";
import { ApiError } from "../api/errors";
import { queryClient } from "../api/queryClient";
import { installTabDoubles, openChannels, posted, resetTabDoubles, type FakeLockManager } from "../../test/authChannel";
import { mockApi, type MockReply, type RecordedCall } from "../../test/server";
import { testUser } from "../../test/session";
import { RequireAuth } from "./RequireAuth";
import {
  AUTH_CHANNEL,
  REFRESH_LOCK,
  adoptAccessToken,
  clearSession,
  endSession,
  getAccessToken,
  getSession,
  installSessionBridge,
  logout,
  refreshAccessToken,
  refreshCurrentUser,
  resetSessionForTests,
  restoreSession,
  setSession,
  updateSessionUser,
} from "./session";

type SessionModule = typeof import("./session");
type ClientModule = typeof import("../api/client");

const OLD = "access-viejo";
const NEW = "access-nuevo";
const REFRESH_OK: MockReply = { status: 200, body: { access_token: NEW, token_type: "bearer", expires_in: 900 } };
const EXPIRED: MockReply = { status: 401, body: { error: { code: "token_expired", message: "Token vencido" } } };
const UNAUTHORIZED: MockReply = { status: 401, body: { error: { code: "unauthorized", message: "No autorizado" } } };
const INVALID_REFRESH: MockReply = { status: 401, body: { error: { code: "invalid_refresh", message: "Sesión inválida" } } };
const TOO_MANY: MockReply = {
  status: 429,
  body: { error: { code: "rate_limited", message: "Demasiadas solicitudes" } },
  headers: { "Retry-After": "30" },
};
const SERVER_ERROR: MockReply = { status: 500, body: { error: { code: "internal_error", message: "Error" } } };
const ME = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "admin@apex.test",
  role: "admin",
  member_id: null,
  gym_name: "Box Norte",
  must_change_password: false,
};

// JSX no cabe en un .ts (el plan fija session.test.ts): los elementos se crean con createElement.
const h1 = (text: string) => createElement("h1", null, text);

const bearer = (call: RecordedCall): string | null => call.headers.get("Authorization");

/** Responde 200 a quien trae el token nuevo y token_expired a quien trae el viejo. */
function protectedReply(call: RecordedCall): MockReply {
  return bearer(call) === `Bearer ${NEW}` ? { status: 200, body: { ok: true } } : EXPIRED;
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

const flush = async (): Promise<void> => {
  for (let i = 0; i < 5; i += 1) await Promise.resolve();
};

let uninstall: (() => void) | null = null;

function signIn(token = OLD, role: "admin" | "coach" = "admin"): void {
  setSession({ accessToken: token, user: testUser(role) });
}

beforeEach(() => {
  uninstall = installSessionBridge();
});

afterEach(() => {
  cleanup();
  uninstall?.();
  uninstall = null;
  resetSessionForTests();
  resetTabDoubles();
  queryClient.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("puente con el cliente del api", () => {
  it("entrega el access token de la sesión al cliente", async () => {
    const server = mockApi({ "GET /socios": { status: 200, body: { ok: true } } });
    signIn("abc");

    await api.get("/socios");

    expect(bearer(server.callsTo("GET /socios")[0] as RecordedCall)).toBe("Bearer abc");
  });

  it("tres peticiones con token_expired hacen un solo refresh y tres reintentos", async () => {
    const server = mockApi({ "GET /socios": protectedReply, "POST /auth/refresh": REFRESH_OK });
    signIn();

    const results = await Promise.all([api.get("/socios"), api.get("/socios"), api.get("/socios")]);

    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }]);
    expect(server.callsTo("POST /auth/refresh")).toHaveLength(1);
    expect(server.callsTo("GET /socios").map(bearer)).toEqual([
      `Bearer ${OLD}`,
      `Bearer ${OLD}`,
      `Bearer ${OLD}`,
      `Bearer ${NEW}`,
      `Bearer ${NEW}`,
      `Bearer ${NEW}`,
    ]);
    expect(getAccessToken()).toBe(NEW);
    expect(getSession().status).toBe("authenticated");
  });

  it("el refresh va con la cookie del mismo origen, sin Bearer viejo de por medio y sin reintentarse a sí mismo", async () => {
    const server = mockApi({ "GET /socios": EXPIRED, "POST /auth/refresh": INVALID_REFRESH });
    signIn();

    await expect(api.get("/socios")).rejects.toMatchObject({ status: 401 });

    const [refresh] = server.callsTo("POST /auth/refresh");
    expect(server.callsTo("POST /auth/refresh")).toHaveLength(1);
    expect(refresh?.credentials).toBe("same-origin");
  });

  it("un refresh 401 limpia la sesión como vencida", async () => {
    mockApi({ "GET /socios": EXPIRED, "POST /auth/refresh": INVALID_REFRESH });
    signIn();

    await expect(api.get("/socios")).rejects.toBeInstanceOf(ApiError);

    expect(getSession()).toEqual({ status: "anonymous", user: null, reason: "expired" });
    expect(getAccessToken()).toBeNull();
  });

  it("un refresh 401 lleva a /login?next=/socios", async () => {
    mockApi({ "GET /socios": EXPIRED, "POST /auth/refresh": INVALID_REFRESH });
    signIn();
    const router = createMemoryRouter(
      [
        { path: "/login", element: h1("Pantalla de login") },
        { element: createElement(RequireAuth), children: [{ path: "/socios", element: h1("Socios") }] },
      ],
      { initialEntries: ["/socios"] },
    );
    render(createElement(RouterProvider, { router }));
    expect(screen.getByRole("heading", { name: "Socios" })).toBeInTheDocument();

    await act(async () => {
      await expect(api.get("/socios")).rejects.toBeInstanceOf(ApiError);
    });

    expect(await screen.findByRole("heading", { name: "Pantalla de login" })).toBeInTheDocument();
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe("/login?next=%2Fsocios");
  });

  it("un 401 unauthorized limpia la sesión sin intentar el refresh", async () => {
    const server = mockApi({ "GET /socios": UNAUTHORIZED });
    signIn();

    await expect(api.get("/socios")).rejects.toMatchObject({ code: "unauthorized" });

    expect(server.callsTo("POST /auth/refresh")).toHaveLength(0);
    expect(getSession()).toMatchObject({ status: "anonymous", reason: "unauthorized" });
  });

  it("L-12: un refresh con 429 no limpia la sesión", async () => {
    mockApi({ "GET /socios": EXPIRED, "POST /auth/refresh": TOO_MANY });
    signIn();

    await expect(api.get("/socios")).rejects.toMatchObject({ status: 401 });

    expect(getSession().status).toBe("authenticated");
    expect(getAccessToken()).toBe(OLD);
  });

  it("un refresh con 5xx o sin red tampoco limpia la sesión", async () => {
    mockApi({ "POST /auth/refresh": SERVER_ERROR });
    signIn();
    await expect(refreshAccessToken()).resolves.toBe(false);
    expect(getSession().status).toBe("authenticated");

    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(refreshAccessToken()).resolves.toBe(false);
    expect(getSession().status).toBe("authenticated");
    expect(getAccessToken()).toBe(OLD);
  });

  it("una respuesta de refresh con forma inesperada no cambia el token ni la sesión", async () => {
    mockApi({ "POST /auth/refresh": { status: 200, body: { token: "x" } } });
    signIn();

    await expect(refreshAccessToken()).resolves.toBe(false);

    expect(getAccessToken()).toBe(OLD);
    expect(getSession().status).toBe("authenticated");
  });

  it("sin sesión no intenta el refresh", async () => {
    const server = mockApi({ "POST /auth/refresh": REFRESH_OK });
    clearSession("logout");

    await expect(refreshAccessToken()).resolves.toBe(false);

    expect(server.callsTo("POST /auth/refresh")).toHaveLength(0);
  });

  it("un logout durante el refresh gana: la respuesta tardía no revive la sesión ni se publica", async () => {
    installTabDoubles();
    uninstall?.();
    uninstall = installSessionBridge();
    const gate = deferred<MockReply>();
    mockApi({ "POST /auth/refresh": () => gate.promise, "POST /auth/logout": { status: 204 } });
    signIn();

    const pending = refreshAccessToken();
    await flush();
    clearSession("logout");
    gate.resolve(REFRESH_OK);

    await expect(pending).resolves.toBe(false);
    expect(getAccessToken()).toBeNull();
    expect(getSession().status).toBe("anonymous");
    expect(posted.filter((m) => (m.data as { type: string }).type === "token")).toHaveLength(0);
  });

  it("uninstall desconecta el gancho del 401", async () => {
    const server = mockApi({ "GET /socios": EXPIRED, "POST /auth/refresh": REFRESH_OK });
    signIn();
    uninstall?.();
    uninstall = null;

    await expect(api.get("/socios")).rejects.toMatchObject({ code: "token_expired" });

    expect(server.callsTo("POST /auth/refresh")).toHaveLength(0);
  });

  it("installSessionBridge es idempotente", async () => {
    const again = installSessionBridge();
    const server = mockApi({ "GET /socios": protectedReply, "POST /auth/refresh": REFRESH_OK });
    signIn();

    await api.get("/socios");

    expect(server.callsTo("POST /auth/refresh")).toHaveLength(1);
    again();
  });
});

describe("restauración al arrancar", () => {
  it("POST /auth/refresh y GET /auth/me van con credentials same-origin", async () => {
    resetSessionForTests();
    const server = mockApi({ "POST /auth/refresh": REFRESH_OK, "GET /auth/me": { status: 200, body: ME } });

    await expect(restoreSession()).resolves.toBe(true);

    expect(server.calls.map((c) => [`${c.method} ${c.path}`, c.credentials])).toEqual([
      ["POST /auth/refresh", "same-origin"],
      ["GET /auth/me", "same-origin"],
    ]);
  });

  it("must_change_password queda en la sesión y RequireAuth manda a /cambiar-clave", async () => {
    resetSessionForTests();
    mockApi({ "POST /auth/refresh": REFRESH_OK, "GET /auth/me": { status: 200, body: { ...ME, must_change_password: true } } });
    const router = createMemoryRouter(
      [
        {
          element: createElement(RequireAuth),
          children: [
            { path: "/socios", element: h1("Socios") },
            { path: "/cambiar-clave", element: h1("Cambiar contraseña") },
          ],
        },
      ],
      { initialEntries: ["/socios"] },
    );
    render(createElement(RouterProvider, { router }));

    expect(await screen.findByRole("heading", { name: "Cambiar contraseña" })).toBeInTheDocument();
    expect(getSession().user?.mustChangePassword).toBe(true);
  });
});

describe("usuario de la sesión (GET /auth/me)", () => {
  it("refreshCurrentUser toma gym_name y member_id de me", async () => {
    mockApi({ "GET /auth/me": { status: 200, body: { ...ME, gym_name: "Box Sur" } } });
    setSession({ accessToken: OLD, user: testUser("admin", { gymName: "APEX" }) });

    await refreshCurrentUser();

    expect(getSession().user).toMatchObject({ gymName: "Box Sur", memberId: null, email: ME.email });
    expect(getAccessToken()).toBe(OLD);
  });

  it("L-12: GET /auth/me con 429 mantiene al usuario", async () => {
    mockApi({ "GET /auth/me": TOO_MANY });
    const user = testUser("admin");
    setSession({ accessToken: OLD, user });

    await refreshCurrentUser();

    expect(getSession()).toEqual({ status: "authenticated", user });
    expect(getAccessToken()).toBe(OLD);
  });

  it("una respuesta de me con forma inesperada no cambia nada", async () => {
    const user = testUser("admin");
    mockApi({ "GET /auth/me": { status: 200, body: { nope: true } } });
    setSession({ accessToken: OLD, user });

    await refreshCurrentUser();

    expect(getSession().user).toEqual(user);
  });

  it("si me es de otra cuenta (otra pestaña entró con ella), esta pestaña cierra su sesión", async () => {
    mockApi({ "GET /auth/me": { status: 200, body: { ...ME, id: "otra-cuenta" } } });
    signIn();

    await refreshCurrentUser();

    expect(getSession()).toMatchObject({ status: "anonymous", reason: "unauthorized" });
    expect(getAccessToken()).toBeNull();
  });

  it("un cierre de sesión durante me no se deshace", async () => {
    const gate = deferred<MockReply>();
    mockApi({ "GET /auth/me": () => gate.promise });
    signIn();

    const pending = refreshCurrentUser();
    await flush();
    clearSession("logout");
    gate.resolve({ status: 200, body: ME });
    await pending;

    expect(getSession().status).toBe("anonymous");
  });

  it("sin sesión no pide me", async () => {
    const server = mockApi({ "GET /auth/me": { status: 200, body: ME } });
    clearSession("logout");

    await refreshCurrentUser();

    expect(server.calls).toHaveLength(0);
  });
});

describe("cierre de sesión", () => {
  it("POST /auth/logout con la cookie, sin refresh ante un 401; limpia, publica y vacía la caché", async () => {
    installTabDoubles();
    uninstall?.();
    uninstall = installSessionBridge();
    const server = mockApi({ "POST /auth/logout": UNAUTHORIZED, "POST /auth/refresh": REFRESH_OK });
    signIn();
    queryClient.setQueryData(["socios"], { items: [1] });

    const result = await logout();

    expect(server.callsTo("POST /auth/refresh")).toHaveLength(0);
    expect(server.callsTo("POST /auth/logout")[0]?.credentials).toBe("same-origin");
    expect(result.serverConfirmed).toBe(false);
    expect(getSession().status).toBe("anonymous");
    expect(queryClient.getQueryData(["socios"])).toBeUndefined();
    expect(posted.map((m) => (m.data as { type: string }).type)).toEqual(["logout"]);
  });

  it("tras el 204 la sesión queda limpia con la razón logout", async () => {
    mockApi({ "POST /auth/logout": { status: 204 } });
    signIn();

    await expect(logout()).resolves.toEqual({ serverConfirmed: true });

    expect(getSession()).toEqual({ status: "anonymous", user: null, reason: "logout" });
    expect(getAccessToken()).toBeNull();
  });

  it("H-1: un 5xx no se presenta como éxito (logout_unconfirmed) y aun así limpia", async () => {
    mockApi({ "POST /auth/logout": SERVER_ERROR });
    signIn();

    await expect(logout()).resolves.toEqual({ serverConfirmed: false });

    expect(getSession()).toEqual({ status: "anonymous", user: null, reason: "logout_unconfirmed" });
    expect(getAccessToken()).toBeNull();
  });

  it("H-1: sin red tampoco es éxito", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    signIn();

    await expect(logout()).resolves.toEqual({ serverConfirmed: false });

    expect(getSession().reason).toBe("logout_unconfirmed");
  });

  it("dos clics seguidos hacen un solo POST /auth/logout", async () => {
    const server = mockApi({ "POST /auth/logout": { status: 204 } });
    signIn();

    await Promise.all([logout(), logout()]);

    expect(server.callsTo("POST /auth/logout")).toHaveLength(1);
  });

  it("clearSession vacía la caché de TanStack Query", () => {
    signIn();
    queryClient.setQueryData(["usuarios"], [1, 2]);

    clearSession("expired");

    expect(queryClient.getQueryData(["usuarios"])).toBeUndefined();
  });
});

describe("varias pestañas (apex-auth y apex-refresh)", () => {
  interface Tab {
    session: SessionModule;
    client: ClientModule;
    uninstall: () => void;
  }

  const tabs: Tab[] = [];

  async function openTab(): Promise<Tab> {
    vi.resetModules();
    const session = await import("./session");
    const client = await import("../api/client");
    const tab = { session, client, uninstall: session.installSessionBridge() };
    tabs.push(tab);
    return tab;
  }

  function signInTab(tab: Tab, token = OLD): void {
    tab.session.setSession({ accessToken: token, user: testUser("admin") });
  }

  afterEach(() => {
    for (const tab of tabs.splice(0)) {
      tab.uninstall();
      tab.session.resetSessionForTests();
    }
  });

  it("dos pestañas con el access vencido hacen un solo refresh y las dos reintentan con el nuevo", async () => {
    const locks = installTabDoubles() as FakeLockManager;
    const server = mockApi({ "GET /socios": protectedReply, "POST /auth/refresh": REFRESH_OK });
    const a = await openTab();
    const b = await openTab();
    signInTab(a);
    signInTab(b);

    const results = await Promise.all([a.client.api.get("/socios"), b.client.api.get("/socios")]);

    expect(results).toEqual([{ ok: true }, { ok: true }]);
    expect(server.callsTo("POST /auth/refresh")).toHaveLength(1);
    expect(locks.requested.length).toBeGreaterThan(0);
    expect(new Set(locks.requested)).toEqual(new Set([REFRESH_LOCK]));
    expect(a.session.getAccessToken()).toBe(NEW);
    expect(b.session.getAccessToken()).toBe(NEW);
  });

  it("M1 (revisión del Sprint 2): solo la pestaña que pidió el refresh a la red relee me desde el refresh", async () => {
    installTabDoubles();
    const server = mockApi({ "GET /socios": protectedReply, "POST /auth/refresh": REFRESH_OK, "GET /auth/me": { status: 200, body: ME } });
    const a = await openTab();
    const b = await openTab();
    signInTab(a);
    signInTab(b);

    await Promise.all([a.client.api.get("/socios"), b.client.api.get("/socios")]);
    await vi.waitFor(() => {
      expect(server.callsTo("GET /auth/me").length).toBeGreaterThanOrEqual(2);
    });
    await flush();

    // Una lectura por el refresh de red y otra por el token recibido en el canal; ninguna más.
    expect(server.callsTo("POST /auth/refresh")).toHaveLength(1);
    expect(server.callsTo("GET /auth/me")).toHaveLength(2);
    expect(a.session.getSession().status).toBe("authenticated");
    expect(b.session.getSession().status).toBe("authenticated");
  });

  it("sin navigator.locks rigen la promesa única y el canal", async () => {
    installTabDoubles({ locks: false });
    const server = mockApi({ "GET /socios": protectedReply, "POST /auth/refresh": REFRESH_OK });
    const a = await openTab();
    signInTab(a);

    await Promise.all([a.client.api.get("/socios"), a.client.api.get("/socios")]);

    expect(server.callsTo("POST /auth/refresh")).toHaveLength(1);
  });

  it("el mensaje token lleva el access, el vencimiento y la secuencia; nunca el refresh", async () => {
    installTabDoubles();
    mockApi({ "POST /auth/refresh": REFRESH_OK });
    const a = await openTab();
    signInTab(a);

    await a.session.refreshAccessToken();

    const tokens = posted.filter((m) => (m.data as { type: string }).type === "token");
    expect(tokens).toHaveLength(1);
    expect(tokens[0]?.channel).toBe(AUTH_CHANNEL);
    expect(Object.keys(tokens[0]?.data as object).sort()).toEqual(["accessToken", "expiresIn", "seq", "type"]);
    expect(tokens[0]?.data).toMatchObject({ type: "token", accessToken: NEW, expiresIn: 900 });
    expect(JSON.stringify(posted)).not.toMatch(/refresh_token|apex_refresh/);
  });

  it("un token de otra pestaña reemplaza el access de esta", async () => {
    installTabDoubles();
    const a = await openTab();
    const b = await openTab();
    signInTab(a);
    signInTab(b);

    a.session.adoptAccessToken("de-a", 900);
    await flush();

    expect(b.session.getAccessToken()).toBe("de-a");
    expect(b.session.getSession().status).toBe("authenticated");
  });

  it("un logout en una pestaña cierra la sesión de las demás", async () => {
    installTabDoubles();
    mockApi({ "POST /auth/logout": { status: 204 } });
    const a = await openTab();
    const b = await openTab();
    signInTab(a);
    signInTab(b);

    await a.session.logout();
    await flush();

    expect(b.session.getSession()).toEqual({ status: "anonymous", user: null, reason: "logout" });
    expect(b.session.getAccessToken()).toBeNull();
  });

  it("L-6: un token que llega después de un logout se ignora", async () => {
    installTabDoubles();
    const b = await openTab();
    signInTab(b);
    const [channel] = openChannels(AUTH_CHANNEL);

    channel?.deliver({ type: "logout", seq: 10 });
    channel?.deliver({ type: "token", seq: 11, accessToken: "tardio", expiresIn: 900 });

    expect(b.session.getAccessToken()).toBeNull();
    expect(b.session.getSession().status).toBe("anonymous");
  });

  it("L-6: un mensaje con secuencia vieja o mal formado se ignora", async () => {
    installTabDoubles();
    const b = await openTab();
    signInTab(b);
    const [channel] = openChannels(AUTH_CHANNEL);

    channel?.deliver({ type: "token", seq: 20, accessToken: "veinte", expiresIn: 900 });
    channel?.deliver({ type: "token", seq: 19, accessToken: "diecinueve", expiresIn: 900 });
    channel?.deliver({ type: "token", seq: 21, accessToken: 5 });
    channel?.deliver("basura");

    expect(b.session.getAccessToken()).toBe("veinte");
    expect(b.session.getSession().status).toBe("authenticated");
  });

  it("un logout se aplica aunque su secuencia sea vieja (perder un cierre es peor que repetirlo)", async () => {
    installTabDoubles();
    const b = await openTab();
    signInTab(b);
    const [channel] = openChannels(AUTH_CHANNEL);

    channel?.deliver({ type: "token", seq: 20, accessToken: "veinte", expiresIn: 900 });
    channel?.deliver({ type: "logout", seq: 3 });

    expect(b.session.getSession()).toMatchObject({ status: "anonymous", reason: "logout" });
  });

  it("la secuencia propia supera a la última recibida", async () => {
    installTabDoubles();
    const b = await openTab();
    signInTab(b);
    const [channel] = openChannels(AUTH_CHANNEL);
    channel?.deliver({ type: "token", seq: Number.MAX_SAFE_INTEGER - 5, accessToken: "x", expiresIn: 900 });

    b.session.adoptAccessToken("propio", 900);

    const own = posted.at(-1)?.data as { seq: number };
    expect(own.seq).toBeGreaterThan(Number.MAX_SAFE_INTEGER - 5);
  });

  it("una pestaña sin sesión no adopta tokens ajenos", async () => {
    installTabDoubles();
    const b = await openTab();
    b.session.clearSession("logout");
    const [channel] = openChannels(AUTH_CHANNEL);

    channel?.deliver({ type: "token", seq: 50, accessToken: "ajeno", expiresIn: 900 });

    expect(b.session.getAccessToken()).toBeNull();
  });
});

describe("el token nunca sale de la memoria", () => {
  it("no se escribe en console ni en el almacenamiento del navegador", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((method) => vi.spyOn(console, method));
    installTabDoubles();
    uninstall?.();
    uninstall = installSessionBridge();
    mockApi({
      "GET /socios": protectedReply,
      "POST /auth/refresh": REFRESH_OK,
      "POST /auth/logout": SERVER_ERROR,
    });
    signIn();

    await api.get("/socios");
    await logout();

    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
    for (const storage of [localStorage, sessionStorage]) {
      const dump = Array.from({ length: storage.length }, (_, i) => `${storage.key(i) ?? ""}=${storage.getItem(storage.key(i) ?? "") ?? ""}`).join("|");
      expect(dump).not.toContain(OLD);
      expect(dump).not.toContain(NEW);
    }
  });

  it("ningún archivo de src/core/auth usa localStorage ni sessionStorage", () => {
    const sources = import.meta.glob(["./*.ts", "./*.tsx", "!./*.test.ts", "!./*.test.tsx"], {
      query: "?raw",
      import: "default",
      eager: true,
    });
    const files = Object.keys(sources);
    expect(files).toContain("./session.ts");
    for (const [file, text] of Object.entries(sources)) {
      expect({ file, uses: /\b(?:local|session)Storage\s*[.[]|\bwindow\s*\.\s*(?:local|session)Storage/.test(String(text)) }).toEqual({
        file,
        uses: false,
      });
    }
  });
});

describe("adoptAccessToken (S2-D37: access nuevo tras cambiar la contraseña)", () => {
  it("reemplaza el access de la sesión sin tocar el usuario", () => {
    signIn();
    const user = getSession().user;

    adoptAccessToken("tras-cambio", 900);

    expect(getAccessToken()).toBe("tras-cambio");
    expect(getSession().user).toBe(user);
  });

  it("sin sesión no hace nada", () => {
    clearSession("logout");

    adoptAccessToken("ajeno", 900);

    expect(getAccessToken()).toBeNull();
  });
});

describe("correcciones de la revisión (S2-F3)", () => {
  it("un 401 unauthorized de una petición que salió con un token viejo no cierra la sesión nueva", async () => {
    const gate = deferred<MockReply>();
    const server = mockApi({ "GET /lento": () => gate.promise, "GET /socios": protectedReply });
    signIn(OLD);

    const slow = api.get("/lento");
    await flush();
    signIn(NEW);
    gate.resolve(UNAUTHORIZED);

    await expect(slow).rejects.toBeInstanceOf(ApiError);
    expect(getSession().status).toBe("authenticated");
    expect(getAccessToken()).toBe(NEW);
    expect(server.callsTo("GET /lento").map(bearer)).toEqual([`Bearer ${OLD}`, `Bearer ${NEW}`]);
  });

  it("si publicar en el canal falla, el cierre de sesión igual limpia todo", async () => {
    installTabDoubles();
    uninstall?.();
    uninstall = installSessionBridge();
    mockApi({ "POST /auth/logout": { status: 204 } });
    signIn();
    for (const channel of openChannels(AUTH_CHANNEL)) channel.close();

    await expect(logout()).resolves.toEqual({ serverConfirmed: true });

    expect(getSession()).toMatchObject({ status: "anonymous", reason: "logout" });
  });

  it("un login nuevo no hereda un refresh viejo todavía en curso", async () => {
    const gate = deferred<MockReply>();
    const server = mockApi({ "POST /auth/refresh": () => gate.promise });
    signIn();
    const old = refreshAccessToken();
    await flush();

    signIn("de-otro-login");
    const fresh = refreshAccessToken();

    expect(fresh).not.toBe(old);
    gate.resolve(REFRESH_OK);
    await expect(old).resolves.toBe(false);
    await fresh;
    expect(server.callsTo("POST /auth/refresh").length).toBeGreaterThanOrEqual(1);
  });

  it("restaurar conserva un token más nuevo que llegó por el canal mientras se leía me", async () => {
    installTabDoubles();
    uninstall?.();
    resetSessionForTests();
    uninstall = installSessionBridge();
    const gate = deferred<MockReply>();
    const server = mockApi({ "POST /auth/refresh": REFRESH_OK, "GET /auth/me": () => gate.promise });

    const pending = restoreSession();
    await flush();
    await vi.waitFor(() => {
      expect(server.callsTo("GET /auth/me")).toHaveLength(1);
    });
    openChannels(AUTH_CHANNEL)[0]?.deliver({ type: "token", seq: Number.MAX_SAFE_INTEGER, accessToken: "mas-nuevo", expiresIn: 900 });
    gate.resolve({ status: 200, body: ME });

    await expect(pending).resolves.toBe(true);
    expect(getAccessToken()).toBe("mas-nuevo");
  });

  it("un token de otra pestaña relee me y, si la cuenta cambió, cierra esta sesión", async () => {
    installTabDoubles();
    uninstall?.();
    uninstall = installSessionBridge();
    const server = mockApi({ "GET /auth/me": { status: 200, body: { ...ME, id: "otra-cuenta" } } });
    signIn();

    openChannels(AUTH_CHANNEL)[0]?.deliver({ type: "token", seq: Number.MAX_SAFE_INTEGER, accessToken: "de-otra-cuenta", expiresIn: 900 });
    await vi.waitFor(() => {
      expect(getSession().status).toBe("anonymous");
    });

    expect(server.callsTo("GET /auth/me")[0]?.headers.get("Authorization")).toBe("Bearer de-otra-cuenta");
  });
});

describe("correcciones de la revisión del Sprint 2", () => {
  it("M1: un refresh de red relee me y, si la cookie es de otra cuenta, cierra esta sesión sin reintentar la petición", async () => {
    const server = mockApi({
      "GET /socios": protectedReply,
      "POST /auth/refresh": REFRESH_OK,
      "GET /auth/me": { status: 200, body: { ...ME, id: "00000000-0000-4000-8000-0000000000ff", email: "otra@apex.test" } },
    });
    signIn();

    await expect(api.get("/socios")).rejects.toMatchObject({ status: 401 });

    expect(getSession()).toMatchObject({ status: "anonymous", reason: "unauthorized" });
    // La petición original nunca sale con el token de la otra cuenta.
    expect(server.callsTo("GET /socios").map(bearer)).toEqual([`Bearer ${OLD}`]);
    expect(server.callsTo("GET /auth/me")[0]?.headers.get("Authorization")).toBe(`Bearer ${NEW}`);
    expect(getAccessToken()).toBeNull();
  });

  it("M1: si me es de la misma cuenta, la sesión sigue con el token nuevo", async () => {
    const server = mockApi({ "GET /socios": protectedReply, "POST /auth/refresh": REFRESH_OK, "GET /auth/me": { status: 200, body: ME } });
    signIn();

    await api.get("/socios");

    await vi.waitFor(() => {
      expect(server.callsTo("GET /auth/me")).toHaveLength(1);
    });
    await flush();
    expect(getSession().status).toBe("authenticated");
    expect(getAccessToken()).toBe(NEW);
  });

  it("M2: updateSessionUser cambia el usuario sin descartar un refresh en vuelo", async () => {
    const gate = deferred<MockReply>();
    mockApi({ "GET /socios": protectedReply, "POST /auth/refresh": () => gate.promise });
    signIn();

    const request = api.get("/socios");
    await vi.waitFor(() => {
      expect(getAccessToken()).toBe(OLD);
    });
    await flush();
    updateSessionUser({ gymName: "Box Sur" });
    gate.resolve(REFRESH_OK);

    await expect(request).resolves.toEqual({ ok: true });
    expect(getSession().user?.gymName).toBe("Box Sur");
    expect(getAccessToken()).toBe(NEW);
  });

  it("M2: una lectura de me que salió antes de updateSessionUser no pisa el cambio", async () => {
    const gate = deferred<MockReply>();
    mockApi({ "GET /auth/me": () => gate.promise });
    setSession({ accessToken: OLD, user: testUser("admin", { id: ME.id, gymName: "Box Norte" }) });

    const pending = refreshCurrentUser();
    await flush();
    updateSessionUser({ gymName: "Box Sur" });
    gate.resolve({ status: 200, body: ME });
    await pending;

    expect(getSession().user?.gymName).toBe("Box Sur");
  });

  it("M2: una lectura de me igual al usuario no emite un usuario nuevo", async () => {
    mockApi({ "GET /auth/me": { status: 200, body: ME } });
    setSession({ accessToken: OLD, user: testUser("admin", { id: ME.id, email: ME.email, gymName: ME.gym_name }) });
    const before = getSession();

    await refreshCurrentUser();

    expect(getSession()).toBe(before);
  });

  it("M2: updateSessionUser sin sesión no hace nada", () => {
    clearSession("logout");

    updateSessionUser({ gymName: "Box Sur" });

    expect(getSession()).toEqual({ status: "anonymous", user: null, reason: "logout" });
  });

  it("L3: endSession publica logout a las demás pestañas y limpia esta", () => {
    installTabDoubles();
    uninstall?.();
    uninstall = installSessionBridge();
    signIn();

    endSession();

    expect(posted.map((m) => (m.data as { type: string }).type)).toContain("logout");
    expect(getSession()).toEqual({ status: "anonymous", user: null, reason: "logout" });
    expect(getAccessToken()).toBeNull();
  });
});
