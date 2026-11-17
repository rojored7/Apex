// S5-F1 · US-127 (front): "Abrir WhatsApp".
// - POST /notifications/{id}/wa-link; window.open(url, "_blank", "noopener,noreferrer") solo tras
//   el 200 (el POST marca el aviso como enviado y descifra el teléfono, S5-D59).
// - La URL no queda en el estado, en el DOM ni en la caché de TanStack (M-9).
// - Objetivo táctil de al menos 44 px (--control). 422 invalid_phone y 429 muestran el mensaje del api.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { axe } from "vitest-axe";
import { apiError, NOTIFICATIONS, WA_URL } from "../../../test/notifications";
import { mockApi, testQueryClient, type MockReply } from "../../../test/server";
import { MemoryRouter } from "react-router";
import { WaButton } from "./WaButton";

const JUAN = NOTIFICATIONS.juan;
const WA_KEY = `POST /notifications/${JUAN.id}/wa-link`;
const css = readFileSync("src/features/notifications/components/WaButton.module.css", "utf8");

let openSpy: ReturnType<typeof vi.fn>;

function mount(queryClient: QueryClient = testQueryClient(), onOpened?: () => void) {
  return render(
    <QueryClientProvider client={queryClient}>
      <WaButton notificationId={JUAN.id} memberName={JUAN.member_name} memberId={JUAN.member_id} canWhatsapp {...(onOpened ? { onOpened } : {})} />
    </QueryClientProvider>,
  );
}

const button = () => screen.getByRole("button", { name: "Abrir WhatsApp de Juan Pérez" });

beforeEach(() => {
  openSpy = vi.fn(() => null);
  vi.stubGlobal("open", openSpy);
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WaButton", () => {
  it("muestra el texto 'Abrir WhatsApp' y un nombre accesible con el socio", () => {
    mockApi({});
    mount();

    expect(button()).toHaveTextContent("Abrir WhatsApp");
  });

  it("no abre nada antes de la respuesta y abre con noopener,noreferrer tras el 200", async () => {
    let release: (reply: MockReply) => void = () => undefined;
    const pending = new Promise<MockReply>((resolve) => {
      release = resolve;
    });
    mockApi({ [WA_KEY]: () => pending });
    const onOpened = vi.fn();
    const user = userEvent.setup();
    mount(testQueryClient(), onOpened);

    await user.click(button());
    expect(openSpy).not.toHaveBeenCalled();
    expect(button()).toBeDisabled();
    expect(button()).toHaveAttribute("aria-busy", "true");

    release({ status: 200, body: { url: WA_URL } });

    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledTimes(1);
    });
    expect(openSpy).toHaveBeenCalledWith(WA_URL, "_blank", "noopener,noreferrer");
    expect(onOpened).toHaveBeenCalledTimes(1);
  });

  it("la URL no queda en el DOM ni en la caché de consultas ni de mutaciones", async () => {
    mockApi({ [WA_KEY]: { status: 200, body: { url: WA_URL } } });
    const queryClient = testQueryClient();
    const user = userEvent.setup();
    const { container } = mount(queryClient);

    await user.click(button());
    await waitFor(() => {
      expect(openSpy).toHaveBeenCalled();
    });

    expect(container.innerHTML).not.toContain("wa.me");
    expect(container.innerHTML).not.toContain("573201234567");
    expect(JSON.stringify(queryClient.getQueryCache().getAll().map((q) => q.state.data))).not.toContain("wa.me");
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
  });

  it("un 422 invalid_phone muestra el mensaje del api y no abre nada", async () => {
    mockApi({ [WA_KEY]: apiError(422, "invalid_phone", {}, undefined, "El teléfono de este socio no es un celular válido. Corrígelo en su ficha.") });
    const user = userEvent.setup();
    mount();

    await user.click(button());

    expect(await screen.findByRole("alert")).toHaveTextContent("El teléfono de este socio no es un celular válido para WhatsApp. Corrígelo en su ficha o omite el aviso.");
    expect(openSpy).not.toHaveBeenCalled();
    expect(button()).toBeEnabled();
  });

  it("un 422 member_without_phone dice que falta el teléfono y qué hacer, sin abrir nada", async () => {
    mockApi({ [WA_KEY]: apiError(422, "member_without_phone", {}, undefined, "El socio no tiene teléfono.") });
    const user = userEvent.setup();
    mount();

    await user.click(button());

    expect(await screen.findByRole("alert")).toHaveTextContent("Este socio no tiene teléfono registrado. Agrégalo en su ficha o omite el aviso.");
    expect(openSpy).not.toHaveBeenCalled();
    expect(button()).toBeEnabled();
  });

  it("un 503 crypto_unavailable pide reintentar, sin abrir nada", async () => {
    mockApi({ [WA_KEY]: apiError(503, "crypto_unavailable", {}, { "Retry-After": "30" }, "Servicio de llaves no disponible.") });
    const user = userEvent.setup();
    mount();

    await user.click(button());

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos leer el teléfono del socio por ahora. Intenta de nuevo en unos segundos.");
    expect(openSpy).not.toHaveBeenCalled();
    expect(button()).toBeEnabled();
  });

  it("un 429 muestra el mensaje del api con la espera", async () => {
    mockApi({ [WA_KEY]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }, "Hiciste muchas aperturas seguidas.") });
    const user = userEvent.setup();
    mount();

    await user.click(button());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Hiciste muchas aperturas seguidas.");
    expect(alert).toHaveTextContent("Espera 30 segundos");
    expect(openSpy).not.toHaveBeenCalled();
  });

  it("un 409 explica que el aviso ya no se puede enviar", async () => {
    mockApi({ [WA_KEY]: apiError(409, "notification_closed", {}, undefined, "Este aviso ya fue omitido.") });
    const user = userEvent.setup();
    mount();

    await user.click(button());

    expect(await screen.findByRole("alert")).toHaveTextContent("Este aviso ya fue omitido.");
  });

  it("un 500 da un mensaje general, sin detalle técnico", async () => {
    mockApi({ [WA_KEY]: apiError(500, "internal_error", {}, undefined, "Traceback...") });
    const user = userEvent.setup();
    mount();

    await user.click(button());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No pudimos abrir WhatsApp. Intenta de nuevo en un momento.");
    expect(alert).not.toHaveTextContent("Traceback");
  });

  it("el error se quita al volver a intentar", async () => {
    let calls = 0;
    mockApi({ [WA_KEY]: () => (++calls === 1 ? apiError(429, "rate_limited") : { status: 200, body: { url: WA_URL } }) });
    const user = userEvent.setup();
    mount();

    await user.click(button());
    await screen.findByRole("alert");
    await user.click(button());

    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("su objetivo táctil mide al menos 44 px (usa --control)", () => {
    const rule = /\.wa\s*\{[^}]*\}/.exec(css)?.[0] ?? "";
    expect(rule).toMatch(/min-height:\s*calc\(var\(--control\)/);
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,6}\b/);
  });

  it.each([["claro", null], ["oscuro", "dark"]])("no tiene violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    mockApi({});
    const { container } = mount();

    expect(await axe(container)).toHaveNoViolations();
  });
});

// S9-X1 (S9-D22, L-5): con can_whatsapp = false el botón no se ofrece; se explica y se enlaza la ficha.
describe("WaButton sin posibilidad de abrir WhatsApp (S9-X1)", () => {
  const mountDisabled = () =>
    render(
      <MemoryRouter>
        <QueryClientProvider client={testQueryClient()}>
          <WaButton notificationId={JUAN.id} memberId={JUAN.member_id} memberName={JUAN.member_name} canWhatsapp={false} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

  it("queda deshabilitado con el texto 'No se puede abrir WhatsApp'", () => {
    mockApi({});
    mountDisabled();

    expect(button()).toBeDisabled();
    expect(screen.getByText("No se puede abrir WhatsApp")).toBeInTheDocument();
    expect(screen.queryByText("Sin teléfono")).not.toBeInTheDocument();
    expect(button()).toHaveAccessibleDescription(/No se puede abrir WhatsApp/);
  });

  it("ofrece un enlace a la ficha del socio", () => {
    mockApi({});
    mountDisabled();

    const link = screen.getByRole("link", { name: `Revisar la ficha de ${JUAN.member_name}` });
    expect(link).toHaveAttribute("href", `/socios/${JUAN.member_id}`);
    expect(link).toHaveTextContent("Revisar la ficha");
  });

  it("no llama al api ni abre nada al hacer clic", async () => {
    const mock = mockApi({ [WA_KEY]: { status: 200, body: { url: WA_URL } } });
    const user = userEvent.setup();
    mountDisabled();

    await user.click(button());

    expect(mock.callsTo(WA_KEY)).toHaveLength(0);
    expect(openSpy).not.toHaveBeenCalled();
  });

  it.each([["claro", null], ["oscuro", "dark"]])("el estado bloqueado no tiene violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    mockApi({});
    const { container } = mountDisabled();

    expect(await axe(container)).toHaveNoViolations();
  });

  it("el enlace de la ficha tiene objetivo táctil de 48 px y la regla solo usa tokens", () => {
    const rule = /\.reasonLink\s*\{[^}]*\}/.exec(css)?.[0] ?? "";
    expect(rule).toMatch(/min-height:\s*calc\(var\(--control\)/);
    expect(css).toMatch(/\.reasonLink:focus-visible/);
  });

  it("el error previo se limpia cuando la fila pasa a bloqueada", async () => {
    mockApi({ [WA_KEY]: apiError(429, "rate_limited") });
    const user = userEvent.setup();
    const client = testQueryClient();
    const view = (can: boolean) => (
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <WaButton notificationId={JUAN.id} memberId={JUAN.member_id} memberName={JUAN.member_name} canWhatsapp={can} />
        </QueryClientProvider>
      </MemoryRouter>
    );
    const { rerender } = render(view(true));
    await user.click(button());
    await screen.findByRole("alert");

    rerender(view(false));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("con can_whatsapp verdadero sigue abriendo y maneja el 409", async () => {
    mockApi({ [WA_KEY]: apiError(409, "notification_closed", {}, undefined, "Este aviso ya fue omitido.") });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <QueryClientProvider client={testQueryClient()}>
          <WaButton notificationId={JUAN.id} memberId={JUAN.member_id} memberName={JUAN.member_name} canWhatsapp />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await user.click(button());

    expect(await screen.findByRole("alert")).toHaveTextContent("Este aviso ya fue omitido.");
  });

  it("con can_whatsapp verdadero un 422 invalid_phone (fijo con indicativo) muestra el mensaje fijo", async () => {
    mockApi({ [WA_KEY]: apiError(422, "invalid_phone", {}, undefined, "texto del api") });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <QueryClientProvider client={testQueryClient()}>
          <WaButton notificationId={JUAN.id} memberId={JUAN.member_id} memberName={JUAN.member_name} canWhatsapp />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await user.click(button());

    expect(await screen.findByRole("alert")).toHaveTextContent("El teléfono de este socio no es un celular válido para WhatsApp. Corrígelo en su ficha o omite el aviso.");
    expect(openSpy).not.toHaveBeenCalled();
  });
});
