// S4A-F3 (plan del Sprint 4A, paso 121): datos y montaje de prueba de Inicio. El cuerpo imita
// DashboardOut y MovementOut de GET /dashboard (api/src/app/modules/dashboard/schemas.py): el del
// admin con ingresos y montos en las frases, el del coach con `income_month_cop` en null y las frases
// de pagos sin monto (S4A-D118). Los futuros vienen en null (S4A-D33).
import type { ReactElement } from "react";
import type { Role } from "../core/auth";
import { mockApi, renderWithProviders, type ApiMock, type MockHandler, type MockReply } from "./server";
import { signInAs } from "./session";

export const TODAY = "2026-10-20";
/** 2:32 p. m. del 20 de octubre en Bogotá. */
export const NOW = "2026-10-20T19:32:00Z";
export const LAURA_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const DIEGO_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

export interface MovementFixture {
  seq: number;
  at: string;
  table_name: "members.members" | "memberships.memberships" | "payments.payments";
  record_id: string | null;
  member_id: string | null;
  phrase: string;
}

export function movement(overrides: Partial<MovementFixture> = {}): MovementFixture {
  return {
    seq: 500,
    at: NOW,
    table_name: "members.members",
    record_id: LAURA_ID,
    member_id: LAURA_ID,
    phrase: "admin registró a Laura G.",
    ...overrides,
  };
}

/** Diez movimientos en el orden del api (seq descendente), con la hora esperada en Bogotá. */
export const MOVEMENTS: readonly MovementFixture[] = [
  movement({ seq: 510, at: "2026-10-20T19:31:30Z", table_name: "payments.payments", record_id: "99999999-9999-4999-8999-999999999999", phrase: "admin registró un pago de $ 120.000 de Laura G." }),
  movement({ seq: 509, at: "2026-10-20T19:20:00Z", table_name: "memberships.memberships", member_id: DIEGO_ID, record_id: "66666666-6666-4666-8666-666666666666", phrase: "coach vendió Mensual a Diego M." }),
  movement({ seq: 508, at: "2026-10-20T17:10:00Z", phrase: "admin actualizó los datos de Laura G." }),
  movement({ seq: 507, at: "2026-10-20T16:00:00Z", member_id: DIEGO_ID, record_id: DIEGO_ID, phrase: "admin registró a Diego M." }),
  movement({ seq: 506, at: "2026-10-20T14:00:00Z", table_name: "memberships.memberships", phrase: "La membresía Mensual de Laura G. quedó al día" }),
  movement({ seq: 505, at: "2026-10-20T13:00:00Z", table_name: "payments.payments", phrase: "coach anuló un pago de Laura G." }),
  movement({ seq: 504, at: "2026-10-19T22:00:00Z", phrase: "admin reactivó a Laura G." }),
  movement({ seq: 503, at: "2026-10-19T12:00:00Z", phrase: "admin dio de baja a Laura G." }),
  movement({ seq: 502, at: "2026-10-15T15:00:00Z", member_id: null, record_id: null, phrase: "admin modificó la ficha de un socio" }),
  movement({ seq: 501, at: "2026-10-14T15:00:00Z", phrase: "admin registró a <b>Laura</b> G." }),
];

/** La hora de cada uno de MOVEMENTS vista desde NOW. */
export const MOVEMENT_TIMES: readonly string[] = [
  "hace un momento",
  "hace 12 min",
  "hoy, 12:10 p. m.",
  "hoy, 11:00 a. m.",
  "hoy, 9:00 a. m.",
  "hoy, 8:00 a. m.",
  "ayer, 5:00 p. m.",
  "ayer, 7:00 a. m.",
  "15 oct 2026, 10:00 a. m.",
  "14 oct 2026, 10:00 a. m.",
];

export interface DashboardFixture {
  today: string;
  members_active: number;
  members_expiring: number;
  members_expired: number;
  members_frozen: number;
  members_pending_payment: number;
  income_month: string;
  income_month_cop: number | null;
  attendance_week: number | null;
  sessions_today: number | null;
  notifications_today: number | null;
  members_without_consent: number | null;
  wod_today: string | null;
  last_movements: MovementFixture[];
}

export function dashboardBody(overrides: Partial<DashboardFixture> = {}): DashboardFixture {
  return {
    today: TODAY,
    members_active: 120,
    members_expiring: 14,
    members_expired: 9,
    members_frozen: 2,
    members_pending_payment: 3,
    income_month: "2026-10",
    income_month_cop: 3_250_000,
    attendance_week: null,
    sessions_today: null,
    notifications_today: null,
    members_without_consent: null,
    wod_today: null,
    last_movements: [...MOVEMENTS],
    ...overrides,
  };
}

/** El cuerpo del coach: sin ingresos y sin montos en las frases de pagos (S4A-D118). */
export function coachDashboardBody(overrides: Partial<DashboardFixture> = {}): DashboardFixture {
  return dashboardBody({
    income_month_cop: null,
    last_movements: MOVEMENTS.map((m) => (m.seq === 510 ? { ...m, phrase: "admin registró un pago de Laura G." } : m)),
    ...overrides,
  });
}

export const ok = (body: DashboardFixture = dashboardBody()): MockReply => ({ status: 200, body });

export const tooMany: MockReply = { status: 429, body: { error: { code: "rate_limited", message: "x" } }, headers: { "Retry-After": "30" } };
export const serverError: MockReply = { status: 500, body: { error: { code: "internal_error", message: "x" } } };

/** GET /dashboard responde con `replies` en orden (el último se repite). */
export function mockDashboard(...replies: MockHandler[]): ApiMock {
  let calls = 0;
  return mockApi({
    "GET /dashboard": (call) => {
      const handler = replies[Math.min(calls, replies.length - 1)] ?? ok();
      calls += 1;
      return typeof handler === "function" ? handler(call) : handler;
    },
  });
}

/** Sesión del rol y montaje con los proveedores de prueba. */
export function renderDashboard(ui: ReactElement, role: Role = "admin") {
  signInAs(role);
  return renderWithProviders(ui, { role });
}
