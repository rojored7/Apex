// S5-F4 · US-137 (front): "Recibo" del detalle y de la fila (GET /payments/{id}/receipt.pdf por
// api.blob). Admin y coach lo ven, el socio no; carga, 404, 503 con el mensaje del api; el PDF se
// entrega al navegador y no se guarda.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { RoleProvider, type Role } from "../../../core/auth";
import { PAYMENT_ID } from "../../../test/payments";
import { mockApi, testQueryClient, type MockHandler, type MockReply } from "../../../test/server";
import { RECEIPT_BUSY, ReceiptButton, type ReceiptButtonProps } from "./ReceiptButton";

const saved = vi.hoisted(() => ({ calls: [] as { filename: string | null; text: string; fallback: string }[] }));

vi.mock("../../../shared/lib/download", () => ({
  saveDownload: vi.fn(async (result: { blob: Blob; filename: string | null }, fallback: string) => {
    saved.calls.push({ filename: result.filename, text: await result.blob.text(), fallback });
  }),
}));

const apiError = (status: number, code: string, message: string, headers?: Record<string, string>): MockReply => ({
  status,
  body: { error: { code, message } },
  ...(headers ? { headers } : {}),
});

const RECEIPT_KEY = `GET /payments/${PAYMENT_ID}/receipt.pdf`;
const RECEIPT_FILE: MockHandler = { status: 200, file: { content: "%PDF-1.4", contentType: "application/pdf", filename: "recibo-99999999.pdf" } };

function renderButton(role: Role, props: Partial<ReceiptButtonProps> = {}, handlers: Record<string, MockHandler> = {}) {
  const mock = mockApi({ [RECEIPT_KEY]: RECEIPT_FILE, ...handlers });
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <RoleProvider value={role}>
        <ReceiptButton paymentId={PAYMENT_ID} {...props} />
      </RoleProvider>
    </QueryClientProvider>,
  );
  return { mock, user: userEvent.setup(), ...view };
}

beforeEach(() => {
  saved.calls.length = 0;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ReceiptButton", () => {
  it.each<Role>(["admin", "coach"])("el %s ve 'Recibo'", (role) => {
    renderButton(role);

    expect(screen.getByRole("button", { name: "Descargar el recibo del pago" })).toBeInTheDocument();
  });

  it("el socio no lo ve", () => {
    renderButton("member");

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("descarga el PDF por api.blob y lo entrega con el nombre del api", async () => {
    const { mock, user } = renderButton("admin");

    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));

    await waitFor(() => {
      expect(saved.calls).toEqual([{ filename: "recibo-99999999.pdf", text: "%PDF-1.4", fallback: "recibo-99999999.pdf" }]);
    });
    expect(mock.callsTo(RECEIPT_KEY)).toHaveLength(1);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("en la fila el nombre accesible incluye al socio", () => {
    renderButton("coach", { memberName: "Ana Gómez", appearance: "inline" });

    expect(screen.getByRole("button", { name: "Descargar el recibo del pago de Ana Gómez" })).toHaveTextContent("Recibo");
  });

  it("mientras descarga queda ocupado y lo anuncia; un segundo clic no pide otro PDF", async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const { mock, user } = renderButton("admin", {}, {
      [RECEIPT_KEY]: async () => {
        await gate;
        return { status: 200, file: { content: "%PDF", contentType: "application/pdf" } };
      },
    });

    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));

    const busy = await screen.findByRole("button", { name: "Descargar el recibo del pago" });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveTextContent(RECEIPT_BUSY);
    await user.click(busy);
    expect(mock.callsTo(RECEIPT_KEY)).toHaveLength(1);

    release?.();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Descargar el recibo del pago" })).toBeEnabled();
    });
    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("404: dice que el pago ya no existe y qué hacer", async () => {
    const { user } = renderButton("admin", {}, { [RECEIPT_KEY]: apiError(404, "not_found", "Pago no encontrado.") });

    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No encontramos este pago. Actualiza la lista e intenta de nuevo.");
    expect(saved.calls).toHaveLength(0);
  });

  it("503 crypto_unavailable: muestra el mensaje del api", async () => {
    const { user } = renderButton("admin", {}, {
      [RECEIPT_KEY]: apiError(503, "crypto_unavailable", "El custodio de llaves no está disponible. Avise al administrador para desellarlo.", { "Retry-After": "30" }),
    });

    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("El custodio de llaves no está disponible. Avise al administrador para desellarlo.");
  });

  it("403 y 429 usan el texto de la pantalla; un 500, el de reintentar", async () => {
    const { user } = renderButton("admin", {}, { [RECEIPT_KEY]: apiError(403, "forbidden", "Forbidden") });
    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para descargar esta información.");
    cleanup();
    vi.unstubAllGlobals();

    renderButton("admin", {}, { [RECEIPT_KEY]: apiError(429, "rate_limited", "x", { "Retry-After": "20" }) });
    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Espera 20 segundos e intenta de nuevo.");
    cleanup();
    vi.unstubAllGlobals();

    renderButton("admin", {}, { [RECEIPT_KEY]: apiError(500, "internal_error", "boom") });
    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos preparar la descarga. Intenta de nuevo en un momento.");
  });

  it("un error se borra al reintentar y la descarga que sale bien no deja aviso", async () => {
    let attempt = 0;
    const { user } = renderButton("admin", {}, {
      [RECEIPT_KEY]: () => {
        attempt += 1;
        return attempt === 1 ? { status: 500, body: { error: { code: "internal_error", message: "boom" } } } : { status: 200, file: { content: "%PDF", contentType: "application/pdf" } };
      },
    });

    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));

    await waitFor(() => {
      expect(saved.calls).toHaveLength(1);
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad (botón y error)", async () => {
    const { user, container } = renderButton("admin", {}, { [RECEIPT_KEY]: apiError(404, "not_found", "x") });
    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));
    await screen.findByRole("alert");

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("ReceiptButton · revisión de seguridad de F4", () => {
  it("LOW 1: al desmontar durante la descarga se cancela, no se entrega nada y no hay error", async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const { mock, user, unmount } = renderButton("admin", {}, {
      [RECEIPT_KEY]: async () => {
        await gate;
        return RECEIPT_FILE;
      },
    });

    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));
    await waitFor(() => {
      expect(mock.callsTo(RECEIPT_KEY)).toHaveLength(1);
    });
    expect(mock.callsTo(RECEIPT_KEY)[0]?.signal?.aborted).toBe(false);
    unmount();
    expect(mock.callsTo(RECEIPT_KEY)[0]?.signal?.aborted).toBe(true);
    release?.();
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(saved.calls).toHaveLength(0);
  });

  it("LOW 2: un 503 busy dice cuánto esperar, bloquea el botón ese tiempo y no reintenta solo", async () => {
    const { mock, user } = renderButton("admin", {}, { [RECEIPT_KEY]: apiError(503, "busy", "ocupado", { "Retry-After": "1" }) });

    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("El sistema está ocupado. Espera 1 segundo e intenta de nuevo.");
    expect(screen.getByRole("button", { name: "Descargar el recibo del pago" })).toBeDisabled();
    expect(mock.callsTo(RECEIPT_KEY)).toHaveLength(1);
    await waitFor(
      () => {
        expect(screen.getByRole("button", { name: "Descargar el recibo del pago" })).toBeEnabled();
      },
      { timeout: 3000 },
    );
    expect(mock.callsTo(RECEIPT_KEY)).toHaveLength(1);
  });

  it("LOW 3: un archivo que no es PDF ni CSV no se entrega", async () => {
    const { user } = renderButton("admin", {}, { [RECEIPT_KEY]: { status: 200, file: { content: "<html></html>", contentType: "text/html" } } });

    await user.click(screen.getByRole("button", { name: "Descargar el recibo del pago" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("El servidor devolvió un archivo que no esperábamos");
    expect(saved.calls).toHaveLength(0);
  });
});
