// @vitest-environment node
// US-060 T2 (criterio 7): ningún componente formatea dinero o fechas por fuera de
// src/core/i18n. Las reglas viven en tests/lint/restricted-config.ts (ver no-direct-fetch).
import { lintSnippet } from "./restricted-config";

describe("formato solo desde src/core/i18n", () => {
  it.each(["toLocaleString", "toLocaleDateString", "toLocaleTimeString"])("rechaza %s en un componente", async (method) => {
    expect(await lintSnippet(`export const x = (n: number) => n.${method}();\n`, "src/shared/ui/KpiCard.tsx")).toContain(
      "no-restricted-properties",
    );
  });

  it("rechaza Intl en un componente", async () => {
    expect(
      await lintSnippet('export const f = new Intl.NumberFormat("es-CO");\n', "src/features/dashboard/Kpi.tsx"),
    ).toContain("no-restricted-globals");
  });

  it("rechaza Intl también dentro de src/core/api", async () => {
    expect(await lintSnippet('export const f = new Intl.DateTimeFormat("es-CO");\n', "src/core/api/x.ts")).toContain(
      "no-restricted-globals",
    );
  });

  it("acepta Intl y toLocaleString en src/core/i18n/format.ts", async () => {
    expect(
      await lintSnippet(
        'export const f = new Intl.NumberFormat("es-CO");\nexport const g = (n: number) => n.toLocaleString();\n',
        "src/core/i18n/format.ts",
      ),
    ).toEqual([]);
  });

  it("src/core/i18n sigue sin poder usar fetch", async () => {
    expect(await lintSnippet('export const x = () => fetch("/x");\n', "src/core/i18n/format.ts")).toContain(
      "no-restricted-globals",
    );
  });
});
