// S2-F4a: enlace a un usuario. No hay ficha de usuario: es `?usuario=<id>` sobre la lista de
// Usuarios, donde S2-F4b abre su panel de edición. Lo usan la tabla (primera columna) y el
// 409 del alta (usuario existente). El id va escapado.
export const USERS_PATH = "/sistema/usuarios";

export function userHref(id: string): string {
  return `${USERS_PATH}?usuario=${encodeURIComponent(id)}`;
}
