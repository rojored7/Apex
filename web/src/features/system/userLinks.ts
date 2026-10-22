// S2-F4a/F4b: enlace a un usuario. No hay ficha de usuario: es `?usuario=<id>` sobre la lista
// de Usuarios, donde se abre su panel de edición (S2-F4b). Lo usan la tabla (correo y
// "Editar") y el 409 del alta o de la edición (usuario existente). El id va escapado.
// Con `search` (la búsqueda actual de la lista) se conservan los filtros de la URL.
export const USERS_PATH = "/sistema/usuarios";
export const USER_PARAM = "usuario";

export function userHref(id: string, search = ""): string {
  const params = new URLSearchParams(search);
  params.delete(USER_PARAM);
  params.set(USER_PARAM, id);
  return `${USERS_PATH}?${params.toString()}`;
}
