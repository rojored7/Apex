// S2-F2: ruta del Sprint 2 cuya pantalla llega en otro slice (routeTable `pending`). Pasa por
// las guardas como la definitiva y solo cambia el contenido.
// DESIGN-GAP: estado intermedio del sprint, sin pantalla de referencia.
import { MessagePage } from "../shared/ui/MessagePage";

export function PendingPage({ title }: { title: string }) {
  return <MessagePage title={title} message="Esta pantalla estará disponible pronto." />;
}
