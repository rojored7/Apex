// US-064 T1: encabezado de página (Socio_Ficha.html, Socios_Lista.html). Migas opcionales,
// un único h1 en Michroma, total junto al título y hasta tres acciones; las demás van al
// menú "Más acciones". Las acciones siguen al título en el orden de tabulación.
import { ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { Button, type ButtonVariant } from "./Button";
import buttonStyles from "./Button.module.css";
import { cx } from "./cx";
import styles from "./PageHeader.module.css";

export interface Breadcrumb {
  label: string;
  /** Sin href es la página actual. */
  href?: string;
}

export interface PageAction {
  id: string;
  label: string;
  /** Ruta interna; si está, la acción es un enlace. */
  href?: string;
  onClick?: () => void;
  variant?: ButtonVariant;
  /** `danger` para dar de baja o anular: texto explícito, nunca solo un icono. */
  tone?: "danger";
  disabled?: boolean;
}

export interface PageHeaderProps {
  title: string;
  /** Texto junto al título, por ejemplo "342 en total · 269 con membresía". */
  total?: string;
  /** Insignia junto al título (por ejemplo un StatusTag en la ficha). */
  badge?: ReactNode;
  description?: string;
  breadcrumbs?: Breadcrumb[];
  actions?: PageAction[];
}

const MAX_VISIBLE_ACTIONS = 3;

function variantOf(action: PageAction): ButtonVariant {
  return action.tone === "danger" ? "danger" : (action.variant ?? "secondary");
}

function ActionButton({ action }: { action: PageAction }) {
  const variant = variantOf(action);
  if (action.href && !action.disabled) {
    return (
      <Link to={action.href} className={cx(buttonStyles.button, buttonStyles[variant], buttonStyles.md)}>
        {action.label}
      </Link>
    );
  }
  return (
    <Button variant={variant} disabled={action.disabled ?? false} {...(action.onClick ? { onClick: action.onClick } : {})}>
      {action.label}
    </Button>
  );
}

function MoreMenu({ items }: { items: PageAction[] }) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLElement | null)[]>([]);

  const close = (refocus: boolean): void => {
    setOpen(false);
    if (refocus) buttonRef.current?.focus();
  };

  useEffect(() => {
    if (!open) return undefined;
    itemRefs.current[0]?.focus();
    const onPointerDown = (event: MouseEvent): void => {
      if (event.target instanceof Node && !wrapperRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open]);

  const onMenuKeyDown = (event: KeyboardEvent<HTMLUListElement>): void => {
    const current = itemRefs.current.findIndex((el) => el === document.activeElement);
    const last = items.length - 1;
    const moves: Record<string, number> = {
      ArrowDown: current >= last ? 0 : current + 1,
      ArrowUp: current <= 0 ? last : current - 1,
      Home: 0,
      End: last,
    };
    const target = moves[event.key];
    if (target !== undefined) {
      event.preventDefault();
      itemRefs.current[target]?.focus();
    } else if (event.key === "Escape") {
      event.preventDefault();
      close(true);
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  };

  return (
    <div className={styles.more} ref={wrapperRef}>
      <button
        ref={buttonRef}
        type="button"
        className={cx(buttonStyles.button, buttonStyles.secondary, buttonStyles.md)}
        aria-label="Más acciones"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => {
          setOpen((value) => !value);
        }}
      >
        Más
        <ChevronDown size={20} aria-hidden="true" />
      </button>
      {open ? (
        <ul id={menuId} role="menu" aria-label="Más acciones" className={styles.menu} onKeyDown={onMenuKeyDown}>
          {items.map((item, index) => {
            const className = cx(styles.menuItem, item.tone === "danger" && styles.menuDanger);
            const setRef = (el: HTMLElement | null): void => {
              itemRefs.current[index] = el;
            };
            return (
              <li key={item.id} role="none">
                {item.href ? (
                  <Link
                    ref={setRef}
                    role="menuitem"
                    tabIndex={-1}
                    to={item.href}
                    className={className}
                    onClick={() => {
                      close(false);
                    }}
                  >
                    {item.label}
                  </Link>
                ) : (
                  <button
                    ref={setRef}
                    role="menuitem"
                    type="button"
                    tabIndex={-1}
                    className={className}
                    disabled={item.disabled}
                    onClick={() => {
                      item.onClick?.();
                      close(true);
                    }}
                  >
                    {item.label}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

export function PageHeader({ title, total, badge, description, breadcrumbs = [], actions = [] }: PageHeaderProps) {
  const visible = actions.slice(0, MAX_VISIBLE_ACTIONS);
  const overflow = actions.slice(MAX_VISIBLE_ACTIONS);
  const lastCrumb = breadcrumbs.length - 1;

  return (
    <header className={styles.header}>
      {breadcrumbs.length > 0 ? (
        <nav aria-label="Migas" className={styles.crumbs}>
          <ol className={styles.crumbList}>
            {breadcrumbs.map((crumb, index) => (
              <li key={`${crumb.label}-${String(index)}`} className={styles.crumb}>
                {crumb.href && index < lastCrumb ? (
                  <Link to={crumb.href} className={styles.crumbLink}>
                    {crumb.label}
                  </Link>
                ) : (
                  <span aria-current={index === lastCrumb ? "page" : undefined}>{crumb.label}</span>
                )}
              </li>
            ))}
          </ol>
        </nav>
      ) : null}
      <div className={styles.row}>
        <div className={styles.titleBlock}>
          <h1 className={styles.title}>
            {title}
            {total ? <span className={styles.total}>{total}</span> : null}
            {badge ? <span className={styles.badge}>{badge}</span> : null}
          </h1>
          {description ? <p className={styles.description}>{description}</p> : null}
        </div>
        {actions.length > 0 ? (
          <div className={styles.actions}>
            {visible.map((action) => (
              <ActionButton key={action.id} action={action} />
            ))}
            {overflow.length > 0 ? <MoreMenu items={overflow} /> : null}
          </div>
        ) : null}
      </div>
    </header>
  );
}
