// S2-F2: contenedores de las zonas que no son el panel. Leen de la sesión o de la ruta lo que
// su layout presentacional necesita.
import { Outlet, useMatches } from "react-router";
import { useSession } from "../core/auth";
import { GymLayout } from "./GymLayout";
import { PortalLayout } from "./PortalLayout";
import { TvLayout } from "./TvLayout";

export function PortalShell() {
  const { user } = useSession();
  return <PortalLayout gymName={user?.gymName} />;
}

function titleOf(handle: unknown): string | null {
  if (typeof handle !== "object" || handle === null || !("title" in handle)) return null;
  const title: unknown = handle.title;
  return typeof title === "string" ? title : null;
}

/** La tablet del box toma el título de la ruta (handle.title) y sale al panel. */
export function GymShell() {
  const matches = useMatches();
  const title = matches.map((m) => titleOf(m.handle)).findLast((t): t is string => t !== null) ?? "APEX";
  // DESIGN-GAP: CheckIn.html sale a "‹ Clases"; cada pantalla de tablet fijará su salida cuando
  // exista (v0.4); por ahora sale al inicio del panel.
  return <GymLayout title={title} exitTo="/" />;
}

export function TvShell() {
  return (
    <TvLayout>
      <Outlet />
    </TvLayout>
  );
}
