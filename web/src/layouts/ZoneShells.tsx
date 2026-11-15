// S2-F2: contenedores de las zonas que no son el panel. Leen de la sesión o de la ruta lo que
// su layout presentacional necesita.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Outlet, useBlocker, useLocation, useMatches, useNavigate } from "react-router";
import { CustodyNoticeHost } from "../core/custody/CustodyNoticeHost";
import { useSession } from "../core/auth";
import { enterKiosk, exitKiosk, logoutDevice, normalizeKioskPath } from "../core/auth/kiosk";
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
 * La tablet del box toma el título de la ruta (handle.title). S7-D41: el modo tablet lo manda el servidor. Al llegar a
 * /clases/:id/checkin llama POST /auth/kiosk (la sesión queda confinada y trae un access nuevo); el check-in solo se muestra
 * con la marca puesta (`kioskPath` igual a la ruta). Con la marca, «atrás» y toda navegación fuera abren el diálogo de salida
 * con contraseña (POST /auth/kiosk/exit) y 10 minutos sin actividad cierran la sesión. Recargar o escribir otra dirección lo
 * resuelve RequireAuth con el kiosk_path de /auth/me. S7-D42: `switchSession` pasa a otra clase de hoy sin contraseña.
 */
export function GymShell() {
  const matches = useMatches();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user } = useSession();
  const hasUser = user !== null;
  const onCheckIn = CHECKIN_PATH.test(pathname);
  const wanted = normalizeKioskPath(pathname);
  const kioskPath = user?.kioskPath ?? null;
  const [enterError, setEnterError] = useState<string | null>(null);
  // La salida en curso vale solo para la ruta en que empezó: al cambiar de ruta se apaga sola (LOW-2).
  const [leavingAt, setLeavingAt] = useState<string | null>(null);
  const leavingRef = useRef<string | null>(null);
  const kioskRef = useRef(kioskPath);
  const entering = useRef(false);

  const setLeaving = useCallback(
    (on: boolean): void => {
      const at = on ? pathname : null;
      leavingRef.current = at;
      setLeavingAt(at);
    },
    [pathname],
  );

  useEffect(() => {
    kioskRef.current = kioskPath;
  }, [kioskPath]);

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
  // HIGH-1: se entra al LLEGAR a la ruta del check-in, no cuando la marca pasa a null (eso es la salida con contraseña).
  useEffect(() => {
    if (onCheckIn && hasUser && kioskRef.current !== wanted) enter(wanted);
  }, [onCheckIn, hasUser, wanted, enter]);

  // Optimista en el check-in: sin esperar al servidor la barra ya no trae enlaces.
  const isTablet = kioskPath !== null || (onCheckIn && hasUser);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => isTablet && leavingRef.current !== currentLocation.pathname && nextLocation.pathname !== currentLocation.pathname);
  const title = matches.map((m) => titleOf(m.handle)).findLast((t): t is string => t !== null) ?? "APEX";

  const tablet = useMemo<TabletOptions>(
    () => ({
      verifyPassword: async (password) => {
        // S7-F5b (L2): la marca de salida se pone justo antes de proceder (en onLeave), no mientras viaja la petición.
        return exitKiosk(password);
      },
      onLeave: (to) => {
        setLeaving(true);
        if (blocker.state === "blocked") blocker.proceed();
        else void navigate(to);
      },
      onIdle: () => {
        void logoutDevice();
      },
      blockedTo: blocker.state === "blocked" ? `${blocker.location.pathname}${blocker.location.search}` : null,
      onCancelLeave: () => {
        setLeaving(false);
        if (blocker.state === "blocked") blocker.reset();
      },
      switchSession: async (path) => {
        const target = normalizeKioskPath(path);
        setLeaving(true);
        const failure = await enterKiosk(target);
        if (failure !== null) {
          setLeaving(false);
          return failure;
        }
        await navigate(target, { replace: true });
        return null;
      },
    }),
    [blocker, navigate, setLeaving],
  );
  // MEDIUM-1: el check-in solo se ve con la marca del servidor (o mientras se sale con la contraseña / se cambia de clase).
  const confined = !onCheckIn || !hasUser || leavingAt === pathname || kioskPath === wanted;
  // DESIGN-GAP: cada pantalla de tablet fijará su salida cuando exista; el check-in sale a «‹ Clases» y las demás, por ahora, al inicio del panel.
  return (
    <GymLayout title={title} exitTo={onCheckIn ? "/clases" : "/"} exitLabel={onCheckIn ? "Clases" : "Salir"} tablet={isTablet ? tablet : undefined}>
      {confined ? (
        <Outlet />
      ) : enterError !== null ? (
        <div role="alert">
          <p>{enterError}</p>
          <Button
            size="lg"
            variant="secondary"
            onClick={() => {
              enter(wanted);
            }}
          >
            Reintentar
          </Button>
        </div>
      ) : (
        <p role="status">Activando el modo tablet…</p>
      )}
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
