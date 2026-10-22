// US-053 T1, L-5 y S2-D23: acceso por ruta con la matriz de US-040, inicio por rol sin
// literales de rol y `next` sin redirecciones abiertas.
import { REFERENCE_ROUTES } from "../../config/routes.reference";
import { ROLES, can, type Role } from "./permissions";
import { canAccess, canAccessRoute, findRoute, homeFor, safeNext } from "./routeAccess";

const concrete = (path: string): string => path.replace(":id", "42").replace(":token", "abc123");

describe("findRoute", () => {
  it("encuentra la definición por ruta concreta, con parámetros y sin query ni barra final", () => {
    expect(findRoute("/socios/42")?.path).toBe("/socios/:id");
    expect(findRoute("/socios/nuevo")?.path).toBe("/socios/nuevo");
    expect(findRoute("/clases?dia=hoy")?.path).toBe("/clases");
    expect(findRoute("/clases/asistencia")?.path).toBe("/clases/asistencia");
    expect(findRoute("/planes/")?.path).toBe("/planes");
    expect(findRoute("/no-existe")).toBeNull();
    expect(findRoute("/hoy")).toBeNull();
  });
});

describe("canAccess", () => {
  it("public siempre; session con cualquier rol; una acción según la matriz", () => {
    expect(canAccess(null, "public")).toBe(true);
    expect(canAccess(null, "session")).toBe(false);
    for (const role of ROLES) expect(canAccess(role, "session")).toBe(true);
    expect(canAccess("coach", "plans.view")).toBe(false);
    expect(canAccess("admin", "plans.view")).toBe(true);
  });
});

describe("canAccessRoute", () => {
  const cases = ROLES.flatMap((role) => REFERENCE_ROUTES.map((route) => [role, route.path, route.access] as const));

  it.each(cases)("%s en %s sigue la matriz (%s)", (role, path, access) => {
    const expected = access === "public" || access === "session" ? true : can(role, access);
    expect(canAccessRoute(role, concrete(path))).toBe(expected);
  });

  it("el coach no entra a /planes ni a /sistema/*; el admin sí", () => {
    for (const path of ["/planes", "/sistema/usuarios", "/sistema/auditoria", "/sistema/llaves", "/sistema/configuracion"]) {
      expect(canAccessRoute("coach", path)).toBe(false);
      expect(canAccessRoute("admin", path)).toBe(true);
    }
  });

  it("member solo entra a /mi/* y a las públicas", () => {
    expect(canAccessRoute("member", "/mi")).toBe(true);
    expect(canAccessRoute("member", "/mi/pagos")).toBe(true);
    expect(canAccessRoute("member", "/socios")).toBe(false);
    expect(canAccessRoute("member", "/")).toBe(false);
    expect(canAccessRoute("admin", "/mi")).toBe(false);
  });

  it("sin rol solo las públicas; una ruta desconocida nunca", () => {
    expect(canAccessRoute(null, "/login")).toBe(true);
    expect(canAccessRoute(null, "/tv")).toBe(true);
    expect(canAccessRoute(null, "/socios")).toBe(false);
    expect(canAccessRoute(null, "/cambiar-clave")).toBe(false);
    expect(canAccessRoute("admin", "/no-existe")).toBe(false);
  });
});

describe("homeFor", () => {
  it.each<[Role | null, string]>([
    ["admin", "/"],
    ["coach", "/"],
    ["member", "/mi"],
    [null, "/login"],
  ])("%s va a %s", (role, home) => {
    expect(homeFor(role)).toBe(home);
  });
});

describe("safeNext", () => {
  it("acepta una ruta interna permitida, con query y hash", () => {
    expect(safeNext("/socios", "coach")).toBe("/socios");
    expect(safeNext("/socios?status=deleted&limit=50", "admin")).toBe("/socios?status=deleted&limit=50");
    expect(safeNext("/socios/42#historial", "coach")).toBe("/socios/42#historial");
  });

  it.each([
    "//evil.com",
    "//evil.com/socios",
    "/\\evil.com",
    "\\\\evil.com",
    "/\t/evil.com",
    "/socios\n",
    "/\u0000socios",
    "https://x",
    "https://evil.com/socios",
    "javascript:alert(1)",
    "socios",
    "",
    "/%2F%2Fevil.com",
  ])("rechaza %j", (next) => {
    expect(safeNext(next, "admin")).toBeNull();
  });

  it("rechaza una ruta de otro rol y una pública", () => {
    expect(safeNext("/planes", "coach")).toBeNull();
    expect(safeNext("/sistema/usuarios", "coach")).toBeNull();
    expect(safeNext("/mi", "admin")).toBeNull();
    expect(safeNext("/socios", "member")).toBeNull();
    expect(safeNext("/login", "admin")).toBeNull();
    expect(safeNext("/tv", "admin")).toBeNull();
  });

  it("sin valor o sin rol devuelve null", () => {
    expect(safeNext(null, "admin")).toBeNull();
    expect(safeNext(undefined, "admin")).toBeNull();
    expect(safeNext("/socios", null)).toBeNull();
    expect(safeNext(`/${"a".repeat(3000)}`, "admin")).toBeNull();
  });
});
