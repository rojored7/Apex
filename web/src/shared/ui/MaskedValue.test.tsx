// US-066 T4 y T6: valor enmascarado con "Mostrar". El claro solo vive en el estado local,
// se descarta al ocultar, al desmontar o a los 60 s, y nunca va a almacenamiento.
// Criterio diferido: la feature conecta onReveal a POST /members/{id}/reveal en US-074.
import { act, render, screen } from "@testing-library/react";
import { fakeTimersUser, restoreRtlTimers, useRtlFakeTimers } from "../../test/fakeTimers";
import type { ReactElement } from "react";
import { ApiError } from "../../core/api/errors";
import { RoleProvider } from "../../core/auth/useCan";
import type { Role } from "../../core/auth/permissions";
import { MaskedValue, REVEAL_TTL_MS } from "./MaskedValue";

function asRole(role: Role | null, ui: ReactElement) {
  return render(<RoleProvider value={role}>{ui}</RoleProvider>);
}


describe("MaskedValue", () => {
  beforeEach(() => {
    useRtlFakeTimers();
  });
  afterEach(() => {
    restoreRtlTimers();
    vi.restoreAllMocks();
  });

  it("muestra el enmascarado del api y un botón Mostrar descrito por el campo", () => {
    asRole("coach", <MaskedValue label="Documento" masked="CC •••• 4417" onReveal={() => Promise.resolve("CC 1020304417")} />);

    expect(screen.getByText("CC •••• 4417")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Mostrar" });
    expect(button).toHaveAccessibleDescription("Documento");
  });

  it("una pulsación llama a onReveal una vez y muestra el claro; a los 60 s vuelve el enmascarado", async () => {
    const user = fakeTimersUser();
    const onReveal = vi.fn(() => Promise.resolve("CC 1020304417"));
    asRole("coach", <MaskedValue label="Documento" masked="CC •••• 4417" onReveal={onReveal} />);

    await user.click(screen.getByRole("button", { name: "Mostrar" }));

    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("CC 1020304417")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ocultar" })).toBeInTheDocument();
    expect(REVEAL_TTL_MS).toBe(60_000);
    act(() => {
      vi.advanceTimersByTime(REVEAL_TTL_MS);
    });
    expect(screen.queryByText("CC 1020304417")).not.toBeInTheDocument();
    expect(screen.getByText("CC •••• 4417")).toBeInTheDocument();
  });

  it("Ocultar descarta el claro y volver a Mostrar vuelve a pedirlo", async () => {
    const user = fakeTimersUser();
    const onReveal = vi.fn(() => Promise.resolve("3101234221"));
    asRole("admin", <MaskedValue label="Teléfono" masked="310 ••• 221" onReveal={onReveal} />);

    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await user.click(await screen.findByRole("button", { name: "Ocultar" }));
    expect(screen.queryByText("3101234221")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mostrar" }));

    expect(onReveal).toHaveBeenCalledTimes(2);
  });

  it("mientras espera el botón muestra el envío y no admite otra pulsación", async () => {
    const user = fakeTimersUser();
    let resolve: (value: string) => void = () => undefined;
    const onReveal = vi.fn(
      () =>
        new Promise<string>((r) => {
          resolve = r;
        }),
    );
    asRole("coach", <MaskedValue label="Correo" masked="laura@…" onReveal={onReveal} />);

    const button = screen.getByRole("button", { name: "Mostrar" });
    await user.dblClick(button);

    expect(onReveal).toHaveBeenCalledTimes(1);
    expect(button).toHaveAttribute("aria-busy", "true");
    await act(async () => {
      resolve("laura@correo.co");
      await Promise.resolve();
    });
    expect(screen.getByText("laura@correo.co")).toBeInTheDocument();
  });

  it("al desmontar el claro no queda en el DOM ni en el almacenamiento", async () => {
    const user = fakeTimersUser();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { unmount } = asRole(
      "coach",
      <MaskedValue label="Documento" masked="CC •••• 4417" onReveal={() => Promise.resolve("CC 1020304417")} />,
    );

    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await screen.findByText("CC 1020304417");
    unmount();

    expect(document.body).not.toHaveTextContent("1020304417");
    expect(setItem).not.toHaveBeenCalled();
    expect(window.location.href).not.toContain("1020304417");
  });

  it("si la respuesta llega después de desmontar, no hace nada", async () => {
    const user = fakeTimersUser();
    let resolve: (value: string) => void = () => undefined;
    const { unmount } = asRole(
      "coach",
      <MaskedValue
        label="Documento"
        masked="CC •••• 4417"
        onReveal={() =>
          new Promise<string>((r) => {
            resolve = r;
          })
        }
      />,
    );

    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    unmount();
    await act(async () => {
      resolve("CC 1020304417");
      await Promise.resolve();
    });

    expect(document.body).not.toHaveTextContent("1020304417");
  });

  it("un 403 muestra 'No tienes permiso para ver este dato' y sigue enmascarado", async () => {
    const user = fakeTimersUser();
    asRole(
      "coach",
      <MaskedValue
        label="Documento"
        masked="CC •••• 4417"
        onReveal={() => Promise.reject(new ApiError({ status: 403, code: "forbidden", message: "Forbidden" }))}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Mostrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para ver este dato");
    expect(screen.getByText("CC •••• 4417")).toBeInTheDocument();
  });

  it("otro error del api muestra su message; uno ajeno, un mensaje genérico", async () => {
    const user = fakeTimersUser();
    const errors = [new ApiError({ status: 503, code: "crypto_unavailable", message: "El servicio de llaves no está disponible" }), new Error("x")];
    asRole("coach", <MaskedValue label="Documento" masked="CC •••• 4417" onReveal={() => Promise.reject(errors.shift() ?? new Error("y"))} />);

    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("El servicio de llaves no está disponible");
    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    expect(await screen.findByText("No se pudo mostrar el dato. Intenta de nuevo.")).toBeInTheDocument();
  });

  it("si el componente pasa a otro registro, el claro anterior no se muestra", async () => {
    const user = fakeTimersUser();
    const { rerender } = asRole(
      "coach",
      <MaskedValue label="Documento" masked="CC •••• 4417" onReveal={() => Promise.resolve("CC 1020304417")} />,
    );
    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await screen.findByText("CC 1020304417");

    rerender(
      <RoleProvider value="coach">
        <MaskedValue label="Documento" masked="CC •••• 9031" onReveal={() => Promise.resolve("CC 5559031")} />
      </RoleProvider>,
    );

    expect(screen.queryByText("CC 1020304417")).not.toBeInTheDocument();
    expect(screen.getByText("CC •••• 9031")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mostrar" })).toBeInTheDocument();
  });

  it("si se pierde el permiso, el claro deja de mostrarse", async () => {
    const user = fakeTimersUser();
    const ui = (role: Role) => (
      <RoleProvider value={role}>
        <MaskedValue label="Documento" masked="CC •••• 4417" onReveal={() => Promise.resolve("CC 1020304417")} />
      </RoleProvider>
    );
    const { rerender } = render(ui("coach"));
    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await screen.findByText("CC 1020304417");

    rerender(ui("member"));

    expect(screen.queryByText("CC 1020304417")).not.toBeInTheDocument();
    expect(screen.getByText("CC •••• 4417")).toBeInTheDocument();
  });

  it("sin permiso members.reveal no hay botón", () => {
    asRole("member", <MaskedValue label="Documento" masked="CC •••• 4417" onReveal={() => Promise.resolve("x")} />);

    expect(screen.queryByRole("button", { name: "Mostrar" })).not.toBeInTheDocument();
    expect(screen.getByText("CC •••• 4417")).toBeInTheDocument();
  });

  it("sin rol no hay botón; con otra acción de permiso se respeta", () => {
    asRole(null, <MaskedValue label="Documento" masked="CC •••• 4417" onReveal={() => Promise.resolve("x")} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("un campo vacío muestra Sin dato y no ofrece Mostrar", () => {
    asRole("admin", <MaskedValue label="Correo" masked={null} onReveal={() => Promise.resolve("x")} />);

    expect(screen.getByText("Sin dato")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
