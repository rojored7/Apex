// Archivo de control: viola a propósito las reglas de color y fuente literales.
export function BadInlineHex() {
  return <p style={{ color: "#ff0000", fontFamily: "Arial" }}>Control</p>;
}
