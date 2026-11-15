// S7-F1 · US-154: pestaña Clases. Cupo por defecto (1 a 100) y ventana de check-in (0 a 240), enteros estrictos.
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { mockApi, renderWithProviders, type MockReply } from "../../../test/server";
import { CONFLICT_REPLY, classesSection, fieldErrorReply } from "../../../test/settings";
import { ClassesSettingsForm } from "./ClassesSettingsForm";

async function renderLoaded(handlers: Record<string, MockReply> = {}) {
  const mock = mockApi({ "GET /settings/classes": { status: 200, body: classesSection() }, ...handlers });
  const user = userEvent.setup();
  const view = renderWithProviders(<ClassesSettingsForm />, { role: "admin" });
  await screen.findByRole("spinbutton", { name: /Cupo por defecto/ });
  return { mock, user, ...view };
}

const capacity = () => screen.getByRole("spinbutton", { name: /Cupo por defecto/ });
const windowMin = () => screen.getByRole("spinbutton", { name: /Ventana de check-in/ });

describe("ClassesSettingsForm", () => {
  it("muestra los dos parámetros con su explicación, sus rangos y el valor por defecto, y las dos reglas fijas", async () => {
    await renderLoaded();

    expect(screen.getByRole("heading", { level: 2, name: "Clases" })).toBeInTheDocument();
    expect(capacity()).toHaveValue(15);
    expect(capacity()).toHaveAccessibleDescription(expect.stringContaining("Entre 1 y 100. Por defecto: 15."));
    expect(windowMin()).toHaveValue(30);
    expect(windowMin()).toHaveAccessibleDescription(expect.stringContaining("Entre 0 y 240. Por defecto: 30."));
    expect(screen.getByText(/14 días hacia adelante/)).toBeInTheDocument();
    expect(screen.getByText(/membresía vencida/i)).toBeInTheDocument();
  });

  it("guarda los dos enteros con la versión leída", async () => {
    const { mock, user } = await renderLoaded({ "PATCH /settings/classes": { status: 200, body: classesSection({ default_capacity: 18 }, 1) } });

    await user.clear(capacity());
    await user.type(capacity(), "18");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/classes")[0]?.body).toEqual({ value: { default_capacity: 18, checkin_window_min: 30 }, version: 0 });
    expect(capacity()).toHaveValue(18);
  });

  it.each([
    ["capacity", "0", "Escribe un número entre 1 y 100."],
    ["capacity", "101", "Escribe un número entre 1 y 100."],
    ["capacity", "", "Escribe un número."],
    ["window", "241", "Escribe un número entre 0 y 240."],
    ["window", "2.5", "Escribe un número entero, sin decimales ni signos."],
  ])("%s con %j muestra «%s» y no llama al api", async (which, value, message) => {
    const { mock, user } = await renderLoaded();
    const input = which === "capacity" ? capacity() : windowMin();

    await user.clear(input);
    if (value) await user.type(input, value);
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(mock.callsTo("PATCH /settings/classes")).toHaveLength(0);
  });

  it("la ventana 0 es válida (check-in sin margen)", async () => {
    const { mock, user } = await renderLoaded({ "PATCH /settings/classes": { status: 200, body: classesSection({ checkin_window_min: 0 }, 1) } });

    await user.clear(windowMin());
    await user.type(windowMin(), "0");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await screen.findByText("Cambios guardados");
    expect(mock.callsTo("PATCH /settings/classes")[0]?.body).toMatchObject({ value: { checkin_window_min: 0 } });
  });

  it("un 422 de value.default_capacity marca ese campo", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/classes": fieldErrorReply("value.default_capacity") });

    await user.clear(capacity());
    await user.type(capacity(), "20");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(capacity()).toHaveAttribute("aria-invalid", "true");
    });
  });

  it("un 409 muestra el aviso de conflicto con Recargar", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/classes": CONFLICT_REPLY });

    await user.clear(capacity());
    await user.type(capacity(), "20");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Otra persona cambió esta sección.");
    expect(screen.getByRole("button", { name: "Recargar" })).toBeInTheDocument();
  });

  it("es accesible", async () => {
    const { container } = await renderLoaded();

    expect(await axe(container)).toHaveNoViolations();
  });
});
