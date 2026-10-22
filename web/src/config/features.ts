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

/** Features del Sprint 2 (decisión 25 del blueprint). */
export const ENABLED_FEATURES: ReadonlySet<Feature> = new Set<Feature>([
  "auth",
  "dashboard",
  "members",
  "plans",
  "users",
  "settings",
]);
