// S2-F4b: reglas de qué acciones tiene cada fila de Usuarios (L-13) y los mensajes de error
// de esas acciones por código.
import { ApiError } from "../../core/api/errors";
import { rowActions, toUserActionError, USER_ACTION_MESSAGES, userActionMessage } from "./userActions";

const SELF = "self";
const row = (role: "admin" | "coach" | "member", status: "active" | "pending_activation" | "locked" | "inactive" | "deleted", id = "other") => ({ id, role, status });

describe("rowActions", () => {
  it("una cuenta dada de baja solo se puede ver", () => {
    expect(rowActions(row("coach", "deleted"), SELF)).toEqual(["edit"]);
  });

  it("la propia cuenta: editar y cerrar sesiones, nada más", () => {
    expect(rowActions(row("admin", "active", SELF), SELF)).toEqual(["edit", "revoke"]);
  });

  it("un coach activo tiene todas las acciones, con bloquear", () => {
    expect(rowActions(row("coach", "active"), SELF)).toEqual(["edit", "revoke", "resend", "lock", "delete"]);
  });

  it("un bloqueado no recibe enlace y se desbloquea", () => {
    expect(rowActions(row("coach", "locked"), SELF)).toEqual(["edit", "revoke", "unlock", "delete"]);
  });

  it("un admin activo (con contraseña) no recibe enlace; uno pendiente sí", () => {
    expect(rowActions(row("admin", "active"), SELF)).not.toContain("resend");
    expect(rowActions(row("admin", "pending_activation"), SELF)).toContain("resend");
    expect(rowActions(row("admin", "inactive"), SELF)).toContain("resend");
  });

  it("sin sesión conocida ninguna fila es la propia", () => {
    expect(rowActions(row("coach", "active", SELF), null)).toContain("delete");
  });
});

describe("userActionMessage", () => {
  const err = (status: number, code: string) => new ApiError({ status, code, message: "texto técnico" });

  it.each([
    [409, "last_admin", USER_ACTION_MESSAGES.lastAdmin],
    [409, "cannot_lock_self", USER_ACTION_MESSAGES.cannotLockSelf],
    [409, "already_locked", USER_ACTION_MESSAGES.alreadyLocked],
    [409, "not_locked", USER_ACTION_MESSAGES.notLocked],
    [409, "user_not_eligible", USER_ACTION_MESSAGES.notEligible],
    [404, "user_not_found", USER_ACTION_MESSAGES.notFound],
    [403, "forbidden", USER_ACTION_MESSAGES.forbidden],
    [429, "rate_limited", USER_ACTION_MESSAGES.tooMany],
    [500, "internal", USER_ACTION_MESSAGES.failed],
    [409, "otro_conflicto", USER_ACTION_MESSAGES.failed],
  ])("%i %s", (status, code, message) => {
    expect(userActionMessage(err(status, code))).toBe(message);
  });

  it("red, timeout, respuesta inválida y errores desconocidos", () => {
    expect(userActionMessage(err(0, "network_error"))).toBe("No pudimos conectar con el servidor. Intenta de nuevo.");
    expect(userActionMessage(err(0, "timeout"))).toBe("El servidor tardó demasiado en responder. Intenta de nuevo.");
    expect(userActionMessage(new ApiError({ status: 0, code: "invalid_response", message: "La respuesta no es válida." }))).toBe("La respuesta no es válida.");
    expect(userActionMessage(new Error("x"))).toBe(USER_ACTION_MESSAGES.failed);
  });
});

describe("toUserActionError", () => {
  it("conserva código y estado con el mensaje de la pantalla", () => {
    const mapped = toUserActionError(new ApiError({ status: 409, code: "last_admin", message: "x", field: "role" }));

    expect(mapped).toMatchObject({ status: 409, code: "last_admin", field: "role", message: USER_ACTION_MESSAGES.lastAdmin });
  });

  it("un error que no es del api queda como desconocido", () => {
    expect(toUserActionError(new Error("x"))).toMatchObject({ status: 0, code: "unknown", message: USER_ACTION_MESSAGES.failed });
  });
});
