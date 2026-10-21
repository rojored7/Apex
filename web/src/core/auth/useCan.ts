// US-040 T4: el rol de la sesión llega por contexto. Hasta US-053 lo inyecta RoleProvider;
// US-053 lo conecta a session.ts sin cambiar la firma de useCan.
import { createContext, useContext } from "react";
import { can, type Action, type Role } from "./permissions";

export const RoleContext = createContext<Role | null>(null);

/** Proveedor del rol actual (`null` = sin sesión). */
export const RoleProvider = RoleContext.Provider;

export function useRole(): Role | null {
  return useContext(RoleContext);
}

export function useCan(action: Action): boolean {
  return can(useRole(), action);
}
