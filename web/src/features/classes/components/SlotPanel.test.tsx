// S7-F2 · US-155 (front): panel lateral para crear y editar una franja (Horario.html, «Editar franja · 17:00»).
// - Zod: al menos un día, hora HH:MM, duración 15 a 240, cupo 1 a 100, nombre hasta 40.
// - 409 `slot_conflict` va bajo los días; 422 `coach_invalid` bajo el coach; el coach sale de GET /users.
// - Al editar solo viajan los campos modificados (PATCH).
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError, CARLOS_ID, MARIA_ID, slot, SLOTS, usersPage } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import type { SlotView } from "../api";
import { SlotPanel } from "./SlotPanel";

function renderPanel(handlers: Record<string, MockHandler> = {}, target: SlotView | null = null) {
  const mock = mockApi({ "GET /users": usersPage, "POST /class-slots": { status: 201, body: slot("b2b2b2b2-0000-4000-8000-000000000009") }, ...handlers });
  const onClose = vi.fn();
  const onSaved = vi.fn();
  const onCancelFuture = vi.fn();
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter>
          <SlotPanel open slot={target} onClose={onClose} onSaved={onSaved} onCancelFuture={onCancelFuture} />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, onClose, onSaved, onCancelFuture, user: userEvent.setup(), ...view };
}

const day = (name: string) => screen.getByRole("checkbox", { name });
const field = (name: string | RegExp) => screen.getByLabelText(name);
const save = () => screen.getByRole("button", { name: /^(Crear franja|Guardar)/ });
const change = (label: string | RegExp, value: string): void => {
  fireEvent.change(field(label), { target: { value } });
};
const coachesLoaded = () => screen.findByRole("option", { name: "carlos@apex.test" });

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("SlotPanel · crear", () => {
  it("pide los datos de la franja y ofrece los coaches y admins activos más «Sin coach (open box)»", async () => {
    const { mock } = renderPanel();

    expect(screen.getByRole("dialog", { name: "Nueva franja" })).toBeInTheDocument();
    const coach = (await coachesLoaded()).closest("select");
    expect(coach).not.toBeNull();
    const options = within(coach as HTMLElement)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(options).toEqual(["Sin coach (open box)", "carlos@apex.test", "maria@apex.test"]);
    // L5: el servidor filtra por rol y estado; el socio ni siquiera se descarga.
    const queries = mock.callsTo("GET /users").map((c) => new URL(c.url, "http://apex.test").searchParams);
    expect(queries.map((q) => q.get("role")).sort()).toEqual(["admin", "coach"]);
    for (const q of queries) expect(q.get("status")).toBe("active");
    expect(screen.getByText(/Los cambios valen para las sesiones que aún no se generaron/)).toBeInTheDocument();
  });

  it("sin días, con cupo 0 y con duración fuera de rango no envía y lo dice bajo cada campo", async () => {
    const { user, mock } = renderPanel();
    await coachesLoaded();
    change(/^Hora de inicio/, "07:00");
    change(/^Duración/, "10");
    change(/^Cupo/, "0");

    await user.click(save());

    expect(await screen.findByText("Elige al menos un día.")).toBeInTheDocument();
    expect(screen.getByText("La duración debe estar entre 15 y 240 minutos.")).toBeInTheDocument();
    expect(screen.getByText("El cupo debe estar entre 1 y 100.")).toBeInTheDocument();
    expect(mock.callsTo("POST /class-slots")).toHaveLength(0);
  });

  it("envía días ordenados, hora, duración, cupo, coach y nombre, y avisa al padre", async () => {
    const { user, mock, onSaved } = renderPanel();
    await coachesLoaded();
    await user.click(day("Viernes"));
    await user.click(day("Lunes"));
    change(/^Hora de inicio/, "17:00");
    change(/^Duración/, "60");
    change(/^Cupo/, "12");
    await user.selectOptions(field("Coach"), MARIA_ID);
    await user.type(field("Nombre (opcional)"), "  Halterofilia ");

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo("POST /class-slots")[0]?.body).toEqual({
      weekdays: [0, 4],
      start_time: "17:00",
      duration_min: 60,
      capacity: 12,
      default_coach_id: MARIA_ID,
      name: "Halterofilia",
    });
  });

  it("un doble clic manda un solo POST", async () => {
    let release: () => void = () => undefined;
    const { user, mock } = renderPanel({
      "POST /class-slots": () =>
        new Promise((resolve) => {
          release = () => {
            resolve({ status: 201, body: slot("b2b2b2b2-0000-4000-8000-000000000009") });
          };
        }),
    });
    await coachesLoaded();
    await user.click(day("Lunes"));
    change(/^Hora de inicio/, "17:00");
    change(/^Cupo/, "12");

    await user.dblClick(save());

    expect(mock.callsTo("POST /class-slots")).toHaveLength(1);
    release();
  });

  it("409 slot_conflict va bajo los días y no cierra el panel", async () => {
    const { user, onSaved } = renderPanel({ "POST /class-slots": apiError(409, "slot_conflict") });
    await coachesLoaded();
    await user.click(day("Lunes"));
    change(/^Hora de inicio/, "17:00");
    change(/^Cupo/, "12");

    await user.click(save());

    expect(await screen.findByText("Ya hay una franja activa a esa hora en alguno de esos días. Cambia la hora o quita esos días.")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: /Días/ })).toHaveAccessibleDescription(expect.stringContaining("Ya hay una franja activa") as string);
  });

  it("422 coach_invalid va bajo el coach", async () => {
    const { user } = renderPanel({ "POST /class-slots": apiError(422, "coach_invalid", { field: "default_coach_id" }) });
    await coachesLoaded();
    await user.click(day("Lunes"));
    change(/^Hora de inicio/, "17:00");
    change(/^Cupo/, "12");
    await user.selectOptions(field("Coach"), CARLOS_ID);

    await user.click(save());

    expect(await screen.findByText("Ese usuario ya no puede ser coach. Elige otro o deja la franja sin coach.")).toBeInTheDocument();
  });

  it.each([
    [403, "forbidden", "Solo un administrador puede crear franjas. Si lo necesitas, pídeselo a uno."],
    [500, "internal_error", "No pudimos guardar la franja. Intenta de nuevo en un momento."],
  ])("%i %s como aviso del panel", async (status, code, message) => {
    const { user } = renderPanel({ "POST /class-slots": apiError(status, code) });
    await coachesLoaded();
    await user.click(day("Lunes"));
    change(/^Hora de inicio/, "17:00");
    change(/^Cupo/, "12");

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderPanel();
    await coachesLoaded();

    expect(await axe(container.ownerDocument.body)).toHaveNoViolations();
  });
});

describe("SlotPanel · editar", () => {
  const target = SLOTS.manana;

  it("precarga la franja y marca sus días", async () => {
    renderPanel({}, target);

    expect(screen.getByRole("dialog", { name: "Editar franja · 06:00" })).toBeInTheDocument();
    for (const name of ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]) expect(day(name)).toBeChecked();
    expect(day("Sábado")).not.toBeChecked();
    expect(field(/^Hora de inicio/)).toHaveValue("06:00");
    expect(field(/^Cupo/)).toHaveValue(12);
    expect(field("Nombre (opcional)")).toHaveValue("CrossFit");
    expect(screen.getByRole("checkbox", { name: "Activa" })).toBeChecked();
    await coachesLoaded();
    await waitFor(() => {
      expect(field("Coach")).toHaveValue(CARLOS_ID);
    });
  });

  it("solo envía los campos cambiados", async () => {
    const { user, mock, onSaved } = renderPanel({ [`PATCH /class-slots/${target.id}`]: { status: 200, body: { ...target, capacity: 15, is_active: false } } }, target);
    await coachesLoaded();
    change(/^Cupo/, "15");
    await user.click(screen.getByRole("checkbox", { name: "Activa" }));

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo(`PATCH /class-slots/${target.id}`)[0]?.body).toEqual({ capacity: 15, is_active: false });
  });

  it("quitar el coach y el nombre viaja como null", async () => {
    const { user, mock } = renderPanel({ [`PATCH /class-slots/${target.id}`]: { status: 200, body: target } }, target);
    await coachesLoaded();
    await waitFor(() => {
      expect(field("Coach")).toHaveValue(CARLOS_ID);
    });
    await user.selectOptions(field("Coach"), "");
    await user.clear(field("Nombre (opcional)"));

    await user.click(save());

    await waitFor(() => {
      expect(mock.callsTo(`PATCH /class-slots/${target.id}`)).toHaveLength(1);
    });
    expect(mock.callsTo(`PATCH /class-slots/${target.id}`)[0]?.body).toEqual({ default_coach_id: null, name: null });
  });

  it("sin cambios no envía nada y cierra", async () => {
    const { user, mock, onClose } = renderPanel({}, target);
    await coachesLoaded();
    await waitFor(() => {
      expect(field("Coach")).toHaveValue(CARLOS_ID);
    });

    await user.click(save());

    expect(onClose).toHaveBeenCalled();
    expect(mock.calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
  });

  it("404 slot_not_found dice que la franja ya no existe", async () => {
    const { user } = renderPanel({ [`PATCH /class-slots/${target.id}`]: apiError(404, "slot_not_found") }, target);
    await coachesLoaded();
    change(/^Cupo/, "15");

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("Esta franja ya no existe. Cierra el panel y actualiza la lista.");
  });

  it("con cambios sin guardar «Cancelar sesiones futuras» queda deshabilitado y dice por qué (L8)", async () => {
    const { user, onCancelFuture } = renderPanel({}, target);
    await coachesLoaded();
    expect(screen.getByRole("button", { name: "Cancelar sesiones futuras" })).toBeEnabled();

    change(/^Cupo/, "15");

    const button = screen.getByRole("button", { name: "Cancelar sesiones futuras" });
    expect(button).toBeDisabled();
    expect(screen.getByText("Guarda o descarta los cambios para cancelar sesiones futuras.")).toBeInTheDocument();
    await user.click(button);
    expect(onCancelFuture).not.toHaveBeenCalled();
  });

  it("ofrece «Cancelar sesiones futuras» y avisa al padre", async () => {
    const { user, onCancelFuture } = renderPanel({}, target);

    await user.click(screen.getByRole("button", { name: "Cancelar sesiones futuras" }));

    expect(onCancelFuture).toHaveBeenCalledWith(expect.objectContaining({ id: target.id }));
  });
});
