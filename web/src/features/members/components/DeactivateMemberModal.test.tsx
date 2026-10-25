// S3-F1 · US-076 (front): dar de baja y reactivar con ConfirmModal (DESIGN.md regla 3).
// - Dar de baja: DELETE /members/{id} (solo admin) con la consecuencia "El socio deja de aparecer en
//   la lista; sus membresías, pagos e historial se conservan"; al salir bien invalida ["members"].
// - Reactivar: POST /members/{id}/reactivate; el 409 `member_document_duplicated` no se queda en el
//   modal: lo cierra y entrega `existing_id` a la ficha, que enlaza al socio vivo.
// - Los errores del api se quedan dentro del modal en palabras de la pantalla (409, 403, 404, 429,
//   5xx y 503 `busy`).
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BUSY_MESSAGE } from "../../../core/api/errorCodes";
import { apiError, DETAIL_PATH, DUPLICATE_ID, MEMBER_ID, memberDetailBody, ok } from "../../../test/memberDetail";
import { mockApi, renderWithProviders, type MockHandler, type MockReply } from "../../../test/server";
import { DeactivateMemberModal, ReactivateMemberModal } from "./DeactivateMemberModal";

const MEMBER = { id: MEMBER_ID, name: "Laura Gómez" };

function renderDeactivate(reply: MockHandler = { status: 204 }) {
  const mock = mockApi({ [`DELETE ${DETAIL_PATH}`]: reply });
  const onClose = vi.fn();
  const onDone = vi.fn();
  const view = renderWithProviders(<DeactivateMemberModal open member={MEMBER} onClose={onClose} onDone={onDone} />, { role: "admin" });
  return { mock, onClose, onDone, user: userEvent.setup(), ...view };
}

function renderReactivate(reply: MockReply = ok(memberDetailBody())) {
  const mock = mockApi({ [`POST ${DETAIL_PATH}/reactivate`]: reply });
  const onClose = vi.fn();
  const onDone = vi.fn();
  const onDuplicate = vi.fn();
  const view = renderWithProviders(<ReactivateMemberModal open member={MEMBER} onClose={onClose} onDone={onDone} onDuplicate={onDuplicate} />, { role: "admin" });
  return { mock, onClose, onDone, onDuplicate, user: userEvent.setup(), ...view };
}

const dialog = (): HTMLElement => screen.getByRole("dialog");

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DeactivateMemberModal · dar de baja", () => {
  it("pregunta con el nombre y explica la consecuencia; la acción es 'Dar de baja' en peligro", () => {
    renderDeactivate();

    expect(screen.getByRole("dialog", { name: "¿Dar de baja a Laura Gómez?" })).toHaveAccessibleDescription(
      "El socio deja de aparecer en la lista; sus membresías, pagos e historial se conservan.",
    );
    expect(within(dialog()).getByRole("button", { name: "Volver" })).toBeInTheDocument();
    expect(within(dialog()).getByRole("button", { name: "Dar de baja" })).toBeInTheDocument();
    expect(within(dialog()).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("confirmar hace un solo DELETE aunque se pulse dos veces mientras espera, avisa a la ficha e invalida los socios", async () => {
    let answer: (reply: MockReply) => void = () => undefined;
    const pending = new Promise<MockReply>((resolve) => {
      answer = resolve;
    });
    const { mock, onClose, onDone, queryClient, user } = renderDeactivate(() => pending);
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    await user.dblClick(within(dialog()).getByRole("button", { name: "Dar de baja" }));
    answer({ status: 204 });

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
    expect(mock.callsTo(`DELETE ${DETAIL_PATH}`)).toHaveLength(1);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["members"] });
  });

  it("Volver cierra sin llamar al api", async () => {
    const { mock, onClose, user } = renderDeactivate();

    await user.click(within(dialog()).getByRole("button", { name: "Volver" }));

    expect(onClose).toHaveBeenCalled();
    expect(mock.calls).toHaveLength(0);
  });

  it.each([
    [apiError(409, "member_already_deactivated"), "Otra persona ya dio de baja a este socio. Cierra y recarga la ficha."],
    [apiError(403, "forbidden"), "No tienes permiso para dar de baja socios. Si lo necesitas, pídeselo a un administrador."],
    [apiError(404, "member_not_found"), "Este socio ya no existe. Vuelve a la lista de socios."],
    [apiError(429, "rate_limited", {}, { "Retry-After": "20" }), "Hiciste muchos cambios seguidos. Espera 20 segundos e intenta de nuevo."],
    [apiError(500, "internal_error"), "No pudimos dar de baja al socio. Intenta de nuevo en un momento."],
    [apiError(503, "busy", {}, { "Retry-After": "1" }), BUSY_MESSAGE],
  ])("un error del api se queda en el modal en palabras de la pantalla (%#)", async (reply, message) => {
    const { onDone, user } = renderDeactivate(reply);

    await user.click(within(dialog()).getByRole("button", { name: "Dar de baja" }));

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.queryByText("Mensaje del api.")).not.toBeInTheDocument();
  });
});

describe("ReactivateMemberModal · reactivar", () => {
  it("pregunta con el nombre y explica la consecuencia", () => {
    renderReactivate();

    expect(screen.getByRole("dialog", { name: "¿Reactivar a Laura Gómez?" })).toHaveAccessibleDescription(
      "Vuelve a aparecer en la lista de socios y se puede editar y venderle de nuevo.",
    );
    expect(within(dialog()).getByRole("button", { name: "Reactivar" })).toBeInTheDocument();
  });

  it("confirmar hace POST reactivate, avisa a la ficha e invalida los socios", async () => {
    const { mock, onDone, onClose, queryClient, user } = renderReactivate();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    await user.click(within(dialog()).getByRole("button", { name: "Reactivar" }));

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
    expect(mock.callsTo(`POST ${DETAIL_PATH}/reactivate`)).toHaveLength(1);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["members"] });
  });

  it("409 member_document_duplicated cierra el modal y entrega el id del socio vivo", async () => {
    const { onDuplicate, onDone, onClose, user } = renderReactivate(apiError(409, "member_document_duplicated", { field: "document", existing_id: DUPLICATE_ID }));

    await user.click(within(dialog()).getByRole("button", { name: "Reactivar" }));

    await waitFor(() => {
      expect(onDuplicate).toHaveBeenCalledWith(DUPLICATE_ID);
    });
    expect(onClose).toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
  });

  it.each([
    [apiError(409, "member_not_deactivated"), "Este socio ya estaba activo. Cierra y recarga la ficha."],
    [apiError(403, "forbidden"), "No tienes permiso para reactivar socios. Si lo necesitas, pídeselo a un administrador."],
    [apiError(500, "internal_error"), "No pudimos reactivar al socio. Intenta de nuevo en un momento."],
  ])("un error del api se queda en el modal (%#)", async (reply, message) => {
    const { onDone, user } = renderReactivate(reply);

    await user.click(within(dialog()).getByRole("button", { name: "Reactivar" }));

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
    expect(onDone).not.toHaveBeenCalled();
  });

  it("un 409 de documento sin existing_id se explica en el modal", async () => {
    const { onDuplicate, user } = renderReactivate(apiError(409, "member_document_duplicated", { field: "document" }));

    await user.click(within(dialog()).getByRole("button", { name: "Reactivar" }));

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("No se puede reactivar: otro socio activo ya tiene este documento.");
    expect(onDuplicate).not.toHaveBeenCalled();
  });
});
