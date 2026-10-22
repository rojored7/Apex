// S2-F2 (el blueprint lo pone en F3; nace aquí porque las rutas del panel lo necesitan): el
// contenedor de PanelLayout. Lee la sesión y arma la TopBar (correo, etiqueta del rol,
// gimnasio) y el menú del rol con las features del sprint.
// S2-F8: aplica el tema del panel (claro por defecto, la elección guardada si la hay) y pone
// el conmutador en la TopBar. S2-F3 le conecta "Cerrar sesión" (logout) y S2-F4a "Mi cuenta".
import { useMemo } from "react";
import { ENABLED_FEATURES } from "../config/features";
import { ROLE_LABELS, useSession } from "../core/auth";
import { usePanelTheme } from "../core/theme/theme";
import { ThemeToggle } from "../core/theme/ThemeToggle";
import { buildNavItems } from "./nav";
import { PanelLayout } from "./PanelLayout";

export function PanelShell() {
  usePanelTheme();
  const { user } = useSession();
  const role = user?.role ?? null;
  const navGroups = useMemo(() => buildNavItems(role, ENABLED_FEATURES), [role]);
  return (
    <PanelLayout
      user={user ? { email: user.email, roleLabel: ROLE_LABELS[user.role] } : null}
      gymName={user?.gymName}
      navGroups={navGroups}
      themeToggle={<ThemeToggle />}
    />
  );
}
