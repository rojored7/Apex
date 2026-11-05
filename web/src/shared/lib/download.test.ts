// S5-F4 (L-8): entrega del archivo al navegador sin dejar rastro. jsdom no implementa
// URL.createObjectURL: se simula, igual que el clic del enlace.
import type { BlobResult } from "../../core/api/client";
import { downloadBlob, safeFilename, saveDownload } from "./download";

let created: string[];
let revoked: string[];
let clicked: { href: string; download: string; inDom: boolean }[];

beforeEach(() => {
  vi.useFakeTimers();
  created = [];
  revoked = [];
  clicked = [];
  let n = 0;
  vi.stubGlobal(
    "URL",
    Object.assign(URL, {
      createObjectURL: vi.fn(() => {
        n += 1;
        const url = `blob:apex/${String(n)}`;
        created.push(url);
        return url;
      }),
      revokeObjectURL: vi.fn((url: string) => {
        revoked.push(url);
      }),
    }),
  );
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push({ href: this.href, download: this.download, inDom: document.body.contains(this) });
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("downloadBlob", () => {
  it("crea el ObjectURL, hace clic en un enlace con el nombre y luego lo revoca", () => {
    downloadBlob(new Blob(["x"]), "recibo-9a8b7c6d.pdf");

    expect(created).toEqual(["blob:apex/1"]);
    expect(clicked).toEqual([{ href: "blob:apex/1", download: "recibo-9a8b7c6d.pdf", inDom: true }]);
    vi.advanceTimersByTime(0);
    expect(revoked).toEqual(["blob:apex/1"]);
  });

  it("no revoca en el mismo tick del clic (Safari y Firefox truncarían la descarga)", () => {
    downloadBlob(new Blob(["x"]), "a.csv");

    expect(revoked).toEqual([]);
    vi.advanceTimersByTime(0);
    expect(revoked).toEqual(["blob:apex/1"]);
  });

  it("no deja nodos en el DOM", () => {
    downloadBlob(new Blob(["x"]), "a.csv");

    expect(document.body.querySelectorAll("a")).toHaveLength(0);
  });

  it("revoca y limpia aunque el clic falle", () => {
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {
      throw new Error("bloqueado");
    });

    expect(() => {
      downloadBlob(new Blob(["x"]), "a.csv");
    }).toThrow("bloqueado");

    vi.advanceTimersByTime(0);
    expect(revoked).toEqual(["blob:apex/1"]);
    expect(document.body.querySelectorAll("a")).toHaveLength(0);
  });
});

describe("saveDownload", () => {
  const result = (filename: string | null): BlobResult => ({ blob: new Blob(["x"]), filename, contentType: "text/csv" });

  it("usa el nombre del Content-Disposition si existe", () => {
    saveDownload(result("socios-20261105.csv"), "socios.csv");

    expect(clicked[0]?.download).toBe("socios-20261105.csv");
  });

  it("sin nombre del api usa el de respaldo", () => {
    saveDownload(result(null), "pagos-20261105.csv");

    expect(clicked[0]?.download).toBe("pagos-20261105.csv");
  });

  it("sanea un nombre con rutas o caracteres raros", () => {
    saveDownload(result("../../etc/pa sswd<>.csv"), "x.csv");

    expect(clicked[0]?.download).toBe("pa_sswd_.csv");
  });
});

describe("safeFilename", () => {
  it.each([
    ["recibo-9a8b7c6d.pdf", "recibo-9a8b7c6d.pdf"],
    ["C:\\temp\\x.csv", "x.csv"],
    [".htaccess", "htaccess"],
    ["...", "respaldo.csv"],
    ["", "respaldo.csv"],
    [null, "respaldo.csv"],
    [undefined, "respaldo.csv"],
    ["ñandú.csv", "_and_.csv"],
  ])("%s -> %s", (name, expected) => {
    expect(safeFilename(name, "respaldo.csv")).toBe(expected);
  });

  it("recorta a 100 caracteres", () => {
    expect(safeFilename(`${"a".repeat(300)}.csv`, "x.csv")).toHaveLength(100);
  });
});
