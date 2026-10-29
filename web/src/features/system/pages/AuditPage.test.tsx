// S4A-F1 · US-102 (front): /sistema/auditoria (Auditoria.html), solo admin. Filtros en la URL con
// los nombres del api, búsqueda en memoria (S2-D41), selector de usuario con GET /users?limit=200 y
// "Sistema (worker)", paginación por offset (25/50/100), carga, vacío, error con reintento, el
// detalle por `?seq=` y los DESIGN-GAP de S4A-D31 visibles en el código.
import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { canAccessRoute, isPageAvailable } from "../../../core/auth/routeAccess";
import { AUDIT_PATH, AUDIT_ROWS, COACH_ID, LAURA_ID, SYSTEM_ID, auditPageReply, auditRow, queryOf, renderAuditPage } from "../../../test/audit";
import type { RecordedCall } from "../../../test/server";

const SOURCES = import.meta.glob<string>(["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}"], { query: "?raw", import: "default", eager: true });

/** La tabla ya con filas (mientras carga, DataTable pinta el esqueleto dentro de la misma tabla). */
async function loadedTable(): Promise<HTMLElement> {
  await screen.findAllByRole("link", { name: /\d{4}, \d{1,2}:\d{2}/ });
  return screen.getByRole("table", { name: "Auditoría" });
}

const lastList = (calls: RecordedCall[]): URLSearchParams => queryOf(calls.filter((c) => c.method === "GET" && c.path === "/audit").at(-1));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AuditPage · lista (US-102)", () => {
  it("pide la primera página con limit 25 y offset 0 y pinta las filas", async () => {
    const { mock, container } = renderAuditPage();

    const table = await loadedTable();
    expect(Object.fromEntries(lastList(mock.calls))).toEqual({ limit: "25", offset: "0" });
    expect(screen.getByRole("heading", { level: 1, name: /Auditoría/ })).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "20 oct 2026, 11:52 a. m." })).toBeInTheDocument();
    expect(within(table).getByText("admin@apex.test")).toBeInTheDocument();
    expect(within(table).getByText("carlos@apex.test")).toBeInTheDocument();
    expect(within(table).getByText("Sistema (worker)")).toBeInTheDocument();
    expect(within(table).getAllByText("Cambiar")).toHaveLength(2);
    expect(within(table).getByText("Crear")).toBeInTheDocument();
    expect(within(table).getByText(/^Socio/)).toBeInTheDocument();
    expect(within(table).getByText(/^Pago/)).toBeInTheDocument();
    expect(within(table).getByText(/^Membresía/)).toBeInTheDocument();
    expect(screen.getByText("3 entradas")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("el total saturado del api (100.001, S4A-D106) se muestra como más de 100.000", async () => {
    renderAuditPage(AUDIT_PATH, { handlers: { "GET /audit": (call) => auditPageReply(call, AUDIT_ROWS, 100_001) } });

    expect(await screen.findByText("Más de 100.000 entradas")).toBeInTheDocument();
  });

  it("los filtros de la URL viajan con los nombres del api y las fechas de Bogotá en UTC", async () => {
    const { mock } = renderAuditPage(`${AUDIT_PATH}?from=2026-10-13&to=2026-10-20&table=members.members&user_id=${COACH_ID}&action=update&record_id=${LAURA_ID}`);

    await loadedTable();
    expect(Object.fromEntries(lastList(mock.calls))).toEqual({
      limit: "25",
      offset: "0",
      from: "2026-10-13T05:00:00.000Z",
      to: "2026-10-21T05:00:00.000Z",
      table: "members.members",
      user_id: COACH_ID,
      action: "update",
      record_id: LAURA_ID,
    });
    expect(screen.getByRole("combobox", { name: "Entidad" })).toHaveValue("members.members");
    expect(screen.getByRole("combobox", { name: "Acción" })).toHaveValue("update");
    expect(screen.getByLabelText("Desde")).toHaveValue("2026-10-13");
  });

  it("un filtro de la URL que no es válido no viaja al api", async () => {
    const { mock } = renderAuditPage(`${AUDIT_PATH}?table=x&user_id=yo&action=descifrar&record_id=1`);

    await loadedTable();
    expect(Object.fromEntries(lastList(mock.calls))).toEqual({ limit: "25", offset: "0" });
  });

  it("Entidad, Usuario y Acción quedan en la URL con table, user_id y action", async () => {
    const { mock, router, user } = renderAuditPage();
    await loadedTable();

    await user.selectOptions(screen.getByRole("combobox", { name: "Entidad" }), "Pago");
    await waitFor(() => {
      expect(lastList(mock.calls).get("table")).toBe("payments.payments");
    });
    await user.selectOptions(screen.getByRole("combobox", { name: "Usuario" }), "carlos@apex.test");
    await waitFor(() => {
      expect(lastList(mock.calls).get("user_id")).toBe(COACH_ID);
    });
    await user.selectOptions(screen.getByRole("combobox", { name: "Acción" }), "Crear");
    await waitFor(() => {
      expect(lastList(mock.calls).get("action")).toBe("insert");
    });
    const search = new URLSearchParams(router.state.location.search);
    expect(search.get("table")).toBe("payments.payments");
    expect(search.get("user_id")).toBe(COACH_ID);
    expect(search.get("action")).toBe("insert");
  });

  it("el selector de usuario lee GET /users?limit=200 y ofrece Sistema (worker) con el id del usuario técnico", async () => {
    const { mock, user, router } = renderAuditPage();
    await loadedTable();

    await waitFor(() => {
      expect(queryOf(mock.callsTo("GET /users")[0]).get("limit")).toBe("200");
    });
    const select = screen.getByRole("combobox", { name: "Usuario" });
    await waitFor(() => {
      expect(within(select).getByRole("option", { name: "carlos@apex.test" })).toBeInTheDocument();
    });
    expect(within(select).getByRole("option", { name: "Todos" })).toHaveValue("");
    await user.selectOptions(select, "Sistema (worker)");
    await waitFor(() => {
      expect(new URLSearchParams(router.state.location.search).get("user_id")).toBe(SYSTEM_ID);
    });
  });

  it("el rango de fechas queda en la URL como días", async () => {
    const { router, user } = renderAuditPage();
    await loadedTable();

    await user.type(screen.getByLabelText("Desde"), "2026-10-13");

    await waitFor(() => {
      expect(new URLSearchParams(router.state.location.search).get("from")).toBe("2026-10-13");
    });
  });

  it("la búsqueda viaja como q y nunca queda en la URL (S2-D41)", async () => {
    const { mock, router, user } = renderAuditPage();
    await loadedTable();

    await user.type(screen.getByRole("searchbox", { name: "Registro" }), "carlos@apex.test");

    await waitFor(() => {
      expect(lastList(mock.calls).get("q")).toBe("carlos@apex.test");
    });
    expect(router.state.location.search).not.toContain("carlos");
  });

  it("pagina por offset: Siguiente pide offset 25 y Mostrar 50 cambia el limit", async () => {
    const { mock, router, user } = renderAuditPage(AUDIT_PATH, { handlers: { "GET /audit": (call) => auditPageReply(call, AUDIT_ROWS, 120) } });
    await loadedTable();

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));
    await waitFor(() => {
      expect(lastList(mock.calls).get("offset")).toBe("25");
    });
    expect(new URLSearchParams(router.state.location.search).get("offset")).toBe("25");

    await user.selectOptions(screen.getByRole("combobox", { name: "Mostrar" }), "50");
    await waitFor(() => {
      expect(Object.fromEntries(lastList(mock.calls))).toMatchObject({ limit: "50", offset: "0" });
    });
  });

  it("muestra la carga mientras llega la página", async () => {
    renderAuditPage(AUDIT_PATH, { handlers: { "GET /audit": () => new Promise(() => undefined) } });

    expect(await screen.findByText(/Cargando/)).toBeInTheDocument();
  });

  it("sin entradas dice qué pasó y ofrece limpiar los filtros", async () => {
    const { router, user } = renderAuditPage(`${AUDIT_PATH}?action=delete`, { handlers: { "GET /audit": (call) => auditPageReply(call, []) } });

    expect(await screen.findByText("No hay entradas de auditoría con estos filtros")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
  });

  it("un error del api se explica y Reintentar vuelve a pedir", async () => {
    let fail = true;
    const { mock, user } = renderAuditPage(AUDIT_PATH, {
      handlers: { "GET /audit": (call) => (fail ? { status: 500, body: { error: { code: "internal_error", message: "x" } } } : auditPageReply(call)) },
    });

    expect(await screen.findByText("No pudimos cargar la auditoría. Intenta de nuevo en un momento.")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await loadedTable()).toBeInTheDocument();
    expect(mock.callsTo("GET /audit").length).toBeGreaterThanOrEqual(2);
  });

  it("un 403 dice que no hay permiso", async () => {
    renderAuditPage(AUDIT_PATH, { handlers: { "GET /audit": { status: 403, body: { error: { code: "forbidden", message: "x" } } } } });

    expect(await screen.findByText("No tienes permiso para ver la auditoría. Solo un administrador puede consultarla.")).toBeInTheDocument();
  });

  it("un 422 de las fechas dice qué revisar", async () => {
    renderAuditPage(`${AUDIT_PATH}?from=2019-01-01`, { handlers: { "GET /audit": { status: 422, body: { error: { code: "validation_error", message: "x", field: "from" } } } } });

    expect(await screen.findByText("Revisa los filtros: las fechas van desde 2020 hasta mañana. Corrígelas e intenta de nuevo.")).toBeInTheDocument();
  });
});

describe("AuditPage · detalle por ?seq= (US-103)", () => {
  it("una fila abre el detalle con ?seq= sin perder los filtros y cerrar lo quita", async () => {
    const { mock, router, user } = renderAuditPage(`${AUDIT_PATH}?action=update`);
    const table = await loadedTable();

    await user.click(within(table).getByRole("link", { name: "20 oct 2026, 11:52 a. m." }));

    const panel = await screen.findByRole("dialog", { name: "Entrada #88412" });
    const search = new URLSearchParams(router.state.location.search);
    expect(search.get("seq")).toBe("88412");
    expect(search.get("action")).toBe("update");
    expect(mock.callsTo("GET /audit/88412")).toHaveLength(1);
    // El seq no viaja a la lista.
    expect(lastList(mock.calls).has("seq")).toBe(false);

    await user.click(within(panel).getByRole("button", { name: "Cerrar" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(new URLSearchParams(router.state.location.search).has("seq")).toBe(false);
  });

  it("entrar con ?seq=abc no pide ningún detalle ni abre el panel", async () => {
    const { mock } = renderAuditPage(`${AUDIT_PATH}?seq=abc`);
    await loadedTable();

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.calls.filter((c) => c.path.startsWith("/audit/") && c.path !== "/audit/verify/last")).toEqual([]);
  });
});

describe("AuditPage · filtro por registro", () => {
  it("un record_id de la URL se ve como filtro y Quitar lo borra", async () => {
    const { router, user } = renderAuditPage(`${AUDIT_PATH}?table=members.members&record_id=${LAURA_ID}`);
    await loadedTable();

    expect(screen.getByText(new RegExp(LAURA_ID))).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Quitar el filtro de registro" }));

    await waitFor(() => {
      expect(new URLSearchParams(router.state.location.search).has("record_id")).toBe(false);
    });
    expect(new URLSearchParams(router.state.location.search).get("table")).toBe("members.members");
  });
});

describe("AuditPage · acceso y diseño", () => {
  it("solo el admin entra: el coach no ve la ruta", () => {
    expect(canAccessRoute("coach", "/sistema/auditoria")).toBe(false);
    expect(isPageAvailable("admin", "/sistema/auditoria")).toBe(true);
    expect(isPageAvailable("coach", "/sistema/auditoria")).toBe(false);
  });

  it("el usuario de una fila sin correo (cuenta borrada) se nombra sin inventar datos", async () => {
    renderAuditPage(AUDIT_PATH, { handlers: { "GET /audit": (call) => auditPageReply(call, [auditRow({ user_email: null, user_name: null, user_id: "12121212-1212-4212-8212-121212121212" })]) } });

    const table = await loadedTable();
    expect(within(table).getByText("Usuario sin cuenta")).toBeInTheDocument();
  });

  it("los DESIGN-GAP de S4A-D31 están escritos en el código de la pantalla", () => {
    const code = Object.entries(SOURCES)
      .filter(([path]) => /Audit|audit|VerifyChain/.test(path))
      .map(([, text]) => text)
      .join("\n");
    const gaps = code.split("\n").filter((line) => line.includes("DESIGN-GAP:")).join("\n");

    for (const topic of ["Qué cambió", "nombre del socio", "Exportar rango", "ML-DSA", "Resultado", "Llave", "enmascarad", "Descifrar"]) {
      expect(gaps).toContain(topic);
    }
    expect(code).not.toContain("dangerouslySetInnerHTML");
  });
});
