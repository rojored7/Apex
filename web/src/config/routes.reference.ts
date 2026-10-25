// US-067 T3 y S2-D23: oráculo escrito a mano desde docs/design/ROUTES.md (y `/cambiar-clave`,
// S2-D18). No lo importa la app: solo src/routes.test.ts lo compara con routeTable.ts. Si
// cambia ROUTES.md, se cambia aquí a mano y la prueba obliga a cambiar la tabla.
// Acceso: "public" (sin sesión), "session" (cualquier rol con sesión) o la acción de la
// matriz de US-040 que ROUTES.md ("Permisos") asigna a la pantalla.
import type { RouteAccess, RouteLayout } from "./routeTable";
import type { Feature } from "./features";

export interface ReferenceRoute {
  path: string;
  feature: Feature;
  access: RouteAccess;
  layout: RouteLayout;
  /** S3-F3 (E3, E14): ruta del padre de una ruta hija (pestañas de la ficha, F1 y F7). */
  parent?: string;
}

const r = (path: string, feature: Feature, access: RouteAccess, layout: RouteLayout): ReferenceRoute => ({ path, feature, access, layout });

export const REFERENCE_ROUTES: readonly ReferenceRoute[] = [
  // Acceso (sin sesión)
  r("/login", "auth", "public", "access"),
  r("/recuperar", "auth", "public", "access"),
  r("/restablecer/:token", "auth", "public", "access"),
  r("/tv", "tv", "public", "tv"),
  // DESIGN-GAP (S2-D18): cambio de contraseña obligatorio; sin pantalla propia en screens/.
  r("/cambiar-clave", "auth", "session", "access"),
  // Panel: Inicio
  r("/", "dashboard", "dashboard.view", "panel"),
  // Socios
  r("/socios", "members", "members.view", "panel"),
  r("/socios/nuevo", "members", "members.create", "panel"),
  r("/socios/:id", "members", "members.view", "panel"),
  // S3-F1 (E14): la pestaña "Datos" es la hija índice de la ficha (path vacío, mismo acceso).
  { path: "", feature: "members", access: "members.view", layout: "panel", parent: "/socios/:id" },
  // S3-F7 (S3-D65, E3): las pestañas Membresías y Pagos son hijas con su feature y su acceso.
  { path: "/socios/:id/membresias", feature: "memberships", access: "memberships.view", layout: "panel", parent: "/socios/:id" },
  { path: "/socios/:id/pagos", feature: "payments", access: "payments.view", layout: "panel", parent: "/socios/:id" },
  r("/socios/:id/editar", "members", "members.update", "panel"),
  // Planes (solo admin)
  r("/planes", "plans", "plans.view", "panel"),
  // Membresías
  r("/membresias", "memberships", "memberships.view", "panel"),
  r("/membresias/vender", "memberships", "memberships.sell", "panel"),
  // Pagos
  r("/pagos", "payments", "payments.view", "panel"),
  // Clases
  r("/clases", "classes", "classes.view", "panel"),
  r("/clases/horario", "classes", "classes.schedule", "panel"),
  r("/clases/:id/checkin", "classes", "classes.view", "gym"),
  r("/clases/asistencia", "classes", "classes.view", "panel"),
  // Movimientos
  r("/movimientos", "wods", "movements.view", "panel"),
  // WODs
  r("/wods", "wods", "wods.view", "panel"),
  r("/wods/nuevo", "wods", "wods.view", "panel"),
  r("/wods/:id/editar", "wods", "wods.view", "panel"),
  r("/wods/:id", "wods", "wods.view", "panel"),
  // Resultados
  r("/clases/:id/resultados", "results", "results.record", "gym"),
  // Atleta
  r("/socios/:id/atleta", "athletes", "athletes.view", "panel"),
  // Avisos
  r("/avisos/hoy", "notifications", "notifications.view", "panel"),
  r("/avisos/reglas", "notifications", "notifications.view", "panel"),
  r("/avisos/historial", "notifications", "notifications.view", "panel"),
  // Sistema (solo admin)
  r("/sistema/usuarios", "users", "users.manage", "panel"),
  r("/sistema/auditoria", "audit", "audit.view", "panel"),
  r("/sistema/llaves", "crypto", "crypto.manage", "panel"),
  r("/sistema/configuracion", "settings", "settings.manage", "panel"),
  // Portal del socio
  r("/mi", "portal", "me.home.view", "portal"),
  r("/mi/pagos", "portal", "me.payments.view", "portal"),
  r("/mi/wods", "portal", "me.wods.view", "portal"),
  r("/mi/progreso", "portal", "me.progress.view", "portal"),
  r("/mi/datos", "portal", "me.profile.update", "portal"),
  r("/mi/avisos", "portal", "me.notifications.manage", "portal"),
];
