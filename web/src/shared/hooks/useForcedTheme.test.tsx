// US-062 T3: el layout fija data-theme en <html> mientras está montado y deja el valor
// anterior al desmontar (riesgo del desglose: no dejar el panel en oscuro).
import { renderHook } from "@testing-library/react";
import { useForcedTheme, type ForcedTheme } from "./useForcedTheme";

afterEach(() => {
  delete document.documentElement.dataset.theme;
});

describe("useForcedTheme", () => {
  it.each<[ForcedTheme, string | undefined]>([
    ["dark", "dark"],
    ["light", "light"],
    ["system", undefined],
  ])("%s fija %s y restaura el valor previo", (theme, expected) => {
    document.documentElement.dataset.theme = theme === "light" ? "dark" : "light";
    const before = document.documentElement.dataset.theme;
    const { unmount } = renderHook(() => {
      useForcedTheme(theme);
    });

    expect(document.documentElement.dataset.theme).toBe(expected);
    unmount();
    expect(document.documentElement.dataset.theme).toBe(before);
  });

  it("sin valor previo, al desmontar deja <html> sin atributo", () => {
    const { unmount } = renderHook(() => {
      useForcedTheme("dark");
    });
    unmount();

    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("cambiar el tema forzado re-aplica sin perder el valor original", () => {
    document.documentElement.dataset.theme = "light";
    const { rerender, unmount } = renderHook(({ theme }: { theme: ForcedTheme }) => {
      useForcedTheme(theme);
    }, { initialProps: { theme: "dark" } });

    rerender({ theme: "system" });
    expect(document.documentElement.dataset.theme).toBeUndefined();
    unmount();
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
