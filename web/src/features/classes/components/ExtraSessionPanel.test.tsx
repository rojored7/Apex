// S7-F3 · US-157 (front): sesión extra (Sesiones.html, «+ Sesión extra»), panel lateral para admin y coach.
// - Fecha y hora de Bogotá (se envía en UTC), duración 15 a 240, cupo opcional (1 a 100), nombre opcional.
// - Coach: el admin elige entre los coaches y admins activos (GET /users) o nadie; el coach solo puede ponerse a sí mismo o a nadie.
// - 409 `session_duplicate` y 422 `starts_at` bajo la fecha; `coach_invalid` bajo el coach; el resto como aviso del panel.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError, CARLOS_ID, MARIA_ID, session, usersPage } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { ExtraSessionPanel } from "./ExtraSessionPanel";

const EXTRA = session("f2f2f2f2-0000-4000-8000-000000000009", { slot_id: null, session_date: "2026-10-21", starts_at: "2026-10-21T23:00:00Z" });

function renderPanel(handlers: Record<string, MockHandler> = {}) {
  const mock = mockApi({ "GET /users": usersPage, "POST /class-sessions": { status: 201, body: EXTRA }, ...handlers });
  const onClose = vi.fn();
  const onCreated = vi.fn();
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter>
          <ExtraSessionPanel open onClose={onClose} onCreated={onCreated} />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, onClose, onCreated, user: userEvent.setup(), ...view };
}

const field = (name: string | RegExp) => screen.getByLabelText(name);
const change = (label: string | RegExp, value: string): void => {
  fireEvent.change(field(label), { target: { value } });
};
const save = () => screen.getByRole("button", { name: /^Crear sesión/ });
const fillValid = (): void => {
  change(/^Fecha y hora/, "2026-10-21T18:00");
  change(/^Duración/, "60");
};
const bodies = (mock: { callsTo: (key: string) => { body: unknown }[] }) => mock.callsTo("POST /class-sessions").map((c) => c.body);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-10-20T15:00:00Z") });
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("ExtraSessionPanel · admin", () => {
  beforeEach(() => {
    signInAs("admin");
  });

  it("empieza con la hora de ahora en Bogotá y ofrece los coaches y «Sin coach (open box)»", async () => {
    renderPanel();

    expect(screen.getByRole("dialog", { name: "Sesión extra" })).toBeInTheDocument();
    expect(field(/^Fecha y hora/)).toHaveValue("2026-10-20T10:00");
    const coach = (await screen.findByRole("option", { name: "carlos@apex.test" })).closest("select") as HTMLElement;
    expect(within(coach).getAllByRole("option").map((o) => o.textContent)).toEqual(["Sin coach (open box)", "carlos@apex.test", "maria@apex.test"]);
  });

  it("envía la hora de Bogotá en UTC, la duración, el cupo, el coach y el nombre", async () => {
    const { user, mock, onCreated } = renderPanel();
    await screen.findByRole("option", { name: "carlos@apex.test" });
    fillValid();
    change(/^Cupo/, "10");
    await user.selectOptions(field("Coach"), MARIA_ID);
    await user.type(field("Nombre (opcional)"), "Open box festivo");

    await user.click(save());

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledTimes(1);
    });
    expect(bodies(mock)).toEqual([{ starts_at: "2026-10-21T23:00:00.000Z", duration_min: 60, capacity: 10, coach_id: MARIA_ID, name: "Open box festivo" }]);
  });

  it("sin cupo ni nombre ni coach solo viajan la hora, la duración y coach_id null", async () => {
    const { user, mock } = renderPanel();
    await screen.findByRole("option", { name: "carlos@apex.test" });
    fillValid();

    await user.click(save());

    await waitFor(() => {
      expect(bodies(mock)).toHaveLength(1);
    });
    expect(bodies(mock)[0]).toEqual({ starts_at: "2026-10-21T23:00:00.000Z", duration_min: 60, coach_id: null });
  });

  it("sin fecha, con duración fuera de rango o cupo 0 no envía y lo dice bajo cada campo", async () => {
    const { user, mock } = renderPanel();
    await screen.findByRole("option", { name: "carlos@apex.test" });
    change(/^Fecha y hora/, "");
    change(/^Duración/, "5");
    change(/^Cupo/, "0");

    await user.click(save());

    expect(await screen.findByText("Indica la fecha y la hora de inicio.")).toBeInTheDocument();
    expect(screen.getByText("La duración debe estar entre 15 y 240 minutos.")).toBeInTheDocument();
    expect(screen.getByText("El cupo debe estar entre 1 y 100, o déjalo vacío para usar el de Configuración.")).toBeInTheDocument();
    expect(bodies(mock)).toHaveLength(0);
  });

  it("un doble clic manda un solo POST", async () => {
    let release: () => void = () => undefined;
    const { user, mock } = renderPanel({
      "POST /class-sessions": () =>
        new Promise((resolve) => {
          release = () => {
            resolve({ status: 201, body: EXTRA });
          };
        }),
    });
    await screen.findByRole("option", { name: "carlos@apex.test" });
    fillValid();

    await user.dblClick(save());
    release();

    await waitFor(() => {
      expect(bodies(mock)).toHaveLength(1);
    });
  });

  it("409 session_duplicate va bajo la fecha", async () => {
    const { user, onCreated } = renderPanel({ "POST /class-sessions": apiError(409, "session_duplicate") });
    await screen.findByRole("option", { name: "carlos@apex.test" });
    fillValid();

    await user.click(save());

    expect(await screen.findByText("Ya existe una sesión extra con ese horario y ese coach. Cambia la hora o el coach.")).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("422 starts_at dice el rango permitido bajo la fecha", async () => {
    const { user } = renderPanel({ "POST /class-sessions": apiError(422, "validation_error", { field: "starts_at" }) });
    await screen.findByRole("option", { name: "carlos@apex.test" });
    fillValid();

    await user.click(save());

    expect(await screen.findByText("La sesión debe empezar entre ayer y los próximos 90 días.")).toBeInTheDocument();
  });

  it("422 coach_invalid va bajo el coach", async () => {
    const { user } = renderPanel({ "POST /class-sessions": apiError(422, "coach_invalid", { field: "coach_id" }) });
    await screen.findByRole("option", { name: "carlos@apex.test" });
    fillValid();
    await user.selectOptions(field("Coach"), CARLOS_ID);

    await user.click(save());

    expect(await screen.findByText("Ese usuario ya no puede ser coach. Elige otro o deja la sesión sin coach.")).toBeInTheDocument();
  });

  it.each([
    [403, "forbidden", "No tienes permiso para crear sesiones. Si lo necesitas, pídeselo a un administrador."],
    [429, "rate_limited", "Hiciste muchos cambios seguidos. Espera un momento e intenta de nuevo."],
    [500, "internal_error", "No pudimos crear la sesión. Intenta de nuevo en un momento."],
  ])("%i %s como aviso del panel", async (status, code, message) => {
    const { user } = renderPanel({ "POST /class-sessions": apiError(status, code) });
    await screen.findByRole("option", { name: "carlos@apex.test" });
    fillValid();

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderPanel();
    await screen.findByRole("option", { name: "carlos@apex.test" });

    expect(await axe(container.ownerDocument.body)).toHaveNoViolations();
  });
});

describe("ExtraSessionPanel · hora inicial al abrir (L8)", () => {
  it("cada vez que se abre vuelve a la hora de ahora, no a la de cuando se montó", async () => {
    signInAs("admin");
    mockApi({ "GET /users": usersPage });
    const props = { onClose: vi.fn(), onCreated: vi.fn() };
    const tree = (open: boolean) => (
      <QueryClientProvider client={testQueryClient()}>
        <SessionRoleProvider>
          <MemoryRouter>
            <ExtraSessionPanel open={open} {...props} />
          </MemoryRouter>
        </SessionRoleProvider>
      </QueryClientProvider>
    );
    const view = render(tree(false));
    vi.setSystemTime(new Date("2026-10-20T20:30:00Z"));

    view.rerender(tree(true));

    await waitFor(() => {
      expect(field(/^Fecha y hora/)).toHaveValue("2026-10-20T15:30");
    });
  });
});

describe("ExtraSessionPanel · coach", () => {
  it("solo puede ponerse a sí mismo o a nadie y no lee la lista de usuarios", async () => {
    const me = signInAs("coach");
    const { user, mock } = renderPanel();

    const select = field("Coach") as HTMLSelectElement;
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Sin coach (open box)", "Yo (coach@apex.test)"]);
    fillValid();
    await user.selectOptions(select, me.id);
    await user.click(save());

    await waitFor(() => {
      expect(bodies(mock)).toHaveLength(1);
    });
    expect(bodies(mock)[0]).toEqual({ starts_at: "2026-10-21T23:00:00.000Z", duration_min: 60, coach_id: me.id });
    expect(mock.callsTo("GET /users")).toHaveLength(0);
  });
});

