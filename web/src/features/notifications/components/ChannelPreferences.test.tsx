// S5-F3 · US-123 (front): preferencias de canal de aviso de un socio (GET y PATCH /members/{id}/channels).
// - Dos interruptores con su etiqueta de texto: "Correo" (opt-in) y "WhatsApp manual" (activo salvo que se apague).
// - Notas: el correo es opt-in; "sin consentimiento no se avisa" cuando el socio no autorizó sus datos.
// - Cada cambio hace un PATCH con ese canal; 422 `consent_required` y demás errores con el mensaje del api.
// - Un socio dado de baja es de solo lectura (N-20).
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { apiError, CHANNELS_PATH, channelsOut, MEMBER_ID } from "../../../test/memberNotifications";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { ChannelPreferences } from "./ChannelPreferences";

beforeEach(() => {
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderLoaded(handlers: Record<string, MockHandler> = {}, props: { readOnly?: boolean; body?: unknown } = {}) {
  const mock = mockApi({ [`GET ${CHANNELS_PATH}`]: { status: 200, body: props.body ?? channelsOut() }, ...handlers });
  const user = userEvent.setup();
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <ChannelPreferences memberId={MEMBER_ID} {...(props.readOnly ? { readOnly: true } : {})} />
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", { level: 2, name: "Canales de aviso" });
  await screen.findByRole("checkbox", { name: "Correo" });
  return { mock, user, ...view };
}

const email = () => screen.getByRole("checkbox", { name: "Correo" });
const whatsapp = () => screen.getByRole("checkbox", { name: "WhatsApp manual" });

describe("ChannelPreferences", () => {
  it("mientras carga dice 'Cargando los canales…'", () => {
    mockApi({ [`GET ${CHANNELS_PATH}`]: () => new Promise(() => undefined) });
    render(
      <QueryClientProvider client={testQueryClient()}>
        <ChannelPreferences memberId={MEMBER_ID} />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Cargando los canales…");
  });

  it("sin preferencias explícitas: correo apagado (opt-in) y WhatsApp manual activo", async () => {
    await renderLoaded();

    expect(email()).not.toBeChecked();
    expect(whatsapp()).toBeChecked();
  });

  it("con preferencias explícitas muestra lo que el socio tiene (correo sí, WhatsApp no)", async () => {
    await renderLoaded({}, { body: channelsOut({ channels: [{ channel: "email", active: true }, { channel: "whatsapp_link", active: false }], effective: ["email"] }) });

    expect(email()).toBeChecked();
    expect(whatsapp()).not.toBeChecked();
  });

  it("siempre explica el opt-in del correo y dice por dónde se le avisa", async () => {
    await renderLoaded();

    expect(screen.getByText("El correo es opt-in: solo se le escribe al socio si lo activas aquí.")).toBeInTheDocument();
    expect(screen.getByText("Se le avisa por: WhatsApp manual.")).toBeInTheDocument();
    expect(screen.queryByText(/Sin consentimiento no se avisa/)).not.toBeInTheDocument();
  });

  it("sin consentimiento dice 'Sin consentimiento no se avisa' y que no se avisa por nada", async () => {
    await renderLoaded({}, { body: channelsOut({ has_consent: false, effective: [] }) });

    expect(screen.getByText("Sin consentimiento no se avisa: este socio no autorizó el uso de sus datos, así que no recibe avisos por ningún canal.")).toBeInTheDocument();
    expect(screen.getByText("Se le avisa por: nadie.")).toBeInTheDocument();
  });

  it("activar el correo hace PATCH con ese canal y refleja la respuesta", async () => {
    const saved = channelsOut({ channels: [{ channel: "email", active: true }], effective: ["email", "whatsapp_link"] });
    const { mock, user } = await renderLoaded({ [`PATCH ${CHANNELS_PATH}`]: { status: 200, body: saved } });

    await user.click(email());

    expect(await screen.findByText("Preferencia guardada.")).toBeInTheDocument();
    expect(mock.callsTo(`PATCH ${CHANNELS_PATH}`)[0]?.body).toEqual({ items: [{ channel: "email", active: true }] });
    expect(email()).toBeChecked();
    expect(screen.getByText("Se le avisa por: correo y WhatsApp manual.")).toBeInTheDocument();
  });

  it("apagar WhatsApp manual envía active false", async () => {
    const saved = channelsOut({ channels: [{ channel: "whatsapp_link", active: false }], effective: [] });
    const { mock, user } = await renderLoaded({ [`PATCH ${CHANNELS_PATH}`]: { status: 200, body: saved } });

    await user.click(whatsapp());

    await screen.findByText("Preferencia guardada.");
    expect(mock.callsTo(`PATCH ${CHANNELS_PATH}`)[0]?.body).toEqual({ items: [{ channel: "whatsapp_link", active: false }] });
    expect(whatsapp()).not.toBeChecked();
  });

  it("mientras guarda, los interruptores quedan deshabilitados y ocupados", async () => {
    let release: (value: { status: number; body: unknown }) => void = () => undefined;
    const pending = new Promise<{ status: number; body: unknown }>((resolve) => {
      release = resolve;
    });
    const { user } = await renderLoaded({ [`PATCH ${CHANNELS_PATH}`]: () => pending });

    await user.click(email());
    expect(email()).toBeDisabled();
    expect(whatsapp()).toBeDisabled();

    release({ status: 200, body: channelsOut({ channels: [{ channel: "email", active: true }] }) });
    await waitFor(() => {
      expect(email()).toBeEnabled();
    });
  });

  it("un 422 consent_required muestra el mensaje del api y el correo sigue apagado", async () => {
    const { user } = await renderLoaded({
      [`PATCH ${CHANNELS_PATH}`]: apiError(422, "consent_required", {}, undefined, "El socio no autorizó el uso de sus datos; no se puede activar el correo."),
    });

    await user.click(email());

    expect(await screen.findByRole("alert")).toHaveTextContent("El socio no autorizó el uso de sus datos; no se puede activar el correo.");
    expect(email()).not.toBeChecked();
  });

  it("un 409 (socio dado de baja) y un 404 muestran el mensaje del api", async () => {
    const { user } = await renderLoaded({ [`PATCH ${CHANNELS_PATH}`]: apiError(409, "member_deleted", {}, undefined, "El socio está dado de baja.") });

    await user.click(email());

    expect(await screen.findByRole("alert")).toHaveTextContent("El socio está dado de baja.");
  });

  it("un 429 pide esperar y un 500 da un mensaje general", async () => {
    const { user } = await renderLoaded({ [`PATCH ${CHANNELS_PATH}`]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) });
    await user.click(email());
    expect(await screen.findByRole("alert")).toHaveTextContent("Espera 30 segundos e intenta de nuevo.");
    cleanup();

    const second = await renderLoaded({ [`PATCH ${CHANNELS_PATH}`]: apiError(500, "internal_error", {}, undefined, "Traceback") });
    await second.user.click(email());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No pudimos guardar la preferencia. Intenta de nuevo en un momento.");
    expect(alert).not.toHaveTextContent("Traceback");
  });

  it("S5-D245: sin consentimiento el correo no se puede activar y no llama al PATCH; lo explica", async () => {
    const { mock, user } = await renderLoaded({}, { body: channelsOut({ has_consent: false, effective: [] }) });

    expect(email()).toBeDisabled();
    await user.click(email());

    expect(mock.callsTo(`PATCH ${CHANNELS_PATH}`)).toHaveLength(0);
    expect(screen.getByText("Para activar el correo, primero registra el consentimiento del socio en su ficha (pestaña Datos).")).toBeInTheDocument();
  });

  it("S5-D245: con consentimiento el correo sí se activa", async () => {
    const { mock, user } = await renderLoaded({ [`PATCH ${CHANNELS_PATH}`]: { status: 200, body: channelsOut({ channels: [{ channel: "email", active: true }] }) } });

    expect(email()).toBeEnabled();
    await user.click(email());

    await screen.findByText("Preferencia guardada.");
    expect(mock.callsTo(`PATCH ${CHANNELS_PATH}`)).toHaveLength(1);
    expect(screen.queryByText(/primero registra el consentimiento/)).not.toBeInTheDocument();
  });

  it.each([true, false])("S5-D245: desactivar el correo funciona con has_consent %s", async (hasConsent) => {
    const body = channelsOut({ has_consent: hasConsent, channels: [{ channel: "email", active: true }], effective: hasConsent ? ["email", "whatsapp_link"] : [] });
    const { mock, user } = await renderLoaded({ [`PATCH ${CHANNELS_PATH}`]: { status: 200, body: { ...body, channels: [{ channel: "email", active: false }] } } }, { body });

    expect(email()).toBeEnabled();
    await user.click(email());

    await screen.findByText("Preferencia guardada.");
    expect(mock.callsTo(`PATCH ${CHANNELS_PATH}`)[0]?.body).toEqual({ items: [{ channel: "email", active: false }] });
  });

  it("mientras guarda hay una región aria-live con 'Guardando…'", async () => {
    let release: (value: { status: number; body: unknown }) => void = () => undefined;
    const pending = new Promise<{ status: number; body: unknown }>((resolve) => {
      release = resolve;
    });
    const { user, container } = await renderLoaded({ [`PATCH ${CHANNELS_PATH}`]: () => pending });

    expect(container.querySelector("[aria-live=polite]")).toHaveTextContent("");
    await user.click(email());
    expect(container.querySelector("[aria-live=polite]")).toHaveTextContent("Guardando…");

    release({ status: 200, body: channelsOut({ channels: [{ channel: "email", active: true }] }) });
    await waitFor(() => {
      expect(container.querySelector("[aria-live=polite]")).toHaveTextContent("");
    });
  });

  it("de solo lectura (socio dado de baja) deshabilita los interruptores y lo explica", async () => {
    await renderLoaded({}, { readOnly: true });

    expect(email()).toBeDisabled();
    expect(whatsapp()).toBeDisabled();
    expect(screen.getByText("Este socio está dado de baja: sus preferencias son de solo lectura.")).toBeInTheDocument();
  });

  it("si la lectura falla ofrece Reintentar; con 403 explica el permiso; una respuesta inválida no se pinta", async () => {
    let calls = 0;
    mockApi({ [`GET ${CHANNELS_PATH}`]: () => (++calls === 1 ? apiError(500, "internal_error") : { status: 200, body: channelsOut() }) });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={testQueryClient()}>
        <ChannelPreferences memberId={MEMBER_ID} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("No pudimos cargar los canales del socio. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("checkbox", { name: "Correo" })).toBeInTheDocument();
    cleanup();

    mockApi({ [`GET ${CHANNELS_PATH}`]: apiError(403, "forbidden") });
    render(
      <QueryClientProvider client={testQueryClient()}>
        <ChannelPreferences memberId={MEMBER_ID} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("No tienes permiso para ver los canales de este socio. Si lo necesitas, pídeselo a un administrador.")).toBeInTheDocument();
    cleanup();

    mockApi({ [`GET ${CHANNELS_PATH}`]: { status: 200, body: { member_id: MEMBER_ID, channels: [] } } });
    render(
      <QueryClientProvider client={testQueryClient()}>
        <ChannelPreferences memberId={MEMBER_ID} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/La respuesta del servidor no es válida/)).toBeInTheDocument();
  });

  it.each([["claro", null], ["oscuro", "dark"]])("no tiene violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { container } = await renderLoaded({}, { body: channelsOut({ has_consent: false, effective: [] }) });

    expect(await axe(container)).toHaveNoViolations();
  });
});
