// US-068 T1 (criterio 3): el tema se resuelve por zona y preferencia guardada, y un
// localStorage que lanza (modo privado, sitio bloqueado) no rompe nada: cae a la preferencia
// en memoria o a la del sistema.
import { act, cleanup, renderHook } from "@testing-library/react";
import { setViewportWidth } from "../../test/server";
import {
  THEME_STORAGE_KEY,
  applyTheme,
  getTheme,
  readStoredTheme,
  resetThemeForTests,
  resolveTheme,
  setTheme,
  subscribeTheme,
  toggleTheme,
  usePanelTheme,
  useTheme,
  writeStoredTheme,
} from "./theme";

const throwing = (): Storage => {
  throw new DOMException("bloqueado", "SecurityError");
};

function brokenStorage(): Storage {
  const fail = (): never => {
    throw new DOMException("cuota", "QuotaExceededError");
  };
  return { length: 0, clear: fail, getItem: fail, key: fail, removeItem: fail, setItem: fail };
}

function prefersDark(dark: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: dark && query.includes("prefers-color-scheme: dark"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    })),
  );
}

beforeEach(() => {
  localStorage.clear();
  resetThemeForTests();
});

afterEach(() => {
  // L7 (revisión del Sprint 2): desmontar antes de reiniciar; resetThemeForTests avisa a los
  // suscriptores y un hook todavía montado se actualizaría fuera de act(...).
  cleanup();
  vi.unstubAllGlobals();
  delete document.documentElement.dataset.theme;
  localStorage.clear();
  resetThemeForTests();
});

describe("resolveTheme", () => {
  it("la preferencia guardada gana sobre el defecto de la zona", () => {
    expect(resolveTheme("dark", "light", false)).toBe("dark");
    expect(resolveTheme("light", "system", true)).toBe("light");
  });

  it("sin preferencia, el panel es claro aunque el sistema prefiera oscuro", () => {
    expect(resolveTheme(null, "light", true)).toBe("light");
  });

  it("sin preferencia, la zona que sigue al sistema usa prefers-color-scheme", () => {
    expect(resolveTheme(null, "system", true)).toBe("dark");
    expect(resolveTheme(null, "system", false)).toBe("light");
    expect(resolveTheme(null, "dark", false)).toBe("dark");
  });
});

describe("almacenamiento de la preferencia", () => {
  it("lee y escribe apex.theme", () => {
    expect(writeStoredTheme("dark")).toBe(true);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(readStoredTheme()).toBe("dark");
  });

  it("un valor ajeno guardado se ignora", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "morado");
    expect(readStoredTheme()).toBeNull();
  });

  it("si acceder a localStorage lanza, leer da null y escribir no rompe", () => {
    expect(readStoredTheme(throwing)).toBeNull();
    expect(writeStoredTheme("dark", throwing)).toBe(false);
  });

  it("si getItem o setItem lanzan, leer da null y escribir no rompe", () => {
    expect(readStoredTheme(brokenStorage)).toBeNull();
    expect(writeStoredTheme("dark", brokenStorage)).toBe(false);
  });

  it("sin localStorage en el entorno no rompe", () => {
    expect(readStoredTheme(() => null)).toBeNull();
    expect(writeStoredTheme("light", () => null)).toBe(false);
  });
});

describe("tema de la app", () => {
  it("applyTheme fija data-theme en <html>", () => {
    applyTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("el panel arranca en claro y toggleTheme alterna y guarda", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeTheme(listener);

    expect(getTheme()).toBe("light");
    toggleTheme();
    expect(getTheme()).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    toggleTheme();
    expect(getTheme()).toBe("light");
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
  });

  it("con localStorage bloqueado el cambio de tema sigue en memoria", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("bloqueado", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("bloqueado", "SecurityError");
    });
    try {
      setTheme("dark");
      expect(getTheme()).toBe("dark");
    } finally {
      vi.restoreAllMocks();
    }
  });

  it("recupera la preferencia guardada en otra sesión", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    resetThemeForTests();

    expect(getTheme()).toBe("dark");
  });

  it("la zona que sigue al sistema responde a prefers-color-scheme", () => {
    prefersDark(true);
    expect(getTheme("system")).toBe("dark");
    prefersDark(false);
    expect(getTheme("system")).toBe("light");
  });

  it("un cambio guardado desde otra pestaña (evento storage) se refleja", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current).toBe("light");

    act(() => {
      localStorage.setItem(THEME_STORAGE_KEY, "dark");
      window.dispatchEvent(new StorageEvent("storage", { key: THEME_STORAGE_KEY, newValue: "dark" }));
    });
    expect(result.current).toBe("dark");
  });

  it("usePanelTheme aplica el tema mientras el panel está montado y lo restaura al salir", () => {
    setViewportWidth(1280);
    document.documentElement.dataset.theme = "dark";
    const { result, unmount } = renderHook(() => usePanelTheme());

    expect(result.current).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    act(() => {
      toggleTheme();
    });
    expect(document.documentElement.dataset.theme).toBe("dark");
    unmount();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
