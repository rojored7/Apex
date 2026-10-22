// Sesión de prueba (plan del Sprint 2, sección 2): signInAs deja una sesión autenticada en
// memoria sin pasar por el api; signOutForTests vuelve al estado inicial.
import { cleanup } from "@testing-library/react";
import { ROLES, type Role } from "../core/auth/permissions";
import { resetSessionForTests, setSession, type SessionUser } from "../core/auth/session";

export const TEST_TOKEN = "token-de-prueba";

export function testUser(role: Role, overrides: Partial<SessionUser> = {}): SessionUser {
  return {
    id: `00000000-0000-4000-8000-00000000000${String(ROLES.indexOf(role) + 1)}`,
    email: `${role}@apex.test`,
    role,
    memberId: null,
    gymName: "Box de prueba",
    mustChangePassword: false,
    ...overrides,
  };
}

export function signInAs(role: Role, overrides: Partial<SessionUser> = {}): SessionUser {
  const user = testUser(role, overrides);
  setSession({ accessToken: TEST_TOKEN, user });
  return user;
}

/**
 * Desmonta lo renderizado y vuelve al estado inicial. Desmontar primero evita que un
 * RequireAuth todavía montado vea "loading" y arranque una restauración que se cruce con la
 * prueba siguiente.
 */
export function signOutForTests(): void {
  cleanup();
  resetSessionForTests();
}
