// S4A-F4 · US-080 (front; S4A-D22, S4A-D34, S4A-D114): PlanForm en modo edición.
// - Título "Editar plan · <nombre>", campos precargados y botón "Guardar".
// - Aviso fijo "Cambiar el precio no modifica las membresías ya vendidas" (RN-04).
// - PATCH /plans/{id} con solo los campos modificados (`dirtyFields`); al pasar de clases a días
//   viaja `class_count: null` (el único null válido, S4A-D114); sin cambios no sale nada.
// - 422 con `field` y 409 `plan_name_duplicated` bajo su campo; 404, 403, 429 y 5xx como aviso.
// - 200: avisa al padre (onSaved), cierra el panel y deja el formulario en los valores guardados.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { mockApi, renderWithProviders, testQueryClient, type MockHandler, type RecordedCall } from "../../../test/server";
import { apiError, EXISTING_PLAN_ID, PLANS, type PlanFixture } from "../../../test/plans";
import { PLAN_EDIT_NOTICE, PLAN_MESSAGES, type PlanRowView } from "../schemas";
import { PlanForm } from "./PlanForm";

const asRow = (plan: PlanFixture): PlanRowView => ({ ...plan, active_members_count: plan.active_members_count ?? 0 });
const CLASES = asRow(PLANS.clases);
const MENSUAL = asRow(PLANS.mensual);

const dialog = () => screen.getByRole("dialog");
const nameInput = () => screen.getByRole("textbox", { name: /^Nombre/ });
const priceInput = () => screen.getByRole("textbox", { name: /^Precio \(COP\)/ });
const kindSelect = () => screen.getByRole("combobox", { name: /^Tipo de duración/ });
const classesInput = () => screen.getByRole("textbox", { name: /^Número de clases/ });
const saveButton = () => within(dialog()).getByRole("button", { name: /^(Guardar|Guardando…)$/ });

function setup(plan: PlanRowView = CLASES, handler: MockHandler = (call) => ({ status: 200, body: { ...plan, ...(call.body as object) } })) {
  const mock = mockApi({ [`PATCH /plans/${plan.id}`]: handler });
  const onClose = vi.fn();
  const onSaved = vi.fn();
  const user = userEvent.setup();
  const view = renderWithProviders(<PlanForm open plan={plan} onClose={onClose} onSaved={onSaved} />, { role: "admin", queryClient: testQueryClient() });
  return { mock, onClose, onSaved, user, ...view };
}

const patches = (mock: { callsTo: (key: string) => RecordedCall[] }, plan: PlanRowView = CLASES) => mock.callsTo(`PATCH /plans/${plan.id}`);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PlanForm · modo edición (Planes.html, 'Editar plan')", () => {
  it("precarga el plan por clases con su título y el botón Guardar", () => {
    setup();

    expect(screen.getByRole("dialog", { name: "Editar plan · 12 clases" })).toBeInTheDocument();
    expect(nameInput()).toHaveValue("12 clases");
    expect(priceInput()).toHaveValue("$ 110.000");
    expect(kindSelect()).toHaveValue("classes");
    expect(classesInput()).toHaveValue("12");
    expect(screen.getByRole("textbox", { name: /^Días para usarlas/ })).toHaveValue("60");
    expect(saveButton()).toHaveTextContent("Guardar");
  });

  it("precarga el plan por días con 'Duración en días' y sin número de clases", () => {
    setup(MENSUAL);

    expect(screen.getByRole("dialog", { name: "Editar plan · Mensual" })).toBeInTheDocument();
    expect(kindSelect()).toHaveValue("days");
    expect(screen.getByRole("textbox", { name: /^Duración en días/ })).toHaveValue("30");
    expect(screen.queryByRole("textbox", { name: /^Número de clases/ })).not.toBeInTheDocument();
  });

  it("muestra el aviso fijo sobre el precio de lo ya vendido", () => {
    setup();

    expect(within(dialog()).getByText(PLAN_EDIT_NOTICE)).toBeInTheDocument();
    expect(PLAN_EDIT_NOTICE).toBe("Cambiar el precio no modifica las membresías ya vendidas.");
  });

  it("no tiene violaciones de accesibilidad", async () => {
    setup();

    expect(await axe(document.body)).toHaveNoViolations();
  });
});

describe("PlanForm · envía solo lo modificado (dirtyFields)", () => {
  it("cambiar el precio envía solo price_cop como entero", async () => {
    const { mock, user } = setup();

    await user.clear(priceInput());
    await user.type(priceInput(), "135000");
    await user.click(saveButton());

    await waitFor(() => {
      expect(patches(mock).map((c) => c.body)).toEqual([{ price_cop: 135_000 }]);
    });
  });

  it("cambiar el nombre envía solo el nombre recortado", async () => {
    const { mock, user } = setup();

    await user.clear(nameInput());
    await user.type(nameInput(), "  12 clases plus  ");
    await user.click(saveButton());

    await waitFor(() => {
      expect(patches(mock).map((c) => c.body)).toEqual([{ name: "12 clases plus" }]);
    });
  });

  it("pasar de clases a días envía kind y class_count: null, sin la duración que no cambió", async () => {
    const { mock, user } = setup();

    await user.selectOptions(kindSelect(), "days");
    await user.click(saveButton());

    await waitFor(() => {
      expect(patches(mock).map((c) => c.body)).toEqual([{ kind: "days", class_count: null }]);
    });
  });

  it("pasar de días a clases envía kind y el número de clases", async () => {
    const { mock, user } = setup(MENSUAL);

    await user.selectOptions(kindSelect(), "classes");
    await user.type(classesInput(), "8");
    await user.click(saveButton());

    await waitFor(() => {
      expect(patches(mock, MENSUAL).map((c) => c.body)).toEqual([{ kind: "classes", class_count: 8 }]);
    });
  });

  it("cambiar solo el número de clases envía class_count", async () => {
    const { mock, user } = setup();

    await user.clear(classesInput());
    await user.type(classesInput(), "16");
    await user.click(saveButton());

    await waitFor(() => {
      expect(patches(mock).map((c) => c.body)).toEqual([{ class_count: 16 }]);
    });
  });

  it("un campo que vuelve a su valor no viaja; sin cambios no sale el PATCH y el panel se cierra", async () => {
    const { mock, onClose, user } = setup();

    await user.clear(nameInput());
    await user.type(nameInput(), "12 clases");
    await user.click(saveButton());

    await waitFor(() => {
      expect(onClose).toHaveBeenCalledTimes(1);
    });
    expect(patches(mock)).toHaveLength(0);
  });

  it("la validación del cliente frena un precio vacío sin enviar nada", async () => {
    const { mock, user } = setup();

    await user.clear(priceInput());
    await user.click(saveButton());

    expect(await screen.findByText(PLAN_MESSAGES.priceRequired)).toBeInTheDocument();
    expect(patches(mock)).toHaveLength(0);
  });

  it("un solo PATCH aunque se pulse Guardar dos veces mientras envía", async () => {
    let release: (reply: { status: number; body: unknown }) => void = () => undefined;
    const pending = new Promise<{ status: number; body: unknown }>((resolve) => {
      release = resolve;
    });
    const { mock, user } = setup(CLASES, () => pending);

    await user.clear(priceInput());
    await user.type(priceInput(), "135000");
    await user.click(saveButton());
    await user.click(saveButton());

    expect(saveButton()).toHaveTextContent("Guardando…");
    release({ status: 200, body: { ...CLASES, price_cop: 135_000 } });
    await waitFor(() => {
      expect(patches(mock)).toHaveLength(1);
    });
  });
});

describe("PlanForm · errores del api al editar", () => {
  it("el 422 de class_count va bajo 'Número de clases'", async () => {
    const { user } = setup(CLASES, apiError(422, "validation_error", { field: "class_count" }));

    await user.clear(classesInput());
    await user.type(classesInput(), "16");
    await user.click(saveButton());

    expect(await screen.findByText(PLAN_MESSAGES.classCountRange)).toBeInTheDocument();
    expect(classesInput()).toHaveAttribute("aria-invalid", "true");
  });

  it("el 409 de nombre va bajo 'Nombre' con el enlace al plan existente", async () => {
    const { user } = setup(CLASES, apiError(409, "plan_name_duplicated", { field: "name", existing_id: EXISTING_PLAN_ID }));

    await user.clear(nameInput());
    await user.type(nameInput(), "Mensual");
    await user.click(saveButton());

    expect(await screen.findByText(PLAN_MESSAGES.duplicated)).toBeInTheDocument();
    expect(within(dialog()).getByRole("link", { name: "Ver el plan existente" })).toHaveAttribute("href", `/planes?plan=${EXISTING_PLAN_ID}`);
  });

  it.each([
    [404, "plan_not_found", {}, "Este plan ya no existe: lo dieron de baja. Cierra el panel y elige otro de la lista."],
    [403, "forbidden", {}, "Solo un administrador puede editar planes. Si lo necesitas, pídeselo a uno."],
    [500, "internal_error", {}, "No pudimos guardar el plan. Intenta de nuevo en un momento."],
  ])("un %i se explica como aviso general", async (status, code, extra, message) => {
    const { user } = setup(CLASES, apiError(status, code, extra));

    await user.clear(priceInput());
    await user.type(priceInput(), "135000");
    await user.click(saveButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
  });

  it("un 429 dice cuánto esperar", async () => {
    const { user } = setup(CLASES, apiError(429, "rate_limited", {}, { "Retry-After": "12" }));

    await user.clear(priceInput());
    await user.type(priceInput(), "135000");
    await user.click(saveButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("Hiciste muchos cambios seguidos. Espera 12 segundos e intenta de nuevo.");
  });
});

describe("PlanForm · tras guardar", () => {
  it("avisa al padre con el plan guardado y cierra", async () => {
    const { onClose, onSaved, user } = setup();

    await user.clear(priceInput());
    await user.type(priceInput(), "135000");
    await user.click(saveButton());

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: CLASES.id, price_cop: 135_000 }));
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("reset(): al reabrir quedan los valores guardados y sin cambios no sale otro PATCH", async () => {
    const { mock, onClose, rerender, user } = setup();

    await user.clear(priceInput());
    await user.type(priceInput(), "135000");
    await user.click(saveButton());
    await waitFor(() => {
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    const saved = { ...CLASES, price_cop: 135_000 };
    rerender(<PlanForm open={false} plan={saved} onClose={onClose} />);
    rerender(<PlanForm open plan={saved} onClose={onClose} />);

    expect(priceInput()).toHaveValue("$ 135.000");
    await user.click(saveButton());
    await waitFor(() => {
      expect(onClose).toHaveBeenCalledTimes(2);
    });
    expect(patches(mock)).toHaveLength(1);
  });
});
