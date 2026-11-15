// S7-F4 · US-159 (front): /clases/:id/checkin (CheckIn.html), tablet del box, admin y coach (`classes.view`).
// - Contador «N / cupo llegaron», búsqueda de 3+ letras, «Llegó» (al día) o «Llegó igual» (vencida, sin plan...), «Vender» sin plan.
// - Las siete banderas salen con texto; `other_day` y `over_capacity` son advertencias (201), nunca error. 409 `already_checked_in` y `session_cancelled`.
// - S7-D24: la pantalla nunca llama GET /members/{id}, /reveal ni /attachments salvo la foto.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError, ATTENDEES, MEMBER_ROWS, membersPage, memberRow, SESSIONS, sessionDetail, sessionsPage } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler, type MockReply } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { GymLayout } from "../../../layouts/GymLayout";
import { KIOSK_MESSAGES } from "../../../core/auth/kiosk";
import CheckInPage from "./CheckInPage";

const ID = SESSIONS.hoy17.id;
const DETAIL = `GET /class-sessions/${ID}`;
const CREATED = { id: "new", flags: [], flagged: false, membership_status_at_checkin: "active", attendance_count: 4, capacity: 12 };

const searchReply: MockHandler = (call) => {
  const q = new URL(call.url, "http://apex.test").searchParams.get("q") ?? "";
  const rows = Object.values(MEMBER_ROWS).filter((r) => `${r.first_name} ${r.last_name}`.toLowerCase().includes(q.toLowerCase()));
  return membersPage(rows);
};

function renderPage(handlers: Record<string, MockHandler> = {}, client = testQueryClient()) {
  const mock = mockApi({ [DETAIL]: { status: 200, body: sessionDetail() }, "GET /members": searchReply, "POST /attendance": { status: 201, body: CREATED }, ...handlers });
  const view = render(
    <QueryClientProvider client={client}>
      <SessionRoleProvider>
        <MemoryRouter initialEntries={[`/clases/${ID}/checkin`]}>
          <Routes>
            <Route element={<GymLayout title="Check-in" exitTo="/clases" exitLabel="Clases" />}>
              <Route path="/clases/:id/checkin" element={<CheckInPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, user: userEvent.setup(), ...view };
}

const searchBox = () => screen.getByRole("searchbox", { name: "Buscar socio" });
const results = () => screen.getByRole("list", { name: "Socios encontrados" });
const row = (name: string) => within(results()).getByText(name).closest("li") as HTMLElement;

async function search(user: ReturnType<typeof userEvent.setup>, text: string) {
  await screen.findByText("Ya llegaron (3)");
  await user.type(searchBox(), text);
  await screen.findByRole("list", { name: "Socios encontrados" });
}

beforeEach(() => {
  signInAs("coach");
});
afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("CheckInPage · pantalla", () => {
  it("contador «3 / 12 llegaron», lista de los que ya llegaron con hora y banderas con texto", async () => {
    renderPage();

    expect(await screen.findByText("Ya llegaron (3)")).toBeInTheDocument();
    expect(screen.getByLabelText("Llegaron 3 de 12")).toHaveTextContent("3 / 12 llegaron");
    const list = screen.getByRole("list", { name: "Asistentes" });
    expect(within(list).getByText("Diego Mora")).toBeInTheDocument();
    const juan = within(list).getByText("Juan Pérez").closest("li") as HTMLElement;
    expect(within(juan).getByText("Vencido")).toHaveAttribute("data-flag", "expired");
    expect(within(juan).getByText("Otro día")).toHaveAttribute("data-flag", "other_day");
    expect(within(list).getByText("Pendiente de pago")).toHaveAttribute("data-flag", "pending_payment");
  });

  it("muestra cada tipo de bandera con su texto", async () => {
    const todas = ["expired", "no_membership", "frozen", "pending_payment", "over_capacity", "out_of_window", "other_day"];
    const [first] = ATTENDEES;
    renderPage({ [DETAIL]: { status: 200, body: sessionDetail({}, first ? [{ ...first, flagged: true, flags: todas }] : []) } });

    await screen.findByText("Ya llegaron (1)");
    for (const text of ["Vencido", "Sin plan", "Congelado", "Pendiente de pago", "Cupo lleno", "Fuera de horario", "Otro día"]) expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("sin asistentes guía al coach a buscar al primer socio", async () => {
    renderPage({ [DETAIL]: { status: 200, body: sessionDetail({}, []) } });

    expect(await screen.findByText(/Todavía no llegó nadie/)).toBeInTheDocument();
    expect(screen.getByLabelText("Llegaron 0 de 12")).toBeInTheDocument();
  });

  it("carga: anuncia que está cargando; error: dice qué hacer y Reintentar vuelve a pedir", async () => {
    let calls = 0;
    const handler: MockHandler = (): MockReply => (++calls === 1 ? apiError(500, "internal_error") : { status: 200, body: sessionDetail() });
    const { mock, user } = renderPage({ [DETAIL]: handler });

    expect(screen.getByRole("status", { name: "Cargando la sesión" })).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar la sesión. Intenta de nuevo en un momento.");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Ya llegaron (3)")).toBeInTheDocument();
    expect(mock.callsTo(DETAIL)).toHaveLength(2);
  });

  it("403 y 404 de la sesión tienen su propio mensaje", async () => {
    renderPage({ [DETAIL]: apiError(404, "session_not_found") });
    expect(await screen.findByRole("alert")).toHaveTextContent("Esta sesión ya no existe. Vuelve a Clases y elige otra.");
    cleanup();
    renderPage({ [DETAIL]: apiError(403, "forbidden") });
    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para registrar asistencia en esta clase.");
  });

  it("sesión cancelada: dice por qué y no ofrece buscar", async () => {
    renderPage({ [DETAIL]: { status: 200, body: sessionDetail({ status: "cancelled", cancel_reason: "festivo" }) } });

    expect(await screen.findByText(/Esta sesión fue cancelada/)).toHaveTextContent("festivo");
    expect(screen.queryByRole("searchbox", { name: "Buscar socio" })).toBeNull();
  });

  it("cupo lleno: avisa que la llegada se registra igual", async () => {
    renderPage({ [DETAIL]: { status: 200, body: sessionDetail({ capacity: 3 }) } });

    expect(await screen.findByText(/Cupo lleno: la llegada se registra igual/)).toBeInTheDocument();
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderPage();
    await screen.findByText("Ya llegaron (3)");

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("CheckInPage · registrar la llegada", () => {
  it("«Llegó» manda solo la sesión y el socio, confirma y limpia la búsqueda", async () => {
    const { mock, user } = renderPage();
    await search(user, "Laura");

    const laura = row("Laura Gómez");
    expect(within(laura).getByText("Al día")).toBeInTheDocument();
    await user.click(within(laura).getByRole("button", { name: "Llegó" }));

    expect(await screen.findByRole("status", { name: "Resultado del check-in" })).toHaveTextContent("Laura Gómez llegó.");
    expect(mock.callsTo("POST /attendance")[0]?.body).toEqual({ session_id: ID, member_id: "mem-laura" });
    await waitFor(() => expect(searchBox()).toHaveValue(""));
    await waitFor(() => { expect(mock.callsTo(DETAIL).length).toBeGreaterThan(1); });
  });

  it("L4: «Llegó» invalida [\"attendance\"] (Asistencia y la pestaña del socio se releen; la lista de socios y el historial lo hacen por staleTime)", async () => {
    const client = testQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { user } = renderPage({}, client);
    await search(user, "Laura");

    await user.click(within(row("Laura Gómez")).getByRole("button", { name: "Llegó" }));

    await screen.findByRole("status", { name: "Resultado del check-in" });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["attendance"] });
  });

  it("LOW a: tras «Llegó» el foco vuelve al buscador (la tablet sigue lista para el siguiente)", async () => {
    const { user } = renderPage();
    await search(user, "Laura");

    await user.click(within(row("Laura Gómez")).getByRole("button", { name: "Llegó" }));

    await waitFor(() => { expect(searchBox()).toHaveFocus(); });
  });

  it("vencida: marca «Vencido» y el botón dice «Llegó igual»; sin plan suma «Vender»", async () => {
    const { user } = renderPage();
    await search(user, "Cam");

    const camila = row("Camila Torres");
    expect(within(camila).getByText("Vencido")).toBeInTheDocument();
    expect(within(camila).getByRole("button", { name: "Llegó igual" })).toBeInTheDocument();
  });

  it("sin plan: «Llegó igual» y «Vender»; por vencer sigue siendo «Llegó»", async () => {
    const { user } = renderPage({ "GET /members": membersPage([MEMBER_ROWS.elena, MEMBER_ROWS.andres]) });
    await search(user, "ele");

    const elena = row("Elena Vargas");
    expect(within(elena).getByText("Sin plan")).toBeInTheDocument();
    expect(within(elena).getByRole("button", { name: "Llegó igual" })).toBeInTheDocument();
    expect(within(elena).getByRole("button", { name: "Vender" })).toBeInTheDocument();
    expect(within(row("Andrés Ruiz")).getByRole("button", { name: "Llegó" })).toBeInTheDocument();
  });

  it("quien ya llegó sale como «Ya llegó» y no se vuelve a registrar", async () => {
    const [first] = ATTENDEES;
    const { user } = renderPage({ "GET /members": membersPage([memberRow(first?.member_id ?? "x", "Diego", "Mora")]) });
    await search(user, "Die");

    expect(within(row("Diego Mora")).getByRole("button", { name: "Ya llegó" })).toBeDisabled();
  });

  it("other_day y over_capacity responden 201 y se muestran como advertencia, no como error", async () => {
    const body = { ...CREATED, flags: ["other_day", "over_capacity"], flagged: true, attendance_count: 13 };
    const { user } = renderPage({ "POST /attendance": { status: 201, body } });
    await search(user, "Laura");
    await user.click(within(row("Laura Gómez")).getByRole("button", { name: "Llegó" }));

    const status = await screen.findByRole("status", { name: "Resultado del check-in" });
    expect(status).toHaveTextContent("Laura Gómez llegó.");
    expect(within(status).getByText("Otro día")).toHaveAttribute("data-flag", "other_day");
    expect(within(status).getByText("Cupo lleno")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("409 already_checked_in: «Ya registró asistencia en esta clase» y relee la lista", async () => {
    const { mock, user } = renderPage({ "POST /attendance": apiError(409, "already_checked_in") });
    await search(user, "Laura");
    await user.click(within(row("Laura Gómez")).getByRole("button", { name: "Llegó" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Ya registró asistencia en esta clase.");
    await waitFor(() => { expect(mock.callsTo(DETAIL).length).toBeGreaterThan(1); });
  });

  it.each([
    [409, "session_cancelled", "Esta sesión fue cancelada. Ya no se puede registrar la llegada."],
    [404, "member_not_found", "Ese socio ya no existe. Búscalo de nuevo."],
    [429, "rate_limited", "Espera un momento"],
    [500, "internal_error", "No pudimos registrar la llegada. Intenta de nuevo."],
  ])("%i %s dice qué hacer", async (status, code, text) => {
    const { user } = renderPage({ "POST /attendance": apiError(status, code) });
    await search(user, "Laura");
    await user.click(within(row("Laura Gómez")).getByRole("button", { name: "Llegó" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(text);
  });

  it("no_llama_members_id_reveal_ni_attachments_salvo_foto", async () => {
    const withPhoto = memberRow("mem-laura", "Laura", "Gómez", { photo_attachment_id: "ph1" });
    const { mock, user } = renderPage({
      "GET /members": membersPage([withPhoto]),
      "GET /attachments/ph1": { status: 200, file: { content: "x", contentType: "image/png" } },
    });
    await search(user, "Laura");
    await user.click(within(row("Laura Gómez")).getByRole("button", { name: "Llegó" }));
    await screen.findByRole("status", { name: "Resultado del check-in" });

    const paths = mock.calls.map((c) => c.path);
    expect(paths.filter((p) => /^\/members\/[^/]+/.test(p))).toEqual([]);
    expect(paths.filter((p) => p.includes("reveal"))).toEqual([]);
    expect(paths.filter((p) => p.startsWith("/attachments"))).toEqual(["/attachments/ph1"]);
  });
});

describe("CheckInPage · selector «Clases de hoy» (S7-D42)", () => {
  const OTRA = { ...SESSIONS.hoy17, id: "e1e1e1e1-0000-4000-8000-0000000000aa", starts_at: "2026-10-20T23:00:00Z", name: "WOD noche" };

  function renderTablet(switchSession: (path: string) => Promise<string | null>) {
    const mock = mockApi({
      [DETAIL]: { status: 200, body: sessionDetail() },
      "GET /members": searchReply,
      "GET /class-sessions": sessionsPage([SESSIONS.hoy17, OTRA]),
    });
    renderTabletWith(switchSession);
    return mock;
  }

  function renderTabletWith(switchSession: (path: string) => Promise<string | null>) {
    render(
      <QueryClientProvider client={testQueryClient()}>
        <SessionRoleProvider>
          <MemoryRouter initialEntries={[`/clases/${ID}/checkin`]}>
            <Routes>
              <Route element={<GymLayout title="Check-in" exitTo="/clases" exitLabel="Clases" tablet={{ verifyPassword: () => Promise.resolve(null), onLeave: () => undefined, onIdle: () => undefined, switchSession }} />}>
                <Route path="/clases/:id/checkin" element={<CheckInPage />} />
              </Route>
            </Routes>
          </MemoryRouter>
        </SessionRoleProvider>
      </QueryClientProvider>,
    );
  }

  it("lista las sesiones programadas de hoy y al elegir otra pide cambiar de sesión por la ruta de su check-in", async () => {
    const switchSession = vi.fn(() => Promise.resolve<string | null>(null));
    const mock = renderTablet(switchSession);
    const user = userEvent.setup();

    const select = await screen.findByRole("combobox", { name: "Clases de hoy" });
    const query = new URL(mock.callsTo("GET /class-sessions")[0]?.url ?? "", "http://apex.test").searchParams;
    expect(query.get("status")).toBe("scheduled");
    expect(query.get("from")).toBe(query.get("to"));
    expect(within(select).getAllByRole("option")).toHaveLength(2);

    await user.selectOptions(select, OTRA.id);
    // M-5: elegir en la lista no cambia de clase; lo hace el botón.
    expect(switchSession).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Cambiar de clase" }));

    expect(switchSession).toHaveBeenCalledWith(`/clases/${OTRA.id}/checkin`);
  });

  it("M-5: «Cambiar de clase» está deshabilitado mientras la elegida sea la clase actual", async () => {
    renderTablet(() => Promise.resolve(null));

    await screen.findByRole("combobox", { name: "Clases de hoy" });

    expect(screen.getByRole("button", { name: "Cambiar de clase" })).toBeDisabled();
  });

  it("si el servidor no deja cambiar, lo dice y la sesión actual sigue", async () => {
    renderTablet(() => Promise.resolve(KIOSK_MESSAGES.notToday));
    const user = userEvent.setup();

    await user.selectOptions(await screen.findByRole("combobox", { name: "Clases de hoy" }), OTRA.id);
    await user.click(screen.getByRole("button", { name: "Cambiar de clase" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(KIOSK_MESSAGES.notToday);
  });

  it("si la sesión actual no está entre las de hoy, muestra «Elige otra clase» y deja pasar a cualquiera", async () => {
    const lejana = { ...SESSIONS.hoy17, id: "e1e1e1e1-0000-4000-8000-0000000000bb", starts_at: "2026-10-20T11:00:00Z" };
    const switchSession = vi.fn(() => Promise.resolve<string | null>(null));
    mockApi({ [DETAIL]: { status: 200, body: sessionDetail() }, "GET /members": searchReply, "GET /class-sessions": sessionsPage([lejana]) });
    renderTabletWith(switchSession);
    const user = userEvent.setup();

    const select = await screen.findByRole("combobox", { name: "Clases de hoy" });
    expect(within(select).getByRole("option", { name: "Elige otra clase" })).toBeInTheDocument();
    expect(select).toHaveValue("");
    await user.selectOptions(select, lejana.id);
    await user.click(screen.getByRole("button", { name: "Cambiar de clase" }));

    expect(switchSession).toHaveBeenCalledWith(`/clases/${lejana.id}/checkin`);
  });

  it("con una sola clase hoy y es la actual no hay selector", async () => {
    mockApi({ [DETAIL]: { status: 200, body: sessionDetail() }, "GET /members": searchReply, "GET /class-sessions": sessionsPage([SESSIONS.hoy17]) });
    renderTabletWith(() => Promise.resolve(null));
    await screen.findByText("Ya llegaron (3)");

    expect(screen.queryByRole("combobox", { name: "Clases de hoy" })).not.toBeInTheDocument();
  });

  it("fuera del modo tablet no hay selector", async () => {
    renderPage();
    await screen.findByText("Ya llegaron (3)");

    expect(screen.queryByRole("combobox", { name: "Clases de hoy" })).not.toBeInTheDocument();
  });
});

describe("CheckInPage · «Registrar resultados» (S8-F4, S8-D15)", () => {
  function renderTabletResults(switchSession: (path: string) => Promise<string | null>) {
    mockApi({ [DETAIL]: { status: 200, body: sessionDetail() }, "GET /members": searchReply, "GET /class-sessions": sessionsPage([SESSIONS.hoy17]) });
    render(
      <QueryClientProvider client={testQueryClient()}>
        <SessionRoleProvider>
          <MemoryRouter initialEntries={[`/clases/${ID}/checkin`]}>
            <Routes>
              <Route element={<GymLayout title="Check-in" exitTo="/clases" exitLabel="Clases" tablet={{ verifyPassword: () => Promise.resolve(null), onLeave: () => undefined, onIdle: () => undefined, switchSession }} />}>
                <Route path="/clases/:id/checkin" element={<CheckInPage />} />
              </Route>
            </Routes>
          </MemoryRouter>
        </SessionRoleProvider>
      </QueryClientProvider>,
    );
  }

  it("el botón pasa a los resultados de la misma clase por el cambio de clase del quiosco, sin contraseña", async () => {
    const switchSession = vi.fn(() => Promise.resolve<string | null>(null));
    renderTabletResults(switchSession);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Registrar resultados" }));
    expect(switchSession).toHaveBeenCalledWith(`/clases/${ID}/resultados`);
  });

  it("si el servidor rechaza el cambio, lo dice", async () => {
    const switchSession = vi.fn(() => Promise.resolve<string | null>(KIOSK_MESSAGES.notToday));
    renderTabletResults(switchSession);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Registrar resultados" }));
    expect(await screen.findByText(KIOSK_MESSAGES.notToday)).toBeInTheDocument();
  });
});
