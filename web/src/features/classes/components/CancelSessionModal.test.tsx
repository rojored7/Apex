// S7-F3 · US-157 (front): cancelar una sesión (modal de confirmación con motivo; admin y coach).
// - Motivo obligatorio de 3 a 200 caracteres; la sesión queda cancelada con motivo y el padre avisa.
// - 409 `session_finished` y `session_already_cancelled`, 404, 403, 429 y 5xx dentro del modal.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError, SESSIONS } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import type { SessionView } from "../api";
import { CancelSessionModal } from "./CancelSessionModal";

const TARGET = SESSIONS.hoy17;
const KEY = `POST /class-sessions/${TARGET.id}/cancel`;
const REASON = "Se enfermó la coach";
const CANCELLED = { ...TARGET, status: "cancelled", cancel_reason: REASON, cancelled_at: "2026-10-20T15:00:00Z" };

function renderModal(handlers: Record<string, MockHandler> = {}, target: SessionView | null = TARGET) {
  const mock = mockApi({ [KEY]: { status: 200, body: CANCELLED }, ...handlers });
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
          <CancelSessionModal session={target} onClose={onClose} onDone={onDone} />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, queryClient, onClose, onDone, user: userEvent.setup(), ...view };
}

const dialog = () => screen.getByRole("dialog", { name: "¿Cancelar la sesión de las 17:00?" });
const reasonField = () => within(dialog()).getByRole("textbox", { name: /^Motivo/ });
const confirmButton = () => within(dialog()).getByRole("button", { name: "Sí, cancelar sesión" });

beforeEach(() => {
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("CancelSessionModal", () => {
  it("pregunta por la sesión, dice que queda cancelada con el motivo y pide un motivo obligatorio", () => {
    renderModal();

    expect(dialog()).toHaveAccessibleDescription(expect.stringContaining("La sesión queda cancelada con el motivo") as string);
    expect(reasonField()).toBeRequired();
    expect(confirmButton()).toBeDisabled();
  });

  it("también lo ve el admin y sin sesión no pinta nada", () => {
    signInAs("admin");
    renderModal();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    cleanup();
    renderModal({}, null);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("envía el motivo recortado y avisa al padre", async () => {
    const { user, mock, onDone } = renderModal();

    await user.type(reasonField(), `  ${REASON} `);
    await user.click(confirmButton());

    await waitFor(() => {
      expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ id: TARGET.id }));
    });
    expect(mock.callsTo(KEY).map((c) => c.body)).toEqual([{ reason: REASON }]);
  });

  it("un doble clic manda un solo POST y la caché no conserva el motivo", async () => {
    let release: () => void = () => undefined;
    const { user, mock, queryClient, onDone } = renderModal({
      [KEY]: () =>
        new Promise((resolve) => {
          release = () => {
            resolve({ status: 200, body: CANCELLED });
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

  it("menos de 3 o más de 200 caracteres no dejan confirmar", async () => {
    const { user } = renderModal();

    await user.type(reasonField(), " ab ");
    expect(confirmButton()).toBeDisabled();
    await user.clear(reasonField());
    await user.click(reasonField());
    await user.paste("a".repeat(201));
    expect(confirmButton()).toBeDisabled();
  });

  it.each([
    [409, "session_finished", {}, "Esta sesión ya terminó y no se puede cancelar."],
    [409, "session_already_cancelled", {}, "Otra persona ya canceló esta sesión. Actualizamos la semana."],
    [404, "session_not_found", {}, "Esta sesión ya no existe. Cierra este aviso y actualiza la semana."],
    [403, "forbidden", {}, "No tienes permiso para cancelar sesiones. Si lo necesitas, pídeselo a un administrador."],
    [429, "rate_limited", { "Retry-After": "30" }, "Hiciste muchos cambios seguidos. Espera 30 segundos e intenta de nuevo."],
    [500, "internal_error", {}, "No pudimos cancelar la sesión. Intenta de nuevo en un momento."],
  ])("%i %s como aviso del modal", async (status, code, headers, message) => {
    const { user, onDone } = renderModal({ [KEY]: apiError(status, code, {}, headers) });
    await user.type(reasonField(), REASON);

    await user.click(confirmButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
    expect(onDone).not.toHaveBeenCalled();
  });

  it.each([
    [409, "session_already_cancelled"],
    [409, "session_finished"],
    [404, "session_not_found"],
  ])("%i %s relee la semana: el aviso dice «Actualizamos la semana» y de verdad se invalida", async (status, code) => {
    const { user, queryClient } = renderModal({ [KEY]: apiError(status, code) });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    await user.type(reasonField(), REASON);

    await user.click(confirmButton());

    await within(dialog()).findByRole("alert");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["class-sessions"] });
  });

  it("un 500 no invalida las sesiones", async () => {
    const { user, queryClient } = renderModal({ [KEY]: apiError(500, "internal_error") });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    await user.type(reasonField(), REASON);

    await user.click(confirmButton());

    await within(dialog()).findByRole("alert");
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("422 field=reason va bajo el motivo", async () => {
    const { user } = renderModal({ [KEY]: apiError(422, "validation_error", { field: "reason" }) });
    await user.type(reasonField(), REASON);

    await user.click(confirmButton());

    await waitFor(() => {
      expect(reasonField()).toHaveAccessibleDescription(expect.stringContaining("Escribe un motivo de 3 a 200 caracteres.") as string);
    });
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderModal();

    expect(await axe(container.ownerDocument.body)).toHaveNoViolations();
  });
});
