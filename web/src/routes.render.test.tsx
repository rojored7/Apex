// US-067 T6 y US-053 T7: el router real (createMemoryRouter) monta cada zona en su layout,
// una ruta deshabilitada da 404 sin descargar su código y no existe /hoy.
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { RouterProvider } from "react-router";
import { ENABLED_FEATURES, type Feature } from "./config/features";
import type { RouteDef } from "./config/routeTable";
import { SessionRoleProvider } from "./core/auth/SessionRole";
import { createAppRouter, type AppRouterOptions } from "./routes";
import { testQueryClient } from "./test/server";
import { signInAs, signOutForTests } from "./test/session";

function Page({ text }: { text: string }) {
  return <h1>{text}</h1>;
}

const loadSocios = vi.fn(async () => Promise.resolve({ default: () => <Page text="Lista de socios" /> }));
const loadClases = vi.fn(async () => Promise.resolve({ default: () => <Page text="Sesiones" /> }));
const loadMi = vi.fn(async () => Promise.resolve({ default: () => <Page text="Mi inicio" /> }));
const loadCheckin = vi.fn(async () => Promise.resolve({ default: () => <Page text="Lista de llegada" /> }));
const loadTv = vi.fn(async () => Promise.resolve({ default: () => <Page text="Leaderboard" /> }));

const TABLE: RouteDef[] = [
  { path: "/login", title: "Iniciar sesión", feature: "auth", access: "public", layout: "access", pending: true },
  { path: "/socios", title: "Socios", feature: "members", access: "members.view", layout: "panel", load: loadSocios },
  { path: "/clases", title: "Clases", feature: "classes", access: "classes.view", layout: "panel", load: loadClases },
  { path: "/clases/:id/checkin", title: "Check-in", feature: "classes", access: "classes.view", layout: "gym", load: loadCheckin },
  { path: "/mi", title: "Inicio", feature: "portal", access: "me.home.view", layout: "portal", load: loadMi },
  { path: "/tv", title: "TV", feature: "tv", access: "public", layout: "tv", load: loadTv },
];

function renderAt(path: string, options: AppRouterOptions = {}) {
  const router = createAppRouter({ table: TABLE, initialEntries: [path], ...options });
  render(
    // S2-F4a: el panel monta "Mi cuenta", que usa TanStack Query (como App).
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <RouterProvider router={router} />
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return router;
}

const WITH_FUTURE = new Set<Feature>([...ENABLED_FEATURES, "classes", "portal", "tv"]);

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  signOutForTests();
  delete document.documentElement.dataset.theme;
});

describe("router de la app", () => {
  it("/socios carga su página dentro de PanelLayout", async () => {
    signInAs("coach");
    renderAt("/socios");

    const main = await screen.findByRole("main");
    expect(await within(main).findByRole("heading", { name: "Lista de socios" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Menú principal" })).toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent("coach@apex.test · Coach");
    expect(loadSocios).toHaveBeenCalledTimes(1);
  });

  it("/clases con classes deshabilitada da No encontrada y su import no se ejecuta", async () => {
    signInAs("admin");
    renderAt("/clases");

    expect(await screen.findByRole("heading", { level: 1, name: "No encontrada" })).toBeInTheDocument();
    expect(loadClases).not.toHaveBeenCalled();
  });

  it("/hoy da No encontrada", async () => {
    signInAs("admin");
    renderAt("/hoy");

    expect(await screen.findByRole("heading", { level: 1, name: "No encontrada" })).toBeInTheDocument();
  });

  it("una ruta pendiente muestra Disponible pronto con su título", async () => {
    signOutForTests();
    renderAt("/login");

    expect(await screen.findByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeInTheDocument();
    expect(screen.getByText(/disponible pronto/i)).toBeInTheDocument();
  });

  it("la tablet del box monta GymLayout con el título de la ruta", async () => {
    signInAs("coach");
    renderAt("/clases/7/checkin", { enabled: WITH_FUTURE });

    expect(await screen.findByRole("heading", { name: "Lista de llegada" })).toBeInTheDocument();
    expect(within(screen.getByRole("banner")).getByRole("heading", { level: 1, name: "Check-in" })).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("el portal monta PortalLayout para el socio", async () => {
    signInAs("member");
    renderAt("/mi", { enabled: WITH_FUTURE });

    expect(await screen.findByRole("heading", { name: "Mi inicio" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Menú del portal" })).toBeInTheDocument();
  });

  it("/tv es pública y monta TvLayout", async () => {
    signOutForTests();
    renderAt("/tv", { enabled: WITH_FUTURE });

    expect(await screen.findByRole("heading", { name: "Leaderboard" })).toBeInTheDocument();
    expect(screen.getByTestId("tv-stage")).toBeInTheDocument();
  });
});
