// H1 (revisión del Sprint 2): recargar la página, en un módulo propio para que las pruebas lo
// reemplacen (jsdom no navega).
export function reloadPage(): void {
  window.location.reload();
}
