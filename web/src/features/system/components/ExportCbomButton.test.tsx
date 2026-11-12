// S6-F2 · US-146 (S6-D57, S6-B3): «Exportar CBOM». GET /crypto/cbom por api.blob con el JSON permitido
// solo en esta llamada, nombre del api saneado y entrega con downloadBlob (a[download] con ObjectURL
// revocado); sin caché ni almacenamiento. 429, 403 y 503 con mensaje; el botón se bloquea mientras baja.
import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";
import { mockApi, renderWithProviders, type MockReply } from "../../../test/server";
import { apiError } from "../../../test/keys";
import { ExportCbomButton } from "./ExportCbomButton";
import userEvent from "@testing-library/user-event";

const CBOM: MockReply = {
  status: 200,
  file: { content: '{"format":"cbom"}', contentType: "application/json", filename: "../apex-cbom-2026-10-20.json" },
};

let clicked: { download: string; href: string }[];
let revoked: string[];

beforeEach(() => {
  clicked = [];
  revoked = [];
  vi.stubGlobal(
    "URL",
    Object.assign(URL, {
      createObjectURL: vi.fn(() => "blob:apex/cbom"),
      revokeObjectURL: vi.fn((url: string) => {
        revoked.push(url);
      }),
    }),
  );
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push({ download: this.download, href: this.href });
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderButton(reply: MockReply = CBOM) {
  const mock = mockApi({ "GET /crypto/cbom": reply });
  return { mock, user: userEvent.setup(), ...renderWithProviders(<ExportCbomButton />) };
}

describe("ExportCbomButton", () => {
  it("baja el CBOM con el nombre del api saneado y revoca el ObjectURL", async () => {
    const { mock, user } = renderButton();

    await user.click(screen.getByRole("button", { name: "Exportar CBOM" }));

    await waitFor(() => {
      expect(clicked).toHaveLength(1);
    });
    expect(clicked[0]?.download).toBe("apex-cbom-2026-10-20.json");
    expect(mock.callsTo("GET /crypto/cbom")).toHaveLength(1);
    await waitFor(() => {
      expect(revoked).toEqual(["blob:apex/cbom"]);
    });
  });

  it("sin nombre del api usa apex-cbom-AAAA-MM-DD.json de respaldo", async () => {
    const { user } = renderButton({ status: 200, file: { content: "{}", contentType: "application/json" } });

    await user.click(screen.getByRole("button", { name: "Exportar CBOM" }));

    await waitFor(() => {
      expect(clicked).toHaveLength(1);
    });
    expect(clicked[0]?.download).toMatch(/^apex-cbom-\d{4}-\d{2}-\d{2}\.json$/);
  });

  it("el botón queda deshabilitado mientras baja el archivo", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    mockApi({
      "GET /crypto/cbom": async () => {
        await gate;
        return CBOM;
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<ExportCbomButton />);

    await user.click(screen.getByRole("button", { name: "Exportar CBOM" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Exportar CBOM|Exportando/ })).toBeDisabled();
    });
    release();
    await waitFor(() => {
      expect(clicked).toHaveLength(1);
    });
  });

  it("un 429 dice que espere y no entrega nada", async () => {
    const { user } = renderButton(apiError(429, "rate_limited", "x", {}, { "Retry-After": "30" }));

    await user.click(screen.getByRole("button", { name: "Exportar CBOM" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Espera 30 segundos");
    expect(clicked).toHaveLength(0);
  });

  it("un 403 explica que solo el administrador exporta", async () => {
    const { user } = renderButton(apiError(403, "forbidden", "x"));

    await user.click(screen.getByRole("button", { name: "Exportar CBOM" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso");
  });

  it("un 503 crypto_unavailable muestra el texto del api", async () => {
    const { user } = renderButton(apiError(503, "crypto_unavailable", "El custodio de llaves no responde. Intenta en unos minutos."));

    await user.click(screen.getByRole("button", { name: "Exportar CBOM" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("El custodio de llaves no responde. Intenta en unos minutos.");
  });

  it("un error vuelve a permitir reintentar", async () => {
    const { user } = renderButton(apiError(500, "internal_error", "x"));

    await user.click(screen.getByRole("button", { name: "Exportar CBOM" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exportar CBOM" })).toBeEnabled();
  });
});
