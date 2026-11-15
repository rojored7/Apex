// S7-F5 · US-162 (front): pestaña Asistencia de la ficha (/socios/:id/asistencia), admin y coach (`classes.view`).
// Ruta hija de /socios/:id (S3-D65): la ficha la pinta en su <Outlet />.
// - Lista GET /members/{id}/attendance paginada en el servidor (25, 50 o 100; `offset` en la URL), sin la columna «Socio».
// - Resumen: última asistencia y total de los últimos 30 días (GET /attendance?member_id con `from`), con las marcas en texto.
// - Estados: carga, vacío (guía a las clases de hoy), error con Reintentar (404, 403, 429, 5xx) y página fuera de rango.
// DESIGN-GAP: la «racha» de Socio_Ficha.html no existe en el api (S7-D15): no se dibuja.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { ROUTE_TABLE } from "../../../config/routeTable";
import { ATTENDANCE_NOW, ATTENDANCE_ROWS, attendancePageReply, paramsOf } from "../../../test/attendance";
import { apiError } from "../../../test/classes";
import { MEMBER_ID, renderMemberTab } from "../../../test/memberTabs";
import { setViewportWidth, type MockHandler, type RecordedCall } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import MemberAttendanceTab from "./MemberAttendanceTab";

const LIST = `GET /members/${MEMBER_ID}/attendance`;

const rowsReply =
  (rows: readonly unknown[], total = rows.length): MockHandler =>
  (call: RecordedCall) =>
    attendancePageReply(call, rows, total);

/** La más reciente (sin `from`, total de siempre) y los últimos 30 días (con `from`) comparten GET /attendance. */
const statsReply: MockHandler = (call) => {
  const params = new URL(call.url, "http://apex.test").searchParams;
  return attendancePageReply(call, [ATTENDANCE_ROWS[0]], params.has("from") ? 14 : 120);
};

const renderTab = (extra: Record<string, MockHandler> = {}, entry?: string) =>
  renderMemberTab(MemberAttendanceTab, "asistencia", entry, { handlers: { [LIST]: rowsReply(ATTENDANCE_ROWS), "GET /attendance": statsReply, ...extra } });
const table = () => screen.getByRole("table", { name: "Asistencia del socio" });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: ATTENDANCE_NOW });
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("MemberAttendanceTab · registro (S3-D65)", () => {
  it("es una hija de /socios/:id de la feature classes, con carga diferida y acceso classes.view", () => {
    const route = ROUTE_TABLE.find((r) => r.path === "/socios/:id/asistencia");

    expect(route).toMatchObject({ parent: "/socios/:id", feature: "classes", access: "classes.view", layout: "panel" });
    expect(typeof route?.load).toBe("function");
  });
});

describe("MemberAttendanceTab · contenido", () => {
  it("pide la lista del socio con limit 25 y offset 0 y muestra sus columnas sin la de Socio", async () => {
    const { mock } = renderTab();

    await screen.findByText("20 oct 2026, 6:00 a. m.");
    expect(within(table()).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Clase", "Llegó", "Membresía al llegar", "Marcas"]);
    const [params] = paramsOf(mock, LIST);
    expect(params?.get("limit")).toBe("25");
    expect(params?.get("offset")).toBe("0");
    expect(params?.has("q")).toBe(false);
  });

  it("cada fila: clase, hora de llegada, membresía al llegar y las marcas con texto (las desconocidas se descartan)", async () => {
    renderTab();

    await screen.findByText("20 oct 2026, 6:00 a. m.");
    const [, laura, juan, congelada] = within(table()).getAllByRole("row");
    const cells = (row: HTMLElement | undefined) => within(row as HTMLElement).getAllByRole("cell").map((c) => c.textContent);
    expect(cells(laura)).toEqual(["20 oct 2026, 6:00 a. m.", "6:02 a. m.", "Al día", "—"]);
    expect(cells(juan)).toEqual(["19 oct 2026, 6:00 p. m.", "6:05 p. m.", "Vencido", "VencidoOtro día"]);
    expect(cells(congelada)).toEqual(["19 oct 2026, 6:00 a. m.", "6:00 a. m.", "Congelado", "Congelado"]);
  });

  it("el resumen dice la última asistencia y el total de los últimos 30 días", async () => {
    const { mock } = renderTab();

    expect(await screen.findByText("14 clases")).toBeInTheDocument();
    expect(screen.getByText("Última asistencia").closest("div")).toHaveTextContent("hoy, 6:02 a. m.");
    const calls = paramsOf(mock, "GET /attendance");
    const recent = calls.find((p) => p.has("from"));
    expect(recent?.get("member_id")).toBe(MEMBER_ID);
    expect(recent?.get("limit")).toBe("1");
    // 30 días: desde el 21 de septiembre (hoy 20 de octubre, Bogotá) a las 00:00.
    expect(recent?.get("from")).toBe("2026-09-21T05:00:00.000Z");
    expect(calls.find((p) => !p.has("from"))?.get("member_id")).toBe(MEMBER_ID);
  });

  it("singular: «1 clase»", async () => {
    renderTab({ "GET /attendance": rowsReply([ATTENDANCE_ROWS[0]], 1) });

    expect(await screen.findAllByText("1 clase")).not.toHaveLength(0);
  });

  it("no dibuja la «racha» (el api no la calcula)", async () => {
    renderTab();

    await screen.findByText("14 clases");
    expect(screen.queryByText(/racha/i)).toBeNull();
  });

  it("con total grande pagina en el servidor: la página 2 pide offset 25", async () => {
    const { mock, user } = renderTab({ [LIST]: rowsReply(ATTENDANCE_ROWS, 60) });

    await screen.findByText("20 oct 2026, 6:00 a. m.");
    await user.click(screen.getByRole("button", { name: /Siguiente/ }));
    await waitFor(() => {
      expect(paramsOf(mock, LIST).map((p) => p.get("offset"))).toContain("25");
    });
  });

  it("sin violaciones de accesibilidad", async () => {
    const { container } = renderTab();

    await screen.findByText("14 clases");
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("MemberAttendanceTab · estados", () => {
  it("vacío: dice que no hay asistencias y guía a las clases de hoy", async () => {
    renderTab({ [LIST]: rowsReply([]), "GET /attendance": rowsReply([], 0) });

    expect(await screen.findByText(/Este socio todavía no tiene asistencias/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver las clases de hoy" })).toHaveAttribute("href", "/clases?dia=hoy");
    expect(screen.getByText("Sin asistencias")).toBeInTheDocument();
  });

  it("error 500: mensaje en palabras de la pantalla y Reintentar vuelve a pedir", async () => {
    let fail = true;
    const { mock, user } = renderTab({ [LIST]: (call) => (fail ? apiError(500, "internal_error") : attendancePageReply(call, ATTENDANCE_ROWS)) });

    expect(await screen.findByText("No pudimos cargar la asistencia del socio. Intenta de nuevo en un momento.")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    await screen.findByText("20 oct 2026, 6:00 a. m.");
    expect(paramsOf(mock, LIST).length).toBeGreaterThanOrEqual(2);
  });

  it("404: el socio ya no existe", async () => {
    renderTab({ [LIST]: apiError(404, "member_not_found") });

    expect(await screen.findByText("Este socio ya no existe. Vuelve a Socios y búscalo de nuevo.")).toBeInTheDocument();
  });

  it("403: sin permiso", async () => {
    renderTab({ [LIST]: apiError(403, "forbidden") });

    expect(await screen.findByText(/No tienes permiso para ver la asistencia/)).toBeInTheDocument();
  });

  it("429: dice cuánto esperar", async () => {
    renderTab({ [LIST]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) });

    expect(await screen.findByText(/Hiciste muchas consultas seguidas\. Espera 30 segundos/)).toBeInTheDocument();
  });

  it("página fuera de rango: lo dice y ofrece la primera", async () => {
    renderTab({ [LIST]: rowsReply([], 40) }, `/socios/${MEMBER_ID}/asistencia?offset=50`);

    expect(await screen.findByText("Esta página ya no tiene asistencias.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ir a la primera página" })).toBeInTheDocument();
  });

  it("si el resumen falla, la lista sigue y el resumen lo dice sin romper la pestaña", async () => {
    renderTab({ "GET /attendance": apiError(500, "internal_error") });

    expect(await screen.findByText("20 oct 2026, 6:00 a. m.")).toBeInTheDocument();
    expect(screen.getAllByText("No disponible").length).toBeGreaterThan(0);
  });
});
