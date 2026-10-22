// US-067 T4 y US-053: el árbol de React Router sale de config/routeTable.ts (S2-D23).
// - Solo se registran las rutas habilitadas (isRouteEnabled) que tienen página (`load`, lazy)
//   o están pendientes en este sprint; las demás caen en la ruta comodín y dan "No encontrada"
//   sin descargar su código.
// - Cada hoja lleva `handle: { feature, access, layout, title }`.
// - Zonas: acceso (públicas), /cambiar-clave (con sesión), panel, tablet del box y portal
//   (RequireAuth, luego RequireRole con zona antes del layout y RequireRole por ruta dentro) y
//   TV (pública).
import { createBrowserRouter, createMemoryRouter, Outlet, type RouteObject } from "react-router";
import { ENABLED_FEATURES, isRouteEnabled, type Feature } from "./config/features";
import { ROUTE_TABLE, type RouteDef, type RouteLayout } from "./config/routeTable";
import { RequireAuth } from "./core/auth/RequireAuth";
import { RequireRole, type GuardZone } from "./core/auth/RequireRole";
import { AccessLayout } from "./layouts/AccessLayout";
import { PanelShell } from "./layouts/PanelShell";
import { GymShell, PortalShell, TvShell } from "./layouts/ZoneShells";
import { NotFound } from "./pages/NotFound";
import { PendingPage } from "./pages/PendingPage";
import { RouteLoading } from "./pages/RouteLoading";

export interface AppRouterOptions {
  table?: readonly RouteDef[];
  enabled?: ReadonlySet<Feature>;
  /** Con entradas se crea un router en memoria (pruebas); sin ellas, el del navegador. */
  initialEntries?: string[];
}

function leaf(def: RouteDef): RouteObject {
  const handle = { feature: def.feature, access: def.access, layout: def.layout, title: def.title };
  const { load } = def;
  if (load) {
    return {
      path: def.path,
      handle,
      lazy: async () => {
        const module = await load();
        return { Component: module.default };
      },
    };
  }
  return { path: def.path, handle, element: <PendingPage title={def.title} /> };
}

function zone(shell: RouteObject["element"], guard: GuardZone, children: RouteObject[]): RouteObject {
  return {
    element: <RequireAuth />,
    children: [{ element: <RequireRole zone={guard} />, children: [{ element: shell, children: [{ element: <RequireRole />, children }] }] }],
  };
}

/** Árbol de rutas. Exportado para la prueba de inventario. */
export function buildRoutes(table: readonly RouteDef[] = ROUTE_TABLE, enabled: ReadonlySet<Feature> = ENABLED_FEATURES): RouteObject[] {
  const active = table.filter((def) => isRouteEnabled(def, enabled) && (def.load !== undefined || def.pending === true));
  const of = (layout: RouteLayout, test: (def: RouteDef) => boolean = () => true): RouteObject[] =>
    active.filter((def) => def.layout === layout && test(def)).map(leaf);

  const groups: RouteObject[] = [];
  const add = (children: RouteObject[], build: (c: RouteObject[]) => RouteObject): void => {
    if (children.length > 0) groups.push(build(children));
  };

  add(of("access", (d) => d.access === "public"), (children) => ({ element: <AccessLayout />, children }));
  add(of("access", (d) => d.access !== "public"), (children) => ({
    element: <RequireAuth />,
    children: [{ element: <AccessLayout />, children }],
  }));
  add(of("panel"), (children) => zone(<PanelShell />, "panel", children));
  add(of("gym"), (children) => zone(<GymShell />, "panel", children));
  add(of("portal"), (children) => zone(<PortalShell />, "portal", children));
  add(of("tv"), (children) => ({ element: <TvShell />, children }));

  return [
    {
      element: <Outlet />,
      // La primera página diferida todavía no llegó: se muestra un estado de carga.
      hydrateFallbackElement: <RouteLoading />,
      children: [...groups, { path: "*", element: <NotFound /> }],
    },
  ];
}

export function createAppRouter(options: AppRouterOptions = {}) {
  const routes = buildRoutes(options.table, options.enabled);
  return options.initialEntries ? createMemoryRouter(routes, { initialEntries: options.initialEntries }) : createBrowserRouter(routes);
}

export type AppRouter = ReturnType<typeof createAppRouter>;
