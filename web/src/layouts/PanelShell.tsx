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
// S3-F4 (S3-D65, E10): el panel "Registrar pago" se monta aquí una sola vez, en la misma ranura
// `banner`, y cualquier pantalla lo abre con la URL (`?pago=<membresía>` o `?pago=nuevo&socio=`,
// shared/lib/paymentPanel.ts). Solo con la feature `payments` habilitada y solo se descarga cuando
// la URL lo pide. PanelLayout sigue siendo presentacional (no pide datos).
import { lazy, Suspense, useMemo, useState } from "react";
import { useLocation } from "react-router";
import { ENABLED_FEATURES, type Feature } from "../config/features";
import { ROLE_LABELS, can, logout, useSession } from "../core/auth";
import { usePanelTheme } from "../core/theme/theme";
import { ThemeToggle } from "../core/theme/ThemeToggle";
import { readPaymentPanel } from "../shared/lib/paymentPanel";
import { buildNavItems } from "./nav";
import { PanelLayout } from "./PanelLayout";

const ChangePasswordPanel = lazy(async () => ({
  default: (await import("../features/auth/components/ChangePasswordPanel")).ChangePasswordPanel,
}));
const RegisterPaymentPanelHost = lazy(async () => ({
  default: (await import("../features/payments/components/RegisterPaymentPanelHost")).RegisterPaymentPanelHost,
}));

export interface PanelShellProps {
  /** Features habilitadas; por defecto las del sprint (las pruebas pasan otras). */
  enabledFeatures?: ReadonlySet<Feature>;
}

export function PanelShell({ enabledFeatures = ENABLED_FEATURES }: PanelShellProps) {
  usePanelTheme();
  const { user } = useSession();
  const { search } = useLocation();
  const [loggingOut, setLoggingOut] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  // Montado desde la primera apertura: el aviso "Contraseña actualizada" sobrevive al cierre.
  const [accountMounted, setAccountMounted] = useState(false);
  const role = user?.role ?? null;
  const navGroups = useMemo(() => buildNavItems(role, enabledFeatures), [role, enabledFeatures]);
  // Revisión S3-F4 (M3): solo quien puede registrar pagos (el api vuelve a verificar).
  const paymentPanelOpen = user !== null && can(user.role, "payments.register") && enabledFeatures.has("payments") && readPaymentPanel(search) !== null;
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
        user && (accountMounted || paymentPanelOpen) ? (
          <>
            {accountMounted ? (
              <Suspense fallback={null}>
                <ChangePasswordPanel
                  open={accountOpen}
                  onClose={() => {
                    setAccountOpen(false);
                  }}
                />
              </Suspense>
            ) : null}
            {paymentPanelOpen ? (
              <Suspense fallback={null}>
                <RegisterPaymentPanelHost />
              </Suspense>
            ) : null}
          </>
        ) : null
      }
    />
  );
}
