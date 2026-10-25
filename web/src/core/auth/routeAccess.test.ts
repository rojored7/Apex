// US-053 T1, L-5 y S2-D23: acceso por ruta con la matriz de US-040, inicio por rol sin
// literales de rol y `next` sin redirecciones abiertas.
import { childRoute, fullPathOf, type RouteDef } from "../../config/routeTable";
import { REFERENCE_ROUTES } from "../../config/routes.reference";
import { ROLES, can, type Role } from "./permissions";
import { canAccess, canAccessRoute, findRoute, homeFor, safeNext } from "./routeAccess";

const concrete = (path: string): string => path.replace(":id", "42").replace(":token", "abc123");

describe("findRoute", () => {
  it("encuentra la definición por ruta concreta, con parámetros y sin query ni barra final", () => {
    // S3-F1 (E14): en la ruta de la ficha responde su hija índice ("Datos"), con el acceso del padre.
    expect(findRoute("/socios/42")).toMatchObject({ path: "", parent: "/socios/:id", access: "members.view" });
    expect(findRoute("/socios/42/editar")?.path).toBe("/socios/:id/editar");
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
  // S3-F1 (E14): la hija índice de la ficha se abre en la ruta de su padre.
  const cases = ROLES.flatMap((role) => REFERENCE_ROUTES.map((route) => [role, fullPathOf(route), route.access] as const));

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

describe("findRoute con rutas hijas (S3-F3, E3 y E14)", () => {
  const FICHA: RouteDef = { path: "/socios/:id", title: "Ficha del socio", feature: "members", access: "members.view", layout: "panel" };
  const EDITAR: RouteDef = { path: "/socios/:id/editar", title: "Editar socio", feature: "members", access: "members.update", layout: "panel" };
  const DATOS = childRoute(FICHA, "", "Datos");
  const MEMBRESIAS = childRoute(FICHA, "/socios/:id/membresias", "Membresías del socio", { access: "memberships.view" });
  const PAGOS = childRoute(FICHA, "/socios/:id/pagos", "Pagos del socio");
  // El padre va primero a propósito: la hija (más específica) gana aunque esté después.
  const TABLE: readonly RouteDef[] = [FICHA, EDITAR, DATOS, MEMBRESIAS, PAGOS];

  it("resuelve la hija nombrada y la hija índice antes que el padre", () => {
    expect(findRoute("/socios/42/membresias", TABLE)).toBe(MEMBRESIAS);
    expect(findRoute("/socios/42", TABLE)).toBe(DATOS);
    expect(findRoute("/socios/42?tab=1", TABLE)).toBe(DATOS);
  });

  it("la hija que no declara acceso hereda el del padre; la que lo declara usa el suyo", () => {
    expect(findRoute("/socios/42/pagos", TABLE)?.access).toBe("members.view");
    expect(findRoute("/socios/42/membresias", TABLE)?.access).toBe("memberships.view");
  });

  it("una ruta estática hermana sigue ganando a una dinámica y una ruta desconocida da null", () => {
    expect(findRoute("/socios/42/editar", TABLE)).toBe(EDITAR);
    expect(findRoute("/socios/42/otra", TABLE)).toBeNull();
  });

  it("sin tabla usa ROUTE_TABLE", () => {
    expect(findRoute("/membresias/vender")?.path).toBe("/membresias/vender");
  });
});

describe("revisión S3-F3 (HIGH 1): una estática raíz gana a la hija índice dinámica", () => {
  const FICHA: RouteDef = { path: "/socios/:id", title: "Ficha del socio", feature: "members", access: "members.view", layout: "panel" };
  const NUEVO: RouteDef = { path: "/socios/nuevo", title: "Nuevo socio", feature: "members", access: "members.create", layout: "panel" };
  const DATOS = childRoute(FICHA, "", "Datos");

  it("/socios/nuevo resuelve la raíz estática aunque exista la hija índice de /socios/:id", () => {
    expect(findRoute("/socios/nuevo", [FICHA, DATOS, NUEVO])).toBe(NUEVO);
    expect(findRoute("/socios/42", [FICHA, DATOS, NUEVO])).toBe(DATOS);
  });
});
