// S2-F7 · US-078 (front): alta de un plan en el SidePanel de Planes.html (solo admin).
// - Nombre, Precio (COP) con formato "$ 120.000" al escribir, Tipo de duración y, según el tipo,
//   "Duración en días" o "Número de clases" + "Días para usarlas" (el campo de clases solo existe
//   con "Por número de clases").
// - Validación en el cliente igual al api (PlanCreate y validate_plan de B9): nombre de 1 a 80,
//   precio entero de 1 a 1.000.000.000, duración de 1 a 3.650 y clases de 1 a 1.000 solo con
//   `classes`. Si algo no cumple, no sale el POST.
// - Botón deshabilitado mientras envía (un solo POST). 422 con `field` bajo su campo; 409
//   `plan_name_duplicated` bajo "Nombre" con enlace al plan existente; 403, 5xx y red como aviso.
// - 201: avisa al padre (onCreated), cierra el panel e invalida ["plans"].
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { mockApi, renderWithProviders, testQueryClient, type MockHandler, type RecordedCall } from "../../../test/server";
import { apiError, EXISTING_PLAN_ID, NEW_PLAN } from "../../../test/plans";
import { PlanForm } from "./PlanForm";

const dialog = () => screen.getByRole("dialog", { name: "Nuevo plan" });
const nameInput = () => screen.getByRole("textbox", { name: /^Nombre/ });
const priceInput = () => screen.getByRole("textbox", { name: /^Precio \(COP\)/ });
const kindSelect = () => screen.getByRole("combobox", { name: /^Tipo de duración/ });
const durationInput = () => screen.getByRole("textbox", { name: /^(Duración en días|Días para usarlas)/ });
const classesInput = () => screen.getByRole("textbox", { name: /^Número de clases/ });
const saveButton = () => within(dialog()).getByRole("button", { name: /^(Crear plan|Guardando…)$/ });

function setup(handler: MockHandler = { status: 201, body: NEW_PLAN }) {
  const mock = mockApi({ "POST /plans": handler });
  const onClose = vi.fn();
  const onCreated = vi.fn();
  const user = userEvent.setup();
  const view = renderWithProviders(<PlanForm open onClose={onClose} onCreated={onCreated} />, { role: "admin", queryClient: testQueryClient() });
  return { mock, onClose, onCreated, user, ...view };
}

const posts = (mock: { callsTo: (key: string) => RecordedCall[] }) => mock.callsTo("POST /plans");

async function fillDays(user: ReturnType<typeof userEvent.setup>, { name = "Mensual", price = "120000", days = "30" } = {}) {
  if (name) await user.type(nameInput(), name);
  if (price) await user.type(priceInput(), price);
  if (days) await user.type(durationInput(), days);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PlanForm · estructura (Planes.html)", () => {
  it("es un panel 'Nuevo plan' con nombre, precio, tipo y duración en días; sin número de clases", () => {
    setup();

    expect(dialog()).toBeInTheDocument();
    expect(nameInput()).toHaveValue("");
    expect(priceInput()).toHaveAttribute("inputmode", "numeric");
    expect(within(kindSelect()).getAllByRole("option").map((o) => o.textContent)).toEqual(["Por días", "Por número de clases"]);
    expect(kindSelect()).toHaveValue("days");
    expect(screen.getByRole("textbox", { name: /^Duración en días/ })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /^Número de clases/ })).not.toBeInTheDocument();
    expect(within(dialog()).getByRole("button", { name: "Cancelar" })).toBeInTheDocument();
    expect(saveButton()).toHaveTextContent("Crear plan");
  });

  it("no pinta nada si está cerrado", () => {
    mockApi({});
    renderWithProviders(<PlanForm open={false} onClose={vi.fn()} onCreated={vi.fn()} />, { role: "admin" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    setup();

    expect(await axe(document.body)).toHaveNoViolations();
  });
});

describe("PlanForm · campo condicional de clases", () => {
  it("con 'Por número de clases' aparecen 'Número de clases' y 'Días para usarlas'; con 'Por días' se van", async () => {
    const { user } = setup();

    await user.selectOptions(kindSelect(), "Por número de clases");

    expect(classesInput()).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^Días para usarlas/ })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /^Duración en días/ })).not.toBeInTheDocument();

    await user.selectOptions(kindSelect(), "Por días");

    expect(screen.queryByRole("textbox", { name: /^Número de clases/ })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^Duración en días/ })).toBeInTheDocument();
  });

  it("por días no envía class_count aunque antes se haya escrito un número de clases", async () => {
    const { mock, user } = setup();
    await user.selectOptions(kindSelect(), "Por número de clases");
    await user.type(classesInput(), "12");
    await user.selectOptions(kindSelect(), "Por días");
    await fillDays(user);

    await user.click(saveButton());

    await waitFor(() => {
      expect(posts(mock)).toHaveLength(1);
    });
    expect(posts(mock)[0]?.body).toEqual({ name: "Mensual", price_cop: 120_000, kind: "days", duration_days: 30 });
  });

  it("por clases envía class_count y los días para usarlas como duration_days", async () => {
    const { mock, user } = setup();
    await user.type(nameInput(), "  12 clases  ");
    await user.type(priceInput(), "110000");
    await user.selectOptions(kindSelect(), "Por número de clases");
    await user.type(classesInput(), "12");
    await user.type(durationInput(), "60");

    await user.click(saveButton());

    await waitFor(() => {
      expect(posts(mock)).toHaveLength(1);
    });
    expect(posts(mock)[0]?.body).toEqual({ name: "12 clases", price_cop: 110_000, kind: "classes", duration_days: 60, class_count: 12 });
  });
});

describe("PlanForm · precio en COP", () => {
  it("se muestra con el formato de pesos mientras se escribe", async () => {
    const { user } = setup();

    await user.type(priceInput(), "120000");
    expect(priceInput()).toHaveValue("$ 120.000");

    await user.clear(priceInput());
    await user.type(priceInput(), "1500");
    expect(priceInput()).toHaveValue("$ 1.500");

    await user.clear(priceInput());
    expect(priceInput()).toHaveValue("");
  });

  it("acepta pegar un precio ya formateado y lo envía como entero", async () => {
    const { mock, user } = setup();
    await user.type(nameInput(), "Mensual");
    await user.click(priceInput());
    await user.paste("$ 1.000.000.000");
    await user.type(durationInput(), "30");

    expect(priceInput()).toHaveValue("$ 1.000.000.000");
    await user.click(saveButton());

    await waitFor(() => {
      expect(posts(mock)).toHaveLength(1);
    });
    expect((posts(mock)[0]?.body as { price_cop: number }).price_cop).toBe(1_000_000_000);
  });

  it("un precio con centavos no se reformatea y se rechaza sin enviar", async () => {
    const { mock, user } = setup();
    await fillDays(user, { price: "" });
    await user.type(priceInput(), "120000,50");

    // Los dígitos se formatean mientras se escriben; desde la coma el texto queda tal cual.
    expect(priceInput()).toHaveValue("$ 120.000,50");
    await user.click(saveButton());

    expect(await screen.findByText("Escribe el precio en pesos enteros, sin centavos (por ejemplo $ 120.000).")).toBeInTheDocument();
    expect(posts(mock)).toHaveLength(0);
  });

  it.each([
    ["0", "$ 0"],
    ["1000000001", "$ 1.000.000.001"],
  ])("un precio fuera de 1 a 1.000.000.000 (%s) se rechaza", async (typed, shown) => {
    const { mock, user } = setup();
    await fillDays(user, { price: typed });

    expect(priceInput()).toHaveValue(shown);
    await user.click(saveButton());

    expect(await screen.findByText("El precio debe estar entre $ 1 y $ 1.000.000.000.")).toBeInTheDocument();
    expect(priceInput()).toHaveAttribute("aria-invalid", "true");
    expect(posts(mock)).toHaveLength(0);
  });
});

describe("PlanForm · validación en el cliente", () => {
  it("vacío marca nombre, precio y duración y no envía", async () => {
    const { mock, user } = setup();

    await user.click(saveButton());

    expect(await screen.findByText("Escribe el nombre del plan.")).toBeInTheDocument();
    expect(screen.getByText("Escribe el precio del plan.")).toBeInTheDocument();
    expect(screen.getByText("Escribe cuántos días dura el plan.")).toBeInTheDocument();
    expect(nameInput()).toHaveFocus();
    expect(posts(mock)).toHaveLength(0);
  });

  it("un nombre de solo espacios cuenta como vacío", async () => {
    const { mock, user } = setup();
    await fillDays(user, { name: "    " });

    await user.click(saveButton());

    expect(await screen.findByText("Escribe el nombre del plan.")).toBeInTheDocument();
    expect(posts(mock)).toHaveLength(0);
  });

  it("un nombre de 81 caracteres se rechaza y uno de 80 pasa", async () => {
    const { mock, user } = setup();
    await fillDays(user, { name: "x".repeat(81) });

    await user.click(saveButton());
    expect(await screen.findByText("El nombre admite hasta 80 caracteres.")).toBeInTheDocument();
    expect(posts(mock)).toHaveLength(0);

    await user.type(nameInput(), "{Backspace}");
    await user.click(saveButton());

    await waitFor(() => {
      expect(posts(mock)).toHaveLength(1);
    });
    expect((posts(mock)[0]?.body as { name: string }).name).toHaveLength(80);
  });

  it.each(["0", "3651", "1.5", "treinta"])("una duración inválida (%s) se rechaza", async (days) => {
    const { mock, user } = setup();
    await fillDays(user, { days });

    await user.click(saveButton());

    expect(await screen.findByText("La duración debe ser un número entero entre 1 y 3.650 días.")).toBeInTheDocument();
    expect(posts(mock)).toHaveLength(0);
  });

  it("3.650 días es el tope y se acepta", async () => {
    const { mock, user } = setup();
    await fillDays(user, { days: "3650" });

    await user.click(saveButton());

    await waitFor(() => {
      expect(posts(mock)).toHaveLength(1);
    });
    expect((posts(mock)[0]?.body as { duration_days: number }).duration_days).toBe(3650);
  });

  it("por clases sin número de clases lo pide y no envía", async () => {
    const { mock, user } = setup();
    await fillDays(user);
    await user.selectOptions(kindSelect(), "Por número de clases");

    await user.click(saveButton());

    expect(await screen.findByText("Escribe cuántas clases incluye el plan.")).toBeInTheDocument();
    expect(posts(mock)).toHaveLength(0);
  });

  it.each(["0", "1001", "2.5"])("un número de clases inválido (%s) se rechaza", async (classes) => {
    const { mock, user } = setup();
    await fillDays(user);
    await user.selectOptions(kindSelect(), "Por número de clases");
    await user.type(classesInput(), classes);

    await user.click(saveButton());

    expect(await screen.findByText("El número de clases debe ser un entero entre 1 y 1.000.")).toBeInTheDocument();
    expect(classesInput()).toHaveAttribute("aria-invalid", "true");
    expect(posts(mock)).toHaveLength(0);
  });

  it("1.000 clases es el tope y se acepta", async () => {
    const { mock, user } = setup();
    await fillDays(user);
    await user.selectOptions(kindSelect(), "Por número de clases");
    await user.type(classesInput(), "1000");

    await user.click(saveButton());

    await waitFor(() => {
      expect(posts(mock)).toHaveLength(1);
    });
    expect((posts(mock)[0]?.body as { class_count: number }).class_count).toBe(1000);
  });
});

describe("PlanForm · envío", () => {
  it("mientras envía el botón queda deshabilitado, dice 'Guardando…' y no sale otro POST", async () => {
    let release: (value: { status: number; body: unknown }) => void = () => undefined;
    const { mock, user, onCreated, onClose } = setup(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    await fillDays(user);

    await user.click(saveButton());

    await waitFor(() => {
      expect(saveButton()).toBeDisabled();
    });
    expect(saveButton()).toHaveTextContent("Guardando…");
    await user.click(saveButton());
    await user.type(nameInput(), "{Enter}");
    expect(posts(mock)).toHaveLength(1);
    // revisión L7: ni Escape, ni Cancelar, ni el ✕ cierran el panel a medio envío.
    await user.keyboard("{Escape}");
    await user.click(within(dialog()).getByRole("button", { name: "Cancelar" }));
    await user.click(within(dialog()).getByRole("button", { name: "Cerrar" }));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog", { name: "¿Descartar los cambios?" })).not.toBeInTheDocument();

    release({ status: 201, body: NEW_PLAN });
    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledTimes(1);
    });
  });

  it("201: avisa al padre con el plan creado, cierra el panel e invalida ['plans']", async () => {
    const { user, onCreated, onClose, queryClient } = setup();
    const listKey = ["plans", { limit: 25, offset: 0 }];
    queryClient.setQueryData(listKey, { items: [], total: 0, limit: 25, offset: 0 });
    await fillDays(user, { name: "Trimestral", price: "320000", days: "90" });

    await user.click(saveButton());

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: NEW_PLAN.id, name: "Trimestral", price_cop: 320_000 }));
    });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(queryClient.getQueryState(listKey)?.isInvalidated).toBe(true);
  });

  it("una respuesta 201 con forma inesperada es un aviso, no un plan creado", async () => {
    const { user, onCreated } = setup({ status: 201, body: { id: 7 } });
    await fillDays(user);

    await user.click(saveButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.");
    expect(onCreated).not.toHaveBeenCalled();
  });
});

describe("PlanForm · errores del api", () => {
  it("409 plan_name_duplicated va bajo 'Nombre', con foco y con enlace al plan existente", async () => {
    const { user, onCreated } = setup(apiError(409, "plan_name_duplicated", { field: "name", existing_id: EXISTING_PLAN_ID }));
    await fillDays(user, { name: "mensual" });

    await user.click(saveButton());

    expect(await screen.findByText(/Ya existe un plan con este nombre\./)).toBeInTheDocument();
    expect(nameInput()).toHaveAttribute("aria-invalid", "true");
    expect(nameInput()).toHaveFocus();
    expect(screen.getByRole("link", { name: "Ver el plan existente" })).toHaveAttribute("href", `/planes?plan=${EXISTING_PLAN_ID}`);
    expect(onCreated).not.toHaveBeenCalled();
    expect(dialog()).toBeInTheDocument();
  });

  it("revisión M2: tras el 409, un error del cliente en 'Nombre' ya no enlaza al plan existente", async () => {
    const { user } = setup(apiError(409, "plan_name_duplicated", { field: "name", existing_id: EXISTING_PLAN_ID }));
    await fillDays(user);
    await user.click(saveButton());
    expect(await screen.findByRole("link", { name: "Ver el plan existente" })).toBeInTheDocument();

    await user.clear(nameInput());
    await user.click(saveButton());

    expect(await screen.findByText("Escribe el nombre del plan.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ver el plan existente" })).not.toBeInTheDocument();
  });

  it("409 sin existing_id va bajo 'Nombre' sin enlace", async () => {
    const { user } = setup(apiError(409, "plan_name_duplicated", { field: "name" }));
    await fillDays(user);

    await user.click(saveButton());

    expect(await screen.findByText("Ya existe un plan con este nombre. Usa otro nombre.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ver el plan existente" })).not.toBeInTheDocument();
  });

  it("'Ver el plan existente' cierra el panel sin recargar", async () => {
    const { user, onClose } = setup(apiError(409, "plan_name_duplicated", { field: "name", existing_id: EXISTING_PLAN_ID }));
    await fillDays(user);
    await user.click(saveButton());

    await user.click(await screen.findByRole("link", { name: "Ver el plan existente" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["name", /^Nombre/, "El servidor no aceptó este nombre. Revísalo e intenta de nuevo."],
    ["price_cop", /^Precio \(COP\)/, "El precio debe estar entre $ 1 y $ 1.000.000.000."],
    ["duration_days", /^Duración en días/, "La duración debe ser un número entero entre 1 y 3.650 días."],
  ])("422 con field=%s va bajo su campo", async (field, label, message) => {
    const { user } = setup(apiError(422, "validation_error", { field }));
    await fillDays(user);

    await user.click(saveButton());

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: label })).toHaveAttribute("aria-invalid", "true");
  });

  it("422 con field=class_count va bajo 'Número de clases'", async () => {
    const { user } = setup(apiError(422, "validation_error", { field: "class_count" }));
    await fillDays(user);
    await user.selectOptions(kindSelect(), "Por número de clases");
    await user.type(classesInput(), "12");

    await user.click(saveButton());

    expect(await screen.findByText("El número de clases debe ser un entero entre 1 y 1.000.")).toBeInTheDocument();
    expect(classesInput()).toHaveAttribute("aria-invalid", "true");
  });

  it("422 sin field (o con uno desconocido) es un aviso general", async () => {
    const { user } = setup(apiError(422, "validation_error", { field: "extra" }));
    await fillDays(user);

    await user.click(saveButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("No pudimos crear el plan. Revisa los datos e intenta de nuevo.");
  });

  it.each([
    [apiError(403, "forbidden"), "Solo un administrador puede crear planes. Si lo necesitas, pídeselo a uno."],
    [apiError(500, "internal"), "No pudimos crear el plan. Intenta de nuevo en un momento."],
    [apiError(429, "rate_limited", {}, { "Retry-After": "8" }), "Hiciste muchos intentos seguidos. Espera 8 segundos e intenta de nuevo."],
  ])("otros errores son un aviso general (%#)", async (reply, message) => {
    const { user, onCreated } = setup(reply);
    await fillDays(user);

    await user.click(saveButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("sin conexión lo dice con el mensaje de red y deja reintentar", async () => {
    let fail = true;
    const { mock, user, onCreated } = setup(() => (fail ? Promise.reject(new TypeError("Failed to fetch")) : { status: 201, body: NEW_PLAN }));
    await fillDays(user);

    await user.click(saveButton());
    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("No pudimos conectar con el servidor. Intenta de nuevo.");

    fail = false;
    await user.click(saveButton());

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledTimes(1);
    });
    expect(posts(mock)).toHaveLength(2);
  });
});
