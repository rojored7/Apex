// S2-F4a · US-046 (front): /sistema/usuarios (Usuarios.html).
// - PageHeader con el total y "Nuevo usuario del equipo"; FilterBar con búsqueda, rol y estado;
//   DataTable con correo, rol, StatusTag de cuenta, último acceso en hora de Bogotá y sesiones
//   abiertas; Pagination; estados de carga, vacío, error y sin permiso.
// - S2-D41 (M-8): la búsqueda va al api con debounce y vive en estado local: nunca en la URL.
//   En la URL quedan solo los filtros (rol y estado), limit y offset.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { axe } from "vitest-axe";
import { mockApi, setViewportWidth, testQueryClient, type MockHandler, type RecordedCall } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import UsersPage from "./UsersPage";

interface Row {
  id: string;
  email: string;
  role: "admin" | "coach" | "member";
  status: "active" | "pending_activation" | "locked" | "inactive" | "deleted";
  member_id: string | null;
  last_login_at: string | null;
  created_at: string;
  active_sessions: number;
}

const ROWS: Row[] = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    email: "ana@apex.test",
    role: "admin",
    status: "active",
    member_id: null,
    last_login_at: "2026-10-21T19:30:00Z",
    created_at: "2026-10-01T12:00:00Z",
    active_sessions: 2,
  },
  {
    id: "22222222-2222-4222-8222-222222222222",
    email: "carlos@apex.test",
    role: "coach",
    status: "pending_activation",
    member_id: null,
    last_login_at: null,
    created_at: "2026-10-20T12:00:00Z",
    active_sessions: 0,
  },
  {
    id: "33333333-3333-4333-8333-333333333333",
    email: "luis@apex.test",
    role: "coach",
    status: "locked",
    member_id: null,
    last_login_at: "2026-08-12T23:10:00Z",
    created_at: "2026-08-01T12:00:00Z",
    active_sessions: 0,
  },
];

function pageOf(call: RecordedCall, rows: Row[] = ROWS, total = rows.length) {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items: rows, total, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) } };
}

function renderUsers(entry = "/sistema/usuarios", handlers: Record<string, MockHandler> = {}) {
  const mock = mockApi({ "GET /users": (call) => pageOf(call), ...handlers });
  const router = createMemoryRouter(
    [
      {
        path: "/sistema/usuarios",
        element: (
          <>
            <nav aria-label="Menú principal">
              <a href="/">Inicio</a>
            </nav>
            <main>
              <UsersPage />
            </main>
          </>
        ),
      },
    ],
    { initialEntries: [entry] },
  );
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { mock, router, user: userEvent.setup(), ...view };
}

const listCalls = (mock: ReturnType<typeof renderUsers>["mock"]) => mock.callsTo("GET /users").map((c) => new URL(c.url, "http://apex.test").searchParams);
const search = (router: ReturnType<typeof renderUsers>["router"]) => router.state.location.search;
const table = () => screen.getByRole("table", { name: "Usuarios" });

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("UsersPage · estructura (Usuarios.html)", () => {
  it("muestra el título con el total, la acción de alta, los filtros y la tabla", async () => {
    renderUsers();

    expect(screen.getByRole("heading", { level: 1, name: /Usuarios del sistema/ })).toBeInTheDocument();
    expect(await screen.findByText("3 en total")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nuevo usuario del equipo" })).toBeInTheDocument();
    const filters = screen.getByRole("search");
    expect(within(filters).getByRole("searchbox", { name: "Buscar" })).toHaveAttribute("placeholder", "Correo");
    expect(within(filters).getByRole("combobox", { name: "Rol" })).toBeInTheDocument();
    expect(within(filters).getByRole("combobox", { name: "Estado" })).toBeInTheDocument();
    expect(within(table()).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Correo", "Rol", "Estado", "Último acceso", "Sesiones abiertas", "Acción"]);
  });

  it("cada fila trae correo como enlace, rol, estado con texto, último acceso en Bogotá y sesiones", async () => {
    renderUsers();

    const link = await screen.findByRole("link", { name: "ana@apex.test" });
    expect(link).toHaveAttribute("href", "/sistema/usuarios?usuario=11111111-1111-4111-8111-111111111111");
    const [, ana, carlos, luis] = within(table()).getAllByRole("row");
    expect(within(ana as HTMLElement).getAllByRole("cell").slice(0, 5).map((c) => c.textContent)).toEqual(["ana@apex.test", "Admin", "Activo", "21 oct 2026, 2:30 p. m.", "2"]);
    expect(within(carlos as HTMLElement).getAllByRole("cell").slice(0, 5).map((c) => c.textContent)).toEqual(["carlos@apex.test", "Coach", "Pendiente de activación", "Nunca", "0"]);
    expect(within(luis as HTMLElement).getByText("Bloqueado")).toHaveAttribute("data-account", "locked");
    expect(within(luis as HTMLElement).getByText("12 ago 2026, 6:10 p. m.")).toBeInTheDocument();
  });

  it("la primera petición pide la primera página de 25 sin búsqueda ni filtros", async () => {
    const { mock } = renderUsers();
    await screen.findByRole("link", { name: "ana@apex.test" });

    const [params] = listCalls(mock);
    expect(params?.toString()).toBe("limit=25&offset=0");
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderUsers();
    await screen.findByRole("link", { name: "ana@apex.test" });

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("UsersPage · búsqueda local (S2-D41)", () => {
  it("espera a que dejes de escribir, envía q al api y nunca la escribe en la URL", async () => {
    const { mock, router, user } = renderUsers();
    await screen.findByRole("link", { name: "ana@apex.test" });

    await user.type(screen.getByRole("searchbox", { name: "Buscar" }), "ana");

    await waitFor(() => {
      expect(listCalls(mock).some((p) => p.get("q") === "ana")).toBe(true);
    });
    expect(listCalls(mock).filter((p) => p.has("q")).map((p) => p.get("q"))).toEqual(["ana"]);
    expect(search(router)).not.toContain("q=");
    expect(search(router)).not.toContain("ana");
  });

  it("buscar desde la página 2 vuelve a la primera", async () => {
    const { mock, router, user } = renderUsers("/sistema/usuarios?offset=25", { "GET /users": (call) => pageOf(call, ROWS, 60) });
    await screen.findByRole("link", { name: "ana@apex.test" });

    await user.type(screen.getByRole("searchbox", { name: "Buscar" }), "luis");

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=0&q=luis");
    });
    expect(search(router)).toBe("");
  });

  it("un q que llegue en la URL no viaja al api", async () => {
    const { mock } = renderUsers("/sistema/usuarios?q=7319582046&role=coach");
    await screen.findByRole("link", { name: "ana@apex.test" });

    expect(listCalls(mock).every((p) => !p.has("q"))).toBe(true);
    expect(listCalls(mock)[0]?.get("role")).toBe("coach");
  });
});

describe("UsersPage · filtros y paginación en la URL", () => {
  it("rol y estado se escriben en la URL y llegan al api", async () => {
    const { mock, router, user } = renderUsers();
    await screen.findByRole("link", { name: "ana@apex.test" });

    await user.selectOptions(screen.getByRole("combobox", { name: "Rol" }), "Coach");
    await user.selectOptions(screen.getByRole("combobox", { name: "Estado" }), "Bloqueado");

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=0&role=coach&status=locked");
    });
    expect(search(router)).toBe("?role=coach&status=locked");
  });

  it("el rol ofrece Admin, Coach y Socio, y el estado los cinco de la cuenta", () => {
    renderUsers();

    expect(within(screen.getByRole("combobox", { name: "Rol" })).getAllByRole("option").map((o) => o.textContent)).toEqual(["Todos", "Admin", "Coach", "Socio"]);
    expect(within(screen.getByRole("combobox", { name: "Estado" })).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Todos menos dados de baja",
      "Activo",
      "Pendiente de activación",
      "Bloqueado",
      "Inactivo",
      "Dado de baja",
    ]);
  });

  it("un filtro desconocido en la URL no llega al api", async () => {
    const { mock } = renderUsers("/sistema/usuarios?role=coach&hack=1&sort=password");
    await screen.findByRole("link", { name: "ana@apex.test" });

    expect(listCalls(mock)[0]?.toString()).toBe("limit=25&offset=0&role=coach");
  });

  it("Siguiente pide offset=25 y lo deja en la URL", async () => {
    const { mock, router, user } = renderUsers("/sistema/usuarios", { "GET /users": (call) => pageOf(call, ROWS, 60) });
    await screen.findByText("Mostrando 1–25 de 60");

    await user.click(screen.getByRole("button", { name: "Siguiente" }));

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.get("offset")).toBe("25");
    });
    expect(search(router)).toBe("?offset=25");
  });

  it("mientras llega la página siguiente la tabla queda ocupada y no muestra las filas viejas como nuevas", async () => {
    let second = false;
    const { user } = renderUsers("/sistema/usuarios", {
      "GET /users": (call) => (new URL(call.url, "http://apex.test").searchParams.get("offset") === "25" ? ((second = true), new Promise(() => undefined)) : pageOf(call, ROWS, 60)),
    });
    await screen.findByText("Mostrando 1–25 de 60");

    await user.click(screen.getByRole("button", { name: "Siguiente" }));

    await waitFor(() => {
      expect(second).toBe(true);
    });
    expect(screen.getByRole("region", { name: "Usuarios" })).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("link", { name: "ana@apex.test" })).not.toBeInTheDocument();
  });

  it("cambiar a 50 por página vuelve a la primera", async () => {
    const { mock, router, user } = renderUsers("/sistema/usuarios?offset=25", { "GET /users": (call) => pageOf(call, ROWS, 60) });
    await screen.findByText("Mostrando 26–50 de 60");

    await user.selectOptions(screen.getByRole("combobox", { name: "Mostrar" }), "50");

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe("limit=50&offset=0");
    });
    expect(search(router)).toBe("?limit=50");
  });
});

describe("UsersPage · estados", () => {
  it("mientras carga la tabla lo anuncia", () => {
    renderUsers("/sistema/usuarios", { "GET /users": () => new Promise(() => undefined) });

    expect(screen.getByRole("region", { name: "Usuarios" })).toHaveAttribute("aria-busy", "true");
  });

  it("sin resultados guía a limpiar los filtros", async () => {
    const { router, user } = renderUsers("/sistema/usuarios?status=locked", { "GET /users": (call) => pageOf(call, [], 0) });

    expect(await screen.findByText("No hay usuarios con estos filtros")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));

    expect(search(router)).toBe("");
  });

  it("un error del servidor se explica y se puede reintentar", async () => {
    let fail = true;
    const { mock, user } = renderUsers("/sistema/usuarios", {
      "GET /users": (call) => (fail ? { status: 500, body: { error: { code: "internal", message: "Error inesperado." } } } : pageOf(call)),
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar los usuarios. Intenta de nuevo en un momento.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("link", { name: "ana@apex.test" })).toBeInTheDocument();
    expect(mock.callsTo("GET /users")).toHaveLength(2);
  });

  it("un 403 dice que no tienes permiso y a quién pedirlo", async () => {
    renderUsers("/sistema/usuarios", { "GET /users": { status: 403, body: { error: { code: "forbidden", message: "Sin permiso." } } } });

    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para ver los usuarios. Si lo necesitas, pídeselo a un administrador.");
  });

  it("una respuesta con forma inesperada es un error, no datos", async () => {
    renderUsers("/sistema/usuarios", { "GET /users": { status: 200, body: { items: [{ id: 1 }], total: 1, limit: 25, offset: 0 } } });

    expect(await screen.findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.");
  });
});

describe("UsersPage · alta", () => {
  it("'Nuevo usuario del equipo' abre el panel de alta", async () => {
    const { user } = renderUsers();

    await user.click(screen.getByRole("button", { name: "Nuevo usuario del equipo" }));

    expect(screen.getByRole("dialog", { name: "Nuevo usuario del equipo" })).toBeInTheDocument();
  });
});

describe("UsersPage · cerrar el alta", () => {
  it("Cancelar cierra el panel y la lista sigue igual", async () => {
    const { user } = renderUsers();
    await screen.findByRole("link", { name: "ana@apex.test" });

    await user.click(screen.getByRole("button", { name: "Nuevo usuario del equipo" }));
    await user.click(within(screen.getByRole("dialog", { name: "Nuevo usuario del equipo" })).getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ana@apex.test" })).toBeInTheDocument();
  });
});
