// US-067 T4 y US-053: el árbol de React Router sale de config/routeTable.ts (S2-D23).
// - Solo se registran las rutas habilitadas (isRouteEnabled) que tienen página (`load`, lazy);
//   las demás caen en la ruta comodín y dan "No encontrada" sin descargar su código.
// - Cada hoja lleva `handle: { feature, access, layout, title }`.
// - S3-F3 (E3, E14): una ruta con `parent` se registra bajo su padre (`children`; la hija índice,
//   de path "", con `index`) y el padre la pinta en su `<Outlet />`. Una hija sin página, o cuyo
//   padre no tiene página o no está habilitado, no se registra.
// - Zonas: acceso (públicas), /cambiar-clave (con sesión), panel, tablet del box y portal
//   (RequireAuth, luego RequireRole con zona antes del layout y RequireRole por ruta dentro) y
//   TV (pública).
// - H1 (revisión del Sprint 2): la ruta raíz lleva `errorElement` (RouteError): un chunk que
//   ya no existe tras un despliegue o una excepción al pintar muestran "Algo salió mal" con
//   "Recargar" en lugar de la pantalla técnica de React Router.
import type { ComponentType } from "react";
import { createBrowserRouter, createMemoryRouter, Outlet, type RouteObject } from "react-router";
import { ENABLED_FEATURES, isRouteEnabled, type Feature } from "./config/features";
import { ROUTE_TABLE, type RouteDef, type RouteLayout } from "./config/routeTable";
import { RequireAuth } from "./core/auth/RequireAuth";
import { RequireRole, type GuardZone } from "./core/auth/RequireRole";
import { AccessLayout } from "./layouts/AccessLayout";
import { PanelShell } from "./layouts/PanelShell";
import { GymShell, PortalShell, TvShell } from "./layouts/ZoneShells";
import { NotFound } from "./pages/NotFound";
import { RouteError } from "./pages/RouteError";
import { RouteLoading } from "./pages/RouteLoading";

export interface AppRouterOptions {
  table?: readonly RouteDef[];
  enabled?: ReadonlySet<Feature>;
  /** Con entradas se crea un router en memoria (pruebas); sin ellas, el del navegador. */
  initialEntries?: string[];
}

type PageRouteDef = RouteDef & Required<Pick<RouteDef, "load">>;

const hasPage = (def: RouteDef): def is PageRouteDef => def.load !== undefined;

function handleOf(def: PageRouteDef): Record<string, unknown> {
  return { feature: def.feature, access: def.access, layout: def.layout, title: def.title };
}

function lazyOf(def: PageRouteDef): () => Promise<{ Component: ComponentType }> {
  const { load } = def;
  return async () => {
    const module = await load();
    return { Component: module.default };
  };
}

/**
 * S3-F3 (E3, E14): una ruta con página y, debajo, sus hijas con página (la índice, de path "", con
 * `index`). El padre pinta las hijas en su `<Outlet />`. Una hija nunca queda como hoja plana.
 */
function node(def: PageRouteDef, active: readonly PageRouteDef[]): RouteObject {
  if (def.parent !== undefined && def.path === "") return { index: true, handle: handleOf(def), lazy: lazyOf(def) };
  const children = active.filter((child) => child.parent === def.path).map((child) => node(child, active));
  return {
    path: def.path,
    handle: handleOf(def),
    lazy: lazyOf(def),
    ...(children.length > 0 ? { children } : {}),
  };
}

function zone(shell: RouteObject["element"], guard: GuardZone, children: RouteObject[]): RouteObject {
  return {
    element: <RequireAuth />,
    children: [
      {
        element: <RequireRole zone={guard} />,
        // H1: un error de la página se pinta dentro del layout de la zona (el menú sigue).
        children: [{ element: shell, children: [{ element: <RequireRole />, errorElement: <RouteError inLayout />, children }] }],
      },
    ],
  };
}

/** Árbol de rutas. Exportado para la prueba de inventario. */
export function buildRoutes(table: readonly RouteDef[] = ROUTE_TABLE, enabled: ReadonlySet<Feature> = ENABLED_FEATURES): RouteObject[] {
  const active = table.filter(hasPage).filter((def) => isRouteEnabled(def, enabled));
  // Las hijas se cuelgan de su padre (node); en la zona solo van las rutas sin padre.
  const roots = active.filter((def) => def.parent === undefined);
  const of = (layout: RouteLayout, test: (def: PageRouteDef) => boolean = () => true): RouteObject[] =>
    roots.filter((def) => def.layout === layout && test(def)).map((def) => node(def, active));

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
      errorElement: <RouteError />,
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
