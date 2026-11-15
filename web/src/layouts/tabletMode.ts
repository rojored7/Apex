// S7-F4 · S7-D24 (H-2): la marca del modo tablet. Al entrar a /clases/:id/checkin se marca y, mientras exista, GymLayout corre
// en modo tablet aunque la tablet pase a otra pantalla de la tablet. No es una barrera de seguridad: el api decide los permisos;
// es el límite de la pantalla (sin enlaces al panel, sin revelar datos, salida con contraseña).
// DESIGN-GAP: S7-D24 pide sessionStorage, pero la regla de lint de S4B-D51 lo reserva a src/pages/RouteError.tsx y su lista blanca
// es de esa decisión. La marca vive en memoria del módulo: un F5 en /clases/:id/checkin vuelve a marcarla (la ruta la implica);
// un F5 en otra pantalla de la tablet (resultados, v0.5) la pierde. Si se necesita persistirla, se amplía la lista blanca con S4B-D51.
let active = false;

/** La ruta del check-in (la que implica el modo tablet). */
export const CHECKIN_PATH = /^\/clases\/[^/]+\/checkin\/?$/;

export function isTabletMode(): boolean {
  return active;
}

export function enterTabletMode(): void {
  active = true;
}

export function leaveTabletMode(): void {
  active = false;
}
