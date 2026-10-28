// S3-F5 · US-089 (front): congelar una membresía (Membresias.html, "Modal · Congelar membresía de …").
// - Dos fechas ("Desde", hoy en Bogotá por defecto, y "Hasta") y la vista previa en vivo
//   "Son N días; la membresía terminará el …" (freezePreview, RN-07). Sin campo Motivo: FreezeIn no
//   lo tiene (D14, DESIGN-GAP).
// - Fechas vacías o invertidas no se envían. Un solo POST por doble clic.
// - 409 de límites y de estado como aviso del modal, en palabras de la pantalla; el de días
//   (`freeze_days_exceeded`) dice los días disponibles tomados del mensaje del api (S3-B2). 422 con
//   `field` bajo su fecha y con foco.
// - La mutación lleva fechas: `gcTime: 0` y `reset()` (S3-D52): al terminar, o al cerrar tras un
//   error, la caché de mutaciones queda vacía.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError, ELENA_MEMBERSHIP_ID, freezeKey, membershipOut, SELL_NOW } from "../../../test/memberships";
import { MEMBERS } from "../../../test/members";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { FreezeModal, type FreezeTarget } from "./FreezeModal";

const TARGET: FreezeTarget = { id: ELENA_MEMBERSHIP_ID, member_name: "Elena Vargas", plan_name: "Mensual", end_date: "2026-10-31" };
const FROZEN = membershipOut({ id: ELENA_MEMBERSHIP_ID, member_id: MEMBERS.elena.id, member_name: "Elena Vargas", status: "frozen", end_date: "2026-11-10" });

function renderFreeze(handlers: Record<string, MockHandler> = {}, target: FreezeTarget | null = TARGET) {
  const mock = mockApi({ [freezeKey()]: { status: 200, body: FROZEN }, ...handlers });
  const queryClient = testQueryClient();
  const onClose = vi.fn();
  const onFrozen = vi.fn();
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionRoleProvider>
        <MemoryRouter>
          <main>
            <h1>Membresías</h1>
          </main>
          <FreezeModal membership={target} onClose={onClose} onFrozen={onFrozen} />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, queryClient, onClose, onFrozen, user: userEvent.setup(), ...view };
}

const dialog = () => screen.getByRole("dialog", { name: "Congelar la membresía de Elena Vargas" });
const fromField = () => within(dialog()).getByLabelText(/^Desde/);
const toField = () => within(dialog()).getByLabelText(/^Hasta/);
const freezeButton = () => within(dialog()).getByRole("button", { name: /^Congela/ });
const setDate = (input: HTMLElement, value: string) => {
  fireEvent.change(input, { target: { value } });
};
const bodies = (mock: { callsTo: (key: string) => { body: unknown }[] }) => mock.callsTo(freezeKey()).map((c) => c.body);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: SELL_NOW });
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("FreezeModal · estructura (Membresias.html)", () => {
  it("pregunta por la membresía del socio, con Desde (hoy), Hasta, la nota de Configuración, Volver y Congelar", () => {
    renderFreeze();

    expect(dialog()).toBeInTheDocument();
    expect(fromField()).toHaveValue("2026-10-28");
    expect(fromField()).toBeRequired();
    expect(toField()).toHaveValue("");
    expect(toField()).toBeRequired();
    expect(within(dialog()).getByText("La fecha de fin se corre los mismos días. Máximo de días congelados por membresía: lo define Configuración.")).toBeInTheDocument();
    expect(within(dialog()).getByRole("button", { name: "Volver" })).toBeInTheDocument();
    expect(freezeButton()).toHaveTextContent("Congelar");
  });

  it("no tiene campo Motivo: FreezeIn no lo recibe (D14, DESIGN-GAP)", () => {
    renderFreeze();

    expect(within(dialog()).queryByLabelText(/Motivo/)).toBeNull();
    expect(within(dialog()).queryByRole("textbox")).toBeNull();
  });

  it("sin membresía no pinta nada", () => {
    renderFreeze({}, null);

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("un socio sin `memberships.freeze` no ve el modal", () => {
    signInAs("member");
    renderFreeze();

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("no tiene violaciones de axe con la vista previa a la vista", async () => {
    vi.useRealTimers();
    const { container } = renderFreeze();
    setDate(toField(), "2026-11-06");

    expect(await axe(container.ownerDocument.body)).toHaveNoViolations();
  });
});

describe("FreezeModal · vista previa y validación", () => {
  it("con las dos fechas dice los días y el nuevo fin: 'Son 10 días; la membresía terminará el 10 nov 2026'", () => {
    renderFreeze();

    setDate(toField(), "2026-11-06");

    expect(within(dialog()).getByText("Son 10 días; la membresía terminará el 10 nov 2026")).toBeInTheDocument();
  });

  it("al cambiar Desde la vista previa se recalcula", () => {
    renderFreeze();
    setDate(toField(), "2026-11-06");

    setDate(fromField(), "2026-11-02");

    expect(within(dialog()).getByText("Son 5 días; la membresía terminará el 5 nov 2026")).toBeInTheDocument();
  });

  it("fechas invertidas: sin vista previa, error bajo Hasta y ningún envío", async () => {
    const { user, mock } = renderFreeze();
    setDate(toField(), "2026-10-20");

    expect(within(dialog()).queryByText(/^Son \d+ días/)).toBeNull();
    await user.click(freezeButton());

    expect(await within(dialog()).findByText("La fecha final no puede ser anterior a la inicial.")).toBeInTheDocument();
    expect(toField()).toHaveAttribute("aria-invalid", "true");
    expect(bodies(mock)).toHaveLength(0);
  });

  it("sin fechas pide las dos y no envía", async () => {
    const { user, mock } = renderFreeze();
    setDate(fromField(), "");

    await user.click(freezeButton());

    expect(await within(dialog()).findByText("Escribe desde qué fecha se congela.")).toBeInTheDocument();
    expect(within(dialog()).getByText("Escribe hasta qué fecha se congela.")).toBeInTheDocument();
    expect(bodies(mock)).toHaveLength(0);
  });
});

describe("FreezeModal · envío", () => {
  it("envía { frozen_from, frozen_to } y avisa el nuevo fin al padre", async () => {
    const { user, mock, onFrozen } = renderFreeze();
    setDate(toField(), "2026-11-06");

    await user.click(freezeButton());

    await waitFor(() => {
      expect(onFrozen).toHaveBeenCalledWith(TARGET, "2026-11-10");
    });
    expect(bodies(mock)).toEqual([{ frozen_from: "2026-10-28", frozen_to: "2026-11-06" }]);
  });

  it("un doble clic manda un solo POST y el botón dice 'Congelando…' mientras tanto", async () => {
    let release: () => void = () => undefined;
    const { user, mock } = renderFreeze({
      [freezeKey()]: () =>
        new Promise((resolve) => {
          release = () => {
            resolve({ status: 200, body: FROZEN });
          };
        }),
    });
    setDate(toField(), "2026-11-06");

    await user.dblClick(freezeButton());

    await waitFor(() => {
      expect(freezeButton()).toHaveTextContent("Congelando…");
    });
    expect(mock.callsTo(freezeKey())).toHaveLength(1);
    release();
  });

  it("tras responder, la caché de mutaciones no conserva las fechas (S3-D52)", async () => {
    const { user, queryClient, onFrozen } = renderFreeze();
    setDate(toField(), "2026-11-06");

    await user.click(freezeButton());

    await waitFor(() => {
      expect(onFrozen).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
  });
});

describe("FreezeModal · errores del api", () => {
  it.each([
    ["membership_not_freezable", "Esta membresía ya no se puede congelar: solo se congelan las membresías al día o por vencer."],
    ["freeze_already_scheduled", "Esta membresía ya tiene una congelación en curso o programada. Congélala de nuevo cuando esa termine."],
    ["freeze_limit_reached", "Esta membresía ya usó todas las congelaciones que permite el gimnasio."],
    ["overlaps_future_membership", "Con esta congelación la membresía se cruzaría con la siguiente del socio. Elige menos días."],
  ])("409 %s se explica en el modal sin cerrarlo", async (code, message) => {
    const { user, onFrozen } = renderFreeze({ [freezeKey()]: apiError(409, code) });
    setDate(toField(), "2026-11-06");

    await user.click(freezeButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
    expect(onFrozen).not.toHaveBeenCalled();
  });

  it("409 freeze_days_exceeded dice los días disponibles que trae el mensaje del api", async () => {
    const { user } = renderFreeze({ [freezeKey()]: apiError(409, "freeze_days_exceeded", { message: "Quedan 5 días de congelación para esta membresía." }) });
    setDate(toField(), "2026-11-06");

    await user.click(freezeButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("Quedan 5 días de congelación para esta membresía. Elige un rango más corto.");
  });

  it.each([
    ["Quedan 1 días de congelación para esta membresía.", "Queda 1 día de congelación para esta membresía. Elige un rango más corto."],
    ["Quedan 0 días de congelación para esta membresía.", "Esta membresía ya no tiene días de congelación disponibles."],
    ["Mensaje del api.", "El rango supera los días de congelación que le quedan a esta membresía. Elige un rango más corto."],
  ])("409 freeze_days_exceeded con %j", async (apiMessage, message) => {
    const { user } = renderFreeze({ [freezeKey()]: apiError(409, "freeze_days_exceeded", { message: apiMessage }) });
    setDate(toField(), "2026-11-06");

    await user.click(freezeButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
  });

  it.each([
    ["freeze_too_retroactive", "frozen_from", /^Desde/, "La congelación no puede empezar tan atrás. Elige una fecha más reciente."],
    ["freeze_outside_validity", "frozen_from", /^Desde/, "La congelación tiene que empezar dentro de la vigencia de la membresía."],
    ["validation_error", "frozen_to", /^Hasta/, "La fecha final no puede ser anterior a la inicial."],
    ["validation_error", "frozen_from", /^Desde/, "Escribe una fecha de inicio válida."],
  ])("422 %s en %s va bajo su fecha, con foco", async (code, field, label, message) => {
    const { user } = renderFreeze({ [freezeKey()]: apiError(422, code, { field }) });
    setDate(toField(), "2026-11-06");

    await user.click(freezeButton());

    const input = within(dialog()).getByLabelText(label);
    await waitFor(() => {
      expect(input).toHaveAccessibleDescription(expect.stringContaining(message) as string);
    });
    expect(input).toHaveFocus();
  });

  it.each([
    [422, "member_inactive", {}, "Este socio no está activo. Reactívalo antes de congelar su membresía."],
    [404, "membership_not_found", {}, "No encontramos esta membresía. Actualiza la lista e intenta de nuevo."],
    [403, "forbidden", {}, "No tienes permiso para congelar membresías. Si lo necesitas, pídeselo a un administrador."],
    [500, "internal_error", {}, "No pudimos congelar la membresía. Intenta de nuevo en un momento."],
    [503, "busy", {}, "El sistema está ocupado; intenta de nuevo."],
  ])("%i %s como aviso del modal", async (status, code, extra, message) => {
    const { user } = renderFreeze({ [freezeKey()]: apiError(status, code, extra) });
    setDate(toField(), "2026-11-06");

    await user.click(freezeButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
  });

  it("429 dice cuánto esperar", async () => {
    const { user } = renderFreeze({ [freezeKey()]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) });
    setDate(toField(), "2026-11-06");

    await user.click(freezeButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("Hiciste muchos cambios seguidos. Espera 30 segundos e intenta de nuevo.");
  });

  it("sin red lo dice con el mensaje común", async () => {
    const { user } = renderFreeze({ [freezeKey()]: () => Promise.reject(new TypeError("Failed to fetch")) });
    setDate(toField(), "2026-11-06");

    await user.click(freezeButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("No pudimos conectar con el servidor. Intenta de nuevo.");
  });
});

describe("FreezeModal · cerrar", () => {
  it("Volver cierra sin enviar", async () => {
    const { user, mock, onClose } = renderFreeze();

    await user.click(within(dialog()).getByRole("button", { name: "Volver" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(bodies(mock)).toHaveLength(0);
  });

  it("Escape cierra, pero no mientras se congela", async () => {
    let release: () => void = () => undefined;
    const { user, onClose } = renderFreeze({
      [freezeKey()]: () =>
        new Promise((resolve) => {
          release = () => {
            resolve({ status: 200, body: FROZEN });
          };
        }),
    });
    setDate(toField(), "2026-11-06");
    await user.click(freezeButton());
    await waitFor(() => {
      expect(freezeButton()).toHaveTextContent("Congelando…");
    });

    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
    release();
    await waitFor(() => {
      expect(screen.queryByText("Congelando…")).toBeNull();
    });
  });

  it("tras un error, cerrar deja vacía la caché de mutaciones (reset al cerrar)", async () => {
    const { user, queryClient, onClose } = renderFreeze({ [freezeKey()]: apiError(409, "freeze_limit_reached") });
    setDate(toField(), "2026-11-06");
    await user.click(freezeButton());
    await within(dialog()).findByRole("alert");

    await user.click(within(dialog()).getByRole("button", { name: "Volver" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
  });
});

describe("FreezeModal · revisión S3-F5", () => {
  it("M3: el aviso de un intento anterior se quita al corregir una fecha", async () => {
    const { user } = renderFreeze({ [freezeKey()]: apiError(409, "freeze_days_exceeded", { message: "Quedan 5 días de congelación para esta membresía." }) });
    setDate(toField(), "2026-11-06");
    await user.click(freezeButton());
    await within(dialog()).findByRole("alert");

    setDate(toField(), "2026-10-30");

    expect(within(dialog()).queryByRole("alert")).toBeNull();
  });

  it("L6: un 422 en frozen_to con otro código no dice que las fechas están invertidas", async () => {
    const { user } = renderFreeze({ [freezeKey()]: apiError(422, "too_long", { field: "frozen_to" }) });
    setDate(toField(), "2026-11-06");

    await user.click(freezeButton());

    await waitFor(() => {
      expect(toField()).toHaveAccessibleDescription(expect.stringContaining("Escribe una fecha final válida.") as string);
    });
  });
});
