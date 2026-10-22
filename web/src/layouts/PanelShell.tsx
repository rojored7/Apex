// S2-F2 (el blueprint lo pone en F3; nace aquí porque las rutas del panel lo necesitan): el
// contenedor de PanelLayout. Lee la sesión y arma la TopBar (correo, etiqueta del rol,
// gimnasio) y el menú del rol con las features del sprint.
// S2-F8: aplica el tema del panel (claro por defecto, la elección guardada si la hay) y pone
// el conmutador en la TopBar.
// S2-F3 (US-044): "Cerrar sesión" llama a logout(); la opción queda deshabilitada mientras dura
// la petición. Al terminar (bien o mal) la sesión queda limpia y RequireAuth lleva a /login,
// que avisa si el servidor no confirmó el cierre (H-1).
// S2-F4a (US-045): "Mi cuenta" abre ChangePasswordPanel; su aviso "Contraseña actualizada"
// queda arriba del contenido (ranura `banner` de PanelLayout). El panel se descarga la
// primera vez que se abre (React Hook Form y Zod no entran al chunk principal).
import { lazy, Suspense, useMemo, useState } from "react";
import { ENABLED_FEATURES } from "../config/features";
import { ROLE_LABELS, logout, useSession } from "../core/auth";
import { usePanelTheme } from "../core/theme/theme";
import { ThemeToggle } from "../core/theme/ThemeToggle";
const ChangePasswordPanel = lazy(async () => ({
  default: (await import("../features/auth/components/ChangePasswordPanel")).ChangePasswordPanel,
}));
import { buildNavItems } from "./nav";
import { PanelLayout } from "./PanelLayout";

export function PanelShell() {
  usePanelTheme();
  const { user } = useSession();
  const [loggingOut, setLoggingOut] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  // Montado desde la primera apertura: el aviso "Contraseña actualizada" sobrevive al cierre.
  const [accountMounted, setAccountMounted] = useState(false);
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
      onChangePassword={
        user
          ? () => {
              setAccountMounted(true);
              setAccountOpen(true);
            }
          : undefined
      }
      onLogout={user ? onLogout : undefined}
      logoutPending={loggingOut}
      themeToggle={<ThemeToggle />}
      banner={
        user && accountMounted ? (
          <Suspense fallback={null}>
            <ChangePasswordPanel
              open={accountOpen}
              onClose={() => {
                setAccountOpen(false);
              }}
            />
          </Suspense>
        ) : null
      }
    />
  );
}
