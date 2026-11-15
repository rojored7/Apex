// @vitest-environment node
// S4A-F3, revisión de seguridad (M1, M2, L5): la forma de GET /dashboard se valida estricta. Una clave
// de más, un id que no es UUID o ingresos negativos son `invalid_response`, nunca datos en pantalla.
import { CLIENT_ERROR_CODES } from "../../core/api/errorCodes";
import { ApiError } from "../../core/api/errors";
import { parseResponse } from "../../core/api/response";
import { MOVEMENTS, dashboardBody, movement } from "../../test/dashboard";
import { dashboardSchema, movementSchema } from "./schemas";

function invalid(run: () => unknown): ApiError {
  try {
    run();
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("se esperaba invalid_response");
}

describe("dashboardSchema y movementSchema (revisión de seguridad de F3)", () => {
  it("el cuerpo del api pasa tal cual", () => {
    expect(parseResponse(dashboardSchema, dashboardBody()).last_movements).toHaveLength(MOVEMENTS.length);
  });

  it("M1: un movimiento con una clave de más (before/after de la auditoría) es invalid_response", () => {
    expect(invalid(() => parseResponse(movementSchema, { ...movement(), after: {} })).code).toBe(CLIENT_ERROR_CODES.invalidResponse);
    expect(invalid(() => parseResponse(dashboardSchema, dashboardBody({ last_movements: [{ ...movement(), before: { phone: "x" } }] as never }))).code).toBe(
      CLIENT_ERROR_CODES.invalidResponse,
    );
  });

  it("M1: el tablero con una clave de más es invalid_response", () => {
    expect(invalid(() => parseResponse(dashboardSchema, { ...dashboardBody(), x: 1 })).code).toBe(CLIENT_ERROR_CODES.invalidResponse);
  });

  it.each(["../x", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/../../sistema", "", "javascript:alert(1)"])("M2: member_id %j no es un UUID: invalid_response", (id) => {
    expect(invalid(() => parseResponse(movementSchema, movement({ member_id: id }))).code).toBe(CLIENT_ERROR_CODES.invalidResponse);
  });

  it("M2: record_id que no es UUID es invalid_response; null vale en los dos", () => {
    expect(invalid(() => parseResponse(movementSchema, movement({ record_id: "../x" }))).code).toBe(CLIENT_ERROR_CODES.invalidResponse);
    expect(parseResponse(movementSchema, movement({ member_id: null, record_id: null })).member_id).toBeNull();
  });

  it("L5: ingresos negativos son invalid_response; null (coach) y cero valen", () => {
    expect(invalid(() => parseResponse(dashboardSchema, dashboardBody({ income_month_cop: -1 }))).code).toBe(CLIENT_ERROR_CODES.invalidResponse);
    expect(parseResponse(dashboardSchema, dashboardBody({ income_month_cop: null })).income_month_cop).toBeNull();
    expect(parseResponse(dashboardSchema, dashboardBody({ income_month_cop: 0 })).income_month_cop).toBe(0);
  });

  it("S7-R3: attendance_week null o sessions_today con más de 50 o un id que no es UUID son invalid_response", () => {
    const sesion = { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa01", starts_at: "2026-10-21T11:00:00Z", coach_name: null, capacity: 15, attendance_count: 1, duration_min: 60, status: "scheduled" as const };
    expect(invalid(() => parseResponse(dashboardSchema, { ...dashboardBody(), attendance_week: null })).code).toBe(CLIENT_ERROR_CODES.invalidResponse);
    expect(invalid(() => parseResponse(dashboardSchema, dashboardBody({ sessions_today: Array.from({ length: 51 }, () => sesion) }))).code).toBe(CLIENT_ERROR_CODES.invalidResponse);
    expect(invalid(() => parseResponse(dashboardSchema, dashboardBody({ sessions_today: [{ ...sesion, id: "../x" }] }))).code).toBe(CLIENT_ERROR_CODES.invalidResponse);
    expect(parseResponse(dashboardSchema, dashboardBody({ sessions_today: [sesion] })).sessions_today).toHaveLength(1);
  });

  it("S8-B5: wod_today es un objeto estricto o null; un string o una clave de más es invalid_response", () => {
    const wod = { id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb01", title: "Fran", score_type: "time" as const, is_benchmark: true };
    expect(parseResponse(dashboardSchema, dashboardBody({ wod_today: wod })).wod_today).toEqual(wod);
    expect(parseResponse(dashboardSchema, dashboardBody({ wod_today: null })).wod_today).toBeNull();
    expect(invalid(() => parseResponse(dashboardSchema, { ...dashboardBody(), wod_today: "Fran" })).code).toBe(CLIENT_ERROR_CODES.invalidResponse);
    expect(invalid(() => parseResponse(dashboardSchema, { ...dashboardBody(), wod_today: { ...wod, x: 1 } })).code).toBe(CLIENT_ERROR_CODES.invalidResponse);
    expect(invalid(() => parseResponse(dashboardSchema, { ...dashboardBody(), wod_today: { ...wod, id: "../x" } })).code).toBe(CLIENT_ERROR_CODES.invalidResponse);
  });

  it("un futuro ausente es invalid_response (nullable, no optional)", () => {
    const rest: Record<string, unknown> = { ...dashboardBody() };
    delete rest.sessions_today;
    expect(invalid(() => parseResponse(dashboardSchema, rest)).code).toBe(CLIENT_ERROR_CODES.invalidResponse);
  });
});
