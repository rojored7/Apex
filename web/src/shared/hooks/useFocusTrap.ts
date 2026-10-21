// US-065 T1: trampa de foco para diálogos (SidePanel, ConfirmModal).
// - Al activarse guarda el elemento que tenía el foco, enfoca el control inicial (o el
//   primero, o el propio contenedor) y bloquea el desplazamiento del body.
// - Tab y Mayús+Tab ciclan dentro del contenedor; Escape llama a onEscape.
// - Con trampas anidadas (un ConfirmModal sobre un SidePanel) solo la de arriba responde.
// - Al desactivarse devuelve el foco al que abrió y libera el body si era la última.
import { useEffect, useRef, type RefObject } from "react";

export interface FocusTrapOptions {
  onEscape?: (() => void) | undefined;
  /** Control que recibe el foco al abrir; por defecto el primero enfocable. */
  initialFocusRef?: RefObject<HTMLElement | null> | undefined;
}

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

/** Pila de trampas activas; la última es la que responde al teclado. */
const stack: symbol[] = [];
let previousOverflow = "";

function lockBody(): void {
  if (stack.length === 1) {
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
}

function unlockBody(): void {
  if (stack.length === 0) document.body.style.overflow = previousOverflow;
}

function focusables(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE));
}

function cycleTab(event: KeyboardEvent, container: HTMLElement): void {
  const items = focusables(container);
  const first = items[0];
  const last = items.at(-1);
  if (!first || !last) {
    event.preventDefault();
    container.focus();
    return;
  }
  const current = document.activeElement;
  const inside = current instanceof Node && container.contains(current);
  if (event.shiftKey && (!inside || current === first)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (!inside || current === last)) {
    event.preventDefault();
    first.focus();
  }
}

export function useFocusTrap<T extends HTMLElement>(active: boolean, options: FocusTrapOptions = {}): RefObject<T | null> {
  const containerRef = useRef<T>(null);
  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  });

  useEffect(() => {
    const container = containerRef.current;
    if (!active || !container) return undefined;

    const id = Symbol("focus-trap");
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    stack.push(id);
    lockBody();

    const initial = optionsRef.current.initialFocusRef?.current ?? focusables(container)[0] ?? container;
    initial.focus();

    const onKeyDown = (event: KeyboardEvent): void => {
      if (stack.at(-1) !== id) return;
      if (event.key === "Tab") cycleTab(event, container);
      else if (event.key === "Escape") {
        event.preventDefault();
        optionsRef.current.onEscape?.();
      }
    };
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      stack.splice(stack.indexOf(id), 1);
      unlockBody();
      if (opener?.isConnected) opener.focus();
    };
  }, [active]);

  return containerRef;
}
