// US-061 T4: barra superior del panel (Inicio.html).
// - Fondo --black en los dos temas, logo de wordmark blanco, nombre del gimnasio ("APEX"
//   mientras no llega gym_name de GET /auth/me), fecha y hora de Bogotá en un subcomponente
//   con su propio temporizador (el resto de la barra no se vuelve a pintar cada minuto).
// - Correo y rol del usuario; con acciones, un menú accesible (aria-haspopup, aria-expanded,
//   flechas, Inicio, Fin, Escape, clic fuera) con "Mi cuenta" y "Cerrar sesión".
// - Ranura para el conmutador de tema (US-068) y botón ☰ de 44 px solo en celular.
import { ChevronDown, Menu } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { formatDateTime } from "../../core/i18n/format";
import styles from "./TopBar.module.css";

export interface TopBarUser {
  email: string;
  roleLabel: string;
}

export interface TopBarNavButton {
  expanded: boolean;
  controls: string;
  onClick: () => void;
}

export interface TopBarProps {
  gymName?: string | undefined;
  user: TopBarUser | null;
  onChangePassword?: (() => void) | undefined;
  onLogout?: (() => void) | undefined;
  logoutPending?: boolean | undefined;
  themeToggle?: ReactNode;
  navButton?: TopBarNavButton | undefined;
}

const CLOCK_TICK_MS = 60_000;
const DEFAULT_GYM_NAME = "APEX";

function TopBarClock() {
  const [now, setNow] = useState(() => new Date().toISOString());
  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date().toISOString());
    }, CLOCK_TICK_MS);
    return () => {
      clearInterval(timer);
    };
  }, []);
  return (
    <span className={styles.clock}>
      <time dateTime={now}>{formatDateTime(now)}</time>
      <span> · Bogotá</span>
    </span>
  );
}

interface MenuEntry {
  key: string;
  label: string;
  disabled: boolean;
  run: () => void;
}

function entriesFor(props: TopBarProps): MenuEntry[] {
  const entries: MenuEntry[] = [];
  if (props.onChangePassword) entries.push({ key: "account", label: "Mi cuenta", disabled: false, run: props.onChangePassword });
  if (props.onLogout) {
    const pending = props.logoutPending === true;
    entries.push({ key: "logout", label: pending ? "Cerrando sesión…" : "Cerrar sesión", disabled: pending, run: props.onLogout });
  }
  return entries;
}

function UserMenu({ user, entries }: { user: TopBarUser; entries: MenuEntry[] }) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (!open) return undefined;
    itemRefs.current[0]?.focus();
    const onPointerDown = (event: MouseEvent): void => {
      if (event.target instanceof Node && wrapperRef.current?.contains(event.target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open]);

  const close = (): void => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    const items = itemRefs.current.filter((el): el is HTMLButtonElement => el !== null);
    const index = items.findIndex((el) => el === document.activeElement);
    const focusAt = (i: number): void => {
      items[(i + items.length) % items.length]?.focus();
    };
    if (event.key === "ArrowDown") focusAt(index + 1);
    else if (event.key === "ArrowUp") focusAt(index - 1);
    else if (event.key === "Home") focusAt(0);
    else if (event.key === "End") focusAt(items.length - 1);
    else if (event.key === "Escape") close();
    else if (event.key === "Tab") setOpen(false);
    else return;
    if (event.key !== "Tab") event.preventDefault();
  };

  return (
    <div ref={wrapperRef} className={styles.userMenu}>
      <button
        ref={triggerRef}
        type="button"
        className={styles.userButton}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? "menu-usuario" : undefined}
        onClick={() => {
          setOpen((value) => !value);
        }}
      >
        <span className={styles.userText}>{`${user.email} · ${user.roleLabel}`}</span>
        <ChevronDown size={20} aria-hidden="true" />
      </button>
      {open && (
        <div id="menu-usuario" role="menu" aria-label="Menú de usuario" className={styles.menu} onKeyDown={onMenuKeyDown}>
          {entries.map((entry, i) => (
            <button
              key={entry.key}
              ref={(el) => {
                itemRefs.current[i] = el;
              }}
              type="button"
              role="menuitem"
              tabIndex={-1}
              className={styles.menuItem}
              aria-disabled={entry.disabled ? true : undefined}
              onClick={() => {
                if (entry.disabled) return;
                close();
                entry.run();
              }}
            >
              {entry.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function TopBar(props: TopBarProps) {
  const { gymName, user, themeToggle, navButton } = props;
  const entries = entriesFor(props);
  return (
    <header className={styles.bar}>
      {navButton && (
        <button
          type="button"
          className={styles.iconButton}
          aria-label="Abrir menú"
          aria-controls={navButton.controls}
          aria-expanded={navButton.expanded}
          onClick={navButton.onClick}
        >
          <Menu size={20} aria-hidden="true" />
        </button>
      )}
      <img className={styles.logo} src="/brand/apex-logo-dark-bg.png" alt="APEX Hybrid Training" width={99} height={28} />
      <span className={styles.gym}>{gymName ?? DEFAULT_GYM_NAME}</span>
      <span className={styles.spacer} />
      <TopBarClock />
      {themeToggle}
      {user &&
        (entries.length > 0 ? (
          <UserMenu user={user} entries={entries} />
        ) : (
          <span className={styles.userTag}>{`${user.email} · ${user.roleLabel}`}</span>
        ))}
    </header>
  );
}
