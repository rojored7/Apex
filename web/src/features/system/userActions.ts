// S2-F4b · US-049 a US-052: qué acciones muestra cada fila de Usuarios y cómo se explican
// los errores de esas acciones ("qué pasó y qué hacer"), por código y nunca con el texto
// técnico del api.
// - La propia cuenta (row.id === session.user.id) no se da de baja, no se bloquea y no recibe
//   enlace (L-13); el api igual lo protege.
// - "Reenviar enlace" (L-13) se oculta además en cuentas bloqueadas o dadas de baja y en las
//   de otro admin activo con contraseña. El front no ve si hay contraseña: toma rol admin
//   (`can(role, "users.manage")`) y `status === "active"`; un admin pendiente de activación sí
//   recibe enlace. Si el api igual responde 409 user_not_eligible, el modal lo explica.
import { API_ERROR_CODES, CLIENT_ERROR_CODES } from "../../core/api/errorCodes";
import { ApiError, isApiError } from "../../core/api/errors";
import { HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_TOO_MANY } from "../../core/api/status";
import { connectionMessage, TOO_MANY_MESSAGE } from "../../shared/lib/apiMessages";
import { can } from "../../core/auth/permissions";
import type { UserRowView } from "./schemas";

export type RowAction = "edit" | "revoke" | "resend" | "lock" | "unlock" | "delete";

export const USER_ACTION_MESSAGES = {
  lastAdmin: "Debe quedar al menos un administrador activo. Nombra a otro administrador antes de hacer este cambio.",
  cannotLockSelf: "No puedes bloquear tu propia cuenta. Si necesitas bloquearla, pídeselo a otro administrador.",
  alreadyLocked: "Esta cuenta ya estaba bloqueada. Cierra y recarga la lista para ver su estado.",
  notLocked: "Esta cuenta ya no estaba bloqueada. Cierra y recarga la lista para ver su estado.",
  notEligible:
    "Esta cuenta no puede recibir un enlace nuevo. Si está bloqueada, desbloquéala primero; el enlace de un administrador activo se genera desde la consola del servidor.",
  notFound: "No encontramos esta cuenta: puede que otra persona ya la haya dado de baja. Cierra y recarga la lista.",
  forbidden: "Solo un administrador puede hacer esto. Si lo necesitas, pídeselo a uno.",
  tooMany: TOO_MANY_MESSAGE,
  failed: "No pudimos completar la acción. Intenta de nuevo en un momento.",
} as const;

const BY_CODE: Partial<Record<string, string>> = {
  [API_ERROR_CODES.lastAdmin]: USER_ACTION_MESSAGES.lastAdmin,
  [API_ERROR_CODES.cannotLockSelf]: USER_ACTION_MESSAGES.cannotLockSelf,
  [API_ERROR_CODES.alreadyLocked]: USER_ACTION_MESSAGES.alreadyLocked,
  [API_ERROR_CODES.notLocked]: USER_ACTION_MESSAGES.notLocked,
  [API_ERROR_CODES.userNotEligible]: USER_ACTION_MESSAGES.notEligible,
};

/** El error de una acción sobre una cuenta en palabras de la pantalla. */
export function userActionMessage(error: unknown): string {
  if (!isApiError(error)) return USER_ACTION_MESSAGES.failed;
  const connection = connectionMessage(error);
  if (connection) return connection;
  const byCode = BY_CODE[error.code];
  if (byCode) return byCode;
  if (error.status === HTTP_NOT_FOUND) return USER_ACTION_MESSAGES.notFound;
  if (error.status === HTTP_FORBIDDEN) return USER_ACTION_MESSAGES.forbidden;
  if (error.status === HTTP_TOO_MANY) return USER_ACTION_MESSAGES.tooMany;
  return USER_ACTION_MESSAGES.failed;
}

/** El mismo error con el mensaje de la pantalla (ConfirmModal muestra `message`). */
export function toUserActionError(error: unknown): ApiError {
  const message = userActionMessage(error);
  if (!isApiError(error)) return new ApiError({ status: 0, code: CLIENT_ERROR_CODES.unknown, message });
  return new ApiError({ status: error.status, code: error.code, message, field: error.field, existingId: error.existingId, retryAfterS: error.retryAfterS });
}

/**
 * Admin activo (L-13): un rol que administra usuarios, en estado active; el front lo toma como
 * "con contraseña". Sin literales de rol (matriz de permissions.ts).
 */
function isActiveAdmin(row: Pick<UserRowView, "role" | "status">): boolean {
  return can(row.role, "users.manage") && row.status === "active";
}

/** Las acciones de una fila, en el orden en que se muestran. */
export function rowActions(row: Pick<UserRowView, "id" | "role" | "status">, currentUserId: string | null): RowAction[] {
  if (row.status === "deleted") return ["edit"];
  const isSelf = row.id === currentUserId;
  const actions: RowAction[] = ["edit", "revoke"];
  if (!isSelf && row.status !== "locked" && !isActiveAdmin(row)) actions.push("resend");
  if (!isSelf) actions.push(row.status === "locked" ? "unlock" : "lock");
  if (!isSelf) actions.push("delete");
  return actions;
}
