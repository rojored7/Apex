// S9-F1 (revisión, L6, L7, seguridad L1 y L2): la lógica de un dato en claro que vive poco, en un solo lugar (MaskedValue y MetricField).
// - `arm()` guarda `expiresAt = Date.now() + ttl` y arma un temporizador; `disarm()` lo cancela. `onExpire` enmascara.
// - Mientras `active` (hay un claro a la vista) escucha: la pestaña oculta (visibilitychange a hidden) enmascara; al volver a visible,
//   en `pageshow` o en `focus` enmascara si el plazo ya venció (el equipo estuvo suspendido y el temporizador no disparó); `pageshow`
//   con `persisted` (página restaurada de la caché) enmascara siempre; `pagehide` enmascara de forma síncrona (flushSync) para que el
//   DOM no conserve el valor al congelar la página.
// - Al desmontar o al dejar de estar activo, cancela el temporizador y suelta los oyentes.
import { useCallback, useEffect, useRef } from "react";
import { flushSync } from "react-dom";

/** Tiempo que el dato queda en claro antes de volver a enmascararse. */
export const REVEAL_TTL_MS = 60_000;

export interface TimedReveal {
  /** Empieza a contar el plazo desde ahora (llámala al mostrar el claro). */
  arm: () => void;
  /** Cancela el plazo (llámala al ocultar a mano). */
  disarm: () => void;
}

export function useTimedReveal(active: boolean, onExpire: () => void, ttlMs: number = REVEAL_TTL_MS): TimedReveal {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const expiresAt = useRef(0);
  const expire = useRef(onExpire);
  useEffect(() => {
    expire.current = onExpire;
  }, [onExpire]);

  const disarm = useCallback((): void => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const arm = useCallback((): void => {
    disarm();
    expiresAt.current = Date.now() + ttlMs;
    timer.current = setTimeout(() => {
      timer.current = null;
      expire.current();
    }, ttlMs);
  }, [disarm, ttlMs]);

  useEffect(() => {
    if (!active) return undefined;
    const mask = (): void => {
      disarm();
      expire.current();
    };
    const maskIfDue = (): void => {
      if (Date.now() >= expiresAt.current) mask();
    };
    const onVisibility = (): void => {
      if (document.visibilityState === "hidden") mask();
      else maskIfDue();
    };
    const onPageShow = (event: Event): void => {
      if ((event as PageTransitionEvent).persisted) mask();
      else maskIfDue();
    };
    const onPageHide = (): void => {
      flushSync(mask);
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pageshow", onPageShow);
    window.addEventListener("focus", maskIfDue);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pageshow", onPageShow);
      window.removeEventListener("focus", maskIfDue);
      window.removeEventListener("pagehide", onPageHide);
      disarm();
    };
  }, [active, disarm]);

  return { arm, disarm };
}
