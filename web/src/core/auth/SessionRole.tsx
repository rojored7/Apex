// US-053 (S2-F2): el rol de la sesión llega a RoleProvider, así useCan y <Can> leen la
// sesión real sin cambiar su firma (US-040 T4).
import type { ReactNode } from "react";
import { useSession } from "./session";
import { RoleProvider } from "./useCan";

export function SessionRoleProvider({ children }: { children: ReactNode }) {
  const { user } = useSession();
  return <RoleProvider value={user?.role ?? null}>{children}</RoleProvider>;
}
