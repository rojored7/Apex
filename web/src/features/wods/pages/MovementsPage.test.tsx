// S8-F1 · US-165 y US-166 (front): /movimientos (Movimientos.html) con la pestaña ?tab=benchmarks.
// - Tabla paginada en el servidor: movimiento, categoría, unidad, «Usado en WODs», estado y acción.
// - Chips por categoría e «Inactivos» (single), búsqueda, «+ Nuevo movimiento» y «Editar» abren el panel.
// - Estados: carga, vacío, error con Reintentar, 403 y permiso denegado.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { benchmarksPage, movement, movementsPage } from "../../../test/wods";
import MovementsPage from "./MovementsPage";

function renderPage(handlers: Record<string, MockHandler> = {}, entry = "/movimientos") {
  const mock = mockApi({ "GET /movements": movementsPage(), "GET /benchmarks": benchmarksPage(), ...handlers });
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter initialEntries={[entry]}>
          <MovementsPage />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, user: userEvent.setup(), ...view };
}

const rowOf = (text: string) => screen.getByText(text).closest("tr") as HTMLElement;
const lastQuery = (calls: { url: string }[]) => new URL(calls[calls.length - 1]?.url ?? "", "http://apex.test").searchParams;

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("MovementsPage · estructura (Movimientos.html)", () => {
  it("título, pestañas, columnas y «Usado en WODs»", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { level: 1, name: "Movimientos" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Movimientos", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Benchmarks" })).toBeInTheDocument();
    await screen.findByText("Back Squat");
    for (const header of ["Movimiento", "Categoría", "Unidad", "Usado en WODs", "Estado"]) {
      expect(screen.getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
    const squat = rowOf("Back Squat");
    expect(within(squat).getByText("Fuerza")).toBeInTheDocument();
    expect(within(squat).getByText("kg")).toBeInTheDocument();
    expect(within(squat).getByText("38")).toBeInTheDocument();
    expect(within(rowOf("Pull-up")).getByText("Gimnástico")).toBeInTheDocument();
    expect(within(rowOf("Run 400 m")).getByText("Mono-estructural")).toBeInTheDocument();
    expect(within(rowOf("Sled Push")).getByText("Otro")).toBeInTheDocument();
    expect(within(rowOf("Sled Push")).getByText("Inactivo")).toBeInTheDocument();
  });

  it("pide los movimientos paginados al servidor", async () => {
    const { mock } = renderPage();

    await screen.findByText("Back Squat");
    const query = lastQuery(mock.callsTo("GET /movements"));
    expect(query.get("limit")).toBe("25");
    expect(query.get("offset")).toBe("0");
    expect(query.get("category")).toBeNull();
    expect(query.get("active")).toBeNull();
  });

  it("la nota explica que un movimiento usado en WODs se desactiva", async () => {
    renderPage();

    expect(await screen.findByText(/Un movimiento usado en WODs no se borra: se desactiva/)).toBeInTheDocument();
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderPage();
    await screen.findByText("Back Squat");

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("MovementsPage · filtros", () => {
  it("el chip de una categoría filtra en el servidor y «Todos» lo quita", async () => {
    const { user, mock } = renderPage();
    await screen.findByText("Back Squat");

    await user.click(screen.getByRole("button", { name: "Fuerza" }));
    await waitFor(() => {
      expect(lastQuery(mock.callsTo("GET /movements")).get("category")).toBe("weightlifting");
    });
    expect(screen.getByRole("button", { name: "Fuerza", pressed: true })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Todos" }));
    await waitFor(() => {
      expect(lastQuery(mock.callsTo("GET /movements")).get("category")).toBeNull();
    });
  });

  it("«Inactivos» pide active=false", async () => {
    const { user, mock } = renderPage();
    await screen.findByText("Back Squat");

    await user.click(screen.getByRole("button", { name: "Inactivos" }));

    await waitFor(() => {
      expect(lastQuery(mock.callsTo("GET /movements")).get("active")).toBe("false");
    });
  });

  it("la búsqueda manda q al servidor", async () => {
    const { user, mock } = renderPage();
    await screen.findByText("Back Squat");

    await user.type(screen.getByRole("searchbox"), "squat");

    await waitFor(() => {
      expect(lastQuery(mock.callsTo("GET /movements")).get("q")).toBe("squat");
    });
  });
});

describe("MovementsPage · estados", () => {
  it("sin movimientos guía a crear el primero", async () => {
    renderPage({ "GET /movements": movementsPage([]) });

    expect(await screen.findByText("Todavía no hay movimientos. Crea el primero para poder armar WODs.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Nuevo movimiento|Crear el primer movimiento/ }).length).toBeGreaterThan(0);
  });

  it("sin coincidencias ofrece limpiar filtros", async () => {
    const { user } = renderPage();
    await screen.findByText("Back Squat");
    // La respuesta vacía llega con un filtro puesto.
    mockApi({ "GET /movements": movementsPage([]), "GET /benchmarks": benchmarksPage() });
    await user.click(screen.getByRole("button", { name: "Fuerza" }));

    expect(await screen.findByText("No hay movimientos que coincidan con la búsqueda")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Limpiar filtros" })).toBeInTheDocument();
  });

  it("error 500 con Reintentar", async () => {
    let calls = 0;
    const { user } = renderPage({
      "GET /movements": () => {
        calls += 1;
        return calls === 1 ? apiError(500, "internal_error") : movementsPage();
      },
    });

    expect(await screen.findByText("No pudimos cargar los movimientos. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Back Squat")).toBeInTheDocument();
  });

  it("un 403 del api se dice como permiso", async () => {
    renderPage({ "GET /movements": apiError(403, "forbidden") });

    expect(await screen.findByText("No tienes permiso para ver los movimientos. Si lo necesitas, pídeselo a un administrador.")).toBeInTheDocument();
  });

  it("el socio no ve el catálogo: permiso denegado y ninguna petición", () => {
    signInAs("member");
    const { mock } = renderPage();

    expect(screen.getByRole("heading", { name: "No tienes permiso para ver los movimientos" })).toBeInTheDocument();
    expect(mock.callsTo("GET /movements")).toHaveLength(0);
  });

  it("el coach también ve y crea movimientos", async () => {
    signInAs("coach");
    renderPage();

    expect(await screen.findByText("Back Squat")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "+ Nuevo movimiento" })).toBeInTheDocument();
  });
});

describe("MovementsPage · acciones", () => {
  it("«+ Nuevo movimiento» abre el panel de un movimiento nuevo", async () => {
    const { user } = renderPage();
    await screen.findByText("Back Squat");

    await user.click(screen.getByRole("button", { name: "+ Nuevo movimiento" }));

    expect(screen.getByRole("dialog", { name: "Nuevo movimiento" })).toBeInTheDocument();
  });

  it("«Editar» abre el panel con el movimiento de la fila", async () => {
    const { user } = renderPage();
    await screen.findByText("Pull-up");

    await user.click(within(rowOf("Pull-up")).getByRole("button", { name: "Editar Pull-up" }));

    expect(screen.getByRole("dialog", { name: "Editar movimiento · Pull-up" })).toBeInTheDocument();
  });

  it("crear un movimiento avisa y vuelve a pedir la lista", async () => {
    const { user, mock } = renderPage({
      "POST /movements": { status: 201, body: movement("d1d1d1d1-0000-4000-8000-000000000009", { name: "Deadlift", wod_count: 0 }) },
    });
    await screen.findByText("Back Squat");
    await user.click(screen.getByRole("button", { name: "+ Nuevo movimiento" }));
    await user.type(screen.getByLabelText(/^Nombre/), "Deadlift");
    const before = mock.callsTo("GET /movements").length;

    await user.click(screen.getByRole("button", { name: "Crear movimiento" }));

    expect(await screen.findByText("Movimiento «Deadlift» creado.")).toBeInTheDocument();
    await waitFor(() => {
      expect(mock.callsTo("GET /movements").length).toBeGreaterThan(before);
    });
  });
});

describe("MovementsPage · pestaña Benchmarks (?tab=benchmarks)", () => {
  it("muestra los benchmarks con su tipo de marca y los WODs que los usan", async () => {
    const { mock } = renderPage({}, "/movimientos?tab=benchmarks");

    expect(await screen.findByText("Fran")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Benchmarks", selected: true })).toBeInTheDocument();
    expect(within(rowOf("Fran")).getByText("Tiempo")).toBeInTheDocument();
    expect(within(rowOf("Cindy")).getByText("Rondas + repeticiones")).toBeInTheDocument();
    expect(within(rowOf("Cindy")).getByText("3")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Usado en WODs" })).toBeInTheDocument();
    const query = lastQuery(mock.callsTo("GET /benchmarks"));
    expect(query.get("limit")).toBe("25");
    expect(query.get("offset")).toBe("0");
    expect(mock.callsTo("GET /movements")).toHaveLength(0);
  });

  it("cambiar de pestaña pide los benchmarks", async () => {
    const { user, mock } = renderPage();
    await screen.findByText("Back Squat");

    await user.click(screen.getByRole("tab", { name: "Benchmarks" }));

    expect(await screen.findByText("Fran")).toBeInTheDocument();
    expect(mock.callsTo("GET /benchmarks").length).toBeGreaterThan(0);
  });

  it("sin benchmarks guía a sembrarlos o crear el primero", async () => {
    renderPage({ "GET /benchmarks": benchmarksPage([]) }, "/movimientos?tab=benchmarks");

    expect(await screen.findByText("Todavía no hay benchmarks. Crea el primero para usarlo al armar un WOD.")).toBeInTheDocument();
  });

  it("«+ Nuevo benchmark» y «Editar» abren su panel", async () => {
    const { user } = renderPage({}, "/movimientos?tab=benchmarks");
    await screen.findByText("Fran");

    await user.click(screen.getByRole("button", { name: "+ Nuevo benchmark" }));
    expect(screen.getByRole("dialog", { name: "Nuevo benchmark" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    await user.click(within(rowOf("Fran")).getByRole("button", { name: "Editar Fran" }));
    expect(screen.getByRole("dialog", { name: "Editar benchmark · Fran" })).toBeInTheDocument();
  });

  it("error 500 con Reintentar", async () => {
    renderPage({ "GET /benchmarks": apiError(500, "internal_error") }, "/movimientos?tab=benchmarks");

    expect(await screen.findByText("No pudimos cargar los benchmarks. Intenta de nuevo en un momento.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderPage({}, "/movimientos?tab=benchmarks");
    await screen.findByText("Fran");

    expect(await axe(container)).toHaveNoViolations();
  });
});
