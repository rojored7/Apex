// S7-F2 · US-155 y US-158 (front): /clases/horario (Horario.html), solo admin (`classes.schedule`).
// - Tabla de franjas: hora, días «L M X J V», coach («Open box · sin coach»), cupo, duración, estado
//   («Activa» o «Pausada») y acciones Editar y Cancelar sesiones futuras.
// - «+ Franja horaria» y «Editar» abren SlotPanel; «Cancelar sesiones futuras» abre CancelFutureModal.
// - Estados: carga, vacío, error con Reintentar, permiso denegado (el coach no ve el Horario).
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError, SLOTS, slotsPage, usersPage } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import SchedulePage from "./SchedulePage";

function renderPage(handlers: Record<string, MockHandler> = {}) {
  const mock = mockApi({ "GET /class-slots": slotsPage(), "GET /users": usersPage, ...handlers });
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter initialEntries={["/clases/horario"]}>
          <SchedulePage />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, user: userEvent.setup(), ...view };
}

const rowOf = (text: string) => screen.getByText(text).closest("tr") as HTMLElement;

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("SchedulePage · estructura (Horario.html)", () => {
  it("título, pestañas y la nota de que el horario es la plantilla", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { level: 1, name: "Clases" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Sesiones" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Horario semanal", selected: true })).toBeInTheDocument();
    expect(screen.getByText(/El horario es la plantilla/)).toBeInTheDocument();
  });

  it("la tabla muestra días «L M X J V», «Open box · sin coach» y «Pausada»", async () => {
    renderPage();

    await screen.findByText("06:00");
    const manana = rowOf("06:00");
    expect(within(manana).getByText("L M X J V")).toBeInTheDocument();
    expect(within(manana).getByText("Carlos")).toBeInTheDocument();
    expect(within(manana).getByText("60 min")).toBeInTheDocument();
    expect(within(manana).getByText("Activa")).toHaveAttribute("data-slot", "active");
    const open = rowOf("09:30");
    expect(within(open).getByText("Open box · sin coach")).toBeInTheDocument();
    expect(within(open).getByText("S")).toBeInTheDocument();
    expect(within(open).getByText("90 min")).toBeInTheDocument();
    const pausada = rowOf("12:00");
    expect(within(pausada).getByText("L X V")).toBeInTheDocument();
    expect(within(pausada).getByText("Pausada")).toHaveAttribute("data-slot", "paused");
  });

  it("pide las franjas paginadas al servidor", async () => {
    const { mock } = renderPage();

    await screen.findByText("06:00");
    const url = new URL(mock.callsTo("GET /class-slots")[0]?.url ?? "", "http://apex.test");
    expect(url.searchParams.get("limit")).toBe("25");
    expect(url.searchParams.get("offset")).toBe("0");
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderPage();
    await screen.findByText("06:00");

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("SchedulePage · estados", () => {
  it("sin franjas guía a crear la primera", async () => {
    renderPage({ "GET /class-slots": slotsPage([]) });

    expect(await screen.findByText("Todavía no hay franjas. El horario semanal es la plantilla de las sesiones.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Franja horaria/ }).length).toBeGreaterThan(0);
  });

  it("error 500 con Reintentar", async () => {
    let calls = 0;
    const { user } = renderPage({
      "GET /class-slots": () => {
        calls += 1;
        return calls === 1 ? apiError(500, "internal_error") : slotsPage();
      },
    });

    expect(await screen.findByText("No pudimos cargar el horario. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("06:00")).toBeInTheDocument();
  });

  it("el coach no ve el Horario: permiso denegado y ninguna petición", () => {
    signInAs("coach");
    const { mock } = renderPage();

    expect(screen.getByRole("heading", { name: "No tienes permiso para ver el horario" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Horario semanal" })).toBeNull();
    expect(mock.callsTo("GET /class-slots")).toHaveLength(0);
  });

  it("un 403 del api se dice como permiso", async () => {
    renderPage({ "GET /class-slots": apiError(403, "forbidden") });

    expect(await screen.findByText("No tienes permiso para ver el horario. Si lo necesitas, pídeselo a un administrador.")).toBeInTheDocument();
  });
});

describe("SchedulePage · acciones", () => {
  it("«+ Franja horaria» abre el panel de una franja nueva", async () => {
    const { user } = renderPage();
    await screen.findByText("06:00");

    await user.click(screen.getByRole("button", { name: "+ Franja horaria" }));

    expect(screen.getByRole("dialog", { name: "Nueva franja" })).toBeInTheDocument();
  });

  it("«Editar» abre el panel con la franja de la fila", async () => {
    const { user } = renderPage();
    await screen.findByText("09:30");

    await user.click(within(rowOf("09:30")).getByRole("button", { name: "Editar la franja de las 09:30" }));

    expect(screen.getByRole("dialog", { name: "Editar franja · 09:30" })).toBeInTheDocument();
  });

  it("«Cancelar sesiones futuras» abre el modal y, al terminar, avisa cuántas se cancelaron", async () => {
    const { user } = renderPage({ [`POST /class-slots/${SLOTS.manana.id}/cancel-future-sessions`]: { status: 200, body: { cancelled_count: 2 } } });
    await screen.findByText("06:00");

    await user.click(within(rowOf("06:00")).getByRole("button", { name: "Cancelar sesiones futuras de la franja de las 06:00" }));
    const dialog = screen.getByRole("dialog", { name: "¿Cancelar las sesiones futuras de la franja de las 06:00?" });
    await user.type(within(dialog).getByRole("textbox", { name: /^Motivo/ }), "La clase pasa a las 06:30");
    await user.click(within(dialog).getByRole("button", { name: "Sí, cancelar sesiones" }));

    expect(await screen.findByText("Se cancelaron 2 sesiones futuras de la franja de las 06:00. La franja sigue activa.")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });

  it("sin sesiones futuras el aviso dice que no había nada que cancelar", async () => {
    const { user } = renderPage({ [`POST /class-slots/${SLOTS.manana.id}/cancel-future-sessions`]: { status: 200, body: { cancelled_count: 0 } } });
    await screen.findByText("06:00");

    await user.click(within(rowOf("06:00")).getByRole("button", { name: "Cancelar sesiones futuras de la franja de las 06:00" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByRole("textbox", { name: /^Motivo/ }), "Prueba de cambio");
    await user.click(within(dialog).getByRole("button", { name: "Sí, cancelar sesiones" }));

    expect(await screen.findByText("La franja de las 06:00 no tenía sesiones futuras por cancelar.")).toBeInTheDocument();
  });
});
