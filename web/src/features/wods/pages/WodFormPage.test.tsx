// S8-F2 · US-166 y US-167 (front): /wods/nuevo y /wods/:id/editar (WOD_Form.html).
// Zod, cargas en kg con hasta dos decimales enviadas en gramos enteros (S8-D41), el benchmark fija el tipo,
// un solo movimiento principal, 409 `wod_date_taken` bajo «Fecha», 422 `locked_by_results` bajo su campo y aviso con resultados.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { benchmarksPage, BENCHMARKS, movementsPage, MOVEMENTS, wodFull, WODS } from "../../../test/wods";
import WodFormPage from "./WodFormPage";

function renderPage(handlers: Record<string, MockHandler> = {}, entry = "/wods/nuevo?date=2026-10-24") {
  const mock = mockApi({ "GET /movements": movementsPage(), "GET /benchmarks": benchmarksPage(), ...handlers });
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/wods/nuevo" element={<WodFormPage />} />
            <Route path="/wods/:id/editar" element={<WodFormPage />} />
            <Route path="/wods/:id" element={<p>Detalle</p>} />
          </Routes>
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, user: userEvent.setup(), ...view };
}

async function addMovement(user: ReturnType<typeof userEvent.setup>, name: string) {
  await screen.findByRole("option", { name });
  await user.selectOptions(screen.getByRole("combobox", { name: "Agregar movimiento" }), name);
  await user.click(screen.getByRole("button", { name: "Agregar" }));
}

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("WodFormPage · crear", () => {
  it("precarga la fecha de ?date= y valida título y movimientos con Zod", async () => {
    const { user, mock } = renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Nuevo WOD" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Fecha/)).toHaveValue("2026-10-24");
    await user.click(screen.getByRole("button", { name: "Crear WOD" }));
    expect(await screen.findByText("Escribe el título del WOD (hasta 80 caracteres).")).toBeInTheDocument();
    expect(screen.getByText("Agrega al menos un movimiento.")).toBeInTheDocument();
    expect(mock.callsTo("POST /wods")).toHaveLength(0);
  });

  it("envía las cargas en gramos enteros: 102,5 kg es 102500", async () => {
    const { user, mock } = renderPage({ "POST /wods": { status: 201, body: wodFull(WODS.fran) } });
    await user.type(await screen.findByLabelText(/Título/), "Fuerza del día");
    await addMovement(user, "Back Squat");
    await user.type(screen.getByLabelText("Repeticiones de Back Squat"), "5x5");
    await user.type(screen.getByLabelText("Carga RX hombres (kg) de Back Squat"), "102,5");
    await user.type(screen.getByLabelText("Carga RX mujeres (kg) de Back Squat"), "70");
    await user.click(screen.getByRole("button", { name: "Crear WOD" }));
    await waitFor(() => {
      expect(mock.callsTo("POST /wods")).toHaveLength(1);
    });
    const body = mock.callsTo("POST /wods")[0]?.body as Record<string, unknown>;
    expect(body.date).toBe("2026-10-24");
    expect(body.title).toBe("Fuerza del día");
    expect(body.movements).toEqual([
      { movement_id: MOVEMENTS.squat.id, position: 1, reps: "5x5", load_rx_m_g: 102500, load_rx_f_g: 70000, is_primary: false, notes: "" },
    ]);
    expect(await screen.findByText("Detalle")).toBeInTheDocument();
  });

  it("rechaza más de dos decimales o más de 1.000 kg", async () => {
    const { user } = renderPage();
    await addMovement(user, "Back Squat");
    await user.type(screen.getByLabelText("Carga RX hombres (kg) de Back Squat"), "1,234");
    await user.click(screen.getByRole("button", { name: "Crear WOD" }));
    expect(await screen.findByText("La carga son kg con hasta dos decimales y no pasa de 1.000.")).toBeInTheDocument();
  });

  it("un benchmark fija el tipo de marca", async () => {
    const { user } = renderPage();
    await screen.findByRole("option", { name: "Cindy" });
    await user.selectOptions(screen.getByLabelText(/Benchmark/), BENCHMARKS.cindy.id);
    expect(screen.getByLabelText(/Tipo de marca/)).toHaveValue("rounds_reps");
    expect(screen.getByLabelText(/Tipo de marca/)).toBeDisabled();
  });

  it("solo un movimiento puede ser el principal", async () => {
    const { user } = renderPage();
    await addMovement(user, "Back Squat");
    await addMovement(user, "Pull-up");
    await user.click(screen.getByRole("radio", { name: "Principal: Back Squat" }));
    await user.click(screen.getByRole("radio", { name: "Principal: Pull-up" }));
    expect(screen.getByRole("radio", { name: "Principal: Back Squat" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Principal: Pull-up" })).toBeChecked();
  });

  it("la carga solo se pide en movimientos en kg", async () => {
    const { user } = renderPage();
    await addMovement(user, "Pull-up");
    expect(screen.queryByLabelText("Carga RX hombres (kg) de Pull-up")).not.toBeInTheDocument();
  });

  it("409 wod_date_taken va bajo «Fecha» con enlace al existente", async () => {
    const { user } = renderPage({ "POST /wods": apiError(409, "wod_date_taken", { field: "date", existing_id: WODS.fran.id }) });
    await user.type(await screen.findByLabelText(/Título/), "Otro");
    await addMovement(user, "Pull-up");
    await user.type(screen.getByLabelText("Repeticiones de Pull-up"), "10");
    await user.click(screen.getByRole("button", { name: "Crear WOD" }));
    expect(await screen.findByText(/Ya hay un WOD para esa fecha/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Abrir el WOD existente" })).toHaveAttribute("href", `/wods/${WODS.fran.id}/editar`);
  });

  it("el socio no ve el formulario", () => {
    signOutForTests();
    signInAs("member");
    renderPage();
    expect(screen.getByText(/No tienes permiso para editar WODs/)).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderPage();
    await screen.findByRole("heading", { level: 1, name: "Nuevo WOD" });
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("WodFormPage · editar", () => {
  const entry = `/wods/${WODS.fran.id}/editar`;
  const getKey = `GET /wods/${WODS.fran.id}`;
  const patchKey = `PATCH /wods/${WODS.fran.id}`;

  it("abre con los datos, cargas en kg y avisa de los resultados", async () => {
    renderPage({ [getKey]: { status: 200, body: wodFull(WODS.fran, { result_count: 3 }) } }, entry);
    expect(await screen.findByRole("heading", { level: 1, name: "Editar WOD" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Título/)).toHaveValue("Fran");
    expect(screen.getByLabelText("Carga RX hombres (kg) de Thruster")).toHaveValue("43");
    expect(screen.getByText(/Este WOD ya tiene 3 resultados/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Fecha/)).toBeDisabled();
  });

  it("PATCH lleva solo lo cambiado", async () => {
    const { user, mock } = renderPage({ [getKey]: { status: 200, body: wodFull(WODS.fran) }, [patchKey]: { status: 200, body: wodFull(WODS.fran) } }, entry);
    const title = await screen.findByLabelText(/Título/);
    await user.clear(title);
    await user.type(title, "Fran RX");
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => {
      expect(mock.callsTo(patchKey)).toHaveLength(1);
    });
    expect(mock.callsTo(patchKey)[0]?.body).toEqual({ title: "Fran RX" });
  });

  it("422 locked_by_results va bajo su campo", async () => {
    const { user } = renderPage({ [getKey]: { status: 200, body: wodFull(WODS.fran) }, [patchKey]: apiError(422, "locked_by_results", { field: "time_cap_s" }) }, entry);
    const cap = await screen.findByLabelText(/Time cap/);
    await user.clear(cap);
    await user.type(cap, "12");
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText(/ya tiene resultados/i, { selector: "p, span, div" })).toBeInTheDocument();
    expect(within(document.body).getAllByText(/Time cap/).length).toBeGreaterThan(0);
  });

  it("404 explica que el WOD ya no existe", async () => {
    renderPage({ [getKey]: apiError(404, "wod_not_found") }, entry);
    expect(await screen.findByText(/Este WOD ya no existe/)).toBeInTheDocument();
  });
});
