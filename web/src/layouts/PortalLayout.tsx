// US-062 T2: marco del portal del socio (Portal_Inicio.html).
// - Una columna de máximo 600 px centrada; menú inferior fijo con PORTAL_TABS (icono de
//   20 px más texto, 44 px o más, aria-current en el activo).
// - El contenido lleva un relleno inferior igual al alto del menú más el área segura, para
//   que el último elemento no quede tapado.
// - Sigue el tema del teléfono: quita el data-theme forzado mientras está montado.
// DESIGN-GAP: el contador de avisos de la cabecera ("● 1") llega con el portal (v1.0).
import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router";
import { useForcedTheme } from "../shared/hooks/useForcedTheme";
import { cx } from "../shared/ui/cx";
import { PORTAL_TABS, type PortalTab } from "./portalTabs";
import styles from "./PortalLayout.module.css";

export interface PortalLayoutProps {
  gymName?: string | undefined;
  tabs?: readonly PortalTab[];
  children?: ReactNode;
}

export function PortalLayout({ gymName, tabs = PORTAL_TABS, children }: PortalLayoutProps) {
  useForcedTheme("system");
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <picture>
          <source srcSet="/brand/apex-logo-dark-bg.png" media="(prefers-color-scheme: dark)" />
          <img className={styles.logo} src="/brand/apex-logo-light-bg.png" alt="APEX" width={78} height={22} />
        </picture>
        <span className={styles.gym}>{gymName ?? "APEX"}</span>
      </header>
      <main className={styles.content}>{children ?? <Outlet />}</main>
      <nav aria-label="Menú del portal" className={styles.tabs}>
        <ul className={styles.tabList}>
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <li key={tab.to} className={styles.tabItem}>
                <NavLink to={tab.to} end={tab.end === true} className={({ isActive }) => cx(styles.tab, isActive && styles.active)}>
                  <Icon size={20} aria-hidden="true" />
                  <span>{tab.label}</span>
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
