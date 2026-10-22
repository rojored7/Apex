// US-061 T3: marco del panel (admin y coach).
// - Enlace "Saltar al contenido", TopBar, SideNav y <main id="contenido" tabIndex={-1}>; el
//   orden del DOM es el orden de tabulación (TopBar, menú, contenido).
// - Escritorio (1024 px o más) con menú de --sidebar; tablet con el menú plegado a iconos
//   (CSS de SideNav); celular (menos de 768 px) con el menú en un cajón que abre el ☰.
// - Presentacional: la sesión, el menú del rol y el cierre de sesión llegan por props
//   (PanelShell). El contenido llega como hijos o por la ruta (<Outlet />).
import { useId, useState, type MouseEvent, type ReactNode } from "react";
import { Outlet } from "react-router";
import { MOBILE_QUERY, useMediaQuery } from "../shared/hooks/useMediaQuery";
import { SideNav } from "../shared/ui/SideNav";
import { TopBar, type TopBarUser } from "../shared/ui/TopBar";
import type { NavGroup } from "./nav";
import styles from "./PanelLayout.module.css";

export interface PanelLayoutProps {
  user: TopBarUser | null;
  gymName?: string | undefined;
  navGroups: readonly NavGroup[];
  onChangePassword?: (() => void) | undefined;
  onLogout?: (() => void) | undefined;
  logoutPending?: boolean | undefined;
  themeToggle?: ReactNode;
  children?: ReactNode;
}

export const MAIN_ID = "contenido";

function focusMain(event: MouseEvent<HTMLAnchorElement>): void {
  const main = document.getElementById(MAIN_ID);
  if (!main) return;
  event.preventDefault();
  main.focus();
}

export function PanelLayout({ user, gymName, navGroups, onChangePassword, onLogout, logoutPending, themeToggle, children }: PanelLayoutProps) {
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navId = `menu-principal-${useId().replace(/:/g, "")}`;
  const showDrawer = isMobile && drawerOpen;

  return (
    <div className={styles.shell}>
      <a className={styles.skip} href={`#${MAIN_ID}`} onClick={focusMain}>
        Saltar al contenido
      </a>
      <TopBar
        user={user}
        gymName={gymName}
        onChangePassword={onChangePassword}
        onLogout={onLogout}
        logoutPending={logoutPending}
        themeToggle={themeToggle}
        navButton={
          isMobile
            ? {
                expanded: showDrawer,
                controls: navId,
                onClick: () => {
                  setDrawerOpen(true);
                },
              }
            : undefined
        }
      />
      <div className={styles.body}>
        {isMobile ? (
          <SideNav
            id={navId}
            groups={navGroups}
            mode="drawer"
            open={showDrawer}
            onClose={() => {
              setDrawerOpen(false);
            }}
          />
        ) : (
          <SideNav id={navId} groups={navGroups} />
        )}
        <main id={MAIN_ID} tabIndex={-1} className={styles.main}>
          {children ?? <Outlet />}
        </main>
      </div>
    </div>
  );
}
