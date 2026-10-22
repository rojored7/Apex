// US-062 T3: un layout fija el tema de <html> mientras está montado.
// - "dark" y "light" ponen data-theme; "system" lo quita para que tokens.css siga a
//   prefers-color-scheme (portal del socio, DESIGN.md "Temas").
// - Al desmontar (o al cambiar de tema) deja el valor que había antes, para que un layout
//   de gimnasio o de TV no deje el panel en oscuro.
import { useEffect } from "react";

export type ForcedTheme = "dark" | "light" | "system";

export function useForcedTheme(theme: ForcedTheme): void {
  useEffect(() => {
    const root = document.documentElement;
    const previous = root.dataset.theme;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
    return () => {
      if (previous === undefined) delete root.dataset.theme;
      else root.dataset.theme = previous;
    };
  }, [theme]);
}
