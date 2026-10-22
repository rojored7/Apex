// S2-D23 (US-067, US-053): única tabla de rutas del front. La consumen routes.tsx (árbol de
// React Router), core/auth/routeAccess.ts (guardas, homeFor, safeNext) y, a través de este,
// layouts/nav.ts. src/config/routes.reference.ts es su oráculo escrito a mano desde
// docs/design/ROUTES.md y src/routes.test.ts compara las dos.
// - `access`: "public" (sin sesión), "session" (cualquier rol con sesión) o la acción de la
//   matriz de US-040. El front oculta; cada endpoint vuelve a verificar el rol (RN-15).
// - `load`: la página se descarga solo al visitar la ruta (US-067, criterio 3).
// - `pending`: la pantalla llega en otro slice de este sprint (F3 a F7); la ruta existe, pasa
//   por las guardas y muestra "Disponible pronto". Cada slice cambia `pending` por `load`.
// - Sin `load` ni `pending` (versiones futuras, o /socios/:id hasta S3-F1, S2-D34) la ruta no
//   se registra y da 404 sin descargar nada.
import type { ComponentType } from "react";
import type { Action } from "../core/auth/permissions";
import type { Feature } from "./features";

export type RouteLayout = "access" | "panel" | "portal" | "gym" | "tv";
/** `public`: sin sesión; `session`: cualquier rol con sesión; si no, la acción de la matriz. */
export type RouteAccess = "public" | "session" | Action;

export interface RouteDef {
  path: string;
  title: string;
  feature?: Feature;
  access: RouteAccess;
  layout: RouteLayout;
  /** Página diferida; sin `load` y sin `pending` la ruta no se registra (404). */
  load?: () => Promise<{ default: ComponentType }>;
  /** La pantalla llega en otro slice de este sprint: se muestra "Disponible pronto". */
  pending?: boolean;
}

type Extra = Pick<RouteDef, "load" | "pending">;

const route = (path: string, title: string, feature: Feature, access: RouteAccess, layout: RouteLayout, extra: Extra = {}): RouteDef =>
  Object.freeze({ path, title, feature, access, layout, ...extra });


export const ROUTE_TABLE: readonly RouteDef[] = Object.freeze([
  // Acceso (sin sesión): login (S2-F3), recuperación y restablecimiento (S2-F4a).
  route("/login", "Iniciar sesión", "auth", "public", "access", { load: () => import("../features/auth/pages/LoginPage") }),
  route("/recuperar", "Olvidé mi contraseña", "auth", "public", "access", { load: () => import("../features/auth/pages/ForgotPage") }),
  route("/restablecer/:token", "Nueva contraseña", "auth", "public", "access", { load: () => import("../features/auth/pages/ResetPage") }),
  route("/tv", "Pantalla del gimnasio", "tv", "public", "tv"),
  // DESIGN-GAP (S2-D18, S2-F4a): cambio de contraseña obligatorio con la tarjeta de ResetPage; no está
  // en las pantallas de docs/design/screens/.
  route("/cambiar-clave", "Cambiar contraseña", "auth", "session", "access", { load: () => import("../features/auth/pages/ChangePasswordPage") }),

  // Panel. Inicio mínima hasta GET /dashboard (S2-D25).
  route("/", "Inicio", "dashboard", "dashboard.view", "panel", { load: () => import("../features/dashboard/pages/InicioPage") }),
  // S2-F6: lista (US-070) y alta (US-069).
  route("/socios", "Socios", "members", "members.view", "panel", { load: () => import("../features/members/pages/MembersListPage") }),
  route("/socios/nuevo", "Nuevo socio", "members", "members.create", "panel", { load: () => import("../features/members/pages/MemberFormPage") }),
  // S2-D34: la ficha y la edición llegan con S3-B9 y S3-F1; hasta entonces dan 404.
  route("/socios/:id", "Ficha del socio", "members", "members.view", "panel"),
  route("/socios/:id/editar", "Editar socio", "members", "members.update", "panel"),
  route("/socios/:id/atleta", "Perfil del atleta", "athletes", "athletes.view", "panel"),
  // S2-D26: /planes es solo admin en el front. S2-F7: lista (US-079) y alta (US-078).
  route("/planes", "Planes", "plans", "plans.view", "panel", { load: () => import("../features/plans/pages/PlansPage") }),
  route("/membresias", "Membresías", "memberships", "memberships.view", "panel"),
  route("/membresias/vender", "Vender membresía", "memberships", "memberships.sell", "panel"),
  route("/pagos", "Pagos", "payments", "payments.view", "panel"),
  route("/clases", "Clases", "classes", "classes.view", "panel"),
  route("/clases/horario", "Horario", "classes", "classes.schedule", "panel"),
  route("/clases/asistencia", "Asistencia", "classes", "classes.view", "panel"),
  route("/clases/:id/checkin", "Check-in", "classes", "classes.view", "gym"),
  route("/clases/:id/resultados", "Registro de resultados", "results", "results.record", "gym"),
  route("/movimientos", "Movimientos", "wods", "movements.view", "panel"),
  route("/wods", "WODs", "wods", "wods.view", "panel"),
  route("/wods/nuevo", "Nuevo WOD", "wods", "wods.view", "panel"),
  route("/wods/:id", "WOD", "wods", "wods.view", "panel"),
  route("/wods/:id/editar", "Editar WOD", "wods", "wods.view", "panel"),
  route("/avisos/hoy", "Por avisar hoy", "notifications", "notifications.view", "panel"),
  route("/avisos/reglas", "Reglas y plantillas", "notifications", "notifications.view", "panel"),
  route("/avisos/historial", "Historial de envíos", "notifications", "notifications.view", "panel"),
  // S2-F4a: lista y alta; la gestión (editar, bloquear, sesiones, reenviar) llega en S2-F4b.
  route("/sistema/usuarios", "Usuarios y roles", "users", "users.manage", "panel", { load: () => import("../features/system/pages/UsersPage") }),
  route("/sistema/auditoria", "Auditoría", "audit", "audit.view", "panel"),
  route("/sistema/llaves", "Llaves de cifrado", "crypto", "crypto.manage", "panel"),
  // S2-F5: Gimnasio, Privacidad y Membresías (S2-D15).
  route("/sistema/configuracion", "Configuración", "settings", "settings.manage", "panel", { load: () => import("../features/system/pages/ConfigPage") }),

  // Portal del socio (v1.0).
  route("/mi", "Inicio", "portal", "me.home.view", "portal"),
  route("/mi/pagos", "Mis pagos", "portal", "me.payments.view", "portal"),
  route("/mi/wods", "Mis WODs", "portal", "me.wods.view", "portal"),
  route("/mi/progreso", "Mi progreso", "portal", "me.progress.view", "portal"),
  route("/mi/datos", "Mis datos", "portal", "me.profile.update", "portal"),
  route("/mi/avisos", "Mis avisos", "portal", "me.notifications.manage", "portal"),
]);
