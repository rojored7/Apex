// S2-F5 · US-055: pestaña Gimnasio. Siete campos de 44 px, "Guardar" con estado de envío,
// "Cambios guardados", errores bajo el campo (cliente y 422 del api), conflicto 409 con
// "Recargar" sin sobrescribir, estados de carga y error, y el nombre nuevo en la sesión.
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { getSession } from "../../../core/auth/session";
import { mockApi, renderWithProviders, type MockReply } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { CONFLICT_REPLY, deferred, fieldErrorReply, gymSection, SERVER_ERROR_REPLY } from "../../../test/settings";
import { settingsQueryKey } from "../api";
import { GymSettingsForm } from "./GymSettingsForm";

const LABELS = ["Nombre", "NIT", "Dirección", "Ciudad", "Teléfono", "WhatsApp Business", "Correo de contacto"];

afterEach(() => {
  vi.unstubAllGlobals();
  signOutForTests();
});

async function renderLoaded(handlers: Record<string, MockReply | (() => MockReply | Promise<MockReply>)> = {}, onDirtyChange = vi.fn()) {
  const mock = mockApi({ "GET /settings/gym": { status: 200, body: gymSection() }, ...handlers });
  const user = userEvent.setup();
  const view = renderWithProviders(<GymSettingsForm onDirtyChange={onDirtyChange} />, { role: "admin" });
  await screen.findByRole("textbox", { name: /Nombre/ });
  return { mock, user, onDirtyChange, ...view };
}

describe("GymSettingsForm", () => {
  it("muestra un estado de carga y luego los siete campos con los datos del api", async () => {
    mockApi({ "GET /settings/gym": { status: 200, body: gymSection({ name: "APEX CrossFit", city: "Bogotá" }, 2) } });
    renderWithProviders(<GymSettingsForm />, { role: "admin" });

    expect(screen.getByRole("status")).toHaveTextContent("Cargando la sección…");
    const name = await screen.findByRole("textbox", { name: /Nombre/ });

    expect(name).toHaveValue("APEX CrossFit");
    expect(screen.getByRole("textbox", { name: "Ciudad" })).toHaveValue("Bogotá");
    for (const label of LABELS) expect(screen.getByLabelText(new RegExp(`^${label}`))).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Gimnasio" })).toBeInTheDocument();
    expect(name).toHaveAttribute("aria-required", "true");
  });

  it("los campos y el botón usan el control de 44 px del kit", async () => {
    await renderLoaded();

    for (const label of LABELS) expect(screen.getByLabelText(new RegExp(`^${label}`))).toHaveClass("control", "md");
    expect(screen.getByRole("button", { name: "Guardar" })).toHaveClass("button", "md");
  });

  it("si la lectura falla explica qué pasó y Reintentar vuelve a pedirla", async () => {
    let calls = 0;
    mockApi({
      "GET /settings/gym": () => {
        calls += 1;
        return calls === 1 ? SERVER_ERROR_REPLY : { status: 200, body: gymSection() };
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<GymSettingsForm />, { role: "admin" });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No pudimos cargar esta sección. Revisa tu conexión e intenta de nuevo.");
    await user.click(within(alert).getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("textbox", { name: /Nombre/ })).toHaveValue("APEX");
  });

  it("un 403 al leer dice que no hay permiso, sin botón de reintento", async () => {
    mockApi({ "GET /settings/gym": { status: 403, body: { error: { code: "forbidden", message: "No tienes permiso." } } } });
    renderWithProviders(<GymSettingsForm />, { role: "admin" });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No tienes permiso para ver esta sección. Pide a un administrador que la revise.");
    expect(within(alert).queryByRole("button")).not.toBeInTheDocument();
  });

  it("guarda la sección completa con la versión leída y muestra Cambios guardados", async () => {
    const { mock, user } = await renderLoaded({
      "PATCH /settings/gym": { status: 200, body: gymSection({ name: "APEX CrossFit Bogotá", nit: "901234567-8", email: "box@apex.co" }, 1) },
    });

    const name = screen.getByRole("textbox", { name: /Nombre/ });
    await user.clear(name);
    await user.type(name, "APEX CrossFit Bogotá");
    await user.type(screen.getByRole("textbox", { name: "NIT" }), "901234567-8");
    await user.type(screen.getByRole("textbox", { name: "Correo de contacto" }), "Box@APEX.co");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/gym")[0]?.body).toEqual({
      value: { name: "APEX CrossFit Bogotá", nit: "901234567-8", address: null, city: null, phone: null, whatsapp: null, email: "Box@APEX.co" },
      version: 0,
    });
    // El servidor guarda el correo en minúsculas: el formulario muestra lo guardado.
    expect(screen.getByRole("textbox", { name: "Correo de contacto" })).toHaveValue("box@apex.co");
  });

  it("Cambios guardados desaparece al volver a editar", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/gym": { status: 200, body: gymSection({ name: "Box" }, 1) } });
    const name = screen.getByRole("textbox", { name: /Nombre/ });
    await user.clear(name);
    await user.type(name, "Box");
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await screen.findByText("Cambios guardados");

    await user.type(name, " Norte");

    expect(screen.queryByText("Cambios guardados")).not.toBeInTheDocument();
  });

  it("mientras guarda, el botón queda ocupado y no envía dos veces", async () => {
    const pending = deferred<MockReply>();
    const { mock, user } = await renderLoaded({ "PATCH /settings/gym": () => pending.promise });

    await user.type(screen.getByRole("textbox", { name: "Ciudad" }), "Bogotá");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    const button = screen.getByRole("button", { name: "Guardar" });
    await waitFor(() => {
      expect(button).toHaveAttribute("aria-busy", "true");
    });
    expect(button).toBeDisabled();
    // Los campos quedan de solo lectura: lo guardado no pisa algo escrito durante el envío.
    expect(screen.getByRole("textbox", { name: "Ciudad" })).toBeDisabled();
    await user.click(button);
    pending.resolve({ status: 200, body: gymSection({ city: "Bogotá" }, 1) });

    await screen.findByText("Cambios guardados");
    expect(mock.callsTo("PATCH /settings/gym")).toHaveLength(1);
  });

  it.each([
    ["Nombre", "", "Escribe el nombre del gimnasio."],
    ["NIT", "90A", "El NIT no es válido. Usa solo dígitos y, si tiene, un guion con el dígito de verificación: 901234567-8."],
    ["Correo de contacto", "box@", "El correo no es válido. Escríbelo completo, por ejemplo box@ejemplo.com."],
  ])("valida %s en el navegador y no llama al api", async (label, value, message) => {
    const { mock, user } = await renderLoaded();
    const input = screen.getByLabelText(new RegExp(`^${label}`));

    await user.clear(input);
    if (value) await user.type(input, value);
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(expect.stringContaining(message));
    expect(mock.callsTo("PATCH /settings/gym")).toHaveLength(0);
  });

  it("un 422 con field value.email marca el campo Correo con un mensaje claro", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/gym": fieldErrorReply("value.email") });

    await user.type(screen.getByRole("textbox", { name: "Correo de contacto" }), "box@apex.co");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    const email = screen.getByRole("textbox", { name: "Correo de contacto" });
    await waitFor(() => {
      expect(email).toHaveAttribute("aria-invalid", "true");
    });
    expect(email).toHaveAccessibleDescription(expect.stringContaining("El servidor no aceptó el correo. Revísalo y vuelve a guardar."));
    expect(screen.queryByText("Cambios guardados")).not.toBeInTheDocument();
  });

  it("un 422 de un campo que no está en el formulario se muestra como aviso general", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/gym": fieldErrorReply("value.logo") });

    await user.type(screen.getByRole("textbox", { name: "Ciudad" }), "Cali");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("El campo value.logo no es válido.");
  });

  it("un 409 muestra el aviso de conflicto, deshabilita Guardar y Recargar trae lo nuevo sin sobrescribir", async () => {
    let reads = 0;
    const { mock, user } = await renderLoaded({
      "GET /settings/gym": () => {
        reads += 1;
        return { status: 200, body: reads === 1 ? gymSection() : gymSection({ name: "Nombre de la otra persona" }, 5) };
      },
      "PATCH /settings/gym": CONFLICT_REPLY,
    });

    const name = screen.getByRole("textbox", { name: /Nombre/ });
    await user.clear(name);
    await user.type(name, "Mi cambio");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Otra persona cambió esta sección. Recarga para ver los cambios.");
    expect(screen.getByRole("button", { name: "Guardar" })).toBeDisabled();
    expect(name).toHaveValue("Mi cambio");
    expect(mock.callsTo("PATCH /settings/gym")).toHaveLength(1);

    await user.click(within(alert).getByRole("button", { name: "Recargar" }));

    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: /Nombre/ })).toHaveValue("Nombre de la otra persona");
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar" })).toBeEnabled();
    expect(mock.callsTo("PATCH /settings/gym")).toHaveLength(1);
  });

  it("si Recargar falla, conserva lo escrito y el aviso de conflicto, y lo explica", async () => {
    let reads = 0;
    const { user } = await renderLoaded({
      "GET /settings/gym": () => {
        reads += 1;
        return reads === 1 ? { status: 200, body: gymSection() } : SERVER_ERROR_REPLY;
      },
      "PATCH /settings/gym": CONFLICT_REPLY,
    });
    const name = screen.getByRole("textbox", { name: /Nombre/ });
    await user.clear(name);
    await user.type(name, "Mi cambio");
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    const conflict = await screen.findByText("Otra persona cambió esta sección. Recarga para ver los cambios.");

    await user.click(screen.getByRole("button", { name: "Recargar" }));

    expect(await screen.findByText("No pudimos recargar la sección. Revisa tu conexión y pulsa Recargar otra vez.")).toBeInTheDocument();
    expect(conflict).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Nombre/ })).toHaveValue("Mi cambio");
    expect(screen.getByRole("button", { name: "Guardar" })).toBeDisabled();
  });

  it("un error del servidor al guardar se explica y el formulario conserva lo escrito", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/gym": SERVER_ERROR_REPLY });

    await user.type(screen.getByRole("textbox", { name: "Dirección" }), "Cra 7 # 45-10");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Ocurrió un error inesperado. Intenta de nuevo.");
    expect(screen.getByRole("textbox", { name: "Dirección" })).toHaveValue("Cra 7 # 45-10");
  });

  it("avisa si hay cambios sin guardar y deja de avisar al guardar", async () => {
    const { user, onDirtyChange } = await renderLoaded({ "PATCH /settings/gym": { status: 200, body: gymSection({ city: "Cali" }, 1) } });

    await user.type(screen.getByRole("textbox", { name: "Ciudad" }), "Cali");
    expect(onDirtyChange).toHaveBeenLastCalledWith(true);

    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await screen.findByText("Cambios guardados");

    expect(onDirtyChange).toHaveBeenLastCalledWith(false);
  });

  it("al guardar, la sesión toma el nombre nuevo del gimnasio para el TopBar", async () => {
    signInAs("admin", { gymName: "APEX" });
    const { user } = await renderLoaded({ "PATCH /settings/gym": { status: 200, body: gymSection({ name: "APEX Norte" }, 1) } });

    const name = screen.getByRole("textbox", { name: /Nombre/ });
    await user.clear(name);
    await user.type(name, "APEX Norte");
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await screen.findByText("Cambios guardados");

    expect(getSession().user?.gymName).toBe("APEX Norte");
  });

  it("sin cambios sin guardar, una lectura con versión nueva actualiza el formulario", async () => {
    const { queryClient } = await renderLoaded();

    act(() => {
      queryClient.setQueryData(settingsQueryKey("gym"), gymSection({ name: "Cambiado en otra pestaña" }, 2));
    });

    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: /Nombre/ })).toHaveValue("Cambiado en otra pestaña");
    });
  });

  it("con cambios sin guardar, una lectura nueva no pisa lo escrito y el PATCH lleva la versión del formulario", async () => {
    const { queryClient, mock, user } = await renderLoaded({ "PATCH /settings/gym": CONFLICT_REPLY });
    await user.type(screen.getByRole("textbox", { name: "Ciudad" }), "Cali");

    act(() => {
      queryClient.setQueryData(settingsQueryKey("gym"), gymSection({ name: "Cambiado en otra pestaña" }, 2));
    });
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Otra persona cambió esta sección.");
    expect(screen.getByRole("textbox", { name: "Ciudad" })).toHaveValue("Cali");
    expect(mock.callsTo("PATCH /settings/gym")[0]?.body).toMatchObject({ version: 0 });
  });

  it("indica que la zona horaria es fija", async () => {
    await renderLoaded();

    expect(screen.getByText("Zona horaria: America/Bogota. Es fija para todo el sistema.")).toBeInTheDocument();
  });

  it("es accesible cargado y con errores", async () => {
    const { container, user } = await renderLoaded();
    expect(await axe(container)).toHaveNoViolations();

    await user.clear(screen.getByRole("textbox", { name: /Nombre/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await screen.findByText("Escribe el nombre del gimnasio.");

    expect(await axe(container)).toHaveNoViolations();
  });
});
