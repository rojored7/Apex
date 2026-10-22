// US-067 T5: ruta inexistente o de una versión no habilitada. Un único h1 y un enlace al
// inicio del rol (homeFor): "/" para el equipo, "/mi" para el socio, "/login" sin sesión.
import { homeFor, useRole } from "../core/auth";
import { MessagePage } from "../shared/ui/MessagePage";
import styles from "./NotFound.module.css";

export function NotFound() {
  return (
    <main className={styles.page}>
      <MessagePage
        title="No encontrada"
        message="Esta dirección no existe o todavía no está disponible. Revisa el enlace o vuelve al inicio."
        linkLabel="Ir al inicio"
        linkTo={homeFor(useRole())}
      />
    </main>
  );
}

export default NotFound;
