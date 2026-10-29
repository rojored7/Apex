// S4A-F4 · US-080, US-081 y US-082 (front; S4A-D34): acciones de la fila de /planes (Planes.html).
// - Columna "Acción" (solo con `plans.manage`): Editar, Activar o Desactivar según el estado y Dar de
//   baja. El coach no ve la columna ni las acciones.
// - Columna "Socios con él" (`active_members_count`, S4A-D25) y total "N activos · M inactivos" con
//   dos GET /plans de limit=1 (active=true y active=false).
// - Desactivar pide confirmación con ConfirmModal ("Las membresías vigentes con este plan siguen
//   igual; el plan deja de aparecer al vender"); Activar va directo. La etiqueta de estado cambia
//   al releer la lista y queda un aviso.
// - Editar abre PlanForm en modo edición; el 200 cierra el panel y avisa "Plan guardado".
// - `// DESIGN-GAP:` en el código por Descripción, Días para usarlas y la casilla Activo.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { apiError, countCalls, MANAGED_ROWS, planStore, PLANS, renderPlans } from "../../../test/plans";

const SOURCES = import.meta.glob<string>(["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}"], { query: "?raw", import: "default", eager: true });

const table = () => screen.getByRole("table", { name: "Planes" });
const rowOf = (name: string) => screen.getByRole("link", { name }).closest("tr") as HTMLElement;
const cellsOf = (name: string) => within(rowOf(name)).getAllByRole("cell").map((c) => c.textContent);

const CONSEQUENCE = "Las membresías vigentes con este plan siguen igual; el plan deja de aparecer al vender.";

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("PlansPage · columnas y total (Planes.html, S4A-D25)", () => {
  it("la tabla gana 'Socios con él' y 'Acción'", async () => {
    renderPlans();
    await screen.findByRole("link", { name: "Mensual" });

    expect(within(table()).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Plan", "Tipo", "Precio", "Duración", "Clases", "Socios con él", "Estado", "Acción"]);
  });

  it("'Socios con él' muestra active_members_count de cada plan", async () => {
    renderPlans();
    await screen.findByRole("link", { name: "Mensual" });

    expect(cellsOf("Mensual")[5]).toBe("4");
    expect(cellsOf("12 clases")[5]).toBe("12");
    expect(cellsOf("Promo apertura")[5]).toBe("0");
  });

  it("el total se parte en 'N activos · M inactivos' con dos lecturas de limit=1", async () => {
    const { mock } = renderPlans();

    expect(await screen.findByText("2 activos · 1 inactivo")).toBeInTheDocument();
    expect(
      countCalls(mock)
        .map((p) => p.toString())
        .sort(),
    ).toEqual(["limit=1&offset=0&active=false", "limit=1&offset=0&active=true"]);
  });

  it("el total va en singular y en plural según el número", async () => {
    renderPlans("/planes", { rows: [{ ...PLANS.mensual, active_members_count: 1 }] });

    expect(await screen.findByText("1 activo · 0 inactivos")).toBeInTheDocument();
  });

  it("el total no cambia al buscar: cuenta todos los planes", async () => {
    const { mock, user } = renderPlans();
    expect(await screen.findByText("2 activos · 1 inactivo")).toBeInTheDocument();

    await user.type(screen.getByRole("searchbox", { name: "Buscar" }), "mens");

    await waitFor(() => {
      expect(mock.callsTo("GET /plans").some((c) => c.url.includes("q=mens"))).toBe(true);
    });
    expect(screen.getByText("2 activos · 1 inactivo")).toBeInTheDocument();
    expect(countCalls(mock).every((p) => !p.has("q"))).toBe(true);
  });

  it("cada fila trae Editar, Desactivar o Activar según el estado y Dar de baja, con el nombre del plan", async () => {
    renderPlans();
    await screen.findByRole("link", { name: "Mensual" });

    const mensual = within(rowOf("Mensual")).getByRole("group", { name: "Acciones de Mensual" });
    expect(within(mensual).getAllByRole("button").map((b) => b.textContent)).toEqual(["Editar", "Desactivar", "Dar de baja"]);
    expect(within(mensual).getByRole("button", { name: "Desactivar: Mensual" })).toBeInTheDocument();
    const promo = within(rowOf("Promo apertura")).getByRole("group", { name: "Acciones de Promo apertura" });
    expect(within(promo).getAllByRole("button").map((b) => b.textContent)).toEqual(["Editar", "Activar", "Dar de baja"]);
  });

  it("no tiene violaciones de accesibilidad con la columna de acción", async () => {
    const { container } = renderPlans();
    await screen.findByText("2 activos · 1 inactivo");

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("PlansPage · Desactivar (US-081)", () => {
  it("pide confirmación con el nombre del plan y la consecuencia; al confirmar cambia el estado y el total", async () => {
    const store = planStore();
    const { mock, user } = renderPlans("/planes", { handlers: store.handlers });
    await screen.findByText("2 activos · 1 inactivo");

    await user.click(screen.getByRole("button", { name: "Desactivar: Mensual" }));
    const modal = screen.getByRole("dialog", { name: "¿Desactivar el plan Mensual?" });
    expect(modal).toHaveAccessibleDescription(CONSEQUENCE);
    expect(await axe(document.body)).toHaveNoViolations();
    await user.click(within(modal).getByRole("button", { name: "Desactivar" }));

    expect(await screen.findByText("Plan desactivado: Mensual.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo(`POST /plans/${PLANS.mensual.id}/deactivate`)).toHaveLength(1);
    await waitFor(() => {
      expect(cellsOf("Mensual")[6]).toBe("Inactivo");
    });
    expect(await screen.findByText("1 activo · 2 inactivos")).toBeInTheDocument();
    expect(within(rowOf("Mensual")).getByRole("button", { name: "Activar: Mensual" })).toBeInTheDocument();
  });

  it("'Volver' cierra la confirmación sin desactivar", async () => {
    const store = planStore();
    const { mock, user } = renderPlans("/planes", { handlers: store.handlers });
    await screen.findByRole("link", { name: "Mensual" });

    await user.click(screen.getByRole("button", { name: "Desactivar: Mensual" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Volver" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo(`POST /plans/${PLANS.mensual.id}/deactivate`)).toHaveLength(0);
    expect(cellsOf("Mensual")[6]).toBe("Activo");
  });

  it("un 429 se explica dentro de la confirmación, que sigue abierta", async () => {
    const { user } = renderPlans("/planes", {
      handlers: { [`POST /plans/${PLANS.mensual.id}/deactivate`]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) },
    });
    await screen.findByRole("link", { name: "Mensual" });

    await user.click(screen.getByRole("button", { name: "Desactivar: Mensual" }));
    const modal = screen.getByRole("dialog");
    await user.click(within(modal).getByRole("button", { name: "Desactivar" }));

    expect(await within(modal).findByRole("alert")).toHaveTextContent("Hiciste muchos cambios seguidos. Espera 30 segundos e intenta de nuevo.");
  });

  it("la caché de mutaciones no conserva el plan desactivado (useSensitiveMutation)", async () => {
    const store = planStore();
    const { queryClient, user } = renderPlans("/planes", { handlers: store.handlers });
    await screen.findByRole("link", { name: "Mensual" });

    await user.click(screen.getByRole("button", { name: "Desactivar: Mensual" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Desactivar" }));
    await screen.findByText("Plan desactivado: Mensual.");

    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toEqual([]);
    });
  });
});

describe("PlansPage · Activar (US-081)", () => {
  it("activa sin confirmación, cambia la etiqueta y avisa", async () => {
    const store = planStore();
    const { mock, user } = renderPlans("/planes", { handlers: store.handlers });
    await screen.findByText("2 activos · 1 inactivo");

    await user.click(screen.getByRole("button", { name: "Activar: Promo apertura" }));

    expect(await screen.findByText("Plan activado: Promo apertura.")).toBeInTheDocument();
    expect(mock.callsTo(`POST /plans/${PLANS.promo.id}/activate`)).toHaveLength(1);
    await waitFor(() => {
      expect(cellsOf("Promo apertura")[6]).toBe("Activo");
    });
    expect(await screen.findByText("3 activos · 0 inactivos")).toBeInTheDocument();
  });

  it("revisión de seguridad de F4 (LOW-2): dos clics seguidos en Activar hacen una sola petición y el botón queda deshabilitado mientras tanto", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const { mock } = renderPlans("/planes", {
      handlers: {
        [`POST /plans/${PLANS.promo.id}/activate`]: async () => {
          await gate;
          return { status: 200, body: { ...PLANS.promo, is_active: true } };
        },
      },
    });
    const button = await screen.findByRole("button", { name: "Activar: Promo apertura" });

    fireEvent.click(button);
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Activar: Promo apertura" })).toBeDisabled();
    });
    expect(screen.getByRole("button", { name: "Desactivar: Mensual" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Editar: Mensual" })).toBeEnabled();
    release();
    expect(await screen.findByText("Plan activado: Promo apertura.")).toBeInTheDocument();
    expect(mock.callsTo(`POST /plans/${PLANS.promo.id}/activate`)).toHaveLength(1);
  });

  it("un error al activar se explica con un aviso y la fila no cambia", async () => {
    const { user } = renderPlans("/planes", { handlers: { [`POST /plans/${PLANS.promo.id}/activate`]: apiError(500, "internal_error") } });
    await screen.findByRole("link", { name: "Promo apertura" });

    await user.click(screen.getByRole("button", { name: "Activar: Promo apertura" }));

    expect(await screen.findByText("No pudimos cambiar el estado del plan. Intenta de nuevo en un momento.")).toBeInTheDocument();
    expect(cellsOf("Promo apertura")[6]).toBe("Inactivo");
  });
});

describe("PlansPage · Editar (US-080)", () => {
  it("Editar abre el panel precargado; guardar el precio envía solo ese campo, cierra y avisa", async () => {
    const store = planStore();
    const { mock, user } = renderPlans("/planes", { handlers: store.handlers });
    await screen.findByRole("link", { name: "Mensual" });

    await user.click(screen.getByRole("button", { name: "Editar: Mensual" }));
    const panel = screen.getByRole("dialog", { name: "Editar plan · Mensual" });
    expect(within(panel).getByRole("textbox", { name: /^Nombre/ })).toHaveValue("Mensual");
    const price = within(panel).getByRole("textbox", { name: /^Precio \(COP\)/ });
    await user.clear(price);
    await user.type(price, "135000");
    await user.click(within(panel).getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Plan guardado: Mensual.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo(`PATCH /plans/${PLANS.mensual.id}`).map((c) => c.body)).toEqual([{ price_cop: 135_000 }]);
    await waitFor(() => {
      expect(cellsOf("Mensual")[2]).toBe("$ 135.000");
    });
  });
});

describe("PlansPage · acciones ocultas sin plans.manage (S2-D26)", () => {
  it("el coach no ve la columna de acción ni los botones, y no pide los totales de inactivos", async () => {
    signInAs("coach");
    const { mock } = renderPlans("/planes", { rows: MANAGED_ROWS.filter((row) => row.is_active) });
    await screen.findByRole("link", { name: "Mensual" });

    expect(within(table()).getAllByRole("columnheader").map((h) => h.textContent)).not.toContain("Acción");
    expect(screen.queryByRole("button", { name: /^(Editar|Desactivar|Activar|Dar de baja)/ })).not.toBeInTheDocument();
    expect(countCalls(mock).some((p) => p.get("active") === "false")).toBe(false);
  });
});

describe("PlansPage · DESIGN-GAP de S4A-F4 (S4A-D36)", () => {
  it("el código deja constancia de Descripción, Días para usarlas y la casilla Activo", () => {
    const gaps = Object.entries(SOURCES)
      .filter(([path]) => /\/(PlanForm|PlansPage|PlanRowActions)\.tsx$/.test(path))
      .map(([, source]) => source)
      .join("\n");

    expect(gaps).toMatch(/DESIGN-GAP:[\s\S]*Descripción/);
    expect(gaps).toMatch(/DESIGN-GAP:[\s\S]*Días para usarlas/);
    expect(gaps).toMatch(/DESIGN-GAP:[\s\S]*casilla "Activo/);
  });
});
