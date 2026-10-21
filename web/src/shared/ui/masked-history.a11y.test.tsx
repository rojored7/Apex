// US-066 T8: axe sobre MaskedValue y HistoryAside en sus estados.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { axe } from "vitest-axe";
import { ApiError } from "../../core/api/errors";
import { RoleProvider } from "../../core/auth/useCan";
import { HistoryAside } from "./HistoryAside";
import { MaskedValue } from "./MaskedValue";

function inPage(ui: ReactElement) {
  return render(
    <RoleProvider value="admin">
      <main>{ui}</main>
    </RoleProvider>,
  );
}

describe("accesibilidad de valor enmascarado e historial", () => {
  it("MaskedValue enmascarado, en claro y con error", async () => {
    const user = userEvent.setup();
    let fail = false;
    const { container } = inPage(
      <MaskedValue
        label="Documento"
        masked="CC •••• 4417"
        onReveal={() =>
          fail ? Promise.reject(new ApiError({ status: 403, code: "forbidden", message: "x" })) : Promise.resolve("CC 1020304417")
        }
      />,
    );
    expect(await axe(container)).toHaveNoViolations();

    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await screen.findByText("CC 1020304417");
    expect(await axe(container)).toHaveNoViolations();

    fail = true;
    await user.click(screen.getByRole("button", { name: "Ocultar" }));
    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await screen.findByRole("alert");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("MaskedValue sin dato", async () => {
    const { container } = inPage(<MaskedValue label="Correo" masked={null} onReveal={() => Promise.resolve("")} />);

    expect(await axe(container)).toHaveNoViolations();
  });

  it.each([
    ["con entradas", { entries: [{ id: "1", at: "2026-10-20T15:00:00Z", actor_id: "u", actor_name: "Ana", entity: "members", action: "update", before: { first_name: "a" }, after: { first_name: "b" } }], total: 5 }],
    ["vacío", { entries: [], total: 0 }],
    ["cargando", { entries: [], total: 0, isLoading: true }],
    ["con error", { entries: [], total: 0, error: new Error("x"), onRetry: () => undefined }],
  ])("HistoryAside %s", async (_estado, props) => {
    const { container } = inPage(<HistoryAside onLoadMore={() => undefined} {...props} />);

    expect(await axe(container)).toHaveNoViolations();
  });
});
