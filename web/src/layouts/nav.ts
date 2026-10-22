// US-061 T2: catálogo del menú lateral del panel y su filtro puro.
// - Grupos de DESIGN.md: Inicio · Hoy · Gestión · Entrenamiento · Avisos · Sistema.
// - Una entrada aparece si su feature está habilitada y el rol tiene su acción en la matriz
//   de US-040 (can); no hay listas de roles aquí (RN-15: el front oculta, el API verifica).
// - "Hoy" son tres enlaces a pantallas que ya existen (Q25), sin ruta propia, y solo se
//   muestra cuando sus tres épicas están habilitadas.
// - Los grupos vacíos se omiten; para el rol member el resultado es vacío porque ninguna
//   acción del panel es suya (el socio usa PortalLayout).
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
import type { Feature } from "../config/features";
import { can, type Action, type Role } from "../core/auth";

export type NavGroupId = "inicio" | "hoy" | "gestion" | "entrenamiento" | "avisos" | "sistema";

export interface NavItem {
  label: string;
  to: string;
  feature: Feature;
  action: Action;
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

const item = (group: NavGroupId, label: string, to: string, feature: Feature, action: Action, icon: LucideIcon): NavItem =>
  Object.freeze({ group, label, to, feature, action, icon });

export const NAV_CATALOG: readonly NavItem[] = Object.freeze([
  item("inicio", "Inicio", "/", "dashboard", "dashboard.view", House),
  item("hoy", "Clases de hoy", "/clases?dia=hoy", "classes", "classes.view", CalendarClock),
  item("hoy", "WOD de hoy", "/wods?dia=hoy", "wods", "wods.view", Timer),
  item("hoy", "Por avisar hoy", "/avisos/hoy", "notifications", "notifications.view", Bell),
  item("gestion", "Socios", "/socios", "members", "members.view", Users),
  item("gestion", "Membresías", "/membresias", "memberships", "memberships.view", ClipboardList),
  item("gestion", "Pagos", "/pagos", "payments", "payments.view", CreditCard),
  item("gestion", "Planes", "/planes", "plans", "plans.view", Tags),
  item("entrenamiento", "Clases", "/clases", "classes", "classes.view", CalendarDays),
  item("entrenamiento", "WODs", "/wods", "wods", "wods.view", Dumbbell),
  item("entrenamiento", "Movimientos", "/movimientos", "wods", "movements.view", ListChecks),
  item("avisos", "Reglas y plantillas", "/avisos/reglas", "notifications", "notifications.view", Bell),
  item("avisos", "Historial de envíos", "/avisos/historial", "notifications", "notifications.view", History),
  item("sistema", "Usuarios y roles", "/sistema/usuarios", "users", "users.manage", UserCog),
  item("sistema", "Auditoría", "/sistema/auditoria", "audit", "audit.view", ShieldCheck),
  item("sistema", "Llaves de cifrado", "/sistema/llaves", "crypto", "crypto.manage", KeyRound),
  item("sistema", "Configuración", "/sistema/configuracion", "settings", "settings.manage", Settings),
]);

function isVisible(entry: NavItem, role: Role | null, enabled: ReadonlySet<Feature>): boolean {
  if (!enabled.has(entry.feature) || !can(role, entry.action)) return false;
  return entry.group !== "hoy" || HOY_FEATURES.every((f) => enabled.has(f));
}

/** Menú del panel para un rol y las features habilitadas, agrupado y sin grupos vacíos. */
export function buildNavItems(role: Role | null, enabled: ReadonlySet<Feature>): NavGroup[] {
  const visible = NAV_CATALOG.filter((entry) => isVisible(entry, role, enabled));
  return GROUPS.map((group) => ({ ...group, items: visible.filter((entry) => entry.group === group.id) })).filter(
    (group) => group.items.length > 0,
  );
}
