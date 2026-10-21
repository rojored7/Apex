// @vitest-environment node
// US-059 T2 y T8 (criterios 1 y 9): fetch directo solo dentro de src/core/api y nada de
// console en src/. Como web/eslint.config.js está protegido por el hook config-protection,
// las reglas viven en tests/lint/restricted-config.ts y esta prueba las aplica a todo src/.
import { lintSnippet, lintSourceTree } from "./restricted-config";

describe("fetch solo desde src/core/api", () => {
  it("rechaza fetch( en una feature", async () => {
    expect(await lintSnippet('export const x = () => fetch("/api/v1/members");\n', "src/features/x/api.ts")).toContain(
      "no-restricted-globals",
    );
  });

  it("rechaza window.fetch y globalThis.fetch en un componente", async () => {
    const rules = await lintSnippet(
      'export const a = () => window.fetch("/x");\nexport const b = () => globalThis.fetch("/x");\n',
      "src/shared/ui/X.tsx",
    );
    expect(rules.filter((r) => r === "no-restricted-properties")).toHaveLength(2);
  });

  it("acepta fetch en src/core/api/client.ts", async () => {
    expect(await lintSnippet('export const x = () => fetch("/api/v1/health");\n', "src/core/api/client.ts")).toEqual([]);
  });

  it("rechaza console.log también dentro de src/core/api", async () => {
    expect(await lintSnippet('console.log("cuerpo");\n', "src/core/api/client.ts")).toContain("no-console");
    expect(await lintSnippet('console.error("x");\n', "src/features/x/Page.tsx")).toContain("no-console");
  });

  it("todo src/ cumple las reglas de fetch, console, Intl y roles", async () => {
    expect(await lintSourceTree()).toEqual([]);
  }, 60_000);
});
