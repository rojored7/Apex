// US-053 T5 y T7 (criterios 3, 4 y 6): el coach ve "Sin permiso" en /planes y no ve esas
// entradas en el menú; member en el panel va a /mi; admin o coach en /mi van a /; un 403 del
// api se muestra en la página sin cerrar la sesión.
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { RouterProvider } from "react-router";
import { ENABLED_FEATURES, type Feature } from "../../config/features";
import type { RouteDef } from "../../config/routeTable";
import { createAppRouter } from "../../routes";
import { mockApi, testQueryClient } from "../../test/server";
import { signInAs, signOutForTests } from "../../test/session";
import { api } from "../api/client";
import type { ApiError } from "../api/errors";
import { getSession } from "./session";
import { SessionRoleProvider } from "./SessionRole";

function Page({ text }: { text: string }) {
  return <h1>{text}</h1>;
}

function PlanesQueLlamanAlApi() {
  const query = useQuery({ queryKey: ["plans"], queryFn: () => api.get<unknown>("/plans") });
  return (
    <>
      <h1>Planes</h1>
      {query.isError && <p role="alert">{(query.error as ApiError).message}</p>}
    </>
  );
}

const page = (text: string) => async () => Promise.resolve({ default: () => <Page text={text} /> });

const TABLE: RouteDef[] = [
  { path: "/", title: "Inicio", feature: "dashboard", access: "dashboard.view", layout: "panel", load: page("Inicio") },
  { path: "/socios", title: "Socios", feature: "members", access: "members.view", layout: "panel", load: page("Socios") },
  { path: "/planes", title: "Planes", feature: "plans", access: "plans.view", layout: "panel", load: page("Planes") },
  { path: "/sistema/configuracion", title: "Configuración", feature: "settings", access: "settings.manage", layout: "panel", load: page("Configuración") },
  { path: "/mi", title: "Inicio", feature: "portal", access: "me.home.view", layout: "portal", load: page("Mi inicio") },
];

const ENABLED = new Set<Feature>([...ENABLED_FEATURES, "portal"]);

function renderAt(path: string, table: RouteDef[] = TABLE) {
  const router = createAppRouter({ table, enabled: ENABLED, initialEntries: [path] });
  render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <RouterProvider router={router} />
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return router;
}

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("RequireRole", () => {
  it.each(["/planes", "/sistema/configuracion"])("un coach que abre %s ve Sin permiso y el menú no muestra Planes ni Sistema", async (path) => {
    signInAs("coach");
    renderAt(path);

    expect(await screen.findByRole("heading", { level: 1, name: "Sin permiso" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir al inicio" })).toHaveAttribute("href", "/");
    const nav = screen.getByRole("navigation", { name: "Menú principal" });
    expect(within(nav).queryByRole("link", { name: "Planes" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Configuración" })).not.toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Socios" })).toBeInTheDocument();
  });

  it("el admin entra a /planes y ve Planes y Sistema en el menú", async () => {
    signInAs("admin");
    renderAt("/planes");

    expect(await screen.findByRole("heading", { level: 1, name: "Planes" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Menú principal" });
    expect(within(nav).getByRole("link", { name: "Planes" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Configuración" })).toBeInTheDocument();
  });

  it("un member que abre una ruta del panel va a /mi", async () => {
    signInAs("member");
    const router = renderAt("/socios");

    expect(await screen.findByRole("heading", { name: "Mi inicio" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/mi");
  });

  it.each(["admin", "coach"] as const)("%s que abre /mi va a /", async (role) => {
    signInAs(role);
    const router = renderAt("/mi");

    expect(await screen.findByRole("heading", { name: "Inicio" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });

  it("un 403 del api se muestra en la página y la sesión sigue", async () => {
    mockApi({ "GET /plans": { status: 403, body: { error: { code: "forbidden", message: "No tienes permiso para esta acción." } } } });
    signInAs("admin");
    renderAt("/planes", [
      ...TABLE.filter((r) => r.path !== "/planes"),
      {
        path: "/planes",
        title: "Planes",
        feature: "plans",
        access: "plans.view",
        layout: "panel",
        load: async () => Promise.resolve({ default: PlanesQueLlamanAlApi }),
      },
    ]);

    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para esta acción.");
    expect(getSession().status).toBe("authenticated");
    expect(screen.getByRole("heading", { level: 1, name: "Planes" })).toBeInTheDocument();
  });
});
