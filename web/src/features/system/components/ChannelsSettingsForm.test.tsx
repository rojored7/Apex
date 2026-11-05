// S5-F2 · US-122 (front): pestaña "Canales" de Configuración (Config.html, "4 · Canales de aviso").
// - GET y PATCH /settings/channels con la versión leída (useSectionForm).
// - Insignia por canal desde `credentials_present` (S5-D204): "Credenciales listas" o "Faltan
//   credenciales en .env". El formulario nunca pide ni muestra contraseñas, tokens ni claves.
// - Campos: correo (activo, nombre del remitente, responder a), WhatsApp (activo, indicativo) y
//   Telegram (activo). Validación con Zod; 422 con campo bajo el campo y sin campo como aviso; 409.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { mockApi, renderWithProviders, type MockReply } from "../../../test/server";
import { channelsSection, CONFLICT_REPLY, fieldErrorReply, SERVER_ERROR_REPLY } from "../../../test/settings";
import { ChannelsSettingsForm } from "./ChannelsSettingsForm";

beforeEach(() => {
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderLoaded(handlers: Record<string, MockReply> = {}, section = channelsSection()) {
  const mock = mockApi({ "GET /settings/channels": { status: 200, body: section }, ...handlers });
  const user = userEvent.setup();
  const view = renderWithProviders(<ChannelsSettingsForm />, { role: "admin" });
  await screen.findByRole("group", { name: "Correo" });
  return { mock, user, ...view };
}

const group = (name: string) => screen.getByRole("group", { name });
const senderBox = () => within(group("Correo")).getByRole("textbox", { name: /^Nombre del remitente/ });
const replyBox = () => within(group("Correo")).getByRole("textbox", { name: /^Responder a/ });
const countryBox = () => within(group("WhatsApp")).getByRole("textbox", { name: /^Indicativo del país/ });
const emailSwitch = () => within(group("Correo")).getByRole("checkbox", { name: "Enviar avisos por correo" });
const whatsappSwitch = () => within(group("WhatsApp")).getByRole("checkbox", { name: "Ofrecer WhatsApp manual (lista «Por avisar hoy»)" });
const telegramSwitch = () => within(group("Telegram")).getByRole("checkbox", { name: "Avisar al equipo por Telegram" });
const save = () => screen.getByRole("button", { name: "Guardar" });

describe("ChannelsSettingsForm", () => {
  it("muestra los tres canales con sus valores y todo apagado por defecto", async () => {
    await renderLoaded();

    expect(screen.getByRole("heading", { level: 2, name: "Canales de aviso" })).toBeInTheDocument();
    expect(emailSwitch()).not.toBeChecked();
    expect(whatsappSwitch()).not.toBeChecked();
    expect(telegramSwitch()).not.toBeChecked();
    expect(senderBox()).toHaveValue("APEX");
    expect(replyBox()).toHaveValue("");
    expect(countryBox()).toHaveValue("57");
  });

  it("muestra 'Credenciales listas' para el correo y 'Faltan credenciales en .env' para Telegram", async () => {
    await renderLoaded();

    expect(within(group("Correo")).getByText("Credenciales listas")).toBeInTheDocument();
    expect(within(group("Telegram")).getByText("Faltan credenciales en .env")).toBeInTheDocument();
    expect(within(group("WhatsApp")).getByText("No necesita credenciales")).toBeInTheDocument();
  });

  it("sin credenciales de correo avisa con el texto del diseño y explica qué pasa si se activa", async () => {
    await renderLoaded({}, channelsSection({}, 0, { email: false, telegram: false }));

    expect(within(group("Correo")).getByText("Faltan credenciales en .env")).toBeInTheDocument();
    expect(within(group("Correo")).getByText(/el correo no sale aunque esté activo/)).toBeInTheDocument();
  });

  it("nunca pide ni muestra contraseñas, tokens ni claves", async () => {
    const { container } = await renderLoaded();

    expect(container.querySelector("input[type=password]")).toBeNull();
    expect(screen.queryByLabelText(/contraseña|token|clave|password|secret/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /chat|bot/i })).not.toBeInTheDocument();
  });

  it("guarda los tres canales con la versión leída, el correo vacío como null y muestra «Cambios guardados»", async () => {
    const saved = channelsSection({ email: { enabled: true, sender_name: "Box Norte", reply_to: "hola@box.co" }, whatsapp: { enabled: true, country_code: "57" } }, 1);
    const { mock, user } = await renderLoaded({ "PATCH /settings/channels": { status: 200, body: saved } });

    await user.click(emailSwitch());
    await user.click(whatsappSwitch());
    await user.clear(senderBox());
    await user.type(senderBox(), "  Box Norte ");
    await user.type(replyBox(), "hola@box.co");
    await user.click(save());

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/channels")[0]?.body).toEqual({
      value: {
        email: { enabled: true, sender_name: "Box Norte", reply_to: "hola@box.co" },
        whatsapp: { enabled: true, country_code: "57" },
        telegram: { enabled: false },
      },
      version: 0,
    });
    expect(within(group("Correo")).getByText("Credenciales listas")).toBeInTheDocument();
  });

  it("un responder-a vacío viaja como null", async () => {
    const { mock, user } = await renderLoaded({ "PATCH /settings/channels": { status: 200, body: channelsSection({}, 1) } });

    await user.click(telegramSwitch());
    await user.click(save());

    await screen.findByText("Cambios guardados");
    expect(mock.callsTo("PATCH /settings/channels")[0]?.body).toMatchObject({ value: { email: { reply_to: null }, telegram: { enabled: true } } });
  });

  it("un remitente vacío, un correo inválido y un indicativo inválido se explican y no llaman al api", async () => {
    const { mock, user } = await renderLoaded();

    await user.clear(senderBox());
    await user.type(replyBox(), "no-es-correo");
    await user.clear(countryBox());
    await user.type(countryBox(), "+57");
    await user.click(save());

    expect(await screen.findByText("Escribe el nombre del remitente.")).toBeInTheDocument();
    expect(screen.getByText("Escribe un correo válido, por ejemplo hola@mibox.co.")).toBeInTheDocument();
    expect(screen.getByText("El indicativo tiene de 1 a 3 dígitos, sin el signo +.")).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/channels")).toHaveLength(0);
  });

  it("un remitente de más de 80 caracteres se explica", async () => {
    const { user } = await renderLoaded();

    await user.clear(senderBox());
    await user.click(senderBox());
    await user.paste("B".repeat(81));
    await user.click(save());

    expect(await screen.findByText("El remitente admite hasta 80 caracteres.")).toBeInTheDocument();
  });

  it("un 422 con campo marca ese campo con un mensaje que dice qué hacer", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/channels": fieldErrorReply("value.email.sender_name") });

    await user.click(save());

    await waitFor(() => {
      expect(senderBox()).toHaveAttribute("aria-invalid", "true");
    });
    expect(senderBox()).toHaveAccessibleDescription(expect.stringContaining("El servidor no aceptó este nombre. Revísalo y vuelve a guardar."));
  });

  it("un 422 sin campo (validation_error) se muestra como aviso con el mensaje del api", async () => {
    const { user } = await renderLoaded({
      "PATCH /settings/channels": { status: 422, body: { error: { code: "validation_error", message: "Los canales no son válidos. Revisa los datos." } } },
    });

    await user.click(save());

    expect(await screen.findByRole("alert")).toHaveTextContent("Los canales no son válidos. Revisa los datos.");
  });

  it("un 409 version_conflict ofrece Recargar y bloquea Guardar", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/channels": CONFLICT_REPLY });

    await user.click(save());

    expect(await screen.findByText("Otra persona cambió esta sección. Recarga para ver los cambios.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recargar" })).toBeInTheDocument();
    expect(save()).toBeDisabled();
  });

  it("un 500 al guardar da un aviso general", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/channels": SERVER_ERROR_REPLY });

    await user.click(save());

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("si la lectura falla ofrece Reintentar y con 403 explica el permiso", async () => {
    mockApi({ "GET /settings/channels": SERVER_ERROR_REPLY });
    renderWithProviders(<ChannelsSettingsForm />, { role: "admin" });
    expect(await screen.findByText("No pudimos cargar esta sección. Revisa tu conexión e intenta de nuevo.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    cleanup();

    mockApi({ "GET /settings/channels": { status: 403, body: { error: { code: "forbidden", message: "No." } } } });
    renderWithProviders(<ChannelsSettingsForm />, { role: "admin" });
    expect(await screen.findByText("No tienes permiso para ver esta sección. Pide a un administrador que la revise.")).toBeInTheDocument();
  });

  it("una respuesta sin credentials_present no se pinta (respuesta inválida)", async () => {
    mockApi({ "GET /settings/channels": { status: 200, body: { ...channelsSection(), credentials_present: undefined } } });
    renderWithProviders(<ChannelsSettingsForm />, { role: "admin" });

    expect(await screen.findByText("No pudimos cargar esta sección. Revisa tu conexión e intenta de nuevo.")).toBeInTheDocument();
  });

  it.each([["claro", null], ["oscuro", "dark"]])("no tiene violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { container } = await renderLoaded();

    expect(await axe(container)).toHaveNoViolations();
  });
});
