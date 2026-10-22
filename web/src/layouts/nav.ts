// US-061 T2 (y S2-F2): catálogo del menú lateral del panel y su filtro puro.
// - Grupos de DESIGN.md: Inicio · Hoy · Gestión · Entrenamiento · Avisos · Sistema.
// - Una entrada aparece si su feature está habilitada (isRouteEnabled) y el rol puede abrir su
//   ruta (canAccessRoute, que usa la matriz de US-040 y config/routeTable.ts): el menú y las
//   guardas deciden con la misma regla. Sin listas de roles (RN-15: el front oculta, el API
//   verifica).
// - "Hoy" son tres enlaces a pantallas que ya existen (Q25), sin ruta propia, y solo se
//   muestra cuando sus tres épicas están habilitadas.
// - Los grupos vacíos se omiten; para el socio el resultado es vacío porque ninguna ruta del
//   panel es suya (usa PortalLayout).
// DESIGN-GAP: Inicio.html trae un grupo "Pantalla" con "Abrir pantalla TV ↗"; la TV se abre
// con un token de Configuración (US-176) y no es una entrada del menú en v0.1.
import {
  Bell,
  CalendarClock,
  CalendarDays,
  ClipboardList,
  CreditCard,
  Dumbbell,
  History,
  House,
  KeyRound,
  ListChecks,
  type LucideIcon,
  Settings,
  ShieldCheck,
  Tags,
  Timer,
  UserCog,
  Users,
} from "lucide-react";
import { isRouteEnabled, type Feature } from "../config/features";
import type { Role } from "../core/auth/permissions";
import { canAccessRoute } from "../core/auth/routeAccess";

export type NavGroupId = "inicio" | "hoy" | "gestion" | "entrenamiento" | "avisos" | "sistema";

export interface NavItem {
  label: string;
  to: string;
  feature: Feature;
  group: NavGroupId;
  icon: LucideIcon;
}

export interface NavGroup {
  id: NavGroupId;
  /** `null`: el grupo no lleva título (Inicio). */
  title: string | null;
  items: readonly NavItem[];
}

const GROUPS: readonly { id: NavGroupId; title: string | null }[] = [
  { id: "inicio", title: null },
  { id: "hoy", title: "Hoy" },
  { id: "gestion", title: "Gestión" },
  { id: "entrenamiento", title: "Entrenamiento" },
  { id: "avisos", title: "Avisos" },
  { id: "sistema", title: "Sistema" },
];

/** El grupo "Hoy" necesita sus tres épicas a la vez (Q25). */
const HOY_FEATURES: readonly Feature[] = ["classes", "wods", "notifications"];

const item = (group: NavGroupId, label: string, to: string, feature: Feature, icon: LucideIcon): NavItem =>
  Object.freeze({ group, label, to, feature, icon });

export const NAV_CATALOG: readonly NavItem[] = Object.freeze([
  item("inicio", "Inicio", "/", "dashboard", House),
  item("hoy", "Clases de hoy", "/clases?dia=hoy", "classes", CalendarClock),
  item("hoy", "WOD de hoy", "/wods?dia=hoy", "wods", Timer),
  item("hoy", "Por avisar hoy", "/avisos/hoy", "notifications", Bell),
  item("gestion", "Socios", "/socios", "members", Users),
  item("gestion", "Membresías", "/membresias", "memberships", ClipboardList),
  item("gestion", "Pagos", "/pagos", "payments", CreditCard),
  item("gestion", "Planes", "/planes", "plans", Tags),
  item("entrenamiento", "Clases", "/clases", "classes", CalendarDays),
  item("entrenamiento", "WODs", "/wods", "wods", Dumbbell),
  item("entrenamiento", "Movimientos", "/movimientos", "wods", ListChecks),
  item("avisos", "Reglas y plantillas", "/avisos/reglas", "notifications", Bell),
  item("avisos", "Historial de envíos", "/avisos/historial", "notifications", History),
  item("sistema", "Usuarios y roles", "/sistema/usuarios", "users", UserCog),
  item("sistema", "Auditoría", "/sistema/auditoria", "audit", ShieldCheck),
  item("sistema", "Llaves de cifrado", "/sistema/llaves", "crypto", KeyRound),
  item("sistema", "Configuración", "/sistema/configuracion", "settings", Settings),
]);

function isVisible(entry: NavItem, role: Role | null, enabled: ReadonlySet<Feature>): boolean {
  if (!isRouteEnabled(entry, enabled) || !canAccessRoute(role, entry.to)) return false;
  return entry.group !== "hoy" || HOY_FEATURES.every((f) => enabled.has(f));
}

/** Menú del panel para un rol y las features habilitadas, agrupado y sin grupos vacíos. */
export function buildNavItems(role: Role | null, enabled: ReadonlySet<Feature>): NavGroup[] {
  const visible = NAV_CATALOG.filter((entry) => isVisible(entry, role, enabled));
  return GROUPS.map((group) => ({ ...group, items: visible.filter((entry) => entry.group === group.id) })).filter(
    (group) => group.items.length > 0,
  );
}
