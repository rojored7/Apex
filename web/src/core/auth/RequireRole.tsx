// US-053 T5 (criterios 3 y 4): guardas por rol.
// - Con `zone` va antes del layout y manda a cada rol a su zona: quien entra al portal
//   (can(role, "portal.view"), el socio) no usa el panel ni la tablet y va a /mi; el equipo en
//   /mi/* va a /. Así el layout equivocado ni se pinta.
// - Sin `zone` va dentro del layout, como padre de las páginas: si el rol no tiene el acceso de
//   la ruta (handle.access de la coincidencia más profunda), muestra "Sin permiso" con el
//   menú del rol alrededor.
// Comodidad, no control: cada endpoint vuelve a verificar el rol (RN-15).
import { Navigate, Outlet, useMatches } from "react-router";
import type { RouteAccess } from "../../config/routeTable";
import { NoPermissionPage } from "./NoPermissionPage";
import { can } from "./permissions";
import { canAccess, homeFor } from "./routeAccess";
import { useSession } from "./session";

export type GuardZone = "panel" | "portal";

export interface RequireRoleProps {
  zone?: GuardZone;
}

function accessOf(handle: unknown): RouteAccess | null {
  if (typeof handle !== "object" || handle === null || !("access" in handle)) return null;
  return (handle as { access: RouteAccess }).access;
}

export function RequireRole({ zone }: RequireRoleProps) {
  const role = useSession().user?.role ?? null;
  const matches = useMatches();

  if (zone !== undefined) {
    const isMember = can(role, "portal.view");
    const wrongZone = zone === "portal" ? !isMember : isMember;
    return wrongZone ? <Navigate to={homeFor(role)} replace /> : <Outlet />;
  }

  const access = matches.map((m) => accessOf(m.handle)).findLast((a): a is RouteAccess => a !== null) ?? null;
  if (access !== null && !canAccess(role, access)) return <NoPermissionPage />;
  return <Outlet />;
}
