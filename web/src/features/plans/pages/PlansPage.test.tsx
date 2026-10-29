// S2-F7 · US-079 y US-078 (front): /planes (Planes.html).
// - S2-D26: la ruta es solo admin (`plans.view`); la página igual respeta el alcance del api: sin
//   `plans.manage` no hay "Nuevo plan" ni el filtro de estado, y siempre pide `active=true`.
// - S2-D41: la búsqueda ("Nombre del plan") espera 300 ms, va al api y vive en memoria; en la URL
//   quedan `active`, `limit` y `offset`. Un `active` desconocido no viaja.
// - Columnas: plan (enlace a /planes?plan=<id>), tipo, precio "$ 120.000", duración, clases y
//   estado con StatusTag ("Activo" o "Inactivo", con texto). S4A-F4: más "Socios con él" y "Acción"
//   (sus casos en PlansPage.actions.test.tsx) y el total "N activos · M inactivos" para el admin.
// - Estados: carga, vacío ("No hay planes"), sin coincidencias, página fuera de rango, error con
//   Reintentar, 403 y respuesta inválida.
// - `?plan=<id>` abre el detalle de solo lectura (usePlan); 403 del coach sobre un inactivo y 404
//   con mensaje. "Nuevo plan" abre el panel; el 201 lo cierra, avisa "Plan creado" y relee la lista.
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { apiError, listCalls, NEW_PLAN, planPage, PLANS, renderPlans } from "../../../test/plans";

const table = () => screen.getByRole("table", { name: "Planes" });
const searchbox = () => screen.getByRole("searchbox", { name: "Buscar" });
const showSelect = () => screen.getByRole("combobox", { name: "Estado" });
const detail = () => screen.getByRole("dialog");

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("PlansPage · estructura (Planes.html)", () => {
  it("muestra el título con el total, Nuevo plan, la búsqueda, el filtro de estado y la tabla", async () => {
    renderPlans();

    expect(screen.getByRole("heading", { level: 1, name: /Planes/ })).toBeInTheDocument();
    expect(await screen.findByText("2 activos · 1 inactivo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nuevo plan" })).toBeInTheDocument();
    expect(searchbox()).toHaveAttribute("placeholder", "Nombre del plan");
    expect(within(showSelect()).getAllByRole("option").map((o) => o.textContent)).toEqual(["Todos", "Activos", "Inactivos"]);
    expect(within(table()).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Plan", "Tipo", "Precio", "Duración", "Clases", "Socios con él", "Estado", "Acción"]);
  });

  it("cada fila trae el nombre como enlace al detalle, el precio en COP y el estado con texto", async () => {
    renderPlans();

    const link = await screen.findByRole("link", { name: "Mensual" });
    expect(link).toHaveAttribute("href", `/planes?plan=${PLANS.mensual.id}`);
    const [, clases, mensual, promo] = within(table()).getAllByRole("row");
    expect(within(clases as HTMLElement).getAllByRole("cell").map((c) => c.textContent).slice(0, 7)).toEqual([
      "12 clases",
      "Por número de clases",
      "$ 110.000",
      "60 días",
      "12 clases",
      "12",
      "Activo",
    ]);
    expect(within(mensual as HTMLElement).getAllByRole("cell").map((c) => c.textContent).slice(0, 7)).toEqual(["Mensual", "Por días", "$ 120.000", "30 días", "—", "4", "Activo"]);
    expect(within(promo as HTMLElement).getByText("Inactivo")).toHaveAttribute("data-account", "inactive");
    expect(within(mensual as HTMLElement).getByText("Activo")).toHaveAttribute("data-account", "active");
  });

  it("un plan de 1 día y 1 clase va en singular", async () => {
    renderPlans("/planes", { rows: [{ ...PLANS.clases, name: "Clase suelta", duration_days: 1, class_count: 1, price_cop: 15_000 }] });

    const link = await screen.findByRole("link", { name: "Clase suelta" });
    const cells = within(link.closest("tr") as HTMLElement).getAllByRole("cell").map((c) => c.textContent).slice(0, 7);
    expect(cells).toEqual(["Clase suelta", "Por número de clases", "$ 15.000", "1 día", "1 clase", "0", "Activo"]);
  });

  it("la primera petición pide la primera página de 25 sin búsqueda ni filtro", async () => {
    const { mock } = renderPlans();
    await screen.findByRole("link", { name: "Mensual" });

    expect(listCalls(mock)[0]?.toString()).toBe("limit=25&offset=0");
  });

  it("explica que el precio de lo vendido no cambia", async () => {
    renderPlans();
    await screen.findByRole("link", { name: "Mensual" });

    expect(screen.getByText(/Las membresías ya vendidas guardan su propio precio/)).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderPlans();
    await screen.findByRole("link", { name: "Mensual" });

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("PlansPage · búsqueda local (S2-D41) y filtro en la URL", () => {
  it("espera a que dejes de escribir, envía q al api una vez y nunca la escribe en la URL", async () => {
    const { mock, router, user } = renderPlans();
    await screen.findByRole("link", { name: "Mensual" });

    await user.type(searchbox(), "mens");

    await waitFor(() => {
      expect(listCalls(mock).some((p) => p.get("q") === "mens")).toBe(true);
    });
    expect(listCalls(mock).filter((p) => p.has("q")).map((p) => p.get("q"))).toEqual(["mens"]);
    expect(router.state.location.search).not.toContain("q=");
    expect(router.state.location.search).not.toContain("mens");
  });

  it("no llama al api antes de 300 ms sin teclear", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { mock, user } = renderPlans();
      await screen.findByRole("link", { name: "Mensual" });

      await user.type(searchbox(), "promo");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(250);
      });
      expect(listCalls(mock).some((p) => p.has("q"))).toBe(false);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });

      await waitFor(() => {
        expect(listCalls(mock).at(-1)?.get("q")).toBe("promo");
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it("buscar desde la página 2 vuelve a la primera y conserva el filtro", async () => {
    const { mock, router, user } = renderPlans("/planes?active=true&offset=25", { handlers: { "GET /plans": (call) => planPage(call, Object.values(PLANS), 60) } });
    await screen.findByRole("link", { name: "Mensual" });

    await user.type(searchbox(), "mens");

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=0&q=mens&active=true");
    });
    expect(router.state.location.search).toBe("?active=true");
  });

  it.each([
    ["Activos", "true"],
    ["Inactivos", "false"],
  ])("El filtro de estado '%s' va a la URL como active=%s y al api", async (label, value) => {
    const { mock, router, user } = renderPlans();
    await screen.findByRole("link", { name: "Mensual" });

    await user.selectOptions(showSelect(), label);

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.get("active")).toBe(value);
    });
    expect(router.state.location.search).toBe(`?active=${value}`);
    expect(showSelect()).toHaveValue(value);
  });

  it("El filtro de estado 'Todos' quita active de la URL y del api", async () => {
    const { mock, router, user } = renderPlans("/planes?active=false");
    await screen.findByRole("link", { name: "Mensual" });
    expect(listCalls(mock)[0]?.get("active")).toBe("false");

    await user.selectOptions(showSelect(), "Todos");

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.has("active")).toBe(false);
    });
    expect(router.state.location.search).toBe("");
  });

  it("un active desconocido en la URL no llega al api", async () => {
    const { mock } = renderPlans("/planes?active=yes&sort=price&kind=x");
    await screen.findByRole("link", { name: "Mensual" });

    expect(listCalls(mock)[0]?.toString()).toBe("limit=25&offset=0");
    expect(showSelect()).toHaveValue("");
  });

  it("Siguiente pide offset=25 y lo deja en la URL", async () => {
    const { mock, router, user } = renderPlans("/planes", { handlers: { "GET /plans": (call) => planPage(call, Object.values(PLANS), 60) } });
    await screen.findByText("Mostrando 1–25 de 60");

    await user.click(screen.getByRole("button", { name: "Siguiente" }));

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.get("offset")).toBe("25");
    });
    expect(router.state.location.search).toBe("?offset=25");
  });
});

describe("PlansPage · alcance sin plans.manage (S2-D26)", () => {
  it("el coach no ve 'Nuevo plan' ni el filtro de estado y solo pide planes activos, aunque la URL diga otra cosa", async () => {
    signInAs("coach");
    const { mock } = renderPlans("/planes?active=false");
    await screen.findByRole("link", { name: "Mensual" });

    expect(screen.queryByRole("button", { name: "Nuevo plan" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Estado" })).not.toBeInTheDocument();
    expect(screen.getByText("Ves solo los planes activos.")).toBeInTheDocument();
    expect(listCalls(mock).every((p) => p.get("active") === "true")).toBe(true);
  });

  it("el coach con una lista vacía no recibe la invitación a crear", async () => {
    signInAs("coach");
    renderPlans("/planes", { rows: [] });

    expect(await screen.findByText("No hay planes.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Crear el primer plan" })).not.toBeInTheDocument();
  });
});

describe("PlansPage · estados", () => {
  it("mientras carga la tabla lo anuncia", () => {
    renderPlans("/planes", { handlers: { "GET /plans": () => new Promise(() => undefined) } });

    expect(screen.getByRole("region", { name: "Planes" })).toHaveAttribute("aria-busy", "true");
  });

  it("revisión L6: mientras llega una búsqueda no se muestra el total de la consulta anterior (S4A-F4: el del coach; el del admin no depende de la búsqueda)", async () => {
    signInAs("coach");
    const { user } = renderPlans("/planes", {
      handlers: { "GET /plans": (call) => (new URL(call.url, "http://apex.test").searchParams.has("q") ? new Promise(() => undefined) : planPage(call)) },
    });
    expect(await screen.findByText("3 en total")).toBeInTheDocument();

    await user.type(searchbox(), "mens");

    await waitFor(() => {
      expect(screen.queryByText("3 en total")).not.toBeInTheDocument();
    });
    expect(screen.queryByText("Esta página ya no tiene planes.")).not.toBeInTheDocument();
  });

  it("sin planes todavía guía a crear el primero y lo abre", async () => {
    const { user } = renderPlans("/planes", { rows: [] });

    expect(await screen.findByText("No hay planes.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Crear el primer plan" }));

    expect(screen.getByRole("dialog", { name: "Nuevo plan" })).toBeInTheDocument();
  });

  it("sin resultados de una búsqueda lo dice y guía a limpiarla", async () => {
    const { mock, user } = renderPlans("/planes", {
      handlers: { "GET /plans": (call) => (new URL(call.url, "http://apex.test").searchParams.has("q") ? planPage(call, [], 0) : planPage(call)) },
    });
    await screen.findByRole("link", { name: "Mensual" });

    await user.type(searchbox(), "nada");

    expect(await screen.findByText("No hay planes que coincidan con la búsqueda")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.has("q")).toBe(false);
    });
    expect(searchbox()).toHaveValue("");
  });

  it("un offset fuera de rango lleva a la primera página", async () => {
    const { router, user } = renderPlans("/planes?offset=500", {
      handlers: { "GET /plans": (call) => (new URL(call.url, "http://apex.test").searchParams.get("offset") === "500" ? planPage(call, [], 3) : planPage(call)) },
    });

    expect(await screen.findByText("Esta página ya no tiene planes.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ir a la primera página" }));

    expect(await screen.findByRole("link", { name: "Mensual" })).toBeInTheDocument();
    expect(router.state.location.search).toBe("");
  });

  it("un error del servidor se explica y se puede reintentar", async () => {
    let fail = true;
    const { mock, user } = renderPlans("/planes", { handlers: { "GET /plans": (call) => (fail ? apiError(500, "internal") : planPage(call)) } });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar los planes. Intenta de nuevo en un momento.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("link", { name: "Mensual" })).toBeInTheDocument();
    expect(listCalls(mock)).toHaveLength(2);
  });

  it("un 403 dice que no tienes permiso y a quién pedirlo", async () => {
    renderPlans("/planes", { handlers: { "GET /plans": apiError(403, "forbidden") } });

    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para ver estos planes. Si lo necesitas, pídeselo a un administrador.");
  });

  it("sin conexión lo dice con el mensaje de red", async () => {
    renderPlans("/planes", { handlers: { "GET /plans": () => Promise.reject(new TypeError("Failed to fetch")) } });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos conectar con el servidor. Intenta de nuevo.");
  });

  it("una respuesta con forma inesperada es un error, no datos", async () => {
    renderPlans("/planes", { handlers: { "GET /plans": { status: 200, body: { items: [{ ...PLANS.mensual, price_cop: 1.5 }], total: 1, limit: 25, offset: 0 } } } });

    expect(await screen.findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.");
  });
});

describe("PlansPage · detalle de solo lectura (?plan=<id>)", () => {
  it("abre el plan con usePlan, sin campos editables, y al cerrarlo quita el parámetro y conserva el filtro", async () => {
    const { mock, router, user } = renderPlans(`/planes?active=true&plan=${PLANS.clases.id}`);

    const panel = await screen.findByRole("dialog", { name: "12 clases" });
    expect(mock.callsTo(`GET /plans/${PLANS.clases.id}`)).toHaveLength(1);
    const values = within(panel).getAllByRole("definition").map((d) => d.textContent);
    expect(within(panel).getAllByRole("term").map((t) => t.textContent)).toEqual(["Precio", "Tipo", "Número de clases", "Días para usarlas", "Estado", "Creado"]);
    expect(values).toEqual(["$ 110.000", "Por número de clases", "12 clases", "60 días", "Activo", "20 oct 2026"]);
    expect(within(panel).queryByRole("textbox")).not.toBeInTheDocument();
    expect(await axe(document.body)).toHaveNoViolations();

    await user.click(within(panel).getByRole("button", { name: "Cerrar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(router.state.location.search).toBe("?active=true");
  });

  it("un plan por días muestra la duración en días y no el número de clases", async () => {
    renderPlans(`/planes?plan=${PLANS.promo.id}`);

    const panel = await screen.findByRole("dialog", { name: "Promo apertura" });
    expect(within(panel).getAllByRole("term").map((t) => t.textContent)).toEqual(["Precio", "Tipo", "Duración", "Estado", "Creado"]);
    expect(within(panel).getByText("Inactivo")).toHaveAttribute("data-account", "inactive");
  });

  it("al hacer clic en una fila se abre su detalle", async () => {
    const { router, user } = renderPlans();

    await user.click(await screen.findByRole("link", { name: "Mensual" }));

    expect(await screen.findByRole("dialog", { name: "Mensual" })).toBeInTheDocument();
    expect(router.state.location.search).toBe(`?plan=${PLANS.mensual.id}`);
  });

  it("el 403 del coach sobre un plan inactivo se explica", async () => {
    signInAs("coach");
    renderPlans(`/planes?plan=${PLANS.promo.id}`, { handlers: { [`GET /plans/${PLANS.promo.id}`]: apiError(403, "forbidden") } });

    await waitFor(() => {
      expect(within(detail()).getByRole("alert")).toHaveTextContent("Este plan está inactivo y solo un administrador puede verlo.");
    });
  });

  it("un plan que no existe lo dice y guía a volver a la lista", async () => {
    const missing = "99999999-9999-4999-8999-999999999999";
    renderPlans(`/planes?plan=${missing}`, { handlers: { [`GET /plans/${missing}`]: apiError(404, "plan_not_found") } });

    await waitFor(() => {
      expect(within(detail()).getByRole("alert")).toHaveTextContent("No encontramos este plan. Puede que lo hayan dado de baja; ciérralo y elige otro de la lista.");
    });
  });

  it("un error del servidor en el detalle se puede reintentar", async () => {
    let fail = true;
    const { mock, user } = renderPlans(`/planes?plan=${PLANS.mensual.id}`, {
      handlers: { [`GET /plans/${PLANS.mensual.id}`]: () => (fail ? apiError(500, "internal") : { status: 200, body: PLANS.mensual }) },
    });

    await waitFor(() => {
      expect(within(detail()).getByRole("alert")).toHaveTextContent("No pudimos cargar el plan. Intenta de nuevo en un momento.");
    });
    fail = false;
    await user.click(within(detail()).getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("dialog", { name: "Mensual" })).toBeInTheDocument();
    expect(mock.callsTo(`GET /plans/${PLANS.mensual.id}`)).toHaveLength(2);
  });

  it.each(["abc", "12345", "..%2Fusers", "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa%3F"])("revisión de seguridad de F4 (LOW-1): un ?plan=%s sin forma de UUID no abre nada ni pide nada", async (value) => {
    const { mock } = renderPlans(`/planes?plan=${value}`);
    await screen.findByRole("link", { name: "Mensual" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.calls.filter((c) => c.path.startsWith("/plans/"))).toHaveLength(0);
  });

  it("un ?plan= vacío no abre nada ni pide nada", async () => {
    const { mock } = renderPlans("/planes?plan=");
    await screen.findByRole("link", { name: "Mensual" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.calls.filter((c) => c.path.startsWith("/plans/"))).toHaveLength(0);
  });
});

describe("PlansPage · alta", () => {
  it("'Nuevo plan' abre el panel; el 201 lo cierra, avisa 'Plan creado' y relee la lista", async () => {
    const { mock, user } = renderPlans();
    await screen.findByRole("link", { name: "Mensual" });
    const before = mock.callsTo("GET /plans").length;

    await user.click(screen.getByRole("button", { name: "Nuevo plan" }));
    const panel = screen.getByRole("dialog", { name: "Nuevo plan" });
    await user.type(within(panel).getByRole("textbox", { name: /^Nombre/ }), "Trimestral");
    await user.type(within(panel).getByRole("textbox", { name: /^Precio \(COP\)/ }), "320000");
    await user.type(within(panel).getByRole("textbox", { name: /^Duración en días/ }), "90");
    await user.click(within(panel).getByRole("button", { name: "Crear plan" }));

    expect(await screen.findByText(`Plan creado: ${NEW_PLAN.name}.`)).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Nuevo plan" })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(mock.callsTo("GET /plans").length).toBeGreaterThan(before);
    });

    await user.click(screen.getByRole("button", { name: "Cerrar aviso" }));
    expect(screen.queryByText(/Plan creado/)).not.toBeInTheDocument();
  });

  it("'Ver el plan existente' del 409 abre ese plan en el detalle", async () => {
    const { user, router } = renderPlans("/planes", {
      handlers: { "POST /plans": apiError(409, "plan_name_duplicated", { field: "name", existing_id: PLANS.mensual.id }) },
    });
    await screen.findByRole("link", { name: "Mensual" });

    await user.click(screen.getByRole("button", { name: "Nuevo plan" }));
    const panel = screen.getByRole("dialog", { name: "Nuevo plan" });
    await user.type(within(panel).getByRole("textbox", { name: /^Nombre/ }), "mensual");
    await user.type(within(panel).getByRole("textbox", { name: /^Precio \(COP\)/ }), "120000");
    await user.type(within(panel).getByRole("textbox", { name: /^Duración en días/ }), "30");
    await user.click(within(panel).getByRole("button", { name: "Crear plan" }));
    await user.click(await within(panel).findByRole("link", { name: "Ver el plan existente" }));

    expect(await screen.findByRole("dialog", { name: "Mensual" })).toBeInTheDocument();
    expect(router.state.location.search).toBe(`?plan=${PLANS.mensual.id}`);
  });
});
