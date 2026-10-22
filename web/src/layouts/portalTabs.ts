// US-062 T2: destinos del menú inferior del portal. Siguen DESIGN.md y Portal_Inicio.html
// (cinco pestañas; "Avisos" se abre desde "Yo"), no los seis destinos de la historia:
// manda el diseño aprobado (pregunta abierta del desglose, alternativa por defecto).
// Pasar a seis es un cambio de datos aquí, no del componente.
import { CreditCard, Dumbbell, House, type LucideIcon, TrendingUp, User } from "lucide-react";

export interface PortalTab {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Activo solo con la ruta exacta (Inicio). */
  end?: boolean;
}

export const PORTAL_TABS: readonly PortalTab[] = Object.freeze([
  { label: "Inicio", to: "/mi", icon: House, end: true },
  { label: "Pagos", to: "/mi/pagos", icon: CreditCard },
  { label: "WODs", to: "/mi/wods", icon: Dumbbell },
  { label: "Progreso", to: "/mi/progreso", icon: TrendingUp },
  { label: "Yo", to: "/mi/datos", icon: User },
]);
