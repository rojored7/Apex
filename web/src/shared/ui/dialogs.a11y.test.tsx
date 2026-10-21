// US-065 T6: axe sobre SidePanel y ConfirmModal abiertos, con y sin error.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { ApiError } from "../../core/api/errors";
import { Button } from "./Button";
import { ConfirmModal } from "./ConfirmModal";
import { SidePanel } from "./SidePanel";

describe("accesibilidad de paneles y modales", () => {
  it("SidePanel abierto", async () => {
    render(
      <SidePanel open title="Nuevo movimiento" onClose={() => undefined} footer={<Button>Guardar</Button>}>
        <label htmlFor="n">Nombre</label>
        <input id="n" />
      </SidePanel>,
    );

    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("SidePanel con la confirmación de descartar abierta", async () => {
    render(
      <SidePanel open isDirty title="Nuevo movimiento" onClose={() => undefined}>
        <p>Formulario</p>
      </SidePanel>,
    );

    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { name: "¿Descartar los cambios?" })).toBeInTheDocument();
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("ConfirmModal con motivo y texto de confirmación", async () => {
    render(
      <ConfirmModal
        open
        title="¿Rotar la llave?"
        consequence="Se crea una versión nueva."
        confirmLabel="Rotar llave"
        reasonRequired
        confirmText="ROTAR"
        onConfirm={() => undefined}
        onClose={() => undefined}
      />,
    );

    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("ConfirmModal con error del api en el motivo y error general", async () => {
    const user = userEvent.setup();
    let calls = 0;
    render(
      <ConfirmModal
        open
        title="¿Anular este pago?"
        consequence="No se puede deshacer."
        confirmLabel="Anular pago"
        reasonRequired
        onConfirm={() => {
          calls += 1;
          return Promise.reject(
            calls === 1
              ? new ApiError({ status: 422, code: "v", message: "Motivo inválido", field: "reason" })
              : new ApiError({ status: 500, code: "i", message: "Error interno" }),
          );
        }}
        onClose={() => undefined}
      />,
    );

    await user.type(screen.getByRole("textbox", { name: /Motivo/ }), "Pago duplicado");
    await user.click(screen.getByRole("button", { name: "Anular pago" }));
    await screen.findByText("Motivo inválido");
    expect(await axe(document.body)).toHaveNoViolations();

    await user.click(screen.getByRole("button", { name: "Anular pago" }));
    await screen.findByRole("alert");
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
