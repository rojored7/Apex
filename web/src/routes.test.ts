// US-067 T2 y US-053 T2: inventario de rutas. routeTable.ts es la única tabla (S2-D23) y
// debe coincidir con el oráculo escrito a mano desde ROUTES.md; el árbol de routes.tsx
// solo registra rutas habilitadas y cada hoja declara su acceso.
import type { RouteObject } from "react-router";
import { ENABLED_FEATURES, FEATURES } from "./config/features";
import { ROUTE_TABLE } from "./config/routeTable";
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

const strip = ({ path, feature, access, layout }: (typeof ROUTE_TABLE)[number]) => ({ path, feature, access, layout });

describe("tabla de rutas (routeTable.ts)", () => {
  it("coincide exactamente con el oráculo de ROUTES.md", () => {
    const byPath = (a: { path: string }, b: { path: string }) => a.path.localeCompare(b.path);
    expect(ROUTE_TABLE.map(strip).sort(byPath)).toEqual([...REFERENCE_ROUTES].sort(byPath));
  });

  it("no tiene rutas repetidas ni ninguna /hoy (Q25)", () => {
    const paths = ROUTE_TABLE.map((r) => r.path);
    expect(new Set(paths).size).toBe(paths.length);
    expect(paths.some((p) => p === "/hoy" || p.startsWith("/hoy/"))).toBe(false);
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

  it("en el Sprint 2 el acceso (S2-F3, S2-F4a), Inicio, Socios (S2-F6), Usuarios (S2-F4a) y Configuración (S2-F5) tienen página; las del sprint que faltan quedan pendientes", () => {
    expect(ROUTE_TABLE.filter((r) => r.load).map((r) => r.path)).toEqual([
      "/login",
      "/recuperar",
      "/restablecer/:token",
      "/cambiar-clave",
      "/",
      "/socios",
      "/socios/nuevo",
      "/sistema/usuarios",
      "/sistema/configuracion",
    ]);
    expect(ROUTE_TABLE.filter((r) => r.pending).map((r) => r.path)).toEqual(["/planes"]);
    for (const route of ROUTE_TABLE.filter((r) => r.load || r.pending)) expect(ENABLED_FEATURES.has(route.feature as never)).toBe(true);
  });
});

describe("árbol de routes.tsx", () => {
  it("con las features del Sprint 2 registra solo las rutas habilitadas con página o pendientes", () => {
    const registered = leaves(buildRoutes()).map((l) => l.path).sort();
    const expected = ROUTE_TABLE.filter((r) => (r.load || r.pending) && r.feature !== undefined && ENABLED_FEATURES.has(r.feature))
      .map((r) => r.path)
      .sort();

    expect(registered).toEqual(expected);
    expect(registered).not.toContain("/clases");
    expect(registered).not.toContain("/socios/:id");
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

  it("con todas las features habilitadas registra las rutas con página o pendientes de la tabla", () => {
    const registered = leaves(buildRoutes(ROUTE_TABLE, new Set(FEATURES))).map((l) => l.path);
    expect(registered.length).toBe(ROUTE_TABLE.filter((r) => r.load || r.pending).length);
  });

  it("termina en una ruta comodín de NotFound", () => {
    const root = buildRoutes()[0];
    expect(root?.children?.at(-1)?.path).toBe("*");
  });
});
