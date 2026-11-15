// S7-F4 · S7-D24 · S7-D41 (H-2): el modo tablet lo manda el servidor. La sesión trae `kioskPath` (POST /auth/kiosk, GET /auth/me);
// aquí solo se reconoce la ruta del check-in y se deriva el modo de la sesión. Nada en sessionStorage ni en memoria propia.
import type { SessionUser } from "../core/auth";

/** La ruta del check-in (la que implica entrar al modo tablet). */
export const CHECKIN_PATH = /^\/clases\/[^/]+\/checkin\/?$/;

/** El modo tablet rige mientras la sesión tenga la marca del servidor. */
export function isTabletSession(user: SessionUser | null): boolean {
  return user?.kioskPath != null;
}
