// US-062 T4: marco de la pantalla de TV (TV.html), solo en oscuro.
// - Escenario fijo de 1920 × 1080 que se escala con transform para pantallas que no son
//   exactamente 1080p, sin barras de desplazamiento.
// - Sin interacción: el escenario es `inert`, sin cursor y sin elementos enfocables.
import { useEffect, useState, type ReactNode } from "react";
import { useForcedTheme } from "../shared/hooks/useForcedTheme";
import styles from "./TvLayout.module.css";

export interface TvLayoutProps {
  children?: ReactNode;
}

export const TV_WIDTH = 1920;
export const TV_HEIGHT = 1080;

/** Escala que hace caber el escenario de 1920 × 1080 en la ventana, sin deformarlo. */
export function tvScale(width: number, height: number): number {
  if (!(width > 0) || !(height > 0)) return 1;
  return Math.min(width / TV_WIDTH, height / TV_HEIGHT);
}

function useWindowScale(): number {
  const [scale, setScale] = useState(() => tvScale(window.innerWidth, window.innerHeight));
  useEffect(() => {
    const onResize = (): void => {
      setScale(tvScale(window.innerWidth, window.innerHeight));
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
    };
  }, []);
  return scale;
}

export function TvLayout({ children }: TvLayoutProps) {
  useForcedTheme("dark");
  const scale = useWindowScale();
  return (
    <div className={styles.root}>
      <div
        data-testid="tv-stage"
        className={styles.stage}
        inert
        role="region"
        aria-label="Pantalla del gimnasio"
        style={{ transform: `scale(${String(scale)})` }}
      >
        {children}
      </div>
    </div>
  );
}
