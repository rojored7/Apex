// S7-F2 · US-158 (front): cancelar las sesiones futuras de una franja (modal de confirmación con motivo).
// - Solo admin (`classes.schedule`); motivo obligatorio; el modal dice que NO desactiva la franja.
// - 200 con `cancelled_count`; 404, 403, 429 y 5xx dentro del modal.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError, SLOTS } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import type { SlotView } from "../api";
import { CancelFutureModal } from "./CancelFutureModal";

const KEY = `POST /class-slots/${SLOTS.manana.id}/cancel-future-sessions`;
const REASON = "La clase pasa a las 06:30";

function renderModal(handlers: Record<string, MockHandler> = {}, target: SlotView | null = SLOTS.manana) {
  const mock = mockApi({ [KEY]: { status: 200, body: { cancelled_count: 2 } }, ...handlers });
  const queryClient = testQueryClient();
  const onClose = vi.fn();
  const onDone = vi.fn();
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionRoleProvider>
        <MemoryRouter>
          <main>
            <h1>Clases</h1>
          </main>
          <CancelFutureModal slot={target} onClose={onClose} onDone={onDone} />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, queryClient, onClose, onDone, user: userEvent.setup(), ...view };
}

const dialog = () => screen.getByRole("dialog", { name: "¿Cancelar las sesiones futuras de la franja de las 06:00?" });
const reasonField = () => within(dialog()).getByRole("textbox", { name: /^Motivo/ });
const confirmButton = () => within(dialog()).getByRole("button", { name: "Sí, cancelar sesiones" });

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("CancelFutureModal", () => {
  it("dice que no desactiva la franja y pide un motivo obligatorio", () => {
    renderModal();

    expect(dialog()).toHaveAccessibleDescription(expect.stringContaining("no desactiva la franja") as string);
    expect(reasonField()).toBeRequired();
    expect(confirmButton()).toBeDisabled();
  });

  it("el coach no la ve", () => {
    signInAs("coach");
    renderModal();

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("sin franja no pinta nada", () => {
    renderModal({}, null);

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("envía el motivo recortado y avisa cuántas sesiones se cancelaron", async () => {
    const { user, mock, onDone } = renderModal();

    await user.type(reasonField(), `  ${REASON} `);
    await user.click(confirmButton());

    await waitFor(() => {
      expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ id: SLOTS.manana.id }), 2);
    });
    expect(mock.callsTo(KEY).map((c) => c.body)).toEqual([{ reason: REASON }]);
  });

  it("un doble clic manda un solo POST y la caché no conserva el motivo", async () => {
    let release: () => void = () => undefined;
    const { user, mock, queryClient, onDone } = renderModal({
      [KEY]: () =>
        new Promise((resolve) => {
          release = () => {
            resolve({ status: 200, body: { cancelled_count: 2 } });
          };
        }),
    });
    await user.type(reasonField(), REASON);

    await user.dblClick(confirmButton());
    release();

    await waitFor(() => {
      expect(onDone).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(mock.callsTo(KEY)).toHaveLength(1);
  });

  it("más de 200 caracteres no deja confirmar", async () => {
    const { user } = renderModal();
    await user.click(reasonField());
    await user.paste("a".repeat(201));

    expect(confirmButton()).toBeDisabled();
  });

  it("422 field=reason va bajo el motivo", async () => {
    const { user } = renderModal({ [KEY]: apiError(422, "validation_error", { field: "reason" }) });
    await user.type(reasonField(), REASON);

    await user.click(confirmButton());

    await waitFor(() => {
      expect(reasonField()).toHaveAccessibleDescription(expect.stringContaining("Escribe un motivo de 3 a 200 caracteres.") as string);
    });
  });

  it.each([
    [404, "slot_not_found", {}, "Esta franja ya no existe. Cierra este aviso y actualiza la lista."],
    [403, "forbidden", {}, "Solo un administrador puede cancelar sesiones. Si lo necesitas, pídeselo a uno."],
    [429, "rate_limited", { "Retry-After": "30" }, "Hiciste muchos cambios seguidos. Espera 30 segundos e intenta de nuevo."],
    [500, "internal_error", {}, "No pudimos cancelar las sesiones. Intenta de nuevo en un momento."],
  ])("%i %s como aviso del modal", async (status, code, headers, message) => {
    const { user, onDone } = renderModal({ [KEY]: apiError(status, code, {}, headers) });
    await user.type(reasonField(), REASON);

    await user.click(confirmButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
    expect(onDone).not.toHaveBeenCalled();
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderModal();

    expect(await axe(container.ownerDocument.body)).toHaveNoViolations();
  });
});
