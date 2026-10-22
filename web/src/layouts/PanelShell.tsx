// S2-F2 (el blueprint lo pone en F3; nace aquí porque las rutas del panel lo necesitan): el
// contenedor de PanelLayout. Lee la sesión y arma la TopBar (correo, etiqueta del rol,
// gimnasio) y el menú del rol con las features del sprint.
// S2-F3 le conecta "Cerrar sesión" (logout) y S2-F4a "Mi cuenta"; S2-F8, el conmutador de tema.
import { useMemo } from "react";
import { ENABLED_FEATURES } from "../config/features";
import { ROLE_LABELS, useSession } from "../core/auth";
import { buildNavItems } from "./nav";
import { PanelLayout } from "./PanelLayout";

export function PanelShell() {
  const { user } = useSession();
  const role = user?.role ?? null;
  const navGroups = useMemo(() => buildNavItems(role, ENABLED_FEATURES), [role]);
  return (
    <PanelLayout
      user={user ? { email: user.email, roleLabel: ROLE_LABELS[user.role] } : null}
      gymName={user?.gymName}
      navGroups={navGroups}
    />
  );
}
