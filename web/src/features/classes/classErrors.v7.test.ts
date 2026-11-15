// S7-V7f (L-11): los mensajes de check-in y de quitar una asistencia por código, no solo por status.
import { ApiError } from "../../core/api/errors";
import { checkInMessage, CHECKIN_MESSAGES, removeAttendanceError, REMOVE_ATTENDANCE_MESSAGES, SESSION_LOAD_MESSAGES } from "./classErrors";

const apiError = (status: number, code: string): ApiError => new ApiError({ status, code, message: "x" });

describe("checkInMessage", () => {
  it("404 session_not_found habla de la sesión, no del socio", () => {
    expect(checkInMessage(apiError(404, "session_not_found"))).toBe(SESSION_LOAD_MESSAGES.notFound);
  });

  it("404 de otro código sigue diciendo que el socio ya no existe", () => {
    expect(checkInMessage(apiError(404, "member_not_found"))).toBe(CHECKIN_MESSAGES.notFound);
  });
});

describe("removeAttendanceError", () => {
  it("403 attendance_locked dice que la quita un administrador", () => {
    expect(removeAttendanceError(apiError(403, "attendance_locked")).message).toBe(REMOVE_ATTENDANCE_MESSAGES.locked);
  });

  it("un 403 de otro código no dice «bloqueada»", () => {
    expect(removeAttendanceError(apiError(403, "forbidden")).message).not.toBe(REMOVE_ATTENDANCE_MESSAGES.locked);
  });
});
