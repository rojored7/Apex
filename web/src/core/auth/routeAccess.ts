// US-053 T3 y S2-D23: acceso por ruta con la matriz de US-040 y la tabla única de rutas.
// - canAccessRoute(role, path): la ruta existe en la tabla y su acceso lo permite el rol.
// - homeFor(role): "/mi" si el rol entra al portal (can(role, "portal.view")), "/" para el
//   resto del equipo y "/login" sin sesión. Ningún literal de rol (condición 6).
// - safeNext(next, role): solo rutas internas que empiezan por una sola "/", sin "\" ni
//   caracteres de control (L-5), no públicas y permitidas para el rol; si no, null.
// Las guardas son comodidad: cada endpoint vuelve a verificar el rol (RN-15).
import { matchPath } from "react-router";
import { ROUTE_TABLE, type RouteAccess, type RouteDef } from "../../config/routeTable";
import { can, type Role } from "./permissions";

export const CHANGE_PASSWORD_PATH = "/cambiar-clave";
export const LOGIN_PATH = "/login";
export const PANEL_HOME = "/";
export const PORTAL_HOME = "/mi";

const MAX_NEXT_LENGTH = 2048;
const BASE = "http://apex.invalid";
// eslint-disable-next-line no-control-regex -- L-5: se rechazan justamente los caracteres de control.
const UNSAFE_CHARS = /[\\\u0000-\u001f\u007f]/;

function pathnameOf(path: string): string {
  const cut = path.search(/[?#]/);
  return cut === -1 ? path : path.slice(0, cut);
}

/** Definición de la tabla que corresponde a una ruta concreta (sin query ni hash). */
export function findRoute(path: string): RouteDef | null {
  const pathname = pathnameOf(path);
  // Las rutas estáticas ganan a las dinámicas (/socios/nuevo frente a /socios/:id).
  const statics = ROUTE_TABLE.filter((r) => !r.path.includes(":"));
  const dynamics = ROUTE_TABLE.filter((r) => r.path.includes(":"));
  for (const def of [...statics, ...dynamics]) {
    if (matchPath({ path: def.path, end: true }, pathname)) return def;
  }
  return null;
}

/** ¿Este rol cumple este acceso? `session` exige cualquier rol; una acción, la matriz. */
export function canAccess(role: Role | null, access: RouteAccess): boolean {
  if (access === "public") return true;
  if (access === "session") return role !== null;
  return can(role, access);
}

export function canAccessRoute(role: Role | null, path: string): boolean {
  const def = findRoute(path);
  return def !== null && canAccess(role, def.access);
}

export function homeFor(role: Role | null): string {
  if (role === null) return LOGIN_PATH;
  return can(role, "portal.view") ? PORTAL_HOME : PANEL_HOME;
}

export function safeNext(next: string | null | undefined, role: Role | null): string | null {
  if (typeof next !== "string" || next.length === 0 || next.length > MAX_NEXT_LENGTH) return null;
  if (!next.startsWith("/") || next.startsWith("//") || UNSAFE_CHARS.test(next)) return null;
  let url: URL;
  try {
    url = new URL(next, BASE);
  } catch {
    return null;
  }
  if (url.origin !== BASE) return null;
  const def = findRoute(url.pathname);
  if (!def || def.access === "public" || !canAccess(role, def.access)) return null;
  return `${url.pathname}${url.search}${url.hash}`;
}
