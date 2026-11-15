// S8-F6 · US-177 (S8-D32, L-4): el token de la TV y su ciclo.
// - El enlace es `/tv#token=<token>`: el fragmento nunca sale en una petición ni queda en el registro de Nginx. Por compatibilidad también
//   se acepta `?token=`, que SÍ viaja al servidor una vez: por eso el enlace que da Configuración usa el fragmento.
// - consumeTvToken() lo lee UNA vez, lo guarda en el navegador de la TV y deja la URL en `/tv` ANTES de la primera petición (nadie ve el
//   token en la barra ni en el historial). Un token con forma inválida se descarta, pero la URL se limpia igual.
// - Decisión (documentada en docs/operacion/tv.md): el token se guarda en localStorage (`apex.tv.token`), solo en el navegador de la TV,
//   para que un reinicio de la TV o un corte de luz no la dejen sin pantalla (no tiene teclado: no hay forma de pegar el enlace de nuevo).
//   El lint solo prohíbe sessionStorage (S4B-D51). Es un token de solo lectura del tablero (nombre con inicial y marca) y se revoca desde
//   Configuración. Si el almacenamiento no está disponible, el token vive en memoria y el enlace se vuelve a abrir tras un reinicio.
export const TV_TOKEN_STORAGE_KEY = "apex.tv.token";
export const TV_PATH = "/tv";

const TOKEN_PATTERN = /^[A-Za-z0-9_-]{16,200}$/;
const TOKEN_PARAM = "token";

function fromUrl(): { token: string | null; present: boolean } {
  const fromHash = new URLSearchParams(window.location.hash.replace(/^#/, "")).get(TOKEN_PARAM);
  const fromQuery = new URLSearchParams(window.location.search).get(TOKEN_PARAM);
  const raw = fromHash ?? fromQuery;
  return { token: raw !== null && TOKEN_PATTERN.test(raw) ? raw : null, present: raw !== null };
}

function readStored(): string | null {
  try {
    const stored = window.localStorage.getItem(TV_TOKEN_STORAGE_KEY);
    return stored !== null && TOKEN_PATTERN.test(stored) ? stored : null;
  } catch {
    return null;
  }
}

function store(token: string): void {
  try {
    window.localStorage.setItem(TV_TOKEN_STORAGE_KEY, token);
  } catch {
    // Sin almacenamiento: el token vive solo en memoria.
  }
}

/** El token de esta TV (el del enlace, o el guardado), con la URL ya limpia; null si no hay. */
export function consumeTvToken(): string | null {
  const url = fromUrl();
  if (url.present) window.history.replaceState(window.history.state, "", TV_PATH);
  if (url.token !== null) {
    store(url.token);
    return url.token;
  }
  return readStored();
}
