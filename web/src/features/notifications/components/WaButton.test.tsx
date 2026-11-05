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
import { WaButton } from "./WaButton";

const JUAN = NOTIFICATIONS.juan;
const WA_KEY = `POST /notifications/${JUAN.id}/wa-link`;
const css = readFileSync("src/features/notifications/components/WaButton.module.css", "utf8");

let openSpy: ReturnType<typeof vi.fn>;

function mount(queryClient: QueryClient = testQueryClient(), onOpened?: () => void) {
  return render(
    <QueryClientProvider client={queryClient}>
      <WaButton notificationId={JUAN.id} memberName={JUAN.member_name} {...(onOpened ? { onOpened } : {})} />
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

    expect(await screen.findByRole("alert")).toHaveTextContent("El teléfono de este socio no es un celular válido. Corrígelo en su ficha.");
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
