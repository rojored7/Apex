// @vitest-environment node
// US-066 T2 (criterio 3): el valor en claro de MaskedValue no pasa por la caché de TanStack
// Query ni por el almacenamiento del navegador ni por la URL.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const SOURCE = readFileSync(fileURLToPath(new URL("../../src/shared/ui/MaskedValue.tsx", import.meta.url)), "utf8");

describe("MaskedValue no cachea el claro", () => {
  it("no importa @tanstack/react-query", () => {
    expect(SOURCE).not.toMatch(/@tanstack\/react-query/);
  });

  it.each(["localStorage", "sessionStorage", "indexedDB", "document.cookie", "history.", "location.", "useSearchParams", "console."])(
    "no usa %s",
    (needle) => {
      expect(SOURCE).not.toContain(needle);
    },
  );

  it("no recibe el valor en claro como prop: solo masked y onReveal", () => {
    expect(SOURCE).toMatch(/masked:\s*string \| null/);
    expect(SOURCE).toMatch(/onReveal:\s*\(\) => Promise<string>/);
    expect(SOURCE).not.toMatch(/\bvalue\??:\s*string/);
  });
});
