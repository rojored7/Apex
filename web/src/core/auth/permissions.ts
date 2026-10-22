// US-040: matriz única de permisos del front (ROUTES.md, "Permisos"; RN-15). El front solo
// oculta: cada acción tiene detrás un endpoint con require_role (US-034) que vuelve a
// verificar. Un cambio aquí debe acompañar al rol del endpoint correspondiente.
// Este archivo y session.ts son los únicos lugares donde se compara un rol con un literal
// (regla en tests/lint/restricted-config.ts).

export const ROLES = ["admin", "coach", "member"] as const;
export type Role = (typeof ROLES)[number];

/**
 * S2-F4a (L-2): roles que se crean desde Usuarios (cuentas del equipo; el socio entra con el
 * portal), en el orden del select, y el que se propone por defecto (el de menos permisos).
 */
export const STAFF_ROLES = Object.freeze(["coach", "admin"] as const satisfies readonly Role[]);
export type StaffRole = (typeof STAFF_ROLES)[number];
export const DEFAULT_STAFF_ROLE: StaffRole = "coach";

const ADMIN: readonly Role[] = ["admin"];
const STAFF: readonly Role[] = ["admin", "coach"];
const MEMBER: readonly Role[] = ["member"];

const TABLE = {
  // Solo admin (N-20: documento y reactivación; Q15 y N-29: exportaciones de v0.2).
  "members.delete": ADMIN,
  "members.reactivate": ADMIN,
  "members.document.update": ADMIN,
  "members.export": ADMIN,
  "plans.view": ADMIN,
  "plans.manage": ADMIN,
  "memberships.cancel": ADMIN,
  "payments.void": ADMIN,
  "payments.export": ADMIN,
  "audit.view": ADMIN,
  "users.manage": ADMIN,
  "settings.manage": ADMIN,
  "crypto.manage": ADMIN,
  "notifications.rules.edit": ADMIN,
  // Admin y coach (Q6 reveal, Q7 congelar, Q8 borrar asistencia; Q25: "Hoy" no es acción).
  "dashboard.view": STAFF,
  "members.view": STAFF,
  "members.create": STAFF,
  "members.update": STAFF,
  "members.reveal": STAFF,
  "members.history.view": STAFF,
  "memberships.view": STAFF,
  "memberships.sell": STAFF,
  "memberships.freeze": STAFF,
  "payments.view": STAFF,
  "payments.register": STAFF,
  "classes.view": STAFF,
  "attendance.delete": STAFF,
  "wods.view": STAFF,
  "movements.view": STAFF,
  "results.record": STAFF,
  "athletes.view": STAFF,
  "notifications.view": STAFF,
  "account.manage": STAFF,
  // Solo el socio, en /mi/*.
  "me.home.view": MEMBER,
  "me.payments.view": MEMBER,
  "me.wods.view": MEMBER,
  "me.results.submit": MEMBER,
  "me.progress.view": MEMBER,
  "me.profile.update": MEMBER,
  "me.notifications.manage": MEMBER,
  // S2-D23: entrada al portal; homeFor la usa en lugar de comparar el rol con un literal.
  "portal.view": MEMBER,
  // S2-F2: /clases/horario es solo admin (ROUTES.md, "Clases").
  "classes.schedule": ADMIN,
} as const satisfies Record<string, readonly Role[]>;

/** Etiqueta visible de cada rol (TopBar, listas de usuarios). */
export const ROLE_LABELS: Readonly<Record<Role, string>> = Object.freeze({ admin: "Admin", coach: "Coach", member: "Socio" });

export type Action = keyof typeof TABLE;

export const ACTIONS = Object.freeze(Object.keys(TABLE) as Action[]);

/** Matriz acción → roles, congelada (no se modifica en tiempo de ejecución). */
export const MATRIX: Readonly<Record<Action, readonly Role[]>> = Object.freeze(
  Object.fromEntries(ACTIONS.map((action) => [action, Object.freeze([...TABLE[action]])])) as Record<
    Action,
    readonly Role[]
  >,
);

/** ¿Puede este rol hacer esta acción? Niega por defecto: sin rol, acción o rol desconocidos. */
export function can(role: Role | null | undefined, action: Action): boolean {
  if (!role) return false;
  if (!Object.hasOwn(MATRIX, action)) return false;
  return MATRIX[action].includes(role);
}
