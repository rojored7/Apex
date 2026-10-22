// Revisión del Sprint 2 (M5): los códigos HTTP que el front compara, en un solo lugar. Antes se
// redeclaraban en una docena de archivos de features.
export const HTTP_BAD_REQUEST = 400;
export const HTTP_UNAUTHORIZED = 401;
export const HTTP_FORBIDDEN = 403;
export const HTTP_NOT_FOUND = 404;
export const HTTP_CONFLICT = 409;
export const HTTP_UNPROCESSABLE = 422;
export const HTTP_TOO_MANY = 429;
export const HTTP_SERVER_ERROR = 500;

/** 4xx: no es transitorio (credenciales, permiso, validación, conflicto, 429). */
export function isClientErrorStatus(status: number): boolean {
  return status >= HTTP_BAD_REQUEST && status < HTTP_SERVER_ERROR;
}
