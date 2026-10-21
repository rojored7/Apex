// US-063: consulta de medios para cambiar la tabla por tarjetas en celular (DESIGN.md:
// "En celular se convierte en lista de tarjetas"). Sin matchMedia (jsdom) responde falso.
import { useCallback, useSyncExternalStore } from "react";

/** Celular: por debajo de 768 px. */
export const MOBILE_QUERY = "(width < 768px)";

function mediaList(query: string): MediaQueryList | null {
  return typeof window.matchMedia === "function" ? window.matchMedia(query) : null;
}

export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (notify: () => void) => {
      const list = mediaList(query);
      list?.addEventListener("change", notify);
      return () => {
        list?.removeEventListener("change", notify);
      };
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => mediaList(query)?.matches ?? false,
    () => false,
  );
}
