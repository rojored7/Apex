// US-053 T4 (criterios 1 y 7): guarda de sesión de las rutas que no son públicas.
// - Al cargar la página restaura la sesión una sola vez (POST /auth/refresh y GET /auth/me);
//   mientras tanto muestra un estado de carga.
// - Sin sesión va a /login?next=<ruta y query>; LoginPage (F3) valida `next` con safeNext.
//   Tras un cierre de sesión (S2-F3) va a /login sin next.
// - Con must_change_password va a /cambiar-clave (S2-D18), salvo que ya esté ahí.
// No hace peticiones con la sesión ya cargada: el rol sale de login o de me.
import { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router";
import { CHANGE_PASSWORD_PATH, LOGIN_PATH } from "./routeAccess";
import { restoreSession, useSession } from "./session";
import styles from "./RequireAuth.module.css";

export function RequireAuth() {
  const { status, user, reason } = useSession();
  const location = useLocation();

  useEffect(() => {
    if (status === "loading") void restoreSession();
  }, [status]);

  if (status === "loading") {
    return (
      <div className={styles.loading} role="status" aria-live="polite" aria-busy="true">
        Cargando tu sesión…
      </div>
    );
  }
  if (user === null) {
    // S2-F3: tras cerrar la sesión (aquí o en otra pestaña) se va a /login sin next.
    if (reason === "logout" || reason === "logout_unconfirmed") return <Navigate to={LOGIN_PATH} replace />;
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={`${LOGIN_PATH}?next=${encodeURIComponent(next)}`} replace />;
  }
  if (user.mustChangePassword && location.pathname !== CHANGE_PASSWORD_PATH) {
    return <Navigate to={CHANGE_PASSWORD_PATH} replace />;
  }
  return <Outlet />;
}
