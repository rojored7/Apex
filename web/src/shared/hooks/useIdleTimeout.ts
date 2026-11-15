// S7-F4 · S7-D24: llama `onIdle` cuando pasan `ms` sin que nadie toque la pantalla (puntero, teclado o toque).
// Cada gesto reinicia la cuenta. Con `enabled` en falso no escucha nada.
// S7-F4b (LOW b): además del temporizador guarda el instante límite y lo revisa al volver a verse la pestaña: un navegador
// que duerme una tablet en reposo congela los temporizadores y, sin esa revisión, la sesión seguiría abierta.
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
    let deadline = Date.now() + ms;
    let fired = false;
    const fire = (): void => {
      if (fired) return;
      fired = true;
      latest.current();
    };
    const arm = (): void => {
      if (fired) return;
      if (timer !== undefined) clearTimeout(timer);
      deadline = Date.now() + ms;
      timer = setTimeout(fire, ms);
    };
    const onVisible = (): void => {
      if (document.visibilityState === "visible" && Date.now() >= deadline) fire();
    };
    arm();
    for (const name of ACTIVITY_EVENTS) document.addEventListener(name, arm, { passive: true });
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      if (timer !== undefined) clearTimeout(timer);
      for (const name of ACTIVITY_EVENTS) document.removeEventListener(name, arm);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [ms, enabled]);
}
