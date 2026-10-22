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

  it("exporta las guardas, el acceso por ruta y la sesión del Sprint 2 (US-053)", () => {
    expect(auth.ROLE_LABELS.coach).toBe("Coach");
    expect(auth.homeFor("coach")).toBe("/");
    expect(auth.canAccessRoute("coach", "/planes")).toBe(false);
    expect(auth.safeNext("//evil.com", "admin")).toBeNull();
    for (const fn of [auth.RequireAuth, auth.RequireRole, auth.NoPermissionPage, auth.SessionRoleProvider, auth.useSession, auth.restoreSession]) {
      expect(typeof fn).toBe("function");
    }
  });
});

describe("src/core/auth · S2-F3", () => {
  it("exporta el refresh coordinado, el cierre de sesión y el puente con el cliente", () => {
    expect(auth.AUTH_CHANNEL).toBe("apex-auth");
    expect(auth.REFRESH_LOCK).toBe("apex-refresh");
    for (const fn of [auth.refreshAccessToken, auth.refreshCurrentUser, auth.adoptAccessToken, auth.logout, auth.installSessionBridge]) {
      expect(typeof fn).toBe("function");
    }
  });
});
