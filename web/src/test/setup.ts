import "@testing-library/jest-dom/vitest";
import * as axeMatchers from "vitest-axe/matchers";

expect.extend(axeMatchers);

// S2-F2: los routers de datos de React Router crean `new Request(url, { signal })` en cada
// navegación. En Vitest con jsdom, `AbortSignal` es el de jsdom y `Request` el de Node
// (undici), que lo rechaza ("Expected signal to be an instance of AbortSignal"). Solo en
// pruebas, el Request descarta una señal ajena; las páginas del Sprint 2 no tienen loaders
// que cancelar. En el navegador no hay mezcla de implementaciones.
const NativeRequest = globalThis.Request;

class TestRequest extends NativeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    if (init?.signal && !(init.signal instanceof AbortSignal && isNativeSignal(init.signal))) {
      super(input, { ...init, signal: null });
      return;
    }
    super(input, init);
  }
}

function isNativeSignal(signal: AbortSignal): boolean {
  try {
    new NativeRequest("http://apex.test/", { signal });
    return true;
  } catch {
    return false;
  }
}

globalThis.Request = TestRequest;

// L7 (revisión del Sprint 2): jsdom no implementa canvas y avisa "Not implemented:
// HTMLCanvasElement.prototype.getContext" cada vez que axe prueba `color-contrast`. Un
// getContext que devuelve null es lo que responde un navegador sin ese contexto: axe lo
// trata como "no se puede medir" (el contraste lo mide la prueba de Playwright con axe).
if (typeof HTMLCanvasElement !== "undefined") {
  Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { configurable: true, value: () => null });
}
