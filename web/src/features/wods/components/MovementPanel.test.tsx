// S8-F1 · US-165 (front): panel lateral para crear y editar un movimiento del catálogo (Movimientos.html).
// - Zod: nombre de 1 a 60, categoría y unidad del contrato. 409 `movement_exists` bajo «Nombre».
// - La carga solo se pide en los WODs si la unidad es kg (S8-D5): el panel lo dice según la unidad elegida.
// - Al editar solo viaja lo cambiado (PATCH).
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { MOVEMENTS, movement } from "../../../test/wods";
import type { MovementView } from "../api";
import { MovementPanel } from "./MovementPanel";

const SQUAT_PATCH = `PATCH /movements/${MOVEMENTS.squat.id}`;

function renderPanel(handlers: Record<string, MockHandler> = {}, target: MovementView | null = null) {
  const mock = mockApi({
    "POST /movements": { status: 201, body: movement("d1d1d1d1-0000-4000-8000-000000000009", { name: "Deadlift", wod_count: 0 }) },
    [SQUAT_PATCH]: { status: 200, body: { ...MOVEMENTS.squat, name: "Back Squat 2" } },
    ...handlers,
  });
  const onClose = vi.fn();
  const onSaved = vi.fn();
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter>
          <MovementPanel open movement={target} onClose={onClose} onSaved={onSaved} />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, onClose, onSaved, user: userEvent.setup(), ...view };
}

const save = () => screen.getByRole("button", { name: /^(Guardar|Crear movimiento)/ });

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("MovementPanel · crear", () => {
  it("pide nombre, categoría y unidad; sin nombre no envía", async () => {
    const { user, mock } = renderPanel();

    expect(screen.getByRole("dialog", { name: "Nuevo movimiento" })).toBeInTheDocument();
    await user.click(save());

    expect(await screen.findByText("Escribe el nombre del movimiento (hasta 60 caracteres).")).toBeInTheDocument();
    expect(mock.callsTo("POST /movements")).toHaveLength(0);
  });

  it("envía el nombre recortado con su categoría y unidad, y avisa al padre", async () => {
    const { user, mock, onSaved } = renderPanel();
    await user.type(screen.getByLabelText(/^Nombre/), "  Deadlift ");
    await user.selectOptions(screen.getByLabelText(/^Categoría/), "gymnastics");
    await user.selectOptions(screen.getByLabelText(/^Unidad/), "reps");

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo("POST /movements")[0]?.body).toEqual({ name: "Deadlift", category: "gymnastics", unit: "reps" });
  });

  it("la nota de carga sigue a la unidad: solo kg admite carga en un WOD", async () => {
    const { user } = renderPanel();

    expect(screen.getByText("Este movimiento admite carga en los WODs.")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText(/^Unidad/), "m");
    expect(screen.getByText("Sin carga: los WODs no piden peso para este movimiento.")).toBeInTheDocument();
  });

  it("409 movement_exists va bajo «Nombre» y no cierra el panel", async () => {
    const { user, onSaved } = renderPanel({ "POST /movements": apiError(409, "movement_exists", { field: "name", existing_id: MOVEMENTS.squat.id }) });
    await user.type(screen.getByLabelText(/^Nombre/), "back squat");

    await user.click(save());

    expect(await screen.findByText("Ya existe un movimiento con ese nombre. Búscalo en la lista o usa otro nombre.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Nombre/)).toHaveAccessibleDescription(expect.stringContaining("Ya existe un movimiento") as string);
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("un doble clic manda un solo POST", async () => {
    let release: () => void = () => undefined;
    const { user, mock } = renderPanel({
      "POST /movements": () =>
        new Promise((resolve) => {
          release = () => {
            resolve({ status: 201, body: movement("d1d1d1d1-0000-4000-8000-000000000009") });
          };
        }),
    });
    await user.type(screen.getByLabelText(/^Nombre/), "Deadlift");

    await user.dblClick(save());

    expect(mock.callsTo("POST /movements")).toHaveLength(1);
    release();
  });

  it.each([
    [403, "forbidden", "No tienes permiso para guardar movimientos. Si lo necesitas, pídeselo a un administrador."],
    [500, "internal_error", "No pudimos guardar el movimiento. Intenta de nuevo en un momento."],
  ])("%i %s como aviso del panel", async (status, code, message) => {
    const { user } = renderPanel({ "POST /movements": apiError(status, code) });
    await user.type(screen.getByLabelText(/^Nombre/), "Deadlift");

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderPanel();

    expect(await axe(container.ownerDocument.body)).toHaveNoViolations();
  });
});

describe("MovementPanel · editar", () => {
  it("precarga el movimiento, ofrece «Activo» y avisa que los WODs guardan su propia copia del nombre", () => {
    renderPanel({}, MOVEMENTS.squat);

    expect(screen.getByRole("dialog", { name: "Editar movimiento · Back Squat" })).toBeInTheDocument();
    expect(screen.getByLabelText(/^Nombre/)).toHaveValue("Back Squat");
    expect(screen.getByLabelText(/^Categoría/)).toHaveValue("weightlifting");
    expect(screen.getByLabelText(/^Unidad/)).toHaveValue("kg");
    expect(screen.getByRole("checkbox", { name: "Activo" })).toBeChecked();
    expect(screen.getByText(/Los WODs ya guardados conservan su propia copia del nombre/)).toBeInTheDocument();
  });

  it("solo manda lo que cambió", async () => {
    const { user, mock, onSaved } = renderPanel({}, MOVEMENTS.squat);
    const name = screen.getByLabelText(/^Nombre/);
    await user.clear(name);
    await user.type(name, "Back Squat 2");

    await user.click(save());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo(SQUAT_PATCH)[0]?.body).toEqual({ name: "Back Squat 2" });
  });

  it("desactivar manda solo is_active", async () => {
    const { user, mock } = renderPanel({ [SQUAT_PATCH]: { status: 200, body: { ...MOVEMENTS.squat, is_active: false } } }, MOVEMENTS.squat);

    await user.click(screen.getByRole("checkbox", { name: "Activo" }));
    await user.click(save());

    await waitFor(() => {
      expect(mock.callsTo(SQUAT_PATCH)).toHaveLength(1);
    });
    expect(mock.callsTo(SQUAT_PATCH)[0]?.body).toEqual({ is_active: false });
  });

  it("sin cambios no envía nada y cierra", async () => {
    const { user, mock, onClose } = renderPanel({}, MOVEMENTS.squat);

    await user.click(save());

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
    expect(mock.calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
  });

  it("404 dice que el movimiento ya no existe", async () => {
    const { user } = renderPanel({ [SQUAT_PATCH]: apiError(404, "movement_not_found") }, MOVEMENTS.squat);
    await user.click(screen.getByRole("checkbox", { name: "Activo" }));

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("Este movimiento ya no existe. Cierra el panel y actualiza la lista.");
  });
});
