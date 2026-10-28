// S3-F5 · US-090 (front): anular una membresía (Membresias.html, "Modal · ¿Anular la membresía de …?").
// - Solo admin (`memberships.cancel`): para el coach no pinta nada; el api vuelve a verificar (403).
// - ConfirmModal con la consecuencia del diseño ("Los pagos asociados no se tocan: si hay que
//   devolver dinero, se anula el pago aparte."), motivo obligatorio de 5 a 500 caracteres tras
//   recortar (D17) y el aviso M-7 bajo el motivo (S3-D50).
// - Un solo POST por doble clic; 409 `membership_already_cancelled` dice que otra persona la anuló;
//   422 `field="reason"` bajo el motivo. La mutación lleva el motivo: `gcTime: 0` y `reset()`
//   (S3-D52).
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError, cancelKey, ELENA_MEMBERSHIP_ID, membershipOut } from "../../../test/memberships";
import { MEMBERS } from "../../../test/members";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { CancelMembershipModal, type CancelTarget } from "./CancelMembershipModal";

const TARGET: CancelTarget = { id: ELENA_MEMBERSHIP_ID, member_name: "Elena Vargas", plan_name: "Mensual" };
const CANCELLED = membershipOut({ id: ELENA_MEMBERSHIP_ID, member_id: MEMBERS.elena.id, member_name: "Elena Vargas", status: "cancelled" });
const REASON = "Se vendió por error al socio equivocado";

function renderCancel(handlers: Record<string, MockHandler> = {}, target: CancelTarget | null = TARGET) {
  const mock = mockApi({ [cancelKey()]: { status: 200, body: CANCELLED }, ...handlers });
  const queryClient = testQueryClient();
  const onClose = vi.fn();
  const onCancelled = vi.fn();
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionRoleProvider>
        <MemoryRouter>
          <main>
            <h1>Membresías</h1>
          </main>
          <CancelMembershipModal membership={target} onClose={onClose} onCancelled={onCancelled} />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, queryClient, onClose, onCancelled, user: userEvent.setup(), ...view };
}

const dialog = () => screen.getByRole("dialog", { name: "¿Anular la membresía de Elena Vargas?" });
const reasonField = () => within(dialog()).getByRole("textbox", { name: /^Motivo/ });
const confirmButton = () => within(dialog()).getByRole("button", { name: "Sí, anular" });
const bodies = (mock: { callsTo: (key: string) => { body: unknown }[] }) => mock.callsTo(cancelKey()).map((c) => c.body);

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("CancelMembershipModal · estructura", () => {
  it("pregunta por la membresía, dice que los pagos no se tocan y pide el motivo con el aviso M-7", () => {
    renderCancel();

    expect(dialog()).toHaveAccessibleDescription(
      "La membresía deja de contar desde hoy. Los pagos asociados no se tocan: si hay que devolver dinero, se anula el pago aparte.",
    );
    expect(reasonField()).toBeRequired();
    expect(reasonField()).toHaveAccessibleDescription(expect.stringContaining("No escribas teléfonos, documentos ni datos de salud.") as string);
    expect(within(dialog()).getByRole("button", { name: "Volver" })).toBeInTheDocument();
    expect(confirmButton()).toBeDisabled();
  });

  it("el coach no la ve (solo admin, `memberships.cancel`)", () => {
    signInAs("coach");
    renderCancel();

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("sin membresía no pinta nada", () => {
    renderCancel({}, null);

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderCancel();

    expect(await axe(container.ownerDocument.body)).toHaveNoViolations();
  });
});

describe("CancelMembershipModal · motivo de 5 a 500", () => {
  it("con menos de 5 caracteres (tras recortar) no deja anular; con 5 sí", async () => {
    const { user } = renderCancel();

    await user.type(reasonField(), "  abcd   ");
    expect(confirmButton()).toBeDisabled();
    await user.type(reasonField(), "e");
    expect(confirmButton()).toBeEnabled();
  });

  it("más de 500 caracteres lo dice bajo el motivo y no deja anular", async () => {
    const { user } = renderCancel();

    await user.click(reasonField());
    await user.paste("a".repeat(501));

    expect(reasonField()).toHaveAccessibleDescription(expect.stringContaining("El motivo admite hasta 500 caracteres.") as string);
    expect(confirmButton()).toBeDisabled();
  });
});

describe("CancelMembershipModal · envío", () => {
  it("envía el motivo recortado y avisa al padre", async () => {
    const { user, mock, onCancelled } = renderCancel();

    await user.type(reasonField(), `  ${REASON}  `);
    await user.click(confirmButton());

    await waitFor(() => {
      expect(onCancelled).toHaveBeenCalledWith(TARGET);
    });
    expect(bodies(mock)).toEqual([{ reason: REASON }]);
  });

  it("un doble clic manda un solo POST", async () => {
    let release: () => void = () => undefined;
    const { user, mock } = renderCancel({
      [cancelKey()]: () =>
        new Promise((resolve) => {
          release = () => {
            resolve({ status: 200, body: CANCELLED });
          };
        }),
    });
    await user.type(reasonField(), REASON);

    await user.dblClick(confirmButton());

    expect(mock.callsTo(cancelKey())).toHaveLength(1);
    release();
  });

  it("tras responder, la caché de mutaciones no conserva el motivo (S3-D52)", async () => {
    const { user, queryClient, onCancelled } = renderCancel();
    await user.type(reasonField(), REASON);

    await user.click(confirmButton());

    await waitFor(() => {
      expect(onCancelled).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
  });
});

describe("CancelMembershipModal · errores del api", () => {
  it("409 membership_already_cancelled dice que otra persona la anuló, sin cerrar", async () => {
    const { user, onCancelled } = renderCancel({ [cancelKey()]: apiError(409, "membership_already_cancelled") });
    await user.type(reasonField(), REASON);

    await user.click(confirmButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("Otra persona ya anuló esta membresía. Actualizamos la lista.");
    expect(onCancelled).not.toHaveBeenCalled();
  });

  it("422 field=reason va bajo el motivo", async () => {
    const { user } = renderCancel({ [cancelKey()]: apiError(422, "validation_error", { field: "reason" }) });
    await user.type(reasonField(), REASON);

    await user.click(confirmButton());

    await waitFor(() => {
      expect(reasonField()).toHaveAccessibleDescription(expect.stringContaining("Escribe un motivo de 5 a 500 caracteres, sin caracteres invisibles.") as string);
    });
  });

  it.each([
    [404, "membership_not_found", {}, "No encontramos esta membresía. Actualiza la lista e intenta de nuevo."],
    [403, "forbidden", {}, "Solo un administrador puede anular membresías."],
    [429, "rate_limited", { "Retry-After": "30" }, "Hiciste muchos cambios seguidos. Espera 30 segundos e intenta de nuevo."],
    [500, "internal_error", {}, "No pudimos anular la membresía. Intenta de nuevo en un momento."],
    [503, "busy", {}, "El sistema está ocupado; intenta de nuevo."],
  ])("%i %s como aviso del modal", async (status, code, headers, message) => {
    const { user } = renderCancel({ [cancelKey()]: apiError(status, code, {}, headers) });
    await user.type(reasonField(), REASON);

    await user.click(confirmButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
  });

  it("tras un error, cerrar deja vacía la caché de mutaciones", async () => {
    const { user, queryClient, onClose } = renderCancel({ [cancelKey()]: apiError(409, "membership_already_cancelled") });
    await user.type(reasonField(), REASON);
    await user.click(confirmButton());
    await within(dialog()).findByRole("alert");

    await user.click(within(dialog()).getByRole("button", { name: "Volver" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
  });
});
