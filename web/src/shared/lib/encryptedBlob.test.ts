// S4A-F1 (S4A-D31, S4A-D52, S4A-D105, S4A-D107): el front reconoce un valor cifrado por el
// marcador del api y, como defensa en profundidad, por el prefijo `apx1.`; nunca devuelve el
// texto cifrado.
import { isEncryptedValue, parseEncryptedBlob } from "./encryptedBlob";

const KEY = "5f0c2a7e-1b3d-4c5e-8f9a-0b1c2d3e4f5a";
const NONCE = "bm9uY2UtZGUtcHJ1ZWJh";
const CIPHER = "dGV4dG8tY2lmcmFkby1zZWNyZXRv";
const BLOB = `apx1.${KEY}.A256GCM.${NONCE}.${CIPHER}`;

describe("parseEncryptedBlob", () => {
  it("un marcador válido del api da keyId y alg", () => {
    expect(parseEncryptedBlob({ encrypted: true, key_id: KEY, alg: "A256GCM" })).toEqual({ keyId: KEY, alg: "A256GCM" });
  });

  it("un blob apx1. válido da keyId y alg", () => {
    expect(parseEncryptedBlob(BLOB)).toEqual({ keyId: KEY, alg: "A256GCM" });
  });

  it("nunca devuelve el texto cifrado: ni el nonce ni el cuarto y quinto segmento", () => {
    const text = JSON.stringify(parseEncryptedBlob(BLOB));

    expect(text).not.toContain(NONCE);
    expect(text).not.toContain(CIPHER);
    expect(Object.keys(parseEncryptedBlob(BLOB) ?? {}).sort()).toEqual(["alg", "keyId"]);
  });

  it.each([
    ["texto sin prefijo", "310 555 0101"],
    ["texto vacío", ""],
    ["un número", 42],
    ["null", null],
    ["undefined", undefined],
    ["un arreglo", [BLOB]],
    ["marcador sin key_id", { encrypted: true, alg: "A256GCM" }],
    ["marcador con key_id nulo (S4A-D105)", { encrypted: true, key_id: null, alg: null }],
    ["marcador con encrypted falso", { encrypted: false, key_id: KEY, alg: "A256GCM" }],
    ["blob con cuatro partes", `apx1.${KEY}.A256GCM.${NONCE}`],
    ["blob con key_id que no es UUID", `apx1.llave.A256GCM.${NONCE}.${CIPHER}`],
    ["blob sin alg", `apx1.${KEY}..${NONCE}.${CIPHER}`],
    ["blob con cifrado fuera de base64url", `apx1.${KEY}.A256GCM.${NONCE}.no+es/base64`],
    ["blob con texto delante", ` ${BLOB}`],
    ["blob con salto final", `${BLOB}\n`],
  ])("%s da null", (_name, value) => {
    expect(parseEncryptedBlob(value)).toBeNull();
  });
});

describe("isEncryptedValue", () => {
  it.each([
    ["el marcador válido", { encrypted: true, key_id: KEY, alg: "A256GCM" }],
    ["el marcador sin llave de un blob mal formado (S4A-D105)", { encrypted: true, key_id: null, alg: null }],
    ["un blob válido", BLOB],
    ["un texto con apx1. incrustado (S4A-D107)", `nota: ${BLOB}`],
    ["un blob mal formado", "apx1.roto"],
  ])("%s es un valor cifrado", (_name, value) => {
    expect(isEncryptedValue(value)).toBe(true);
  });

  it.each([
    ["texto común", "Llamar en la tarde"],
    ["un número", 120_000],
    ["null", null],
    ["el marcador de recorte", { truncated: true }],
    ["un objeto cualquiera", { encrypted: "true" }],
  ])("%s no es un valor cifrado", (_name, value) => {
    expect(isEncryptedValue(value)).toBe(false);
  });
});
