// S7-F5 · US-163 (front): filtro «Última asistencia» y columna de /socios (Socios_Lista.html).
// - Un <select> dentro de FilterBar: Cualquiera, «Hace más de 7/14/30/60 días» y «Nunca» (`last_attendance=7d|14d|30d|60d|never`).
// - El valor vive en la URL, cambiarlo vuelve a la primera página y viaja al api; un valor desconocido de la URL no viaja.
// - La columna «Última asistencia» dice «hoy 07:02», «ayer 18:05», una fecha con año o «Nunca»; «Plan vigente» suma «quedan N».
// - La exportación lo acepta (C4c): con el filtro activo «Exportar» lo envía.
// - En quiosco el api rechaza los filtros; esta pantalla no se usa ahí.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { listCalls, MEMBERS, memberPage, renderMembers, type MemberRowFixture } from "../../../test/members";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { LAST_ATTENDANCE_FILTER_NAME, readLastAttendance } from "./LastAttendanceFilter";

const filter = () => screen.getByRole("combobox", { name: "Última asistencia" });
const table = () => screen.getByRole("table", { name: "Socios" });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-10-20T15:00:00Z") });
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("readLastAttendance", () => {
  it("solo deja pasar los cinco valores del api", () => {
    expect(LAST_ATTENDANCE_FILTER_NAME).toBe("last_attendance");
    for (const value of ["7d", "14d", "30d", "60d", "never"]) expect(readLastAttendance([value])).toBe(value);
    for (const value of ["", "mucho", "7D", "90d", "7d;drop"]) expect(readLastAttendance([value])).toBe("");
    expect(readLastAttendance([])).toBe("");
  });
});

describe("LastAttendanceFilter · select", () => {
  it("es un select con nombre accesible 'Última asistencia' y sus opciones en palabras", async () => {
    renderMembers();

    await screen.findByRole("link", { name: "Laura Gómez" });
    expect(within(filter()).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Cualquiera",
      "Hace más de 7 días",
      "Hace más de 14 días",
      "Hace más de 30 días",
      "Hace más de 60 días",
      "Nunca",
    ]);
    expect(filter()).toHaveValue("");
    expect(filter().tagName).toBe("SELECT");
  });

  it("elegir 30 días lo deja en la URL, vuelve a la primera página y viaja al api", async () => {
    const { mock, router, user } = renderMembers("/socios?offset=25");
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.selectOptions(filter(), "30d");

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.get("last_attendance")).toBe("30d");
    });
    expect(listCalls(mock).at(-1)?.get("offset")).toBe("0");
    expect(router.state.location.search).toContain("last_attendance=30d");
    expect(router.state.location.search).not.toContain("offset=");
    expect(filter()).toHaveValue("30d");
  });

  it("«Nunca» viaja como never", async () => {
    const { mock, user } = renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.selectOptions(filter(), "never");

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.get("last_attendance")).toBe("never");
    });
  });

  it("un valor desconocido en la URL no viaja", async () => {
    const { mock } = renderMembers("/socios?last_attendance=mucho");

    await screen.findByRole("link", { name: "Laura Gómez" });
    expect(listCalls(mock)[0]?.has("last_attendance")).toBe(false);
    expect(filter()).toHaveValue("");
  });

  it("el valor de la URL deja el select elegido y «Limpiar» lo quita", async () => {
    const { mock, user } = renderMembers("/socios?last_attendance=14d");
    await screen.findByRole("link", { name: "Laura Gómez" });
    expect(filter()).toHaveValue("14d");
    expect(listCalls(mock)[0]?.get("last_attendance")).toBe("14d");

    await user.click(screen.getByRole("button", { name: "Limpiar" }));

    await waitFor(() => {
      expect(filter()).toHaveValue("");
    });
  });

  it("con el filtro y sin resultados el vacío guía a limpiar filtros", async () => {
    renderMembers("/socios?last_attendance=60d", { handlers: { "GET /members": (call) => memberPage(call, []) } });

    expect(await screen.findByText("No hay socios que coincidan con la búsqueda")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Limpiar filtros" })).toBeInTheDocument();
  });
});

describe("LastAttendanceFilter · exportar", () => {
  it("con el filtro activo «Exportar» sigue y la exportación recibe last_attendance (el api lo acepta desde C4c)", async () => {
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:apex/1"), revokeObjectURL: vi.fn() }));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const { mock, user } = renderMembers("/socios?last_attendance=30d&sort=-created_at&limit=50", {
      handlers: { "GET /members/export": { status: 200, file: { content: "nombre\r\n", contentType: "text/csv", filename: "socios-20261120.csv" } } },
    });

    await screen.findByRole("link", { name: "Laura Gómez" });
    expect(screen.queryByText(/La exportación no admite/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Exportar" }));
    await user.click(within(screen.getByRole("dialog", { name: "¿Exportar la lista de socios?" })).getByRole("button", { name: "Descargar CSV" }));

    await waitFor(() => {
      expect(mock.callsTo("GET /members/export")).toHaveLength(1);
    });
    const params = new URL(mock.callsTo("GET /members/export")[0]?.url ?? "", "http://apex.test").searchParams;
    expect(Object.fromEntries(params)).toEqual({ last_attendance: "30d" });
  });

  it("sin el filtro «Exportar» sigue estando para el admin", async () => {
    renderMembers();

    await screen.findByRole("link", { name: "Laura Gómez" });
    expect(screen.getByRole("button", { name: "Exportar" })).toBeInTheDocument();
  });
});

describe("Última asistencia · columna", () => {
  const rows: MemberRowFixture[] = [
    { ...MEMBERS.laura, last_attendance_at: "2026-10-20T12:02:00Z" },
    { ...MEMBERS.andres, plan_name: "12 clases", membership_status: "expiring", membership_classes_remaining: 2, last_attendance_at: "2026-10-19T23:05:00Z" },
    { ...MEMBERS.elena, last_attendance_at: "2026-10-14T23:00:00Z" },
  ];

  it("dice hoy, ayer, la fecha con año o Nunca", async () => {
    renderMembers("/socios", { rows });

    await screen.findByRole("link", { name: "Laura Gómez" });
    const [, laura, andres, elena] = within(table()).getAllByRole("row");
    const last = (row: HTMLElement | undefined) => within(row as HTMLElement).getAllByRole("cell").at(-1)?.textContent;
    expect(last(laura)).toBe("hoy 07:02");
    expect(last(andres)).toBe("ayer 18:05");
    expect(last(elena)).toBe("14 oct 2026");
  });

  it("una tiquetera dice cuántas clases le quedan en «Plan vigente»", async () => {
    renderMembers("/socios", { rows });

    const link = await screen.findByRole("link", { name: "Andrés Ruiz" });
    const plan = within(link.closest("tr") as HTMLElement).getAllByRole("cell")[1];
    expect(plan).toHaveTextContent("12 clases · quedan 2");
  });

  it("sin clases que contar (plan mensual) «Plan vigente» queda con el nombre", async () => {
    renderMembers("/socios", { rows: [{ ...MEMBERS.laura, plan_name: "Mensual", membership_classes_remaining: null }] });

    const link = await screen.findByRole("link", { name: "Laura Gómez" });
    expect(within(link.closest("tr") as HTMLElement).getAllByRole("cell")[1]).toHaveTextContent(/^Mensual$/);
  });
});
