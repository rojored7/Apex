// US-067 T3: épicas del front que se habilitan por versión. Una ruta o una entrada del menú
// cuya feature no está habilitada no existe para el usuario (404 y fuera del menú).
// `system` de 05_service_design.md se parte en users, audit, settings y crypto porque se
// habilitan en versiones distintas.

export const FEATURES = [
  "auth",
  "dashboard",
  "members",
  "plans",
  "memberships",
  "payments",
  "users",
  "audit",
  "settings",
  "crypto",
  "classes",
  "wods",
  "results",
  "athletes",
  "notifications",
  "portal",
  "tv",
] as const;

export type Feature = (typeof FEATURES)[number];

/** Una ruta (o entrada del menú) está habilitada si no declara feature o si la suya lo está. */
export function isRouteEnabled(route: { feature?: Feature | undefined }, enabled: ReadonlySet<Feature>): boolean {
  return route.feature === undefined || enabled.has(route.feature);
}

/** Features del Sprint 2 (decisión 25 del blueprint), membresías desde S3-F3, pagos desde S3-F4 (D36) y auditoría desde S4A-F1 (S4A-D30). */
export const ENABLED_FEATURES: ReadonlySet<Feature> = new Set<Feature>([
  "auth",
  "dashboard",
  "members",
  "plans",
  "memberships",
  "payments",
  "users",
  "audit",
  "settings",
]);
