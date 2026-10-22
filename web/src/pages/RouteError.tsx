// H1 (revisión del Sprint 2): `errorElement` de la ruta raíz. En lugar de la pantalla en inglés
// de React Router ("Unexpected Application Error!") con el mensaje técnico, un MessagePage en
// español: qué pasó, qué hacer y "Recargar".
// - Tras un despliegue, el chunk con hash de una página diferida ya no existe (404) y el import
//   dinámico rechaza: se recarga sola una vez para traer el index.html nuevo. La marca en
//   sessionStorage (con try/catch: modo privado o almacenamiento bloqueado) evita el bucle si el
//   chunk sigue sin llegar; sin almacenamiento no hay recarga automática.
// - Cualquier otro error (una excepción al pintar) muestra el mismo aviso, sin recargar sola.
// - Dentro de una zona (panel, tablet, portal) va con `inLayout`: el aviso ocupa el <main> del
//   layout y el menú sigue; el de la raíz es el último recurso y trae su propio <main>.
// DESIGN-GAP: docs/design/screens/ no dibuja una pantalla de error; se usa MessagePage como
// NotFound.
import { useEffect } from "react";
import { useRouteError } from "react-router";
import { Button } from "../shared/ui/Button";
import { MessagePage } from "../shared/ui/MessagePage";
import styles from "./NotFound.module.css";
import { reloadPage } from "./reload";

export const CHUNK_RELOAD_KEY = "apex-chunk-reload";
/** Dentro de esta ventana no se vuelve a recargar sola (el chunk sigue sin llegar). */
export const CHUNK_RELOAD_WINDOW_MS = 30_000;

export const ROUTE_ERROR_MESSAGES = {
  title: "Algo salió mal",
  message: "No pudimos abrir esta pantalla. Recarga la página; si vuelve a pasar, avisa al administrador.",
  reload: "Recargar",
} as const;

const CHUNK_ERROR = /dynamically imported module|Importing a module script failed|error loading dynamically imported module|ChunkLoadError/i;

/** El import dinámico de una página falló (chunk que ya no existe o red caída al pedirlo). */
export function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  return error.name === "ChunkLoadError" || CHUNK_ERROR.test(error.message);
}

/** Reserva la única recarga automática; `false` si ya se hizo hace poco o no hay almacenamiento. */
export function claimChunkReload(now: number): boolean {
  try {
    const last = Number(sessionStorage.getItem(CHUNK_RELOAD_KEY));
    if (Number.isFinite(last) && last > 0 && now - last < CHUNK_RELOAD_WINDOW_MS) return false;
    sessionStorage.setItem(CHUNK_RELOAD_KEY, String(now));
    return true;
  } catch {
    return false;
  }
}

export interface RouteErrorProps {
  /** Se pinta dentro del <main> de un layout (no abre otro). */
  inLayout?: boolean;
}

export function RouteError({ inLayout = false }: RouteErrorProps) {
  const isChunk = isChunkLoadError(useRouteError());

  useEffect(() => {
    if (isChunk && claimChunkReload(Date.now())) reloadPage();
  }, [isChunk]);

  const message = (
    <MessagePage title={ROUTE_ERROR_MESSAGES.title} message={ROUTE_ERROR_MESSAGES.message} alert>
      <Button onClick={reloadPage}>{ROUTE_ERROR_MESSAGES.reload}</Button>
    </MessagePage>
  );
  return inLayout ? message : <main className={styles.page}>{message}</main>;
}
