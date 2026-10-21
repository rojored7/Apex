// US-040 T5: renderiza sus hijos solo si el rol actual tiene la acción.
import type { ReactNode } from "react";
import type { Action } from "./permissions";
import { useCan } from "./useCan";

export interface CanProps {
  action: Action;
  /** Lo que se muestra sin permiso; por defecto nada. */
  fallback?: ReactNode;
  children: ReactNode;
}

export function Can({ action, fallback = null, children }: CanProps) {
  return <>{useCan(action) ? children : fallback}</>;
}
