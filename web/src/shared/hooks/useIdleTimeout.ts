// S7-F4 · S7-D24: llama `onIdle` cuando pasan `ms` sin que nadie toque la pantalla (puntero, teclado o toque).
// Cada gesto reinicia la cuenta. Con `enabled` en falso no escucha nada.
import { useEffect, useRef } from "react";

const ACTIVITY_EVENTS = ["pointerdown", "pointermove", "keydown", "touchstart", "wheel"] as const;

export function useIdleTimeout(ms: number, onIdle: () => void, enabled: boolean): void {
  const latest = useRef(onIdle);
  useEffect(() => {
    latest.current = onIdle;
  }, [onIdle]);

  useEffect(() => {
    if (!enabled) return undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const arm = (): void => {
      if (timer !== undefined) clearTimeout(timer);
      timer = setTimeout(() => {
        latest.current();
      }, ms);
    };
    arm();
    for (const name of ACTIVITY_EVENTS) document.addEventListener(name, arm, { passive: true });
    return () => {
      if (timer !== undefined) clearTimeout(timer);
      for (const name of ACTIVITY_EVENTS) document.removeEventListener(name, arm);
    };
  }, [ms, enabled]);
}
