// S6-F2 · US-145 (S6-R1, S6-D121, S6-D122): «Rotar» una llave de cifrado. ConfirmModal con la clase, los
// registros, el motivo (1 a 200 caracteres, el límite del contrato) y «Escribe ROTAR» exacto; confirmar
// queda deshabilitado hasta entonces. 202 → salto a Trabajos; 409 y 422 con el mensaje del api; 503 con
// el aviso del custodio; 429 con la espera. Nada del cuerpo queda en la caché de mutaciones.
import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import type { MockReply } from "../../../test/server";
import { KEY_PHONE, apiError, cryptoKey, renderKeys, rotationStarted } from "../../../test/keys";
import { RotateKeyModal } from "./RotateKeyModal";

const PHONE = cryptoKey({ id: KEY_PHONE, data_class: "member.phone", version: 1, rotated_at: null, records_count: 342 });
const ROTATE = `POST /crypto/keys/${KEY_PHONE}/rotate`;

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderModal(target = PHONE, handlers: Parameters<typeof renderKeys>[2] = {}) {
  const onClose = vi.fn();
  const view = renderKeys(<RotateKeyModal target={target} onClose={onClose} />, "/sistema/llaves", handlers);
  return { onClose, ...view };
}

const dialog = () => screen.getByRole("dialog", { name: "¿Rotar la llave de member.phone?" });
const confirm = () => within(dialog()).getByRole("button", { name: "Rotar llave" });

async function fill(user: ReturnType<typeof renderKeys>["user"], reason = "Rotación programada", typed = "ROTAR") {
  await user.type(within(dialog()).getByLabelText(/^Motivo/), reason);
  await user.type(within(dialog()).getByRole("textbox", { name: "Escribe ROTAR para confirmar" }), typed);
}

describe("RotateKeyModal · contenido", () => {
  it("dice la clase, cuántos registros se recifran y qué pasa con la versión actual", () => {
    renderModal();

    expect(dialog()).toBeInTheDocument();
    expect(screen.getByText(/Se crea la versión v2 y el worker recifra en segundo plano los 342 registros/)).toBeInTheDocument();
    expect(screen.getByText(/v1 queda en «solo descifrar»/)).toBeInTheDocument();
    expect(screen.getByText(/No hay corte de servicio/)).toBeInTheDocument();
  });

  it("sin records_count dice «los registros», sin inventar un número", () => {
    renderModal(cryptoKey({ id: KEY_PHONE, data_class: "member.phone", records_count: null }));

    expect(screen.getByText(/recifra en segundo plano los registros/)).toBeInTheDocument();
  });

  it("sin llave elegida no hay diálogo", () => {
    renderKeys(<RotateKeyModal target={null} onClose={vi.fn()} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad", async () => {
    renderModal();

    expect(await axe(document.body)).toHaveNoViolations();
  });
});

describe("RotateKeyModal · ROTAR exacto y motivo", () => {
  it("confirmar está deshabilitado hasta escribir ROTAR exacto (ni «rotar» ni con espacios)", async () => {
    const { user } = renderModal();
    await user.type(within(dialog()).getByLabelText(/^Motivo/), "Rotación programada");
    const typed = within(dialog()).getByRole("textbox", { name: "Escribe ROTAR para confirmar" });

    expect(confirm()).toBeDisabled();
    await user.type(typed, "rotar");
    expect(confirm()).toBeDisabled();
    await user.clear(typed);
    await user.type(typed, "ROTAR ");
    expect(confirm()).toBeDisabled();
    await user.clear(typed);
    await user.type(typed, "ROTAR");
    expect(confirm()).toBeEnabled();
  });

  it("el motivo es obligatorio", async () => {
    const { user } = renderModal();
    await user.type(within(dialog()).getByRole("textbox", { name: "Escribe ROTAR para confirmar" }), "ROTAR");

    expect(confirm()).toBeDisabled();
  });

  it("el motivo admite hasta 200 caracteres (el límite del contrato) y lo dice", async () => {
    const { user } = renderModal();
    const reason = within(dialog()).getByLabelText(/^Motivo/);
    await user.click(reason);
    await user.paste("a".repeat(201));
    await user.type(within(dialog()).getByRole("textbox", { name: "Escribe ROTAR para confirmar" }), "ROTAR");

    expect(screen.getByText("El motivo admite hasta 200 caracteres.")).toBeInTheDocument();
    expect(confirm()).toBeDisabled();
  });

  it("avisa que el motivo no lleva correos, teléfonos ni documentos", () => {
    renderModal();

    expect(within(dialog()).getByText(/No escribas correos, teléfonos ni documentos/)).toBeInTheDocument();
  });
});

describe("RotateKeyModal · rotar", () => {
  it("POST con el motivo recortado y confirm ROTAR; al 202 salta a Trabajos y cierra", async () => {
    const { user, mock, router, onClose } = renderModal(PHONE, { handlers: { [ROTATE]: rotationStarted() } });
    await fill(user, "  Rotación programada  ");

    await user.click(confirm());

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
    expect(mock.callsTo(ROTATE)).toHaveLength(1);
    expect(mock.callsTo(ROTATE)[0]?.body).toEqual({ reason: "Rotación programada", confirm: "ROTAR" });
    expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("trabajos");
  });

  it("invalida toda la caché de [\"crypto\"] (llaves, resumen y trabajos) tras el 202", async () => {
    const { user, queryClient } = renderModal(PHONE, { handlers: { [ROTATE]: rotationStarted() } });
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    await fill(user);

    await user.click(confirm());

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith({ queryKey: ["crypto"] });
    });
  });

  it("no deja el motivo ni el texto de confirmación en la caché de mutaciones", async () => {
    const { user, queryClient } = renderModal(PHONE, { handlers: { [ROTATE]: rotationStarted() } });
    await fill(user, "Motivo secreto de prueba");

    await user.click(confirm());

    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(JSON.stringify(queryClient.getQueryCache().getAll().map((q) => q.state.data))).not.toContain("Motivo secreto de prueba");
  });

  it("409 muestra el mensaje del api dentro del modal y no cierra", async () => {
    const message = "Ya hay una rotación en curso para esta clase. Espera a que termine.";
    const { user, onClose } = renderModal(PHONE, { handlers: { [ROTATE]: apiError(409, "rotation_running", message) } });
    await fill(user);

    await user.click(confirm());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("422 sobre el motivo se muestra bajo el campo con el mensaje del api", async () => {
    const message = "El motivo no puede llevar correos ni números largos.";
    const { user } = renderModal(PHONE, { handlers: { [ROTATE]: apiError(422, "validation_error", message, { field: "reason" }) } });
    await fill(user, "escribe a ana@correo.com");

    await user.click(confirm());

    expect(await within(dialog()).findByText(message)).toBeInTheDocument();
  });

  it("503 crypto_unavailable muestra el texto del api (el CustodyNotice global explica el sellado)", async () => {
    const message = "El custodio de llaves está sellado. Intenta de nuevo cuando se desselle.";
    const { user } = renderModal(PHONE, { handlers: { [ROTATE]: apiError(503, "crypto_unavailable", message) } });
    await fill(user);

    await user.click(confirm());

    const alert = await within(dialog()).findByRole("alert");
    expect(alert).toHaveTextContent(message);
  });

  it("una respuesta 202 con material de llave (campo extra) es inválida: error en el modal y el texto no llega al DOM", async () => {
    const leaking: MockReply = { status: 202, body: { ...(rotationStarted().body as object), wrapped_material: "vault:v1:SECRETO" } };
    const { user, onClose } = renderModal(PHONE, { handlers: { [ROTATE]: leaking } });
    await fill(user);

    await user.click(confirm());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(/La respuesta del servidor no es válida/);
    expect(document.body.textContent).not.toContain("SECRETO");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("429 dice cuánto esperar", async () => {
    const { user } = renderModal(PHONE, { handlers: { [ROTATE]: apiError(429, "rate_limited", "x", {}, { "Retry-After": "20" }) } });
    await fill(user);

    await user.click(confirm());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("espera 20 segundos");
  });

  it("403 y 404 tienen su explicación", async () => {
    const { user } = renderModal(PHONE, { handlers: { [ROTATE]: apiError(404, "not_found", "x") } });
    await fill(user);

    await user.click(confirm());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(/Esa llave ya no existe/);
  });

  it("un id que no es UUID no sale en la URL", async () => {
    const { user, mock } = renderModal(cryptoKey({ id: "../x", data_class: "member.phone" }));
    await fill(user);

    await user.click(confirm());

    expect(await within(dialog()).findByRole("alert")).toBeInTheDocument();
    expect(mock.calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });
});
