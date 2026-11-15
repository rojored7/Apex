// S7-F4 · S7-D24 · S7-D41 (H-2): el modo tablet lo manda el servidor. La sesión trae `kioskPath` (POST /auth/kiosk, GET /auth/me);
// aquí solo se reconocen las rutas de la tablet y se deriva el modo de la sesión. Nada en sessionStorage ni en memoria propia.
// S8-F4 · S8-D27: son dos rutas de la clase, el check-in y el registro de resultados (S8-D15).
import type { SessionUser } from "../core/auth";

/** Las rutas de la tablet (las que implican entrar al modo tablet). */
export const TABLET_PATH = /^\/clases\/[^/]+\/(checkin|resultados)\/?$/;

/** El modo tablet rige mientras la sesión tenga la marca del servidor. */
export function isTabletSession(user: SessionUser | null): boolean {
  return user?.kioskPath != null;
}
