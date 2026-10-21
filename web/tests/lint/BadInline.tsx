// Archivo de control: viola a propósito la regla de colores literales.
export function BadInline() {
  return <p style={{ color: "rgb(1,2,3)" }}>Control</p>;
}
