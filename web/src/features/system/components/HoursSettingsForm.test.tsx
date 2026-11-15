// S7-F1 · US-154: pestaña Horario. Siete días con «Cerrado» o hasta dos rangos HH:MM; lista vacía = cerrado.
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { mockApi, renderWithProviders, type MockReply } from "../../../test/server";
import { CONFLICT_REPLY, fieldErrorReply, hoursSection } from "../../../test/settings";
import { HoursSettingsForm } from "./HoursSettingsForm";

async function renderLoaded(value = {}, handlers: Record<string, MockReply> = {}) {
  const mock = mockApi({ "GET /settings/hours": { status: 200, body: hoursSection(value) }, ...handlers });
  const user = userEvent.setup();
  const view = renderWithProviders(<HoursSettingsForm />, { role: "admin" });
  await screen.findByRole("heading", { level: 2, name: "Horario de atención" });
  return { mock, user, ...view };
}

const time = (label: string) => screen.getByLabelText(label);
const setTime = (label: string, value: string): void => {
  fireEvent.change(time(label), { target: { value } });
};
const closed = (day: string) => screen.getByRole("checkbox", { name: `${day}: cerrado` });

describe("HoursSettingsForm", () => {
  it("sin configurar muestra los siete días como «Cerrado»", async () => {
    await renderLoaded();

    for (const day of ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]) {
      expect(closed(day)).toBeChecked();
      expect(screen.queryByLabelText(`${day}: abre`)).not.toBeInTheDocument();
    }
  });

  it("muestra los rangos que trae el servidor, con el segundo rango", async () => {
    await renderLoaded({
      monday: [
        { open: "05:30", close: "12:00" },
        { open: "16:00", close: "21:00" },
      ],
    });

    expect(closed("Lunes")).not.toBeChecked();
    expect(time("Lunes: abre")).toHaveValue("05:30");
    expect(time("Lunes: cierra")).toHaveValue("12:00");
    expect(time("Lunes: abre (segundo rango)")).toHaveValue("16:00");
    expect(time("Lunes: cierra (segundo rango)")).toHaveValue("21:00");
  });

  it("guarda un día con un rango y los demás cerrados (lista vacía) con la versión leída", async () => {
    const { mock, user } = await renderLoaded({}, { "PATCH /settings/hours": { status: 200, body: hoursSection({ monday: [{ open: "05:30", close: "21:00" }] }, 1) } });

    await user.click(closed("Lunes"));
    setTime("Lunes: abre", "05:30");
    setTime("Lunes: cierra", "21:00");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/hours")[0]?.body).toEqual({
      value: {
        monday: [{ open: "05:30", close: "21:00" }],
        tuesday: [],
        wednesday: [],
        thursday: [],
        friday: [],
        saturday: [],
        sunday: [],
      },
      version: 0,
    });
  });

  it("guarda dos rangos en un día con el botón de segundo rango", async () => {
    const { mock, user } = await renderLoaded({ saturday: [{ open: "07:00", close: "09:00" }] }, { "PATCH /settings/hours": { status: 200, body: hoursSection({}, 1) } });

    await user.click(screen.getByRole("button", { name: "Agregar segundo rango del sábado" }));
    setTime("Sábado: abre (segundo rango)", "10:00");
    setTime("Sábado: cierra (segundo rango)", "12:00");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await screen.findByText("Cambios guardados");
    expect((mock.callsTo("PATCH /settings/hours")[0]?.body as { value: { saturday: unknown } }).value.saturday).toEqual([
      { open: "07:00", close: "09:00" },
      { open: "10:00", close: "12:00" },
    ]);
  });

  it("marcar «Cerrado» en un día con rangos lo envía como lista vacía", async () => {
    const { mock, user } = await renderLoaded({ monday: [{ open: "05:30", close: "21:00" }] }, { "PATCH /settings/hours": { status: 200, body: hoursSection({}, 1) } });

    await user.click(closed("Lunes"));
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await screen.findByText("Cambios guardados");
    expect((mock.callsTo("PATCH /settings/hours")[0]?.body as { value: { monday: unknown } }).value.monday).toEqual([]);
  });

  it("apertura posterior al cierre da un error bajo el día y no llama al api", async () => {
    const { mock, user } = await renderLoaded();

    await user.click(closed("Lunes"));
    setTime("Lunes: abre", "21:00");
    setTime("Lunes: cierra", "05:00");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("La hora de apertura debe ser anterior a la de cierre. Corrige los horarios del lunes.")).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/hours")).toHaveLength(0);
  });

  it("un día abierto sin horas pide escribirlas", async () => {
    const { mock, user } = await renderLoaded();

    await user.click(closed("Martes"));
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findAllByText("Escribe la hora de apertura y la de cierre.")).not.toHaveLength(0);
    expect(mock.callsTo("PATCH /settings/hours")).toHaveLength(0);
  });

  it("rangos solapados dan un error bajo el día", async () => {
    const { mock, user } = await renderLoaded({
      monday: [
        { open: "05:00", close: "12:00" },
        { open: "13:00", close: "20:00" },
      ],
    });

    setTime("Lunes: abre (segundo rango)", "11:00");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Los dos rangos del lunes se solapan. El segundo debe empezar cuando o después de que termina el primero.")).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/hours")).toHaveLength(0);
  });

  it("un 422 con value.monday se muestra bajo el lunes", async () => {
    const { user } = await renderLoaded({}, { "PATCH /settings/hours": fieldErrorReply("value.monday") });

    await user.click(closed("Lunes"));
    setTime("Lunes: abre", "05:00");
    setTime("Lunes: cierra", "21:00");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    const group = await screen.findByRole("group", { name: "Lunes" });
    await waitFor(() => {
      expect(group).toHaveTextContent("El servidor no aceptó el horario del lunes");
    });
    expect(screen.queryByText("Cambios guardados")).not.toBeInTheDocument();
  });

  it("un 409 muestra el aviso de conflicto con Recargar", async () => {
    const { user } = await renderLoaded({}, { "PATCH /settings/hours": CONFLICT_REPLY });

    await user.click(closed("Lunes"));
    setTime("Lunes: abre", "05:00");
    setTime("Lunes: cierra", "21:00");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Otra persona cambió esta sección. Recarga para ver los cambios.");
    expect(screen.getByRole("button", { name: "Recargar" })).toBeInTheDocument();
  });

  it("es accesible", async () => {
    const { container } = await renderLoaded({ monday: [{ open: "05:30", close: "21:00" }] });

    expect(await axe(container)).toHaveNoViolations();
  });
});
