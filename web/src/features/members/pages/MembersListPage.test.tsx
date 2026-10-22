// S2-F6 · US-070 (front): /socios (Socios_Lista.html), admin y coach.
// - S2-D41 (M-8): la búsqueda (placeholder "Nombre, documento o teléfono") espera 300 ms, va al
//   api y vive en memoria: nunca en la URL. En la URL quedan `status`, `sort`, `limit` y `offset`.
// - Chips "Todos" y "Dados de baja" (status=deleted), también para el coach (N-20).
// - Cambiar la búsqueda vuelve a la primera página; la petición anterior se cancela (`signal`).
// - Filas con el nombre (enlace a /socios/{id}, S2-D34), el estado del socio con StatusTag y la
//   membresía vacía hasta el Sprint 3. Nada cifrado en la lista (N-01).
// - Estados de carga, vacío, error y sin permiso. "Nuevo socio" solo con `members.create`.
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { apiError, listCalls, memberPage, MEMBERS, renderMembers } from "../../../test/members";

const table = () => screen.getByRole("table", { name: "Socios" });
const searchbox = () => screen.getByRole("searchbox", { name: "Buscar" });
const chips = () => screen.getByRole("group", { name: "Estado" });

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("MembersListPage · estructura (Socios_Lista.html)", () => {
  it("muestra el título con el total, Nuevo socio, los chips, la búsqueda, el orden y la tabla", async () => {
    renderMembers();

    expect(screen.getByRole("heading", { level: 1, name: /Socios/ })).toBeInTheDocument();
    expect(await screen.findByText("3 en total")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Nuevo socio" })).toHaveAttribute("href", "/socios/nuevo");
    expect(within(chips()).getAllByRole("button").map((b) => b.textContent)).toEqual(["Todos", "Dados de baja"]);
    expect(within(chips()).getByRole("button", { name: "Todos" })).toHaveAttribute("aria-pressed", "true");
    expect(searchbox()).toHaveAttribute("placeholder", "Nombre, documento o teléfono");
    expect(within(screen.getByRole("combobox", { name: "Ordenar por" })).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Apellido A–Z",
      "Apellido Z–A",
      "Nombre A–Z",
      "Nombre Z–A",
      "Más reciente",
      "Más antiguo",
    ]);
    expect(within(table()).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Socio", "Estado", "Membresía"]);
  });

  it("cada fila trae el nombre como enlace a la ficha, el estado con texto y la membresía vacía", async () => {
    renderMembers();

    const link = await screen.findByRole("link", { name: "Laura Gómez" });
    expect(link).toHaveAttribute("href", `/socios/${MEMBERS.laura.id}`);
    const [, laura, andres, elena] = within(table()).getAllByRole("row");
    expect(within(laura as HTMLElement).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Laura Gómez", "Activo", "—"]);
    expect(within(andres as HTMLElement).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Andrés Ruiz", "Inactivo", "—"]);
    expect(within(elena as HTMLElement).getByText("Dado de baja")).toHaveAttribute("data-account", "deleted");
    expect(within(laura as HTMLElement).getByText("Activo")).toHaveAttribute("data-account", "active");
  });

  it("una membresía conocida se muestra con su StatusTag", async () => {
    renderMembers("/socios", { rows: [{ ...MEMBERS.laura, membership_status: "active", plan_name: "Mensual" }] });

    const link = await screen.findByRole("link", { name: "Laura Gómez" });
    const tr = link.closest("tr") as HTMLElement;
    expect(within(tr).getByText("Al día")).toHaveAttribute("data-status", "active");
  });

  it("la lista no muestra nada enmascarado ni cifrado (N-01)", async () => {
    renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(table().textContent).not.toContain("•");
  });

  it("la primera petición pide la primera página de 25 sin búsqueda, filtro ni orden", async () => {
    const { mock } = renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(listCalls(mock)[0]?.toString()).toBe("limit=25&offset=0");
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("MembersListPage · búsqueda local (S2-D41)", () => {
  it("espera a que dejes de escribir, envía q al api una vez y nunca la escribe en la URL", async () => {
    const { mock, router, user } = renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.type(searchbox(), "1020304417");

    await waitFor(() => {
      expect(listCalls(mock).some((p) => p.get("q") === "1020304417")).toBe(true);
    });
    expect(listCalls(mock).filter((p) => p.has("q")).map((p) => p.get("q"))).toEqual(["1020304417"]);
    expect(router.state.location.search).not.toContain("q=");
    expect(router.state.location.search).not.toContain("1020304417");
  });

  it("no llama al api antes de 300 ms sin teclear", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { mock, user } = renderMembers();
      await screen.findByRole("link", { name: "Laura Gómez" });

      await user.type(searchbox(), "laura");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(250);
      });
      expect(listCalls(mock).some((p) => p.has("q"))).toBe(false);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });

      await waitFor(() => {
        expect(listCalls(mock).at(-1)?.get("q")).toBe("laura");
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it("buscar desde la página 2 vuelve a la primera", async () => {
    const { mock, router, user } = renderMembers("/socios?offset=25&sort=first_name", { handlers: { "GET /members": (call) => memberPage(call, Object.values(MEMBERS), 60) } });
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.type(searchbox(), "gomez");

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=0&q=gomez&sort=first_name");
    });
    expect(router.state.location.search).toBe("?sort=first_name");
  });

  it("revisión M2: la búsqueda no se queda en la caché al dejar de usarse", async () => {
    const { mock, queryClient, user } = renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.type(searchbox(), "1020304417");
    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.get("q")).toBe("1020304417");
    });
    await user.click(screen.getByRole("button", { name: "Limpiar" }));

    await waitFor(() => {
      expect(JSON.stringify(queryClient.getQueryCache().findAll({ queryKey: ["members"] }).map((query) => query.queryKey))).not.toContain("1020304417");
    });
  });

  it("un q que llegue en la URL no viaja al api", async () => {
    const { mock } = renderMembers("/socios?q=1020304417&status=deleted");
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(listCalls(mock).every((p) => !p.has("q"))).toBe(true);
    expect(listCalls(mock)[0]?.get("status")).toBe("deleted");
  });

  it("cambiar la búsqueda cancela la petición anterior con su signal", async () => {
    const { mock, user } = renderMembers("/socios", {
      handlers: { "GET /members": (call) => (new URL(call.url, "http://apex.test").searchParams.has("q") ? memberPage(call) : new Promise(() => undefined)) },
    });
    await waitFor(() => {
      expect(listCalls(mock)).toHaveLength(1);
    });
    const first = mock.callsTo("GET /members")[0]?.signal;
    expect(first?.aborted).toBe(false);

    await user.type(searchbox(), "laura");

    await screen.findByRole("link", { name: "Laura Gómez" });
    expect(first?.aborted).toBe(true);
  });
});

describe("MembersListPage · chips, orden y paginación en la URL", () => {
  it("'Dados de baja' pide status=deleted y lo deja en la URL; 'Todos' lo quita", async () => {
    const { mock, router, user } = renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.click(within(chips()).getByRole("button", { name: "Dados de baja" }));

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=0&status=deleted");
    });
    expect(router.state.location.search).toBe("?status=deleted");
    expect(within(chips()).getByRole("button", { name: /Dados de baja/ })).toHaveAttribute("aria-pressed", "true");

    await user.click(within(chips()).getByRole("button", { name: "Todos" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
    expect(listCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=0");
  });

  it("el coach también ve los chips y los dados de baja (N-20) y puede registrar socios", async () => {
    signInAs("coach");
    const { mock, user } = renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.click(within(chips()).getByRole("button", { name: "Dados de baja" }));

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.get("status")).toBe("deleted");
    });
    expect(screen.getByRole("link", { name: "Nuevo socio" })).toBeInTheDocument();
  });

  it("sin members.create no aparece 'Nuevo socio'", async () => {
    signInAs("member");
    renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(screen.queryByRole("link", { name: "Nuevo socio" })).not.toBeInTheDocument();
  });

  it("el orden va a la URL y al api, y vuelve a la primera página", async () => {
    const { mock, router, user } = renderMembers("/socios?offset=25", { handlers: { "GET /members": (call) => memberPage(call, Object.values(MEMBERS), 60) } });
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.selectOptions(screen.getByRole("combobox", { name: "Ordenar por" }), "Más reciente");

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=0&sort=-created_at");
    });
    expect(router.state.location.search).toBe("?sort=-created_at");
    expect(screen.getByRole("combobox", { name: "Ordenar por" })).toHaveValue("-created_at");
  });

  it("un estado, un orden o un filtro desconocidos en la URL no llegan al api", async () => {
    const { mock } = renderMembers("/socios?status=hack&sort=document&plan=x");
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(listCalls(mock)[0]?.toString()).toBe("limit=25&offset=0");
    expect(within(chips()).getByRole("button", { name: "Todos" })).toHaveAttribute("aria-pressed", "true");
  });

  it("Siguiente pide offset=25 y lo deja en la URL", async () => {
    const { mock, router, user } = renderMembers("/socios", { handlers: { "GET /members": (call) => memberPage(call, Object.values(MEMBERS), 60) } });
    await screen.findByText("Mostrando 1–25 de 60");

    await user.click(screen.getByRole("button", { name: "Siguiente" }));

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.get("offset")).toBe("25");
    });
    expect(router.state.location.search).toBe("?offset=25");
  });
});

describe("MembersListPage · estados", () => {
  it("mientras carga la tabla lo anuncia", () => {
    renderMembers("/socios", { handlers: { "GET /members": () => new Promise(() => undefined) } });

    expect(screen.getByRole("region", { name: "Socios" })).toHaveAttribute("aria-busy", "true");
  });

  it("sin resultados de una búsqueda lo dice y guía a limpiarla", async () => {
    const { mock, user } = renderMembers("/socios", {
      handlers: { "GET /members": (call) => (new URL(call.url, "http://apex.test").searchParams.has("q") ? memberPage(call, [], 0) : memberPage(call)) },
    });
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.type(searchbox(), "nadie");

    expect(await screen.findByText("No hay socios que coincidan con la búsqueda")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.has("q")).toBe(false);
    });
    expect(searchbox()).toHaveValue("");
  });

  it("sin socios todavía guía a registrar el primero", async () => {
    renderMembers("/socios", { rows: [] });

    expect(await screen.findByText("Todavía no hay socios registrados.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Registrar el primer socio" })).toHaveAttribute("href", "/socios/nuevo");
  });

  it("revisión L1: un offset fuera de rango no dice que no hay socios y lleva a la primera página", async () => {
    const { router, user } = renderMembers("/socios?offset=500", {
      handlers: { "GET /members": (call) => (new URL(call.url, "http://apex.test").searchParams.get("offset") === "500" ? memberPage(call, [], 3) : memberPage(call)) },
    });

    expect(await screen.findByText("Esta página ya no tiene socios.")).toBeInTheDocument();
    expect(screen.queryByText("Todavía no hay socios registrados.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ir a la primera página" }));

    expect(await screen.findByRole("link", { name: "Laura Gómez" })).toBeInTheDocument();
    expect(router.state.location.search).toBe("");
  });

  it("sin dados de baja lo dice con el filtro puesto", async () => {
    renderMembers("/socios?status=deleted", { rows: [] });

    expect(await screen.findByText("No hay socios que coincidan con la búsqueda")).toBeInTheDocument();
  });

  it("un error del servidor se explica y se puede reintentar", async () => {
    let fail = true;
    const { mock, user } = renderMembers("/socios", { handlers: { "GET /members": (call) => (fail ? apiError(500, "internal") : memberPage(call)) } });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar los socios. Intenta de nuevo en un momento.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("link", { name: "Laura Gómez" })).toBeInTheDocument();
    expect(mock.callsTo("GET /members")).toHaveLength(2);
  });

  it("un 403 dice que no tienes permiso y a quién pedirlo", async () => {
    renderMembers("/socios", { handlers: { "GET /members": apiError(403, "forbidden") } });

    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para ver los socios. Si lo necesitas, pídeselo a un administrador.");
  });

  it("un 429 de la búsqueda dice cuánto esperar", async () => {
    const { user } = renderMembers("/socios", {
      handlers: { "GET /members": (call) => (new URL(call.url, "http://apex.test").searchParams.has("q") ? apiError(429, "rate_limited", {}, { "Retry-After": "12" }) : memberPage(call)) },
    });
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.type(searchbox(), "laura");

    expect(await screen.findByRole("alert")).toHaveTextContent("Hiciste muchas búsquedas seguidas. Espera 12 segundos e intenta de nuevo.");
  });

  it("sin conexión lo dice con el mensaje de red", async () => {
    renderMembers("/socios", { handlers: { "GET /members": () => Promise.reject(new TypeError("Failed to fetch")) } });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos conectar con el servidor. Intenta de nuevo.");
  });

  it("una respuesta con forma inesperada es un error, no datos", async () => {
    renderMembers("/socios", { handlers: { "GET /members": { status: 200, body: { items: [{ id: 1 }], total: 1, limit: 25, offset: 0 } } } });

    expect(await screen.findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.");
  });
});

describe("MembersListPage · aviso del alta", () => {
  it("el aviso se puede cerrar y no vuelve al recargar la vista", async () => {
    const { router, user } = renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    await act(async () => {
      await router.navigate("/socios", { state: { memberCreated: { name: "Laura Gómez", consentMissing: true } } });
    });

    expect(await screen.findByText("Socio registrado: Laura Gómez.")).toBeInTheDocument();
    expect(screen.getByText(/Falta la autorización de tratamiento de datos/)).toBeInTheDocument();
    await waitFor(() => {
      expect(router.state.location.state).toBeNull();
    });
    await user.click(screen.getByRole("button", { name: "Cerrar aviso" }));

    expect(screen.queryByText(/Socio registrado/)).not.toBeInTheDocument();
  });

  it("un estado de navegación ajeno no muestra aviso", async () => {
    const { router } = renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    await act(async () => {
      await router.navigate("/socios", { state: { memberCreated: { name: 7 } } });
    });

    expect(screen.queryByText(/Socio registrado/)).not.toBeInTheDocument();
  });
});
