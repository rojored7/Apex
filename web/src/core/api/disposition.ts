// S5-F4: el nombre de archivo que propone el api en `Content-Disposition` (RFC 6266). Devuelve el
// valor tal cual vino; quien lo usa lo sanea (shared/lib/download.ts) antes de dárselo al navegador.
const EXTENDED = /filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/;
const QUOTED = /filename\s*=\s*"((?:[^"\\]|\\.)*)"/;
const BARE = /filename\s*=\s*([^;\s"]+)/;
const ESCAPED_CHAR = /\\(.)/g;

function decode(value: string): string | null {
  try {
    return decodeURIComponent(value);
  } catch {
    return null;
  }
}

/** El nombre de `attachment; filename=...`, o null si la cabecera falta o no lo trae. */
export function filenameFromDisposition(header: string | null): string | null {
  if (header === null) return null;
  const extended = EXTENDED.exec(header)?.[1];
  if (extended !== undefined) {
    const decoded = decode(extended.trim());
    if (decoded !== null && decoded !== "") return decoded;
  }
  const quoted = QUOTED.exec(header)?.[1];
  if (quoted !== undefined && quoted !== "") return quoted.replace(ESCAPED_CHAR, "$1");
  const bare = BARE.exec(header)?.[1];
  return bare !== undefined && bare !== "" ? bare : null;
}
