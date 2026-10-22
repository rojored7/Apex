// S2-F5 · US-058: pestaña Membresías. Cuatro enteros con su explicación y su valor por
// defecto, enteros estrictos en el envío, rangos del api y conflicto 409.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { mockApi, renderWithProviders, type MockReply } from "../../../test/server";
import { CONFLICT_REPLY, fieldErrorReply, membershipsSection } from "../../../test/settings";
import { MembershipsSettingsForm } from "./MembershipsSettingsForm";

const FIELDS = [
  ["Días antes del vencimiento para marcar «Por vencer»", "Entre 1 y 30. Por defecto: 7."],
  ["Máximo de días congelados por membresía", "Entre 0 y 180. Por defecto: 30."],
  ["Máximo de congelaciones por membresía", "Entre 0 y 12. Por defecto: 2."],
  ["Días hacia atrás para la fecha de inicio", "Entre 0 y 30. Por defecto: 7."],
] as const;

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderLoaded(handlers: Record<string, MockReply> = {}) {
  const mock = mockApi({ "GET /settings/memberships": { status: 200, body: membershipsSection() }, ...handlers });
  const user = userEvent.setup();
  const view = renderWithProviders(<MembershipsSettingsForm />, { role: "admin" });
  await screen.findByRole("spinbutton", { name: /Por vencer/ });
  return { mock, user, ...view };
}

const expiring = () => screen.getByRole("spinbutton", { name: /Por vencer/ });

describe("MembershipsSettingsForm", () => {
  it("muestra los cuatro parámetros con su explicación y su valor por defecto", async () => {
    await renderLoaded();

    expect(screen.getByRole("heading", { level: 2, name: "Membresías" })).toBeInTheDocument();
    for (const [label, hint] of FIELDS) {
      const input = screen.getByRole("spinbutton", { name: label });
      expect(input).toHaveAccessibleDescription(expect.stringContaining(hint));
      expect(input).toHaveClass("control", "md");
    }
    expect(expiring()).toHaveValue(7);
    expect(screen.getByRole("spinbutton", { name: /días congelados/ })).toHaveValue(30);
  });

  it("guarda los cuatro valores como enteros con la versión leída", async () => {
    const { mock, user } = await renderLoaded({ "PATCH /settings/memberships": { status: 200, body: membershipsSection({ expiring_days: 10 }, 1) } });

    await user.clear(expiring());
    await user.type(expiring(), "10");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/memberships")[0]?.body).toEqual({
      value: { expiring_days: 10, max_freeze_days_per_membership: 30, max_freezes_per_membership: 2, max_retroactive_days: 7 },
      version: 0,
    });
    expect(expiring()).toHaveValue(10);
  });

  it.each([
    ["31", "Escribe un número entre 1 y 30."],
    ["0", "Escribe un número entre 1 y 30."],
    ["7.5", "Escribe un número entero, sin decimales ni signos."],
    ["", "Escribe un número."],
  ])("con %j muestra «%s» y no llama al api", async (value, message) => {
    const { mock, user } = await renderLoaded();

    await user.clear(expiring());
    if (value) await user.type(expiring(), value);
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(expiring()).toHaveAttribute("aria-invalid", "true");
    expect(mock.callsTo("PATCH /settings/memberships")).toHaveLength(0);
  });

  it("un 422 de value.expiring_days marca ese campo", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/memberships": fieldErrorReply("value.expiring_days") });

    await user.clear(expiring());
    await user.type(expiring(), "9");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(expiring()).toHaveAttribute("aria-invalid", "true");
    });
    expect(expiring()).toHaveAccessibleDescription(expect.stringContaining("El servidor no aceptó este valor. Revísalo y vuelve a guardar."));
  });

  it("un 409 muestra el aviso de conflicto con Recargar", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/memberships": CONFLICT_REPLY });

    await user.clear(expiring());
    await user.type(expiring(), "8");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Otra persona cambió esta sección. Recarga para ver los cambios.");
    expect(within(alert).getByRole("button", { name: "Recargar" })).toBeInTheDocument();
  });

  it("es accesible", async () => {
    const { container } = await renderLoaded();

    expect(await axe(container)).toHaveNoViolations();
  });
});
