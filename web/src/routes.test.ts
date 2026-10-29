// US-067 T2 y US-053 T2: inventario de rutas. routeTable.ts es la única tabla (S2-D23) y
// debe coincidir con el oráculo escrito a mano desde ROUTES.md; el árbol de routes.tsx
// solo registra rutas habilitadas y cada hoja declara su acceso.
// S3-F3 (E3, E14): rutas hijas. Una hija se registra bajo su padre (`children`, la índice con
// `index`), nunca como hoja plana; hereda feature y layout (y el acceso si no declara uno); la
// clave de una ruta es (parent, path) y el oráculo compara también el anidamiento.
// S3-F1: /socios/:id (con su hija índice "Datos") y /socios/:id/editar se registran con página.
// S3-F7: /socios/:id/membresias y /socios/:id/pagos son hijas con su feature (memberships, payments).
import type { RouteObject } from "react-router";
import { ENABLED_FEATURES, FEATURES, type Feature } from "./config/features";
import { childRoute, fullPathOf, ROUTE_TABLE, routeKey, type RouteDef } from "./config/routeTable";
import { REFERENCE_ROUTES } from "./config/routes.reference";
import { ACTIONS } from "./core/auth/permissions";
import { buildRoutes } from "./routes";

interface Leaf {
  path: string;
  handle: unknown;
  lazy: boolean;
}

function leaves(routes: RouteObject[], out: Leaf[] = []): Leaf[] {
  for (const route of routes) {
    if (route.path !== undefined && route.path !== "*") out.push({ path: route.path, handle: route.handle, lazy: route.lazy !== undefined });
    if (route.children) leaves(route.children, out);
  }
  return out;
}

const strip = ({ path, feature, access, layout, parent }: (typeof ROUTE_TABLE)[number]) => ({ path, feature, access, layout, parent });
const byKey = (a: { path: string; parent?: string | undefined }, b: { path: string; parent?: string | undefined }) => routeKey(a).localeCompare(routeKey(b));

describe("tabla de rutas (routeTable.ts)", () => {
  it("coincide exactamente con el oráculo de ROUTES.md, anidamiento incluido", () => {
    expect(ROUTE_TABLE.map(strip).sort(byKey)).toEqual([...REFERENCE_ROUTES].sort(byKey));
  });

  it("no tiene rutas repetidas por (parent, path) ni ninguna /hoy (Q25)", () => {
    const keys = ROUTE_TABLE.map(routeKey);
    expect(new Set(keys).size).toBe(keys.length);
    const paths = ROUTE_TABLE.map(fullPathOf);
    expect(paths.some((p) => p === "/hoy" || p.startsWith("/hoy/"))).toBe(false);
  });

  it("todo padre declarado existe en la tabla", () => {
    const paths = new Set(ROUTE_TABLE.filter((r) => r.parent === undefined).map((r) => r.path));
    for (const route of ROUTE_TABLE) if (route.parent !== undefined) expect(paths.has(route.parent), route.path).toBe(true);
  });

  it("cada acceso es public, session o una acción de la matriz", () => {
    for (const route of ROUTE_TABLE) {
      expect(route.access === "public" || route.access === "session" || ACTIONS.includes(route.access)).toBe(true);
    }
  });

  it("los parámetros usan los nombres de ROUTES.md", () => {
    const params = ROUTE_TABLE.flatMap((r) => r.path.match(/:[a-z]+/g) ?? []);
    expect(new Set(params)).toEqual(new Set([":id", ":token"]));
  });

  it("/mi/* usa PortalLayout, las de tablet GymLayout, /tv TvLayout y el resto del panel PanelLayout", () => {
    for (const route of ROUTE_TABLE) {
      if (route.path === "/mi" || route.path.startsWith("/mi/")) expect(route.layout).toBe("portal");
      else if (/\/(checkin|resultados)$/.test(route.path)) expect(route.layout).toBe("gym");
      else if (route.path === "/tv") expect(route.layout).toBe("tv");
      else if (route.access === "public" || route.access === "session") expect(route.layout).toBe("access");
      else expect(route.layout).toBe("panel");
    }
  });

  it("tienen página el acceso (S2-F3, S2-F4a), Inicio, Socios (S2-F6), la ficha con sus pestañas Datos (S3-F1), Membresías y Pagos (S3-F7) y la edición (S3-F1), Planes (S2-F7), Membresías (S3-F5), Vender (S3-F3), Pagos (S3-F6), Usuarios (S2-F4a), Auditoría (S4A-F1) y Configuración (S2-F5)", () => {
    expect(ROUTE_TABLE.filter((r) => r.load).map(fullPathOf)).toEqual([
      "/login",
      "/recuperar",
      "/restablecer/:token",
      "/cambiar-clave",
      "/",
      "/socios",
      "/socios/nuevo",
      "/socios/:id",
      "/socios/:id",
      "/socios/:id/membresias",
      "/socios/:id/pagos",
      "/socios/:id/editar",
      "/planes",
      "/membresias",
      "/membresias/vender",
      "/pagos",
      "/sistema/usuarios",
      "/sistema/auditoria",
      "/sistema/configuracion",
    ]);
    for (const route of ROUTE_TABLE.filter((r) => r.load)) expect(ENABLED_FEATURES.has(route.feature as never)).toBe(true);
  });
});

describe("árbol de routes.tsx", () => {
  /** La hija índice (path "") no es una hoja con path: cuelga de su padre con `index`. */
  const isIndexChild = (r: RouteDef): boolean => r.parent !== undefined && r.path === "";

  it("con las features habilitadas registra solo las rutas habilitadas con página, la ficha incluida (S3-F1)", () => {
    const registered = leaves(buildRoutes()).map((l) => l.path).sort();
    const expected = ROUTE_TABLE.filter((r) => r.load && r.feature !== undefined && ENABLED_FEATURES.has(r.feature) && !isIndexChild(r))
      .map((r) => r.path)
      .sort();

    expect(registered).toEqual(expected);
    expect(registered).not.toContain("/clases");
    // S3-F1: la aserción del Sprint 2 ("/socios/:id no se registra") se invierte.
    expect(registered).toContain("/socios/:id");
    expect(registered).toContain("/socios/:id/editar");
  });

  it("S3-F1 (E3, E14): la ficha lleva la pestaña Datos como hija índice con página; la edición es otra pantalla, no una hija", () => {
    const find = (routes: RouteObject[], test: (r: RouteObject) => boolean): RouteObject | undefined => {
      for (const r of routes) {
        if (test(r)) return r;
        const inner = r.children ? find(r.children, test) : undefined;
        if (inner) return inner;
      }
      return undefined;
    };
    const routes = buildRoutes();
    const ficha = find(routes, (r) => r.path === "/socios/:id");

    expect(ficha?.lazy).toBeDefined();
    // S3-F7: Membresías y Pagos se suman como hijas con nombre después de la índice.
    expect(ficha?.children?.map((c) => (c.index ? "index" : c.path))).toEqual(["index", "/socios/:id/membresias", "/socios/:id/pagos"]);
    expect(ficha?.children?.[0]?.handle).toEqual({ feature: "members", access: "members.view", layout: "panel", title: "Datos" });
    const editar = find(routes, (r) => r.path === "/socios/:id/editar");
    expect(editar?.handle).toEqual({ feature: "members", access: "members.update", layout: "panel", title: "Editar socio" });
    expect(ficha?.children?.some((c) => c.path === "/socios/:id/editar")).toBe(false);
  });

  it("cada hoja declara feature, access y layout en handle", () => {
    for (const leaf of leaves(buildRoutes())) {
      const handle = (leaf.handle ?? {}) as Record<string, unknown>;
      for (const key of ["access", "layout", "feature", "title"]) expect(typeof handle[key], `${leaf.path} ${key}`).toBe("string");
    }
  });

  it("una página con load se carga de forma diferida (lazy)", () => {
    const inicio = leaves(buildRoutes()).find((l) => l.path === "/");
    expect(inicio?.lazy).toBe(true);
  });

  it("con todas las features habilitadas registra las rutas con página de la tabla", () => {
    const registered = leaves(buildRoutes(ROUTE_TABLE, new Set(FEATURES))).map((l) => l.path);
    expect(registered.length).toBe(ROUTE_TABLE.filter((r) => r.load && !isIndexChild(r)).length);
  });

  it("termina en una ruta comodín de NotFound", () => {
    const root = buildRoutes()[0];
    expect(root?.children?.at(-1)?.path).toBe("*");
  });
});

describe("rutas hijas (S3-F3, E3 y E14) con una tabla de prueba", () => {
  const page = (text: string) => vi.fn(async () => Promise.resolve({ default: () => text }));
  const FICHA: RouteDef = { path: "/socios/:id", title: "Ficha del socio", feature: "members", access: "members.view", layout: "panel", load: page("Ficha") };
  const DATOS = childRoute(FICHA, "", "Datos", { load: page("Datos") });
  const MEMBRESIAS = childRoute(FICHA, "/socios/:id/membresias", "Membresías del socio", { access: "memberships.view", load: page("Membresías") });
  const PAGOS = childRoute(FICHA, "/socios/:id/pagos", "Pagos del socio");
  const SIN_PADRE: RouteDef = { path: "/wods/:id", title: "WOD", feature: "wods", access: "wods.view", layout: "panel" };
  const HUERFANA = childRoute(SIN_PADRE, "/wods/:id/resultados", "Resultados del WOD", { load: page("Resultados") });
  const LISTA: RouteDef = { path: "/socios", title: "Socios", feature: "members", access: "members.view", layout: "panel", load: page("Lista") };
  const TABLE: readonly RouteDef[] = [LISTA, FICHA, DATOS, MEMBRESIAS, PAGOS, SIN_PADRE, HUERFANA];
  const ALL: ReadonlySet<Feature> = new Set(FEATURES);

  function find(routes: RouteObject[], test: (r: RouteObject) => boolean): RouteObject | undefined {
    for (const route of routes) {
      if (test(route)) return route;
      const inner = route.children ? find(route.children, test) : undefined;
      if (inner) return inner;
    }
    return undefined;
  }

  it("childRoute hereda feature y layout del padre, el acceso si no declara uno y guarda el padre", () => {
    expect(PAGOS).toMatchObject({ path: "/socios/:id/pagos", feature: "members", layout: "panel", access: "members.view", parent: "/socios/:id" });
    expect(MEMBRESIAS.access).toBe("memberships.view");
    expect(DATOS).toMatchObject({ path: "", parent: "/socios/:id" });
    expect(Object.isFrozen(DATOS)).toBe(true);
  });

  it("la clave (parent, path) distingue la hija índice de su padre y fullPathOf da la ruta que abre", () => {
    expect(routeKey(DATOS)).not.toBe(routeKey(FICHA));
    expect(new Set(TABLE.map(routeKey)).size).toBe(TABLE.length);
    expect(fullPathOf(DATOS)).toBe("/socios/:id");
    expect(fullPathOf(MEMBRESIAS)).toBe("/socios/:id/membresias");
    expect(fullPathOf(FICHA)).toBe("/socios/:id");
  });

  it("una hija con load aparece bajo su padre (la índice con index) y no como hoja plana", () => {
    const routes = buildRoutes(TABLE, ALL);
    const ficha = find(routes, (r) => r.path === "/socios/:id");

    expect(ficha?.children?.map((c) => (c.index ? "index" : c.path))).toEqual(["index", "/socios/:id/membresias"]);
    const index = ficha?.children?.[0];
    expect(index?.index).toBe(true);
    expect(index?.lazy).toBeDefined();
    expect(index?.handle).toEqual({ feature: "members", access: "members.view", layout: "panel", title: "Datos" });
    const panelChildren = find(routes, (r) => (r.children ?? []).some((c) => c.path === "/socios"))?.children ?? [];
    expect(panelChildren.map((c) => c.path)).toEqual(["/socios", "/socios/:id"]);
  });

  it("una hija sin load no se registra, ni una hija cuyo padre no tiene página", () => {
    const paths = leaves(buildRoutes(TABLE, ALL)).map((l) => l.path);

    expect(paths).not.toContain("/socios/:id/pagos");
    expect(paths).not.toContain("/wods/:id/resultados");
    expect(paths).not.toContain("/wods/:id");
  });

  it("la hija hereda la feature: con members deshabilitada no se registra ni el padre ni sus hijas", () => {
    const routes = buildRoutes(TABLE, new Set<Feature>(["auth", "dashboard"]));

    expect(find(routes, (r) => r.path === "/socios/:id" || r.path === "/socios/:id/membresias" || r.index === true)).toBeUndefined();
  });

  it("el oráculo compara también el padre: una hija sin parent en el oráculo no coincide", () => {
    const table = [FICHA, MEMBRESIAS].map(strip);
    const oracle = [
      { path: "/socios/:id", feature: "members", access: "members.view", layout: "panel" },
      { path: "/socios/:id/membresias", feature: "members", access: "memberships.view", layout: "panel" },
    ];

    expect(table).not.toEqual(oracle);
    expect(table).toEqual([oracle[0], { ...oracle[1], parent: "/socios/:id" }]);
  });
});

describe("pestañas Membresías y Pagos de la ficha (S3-F7, S3-D65, E3)", () => {
  function find(routes: RouteObject[], test: (r: RouteObject) => boolean): RouteObject | undefined {
    for (const route of routes) {
      if (test(route)) return route;
      const inner = route.children ? find(route.children, test) : undefined;
      if (inner) return inner;
    }
    return undefined;
  }
  const fichaChildren = (enabled: ReadonlySet<Feature>): RouteObject[] => find(buildRoutes(ROUTE_TABLE, enabled), (r) => r.path === "/socios/:id")?.children ?? [];

  it("son hijas de /socios/:id con su feature, su acceso y su página diferida", () => {
    const children = ROUTE_TABLE.filter((r) => r.parent === "/socios/:id" && r.path !== "");

    expect(children.map(strip)).toEqual([
      { path: "/socios/:id/membresias", feature: "memberships", access: "memberships.view", layout: "panel", parent: "/socios/:id" },
      { path: "/socios/:id/pagos", feature: "payments", access: "payments.view", layout: "panel", parent: "/socios/:id" },
    ]);
    for (const child of children) expect(child.load).toBeDefined();
    const [membresias, pagos] = fichaChildren(ENABLED_FEATURES).slice(1);
    expect(membresias?.handle).toEqual({ feature: "memberships", access: "memberships.view", layout: "panel", title: "Membresías del socio" });
    expect(pagos?.handle).toEqual({ feature: "payments", access: "payments.view", layout: "panel", title: "Pagos del socio" });
    expect(membresias?.lazy).toBeDefined();
  });

  it("una hija cuya feature no está habilitada no se registra; el padre y las demás sí", () => {
    const withoutPayments = new Set<Feature>([...ENABLED_FEATURES].filter((f) => f !== "payments"));
    const withoutMemberships = new Set<Feature>([...ENABLED_FEATURES].filter((f) => f !== "memberships"));

    expect(fichaChildren(withoutPayments).map((c) => (c.index ? "index" : c.path))).toEqual(["index", "/socios/:id/membresias"]);
    expect(fichaChildren(withoutMemberships).map((c) => (c.index ? "index" : c.path))).toEqual(["index", "/socios/:id/pagos"]);
    expect(leaves(buildRoutes(ROUTE_TABLE, withoutPayments)).map((l) => l.path)).not.toContain("/socios/:id/pagos");
  });

  it("childRoute toma la feature propia de la hija y sin ella hereda la del padre", () => {
    const parent: RouteDef = { path: "/socios/:id", title: "Ficha", feature: "members", access: "members.view", layout: "panel" };

    expect(childRoute(parent, "/socios/:id/pagos", "Pagos", { feature: "payments" }).feature).toBe("payments");
    expect(childRoute(parent, "/socios/:id/x", "X").feature).toBe("members");
  });
});
