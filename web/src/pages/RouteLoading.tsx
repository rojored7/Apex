// S2-F2: lo que se ve mientras llega el código de la primera página (rutas diferidas).
import styles from "./NotFound.module.css";

export function RouteLoading() {
  return (
    <div className={styles.page} role="status" aria-live="polite" aria-busy="true">
      Cargando…
    </div>
  );
}
