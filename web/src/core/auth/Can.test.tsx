// US-040 T6: <Can> y useCan leen el rol del contexto; sin proveedor no hay rol y se niega.
import { render, renderHook, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { Can } from "./Can";
import { RoleProvider, useCan, useRole } from "./useCan";
import type { Role } from "./permissions";

function withRole(role: Role | null) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <RoleProvider value={role}>{children}</RoleProvider>;
  };
}

describe("<Can>", () => {
  it("con coach no renderiza Anular y sí Registrar pago", () => {
    render(
      <RoleProvider value="coach">
        <Can action="payments.void">
          <button type="button">Anular pago</button>
        </Can>
        <Can action="payments.register">
          <button type="button">Registrar pago</button>
        </Can>
      </RoleProvider>,
    );

    expect(screen.queryByRole("button", { name: "Anular pago" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Registrar pago" })).toBeInTheDocument();
  });

  it("con admin renderiza Anular pago", () => {
    render(
      <RoleProvider value="admin">
        <Can action="payments.void">
          <button type="button">Anular pago</button>
        </Can>
      </RoleProvider>,
    );

    expect(screen.getByRole("button", { name: "Anular pago" })).toBeInTheDocument();
  });

  it("sin proveedor (rol nulo) no renderiza nada", () => {
    const { container } = render(
      <Can action="members.view">
        <p>Socios</p>
      </Can>,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("muestra el fallback cuando no hay permiso", () => {
    render(
      <RoleProvider value="member">
        <Can action="members.view" fallback={<p>Sin acceso</p>}>
          <p>Socios</p>
        </Can>
      </RoleProvider>,
    );

    expect(screen.getByText("Sin acceso")).toBeInTheDocument();
    expect(screen.queryByText("Socios")).not.toBeInTheDocument();
  });
});

describe("useCan y useRole", () => {
  it("useCan responde según el rol del proveedor", () => {
    expect(renderHook(() => useCan("members.reveal"), { wrapper: withRole("coach") }).result.current).toBe(true);
    expect(renderHook(() => useCan("payments.void"), { wrapper: withRole("coach") }).result.current).toBe(false);
    expect(renderHook(() => useCan("me.home.view"), { wrapper: withRole("member") }).result.current).toBe(true);
  });

  it("sin proveedor useRole es null y useCan niega", () => {
    expect(renderHook(() => useRole()).result.current).toBeNull();
    expect(renderHook(() => useCan("members.view")).result.current).toBe(false);
  });
});
