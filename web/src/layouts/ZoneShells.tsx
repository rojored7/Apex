// S2-F2: contenedores de las zonas que no son el panel. Leen de la sesión o de la ruta lo que
// su layout presentacional necesita.
import { useEffect, useMemo } from "react";
import { Outlet, useLocation, useMatches, useNavigate } from "react-router";
import { CustodyNoticeHost } from "../core/custody/CustodyNoticeHost";
import { logout, useSession } from "../core/auth";
import { confirmPassword } from "../core/auth/confirmPassword";
import { GymLayout, type TabletOptions } from "./GymLayout";
import { PortalLayout } from "./PortalLayout";
import { CHECKIN_PATH, enterTabletMode, isTabletMode, leaveTabletMode } from "./tabletMode";
import { TvLayout } from "./TvLayout";

export function PortalShell() {
  const { user } = useSession();
  return (
    <PortalLayout gymName={user?.gymName}>
      <CustodyNoticeHost />
      <Outlet />
    </PortalLayout>
  );
}

function titleOf(handle: unknown): string | null {
  if (typeof handle !== "object" || handle === null || !("title" in handle)) return null;
  const title: unknown = handle.title;
  return typeof title === "string" ? title : null;
}

const NO_SESSION_MESSAGE = "Tu sesión ya no está abierta. Vuelve a iniciar sesión.";

/**
 * La tablet del box toma el título de la ruta (handle.title). S7-F4 (S7-D24): al entrar a /clases/:id/checkin marca el modo tablet
 * (marca en memoria); mientras rija, la barra no lleva enlaces al panel, salir pide la contraseña de la cuenta y 10 minutos sin
 * actividad cierran la sesión.
 */
export function GymShell() {
  const matches = useMatches();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user } = useSession();
  const email = user?.email;
  const onCheckIn = CHECKIN_PATH.test(pathname);
  useEffect(() => {
    if (onCheckIn) enterTabletMode();
  }, [onCheckIn]);
  const isTablet = onCheckIn || isTabletMode();
  const title = matches.map((m) => titleOf(m.handle)).findLast((t): t is string => t !== null) ?? "APEX";

  const tablet = useMemo<TabletOptions>(
    () => ({
      verifyPassword: (password) => (email === undefined ? Promise.resolve(NO_SESSION_MESSAGE) : confirmPassword(email, password)),
      onLeave: (to) => {
        leaveTabletMode();
        void navigate(to);
      },
      onIdle: () => {
        leaveTabletMode();
        void logout();
      },
    }),
    [email, navigate],
  );
  // DESIGN-GAP: cada pantalla de tablet fijará su salida cuando exista; el check-in sale a «‹ Clases» y las demás, por ahora, al inicio del panel.
  return <GymLayout title={title} exitTo={onCheckIn ? "/clases" : "/"} exitLabel={onCheckIn ? "Clases" : "Salir"} tablet={isTablet ? tablet : undefined} />;
}

export function TvShell() {
  return (
    <TvLayout>
      <Outlet />
    </TvLayout>
  );
}
