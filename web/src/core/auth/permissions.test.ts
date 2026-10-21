// US-040 T1: tabla de verdad completa de la matriz de permisos. La matriz esperada es una
// copia literal del desglose (con N-20, Q6, Q7, Q8, Q15, Q25 y N-29 aplicados): si alguien
// cambia permissions.ts sin cambiar esta copia, la prueba falla.
import { ACTIONS, MATRIX, ROLES, can, type Action, type Role } from "./permissions";

const ADMIN_ONLY = [
  "members.delete",
  "members.reactivate",
  "members.document.update",
  "members.export",
  "plans.view",
  "plans.manage",
  "memberships.cancel",
  "payments.void",
  "payments.export",
  "audit.view",
  "users.manage",
  "settings.manage",
  "crypto.manage",
  "notifications.rules.edit",
] as const;

const STAFF = [
  "dashboard.view",
  "members.view",
  "members.create",
  "members.update",
  "members.reveal",
  "members.history.view",
  "memberships.view",
  "memberships.sell",
  "memberships.freeze",
  "payments.view",
  "payments.register",
  "classes.view",
  "attendance.delete",
  "wods.view",
  "movements.view",
  "results.record",
  "athletes.view",
  "notifications.view",
  "account.manage",
] as const;

const MEMBER_ONLY = [
  "me.home.view",
  "me.payments.view",
  "me.wods.view",
  "me.results.submit",
  "me.progress.view",
  "me.profile.update",
  "me.notifications.manage",
] as const;

type Entry = [string, readonly string[]];

const EXPECTED: Record<string, readonly string[]> = Object.fromEntries([
  ...ADMIN_ONLY.map((a): Entry => [a, ["admin"]]),
  ...STAFF.map((a): Entry => [a, ["admin", "coach"]]),
  ...MEMBER_ONLY.map((a): Entry => [a, ["member"]]),
]);

const CASES: [Role, Action, boolean][] = ROLES.flatMap((role) =>
  ACTIONS.map((action): [Role, Action, boolean] => [role, action, (EXPECTED[action] ?? []).includes(role)]),
);

describe("matriz de permisos del front (US-040)", () => {
  it("declara exactamente los tres roles", () => {
    expect([...ROLES]).toEqual(["admin", "coach", "member"]);
  });

  it("declara exactamente las acciones de la matriz aprobada", () => {
    expect([...ACTIONS].sort()).toEqual(Object.keys(EXPECTED).sort());
    expect(new Set(ACTIONS).size).toBe(ACTIONS.length);
  });

  it("la matriz exportada coincide con la copia esperada", () => {
    for (const action of ACTIONS) expect([...MATRIX[action]].sort()).toEqual([...(EXPECTED[action] ?? [])].sort());
  });

  it.each(CASES)("can(%s, %s) es %s", (role, action, expected) => {
    expect(can(role, action)).toBe(expected);
  });

  it("criterio 1: el coach no anula, no cancela, no da de baja, no ve planes ni sistema", () => {
    for (const action of ["payments.void", "memberships.cancel", "members.delete", "plans.manage", "settings.manage"] as const) {
      expect(can("coach", action)).toBe(false);
    }
  });

  it("criterio 2: el coach muestra datos, congela, vende y registra pagos", () => {
    for (const action of ["members.reveal", "memberships.freeze", "memberships.sell", "payments.register"] as const) {
      expect(can("coach", action)).toBe(true);
    }
  });

  it("criterio 3: admin tiene todo el panel y nada del portal", () => {
    for (const action of ACTIONS) expect(can("admin", action)).toBe(!action.startsWith("me."));
  });

  it("criterio 4: member solo tiene acciones me.*", () => {
    for (const action of ACTIONS) expect(can("member", action)).toBe(action.startsWith("me."));
  });

  it("criterio 5: niega por defecto sin rol, con acción desconocida o con rol desconocido", () => {
    expect(can(null, "members.view")).toBe(false);
    expect(can(undefined, "members.view")).toBe(false);
    expect(can("coach", "pagos.anular" as Action)).toBe(false);
    expect(can("coach", "toString" as Action)).toBe(false);
    expect(can("root" as Role, "members.view")).toBe(false);
    // @ts-expect-error -- una acción que no existe no compila.
    expect(can("coach", "no.existe")).toBe(false);
  });

  it("la matriz no se puede modificar en tiempo de ejecución", () => {
    expect(Object.isFrozen(MATRIX)).toBe(true);
    expect(Object.isFrozen(MATRIX["payments.void"])).toBe(true);
  });
});
