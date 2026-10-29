// S4A-F1 · US-103 (S4A-D58, S4A-D105, S4A-D107): un valor del detalle de auditoría como texto.
// - Cifrado (marcador o `apx1.`): "Cifrado · llave <key_id>" o "Cifrado · sin llave identificable";
//   nunca el contenido.
// - `{"truncated": true}` (S4A-D107, más de 32 niveles en el api): "(recortado)".
// - Un objeto o una lista se aplana en "clave.sub: valor · otra: valor" y todo se corta a 2.000
//   caracteres con "…". El resultado es texto plano: React lo escapa (sin innerHTML).
import { isEncryptedValue, parseEncryptedBlob } from "../../shared/lib/encryptedBlob";

export const MAX_VALUE_CHARS = 2_000;
export const EMPTY_SIDE = "(sin valor)";
export const TRUNCATED = "(recortado)";
/** Revisión de seguridad de F1 (LOW 2): una clave que parece un blob tampoco se muestra. */
export const ENCRYPTED_KEY = "(clave cifrada)";
const SEPARATOR = " · ";
/** Tope de niveles al aplanar (el api ya corta en 32, S4A-D107). */
const MAX_FLATTEN_DEPTH = 32;

const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> => typeof value === "object" && value !== null && !Array.isArray(value);
export const auditKeyText = (key: string): string => (isEncryptedValue(key) ? ENCRYPTED_KEY : key);
const isTruncated = (value: unknown): boolean => isRecord(value) && value.truncated === true && Object.keys(value).length === 1;

function encryptedText(value: unknown): string {
  const info = parseEncryptedBlob(value);
  return info ? `Cifrado · llave ${info.keyId}` : "Cifrado · sin llave identificable";
}

function scalarText(value: unknown): string {
  if (value === null || value === undefined) return EMPTY_SIDE;
  if (typeof value === "boolean") return value ? "sí" : "no";
  if (typeof value === "string" || typeof value === "number" || typeof value === "bigint") return String(value);
  return JSON.stringify(value);
}

/** Pares "ruta: valor" de un valor anidado; las hojas cifradas o recortadas no se abren. */
function flatten(value: unknown, path: string, depth: number): string[] {
  if (isEncryptedValue(value)) return [`${path}: ${encryptedText(value)}`];
  if (isTruncated(value) || depth > MAX_FLATTEN_DEPTH) return [`${path}: ${TRUNCATED}`];
  const entries: [string, unknown][] = Array.isArray(value) ? value.map((item, index) => [String(index), item]) : isRecord(value) ? Object.entries(value) : [];
  if (entries.length === 0 && (Array.isArray(value) || isRecord(value))) return [`${path}: ${EMPTY_SIDE}`];
  if (entries.length === 0) return [`${path}: ${scalarText(value)}`];
  return entries.flatMap(([rawKey, item]) => {
    const key = auditKeyText(rawKey);
    return flatten(item, path ? `${path}.${key}` : key, depth + 1);
  });
}

function cut(text: string): string {
  return text.length > MAX_VALUE_CHARS ? `${text.slice(0, MAX_VALUE_CHARS)}…` : text;
}

/** El valor de un lado de un cambio como texto plano, recortado a 2.000 caracteres. */
export function auditValueText(value: unknown, encrypted = false): string {
  if (value === null || value === undefined) return EMPTY_SIDE;
  if (encrypted || isEncryptedValue(value)) return encryptedText(value);
  if (isTruncated(value)) return TRUNCATED;
  if (Array.isArray(value) || isRecord(value)) {
    const pairs = flatten(value, "", 0).map((pair) => pair.replace(/^: /, ""));
    return cut(pairs.join(SEPARATOR));
  }
  return cut(scalarText(value));
}
