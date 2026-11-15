// S7-F4 · US-159: lo que la tablet del box (GymLayout) comparte con la pantalla que enmarca.
// - useGymHeader: la pantalla pone el título («Check-in · 17:00 · Coach María»), el subtítulo y el contador
//   «3 / 12 llegaron» en la barra; al desmontar vuelven los de la ruta.
// - useGym: `tablet` dice si rige el modo tablet (S7-D24) y `requestLeave(to)` sale hacia `to` (en modo tablet
//   pidiendo antes la contraseña; fuera de él, navegando).
import { createContext, useContext, useEffect } from "react";

export interface GymCounter {
  value: number;
  of: number;
  label: string;
}

export interface GymHeader {
  title: string;
  subtitle?: string | undefined;
  counter?: GymCounter | undefined;
}

export interface GymContextValue {
  tablet: boolean;
  requestLeave: (to: string) => void;
  setHeader: (header: GymHeader | null) => void;
}

const NOOP = (): void => undefined;

export const GymContext = createContext<GymContextValue>({ tablet: false, requestLeave: NOOP, setHeader: NOOP });

export function useGym(): GymContextValue {
  return useContext(GymContext);
}

/** Pone el encabezado de la tablet mientras la pantalla está montada; `null` deja el de la ruta. */
export function useGymHeader(header: GymHeader | null): void {
  const { setHeader } = useGym();
  const title = header?.title;
  const subtitle = header?.subtitle;
  const value = header?.counter?.value;
  const of = header?.counter?.of;
  const label = header?.counter?.label;
  useEffect(() => {
    if (title === undefined) return undefined;
    const counter = value !== undefined && of !== undefined && label !== undefined ? { value, of, label } : undefined;
    setHeader({ title, subtitle, counter });
    return () => {
      setHeader(null);
    };
  }, [setHeader, title, subtitle, value, of, label]);
}
