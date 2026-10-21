// @vitest-environment node
// US-040 T2 (criterio 7): ningún componente compara el rol con un literal; solo
// src/core/auth/permissions.ts y session.ts. La regla vive en tests/lint/restricted-config.ts
// porque web/eslint.config.js está protegido (ver docs/scratch/sprint-01-front.md); la
// aplicación a todo src/ la hace tests/lint/no-direct-fetch.test.ts.
import { lintSnippet, lintSourceTree } from "../lint/restricted-config";

describe("sin literales de rol fuera de la matriz", () => {
  it.each([
    ['export const f = (role: string) => role === "admin";\n', "comparación directa"],
    ['export const f = (u: { role: string }) => "coach" !== u.role;\n', "literal a la izquierda"],
    ['export const f = (session: { user: { role: string } }) => session.user.role == "member";\n', "igualdad débil"],
    ['export function f(role: string) { switch (role) { default: return 1; } }\n', "switch sobre el rol"],
    ['export function f(r: string) { switch (r) { case "admin": return 1; default: return 0; } }\n', "case con literal de rol"],
  ])("rechaza %j (%s) en una feature", async (code) => {
    expect(await lintSnippet(code, "src/features/members/MemberActions.tsx")).toContain("no-restricted-syntax");
  });

  it("acepta la comparación dentro de src/core/auth/permissions.ts y session.ts", async () => {
    const code = 'export const f = (role: string) => role === "admin";\n';

    expect(await lintSnippet(code, "src/core/auth/permissions.ts")).toEqual([]);
    expect(await lintSnippet(code, "src/core/auth/session.ts")).toEqual([]);
  });

  it("acepta pasar un rol como argumento o prop (no es una comparación)", async () => {
    expect(await lintSnippet('import { can } from "../../core/auth/permissions";\nexport const x = can("coach", "members.view");\n', "src/features/x/y.ts")).toEqual([]);
  });

  it("ningún archivo de src/ compara el rol con un literal", async () => {
    const findings = await lintSourceTree();

    expect(findings.filter((f) => f.ruleId === "no-restricted-syntax")).toEqual([]);
  }, 60_000);
});
