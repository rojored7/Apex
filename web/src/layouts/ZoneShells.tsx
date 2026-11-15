// S2-F2: contenedores de las zonas que no son el panel. Leen de la sesión o de la ruta lo que
// su layout presentacional necesita.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Outlet, useBlocker, useLocation, useMatches, useNavigate } from "react-router";
import { CustodyNoticeHost } from "../core/custody/CustodyNoticeHost";
import { useSession } from "../core/auth";
import { enterKiosk, exitKiosk, logoutDevice } from "../core/auth/kiosk";
import { Button } from "../shared/ui/Button";
import { GymLayout, type TabletOptions } from "./GymLayout";
import { PortalLayout } from "./PortalLayout";
import { CHECKIN_PATH } from "./tabletMode";
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

/**
 * La tablet del box toma el título de la ruta (handle.title). S7-D41: el modo tablet lo manda el servidor. Al entrar a
 * /clases/:id/checkin llama POST /auth/kiosk (la sesión queda confinada y trae un access nuevo); mientras la sesión tenga
 * `kioskPath` la barra no lleva enlaces, «atrás» y toda navegación fuera abren el diálogo de salida con contraseña
 * (POST /auth/kiosk/exit) y 10 minutos sin actividad cierran la sesión. Recargar o escribir otra dirección lo resuelve
 * RequireAuth con el kiosk_path de /auth/me.
 */
export function GymShell() {
  const matches = useMatches();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user } = useSession();
  const onCheckIn = CHECKIN_PATH.test(pathname);
  const kioskPath = user?.kioskPath ?? null;
  const [enterError, setEnterError] = useState<string | null>(null);
  const entering = useRef(false);
  const leaving = useRef(false);

  const enter = useCallback((path: string): void => {
    if (entering.current) return;
    entering.current = true;
    setEnterError(null);
    void enterKiosk(path)
      .then(setEnterError)
      .finally(() => {
        entering.current = false;
      });
  }, []);
  const needsEntry = onCheckIn && user !== null && kioskPath === null;
  useEffect(() => {
    if (needsEntry) enter(pathname);
  }, [needsEntry, pathname, enter]);

  // Optimista en el check-in: sin esperar al servidor la barra ya no trae enlaces.
  const isTablet = kioskPath !== null || (onCheckIn && user !== null);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => isTablet && !leaving.current && nextLocation.pathname !== currentLocation.pathname);
  const title = matches.map((m) => titleOf(m.handle)).findLast((t): t is string => t !== null) ?? "APEX";

  const tablet = useMemo<TabletOptions>(
    () => ({
      verifyPassword: exitKiosk,
      onLeave: (to) => {
        leaving.current = true;
        if (blocker.state === "blocked") blocker.proceed();
        else void navigate(to);
      },
      onIdle: () => {
        void logoutDevice();
      },
      blockedTo: blocker.state === "blocked" ? `${blocker.location.pathname}${blocker.location.search}` : null,
      onCancelLeave: () => {
        if (blocker.state === "blocked") blocker.reset();
      },
    }),
    [blocker, navigate],
  );
  // DESIGN-GAP: cada pantalla de tablet fijará su salida cuando exista; el check-in sale a «‹ Clases» y las demás, por ahora, al inicio del panel.
  return (
    <GymLayout title={title} exitTo={onCheckIn ? "/clases" : "/"} exitLabel={onCheckIn ? "Clases" : "Salir"} tablet={isTablet ? tablet : undefined}>
      {enterError !== null ? (
        <div role="alert">
          <p>{enterError}</p>
          <Button
            size="lg"
            variant="secondary"
            onClick={() => {
              enter(pathname);
            }}
          >
            Reintentar
          </Button>
        </div>
      ) : null}
      <Outlet />
    </GymLayout>
  );
}

export function TvShell() {
  return (
    <TvLayout>
      <Outlet />
    </TvLayout>
  );
}
