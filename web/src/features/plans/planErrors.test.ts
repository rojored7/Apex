// S2-F7: traducción de los errores del api de planes a mensajes de la pantalla.
import { ApiError, GENERIC_MESSAGES } from "../../core/api/errors";
import {
  ACTIVE_MESSAGES,
  activeError,
  createErrorMessage,
  DELETE_MESSAGES,
  deleteError,
  DETAIL_MESSAGES,
  detailErrorMessage,
  fieldErrorOf,
  isTransientError,
  LIST_MESSAGES,
  listError,
  planInUseMessage,
  UPDATE_MESSAGES,
  updateErrorMessage,
} from "./planErrors";
import { PLAN_MESSAGES } from "./schemas";

const err = (status: number, code: string, extra: Partial<ConstructorParameters<typeof ApiError>[0]> = {}) => new ApiError({ status, code, message: "api", ...extra });

describe("fieldErrorOf", () => {
  it("el 409 por nombre va bajo 'name' con el plan existente, aunque el código cambie", () => {
    expect(fieldErrorOf(err(409, "plan_name_duplicated", { existingId: "x" }))).toEqual({ path: "name", message: PLAN_MESSAGES.duplicated, existingId: "x" });
    expect(fieldErrorOf(err(409, "conflict", { field: "name" }))).toEqual({ path: "name", message: PLAN_MESSAGES.duplicated, existingId: null });
  });

  it("el 422 con kind va bajo el tipo; sin field, otro 409 o algo ajeno no van a un campo", () => {
    expect(fieldErrorOf(err(422, "validation_error", { field: "kind" }))?.path).toBe("kind");
    expect(fieldErrorOf(err(422, "validation_error"))).toBeNull();
    expect(fieldErrorOf(err(409, "version_conflict"))).toBeNull();
    expect(fieldErrorOf(new Error("x"))).toBeNull();
  });
});

describe("mensajes generales", () => {
  it("un error ajeno, un timeout y una respuesta inválida tienen su mensaje", () => {
    expect(createErrorMessage(new Error("x"))).toBe("No pudimos crear el plan. Revisa los datos e intenta de nuevo.");
    expect(createErrorMessage(err(0, "timeout"))).toBe(GENERIC_MESSAGES.timeout);
    expect(createErrorMessage(err(0, "invalid_response", { message: "inválida" }))).toBe("inválida");
    expect(createErrorMessage(err(400, "plan_error"))).toBe("No pudimos crear el plan. Revisa los datos e intenta de nuevo.");
  });

  it("listError: sin error nada; un 429 dice cuánto esperar; algo ajeno es el mensaje de carga", () => {
    expect(listError(null)).toBeNull();
    expect(listError(err(429, "rate_limited", { retryAfterS: 1 }))?.message).toBe("Hiciste muchas búsquedas seguidas. Espera 1 segundo e intenta de nuevo.");
    expect(listError(new Error("x"))?.message).toBe(LIST_MESSAGES.failed);
    expect(listError(err(0, "network_error"))?.message).toBe(GENERIC_MESSAGES.network_error);
  });

  it("detailErrorMessage: algo ajeno o la red", () => {
    expect(detailErrorMessage(new Error("x"))).toBe(DETAIL_MESSAGES.failed);
    expect(detailErrorMessage(null)).toBe(DETAIL_MESSAGES.failed);
    expect(detailErrorMessage(err(0, "network_error"))).toBe(GENERIC_MESSAGES.network_error);
  });

  it("isTransientError: un 4xx no se reintenta; un 5xx, la red o algo ajeno sí", () => {
    expect(isTransientError(err(403, "forbidden"))).toBe(false);
    expect(isTransientError(err(404, "plan_not_found"))).toBe(false);
    expect(isTransientError(err(500, "internal"))).toBe(true);
    expect(isTransientError(err(0, "network_error"))).toBe(true);
    expect(isTransientError(new Error("x"))).toBe(true);
  });
});

describe("S4A-F4 · editar, activar o desactivar y dar de baja", () => {
  it("updateErrorMessage: 404, 403, 429 con la espera, 5xx, la red y lo demás", () => {
    expect(updateErrorMessage(err(404, "plan_not_found"))).toBe(UPDATE_MESSAGES.notFound);
    expect(updateErrorMessage(err(403, "forbidden"))).toBe(UPDATE_MESSAGES.forbidden);
    expect(updateErrorMessage(err(429, "rate_limited", { retryAfterS: 5 }))).toBe("Hiciste muchos cambios seguidos. Espera 5 segundos e intenta de nuevo.");
    expect(updateErrorMessage(err(500, "internal_error"))).toBe(UPDATE_MESSAGES.server);
    expect(updateErrorMessage(err(0, "network_error"))).toBe(GENERIC_MESSAGES.network_error);
    expect(updateErrorMessage(err(503, "busy"))).toBe("El sistema está ocupado; intenta de nuevo.");
    expect(updateErrorMessage(err(400, "otro"))).toBe(UPDATE_MESSAGES.generic);
    expect(updateErrorMessage(new Error("x"))).toBe(UPDATE_MESSAGES.generic);
  });

  it("activeError: conserva status y code con el mensaje de la pantalla", () => {
    const error = activeError(err(404, "plan_not_found"));
    expect(error).toMatchObject({ status: 404, code: "plan_not_found", message: ACTIVE_MESSAGES.notFound });
    expect(activeError(err(403, "forbidden")).message).toBe(ACTIVE_MESSAGES.forbidden);
    expect(activeError(err(429, "rate_limited", { retryAfterS: 1 })).message).toBe("Hiciste muchos cambios seguidos. Espera 1 segundo e intenta de nuevo.");
    expect(activeError(err(500, "internal_error")).message).toBe(ACTIVE_MESSAGES.generic);
    expect(activeError(new Error("x")).message).toBe(ACTIVE_MESSAGES.generic);
  });

  it("deleteError: 404, 403, 429 y lo demás", () => {
    expect(deleteError(err(404, "plan_not_found")).message).toBe(DELETE_MESSAGES.notFound);
    expect(deleteError(err(403, "forbidden")).message).toBe(DELETE_MESSAGES.forbidden);
    expect(deleteError(err(429, "rate_limited")).message).toBe("Hiciste muchos cambios seguidos. Espera un momento e intenta de nuevo.");
    expect(deleteError(err(500, "internal_error")).message).toBe(DELETE_MESSAGES.generic);
    expect(deleteError(new Error("x")).message).toBe(DELETE_MESSAGES.generic);
  });

  it("planInUseMessage: el mensaje del api del 409 plan_has_active_memberships; sin texto, el propio; otro error, null", () => {
    expect(planInUseMessage(err(409, "plan_has_active_memberships", { message: "Este plan tiene 1 membresía activa, desactívalo en su lugar." }))).toBe(
      "Este plan tiene 1 membresía activa, desactívalo en su lugar.",
    );
    expect(planInUseMessage(err(409, "plan_has_active_memberships", { message: "  " }))).toBe(DELETE_MESSAGES.inUse);
    expect(planInUseMessage(err(409, "plan_name_duplicated"))).toBeNull();
    expect(planInUseMessage(err(404, "plan_has_active_memberships"))).toBeNull();
    expect(planInUseMessage(new Error("plan_has_active_memberships"))).toBeNull();
  });
});
