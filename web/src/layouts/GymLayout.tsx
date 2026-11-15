// US-062 T3: marco de las pantallas de la tablet del box (CheckIn.html y
// Resultados_Registro.html).
// - Tema oscuro forzado sin depender de la preferencia del sistema; se restaura al salir.
// - --control pasa a --control-gym (56 px) en el contenedor: Button y Field miden 56 px sin
//   variantes nuevas.
// - Barra mínima con la salida, el nombre de la sesión y un subtítulo; sin menú lateral.
// S7-F4 (S7-D24, H-2): modo tablet. Con `tablet` la salida deja de ser un enlace (no hay enlaces al panel) y pide la
// contraseña de la cuenta antes de salir; a los 10 minutos sin tocar la pantalla avisa con `onIdle` (el contenedor
// cierra la sesión). La pantalla puede poner su título y el contador de llegadas con useGymHeader.
import { ChevronLeft } from "lucide-react";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Link, Outlet, useNavigate } from "react-router";
import { GymContext, type GymContextValue, type GymCounter, type GymHeader } from "../shared/hooks/gymContext";
import { useForcedTheme } from "../shared/hooks/useForcedTheme";
import { useIdleTimeout } from "../shared/hooks/useIdleTimeout";
import styles from "./GymLayout.module.css";
import { LeaveTabletDialog } from "./LeaveTabletDialog";

/** Diez minutos sin tocar la tablet cierran la sesión (S7-D24). */
export const TABLET_IDLE_MS = 10 * 60 * 1000;

export interface TabletOptions {
  /** Devuelve el mensaje de error, o null si la contraseña es la de la cuenta. */
  verifyPassword: (password: string) => Promise<string | null>;
  /** La contraseña fue correcta: sale del modo hacia `to`. */
  onLeave: (to: string) => void;
  /** Pasó el tiempo sin actividad. */
  onIdle: () => void;
  idleMs?: number;
  /** S7-D41: una navegación fuera del check-in (por ejemplo «atrás») quedó retenida; abre el mismo diálogo de salida hacia ahí. */
  blockedTo?: string | null;
  /** Se cerró el diálogo de una navegación retenida sin salir. */
  onCancelLeave?: () => void;
  /** S7-D42: cambia de sesión de clase sin contraseña (el servidor solo acepta hoy y ayer). Devuelve el error o null. */
  switchSession?: (path: string) => Promise<string | null>;
}

export interface GymLayoutProps {
  title: string;
  subtitle?: string | undefined;
  exitTo: string;
  exitLabel?: string;
  counter?: GymCounter | undefined;
  tablet?: TabletOptions | undefined;
  children?: ReactNode;
}

function Counter({ counter }: { counter: GymCounter }) {
  return (
    <div className={styles.counter} role="status" aria-live="polite" aria-label={`${counter.label.charAt(0).toUpperCase()}${counter.label.slice(1)} ${String(counter.value)} de ${String(counter.of)}`}>
      <p className={styles.counterValue}>
        {String(counter.value)} <span className={styles.counterOf}>{`/ ${String(counter.of)}`}</span> <span className={styles.counterLabel}>{counter.label}</span>
      </p>
    </div>
  );
}

export function GymLayout({ title, subtitle, exitTo, exitLabel = "Salir", counter, tablet, children }: GymLayoutProps) {
  useForcedTheme("dark");
  const navigate = useNavigate();
  const [override, setOverride] = useState<GymHeader | null>(null);
  const [leaveTo, setLeaveTo] = useState<string | null>(null);
  const isTablet = tablet !== undefined;
  const onIdle = tablet?.onIdle;
  useIdleTimeout(
    tablet?.idleMs ?? TABLET_IDLE_MS,
    () => {
      onIdle?.();
    },
    isTablet,
  );

  const target = leaveTo ?? tablet?.blockedTo ?? null;
  const requestLeave = useCallback(
    (to: string): void => {
      if (isTablet) setLeaveTo(to);
      else void navigate(to);
    },
    [isTablet, navigate],
  );
  const switchSession = tablet?.switchSession;
  const context = useMemo<GymContextValue>(
    () => ({ tablet: isTablet, requestLeave, switchSession: switchSession ?? (() => Promise.resolve(null)), setHeader: setOverride }),
    [isTablet, requestLeave, switchSession],
  );

  const shownTitle = override?.title ?? title;
  const shownSubtitle = override ? override.subtitle : subtitle;
  const shownCounter = override ? override.counter : counter;
  return (
    <GymContext.Provider value={context}>
      <div className={styles.root}>
        <header className={styles.bar}>
          {isTablet ? (
            <button
              type="button"
              className={styles.exit}
              onClick={() => {
                requestLeave(exitTo);
              }}
            >
              <ChevronLeft size={20} aria-hidden="true" />
              {exitLabel}
            </button>
          ) : (
            <Link to={exitTo} className={styles.exit}>
              <ChevronLeft size={20} aria-hidden="true" />
              {exitLabel}
            </Link>
          )}
          <div className={styles.titles}>
            <h1 className={styles.title}>{shownTitle}</h1>
            {shownSubtitle !== undefined && <p className={styles.subtitle}>{shownSubtitle}</p>}
          </div>
          {shownCounter ? <Counter counter={shownCounter} /> : null}
        </header>
        <main className={styles.content}>{children ?? <Outlet />}</main>
        {tablet ? (
          <LeaveTabletDialog
            open={target !== null}
            verifyPassword={tablet.verifyPassword}
            onConfirmed={() => {
              setLeaveTo(null);
              if (target !== null) tablet.onLeave(target);
            }}
            onClose={() => {
              setLeaveTo(null);
              tablet.onCancelLeave?.();
            }}
          />
        ) : null}
      </div>
    </GymContext.Provider>
  );
}
