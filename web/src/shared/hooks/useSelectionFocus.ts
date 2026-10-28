// Fase 4 del Sprint 3 (M3): a dónde va el foco cuando cambia la selección de un buscador (la venta y
// el panel de pagos). El control que tenía el foco desaparece: al elegir, el foco va al primer botón
// de la selección ("Cambiar socio"); al cambiar, al buscador (revisión S3-F3, MEDIUM 3).
import { useEffect, useRef, type RefObject } from "react";

export interface SelectionFocus {
  selectedRef: RefObject<HTMLDivElement | null>;
  searchRef: RefObject<HTMLInputElement | null>;
  /** Llamar antes de elegir: el foco irá al botón de la selección. */
  focusChangeNext: () => void;
  /** Llamar antes de quitar la selección: el foco irá al buscador. */
  focusSearchNext: () => void;
}

export function useSelectionFocus(selection: unknown): SelectionFocus {
  const selectedRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const next = useRef<"change" | "search" | null>(null);
  useEffect(() => {
    if (next.current === "change") selectedRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    if (next.current === "search") searchRef.current?.focus();
    next.current = null;
  }, [selection]);
  return {
    selectedRef,
    searchRef,
    focusChangeNext: () => {
      next.current = "change";
    },
    focusSearchNext: () => {
      next.current = "search";
    },
  };
}
