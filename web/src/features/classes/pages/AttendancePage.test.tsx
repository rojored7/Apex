// S7-F5 · US-162 (front): /clases/asistencia (pestaña «Asistencia por socio» de Sesiones.html), admin y coach (`classes.view`).
// - Rango de fechas en la URL (`from` y `to`, días civiles de Bogotá); sin él, las últimas 4 semanas hasta hoy. Hacia el api la
//   lista va en UTC `[from, to)` y el resumen en días civiles.
// - Rango invertido o de más de 26 semanas: no viaja, la pantalla lo explica. Marcas: todas, solo con marca, sin marca.
// - Tabla paginada en el servidor con socio (enlace a su ficha), clase, llegada, membresía al llegar y marcas con texto.
// - Resumen semanal (WeeklySummary) con su propia carga y su propio error: si falla, la lista sigue.
// - Estados: carga, vacío, error con Reintentar, 403, 429 y sin permiso (sin peticiones).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { ATTENDANCE_NOW, ATTENDANCE_ROWS, attendancePageReply, handlersFor, JUAN_ID, LAURA_ID, paramsOf, summaryReply } from "../../../test/attendance";
import { apiError } from "../../../test/classes";
import { renderPageAt } from "../../../test/attendancePage";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

const table = () => screen.getByRole("table", { name: "Asistencias" });
/** Laura llegó a dos clases: dos filas con su enlace. */
const waitRows = () => screen.findAllByRole("link", { name: "Laura Gómez" });
const where = () => screen.getByTestId("where").textContent;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: ATTENDANCE_NOW });
  setViewportWidth(1440);
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("AttendancePage · estructura", () => {
  it("título, pestaña activa, filtros y tabla con sus columnas", async () => {
    renderPageAt();

    expect(await screen.findByRole("heading", { level: 1, name: "Clases" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Asistencia por socio", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Buscar" })).toHaveAttribute("placeholder", "Nombre, documento o teléfono");
    expect(screen.getByLabelText("Desde")).toHaveValue("2026-09-23");
    expect(screen.getByLabelText("Hasta")).toHaveValue("2026-10-20");
    expect(screen.getByRole("combobox", { name: "Marcas" })).toHaveValue("");
    await waitRows();
    expect(within(table()).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Socio", "Clase", "Llegó", "Membresía al llegar", "Marcas"]);
  });

  it("sin fechas en la URL pide las últimas 4 semanas: la lista en UTC [desde, hasta+1) y el resumen en días civiles", async () => {
    const { mock } = renderPageAt();

    await waitRows();
    const [list] = paramsOf(mock, "GET /attendance");
    expect(list?.get("from")).toBe("2026-09-23T05:00:00.000Z");
    expect(list?.get("to")).toBe("2026-10-21T05:00:00.000Z");
    expect(list?.get("limit")).toBe("25");
    expect(list?.get("offset")).toBe("0");
    expect(list?.has("flagged")).toBe(false);
    expect(list?.has("q")).toBe(false);
    const [summary] = paramsOf(mock, "GET /attendance/summary");
    expect(summary?.get("from")).toBe("2026-09-23");
    expect(summary?.get("to")).toBe("2026-10-20");
  });

  it("cada fila: socio con enlace a su ficha, clase, llegada, membresía y marcas con texto (las desconocidas se descartan)", async () => {
    renderPageAt();

    expect((await waitRows())[0]).toHaveAttribute("href", `/socios/${LAURA_ID}`);
    expect(screen.getByRole("link", { name: "Juan Pérez" })).toHaveAttribute("href", `/socios/${JUAN_ID}`);
    const [, laura, juan] = within(table()).getAllByRole("row");
    const cells = (row: HTMLElement | undefined) => within(row as HTMLElement).getAllByRole("cell").map((c) => c.textContent);
    expect(cells(laura)).toEqual(["Laura Gómez", "20 oct 2026, 6:00 a. m.", "6:02 a. m.", "Al día", "—"]);
    expect(cells(juan)).toEqual(["Juan Pérez", "19 oct 2026, 6:00 p. m.", "6:05 p. m.", "Vencido", "VencidoOtro día"]);
  });

  it("un socio sin nombre (dado de baja) se ve como «Socio sin nombre»", async () => {
    const rows = [{ ...ATTENDANCE_ROWS[0], first_name: null, last_name: null }];
    renderPageAt(`/clases/asistencia`, handlersFor(rows as never));

    expect(await screen.findByRole("link", { name: "Socio sin nombre" })).toBeInTheDocument();
  });

  it("el resumen semanal se pinta con sus semanas", async () => {
    renderPageAt();

    expect(await screen.findByRole("heading", { level: 2, name: "Resumen por semana" })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Semana del 19 al 25 de octubre de 2026" })).toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad", async () => {
    const { container } = renderPageAt();

    await screen.findByRole("region", { name: /19 al 25/ });
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("AttendancePage · filtros", () => {
  it("cambiar «Desde» deja la fecha en la URL, vuelve al inicio y pide de nuevo lista y resumen", async () => {
    const { mock } = renderPageAt("/clases/asistencia?offset=25");
    await waitRows();

    fireEvent.change(screen.getByLabelText("Desde"), { target: { value: "2026-10-01" } });

    await waitFor(() => {
      expect(where()).toContain("from=2026-10-01");
    });
    expect(where()).not.toContain("offset=");
    await waitFor(() => {
      expect(paramsOf(mock, "GET /attendance").at(-1)?.get("from")).toBe("2026-10-01T05:00:00.000Z");
    });
    expect(paramsOf(mock, "GET /attendance/summary").at(-1)?.get("from")).toBe("2026-10-01");
  });

  it("rango invertido: no pide nada y explica qué corregir", async () => {
    const { mock } = renderPageAt("/clases/asistencia?from=2026-10-10&to=2026-10-01");

    expect(await screen.findByText("La fecha inicial no puede ser posterior a la final. Corrige el rango.")).toBeInTheDocument();
    expect(mock.callsTo("GET /attendance")).toHaveLength(0);
    expect(mock.callsTo("GET /attendance/summary")).toHaveLength(0);
  });

  it("rango de más de 26 semanas: no pide nada y dice el tope", async () => {
    const { mock } = renderPageAt("/clases/asistencia?from=2026-01-01&to=2026-10-20");

    expect(await screen.findByText("El rango no puede pasar de 26 semanas. Acórtalo y vuelve a intentar.")).toBeInTheDocument();
    expect(mock.callsTo("GET /attendance")).toHaveLength(0);
    expect(mock.callsTo("GET /attendance/summary")).toHaveLength(0);
  });

  it("exactamente 26 semanas (182 días) sí viaja", async () => {
    const { mock } = renderPageAt("/clases/asistencia?from=2026-04-22&to=2026-10-20");

    await waitRows();
    expect(mock.callsTo("GET /attendance/summary")).toHaveLength(1);
  });

  it("una fecha que no es real en la URL se ignora (vuelve al valor por omisión)", async () => {
    renderPageAt("/clases/asistencia?from=2026-13-45");

    await waitRows();
    expect(screen.getByLabelText("Desde")).toHaveValue("2026-09-23");
  });

  it("«Marcas» → «Solo con marca» viaja flagged=true y queda en la URL", async () => {
    const { mock, user } = renderPageAt();
    await waitRows();

    await user.selectOptions(screen.getByRole("combobox", { name: "Marcas" }), "true");

    await waitFor(() => {
      expect(paramsOf(mock, "GET /attendance").at(-1)?.get("flagged")).toBe("true");
    });
    expect(where()).toContain("flagged=true");
    // El resumen no se filtra por marca: es de toda la semana.
    expect(paramsOf(mock, "GET /attendance/summary").at(-1)?.has("flagged")).toBe(false);
  });

  it("un valor raro de flagged en la URL no viaja", async () => {
    const { mock } = renderPageAt("/clases/asistencia?flagged=quizas");

    await waitRows();
    expect(paramsOf(mock, "GET /attendance")[0]?.has("flagged")).toBe(false);
  });

  it("la búsqueda viaja como q pero nunca queda en la URL", async () => {
    const { mock, user } = renderPageAt();
    await waitRows();

    await user.type(screen.getByRole("searchbox", { name: "Buscar" }), "laura");

    await waitFor(() => {
      expect(paramsOf(mock, "GET /attendance").at(-1)?.get("q")).toBe("laura");
    });
    expect(where()).not.toContain("laura");
  });

  it("«Limpiar» vuelve al rango por omisión", async () => {
    const { user } = renderPageAt("/clases/asistencia?from=2026-10-01&flagged=true");
    await waitRows();

    await user.click(screen.getByRole("button", { name: "Limpiar" }));

    await waitFor(() => {
      expect(where()).toBe("/clases/asistencia");
    });
    expect(screen.getByLabelText("Desde")).toHaveValue("2026-09-23");
  });
});

describe("AttendancePage · paginación", () => {
  it("con 60 asistencias ofrece la página 2 y pide offset 25", async () => {
    const { mock, user } = renderPageAt("/clases/asistencia", { ...handlersFor(), "GET /attendance": (call) => attendancePageReply(call, ATTENDANCE_ROWS, 60) });
    await waitRows();

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));

    await waitFor(() => {
      expect(paramsOf(mock, "GET /attendance").at(-1)?.get("offset")).toBe("25");
    });
  });
});

describe("AttendancePage · estados", () => {
  it("vacío con filtros: guía a limpiarlos", async () => {
    renderPageAt("/clases/asistencia?flagged=true", { ...handlersFor(), "GET /attendance": (call) => attendancePageReply(call, []) });

    expect(await screen.findByText("No hay asistencias con estos filtros. Prueba con otro rango o limpia los filtros.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Limpiar filtros" }).length).toBeGreaterThan(0);
  });

  it("vacío sin filtros: guía a las clases de hoy", async () => {
    renderPageAt("/clases/asistencia", { ...handlersFor(), "GET /attendance": (call) => attendancePageReply(call, []) });

    expect(await screen.findByText("Todavía no hay asistencias en estas fechas. Aparecen cuando alguien registra su llegada en el check-in.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver las clases de hoy" })).toHaveAttribute("href", "/clases?dia=hoy");
  });

  it("error 500 en la lista: mensaje y Reintentar; el resumen sigue", async () => {
    let fail = true;
    const { user } = renderPageAt("/clases/asistencia", { ...handlersFor(), "GET /attendance": (call) => (fail ? apiError(500, "internal_error") : attendancePageReply(call, ATTENDANCE_ROWS)) });

    expect(await screen.findByText("No pudimos cargar las asistencias. Intenta de nuevo en un momento.")).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: /19 al 25/ })).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect((await waitRows())[0]).toBeInTheDocument();
  });

  it("403: dice que no tiene permiso", async () => {
    renderPageAt("/clases/asistencia", { ...handlersFor(), "GET /attendance": apiError(403, "forbidden") });

    expect(await screen.findByText("No tienes permiso para ver la asistencia. Si lo necesitas, pídeselo a un administrador.")).toBeInTheDocument();
  });

  it("429: dice cuánto esperar", async () => {
    renderPageAt("/clases/asistencia", { ...handlersFor(), "GET /attendance": apiError(429, "rate_limited", {}, { "Retry-After": "12" }) });

    expect(await screen.findByText("Hiciste muchas consultas seguidas. Espera 12 segundos e intenta de nuevo.")).toBeInTheDocument();
  });

  it("el resumen falla pero la lista sigue: el error del resumen trae su Reintentar", async () => {
    let fail = true;
    const { mock, user } = renderPageAt("/clases/asistencia", { ...handlersFor(), "GET /attendance/summary": () => (fail ? apiError(500, "internal_error") : summaryReply()) });

    expect((await waitRows())[0]).toBeInTheDocument();
    expect(await screen.findByText("No pudimos cargar el resumen por semana. Intenta de nuevo en un momento.")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar el resumen" }));
    expect(await screen.findByRole("region", { name: /19 al 25/ })).toBeInTheDocument();
    expect(mock.callsTo("GET /attendance/summary").length).toBeGreaterThanOrEqual(2);
  });

  it("mientras carga dice «Cargando resumen…»", async () => {
    renderPageAt("/clases/asistencia", { ...handlersFor(), "GET /attendance/summary": () => new Promise(() => undefined) });

    expect(await screen.findByText("Cargando resumen…")).toBeInTheDocument();
  });

  it("un rol sin classes.view no pide nada y lo dice", async () => {
    signInAs("member");
    const { mock } = renderPageAt();

    expect(await screen.findByText("No tienes permiso para ver la asistencia. Si lo necesitas, pídeselo a un administrador.")).toBeInTheDocument();
    expect(mock.callsTo("GET /attendance")).toHaveLength(0);
    expect(mock.callsTo("GET /attendance/summary")).toHaveLength(0);
  });
});
