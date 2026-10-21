// US-063: espera de 300 ms para la búsqueda y consulta de ancho para la vista de tarjetas.
import { act, renderHook } from "@testing-library/react";
import { useDebouncedValue } from "./useDebouncedValue";
import { MOBILE_QUERY, useMediaQuery } from "./useMediaQuery";

describe("useDebouncedValue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("entrega el valor solo después de la espera y reinicia la espera con cada cambio", () => {
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 300), { initialProps: { value: "p" } });

    expect(result.current).toBe("p");
    rerender({ value: "pé" });
    act(() => {
      vi.advanceTimersByTime(200);
    });
    rerender({ value: "pér" });
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current).toBe("p");
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current).toBe("pér");
  });
});

describe("useMediaQuery", () => {
  type Listener = (event: { matches: boolean }) => void;

  function stubMatchMedia(initial: boolean) {
    const listeners = new Set<Listener>();
    const mql = {
      matches: initial,
      addEventListener: (_: string, l: Listener) => listeners.add(l),
      removeEventListener: (_: string, l: Listener) => listeners.delete(l),
    };
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => mql),
    );
    return {
      change(matches: boolean) {
        mql.matches = matches;
        for (const l of listeners) l({ matches });
      },
      listeners,
    };
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("la consulta de celular es por debajo de 768 px", () => {
    expect(MOBILE_QUERY).toBe("(width < 768px)");
  });

  it("sin matchMedia (jsdom) responde falso", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(renderHook(() => useMediaQuery(MOBILE_QUERY)).result.current).toBe(false);
  });

  it("sigue los cambios de la consulta y se desuscribe al desmontar", () => {
    const media = stubMatchMedia(true);
    const { result, unmount } = renderHook(() => useMediaQuery(MOBILE_QUERY));

    expect(result.current).toBe(true);
    act(() => {
      media.change(false);
    });
    expect(result.current).toBe(false);
    unmount();
    expect(media.listeners.size).toBe(0);
  });
});
