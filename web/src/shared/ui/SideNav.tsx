// US-061 T5: menú lateral del panel.
// - Grupos con título en --text-section-title (Inicio va sin título).
// - El ítem activo lleva aria-current="page" (NavLink) y un indicador que no depende solo
//   del color: barra lateral y peso 700, además del fondo invertido.
// - Modo "inline" (escritorio y tablet) o "drawer" (celular): diálogo modal con el foco
//   atrapado; Escape, el botón de cerrar, el clic en el velo o elegir una entrada lo cierran,
//   y useFocusTrap devuelve el foco al botón que lo abrió.
// DESIGN-GAP: el diseño no dibuja el cajón en celular ni el modo plegado a iconos de tablet
// (768 a 1023 px); se siguen las pautas del desglose de US-061 (T3 y T5).
import { X } from "lucide-react";
import { NavLink } from "react-router";
import type { NavGroup } from "../../layouts/nav";
import { useFocusTrap } from "../hooks/useFocusTrap";
import { cx } from "./cx";
import styles from "./SideNav.module.css";

export interface SideNavProps {
  groups: readonly NavGroup[];
  mode?: "inline" | "drawer";
  /** Solo en modo cajón. */
  open?: boolean;
  onClose?: () => void;
  id?: string;
}

const NAV_LABEL = "Menú principal";

function NavList({ groups, onNavigate }: { groups: readonly NavGroup[]; onNavigate?: (() => void) | undefined }) {
  return (
    <ul className={styles.groups}>
      {groups.map((group) => (
        <li key={group.id} className={styles.group}>
          {group.title !== null && (
            <p className={styles.groupTitle} id={`nav-grupo-${group.id}`}>
              {group.title}
            </p>
          )}
          <ul className={styles.items} aria-labelledby={group.title !== null ? `nav-grupo-${group.id}` : undefined}>
            {group.items.map((entry) => {
              const Icon = entry.icon;
              return (
                <li key={entry.to}>
                  <NavLink
                    to={entry.to}
                    end={entry.to === "/"}
                    title={entry.label}
                    className={({ isActive }) => cx(styles.link, isActive && styles.active)}
                    onClick={onNavigate}
                  >
                    <Icon className={styles.icon} size={20} aria-hidden="true" />
                    <span className={styles.label}>{entry.label}</span>
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </li>
      ))}
    </ul>
  );
}

export function SideNav({ groups, mode = "inline", open = false, onClose, id }: SideNavProps) {
  const isDrawer = mode === "drawer";
  const trapRef = useFocusTrap<HTMLDivElement>(isDrawer && open, { onEscape: onClose });

  if (!isDrawer) {
    return (
      <nav id={id} aria-label={NAV_LABEL} className={cx(styles.nav, styles.inline)}>
        <NavList groups={groups} />
      </nav>
    );
  }
  if (!open) return null;
  return (
    <div className={styles.overlay}>
      <div className={styles.backdrop} data-testid="sidenav-backdrop" aria-hidden="true" onClick={onClose} />
      <div ref={trapRef} id={id} role="dialog" aria-modal="true" aria-label={NAV_LABEL} tabIndex={-1} className={styles.drawer}>
        <button type="button" className={styles.close} aria-label="Cerrar menú" onClick={onClose}>
          <X size={20} aria-hidden="true" />
        </button>
        <nav aria-label={NAV_LABEL} className={styles.nav}>
          <NavList groups={groups} onNavigate={onClose} />
        </nav>
      </div>
    </div>
  );
}
