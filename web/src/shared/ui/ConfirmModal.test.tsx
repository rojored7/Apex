// US-065 T3 y T5: modal de confirmación con motivo, texto tecleado, envío único y errores del api.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ApiError } from "../../core/api/errors";
import { ConfirmModal, type ConfirmModalProps } from "./ConfirmModal";

type Partial = Omit<ConfirmModalProps, "open" | "onClose">;

function Harness(props: Partial & { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  const { onClose, ...rest } = props;
  return (
    <>
      <button type="button" onClick={() => { setOpen(true); }}>
        Abrir
      </button>
      <ConfirmModal
        {...rest}
        open={open}
        onClose={() => {
          onClose?.();
          setOpen(false);
        }}
      />
    </>
  );
}

const voidPayment: Partial = {
  title: "¿Anular este pago?",
  consequence: "El pago queda anulado y no cuenta en los ingresos. No se puede deshacer.",
  confirmLabel: "Anular pago",
  reasonRequired: true,
  onConfirm: () => Promise.resolve(),
};

async function open(props: Partial & { onClose?: () => void }) {
  const user = userEvent.setup();
  render(<Harness {...props} />);
  await user.click(screen.getByRole("button", { name: "Abrir" }));
  return user;
}

describe("ConfirmModal", () => {
  it("es un diálogo modal con la pregunta como título y la consecuencia como descripción", async () => {
    await open(voidPayment);

    const dialog = screen.getByRole("dialog", { name: "¿Anular este pago?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleDescription(voidPayment.consequence);
    expect(screen.getByRole("button", { name: "Volver" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anular pago" })).toHaveClass("danger");
  });

  it("con motivo, el foco empieza en el motivo", async () => {
    await open(voidPayment);

    expect(screen.getByRole("textbox", { name: /Motivo/ })).toHaveFocus();
  });

  it("envía el motivo tal cual y cierra si sale bien", async () => {
    const onConfirm = vi.fn(() => Promise.resolve());
    const onClose = vi.fn();
    const user = await open({ ...voidPayment, onConfirm, onClose });

    await user.type(screen.getByRole("textbox", { name: /Motivo/ }), "Pago duplicado");
    await user.click(screen.getByRole("button", { name: "Anular pago" }));

    expect(onConfirm).toHaveBeenCalledWith("Pago duplicado");
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("solo espacios o menos de 3 caracteres deshabilitan el botón", async () => {
    const user = await open(voidPayment);
    const confirm = screen.getByRole("button", { name: "Anular pago" });
    const reason = screen.getByRole("textbox", { name: /Motivo/ });

    expect(confirm).toBeDisabled();
    await user.type(reason, "   ");
    expect(confirm).toBeDisabled();
    await user.clear(reason);
    await user.type(reason, "ab");
    expect(confirm).toBeDisabled();
    await user.type(reason, "c");
    expect(confirm).toBeEnabled();
  });

  it("respeta un mínimo distinto", async () => {
    const user = await open({ ...voidPayment, minReasonLength: 10 });

    await user.type(screen.getByRole("textbox", { name: /Motivo/ }), "corto");

    expect(screen.getByRole("button", { name: "Anular pago" })).toBeDisabled();
  });

  it("con confirmText exige el texto exacto", async () => {
    const onConfirm = vi.fn(() => Promise.resolve());
    const user = await open({
      title: "¿Rotar la llave de member.document?",
      consequence: "Se crea la versión v3 y el worker recifra en segundo plano.",
      confirmLabel: "Rotar llave",
      confirmText: "ROTAR",
      onConfirm,
    });
    const confirm = screen.getByRole("button", { name: "Rotar llave" });
    const typed = screen.getByRole("textbox", { name: "Escribe ROTAR para confirmar" });

    await user.type(typed, "rotar");
    expect(confirm).toBeDisabled();
    await user.clear(typed);
    await user.type(typed, "ROTAR");
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    expect(onConfirm).toHaveBeenCalledWith(undefined);
  });

  it("con motivo opcional permite confirmar vacío y envía undefined", async () => {
    const onConfirm = vi.fn(() => Promise.resolve());
    const user = await open({
      title: "¿Omitir este aviso?",
      consequence: "No se envía hoy.",
      confirmLabel: "Omitir aviso",
      tone: "primary",
      showReason: true,
      onConfirm,
    });

    expect(screen.getByRole("button", { name: "Omitir aviso" })).toHaveClass("primary");
    await user.click(screen.getByRole("button", { name: "Omitir aviso" }));

    expect(onConfirm).toHaveBeenCalledWith(undefined);
  });

  it("doble clic con la petición pendiente produce una sola llamada y marca el envío", async () => {
    let resolve: () => void = () => undefined;
    const onConfirm = vi.fn(
      () =>
        new Promise<void>((r) => {
          resolve = r;
        }),
    );
    const user = await open({ ...voidPayment, onConfirm });
    await user.type(screen.getByRole("textbox", { name: /Motivo/ }), "Pago duplicado");
    const confirm = screen.getByRole("button", { name: "Anular pago" });

    await user.dblClick(confirm);

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(confirm).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true");
    resolve();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("422 con field reason muestra el error bajo el motivo y sigue abierto", async () => {
    const onConfirm = vi.fn(() =>
      Promise.reject(new ApiError({ status: 422, code: "validation_error", message: "El motivo es muy corto", field: "reason" })),
    );
    const user = await open({ ...voidPayment, onConfirm });
    const reason = screen.getByRole("textbox", { name: /Motivo/ });

    await user.type(reason, "abc");
    await user.click(screen.getByRole("button", { name: "Anular pago" }));

    expect(await screen.findByText("El motivo es muy corto")).toBeInTheDocument();
    expect(reason).toHaveAttribute("aria-invalid", "true");
    expect(reason).toHaveAccessibleDescription("El motivo es muy corto");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anular pago" })).toBeEnabled();
  });

  it("500 muestra el message del api y el modal sigue abierto", async () => {
    const onConfirm = vi.fn(() => Promise.reject(new ApiError({ status: 500, code: "internal_error", message: "Error interno" })));
    const user = await open({ ...voidPayment, onConfirm });

    await user.type(screen.getByRole("textbox", { name: /Motivo/ }), "Pago duplicado");
    await user.click(screen.getByRole("button", { name: "Anular pago" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Error interno");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("un error que no es del api muestra un mensaje genérico en español", async () => {
    const onConfirm = vi.fn(() => Promise.reject(new Error("boom")));
    const user = await open({ ...voidPayment, onConfirm });

    await user.type(screen.getByRole("textbox", { name: /Motivo/ }), "Pago duplicado");
    await user.click(screen.getByRole("button", { name: "Anular pago" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo completar la acción. Intenta de nuevo.");
  });

  it("el error se muestra como texto, nunca como HTML", async () => {
    const onConfirm = vi.fn(() =>
      Promise.reject(new ApiError({ status: 400, code: "x", message: "<img src=x onerror=alert(1)>" })),
    );
    const user = await open({ ...voidPayment, onConfirm });

    await user.type(screen.getByRole("textbox", { name: /Motivo/ }), "Pago duplicado");
    await user.click(screen.getByRole("button", { name: "Anular pago" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("<img src=x onerror=alert(1)>");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("Volver y Escape cierran sin confirmar y devuelven el foco", async () => {
    const onConfirm = vi.fn(() => Promise.resolve());
    const onClose = vi.fn();
    const user = await open({ ...voidPayment, onConfirm, onClose });

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Abrir" })).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Abrir" }));
    await user.click(screen.getByRole("button", { name: "Volver" }));
    expect(onClose).toHaveBeenCalledTimes(2);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("al reabrir empieza limpio", async () => {
    const user = await open(voidPayment);

    await user.type(screen.getByRole("textbox", { name: /Motivo/ }), "algo");
    await user.click(screen.getByRole("button", { name: "Volver" }));
    await user.click(screen.getByRole("button", { name: "Abrir" }));

    expect(screen.getByRole("textbox", { name: /Motivo/ })).toHaveValue("");
  });

  it("sin motivo ni texto, el foco empieza en Volver", async () => {
    await open({ title: "¿Dar de baja a Laura?", consequence: "Deja de aparecer en las listas.", confirmLabel: "Dar de baja", onConfirm: () => undefined });

    expect(screen.getByRole("button", { name: "Volver" })).toHaveFocus();
  });
});

describe("ConfirmModal · ayuda y tope del motivo (S3-F4, M-7, D17)", () => {
  it("reasonHint queda como descripción del motivo", async () => {
    await open({ ...voidPayment, reasonHint: "No escribas teléfonos, documentos ni datos de salud." });

    expect(screen.getByRole("textbox", { name: /Motivo/ })).toHaveAccessibleDescription("No escribas teléfonos, documentos ni datos de salud.");
  });

  it("maxReasonLength cuenta caracteres tras recortar: al pasarse lo explica y deshabilita la acción", async () => {
    const onConfirm = vi.fn(() => Promise.resolve());
    const user = await open({ ...voidPayment, minReasonLength: 1, maxReasonLength: 5, onConfirm });
    const reason = screen.getByRole("textbox", { name: /Motivo/ });

    await user.type(reason, "  hola  ");
    expect(screen.getByRole("button", { name: "Anular pago" })).toBeEnabled();
    await user.type(reason, "123");

    expect(screen.getByText("El motivo admite hasta 5 caracteres.")).toBeInTheDocument();
    expect(reason).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Anular pago" })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
