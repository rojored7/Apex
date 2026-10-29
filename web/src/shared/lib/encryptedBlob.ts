// S4A-F1 (S4A-D31, S4A-D52, S4A-D105, S4A-D107): reconocer un valor cifrado sin tocar su contenido.
// - El api sustituye todo valor `apx1.` por el marcador `{"encrypted": true, "key_id", "alg"}`; un
//   blob mal formado sale con `key_id` y `alg` nulos (S4A-D105).
// - Defensa en profundidad: el front también reconoce el blob con el formato de CLAUDE.md,
//   `apx1.<key_id>.<alg>.<nonce_b64url>.<ciphertext_b64url>`, por si alguno llegara sin marcador.
// - parseEncryptedBlob devuelve solo la llave y el algoritmo; nunca el nonce ni el texto cifrado.
// - isEncryptedValue dice si un valor debe pintarse como "Cifrado": el marcador (con o sin llave) o
//   cualquier texto que contenga `apx1.` (S4A-D107: aunque esté incrustado o mal formado).
import { isUuid } from "./ids";

export interface EncryptedBlobInfo {
  keyId: string;
  alg: string;
}

const BLOB_PREFIX = "apx1.";
const ALG = /^[A-Za-z0-9_-]+$/;
const BASE64URL = /^[A-Za-z0-9_-]+$/;
const BLOB_PARTS = 5;

const isRecord = (value: unknown): value is Readonly<Record<string, unknown>> => typeof value === "object" && value !== null && !Array.isArray(value);

function fromMarker(value: Readonly<Record<string, unknown>>): EncryptedBlobInfo | null {
  const { key_id: keyId, alg } = value;
  if (value.encrypted !== true || typeof keyId !== "string" || typeof alg !== "string") return null;
  return isUuid(keyId) && ALG.test(alg) ? { keyId, alg } : null;
}

function fromBlob(value: string): EncryptedBlobInfo | null {
  if (!value.startsWith(BLOB_PREFIX)) return null;
  const parts = value.split(".");
  if (parts.length !== BLOB_PARTS) return null;
  const [, keyId = "", alg = "", nonce = "", cipher = ""] = parts;
  if (!isUuid(keyId) || !ALG.test(alg) || !BASE64URL.test(nonce) || !BASE64URL.test(cipher)) return null;
  return { keyId, alg };
}

/** La llave y el algoritmo de un marcador o de un blob bien formado; `null` para cualquier otra cosa. */
export function parseEncryptedBlob(value: unknown): EncryptedBlobInfo | null {
  if (typeof value === "string") return fromBlob(value);
  return isRecord(value) ? fromMarker(value) : null;
}

/** ¿Hay que pintar el valor como "Cifrado"? Nunca se muestra su contenido. */
export function isEncryptedValue(value: unknown): boolean {
  if (typeof value === "string") return value.includes(BLOB_PREFIX);
  return isRecord(value) && value.encrypted === true;
}
