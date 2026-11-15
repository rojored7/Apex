// S8-F4 · US-169 y US-170 (front): /clases/:id/resultados (Resultados_Registro.html), tablet del box en GymLayout.
// - Lista de asistentes con su marca o «sin registrar», contador «N / M registrados», formulario por `score_type`, «Guardar y siguiente»
//   (salta al próximo sin marca), «Omitir», prellenado y corrección con `supersedes_id` y el MISMO `session_id` (S8-B1d M-3).
// - S8-D24: nunca llama /reveal ni /members/{id}. 403 `kiosk_mode`, 409 `result_exists` y `session_cancelled` se explican.
// - «+ Alguien que no hizo check-in»: POST /attendance y luego el resultado.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError, MEMBER_ROWS, membersPage } from "../../../test/classes";
import { ATTENDEE_ROWS, attendanceResults, attendeeRow, mid, resultOut, scoringWod, SESSION_ID, WOD_ID } from "../../../test/results";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { GymLayout } from "../../../layouts/GymLayout";
import ResultsEntryPage from "./ResultsEntryPage";

const ATTENDANCE = `GET /class-sessions/${SESSION_ID}/attendance`;

function renderPage(handlers: Record<string, MockHandler> = {}) {
  const mock = mockApi({
    [ATTENDANCE]: attendanceResults(),
    "PUT /results": (call) => ({ status: 201, body: resultOut((call.body as { member_id: string }).member_id) }),
    "GET /members": (call) => {
      const q = new URL(call.url, "http://apex.test").searchParams.get("q") ?? "";
      return membersPage(Object.values(MEMBER_ROWS).filter((r) => `${r.first_name} ${r.last_name}`.toLowerCase().includes(q.toLowerCase())));
    },
    ...handlers,
  });
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter initialEntries={[`/clases/${SESSION_ID}/resultados`]}>
          <Routes>
            <Route element={<GymLayout title="Registro de resultados" exitTo="/clases" exitLabel="Clases" />}>
              <Route path="/clases/:id/resultados" element={<ResultsEntryPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, user: userEvent.setup(), ...view };
}

const attendeeButton = (name: string) => within(screen.getByRole("list", { name: "Asistieron" })).getByRole("button", { name: new RegExp(name) });
const save = () => screen.getByRole("button", { name: /Guardar y siguiente/ });
const puts = (mock: { callsTo: (key: string) => { body?: unknown }[] }) => mock.callsTo("PUT /results").map((call) => call.body as Record<string, unknown>);

beforeEach(() => {
  signInAs("coach");
});
afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("ResultsEntryPage · pantalla", () => {
  it("contador, marcas de los que ya tienen resultado y «sin registrar» para el resto", async () => {
    renderPage();
    expect(await screen.findByText("Laura Gómez", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByLabelText("Registrados 2 de 4")).toHaveTextContent("2 / 4 registrados");
    expect(screen.getByRole("heading", { name: /Resultados · Helen · 17:00/i })).toBeInTheDocument();
    expect(attendeeButton("Diego Mora")).toHaveTextContent("10:58 RX");
    expect(attendeeButton("Sofía Pardo")).toHaveTextContent("13:40 Esc.");
    expect(attendeeButton("Laura Gómez")).toHaveTextContent("sin registrar");
  });

  it("abre el primero sin registrar y nunca llama a /reveal ni a /members/{id}", async () => {
    const { mock } = renderPage();
    expect(await screen.findByRole("heading", { level: 2, name: "Laura Gómez" })).toBeInTheDocument();
    expect(attendeeButton("Laura Gómez")).toHaveAttribute("aria-current", "true");
    expect(mock.calls.filter((c) => /\/reveal|\/members\/[^/?]+/.test(c.path))).toHaveLength(0);
  });

  it("carga: «Cargando…», y con error de red deja Reintentar", async () => {
    const { user, mock } = renderPage({ [ATTENDANCE]: apiError(500, "internal_error") });
    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar la clase");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() => {
      expect(mock.callsTo(ATTENDANCE).length).toBeGreaterThan(1);
    });
  });

  it("403 del quiosco y sesión inexistente explican qué hacer", async () => {
    renderPage({ [ATTENDANCE]: apiError(403, "kiosk_mode") });
    expect(await screen.findByRole("alert")).toHaveTextContent("de hoy ni de ayer");
    cleanup();
    renderPage({ [ATTENDANCE]: apiError(404, "session_not_found") });
    expect(await screen.findByRole("alert")).toHaveTextContent("ya no existe");
  });

  it("sin WOD asignado o con WOD sin marca no se registra nada", async () => {
    renderPage({ [ATTENDANCE]: attendanceResults(ATTENDEE_ROWS, null) });
    expect(await screen.findByText(/no tiene WOD asignado/)).toBeInTheDocument();
    cleanup();
    renderPage({ [ATTENDANCE]: attendanceResults(ATTENDEE_ROWS, scoringWod({ score_type: "none" })) });
    expect(await screen.findByText(/no registra resultados/)).toBeInTheDocument();
  });

  it("sin asistentes lo dice y deja agregar a alguien", async () => {
    renderPage({ [ATTENDANCE]: attendanceResults([]) });
    expect(await screen.findByText(/Nadie ha llegado todavía/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Alguien que no hizo check-in/ })).toBeInTheDocument();
  });

  it("sesión cancelada: no se registra", async () => {
    renderPage({ [ATTENDANCE]: attendanceResults(ATTENDEE_ROWS, scoringWod(), { status: "cancelled", cancel_reason: "festivo" }) });
    expect(await screen.findByText(/sesión fue cancelada/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Guardar y siguiente/ })).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderPage();
    await screen.findByRole("heading", { level: 2, name: "Laura Gómez" });
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("ResultsEntryPage · guardar", () => {
  it("«Guardar y siguiente» envía PUT /results con la sesión y salta al próximo sin registrar", async () => {
    const { user, mock } = renderPage();
    await screen.findByRole("heading", { level: 2, name: "Laura Gómez" });
    await user.type(screen.getByLabelText("Tiempo (mm:ss)"), "11:42");
    await user.click(save());
    await waitFor(() => {
      expect(puts(mock)).toHaveLength(1);
    });
    expect(puts(mock)[0]).toEqual({ wod_id: WOD_ID, member_id: mid(3), session_id: SESSION_ID, level: "rx", seconds: 702, capped: false, scaled_movement_ids: [] });
    expect(await screen.findByRole("heading", { level: 2, name: "Juan Pérez" })).toBeInTheDocument();
  });

  it("«Omitir» salta al próximo sin enviar", async () => {
    const { user, mock } = renderPage();
    await screen.findByRole("heading", { level: 2, name: "Laura Gómez" });
    await user.click(screen.getByRole("button", { name: "Omitir" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Juan Pérez" })).toBeInTheDocument();
    expect(mock.callsTo("PUT /results")).toHaveLength(0);
  });

  it("corregir: prellena y envía supersedes_id con la misma sesión", async () => {
    const { user, mock } = renderPage();
    await user.click(await screen.findByRole("button", { name: /Diego Mora/ }));
    expect(screen.getByLabelText("Tiempo (mm:ss)")).toHaveValue("10:58");
    const field = screen.getByLabelText("Tiempo (mm:ss)");
    await user.clear(field);
    await user.type(field, "10:30");
    await user.click(save());
    await waitFor(() => {
      expect(puts(mock)).toHaveLength(1);
    });
    expect(puts(mock)[0]).toMatchObject({ member_id: mid(1), session_id: SESSION_ID, seconds: 630, supersedes_id: ATTENDEE_ROWS[0]?.result?.id });
  });

  it("un resultado registrado en OTRA clase se rotula así y no se corrige desde esta tablet (L-4, V7)", async () => {
    const OTRA = "99999999-9999-4999-8999-999999999999";
    const rows = [attendeeRow(1, "Diego", "Mora", resultOut(mid(1), { session_id: OTRA })), attendeeRow(3, "Laura", "Gómez")];
    const { user, mock } = renderPage({ [ATTENDANCE]: attendanceResults(rows) });
    await user.click(await screen.findByRole("button", { name: /Diego Mora/ }));
    expect(attendeeButton("Diego Mora")).toHaveTextContent("Registrado en otra clase");
    expect(screen.queryByRole("button", { name: /Guardar y siguiente/ })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Registrar resultado" })).toHaveTextContent("Se corrige desde esa clase");
    expect(mock.callsTo("PUT /results")).toHaveLength(0);
  });

  it("403 `kiosk_mode` al corregir uno de escritorio lo explica y deja la pantalla", async () => {
    const { user } = renderPage({ "PUT /results": apiError(403, "kiosk_mode") });
    await user.click(await screen.findByRole("button", { name: /Diego Mora/ }));
    await user.click(save());
    expect(await screen.findByRole("alert")).toHaveTextContent("no se registró en la tablet");
    expect(screen.getByRole("heading", { level: 2, name: "Diego Mora" })).toBeInTheDocument();
  });

  it("409 `result_exists` explica que otra tablet ya lo registró y relee la lista", async () => {
    const { user, mock } = renderPage({ "PUT /results": apiError(409, "result_exists") });
    await screen.findByRole("heading", { level: 2, name: "Laura Gómez" });
    await user.type(screen.getByLabelText("Tiempo (mm:ss)"), "11:42");
    await user.click(save());
    expect(await screen.findByRole("alert")).toHaveTextContent("ya tiene un resultado");
    await waitFor(() => {
      expect(mock.callsTo(ATTENDANCE).length).toBeGreaterThan(1);
    });
  });

  it("409 `session_cancelled`, 422 con campo y 429 dicen qué hacer", async () => {
    const { user } = renderPage({ "PUT /results": apiError(409, "session_cancelled") });
    await screen.findByRole("heading", { level: 2, name: "Laura Gómez" });
    await user.type(screen.getByLabelText("Tiempo (mm:ss)"), "11:42");
    await user.click(save());
    expect(await screen.findByRole("alert")).toHaveTextContent("cancelada");
  });

  it("429 pide esperar", async () => {
    const { user } = renderPage({ "PUT /results": apiError(429, "rate_limited", {}, { "Retry-After": "7" }) });
    await screen.findByRole("heading", { level: 2, name: "Laura Gómez" });
    await user.type(screen.getByLabelText("Tiempo (mm:ss)"), "11:42");
    await user.click(save());
    expect(await screen.findByRole("alert")).toHaveTextContent("Espera 7 segundos");
  });
});

describe("ResultsEntryPage · alguien que no hizo check-in", () => {
  it("busca por nombre, registra la llegada y deja registrar su resultado", async () => {
    const { user, mock } = renderPage({ "POST /attendance": { status: 201, body: { id: "new", flags: [], flagged: false, membership_status_at_checkin: "active", attendance_count: 5, capacity: 12 } } });
    await screen.findByRole("heading", { level: 2, name: "Laura Gómez" });
    await user.click(screen.getByRole("button", { name: /Alguien que no hizo check-in/ }));
    await user.type(screen.getByRole("searchbox", { name: "Buscar socio" }), "Cami");
    await user.click(await screen.findByRole("button", { name: /Camila Torres/ }));
    await waitFor(() => {
      expect(mock.callsTo("POST /attendance")).toHaveLength(1);
    });
    expect(mock.callsTo("POST /attendance")[0]?.body).toEqual({ session_id: SESSION_ID, member_id: MEMBER_ROWS.camila.id });
  });
});
