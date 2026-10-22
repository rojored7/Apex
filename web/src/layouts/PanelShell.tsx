// S2-F2 (el blueprint lo pone en F3; nace aquí porque las rutas del panel lo necesitan): el
// contenedor de PanelLayout. Lee la sesión y arma la TopBar (correo, etiqueta del rol,
// gimnasio) y el menú del rol con las features del sprint.
// S2-F8: aplica el tema del panel (claro por defecto, la elección guardada si la hay) y pone
// el conmutador en la TopBar.
// S2-F3 (US-044): "Cerrar sesión" llama a logout(); la opción queda deshabilitada mientras dura
// la petición. Al terminar (bien o mal) la sesión queda limpia y RequireAuth lleva a /login,
// que avisa si el servidor no confirmó el cierre (H-1). S2-F4a conecta "Mi cuenta".
import { useMemo, useState } from "react";
import { ENABLED_FEATURES } from "../config/features";
import { ROLE_LABELS, logout, useSession } from "../core/auth";
import { usePanelTheme } from "../core/theme/theme";
import { ThemeToggle } from "../core/theme/ThemeToggle";
import { buildNavItems } from "./nav";
import { PanelLayout } from "./PanelLayout";

export function PanelShell() {
  usePanelTheme();
  const { user } = useSession();
  const [loggingOut, setLoggingOut] = useState(false);
  const role = user?.role ?? null;
  const navGroups = useMemo(() => buildNavItems(role, ENABLED_FEATURES), [role]);
  const onLogout = (): void => {
    setLoggingOut(true);
    void logout();
  };
  return (
    <PanelLayout
      user={user ? { email: user.email, roleLabel: ROLE_LABELS[user.role] } : null}
      gymName={user?.gymName}
      navGroups={navGroups}
      onLogout={user ? onLogout : undefined}
      logoutPending={loggingOut}
      themeToggle={<ThemeToggle />}
    />
  );
}
