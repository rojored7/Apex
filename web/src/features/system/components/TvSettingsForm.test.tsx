// S8-F5 · US-175 (front, S8-D30, S8-D32, L-4): pestaña «Pantalla de TV» de Configuración (?tab=tv).
// - Estado del token (últimos 4 y fecha, nunca el valor), refresco de 15 a 300 s y «Mostrar el ranking».
// - «Generar enlace nuevo» y «Revocar» piden confirmación; el enlace con `#token=` se ve UNA vez y nunca queda en la caché
//   (gcTime 0, sin persistir la respuesta de regenerate-token) ni en localStorage/sessionStorage.
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { CONFLICT_REPLY, SERVER_ERROR_REPLY, tvSection } from "../../../test/settings";
import { mockApi, renderWithProviders, type MockReply } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { TvSettingsForm } from "./TvSettingsForm";

const TOKEN = "Zk3-secreto-de-prueba-0123456789abcdefghijklmnopq";
const URL_TV = `https://apex.test/tv#token=${TOKEN}`;
const REGENERATED: MockReply = { status: 200, body: { token: TOKEN, url: URL_TV, token_last4: "nopq", rotated_at: "2026-10-21T15:00:00Z", version: 3 } };

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

async function renderLoaded(handlers: Record<string, MockReply> = {}, value = tvSection({ has_token: true, token_last4: "ab12", rotated_at: "2026-10-20T15:00:00Z", refresh_seconds: 30 }, 2)) {
  signInAs("admin");
  const mock = mockApi({ "GET /settings/tv": { status: 200, body: value }, ...handlers });
  const view = renderWithProviders(<TvSettingsForm />, { role: "admin" });
  await screen.findByRole("heading", { level: 2, name: "Pantalla de TV" });
  return { mock, user: userEvent.setup(), ...view };
}

describe("TvSettingsForm", () => {
  it("muestra el estado del token con sus últimos 4 y la fecha, nunca el valor, y qué muestra la pantalla", async () => {
    await renderLoaded();

    expect(screen.getByText(/Token activo/)).toBeInTheDocument();
    expect(screen.getByText(/termina en ab12/)).toBeInTheDocument();
    expect(screen.getByText(/20 oct 2026/)).toBeInTheDocument();
    expect(screen.getByText(/Qué muestra/)).toBeInTheDocument();
    expect(screen.getByText(/nombre e inicial del apellido/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /Enlace/ })).not.toBeInTheDocument();
  });

  it("sin token lo dice y ofrece «Generar enlace nuevo» sin «Revocar»", async () => {
    await renderLoaded({}, tvSection());

    expect(screen.getByText("Sin token: la pantalla de la pared no puede abrirse.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generar enlace nuevo" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revocar" })).not.toBeInTheDocument();
  });

  it("guarda refresco y ranking con la versión leída y solo esos dos campos", async () => {
    const { mock, user } = await renderLoaded({ "PATCH /settings/tv": { status: 200, body: tvSection({ has_token: true, token_last4: "ab12", refresh_seconds: 60, show_leaderboard: false }, 3) } });

    const refresh = screen.getByRole("spinbutton", { name: /Refresco/ });
    await user.clear(refresh);
    await user.type(refresh, "60");
    await user.click(screen.getByRole("checkbox", { name: "Mostrar el ranking" }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/tv")[0]?.body).toEqual({ value: { refresh_seconds: 60, show_leaderboard: false }, version: 2 });
  });

  it.each([
    ["14", "Escribe un número entre 15 y 300."],
    ["301", "Escribe un número entre 15 y 300."],
    ["", "Escribe un número."],
  ])("refresco %j muestra «%s» y no llama al api", async (value, message) => {
    const { mock, user } = await renderLoaded();
    const refresh = screen.getByRole("spinbutton", { name: /Refresco/ });

    await user.clear(refresh);
    if (value) await user.type(refresh, value);
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(mock.callsTo("PATCH /settings/tv")).toHaveLength(0);
  });

  it("un 409 de versión avisa y deja Recargar", async () => {
    const { user } = await renderLoaded({ "PATCH /settings/tv": CONFLICT_REPLY });

    await user.type(screen.getByRole("spinbutton", { name: /Refresco/ }), "0");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Otra persona cambió esta sección. Recarga para ver los cambios.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recargar" })).toBeInTheDocument();
  });

  it("«Generar enlace nuevo» avisa que el anterior deja de servir y no llama hasta confirmar", async () => {
    const { mock, user } = await renderLoaded({ "POST /settings/tv/regenerate-token": REGENERATED });

    await user.click(screen.getByRole("button", { name: "Generar enlace nuevo" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/la pantalla actual mostrará «Token inválido»/)).toBeInTheDocument();
    expect(mock.callsTo("POST /settings/tv/regenerate-token")).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Volver" }));
    expect(mock.callsTo("POST /settings/tv/regenerate-token")).toHaveLength(0);
  });

  it("al confirmar muestra el enlace con #token= una vez, con «Copiar» y «Abrir», y al cerrarlo ya no está", async () => {
    const { mock, user } = await renderLoaded({ "POST /settings/tv/regenerate-token": REGENERATED });

    await user.click(screen.getByRole("button", { name: "Generar enlace nuevo" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Generar enlace" }));

    const link = await screen.findByRole("textbox", { name: "Enlace de la TV" });
    expect(link).toHaveValue(URL_TV);
    expect(screen.getByRole("button", { name: "Copiar" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Abrir la TV" })).toHaveAttribute("href", URL_TV);
    expect(screen.getByRole("link", { name: "Abrir la TV" })).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText(/Genera el enlace en otro equipo/)).toBeInTheDocument();
    expect(mock.callsTo("POST /settings/tv/regenerate-token")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Listo" }));
    expect(screen.queryByRole("textbox", { name: "Enlace de la TV" })).not.toBeInTheDocument();
  });

  it("no_persiste_el_token_en_la_cache: ni en la caché de consultas, ni en la de mutaciones, ni en el almacenamiento del navegador", async () => {
    const { user, queryClient } = await renderLoaded({ "POST /settings/tv/regenerate-token": REGENERATED });

    await user.click(screen.getByRole("button", { name: "Generar enlace nuevo" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Generar enlace" }));
    await screen.findByRole("textbox", { name: "Enlace de la TV" });
    await act(async () => {
      await Promise.resolve();
    });

    const queries = JSON.stringify(queryClient.getQueryCache().getAll().map((q) => q.state.data));
    const mutations = JSON.stringify(queryClient.getMutationCache().getAll().map((m) => [m.state.data, m.state.variables]));
    expect(queries).not.toContain(TOKEN);
    expect(mutations).not.toContain(TOKEN);
    expect(JSON.stringify(Object.entries(window.localStorage))).not.toContain(TOKEN);
    expect(JSON.stringify(Object.entries(window.sessionStorage))).not.toContain(TOKEN);
  });

  it("tras regenerar relee el estado de la sección (ya no se confía en la respuesta del token)", async () => {
    let reads = 0;
    signInAs("admin");
    const mock = mockApi({
      "GET /settings/tv": () => {
        reads += 1;
        return { status: 200, body: reads === 1 ? tvSection() : tvSection({ has_token: true, token_last4: "nopq", rotated_at: "2026-10-21T15:00:00Z" }, 3) };
      },
      "POST /settings/tv/regenerate-token": REGENERATED,
    });
    const user = userEvent.setup();
    renderWithProviders(<TvSettingsForm />, { role: "admin" });
    await screen.findByText(/^Sin token/);

    await user.click(screen.getByRole("button", { name: "Generar enlace nuevo" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Generar enlace" }));

    expect(await screen.findByText(/termina en nopq/)).toBeInTheDocument();
    expect(mock.callsTo("GET /settings/tv").length).toBeGreaterThanOrEqual(2);
  });

  it("«Revocar» pide confirmación, llama revoke-token y deja «Sin token»", async () => {
    const { mock, user } = await renderLoaded({ "POST /settings/tv/revoke-token": { status: 200, body: tvSection({ has_token: false }, 3) } });

    await user.click(screen.getByRole("button", { name: "Revocar" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/pantalla dejará de abrir hasta que generes otro enlace/)).toBeInTheDocument();
    expect(mock.callsTo("POST /settings/tv/revoke-token")).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Revocar token" }));

    expect(await screen.findByText(/^Sin token/)).toBeInTheDocument();
    expect(mock.callsTo("POST /settings/tv/revoke-token")).toHaveLength(1);
  });

  it("un error al generar lo dice en el diálogo y no muestra ningún enlace", async () => {
    const { user } = await renderLoaded({ "POST /settings/tv/regenerate-token": SERVER_ERROR_REPLY });

    await user.click(screen.getByRole("button", { name: "Generar enlace nuevo" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Generar enlace" }));

    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("No pudimos generar el enlace");
    expect(screen.queryByRole("textbox", { name: "Enlace de la TV" })).not.toBeInTheDocument();
  });

  it("sin permiso (403) la lectura dice que lo pida a un administrador", async () => {
    signInAs("admin");
    mockApi({ "GET /settings/tv": { status: 403, body: { error: { code: "forbidden", message: "x" } } } });
    renderWithProviders(<TvSettingsForm />, { role: "admin" });

    expect(await screen.findByText(/No tienes permiso para ver esta sección/)).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = await renderLoaded();

    await waitFor(async () => {
      expect(await axe(container)).toHaveNoViolations();
    });
  });
});
