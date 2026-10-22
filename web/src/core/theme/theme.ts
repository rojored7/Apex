// US-068 T3: tema de la app.
// - El tema solo cambia variables: tokens.css redefine los colores bajo data-theme="dark" o
//   prefers-color-scheme, y ningún componente duplica estilos por tema (criterio 2).
// - Zonas (DESIGN.md, "Temas"): el panel es claro por defecto y recuerda la elección; el
//   portal sigue al teléfono; la tablet del box y la TV fuerzan el oscuro (useForcedTheme).
// - La preferencia se guarda en localStorage con la clave apex.theme; si el almacenamiento no
//   está disponible o lanza (modo privado, sitio bloqueado), el tema sigue en memoria y nada
//   se rompe (criterio 3). No es un dato sensible (revisión de seguridad del diseño).
import { useSyncExternalStore } from "react";
import { useForcedTheme } from "../../shared/hooks/useForcedTheme";

export type Theme = "light" | "dark";
export type ZoneDefault = Theme | "system";

export const THEME_STORAGE_KEY = "apex.theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

type StorageGetter = () => Storage | null;

const browserStorage: StorageGetter = () => (typeof window === "undefined" ? null : window.localStorage);

function isTheme(value: unknown): value is Theme {
  return value === "light" || value === "dark";
}

export function resolveTheme(stored: Theme | null, zoneDefault: ZoneDefault, prefersDark: boolean): Theme {
  if (stored) return stored;
  if (zoneDefault === "system") return prefersDark ? "dark" : "light";
  return zoneDefault;
}

export function readStoredTheme(getStorage: StorageGetter = browserStorage): Theme | null {
  try {
    const value = getStorage()?.getItem(THEME_STORAGE_KEY);
    return isTheme(value) ? value : null;
  } catch {
    return null;
  }
}

/** true si quedó guardado; false si no hay almacenamiento o lanzó. */
export function writeStoredTheme(theme: Theme, getStorage: StorageGetter = browserStorage): boolean {
  try {
    const storage = getStorage();
    if (!storage) return false;
    storage.setItem(THEME_STORAGE_KEY, theme);
    return true;
  } catch {
    return false;
  }
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches;
}

/** Preferencia elegida en esta pestaña; `undefined` mientras no se ha leído el almacenamiento. */
let chosen: Theme | null | undefined;
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) listener();
}

function chosenTheme(): Theme | null {
  chosen ??= readStoredTheme();
  return chosen;
}

export function getTheme(zoneDefault: ZoneDefault = "light"): Theme {
  return resolveTheme(chosenTheme(), zoneDefault, systemPrefersDark());
}

export function setTheme(theme: Theme): void {
  chosen = theme;
  writeStoredTheme(theme);
  notify();
}

export function toggleTheme(): void {
  setTheme(getTheme() === "dark" ? "light" : "dark");
}

function onStorage(event: StorageEvent): void {
  if (event.key !== THEME_STORAGE_KEY) return;
  chosen = readStoredTheme();
  notify();
}

/** Avisa cuando cambia la elección, la preferencia del sistema u otra pestaña guarda otra. */
export function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener);
  const media = typeof window.matchMedia === "function" ? window.matchMedia(DARK_QUERY) : null;
  media?.addEventListener("change", listener);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    media?.removeEventListener("change", listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function useTheme(zoneDefault: ZoneDefault = "light"): Theme {
  return useSyncExternalStore(
    subscribeTheme,
    () => getTheme(zoneDefault),
    () => resolveTheme(null, zoneDefault, false),
  );
}

/** Tema del panel: claro por defecto, aplicado a <html> mientras el panel está montado. */
export function usePanelTheme(): Theme {
  const theme = useTheme("light");
  useForcedTheme(theme);
  return theme;
}

/** Solo pruebas: olvida la elección en memoria para volver a leer el almacenamiento. */
export function resetThemeForTests(): void {
  chosen = undefined;
  notify();
}
