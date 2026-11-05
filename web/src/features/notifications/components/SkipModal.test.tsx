// S5-F1 · US-129 (front): "Omitir" pide un motivo de 3 a 500 caracteres.
// - Sin motivo (o de menos de 3) el botón "Omitir aviso" está deshabilitado; más de 500 da un error.
// - POST /notifications/{id}/skip {reason}; el error del api se queda dentro del diálogo.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { apiError, NOTIFICATIONS } from "../../../test/notifications";
import { mockApi, testQueryClient } from "../../../test/server";
import { SkipModal } from "./SkipModal";

const CAMILA = NOTIFICATIONS.camila;
const SKIP_KEY = `POST /notifications/${CAMILA.id}/skip`;

function mount(onClose = vi.fn(), onSkipped = vi.fn(), target: { id: string; member_name: string } | null = CAMILA) {
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SkipModal target={target} onClose={onClose} onSkipped={onSkipped} />
    </QueryClientProvider>,
  );
  return { ...view, onClose, onSkipped };
}

const confirm = () => screen.getByRole("button", { name: "Omitir aviso" });
const reason = () => screen.getByRole("textbox", { name: /Motivo/ });

beforeEach(() => {
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SkipModal", () => {
  it("sin objetivo no pinta nada", () => {
    mockApi({});
    mount(vi.fn(), vi.fn(), null);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("pregunta por el socio, explica la consecuencia y deshabilita la acción con el motivo vacío", () => {
    mockApi({});
    mount();

    expect(screen.getByRole("dialog", { name: "¿Omitir el aviso de Camila Torres?" })).toBeInTheDocument();
    expect(screen.getByText(/queda en el historial como omitido/)).toBeInTheDocument();
    expect(screen.getByText(/No escribas teléfonos, documentos ni datos de salud/)).toBeInTheDocument();
    expect(confirm()).toBeDisabled();
  });

  it("con menos de 3 caracteres sigue deshabilitado; con 3 se habilita", async () => {
    mockApi({});
    const user = userEvent.setup();
    mount();

    await user.type(reason(), "ab");
    expect(confirm()).toBeDisabled();
    await user.type(reason(), "c");
    expect(confirm()).toBeEnabled();
  });

  it("espacios solos no cuentan como motivo", async () => {
    mockApi({});
    const user = userEvent.setup();
    mount();

    await user.type(reason(), "     ");

    expect(confirm()).toBeDisabled();
  });

  it("con más de 500 caracteres avisa y deshabilita; con 500 exactos se puede", async () => {
    mockApi({});
    const user = userEvent.setup();
    mount();

    await user.click(reason());
    await user.paste("x".repeat(501));
    expect(confirm()).toBeDisabled();
    expect(screen.getByText("El motivo admite hasta 500 caracteres.")).toBeInTheDocument();

    await user.clear(reason());
    await user.paste("x".repeat(500));
    expect(confirm()).toBeEnabled();
  });

  it("envía el motivo recortado, avisa con el aviso omitido y cierra", async () => {
    const mock = mockApi({ [SKIP_KEY]: { status: 200, body: { ...CAMILA, status: "skipped", skip_reason: "Ya pagó en el box" } } });
    const user = userEvent.setup();
    const { onClose, onSkipped } = mount();

    await user.type(reason(), "  Ya pagó en el box ");
    await user.click(confirm());

    await waitFor(() => {
      expect(onClose).toHaveBeenCalledTimes(1);
    });
    expect(mock.callsTo(SKIP_KEY)[0]?.body).toEqual({ reason: "Ya pagó en el box" });
    expect(onSkipped).toHaveBeenCalledWith("Camila Torres");
  });

  it("un 409 deja el diálogo abierto con un mensaje que dice qué hacer", async () => {
    mockApi({ [SKIP_KEY]: apiError(409, "notification_closed") });
    const user = userEvent.setup();
    const { onClose, onSkipped } = mount();

    await user.type(reason(), "Ya pagó");
    await user.click(confirm());

    expect(await screen.findByRole("alert")).toHaveTextContent("Este aviso ya no está pendiente. La lista se actualiza sola; cierra este diálogo.");
    expect(onClose).not.toHaveBeenCalled();
    expect(onSkipped).not.toHaveBeenCalled();
  });

  it("un 429 pide esperar", async () => {
    mockApi({ [SKIP_KEY]: apiError(429, "rate_limited", {}, { "Retry-After": "10" }) });
    const user = userEvent.setup();
    mount();

    await user.type(reason(), "Ya pagó");
    await user.click(confirm());

    expect(await screen.findByRole("alert")).toHaveTextContent("Espera 10 segundos e intenta de nuevo.");
  });

  it("Volver cierra sin enviar", async () => {
    const mock = mockApi({});
    const user = userEvent.setup();
    const { onClose } = mount();

    await user.click(screen.getByRole("button", { name: "Volver" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(mock.calls).toHaveLength(0);
  });

  it.each([["claro", null], ["oscuro", "dark"]])("no tiene violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    mockApi({});
    mount();

    expect(await axe(document.body)).toHaveNoViolations();
  });
});
