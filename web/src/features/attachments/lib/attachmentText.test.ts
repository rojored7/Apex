// S6-F3 · US-150: textos de la tabla de adjuntos: tamaño legible con coma decimal (Colombia), tipo y
// quien subió (nombre si el contrato lo trae; si no, el id corto).
import { fallbackFileName, formatBytes, kindLabel, uploaderText } from "./attachmentText";

describe("formatBytes", () => {
  it.each([
    [0, "0 B"],
    [512, "512 B"],
    [1023, "1023 B"],
    [1024, "1 KB"],
    [225_280, "220 KB"],
    [1_536, "1,5 KB"],
    [1_048_575, "1024 KB"],
    [1_048_576, "1 MB"],
    [1_572_864, "1,5 MB"],
    [5_242_880, "5 MB"],
  ])("%i bytes se leen %s", (bytes, text) => {
    expect(formatBytes(bytes)).toBe(text);
  });

  it("un valor inválido no se inventa: raya", () => {
    expect(formatBytes(-1)).toBe("—");
    expect(formatBytes(Number.NaN)).toBe("—");
  });
});

describe("kindLabel", () => {
  it("nombra los tres tipos", () => {
    expect(kindLabel("photo")).toBe("Foto de perfil");
    expect(kindLabel("consent")).toBe("Autorización de datos");
    expect(kindLabel("other")).toBe("Otro documento");
  });
});

describe("uploaderText", () => {
  it("usa el nombre si viene y, si no, 'Usuario' con el id corto", () => {
    expect(uploaderText({ uploaded_by: "a0a0a0a0-0000-4000-8000-000000000001" })).toBe("Usuario a0a0a0a0");
    expect(uploaderText({ uploaded_by: "a0a0a0a0-0000-4000-8000-000000000001", uploaded_by_name: "ana" })).toBe("ana");
    expect(uploaderText({ uploaded_by: "a0a0a0a0-0000-4000-8000-000000000001", uploaded_by_name: "  " })).toBe("Usuario a0a0a0a0");
  });
});

describe("fallbackFileName (revisión V11, LOW 9)", () => {
  const id = "bbbb0002-0000-4000-8000-000000000002";

  it.each([
    ["image/jpeg", "adjunto-bbbb0002.jpg"],
    ["image/png", "adjunto-bbbb0002.png"],
    ["application/pdf", "adjunto-bbbb0002.pdf"],
    ["image/webp", "adjunto-bbbb0002"],
  ])("%s -> %s", (mime, expected) => {
    expect(fallbackFileName({ id, mime })).toBe(expected);
  });
});
