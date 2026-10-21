import * as auth from "./index";

describe("src/core/auth", () => {
  it("exporta la matriz, can, useCan y Can", () => {
    expect(auth.ROLES).toHaveLength(3);
    expect(auth.ACTIONS.length).toBeGreaterThan(0);
    expect(auth.can("admin", "plans.manage")).toBe(true);
    expect(typeof auth.useCan).toBe("function");
    expect(typeof auth.useRole).toBe("function");
    expect(typeof auth.Can).toBe("function");
    expect(auth.RoleProvider).toBe(auth.RoleContext.Provider);
  });
});
