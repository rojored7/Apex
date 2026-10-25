// S3-F4 · US-056 (front): pestaña "Medios de pago" de Configuración (Config.html, "3 · Medios de
// pago"). Tres filas fijas (Efectivo, Nequi, Bre-B; D24), sin agregar ni quitar, con la etiqueta y la
// ayuda que ve el equipo al registrar un pago. Etiquetas de 1 a 30 caracteres y sin repetirse sin
// distinguir mayúsculas (S3-D55); 422 en `value.<code>.label`; 409 `version_conflict`.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { mockApi, renderWithProviders, type MockReply } from "../../../test/server";
import { CONFLICT_REPLY, fieldErrorReply, paymentMethodsSection } from "../../../test/settings";
import { PaymentMethodsForm } from "./PaymentMethodsForm";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderLoaded(handlers: Record<string, MockReply> = {}) {
  const mock = mockApi({ "GET /settings/payment_methods": { status: 200, body: paymentMethodsSection() }, ...handlers });
  const user = userEvent.setup();
  const view = renderWithProviders(<PaymentMethodsForm />, { role: "admin" });
  await screen.findByRole("group", { name: "Efectivo" });
  return { mock, user, ...view };
}

const row = (name: string) => screen.getByRole("group", { name });
const labelBox = (name: string) => within(row(name)).getByRole("textbox", { name: /^Nombre que se muestra/ });
const hintBox = (name: string) => within(row(name)).getByRole("textbox", { name: /^Ayuda al registrar/ });
const save = () => screen.getByRole("button", { name: "Guardar" });

describe("PaymentMethodsForm", () => {
  it("muestra las tres filas fijas con su etiqueta y la nota de que no se agregan medios", async () => {
    const { container } = await renderLoaded();

    expect(screen.getByRole("heading", { level: 2, name: "Medios de pago" })).toBeInTheDocument();
    expect(Array.from(container.querySelectorAll("legend"), (legend) => legend.textContent)).toEqual(["Efectivo", "Nequi", "Bre-B"]);
    expect(labelBox("Efectivo")).toHaveValue("Efectivo");
    expect(labelBox("Nequi")).toHaveValue("Nequi");
    expect(hintBox("Bre-B")).toHaveValue("");
    expect(screen.getByText("Para agregar un medio nuevo se requiere una actualización del sistema.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Agregar|Quitar|Eliminar/ })).not.toBeInTheDocument();
  });

  it("guarda las tres etiquetas recortadas con la versión leída y muestra «Cambios guardados»", async () => {
    const saved = paymentMethodsSection({ nequi: { label: "Nequi del box", hint: "Número de transacción" } }, 1);
    const { mock, user } = await renderLoaded({ "PATCH /settings/payment_methods": { status: 200, body: saved } });

    await user.clear(labelBox("Nequi"));
    await user.type(labelBox("Nequi"), "  Nequi del box ");
    await user.type(hintBox("Nequi"), "Número de transacción");
    await user.click(save());

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/payment_methods")[0]?.body).toEqual({
      value: {
        cash: { label: "Efectivo", hint: "" },
        nequi: { label: "Nequi del box", hint: "Número de transacción" },
        breb: { label: "Bre-B", hint: "" },
      },
      version: 0,
    });
    expect(labelBox("Nequi")).toHaveValue("Nequi del box");
  });

  it("guardar relee los medios con etiqueta de la venta y el panel de pagos (['payment-methods'])", async () => {
    const { user, queryClient } = await renderLoaded({ "PATCH /settings/payment_methods": { status: 200, body: paymentMethodsSection({}, 1) } });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    await user.type(hintBox("Efectivo"), "Recibo en caja");
    await user.click(save());

    await screen.findByText("Cambios guardados");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["payment-methods"] });
  });

  it("una etiqueta vacía muestra el error bajo Efectivo y no llama al api", async () => {
    const { mock, user } = await renderLoaded();

    await user.clear(labelBox("Efectivo"));
    await user.click(save());

    await waitFor(() => {
      expect(labelBox("Efectivo")).toHaveAttribute("aria-invalid", "true");
    });
    expect(labelBox("Efectivo")).toHaveAccessibleDescription(expect.stringContaining("Escribe el nombre del medio de pago."));
    expect(mock.callsTo("PATCH /settings/payment_methods")).toHaveLength(0);
  });

  it("una etiqueta de más de 30 caracteres se explica", async () => {
    const { user } = await renderLoaded();

    await user.clear(labelBox("Bre-B"));
    await user.type(labelBox("Bre-B"), "B".repeat(31));
    await user.click(save());

    expect(await screen.findByText("El nombre admite hasta 30 caracteres.")).toBeInTheDocument();
  });

  it("dos etiquetas iguales (sin distinguir mayúsculas) marcan la segunda y no llaman al api", async () => {
    const { mock, user } = await renderLoaded();

    await user.clear(labelBox("Bre-B"));
    await user.type(labelBox("Bre-B"), "nequi");
    await user.click(save());

    await waitFor(() => {
      expect(labelBox("Bre-B")).toHaveAttribute("aria-invalid", "true");
    });
    expect(labelBox("Bre-B")).toHaveAccessibleDescription(expect.stringContaining("Ya hay otro medio con este nombre. Usa uno distinto."));
    expect(labelBox("Nequi")).toHaveAttribute("aria-invalid", "false");
    expect(mock.callsTo("PATCH /settings/payment_methods")).toHaveLength(0);
  });

  it("un 422 del api en value.nequi.label va bajo la etiqueta de Nequi", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/payment_methods": fieldErrorReply("value.nequi.label") });

    await user.clear(labelBox("Nequi"));
    await user.type(labelBox("Nequi"), "NEQUÍ");
    await user.click(save());

    await waitFor(() => {
      expect(labelBox("Nequi")).toHaveAttribute("aria-invalid", "true");
    });
    expect(labelBox("Nequi")).toHaveAccessibleDescription(expect.stringContaining("El servidor no aceptó este nombre: puede estar repetido o tener caracteres no válidos."));
  });

  it("un 409 muestra el aviso de conflicto con Recargar", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/payment_methods": CONFLICT_REPLY });

    await user.type(hintBox("Efectivo"), "Recibo en caja");
    await user.click(save());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Otra persona cambió esta sección. Recarga para ver los cambios.");
    expect(within(alert).getByRole("button", { name: "Recargar" })).toBeInTheDocument();
    expect(save()).toBeDisabled();
  });

  it("es accesible", async () => {
    const { container } = await renderLoaded();

    expect(await axe(container)).toHaveNoViolations();
  });
});
